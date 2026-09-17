"""Disposable-Postgres proof for the ROOTLINE policy-review ledger.

This test runs only with ROOTLINE_POLICY_DISPOSABLE_POSTGRES_URL. It never
falls back to DATABASE_URL and never connects to production.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
import uuid

import psycopg


class RootlineOperatingPolicyPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv(
            "ROOTLINE_POLICY_DISPOSABLE_POSTGRES_URL", ""
        ).strip()
        if not cls.database_url:
            raise unittest.SkipTest(
                "ROOTLINE_POLICY_DISPOSABLE_POSTGRES_URL not configured"
            )
        migrations = Path("supabase/migrations")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    do $$ begin create role anon nologin;
                    exception when duplicate_object then null; end $$;
                    do $$ begin create role authenticated nologin;
                    exception when duplicate_object then null; end $$;
                    do $$ begin create role service_role nologin bypassrls;
                    exception when duplicate_object then null; end $$;
                    alter default privileges in schema public
                        grant all privileges on tables
                        to public, anon, authenticated, service_role;
                    alter default privileges in schema public
                        grant all privileges on sequences
                        to public, anon, authenticated, service_role;
                    alter default privileges in schema public
                        grant execute on functions
                        to public, anon, authenticated, service_role;
                    """
                )
                cursor.execute(
                    (migrations / "202605210001_foundation_migration_log.sql").read_text(
                        encoding="utf-8"
                    )
                )
                cursor.execute(
                    "select to_regclass('public.rootline_operating_policy_versions')"
                )
                if cursor.fetchone()[0] is None:
                    cursor.execute(
                        (
                            migrations
                            / "202607270002_create_rootline_operating_policies.sql"
                        ).read_text(encoding="utf-8")
                    )

    def setUp(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """truncate public.rootline_operating_policy_events,
                                      public.rootline_operating_policy_versions
                       restart identity cascade"""
                )
        self.identity = uuid.uuid4().hex
        self.proposal_id = f"ROOTLINE-POLICY-{self.identity[:24].upper()}"

    def _propose(self, idempotency=None, proposal_id=None, sha=None):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select version,created,stored_proposed_at
                       from public.rootline_append_operating_policy_proposal(
                         %s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (
                        "ROOTLINE-OPERATING-KNOWLEDGE",
                        proposal_id or self.proposal_id,
                        sha or ("a" * 64),
                        idempotency or f"proposal-{self.identity}",
                        json.dumps({"seasonal_boundaries": "Unknown"}),
                        json.dumps({"owner_note": "disposable test"}),
                        "owner-admin:test",
                        "2026-07-27T16:00:00Z",
                    ),
                )
                row = cursor.fetchone()
                return row[:2]

    def _transition(self, state, key, proposal_id=None, effective=None):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select created
                       from public.rootline_append_operating_policy_transition(
                         %s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
                    (
                        proposal_id or self.proposal_id,
                        state,
                        "owner-admin:test",
                        json.dumps({"owner_note": state}),
                        key,
                        "2026-07-27T16:01:00Z",
                        effective,
                        "b" * 64,
                    ),
                )
                return cursor.fetchone()[0]

    def test_client_roles_have_zero_direct_access(self):
        tables = (
            "public.rootline_operating_policy_versions",
            "public.rootline_operating_policy_events",
        )
        functions = (
            "public.rootline_append_operating_policy_proposal(text,text,text,text,jsonb,jsonb,text,timestamp with time zone)",
            "public.rootline_append_operating_policy_transition(text,text,text,jsonb,text,timestamp with time zone,timestamp with time zone,text)",
        )
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    for table in tables:
                        for privilege in (
                            "SELECT",
                            "INSERT",
                            "UPDATE",
                            "DELETE",
                            "TRUNCATE",
                            "REFERENCES",
                            "TRIGGER",
                        ):
                            cursor.execute(
                                "select has_table_privilege(%s,%s,%s)",
                                (role, table, privilege),
                            )
                            self.assertFalse(cursor.fetchone()[0])
                    for function in functions:
                        cursor.execute(
                            "select has_function_privilege(%s,%s,'EXECUTE')",
                            (role, function),
                        )
                        self.assertFalse(cursor.fetchone()[0])
                    cursor.execute(
                        """select has_sequence_privilege(
                             %s,
                             'public.rootline_operating_policy_events_event_sequence_seq',
                             'USAGE')""",
                        (role,),
                    )
                    self.assertFalse(cursor.fetchone()[0])
                cursor.execute(
                    """
                    select count(*)
                    from pg_class c
                    cross join lateral aclexplode(
                        coalesce(c.relacl, acldefault(case c.relkind
                          when 'S' then 'S'::"char" else 'r'::"char" end, c.relowner))
                    ) acl
                    where c.oid in (
                        'public.rootline_operating_policy_versions'::regclass,
                        'public.rootline_operating_policy_events'::regclass,
                        'public.rootline_operating_policy_events_event_sequence_seq'::regclass
                    )
                      and acl.grantee = 0
                    """
                )
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute(
                    """
                    select count(*)
                    from pg_proc p
                    cross join lateral aclexplode(
                        coalesce(p.proacl, acldefault('f', p.proowner))
                    ) acl
                    where p.oid in (
                        'public.rootline_append_operating_policy_proposal(text,text,text,text,jsonb,jsonb,text,timestamptz)'::regprocedure,
                        'public.rootline_append_operating_policy_transition(text,text,text,jsonb,text,timestamptz,timestamptz,text)'::regprocedure
                    )
                      and acl.grantee = 0
                    """
                )
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_service_role_is_read_and_function_only(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for table in (
                    "public.rootline_operating_policy_versions",
                    "public.rootline_operating_policy_events",
                ):
                    cursor.execute(
                        "select has_table_privilege('service_role',%s,'SELECT')",
                        (table,),
                    )
                    self.assertTrue(cursor.fetchone()[0])
                    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "select has_table_privilege('service_role',%s,%s)",
                            (table, privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0])

    def test_replayed_proposal_is_one_version(self):
        first = self._propose()
        replay = self._propose()
        self.assertEqual(first, (1, True))
        self.assertEqual(replay, (1, False))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from public.rootline_operating_policy_versions"
                )
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute(
                    "select count(*) from public.rootline_operating_policy_events"
                )
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_concurrent_replay_cannot_create_competing_versions(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _item: self._propose(), range(2)))
        self.assertEqual(sorted(results), [(1, False), (1, True)])

    def test_idempotency_conflict_is_rejected(self):
        self._propose()
        with self.assertRaisesRegex(Exception, "proposal_idempotency_conflict"):
            self._propose(proposal_id=f"ROOTLINE-POLICY-{'B' * 24}", sha="b" * 64)

    def test_transition_cannot_replay_a_proposal_event_key_or_null_digest(self):
        self._propose()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaisesRegex(Exception, "transition_idempotency_conflict"):
                    cursor.execute(
                        """select * from public.rootline_append_operating_policy_transition(
                           %s,'owner_reviewed','owner-admin:test','{}'::jsonb,%s,
                           now(),null,%s)""",
                        (
                            self.proposal_id,
                            f"proposal:proposal-{self.identity}",
                            "d" * 64,
                        ),
                    )
            connection.rollback()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaisesRegex(Exception, "invalid_transition_sha256"):
                    cursor.execute(
                        """select * from public.rootline_append_operating_policy_transition(
                           %s,'owner_reviewed','owner-admin:test','{}'::jsonb,%s,
                           now(),null,null)""",
                        (self.proposal_id, f"null-digest-{self.identity}"),
                    )

    def test_transition_replay_compares_immutable_semantics_not_only_digest(self):
        self._propose()
        key = f"review-semantic-{self.identity}"
        self.assertTrue(self._transition("owner_reviewed", key))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaisesRegex(Exception, "transition_idempotency_conflict"):
                    cursor.execute(
                        """select * from public.rootline_append_operating_policy_transition(
                           %s,'owner_reviewed','owner-admin:changed',
                           '{"owner_note":"changed"}'::jsonb,%s,%s,null,%s)""",
                        (
                            self.proposal_id,
                            key,
                            "2026-07-27T16:02:00Z",
                            "b" * 64,
                        ),
                    )

    def test_review_then_explicit_activation(self):
        self._propose()
        self.assertTrue(self._transition("owner_reviewed", f"review-{self.identity}"))
        self.assertTrue(
            self._transition(
                "active_for_advice",
                f"activate-{self.identity}",
                effective="2026-07-28T06:00:00+02:00",
            )
        )
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select state,actor_identity,effective_at
                       from public.rootline_operating_policy_events
                       order by event_sequence"""
                )
                rows = cursor.fetchall()
        self.assertEqual([row[0] for row in rows], list(("proposed", "owner_reviewed", "active_for_advice")))
        self.assertEqual(rows[-1][1], "owner-admin:test")
        self.assertIsNotNone(rows[-1][2])

    def test_activation_without_review_is_rejected(self):
        self._propose()
        with self.assertRaisesRegex(Exception, "owner_reviewed_state_required"):
            self._transition(
                "active_for_advice",
                f"activate-{self.identity}",
                effective="2026-07-28T06:00:00+02:00",
            )

    def test_direct_backdated_activation_is_rejected(self):
        self._propose()
        self._transition("owner_reviewed", f"review-backdate-{self.identity}")
        with self.assertRaisesRegex(Exception, "effective_time_must_not_precede_activation"):
            self._transition(
                "active_for_advice",
                f"activate-backdate-{self.identity}",
                effective="2026-07-27T15:59:00Z",
            )

    def test_stale_predecessor_version_is_rejected(self):
        self._propose()
        second_id = f"ROOTLINE-POLICY-{'C' * 24}"
        self._propose(
            idempotency=f"second-{self.identity}", proposal_id=second_id, sha="c" * 64
        )
        with self.assertRaisesRegex(Exception, "stale_policy_version"):
            self._transition("owner_reviewed", f"review-{self.identity}")

    def test_concurrent_review_has_one_append(self):
        self._propose()

        def review(key):
            try:
                return self._transition("owner_reviewed", key)
            except Exception as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(review, (f"review-a-{self.identity}", f"review-b-{self.identity}"))
            )
        self.assertEqual(sum(result is True for result in results), 1)
        self.assertTrue(any("conflicting_transition" in str(result) for result in results))

    def test_history_is_immutable_and_authority_flags_are_false(self):
        self._propose()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select generates_plan,creates_command,mutates_schedule,
                              activates_workflow,calls_ifttt,calls_n8n,
                              controls_hardware,automatic_retry,
                              canary_runtime_used,measured_water_inferred,
                              successful_routine_irrigation_inferred
                       from public.rootline_operating_policy_versions"""
                )
                self.assertEqual(cursor.fetchone(), (False,) * 11)
                with self.assertRaisesRegex(Exception, "append-only"):
                    cursor.execute(
                        """update public.rootline_operating_policy_versions
                           set evidence_json='{}'::jsonb"""
                    )
            connection.rollback()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaisesRegex(Exception, "append-only"):
                    cursor.execute(
                        "delete from public.rootline_operating_policy_versions"
                    )

    def test_reserved_or_unknown_state_is_database_rejected(self):
        self._propose()
        with self.assertRaisesRegex(Exception, "invalid_policy_transition"):
            self._transition("dispatch_pending", f"dispatch-{self.identity}")


if __name__ == "__main__":
    unittest.main()
