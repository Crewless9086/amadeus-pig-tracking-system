"""Pure whole-herd next-round composition for the existing Oom Sakkie manager.

This module consumes already-canonical evidence. It performs no loading,
persistence, delivery, inference, or protected action.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Mapping, Sequence


CONTRACT_VERSION = "herdmaster_whole_herd_next_round_v1"
MAX_NEW_ACTIONS = 3
ACTIVE_STATES = frozenset({"waiting_for_input", "preview_ready", "waiting_for_confirmation", "preview_correction_pending"})
REPRODUCTIVE_STATES = frozenset({"Assumed Pregnant", "Inconclusive", "Not Pregnant", "Needs Data"})
AUTHORITY = {
    "zero_io": True,
    "writes_farm_data": False,
    "sends_telegram": False,
    "creates_owner_question": False,
    "creates_mating": False,
    "changes_pregnancy": False,
    "changes_lifecycle": False,
    "changes_movement": False,
    "changes_health": False,
    "changes_availability": False,
    "publication_execution_authority": False,
}


def build_whole_herd_packet(
    canonical_evidence: Mapping,
    *,
    active_lifecycles: Sequence[Mapping] = (),
    monday_weighing_candidates: Sequence[Mapping] = (),
    reproductive_reviews: Sequence[Mapping] = (),
    breeding_reviews: Sequence[Mapping] = (),
    data_quality_matters: Sequence[Mapping] = (),
) -> dict:
    """Return one deterministic packet for later authenticated consumption."""
    source = _mapping(canonical_evidence, "canonical_evidence")
    if source.get("success") is not True or source.get("writes_performed") is not False:
        raise ValueError("canonical_read_only_evidence_required")
    generated = _time(source.get("evidence_generation"), "evidence_generation")
    source_id = _required(source.get("evidence_identity"), "evidence_identity")

    active = _active_cases(active_lifecycles)
    active_ids = {item["pig_id"] for item in active}
    weighing = _weighing_journey(monday_weighing_candidates, active_ids)
    reproduction = [_reproductive(item, generated, active_ids) for item in reproductive_reviews]
    breeding = [_breeding(item, active_ids) for item in breeding_reviews]
    quality = [_quality(item, active_ids) for item in data_quality_matters]
    _unique_pigs(reproduction, "reproductive_review")
    _unique_pigs(breeding, "breeding_review")

    candidates = []
    for row in reproduction:
        if row["operational_status"] == "Assumed Pregnant" and row["current_applicability"]:
            candidates.append(_action(95, row["pig_id"], row["tag_number"], "farrowing preparation",
                row["current_evidence"], row["smallest_next_observation"],
                "Preparation urgency or reproductive-status reassessment", row["source_identity"],
                detail={"reproductive_plan": row}))
        elif row["operational_status"] == "Inconclusive":
            candidates.append(_action(70, row["pig_id"], row["tag_number"], "reproductive reassessment",
                row["current_evidence"], row["smallest_next_observation"],
                "Continue monitoring, classify current status, or return to heat path", row["source_identity"],
                detail={"reproductive_plan": row}))
    if weighing["candidate_count"]:
        candidates.append(_action(85, "HERD-MONDAY-WEIGHTS", "Monday weighing group", "targeted weighing intake",
            [f"{weighing['candidate_count']} canonically identified pigs need current weights."],
            weighing["single_family_request"], "Weight-dependent worklist and breeding-readiness priorities",
            weighing["journey_identity"], detail={"bulk_weight_journey": weighing}))
    for row in breeding:
        if row["classification"] == "conditionally_ready_after_inspection":
            candidates.append(_action(60, row["pig_id"], row["tag_number"], "breeding readiness",
                row["current_evidence"], row["smallest_missing_observation"],
                "Whether a conditional male shortlist may be reviewed", row["source_identity"],
                detail={"breeding_guidance": row}))
    for row in quality:
        if row["status"] == "unresolved":
            candidates.append(_action(55, row["pig_id"], row["tag_number"], "data-quality follow-up",
                row["current_evidence"], row["smallest_missing_evidence"],
                "Whether the conflict can be corrected through its governed workflow", row["source_identity"],
                detail={"data_quality": row}))

    ranked = sorted(candidates, key=lambda row: (-row.pop("_score"), row["pig_id"], row["category"]))[:MAX_NEW_ACTIONS]
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    payload = {
        "source_evidence_identity": source_id,
        "protected_active_lifecycles": active,
        "ranked_new_actions": ranked,
        "monday_weighing_journey": weighing,
        "reproductive_reviews": reproduction,
        "breeding_reviews": breeding,
        "data_quality_matters": quality,
    }
    digest = _digest(payload)
    return {
        "success": True,
        "status": "whole_herd_next_round_prepared",
        "contract_version": CONTRACT_VERSION,
        "packet_identity": "HERD-NEXT-" + digest[:24].upper(),
        "deduplication_key": "HERD-NEXT-DEDUP-" + digest[24:48].upper(),
        "evidence_generation": generated.isoformat(),
        "source_evidence_identity": source_id,
        "protected_active_lifecycles": active,
        "ranked_new_actions": ranked,
        "ranked_new_action_count": len(ranked),
        "monday_weighing_journey": weighing,
        "reproductive_reviews": reproduction,
        "breeding_reviews": breeding,
        "data_quality_matters": quality,
        "owner_text": _render(active, ranked, reproduction, breeding, quality),
        "future_consumer": "existing_authenticated_oom_sakkie_herdmaster_manager_boundary",
        **AUTHORITY,
    }


def _active_cases(rows):
    result, seen = [], set()
    for raw in rows:
        row = _mapping(raw, "active_lifecycle")
        pig_id = _required(row.get("pig_id"), "active_lifecycle_pig_id")
        if pig_id in seen:
            raise ValueError("duplicate_active_lifecycle_pig_id")
        seen.add(pig_id)
        state = _required(row.get("state"), "active_lifecycle_state")
        if state not in ACTIVE_STATES:
            raise ValueError("active_lifecycle_state_not_active")
        result.append({
            "pig_id": pig_id,
            "tag_number": _required(row.get("tag_number"), "active_lifecycle_tag"),
            "lifecycle_id": _required(row.get("lifecycle_id"), "active_lifecycle_id"),
            "state": state,
            "specialist_owner": _required(row.get("specialist_owner"), "active_lifecycle_owner"),
            "current_evidence": list(row.get("current_evidence") or ()),
            "existing_question_or_card_id": _required(row.get("existing_question_or_card_id"), "active_lifecycle_existing_card"),
            "reassessment_trigger": _required(row.get("reassessment_trigger"), "active_lifecycle_trigger"),
            "question_suppressed": True,
            "new_case_created": False,
        })
    return sorted(result, key=lambda item: item["pig_id"])


def _weighing_journey(rows, active_ids):
    candidates, seen = [], set()
    for raw in rows:
        row = _mapping(raw, "weighing_candidate")
        pig_id = _required(row.get("pig_id"), "weighing_candidate_pig_id")
        if pig_id in seen:
            raise ValueError("duplicate_weighing_candidate_pig_id")
        seen.add(pig_id)
        if pig_id in active_ids:
            continue
        candidates.append({
            "pig_id": pig_id,
            "tag_number": _required(row.get("tag_number"), "weighing_candidate_tag"),
            "why_now": _required(row.get("why_now"), "weighing_candidate_reason"),
            "latest_weight_kg": row.get("latest_weight_kg") if row.get("latest_weight_kg") is not None else "Unknown",
            "latest_weight_date": str(row.get("latest_weight_date") or "Unknown"),
            "source_identity": _required(row.get("source_identity"), "weighing_candidate_source"),
        })
    candidates.sort(key=lambda item: item["pig_id"])
    identity = "HERD-MONDAY-WEIGHTS-" + _digest(candidates)[:24].upper()
    tags = ", ".join(f"{item['tag_number']} ({item['pig_id']})" for item in candidates)
    request = ("On Monday, send one message with each listed pig's tag and measured weight in kg; "
        "include the weighing date once and include an observation time only if known: " + tags) if candidates else "No Monday reweigh is currently required."
    return {
        "journey_identity": identity,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "single_family_request": request,
        "natural_language_example": "Monday weights: Tag 41 was 23.4 kg and Tag 52 was 19.8 kg. Weighed 3 August 2026; time Unknown.",
        "preview_contract": {
            "requires_exact_canonical_identity_per_fact": True,
            "requires_weight_kg_and_evidence_date": True,
            "observation_time_optional_unknown_allowed": True,
            "one_consolidated_before_after_preview": True,
            "confirmation_bound_to_preview_hash_and_evidence_generation": True,
            "future_persistence": "existing_governed_conversational_weight_writer_only",
            "replay_additional_fact_count": 0,
            "refresh_recommendation_after_confirmed_write": True,
        },
    }


def _reproductive(raw, generated, active_ids):
    row = _mapping(raw, "reproductive_review")
    pig_id = _required(row.get("pig_id"), "reproductive_pig_id")
    if pig_id in active_ids:
        raise ValueError("active_lifecycle_reproductive_overlap")
    status = _required(row.get("operational_status"), "reproductive_status")
    if status not in REPRODUCTIVE_STATES:
        raise ValueError("unsupported_reproductive_status")
    observed = _time(row.get("observed_at"), "reproductive_observed_at")
    if observed > generated:
        raise ValueError("reproductive_observation_future_dated")
    result = {
        "pig_id": pig_id,
        "tag_number": _required(row.get("tag_number"), "reproductive_tag"),
        "operational_status": status,
        "current_evidence": list(row.get("current_evidence") or ()),
        "observed_at": observed.isoformat(),
        "source_identity": _required(row.get("source_identity"), "reproductive_source"),
        "smallest_next_observation": _required(row.get("smallest_next_observation"), "reproductive_next_observation"),
        "clinical_confirmation": str(row.get("clinical_confirmation") or "Unknown"),
        "current_applicability": bool(row.get("current_applicability")),
    }
    if status == "Assumed Pregnant":
        result.update({
            "mating_id": _required(row.get("mating_id"), "reproductive_mating_id"),
            "mating_date": _required(row.get("mating_date"), "reproductive_mating_date"),
            "observed_signs": _required(row.get("observed_signs"), "reproductive_observed_signs"),
            "projected_farrowing_range": _range(row.get("projected_farrowing_range")),
            "preparation_window": _range(row.get("preparation_window")),
            "change_triggers": list(row.get("change_triggers") or ()),
            "prohibited_without_more_evidence": list(row.get("prohibited_without_more_evidence") or ()),
        })
        if "confirmed" in result["clinical_confirmation"].casefold() and "not clinically" not in result["clinical_confirmation"].casefold():
            raise ValueError("assumed_pregnant_must_not_claim_clinical_confirmation")
    return result


def _breeding(raw, active_ids):
    row = _mapping(raw, "breeding_review")
    pig_id = _required(row.get("pig_id"), "breeding_pig_id")
    if pig_id in active_ids:
        raise ValueError("active_lifecycle_breeding_overlap")
    classification = _required(row.get("classification"), "breeding_classification")
    if classification not in {"conditionally_ready_after_inspection", "not_currently_eligible", "needs_data"}:
        raise ValueError("breeding_classification_unsupported")
    males = list(row.get("compatible_males") or ())
    readiness = row.get("readiness_evidence_complete") is True
    if not readiness and males:
        raise ValueError("unsupported_male_recommendation_without_readiness")
    guidance = []
    for male in males:
        item = _mapping(male, "compatible_male")
        guidance.append({
            "pig_id": _required(item.get("pig_id"), "compatible_male_pig_id"),
            "tag_number": _required(item.get("tag_number"), "compatible_male_tag"),
            "compatibility_evidence": _required(item.get("compatibility_evidence"), "compatible_male_evidence"),
            "performance_reason": _required(item.get("performance_reason"), "compatible_male_performance"),
            "actionable_mating_recommendation": False,
        })
    return {
        "pig_id": pig_id,
        "tag_number": _required(row.get("tag_number"), "breeding_tag"),
        "classification": classification,
        "current_evidence": list(row.get("current_evidence") or ()),
        "readiness_evidence_complete": readiness,
        "smallest_missing_observation": _required(row.get("smallest_missing_observation"), "breeding_missing_observation"),
        "conditional_male_shortlist": guidance,
        "requires_owner_confirmed_mating_preview": True,
        "mating_authority": False,
        "source_identity": _required(row.get("source_identity"), "breeding_source"),
    }


def _quality(raw, active_ids):
    row = _mapping(raw, "data_quality_matter")
    pig_id = _required(row.get("pig_id"), "data_quality_pig_id")
    return {
        "pig_id": pig_id,
        "tag_number": _required(row.get("tag_number"), "data_quality_tag"),
        "status": _required(row.get("status"), "data_quality_status"),
        "current_evidence": list(row.get("current_evidence") or ()),
        "smallest_missing_evidence": "Owned by active lifecycle; no duplicate question." if pig_id in active_ids else _required(row.get("smallest_missing_evidence"), "data_quality_missing_evidence"),
        "source_identity": _required(row.get("source_identity"), "data_quality_source"),
        "question_suppressed": pig_id in active_ids,
    }


def _action(score, pig_id, tag, category, evidence, next_observation, decision, source, *, detail):
    return {"_score": score, "pig_id": pig_id, "tag_number": tag, "category": category,
        "current_evidence": list(evidence), "smallest_next_observation": next_observation,
        "decision_that_could_change": decision, "source_identity": source, **detail}


def _render(active, actions, reproduction, breeding, quality):
    lines = ["HERDMASTER next whole-herd round"]
    if active:
        lines.append("Already active — do not ask again: " + "; ".join(
            f"{item['tag_number']} ({item['pig_id']}), {item['state']}, reassess on {item['reassessment_trigger']}" for item in active))
    for row in actions:
        lines.append(f"{row['rank']}. {row['tag_number']} ({row['pig_id']}): {row['category']}. Next: {row['smallest_next_observation']}")
        plan = row.get("reproductive_plan") or {}
        if plan.get("operational_status") == "Assumed Pregnant":
            farrowing, preparation = plan["projected_farrowing_range"], plan["preparation_window"]
            lines.append(f"   Operational Assumed Pregnant, not clinical confirmation; mating {plan['mating_id']} on {plan['mating_date']}; projected farrowing approximately {farrowing['start']} to {farrowing['end']}; prepare approximately {preparation['start']} to {preparation['end']}.")
    inconclusive = [row for row in reproduction if row["operational_status"] == "Inconclusive"]
    if inconclusive:
        lines.append("Monitoring: " + "; ".join(f"{row['tag_number']} remains Inconclusive" for row in inconclusive))
    blocked = [row for row in breeding if not row["readiness_evidence_complete"]]
    if blocked:
        lines.append("Breeding remains conditional: " + "; ".join(f"{row['tag_number']}: {row['smallest_missing_observation']}" for row in blocked))
    unresolved = [row for row in quality if row["status"] == "unresolved"]
    if unresolved:
        lines.append("Data quality: " + "; ".join(f"{row['tag_number']}: {row['smallest_missing_evidence']}" for row in unresolved))
    return "\n".join(lines)


def _range(value):
    row = _mapping(value, "date_range")
    return {"start": _required(row.get("start"), "date_range_start"), "end": _required(row.get("end"), "date_range_end"),
        "uncertainty": _required(row.get("uncertainty"), "date_range_uncertainty")}


def _unique_pigs(rows, label):
    ids = [row["pig_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate_{label}_pig_id")


def _mapping(value, label):
    if not isinstance(value, Mapping):
        raise ValueError(f"{label}_mapping_required")
    return dict(value)


def _required(value, label):
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label}_required")
    return text


def _time(value, label):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}_timezone_required")
    return parsed


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
