"""Disposable-Postgres service proof for Phase 2 breeding observations."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from modules.pig_weights.herdmaster_breeding_observation_service import (
    record_observation,
)
from modules.pig_weights.bulk_body_condition_service import record_body_condition_batch


class BreedingObservationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        root = Path("supabase/migrations")
        migration = (
            root / "202607200001_create_pig_observation_events.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    (root / "202605210001_foundation_migration_log.sql")
                    .read_text(encoding="utf-8")
                )
                cursor.execute("""
                    do $$ begin
                      if not exists(select 1 from pg_roles where rolname='anon')
                        then create role anon nologin; end if;
                      if not exists(select 1 from pg_roles where rolname='authenticated')
                        then create role authenticated nologin; end if;
                      if not exists(select 1 from pg_roles where rolname='service_role')
                        then create role service_role nologin bypassrls; end if;
                    end $$;
                    create table if not exists public.pigs(pig_id text primary key);
                    alter table public.pigs add column if not exists status text;
                    alter table public.pigs add column if not exists on_farm boolean;
                    alter table public.pigs add column if not exists sex text;
                    alter table public.pigs add column if not exists animal_type text;
                    create or replace view public.current_canonical_pigs as
                      select * from public.pigs;
                    grant select, update on public.pigs to service_role;
                    grant select on public.current_canonical_pigs to service_role;
                    delete from app_private.migration_log
                    where migration_id='202607200001_create_pig_observation_events';
                    drop table if exists public.pig_observation_events cascade;
                """)
                cursor.execute(migration)
                cursor.execute("""
                    insert into public.pigs(
                      pig_id,status,on_farm,sex,animal_type
                    ) values ('PHASE2-SOW','Active',true,'Female','Sow')
                    on conflict (pig_id) do update set
                      status=excluded.status,on_farm=excluded.on_farm,
                      sex=excluded.sex,animal_type=excluded.animal_type
                """)
                cursor.execute("""insert into public.pigs(
                      pig_id,status,on_farm,sex,animal_type)
                    values ('PHASE2-SOW-B','Active',true,'Female','Sow')
                    on conflict (pig_id) do update set status=excluded.status,
                      on_farm=excluded.on_farm,sex=excluded.sex,
                      animal_type=excluded.animal_type""")
            connection.commit()

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    drop table if exists public.pig_observation_events cascade;
                    drop view if exists public.current_canonical_pigs;
                    drop function if exists
                      public.pig_observation_events_validate_supersession();
                    drop function if exists
                      public.pig_observation_events_block_update_delete();
                    delete from app_private.migration_log
                    where migration_id='202607200001_create_pig_observation_events';
                """)
            connection.commit()

    @classmethod
    def connect_as_service(cls, _url):
        return psycopg.connect(cls.url, options="-c role=service_role")

    def payload(self, key, **extra):
        value = {
            "pig_id": "PHASE2-SOW",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "body_condition_score": 3,
            "visible_build": "even",
            "feet_legs_movement": "no_visible_concern",
            "visible_injury": "none_observed",
            "standing_heat": "not_observed",
            "temperament": "calm",
            "suitability_concern": "none_observed",
            "factual_note": "Observed standing and walking.",
            "follow_up": "Owner review.",
            "idempotency_key": key,
        }
        value.update(extra)
        return value

    def count(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select count(*) from public.pig_observation_events"
                )
                return cursor.fetchone()[0]

    def test_service_role_append_replay_conflict_and_immutable_privileges(self):
        baseline = self.count()
        exact_payload = self.payload("PHASE2-IDEM-1")
        result, status = record_observation(
            exact_payload, actor_id="owner-admin:test",
            connect_factory=self.connect_as_service,
        )
        self.assertEqual((status, result["status"]), (201, "observation_recorded"))
        self.assertEqual(self.count(), baseline + 1)
        replay, status = record_observation(
            exact_payload, actor_id="owner-admin:test",
            connect_factory=self.connect_as_service,
        )
        self.assertEqual((status, replay["status"]), (
            200, "observation_replayed_withheld",
        ))
        self.assertEqual(self.count(), baseline + 1)
        changed, status = record_observation(
            {**exact_payload, "factual_note": "Changed evidence."},
            actor_id="owner-admin:test",
            connect_factory=self.connect_as_service,
        )
        self.assertEqual((status, changed["status"]), (
            409, "observation_idempotency_conflict",
        ))
        self.assertEqual(self.count(), baseline + 1)
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                for privilege, expected in (
                    ("SELECT", True), ("INSERT", True), ("UPDATE", False),
                    ("DELETE", False), ("TRUNCATE", False),
                ):
                    cursor.execute(
                        "select has_table_privilege("
                        "'service_role','public.pig_observation_events',%s)",
                        (privilege,),
                    )
                    self.assertEqual(cursor.fetchone()[0], expected)

    def test_concurrent_supersession_has_one_winner_and_no_fork(self):
        prior, status = record_observation(
            self.payload("PHASE2-PRIOR"), actor_id="owner-admin:test",
            connect_factory=self.connect_as_service,
        )
        self.assertEqual(status, 201)

        def correct(key):
            return record_observation(
                self.payload(
                    key,
                    factual_note=f"Correction {key}.",
                    supersedes_observation_event_id=prior["observation_event_id"],
                ),
                actor_id="owner-admin:test",
                connect_factory=self.connect_as_service,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(correct, ("PHASE2-CORRECT-A", "PHASE2-CORRECT-B")))
        self.assertEqual(sorted(status for _result, status in results), [201, 409])
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select count(*) from public.pig_observation_events
                    where supersedes_observation_event_id=%s
                """, (prior["observation_event_id"],))
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_bulk_retry_after_commit_reuses_original_predecessor(self):
        prior, status = record_observation(self.payload("BULK-PRIOR"),
            actor_id="owner-admin:test", connect_factory=self.connect_as_service)
        self.assertEqual(status, 201)
        batch = {"draft_id": "DRAFT-RESPONSE-LOSS", "observed_date": "2026-08-24",
            "rows": [{"pig_id": "PHASE2-SOW", "body_condition_score": 2}]}
        first, status = record_body_condition_batch(batch, actor_id="owner-admin:test",
            connect_factory=self.connect_as_service)
        self.assertEqual(status, 201, first)
        event = first["events"][0]
        self.assertEqual(event["supersedes_observation_event_id"], prior["observation_event_id"])
        replay, status = record_body_condition_batch(batch, actor_id="owner-admin:test",
            connect_factory=self.connect_as_service)
        self.assertEqual((status, replay["replayed_count"]), (200, 1), replay)
        self.assertEqual(replay["events"][0]["supersedes_observation_event_id"],
                         prior["observation_event_id"])

    def test_concurrent_bulk_replay_creates_one_event(self):
        batch = {"draft_id": "DRAFT-CONCURRENT", "observed_date": "2026-08-24",
            "rows": [{"pig_id": "PHASE2-SOW-B", "body_condition_score": 3}]}
        def run(_value):
            return record_body_condition_batch(batch, actor_id="owner-admin:test",
                connect_factory=self.connect_as_service)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertEqual(sorted(status for _result, status in results), [200, 201], results)
        with psycopg.connect(self.url) as connection, connection.cursor() as cursor:
            cursor.execute("""select count(*) from public.pig_observation_events
                where idempotency_key='bulk-bcs:DRAFT-CONCURRENT:PHASE2-SOW-B'""")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_multi_pig_partial_reports_committed_event_and_failed_pig(self):
        batch = {"draft_id": "DRAFT-PARTIAL", "observed_date": "2026-08-24",
            "rows": [{"pig_id": "PHASE2-SOW-B", "body_condition_score": 2},
                     {"pig_id": "ZZ-MISSING", "body_condition_score": 3}]}
        result, status = record_body_condition_batch(batch, actor_id="owner-admin:test",
            connect_factory=self.connect_as_service)
        self.assertEqual(status, 409, result)
        self.assertEqual(result["events"][0]["pig_id"], "PHASE2-SOW-B")
        self.assertEqual(result["failed_pig_id"], "ZZ-MISSING")
        self.assertTrue(result["draft_must_be_retained"])

    def test_same_day_pre_noon_bulk_timestamp_is_not_future(self):
        server_now = datetime(2026, 8, 24, 6, 15, tzinfo=timezone.utc)
        batch = {"draft_id": "DRAFT-PRE-NOON", "observed_date": "2026-08-24",
            "rows": [{"pig_id": "PHASE2-SOW-B", "body_condition_score": 3.5}]}
        result, status = record_body_condition_batch(batch, actor_id="owner-admin:test",
            connect_factory=self.connect_as_service, now=server_now)
        self.assertEqual(status, 201, result)
        with psycopg.connect(self.url) as connection, connection.cursor() as cursor:
            cursor.execute("""select observed_at from public.pig_observation_events
                where idempotency_key='bulk-bcs:DRAFT-PRE-NOON:PHASE2-SOW-B'""")
            observed = cursor.fetchone()[0]
        self.assertEqual(observed, server_now)
        self.assertLessEqual(observed, server_now)


if __name__ == "__main__":
    unittest.main()
