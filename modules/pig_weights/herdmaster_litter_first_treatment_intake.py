"""Pure typed preview for a litter's governed first-treatment action."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Mapping

ACTION_KIND = "herdmaster_record_litter_first_treatment"
CONTRACT_VERSION = "herdmaster_litter_first_treatment_preview_v1"


class LitterTreatmentEvidenceError(ValueError):
    pass


def prepare_litter_first_treatment_preview(report: Mapping, canonical: Mapping) -> dict:
    if not isinstance(report, Mapping) or not isinstance(canonical, Mapping):
        raise LitterTreatmentEvidenceError("typed_evidence_required")
    if report.get("authenticated") is not True:
        raise LitterTreatmentEvidenceError("authenticated_report_required")
    principal = _text(report.get("authenticated_principal_id"))
    provider_id = _text(report.get("provider_message_id"))
    generation = _text(canonical.get("evidence_generation"))
    facts = report.get("litter_first_treatment")
    if not principal or not provider_id or not generation or not isinstance(facts, Mapping):
        raise LitterTreatmentEvidenceError("principal_provider_generation_and_facts_required")
    sow = _resolve_one(facts.get("sow_ref"), canonical.get("animals") or [])
    if sow.get("state") != "resolved":
        return _hold("sow_identity_required", sow=sow)
    active = [dict(row) for row in canonical.get("litters") or []
              if _text(row.get("sow_pig_id")) == sow["pig_id"]
              and _text(row.get("litter_status") or row.get("status")).casefold() == "active"]
    explicit = _text(facts.get("litter_ref"))
    if explicit:
        active = [row for row in active if _text(row.get("litter_id")).casefold() == explicit.casefold()]
    if len(active) != 1:
        return _hold("exactly_one_active_litter_required",
                     candidate_litter_ids=sorted(_text(row.get("litter_id")) for row in active))
    litter = active[0]
    if litter.get("first_treatment_complete") is True or litter.get("first_treatment_partial") is True:
        return _hold("first_treatment_already_has_canonical_evidence")
    male, female, total = (facts.get("male_count"), facts.get("female_count"), facts.get("total_count"))
    if any(type(value) is not int or value < 0 for value in (male, female, total)):
        return _hold("male_female_total_required")
    if male + female != total or total != int(litter.get("active_count") or -1):
        return _hold("litter_tally_conflict", active_count=litter.get("active_count"))
    action_date = _date(facts.get("action_date"))
    if not action_date:
        return _hold("action_date_required", question="On which date was the first treatment given?")
    products = []
    for key, treatment_type in (("antiparasitic_product_ref", "antiparasitic"),
                                ("deworming_product_ref", "deworming"),
                                ("vaccination_product_ref", "vaccination")):
        ref = _text(facts.get(key))
        if ref:
            found = _resolve_product(ref, canonical.get("products") or [])
            if found.get("state") != "resolved":
                return _hold("exact_treatment_product_required", question=(
                    "Which exact product, dose, route and batch did you use?"))
            products.append({"treatment_type": treatment_type, **found})
    missing = []
    if not products: missing.append("product")
    for key in ("dose", "route", "batch_lot_number"):
        if facts.get(key) in (None, ""): missing.append(key)
    if missing:
        return _hold("medical_details_required", missing=missing,
                     question="Which exact product, dose, route and batch did you use?")
    material = {"contract_version": CONTRACT_VERSION, "principal": principal,
                "provider_message_id": provider_id, "evidence_generation": generation,
                "sow_pig_id": sow["pig_id"], "sow_tag_number": sow.get("tag_number"),
                "sow_name": sow.get("name"), "litter_id": _text(litter.get("litter_id")),
                "action_date": action_date.isoformat(), "male_count": male,
                "female_count": female, "total_count": total,
                "earmarked": facts.get("earmarked") is True, "products": products,
                "dose": facts.get("dose"), "route": _text(facts.get("route")),
                "batch_lot_number": _text(facts.get("batch_lot_number")),
                "notes": _text(facts.get("notes"))}
    operation_id = "HERD-LITTER-TREAT-" + hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:24].upper()
    preview = {**material, "operation_id": operation_id, "action_kind": ACTION_KIND}
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


def _resolve_product(reference, rows):
    ref = _text(reference).casefold()
    matches = [dict(row) for row in rows if row.get("active", True) is not False and ref in {
        _text(row.get("product_id")).casefold(), _text(row.get("product_name")).casefold()}]
    if len(matches) != 1:
        return {"state": "missing" if not matches else "ambiguous"}
    row = matches[0]
    return {"state": "resolved", "product_id": _text(row.get("product_id")),
            "product_name": _text(row.get("product_name"))}


def _hold(status, **extra):
    return {"success": False, "status": status, "writes_farm_data": False, **extra}


def _date(value):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    try: return date.fromisoformat(_text(value))
    except ValueError: return None


def _text(value):
    return str(value or "").strip()


