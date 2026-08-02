"""Deterministic, owner-only answers to ordinary questions about one pig."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from modules.pig_weights.pregnancy_evidence import (
    pregnancy_recommendation,
    resolve_pregnancy_evidence,
)

CONTRACT_VERSION = "herdmaster_ordinary_herd_question_v2"
STALE_WEIGHT_DAYS = 30
_SUBJECT_PATTERNS = (
    re.compile(r"\babout\s+([^,?.]+)", re.I),
    re.compile(
        r"\b(?:latest recorded weight|breeding status|next recommended action)"
        r"\s+(?:for|of)\s+([^,?.]+)",
        re.I,
    ),
    re.compile(
        r"\bwhat is\s+(.+?)(?:'s|’s)\s+"
        r"(?:latest recorded weight|breeding status)",
        re.I,
    ),
    re.compile(r"\b(?:is|was|does|did)\s+([^,?.]+?)\s+(?:weigh|bred|mated)", re.I),
)


def answer_herd_question(
    question,
    *,
    readiness,
    matings,
    worklist=None,
    today=None,
):
    """Resolve exactly one pig and compose canonical facts without writes."""
    today = today or date.today()
    subject = _subject(question)
    if not subject:
        return _failure(
            "animal_identity_required",
            "Please name one pig or give one exact Pig ID.",
        )
    if not isinstance(readiness, dict) or readiness.get("success") is not True:
        return _failure(
            "canonical_herd_evidence_unavailable",
            "Canonical herd evidence is unavailable. No farm action was taken.",
        )
    pigs = [row for row in readiness.get("pigs", []) if isinstance(row, dict)]
    matches = [row for row in pigs if subject.casefold() in _identities(row)]
    if len(matches) != 1:
        status = "animal_identity_ambiguous" if matches else "animal_identity_not_found"
        candidates = [
            {
                "pig_id": _text(row.get("pig_id")) or "Unknown",
                "tag_number": _text(row.get("tag_number")) or "Unknown",
            }
            for row in matches[:10]
        ]
        return {
            **_failure(
                status,
                (
                    "More than one pig matches. Please use one exact Pig ID."
                    if matches
                    else "I could not match that name or Pig ID to a canonical pig."
                ),
            ),
            "candidates": candidates,
        }

    pig = matches[0]
    pig_id = _text(pig.get("pig_id"))
    tag = _text(pig.get("tag_number")) or "Unknown"
    mating_rows = [
        row for row in (matings or [])
        if isinstance(row, dict)
        and pig_id in {
            _text(row.get("sow_pig_id")),
            _text(row.get("boar_pig_id")),
        }
    ]
    mating_rows.sort(
        key=lambda row: (_date(row.get("mating_date")) or date.min),
        reverse=True,
    )
    latest_mating = mating_rows[0] if mating_rows else None
    pregnancy_rows = [
        row for row in mating_rows
        if _text(row.get("sow_pig_id")) == pig_id
    ]
    pregnancy_subject_eligible = (
        _text(pig.get("sex")).casefold() == "female"
        and bool(pregnancy_rows)
    )
    pregnancy = resolve_pregnancy_evidence(
        pregnancy_rows if pregnancy_subject_eligible else [],
        today=today,
    )
    if not pregnancy_subject_eligible and mating_rows:
        pregnancy.update({
            "state": "not_applicable",
            "derived_status": "",
            "missing_supporting_evidence": [],
        })
    weight_date = _date(pig.get("latest_weight_date"))
    days_since_weight = (
        (today - weight_date).days if weight_date is not None else None
    )
    weight_stale = (
        days_since_weight is None or days_since_weight > STALE_WEIGHT_DAYS
    )
    worklist_case = _worklist_case(worklist, pig_id)
    worklist_task = _worklist_task(worklist, pig_id)
    missing = _missing_evidence(
        pig, latest_mating, weight_date, weight_stale, worklist_case, pregnancy
    )
    breeding_status = _breeding_status(
        pig, latest_mating, worklist_case, pregnancy
    )
    recommendation = _recommendation(
        pig, worklist_task, worklist_case, pregnancy
    )
    breeding_exclusion = _breeding_exclusion(pig)
    facts = {
        "identity": {
            "tag_number": tag,
            "pig_id": pig_id or "Unknown",
            "sex": _known(pig.get("sex")),
            "lifecycle_status": _known(pig.get("status")),
            "on_farm": _known(pig.get("on_farm")),
            "purpose": _known(pig.get("purpose")),
        },
        "latest_weight": {
            "weight_kg": pig.get("latest_weight_kg")
            if pig.get("latest_weight_kg") not in ("", None)
            else "Unknown",
            "evidence_date": weight_date.isoformat() if weight_date else "Unknown",
            "observation_time": "Unknown",
            "days_old": days_since_weight if days_since_weight is not None else "Unknown",
            "stale": weight_stale,
        },
        "breeding": {
            "status": breeding_status,
            "mating_event_count": len(mating_rows),
            "latest_mating_date": (
                _date(latest_mating.get("mating_date")).isoformat()
                if latest_mating and _date(latest_mating.get("mating_date"))
                else "Unknown"
            ),
            "latest_mating_status": (
                _known(latest_mating.get("mating_status"))
                if latest_mating else "Unknown"
            ),
            "pregnancy_check_result": (
                pregnancy["governed_result"]
            ),
            "pregnancy_result_date": pregnancy["result_date"],
            "pregnancy_result_time": pregnancy["result_time"],
            "pregnancy_check_method": pregnancy["method"],
            "pregnancy_check_assessor": pregnancy["assessor"],
            "pregnancy_evidence_freshness": pregnancy["freshness"],
            "pregnancy_currently_applicable": pregnancy[
                "currently_applicable"
            ],
            "pregnancy_evidence_state": pregnancy["state"],
            "readiness_bucket": _known(pig.get("readiness_bucket")),
            "readiness_reason": _known(pig.get("readiness_reason")),
            "readiness_currently_applicable": not bool(breeding_exclusion),
            "readiness_applicability_reason": (
                breeding_exclusion or "Canonical lifecycle permits evaluation"
            ),
        },
    }
    answer = _compose(tag, facts, missing, recommendation)
    fingerprint = hashlib.sha256(
        repr((CONTRACT_VERSION, pig_id, facts, missing, recommendation)).encode()
    ).hexdigest()[:24]
    return {
        "success": True,
        "status": "herd_question_answer_ready",
        "contract_version": CONTRACT_VERSION,
        "subject": {"tag_number": tag, "pig_id": pig_id},
        "facts": facts,
        "missing_or_stale_evidence": missing,
        "recommendation": recommendation,
        "answer": answer,
        "evidence_provenance": [
            {
                "source": "supabase_allocation_readiness",
                "authority": "canonical",
                "observed_date": _known(readiness.get("generated_date")),
            },
            {
                "source": "supabase_mating_events",
                "authority": "canonical",
                "latest_evidence_date": facts["breeding"]["latest_mating_date"],
            },
            {
                "source": "herdmaster_breeding_operating_loop",
                "authority": "calculated_read_only",
                "observed_at": _known((worklist or {}).get("generated_at")),
            },
        ],
        "response_fingerprint": fingerprint,
        "read_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
        "confirmation_required": False,
    }


def _subject(question):
    text = " ".join(str(question or "").split())
    for pattern in _SUBJECT_PATTERNS:
        match = pattern.search(text)
        if match:
            subject = match.group(1).strip(" '\"")
            subject = re.sub(r"^(?:pig|sow|boar|gilt)\s+", "", subject, flags=re.I)
            if subject.casefold() in {
                "the latest recorded",
                "the pig",
                "this pig",
                "her",
                "him",
                "it",
            }:
                continue
            return subject
    return ""


def _identities(row):
    return {
        _text(row.get(key)).casefold()
        for key in ("pig_id", "tag_number", "name", "pig_name")
        if _text(row.get(key))
    }


def _worklist_case(worklist, pig_id):
    return next(
        (
            row for row in (worklist or {}).get("cases", [])
            if isinstance(row, dict) and _text(row.get("pig_id")) == pig_id
        ),
        None,
    )


def _worklist_task(worklist, pig_id):
    return next(
        (
            row for row in (worklist or {}).get("tasks", [])
            if isinstance(row, dict) and _text(row.get("pig_id")) == pig_id
        ),
        None,
    )


def _breeding_status(pig, mating, case, pregnancy):
    exclusion = _breeding_exclusion(pig)
    if exclusion:
        return exclusion
    if mating and pregnancy.get("derived_status"):
        return _text(pregnancy["derived_status"])
    if case:
        classification = case.get("classification") or {}
        value = (
            classification.get("status")
            or classification.get("state")
            or classification.get("label")
        )
        if value:
            return _text(value)
    if mating:
        if _text(mating.get("is_open")).casefold() == "yes":
            return _known(mating.get("mating_status"), "Active mating")
        return _known(mating.get("mating_status"), "Mating history recorded")
    if _text(pig.get("purpose")).casefold() == "breeding":
        return "Breeding animal; no canonical mating event found"
    return "No current breeding status recorded"


def _missing_evidence(
    pig, mating, weight_date, weight_stale, case, pregnancy
):
    missing = []
    if weight_date is None:
        missing.append("Latest weight date is Unknown.")
    else:
        missing.append("Weight observation time is Unknown.")
        if weight_stale:
            missing.append(
                f"Latest weight is stale ({pig.get('days_since_weight', 'Unknown')} days old)."
            )
    if mating is None and _text(pig.get("purpose")).casefold() == "breeding":
        missing.append("No canonical mating chronology is recorded.")
    for item in pregnancy.get("missing_supporting_evidence") or []:
        if item not in missing:
            missing.append(item)
    if case:
        for item in (case.get("evidence") or {}).get("missing", []) or []:
            if _case_gap_is_superseded(item, pregnancy):
                continue
            wording = f"{_text(item) or 'Required breeding evidence'} is missing."
            if wording not in missing:
                missing.append(wording)
    if not _text(pig.get("readiness_bucket")):
        missing.append("Breeding/readiness classification is Unknown.")
    return missing or ["No material evidence gap was identified in the requested view."]


def _recommendation(pig, task, case, pregnancy):
    exclusion = _breeding_exclusion(pig)
    if exclusion:
        return {
            "action": (
                "review canonical lifecycle, location and purpose before any "
                "breeding plan"
            ),
            "basis": "Canonical breeding exclusion precedence",
            "priority": 5,
            "due_date": "Unknown",
            "fact": False,
        }
    classification = (case or {}).get("classification") or {}
    if _text(classification.get("state")).casefold().startswith("hold"):
        return {
            "action": _known(
                classification.get("provisional_recommendation")
                or classification.get("recommended_action")
                or classification.get("task_group"),
                "review the current breeding hold",
            ),
            "basis": "Current governed breeding hold",
            "priority": classification.get("priority", 5),
            "due_date": "Unknown",
            "fact": False,
        }
    pregnancy_action = pregnancy_recommendation(pregnancy)
    if pregnancy_action and pregnancy.get("state") in {
        "pregnant",
        "not_pregnant",
        "conflicting",
        "historical",
        "unattributed",
    }:
        state = pregnancy.get("state")
        return {
            "action": pregnancy_action,
            "basis": "Canonical pregnancy evidence precedence",
            "priority": (
                10 if state == "conflicting" else
                15 if state == "not_pregnant" else
                35 if state == "pregnant" else 18
            ),
            "due_date": "Unknown",
            "fact": False,
        }
    if task:
        return {
            "action": _known(
                task.get("action") or task.get("task_group"),
                "Complete the current breeding worklist task.",
            ),
            "basis": "Current HERDMASTER breeding worklist",
            "priority": task.get("priority", "Unknown"),
            "due_date": _known(task.get("due_date")),
            "fact": False,
        }
    if case:
        action = (
            classification.get("provisional_recommendation")
            or classification.get("recommended_action")
            or classification.get("task_group")
        )
        if action:
            return {
                "action": _text(action),
                "basis": "Current HERDMASTER breeding case",
                "priority": classification.get(
                    "priority", "Not on current worklist"
                ),
                "due_date": "Unknown",
                "fact": False,
            }
    if pregnancy_action and pregnancy.get("state") == "no_governed_result":
        return {
            "action": pregnancy_action,
            "basis": "Canonical pregnancy evidence precedence",
            "priority": 18,
            "due_date": "Unknown",
            "fact": False,
        }
    return {
        "action": _known(
            pig.get("recommended_action"),
            "Review the current evidence before making a breeding decision.",
        ),
        "basis": "Canonical allocation/readiness model",
        "priority": "Not on current worklist",
        "due_date": "Unknown",
        "fact": False,
    }


def _breeding_exclusion(pig):
    lifecycle = _text(pig.get("status")).casefold()
    on_farm = _text(pig.get("on_farm")).casefold()
    purpose = _text(pig.get("purpose")).casefold().replace(" ", "_")
    if lifecycle in {"retired", "sold", "dead", "removed", "slaughtered"}:
        return "Not currently eligible for breeding: lifecycle excludes breeding"
    if on_farm in {"no", "false", "0"}:
        return "Not currently eligible for breeding: animal is not on farm"
    if purpose in {"retired", "sale", "meat", "not_for_breeding"}:
        return "Not currently eligible for breeding: purpose excludes breeding"
    return ""


def _case_gap_is_superseded(item, pregnancy):
    text = _text(item).casefold()
    return (
        pregnancy.get("state") in {"pregnant", "not_pregnant"}
        and "pregnan" in text
    )


def _compose(tag, facts, missing, recommendation):
    identity = facts["identity"]
    weight = facts["latest_weight"]
    breeding = facts["breeding"]
    weight_text = (
        "Unknown"
        if weight["weight_kg"] == "Unknown"
        else f"{weight['weight_kg']:g} kg"
        if isinstance(weight["weight_kg"], (int, float))
        else f"{weight['weight_kg']} kg"
    )
    return (
        f"Facts — {tag} ({identity['pig_id']}): lifecycle "
        f"{identity['lifecycle_status']}; purpose {identity['purpose']}. "
        f"Latest recorded weight {weight_text}, evidence date "
        f"{weight['evidence_date']}, observation time Unknown. Breeding status: "
        f"{breeding['status']}. Latest mating date: "
        f"{breeding['latest_mating_date']}; pregnancy-check result: "
        f"{breeding['pregnancy_check_result']}; result date: "
        f"{breeding['pregnancy_result_date']}; method: "
        f"{breeding['pregnancy_check_method']}; assessor: "
        f"{breeding['pregnancy_check_assessor']}; observation time: "
        f"{breeding['pregnancy_result_time']}; freshness: "
        f"{breeding['pregnancy_evidence_freshness']}.\n\n"
        f"Missing or stale evidence — {' '.join(missing)}\n\n"
        f"Recommendation — {recommendation['action']} "
        f"(basis: {recommendation['basis']}; priority: "
        f"{recommendation['priority']}; due date: "
        f"{recommendation['due_date']}). No farm record was changed."
    )


def _known(value, fallback="Unknown"):
    return _text(value) or fallback


def _text(value):
    return str(value or "").strip()


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _failure(status, clarification):
    return {
        "success": False,
        "status": status,
        "clarification": clarification,
        "read_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }
