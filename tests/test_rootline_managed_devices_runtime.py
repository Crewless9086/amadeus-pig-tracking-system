from datetime import datetime, timedelta, timezone

from modules.telemetry.rootline_managed_devices_runtime import (
    run_rootline_managed_device_cycle,
)
from modules.telemetry.rootline_execution_runtime import (
    run_rootline_managed_device_reassessment,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self):
        self.active_aux = None
        self.active_borehole = None
        self.rows = []

    def __call__(self, action, payload):
        if action == "load_active_auxiliary":
            return self.active_aux
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
        return {"authoritative": True, "state": self.state, "evidence_id": "STATE-1"}

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
            "verified_mixing_minutes_today": 0, "verified_mixing_sessions_today": 0,
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
    assert result["status"] == "auxiliary_started" and result["blocks_bc"] is True
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
        "fertilizer_needed": True, "job_id": "ROOTLINE-IRRIGATION-JOB-" + "A" * 24,
        "job_sha256": "a" * 64, "segment_identity": "ROOTLINE-JOB-SEGMENT-" + "B" * 24,
        "active_zone_ids": ["B12345"], "zone_execution_id": "ZONE-EXEC-1",
        "zone_start_evidence": {"evidence_id": "START-1", "zone_execution_id": "ZONE-EXEC-1",
            "observed_at": start},
        "zone_output_evidence": {"evidence_id": "OUTPUT-1", "zone_execution_id": "ZONE-EXEC-1",
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
        "start_evidence": {"authoritative": True, "state": "ON"}}
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


def test_default_loader_refreshes_active_zone_then_scheduler_starts_injector(monkeypatch):
    active = {"action": "mark_active", "state": "Active", "execution_id": "ZONE-EXEC-1",
        "zone_id": "B12345", "device_id": "100204e9bc", "channel": 1,
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
    transport = Transport(); store = Store()
    result = run_rootline_managed_device_reassessment(
        environ={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true"},
        database_url="postgres://test", store=store, token_store=object(),
        transport=transport, now=NOW)
    assert result["status"] == "auxiliary_started"
    assert [(row["channel"], row["state"]) for row in transport.calls] == [(1, "ON")]


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
        "borehole_interlocks": {"observed_at": NOW.isoformat(), "dry_run_safe": True,
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
