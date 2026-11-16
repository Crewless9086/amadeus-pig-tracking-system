"""Actual gateway/scheduler and accounting boundaries, entirely offline."""
from contextlib import nullcontext
from datetime import timedelta
import json

import psycopg
import pytest

from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry import rootline_ewelink_oauth as oauth
from modules.telemetry.rootline_failure_diagnostics import exception_failure, sanitize_failure
from tests.test_rootline_active_supervision import (
    NOW, ExecutionStore, Transport, ScheduleStore, gateway, reports,
)

SECRET = "postgresql://secret-user:secret-password@private-host/database SELECT secret_column"


@pytest.mark.parametrize("report_due", [True, False])
@pytest.mark.parametrize("failure_stage", ["locked", "append"])
def test_actual_accounting_failure_survives_oauth_gateway_and_durable_outcome(
        monkeypatch, reports, report_due, failure_stage):
    # The real lock handler and real recorder see the original database error.
    # Neither a connection nor provider request leaves this process.
    class BrokenConnection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return self
        def execute(self, *args, **kwargs):
            raise psycopg.errors.QueryCanceled(SECRET)

    monkeypatch.setattr(budget.RequestBudget, "_connect", lambda self: BrokenConnection())
    monkeypatch.setattr(budget.RequestBudget, "_audit_transaction",
        lambda self, action: nullcontext(BrokenConnection()))
    monkeypatch.setattr(budget.RequestBudget, "_now", lambda *a: NOW)
    def fail_dispatch(self, **kwargs):
        with self._locked():
            pytest.fail("failed lock must never yield")
    if failure_stage == "append":
        def fail_dispatch(self, **kwargs):
            self._append({}, action="synthetic_diagnostic")
    monkeypatch.setattr(budget.RequestBudget, "dispatch", fail_dispatch)
    monkeypatch.setattr(oauth.urllib.request, "urlopen",
        lambda *a, **k: pytest.fail("no provider call permitted"))
    def control(**kwargs):
        return oauth._provider_request("GET", oauth.REGION_HOSTS["eu"] + "/v2/family",
            mode="bearer", token="synthetic", environ={"EWELINK_CLIENT_ID": "synthetic", "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc"})
    schedules = ScheduleStore()
    if not report_due:
        schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
            "next_due_at": (NOW + timedelta(minutes=30)).isoformat()}
    result, status, starts, messages = gateway(ExecutionStore(), Transport(),
        schedules=schedules, execution_cycle=control)
    outcome = schedules.rows[result["schedule_identity"] + ":outcome"]
    expected = {"error_type": "OAuthFailure", "reason": "ewelink_request_accounting_unavailable",
        "accounting_stage": failure_stage, "cause_type": "QueryCanceled"}
    expected.update({"sqlstate": "57014"} if failure_stage == "locked" else {
        "recorder_status": "sam_live_stock_review_event_write_failed", "recorder_http_status": 500})
    assert outcome["irrigation_failure"] == result["irrigation_failure"] == expected
    assert outcome["execution_status"] == "irrigation_control_unproven"
    assert outcome["status"] == "contained" and outcome["report_work_due"] is report_due
    assert status == 202 and starts == messages == []
    assert outcome["hardware_commands"] == 0 and outcome["provider_effects_unknown"] is True
    assert "secret" not in json.dumps(outcome).lower()
    assert "private-host" not in json.dumps(result)


def test_finite_metadata_rejects_exception_messages_dynamic_names_and_extra_fields():
    secret_error = type("secret_password", (RuntimeError,), {})(SECRET)
    secret_error.failure_diagnostics = {"cause_type": "secret_password", "reason": "secret_token",
        "sqlstate": SECRET, "accounting_stage": SECRET, "recorder_status": SECRET,
        "recorder_http_status": "500 secret", "provider_payload": SECRET}
    assert exception_failure(secret_error) == {"error_type": "UnknownError", "cause_type": "UnknownError"}
    assert sanitize_failure({"error_type": [], "cause_type": {}, "reason": [], "sqlstate": []}) == {
        "error_type": "UnknownError", "cause_type": "UnknownError"}


def test_store_action_is_finite_and_optional_deferral_retains_its_type():
    from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable
    assert exception_failure(RootlineExecutionStoreUnavailable("load_current_water_energy_evidence")) == {
        "error_type": "RootlineExecutionStoreUnavailable", "store_action": "load_current_water_energy_evidence"}
    assert exception_failure(RootlineExecutionStoreUnavailable(SECRET)) == {
        "error_type": "RootlineExecutionStoreUnavailable"}
    deferred = budget.OptionalObservationDeferred(NOW)
    assert deferred.next_read_at == NOW and isinstance(deferred, budget.OptionalObservationDeferred)
    assert exception_failure(deferred) == {"error_type": "OptionalObservationDeferred",
        "reason": "ewelink_optional_observation_deferred"}


@pytest.mark.parametrize("report_due", [True, False])
def test_normal_cycle_has_no_failure_metadata_and_unchanged_effects(reports, report_due):
    schedules = ScheduleStore()
    if not report_due:
        schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
            "next_due_at": (NOW + timedelta(minutes=30)).isoformat()}
    result, status, starts, messages = gateway(ExecutionStore(), Transport(), schedules=schedules)
    outcome = schedules.rows[result["schedule_identity"] + ":outcome"]
    assert "irrigation_failure" not in result and "irrigation_failure" not in outcome
    assert outcome["hardware_commands"] == 0 and outcome["provider_effects_unknown"] is False
    assert len(starts) == 1 and outcome["report_work_due"] is report_due
