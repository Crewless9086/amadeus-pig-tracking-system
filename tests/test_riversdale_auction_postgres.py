"""Opt-in disposable-Postgres verification for the Riversdale migration.

Set CHARLIE_DISPOSABLE_POSTGRES_URL only to an isolated test database. This
test intentionally never reads DATABASE_URL, which can point at live state.
"""
import os
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from modules.sales.riversdale_auction_list import (
    eligibility_tokens,
    read_auction_list,
    record_auction_list_events,
)


class RiversdaleAuctionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured for disposable Riversdale migration tests")
        root = Path("supabase/migrations")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""do $$ begin
                    if not exists(select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
                    if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
                    if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role nologin bypassrls; end if;
                end $$;""")
                cursor.execute((root / "202605210001_foundation_migration_log.sql").read_text(encoding="utf-8"))
                cursor.execute("""
                    create table if not exists public.orders (
                        order_id text primary key,
                        order_status text not null default 'Draft',
                        updated_at timestamptz not null default now()
                    );
                    create table if not exists public.order_lines (
                        order_line_id text primary key, order_id text, pig_id text,
                        line_status text not null default 'Draft', reserved_status text not null default 'Not_Reserved'
                    );
                    create table if not exists public.sales_transactions (
                        sale_id text primary key, sale_stream text not null,
                        sale_status text not null default 'Draft'
                    );
                    create table if not exists public.sales_transaction_items (
                        sale_item_id text primary key, sale_id text not null,
                        pig_id text, order_line_id text
                    );
                    create table if not exists public.meat_processing_batches (
                        batch_id text primary key, status text not null
                    );
                    create table if not exists public.meat_processing_batch_pigs (
                        batch_pig_id text primary key, batch_id text not null, pig_id text not null
                    );
                """)
                cursor.execute("select to_regclass('public.riversdale_auction_cycles')")
                if cursor.fetchone()[0] is None:
                    cursor.execute((root / "202607230001_create_riversdale_auction_cycles.sql").read_text(encoding="utf-8"))
                cursor.execute("select to_regclass('public.pigs')")
                if cursor.fetchone()[0] is None:
                    cursor.execute("create table public.pigs(pig_id text primary key)")
                cursor.execute("select to_regclass('public.pig_observation_events')")
                if cursor.fetchone()[0] is None:
                    cursor.execute((root / "202607200001_create_pig_observation_events.sql").read_text(encoding="utf-8"))
                cursor.execute("select to_regclass('public.riversdale_auction_candidate_reviews')")
                if cursor.fetchone()[0] is None:
                    cursor.execute((root / "202607260004_create_riversdale_auction_candidate_reviews.sql").read_text(encoding="utf-8"))
                cursor.execute("select to_regclass('public.riversdale_auction_list_events')")
                if cursor.fetchone()[0] is None:
                    cursor.execute((root / "202607260009_create_riversdale_auction_list_events.sql").read_text(encoding="utf-8"))
                cursor.execute("delete from public.meat_processing_batch_pigs")
                cursor.execute("delete from public.meat_processing_batches")
                cursor.execute("delete from public.sales_transaction_items")
                cursor.execute("delete from public.sales_transactions")
                cursor.execute("delete from public.order_lines")
                cursor.execute("delete from public.riversdale_auction_cohort_members")
                cursor.execute("delete from public.pig_active_outlets")
                cursor.execute("delete from public.riversdale_auction_cycles")

    def test_cycle_idempotency_and_active_outlet_are_unique(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.riversdale_auction_cycles
                    (auction_cycle_id, auction_date, operating_confirmed, decision_status,
                     owner_confirmed_by, owner_confirmed_at, idempotency_key, decision_hash)
                    values ('auction-a', '2026-08-05', true, 'confirmed_operating',
                            'test-owner', now(), 'auction-a-key', repeat('a', 64))""")
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("""insert into public.riversdale_auction_cycles
                        (auction_cycle_id, auction_date, operating_confirmed, decision_status,
                         owner_confirmed_by, owner_confirmed_at, idempotency_key, decision_hash)
                        values ('auction-b', '2026-08-12', true, 'confirmed_operating',
                                'test-owner', now(), 'auction-a-key', repeat('b', 64))""")
                connection.rollback()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.pig_active_outlets (outlet_assignment_id, pig_id, outlet_type, source_record_id) values ('claim-a', 'PIG-1', 'riversdale_auction', 'auction-a')")
                with self.assertRaises(psycopg.Error):
                    cursor.execute("insert into public.pig_active_outlets (outlet_assignment_id, pig_id, outlet_type, source_record_id) values ('claim-b', 'PIG-1', 'meat', 'meat-a')")
                connection.rollback()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.pig_active_outlets (outlet_assignment_id, pig_id, outlet_type, source_record_id) values ('claim-c', 'PIG-2', 'riversdale_auction', 'auction-a')")
                with self.assertRaises(psycopg.Error):
                        cursor.execute("insert into public.riversdale_auction_cohort_members (auction_cycle_id, pig_id, outlet_assignment_id) values ('auction-a', 'PIG-3', 'claim-c')")

    def test_candidate_review_privileges_are_server_insert_only(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon","authenticated"):
                    cursor.execute("select has_table_privilege(%s,'public.riversdale_auction_candidate_reviews','insert')",(role,))
                    self.assertFalse(cursor.fetchone()[0])
                cursor.execute("select has_table_privilege('service_role','public.riversdale_auction_candidate_reviews','insert')")
                self.assertTrue(cursor.fetchone()[0])
                cursor.execute("select has_table_privilege('service_role','public.riversdale_auction_candidate_reviews','update')")
                self.assertFalse(cursor.fetchone()[0])

    def test_auction_list_is_append_only_service_insert_only(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon","authenticated"):
                    cursor.execute("select has_table_privilege(%s,'public.riversdale_auction_list_events','insert')",(role,))
                    self.assertFalse(cursor.fetchone()[0])
                for privilege,expected in (("select",True),("insert",True),("update",False),("delete",False)):
                    cursor.execute("select has_table_privilege('service_role','public.riversdale_auction_list_events',%s)",(privilege,))
                    self.assertEqual(cursor.fetchone()[0],expected)
                cursor.execute("""select column_name from information_schema.columns
                    where table_schema='public' and table_name='riversdale_auction_list_events'""")
                columns = {row[0] for row in cursor.fetchall()}
                self.assertTrue({
                    "decision_sequence", "prior_event_id",
                    "eligibility_evidence_hash", "request_hash",
                }.issubset(columns))

    def test_auction_list_exact_cycle_atomic_replay_and_causal_contract(self):
        suffix = uuid.uuid4().hex[:10]
        cycle_a, cycle_b = f"cycle-a-{suffix}", f"cycle-b-{suffix}"
        pigs = [f"PIG-L-{suffix}-{index}" for index in range(1, 5)]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for pig_id in pigs:
                    cursor.execute(
                        "insert into public.pigs(pig_id) values(%s) on conflict do nothing",
                        (pig_id,),
                    )
                cursor.execute("""insert into public.riversdale_auction_cycles
                    (auction_cycle_id,auction_date,operating_confirmed,decision_status,
                     owner_confirmed_by,owner_confirmed_at,idempotency_key,decision_hash)
                    values(%s,'2026-08-05',true,'confirmed_operating','owner',
                           now()+interval '20 minutes',
                           %s,repeat('a',64))""", (cycle_a, f"cycle-key-a-{suffix}"))

        def evidence(cycle, eligible_ids):
            return {
                "success": True,
                "confirmation": {"auction_cycle_id": cycle},
                "candidate_preview": [{
                    "pig_id": pig_id,
                    "herdmaster_evidence": {
                        "withdrawal_clear": "Yes", "observed_quality": "Suitable",
                        "health_status": "Clear",
                    },
                } for pig_id in eligible_ids],
                "coordination_evidence": {"herdmaster": "canonical_allocation_rows"},
            }

        packet_a = evidence(cycle_a, pigs)
        tokens = eligibility_tokens(packet_a)
        base = {
            "action": "add", "pig_ids": [pigs[0]],
            "auction_cycle_id": cycle_a,
            "eligibility_tokens": {pigs[0]: tokens[pigs[0]]},
            "prior_event_ids": {pigs[0]: ""},
            "idempotency_key": f"add-{suffix}",
        }
        first, first_status = record_auction_list_events(
            base, actor_id="owner-admin:test",
            eligibility_loader=lambda *_: packet_a,
            database_url=self.database_url,
        )
        self.assertEqual((first_status, first["status"]), (201, "auction_list_updated"))
        replay, replay_status = record_auction_list_events(
            base, actor_id="owner-admin:test",
            eligibility_loader=lambda *_: packet_a,
            database_url=self.database_url,
        )
        self.assertEqual((replay_status, replay["status"]), (200, "auction_list_replayed"))

        listing, status = read_auction_list(database_url=self.database_url)
        self.assertEqual(status, 200)
        prior = listing["causal_heads"][pigs[0]]["event_id"]

        blocked_packet = evidence(cycle_a, [])
        removal = {
            "action": "remove", "pig_ids": [pigs[0]],
            "auction_cycle_id": cycle_a, "eligibility_tokens": {pigs[0]: ""},
            "prior_event_ids": {pigs[0]: prior},
            "idempotency_key": f"remove-{suffix}",
        }
        removed, removed_status = record_auction_list_events(
            removal, actor_id="owner-admin:test",
            eligibility_loader=lambda *_: blocked_packet,
            database_url=self.database_url,
        )
        self.assertEqual((removed_status, removed["status"]), (201, "auction_list_updated"))

        multi = {
            "action": "add", "pig_ids": [pigs[1], pigs[2]],
            "auction_cycle_id": cycle_a,
            "eligibility_tokens": {
                pigs[1]: tokens[pigs[1]], pigs[2]: tokens[pigs[2]],
            },
            "prior_event_ids": {pigs[1]: "", pigs[2]: ""},
            "idempotency_key": f"multi-{suffix}",
        }
        partial_packet = evidence(cycle_a, [pigs[1]])
        failed, failed_status = record_auction_list_events(
            multi, actor_id="owner-admin:test",
            eligibility_loader=lambda *_: partial_packet,
            database_url=self.database_url,
        )
        self.assertEqual((failed_status, failed["status"]),
                         (409, "auction_list_selection_not_allowed"))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select count(*) from public.riversdale_auction_list_events
                    where auction_cycle_id=%s and pig_id=any(%s)""",
                               (cycle_a, pigs[1:3]))
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("""insert into public.riversdale_auction_cycles
                    (auction_cycle_id,auction_date,operating_confirmed,decision_status,
                     owner_confirmed_by,owner_confirmed_at,idempotency_key,decision_hash)
                    values(%s,'2026-08-12',true,'confirmed_operating','owner',
                           now()+interval '25 minutes',%s,repeat('b',64))""",
                               (cycle_b, f"cycle-key-b-{suffix}"))
        stale, stale_status = record_auction_list_events(
            {**multi, "pig_ids": [pigs[3]],
             "eligibility_tokens": {pigs[3]: tokens[pigs[3]]},
             "prior_event_ids": {pigs[3]: ""}},
            actor_id="owner-admin:test", eligibility_loader=lambda *_: packet_a,
            database_url=self.database_url,
        )
        self.assertEqual((stale_status, stale["status"]),
                         (409, "auction_list_stale_cycle"))

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select decision_sequence,prior_event_id,recorded_at
                    from public.riversdale_auction_list_events
                    where auction_cycle_id=%s and pig_id=%s order by decision_sequence""",
                               (cycle_a, pigs[0]))
                history = cursor.fetchall()
        self.assertEqual([row[0] for row in history], [1, 2])
        self.assertIsNone(history[0][1])
        self.assertIsNotNone(history[1][1])

    def test_auction_list_concurrency_is_serialized_and_lock_order_is_canonical(self):
        suffix = uuid.uuid4().hex[:10]
        cycle = f"cycle-concurrent-{suffix}"
        pigs = [f"PIG-C-{suffix}-{index}" for index in range(1, 4)]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for pig_id in pigs:
                    cursor.execute(
                        "insert into public.pigs(pig_id) values(%s) on conflict do nothing",
                        (pig_id,),
                    )
                cursor.execute("""insert into public.riversdale_auction_cycles
                    (auction_cycle_id,auction_date,operating_confirmed,decision_status,
                     owner_confirmed_by,owner_confirmed_at,idempotency_key,decision_hash)
                    values(%s,'2026-08-19',true,'confirmed_operating','owner',
                           now()+interval '10 minutes',%s,repeat('c',64))""",
                               (cycle, f"cycle-concurrent-key-{suffix}"))
        packet = {
            "success": True,
            "confirmation": {"auction_cycle_id": cycle},
            "candidate_preview": [{
                "pig_id": pig_id,
                "herdmaster_evidence": {
                    "withdrawal_clear": "Yes", "observed_quality": "Suitable",
                    "health_status": "Clear",
                },
            } for pig_id in pigs],
            "coordination_evidence": {"herdmaster": "canonical_allocation_rows"},
        }
        tokens = eligibility_tokens(packet)

        def submit(action, selected, key, priors):
            return record_auction_list_events({
                "action": action, "pig_ids": selected,
                "auction_cycle_id": cycle,
                "eligibility_tokens": {
                    pig_id: tokens[pig_id] if action == "add" else ""
                    for pig_id in selected
                },
                "prior_event_ids": priors,
                "idempotency_key": key,
            }, actor_id="owner-admin:test",
                eligibility_loader=lambda *_: packet,
                database_url=self.database_url)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda key: submit("add", [pigs[0]], key, {pigs[0]: ""}),
                [f"same-add-a-{suffix}", f"same-add-b-{suffix}"],
            ))
        self.assertEqual(sorted(status for _, status in results), [201, 409], results)
        listing, _ = read_auction_list(database_url=self.database_url)
        first_add = listing["causal_heads"][pigs[0]]["event_id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda key: submit(
                    "remove", [pigs[0]], key, {pigs[0]: first_add}
                ),
                [f"same-remove-a-{suffix}", f"same-remove-b-{suffix}"],
            ))
        self.assertEqual(sorted(status for _, status in results), [201, 409])
        listing, _ = read_auction_list(database_url=self.database_url)
        removed_head = listing["causal_heads"][pigs[0]]["event_id"]

        # Both requests bind the same causal head. Remove is invalid before Add,
        # and stale after Add, so the final state is deterministic regardless
        # of scheduling.
        with ThreadPoolExecutor(max_workers=2) as pool:
            add_future = pool.submit(
                submit, "add", [pigs[0]], f"opposite-add-{suffix}",
                {pigs[0]: removed_head},
            )
            remove_future = pool.submit(
                submit, "remove", [pigs[0]], f"opposite-remove-{suffix}",
                {pigs[0]: removed_head},
            )
            opposite = [add_future.result(), remove_future.result()]
        self.assertEqual(sorted(status for _, status in opposite), [201, 409])
        listing, _ = read_auction_list(database_url=self.database_url)
        self.assertIn(pigs[0], {item["pig_id"] for item in listing["items"]})

        # Reversed browser order is canonicalized before any row lock.
        with ThreadPoolExecutor(max_workers=2) as pool:
            ordered = pool.submit(
                submit, "add", [pigs[1], pigs[2]], f"ordered-{suffix}",
                {pigs[1]: "", pigs[2]: ""},
            )
            reversed_order = pool.submit(
                submit, "add", [pigs[2], pigs[1]], f"reversed-{suffix}",
                {pigs[1]: "", pigs[2]: ""},
            )
            lock_results = [ordered.result(timeout=10), reversed_order.result(timeout=10)]
        self.assertEqual(sorted(status for _, status in lock_results), [201, 409])

    def test_projection_uses_sequence_when_timestamps_are_equal(self):
        suffix = uuid.uuid4().hex[:10]
        cycle, pig_id = f"cycle-equal-{suffix}", f"PIG-E-{suffix}"
        event_one, event_two = f"event-one-{suffix}", f"event-two-{suffix}"
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into public.pigs(pig_id) values(%s) on conflict do nothing",
                    (pig_id,),
                )
                cursor.execute("""insert into public.riversdale_auction_cycles
                    (auction_cycle_id,auction_date,operating_confirmed,decision_status,
                     owner_confirmed_by,owner_confirmed_at,idempotency_key,decision_hash)
                    values(%s,'2026-08-26',true,'confirmed_operating','owner',
                           now()+interval '30 minutes',%s,repeat('d',64))""",
                               (cycle, f"cycle-equal-key-{suffix}"))
                cursor.execute("""insert into public.riversdale_auction_list_events
                    (auction_list_event_id,auction_cycle_id,pig_id,event_type,
                     decision_sequence,prior_event_id,eligibility_evidence_hash,
                     owner_principal,idempotency_key,request_hash,event_hash,recorded_at)
                    values(%s,%s,%s,'added',1,null,repeat('a',64),'owner',%s,
                           repeat('b',64),repeat('c',64),timestamp with time zone '2026-07-26 12:00:00+00')""",
                               (event_one, cycle, pig_id, f"equal-one-{suffix}"))
                cursor.execute("""insert into public.riversdale_auction_list_events
                    (auction_list_event_id,auction_cycle_id,pig_id,event_type,
                     decision_sequence,prior_event_id,eligibility_evidence_hash,
                     owner_principal,idempotency_key,request_hash,event_hash,recorded_at)
                    values(%s,%s,%s,'removed',2,%s,'','owner',%s,
                           repeat('d',64),repeat('e',64),timestamp with time zone '2026-07-26 12:00:00+00')""",
                               (event_two, cycle, pig_id, event_one,
                                f"equal-two-{suffix}"))
        listing, status = read_auction_list(database_url=self.database_url)
        self.assertEqual(status, 200)
        self.assertNotIn(pig_id, {item["pig_id"] for item in listing["items"]})
        self.assertEqual(listing["causal_heads"][pig_id]["decision_sequence"], 2)

    def test_real_source_writer_tables_cannot_cross_claim_an_active_pig(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.order_lines (order_line_id, order_id, pig_id, line_status, reserved_status) values ('line-1', 'order-1', 'PIG-WRITER', 'Reserved', 'Reserved')")
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.sales_transactions (sale_id, sale_stream, sale_status) values ('sale-1', 'Slaughter', 'Confirmed')")
                with self.assertRaises(psycopg.Error):
                    cursor.execute("insert into public.sales_transaction_items (sale_item_id, sale_id, pig_id) values ('sale-item-1', 'sale-1', 'PIG-WRITER')")
                connection.rollback()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.meat_processing_batches (batch_id, status) values ('batch-1', 'Planned')")
                with self.assertRaises(psycopg.Error):
                    cursor.execute("insert into public.meat_processing_batch_pigs (batch_pig_id, batch_id, pig_id) values ('batch-pig-1', 'batch-1', 'PIG-WRITER')")
