import os
from pathlib import Path
import unittest


class SamAvailabilityObservationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        import psycopg

        cls.psycopg = psycopg
        root = Path("supabase/migrations")
        cls.sql = (
            root
            / "202607270003_create_sam_live_stock_availability_observations.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    (
                        root / "202605210001_foundation_migration_log.sql"
                    ).read_text(encoding="utf-8")
                )
                cursor.execute(
                    """
                    do $$ begin
                      if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
                      if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
                      if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
                    end $$;
                    alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
                    alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
                    """
                )
                cursor.execute(cls.sql)
            connection.commit()

    def test_privileges_append_only_and_replay_identity(self):
        psycopg = self.psycopg
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "select has_table_privilege(%s,'public.sam_live_stock_availability_observation_events',%s)",
                            (role, privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0], (role, privilege))
                for privilege, expected in (
                    ("SELECT", True),
                    ("INSERT", True),
                    ("UPDATE", False),
                    ("DELETE", False),
                    ("TRUNCATE", False),
                ):
                    cursor.execute(
                        "select has_table_privilege('service_role','public.sam_live_stock_availability_observation_events',%s)",
                        (privilege,),
                    )
                    self.assertEqual(cursor.fetchone()[0], expected)
                cursor.execute(
                    "select relrowsecurity from pg_class where oid='public.sam_live_stock_availability_observation_events'::regclass"
                )
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute(
                    """
                    insert into public.sam_live_stock_availability_observation_events (
                      observation_event_id, cohort_hash, contract_version,
                      evaluator_version, observed_at, expires_at,
                      observer_principal, source, row_count,
                      eligible_totals_json, exclusions_json, unresolved_count,
                      lineage_json
                    ) values (
                      'SAM-LIVE-STOCK-AVAIL-TEST',
                      repeat('a',64),
                      'sam_live_stock_availability_observation_v1',
                      'sam_live_stock_availability_evaluator_v1',
                      now()-interval '1 minute', now()+interval '1 hour',
                      'owner-admin:test', 'owner_weighing_review', 1,
                      '{}'::jsonb, '{}'::jsonb, 0, '[]'::jsonb
                    )
                    """
                )
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    cursor.execute(
                        """
                        insert into public.sam_live_stock_availability_observation_events
                        select * from public.sam_live_stock_availability_observation_events
                        where observation_event_id='SAM-LIVE-STOCK-AVAIL-TEST'
                        """
                    )
            connection.rollback()

    def test_update_and_delete_are_blocked(self):
        psycopg = self.psycopg
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.sam_live_stock_availability_observation_events (
                      observation_event_id, cohort_hash, contract_version,
                      evaluator_version, observed_at, expires_at,
                      observer_principal, source, row_count,
                      eligible_totals_json, exclusions_json, unresolved_count,
                      lineage_json
                    ) values (
                      'SAM-LIVE-STOCK-AVAIL-IMMUTABLE',
                      repeat('b',64), 'v1', 'v1',
                      now()-interval '1 minute', now()+interval '1 hour',
                      'owner-admin:test', 'owner_weighing_review', 0,
                      '{}'::jsonb, '{}'::jsonb, 0, '[]'::jsonb
                    )
                    """
                )
                cursor.execute("savepoint immutable")
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "update public.sam_live_stock_availability_observation_events set row_count=2 where observation_event_id='SAM-LIVE-STOCK-AVAIL-IMMUTABLE'"
                    )
                cursor.execute("rollback to savepoint immutable")
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "delete from public.sam_live_stock_availability_observation_events where observation_event_id='SAM-LIVE-STOCK-AVAIL-IMMUTABLE'"
                    )
            connection.rollback()
