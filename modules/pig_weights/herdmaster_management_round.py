"""Pure proactive HERDMASTER management-round publication contract.

The caller supplies canonical worklist evidence plus attributable active-case
and owner-observation evidence. This module ranks and composes; it performs no
I/O, delivery, persistence, or protected action.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Mapping, Sequence


CONTRACT_VERSION = "herdmaster_proactive_management_round_v1"
MAX_ACTIONS = 3
AUTHORITY = {
    "zero_io": True,
    "writes_farm_data": False,
    "sends_telegram": False,
    "directly_messages_owner": False,
    "creates_mating": False,
    "changes_lifecycle": False,
    "changes_availability": False,
    "publication_execution_authority": False,
}


def build_management_round(
    canonical_round: Mapping,
    *,
    active_specialist_cases: Sequence[Mapping] = (),
    attributable_owner_observations: Sequence[Mapping] = (),
    contained_animal_ids: Sequence[str] = (),
) -> dict:
    """Build one deterministic maximum-three internal Oom Sakkie packet."""
    source = _mapping(canonical_round, "canonical_round")
    if source.get("success") is not True or source.get("writes_performed") is not False:
        raise ValueError("canonical_read_only_round_required")
    generated_at = _time(source.get("generated_at"), "generated_at")
    worklist_id = _required(source.get("worklist_id"), "worklist_id")
    contained = {_required(value, "contained_animal_id") for value in contained_animal_ids}
    observations = {}
    for raw in attributable_owner_observations:
        row = _mapping(raw, "attributable_owner_observation")
        pig_id = _required(row.get("pig_id"), "owner_observation_pig_id")
        if pig_id in observations:
            raise ValueError("duplicate_owner_observation_pig_id")
        _required(row.get("source_identity"), "owner_observation_source_identity")
        observed_at = _time(row.get("observed_at"), "owner_observation_observed_at")
        if observed_at > generated_at:
            raise ValueError("owner_observation_future_dated")
        _required(row.get("canonical_task_id"), "owner_observation_canonical_task_id")
        observations[pig_id] = row

    candidates = []
    active_ids = set()
    for raw in active_specialist_cases:
        case = _mapping(raw, "active_specialist_case")
        pig_id = _required(case.get("pig_id"), "active_case_pig_id")
        if pig_id in active_ids:
            raise ValueError("duplicate_active_specialist_case_pig_id")
        active_ids.add(pig_id)
        candidates.append({
            "pig_id": pig_id,
            "tag_number": _required(case.get("tag_number"), "active_case_tag"),
            "category": "urgent welfare and health follow-up",
            "score": 100,
            "current_evidence": list(case.get("current_evidence") or ()),
            "why_it_matters_now": _required(case.get("why_it_matters_now"), "active_case_reason"),
            "smallest_missing_physical_observation": "Already requested by Oom Sakkie; do not ask again.",
            "decision_that_could_change": _required(case.get("decision_that_could_change"), "active_case_decision"),
            "specialist_ownership": _required(case.get("specialist_ownership"), "active_case_owner"),
            "reassessment_trigger": _required(case.get("reassessment_trigger"), "active_case_trigger"),
            "question_suppressed": True,
            "source_identity": _required(case.get("source_identity"), "active_case_source"),
        })

    task_ids = set()
    task_pig_ids = set()
    for raw in source.get("tasks") or ():
        task = _mapping(raw, "canonical_task")
        pig_id = _required(task.get("pig_id"), "task_pig_id")
        task_id = _required(task.get("task_id"), "task_id")
        _required(task.get("evidence_digest"), "task_evidence_digest")
        if task.get("writes_performed") is not False:
            raise ValueError("canonical_task_read_only_required")
        if task_id in task_ids or pig_id in task_pig_ids:
            raise ValueError("duplicate_canonical_task_identity")
        task_ids.add(task_id)
        task_pig_ids.add(pig_id)
        if pig_id in active_ids or pig_id in contained or task.get("completed") is True:
            continue
        owner_observation = observations.get(pig_id, {})
        if owner_observation and owner_observation["canonical_task_id"] != task_id:
            raise ValueError("owner_observation_task_binding_mismatch")
        candidate = _canonical_candidate(task, owner_observation)
        candidates.append(candidate)

    ranked = sorted(
        candidates,
        key=lambda row: (-row["score"], row["pig_id"], row["category"]),
    )[:MAX_ACTIONS]
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
        row.pop("score", None)
    evidence = {
        "source_worklist_id": worklist_id,
        "actions": ranked,
        "contained_animal_ids": sorted(contained),
    }
    digest = _digest(evidence)
    return {
        "success": True,
        "status": "management_round_prepared_for_internal_publication",
        "contract_version": CONTRACT_VERSION,
        "publication_id": "HERD-ROUND-" + digest[:24].upper(),
        "deduplication_key": "HERD-ROUND-NOTIFY-" + digest[24:48].upper(),
        "publish_to": "oom_sakkie_internal_owner_attention",
        "direct_owner_delivery": False,
        "automatic_publication_ready": True,
        "source_worklist_id": worklist_id,
        "source_evidence_generation": generated_at.isoformat(),
        "ranked_actions": ranked,
        "ranked_action_count": len(ranked),
        "suppressed": {
            "active_case_duplicate_questions": sorted(active_ids),
            "contained_data_quality_cases": sorted(contained),
            "lower_ranked_count": max(0, len(candidates) - len(ranked)),
        },
        "owner_text": _render(ranked),
        "reassessment_policy": "rebuild_when_bound_canonical_or_specialist_case_evidence_changes",
        **AUTHORITY,
    }


def _canonical_candidate(task, observation):
    group = str(task.get("task_group") or "").strip().casefold()
    category, score = {
        "pregnancy check due": ("pregnancy/reproductive status", 80),
        "post-litter recovery check": ("post-litter recovery", 65),
        "review current reproductive status before a breeding decision": ("breeding readiness", 55),
        "weigh before breeding decision": ("breeding readiness", 45),
        "withdrawal or availability evidence": ("withdrawal or availability evidence", 60),
        "lifecycle/data-quality conflict": ("lifecycle/data-quality conflicts", 70),
    }.get(group, (group or "herd evidence follow-up", 40))
    result = str(observation.get("operational_result") or "").strip()
    days_to_farrowing = observation.get("days_to_expected_farrowing")
    if result == "Assumed Pregnant" and isinstance(days_to_farrowing, int) and days_to_farrowing <= 30:
        score = 90
    elif result == "Inconclusive":
        score = max(score, 75)
    known = dict(task.get("known_evidence") or {})
    current = [
        f"Canonical task: {task.get('why') or 'Unresolved herd evidence.'}",
        f"Latest weight: {known.get('latest_weight_kg', 'Unknown')} kg on {known.get('latest_weight_date', 'Unknown')}",
        f"Canonical state: {known.get('state', 'Unknown')}",
    ]
    if result:
        current.append(
            f"Attributable owner observation: {result}; {observation.get('observed_signs') or 'no additional signs supplied'}; not clinically confirmed."
        )
    question = str(observation.get("smallest_missing_physical_observation") or "").strip()
    if not question:
        checks = list(task.get("required_checks") or ())
        question = checks[0] if checks else "One current attributable physical observation."
    return {
        "pig_id": _required(task.get("pig_id"), "task_pig_id"),
        "tag_number": _required(task.get("tag_number"), "task_tag"),
        "category": category,
        "score": score,
        "current_evidence": current,
        "why_it_matters_now": str(task.get("delay_consequence") or task.get("why") or "The unresolved evidence can change current management."),
        "smallest_missing_physical_observation": question,
        "decision_that_could_change": str(observation.get("decision_that_could_change") or task.get("provisional_recommendation") or "Current herd recommendation"),
        "specialist_ownership": str(observation.get("specialist_ownership") or "HERDMASTER"),
        "reassessment_trigger": str(observation.get("reassessment_trigger") or "New attributable canonical evidence for this task"),
        "question_suppressed": False,
        "source_identity": str(observation.get("source_identity") or task.get("task_id") or ""),
        "source_evidence_digest": _required(task.get("evidence_digest"), "task_evidence_digest"),
        "owner_observation_observed_at": str(observation.get("observed_at") or ""),
    }


def _render(actions):
    lines = ["HERDMASTER management round", ""]
    for row in actions:
        lines.extend([
            f"{row['rank']}. {row['tag_number']} ({row['pig_id']}) - {row['category']}",
            "Current evidence: " + " | ".join(str(item) for item in row["current_evidence"]),
            f"Why now: {row['why_it_matters_now']}",
            f"Next evidence: {row['smallest_missing_physical_observation']}",
            f"Could change: {row['decision_that_could_change']}",
            f"Owner: {row['specialist_ownership']}; reassess: {row['reassessment_trigger']}",
            "",
        ])
    return "\n".join(lines).rstrip()


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
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
