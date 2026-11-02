from copy import deepcopy
from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
import json
from unittest import mock

import pytest

from modules.telemetry import rootline_device_registry as registry
from modules.telemetry.rootline_adaptive_irrigation import build_adaptive_irrigation_decisions
from modules.telemetry.rootline_daily_advisor import _active_policy_snapshot
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline, load_canonical_a_irrigation_binding)
from modules.telemetry.rootline_execution_authority import build_execution_eligibility, validate_execution_eligibility
from modules.telemetry.rootline_execution_runtime import run_rootline_execution_cycle, supervise_rootline_active_execution
from modules.telemetry.rootline_irrigation_execution_contract import validate_commissioning
from modules.telemetry.rootline_operating_policy import normalize_policy_snapshot, PolicyValidationError
from tests.test_rootline_adaptive_irrigation import evidence as adaptive_evidence
from tests.test_rootline_execution_authority import inputs
from tests.test_rootline_execution_runtime import NOW, Store, Transport, controller
from tests.test_rootline_irrigation_execution_contract import evidence as commissioning_evidence
from tests.test_rootline_operating_policy import unknown_policy


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fresh_adaptive_evidence():
    value = adaptive_evidence()
    for key in ("power", "local_weather", "forecast", "water"):
        value[key]["observed_at"] = NOW.isoformat()
    for zone in value["zones"]:
        zone["visible_need_observed_at"] = NOW.isoformat()
        zone["completion_ledger_complete_through"] = NOW.isoformat()
    return value


def a_policy(**changes):
    return {"daylight_window": "any_time", "minimum_useful_runtime_minutes": 5,
        "maximum_continuous_runtime_minutes": 60, "requested_total_duration_minutes": 35,
        "target_days_per_week": "need_based", "water_supply": "gravity_fed_downhill",
        "evidence_source": "canonical:test-owner-policy", **changes}


def successor():
    policy = unknown_policy()
    policy["contract_version"] = "rootline_operating_policy_abc.v2"
    policy["zones"]["A12345"] = a_policy()
    policy["crop_need_bands"]["A12345"] = "Unknown"
    return policy


def canonical_record():
    raw = commissioning_evidence("A12345", 4)
    proof = validate_commissioning("A12345", raw, now=NOW)
    material = {"contract_version": "rootline_a_irrigation_commissioning.v1", "evidence": raw}
    reference = {"source": "physical_review", "evidence_id": "A-OWN-PROOF",
        "observed_at": raw["observed_at"], "sha256": digest(material)}
    return {"provider": "ifttt_ewelink", "provider_account_binding": "ewelink_owner_account",
        "device_id": "100204e9bc", "channel": 4, "physical_name": "A Camp",
        "device_type": "gravity_irrigation_valve", "adapter_profile": "ifttt_ewelink_relay",
        "safe_state": "OFF", "maximum_runtime_seconds": 3599, "native_fail_stop_seconds": 3599,
        "readback": "provider_state", "physical_effect": "A12345 irrigation water flow",
        "dependencies": [], "manual_isolation": "owner-proven manual valve",
        "commissioning_stage": "standing_active", "standing_authority": True,
        "registry_generation": 1, "commissioning_evidence": {"supervised": reference},
        "historical_commissioning_evidence": {key: proof[key] for key in (
            "commissioning_id", "commissioning_sha256", "configuration_generation")},
        "authority_envelope": {"standing_authority_id": "A-OWN-AUTHORITY", "version": "1",
            "issuer": "owner_policy", "policy_sha256": "a" * 64, "revoked": False,
            "irrigation_commissioning": {**material, "reference": reference}}}


class CanonicalRead:
    """Exercise the real spine resolver with a strict read-only SQL fake."""
    def __init__(self, record=None, *, evidence_current=True, authority_active=True):
        self.record = record or canonical_record()
        self.evidence_current = evidence_current
        self.authority_active = authority_active
        self.queries = []
    def __call__(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def execute(self, sql, params):
        assert sql.lstrip().lower().startswith("select ")
        self.queries.append((sql, params))
        if "from app_private.rootline_device_registry where" in sql:
            assert params == ("ifttt_ewelink:ewelink_owner_account:100204e9bc:4",)
            self.row = ("rootline_device_spine.v1", self.record, digest(self.record), 1, digest(self.record))
        elif "from app_private.rootline_device_commissioning_evidence e" in sql:
            ref = self.record["authority_envelope"]["irrigation_commissioning"]["reference"]
            self.row = (ref["evidence_id"], ref["sha256"], self.evidence_current)
        elif "from app_private.rootline_standing_authorities a" in sql:
            authority = self.record["authority_envelope"]
            self.row = (authority["standing_authority_id"], authority["version"],
                authority["policy_sha256"], self.authority_active)
        else:
            raise AssertionError(sql)
    def fetchone(self): return self.row


def a_binding():
    return load_canonical_a_irrigation_binding(connect_factory=CanonicalRead(), now=NOW)


@contextmanager
def commissioned_a():
    token = registry._canonical_irrigation_binding.set(a_binding())
    try: yield
    finally: registry._canonical_irrigation_binding.reset(token)


def test_a_readiness_does_not_transfer_commissioning_or_enable_e():
    a = registry.get_device_contract("A12345")
    assert a["plumbing_ready"] is True and a["commissioned"] is False
    assert a["authority_flag"] == "ROOTLINE_A_ENABLED" and a["channel"] == 4
    assert "A12345" not in registry.commissioned_irrigation_contracts(environ={"ROOTLINE_A_ENABLED": "true"})
    assert registry.get_device_contract("E12345")["plumbing_ready"] is False


def test_a_canonical_proof_resolves_own_identity_without_modifying_bc_baseline():
    before = commissioned_controller_baseline()
    binding = a_binding()
    assert binding["commissioned"] is True
    assert binding["commissioning_id"] not in before["irrigation_commissioning_ids"].values()
    with commissioned_a():
        assert set(registry.commissioned_irrigation_contracts(environ={"ROOTLINE_A_ENABLED": "true"})) == {"A12345"}
        assert set(registry.commissioned_irrigation_contracts(environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"})) == {"B12345", "C12345"}
        assert "E12345" not in registry.commissioned_irrigation_contracts(environ={"ROOTLINE_E_ENABLED": "true"})
    assert commissioned_controller_baseline() == before
    assert registry.get_device_contract("A12345")["commissioned"] is False


@pytest.mark.parametrize("change", [
    {"channel": 1}, {"device_id": "OTHER"}, {"physical_effect": "B12345 irrigation water flow"},
    {"native_fail_stop_seconds": 3600}, {"standing_authority": False},
])
def test_a_canonical_record_rejects_cross_identity_or_unproven_bounds(change):
    record = canonical_record(); record.update(change)
    try: value = load_canonical_a_irrigation_binding(connect_factory=CanonicalRead(record), now=NOW)
    except ValueError: value = None
    assert value is None


@pytest.mark.parametrize("kwargs", [{"evidence_current": False}, {"authority_active": False}])
def test_a_invalidated_proof_or_revoked_authority_fails_closed(kwargs):
    with pytest.raises(ValueError):
        load_canonical_a_irrigation_binding(connect_factory=CanonicalRead(**kwargs), now=NOW)


def test_a_altered_physical_proof_cannot_reuse_reference_digest():
    record = canonical_record()
    record["authority_envelope"]["irrigation_commissioning"]["evidence"]["configuration_generation"] = 2
    assert load_canonical_a_irrigation_binding(connect_factory=CanonicalRead(record), now=NOW) is None


def test_old_exact_bc_snapshot_remains_compatible_and_a_requires_explicit_successor():
    old = normalize_policy_snapshot(unknown_policy())
    assert set(old["zones"]) == {"B12345", "C12345"}
    assert "contract_version" not in old
    assert _active_policy_snapshot({"policy": old}) == old
    raw = successor(); new = normalize_policy_snapshot(raw)
    assert new["zones"]["A12345"]["crop_use"] == "Unknown"
    assert _active_policy_snapshot({"policy": new}) == new
    raw.pop("contract_version")
    with pytest.raises(PolicyValidationError): normalize_policy_snapshot(raw)


def test_a_unknown_runtime_cannot_inherit_two_hour_four_day_bc_target():
    data = fresh_adaptive_evidence()
    data["zones"].append({**deepcopy(data["zones"][0]), "zone_id": "A12345"})
    rows = {row["zone_id"]: row for row in build_adaptive_irrigation_decisions(data, now=NOW)["zones"]}
    assert rows["A12345"]["decision"] == "Needs Data"
    assert rows["A12345"]["requested_total_duration_minutes"] is None
    assert rows["A12345"]["weekly_obligation"]["target_days_per_week"] is None
    assert rows["B12345"]["requested_total_duration_minutes"] == 120


@pytest.mark.parametrize("hour", [0, 3, 12, 23])
def test_a_current_need_supports_own_runtime_at_any_hour(hour):
    clock = NOW.replace(hour=hour)
    data = fresh_adaptive_evidence()
    data["zones"] = [{"zone_id": "A12345", "operating_policy": a_policy(),
        "visible_need": "dry", "visible_need_observed_at": clock.isoformat(),
        "visible_need_source": "governed_sensor", "completion_ledger_complete_through": clock.isoformat()}]
    data["local_weather"] = {"observed_at": clock.isoformat(), "rain_rate_mm_h": 0, "rain_today_mm": 0}
    row = next(row for row in build_adaptive_irrigation_decisions(data, now=clock)["zones"] if row["zone_id"] == "A12345")
    assert row["decision"] == "Run now" and row["requested_total_duration_minutes"] == 35
    assert row["expected_segment_count"] == 1 and row["weekly_obligation"]["mode"] == "need_based"
    assert row["delivered_volume"] == "Unavailable"


@pytest.mark.parametrize("change", [{"water_supply": "Unknown"}, {"requested_total_duration_minutes": "Unknown"},
    {"minimum_useful_runtime_minutes": "Unknown"}])
def test_a_unknown_dependent_input_holds_a_only(change):
    data = fresh_adaptive_evidence()
    data["zones"].append({**deepcopy(data["zones"][0]), "zone_id": "A12345", "operating_policy": a_policy(**change)})
    rows = {row["zone_id"]: row for row in build_adaptive_irrigation_decisions(data, now=NOW)["zones"]}
    assert rows["A12345"]["decision"] == "Needs Data"
    assert rows["B12345"]["decision"] == "Run now"


@pytest.mark.parametrize("sibling", [1, 2, 3])
def test_a_admission_rejects_each_other_open_output_including_held_e(sibling):
    plan, evidence, readback = inputs(zone="A12345")
    with commissioned_a():
        eligible = build_execution_eligibility(plan=plan, evidence=evidence, controller=readback, now=NOW)
        assert eligible["eligible"] is True and eligible["channel"] == 4
        assert validate_execution_eligibility(eligible, now=NOW) == eligible
        readback["channels"][sibling-1]["output_state"] = "ON"
        assert build_execution_eligibility(plan=plan, evidence=evidence, controller=readback, now=NOW)["eligible"] is False
    assert validate_execution_eligibility(eligible, now=NOW) is None


class ATransport(Transport):
    observed_at = NOW
    def read_output_state(self, **kwargs):
        state = self.calls[-1]["state"] if self.calls else "OFF"
        return {**kwargs, "authoritative": True, "state": state,
            "evidence_id": "SYNTHETIC-A-" + state, "retrieved_at": self.observed_at.isoformat()}
    def read_safety_configuration(self, **kwargs):
        assert kwargs == {"device_id": "100204e9bc", "channel": 4}
        return {**super().read_safety_configuration(**kwargs), "zone_id": "A12345", "channel": 4}


def test_a_only_flag_runs_through_existing_coordinator_and_restart_stops_with_flag_off():
    plan, evidence, readback = inputs(zone="A12345")
    task = plan["candidate_tasks"][0]
    task.update(planned_duration_minutes=35, requested_total_duration_minutes=35, expected_segment_count=1)
    store = Store(); transport = ATransport()
    def refresh(source, database_url, now):
        registry._canonical_irrigation_binding.set(a_binding() if source.get("ROOTLINE_A_ENABLED") == "true" else None)
    with mock.patch("modules.telemetry.rootline_execution_runtime._refresh_a_irrigation_binding", side_effect=refresh), mock.patch(
            "modules.telemetry.rootline_execution_runtime.build_water_energy_plan", return_value=plan):
        result = run_rootline_execution_cycle(notify=lambda *_: {"success": True},
            environ={"ROOTLINE_A_ENABLED": "true"}, now=NOW, clock=lambda: NOW,
            store=store, token_store=object(), transport=transport,
            evidence_loader=lambda **_: (evidence, "2026-08-08", NOW), readback=lambda **_: readback,
            owner_user_id="42", chat_id="42", observation_store=lambda *_: {"success": True},
            authority_checker=lambda *_: True)
    assert result["status"] == "segment_started"
    assert store.active["zone_id"] == "A12345" and store.active["planned_runtime_seconds"] == 2100
    assert [call["state"] for call in transport.calls] == ["ON"]
    clock = NOW + timedelta(minutes=36)
    transport.observed_at = clock
    result = supervise_rootline_active_execution(notify=lambda *_: {"success": True},
        environ={}, now=clock, clock=lambda: clock, store=store, token_store=object(), transport=transport,
        owner_user_id="42", chat_id="42")
    assert [call["state"] for call in transport.calls] == ["ON", "OFF"]
    assert result["hardware_commands"] == 1
    assert result["status"] == "segment_completed"
    assert result["execution"]["verified_runtime_seconds"] == 2100
    assert result["execution"]["job_completed"] is True


def a_authority_policy():
    return {"contract_version": "rootline_a_standing_authority.v1",
        "device_keys": ["ifttt_ewelink:ewelink_owner_account:100204e9bc:4"],
        "zone_ids": ["A12345"], "allowed_channels": [4],
        "provider": "ifttt_ewelink", "provider_account_binding": "ewelink_owner_account",
        "device_id": "100204e9bc", "maximum_runtime_seconds": 3599,
        "water_supply": "gravity_fed_downhill", "own_operating_policy_required": True,
        "simultaneous_outputs_allowed": False, "mutual_exclusion_required": True,
        "missing_or_stale_reservoir_observation_is_hold": False,
        "fresh_adverse_reservoir_evidence_is_hold": True, "unproven_reservoir_water_credit_litres": 0,
        "fresh_weather_and_rain_hold_required": True, "current_plan_identity_required": True,
        "application_timeout_required": True, "provider_on_off_readback_required": True,
        "explicit_exclusions": ["fertilizer_injection", "fertilizer_mixing", "borehole_pump"],
        "emergency_off_owner": "synthetic A coordinator", "emergency_off_procedure": "exact OFF and readback",
        "provider_fail_stop_proven": True, "physical_fail_safe_proven": True,
        "power_restoration_off_proven": True, "automatic_on_retry": False}


@pytest.mark.parametrize("change", [{"contract_version": "rootline_bc_standing_authority.v2"},
    {"zone_ids": ["A12345", "B12345"]}, {"allowed_channels": [1, 4]},
    {"water_supply": "Unknown"}, {"own_operating_policy_required": False},
    {"explicit_exclusions": []}, {"automatic_on_retry": True}, {"physical_fail_safe_proven": False}])
def test_a_authority_requires_own_scope_and_all_common_safety(change):
    from modules.telemetry.rootline_execution_runtime import _a_authority_policy_proven
    policy = a_authority_policy()
    artifact = {"zone_id": "A12345", "channel": 4, "maximum_duration_seconds": 2100}
    assert _a_authority_policy_proven(policy, artifact, policy["device_keys"])
    assert not _a_authority_policy_proven({**policy, **change}, artifact, policy["device_keys"])


def test_a_transport_refreshes_own_proof_and_revocation_preserves_exact_durable_off():
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty
    from tests.test_rootline_ifttt_transport import snapshot, Response
    canonical = CanonicalRead()
    calls = []
    def send(request, timeout):
        calls.append(request.full_url)
        return Response()
    snap = snapshot(firmware="3.8.2", commissioned_baseline_fresh=True)
    transport = RootlineIFTTTTransport(token_store=object(),
        environ={"ROOTLINE_IFTTT_MAKER_KEY": "synthetic-only"},
        readback=lambda **_: snap, http_open=send, commissioning_connect_factory=canonical)
    with commissioned_a():
        assert transport.read_safety_configuration(device_id="100204e9bc", channel=4)["authoritative"]
        canonical.authority_active = False
        assert not transport.read_safety_configuration(device_id="100204e9bc", channel=4)["authoritative"]
    # No canonical binding survives; only the exact persisted execution can stop.
    assert not transport.set_state(device_id="100204e9bc", channel=4, state="ON",
        idempotency_key="A-OFF:ON")["accepted_unambiguous"]
    assert not transport.set_state(device_id="100204e9bc", channel=4, state="OFF",
        idempotency_key="A-OFF:OFF:1")["accepted_unambiguous"]
    duty = {"execution_id": "A-OFF", "zone_id": "A12345", "device_id": "100204e9bc",
        "channel": 4, "commissioning_id": a_binding()["commissioning_id"]}
    with execution_duty(duty):
        assert transport.set_state(device_id="100204e9bc", channel=4, state="OFF",
            idempotency_key="A-OFF:OFF:1")["accepted_unambiguous"]
        assert not transport.set_state(device_id="100204e9bc", channel=3, state="OFF",
            idempotency_key="A-OFF:OFF:2")["accepted_unambiguous"]
    assert len(calls) == 1 and "/irrigation_1_ch4_off/" in calls[0]


@pytest.mark.parametrize("segment", [1, 2])
def test_a_rain_after_start_stops_exact_channel_and_replay_keeps_partial(segment):
    from tests.test_rootline_active_weather_stop import subject, supervise, NOW as RAIN_NOW
    from tests.test_rootline_active_supervision import ExecutionStore
    from modules.telemetry.rootline_irrigation_job_contract import validate_weather_stopped_execution
    _, active = subject(zone="A12345", segment=segment, prior=3599 if segment == 2 else 0)
    active["channel"] = active["start_evidence"]["channel"] = 4
    active["commissioning_id"] = a_binding()["commissioning_id"]
    store = ExecutionStore(active, fail="record_completed")
    first, _, transport, _ = supervise(active, store=store)
    assert first["success"] is False and store.active["state"] == "stopping"
    store.fail = None
    second, _, _, _ = supervise(active, store=store, transport=transport,
        clock=lambda: RAIN_NOW + timedelta(minutes=61),
        reader=lambda **_: pytest.fail("persisted weather stop must not replan"))
    assert second["status"] == "segment_stopped_for_weather"
    assert validate_weather_stopped_execution(second["execution"])
    assert second["execution"]["verified_runtime_seconds"] == 0
    assert second["execution"]["cumulative_verified_runtime_seconds"] == active["cumulative_verified_runtime_seconds"]
    assert all(call["channel"] == 4 and call["state"] == "OFF" for call in transport.calls)


def test_a_water_permission_never_transfers_bc_fertilizer_permission():
    from modules.telemetry.rootline_auxiliary_management import build_fertilized_irrigation_sequence, _injection_gate
    with commissioned_a():
        with pytest.raises(ValueError, match="fertilized_irrigation_envelope_invalid"):
            build_fertilized_irrigation_sequence(zone_id="A12345")
        assert _injection_gate({"active_zone_ids": ["A12345"], "job_id": "ROOTLINE-IRRIGATION-JOB-A",
            "job_sha256": "a" * 64, "segment_identity": "ROOTLINE-JOB-SEGMENT-A"}, NOW) == "exactly_one_bc_zone_required"


def test_a_honest_midweek_epoch_covers_current_need_without_inventing_weekly_history():
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event, project_canonical_irrigation_history
    event = build_typed_history_event(event_id="A-HONEST-EPOCH", event_at=NOW,
        event_type="PLANNING_EPOCH_STARTED", zone_id="A12345",
        details={"epoch_start": NOW.isoformat(), "provenance": "reviewed_reconciliation"})
    event["event_at"] = NOW  # Production PostgreSQL rows supply timestamps, not strings.
    history = project_canonical_irrigation_history([event], snapshot_cutoff=NOW)["zones"]
    assert history["A12345"]["complete_through"] is None
    assert history["A12345"]["epoch_complete_through"] == NOW.isoformat()
    assert history["A12345"]["verified_completed_days"] == []
    assert history["B12345"]["epoch_complete_through"] is None


@pytest.mark.parametrize("defect", ["native_shorter", "native_unproven", "wrong_channel", "early_stop", "missing_start"])
def test_a_short_target_cannot_claim_completion_outside_its_backup_and_exact_readbacks(defect):
    from tests.test_rootline_active_weather_stop import subject, NOW as RAIN_NOW
    from modules.telemetry.rootline_irrigation_coordinator import _provider_bounded_outcome
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job
    job = build_irrigation_job(zone_id="A12345", operating_date=RAIN_NOW.date().isoformat(),
        requested_total_seconds=2100, maximum_segment_seconds=3599, plan_identity="A-SHORT-TEST",
        requested_total_minutes=35, expected_segment_count=1)
    _, active = subject(zone="A12345", total=2100, job=job)
    active["expected_segment_count"] = 1
    claimed = RAIN_NOW - timedelta(seconds=100)
    active.update(channel=4, planned_runtime_seconds=2100, primary_stop_deadline=(claimed + timedelta(seconds=2100)).isoformat())
    active["start_evidence"]["channel"] = 4
    stopped_at = claimed + timedelta(seconds=2101)
    shutdown = {"authoritative": True, "state": "OFF", "device_id": "100204e9bc", "channel": 4,
        "evidence_id": "A-SHORT-OFF", "retrieved_at": stopped_at.isoformat()}
    assert _provider_bounded_outcome(active, shutdown, stopped_at)["verified_runtime_minutes"] == 35
    if defect == "native_shorter": active["native_fail_stop_deadline"] = (claimed + timedelta(seconds=2000)).isoformat()
    elif defect == "native_unproven": active["native_fail_stop_deadline"] = (claimed + timedelta(seconds=3600)).isoformat()
    elif defect == "wrong_channel": shutdown["channel"] = 1
    elif defect == "early_stop": shutdown["retrieved_at"] = (claimed + timedelta(seconds=2099)).isoformat()
    elif defect == "missing_start": active["start_evidence"] = {}
    assert _provider_bounded_outcome(active, shutdown, stopped_at) == {}



def test_a_active_due_stop_skips_optional_commissioning_reads_on_execution_cycle():
    from tests.test_rootline_active_weather_stop import subject, Transport as StopTransport, NOW as RAIN_NOW
    from tests.test_rootline_active_supervision import ExecutionStore
    _, active = subject(zone="A12345")
    active["channel"] = active["start_evidence"]["channel"] = 4
    active["commissioning_id"] = a_binding()["commissioning_id"]
    clock = RAIN_NOW + timedelta(hours=1)
    transport = StopTransport(clock=lambda: clock)
    with mock.patch("modules.telemetry.rootline_execution_runtime._refresh_a_irrigation_binding",
            side_effect=AssertionError("active OFF waited for optional new-start proof")):
        result = run_rootline_execution_cycle(notify=lambda *_: {"success": True},
            environ={"ROOTLINE_A_ENABLED": "true"}, now=clock, clock=lambda: clock,
            store=ExecutionStore(active), token_store=object(), transport=transport,
            owner_user_id="42", chat_id="42")
    assert result["status"] == "segment_completed"
    assert [(call["channel"], call["state"]) for call in transport.calls] == [(4, "OFF")]


@pytest.mark.parametrize("maximum,segments", [(60, 1), (20, 2)])
def test_real_advisor_reader_planner_and_authority_preserve_own_a_policy(maximum, segments):
    from modules.telemetry.rootline_daily_advisor import build_rootline_daily_advisor
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event, project_canonical_irrigation_history
    from modules.telemetry.rootline_water_energy_plan import read_current_water_energy_evidence, build_water_energy_plan
    from tests.test_rootline_daily_advisor import active_policy_v2, dry_brief_at
    raw = successor()
    raw["live_rain_hold"] = active_policy_v2()["policy"]["live_rain_hold"]
    raw["zones"]["A12345"] = a_policy(maximum_continuous_runtime_minutes=maximum)
    snapshot = normalize_policy_snapshot(raw)
    brief = dry_brief_at(NOW)
    brief["current_conditions"]["rain_today_mm"] = 0
    brief["current_weather_packet"] = {"success": True,
        "source": {"last_reading_at": NOW.isoformat()},
        "current": {"rain_rate_mm_h": 0, "rain_today_mm": 0}}
    advisor = build_rootline_daily_advisor(brief, NOW.date().isoformat(),
        active_policy={"proposal_id": "SYNTHETIC-A-POLICY", "version": 4, "policy": snapshot}, now=NOW)
    a = next(row for row in advisor["zones"] if row["zone_id"] == "A12345")
    assert a["live_rain_release_proven"] is True
    assert a["operating_policy"]["maximum_continuous_runtime_minutes"] == maximum
    epoch = build_typed_history_event(event_id="SYNTHETIC-A-READER-EPOCH", event_at=NOW,
        event_type="PLANNING_EPOCH_STARTED", zone_id="A12345",
        details={"epoch_start": NOW.isoformat(), "provenance": "reviewed_reconciliation"})
    epoch["event_at"] = NOW
    history = project_canonical_irrigation_history([epoch], snapshot_cutoff=NOW)
    loaded = {"power": ({}, 200), "forecast": ({}, 200), "advisor": (advisor, 200),
        "balances": {}, "history": {}, "irrigation_history": history, "tanks": {},
        "owner_zone_need": {"status": "Available", "zone_id": "A12345",
            "observed_at": NOW.isoformat(), "source": "oom_sakkie_authenticated_operational_intake"},
        "managed_devices": {}}
    with mock.patch("modules.telemetry.rootline_bounded_read_group.run_bounded_read_group", return_value=loaded):
        evidence, selected, clock = read_current_water_energy_evidence(now=NOW)
    plan = build_water_energy_plan(evidence, selected, now=clock)
    task = next(row for row in plan["candidate_tasks"] if row["task_id"] == "irrigation_A12345")
    assert task["zone_decision"] == "Run now"
    assert task["requested_total_duration_minutes"] == 35
    assert task["max_execution_minutes"] == maximum and task["expected_segment_count"] == segments
    assert task["weekly_obligation"]["coverage_scope"] == "current_commissioning_epoch"
    with commissioned_a():
        eligible = build_execution_eligibility(plan=plan, evidence=evidence,
            controller=controller(), now=NOW, enabled_zone_ids={"A12345"})
        assert eligible["eligible"] is True, eligible
        assert eligible["channel"] == 4 and eligible["expected_segment_count"] == segments
        assert eligible["requested_total_duration_seconds"] == 2100
        assert eligible["maximum_duration_seconds"] == min(2100, maximum * 60, 3599)
        assert validate_execution_eligibility(eligible, now=NOW) == eligible


@pytest.mark.parametrize("case", ["shorter_segment", "smaller_total", "safe_remainder"])
def test_a_current_policy_limits_immutable_parent_without_rewriting_it(case):
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment
    job = build_irrigation_job(zone_id="A12345", operating_date=NOW.date().isoformat(),
        requested_total_seconds=5400, requested_total_minutes=90, maximum_segment_seconds=3599,
        expected_segment_count=2, plan_identity="SYNTHETIC-A-ORIGINAL-PARENT")
    events = []
    if case == "safe_remainder":
        first = project_next_segment(job, [])
        events = [{"job_id": job["job_id"], "segment_number": 1,
            "segment_identity": first["segment_identity"], "state": "Completed",
            "verified_runtime_seconds": 3599, "shutdown_verified": True}]
    projection = project_next_segment(job, events, rearm_readback_off=True)
    parent = {"job": job, "projection": projection}
    before = deepcopy(parent)
    policy = a_policy(requested_total_duration_minutes=60 if case == "smaller_total" else 90,
        maximum_continuous_runtime_minutes=60 if case == "smaller_total" else 45)
    data = fresh_adaptive_evidence()
    data["zones"] = [{"zone_id": "A12345", "operating_policy": policy,
        "visible_need": "dry", "visible_need_observed_at": NOW.isoformat(),
        "visible_need_source": "governed_sensor", "completion_ledger_complete_through": NOW.isoformat(),
        "incomplete_parent_job": parent}]
    row = next(row for row in build_adaptive_irrigation_decisions(data, now=NOW)["zones"]
        if row["zone_id"] == "A12345")
    if case == "safe_remainder":
        assert row["decision"] == "Run now"
        assert projection["segment_requested_seconds"] == 1801
    else:
        assert row["decision"] == "Hold"
        assert "current A policy" in row["reason"]
    assert parent == before and row["incomplete_parent_job"] == before


def test_a_eligibility_rechecks_current_segment_limit_on_a_stored_parent():
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job
    plan, evidence, readback = inputs(zone="A12345")
    job = build_irrigation_job(zone_id="A12345", operating_date=NOW.date().isoformat(),
        requested_total_seconds=7200, requested_total_minutes=120, maximum_segment_seconds=3599,
        expected_segment_count=2, plan_identity="SYNTHETIC-A-ORIGINAL-PARENT")
    plan["candidate_tasks"][0].update(max_execution_minutes=45, incomplete_parent_job={"job": job})
    with commissioned_a():
        result = build_execution_eligibility(plan=plan, evidence=evidence,
            controller=readback, now=NOW, enabled_zone_ids={"A12345"})
    assert result["eligible"] is False and result["status"] == "current_a_segment_limit_exceeded"


def a_brief_result(*, language="en", a_recommendation=None, a_receipt_zone=None):
    """Actual specialist projection; no A recommendation is supplied by default."""
    from modules.oom_sakkie import farm_manager_runtime
    from tests.test_oom_sakkie_farm_brief_concise import REASON
    raw = {"success": True, "result_id": "SYNTHETIC-A-BRIEF", "generated_at": NOW.isoformat(),
        "recommendations": [{"subject": zone, "status": "Recommend", "reason": REASON}
                            for zone in ("B12345", "C12345")],
        "irrigation_lifecycle": {zone: {"contract_version": "rootline_zone_lifecycle.v1",
            "zone_id": zone, "state": "Completed", "next_action_owner": "ROOTLINE",
            "completion_evidence": {"zone_id": zone, "shutdown_verified": True,
                "objective_satisfied": True,
                "shutdown_evidence": {"authoritative": True, "state": "OFF"}}}
            for zone in ("B12345", "C12345")}}
    if a_recommendation is not None:
        raw["recommendations"].append({"subject": "A12345", **a_recommendation})
    if a_receipt_zone is not None:
        raw["irrigation_lifecycle"]["A12345"] = deepcopy(raw["irrigation_lifecycle"]["B12345"])
        raw["irrigation_lifecycle"]["A12345"]["zone_id"] = "A12345"
        raw["irrigation_lifecycle"]["A12345"]["completion_evidence"]["zone_id"] = a_receipt_zone
    return farm_manager_runtime._project_rootline_snapshot({"raw": raw}, NOW, language)


def render_a_brief(result, language):
    from modules.oom_sakkie.farm_manager_loop import build_family_brief
    from modules.oom_sakkie.owner_response_composer import compose_manager_brief
    return compose_manager_brief(build_family_brief([result], now=NOW), language=language)


@pytest.mark.parametrize("language", ["en", "af"])
def test_a_default_brief_status_stays_visible_without_inheriting_bc_recommendation(language):
    result = a_brief_result(language=language)
    facts = result.work_items[0].metadata["brief_facts"]
    assert facts["zones"][2] == {"zone": "A12345", "status": "Not running",
        "reason": "", "recommendation": ""}
    original = deepcopy(facts)
    answer = render_a_brief(result, language)
    assert ("B &amp; C camps:</b> Controller OFF verified" if language == "en" else
            "B &amp; C kampe:</b> Beheerder AF geverifieer") in answer
    assert ("A camp:</b> Not running" if language == "en" else "A kamp:</b> Loop nie") in answer
    assert ("For B and C camps only." if language == "en" else "Slegs vir B en C kampe.") in answer
    assert "Next:" not in answer and "bronwoorde" not in answer
    assert "A camp:</b> Needs watering" not in answer and "A kamp:</b> Moet natgemaak word" not in answer
    assert result.work_items[0].metadata["brief_facts"] == original


@pytest.mark.parametrize("language", ["en", "af"])
def test_a_brief_foreign_off_receipt_never_joins_verified_bc_group(language):
    result = a_brief_result(language=language, a_receipt_zone="B12345")
    answer = render_a_brief(result, language)
    assert result.work_items[0].metadata["brief_facts"]["zones"][2]["status"] == "Not running"
    assert ("A camp:</b> Not running" if language == "en" else "A kamp:</b> Loop nie") in answer
    assert "B &amp; C &amp; A" not in answer
    assert ("For B and C camps only." if language == "en" else "Slegs vir B en C kampe.") in answer


@pytest.mark.parametrize("language", ["en", "af"])
@pytest.mark.parametrize("recommendation", ["Hold", "Recommend"])
def test_a_unknown_nonempty_reason_keeps_existing_source_fallback(language, recommendation):
    from modules.oom_sakkie.owner_response_composer import _irrigation_brief
    result = a_brief_result(language=language,
        a_recommendation={"status": recommendation, "reason": "A own water-supply evidence is unresolved."})
    facts = result.work_items[0].metadata["brief_facts"]
    assert facts["zones"][2]["reason"] == "A own water-supply evidence is unresolved."
    assert _irrigation_brief(facts, language == "af") == ""
    answer = render_a_brief(result, language)
    assert "Recommendation:" not in answer and "Aanbeveling:" not in answer
    assert ("Next:" if language == "en" else "bronwoorde") in answer


@pytest.mark.parametrize("language", ["en", "af"])
def test_a_old_support_reason_does_not_upgrade_its_current_hold(language):
    from tests.test_oom_sakkie_farm_brief_concise import REASON
    result = a_brief_result(language=language, a_recommendation={"status": "Hold", "reason": REASON})
    answer = render_a_brief(result, language)
    assert "Recommendation:" not in answer and "Aanbeveling:" not in answer
    assert result.work_items[0].metadata["brief_facts"]["zones"][2]["status"] == "Not running"


@pytest.mark.parametrize("language", ["en", "af"])
def test_a_joins_compact_advice_only_with_its_own_matching_recommendation(language):
    from tests.test_oom_sakkie_farm_brief_concise import REASON
    result = a_brief_result(language=language,
        a_recommendation={"status": "Recommend", "reason": REASON}, a_receipt_zone="A12345")
    answer = render_a_brief(result, language)
    assert ("B &amp; C &amp; A camps:</b> Controller OFF verified" if language == "en" else
            "B &amp; C &amp; A kampe:</b> Beheerder AF geverifieer") in answer
    assert ("For B and C and A camps only." if language == "en" else "Slegs vir B en C en A kampe.") in answer
    assert "watering completed" not in answer and "start irrigation" not in answer
