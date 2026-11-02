"""Exact A migration through the existing closed runner; no provider or farm operation.

Uses only the explicitly disposable render_migration_rail_test database. Historical
runner qualification stays intact in its existing suite; this suite upgrades that
real eight-migration prefix to A and challenges the new semantic boundary.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
    "alter table public.irrigation_events add constraint synthetic_bc_only check(zone_id in ('B12345','C12345'))",
    "alter table public.irrigation_events alter column created_at drop default",
    "alter table public.irrigation_events alter column created_at set default '2000-01-01Z'::timestamptz",
    "alter table public.irrigation_events alter column weather_snapshot drop default",
    "alter table public.irrigation_events alter column power_snapshot drop default",
    "alter table public.irrigation_events add column synthetic_required text not null default 'unexpected'",
    "alter table public.irrigation_events drop constraint irrigation_events_actual_minutes_check",
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


@pytest.mark.parametrize("attack", [
    "grant execute on function " + FUNCTION + " to authenticated",
    "alter table public.irrigation_events add constraint synthetic_bc_only check(zone_id in ('B12345','C12345'))",
    "alter table public.irrigation_events alter column created_at drop default",
])
def test_applied_a_catalog_drift_is_refused_before_replay_mutation(predecessor, attack):
    rail.run(DATABASE_URL, legacy.ENV)
    with _connect() as db:
        db.execute(attack)
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


GUARD_FUNCTION = "public.irrigation_events_block_update_delete()"
TEMPORARY_ROLES = ("rootline_history_attacker", "supabase_storage_admin", "authenticator", "supabase_admin")


@contextmanager
def _temporary_role_graph(*, transport=False, storage=False, attack=None):
    """Exact synthetic hosted grants; remove only roles created by this fixture."""
    created = []
    with _connect() as db:
        assert not db.execute("select exists(select 1 from pg_roles where rolname=any(%s))", (list(TEMPORARY_ROLES),)).fetchone()[0]
        original = db.execute("select rolinherit,rolsuper from pg_roles where rolname='authenticated'").fetchone()
        assert not db.execute("select pg_has_role('authenticated','service_role','MEMBER')").fetchone()[0]
        db.execute("create role rootline_history_attacker nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls")
        created.append("rootline_history_attacker")
        if transport or storage:
            db.execute("create role supabase_admin nologin superuser")
            created.append("supabase_admin")
            db.execute("grant anon,authenticated,service_role,rootline_history_attacker to supabase_admin with admin true, inherit false, set true")
        if transport:
            db.execute("create role authenticator login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls")
            created.append("authenticator")
            db.execute("grant authenticator to supabase_admin with admin true, inherit false, set true")
            db.execute("grant anon,authenticated,service_role to authenticator with admin false, inherit false, set true granted by supabase_admin")
        if storage:
            db.execute("create role supabase_storage_admin login noinherit nosuperuser nocreatedb createrole noreplication nobypassrls")
            created.append("supabase_storage_admin")
            if transport:
                db.execute("grant authenticator to supabase_storage_admin with admin false, inherit false, set true granted by supabase_admin")
    try:
        if attack:
            _apply_role_attack(attack)
        yield
    finally:
        from psycopg import sql
        with _connect() as db:
            db.execute("alter role authenticated " + ("inherit" if original[0] else "noinherit") + " " + ("superuser" if original[1] else "nosuperuser"))
            db.execute("revoke service_role from authenticated")
            owner = db.execute("select current_user").fetchone()[0]
            db.execute(sql.SQL("revoke {} from authenticated").format(sql.Identifier(owner)))
            for function in (FUNCTION, GUARD_FUNCTION):
                db.execute("revoke execute on function " + function + " from public,anon,authenticated")
                db.execute("revoke grant option for execute on function " + function + " from service_role cascade")
            # DROP OWNED removes only these fixture roles' ACLs in this database.
            # DROP ROLE also removes their membership edges, including grantors.
            for role in reversed(created):
                db.execute(sql.SQL("drop owned by {}").format(sql.Identifier(role)))
            for role in reversed(created):
                db.execute(sql.SQL("drop role {}").format(sql.Identifier(role)))
            assert not db.execute("select pg_has_role('authenticated','service_role','MEMBER')").fetchone()[0]
            assert not db.execute("select has_function_privilege('authenticated',%s,'EXECUTE')", (FUNCTION,)).fetchone()[0]


def _apply_role_attack(attack):
    with _connect() as db:
        owner = db.execute("select current_user").fetchone()[0]
        from psycopg import sql
        if attack in ("noinherit_direct", "noinherit_indirect"):
            db.execute("alter role authenticated noinherit")
        commands = {
            "direct": "grant service_role to authenticated",
            "noinherit_direct": "grant service_role to authenticated",
            "indirect": "grant service_role to rootline_history_attacker; grant rootline_history_attacker to authenticated",
            "noinherit_indirect": "grant service_role to rootline_history_attacker; grant rootline_history_attacker to authenticated",
            "inherit": "alter role authenticator inherit",
            "bypassrls": "alter role authenticator bypassrls",
            "cannot_login": "alter role authenticator nologin",
            "missing_member": "revoke anon from authenticator granted by supabase_admin",
            "grant_option": "grant service_role to authenticator with admin true granted by supabase_admin",
            "extra_member": "grant rootline_history_attacker to authenticator granted by supabase_admin",
            "effective_execute": "grant service_role to authenticator with inherit true granted by supabase_admin",
            "set_false": "grant service_role to authenticator with set false granted by supabase_admin",
            "wrong_grantor": "revoke service_role from authenticator granted by supabase_admin; grant service_role to authenticator with inherit false",
            "incoming_noinherit": "grant authenticator to rootline_history_attacker",
            "exposed_authenticator": "revoke authenticated from authenticator granted by supabase_admin; grant authenticator to authenticated",
            "exposed_storage": "revoke authenticated from authenticator granted by supabase_admin; grant supabase_storage_admin to authenticated",
            "incoming_storage": "grant supabase_storage_admin to rootline_history_attacker",
            "exposed_superuser": "alter role authenticated superuser",
        }
        if attack in commands:
            db.execute(commands[attack])
        elif attack.startswith("attribute:"):
            _, role, option = attack.split(":")
            db.execute(sql.SQL("alter role {} ").format(sql.Identifier(role)) + sql.SQL(option))
        elif attack.startswith("edge:"):
            _, role, option = attack.split(":")
            authority = "authenticator" if role == "supabase_storage_admin" else "service_role"
            db.execute(sql.SQL("grant {} to {} with ").format(sql.Identifier(authority), sql.Identifier(role)) + sql.SQL(option) + sql.SQL(" granted by supabase_admin"))
        elif attack == "storage_missing_member":
            db.execute("revoke authenticator from supabase_storage_admin granted by supabase_admin")
        elif attack == "storage_direct_api":
            db.execute("grant service_role to supabase_storage_admin with inherit false granted by supabase_admin")
        elif attack == "storage_wrong_grantor":
            db.execute("revoke authenticator from supabase_storage_admin granted by supabase_admin; grant authenticator to supabase_storage_admin with inherit false")
        elif attack in ("owner_direct", "owner_indirect", "storage_owner", "authenticator_owner", "service_owner"):
            role = {"owner_direct": "authenticated", "owner_indirect": "rootline_history_attacker", "storage_owner": "supabase_storage_admin", "authenticator_owner": "authenticator", "service_owner": "service_role"}[attack]
            db.execute(sql.SQL("grant {} to {}").format(sql.Identifier(owner), sql.Identifier(role)))
            if attack == "owner_indirect": db.execute("grant rootline_history_attacker to authenticated")
        else:
            raise AssertionError(attack)
        if attack in ("noinherit_direct", "noinherit_indirect"):
            assert not db.execute("select has_function_privilege('authenticated',%s,'EXECUTE')", (FUNCTION,)).fetchone()[0]
            assert db.execute("select pg_has_role('authenticated','service_role','MEMBER')").fetchone()[0]
            assert db.execute("select pg_has_role('authenticated','service_role','SET')").fetchone()[0]


def _assert_atomic_refusal(stage):
    before = _state()
    with pytest.raises(RuntimeError) as refusal:
        rail.run(DATABASE_URL, legacy.ENV)
    reason = refusal.value
    if str(reason).startswith("migration_failed_and_rolled_back:"):
        assert stage == "predecessor"
        assert str(reason) == "migration_failed_and_rolled_back:" + A_ITEM.migration_id + ":receipt=none"
        reason = reason.__cause__
    assert isinstance(reason, RuntimeError)
    # Owner reachability can be refused by the unchanged earlier protected-claim
    # boundary before A is reached. This is still an atomic closed-runner refusal.
    assert str(reason).startswith(("migration_rootline_", "migration_catalog_drift",
        "migration_readback_protected_claim_acl_mismatch:"))
    assert _state() == before


@pytest.mark.parametrize("stage", ["predecessor", "replay"])
@pytest.mark.parametrize("attack", ["direct", "indirect", "noinherit_direct", "noinherit_indirect", "owner_direct", "owner_indirect", "exposed_superuser"])
def test_untrusted_execute_or_set_role_path_refuses_before_any_new_effect(predecessor, stage, attack):
    with _temporary_role_graph():
        if stage == "replay": rail.run(DATABASE_URL, legacy.ENV)
        _apply_role_attack(attack)
        _assert_atomic_refusal(stage)


def _assert_upgrade_append_replay(predecessor, *, broker_names, residual_count=None):
    first = rail.run(DATABASE_URL, legacy.ENV)
    assert first["migrations"][-1]["outcome"] == "applied"
    readback = first["migrations"][-1]["readback"]
    assert set(readback["typed_append_function"]["trusted_transports"]) == set(broker_names)
    assert _state()[1] == predecessor[1]
    with _connect() as db:
        db.execute("set local role service_role")
        details = json.dumps({"contract_version": "rootline_irrigation_outcome_v1", "event_sha256": "c" * 64, "execution_id": "SYNTHETIC-HOSTED-A"})
        args = ("SYNTHETIC-HOSTED-A", details)
        statement = "select public.rootline_append_typed_irrigation_event(%s,now(),'PLANNED','A12345',10,null,%s::jsonb)"
        assert db.execute(statement, args).fetchone()[0]
        assert not db.execute(statement, args).fetchone()[0]
    after = _state()
    assert len(after[1]) == len(predecessor[1]) + 1
    assert [row for row in after[1] if row[0]['zone_id'] in ('B12345','C12345')] == predecessor[1]
    second = rail.run(DATABASE_URL, legacy.ENV)
    assert second["migrations"][-1]["outcome"] == "already_applied"
    assert _state() == after
    if residual_count is not None:
        with _connect() as db:
            boundary = rail._rootline_history_boundary(db)
        assert boundary["history_constraint_count"] == 7
        assert len(boundary["table_residual_acl"]) == residual_count


def test_exact_noinherit_transport_profile_preserves_upgrade_and_replay(predecessor):
    with _temporary_role_graph(transport=True):
        _assert_upgrade_append_replay(predecessor, broker_names=["authenticator"])


@pytest.mark.parametrize("guard_service,residual_profile", [(True, "all"), (False, "all"), (True, "reduced")])
def test_hosted_broker_and_finite_acl_profiles_upgrade_append_and_replay(predecessor, guard_service, residual_profile):
    with _temporary_role_graph(transport=True, storage=True):
        with _connect() as db:
            if guard_service: db.execute("grant execute on function " + GUARD_FUNCTION + " to service_role")
            full = ["SELECT", "REFERENCES", "TRIGGER"] + (["MAINTAIN"] if db.info.server_version >= 170000 else [])
            privileges = full if residual_profile == "all" else ["SELECT"]
            db.execute("grant " + ",".join(privileges) + " on public.irrigation_events to anon,authenticated,service_role")
        _assert_upgrade_append_replay(predecessor, broker_names=["authenticator", "supabase_storage_admin"], residual_count=len(privileges)*3)


def test_exact_pg17_saved_catalogue_profile_with_twelve_residual_grants(predecessor):
    with _connect() as db:
        if db.info.server_version < 170000:
            pytest.skip("MAINTAIN requires actual PostgreSQL 17; migration CI job is pinned to 17")
    with _temporary_role_graph(transport=True, storage=True):
        with _connect() as db:
            db.execute("grant execute on function " + GUARD_FUNCTION + " to service_role")
            db.execute("grant select,references,trigger,maintain on public.irrigation_events to anon,authenticated,service_role")
        _assert_upgrade_append_replay(predecessor, broker_names=["authenticator", "supabase_storage_admin"], residual_count=12)


BROKER_ATTACKS = [
    "missing_member", "grant_option", "extra_member", "effective_execute", "set_false", "wrong_grantor",
    "incoming_noinherit", "exposed_authenticator", "exposed_storage", "incoming_storage",
    "storage_missing_member", "storage_direct_api", "storage_wrong_grantor",
    "owner_direct", "owner_indirect", "storage_owner", "authenticator_owner", "service_owner",
] + ["attribute:" + role + ":" + option
     for role in ("authenticator", "supabase_storage_admin")
     for option in ("nologin", "inherit", "superuser", "createdb", "replication", "bypassrls")]
BROKER_ATTACKS += ["attribute:authenticator:createrole", "attribute:supabase_storage_admin:nocreaterole"]
BROKER_ATTACKS += ["edge:supabase_storage_admin:" + option for option in ("admin true", "inherit true", "set false")]


@pytest.mark.parametrize("stage", ["predecessor", "replay"])
@pytest.mark.parametrize("attack", BROKER_ATTACKS)
def test_transport_profile_or_untrusted_incoming_path_is_not_adopted(predecessor, stage, attack):
    with _temporary_role_graph(transport=True, storage=True):
        if stage == "replay": rail.run(DATABASE_URL, legacy.ENV)
        _apply_role_attack(attack)
        try:
            _assert_atomic_refusal(stage)
        finally:
            # The service/owner edge involves existing roles, so restore explicitly.
            if attack == "service_owner":
                from psycopg import sql
                with _connect() as db:
                    owner = db.execute("select current_user").fetchone()[0]
                    db.execute(sql.SQL("revoke {} from service_role").format(sql.Identifier(owner)))
            if attack == "owner_direct":
                from psycopg import sql
                with _connect() as db:
                    owner = db.execute("select current_user").fetchone()[0]
                    db.execute(sql.SQL("revoke {} from authenticated").format(sql.Identifier(owner)))


def test_storage_role_without_authenticator_fails_closed(predecessor):
    with _temporary_role_graph(storage=True):
        _assert_atomic_refusal("predecessor")


@pytest.mark.parametrize("stage", ["predecessor", "replay"])
@pytest.mark.parametrize("function", [FUNCTION, GUARD_FUNCTION])
@pytest.mark.parametrize("grantee", ["public", "anon", "authenticated", "rootline_history_attacker", "service_role with grant option"])
def test_both_function_acl_boundaries_reject_extra_authority(predecessor, stage, function, grantee):
    with _temporary_role_graph():
        if stage == "replay": rail.run(DATABASE_URL, legacy.ENV)
        with _connect() as db: db.execute("grant execute on function " + function + " to " + grantee)
        _assert_atomic_refusal(stage)


TABLE_AND_CONSTRAINT_ATTACKS = [
    "grant select on public.irrigation_events to public",
    "grant references on public.irrigation_events to rootline_history_attacker",
    "grant select on public.irrigation_events to anon with grant option",
    "grant insert on public.irrigation_events to service_role",
    "grant update on public.irrigation_events to authenticated",
    "grant delete on public.irrigation_events to anon",
    "grant truncate on public.irrigation_events to anon",
    "grant select(details) on public.irrigation_events to service_role",
    "grant update(details) on public.irrigation_events to authenticated",
    "alter table public.irrigation_events add constraint synthetic_unique unique(zone_id)",
    "alter table public.irrigation_events add constraint synthetic_exclude exclude using hash (irrigation_event_id with =)",
    "alter table public.irrigation_events add constraint synthetic_fk foreign key(import_batch_id) references public.irrigation_zones(zone_id)",
    "alter table public.irrigation_events drop constraint irrigation_events_source_id_fkey",
    "alter table public.irrigation_events drop constraint irrigation_events_zone_id_fkey; alter table public.irrigation_events add foreign key(zone_id) references public.irrigation_zones(zone_id) on delete cascade",
    "alter table public.irrigation_events drop constraint irrigation_events_zone_id_fkey; alter table public.irrigation_events add foreign key(zone_id) references public.irrigation_zones(zone_id) on update cascade on delete set null",
    "alter table public.irrigation_events drop constraint irrigation_events_zone_id_fkey; alter table public.irrigation_events add foreign key(zone_id) references public.irrigation_zones(zone_id) match full on delete set null",
    "alter table public.irrigation_events drop constraint irrigation_events_source_id_fkey; alter table public.irrigation_events add foreign key(source_id) references public.irrigation_zones(zone_id) on delete set null not valid",
    "alter table public.irrigation_events drop constraint irrigation_events_zone_id_fkey; alter table public.irrigation_events add foreign key(zone_id) references public.irrigation_zones(zone_id) on delete set null deferrable initially deferred",
    "alter table public.irrigation_events drop constraint irrigation_events_zone_id_fkey; alter table public.irrigation_events add foreign key(zone_id) references public.irrigation_zones(zone_id) on delete set null not valid",
    "alter table public.irrigation_events disable trigger trg_irrigation_events_no_update_delete",
    "alter table public.irrigation_events enable always trigger trg_irrigation_events_no_update_delete",
    "create trigger synthetic_guard before update or delete on public.irrigation_events for each row execute function public.irrigation_events_block_update_delete()",
    "alter table public.irrigation_events alter column created_at drop default",
    "alter table public.irrigation_events alter column weather_snapshot drop not null",
    "alter table public.irrigation_events alter column actual_minutes type numeric(12,2)",
    "alter table public.irrigation_events add constraint synthetic_bc_only check(zone_id in ('B12345','C12345'))",
]


@pytest.mark.parametrize("stage", ["predecessor", "replay"])
@pytest.mark.parametrize("attack", TABLE_AND_CONSTRAINT_ATTACKS)
def test_complete_table_insert_contract_rejects_preapply_and_replay_drift(predecessor, stage, attack):
    with _temporary_role_graph():
        if stage == "replay": rail.run(DATABASE_URL, legacy.ENV)
        with _connect() as db: db.execute(attack)
        _assert_atomic_refusal(stage)
