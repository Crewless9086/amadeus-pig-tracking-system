"""Pure typed preview for a litter's governed first-treatment action."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Mapping

from modules.pig_weights.herdmaster_first_treatment_protocol import (
    FirstTreatmentProtocolError,
    resolve_first_treatment_protocol,
)

ACTION_KIND = "herdmaster_record_litter_first_treatment"
CONTRACT_VERSION = "herdmaster_litter_first_treatment_preview_v2"


class LitterTreatmentEvidenceError(ValueError):
    pass


def prepare_litter_first_treatment_preview(report: Mapping, canonical: Mapping) -> dict:
    if not isinstance(report, Mapping) or not isinstance(canonical, Mapping):
        raise LitterTreatmentEvidenceError("typed_evidence_required")
    if report.get("authenticated") is not True:
        raise LitterTreatmentEvidenceError("authenticated_report_required")
    principal = _text(report.get("authenticated_principal_id"))
    source_reference = _text(
        report.get("source_reference") or report.get("provider_message_id")
    )
    generation = _text(canonical.get("evidence_generation"))
    facts = report.get("litter_first_treatment")
    if not principal or not source_reference or not generation or not isinstance(facts, Mapping):
        raise LitterTreatmentEvidenceError(
            "principal_source_generation_and_facts_required"
        )
    sow = _resolve_one(facts.get("sow_ref"), canonical.get("animals") or [])
    explicit = _text(facts.get("litter_ref"))
    if sow.get("state") != "resolved" and explicit:
        litter_matches = [
            dict(row)
            for row in canonical.get("litters") or []
            if _text(row.get("litter_id")).casefold() == explicit.casefold()
        ]
        if len(litter_matches) == 1:
            sow = _resolve_one(
                litter_matches[0].get("sow_pig_id"), canonical.get("animals") or []
            )
    if sow.get("state") != "resolved":
        return _hold("sow_identity_required", sow=sow)
    active = [dict(row) for row in canonical.get("litters") or []
              if _text(row.get("sow_pig_id")) == sow["pig_id"]
              and _text(row.get("litter_status") or row.get("status")).casefold() == "active"]
    if explicit:
        active = [row for row in active if _text(row.get("litter_id")).casefold() == explicit.casefold()]
    if len(active) != 1:
        return _hold("exactly_one_active_litter_required",
                     candidate_litter_ids=sorted(_text(row.get("litter_id")) for row in active))
    litter = active[0]
    if litter.get("first_treatment_complete") is True or litter.get("first_treatment_partial") is True:
        return _hold("first_treatment_already_has_canonical_evidence")
    detail = litter.get("detail") if isinstance(litter.get("detail"), Mapping) else {}
    active_piglets = sorted(
        [
            {
                "pig_id": _text(row.get("pig_id")),
                "tag_number": _text(row.get("tag_number")),
                "name": _text(row.get("name") or row.get("pig_name")),
                "sex": _text(row.get("sex")),
            }
            for row in detail.get("piglets") or []
            if _text(row.get("pig_id"))
            and _text(row.get("status")).casefold() == "active"
            and row.get("on_farm") in (True, "Yes", "yes")
        ],
        key=lambda row: (row["tag_number"], row["pig_id"]),
    )
    active_pig_ids = [row["pig_id"] for row in active_piglets]
    if not active_pig_ids:
        return _hold("canonical_active_litter_membership_required")
    canonical_count = int(litter.get("active_count") or len(active_pig_ids))
    if canonical_count != len(active_pig_ids):
        return _hold("canonical_active_litter_membership_conflict")
    action_date = _date(facts.get("action_date"))
    if not action_date:
        return _hold("action_date_required", question="On which date was the first treatment given?")
    male_count = _count(facts.get("male_count"))
    female_count = _count(facts.get("female_count"))
    if male_count is None or female_count is None:
        return _hold(
            "litter_sex_counts_required",
            question=(
                f"How many of the {canonical_count} active piglets are male and "
                "how many are female?"
            ),
        )
    if male_count + female_count != canonical_count:
        return _hold(
            "litter_sex_count_conflict",
            active_piglet_count=canonical_count,
            supplied_total=male_count + female_count,
        )
    try:
        protocol = resolve_first_treatment_protocol(canonical)
    except FirstTreatmentProtocolError as exc:
        return _hold(str(exc), protocol_setting_key="herdmaster_first_treatment_protocol_v1")

    material = {"contract_version": CONTRACT_VERSION,
                "evidence_generation": generation,
                "sow_pig_id": sow["pig_id"], "sow_tag_number": sow.get("tag_number"),
                "sow_name": sow.get("name"), "litter_id": _text(litter.get("litter_id")),
                "action_date": action_date.isoformat(),
                "pig_ids": active_pig_ids, "total_count": canonical_count,
                "piglets": active_piglets,
                "male_count": male_count, "female_count": female_count,
                "protocol": protocol}
    operation_id = "HERD-LITTER-TREAT-" + hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:24].upper()
    preview = {
        **material,
        "source_reference": source_reference,
        "operation_id": operation_id,
        "action_kind": ACTION_KIND,
        "request": {
            "sow_ref": sow["pig_id"],
            "litter_ref": _text(litter.get("litter_id")),
            "action_date": action_date.isoformat(),
            "male_count": male_count,
            "female_count": female_count,
        },
    }
    return {"success": True, "status": "preview_ready", "preview": preview,
            "operation_id": operation_id, "action_kind": ACTION_KIND,
            "confirmation_required": True, "writes_farm_data": False}


def _resolve_one(reference, rows):
    ref = _text(reference).casefold()
    matches = [dict(row) for row in rows if ref and ref in {
        _text(row.get("pig_id")).casefold(), _text(row.get("tag_number")).casefold(),
        _text(row.get("name") or row.get("pig_name")).casefold()}]
    if len(matches) != 1:
        return {"state": "missing" if not matches else "ambiguous"}
    row = matches[0]
    return {"state": "resolved", "pig_id": _text(row.get("pig_id")),
            "tag_number": _text(row.get("tag_number")),
            "name": _text(row.get("name") or row.get("pig_name"))}


def _hold(status, **extra):
    return {"success": False, "status": status, "writes_farm_data": False, **extra}


def _date(value):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    try: return date.fromisoformat(_text(value))
    except ValueError: return None


def _text(value):
    return str(value or "").strip()


def _count(value):
    if type(value) is not int or value < 0:
        return None
    return value

