"""Fault history is shared only inside one active supervision pass."""
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
from tests.test_rootline_continuous_borehole import NOW, eligibility, Transport, snapshot
from tests.test_rootline_borehole_commissioning import BoreholeStore


class Case:
    def __init__(self, monkeypatch):
        self.rows = []; self.queries = 0; self.conditions = []; self.weather_reads = 0
        self.fault_error = False; self.condition_error = False; self.rain = 0
        self.now = NOW; self.soc = 99
        case = self
        class Store(BoreholeStore):
            def __call__(self, action, body):
                if action == "load_active_auxiliaries": return []
                if action == "assess_borehole_conditions":
                    case.conditions.append(deepcopy(body))
                    if case.condition_error: raise RuntimeError("conditions unavailable")
                    raining = body["weather_snapshot"]["weather_current"]["current"]["rain_rate_mm_h"] > 0
                    return {"success": True, "stop_required": raining or body["protection_safe"] is False,
                        "reason": "observed_rain" if raining else "explicit_protection_or_manual_stop"}
                return super().__call__(action, body)
        self.store = Store(); self.transport = Transport()
        advance_borehole_execution(eligibility=eligibility(), store=self.store,
            transport=self.transport, now=NOW, clock=lambda: NOW)
        self.transport.commands.clear()
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, sql):
                assert "rootline_operational_intake" in sql
                case.queries += 1
                if case.fault_error: raise RuntimeError("fault history unavailable")
                return self
            def fetchall(self): return deepcopy(case.rows)
        monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
            lambda **_: Connection())
        monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state",
            lambda **_: ({"success": True, "current": {"solar_power_w": 768,
                "battery_soc_pct": self.soc, "grid_power_w": 0, "battery_power_w": 0,
                "load_power_w": 100}, "source": {"last_reading_at": NOW.isoformat()}}, 200))
        def weather(*_, **__):
            self.weather_reads += 1
            return snapshot(self.now, rate=self.rain), 200
        monkeypatch.setattr("modules.telemetry.weather_service.get_weather_control_snapshot", weather)

    def fault(self, key, value):
        self.rows.append(({"borehole_interlocks": {key: value,
            "observed_at": self.now.isoformat(), "provider_message_id": "manual-1"}},))

    def run(self, callback=None, planning=None):
        def load(**_):
            if planning: planning()
            return {}, NOW.date().isoformat(), self.now
        return runtime.run_rootline_managed_device_reassessment(
            environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED": "true"} if planning else {},
            database_url="offline-test", store=self.store, token_store=object(),
            transport=self.transport, now=self.now, clock=lambda: self.now,
            allow_new_starts=bool(planning), allow_borehole_starts=False,
            evidence_loader=load, after_safety=callback)


def test_one_query_per_pass_and_fresh_after_callback_and_planning(monkeypatch):
    case = Case(monkeypatch)
    result = case.run(callback=lambda _: None, planning=lambda: None)
    assert case.queries == len(case.conditions) == case.weather_reads == 3
    assert all(row["protection_evidence"]["safe"] is True for row in case.conditions)
    assert case.transport.commands == [] and result["hardware_commands"] == 0
    case.run()
    assert case.queries == 4  # no reuse across a later scheduler invocation


@pytest.mark.parametrize("boundary", ["initial", "callback", "planning"])
@pytest.mark.parametrize("key,value", [("manual_off_active", True), ("manual_isolation_active", True),
    ("dry_run_safe", False), ("low_water_clear", False), ("supply_pressure_safe", False),
    ("full_tank_cutoff_fault", True)])
def test_negative_evidence_still_stops_at_each_boundary(monkeypatch, boundary, key, value):
    case = Case(monkeypatch)
    change = lambda: case.fault(key, value)
    if boundary == "initial": change()
    case.run(callback=(lambda _: change()) if boundary == "callback" else None,
        planning=change if boundary == "planning" else None)
    assert [row["state"] for row in case.transport.commands] == ["OFF"]
    assert case.conditions[-1]["protection_evidence"]["facts"][key] is value
    assert case.conditions[-1]["protection_safe"] is False
    assert case.queries == len(case.conditions) == (1 if boundary == "initial" else 2)


def test_negative_fault_not_lost_when_conditions_fail(monkeypatch):
    case = Case(monkeypatch); case.fault("manual_off_active", True); case.condition_error = True
    case.run()
    assert [row["state"] for row in case.transport.commands] == ["OFF"]
    assert case.queries == 1


def test_fault_read_failure_remains_pending_and_later_pass_retries(monkeypatch):
    case = Case(monkeypatch); case.fault_error = True
    result = case.run()
    assert result["supervision_evidence_pending"] is True
    assert case.transport.commands == []
    case.fault_error = False; case.fault("manual_isolation_active", True)
    case.run()
    assert [row["state"] for row in case.transport.commands] == ["OFF"]


def test_changed_weather_is_read_after_callback(monkeypatch):
    case = Case(monkeypatch)
    case.run(callback=lambda _: setattr(case, "rain", 1))
    assert case.weather_reads == 2 and case.queries == 2
    assert [row["state"] for row in case.transport.commands] == ["OFF"]


def test_energy_backup_rule_and_current_age_are_unchanged(monkeypatch):
    case = Case(monkeypatch)
    result = case.run(callback=lambda _: setattr(case, "now", NOW + timedelta(minutes=16)))
    assert case.transport.commands == []
    assert any(row.get("supervision_evidence_pending") for row in result.get("outcomes", [result]))
    assert case.queries == 2


@pytest.mark.parametrize("safe", [True, False, None])
def test_boolean_only_reader_remains_compatible(monkeypatch, safe):
    case = Case(monkeypatch); calls = []
    result = managed.run_rootline_managed_device_cycle(evidence={}, transport=case.transport,
        store=case.store, environ={}, now=NOW, clock=lambda: NOW, allow_new_starts=False,
        energy_reader=lambda: {"continuous_borehole_fresh": True, "continuous_borehole_eligible": True},
        borehole_safety_reader=lambda: safe,
        borehole_conditions_reader=lambda: calls.append(True) or {"success": True})
    assert calls == [True]
    assert [row["state"] for row in case.transport.commands] == (["OFF"] if safe is False else [])
    if safe is None: assert result["supervision_evidence_pending"] is True


def test_callback_exception_still_rereads_and_stops(monkeypatch):
    case = Case(monkeypatch)
    def callback(_):
        case.fault("manual_off_active", True)
        raise RuntimeError("callback failed")
    with pytest.raises(RuntimeError, match="callback failed"):
        case.run(callback=callback)
    assert case.queries == 2
    assert [row["state"] for row in case.transport.commands] == ["OFF"]


def test_planning_exception_still_rereads_and_stops(monkeypatch):
    case = Case(monkeypatch)
    def planning():
        case.fault("manual_isolation_active", True)
        raise RuntimeError("planning failed")
    case.run(planning=planning)
    assert case.queries == 2
    assert [row["state"] for row in case.transport.commands] == ["OFF"]
