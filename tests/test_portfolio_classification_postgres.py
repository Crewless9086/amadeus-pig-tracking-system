import hashlib
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg

from modules.charlie.portfolio_classification import classify_legacy_portfolio

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PREFIX = "CMQ-PORTFOLIO-TEST-"


@unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL is required")
class PortfolioClassificationPostgresTests(unittest.TestCase):
    def setUp(self):
        self._cleanup()
        self.ids = [f"{PREFIX}{number:03d}" for number in range(86)]
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            for number, mission_id in enumerate(self.ids):
                cursor.execute("""insert into public.charlie_missions
                    (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json,created_at,updated_at)
                    values (%s,'new','test',%s,%s,'P3','test','LEVEL 3','{}'::jsonb,now()+(%s||' seconds')::interval,now())""",
                    (mission_id, mission_id, mission_id, number))
                cursor.execute("""insert into public.charlie_mission_events
                    (event_id,mission_id,event_type,notes,metadata_json,created_at)
                    values (%s,%s,'created','test','{}'::jsonb,now())""", (f"EVENT-{mission_id}", mission_id))

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        if not DATABASE_URL:
            return
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("delete from public.charlie_mission_events where mission_id like %s", (PREFIX + "%",))
            cursor.execute("delete from public.charlie_missions where mission_id like %s", (PREFIX + "%",))

    def _baseline_digest(self):
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("select mission_id,status,source,title,updated_at from public.charlie_missions where mission_id=any(%s) order by created_at,mission_id", (self.ids,))
            rows = cursor.fetchall()
        snapshot = [{"mission_id": row[0], "status": row[1], "source": row[2], "title": row[3],
                     "updated_at": str(row[4]), "events": {"created": 1}} for row in rows]
        return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def test_atomic_replay_preserves_status_and_evidence(self):
        classifications = {mission_id: "historical" for mission_id in self.ids}
        baseline = self._baseline_digest()
        set_digest = hashlib.sha256(json.dumps(classifications, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with patch("modules.charlie.portfolio_classification.APPROVED_BASELINE_DIGEST", baseline), \
             patch("modules.charlie.portfolio_classification.APPROVED_SET_DIGEST", set_digest), \
             patch("modules.charlie.portfolio_classification.APPROVED_COUNTS", {"historical": 86}):
            with ThreadPoolExecutor(max_workers=2) as pool:
                initial = list(pool.map(lambda _: classify_legacy_portfolio(classifications, baseline, database_url=DATABASE_URL), range(2)))
            replay = classify_legacy_portfolio(classifications, baseline, database_url=DATABASE_URL)
        self.assertEqual(sorted(item[1] for item in initial), [200, 201])
        self.assertEqual(replay[1], 200)
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("select count(*),count(*) filter(where status='new'),count(distinct metadata_json->'portfolio_classification'->>'classification') from public.charlie_missions where mission_id=any(%s)", (self.ids,))
            self.assertEqual(cursor.fetchone(), (86, 86, 1))
            cursor.execute("select event_type,count(*) from public.charlie_mission_events where mission_id=any(%s) group by event_type order by event_type", (self.ids,))
            self.assertEqual(cursor.fetchall(), [("created", 86), ("portfolio_classified", 86)])

    def test_mid_batch_database_failure_rolls_back_every_effect(self):
        classifications = {mission_id: "historical" for mission_id in self.ids}
        baseline = self._baseline_digest()
        set_digest = hashlib.sha256(json.dumps(classifications, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("""create or replace function public.cmq_portfolio_test_fail() returns trigger language plpgsql as $$
                begin if new.mission_id = 'CMQ-PORTFOLIO-TEST-043' and new.metadata_json ? 'portfolio_classification'
                then raise exception 'injected portfolio failure'; end if; return new; end $$""")
            cursor.execute("create trigger cmq_portfolio_test_fail before update on public.charlie_missions for each row execute function public.cmq_portfolio_test_fail()")
        try:
            with patch("modules.charlie.portfolio_classification.APPROVED_BASELINE_DIGEST", baseline), \
                 patch("modules.charlie.portfolio_classification.APPROVED_SET_DIGEST", set_digest), \
                 patch("modules.charlie.portfolio_classification.APPROVED_COUNTS", {"historical": 86}):
                result, status = classify_legacy_portfolio(classifications, baseline, database_url=DATABASE_URL)
            self.assertEqual((status, result["status"]), (503, "portfolio_classification_failed"))
            with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
                cursor.execute("select count(*) from public.charlie_missions where mission_id=any(%s) and metadata_json ? 'portfolio_classification'", (self.ids,))
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("select count(*) from public.charlie_mission_events where mission_id=any(%s) and event_type='portfolio_classified'", (self.ids,))
                self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
                cursor.execute("drop trigger if exists cmq_portfolio_test_fail on public.charlie_missions")
                cursor.execute("drop function if exists public.cmq_portfolio_test_fail()")


if __name__ == "__main__":
    unittest.main()
