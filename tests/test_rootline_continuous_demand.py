"""Bounded continuous-control demand through real admission and minute entries."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
import time

import pytest

from modules.telemetry import rootline_ewelink_request_budget as budget
from tests.test_rootline_ewelink_request_budget import MemoryBudget, snapshot, ENV, NOW, fail


def reserve(client, *, kind="irrigation_zone_valve", identity="PARENT"):
    device = "1002851416" if kind == "borehole_pump_power" else "100204e9bc"
    permit = client.reserve_for_on(execution_id=identity, device_id=device, channel=1,
        device_type=kind, region="eu")
    client.begin_on(execution_id=identity, permit=permit, device_id=device, channel=1)
    return {"execution_id": identity, "device_id": device, "channel": 1, "device_type": kind,
        "start_evidence": {"retrieved_at": NOW.isoformat()},
        "provider_start_evidence": {"retrieved_at": NOW.isoformat()}}


@pytest.mark.parametrize("kind,seconds,interval", [
    ("irrigation_zone_valve", 7200, 900), ("borehole_pump_power", 14400, 1800),
    ("borehole_pump_power", 36000, 4500)])
def test_due_slots_survive_restarts_and_duplicate_workers(kind, seconds, interval):
    client = MemoryBudget()
    execution = {**reserve(client, kind=kind), "requested_seconds": seconds}
    sent = []
    for elapsed in range(0, seconds, 60):
        client.backend.now = NOW+timedelta(seconds=elapsed)
        for worker in range(2):
            restarted = MemoryBudget(client.backend)
            try:
                with budget.execution_duty(execution), budget.routine_execution_observation(execution):
                    snapshot(restarted, device=execution["device_id"])
                sent.append(elapsed)
            except budget.OptionalObservationDeferred:
                pass
    # Pacing adds two seconds to each complete read; due admission uses start time.
    assert sent == list(range(interval, seconds, interval))
    assert len(sent) == 7
    assert sum(row["units"] for row in client.backend.events) == 21


def test_optional_group_admits_four_units_atomically_and_preserves_tail():
    client = MemoryBudget(); execution = reserve(client)
    client.backend.state["reserves"]["PARENT"]["remaining"] = 8
    with budget.execution_duty(execution), budget.optional_observation("irrigation_routine"):
        with budget.snapshot_group(expected_device=execution["device_id"], environ=ENV, region="eu") as group:
            for endpoint in ("/v2/user/refresh", "/v2/family", "/v2/device/thing", "/v2/device/thing/status"):
                client.dispatch(region="eu", endpoint=endpoint, send=lambda _: {})
            with pytest.raises(budget.RequestBudgetUnavailable, match="group_exhausted"):
                client.dispatch(region="eu", endpoint="/v2/family", send=lambda _: pytest.fail("fifth request"))
    assert client.backend.state["reserves"]["PARENT"]["remaining"] == 4
    client.backend.advance(901)
    with budget.execution_duty(execution), budget.optional_observation("irrigation_routine"):
        with pytest.raises(budget.RequestBudgetUnavailable, match="tail_protected"):
            snapshot(client)
    # Terminal proof bypasses optional admission and can spend the existing tail.
    with budget.execution_duty(execution):
        snapshot(client)
    assert client.backend.state["reserves"]["PARENT"]["remaining"] == 1


def test_partial_optional_failure_never_refunds_or_enlarges_legacy_reserve():
    client = MemoryBudget(); execution = reserve(client)
    client.backend.state["reserves"]["PARENT"]["remaining"] = 7
    with budget.execution_duty(execution), budget.optional_observation("irrigation_routine"):
        with pytest.raises(budget.RequestBudgetUnavailable, match="tail_protected"):
            snapshot(client)
    assert client.backend.state["reserves"]["PARENT"]["remaining"] == 7
    assert not any(row["units"] for row in client.backend.events)
    client.backend.state["reserves"]["PARENT"]["remaining"] = 8
    with budget.execution_duty(execution), budget.optional_observation("irrigation_routine"):
        with pytest.raises(Exception, match="sanitized"):
            snapshot(client, send=fail(http=503, code=None))
    assert client.backend.state["reserves"]["PARENT"]["remaining"] == 7
    assert sum(row["units"] for row in client.backend.events) == 1
    assert client.backend.state["reserves"]["PARENT"]["optional_groups"] == {}


def test_pulse_retry_token_is_bound_to_invocation_and_last_opportunity():
    client = MemoryBudget()
    last = NOW+timedelta(minutes=7)
    binding = {"zone_execution_id": "PARENT", "device_id": "100204d497", "channel": 1,
        "phase_number": 1, "pulse_number": 1}
    def read(token):
        with budget.optional_observation("pulse_preparation", binding=binding,
                admission_token=token, last_read_at=last.isoformat()):
            return snapshot(client)
    read("invocation-1")
    read("invocation-1")  # Same invocation, distinct fresh snapshots.
    with pytest.raises(budget.OptionalObservationDeferred):
        read("invocation-2")
    client.backend.now = NOW+timedelta(minutes=5)
    read("invocation-3")
    client.backend.now = last
    read("invocation-4")
    with pytest.raises(budget.OptionalObservationDeferred):
        read("invocation-5")
    assert sum(row["units"] for row in client.backend.events) == 12


@pytest.mark.parametrize("cap,used", [("LOCAL_ROLLING_LIMIT",budget.LOCAL_ROLLING_LIMIT-1), ("LOCAL_ROLLING_LIMIT",budget.LOCAL_ROLLING_LIMIT),
    ("FIVE_MINUTE_LIMIT",249), ("FIVE_MINUTE_LIMIT",250)])
def test_optional_whole_group_never_crosses_actual_request_limits(cap, used):
    client = MemoryBudget(); scope = budget.scope_digest(ENV,"eu")
    client.backend.events.append({"at": NOW, "units": used,
        "detail": {"scope": scope,"region":"eu"}})
    with budget.optional_observation("mixer_readiness"):
        with pytest.raises(budget.RequestBudgetUnavailable, match="snapshot_capacity"):
            snapshot(client)
    assert sum(row["units"] for row in client.backend.events) == used


@pytest.mark.parametrize("status", ["eskom_state_retained", "eskom_readiness_unavailable"])
def test_scheduler_retains_eskom_result_inside_existing_finite_projection(status):
    from modules.oom_sakkie.automatic_reassessment_scheduler import _managed_outcomes
    value = {"status":"managed_device_cycle", "eskom":{"status":status,
        "error_type":"X"*200,"private_payload":"excluded"},
        "outcomes":[{"status":"other"} for _ in range(20)]}
    rows = _managed_outcomes(value)
    assert len(rows) == 8
    assert rows[1] == {"managed_device":"eskom","status":status,"error_type":"X"*100}
    assert all(set(row) == {"managed_device","status","error_type"} for row in rows)


class MinuteJourney:
    """Existing entry points, canonical store fixture and real provider normalizer."""
    def __init__(self, monkeypatch, *, borehole_seconds=14400):
        from tests.test_rootline_ewelink_readback import Store as Tokens, env
        from tests.test_rootline_execution_runtime import Store as IrrigationStore
        from tests.test_rootline_managed_devices_runtime import canonical
        from modules.telemetry import rootline_execution_runtime as runtime
        from modules.telemetry import rootline_managed_devices_runtime as managed
        from modules.telemetry import rootline_borehole_commissioning as borehole
        from modules.telemetry import rootline_timed_control as timed
        from modules.telemetry import rootline_ifttt_transport as transport_module
        from modules.telemetry.rootline_ewelink_readback import read_registered_device
        from modules.telemetry.rootline_ewelink_request_budget import current_duty
        from urllib.parse import urlparse
        import json
        self.client = MemoryBudget(environ=env())
        self.start = datetime(2026,11,15,6,0,tzinfo=timezone.utc)
        self.client.backend.now = self.start
        self.source = {**env(), "ROOTLINE_TIMED_CONTROL_ENABLED":"true",
            "ROOTLINE_AUTONOMOUS_BC_ENABLED":"true", "ROOTLINE_BOREHOLE_ENABLED":"true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED":"true", "ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true",
            "ROOTLINE_IFTTT_MAKER_KEY":"offline-fixture"}
        self.tokens = Tokens(self.source)
        self.tokens.record.update(access_expires_at=self.start+timedelta(days=1),
            refresh_expires_at=self.start+timedelta(days=30))
        self.outputs = {"100204e9bc":["off"]*4,"100204d497":["off"]*4,"1002851416":["off"]}
        self.commands=[];self.reads=[];self.admissions=[]
        self.store=IrrigationStore();self.aux={};self.borehole=None;self.rows=[]
        self.borehole_seconds=borehole_seconds
        self.parent_finished=False
        self.weather=None;self.delay_once=0
        journey=self
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return journey.now().astimezone(tz or timezone.utc)
        monkeypatch.setattr(budget,"datetime",Clock)
        original_dispatch=self.client.dispatch
        def dispatch(**kwargs):
            # Same production fenced body, without per-request test threads.
            return self.client._dispatch(**kwargs,deadline=time.monotonic()+20)
        self.client.dispatch=dispatch
        append=self.client._append
        def traced_append(state, **kwargs):
            append(state,**kwargs)
            if kwargs["action"] in {"active_duty_reserved","request_attempt_reserved"}:
                count,recent=self.client._counts(self.client.backend,self.now(),
                    scope=budget.scope_digest(self.source,"eu"),region="eu")
                remaining=sum(row["remaining"] for row in state["reserves"].values())
                self.admissions.append({"action":kwargs["action"],"at":self.now().isoformat(),
                    "count":count,"recent":recent,"remaining":remaining,
                    **(kwargs.get("detail") or {})})
                assert recent+remaining<=250
                assert count+remaining<=budget.LOCAL_ROLLING_LIMIT
        self.client._append=traced_append
        monkeypatch.setattr(budget,"RequestBudget",lambda *_args,**_kwargs:self.client)
        safe=timed.timed_snapshot_safe
        monkeypatch.setattr(timed,"timed_snapshot_safe",lambda value,**kwargs:safe(value,**{"now":self.now(),**kwargs}))
        monkeypatch.setattr(managed,"_canonical_loader",lambda _:canonical)
        monkeypatch.setattr(managed,"canonical_timed_authority",lambda *_args,**_kwargs:True)
        monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state",
            lambda **_: ({"success":True,"current":self.power(),
                "source":{"last_reading_at":self.now().isoformat()}},200))
        monkeypatch.setattr("modules.telemetry.rootline_water_energy_plan.read_current_borehole_faults",lambda *_args,**_kwargs:True)
        self.baseline={"current":True,"stop_mode":"scheduled","device_key":borehole.DEVICE_KEY,
            "maximum_routine_runtime_seconds":36000,"native_fail_stop_seconds":0,
            "baseline_sha256":"b"*64,"registry_generation":9}
        monkeypatch.setattr(borehole,"load_registered_borehole_baseline",lambda **_:self.baseline)
        def request(method,url,**kwargs):
            endpoint=urlparse(url).path
            def send(_):
                self.reads.append({"at":self.now().isoformat(),"endpoint":endpoint,
                    "execution_id":current_duty().get("execution_id"),
                    "device":(budget._group.get() or {}).get("expected_device"),
                    "optional":(budget._optional_observation.get() or {}).get("purpose")})
                if self.delay_once and (budget._optional_observation.get() or {}).get("purpose")=="irrigation_routine":
                    self.client.backend.advance(self.delay_once);self.delay_once=0
                if endpoint=="/v2/user/refresh":return {"at":"rotated-access","rt":"rotated-refresh"}
                if endpoint=="/v2/family":
                    return {"currentFamilyId":"farm","familyList":[{"id":"farm","apikey":"account"}]}
                if endpoint=="/v2/device/thing":
                    return {"thingList":[{"itemType":1,"itemData":{
                        "deviceid":device,"apikey":"account","online":True,
                        "productModel":"MINIR4" if device=="1002851416" else "4CHPROR3",
                        "updatedAt":self.now().isoformat(),"extra":{"uiid":138 if device=="1002851416" else 9},
                        "params":({"switch":states[0],"configure":[{"outlet":0,"startup":"off"}],"pulses":[{"outlet":0,"pulse":"off","width":0}]}
                            if len(states)==1 else {"switches":[{"outlet":i,"switch":state} for i,state in enumerate(states)],
                                "configure":[{"outlet":i,"startup":"off"} for i in range(4)],
                                "pulses":[{"outlet":i,"pulse":"off","width":0} for i in range(4)]})}}
                        for device,states in self.outputs.items()]}
                if endpoint=="/v2/device/thing/status":return {"params":{}}
                raise AssertionError(endpoint)
            return self.client.dispatch(region="eu",endpoint=endpoint,send=send)
        class Transport(transport_module.RootlineIFTTTTransport):
            def _snapshot(self,device_id,channel,*,routine_read=False):
                return self._validated_snapshot(read_registered_device(device_id,
                    token_store=self.token_store,environ=self.environ,http_request=request,
                    now=journey.now(),routine_read=routine_read),device_id,channel)
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def getcode(self):return 200
            def read(self,*_):return b"OK"
        def command(req,**_):
            values=json.loads(req.data)
            state="on" if "_on/" in req.full_url else "off"
            self.outputs[values["value2"]][int(values["value3"])-1]=state
            self.commands.append({"at":self.now().isoformat(),"device":values["value2"],
                "channel":int(values["value3"]),"state":state,"execution_id":current_duty().get("execution_id")})
            return Response()
        self.transport=Transport(token_store=self.tokens,environ=self.source,http_open=command)
        self.readback=lambda **kwargs: self.transport._snapshot("100204e9bc",1, routine_read=kwargs.get("routine_read",False))

    def now(self):return self.client.backend.now
    def power(self):
        return {"battery_soc_pct":90,"solar_power_w":3000,"load_power_w":100,
            "grid_power_w":0,"observed_at":self.now().isoformat()}

    def canonical(self,action,payload):
        if action=="load_active_auxiliaries":return deepcopy(list(self.aux.values()))
        if action=="load_active_auxiliary":return deepcopy(self.aux.get(payload))
        if action=="load_active_borehole":return deepcopy(self.borehole)
        if action in {"dispatch_auxiliary_on_edge","dispatch_borehole_on_edge","dispatch_borehole_off_edge"}:
            return {**payload["dispatch"](),"provider_command_attempted":True}
        if action in {"claim_auxiliary_before_on","mark_auxiliary_active"}:
            self.aux[payload["auxiliary_device_id"]]=deepcopy(payload)
        from modules.telemetry.rootline_irrigation_execution_store import _terminal_closes_active
        if _terminal_closes_active({**payload,"action":action}, auxiliary=True) if isinstance(payload,dict) else False:
            self.aux.pop(payload["auxiliary_device_id"],None)
        if action in {"claim_borehole_before_on","mark_borehole_active"}:self.borehole=deepcopy(payload)
        if action=="record_borehole_completed":self.borehole=None
        if action=="record_completed":self.parent_finished=True
        if action in {"load_auxiliary_off_attempts","load_borehole_off_attempts"}:return []
        if action=="load_auxiliary_containment":
            held=next((row for row in reversed(self.rows) if row.get("action")=="contain_auxiliary_device"
                and row.get("auxiliary_device_id")==payload),None)
            return {"contained":True,"evidence":held} if held else None
        if action=="load_auxiliary_physical_outcome":return None
        if action.startswith("load_"):return self.store(action,payload)
        self.rows.append({**deepcopy(payload),"action":action})
        return self.store(action,payload)

    def evidence(self,**_):
        from tests.test_rootline_scheduled_planner import payload
        from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context,ZA_TZ
        from modules.telemetry.rootline_auxiliary_management import build_fertilizer_batch_lifecycle, mixing_daily_accounting
        now=self.now();_,advisor=payload(now)
        for row in advisor["zones"]:
            if row["zone_id"]!="B12345" or self.parent_finished:
                row.update(visible_need="none",visible_need_observed_at=now.isoformat(),visible_need_source="owner")
        batch=build_fertilizer_batch_lifecycle(now=now)
        context=_active_irrigation_context(self.store.active,self.rows,True,batch["batch_generation"])
        if context:
            context.update(premix_verified=mixing_daily_accounting(self.rows,now=now,batch=batch)["premix_verified"],
                explicit_owner_time_programme=True,
                controller_sequence_completed=any(row.get("action")=="record_fertilizer_sequence_completed"
                    and row.get("completed") is True and row.get("zone_execution_id")==context["zone_execution_id"]
                    for row in self.rows),
                fertilizer_history_complete_through=now.isoformat())
        value={"power":self.power(),"weather":{"observed_at":now.isoformat(),"status":"fresh","rain_rate_mm_h":0},
            "irrigation":{"source":"rootline_daily_advisor","advisor_generated_at":now.isoformat(),
                "advisor_operating_date":now.astimezone(ZA_TZ).date().isoformat(),"zones":advisor["zones"],
                "adaptive_management":{"enabled":True,"zones":[{"zone_id":z["zone_id"]} for z in advisor["zones"]]}},
            "irrigation_history":{"status":"Available","zones":{z["zone_id"]:{"planning_epoch_start":self.start.isoformat(),
                "epoch_complete_through":now.isoformat(),"complete_through":now.isoformat(),"events":[]} for z in advisor["zones"]}},
            "fertilizer_executions":self.rows,"fertilizer_history_complete_through":now.isoformat(),
            "active_irrigation_context":context}
        return value,now.astimezone(ZA_TZ).date().isoformat(),now

    def tick(self,minute,*,parent=True,allow_borehole=False):
        from modules.telemetry import rootline_execution_runtime as runtime
        self.client.backend.now=max(self.now(),self.start+timedelta(minutes=minute))
        def admission(_):
            if not parent:return
            return runtime.run_rootline_execution_cycle(notify=lambda *_:{"provider_delivery_confirmed":True},
                environ=self.source,now=self.now(),clock=self.now,store=self.canonical,token_store=self.tokens,
                transport=self.transport,evidence_loader=self.evidence,readback=self.readback,
                owner_user_id="42",chat_id="42",observation_store=lambda *_:{"success":True,"created":True},
                authority_checker=lambda *_:True,active_weather_reader=lambda **_:self.weather() if self.weather else {})
        return runtime.run_rootline_managed_device_reassessment(environ=self.source,now=self.now(),clock=self.now,
            token_store=self.tokens,transport=self.transport,store=self.canonical,evidence_loader=self.evidence,
            after_safety=admission,allow_borehole_starts=allow_borehole)


@pytest.mark.parametrize("workers",[1,2])
def test_actual_managed_two_hour_parent_four_pulses(monkeypatch,workers):
    journey=MinuteJourney(monkeypatch)
    journey.source["ROOTLINE_BOREHOLE_ENABLED"]="false"
    for minute in range(12):
        journey.tick(minute,parent=False)
    journey.source["ROOTLINE_FERTILIZER_MIXING_ENABLED"]="false"
    for minute in range(12,134):
        for worker in range(workers):
            result=journey.tick(minute)
    parent=[row for row in journey.commands if row["device"]=="100204e9bc"]
    injection=[row for row in journey.commands if row["device"]=="100204d497" and row["channel"]==1]
    assert [row["state"] for row in parent]==["on","off"], (result,journey.commands)
    assert [row["state"] for row in injection]==["on","off"]*4, (result,journey.commands)
    assert journey.parent_finished
    from collections import Counter
    print("ACTUAL_MANAGED_TRACE",workers,len(journey.reads),
        dict(Counter(row["execution_id"] or "preclaim" for row in journey.reads)),
        dict(Counter(row["optional"] or "mandatory" for row in journey.reads)),journey.commands,
        "max_recent_plus_reserved",max(row["recent"]+row["remaining"] for row in journey.admissions))


@pytest.mark.parametrize("hours",[4,10])
def test_actual_managed_borehole_minutes(monkeypatch,hours):
    from modules.telemetry import rootline_borehole_commissioning as borehole
    journey=MinuteJourney(monkeypatch,borehole_seconds=hours*3600)
    journey.source.update(ROOTLINE_AUTONOMOUS_BC_ENABLED="false",ROOTLINE_FERTILIZER_MIXING_ENABLED="false",
        ROOTLINE_FERTILIZER_INJECTION_ENABLED="false")
    if hours==4:
        result=journey.tick(0,parent=False,allow_borehole=True)
    else:
        # The automatic caller deliberately caps a new request at four hours.
        # Exercise its existing typed outer ten-hour limit, then minute entry.
        provider=journey.transport.read_output_state(device_id="1002851416",channel=1)
        artifact=borehole.build_borehole_runtime_eligibility(need={"eligible":True},baseline=journey.baseline,
            authority={"inside_standing_authority":True},provider=provider,interlocks={},energy={"eligible":True},
            requested_seconds=36000,now=journey.now())
        result=borehole.advance_borehole_execution(eligibility=artifact,store=journey.canonical,
            transport=journey.transport,now=journey.now(),clock=journey.now)
    assert journey.borehole is not None,(result,journey.commands)
    for minute in range(1,hours*60+2):
        for worker in range(2):journey.tick(minute,parent=False)
    assert journey.borehole is None
    assert [row["state"] for row in journey.commands]==["on","off"],journey.commands
    from collections import Counter
    print("ACTUAL_BOREHOLE_TRACE",hours,len(journey.reads),
        dict(Counter(row["optional"] or "mandatory" for row in journey.reads)),
        "max_recent_plus_reserved",max(row["recent"]+row["remaining"] for row in journey.admissions))


def test_actual_combined_near_deadline_contains_without_completion_credit(monkeypatch):
    journey=MinuteJourney(monkeypatch)
    journey.tick(0,parent=False,allow_borehole=True)
    for minute in range(1,243):
        for worker in range(2):journey.tick(minute)
    assert journey.parent_finished and journey.borehole is None and not journey.aux
    from collections import Counter
    counts=Counter((row["device"],row["channel"],row["state"]) for row in journey.commands)
    assert counts[("100204e9bc",1,"on")]==counts[("100204e9bc",1,"off")]==1
    assert counts[("100204d497",1,"on")]==counts[("100204d497",1,"off")]==1
    held=[row for row in journey.rows if row.get("action")=="contain_auxiliary_device"]
    assert len(held)==1 and held[0]["shutdown_verified"] is True
    assert not any(row.get("action")=="record_auxiliary_completed" and row.get("auxiliary_device_id")=="FERTILIZER-INJECTION-CH1" for row in journey.rows)
    assert counts[("100204d497",2,"on")]==counts[("100204d497",2,"off")]==3
    assert counts[("1002851416",1,"on")]==counts[("1002851416",1,"off")]==1
    assert sum(row["optional"]=="borehole_routine" for row in journey.reads)==14
    assert max(row["recent"]+row["remaining"] for row in journey.admissions)<=250
    print("ACTUAL_COMBINED_TRACE",len(journey.reads),dict(counts),
        "charged_by_execution",dict(Counter(row.get("execution_id") or "preclaim"
            for row in journey.admissions if row["action"]=="request_attempt_reserved")),
        "optional",dict(Counter(row["optional"] or "mandatory" for row in journey.reads)),
        "max_recent_plus_reserved",max(row["recent"]+row["remaining"] for row in journey.admissions))


@pytest.mark.parametrize("case",["manual_off","unknown","rain","slow_deadline"])
def test_actual_parent_safety_and_original_deadline(monkeypatch,case):
    journey=MinuteJourney(monkeypatch)
    journey.source.update(ROOTLINE_BOREHOLE_ENABLED="false",ROOTLINE_FERTILIZER_MIXING_ENABLED="false",
        ROOTLINE_FERTILIZER_INJECTION_ENABLED="false")
    journey.tick(0)
    original=journey.store.active["primary_stop_deadline"]
    if case=="manual_off":
        journey.outputs["100204e9bc"][0]="off"
        journey.tick(1)
        assert journey.store.active is not None  # Not a fabricated fresh observation.
        journey.tick(16)
        assert journey.parent_finished and len(journey.commands)==1
    elif case=="unknown":
        journey.outputs["100204e9bc"][0]="unknown"
        journey.tick(16)
        assert journey.store.active["primary_stop_deadline"]==original
        assert len(journey.commands)==1
        journey.tick(121)
        assert journey.parent_finished and journey.commands[-1]["state"]=="off"
    elif case=="rain":
        from tests.test_rootline_active_weather_stop import weather_packet
        journey.weather=lambda:weather_packet(now=journey.now(),rain=1)
        journey.tick(1)
        assert journey.parent_finished and journey.commands[-1]["state"]=="off"
        assert not any(row["optional"]=="irrigation_routine" for row in journey.reads)
    else:
        journey.delay_once=15
        journey.client.backend.now=datetime.fromisoformat(original)-timedelta(seconds=1)
        journey.tick(119)
        assert journey.parent_finished and journey.commands[-1]["state"]=="off"
    terminal=next(row for row in journey.rows if row["action"]=="record_completed")
    assert terminal["primary_stop_deadline"]==original
    assert sum(row["state"]=="on" for row in journey.commands)==1


def test_actual_active_injector_parent_proof_bypasses_optional_gate(monkeypatch):
    journey=MinuteJourney(monkeypatch)
    journey.source["ROOTLINE_BOREHOLE_ENABLED"]="false"
    for minute in range(12):journey.tick(minute,parent=False)
    journey.source["ROOTLINE_FERTILIZER_MIXING_ENABLED"]="false"
    for minute in range(12,24):journey.tick(minute)
    assert "FERTILIZER-INJECTION-CH1" in journey.aux
    before=len(journey.reads)
    journey.outputs["100204e9bc"][0]="off"
    journey.tick(24)
    assert any(row["device"]=="100204d497" and row["channel"]==1 and row["state"]=="off"
        for row in journey.commands)
    assert any(row["device"]=="100204e9bc" and row["optional"] is None for row in journey.reads[before:])


def test_actual_failed_preparation_defers_without_retaining_positive_parent(monkeypatch):
    journey=MinuteJourney(monkeypatch)
    journey.source["ROOTLINE_BOREHOLE_ENABLED"]="false"
    for minute in range(12):journey.tick(minute,parent=False)
    journey.source["ROOTLINE_FERTILIZER_MIXING_ENABLED"]="false"
    journey.tick(12)
    original=journey.store.active["primary_stop_deadline"]
    journey.outputs["100204e9bc"][0]="unknown"
    journey.tick(23)
    before=len(journey.reads)
    journey.outputs["100204e9bc"][0]="on"
    journey.tick(24)
    assert len(journey.reads)==before
    assert not any(row["device"]=="100204d497" and row["channel"]==1 for row in journey.commands)
    assert journey.store.active["primary_stop_deadline"]==original
    journey.tick(29)
    assert any(row["device"]=="100204d497" and row["channel"]==1 and row["state"]=="on"
        for row in journey.commands)


def test_actual_last_pulse_opportunity_rechecks_after_slow_preparation(monkeypatch):
    journey=MinuteJourney(monkeypatch)
    journey.source["ROOTLINE_BOREHOLE_ENABLED"]="false"
    for minute in range(12):journey.tick(minute,parent=False)
    journey.source["ROOTLINE_FERTILIZER_MIXING_ENABLED"]="false"
    journey.tick(12)
    context=journey.evidence()[0]["active_irrigation_context"]
    started=datetime.fromisoformat(context["zone_start_evidence"]["observed_at"])
    original=journey.store.active["primary_stop_deadline"]
    journey.client.backend.now=started+timedelta(minutes=36)-timedelta(seconds=1)
    read=journey.transport.read_output_state
    def slow(**kwargs):
        value=read(**kwargs)
        if (budget._optional_observation.get() or {}).get("purpose")=="pulse_preparation":
            journey.client.backend.advance(5)
        return value
    monkeypatch.setattr(journey.transport,"read_output_state",slow)
    journey.tick(47)
    assert not any(row["device"]=="100204d497" and row["channel"]==1 for row in journey.commands)
    assert journey.store.active["primary_stop_deadline"]==original
