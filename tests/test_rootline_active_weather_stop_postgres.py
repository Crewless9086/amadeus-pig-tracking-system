"""Actual PostgreSQL stop barriers, atomic partial history, replay and original-slot recovery."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import threading
import uuid

import pytest

from tests.test_rootline_parent_job_resolution_postgres import database
from tests.test_rootline_active_weather_stop import NOW, subject, Transport, weather_packet
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry.rootline_irrigation_job_contract import project_next_segment, weather_stop_digest
from modules.telemetry.rootline_irrigation_history import _attach_parent_jobs, project_canonical_irrigation_history

store = importlib.import_module("modules.telemetry.rootline_irrigation_execution_store")


def seed_active(database, active, *, claimed=False):
    authority = {**active, "action": "record_eligibility", "eligibility_id": "ELIG-" + active["execution_id"],
        "eligibility_sha256": "a" * 64, "predecessor_off_rearm_verified": active["segment_number"] > 1}
    claim = {**active, "action": "claim_before_on", "state": "claimed", "on_attempts": 0,
        "eligibility_id": authority["eligibility_id"], "eligibility_sha256": "a" * 64,
        "consumption_key": "CONSUMPTION-" + active["execution_id"]}
    database.seed([authority])
    if claimed:
        result = store.rootline_irrigation_execution_store("claim_before_on", claim)
        assert result["created"] is True, result
    else:
        database.seed([claim])
    database.seed([{**active, "action": "record_on_outcome", "on_outcome": {"accepted_unambiguous": True}},
        {**active, "action": "mark_active"}], at=datetime.now(timezone.utc))
    return claim


def run_stop(*, now=NOW, rain=True):
    notices = []
    transport = Transport(clock=lambda: now)
    result = coordinator.advance_irrigation_execution(decision_id="", commissioning_id="",
        decision_reader=lambda _: {}, commissioning_reader=lambda _: {},
        store=store.rootline_irrigation_execution_store, transport=transport,
        notify=lambda *args: notices.append(args) or {"provider_delivery_confirmed": True},
        now=now, clock=lambda: now, active_only=True,
        active_weather_revalidator=lambda _: runtime.assess_active_irrigation_weather(
            weather_packet(now=now, rain=1 if rain else 0), now=now))
    return result, transport, notices


def events(database):
    return [row[2]["rootline_execution"] for row in database.read()[0]]


def prepare_barrier(active, *, weather=True):
    row = {**active, "state": "stopping", "reason": "primary_deadline_reached"}
    if weather:
        evidence = runtime.assess_active_irrigation_weather(weather_packet(rain=1), now=NOW)
        row.update(reason=evidence["reason"], weather_stop_evidence=evidence, stop_requested_at=NOW.isoformat())
    return row


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_real_partial_is_atomic_replayable_and_releases_only_that_execution(database, zone):
    job, active = subject(zone=zone)
    seed_active(database, active)
    result, transport, notices = run_stop()
    assert result["status"] == "segment_stopped_for_weather", result
    assert len(transport.calls) == 1 and notices[0][0] == "Stopped"
    assert store.rootline_irrigation_execution_store("load_active", None) is None
    saved = events(database)
    completed = [row for row in saved if row["action"] == "record_completed"]
    assert len(completed) == 1 and completed[0]["state"] == "Stopped"
    typed = database.read()[1]
    assert len(typed) == 1
    import psycopg
    with psycopg.connect(database.url) as connection:
        row = connection.execute("select event_type,actual_minutes,details from public.irrigation_events").fetchone()
    assert row[0] == "PARTIAL" and row[1] is None
    assert row[2]["objective_satisfied"] is False and row[2]["partial_observation"]["physical_delivery"] == "Unknown"
    before = database.read()
    replay = store.rootline_irrigation_execution_store("record_completed", completed[0])
    assert replay["success"] is True and replay["created"] is False
    assert database.read() == before
    projection = project_next_segment(job, store.rootline_irrigation_execution_store("load_job_events", job["job_id"]), rearm_readback_off=True)
    assert projection["current_segment"] == 2 and projection["cumulative_verified_runtime_seconds"] == 0


@pytest.mark.parametrize("rail", ["history", "review"])
def test_failed_terminal_rail_rolls_back_both_and_preserves_sticky_obligation(database, monkeypatch, rail):
    _, active = subject()
    seed_active(database, active)
    if rail == "history":
        monkeypatch.setattr(store, "_append_history", lambda *a, **kw: False)
    else:
        real = store._write_terminal_review
        def failed(connection, action, body):
            if action == "record_completed": raise store._AtomicTerminalWriteFailed("synthetic_terminal_write_failure")
            return real(connection, action, body)
        monkeypatch.setattr(store, "_write_terminal_review", failed)
    result, _, _ = run_stop()
    assert result["status"] == "completion_persistence_unproven"
    assert not database.read()[1]
    assert not any(row["action"] == "record_completed" for row in events(database))
    active_after = store.rootline_irrigation_execution_store("load_active", None)
    assert active_after["state"] == "stopping" and active_after["weather_stop_evidence"]["stop_required"] is True


@pytest.mark.parametrize("weather_first", [True, False])
def test_real_concurrent_stop_barrier_preserves_exact_first_cause(database, monkeypatch, weather_first):
    _, active = subject()
    seed_active(database, active)
    first = prepare_barrier(active, weather=weather_first)
    second = prepare_barrier(active, weather=not weather_first)
    entered = threading.Event(); release = threading.Event()
    real = store._write_terminal_review
    def paused(connection, action, body):
        if action == "mark_stopping" and not entered.is_set():
            entered.set()
            assert release.wait(2)
        return real(connection, action, body)
    monkeypatch.setattr(store, "_write_terminal_review", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(store.rootline_irrigation_execution_store, "mark_stopping", first)
        assert entered.wait(2)
        b = pool.submit(store.rootline_irrigation_execution_store, "mark_stopping", second)
        try: database.wait_for_blocked()
        finally: release.set()
        result_a, result_b = a.result(), b.result()
    assert result_a["success"] is result_b["success"] is True
    assert result_a["execution"] == result_b["execution"]
    assert result_a["execution"]["reason"] == first["reason"]
    assert sum(row["action"] == "mark_stopping" for row in events(database)) == 1
    later = datetime.fromisoformat(active["primary_stop_deadline"]) + timedelta(seconds=1)
    outcome, _, _ = run_stop(now=later)
    assert outcome["status"] == ("segment_stopped_for_weather" if weather_first else "segment_completed")
    assert outcome["execution"]["verified_runtime_seconds"] == (0 if weather_first else 3599)


def test_changed_active_preimage_refuses_stop_before_any_off(database):
    _, active = subject()
    seed_active(database, active)
    changed = prepare_barrier(active)
    changed["primary_stop_deadline"] = NOW.isoformat()
    result = store.rootline_irrigation_execution_store("mark_stopping", changed)
    assert result["success"] is False and result["status"] == "canonical_active_parent_changed"
    assert not any(row["action"] == "mark_stopping" for row in events(database))


def test_partial_replay_conflicts_and_competing_full_completion_cannot_create_credit(database):
    _, active = subject()
    seed_active(database, active)
    result, _, _ = run_stop()
    before = database.read()
    changed = deepcopy(result["execution"])
    changed["remaining_seconds"] -= 1
    changed["terminal_sha256"] = weather_stop_digest(changed)
    rejected = store.rootline_irrigation_execution_store("record_completed", changed)
    assert rejected["success"] is False
    full = {**active, "state": "Completed", "shutdown_verified": True,
        "objective_satisfied": True, "verified_runtime_seconds": 3599,
        "completed_at": NOW.isoformat(), "shutdown_evidence": result["execution"]["shutdown_evidence"]}
    with pytest.raises(ValueError, match="completion_history_conflict"):
        store.rootline_irrigation_execution_store("record_completed", full)
    assert database.read() == before


def test_pending_weather_barrier_refuses_stale_full_callback_before_terminal_commit(database):
    _, active = subject()
    seed_active(database, active)
    barrier = store.rootline_irrigation_execution_store("mark_stopping", prepare_barrier(active))
    assert barrier["success"] is True
    with pytest.raises(ValueError, match="weather_stop_cannot_complete"):
        store.rootline_irrigation_execution_store("record_completed", {**active, "state": "Completed"})
    assert not database.read()[1]
    assert store.rootline_irrigation_execution_store("load_active", None)["state"] == "stopping"


@pytest.mark.parametrize("first_stopped", [True, False])
def test_remaining_original_slot_and_exhausted_deferment_reopen_next_normal_date(database, first_stopped):
    first_time = NOW - timedelta(hours=2)
    job, first = subject(now=first_time)
    seed_active(database, first)
    if first_stopped:
        first_result, _, _ = run_stop(now=first_time)
        assert first_result["status"] == "segment_stopped_for_weather"
    else:
        due = datetime.fromisoformat(first["primary_stop_deadline"]) + timedelta(seconds=1)
        first_result, _, _ = run_stop(now=due)
        assert first_result["status"] == "segment_completed"
    _, second = subject(job=job, segment=2, prior=0 if first_stopped else 3599)
    seed_active(database, second, claimed=True)
    if first_stopped:
        due = datetime.fromisoformat(second["primary_stop_deadline"]) + timedelta(seconds=1)
        second_result, _, _ = run_stop(now=due)
        assert second_result["status"] == "segment_completed"
    else:
        second_result, _, _ = run_stop()
        assert second_result["status"] == "segment_stopped_for_weather"
    all_events = events(database)
    resolutions = [row for row in all_events if row["action"] == "record_job_resolution"]
    assert len(resolutions) == 1 and resolutions[0]["resolution"] == "Deferred"
    assert resolutions[0]["remaining_seconds"] == 3599
    assert resolutions[0]["cumulative_verified_runtime_seconds"] == 3599
    assert store.rootline_irrigation_execution_store("load_active", None) is None
    assert store.rootline_irrigation_execution_store("load_zone_containment", first["zone_id"])["contained"] is False
    current = project_canonical_irrigation_history([], snapshot_cutoff=NOW + timedelta(hours=2))
    _attach_parent_jobs(current, all_events, canonical_ordered=True)
    zone = current["zones"][first["zone_id"]]
    assert zone["incomplete_parent_job"]["projection"]["status"] == "job_deferred"
    assert not zone["verified_completed_days"]
    future = project_canonical_irrigation_history([], snapshot_cutoff=NOW + timedelta(days=1))
    _attach_parent_jobs(future, all_events, canonical_ordered=True)
    next_zone = future["zones"][first["zone_id"]]
    assert next_zone.get("deferred_parent_jobs") and not next_zone.get("incomplete_parent_job")
    assert not next_zone.get("stale_incomplete_parent_jobs") and not next_zone.get("contained_parent_jobs")
    forged = {**second, "execution_id": "EXTRA-" + uuid.uuid4().hex, "segment_number": 3,
        "eligibility_id": "EXTRA-ELIG", "eligibility_sha256": "a" * 64, "consumption_key": "EXTRA-CONSUMPTION"}
    blocked = store.rootline_irrigation_execution_store("claim_before_on", forged)
    assert blocked["created"] is False and blocked["status"] == "parent_job_deferred"
    # A fresh same-day parent is still barred by the original accepted ON.
    _, fresh = subject()
    authority = {**fresh, "action": "record_eligibility", "eligibility_id": "NEW-ELIG",
        "eligibility_sha256": "a" * 64, "consumption_key": "NEW-CONSUMPTION"}
    database.seed([authority])
    refused = store.rootline_irrigation_execution_store("claim_before_on", authority)
    assert refused["created"] is False and refused["status"] == "zone_daily_on_already_accepted"
    # The normal next-date opportunity needs no manual clear of the old parent.
    _, tomorrow = subject(now=NOW + timedelta(days=1))
    authority = {**tomorrow, "action": "record_eligibility", "eligibility_id": "TOMORROW-ELIG",
        "eligibility_sha256": "a" * 64, "consumption_key": "TOMORROW-CONSUMPTION"}
    database.seed([authority])
    admitted = store.rootline_irrigation_execution_store("claim_before_on", authority)
    assert admitted["created"] is True


def test_exhausted_parent_resolution_failure_rolls_back_partial_and_review_together(database, monkeypatch):
    first_time = NOW - timedelta(hours=2)
    job, first = subject(now=first_time)
    seed_active(database, first)
    due = datetime.fromisoformat(first["primary_stop_deadline"]) + timedelta(seconds=1)
    assert run_stop(now=due)[0]["status"] == "segment_completed"
    _, second = subject(job=job, segment=2, prior=3599)
    seed_active(database, second, claimed=True)
    before_history = database.read()[1]
    real = store._write_terminal_review
    def failed(connection, action, body):
        if action == "record_job_resolution": raise store._AtomicTerminalWriteFailed("synthetic_resolution_failure")
        return real(connection, action, body)
    monkeypatch.setattr(store, "_write_terminal_review", failed)
    result, _, _ = run_stop()
    assert result["status"] == "completion_persistence_unproven"
    assert database.read()[1] == before_history
    assert not any(row["action"] == "record_completed" and row["execution_id"] == second["execution_id"] for row in events(database))
    assert store.rootline_irrigation_execution_store("load_active", None)["state"] == "stopping"


@pytest.mark.parametrize("crash_after_barrier", [False, True])
def test_actual_interrupted_claim_preserves_deadlines_and_never_reissues_on(database, monkeypatch, crash_after_barrier):
    _, active = subject()
    claim = {**active, "state": "claimed", "on_attempts": 0, "action": "claim_before_on"}
    claim.pop("start_evidence")
    database.seed([claim])
    original = store.rootline_irrigation_execution_store
    if crash_after_barrier:
        def failed(action, body):
            if action == "contain_zone": raise RuntimeError("synthetic process loss after barrier")
            return original(action, body)
        monkeypatch.setattr(store, "rootline_irrigation_execution_store", failed)
        with pytest.raises(RuntimeError, match="process loss"):
            run_stop()
        monkeypatch.setattr(store, "rootline_irrigation_execution_store", original)
        pending = original("load_active", None)
        assert pending["state"] == "stopping" and pending["reason"] == "restart_after_pre_on_claim"
    result, transport, _ = run_stop()
    assert result["status"] == "interrupted_start_contained"
    assert [(row["channel"], row["state"]) for row in transport.calls] == [(claim["channel"], "OFF")]
    assert original("load_active", None) is None
    rows = events(database)
    assert sum(row["action"] == "claim_before_on" for row in rows) == 1
    barrier = next(row for row in rows if row["action"] == "mark_stopping")
    for key in ("execution_id", "claimed_at", "primary_stop_deadline", "native_fail_stop_deadline", "on_attempts"):
        assert barrier[key] == claim[key]
    assert not any(row["action"] in {"record_on_outcome", "record_completed"} for row in rows)


def test_partial_replay_accepts_stored_timezone_but_rejects_changed_instant(database):
    import psycopg
    _, active = subject()
    seed_active(database, active)
    result, _, _ = run_stop()
    saved = next(row for row in events(database) if row["action"] == "record_completed")
    with psycopg.connect(database.url) as connection:
        connection.execute("set time zone 'Africa/Johannesburg'")
        stored_at = connection.execute("select event_at from public.irrigation_events").fetchone()[0]
    assert stored_at == datetime.fromisoformat(saved["completed_at"])
    assert stored_at.isoformat() != saved["completed_at"]
    before = database.read()
    assert store.rootline_irrigation_execution_store("record_completed", saved)["success"] is True
    changed = deepcopy(saved)
    changed["completed_at"] = (datetime.fromisoformat(saved["completed_at"]) + timedelta(seconds=1)).isoformat()
    changed["terminal_sha256"] = weather_stop_digest(changed)
    assert store.rootline_irrigation_execution_store("record_completed", changed)["success"] is False
    assert database.read() == before


def test_lost_terminal_acknowledgement_leaves_one_atomic_outcome_and_no_off_replay(database, monkeypatch):
    _, active = subject()
    seed_active(database, active)
    real = store._record_parent_terminal_atomic
    def lost(action, body):
        real(action, body)
        raise RuntimeError("synthetic acknowledgement lost after commit")
    monkeypatch.setattr(store, "_record_parent_terminal_atomic", lost)
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        run_stop()
    assert len(database.read()[1]) == 1
    assert sum(row["action"] == "record_completed" for row in events(database)) == 1
    monkeypatch.setattr(store, "_record_parent_terminal_atomic", real)
    result, transport, _ = run_stop()
    assert result["status"] == "no_active_irrigation" and not transport.calls
    assert len(database.read()[1]) == 1


def test_two_real_workers_with_distinct_off_reads_converge_without_intervention(database):
    _, active = subject()
    seed_active(database, active)
    first_committed = threading.Event(); second_entered = threading.Event()
    read_barrier = threading.Barrier(2)
    notices = []; writes = []
    real_store = store.rootline_irrigation_execution_store
    def fenced_store(action, body):
        result = real_store(action, body)
        if action == "mark_stopping":
            if result.get("created") is True:
                first_committed.set()
                assert second_entered.wait(2)
            else:
                second_entered.set()
        if action == "record_completed": writes.append(result)
        return result
    class RacedTransport(Transport):
        def read_output_state(self, **kwargs):
            read_barrier.wait(timeout=2)
            result = super().read_output_state(**kwargs)
            return {**result, "evidence_id": "synthetic-off-" + self.clock().isoformat()}
    def worker(index):
        now = NOW + timedelta(seconds=index)
        transport = RacedTransport(clock=lambda: now)
        result = coordinator.advance_irrigation_execution(decision_id="", commissioning_id="",
            decision_reader=lambda _: {}, commissioning_reader=lambda _: {},
            store=fenced_store, transport=transport,
            notify=lambda *args: notices.append(args) or {"provider_delivery_confirmed": True},
            now=now, clock=lambda: now, active_only=True,
            active_weather_revalidator=lambda _: runtime.assess_active_irrigation_weather(
                weather_packet(now=now, rain=1), now=now))
        return result, transport.calls
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker, 0)
        assert first_committed.wait(2)
        second = pool.submit(worker, 1)
        results = [first.result(timeout=5), second.result(timeout=5)]
    assert all(result[0]["status"] == "segment_stopped_for_weather" for result in results), results
    assert [state for state, _ in notices] == ["Stopped"]
    assert sum(value.get("created") is True for value in writes) == 1
    rejected = [value for value in writes if value.get("success") is False]
    assert len(rejected) == 1 and rejected[0]["status"] == "canonical_weather_stop_already_committed"
    canonical = next(row for row in events(database) if row["action"] == "record_completed")
    assert all(result[0]["execution"] == canonical for result in results if result[0]["execution"].get("action") == "record_completed")
    assert len(database.read()[1]) == 1 and canonical["verified_runtime_seconds"] == 0
    assert sum(row["action"] == "record_completed" for row in events(database)) == 1
    assert all(call["state"] == "OFF" for _, calls in results for call in calls)
    assert len([call for _, calls in results for call in calls]) <= 3
