from tests.test_rootline_ifttt_transport import irrigation_output
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import sys

import pytest

from modules.telemetry.rootline_managed_devices_runtime import (
    run_rootline_managed_device_cycle as _managed_cycle,
)
from modules.telemetry.rootline_execution_runtime import (
    run_rootline_managed_device_reassessment as _managed_reassessment,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def run_rootline_managed_device_cycle(**kwargs):
    kwargs.setdefault("clock", lambda: kwargs.get("now", NOW))
    return _managed_cycle(**kwargs)


def run_rootline_managed_device_reassessment(**kwargs):
    kwargs.setdefault("clock", lambda: kwargs.get("now", NOW))
    return _managed_reassessment(**kwargs)


def active_parent():
    ctx = injection_evidence()["auxiliary_contexts"]["FERTILIZER-INJECTION-CH1"]
    return {"execution_id": ctx["zone_execution_id"], "state": "Active",
        "device_id": "100204e9bc", "channel": 1, "zone_id": "B12345",
        "primary_stop_deadline": ctx["irrigation_stop_deadline"],
        **{key: ctx[key] for key in ("job_id", "job_sha256", "segment_identity")}}


class Store:
    def __init__(self):
        self.active_aux = None
        self.active_borehole = None
        self.rows = []

    def __call__(self, action, payload):
        if action == "load_active":
            return active_parent()
        if action == "load_active_auxiliaries":
            return [self.active_aux] if self.active_aux else []
        if action == "load_active_auxiliary":
            return self.active_aux if not self.active_aux or self.active_aux.get("auxiliary_device_id") == payload else None
        if action == "load_active_borehole":
            return self.active_borehole
        if action == "load_auxiliary_containment":
            return None
        if action == "load_auxiliary_off_attempts":
            return []
        if action == "load_auxiliary_physical_outcome":
            return None
        if action == "load_borehole_off_attempts":
            return []
        if action == "dispatch_auxiliary_on_edge":
            return payload["dispatch"]()
        if action in {"claim_auxiliary_off_attempt", "claim_borehole_off_attempt"}:
            self.rows.append((action, payload)); return {"success": True, "created": True}
        if action in {"record_auxiliary_eligibility", "record_auxiliary_on_outcome"}:
            self.rows.append((action, payload)); return {"success": True, "created": True}
        if action == "claim_auxiliary_before_on":
            self.rows.append((action, payload)); return {"success": True, "created": True}
        if action == "mark_auxiliary_active":
            self.active_aux = payload; self.rows.append((action, payload))
            return {"success": True, "created": True}
        if action in {"record_auxiliary_completed", "record_borehole_completed"}:
            self.rows.append((action, payload))
            self.active_aux = None if action == "record_auxiliary_completed" else self.active_aux
            self.active_borehole = None if action == "record_borehole_completed" else self.active_borehole
            return {"success": True, "created": True}
        return {"success": True, "created": True}


class Transport:
    def __init__(self, state="ON"):
        self.calls = []
        self.state = state

    def read_safety_configuration(self, **_kwargs):
        device = "injection" if int(_kwargs.get("channel") or 0) == 1 else "mixer"
        return safety(device)

    def read_output_state(self, **_kwargs):
        if _kwargs.get("device_id")=="100204e9bc":
            return irrigation_output(NOW,channel=_kwargs["channel"])
        return {"authoritative": True, "state": self.state, "evidence_id": "STATE-1",
            "retrieved_at":NOW.isoformat()}

    def set_state(self, **kwargs):
        self.calls.append(kwargs)
        self.state = kwargs["state"]
        return {"accepted_unambiguous": True, "status": "accepted"}


def safety(device="mixer"):
    channel = 1 if device == "injection" else 2
    return {"authoritative": True, "response_digest": "READ-1",
        "device_id": "100204d497", "channel": channel, "output_state": "OFF",
        "native_inching_enabled": True, "native_inching_seconds": 120 if channel == 1 else 1800,
        "power_restoration_state": "OFF", "schedules_enabled": False,
        "timers_enabled": False, "scenes_enabled": False, "interlock_enabled": False,
        "controller_safety_generation": "SAFE-1",
        "physical_commissioning_generation": "COMMISSION-1", "commissioned": True,
        "observed_at": NOW.isoformat()}


def evidence():
    return {"irrigation_auxiliary_tasks": [{"decision": "Run now",
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
        "device_type": "fertilizer_mixer", "planned_seconds": 1800}],
        "auxiliary_safety": {"FERTILIZER-MIXER-CH2": safety()},
        "auxiliary_contexts": {"FERTILIZER-MIXER-CH2": {
            "plan_generation": "PLAN-1", "injection_active": False,
            "reserved_mixing_seconds_today": 0, "mixing_history_valid":True,
            "verified_mixing_sessions_today": 0,
            "mixing_history_complete_through": NOW.isoformat(), "power_suitable": True}}}


def canonical(key):
    injection = str(key).endswith(":1")
    return {"device_record": {"commissioning_stage": "standing_active",
        "standing_authority": True, "device_id": "100204d497", "channel": 1 if injection else 2,
        "device_type": "flow_dependent_injection_valve" if injection else "independent_mixer_valve"}}


def test_no_canonical_standing_device_means_no_command_and_bc_remains_free():
    transport = Transport()
    result = run_rootline_managed_device_cycle(evidence=evidence(), transport=transport,
        environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED": "true"}, store=Store(),
        canonical_loader=lambda _key: None, now=NOW)
    assert result["status"] == "no_eligible_managed_device_task"
    assert result["blocks_bc"] is False and transport.calls == []


def test_need_task_canonical_authority_and_fresh_edge_start_exact_mixer_once():
    store = Store(); transport = Transport()
    result = run_rootline_managed_device_cycle(evidence=evidence(), transport=transport,
        environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED": "true"}, store=store,
        canonical_loader=canonical, now=NOW)
    assert result["status"] == "auxiliary_started" and result["blocks_bc"] is False
    assert [(row["device_id"], row["channel"], row["state"])
        for row in transport.calls] == [("100204d497", 2, "ON")]
    assert any(action == "record_auxiliary_eligibility" for action, _ in store.rows)


def test_disabled_flag_cannot_consume_a_valid_task_or_command():
    transport = Transport()
    result = run_rootline_managed_device_cycle(evidence=evidence(), transport=transport,
        environ={}, store=Store(), canonical_loader=canonical, now=NOW)
    assert result["status"] == "no_eligible_managed_device_task"
    assert transport.calls == []


def injection_evidence():
    start = (NOW - timedelta(minutes=10)).isoformat()
    context = {"plan_generation": "PLAN-INJECT-1", "batch_generation": "BATCH-1",
        "fertilizer_needed": True, "premix_verified":True, "job_id": "ROOTLINE-IRRIGATION-JOB-" + "A" * 24,
        "fertilizer_history_complete_through": NOW.isoformat(),
        "job_sha256": "a" * 64, "segment_identity": "ROOTLINE-JOB-SEGMENT-" + "B" * 24,
        "active_zone_ids": ["B12345"], "zone_execution_id": "ZONE-EXEC-1",
        "zone_device_id": "100204e9bc", "zone_channel": 1,
        "zone_start_evidence": {"evidence_id": "START-1", "zone_execution_id": "ZONE-EXEC-1",
            "observed_at": start},
        "zone_output_evidence": {**irrigation_output(NOW), "zone_execution_id": "ZONE-EXEC-1",
            "observed_at": NOW.isoformat(), "state": "ON"},
        "irrigation_stop_deadline": (NOW + timedelta(minutes=30)).isoformat(),
        "completed_pulses": 0, "mixer_active": False, "prior_shutdown_unverified": False}
    return {"irrigation_auxiliary_tasks": [{"decision": "Run now",
        "auxiliary_device_id": "FERTILIZER-INJECTION-CH1",
        "device_type": "fertilizer_injection_valve", "pulse_seconds": 120}],
        "auxiliary_safety": {"FERTILIZER-INJECTION-CH1": safety("injection")},
        "auxiliary_contexts": {"FERTILIZER-INJECTION-CH1": context}}


def test_scheduler_composition_starts_injector_only_from_exact_active_irrigation_context():
    store = Store(); transport = Transport()
    result = run_rootline_managed_device_cycle(evidence=injection_evidence(),
        transport=transport, environ={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"},
        store=store, canonical_loader=canonical, now=NOW)
    assert result["status"] == "auxiliary_started"
    assert [(row["channel"], row["state"]) for row in transport.calls] == [(1, "ON")]
    invalid = injection_evidence()
    invalid["auxiliary_contexts"]["FERTILIZER-INJECTION-CH1"]["fertilizer_needed"] = False
    second_transport = Transport()
    held = run_rootline_managed_device_cycle(evidence=invalid, transport=second_transport,
        environ={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"}, store=Store(),
        canonical_loader=canonical, now=NOW)
    assert held["status"] == "no_eligible_managed_device_task" and second_transport.calls == []


def test_scheduler_recovers_active_split_mixer_to_final_off_without_on_retry():
    store = Store(); store.active_aux = {"execution_id": "MIX-SPLIT-1",
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2", "device_type": "fertilizer_mixer",
        "device_id": "100204d497", "channel": 2, "state": "Active",
        "claimed_at": (NOW - timedelta(minutes=6)).isoformat(),
        "primary_stop_deadline": (NOW - timedelta(seconds=1)).isoformat(),
        "maximum_duration_seconds": 300,
        "on_attempts":1,
        "start_evidence": {"authoritative": True, "state": "ON",
            "retrieved_at":(NOW-timedelta(minutes=5)).isoformat()}}
    transport = Transport(state="ON")
    result = run_rootline_managed_device_cycle(evidence={}, transport=transport,
        environ={}, store=store, canonical_loader=canonical, now=NOW)
    assert result["status"] == "auxiliary_completed"
    assert [call["state"] for call in transport.calls] == ["OFF"]
    assert all(call["state"] != "ON" for call in transport.calls)


def test_scheduler_recovers_active_borehole_to_final_off_without_on_retry():
    store = Store(); store.active_borehole = {"execution_id": "BOREHOLE-ACTIVE-1",
        "state": "Active", "primary_stop_deadline": (NOW - timedelta(seconds=1)).isoformat(),
        "provider_start_evidence": {"authoritative": True, "state": "ON"}}
    transport = Transport(state="ON")
    result = run_rootline_managed_device_cycle(evidence={}, transport=transport,
        environ={}, store=store, canonical_loader=canonical, now=NOW)
    assert result["status"] == "borehole_completed"
    assert [call["state"] for call in transport.calls] == ["OFF"]
    assert result["automatic_on_retry"] is False


class ManagedCursor:
    def __init__(self, outcomes, executions=None):
        self.outcomes = outcomes; self.executions = executions or []; self.kind = ""
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, query, _params=None):
        self.kind = "intake" if "rootline_operational_intake" in query else "execution"
    def fetchall(self):
        return [(row,) for row in (self.outcomes if self.kind == "intake" else self.executions)]


class ManagedConnection:
    def __init__(self, outcomes, executions=None):
        self.outcomes = outcomes; self.executions = executions or []
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return ManagedCursor(self.outcomes, self.executions)


def patch_default_sources(monkeypatch, connection):
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_read",
        lambda **_kwargs: connection)
    monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state",
        lambda **_kwargs: ({"success": True, "current": {"battery_soc_pct": 90,
            "solar_power_w": 2000, "load_power_w": 100, "grid_power_w": 0},
            "source": {"last_reading_at": NOW.isoformat()}}, 200))
    monkeypatch.setattr("modules.telemetry.weather_service.get_current_weather_state",
        lambda **_kwargs: ({"success": True, "current": {"rain_today_mm": 0},
            "source": {"last_reading_at": NOW.isoformat()}}, 200))
    monkeypatch.setattr("modules.telemetry.weather_service.get_weather_forecast",
        lambda **_kwargs: ({"success": True, "days": [],
            "source": {"last_forecast_run_at": NOW.isoformat()}}, 200))
    monkeypatch.setattr("modules.telemetry.rootline_daily_advisor.get_rootline_daily_advisor",
        lambda *_args, **_kwargs: ({"zones": [], "generated_at": NOW.isoformat(),
            "operating_date": NOW.date().isoformat()}, 200))
    monkeypatch.setattr("modules.telemetry.rootline_water_energy_plan.read_latest_zone_water_balances",
        lambda *_args, **_kwargs: {"zones": {}})
    for name, value in (("_read_historical_context", {}),
            ("_read_recent_irrigation_history", {}), ("_read_latest_tank_observation", {}),
            ("_read_latest_owner_zone_need", {"status": "Unavailable"})):
        monkeypatch.setattr("modules.telemetry.rootline_water_energy_plan." + name,
            lambda *_args, _value=value, **_kwargs: _value)


def test_default_loader_to_planner_to_scheduler_starts_only_canonical_mixer(monkeypatch):
    batch = {"fertilizer_batch_observation": {"event_type": "fertilizer_batch_prepared",
        "observed_at": NOW.isoformat()}}
    patch_default_sources(monkeypatch, ManagedConnection([batch]))
    monkeypatch.setattr("modules.telemetry.rootline_managed_devices_runtime.load_device_record",
        lambda *_args, **_kwargs: canonical("ifttt_ewelink:ewelink_owner_account:100204d497:2"))
    transport = Transport(); store = Store()
    result = run_rootline_managed_device_reassessment(
        environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED": "true"}, database_url="postgres://test",
        store=store, token_store=object(), transport=transport, now=NOW)
    assert result["status"] == "auxiliary_started"
    assert [(row["channel"], row["state"]) for row in transport.calls] == [(2, "ON")]


def _default_injector_clock_case(monkeypatch, *, channel=1, canonical_delay=0,
        provider_delay=0, safety_delay=0, fault=None, parent_seconds=1800, start=NOW,
        final_parent_delay=0, borehole_delay=0):
    # Advance an independent clock at actual mocked IO boundaries. Provider
    # timestamps are data under test and never determine this clock.
    monkeypatch.setattr(sys.modules[__name__], "NOW", start)
    current = [start]
    plans = []
    zone = "B12345" if channel == 1 else "C12345"
    active = {"action": "mark_active", "state": "Active", "execution_id": "ZONE-EXEC-1",
        "zone_id": zone, "device_id": "100204e9bc", "channel": channel,
        "job_id": "ROOTLINE-IRRIGATION-JOB-" + "A" * 24, "job_sha256": "a" * 64,
        "segment_identity": "ROOTLINE-JOB-SEGMENT-" + "B" * 24,
        "evidence_generation": "PLAN-1",
        "primary_stop_deadline": (NOW + timedelta(seconds=parent_seconds)).isoformat(),
        "start_evidence": {"authoritative": True, "state": "ON", "evidence_id": "START-1",
            "observed_at": (NOW - timedelta(minutes=10)).isoformat()}}
    outcome = {"fertilizer_batch_observation": {"event_type": "fertilizer_batch_prepared",
            "observed_at": NOW.isoformat()}, "fertilizer_needed": True,
        "fertilizer_need_observed_at": NOW.isoformat()}
    from modules.telemetry.rootline_auxiliary_management import build_fertilizer_batch_lifecycle
    outcome["fertilizer_batch_observation"]["observed_at"] = (NOW-timedelta(hours=1)).isoformat()
    batch = build_fertilizer_batch_lifecycle(observations=[outcome["fertilizer_batch_observation"]], now=NOW)
    mix = {"action":"record_auxiliary_completed", "execution_id":"MIX-1",
        "auxiliary_device_id":"FERTILIZER-MIXER-CH2", "device_type":"fertilizer_mixer",
        "claimed_at":(NOW-timedelta(minutes=30)).isoformat(), "maximum_duration_seconds":600,
        "control_completed":True, "shutdown_verified":True, "accounted_mixing_seconds":600,
        "completed_at":(NOW-timedelta(minutes=20)).isoformat(), "batch_generation":batch["batch_generation"]}

    class DelayedConnection(ManagedConnection):
        delayed = False
        def __enter__(self):
            if not self.delayed:
                current[0] += timedelta(seconds=canonical_delay)
                self.delayed = True
            return self
    patch_default_sources(monkeypatch, DelayedConnection([outcome], [active,mix]))
    monkeypatch.setattr("modules.telemetry.rootline_managed_devices_runtime.load_device_record",
        lambda *_args, **_kwargs: canonical("ifttt_ewelink:ewelink_owner_account:100204d497:1"))
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
    from tests.test_rootline_ifttt_transport import irrigation_snapshot
    planner = runtime.build_water_energy_plan
    def observed_planner(evidence, selected, *, now):
        plan = planner(evidence, selected, now=now)
        if borehole_delay:
            plan["candidate_tasks"] = [row for row in plan.get("candidate_tasks",[]) if row.get("task_id") != "borehole"]
            plan["candidate_tasks"].append({"task_id":"borehole", "recommendation":"Recommend"})
        plans.append({"evidence":deepcopy(evidence), "at":now, "plan":plan})
        return plan
    monkeypatch.setattr(runtime,"build_water_energy_plan",observed_planner)
    if borehole_delay:
        monkeypatch.setattr("modules.telemetry.rootline_borehole_commissioning.load_registered_borehole_baseline",lambda **_:None)
    class DelayedTransport(Transport):
        def read_safety_configuration(self, **kwargs):
            current[0] += timedelta(seconds=safety_delay)
            return {**super().read_safety_configuration(**kwargs),
                "observed_at":current[0].isoformat()}
        def read_output_state(self, **kwargs):
            if kwargs["device_id"] != "100204e9bc":
                if kwargs["device_id"] == "1002851416":
                    current[0] += timedelta(seconds=borehole_delay)
                return {"authoritative":True,"state":self.state,"evidence_id":"STATE-1",
                    "retrieved_at":current[0].isoformat()}
            current[0] += timedelta(seconds=provider_delay)
            if fault == "failure": raise TimeoutError("synthetic provider read failed")
            at = current[0]
            if fault == "cached": at -= timedelta(seconds=120)
            if fault == "stale": at -= timedelta(seconds=301)
            if fault == "future": at += timedelta(microseconds=1)
            snapshot = irrigation_snapshot(at, channel=channel)
            if fault == "other_on": snapshot["channels"][2]["output_state"] = "ON"
            if fault == "unknown": snapshot["channels"][2]["output_state"] = "Unknown"
            if fault == "wrong_device": snapshot["device_id"] = "100204d497"
            return output_evidence_from_snapshot(snapshot, **kwargs)
    original = Store()
    parent_delayed = [False]
    def store(action, payload):
        if (action == "load_active" and not parent_delayed[0]
                and any(a == "claim_auxiliary_before_on" for a,_ in original.rows)):
            current[0] += timedelta(seconds=final_parent_delay)
            parent_delayed[0] = True
        result = original(action,payload)
        return {**result,"zone_id":zone,"channel":channel,
            "primary_stop_deadline":active["primary_stop_deadline"]} if action == "load_active" else result
    transport = DelayedTransport()
    result = _managed_reassessment(
        environ={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"},
        database_url="postgres://test", store=store, token_store=object(),
        transport=transport, now=start, clock=lambda:current[0])
    return result, transport, original, plans, current[0]


@pytest.mark.parametrize("channel", [1,2])
@pytest.mark.parametrize("canonical_delay,provider_delay", [
    (0,0),(0.000001,0),(1,0),(5,0),(0,0.000001),(0,1),(0,5),(5,5)])
def test_default_loader_refreshes_active_zone_then_scheduler_starts_injector(
        monkeypatch,channel,canonical_delay,provider_delay):
    result,transport,store,plans,current = _default_injector_clock_case(monkeypatch,
        channel=channel,canonical_delay=canonical_delay,provider_delay=provider_delay)
    assert result["status"] == "auxiliary_started"
    assert [(row["channel"],row["state"]) for row in transport.calls] == [(1,"ON")]
    assert sum(action=="claim_auxiliary_before_on" for action,_ in store.rows)==1
    assert plans[0]["at"] == NOW+timedelta(seconds=canonical_delay+provider_delay)
    observed=plans[0]["evidence"]["active_irrigation_context"]["zone_output_evidence"]
    assert observed["retrieved_at"]==plans[0]["at"].isoformat()
    assert observed["irrigation_output_evidence"]["channels"][channel-1]["output_state"]=="ON"
    assert datetime.fromisoformat(plans[0]["evidence"]["fertilizer_history_complete_through"])==NOW
    assert plans[0]["evidence"]["active_irrigation_context"]["fertilizer_history_complete_through"] == (
        plans[0]["evidence"]["fertilizer_history_complete_through"])
    assert next(t for t in plans[0]["plan"]["irrigation_auxiliary_tasks"]
        if t["auxiliary_device_id"]=="FERTILIZER-INJECTION-CH1")["decision"]=="Run now"


@pytest.mark.parametrize("channel", [1,2])
@pytest.mark.parametrize("fault", ["future","stale","other_on","unknown","wrong_device","failure"])
def test_delayed_default_loader_does_not_accept_invalid_post_read_proof(monkeypatch,channel,fault):
    result,transport,store,plans,_ = _default_injector_clock_case(monkeypatch,
        channel=channel,canonical_delay=1,provider_delay=5,fault=fault)
    assert result["hardware_commands"]==0 and transport.calls==[]
    assert plans[0]["evidence"]["active_irrigation_context"]["zone_output_evidence"]=={}
    assert not any(action=="claim_auxiliary_before_on" for action,_ in store.rows)


def test_delayed_default_loader_preserves_older_valid_provider_timestamp(monkeypatch):
    result,transport,_,plans,_ = _default_injector_clock_case(monkeypatch,
        canonical_delay=1,provider_delay=5,fault="cached")
    assert result["status"]=="auxiliary_started"
    proof=plans[0]["evidence"]["active_irrigation_context"]["zone_output_evidence"]
    assert datetime.fromisoformat(proof["retrieved_at"])==plans[0]["at"]-timedelta(seconds=120)
    assert proof["retrieved_at"]==proof["irrigation_output_evidence"]["retrieved_at"]


@pytest.mark.parametrize("canonical_delay,provider_delay,safety_delay", [(1,0,0),(0,1,0),(0,0,1)])
def test_default_path_elapsed_reads_cannot_spend_required_injection_programme_time(
        monkeypatch,canonical_delay,provider_delay,safety_delay):
    result,transport,_,_,_ = _default_injector_clock_case(monkeypatch,
        canonical_delay=canonical_delay,provider_delay=provider_delay,
        safety_delay=safety_delay,parent_seconds=1440)
    assert result["hardware_commands"]==0 and transport.calls==[]


@pytest.mark.parametrize("canonical_delay,provider_delay,safety_delay", [(1,0,0),(0,1,0),(0,0,1)])
def test_read_crossing_sast_midnight_requires_new_day_evidence_without_retimestamping(
        monkeypatch,canonical_delay,provider_delay,safety_delay):
    start=datetime(2026,8,25,21,59,59,500000,tzinfo=timezone.utc)
    result,transport,store,plans,current = _default_injector_clock_case(monkeypatch,
        start=start,canonical_delay=canonical_delay,provider_delay=provider_delay,safety_delay=safety_delay)
    assert result["status"] in {"managed_device_evidence_unavailable","managed_device_operating_date_changed"}
    assert result["hardware_commands"]==0 and transport.calls==[]
    assert not any(action=="claim_auxiliary_before_on" for action,_ in store.rows)
    for row in plans:
        assert datetime.fromisoformat(row["evidence"]["fertilizer_history_complete_through"])==start


def test_mixer_output_cannot_impersonate_active_zone_and_unlock_injector(monkeypatch):
    active = {"action": "mark_active", "state": "Active", "execution_id": "ZONE-EXEC-1",
        "zone_id": "B12345", "device_id": "100204d497", "channel": 2,
        "job_id": "ROOTLINE-IRRIGATION-JOB-" + "A" * 24, "job_sha256": "a" * 64,
        "segment_identity": "ROOTLINE-JOB-SEGMENT-" + "B" * 24,
        "evidence_generation": "PLAN-1",
        "primary_stop_deadline": (NOW + timedelta(minutes=30)).isoformat(),
        "start_evidence": {"authoritative": True, "state": "ON", "evidence_id": "START-1",
            "observed_at": (NOW - timedelta(minutes=10)).isoformat()}}
    outcome = {"fertilizer_batch_observation": {"event_type": "fertilizer_batch_prepared",
            "observed_at": NOW.isoformat()}, "fertilizer_needed": True,
        "fertilizer_need_observed_at": NOW.isoformat()}
    patch_default_sources(monkeypatch, ManagedConnection([outcome], [active]))
    monkeypatch.setattr("modules.telemetry.rootline_managed_devices_runtime.load_device_record",
        lambda *_args, **_kwargs: canonical("ifttt_ewelink:ewelink_owner_account:100204d497:1"))
    transport = Transport()
    result = run_rootline_managed_device_reassessment(
        environ={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"},
        database_url="postgres://test", store=Store(), token_store=object(),
        transport=transport, now=NOW)
    assert result["status"] == "no_eligible_managed_device_task"
    assert result["hardware_commands"] == 0 and transport.calls == []


def test_default_loader_missing_managed_evidence_stays_command_inert(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_read",
        lambda **_kwargs: ManagedConnection([]))
    from modules.telemetry.rootline_water_energy_plan import _read_managed_device_evidence
    loaded = _read_managed_device_evidence("postgres://test", NOW)
    assert loaded["fertilizer_batch_observations"] == []
    held = run_rootline_managed_device_cycle(evidence={"irrigation_auxiliary_tasks": []},
        transport=Transport(), environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED": "true"},
        store=Store(), canonical_loader=canonical, now=NOW)
    assert held["status"] == "no_eligible_managed_device_task"
    assert held["hardware_commands"] == 0


def test_canonical_managed_reader_composes_active_injector_and_fresh_borehole_facts(monkeypatch):
    active = {"action": "mark_active", "state": "Active", "execution_id": "ZONE-EXEC-1",
        "zone_id": "B12345", "device_id": "100204e9bc", "channel": 1,
        "job_id": "ROOTLINE-IRRIGATION-JOB-" + "A" * 24,
        "job_sha256": "a" * 64, "segment_identity": "ROOTLINE-JOB-SEGMENT-" + "B" * 24,
        "evidence_generation": "PLAN-1",
        "primary_stop_deadline": (NOW + timedelta(minutes=30)).isoformat(),
        "start_evidence": {"authoritative": True, "state": "ON", "evidence_id": "START-1",
            "observed_at": (NOW - timedelta(minutes=10)).isoformat()}}
    outcome = {"fertilizer_batch_observation": {"event_type": "fertilizer_batch_prepared",
            "observed_at": NOW.isoformat()}, "fertilizer_needed": True,
        "fertilizer_need_observed_at": NOW.isoformat(),
        "borehole_interlocks": {"observed_at": NOW.isoformat(), "provider_message_id":"synthetic-owner-fact", "dry_run_safe": True,
            "low_water_clear": True, "supply_pressure_safe": True,
            "full_tank_not_blocking": True}}
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_read",
        lambda **_kwargs: ManagedConnection([outcome], [active]))
    from modules.telemetry.rootline_water_energy_plan import _read_managed_device_evidence
    loaded = _read_managed_device_evidence("postgres://test", NOW)
    context = loaded["active_irrigation_context"]
    assert context["fertilizer_needed"] is True and context["active_zone_ids"] == ["B12345"]
    assert (context["zone_device_id"], context["zone_channel"]) == ("100204e9bc", 1)
    assert context["batch_generation"].startswith("ROOTLINE-BATCH-")
    assert loaded["borehole_interlocks"]["supply_pressure_safe"] is True


@pytest.mark.parametrize("offset,fresh", [(0,True),(0.000001,False),(-900.000001,False)])
def test_managed_energy_uses_post_read_clock_and_ages_cached_evidence(monkeypatch,offset,fresh):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    current=[NOW];reads=[];decisions=[]
    def power(**kwargs):
        reads.append(kwargs);current[0]+=timedelta(seconds=5)
        return {"success":True,"current":{"battery_soc_pct":90,"solar_power_w":2000,
            "load_power_w":100,"grid_power_w":0},"source":{"last_reading_at":
                (current[0]+timedelta(seconds=offset)).isoformat()}},200
    def cycle(**kwargs):
        decisions.append(kwargs["energy_reader"]())
        current[0]+=timedelta(seconds=901)
        decisions.append(kwargs["energy_reader"]())
        return {"status":"observed","hardware_commands":0}
    monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state",power)
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",cycle)
    _managed_reassessment(environ={},database_url="synthetic",store=Store(),token_store=object(),
        transport=Transport(),now=NOW,clock=lambda:current[0])
    assert decisions[0]["fresh"] is fresh and decisions[1]["fresh"] is False
    assert len(reads)==1


@pytest.mark.parametrize("case", ["new_negative","future_clear","stale_clear","naive_clear"])
def test_current_borehole_fault_reader_keeps_negative_facts_across_read_delay(monkeypatch,case):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    current=[NOW];results=[]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def execute(self,query):
            assert "borehole_interlocks" in query
            current[0]+=timedelta(seconds=5)
            return self
        def fetchall(self):
            if case=="new_negative":
                return [({"borehole_interlocks":{"dry_run_safe":False,
                    "observed_at":current[0].isoformat(),"provider_message_id":"new-fault"}},)]
            clear=current[0]+timedelta(microseconds=1) if case=="future_clear" else current[0]-timedelta(minutes=16)
            if case=="naive_clear":clear=current[0].replace(tzinfo=None)
            return [({"borehole_interlocks":{"dry_run_safe":False,
                        "observed_at":(NOW-timedelta(hours=1)).isoformat()}},),
                ({"borehole_interlocks":{"dry_run_safe":True,"observed_at":clear.isoformat(),
                    "provider_message_id":"unproven-clear"}},)]
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
        lambda **_:Connection())
    def cycle(**kwargs):
        results.append(kwargs["borehole_safety_reader"]())
        return {"status":"observed","hardware_commands":0}
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",cycle)
    _managed_reassessment(environ={},database_url="synthetic",store=Store(),token_store=object(),
        transport=Transport(),now=NOW,clock=lambda:current[0])
    assert results==[False]


@pytest.mark.parametrize("power_offset,eligible", [(6,True),(11,False),(-901,False)])
def test_borehole_eligibility_assesses_power_after_baseline_and_provider_reads(monkeypatch,power_offset,eligible):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from tests.test_rootline_borehole_commissioning import canonical as baseline
    current=[NOW];packets=[];outputs=[]
    evidence={"power":{"battery_soc_pct":90,"solar_power_w":2000,"load_power_w":100,
        "grid_power_w":0,"observed_at":(NOW+timedelta(seconds=power_offset)).isoformat()},
        "borehole_interlocks":{key:True for key in
            ("dry_run_safe","low_water_clear","supply_pressure_safe","full_tank_not_blocking")}}
    def load_baseline(**_):
        current[0]+=timedelta(seconds=5)
        return {**baseline(),"registry_generation":2}
    class Reader(Transport):
        def read_safety_configuration(self,**_):raise RuntimeError("No auxiliary authority")
        def read_output_state(self,**kwargs):
            assert kwargs=={"device_id":"1002851416","channel":1}
            current[0]+=timedelta(seconds=5)
            output={"authoritative":True,"state":"OFF","retrieved_at":current[0].isoformat(),
                "evidence_id":"synthetic-off"}
            outputs.append(deepcopy(output));return output
    def cycle(**kwargs):
        packets.append(kwargs["evidence_factory"]())
        return {"status":"prepared","hardware_commands":0}
    monkeypatch.setattr("modules.telemetry.rootline_borehole_commissioning.load_registered_borehole_baseline",load_baseline)
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",cycle)
    transport=Reader()
    _managed_reassessment(environ={},database_url="synthetic",store=Store(),token_store=object(),
        transport=transport,now=NOW,clock=lambda:current[0],
        evidence_loader=lambda **_: (deepcopy(evidence),NOW.date().isoformat(),NOW))
    artifact=packets[0]["borehole_execution"]
    assert artifact["eligible"] is eligible
    assert artifact["assessed_at"]==outputs[0]["retrieved_at"]==(NOW+timedelta(seconds=10)).isoformat()
    assert transport.calls==[]


@pytest.mark.parametrize("power_offset,fresh", [(0,True),(6,False),(-901,False)])
def test_grid_uses_post_power_and_canonical_clock_with_strict_power_age(monkeypatch,power_offset,fresh):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry import rootline_eskom_runtime as eskom
    from tests import test_rootline_eskom_runtime as fixture
    current=[NOW];invocations=[]
    def power(**_):
        current[0]+=timedelta(seconds=5)
        return {"success":True,"current":{"battery_soc_pct":29,"solar_power_w":0,
            "load_power_w":100,"grid_power_w":0},"source":{"last_reading_at":
                (current[0]+timedelta(seconds=power_offset)).isoformat()}},200
    def canonical_read(*_,**__):
        current[0]+=timedelta(seconds=5)
        return fixture.canonical()
    original=eskom.run_eskom_cycle
    def cycle(**kwargs):
        invocations.append(kwargs["now"])
        assert kwargs["clock"]()==current[0]
        return original(**kwargs,observation_cache=eskom.EskomObservationCache(),
            readback=lambda:{"authoritative":True,"device_id":fixture.CONFIG["ROOTLINE_ESKOM_DEVICE_ID"],
                "online":True,"switch_code":"switch_1","state":"ON",
                "retrieved_at":current[0].isoformat(),"evidence_id":"synthetic-grid-on"},
            dispatch=lambda *_:pytest.fail("retained state must never send"))
    monkeypatch.setattr("modules.telemetry.power_service.get_current_power_state",power)
    monkeypatch.setattr("modules.telemetry.rootline_device_spine.load_device_record",canonical_read)
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",
        lambda **_:{"status":"no_active_managed_device","hardware_commands":0})
    monkeypatch.setattr(eskom,"run_eskom_cycle",cycle)
    result=_managed_reassessment(environ=fixture.CONFIG,database_url="synthetic",store=fixture.Store(),
        token_store=object(),transport=Transport(),now=NOW,clock=lambda:current[0])
    assert invocations==[NOW+timedelta(seconds=10)]
    assert result["eskom"]["decision"]["fresh"] is fresh
    assert result["hardware_commands"]==0



def test_late_optional_borehole_read_cannot_hide_sast_day_change(monkeypatch):
    start=datetime(2026,8,25,21,59,59,500000,tzinfo=timezone.utc)
    result,transport,store,plans,current = _default_injector_clock_case(
        monkeypatch,start=start,borehole_delay=1)
    assert current == start+timedelta(seconds=1)
    assert result["status"] == "managed_device_operating_date_changed"
    assert result["hardware_commands"] == 0 and transport.calls == []
    assert not any(action == "claim_auxiliary_before_on" for action,_ in store.rows)
    assert plans[0]["evidence"]["active_irrigation_context"]["fertilizer_history_complete_through"] == (
        plans[0]["evidence"]["fertilizer_history_complete_through"])


def test_final_canonical_parent_read_past_midnight_refuses_prior_day_premix(monkeypatch):
    start=datetime(2026,8,25,21,59,59,500000,tzinfo=timezone.utc)
    result,transport,store,plans,current = _default_injector_clock_case(
        monkeypatch,start=start,final_parent_delay=1)
    assert current == start+timedelta(seconds=1)
    assert sum(action == "claim_auxiliary_before_on" for action,_ in store.rows) == 1
    assert [(row["device_id"],row["channel"],row["state"]) for row in transport.calls] == [
        ("100204d497",1,"OFF")]
    outcome=next(row["on_outcome"] for action,row in store.rows if action == "record_auxiliary_on_outcome")
    assert outcome["provider_command_attempted"] is False
    assert outcome["status"] == "auxiliary_edge_revalidation_failed"
    assert result["automatic_on_retry"] is False
    assert datetime.fromisoformat(plans[0]["evidence"]["fertilizer_history_complete_through"]) == start
