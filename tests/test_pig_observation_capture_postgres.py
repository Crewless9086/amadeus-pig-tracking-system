"""Disposable-PostgreSQL proof for the protected Herdmaster capture rails."""

import os
import unittest
import uuid

import psycopg

from modules.pig_weights.pig_observation_capture_service import record_management_intent, record_observation


class PigObservationCapturePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("DATABASE_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("DATABASE_URL not configured for disposable PostgreSQL capture tests")
        cls.pig_id = f"OBS-CI-{uuid.uuid4().hex[:16]}"
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.pigs (pig_id, tag_number, status) values (%s, %s, 'active')",
                    (cls.pig_id, cls.pig_id),
                )

    def test_observation_and_advisory_intent_are_idempotent_and_append_only(self):
        suffix = uuid.uuid4().hex
        observation = {
            "pig_id": self.pig_id, "observed_at": "2026-07-22T10:00:00+02:00",
            "category": "welfare", "severity": "medium", "confidence": 0.9,
            "note": "Disposable database observation.", "evidence_reference": "ci://observation",
            "idempotency_key": f"observation-{suffix}",
        }
        first, first_status = record_observation(observation, "ci-owner-admin")
        replay, replay_status = record_observation(observation, "ci-owner-admin")
        self.assertEqual((first_status, replay_status), (201, 201))
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["observation_event_id"], replay["observation_event_id"])

        intent = {
            "pig_id": self.pig_id, "intended_at": "2026-07-22T10:01:00+02:00",
            "intent_type": "sell_after_weaning", "confidence": 0.8,
            "rationale": "Advisory plan backed by the observation.",
            "observation_event_id": first["observation_event_id"], "idempotency_key": f"intent-{suffix}",
        }
        intent_result, intent_status = record_management_intent(intent, "ci-owner-admin")
        self.assertEqual(intent_status, 201)
        self.assertTrue(intent_result["advisory_only"])
        self.assertFalse(intent_result["executes_action"])

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("update public.pig_observation_events set note = 'mutated' where observation_event_id = %s", (first["observation_event_id"],))
                connection.rollback()
                with self.assertRaises(psycopg.Error):
                    cursor.execute("delete from public.pig_management_intent_events where management_intent_event_id = %s", (intent_result["management_intent_event_id"],))
                connection.rollback()

    def test_cross_pig_observation_reference_is_rejected_and_rls_is_enabled(self):
        suffix = uuid.uuid4().hex
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.pigs (pig_id, tag_number, status) values (%s, %s, 'active')",
                    (f"OBS-CI-OTHER-{suffix[:12]}", f"OBS-CI-OTHER-{suffix[:12]}"),
                )
                cursor.execute(
                    "insert into public.pig_observation_events (observation_event_id, pig_id, observed_at, author_reference, category, severity, note, confidence, source_system, source_reference, idempotency_key) values (%s, %s, now(), 'ci', 'welfare', 'low', 'fact', 1, 'owner', 'ci', %s)",
                    (f"OBS-REF-{suffix}", self.pig_id, f"reference-{suffix}"),
                )
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "insert into public.pig_management_intent_events (management_intent_event_id, pig_id, intended_at, author_reference, intent_type, rationale, confidence, observation_event_id, source_system, source_reference, idempotency_key) values (%s, %s, now(), 'ci', 'hold_for_review', 'wrong pig reference', 1, %s, 'owner', 'ci', %s)",
                        (f"INTENT-BAD-{suffix}", f"OBS-CI-OTHER-{suffix[:12]}", f"OBS-REF-{suffix}", f"bad-reference-{suffix}"),
                    )
                connection.rollback()
                cursor.execute("select relrowsecurity from pg_class where oid = 'public.pig_observation_events'::regclass")
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute("select relrowsecurity from pg_class where oid = 'public.pig_management_intent_events'::regclass")
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute("select roles from pg_policies where schemaname = 'public' and tablename = 'pig_management_intent_events' and policyname = 'pig_management_intent_events_service_role_insert'")
                self.assertEqual(cursor.fetchone()[0], ["service_role"])


if __name__ == "__main__":
    unittest.main()
