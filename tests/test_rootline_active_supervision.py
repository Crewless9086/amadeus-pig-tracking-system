"""Isolated real scheduler -> runtime -> coordinator shutdown regression tests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

import pytest

from modules.oom_sakkie.automatic_reassessment_scheduler import SCHEDULER_IDENTITY
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.telemetry.rootline_execution_runtime import supervise_rootline_active_execution
from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution
from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
ENV = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true",
    "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "synthetic-token-" * 4,
    "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
    "ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}
HEADERS = {"X-Oom-Sakkie-Telegram-Token": ENV["OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN"]}


def active(*, due=True, zone="B12345"):
    claimed = NOW - timedelta(seconds=3600 if due else 100)
    return {"execution_id": "SYNTHETIC-IRRIGATION", "zone_id": zone,
        "device_id": "100204e9bc", "channel": 1 if zone == "B12345" else 2,
        "state": "Active", "claimed_at": claimed.isoformat(),
        "primary_stop_deadline": (claimed + timedelta(seconds=3599)).isoformat(),
        "native_fail_stop_deadline": (claimed + timedelta(seconds=3599)).isoformat(),
        "planned_runtime_seconds": 3599, "on_attempts": 1, "off_attempts": 0,
        "start_evidence": {"authoritative": True, "state": "ON", "evidence_id": "SYNTHETIC-ON",
            "retrieved_at": (claimed + timedelta(seconds=1)).isoformat()}}


class ExecutionStore:
    def __init__(self, row=None, fail=None):
        self.active = deepcopy(row)
        self.fail = fail
        self.rows = []
        self.used = set()
        self.lock = Lock()
        self.auxiliary = None

    def __call__(self, action, payload):
        with self.lock:
            if action == self.fail:
                raise RootlineExecutionStoreUnavailable("synthetic failure")
            if action == "load_active":
                return deepcopy(self.active)
            if action == "load_active_auxiliary":
                return deepcopy(self.auxiliary)
            if action == "load_off_attempts":
                return [row for name, row in self.rows if name == "claim_off_attempt"]
            if action.startswith("load_"):
                return None
            if action in {"claim_before_on", "record_eligibility"}:
                raise AssertionError("active-only safety must never claim a new ON")
            if action.startswith("claim_"):
                identity = (action, payload.get("attempt"), payload.get("notification_identity"))
                if identity in self.used:
                    return {"success": True, "created": False}
                self.used.add(identity)
            self.rows.append((action, deepcopy(payload)))
            if action == "mark_stopping":
                self.active = deepcopy(payload)
            if action == "record_completed":
                self.active = None
            if action == "contain_auxiliary_device" and payload.get("shutdown_verified") is True:
                self.auxiliary = None
            return {"success": True, "created": True}


class Transport:
    def __init__(self, state="OFF", fail_read=False):
        self.calls = []
        self.state = state
        self.fail_read = fail_read

    def set_state(self, **kwargs):
        assert kwargs["state"] == "OFF"
        self.calls.append(kwargs)
        return {"accepted_unambiguous": True}

    def read_output_state(self, **kwargs):
        if self.fail_read:
            raise RuntimeError("synthetic provider timeout")
        return {"authoritative": self.state != "Unknown", "state": self.state,
            "evidence_id": "SYNTHETIC-OFF", "retrieved_at": NOW.isoformat()}


def supervisor(store, transport):
    return partial(supervise_rootline_active_execution, store=store,
        transport=transport, token_store=object())


def run_supervisor(store, transport, **kwargs):
    return supervisor(store, transport)(notify=lambda *args: {
        "success": True, "provider_delivery_confirmed": True, "provider_message_id": "synthetic-message"},
        environ=kwargs.pop("environ", {}), now=NOW, owner_user_id="42", chat_id="42", **kwargs)


class ScheduleStore:
    def __init__(self):
        self.rows = {}; self.lock = Lock()

    def __call__(self, action, identity, payload):
        with self.lock:
            if action == "load_latest_outcome":
                outcomes = [v for k, v in self.rows.items() if k.endswith(":outcome")]
                return deepcopy(outcomes[-1]) if outcomes else None
            if action == "load_schedule":
                return deepcopy(self.rows.get(identity + ":outcome") or self.rows.get(identity))
            key = identity if action == "claim_schedule" else identity + ":outcome"
            if key in self.rows:
                return {"success": True, "created": False}
            self.rows[key] = deepcopy(payload)
            return {"success": True, "created": True}


def payload(**changes):
    return {"scheduler_identity": SCHEDULER_IDENTITY, "specialist": "ROOTLINE",
        "owner_user_id": "42", "chat_id": "42", "trigger": "declared_time",
        "trigger_id": "SYNTHETIC-SCHEDULE", "trigger_timestamp": NOW.isoformat(),
        "due_at": NOW.isoformat(), "evidence_cutoff": (NOW - timedelta(seconds=1)).isoformat(), **changes}


def current():
    return {"success": True, "overall_status": "Hold", "operating_date": NOW.date().isoformat(),
        "result_id": "SYNTHETIC-RESULT", "generation": "SYNTHETIC-GENERATION",
        "evidence_cutoff": (NOW - timedelta(seconds=2)).isoformat(),
        "recommendations": [], "owner_brief": {"family_fact_needed": ""}}


@pytest.fixture
def reports(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.documents_green_followup_runtime.recover_documents_green_physical_follow_up",
        lambda **k: {"handled": False})
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.reassess_due_mixer_presence",
        lambda **k: {"status": "no_reassessable_mixer_presence"})
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster", lambda *a: {})
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_breeding_attention_source_snapshot",
        lambda **k: {})
    monkeypatch.setattr("modules.sales.sales_transaction_read.list_sales_transactions",
        lambda: ({"success": True, "sales_transactions": []}, 200))
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager",
        lambda **k: {"success": True, "status": "daily_farm_manager_unchanged"})


def gateway(store, transport, *, schedules=None, **kwargs):
    starts = []; messages = []; lifecycle = {}
    def state(action, identity, item):
        if action == "load_identity": return lifecycle.get(identity)
        if action == "load_delivered": return None
        if action in {"claim_pending", "record_observation"}:
            created = identity not in lifecycle; lifecycle.setdefault(identity, item)
            return {"success": True, "created": created}
        return {"success": True}
    def deliver(*args, **kw):
        messages.append((args, kw))
        return {"success": True, "telegram_sends": 1, "telegram_message_id": "synthetic-message"}
    options = dict(specialist_loader=current, state_store=state,
        schedule_store=schedules or ScheduleStore(), scheduler_now=NOW,
        family_delivery=deliver, active_supervision_cycle=supervisor(store, transport),
        execution_cycle=lambda **k: starts.append(k) or {"success": True, "status": "not_eligible"})
    request = kwargs.pop("request_payload", payload())
    source_env = kwargs.pop("source_env", ENV)
    options.update(kwargs)
    value, status = handle_rootline_reassessment_trigger(request, HEADERS, source_env, **options)
    return value, status, starts, messages


def test_overdue_active_stops_before_actual_daily_report_timeout(reports, monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager",
        lambda **k: (_ for _ in ()).throw(TimeoutError("synthetic report timeout")))
    store = ExecutionStore(active()); transport = Transport(); schedules = ScheduleStore()
    value, status, starts, messages = gateway(store, transport, schedules=schedules)
    assert status == 202 and value["status"] == "scheduled_reassessment_evidence_deadline_exceeded"
    assert value["execution_status"] == "segment_completed"
    assert value["hardware_commands"] == 1 and value["telegram_sends"] == 1
    assert value["writes_farm_data"] is True and starts == []
    assert store.active is None and len(messages) == 1
    assert "controller OFF" in messages[0][0][1]["answer"]
    outcome = next(row for key, row in schedules.rows.items() if key.endswith(":outcome"))
    assert outcome["status"] == "contained" and outcome["hardware_commands"] == 1
    assert outcome["active_supervision_status"] == "segment_completed"


@pytest.mark.parametrize("flag", ["false", "true"])
def test_plan_failure_cannot_delay_existing_shutdown_or_enable_new_on(reports, flag):
    store = ExecutionStore(active()); transport = Transport()
    value, status, starts, _ = gateway(store, transport,
        daily_plan_generator=lambda _: (_ for _ in ()).throw(RuntimeError("plan unavailable")))
    assert status == 202 and value["execution_status"] == "segment_completed"
    assert value["hardware_commands"] == 1 and value["writes_farm_data"] is True
    assert starts == []
    # The runtime itself also supervises OFF while the autonomous-start flag is absent.
    assert run_supervisor(ExecutionStore(active()), Transport(), environ={
        "ROOTLINE_AUTONOMOUS_BC_ENABLED": flag})["status"] == "segment_completed"


def test_no_active_and_failed_plan_never_starts_or_reads_provider(reports):
    store = ExecutionStore(); transport = Transport(fail_read=True)
    value, _, starts, messages = gateway(store, transport,
        daily_plan_generator=lambda _: (_ for _ in ()).throw(RuntimeError("plan unavailable")))
    assert value["active_supervision_status"] == "no_active_irrigation"
    assert starts == messages == transport.calls == []


def test_unauthenticated_and_wrong_private_chat_never_reach_supervision():
    calls = []
    for headers, body in [({}, payload()), (HEADERS, payload(chat_id="43"))]:
        value, status = handle_rootline_reassessment_trigger(body, headers, ENV,
            active_supervision_cycle=lambda **k: calls.append(k))
        assert status == 403 and value["success"] is False
    assert calls == []


def test_store_failure_blocks_all_reporting_and_new_starts(reports):
    value, status, starts, messages = gateway(ExecutionStore(fail="load_active"), Transport(),
        specialist_loader=lambda: pytest.fail("reports must not run after unknown active state"))
    assert status == 202 and value["execution_status"] == "execution_store_degraded_hold"
    assert starts == messages == [] and value["hardware_commands"] == 0


def test_missing_active_cannot_fall_through_to_eligible_decision():
    calls = []
    value = advance_irrigation_execution(decision_id="fresh-eligible", commissioning_id="fresh",
        decision_reader=lambda _: pytest.fail("no planning in active-only mode"),
        commissioning_reader=lambda _: pytest.fail("no commissioning in active-only mode"),
        store=lambda action, row: calls.append(action) or None, transport=Transport(),
        notify=lambda *a: pytest.fail("no notification"), now=NOW, active_only=True)
    assert value["status"] == "no_active_irrigation" and calls == ["load_active"]


def test_active_disappears_before_single_load_never_attempts_on():
    store = ExecutionStore(active()); store.active = None
    result = run_supervisor(store, Transport())
    assert result["active_execution_found"] is False and store.rows == []


@pytest.mark.parametrize("failure", ["provider_read", "record_completed", "mark_stopping"])
def test_uncertain_shutdown_or_write_never_hides_attempts_or_claims_completion(failure):
    store = ExecutionStore(active(), fail=failure if failure != "provider_read" else None)
    transport = Transport(fail_read=failure == "provider_read")
    result = run_supervisor(store, transport)
    assert result["success"] is False and result["status"] == "active_irrigation_supervision_unproven"
    assert result["hardware_commands"] == len(transport.calls) == (0 if failure == "mark_stopping" else 1)
    assert result["writes_farm_data"] is None and store.active is not None


def test_unknown_off_retains_containment_and_does_not_complete():
    store = ExecutionStore(active()); transport = Transport(state="Unknown")
    result = run_supervisor(store, transport)
    assert result["status"] == "shutdown_unverified" and result["success"] is False
    assert not any(action == "record_completed" for action, _ in store.rows)
    assert len(transport.calls) <= 3 and store.active is not None


def test_replay_and_concurrent_same_bucket_supervise_once(reports):
    store = ExecutionStore(active()); transport = Transport(); schedules = ScheduleStore()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: gateway(store, transport, schedules=schedules), range(2)))
    again = gateway(store, transport, schedules=schedules)[0]
    assert len(transport.calls) == 1
    assert again["status"] == "scheduled_reassessment_replayed_noop"
    assert sum(value["hardware_commands"] for value, _, _, _ in results) == 1


def test_each_minute_supervises_managed_devices_but_shutdown_tick_forbids_new_starts(reports):
    managed_calls = []
    env = {**ENV, "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"}
    # Use the actual gateway, runtime and coordinator with a fake managed edge.
    for due in (False, True):
        store = ExecutionStore(active(due=due)); transport = Transport()
        options = dict(specialist_loader=current, state_store=lambda *a: {"success": True, "created": True},
            schedule_store=ScheduleStore(), scheduler_now=NOW,
            family_delivery=lambda *a, **k: {"success": True, "telegram_message_id": "synthetic"},
            active_supervision_cycle=supervisor(store, transport),
            execution_cycle=lambda **k: pytest.fail("new B/C cycle after active supervision"),
            managed_device_cycle=lambda **k: managed_calls.append((due,k["allow_new_starts"])) or {
                "success": True, "status": "no_active_managed_device", "blocks_bc": False})
        handle_rootline_reassessment_trigger(payload(), HEADERS, env, **options)
    assert managed_calls == [(False,True),(True,False)]


def test_existing_injector_shutdown_interlock_is_preserved(monkeypatch):
    # Exercise the real parent coordinator; only the auxiliary stop result is
    # injected, because the auxiliary coordinator has its own exhaustive suite.
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_coordinator._stop_bound_injection",
        lambda *a: {"status": "auxiliary_emergency_off_unverified", "shutdown_verified": False,
            "hardware_commands": 0})
    store = ExecutionStore(active()); transport = Transport(state="ON")
    value = run_supervisor(store, transport)
    assert value["status"] == "injector_off_unverified_native_deadline_elapsed"
    assert value["parent_off_command_withheld"] is True and transport.calls == []
    assert not any(action == "record_completed" for action, _ in store.rows)


def test_late_reporting_exception_preserves_verified_stop(reports, monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.telegram_gateway.reassess_rootline",
        lambda **k: (_ for _ in ()).throw(RuntimeError("late presentation failure")))
    value, status, starts, _ = gateway(ExecutionStore(active()), Transport())
    assert status == 202 and value["status"] == "scheduled_rootline_reporting_unproven"
    assert value["hardware_commands"] == 1 and value["writes_farm_data"] is True
    assert value["report_effects_unknown"] is True and starts == []


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_stop_is_bound_to_exact_commissioned_channel_and_does_not_touch_mixer(zone):
    store = ExecutionStore(active(zone=zone)); store.auxiliary = {
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2", "state": "Active"}
    transport = Transport(); result = run_supervisor(store, transport)
    assert result["status"] == "segment_completed"
    assert {(c["device_id"], c["channel"], c["state"]) for c in transport.calls} == {
        ("100204e9bc", 1 if zone == "B12345" else 2, "OFF")}
    assert store.auxiliary["state"] == "Active"


def test_wrong_channel_cannot_dispatch_any_off():
    row = active(); row["channel"] = 4
    transport = Transport(); result = run_supervisor(ExecutionStore(row), transport)
    assert result["success"] is False and transport.calls == []


def test_no_active_never_constructs_provider_or_token_adapter(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_execution_runtime.RootlineIFTTTTransport",
        lambda **k: pytest.fail("no provider adapter required"))
    monkeypatch.setattr("modules.telemetry.rootline_execution_runtime.PostgresOAuthTokenStore",
        lambda *a: pytest.fail("no token adapter required"))
    result = supervise_rootline_active_execution(notify=lambda *a: None,
        environ={}, now=NOW, owner_user_id="42", chat_id="42", store=ExecutionStore())
    assert result["status"] == "no_active_irrigation"


def test_unavailable_adapter_is_contained_after_canonical_identity_load(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_execution_runtime.RootlineIFTTTTransport",
        lambda **k: (_ for _ in ()).throw(RuntimeError("configuration unavailable")))
    result = supervise_rootline_active_execution(notify=lambda *a: None,
        environ={}, now=NOW, owner_user_id="42", chat_id="42",
        store=ExecutionStore(active()), token_store=object())
    assert result["status"] == "active_irrigation_supervision_unproven"
    assert result["active_execution_found"] is True and result["hardware_commands"] == 0


def test_active_duty_owns_next_minute_despite_long_report_plan_and_later_tick(reports, monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.telegram_gateway.reassess_rootline", lambda **k: {
        "success": True, "status": "rootline_reassessment_unchanged",
        "next_due_at": (NOW + timedelta(minutes=30)).isoformat()})
    row = active(due=False)
    row["primary_stop_deadline"] = row["native_fail_stop_deadline"] = (
        NOW + timedelta(seconds=30)).isoformat()
    store = ExecutionStore(row); schedules = ScheduleStore(); transport = Transport()
    first, status, starts, _ = gateway(store, transport, schedules=schedules)
    assert status == 200 and first["execution_status"] == "active_segment_owned"
    assert datetime.fromisoformat(first["next_due_at"]) == NOW + timedelta(minutes=30)
    assert datetime.fromisoformat(first["supervision_next_due_at"]) == NOW + timedelta(minutes=1)
    later = NOW + timedelta(minutes=1)
    second, _, starts2, _ = gateway(store, transport, schedules=schedules, scheduler_now=later,
        request_payload=payload(due_at=later.isoformat(), trigger_timestamp=later.isoformat()))
    assert second["execution_status"] == "segment_stopped_outcome_unconfirmed"
    assert len(transport.calls) == 1 and starts == starts2 == []
    assert len([k for k in schedules.rows if k.endswith(":outcome")]) == 2


@pytest.mark.parametrize("execution_status, supervision_status", [
    ("segment_started", "no_active_irrigation"),
    ("execution_store_degraded_hold", "execution_store_degraded_hold")])
def test_new_start_or_uncertain_safety_retains_separate_report_cadence(execution_status, supervision_status):
    from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
    result = run_due_reassessment(payload=payload(), now=NOW, store=ScheduleStore(), invoke=lambda: {
        "success": execution_status == "segment_started", "status": "synthetic",
        "execution_status": execution_status, "active_supervision_status": supervision_status,
        "next_due_at": (NOW + timedelta(hours=1)).isoformat()},
        invoke_not_due=lambda: {"success": True, "status": "no_active_irrigation"})
    assert datetime.fromisoformat(result["next_due_at"]) == NOW + timedelta(hours=1)
    assert datetime.fromisoformat(result["supervision_next_due_at"]) == NOW + timedelta(minutes=1)


@pytest.mark.parametrize("raise_error", [False, True])
def test_outcome_write_failure_keeps_off_effect_and_cannot_claim_completion(reports, raise_error):
    backing = ScheduleStore()
    def schedules(action, identity, row):
        if action == "record_outcome":
            if raise_error: raise RuntimeError("synthetic outcome write failure")
            return {"success": False}
        return backing(action, identity, row)
    value, status, starts, _ = gateway(ExecutionStore(active()), Transport(), schedules=schedules)
    assert status == 202 and value["status"] == "scheduled_reassessment_outcome_unproven"
    assert value["hardware_commands"] == 1 and value["writes_farm_data"] is True
    assert value["outcome_recorded"] is False and value["terminal_outcome"] == "claimed"
    assert value["active_supervision_status"] == "segment_completed" and starts == []


def test_production_plan_recovery_failure_happens_only_after_supervision(reports, monkeypatch):
    from contextlib import nullcontext
    class Cursor:
        def execute(self, *args): pass
        def fetchone(self): return (1,)
    class Connection:
        def cursor(self): return nullcontext(Cursor())
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_read",
        lambda **k: nullcontext(Connection()))
    state = lambda *a: {"success": True, "created": True}
    monkeypatch.setattr("modules.oom_sakkie.rootline_reassessment_store.rootline_reassessment_state_store", state)
    store = ExecutionStore(active()); transport = Transport()
    def recovery(**kwargs):
        assert store.active is None and len(transport.calls) == 1
        return {"success": False, "status": "synthetic_manager_recovery_unavailable"}
    monkeypatch.setattr("modules.oom_sakkie.rootline_operational_adapter.recover_pending_manager_rootline_observation", recovery)
    value, status = handle_rootline_reassessment_trigger(payload(), HEADERS, ENV,
        schedule_store=ScheduleStore(), scheduler_now=NOW,
        active_supervision_cycle=supervisor(store, transport),
        managed_device_cycle=lambda **k: {"success":True,"status":"no_active_managed_device","blocks_bc":False},
        family_delivery=lambda *a, **k: {"success": True, "telegram_message_id": "synthetic"})
    assert status == 202 and value["status"] == "scheduled_rootline_daily_plan_persistence_ambiguous"
    assert value["execution_status"] == "segment_completed" and value["hardware_commands"] == 1


@pytest.mark.parametrize("has_active", [True, False])
def test_seeded_future_report_does_not_block_safety_or_run_reports(has_active):
    schedules = ScheduleStore(); report_due = NOW + timedelta(minutes=30)
    schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
        "next_due_at": report_due.isoformat()}
    store = ExecutionStore(active() if has_active else None); transport = Transport()
    def forbidden(*args, **kwargs): pytest.fail("report/new-start work is not due")
    value, status, starts, messages = gateway(store, transport, schedules=schedules,
        specialist_loader=forbidden, daily_plan_generator=forbidden, execution_cycle=forbidden)
    assert status == 200 and value["status"] == "scheduled_rootline_active_supervised"
    assert datetime.fromisoformat(value["next_due_at"]) == report_due
    assert value["hardware_commands"] == len(transport.calls) == int(has_active)
    assert starts == [] and len(messages) == int(has_active)
    assert len(schedules.rows) == 3
    own_outcome = [v for k, v in schedules.rows.items() if k != "prior:outcome" and k.endswith(":outcome")][0]
    assert own_outcome["report_work_due"] is False
    replay = gateway(store, transport, schedules=schedules, specialist_loader=forbidden)[0]
    assert replay["status"] == "scheduled_reassessment_replayed_noop"
    later = NOW + timedelta(minutes=1)
    later_result = gateway(store, transport, schedules=schedules, scheduler_now=later,
        request_payload=payload(due_at=later.isoformat(), trigger_timestamp=later.isoformat()),
        specialist_loader=forbidden)[0]
    assert later_result["active_supervision_status"] == "no_active_irrigation"
    assert datetime.fromisoformat(later_result["next_due_at"]) == report_due
    assert len(transport.calls) == int(has_active)


def test_supervision_not_due_callback_requires_valid_claim_and_never_replays():
    from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
    store = ScheduleStore(); report_due = NOW + timedelta(minutes=30)
    store.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed", "next_due_at": report_due.isoformat()}
    calls = []
    def refuse_claim(action, identity, row):
        if action == "claim_schedule": return {"success": False}
        return store(action, identity, row)
    for request, backing in [(payload(scheduler_identity="invalid"), store), (payload(), refuse_claim)]:
        result = run_due_reassessment(payload=request, now=NOW, store=backing,
            invoke=lambda: pytest.fail("not due"), invoke_not_due=lambda: calls.append(1))
        assert result["success"] is False
    assert calls == []


def test_reporting_resumes_at_preserved_due_after_intervening_safety_ticks(reports, monkeypatch):
    due = NOW + timedelta(minutes=2); schedules = ScheduleStore()
    schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed", "next_due_at": due.isoformat()}
    reports_seen = []
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager",
        lambda **k: reports_seen.append(1) or {"success": True, "status": "daily_farm_manager_unchanged"})
    store = ExecutionStore(); transport = Transport()
    first = gateway(store, transport, schedules=schedules)[0]
    assert first["report_work_due"] is False and reports_seen == []
    gateway(store, transport, schedules=schedules, scheduler_now=due,
        request_payload=payload(due_at=due.isoformat(), trigger_timestamp=due.isoformat()))
    assert reports_seen == [1] and transport.calls == []


def test_default_transport_uses_exact_device_readback_for_real_bound_injector_stop(monkeypatch):
    import json
    from modules.telemetry import rootline_ifttt_transport
    parent = active()
    parent.update(job_id="SYNTHETIC-JOB", job_sha256="a" * 64, segment_identity="SYNTHETIC-SEGMENT",
        governed_executable_duration_seconds=7198, cumulative_verified_runtime_seconds=0)
    store = ExecutionStore(parent)
    store.auxiliary = {"execution_id": "SYNTHETIC-INJECTION", "auxiliary_device_id": "FERTILIZER-INJECTION-CH1",
        "device_id": "100204d497", "channel": 1, "state": "Active",
        **{key: parent[key] for key in ("job_id", "job_sha256", "segment_identity", "zone_id")}}
    reads = []; commands = []
    def read_registered(device_id, **kwargs):
        reads.append(device_id)
        return {"device_id": device_id, "provider_control_calls": 0,
            "current_outputs_authoritative": True, "response_digest": "SYNTHETIC-" + device_id,
            "retrieved_at": NOW.isoformat(),
            "channels": [{"channel": n, "output_state": "OFF"} for n in range(1, 5)]}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def getcode(self): return 200
        def read(self, *args): return b"synthetic acceptance"
    def http(request, **kwargs):
        commands.append(json.loads(request.data))
        assert "_off/" in request.full_url
        return Response()
    monkeypatch.setattr("modules.telemetry.rootline_ewelink_readback.read_registered_device", read_registered)
    monkeypatch.setattr("modules.telemetry.rootline_ewelink_readback.read_current_device",
        lambda **k: pytest.fail("B/C-only reader cannot prove the injector"))
    monkeypatch.setattr(rootline_ifttt_transport.urllib_request, "urlopen", http)
    result = supervise_rootline_active_execution(notify=lambda *a: {}, now=NOW,
        environ={"ROOTLINE_IFTTT_MAKER_KEY": "synthetic-not-a-real-key"}, token_store=object(),
        store=store, owner_user_id="42", chat_id="42")
    assert result["status"] == "segment_completed" and result["hardware_commands"] == 2
    assert [(row["value2"], row["value3"]) for row in commands] == [("100204d497", "1"), ("100204e9bc", "1")]
    assert reads == ["100204d497", "100204e9bc"] and store.auxiliary is None
    completion = next(row for action, row in store.rows if action == "record_completed")
    assert completion["job_completed"] is False
    assert completion["shutdown_verified"] is True


@pytest.mark.parametrize("terminal", ["completed", "contained", "claimed"])
def test_safety_only_replay_never_runs_report_delivery_recovery(terminal):
    from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
    backing = ScheduleStore()
    report_due = NOW + timedelta(minutes=30)
    backing.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
        "next_due_at": report_due.isoformat()}
    def failed_outcome(action, identity, row):
        if action == "record_outcome": return {"success": False}
        return backing(action, identity, row)
    first = run_due_reassessment(payload=payload(), now=NOW, store=failed_outcome,
        invoke=lambda: pytest.fail("reports are not due"),
        invoke_not_due=lambda: {"success": False, "status": "uncertain_stop",
            "hardware_commands": 1, "writes_farm_data": None})
    assert first["hardware_commands"] == 1 and first["writes_farm_data"] is None
    assert first["outcome_recorded"] is False
    claim = backing.rows[first["schedule_identity"]]
    assert claim["report_work_due"] is False
    claim["status"] = terminal
    replay = run_due_reassessment(payload=payload(), now=NOW, store=backing,
        invoke=lambda: pytest.fail("reports are not due"),
        invoke_not_due=lambda: pytest.fail("same claim cannot supervise again"),
        recover_delivery=lambda: pytest.fail("safety-only claims have no report delivery"))
    assert replay["status"] == ("scheduled_reassessment_claim_interrupted"
        if terminal == "claimed" else "scheduled_reassessment_replayed_noop")
    assert replay["hardware_commands"] == 0


@pytest.fixture
def sql_schedule_store(monkeypatch):
    """Execute the real store SELECTs with synthetic rows and no network.

    SQLite provides the relational selection/order, while this adapter only
    translates parameter syntax and PostgreSQL JSON ->> boolean text. Native
    PostgreSQL qualification remains a separate release gate.
    """
    import json
    import sqlite3
    from contextlib import nullcontext
    from modules.oom_sakkie import automatic_reassessment_store as persistence
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.execute("attach database ':memory:' as public")
    connection.execute("create table public.sam_live_stock_conversation_review_events "
        "(review_event_id text primary key, event_source text, review_json text, created_at integer)")
    def json_text(value, field):
        item = json.loads(value).get(field) if value is not None else None
        if isinstance(item, bool): return "true" if item else "false"
        return item
    connection.create_function("->>", 2, json_text)
    class Cursor:
        def __init__(self): self.cursor = connection.cursor()
        def __enter__(self): return self
        def __exit__(self, *args): self.cursor.close()
        def execute(self, sql, params): self.cursor.execute(sql.replace("%s", "?"), params)
        def fetchone(self):
            row = self.cursor.fetchone()
            return (json.loads(row[0]),) if row else None
    class Connection:
        def cursor(self): return Cursor()
    monkeypatch.setattr(persistence, "connect_bounded_read", lambda: nullcontext(Connection()))
    class Store:
        def __init__(self): self.sequence = 0; self.lock = Lock()
        def append(self, event_id, body):
            self.sequence += 1
            connection.execute("insert into public.sam_live_stock_conversation_review_events values(?,?,?,?)",
                (event_id, persistence.EVENT_SOURCE, json.dumps({"automatic_reassessment": body}), self.sequence))
        def __call__(self, action, identity, body):
            with self.lock:
                if action in {"load_schedule", "load_latest_outcome"}:
                    return persistence.automatic_reassessment_store(action, identity, body)
                event_id = identity if action == "claim_schedule" else identity + "-OUTCOME"
                if connection.execute("select 1 from public.sam_live_stock_conversation_review_events "
                        "where review_event_id=?", (event_id,)).fetchone():
                    return {"success": True, "created": False}
                self.append(event_id, {**body, "identity": identity, "event_id": event_id})
                return {"success": True, "created": True}
    yield Store()
    connection.close()


def test_actual_store_report_due_query_ignores_only_explicit_safety_outcomes(sql_schedule_store):
    store = sql_schedule_store
    base = {"specialist": "ROOTLINE", "status": "completed"}
    store.append("legacy", {**base, "identity": "legacy", "next_due_at": "legacy-due"})
    store.append("safety", {**base, "identity": "safety", "report_work_due": False,
        "next_due_at": "obsolete-safety-copy"})
    assert store("load_latest_outcome", "ROOTLINE", None)["identity"] == "legacy"
    store.append("report", {**base, "identity": "report", "report_work_due": True,
        "next_due_at": "fresh-report-due"})
    store.append("late-safety", {**base, "identity": "late-safety", "status": "contained",
        "report_work_due": False, "next_due_at": "obsolete-safety-copy"})
    assert store("load_latest_outcome", "ROOTLINE", None)["identity"] == "report"
    assert store("load_schedule", "late-safety", None)["identity"] == "late-safety"


@pytest.mark.parametrize("safety_success", [True, False])
def test_late_safety_outcome_cannot_replace_newer_report_due(sql_schedule_store, safety_success):
    from threading import Event
    from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
    store = sql_schedule_store
    report_at = NOW + timedelta(minutes=1)
    next_report = NOW + timedelta(minutes=31)
    store.append("prior-report", {"specialist": "ROOTLINE", "status": "completed",
        "next_due_at": report_at.isoformat()})
    safety_entered = Event(); release_safety = Event()
    def safety():
        safety_entered.set()
        assert release_safety.wait(5), "test must release safety deterministically"
        return {"success": safety_success, "status": "active_segment_owned"}
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_due_reassessment, payload=payload(), now=NOW, store=store,
            invoke=lambda: pytest.fail("reports are not due"), invoke_not_due=safety)
        try:
            assert safety_entered.wait(5)
            report = run_due_reassessment(payload=payload(due_at=report_at.isoformat()),
                now=report_at, store=store, invoke=lambda: {
                    "success": True, "status": "report_complete", "next_due_at": next_report.isoformat()},
                invoke_not_due=lambda: pytest.fail("report work is due"))
            assert datetime.fromisoformat(report["next_due_at"]) == next_report
        finally:
            release_safety.set()
        assert datetime.fromisoformat(future.result()["next_due_at"]) == report_at
    later = NOW + timedelta(minutes=2)
    result = run_due_reassessment(payload=payload(due_at=later.isoformat()), now=later, store=store,
        invoke=lambda: pytest.fail("late safety outcome must not accelerate reports"),
        invoke_not_due=lambda: {"success": True, "status": "no_active_irrigation"})
    assert datetime.fromisoformat(result["next_due_at"]) == next_report
