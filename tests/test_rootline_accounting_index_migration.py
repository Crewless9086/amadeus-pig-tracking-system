"""Exact concurrent index preparation and normal receipt custody, local PG only."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import pytest
import psycopg
from scripts import run_render_production_migrations as rail
from scripts import rootline_accounting_index as index
from scripts import apply_supabase_migration as single
from tests import test_render_production_migration_rail as legacy
from tests import test_render_rootline_a_migration_rail as a
from tests.test_render_rootline_a_migration_rail import predecessor, purpose_predecessor

ITEM = next(item for item in rail.ALLOWLIST if item.migration_id == index.MIGRATION_ID)
PREFIX = rail.ALLOWLIST[:rail.ALLOWLIST.index(ITEM)]
EVENT_MIGRATION = "202607070001_create_sam_live_stock_conversation_review_events.sql"


@pytest.fixture(autouse=True)
def accounting_prefix_only():
    # Qualify this historical ceremony independently of later append-only entries.
    with patch.object(rail, "ALLOWLIST", PREFIX + (ITEM,)):
        yield


def connect():
    if not legacy.DATABASE_URL:
        pytest.skip("disposable migration database not configured")
    db = psycopg.connect(legacy.DATABASE_URL, autocommit=True)
    assert db.info.dbname == "render_migration_rail_test"
    return db


@pytest.fixture
def ready(predecessor):
    with patch.object(rail, "ALLOWLIST", PREFIX):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        db.execute("drop table if exists public.sam_live_stock_conversation_review_events cascade")
        db.execute((rail.REPO_ROOT / "supabase/migrations" / EVENT_MIGRATION).read_text())
        db.execute("insert into public.sam_live_stock_conversation_review_events(review_event_id) values('SYNTHETIC-INDEX-ROW')")
    return True


def state(db):
    return tuple(db.execute(sql).fetchall() for sql in (
        "select to_jsonb(r) from app_private.production_migration_receipts r order by migration_id",
        "select to_jsonb(r) from app_private.production_migration_catalog_checkpoints r order by created_at,checkpoint_id",
        "select to_jsonb(r) from app_private.migration_log r order by migration_id",
        "select to_jsonb(r) from public.sam_live_stock_conversation_review_events r order by review_event_id",
    ))


def test_registration_preserves_prefix_and_clean_ci_order():
    assert len(PREFIX) == 10
    assert hashlib.sha256(rail._load_sql(ITEM).encode()).hexdigest() == ITEM.sha256
    assert ITEM.migration_id not in rail.BASELINE_ELIGIBLE_IDS
    workflow = (rail.REPO_ROOT / ".github/workflows/oom-sakkie-audit-rails.yml").read_text()
    assert workflow.index("python scripts/apply_supabase_migration.py supabase/migrations/" + EVENT_MIGRATION) < workflow.index("python scripts/apply_supabase_migration.py supabase/migrations/" + ITEM.filename)
    assert "CREATE INDEX" not in rail._load_sql(ITEM).split("DO $verify$",1)[0]
    assert index.TABLE_NAME not in rail._rootline_catalog_scope(PREFIX)[0]
    assert index.TABLE_NAME in rail._rootline_catalog_scope()[0]


def test_real_concurrent_build_then_transaction_receipt_and_replay(ready):
    with connect() as db:
        before = state(db)
    first = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert first["accounting_index_preparation"] == "created_exact_valid"
    assert first["migrations"][-1]["outcome"] == "applied"
    with connect() as db:
        after = state(db)
        assert index.verify_index(db)
    assert before[3] == after[3]
    second = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert second["accounting_index_preparation"] == "existing_exact_valid"
    assert second["migrations"][-1]["receipt_id"] == first["migrations"][-1]["receipt_id"]
    with connect() as db:
        assert state(db) == after


@pytest.mark.parametrize("attack", [
    "create index idx_sam_review_budget_nonzero_window on public.sam_live_stock_conversation_review_events(created_at)",
    "create table public.idx_sam_review_budget_nonzero_window(id int)",
])
def test_wrong_existing_object_stops_without_mutation(ready, attack):
    with connect() as db:
        db.execute(attack)
        before = state(db)
    with pytest.raises(RuntimeError, match="definition_or_state_mismatch"):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        assert state(db) == before
        # This exact object is disposable test setup, never runner remediation.
        db.execute("drop table public.idx_sam_review_budget_nonzero_window" if "create table" in attack else "drop index public.idx_sam_review_budget_nonzero_window")


def test_invalid_exact_index_stops_without_automatic_repair(ready):
    with connect() as db:
        index.prepare_index(db, index.MIGRATION_ID)
        db.execute("update pg_catalog.pg_index set indisvalid=false where indexrelid='public.idx_sam_review_budget_nonzero_window'::regclass")
        before = state(db)
    with pytest.raises(RuntimeError, match="definition_or_state_mismatch"):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        assert state(db) == before
        assert not db.execute("select indisvalid from pg_index where indexrelid='public.idx_sam_review_budget_nonzero_window'::regclass").fetchone()[0]


def test_catalog_drift_fails_before_index_build(ready):
    with connect() as db:
        db.execute("alter table public.irrigation_events add column synthetic_drift text")
        before = state(db)
    with pytest.raises(RuntimeError):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        assert not index.verify_index(db, required=False)
        assert state(db) == before


def test_receipt_tamper_fails_before_index_build(ready):
    with connect() as db:
        db.execute("alter table app_private.production_migration_receipt_identity_anchors disable trigger user")
        db.execute("delete from app_private.production_migration_receipt_identity_anchors where receipt_id=(select receipt_id from app_private.production_migration_receipts where migration_id=%s)", (PREFIX[-1].migration_id,))
        db.execute("alter table app_private.production_migration_receipt_identity_anchors enable trigger user")
        before = state(db)
    with pytest.raises(RuntimeError):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        assert not index.verify_index(db, required=False)
        assert state(db) == before


def test_postcondition_failure_rolls_back_receipts_preserves_prepared_index_for_retry(ready):
    with connect() as db:
        before = state(db)
    original = rail._verify_migration_readback
    def fail(db, item):
        result = original(db, item)
        if item == ITEM:
            raise RuntimeError("synthetic_postcondition_failure")
        return result
    with patch.object(rail, "_verify_migration_readback", side_effect=fail):
        with pytest.raises(RuntimeError, match="migration_transaction_failed_and_rolled_back:" + ITEM.migration_id + ":receipt=none:accounting_index_may_persist"):
            rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        assert state(db) == before
        assert index.verify_index(db)
    result = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert result["accounting_index_preparation"] == "existing_exact_valid"
    assert result["migrations"][-1]["outcome"] == "applied"


def test_two_production_runners_serialize(ready):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rail.run(legacy.DATABASE_URL, legacy.ENV), range(2)))
    assert sorted(r["migrations"][-1]["outcome"] for r in results) == ["already_applied", "applied"]
    assert len({r["migrations"][-1]["receipt_id"] for r in results}) == 1


def test_single_migration_runner_uses_shared_preparation(ready, monkeypatch):
    monkeypatch.setenv(single.DATABASE_URL_ENV, legacy.DATABASE_URL)
    monkeypatch.setattr(single, "load_dotenv", lambda *a: None)
    monkeypatch.setattr("sys.argv", ["apply_supabase_migration.py", "supabase/migrations/" + ITEM.filename])
    assert single.main() == 0
    assert single.main() == 0
    with connect() as db:
        assert index.verify_index(db)
        assert rail._verify_migration_log(db, ITEM.migration_id, required=True) == index.DESCRIPTION


def test_helper_rejects_active_transaction_and_ignores_unregistered_id(ready):
    with connect() as db:
        assert index.prepare_index(db, "unregistered") is None
        with db.transaction():
            with pytest.raises(RuntimeError, match="requires_idle_autocommit"):
                index.prepare_index(db, index.MIGRATION_ID)
        assert not index.verify_index(db, required=False)


def test_build_limits_are_acknowledged_and_restored(ready, monkeypatch):
    execute = psycopg.Connection.execute
    observed = []
    def inspect(db, query, *args, **kwargs):
        if query == index.CREATE_SQL:
            settings = dict(execute(db, "select name,setting::integer from pg_settings where name in ('statement_timeout','lock_timeout')").fetchall())
            observed.append(settings)
        return execute(db, query, *args, **kwargs)
    monkeypatch.setattr(psycopg.Connection, "execute", inspect)
    with connect() as db:
        db.execute("set statement_timeout='300s'")
        db.execute("set lock_timeout='60s'")
        index.prepare_index(db, index.MIGRATION_ID)
        assert observed == [{"statement_timeout": 180000, "lock_timeout": 30000}]
        assert db.execute("show statement_timeout").fetchone()[0] == '5min'
        assert db.execute("show lock_timeout").fetchone()[0] == '1min'


def test_failed_build_restores_stricter_limits_without_receipt(ready):
    with connect() as holder, connect() as db:
        with holder.transaction():
            holder.execute("lock public.sam_live_stock_conversation_review_events in access exclusive mode")
            db.execute("set lock_timeout='50ms'")
            db.execute("set statement_timeout='2s'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                index.prepare_index(db, index.MIGRATION_ID)
            assert db.execute("show lock_timeout").fetchone()[0] == '50ms'
            assert db.execute("show statement_timeout").fetchone()[0] == '2s'
        assert db.execute("select count(*) from app_private.migration_log where migration_id=%s", (ITEM.migration_id,)).fetchone()[0] == 0


def test_clean_database_uses_ordered_canonical_migrations_and_shared_helper(monkeypatch):
    import uuid
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    name = "rootline_accounting_index_clean_" + uuid.uuid4().hex[:12]
    with connect() as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        try:
            parameters = conninfo_to_dict(legacy.DATABASE_URL)
            parameters["dbname"] = name
            url = psycopg.conninfo.make_conninfo(**parameters)
            monkeypatch.setenv(single.DATABASE_URL_ENV, url)
            monkeypatch.setattr(single, "load_dotenv", lambda *args: None)
            for filename in ("202605210001_foundation_migration_log.sql", EVENT_MIGRATION, ITEM.filename, ITEM.filename):
                monkeypatch.setattr("sys.argv", ["apply_supabase_migration.py", "supabase/migrations/" + filename])
                assert single.main() == 0
            with psycopg.connect(url, autocommit=True) as db:
                assert index.verify_index(db)
                assert rail._verify_migration_log(db, ITEM.migration_id, required=True) == index.DESCRIPTION
                assert db.execute("select to_regclass('app_private.production_migration_receipts')").fetchone()[0] is None
                assert db.execute("select count(*) from public.sam_live_stock_conversation_review_events").fetchone()[0] == 0
        finally:
            admin.execute(sql.SQL("drop database {}").format(sql.Identifier(name)))


def test_busy_lock_is_bounded_without_index_or_receipt_changes(ready, monkeypatch):
    monkeypatch.setattr(rail, "ACCOUNTING_LOCK_WAIT_SECONDS", 0.05)
    with connect() as holder:
        before = state(holder)
        holder.execute("select pg_advisory_lock(%s)", (rail.LOCK_KEY,))
        try:
            with pytest.raises(RuntimeError, match="migration_lock_busy:rootline_accounting_index:no_changes"):
                rail.run(legacy.DATABASE_URL, legacy.ENV)
            assert state(holder) == before
            assert not index.verify_index(holder, required=False)
        finally:
            assert holder.execute("select pg_advisory_unlock(%s)", (rail.LOCK_KEY,)).fetchone()[0]


def test_real_purpose_prefix_upgrades_and_replays_without_reexecuting_purpose(purpose_predecessor, monkeypatch):
    with patch.object(rail, "ALLOWLIST", PREFIX):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with connect() as db:
        db.execute("drop table if exists public.sam_live_stock_conversation_review_events cascade")
        db.execute((rail.REPO_ROOT / "supabase/migrations" / EVENT_MIGRATION).read_text())
        before = state(db)
    original = psycopg.Connection.execute
    purpose_sql = rail._load_sql(rail.PURPOSE_MIGRATION)
    def forbid_purpose_reexecution(db, query, *args, **kwargs):
        assert query != purpose_sql
        return original(db, query, *args, **kwargs)
    monkeypatch.setattr(psycopg.Connection, "execute", forbid_purpose_reexecution)
    first = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert first["migrations"][-1]["outcome"] == "applied"
    second = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert second["migrations"][-1]["receipt_id"] == first["migrations"][-1]["receipt_id"]
    with connect() as db:
        assert index.verify_index(db)
        assert state(db)[3] == before[3]
