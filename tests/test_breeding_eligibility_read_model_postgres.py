"""Disposable-PostgreSQL proof for effective breeding-condition projection."""
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from modules.pig_weights.mating_routes import _project_breeding_observations


class BreedingEligibilityReadModelPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        with psycopg.connect(cls.url) as connection:
            connection.execute("create table if not exists public.pigs(pig_id text primary key)")
            if connection.execute("select to_regclass('public.pig_observation_events')").fetchone()[0] is None:
                connection.execute(Path("supabase/migrations/202607200001_create_pig_observation_events.sql").read_text(encoding="utf-8"))

    def setUp(self):
        suffix = uuid.uuid4().hex[:12].upper()
        self.pig_id = f"ELIGIBILITY-{suffix}"
        self.low_id = f"OBS-LOW-{suffix}"
        self.clear_id = f"OBS-CLEAR-{suffix}"
        self.now = datetime.now(timezone.utc)
        with psycopg.connect(self.url) as connection:
            connection.execute("insert into public.pigs(pig_id) values(%s)", (self.pig_id,))

    def tearDown(self):
        with psycopg.connect(self.url) as connection:
            connection.execute("alter table public.pig_observation_events disable trigger trg_pig_observation_events_no_update_delete")
            connection.execute("delete from public.pig_observation_events where pig_id=%s", (self.pig_id,))
            connection.execute("alter table public.pig_observation_events enable trigger trg_pig_observation_events_no_update_delete")
            connection.execute("delete from public.pigs where pig_id=%s", (self.pig_id,))

    def insert(self, event_id, score, observed_at, supersedes=None):
        with psycopg.connect(self.url) as connection:
            connection.execute("""insert into public.pig_observation_events(
              observation_event_id,pig_id,observed_at,observer_reference,
              observation_category,severity,factual_note,measurements_json,
              source_system,source_reference,idempotency_key,
              supersedes_observation_event_id)
              values(%s,%s,%s,'owner-admin:test','body_condition','informational',
              %s,jsonb_build_object('body_condition_score',%s),'owner',%s,%s,%s)""",
              (event_id,self.pig_id,observed_at,f"BCS {score}.",score,event_id,event_id,supersedes))

    def rows(self):
        with psycopg.connect(self.url) as connection:
            return connection.execute("""select pig_id,observed_at,observation_category,
              measurements_json,observation_event_id,recorded_at,factual_note,
              supersedes_observation_event_id from public.pig_observation_events
              where pig_id=%s order by observed_at desc""", (self.pig_id,)).fetchall()

    def count(self):
        with psycopg.connect(self.url) as connection:
            return connection.execute("select count(*) from public.pig_observation_events where pig_id=%s", (self.pig_id,)).fetchone()[0]

    def test_correction_selects_effective_row_and_read_is_zero_write(self):
        self.insert(self.low_id, 1, self.now-timedelta(days=2))
        self.insert(self.clear_id, 3, self.now-timedelta(days=1), self.low_id)
        before = self.count()
        projected = _project_breeding_observations(self.rows(), now=self.now)
        after = self.count()
        self.assertEqual((before, after), (2, 2))
        self.assertEqual(projected[self.pig_id]["body_condition_score"], 3)
        self.assertEqual(projected[self.pig_id]["body_condition_observation_event_id"], self.clear_id)

    def test_time_alone_does_not_remove_stale_low_condition(self):
        self.insert(self.low_id, 2, self.now-timedelta(days=40))
        projected = _project_breeding_observations(self.rows(), now=self.now)
        self.assertEqual(projected[self.pig_id]["body_condition_score"], 2)
        self.assertEqual(projected[self.pig_id]["body_condition_freshness"], "Stale")


if __name__ == "__main__":
    unittest.main()
