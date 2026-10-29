"""Actual canonical no-ON reconciliation, reservation and concurrency contracts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from copy import deepcopy
import uuid

import pytest
from tests.test_rootline_managed_startup_handover_postgres import db, seed, rows, store, pytestmark


def new_claim():
    now = datetime.now(timezone.utc)
    return {"execution_id": "RECONCILE-" + uuid.uuid4().hex,
        "consumption_key": "CONSUME-" + uuid.uuid4().hex,
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2", "device_id": "100204d497",
        "channel": 2, "device_type": "fertilizer_mixer", "maximum_duration_seconds": 600,
        "claimed_at": now.isoformat(), "primary_stop_deadline": (now+timedelta(seconds=600)).isoformat(),
        "state": "claimed", "on_attempts": 0, "off_attempts": 0}


def contained(db):
    claim = new_claim()
    assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on", claim)["created"]
    proof = {"device_id": claim["device_id"], "channel": 2, "state": "OFF", "authoritative": True,
        "evidence_id": "a"*64, "retrieved_at": datetime.now(timezone.utc).isoformat()}
    hold = {**claim, "reason": "restart_or_deadline_ambiguous", "shutdown_verified": True,
            "shutdown_evidence": proof}
    assert store.rootline_irrigation_execution_store("contain_auxiliary_device", hold)["created"]
    events = rows(db, claim)
    original = next(r for r in events if r["action"] == "claim_auxiliary_before_on")
    held = next(r for r in events if r["action"] == "contain_auxiliary_device")
    body = {"execution_id": claim["execution_id"], "auxiliary_device_id": claim["auxiliary_device_id"],
        "claim_event_id": original["event_id"], "claim_sha256": store._event_digest(original),
        "containment_event_id": held["event_id"], "containment_sha256": store._event_digest(held),
        "shutdown_evidence": {**proof, "retrieved_at": datetime.now(timezone.utc).isoformat()},
        "owner_instruction": {"source": "owner_codex_chat", "reference": "synthetic-owner-record",
            "artifact_sha256": "b"*64}, "root_review_sha256": "c"*64}
    return claim, held, body


def reconcile(body):
    return store.rootline_irrigation_execution_store("reconcile_unstarted_auxiliary", body)


def state():
    return store.rootline_irrigation_execution_store("load_auxiliary_containment", "FERTILIZER-MIXER-CH2")


def test_exact_release_preserves_retirement_history_and_budget(db):
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    claim, held, body = contained(db)
    original = rows(db, claim)
    assert state()["contained"]
    assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on", new_claim())["status"] == "auxiliary_contained"
    assert reconcile(body)["created"]
    assert not state()["contained"]
    assert rows(db, claim)[:-1] == original
    assert store.rootline_irrigation_execution_store("load_active_auxiliary", None) is None
    calls = []
    assert not store.rootline_irrigation_execution_store("dispatch_auxiliary_on_edge",
        {**claim, "dispatch": lambda: calls.append("ON")})["accepted_unambiguous"]
    assert not store.rootline_irrigation_execution_store("mark_auxiliary_active",
        {**claim, "state": "Active", "on_attempts": 1})["success"]
    assert calls == []
    account = mixing_daily_accounting(rows(db, claim), now=datetime.now(timezone.utc))
    assert account["reserved_seconds"] == 600 and account["sessions"] == 1
    assert account["controller_completed_seconds"] == 0 and not account["premix_verified"]
    assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on", new_claim())["created"]


def test_exact_replay_and_changed_proof_conflict(db):
    claim, held, body = contained(db)
    assert reconcile(body)["created"]
    assert reconcile(body) == {"success": True, "created": False, "status": "already_reconciled"}
    changed = deepcopy(body); changed["shutdown_evidence"]["evidence_id"] = "d"*64
    assert reconcile(changed)["status"] == "reconciliation_conflict"
    assert sum(r["action"] == "reconcile_unstarted_auxiliary" for r in rows(db, claim)) == 1


@pytest.mark.parametrize("action", ["claim_auxiliary_dispatch", "record_auxiliary_on_outcome",
    "mark_auxiliary_active", "record_auxiliary_completed", "record_auxiliary_control_pulse_stopped"])
def test_any_dispatch_outcome_active_or_completion_refuses_even_if_off(db, action):
    claim, held, body = contained(db)
    seed(db, action, {**claim, "state": "Active"})
    assert not reconcile(body)["success"] and state()["contained"]


@pytest.mark.parametrize("field,value", [("state", "ON"), ("authoritative", False),
    ("device_id", "other"), ("channel", 1), ("channel", True), ("evidence_id", ""),
    ("retrieved_at", "bad"), ("retrieved_at", "2026-01-01T00:00:00+00:00"),
    ("retrieved_at", "2099-01-01T00:00:00+00:00")])
def test_invalid_current_off_refuses(db, field, value):
    claim, held, body = contained(db)
    body["shutdown_evidence"][field] = value
    assert reconcile(body)["status"] == "current_exact_off_unproven" and state()["contained"]


def test_off_predating_containment_refuses(db):
    claim, held, body = contained(db)
    body["shutdown_evidence"]["retrieved_at"] = (datetime.fromisoformat(
        held["shutdown_evidence"]["retrieved_at"])-timedelta(seconds=1)).isoformat()
    assert reconcile(body)["status"] == "current_exact_off_unproven"


@pytest.mark.parametrize("field,value", [("claim_sha256", "d"*64), ("containment_sha256", "d"*64),
    ("claim_event_id", "other"), ("containment_event_id", "other"),
    ("auxiliary_device_id", "FERTILIZER-INJECTION-CH1"),
    ("owner_instruction", {"source": "telegram", "reference": "not-an-owner-record", "artifact_sha256": "b"*64})])
def test_exact_identity_and_authority_refusal(db, field, value):
    claim, held, body = contained(db); body[field] = value
    assert not reconcile(body)["success"] and state()["contained"]


def test_newer_containment_invalidates_old_cas_and_release_does_not_clear_older_hold(db):
    claim, held, body = contained(db)
    seed(db, "contain_auxiliary_device", {**claim, "reason": "newer_unsafe",
        "shutdown_verified": False})
    assert not reconcile(body)["success"] and state()["contained"]


def test_new_hold_after_release_blocks_and_late_on_evidence_cannot_be_masked(db):
    claim, held, body = contained(db)
    assert reconcile(body)["created"]
    seed(db, "record_auxiliary_on_outcome", {**claim, "on_outcome": {"accepted_unambiguous": False}})
    assert state()["contained"]
    assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on", new_claim())["status"] == "auxiliary_contained"


def test_different_older_containment_is_not_superseded(db):
    claim, held, body = contained(db)
    other = new_claim()
    seed(db, "contain_auxiliary_device", {**other, "reason": "unsafe-other", "shutdown_verified": True})
    assert not reconcile(body)["success"] and state()["contained"]


def test_other_open_auxiliary_prevents_release(db):
    claim, held, body = contained(db)
    other = new_claim()
    seed(db, "claim_auxiliary_before_on", other)
    assert reconcile(body)["status"] == "auxiliary_owner_still_active"


def test_reconciliation_rollback_has_no_release_effect(db, monkeypatch):
    claim, held, body = contained(db); original = store._insert_managed_event
    def fail(cursor, action, record):
        result = original(cursor, action, record)
        if action == "reconcile_unstarted_auxiliary": raise RuntimeError("synthetic rollback")
        return result
    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_insert_managed_event", fail)
        with pytest.raises(RuntimeError, match="synthetic rollback"): reconcile(body)
    assert state()["contained"]
    assert not any(r["action"] == "reconcile_unstarted_auxiliary" for r in rows(db, claim))


def test_concurrent_reconciliation_has_one_event(db):
    claim, held, body = contained(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reconcile(body), range(2)))
    assert sum(r["created"] for r in results) == 1 and all(r["success"] for r in results)


def test_new_claim_waits_for_reconciliation_commit(db, monkeypatch):
    claim, held, body = contained(db)
    entered = Event(); release = Event(); started = Event(); original = store._insert_managed_event
    def pause(cursor, action, record):
        result = original(cursor, action, record)
        if action == "reconcile_unstarted_auxiliary":
            entered.set(); assert release.wait(2)
        return result
    def claim_next():
        started.set()
        return store.rootline_irrigation_execution_store("claim_auxiliary_before_on", new_claim())
    with monkeypatch.context() as scoped:
        scoped.setattr(store, "_insert_managed_event", pause)
        with ThreadPoolExecutor(max_workers=2) as pool:
            resolution = pool.submit(reconcile, body); assert entered.wait(2)
            following = pool.submit(claim_next); assert started.wait(2); assert not following.done()
            release.set()
            assert resolution.result(2)["created"] and following.result(2)["created"]


def test_reconciling_latest_exact_hold_does_not_release_other_holds(db):
    claim, held, body = contained(db)
    other = new_claim()
    seed(db, "contain_auxiliary_device", {**other, "reason": "unrelated-fault", "shutdown_verified": True})
    latest = {**claim, "reason": "restart_or_deadline_ambiguous", "shutdown_verified": True,
        "shutdown_evidence": body["shutdown_evidence"], "confirmation": "later exact shutdown"}
    seed(db, "contain_auxiliary_device", latest)
    latest = next(r for r in reversed(rows(db, claim)) if r["action"] == "contain_auxiliary_device")
    body.update(containment_event_id=latest["event_id"], containment_sha256=store._event_digest(latest))
    assert reconcile(body)["created"]
    assert state()["contained"]
    assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on", new_claim())["status"] == "auxiliary_contained"
