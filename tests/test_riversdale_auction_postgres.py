"""Opt-in disposable-Postgres verification for the Riversdale migration.

Set CHARLIE_DISPOSABLE_POSTGRES_URL only to an isolated test database. This
test intentionally never reads DATABASE_URL, which can point at live state.
"""
import os
import unittest
from pathlib import Path

import psycopg


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
