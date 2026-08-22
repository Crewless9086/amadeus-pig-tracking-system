import hashlib
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_render_production_migrations import (
    ALLOWLIST,
    EXPECTED_LITTER_SUPERSESSION_REASONS,
    EXPECTED_PROTECTED_ACTION_KINDS,
    AllowedMigration,
    _constraint_readback,
    _metadata,
    run,
)


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
            "202608220001_extend_litter_supersession_for_fact_corrections.sql",
            "202608220002_allow_herdmaster_farrowing_protected_claims.sql",
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

    def test_litter_release_migrations_are_exact_and_fail_closed(self):
        correction_sql = Path(
            "supabase/migrations/202608220001_extend_litter_supersession_for_fact_corrections.sql"
        ).read_text(encoding="utf-8")
        action_sql = Path(
            "supabase/migrations/202608220002_allow_herdmaster_farrowing_protected_claims.sql"
        ).read_text(encoding="utf-8")
        target = re.search(
            r"target_action_kinds constant text\[\] := array\[(.*?)\]::text\[\];",
            action_sql,
            re.DOTALL,
        )
        predecessor = re.search(
            r"predecessor_action_kinds constant text\[\] := array\[(.*?)\]::text\[\];",
            action_sql,
            re.DOTALL,
        )
        self.assertIsNotNone(target)
        self.assertIsNotNone(predecessor)
        self.assertEqual(
            tuple(re.findall(r"'([^']+)'", target.group(1))),
            EXPECTED_PROTECTED_ACTION_KINDS,
        )
        self.assertEqual(
            set(re.findall(r"'([^']+)'", predecessor.group(1))),
            set(EXPECTED_PROTECTED_ACTION_KINDS) - {"herdmaster_record_farrowing_litter"},
        )
        self.assertIn("canonical protected action-kind constraint mismatch", action_sql)
        self.assertNotIn("create table", action_sql.lower())
        self.assertNotIn("drop table", action_sql.lower())
        self.assertIn("'fact_correction'", correction_sql)
        self.assertIn("create or replace function public.validate_litter_supersession()", correction_sql)
        self.assertIn(
            "202608220001_extend_litter_supersession_for_fact_corrections",
            correction_sql,
        )

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
            db.execute("drop table if exists public.litter_supersessions cascade")
            db.execute("drop table if exists public.litter_correction_authorizations cascade")
            db.execute("drop table if exists public.mating_events cascade")
            db.execute("drop table if exists public.litters cascade")
            db.execute("drop table if exists public.pigs cascade")
            db.execute("create schema app_private")
            db.execute("""create table app_private.migration_log(
              migration_id text primary key,description text not null,
              applied_at timestamptz not null default now())""")
            db.execute("""create table app_private.oom_protected_action_claims(
              callback_token text primary key,
              action_kind text not null,
              constraint oom_protected_action_claims_action_kind_check
              check (action_kind in (
                'mortality','grouped_weights','herdmaster_breeding_grouped',
                'rootline_irrigation_segment','sam_sale_payment',
                'beacon_private_album_finish','beacon_media_review',
                'rootline_fertilizer_mixer_commissioning',
                'rootline_fertilizer_mixer_presence_refresh',
                'rootline_delegated_family','beacon_campaign_review',
                'documents_green_print','documents_green_physical_acceptance'))
            )""")
            db.execute("""create table public.sales_transactions(
              sale_id text primary key,sale_stream text,sale_status text,linked_order_id text,
              gross_total numeric(12,2),deductions_total numeric(12,2),net_total numeric(12,2),
              received_total numeric(12,2),payment_status text,
              payment_received_evidence_json jsonb,payment_evidence_sha256 text)""")
            db.execute("create table public.pigs(pig_id text primary key,litter_id text)")
            db.execute("""create table public.litters(
              litter_id text primary key,sow_pig_id text,boar_pig_id text,
              farrowing_date date)""")
            db.execute("""create table public.litter_correction_authorizations(
              authorization_id text primary key,operation_id text,
              preview_sha256 text,decision_status text)""")
            db.execute("""create table public.mating_events(
              mating_id text primary key,sow_pig_id text,related_litter_id text)""")
            db.execute("""create table public.litter_supersessions(
              operation_id text primary key,retained_litter_id text,
              superseded_litter_id text,authorization_id text,mating_id text not null,
              preview_sha256 text,reason text,
              superseded_child_ids jsonb not null default '[]'::jsonb,
              retained_child_ids jsonb not null default '[]'::jsonb,
              constraint litter_supersessions_reason_check
                check (reason in ('duplicate_creation_same_farrowing')))
            """)
        first = run(DATABASE_URL, ENV)
        second = run(DATABASE_URL, ENV)
        self.assertEqual(first["migrations"][0]["outcome"], "applied")
        self.assertEqual(second["migrations"][0]["outcome"], "already_applied")
        self.assertEqual(first["migrations"][0]["receipt_id"],
                         second["migrations"][0]["receipt_id"])
        self.assertTrue(all(row["outcome"] == "applied" for row in first["migrations"]))
        self.assertTrue(all(row["outcome"] == "already_applied" for row in second["migrations"]))
        self.assertEqual(
            first["migrations"][-2]["readback"]["reason_values"],
            list(EXPECTED_LITTER_SUPERSESSION_REASONS),
        )
        self.assertEqual(
            first["migrations"][-1]["readback"]["action_kinds"],
            list(EXPECTED_PROTECTED_ACTION_KINDS),
        )
        self.assertEqual(
            second["migrations"][-2]["readback"],
            first["migrations"][-2]["readback"],
        )
        self.assertEqual(
            second["migrations"][-1]["readback"],
            first["migrations"][-1]["readback"],
        )
        with psycopg.connect(DATABASE_URL) as db:
            _, reasons = _constraint_readback(
                db, "public", "litter_supersessions", "litter_supersessions_reason_check"
            )
            _, action_kinds = _constraint_readback(
                db,
                "app_private",
                "oom_protected_action_claims",
                "oom_protected_action_claims_action_kind_check",
            )
            self.assertEqual(reasons, EXPECTED_LITTER_SUPERSESSION_REASONS)
            self.assertEqual(action_kinds, EXPECTED_PROTECTED_ACTION_KINDS)
            self.assertEqual(
                db.execute(
                    """select migration_id from app_private.migration_log
                        where migration_id like '20260822000%'
                        order by migration_id"""
                ).fetchall(),
                [
                    ("202608220001_extend_litter_supersession_for_fact_corrections",),
                    ("202608220002_allow_herdmaster_farrowing_protected_claims",),
                ],
            )
            function_definition = db.execute(
                """select pg_catalog.pg_get_functiondef(p.oid)
                     from pg_catalog.pg_proc p
                     join pg_catalog.pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public'
                      and p.proname='validate_litter_supersession'"""
            ).fetchone()[0]
            self.assertIn("exact litter child allowlists required", function_definition)
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "append-only"):
                db.execute("update app_private.production_migration_receipts set ordinal=2")
            db.rollback()

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_b_action_kind_replay_and_schema_mismatch_fail_closed(self):
        import psycopg

        migration = Path(
            "supabase/migrations/202608220002_allow_herdmaster_farrowing_protected_claims.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(migration)
            db.execute(migration)
            db.commit()
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(
                """alter table app_private.oom_protected_action_claims
                     drop constraint oom_protected_action_claims_action_kind_check;
                   alter table app_private.oom_protected_action_claims
                     add constraint oom_protected_action_claims_action_kind_check
                     check (action_kind in ('unexpected_action'))"""
            )
            before = db.execute(
                """select pg_catalog.pg_get_constraintdef(c.oid)
                     from pg_catalog.pg_constraint c
                     where c.conrelid='app_private.oom_protected_action_claims'::regclass
                       and c.conname='oom_protected_action_claims_action_kind_check'"""
            ).fetchone()[0]
            db.execute("savepoint mismatch_attempt")
            with self.assertRaisesRegex(
                psycopg.errors.RaiseException,
                "canonical protected action-kind constraint mismatch",
            ):
                db.execute(migration)
            db.execute("rollback to savepoint mismatch_attempt")
            after = db.execute(
                """select pg_catalog.pg_get_constraintdef(c.oid)
                     from pg_catalog.pg_constraint c
                     where c.conrelid='app_private.oom_protected_action_claims'::regclass
                       and c.conname='oom_protected_action_claims_action_kind_check'"""
            ).fetchone()[0]
            self.assertEqual(after, before)
            db.rollback()

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_c_runner_failure_rolls_back_partial_schema(self):
        import psycopg

        item = AllowedMigration(
            migration_id="209901010001_test_runner_rollback",
            filename="209901010001_test_runner_rollback.sql",
            sha256="0" * 64,
        )
        failing_sql = """create table public.render_migration_rollback_probe(id integer);
        do $$ begin raise exception 'expected rollback probe'; end $$;"""
        with patch("scripts.run_render_production_migrations.ALLOWLIST", (item,)), patch(
            "scripts.run_render_production_migrations._load_sql", return_value=failing_sql
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "migration_failed_and_rolled_back:209901010001_test_runner_rollback",
            ):
                run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            self.assertIsNone(
                db.execute(
                    "select to_regclass('public.render_migration_rollback_probe')"
                ).fetchone()[0]
            )
            self.assertEqual(
                db.execute(
                    """select outcome,error_class
                         from app_private.production_migration_receipts
                        where migration_id='209901010001_test_runner_rollback'
                        order by applied_at desc limit 1"""
                ).fetchone(),
                ("failed", "RaiseException"),
            )
