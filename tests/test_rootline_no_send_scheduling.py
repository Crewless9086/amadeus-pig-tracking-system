"""Optional no-send proof cannot consume B/C's admission window."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry import rootline_borehole_commissioning as borehole
from modules.telemetry import rootline_irrigation_coordinator as coordinator

NOW = datetime.now(timezone.utc)


class Scenario:
    def __init__(self, monkeypatch):
        self.events = []
        self.now = NOW
        self.active = {"execution_id": "UNSENT", "device_id": "1002851416", "channel": 1,
            "on_not_dispatched": True, "state": "claimed_recovery_required",
            "claimed_at": (NOW-timedelta(minutes=5)).isoformat(),
            "primary_stop_deadline": (NOW+timedelta(minutes=2)).isoformat()}
        self.aux = []
        self.factory = None
        self.callback_failure = False
        self.pending_mixer = False
        self.protection = None
        self.energy = None
        monkeypatch.setattr(borehole, "_stop_borehole", self.stop)
        monkeypatch.setattr(managed, "advance_auxiliary_execution", self.stop_aux)
    def stop(self, active, store, transport):
        self.events.append("OFF:"+active["execution_id"])
        return 1
    def stop_aux(self, **kwargs):
        self.events.append("AUX_OFF:"+kwargs["expected_execution_id"])
        return {"success": True, "status": "auxiliary_completed", "hardware_commands": 1}
    def store(self, action, payload):
        self.events.append(action)
        if action == "load_active_auxiliaries": return deepcopy(self.aux)
        if action == "load_active_borehole": return deepcopy(self.active)
        if action == "retire_not_dispatched_execution":
            self.events.append("PROOF:"+payload["execution_id"])
            return {"success": False, "no_send_stage": "family",
                "no_send_reason": "ewelink_active_recovery_capacity_deferred"}
        pytest.fail(action)
    def admission(self, result):
        self.events.append("BC")
        self.now += timedelta(seconds=10)
        if self.callback_failure:
            self.aux = [{"execution_id": "NEW-DUE", "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
                "primary_stop_deadline": (NOW-timedelta(seconds=1)).isoformat()}]
            raise RuntimeError("synthetic BC callback failure")
    def run(self):
        return managed.run_rootline_managed_device_cycle(evidence={}, transport=object(), store=self.store,
            environ={"ROOTLINE_BOREHOLE_ENABLED": "true",
                "ROOTLINE_FERTILIZER_MIXING_ENABLED": str(self.pending_mixer).lower()},
            now=NOW, clock=lambda: self.now, after_safety=self.admission,
            evidence_factory=self.factory, borehole_safety_reader=self.protection, energy_reader=self.energy)


def test_optional_quota_deferred_proof_runs_once_after_bc_and_mandatory_reread(monkeypatch):
    s = Scenario(monkeypatch)
    result = s.run()
    assert s.events.count("OFF:UNSENT") == s.events.count("PROOF:UNSENT") == 1
    assert s.events.index("OFF:UNSENT") < s.events.index("BC") < s.events.index("PROOF:UNSENT")
    between = s.events[s.events.index("BC")+1:s.events.index("PROOF:UNSENT")]
    assert "load_active_auxiliaries" in between and "load_active_borehole" in between
    assert result["hardware_commands"] == 1 and result["writes_farm_data"] is False
    assert result["blocks_bc"] is False and result["status"] == "no_send_off_proof_pending"


def test_callback_exception_still_supervises_new_due_duty_without_optional_proof(monkeypatch):
    s = Scenario(monkeypatch); s.callback_failure = True
    with pytest.raises(RuntimeError, match="callback failure"):
        s.run()
    assert "AUX_OFF:NEW-DUE" in s.events and "PROOF:UNSENT" not in s.events
    assert s.events.index("BC") < s.events.index("AUX_OFF:NEW-DUE")


def test_third_pass_keeps_cumulative_due_dedup_after_factory_failure(monkeypatch):
    s = Scenario(monkeypatch); s.pending_mixer = True
    s.aux = [{"execution_id": "DUE", "auxiliary_device_id": "FERTILIZER-INJECTION-CH1",
        "primary_stop_deadline": (NOW-timedelta(seconds=1)).isoformat()}]
    def factory():
        s.events.append("FACTORY")
        raise managed.ManagedDevicePlanningUnavailable({"success": False, "status": "synthetic_failure"})
    s.factory = factory
    result = s.run()
    assert s.events.count("AUX_OFF:DUE") == 1
    assert s.events.count("load_active_auxiliaries") == 3
    assert s.events.index("PROOF:UNSENT") < s.events.index("FACTORY")
    assert result["success"] is False


def test_changed_canonical_identity_is_not_retired_from_stale_queue(monkeypatch):
    s = Scenario(monkeypatch)
    def admission(result):
        s.events.append("BC")
        s.active = None
    s.admission = admission
    s.run()
    assert "PROOF:UNSENT" not in s.events


def test_no_defer_callback_preserves_existing_stop_then_proof(monkeypatch):
    s = Scenario(monkeypatch)
    coordinator._retire_unsent_execution(s.active, s.store, object())
    assert s.events.index("OFF:UNSENT") < s.events.index("PROOF:UNSENT")


def test_newly_due_no_send_duty_repeats_mandatory_stop_but_not_optional_proof(monkeypatch):
    s = Scenario(monkeypatch)
    def admission(result):
        s.events.append("BC")
        s.now = NOW+timedelta(minutes=3)
    s.admission = admission
    s.run()
    assert s.events.count("OFF:UNSENT") == 2
    assert s.events.count("PROOF:UNSENT") == 1


def test_optional_proof_crossing_deadline_still_gets_final_mandatory_stop(monkeypatch):
    s = Scenario(monkeypatch)
    original = s.store
    def store(action, payload):
        result = original(action, payload)
        if action == "retire_not_dispatched_execution": s.now = NOW+timedelta(minutes=3)
        return result
    s.store = store
    s.run()
    assert s.events.count("OFF:UNSENT") == 2
    assert s.events.index("PROOF:UNSENT") < len(s.events)-1-s.events[::-1].index("OFF:UNSENT")
    assert s.events.count("PROOF:UNSENT") == 1


@pytest.mark.parametrize("outcome", ["missing", "error"])
def test_optional_canonical_reload_elapsed_time_still_gets_final_safety(monkeypatch, outcome):
    s = Scenario(monkeypatch)
    original = s.store
    count = 0
    def store(action, payload):
        nonlocal count
        if action == "load_active_borehole":
            count += 1
            # Initial inventory and advance's own reload, post-BC inventory,
            # then the optional tail's canonical proof preimage.
            if count == 4:
                s.now = NOW+timedelta(minutes=3)
                if outcome == "error": raise RuntimeError("synthetic optional reload failure")
                return None
        return original(action, payload)
    s.store = store
    s.run()
    assert s.events.count("OFF:UNSENT") == 2
    assert "PROOF:UNSENT" not in s.events


@pytest.mark.parametrize("kind", ["protection", "energy"])
def test_fresh_adverse_evidence_does_not_skip_mandatory_stop(monkeypatch, kind):
    s = Scenario(monkeypatch)
    adverse = False
    if kind == "protection": s.protection = lambda: not adverse
    else: s.energy = lambda: {"fresh": True, "borehole_eligible": not adverse}
    def admission(result):
        nonlocal adverse
        s.events.append("BC")
        adverse = True
    s.admission = admission
    s.run()
    assert s.events.count("OFF:UNSENT") >= 2
    assert s.events.count("PROOF:UNSENT") == 1


@pytest.mark.parametrize("fault", [None, "inventory", "mandatory"])
def test_gateway_preserves_known_bc_result_when_only_optional_precheck_expires(monkeypatch, fault):
    from tests.test_rootline_active_supervision import gateway, ExecutionStore, Transport, ScheduleStore, NOW as GATEWAY_NOW
    s = Scenario(monkeypatch)
    original_store = s.store
    def store(action, payload):
        if fault == "inventory" and action == "load_active_auxiliaries":
            raise RuntimeError("synthetic inventory failure")
        return original_store(action, payload)
    def exhausted():
        raise managed.RootlineCycleDeadlineExceeded("synthetic original optional deadline")
    monkeypatch.setattr(managed, "remaining_seconds", exhausted)
    if fault == "mandatory":
        def stop(*args): raise RuntimeError("synthetic mandatory stop failure")
        monkeypatch.setattr(borehole, "_stop_borehole", stop)
    def managed_cycle(**kwargs):
        return managed.run_rootline_managed_device_cycle(evidence={}, transport=object(),
            store=store, clock=lambda:s.now, **kwargs)
    schedules = ScheduleStore()
    schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
        "next_due_at": (GATEWAY_NOW+timedelta(minutes=30)).isoformat()}
    value, _, _, _ = gateway(ExecutionStore(), Transport(), schedules=schedules,
        managed_device_cycle=managed_cycle,
        execution_cycle=lambda **kwargs: {"success":True,"status":"segment_started",
            "hardware_commands":1,"writes_farm_data":True})
    if fault is None:
        assert value["success"] is True
        assert value["status"] == "scheduled_rootline_active_supervised"
        assert value["execution_status"] == "segment_started"
        assert value.get("effects_unknown") is not True
        assert "PROOF:UNSENT" not in s.events
    else:
        assert value["success"] is False
        assert value["status"] == "scheduled_rootline_active_supervision_unproven"


def test_optional_deadline_after_canonical_work_started_remains_failure(monkeypatch):
    s = Scenario(monkeypatch)
    original_store = s.store
    count = 0
    def store(action, payload):
        nonlocal count
        if action == "load_active_borehole":
            count += 1
            if count == 4:
                s.now = NOW+timedelta(minutes=3)
                raise managed.RootlineCycleDeadlineExceeded("synthetic in-work deadline")
        return original_store(action, payload)
    s.store = store
    result = s.run()
    assert result["success"] is False
    deferred = next(row for row in result["outcomes"] if row.get("no_send_stage") == "optional_proof")
    assert "effects_unknown" not in deferred
    assert s.events.count("OFF:UNSENT") == 2 and "PROOF:UNSENT" not in s.events
