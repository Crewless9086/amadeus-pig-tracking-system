from datetime import datetime, timezone

import pytest

from modules.charlie.mission_control import (
    build_mission_control_event,
    owner_projection,
    validate_mission_control_event,
)


NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


def test_finding_projects_owner_first_fields_without_claiming_completion():
    event = build_mission_control_event("MISSION-1", {
        "event_type": "finding_recorded",
        "summary": "Provider callback is still rejected.",
        "outcome": "Anton can record a confirmed mortality in Afrikaans.",
        "real_life_state": "contained",
        "first_missing_acceptance_gate": "One provider-confirmed callback.",
        "current_worker": "HERDMASTER repair lane",
        "next_automatic_step": "Repair callback authorization and run CI.",
        "owner_action": "NONE",
        "idempotency_key": "finding-3925-403",
    }, recorded_by="owner-admin:test", now=NOW)
    valid, reason = validate_mission_control_event(event)
    assert valid, reason
    projection = owner_projection({"status": "in_progress", "metadata": {}}, [event])
    assert projection["outcome"].startswith("Anton can")
    assert projection["real_life_state"] == "contained"
    assert projection["owner_action"] == "NONE"
    assert projection["latest_finding"] == "Provider callback is still rejected."


def test_owner_correction_is_append_only_and_targets_prior_event():
    correction = build_mission_control_event("MISSION-1", {
        "event_type": "owner_correction_recorded",
        "summary": "Anton and Charl have parity except CORE and CHARLIE.",
        "corrects_event_id": "CORE-MISSION-CONTROL-OLD",
        "idempotency_key": "owner-correction-1",
    }, recorded_by="owner-admin:test", now=NOW)
    assert correction["corrects_event_id"] == "CORE-MISSION-CONTROL-OLD"
    assert correction["event_id"] != correction["corrects_event_id"]


@pytest.mark.parametrize("payload,reason", [
    ({"event_type": "owner_correction_recorded", "summary": "Correction"}, "corrects_event_id_required"),
    ({"event_type": "acceptance_recorded", "summary": "Accepted", "accepted": True,
      "real_life_state": "technical_progress"}, "invalid_real_life_state"),
    ({"event_type": "acceptance_recorded", "summary": "Accepted",
      "real_life_state": "operational"}, "accepted_boolean_required"),
])
def test_invalid_events_fail_closed(payload, reason):
    with pytest.raises(ValueError, match=reason):
        build_mission_control_event("MISSION-1", payload,
                                    recorded_by="owner-admin:test", now=NOW)


def test_cached_projection_is_derived_without_rewriting_history():
    projection = owner_projection({
        "status": "deployed",
        "metadata": {"mission_control_projection": {
            "outcome": "One owner-visible mission list.",
            "latest_finding": "API loading repaired.",
            "owner_action": "NONE",
        }},
    })
    assert projection["real_life_state"] == "integrated"
    assert projection["latest_finding"] == "API loading repaired."
