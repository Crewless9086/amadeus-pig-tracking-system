"""Atomic cancellation/completion qualification on an owned disposable database.

No production URL fallback, provider reads, migrations of a shared database, or
hardware calls. PostgreSQL cases use the canonical migrations and real writers.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import uuid

import pytest

store = importlib.import_module("modules.telemetry.rootline_irrigation_execution_store")
resolution = importlib.import_module("modules.telemetry.rootline_parent_job_resolution")
from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment


def subject(zone="B12345"):
    now = datetime.now(timezone.utc)
    job = build_irrigation_job(zone_id=zone, operating_date=now.date().isoformat(),
        requested_total_seconds=7200, maximum_segment_seconds=3599,
        plan_identity="SYNTHETIC-" + uuid.uuid4().hex, requested_total_minutes=120,
        expected_segment_count=2)
    first = project_next_segment(job, [], rearm_readback_off=True)
    parent = {"job": job, "projection": {"status": "segment_contained",
        "current_segment": 1, "cumulative_verified_runtime_seconds": 0},
        "remaining_seconds": 7198}
    controller = {"online": True, "device_id": "100204e9bc",
        "retrieved_at": now.isoformat(), "provider_observed_at": now.isoformat(),
        "response_digest": "SYNTHETIC-OFF-1", "observation_fresh": True,
        "current_outputs_authoritative": True,
        "channels": [{"channel": n, "output_state": "OFF"} for n in range(1, 5)]}
    authorization = {"mission_id": "RMQ-20260813-04", "decision": "cancel_unverified_remainder",
        "job_id": job["job_id"], "job_sha256": job["job_sha256"], "owner_principal": "synthetic-owner"}
    identity = "SYNTHETIC-EXEC-" + uuid.uuid4().hex
    common = {"execution_id": identity, "job_id": job["job_id"], "job_sha256": job["job_sha256"],
        "zone_id": zone, "operating_date": job["operating_date"], "segment_number": 1,
        "segment_identity": first["segment_identity"], "planned_runtime_minutes": 3599 / 60}
    eligibility = {**common, "action": "record_eligibility", "state": "planned",
        "requested_total_duration_seconds": 7200, "requested_total_duration_minutes": 120,
        "governed_executable_duration_seconds": 7198, "expected_segment_count": 2,
        "plan_generation": job["plan_identity"]}
    rows = [eligibility, {**common, "action": "claim_before_on", "state": "claimed"},
        {**common, "action": "contain_zone", "state": "Contained", "shutdown_verified": False,
         "reason": "restart_after_pre_on_claim"},
        {**common, "action": "record_claim_recovery", "state": "claimed_recovery_required",
         "shutdown_verified": True, "shutdown_evidence": {"state": "OFF", "authoritative": True}}]
    completion = {**common, "state": "Completed", "verified_runtime_seconds": 3599,
        "shutdown_verified": True, "completed_at": (now - timedelta(seconds=1)).isoformat(),
        "objective_satisfied": False, "objective_evidence": {"verified_runtime_minutes": 3599 / 60},
        "start_evidence": {"evidence_id": "SYNTHETIC-ON"},
        "shutdown_evidence": {"state": "OFF", "authoritative": True, "evidence_id": "SYNTHETIC-OFF"}}
    return SimpleNamespace(now=now, job=job, parent=parent, controller=controller,
        authorization=authorization, rows=rows, completion=completion)


def packet(case, *, controller=None, parent=None):
    controller = controller or case.controller
    value = resolution.build_contained_parent_cancellation(parent=parent or case.parent,
        controller=controller, authorization=case.authorization, now=datetime.now(timezone.utc))
    return {**value, "_current_controller": controller}


class EmptyHistory:
    def cursor(self):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def execute(self, *_):
        pass
    def fetchall(self):
        return []


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_locked_projection_reuses_canonical_parent_and_rejects_later_active(zone):
    case = subject(zone)
    rows = [(row, case.now - timedelta(minutes=2)) for row in case.rows]
    result = store._locked_contained_parent(EmptyHistory(), packet(case), rows, case.now)
    assert result["remaining_seconds"] == 7198
    assert result["projection"] == case.parent["projection"] | {"command_authority": False}
    rows.append(({**case.rows[1], "action": "mark_active", "state": "Active"}, case.now))
    with pytest.raises(ValueError, match="contained_parent_execution_changed"):
        store._locked_contained_parent(EmptyHistory(), packet(case), rows, case.now)


def test_locked_projection_rejects_legacy_history_first_orphan():
    case = subject()
    class OrphanHistory(EmptyHistory):
        def fetchall(self):
            return [("old-history", case.now, "PARTIAL", "B12345", 60, 60,
                     {"execution_id": case.completion["execution_id"]}, "irrigation-controller-main", "ROOTLINE", case.now)]
    with pytest.raises(ValueError, match="completion_history_unreconciled"):
        store._locked_contained_parent(OrphanHistory(), packet(case),
            [(row, case.now) for row in case.rows], case.now)


@pytest.fixture
def database(monkeypatch, record_property):
    if not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"):
        pytest.skip("disposable ROOTLINE PostgreSQL URL is required")
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from psycopg.types.json import Jsonb

    admin_url = os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    target = conninfo_to_dict(admin_url)
    assert target.get("host") == "127.0.0.1"
    assert target.get("port", "").isdigit() and 0 < int(target["port"]) < 65536
    assert target.get("dbname") == "rootline_managed"
    name = "rootline_managed_resolution_" + uuid.uuid4().hex
    url = make_conninfo(admin_url, dbname=name)

    def check(connection):
        assert connection.info.host == "127.0.0.1"
        assert connection.info.port == int(target["port"])
        assert connection.info.dbname == "rootline_managed"
        assert name.startswith("rootline_managed_resolution_") and name != target["dbname"]

    with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as admin:
        check(admin)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
        with psycopg.connect(url, connect_timeout=3) as connection:
            # Existing test cluster roles are prerequisites, never new grants.
            assert connection.execute("select count(*) from pg_roles where rolname=any(%s)",
                (["anon", "authenticated", "service_role"],)).fetchone()[0] == 3
            for filename in (
                "202605210001_foundation_migration_log.sql",
                "202605210005_create_telemetry_power_tables.sql",
                "202605230001_create_irrigation_tables.sql",
                "202607070001_create_sam_live_stock_conversation_review_events.sql",
                "202608050001_harden_irrigation_events_history.sql",
            ):
                connection.execute((migrations / filename).read_text(encoding="utf-8"))
            connection.execute("""insert into public.irrigation_zones(zone_id,zone_name)
                values ('B12345','Synthetic B'),('C12345','Synthetic C')""")
        monkeypatch.setenv("DATABASE_URL", url)

        def seed(rows, *, connection=None, at=None):
            from contextlib import nullcontext
            with (nullcontext(connection) if connection is not None else psycopg.connect(url)) as conn:
                for index, row in enumerate(rows):
                    conn.execute("""insert into public.sam_live_stock_conversation_review_events
                        (review_event_id,event_source,review_json,created_at)
                        values (%s,%s,%s,%s)""", (row.get("event_id") or "SYNTHETIC-" + uuid.uuid4().hex,
                        store.EVENT_SOURCE, Jsonb({"rootline_execution": row}),
                        (at or datetime.now(timezone.utc) - timedelta(minutes=2)) + timedelta(microseconds=index)))

        def read():
            with psycopg.connect(url) as connection:
                audit = connection.execute("""select review_event_id,event_source,review_json
                    from public.sam_live_stock_conversation_review_events
                    order by created_at,review_event_id""").fetchall()
                typed = connection.execute("select * from public.irrigation_events order by irrigation_event_id").fetchall()
            return audit, typed

        def wait_for_blocked():
            deadline = time.monotonic() + 0.8
            with psycopg.connect(url, autocommit=True) as connection:
                while time.monotonic() < deadline:
                    if connection.execute("""select count(*) from pg_stat_activity
                        where datname=%s and wait_event_type='Lock' and wait_event='advisory'""",
                        (name,)).fetchone()[0]:
                        return
                    time.sleep(0.005)
            pytest.fail("second transaction did not wait for the existing advisory lock")

        yield SimpleNamespace(url=url, seed=seed, read=read, wait_for_blocked=wait_for_blocked)
    finally:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as admin:
            check(admin)
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            assert admin.execute("select count(*) from pg_database where datname=%s", (name,)).fetchone()[0] == 0
        record_property("owned_fixture_database_removed", True)


def cancel(value):
    return store.rootline_irrigation_execution_store("record_job_resolution", value)


def complete(case):
    return store.rootline_irrigation_execution_store("record_completed", case.completion)


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_first_cancellation_and_new_off_replay_preserve_exact_first_row(database, zone):
    case = subject(zone)
    database.seed(case.rows)
    first = cancel(packet(case))
    before = database.read()
    changed_off = {**case.controller, "response_digest": "SYNTHETIC-OFF-2"}
    replay = cancel(packet(case, controller=changed_off))
    assert first["success"] is replay["success"] is True
    assert first["created"] is True and replay["created"] is False
    assert first["resolution"] == replay["resolution"]
    assert database.read() == before
    assert not before[1] and len(before[0]) == len(case.rows) + 1
    saved = first["resolution"]
    assert "_current_controller" not in saved
    assert saved["event_id"] == store._event_id("record_job_resolution", packet(case))
    assert saved["provider_off_evidence_digest"] == "SYNTHETIC-OFF-1"
    assert saved["cancelled_unverified_remaining_seconds"] == 7198
    assert saved["water_credit_created"] is False and saved["fabricated_runtime_seconds"] == 0
    bad = packet(case)
    bad["owner_principal"] = "different-owner"
    with pytest.raises(ValueError, match="history_conflict"):
        cancel(bad)
    assert database.read() == before


def test_two_cancellations_wait_and_converge_without_overwriting_off_receipt(database, monkeypatch):
    case = subject()
    database.seed(case.rows)
    entered, release = threading.Event(), threading.Event()
    real = store._locked_contained_parent
    def hold_first(*args):
        entered.set()
        assert release.wait(2)
        return real(*args)
    monkeypatch.setattr(store, "_locked_contained_parent", hold_first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cancel, packet(case))
        assert entered.wait(1)
        second = pool.submit(cancel, packet(case, controller={**case.controller, "response_digest": "SECOND"}))
        try:
            database.wait_for_blocked()
        finally:
            release.set()
        one, two = first.result(timeout=3), second.result(timeout=3)
    assert one["created"] is True and two["created"] is False
    assert one["resolution"] == two["resolution"]
    assert len(database.read()[0]) == len(case.rows) + 1


def test_state_change_committed_while_cancellation_waits_is_rejected(database):
    import psycopg
    case = subject()
    database.seed(case.rows)
    before = database.read()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with psycopg.connect(database.url) as blocker:
            blocker.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            blocker.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
            pending = pool.submit(cancel, packet(case))
            database.wait_for_blocked()
            database.seed([{**case.rows[1], "action": "mark_active", "state": "Active"}],
                connection=blocker, at=datetime.now(timezone.utc))
        with pytest.raises(ValueError, match="execution_changed"):
            pending.result(timeout=3)
    audit, typed = database.read()
    assert len(audit) == len(before[0]) + 1 and typed == before[1]
    assert not any(row[2]["rootline_execution"]["action"] == "record_job_resolution" for row in audit)


def test_prepared_claim_waiting_behind_cancellation_is_refused_and_old_claim_replay_is_read_only(database, monkeypatch):
    case = subject()
    original = case.rows[1]
    original.update(consumption_key="SYNTHETIC-ORIGINAL", eligibility_id="SYNTHETIC-ELIG-OLD",
                    eligibility_sha256="a" * 64)
    original["event_id"] = store._event_id("claim_before_on", original)
    prepared = {**original, "execution_id": "SYNTHETIC-NEXT-" + uuid.uuid4().hex,
        "consumption_key": "SYNTHETIC-NEW", "eligibility_id": "SYNTHETIC-ELIG-NEW"}
    prepared.pop("event_id")
    database.seed([*case.rows, {**case.rows[0], "execution_id": prepared["execution_id"],
        "eligibility_id": prepared["eligibility_id"], "eligibility_sha256": prepared["eligibility_sha256"]}])
    entered, release = threading.Event(), threading.Event()
    real = store._locked_contained_parent
    def held(*args):
        entered.set()
        assert release.wait(2)
        return real(*args)
    monkeypatch.setattr(store, "_locked_contained_parent", held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancellation = pool.submit(cancel, packet(case))
        assert entered.wait(1)
        claim = pool.submit(store.rootline_irrigation_execution_store, "claim_before_on", prepared)
        try:
            database.wait_for_blocked()
        finally:
            release.set()
        assert cancellation.result(timeout=3)["created"] is True
        assert claim.result(timeout=3) == {
            "success": True, "created": False, "status": "parent_job_cancelled"}
    before = database.read()
    assert store.rootline_irrigation_execution_store("claim_before_on", original) == {
        "success": True, "created": False, "status": "execution_replay"}
    assert database.read() == before
    assert not any(row[2]["rootline_execution"].get("execution_id") == prepared["execution_id"]
        and row[2]["rootline_execution"]["action"] == "claim_before_on" for row in before[0])


@pytest.mark.parametrize("winner", ["completion", "cancellation"])
def test_completion_and_cancellation_winner_is_atomic_in_both_orders(database, monkeypatch, winner):
    case = subject()
    database.seed(case.rows)
    entered, release = threading.Event(), threading.Event()
    helper = "_append_history" if winner == "completion" else "_locked_contained_parent"
    real = getattr(store, helper)
    def held(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return real(*args, **kwargs)
    monkeypatch.setattr(store, helper, held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(complete, case) if winner == "completion" else pool.submit(cancel, packet(case))
        assert entered.wait(1)
        second = pool.submit(cancel, packet(case)) if winner == "completion" else pool.submit(complete, case)
        try:
            database.wait_for_blocked()
        finally:
            release.set()
        assert first.result(timeout=3)["success"] is True
        with pytest.raises(ValueError, match="preimage_changed|completion_refused"):
            second.result(timeout=3)
    audit, typed = database.read()
    assert len(audit) == len(case.rows) + 1
    assert len(typed) == (1 if winner == "completion" else 0)


def test_completion_duplicate_and_replay_after_remainder_cancellation_are_zero_write(database):
    case = subject()
    database.seed(case.rows)
    first = complete(case)
    before = database.read()
    replay = complete(case)
    assert first["created"] is True and replay["created"] is False
    assert database.read() == before and len(before[1]) == 1
    parent = deepcopy(case.parent)
    parent["projection"].update(current_segment=2, cumulative_verified_runtime_seconds=3599)
    parent["remaining_seconds"] = 3599
    assert cancel(packet(case, parent=parent))["success"] is True
    after = database.read()
    assert complete(case)["created"] is False
    assert database.read() == after


def test_changed_completion_cannot_add_another_credit_classification(database):
    case = subject()
    database.seed(case.rows)
    assert complete(case)["success"] is True
    before = database.read()
    case.completion["objective_satisfied"] = True
    with pytest.raises(ValueError, match="canonical_completion_history_conflict"):
        complete(case)
    assert database.read() == before


@pytest.mark.parametrize("failure", ["audit", "readback", "history"])
def test_completion_failure_rolls_back_both_rails(database, monkeypatch, failure):
    case = subject()
    database.seed(case.rows)
    before = database.read()
    if failure == "audit":
        canonical = importlib.import_module("modules.sales.sam_live_stock_launch_control")
        monkeypatch.setattr(canonical, "record_sam_live_stock_review_event",
            lambda *args, **kwargs: ({"success": False}, 500))
    elif failure == "readback":
        real = store._read_terminal_review
        calls = []
        def mismatch(*args):
            result = real(*args)
            calls.append(result)
            return {"corrupt": True} if result is not None else None
        monkeypatch.setattr(store, "_read_terminal_review", mismatch)
    else:
        import psycopg
        with psycopg.connect(database.url) as connection:
            connection.execute("""create function public.reject_completion_test() returns trigger
                language plpgsql as $$begin raise exception 'synthetic history failure'; end;$$""")
            connection.execute("""create trigger reject_completion_test before insert on public.irrigation_events
                for each row execute function public.reject_completion_test()""")
    result = complete(case)
    assert result["success"] is False and result["created"] is False
    assert database.read() == before


def test_cancellation_readback_failure_rolls_back_the_insert(database, monkeypatch):
    case = subject()
    database.seed(case.rows)
    before = database.read()
    monkeypatch.setattr(store, "_read_terminal_review", lambda *_: {"unexpected": True})
    result = cancel(packet(case))
    assert result["success"] is False
    assert database.read() == before


def test_completion_replay_does_not_repair_missing_typed_history(database):
    case = subject()
    database.seed(case.rows)
    import psycopg
    with psycopg.connect(database.url) as connection:
        store._write_terminal_review(connection, "record_completed", case.completion)
    before = database.read()
    assert not before[1]
    result = complete(case)
    assert result["success"] is False
    assert database.read() == before


def test_legacy_history_first_orphan_blocks_cancellation_without_mutation(database):
    case = subject()
    database.seed(case.rows)
    assert store._append_history("record_completed", case.completion) is True
    before = database.read()
    with pytest.raises(ValueError, match="completion_history_unreconciled"):
        cancel(packet(case))
    assert database.read() == before
