"""Authenticated, zero-I/O HERDMASTER management-round consumption.

The adapter invokes HERDMASTER's pure specialist contract and translates the
result into Oom Sakkie's existing typed manager evidence.  It deliberately
does not persist, route, notify, or perform a farm/protected action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Mapping, Sequence

from modules.oom_sakkie.farm_manager_loop import (
    Authority,
    Provenance,
    SpecialistAvailability,
    SpecialistResult,
    SpecialistWorkItem,
    WorkState,
)
from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.pig_weights.herdmaster_management_round import (
    CONTRACT_VERSION as HERDMASTER_CONTRACT_VERSION,
    build_management_round,
)


CONTRACT_VERSION = "oom_sakkie_herdmaster_management_consumer_v1"
TOOL_NAME = "herdmaster_proactive_management_round"
MAX_EVIDENCE_AGE_SECONDS = 24 * 60 * 60
MAX_INVOCATION_SKEW_SECONDS = 120
_SCHEDULED_SEAL = object()
_ACTIVE_STATES = frozenset({"received", "assigned", "working", "waiting_for_input", "preview_ready"})
ZERO_AUTHORITY = {
    "zero_io": True,
    "writes_farm_data": False,
    "writes_lifecycle": False,
    "writes_mating": False,
    "writes_pregnancy": False,
    "writes_health": False,
    "writes_movement": False,
    "writes_availability": False,
    "sends_telegram": False,
    "creates_owner_card": False,
    "creates_owner_question": False,
    "direct_specialist_delivery": False,
    "protected_actions_performed": False,
}


@dataclass(frozen=True)
class ScheduledManagerContext:
    owner_user_id: str
    mission_id: str
    invocation_at: datetime
    _seal: object


def issue_scheduled_manager_context(owner_user_id: str, mission_id: str, invocation_at: datetime):
    owner = str(owner_user_id or "").strip()
    mission = str(mission_id or "").strip()
    if not owner or not mission or not isinstance(invocation_at, datetime) or invocation_at.tzinfo is None:
        return None
    return ScheduledManagerContext(owner, mission, invocation_at.astimezone(timezone.utc), _SCHEDULED_SEAL)


def consume_herdmaster_management_round(
    *,
    authority: Any,
    expected_owner_user_id: str,
    canonical_round: Mapping[str, Any],
    invocation_at: datetime,
    attributable_owner_observations: Sequence[Mapping[str, Any]] = (),
    active_lifecycles: Sequence[Mapping[str, Any]] = (),
    prior_consumptions: Sequence[Mapping[str, Any]] = (),
    specialist_builder: Callable[..., Mapping[str, Any]] | None = build_management_round,
    trusted_now: datetime | None = None,
) -> dict[str, Any]:
    """Consume one current specialist round into an internal manager result."""
    trusted_now = trusted_now or datetime.now(timezone.utc)
    expected_owner = str(expected_owner_user_id or "").strip()
    if not expected_owner or not isinstance(invocation_at, datetime) or invocation_at.tzinfo is None:
        return _exception("authenticated_manager_context_invalid", invocation_at)
    invocation_at = invocation_at.astimezone(timezone.utc)
    if not isinstance(trusted_now, datetime) or trusted_now.tzinfo is None:
        return _exception("trusted_manager_clock_invalid", invocation_at)
    trusted_now = trusted_now.astimezone(timezone.utc)
    if abs((trusted_now - invocation_at).total_seconds()) > MAX_INVOCATION_SKEW_SECONDS:
        return _exception("authenticated_manager_context_stale", trusted_now)
    principal, context_binding = _authenticated_principal(authority, expected_owner, invocation_at)
    if not principal:
        return _exception("authenticated_manager_context_denied", invocation_at)
    if specialist_builder is None:
        return _exception("herdmaster_specialist_unavailable", invocation_at, principal)

    try:
        active, active_digest = _active_case_state(active_lifecycles)
        prepared = specialist_builder(
            canonical_round,
            active_specialist_cases=(),
            attributable_owner_observations=attributable_owner_observations,
            contained_animal_ids=tuple(sorted(active)),
        )
        _validate_round(prepared)
        evidence_at = _time(prepared["source_evidence_generation"])
        age = (trusted_now - evidence_at).total_seconds()
        if age < 0 or age > MAX_EVIDENCE_AGE_SECONDS:
            return _exception("herdmaster_evidence_generation_stale", invocation_at, principal)
        # Evidence generation is freshness metadata, not a material management
        # result.  A loader may regenerate the same canonical packet a few
        # microseconds later; bind replay to the actual result while retaining
        # the generation separately for freshness checks and audit visibility.
        material_result = dict(prepared)
        material_result.pop("source_evidence_generation", None)
        result_digest = _digest(material_result)
        replay = _replay_state(prepared, result_digest, active_digest, context_binding["digest"], prior_consumptions)
        if replay == "changed":
            return _exception("herdmaster_management_round_binding_changed", invocation_at, principal)
        binding = {
            "authenticated_owner_identity_sha256": _digest({"owner_user_id": principal}),
            "management_round_identity": prepared["publication_id"],
            "deduplication_key": prepared["deduplication_key"],
            "evidence_generation": prepared["source_evidence_generation"],
            "specialist_contract_version": prepared["contract_version"],
            "invocation_timestamp": invocation_at.isoformat(),
            "invocation_context": context_binding,
            "result_digest": result_digest,
            "result_digest_version": 2,
            "active_case_deduplication_state": {
                "active_pig_ids": tuple(sorted(active)),
                "digest": active_digest,
            },
        }
        if replay == "exact":
            return {
                "success": True,
                "status": "herdmaster_management_round_replay_suppressed",
                "contract_version": CONTRACT_VERSION,
                "binding": binding,
                "specialist_result": None,
                "accepted_work_item_count": 0,
                "duplicate_packets": 0,
                "systemic_exception": None,
                **ZERO_AUTHORITY,
            }
        specialist_result = _to_specialist_result(prepared, evidence_at, trusted_now)
        return {
            "success": True,
            "status": "herdmaster_management_round_consumed",
            "contract_version": CONTRACT_VERSION,
            "binding": binding,
            "specialist_result": specialist_result,
            "accepted_work_item_count": len(specialist_result.work_items),
            "duplicate_packets": 0,
            "systemic_exception": None,
            **ZERO_AUTHORITY,
        }
    except Exception:
        return _exception("herdmaster_management_round_malformed", invocation_at, principal)


def validate_management_authority(authority, expected_owner_user_id, invocation_at, *, trusted_now=None):
    """Validate the manager capability before any runtime evidence read."""
    trusted_now = trusted_now or datetime.now(timezone.utc)
    if (not isinstance(invocation_at, datetime) or invocation_at.tzinfo is None
            or not isinstance(trusted_now, datetime) or trusted_now.tzinfo is None):
        return None
    invocation_at = invocation_at.astimezone(timezone.utc)
    trusted_now = trusted_now.astimezone(timezone.utc)
    if abs((trusted_now - invocation_at).total_seconds()) > MAX_INVOCATION_SKEW_SECONDS:
        return None
    principal, context = _authenticated_principal(
        authority, str(expected_owner_user_id or "").strip(), invocation_at)
    return {"principal": principal, "context": context} if principal else None


def _authenticated_principal(authority, expected_owner, invocation_at):
    bound = bind_gateway_owner_authority(authority, TOOL_NAME)
    if bound is not None and bound.owner_user_id == expected_owner:
        value = {
            "type": "authenticated_private_owner",
            "mission_identity_sha256": _digest({"tool": TOOL_NAME, "owner": expected_owner}),
        }
        return bound.owner_user_id, {**value, "digest": _digest(value)}
    if (
        isinstance(authority, ScheduledManagerContext)
        and authority._seal is _SCHEDULED_SEAL
        and authority.owner_user_id == expected_owner
        and authority.invocation_at == invocation_at
    ):
        value = {
            "type": "scheduled_manager",
            "mission_identity_sha256": _digest({"mission_id": authority.mission_id}),
        }
        return authority.owner_user_id, {**value, "digest": _digest(value)}
    return "", {}


def _active_case_state(rows):
    active = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("active_lifecycle_mapping_required")
        pig_id = str(raw.get("pig_id") or "").strip()
        lifecycle_id = str(raw.get("lifecycle_id") or "").strip()
        state = str(raw.get("state") or "").strip()
        if not pig_id or not lifecycle_id or state not in _ACTIVE_STATES or pig_id in active:
            raise ValueError("active_lifecycle_binding_invalid")
        active[pig_id] = {
            "lifecycle_id": lifecycle_id,
            "state": state,
            "card_message_id": str(raw.get("card_message_id") or "").strip(),
        }
    return active, _digest(active)


def _validate_round(value):
    if not isinstance(value, Mapping):
        raise ValueError("management_round_mapping_required")
    required = ("publication_id", "deduplication_key", "source_evidence_generation", "ranked_actions")
    if (
        value.get("success") is not True
        or value.get("status") != "management_round_prepared_for_internal_publication"
        or value.get("contract_version") != HERDMASTER_CONTRACT_VERSION
        or value.get("publish_to") != "oom_sakkie_internal_owner_attention"
        or value.get("direct_owner_delivery") is not False
        or value.get("zero_io") is not True
        or value.get("writes_farm_data") is not False
        or value.get("sends_telegram") is not False
        or value.get("directly_messages_owner") is not False
        or value.get("creates_mating") is not False
        or value.get("changes_lifecycle") is not False
        or value.get("changes_availability") is not False
        or value.get("publication_execution_authority") is not False
        or any(not str(value.get(key) or "").strip() for key in required[:-1])
        or not isinstance(value.get("ranked_actions"), list)
        or len(value["ranked_actions"]) > 3
        or value.get("ranked_action_count") != len(value["ranked_actions"])
    ):
        raise ValueError("management_round_contract_invalid")


def _replay_state(prepared, result_digest, active_digest, context_digest, prior_rows):
    matches = []
    for row in prior_rows:
        if not isinstance(row, Mapping):
            raise ValueError("prior_consumption_mapping_required")
        same_identity = (
            row.get("management_round_identity") == prepared["publication_id"]
            or row.get("deduplication_key") == prepared["deduplication_key"]
        )
        if not same_identity:
            continue
        prior_digest = row.get("result_digest")
        legacy_prepared = dict(prepared)
        legacy_prepared["source_evidence_generation"] = row.get("evidence_generation")
        digest_matches = prior_digest == result_digest or (
            row.get("result_digest_version") in (None, 1)
            and prior_digest == _digest(legacy_prepared)
        )
        exact = (
            row.get("management_round_identity") == prepared["publication_id"]
            and row.get("deduplication_key") == prepared["deduplication_key"]
            and digest_matches
            and row.get("active_case_digest") == active_digest
            and row.get("invocation_context_digest") == context_digest
        )
        matches.append(exact)
    if not matches:
        return "new"
    return "exact" if all(matches) else "changed"


def _to_specialist_result(prepared, evidence_at, invocation_at):
    items = []
    for action in prepared["ranked_actions"]:
        if not isinstance(action, Mapping):
            raise ValueError("ranked_action_mapping_required")
        pig_id = str(action.get("pig_id") or "").strip()
        tag = str(action.get("tag_number") or "").strip()
        category = str(action.get("category") or "").strip()
        source_identity = str(action.get("source_identity") or "").strip()
        if not pig_id or not tag or not category or not source_identity:
            raise ValueError("ranked_action_identity_incomplete")
        planning = action.get("pregnancy_planning") if isinstance(action.get("pregnancy_planning"), Mapping) else {}
        status = str(planning.get("operational_status") or "")
        next_action = _next_action(action, planning)
        question = "" if status == "Assumed Pregnant" else str(action.get("smallest_missing_physical_observation") or "").strip()
        provenance = Provenance(
            specialist="herdmaster",
            result_id=prepared["publication_id"],
            source_refs=tuple(filter(None, (
                prepared.get("source_worklist_id"), source_identity,
                action.get("source_evidence_digest"),
            ))),
            observed_at=evidence_at,
            confidence=0.85 if status == "Assumed Pregnant" else 0.7,
        )
        items.append(SpecialistWorkItem(
            item_id=f"{prepared['publication_id']}:{pig_id}",
            dedupe_key=f"herdmaster:{pig_id}:{source_identity}",
            domain="herd",
            title=f"{tag}: {status or category}",
            why=str(action.get("why_it_matters_now") or "Current herd evidence can change management."),
            next_action=next_action,
            assignee="dad",
            state=WorkState.PLANNED if status == "Assumed Pregnant" else WorkState.WAITING_EVIDENCE,
            authority=Authority.ADVISORY,
            provenance=provenance,
            business_value=max(1, 100 - int(action.get("rank") or 1)),
            stale_after_hours=24,
            genuine_question=question,
            question_for="dad" if question else "",
        ))
    return SpecialistResult(
        specialist="herdmaster",
        result_id=prepared["publication_id"],
        observed_at=invocation_at,
        availability=SpecialistAvailability.AVAILABLE,
        work_items=tuple(items),
    )


def _next_action(action, planning):
    status = str(planning.get("operational_status") or "")
    if status == "Assumed Pregnant":
        window = planning.get("farrowing_pen_preparation_window") or {}
        projected = planning.get("projected_farrowing_range") or {}
        return (
            f"Prepare proportionally from {window.get('start')} to {window.get('complete_by')}; "
            f"plan around the approximate {projected.get('earliest')} to {projected.get('latest')} farrowing range. "
            "Keep Assumed Pregnant separate from clinical confirmation; scanning remains optional."
        )
    if status == "Inconclusive":
        return "Retain Inconclusive and reassess only when the next attributable reproductive-status observation arrives."
    return str(action.get("smallest_missing_physical_observation") or "Reassess on new attributable evidence.")


def _exception(reason, invocation_at, principal=""):
    timestamp = invocation_at.isoformat() if isinstance(invocation_at, datetime) and invocation_at.tzinfo else ""
    exception_id = "OOM-HERDMASTER-SYSTEMIC-" + _digest({"reason": reason, "at": timestamp})[:20].upper()
    return {
        "success": False,
        "status": "herdmaster_management_round_contained",
        "contract_version": CONTRACT_VERSION,
        "binding": {},
        "specialist_result": SpecialistResult(
            specialist="herdmaster",
            result_id=exception_id,
            observed_at=invocation_at if isinstance(invocation_at, datetime) and invocation_at.tzinfo else datetime.now(timezone.utc),
            availability=SpecialistAvailability.CONTAINED,
        ),
        "accepted_work_item_count": 0,
        "duplicate_packets": 0,
        "systemic_exception": {
            "exception_id": exception_id,
            "reason": reason,
            "specialist": "HERDMASTER",
            "manual_coverage_required": False,
            "authenticated_principal_bound": bool(principal),
            "deduplicated": True,
        },
        **ZERO_AUTHORITY,
    }


def _time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_aware_evidence_generation_required")
    return parsed.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
