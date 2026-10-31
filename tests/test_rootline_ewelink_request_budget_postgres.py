"""Real processes and transaction fences against an explicitly disposable DB."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import multiprocessing
import os
from pathlib import Path
import time
from urllib.parse import urlparse

import pytest

from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure

DATABASE_URL = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="explicit disposable PostgreSQL URL required")


def environment(url=DATABASE_URL):
    return {"DATABASE_URL": url, "EWELINK_CLIENT_ID": "synthetic-budget-app"}


@pytest.fixture(autouse=True)
def disposable(monkeypatch):
    if not DATABASE_URL:
        return
    target = urlparse(DATABASE_URL)
    assert target.hostname in {"127.0.0.1", "localhost"}
    assert target.path.endswith("_test") or target.path == "/rootline_managed"
    import psycopg
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql").read_text())
        connection.execute("truncate public.sam_live_stock_conversation_review_events")
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)


def ledger(client):
    with client._locked() as connection:
        return client._load(connection), client._counts(connection, client._now(connection))


def _dispatch_worker(url, ready, release, result):
    client = budget.RequestBudget(environment(url))
    ready.put(os.getpid())
    release.wait(10)
    deadline = time.monotonic()+12
    while time.monotonic() < deadline:
        try:
            def send(_timeout):
                started = time.monotonic()
                time.sleep(.04)
                return started
            value = client.dispatch(region="eu", endpoint="/v2/family", send=send)
            result.put({"sent": value, "pid": os.getpid()})
            return
        except budget.RequestBudgetUnavailable as exc:
            if "dispatch_busy" not in str(exc):
                result.put({"error": str(exc)})
                return
            time.sleep(.02)
    result.put({"error": "worker_deadline"})


def _reserve_worker(url, release, result, identity):
    budget.FIVE_MINUTE_LIMIT = 100
    release.wait(10)
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        try:
            permit = budget.RequestBudget(environment(url)).reserve_for_on(
                execution_id=identity, device_id="100204d497", channel=1,
                device_type="fertilizer_injection_valve", region="eu")
            result.put({"reserved": bool(permit)})
            return
        except budget.RequestBudgetUnavailable as exc:
            if "dispatch_busy" not in str(exc):
                result.put({"error": str(exc)})
                return
            time.sleep(.02)


def _crash_after_intent_worker(url):
    class CrashingBudget(budget.RequestBudget):
        def _append(self, state, **kwargs):
            super()._append(state, **kwargs)
            if kwargs["action"] == "request_attempt_reserved":
                os._exit(73)
    client = CrashingBudget(environment(url))
    client.dispatch(region="eu", endpoint="/v2/family", send=lambda _: os._exit(99))


def test_actual_multiprocess_send_spacing_and_committed_attempts():
    context = multiprocessing.get_context("spawn")
    ready, result, release = context.Queue(), context.Queue(), context.Event()
    workers = [context.Process(target=_dispatch_worker, args=(DATABASE_URL, ready, release, result))
        for _ in range(3)]
    for worker in workers:
        worker.start()
    for _ in workers:
        ready.get(timeout=15)
    release.set()
    outputs = [result.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(5)
        assert worker.exitcode == 0
    assert all("sent" in row for row in outputs), outputs
    starts = sorted(row["sent"] for row in outputs)
    assert all(b-a >= 1 for a, b in zip(starts, starts[1:])), starts
    state, counts = ledger(budget.RequestBudget(environment()))
    assert counts == (3, 3) and state["pending_attempt"] is None
    assert state["provider_remaining"] == "Unknown"


def test_actual_multiprocess_reservation_admission_is_atomic():
    context = multiprocessing.get_context("spawn")
    result, release = context.Queue(), context.Event()
    workers = [context.Process(target=_reserve_worker, args=(DATABASE_URL, release, result, "EXEC-"+str(n)))
        for n in range(2)]
    for worker in workers:
        worker.start()
    release.set()
    outputs = [result.get(timeout=15) for _ in workers]
    for worker in workers:
        worker.join(5)
        assert worker.exitcode == 0
    assert sum(row.get("reserved") is True for row in outputs) == 1, outputs
    state, counts = ledger(budget.RequestBudget(environment()))
    assert len(state["reserves"]) == 1 and counts == (0, 0)


def test_actual_process_death_preserves_intent_count_before_provider_send():
    context = multiprocessing.get_context("spawn")
    worker = context.Process(target=_crash_after_intent_worker, args=(DATABASE_URL,))
    worker.start(); worker.join(15)
    assert worker.exitcode == 73
    state, counts = ledger(budget.RequestBudget(environment()))
    assert counts == (1, 1) and state["pending_attempt"] is not None
    with pytest.raises(budget.RequestBudgetUnavailable, match="prior_attempt_unresolved"):
        budget.RequestBudget(environment()).dispatch(region="eu", endpoint="/v2/family",
            send=lambda _: pytest.fail("Unresolved attempt must not be retried"))


def test_send_fence_retains_transaction_backend_across_separate_audit_commit():
    import psycopg
    client = budget.RequestBudget(environment())
    seen = []
    def send(_timeout):
        with psycopg.connect(DATABASE_URL) as other:
            held = other.execute("select pg_try_advisory_xact_lock(%s)", (budget.GLOBAL_SEND_LOCK,)).fetchone()[0]
            count = other.execute("""select count(*) from public.sam_live_stock_conversation_review_events
                where event_source=%s and review_json->'ewelink_request_budget'->>'action'='request_attempt_reserved'""",
                (budget.EVENT_SOURCE,)).fetchone()[0]
            seen.append((held, count))
        return {}
    client.dispatch(region="eu", endpoint="/v2/family", send=send)
    assert seen == [(False, 1)]
    with psycopg.connect(DATABASE_URL) as other:
        assert other.execute("select pg_try_advisory_xact_lock(%s)", (budget.GLOBAL_SEND_LOCK,)).fetchone()[0]


def test_quota_hold_uses_durable_app_scope_and_complete_probe_after_restart():
    client = budget.RequestBudget(environment())
    def fail(_):
        raise OAuthFailure("sanitized", provider_failure=budget.classify_failure(provider_code=412))
    with pytest.raises(OAuthFailure):
        with budget.snapshot_group(expected_device="100204e9bc", environ=environment(), region="eu"):
            client.dispatch(region="eu", endpoint="/v2/family", send=fail)
    restarted = budget.RequestBudget(environment())
    with pytest.raises(budget.RequestBudgetUnavailable, match="application_call_limit_hold"):
        restarted.dispatch(region="us", endpoint="/v2/family", send=lambda _: pytest.fail("held"))
    with restarted._locked() as connection:
        state = restarted._load(connection)
        state["scopes"][budget.scope_digest(environment(), "us")]["next_probe_at"] = (
            restarted._now(connection)-timedelta(seconds=1)).isoformat()
        restarted._append(state, action="synthetic_test_advance_probe_due")
    with budget.snapshot_group(expected_device="100204e9bc", environ=environment(), region="us") as group:
        for endpoint in ("/v2/family", "/v2/device/thing", "/v2/device/thing/status"):
            restarted.dispatch(region="us", endpoint=endpoint, send=lambda _: {})
        group["normalized_complete"] = True
    state, counts = ledger(restarted)
    assert state["scopes"][budget.scope_digest(environment(), "eu")]["category"] is None
    assert counts[0] == 4 and state["provider_remaining"] == "Unknown"


def insert_no_send_pair(*, device="FERTILIZER-INJECTION-CH1", outcome=None, permit="p"*32):
    import psycopg
    now = datetime.now(timezone.utc)
    claim = {"execution_id": "EXEC-UNSENT", "auxiliary_device_id": device,
        "device_id": "100204d497", "channel": 1, "device_type": "fertilizer_injection_valve",
        "provider_capacity_permit": permit, "claimed_at": now.isoformat(),
        "primary_stop_deadline": (now+timedelta(seconds=120)).isoformat(),
        "maximum_duration_seconds": 120, "state": "claimed", "on_attempts": 0,
        "consumption_key": "NO-SEND-CONSUME", "zone_execution_id": "PARENT",
        "zone_id": "B12345", "job_id": "ROOTLINE-IRRIGATION-JOB-"+"A"*24,
        "job_sha256": "a"*64, "segment_identity": "ROOTLINE-JOB-SEGMENT-"+"B"*24,
        "pulse_number": 1}
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        store._insert_managed_event(cursor, "claim_auxiliary_before_on", claim)
        store._insert_managed_event(cursor, "record_auxiliary_on_outcome", {**claim,
            "on_outcome": outcome or {"provider_command_attempted": False, "accepted_unambiguous": False}})
    return claim


def fresh_off():
    return {"authoritative": True, "state": "OFF", "device_id": "100204d497", "channel": 1,
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "evidence_id": "a"*64}


def test_proven_no_send_retirement_requires_exact_fresh_locked_off_and_keeps_history():
    import psycopg
    claim = insert_no_send_pair()
    active = store.rootline_irrigation_execution_store("load_active_auxiliary", "FERTILIZER-INJECTION-CH1")
    assert active["on_not_dispatched"] is True
    def read():
        with psycopg.connect(DATABASE_URL) as connection:
            assert not connection.execute("select pg_try_advisory_xact_lock(%s)", (1874320911,)).fetchone()[0]
            assert not connection.execute("select pg_try_advisory_xact_lock(%s)", (1874320912,)).fetchone()[0]
        return fresh_off()
    result = store.rootline_irrigation_execution_store("retire_not_dispatched_execution", {**claim, "read_final_off": read})
    assert result["success"] and result["created"], result
    assert result["execution"]["not_dispatched_verified"] is True
    assert store.rootline_irrigation_execution_store("load_active_auxiliary", "FERTILIZER-INJECTION-CH1") is None
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        events = store._managed_edge_rows(cursor, claim["execution_id"])
        assert len(events) == 3
        assert store._not_dispatched_ids(cursor) == [claim["execution_id"]]
        terminal = next(row for row in events if row["action"] == "record_execution_not_dispatched")
        for change in ({"claim_sha256": "f"*64}, {"outcome_sha256": "f"*64},
                {"shutdown_evidence": {**fresh_off(), "state": "ON"}}):
            assert not store._verified_not_dispatched({**terminal, **change}, events)


@pytest.mark.parametrize("outcome", [
    {"accepted_unambiguous": False},
    {"provider_command_attempted": True, "accepted_unambiguous": False},
    {"provider_command_attempted": False, "accepted_unambiguous": True}])
def test_ambiguous_or_attempted_on_cannot_be_retired_as_unsent(outcome):
    claim = insert_no_send_pair(outcome=outcome)
    result = store.rootline_irrigation_execution_store("retire_not_dispatched_execution", {
        **claim, "read_final_off": lambda: pytest.fail("Invalid preimage must fail before read")})
    assert result["success"] is False
    assert store.rootline_irrigation_execution_store("load_active_auxiliary", "FERTILIZER-INJECTION-CH1") is not None


def test_stale_off_or_new_active_evidence_cannot_refund_unsent_execution():
    import psycopg
    claim = insert_no_send_pair()
    result = store.rootline_irrigation_execution_store("retire_not_dispatched_execution", {**claim,
        "read_final_off": lambda: {**fresh_off(), "retrieved_at": claim["claimed_at"]}})
    assert result["success"] is False
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        store._insert_managed_event(cursor, "mark_auxiliary_active", {**claim, "state": "Active"})
    result = store.rootline_irrigation_execution_store("retire_not_dispatched_execution", {
        **claim, "read_final_off": lambda: pytest.fail("Active proof forbids no-send retirement")})
    assert result["success"] is False


def test_terminated_send_transaction_cannot_use_its_committed_intent():
    import psycopg
    class LostFence(budget.RequestBudget):
        def _now(self, connection):
            self.connection = connection
            return super()._now(connection)
        def _append(self, state, **kwargs):
            # Save the outer fence identity before _append uses its audit DB.
            pid = self.connection.info.backend_pid
            super()._append(state, **kwargs)
            if kwargs["action"] == "request_attempt_reserved":
                with psycopg.connect(DATABASE_URL) as other:
                    assert other.execute("select pg_terminate_backend(%s)", (pid,)).fetchone()[0]
    client = LostFence(environment())
    sent = []
    with pytest.raises(budget.RequestBudgetUnavailable):
        client.dispatch(region="eu", endpoint="/v2/family", send=lambda _:sent.append(1))
    assert not sent
    state, counts = ledger(budget.RequestBudget(environment()))
    assert counts == (1,1) and state["pending_attempt"] is not None


def test_real_manager_initial_claim_and_fresh_readiness_refresh_are_not_starved(monkeypatch):
    import psycopg
    import uuid
    from types import SimpleNamespace
    from modules.oom_sakkie import general_manager_worker as manager
    from modules.oom_sakkie import manager_case_sources
    from modules.telemetry import rootline_mixer_readiness_observer as observer
    from tests.test_oom_sakkie_general_manager_postgres import _IsolatedConnection
    from tests.test_rootline_mixer_readiness_observer import provider
    owner = SimpleNamespace(schema="budget_manager_"+uuid.uuid4().hex, statements=0)
    def connect():
        return _IsolatedConnection(psycopg.connect(DATABASE_URL), owner)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("create schema "+owner.schema)
        for role in ("anon", "authenticated"):
            if not connection.execute("select 1 from pg_roles where rolname=%s", (role,)).fetchone():
                connection.execute("create role "+role+" nologin")
    try:
        with connect() as connection:
            connection.execute("create table app_private.migration_log(migration_id text primary key,description text not null)")
            connection.execute("create table app_private.oom_protected_action_claims(callback_token text primary key,action_kind text not null,provider_message_id text,status text,result_payload jsonb,completed_at timestamptz)")
            for name in ("202608170002_create_oom_manager_case_runtime.sql", "202608190002_create_beacon_protected_publication_consumer.sql"):
                connection.execute((Path("supabase/migrations")/name).read_text(encoding="utf-8"))
        client = budget.RequestBudget(environment())
        current = [datetime.now(timezone.utc)]
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return current[0]
        monkeypatch.setattr(manager, "datetime", Clock)
        monkeypatch.setattr(manager_case_sources, "collect_manager_candidates", lambda **_: [])
        monkeypatch.setattr(manager, "build_scheduled_brain_guard_audit", lambda **_: {"passed":True})
        reads = []
        def read(device, **kwargs):
            with budget.snapshot_group(expected_device=device, environ=environment(), region="eu") as group:
                for endpoint in ("/v2/family", "/v2/device/thing", "/v2/device/thing/status"):
                    client.dispatch(region="eu", endpoint=endpoint, send=lambda _: {})
                group["normalized_complete"] = True
            reads.append(group["optional_purpose"])
            result = provider(device, now=kwargs["now"])
            result["channels"][1]["native_auto_off_enabled"] = False
            return result
        original = observer.collect_mixer_readiness
        def collect(**kwargs):
            return original(**kwargs, token_store=object(), readback=read, execution_store=lambda *a: None)
        monkeypatch.setattr(observer, "collect_mixer_readiness", collect)
        manager_store = manager.PostgresManagerCaseStore(connect_factory=connect)
        # First natural collection creates a case; its normal five-minute due
        # time follows. The next cycle's initial collector is suppressed, while
        # its independent fresh refresh admits a complete new snapshot.
        first = manager.run_general_manager_cycle(now=current[0], source_revision="synthetic-local",
            store=manager_store, deliver=lambda case, **_: manager.deliver_farm_manager_case(case))
        assert first["success"] is True
        current[0] += timedelta(minutes=5)
        second = manager.run_general_manager_cycle(now=current[0], source_revision="synthetic-local",
            store=manager_store, deliver=lambda case, **_: manager.deliver_farm_manager_case(case))
        assert second["success"] is True, second
        assert reads == ["mixer_readiness", "mixer_readiness_delivery"]
        assert any(row["outcome_status"] == "readiness_attention_only" for row in second["case_results"]), second
        current[0] += timedelta(minutes=5)
        third = manager.run_general_manager_cycle(now=current[0], source_revision="synthetic-local",
            store=manager_store, deliver=lambda case, **_: manager.deliver_farm_manager_case(case))
        assert third["success"] is True, third
        assert any(row["outcome_status"] == "manager_optional_observation_deferred" for row in third["case_results"])
        with connect() as connection:
            row = connection.execute("select status,assigned_worker_id,lease_until from app_private.oom_manager_cases").fetchone()
            assert row == ("waiting_reassessment", None, None)
        assert ledger(client)[1][0] == 6
    finally:
        assert owner.schema.startswith("budget_manager_") and len(owner.schema) == 47
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("drop schema "+owner.schema+" cascade")


def _insert_canonical(action, body):
    import psycopg
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        result = store._insert_managed_event(cursor, action, body)
        return connection.execute("select review_json->'rootline_execution' from public.sam_live_stock_conversation_review_events where review_event_id=%s", (result["event_id"],)).fetchone()[0]


def _off_transport(device, channel):
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    def read(**_):
        # Model nonzero response latency so the Windows application clock has
        # advanced past PostgreSQL's more precise protected-read start. No
        # clock tolerance is introduced into the canonical verifier.
        time.sleep(.02)
        return {"device_id":device,"channels":[{"channel":item,"output_state":"OFF"}
            for item in ([1] if device=="1002851416" else [1,2,3,4])],
            "provider_control_calls":0,"current_outputs_authoritative":True,"response_digest":"a"*64,
            "retrieved_at":datetime.now(timezone.utc).isoformat()}
    return RootlineIFTTTTransport(token_store=object(),environ=environment(),readback=read,
        http_open=lambda *_args,**_kw:pytest.fail("No equipment or provider request authorized"))


def _terminal_case(kind, *, control_only=False):
    client=budget.RequestBudget(environment())
    parent=kind=="irrigation_zone_valve"; borehole=kind=="borehole_pump_power"
    device,channel=(("100204e9bc",1) if parent else ("1002851416",1) if borehole else
        ("100204d497",2 if kind=="fertilizer_mixer" else 1))
    identity="MISSED-CLEANUP-"+kind
    permit=client.reserve_for_on(execution_id=identity,device_id=device,channel=channel,
        device_type=kind,region="eu")
    now=datetime.now(timezone.utc)
    claim={"execution_id":identity,"device_id":device,"channel":channel,"device_type":kind,
        "provider_capacity_permit":permit,"claimed_at":now.isoformat(),
        "primary_stop_deadline":(now+timedelta(seconds=600)).isoformat(),
        "maximum_duration_seconds":600,"state":"claimed","on_attempts":0,"off_attempts":0}
    if not parent and not borehole:
        claim["auxiliary_device_id"]="FERTILIZER-MIXER-CH2" if channel==2 else "FERTILIZER-INJECTION-CH1"
    claim_action="claim_before_on" if parent else "claim_borehole_before_on" if borehole else "claim_auxiliary_before_on"
    _insert_canonical(claim_action,claim)
    client.begin_on(execution_id=identity,permit=permit,device_id=device,channel=channel)
    predecessor=_insert_canonical("mark_active" if parent else "mark_borehole_active" if borehole else
        "mark_auxiliary_active",{**claim,"state":"Active","on_attempts":1})
    if parent:
        predecessor=_insert_canonical("mark_stopping",{**predecessor,"state":"stopping"})
    transport=_off_transport(device,channel)
    return client,claim,predecessor,transport


@pytest.mark.parametrize("kind,control_only",[("irrigation_zone_valve",False),
    ("fertilizer_mixer",False),("fertilizer_injection_valve",False),
    ("fertilizer_injection_valve",True),("borehole_pump_power",False)])
def test_failed_off_cleanup_then_canonical_completion_and_restart_releases_only_old_duty(kind,control_only):
    import psycopg
    client,claim,predecessor,transport=_terminal_case(kind,control_only=control_only)
    identity=claim["execution_id"];device=claim["device_id"];channel=claim["channel"]
    with psycopg.connect(DATABASE_URL) as blocker:
        blocker.execute("select pg_advisory_xact_lock(%s)",(budget.GLOBAL_SEND_LOCK,))
        with budget.execution_duty(claim):
            proof=transport.read_output_state(device_id=device,channel=channel)
        assert proof["authoritative"] and proof["state"]=="OFF"
        assert identity in client._load(blocker)["reserves"]  # Cleanup really lost the fence.
        terminal={**predecessor,"state":"ControlPulseStopped" if control_only else "Completed",
            "shutdown_verified":True,"shutdown_evidence":proof,
            "completed_at":datetime.now(timezone.utc).isoformat(),
            "physical_outcome":"Unmeasured","objective_satisfied":False}
        action="record_auxiliary_control_pulse_stopped" if control_only else "record_auxiliary_completed"
        if kind=="irrigation_zone_valve": action="record_completed"
        if kind=="borehole_pump_power":
            action="record_borehole_completed"
            terminal.update(action=action,operational_proof="provider_app_on_to_off",
                provider_start_evidence={"authoritative":True,"state":"ON"},
                provider_final_off_evidence={**proof,"execution_id":identity},
                canonical_completion_evidence={"execution_id":identity,"final_state":"OFF","evidence_id":"CANONICAL-OFF"})
        stored=_insert_canonical(action,terminal)
    with psycopg.connect(DATABASE_URL) as connection:
        before=connection.execute("select review_event_id,review_json from public.sam_live_stock_conversation_review_events where event_source=%s order by review_event_id",(store.EVENT_SOURCE,)).fetchall()
    restarted=budget.RequestBudget(environment())
    new=restarted.reserve_for_on(execution_id="LATER-SAME-OUTPUT",device_id=device,channel=channel,
        device_type=kind,region="eu")
    restarted.begin_on(execution_id="LATER-SAME-OUTPUT",permit=new,device_id=device,channel=channel)
    restarted.dispatch(region="eu",endpoint="/v2/family",send=lambda _: {})
    state,_=ledger(restarted)
    assert identity not in state["reserves"] and "LATER-SAME-OUTPUT" in state["reserves"]
    with psycopg.connect(DATABASE_URL) as connection:
        after=connection.execute("select review_event_id,review_json from public.sam_live_stock_conversation_review_events where event_source=%s order by review_event_id",(store.EVENT_SOURCE,)).fetchall()
    assert before==after and stored["physical_outcome"]=="Unmeasured" and stored["objective_satisfied"] is False


def test_real_locked_no_send_transaction_time_reconciles_after_missed_off_cleanup():
    import psycopg
    client=budget.RequestBudget(environment())
    permit=client.reserve_for_on(execution_id="EXEC-UNSENT",device_id="100204d497",channel=1,
        device_type="fertilizer_injection_valve",region="eu")
    claim=insert_no_send_pair(permit=permit)
    client.begin_on(execution_id=claim["execution_id"],permit=permit,device_id=claim["device_id"],channel=1)
    transport=_off_transport(claim["device_id"],1)
    with psycopg.connect(DATABASE_URL) as blocker:
        blocker.execute("select pg_advisory_xact_lock(%s)",(budget.GLOBAL_SEND_LOCK,))
        result=store.rootline_irrigation_execution_store("retire_not_dispatched_execution",{**claim,
            "read_final_off":lambda:transport.read_output_state(device_id=claim["device_id"],channel=1)})
        assert result["success"] and result["created"], result
        assert claim["execution_id"] in client._load(blocker)["reserves"]
    terminal=result["execution"]
    with psycopg.connect(DATABASE_URL) as connection:
        recorded=connection.execute("select created_at from public.sam_live_stock_conversation_review_events where review_event_id=%s",(terminal["event_id"],)).fetchone()[0]
    assert recorded < datetime.fromisoformat(terminal["shutdown_evidence"]["retrieved_at"])
    restarted=budget.RequestBudget(environment())
    restarted.dispatch(region="eu",endpoint="/v2/family",send=lambda _: {})
    assert not ledger(restarted)[0]["reserves"]


def test_real_locked_borehole_abort_transaction_time_reconciles_exact_failed_start():
    import psycopg
    from tests.test_rootline_managed_startup_handover_postgres import borehole_start_artifact
    client=budget.RequestBudget(environment())
    artifact=borehole_start_artifact(datetime.now(timezone.utc))
    identity=artifact["execution_id"]
    permit=client.reserve_for_on(execution_id=identity,device_id="1002851416",channel=1,
        device_type="borehole_pump_power",region="eu")
    now=datetime.now(timezone.utc)
    claim={**artifact,"provider_capacity_permit":permit,"claimed_at":now.isoformat(),
        "primary_stop_deadline":(now+timedelta(seconds=60)).isoformat(),
        "native_fail_stop_deadline":(now+timedelta(seconds=1800)).isoformat(),
        "state":"claimed","on_attempts":0,"off_attempts":0}
    assert store.rootline_irrigation_execution_store("record_borehole_eligibility",artifact)["success"]
    assert store.rootline_irrigation_execution_store("claim_borehole_before_on",claim)["created"]
    client.begin_on(execution_id=identity,permit=permit,device_id="1002851416",channel=1)
    assert store.rootline_irrigation_execution_store("claim_borehole_off_attempt",{"execution_id":identity,"attempt":1})["created"]
    transport=_off_transport("1002851416",1)
    with psycopg.connect(DATABASE_URL) as blocker:
        blocker.execute("select pg_advisory_xact_lock(%s)",(budget.GLOBAL_SEND_LOCK,))
        with budget.execution_duty(claim):
            result=store.rootline_irrigation_execution_store("record_borehole_aborted",{**claim,
                "read_final_off":lambda:transport.read_output_state(device_id="1002851416",channel=1)})
        assert result["success"] and result["created"], result
        assert identity in client._load(blocker)["reserves"]
    terminal=result["execution"]
    with psycopg.connect(DATABASE_URL) as connection:
        recorded=connection.execute("select created_at from public.sam_live_stock_conversation_review_events where review_event_id=%s",(terminal["event_id"],)).fetchone()[0]
    assert recorded < datetime.fromisoformat(terminal["provider_final_off_evidence"]["retrieved_at"])
    restarted=budget.RequestBudget(environment())
    restarted.dispatch(region="eu",endpoint="/v2/family",send=lambda _: {})
    assert not ledger(restarted)[0]["reserves"] and terminal["objective_satisfied"] is False


@pytest.mark.parametrize("defect",["duplicate_terminal","later_active","later_unknown_shutdown","wrong_output","forged_matching_identity"])
def test_real_canonical_query_retains_conflicting_or_forged_duty(defect):
    import psycopg
    from psycopg.types.json import Jsonb
    client,claim,predecessor,transport=_terminal_case("fertilizer_mixer")
    proof=transport.read_output_state(device_id=claim["device_id"],channel=claim["channel"])
    terminal={**predecessor,"state":"Completed","shutdown_verified":True,"shutdown_evidence":proof,
        "completed_at":datetime.now(timezone.utc).isoformat()}
    if defect=="wrong_output":terminal["shutdown_evidence"]={**proof,"channel":1}
    stored=(store._stored_event_body("record_auxiliary_completed",terminal,"ROOTLINE-EXEC-"+"F"*32)
        if defect=="forged_matching_identity" else _insert_canonical("record_auxiliary_completed",terminal))
    if defect=="duplicate_terminal":
        _insert_canonical("record_auxiliary_completed",{**terminal,"completed_at":datetime.now(timezone.utc).isoformat()})
    elif defect in {"later_active","later_unknown_shutdown"}:
        _insert_canonical("mark_auxiliary_active" if defect=="later_active" else "contain_auxiliary_device",
            {**predecessor,"shutdown_verified":False,"reason":"later-contradiction"})
    elif defect=="forged_matching_identity":
        # Forge both self-described and outer identities; matching alone must
        # never replace the canonical deterministic writer contract.
        with psycopg.connect(DATABASE_URL) as connection:
            altered={**stored,"event_id":"ROOTLINE-EXEC-"+"F"*32}
            connection.execute("insert into public.sam_live_stock_conversation_review_events(review_event_id,chatwoot_conversation_id,event_source,review_json) values(%s,%s,%s,%s)",
                (altered["event_id"],claim["execution_id"],store.EVENT_SOURCE,Jsonb({"rootline_execution":altered})))
    restarted=budget.RequestBudget(environment())
    restarted.dispatch(region="eu",endpoint="/v2/family",send=lambda _: {})
    assert claim["execution_id"] in ledger(restarted)[0]["reserves"]
