from datetime import datetime, timezone
import unittest

from modules.charlie.mission_control import (
    build_mission_control_event,
    canonical_event_equal,
    owner_projection,
    validate_mission_control_event,
)
from modules.charlie.mission_store import append_mission_control_event


NOW = datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)


MISSION_ROW = ("MISSION-1", "in_progress", "test", None, None, "Do work", "Work", "P1",
               "bug fix", "LEVEL 3", "Continue", "", "", {}, NOW, NOW)


class FakeCursor:
 def __init__(self, mission=MISSION_ROW, correction=None, insert_created=True, stored=None):
    self.mission = mission; self.correction = correction; self.insert_created = insert_created
    self.stored = stored; self.pending = None; self.calls = []
 def __enter__(self): return self
 def __exit__(self, *_): return False
 def execute(self, sql, params=None):
    self.calls.append((sql, params or {}))
    if "from public.charlie_missions where mission_id" in sql and "for update" in sql: self.pending = self.mission
    elif "insert into public.charlie_mission_events" in sql: self.pending = (params["event_id"],) if self.insert_created else None
    elif "from public.charlie_mission_events" in sql:
        self.pending = ({"existing": True},) if params["event_id"] != (self.stored or {}).get("event_id") and self.correction else ((self.stored,) if self.stored else None)
    else: self.pending = None
    return self
 def fetchone(self): return self.pending


class FakeConnection:
 def __init__(self, cursor): self.db_cursor = cursor
 def __enter__(self): return self
 def __exit__(self, *_): return False
 def cursor(self): return self.db_cursor


def connector(cursor):
 return lambda _url: FakeConnection(cursor)


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
        ({"event_type": "acceptance_recorded", "summary": "Rejected", "accepted": False,
          "real_life_state": "operational"}, "rejected_acceptance_cannot_advance_real_life_state"),
        ({"event_type": "acceptance_recorded", "summary": "Accepted", "accepted": True,
          "real_life_state": "prepared", "evidence_refs": ["E-1"]}, "accepted_acceptance_requires_outcome_state"),
        ({"event_type": "acceptance_recorded", "summary": "Accepted", "accepted": True,
          "real_life_state": "operational"}, "accepted_acceptance_requires_evidence"),
        ({"event_type": "acceptance_recorded", "summary": "Accepted", "accepted": 1,
          "real_life_state": "operational", "evidence_refs": ["E-1"]}, "accepted_boolean_required"),
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

 def test_acceptance_requires_real_evidence_and_canonical_replay_is_exact(self):
    event = build_mission_control_event("MISSION-1", {
        "event_type": "acceptance_recorded", "summary": "Live loop accepted.",
        "accepted": True, "real_life_state": "operational",
        "evidence_refs": ["provider:42", "canonical:readback-42"],
        "idempotency_key": "acceptance-42",
    }, recorded_by="owner-admin:test", now=NOW)
    self.assertTrue(canonical_event_equal(event, dict(event)))
    self.assertFalse(canonical_event_equal(event, {**event, "summary": "Changed"}))

 def test_store_accepts_same_mission_correction_and_rejects_missing_target(self):
    payload = {"event_type": "owner_correction_recorded", "summary": "Correction",
               "corrects_event_id": "OLD", "idempotency_key": "C-1"}
    ok, status = append_mission_control_event("MISSION-1", payload, recorded_by="owner-admin:test",
        connect_factory=connector(FakeCursor(correction=True)))
    self.assertEqual(status, 201); self.assertTrue(ok["created"])
    blocked, status = append_mission_control_event("MISSION-1", payload, recorded_by="owner-admin:test",
        connect_factory=connector(FakeCursor(correction=False)))
    self.assertEqual(status, 409); self.assertEqual(blocked["status"], "correction_target_not_found_on_mission")

 def test_store_exact_replay_and_conflicting_replay(self):
    payload = {"event_type": "finding_recorded", "summary": "Finding", "idempotency_key": "F-1"}
    stored = build_mission_control_event("MISSION-1", payload, recorded_by="owner-admin:test", now=NOW)
    replay, status = append_mission_control_event("MISSION-1", payload, recorded_by="owner-admin:test",
        connect_factory=connector(FakeCursor(insert_created=False, stored=stored)))
    self.assertEqual(status, 200); self.assertEqual(replay["status"], "exact_replay")
    conflict_payload = {**payload, "summary": "Changed"}
    conflict, status = append_mission_control_event("MISSION-1", conflict_payload, recorded_by="owner-admin:test",
        connect_factory=connector(FakeCursor(insert_created=False, stored=stored)))
    self.assertEqual(status, 409); self.assertEqual(conflict["status"], "mission_control_event_idempotency_conflict")
