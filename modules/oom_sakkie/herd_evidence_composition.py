"""Pure, owner-only composition of canonical herd evidence for one animal.

This module accepts already-read canonical projections and creates a concise
answer. It performs no I/O, persistence, routing, inference-driven mutation,
or protected action.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime

from modules.pig_weights.pregnancy_evidence import resolve_pregnancy_evidence


CONTRACT_VERSION = "herdmaster_evidence_composition_v1"
WEIGHT_FRESH_DAYS = 30
LOCATION_FRESH_DAYS = 30
MEDICAL_FRESH_DAYS = 90
MAX_HISTORY_ITEMS = 5

SUPPORTED_QUESTION_CATEGORIES = (
    "weight_chronology",
    "pen_movement",
    "availability_purpose",
    "mating_litter",
    "medical_withdrawal",
    "missing_evidence_next_action",
)


def compose_herd_evidence_answer(
    question,
    *,
    authenticated_owner,
    animals,
    weight_history_by_pig=None,
    movement_history_by_pig=None,
    mating_rows=None,
    litter_rows=None,
    medical_history_by_pig=None,
    recommendation_by_pig=None,
    today=None,
):
    """Return a privacy-bounded, canonical, zero-write herd answer."""
    if authenticated_owner is not True:
        return _failure(
            "owner_authentication_required",
            "Protected herd evidence requires the authenticated owner.",
        )
    today = today or date.today()
    animal_rows = _valid_animals(animals)
    if animal_rows is None:
        return _failure(
            "canonical_identity_unavailable",
            "Canonical animal identity is unavailable.",
        )
    subject_text = _subject(question)
    if not subject_text:
        return _failure(
            "animal_identity_required",
            "Name one animal or provide one exact Pig ID.",
        )
    identity = _resolve_identity(subject_text, animal_rows)
    if not identity["success"]:
        return identity
    animal = identity["animal"]
    pig_id = _text(animal["pig_id"])
    requested = _requested_categories(question)

    weights = _subject_rows(weight_history_by_pig, pig_id, "history")
    movements = _subject_rows(movement_history_by_pig, pig_id, "history")
    medical = _subject_rows(medical_history_by_pig, pig_id, "history")
    matings = _matching_matings(mating_rows, pig_id)
    litters = _matching_litters(litter_rows, pig_id)

    facts = {
        "identity": {
            "pig_id": pig_id,
            "tag_number": _known(
                animal.get("tag_number") or animal.get("name")
            ),
            "sex": _known(animal.get("sex")),
            "lifecycle_status": _known(animal.get("status")),
        }
    }
    missing = []
    provenance = []

    if "weight_chronology" in requested:
        facts["weight_chronology"] = _weights(weights, today)
        provenance.append(_source("canonical_weight_events", weights))
        if not weights:
            missing.append("No canonical weight history is recorded.")
        elif facts["weight_chronology"]["latest_stale"]:
            missing.append("The latest weight is stale.")
        if facts["weight_chronology"]["invalid_or_future_count"]:
            missing.append(
                "Future-dated or malformed weight evidence was excluded."
            )

    if "pen_movement" in requested:
        facts["pen_movement"] = _movements(animal, movements, today)
        provenance.append(_source("canonical_location_events", movements))
        if (
            facts["pen_movement"]["current_pen_id"] == "Unknown"
            and not movements
        ):
            missing.append("Current pen and movement history are Unknown.")
        elif not movements:
            missing.append("No canonical movement chronology is recorded.")
        if facts["pen_movement"]["latest_movement_stale"]:
            missing.append("The latest movement evidence is stale.")
        if facts["pen_movement"]["invalid_or_future_count"]:
            missing.append(
                "Future-dated or malformed movement evidence was excluded."
            )

    if "availability_purpose" in requested:
        facts["availability_purpose"] = {
            "on_farm": _known(animal.get("on_farm")),
            "available": _known(
                animal.get("available")
                if animal.get("available") is not None
                else animal.get("availability")
            ),
            "purpose": _known(animal.get("purpose")),
            "as_of": _known(
                animal.get("state_date") or animal.get("updated_date")
            ),
            "clearance_inferred": False,
        }
        provenance.append(_source("canonical_current_animal_state", [animal]))
        for field, label in (
            ("on_farm", "Current farm presence"),
            ("available", "Availability"),
            ("purpose", "Purpose"),
        ):
            if facts["availability_purpose"][field] == "Unknown":
                missing.append(f"{label} is Unknown.")

    if "mating_litter" in requested:
        facts["mating_litter"] = _breeding_history(
            animal, matings, litters, today
        )
        provenance.extend((
            _source("canonical_mating_events", matings),
            _source("canonical_litters", litters),
        ))
        if not matings:
            missing.append("No canonical mating chronology is recorded.")
        if not litters:
            missing.append("No canonical litter chronology is recorded.")

    if "medical_withdrawal" in requested:
        facts["medical_withdrawal"] = _medical(medical, today)
        provenance.append(_source("canonical_medical_events", medical))
        if not medical:
            missing.append("No canonical medical history is recorded.")
        elif facts["medical_withdrawal"]["withdrawal_state"] == "Unknown":
            missing.append("Current withdrawal status is Unknown.")
        if facts["medical_withdrawal"]["latest_evidence_stale"]:
            missing.append("The latest medical evidence is stale.")
        if facts["medical_withdrawal"]["invalid_or_future_count"]:
            missing.append(
                "Future-dated or malformed medical evidence was excluded."
            )

    recommendation = _recommendation(
        pig_id, recommendation_by_pig, missing
    )
    facts["recommendation"] = recommendation
    if recommendation["source"] == "missing_evidence_fallback":
        provenance.append({
            "source": "missing_evidence_fallback",
            "authority": "derived_read_only",
            "latest_evidence_date": "Unknown",
        })

    answer = _compose(animal, facts, requested, missing)
    fingerprint = hashlib.sha256(json.dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "pig_id": pig_id,
            "requested": requested,
            "facts": facts,
            "missing": missing,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()).hexdigest()[:24]
    return {
        "success": True,
        "status": "herd_evidence_answer_ready",
        "contract_version": CONTRACT_VERSION,
        "subject": {
            "pig_id": pig_id,
            "tag_number": facts["identity"]["tag_number"],
        },
        "requested_categories": requested,
        "facts": facts,
        "missing_or_stale_evidence": missing,
        "recommendation": recommendation,
        "answer": answer,
        "evidence_provenance": provenance,
        "response_fingerprint": fingerprint,
        "read_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
        "confirmation_required": False,
    }


def _requested_categories(question):
    text = _text(question).casefold()
    if "what do you know" in text or "what is known" in text:
        return list(SUPPORTED_QUESTION_CATEGORIES)
    selected = []
    terms = {
        "weight_chronology": ("weight", "growth"),
        "pen_movement": ("pen", "movement", "moved", "location"),
        "availability_purpose": (
            "available", "availability", "on farm", "purpose", "presence"
        ),
        "mating_litter": (
            "mating", "mated", "breeding", "pregnan", "litter", "farrow"
        ),
        "medical_withdrawal": (
            "medical", "treatment", "medicine", "injury", "withdrawal"
        ),
        "missing_evidence_next_action": (
            "missing", "stale", "next", "recommend", "action", "know"
        ),
    }
    for category in SUPPORTED_QUESTION_CATEGORIES:
        if any(term in text for term in terms[category]):
            selected.append(category)
    if not selected:
        return list(SUPPORTED_QUESTION_CATEGORIES)
    if "missing_evidence_next_action" not in selected:
        selected.append("missing_evidence_next_action")
    return selected


def _weights(rows, today):
    valid, invalid_count = _dated_rows(
        rows, ("weight_date_display", "weight_date"), today
    )
    ordered = sorted(
        valid,
        key=lambda row: _date(
            row.get("weight_date_display") or row.get("weight_date")
        ) or date.min,
        reverse=True,
    )
    history = [{
        "weight_kg": (
            row.get("weight_kg")
            if isinstance(row.get("weight_kg"), (int, float))
            and not isinstance(row.get("weight_kg"), bool)
            else "Unknown"
        ),
        "evidence_date": _known(
            row.get("weight_date_display") or row.get("weight_date")
        ),
        "observation_time": _known(row.get("observation_time")),
    } for row in ordered[:MAX_HISTORY_ITEMS]]
    latest_date = _date(
        (ordered[0] or {}).get("weight_date_display")
        or (ordered[0] or {}).get("weight_date")
    ) if ordered else None
    return {
        "count": len(ordered),
        "history": history,
        "latest_stale": (
            latest_date is None or (today - latest_date).days > WEIGHT_FRESH_DAYS
        ),
        "truncated": len(ordered) > MAX_HISTORY_ITEMS,
        "invalid_or_future_count": invalid_count,
    }


def _movements(animal, rows, today):
    valid, invalid_count = _dated_rows(
        rows, ("move_date_display", "move_date"), today
    )
    ordered = sorted(
        valid,
        key=lambda row: _date(
            row.get("move_date_display") or row.get("move_date")
        ) or date.min,
        reverse=True,
    )
    latest_date = _date(
        (ordered[0] or {}).get("move_date_display")
        or (ordered[0] or {}).get("move_date")
    ) if ordered else None
    return {
        "current_pen_id": _known(
            animal.get("current_pen_id") or animal.get("current_pen_name")
        ),
        "history": [{
            "evidence_date": _known(
                row.get("move_date_display") or row.get("move_date")
            ),
            "from_pen": _known(
                row.get("from_pen_name") or row.get("from_pen_id")
            ),
            "to_pen": _known(
                row.get("to_pen_name") or row.get("to_pen_id")
            ),
            "reason": _known(row.get("reason_for_move")),
        } for row in ordered[:MAX_HISTORY_ITEMS]],
        "latest_movement_stale": bool(
            latest_date
            and (today - latest_date).days > LOCATION_FRESH_DAYS
        ),
        "truncated": len(ordered) > MAX_HISTORY_ITEMS,
        "invalid_or_future_count": invalid_count,
    }


def _breeding_history(animal, matings, litters, today):
    sex = _text(animal.get("sex")).casefold()
    role = "sow" if sex == "female" else "boar" if sex == "male" else "Unknown"
    ordered_matings = sorted(
        matings,
        key=lambda row: _date(row.get("mating_date")) or date.min,
        reverse=True,
    )
    ordered_litters = sorted(
        litters,
        key=lambda row: _date(row.get("farrowing_date")) or date.min,
        reverse=True,
    )
    sow_matings = [
        row for row in ordered_matings
        if _text(row.get("sow_pig_id")) == _text(animal["pig_id"])
    ]
    pregnancy = (
        resolve_pregnancy_evidence(sow_matings, today=today)
        if role == "sow"
        else {
            "state": "not_applicable",
            "derived_status": "Pregnancy applies only to the canonical sow",
            "currently_applicable": False,
            "governed_result": "Unknown",
        }
    )
    return {
        "animal_role": role,
        "mating_count": len(ordered_matings),
        "matings": [{
            "mating_date": _known(row.get("mating_date")),
            "role": (
                "sow" if _text(row.get("sow_pig_id")) == _text(animal["pig_id"])
                else "boar"
            ),
            "counterpart_pig_id": _known(
                row.get("boar_pig_id")
                if _text(row.get("sow_pig_id")) == _text(animal["pig_id"])
                else row.get("sow_pig_id")
            ),
            "status": _known(row.get("mating_status")),
        } for row in ordered_matings[:MAX_HISTORY_ITEMS]],
        "pregnancy_evidence": pregnancy,
        "litter_count": len(ordered_litters),
        "litters": [{
            "litter_id": _known(row.get("litter_id")),
            "farrowing_date": _known(row.get("farrowing_date")),
            "role": (
                "dam" if _text(row.get("sow_pig_id")) == _text(animal["pig_id"])
                else "sire" if _text(row.get("boar_pig_id")) == _text(animal["pig_id"])
                else "piglet"
            ),
            "born_alive": row.get("born_alive", "Unknown"),
            "weaned_count": row.get("weaned_count", "Unknown"),
            "status": _known(row.get("litter_status")),
        } for row in ordered_litters[:MAX_HISTORY_ITEMS]],
        "protected_actions_performed": False,
    }


def _medical(rows, today):
    valid, invalid_count = _dated_rows(
        rows, ("treatment_date_display", "treatment_date"), today
    )
    ordered = sorted(
        valid,
        key=lambda row: _date(
            row.get("treatment_date_display") or row.get("treatment_date")
        ) or date.min,
        reverse=True,
    )
    active_ends = [
        parsed for parsed in (
            _date(row.get("withdrawal_end_date")) for row in ordered
        )
        if parsed and parsed >= today
    ]
    unknown_withdrawal = any(
        (
            row.get("withdrawal_days") not in (None, "")
            and not _date(row.get("withdrawal_end_date"))
        )
        or (
            row.get("withdrawal_days") in (None, "")
            and not _date(row.get("withdrawal_end_date"))
        )
        for row in ordered
    )
    state = (
        "Active hold" if active_ends
        else "Unknown" if unknown_withdrawal
        else (
            "No current dated hold identified; withdrawal clearance not established"
            if ordered else "Unknown"
        )
    )
    latest_date = _date(
        (ordered[0] or {}).get("treatment_date_display")
        or (ordered[0] or {}).get("treatment_date")
    ) if ordered else None
    return {
        "event_count": len(ordered),
        "latest_treatment": ({
            "evidence_date": _known(
                ordered[0].get("treatment_date_display")
                or ordered[0].get("treatment_date")
            ),
            "type": _known(ordered[0].get("treatment_type")),
            "reason": _known(ordered[0].get("reason_for_treatment")),
            "follow_up_required": _known(
                ordered[0].get("follow_up_required")
            ),
            "follow_up_date": _known(ordered[0].get("follow_up_date")),
        } if ordered else "Unknown"),
        "withdrawal_state": state,
        "withdrawal_end_date": (
            max(active_ends).isoformat() if active_ends else "Unknown"
        ),
        "latest_evidence_stale": bool(
            latest_date
            and (today - latest_date).days > MEDICAL_FRESH_DAYS
        ),
        "clearance_inferred": False,
        "medical_action_performed": False,
        "invalid_or_future_count": invalid_count,
    }


def _recommendation(pig_id, recommendations, missing):
    supplied = (
        recommendations.get(pig_id)
        if isinstance(recommendations, dict) else None
    )
    if isinstance(supplied, dict) and _text(supplied.get("next_action")):
        next_action = _text(supplied["next_action"])
        protected_words = (
            "mate", "medicat", "treat", "move ", "transfer", "retire",
            "sell", "slaughter", "mark available", "change purpose",
        )
        return {
            "status": _known(supplied.get("status")),
            "reason": _known(supplied.get("reason") or supplied.get("basis")),
            "next_action": next_action,
            "source": "canonical_herdmaster_recommendation",
            "protected_action_requires_approval": bool(
                supplied.get("protected_action_requires_approval")
            ) or any(word in next_action.casefold() for word in protected_words),
        }
    prioritized = sorted(missing, key=_missing_risk_key)
    return {
        "status": "Evidence review needed" if missing else "No action due",
        "reason": (
            prioritized[0] if prioritized else "No supported evidence gap found."
        ),
        "next_action": (
            f"Review: {prioritized[0]}" if prioritized
            else "Continue routine evidence collection."
        ),
        "source": "missing_evidence_fallback",
        "protected_action_requires_approval": False,
    }


def _compose(animal, facts, requested, missing):
    tag = _known(animal.get("tag_number") or animal.get("name"))
    pig_id = _text(animal["pig_id"])
    lines = [f"{tag} ({pig_id}) - canonical facts"]
    if "weight_chronology" in requested:
        weights = facts["weight_chronology"]["history"]
        lines.append(
            "Weights: " + (
                "; ".join(
                    f"{row['weight_kg']} kg on {row['evidence_date']}"
                    for row in weights
                ) if weights else "Unknown"
            )
        )
    if "pen_movement" in requested:
        pen = facts["pen_movement"]
        latest = pen["history"][0] if pen["history"] else None
        lines.append(
            f"Current pen: {pen['current_pen_id']}; "
            f"movement events: {len(pen['history'])}."
            + (
                f" Latest: {latest['from_pen']} to {latest['to_pen']} on "
                f"{latest['evidence_date']}."
                if latest else ""
            )
        )
    if "availability_purpose" in requested:
        state = facts["availability_purpose"]
        lines.append(
            f"On farm: {state['on_farm']}; available: {state['available']}; "
            f"purpose: {state['purpose']}; as of: {state['as_of']}. "
            "These are state facts, not clearance."
        )
    if "mating_litter" in requested:
        breeding = facts["mating_litter"]
        latest_mating = (
            breeding["matings"][0] if breeding["matings"] else None
        )
        latest_litter = (
            breeding["litters"][0] if breeding["litters"] else None
        )
        lines.append(
            f"Mating events: {breeding['mating_count']}; litters: "
            f"{breeding['litter_count']}; reproductive status: "
            f"{breeding['pregnancy_evidence']['derived_status']}."
            + (
                f" Latest mating: {latest_mating['mating_date']} with "
                f"{latest_mating['counterpart_pig_id']}."
                if latest_mating else ""
            )
            + (
                f" Latest farrowing: {latest_litter['farrowing_date']} "
                f"({latest_litter['litter_id']})."
                if latest_litter else ""
            )
        )
    if "medical_withdrawal" in requested:
        medical = facts["medical_withdrawal"]
        latest = medical["latest_treatment"]
        lines.append(
            f"Medical events: {medical['event_count']}; withdrawal: "
            f"{medical['withdrawal_state']}; withdrawal end: "
            f"{medical['withdrawal_end_date']}."
            + (
                f" Latest treatment: {latest['type']} on "
                f"{latest['evidence_date']}."
                if isinstance(latest, dict) else ""
            )
            + " No medical clearance is inferred."
        )
    lines.append(
        "Missing or stale evidence: "
        + ("; ".join(missing) if missing else "None identified.")
    )
    recommendation = facts["recommendation"]
    lines.append(
        f"Recommendation: {recommendation['next_action']} "
        f"(reason: {recommendation['reason']})."
    )
    if recommendation["protected_action_requires_approval"]:
        lines.append("The protected action requires separate owner approval.")
    lines.append("Read-only answer; no farm record or protected action changed.")
    return "\n".join(lines)


def _subject(question):
    text = " ".join(_text(question).split())
    patterns = (
        r"\b([A-Za-z0-9_-]+)(?:'s|’s)\s+"
        r"(?:weight|pen|movement|medical|mating|litter|availability|"
        r"purpose|withdrawal|presence)",
        r"\babout\s+([A-Za-z0-9_-]+)",
        r"\bfor\s+([A-Za-z0-9_-]+)",
        r"\bwhat (?:do you know|is known)\s+(?:about\s+)?"
        r"([A-Za-z0-9_-]+)",
        r"\bis\s+([A-Za-z0-9_-]+)\s+(?:in|on|available)",
        r"\bwas\s+([A-Za-z0-9_-]+)\s+(?:moved|mated|treated)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _text(match.group(1))
    return ""


def _resolve_identity(subject, animals):
    wanted = subject.casefold()
    matches = [
        row for row in animals
        if wanted in {
            _text(row.get(key)).casefold()
            for key in ("pig_id", "tag_number", "name", "pig_name")
            if _text(row.get(key))
        }
    ]
    if len(matches) == 1:
        return {"success": True, "animal": matches[0]}
    return {
        **_failure(
            (
                "animal_identity_ambiguous"
                if matches else "animal_identity_not_found"
            ),
            (
                "More than one canonical animal matches. Use the exact Pig ID."
                if matches
                else "No canonical animal matches that name, tag or Pig ID."
            ),
        ),
        "candidate_count": len(matches),
        "safe_disambiguation": (
            "Ask for the exact Pig ID without listing herd records."
        ),
    }


def _valid_animals(animals):
    if not isinstance(animals, list) or any(
        not isinstance(row, dict) for row in animals
    ):
        return None
    ids = [_text(row.get("pig_id")) for row in animals]
    if any(not pig_id for pig_id in ids) or len(ids) != len(set(ids)):
        return None
    return animals


def _subject_rows(mapping, pig_id, list_key):
    value = mapping.get(pig_id) if isinstance(mapping, dict) else None
    if isinstance(value, dict):
        value = value.get(list_key)
    if not isinstance(value, list):
        return []
    return [
        dict(row) for row in value
        if isinstance(row, dict)
        and _text(row.get("pig_id")) == pig_id
    ]


def _matching_matings(rows, pig_id):
    return [
        dict(row) for row in (rows or [])
        if isinstance(row, dict)
        and pig_id in {
            _text(row.get("sow_pig_id")),
            _text(row.get("boar_pig_id")),
        }
    ]


def _matching_litters(rows, pig_id):
    return [
        dict(row) for row in (rows or [])
        if isinstance(row, dict)
        and pig_id in {
            _text(row.get("sow_pig_id")),
            _text(row.get("boar_pig_id")),
            _text(row.get("pig_id")),
        }
    ]


def _source(name, rows):
    dates = []
    for row in rows:
        for key in (
            "weight_date_display", "weight_date", "move_date_display",
            "move_date", "mating_date", "farrowing_date",
            "treatment_date_display", "treatment_date",
        ):
            parsed = _date(row.get(key))
            if parsed:
                dates.append(parsed)
                break
    return {
        "source": name,
        "authority": "canonical",
        "record_count": len(rows),
        "latest_evidence_date": max(dates).isoformat() if dates else "Unknown",
    }


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _known(value, fallback="Unknown"):
    return _text(value) or fallback


def _text(value):
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value or "").strip()


def _dated_rows(rows, date_keys, today):
    valid = []
    invalid_count = 0
    for row in rows:
        parsed = next(
            (_date(row.get(key)) for key in date_keys if _date(row.get(key))),
            None,
        )
        if parsed is None or parsed > today:
            invalid_count += 1
        else:
            valid.append(row)
    return valid, invalid_count


def _missing_risk_key(item):
    text = _text(item).casefold()
    if "withdrawal" in text or "medical" in text:
        return (0, text)
    if "conflict" in text or "future" in text or "malformed" in text:
        return (1, text)
    if "farm presence" in text or "availability" in text:
        return (2, text)
    if "weight" in text:
        return (3, text)
    if "movement" in text or "pen" in text:
        return (4, text)
    return (5, text)


def _failure(status, clarification):
    return {
        "success": False,
        "status": status,
        "clarification": clarification,
        "read_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }
