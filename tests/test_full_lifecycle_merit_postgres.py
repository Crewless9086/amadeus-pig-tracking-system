"""Disposable-PostgreSQL proof for the read-only merit snapshot."""
import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg

from modules.pig_weights.farm_supabase_read_service import get_full_lifecycle_merit


class FullLifecycleMeritPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        with psycopg.connect(cls.url) as c:
            c.execute("create table if not exists public.merit_test_pigs(pig_id text primary key,name text,tag_number text,sex text,litter_id text)")
            c.execute("create or replace view public.current_canonical_pigs as select * from public.merit_test_pigs")
            c.execute("create table if not exists public.merit_test_litters(litter_id text primary key,supersedes_litter_id text,sow_pig_id text,boar_pig_id text,farrowing_date date,litter_status text,born_alive numeric,weaned_count numeric,management_context text,season_context text,environment_context text,feed_context text,health_context text)")
            c.execute("create or replace view public.current_canonical_litters as select * from public.merit_test_litters")
            c.execute("create or replace view public.historical_litter_representations as select l.*,null::text supersession_operation_id,null::text retained_litter_id,false is_superseded from public.merit_test_litters l")
            c.execute("create table if not exists public.mating_events(mating_id text primary key,mating_date date)")
            c.execute("create table if not exists public.pig_observation_events(observation_event_id text primary key,pig_id text,observed_at timestamptz,supersedes_observation_event_id text,factual_note text)")
            c.execute("create table if not exists public.pig_lifecycle_events(lifecycle_event_id text primary key,pig_id text,effective_at timestamptz,recorded_at timestamptz default now(),supersedes_lifecycle_event_id text)")
            c.execute("create table if not exists public.pig_weight_events(weight_event_id text primary key,pig_id text,weight_date date,weight_kg numeric)")
            c.execute("create table if not exists public.pig_medical_events(medical_event_id text primary key,pig_id text,treatment_date date)")
            c.execute("create table if not exists public.sales_transactions(sale_id text primary key,sale_date timestamptz,sale_stream text,sale_channel text,sale_status text)")
            c.execute("create table if not exists public.sales_transaction_items(sale_item_id text primary key,sale_id text,pig_id text)")
            c.execute("create table if not exists public.meat_processing_batches(batch_id text primary key,status text,updated_at timestamptz default now())")
            c.execute("create table if not exists public.meat_processing_batch_pigs(batch_pig_id text primary key,batch_id text,pig_id text)")
            c.execute("create table if not exists public.meat_processing_batch_events(event_id text primary key,batch_id text,pig_id text,event_type text,event_date date,created_at timestamptz default now())")

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:10]
        self.pig = f"MERIT-{self.suffix}"
        with psycopg.connect(self.url) as c:
            c.execute("insert into public.merit_test_pigs values(%s,'Bonnie','TAG-1','Female',null)", (self.pig,))
            for i in range(1, 4):
                c.execute("insert into public.merit_test_litters values(%s,null,%s,'BOAR','2026-0" + str(i) + "-01','Weaned',8,7,'same','same','same','same','same')", (f"L-{self.suffix}-{i}", self.pig))

    def tearDown(self):
        with psycopg.connect(self.url) as c:
            c.execute("delete from public.merit_test_litters where sow_pig_id=%s", (self.pig,))
            c.execute("delete from public.merit_test_pigs where pig_id=%s", (self.pig,))

    def _counts(self):
        with psycopg.connect(self.url) as c:
            return tuple(c.execute(f"select count(*) from public.{table}").fetchone()[0] for table in (
                "merit_test_pigs", "merit_test_litters", "mating_events", "pig_observation_events",
                "pig_lifecycle_events", "pig_weight_events", "pig_medical_events"))

    def test_repeatable_read_packet_is_complete_and_zero_write(self):
        before = self._counts()
        result = get_full_lifecycle_merit(date.today(), self.pig, connect_factory=lambda _url: psycopg.connect(self.url))
        after = self._counts()
        self.assertEqual(before, after)
        self.assertTrue(result["success"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(result["read_progress"]["connection_count"], 1)
        self.assertEqual(result["read_progress"]["query_count"], 10)
        self.assertEqual(result["rows"][0]["identity"]["display_name"], "Bonnie")
        self.assertEqual(result["rows"][0]["confidence"]["label"], "High")

    def test_concurrent_append_is_not_mixed_into_established_snapshot(self):
        late_id = f"L-{self.suffix}-LATE"
        with psycopg.connect(self.url) as c:
            c.execute("create or replace view public.current_canonical_pigs as select p.* from public.merit_test_pigs p cross join lateral (select pg_sleep(0.6)) pause")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    get_full_lifecycle_merit, date.today(), self.pig,
                    lambda _url: psycopg.connect(self.url),
                )
                time.sleep(0.2)
                with psycopg.connect(self.url) as writer:
                    writer.execute("insert into public.merit_test_litters values(%s,null,%s,'BOAR','2026-04-01','Weaned',8,7,'same','same','same','same','same')", (late_id, self.pig))
                result = future.result(timeout=10)
            self.assertNotIn(late_id, result["rows"][0]["evidence_lineage"]["litter_ids"])
        finally:
            with psycopg.connect(self.url) as c:
                c.execute("delete from public.merit_test_litters where litter_id=%s", (late_id,))
                c.execute("create or replace view public.current_canonical_pigs as select * from public.merit_test_pigs")


if __name__ == "__main__":
    unittest.main()
