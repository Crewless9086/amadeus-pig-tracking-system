import hashlib
import os
from pathlib import Path

import pytest

from scripts.run_render_production_migrations import ALLOWLIST, _metadata, run


ENV = {
    "RENDER": "true",
    "RENDER_GIT_COMMIT": "a" * 40,
    "RENDER_MIGRATION_EXPECTED_COMMIT": "a" * 40,
    "RENDER_SERVICE_ID": "srv-production",
    "RENDER_INSTANCE_ID": "job-instance",
}


def test_allowlist_is_ordered_exact_and_checksum_bound():
    assert [row.filename for row in ALLOWLIST] == [
        "202608200001_add_sales_financial_disposition.sql"
    ]
    assert list(ALLOWLIST) == sorted(ALLOWLIST, key=lambda row: row.migration_id)
    for row in ALLOWLIST:
        raw = (Path("supabase/migrations") / row.filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row.sha256


def test_render_identity_is_mandatory_and_exact():
    with pytest.raises(RuntimeError, match="render_runtime_required"):
        _metadata({})
    with pytest.raises(RuntimeError, match="exact_render_source_commit_required"):
        _metadata(dict(ENV, RENDER_GIT_COMMIT="main"))
    with pytest.raises(RuntimeError, match="render_source_deploy_binding_mismatch"):
        _metadata(dict(ENV, RENDER_MIGRATION_EXPECTED_COMMIT="b" * 40))
    assert _metadata(ENV) == ("a" * 40, "srv-production", "job-instance")


DATABASE_URL = os.getenv("RENDER_MIGRATION_TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not DATABASE_URL, reason="disposable PostgreSQL URL not configured")
def test_disposable_postgres_apply_replay_and_immutable_receipt():
    import psycopg

    database_name = psycopg.connect(DATABASE_URL).info.dbname
    if database_name != "render_migration_rail_test":
        pytest.fail("refusing fixture outside render_migration_rail_test")
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        db.execute("drop schema if exists app_private cascade")
        db.execute("drop table if exists public.sales_transactions cascade")
        db.execute("create schema app_private")
        db.execute("""create table app_private.migration_log(
          migration_id text primary key,description text not null,
          applied_at timestamptz not null default now())""")
        db.execute("""create table public.sales_transactions(
          sale_id text primary key,sale_stream text,sale_status text,linked_order_id text,
          gross_total numeric(12,2),deductions_total numeric(12,2),net_total numeric(12,2),
          received_total numeric(12,2),payment_status text,
          payment_received_evidence_json jsonb,payment_evidence_sha256 text)""")
    first = run(DATABASE_URL, ENV)
    second = run(DATABASE_URL, ENV)
    assert first["migrations"][0]["outcome"] == "applied"
    assert second["migrations"][0]["outcome"] == "already_applied"
    assert first["migrations"][0]["receipt_id"] == second["migrations"][0]["receipt_id"]
    with psycopg.connect(DATABASE_URL) as db:
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            db.execute("update app_private.production_migration_receipts set ordinal=2")
