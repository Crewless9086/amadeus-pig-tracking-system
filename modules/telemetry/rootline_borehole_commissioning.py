"""Fail-closed Borehole 1 commissioning and execution-plan contracts.

Command-inert: this module never calls a provider, grants authority, or infers
that an energised relay pumped water.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
from modules.telemetry.rootline_device_registry import get_device_contract
from modules.telemetry.rootline_device_spine import load_device_record

VERSION = "rootline_borehole_commissioning_readiness.v2"
IDENTITY = "BOREHOLE-1-MINI-R4-CH1"
READBACK_MAX_AGE = timedelta(minutes=5)
COMMISSIONING_TEST_MAX_SECONDS = 4 * 60 * 60
DEVICE_KEY = "ewelink:ewelink_owner_account:1002851416:1"


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
    blockers = []
    if not exact: blockers.append("exact_provider_device_channel_off_identity_unproven")
    if readback.get("online") is not True or not current: blockers.append("fresh_online_readback_unproven")
    if not fail_off: blockers.append("native_fail_off_not_configured_or_verified")
    if not conflicts: blockers.append("conflicting_paths_not_proven_disabled")
    if not canonical_ok: blockers.append("canonical_commissioned_baseline_absent")
    else: blockers.append("canonical_baseline_candidate_requires_registered_validator")
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
        "provider_off_verification_required": True, "physical_final_off_required": False,
        "provider_on_then_off_is_operational_proof": True,
        "commissioning_fields": {key: physical.get(key) or "Unknown" for key in fields},
        "required_provider_sequence": ["initial_off", "one_bounded_start", "authoritative_on",
            "native_or_primary_deadline", "state_setting_off", "authoritative_final_off"],
        "blockers": blockers, "commissioned": False,
        "authority_flag_enabled": False, "standing_authority": False}
    provider_ready = not any(item for item in blockers if item not in {
        "canonical_commissioned_baseline_absent"})
    return {**material, "readiness_sha256": _digest(material),
        "status": "Hold",
        "eligible_for_protected_commissioning": provider_ready and not canonical_ok,
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
        "physical_receipts_required": [],
        "operational_proof": "authoritative_provider_on_then_off",
        "recovery": {"on_ambiguous": "no_on_retry_then_bounded_off_and_contain",
            "restart": "load_active_claim_then_observe_or_bounded_off_never_new_on",
            "final_off_unproven": "repeat_safe_off_up_to_three_then_contain_and_manual_isolate",
            "follow_up": "reassess_on_canonical_evidence_change_or_stop_deadline"},
        "blockers": blockers + ["canonical_validator_and_coordinator_integration_absent"],
        "authority_consumed": False, "commands_issued": 0}
    return {**material, "plan_sha256": _digest(material),
        "status": "draft_hold_not_authorized_or_executed",
        "eligible_for_coordinator": False}


def load_registered_borehole_baseline(*, connect_factory):
    """Load the canonical device spine and accept only a commissioned pump baseline.

    `load_device_record` already resolves every referenced commissioning-evidence
    row and standing-authority envelope.  This additional profile check prevents
    a valid record for a different output, provider, or physical effect from
    becoming Borehole 1 authority.
    """
    loaded = load_device_record(DEVICE_KEY, connect_factory=connect_factory)
    if not isinstance(loaded, dict):
        return None
    record = loaded.get("device_record") or {}
    exact = (record.get("provider") == "ewelink"
        and record.get("provider_account_binding") == "ewelink_owner_account"
        and record.get("device_id") == "1002851416" and record.get("channel") == 1
        and record.get("device_type") == "pump" and record.get("safe_state") == "OFF"
        and record.get("physical_effect") == "Borehole 1 pump power"
        and record.get("commissioning_stage") == "standing_active"
        and record.get("standing_authority") is True
        and record.get("independent_physical_identity_proven") is True
        and record.get("independent_fail_stop_proven") is True
        and type(record.get("maximum_runtime_seconds")) is int
        and 0 < record["maximum_runtime_seconds"]
        and type(record.get("native_fail_stop_seconds")) is int
        and 0 < record["native_fail_stop_seconds"] <= record["maximum_runtime_seconds"])
    if not exact:
        return None
    return {"current": True, "device_identity": IDENTITY, "device_key": DEVICE_KEY,
        "provider": record["provider"], "provider_account_binding": record["provider_account_binding"],
        "device_id": record["device_id"], "channel": record["channel"],
        "safe_state": record["safe_state"], "registry_generation": loaded["registry_generation"],
        "baseline_sha256": loaded["evidence_digest"],
        "maximum_routine_runtime_seconds": record["maximum_runtime_seconds"],
        "native_fail_stop_seconds": record["native_fail_stop_seconds"],
        "authority_envelope": dict(record.get("authority_envelope") or {})}


def build_borehole_runtime_eligibility(*, need, baseline, authority, provider,
                                      interlocks, energy, requested_seconds, now=None):
    """Build one immutable canonical eligibility identity; never claim or command."""
    plan = prepare_borehole_execution_plan(need=need, commissioned_baseline=baseline,
        authority=authority, provider=provider, interlocks=interlocks, energy=energy,
        concurrency={"no_conflicting_material_load": True, "borehole_claim_available": True},
        requested_seconds=requested_seconds, execution_id="PENDING", now=now)
    blockers = [item for item in plan["blockers"]
        if item != "canonical_validator_and_coordinator_integration_absent"]
    material = {"contract_version": "rootline_borehole_runtime_eligibility.v1",
        "device_key": DEVICE_KEY, "baseline_sha256": baseline.get("baseline_sha256"),
        "registry_generation": baseline.get("registry_generation"),
        "need_sha256": _digest(dict(need or {})), "evidence_sha256": plan["evidence_sha256"],
        "requested_seconds": requested_seconds, "assessed_at": plan["prepared_at"],
        "gates": plan["gates"], "blockers": blockers}
    digest = _digest(material)
    execution_id = "ROOTLINE-BOREHOLE-" + digest[:24].upper()
    return {**material, "eligibility_sha256": digest, "execution_id": execution_id,
        "consumption_key": "borehole:" + digest,
        "eligible": not blockers and all(plan["gates"].values()),
        "command_authority": False, "hardware_commands": 0}


def advance_borehole_execution(*, eligibility, store, transport, now=None):
    """Advance one exact Borehole execution with one ON and bounded OFF recovery."""
    from modules.telemetry.rootline_irrigation_execution_store import _valid_borehole_eligibility
    now = _aware(now or datetime.now(timezone.utc))
    active = store("load_active_borehole", None)
    if isinstance(active, dict):
        deadline = _time(active.get("primary_stop_deadline"))
        if active.get("state") == "Active" and deadline is not None and now < deadline:
            return _borehole_result("borehole_active", execution=active)
        return _finish_borehole(active, store, transport, now)
    if not _valid_borehole_eligibility(eligibility):
        return _borehole_result("borehole_eligibility_invalid", success=False)
    execution = {**eligibility, "state": "claimed", "claimed_at": now.isoformat(),
        "primary_stop_deadline": (now + timedelta(seconds=eligibility["requested_seconds"])).isoformat(),
        "native_fail_stop_deadline": (now + timedelta(seconds=14400)).isoformat(),
        "on_attempts": 0, "off_attempts": 0}
    claim = store("claim_borehole_before_on", execution)
    if not isinstance(claim, dict) or claim.get("created") is not True:
        return _borehole_result("borehole_claim_conflict")
    on = transport.set_state(device_id="1002851416", channel=1, state="ON",
        idempotency_key=execution["execution_id"] + ":ON")
    store("record_borehole_on_outcome", {**execution, "on_attempts": 1, "on_outcome": on})
    if on.get("accepted_unambiguous") is not True:
        return _contain_failed_borehole_start(
            {**execution, "reason": "ambiguous_on"}, store, transport)
    started = _read_borehole(transport)
    if started.get("authoritative") is not True or started.get("state") != "ON":
        return _contain_failed_borehole_start(
            {**execution, "reason": "start_unverified"}, store, transport)
    active = {**execution, "state": "Active", "on_attempts": 1,
        "provider_start_evidence": started}
    store("mark_borehole_active", active)
    return _borehole_result("borehole_started", commands=1, execution=active)


def _finish_borehole(active, store, transport, now):
    commands = 0
    prior = store("load_borehole_off_attempts", active["execution_id"]) or []
    used = {int(row.get("attempt") or 0) for row in prior if isinstance(row, dict)}
    for attempt in range(1, 4):
        if attempt in used:
            continue
        claim = store("claim_borehole_off_attempt", {"execution_id": active["execution_id"],
            "attempt": attempt})
        if not isinstance(claim, dict) or claim.get("created") is not True:
            continue
        outcome = transport.set_state(device_id="1002851416", channel=1, state="OFF",
            idempotency_key=f"{active['execution_id']}:OFF:{attempt}")
        commands += 1
        store("record_borehole_off_outcome", {"execution_id": active["execution_id"],
            "attempt": attempt, "outcome": outcome})
        if outcome.get("accepted_unambiguous") is True:
            break
    final = _read_borehole(transport)
    if final.get("authoritative") is not True or final.get("state") != "OFF":
        store("contain_borehole", {**active, "shutdown_verified": False,
            "provider_final_off_evidence": final})
        return _borehole_result("borehole_shutdown_unverified", commands=commands,
            success=False, execution=active)
    canonical = {"execution_id": active["execution_id"], "final_state": "OFF",
        "evidence_id": "CANONICAL-" + _digest({"execution": active["execution_id"],
            "final": final})[:24].upper()}
    provider = {**final, "execution_id": active["execution_id"],
        "evidence_id": str(final.get("evidence_id") or final.get("response_digest") or "")}
    completed = {**active, "action": "record_borehole_completed", "state": "Completed",
        "completed_at": now.isoformat(), "shutdown_verified": True,
        "operational_proof": "provider_app_on_to_off",
        "canonical_completion_evidence": canonical,
        "provider_final_off_evidence": provider}
    recorded = store("record_borehole_completed", completed)
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return _borehole_result("borehole_completion_persistence_unproven",
            commands=commands, success=False, execution=completed)
    return _borehole_result("borehole_completed", commands=commands, execution=completed)


def _contain_failed_borehole_start(execution, store, transport):
    """A failed ON edge may drive OFF but can never create completion truth."""
    commands = 0
    prior = store("load_borehole_off_attempts", execution["execution_id"]) or []
    used = {int(row.get("attempt") or 0) for row in prior if isinstance(row, dict)}
    for attempt in range(1, 4):
        if attempt in used:
            continue
        claim = store("claim_borehole_off_attempt", {"execution_id": execution["execution_id"],
            "attempt": attempt})
        if not isinstance(claim, dict) or claim.get("created") is not True:
            continue
        outcome = transport.set_state(device_id="1002851416", channel=1, state="OFF",
            idempotency_key=f"{execution['execution_id']}:OFF:{attempt}")
        commands += 1
        store("record_borehole_off_outcome", {"execution_id": execution["execution_id"],
            "attempt": attempt, "outcome": outcome})
        if outcome.get("accepted_unambiguous") is True:
            break
    final = _read_borehole(transport)
    verified = final.get("authoritative") is True and final.get("state") == "OFF"
    contained = {**execution, "shutdown_verified": verified,
        "provider_final_off_evidence": final}
    store("contain_borehole", contained)
    return _borehole_result("borehole_start_failure_contained" if verified
        else "borehole_shutdown_unverified", commands=commands, success=False,
        execution=contained)


def _read_borehole(transport):
    try:
        return transport.read_output_state(device_id="1002851416", channel=1)
    except Exception:
        return {"authoritative": False, "state": "Unknown"}


def _borehole_result(status, *, commands=0, success=True, **extra):
    return {"success": success, "status": status, "hardware_commands": commands,
        "automatic_on_retry": False, "maximum_off_attempts": 3,
        "physical_presence_required": False, "preview_confirmation_required": False,
        **extra}


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
