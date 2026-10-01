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
    subject=None,
    language="en",
):
    """Resolve exactly one pig and compose canonical facts without writes."""
    today = today or date.today()
    subject = str(subject).strip() if subject is not None else _subject(question)
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
                    "More than one pig matches. What is the visible tag, or the name and pen, of the pig you mean?"
                    if matches
                    else "I could not match that animal. What name or visible tag is on its record?"
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
    from modules.oom_sakkie.family_presentation import animal_label
    answer = _compose(animal_label(pig, language=language), facts, missing, recommendation, language=language)
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


def _compose(tag, facts, missing, recommendation, *, language="en"):
    from modules.oom_sakkie.family_presentation import date_label, message
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
    af = str(language).casefold().startswith("af")
    dated = lambda value: 'Onbekend' if af and value == 'Unknown' else date_label(value, language=language)
    if af:
        labels = {"Active": "Aktief", "Sold": "Verkoop", "Dead": "Dood", "Removed": "Verwyder",
                  "Slaughtered": "Geslag", "Breeding": "Teel", "Sale": "Verkope", "Meat": "Vleis",
                  "Yes": "Ja", "No": "Nee", "Unknown": "Onbekend", "Pregnant": "Dragtig",
                  "Not Pregnant": "Nie dragtig nie"}
        local = lambda value: labels.get(str(value), "Onbekend")
        bullets = [f"Status: {local(identity['lifecycle_status'])}; op plaas: {local(identity['on_farm'])}; doel: {local(identity['purpose'])}.",
            f"Gewig: {'Onbekend' if weight_text == 'Unknown' else weight_text} — {dated(weight['evidence_date'])}; waarnemingstyd onbekend.",
            f"Laaste paring: {dated(breeding['latest_mating_date'])}.",
            f"Dragtigheid: {local(breeding['pregnancy_check_result'])} — {dated(breeding['pregnancy_result_date'])}."]
    else:
        bullets = [f"Status: {identity['lifecycle_status']}; on farm: {identity['on_farm']}; purpose: {identity['purpose']}.",
            f"Weight: {weight_text} — {dated(weight['evidence_date'])}; observation time Unknown.",
            ("No mating recorded." if breeding['latest_mating_date']=='Unknown' and breeding.get('mating_event_count')==0 else
             f"Breeding status: {breeding['status']}; latest mating: {dated(breeding['latest_mating_date'])}."),
            f"Pregnancy: {breeding['pregnancy_check_result']} — {dated(breeding['pregnancy_result_date'])}."]
    # Keep attributable check details and exact observation time, never a date-only
    # rendering of a timestamp. Unknown remains unknown rather than a negative.
    check_keys = ('pregnancy_check_result','pregnancy_result_date','pregnancy_check_method',
                  'pregnancy_check_assessor','pregnancy_result_time')
    absent = (breeding.get('pregnancy_evidence_state') in {'no_mating','no_governed_result','not_applicable'}
        and all(breeding.get(key) in {'',None,'Unknown'} for key in check_keys))
    if absent:
        bullets[-1] = "Geen dragtigheidskontrole is aangeteken nie." if af else "No pregnancy check is recorded."
    else:
        details = [str(breeding[key]) for key in ('pregnancy_check_method','pregnancy_check_assessor',
            'pregnancy_result_time','pregnancy_evidence_freshness') if breeding.get(key) not in {'',None,'Unknown'}]
        if details:
            bullets.append(("Kontrole (bronwoorde): " if af else "Check: ") + '; '.join(details))
    redundant = {'Latest weight date is Unknown.','Weight observation time is Unknown.',
        'No canonical mating chronology is recorded.'}
    if absent:
        redundant.add('Pregnancy-check result is Unknown.')
    gaps = [item for item in missing if item not in redundant]
    if gaps:
        bullets.append(("Ontbreek/verouderd (bronwoorde): " if af else "Missing or stale: ") + ' '.join(gaps))
    bullets.append(("Aanbeveel (bronwoorde): " if af else "Next: ") + str(recommendation['action']))
    if recommendation['priority'] not in {'Not on current worklist','Unknown','',None}:
        bullets.append(("Prioriteit: " if af else "Priority: ") + str(recommendation['priority']))
    if recommendation['due_date'] != 'Unknown':
        bullets.append(("Teen: " if af else "Due: ") + dated(recommendation['due_date']))
    return message(f"{tag} — {'aangetekende status' if af else 'recorded status'}",
        bullets=bullets, status=("Geen plaasrekord is verander nie." if af else "No farm record was changed."),
        language=language, emoji="🐷")


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
