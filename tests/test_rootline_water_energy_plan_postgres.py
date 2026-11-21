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
    record_tank_observations_transactional,
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

    def test_independent_full_observations_commit_and_replay_atomically(self):
        payloads=[
            {"storage_fraction":[1,1],"storage_state":"FULL","provider_message_id":"3477",
             "observed_at":"2026-08-09T07:33:06+00:00","source":"oom_sakkie_owner","idempotency_key":"3477:storage"},
            {"reservoir_fraction":[1,1],"reservoir_state":"FULL","provider_message_id":"3477",
             "observed_at":"2026-08-09T07:33:06+00:00","source":"oom_sakkie_owner","idempotency_key":"3477:reservoir"},
        ]
        first,status=record_tank_observations_transactional(payloads,"telegram-owner:42",self.url)
        self.assertEqual(status,201);self.assertEqual(first["created_count"],2)
        self.assertEqual([row["kind"] for row in first["readback"]],["storage","reservoir"])
        self.assertTrue(all(row["state"]=="FULL" and row["provider_message_id"]=="3477" for row in first["readback"]))
        replay,status=record_tank_observations_transactional(payloads,"telegram-owner:42",self.url)
        self.assertEqual(status,200);self.assertEqual(replay["created_count"],0)
        self.assertEqual(replay["observation_ids"],first["observation_ids"])

    def test_batch_conflict_rolls_back_the_other_independent_observation(self):
        existing={"reservoir_fraction":[1,2],"reservoir_state":"OK","provider_message_id":"old",
            "observed_at":"2026-08-09T07:00:00+00:00","source":"oom_sakkie_owner",
            "idempotency_key":"3477:reservoir"}
        result,status=record_tank_observation(existing,"telegram-owner:42",self.url)
        self.assertEqual(status,201)
        batch=[{"storage_fraction":[1,1],"storage_state":"FULL","provider_message_id":"3477",
                "observed_at":"2026-08-09T07:33:06+00:00","source":"oom_sakkie_owner","idempotency_key":"3477:storage"},
               {"reservoir_fraction":[1,1],"reservoir_state":"FULL","provider_message_id":"3477",
                "observed_at":"2026-08-09T07:33:06+00:00","source":"oom_sakkie_owner","idempotency_key":"3477:reservoir"}]
        failed,status=record_tank_observations_transactional(batch,"telegram-owner:42",self.url)
        self.assertEqual(status,409);self.assertEqual(failed["write_outcome"],"rolled_back")
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from rootline_tank_observations where idempotency_key='3477:storage'")
                self.assertEqual(cursor.fetchone()[0],0)

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


    def _program_facts(self, at, selected=None):
        from tests.test_rootline_water_energy_plan import daily_program_facts
        return daily_program_facts(at, selected)

    def _program_counts(self):
        with psycopg.connect(self.url) as db:
            return db.execute("select count(*),max(generation) from public.rootline_water_energy_plan_generations").fetchone()

    def _initial_program(self, at, selected):
        from modules.telemetry import rootline_water_energy_plan as subject
        with psycopg.connect(self.url) as db:
            result, status = subject.ensure_saved_daily_program(selected, now=at, connection=db,
                evidence_loader=lambda **_: (self._program_facts(at, selected), selected, at),
                forecast_reader=lambda **_: ({'success':True},200))
        self.assertLess(status,400)
        self.assertTrue(result['success'])
        return result

    def test_daily_program_concurrent_different_evidence_one_initial_and_restart(self):
        from threading import Barrier
        from modules.telemetry import rootline_water_energy_plan as subject
        barrier=Barrier(2);loaded=[]
        at=datetime.fromisoformat('2026-11-19T23:30:00+02:00');selected='2026-11-20'
        def worker(number):
            facts=self._program_facts(at,selected)
            facts['power']['battery_soc_pct']+=number
            def evidence_loader(**_):
                loaded.append(number)
                return facts,selected,at
            with psycopg.connect(self.url) as db:
                barrier.wait(timeout=10)
                return subject.ensure_saved_daily_program(selected,now=at,connection=db,
                    evidence_loader=evidence_loader,forecast_reader=lambda **_:({'success':True},200))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,[0,1]))
        self.assertTrue(all(status<400 and result['success'] for result,status in results),results)
        self.assertEqual(len(loaded),1)
        self.assertEqual(self._program_counts(),(1,1))
        first=results[0][0]
        self.assertEqual(first['evidence_sha256'],results[1][0]['evidence_sha256'])
        self.assertEqual(first['daily_program'],results[1][0]['daily_program'])
        def forbidden(**_):raise AssertionError('committed programme must survive lost response without rebuilding')
        # The winner connection is closed and its return is discarded: a new
        # caller recovers only from the committed canonical generation.
        with psycopg.connect(self.url) as db:
            restarted,status=subject.ensure_saved_daily_program(selected,now=at,connection=db,
                evidence_loader=forbidden,forecast_reader=forbidden)
        self.assertEqual(restarted['generation'],1)
        self.assertEqual(restarted['evidence_sha256'],first['evidence_sha256'])
        self.assertEqual(self._program_counts(),(1,1))

    def test_daily_program_uncommitted_crash_rolls_back_before_restart(self):
        from modules.telemetry import rootline_water_energy_plan as subject
        at=datetime.fromisoformat('2026-11-19T23:30:00+02:00');selected='2026-11-20'
        with self.assertRaisesRegex(RuntimeError,'simulated process loss'):
            with psycopg.connect(self.url) as db:
                result,status=subject.ensure_saved_daily_program(selected,now=at,connection=db,
                    evidence_loader=lambda **_:(self._program_facts(at,selected),selected,at),
                    forecast_reader=lambda **_:({'success':True},200))
                self.assertEqual(status,201)
                self.assertEqual(result['generation'],1)
                raise RuntimeError('simulated process loss')
        self.assertEqual(self._program_counts(),(0,None))
        recovered=self._initial_program(at,selected)
        self.assertEqual(recovered['generation'],1)
        self.assertEqual(self._program_counts(),(1,1))

    def test_daily_program_concurrent_revision_expected_generation_cas(self):
        from threading import Barrier
        from modules.telemetry import rootline_water_energy_plan as subject
        at=datetime.fromisoformat('2026-11-20T09:00:00+02:00');selected=at.date().isoformat()
        saved=self._initial_program(at,selected);barrier=Barrier(2)
        def worker(minutes):
            later=at+timedelta(minutes=minutes)
            with psycopg.connect(self.url) as db:
                barrier.wait(timeout=10)
                return subject.revise_program_remainder(saved,self._program_facts(later),now=later,connection=db)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,[1,2]))
        self.assertTrue(all(status<400 and result['success'] for result,status in results),results)
        self.assertEqual(self._program_counts(),(2,2))
        self.assertEqual({result['generation'] for result,_ in results},{2})
        self.assertEqual(len({result['evidence_sha256'] for result,_ in results}),1)
        for result,_ in results:
            self.assertEqual(result['daily_program']['base_tasks'],saved['daily_program']['base_tasks'])
        later=at+timedelta(minutes=3)
        with psycopg.connect(self.url) as db:
            stale,status=subject.revise_program_remainder(saved,self._program_facts(later),now=later,connection=db)
        self.assertEqual(stale['generation'],2)
        self.assertEqual(self._program_counts(),(2,2))

    def _legacy_program(self, at, selected):
        from modules.telemetry import rootline_water_energy_plan as subject
        legacy=subject.build_water_energy_plan(self._program_facts(at,selected),selected,now=at)
        with psycopg.connect(self.url) as db:
            result,status=subject.append_water_energy_plan(legacy,'owner-admin:test',connection=db)
            self.assertEqual(status,201)
            current,status=subject.get_current_water_energy_plan(selected,connection=db)
        self.assertTrue(current['success'])
        return current

    def test_daily_program_exact_current_day_adoption_once(self):
        from unittest.mock import patch
        from modules.telemetry import rootline_water_energy_plan as subject
        at=datetime.fromisoformat('2026-11-20T12:00:00+02:00');selected=at.date().isoformat()
        legacy=self._legacy_program(at,selected)
        def forbidden(**_):raise AssertionError('adoption must preserve exact saved material')
        with patch.object(subject,'build_water_energy_plan',side_effect=AssertionError('no rebuild')):
            with psycopg.connect(self.url) as db:
                adopted,status=subject.ensure_saved_daily_program(selected,now=at,connection=db,
                    evidence_loader=forbidden,forecast_reader=forbidden)
        self.assertEqual(status,201)
        self.assertEqual(adopted['generation'],2)
        self.assertEqual(adopted['candidate_tasks'],legacy['candidate_tasks'])
        self.assertEqual(adopted['irrigation_auxiliary_tasks'],legacy['irrigation_auxiliary_tasks'])
        self.assertEqual(adopted['daily_program']['base_tasks'],legacy['candidate_tasks'])
        self.assertEqual(adopted['daily_program']['legacy_plan']['generation'],legacy['generation'])
        self.assertEqual(adopted['daily_program']['legacy_plan']['evidence_sha256'],legacy['evidence_sha256'])
        self.assertEqual(adopted['daily_program']['provenance'],'legacy_current_day_adoption')
        with psycopg.connect(self.url) as db:
            replay,status=subject.ensure_saved_daily_program(selected,now=at,connection=db,
                evidence_loader=forbidden,forecast_reader=forbidden)
        self.assertEqual(replay['generation'],2)
        self.assertEqual(self._program_counts(),(2,2))

    def test_daily_program_cross_midnight_concurrent_adoption_cannot_bypass_global_once(self):
        from threading import Barrier
        from modules.telemetry import rootline_water_energy_plan as subject
        before=datetime.fromisoformat('2026-11-20T23:59:59+02:00')
        after=before+timedelta(seconds=2)
        legacy={at.date().isoformat():self._legacy_program(at,at.date().isoformat()) for at in (before,after)}
        barrier=Barrier(2)
        def worker(at):
            with psycopg.connect(self.url) as db:
                barrier.wait(timeout=10)
                return subject.ensure_saved_daily_program(at.date().isoformat(),now=at,connection=db,
                    evidence_loader=lambda **_:(_ for _ in ()).throw(AssertionError('no evidence without forecast')),
                    forecast_reader=lambda **_:({'success':False},200))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[before,after]))
        adopted=[result for result,status in results if result.get('daily_program')]
        held=[result for result,status in results if result.get('status')=='nightly_forecast_missing_new_starts_held']
        self.assertEqual(len(adopted),1,results)
        self.assertEqual(len(held),1,results)
        self.assertEqual(self._program_counts(),(3,2))
        winner=adopted[0]
        self.assertEqual(winner['candidate_tasks'],legacy[winner['operating_date']]['candidate_tasks'])
        # A fresh connection on the other date still cannot adopt after midnight.
        loser=next(at for at in (before,after) if at.date().isoformat()!=winner['operating_date'])
        with psycopg.connect(self.url) as db:
            retry,status=subject.ensure_saved_daily_program(loser.date().isoformat(),now=loser,connection=db,
                forecast_reader=lambda **_:({'success':False},200))
            versions=db.execute("select count(*) from public.rootline_water_energy_plan_generations where plan_json->'daily_program'->>'version'=%s",(subject.DAILY_PROGRAM_VERSION,)).fetchone()[0]
        self.assertEqual(retry['status'],'nightly_forecast_missing_new_starts_held')
        self.assertEqual(versions,1)
        self.assertEqual(self._program_counts(),(3,2))

    def test_daily_program_missing_current_or_future_legacy_cannot_adopt(self):
        from modules.telemetry import rootline_water_energy_plan as subject
        at=datetime.fromisoformat('2026-11-20T12:00:00+02:00')
        self._legacy_program(at,'2026-11-21')
        for selected in ('2026-11-20','2026-11-21'):
            with self.subTest(selected=selected), psycopg.connect(self.url) as db:
                held,status=subject.ensure_saved_daily_program(selected,now=at,connection=db,
                    forecast_reader=lambda **_:({'success':False},200))
                self.assertEqual(held['status'],'nightly_forecast_missing_new_starts_held')
        self.assertEqual(self._program_counts(),(1,1))



    def test_daily_program_history_sql_bounds_context_but_keeps_old_allocation_and_latest_debt(self):
        from copy import deepcopy
        from modules.telemetry import rootline_water_energy_plan as subject
        unresolved={'origin_id':'old-open','zone_id':'B12345','operating_date':'2026-08-01',
            'original_minutes':120,'remaining_minutes':60,'repayments':['verified-old-half']}
        resolved={'origin_id':'old-closed','zone_id':'C12345','operating_date':'2026-08-01',
            'original_minutes':120,'remaining_minutes':0,'repayments':['verified-full']}
        for selected in ('2026-08-01','2026-08-02','2026-11-18','2026-11-19','2026-11-21'):
            at=datetime.fromisoformat(selected+'T09:00:00+02:00')
            plan=subject.build_daily_program(self._program_facts(at,selected),selected,now=at)
            plan['daily_program']['carry_origins']=deepcopy([unresolved,resolved])
            if selected=='2026-11-21':
                plan['daily_program']['carry_origins'][0]['remaining_minutes']=0
            for task in plan['daily_program']['base_tasks']:
                task['old_full_context_marker']='must_not_expand_old_context'
                task['carry_allocations']=[]
            if selected=='2026-08-01':
                plan['daily_program']['base_tasks'][0]['carry_allocations']=[{'origin_id':'old-open','minutes':60}]
            subject._hash_program(plan)
            with psycopg.connect(self.url) as db:
                result,status=subject.append_water_energy_plan(plan,'owner-admin:test',connection=db)
                self.assertEqual(status,201,result)
        with psycopg.connect(self.url) as db:
            history=subject.read_program_history('2026-11-20',connection=db)
        self.assertNotIn('error_type',history)
        self.assertEqual(history['status'],'partial')
        self.assertEqual([p['operating_date'] for p in history['plans']],['2026-11-18','2026-11-19'])
        self.assertEqual([p['operating_date'] for p in history['allocation_plans']],['2026-08-01'])
        compact=history['allocation_plans'][0]['tasks']
        self.assertEqual(len(compact),1)
        self.assertEqual(set(compact[0]),{'task_id','carry_allocations'})
        self.assertEqual(compact[0]['carry_allocations'],[{'origin_id':'old-open','minutes':60}])
        self.assertEqual(history['carry_origins'],[unresolved,resolved])
        self.assertEqual(history['unresolved_origins'],[unresolved])
        self.assertEqual(history['from_date'],'2026-10-19')
        self.assertEqual(history['completed_weeks_through_date'],'2026-11-15')
        self.assertEqual(len(history['missing_plan_dates']),28)


if __name__ == "__main__":
    unittest.main()
