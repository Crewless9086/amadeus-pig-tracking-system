"""Opt-in retained local fixture for actual A journal/claim/budget concurrency."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from threading import Barrier, Event, current_thread
import time
import uuid

import pytest

from tests.test_rootline_a_commissioning_admission import (
    digest, grant, journal_rows, runtime, snapshot, transport)
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.oom_sakkie import bounded_postgres_read as native

URL = os.getenv("ROOTLINE_A_COMMISSIONING_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="requires separately leased local A commissioning database")
MIGRATION = "202607070001_create_sam_live_stock_conversation_review_events.sql"


@pytest.fixture(scope="module")
def database():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    info = conninfo_to_dict(URL)
    assert info.get("host") in {"127.0.0.1", "localhost"}
    assert info.get("port", "5432") in {"5432", "65437"}
    assert re.fullmatch(r"rootline_a_commissioning_test(?:_[a-f0-9]{12})?", info.get("dbname", ""))
    # Root/CI creates this dedicated DB. Never create/drop/reset any database.
    with psycopg.connect(URL) as db:
        assert db.execute("select current_database()").fetchone()[0] == info["dbname"]
        if db.execute("select to_regclass('public.sam_live_stock_conversation_review_events')").fetchone()[0] is None:
            db.execute((Path(__file__).resolve().parents[1] / "supabase/migrations" / MIGRATION).read_text())
        if db.execute("select to_regclass('public.irrigation_events')").fetchone()[0] is None:
            for name in ("202605210001_foundation_migration_log.sql",
                         "202605210005_create_telemetry_power_tables.sql",
                         "202605230001_create_irrigation_tables.sql"):
                db.execute((Path(__file__).resolve().parents[1] / "supabase/migrations" / name).read_text())
        assert db.execute("select count(*) from public.irrigation_events").fetchone()[0] == 0
    yield URL
    with psycopg.connect(URL) as db:
        assert db.execute("select count(*) from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid()").fetchone()[0] == 0
        assert db.execute("select count(*) from public.irrigation_events").fetchone()[0] == 0
        db.rollback()


@pytest.fixture
def rail(database, runtime, monkeypatch):
    import psycopg
    prefix = "synthetic-a-commissioning-" + uuid.uuid4().hex
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setattr(store, "EVENT_SOURCE", prefix + "-ordinary")
    monkeypatch.setattr(store, "_A_COMMISSIONING_SOURCE", prefix + "-operator")
    monkeypatch.setattr(budget, "EVENT_SOURCE", prefix + "-budget")
    monkeypatch.setattr(budget, "LEDGER_ID", prefix + "-ledger")
    connections = []
    def connect(**kwargs):
        db = psycopg.connect(database, connect_timeout=3,
            options="-c statement_timeout=5000 -c lock_timeout=3000")
        connections.append(db)
        return db
    monkeypatch.setattr(native, "connect_bounded_rootline_postgres", connect)
    yield connect
    assert all(db.closed for db in connections)


def record_journal(row):
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event({"conversation_id": row["mission_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "rootline_operational_intake"},
        event_source=store._A_COMMISSIONING_SOURCE)
    event.update(review_event_id=row["event_id"], chatwoot_conversation_id=row["mission_id"],
        review_json={"rootline_operational_intake": row}, decision_json={}, facts_json={},
        customer_message_excerpt="", sam_reply_excerpt="")
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: native.connect_bounded_rootline_postgres(read_only=False))
    assert status < 400 and result["created"] is True


def prepare(*, reader=None, sender=None, mutate_grant=None, mutate_command=None):
    instance, calls = transport(reader=reader, sender=sender)
    observation = instance.read_a_commissioning_configuration()
    value = grant(observation)
    if mutate_grant: mutate_grant(value)
    rows = journal_rows(value, observation)
    if mutate_command: mutate_command(rows[1])
    for row in rows: record_journal(row)
    operation = value["operation_id"]
    permit = instance.prepare_execution_capacity({"execution_id": store._a_id(operation, "A-EXECUTION"),
        "device_id": "100204e9bc", "channel": 4})
    body = {"operation_id": operation, "grant_sha256": digest(value),
        "configuration": observation, "provider_capacity_permit": permit}
    return instance, calls, body, value


def claim(body):
    result = store.rootline_irrigation_execution_store("claim_a_commissioning_before_on", body)
    assert result.get("created") is True, result
    return result["operation_claim"]


def state(operation):
    result = store.rootline_irrigation_execution_store("load_a_commissioning_operation", {"operation_id": operation})
    assert result.get("success") is True, result
    return result


def edge(claimed, instance):
    return store.rootline_irrigation_execution_store("dispatch_a_commissioning_on_edge",
        {"operation_claim": claimed, "transport": instance})


def off(claimed, instance, attempt):
    return store.rootline_irrigation_execution_store("claim_a_commissioning_off_attempt",
        {"operation_claim": claimed, "transport": instance, "attempt": attempt})


def observe(claimed, instance):
    return store.rootline_irrigation_execution_store("observe_a_commissioning",
        {"operation_claim": claimed, "transport": instance})


def reserve_present(claimed, instance):
    accounting = budget.RequestBudget(instance._request_environment())
    with accounting._locked() as db:
        return claimed["execution_id"] in accounting._load(db)["reserves"]


def finish(claimed, instance):
    return store.rootline_irrigation_execution_store("finish_a_commissioning",
        {"operation_claim": claimed, "transport": instance})


def normal_claim(zone="B12345"):
    identity = "synthetic-normal-" + uuid.uuid4().hex
    row = {"execution_id": identity, "zone_id": zone, "device_id": "100204e9bc",
        "channel": 1 if zone == "B12345" else 2, "operating_date": datetime.now(timezone.utc).date().isoformat(),
        "consumption_key": identity, "eligibility_id": identity + "-eligibility",
        "eligibility_sha256": digest(identity), "claimed_at": datetime.now(timezone.utc).isoformat()}
    assert store.rootline_irrigation_execution_store("record_eligibility", row)["success"]
    return row


def test_exact_operation_dispatches_once_and_never_writes_irrigation_history(rail):
    outputs = {}
    instance, calls, body, value = prepare(reader=lambda: snapshot(states=outputs))
    claimed = claim(body)
    assert state(value["operation_id"])["unresolved"]
    assert not instance.set_a_commissioning_state(operation_claim=claimed, state="ON",
        idempotency_key=claimed["execution_id"] + ":ON")["accepted_unambiguous"]
    sent = edge(claimed, instance)
    assert sent.get("sender_authorized") is True, sent
    assert sent["outcome"]["accepted_unambiguous"] is True
    assert len(calls) == 1 and "irrigation_1_ch4_on" in calls[0]["url"]
    assert calls[0]["body"]["value2"] == "100204e9bc" and calls[0]["body"]["value3"] == "4"
    assert not edge(claimed, instance)["success"] and len(calls) == 1
    blocked = store.rootline_irrigation_execution_store("claim_before_on", normal_claim())
    assert blocked["status"] == "a_commissioning_unresolved"
    first_off = observe(claimed, instance)
    assert first_off["observation"]["state"] == "OFF" and first_off["startup_state"] == "outstanding"
    assert reserve_present(claimed, instance)
    with budget.execution_duty(claimed):
        assert instance.read_output_state(device_id="100204e9bc", channel=4)["state"] == "OFF"
    assert reserve_present(claimed, instance)
    refused = finish(claimed, instance)
    assert refused["status"] == "a_commissioning_startup_outstanding" and not refused["provider_read_performed"]
    assert state(value["operation_id"])["unresolved"] and reserve_present(claimed, instance)
    outputs[4] = "ON"
    started = observe(claimed, instance)
    assert started["startup_state"] == "delivered_start" and started["delivered_start"]["within_startup_window"]
    assert observe(claimed, instance)["delivered_start"] == started["delivered_start"]
    assert off(claimed, instance, 1)["outcome"]["accepted_unambiguous"]
    outputs.clear()
    ended = finish(claimed, instance)
    assert ended.get("created") is True, ended
    assert ended["retirement"]["native_auto_off_proven"] is False
    assert ended["history_event_created"] is False
    assert ended["retirement"]["safe_branch"] == "delivered_start"
    assert not reserve_present(claimed, instance)
    assert state(value["operation_id"])["retired"] is True
    assert not edge(claimed, instance)["success"]
    with rail() as db:
        assert db.execute("select count(*) from public.sam_live_stock_conversation_review_events where event_source=%s and review_json->'rootline_execution'->>'action' in ('claim_before_on','mark_active','record_completed')", (store.EVENT_SOURCE,)).fetchone()[0] == 0
        rows = db.execute("select review_json from public.sam_live_stock_conversation_review_events where event_source=%s order by created_at", (budget.EVENT_SOURCE,)).fetchall()
        assert any("active_duty_off_verified" in json.dumps(row) for row in rows)


@pytest.mark.parametrize("attack", ["wrong_snapshot", "wrong_source", "wrong_grant", "extra_key", "no_journal"])
def test_actual_canonical_claim_refuses_before_any_new_commissioning_effect(rail, attack):
    instance, calls, body, value = prepare()
    if attack == "wrong_snapshot": body["configuration"]["response_digest"] = "f" * 64
    elif attack == "wrong_source": body["configuration"]["snapshot"]["actuation_configuration_safe"] = False
    elif attack == "wrong_grant": body["grant_sha256"] = "f" * 64
    elif attack == "extra_key": body["allow_uncommissioned"] = True
    elif attack == "no_journal": body["operation_id"] = uuid.uuid4().hex
    result = store.rootline_irrigation_execution_store("claim_a_commissioning_before_on", body)
    assert not result["success"], result
    assert state(value["operation_id"])["operation_claim"] is None and not calls


def test_actual_abc_and_commissioning_claim_race_has_exactly_one_winner(rail):
    instance, calls, body, _ = prepare()
    ordinary = [normal_claim(zone) for zone in ("B12345", "C12345")]
    barrier = Barrier(3)
    def run(pair):
        barrier.wait(timeout=5)
        return store.rootline_irrigation_execution_store(*pair)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, [("claim_a_commissioning_before_on", body),
            *(('claim_before_on', row) for row in ordinary)]))
    assert sum(result.get("created") is True for result in results) == 1, results
    assert not calls


def test_existing_normal_unsent_claim_blocks_first_use(rail):
    ordinary = normal_claim()
    assert store.rootline_irrigation_execution_store("claim_before_on", ordinary)["created"]
    _, calls, body, value = prepare()
    result = store.rootline_irrigation_execution_store("claim_a_commissioning_before_on", body)
    assert result["status"] == "a_commissioning_controller_unresolved" and not calls
    assert state(value["operation_id"])["operation_claim"] is None


def test_expiry_revocation_and_ordinary_a_flag_do_not_remove_three_owned_off_slots(rail, monkeypatch):
    instance, calls, body, value = prepare(mutate_grant=lambda g: g.update(
        on_expires_at=(datetime.now(timezone.utc) + timedelta(seconds=0.3)).isoformat()))
    claimed = claim(body)
    time.sleep(0.35)
    monkeypatch.setenv("ROOTLINE_A_ENABLED", "true")
    monkeypatch.setenv("ROOTLINE_BC_COMMISSIONED_BASELINE_REVOKED", "true")
    revoked = store.rootline_irrigation_execution_store("revoke_a_commissioning", {"operation_claim": claimed})
    assert revoked.get("created") is True
    for n in (1, 2, 3):
        result = off(claimed, instance, n)
        assert result.get("sender_authorized") is True, result
        assert result["outcome"]["accepted_unambiguous"] is True
        assert off(claimed, instance, n)["success"] is False
    assert off(claimed, instance, 4)["success"] is False
    assert len(calls) == 3 and all("irrigation_1_ch4_off" in call["url"] for call in calls)
    assert not edge(claimed, instance)["success"] and len(calls) == 3
    ended = finish(claimed, instance)
    assert ended.get("created") is True, ended
    assert ended["retirement"]["off_attempts"] == 3
    assert ended["retirement"]["native_auto_off_proven"] is False


def test_unknown_or_sibling_on_final_read_retains_fence_until_new_all_off(rail):
    outputs = {}
    instance, _, body, value = prepare(reader=lambda: snapshot(states=outputs))
    claimed = claim(body)
    for states in ({4: "ON"}, {1: "ON"}):
        outputs.clear(); outputs.update(states)
        assert not finish(claimed, instance)["success"]
        assert state(value["operation_id"])["unresolved"]
        assert store.rootline_irrigation_execution_store("claim_before_on", normal_claim())["status"] == "a_commissioning_unresolved"
    outputs.clear()
    assert finish(claimed, instance)["created"]
    assert store.rootline_irrigation_execution_store("claim_before_on", normal_claim())["created"]


@pytest.mark.parametrize("desired", ["ON", "OFF"])
def test_crash_after_consumption_before_sender_keeps_slot_spent(rail, monkeypatch, desired):
    instance, calls, body, value = prepare(); claimed = claim(body)
    count = 0
    def crash(**kwargs):
        nonlocal count
        count += 1
        if count == 2: raise RuntimeError("synthetic process-loss boundary")
        return rail(**kwargs)
    monkeypatch.setattr(native, "connect_bounded_rootline_postgres", crash)
    result = edge(claimed, instance) if desired == "ON" else off(claimed, instance, 1)
    assert result["success"] is False and not calls
    monkeypatch.setattr(native, "connect_bounded_rootline_postgres", rail)
    actual = state(value["operation_id"])
    assert actual["on_spent"] if desired == "ON" else actual["off_attempts"] == 1
    duplicate = edge(claimed, instance) if desired == "ON" else off(claimed, instance, 1)
    assert not duplicate["success"] and not calls
    assert actual["unresolved"]
    if desired == "ON":
        assert actual["startup_state"] == "outstanding"
        assert finish(claimed, instance)["status"] == "a_commissioning_startup_outstanding"


def test_committed_stop_between_on_transactions_wins(rail, monkeypatch):
    instance, calls, body, value = prepare(); claimed = claim(body)
    consumed, resume = Event(), Event()
    count = 0
    def paused(**kwargs):
        nonlocal count
        if current_thread().name.startswith("on-edge"):
            count += 1
            if count == 2:
                consumed.set(); assert resume.wait(5)
        return rail(**kwargs)
    monkeypatch.setattr(native, "connect_bounded_rootline_postgres", paused)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="on-edge") as pool:
        future = pool.submit(edge, claimed, instance)
        assert consumed.wait(5)
        assert store.rootline_irrigation_execution_store("revoke_a_commissioning", {"operation_claim": claimed})["created"]
        resume.set()
        result = future.result(timeout=10)
    assert not result.get("sender_authorized") and not calls
    assert state(value["operation_id"])["on_spent"]


def test_sender_holds_shared_fence_through_http_and_off_follows_once(rail):
    sending, resume = Event(), Event()
    def sender(request, timeout):
        from tests.test_rootline_a_commissioning_admission import Response
        if "ch4_on" in request.full_url:
            sending.set(); assert resume.wait(5)
        return Response()
    instance, calls, body, _ = prepare(sender=sender); claimed = claim(body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        on_result = pool.submit(edge, claimed, instance)
        assert sending.wait(5)
        off_result = pool.submit(off, claimed, instance, 1)
        time.sleep(0.1)
        assert not off_result.done()
        resume.set()
        assert on_result.result(timeout=10)["outcome"]["accepted_unambiguous"]
        assert off_result.result(timeout=10)["outcome"]["accepted_unambiguous"]
    assert ["ON" if "ch4_on" in call["url"] else "OFF" for call in calls] == ["ON", "OFF"]
    assert not edge(claimed, instance)["success"]


def test_sender_rollback_after_http_does_not_restore_on_slot(rail, monkeypatch):
    instance, calls, body, value = prepare(); claimed = claim(body)
    count = 0
    class RollbackAfterSend:
        def __init__(self, db): self.db = db
        def __enter__(self): return self.db
        def __exit__(self, *args):
            self.db.rollback(); self.db.close()
            raise RuntimeError("synthetic acknowledgement loss after sender")
    def fail_second(**kwargs):
        nonlocal count
        count += 1
        db = rail(**kwargs)
        return RollbackAfterSend(db) if count == 2 else db
    monkeypatch.setattr(native, "connect_bounded_rootline_postgres", fail_second)
    assert edge(claimed, instance)["success"] is False and len(calls) == 1
    monkeypatch.setattr(native, "connect_bounded_rootline_postgres", rail)
    assert state(value["operation_id"])["on_spent"]
    assert not edge(claimed, instance)["success"] and len(calls) == 1


def test_budget_refusal_consumes_on_without_retry_or_send(rail, monkeypatch):
    instance, calls, body, value = prepare(); claimed = claim(body)
    def refused(*args, **kwargs): raise budget.RequestBudgetUnavailable("synthetic refusal")
    monkeypatch.setattr(budget.RequestBudget, "begin_on", refused)
    result = edge(claimed, instance)
    assert result["outcome"]["provider_command_attempted"] is False and not calls
    assert state(value["operation_id"])["on_spent"]
    assert state(value["operation_id"])["startup_state"] == "source_proven_no_send"
    assert not edge(claimed, instance)["success"]
    ended = finish(claimed, instance)
    assert ended["created"] and ended["retirement"]["safe_branch"] == "source_proven_no_send"


def test_source_or_snapshot_change_at_final_edge_prevents_on(rail, monkeypatch):
    states = {}
    instance, calls, body, value = prepare(reader=lambda: snapshot(states=states)); claimed = claim(body)
    states[2] = "ON"
    result = edge(claimed, instance)
    assert result["outcome"]["provider_command_attempted"] is False and not calls
    assert state(value["operation_id"])["on_spent"]


def test_corrupt_retirement_boolean_cannot_clear_fence(rail):
    instance, _, body, value = prepare(); claimed = claim(body)
    with rail() as db:
        store._a_write(db, value["operation_id"], "A-RETIRED", {"claim_sha256": digest(claimed),
            "shutdown_verified": True, "read_started_at": datetime.now(timezone.utc).isoformat(),
            "final_off_evidence": {"state": "OFF"}})
    result = store.rootline_irrigation_execution_store("claim_before_on", normal_claim())
    assert result["status"] == "a_commissioning_unresolved"


def test_native_ceiling_accounts_for_async_start_and_pulse_keeps_short_primary(rail):
    instance, _, body, value = prepare()
    claimed = claim(body)
    at = lambda text: datetime.fromisoformat(text)
    assert claimed["observation_mode"] == "native_timeout"
    assert at(claimed["primary_stop_deadline"]) >= at(claimed["startup_verification_deadline"]) + timedelta(seconds=3599)
    assert at(claimed["primary_stop_deadline"]) <= at(claimed["startup_verification_deadline"]) + timedelta(seconds=3659)
    assert "native_fail_stop_deadline" not in claimed
    assert claimed["native_fail_stop_seconds"] == 3599
    assert finish(claimed, instance)["created"]
    instance, _, body, value = prepare(mutate_grant=lambda g: g.update(
        observation_mode="control_pulse", maximum_runtime_seconds=60))
    claimed = claim(body)
    assert at(claimed["primary_stop_deadline"]) - at(claimed["claimed_at"]) == timedelta(seconds=60)
    assert claimed["native_fail_stop_seconds"] == 3599



def test_owned_off_before_delayed_on_cannot_retire_or_refund(rail):
    outputs = {}
    instance, calls, body, value = prepare(reader=lambda: snapshot(states=outputs))
    claimed = claim(body)
    assert edge(claimed, instance)["outcome"]["accepted_unambiguous"]
    assert off(claimed, instance, 1)["outcome"]["accepted_unambiguous"]
    assert observe(claimed, instance)["observation"]["state"] == "OFF"
    assert not finish(claimed, instance)["success"]
    assert reserve_present(claimed, instance) and state(value["operation_id"])["unresolved"]
    assert store.rootline_irrigation_execution_store("claim_before_on", normal_claim())["status"] == "a_commissioning_unresolved"
    outputs[4] = "ON"  # The previously accepted asynchronous ON arrives later.
    assert observe(claimed, instance)["delivered_start"]
    assert off(claimed, instance, 2)["outcome"]["accepted_unambiguous"]
    outputs.clear()
    assert finish(claimed, instance)["created"] and not reserve_present(claimed, instance)
    assert len(calls) == 3


@pytest.mark.parametrize("kind", ["exception", "http_rejection", "forged_no_send_boolean"])
def test_ambiguous_or_caller_claimed_no_send_remains_outstanding(rail, monkeypatch, kind):
    from tests.test_rootline_a_commissioning_admission import Response
    def sender(request, timeout):
        if kind == "exception": raise OSError("synthetic network uncertainty")
        result = Response(); result.status = 503; return result
    instance, calls, body, value = prepare(sender=sender); claimed = claim(body)
    if kind == "forged_no_send_boolean":
        monkeypatch.setattr(instance, "set_a_commissioning_state", lambda **_: {
            "accepted_unambiguous": False, "provider_command_attempted": False,
            "known_no_send": True, "status": "provider_capacity_not_available"})
    edge(claimed, instance)
    current = state(value["operation_id"])
    assert current["startup_state"] == "outstanding" and current["known_no_send"] is None
    assert not finish(claimed, instance)["success"] and not edge(claimed, instance)["success"]
    if kind != "forged_no_send_boolean": assert reserve_present(claimed, instance) and len(calls) == 1


def test_no_send_acknowledgement_rollback_is_not_inferred_from_absence(rail, monkeypatch):
    instance, calls, body, value = prepare(); claimed = claim(body)
    monkeypatch.setattr(budget.RequestBudget, "begin_on", lambda **_: (_ for _ in ()).throw(
        budget.RequestBudgetUnavailable("synthetic pre-command refusal")))
    original_write = store._a_write
    def reject_no_send(connection, operation, phase, material):
        if phase == "A-NO-SEND": raise RuntimeError("synthetic no-send audit loss")
        return original_write(connection, operation, phase, material)
    monkeypatch.setattr(store, "_a_write", reject_no_send)
    assert not edge(claimed, instance)["success"] and not calls
    assert state(value["operation_id"])["startup_state"] == "outstanding"
    assert finish(claimed, instance)["status"] == "a_commissioning_startup_outstanding"


def test_never_sent_retirement_fences_a_late_local_on_sender(rail):
    instance, calls, body, value = prepare(); claimed = claim(body)
    reading, resume = Event(), Event()
    def held_read(**kwargs):
        reading.set(); assert resume.wait(5); return snapshot()
    instance.readback = held_read
    with ThreadPoolExecutor(max_workers=2) as pool:
        finishing = pool.submit(finish, claimed, instance)
        assert reading.wait(5)
        sending = pool.submit(edge, claimed, instance)
        time.sleep(0.1); assert not sending.done()
        resume.set()
        assert finishing.result(timeout=10)["retirement"]["safe_branch"] == "never_sent"
        assert not sending.result(timeout=10)["success"]
    assert state(value["operation_id"])["retired"] and not calls


def test_failed_reserve_release_is_explicit_and_keeps_claim_until_proven(rail, monkeypatch):
    instance, calls, body, value = prepare(); claimed = claim(body)
    original = budget.RequestBudget.release_after_off
    def failed(*args, **kwargs): raise budget.RequestBudgetUnavailable("synthetic accounting failure")
    monkeypatch.setattr(budget.RequestBudget, "release_after_off", failed)
    result = finish(claimed, instance)
    assert result["status"] == "a_commissioning_reserve_release_unresolved"
    assert result["provider_read_performed"] and not result["reserve_released"]
    assert state(value["operation_id"])["unresolved"] and state(value["operation_id"])["revoked"]
    assert reserve_present(claimed, instance) and not edge(claimed, instance)["success"]
    monkeypatch.setattr(budget.RequestBudget, "release_after_off", original)
    assert finish(claimed, instance)["created"] and not calls


def test_observer_rejects_caller_evidence_and_preserves_explicit_finite_duty(rail):
    instance, _, body, value = prepare(); claimed = claim(body)
    called = []
    def reader(**kwargs):
        called.append(budget.current_duty().get("read_deadline")); return snapshot()
    instance.readback = reader
    refused = store.rootline_irrigation_execution_store("observe_a_commissioning", {
        "operation_claim": claimed, "transport": instance, "observation": snapshot(states={4:"ON"})})
    assert not refused["success"] and not called
    deadline = (datetime.now(timezone.utc)+timedelta(seconds=5)).isoformat()
    with budget.execution_duty(claimed, deadline=deadline):
        assert observe(claimed, instance)["observation"]["state"] == "OFF"
        assert finish(claimed, instance)["created"]
    assert called == [datetime.fromisoformat(deadline), datetime.fromisoformat(deadline)]


def test_sibling_on_or_stale_snapshot_cannot_become_delivered_start(rail):
    outputs = {}; fixed_time = [None]
    instance, _, body, value = prepare(reader=lambda: snapshot(states=outputs, now=fixed_time[0]))
    claimed = claim(body); assert edge(claimed, instance)["outcome"]["accepted_unambiguous"]
    outputs.update({1: "ON", 4: "ON"})
    assert observe(claimed, instance)["delivered_start"] is None
    outputs.pop(1); fixed_time[0] = datetime.now(timezone.utc)-timedelta(seconds=40)
    assert observe(claimed, instance)["delivered_start"] is None
    assert state(value["operation_id"])["startup_state"] == "outstanding"
    fixed_time[0] = None
    assert observe(claimed, instance)["delivered_start"]
    outputs.clear(); assert finish(claimed, instance)["created"]
