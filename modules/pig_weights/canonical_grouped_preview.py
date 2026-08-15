"""Pure canonical preview contract for grouped weights and optional movements.

This module has no database, network, provider, Telegram or Sheets imports.  It
normalizes already-prepared input against caller-supplied canonical snapshots;
it never loads evidence and never executes the preview.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


CONTRACT_VERSION = "canonical_grouped_weight_movement_preview_v1"
PROTECTED_ACTION_KIND = "grouped_weights"
SUPPORTED_CHANNELS = frozenset({"application_typed", "oom_typed", "browser_voice_prepared_text"})
_FACT = re.compile(
    r"(?:^|(?<=[\n,;.]))\s*(?:(?:pig|vark)\s+)?"
    r"(?P<identity>[^\W_](?:[^\W_]|-)*)\s*(?:-|:|weigh(?:ed|s)?\s+)?\s*"
    r"(?P<weight>\d+(?:[.,]\d+)?)\s*kg\b",
    re.IGNORECASE,
)
_MOVE = re.compile(
    r"\b(?:all\s+)?(?:were\s+)?(?:moved|move)\s+to\s+(?:pen\s*:?)?\s*"
    r"(?P<pen>[A-Za-z0-9][A-Za-z0-9-]*)\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def preview_application_typed(payload: Mapping, *, pigs: Sequence[Mapping], pens: Sequence[Mapping]):
    """Normalize explicit application rows without reading or writing state."""
    if not isinstance(payload, Mapping):
        return _failure("application_payload_invalid")
    facts = payload.get("rows")
    return _preview(
        channel="application_typed",
        facts=facts,
        effective_date=payload.get("effective_date") or payload.get("weight_date"),
        destination_pen=payload.get("destination_pen") or payload.get("movement_pen"),
        pigs=pigs,
        pens=pens,
    )


def preview_prepared_owner_text(
    text: str,
    *,
    channel: str,
    effective_date: str | None,
    pigs: Sequence[Mapping],
    pens: Sequence[Mapping],
):
    """Normalize OOM typed or prepared browser-voice text.

    Telegram voice is deliberately unsupported until transcript routing is
    proven independently.
    """
    if channel not in {"oom_typed", "browser_voice_prepared_text"}:
        return _failure("channel_not_authorized")
    raw = str(text or "")
    supplied_dates = sorted(set(_ISO_DATE.findall(raw)))
    if len(supplied_dates) > 1:
        return _failure("effective_date_ambiguous")
    facts = [
        {"identity": match.group("identity"), "weight_kg": match.group("weight")}
        for match in _FACT.finditer(raw)
    ]
    movement_matches = [match.group("pen") for match in _MOVE.finditer(raw)]
    if len({value.casefold() for value in movement_matches}) > 1:
        return _failure("destination_pen_ambiguous")
    return _preview(
        channel=channel,
        facts=facts,
        effective_date=supplied_dates[0] if supplied_dates else effective_date,
        destination_pen=movement_matches[0] if movement_matches else None,
        pigs=pigs,
        pens=pens,
    )


def _preview(*, channel, facts, effective_date, destination_pen, pigs, pens):
    if channel not in SUPPORTED_CHANNELS:
        return _failure("channel_not_authorized")
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes)) or not facts:
        return _failure("grouped_weight_facts_required")
    canonical_date = _date(effective_date)
    if canonical_date is None:
        return _failure("effective_date_invalid")
    if not _valid_snapshot(pigs) or not _valid_snapshot(pens):
        return _failure("canonical_identity_snapshot_invalid")

    shared_destination = _resolve_pen(destination_pen, pens)
    if shared_destination[0] is False:
        return _failure(shared_destination[1])

    rows = []
    seen = set()
    for fact in facts:
        if not isinstance(fact, Mapping):
            return _failure("grouped_weight_fact_invalid")
        supplied_identity = str(
            fact.get("identity") or fact.get("pig_id") or fact.get("tag_number") or fact.get("name") or ""
        ).strip()
        pig = _resolve_pig(supplied_identity, pigs)
        if pig[0] is False:
            return _failure(pig[1])
        record = pig[1]
        pig_id = str(record.get("pig_id") or "").strip()
        if pig_id in seen:
            return _failure("duplicate_animal_identity")
        seen.add(pig_id)
        explicit_destination = (
            fact.get("destination_pen") or fact.get("moved_to_pen_id")
            if channel == "application_typed" else None
        )
        row_destination_value = explicit_destination if explicit_destination not in (None, "") else destination_pen
        destination = _resolve_pen(row_destination_value, pens)
        if destination[0] is False:
            return _failure(destination[1])
        destination_pen_id, destination_pen_label = destination[1], destination[2]
        raw_weight = fact.get("weight_kg")
        weight = (
            "Unknown"
            if channel == "application_typed" and (raw_weight in (None, "") or str(raw_weight).strip().casefold() == "unknown")
            else _weight(raw_weight)
        )
        if weight is None or (weight == "Unknown" and destination_pen_id == "Unknown"):
            return _failure("weight_invalid")
        current_pen_id = _unknown(record.get("current_pen_id") or record.get("pen_id"))
        rows.append({
            "pig_id": pig_id,
            "tag_number": _unknown(record.get("tag_number") or record.get("name")),
            "weight_kg": weight,
            "current_pen_id": current_pen_id,
            "moved_to_pen_id": destination_pen_id,
            "moved_to_pen_label": destination_pen_label,
            "condition_notes": _unknown(fact.get("condition_notes")),
        })

    canonical = {
        "contract_version": CONTRACT_VERSION,
        "effective_date": canonical_date,
        "rows": rows,
        "confirmation_required": True,
    }
    digest_material = {"kind": PROTECTED_ACTION_KIND, "payload": canonical}
    encoded = json.dumps(digest_material, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return {
        "success": True,
        "status": "canonical_grouped_preview_ready",
        **canonical,
        "preview_digest": hashlib.sha256(encoded).hexdigest(),
        "writes_performed": False,
        "database_calls": 0,
        "provider_calls": 0,
        "telegram_calls": 0,
        "google_sheets_calls": 0,
        "farm_writes": 0,
    }


def _resolve_pig(identity, pigs):
    if not identity:
        return False, "animal_identity_required"
    needle = identity.casefold()
    matches = [pig for pig in pigs if needle in _identity_values(pig)]
    if len(matches) != 1:
        return False, "animal_identity_ambiguous" if matches else "animal_identity_not_found"
    pig = matches[0]
    if not str(pig.get("pig_id") or "").strip():
        return False, "opaque_animal_identity_missing"
    active = str(pig.get("status") or pig.get("lifecycle_status") or "").casefold() == "active"
    on_farm = str(pig.get("on_farm") or "").casefold() in {"true", "yes", "1"}
    if not active or not on_farm:
        return False, "animal_not_active_on_farm"
    return True, pig


def _resolve_pen(identity, pens):
    if identity in (None, "") or str(identity).strip().casefold() == "unknown":
        return True, "Unknown", "Unknown"
    needle = str(identity).strip().casefold()
    matches = [pen for pen in pens if needle in _pen_values(pen)]
    if len(matches) != 1:
        return False, "destination_pen_ambiguous" if matches else "destination_pen_invalid", "Unknown"
    pen_id = str(matches[0].get("pen_id") or matches[0].get("Pen_ID") or "").strip()
    if not pen_id:
        return False, "opaque_destination_pen_identity_missing", "Unknown"
    active_value = matches[0].get("active", matches[0].get("is_active", True))
    if str(active_value).casefold() not in {"true", "yes", "1"}:
        return False, "destination_pen_inactive", "Unknown"
    label = _unknown(matches[0].get("pen_name") or matches[0].get("Pen_Name") or matches[0].get("name"))
    return True, pen_id, label


def _identity_values(record):
    return {str(record.get(key) or "").strip().casefold() for key in ("pig_id", "tag_number", "name", "pig_name") if str(record.get(key) or "").strip()}


def _pen_values(record):
    return {str(record.get(key) or "").strip().casefold() for key in ("pen_id", "Pen_ID", "pen_name", "Pen_Name", "name") if str(record.get(key) or "").strip()}


def _weight(value):
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return format(parsed.normalize(), "f")


def _date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        return None


def _unknown(value):
    clean = str(value).strip() if value is not None else ""
    return clean or "Unknown"


def _valid_snapshot(value):
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and all(isinstance(item, Mapping) for item in value)


def _failure(status):
    return {
        "success": False,
        "status": status,
        "confirmation_required": False,
        "writes_performed": False,
        "database_calls": 0,
        "provider_calls": 0,
        "telegram_calls": 0,
        "google_sheets_calls": 0,
        "farm_writes": 0,
    }
