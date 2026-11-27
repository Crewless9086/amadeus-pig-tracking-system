"""Costed, offline scheduler -> gateway -> managed -> coordinator replay.

The captured parent/history are evidence fixtures. Premix, route replies and
latencies here are explicitly hypothetical; no live eligibility is asserted.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial

import pytest

from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry.rootline_execution_runtime import supervise_rootline_owned_injector, supervise_rootline_active_execution
from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
from modules.telemetry.rootline_command_acceptance import digest, program_completed, injector_target_timing
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_active_supervision import ScheduleStore, ENV as GATEWAY_ENV, HEADERS, payload, reports
from tests.test_rootline_command_mode import ENV, Store, Transport, receipt
from tests.test_rootline_auxiliary_shutdown_history import CAPTURE, history


class Rig:
    def __init__(self, monkeypatch, *, phase=0, database_cost=1, preparation_cost=3, receipt_cost=2):
        self.now = datetime.fromisoformat(CAPTURE["observed_at"]).replace(second=phase, microsecond=0)
        self.monotonic = 1000.0
        self.database_cost = database_cost
        self.preparation_cost = preparation_cost
        self.receipt_cost = receipt_cost
        self.trace = []
        self.commands = []
        self.waits = []
        self.schedules = ScheduleStore()
        self.phase = phase
        monkeypatch.setattr("time.monotonic", lambda: self.monotonic)
        monkeypatch.setattr(managed, "monotonic", lambda: self.monotonic)
        monkeypatch.setattr(managed, "canonical_timed_authority", lambda *args, **kwargs: True)
        rig = self

        class CostedStore(Store):
            def __call__(self, action, body):
                rig.advance(rig.database_cost)
                rig.trace.append((action, rig.now.isoformat()))
                if action == "load_active_auxiliaries":
                    return deepcopy(list(self.auxiliary.values()))
                if action == "claim_auxiliary_before_on" and any(
                        row.get("action") == action and row.get("consumption_key") == body.get("consumption_key")
                        for row in self.rows):
                    return {"success": True, "created": False}
                return super().__call__(action, body)

        class CostedTransport(Transport):
            def set_state(self, **kwargs):
                rig.advance(rig.preparation_cost)
                attempted = rig.now
                value = super().set_state(**kwargs)
                rig.commands.append({**kwargs, "attempted_at": attempted.isoformat()})
                rig.advance(rig.receipt_cost)
                if value.get("accepted_unambiguous"):
                    value["accepted_at"] = rig.now.isoformat()
                    value["receipt_sha256"] = digest({k:v for k,v in value.items() if k != "receipt_sha256"})
                return value

        self.store = CostedStore()
        self.store.rows = history()
        self.store.active = deepcopy(CAPTURE["active_irrigation_context"]["command_parent_execution"])
        self.transport = CostedTransport(self.store, lambda: self.now)
        self.env = {**GATEWAY_ENV, **ENV, "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"}

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.monotonic += seconds

    def wait(self, seconds):
        self.waits.append(seconds)
        self.advance(seconds)

    def evidence(self, **kwargs):
        # Measured production B admission took 71 seconds. This deliberately
        # costs the offline managed evidence path, rather than pretending it
        # is zero-latency or claiming B cost is a measured injector cost.
        from modules.telemetry.rootline_cycle_budget import remaining_seconds
        self.trace.append(("optional_evidence", self.now.isoformat()))
        remaining_seconds(minimum=50)
        self.advance(50)
        context = _active_irrigation_context(self.store.active, self.store.rows, True, "OFFLINE-BATCH", now=self.now)
        context.update(premix_command_accepted=True, fertilizer_history_complete_through=self.now.isoformat())
        context["zone_output_evidence"] = self.transport.read_output_state(device_id="100204e9bc", channel=1)
        return {"irrigation_auxiliary_tasks": [{"auxiliary_device_id": "FERTILIZER-INJECTION-CH1",
            "device_type": "fertilizer_injection_valve", "decision": "Run now"}],
            "auxiliary_contexts": {"FERTILIZER-INJECTION-CH1": context},
            "auxiliary_safety": {"FERTILIZER-INJECTION-CH1": self.transport.read_safety_configuration(device_id="100204d497", channel=1)}}

    def managed_cycle(self, **kwargs):
        self.trace.append(("managed_safety_entry", self.now.isoformat()))
        with timed_control_scope(self.env):
            return managed.run_rootline_managed_device_cycle(evidence={}, evidence_factory=self.evidence,
                transport=self.transport, store=self.store, environ=self.env, clock=lambda: self.now,
                now=self.now, deadline_wait=self.wait, connect_factory=lambda: None,
                after_safety=kwargs.get("after_safety"), refresh_after_safety=kwargs.get("refresh_after_safety", True),
                allow_new_starts=kwargs.get("allow_new_starts", True),
                allow_borehole_starts=kwargs.get("allow_borehole_starts"),
                canonical_loader=lambda _: {"device_record": {"commissioning_stage": "standing_active",
                    "standing_authority": True, "device_id": "100204d497", "channel": 1,
                    "device_type": "flow_dependent_injection_valve"}})

    def cycle(self, *, requested_at=None):
        current = requested_at or self.now
        request = payload(due_at=current.isoformat(), evidence_cutoff=current.isoformat(),
            trigger_timestamp=current.isoformat())
        def short(**kwargs):
            self.trace.append(("priority_entry", self.now.isoformat()))
            return supervise_rootline_owned_injector(environ=self.env, store=self.store,
                transport=self.transport, clock=lambda: self.now, deadline_wait=self.wait)
        def parent(**kwargs):
            self.trace.append(("parent_entry", self.now.isoformat()))
            return supervise_rootline_active_execution(**kwargs, store=self.store, transport=self.transport,
                token_store=object(), clock=lambda: self.now, active_weather_reader=lambda *a, **k: {})
        def reports_unavailable(*args, **kwargs):
            self.trace.append(("optional_report", self.now.isoformat()))
            raise TimeoutError("offline report failure")
        def family_unavailable(*args, **kwargs):
            self.trace.append(("family_delivery", self.now.isoformat()))
            raise TimeoutError("offline family delivery failure")
        return handle_rootline_reassessment_trigger(request, HEADERS, self.env,
            scheduler_now=current, schedule_store=self.schedules,
            supervision_clock=lambda:self.now, parent_deadline_store=self.store, parent_deadline_wait=self.wait,
            state_store=lambda *args: {"success": True, "created": True},
            short_auxiliary_supervision_cycle=short, active_supervision_cycle=parent,
            managed_device_cycle=self.managed_cycle,
            specialist_loader=reports_unavailable, daily_plan_generator=reports_unavailable,
            family_delivery=family_unavailable, equipment_notification_cycle=lambda **kwargs: {"success": True})


@pytest.mark.parametrize("phase", [0, 1, 15, 30, 45, 59])
def test_costed_two_normal_minutes_keep_original_duty_and_expose_off_preparation_latency(monkeypatch, reports, phase):
    rig = Rig(monkeypatch, phase=phase)
    first, _ = rig.cycle()
    assert first.get("short_auxiliary_duty_owned") is True, first
    assert [r["state"] for r in rig.commands] == ["ON"]
    assert not rig.waits and not any(row[0] == "optional_report" for row in rig.trace)
    original = deepcopy(rig.store.auxiliary["FERTILIZER-INJECTION-CH1"])
    deadline = datetime.fromisoformat(original["injector_target"]["target_off_at"])
    next_minute = rig.now.replace(second=0, microsecond=0)+timedelta(minutes=1)
    rig.advance((next_minute-rig.now).total_seconds())
    boundary = len(rig.trace)
    second_start = rig.now
    second, _ = rig.cycle()
    assert (rig.now-second_start).total_seconds() < 140
    assert not any(name in {"optional_report", "optional_evidence"} for name, _ in rig.trace[boundary:])
    assert any(name == "managed_safety_entry" for name, _ in rig.trace[boundary:])
    assert second["plan_delivery_status"] == "short_duty_reporting_deferred"
    saved = list(rig.schedules.rows.values())[-1]
    assert saved["plan_delivery_status"] == "short_duty_reporting_deferred"
    assert saved["supervision_next_due_at"] and saved["next_due_at"]
    assert [r["state"] for r in rig.commands] == ["ON", "OFF"]
    assert rig.trace[boundary][0] == "priority_entry"
    parent_at = next(datetime.fromisoformat(at) for name, at in rig.trace[boundary:] if name == "parent_entry")
    off_at = datetime.fromisoformat(rig.commands[-1]["attempted_at"])
    assert off_at < parent_at
    assert off_at > deadline  # Delivery/setup delay is measured, never hidden.
    terminal = next(row for row in reversed(rig.store.rows) if row["action"] == "record_auxiliary_completed")
    assert terminal["primary_stop_deadline"] == original["primary_stop_deadline"]
    assert terminal["command_duty_closed"] is True
    assert terminal["command_program_completed"] is True and program_completed(terminal)
    timing = injector_target_timing(terminal)
    assert timing["on_delivery_delay_seconds"] == rig.receipt_cost
    assert timing["off_request_delay_seconds"] == (off_at-deadline).total_seconds()
    assert timing["off_delivery_delay_seconds"] == rig.receipt_cost
    assert timing["physical_runtime_verified"] is False


@pytest.mark.parametrize("failure", ["missed_tick", "parent_off", "uncertain_off", "replay"])
def test_two_cycle_failure_or_duplicate_retains_truth_and_never_repeats_on(monkeypatch, reports, failure):
    rig = Rig(monkeypatch)
    first_at = rig.now
    first, _ = rig.cycle()
    assert first["short_auxiliary_duty_owned"]
    original = deepcopy(rig.store.auxiliary["FERTILIZER-INJECTION-CH1"])
    if failure == "replay":
        replay, _ = rig.cycle(requested_at=first_at)
        assert replay["status"] == "scheduled_reassessment_replayed_noop"
        assert [r["state"] for r in rig.commands] == ["ON"]
        assert rig.store.auxiliary["FERTILIZER-INJECTION-CH1"] == original
        return
    if failure == "missed_tick":
        rig.advance(180)
    else:
        next_tick = rig.now.replace(second=0, microsecond=0)+timedelta(minutes=1)
        rig.advance((next_tick-rig.now).total_seconds())
    if failure == "parent_off":
        rig.store.active = None
    if failure == "uncertain_off":
        rig.transport.reject_off = True
    rig.cycle()
    assert sum(r["state"] == "ON" for r in rig.commands) == 1
    terminals = [r for r in rig.store.rows if r["action"] == "record_auxiliary_completed"
        and r.get("execution_id") == original["execution_id"]]
    if failure == "uncertain_off":
        assert not terminals
        assert rig.store.auxiliary["FERTILIZER-INJECTION-CH1"]["primary_stop_deadline"] == original["primary_stop_deadline"]
    else:
        assert len(terminals) == 1 and terminals[0]["command_duty_closed"]
        assert terminals[0]["command_program_completed"] is (failure == "missed_tick")


@pytest.mark.parametrize("competing", ["mixer_due", "parent_due", "parent_lost"])
def test_short_duty_deferral_retains_other_owned_shutdowns(monkeypatch, reports, competing):
    rig = Rig(monkeypatch)
    rig.cycle()
    next_tick = rig.now.replace(second=0, microsecond=0)+timedelta(minutes=1)
    rig.advance((next_tick-rig.now).total_seconds())
    if competing == "mixer_due":
        claimed = rig.now-timedelta(seconds=601)
        mixer = {"execution_id": "OFFLINE-DUE-MIXER", "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
            "device_id": "100204d497", "channel": 2, "device_type": "fertilizer_mixer",
            "state": "Active", "stop_mode": "scheduled", "acceptance_mode": "command_accepted",
            "on_attempts": 1, "maximum_duration_seconds": 600, "claimed_at": claimed.isoformat(),
            "primary_stop_deadline": (claimed+timedelta(seconds=600)).isoformat()}
        mixer["command_on_receipt"] = receipt(mixer, "ON", at=claimed)
        rig.store.auxiliary[mixer["auxiliary_device_id"]] = deepcopy(mixer)
        rig.store.rows.append({**deepcopy(mixer), "action": "claim_auxiliary_before_on"})
    elif competing == "parent_due":
        # A malformed/expired parent deadline still owes conservative OFF.
        rig.store.active["primary_stop_deadline"] = (rig.now-timedelta(seconds=1)).isoformat()
    else:
        rig.store.active = None
    boundary = len(rig.trace)
    result, _ = rig.cycle()
    assert result["short_auxiliary_optional_deferred"] is True
    assert not any(name in {"optional_report", "optional_evidence"} for name, _ in rig.trace[boundary:])
    assert any(name == "parent_entry" for name, _ in rig.trace[boundary:])
    assert any(name == "managed_safety_entry" for name, _ in rig.trace[boundary:])
    assert sum(row["state"] == "ON" for row in rig.commands) == 1
    assert any(row["state"] == "OFF" and row["device_id"] == "100204d497"
        and row["channel"] == 1 for row in rig.commands)
    if competing == "mixer_due":
        assert any(row["state"] == "OFF" and row["channel"] == 2 for row in rig.commands)
    if competing == "parent_due":
        assert any(row["state"] == "OFF" and row["device_id"] == "100204e9bc" for row in rig.commands)


def test_deferred_optional_work_is_available_on_next_normal_cycle(monkeypatch, reports):
    rig = Rig(monkeypatch, phase=15)
    rig.cycle()
    for cycle in (2, 3):
        tick = rig.now.replace(second=0, microsecond=0)+timedelta(minutes=1)
        rig.advance((tick-rig.now).total_seconds())
        boundary = len(rig.trace)
        rig.cycle()
        assert any(name == "optional_evidence" for name, _ in rig.trace[boundary:]) is (cycle == 3)
    assert sum(row["state"] == "ON" for row in rig.commands) == 1



def test_short_duty_deferral_runs_real_managed_grid_reconciliation(monkeypatch, reports):
    from modules.telemetry.rootline_execution_runtime import run_rootline_managed_device_reassessment
    from tests.test_rootline_eskom_runtime import CONFIG, canonical
    rig = Rig(monkeypatch, phase=15)
    from modules.telemetry.rootline_owner_controls import project_owner_controls
    monkeypatch.setattr("modules.telemetry.rootline_owner_controls.load_runtime_owner_controls",
        lambda *args, **kwargs: project_owner_controls([], now=kwargs.get("now") or rig.now))
    rig.cycle()
    tick = rig.now.replace(second=0, microsecond=0)+timedelta(minutes=1)
    rig.advance((tick-rig.now).total_seconds())
    rig.env.update(CONFIG)
    events = [
        {"action": "claim_eskom_before_command", "execution_id": "OFFLINE-PENDING-GRID", "desired_state": "ON"},
        {"action": "record_eskom_command_outcome", "execution_id": "OFFLINE-PENDING-GRID"}]
    def store(action, body):
        if action == "load_eskom_events":
            rig.trace.append(("grid_pending_read", rig.now.isoformat()))
            return deepcopy(events)
        if action == "record_eskom_completed":
            events.append({**body, "action": action})
            return {"success": True, "created": True}
        return rig.store(action, body)
    monkeypatch.setattr("modules.telemetry.rootline_device_spine.load_device_record", lambda *a, **k: canonical())
    monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state", lambda **k: (
        {"success": True, "source": {"last_reading_at": rig.now.isoformat()}, "current": {
            "battery_soc_pct": 29, "solar_power_w": 0, "load_power_w": 1000,
            "grid_power_w": 0, "battery_power_w": 1000, "battery_state": "discharging"}}, 200))
    monkeypatch.setattr("modules.telemetry.rootline_eskom_runtime.read_eskom_switch", lambda **k: {
        "authoritative": True, "device_id": CONFIG["ROOTLINE_ESKOM_DEVICE_ID"], "online": True,
        "switch_code": "switch_1", "state": "ON", "retrieved_at": rig.now.isoformat(), "evidence_id": "offline-grid"})
    def managed_cycle(**kwargs):
        assert kwargs["allow_new_starts"] is False and kwargs["allow_borehole_starts"] is False
        return run_rootline_managed_device_reassessment(**kwargs, store=store,
            token_store=object(), transport=rig.transport, clock=lambda: rig.now,
            evidence_loader=lambda **k: pytest.fail("Optional evidence must be deferred"))
    rig.managed_cycle = managed_cycle
    result, _ = rig.cycle()
    assert result["managed_device_result"]["eskom"]["status"] == "eskom_command_reconciled"
    assert events[-1]["action"] == "record_eskom_completed"
    assert sum(row["state"] == "ON" for row in rig.commands) == 1


@pytest.mark.parametrize("failure", ["on_record_rejected", "on_record_exception", "activation_rejected", "activation_exception", "late_activation_ack"])
def test_start_persistence_failure_contains_without_handoff_or_on_retry(monkeypatch,reports,failure):
    rig=Rig(monkeypatch)
    original=rig.store
    def store(action,body):
        if action=="record_auxiliary_on_outcome" and failure.startswith("on_record"):
            if failure.endswith("exception"): raise RuntimeError("offline outcome persistence failure")
            return {"success":False}
        if action=="mark_auxiliary_active" and failure.startswith("activation"):
            if failure.endswith("exception"): raise RuntimeError("offline activation failure")
            return {"success":False}
        value=original(action,body)
        if action=="mark_auxiliary_active" and failure=="late_activation_ack": rig.advance(130)
        return value
    class Proxy:
        def __call__(self,action,body): return store(action,body)
        def __getattr__(self,name): return getattr(original,name)
    rig.store=Proxy()
    result,_=rig.cycle()
    assert result.get("short_auxiliary_duty_owned") is not True
    assert [row["state"] for row in rig.commands]==["ON","OFF"]
    terminals=[r for r in original.rows if r["action"]=="record_auxiliary_completed" and r.get("auxiliary_device_id")=="FERTILIZER-INJECTION-CH1"]
    assert len(terminals)==1 and not terminals[0]["command_program_completed"]
    assert not program_completed(terminals[0])


def test_parent_disappearing_during_wait_cannot_receive_full_programme(monkeypatch,reports):
    rig=Rig(monkeypatch);rig.cycle()
    next_tick=rig.now.replace(second=0,microsecond=0)+timedelta(minutes=1)
    rig.advance((next_tick-rig.now).total_seconds())
    wait=rig.wait
    def interrupted(seconds):
        wait(seconds);rig.store.active=None
    rig.wait=interrupted
    rig.cycle()
    terminal=next(r for r in reversed(rig.store.rows) if r["action"]=="record_auxiliary_completed")
    assert terminal["reason"]=="irrigation_parent_lost"
    assert not terminal["command_program_completed"] and not program_completed(terminal)
    assert [r["state"] for r in rig.commands]==["ON","OFF"]


@pytest.mark.parametrize("manual",["parent","injector"])
def test_explicit_manual_stop_preempts_target_wait(monkeypatch,reports,manual):
    rig=Rig(monkeypatch);rig.cycle()
    tick=rig.now.replace(second=0,microsecond=0)+timedelta(minutes=1)
    rig.advance((tick-rig.now).total_seconds())
    if manual=="parent": rig.store.active["manual_off_active"]=True
    else: rig.store.auxiliary["FERTILIZER-INJECTION-CH1"]["manual_isolation_active"]=True
    rig.cycle()
    assert not rig.waits
    terminal=next(r for r in reversed(rig.store.rows) if r["action"]=="record_auxiliary_completed" and r.get("auxiliary_device_id")=="FERTILIZER-INJECTION-CH1")
    assert not terminal["command_program_completed"]
    assert terminal["reason"]==("irrigation_parent_lost" if manual=="parent" else "manual_isolation")


@pytest.mark.parametrize("phase",[0,15,45])
def test_real_ha_sender_and_canonical_fences_across_two_cycles(monkeypatch,reports,phase):
    # Keep the real coordinator, bound adapter, locked ON/OFF sender and HA
    # request guards. Only database wire I/O and authenticated client I/O are fake.
    from modules.telemetry import rootline_home_assistant as ha
    from modules.telemetry import rootline_ifttt_transport as adapter
    from modules.telemetry import rootline_irrigation_execution_store as canonical_store
    from tests.test_rootline_injector_target import Database
    from tests.test_rootline_home_assistant import fixture as ha_fixture
    import datetime as datetime_module
    rig=Rig(monkeypatch,phase=phase)
    d=Database(monkeypatch);d.rows=rig.store.rows
    parent=deepcopy(rig.store.active)
    d.parents=[{**parent,"action":"claim_before_on"},
        {**parent,"action":"record_on_outcome","on_outcome":parent["command_on_receipt"]},
        {**parent,"action":"mark_active"}]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return rig.now if tz else rig.now.replace(tzinfo=None)
    monkeypatch.setattr(datetime_module,"datetime",Clock)
    monkeypatch.setattr(adapter,"datetime",Clock)
    monkeypatch.setattr(ha,"datetime",Clock)
    calls=[]
    devices=[];entities=[];debug={"entities":[]}
    for identity in ("100204d497","100204e9bc"):
        ds,es,_=ha_fixture(identity)
        ds[0]["id"]="registry-"+identity
        for row in es:
            channel=int(row["entity_id"].rsplit("_",1)[1])
            row["device_id"]=ds[0]["id"];row["entity_id"]=f"switch.{identity}_{channel}"
            topic=f"cube2ha/switch/{identity}/toggle_{channel}/state"
            debug["entities"].append({"entity_id":row["entity_id"],"discovery_data":{"payload":{
                "unique_id":row["unique_id"],"platform":"switch","state_topic":topic,
                "command_topic":topic[:-5]+"set","availability_topic":f"cube2ha/{identity}/availability",
                "value_template":"{{ value_json.state }}","device":{"identifiers":identity,
                    "manufacturer":"SONOFF","model":"4CHPROR3"}}}})
        devices+=ds;entities+=es
    class Client:
        def __init__(self,environ): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def request(self,kind,**fields):
            calls.append((kind,deepcopy(fields)))
            if kind!="call_service": rig.advance(1)
            if kind=="config/device_registry/list": return deepcopy(devices)
            if kind=="config/entity_registry/list": return deepcopy(entities)
            if kind=="mqtt/device/debug_info": return deepcopy(debug)
            if kind=="call_service":
                rig.commands.append({"state":"ON" if fields["service"]=="turn_on" else "OFF",
                    "attempted_at":rig.now.isoformat(),"entity_id":fields["target"]["entity_id"]})
                rig.advance(2)
                return {"success":True}
            raise AssertionError(kind)
    read=ha.read_registered_device;send=ha.send_state
    monkeypatch.setattr(ha,"read_registered_device",lambda *a,**k:read(*a,**k,now=rig.now,client_factory=Client))
    monkeypatch.setattr(ha,"send_state",lambda **k:send(**k,client_factory=Client))
    rig.transport=adapter.RootlineIFTTTTransport(token_store=None,environ=rig.env)
    original=type(rig.store).__call__
    execute=d.execute
    def sql(statement,args=()):
        if "execution_id'=%s" in statement and "order by created_at,review_event_id" in statement:
            d.result=[(deepcopy(r),) for r in d.rows+d.parents if r.get("execution_id")==args[-1]]
            return d
        if statement.lstrip().startswith("select 1 from public.sam_live_stock_conversation_review_events claim"):
            assert args[1]==parent["execution_id"]
            d.result=[(1,)];return d
        return execute(statement,args)
    d.execute=sql
    def store(self,action,body):
        if action=="claim_auxiliary_before_on": d.body=deepcopy(body)
        if action in {"dispatch_auxiliary_on_edge","dispatch_auxiliary_off_edge","mark_auxiliary_active","record_auxiliary_completed"}:
            rig.advance(1);d.now=rig.now
            rig.trace.append((action,rig.now.isoformat()))
            if action=="dispatch_auxiliary_on_edge": return canonical_store._dispatch_auxiliary_on_edge(body)
            if action=="dispatch_auxiliary_off_edge": return canonical_store._dispatch_auxiliary_off_edge(body)
            result=canonical_store._guarded_managed_transition(action,body)
            if result.get("success"):
                if action=="mark_auxiliary_active": self.auxiliary[body["auxiliary_device_id"]]=deepcopy(result["execution"])
                else: self.auxiliary.pop(body["auxiliary_device_id"],None)
            return result
        return original(self,action,body)
    monkeypatch.setattr(type(rig.store),"__call__",store)
    first,_=rig.cycle()
    assert first.get("short_auxiliary_duty_owned") is True, __import__("json").dumps(first.get("managed_device_result"), default=str)
    assert [r["state"] for r in rig.commands]==["ON"]
    owned=deepcopy(rig.store.auxiliary["FERTILIZER-INJECTION-CH1"])
    from modules.telemetry.rootline_command_acceptance import injector_target_matches_rows
    assert injector_target_matches_rows(owned,d.rows)
    tick=rig.now.replace(second=0,microsecond=0)+timedelta(minutes=1);rig.advance((tick-rig.now).total_seconds())
    rig.cycle()
    assert [r["state"] for r in rig.commands]==["ON","OFF"]
    terminal=next(r for r in reversed(d.rows) if r["action"]=="record_auxiliary_completed" and r.get("auxiliary_device_id")=="FERTILIZER-INJECTION-CH1")
    assert terminal["command_program_completed"] and program_completed(terminal)
    assert terminal["command_on_receipt"]["entity_id"]=="switch.100204d497_1"
    assert terminal["command_off_receipt"]["entity_id"]=="switch.100204d497_1"
    assert injector_target_timing(terminal)["off_delivery_delay_seconds"]==2
    assert len([kind for kind,fields in calls if kind=="call_service"])==2
