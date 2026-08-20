import hashlib
import os
import unittest
from pathlib import Path

from scripts.run_render_production_migrations import ALLOWLIST, _metadata, run


ENV = {
    "RENDER": "true",
    "RENDER_GIT_COMMIT": "a" * 40,
    "RENDER_MIGRATION_EXPECTED_COMMIT": "a" * 40,
    "RENDER_SERVICE_ID": "srv-production",
    "RENDER_INSTANCE_ID": "job-instance",
}


DATABASE_URL = os.getenv("RENDER_MIGRATION_TEST_DATABASE_URL", "").strip()


class RenderProductionMigrationRailTests(unittest.TestCase):
    def test_allowlist_is_ordered_exact_and_checksum_bound(self):
        self.assertEqual([row.filename for row in ALLOWLIST], [
            "202608190002_create_beacon_protected_publication_consumer.sql",
            "202608200001_add_sales_financial_disposition.sql",
            "202608200002_create_pig_welfare_case_lifecycle.sql",
        ])
        self.assertEqual(list(ALLOWLIST), sorted(ALLOWLIST, key=lambda row: row.migration_id))
        for row in ALLOWLIST:
            sql = (Path("supabase/migrations") / row.filename).read_text(encoding="utf-8")
            canonical = sql.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), row.sha256)

    def test_render_identity_is_mandatory_and_exact(self):
        with self.assertRaisesRegex(RuntimeError, "render_runtime_required"):
            _metadata({})
        with self.assertRaisesRegex(RuntimeError, "exact_render_source_commit_required"):
            _metadata(dict(ENV, RENDER_GIT_COMMIT="main"))
        with self.assertRaisesRegex(RuntimeError, "render_source_deploy_binding_mismatch"):
            _metadata(dict(ENV, RENDER_MIGRATION_EXPECTED_COMMIT="b" * 40))
        self.assertEqual(_metadata(ENV), ("a" * 40, "srv-production", "job-instance"))

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_apply_replay_and_immutable_receipt(self):
        import psycopg

        with psycopg.connect(DATABASE_URL) as connection:
            database_name = connection.info.dbname
        self.assertEqual(database_name, "render_migration_rail_test",
                         "refusing fixture outside render_migration_rail_test")
        with psycopg.connect(DATABASE_URL, autocommit=True) as db:
            db.execute("""do $$ begin
              if not exists (select 1 from pg_roles where rolname='anon') then
                create role anon;
              end if;
              if not exists (select 1 from pg_roles where rolname='authenticated') then
                create role authenticated;
              end if;
            end $$""")
            db.execute("drop schema if exists app_private cascade")
            db.execute("drop table if exists public.pig_welfare_cases cascade")
            db.execute("drop table if exists public.sales_transactions cascade")
            db.execute("drop table if exists public.pigs cascade")
            db.execute("create schema app_private")
            db.execute("""create table app_private.migration_log(
              migration_id text primary key,description text not null,
              applied_at timestamptz not null default now())""")
            db.execute("""create table app_private.oom_protected_action_claims(
              callback_token text primary key)""")
            db.execute("""create table public.sales_transactions(
              sale_id text primary key,sale_stream text,sale_status text,linked_order_id text,
              gross_total numeric(12,2),deductions_total numeric(12,2),net_total numeric(12,2),
              received_total numeric(12,2),payment_status text,
              payment_received_evidence_json jsonb,payment_evidence_sha256 text)""")
            db.execute("create table public.pigs(pig_id text primary key)")
        first = run(DATABASE_URL, ENV)
        second = run(DATABASE_URL, ENV)
        self.assertEqual(first["migrations"][0]["outcome"], "applied")
        self.assertEqual(second["migrations"][0]["outcome"], "already_applied")
        self.assertEqual(first["migrations"][0]["receipt_id"],
                         second["migrations"][0]["receipt_id"])
        with psycopg.connect(DATABASE_URL) as db:
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "append-only"):
                db.execute("update app_private.production_migration_receipts set ordinal=2")
