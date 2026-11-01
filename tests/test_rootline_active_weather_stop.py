"""Rain-after-start safety through real runtime/coordinator and canonical projections."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import partial
import hashlib
import json
import uuid

import pytest

from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.telemetry.rootline_irrigation_history import _attach_parent_jobs, project_canonical_irrigation_history
from modules.telemetry.rootline_irrigation_job_contract import (
    build_irrigation_job, project_next_segment, validate_weather_stopped_execution, weather_stop_digest,
)
from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle
from modules.telemetry import weather_service as weather
from tests.test_rootline_daily_advisor import active_policy_v3
from tests.test_rootline_active_supervision import ExecutionStore, gateway, reports, ScheduleStore, payload

NOW = datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc)


def weather_packet(*, now=NOW, rain=0.0, observed=None):
    observed = observed or now - timedelta(minutes=1)
    policy = active_policy_v3()
    policy.update(proposal_sha256="3" * 64,
        activation={"actor_identity": "synthetic-owner", "effective_at": (now - timedelta(days=1)).isoformat()})
    current = weather._format_current_weather_response((weather.DEFAULT_WEATHER_SOURCE_ID,
        "Synthetic station", "synthetic", 30, observed, 20, 60, 5, 7, 180, rain, 0,
        1000, {}, "ok", "Current conditions", []), now=now)
    release = weather.build_weather_dry_release_evidence(
        [(observed - timedelta(minutes=30), 0.0), (observed, rain)],
        evaluated_at=now, stale_after_minutes=30)
    return {"weather_snapshot": {"success": True, "snapshot_cutoff": now.isoformat(),
        "weather_current": current, "rain_release": release},
        "policy_snapshot": {"success": True, "status": "policy_review_ready", "active_policy": policy}}


def dry_weather_reader(**kwargs):
    return weather_packet(now=kwargs["now"])


def subject(*, zone="B12345", segment=1, now=NOW, total=7198, job=None, prior=0):
    job = job or build_irrigation_job(zone_id=zone, operating_date=now.date().isoformat(),
        requested_total_seconds=total, requested_total_minutes=(total + 59) // 60,
        maximum_segment_seconds=3599, expected_segment_count=2,
        plan_identity="synthetic-plan-" + uuid.uuid4().hex)
    duration = min(3599, total - (segment - 1) * 3599)
    identity = "ROOTLINE-JOB-SEGMENT-" + coordinator._digest({"job_id": job["job_id"],
        "segment_number": segment, "duration_seconds": duration})[:24].upper()
    claimed = now - timedelta(seconds=100)
    row = {"execution_id": "SYNTHETIC-" + uuid.uuid4().hex, "state": "Active",
        "device_id": "100204e9bc", "channel": 1 if zone == "B12345" else 2,
        "zone_id": zone, "job_id": job["job_id"], "job_sha256": job["job_sha256"],
        "operating_date": job["operating_date"], "plan_generation": job["plan_identity"],
        "requested_total_duration_seconds": total, "requested_total_duration_minutes": job["requested_total_minutes"],
        "governed_executable_duration_seconds": total, "expected_segment_count": 2,
        "segment_number": segment, "current_segment": segment, "segment_identity": identity,
        "planned_runtime_seconds": duration, "planned_runtime_minutes": duration / 60,
        "claimed_at": claimed.isoformat(), "primary_stop_deadline": (claimed + timedelta(seconds=duration)).isoformat(),
        "native_fail_stop_deadline": (claimed + timedelta(seconds=3599)).isoformat(),
        "on_attempts": 1, "off_attempts": 0, "cumulative_verified_runtime_seconds": prior,
        "start_evidence": {"authoritative": True, "state": "ON", "device_id": "100204e9bc",
            "channel": 1 if zone == "B12345" else 2, "evidence_id": "synthetic-on-" + uuid.uuid4().hex,
            "retrieved_at": (claimed + timedelta(seconds=1)).isoformat()}}
    return job, row


class Transport:
    def __init__(self, clock=lambda: NOW, *, injector_off=True):
        self.clock = clock
        self.calls = []
        self.injector_off = injector_off
    def set_state(self, **kwargs):
        assert kwargs["state"] == "OFF"
        self.calls.append(kwargs)
        return {"accepted_unambiguous": kwargs["device_id"] != "100204d497" or self.injector_off}
    def read_output_state(self, **kwargs):
        state = "ON" if kwargs["device_id"] == "100204d497" and not self.injector_off else "OFF"
        return {**kwargs, "authoritative": True, "state": state,
            "evidence_id": "synthetic-off-" + kwargs["device_id"], "retrieved_at": self.clock().isoformat()}


def supervise(row, *, reader=None, clock=lambda: NOW, store=None, transport=None):
    store = store or ExecutionStore(row)
    transport = transport or Transport(clock)
    notices = []
    result = runtime.supervise_rootline_active_execution(store=store, transport=transport,
        notify=lambda *args: notices.append(args) or {"provider_delivery_confirmed": True},
        token_store=object(), environ={}, now=clock(), clock=clock, owner_user_id="42", chat_id="42",
        active_weather_reader=reader or (lambda **kwargs: weather_packet(now=kwargs["now"], rain=0.5)))
    return result, store, transport, notices


def stopped_row(*, now=NOW, **kwargs):
    job, active = subject(now=now, **kwargs)
    result, store, _, _ = supervise(active, clock=lambda: now)
    assert result["status"] == "segment_stopped_for_weather", result
    stopped = {**result["execution"], "action": "record_completed"}
    return job, active, stopped


@pytest.mark.parametrize("rate,stop", [(0, False), (0.19, False), (0.2, False), (0.20001, True), (2, True)])
def test_actual_normalized_policy_threshold_is_strict(rate, stop):
    packet = weather_packet(rain=rate)
    result = runtime.assess_active_irrigation_weather(packet, now=NOW)
    assert result["stop_required"] is stop
    assert result["policy_version"] == 3 and result["policy_sha256"] == "3" * 64
    assert packet["policy_snapshot"]["active_policy"]["policy"]["zones"]["B12345"]["daylight_window"]["timezone"] == "Africa/Johannesburg"


@pytest.mark.parametrize("defect", ["missing", "policy_missing", "policy_failed", "policy_unknown_hold",
    "policy_digest", "policy_future", "wrong_station", "stale", "future", "conflict", "unhealthy",
    "boolean_rate", "nan_rate", "negative_rate", "missing_rate", "mismatched_interval", "failed_weather"])
def test_unsafe_active_evidence_requires_stop(defect):
    packet = weather_packet()
    snapshot = packet["weather_snapshot"]
    current = snapshot["weather_current"]
    policy = packet["policy_snapshot"]["active_policy"]
    if defect == "missing": packet = {}
    elif defect == "policy_missing": packet["policy_snapshot"] = {}
    elif defect == "policy_failed": packet["policy_snapshot"]["success"] = False
    elif defect == "policy_unknown_hold": policy["policy"]["live_rain_hold"] = "Unknown"
    elif defect == "policy_digest": policy["proposal_sha256"] = "x" * 64
    elif defect == "policy_future": policy["activation"]["effective_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif defect == "wrong_station": current["source"]["source_id"] = "Other"
    elif defect == "stale": packet = weather_packet(observed=NOW - timedelta(minutes=31))
    elif defect == "future": packet = weather_packet(observed=NOW + timedelta(seconds=1))
    elif defect == "conflict": snapshot["rain_release"]["conflicting"] = True
    elif defect == "unhealthy": current["flags"]["source_unhealthy"] = True
    elif defect == "boolean_rate": current["current"]["rain_rate_mm_h"] = False
    elif defect == "nan_rate": current["current"]["rain_rate_mm_h"] = float("nan")
    elif defect == "negative_rate": current["current"]["rain_rate_mm_h"] = -1
    elif defect == "missing_rate": current["current"].pop("rain_rate_mm_h")
    elif defect == "mismatched_interval": snapshot["rain_release"]["interval_end_at"] = NOW.isoformat()
    elif defect == "failed_weather": snapshot["success"] = False
    assert runtime.assess_active_irrigation_weather(packet, now=NOW)["stop_required"] is True


def test_current_dry_run_does_not_require_a_new_dry_release_or_fresh_forecast():
    packet = weather_packet()
    packet["weather_snapshot"]["rain_release"]["continuous_zero_rain_confirmed"] = False
    packet["weather_snapshot"]["forecast"] = {"success": False, "flags": {"forecast_stale": True}}
    assert runtime.assess_active_irrigation_weather(packet, now=NOW)["stop_required"] is False


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
@pytest.mark.parametrize("segment", [1, 2])
@pytest.mark.parametrize("path", ["supervisor", "cycle"])
def test_wet_after_start_stops_both_entrypoints_without_full_credit(zone, segment, path):
    job, active = subject(zone=zone, segment=segment, prior=3599 if segment == 2 else 0)
    original_deadlines = active["primary_stop_deadline"], active["native_fail_stop_deadline"]
    store = ExecutionStore(active); transport = Transport(); calls = []
    def reader(**kwargs):
        calls.append(kwargs)
        return weather_packet(now=kwargs["now"], rain=0.5)
    if path == "supervisor":
        result, _, _, notices = supervise(active, reader=reader, store=store, transport=transport)
        assert [state for state, _ in notices] == ["Stopped"]
    else:
        result = runtime.run_rootline_execution_cycle(notify=lambda *args: {},
            environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}, store=store, transport=transport,
            token_store=object(), now=NOW, clock=lambda: NOW, active_weather_reader=reader,
            evidence_loader=lambda **kw: pytest.fail("active path ran full planner"))
    assert result["status"] == "segment_stopped_for_weather"
    assert len(calls) == 1 and [(c["channel"], c["state"]) for c in transport.calls] == [(active["channel"], "OFF")]
    stopped = result["execution"]
    assert validate_weather_stopped_execution(stopped)
    assert (stopped["primary_stop_deadline"], stopped["native_fail_stop_deadline"]) == original_deadlines
    assert stopped["objective_satisfied"] is stopped["job_completed"] is False
    assert stopped["verified_runtime_seconds"] == 0 and stopped["cumulative_verified_runtime_seconds"] == active["cumulative_verified_runtime_seconds"]
    assert stopped["partial_observation"]["observed_interval_seconds"] == 99
    assert store.active is None and not any(action == "contain_zone" for action, _ in store.rows)


def test_unavailable_reader_is_an_explicit_normal_stop_with_verified_off():
    _, active = subject()
    result, _, transport, notices = supervise(active, reader=lambda **kw: (_ for _ in ()).throw(TimeoutError()))
    assert result["status"] == "segment_stopped_for_weather" and len(transport.calls) == 1
    assert result["execution"]["reason"] == "active_weather_policy_unavailable"
    assert notices[0][0] == "Stopped"


@pytest.mark.parametrize("dry", [True, False])
def test_read_crossing_deadline_uses_post_read_clock_and_keeps_weather_cause(dry):
    _, active = subject()
    deadline = datetime.fromisoformat(active["primary_stop_deadline"])
    current = [deadline - timedelta(seconds=1)]
    def reader(**kwargs):
        current[0] = deadline + timedelta(seconds=2)
        assert 0 < kwargs["deadline_seconds"] <= 1
        return weather_packet(now=kwargs["now"], rain=0 if dry else 1)
    result, _, _, _ = supervise(active, reader=reader, clock=lambda: current[0])
    assert result["status"] == ("segment_completed" if dry else "segment_stopped_for_weather")
    assert result["execution"]["state"] == ("Completed" if dry else "Stopped")


def test_due_stop_skips_weather_and_policy_io():
    _, active = subject()
    due = datetime.fromisoformat(active["primary_stop_deadline"]) + timedelta(seconds=1)
    result, _, _, _ = supervise(active, reader=lambda **kw: pytest.fail("due stop waited for weather"), clock=lambda: due)
    assert result["status"] == "segment_completed"


def test_restart_after_stop_persistence_skips_weather_even_after_original_deadline():
    _, active = subject()
    store = ExecutionStore(active, fail="record_completed")
    first, _, _, _ = supervise(active, store=store)
    assert first["success"] is False and store.active["state"] == "stopping"
    store.fail = None
    later = datetime.fromisoformat(active["primary_stop_deadline"]) + timedelta(seconds=10)
    second, _, _, _ = supervise(active, store=store, clock=lambda: later,
        reader=lambda **kw: pytest.fail("sticky stop reloaded weather"))
    assert second["status"] == "segment_stopped_for_weather"
    assert second["execution"]["verified_runtime_seconds"] == 0
    assert second["execution"]["stop_requested_at"] == NOW.isoformat()


def test_losing_deadline_callback_uses_winning_weather_stop():
    _, active, stopped = stopped_row()
    barrier = {**stopped, "state": "stopping", "action": "mark_stopping"}
    class WonByWeather(ExecutionStore):
        def __call__(self, action, payload):
            if action == "mark_stopping": return {"success": True, "execution": barrier}
            return super().__call__(action, payload)
    later = datetime.fromisoformat(active["primary_stop_deadline"]) + timedelta(seconds=1)
    result, _, _, _ = supervise(active, store=WonByWeather(active), clock=lambda: later)
    assert result["status"] == "segment_stopped_for_weather" and result["execution"]["verified_runtime_seconds"] == 0


def test_stopped_slot_consumed_next_original_slot_unchanged_and_final_deferred():
    job, active, stopped = stopped_row(total=4900)
    next_segment = project_next_segment(job, [stopped], rearm_readback_off=True)
    assert next_segment["current_segment"] == 2 and next_segment["segment_requested_seconds"] == 1301
    assert next_segment["cumulative_verified_runtime_seconds"] == 0
    assert project_next_segment(job, [stopped])["status"] == "segment_rearm_required"
    _, second, final = stopped_row(job=job, segment=2, total=4900)
    deferred = project_next_segment(job, [stopped, final], rearm_readback_off=True)
    assert deferred["status"] == "job_deferred" and deferred["remaining_seconds"] == 4900
    assert deferred["command_authority"] is False and deferred["unused_segment_count"] == 0


def test_stopped_parent_survives_without_completed_segment_and_is_held_truthfully():
    job, active, stopped = stopped_row()
    authority = {**active, "action": "record_eligibility"}
    history = project_canonical_irrigation_history([], snapshot_cutoff=NOW)
    _attach_parent_jobs(history, [authority, stopped], canonical_ordered=True)
    parent = history["zones"]["B12345"]["incomplete_parent_job"]
    assert parent["projection"]["current_segment"] == 2 and parent["completed_segment_count"] == 0
    assert parent["remaining_seconds"] == 7198 and parent["stopped_segment_count"] == 1
    lifecycle = project_zone_lifecycle(zone_id="B12345", recommendation={},
        history=history["zones"]["B12345"], execution=stopped, evidence_cutoff=NOW)
    assert lifecycle["state"] == "Held" and lifecycle["next_action_owner"] == "ROOTLINE"
    assert not lifecycle["execution_exceptions"]


@pytest.mark.parametrize("defect", ["device", "channel", "execution", "zone", "time", "future", "missing_identity", "full_credit", "deadline"])
def test_partial_terminal_rejects_forged_shutdown_or_credit(defect):
    _, _, stopped = stopped_row()
    shutdown = stopped["shutdown_evidence"]
    if defect == "device": shutdown["device_id"] = "OTHER"
    elif defect == "channel": shutdown["channel"] = 2
    elif defect == "execution": shutdown["execution_id"] = "OTHER"
    elif defect == "zone": shutdown["zone_id"] = "C12345"
    elif defect == "time": shutdown["retrieved_at"] = (NOW - timedelta(seconds=1)).isoformat()
    elif defect == "future": shutdown["retrieved_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif defect == "missing_identity": shutdown.pop("evidence_id")
    elif defect == "full_credit": stopped["verified_runtime_seconds"] = 3599
    elif defect == "deadline": stopped["primary_stop_deadline"] = NOW.isoformat()
    stopped["terminal_sha256"] = weather_stop_digest(stopped)
    assert validate_weather_stopped_execution(stopped) is False


@pytest.mark.parametrize("injector_off", [True, False])
def test_rain_stop_retains_injector_first_shutdown_order(injector_off):
    _, active = subject()
    store = ExecutionStore(active)
    store.auxiliary = {"execution_id": "SYNTHETIC-INJECTOR", "auxiliary_device_id": "FERTILIZER-INJECTION-CH1",
        "device_id": "100204d497", "channel": 1, "state": "Active", "job_id": active["job_id"],
        "job_sha256": active["job_sha256"], "segment_identity": active["segment_identity"],
        "zone_id": active["zone_id"], "zone_execution_id": active["execution_id"]}
    transport = Transport(injector_off=injector_off)
    result, _, _, _ = supervise(active, store=store, transport=transport)
    assert transport.calls[0]["device_id"] == "100204d497"
    if injector_off:
        assert result["status"] == "segment_stopped_for_weather"
        assert [call["device_id"] for call in transport.calls] == ["100204d497", "100204e9bc"]
        assert result["execution"]["fertilizer_flush_completion"] == "Unproven"
    else:
        assert result["parent_off_command_withheld"] is True
        assert all(call["device_id"] == "100204d497" for call in transport.calls)
        assert result["irrigation_flow_state"] == "Unknown" and store.active["state"] == "stopping"


def test_genuine_gateway_stop_notifies_once_and_does_not_admit_on_in_same_pass(reports):
    _, active = subject()
    store = ExecutionStore(active); transport = Transport(); schedules = ScheduleStore()
    schedules.rows["prior:outcome"] = {"specialist": "ROOTLINE", "status": "completed",
        "next_due_at": (NOW + timedelta(minutes=30)).isoformat()}
    value, _, starts, messages = gateway(store, transport, schedules=schedules, scheduler_now=NOW,
        request_payload=payload(trigger_timestamp=NOW.isoformat(), due_at=NOW.isoformat(),
            evidence_cutoff=(NOW - timedelta(seconds=1)).isoformat()),
        active_supervision_cycle=partial(runtime.supervise_rootline_active_execution,
            store=store, transport=transport, token_store=object(), clock=lambda: NOW,
            active_weather_reader=lambda **kwargs: weather_packet(now=kwargs["now"], rain=1)))
    assert value["active_supervision_status"] == "segment_stopped_for_weather" and starts == []
    assert len(messages) == 1 and "IRRIGATION STOPPED" in messages[0][0][1]["answer"]
    assert "No owner action is required" in messages[0][0][1]["answer"]
    assert len(transport.calls) == 1


def test_active_policy_reader_uses_bounded_connector_and_coherent_snapshot(monkeypatch):
    from modules.telemetry import rootline_operating_policy as policy_module
    from modules.oom_sakkie import bounded_postgres_read
    calls = []
    packet = weather_packet()
    sentinel = object()
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_rootline_postgres",
        lambda **kwargs: calls.append(kwargs) or sentinel)
    def policy_read(*, store):
        assert store.connect_factory("synthetic-local-url") is sentinel
        return packet["policy_snapshot"], 200
    monkeypatch.setattr(policy_module, "list_policy_review", policy_read)
    monkeypatch.setattr(weather, "get_weather_control_snapshot",
        lambda **kwargs: (packet["weather_snapshot"], 200))
    result = runtime.read_active_irrigation_weather(database_url="synthetic-local-url", now=NOW)
    assert result == packet
    assert calls == [{"database_url": "synthetic-local-url", "read_only": True}]


def test_disappearing_active_execution_cannot_fall_through_to_a_new_on():
    _, active = subject()
    class Disappearing(ExecutionStore):
        reads = 0
        def __call__(self, action, payload):
            if action == "load_active":
                self.reads += 1
                return active if self.reads == 1 else None
            pytest.fail("disappearing active path attempted mutation")
    transport = Transport()
    result = runtime.run_rootline_execution_cycle(notify=lambda *a: {},
        environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}, store=Disappearing(active),
        transport=transport, token_store=object(), now=NOW, clock=lambda: NOW,
        active_weather_reader=lambda **kw: pytest.fail("missing active execution read weather"),
        evidence_loader=lambda **kw: pytest.fail("missing active execution ran full planner"))
    assert result["status"] == "no_active_irrigation" and not transport.calls


@pytest.mark.parametrize("defect", ["arbitrary_failure", "other_execution", "other_claim", "other_barrier"])
def test_failed_write_cannot_masquerade_as_canonical_terminal_convergence(defect):
    _, active = subject()
    class FailedStore(ExecutionStore):
        def __call__(self, action, body):
            if action == "record_completed":
                canonical = {**deepcopy(body), "action": "record_completed"}
                status = "canonical_weather_stop_already_committed"
                if defect == "arbitrary_failure": status = "arbitrary_failure"
                elif defect == "other_execution": canonical["execution_id"] = "OTHER-EXECUTION"
                elif defect == "other_claim": canonical["eligibility_id"] = "OTHER-CLAIM"
                elif defect == "other_barrier":
                    canonical["weather_stop_evidence"]["reason"] = "active_weather_stale"
                    canonical["weather_stop_evidence"]["evidence_sha256"] = coordinator._digest({
                        key: value for key, value in canonical["weather_stop_evidence"].items() if key != "evidence_sha256"})
                    canonical["reason"] = "active_weather_stale"
                canonical["terminal_sha256"] = weather_stop_digest(canonical)
                return {"success": False, "created": False, "status": status, "canonical_execution": canonical}
            return super().__call__(action, body)
    result, store, _, notices = supervise(active, store=FailedStore(active))
    assert result["status"] == "completion_persistence_unproven"
    assert [state for state, _ in notices] == ["Intervention"]
    assert store.active["state"] == "stopping"
