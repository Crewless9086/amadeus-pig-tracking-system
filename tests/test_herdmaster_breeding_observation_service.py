import unittest
from datetime import datetime, timedelta, timezone

from modules.pig_weights.herdmaster_breeding_observation_service import (
    list_observations,
    observation_event_id,
    preview_observation,
    record_observation,
    validate_observation,
)


def payload(**changes):
    value = {
        "pig_id": "SOW-1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "body_condition_score": 3,
        "visible_build": "even",
        "feet_legs_movement": "no_visible_concern",
        "visible_injury": "none_observed",
        "standing_heat": "not_observed",
        "temperament": "calm",
        "suitability_concern": "none_observed",
        "factual_note": "Observed standing and walking in the pen.",
        "follow_up": "Observe again tomorrow.",
        "idempotency_key": "OBS-IDEM-1",
        "owner_id": "browser-spoof",
    }
    value.update(changes)
    return value


def attention(**changes):
    value = {
        "pig_id": "SOW-1",
        "current_state": "Needs observation",
        "filter_state": "Needs observation",
        "recommended_human_action": "observe for standing heat",
        "missing_facts": ["body condition", "current heat observation"],
        "conflicting_facts": [],
    }
    value.update(changes)
    return value


def hypothetical_attention(**changes):
    value = attention(
        current_state="Ready for review",
        filter_state="Ready for review",
        recommended_human_action="confirm body condition manually",
        missing_facts=[],
    )
    value.update(changes)
    return value


class Cursor:
    def __init__(self, existing=None, current=True, supersedes=True):
        self.existing = existing
        self.current = current
        self.supersedes = supersedes
        self.query = ""
        self.inserted = 0

    def execute(self, query, params=()):
        self.query = " ".join(str(query).split()).lower()
        self.params = params
        if self.query.startswith("insert into public.pig_observation_events"):
            self.inserted += 1

    def fetchone(self):
        if (
            "from public.pigs pig" in self.query
            and "public.current_canonical_pigs" in self.query
        ):
            return ("SOW-1",) if self.current else None
        if "where idempotency_key" in self.query:
            return self.existing
        if "where prior.observation_event_id" in self.query:
            return (1,) if self.supersedes else None
        if "returning observation_event_id" in self.query:
            return ("HERD-OBS-1",)
        return None

    def __enter__(self): return self
    def __exit__(self, *_args): return False


class Connection:
    def __init__(self, cursor): self.value = cursor
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class HistoryCursor(Cursor):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows
    def fetchall(self): return self.rows


class BreedingObservationServiceTests(unittest.TestCase):
    def test_preview_and_record_share_deterministic_event_identity(self):
        self.assertEqual(
            observation_event_id("same-idempotency"),
            observation_event_id("same-idempotency"),
        )
        self.assertTrue(
            observation_event_id("same-idempotency").startswith("HERD-OBS-")
        )

    def call(self, data=None, actor="owner-admin:stable", cursor=None):
        cursor = cursor or Cursor()
        result = record_observation(
            data or payload(),
            actor_id=actor,
            connect_factory=lambda _url: Connection(cursor),
        )
        return result, cursor

    def test_records_one_factual_append_only_observation_with_zero_authority(self):
        (result, status), cursor = self.call()
        self.assertEqual((status, result["status"]), (201, "observation_recorded"))
        self.assertEqual(cursor.inserted, 1)
        self.assertNotIn("owner_id", result)
        self.assertTrue(result["append_only"])
        self.assertTrue(result["advisory_only"])
        self.assertTrue(all(result[key] is False for key in (
            "creates_mating", "asserts_pregnancy", "asserts_heat",
            "changes_medical", "changes_lifecycle", "changes_purpose",
            "changes_movement", "changes_availability", "changes_retirement",
            "schedules_core_work", "contacts_customer", "changes_farm_state",
        )))

    def test_missing_principal_and_non_current_female_fail_before_insert(self):
        (result, status), cursor = self.call(actor="")
        self.assertEqual((status, result["status"]), (403, "owner_identity_required"))
        self.assertEqual(cursor.inserted, 0)
        (result, status), cursor = self.call(cursor=Cursor(current=False))
        self.assertEqual((status, result["status"]), (409, "current_sow_or_gilt_required"))
        self.assertEqual(cursor.inserted, 0)

    def test_replay_is_withheld_and_changed_evidence_conflicts(self):
        data = payload()
        (_, _), first = self.call(data)
        actor = "owner-admin:stable"
        clean, _ = validate_observation(data)
        existing = (
            "HERD-OBS-1", clean["pig_id"], clean["observed_at"], actor,
            clean["factual_note"], clean["measurements"], None,
        )
        (result, status), cursor = self.call(data, cursor=Cursor(existing=existing))
        self.assertEqual((status, result["status"]), (200, "observation_replayed_withheld"))
        self.assertEqual(cursor.inserted, 0)
        changed = {**data, "factual_note": "Different evidence."}
        (result, status), cursor = self.call(changed, cursor=Cursor(existing=existing))
        self.assertEqual((status, result["status"]), (409, "observation_idempotency_conflict"))
        self.assertEqual(cursor.inserted, 0)

    def test_correction_requires_same_pig_prior_event(self):
        data = payload(supersedes_observation_event_id="OBS-OLD")
        (result, status), cursor = self.call(data, cursor=Cursor(supersedes=False))
        self.assertEqual((status, result["status"]), (409, "invalid_supersession"))
        self.assertEqual(cursor.inserted, 0)

    def test_backend_rejects_oversized_immutable_evidence(self):
        for field, value in (
            ("pig_id", "P" * 129),
            ("idempotency_key", "I" * 201),
            ("factual_note", "N" * 1001),
            ("follow_up", "F" * 501),
        ):
            clean, error = validate_observation(payload(**{field: value}))
            self.assertIsNone(clean, field)
            self.assertEqual(error, "observation_evidence_too_long", field)

    def test_unknown_or_missing_evidence_never_becomes_affirmative(self):
        clean, error = validate_observation(payload(
            body_condition_score=None,
            visible_build="not_recorded",
            feet_legs_movement="not_recorded",
            visible_injury="not_recorded",
            standing_heat="not_recorded",
            temperament="not_recorded",
            suitability_concern="not_recorded",
        ))
        self.assertIsNone(clean)
        self.assertEqual(error, "factual_measurement_required")
        result, status = preview_observation(
            payload(body_condition_score=None, standing_heat="not_observed"),
            authoritative_attention=attention(),
            hypothetical_attention=attention(),
        )
        self.assertEqual(status, 200)
        self.assertFalse(result["system_recommendation"]["attention_recalculation_required"])
        self.assertIn(
            "body condition",
            result["system_recommendation"]["advisory_change"][
                "after_if_recorded"
            ]["missing_facts"],
        )

    def test_preview_separates_fact_interpretation_and_recommendation(self):
        result, status = preview_observation(
            payload(standing_heat="observed"),
            authoritative_attention=attention(),
            hypothetical_attention=hypothetical_attention(),
        )
        self.assertEqual(status, 200)
        self.assertIn("observed", result)
        self.assertEqual(result["owner_interpretation"], "Not recorded by this operation.")
        self.assertTrue(any(
            "standing-heat" in effect
            for effect in result["system_recommendation"]["effect"]
        ))
        self.assertTrue(result["system_recommendation"]["proposal_only"])

    def test_preview_uses_phase1_fact_specific_freshness_boundaries(self):
        now = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)
        result, _ = preview_observation(payload(
            observed_at=(now - timedelta(days=10)).isoformat(),
            standing_heat="observed",
        ), authoritative_attention=attention(),
            hypothetical_attention=attention(), now=now)
        self.assertEqual(result["system_recommendation"]["freshness"], {
            "body_condition": "Fresh",
            "standing_heat": "Stale",
        })

    def test_preview_shows_authoritative_before_and_after_advice(self):
        result, status = preview_observation(
            payload(standing_heat="observed"),
            authoritative_attention=attention(),
            hypothetical_attention=hypothetical_attention(),
        )
        self.assertEqual(status, 200)
        change = result["system_recommendation"]["advisory_change"]
        self.assertEqual(change["before"]["state"], "Needs observation")
        self.assertEqual(change["after_if_recorded"]["state"], "Ready for review")
        self.assertEqual(
            change["after_if_recorded"]["recommended_human_action"],
            "confirm body condition manually",
        )

    def test_preview_fails_closed_without_authoritative_attention(self):
        result, status = preview_observation(payload())
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "current_attention_evidence_unavailable")

    def test_history_is_owner_only_projection_without_observer_identity(self):
        now = datetime.now(timezone.utc)
        rows = [(
            "OBS-1", now, now, "other", "informational", "Observed walking.",
            {"contract_version": "herdmaster_breeding_observation_v1"},
            "digest-only", None,
        )]
        result, status = list_observations(
            "SOW-1",
            connect_factory=lambda _url: Connection(HistoryCursor(rows)),
            now=now,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(result["history"]), 1)
        self.assertNotIn("observer_reference", result["history"][0])
        self.assertNotIn("customer_name", str(result).lower())
        self.assertEqual(
            result["history"][0]["freshness"]["standing_heat"], "Unknown"
        )
        self.assertFalse(result["contacts_customer"])


if __name__ == "__main__":
    unittest.main()
