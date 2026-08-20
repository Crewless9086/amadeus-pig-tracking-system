"""Opt-in disposable-PostgreSQL proof for welfare-case lifecycle integrity.

Only CHARLIE_DISPOSABLE_POSTGRES_URL is accepted; production DATABASE_URL is
deliberately ignored.
"""
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg


class PigWelfareCasePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        migrations = Path("supabase/migrations")
        with psycopg.connect(cls.database_url) as connection:
            connection.execute(
                (migrations / "202605210001_foundation_migration_log.sql").read_text(encoding="utf-8")
            )
            connection.execute("create table if not exists public.pigs (pig_id text primary key)")
            connection.execute(
                (migrations / "202608200002_create_pig_welfare_case_lifecycle.sql").read_text(encoding="utf-8")
            )

    def setUp(self):
        self.run_id = uuid.uuid4().hex
        self.pig_id = f"PIG-WELFARE-{self.run_id}"
        with psycopg.connect(self.database_url) as connection:
            connection.execute("insert into public.pigs(pig_id) values (%s)", (self.pig_id,))

    def _case(self, connection, case_id, episode, concern, recurrence=None, episode_started_at="2026-08-20 08:00+00"):
        connection.execute(
            """
            insert into public.pig_welfare_cases(
              welfare_case_id,pig_id,episode_key,concern_key,episode_started_at,
              first_reported_at,first_recorded_at,recurrence_of_welfare_case_id,
              created_by,source_system,source_reference,provenance_json,idempotency_key)
            values(%s,%s,%s,%s,%s,'2026-08-20 08:01+00',
              '2026-08-20 08:02+00',%s,'owner:1','owner','telegram:1','{}',%s)
            """,
            (case_id, self.pig_id, episode, concern, episode_started_at, recurrence, f"case:{case_id}"),
        )

    def _event(self, connection, case_id, suffix, event_type, state, occurred, **values):
        connection.execute(
            """
            insert into public.pig_welfare_case_events(
              welfare_case_event_id,welfare_case_id,event_type,case_state,urgency,
              responsible_owner,next_check_at,escalation_reason,closure_kind,closure_reason,
              occurred_at,recorded_at,actor_reference,source_system,source_reference,
              provenance_json,idempotency_key)
            values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'owner:1','owner','telegram:1','{}',%s)
            """,
            (
                f"event:{case_id}:{suffix}", case_id, event_type, state,
                values.get("urgency", "due"), values.get("owner", "HERDMASTER"),
                values.get("next_check"), values.get("escalation_reason"),
                values.get("closure_kind"), values.get("closure_reason"), occurred, occurred,
                f"event-key:{case_id}:{suffix}",
            ),
        )

    def test_episode_uniqueness_concurrency_and_recurrence(self):
        first = f"WELFARE-{self.run_id}-A"
        unrelated = f"WELFARE-{self.run_id}-B"
        recurrence = f"WELFARE-{self.run_id}-C"
        with psycopg.connect(self.database_url) as first_connection, psycopg.connect(self.database_url) as second_connection:
            self._case(first_connection, first, "episode-1", "not-eating")
            self._case(second_connection, unrelated, "episode-1", "leg-injury")
            first_connection.commit()
            second_connection.commit()
        with psycopg.connect(self.database_url) as connection:
            self._case(
                connection, recurrence, "episode-2", "not-eating", first,
                episode_started_at="2026-08-20 08:01+00",
            )
            connection.commit()
            count = connection.execute(
                "select count(*) from public.pig_welfare_cases where pig_id=%s", (self.pig_id,)
            ).fetchone()[0]
            self.assertEqual(count, 3)
            with self.assertRaises(psycopg.Error):
                self._case(connection, f"WELFARE-{self.run_id}-D", "episode-1", "not-eating")
            connection.rollback()
            with self.assertRaises(psycopg.Error):
                self._case(
                    connection, f"WELFARE-{self.run_id}-E", "episode-3", "leg-injury", first,
                    episode_started_at="2026-08-20 08:01+00",
                )
            connection.rollback()

    def test_explicit_close_reopen_and_non_merging_fact_links(self):
        case_id = f"WELFARE-{self.run_id}-LIFE"
        with psycopg.connect(self.database_url) as connection:
            self._case(connection, case_id, "episode-life", "feeding")
            self._event(connection, case_id, "open", "opened", "open", "2026-08-20 08:02+00")
            self._event(
                connection, case_id, "check", "next_check_scheduled", "monitoring",
                "2026-08-20 08:03+00", next_check="2026-08-20 10:00+00",
            )
            self._event(
                connection, case_id, "close", "closed", "closed", "2026-08-20 08:04+00",
                closure_reason="canonical death fact recorded",
                closure_kind="death",
            )
            connection.execute(
                """
                insert into public.pig_welfare_case_fact_links(
                  welfare_case_fact_link_id,welfare_case_id,welfare_case_event_id,
                  fact_domain,fact_id,relationship,linked_at,recorded_at,
                  actor_reference,source_reference,provenance_json,idempotency_key)
                values(%s,%s,%s,'pig_lifecycle',%s,'closes_living_welfare_question',
                  '2026-08-20 08:04+00','2026-08-20 08:04+00','system:herdmaster',
                  'lifecycle-event','{}',%s)
                """,
                (
                    f"link:{case_id}", case_id, f"event:{case_id}:close",
                    f"death-fact:{self.run_id}", f"link-key:{case_id}",
                ),
            )
            connection.commit()
            with self.assertRaises(psycopg.Error):
                self._event(connection, case_id, "silent", "assessed", "monitoring", "2026-08-20 09:00+00")
            connection.rollback()
            with self.assertRaises(psycopg.Error):
                self._event(
                    connection, case_id, "correction-reopen", "correction", "open",
                    "2026-08-20 09:00+00",
                )
            connection.rollback()
            with self.assertRaises(psycopg.Error):
                self._event(
                    connection, case_id, "correction-death", "correction", "closed",
                    "2026-08-20 09:00+00", closure_kind="recovered",
                    closure_reason="unsupported reversal",
                )
            connection.rollback()
            with self.assertRaises(psycopg.Error):
                self._event(connection, case_id, "death-reopen", "reopened", "open", "2026-08-20 09:01+00")
            connection.rollback()
            row = connection.execute(
                "select case_state,event_type,closure_kind from public.pig_welfare_case_current where welfare_case_id=%s",
                (case_id,),
            ).fetchone()
            self.assertEqual(row, ("closed", "closed", "death"))

            with self.assertRaises(psycopg.Error):
                connection.execute(
                    """
                    insert into public.pig_welfare_case_fact_links(
                      welfare_case_fact_link_id,welfare_case_id,fact_domain,fact_id,relationship,
                      linked_at,recorded_at,actor_reference,source_reference,provenance_json,idempotency_key)
                    values(%s,%s,'observation','OBS-1','closes_living_welfare_question',
                      '2026-08-20 09:02+00','2026-08-20 09:02+00','owner:1','telegram:2','{}',%s)
                    """,
                    (f"bad-link:{case_id}", case_id, f"bad-link-key:{case_id}"),
                )
            connection.rollback()

            with self.assertRaises(psycopg.Error):
                connection.execute(
                    "update public.pig_welfare_cases set concern_key='changed' where welfare_case_id=%s",
                    (case_id,),
                )

    def test_non_death_reopen_equal_time_sequence_and_idempotency(self):
        case_id = f"WELFARE-{self.run_id}-RECOVERED"
        with psycopg.connect(self.database_url) as connection:
            self._case(connection, case_id, "episode-recovered", "feeding")
            self._event(connection, case_id, "open", "opened", "open", "2026-08-20 08:02+00")
            self._event(
                connection, case_id, "close", "closed", "closed", "2026-08-20 08:03+00",
                closure_kind="recovered", closure_reason="observed eating normally",
            )
            self._event(connection, case_id, "reopen", "reopened", "open", "2026-08-20 08:04+00")
            self._event(connection, case_id, "same-time-a", "assessed", "monitoring", "2026-08-20 08:05+00")
            self._event(connection, case_id, "same-time-b", "assessed", "monitoring", "2026-08-20 08:05+00")
            connection.commit()
            row = connection.execute(
                "select welfare_case_event_id,sequence_no from public.pig_welfare_case_current where welfare_case_id=%s",
                (case_id,),
            ).fetchone()
            self.assertEqual(row, (f"event:{case_id}:same-time-b", 5))
            with self.assertRaises(psycopg.Error):
                connection.execute(
                    """
                    insert into public.pig_welfare_case_events(
                      welfare_case_event_id,welfare_case_id,event_type,case_state,sequence_no,
                      urgency,responsible_owner,occurred_at,recorded_at,actor_reference,
                      source_system,source_reference,provenance_json,idempotency_key)
                    values(%s,%s,'assessed','monitoring',99,'due','HERDMASTER',
                      '2026-08-20 08:06+00','2026-08-20 08:06+00','owner:1','owner',
                      'telegram:duplicate','{}',%s)
                    """,
                    (
                        f"event:{case_id}:duplicate-idempotency", case_id,
                        f"event-key:{case_id}:same-time-b",
                    ),
                )

    def test_concurrent_same_case_events_receive_distinct_sequence(self):
        case_id = f"WELFARE-{self.run_id}-CONCURRENT"
        with psycopg.connect(self.database_url) as connection:
            self._case(connection, case_id, "episode-concurrent", "mobility")
            self._event(connection, case_id, "open", "opened", "open", "2026-08-20 08:02+00")
            connection.commit()

        barrier = threading.Barrier(2)

        def append(suffix):
            with psycopg.connect(self.database_url) as connection:
                barrier.wait()
                self._event(
                    connection, case_id, suffix, "assessed", "monitoring",
                    "2026-08-20 08:03+00",
                )
                connection.commit()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(append, suffix) for suffix in ("worker-a", "worker-b")]
            for future in futures:
                future.result(timeout=10)

        with psycopg.connect(self.database_url) as connection:
            sequences = connection.execute(
                "select sequence_no from public.pig_welfare_case_events where welfare_case_id=%s order by sequence_no",
                (case_id,),
            ).fetchall()
            self.assertEqual(sequences, [(1,), (2,), (3,)])

    def test_default_deny_function_and_table_privileges(self):
        with psycopg.connect(self.database_url) as connection:
            public_execute = connection.execute(
                """
                select has_function_privilege('public',
                  'public.pig_welfare_case_event_validate_insert()', 'EXECUTE')
                """
            ).fetchone()[0]
            public_select = connection.execute(
                "select has_table_privilege('public','public.pig_welfare_cases','SELECT')"
            ).fetchone()[0]
            security_invoker = connection.execute(
                "select reloptions from pg_class where oid='public.pig_welfare_case_current'::regclass"
            ).fetchone()[0]
            self.assertFalse(public_execute)
            self.assertFalse(public_select)
            self.assertIn("security_invoker=true", security_invoker)


if __name__ == "__main__":
    unittest.main()
