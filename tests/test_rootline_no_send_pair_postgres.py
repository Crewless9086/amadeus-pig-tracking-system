"""Private two-read ownership, exact receipt and deadline qualification."""
from contextlib import nullcontext
from datetime import datetime, timezone
from copy import deepcopy
import threading
import time

import pytest

from tests.test_rootline_no_send_preparation_postgres import (
    Subject, connect, isolated_database, DATABASE_URL, budget, bounded, cycle,
    readback, oauth, executions)
from modules.sales import sam_live_stock_launch_control as launch

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="explicit disposable PostgreSQL URL required")


def test_same_prepared_context_cannot_be_used_twice(monkeypatch):
    subject = Subject(monkeypatch)
    original = readback._PreparedNoSendRead.read_locked
    rejected = []
    def twice(prepared, **kwargs):
        value = original(prepared, **kwargs)
        calls = list(subject.calls)
        with pytest.raises(readback.NoSendReadUnavailable, match="changed_or_consumed"):
            original(prepared, **kwargs)
        rejected.append(True)
        assert calls == subject.calls
        return value
    monkeypatch.setattr(readback._PreparedNoSendRead, "read_locked", twice)
    assert subject.run()["status"] == "execution_not_dispatched"
    assert rejected == [True]


def test_metadata_then_locked_status_keep_six_acknowledged_audits_and_fresh_preimage(monkeypatch):
    import psycopg
    subject = Subject(monkeypatch)
    original_dispatch = budget.RequestBudget.dispatch
    original_preimage = budget.RequestBudget._admission_preimage
    facades, snapshots, observations = [], [], []
    def dispatch(client, **kwargs):
        facades.append((client, budget._private_pair.get()))
        return original_dispatch(client, **kwargs)
    def preimage(client, connection, **kwargs):
        value = original_preimage(client, connection, **kwargs)
        snapshots.append((value[2], value[0]["pending_attempt"], value[0]["last_finished_at"]))
        return value
    def sent():
        active = budget._private_pair.get()
        session = budget._dispatch_audit.get()
        audit = session["connection"]
        assert audit._connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert audit is not session["fence"]
        assert session["fence"]._connection.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        observations.append((active, audit))
        attempts = [row for row in subject.audit() if row["action"] == "request_attempt_reserved"]
        completions = [row for row in subject.audit() if row["action"] == "request_completed"]
        assert len(attempts) == len(completions)+1
    monkeypatch.setattr(budget.RequestBudget, "dispatch", dispatch)
    monkeypatch.setattr(budget.RequestBudget, "_admission_preimage", preimage)
    for path in ("/v2/family", "/v2/device/thing", "/v2/device/thing/status"):
        subject.hooks[path] = sent
    assert subject.run()["status"] == "execution_not_dispatched"
    assert len(facades) == 3 and len({id(row[0]) for row in facades}) == 3
    assert [row[1] is not None for row in facades] == [False, False, True]
    assert [row[0].environ["EWELINK_EXPECTED_DEVICE_ID"] for row in facades] == [
        "100204e9bc", "100204e9bc", "1002851416"]
    assert all(row[1].closed for row in observations)
    assert observations[2][0].fence.closed
    assert len(snapshots) == 1 and snapshots[0][1] is None and snapshots[0][2] is not None
    audit = subject.audit()
    assert len([r for r in audit if r["action"] == "request_attempt_reserved"]) == 3
    assert len([r for r in audit if r["action"] == "request_completed"]) == 3
    assert budget._private_pair.get() is None and budget._dispatch_audit.get() is None


@pytest.mark.parametrize("change", ["application", "region", "database", "unknown_environment",
    "status_anchor", "status_target", "endpoint", "group_object", "group_id", "duty", "capability", "missing_capability", "thread"])
def test_private_facade_mismatch_never_falls_back_or_sends_second_request(monkeypatch, change):
    subject = Subject(monkeypatch)
    original = budget.RequestBudget.dispatch
    def tamper(client, **kwargs):
        pair = budget._private_pair.get()
        target_phase = "/v2/device/thing/status"
        if pair is None or kwargs["endpoint"] != target_phase:
            return original(client, **kwargs)
        token = None
        variable = None
        if change in {"application", "database", "unknown_environment", "status_anchor", "status_target"}:
            client.environ = dict(client.environ)
            key, value = {"application": ("EWELINK_CLIENT_ID", "other"),
                "database": ("DATABASE_URL", "synthetic-wrong-connection"),
                "unknown_environment": ("UNRECOGNIZED_CONTEXT", "changed"),
                "status_anchor": ("EWELINK_EXPECTED_DEVICE_ID", "100204e9bc"),
                "status_target": ("EWELINK_EXPECTED_DEVICE_ID", "different-target")}[change]
            client.environ[key] = value
        elif change == "region": kwargs["region"] = "us"
        elif change == "endpoint": kwargs["endpoint"] = "/v2/family"
        elif change == "group_id": pair.group["id"] = "different"
        elif change == "thread": pair.thread = -1
        else:
            variable = {"group_object": budget._group, "duty": budget._duty,
                "capability": budget._private_pair, "missing_capability": budget._private_pair}[change]
            replacement = dict(pair.group) if change == "group_object" else (
                {**pair.duty, "execution_id": "other"} if change == "duty" else
                None if change == "missing_capability" else object())
            token = variable.set(replacement)
        try:
            return original(client, **kwargs)
        finally:
            if token is not None: variable.reset(token)
    monkeypatch.setattr(budget.RequestBudget, "dispatch", tamper)
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == ["/v2/family", "/v2/device/thing"]
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())


@pytest.mark.parametrize("change", ["query", "method", "host", "body", "auth", "token"])
def test_real_provider_guards_remain_ahead_of_private_dispatch(monkeypatch, change):
    subject = Subject(monkeypatch)
    original = readback._provider_request
    def request(method, url, **kwargs):
        if "/v2/device/thing/status" in url:
            if change == "query": url = url.replace("type=1", "type=2")
            elif change == "method": method = "POST"
            elif change == "host": url = url.replace("https://eu-apia.coolkit.cc", "https://invalid.example")
            elif change == "body": kwargs["body"] = {"switch": "on"}
            elif change == "auth": kwargs["mode"] = "signed"
            else: kwargs["token"] = ""
        return original(method, url, **kwargs)
    monkeypatch.setattr(readback, "_provider_request", request)
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == ["/v2/family", "/v2/device/thing"]


def test_abandonment_during_status_http_prevents_proof_and_keeps_charge(monkeypatch):
    subject = Subject(monkeypatch)
    observed = []
    def cancel():
        pair = budget._private_pair.get()
        pair.abandon()
        observed.append(pair)
    subject.hooks["/v2/device/thing/status"] = cancel
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == ["/v2/family", "/v2/device/thing", "/v2/device/thing/status"]
    assert observed[0].abandoned and observed[0].fence.closed
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]


def test_late_status_http_abandons_before_unlock_then_drains_without_proof(monkeypatch):
    subject = Subject(monkeypatch)
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    values, pairs = [], []
    def late():
        pairs.append(budget._private_pair.get())
        entered.set()
        assert release.wait(12)
    subject.hooks["/v2/device/thing/status"] = late
    def invoke():
        try: values.append(subject.run())
        finally: returned.set()
    caller = threading.Thread(target=invoke, name="synthetic-no-send-caller")
    caller.start()
    try:
        assert entered.wait(5)
        assert returned.wait(9)
        assert values[0]["status"] == "no_send_off_proof_pending"
        assert pairs[0].abandoned and not pairs[0].fence.closed
        with connect() as observer:
            free = observer.execute("select pg_try_advisory_xact_lock(1874320911),"
                "pg_try_advisory_xact_lock(1874320912)").fetchone()
            assert free == (True, True)
            assert observer.execute("select pg_try_advisory_xact_lock(%s)",
                (budget.GLOBAL_SEND_LOCK,)).fetchone() == (False,)
        # A separate group defers on the still-owned fence; it cannot share it.
        with pytest.raises(budget.RequestBudgetUnavailable, match="dispatch_busy"):
            subject.client.dispatch(region="eu", endpoint="/v2/family",
                send=lambda _: pytest.fail("Competing group must not send"))
    finally:
        release.set()
        caller.join(3)
        for worker in threading.enumerate():
            if worker.name == "rootline-bounded-ewelink-read": worker.join(3)
    assert not caller.is_alive() and pairs[0].fence.closed
    assert subject.calls == ["/v2/family", "/v2/device/thing", "/v2/device/thing/status"]
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    slots = [budget._request_workers.acquire(False) for _ in range(2)]
    try: assert slots == [True, True]
    finally:
        for owned in slots:
            if owned: budget._request_workers.release()


def receipt_event(identity="SYNTHETIC-EXACT-RECEIPT"):
    event = launch.build_sam_live_stock_review_event({"conversation_id": "SYNTHETIC-RECEIPT"},
        {}, {}, {"score": 0, "safe_to_send": False, "recommended_action": "audit"},
        event_source=budget.EVENT_SOURCE)
    event.update(review_event_id=identity, review_json={"synthetic": {"a": 1}})
    return event


def test_canonical_receipt_insert_exact_replay_conflict_and_default_contract():
    event = receipt_event()
    before = datetime.now(timezone.utc)
    result, status = launch.record_sam_live_stock_review_event(event, database_url=DATABASE_URL,
        durable_receipt=True)
    assert status == 201 and result["created"] is True
    assert result["conversation_event_count"] is None
    receipt = result["persisted_receipt"]
    assert receipt["review_json"] == event["review_json"]
    assert before <= receipt["created_at"] <= datetime.now(timezone.utc)
    replay, status = launch.record_sam_live_stock_review_event(event, database_url=DATABASE_URL,
        durable_receipt=True)
    assert status == 200 and replay["persisted_receipt"] == receipt
    conflict, status = launch.record_sam_live_stock_review_event({**event, "review_json": {"other": 1}},
        database_url=DATABASE_URL, durable_receipt=True)
    assert status == 500 and conflict["success"] is False
    normal, status = launch.record_sam_live_stock_review_event(receipt_event("SYNTHETIC-NORMAL"),
        database_url=DATABASE_URL)
    assert status == 201 and normal["conversation_event_count"] == 2
    assert "persisted_receipt" not in normal


@pytest.mark.parametrize("mode", ["before_transform", "statement_error", "deferred_error"])
def test_canonical_receipt_rejects_trigger_transform_and_statement_or_commit_failure(mode):
    with connect() as setup:
        if mode == "before_transform":
            body = "new.review_json := '{\"changed\":true}'::jsonb; return new;"
        else:
            body = "raise exception 'synthetic receipt constraint';"
        setup.execute("create or replace function app_private.synthetic_receipt_guard() returns trigger "
            "language plpgsql as $$ begin " + body + " end $$")
        if mode == "deferred_error":
            setup.execute("create constraint trigger synthetic_receipt_guard after insert on "
                "public.sam_live_stock_conversation_review_events deferrable initially deferred "
                "for each row execute function app_private.synthetic_receipt_guard()")
        else:
            setup.execute("create trigger synthetic_receipt_guard before insert on "
                "public.sam_live_stock_conversation_review_events for each row "
                "execute function app_private.synthetic_receipt_guard()")
    try:
        result, status = launch.record_sam_live_stock_review_event(receipt_event(),
            database_url=DATABASE_URL, durable_receipt=True)
        assert status == 500 and result["success"] is False
        with connect() as observer:
            assert observer.execute("select count(*) from public.sam_live_stock_conversation_review_events "
                "where review_event_id='SYNTHETIC-EXACT-RECEIPT'").fetchone() == (0,)
    finally:
        with connect() as cleanup:
            cleanup.execute("drop trigger synthetic_receipt_guard on public.sam_live_stock_conversation_review_events")
            cleanup.execute("drop function app_private.synthetic_receipt_guard()")


def test_scoped_timeout_knowledge_invalidates_savepoint_raw_set_commit_and_rollback():
    with cycle.cycle_budget(deadline=time.monotonic()+4):
        with bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
                read_only=False, reuse_local_settings=True, read_committed=True) as connection:
            connection.execute("select clock_timestamp()").fetchone()
            assert connection._installed_timeout is not None
            connection.execute("savepoint synthetic_bound")
            assert connection._installed_timeout is None and connection._reuse_disabled
            with cycle.cycle_budget(deadline=time.monotonic()+.08):
                connection.execute("select 1")
                actual = connection._connection.execute("show statement_timeout").fetchone()[0]
                assert actual.endswith("ms") and 0 < int(actual[:-2]) <= 80
            connection.execute("rollback to savepoint synthetic_bound")
            connection.execute("select set_config('statement_timeout','20s',true)")
            connection.execute("select 1")
            assert connection._installed_timeout is None
            assert connection._connection.execute("show statement_timeout").fetchone()[0] != "20s"
            connection.commit()
            connection.execute("select 1")
            connection.rollback()
            assert connection._installed_timeout is None
            with connection.cursor() as cursor:
                cursor.cursor.execute("set local statement_timeout='20s'")
                cursor.execute("select 1")
            raw = connection.connection
            raw.execute("set local statement_timeout='20s'")
            connection.execute("select 1")
            assert raw.execute("show statement_timeout").fetchone()[0] != "20s"


@pytest.mark.parametrize("stage", ["intent", "completion", "terminal"])
def test_exact_live_reject_only_trigger_refuses_before_send_or_acceptance(monkeypatch, stage):
    subject = Subject(monkeypatch)
    marker = {"intent": "request_attempt_reserved", "completion": "request_completed",
        "terminal": "record_execution_not_dispatched"}[stage]
    def install_denial():
        with connect() as connection:
            connection.execute("insert into public.litter_cohort_dispositions values (%s)", (marker,))
    subject.hooks["/v2/family" if stage == "intent" else "/v2/device/thing"] = install_denial
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == (["/v2/family"] if stage == "intent" else
        ["/v2/family", "/v2/device/thing"] if stage == "completion" else
        ["/v2/family", "/v2/device/thing", "/v2/device/thing/status"])
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]


def test_binding_failure_after_first_read_records_existing_snapshot_hold(monkeypatch):
    subject = Subject(monkeypatch)
    subject.packets["/v2/device/thing"]["thingList"][0]["itemData"]["apikey"] = "different-account"
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == ["/v2/family", "/v2/device/thing"]
    assert any(row["action"] == "snapshot_validation_failed" for row in subject.audit())


def test_equal_anchor_target_still_binds_one_locked_status_facade(monkeypatch):
    subject = Subject(monkeypatch)
    identity = "SYNTHETIC-EQUAL-ANCHOR"
    subject.client.reserve_for_on(execution_id=identity, device_id="100204e9bc",
        channel=1, device_type="irrigation_zone_valve", region="eu")
    subject.packets["/v2/device/thing"]["thingList"][0]["itemData"]["deviceid"] = "100204e9bc"
    subject.status_device_id = "100204e9bc"
    binding = {"execution_id": identity, "device_id": "100204e9bc", "channel": 1}
    facades = []
    original = budget.RequestBudget.dispatch
    def dispatch(client, **kwargs):
        if budget._private_pair.get() is not None: facades.append(client)
        return original(client, **kwargs)
    monkeypatch.setattr(budget.RequestBudget, "dispatch", dispatch)
    from datetime import timedelta
    with budget.execution_duty(binding), readback.prepare_registered_no_send_read(
            binding=binding, token_store=subject.tokens, environ=subject.source) as prepared:
        with bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
                read_only=False) as connection:
            connection.execute("select pg_advisory_xact_lock(1874320911)")
            connection.execute("select pg_advisory_xact_lock(1874320912)")
            value = prepared.read_locked(binding=binding, connection=connection,
                deadline=datetime.now(timezone.utc)+timedelta(seconds=8))
    assert value["device_id"] == "100204e9bc"
    assert len(facades) == 1
    assert all(client.environ["EWELINK_EXPECTED_DEVICE_ID"] == "100204e9bc" for client in facades)


@pytest.mark.parametrize("commit_fault", ["none", "failed", "lost_ack", "unproven_idle"])
def test_private_audit_frontend_survives_synthetic_backend_turnover(monkeypatch, commit_fault):
    """Synthetic stable frontend; this is not qualification of an actual pooler."""
    import psycopg
    subject = Subject(monkeypatch)
    # This explicit synthetic non-native frontend exercises the retained
    # injected-acquisition fallback, not the native preopened-client capability.
    monkeypatch.setattr(budget, "_PreparedNoSendClients", lambda *_: None)
    original = budget.RequestBudget._connect
    frontends, proxies, receipts, swaps = [], [], [], []

    class BackendProxy:
        def __init__(self, native):
            self.native = native
            self.natives = [native]
            self.outer = None
            self.default = native.execute("show default_transaction_isolation").fetchone()[0]
        def __getattr__(self, key):
            return getattr(self.native, key)
        def commit(self):
            native = self.native
            receipt = {"outer": id(self.outer), "proxy": id(self),
                "backend": native.info.backend_pid, "default": self.default,
                "isolation": native.execute("show transaction_isolation").fetchone()[0],
                "native_commit_returned": False, "old_idle_acknowledged": False}
            receipts.append(receipt)
            assert receipt["isolation"] == "read committed"
            if commit_fault == "failed":
                raise psycopg.OperationalError("synthetic old native commit failed")
            native.commit()
            receipt["native_commit_returned"] = True
            if commit_fault == "unproven_idle":
                native.execute("select 1")
            receipt["old_idle_acknowledged"] = native.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            if not receipt["old_idle_acknowledged"]:
                raise budget.RequestBudgetUnavailable("synthetic old native commit is not idle")
            if commit_fault == "lost_ack":
                raise psycopg.OperationalError("synthetic old commit acknowledgement lost")
            # Only successful old-native return AND its own IDLE acknowledgement
            # permit the test-only backend swap. A new backend cannot prove them.
            native.close()
            replacement = psycopg.connect(DATABASE_URL, connect_timeout=3,
                options=r"-c default_transaction_isolation=repeatable\ read -c statement_timeout=3000")
            self.natives.append(replacement)
            # Test-only scalar observation plus rollback leaves the simulated
            # replacement idle; application must choose RC before its first SELECT.
            default = replacement.execute("show default_transaction_isolation").fetchone()[0]
            replacement.rollback()
            assert default == "repeatable read"
            assert replacement.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            swaps.append({"old": receipt["backend"], "new": replacement.info.backend_pid,
                "new_default": default, "old_commit_returned": True, "old_idle_acknowledged": True})
            self.native, self.default = replacement, default

    def factory(client):
        session = budget._dispatch_audit.get()
        private_audit = budget._private_pair.get() is not None and session is not None and session["fence"] is not None
        connection = (bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
            connect=psycopg.connect, read_only=False, reuse_local_settings=True, read_committed=True)
            if private_audit else original(client))
        if private_audit:
            assert connection._native_begin_connection is None
            proxy = BackendProxy(connection._connection)
            proxy.outer = connection
            connection._connection = proxy  # stable native-frontend simulation seam
            frontends.append(connection)
            proxies.append(proxy)
        return connection

    monkeypatch.setattr(budget.RequestBudget, "_connect", factory)
    result = subject.run()
    assert len(frontends) == len(proxies) == 1
    assert {r["outer"] for r in receipts} == {id(frontends[0])}
    assert {r["proxy"] for r in receipts} == {id(proxies[0])}
    assert frontends[0]._connection is proxies[0]
    assert frontends[0].closed and all(native.closed for native in proxies[0].natives)
    if commit_fault == "none":
        assert result["status"] == "execution_not_dispatched"
        assert len(receipts) == len({r["backend"] for r in receipts}) == len(swaps) == 2
        assert all(r["native_commit_returned"] and r["old_idle_acknowledged"] for r in receipts)
        assert all(r["default"] == "repeatable read" for r in receipts[1:])
        assert all(row["old"] != row["new"] and row["new_default"] == "repeatable read" for row in swaps)
    else:
        assert result["status"] == "no_send_off_proof_pending"
        assert subject.calls == ["/v2/family", "/v2/device/thing"] and swaps == []
        assert len(receipts) == 1
        assert receipts[0]["native_commit_returned"] is (commit_fault != "failed")
        assert receipts[0]["old_idle_acknowledged"] is (commit_fault == "lost_ack")
        assert subject.claim["execution_id"] in subject.ledger()["reserves"]
        assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())


@pytest.mark.parametrize("commit_number", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("ack_lost", [False, True])
def test_each_audit_commit_failure_stops_before_next_endpoint_or_output(monkeypatch, commit_number, ack_lost):
    import psycopg
    subject = Subject(monkeypatch)
    original = bounded._CycleBudgetConnection.commit
    commits, clients = [], []
    def commit(connection):
        session = budget._dispatch_audit.get()
        audit = session is not None and session.get("connection") is connection
        if audit:
            commits.append(connection)
            if connection not in clients: clients.append(connection)
            if len(commits) == commit_number and not ack_lost:
                connection.rollback()
                raise psycopg.OperationalError("synthetic audit rollback before acknowledgement")
        original(connection)
        if audit and len(commits) == commit_number and ack_lost:
            raise psycopg.OperationalError("synthetic audit acknowledgement lost")
    monkeypatch.setattr(bounded._CycleBudgetConnection, "commit", commit)
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == ["/v2/family", "/v2/device/thing", "/v2/device/thing/status"][:commit_number//2]
    assert len(commits) >= commit_number and all(client.closed for client in clients)
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())


@pytest.mark.parametrize("fault", ["thread_start", "slots", "nested"])
def test_private_worker_lifetime_refuses_nested_or_unavailable_workers(monkeypatch, fault):
    subject = Subject(monkeypatch)
    if fault == "thread_start":
        original = threading.Thread.start
        def start(worker):
            if getattr(worker._target, "__qualname__", "").startswith("_NoSendPair.run."):
                raise RuntimeError("synthetic pair thread start refusal")
            return original(worker)
        monkeypatch.setattr(threading.Thread, "start", start)
    elif fault == "slots":
        original = budget._NoSendPair.run
        def run(pair, read):
            acquired = [budget._request_workers.acquire(False) for _ in range(2)]
            assert acquired == [True, True]
            try: return original(pair, read)
            finally:
                for _ in acquired: budget._request_workers.release()
        monkeypatch.setattr(budget._NoSendPair, "run", run)
    else:
        def nested():
            pair = budget._private_pair.get()
            with pytest.raises(budget.RequestBudgetUnavailable, match="context_rejected"):
                budget._NoSendPair(source=pair.source, binding=pair.binding,
                    token_identity=pair.token_identity, group=pair.group)
        subject.hooks["/v2/device/thing/status"] = nested
    value = subject.run()
    assert value["status"] == ("execution_not_dispatched" if fault == "nested" else "no_send_off_proof_pending")
    assert len(subject.calls) == (3 if fault == "nested" else 2)
    acquired = [budget._request_workers.acquire(False) for _ in range(2)]
    try: assert acquired == [True, True]
    finally:
        for owned in acquired:
            if owned: budget._request_workers.release()


@pytest.mark.parametrize("history_size", [0, 1, 5000])
def test_combined_fresh_preimage_matches_original_queries_and_window_counts(history_size):
    import json
    client = budget.RequestBudget({"DATABASE_URL": DATABASE_URL, "EWELINK_CLIENT_ID": "synthetic"})
    state = {"version": 1, "coverage_start": datetime.now(timezone.utc).isoformat(),
        "prior_provider_usage": "Unknown", "provider_remaining": "Unknown", "provider_entitlement": "Unknown",
        "external_clients_counted": False, "scopes": {}, "reserves": {}, "last_finished_at": None,
        "pending_attempt": None}
    if history_size:
        with connect() as connection:
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,event_source,review_json,created_at)
                select 'SYNTHETIC-HISTORY-'||i,%s,%s,jsonb_build_object('ewelink_request_budget',
                    jsonb_build_object('state',%s::jsonb,'attempt_units',case when i%%4=0 then 0 else 1 end,
                        'detail',jsonb_build_object('scope',case when i%%2=0 then 'scope1' else 'scope2' end,
                            'region',case when i%%3=0 then 'eu' else 'us' end))),
                    clock_timestamp()-(i%%3 * interval '5 minutes')
                from generate_series(1,%s) as i""",
                (budget.LEDGER_ID,budget.EVENT_SOURCE,json.dumps(state),history_size))
    with client._locked() as connection:
        for scope, region in ((None,None),("scope1","eu"),("scope2","us"),("missing","cn")):
            fresh, at, counts = client._admission_preimage(connection, scope=scope, region=region)
            old = client._load(connection)
            if history_size: assert fresh == old == state
            else:
                assert {k:v for k,v in fresh.items() if k != "coverage_start"} == {
                    k:v for k,v in old.items() if k != "coverage_start"}
            assert counts == client._counts(connection, at, scope=scope, region=region)


@pytest.mark.parametrize("payload", [None, [], {}, {"state": {}}, {"state": {"version": 2}}])
def test_empty_or_invalid_stored_ledger_never_becomes_a_fresh_ledger(payload):
    import json
    client = budget.RequestBudget({"DATABASE_URL": DATABASE_URL, "EWELINK_CLIENT_ID": "synthetic"})
    with connect() as connection:
        connection.execute("insert into public.sam_live_stock_conversation_review_events "
            "(review_event_id,chatwoot_conversation_id,event_source,review_json) values (%s,%s,%s,%s::jsonb)",
            ("SYNTHETIC-INVALID-LEDGER",budget.LEDGER_ID,budget.EVENT_SOURCE,
             json.dumps({"ewelink_request_budget": payload})))
    with client._locked() as connection:
        with pytest.raises(budget.RequestBudgetUnavailable, match="ledger_invalid"):
            client._admission_preimage(connection, scope="synthetic", region="eu")
        with pytest.raises(budget.RequestBudgetUnavailable, match="ledger_invalid"):
            client._load(connection)


class _SettingsTrace:
    """Real PostgreSQL with observation and explicit acknowledgement faults only."""
    def __init__(self):
        self.raw = None
        self.sql = []
        self.fault = None
        self.delay_settings = 0

    def connect(self, *args, **kwargs):
        import psycopg
        self.raw = psycopg.connect(*args, **kwargs)
        trace = self
        class Cursor:
            def __init__(self, cursor):
                self.raw, self.statement = cursor, None
            def __enter__(self):
                self.raw.__enter__()
                return self
            def __exit__(self, *args):
                return self.raw.__exit__(*args)
            def execute(self, statement, params=None, **kwargs):
                self.statement = statement
                trace.sql.append(statement)
                if trace.fault == "execute" and statement == bounded._CONFIGURATION_SQL:
                    raise psycopg.OperationalError("synthetic verifier acknowledgement loss")
                self.raw.execute(statement, params, **kwargs)
                if statement.startswith("set local statement_timeout=") and trace.delay_settings:
                    time.sleep(trace.delay_settings)
                return self
            def fetchone(self):
                row = self.raw.fetchone()
                if self.statement == bounded._CONFIGURATION_SQL:
                    if trace.fault == "statement":
                        return ("20s", row[1], row[2])
                    if trace.fault == "lock":
                        return (row[0], "20s", row[2])
                    if trace.fault == "isolation":
                        return (*row[:2], "repeatable read")
                    if trace.fault == "shape":
                        return row[:2]
                return row
            def __getattr__(self, name):
                return getattr(self.raw, name)
        class Connection:
            def cursor(self, *args, **kwargs):
                return Cursor(trace.raw.cursor(*args, **kwargs))
            def __enter__(self):
                trace.raw.__enter__()
                return self
            def __exit__(self, *args):
                return trace.raw.__exit__(*args)
            def __getattr__(self, name):
                return getattr(trace.raw, name)
        return Connection()

    def open(self):
        return bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
            connect=self.connect, read_only=False, reuse_local_settings=True, read_committed=True)


def test_setup_reuse_requires_both_bounds_and_verified_fresh_transaction():
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        before = list(trace.sql)
        connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
        assert trace.sql == before  # genuine no-SQL reuse of initial acknowledged proof
        connection.configure_transaction_timeouts(3000, 500, read_committed=True)
        assert trace.sql[len(before):] == [bounded._CONFIGURATION_SQL]
        assert trace.raw.execute("show lock_timeout").fetchone() == ("500ms",)
        connection.commit()
        before = len(trace.sql)
        connection.configure_transaction_timeouts(3000, 500, read_committed=True)
        later = trace.sql[before:]
        assert bounded._ISOLATION_SQL in later and bounded._CONFIGURATION_SQL in later
        assert later.index(bounded._ISOLATION_SQL) < later.index(bounded._CONFIGURATION_SQL)
        assert connection._installed_timeout == 3000 and connection._installed_lock_timeout == 500
    assert trace.raw.closed


@pytest.mark.parametrize("route", ["connection", "cursor", "cursor.connection", "info.pgconn"])
def test_setup_retained_raw_alias_permanently_disables_reuse(route):
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        with connection.cursor() as cursor:
            raw = (connection.connection if route == "connection" else
                cursor.cursor if route == "cursor" else
                connection.info.pgconn if route == "info.pgconn" else cursor.connection)
            connection.rollback()
            connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
            assert connection._reuse_disabled and connection._installed_timeout is None
            if route == "info.pgconn":
                from psycopg.pq import ExecStatus
                assert raw.exec_(b"set local statement_timeout='20s'").status == ExecStatus.COMMAND_OK
            else:
                raw.execute("set local statement_timeout='20s'")
            with pytest.raises(RuntimeError, match="isolation_unproven"):
                connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
            connection.execute("select clock_timestamp()").fetchone()
            assert trace.raw.execute("show statement_timeout").fetchone()[0] != "20s"
            assert connection._installed_timeout is None
    assert trace.raw.closed


@pytest.mark.parametrize("rollback", [False, True])
def test_setup_nested_native_transaction_exit_keeps_reuse_disabled(rollback):
    trace = _SettingsTrace()
    class SyntheticAbort(Exception):
        pass
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        try:
            with connection.transaction() as transaction:
                assert transaction.connection is trace.raw
                connection.configure_transaction_timeouts(200, 100, read_committed=False)
                assert trace.raw.execute("show statement_timeout").fetchone() == ("200ms",)
                assert connection._installed_timeout is None
                if rollback:
                    raise SyntheticAbort()
        except SyntheticAbort:
            assert rollback
        assert connection._reuse_disabled and connection._installed_timeout is None
        assert trace.raw.execute("show statement_timeout").fetchone() == (
            "3s" if rollback else "200ms",)
        connection.execute("select clock_timestamp()").fetchone()
        assert connection._installed_timeout is None
    assert trace.raw.closed


@pytest.mark.parametrize("statement", [
    "select set_config('statement_timeout','20s',true)",
    "with changed as (select set_config('statement_timeout','20s',true)) select * from changed",
    "insert into synthetic_settings_escape(value) values (set_config('statement_timeout','20s',true))",
])
def test_setup_unknown_settings_capable_sql_cannot_use_prefix_trust(statement):
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        trace.raw.execute("create temporary table synthetic_settings_escape(value text)")
        connection.execute(statement)
        assert trace.raw.execute("show statement_timeout").fetchone() == ("20s",)
        assert connection._reuse_disabled and connection._installed_timeout is None
        connection.execute("select clock_timestamp()").fetchone()
        assert trace.raw.execute("show statement_timeout").fetchone() == ("3s",)
        assert connection._installed_timeout is None
    assert trace.raw.closed


@pytest.mark.parametrize("fault", ["statement", "lock", "isolation", "shape", "execute"])
def test_setup_fixed_verifier_failure_never_installs_proof(fault):
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        trace.fault = fault
        with pytest.raises(Exception, match="unproven|acknowledgement loss"):
            connection.configure_transaction_timeouts(2000, 500, read_committed=True)
        assert connection._installed_timeout is None
        assert connection._installed_lock_timeout is None and not connection._read_committed
    assert trace.raw.closed


@pytest.mark.parametrize("which", ["captured", "current"])
def test_setup_no_sql_return_still_checks_minimum_deadline(which):
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        if which == "captured":
            connection.deadline = time.monotonic()-1
        with cycle.cycle_budget(deadline=time.monotonic()-1 if which == "current" else time.monotonic()+10):
            before = list(trace.sql)
            with pytest.raises(cycle.RootlineCycleDeadlineExceeded):
                connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
            assert trace.sql == before
    assert trace.raw.closed


def test_setup_no_sql_return_does_not_admit_later_statement():
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
        with cycle.cycle_budget(deadline=time.monotonic()+.2):
            before = len(trace.sql)
            connection.execute("select clock_timestamp()").fetchone()
            assert trace.sql[before].startswith("set local statement_timeout=")
            assert 0 < connection._installed_timeout <= 200
        with cycle.cycle_budget(deadline=time.monotonic()-1):
            before = list(trace.sql)
            with pytest.raises(cycle.RootlineCycleDeadlineExceeded):
                connection.execute("select clock_timestamp()")
            assert trace.sql == before
    assert trace.raw.closed


def test_setup_disabled_guard_rechecks_remaining_time_after_slow_setter():
    trace = _SettingsTrace()
    with cycle.cycle_budget(deadline=time.monotonic()+10), trace.open() as connection:
        _retained = connection.info.pgconn
        trace.delay_settings = .12
        with cycle.cycle_budget(deadline=time.monotonic()+.2):
            before = len(trace.sql)
            with pytest.raises(cycle.RootlineCycleDeadlineExceeded):
                connection.configure_transaction_timeouts(3000, 1000, read_committed=False)
            assert bounded._CONFIGURATION_SQL not in trace.sql[before:]
            assert all(sql.startswith("set local statement_timeout=") for sql in trace.sql[before:])
            assert connection._installed_timeout is None
    assert trace.raw.closed


def _native_begin_open():
    return bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
        read_only=False, reuse_local_settings=True, read_committed=True,
        native_begin_read_committed=True)


def _trace_query_count(wire, sql):
    expected = '"' + sql + '"'
    count = 0
    for line in wire.splitlines():
        fields = line.split("\t", 4)
        if (len(fields) == 5 and fields[1] == "F" and fields[3] == "Query"
                and fields[4].strip(" \t") == expected):
            count += 1
    return count


@pytest.mark.parametrize("wire,expected", [
    ('time\tF\t41\tQuery\t"BEGIN ISOLATION LEVEL READ COMMITTED"', 1),
    ('time\tF\t41\tQuery\t "BEGIN ISOLATION LEVEL READ COMMITTED"', 1),
    ('time\tF\t41\tQuery\t \t"BEGIN ISOLATION LEVEL READ COMMITTED"  ', 1),
    ('time\tF\t41\tParse\t "BEGIN ISOLATION LEVEL READ COMMITTED"', 0),
    ('time\tB\t41\tQuery\t "BEGIN ISOLATION LEVEL READ COMMITTED"', 0),
    ('time\tF\t41\tQuery\t "BEGIN ISOLATION LEVEL SERIALIZABLE"', 0),
    ('time\tF\t41\tQuery\t "BEGIN ISOLATION LEVEL READ COMMITTED;"', 0),
    ('time\tF\t41\tQuery\t "BEGIN ISOLATION LEVEL READ COMMITTED" suffix', 0),
    ('time\tF\t41\tQuery\t "BEGIN ISOLATION LEVEL READ COMMITTED"\textra', 0),
    ('Query\t"BEGIN ISOLATION LEVEL READ COMMITTED"', 0),
    ('time\tF\t41\tQuery\t BEGIN ISOLATION LEVEL READ COMMITTED', 0),
    ('\n'.join('time\tF\t41\tQuery\t' + spacing +
        '"BEGIN ISOLATION LEVEL READ COMMITTED"' for spacing in ('', ' ', '', ' ')), 4),
])
def test_native_begin_trace_query_fields(wire, expected):
    assert _trace_query_count(wire, "BEGIN ISOLATION LEVEL READ COMMITTED") == expected


@pytest.mark.parametrize("default", ["repeatable read", "serializable"])
def test_begin_native_intent_is_verified_for_each_of_four_transactions(monkeypatch, tmp_path, default):
    import psycopg
    import sys
    native_connect = psycopg.connect
    clients, trace_files = [], []
    can_trace = sys.platform != "win32"
    def connect_native(*args, **kwargs):
        kwargs["options"] += " -c default_transaction_isolation=" + default.replace(" ", r"\ ")
        client = native_connect(*args, **kwargs)
        client.prepare_threshold = None
        if can_trace:
            trace = (tmp_path / ("native-" + str(len(clients)) + ".trace")).open("wb")
            client.pgconn.trace(trace.fileno())
            trace_files.append(trace)
        clients.append(client)
        return client
    monkeypatch.setattr(psycopg, "connect", connect_native)
    with cycle.cycle_budget(deadline=time.monotonic()+12), _native_begin_open() as connection:
        raw = connection._connection
        assert connection._native_begin_connection is raw and type(raw) is psycopg.Connection
        assert raw.isolation_level == psycopg.IsolationLevel.READ_COMMITTED
        # A wrapper-shadowed attribute is not the native setter or server proof.
        connection.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
        for index in range(4):
            if index:
                assert not connection._read_committed
                with pytest.raises(RuntimeError, match="isolation_unproven"):
                    connection.execute("select clock_timestamp()")
                connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
            actual = raw.execute("select current_setting('transaction_isolation'),"
                "current_setting('statement_timeout'),current_setting('lock_timeout'),"
                "current_setting('default_transaction_isolation')").fetchone()
            assert actual == ("read committed", "3s", "1s", default)
            assert connection._read_committed and connection._installed_lock_timeout == 1000
            connection.execute("select clock_timestamp()").fetchone()
            connection.commit()
        if can_trace: raw.pgconn.untrace()
    for trace in trace_files: trace.close()
    # Windows binary libpq has no trace API. Server-state assertions above
    # still run; separate wire-relay qualification covers actual BEGIN bytes.
    if can_trace:
        wire = (tmp_path / "native-0.trace").read_text()
        assert _trace_query_count(wire, "BEGIN ISOLATION LEVEL READ COMMITTED") == 4
        assert "set transaction isolation level read committed" not in wire.lower()
        assert wire.count("set_config('statement_timeout'") == 4
    assert all(client.closed for client in clients)


@pytest.mark.parametrize("injected", [False, True])
def test_begin_generic_or_explicit_native_factory_keeps_legacy_semantics(injected):
    import psycopg
    with cycle.cycle_budget(deadline=time.monotonic()+10):
        with bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
                connect=psycopg.connect if injected else None, read_only=False,
                reuse_local_settings=True, read_committed=True,
                native_begin_read_committed=injected) as connection:
            assert connection._native_begin_connection is None
            assert connection._connection.isolation_level is None
            assert connection._read_committed
            assert connection.execute("select clock_timestamp()").fetchone()


@pytest.mark.parametrize("shape", ["missing", "read_only", "lying", "wrapper"])
def test_begin_native_capability_rejects_duck_types_before_attribute_mutation(shape):
    class NotNative:
        def __getattr__(self, name):
            pytest.fail("non-native capability must fail before reading mutable attributes: "+name)
    if shape == "wrapper":
        value = bounded._CycleBudgetConnection(NotNative(), time.monotonic()+10)
    elif shape == "read_only":
        class ReadOnly(NotNative):
            isolation_level = property(lambda _: 2)
        value = ReadOnly()
    elif shape == "lying":
        class Lying(NotNative):
            isolation_level = 2
        value = Lying()
    else:
        value = NotNative()
    with pytest.raises(RuntimeError, match="native_begin_state_unproven"):
        bounded._install_native_read_committed(value, time.monotonic()+10)


@pytest.mark.parametrize("state", ["closed_unknown", "autocommit", "intrans", "inerror", "transaction_context"])
def test_begin_rejects_invalid_native_state_without_repairing_caller_work(state):
    import psycopg
    raw = connect()
    manager = nullcontext()
    try:
        if state == "closed_unknown": raw.close()
        if state == "autocommit": raw.autocommit = True
        if state == "intrans": raw.execute("select 1")
        if state == "inerror":
            with pytest.raises(psycopg.errors.DivisionByZero): raw.execute("select 1/0")
        if state == "transaction_context": manager = raw.transaction()
        with manager:
            before = raw.info.transaction_status
            with pytest.raises(RuntimeError, match="native_begin_state_unproven"):
                bounded._install_native_read_committed(raw, time.monotonic()+10)
            assert raw.info.transaction_status == before
            assert raw.isolation_level is None
    finally:
        raw.close()


@pytest.mark.parametrize("pending", [False, True])
def test_begin_pipeline_is_rejected_without_flush_or_property_set(pending):
    import psycopg
    raw = connect()
    try:
        with raw.pipeline():
            cursor = raw.execute("select 17") if pending else None
            before = None if cursor is None else cursor.pgresult
            with pytest.raises(RuntimeError, match="native_begin_state_unproven"):
                bounded._install_native_read_committed(raw, time.monotonic()+10)
            assert raw.isolation_level is None
            assert raw.pgconn.pipeline_status != psycopg.pq.PipelineStatus.OFF
            assert cursor is None or cursor.pgresult is before
    finally:
        raw.close()


def test_begin_active_native_query_fails_before_contending_for_driver_lock():
    import psycopg
    raw = connect()
    errors = []
    def read():
        try: raw.execute("select pg_sleep(.35)")
        except BaseException as exc: errors.append(exc)
    worker = threading.Thread(target=read)
    try:
        worker.start()
        deadline = time.monotonic()+2
        while raw.info.transaction_status != psycopg.pq.TransactionStatus.ACTIVE:
            assert time.monotonic() < deadline
            time.sleep(.001)
        began = time.monotonic()
        with pytest.raises(RuntimeError, match="native_begin_state_unproven"):
            bounded._install_native_read_committed(raw, time.monotonic()+10)
        assert time.monotonic()-began < .15
    finally:
        worker.join(3)
        raw.close()
    assert not worker.is_alive() and errors == []


@pytest.mark.parametrize("fault", ["raise", "read_only", "wrong_intent", "stale_cached_begin"])
def test_begin_property_failure_never_falls_back_or_creates_server_proof(monkeypatch, fault):
    import psycopg
    raw = connect()
    original = psycopg.Connection.isolation_level
    if fault == "stale_cached_begin":
        raw.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        raw.execute("select 1"); raw.commit()
        monkeypatch.setattr(psycopg.Connection, "isolation_level", property(
            lambda _: psycopg.IsolationLevel.READ_COMMITTED, lambda *_: None))
    elif fault == "read_only":
        monkeypatch.setattr(psycopg.Connection, "isolation_level", property(original.fget))
    elif fault == "wrong_intent":
        monkeypatch.setattr(psycopg.Connection, "isolation_level", property(
            original.fget, lambda conn, _: original.fset(conn, psycopg.IsolationLevel.SERIALIZABLE)))
    else:
        def refused(*_): raise RuntimeError("synthetic native property failure")
        monkeypatch.setattr(psycopg.Connection, "isolation_level", property(original.fget, refused))
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: raw)
    with cycle.cycle_budget(deadline=time.monotonic()+10):
        with pytest.raises((RuntimeError, AttributeError)):
            _native_begin_open()
    assert raw.closed


@pytest.mark.parametrize("route", ["connection", "cursor", "cursor.connection", "info.pgconn"])
@pytest.mark.parametrize("mutation", ["isolation", "explicit_begin", "autocommit"])
def test_begin_raw_alias_permanently_revokes_native_ownership(route, mutation):
    import psycopg
    with cycle.cycle_budget(deadline=time.monotonic()+10), _native_begin_open() as connection:
        with connection.cursor() as cursor:
            if route == "connection": raw = connection.connection
            elif route == "cursor": raw = cursor.cursor.connection
            elif route == "cursor.connection": raw = cursor.connection
            else:
                pgconn = connection.info.pgconn
                raw = connection._connection
                assert pgconn is raw.pgconn
            connection.rollback()
            if mutation == "isolation": raw.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
            if mutation == "explicit_begin": raw.execute("begin isolation level repeatable read")
            if mutation == "autocommit": raw.autocommit = True
            with pytest.raises(RuntimeError, match="ownership_lost"):
                connection.configure_transaction_timeouts(3000, 1000, read_committed=True)
            with pytest.raises(RuntimeError, match="ownership_lost"):
                connection.execute("select clock_timestamp()")
            assert not connection._read_committed and connection._installed_timeout is None


@pytest.mark.parametrize("rollback", [False, True])
def test_begin_native_transaction_context_never_recertifies_ownership(rollback):
    class Synthetic(Exception): pass
    with cycle.cycle_budget(deadline=time.monotonic()+10), _native_begin_open() as connection:
        try:
            with connection.transaction():
                if rollback: raise Synthetic()
        except Synthetic: pass
        assert connection._reuse_disabled and not connection._read_committed
        with pytest.raises(RuntimeError, match="ownership_lost"):
            connection.configure_transaction_timeouts(3000, 1000, read_committed=True)


def test_begin_unknown_sql_revokes_native_contract_before_execution():
    with cycle.cycle_budget(deadline=time.monotonic()+10), _native_begin_open() as connection:
        with pytest.raises(RuntimeError, match="sql_contract_changed"):
            connection.execute("select set_config('transaction_isolation','serializable',true)")
        assert connection._reuse_disabled and not connection._read_committed
        assert connection._connection.execute("show transaction_isolation").fetchone() == ("read committed",)


@pytest.mark.parametrize("target", ["captured", "nested"])
def test_begin_configuration_checks_deadline_before_property_and_after_ack(monkeypatch, target):
    import psycopg
    raw = connect()
    original = psycopg.Connection.isolation_level
    writes = []
    def delayed(conn, value):
        writes.append(value)
        original.fset(conn, value)
        time.sleep(.08)
    monkeypatch.setattr(psycopg.Connection, "isolation_level", property(original.fget, delayed))
    try:
        limit = time.monotonic()+.04
        with cycle.cycle_budget(deadline=limit if target == "nested" else time.monotonic()+10):
            with pytest.raises(cycle.RootlineCycleDeadlineExceeded):
                bounded._install_native_read_committed(raw, limit if target == "captured" else time.monotonic()+10)
        assert writes == [psycopg.IsolationLevel.READ_COMMITTED]
        assert raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        writes.clear()
        with pytest.raises(cycle.RootlineCycleDeadlineExceeded):
            bounded._install_native_read_committed(raw, time.monotonic()-1)
        assert writes == []
    finally: raw.close()


@pytest.mark.parametrize("native_requested", [False, True])
@pytest.mark.parametrize("setup_fails", [False, True])
def test_begin_injected_acquisition_never_requires_driver_import_and_keeps_cleanup(
        monkeypatch, native_requested, setup_fails):
    import builtins
    original_import = builtins.__import__
    imports = []
    class Injected:
        closed = False
        rollbacks = 0
        statements = []
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, statement, params=None):
            self.statements.append(statement)
            if setup_fails: raise RuntimeError("synthetic injected setup failure")
        def fetchone(self): return ("3s", "1s", "read committed")
        def rollback(self): self.rollbacks += 1
        def close(self): self.closed = True
    client = Injected()
    def injected_import(name, *args, **kwargs):
        if name == "psycopg" or name.startswith("psycopg."):
            imports.append(name)
            raise ImportError("injected connector must not require psycopg")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", injected_import)
    def acquire():
        return bounded.connect_bounded_rootline_postgres(database_url="synthetic://injected",
            connect=lambda *_args, **_kwargs: client, read_only=False,
            reuse_local_settings=native_requested, read_committed=native_requested,
            native_begin_read_committed=native_requested)
    if setup_fails:
        with pytest.raises(RuntimeError, match="synthetic injected setup failure"):
            acquire()
        assert client.closed and client.rollbacks == 1
    else:
        assert acquire() is client
        assert not client.closed and client.rollbacks == 0
        client.close()
    assert imports == [] and client.statements
