"""Pure typed HERDMASTER farrowing/litter preview composer.

Language understanding belongs to Oom Sakkie's semantic front door.  This
module validates typed facts against canonical animals, litters and matings. It
performs no I/O and grants no mutation authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Mapping


CONTRACT_VERSION = "herdmaster_farrowing_litter_preview_v1"
ACTION_KIND = "herdmaster_record_farrowing_litter"


class FarrowingEvidenceError(ValueError):
    pass


def prepare_farrowing_litter_preview(report: Mapping, canonical: Mapping) -> dict:
    report, canonical = _map(report, "report"), _map(canonical, "canonical")
    if report.get("authenticated") is not True:
        raise FarrowingEvidenceError("authenticated_report_required")
    provider_message_id = _text(report.get("provider_message_id"))
    principal = _text(report.get("authenticated_principal_id"))
    generation = _text(canonical.get("evidence_generation"))
    if not provider_message_id or not principal or not generation:
        raise FarrowingEvidenceError("provider_principal_and_generation_required")
    facts = _map(report.get("farrowing_litter"), "farrowing_litter")
    sow = _resolve_one(facts.get("sow_ref"), canonical.get("animals") or [])
    if sow["state"] != "resolved":
        return _hold("sow_identity_required", sow=sow)
    if (sow.get("status", "").casefold() != "active"
            or sow.get("on_farm") is not True
            or sow.get("sex", "").casefold() not in {"female", "sow"}):
        return _hold("current_active_on_farm_sow_required", sow=sow)
    farrowing_date = _date(facts.get("farrowing_date"), "farrowing_date")
    counts = _counts(facts)
    if counts.get("error"):
        return _hold(counts["error"], sow=sow, counts=counts)

    existing = [dict(row) for row in canonical.get("litters") or []
                if _text(row.get("sow_pig_id")) == sow["pig_id"]
                and _date_or_none(row.get("farrowing_date")) == farrowing_date]
    correction_of = _text(facts.get("correction_of_litter_id"))
    correction_reason = _text(facts.get("correction_reason"))
    if existing and not correction_of:
        return _hold("canonical_litter_already_exists", sow=sow,
                     existing_litter_ids=sorted(_text(row.get("litter_id")) for row in existing))
    if correction_of:
        if not correction_reason:
            return _hold("litter_correction_reason_required", sow=sow)
        matching = [row for row in existing if _text(row.get("litter_id")) == correction_of]
        if len(matching) != 1:
            return _hold("litter_correction_target_invalid", sow=sow,
                         existing_litter_ids=sorted(_text(row.get("litter_id")) for row in existing))

    mating = _mating_result(sow["pig_id"], farrowing_date,
                            canonical.get("matings") or [],
                            canonical.get("animals") or [], facts)
    if mating["state"] == "multiple_candidates":
        return _hold("mating_clarification_required", sow=sow, counts=counts,
                     mating=mating,
                     question="Which mating applies: " + ", ".join(mating["candidate_mating_ids"]) + "?")

    operation_material = {
        "contract_version": CONTRACT_VERSION,
        "provider_message_id": provider_message_id,
        "principal": principal,
        "evidence_generation": generation,
        "sow_pig_id": sow["pig_id"],
        "farrowing_date": farrowing_date.isoformat(),
        "counts": counts,
        "mating": mating,
        "requested_mating_ref": _text(facts.get("mating_ref")) or None,
        "requested_father_ref": _text(facts.get("father_ref")) or None,
        "correction_of_litter_id": correction_of or None,
        "correction_reason": correction_reason or None,
    }
    operation_id = "HERD-LITTER-" + hashlib.sha256(
        json.dumps(operation_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24].upper()
    preview = {
        **operation_material,
        "operation_id": operation_id,
        "action_kind": ACTION_KIND,
        "litter_status": "Active",
        "father_pig_id": mating.get("boar_pig_id"),
        "mating_id": mating.get("mating_id"),
        "unknowns": [key for key, value in {
            "mating": mating.get("mating_id"), "father": mating.get("boar_pig_id")
        }.items() if not value],
        "piglet_identity_count": counts["born_alive"],
        "mummified_identity_count": 0,
        "stillborn_identity_count": 0,
        "writes_performed": False,
    }
    digest = hashlib.sha256(json.dumps(
        preview, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"success": True, "status": "preview_ready", "contract_version": CONTRACT_VERSION,
            "action_kind": ACTION_KIND, "operation_id": operation_id,
            "preview_sha256": digest, "preview": preview, "sow": sow,
            "counts": counts, "mating": mating, "confirmation_required": True,
            "writes_farm_data": False, "zero_io": True}


def _counts(facts):
    values = {}
    for key in ("total_born", "born_alive", "stillborn", "mummified", "died_after_live_birth"):
        value = facts.get(key)
        if value is not None and (type(value) is not int or value < 0 or value > 40):
            return {"error": "litter_count_invalid", key: value}
        values[key] = value
    if values["total_born"] is None or values["born_alive"] is None:
        return {**values, "error": "total_and_born_alive_required"}
    known_nonlive = sum(value for value in (values["stillborn"], values["mummified"]) if value is not None)
    remainder = values["total_born"] - values["born_alive"] - known_nonlive
    if remainder < 0:
        return {**values, "error": "litter_count_arithmetic_conflict"}
    missing = [key for key in ("stillborn", "mummified") if values[key] is None]
    if len(missing) == 1:
        values[missing[0]] = remainder
    elif not missing and remainder != 0:
        return {**values, "error": "litter_count_arithmetic_conflict"}
    elif len(missing) > 1 and remainder:
        return {**values, "error": "nonlive_outcome_breakdown_required"}
    else:
        for key in missing:
            values[key] = 0
    values["died_after_live_birth"] = values["died_after_live_birth"] or 0
    if values["died_after_live_birth"] > values["born_alive"]:
        return {**values, "error": "later_deaths_exceed_born_alive"}
    values["alive_now"] = values["born_alive"] - values["died_after_live_birth"]
    values["arithmetic"] = (f"{values['total_born']}={values['born_alive']}+"
                            f"{values['stillborn']}+{values['mummified']}")
    return values


def _mating_result(sow_id, farrowing_date, rows, animals, facts):
    explicit_mating, explicit_father = _text(facts.get("mating_ref")), _text(facts.get("father_ref"))
    resolved_father = None
    if explicit_father:
        father = _resolve_one(explicit_father, animals)
        eligible = (father.get("state") == "resolved"
                    and father.get("status", "").casefold() == "active"
                    and father.get("on_farm") is True
                    and father.get("sex", "").casefold() in {"male", "boar"})
        if eligible:
            resolved_father = father["pig_id"]
    candidates = []
    conflicts = []
    for raw in rows:
        row = dict(raw)
        if _text(row.get("sow_pig_id")) != sow_id or _text(row.get("linked_litter_id")):
            continue
        state = _text(row.get("outcome") or row.get("state") or row.get("status")).casefold()
        if state and state not in {"mated", "served", "exposed", "pregnant", "confirmed_pregnant", "open"}:
            continue
        mating_id = _text(row.get("mating_id"))
        mating_date = _date_or_none(row.get("mating_date"))
        start = _date_or_none(row.get("expected_farrowing_window_start"))
        end = _date_or_none(row.get("expected_farrowing_window_end"))
        compatible = bool(start and end and start <= farrowing_date <= end)
        compatible = compatible or bool(mating_date and mating_date + timedelta(days=105) <= farrowing_date <= mating_date + timedelta(days=125))
        if not compatible:
            continue
        boar = _text(row.get("boar_pig_id")) or None
        if explicit_father and (not resolved_father or not boar
                                or resolved_father.casefold() != boar.casefold()):
            conflicts.append(mating_id)
            continue
        if explicit_mating and explicit_mating.casefold() != mating_id.casefold():
            continue
        candidates.append({"mating_id": mating_id, "boar_pig_id": boar})
    if len(candidates) == 1:
        return {"state": "attributed", **candidates[0], "conflicting_mating_ids": conflicts}
    if len(candidates) > 1:
        return {"state": "multiple_candidates", "mating_id": None, "boar_pig_id": None,
                "candidate_mating_ids": sorted(row["mating_id"] for row in candidates),
                "conflicting_mating_ids": conflicts}
    return {"state": "unknown" if not conflicts else "linkage_conflict_contained",
            "mating_id": None, "boar_pig_id": None, "conflicting_mating_ids": conflicts}


def _resolve_one(reference, animals):
    ref = _text(reference).casefold()
    matches = []
    for raw in animals:
        row = dict(raw)
        identities = {_text(row.get(key)).casefold() for key in ("pig_id", "tag_number", "name")}
        if ref and ref in identities:
            matches.append(row)
    if len(matches) != 1:
        return {"state": "missing" if not matches else "ambiguous",
                "candidate_pig_ids": sorted(_text(row.get("pig_id")) for row in matches)}
    row = matches[0]
    return {"state": "resolved", "pig_id": _text(row.get("pig_id")),
            "tag_number": _text(row.get("tag_number")), "name": _text(row.get("name")),
            "status": _text(row.get("status")), "on_farm": row.get("on_farm"),
            "sex": _text(row.get("sex") or row.get("animal_type"))}


def _hold(status, **extra):
    return {"success": False, "status": status, "contract_version": CONTRACT_VERSION,
            "writes_farm_data": False, "zero_io": True, **extra}


def _map(value, label):
    if not isinstance(value, Mapping):
        raise FarrowingEvidenceError(label + "_mapping_required")
    return dict(value)


def _text(value):
    return str(value or "").strip()


def _date(value, label):
    parsed = _date_or_none(value)
    if not parsed:
        raise FarrowingEvidenceError(label + "_required_or_invalid")
    return parsed


def _date_or_none(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)) if value else None
    except ValueError:
        return None
