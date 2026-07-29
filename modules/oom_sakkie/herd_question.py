"""Deterministic, owner-only answers to ordinary questions about one pig."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime


CONTRACT_VERSION = "herdmaster_ordinary_herd_question_v1"
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
        pig, latest_mating, weight_date, weight_stale, worklist_case
    )
    breeding_status = _breeding_status(pig, latest_mating, worklist_case)
    recommendation = _recommendation(pig, worklist_task, worklist_case)
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
                _known(latest_mating.get("pregnancy_check_result"))
                if latest_mating else "Unknown"
            ),
            "readiness_bucket": _known(pig.get("readiness_bucket")),
            "readiness_reason": _known(pig.get("readiness_reason")),
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


def _breeding_status(pig, mating, case):
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


def _missing_evidence(pig, mating, weight_date, weight_stale, case):
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
    if mating is not None and not _text(mating.get("pregnancy_check_result")):
        missing.append("Pregnancy-check result is Unknown.")
    if case:
        for item in (case.get("evidence") or {}).get("missing", []) or []:
            wording = f"{_text(item) or 'Required breeding evidence'} is missing."
            if wording not in missing:
                missing.append(wording)
    if not _text(pig.get("readiness_bucket")):
        missing.append("Breeding/readiness classification is Unknown.")
    return missing or ["No material evidence gap was identified in the requested view."]


def _recommendation(pig, task, case):
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
        classification = case.get("classification") or {}
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


def _compose(tag, facts, missing, recommendation):
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
        f"Facts — {tag}: latest recorded weight {weight_text}, evidence date "
        f"{weight['evidence_date']}, observation time Unknown. Breeding status: "
        f"{breeding['status']}. Latest mating date: "
        f"{breeding['latest_mating_date']}; pregnancy-check result: "
        f"{breeding['pregnancy_check_result']}.\n\n"
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
