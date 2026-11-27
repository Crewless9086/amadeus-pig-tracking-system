"""Finite, invocation-local observations; never a control or deadline guard.

Stages are inclusive and may nest. Their durations must not be added together.
The existing scheduler outcome is the only persistence path.
"""
from contextlib import contextmanager
import math
import time

STAGES = frozenset({
    "supervision", "short_auxiliary_supervision", "active_supervision",
    "managed_owned_inventory", "managed_borehole_energy", "managed_borehole_protection",
    "managed_borehole_owner_stop", "managed_borehole_conditions", "managed_borehole_advance",
    "managed_borehole_observation", "managed_borehole_facts", "managed_borehole_weather",
    "irrigation_admission", "managed_control", "managed_evidence", "daily_program",
    "plan_manager_recovery", "plan_evidence", "plan_programme", "plan_revision", "plan_enrichment",
    "current_plan", "provider_notifications", "input_notifications",
    "equipment_notifications", "manager_reports", "parent_recheck",
    "managed_source_reads", "managed_grid", "controller_connectivity", "controller_notifications",
})
MAX_MS = 86_400_000


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _milliseconds(seconds):
    if seconds >= MAX_MS / 1000:
        return MAX_MS
    return max(0, int(seconds * 1000))


class StageTimings:
    def __init__(self):
        self.rows = {}
        self.started = self._now()

    @staticmethod
    def _now():
        try:
            value = time.monotonic()
            return value if _finite(value) else None
        except Exception:
            return None

    @staticmethod
    def _remaining(now):
        try:
            from modules.telemetry.rootline_cycle_budget import work_deadline
            deadline = work_deadline()
            return (_milliseconds(deadline - now)
                if now is not None and _finite(deadline) else None)
        except Exception:
            return None

    @contextmanager
    def stage(self, name):
        started = self._now()
        before = self._remaining(started)
        try:
            yield
        finally:
            # Diagnostic failure must never replace a control result/exception.
            try:
                ended = self._now()
                if name in STAGES and started is not None and ended is not None and ended >= started:
                    old = self.rows.get(name, {})
                    self.rows[name] = {
                        "calls": min(1024, old.get("calls", 0) + 1),
                        "elapsed_ms": min(MAX_MS, old.get("elapsed_ms", 0) + _milliseconds(ended - started)),
                        "last_start_remaining_ms": before,
                        "last_end_remaining_ms": self._remaining(ended),
                    }
            except Exception:
                pass

    def call(self, name, function, *args, **kwargs):
        with self.stage(name):
            return function(*args, **kwargs)

    def snapshot(self):
        now = self._now()
        rows = {}
        for name in sorted(STAGES):
            value = self.rows.get(name)
            if not isinstance(value, dict):
                continue
            if not (type(value.get("calls")) is int and 0 < value["calls"] <= 1024
                    and type(value.get("elapsed_ms")) is int and 0 <= value["elapsed_ms"] <= MAX_MS):
                continue
            rows[name] = {key: value[key] for key in ("calls", "elapsed_ms")}
            for key in ("last_start_remaining_ms", "last_end_remaining_ms"):
                item = value.get(key)
                rows[name][key] = item if type(item) is int and 0 <= item <= MAX_MS else None
        return {"version": "rootline_stage_timings.v1", "duration_scope": "inclusive_not_additive",
            "captured_before": "scheduler_outcome_persistence",
            "elapsed_ms": (_milliseconds(now - self.started)
                if now is not None and self.started is not None and now >= self.started else None),
            "stages": rows}
