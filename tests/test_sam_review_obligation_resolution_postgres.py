"""Disposable-PostgreSQL proof for the append-only review resolution rail."""
import copy
import hashlib
import json
import os
import pathlib
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.sales.sam_review_obligation_resolution import resolve_review_obligation
from modules.sales.sam_review_obligation_resolution import canonical_sha256
from tests.test_sam_review_obligation_resolution import evidence, represented, review

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SamReviewObligationResolutionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        base = (ROOT / "supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql").read_text()
        migration = (ROOT / "supabase/migrations/202607310002_create_sam_review_obligation_resolutions.sql").read_text()
        with psycopg.connect(cls.url) as connection:
            connection.execute("drop table if exists public.sam_review_obligation_resolution_events cascade")
            connection.execute("drop table if exists public.sam_live_stock_conversation_review_events cascade")
            connection.execute("do $$ begin if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role; end if; end $$")
            connection.execute("grant usage on schema public to service_role")
            connection.execute(base)
            connection.execute("create table if not exists public.litter_supersessions(operation_id text primary key,historical_reference_row_ids jsonb not null default '[]'::jsonb)")
            connection.execute("create or replace function public.refresh_litter_supersession_write_guards() returns void language sql as $$ select $$")
            connection.execute(migration)

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8].upper()
        self.review_ids = [f"SAM-REVIEW-{self.suffix}-{i:03d}" for i in range(362)]
        with psycopg.connect(self.url) as connection:
            for i, review_id in enumerate(self.review_ids):
                connection.execute(
                    "insert into public.sam_live_stock_conversation_review_events(review_event_id,chatwoot_conversation_id,chatwoot_message_id,decision_json) values(%s,%s,%s,%s::jsonb)",
                    (review_id, f"CONV-{self.suffix}-{i:03d}", f"IN-{self.suffix}-{i:03d}", json.dumps({"canonical_inventory_snapshot":{"selected_pig_ids":["PIG-2026-1AC2"]}})),
                )

    def packet(self, index=0, cutoff="2026-07-31T12:00:00+00:00"):
        row = review(index + 1)
        row.update(review_event_id=self.review_ids[index], chatwoot_conversation_id=f"CONV-{self.suffix}-{index:03d}", chatwoot_message_id=f"IN-{self.suffix}-{index:03d}")
        with psycopg.connect(self.url) as connection:
            decision_text = connection.execute(
                "select decision_json::text from public.sam_live_stock_conversation_review_events where review_event_id=%s",
                (row["review_event_id"],),
            ).fetchone()[0]
        row["decision_json_sha256"] = hashlib.sha256(decision_text.encode()).hexdigest()
        row["decision_json_text"] = decision_text
        proof = evidence(index + 1)
        proof["identity"].update(review_event_id=self.review_ids[index], conversation_id=row["chatwoot_conversation_id"], bound_inbound_message_id=row["chatwoot_message_id"], latest_inbound_message_id=row["chatwoot_message_id"])
        proof["public_chronology"] = [{"message_id": row["chatwoot_message_id"], "message_type": "incoming"}]
        proof["chronology_sha256"] = canonical_sha256(proof["public_chronology"])
        proof["delivery"].update(
            conversation_id=row["chatwoot_conversation_id"],
            inbound_message_id=row["chatwoot_message_id"],
        )
        proof["delivery"]["evidence_payload"] = {
            key: value for key, value in proof["delivery"].items()
            if key not in {"evidence_id", "evidence_sha256", "evidence_payload"}
        }
        proof["delivery"]["evidence_sha256"] = canonical_sha256(proof["delivery"]["evidence_payload"])
        proof["chronology_cutoff_at"] = cutoff
        return resolve_review_obligation(review=row, evidence=proof, represented_identity=represented())

    def service(self):
        connection = psycopg.connect(self.url, autocommit=True)
        connection.execute("set role service_role")
        return connection

    def record(self, packet):
        with self.service() as connection:
            return connection.execute("select public.record_sam_review_obligation_resolution(%s::jsonb)", (json.dumps(packet),)).fetchone()[0]

    def test_362_rows_are_unchanged_and_resolution_is_append_only(self):
        with psycopg.connect(self.url) as connection:
            before = connection.execute("select review_event_id,decision_json::text from public.sam_live_stock_conversation_review_events where review_event_id=any(%s) order by review_event_id", (self.review_ids,)).fetchall()
        for i in range(362):
            self.assertTrue(self.record(self.packet(i)))
        with psycopg.connect(self.url) as connection:
            after = connection.execute("select review_event_id,decision_json::text from public.sam_live_stock_conversation_review_events where review_event_id=any(%s) order by review_event_id", (self.review_ids,)).fetchall()
            self.assertEqual(connection.execute("select count(*) from public.sam_review_obligation_resolution_events where review_event_id=any(%s)", (self.review_ids,)).fetchone()[0], 362)
        self.assertEqual(before, after)
        with psycopg.connect(self.url) as connection:
            with self.assertRaisesRegex(psycopg.Error, "append-only"):
                connection.execute("update public.sam_review_obligation_resolution_events set source_generation='changed' where review_event_id=%s", (self.review_ids[0],))
            connection.rollback()
            with self.assertRaisesRegex(psycopg.Error, "append-only"):
                connection.execute("delete from public.sam_review_obligation_resolution_events where review_event_id=%s", (self.review_ids[0],))
        with self.service() as connection:
            with self.assertRaisesRegex(psycopg.Error, "permission denied"):
                connection.execute("delete from public.sam_review_obligation_resolution_events where review_event_id=%s", (self.review_ids[0],))

    def test_replay_concurrency_stale_and_changed_content_fail_closed(self):
        packet = self.packet()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.record(packet), range(2)))
        self.assertEqual(sorted(results), [False, True])
        stale = self.packet(cutoff="2026-07-31T11:59:59+00:00")
        with self.assertRaisesRegex(psycopg.Error, "stale chronology"):
            self.record(stale)
        changed = copy.deepcopy(packet)
        changed["chronology_sha256"] = "9" * 64
        from modules.sales.sam_review_obligation_resolution import resolution_payload_sha256, resolution_identity
        changed["event_payload_sha256"] = resolution_payload_sha256(changed)
        changed["resolution_event_id"] = resolution_identity(changed)
        with self.assertRaisesRegex(psycopg.Error, "identical chronology cutoff"):
            self.record(changed)

    def test_unprivileged_write_and_same_animal_mapping_are_denied(self):
        packet = self.packet()
        packet["canonical_same_animal_pig_id"] = "PIG-B1A8-CHILD"
        from modules.sales.sam_review_obligation_resolution import resolution_payload_sha256, resolution_identity
        packet["event_payload_sha256"] = resolution_payload_sha256(packet)
        packet["resolution_event_id"] = resolution_identity(packet)
        with self.assertRaises(psycopg.Error):
            self.record(packet)
        with psycopg.connect(self.url) as connection:
            with self.assertRaises(psycopg.Error):
                connection.execute("select public.record_sam_review_obligation_resolution(%s::jsonb)", (json.dumps(self.packet(1)),))

    def test_direct_rpc_payload_tamper_and_same_id_different_body_are_denied(self):
        packet = self.packet()
        tampered = copy.deepcopy(packet)
        tampered["resolution_action"] = "completed"
        with self.assertRaisesRegex(psycopg.Error, "deterministic resolution identity"):
            self.record(tampered)
        self.assertTrue(self.record(packet))
        same_identity_changed_body = copy.deepcopy(packet)
        same_identity_changed_body["source_generation"] = "forged-generation"
        with self.assertRaisesRegex(psycopg.Error, "deterministic resolution identity"):
            self.record(same_identity_changed_body)
        changed_errors = copy.deepcopy(packet)
        changed_errors["resolution_errors"] = ["forged_error"]
        with self.assertRaisesRegex(psycopg.Error, "deterministic resolution identity"):
            self.record(changed_errors)

    def test_consumer_projection_keeps_containment_and_surfaces_only_safe_work(self):
        with psycopg.connect(self.url) as connection:
            connection.execute(
                "insert into public.litter_supersessions(operation_id,historical_reference_row_ids) values(%s,%s::jsonb)",
                (f"ZIGAY-{self.suffix}", json.dumps(self.review_ids)),
            )
            self.assertEqual(connection.execute(
                "select count(*) from public.current_actionable_sam_live_stock_review_events where review_event_id=any(%s)",
                (self.review_ids,),
            ).fetchone()[0], 0)
        self.record(self.packet(0))
        with psycopg.connect(self.url) as connection:
            row = connection.execute(
                "select safe_to_send,sam_reply_excerpt,recommended_action,resolution_action,canonical_same_animal_pig_id from public.current_actionable_sam_live_stock_review_events where review_event_id=%s",
                (self.review_ids[0],),
            ).fetchone()
        self.assertEqual(row, (False, "", "replan_from_current_canonical_inventory", "active", None))


if __name__ == "__main__":
    unittest.main()
