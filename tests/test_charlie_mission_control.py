from datetime import datetime, timezone
import unittest

from modules.charlie.mission_control import (
    build_mission_control_event,
    owner_projection,
    validate_mission_control_event,
)


NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


class MissionControlContractTests(unittest.TestCase):
 def test_finding_projects_owner_first_fields_without_claiming_completion(self):
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
    self.assertTrue(valid, reason)
    projection = owner_projection({"status": "in_progress", "metadata": {}}, [event])
    self.assertTrue(projection["outcome"].startswith("Anton can"))
    self.assertEqual(projection["real_life_state"], "contained")
    self.assertEqual(projection["owner_action"], "NONE")
    self.assertEqual(projection["latest_finding"], "Provider callback is still rejected.")


 def test_owner_correction_is_append_only_and_targets_prior_event(self):
    correction = build_mission_control_event("MISSION-1", {
        "event_type": "owner_correction_recorded",
        "summary": "Anton and Charl have parity except CORE and CHARLIE.",
        "corrects_event_id": "CORE-MISSION-CONTROL-OLD",
        "idempotency_key": "owner-correction-1",
    }, recorded_by="owner-admin:test", now=NOW)
    self.assertEqual(correction["corrects_event_id"], "CORE-MISSION-CONTROL-OLD")
    self.assertNotEqual(correction["event_id"], correction["corrects_event_id"])


 def test_invalid_events_fail_closed(self):
    cases = [
        ({"event_type": "owner_correction_recorded", "summary": "Correction"}, "corrects_event_id_required"),
        ({"event_type": "acceptance_recorded", "summary": "Accepted", "accepted": True,
          "real_life_state": "technical_progress"}, "invalid_real_life_state"),
        ({"event_type": "acceptance_recorded", "summary": "Accepted",
          "real_life_state": "operational"}, "accepted_boolean_required"),
    ]
    for payload, reason in cases:
        with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
            build_mission_control_event("MISSION-1", payload,
                                        recorded_by="owner-admin:test", now=NOW)


 def test_cached_projection_is_derived_without_rewriting_history(self):
    projection = owner_projection({
        "status": "deployed",
        "metadata": {"mission_control_projection": {
            "outcome": "One owner-visible mission list.",
            "latest_finding": "API loading repaired.",
            "owner_action": "NONE",
        }},
    })
    self.assertEqual(projection["real_life_state"], "integrated")
    self.assertEqual(projection["latest_finding"], "API loading repaired.")
