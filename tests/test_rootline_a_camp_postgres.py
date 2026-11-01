"""Opt-in real PostgreSQL A qualification on a new, retained, isolated database.

ROOTLINE_A_TEST_POSTGRES=1 is required. Never targets a production or retained DB.
The fixture creates only a UUID-suffixed database on the assigned localhost port;
it does not create roles, stop a server, truncate tables or remove evidence.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
from threading import Barrier
import uuid

import pytest

from tests.test_rootline_a_camp_automation import (
    NOW, a_binding, a_authority_policy, canonical_record, commissioned_a, digest, successor)

pytestmark = pytest.mark.skipif(os.getenv("ROOTLINE_A_TEST_POSTGRES") != "1",
    reason="requires explicitly leased local PostgreSQL A fixture")
MIGRATIONS = (
    "202605210001_foundation_migration_log.sql",
    "202605210005_create_telemetry_power_tables.sql",
    "202605230001_create_irrigation_tables.sql",
    "202607070001_create_sam_live_stock_conversation_review_events.sql",
    "202607270002_create_rootline_operating_policies.sql",
    "202608050001_harden_irrigation_events_history.sql",
    "202608150009_create_rootline_water_credit_lifecycle.sql",
    "202608170001_add_rootline_device_registry.sql",
    "20261101150806_extend_rootline_a_irrigation_history.sql",
)


@pytest.fixture(scope="module")
def database():
    import psycopg
    from psycopg import sql
    name = "rootline_a_automation_test_" + uuid.uuid4().hex[:12]
    base = "host=127.0.0.1 port=65436 user=rootline_demand_test connect_timeout=5"
    with psycopg.connect(base + " dbname=postgres", autocommit=True) as db:
        assert db.execute("select current_user,inet_server_addr()::text,inet_server_port()").fetchone() == (
            "rootline_demand_test", "127.0.0.1/32", 65436)
        assert db.execute("select count(*) from pg_roles where rolname=any(%s)",
            (["anon", "authenticated", "service_role"],)).fetchone()[0] == 3
        db.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    dsn = base + " dbname=" + name
    migration_root = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    with psycopg.connect(dsn) as db:
        db.execute("create extension if not exists pgcrypto")
        for migration in MIGRATIONS:
            db.execute((migration_root / migration).read_text())
        for zone in ("A12345", "B12345", "C12345"):
            db.execute("insert into public.irrigation_zones(zone_id,source_id,zone_name,zone_type) values(%s,%s,%s,%s)",
                (zone, "irrigation-controller-main", "Synthetic " + zone, "drip"))
    print("Retained isolated A database:", name)
    yield dsn
    with psycopg.connect(base + " dbname=postgres", autocommit=True) as db:
        assert db.execute("select count(*) from pg_stat_activity where datname=%s", (name,)).fetchone()[0] == 0


def append_history(db, event):
    return db.execute("select public.rootline_append_typed_irrigation_event(%s,%s,%s,%s,%s,%s,%s::jsonb)",
        (event["irrigation_event_id"], event["event_at"], event["event_type"], event["zone_id"],
         event["planned_minutes"], event["actual_minutes"], json.dumps(event["details"]))).fetchone()[0]


def test_real_a_history_preserves_bc_replay_append_only_and_service_boundary(database):
    import psycopg
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event, read_canonical_irrigation_history
    events = [build_typed_history_event(event_id="SYNTHETIC-EPOCH-" + zone,
        event_at=NOW, event_type="PLANNING_EPOCH_STARTED", zone_id=zone,
        details={"epoch_start": NOW.isoformat(), "provenance": "reviewed_reconciliation"})
        for zone in ("A12345", "B12345", "C12345")]
    with psycopg.connect(database) as db:
        for event in events:
            assert append_history(db, event) is True
            assert append_history(db, event) is False
    snapshot = read_canonical_irrigation_history(connect=lambda: psycopg.connect(database), now=NOW)
    assert snapshot["status"] == "Available"
    assert set(snapshot["zones"]) == {"A12345", "B12345", "C12345"}
    assert snapshot["zones"]["A12345"]["epoch_complete_through"] == NOW.isoformat()
    assert snapshot["zones"]["A12345"]["complete_through"] is None
    with psycopg.connect(database) as db:
        assert db.execute("select count(*) from public.irrigation_water_credit_events").fetchone()[0] == 0
        for role, allowed in (("anon", False), ("authenticated", False), ("service_role", True)):
            assert db.execute("select has_function_privilege(%s,%s,'execute')", (role,
                "public.rootline_append_typed_irrigation_event(text,timestamptz,text,text,numeric,numeric,jsonb)")).fetchone()[0] is allowed
        with pytest.raises(psycopg.Error, match="append-only"):
            with db.transaction():
                db.execute("delete from public.irrigation_events where zone_id='A12345'")
        bad = {**events[0], "irrigation_event_id": "SYNTHETIC-E", "zone_id": "E12345"}
        with pytest.raises(psycopg.Error, match="invalid typed"):
            with db.transaction(): append_history(db, bad)


def test_real_a_migration_replay_and_unexpected_predecessor_rejected_before_change(database):
    import psycopg
    migration = (Path(__file__).resolve().parents[1] / "supabase/migrations" / MIGRATIONS[-1]).read_text()
    identity = "public.rootline_append_typed_irrigation_event(text,timestamptz,text,text,numeric,numeric,jsonb)"
    with psycopg.connect(database) as db:
        before = db.execute("select pg_get_functiondef(%s::regprocedure)", (identity,)).fetchone()[0]
        db.execute(migration)
        assert db.execute("select pg_get_functiondef(%s::regprocedure)", (identity,)).fetchone()[0] == before
        with pytest.raises(psycopg.Error, match="prerequisite differs"):
            with db.transaction():
                db.execute(before.replace("return found;", "return false;"))
                db.execute(migration)
        assert db.execute("select pg_get_functiondef(%s::regprocedure)", (identity,)).fetchone()[0] == before
        assert db.execute("select count(*) from public.irrigation_events").fetchone()[0] == 3


def test_real_a_own_commissioning_authority_and_append_only_revocation(database):
    import psycopg
    from modules.telemetry.rootline_device_spine import store_device_record
    from modules.telemetry.rootline_ewelink_commissioned_baseline import load_canonical_a_irrigation_binding
    from modules.telemetry.rootline_execution_runtime import _canonical_standing_authority_proven
    record = canonical_record()
    policy = a_authority_policy()
    envelope = record["authority_envelope"]
    envelope["policy_sha256"] = digest(policy)
    ref = envelope["irrigation_commissioning"]["reference"]
    with psycopg.connect(database) as db:
        db.execute("insert into app_private.rootline_device_commissioning_evidence(evidence_id,source,observed_at,evidence_sha256,evidence_payload) values(%s,%s,%s,%s,%s::jsonb)",
            (ref["evidence_id"], ref["source"], ref["observed_at"], ref["sha256"], json.dumps(envelope["irrigation_commissioning"])))
        db.execute("insert into app_private.rootline_standing_authorities(standing_authority_id,version,issuer,policy_sha256,active,policy_payload) values(%s,%s,%s,%s,true,%s::jsonb)",
            (envelope["standing_authority_id"], envelope["version"], envelope["issuer"], envelope["policy_sha256"], json.dumps(policy)))
    connect = lambda: psycopg.connect(database)
    first = store_device_record(record, connect_factory=connect)
    assert first["success"] is True and first["replayed"] is False
    assert store_device_record(record, connect_factory=connect)["replayed"] is True
    binding = load_canonical_a_irrigation_binding(connect_factory=connect, now=NOW)
    assert binding["canonical_registry_sha256"] == first["evidence_digest"]
    with commissioned_a():
        assert _canonical_standing_authority_proven(database,
            {"zone_id": "A12345", "channel": 4, "maximum_duration_seconds": 2100})
    with connect() as db:
        db.execute("insert into app_private.rootline_authority_events(event_id,standing_authority_id,version,event_type,reason) values(%s,%s,%s,'revoked','synthetic regression')",
            ("SYNTHETIC-A-REVOKE", envelope["standing_authority_id"], envelope["version"]))
        assert db.execute("select count(*) from app_private.rootline_device_registry_history where device_key=%s", (first["device_key"],)).fetchone()[0] == 1
    with pytest.raises(ValueError): load_canonical_a_irrigation_binding(connect_factory=connect, now=NOW)
    with commissioned_a():
        assert not _canonical_standing_authority_proven(database,
            {"zone_id": "A12345", "channel": 4, "maximum_duration_seconds": 2100})


def test_real_abc_parallel_claims_have_exactly_one_winner_and_replay_is_inert(database, monkeypatch):
    import psycopg
    from modules.telemetry import rootline_irrigation_execution_store as store
    monkeypatch.setenv("DATABASE_URL", database)
    prefix = "a-synthetic-parallel-" + uuid.uuid4().hex
    monkeypatch.setattr(store, "EVENT_SOURCE", prefix)
    bodies = [{"execution_id": prefix + zone, "zone_id": zone, "device_id": "100204e9bc",
        "channel": channel, "operating_date": NOW.date().isoformat(), "consumption_key": prefix + zone,
        "eligibility_id": prefix + "eligibility-" + zone, "eligibility_sha256": digest(zone),
        "segment_number": 1, "claimed_at": NOW.isoformat()} for zone, channel in (
            ("A12345", 4), ("B12345", 1), ("C12345", 2))]
    for body in bodies:
        assert store.rootline_irrigation_execution_store("record_eligibility", body)["success"]
    barrier = Barrier(3)
    def claim(body):
        with commissioned_a():
            barrier.wait(timeout=10)
            return store.rootline_irrigation_execution_store("claim_before_on", body)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(claim, bodies))
    assert sum(row["created"] for row in results) == 1, results
    assert sorted(row["status"] for row in results) == ["claimed", "controller_active", "controller_active"]
    winner = next(body for body, result in zip(bodies, results) if result["created"])
    with commissioned_a():
        replay = store.rootline_irrigation_execution_store("claim_before_on", winner)
    assert replay["status"] == "execution_replay" and replay["created"] is False
    with psycopg.connect(database) as db:
        assert db.execute("select count(*) from public.sam_live_stock_conversation_review_events where event_source=%s and recommended_action='claim_before_on'", (prefix,)).fetchone()[0] == 1


def test_real_policy_successor_round_trips_without_changing_prior_bc_payload(database):
    from modules.telemetry.rootline_operating_policy import PostgresPolicyStore, prepare_policy_proposal
    from tests.test_rootline_operating_policy import proposal_payload, unknown_policy
    store = PostgresPolicyStore(database_url=database)
    old = prepare_policy_proposal(proposal_payload("synthetic-bc"), "synthetic-owner", now=NOW)
    new = prepare_policy_proposal(proposal_payload("synthetic-abc", successor()), "synthetic-owner", now=NOW + timedelta(seconds=1))
    original = store.append_proposal(old)
    appended = store.append_proposal(new)
    replay = store.append_proposal(new)
    assert original["created"] and appended["created"] and not replay["created"]
    assert appended["proposal"]["policy"]["zones"]["A12345"]["requested_total_duration_minutes"] == 35
    assert set(original["proposal"]["policy"]["zones"]) == set(unknown_policy()["zones"])
    assert appended["proposal"]["version"] == original["proposal"]["version"] + 1


def test_real_a_rain_stop_rolls_back_partial_failure_then_replays_without_credit(database, monkeypatch):
    import psycopg
    from modules.telemetry import rootline_irrigation_execution_store as store
    from modules.telemetry import rootline_irrigation_coordinator as coordinator
    from modules.telemetry.rootline_execution_runtime import assess_active_irrigation_weather
    from modules.telemetry.rootline_irrigation_history import project_canonical_irrigation_history, _attach_parent_jobs
    from tests.test_rootline_active_weather_stop import subject, Transport, weather_packet, NOW as RAIN_NOW
    monkeypatch.setenv("DATABASE_URL", database)
    prefix = "a-synthetic-rain-" + uuid.uuid4().hex
    monkeypatch.setattr(store, "EVENT_SOURCE", prefix)
    job, active = subject(zone="A12345")
    active["channel"] = active["start_evidence"]["channel"] = 4
    active.update(commissioning_id=a_binding()["commissioning_id"],
        eligibility_id=prefix + "-eligibility", eligibility_sha256="a" * 64,
        consumption_key=prefix + "-consumption")
    authority = {**active, "job": job}
    assert store.rootline_irrigation_execution_store("record_eligibility", authority)["success"]
    with commissioned_a():
        assert store.rootline_irrigation_execution_store("claim_before_on", active)["created"]
    assert store.rootline_irrigation_execution_store("record_on_outcome", {
        **active, "on_outcome": {"accepted_unambiguous": True}})["success"]
    assert store.rootline_irrigation_execution_store("mark_active", active)["success"]
    transport = Transport()
    def stop():
        return coordinator.advance_irrigation_execution(decision_id="", commissioning_id="",
            decision_reader=lambda _: {}, commissioning_reader=lambda _: {},
            store=store.rootline_irrigation_execution_store, transport=transport,
            notify=lambda *_: {"provider_delivery_confirmed": True}, now=RAIN_NOW, clock=lambda: RAIN_NOW,
            active_only=True, active_weather_revalidator=lambda _: assess_active_irrigation_weather(
                weather_packet(rain=1), now=RAIN_NOW))
    with monkeypatch.context() as failure:
        failure.setattr(store, "_append_history", lambda *_a, **_k: False)
        assert stop()["status"] == "completion_persistence_unproven"
    assert store.rootline_irrigation_execution_store("load_active", None)["state"] == "stopping"
    stopped = stop()
    assert stopped["status"] == "segment_stopped_for_weather"
    assert store.rootline_irrigation_execution_store("load_active", None) is None
    terminal = stopped["execution"]
    assert terminal["verified_runtime_seconds"] == 0 and terminal["objective_satisfied"] is False
    assert store.rootline_irrigation_execution_store("record_completed", terminal)["created"] is False
    with psycopg.connect(database) as db:
        rows = db.execute("select irrigation_event_id,event_at,event_type,zone_id,planned_minutes,actual_minutes,details,source_id,actor,created_at from public.irrigation_events where details->>'execution_id'=%s", (active["execution_id"],)).fetchall()
        partials = [row for row in rows if row[2] == "PARTIAL"]
        assert len(partials) == 1 and partials[0][5] is None
        assert partials[0][6]["partial_observation"]["physical_delivery"] == "Unknown"
        assert db.execute("select count(*) from public.irrigation_water_credit_events").fetchone()[0] == 0
    projected = project_canonical_irrigation_history(rows, snapshot_cutoff=RAIN_NOW)
    events = store.rootline_irrigation_execution_store("load_job_events", job["job_id"])
    _attach_parent_jobs(projected, events, canonical_ordered=True)
    assert projected["zones"]["A12345"]["verified_completed_days"] == []
    assert all(call["state"] == "OFF" and call["channel"] == 4 for call in transport.calls)
