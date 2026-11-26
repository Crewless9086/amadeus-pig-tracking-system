"""Real canonical activation/loader and receipt boundaries, entirely offline."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_irrigation_execution_store as db
from tests.test_rootline_command_mode import receipt
from tests.test_rootline_auxiliary_shutdown_history import CAPTURE


def fixture():
    parent = deepcopy(CAPTURE["active_irrigation_context"]["command_parent_execution"])
    now = ca.moment(CAPTURE["observed_at"])
    claim = {"execution_id": "OFFLINE-TARGET", "auxiliary_device_id": "FERTILIZER-INJECTION-CH1",
        "device_type": "fertilizer_injection_valve", "device_id": "100204d497", "channel": 1,
        "acceptance_mode": ca.MODE, "stop_mode": "scheduled", "state": "claimed", "on_attempts": 0,
        "off_attempts": 0, "maximum_duration_seconds": 120, "claimed_at": now.isoformat(),
        "primary_stop_deadline": (now+timedelta(seconds=120)).isoformat(),
        "injector_timing_contract": ca.INJECTOR_TARGET_V1, "consumption_key": "OFFLINE-CONSUMPTION",
        "zone_execution_id": parent["execution_id"],
        **{k:parent[k] for k in ("zone_id", "job_id", "job_sha256", "segment_identity")}}
    on = receipt(claim, "ON", at=now+timedelta(seconds=4))
    on["accepted_at"] = (now+timedelta(seconds=9)).isoformat()
    on["receipt_sha256"] = ca.digest({k:v for k,v in on.items() if k != "receipt_sha256"})
    body = {**claim, "state":"Active", "on_attempts":1, "command_on_receipt":on}
    rows = [{**claim,"action":"claim_auxiliary_before_on"},
        {**claim,"action":"claim_auxiliary_dispatch"},
        {**claim,"action":"record_auxiliary_on_outcome", "on_outcome":on}]
    parents = [{**parent,"action":"claim_before_on"},
        {**parent,"action":"record_on_outcome","on_outcome":parent["command_on_receipt"]},
        {**parent,"action":"mark_active"}]
    return now, body, rows, parents


class Database:
    def __init__(self, monkeypatch):
        self.now, self.body, self.rows, self.parents = fixture()
        self.now += timedelta(seconds=10)
        self.clock_step = 0
        self.calls=[]; self.rowcount=0; self.result=[]; self.fail_commit=False
        monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres", self.connect)
        monkeypatch.setattr(db, "_load_connection", lambda action:self.connect())
    @contextmanager
    def connect(self, **kwargs):
        self.calls.append(("connect",kwargs))
        before = deepcopy(self.rows)
        try:
            yield self
            if self.fail_commit:
                raise RuntimeError("offline commit failure")
        except Exception:
            self.rows = before
            raise
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self, sql, args=()):
        self.calls.append((sql,args))
        if "clock_timestamp" in sql:
            self.result=[(self.now,)]
            self.now += timedelta(seconds=self.clock_step)
        elif "pg_advisory_xact_lock" in sql:
            self.result=[]
        elif "insert into" in sql:
            value=json.loads(args[-1])["rootline_execution"]
            self.rows.append(value); self.rowcount=1
        elif "order by created_at desc" in sql:
            self.result=[(deepcopy(r),) for r in reversed(self.rows)]
        elif "execution_id'=%s" in sql:
            selected=self.rows if args[-1]==self.body["execution_id"] else self.parents
            self.result=[(deepcopy(r),) for r in selected]
        else: raise AssertionError(sql)
    def fetchone(self): return self.result[0] if self.result else None
    def fetchall(self): return self.result
    def activate(self): return db._guarded_managed_transition("mark_auxiliary_active",deepcopy(self.body))


def test_locked_activation_restart_replay_and_original_deadline(monkeypatch):
    database=Database(monkeypatch)
    result=database.activate(); active=result["execution"]
    assert result["success"] and result["created"]
    assert active["primary_stop_deadline"]==database.body["primary_stop_deadline"]
    assert ca.command_stop_deadline(active)==ca.moment(database.body["command_on_receipt"]["accepted_at"])+timedelta(seconds=120)
    assert ca.injector_target_matches_rows(active,database.rows)
    assert database.calls[0][1]["read_committed"] is True
    statements=[sql for sql,args in database.calls if "pg_advisory" in sql]
    assert len(statements)==2
    loaded=db._load("load_active_auxiliary","FERTILIZER-INJECTION-CH1")
    assert loaded["injector_target"]==active["injector_target"]
    database.now+=timedelta(seconds=70)
    replay=database.activate()
    assert replay["success"] and not replay["created"] and replay["execution"]==active
    assert len([r for r in database.rows if r["action"]=="mark_auxiliary_active"])==1


@pytest.mark.parametrize("fault", ["off_slot","off_outcome","containment","manual","parent_off",
    "parent_stopping","parent_manual","parent_flush","missing_dispatch","outcome_before_dispatch",
    "duplicate_claim","missing_outcome","changed_receipt","expired","future_receipt","late_persistence","forged_target"])
def test_canonical_activation_refuses_uncertainty_without_target(monkeypatch,fault):
    d=Database(monkeypatch)
    if fault in {"off_slot","off_outcome","containment"}:
        d.rows.append({"execution_id":d.body["execution_id"],"action":{
            "off_slot":"claim_auxiliary_off_attempt","off_outcome":"record_auxiliary_off_outcome",
            "containment":"contain_auxiliary_device"}[fault]})
    elif fault=="manual": d.rows[0]["manual_isolation_active"]=True
    elif fault in {"parent_off","parent_stopping","parent_manual"}:
        d.parents.append({**d.parents[-1],"action":"mark_stopping" if fault=="parent_stopping" else "record_off_outcome",
            "manual_off_active":fault=="parent_manual"})
    elif fault=="parent_flush":
        for row in d.parents:
            row["primary_stop_deadline"]=(d.now+timedelta(seconds=500)).isoformat()
    elif fault=="missing_dispatch": d.rows.pop(1)
    elif fault=="outcome_before_dispatch": d.rows[1],d.rows[2]=d.rows[2],d.rows[1]
    elif fault=="duplicate_claim": d.rows.append(deepcopy(d.rows[0]))
    elif fault=="missing_outcome": d.rows.pop()
    elif fault=="changed_receipt": d.body["command_on_receipt"]={**d.body["command_on_receipt"],"entity_id":"switch.forged"}
    elif fault=="expired": d.now=ca.moment(d.body["primary_stop_deadline"])
    elif fault=="future_receipt": d.now=ca.moment(d.body["command_on_receipt"]["accepted_at"])-timedelta(seconds=1)
    elif fault=="late_persistence": d.clock_step=120
    elif fault=="forged_target": d.body["injector_target"]={"target_seconds":999}
    result=d.activate()
    assert result["success"] is False, (fault,result)
    assert not any(r["action"]=="mark_auxiliary_active" for r in d.rows)


@pytest.mark.parametrize("fault", ["missing_active","missing_dispatch","forged_binding","off_slot","manual"])
def test_restart_never_extends_unproven_or_interrupted_claim(monkeypatch,fault):
    d=Database(monkeypatch); active=d.activate()["execution"]
    if fault=="missing_active": d.rows.pop()
    elif fault=="missing_dispatch": d.rows.pop(1)
    elif fault=="forged_binding": d.rows[-1]["injector_target"]["target_off_at"]=(d.now+timedelta(days=1)).isoformat()
    elif fault=="off_slot": d.rows.append({"execution_id":active["execution_id"],"action":"claim_auxiliary_off_attempt"})
    else: d.rows[-1]["manual_off_active"]=True
    loaded=db._load("load_active_auxiliary","FERTILIZER-INJECTION-CH1")
    assert loaded["state"]=="claimed_recovery_required"
    assert ca.command_stop_deadline(loaded)==ca.moment(active["primary_stop_deadline"])


def test_failed_commit_does_not_leave_activation(monkeypatch):
    d=Database(monkeypatch); d.fail_commit=True
    with pytest.raises(RuntimeError): d.activate()
    assert not any(r["action"]=="mark_auxiliary_active" for r in d.rows)


@pytest.mark.parametrize("offset,delivery,complete", [(-60,65,False),(-1,5,False),(0,0,True),(0,5,True),(1,2,True),(70,10,True)])
def test_elapsed_target_and_delay_reports_preserve_receipt_truth(monkeypatch,offset,delivery,complete):
    d=Database(monkeypatch); active=d.activate()["execution"]
    deadline=ca.command_stop_deadline(active)
    off=receipt(active,"OFF",at=deadline+timedelta(seconds=offset))
    off["accepted_at"]=(deadline+timedelta(seconds=offset+delivery)).isoformat()
    off["receipt_sha256"]=ca.digest({k:v for k,v in off.items() if k!="receipt_sha256"})
    terminal=ca.terminal(active,off,now=ca.moment(off["accepted_at"]),reason="primary_deadline_reached")
    terminal["command_program_completed"]=True
    assert ca.program_completed(terminal) is complete
    timing=ca.injector_target_timing(terminal)
    assert timing["off_request_offset_seconds"]==offset
    assert timing["off_acceptance_offset_seconds"]==offset+delivery
    assert timing["off_delivery_delay_seconds"]==delivery
    assert timing["accepted_command_interval_seconds"]==120+offset+delivery
    assert timing["physical_runtime_seconds"] is None
    from modules.oom_sakkie.rootline_transition_notifications import compose_transition_notice
    terminal["notification_observed_at"]=off["accepted_at"]
    for language in ("en","af"):
        text=compose_transition_notice("Stopped",terminal,language=language)
        assert "120 s" in text
        assert (("Programme completed" if language == "en" else "Program voltooi") in text) is complete
        if offset+delivery > 0:
            assert f"{offset+delivery:g} s" in text and "⚠️" in text


def test_registry_target_compatibility_and_old_claims_unchanged():
    from modules.telemetry.rootline_device_registry import get_device_contract
    contract=get_device_contract("FERTILIZER-INJECTION-CH1")
    from modules.telemetry.rootline_auxiliary_management import INJECTION_SECONDS
    assert INJECTION_SECONDS==120
    assert contract["device_id"]=="100204d497" and contract["channel"]==1
    now,body,rows,parents=fixture(); body.pop("injector_timing_contract")
    assert not ca.injector_target_claim(body)
    assert ca.command_stop_deadline(body)==now+timedelta(seconds=120)


def test_target_registry_profile_remains_120_without_native_countdown():
    from modules.telemetry.rootline_device_spine import scheduled_device_profile
    record={"stop_mode":"scheduled","provider":"ifttt_ewelink",
        "provider_account_binding":"ewelink_owner_account","device_id":"100204d497","channel":1,
        "device_type":"flow_dependent_injection_valve","maximum_runtime_seconds":120,
        "native_fail_stop_seconds":0}
    assert scheduled_device_profile(record)
    assert not scheduled_device_profile({**record,"maximum_runtime_seconds":121})


def test_completion_cannot_strip_new_claim_timing_marker(monkeypatch):
    d=Database(monkeypatch);active=d.activate()["execution"]
    off=receipt(active,"OFF",at=ca.command_stop_deadline(active))
    d.rows.append({"execution_id":active["execution_id"],"action":"record_auxiliary_off_outcome","outcome":off})
    terminal=ca.terminal(active,off,reason="primary_deadline_reached")
    terminal["command_program_completed"]=True
    assert ca.terminal_matches_rows(terminal,d.rows)
    terminal.pop("injector_timing_contract");terminal.pop("injector_target")
    assert not ca.terminal_matches_rows(terminal,d.rows)

@pytest.mark.parametrize("language", ["en", "af"])
@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("known", [False, True])
def test_activity_target_uses_immutable_closed_execution(monkeypatch, language, configured, known):
    from modules.oom_sakkie.rootline_activity_presentation import activity_notice
    from tests.test_rootline_owner_injection_programme import versioned_database
    d = versioned_database(monkeypatch, minutes=10) if configured else Database(monkeypatch)
    active = d.activate()["execution"]
    deadline = ca.command_stop_deadline(active)
    off = receipt(active, "OFF", at=deadline)
    terminal = ca.terminal(active, off, now=deadline, reason="primary_deadline_reached")
    terminal["command_program_completed"] = True
    assert ca.duty_closed(terminal) and ca.program_completed(terminal)
    target = 600 if configured else 120
    assert ca.injector_target_timing(terminal)["target_seconds"] == target
    # A later caller setting cannot change the original accepted duty target.
    terminal["owner_settings"] = {"pulse_minutes": 3}
    if not known:
        terminal.pop("injector_target", None)
        assert ca.injector_target_timing(terminal) is None
    text = activity_notice("Stopped", terminal, language=language)
    prefix = "Teiken:" if language == "af" else "Target:"
    if known:
        assert f"{prefix} {target} s" in text
        assert f"{prefix} {120 if configured else 600} s" not in text
    else:
        assert prefix not in text
