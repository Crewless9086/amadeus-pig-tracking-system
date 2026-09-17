"""Pure ROOTLINE contract for commissioned B/C irrigation executions.

This module validates evidence and produces immutable lifecycle packets.  It
does not persist, notify, schedule, or call SONOFF/eWeLink/IFTTT hardware.
Those effects remain the responsibility of a separately reviewed adapter.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone


MAX_NATIVE_INCHING_MINUTES = 60
MAX_OFF_ATTEMPTS = 3
ZONE_BINDINGS = {
    "B12345": {"channel": 1, "name": "B Camp"},
    "C12345": {"channel": 2, "name": "C Camp"},
}
CONTROLLER = {
    "platform": "eWeLink",
    "model": "SONOFF 4CH Pro R3",
    "firmware": "3.8.2",
    "device": "IRRIGATION (1) - Left",
}
LIFECYCLE = {
    "Planned": frozenset({"Active", "Failed"}),
    "Active": frozenset({"Stopped", "Failed"}),
    "Stopped": frozenset({"Completed", "Failed"}),
    "Completed": frozenset(),
    "Failed": frozenset(),
}
AUTHORITY = {
    "command_authority": False,
    "hardware_control": False,
    "schedule_authority": False,
    "workflow_authority": False,
    "automatic_on_retry": False,
}


class ContractError(ValueError):
    """The supplied evidence cannot support the requested execution."""


def commissioning_checklist(zone_id: str) -> dict:
    binding = _binding(zone_id)
    return {
        "version": "rootline_sonoff_4ch_commissioning_v1",
        "controller": dict(CONTROLLER),
        "zone_id": zone_id,
        "channel": binding["channel"],
        "required_configuration": {
            "native_inching_enabled": True,
            "native_inching_minutes": MAX_NATIVE_INCHING_MINUTES,
            "power_restoration_state": "OFF",
            "conflicting_schedules": [],
            "conflicting_scenes": [],
            "conflicting_ifttt_automations": [],
        },
        "supervised_proof": {
            "required": True,
            "duration_must_be_less_than_minutes": MAX_NATIVE_INCHING_MINUTES,
            "physical_start_required": True,
            "native_auto_off_required": True,
            "oom_sakkie_off_command_count": 0,
            "physical_stop_required": True,
            "other_channel_actuation_count": 0,
            "offline_timeout_proven": True,
            "power_cycle_off_no_restart_proven": True,
            "production_setting_reverified_after_proof": True,
        },
        **AUTHORITY,
    }


def validate_commissioning(zone_id: str, evidence: dict, *, now=None) -> dict:
    binding = _binding(zone_id)
    evidence = _object(evidence, "commissioning_evidence_required")
    now = _utc(now or datetime.now(timezone.utc))
    expected = {**CONTROLLER, "zone_id": zone_id, "channel": binding["channel"]}
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise ContractError(f"commissioning_{key}_mismatch")
    observed_at = _timestamp(evidence.get("observed_at"), "commissioning_time_required")
    if observed_at > now:
        raise ContractError("commissioning_evidence_from_future")
    if evidence.get("power_restoration_state") != "OFF":
        raise ContractError("power_restoration_off_not_proven")
    if evidence.get("native_inching_enabled") is not True:
        raise ContractError("native_inching_not_enabled")
    if evidence.get("native_inching_minutes") != MAX_NATIVE_INCHING_MINUTES:
        raise ContractError("native_inching_limit_not_commissioned")
    if evidence.get("revoked") is not False:
        raise ContractError("commissioning_revoked_or_unknown")
    if not isinstance(evidence.get("configuration_generation"), int) or evidence["configuration_generation"] < 1:
        raise ContractError("configuration_generation_required")
    for field in ("conflicting_schedules", "conflicting_scenes", "conflicting_ifttt_automations"):
        if evidence.get(field) != []:
            raise ContractError(f"{field}_present_or_unverified")
    proof = _object(evidence.get("supervised_proof"), "supervised_proof_required")
    proof_minutes = _positive_number(proof.get("duration_minutes"), "proof_duration_required")
    if proof_minutes >= MAX_NATIVE_INCHING_MINUTES:
        raise ContractError("proof_must_be_sub_60_minutes")
    required_true = (
        "physical_start_confirmed", "native_auto_off_observed",
        "physical_stop_confirmed", "production_setting_reverified_after_proof",
        "offline_timeout_proven", "power_cycle_off_no_restart_proven",
    )
    if any(proof.get(field) is not True for field in required_true):
        raise ContractError("supervised_native_auto_off_proof_incomplete")
    if proof.get("oom_sakkie_off_command_count") != 0:
        raise ContractError("native_auto_off_independence_not_proven")
    if proof.get("other_channel_actuation_count") != 0:
        raise ContractError("cross_channel_actuation_detected")
    normalized = {key: evidence[key] for key in (
        "platform", "model", "firmware", "device", "zone_id", "channel",
        "power_restoration_state", "native_inching_enabled", "native_inching_minutes",
        "configuration_generation", "revoked", "conflicting_schedules",
        "conflicting_scenes", "conflicting_ifttt_automations", "supervised_proof",
    )}
    normalized["observed_at"] = observed_at.isoformat()
    identity = _digest(normalized)
    return {
        "commissioning_id": "ROOTLINE-COMMISSION-" + identity[:24].upper(),
        "commissioning_sha256": identity,
        "zone_id": zone_id,
        "channel": binding["channel"],
        "observed_at": observed_at.isoformat(),
        "native_fail_stop_minutes": MAX_NATIVE_INCHING_MINUTES,
        "configuration_generation": evidence["configuration_generation"],
        "commissioned": True,
        **AUTHORITY,
    }


def prepare_execution_segment(payload: dict, *, commissioning_id: str, eligibility_id: str,
                              commissioning_reader, eligibility_reader, now=None,
                              prior_segment=None, execution_reader=None) -> dict:
    """Create one independently eligible segment, never an ON instruction."""
    payload = _object(payload, "execution_payload_required")
    now = _utc(now or datetime.now(timezone.utc))
    zone_id = str(payload.get("zone_id") or "")
    binding = _binding(zone_id)
    raw_commissioning = commissioning_reader(commissioning_id)
    commissioning = validate_commissioning(zone_id, raw_commissioning, now=now)
    if commissioning.get("commissioning_id") != commissioning_id:
        raise ContractError("commissioning_identity_mismatch")
    duration = _positive_number(payload.get("duration_minutes"), "duration_required")
    if duration > commissioning.get("native_fail_stop_minutes", 0) or duration > MAX_NATIVE_INCHING_MINUTES:
        raise ContractError("segment_exceeds_native_fail_stop")
    eligibility = _object(eligibility_reader(eligibility_id), "canonical_eligibility_required")
    if eligibility.get("eligibility_id") != eligibility_id:
        raise ContractError("eligibility_identity_mismatch")
    assessed_at = _timestamp(eligibility.get("assessed_at"), "fresh_eligibility_required")
    if assessed_at > now or now - assessed_at > timedelta(minutes=15):
        raise ContractError("eligibility_stale")
    if eligibility.get("eligible") is not True or eligibility.get("zone_id") != zone_id:
        raise ContractError("zone_not_currently_eligible")
    if eligibility.get("conflicts") != [] or eligibility.get("concurrency_clear") is not True:
        raise ContractError("eligibility_conflict")
    segment_number = int(payload.get("segment_number") or 0)
    if segment_number not in (1, 2):
        raise ContractError("segment_number_must_be_1_or_2")
    if segment_number == 2:
        if not isinstance(prior_segment, dict) or not callable(execution_reader):
            raise ContractError("canonical_predecessor_reader_required")
        canonical_prior = execution_reader(prior_segment.get("execution_id"))
        if canonical_prior != prior_segment:
            raise ContractError("predecessor_canonical_record_mismatch")
        _validate_execution(canonical_prior)
        _validate_second_segment(
            canonical_prior, zone_id, assessed_at, eligibility_id,
            eligibility.get("evidence_generation"),
        )
    elif prior_segment is not None:
        raise ContractError("first_segment_must_not_have_predecessor")
    plan_id = str(payload.get("plan_id") or "").strip()
    plan_generation = int(payload.get("plan_generation") or 0)
    if not plan_id or plan_generation < 1:
        raise ContractError("exact_plan_identity_required")
    exact = {
        "plan_id": plan_id, "plan_generation": plan_generation,
        "commissioning_id": commissioning_id,
    }
    if any(eligibility.get(key) != value for key, value in exact.items()):
        raise ContractError("eligibility_plan_or_commissioning_mismatch")
    for field in ("evidence_generation", "power_evidence_id", "local_weather_evidence_id",
                  "forecast_evidence_id", "water_evidence_status", "governing_reserve_pct"):
        if eligibility.get(field) in (None, ""):
            raise ContractError(f"eligibility_{field}_required")
    supplied_digest = eligibility.get("evidence_sha256")
    canonical_eligibility = {key: value for key, value in eligibility.items() if key != "evidence_sha256"}
    if supplied_digest != _digest(canonical_eligibility):
        raise ContractError("eligibility_evidence_digest_mismatch")
    raw_identity = {
        "plan_id": plan_id, "plan_generation": plan_generation, "zone_id": zone_id,
        "channel": binding["channel"], "segment_number": segment_number,
        "commissioning_id": commissioning_id,
        "eligibility_id": eligibility_id, "eligibility_generation": eligibility["evidence_generation"],
        "duration_minutes": duration,
    }
    digest = _digest(raw_identity)
    return {
        "contract_version": "rootline_irrigation_execution_v1",
        "execution_id": "ROOTLINE-IRRIGATION-" + digest[:24].upper(),
        "execution_sha256": digest,
        **raw_identity,
        "state": "Planned",
        "planned_at": now.isoformat(),
        "native_auto_off_deadline": None,
        "persist_before_on": True,
        "daily_card_id": f"ROOTLINE-CARD-{plan_id}-{zone_id}",
        "visible_telegram_lifecycle": ["Planned", "Active", "Stopped", "Completed", "Failed"],
        "on_policy": {"state_setting": True, "max_attempts": 1, "ambiguous_retry": False},
        "off_policy": {
            "state_setting": True, "physically_idempotent": True,
            "max_attempts": MAX_OFF_ATTEMPTS, "repeat_only_until_shutdown_verified": True,
        },
        "second_segment_requires_fresh_decision": True,
        **AUTHORITY,
    }


def transition_lifecycle(execution: dict, next_state: str, evidence_id: str, evidence_reader) -> dict:
    _validate_execution(execution)
    current = execution.get("state")
    history = list(execution.get("lifecycle_history") or [])
    evidence = _object(evidence_reader(evidence_id), "canonical_transition_evidence_required")
    if evidence.get("evidence_id") != evidence_id or evidence.get("execution_id") != execution.get("execution_id"):
        raise ContractError("transition_evidence_identity_mismatch")
    if evidence.get("state") != next_state or not evidence.get("provenance"):
        raise ContractError("transition_evidence_type_or_provenance_invalid")
    observed_at = _timestamp(evidence.get("observed_at"), "transition_evidence_time_required")
    supplied_digest = evidence.get("evidence_sha256")
    if supplied_digest != _digest({key: value for key, value in evidence.items() if key != "evidence_sha256"}):
        raise ContractError("transition_evidence_digest_mismatch")
    if current == next_state and history and history[-1] == evidence:
        return dict(execution)
    if history and observed_at <= _timestamp(history[-1]["observed_at"], "history_time_invalid"):
        raise ContractError("transition_chronology_conflict")
    if next_state not in LIFECYCLE.get(current, frozenset()):
        raise ContractError("invalid_lifecycle_transition")
    if next_state == "Active" and evidence.get("on_outcome") != "accepted_unambiguous":
        raise ContractError("unambiguous_on_acceptance_required")
    if next_state == "Active" and evidence.get("native_timer_armed_readback") is not True:
        raise ContractError("native_timer_start_binding_required")
    if next_state == "Active" and evidence.get("native_timer_minutes") != MAX_NATIVE_INCHING_MINUTES:
        raise ContractError("native_timer_readback_mismatch")
    if next_state in {"Stopped", "Completed"} and evidence.get("shutdown_verified") is not True:
        raise ContractError("verified_shutdown_required")
    if next_state == "Completed":
        if execution.get("duration_minutes") == MAX_NATIVE_INCHING_MINUTES:
            if evidence.get("native_auto_off_observed") is not True:
                raise ContractError("native_auto_off_outcome_required")
        elif evidence.get("primary_off_accepted_unambiguous") is not True:
            raise ContractError("short_segment_primary_off_outcome_required")
    history.append(dict(evidence))
    result = {**execution, "state": next_state, "state_evidence": dict(evidence),
              "lifecycle_history": history}
    if next_state == "Active":
        result["native_auto_off_deadline"] = (
            observed_at + timedelta(minutes=evidence["native_timer_minutes"])
        ).isoformat()
    return result


def _validate_second_segment(prior, zone_id, assessed_at, eligibility_id, eligibility_generation):
    if not isinstance(prior, dict) or prior.get("state") != "Completed":
        raise ContractError("first_segment_completion_required")
    if prior.get("zone_id") != zone_id or prior.get("segment_number") != 1:
        raise ContractError("segment_predecessor_mismatch")
    evidence = prior.get("state_evidence") or {}
    if evidence.get("native_auto_off_observed") is not True or evidence.get("shutdown_verified") is not True:
        raise ContractError("first_segment_native_shutdown_unverified")
    stopped_at = _timestamp(evidence.get("observed_at"), "first_segment_stop_time_required")
    if assessed_at <= stopped_at:
        raise ContractError("second_segment_requires_fresh_reassessment")
    if prior.get("eligibility_id") == eligibility_id:
        raise ContractError("second_segment_requires_new_eligibility_identity")
    if prior.get("eligibility_generation") == eligibility_generation:
        raise ContractError("second_segment_requires_new_evidence_generation")


def _validate_execution(execution):
    execution = _object(execution, "canonical_execution_required")
    identity_fields = (
        "plan_id", "plan_generation", "zone_id", "channel", "segment_number",
        "commissioning_id", "eligibility_id", "eligibility_generation", "duration_minutes",
    )
    identity = {field: execution.get(field) for field in identity_fields}
    if execution.get("execution_sha256") != _digest(identity):
        raise ContractError("execution_identity_digest_mismatch")
    expected_id = "ROOTLINE-IRRIGATION-" + execution["execution_sha256"][:24].upper()
    if execution.get("execution_id") != expected_id:
        raise ContractError("execution_identity_mismatch")
    history = execution.get("lifecycle_history") or []
    previous = None
    for item in history:
        if item.get("execution_id") != expected_id:
            raise ContractError("lifecycle_history_execution_mismatch")
        if item.get("evidence_sha256") != _digest(
            {key: value for key, value in item.items() if key != "evidence_sha256"}
        ):
            raise ContractError("lifecycle_history_digest_mismatch")
        observed = _timestamp(item.get("observed_at"), "lifecycle_history_time_invalid")
        if previous is not None and observed <= previous:
            raise ContractError("lifecycle_history_chronology_conflict")
        previous = observed
    expected_state = history[-1]["state"] if history else "Planned"
    if execution.get("state") != expected_state:
        raise ContractError("execution_state_history_mismatch")
    if history and execution.get("state_evidence") != history[-1]:
        raise ContractError("execution_state_evidence_mismatch")


def _binding(zone_id):
    try:
        return ZONE_BINDINGS[zone_id]
    except KeyError as exc:
        raise ContractError("only_proven_B_or_C_zone_supported") from exc


def _object(value, error):
    if not isinstance(value, dict):
        raise ContractError(error)
    return value


def _positive_number(value, error):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ContractError(error)
    return value


def _timestamp(value, error):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ContractError(error) from exc
    if parsed.tzinfo is None:
        raise ContractError(error)
    return _utc(parsed)


def _utc(value):
    return value.astimezone(timezone.utc)


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
