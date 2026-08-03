"""Disposable-Postgres proof for the command-inert Water & Energy ledger."""

import json
import os
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest

import psycopg
from modules.telemetry.rootline_water_energy_plan import (
    _read_latest_tank_observation,
    record_tank_observation,
)


class WaterEnergyPlanPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("ROOTLINE_WATER_ENERGY_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("ROOTLINE_WATER_ENERGY_DISPOSABLE_POSTGRES_URL not configured")
        migrations = Path("supabase/migrations")
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    do $$ begin create role anon nologin;
                    exception when duplicate_object then null; end $$;
                    do $$ begin create role authenticated nologin;
                    exception when duplicate_object then null; end $$;
                    do $$ begin create role service_role nologin bypassrls;
                    exception when duplicate_object then null; end $$;
                    alter default privileges in schema public grant all on tables
                      to public,anon,authenticated,service_role;
                    alter default privileges in schema public grant execute on functions
                      to public,anon,authenticated,service_role;
                """)
                cursor.execute(
                    (migrations / "202605210001_foundation_migration_log.sql").read_text("utf-8")
                )
                cursor.execute(
                    "select to_regclass('public.rootline_water_energy_plan_identities')"
                )
                if cursor.fetchone()[0] is None:
                    cursor.execute(
                        (migrations / "202607280001_create_rootline_water_energy_plans.sql").read_text("utf-8")
                    )
                cursor.execute("select 1 from information_schema.columns where table_schema='public' and table_name='rootline_tank_observations' and column_name='provider_message_id'")
                if cursor.fetchone() is None:
                    cursor.execute((migrations / "202608030001_extend_rootline_fraction_observations.sql").read_text("utf-8"))

    def setUp(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    truncate rootline_water_energy_plan_generations,
                             rootline_water_energy_plan_identities,
                             rootline_tank_observations cascade
                """)

    def _append(self, digest="a" * 64):
        plan = {
            "plan_id": "ROOTLINE-WEP-20260728",
            "operating_date": "2026-07-28",
            "operating_timezone": "Africa/Johannesburg",
            "status": "needs_data",
            "evidence_sha256": digest,
            "candidate_tasks": [],
            "authority": {
                "writes_performed": False,
                "creates_irrigation_plan": False,
                "creates_command": False,
                "mutates_schedule": False,
                "activates_workflow": False,
                "calls_smartlife": False,
                "calls_sonoff": False,
                "calls_ifttt": False,
                "calls_n8n": False,
                "controls_hardware": False,
                "automatic_retry": False,
            },
        }
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select created,superseded_generation,generation
                      from rootline_append_water_energy_plan(
                        'ROOTLINE-WEP-20260728','2026-07-28',%s,now(),
                        'evidence changed','needs_data','{}',%s::jsonb,'owner-admin:test')
                """, (digest, json.dumps(plan)))
                return cursor.fetchone()

    def test_identity_date_and_embedded_authority_are_structurally_bound(self):
        plan = {
            "plan_id": "ROOTLINE-WEP-20260728",
            "operating_date": "2026-07-28",
            "operating_timezone": "Africa/Johannesburg",
            "status": "needs_data",
            "evidence_sha256": "c" * 64,
            "candidate_tasks": [],
            "authority": {
                "writes_performed": False, "creates_irrigation_plan": False,
                "creates_command": False, "mutates_schedule": False,
                "activates_workflow": False, "calls_smartlife": False,
                "calls_sonoff": False, "calls_ifttt": False, "calls_n8n": False,
                "controls_hardware": False, "automatic_retry": False,
            },
        }
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaisesRegex(Exception, "identity"):
                    cursor.execute("""
                        select * from rootline_append_water_energy_plan(
                          'ROOTLINE-WEP-20260729','2026-07-28',%s,now(),
                          'changed','needs_data','{}',%s::jsonb,'owner-admin:test')
                    """, ("c" * 64, json.dumps(plan)))

    def test_misleading_status_or_dispatchable_task_is_rejected(self):
        base = {
            "plan_id": "ROOTLINE-WEP-20260728",
            "operating_date": "2026-07-28",
            "operating_timezone": "Africa/Johannesburg",
            "status": "recommend",
            "evidence_sha256": "d" * 64,
            "candidate_tasks": [{
                "command_created": False, "dispatchable": True,
                "electrical_operation_confirmed": False,
                "physical_water_flow_confirmed": False,
            }],
            "authority": {
                "writes_performed": False, "creates_irrigation_plan": False,
                "creates_command": False, "mutates_schedule": False,
                "activates_workflow": False, "calls_smartlife": False,
                "calls_sonoff": False, "calls_ifttt": False, "calls_n8n": False,
                "controls_hardware": False, "automatic_retry": False,
            },
        }
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaisesRegex(Exception, "identity|advisory"):
                    cursor.execute("""
                        select * from rootline_append_water_energy_plan(
                          'ROOTLINE-WEP-20260728','2026-07-28',%s,now(),
                          'changed','needs_data','{}',%s::jsonb,'owner-admin:test')
                    """, ("d" * 64, json.dumps(base)))
        for field in (
            "command_created", "dispatchable",
            "electrical_operation_confirmed", "physical_water_flow_confirmed",
        ):
            for bad_value in ("missing", None):
                candidate = json.loads(json.dumps(base))
                candidate["status"] = "needs_data"
                candidate["candidate_tasks"][0]["dispatchable"] = False
                if bad_value == "missing":
                    candidate["candidate_tasks"][0].pop(field)
                else:
                    candidate["candidate_tasks"][0][field] = None
                with self.subTest(field=field, bad_value=bad_value):
                    with psycopg.connect(self.url) as connection:
                        with connection.cursor() as cursor:
                            with self.assertRaisesRegex(Exception, "advisory"):
                                cursor.execute("""
                                    select * from rootline_append_water_energy_plan(
                                      'ROOTLINE-WEP-20260728','2026-07-28',%s,now(),
                                      'changed','needs_data','{}',%s::jsonb,'owner-admin:test')
                                """, ("d" * 64, json.dumps(candidate)))

    def test_replay_and_concurrency_create_one_current_generation(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self._append(), range(2)))
        self.assertEqual(sorted(results), [(False, None, 1), (True, None, 1)])
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*),max(current_generation) from rootline_water_energy_plan_identities")
                self.assertEqual(cursor.fetchone(), (1, 1))
                cursor.execute("select count(*) from rootline_water_energy_plan_generations")
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_material_evidence_supersedes_without_mutating_history(self):
        self.assertEqual(self._append(), (True, None, 1))
        self.assertEqual(self._append("b" * 64), (True, 1, 2))
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_generation from rootline_water_energy_plan_identities")
                self.assertEqual(cursor.fetchone()[0], 2)
                cursor.execute("select count(*) from rootline_water_energy_plan_generations")
                self.assertEqual(cursor.fetchone()[0], 2)
                with self.assertRaisesRegex(Exception, "append-only"):
                    cursor.execute("delete from rootline_water_energy_plan_generations")

    def test_roles_and_authority_are_fail_closed(self):
        tables = (
            "rootline_tank_observations",
            "rootline_water_energy_plan_identities",
            "rootline_water_energy_plan_generations",
        )
        function = (
            "rootline_append_water_energy_plan(text,date,text,timestamp with time zone,"
            "text,text,jsonb,jsonb,text)"
        )
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    for table in tables:
                        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                            cursor.execute("select has_table_privilege(%s,%s,%s)", (role, table, privilege))
                            self.assertFalse(cursor.fetchone()[0])
                    cursor.execute("select has_function_privilege(%s,%s,'EXECUTE')", (role, function))
                    self.assertFalse(cursor.fetchone()[0])
                cursor.execute("select has_function_privilege('public',%s,'EXECUTE')", (function,))
                self.assertFalse(cursor.fetchone()[0])
                cursor.execute("select has_function_privilege('service_role',%s,'EXECUTE')", (function,))
                self.assertTrue(cursor.fetchone()[0])
                for table in tables[1:]:
                    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute("select has_table_privilege('service_role',%s,%s)", (table, privilege))
                        self.assertFalse(cursor.fetchone()[0])
                for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                    cursor.execute(
                        "select has_table_privilege('service_role','rootline_tank_observations',%s)",
                        (privilege,),
                    )
                    self.assertFalse(cursor.fetchone()[0])

        self._append()
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select writes_farm_data,creates_irrigation_plan,creates_command,
                           mutates_schedule,activates_workflow,calls_smartlife,
                           calls_sonoff,calls_ifttt,calls_n8n,controls_hardware,
                           automatic_retry
                      from rootline_water_energy_plan_generations
                """)
                self.assertEqual(cursor.fetchone(), (False,) * 11)

    def test_tank_observation_is_append_only_counts_not_litres(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into rootline_tank_observations(
                      observation_id,idempotency_key,storage_reported_count,
                      reservoir_reported_count,storage_state,reservoir_state,
                      observed_at,reporter_identity,source)
                    values('ROOTLINE-TANK-AAAAAAAAAAAAAAAAAAAAAAAA','tank-1',4,8,
                           'OK','OK',now(),'owner-admin:test','owner_dashboard')
                """)
                with self.assertRaisesRegex(Exception, "append-only"):
                    cursor.execute("update rootline_tank_observations set storage_reported_count=5")

    def test_tank_idempotency_conflict_is_not_reported_as_replay(self):
        payload = {
            "storage_reported_count": 4,
            "reservoir_reported_count": 8,
            "storage_state": "OK",
            "reservoir_state": "OK",
            "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "source": "owner_dashboard",
            "idempotency_key": "tank-conflict",
        }
        first, status = record_tank_observation(payload, "owner-admin:test", self.url)
        self.assertEqual(status, 201)
        self.assertTrue(first["created"])
        latest = _read_latest_tank_observation(self.url)
        self.assertEqual(latest["storage_reported_count"], 4)
        self.assertEqual(latest["storage_state"], "OK")
        conflict, status = record_tank_observation(
            payload | {"storage_reported_count": 3},
            "owner-admin:test", self.url,
        )
        self.assertEqual(status, 409)
        self.assertEqual(conflict["status"], "tank_observation_idempotency_conflict")

    def test_provider_bound_fractions_round_trip_exactly_and_replay_once(self):
        payload={"storage_fraction":[2,4],"reservoir_fraction":[4,4],
            "storage_state":"OK","reservoir_state":"FULL",
            "provider_message_id":"3213","observed_at":"2026-08-03T16:22:07+00:00",
            "source":"oom_sakkie_owner","idempotency_key":"telegram:3213:water-fractions"}
        first,status=record_tank_observation(payload,"telegram-owner:42",self.url)
        self.assertEqual(status,201);self.assertTrue(first["created"])
        self.assertEqual(first["storage_fraction"],[2,4]);self.assertEqual(first["reservoir_fraction"],[4,4])
        self.assertEqual(first["provider_message_id"],"3213")
        latest=_read_latest_tank_observation(self.url)
        self.assertEqual(latest["storage_fraction"],[2,4])
        self.assertEqual(latest["reservoir_fraction"],[4,4])
        self.assertEqual(latest["storage_provider_message_id"],"3213")
        self.assertEqual(latest["reservoir_provider_message_id"],"3213")
        replay,status=record_tank_observation(payload,"telegram-owner:42",self.url)
        self.assertEqual(status,200);self.assertFalse(replay["created"])

    def test_fraction_requires_provider_identity_and_rejects_invalid_values(self):
        base={"storage_fraction":[2,4],"observed_at":"2026-08-03T16:22:07+00:00",
              "source":"oom_sakkie_owner","idempotency_key":"fraction-invalid"}
        result,status=record_tank_observation(base,"telegram-owner:42",self.url)
        self.assertEqual(status,400);self.assertEqual(result["status"],"provider_message_id_required_for_fraction")
        for fraction in ([5,4],[-1,4],[2,0],[2],"2/4"):
            result,status=record_tank_observation({**base,"storage_fraction":fraction,"provider_message_id":"3213"},"telegram-owner:42",self.url)
            self.assertEqual(status,400)

    def test_fraction_database_constraints_reject_partial_pairs_and_missing_provider(self):
        base="""insert into rootline_tank_observations(
            observation_id,idempotency_key,storage_fraction_numerator,
            storage_fraction_denominator,provider_message_id,storage_state,
            reservoir_state,observed_at,reporter_identity,source)
            values(%s,%s,%s,%s,%s,'OK','Unknown',now(),'telegram-owner:test','oom_sakkie_owner')"""
        invalid=(
            ("ROOTLINE-TANK-BBBBBBBBBBBBBBBBBBBBBBBB","partial-fraction",2,None,"3213"),
            ("ROOTLINE-TANK-CCCCCCCCCCCCCCCCCCCCCCCC","missing-provider",2,4,None),
        )
        for values in invalid:
            with self.subTest(identity=values[0]):
                with psycopg.connect(self.url) as connection:
                    with connection.cursor() as cursor:
                        with self.assertRaises(Exception):
                            cursor.execute(base,values)

    def test_future_tank_observation_rejected_before_database_access(self):
        result, status = record_tank_observation({
            "storage_reported_count": 4,
            "storage_state": "OK",
            "observed_at": "2999-01-01T00:00:00+00:00",
            "idempotency_key": "future",
        }, "owner-admin:test", "postgresql://must-not-connect")
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "future_observation_prohibited")


if __name__ == "__main__":
    unittest.main()
