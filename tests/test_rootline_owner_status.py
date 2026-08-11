from datetime import datetime, timezone
from unittest.mock import patch

from modules.telemetry.rootline_owner_status import get_rootline_owner_status


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
       return_value=({}, {"state": "not_sent", "provider_confirmed": False}))
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
