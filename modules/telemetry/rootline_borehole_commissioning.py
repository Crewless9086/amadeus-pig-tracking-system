"""Fail-closed Borehole 1 commissioning and execution-plan contracts.

Command-inert: this module never calls a provider, grants authority, or infers
that an energised relay pumped water.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
from modules.telemetry.rootline_device_registry import get_device_contract

VERSION = "rootline_borehole_commissioning_readiness.v2"
IDENTITY = "BOREHOLE-1-MINI-R4-CH1"
READBACK_MAX_AGE = timedelta(minutes=5)
COMMISSIONING_TEST_MAX_SECONDS = 30


def assess_borehole_commissioning_readiness(readback, *, canonical=None, physical=None, now=None):
    """Return an evidence-separated, non-actuating commissioning assessment."""
    now = _aware(now or datetime.now(timezone.utc))
    device = get_device_contract(IDENTITY)
    readback, canonical, physical = map(lambda value: dict(value or {}),
                                        (readback, canonical, physical))
    observed = _time(readback.get("retrieved_at") or readback.get("trusted_receipt_at"))
    channels = list(readback.get("channels") or ())
    exact = (readback.get("device_id") == device["device_id"]
             and readback.get("device_name") == device["device_name"]
             and str(readback.get("model") or "").upper().replace(" ", "") == "MINIR4"
             and channels == [{"channel": 1, "output_state": "OFF"}])
    current = observed is not None and not now < observed and now - observed <= READBACK_MAX_AGE
    fail_off = (readback.get("native_auto_off_enabled") is True
                and type(readback.get("native_auto_off_seconds")) is int
                and 1 <= readback["native_auto_off_seconds"] <= COMMISSIONING_TEST_MAX_SECONDS)
    conflicts = (readback.get("timers_enabled") is False
                 and readback.get("scenes_enabled") is False
                 and readback.get("interlock_enabled") is False
                 and readback.get("power_restoration_state") == "OFF")
    canonical_ok = _canonical_baseline_valid(canonical, device)
    physical_ok = _physical_baseline_valid(physical)
    blockers = []
    if not exact: blockers.append("exact_provider_device_channel_off_identity_unproven")
    if readback.get("online") is not True or not current: blockers.append("fresh_online_readback_unproven")
    if not fail_off: blockers.append("native_fail_off_not_configured_or_verified")
    if not conflicts: blockers.append("conflicting_paths_not_proven_disabled")
    if not canonical_ok: blockers.append("canonical_commissioned_baseline_absent")
    else: blockers.append("canonical_baseline_candidate_requires_registered_validator")
    if not physical_ok: blockers.append("supervised_physical_baseline_absent")
    fields = ("manual_isolation_location", "dry_run_protection_identity_and_test",
              "full_tank_cutoff_identity_and_test", "supply_pressure_or_flow_observation",
              "pump_current_or_motor_observation", "electrical_supply_identity",
              "maximum_routine_runtime_seconds")
    material = {"contract_version": VERSION, "identity": device["identity"],
        "provider": device["provider"], "provider_account_binding": device["provider_account_binding"],
        "device_id": device["device_id"], "device_name": device["device_name"],
        "model": device["model"], "channel": 1, "safe_state": "OFF",
        "maximum_test_seconds": COMMISSIONING_TEST_MAX_SECONDS,
        "native_fail_off_required": True, "all_other_channels_off_required": True,
        "no_on_retry": True, "safe_repeated_off": True,
        "provider_off_verification_required": True, "physical_final_off_required": True,
        "commissioning_fields": {key: physical.get(key) or "Unknown" for key in fields},
        "required_physical_sequence": ["initial_pump_off", "initial_water_flow_stopped",
            "one_bounded_start", "pump_started", "water_flow_observed", "native_auto_off_observed",
            "pump_stopped", "water_flow_stopped", "manual_off_and_isolation_proven"],
        "blockers": blockers, "commissioned": False,
        "authority_flag_enabled": False, "standing_authority": False}
    provider_ready = not any(item for item in blockers if item not in {
        "canonical_commissioned_baseline_absent", "supervised_physical_baseline_absent"})
    return {**material, "readiness_sha256": _digest(material),
        "status": "Hold",
        "eligible_for_protected_commissioning": provider_ready and not (canonical_ok or physical_ok),
        "eligible_for_routine_execution": False, "hardware_commands": 0,
        "provider_control_calls": 0, "writes_farm_data": False}


def prepare_borehole_execution_plan(*, need, commissioned_baseline, authority, provider,
                                    interlocks, energy, concurrency, requested_seconds,
                                    execution_id, now=None):
    """Prepare a digest-bound handoff for the existing coordinator; never execute."""
    now = _aware(now or datetime.now(timezone.utc))
    packets = {name: dict(value or {}) for name, value in {"need": need,
        "commissioned_baseline": commissioned_baseline, "authority": authority,
        "provider": provider, "interlocks": interlocks, "energy": energy,
        "concurrency": concurrency}.items()}
    maximum = packets["commissioned_baseline"].get("maximum_routine_runtime_seconds")
    seconds_ok = (type(requested_seconds) is int and requested_seconds > 0
                  and type(maximum) is int and requested_seconds <= maximum)
    gates = {"canonical_need": packets["need"].get("eligible") is True,
        "commissioned_baseline": packets["commissioned_baseline"].get("current") is True,
        "standing_authority": packets["authority"].get("inside_standing_authority") is True,
        "provider_off": packets["provider"].get("authoritative") is True and packets["provider"].get("state") == "OFF",
        "dry_run": packets["interlocks"].get("dry_run_safe") is True,
        "low_water": packets["interlocks"].get("low_water_clear") is True,
        "supply_pressure": packets["interlocks"].get("supply_pressure_safe") is True,
        "full_tank": packets["interlocks"].get("full_tank_not_blocking") is True,
        "energy": packets["energy"].get("eligible") is True,
        "concurrency": packets["concurrency"].get("no_conflicting_material_load") is True
            and packets["concurrency"].get("borehole_claim_available") is True,
        "bounded_runtime": seconds_ok}
    blockers = [name for name, passed in gates.items() if not passed]
    identity = str(execution_id or "").strip()
    if not identity: blockers.append("execution_identity")
    # These are proposed identities only. The existing canonical store must mint
    # and claim the final identity before a future coordinator may use it.
    material = {"contract_version": VERSION, "proposed_execution_id": identity,
        "device_identity": IDENTITY, "requested_seconds": requested_seconds,
        "prepared_at": now.isoformat(), "evidence_sha256": _digest(packets), "gates": gates,
        "command_identities": {"on": identity + ":ON", "primary_off": identity + ":OFF:1",
            "recovery_off_2": identity + ":OFF:2", "recovery_off_3": identity + ":OFF:3"},
        "on_retry_allowed": False, "maximum_off_attempts": 3,
        "provider_receipts_required": ["on_acceptance", "on_readback", "each_off_acceptance", "final_off_readback"],
        "canonical_receipts_required": ["claim_before_on", "command_attempts", "outcome", "follow_up_trigger"],
        "physical_receipts_required": ["pump_started", "water_flow_observed", "pump_stopped", "water_flow_stopped"],
        "recovery": {"on_ambiguous": "no_on_retry_then_bounded_off_and_contain",
            "restart": "load_active_claim_then_observe_or_bounded_off_never_new_on",
            "final_off_unproven": "repeat_safe_off_up_to_three_then_contain_and_manual_isolate",
            "follow_up": "reassess_on_canonical_evidence_change_or_stop_deadline"},
        "blockers": blockers + ["canonical_validator_and_coordinator_integration_absent"],
        "authority_consumed": False, "commands_issued": 0}
    return {**material, "plan_sha256": _digest(material),
        "status": "draft_hold_not_authorized_or_executed",
        "eligible_for_coordinator": False}


def _canonical_baseline_valid(value, device):
    return (value.get("current") is True and value.get("device_identity") == IDENTITY
        and value.get("device_id") == device["device_id"] and value.get("channel") == 1
        and type(value.get("commissioning_generation")) is int
        and value.get("commissioning_generation") > 0
        and len(str(value.get("baseline_sha256") or "")) == 64)


def _physical_baseline_valid(value):
    required = ("supervised", "pump_started", "water_flow_observed", "native_auto_off_observed",
                "pump_stopped", "water_flow_stopped", "manual_off_and_isolation_proven")
    return all(value.get(key) is True for key in required)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None: raise ValueError("aware_time_required")
    return value.astimezone(timezone.utc)


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError): return None
