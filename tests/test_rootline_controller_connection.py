"""Connectivity polling must not reconstruct control authority or relay evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial
import pytest
from modules.telemetry import rootline_home_assistant as ha
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport

NOW = datetime(2026, 11, 27, 10, 4, tzinfo=timezone.utc)
DEVICE = "100204d497"
SOURCE = {"ROOTLINE_SONOFF_TRANSPORT": "home_assistant"}


def packet(device=DEVICE, age=0, state="online"):
    return {"contract_version": "rootline_sonoff_observation.v1", "device_id": device,
        "model": ha.MODELS[device], "uiid": 138 if device == "1002851416" else 4,
        "control_commands": 0, "observer_epoch": "a"*32,
        "source_authentication": "unauthenticated_sonoff_lan_protocol",
        "generated_at": NOW.isoformat(),
        # A cached relay state is deliberately irrelevant to connectivity.
        "channels": [{"channel": 1, "state": "ON", "fresh": False}],
        "controller_availability": {"state": state, "checked_at": (NOW-timedelta(seconds=age)).isoformat(),
            "source": "controller_query_unanswered" if state == "offline" else "correlated_controller_query",
            "output_state": "Unknown"}}


class Client:
    def __init__(self, replies): self.replies = list(replies); self.calls = []
    def __call__(self, environ): assert environ == SOURCE; return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def request(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        value = self.replies.pop(0)
        if isinstance(value, BaseException): raise value
        return deepcopy(value)


def read(client, device=DEVICE):
    return ha.read_controller_connection(device, environ=SOURCE, now=NOW, client_factory=client)


@pytest.mark.parametrize("state", ["online", "offline", "unknown"])
def test_fresh_snapshot_reuses_only_original_reachability(state):
    envelope = packet(age=32, state=state); client = Client([envelope])
    result = read(client)
    assert result == envelope["controller_availability"]
    assert client.calls == [("rootline_observer/snapshot", {"device_id": DEVICE})]
    assert set(result) == {"state", "source", "checked_at", "output_state"}
    assert result["output_state"] == "Unknown"


@pytest.mark.parametrize("first", [None, {}, {"state": "unknown"}, packet(age=60)["controller_availability"],
    {**packet()["controller_availability"], "checked_at": (NOW+timedelta(seconds=1)).isoformat()},
    {**packet(state="offline")["controller_availability"], "source": "mqtt"}])
def test_missing_stale_or_invalid_availability_queries_once(first):
    envelope = packet(); envelope["controller_availability"] = first
    client = Client([envelope, packet(state="offline")]); result = read(client)
    assert [kind for kind, _ in client.calls] == ["rootline_observer/snapshot", "rootline_observer/query"]
    assert result == packet(state="offline")["controller_availability"]


@pytest.mark.parametrize("change", [{"device_id": "100204e9bc"}, {"contract_version": "other"},
    {"observer_epoch": "bad"}, {"uiid": True}, {"control_commands": False},
    {"model": "other"}, {"source_authentication": "mqtt"},
    {"generated_at": (NOW+timedelta(seconds=1)).isoformat()},
    {"generated_at": (NOW-timedelta(seconds=16)).isoformat()}])
def test_bad_envelope_is_not_repaired_into_authority(change):
    client = Client([{**packet(), **change}])
    with pytest.raises(ha.HomeAssistantUnavailable): read(client)
    assert len(client.calls) == 1


@pytest.mark.parametrize("invalid", [{}, {"state": "unknown"}, packet(age=61)["controller_availability"],
    {**packet()["controller_availability"], "output_state": "ON"},
    {**packet()["controller_availability"], "source": "mqtt"}])
def test_query_cannot_refresh_old_or_unproven_evidence(invalid):
    queried = packet(); queried["controller_availability"] = invalid
    assert read(Client([packet(age=61), queried])) == {"state": "unknown"}


def test_unknown_device_fails_before_client():
    client = Client([])
    with pytest.raises(ha.HomeAssistantUnavailable): read(client, "arbitrary")
    assert not client.calls


def runtime_probe(monkeypatch, replies, known=None):
    from modules.telemetry import rootline_controller_availability as availability
    from modules.telemetry import rootline_owned_deadlines as deadlines
    client = Client(replies); recorded = []; checkpoints = []
    original = ha.read_controller_connection
    monkeypatch.setattr(ha, "read_controller_connection", partial(original, now=NOW, client_factory=client))
    monkeypatch.setattr(availability, "read_controller_availability", lambda **kwargs: known or {
        identity: {"checked_at": NOW.isoformat()} for identity in ha.MODELS if identity != DEVICE})
    monkeypatch.setattr(deadlines, "check_owned_deadline", lambda **kwargs: checkpoints.append(len(client.calls)))
    transport = RootlineIFTTTTransport(token_store=object(), environ=SOURCE)
    transport.availability_recorder = lambda identity, observation: recorded.append((identity, observation))
    monkeypatch.setattr(transport, "read_output_state", lambda **kwargs: pytest.fail("connectivity must not build command route"))
    monkeypatch.setattr(transport, "set_state", lambda **kwargs: pytest.fail("connectivity must never command"))
    return client, recorded, checkpoints, transport


def test_real_runtime_transport_adapter_path_preserves_device_and_original_clock(monkeypatch):
    client, recorded, checkpoints, transport = runtime_probe(monkeypatch, [packet(age=15)])
    runtime._refresh_one_controller_availability(transport, runtime._NATIVE_EXECUTION_STORE, "unused", lambda: NOW)
    assert recorded == [(DEVICE, packet(age=15)["controller_availability"])]
    assert checkpoints == [0, 1]
    assert len(client.calls) == 1


def test_generic_ha_failure_does_not_invent_controller_offline(monkeypatch):
    client, recorded, checkpoints, transport = runtime_probe(monkeypatch, [RuntimeError("HA unavailable")])
    runtime._refresh_one_controller_availability(transport, runtime._NATIVE_EXECUTION_STORE, "unused", lambda: NOW)
    assert not recorded and checkpoints == [0, 1]


def test_owned_deadline_failure_after_read_is_not_swallowed(monkeypatch):
    from modules.telemetry import rootline_owned_deadlines as deadlines
    client, recorded, checkpoints, transport = runtime_probe(monkeypatch, [packet()])
    def checkpoint(**kwargs):
        if client.calls: raise RuntimeError("owned deadline crossed")
    monkeypatch.setattr(deadlines, "check_owned_deadline", checkpoint)
    with pytest.raises(RuntimeError, match="owned deadline crossed"):
        runtime._refresh_one_controller_availability(transport, runtime._NATIVE_EXECUTION_STORE, "unused", lambda: NOW)
    assert len(client.calls) == 1


def test_low_optional_budget_does_not_read_or_command(monkeypatch):
    from modules.telemetry import rootline_cycle_budget as budget
    client, recorded, checkpoints, transport = runtime_probe(monkeypatch, [packet()])
    monkeypatch.setattr(budget, "remaining_seconds", lambda *args: 14)
    runtime._refresh_one_controller_availability(transport, runtime._NATIVE_EXECUTION_STORE, "unused", lambda: NOW)
    assert not client.calls and not recorded


def test_clock_is_checked_after_io_not_at_request_start(monkeypatch):
    wall = [NOW]
    class AdvancingDatetime(datetime):
        @classmethod
        def now(cls, tz=None): return wall[0]
    monkeypatch.setattr(ha, "datetime", AdvancingDatetime)
    class Slow(Client):
        def request(self, *args, **kwargs):
            result = super().request(*args, **kwargs)
            wall[0] += timedelta(seconds=16)
            return result
    with pytest.raises(ha.HomeAssistantUnavailable):
        ha.read_controller_connection(DEVICE, environ=SOURCE, client_factory=Slow([packet()]))


from tests.test_rootline_active_supervision import reports

@pytest.mark.parametrize("legacy_route", [False, True])
@pytest.mark.parametrize("other_work,report_work", [(78, 2), (66, 12), (78, 12)])
def test_costed_gateway_managed_poll_leaves_report_budget_without_relaxing_limits(monkeypatch, reports, legacy_route, other_work, report_work):
    """Actual gateway/runtime/adapter; synthetic 2s per HA request, no live I/O.

    This proves the bounded saving, not an assertion about unmeasured live RTT.
    No-op equipment work is costed identically in both runs; original route is
    exercised as the baseline rather than replacing it with a guessed duration.
    """
    from tests.test_rootline_bc_cycle_efficiency import Path as CostedPath, report_inputs
    from tests.test_rootline_home_assistant import debug_fixture
    from modules.telemetry import rootline_controller_availability as availability
    from modules.telemetry import rootline_cycle_budget as budget
    from modules.telemetry.rootline_stage_timings import StageTimings
    path = CostedPath(monkeypatch); calls = []; stored = []; inventory = []; metrics = StageTimings()
    class Wall(datetime):
        @classmethod
        def now(cls, tz=None): return path.clock.now()
    monkeypatch.setattr(ha, "datetime", Wall)
    devices, entities, states, debug = debug_fixture()
    class CostedClient:
        def __init__(self, environ): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, kind, **kwargs):
            calls.append(kind); path.clock.spend(kind, 2)
            if kind == "config/device_registry/list": return devices
            if kind == "config/entity_registry/list": return entities
            if kind == "mqtt/device/debug_info": return debug
            assert kind == "rootline_observer/snapshot"
            value = packet("100204e9bc")
            value["generated_at"] = path.clock.now().isoformat()
            value["controller_availability"]["checked_at"] = path.clock.now().isoformat()
            return value
    original = ha.read_controller_connection
    monkeypatch.setattr(ha, "read_controller_connection", partial(original, client_factory=CostedClient))
    monkeypatch.setattr(availability, "read_controller_availability", lambda **kwargs: {
        identity: {"checked_at": path.clock.now().isoformat()} for identity in ha.MODELS if identity != "100204e9bc"})
    monkeypatch.setattr(availability, "reconcile_controller_availability", lambda *args, **kwargs: stored.append(args))
    def store(action, body):
        inventory.append(action)
        if action == "load_active_auxiliaries": return []
        if action == "load_active_borehole": return None
        pytest.fail("unexpected equipment operation " + action)
    monkeypatch.setattr(runtime, "_NATIVE_EXECUTION_STORE", store)
    transport = RootlineIFTTTTransport(token_store=object(), environ=SOURCE)
    if legacy_route:
        def old_poll(*, device_id):
            value = ha.read_command_route(device_id, environ=SOURCE, client_factory=CostedClient)
            transport.availability_recorder(device_id, value["controller_availability"])
            return value
        monkeypatch.setattr(transport, "read_controller_connection", old_poll)
    monkeypatch.setattr(transport, "set_state", lambda **kwargs: pytest.fail("no equipment command expected"))
    def managed(**kwargs):
        path.clock.spend("other unchanged owned/inventory work", other_work)
        # No pending work in this scoped journey; inventory and optional poll
        # are the real production coordinator and transport implementations.
        return runtime.run_rootline_managed_device_reassessment(
            environ={**SOURCE, "ROOTLINE_ESKOM_ENABLED": "false"},
            now=path.clock.now(), clock=path.clock.now, token_store=object(),
            store=store, transport=transport, allow_new_starts=False,
            allow_borehole_starts=False, stage_timings=metrics)
    path.managed = managed
    path.cycle = lambda **kwargs: {"success": True, "status": "planner_hold_or_no_dispatchable_zone",
        "hardware_commands": 0, "writes_farm_data": False}
    loader, unbounded_generator = report_inputs(path, plan_seconds=report_work-1)
    def generator(current):
        # Production persistence is bounded by the current DB/read budget;
        # the synthetic I/O must enforce that same limit after elapsed work.
        budget.remaining_seconds()
        result = unbounded_generator(current)
        budget.remaining_seconds()
        return result
    value, status = path.gateway(reports_due=True, report_loader=loader, plan_generator=generator)
    assert budget.CYCLE_WORK_SECONDS == 140 and budget.REPORT_MINIMUM_SECONDS == 25
    assert inventory == ["load_active_auxiliaries", "load_active_borehole"]
    assert len(stored) == 1 and not path.transport.calls
    assert metrics.snapshot()["stages"]["controller_connectivity"]["elapsed_ms"] == (8000 if legacy_route else 2000)
    assert len(calls) == (4 if legacy_route else 1)
    if legacy_route or (other_work == 78 and report_work == 12):
        # The optimization does not manufacture time for longer plan work.
        assert value["status"] == "scheduled_rootline_reporting_deadline_deferred", value
    else:
        assert calls == ["rootline_observer/snapshot"]
        assert status == 200, value
        assert value["hardware_commands"] == 0
    assert budget.work_deadline() is budget.on_deadline() is None


def test_notification_reader_keeps_original_clock_and_refuses_true_future():
    from tests.test_rootline_controller_availability import Database, observation
    from modules.telemetry import rootline_controller_availability as availability
    db = Database(); observed = NOW+timedelta(seconds=30); sent = []
    availability.reconcile_controller_availability(DEVICE, observation("offline", observed), now=observed, connect=db.connect)
    def store(action, body):
        db.rows.append({**body, "action": action, "event_id": "receipt"}); return {"success": True}
    def notify(state, body, **kwargs):
        sent.append((state, body)); return {"provider_delivery_confirmed": True, "provider_message_id": "1", "telegram_sends": 1}
    with pytest.raises(ValueError, match="clock_invalid"):
        availability.notify_controller_availability(notify=notify, store=store, now=NOW, connect=db.connect)
    assert not sent
    availability.notify_controller_availability(notify=notify, store=store, now=observed, connect=db.connect)
    availability.notify_controller_availability(notify=notify, store=store, now=observed, connect=db.connect)
    assert len(sent) == 1 and sent[0][1]["checked_at"] == observed.isoformat()


def test_production_gateway_notifies_same_cycle_availability_at_delivery_time(monkeypatch, reports):
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.oom_sakkie import automatic_reassessment_store as schedules_module
    from modules.telemetry import rootline_controller_availability as availability
    from modules.telemetry import rootline_irrigation_execution_store as execution_store
    from modules.telemetry import rootline_water_energy_plan as plans
    from tests.test_rootline_active_supervision import ScheduleStore, ENV, HEADERS, payload
    from tests.test_rootline_controller_availability import Database, observation
    db = Database(); schedules = ScheduleStore(); sent = []; notifier_clocks = []
    later = NOW+timedelta(seconds=30)
    schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed", "next_due_at": (NOW+timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(schedules_module, "automatic_reassessment_store", schedules)
    monkeypatch.setattr(plans, "ensure_due_daily_program", lambda **kwargs: ({"success": True, "status": "reused"}, 200))
    def store(action, body):
        assert action == "record_notification_delivery"
        db.rows.append({**body, "action": action, "event_id": "receipt"}); return {"success": True}
    monkeypatch.setattr(execution_store, "rootline_irrigation_execution_store", store)
    real_notify = availability.notify_controller_availability
    def notify(**kwargs):
        notifier_clocks.append(kwargs["now"])
        return real_notify(**kwargs, connect=db.connect)
    monkeypatch.setattr(availability, "notify_controller_availability", notify)
    def managed(**kwargs):
        availability.reconcile_controller_availability(DEVICE, observation("offline", later), now=later, connect=db.connect)
        return {"success": True, "status": "no_eligible_managed_device_task", "hardware_commands": 0}
    def delivery(*args, **kwargs):
        sent.append((args, kwargs)); return {"success": True, "provider_delivery_confirmed": True,
            "provider_message_id": "1", "telegram_message_id": "1", "telegram_sends": 1}
    source = {**ENV, "ROOTLINE_AUTONOMOUS_BC_ENABLED": "false", "ROOTLINE_INPUT_HEALTH_ENABLED": "false"}
    value, status = handle_rootline_reassessment_trigger(
        payload(due_at=NOW.isoformat(), trigger_timestamp=NOW.isoformat(), evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat()),
        HEADERS, source, scheduler_now=NOW, supervision_clock=lambda: later,
        schedule_store=None, state_store=lambda *args: {"success": True, "created": True},
        managed_device_cycle=managed, family_delivery=delivery,
        active_supervision_cycle=lambda **kwargs: {"success": True, "status": "no_active_irrigation", "active_execution_found": False},
        equipment_notification_cycle=lambda **kwargs: {"success": True, "status": "observed", "telegram_sends": 0})
    assert notifier_clocks == [later]
    assert len(sent) == 1, value
    outcome = list(schedules.rows.values())[-1]
    assert "controller_notifications" in outcome["stage_timings"]["stages"]
    assert db.rows[0]["checked_at"] == later.isoformat()
