"""Fail-closed business outcome gate for the canonical CORE mission lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Mapping


CONTRACT_VERSION = "core_mission_outcome_handover_v1"
LIFECYCLE_VERSION = "core_mission_lifecycle_v1"
OPEN_LIFECYCLES = {"WORKING", "REVIEW_HOLD", "RELEASE_HOLD", "EXTERNAL_HOLD", "PROTECTED_BOUNDARY"}
TECHNICAL_MILESTONES = {"source_ready", "tests_passed", "pr_open", "merged", "deployed", "health_passed"}
AMBIGUOUS_DISPOSITIONS = {"complete", "completed", "done"}
EVIDENCE_ROWS = (
    "operational_actor", "genuine_trigger", "loaded_revision", "canonical_readback",
    "provider_result", "physical_or_customer_result", "later_independent_cycle",
    "owner_work_removal",
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def evaluate_outcome_handover(handover, *, mission_id="", prior=None):
    """Validate one handover and project lifecycle without trusting prose."""
    item = dict(handover) if isinstance(handover, Mapping) else {}
    prior = dict(prior) if isinstance(prior, Mapping) else {}
    errors = []
    if item.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version")
    if not str(item.get("handover_id") or "").strip():
        errors.append("handover_id")
    if not str(item.get("mission_id") or "").strip():
        errors.append("mission_id")
    if str(item.get("mission_id") or "") != str(mission_id or item.get("mission_id") or ""):
        errors.append("mission_identity")
    origin = str(item.get("reporting_actor_type") or "").strip().lower()
    if origin not in {"terminal", "control_tower", "deployed_agent", "external_verifier"}:
        errors.append("reporting_actor_type")
    disposition = str(item.get("terminal_disposition") or "").strip().lower()
    if not disposition or disposition in AMBIGUOUS_DISPOSITIONS:
        errors.append("terminal_disposition_stage_qualifier")
    requested = str(item.get("requested_lifecycle") or "WORKING").strip().upper()
    if requested not in OPEN_LIFECYCLES | {"BUSINESS_COMPLETE"}:
        errors.append("requested_lifecycle")
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    applicability = item.get("applicability") if isinstance(item.get("applicability"), Mapping) else {}
    missing, invalid_na = [], []
    for row in EVIDENCE_ROWS:
        state = applicability.get(row, "required")
        if state == "required":
            if not _evidence_present(evidence.get(row)):
                missing.append(row)
        elif isinstance(state, Mapping) and state.get("state") == "not_applicable":
            if not _bounded_na(state):
                invalid_na.append(row)
        else:
            invalid_na.append(row)
    if requested == "BUSINESS_COMPLETE":
        if origin == "terminal":
            errors.append("terminal_cannot_set_business_complete")
        errors.extend(_business_evidence_errors(evidence))
        errors.extend(f"missing:{row}" for row in missing)
        errors.extend(f"invalid_not_applicable:{row}" for row in invalid_na)
    hold = item.get("hold") if isinstance(item.get("hold"), Mapping) else {}
    if requested in {"EXTERNAL_HOLD", "PROTECTED_BOUNDARY"} and not _valid_hold(hold, requested):
        errors.append("hold_contract")
    technical = sorted({str(value).strip().lower() for value in item.get("technical_milestones", []) if str(value).strip().lower() in TECHNICAL_MILESTONES})
    valid = not errors
    lifecycle = requested if valid else str(prior.get("lifecycle_state") or "WORKING").upper()
    if lifecycle == "BUSINESS_COMPLETE" and (missing or invalid_na):
        lifecycle = "WORKING"
    remaining = [] if lifecycle == "BUSINESS_COMPLETE" else sorted(set(missing + invalid_na))
    next_stage = "closed" if lifecycle == "BUSINESS_COMPLETE" else _next_stage(item, remaining, lifecycle)
    digest = _digest(item) if item else ""
    return {
        "version": LIFECYCLE_VERSION,
        "contract_version": item.get("contract_version", ""),
        "handover_id": str(item.get("handover_id") or ""),
        "handover_digest": digest,
        "mission_id": str(mission_id or item.get("mission_id") or ""),
        "handover_status": "VALID_HANDOVER" if valid else "INVALID_HANDOVER",
        "lifecycle_state": lifecycle,
        "technical_stage": disposition or "unqualified",
        "technical_milestones": technical,
        "remaining_acceptance_rows": remaining,
        "next_safe_stage": next_stage,
        "hold": hold if lifecycle in {"EXTERNAL_HOLD", "PROTECTED_BOUNDARY"} else {},
        "errors": sorted(set(errors)),
        "business_complete": lifecycle == "BUSINESS_COMPLETE",
        "terminal_can_close_business": False,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def mission_lifecycle_projection(mission):
    item = mission if isinstance(mission, Mapping) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    lifecycle = metadata.get("mission_lifecycle") if isinstance(metadata.get("mission_lifecycle"), Mapping) else {}
    if lifecycle:
        return dict(lifecycle)
    return {
        "version": LIFECYCLE_VERSION,
        "lifecycle_state": "WORKING",
        "business_complete": False,
        "handover_status": "NO_HANDOVER",
        "technical_stage": str(item.get("status") or "unknown"),
        "technical_milestones": [],
        "remaining_acceptance_rows": list(EVIDENCE_ROWS),
        "next_safe_stage": "collect_operational_evidence",
        "terminal_can_close_business": False,
    }


def _business_evidence_errors(evidence):
    errors = []
    actor = evidence.get("operational_actor") if isinstance(evidence.get("operational_actor"), Mapping) else {}
    trigger = evidence.get("genuine_trigger") if isinstance(evidence.get("genuine_trigger"), Mapping) else {}
    revision = evidence.get("loaded_revision") if isinstance(evidence.get("loaded_revision"), Mapping) else {}
    later = evidence.get("later_independent_cycle") if isinstance(evidence.get("later_independent_cycle"), Mapping) else {}
    delta = evidence.get("owner_work_removal") if isinstance(evidence.get("owner_work_removal"), Mapping) else {}
    if not actor.get("runtime_identity") or actor.get("is_terminal") is not False:
        errors.append("operational_actor_not_deployed")
    if trigger.get("created_by_terminal") is not False or not trigger.get("provider_identity"):
        errors.append("genuine_trigger_not_proven")
    if not SHA40.fullmatch(str(revision.get("sha") or "").lower()) or revision.get("exact_match") is not True:
        errors.append("loaded_revision_not_exact")
    if later.get("terminal_independent") is not True or not later.get("correlation_id"):
        errors.append("later_independent_cycle_not_proven")
    before, after = delta.get("before_manual_steps"), delta.get("after_manual_steps")
    if not isinstance(before, int) or not isinstance(after, int) or before <= after or not delta.get("measurement_id"):
        errors.append("owner_work_removal_not_measured")
    return errors


def _evidence_present(value):
    if not isinstance(value, Mapping) or not value.get("evidence_id") or not value.get("observed_at"):
        return False
    try:
        observed = datetime.fromisoformat(str(value["observed_at"]).replace("Z", "+00:00"))
        return observed.tzinfo is not None
    except (TypeError, ValueError):
        return False


def _bounded_na(value):
    return all(str(value.get(key) or "").strip() for key in ("reason_code", "reason", "authority", "audit_ref"))


def _valid_hold(hold, lifecycle):
    return (hold.get("type") == lifecycle and all(str(hold.get(key) or "").strip()
            for key in ("owner", "reason", "wake_condition", "automatic_continuation_trigger")))


def _next_stage(item, remaining, lifecycle):
    if lifecycle in {"EXTERNAL_HOLD", "PROTECTED_BOUNDARY"}:
        return "automatic_continuation_on_hold_wake"
    proposed = str(item.get("next_safe_stage") or "").strip()
    return proposed or (f"collect:{remaining[0]}" if remaining else "control_tower_outcome_review")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
