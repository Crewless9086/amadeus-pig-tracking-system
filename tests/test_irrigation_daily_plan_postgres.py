"""Opt-in production-shaped PostgreSQL proof for canonical daily plans."""

import concurrent.futures
import os
import unittest
from pathlib import Path

import psycopg

from modules.telemetry.irrigation_daily_plan_service import (
    PostgresDailyPlanLedger,
    generate_or_reuse_daily_plan,
)
from tests.test_irrigation_daily_plan_service import packet


class IrrigationDailyPlanPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("ROOTLINE_DISPOSABLE_POSTGRES_URL not configured")
        migrations = Path("supabase/migrations")
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
                    do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
                    do $$ begin create role service_role nologin bypassrls; exception when duplicate_object then null; end $$;
                    alter default privileges in schema public grant all on tables to public,anon,authenticated,service_role;
                    alter default privileges in schema public grant all on sequences to public,anon,authenticated,service_role;
                    alter default privileges in schema public grant execute on functions to public,anon,authenticated,service_role;
                """)
                cursor.execute(
                    (migrations / "202605210001_foundation_migration_log.sql").read_text(
                        encoding="utf-8"
                    )
                )
                for table, name in (
                    ("irrigation_command_plans", "202607250002_create_irrigation_command_ledger.sql"),
                    ("irrigation_daily_plan_identities", "202607260005_create_irrigation_daily_plans.sql"),
                ):
                    cursor.execute("select to_regclass(%s)", (f"public.{table}",))
                    if cursor.fetchone()[0] is None:
                        cursor.execute((migrations / name).read_text(encoding="utf-8"))

    def setUp(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """truncate public.irrigation_command_state_events,
                       public.irrigation_command_plans,
                       public.irrigation_daily_plan_generations,
                       public.irrigation_daily_plan_identities cascade"""
                )

    def ledger(self):
        return PostgresDailyPlanLedger(self.url)

    def test_repeated_generation_is_idempotent(self):
        first = generate_or_reuse_daily_plan(packet(), ledger=self.ledger())
        second = generate_or_reuse_daily_plan(packet(), ledger=self.ledger())
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*),max(generation) from public.irrigation_daily_plan_generations")
                self.assertEqual(cursor.fetchone(), (1, 1))

    def test_simultaneous_generation_creates_one_current_plan(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: generate_or_reuse_daily_plan(packet(), ledger=self.ledger()),
                range(8),
            ))
        self.assertEqual(sum(item["created"] for item in results), 1)
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select count(*),count(distinct i.daily_plan_id),max(i.current_generation)
                    from public.irrigation_daily_plan_identities i
                    join public.irrigation_daily_plan_generations g using (daily_plan_id)
                """)
                self.assertEqual(cursor.fetchone(), (1, 1, 1))

    def test_changed_evidence_appends_history_and_selects_only_latest(self):
        generate_or_reuse_daily_plan(packet(), ledger=self.ledger())
        changed = generate_or_reuse_daily_plan(
            packet(evidence={"weather": {"rain_mm": 4}}, replacement_reason="rain changed"),
            ledger=self.ledger(),
        )
        self.assertEqual(changed["superseded_generation"], 1)
        self.assertEqual(changed["daily_plan"]["generation"], 2)
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_generation from public.irrigation_daily_plan_identities")
                self.assertEqual(cursor.fetchone()[0], 2)
                cursor.execute("select count(*) from public.irrigation_daily_plan_generations")
                self.assertEqual(cursor.fetchone()[0], 2)

    def test_client_roles_denied_and_service_function_bounded(self):
        function = (
            "public.rootline_generate_daily_irrigation_plan("
            "text,date,text,text,text,timestamp with time zone,text,jsonb,jsonb)"
        )
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    for table in (
                        "public.irrigation_daily_plan_identities",
                        "public.irrigation_daily_plan_generations",
                    ):
                        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                            cursor.execute(
                                "select has_table_privilege(%s,%s,%s)",
                                (role, table, privilege),
                            )
                            self.assertFalse(cursor.fetchone()[0])
                    cursor.execute("select has_function_privilege(%s,%s,'EXECUTE')", (role, function))
                    self.assertFalse(cursor.fetchone()[0])
                cursor.execute("select has_function_privilege('service_role',%s,'EXECUTE')", (function,))
                self.assertTrue(cursor.fetchone()[0])

    def test_command_cannot_reference_superseded_generation(self):
        generate_or_reuse_daily_plan(packet(), ledger=self.ledger())
        generate_or_reuse_daily_plan(
            packet(evidence={"weather": {"rain_mm": 4}}, replacement_reason="rain changed"),
            ledger=self.ledger(),
        )
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("""
                        insert into public.irrigation_command_plans
                        (command_id,generation,daily_plan_id,daily_plan_generation,
                         daily_plan_operating_date,zone_id,zone_name,intent,
                         requested_duration_minutes,created_at,expires_at,idempotency_key,
                         request_sha256,paired_off_required,paired_off_command_id,
                         weather_evidence,power_evidence,water_infrastructure_evidence,
                         controller_actuator_inventory,safety_interlocks,
                         prohibition_reasons,command_json,recorded_by)
                        values ('OLD',1,'ROOTLINE-DAILY-PLAN-20260726',1,'2026-07-26',
                         'B12345','B - Kamp','OFF',1,now(),now()+interval '1 minute','old',
                         %s,false,null,'{}','{}','{}','{}','{}','[]','{}','test')
                    """, ("e" * 64,))


if __name__ == "__main__":
    unittest.main()
