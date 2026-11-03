"""Offline composed scheduler -> managed safety -> B/C -> optional planning.

Provider, database and clock boundaries are synthetic. Gateway, managed runtime,
energy policy, B/C runtime and coordinators execute their actual production code.
The deterministic candidate plan comes from the established execution fixture.
"""
from copy import deepcopy
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.telemetry import rootline_cycle_budget as budget
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_water_energy_plan as planning
from modules.telemetry import power_service
from tests.test_rootline_bc_cycle_efficiency import Path
from tests.test_rootline_execution_runtime import NOW, evidence
from tests.test_rootline_active_supervision import ENV, HEADERS, payload
from tests.test_rootline_active_weather_stop import dry_weather_reader


class ComposedPath(Path):
    def __init__(self, monkeypatch, *, optional_seconds=65, **kwargs):
        super().__init__(monkeypatch, **kwargs)
        self.optional_seconds = optional_seconds
        self.borehole = {"execution_id": "SYNTHETIC-OWNED-BOREHOLE",
            "device_id": "1002851416", "channel": 1, "state": "Active",
            "primary_stop_deadline": (NOW + timedelta(hours=2)).isoformat(),
            "provider_start_evidence": {"authoritative": True, "state": "ON"}}
        self.borehole_state = "ON"
        self.borehole_reads = []
        self.off_slots = set()
        self.fault_checks = 0
        self.fault = lambda: True
        self.optional_hook = lambda: None
        self.managed_calls = 0
        self.current_deadline = None
        self.auxiliaries = []
        original_read = self.transport.read_output_state
        original_send = self.transport.set_state

        def read(**kwargs):
            if kwargs["device_id"] != "1002851416":
                return original_read(**kwargs)
            self.clock.spend("borehole provider observation", 18)
            self.borehole_reads.append(self.clock.elapsed)
            return {**kwargs, "authoritative": self.borehole_state != "Unknown",
                "state": self.borehole_state, "evidence_id": "SYNTHETIC-BOREHOLE-READ",
                "retrieved_at": self.clock.now().isoformat()}

        def send(**kwargs):
            if kwargs["state"] == "ON":
                assert self.clock.monotonic() < budget.on_deadline()
            value = original_send(**kwargs)
            if kwargs["device_id"] == "1002851416":
                self.borehole_state = kwargs["state"]
            return value

        self.transport.read_output_state = read
        self.transport.set_state = send
        monkeypatch.setattr(power_service, "get_current_power_state", self.power)
        monkeypatch.setattr(planning, "read_current_borehole_faults", self.protection)

    def power(self, **kwargs):
        self.clock.spend("power evidence", 2)
        return {"success": True, "source": {"last_reading_at": self.clock.now().isoformat()},
            "current": {"battery_soc_pct": 60, "solar_power_w": 1500,
                "load_power_w": 1000, "grid_power_w": 0, "battery_power_w": -100,
                "battery_state": "charging"}}, 200

    def protection(self, *args, **kwargs):
        self.clock.spend("borehole protection evidence", 1)
        self.fault_checks += 1
        return self.fault()

    def store(self, action, item):
        if action == "load_active_auxiliaries":
            self.clock.spend("managed inventory", .7)
            return deepcopy(self.auxiliaries)
        if action == "load_active_borehole":
            self.clock.spend("borehole inventory", .7)
            return deepcopy(self.borehole)
        if action == "load_borehole_off_attempts":
            return [{"attempt": value} for value in self.off_slots]
        if action == "dispatch_borehole_off_edge":
            assert budget.work_deadline() is None
            if item["attempt"] in self.off_slots:
                return {"provider_command_attempted": False}
            self.off_slots.add(item["attempt"])
            return {**item["dispatch"](), "provider_command_attempted": True}
        if action == "record_borehole_completed":
            assert budget.work_deadline() is None
            self.backing.rows.append((action, deepcopy(item)))
            self.borehole = None
            return {"success": True, "created": True}
        return super().store(action, item)

    def optional_loader(self, **kwargs):
        assert budget.work_deadline() == self.current_deadline
        assert budget.on_deadline() == self.current_deadline
        # Bound the modeled I/O as production readers bound their statement/socket.
        available = budget.remaining_seconds(self.optional_seconds)
        self.clock.spend("optional managed evidence", available)
        self.optional_hook()
        budget.remaining_seconds()
        return evidence(), NOW.date().isoformat(), NOW

    def managed(self, **kwargs):
        self.managed_calls += 1
        self.current_deadline = budget.on_deadline()
        assert budget.work_deadline() == self.current_deadline
        return runtime.run_rootline_managed_device_reassessment(**kwargs,
            store=self.store, transport=self.transport, token_store=object(),
            evidence_loader=self.optional_loader, clock=self.clock.now)

    def supervisor(self, **kwargs):
        return runtime.supervise_rootline_active_execution(**kwargs, store=self.store,
            token_store=object(), transport=self.transport, clock=self.clock.now,
            active_weather_reader=dry_weather_reader)

    def gateway(self, *, tick=None):
        tick = tick or NOW
        if not self.schedules.rows:
            self.schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
                "next_due_at": (NOW + timedelta(hours=1)).isoformat()}
        request = payload(due_at=tick.isoformat(), trigger_timestamp=tick.isoformat(),
            evidence_cutoff=(tick - timedelta(seconds=1)).isoformat())
        source = {**ENV, "ROOTLINE_BOREHOLE_ENABLED": "true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED": "true",
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true", "ROOTLINE_A_ENABLED": "false",
            "ROOTLINE_ESKOM_ENABLED": "false"}
        return handle_rootline_reassessment_trigger(request, HEADERS, source,
            state_store=self.state, schedule_store=self.schedules, scheduler_now=tick,
            family_delivery=lambda *a, **k: {"success": True, "telegram_message_id": "synthetic"},
            specialist_loader=lambda **k: pytest.fail("report cadence is not due"),
            active_supervision_cycle=self.supervisor, managed_device_cycle=self.managed,
            execution_cycle=self.cycle)


def test_real_composition_starts_bc_before_optional_planning_spends_budget(monkeypatch):
    path = ComposedPath(monkeypatch)
    value, status = path.gateway()
    assert path.controls[0]["status"] == "segment_started"
    assert status == 202  # Optional work is honestly deferred after useful control.
    assert value["execution_status"] == "segment_started"
    assert value["hardware_commands"] == 1 and value.get("effects_unknown", False) is False
    assert len(path.borehole_reads) == 1
    assert path.fault_checks == 2
    assert path.managed_calls == 1
    assert [(row["device_id"], row["channel"], row["state"]) for row in path.transport.calls] == [
        ("100204e9bc", 1, "ON")]
    names = [name for name, _ in path.clock.events]
    assert names.index("borehole provider observation") < names.index("provider ON")
    assert names.index("provider ON") < names.index("optional managed evidence")
    saved = path.schedules.rows[value["schedule_identity"] + ":outcome"]
    assert saved["execution_status"] == "segment_started" and saved["hardware_commands"] == 1
    assert saved["provider_effects_unknown"] is False
    assert value["supervision_next_due_at"]
    replay, _ = path.gateway()
    assert replay["status"] == "scheduled_reassessment_replayed_noop"
    assert len(path.transport.calls) == len(path.borehole_reads) == 1


def test_later_distinct_tick_gets_fresh_borehole_observation_without_duplicate_on(monkeypatch):
    path = ComposedPath(monkeypatch, optional_seconds=10)
    first, _ = path.gateway()
    path.clock.elapsed = 180
    second, _ = path.gateway(tick=NOW + timedelta(minutes=3))
    assert first["schedule_identity"] != second["schedule_identity"]
    assert second["active_supervision_status"] == "active_segment_owned"
    assert len(path.borehole_reads) == 2 and path.managed_calls == 2
    assert [row["state"] for row in path.transport.calls] == ["ON"]


@pytest.mark.parametrize("change", ["deadline", "canonical", "fault"])
def test_post_planning_recheck_preserves_due_changed_and_unsafe_duties(monkeypatch, change):
    path = ComposedPath(monkeypatch)
    if change == "deadline":
        path.borehole["primary_stop_deadline"] = (NOW + timedelta(seconds=130)).isoformat()
    elif change == "canonical":
        path.optional_hook = lambda: path.borehole.update(state="Stopping")
    else:
        path.fault = lambda: path.fault_checks == 1
    value, _ = path.gateway()
    assert value["execution_status"] == "segment_started"
    assert [row["state"] for row in path.transport.calls] == ["ON", "OFF"]
    assert path.borehole is None and len(path.borehole_reads) == 2
    assert any(action == "record_borehole_completed" for action, _ in path.backing.rows)
    assert value["hardware_commands"] == 2
    if change == "deadline":
        assert next(at for name, at in path.clock.events if name == "provider OFF") >= 140


def test_new_owned_device_after_planning_is_supervised_even_after_optional_expiry(monkeypatch):
    path = ComposedPath(monkeypatch)
    prior = deepcopy(path.borehole)
    path.borehole = None
    def claim_elsewhere():
        path.borehole = {**prior, "execution_id": "SYNTHETIC-NEW-CLAIM",
            "primary_stop_deadline": (NOW + timedelta(seconds=130)).isoformat()}
    path.optional_hook = claim_elsewhere
    value, _ = path.gateway()
    assert value["execution_status"] == "segment_started"
    assert path.borehole is None and path.off_slots == {1}
    assert [row["state"] for row in path.transport.calls] == ["ON", "OFF"]


def test_safety_fault_is_local_to_borehole_and_does_not_block_bc(monkeypatch):
    path = ComposedPath(monkeypatch, optional_seconds=5)
    path.fault = lambda: False
    value, _ = path.gateway()
    assert path.controls[0]["status"] == "segment_started"
    assert [(row["device_id"], row["state"]) for row in path.transport.calls] == [
        ("1002851416", "OFF"), ("100204e9bc", "ON")]
    assert value["hardware_commands"] == 2


def test_original_on_deadline_is_not_extended_by_mandatory_safety(monkeypatch):
    path = ComposedPath(monkeypatch, claim_seconds=80)
    value, _ = path.gateway()
    assert path.clock.elapsed > 140
    assert all(row["state"] != "ON" for row in path.transport.calls)
    outcome = next(row for action, row in path.backing.rows if action == "record_on_outcome")
    assert outcome["on_outcome"]["status"] == "execution_cycle_deadline_deferred"
    assert outcome["on_outcome"]["provider_command_attempted"] is False
    assert value["execution_status"] == "ambiguous_on_shutdown_unverified"
    assert path.current_deadline == 140


def test_concurrent_same_schedule_runs_real_managed_path_once(monkeypatch):
    path = ComposedPath(monkeypatch, optional_seconds=10)
    entered, release = Event(), Event()
    original = path.managed
    def blocked(**kwargs):
        entered.set()
        assert release.wait(10)
        return original(**kwargs)
    path.managed = blocked
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(path.gateway)
        assert entered.wait(10)
        duplicate, _ = path.gateway()
        release.set()
        value, _ = first.result()
    assert duplicate["status"] == "scheduled_reassessment_claim_interrupted"
    assert value["execution_status"] == "segment_started"
    assert path.managed_calls == len(path.borehole_reads) == 1
    assert [row["state"] for row in path.transport.calls] == ["ON"]


def test_unproven_auxiliary_ownership_blocks_bc_but_still_supervises_borehole(monkeypatch):
    path = ComposedPath(monkeypatch, optional_seconds=5)
    path.auxiliaries = [{"execution_id": "SYNTHETIC-UNKNOWN-AUXILIARY",
        "auxiliary_device_id": "UNKNOWN", "primary_stop_deadline": NOW.isoformat()}]
    value, status = path.gateway()
    assert status == 202 and path.controls == []
    assert len(path.borehole_reads) == 1 and path.borehole is not None
    assert path.transport.calls == []
    assert value["managed_device_result"]["blocks_bc"] is True


def test_missing_borehole_observation_does_not_cancel_run_or_hold_bc(monkeypatch):
    path = ComposedPath(monkeypatch, optional_seconds=5)
    original = deepcopy(path.borehole)
    path.borehole_state = "Unknown"
    value, _ = path.gateway()
    assert value["execution_status"] == "segment_started"
    assert path.borehole == original
    assert [row["state"] for row in path.transport.calls] == ["ON"]
    assert not any(action == "record_borehole_completed" for action, _ in path.backing.rows)
