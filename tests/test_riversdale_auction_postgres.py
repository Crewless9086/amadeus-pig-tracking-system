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
                cursor.execute((root / "202607230001_create_riversdale_auction_cycles.sql").read_text(encoding="utf-8"))
                cursor.execute("delete from public.meat_processing_batch_pigs")
                cursor.execute("delete from public.meat_processing_batches")
                cursor.execute("delete from public.sales_transaction_items")
                cursor.execute("delete from public.sales_transactions")
                cursor.execute("delete from public.order_lines")
                cursor.execute("delete from public.riversdale_auction_cohort_members")
                cursor.execute("delete from public.pig_active_outlets")
                cursor.execute("delete from public.riversdale_auction_cycles")

    def test_cycle_date_and_active_outlet_are_unique(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("insert into public.riversdale_auction_cycles (auction_cycle_id, auction_date) values ('auction-a', '2026-08-05')")
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("insert into public.riversdale_auction_cycles (auction_cycle_id, auction_date) values ('auction-b', '2026-08-05')")
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
