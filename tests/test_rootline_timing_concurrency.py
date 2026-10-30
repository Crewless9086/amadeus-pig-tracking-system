"""Production-path regressions for minute control and independent device duties."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from zoneinfo import ZoneInfo

import pytest

from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment
from modules.telemetry.rootline_irrigation_history import _cross_midnight_continuation
from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
from modules.telemetry.rootline_ifttt_transport import active_auxiliary_output_owned
from modules.telemetry.rootline_device_registry import get_device_contract, commissioned_irrigation_contracts
from tests.test_rootline_execution_runtime import NOW, Store, Transport, evidence, controller, plan
from tests.test_rootline_active_supervision import gateway, ScheduleStore, payload
from tests.test_rootline_managed_recovery_planning import Store as RecoveryStore, OffOnlyTransport, active as due_active


def parent_material():
    value = build_execution_eligibility(plan=plan(), evidence=evidence(), controller=controller(), now=NOW)
    job = build_irrigation_job(zone_id="B12345", operating_date="2026-08-08",
        requested_total_seconds=7200, requested_total_minutes=120, maximum_segment_seconds=3599,
        expected_segment_count=2, plan_identity=value["plan_generation"])
    return value, job


def test_nonreport_tick_completes_then_starts_real_parent_segment_once(monkeypatch):
    first, job = parent_material()
    store = Store()
    claimed = NOW - timedelta(seconds=3600)
    active = {**first, "state":"Active", "device_id":"100204e9bc", "channel":1,
        "claimed_at":claimed.isoformat(), "primary_stop_deadline":(NOW-timedelta(seconds=1)).isoformat(),
        "native_fail_stop_deadline":(NOW-timedelta(seconds=1)).isoformat(),
        "planned_runtime_seconds":3599,"segment_number":1,"on_attempts":1,"off_attempts":0,
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"first-on",
            "retrieved_at":claimed.isoformat()}}
    store.active=active
    store.rows=[("record_eligibility",first),("claim_before_on",active),("mark_active",active)]
    class PhysicalTransport(Transport):
        state="ON"
        def set_state(self, **kwargs):
            self.state=kwargs["state"]
            return super().set_state(**kwargs)
        def read_output_state(self, **kwargs):
            return {"authoritative":True,"state":self.state,"evidence_id":"read-"+self.state,
                "retrieved_at":NOW.isoformat()}
    transport=PhysicalTransport()
    def current_plan(*args, **kwargs):
        value=plan(); value["evidence_generation"]="fresh-parent-handover"
        value["candidate_tasks"][0]["incomplete_parent_job"]={"job":job,
            "projection":{"status":"segment_ready","current_segment":2},"remaining_seconds":3599}
        return value
    monkeypatch.setattr(runtime,"build_water_energy_plan",current_plan)
    def execute(**kwargs):
        return runtime.run_rootline_execution_cycle(**kwargs, store=store,transport=transport,
            token_store=object(),clock=lambda:NOW,evidence_loader=lambda **k:(evidence(),"2026-08-08",NOW),
            readback=lambda **k:controller(),authority_checker=lambda *a:True)
    schedules=ScheduleStore();due=NOW+timedelta(minutes=30)
    schedules.rows["prior:outcome"]={"specialist":"ROOTLINE","status":"completed","next_due_at":due.isoformat()}
    def report_forbidden(*args,**kwargs): pytest.fail("control must not run report work")
    options=dict(schedules=schedules,scheduler_now=NOW,
        request_payload=payload(due_at=NOW.isoformat(),trigger_timestamp=NOW.isoformat(),
            evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat()),
        specialist_loader=report_forbidden,daily_plan_generator=report_forbidden,
        active_supervision_cycle=partial(runtime.supervise_rootline_active_execution,
            store=store,transport=transport,token_store=object()),execution_cycle=execute)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:gateway(store,transport,**options)[0],range(2)))
    assert [(r["channel"],r["state"]) for r in transport.calls]==[(1,"OFF"),(1,"ON")], results
    changed=next(r for r in results if r.get("hardware_commands"))
    assert changed["report_work_due"] is False and changed["execution_status"]=="segment_started"
    assert changed["active_supervision_status"]=="segment_completed"
    assert datetime.fromisoformat(changed["next_due_at"])==due
    assert store.active["job_id"]==job["job_id"] and store.active["current_segment"]==2
    assert store.active["cumulative_verified_runtime_seconds"]==3599
    assert sum(name=="claim_before_on" for name,_ in store.rows)==2
    replay=gateway(store,transport,**options)[0]
    assert replay["status"]=="scheduled_reassessment_replayed_noop" and len(transport.calls)==2


def test_continuation_has_priority_without_bypassing_rain_or_hold():
    first,job=parent_material(); base=plan()
    b=base["candidate_tasks"][0]; b["rank"]=99
    b["incomplete_parent_job"]={"job":job,"projection":{"status":"segment_ready"},"remaining_seconds":3599}
    c={**deepcopy(b),"task_id":"irrigation_C12345","rank":1};c.pop("incomplete_parent_job")
    base["candidate_tasks"].append(c)
    weather=evidence();weather["irrigation"]["zones"].append({"zone_id":"C12345","live_rain_release_proven":True})
    completion={"job_id":job["job_id"],"segment_number":1,"segment_identity":first["segment_identity"],
        "execution_id":first["execution_id"],"state":"Completed","verified_runtime_seconds":3599,"shutdown_verified":True}
    def build():return build_execution_eligibility(plan=base,evidence=weather,controller=controller(),now=NOW,
        job_event_reader=lambda identity:[completion] if identity==job["job_id"] else [])
    chosen=build();assert chosen["zone_id"]=="B12345" and chosen["current_segment"]==2
    weather["weather"]["rain_rate_mm_h"]=1
    assert build()["eligible"] is False
    weather["weather"]["rain_rate_mm_h"]=0;b["zone_decision"]="Hold"
    assert build()["zone_id"]=="C12345"


@pytest.mark.parametrize("completion,cutoff,expected",[
    ("2026-08-23T23:59:00+02:00","2026-08-24T00:01:00+02:00",True),
    ("2026-08-24T00:01:00+02:00","2026-08-24T00:16:00+02:00",True),
    ("2026-08-23T23:59:00+02:00","2026-08-24T00:30:00+02:00",False),
])
def test_midnight_continuation_keeps_bounded_elapsed_time(completion,cutoff,expected):
    assert _cross_midnight_continuation({"operating_date":"2026-08-23"},
        [{"completed_at":completion}],datetime.fromisoformat(cutoff),"2026-08-24") is expected


@pytest.mark.parametrize("failed,remaining",[("load_active_auxiliaries","1002851416"),
    ("load_active_borehole","100204d497")])
def test_inventory_failure_still_stops_independent_known_obligation(failed,remaining):
    from tests.test_rootline_managed_recovery_planning import NOW as at
    store=RecoveryStore("mixer",both=True,fail_action=failed);transport=OffOnlyTransport()
    result=run_rootline_managed_device_cycle(evidence={},store=store,transport=transport,
        allow_new_starts=False,now=at,clock=lambda:at)
    assert result["success"] is False
    assert [(row["device_id"],row["state"]) for row in transport.commands]==[(remaining,"OFF")]
    assert any(row.get("managed_device_recovery") for row in result["outcomes"])


@pytest.mark.parametrize("local",["2026-08-26T00:00:00+02:00","2026-08-26T00:05:00+02:00","2026-08-26T01:59:00+02:00"])
def test_managed_reader_derives_sast_operating_date(local):
    at=datetime.fromisoformat(local).astimezone(timezone.utc);seen=[]
    def loader(**kwargs):
        # Exercise the actual reader's documented SAST date derivation.
        selected=kwargs.get("operating_date") or kwargs["now"].astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
        seen.append(selected)
        return {},selected,kwargs["now"]
    runtime.run_rootline_managed_device_reassessment(environ={},now=at,clock=lambda:at,
        database_url="",store=RecoveryStore(),token_store=object(),transport=OffOnlyTransport(),evidence_loader=loader)
    assert seen==["2026-08-26"]


def test_sibling_ownership_rejects_unknown_stale_wrong_and_naive_evidence():
    contract=get_device_contract("FERTILIZER-MIXER-CH2")
    active={"execution_id":"mixer-owned","auxiliary_device_id":contract["identity"],
        "device_id":contract["device_id"],"channel":2,"state":"Active","on_attempts":1,
        "maximum_duration_seconds":600,"claimed_at":(NOW-timedelta(seconds=10)).isoformat(),
        "primary_stop_deadline":(NOW+timedelta(seconds=590)).isoformat(),
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"provider-on",
            "retrieved_at":(NOW-timedelta(seconds=9)).isoformat()}}
    assert active_auxiliary_output_owned(active,contract,NOW.isoformat())
    for changes in ({"state":"claimed"},{"channel":1},{"execution_id":""},
        {"primary_stop_deadline":NOW.isoformat()},{"claimed_at":NOW.replace(tzinfo=None).isoformat()},
        {"start_evidence":{"state":"ON"}}):
        assert not active_auxiliary_output_owned({**active,**changes},contract,NOW.isoformat())


def test_registry_flags_cannot_activate_uncommissioned_ae():
    selected=commissioned_irrigation_contracts(environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true",
        "ROOTLINE_A_ENABLED":"true","ROOTLINE_E_ENABLED":"true"})
    assert set(selected)=={"B12345","C12345"}
    assert commissioned_irrigation_contracts(environ={})=={}


@pytest.mark.parametrize("failed_channel",[None,1,2])
def test_all_three_due_devices_are_supervised_even_if_one_provider_raises(failed_channel):
    from tests.test_rootline_managed_recovery_planning import NOW as at
    class MultiStore(RecoveryStore):
        def __init__(self):
            super().__init__("mixer",both=True)
            injector=due_active("injector")
            injector.update(maximum_duration_seconds=120,claimed_at=(at-timedelta(seconds=121)).isoformat(),
                start_evidence={"authoritative":True,"state":"ON","evidence_id":"injector-on",
                    "retrieved_at":(at-timedelta(seconds=120)).isoformat()})
            self.auxiliaries={row["auxiliary_device_id"]:row for row in (due_active("mixer"),injector)}
        def __call__(self,action,payload):
            if action=="load_active_auxiliaries":return deepcopy(list(self.auxiliaries.values()))
            if action=="load_active_auxiliary":return deepcopy(self.auxiliaries.get(payload))
            identity=payload.get("auxiliary_device_id") if isinstance(payload,dict) else None
            value=super().__call__(action,payload)
            if identity and action in {"record_auxiliary_completed","record_auxiliary_control_pulse_stopped","contain_auxiliary_device"}:
                self.auxiliaries.pop(identity,None)
            return value
    class FailingTransport(OffOnlyTransport):
        def set_state(self,**kwargs):
            if kwargs["device_id"]=="100204d497" and kwargs["channel"]==failed_channel:
                self.commands.append(kwargs)
                raise TimeoutError("synthetic unknown OFF response")
            return super().set_state(**kwargs)
    store=MultiStore();transport=FailingTransport()
    result=run_rootline_managed_device_cycle(evidence={},store=store,transport=transport,
        allow_new_starts=False,now=at,clock=lambda:at,
        energy_reader=lambda:pytest.fail("due OFF must precede optional power reads"),
        borehole_safety_reader=lambda:pytest.fail("due OFF must precede optional fault reads"))
    assert {(row["device_id"],row["channel"]) for row in transport.commands}=={
        ("100204d497",1),("100204d497",2),("1002851416",1)}
    assert all(row["state"]=="OFF" for row in transport.commands)
    assert result["hardware_commands"]==3
    if failed_channel:
        assert result["success"] is False and result["effects_unknown"] is True
        failure=next(row for row in result["outcomes"] if row.get("error_type"))
        assert failure["error_type"]=="TimeoutError" and failure["hardware_commands"]==1
    else:assert result["success"] is True, [(row.get("status"),row.get("error_type")) for row in result["outcomes"]]


def test_unidentified_auxiliary_holds_irrigation_but_keeps_known_borehole_off():
    from tests.test_rootline_managed_recovery_planning import NOW as at
    store=RecoveryStore("mixer",both=True)
    store.aux["auxiliary_device_id"]="unidentified-output"
    transport=OffOnlyTransport()
    result=run_rootline_managed_device_cycle(evidence={},store=store,transport=transport,
        allow_new_starts=True,now=at,clock=lambda:at,
        environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED":"true","ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"},
        evidence_factory=lambda:pytest.fail("ambiguous auxiliary inventory cannot admit new auxiliary work"))
    assert result["success"] is False and result["blocks_bc"] is True
    assert [(row["device_id"],row["state"]) for row in transport.commands]==[("1002851416","OFF")]
