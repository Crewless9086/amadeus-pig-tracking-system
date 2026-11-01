"""Exact A migration through the existing closed runner; no provider or farm operation.

Uses only the explicitly disposable render_migration_rail_test database. Historical
runner qualification stays intact in its existing suite; this suite upgrades that
real eight-migration prefix to A and challenges the new semantic boundary.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import run_render_production_migrations as rail
from tests import test_render_production_migration_rail as legacy


DATABASE_URL = legacy.DATABASE_URL
A_ITEM = rail.ALLOWLIST[-1]
PREREQUISITES = (
    "202605210005_create_telemetry_power_tables.sql",
    "202605230001_create_irrigation_tables.sql",
    "202608050001_harden_irrigation_events_history.sql",
)
FUNCTION = "public.rootline_append_typed_irrigation_event(text,timestamptz,text,text,numeric,numeric,jsonb)"
RESET_RELATIONS = (
    "irrigation_events", "irrigation_sensor_states", "irrigation_auxiliary_tasks",
    "irrigation_auxiliary_devices", "irrigation_state_snapshots", "irrigation_plan_items",
    "irrigation_daily_plans", "irrigation_zones", "telemetry_alerts",
    "power_latest_state", "power_readings_5min", "telemetry_sources",
)


def test_exact_a_allowlist_append_preserves_old_prefix_and_source_digest():
    assert len(rail.ALLOWLIST) == 9
    assert rail.ALLOWLIST[:-1] == legacy.ALLOWLIST
    assert A_ITEM.migration_id == "20261101150806_extend_rootline_a_irrigation_history"
    assert A_ITEM.sha256 == "8feb9409fb36ad64b88ff84a1ace4b88f1d3ccc9b89f26cca2cd99cc367f2a79"
    assert hashlib.sha256(rail._load_sql(A_ITEM).encode()).hexdigest() == A_ITEM.sha256
    assert rail.ROOTLINE_HISTORY_PREDECESSOR not in rail.ALLOWLIST
    assert rail.ROOTLINE_A_MIGRATION_ID not in rail.BASELINE_ELIGIBLE_IDS
    assert rail.ROOTLINE_A_MIGRATION_ID not in rail.LEGACY_ADOPTION_BASELINE_IDS
    assert rail.ROOTLINE_A_MIGRATION_ID not in rail.LEGACY_ADOPTION_RECEIPT_IDS


def test_catalog_scope_uses_exact_a_identity_not_tail_position():
    old_relations, old_functions = rail._rootline_catalog_scope(legacy.ALLOWLIST)
    new_relations, new_functions = rail._rootline_catalog_scope()
    assert new_relations == old_relations + list(rail.ROOTLINE_CATALOG_RELATIONS)
    assert new_functions == old_functions + list(rail.ROOTLINE_CATALOG_FUNCTIONS)
    unrelated = rail.AllowedMigration("20990101_unrelated", "unrelated.sql", "0" * 64)
    assert rail._rootline_catalog_scope(legacy.ALLOWLIST + (unrelated,)) == (old_relations, old_functions)


def _connect():
    import psycopg
    db = psycopg.connect(DATABASE_URL)
    if db.info.dbname != "render_migration_rail_test":
        db.close()
        raise AssertionError("refusing fixture outside render_migration_rail_test")
    return db


def _state():
    with _connect() as db:
        catalog = rail._catalog_snapshot(db)
        history = db.execute("select to_jsonb(e) from public.irrigation_events e order by irrigation_event_id").fetchall()
        receipts = db.execute("select to_jsonb(r) from app_private.production_migration_receipts r order by migration_id").fetchall()
        checkpoints = db.execute("select to_jsonb(c) from app_private.production_migration_catalog_checkpoints c order by created_at,checkpoint_id").fetchall()
        logs = db.execute("select to_jsonb(l) from app_private.migration_log l order by migration_id").fetchall()
    return catalog, history, receipts, checkpoints, logs


@pytest.fixture
def predecessor():
    if not DATABASE_URL:
        pytest.skip("disposable PostgreSQL URL not configured")
    legacy._reset_disposable_database()
    with _connect() as db:
        from psycopg import sql
        for table in RESET_RELATIONS:
            db.execute(sql.SQL("drop table if exists public.{} cascade").format(sql.Identifier(table)))
        # CREATE OR REPLACE intentionally preserves ACLs. Remove only this
        # fixture's functions/overload so one adversary cannot contaminate another.
        db.execute("drop function if exists " + FUNCTION)
        db.execute("drop function if exists public.rootline_append_typed_irrigation_event()")
        db.execute("drop function if exists public.irrigation_events_block_update_delete()")
        db.execute("""do $$ begin
          if not exists(select 1 from pg_roles where rolname='service_role') then
            create role service_role nologin;
          end if;
        end $$""")
        for filename in PREREQUISITES:
            db.execute((Path("supabase/migrations") / filename).read_text(encoding="utf-8"))
        for zone in ("A12345", "B12345", "C12345"):
            db.execute("insert into public.irrigation_zones(zone_id,source_id,zone_name,zone_type) values(%s,'irrigation-controller-main',%s,'drip')", (zone, "Synthetic " + zone))
        for zone in ("B12345", "C12345"):
            details = json.dumps({"contract_version": "rootline_irrigation_outcome_v1", "event_sha256": "a" * 64, "execution_id": "SYNTHETIC-OLD-" + zone})
            assert db.execute("select " + FUNCTION.split("(")[0] + "(%s,now(),'PLANNED',%s,10,null,%s::jsonb)",
                              ("SYNTHETIC-OLD-" + zone, zone, details)).fetchone()[0]
    with patch.object(rail, "ALLOWLIST", legacy.ALLOWLIST):
        report = rail.run(DATABASE_URL, legacy.ENV)
    assert len(report["migrations"]) == 8
    with _connect() as db:
        assert rail._verify_migration_precondition(db, A_ITEM, already_applied=False) == "predecessor"
    return _state()


def test_actual_eight_to_nine_upgrade_and_replay_preserve_history_and_receipts(predecessor):
    first = rail.run(DATABASE_URL, legacy.ENV)
    assert [r["outcome"] for r in first["migrations"]] == ["already_applied"] * 8 + ["applied"]
    assert first["prior_catalog_checkpoint"]["allowlist"] == rail._allowlist_payload(legacy.ALLOWLIST)
    after = _state()
    assert after[1] == predecessor[1]
    assert after[2][:-1] == predecessor[2]
    assert after[3][:-1] == predecessor[3]
    second = rail.run(DATABASE_URL, legacy.ENV)
    assert [r["outcome"] for r in second["migrations"]] == ["already_applied"] * 9
    assert second["migrations"][-1]["receipt_id"] == first["migrations"][-1]["receipt_id"]
    assert _state() == after
    with _connect() as db:
        db.execute("set local role service_role")
        details = json.dumps({"contract_version": "rootline_irrigation_outcome_v1", "event_sha256": "b" * 64, "execution_id": "SYNTHETIC-A"})
        assert db.execute("select public.rootline_append_typed_irrigation_event('SYNTHETIC-A',now(),'PLANNED','A12345',10,null,%s::jsonb)", (details,)).fetchone()[0]
        assert not db.execute("select public.rootline_append_typed_irrigation_event('SYNTHETIC-A',now(),'PLANNED','A12345',10,null,%s::jsonb)", (details,)).fetchone()[0]
    with _connect() as db:
        import psycopg
        with pytest.raises(psycopg.Error, match="append-only"):
            with db.transaction():
                db.execute("delete from public.irrigation_events where irrigation_event_id='SYNTHETIC-A'")
        for role in ("anon", "authenticated"):
            assert not db.execute("select has_function_privilege(%s,%s,'execute')", (role, FUNCTION)).fetchone()[0]


@pytest.mark.parametrize("attack", [
    "alter function " + FUNCTION + " security invoker",
    "alter function " + FUNCTION + " set search_path=public",
    "alter function " + FUNCTION + " strict",
    "grant execute on function " + FUNCTION + " to public",
    "grant execute on function " + FUNCTION + " to service_role with grant option",
    "grant insert on public.irrigation_events to service_role",
    "grant update(details) on public.irrigation_events to authenticated",
    "alter table public.irrigation_events disable trigger trg_irrigation_events_no_update_delete",
    "alter table public.irrigation_events alter column actual_minutes type numeric(12,2)",
    "alter table public.irrigation_events drop constraint irrigation_events_pkey",
    "drop trigger trg_irrigation_events_no_update_delete on public.irrigation_events",
    "drop index public.irrigation_events_rootline_execution_phase_uq",
    "drop index public.irrigation_events_rootline_zone_cutoff_idx; create index irrigation_events_rootline_zone_cutoff_idx on public.irrigation_events(zone_id,event_at,irrigation_event_id) where zone_id in ('B12345','C12345')",
    "create index irrigation_events_rootline_abc_zone_cutoff_idx on public.irrigation_events(zone_id)",
    "insert into app_private.migration_log(migration_id,description) values('20261101150806_extend_rootline_a_irrigation_history','fabricated target')",
    "create or replace function public.rootline_append_typed_irrigation_event() returns boolean language sql as $$select true$$",
])
def test_predecessor_drift_refuses_without_any_new_schema_or_receipt(predecessor, attack):
    with _connect() as db:
        db.execute(attack)
    before = _state()
    with pytest.raises(RuntimeError, match="migration_failed_and_rolled_back:" + rail.ROOTLINE_A_MIGRATION_ID):
        rail.run(DATABASE_URL, legacy.ENV)
    assert _state() == before


def test_exact_target_without_receipt_cannot_be_self_certified(predecessor):
    with _connect() as db:
        db.execute(rail._load_sql(A_ITEM))
    before = _state()
    with pytest.raises(RuntimeError, match="migration_failed_and_rolled_back:" + rail.ROOTLINE_A_MIGRATION_ID):
        rail.run(DATABASE_URL, legacy.ENV)
    assert _state() == before


def test_mutated_function_body_with_same_phrases_refuses(predecessor):
    with _connect() as db:
        definition = db.execute("select pg_get_functiondef(%s::regprocedure)", (FUNCTION,)).fetchone()[0]
        db.execute(definition.replace("return found;", "return false; -- return found;"))
    before = _state()
    with pytest.raises(RuntimeError, match="migration_failed_and_rolled_back:" + rail.ROOTLINE_A_MIGRATION_ID):
        rail.run(DATABASE_URL, legacy.ENV)
    assert _state() == before


def test_failed_a_readback_rolls_back_function_index_log_receipt_and_checkpoint(predecessor):
    real_readback = rail._verify_migration_readback
    def fail_a(db, item):
        result = real_readback(db, item)
        if item.migration_id == rail.ROOTLINE_A_MIGRATION_ID:
            raise RuntimeError("synthetic postcondition failure")
        return result
    with patch.object(rail, "_verify_migration_readback", side_effect=fail_a):
        with pytest.raises(RuntimeError, match="migration_failed_and_rolled_back:" + rail.ROOTLINE_A_MIGRATION_ID):
            rail.run(DATABASE_URL, legacy.ENV)
    assert _state() == predecessor


def test_a_readback_checks_index_structure_and_log_after_sql(predecessor):
    with _connect() as db:
        db.execute(rail._load_sql(A_ITEM))
        assert rail._verify_migration_readback(db, A_ITEM)
        with db.transaction(force_rollback=True):
            db.execute("drop index public.irrigation_events_rootline_abc_zone_cutoff_idx; create index irrigation_events_rootline_abc_zone_cutoff_idx on public.irrigation_events(zone_id,event_at desc,irrigation_event_id) where zone_id in ('A12345','B12345','C12345') or true")
            with pytest.raises(RuntimeError, match="migration_rootline_index_definition_mismatch"):
                rail._verify_migration_readback(db, A_ITEM)
        with db.transaction(force_rollback=True):
            db.execute("update app_private.migration_log set description='wrong' where migration_id=%s", (A_ITEM.migration_id,))
            with pytest.raises(RuntimeError, match="migration_readback_log_mismatch"):
                rail._verify_migration_readback(db, A_ITEM)


def test_applied_a_catalog_drift_is_refused_before_replay_mutation(predecessor):
    rail.run(DATABASE_URL, legacy.ENV)
    with _connect() as db:
        db.execute("grant execute on function " + FUNCTION + " to authenticated")
    before = _state()
    with pytest.raises(RuntimeError, match="migration_catalog_drift"):
        rail.run(DATABASE_URL, legacy.ENV)
    assert _state() == before


def test_concurrent_a_migration_applies_once_and_other_runner_replays(predecessor):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rail.run(DATABASE_URL, legacy.ENV), range(2)))
    assert sorted(r["migrations"][-1]["outcome"] for r in results) == ["already_applied", "applied"]
    assert len({r["migrations"][-1]["receipt_id"] for r in results}) == 1
    with _connect() as db:
        assert db.execute("select count(*) from app_private.production_migration_receipts where migration_id=%s", (A_ITEM.migration_id,)).fetchone()[0] == 1
        assert db.execute("select count(*) from app_private.production_migration_catalog_checkpoints").fetchone()[0] == 2
