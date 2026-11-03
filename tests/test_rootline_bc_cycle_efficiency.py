"""Synthetic real scheduler/admission paths, with a shared advancing request clock."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from modules.telemetry import rootline_cycle_budget as budget
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable
from tests.test_rootline_execution_runtime import Store, Transport, NOW, evidence, controller, plan
from tests.test_rootline_active_supervision import ScheduleStore, ENV, HEADERS, payload, reports
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger


class Clock:
    def __init__(self):
        self.elapsed = 0.0
        self.events = []
    def monotonic(self):
        return self.elapsed
    def now(self):
        return NOW + timedelta(seconds=self.elapsed)
    def spend(self, operation, seconds):
        self.events.append((operation, self.elapsed))
        self.elapsed += seconds


class Path:
    """Replace I/O only: gateway, runtime, eligibility and coordinator remain real."""
    def __init__(self, monkeypatch, *, managed_seconds=22, evidence_seconds=8,
                 provider_seconds=18, fail=None, revoke=False, claim_seconds=.7, refuse=False):
        self.clock = Clock()
        self.backing = Store()
        self.schedules = ScheduleStore()
        self.transport = Transport()
        self.controls = []
        self.authority_calls = []
        self.maintenance_calls = []
        self.observations = {}
        self.managed_seconds = managed_seconds
        self.evidence_seconds = evidence_seconds
        self.provider_seconds = provider_seconds
        self.fail = fail
        self.refuse = refuse
        self.revoke = revoke
        self.claim_seconds = claim_seconds
        monkeypatch.setattr(budget.time, "monotonic", self.clock.monotonic)
        monkeypatch.setattr(runtime, "build_water_energy_plan", lambda *a, **k: plan())
        original_maintenance = runtime._persist_stale_parent_resolutions
        def maintenance(*args):
            self.maintenance_calls.append(self.clock.elapsed)
            return original_maintenance(*args)
        monkeypatch.setattr(runtime, "_persist_stale_parent_resolutions", maintenance)
        original_safety = self.transport.read_safety_configuration
        def safety(**kwargs):
            self.clock.spend("provider safety", 19)
            return original_safety(**kwargs)
        self.transport.read_safety_configuration = safety
        original_command = self.transport.set_state
        def command(**kwargs):
            self.clock.spend("provider " + kwargs["state"], 1)
            return original_command(**kwargs)
        self.transport.set_state = command

    def store(self, action, item):
        self.clock.spend("store " + action,
            self.claim_seconds if action == "claim_before_on" else .7)
        if action == self.fail:
            if self.refuse:
                return {"success": False, "created": False}
            raise RootlineExecutionStoreUnavailable("synthetic persistence failure")
        return self.backing(action, item)

    def loader(self, **kwargs):
        self.clock.spend("canonical weather and history", self.evidence_seconds)
        return evidence(), NOW.date().isoformat(), NOW

    def readback(self, **kwargs):
        self.clock.spend("provider controller", self.provider_seconds)
        return {**controller(), "trusted_receipt_at": self.clock.now().isoformat()}

    def authority(self, *args):
        self.clock.spend("authority transaction", 2.2)
        self.authority_calls.append(self.clock.elapsed)
        return not (self.revoke and len(self.authority_calls) > 1)

    def state(self, action, identity, item):
        if action.startswith("load_"):
            return self.observations.get(identity)
        self.clock.spend("observation " + action, .7)
        self.observations[identity] = deepcopy(item)
        return {"success": True, "created": True}

    def cycle(self, **kwargs):
        value = runtime.run_rootline_execution_cycle(**kwargs, store=self.store,
            token_store=object(), transport=self.transport, clock=self.clock.now,
            evidence_loader=self.loader, readback=self.readback,
            authority_checker=self.authority)
        self.controls.append(value)
        return value

    def managed(self, **kwargs):
        assert budget.work_deadline() == 140
        assert budget.on_deadline() == 140
        with budget.mandatory_safety():
            self.clock.spend("independent borehole and managed supervision", self.managed_seconds)
        return {"success": True, "status": "borehole_active", "hardware_commands": 0}

    def gateway(self, *, reports_due=False, supervisor=None, report_loader=None,
                plan_generator=None):
        if not reports_due and not self.schedules.rows:
            self.schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
                "next_due_at": (NOW + timedelta(minutes=30)).isoformat()}
        def unavailable_report(**kwargs):
            pytest.fail("optional reporting must not run on a safety-only or expired tick")
        source = {**ENV, "ROOTLINE_BOREHOLE_ENABLED": "true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED": "true", "ROOTLINE_A_ENABLED": "false",
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "false", "ROOTLINE_ESKOM_ENABLED": "false"}
        request = payload(due_at=NOW.isoformat(), trigger_timestamp=NOW.isoformat(),
            evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat())
        return handle_rootline_reassessment_trigger(request, HEADERS, source,
            specialist_loader=report_loader or unavailable_report, state_store=self.state,
            daily_plan_generator=plan_generator,
            schedule_store=self.schedules, scheduler_now=NOW,
            family_delivery=lambda *a, **k: {"success": True, "telegram_message_id": "synthetic"},
            active_supervision_cycle=supervisor or (lambda **k: {
                "success": True, "status": "no_active_irrigation", "active_execution_found": False}),
            managed_device_cycle=self.managed, execution_cycle=self.cycle)


def test_actual_scheduled_path_completes_on_with_accumulated_latency_and_no_duplicate(monkeypatch):
    path = Path(monkeypatch)
    value, status = path.gateway()
    assert path.controls[0]["status"] == "segment_started", path.controls
    assert status == 200 and value["hardware_commands"] == 1
    assert [row["state"] for row in path.transport.calls] == ["ON"]
    assert 90 < path.clock.elapsed < 140
    assert len(path.authority_calls) == 2  # current invocation and fresh command-edge invocation
    assert len(path.maintenance_calls) == 1  # never repeated during pre-ON reads
    assert sum(name == "provider controller" for name, _ in path.clock.events) == 2
    assert value["managed_device_status"] == "borehole_active"
    assert datetime.fromisoformat(value["supervision_next_due_at"]) == NOW+timedelta(minutes=1)
    replay, _ = path.gateway()
    assert replay["status"] == "scheduled_reassessment_replayed_noop"
    assert len(path.transport.calls) == 1


def test_slow_current_path_defers_before_claim_and_records_next_minute(monkeypatch):
    path = Path(monkeypatch, managed_seconds=110)
    value, status = path.gateway()
    assert status == 202
    assert path.controls[0]["status"] == "execution_cycle_deadline_deferred"
    assert path.transport.calls == []
    assert not any(action == "claim_before_on" for action, _ in path.backing.rows)
    saved = [v for k, v in path.schedules.rows.items() if k.endswith(":outcome")][-1]
    assert datetime.fromisoformat(saved["supervision_next_due_at"]) == NOW+timedelta(minutes=1)
    assert saved["managed_device_status"] == "borehole_active"


def test_fresh_command_edge_authority_revocation_blocks_on(monkeypatch):
    path = Path(monkeypatch, revoke=True)
    path.gateway()
    assert path.controls[0]["status"] == "execution_eligibility_changed"
    assert len(path.authority_calls) == 2 and path.transport.calls == []
    assert not any(action == "claim_before_on" for action, _ in path.backing.rows)


@pytest.mark.parametrize("fail", ["record_on_outcome", "mark_active"])
@pytest.mark.parametrize("refuse", [False, True])
def test_on_success_then_store_failure_preserves_attempt_and_uncertainty(monkeypatch, fail, refuse):
    path = Path(monkeypatch, fail=fail, refuse=refuse)
    value, status = path.gateway()
    control = path.controls[0]
    assert status == 202 and control["status"] == "execution_store_degraded_hold"
    assert control["provider_command_attempts"] == control["hardware_commands"] == 1
    assert control["effects_unknown"] is True and control["provider_effects_unknown"] is True
    assert control["canonical_write_state"] == "unknown"
    assert control["current_segment_consumed"] is None
    assert value["hardware_commands"] == 1 and value["effects_unknown"] is True
    saved = [v for k, v in path.schedules.rows.items() if k.endswith(":outcome")][-1]
    assert saved["hardware_commands"] == 1 and saved["provider_effects_unknown"] is True
    assert [row["state"] for row in path.transport.calls] == ["ON"]


def test_expired_optional_budget_keeps_active_stop_and_independent_supervision(monkeypatch):
    path = Path(monkeypatch, managed_seconds=1)
    from tests.test_rootline_active_supervision import ExecutionStore, Transport as OffTransport, active
    from tests.test_rootline_active_weather_stop import dry_weather_reader
    active_row = active()
    active_row.update(claimed_at=(NOW-timedelta(seconds=3600)).isoformat(),
        primary_stop_deadline=(NOW-timedelta(seconds=1)).isoformat(),
        native_fail_stop_deadline=(NOW-timedelta(seconds=1)).isoformat())
    backing, transport = ExecutionStore(active_row), OffTransport()
    def supervisor(**kwargs):
        path.clock.spend("prior request work", 141)
        assert budget.work_deadline() is None
        return runtime.supervise_rootline_active_execution(**kwargs, store=backing,
            transport=transport, token_store=object(), clock=path.clock.now,
            active_weather_reader=dry_weather_reader)
    value, status = path.gateway(supervisor=supervisor)
    assert status == 202 and value["hardware_commands"] == 1
    assert [row["state"] for row in transport.calls] == ["OFF"]
    assert any(name.startswith("independent borehole") for name, _ in path.clock.events)
    assert path.controls[0]["status"] == "execution_cycle_deadline_deferred"
    assert path.transport.calls == []
    assert budget.work_deadline() is None and budget.on_deadline() is None


def test_report_deferral_preserves_known_start_and_durable_result(monkeypatch):
    path = Path(monkeypatch, managed_seconds=45)
    value, status = path.gateway(reports_due=True)
    assert path.controls[0]["status"] == "segment_started"
    assert 115 < path.clock.elapsed < 140
    assert status == 202 and value["status"] == "scheduled_rootline_reporting_deadline_deferred"
    assert value["hardware_commands"] == 1 and value["report_effects_unknown"] is False
    saved = [v for k, v in path.schedules.rows.items() if k.endswith(":outcome")][-1]
    assert saved["execution_status"] == "segment_started" and saved["hardware_commands"] == 1


def test_nested_scope_does_not_extend_on_deadline_when_safety_budget_is_lifted(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(budget.time, "monotonic", clock.monotonic)
    with budget.cycle_budget(10):
        with budget.mandatory_safety():
            clock.elapsed = 11
            assert budget.remaining_seconds(3) == 3
            with budget.cycle_budget(30):
                assert budget.work_deadline() == 30 and budget.on_deadline() == 10
        with pytest.raises(budget.RootlineCycleDeadlineExceeded):
            budget.remaining_seconds()
    assert budget.work_deadline() is budget.on_deadline() is None


def test_connection_budget_expiry_rolls_back_current_transaction_and_restores_scope(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read as db
    clock = Clock()
    monkeypatch.setattr(budget.time, "monotonic", clock.monotonic)
    events = []
    class Connection:
        def __enter__(self):
            events.append("begin"); return self
        def __exit__(self, kind, value, tb):
            events.append("rollback" if kind else "commit")
            events.append("close")
        def cursor(self):
            return self
        def execute(self, sql, params=None, **kwargs):
            events.append((sql, params))
        def fetchone(self):
            return (1,)
    with budget.cycle_budget(1):
        with pytest.raises(budget.RootlineCycleDeadlineExceeded):
            with db.connect_bounded_rootline_postgres(database_url="synthetic", read_only=False,
                    connect=lambda *a, **k: Connection()) as connection:
                assert connection.execute("select 1").fetchone() == (1,)
                clock.elapsed = 2
                connection.execute("insert into synthetic values (2)")
    assert events[-2:] == ["rollback", "close"]
    assert not any(isinstance(row, tuple) and row[0].startswith("insert") for row in events)
    assert any(isinstance(row, tuple) and row[0] == "set local statement_timeout='1000ms'"
        for row in events)
    assert budget.work_deadline() is None


def test_read_only_fanout_inherits_request_budget_and_preserves_caller_context():
    import time
    from modules.telemetry.rootline_bounded_read_group import run_bounded_read_group
    deadline = time.monotonic()+1
    with budget.cycle_budget(deadline):
        result = run_bounded_read_group({"a": budget.work_deadline,
            "b": budget.on_deadline}, max_workers=2, deadline_seconds=30)
        assert result == {"a": deadline, "b": deadline}
        assert budget.work_deadline() == deadline
    assert budget.work_deadline() is budget.on_deadline() is None


def test_final_sender_never_sends_late_on_but_keeps_off_available(monkeypatch):
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty, RequestBudget
    from tests.test_rootline_ifttt_transport import Response
    clock, calls = Clock(), []
    monkeypatch.setattr(budget.time, "monotonic", clock.monotonic)
    def consume_remaining(*args, **kwargs):
        clock.elapsed = 11
        return 100
    monkeypatch.setattr(RequestBudget, "begin_on", consume_remaining)
    transport = RootlineIFTTTTransport(token_store=object(),
        environ={"ROOTLINE_IFTTT_MAKER_KEY": "synthetic-key"},
        http_open=lambda *a, **k: calls.append(True) or Response())
    with budget.cycle_budget(10), execution_duty({"execution_id": "SYNTHETIC",
            "claimed_at": NOW.isoformat(), "primary_stop_deadline": (NOW+timedelta(minutes=5)).isoformat()}):
        with budget.mandatory_safety():
            on = transport.set_state(device_id="100204e9bc", channel=1,
                state="ON", idempotency_key="SYNTHETIC:ON")
            assert on["provider_command_attempted"] is False and calls == []
            assert on["status"] == "provider_command_deadline_reached"
            off = transport.set_state(device_id="100204e9bc", channel=1,
                state="OFF", idempotency_key="SYNTHETIC:OFF:1")
            assert off["accepted_unambiguous"] is True and calls == [True]


def test_authority_uses_one_session_and_rechecks_revocation_without_cache(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read as db
    from tests.test_rootline_commissioning_bridges import record_for, digest
    keys = ["ifttt_ewelink:ewelink_owner_account:100204e9bc:"+str(ch) for ch in (1, 2)]
    records = {}
    for key, zone in zip(keys, ("B12345", "C12345")):
        row = record_for(key, "gravity_irrigation_valve", 3599)
        row["physical_effect"] = zone+" irrigation water flow"
        row["historical_commissioning_evidence"] = {}
        records[key] = row
    calls, queries, revoked = [], [], [False]
    policy = {"synthetic": "validated by the unchanged separate policy contract tests"}
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return self
        def execute(self, sql, params=None):
            queries.append(sql)
            if "rootline_device_registry where" in sql:
                row = records[params[0]]
                self.row = ("rootline_device_spine.v1", row, digest(row), 1, digest(row))
            elif "rootline_device_commissioning_evidence e" in sql:
                ref = records[keys[0]]["commissioning_evidence"]["supervised"]
                self.row = (ref["evidence_id"], ref["sha256"], True)
            elif "rootline_standing_authorities a" in sql:
                self.row = ("synthetic:authority", "1", "a"*64, not revoked[0])
            elif "select issuer,policy_payload" in sql:
                self.row = ("owner_policy", policy, "a"*64, True, revoked[0], not revoked[0])
            else:
                pytest.fail("unexpected authority query")
        def fetchone(self): return self.row
    def connect(**kwargs):
        assert kwargs["read_only"] is True
        calls.append(True)
        return Connection()
    monkeypatch.setattr(db, "connect_bounded_rootline_postgres", connect)
    # Policy schema validation itself is unchanged and separately covered; all
    # actual device/digest/evidence/revocation readers below remain real.
    monkeypatch.setattr(runtime, "_bc_authority_policy_proven", lambda p, a, k: p is policy and list(k) == keys)
    artifact = {"zone_id": "C12345", "channel": 2, "maximum_duration_seconds": 3599}
    assert runtime._canonical_standing_authority_proven("synthetic", artifact) is True
    assert len(calls) == 1 and len(queries) == 7
    revoked[0] = True
    assert runtime._canonical_standing_authority_proven("synthetic", artifact) is False
    assert len(calls) == 2
    assert budget.work_deadline() is None


@pytest.mark.parametrize("fail", ["record_eligibility", "claim_before_on"])
def test_uncertain_pre_on_persistence_never_claims_zero_canonical_effect(monkeypatch, fail):
    path = Path(monkeypatch, fail=fail)
    value, status = path.gateway()
    control = path.controls[0]
    assert status == 202 and control["canonical_write_uncertain"] is True
    assert control["canonical_write_state"] == "unknown" and control["writes_farm_data"] is None
    assert control["current_segment_consumed"] is (None if fail == "claim_before_on" else False)
    assert path.transport.calls == [] and control["hardware_commands"] == 0
    assert value["writes_farm_data"] is None
    saved = path.schedules.rows[value["schedule_identity"]+":outcome"]
    assert saved["writes_farm_data"] is None


def test_post_claim_deadline_keeps_reconciliation_and_does_not_send_on(monkeypatch):
    path = Path(monkeypatch, claim_seconds=60)
    path.gateway()
    assert any(action == "claim_before_on" for action, _ in path.backing.rows)
    assert not any(row["state"] == "ON" for row in path.transport.calls)
    assert any(action == "record_on_outcome" for action, _ in path.backing.rows)
    assert any(action == "contain_zone" for action, _ in path.backing.rows)


def test_slow_statement_configuration_cannot_issue_a_late_mutation(monkeypatch):
    from modules.oom_sakkie.bounded_postgres_read import _CycleBudgetCursor
    clock, queries = Clock(), []
    monkeypatch.setattr(budget.time, "monotonic", clock.monotonic)
    class Cursor:
        def execute(self, sql, params=None):
            queries.append(sql)
            clock.elapsed = 2
    with pytest.raises(budget.RootlineCycleDeadlineExceeded):
        _CycleBudgetCursor(Cursor(), 1).execute("insert into synthetic values (1)")
    assert len(queries) == 1 and queries[0].startswith("set local statement_timeout")


def test_post_on_provider_read_exception_preserves_attempt_in_gateway_and_receipt(monkeypatch):
    path = Path(monkeypatch)
    def invalid_readback(**kwargs):
        raise RuntimeError("ewelink_safety_readback_invalid")
    path.transport.read_output_state = invalid_readback
    value, status = path.gateway()
    control = path.controls[0]
    assert status == 202 and control["status"] == "execution_cycle_effects_unproven"
    assert [row["state"] for row in path.transport.calls] == ["ON"]
    assert control["hardware_commands"] == control["provider_command_attempts"] == 1
    assert value["hardware_commands"] == 1 and value["effects_unknown"] is True
    assert value["writes_farm_data"] is None
    saved = path.schedules.rows[value["schedule_identity"]+":outcome"]
    assert saved["hardware_commands"] == 1 and saved["provider_effects_unknown"] is True
    assert saved["writes_farm_data"] is None
    assert not any(action in {"mark_active", "record_completed"} for action, _ in path.backing.rows)
    replay, _ = path.gateway()
    assert replay["status"] == "scheduled_reassessment_replayed_noop"
    assert len(path.transport.calls) == 1


def report_inputs(path, *, plan_seconds=1):
    def loader():
        path.clock.spend("report evidence", 1)
        return {"success": True, "overall_status": "Hold", "operating_date": NOW.date().isoformat(),
            "result_id": "SYNTHETIC-REPORT", "generation": "SYNTHETIC-GENERATION",
            "evidence_cutoff": (NOW-timedelta(seconds=2)).isoformat(),
            "recommendations": [], "owner_brief": {"family_fact_needed": ""}}
    def generator(current):
        path.clock.spend("date-stable report plan", plan_seconds)
        return {"success": True, "created": False, "status": "daily_plan_reused",
            "readback_bound": True, "daily_plan": {"daily_plan_id": "SYNTHETIC-PLAN",
                "operating_date": NOW.date().isoformat(), "generation": "SYNTHETIC-GENERATION",
                "evidence_sha256": "a"*64}}
    return loader, generator


def test_healthy_report_due_path_preserves_on_and_clamps_read_only_wait(monkeypatch, reports):
    import concurrent.futures
    from threading import current_thread
    path = Path(monkeypatch)
    loader, generator = report_inputs(path, plan_seconds=20)
    waits, contexts, stages = [], [], []
    original_wait = concurrent.futures.wait
    def bounded_wait(futures, timeout):
        waits.append((timeout, budget.work_deadline()-path.clock.elapsed))
        return original_wait(futures, timeout=timeout)
    monkeypatch.setattr(concurrent.futures, "wait", bounded_wait)
    def herd(*args):
        contexts.append(budget.work_deadline())
        return {}
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster", herd)
    def daily(**kwargs):
        stages.append(current_thread().name)
        path.clock.spend("synchronous daily presentation", 1)
        return {"success": True, "status": "daily_farm_manager_unchanged", "telegram_sends": 0}
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager", daily)
    value, status = path.gateway(reports_due=True, report_loader=loader, plan_generator=generator)
    assert status == 200, value
    assert path.controls[0]["status"] == "segment_started"
    assert value["hardware_commands"] == 1 and [r["state"] for r in path.transport.calls] == ["ON"]
    assert len(path.controls) == 1 and path.clock.elapsed < 140
    assert waits and all(0 < timeout <= remaining < 12 for timeout, remaining in waits)
    assert contexts == [140]
    assert stages == [current_thread().name]
    saved = path.schedules.rows[value["schedule_identity"]+":outcome"]
    assert saved["status"] == "completed" and saved["hardware_commands"] == 1
    assert saved["execution_status"] == "segment_started"


def test_expiry_during_synchronous_reporting_preserves_prior_control_and_known_delivery(monkeypatch, reports):
    from threading import current_thread
    path = Path(monkeypatch)
    loader, generator = report_inputs(path)
    calls = []
    def daily(**kwargs):
        calls.append(current_thread().name)
        path.clock.spend("synchronous known report delivery", 50)
        return {"success": True, "status": "daily_farm_manager_delivered", "telegram_sends": 1}
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager", daily)
    value, status = path.gateway(reports_due=True, report_loader=loader, plan_generator=generator)
    assert status == 202 and value["status"] == "scheduled_rootline_reporting_unproven"
    assert value["error_type"] == "RootlineCycleDeadlineExceeded"
    assert value["hardware_commands"] == 1 and value["report_effects_unknown"] is True
    assert value["telegram_sends"] == 2  # known start plus completed daily delivery
    assert calls == [current_thread().name] and len(path.controls) == 1
    assert [r["state"] for r in path.transport.calls] == ["ON"]
    saved = path.schedules.rows[value["schedule_identity"]+":outcome"]
    assert saved["hardware_commands"] == 1 and saved["telegram_sends"] == 2
    assert saved["report_effects_unknown"] is True and saved["status"] == "contained"
