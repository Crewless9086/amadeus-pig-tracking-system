from datetime import datetime, timezone
from unittest.mock import patch

from modules.telemetry.rootline_owner_status import _project_runtime, get_rootline_owner_status


NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def evidence():
    return {"water_balance": {
        "B12345": {"effective_rainfall_mm": 0.7, "remaining_water_need_mm": 6.3,
                   "complete_through": NOW.isoformat()},
        "C12345": {"effective_rainfall_mm": 0.7, "remaining_water_need_mm": 6.3,
                   "complete_through": NOW.isoformat()},
    }}


def specialist(_evidence, *_args, **_kwargs):
    return {"result_id": "ROOTLINE-RESULT-1", "generation": "GEN-1",
            "operating_date": "2026-08-11", "evidence_cutoff": NOW.isoformat(),
            "overall_status": "Hold", "current_local_weather": {"status": "fresh",
            "observed_at": NOW.isoformat()}, "forecast": {"status": "fresh"},
            "water_observations": {"status": "fresh", "observed_at": NOW.isoformat()},
            "next_reassessment": {"at": "2026-08-11T14:15:00+02:00"},
            "owner_brief": {"why": ["Observed rain supports Hold."]},
            "recommendations": [
                {"subject": "B12345", "status": "Hold", "reason": "Observed rain.",
                 "planned_duration_minutes": 60, "preferred_window": "later", "needs": []},
                {"subject": "C12345", "status": "Do Not Run", "reason": "Not due.",
                 "planned_duration_minutes": None, "preferred_window": None, "needs": []},
            ]}


@patch("modules.telemetry.rootline_owner_status._runtime_and_notification",
       return_value=({}, {}, {"state": "not_sent", "provider_confirmed": False}))
@patch("modules.telemetry.rootline_owner_status.read_latest_zone_water_balances",
       return_value={"status": "Available", "zones": {
           "B12345": {"effective_rainfall_mm": 0.7, "remaining_water_need_mm": 6.3,
                      "complete_through": NOW.isoformat(), "ledger_current": True},
           "C12345": {"effective_rainfall_mm": 0.7, "remaining_water_need_mm": 6.3,
                      "complete_through": NOW.isoformat(), "ledger_current": True}}})
@patch("modules.telemetry.rootline_owner_status.read_canonical_irrigation_history",
       return_value={"zones": {"B12345": {"verified_completed_days": [], "complete_through": NOW.isoformat()},
                               "C12345": {"verified_completed_days": [], "complete_through": NOW.isoformat()}}})
@patch("modules.telemetry.rootline_owner_status._specialist_projection", side_effect=specialist)
@patch("modules.telemetry.rootline_owner_status._canonical_evidence",
       return_value=evidence())
def test_projects_existing_canonical_rails_without_sheet_fallback(*_mocks):
    result, status = get_rootline_owner_status("2026-08-11", "postgresql://fixture", now=NOW)
    assert status == 200
    assert result["source"]["source"] == "supabase"
    assert result["source"]["legacy_google_sheets_used"] is False
    assert result["plan_identity"] == "ROOTLINE-RESULT-1"
    assert result["zones"][0]["decision"] == "Hold"
    assert result["zones"][0]["effective_rainfall_mm"] == 0.7
    assert result["zones"][0]["remaining_supported_water_need_mm"] == 6.3
    assert result["zones"][1]["decision"] == "Not Due"


def test_missing_database_is_precise_and_never_uses_legacy_sheet():
    result, status = get_rootline_owner_status("2026-08-11", "")
    assert status == 503
    assert result["status"] == "database_not_configured"
    assert result["source"]["legacy_google_sheets_used"] is False


def test_active_runtime_is_selected_without_terminal_and_notification_is_correlated():
    older = NOW.replace(hour=10)
    events = [
        (NOW, {"execution_id": "OLD", "action": "record_notification_delivery",
               "notification_state": "Completed", "delivery_confirmed": True}),
        (NOW, {"execution_id": "ACTIVE", "action": "record_notification_delivery",
               "notification_state": "Started", "delivery_confirmed": True}),
        (older, {"execution_id": "ACTIVE", "action": "claim_before_on", "zone_id": "B12345"}),
        (older, {"execution_id": "OLD", "action": "record_completed", "shutdown_verified": True}),
    ]
    active, outcome, notification = _project_runtime(events)
    assert active["execution_id"] == "ACTIVE" and active["state"] == "claimed"
    assert outcome["execution_id"] == "OLD"
    assert notification["state"] == "Started" and notification["provider_confirmed"] is True


def test_consumer_query_requires_exact_persisted_operating_date():
    import inspect
    from modules.telemetry.rootline_owner_status import _canonical_evidence
    from modules.oom_sakkie.rootline_reassessment_lifecycle import reassess_rootline
    assert "->>'operating_date'=%s" in inspect.getsource(_canonical_evidence)
    assert '"operating_date": str(current.get("operating_date")' in inspect.getsource(reassess_rootline)


def test_run_with_persisted_technical_blocker_projects_run_blocked():
    from modules.telemetry.rootline_owner_status import (
        _blocker, _operational_state, _specialist_projection,
    )
    projected = _specialist_projection({"operating_date":"2026-08-11","weather":{},
        "reassessment":{"result_id":"R1","zones":[{"zone_id":"B12345",
            "decision":"Run","reason":"Water is due.",
            "eligibility_blocker":"controller_safety_not_dispatchable"}]}},
        "2026-08-11", NOW)
    b = next(row for row in projected["recommendations"] if row["subject"] == "B12345")
    blocker = _blocker(b)
    assert b["status"] == "Recommend"
    assert blocker == "controller_safety_not_dispatchable"
    assert _operational_state("Run", blocker, {}) == "Run — blocked"
