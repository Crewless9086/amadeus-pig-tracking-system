"""Shared OFF duty races on the explicitly selected synthetic database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import json

import pytest

from tests.test_rootline_command_mode_postgres import schema, db, seed, connect, store_module
from tests.test_rootline_command_mode import receipt
from modules.telemetry.rootline_command_acceptance import MODE, digest

pytestmark = pytest.mark.skipif(not os.getenv("ROOTLINE_HA_COMMAND_TEST_URL"), reason="synthetic database required")


def execution():
    at = datetime.now(timezone.utc)-timedelta(hours=1)
    return {"execution_id": "shutdown57-synthetic", "device_id": "100204e9bc", "channel": 1,
        "zone_id": "A12345", "claimed_at": at.isoformat(), "acceptance_mode": MODE,
        "primary_stop_deadline": (at+timedelta(minutes=60)).isoformat(),
        "planned_runtime_seconds": 3600, "state": "stopping"}


def actual_receipt(value, attempt):
    at = datetime.now(timezone.utc)
    result = receipt(value, "OFF", at=at, attempt=attempt)
    result["controller_acceptance"] = {"version": "rootline_controller_command.v1", "accepted": True,
        "status": "controller_accepted", "availability": "online", "device_id": value["device_id"],
        "channel": value["channel"], "state": "OFF", "attempt_id": result["idempotency_key"],
        "issued_at": result["command_attempted_at"], "expires_at": (at+timedelta(seconds=30)).isoformat(),
        "responded_at": result["accepted_at"], "response_digest": "a"*64}
    result["receipt_sha256"] = digest({key: val for key, val in result.items() if key != "receipt_sha256"})
    return result


def test_two_senders_send_one_off_and_reuse_actual_receipt(db):
    value = execution()
    seed([{**value, "action": "claim_before_on"}])
    calls = []
    def send(attempt):
        calls.append(attempt)
        return actual_receipt(value, attempt)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: db("dispatch_controller_off", {"execution": value, "dispatch": send}), range(2)))
    assert len(calls) == 1, results
    assert any(row.get("accepted_unambiguous") is True for row in results)
    assert db("dispatch_controller_off", {"execution": value, "dispatch": send}).get("reused_outcome")
    assert len(calls) == 1


def test_initial_three_then_persistent_five_minute_retry(db):
    value = execution()
    seed([{**value, "action": "claim_before_on"}])
    calls = []
    def fail(attempt):
        calls.append(attempt)
        return {"accepted_unambiguous": False, "provider_command_attempted": True}
    body = {"execution": value, "dispatch": fail}
    for _ in range(4): db("dispatch_controller_off", body)
    assert calls == [1, 2, 3]
    with connect() as connection:
        connection.execute("truncate public.sam_live_stock_conversation_review_events")
    seed([{**value, "action": "claim_before_on"}])
    with connect() as connection:
        for attempt in (1, 2, 3):
            for action in ("claim_off_attempt", "record_off_outcome"):
                row = {"execution_id": value["execution_id"], "attempt": attempt}
                if action == "record_off_outcome":
                    row["outcome"] = {"accepted_unambiguous": False, "provider_command_attempted": True}
                event_id = store_module._event_id(action, row)
                stored = store_module._stored_event_body(action, row, event_id)
                connection.execute("""insert into public.sam_live_stock_conversation_review_events
                    (review_event_id, chatwoot_conversation_id, source_agent, event_source, recommended_action, review_json, created_at)
                    values (%s,%s,'rootline_backend',%s,%s,%s::jsonb,clock_timestamp()-interval '301 seconds')""",
                    (event_id, value["execution_id"], store_module.EVENT_SOURCE, action, json.dumps({"rootline_execution": stored})))
    db("dispatch_controller_off", body)
    db("dispatch_controller_off", body)
    assert calls == [1, 2, 3, 4]


def test_legacy_queue_receipt_does_not_close_retry_duty(db):
    value = execution()
    seed([{**value, "action": "claim_before_on"},
        {"execution_id": value["execution_id"], "action": "claim_off_attempt", "attempt": 1},
        {"execution_id": value["execution_id"], "action": "record_off_outcome", "attempt": 1,
            "outcome": receipt(value, "OFF", at=datetime.now(timezone.utc), attempt=1, controller=False)}])
    calls = []
    def send(attempt):
        calls.append(attempt)
        return actual_receipt(value, attempt)
    result = db("dispatch_controller_off", {"execution": value, "dispatch": send})
    assert calls == [2] and result["accepted_unambiguous"]


def test_newer_output_ownership_fences_old_duty(db):
    value = execution()
    seed([{**value, "action": "claim_before_on"},
        {**value, "execution_id": "newer-owner", "claimed_at": datetime.now(timezone.utc).isoformat(), "action": "claim_before_on"}])
    calls = []
    result = db("dispatch_controller_off", {"execution": value, "dispatch": lambda n: calls.append(n)})
    assert not calls and result["status"] == "shutdown_ownership_retired"


def test_delayed_claim_cannot_send_after_newer_retry_consumed(db, monkeypatch):
    from contextlib import contextmanager
    from threading import Event, current_thread
    from modules.oom_sakkie import bounded_postgres_read as postgres
    value = execution()
    seed([{**value, "action": "claim_before_on"}])
    calls = []
    def fail(attempt):
        calls.append(attempt)
        return {"accepted_unambiguous": False, "provider_command_attempted": True}
    body = {"execution": value, "dispatch": fail}
    for _ in range(3): db("dispatch_controller_off", body)
    original = postgres.connect_bounded_rootline_postgres
    paused, resume = Event(), Event()
    counts = {}
    offset = [301]
    class Cursor:
        def __init__(self, real): self.real = real; self.clock_query = False
        def execute(self, sql, *args):
            self.clock_query = sql.strip() == "select clock_timestamp()"
            self.real.execute(sql, *args)
            return self
        def fetchone(self):
            result = self.real.fetchone()
            return (result[0]+timedelta(seconds=offset[0]),) if self.clock_query else result
        def __getattr__(self, key): return getattr(self.real, key)
    class Connection:
        def __init__(self, real): self.real = real
        @contextmanager
        def cursor(self):
            with self.real.cursor() as cursor: yield Cursor(cursor)
    @contextmanager
    def guarded(**kwargs):
        name = current_thread().name
        counts[name] = counts.get(name, 0)+1
        if name.startswith("delayed-off") and counts[name] == 2:
            paused.set()
            assert resume.wait(10)
        with original(**kwargs) as connection: yield Connection(connection)
    monkeypatch.setattr(postgres, "connect_bounded_rootline_postgres", guarded)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="delayed-off") as pool:
        delayed = pool.submit(db, "dispatch_controller_off", body)
        assert paused.wait(10)
        offset[0] = 602
        try:
            db("dispatch_controller_off", body)
        finally:
            resume.set()
        result = delayed.result(timeout=10)
    assert calls == [1, 2, 3, 5]
    assert result["status"] == "shutdown_attempt_superseded"


@pytest.mark.parametrize("attempted", [False, True, None])
def test_only_proven_adapter_pre_send_failure_retires_without_off_state_gate(db, attempted):
    value = {**execution(), "provider_capacity_permit": "home_assistant:synthetic"}
    now = datetime.now(timezone.utc)
    proof = {"version": "rootline_controller_command.v1", "accepted": False,
        "controller_command_attempted": attempted, "status": "controller_not_sent",
        "state": "ON", "device_id": value["device_id"], "channel": value["channel"],
        "attempt_id": value["execution_id"]+":ON", "issued_at": now.isoformat(),
        "consumed_at": now.isoformat(), "expires_at": (now+timedelta(seconds=30)).isoformat()}
    seed([{**value, "action": "claim_before_on"}, {**value, "action": "record_on_outcome",
        "on_outcome": {"accepted_unambiguous": False, "provider_command_attempted": False,
            "status": "controller_not_sent", "controller_response": proof}}])
    result = db("retire_controller_not_sent", value)
    assert result["success"] is (attempted is False)
    if result["success"]:
        assert result["execution"]["shutdown_verified"] is False
        assert result["execution"]["not_dispatched_verified"] is True
        assert db("load_active", None) is None


def test_proven_no_send_can_rearm_new_execution_without_replaying_old_attempt(db):
    from tests.test_rootline_command_mode import start, ENV
    from modules.telemetry.rootline_timed_control import timed_control_scope
    _, _, memory, _, _ = start(at=datetime.now(timezone.utc))
    claim = next(row for row in memory.rows if row["action"] == "claim_before_on")
    claim["provider_capacity_permit"] = "home_assistant:synthetic"
    now = datetime.now(timezone.utc)
    proof = {"version": "rootline_controller_command.v1", "accepted": False,
        "controller_command_attempted": False, "status": "controller_not_sent", "state": "ON",
        "device_id": claim["device_id"], "channel": claim["channel"], "attempt_id": claim["execution_id"]+":ON",
        "issued_at": now.isoformat(), "consumed_at": now.isoformat(), "expires_at": (now+timedelta(seconds=30)).isoformat()}
    seed([claim, {**claim, "action": "record_on_outcome", "on_outcome": {
        "accepted_unambiguous": False, "provider_command_attempted": False,
        "status": "controller_not_sent", "controller_response": proof}}])
    assert db("retire_controller_not_sent", claim)["success"]
    _, artifact, next_memory, _, _ = start(at=datetime.now(timezone.utc))
    next_claim = next(row for row in next_memory.rows if row["action"] == "claim_before_on")
    assert next_claim["execution_id"] != claim["execution_id"]
    with timed_control_scope(ENV):
        assert db("record_eligibility", artifact)["success"]
        assert db("claim_before_on", next_claim)["created"]
    assert db("load_active", None)["execution_id"] == next_claim["execution_id"]


def test_reconnect_closes_owned_off_before_resuming_eligible_camp_and_next_tick_is_idempotent(db):
    from copy import deepcopy
    from tests.test_rootline_command_mode import start, recover, Transport, ENV, route, inputs
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_irrigation_coordinator as coordinator
    from modules.telemetry.rootline_execution_authority import build_execution_eligibility
    from modules.telemetry.rootline_timed_control import timed_control_scope
    now = datetime.now(timezone.utc)
    _, _, old, _, _ = start("A12345", at=now-timedelta(hours=3))
    seed(old.rows)
    active = db("load_active", None)
    assert db("mark_stopping", {**active, "state": "stopping", "reason": "owner_requested_stop"})["success"]
    class Persisted:
        @property
        def active(self): return db("load_active", None)
        @property
        def rows(self):
            with connect() as connection:
                return [row[0] for row in connection.execute(
                    "select review_json->'rootline_execution' from public.sam_live_stock_conversation_review_events order by created_at,review_event_id")]
    memory = Persisted()
    clock = [now]
    transport = Transport(memory, lambda: clock[0])
    # Reconnected transport must resolve the original stop before a new admission.
    closed = recover(db, transport, clock)
    assert closed["execution"]["reason"] == "owner_requested_stop"
    assert memory.active is None and [row[2] for row in transport.calls] == ["OFF"]
    plan, evidence, _ = inputs(zone="E12345")
    selected = now.astimezone(timezone(timedelta(hours=2))).date().isoformat()
    plan["operating_date"] = selected
    evidence["weather"]["observed_at"] = evidence["tanks"]["observed_at"] = now.isoformat()
    evidence["irrigation"].update(advisor_generated_at=now.isoformat(), advisor_operating_date=selected)
    offline = route(now=now); offline["command_route_ready"] = False
    offline["response_digest"] = digest({k:v for k,v in offline.items() if k != "response_digest"})
    with timed_control_scope(ENV):
        held = build_execution_eligibility(plan=plan, evidence=evidence, controller=offline, now=now)
        assert not held["eligible"] and memory.active is None
        artifact = build_execution_eligibility(plan=plan, evidence=evidence, controller=route(now=now), now=now)
        assert artifact["eligible"]
        assert db("record_eligibility", artifact)["success"]
        output, _, identity = runtime._commissioned_output("E12345", stop_mode="scheduled")
        packet = runtime._timed_mapping_packet(output, identity)
        decision = {"decision_id": "RECOVERED-E", "decision": "Run now", "standing_authority": True,
            "zone_id": "E12345", "runtime_minutes": 120, "runtime_seconds": 7200,
            "execution_id": artifact["execution_id"], "eligibility_id": artifact["eligibility_id"],
            "evidence_generation": artifact["plan_generation"], "assessed_at": now.isoformat(),
            "commissioning_id": identity, "commissioning_generation": 1, "execution_eligibility": artifact}
        decision["decision_sha256"] = coordinator._digest(decision)
        resumed = coordinator.advance_irrigation_execution(decision_id=decision["decision_id"], commissioning_id=identity,
            decision_reader=lambda _: decision, commissioning_reader=lambda _: packet, store=db, transport=transport,
            notify=lambda *args: {}, eligibility_revalidator=lambda _: artifact, now=now, clock=lambda: clock[0])
    assert resumed["status"] == "irrigation_on_command_accepted", resumed
    assert memory.active["zone_id"] == "E12345"
    resumed_id = memory.active["execution_id"]
    clock[0] += timedelta(seconds=60)
    recover(db, transport, clock)
    assert memory.active["execution_id"] == resumed_id
    assert [row[2] for row in transport.calls] == ["OFF", "ON"]
    assert any(row.get("action") == "record_on_outcome" and row.get("execution_id") == resumed_id for row in memory.rows)
