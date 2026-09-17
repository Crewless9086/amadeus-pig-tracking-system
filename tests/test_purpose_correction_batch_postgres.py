"""Disposable PostgreSQL proof for exact purpose correction execution."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

import psycopg

from modules.pig_weights.purpose_correction_batch_service import (
    approve_correction_batch,
    create_correction_batch,
    execute_correction_batch,
    preview_correction_batch,
)


class PurposeCorrectionBatchPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        with psycopg.connect(cls.url) as db:
            cls.original_canonical_pigs_view = db.execute(
                "select pg_get_viewdef('public.current_canonical_pigs'::regclass, true)"
            ).fetchone()[0]
            db.execute("create schema if not exists app_private")
            db.execute("""create table if not exists public.pig_purpose_correction_batches(
                batch_id text primary key,idempotency_key text not null unique,
                status text not null,decisions_json jsonb not null,decision_hash text not null,
                created_by text not null,created_at timestamptz not null default now(),
                owner_approved_by text,owner_approved_at timestamptz,executed_by text,executed_at timestamptz)""")
            db.execute("""create table if not exists public.operational_events(
                event_id text primary key,idempotency_key text not null unique,
                schema_version text not null default '1',event_type text not null,
                domain text not null,aggregate_type text not null,aggregate_id text not null,
                source_system text not null,source_record_id text not null default '',
                authority_tier text not null,privacy_class text not null,
                actor_type text not null default 'system',actor_id text not null default '',
                correlation_id text not null default '',causation_id text not null default '',
                occurred_at timestamptz not null,recorded_at timestamptz not null default now(),
                freshness_at timestamptz not null,payload_json jsonb not null,
                provenance_json jsonb not null,created_at timestamptz not null default now())""")
            db.execute("drop view public.current_canonical_pigs")
            db.execute("""create view public.current_canonical_pigs as
                select pig_id,tag_number,status,on_farm,purpose from public.pigs""")
            db.execute("""create or replace function public.purpose_test_reject_update()
                returns trigger language plpgsql as $$ begin
                  if new.pig_id like 'PURPOSE-ROLLBACK-B-%' then return null; end if;
                  return new;
                end $$""")

    @classmethod
    def tearDownClass(cls):
        if not getattr(cls, "url", None):
            return
        with psycopg.connect(cls.url) as db:
            db.execute("drop view if exists public.current_canonical_pigs")
            db.execute(
                "create view public.current_canonical_pigs as "
                + cls.original_canonical_pigs_view
            )

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:10]
        self.ids = [f"PURPOSE-TAG-123-{self.suffix}", f"PURPOSE-TAG-151-{self.suffix}"]
        self.cleanup_ids = list(self.ids)
        with psycopg.connect(self.url) as db:
            for pig_id, tag, weight in zip(self.ids, ("123", "151"), (5.6, 4.0)):
                db.execute("insert into public.pigs(pig_id,tag_number,status,on_farm,purpose,animal_type,sex,wean_date) values(%s,%s,'Active',true,'Unknown','Weaner','Male','2026-08-11')", (pig_id, tag))
                db.execute("insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg,source) values(%s,%s,'2026-08-11',%s,'purpose_test')", (f"W-{pig_id}", pig_id, weight))

    def tearDown(self):
        with psycopg.connect(self.url) as db:
            db.execute("drop trigger if exists purpose_test_reject_update on public.pigs")
            db.execute("delete from public.operational_events where aggregate_id=any(%s)", (self.cleanup_ids,))
            db.execute("""delete from public.pig_purpose_correction_batches where exists (
                select 1 from jsonb_array_elements(coalesce(decisions_json->'decisions',decisions_json)) item
                where item->>'pig_id'=any(%s))""", (self.cleanup_ids,))
            db.execute("delete from public.pig_weight_events where pig_id=any(%s)", (self.cleanup_ids,))
            db.execute("delete from public.pigs where pig_id=any(%s)", (self.cleanup_ids,))

    def decisions(self):
        return [{"pig_id": pig_id, "purpose": "Sale", "reason": "Owner sale review", "note": tag}
                for pig_id, tag in zip(self.ids, ("Tag 123", "Tag 151"))]

    def prepare(self, key):
        preview, status = preview_correction_batch(
            self.decisions(), actor_id="owner-admin:postgres",
            return_to="/orders/ORD-2026-A6EC6D",
            connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertEqual(status, 200)
        created, status = create_correction_batch(
            self.decisions(), idempotency_key=key, actor_id="owner-admin:postgres",
            confirmation_binding=preview["confirmation_binding"],
            return_to="/orders/ORD-2026-A6EC6D",
            connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertIn(status, (200, 201))
        approved, status = approve_correction_batch(
            created["batch_id"], actor_id="owner-admin:postgres",
            connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertEqual(status, 200)
        return created["batch_id"]

    def test_exact_execution_readback_replay_and_concurrency(self):
        with patch.dict(os.environ, {"OWNER_SESSION_SECRET": "postgres-purpose-secret"}):
            batch_id = self.prepare(f"purpose-exact-{self.suffix}")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _index: execute_correction_batch(
                    batch_id, actor_id="owner-admin:postgres", today=date(2026, 8, 16),
                    connect_factory=lambda _url: psycopg.connect(self.url)), range(2)))
        statuses = sorted(result[0]["status"] for result in results)
        self.assertIn("correction_batch_executed", statuses)
        executed = next(result[0] for result in results if result[0]["status"] == "correction_batch_executed")
        replay, replay_status = execute_correction_batch(
            batch_id, actor_id="owner-admin:postgres", today=date(2026, 8, 16),
            connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "correction_batch_duplicate_execution")
        self.assertEqual(executed["rows_updated"], 2)
        self.assertEqual(len(executed["canonical_readback"]), 2)
        self.assertTrue(all(row["purpose"] == "Sale" for row in executed["canonical_readback"]))
        self.assertEqual(replay["rows_updated"], 0)
        cross_owner, cross_status = execute_correction_batch(
            batch_id, actor_id="owner-admin:different", today=date(2026, 8, 16),
            connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertEqual(cross_status, 403)
        self.assertEqual(cross_owner["status"], "correction_batch_owner_mismatch")
        with psycopg.connect(self.url) as db:
            self.assertEqual(db.execute("select count(*) from public.operational_events where aggregate_id=any(%s)", (self.ids,)).fetchone()[0], 2)

    def test_partial_update_rolls_back_every_pig_and_event(self):
        self.ids = [f"PURPOSE-ROLLBACK-A-{self.suffix}", f"PURPOSE-ROLLBACK-B-{self.suffix}"]
        self.cleanup_ids.extend(self.ids)
        with psycopg.connect(self.url) as db:
            for pig_id, tag in zip(self.ids, ("123", "151")):
                db.execute("insert into public.pigs(pig_id,tag_number,status,on_farm,purpose,animal_type,sex,wean_date) values(%s,%s,'Active',true,'Unknown','Weaner','Male','2026-08-11')", (pig_id, tag))
                db.execute("insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg,source) values(%s,%s,'2026-08-11',5,'purpose_test')", (f"W-{pig_id}", pig_id))
            db.execute("create trigger purpose_test_reject_update before update on public.pigs for each row execute function public.purpose_test_reject_update()")
        with patch.dict(os.environ, {"OWNER_SESSION_SECRET": "postgres-purpose-secret"}):
            batch_id = self.prepare(f"purpose-rollback-{self.suffix}")
            result, status = execute_correction_batch(
                batch_id, actor_id="owner-admin:postgres", today=date(2026, 8, 16),
                connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertEqual(status, 409)
        self.assertEqual(result["rows_updated"], 0)
        with psycopg.connect(self.url) as db:
            self.assertEqual([row[0] for row in db.execute("select purpose from public.pigs where pig_id=any(%s) order by pig_id", (self.ids,))], ["Unknown", "Unknown"])
            self.assertEqual(db.execute("select count(*) from public.operational_events where aggregate_id=any(%s)", (self.ids,)).fetchone()[0], 0)

    def test_stale_confirmed_snapshot_and_conflicting_idempotency_fail_closed(self):
        key = f"purpose-stale-{self.suffix}"
        with patch.dict(os.environ, {"OWNER_SESSION_SECRET": "postgres-purpose-secret"}):
            batch_id = self.prepare(key)
            changed = [{**item, "purpose": "Grow_Out"} for item in self.decisions()]
            preview, preview_status = preview_correction_batch(
                changed, actor_id="owner-admin:postgres",
                return_to="/orders/ORD-2026-A6EC6D",
                connect_factory=lambda _url: psycopg.connect(self.url))
            self.assertEqual(preview_status, 200)
            conflict, conflict_status = create_correction_batch(
                changed, idempotency_key=key, actor_id="owner-admin:postgres",
                confirmation_binding=preview["confirmation_binding"],
                return_to="/orders/ORD-2026-A6EC6D",
                connect_factory=lambda _url: psycopg.connect(self.url))
            self.assertEqual(conflict_status, 409)
            self.assertEqual(conflict["status"], "correction_batch_idempotency_conflict")
            with psycopg.connect(self.url) as db:
                db.execute("update public.pigs set purpose='Meat' where pig_id=%s", (self.ids[0],))
            stale, stale_status = execute_correction_batch(
                batch_id, actor_id="owner-admin:postgres", today=date(2026, 8, 16),
                connect_factory=lambda _url: psycopg.connect(self.url))
        self.assertEqual(stale_status, 409)
        self.assertEqual(stale["status"], "correction_batch_preview_stale_or_altered")
        self.assertEqual(stale["rows_updated"], 0)
        with psycopg.connect(self.url) as db:
            purposes = dict(db.execute(
                "select pig_id,purpose from public.pigs where pig_id=any(%s)",
                (self.ids,)).fetchall())
            self.assertEqual(purposes[self.ids[0]], "Meat")
            self.assertEqual(purposes[self.ids[1]], "Unknown")
            self.assertEqual(db.execute(
                "select count(*) from public.operational_events where aggregate_id=any(%s)",
                (self.ids,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
