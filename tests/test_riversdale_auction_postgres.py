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
                cursor.execute((root / "202607230001_create_riversdale_auction_cycles.sql").read_text(encoding="utf-8"))
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
