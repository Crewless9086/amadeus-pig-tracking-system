import os
import threading
import unittest
import uuid

import psycopg

from modules.charlie.private_store import claim_update, reconcile_incomplete_update, stable_id


class CharlieCallbackPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("DATABASE_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("DATABASE_URL not configured for disposable PostgreSQL callback tests")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    create table if not exists public.charlie_inbound_updates (
                        update_key text primary key,
                        telegram_update_id text not null unique,
                        callback_query_id text,
                        status text not null default 'processing'
                            check (status in ('processing','processed','failed','ignored')),
                        result_json jsonb not null default '{}'::jsonb,
                        received_at timestamptz not null default now(),
                        completed_at timestamptz
                    )
                """)

    def tearDown(self):
        if not hasattr(self, "update_ids"):
            return
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.charlie_inbound_updates where telegram_update_id = any(%s)",
                    (list(self.update_ids),),
                )

    def _update_id(self):
        value = f"test-{uuid.uuid4()}"
        self.update_ids = getattr(self, "update_ids", set())
        self.update_ids.add(value)
        return value

    def test_concurrent_claim_has_one_owner_and_exposes_processing_state(self):
        for _ in range(10):
            update_id = self._update_id()
            barrier = threading.Barrier(2)
            results = []

            def claim():
                barrier.wait()
                results.append(claim_update(update_id, "callback-concurrent", database_url=self.database_url))

            threads = [threading.Thread(target=claim) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertEqual(len(results), 2)
            self.assertTrue(all(payload.get("success") for payload, _ in results), results)
            self.assertEqual(sum(1 for payload, _ in results if payload.get("created")), 1, results)
            duplicate = next(payload for payload, _ in results if not payload["created"])
            self.assertEqual(duplicate["existing_status"], "processing")

    def test_deterministic_update_key_collision_fails_closed(self):
        update_id = self._update_id()
        colliding_id = self._update_id()
        update_key = stable_id("UPDATE", update_id)
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.charlie_inbound_updates(update_key, telegram_update_id) values (%s, %s)",
                    (update_key, colliding_id),
                )

        result, status = claim_update(update_id, "callback-collision", database_url=self.database_url)

        self.assertEqual(status, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "update_key_collision")

    def test_expired_processing_claim_reconciles_to_failed_without_replay(self):
        update_id = self._update_id()
        claimed, status = claim_update(update_id, "callback-expired", database_url=self.database_url)
        self.assertEqual(status, 201)
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "update public.charlie_inbound_updates set received_at=now() - interval '2 minutes' where update_key=%s",
                    (claimed["update_key"],),
                )

        reconciled, reconcile_status = reconcile_incomplete_update(
            claimed["update_key"], minimum_age_seconds=30, database_url=self.database_url
        )
        self.assertEqual(reconcile_status, 200)
        self.assertTrue(reconciled["reconciled"])
        self.assertEqual(reconciled["terminal_status"], "failed")
        self.assertEqual(reconciled["result"]["status"], "completion_unknown_replay_refused")

        duplicate, duplicate_status = claim_update(update_id, "callback-expired", database_url=self.database_url)
        self.assertEqual(duplicate_status, 200)
        self.assertFalse(duplicate["created"])
        self.assertEqual(duplicate["existing_status"], "failed")


if __name__ == "__main__":
    unittest.main()
