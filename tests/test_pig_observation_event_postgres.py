"""Production-shaped disposable PostgreSQL gates for the observation rail."""
import os
import unittest
from pathlib import Path

import psycopg


class PigObservationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        root = Path("supabase/migrations")
        cls.sql = (root / "202607200001_create_pig_observation_events.sql").read_text(encoding="utf-8")
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute((root / "202605210001_foundation_migration_log.sql").read_text(encoding="utf-8"))
                cursor.execute("""
                    do $$ begin
                      if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
                      if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
                      if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
                    end $$;
                    alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
                    alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
                    create table if not exists public.pigs(pig_id text primary key);
                    insert into public.pigs(pig_id) values ('OBS-PIG-1') on conflict do nothing;
                """)
            connection.commit()

    def test_transactional_application_privilege_matrix_and_rollback(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(self.sql)
                for role in ("anon", "authenticated"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "select has_table_privilege(%s,'public.pig_observation_events',%s)",
                            (role, privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0], (role, privilege))
                for privilege, expected in (
                    ("SELECT", True), ("INSERT", True), ("UPDATE", False),
                    ("DELETE", False), ("TRUNCATE", False),
                ):
                    cursor.execute(
                        "select has_table_privilege('service_role','public.pig_observation_events',%s)",
                        (privilege,),
                    )
                    self.assertEqual(cursor.fetchone()[0], expected)
                cursor.execute("""select count(*) from information_schema.role_routine_grants
                    where routine_schema='public'
                      and routine_name in (
                        'pig_observation_events_validate_supersession',
                        'pig_observation_events_block_update_delete'
                      )
                      and grantee='PUBLIC'""")
                self.assertEqual(cursor.fetchone()[0], 0)
                for role in ("anon", "authenticated", "service_role"):
                    cursor.execute(
                        """select has_function_privilege(%s,
                           'public.pig_observation_events_validate_supersession()','EXECUTE')""",
                        (role,),
                    )
                    self.assertFalse(cursor.fetchone()[0], role)
                cursor.execute(
                    "select relrowsecurity from pg_class where oid='public.pig_observation_events'::regclass"
                )
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute(
                    "select count(*) from pg_policies where schemaname='public' and tablename='pig_observation_events'"
                )
                self.assertEqual(cursor.fetchone()[0], 0)
                for role in ("anon", "authenticated"):
                    cursor.execute("savepoint client_denied")
                    cursor.execute(f"set local role {role}")
                    with self.assertRaises(psycopg.Error):
                        cursor.execute("select * from public.pig_observation_events")
                    cursor.execute("rollback to savepoint client_denied")
                cursor.execute("set local role service_role")
                cursor.execute("""insert into public.pig_observation_events(
                    observation_event_id,pig_id,observed_at,observer_reference,
                    observation_category,factual_note,source_system,idempotency_key
                ) values ('OBS-EVENT-1','OBS-PIG-1',now(),'OWNER-TEST',
                          'body_condition','Factual observation','owner','OBS-IDEM-1')""")
                cursor.execute("select count(*) from public.pig_observation_events")
                self.assertEqual(cursor.fetchone()[0], 1)
                for statement in (
                    "update public.pig_observation_events set factual_note='changed'",
                    "delete from public.pig_observation_events",
                ):
                    cursor.execute("savepoint denied")
                    with self.assertRaises(psycopg.Error):
                        cursor.execute(statement)
                    cursor.execute("rollback to savepoint denied")
                cursor.execute("reset role")
            connection.rollback()
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.pig_observation_events')")
                self.assertIsNone(cursor.fetchone()[0])
                cursor.execute("""select exists(select 1 from app_private.migration_log
                    where migration_id='202607200001_create_pig_observation_events')""")
                self.assertFalse(cursor.fetchone()[0])


if __name__ == "__main__":
    unittest.main()
