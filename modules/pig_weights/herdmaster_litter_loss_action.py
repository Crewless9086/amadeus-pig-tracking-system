"""Channel-invariant preview for exact active-litter piglet losses."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Mapping


ACTION_KIND = "herdmaster_record_litter_piglet_deaths"
CONTRACT_VERSION = "herdmaster_litter_piglet_deaths_v2"


def prepare_litter_loss_preview(
    facts: Mapping,
    canonical: Mapping,
    *,
    reserved_pig_ids=(),
) -> dict:
    if not isinstance(facts, Mapping) or not isinstance(canonical, Mapping):
        return _hold("canonical_litter_loss_evidence_required")
    source_event_ids = sorted(
        {
            str(value).strip()
            for value in facts.get("source_event_ids") or []
            if str(value).strip()
        }
    )
    if not source_event_ids:
        return _hold("litter_loss_source_event_identity_required")
    sow = _resolve_sow(facts.get("sow_ref"), canonical.get("animals") or [])
    explicit_litter = str(facts.get("litter_ref") or "").strip()
    active = [
        dict(row)
        for row in canonical.get("litters") or []
        if str(row.get("litter_status") or row.get("status") or "").casefold()
        == "active"
        and (
            (sow and str(row.get("sow_pig_id") or "") == sow["pig_id"])
            or (
                explicit_litter
                and str(row.get("litter_id") or "").casefold()
                == explicit_litter.casefold()
            )
        )
    ]
    if explicit_litter:
        active = [
            row
            for row in active
            if str(row.get("litter_id") or "").casefold()
            == explicit_litter.casefold()
        ]
    if len(active) != 1:
        return _hold("exactly_one_active_litter_required")
    litter = active[0]
    if not sow:
        sow = _resolve_sow(
            litter.get("sow_pig_id"), canonical.get("animals") or []
        )
    if not sow:
        return _hold("sow_identity_required")

    event_date = _date(facts.get("event_date"))
    if not event_date:
        return _hold(
            "litter_loss_event_date_required",
            question="On which date did this piglet loss happen?",
        )
    count = _count(facts.get("count"))
    if count is None or count <= 0:
        return _hold("positive_litter_loss_count_required")
    reserved = {str(value) for value in reserved_pig_ids}
    detail = litter.get("detail") if isinstance(litter.get("detail"), Mapping) else {}
    eligible = sorted(
        [
            {
                "pig_id": str(row.get("pig_id") or "").strip(),
                "tag_number": str(row.get("tag_number") or "").strip(),
                "name": str(row.get("name") or row.get("pig_name") or "").strip(),
                "sex": str(row.get("sex") or "").strip(),
            }
            for row in detail.get("piglets") or []
            if str(row.get("pig_id") or "").strip()
            and str(row.get("status") or "").casefold() == "active"
            and row.get("on_farm") in (True, "Yes", "yes")
            and str(row.get("pig_id") or "").strip() not in reserved
        ],
        key=lambda row: (row["tag_number"], row["pig_id"]),
    )
    if len(eligible) < count:
        return _hold(
            "insufficient_unreserved_active_piglets",
            available_count=len(eligible),
            required_count=count,
        )

    male = _count(facts.get("male_count"))
    female = _count(facts.get("female_count"))
    sex_unknown = facts.get("sex_unknown") is True
    if male is None and female is None and not sex_unknown:
        return _hold(
            "litter_loss_sex_split_required",
            question=(
                f"Of the {count} piglet{'s' if count != 1 else ''} that died in "
                f"{sow.get('name') or sow.get('tag_number') or 'this sow'}'s "
                "litter, how many were male and how many female? If the sex is "
                "unknown, say unknown."
            ),
            known_count=count,
            known_event_date=event_date.isoformat(),
            known_litter_id=str(litter.get("litter_id") or ""),
        )
    if (male is None) != (female is None):
        return _hold("complete_litter_loss_sex_split_required")
    if male is not None and male + female != count:
        return _hold(
            "litter_loss_sex_count_conflict",
            known_count=count,
            supplied_total=male + female,
        )

    if sex_unknown:
        selected = eligible[:count]
        selection_basis = "deterministic_unknown_sex_fallback"
    else:
        selected = []
        for sex, required in (("Male", male), ("Female", female)):
            matches = [
                row for row in eligible if row["sex"].casefold() == sex.casefold()
            ]
            if len(matches) < required:
                return _hold(
                    "matching_sex_active_piglets_unavailable",
                    requested_sex=sex,
                    requested_count=required,
                    available_count=len(matches),
                )
            selected.extend(matches[:required])
        selection_basis = "canonical_matching_sex"

    material = {
        "contract_version": CONTRACT_VERSION,
        "action_kind": ACTION_KIND,
        "source_event_ids": source_event_ids,
        "sow_pig_id": sow["pig_id"],
        "sow_name": sow.get("name"),
        "sow_tag_number": sow.get("tag_number"),
        "litter_id": str(litter.get("litter_id") or ""),
        "event_date": event_date.isoformat(),
        "reason": "Unknown",
        "count": count,
        "male_count": male,
        "female_count": female,
        "sex_unknown": sex_unknown,
        "selection_basis": selection_basis,
        "selected_piglets": selected,
        "pig_ids": [row["pig_id"] for row in selected],
    }
    operation_id = "HERD-LITTER-LOSS-" + hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24].upper()
    return {
        "success": True,
        "status": "litter_piglet_deaths_preview_ready",
        "preview": {**material, "operation_id": operation_id},
        "operation_id": operation_id,
        "confirmation_required": True,
        "writes_farm_data": False,
    }


def render_litter_loss_preview(preview: Mapping) -> str:
    sow = (
        str(preview.get("sow_name") or "")
        or str(preview.get("sow_tag_number") or "")
        or "the sow"
    )
    selected = ", ".join(
        f"{row.get('tag_number') or row.get('name') or row.get('pig_id')} "
        f"({row.get('pig_id')}, {row.get('sex') or 'sex Unknown'})"
        for row in preview.get("selected_piglets") or []
    )
    split = (
        "sex Unknown, deterministic eligible selection disclosed below"
        if preview.get("sex_unknown")
        else f"{preview.get('male_count')} male and {preview.get('female_count')} female"
    )
    return (
        f"HERDMASTER protected preview: {sow}'s active litter "
        f"{preview.get('litter_id')}; {preview.get('count')} piglet loss on "
        f"{preview.get('event_date')}; {split}; reason Unknown. Exact piglets: "
        f"{selected}. Confirm only this operation."
    )


def _resolve_sow(reference, rows):
    ref = str(reference or "").strip().casefold()
    matches = [
        {
            "pig_id": str(row.get("pig_id") or "").strip(),
            "tag_number": str(row.get("tag_number") or "").strip(),
            "name": str(row.get("name") or row.get("pig_name") or "").strip(),
        }
        for row in rows
        if ref
        and ref
        in {
            str(row.get("pig_id") or "").strip().casefold(),
            str(row.get("tag_number") or "").strip().casefold(),
            str(row.get("name") or row.get("pig_name") or "").strip().casefold(),
        }
    ]
    return matches[0] if len(matches) == 1 else None


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _hold(status, **extra):
    return {
        "success": False,
        "status": status,
        "writes_farm_data": False,
        **extra,
    }
