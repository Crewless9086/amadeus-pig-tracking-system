import hashlib
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_render_production_migrations import (
    ALLOWLIST,
    BASELINE_ELIGIBLE_IDS,
    CATALOG_RELATIONS,
    EXPECTED_MIGRATION_LOG_DESCRIPTIONS,
    EXPECTED_LITTER_SUPERSESSION_REASONS,
    EXPECTED_PROTECTED_ACTION_KINDS,
    AllowedMigration,
    _constraint_readback,
    _catalog_snapshot,
    _function_readback,
    _migration_function_body,
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


def _install_litter_function(db, filename):
    body = _migration_function_body(filename)
    db.execute(
        "create or replace function public.validate_litter_supersession() "
        "returns trigger language plpgsql as $function$"
        + body
        + "$function$;"
    )


def _reset_disposable_database(*, unexpected_litter_reason=False):
    import psycopg

    with psycopg.connect(DATABASE_URL) as connection:
        database_name = connection.info.dbname
    if database_name != "render_migration_rail_test":
        raise AssertionError("refusing fixture outside render_migration_rail_test")
    reason_members = (
        "'duplicate_creation_same_farrowing','unexpected_reason'"
        if unexpected_litter_reason
        else "'duplicate_creation_same_farrowing'"
    )
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
        db.execute("drop table if exists public.pig_welfare_case_events cascade")
        db.execute("drop table if exists public.pig_welfare_case_fact_links cascade")
        db.execute("drop table if exists public.sales_transactions cascade")
        db.execute("drop table if exists public.litter_supersessions cascade")
        db.execute("drop table if exists public.litter_correction_authorizations cascade")
        db.execute("drop table if exists public.mating_events cascade")
        db.execute("drop table if exists public.litters cascade")
        db.execute("drop table if exists public.pigs cascade")
        db.execute("drop function if exists public.validate_litter_supersession() cascade")
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
        db.execute(f"""create table public.litter_supersessions(
          operation_id text primary key,retained_litter_id text,
          superseded_litter_id text,authorization_id text,mating_id text not null,
          preview_sha256 text,reason text,
          superseded_child_ids jsonb not null default '[]'::jsonb,
          retained_child_ids jsonb not null default '[]'::jsonb,
          constraint litter_supersessions_reason_check
            check (reason in ({reason_members})))
        """)
        _install_litter_function(
            db, "202607300001_create_litter_supersession_rail.sql"
        )
        db.execute(
            "create trigger validate_litter_supersession_insert "
            "before insert on public.litter_supersessions for each row "
            "execute function public.validate_litter_supersession()"
        )


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
    def test_disposable_postgres_a_unexpected_predecessor_stops_before_mutation(self):
        import psycopg

        _reset_disposable_database(unexpected_litter_reason=True)
        with psycopg.connect(DATABASE_URL) as db:
            before_constraint = _constraint_readback(
                db,
                "public",
                "litter_supersessions",
                "litter_supersessions_reason_check",
            )[0]
            before_function = db.execute(
                "select prosrc from pg_proc where oid="
                "'public.validate_litter_supersession()'::regprocedure"
            ).fetchone()[0]
        with self.assertRaisesRegex(
            RuntimeError,
            "migration_failed_and_rolled_back:"
            "202608220001_extend_litter_supersession_for_fact_corrections",
        ):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            after_constraint = _constraint_readback(
                db,
                "public",
                "litter_supersessions",
                "litter_supersessions_reason_check",
            )[0]
            after_function = db.execute(
                "select prosrc from pg_proc where oid="
                "'public.validate_litter_supersession()'::regprocedure"
            ).fetchone()[0]
            self.assertEqual(after_constraint, before_constraint)
            self.assertEqual(after_function, before_function)
            self.assertIsNone(
                db.execute(
                    "select 1 from app_private.migration_log where migration_id="
                    "'202608220001_extend_litter_supersession_for_fact_corrections'"
                ).fetchone()
            )
            self.assertIsNone(
                db.execute(
                    "select to_regclass('app_private.production_migration_receipts')"
                ).fetchone()[0]
            )

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_apply_replay_and_immutable_receipt(self):
        import psycopg

        _reset_disposable_database()
        first = run(DATABASE_URL, ENV)
        second = run(DATABASE_URL, ENV)
        self.assertEqual(first["migrations"][0]["outcome"], "applied")
        self.assertEqual(second["migrations"][0]["outcome"], "already_applied")
        self.assertEqual(first["migrations"][0]["receipt_id"],
                         second["migrations"][0]["receipt_id"])
        self.assertTrue(all(row["outcome"] == "applied" for row in first["migrations"]))
        self.assertTrue(all(row["outcome"] == "already_applied" for row in second["migrations"]))
        for ordinal, (applied, replayed, allowed) in enumerate(
            zip(first["migrations"], second["migrations"], ALLOWLIST), 1
        ):
            self.assertEqual(
                applied["receipt_identity"]["identity_sha256"],
                replayed["receipt_identity"]["identity_sha256"],
            )
            self.assertTrue(applied["receipt_identity"]["identity_anchored_now"])
            self.assertFalse(replayed["receipt_identity"]["identity_anchored_now"])
            self.assertEqual(applied["receipt_identity"]["migration_filename"], allowed.filename)
            self.assertEqual(applied["receipt_identity"]["ordinal"], ordinal)
            self.assertEqual(applied["receipt_identity"]["render_service_id"], ENV["RENDER_SERVICE_ID"])
            self.assertTrue(applied["receipt_identity"]["render_instance_id"])
            self.assertEqual(applied["receipt_guard"], replayed["receipt_guard"])
        self.assertEqual(
            first["migrations"][-2]["readback"]["reason_values"],
            list(EXPECTED_LITTER_SUPERSESSION_REASONS),
        )
        self.assertEqual(
            first["migrations"][-1]["readback"]["action_kinds"],
            list(EXPECTED_PROTECTED_ACTION_KINDS),
        )
        self.assertEqual(
            first["migrations"][-2]["readback"]["validator_trigger"]["enabled"],
            "O",
        )
        self.assertEqual(
            first["migrations"][-1]["readback"]["protected_claim_acl"],
            {"unauthorized_privilege_count": 0},
        )
        self.assertTrue(
            first["migrations"][-2]["readback"]["migration_log_description_sha256"]
        )
        self.assertTrue(
            first["migrations"][-1]["readback"]["migration_log_description_sha256"]
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
                "canonical protected action-kind constraint structure mismatch",
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
        members = ",".join(f"'{value}'" for value in EXPECTED_PROTECTED_ACTION_KINDS)
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(
                "alter table app_private.oom_protected_action_claims "
                "drop constraint oom_protected_action_claims_action_kind_check; "
                "alter table app_private.oom_protected_action_claims "
                "add constraint oom_protected_action_claims_action_kind_check "
                f"check (true or action_kind in ({members}))"
            )
            before = db.execute(
                """select pg_catalog.pg_get_constraintdef(c.oid)
                     from pg_catalog.pg_constraint c
                    where c.conrelid='app_private.oom_protected_action_claims'::regclass
                      and c.conname='oom_protected_action_claims_action_kind_check'"""
            ).fetchone()[0]
            db.execute("savepoint weakened_attempt")
            with self.assertRaisesRegex(
                psycopg.errors.RaiseException,
                "canonical protected action-kind constraint structure mismatch",
            ):
                db.execute(migration)
            db.execute("rollback to savepoint weakened_attempt")
            after = db.execute(
                """select pg_catalog.pg_get_constraintdef(c.oid)
                     from pg_catalog.pg_constraint c
                    where c.conrelid='app_private.oom_protected_action_claims'::regclass
                      and c.conname='oom_protected_action_claims_action_kind_check'"""
            ).fetchone()[0]
            self.assertEqual(after, before)
            db.rollback()

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_d_runner_rejects_weakened_constraint_with_same_literals(self):
        import psycopg

        _reset_disposable_database()
        run(DATABASE_URL, ENV)
        members = ",".join(f"'{value}'" for value in EXPECTED_PROTECTED_ACTION_KINDS)
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(
                "alter table app_private.oom_protected_action_claims "
                "drop constraint oom_protected_action_claims_action_kind_check; "
                "alter table app_private.oom_protected_action_claims "
                "add constraint oom_protected_action_claims_action_kind_check "
                f"check (true or action_kind in ({members}))"
            )
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            definition = db.execute(
                """select pg_catalog.pg_get_constraintdef(c.oid)
                     from pg_catalog.pg_constraint c
                    where c.conrelid='app_private.oom_protected_action_claims'::regclass
                      and c.conname='oom_protected_action_claims_action_kind_check'"""
            ).fetchone()[0]
            self.assertIn("true", definition.lower())
            db.execute(
                "alter table app_private.oom_protected_action_claims "
                "drop constraint oom_protected_action_claims_action_kind_check; "
                "alter table app_private.oom_protected_action_claims "
                "add constraint oom_protected_action_claims_action_kind_check "
                f"check (action_kind in ({members}))"
            )
            db.commit()

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_e_runner_rejects_phrase_comment_stub_function(self):
        import psycopg

        _reset_disposable_database()
        run(DATABASE_URL, ENV)
        comments = " ".join(
            (
                "cross-sow or cross-farrowing supersession denied",
                "duplicate supersession father mismatch",
                "durable owner confirmation does not match operation",
                "retained litter mating linkage mismatch",
                "exact litter child allowlists required",
            )
        )
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(
                "create or replace function public.validate_litter_supersession() "
                "returns trigger language plpgsql as $stub$begin "
                f"/* {comments} */ return null; end;$stub$;"
            )
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            self.assertIn(
                "return null",
                db.execute(
                    "select prosrc from pg_proc where oid="
                    "'public.validate_litter_supersession()'::regprocedure"
                ).fetchone()[0].lower(),
            )
            _install_litter_function(
                db, "202608220001_extend_litter_supersession_for_fact_corrections.sql"
            )
            db.commit()
            _function_readback(
                db, "202608220001_extend_litter_supersession_for_fact_corrections.sql"
            )

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_f_runner_rejects_wrong_log_descriptions(self):
        import psycopg

        for migration_id in EXPECTED_MIGRATION_LOG_DESCRIPTIONS:
            with self.subTest(migration_id=migration_id):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    db.execute(
                        "update app_private.migration_log "
                        "set description='wrong description' where migration_id=%s",
                        (migration_id,),
                    )
                    db.commit()
                with self.assertRaisesRegex(
                    RuntimeError, "migration_readback_log_mismatch"
                ):
                    run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    self.assertEqual(
                        db.execute(
                            "select description from app_private.migration_log "
                            "where migration_id=%s",
                            (migration_id,),
                        ).fetchone()[0],
                        "wrong description",
                    )
                    db.execute(
                        "update app_private.migration_log set description=%s "
                        "where migration_id=%s",
                        (
                            EXPECTED_MIGRATION_LOG_DESCRIPTIONS[migration_id],
                            migration_id,
                        ),
                    )
                    db.commit()

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_g_rejects_missing_disabled_or_wrong_validator_trigger(self):
        import psycopg

        attacks = ("missing", "disabled", "wrong_function")
        for attack in attacks:
            with self.subTest(attack=attack):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    if attack == "missing":
                        db.execute(
                            "drop trigger validate_litter_supersession_insert "
                            "on public.litter_supersessions"
                        )
                    elif attack == "disabled":
                        db.execute(
                            "alter table public.litter_supersessions disable trigger "
                            "validate_litter_supersession_insert"
                        )
                    else:
                        db.execute(
                            "create or replace function public.wrong_litter_validator() "
                            "returns trigger language plpgsql as $$begin return new; end$$; "
                            "drop trigger validate_litter_supersession_insert "
                            "on public.litter_supersessions; "
                            "create trigger validate_litter_supersession_insert "
                            "before insert on public.litter_supersessions for each row "
                            "execute function public.wrong_litter_validator()"
                        )
                    db.commit()
                with self.assertRaisesRegex(
                    RuntimeError, "migration_catalog_drift",
                ):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_h_rejects_each_applied_receipt_identity_drift(self):
        import psycopg

        attacks = {
            "filename": "migration_filename='wrong.sql'",
            "ordinal": "ordinal=999",
            "service": "render_service_id='srv-wrong'",
            "instance": "render_instance_id='attacker-instance'",
            "source_commit": "source_commit='" + ("b" * 40) + "'",
            "applied_at": "applied_at=applied_at + interval '1 second'",
            "checksum": "migration_sha256='" + ("0" * 64) + "'",
        }
        migration_id = "202608220002_allow_herdmaster_farrowing_protected_claims"
        for field, assignment in attacks.items():
            with self.subTest(field=field):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    db.execute(
                        "alter table app_private.production_migration_receipts "
                        "disable trigger trg_guard_production_migration_receipts"
                    )
                    db.execute(
                        "update app_private.production_migration_receipts set "
                        + assignment
                        + " where migration_id=%s and outcome='applied'",
                        (migration_id,),
                    )
                    db.execute(
                        "alter table app_private.production_migration_receipts "
                        "enable trigger trg_guard_production_migration_receipts"
                    )
                    db.commit()
                expected = (
                    "applied_migration_checksum_conflict"
                    if field == "checksum"
                    else "migration_receipt_identity_anchor_mismatch"
                    if field in {"instance", "source_commit", "applied_at"}
                    else "migration_receipt_identity_mismatch"
                )
                with self.assertRaisesRegex(RuntimeError, expected):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_i_rejects_receipt_guard_drift_before_bootstrap(self):
        import psycopg

        for attack in ("missing", "disabled", "wrong_function"):
            with self.subTest(attack=attack):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    if attack == "missing":
                        db.execute(
                            "drop trigger trg_guard_production_migration_receipts "
                            "on app_private.production_migration_receipts"
                        )
                    elif attack == "disabled":
                        db.execute(
                            "alter table app_private.production_migration_receipts "
                            "disable trigger trg_guard_production_migration_receipts"
                        )
                    else:
                        db.execute(
                            "alter table app_private.production_migration_receipts "
                            "disable trigger trg_guard_production_migration_receipts; "
                            "create or replace function app_private.guard_production_migration_receipts() "
                            "returns trigger language plpgsql as $$begin return old; end$$; "
                            "alter table app_private.production_migration_receipts "
                            "enable trigger trg_guard_production_migration_receipts"
                        )
                    db.commit()
                with self.assertRaisesRegex(
                    RuntimeError,
                    "migration_receipt_guard_",
                ):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_j_rejects_protected_claim_acl_drift(self):
        import psycopg

        for role in (
            "public", "anon", "authenticated", "anon_inherited", "unlisted_login"
        ):
            with self.subTest(role=role):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    if role == "anon_inherited":
                        db.execute(
                            "do $$ begin create role unauthorized_claim_reader; "
                            "exception when duplicate_object then null; end $$; "
                            "grant unauthorized_claim_reader to anon; "
                            "grant select on app_private.oom_protected_action_claims "
                            "to unauthorized_claim_reader"
                        )
                    elif role == "unlisted_login":
                        db.execute(
                            "do $$ begin create role unlisted_claim_reader login; "
                            "exception when duplicate_object then null; end $$; "
                            "grant select on app_private.oom_protected_action_claims "
                            "to unlisted_claim_reader"
                        )
                    else:
                        db.execute(
                            "grant select,insert,update,delete on "
                            f"app_private.oom_protected_action_claims to {role}"
                        )
                    db.commit()
                with self.assertRaisesRegex(
                    RuntimeError, "migration_catalog_drift",
                ):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_k_rejects_function_owner_and_extra_trigger_drift(self):
        import psycopg

        attacks = ("validator_owner", "guard_owner", "extra_before_insert_trigger")
        for attack in attacks:
            with self.subTest(attack=attack):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    if attack == "validator_owner":
                        db.execute(
                            "alter function public.validate_litter_supersession() owner to anon"
                        )
                    elif attack == "guard_owner":
                        db.execute(
                            "alter function app_private.guard_production_migration_receipts() "
                            "owner to anon"
                        )
                    else:
                        db.execute(
                            "create or replace function public.zzz_mutate_litter_after_validation() "
                            "returns trigger language plpgsql as $$begin "
                            "new.authorization_id='ATTACKER'; return new; end$$; "
                            "create trigger zzz_mutate_litter_after_validation "
                            "before insert on public.litter_supersessions for each row "
                            "execute function public.zzz_mutate_litter_after_validation()"
                        )
                    db.commit()
                expected = (
                    "migration_receipt_guard_mismatch"
                    if attack == "guard_owner"
                    else "migration_catalog_drift"
                )
                with self.assertRaisesRegex(RuntimeError, expected):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_l_legacy_receipt_cannot_be_self_certified(self):
        import psycopg

        _reset_disposable_database()
        first = run(DATABASE_URL, ENV)
        receipt_id = first["migrations"][0]["receipt_id"]
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(
                "alter table app_private.production_migration_receipt_identity_anchors "
                "disable trigger trg_guard_production_migration_receipt_identity_anchors"
            )
            db.execute(
                "delete from app_private.production_migration_receipt_identity_anchors "
                "where receipt_id=%s",
                (receipt_id,),
            )
            db.execute(
                "alter table app_private.production_migration_receipt_identity_anchors "
                "enable trigger trg_guard_production_migration_receipt_identity_anchors"
            )
            db.commit()
        with self.assertRaisesRegex(
            RuntimeError, "legacy_migration_receipt_identity_unverifiable"
        ):
            run(DATABASE_URL, ENV)
        with self.assertRaisesRegex(RuntimeError, "legacy_migration_receipt_identity_unverifiable"):
            run(DATABASE_URL, {**ENV, "RENDER_MIGRATION_ALLOW_LEGACY_RECEIPT_ANCHOR": "true"})

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_malformed_historical_object_never_receives_applied_receipt(self):
        import psycopg
        _reset_disposable_database()
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("create table app_private.beacon_protected_publication_consumers(marker text)")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "migration_failed_and_rolled_back:.*receipt=none"):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            exists = db.execute("select to_regclass('app_private.production_migration_receipts')").fetchone()[0]
            self.assertIsNone(exists)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_receipt_hash_is_timezone_invariant(self):
        import psycopg
        _reset_disposable_database()
        run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL, autocommit=True) as db:
            db.execute("alter database render_migration_rail_test set timezone='Africa/Johannesburg'")
        replay = run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL, autocommit=True) as db:
            db.execute("alter database render_migration_rail_test set timezone='UTC'")
        self.assertTrue(all(row["outcome"] == "already_applied" for row in replay["migrations"]))

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_anchor_catalog_and_insert_paths_fail_closed(self):
        import psycopg
        for attack in ("fk", "acl", "insert_trigger"):
            with self.subTest(attack=attack):
                _reset_disposable_database(); run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    if attack == "fk":
                        name = db.execute("select conname from pg_constraint where conrelid='app_private.production_migration_receipt_identity_anchors'::regclass and contype='f'").fetchone()[0]
                        db.execute(f'alter table app_private.production_migration_receipt_identity_anchors drop constraint "{name}"')
                    elif attack == "acl":
                        db.execute("grant select,insert on app_private.production_migration_receipt_identity_anchors to anon")
                    else:
                        db.execute("create function app_private.rewrite_anchor() returns trigger language plpgsql as $$begin new.identity_sha256:=repeat('0',64); return new; end$$; create trigger aaa_rewrite_anchor before insert on app_private.production_migration_receipt_identity_anchors for each row execute function app_private.rewrite_anchor()")
                    db.commit()
                with self.assertRaisesRegex(RuntimeError, "migration_receipt_(anchor_fk|catalog_acl|guard_trigger_inventory)"):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_protected_claim_column_owner_and_set_role_paths_fail_closed(self):
        import psycopg
        for attack in ("column", "owner", "set_role"):
            with self.subTest(attack=attack):
                _reset_disposable_database(); run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    if attack == "column":
                        db.execute("grant select(callback_token) on app_private.oom_protected_action_claims to anon")
                    elif attack == "owner":
                        db.execute("do $$begin create role claim_attacker login; exception when duplicate_object then null; end$$; alter table app_private.oom_protected_action_claims owner to claim_attacker")
                    else:
                        db.execute("do $$begin create role claim_group; exception when duplicate_object then null; end$$; do $$begin create role claim_login login noinherit; exception when duplicate_object then null; end$$; grant claim_group to claim_login; grant select on app_private.oom_protected_action_claims to claim_group")
                    db.commit()
                with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
                    run(DATABASE_URL, ENV)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_catalog_manifest_rejects_all_final_review_attacks_without_mutation(self):
        import psycopg

        attacks = {
            "historical_beacon_extra_column": (
                "alter table app_private.beacon_protected_publication_consumers "
                "add column attacker_marker text",
                "migration_catalog_drift",
            ),
            "historical_sales_guard_removed": (
                "drop trigger trg_guard_charitable_sales_evidence "
                "on public.sales_transactions",
                "migration_catalog_drift",
            ),
            "historical_welfare_guard_removed": (
                "drop trigger trg_pig_welfare_case_events_no_update_delete "
                "on public.pig_welfare_case_events",
                "migration_catalog_drift",
            ),
            "litter_table_and_validator_attacker_owned": (
                "do $$begin create role litter_attacker login; "
                "exception when duplicate_object then null; end$$; "
                "alter table public.litter_supersessions owner to litter_attacker; "
                "alter function public.validate_litter_supersession() "
                "owner to litter_attacker",
                "migration_catalog_drift",
            ),
            "receipt_applied_unique_index_removed": (
                "drop index app_private.uq_production_migration_applied",
                "migration_receipt_catalog_index_inventory_mismatch",
            ),
            "app_private_schema_attacker_owned": (
                "do $$begin create role schema_attacker login; "
                "exception when duplicate_object then null; end$$; "
                "alter schema app_private owner to schema_attacker",
                "migration_private_schema_owner_mismatch",
            ),
            "protected_claim_insert_suppression_rule": (
                "create rule attacker_suppress_claim_insert as "
                "on insert to app_private.oom_protected_action_claims "
                "do instead nothing",
                "migration_catalog_drift",
            ),
        }
        for attack, (sql, expected) in attacks.items():
            with self.subTest(attack=attack):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    db.execute(sql)
                    db.commit()
                    before_oids = db.execute(
                        """select t.tgname,t.oid from pg_catalog.pg_trigger t
                             join pg_catalog.pg_class c on c.oid=t.tgrelid
                             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                            where n.nspname='app_private'
                              and t.tgname like 'trg_guard_production_migration_%'
                            order by 1"""
                    ).fetchall()
                    before_counts = db.execute(
                        """select
                           (select count(*) from app_private.production_migration_receipts),
                           (select count(*) from app_private.production_migration_receipt_identity_anchors),
                           (select count(*) from app_private.production_migration_baselines),
                           (select count(*) from app_private.production_migration_catalog_checkpoints)"""
                    ).fetchone()
                    before_catalog = _catalog_snapshot(db)
                with self.assertRaisesRegex(RuntimeError, expected):
                    run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    after_oids = db.execute(
                        """select t.tgname,t.oid from pg_catalog.pg_trigger t
                             join pg_catalog.pg_class c on c.oid=t.tgrelid
                             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                            where n.nspname='app_private'
                              and t.tgname like 'trg_guard_production_migration_%'
                            order by 1"""
                    ).fetchall()
                    after_counts = db.execute(
                        """select
                           (select count(*) from app_private.production_migration_receipts),
                           (select count(*) from app_private.production_migration_receipt_identity_anchors),
                           (select count(*) from app_private.production_migration_baselines),
                           (select count(*) from app_private.production_migration_catalog_checkpoints)"""
                    ).fetchone()
                    after_catalog = _catalog_snapshot(db)
                self.assertEqual(after_oids, before_oids)
                self.assertEqual(after_counts, before_counts)
                self.assertEqual(after_catalog, before_catalog)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_late_rejection_leaves_guard_oids_and_ledger_exactly_unchanged(self):
        import psycopg

        _reset_disposable_database()
        run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            db.execute(
                "alter table app_private.oom_protected_action_claims drop constraint "
                "oom_protected_action_claims_action_kind_check; "
                "alter table app_private.oom_protected_action_claims add constraint "
                "oom_protected_action_claims_action_kind_check "
                "check(action_kind in ('mortality'))"
            )
            db.commit()
            before_oids = db.execute(
                """select t.tgname,t.oid from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                    where n.nspname='app_private'
                      and t.tgname like 'trg_guard_production_migration_%'
                    order by 1"""
            ).fetchall()
            before_counts = db.execute(
                """select
                   (select count(*) from app_private.production_migration_receipts),
                   (select count(*) from app_private.production_migration_receipt_identity_anchors),
                   (select count(*) from app_private.production_migration_catalog_checkpoints)"""
            ).fetchone()
        with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            after_oids = db.execute(
                """select t.tgname,t.oid from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                    where n.nspname='app_private'
                      and t.tgname like 'trg_guard_production_migration_%'
                    order by 1"""
            ).fetchall()
            after_counts = db.execute(
                """select
                   (select count(*) from app_private.production_migration_receipts),
                   (select count(*) from app_private.production_migration_receipt_identity_anchors),
                   (select count(*) from app_private.production_migration_catalog_checkpoints)"""
            ).fetchone()
        self.assertEqual(after_oids, before_oids)
        self.assertEqual(after_counts, before_counts)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_governed_view_return_rule_drift_rejects_without_mutation(self):
        import psycopg

        _reset_disposable_database()
        run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            original_catalog = _catalog_snapshot(db)
            original_definition = db.execute(
                "select pg_catalog.pg_get_viewdef("
                "'public.pig_welfare_case_current'::regclass,false)"
            ).fetchone()[0].rstrip().rstrip(";")
            db.execute(
                "create or replace view public.pig_welfare_case_current as "
                f"select * from ({original_definition}) governed_view where false"
            )
            db.commit()
            attacked_catalog = _catalog_snapshot(db)
            self.assertNotEqual(attacked_catalog, original_catalog)
            before_oids = db.execute(
                """select t.tgname,t.oid from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                    where n.nspname='app_private'
                      and t.tgname like 'trg_guard_production_migration_%'
                    order by 1"""
            ).fetchall()
            before_counts = db.execute(
                """select
                   (select count(*) from app_private.production_migration_receipts),
                   (select count(*) from app_private.production_migration_receipt_identity_anchors),
                   (select count(*) from app_private.production_migration_baselines),
                   (select count(*) from app_private.production_migration_catalog_checkpoints)"""
            ).fetchone()
        with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            after_catalog = _catalog_snapshot(db)
            after_oids = db.execute(
                """select t.tgname,t.oid from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                    where n.nspname='app_private'
                      and t.tgname like 'trg_guard_production_migration_%'
                    order by 1"""
            ).fetchall()
            after_counts = db.execute(
                """select
                   (select count(*) from app_private.production_migration_receipts),
                   (select count(*) from app_private.production_migration_receipt_identity_anchors),
                   (select count(*) from app_private.production_migration_baselines),
                   (select count(*) from app_private.production_migration_catalog_checkpoints)"""
            ).fetchone()
        self.assertEqual(after_catalog, attacked_catalog)
        self.assertEqual(after_oids, before_oids)
        self.assertEqual(after_counts, before_counts)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_internal_foreign_key_trigger_drift_rejects_without_mutation(self):
        import psycopg
        from psycopg import sql

        _reset_disposable_database()
        run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            original_catalog = _catalog_snapshot(db)
            trigger = db.execute(
                """select n.nspname,c.relname,t.tgname
                     from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                     join pg_catalog.pg_constraint k on k.oid=t.tgconstraint
                    where t.tgisinternal and k.contype='f'
                      and (n.nspname||'.'||c.relname)=any(%s)
                    order by 1,2,3 limit 1""",
                (list(CATALOG_RELATIONS),),
            ).fetchone()
            self.assertIsNotNone(trigger)
            db.execute(
                sql.SQL("alter table {}.{} disable trigger {}").format(
                    sql.Identifier(trigger[0]),
                    sql.Identifier(trigger[1]),
                    sql.Identifier(trigger[2]),
                )
            )
            db.commit()
            attacked_catalog = _catalog_snapshot(db)
            self.assertNotEqual(attacked_catalog, original_catalog)
            before_oids = db.execute(
                """select t.tgname,t.oid from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                    where n.nspname='app_private'
                      and t.tgname like 'trg_guard_production_migration_%'
                    order by 1"""
            ).fetchall()
            before_counts = db.execute(
                """select
                   (select count(*) from app_private.production_migration_receipts),
                   (select count(*) from app_private.production_migration_receipt_identity_anchors),
                   (select count(*) from app_private.production_migration_baselines),
                   (select count(*) from app_private.production_migration_catalog_checkpoints)"""
            ).fetchone()
        with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
            run(DATABASE_URL, ENV)
        with psycopg.connect(DATABASE_URL) as db:
            after_catalog = _catalog_snapshot(db)
            after_oids = db.execute(
                """select t.tgname,t.oid from pg_catalog.pg_trigger t
                     join pg_catalog.pg_class c on c.oid=t.tgrelid
                     join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                    where n.nspname='app_private'
                      and t.tgname like 'trg_guard_production_migration_%'
                    order by 1"""
            ).fetchall()
            after_counts = db.execute(
                """select
                   (select count(*) from app_private.production_migration_receipts),
                   (select count(*) from app_private.production_migration_receipt_identity_anchors),
                   (select count(*) from app_private.production_migration_baselines),
                   (select count(*) from app_private.production_migration_catalog_checkpoints)"""
            ).fetchone()
        self.assertEqual(after_catalog, attacked_catalog)
        self.assertEqual(after_oids, before_oids)
        self.assertEqual(after_counts, before_counts)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_cross_boundary_fk_delete_and_update_triggers_reject_without_mutation(self):
        import psycopg
        from psycopg import sql

        for event_name, trigger_type in (("delete", 9), ("update", 17)):
            with self.subTest(event=event_name):
                _reset_disposable_database()
                run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    original_catalog = _catalog_snapshot(db)
                    trigger = db.execute(
                        """select n.nspname,c.relname,t.tgname,k.conname
                             from pg_catalog.pg_trigger t
                             join pg_catalog.pg_class c on c.oid=t.tgrelid
                             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                             join pg_catalog.pg_constraint k on k.oid=t.tgconstraint
                             join pg_catalog.pg_class src on src.oid=k.conrelid
                             join pg_catalog.pg_namespace sn on sn.oid=src.relnamespace
                             join pg_catalog.pg_class tgt on tgt.oid=k.confrelid
                             join pg_catalog.pg_namespace tn on tn.oid=tgt.relnamespace
                            where t.tgisinternal and k.contype='f' and t.tgtype=%s
                              and ((sn.nspname||'.'||src.relname)=any(%s)
                                or (tn.nspname||'.'||tgt.relname)=any(%s))
                              and not ((n.nspname||'.'||c.relname)=any(%s))
                            order by 1,2,3 limit 1""",
                        (
                            trigger_type,
                            list(CATALOG_RELATIONS),
                            list(CATALOG_RELATIONS),
                            list(CATALOG_RELATIONS),
                        ),
                    ).fetchone()
                    self.assertIsNotNone(trigger)
                    db.execute(
                        sql.SQL("alter table {}.{} disable trigger {}").format(
                            sql.Identifier(trigger[0]),
                            sql.Identifier(trigger[1]),
                            sql.Identifier(trigger[2]),
                        )
                    )
                    db.commit()
                    attacked_catalog = _catalog_snapshot(db)
                    self.assertNotEqual(attacked_catalog, original_catalog)
                    before_oids = db.execute(
                        """select t.tgname,t.oid from pg_catalog.pg_trigger t
                             join pg_catalog.pg_class c on c.oid=t.tgrelid
                             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                            where n.nspname='app_private'
                              and t.tgname like 'trg_guard_production_migration_%'
                            order by 1"""
                    ).fetchall()
                    before_counts = db.execute(
                        """select
                           (select count(*) from app_private.production_migration_receipts),
                           (select count(*) from app_private.production_migration_receipt_identity_anchors),
                           (select count(*) from app_private.production_migration_baselines),
                           (select count(*) from app_private.production_migration_catalog_checkpoints)"""
                    ).fetchone()
                with self.assertRaisesRegex(RuntimeError, "migration_catalog_drift"):
                    run(DATABASE_URL, ENV)
                with psycopg.connect(DATABASE_URL) as db:
                    after_catalog = _catalog_snapshot(db)
                    after_oids = db.execute(
                        """select t.tgname,t.oid from pg_catalog.pg_trigger t
                             join pg_catalog.pg_class c on c.oid=t.tgrelid
                             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                            where n.nspname='app_private'
                              and t.tgname like 'trg_guard_production_migration_%'
                            order by 1"""
                    ).fetchall()
                    after_counts = db.execute(
                        """select
                           (select count(*) from app_private.production_migration_receipts),
                           (select count(*) from app_private.production_migration_receipt_identity_anchors),
                           (select count(*) from app_private.production_migration_baselines),
                           (select count(*) from app_private.production_migration_catalog_checkpoints)"""
                    ).fetchone()
                self.assertEqual(after_catalog, attacked_catalog)
                self.assertEqual(after_oids, before_oids)
                self.assertEqual(after_counts, before_counts)

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_explicit_one_time_historical_baseline_is_digest_bound_and_immutable(self):
        import psycopg

        _reset_disposable_database()
        with psycopg.connect(DATABASE_URL) as db:
            for item in ALLOWLIST[:3]:
                db.execute(
                    (Path("supabase/migrations") / item.filename).read_text(
                        encoding="utf-8"
                    )
                )
            db.commit()
            _, baseline_digest = _catalog_snapshot(db)
        baseline_env = {
            **ENV,
            "RENDER_MIGRATION_BASELINE_IDS": ",".join(BASELINE_ELIGIBLE_IDS),
            "RENDER_MIGRATION_BASELINE_CATALOG_SHA256": baseline_digest,
            "RENDER_MIGRATION_BASELINE_AUTHORIZATION_ID": (
                "7b942817-55d4-451f-b4f8-2431223d1e52"
            ),
        }
        applied = run(DATABASE_URL, baseline_env)
        self.assertEqual(
            [item["outcome"] for item in applied["migrations"]],
            ["baseline_verified"] * 3 + ["applied"] * 2,
        )
        replay = run(DATABASE_URL, ENV)
        self.assertEqual(
            [item["outcome"] for item in replay["migrations"]],
            ["baseline_verified"] * 3 + ["already_applied"] * 2,
        )
        with psycopg.connect(DATABASE_URL) as db:
            self.assertEqual(
                db.execute(
                    """select
                       (select count(*) from app_private.production_migration_baselines),
                       (select count(*) from app_private.production_migration_receipts),
                       (select count(*) from app_private.production_migration_catalog_checkpoints)"""
                ).fetchone(),
                (1, 2, 1),
            )
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "append-only"):
                db.execute(
                    "update app_private.production_migration_baselines "
                    "set source_catalog_sha256=repeat('0',64)"
                )
            db.rollback()
        with self.assertRaisesRegex(RuntimeError, "migration_baseline_already_initialized"):
            run(DATABASE_URL, baseline_env)

        _reset_disposable_database()
        with psycopg.connect(DATABASE_URL) as db:
            _, actual_digest = _catalog_snapshot(db)
        wrong_env = {
            **baseline_env,
            "RENDER_MIGRATION_BASELINE_CATALOG_SHA256": "0" * 64,
        }
        with self.assertRaisesRegex(RuntimeError, "migration_baseline_catalog_mismatch"):
            run(DATABASE_URL, wrong_env)
        with psycopg.connect(DATABASE_URL) as db:
            self.assertNotEqual(actual_digest, "0" * 64)
            self.assertIsNone(
                db.execute(
                    "select to_regclass('app_private.production_migration_receipts')"
                ).fetchone()[0]
            )

    @unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL not configured")
    def test_disposable_postgres_c_runner_failure_rolls_back_partial_schema(self):
        import psycopg

        _reset_disposable_database()
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
            self.assertIsNone(
                db.execute(
                    "select to_regclass('app_private.production_migration_receipts')"
                ).fetchone()[0]
            )
