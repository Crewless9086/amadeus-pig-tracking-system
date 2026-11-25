"""Optional report history cannot prevent claimed owned-duty supervision."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta

import pytest
from psycopg.errors import QueryCanceled

from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
from tests.test_rootline_active_supervision import (
    NOW, ENV, ExecutionStore, Transport, ScheduleStore, active, gateway, payload,
)


class CadenceUnavailable(ScheduleStore):
    def __init__(self, failure=QueryCanceled):
        super().__init__()
        self.failure = failure
        self.actions = []

    def __call__(self, action, identity, value):
        self.actions.append(action)
        if action == "load_latest_outcome":
            raise self.failure("sensitive database diagnostic must not be retained")
        return super().__call__(action, identity, value)


def forbidden(*args, **kwargs):
    pytest.fail("optional reports or new admission must not run")


def owned_gateway(store, transport, schedules, **kwargs):
    managed_calls = []
    def managed(**options):
        managed_calls.append(options)
        assert options["allow_new_starts"] is False
        assert options["allow_borehole_starts"] is False
        assert options["after_safety"] is None
        return {"success": True, "status": "no_active_managed_device", "hardware_commands": 0}
    options = dict(schedules=schedules, specialist_loader=forbidden,
        daily_plan_generator=forbidden, execution_cycle=forbidden,
        managed_device_cycle=managed,
        source_env={**ENV, "ROOTLINE_BOREHOLE_ENABLED": "true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED": "true",
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true", "ROOTLINE_ESKOM_ENABLED": "true"})
    options.update(kwargs)
    result = gateway(store, transport, **options)
    return result, managed_calls


@pytest.mark.parametrize("failure", [QueryCanceled, TimeoutError, ConnectionError])
def test_real_gateway_owned_off_survives_optional_cadence_timeout(failure):
    schedules = CadenceUnavailable(failure)
    store, transport = ExecutionStore(active()), Transport()
    (result, code, starts, messages), managed = owned_gateway(store, transport, schedules)
    assert code == 200 and result["cadence_unavailable"] is True
    assert result["active_supervision_status"] == "segment_completed"
    assert result["hardware_commands"] == 1 and store.active is None
    assert len(transport.calls) == 1 and transport.calls[0]["state"] == "OFF"
    assert starts == [] and len(managed) == 1
    assert len(messages) == 1  # Existing shutdown notice, no optional report.
    outcome = next(v for k, v in schedules.rows.items() if k.endswith(":outcome"))
    assert outcome["report_work_due"] is False
    assert outcome["cadence_unavailable"] is True
    assert outcome["cadence_error_type"] == failure.__name__
    assert outcome["next_due_at"] is None
    assert outcome["supervision_next_due_at"] == "2026-10-26T16:01:00+02:00"
    assert "sensitive" not in str(outcome)
    assert schedules.actions[:4] == ["load_schedule", "load_latest_outcome", "claim_schedule", "load_schedule"]
    before = deepcopy(store.rows)
    (replay, _, _, replay_messages), managed = owned_gateway(store, transport, schedules)
    assert replay["status"] == "scheduled_reassessment_replayed_noop"
    assert len(transport.calls) == 1 and store.rows == before
    assert replay_messages == managed == []


def test_unavailable_no_active_duties_has_no_commands_or_reports():
    transport = Transport()
    (result, code, starts, messages), _ = owned_gateway(ExecutionStore(), transport, CadenceUnavailable())
    assert code == 200 and result["hardware_commands"] == 0
    assert starts == messages == transport.calls == []


def test_unavailable_priority_injector_runs_before_irrigation_and_keeps_managed_owned_pass():
    order = []
    def short(**kw):
        order.append("injector")
        return {"success": True, "short_auxiliary_handled": True, "hardware_commands": 1}
    def irrigation(**kw):
        order.append("irrigation")
        return {"success": True, "status": "no_active_irrigation", "active_execution_found": False, "hardware_commands": 0}
    (result, _, _, _), managed = owned_gateway(ExecutionStore(), Transport(), CadenceUnavailable(),
        short_auxiliary_supervision_cycle=short, active_supervision_cycle=irrigation)
    assert order == ["injector", "irrigation"] and len(managed) == 1
    assert result["hardware_commands"] == 1


@pytest.mark.parametrize("mode", ["claim_denied", "missing_readback", "wrong_digest", "existing_claim"])
def test_unavailable_unproven_claim_or_readback_has_zero_callbacks(mode):
    original = CadenceUnavailable()
    def store(action, identity, value):
        if action == "claim_schedule" and mode == "claim_denied":
            return {"success": False}
        result = original(action, identity, value)
        if action == "load_schedule" and original.rows:
            if mode == "missing_readback": return None
            if mode == "wrong_digest": return {**result, "invocation_receipt": "wrong"}
        if action == "claim_schedule" and mode == "existing_claim":
            return {"success": True, "created": False}
        return result
    result = run_due_reassessment(payload=payload(), now=NOW, store=store,
        invoke=forbidden, invoke_not_due=forbidden, invoke_owned_duties=forbidden,
        recover_delivery=forbidden)
    assert result["success"] is False and result["hardware_commands"] == 0


@pytest.mark.parametrize("action", ["load_schedule", "claim_schedule"])
def test_nonoptional_store_failure_never_runs_callback(action):
    base = CadenceUnavailable()
    def store(name, identity, value):
        if name == action: raise QueryCanceled("claim unavailable")
        return base(name, identity, value)
    with pytest.raises(QueryCanceled):
        run_due_reassessment(payload=payload(), now=NOW, store=store,
            invoke=forbidden, invoke_not_due=forbidden, invoke_owned_duties=forbidden)


def test_concurrent_same_minute_only_one_owned_off():
    schedules = CadenceUnavailable()
    store, transport = ExecutionStore(active()), Transport()
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _: owned_gateway(store, transport, schedules), range(2)))
    assert len(transport.calls) == 1
    assert sum(len(managed) for result, managed in runs) == 1
    assert sum(result[0]["hardware_commands"] for result, managed in runs) == 1


def test_callback_required_for_unknown_cadence():
    result = run_due_reassessment(payload=payload(), now=NOW, store=CadenceUnavailable(),
        invoke=forbidden, invoke_not_due=forbidden)
    assert result["status"] == "scheduled_reassessment_cadence_unavailable"
    assert result["report_work_due"] is False


def test_unknown_exception_label_is_finite():
    class SecretDiagnostic(Exception): pass
    result = run_due_reassessment(payload=payload(), now=NOW, store=CadenceUnavailable(SecretDiagnostic),
        invoke=forbidden, invoke_owned_duties=lambda: {"success": True})
    assert result["cadence_error_type"] == "other"
    assert result["next_due_at"] is None


def test_owned_effects_not_erased_by_outcome_failure():
    original = CadenceUnavailable()
    def store(action, identity, value):
        if action == "record_outcome": raise RuntimeError("unavailable")
        return original(action, identity, value)
    result = run_due_reassessment(payload=payload(), now=NOW, store=store,
        invoke=forbidden, invoke_owned_duties=lambda: {
            "success": True, "hardware_commands": 1, "effects_unknown": True})
    assert result["status"] == "scheduled_reassessment_outcome_unproven"
    assert result["hardware_commands"] == 1 and result["provider_effects_unknown"] is True
    assert result["cadence_unavailable"] is True and result["report_work_due"] is False


@pytest.mark.parametrize("uncertain", [False, True])
def test_actual_command_mode_shutdown_after_cadence_failure_keeps_truth(uncertain):
    from functools import partial
    from tests.test_rootline_command_mode import start, ENV as COMMAND_ENV
    from modules.telemetry.rootline_execution_runtime import supervise_rootline_active_execution
    _, _, store, transport, clock = start(at=NOW-timedelta(seconds=7201), uncertain=uncertain)
    clock[0] = NOW
    transport.calls.clear()
    (result, _, _, _), _ = owned_gateway(store, transport, CadenceUnavailable(),
        source_env={**ENV, **COMMAND_ENV}, active_supervision_cycle=partial(
            supervise_rootline_active_execution, store=store, transport=transport, clock=lambda: clock[0]))
    assert len(transport.calls) == int(not uncertain)
    assert all(row[2] == "OFF" for row in transport.calls)
    assert result["hardware_commands"] == int(not uncertain)
    terminal = next(row for row in reversed(store.rows) if row["action"] == "record_completed")
    assert terminal["shutdown_verified"] is False
    assert terminal["verified_runtime_seconds"] == 0
    if uncertain:
        from modules.telemetry.rootline_command_acceptance import job_completed
        assert not job_completed(terminal)


def test_actual_managed_runtime_suppresses_optional_evidence_and_new_starts():
    from functools import partial
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    managed_store = ExecutionStore()
    managed_transport = Transport()
    def managed(**kw):
        return run_rootline_managed_device_cycle(evidence={}, store=managed_store,
            transport=managed_transport, canonical_loader=forbidden, evidence_factory=forbidden,
            clock=lambda: NOW, **kw)
    (result, code, _, _), _ = owned_gateway(ExecutionStore(), Transport(), CadenceUnavailable(),
        managed_device_cycle=managed)
    assert code == 200 and result["hardware_commands"] == 0
    assert managed_transport.calls == managed_store.rows == []


def test_cadence_fallback_cannot_bypass_authenticated_gateway():
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    result, code = handle_rootline_reassessment_trigger(payload(), {}, ENV,
        schedule_store=forbidden, active_supervision_cycle=forbidden,
        execution_cycle=forbidden, managed_device_cycle=forbidden)
    assert code == 403


def test_actual_injector_parent_interlock_retained_on_unavailable_cadence(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_coordinator._stop_bound_injection",
        lambda *args: {"status": "auxiliary_emergency_off_unverified", "shutdown_verified": False,
            "hardware_commands": 0})
    transport = Transport(state="ON")
    (result, code, _, _), _ = owned_gateway(ExecutionStore(active()), transport, CadenceUnavailable())
    assert code == 202 and transport.calls == []
    assert result["parent_off_command_withheld"] is True


def test_normal_recovered_cadence_uses_previous_reporting_due_without_fallback_acceleration():
    prior_due = NOW + timedelta(minutes=30)
    schedules = CadenceUnavailable()
    schedules.rows["prior:outcome"] = {"status": "completed", "specialist": "ROOTLINE",
        "next_due_at": prior_due.isoformat()}
    run_due_reassessment(payload=payload(), now=NOW, store=schedules,
        invoke=forbidden, invoke_owned_duties=lambda: {"success": True})
    # Production query deliberately excludes report_work_due false outcomes.
    def recovered(action, identity, value):
        if action == "load_latest_outcome":
            return deepcopy(schedules.rows["prior:outcome"])
        return schedules(action, identity, value)
    later = NOW + timedelta(minutes=1)
    calls = []
    result = run_due_reassessment(payload=payload(due_at=later.isoformat()), now=later,
        store=recovered, invoke=forbidden, invoke_owned_duties=forbidden,
        invoke_not_due=lambda: calls.append("normal control") or {"success": True})
    assert calls == ["normal control"]
    assert result["next_due_at"] == "2026-10-26T16:30:00+02:00"
    assert "cadence_unavailable" not in result


@pytest.mark.parametrize("pending", [False, True])
def test_actual_managed_wrapper_retains_only_existing_grid_reconciliation(monkeypatch, pending):
    from modules.telemetry.rootline_owner_controls import project_owner_controls
    monkeypatch.setattr("modules.telemetry.rootline_owner_controls.load_runtime_owner_controls",
        lambda *_args, **kwargs: project_owner_controls([], now=kwargs.get("now") or NOW))
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_eskom_runtime as grid
    from tests.test_rootline_eskom_runtime import CONFIG, canonical, power, Store as GridStore
    grid_store = GridStore()
    if pending:
        grid_store.rows = [
            {"action": "claim_eskom_before_command", "execution_id": "prior-grid", "desired_state": "OFF"},
            {"action": "record_eskom_command_outcome", "execution_id": "prior-grid", "desired_state": "OFF"}]
    reads = []
    monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state",
        lambda **kw: (reads.append("power") or power(observed_at=NOW.isoformat()), 200))
    monkeypatch.setattr("modules.telemetry.rootline_water_energy_plan._normalize_power", lambda packet: packet)
    monkeypatch.setattr("modules.telemetry.rootline_device_spine.load_device_record",
        lambda *args, **kw: reads.append("grid_binding") or canonical())
    monkeypatch.setattr(grid, "_OBSERVATIONS", grid.EskomObservationCache())
    monkeypatch.setattr(grid, "read_eskom_switch", lambda **kw: reads.append("pending_grid_readback") or {
        "authoritative": True, "device_id": CONFIG["ROOTLINE_ESKOM_DEVICE_ID"], "online": True,
        "switch_code": "switch_1", "state": "OFF", "retrieved_at": NOW.isoformat(), "evidence_id": "prior-off"})
    monkeypatch.setattr(grid, "_send", forbidden)
    owned = ExecutionStore()
    def store(action, value):
        return grid_store(action, value) if "eskom" in action else owned(action, value)
    def managed(**kwargs):
        return runtime.run_rootline_managed_device_reassessment(store=store,
            transport=Transport(), token_store=object(), evidence_loader=forbidden,
            clock=lambda: NOW, **kwargs)
    (result, code, _, _), _ = owned_gateway(ExecutionStore(), Transport(), CadenceUnavailable(),
        source_env={**ENV, **CONFIG}, managed_device_cycle=managed)
    assert code == 200 and result["hardware_commands"] == 0
    assert reads == ["power", "grid_binding"] + (["pending_grid_readback"] if pending else [])
    assert not any(row["action"] == "claim_eskom_before_command" and row["execution_id"] != "prior-grid"
        for row in grid_store.rows)
    assert result["managed_device_result"]["eskom"]["status"] == (
        "eskom_command_reconciled" if pending else "eskom_current_state_retained")
    assert len(grid_store.rows) == (3 if pending else 0)
