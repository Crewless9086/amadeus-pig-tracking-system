"""Recovery reaches the real managed cycle/coordinators before optional planning.

Synthetic stores/transports deny every ON edge. The predecessor reference is
reconstructed by inlining the unchanged factory body; qualification separately
compares that AST with the exact pre-change source, not a copied coordinator.
"""
import ast
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry import rootline_water_energy_plan as plan_module
from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
FLAGS = ("ROOTLINE_FERTILIZER_MIXING_ENABLED", "ROOTLINE_FERTILIZER_INJECTION_ENABLED", "ROOTLINE_BOREHOLE_ENABLED")


def predecessor_ast():
    node = ast.parse(inspect.getsource(runtime.run_rootline_managed_device_reassessment)).body[0]
    index = next(i for i, n in enumerate(node.body) if isinstance(n, ast.FunctionDef) and n.name == "build_evidence")
    factory = node.body[index]
    assert isinstance(factory.body[-1], ast.Return)
    body = deepcopy(factory.body[:-1])
    handler = body[0].handlers[0]
    assert isinstance(handler.body[0], ast.Raise)
    failure_result = handler.body[0].exc.args[0]
    handler.body = [ast.Return(value=failure_result)]
    handler.name = None
    call = deepcopy(node.body[-1])
    assert isinstance(call, ast.Return)
    call.value.keywords = [kw for kw in call.value.keywords if kw.arg != "evidence_factory"]
    next(kw for kw in call.value.keywords if kw.arg == "evidence").value = ast.Name(id="packet", ctx=ast.Load())
    node.body = node.body[:index] + body + [call]
    for statement in node.body:
        if isinstance(statement, ast.ImportFrom) and statement.module == "modules.telemetry.rootline_managed_devices_runtime":
            statement.names = [name for name in statement.names if name.name != "ManagedDevicePlanningUnavailable"]
    return ast.fix_missing_locations(node)


def predecessor():
    namespace = dict(vars(runtime))
    exec(compile(ast.Module(body=[predecessor_ast()], type_ignores=[]), "<predecessor-reassessment>", "exec"), namespace)
    return namespace["run_rootline_managed_device_reassessment"]


def active(kind="mixer", *, due=True, claimed=False):
    row = {"execution_id": "synthetic-" + kind, "state": "claimed_recovery_required" if claimed else "Active",
        "primary_stop_deadline": (NOW + timedelta(seconds=-1 if due else 60)).isoformat(),
        "claimed_at": (NOW - timedelta(minutes=6)).isoformat(), "maximum_duration_seconds": 300,
        "start_evidence": {"authoritative": True, "state": "ON"},
        "provider_start_evidence": {"authoritative": True, "state": "ON"}}
    if kind != "borehole":
        row.update({"auxiliary_device_id": "FERTILIZER-INJECTION-CH1" if kind == "injector" else "FERTILIZER-MIXER-CH2",
            "device_type": "fertilizer_injection_valve" if kind == "injector" else "fertilizer_mixer",
            "device_id": "100204d497", "channel": 1 if kind == "injector" else 2})
    return row


class Store:
    def __init__(self, kind=None, *, both=False, vanish=False, fail_action=None, failure=None):
        self.aux = active(kind) if kind and kind != "borehole" else None
        self.borehole = active("borehole") if kind == "borehole" or both else None
        self.vanish, self.fail_action, self.failure = vanish, fail_action, failure
        self.calls, self.writes, self.used = [], [], {}
        self.loads = Counter()

    def __call__(self, action, payload):
        self.calls.append(action)
        if action == self.fail_action:
            raise self.failure or RootlineExecutionStoreUnavailable(action)
        if action in {"load_active_auxiliary", "load_active_borehole"}:
            self.loads[action] += 1
            if self.vanish and self.loads[action] > 1:
                return None
            return deepcopy(self.aux if action.endswith("auxiliary") else self.borehole)
        if action in {"load_auxiliary_off_attempts", "load_borehole_off_attempts"}:
            return [{"attempt": n} for n in sorted(self.used.get(payload, set()))]
        if action == "load_auxiliary_physical_outcome":
            return None
        if action in {"claim_auxiliary_off_attempt", "claim_borehole_off_attempt"}:
            seen = self.used.setdefault(payload["execution_id"], set())
            created = payload["attempt"] not in seen
            seen.add(payload["attempt"])
            self.writes.append((action, deepcopy(payload)))
            return {"success": True, "created": created}
        if action in {"record_auxiliary_off_outcome", "record_borehole_off_outcome", "record_auxiliary_exception"}:
            self.writes.append((action, deepcopy(payload)))
            return {"success": True, "created": True}
        if action in {"record_auxiliary_completed", "record_auxiliary_control_pulse_stopped", "record_borehole_completed",
                      "contain_auxiliary_device", "contain_borehole"}:
            self.writes.append((action, deepcopy(payload)))
            if action == "record_borehole_completed":
                self.borehole = None
            elif action != "contain_borehole" and (action != "contain_auxiliary_device" or payload.get("shutdown_verified") is True):
                self.aux = None
            return {"success": True, "created": True}
        raise AssertionError("Unexpected store effect: " + action)


class OffOnlyTransport:
    def __init__(self, *, accepted=True, verified=True, raise_write=False, raise_read=False):
        self.accepted, self.verified = accepted, verified
        self.raise_write, self.raise_read = raise_write, raise_read
        self.commands, self.reads, self.safety_reads = [], [], []

    def set_state(self, **kwargs):
        assert kwargs["state"] == "OFF", "An ON edge is forbidden in this recovery fixture"
        if self.raise_write:
            raise RuntimeError("synthetic-provider-write-error")
        self.commands.append(deepcopy(kwargs))
        return {"accepted_unambiguous": self.accepted, "status": "accepted" if self.accepted else "ambiguous"}

    def read_output_state(self, **kwargs):
        self.reads.append(kwargs)
        if self.raise_read:
            raise RuntimeError("synthetic-provider-read-error")
        return {"authoritative": self.verified, "state": "OFF" if self.verified else "Unknown", "evidence_id": "synthetic-final-off"}

    def read_safety_configuration(self, **kwargs):
        self.safety_reads.append(kwargs)
        return {}


class Evidence:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("optional-planner-unavailable")
        return {"synthetic_generation": len(self.calls)}, NOW.date().isoformat(), kwargs["now"]


def invoke(store, transport, loader, *, function=None, environ=None, now=NOW):
    return (function or runtime.run_rootline_managed_device_reassessment)(
        environ={} if environ is None else environ, now=now, database_url="postgresql://synthetic-inert",
        store=store, token_store=object(), transport=transport, evidence_loader=loader)


@pytest.mark.parametrize("kind", [None, "mixer", "injector", "borehole"])
def test_healthy_predecessor_results_and_canonical_effects_match(kind, record_property):
    old_store, new_store = Store(kind), Store(kind)
    old_transport, new_transport = OffOnlyTransport(), OffOnlyTransport()
    old_loader, new_loader = Evidence(), Evidence()
    old = invoke(old_store, old_transport, old_loader, function=predecessor())
    new = invoke(new_store, new_transport, new_loader)
    assert new == old
    assert new_store.calls == (old_store.calls * 2 if kind is None else old_store.calls)
    assert new_store.writes == old_store.writes
    assert new_transport.commands == old_transport.commands
    assert len(old_loader.calls) == 1
    assert len(new_loader.calls) == (1 if kind is None else 0)
    record_property("optional_planning_before", len(old_loader.calls))
    record_property("optional_planning_after", len(new_loader.calls))


@pytest.mark.parametrize("kind,status", [("mixer", "auxiliary_completed"), ("injector", "auxiliary_control_pulse_off_verified"), ("borehole", "borehole_completed")])
def test_failed_optional_planner_no_longer_prevents_due_recovery(kind, status):
    prior_store, prior_transport = Store(kind), OffOnlyTransport()
    old = invoke(prior_store, prior_transport, Evidence(fail=True), function=predecessor())
    assert old["status"] == "managed_device_evidence_unavailable"
    assert prior_store.calls == prior_transport.commands == []
    store, transport, loader = Store(kind), OffOnlyTransport(), Evidence(fail=True)
    result = invoke(store, transport, loader, environ={FLAGS[0]: "true"})
    assert result["status"] == status and result["blocks_bc"] is True
    assert result["managed_device_recovery"] is True and loader.calls == []
    assert [c["state"] for c in transport.commands] == ["OFF"]
    assert all(not action.endswith("before_on") for action in store.calls)


@pytest.mark.parametrize("kind", ["mixer", "borehole"])
def test_active_not_due_skips_planning_without_extra_active_reads(kind):
    store = Store(kind)
    if kind == "mixer": store.aux = active(kind, due=False)
    else: store.borehole = active(kind, due=False)
    transport, loader = OffOnlyTransport(), Evidence(fail=True)
    result = invoke(store, transport, loader)
    assert result["status"] == ("auxiliary_active" if kind == "mixer" else "borehole_active")
    assert transport.commands == loader.calls == []
    assert store.loads == ({"load_active_auxiliary": 2, "load_active_borehole": 1} if kind == "mixer" else {
        "load_active_auxiliary": 1, "load_active_borehole": 2})


def test_auxiliary_priority_when_both_are_active_is_unchanged():
    store, transport, loader = Store("mixer", both=True), OffOnlyTransport(), Evidence(fail=True)
    result = invoke(store, transport, loader)
    assert result["status"] == "auxiliary_completed" and store.borehole is not None
    assert all(c["device_id"] == "100204d497" for c in transport.commands)
    assert store.loads["load_active_borehole"] == 1 and loader.calls == []


@pytest.mark.parametrize("kind", ["mixer", "borehole"])
def test_active_disappearing_on_coordinator_reload_never_mints_new_on(kind):
    store, transport, loader = Store(kind, vanish=True), OffOnlyTransport(), Evidence(fail=True)
    result = invoke(store, transport, loader)
    assert result["status"] == ("auxiliary_not_eligible" if kind == "mixer" else "borehole_eligibility_invalid")
    assert result["blocks_bc"] is True and transport.commands == loader.calls == store.writes == []


@pytest.mark.parametrize("kind", ["mixer", "borehole"])
def test_ambiguous_off_uses_existing_three_attempt_budget_and_replay_containment(kind):
    store, transport, loader = Store(kind), OffOnlyTransport(accepted=False, verified=False), Evidence(fail=True)
    first = invoke(store, transport, loader)
    second = invoke(store, transport, loader)
    expected = "auxiliary_shutdown_intervention_required" if kind == "mixer" else "borehole_shutdown_unverified"
    assert first["status"] == second["status"] == expected
    assert first["hardware_commands"] == 3 and second["hardware_commands"] == 0
    assert len(transport.commands) == 3 and len({c["idempotency_key"] for c in transport.commands}) == 3
    assert first["blocks_bc"] is second["blocks_bc"] is True and loader.calls == []
    assert not any(action in {"record_auxiliary_completed", "record_borehole_completed"} for action, _ in store.writes)


@pytest.mark.parametrize("kind", ["mixer", "borehole"])
def test_ambiguous_command_with_authoritative_off_keeps_existing_completion(kind):
    store, transport, loader = Store(kind), OffOnlyTransport(accepted=False, verified=True), Evidence(fail=True)
    result = invoke(store, transport, loader)
    assert result["status"] == ("auxiliary_completed" if kind == "mixer" else "borehole_completed")
    assert result["hardware_commands"] == 3 and len(transport.reads) == 1 and loader.calls == []


@pytest.mark.parametrize("kind", ["mixer", "borehole"])
def test_readback_failure_remains_unknown_and_never_records_completion(kind):
    store, transport = Store(kind), OffOnlyTransport(raise_read=True)
    result = invoke(store, transport, Evidence(fail=True))
    assert result["status"] in {"auxiliary_shutdown_intervention_required", "borehole_shutdown_unverified"}
    assert not any(action in {"record_auxiliary_completed", "record_borehole_completed"} for action, _ in store.writes)


@pytest.mark.parametrize("action", ["load_active_auxiliary", "load_active_borehole"])
def test_unavailable_canonical_store_holds_before_optional_planner(action):
    store, loader, transport = Store(fail_action=action), Evidence(fail=True), OffOnlyTransport()
    result = invoke(store, transport, loader)
    assert result["status"] == "managed_device_store_unavailable" and result["blocks_bc"] is False
    assert loader.calls == transport.commands == []


@pytest.mark.parametrize("failure", [RuntimeError("canonical-read-error"), managed.ManagedDevicePlanningUnavailable({"status": "must-propagate"})])
def test_recovery_errors_are_not_relabeled_as_optional_planning_failure(failure):
    store = Store("mixer", fail_action="load_auxiliary_off_attempts", failure=failure)
    with pytest.raises(type(failure)):
        invoke(store, OffOnlyTransport(), Evidence())


def test_provider_write_exception_keeps_existing_propagation():
    with pytest.raises(RuntimeError, match="synthetic-provider-write-error"):
        invoke(Store("mixer"), OffOnlyTransport(raise_write=True), Evidence(fail=True))


@pytest.mark.parametrize("stage", ["load", "refresh", "build"])
def test_idle_original_planning_error_result_is_preserved(monkeypatch, stage):
    loader = Evidence(fail=stage == "load")
    def fail(*_args, **_kwargs): raise RuntimeError("planning-boundary-error")
    if stage == "refresh": monkeypatch.setattr(runtime, "_refresh_active_irrigation_readback", fail)
    if stage == "build": monkeypatch.setattr(runtime, "build_water_energy_plan", fail)
    old = invoke(Store(), OffOnlyTransport(), loader, function=predecessor())
    new = invoke(Store(), OffOnlyTransport(), Evidence(fail=stage == "load"))
    assert new == old == {**runtime._safe("managed_device_evidence_unavailable"), "blocks_bc": False}


def test_later_packet_error_still_propagates_instead_of_becoming_planning_hold():
    def bad_packet(**kwargs):
        return {"fertilizer_executions": [{"device_type": "fertilizer_mixer", "completed_at": NOW.isoformat(),
                  "verified_runtime_minutes": "not-a-number"}]}, NOW.date().isoformat(), kwargs["now"]
    for fn in (predecessor(), runtime.run_rootline_managed_device_reassessment):
        with pytest.raises(ValueError): invoke(Store(), OffOnlyTransport(), bad_packet, function=fn)


@pytest.mark.parametrize("flag", FLAGS)
def test_idle_enabled_and_reenabled_calls_use_fresh_planning_once_each(monkeypatch, flag):
    loader, transport, store = Evidence(), OffOnlyTransport(), Store()
    observed = []
    original = runtime.build_water_energy_plan
    def build(evidence, *args, **kwargs):
        observed.append(evidence["synthetic_generation"])
        return original(evidence, *args, **kwargs)
    monkeypatch.setattr(runtime, "build_water_energy_plan", build)
    for value in ("true", "false", " TRUE "):
        result = invoke(store, transport, loader, environ={flag: value})
        assert result["status"] == "no_eligible_managed_device_task"
    assert observed == [1, 2, 3] and len(loader.calls) == 3 and transport.commands == []
    assert store.loads == {"load_active_auxiliary": 6, "load_active_borehole": 6}


def test_dictionary_cycle_api_remains_valid_without_a_factory():
    store, transport = Store(), OffOnlyTransport()
    result = managed.run_rootline_managed_device_cycle(evidence={}, transport=transport,
        environ={}, store=store, now=NOW)
    assert result["status"] == "no_eligible_managed_device_task" and transport.commands == []


class HistoryConnection:
    def __init__(self, calls): self.calls = calls
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self
    def execute(self, query, _params=None):
        label = ("outcomes" if "rootline_operational_intake" in query else
                 "credits" if "credit_json" in query else
                 "clock" if "clock_timestamp" in query else
                 "irrigation_events" if "from public.irrigation_events" in query else
                 "parent_execution_history" if "record_job_resolution" in query else "executions")
        self.calls.append(label)
    def fetchall(self): return []
    def fetchone(self): return (NOW,)


def test_actual_scheduled_gateway_keeps_first_specialist_history_read_but_skips_second(monkeypatch, record_property):
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.oom_sakkie.automatic_reassessment_scheduler import SCHEDULER_IDENTITY
    from modules.oom_sakkie import bounded_postgres_read
    from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history
    monkeypatch.setattr("modules.oom_sakkie.documents_green_followup_runtime.recover_documents_green_physical_follow_up", lambda **_: {"handled": False})
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.reassess_due_mixer_presence", lambda **_: {"status": "no_reassessable_mixer_presence"})
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster", lambda *_a, **_k: {})
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_breeding_attention_source_snapshot", lambda **_: {})
    monkeypatch.setattr("modules.sales.sales_transaction_read.list_sales_transactions", lambda: ({"success": True, "sales_transactions": []}, 200))
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager", lambda **_: {"status": "synthetic_quiet", "telegram_sends": 0})
    counts = []
    for fn in (predecessor(), runtime.run_rootline_managed_device_reassessment):
        reads, specialist_calls, optional_calls = [], [], []
        monkeypatch.setattr(bounded_postgres_read, "connect_bounded_read", lambda **_: HistoryConnection(reads))
        def history_projection():
            value = read_canonical_irrigation_history(connect=lambda: HistoryConnection(reads), now=NOW)
            assert value["status"] == "Available"
            return value
        def optional(**kwargs):
            optional_calls.append(1)
            evidence = plan_module._read_managed_device_evidence("synthetic", NOW)
            history_projection()
            return evidence, NOW.date().isoformat(), NOW
        def specialist():
            specialist_calls.append(1)
            plan_module._read_managed_device_evidence("synthetic", NOW)
            history_projection()
            return {"success": True, "overall_status": "Hold", "operating_date": NOW.date().isoformat(),
                "result_id": "synthetic-result", "generation": "synthetic-generation",
                "evidence_cutoff": (NOW - timedelta(seconds=1)).isoformat(),
                "recommendations": [], "owner_brief": {"family_fact_needed": ""}}
        schedules, lifecycle = {}, {}
        def schedule(action, identity, payload):
            if action in {"load_latest_outcome", "load_schedule"}: return None
            key = identity if action == "claim_schedule" else identity + "-OUTCOME"
            created = key not in schedules; schedules.setdefault(key, dict(payload))
            return {"success": True, "created": created}
        def state(action, identity, payload):
            if action == "load_delivered": return None
            if action == "load_identity": return lifecycle.get(identity)
            if action in {"record_observation", "claim_pending"}:
                created = identity not in lifecycle; lifecycle.setdefault(identity, payload)
                return {"success": True, "created": created}
            if action == "mark_delivered":
                lifecycle[identity] = {**lifecycle[identity], **payload}; return {"success": True}
            return None
        store, transport = Store("mixer"), OffOnlyTransport()
        env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true", "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
               "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42", FLAGS[0]: "true"}
        payload = {"scheduler_identity": SCHEDULER_IDENTITY, "specialist": "ROOTLINE", "due_at": NOW.isoformat(),
            "evidence_cutoff": (NOW - timedelta(seconds=1)).isoformat(), "owner_user_id": "42", "chat_id": "42",
            "trigger": "declared_time", "trigger_id": "synthetic-schedule", "trigger_timestamp": NOW.isoformat()}
        result, status = handle_rootline_reassessment_trigger(payload,
            {"X-Oom-Sakkie-Telegram-Token": "x" * 40}, env, scheduler_now=NOW,
            specialist_loader=specialist, schedule_store=schedule, state_store=state,
            daily_plan_generator=lambda _: {"success": True, "status": "daily_plan_created", "readback_bound": True,
                "daily_plan": {"daily_plan_id": "synthetic-plan", "operating_date": NOW.date().isoformat(), "generation": 1, "evidence_sha256": "a" * 64}},
            family_delivery=lambda *_a, **_k: {"success": True, "status": "family_message_delivered", "telegram_message_id": "synthetic-message", "telegram_sends": 1},
            managed_device_cycle=lambda **kwargs: invoke(store, transport, optional, function=fn,
                environ=kwargs["environ"], now=kwargs["now"]))
        assert status == 200 and result["execution_status"] == "auxiliary_completed"
        assert len(specialist_calls) == 1 and [c["state"] for c in transport.commands] == ["OFF"]
        counts.append((len(optional_calls), Counter(reads)))
    labels = ("executions", "outcomes", "credits", "clock", "irrigation_events", "parent_execution_history")
    assert counts == [(1, {label: 2 for label in labels}), (0, {label: 1 for label in labels})]
    record_property("first_specialist_managed_selects_retained", 2)
    record_property("first_specialist_parent_execution_select_retained", 1)
    record_property("duplicate_optional_managed_selects_removed", 2)
    record_property("duplicate_optional_parent_execution_select_removed", 1)
    record_property("synthetic_boundary_only_not_live_savings", True)


@pytest.mark.parametrize("kind", ["mixer", "borehole", "both"])
def test_activity_appearing_during_planning_is_recovered_before_any_new_start(kind):
    store, transport, calls = Store(), OffOnlyTransport(), []
    def load(**kwargs):
        calls.append(1)
        if kind in {"mixer", "both"}: store.aux = active("mixer")
        if kind in {"borehole", "both"}: store.borehole = active("borehole")
        return {}, NOW.date().isoformat(), kwargs["now"]
    result = invoke(store, transport, load, environ={flag: "true" for flag in FLAGS})
    assert result["status"] == ("borehole_completed" if kind == "borehole" else "auxiliary_completed")
    assert result["managed_device_recovery"] is True and len(calls) == 1
    assert [c["state"] for c in transport.commands] == ["OFF"]
    assert not any(action.endswith("before_on") for action in store.calls)
    if kind == "both": assert store.borehole is not None


@pytest.mark.parametrize("action", ["load_active_auxiliary", "load_active_borehole"])
def test_post_planning_store_unavailable_holds_before_any_start(action):
    store, transport, calls = Store(), OffOnlyTransport(), []
    def load(**kwargs):
        calls.append(1); store.fail_action = action
        return {}, NOW.date().isoformat(), kwargs["now"]
    result = invoke(store, transport, load, environ={flag: "true" for flag in FLAGS})
    assert result["status"] == "managed_device_store_unavailable" and result["blocks_bc"] is False
    assert calls == [1] and transport.commands == store.writes == []
