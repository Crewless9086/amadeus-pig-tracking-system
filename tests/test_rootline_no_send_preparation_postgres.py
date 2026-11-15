"""No-send preparation through actual PostgreSQL, provider wrapper and controller rails."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest

from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.telemetry import rootline_cycle_budget as cycle
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry import rootline_ewelink_readback as readback
from modules.telemetry import rootline_ewelink_oauth as oauth
from modules.telemetry import rootline_irrigation_execution_store as executions
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport

DATABASE_URL = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="explicit disposable PostgreSQL URL required")


def connect():
    import psycopg
    return psycopg.connect(DATABASE_URL, connect_timeout=3,
        options="-c statement_timeout=3000 -c lock_timeout=1000")


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    if not DATABASE_URL:
        return
    target = urlparse(DATABASE_URL)
    assert target.hostname in {"127.0.0.1", "localhost"}
    assert re.fullmatch(r"/rootline_[a-z0-9_]+_test(?:_[0-9]{8})?", target.path)
    with connect() as connection:
        # Tests never create/change a global role or a second database.
        assert connection.execute("select count(*) from pg_roles where rolname in "
            "('anon','authenticated')").fetchone()[0] == 2
        connection.execute("create schema if not exists app_private")
        connection.execute("create table if not exists app_private.migration_log "
            "(migration_id text primary key,description text not null,"
            "applied_at timestamptz not null default now())")
        for migration in (
            "202607070001_create_sam_live_stock_conversation_review_events.sql",
            "202608060001_create_rootline_ewelink_oauth_vault.sql",
            "202608130001_serialize_rootline_ewelink_refresh.sql",
        ):
            connection.execute((Path("supabase/migrations") / migration).read_text())
        connection.execute("truncate public.sam_live_stock_conversation_review_events")
        connection.execute("truncate app_private.rootline_ewelink_oauth_tokens")
        connection.execute("truncate app_private.rootline_ewelink_account_binding")
        # Exact live INSERT guard, extracted unchanged from its canonical
        # migration. Only the function's referenced synthetic data is required.
        migration = Path("supabase/migrations/202607300001_create_litter_supersession_rail.sql").read_text()
        function = re.search(r"create or replace function public\.reject_superseded_pig_fact\(\).*?\$\$;",
            migration, re.S).group()
        body = function.split("$$", 2)[1]
        assert hashlib.md5(body.encode()).hexdigest() == "31b5a6e0055d758311b3ce911537b2d5"
        connection.execute("create table if not exists public.litter_cohort_dispositions (pig_id text primary key)")
        connection.execute("truncate public.litter_cohort_dispositions")
        connection.execute("insert into public.litter_cohort_dispositions(pig_id) "
            "select 'SYNTHETIC-SUPERSEDED-PIG-'||generate_series(1,100)")
        connection.execute(function)
        connection.execute("drop trigger if exists reject_superseded_pig_fact on "
            "public.sam_live_stock_conversation_review_events")
        connection.execute("create trigger reject_superseded_pig_fact before insert or update or delete on "
            "public.sam_live_stock_conversation_review_events for each row "
            "execute function public.reject_superseded_pig_fact()")
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    yield
    for worker in threading.enumerate():
        if worker.name in {"rootline-bounded-ewelink-read", "rootline-bounded-db-connect"}:
            worker.join(5)
    assert not [worker for worker in threading.enumerate()
        if worker.name in {"rootline-bounded-ewelink-read", "rootline-bounded-db-connect"}]


class Subject:
    def __init__(self, monkeypatch, *, expired=False):
        self.source = {"DATABASE_URL": DATABASE_URL, "EWELINK_CLIENT_ID": "synthetic-ns-app",
            "EWELINK_CLIENT_SECRET": "c"*40, "EWELINK_OAUTH_STATE_SECRET": "s"*40,
            "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc", "EWELINK_READBACK_ENABLED": "true"}
        self.tokens = PostgresOAuthTokenStore(DATABASE_URL)
        now = datetime.now(timezone.utc)
        account = oauth._digest("account")
        aad = f"eu|{account}|100204e9bc|{oauth.ADAPTER_VERSION}".encode()
        self.token = {"token_binding_id": "ROOTLINE-EWELINK-SYNTHETIC-NO-SEND",
            "provider_account_digest": account, "device_id": "100204e9bc", "region": "eu",
            "access_token_ciphertext": oauth._encrypt("synthetic-access", oauth._token_key(self.source), aad),
            "refresh_token_ciphertext": oauth._encrypt("synthetic-refresh", oauth._token_key(self.source), aad),
            "access_expires_at": now+timedelta(hours=-1 if expired else 1),
            "refresh_expires_at": now+timedelta(days=30), "response_digest": "a"*64,
            "adapter_version": oauth.ADAPTER_VERSION, "status_field_names": [], "created_at": now}
        assert self.tokens.append(self.token)
        self.client = budget.RequestBudget(self.source)
        identity = "SYNTHETIC-UNSENT-BOREHOLE"
        permit = self.client.reserve_for_on(execution_id=identity, device_id="1002851416",
            channel=1, device_type="borehole_pump_power", region="eu")
        now = datetime.now(timezone.utc)
        self.claim = {"execution_id": identity,
            "device_key": "ewelink:ewelink_owner_account:1002851416:1",
            "device_id": "1002851416", "channel": 1, "device_type": "borehole_pump_power",
            "provider_capacity_permit": permit, "claimed_at": now.isoformat(),
            "primary_stop_deadline": (now+timedelta(seconds=120)).isoformat(),
            "state": "claimed", "on_attempts": 0, "off_attempts": 0}
        self.client.begin_on(execution_id=identity, permit=permit, device_id="1002851416",
            channel=1, claimed_at=self.claim["claimed_at"],
            primary_stop_deadline=self.claim["primary_stop_deadline"])
        self.outcome = {**self.claim, "on_outcome": {"provider_command_attempted": False,
            "accepted_unambiguous": False, "status": "provider_command_deadline_reached"}}
        with connect() as connection, connection.cursor() as cursor:
            executions._insert_managed_event(cursor, "claim_borehole_before_on", self.claim)
            executions._insert_managed_event(cursor, "record_borehole_on_outcome", self.outcome)
            for attempt in (1, 2, 3):
                executions._insert_managed_event(cursor, "claim_borehole_off_attempt",
                    {"execution_id": identity, "attempt": attempt})
        params = {"fwVersion": "3.8.2", "switches": [
            {"outlet": i, "switch": "off"} for i in range(4)],
            "pulses": [{"outlet": 0, "pulse": "on", "width": 3600000}],
            "configure": [{"outlet": 0, "startup": "off"}], "timers": []}
        self.packets = {
            "/v2/user/refresh": {"at": "synthetic-rotated-access", "rt": "synthetic-rotated-refresh"},
            "/v2/family": {"currentFamilyId": "farm", "familyList": [{"id": "farm", "apikey": "account"}]},
            "/v2/device/thing": {"thingList": [{"itemType": 1, "itemData": {
                "deviceid": "1002851416", "apikey": "account", "productModel": "MINIR4",
                "extra": {"uiid": 138}, "online": True, "params": params}}]},
            "/v2/device/thing/status": {"params": {"switches": deepcopy(params["switches"])}},
        }
        self.calls, self.lock_observations, self.hooks = [], [], {}
        self.status_packets, self.status_reads = None, []
        self.status_device_id = "1002851416"
        subject = self
        class Response:
            def __init__(self, url, packet): self.url, self.packet = url, packet
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def geturl(self): return self.url
            def read(self, _): return json.dumps({"error": 0, "data": self.packet}).encode()
        class Opener:
            def open(self, request, timeout):
                path = urlparse(request.full_url).path
                assert path in subject.packets
                assert request.method == ("POST" if path == "/v2/user/refresh" else "GET")
                with connect() as observer:
                    free = observer.execute("select pg_try_advisory_xact_lock(1874320911),"
                        "pg_try_advisory_xact_lock(1874320912)").fetchone()
                subject.calls.append(path)
                subject.lock_observations.append((path, free))
                if path in subject.hooks:
                    subject.hooks[path]()
                packet = subject.packets[path]
                if path == "/v2/device/thing/status":
                    query = parse_qs(urlparse(request.full_url).query)
                    assert query.get("type") == ["1"] and len(query.get("id", [])) == 1
                    target = query["id"][0]
                    if subject.status_packets is None:
                        assert target == subject.status_device_id, "unknown synthetic STATUS target"
                    else:
                        assert target in subject.status_packets, "unknown synthetic STATUS target"
                        packet = subject.status_packets[target]
                    subject.status_reads.append((target, deepcopy(packet)))
                return Response(request.full_url, deepcopy(packet))
        monkeypatch.setattr(oauth.urllib.request, "build_opener", lambda *_: Opener())
        def no_commands(*_, **__): pytest.fail("No extra ON or exhausted OFF may be sent")
        self.transport = RootlineIFTTTTransport(token_store=self.tokens,
            environ=self.source, http_open=no_commands)

    def run(self):
        return coordinator._retire_unsent_execution(self.claim,
            executions.rootline_irrigation_execution_store,
            budget.bind_execution_transport(self.transport, self.claim))

    def rows(self):
        with connect() as connection, connection.cursor() as cursor:
            return executions._managed_edge_rows(cursor, self.claim["execution_id"])

    def ledger(self):
        with self.client._locked() as connection:
            return self.client._load(connection)

    def audit(self):
        with connect() as connection:
            return [row[0] for row in connection.execute("select review_json->'ewelink_request_budget' "
                "from public.sam_live_stock_conversation_review_events where event_source=%s "
                "order by created_at,review_event_id", (budget.EVENT_SOURCE,)).fetchall()]


def test_actual_prepared_retirement_keeps_fresh_status_locked_and_replays_without_io(monkeypatch):
    subject = Subject(monkeypatch)
    result = subject.run()
    assert result["status"] == "execution_not_dispatched", result
    assert result["hardware_commands"] == 0 and result["automatic_on_retry"] is False
    assert subject.lock_observations == [("/v2/family", (True, True)),
        ("/v2/device/thing", (True, True)), ("/v2/device/thing/status", (False, False))]
    rows = subject.rows()
    terminal = next(row for row in rows if row["action"] == "record_execution_not_dispatched")
    assert executions._verified_not_dispatched(terminal, rows)
    assert terminal["objective_satisfied"] is False
    assert set(terminal["shutdown_evidence"]) == {
        "authoritative", "state", "device_id", "channel", "evidence_id", "retrieved_at", "prepared_metadata"}
    provenance = terminal["shutdown_evidence"]["prepared_metadata"]
    assert provenance["online_from_fresh_status"] is False
    assert provenance["configuration_from_fresh_status"] is False
    assert provenance["metadata_received_at"] < terminal["shutdown_evidence"]["retrieved_at"]
    assert subject.claim["execution_id"] not in subject.ledger()["reserves"]
    attempts = [row for row in subject.audit() if row["action"] == "request_attempt_reserved"]
    assert len(attempts) == 3
    assert len({row["detail"]["group_id"] for row in attempts}) == 1
    assert all(row["detail"]["execution_id"] == subject.claim["execution_id"] for row in attempts)
    before = len(subject.calls)
    assert subject.run()["status"] == "execution_not_dispatched"
    assert len(subject.calls) == before
    assert len([row for row in subject.rows() if row["action"] == "record_execution_not_dispatched"]) == 1


def test_expired_access_uses_existing_refresh_before_locks_in_the_same_accounting_group(monkeypatch):
    subject = Subject(monkeypatch, expired=True)
    result = subject.run()
    assert result["status"] == "execution_not_dispatched", result
    assert subject.calls == ["/v2/user/refresh", "/v2/family", "/v2/device/thing", "/v2/device/thing/status"]
    assert subject.lock_observations[0][1] == subject.lock_observations[1][1] == (True, True)
    attempts = [row for row in subject.audit() if row["action"] == "request_attempt_reserved"]
    assert len(attempts) == 4 and len({row["detail"]["group_id"] for row in attempts}) == 1
    assert subject.tokens.latest()["token_binding_id"] != subject.token["token_binding_id"]
    assert subject.calls.count("/v2/user/refresh") == 1


@pytest.mark.parametrize("change", ["duplicate_outcome", "attempted", "active"])
def test_invalid_preliminary_preimage_makes_no_provider_or_token_read(monkeypatch, change):
    subject = Subject(monkeypatch)
    with connect() as connection, connection.cursor() as cursor:
        action = "mark_borehole_active" if change == "active" else "record_borehole_on_outcome"
        body = {**subject.outcome, "reason": "synthetic_conflict"}
        if change == "attempted": body["on_outcome"] = {"provider_command_attempted": True, "accepted_unambiguous": False}
        executions._insert_managed_event(cursor, action, body)
    monkeypatch.setattr(subject.tokens, "latest", lambda: pytest.fail("Invalid preimage must precede auth"))
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending"
    assert subject.calls == [] and result["no_send_stage"] == "preimage"


@pytest.mark.parametrize("change", ["active", "outcome", "token"])
def test_changed_preparation_preimage_or_token_abandons_metadata_charges_without_status(monkeypatch, change):
    subject = Subject(monkeypatch)
    def mutate():
        if change == "token":
            assert subject.tokens.append({**subject.token, "token_binding_id": "ROOTLINE-EWELINK-NEW"})
        else:
            with connect() as connection, connection.cursor() as cursor:
                executions._insert_managed_event(cursor,
                    "mark_borehole_active" if change == "active" else "record_borehole_on_outcome",
                    {**subject.outcome, "reason": "changed_during_preparation"})
    subject.hooks["/v2/family"] = mutate
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending", result
    assert subject.calls == ["/v2/family", "/v2/device/thing"]
    audit = subject.audit()
    assert sum(row["attempt_units"] for row in audit) == 2
    assert not any(row["action"] in {"snapshot_validation_failed", "complete_snapshot_restored_availability",
        "active_duty_off_verified"} for row in audit)
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())


@pytest.mark.parametrize("change", ["offline", "on", "wrong_device", "wrong_account"])
def test_fresh_in_lock_provider_proof_must_match_and_show_off(monkeypatch, change):
    subject = Subject(monkeypatch)
    device = subject.packets["/v2/device/thing"]["thingList"][0]["itemData"]
    if change == "offline": device["online"] = False
    elif change == "on": subject.packets["/v2/device/thing/status"] = {"params": {"switches": [
        {"outlet": i, "switch": "on" if i == 0 else "off"} for i in range(4)]}}
    elif change == "wrong_device": device["deviceid"] = "other"
    else: device["apikey"] = "other"
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending", result
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]


def test_final_canonical_delay_cannot_admit_a_new_terminal_after_read_deadline(monkeypatch):
    subject = Subject(monkeypatch)
    original = executions._managed_edge_rows
    calls = 0
    def delayed(cursor, identity):
        nonlocal calls
        if inspect.currentframe().f_back.f_code.co_name == "_retire_no_send_locked":
            calls += 1
            if calls == 2:  # second locked read is the final canonical revalidation
                deadline = cycle.work_deadline()
                assert deadline is not None
                time.sleep(max(0, deadline-time.monotonic())+.05)
        return original(cursor, identity)
    monkeypatch.setattr(executions, "_managed_edge_rows", delayed)
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending", result
    assert result["no_send_stage"] == "final_preimage"
    assert result["no_send_reason"] == "deadline"
    assert len(subject.calls) == 3
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())


def test_commit_ack_loss_preserves_terminal_unknown_without_cleanup_then_replays(monkeypatch):
    import psycopg
    subject = Subject(monkeypatch)
    original = bounded.connect_bounded_rootline_postgres
    class LostAck:
        def __init__(self, connection): self.connection = connection
        def __getattr__(self, key): return getattr(self.connection, key)
        def __enter__(self): self.connection.__enter__(); return self
        def __exit__(self, *args):
            self.connection.__exit__(*args)
            if args[0] is None: raise psycopg.OperationalError("synthetic lost terminal commit acknowledgement")
    def connect_wrapper(**kwargs):
        connection = original(**kwargs)
        if any(frame.function == "_retire_no_send_locked" for frame in inspect.stack()):
            return LostAck(connection)
        return connection
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", connect_wrapper)
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending" and result["effects_unknown"] is True
    assert result["writes_farm_data"] is None and result["no_send_stage"] == "terminal_commit"
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    rows = subject.rows()
    assert any(executions._verified_not_dispatched(row, rows) for row in rows)
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", original)
    before = len(subject.calls)
    assert subject.run()["status"] == "execution_not_dispatched"
    assert len(subject.calls) == before
    with subject.client._locked() as connection:
        state = subject.client._load(connection)
        subject.client._reconcile_reserves(connection, state, subject.client._now(connection))
    assert subject.claim["execution_id"] not in subject.ledger()["reserves"]


def test_nested_database_deadline_tightens_existing_connection_and_restores_parent():
    import psycopg
    with cycle.cycle_budget(deadline=time.monotonic()+2):
        with bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL) as connection:
            with cycle.cycle_budget(deadline=time.monotonic()+.05):
                assert connection.execute("select 1").fetchone()[0] == 1
            time.sleep(.06)
            assert connection.execute("select 2").fetchone()[0] == 2
    with pytest.raises(psycopg.errors.QueryCanceled):
        with cycle.cycle_budget(deadline=time.monotonic()+2):
            with bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL) as connection:
                with cycle.cycle_budget(deadline=time.monotonic()+.05):
                    connection.execute("select pg_sleep(.2)")


def test_token_query_wait_is_bounded_before_provider_preparation(monkeypatch):
    import psycopg
    subject = Subject(monkeypatch)
    with connect() as blocker:
        blocker.execute("lock table app_private.rootline_ewelink_oauth_tokens in access exclusive mode")
        began = time.monotonic()
        with pytest.raises((psycopg.errors.QueryCanceled, cycle.RootlineCycleDeadlineExceeded)):
            with cycle.cycle_budget(deadline=time.monotonic()+.15):
                subject.tokens.latest()
        assert time.monotonic()-began < 1
    assert subject.calls == []

@pytest.mark.parametrize("fault", ["intent_rollback", "intent_ack_lost", "completion_ack_lost",
    "completion_query_cancelled", "closed_between", "aborted_between"])
def test_worker_audit_client_faults_never_send_or_expose_unacknowledged_success(monkeypatch, fault):
    import psycopg
    subject = Subject(monkeypatch)
    original = budget.RequestBudget._connect
    clients = []
    class AuditClient:
        def __init__(self, connection):
            self.connection, self.commits = connection, 0
        def __getattr__(self, name): return getattr(self.connection, name)
        def commit(self):
            self.commits += 1
            if fault == "intent_rollback" and self.commits == 1:
                self.connection.rollback()
                raise psycopg.OperationalError("synthetic pre-commit failure")
            self.connection.commit()
            if (fault == "intent_ack_lost" and self.commits == 1 or
                    fault == "completion_ack_lost" and self.commits == 2):
                raise psycopg.OperationalError("synthetic acknowledgement loss")
        def execute(self, sql, *args, **kwargs):
            if fault == "completion_query_cancelled" and self.commits == 1:
                raw = getattr(self.connection, "connection", self.connection)
                raw.execute("set local statement_timeout='10ms'")
                raw.execute("select pg_sleep(.1)")
            return self.connection.execute(sql, *args, **kwargs)
    def factory(client):
        connection = original(client)
        session = budget._dispatch_audit.get()
        if session is not None and session.get("fence") is not None:
            connection = AuditClient(connection)
            clients.append(connection)
        return connection
    monkeypatch.setattr(budget.RequestBudget, "_connect", factory)
    def during_send():
        client = clients[-1]
        # The request intent must already be committed and visible elsewhere.
        assert client.commits == 1
        assert client.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        assert any(row["action"] == "request_attempt_reserved" for row in subject.audit())
        if fault == "closed_between": client.close()
        if fault == "aborted_between":
            with pytest.raises(psycopg.errors.DivisionByZero):
                client.execute("select 1/0")
    subject.hooks["/v2/family"] = during_send
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending", result
    assert len(subject.calls) == (0 if fault.startswith("intent_") else 1)
    assert clients and all(client.closed for client in clients)
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())
    events = subject.audit()
    assert sum(row["attempt_units"] for row in events) == (0 if fault == "intent_rollback" else 1)
    completions = [row for row in events if row["action"] == "request_completed"]
    assert len(completions) == (1 if fault == "completion_ack_lost" else 0)
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    assert budget._dispatch_audit.get() is None


def test_family_and_private_pair_use_separate_idle_audit_clients(monkeypatch):
    import psycopg
    subject = Subject(monkeypatch)
    original = budget.RequestBudget._connect
    clients, observations = [], []
    def factory(client):
        connection = original(client)
        session = budget._dispatch_audit.get()
        if session is not None and session.get("fence") is not None:
            # Scalar-only private instrumentation must not borrow the public
            # ConnectionInfo object, whose pgconn is a retained raw escape.
            native = getattr(connection, "_connection", connection)
            fence = session["fence"]
            fence_native = getattr(fence, "_connection", fence)
            assert native.info.backend_pid != fence_native.info.backend_pid
            clients.append(connection)
        return connection
    monkeypatch.setattr(budget.RequestBudget, "_connect", factory)
    def sent():
        session = budget._dispatch_audit.get()
        client = session["connection"]
        native = getattr(client, "_connection", client)
        assert native.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        observations.append((id(client), native.info.backend_pid, threading.get_ident()))
    for path in subject.packets:
        subject.hooks[path] = sent
    assert subject.run()["status"] == "execution_not_dispatched"
    assert len(clients) == 2
    assert len({row[0] for row in observations}) == 3
    assert all(client.closed for client in clients)
    assert len([r for r in subject.audit() if r["action"] == "request_completed"]) == 3


class FamilySubject(Subject):
    """Real registered target and matching canonical envelope for each family."""
    def __init__(self, monkeypatch, family, *, outcome=True, consume=True):
        from modules.telemetry.rootline_device_registry import get_device_contract
        super().__init__(monkeypatch)
        with connect() as connection:
            connection.execute("truncate public.sam_live_stock_conversation_review_events")
        identity = {"irrigation": "B12345", "mixer": "FERTILIZER-MIXER-CH2",
            "injector": "FERTILIZER-INJECTION-CH1", "borehole": "BOREHOLE-1-MINI-R4-CH1"}[family]
        contract = get_device_contract(identity)
        self.family, self.contract = family, contract
        self.status_device_id = contract["device_id"]
        self.claim_action = ("claim_before_on" if family == "irrigation" else
            "claim_borehole_before_on" if family == "borehole" else "claim_auxiliary_before_on")
        self.outcome_action = ("record_on_outcome" if family == "irrigation" else
            "record_borehole_on_outcome" if family == "borehole" else "record_auxiliary_on_outcome")
        now = datetime.now(timezone.utc)
        execution = "SYNTHETIC-NO-SEND-"+family.upper()
        permit = self.client.reserve_for_on(execution_id=execution,
            device_id=contract["device_id"], channel=contract["channel"],
            device_type=contract["device_type"], region="eu")
        self.claim = {"execution_id": execution, "device_id": contract["device_id"],
            "channel": contract["channel"], "device_type": contract["device_type"],
            "provider_capacity_permit": permit, "claimed_at": now.isoformat(),
            "primary_stop_deadline": (now+timedelta(seconds=120)).isoformat(),
            "native_fail_stop_deadline": (now+timedelta(seconds=contract["native_fail_stop_seconds"])).isoformat(),
            "state": "claimed", "on_attempts": 0, "off_attempts": 0}
        if family == "borehole":
            self.claim.update(device_key="ewelink:ewelink_owner_account:1002851416:1",
                maximum_duration_seconds=120)
        elif family == "irrigation":
            self.claim.update(zone_id=identity, planned_runtime_seconds=120,
                planned_runtime_minutes=2, commissioning_id=contract["commissioning_id"])
        else:
            self.claim.update(auxiliary_device_id=identity, maximum_duration_seconds=120,
                consumption_key=execution+":CONSUMPTION")
            if family == "injector":
                self.claim.update(zone_execution_id="SYNTHETIC-PARENT", zone_id="B12345",
                    job_id="ROOTLINE-IRRIGATION-JOB-SYNTHETIC", job_sha256="a"*64,
                    segment_identity="ROOTLINE-JOB-SEGMENT-SYNTHETIC", pulse_number=1)
        if consume:
            self.client.begin_on(execution_id=execution, permit=permit,
                device_id=contract["device_id"], channel=contract["channel"],
                claimed_at=self.claim["claimed_at"], primary_stop_deadline=self.claim["primary_stop_deadline"])
        self.outcome = {**self.claim, "on_attempts": 1, "on_outcome": {
            "provider_command_attempted": False, "accepted_unambiguous": False,
            "status": "provider_command_deadline_reached"}}
        with connect() as connection, connection.cursor() as cursor:
            executions._insert_managed_event(cursor, self.claim_action, self.claim)
            if outcome:
                executions._insert_managed_event(cursor, self.outcome_action, self.outcome)
        item = self.packets["/v2/device/thing"]["thingList"][0]["itemData"]
        item["deviceid"] = contract["device_id"]
        if family != "borehole":
            item["productModel"] = "4CHPROR3"
            item["extra"]["uiid"] = 126


def contrary_outcome(subject, kind="accepted"):
    native = {"accepted_unambiguous": True, "status": "accepted",
        "event": subject.contract["on_event"], "provider_status": 200}
    if kind == "ambiguous":
        native = {"accepted_unambiguous": False, "status": "provider_outcome_ambiguous"}
    elif kind == "duplicate_false":
        native = {"accepted_unambiguous": False, "provider_command_attempted": False,
            "status": "provider_capacity_not_available"}
    elif kind == "exact_replay":
        return deepcopy(subject.outcome)
    return {**subject.outcome, "on_outcome": native}


@pytest.mark.parametrize("family", ["irrigation", "mixer", "injector", "borehole"])
@pytest.mark.parametrize("kind", ["accepted", "ambiguous", "duplicate_false", "exact_replay"])
def test_each_outcome_writer_appends_during_locks_and_fresh_preimage_invalidates(monkeypatch, family, kind):
    subject = FamilySubject(monkeypatch, family)
    finished, outcomes, failures = threading.Event(), [], []
    incoming = contrary_outcome(subject, kind)
    def write():
        try: outcomes.append(executions.rootline_irrigation_execution_store(subject.outcome_action, incoming))
        except BaseException as exc: failures.append(type(exc).__name__)
        finally: finished.set()
    thread = threading.Thread(target=write, name="synthetic-outcome-writer")
    def during_status():
        thread.start()
        assert finished.wait(1), "append must not wait for the hardware read"
        time.sleep(1.4)
    subject.hooks["/v2/device/thing/status"] = during_status
    result = subject.run()
    thread.join(3)
    assert not thread.is_alive() and not failures and outcomes[0]["success"] is True, (outcomes, failures)
    rows = subject.rows()
    assert any(row["action"] == subject.outcome_action and row.get("on_outcome") == incoming["on_outcome"] for row in rows)
    terminals = [row for row in rows if row["action"] == "record_execution_not_dispatched"]
    if kind == "exact_replay":
        assert result["status"] == "execution_not_dispatched" and outcomes[0]["created"] is False
        assert len(terminals) == 1 and executions._verified_not_dispatched(terminals[0], rows)
        assert subject.claim["execution_id"] not in subject.ledger()["reserves"]
    else:
        assert result["status"] == "no_send_off_proof_pending", result
        assert not terminals and executions._no_send_preimage(rows, subject.claim["execution_id"]) is None
        assert subject.claim["execution_id"] in subject.ledger()["reserves"]


def test_token_expiring_inside_final_window_is_rejected_without_output_read(monkeypatch):
    subject = Subject(monkeypatch)
    assert subject.tokens.append({**subject.token, "token_binding_id": "ROOTLINE-EXPIRING",
        "access_expires_at": datetime.now(timezone.utc)+timedelta(seconds=6)})
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending"
    assert result["no_send_reason"] == "ewelink_prepared_token_expires_before_read"
    assert subject.calls == ["/v2/family", "/v2/device/thing"]


def test_two_expired_preparations_share_existing_refresh_cas(monkeypatch):
    subject = Subject(monkeypatch, expired=True)
    records = [subject.tokens.latest(), subject.tokens.latest()]
    results, errors = [], []
    barrier = threading.Barrier(2)
    def refresh(record):
        try:
            barrier.wait(2)
            with cycle.cycle_budget(deadline=time.monotonic()+5):
                results.append(readback._refresh_token_generation(record, token_store=subject.tokens,
                    source=subject.source, request=oauth._provider_request, now=datetime.now(timezone.utc)))
        except Exception as exc: errors.append(type(exc).__name__)
    workers = [threading.Thread(target=refresh, args=(record,)) for record in records]
    for worker in workers: worker.start()
    for worker in workers: worker.join(6)
    assert not errors and len(results) == 2, errors
    assert len({row["token_binding_id"] for row in results}) == 1
    assert subject.calls == ["/v2/user/refresh"]


def test_refresh_lost_commit_ack_recovers_without_second_provider_request(monkeypatch):
    import psycopg
    subject = Subject(monkeypatch, expired=True)
    original = subject.tokens._connect
    lost = False
    class LostAck:
        def __init__(self, connection): self.connection = connection
        def __getattr__(self, name): return getattr(self.connection, name)
        def __enter__(self): self.connection.__enter__(); return self
        def __exit__(self, *args):
            nonlocal lost
            self.connection.__exit__(*args)
            if args[0] is None and not lost:
                lost = True
                raise psycopg.OperationalError("synthetic refresh commit acknowledgement loss")
    def factory(**kwargs):
        connection = original(**kwargs)
        return connection if kwargs.get("read_only") or lost else LostAck(connection)
    monkeypatch.setattr(subject.tokens, "_connect", factory)
    result = subject.run()
    assert result["status"] == "execution_not_dispatched", result
    assert subject.calls.count("/v2/user/refresh") == 1 and lost



def test_contradictory_outcome_after_unlock_before_cleanup_retains_duty(monkeypatch):
    from modules.telemetry import rootline_ifttt_transport as transport_module
    subject = Subject(monkeypatch)
    original = transport_module._PreparedNoSendOutput.after_commit
    def after_unlock(prepared, terminal):
        with connect() as observer:
            assert observer.execute("select pg_try_advisory_xact_lock(1874320911),"
                "pg_try_advisory_xact_lock(1874320912)").fetchone() == (True, True)
        result = executions.rootline_irrigation_execution_store("record_borehole_on_outcome",
            {**subject.outcome, "on_outcome": {"provider_command_attempted": True,
                "accepted_unambiguous": True, "status": "late_committed_contradiction"}})
        assert result["success"] is True
        return original(prepared, terminal)
    monkeypatch.setattr(transport_module._PreparedNoSendOutput, "after_commit", after_unlock)
    result = subject.run()
    rows = subject.rows()
    terminal = next(row for row in rows if row["action"] == "record_execution_not_dispatched")
    assert not executions._verified_not_dispatched(terminal, rows)
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    assert result["cleanup_status"] == "retained_for_reconciliation"


def default_repeatable_read(monkeypatch):
    import psycopg
    original = psycopg.connect
    def connect_repeatable(*args, **kwargs):
        kwargs["options"] = kwargs.get("options", "")+" -c default_transaction_isolation=repeatable\\ read"
        return original(*args, **kwargs)
    monkeypatch.setattr(psycopg, "connect", connect_repeatable)


@pytest.mark.parametrize("family", ["irrigation", "mixer", "injector", "borehole"])
@pytest.mark.parametrize("prepared", [False, True])
def test_final_retirement_overrides_repeatable_default_and_sees_between_read_commit(monkeypatch, family, prepared):
    subject = FamilySubject(monkeypatch, family)
    default_repeatable_read(monkeypatch)
    original_rows = executions._managed_edge_rows
    isolation = []
    def rows(cursor, identity):
        if inspect.currentframe().f_back.f_code.co_name == "_retire_no_send_locked":
            cursor.execute("show transaction_isolation")
            isolation.append(cursor.fetchone()[0])
        return original_rows(cursor, identity)
    monkeypatch.setattr(executions, "_managed_edge_rows", rows)
    def contradict():
        assert executions.rootline_irrigation_execution_store(subject.outcome_action,
            contrary_outcome(subject))["success"] is True
    if prepared:
        subject.hooks["/v2/device/thing/status"] = contradict
        result = subject.run()
    else:
        def read_off():
            contradict()
            return {"authoritative": True, "state": "OFF", "device_id": subject.claim["device_id"],
                "channel": subject.claim["channel"], "evidence_id": "a"*64,
                "retrieved_at": datetime.now(timezone.utc).isoformat()}
        result = executions.rootline_irrigation_execution_store("retire_not_dispatched_execution",
            {"execution_id": subject.claim["execution_id"], "read_final_off": read_off})
    assert isolation == ["read committed", "read committed"]
    assert result["status"] == "no_send_off_proof_pending", result
    assert not any(r["action"] == "record_execution_not_dispatched" for r in subject.rows())
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]


@pytest.mark.parametrize("family", ["irrigation", "mixer", "injector", "borehole"])
@pytest.mark.parametrize("boundary", ["terminal_insert", "after_unlock", "cleanup_after_ledger"])
def test_late_canonical_contradiction_retains_duty_independent_of_historical_return(monkeypatch, family, boundary):
    from modules.telemetry import rootline_ifttt_transport as transport_module
    subject = FamilySubject(monkeypatch, family)
    default_repeatable_read(monkeypatch)
    committed, isolation = [], []
    def contradict():
        assert not committed
        assert executions.rootline_irrigation_execution_store(subject.outcome_action,
            contrary_outcome(subject))["success"] is True
        committed.append(True)
    if boundary == "terminal_insert":
        original = executions._insert_managed_event
        def insert(cursor, action, body):
            result = original(cursor, action, body)
            if action == "record_execution_not_dispatched":
                contradict()
            return result
        monkeypatch.setattr(executions, "_insert_managed_event", insert)
    elif boundary == "after_unlock":
        original = transport_module._PreparedNoSendOutput.after_commit
        def after_unlock(prepared, terminal):
            with connect() as observer:
                assert observer.execute("select pg_try_advisory_xact_lock(1874320911),"
                    "pg_try_advisory_xact_lock(1874320912)").fetchone() == (True, True)
            contradict()
            return original(prepared, terminal)
        monkeypatch.setattr(transport_module._PreparedNoSendOutput, "after_commit", after_unlock)
    else:
        original = budget.RequestBudget._terminal_rows
        def terminal_rows(client, connection, identities):
            if inspect.currentframe().f_back.f_code.co_name == "release_after_canonical_terminal":
                isolation.append(connection.execute("show transaction_isolation").fetchone()[0])
                contradict()
            return original(client, connection, identities)
        monkeypatch.setattr(budget.RequestBudget, "_terminal_rows", terminal_rows)
    result = subject.run()
    rows = subject.rows()
    terminals = [r for r in rows if r["action"] == "record_execution_not_dispatched"]
    assert committed and len(terminals) == 1
    assert not executions._verified_not_dispatched(terminals[0], rows)
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    # Existing response contract reports the earlier committed body. It is not
    # proof of present canonical validity or completed accounting cleanup.
    assert result["status"] == "execution_not_dispatched"
    assert result["cleanup_status"] == "retained_for_reconciliation"
    if boundary == "cleanup_after_ledger":
        assert isolation == ["read committed"]
    before = list(subject.calls)
    assert subject.run()["status"] == "no_send_off_proof_pending"
    assert subject.calls == before


def test_cleanup_rejects_borrowed_repeatable_snapshot_and_keeps_other_factory_defaults(monkeypatch):
    import psycopg
    subject = FamilySubject(monkeypatch, "borehole")
    default_repeatable_read(monkeypatch)
    raw = psycopg.connect(DATABASE_URL)
    raw.execute("select 1").fetchone()
    client = budget.RequestBudget(subject.source, connect_factory=lambda: raw)
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.release_after_canonical_terminal(subject.claim["execution_id"])
    assert raw.closed
    client = budget.RequestBudget(subject.source, connect_factory=lambda: psycopg.connect(DATABASE_URL))
    with client._locked() as connection:
        assert connection.execute("show transaction_isolation").fetchone()[0] == "repeatable read"
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("fault", ["set_failure", "false_isolation_ack"])
def test_initial_read_committed_setup_failure_closes_before_business_query(reuse, fault):
    import psycopg
    raw = connect()
    statements = []
    class Cursor:
        def __init__(self, cursor): self.raw, self.sql = cursor, ""
        def __enter__(self): self.raw.__enter__();return self
        def __exit__(self, *args): return self.raw.__exit__(*args)
        def execute(self, sql, params=None):
            self.sql = sql;statements.append(sql)
            if fault == "set_failure" and sql == "set transaction isolation level read committed":
                raise psycopg.errors.ActiveSqlTransaction("synthetic rejected isolation setup")
            return self.raw.execute(sql, params)
        def fetchone(self):
            value = self.raw.fetchone()
            if fault == "false_isolation_ack" and "current_setting('transaction_isolation')" in self.sql:
                return (*value[:-1], "repeatable read")
            return value
    class Connection:
        def cursor(self): return Cursor(raw.cursor())
        def __getattr__(self, name): return getattr(raw, name)
    with pytest.raises((psycopg.errors.ActiveSqlTransaction, RuntimeError)):
        bounded.connect_bounded_rootline_postgres(database_url=DATABASE_URL,
            connect=lambda *args, **kwargs: Connection(), read_only=False,
            reuse_local_settings=reuse, read_committed=True)
    assert raw.closed and statements[0] == "set transaction isolation level read committed"
    assert all(sql.startswith(("set ", "select set_config", "select current_setting")) for sql in statements)


def native_borehole_start(subject, monkeypatch, *, before_http=None, outcome="accepted", after_outcome=None):
    """Real caller/claim/permit/audit/token paths and native transport.

    HTTP wire and the existing canonical configuration-reference seam are
    synthetic. The selected fixture has its original 3599-second native bound;
    it is not evidence about live ten-hour commissioning or physical effects.
    """
    from tests.test_rootline_commissioning_bridges import pump_database
    from tests.test_rootline_borehole_commissioning import canonical
    from modules.telemetry.rootline_borehole_commissioning import (
        advance_borehole_execution, build_borehole_runtime_eligibility)
    subject.source.update(ROOTLINE_IFTTT_MAKER_KEY="synthetic-local-only",
        ROOTLINE_BOREHOLE_ENABLED="true")
    items = subject.packets["/v2/device/thing"]["thingList"]
    item = next((row["itemData"] for row in items if row["itemData"]["deviceid"] == "1002851416"), None)
    if item is None:
        item = deepcopy(items[0]["itemData"])
        item.update(deviceid="1002851416", productModel="MINIR4", extra={"uiid": 138})
        items.append({"itemType": 1, "itemData": item})
    # Independent raw STATUS for each device; metadata is never a live-output
    # fallback. A native borehole command cannot change irrigation's packet.
    subject.status_packets = {row["itemData"]["deviceid"]:
        deepcopy(subject.packets["/v2/device/thing/status"]) for row in items}
    item["params"]["pulses"] = [{"outlet": 0, "pulse": "on", "width": 3599000}]
    snapshot = oauth.normalize_device_readback(device=item,
        status={"params": {}}, retrieved_at=datetime.now(timezone.utc))
    # This established authority fixture supplies the unexposed configuration
    # reference separately. Do not add scene/interlock fields to provider JSON.
    configuration_database = pump_database(snapshot)
    registered = readback.read_registered_device
    def with_configuration_reference(device_id, **kwargs):
        if device_id == "1002851416":
            kwargs["commissioning_connect_factory"] = configuration_database
        return registered(device_id, **kwargs)
    monkeypatch.setattr(readback, "read_registered_device", with_configuration_reference)
    artifact = build_borehole_runtime_eligibility(need={"eligible": True},
        baseline={**canonical(native_fail_stop_seconds=3599), "registry_generation": 2},
        authority={"inside_standing_authority": True}, provider={"authoritative": True, "state": "OFF"},
        interlocks={"dry_run_safe": True, "low_water_clear": True,
            "supply_pressure_safe": True, "full_tank_not_blocking": True},
        energy={"eligible": True}, requested_seconds=60, now=datetime.now(timezone.utc))
    with connect() as connection, connection.cursor() as cursor:
        executions._insert_managed_event(cursor, "record_borehole_eligibility", artifact)
    calls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def getcode(self): return self.status
        def read(self, _): return b"synthetic provider acknowledgement"
    def wire(request, timeout):
        assert urlparse(request.full_url).hostname == "maker.ifttt.com" and request.method == "POST"
        data = json.loads(request.data)
        assert data["value2"] == "1002851416" and data["value3"] == "1"
        command = "ON" if data["value1"].endswith(":ON") else "OFF"
        calls.append((command, data["value1"]))
        if command == "ON" and before_http:
            before_http()
        item = next(row["itemData"] for row in subject.packets["/v2/device/thing"]["thingList"]
            if row["itemData"]["deviceid"] == "1002851416")
        item["params"]["switches"][0]["switch"] = command.lower()
        subject.status_packets["1002851416"]["params"]["switches"][0]["switch"] = command.lower()
        if outcome == "ambiguous" and command == "ON":
            raise TimeoutError("synthetic HTTP acknowledgement loss")
        if outcome == "missing" and command == "OFF":
            raise TimeoutError("synthetic OFF acknowledgement loss")
        return Response()
    subject.transport.http_open = wire
    def actual_store(action, body):
        if action == "record_borehole_on_outcome":
            if after_outcome:
                after_outcome(body)
            if outcome == "missing":
                raise executions.RootlineExecutionStoreUnavailable(action)
        return executions.rootline_irrigation_execution_store(action, body)
    def run(**kwargs):
        return advance_borehole_execution(eligibility=artifact, store=actual_store,
            transport=subject.transport, now=datetime.now(timezone.utc),
            clock=lambda: datetime.now(timezone.utc), **kwargs)
    return artifact, calls, run


@pytest.mark.parametrize("outcome", ["accepted", "ambiguous", "missing"])
def test_actual_native_caller_owns_one_claim_http_and_original_recovery_budget(monkeypatch, outcome):
    from modules.telemetry.rootline_borehole_commissioning import _contain_failed_borehole_start
    subject = Subject(monkeypatch)
    with connect() as connection:
        connection.execute("truncate public.sam_live_stock_conversation_review_events")
    entered, release = threading.Event(), threading.Event()
    results, errors = [], []
    def in_flight():
        entered.set()
        assert release.wait(10)
    artifact, calls, run = native_borehole_start(subject, monkeypatch, before_http=in_flight, outcome=outcome)
    def start():
        try: results.append(run())
        except BaseException as exc: errors.append(type(exc).__name__)
    worker = threading.Thread(target=start, name="synthetic-native-caller")
    worker.start()
    try:
        assert entered.wait(5), (results, errors, subject.calls)
        active = executions.rootline_irrigation_execution_store("load_active_borehole", None)
        identity = active["execution_id"]
        with connect() as connection, connection.cursor() as cursor:
            rows = executions._managed_edge_rows(cursor, identity)
        assert sum(r["action"] == "claim_borehole_before_on" for r in rows) == 1
        assert sum(r["action"] == "claim_borehole_dispatch" for r in rows) == 1
        assert not any(r["action"] == "record_borehole_on_outcome" for r in rows)
        assert executions._no_send_preimage(rows, identity) is None
        original_deadline = active["primary_stop_deadline"]
        subject.claim = active
        # The real caller never enters no-send recovery without an explicit
        # False outcome. Its claim gate keeps the in-flight native send owned.
        assert active.get("on_not_dispatched") is not True
        assert run()["status"] == "borehole_claim_in_progress"
        def forbidden_read(*_):
            pytest.fail("Missing native outcome must refuse before OFF preparation")
        refused = executions.rootline_irrigation_execution_store(
            "retire_not_dispatched_execution", {"execution_id": identity,
                "read_final_off": forbidden_read, "prepare_final_off": forbidden_read})
        assert refused["status"] == "no_send_preimage_unproven"
        assert [state for state, _ in calls] == ["ON"]
    finally:
        release.set()
        worker.join(15)
    assert not worker.is_alive()
    if outcome == "missing":
        assert errors == ["RootlineExecutionStoreUnavailable"] and not results
    else:
        assert not errors and results[0]["status"] == "borehole_started", (errors, results)
    with connect() as connection, connection.cursor() as cursor:
        rows = executions._managed_edge_rows(cursor, identity)
    actual_outcomes = [r for r in rows if r["action"] == "record_borehole_on_outcome"]
    assert len(actual_outcomes) == (0 if outcome == "missing" else 1)
    if actual_outcomes:
        assert "provider_command_attempted" not in actual_outcomes[0]["on_outcome"]
    assert executions._no_send_preimage(rows, identity) is None
    reserve = subject.ledger()["reserves"][identity]
    assert reserve["phase"] == "on_attempt"
    with pytest.raises(budget.RequestBudgetUnavailable):
        subject.client.begin_on(execution_id=identity, permit=reserve["permit"],
            device_id=reserve["device_id"], channel=reserve["channel"],
            claimed_at=active["claimed_at"], primary_stop_deadline=original_deadline)
    assert [state for state, _ in calls] == ["ON"]
    if outcome == "missing":
        # Exercise the existing restart/failed-start OFF rail directly, without
        # pretending thirty wall-clock seconds elapsed or inventing no-send.
        recovery = _contain_failed_borehole_start(active,
            executions.rootline_irrigation_execution_store,
            budget.bind_execution_transport(subject.transport, active))
        assert recovery["status"] == "borehole_start_aborted", recovery
        expected_off = 3
    else:
        recovery = run(stop_for_energy=True)
        assert recovery["status"] == "borehole_completed", recovery
        expected_off = 1
    assert recovery["execution"]["primary_stop_deadline"] == original_deadline
    assert [state for state, _ in calls] == ["ON"]+["OFF"]*expected_off
    assert len({key for _, key in calls}) == len(calls)
    before = list(calls)
    assert executions.rootline_irrigation_execution_store("dispatch_borehole_on_edge",
        {**active, "dispatch": lambda: pytest.fail("Consumed ON must never retry")})["accepted_unambiguous"] is False
    assert calls == before
    with connect() as connection, connection.cursor() as cursor:
        assert not any(r["action"] == "record_execution_not_dispatched"
            for r in executions._managed_edge_rows(cursor, identity))


def test_different_native_duty_outcome_survives_read_locks_and_old_cleanup_cannot_release_it(monkeypatch):
    subject = FamilySubject(monkeypatch, "irrigation")
    outcome_ready, release_outcome, appended = threading.Event(), threading.Event(), threading.Event()
    results, errors, concurrent_status = [], [], []
    def before_outcome(_body):
        outcome_ready.set()
        assert release_outcome.wait(10)
    artifact, calls, run = native_borehole_start(subject, monkeypatch, after_outcome=before_outcome)
    original_store = executions.rootline_irrigation_execution_store
    def observe_append(action, body):
        value = original_store(action, body)
        if action == "record_borehole_on_outcome" and value.get("success") is True:
            appended.set()
        return value
    monkeypatch.setattr(executions, "rootline_irrigation_execution_store", observe_append)
    def start():
        try: results.append(run())
        except BaseException as exc: errors.append(type(exc).__name__)
    worker = threading.Thread(target=start, name="synthetic-different-native-duty")
    worker.start()
    try:
        assert outcome_ready.wait(5), (results, errors, subject.calls)
        def during_status():
            release_outcome.set()
            assert appended.wait(1), "native result must be durable during unrelated equipment read"
            concurrent_status.append(deepcopy(subject.status_packets))
            time.sleep(1.4)
        subject.hooks["/v2/device/thing/status"] = during_status
        retired = subject.run()
    finally:
        release_outcome.set()
        worker.join(15)
    assert not worker.is_alive() and not errors and results
    assert retired["status"] == "execution_not_dispatched", retired
    assert subject.claim["device_id"] == "100204e9bc"
    assert {target for target, _ in subject.status_reads} == {"100204e9bc", "1002851416"}
    irrigation_status = [packet for target, packet in subject.status_reads if target == "100204e9bc"]
    borehole_status = [packet for target, packet in subject.status_reads if target == "1002851416"]
    assert irrigation_status and all(all(row["switch"] == "off" for row in packet["params"]["switches"])
        for packet in irrigation_status)
    assert borehole_status  # Includes the legitimate pre-ON OFF observation.
    # Concurrent fixture state is distinct from a returned post-ON observation.
    assert concurrent_status
    for statuses in concurrent_status:
        assert statuses["1002851416"]["params"]["switches"][0]["switch"] == "on"
        assert all(row["switch"] == "off" for row in statuses["100204e9bc"]["params"]["switches"])
    original_rows = subject.rows()
    assert any(executions._verified_not_dispatched(r, original_rows) for r in original_rows)
    state = subject.ledger()
    assert subject.claim["execution_id"] not in state["reserves"]
    assert artifact["execution_id"] in state["reserves"]
    assert state["reserves"][artifact["execution_id"]]["phase"] == "on_attempt"
    with connect() as connection, connection.cursor() as cursor:
        rows = executions._managed_edge_rows(cursor, artifact["execution_id"])
    actual = [r for r in rows if r["action"] == "record_borehole_on_outcome"]
    assert len(actual) == 1 and actual[0]["on_outcome"]["accepted_unambiguous"] is True
    assert "provider_command_attempted" not in actual[0]["on_outcome"]
    assert executions._no_send_preimage(rows, artifact["execution_id"]) is None
    assert [state for state, _ in calls] == ["ON"]
    assert run()["status"] == "borehole_claim_in_progress"
    assert [state for state, _ in calls] == ["ON"]


@pytest.mark.parametrize("field", ["source", "binding", "device", "baseline", "token", "group", "extended_deadline", "expired_metadata"])
def test_prepared_metadata_seal_and_original_deadline_refuse_before_status(monkeypatch, field):
    subject = Subject(monkeypatch)
    original = readback._PreparedNoSendRead.read_locked
    def mutate(prepared, **kwargs):
        if field == "source": prepared.source["EWELINK_CLIENT_ID"] = "changed"
        elif field == "binding": prepared.binding["channel"] = 2
        elif field == "device": prepared._device["online"] = False
        elif field == "baseline": prepared._baseline = {"changed": True}
        elif field == "token": prepared._record["token_binding_id"] = "changed"
        elif field == "group": prepared._group["id"] = "changed"
        elif field == "extended_deadline": prepared._group["deadline"] += 30
        else:
            prepared._metadata_deadline = time.monotonic()-1
            prepared._metadata_seal = prepared._seal()  # isolate the expiry check from seal tampering
        return original(prepared, **kwargs)
    monkeypatch.setattr(readback._PreparedNoSendRead, "read_locked", mutate)
    result = subject.run()
    assert result["status"] == "no_send_off_proof_pending"
    assert subject.calls == ["/v2/family", "/v2/device/thing"]
    assert not any(row["action"] == "record_execution_not_dispatched" for row in subject.rows())
    assert subject.claim["execution_id"] in subject.ledger()["reserves"]
    assert sum(row["attempt_units"] for row in subject.audit()) == 2
