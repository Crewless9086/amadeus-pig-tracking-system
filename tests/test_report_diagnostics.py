from datetime import datetime, timezone
import pytest
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.oom_sakkie.automatic_reassessment_scheduler import SCHEDULER_IDENTITY, safe_daily_plan_diagnostics
from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded


def run_case(loader, generator):
    rows = {}; calls = []
    def store(action, identity, payload):
        if action == "load_schedule":
            return rows.get(identity + "-OUTCOME") or rows.get(identity)
        if action == "load_latest_outcome":
            return None
        key = identity if action == "claim_schedule" else identity + "-OUTCOME"
        created = key not in rows
        rows[key] = dict(payload)
        return {"success": True, "created": created}
    def control(**kwargs):
        calls.append("control")
        return {"success": True, "status": "zone_contained", "hardware_commands": 0,
                "telegram_sends": 0, "writes_farm_data": False}
    result, status = handle_rootline_reassessment_trigger(
        {"scheduler_identity": SCHEDULER_IDENTITY, "specialist": "ROOTLINE",
         "due_at": "2026-08-05T10:15:00+02:00", "evidence_cutoff": "2026-08-05T10:14:59+02:00",
         "owner_user_id": "42", "chat_id": "42", "trigger": "declared_time",
         "trigger_id": "DIAGNOSTICS", "trigger_timestamp": "2026-08-05T10:15:00+02:00"},
        {"X-Oom-Sakkie-Telegram-Token": "x"*40},
        {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true", "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42", "ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"},
        schedule_store=store, state_store=lambda *args: None,
        scheduler_now=datetime(2026,8,5,8,15,tzinfo=timezone.utc), specialist_loader=loader,
        daily_plan_generator=generator, execution_cycle=control,
        active_supervision_cycle=lambda **kwargs: {"success": True, "status": "no_active_irrigation",
            "active_execution_found": False, "hardware_commands": 0, "telegram_sends": 0, "writes_farm_data": False},
        family_delivery=lambda *args, **kwargs: calls.append("send"))
    outcome = next(value for key,value in rows.items() if key.endswith("-OUTCOME"))
    assert status == 202 and result["telegram_sends"] == result["hardware_commands"] == 0
    assert result["execution_status"] == "zone_contained" and calls == ["control"]
    return result, outcome


def fresh():
    return {"success": True, "operating_date": "2026-08-05", "evidence_cutoff": "2026-08-05T10:14:00+02:00"}


def fail(exc):
    raise exc


def test_evidence_failure_preserves_reason_before_cutoff_parse_and_skips_generator():
    result,outcome=run_case(lambda: {"success": False, "status": "rootline_manager_observation_recovery_failed"},
        lambda _: pytest.fail("failed evidence must not generate a receipt"))
    assert result["status"] == "scheduled_rootline_plan_evidence_unavailable"
    assert outcome["daily_plan_stage"] == "evidence_load"
    assert outcome["daily_plan_status"] == "rootline_manager_observation_recovery_failed"
    assert result["writes_farm_data"] is None and outcome["report_effects_unknown"] is True


@pytest.mark.parametrize("stage", ["evidence_load", "receipt_generation"])
def test_deadline_is_distinct_without_false_no_write_claim(stage):
    loader=(lambda: fail(RootlineCycleDeadlineExceeded("secret"))) if stage == "evidence_load" else fresh
    result,outcome=run_case(loader,lambda _: fail(RootlineCycleDeadlineExceeded("secret")))
    assert result["status"] == "scheduled_rootline_reporting_deadline_deferred"
    assert outcome["daily_plan_stage"] == stage
    assert outcome["daily_plan_error_type"] == "RootlineCycleDeadlineExceeded"
    assert result["write_state"] == "unknown" and result["writes_farm_data"] is None
    assert "secret" not in str(outcome)


@pytest.mark.parametrize("generator,stage", [(lambda _: fail(RuntimeError("secret")),"receipt_generation"),
    (lambda _: {},"receipt_readback")])
def test_write_failure_stays_ambiguous(generator,stage):
    result,outcome=run_case(fresh,generator)
    assert result["status"] == "scheduled_rootline_daily_plan_persistence_ambiguous"
    assert outcome["daily_plan_stage"] == stage
    assert result["write_state"] == "unknown" and result["writes_farm_data"] is None
    assert outcome["report_effects_unknown"] is True and "secret" not in str(outcome)


def test_diagnostics_are_finite_and_do_not_persist_arbitrary_text():
    value=safe_daily_plan_diagnostics({"daily_plan_stage": "secret", "daily_plan_status": "password",
        "daily_plan_error_type": "custom-sensitive-class", "exception": "secret"})
    assert value == {"daily_plan_stage": "other", "daily_plan_status": "other", "daily_plan_error_type": "other"}


@pytest.mark.parametrize("reason", ["water_energy_plan_append_failed", "canonical_plan_append_failed",
    "canonical_plan_readback_mismatch", "canonical_evidence_unavailable", "owner_identity_required",
    "unsafe_or_invalid_plan", "database_not_configured", "secret-provider-detail"])
def test_real_unavailable_result_retains_only_allowlisted_reason(reason):
    from modules.telemetry.rootline_specialist_result import _unavailable_result
    unavailable = _unavailable_result("2026-08-05", datetime(2026,8,5,8,15,tzinfo=timezone.utc), reason)
    assert "status" not in unavailable
    result,outcome=run_case(lambda: unavailable,lambda _: pytest.fail("unavailable evidence must not generate receipt"))
    expected = "other" if reason == "secret-provider-detail" else reason
    assert result["status"] == "scheduled_rootline_plan_evidence_unavailable"
    assert result["daily_plan_status"] == outcome["daily_plan_status"] == expected
    assert outcome["daily_plan_stage"] == "evidence_load"
    assert outcome["report_effects_unknown"] is True and result["writes_farm_data"] is None
    assert "secret-provider-detail" not in str(result) + str(outcome)
