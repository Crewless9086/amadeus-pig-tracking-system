"""Borehole/B-C regressions through the existing controller and scheduler rails."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest

from modules.telemetry import rootline_borehole_commissioning as borehole
from modules.telemetry import rootline_managed_devices_runtime as managed
from tests.test_rootline_borehole_commissioning import (
    BoreholeStore, BoreholeTransport, canonical,
)


NOW = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)


def eligibility():
    return borehole.build_borehole_runtime_eligibility(
        need={"eligible": True}, baseline={**canonical(), "registry_generation": 2},
        authority={"inside_standing_authority": True},
        provider={"authoritative": True, "state": "OFF"},
        interlocks={"dry_run_safe": True, "low_water_clear": True,
            "supply_pressure_safe": True, "full_tank_not_blocking": True},
        energy={"eligible": True}, requested_seconds=900, now=NOW)


def test_lost_borehole_start_readback_keeps_bounded_observation_pending():
    store = BoreholeStore()
    transport = BoreholeTransport(on_readback="Unknown")
    result = borehole.advance_borehole_execution(eligibility=eligibility(),
        store=store, transport=transport, now=NOW, clock=lambda: NOW)
    assert result["status"] == "borehole_start_observation_pending"
    assert [row["state"] for row in transport.commands] == ["ON"]
    assert result["effects_unknown"] is True
    assert not any(action in {"mark_borehole_active", "record_borehole_completed"}
        for action, _ in store.events)


def test_unavailable_energy_read_does_not_stop_an_owned_borehole():
    backing = BoreholeStore()
    transport = BoreholeTransport()
    result = borehole.advance_borehole_execution(eligibility=eligibility(),
        store=backing, transport=transport, now=NOW, clock=lambda: NOW)
    assert result["status"] == "borehole_started"
    def store(action, body):
        if action == "load_active_auxiliaries":
            return []
        return backing(action, body)
    def unavailable():
        raise TimeoutError("synthetic bounded read timeout")
    result = managed.run_rootline_managed_device_cycle(evidence={},
        transport=transport, store=store, environ={}, allow_new_starts=False,
        now=NOW+timedelta(seconds=60), clock=lambda: NOW+timedelta(seconds=60),
        energy_reader=unavailable, borehole_safety_reader=lambda: True)
    assert result["status"] == "borehole_active"
    assert [row["state"] for row in transport.commands] == ["ON"]


def test_start_observation_recovers_same_claim_and_keeps_original_stop_deadline():
    store, transport = BoreholeStore(), BoreholeTransport(on_readback="Unknown")
    first = borehole.advance_borehole_execution(eligibility=eligibility(), store=store,
        transport=transport, now=NOW, clock=lambda: NOW)
    deadline = first["execution"]["primary_stop_deadline"]
    later = NOW + timedelta(seconds=60)
    pending = borehole.advance_borehole_execution(eligibility={}, store=store,
        transport=transport, now=later, clock=lambda: later)
    assert pending["status"] == "borehole_start_observation_pending"
    transport.state = "ON"
    recovered = borehole.advance_borehole_execution(eligibility={}, store=store,
        transport=transport, now=later, clock=lambda: later)
    assert recovered["status"] == "borehole_start_observed"
    assert recovered["execution"]["execution_id"] == first["execution"]["execution_id"]
    assert recovered["execution"]["primary_stop_deadline"] == deadline
    assert [row["state"] for row in transport.commands] == ["ON"]
    stopped_at = NOW + timedelta(seconds=900)
    stopped = borehole.advance_borehole_execution(eligibility={}, store=store,
        transport=transport, now=stopped_at, clock=lambda: stopped_at)
    assert stopped["status"] == "borehole_completed"
    assert [row["state"] for row in transport.commands] == ["ON", "OFF"]


@pytest.mark.parametrize("fault", ["energy", "protection"])
def test_actual_adverse_evidence_stops_owned_borehole_even_when_other_read_times_out(fault):
    store, transport = BoreholeStore(), BoreholeTransport()
    borehole.advance_borehole_execution(eligibility=eligibility(), store=store,
        transport=transport, now=NOW, clock=lambda: NOW)
    def unavailable(): raise TimeoutError("synthetic")
    def backing(action, body):
        return [] if action == "load_active_auxiliaries" else store(action, body)
    later = NOW + timedelta(seconds=60)
    result = managed.run_rootline_managed_device_cycle(evidence={}, store=backing,
        transport=transport, allow_new_starts=False, now=later, clock=lambda: later,
        energy_reader=(lambda: {"fresh": True, "borehole_eligible": False}) if fault == "energy" else unavailable,
        borehole_safety_reader=(lambda: False) if fault == "protection" else unavailable)
    assert result["status"] == "borehole_completed"
    assert [row["state"] for row in transport.commands] == ["ON", "OFF"]


OFF_TIMER = {"type": "repeat", "at": "0 4 * * 0,1,2,3,4,5,6",
    "atLocal": "synthetic-local-display", "mId": "synthetic-timer-id",
    "coolkit_timer_type": "repeat", "enabled": 1,
    "do": {"switches": [{"outlet": 0, "switch": "off"}]}}


def current_borehole(monkeypatch, *, state="OFF", native=36000, timer=None, now=NOW):
    from tests.test_rootline_commissioning_bridges import (
        borehole_snapshot, pump_database, read_pump,
    )
    from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
    original = borehole_snapshot()
    db = pump_database(original)
    db.record["physical_effect"] = "Borehole 1 pump power"
    current = borehole_snapshot(
        switches=[{"outlet": i, "switch": state.lower() if i == 0 else "off"} for i in range(4)],
        pulses=[{"outlet": 0, "pulse": "on", "width": native * 1000}],
        timers=[deepcopy(OFF_TIMER if timer is None else timer)])
    current.update(retrieved_at=now.isoformat(), trusted_receipt_at=now.isoformat())
    snapshot = read_pump(monkeypatch, current, db)
    baseline = borehole.load_registered_borehole_baseline(connect_factory=db)
    output = output_evidence_from_snapshot(snapshot, device_id="1002851416", channel=1)
    return baseline, output, snapshot, db


def current_eligibility(baseline, output, *, requested=3600, now=NOW):
    return borehole.build_borehole_runtime_eligibility(need={"eligible": True}, baseline=baseline,
        authority={"inside_standing_authority": True}, provider=output,
        interlocks={"dry_run_safe": True, "low_water_clear": True,
            "supply_pressure_safe": True, "full_tank_not_blocking": True},
        energy={"eligible": True}, requested_seconds=requested, now=now)


def test_ten_hour_fallback_preserves_commissioned_reference_and_uses_one_snapshot(monkeypatch):
    from modules.telemetry.rootline_irrigation_execution_store import _valid_borehole_eligibility
    baseline, output, snapshot, db = current_borehole(monkeypatch)
    old_profile = deepcopy(db.record["authority_envelope"]["controller_configuration"])
    assert baseline["native_fail_stop_seconds"] == old_profile["native_fail_stop_seconds"] == 3599
    assert snapshot["timers_enabled"] is True and snapshot["timers_only_turn_off"] is True
    assert snapshot["scenes_enabled"] is snapshot["interlock_enabled"] is False
    artifact = current_eligibility(baseline, output)
    assert artifact["eligible"] and _valid_borehole_eligibility(artifact)
    assert artifact["native_fail_stop_seconds"] == 36000 and artifact["requested_seconds"] == 3600
    assert db.record["authority_envelope"]["controller_configuration"] == old_profile
    class Once(BoreholeTransport):
        def read_safety_configuration(self, **kwargs):
            pytest.fail("must use the same current authenticated configuration proof")
    transport, store = Once(), BoreholeStore()
    result = borehole.advance_borehole_execution(eligibility=artifact, store=store,
        transport=transport, now=NOW, clock=lambda: NOW)
    assert result["status"] == "borehole_started"
    assert [row["state"] for row in transport.commands] == ["ON"]
    assert not _valid_borehole_eligibility({**artifact, "native_fail_stop_seconds": 36001})


@pytest.mark.parametrize("change", ["on", "toggle", "other_outlet", "missing_action", "unknown_action", "native", "stale", "identity"])
def test_current_configuration_rejects_unknown_or_conflicting_controls(monkeypatch, change):
    timer = deepcopy(OFF_TIMER)
    if change in {"on", "toggle"}: timer["do"]["switches"][0]["switch"] = change
    if change == "other_outlet": timer["do"]["switches"][0]["outlet"] = 1
    if change == "missing_action": timer.pop("do")
    if change == "unknown_action": timer["do"]["unknown"] = "on"
    baseline, output, _, _ = current_borehole(monkeypatch, timer=timer,
        native=36001 if change == "native" else 36000)
    if change == "stale":
        output["retrieved_at"] = (NOW-timedelta(minutes=6)).isoformat()
        output["borehole_configuration"]["retrieved_at"] = output["retrieved_at"]
    if change == "identity": output["borehole_configuration"]["device_id"] = "other"
    assert current_eligibility(baseline, output)["eligible"] is False


def test_manual_on_is_adopted_without_command_or_invented_start_then_reconciles_off(monkeypatch):
    baseline, output, _, _ = current_borehole(monkeypatch, state="ON")
    artifact = current_eligibility(baseline, output, requested=36000)
    class AdoptionStore(BoreholeStore):
        def __call__(self, action, body):
            if action == "adopt_borehole_observed_on": self.active = dict(body)
            return super().__call__(action, body)
    store, transport = AdoptionStore(), BoreholeTransport()
    transport.state = "ON"
    adopted = borehole.advance_borehole_execution(eligibility=artifact, store=store,
        transport=transport, now=NOW, clock=lambda: NOW)
    assert adopted["status"] == "borehole_observed_on_adopted" and transport.commands == []
    assert adopted["execution"]["original_start_at"] is None
    assert adopted["execution"]["on_attempts"] == 0
    assert not any(action in {"claim_borehole_before_on", "dispatch_borehole_on_edge"} for action, _ in store.events)
    transport.state = "OFF"
    later = NOW+timedelta(seconds=60)
    result = borehole.advance_borehole_execution(eligibility={}, store=store,
        transport=transport, now=later, clock=lambda: later)
    assert result["status"] == "borehole_completed" and transport.commands == []
    assert result["execution"]["original_start_at"] is None
    assert "verified_runtime_seconds" not in result["execution"]


def test_borehole_admission_is_independent_of_irrigation_and_auxiliary_admission():
    store, transport = BoreholeStore(), BoreholeTransport()
    def backing(action, body):
        return [] if action == "load_active_auxiliaries" else store(action, body)
    result = managed.run_rootline_managed_device_cycle(evidence={"borehole_execution": eligibility()},
        store=backing, transport=transport, environ={"ROOTLINE_BOREHOLE_ENABLED": "true"},
        allow_new_starts=False, allow_borehole_starts=True, now=NOW, clock=lambda: NOW)
    assert result["status"] == "borehole_started"
    assert [row["state"] for row in transport.commands] == ["ON"]
    assert result["blocks_bc"] is False


def test_stale_c_reconciliation_uses_existing_rail_and_preserves_unknown_remainder():
    from modules.telemetry.rootline_execution_runtime import _reconcile_contained_bc_parents
    from tests.test_rootline_parent_job_resolution import subject, _recording_store
    job, parent, controller, _, _ = subject("C12345")
    controller["retrieved_at"] = NOW.isoformat()
    calls = []
    rows = _reconcile_contained_bc_parents(history={"status": "Available", "zones": {
        "C12345": {"contained_parent_jobs": [parent]}}},
        source={"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}, database_url="synthetic",
        readback=lambda **_: controller, token_store=None, store=_recording_store(calls),
        now=NOW, clock=lambda: NOW, authority_checker=lambda *_: True)
    assert len(rows) == 1
    row = rows[0]
    assert row["fabricated_runtime_seconds"] == 0 and row["water_credit_created"] is False
    assert row["cancelled_unverified_remaining_seconds"] == parent["remaining_seconds"]
    assert row["next_attempt_requires_fresh_execution_identity"] is True
    assert row["job_id"] == job["job_id"] and row["job_sha256"] == job["job_sha256"]


@pytest.mark.parametrize("case", ["on", "wrong_device", "authority", "disabled", "parent_changed"])
def test_automatic_reconciliation_cannot_clear_uncertain_current_or_unauthorized_job(case):
    from modules.telemetry.rootline_execution_runtime import _reconcile_contained_bc_parents
    from tests.test_rootline_parent_job_resolution import subject
    _, parent, controller, _, _ = subject("C12345")
    controller["retrieved_at"] = NOW.isoformat()
    if case == "on": controller["channels"][1]["output_state"] = "ON"
    if case == "wrong_device": controller["device_id"] = "other"
    calls = []
    def store(action, body):
        calls.append(action)
        if case == "parent_changed": raise ValueError("contained_parent_execution_changed")
        pytest.fail("must not write or read cancellation for rejected evidence")
    rows = _reconcile_contained_bc_parents(history={"status": "Available", "zones": {
        "C12345": {"contained_parent_jobs": [parent]}}},
        source={"ROOTLINE_AUTONOMOUS_BC_ENABLED": "false" if case == "disabled" else "true"},
        database_url="synthetic", readback=lambda **_: controller, token_store=None, store=store,
        now=NOW, clock=lambda: NOW, authority_checker=lambda *_: case != "authority")
    assert rows == []
    assert calls == (["record_job_resolution"] if case == "parent_changed" else [])


def test_scheduler_keeps_managed_outcome_without_private_payloads():
    from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment
    from tests.test_oom_sakkie_automatic_reassessment_scheduler import memory_store, scheduled_payload, NOW as schedule_now
    rows, store = memory_store()
    run_due_reassessment(payload=scheduled_payload(), store=store, now=schedule_now,
        invoke=lambda: {"success": False, "status": "contained", "effects_unknown": True,
            "managed_device_status": "borehole_start_observation_pending",
            "managed_device_result": {"status": "borehole_start_observation_pending",
                "managed_device": borehole.IDENTITY, "private": "omit", "error_type": "TimeoutError"}})
    outcome = next(value for key, value in rows.items() if key.endswith("-OUTCOME"))
    assert outcome["managed_device_status"] == "borehole_start_observation_pending"
    assert outcome["managed_device_outcomes"] == [{"managed_device": borehole.IDENTITY,
        "status": "borehole_start_observation_pending", "error_type": "TimeoutError"}]

