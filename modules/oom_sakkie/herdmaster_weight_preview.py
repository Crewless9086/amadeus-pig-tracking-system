"""Deterministic owner-only preview for conversational herd weight facts."""

import hashlib
import re
from datetime import datetime


CONTRACT_VERSION = "herdmaster_telegram_weight_preview_v1"
GROUPED_CONTRACT_VERSION = "herdmaster_telegram_grouped_weight_preview_v1"
_WEIGHT_FACT = re.compile(
    r"^\s*(?P<animal>.+?)\s+weighed\s+"
    r"(?P<weight>\d+(?:[.,]\d+)?)\s*kg\s+on\s+"
    r"(?P<date>.+?)\s*$",
    re.IGNORECASE,
)


def preview_herd_weight_fact(owner_words, readiness, preflight):
    parsed = _parse_weight_fact(owner_words)
    if not parsed["success"]:
        return parsed

    if not isinstance(readiness, dict):
        return _failure(
            "canonical_herd_identity_unavailable",
            "I received the weight update, but canonical herd identity is unavailable. Nothing was recorded.",
        )
    pigs = readiness.get("pigs")
    if (
        readiness.get("success") is not True
        or not isinstance(pigs, list)
        or any(not isinstance(pig, dict) for pig in pigs)
    ):
        return _failure(
            "canonical_herd_identity_unavailable",
            "I received the weight update, but canonical herd identity is unavailable. Nothing was recorded.",
        )
    matches = [
        pig for pig in pigs
        if _identity_values(pig) & {parsed["animal"].casefold()}
    ]
    if len(matches) != 1:
        status = "animal_identity_ambiguous" if matches else "animal_identity_not_found"
        wording = (
            "More than one current animal matches that name. Please use the exact tag."
            if matches else
            "I could not match that name to one current active/on-farm animal."
        )
        return _failure(status, wording)

    pig = matches[0]
    if (
        str(pig.get("status") or pig.get("lifecycle_status") or "").casefold()
        != "active"
        or str(pig.get("on_farm") or "").casefold() not in {"yes", "true", "1"}
    ):
        return _failure(
            "animal_not_active_on_farm",
            "That animal is not confirmed active and on-farm. Nothing was recorded.",
        )

    pig_id = str(pig.get("pig_id") or "").strip()
    tag = str(pig.get("tag_number") or pig.get("name") or "").strip()
    check, status_code = preflight({
        "weight_date": parsed["weight_date"],
        "weighed_by": "Authenticated owner via Oom Sakkie",
        "rows": [{
            "pig_id": pig_id,
            "tag_number": tag,
            "weight_kg": parsed["weight_kg"],
        }],
    })
    if status_code != 200 or check.get("accepted_count") != 1:
        return _failure(
            str(check.get("status") or check.get("error") or "weight_preflight_blocked"),
            "The canonical weight preflight did not accept this fact. Nothing was recorded.",
        )

    identity_basis = "|".join([
        CONTRACT_VERSION,
        pig_id,
        parsed["weight_date"],
        _canonical_weight(parsed["weight_kg"]),
    ])
    preview_id = "HERD-WEIGHT-PREVIEW-" + hashlib.sha256(
        identity_basis.encode("utf-8")
    ).hexdigest()[:24].upper()
    return {
        "success": True,
        "status": "weight_preview_ready",
        "contract_version": CONTRACT_VERSION,
        "preview_id": preview_id,
        "pig_id": pig_id,
        "tag_number": tag,
        "weight_kg": parsed["weight_kg"],
        "weight_date": parsed["weight_date"],
        "observation_time": None,
        "observation_time_state": "Unknown",
        "confirmation_required": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def preview_grouped_herd_weights(owner_words, *, weight_date, readiness, preflight,
                                 pen_lookup=None):
    """Resolve natural grouped weights plus one shared date and movement."""
    text = str(owner_words or "")
    pairs = re.findall(
        r"(?:^|(?<=[\n,;.]))\s*(?:(?:pig|vark)\s+)?"
        r"([A-Za-z0-9-]+)\s*(?:-|:|weigh(?:ed|s)?\s+)?\s*"
        r"(\d+(?:[.,]\d+)?)\s*kg\b", text, flags=re.I)
    if not pairs:
        return _failure("grouped_weight_facts_not_found", "Send each pig tag or name followed by its kg.")
    explicit_dates = sorted(set(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)))
    if len(explicit_dates) > 1:
        return _failure("weight_date_ambiguous", "More than one weight date was supplied.")
    try:
        canonical_date = datetime.fromisoformat(
            explicit_dates[0] if explicit_dates else str(weight_date)).date().isoformat()
    except (TypeError, ValueError):
        return _failure("weight_date_needs_clarification", "The observation date is not safely known.")
    pigs = readiness.get("pigs") if isinstance(readiness, dict) and readiness.get("success") is True else None
    if not isinstance(pigs, list) or any(not isinstance(pig, dict) for pig in pigs):
        return _failure("canonical_herd_identity_unavailable", "Canonical herd identity is unavailable.")
    pen_match = re.search(
        r"\b(?:all\s+)?(?:were\s+)?(?:moved|move)\s+to\s+(?:pen\s*:?)?\s*([A-Za-z0-9-]+)\b",
        text, re.I)
    pen_label = pen_match.group(1) if pen_match else ""
    moved_to_pen_id = ""
    if pen_label:
        candidates = list((pen_lookup or {}).get(pen_label.casefold(), []))
        if len(candidates) != 1:
            return _failure("movement_pen_ambiguous", f"I could not resolve pen {pen_label} exactly once.")
        moved_to_pen_id = str(candidates[0])
    rows = []
    resolved_ids = set()
    for label, raw_weight in pairs:
        matches = [pig for pig in pigs if _identity_values(pig) & {label.casefold()}]
        if len(matches) != 1:
            return _failure("animal_identity_ambiguous" if matches else "animal_identity_not_found",
                            f"I could not resolve {label} to exactly one active on-farm pig.")
        pig = matches[0]
        if (str(pig.get("status") or pig.get("lifecycle_status") or "").casefold() != "active"
                or str(pig.get("on_farm") or "").casefold() not in {"yes", "true", "1"}):
            return _failure("animal_not_active_on_farm", f"{label} is not confirmed active and on-farm.")
        pig_id = str(pig.get("pig_id") or "")
        if pig_id in resolved_ids:
            return _failure("duplicate_animal_identity", f"{label} appears more than once.")
        resolved_ids.add(pig_id)
        rows.append({"pig_id": pig_id,
                     "tag_number": str(pig.get("tag_number") or pig.get("name") or label),
                     "label": label, "weight_kg": float(raw_weight.replace(",", ".")),
                     "current_pen_id": str(pig.get("current_pen_id") or pig.get("pen_id") or ""),
                     "moved_to_pen_id": moved_to_pen_id,
                     "moved_to_pen_label": pen_label})
    check, status = preflight({"weight_date": canonical_date,
        "weighed_by": "Authenticated owner via Oom Sakkie",
        "rows": [{key: row[key] for key in ("pig_id", "tag_number", "weight_kg",
                  "current_pen_id", "moved_to_pen_id")} for row in rows]})
    if status != 200 or check.get("accepted_count") != len(rows):
        return _failure(str(check.get("status") or check.get("error") or "weight_preflight_blocked"),
                        "The canonical grouped-weight preflight did not accept every mapping.")
    basis = {"contract": GROUPED_CONTRACT_VERSION, "weight_date": canonical_date,
             "rows": [(row["pig_id"], _canonical_weight(row["weight_kg"]),
                       row["moved_to_pen_id"]) for row in rows]}
    preview_id = "HERD-WEIGHT-GROUP-PREVIEW-" + hashlib.sha256(
        repr(basis).encode("utf-8")).hexdigest()[:24].upper()
    return {"success": True, "status": "grouped_weight_preview_ready",
        "contract_version": GROUPED_CONTRACT_VERSION, "preview_id": preview_id,
        "weight_date": canonical_date, "rows": rows, "movement_pen_id": moved_to_pen_id,
        "movement_pen_label": pen_label, "row_count": len(rows), "confirmation_required": True,
        "writes_performed": False, "protected_actions_performed": False}


def _parse_weight_fact(owner_words):
    text = " ".join(str(owner_words or "").split())
    match = _WEIGHT_FACT.fullmatch(text)
    if not match:
        return _failure(
            "weight_fact_needs_clarification",
            "Please state one animal, weight in kg, and the observation date.",
        )
    animal = match.group("animal").strip()
    try:
        weight = float(match.group("weight").replace(",", "."))
    except ValueError:
        weight = 0
    if weight <= 0:
        return _failure("weight_invalid", "Weight must be greater than zero.")
    supplied_weekday = None
    weekday_match = re.match(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+",
        match.group("date").strip(),
        flags=re.IGNORECASE,
    )
    if weekday_match:
        supplied_weekday = weekday_match.group(1).casefold()
    date_text = re.sub(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+",
        "",
        match.group("date").strip(),
        flags=re.IGNORECASE,
    )
    date_text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", date_text, flags=re.I)
    try:
        parsed_date = datetime.strptime(date_text, "%d %B %Y").date()
    except ValueError:
        return _failure(
            "weight_date_needs_clarification",
            "I could not interpret the weight date safely. Nothing was recorded.",
        )
    if supplied_weekday and parsed_date.strftime("%A").casefold() != supplied_weekday:
        return _failure(
            "weight_date_weekday_conflict",
            "The stated weekday does not match the calendar date. Please correct the date before previewing it.",
        )
    return {
        "success": True,
        "animal": animal,
        "weight_kg": weight,
        "weight_date": parsed_date.isoformat(),
    }


def _identity_values(pig):
    return {
        str(pig.get(key) or "").strip().casefold()
        for key in ("tag_number", "name", "pig_name")
        if str(pig.get(key) or "").strip()
    }


def _canonical_weight(value):
    return ("%.3f" % float(value)).rstrip("0").rstrip(".")


def _failure(status, clarification):
    return {
        "success": False,
        "status": status,
        "clarification": clarification,
        "writes_performed": False,
        "protected_actions_performed": False,
    }
