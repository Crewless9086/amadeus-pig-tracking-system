"""An empty optional tail preserves mandatory supervision and all real work gates."""
from copy import deepcopy
from datetime import timedelta

import pytest

from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry import rootline_cycle_budget as cycle
from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable
from tests.test_rootline_bc_cycle_efficiency import Clock
from tests.test_rootline_execution_runtime import NOW


_MISSING = object()


class Scenario:
    def __init__(self, monkeypatch):
        self.clock = Clock()
        monkeypatch.setattr(cycle.time, "monotonic", self.clock.monotonic)
        self.source = {"ROOTLINE_BOREHOLE_ENABLED": "true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED": "false",
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "false"}
        self.borehole = {"execution_id": "RECOVERY", "device_id": "1002851416",
            "primary_stop_deadline": (NOW+timedelta(seconds=120)).isoformat(),
            "state": "claimed_recovery_required", "on_not_dispatched": True}
        self.auxiliaries = []
        self.events = []
        self.fail_inventory = self.fail_recovery = False
        self.expire = True
        self.final_duty = None
        self.evidence_reads = 0
        self.completion_success = True
        self.after = None
        def recover(**kwargs):
            self.events.append(("recover", self.clock.elapsed))
            if self.fail_recovery:
                return {"success": False, "status": "borehole_supervision_unproven"}
            self.borehole = None
            return {"success": True, "status": "execution_not_dispatched",
                "hardware_commands": 0, "writes_farm_data": True}
        monkeypatch.setattr(managed, "advance_borehole_execution", recover)
        def auxiliary(**kwargs):
            self.events.append(("final_auxiliary", self.clock.elapsed))
            self.auxiliaries = []
            return {"success": self.final_duty != "failed",
                "status": "auxiliary_completed" if self.final_duty != "failed" else "auxiliary_supervision_unproven",
                "hardware_commands": 0}
        monkeypatch.setattr(managed, "advance_auxiliary_execution", auxiliary)

    def store(self, action, payload):
        self.events.append((action, self.clock.elapsed))
        if action == "load_active_auxiliaries":
            if self.fail_inventory: raise RootlineExecutionStoreUnavailable(action)
            return deepcopy(self.auxiliaries)
        if action == "load_active_borehole": return deepcopy(self.borehole)
        if action == "record_fertilizer_sequence_completed":
            return {"success": self.completion_success, "created": self.completion_success}
        pytest.fail("unexpected optional store operation: " + action)

    def admission(self, result):
        self.events.append(("after_safety", self.clock.elapsed))
        self.clock.elapsed = 165 if self.expire else 10
        if self.final_duty:
            self.auxiliaries = [{"execution_id": "FINAL-DUTY", "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
                "primary_stop_deadline": (NOW+timedelta(seconds=100)).isoformat()}]
        if self.after: self.after()

    def evidence_factory(self):
        self.evidence_reads += 1
        self.events.append(("evidence_factory", self.clock.elapsed))
        return {}

    def run(self, evidence=_MISSING, *, factory=True, allow_new=True, allow_borehole=True):
        class ForbiddenTransport:
            def __getattr__(self, name): pytest.fail("unexpected provider operation: " + name)
        with cycle.cycle_budget(deadline=140):
            return managed.run_rootline_managed_device_cycle(
                evidence={} if evidence is _MISSING else evidence, transport=ForbiddenTransport(),
                environ=self.source, store=self.store, clock=self.clock.now, now=NOW,
                evidence_factory=self.evidence_factory if factory else None,
                allow_new_starts=allow_new, allow_borehole_starts=allow_borehole,
                after_safety=self.admission)

    def assert_two_mandatory_passes(self):
        names = [name for name, _ in self.events]
        assert names.count("load_active_auxiliaries") == names.count("load_active_borehole") == 2
        assert names.index("after_safety") > names.index("recover")
        assert [at for name, at in self.events if name == "load_active_borehole"] == [0, 165 if self.expire else 10]


def statuses(result):
    return [v["status"] for v in result.get("outcomes", [result])]


def test_genuine_empty_tail_keeps_completed_mandatory_passes_without_optional_io(monkeypatch):
    s = Scenario(monkeypatch)
    result = s.run()
    assert result["success"] is True and result["status"] == "execution_not_dispatched"
    s.assert_two_mandatory_passes()
    assert s.evidence_reads == 0
    assert [name for name, at in s.events if at == 165] == ["load_active_auxiliaries", "load_active_borehole"]
    assert cycle.work_deadline() is cycle.on_deadline() is None


@pytest.mark.parametrize("work", ["borehole", "mixer", "injector"])
def test_pending_work_with_expired_budget_still_defers(monkeypatch, work):
    s = Scenario(monkeypatch)
    if work == "borehole": s.borehole = None
    else: s.source["ROOTLINE_FERTILIZER_" + ("MIXING" if work == "mixer" else "INJECTION") + "_ENABLED"] = "true"
    result = s.run()
    assert result["success"] is False
    assert "managed_device_cycle_deadline_deferred" in statuses(result)
    assert s.evidence_reads == 0
    assert len([name for name, _ in s.events if name == "load_active_borehole"]) == 2


@pytest.mark.parametrize("expired", [True, False])
@pytest.mark.parametrize("success", [True, False])
def test_known_fertilizer_completion_keeps_budget_and_persistence_semantics(monkeypatch, expired, success):
    s = Scenario(monkeypatch); s.expire = expired; s.completion_success = success
    result = s.run({"fertilizer_control_progress": {"completed": True, "sequence_id": "SEQUENCE"}})
    written = [name for name, _ in s.events if name == "record_fertilizer_sequence_completed"]
    assert written == ([] if expired else ["record_fertilizer_sequence_completed"])
    if expired:
        assert result["success"] is False and "managed_device_cycle_deadline_deferred" in statuses(result)
    elif success:
        assert result["success"] is True and "fertilizer_controller_sequence_completed" in statuses(result)
    else:
        assert result["success"] is False and "fertilizer_sequence_persistence_unproven" in statuses(result)
    s.assert_two_mandatory_passes()


@pytest.mark.parametrize("packet", [None, [], "unknown", {"status": "Unavailable"},
    {"fertilizer_control_progress": {"completed": False}}, {"fertilizer_control_progress": {"completed": True}}])
def test_supplied_or_malformed_packets_retain_legacy_deadline(monkeypatch, packet):
    s = Scenario(monkeypatch)
    result = s.run(packet)
    assert result["success"] is False and "managed_device_cycle_deadline_deferred" in statuses(result)
    s.assert_two_mandatory_passes()


def test_exact_dict_guard_does_not_admit_subclass(monkeypatch):
    class Packet(dict): pass
    s = Scenario(monkeypatch)
    result = s.run(Packet())
    assert result["success"] is False and "managed_device_cycle_deadline_deferred" in statuses(result)


@pytest.mark.parametrize("failure", ["inventory", "final_inventory", "mandatory_recovery", "final_duty"])
def test_failed_mandatory_outcomes_are_never_cleared(monkeypatch, failure):
    s = Scenario(monkeypatch)
    if failure == "inventory": s.fail_inventory = True
    elif failure == "final_inventory": s.after = lambda: setattr(s, "fail_inventory", True)
    elif failure == "mandatory_recovery": s.fail_recovery = True
    else: s.final_duty = "failed"
    result = s.run()
    assert result["success"] is False
    expected = {"inventory": "auxiliary_inventory_unproven", "final_inventory": "auxiliary_inventory_unproven", "mandatory_recovery": "borehole_supervision_unproven",
        "final_duty": "auxiliary_supervision_unproven"}[failure]
    assert expected in statuses(result)
    s.assert_two_mandatory_passes()


def test_new_due_duty_is_supervised_before_empty_tail_returns(monkeypatch):
    s = Scenario(monkeypatch); s.final_duty = "completed"
    result = s.run()
    assert result["success"] is True and "auxiliary_completed" in statuses(result)
    assert ("final_auxiliary", 165) in s.events
    assert s.evidence_reads == 0
    s.assert_two_mandatory_passes()


def test_evidence_needed_path_keeps_planning_failure_and_final_pass(monkeypatch):
    s = Scenario(monkeypatch); s.borehole = None; s.expire = False
    def failed():
        s.evidence_reads += 1
        raise managed.ManagedDevicePlanningUnavailable({"success": False, "status": "managed_device_evidence_unavailable"})
    s.evidence_factory = failed
    result = s.run()
    assert result["success"] is False and "managed_device_evidence_unavailable" in statuses(result)
    assert s.evidence_reads == 1
    assert len([name for name, _ in s.events if name == "load_active_borehole"]) == 3


def test_disabled_start_branch_and_supplied_completion_remain_unchanged(monkeypatch):
    s = Scenario(monkeypatch)
    result = s.run({"fertilizer_control_progress": {"completed": True}}, allow_new=False, allow_borehole=False)
    assert result["success"] is True and result["status"] == "execution_not_dispatched"
    assert not any(name == "record_fertilizer_sequence_completed" for name, _ in s.events)
    s.assert_two_mandatory_passes()


def test_empty_pending_but_evidence_needed_keeps_expired_planning_hold(monkeypatch):
    s = Scenario(monkeypatch); s.borehole = None
    s.source["ROOTLINE_BOREHOLE_ENABLED"] = "false"
    result = s.run()
    assert result["success"] is False and "managed_device_cycle_deadline_deferred" in statuses(result)
    assert s.evidence_reads == 0
    assert len([name for name, _ in s.events if name == "load_active_borehole"]) == 2
