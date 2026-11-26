"""Timing observations preserve control traces and the existing outcome write."""
from contextlib import contextmanager
import pytest
from modules.telemetry import rootline_stage_timings as timing
from modules.telemetry import rootline_cycle_budget as budget
from tests.test_rootline_active_supervision import (
    reports, gateway, ExecutionStore, Transport, ScheduleStore, active,
)


def test_nested_stages_are_inclusive_and_observe_without_consuming_budget(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(timing.time, "monotonic", lambda: clock[0])
    sample = timing.StageTimings()
    with budget.cycle_budget(140):
        with sample.stage("supervision"):
            clock[0] += 2
            with sample.stage("managed_control"):
                clock[0] += 3
        assert budget.work_deadline() == 140
    result = sample.snapshot()
    assert result["duration_scope"] == "inclusive_not_additive"
    assert result["elapsed_ms"] == 5000
    assert result["stages"]["supervision"] == {
        "calls": 1, "elapsed_ms": 5000,
        "last_start_remaining_ms": 40000, "last_end_remaining_ms": 35000}
    assert result["stages"]["managed_control"]["elapsed_ms"] == 3000


@pytest.mark.parametrize("bad", [None, True, float("nan"), float("inf"), "secret"])
def test_bad_clock_never_changes_operation_or_exception(monkeypatch, bad):
    monkeypatch.setattr(timing.time, "monotonic", lambda: bad)
    sample = timing.StageTimings()
    expected = ValueError("original failure")
    with pytest.raises(ValueError) as caught:
        with sample.stage("managed_control"):
            raise expected
    assert caught.value is expected
    assert sample.snapshot()["stages"] == {}


def test_snapshot_excludes_untrusted_fields_and_reversed_clock(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(timing.time, "monotonic", lambda: clock[0])
    sample = timing.StageTimings()
    with sample.stage("managed_control"):
        clock[0] = 9
    sample.rows["secret"] = {"payload": "not retained"}
    sample.rows["current_plan"] = {"calls": True, "elapsed_ms": 10}
    assert sample.snapshot()["stages"] == {}
    assert sample.snapshot()["elapsed_ms"] is None


@pytest.mark.parametrize("failure", [False, True])
def test_composed_gateway_persists_partial_timings_without_effect_changes(monkeypatch, reports, failure):
    clock = [1000.0]
    monkeypatch.setattr(timing.time, "monotonic", lambda: clock[0])
    real = timing.StageTimings
    def run(enabled):
        clock[0] = 1000.0
        class InertTimings:
            @contextmanager
            def stage(self, name):
                yield
            def call(self, name, function, *args, **kwargs):
                return function(*args, **kwargs)
            def snapshot(self):
                return {}
        monkeypatch.setattr(timing, "StageTimings", real if enabled else InertTimings)
        schedules = ScheduleStore(); store = ExecutionStore(active()); transport = Transport()
        trace = []
        def managed(**kwargs):
            trace.append("managed")
            clock[0] += 10
            return {"success": True, "status": "no_eligible_managed_device_task", "hardware_commands": 0}
        def equipment(**kwargs):
            trace.append("equipment")
            clock[0] += 2
            if failure:
                raise RuntimeError("no diagnostic payload")
            return {"success": True, "status": "rootline_transition_notifications_observed", "telegram_sends": 0}
        value, code, starts, messages = gateway(store, transport, schedules=schedules,
            managed_device_cycle=managed, equipment_notification_cycle=equipment)
        outcomes = [row for key, row in schedules.rows.items() if key.endswith(":outcome")]
        assert len(outcomes) == 1
        outcome = dict(outcomes[0]); metrics = outcome.pop("stage_timings")
        def stable(item):
            if callable(item):
                return item.__qualname__
            if isinstance(item, dict):
                return {key: stable(child) for key, child in item.items()}
            if isinstance(item, (list, tuple)):
                return [stable(child) for child in item]
            return item
        return stable((value, code, starts, messages, transport.calls, trace, outcome)), metrics
    observed, metrics = run(True)
    baseline, unused = run(False)
    assert observed == baseline
    assert metrics["stages"]["managed_control"]["elapsed_ms"] == 10000
    assert metrics["stages"]["equipment_notifications"]["elapsed_ms"] == 2000
    assert metrics["captured_before"] == "scheduler_outcome_persistence"
    assert observed[0]["hardware_commands"] == 1
    assert "no diagnostic payload" not in str(metrics)


def test_extreme_clock_is_bounded(monkeypatch):
    clock = [-1e308]
    monkeypatch.setattr(timing.time, "monotonic", lambda: clock[0])
    sample = timing.StageTimings()
    with sample.stage("managed_control"):
        clock[0] = 1e308
    assert sample.snapshot()["elapsed_ms"] == timing.MAX_MS
    assert sample.snapshot()["stages"]["managed_control"]["elapsed_ms"] == timing.MAX_MS


def test_diagnostic_snapshot_failure_does_not_block_existing_outcome(monkeypatch, reports):
    def fail(self):
        raise RuntimeError("diagnostic only")
    monkeypatch.setattr(timing.StageTimings, "snapshot", fail)
    schedules = ScheduleStore()
    value, _, _, _ = gateway(ExecutionStore(active()), Transport(), schedules=schedules)
    rows = [row for key, row in schedules.rows.items() if key.endswith(":outcome")]
    assert len(rows) == 1 and "stage_timings" not in rows[0]
    assert value["hardware_commands"] == rows[0]["hardware_commands"] == 1
    assert rows[0]["active_supervision_status"] == "segment_completed"
