"""Owner controls through their real validation, planner and coordinator paths."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry import rootline_owner_controls as controls
from modules.telemetry import rootline_water_energy_plan as planner
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_water_energy_plan import daily_program_facts
from tests.test_rootline_command_mode import ENV, start, recover

NOW = datetime(2026, 11, 25, 8, tzinfo=timezone.utc)
ACTOR = "owner-admin:fixture"


def record(device="borehole", *, mode="automatic", fields=None, at=NOW, expiry=None,
        identity="request-one", kind="settings", changes=None):
    if fields is None:
        fields = {"solar_proxy_w": 1800, "battery_floor_pct": 30} if device == "borehole" else {}
    change = {"kind": kind, "device_id": device, "reason": "Owner decision",
        "changes": changes if changes is not None else {"mode": mode,
            "scope": "today" if expiry else "ongoing", "fields": fields}}
    return {"mission_id": "ROOTLINE-OWNER-CONTROLS", "state": "confirmed", "context": {
        "contract_version": controls.VERSION, "event_type": "owner_control",
        "source": "authenticated_owner_controls", "actor": ACTOR, "change": change,
        "request_id": identity, "effective_at": at.isoformat(), "expires_at": expiry.isoformat() if expiry else None}}


def test_today_override_expires_at_sast_midnight_and_restores_ongoing():
    midnight = controls._midnight(NOW)
    rows = [record(), record(mode="paused", at=NOW + timedelta(seconds=1), expiry=midnight,
        identity="temporary", fields={"solar_proxy_w": 2000, "battery_floor_pct": 40})]
    before = controls.project_owner_controls(rows, now=midnight - timedelta(microseconds=1))
    after = controls.project_owner_controls(rows, now=midnight)
    assert before["devices"]["borehole"]["mode"] == "paused"
    assert after["devices"]["borehole"]["mode"] == "automatic"
    assert after["devices"]["borehole"]["fields"]["solar_proxy_w"] == 1800
    assert midnight.hour == 22  # SAST midnight, not UTC midnight.


@pytest.mark.parametrize("mutation", [
    lambda r: r["context"]["change"]["changes"].update(mode="invented"),
    lambda r: r["context"].update(source="ordinary_chat"),
    lambda r: r["context"]["change"].update(device_id="unknown"),
    lambda r: r["context"].update(effective_at="naive"),
    lambda r: r["context"]["change"]["changes"]["fields"].update(solar_proxy_w=True),
])
def test_corrupted_typed_control_fails_closed(mutation):
    row = record()
    mutation(row)
    with pytest.raises((ValueError, controls.ControlError)):
        controls.project_owner_controls([row], now=NOW)


def test_pending_manual_request_is_exact_once_and_later_pause_revokes_it():
    run = record(kind="run", fields={}, changes={}, expiry=controls._midnight(NOW))
    state = controls.project_owner_controls([run], now=NOW)
    assert controls.pending_owner_request(state, "borehole", NOW)["request_id"] == "request-one"
    consumed = {"mission_id": run["mission_id"], "state": "consumed", "context": {
        **{k: run["context"][k] for k in ("contract_version", "event_type", "source", "actor")},
        "request_id": "request-one", "execution_id": "execution-one", "device_id": "borehole", "at": NOW.isoformat()}}
    state = controls.project_owner_controls([run, consumed], now=NOW)
    assert controls.pending_owner_request(state, "borehole", NOW) is None
    assert controls.owner_request_for_execution(state, "borehole", "execution-one", NOW)
    assert controls.owner_request_for_execution(state, "mixer", "execution-one", NOW) is None
    pause = record(mode="paused", identity="pause-later", at=NOW + timedelta(seconds=1))
    state = controls.project_owner_controls([run, consumed, pause], now=NOW + timedelta(seconds=1))
    assert controls.owner_request_for_execution(state, "borehole", "execution-one", NOW + timedelta(seconds=1)) is None


def test_full_schema_supports_real_values_and_rejects_unknown_or_partial_settings():
    empty = controls.project_owner_controls([], now=NOW)
    schema = controls.owner_device_settings("mixer", empty, {}, NOW)
    editable = {f["key"]: f["value"] for f in schema["fields"] if f["editable"]}
    assert editable == {"reserve_soc_pct": 70, "session_minutes": 10, "daily_minutes": 30}
    assert controls._validate_owner_fields("mixer", editable, require_full=True) == editable
    with pytest.raises(ValueError):
        controls._validate_owner_fields("mixer", {"reserve_soc_pct": 70}, require_full=True)
    with pytest.raises(ValueError):
        controls._validate_owner_fields("camp_a", {"duration_minutes": 121})
    with pytest.raises(ValueError):
        controls._validate_owner_fields("eskom", {"on_soc_pct": 45, "off_soc_pct": 40})
    normalized = controls.project_owner_controls([record("mixer", fields={"reserve_soc_pct": 70.0})], now=NOW)
    assert controls.energy_policy_digest("mixer", normalized, NOW) == controls.energy_policy_digest("mixer", None, NOW)


@pytest.fixture
def memory_api(monkeypatch):
    rows = []
    class Connection:
        def __enter__(self):
            self.before = deepcopy(rows)
            return self
        def __exit__(self, kind, value, trace):
            if kind:
                rows[:] = self.before
            return False
        def execute(self, *_): return self
    connection = Connection()
    monkeypatch.setattr(controls, "_connect", lambda *a, **k: connection)
    monkeypatch.setattr(controls, "_read_records", lambda _: deepcopy(rows))
    def write(_connection, identity, context, state, **_):
        value = {"mission_id": "ROOTLINE-OWNER-CONTROLS", "state": state, "context": {
            **deepcopy(context), "contract_version": controls.VERSION, "event_type": "owner_control",
            "source": "authenticated_owner_controls"}}
        rows.append(value)
        return value
    monkeypatch.setattr(controls, "_write", write)
    monkeypatch.setattr(planner, "get_current_water_energy_plan", lambda *a, **k: ({}, 200))
    return rows


def preview_body(rows, **overrides):
    state = controls.project_owner_controls(rows, now=NOW)
    return {"kind": "settings", "device_id": "borehole", "reason": "Reduce backup use",
        "expected_revision": state["devices"]["borehole"]["revision"], "idempotency_key": "preview-key-001",
        "changes": {"mode": "automatic", "scope": "ongoing", "fields": {
            "solar_proxy_w": 1800, "battery_floor_pct": 30}}, **overrides}


def test_preview_apply_readback_and_late_duplicate_replays_receipt(memory_api):
    preview, http = controls.preview_owner_control(preview_body(memory_api), ACTOR, now=NOW)
    assert http == 200 and preview["success"]
    assert preview["preview"]["changes"] == [{"label": "Solar level to stop AC backup (W)", "before": 1500, "after": 1800.0}]
    assert preview["preview"]["expires_at"] == (NOW + timedelta(minutes=10)).isoformat()
    payload = {"preview_id": preview["preview"]["id"], "preview_digest": preview["preview"]["digest"],
        "idempotency_key": "apply-key-001"}
    saved, http = controls.apply_owner_control(payload, ACTOR, now=NOW)
    assert http == 200 and saved["readback_bound"] is True
    replay, http = controls.apply_owner_control(payload, ACTOR, now=NOW + timedelta(days=2))
    assert http == 200 and replay == saved
    assert len([r for r in memory_api if r["state"] == "confirmed"]) == 1
    conflict, http = controls.apply_owner_control({**payload, "preview_digest": "different"}, ACTOR, now=NOW)
    assert http == 409 and conflict["status"] == "idempotency_key_conflict"


def test_expired_wrong_actor_and_stale_preview_never_write(memory_api):
    preview, _ = controls.preview_owner_control(preview_body(memory_api), ACTOR, now=NOW)
    payload = {"preview_id": preview["preview"]["id"], "preview_digest": preview["preview"]["digest"], "idempotency_key": "apply-key-001"}
    assert controls.apply_owner_control(payload, "owner-admin:other", now=NOW)[1] == 403
    assert controls.apply_owner_control(payload, ACTOR, now=NOW + timedelta(minutes=10))[1] == 410
    memory_api.append(record(identity="intervening", mode="paused"))
    rejected, status = controls.apply_owner_control(payload, ACTOR, now=NOW)
    assert status == 409 and rejected["status"] == "settings_revision_changed"
    assert len([r for r in memory_api if r["state"] == "confirmed"]) == 1


def test_unknown_camp_duration_allows_mode_only_without_inventing_value(memory_api):
    state = controls.project_owner_controls([], now=NOW)
    schema = controls.owner_device_settings("camp_a", state, {}, NOW)
    duration = next(f for f in schema["fields"] if f["key"] == "duration_minutes")
    assert duration["value"] is None and duration["required"] is False
    body = preview_body([], device_id="camp_a", expected_revision=state["devices"]["camp_a"]["revision"],
        changes={"mode": "paused", "scope": "ongoing", "fields": {}})
    preview, status = controls.preview_owner_control(body, ACTOR, now=NOW)
    assert status == 200, preview
    saved, status = controls.apply_owner_control({"preview_id": preview["preview"]["id"],
        "preview_digest": preview["preview"]["digest"], "idempotency_key": "apply-mode-only"}, ACTOR, now=NOW)
    assert status == 200, saved
    readback = controls.project_owner_controls(memory_api, now=NOW)["devices"]["camp_a"]
    assert readback["mode"] == "paused" and readback["fields"] == {}


def test_runtime_camp_duration_pause_and_explicit_day_skip_keep_live_safety():
    with timed_control_scope(ENV):
        facts = daily_program_facts(NOW)
        saved = planner.build_daily_program(facts, NOW.date().isoformat(), now=NOW)
        settings = record("camp_a", fields={"duration_minutes": 30})
        state = controls.project_owner_controls([settings], now=NOW)
        facts["owner_controls"] = state
        current = planner.project_saved_program_for_execution(saved, facts, now=NOW)
        target = next(t for t in current["candidate_tasks"] if t["task_id"] == "irrigation_A12345")
        assert target["requested_total_duration_minutes"] == 30
        pause = record("camp_a", mode="paused", fields={"duration_minutes": 30})
        facts["owner_controls"] = controls.project_owner_controls([pause], now=NOW)
        current = planner.project_saved_program_for_execution(saved, facts, now=NOW)
        target = next(t for t in current["candidate_tasks"] if t["task_id"] == "irrigation_A12345")
        assert target["zone_decision"] == "Hold"
        saved["daily_program"]["base_tasks"][0]["owner_skip"] = True
        controls.apply_controls_to_plan(saved, state, now=NOW)


def test_manual_stop_uses_real_coordinator_without_moving_deadline_or_claiming_completion():
    _, _, store, transport, clock = start("A12345", at=NOW)
    active = deepcopy(store.active)
    request = record("camp_a", kind="stop", changes={"execution_id": active["execution_id"]}, expiry=controls._midnight(NOW))["context"]
    class RequestedStore:
        def __call__(self, action, body):
            if action == "load_owner_control_stop": return request
            return store(action, body)
    clock[0] += timedelta(seconds=100)
    with timed_control_scope(ENV):
        result = recover(RequestedStore(), transport, clock)
    assert result["status"] == "irrigation_off_command_accepted"
    assert result["execution"]["primary_stop_deadline"] == active["primary_stop_deadline"]
    assert result["execution"]["reason"] == "owner_requested_stop"
    assert result["execution"]["command_program_completed"] is False
    assert [row[2] for row in transport.calls] == ["ON", "OFF"]


def test_mixer_saved_limits_change_real_task_duration_and_energy_eligibility():
    from modules.telemetry.rootline_auxiliary_management import build_auxiliary_tasks, mixing_daily_accounting
    row = record("mixer", fields={"reserve_soc_pct": 80, "session_minutes": 5, "daily_minutes": 15})
    state = controls.project_owner_controls([row], now=NOW)
    power = {"observed_at": NOW.isoformat(), "battery_soc_pct": 90, "solar_power_w": 0,
        "load_power_w": 900, "grid_power_w": 0}
    with timed_control_scope(ENV):
        account = mixing_daily_accounting([], now=NOW)
        canonical_session = deepcopy(account["mixer_session"])
        tasks = build_auxiliary_tasks(batch={"state": "batch_reported_prepared"}, power=power,
            verified_mixing=[], mixing_history_complete_through=NOW.isoformat(), now=NOW, owner_controls=state)
        mixer = next(t for t in tasks["irrigation_auxiliary_tasks"] if t["device_type"] == "fertilizer_mixer")
        assert mixer["planned_seconds"] == 300 and mixer["decision"] == "Run now"
        assert mixing_daily_accounting([], now=NOW)["mixer_session"] == canonical_session
        held = build_auxiliary_tasks(batch={"state": "batch_reported_prepared"}, power={**power, "battery_soc_pct": 75},
            verified_mixing=[], mixing_history_complete_through=NOW.isoformat(), now=NOW, owner_controls=state)
        assert next(t for t in held["irrigation_auxiliary_tasks"] if t["device_type"] == "fertilizer_mixer")["decision"] == "Run later"


def test_saved_injection_limit_stops_next_pulse_without_changing_accepted_first_pulse():
    from modules.telemetry import rootline_irrigation_coordinator as coordinator
    from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility, build_auxiliary_tasks
    _, _, store, transport, clock = start("B12345", at=NOW)
    clock[0] = NOW + timedelta(seconds=600)
    context = planner._active_irrigation_context(store.active, store.rows, True, "BATCH", now=clock[0])
    context.update(premix_command_accepted=True, fertilizer_history_complete_through=clock[0].isoformat())
    context["zone_output_evidence"] = transport.read_output_state(device_id="100204e9bc", channel=1)
    with timed_control_scope(ENV):
        eligibility = build_auxiliary_eligibility(task={"auxiliary_device_id": "FERTILIZER-INJECTION-CH1"},
            safety=transport.read_safety_configuration(device_id="100204d497", channel=1), context=context,
            flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": True}, now=clock[0])
        result = coordinator.advance_auxiliary_execution(eligibility=eligibility, store=store, transport=transport,
            revalidate=lambda _: context, now=clock[0], clock=lambda: clock[0])
        assert result["status"] == "auxiliary_on_command_accepted"
        original_deadline = result["execution"]["primary_stop_deadline"]
        state = controls.project_owner_controls([record("injection", fields={"max_pulses_per_run": 1}, at=clock[0])], now=clock[0])
        clock[0] += timedelta(seconds=120)
        stopped = coordinator.advance_auxiliary_execution(eligibility=None, store=store, transport=transport,
            auxiliary_device_id="FERTILIZER-INJECTION-CH1", now=clock[0], clock=lambda: clock[0])
        assert stopped["execution"]["primary_stop_deadline"] == original_deadline
        clock[0] = NOW + timedelta(seconds=1320)
        context = planner._active_irrigation_context(store.active, store.rows, True, "BATCH", now=clock[0])
        context.update(premix_command_accepted=True, fertilizer_history_complete_through=clock[0].isoformat())
        context["zone_output_evidence"] = transport.read_output_state(device_id="100204e9bc", channel=1)
        tasks = build_auxiliary_tasks(batch={"state": "batch_reported_prepared"}, active_irrigation_context=context,
            now=clock[0], owner_controls=state)
        injection = next(t for t in tasks["irrigation_auxiliary_tasks"] if t["device_type"] == "fertilizer_injection_valve")
    assert injection["maximum_pulses_per_segment"] == 1
    assert injection["decision"] != "Run now"
    assert injection["pulse_seconds"] == 120
    assert [row[2] for row in transport.calls] == ["ON", "ON", "OFF"]
