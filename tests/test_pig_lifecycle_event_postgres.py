"""Opt-in disposable-Postgres verification for the lifecycle audit migration.

This test only connects when CHARLIE_DISPOSABLE_POSTGRES_URL is explicitly
provided by isolated CI; it never reads DATABASE_URL.
"""
import os
import unittest
import uuid
from pathlib import Path

import psycopg


class PigLifecycleEventPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured for disposable lifecycle migration tests")

        migrations = Path("supabase/migrations")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute((migrations / "202605210001_foundation_migration_log.sql").read_text(encoding="utf-8"))
                cursor.execute("create table if not exists public.pigs (pig_id text primary key)")
                cursor.execute((migrations / "202607210001_create_pig_lifecycle_events.sql").read_text(encoding="utf-8"))

    def setUp(self):
        self.test_id = uuid.uuid4().hex
        self.pig_id = f"PIG-{self.test_id}-1"
        self.other_pig_id = f"PIG-{self.test_id}-2"
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.pigs (pig_id) values (%s), (%s)", (self.pig_id, self.other_pig_id))

    def _insert_event(self, cursor, event_id, pig_id=None, **overrides):
        event = {
            "lifecycle_event_type": "entered_farm",
            "effective_at": "2026-07-21T09:00:00+00:00",
            "recorded_at": "2026-07-21T10:00:00+00:00",
            "actor_reference": "owner-1",
            "source_system": "owner",
            "source_reference": "lifecycle-test",
            "idempotency_key": f"key-{self.test_id}-{event_id}",
            "supersedes_lifecycle_event_id": None,
        }
        event.update(overrides)
        cursor.execute(
            """
            insert into public.pig_lifecycle_events (
                lifecycle_event_id, pig_id, lifecycle_event_type, effective_at, recorded_at,
                actor_reference, source_system, source_reference, idempotency_key,
                supersedes_lifecycle_event_id
            ) values (
                %(event_id)s, %(pig_id)s, %(lifecycle_event_type)s, %(effective_at)s, %(recorded_at)s,
                %(actor_reference)s, %(source_system)s, %(source_reference)s, %(idempotency_key)s,
                %(supersedes_lifecycle_event_id)s
            )
            """,
            {"event_id": f"{self.test_id}-{event_id}", "pig_id": pig_id or self.pig_id, **event},
        )

    def test_valid_event_and_same_pig_correction_are_accepted(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._insert_event(cursor, "event-1")
                self._insert_event(
                    cursor,
                    "event-2",
                    lifecycle_event_type="lifecycle_correction",
                    supersedes_lifecycle_event_id=f"{self.test_id}-event-1",
                )
                cursor.execute("select count(*) from public.pig_lifecycle_events where pig_id = %s", (self.pig_id,))
                self.assertEqual(cursor.fetchone()[0], 2)

    def test_invalid_events_and_mutation_are_rejected(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._insert_event(cursor, "event-base")
                connection.commit()
                cases = [
                    {"event_id": "missing-provenance", "actor_reference": ""},
                    {"event_id": "future-effective", "effective_at": "2026-07-21T11:00:00+00:00"},
                    {"event_id": "ordinary-supersession", "supersedes_lifecycle_event_id": f"{self.test_id}-event-base"},
                    {"event_id": "missing-correction-target", "lifecycle_event_type": "lifecycle_correction"},
                    {
                        "event_id": "cross-pig-correction",
                        "pig_id": self.other_pig_id,
                        "lifecycle_event_type": "lifecycle_correction",
                        "supersedes_lifecycle_event_id": f"{self.test_id}-event-base",
                    },
                ]
                for case in cases:
                    with self.subTest(case=case["event_id"]), self.assertRaises(psycopg.Error):
                        self._insert_event(cursor, **case)
                    connection.rollback()

                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "update public.pig_lifecycle_events set event_note = 'mutated' where lifecycle_event_id = %s",
                        (f"{self.test_id}-event-base",),
                    )
                connection.rollback()
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "delete from public.pig_lifecycle_events where lifecycle_event_id = %s",
                        (f"{self.test_id}-event-base",),
                    )


if __name__ == "__main__":
    unittest.main()
