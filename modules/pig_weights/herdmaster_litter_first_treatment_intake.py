"""Pure validation of reported first-treatment facts; never a prescription."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Mapping
from zoneinfo import ZoneInfo

ACTION_KIND = "herdmaster_record_litter_first_treatment"
CONTRACT_VERSION = "herdmaster_litter_first_treatment_preview_v2"
PRODUCT_KEYS = ("antiparasitic_product_ref", "deworming_product_ref", "vaccination_product_ref")


class LitterTreatmentEvidenceError(ValueError):
    pass


def treatment_digest(value):
    def normalize(item):
        if isinstance(item, Mapping):
            return {key: normalize(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(val) for val in item]
        if isinstance(item, float) and math.isfinite(item) and item.is_integer():
            return int(item)
        return item
    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True,
        separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()


def canonical_treatment_evidence(snapshot, products):
    """Adapt the existing canonical cohort without reconstructing pig facts."""
    if not snapshot:
        return {"evidence_generation": "missing", "animals": [], "litters": [], "products": products}
    litter = snapshot["litter"]
    return {"evidence_generation": treatment_digest(snapshot), "animals": [snapshot.get("sow") or {}],
        "litters": [{**litter, "detail": {**litter, "piglets": snapshot["piglets"],
            "reconciliation": snapshot.get("reconciliation")},
            "first_treatment_complete": bool(snapshot.get("treatment_receipts")),
            "first_treatment_partial": bool(snapshot.get("medical")),
            "first_treatment_skipped": bool(snapshot.get("skip", {}).get("first_treatment_skipped_at"))}],
        "products": products}


def reported_dose(value, unit=None):
    """Split a reported quantity/unit, without using a product's default dose."""
    if isinstance(value, bool) or value is None:
        raise LitterTreatmentEvidenceError("dose_required")
    match = re.fullmatch(r"\s*([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-zµμ%][A-Za-zµμ% /-]*)?\s*", str(value))
    if not match:
        raise LitterTreatmentEvidenceError("dose_required")
    amount = float(match[1].replace(",", "."))
    if not math.isfinite(amount) or amount <= 0:
        raise LitterTreatmentEvidenceError("dose_required")
    embedded, explicit = _text(match[2]).casefold(), _text(unit).casefold()
    if embedded and explicit and embedded != explicit:
        raise LitterTreatmentEvidenceError("dose_unit_conflict")
    selected = embedded or explicit
    if selected and not re.fullmatch(r"[a-zµμ%][a-zµμ% /-]{0,30}", selected):
        raise LitterTreatmentEvidenceError("dose_unit_required")
    return amount, selected


def prepare_litter_first_treatment_preview(report: Mapping, canonical: Mapping, *, today=None) -> dict:
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
    active = [dict(row) for row in canonical.get("litters") or []
        if _text(row.get("litter_status") or row.get("status")).casefold() == "active"]
    sow = None
    if facts.get("sow_ref"):
        sow = _resolve_one(facts["sow_ref"], canonical.get("animals") or [])
        if sow.get("state") != "resolved":
            return _hold("sow_identity_required", missing=["sow_ref"], sow=sow)
        active = [row for row in active if _text(row.get("sow_pig_id")) == sow["pig_id"]]
    explicit = _text(facts.get("litter_ref"))
    if explicit:
        active = [row for row in active if _text(row.get("litter_id")).casefold() == explicit.casefold()]
    if not (sow or explicit) or len(active) != 1:
        return _hold("exactly_one_active_litter_required", missing=["litter_ref"],
            candidate_litter_ids=sorted(_text(row.get("litter_id")) for row in active))
    litter = active[0]
    if sow is None:
        sow = _resolve_one(litter.get("sow_pig_id"), canonical.get("animals") or [])
    if sow.get("state") != "resolved":
        return _hold("sow_identity_required", missing=["sow_ref"])
    if any(litter.get(key) is True for key in (
            "first_treatment_complete", "first_treatment_partial", "first_treatment_skipped")):
        return _hold("first_treatment_already_has_canonical_evidence")
    detail = litter.get("detail") if isinstance(litter.get("detail"), Mapping) else {}
    reconciliation = detail.get("reconciliation") or {}
    if reconciliation.get("mismatch") or reconciliation.get("source_count_conflict"):
        return _hold("canonical_active_litter_membership_conflict")
    pigs = [dict(row) for row in detail.get("piglets") or []]
    if any((_text(row.get("status")).casefold() == "active") != _on_farm(row.get("on_farm")) for row in pigs):
        return _hold("canonical_active_litter_membership_conflict")
    current = [row for row in pigs if _text(row.get("status")).casefold() == "active" and _on_farm(row.get("on_farm"))]
    ids = [_text(row.get("pig_id")) for row in current]
    if not ids or not all(ids) or len(ids) != len(set(ids)):
        return _hold("canonical_active_litter_membership_required")
    if any(row.get("mother_pig_id") not in (None, "", sow["pig_id"]) for row in current):
        return _hold("canonical_sow_identity_conflict")
    if litter.get("active_count") is not None and litter["active_count"] != len(ids):
        return _hold("canonical_active_litter_membership_conflict")
    if any(row.get("wean_date") or row.get("animal_type") == "Weaner" for row in current) or litter.get("weaned_count") not in (None, 0):
        return _hold("first_treatment_litter_already_weaned")
    action_date = _date(facts.get("action_date"))
    if not action_date:
        return _hold("action_date_required", missing=["action_date"])
    today = today or datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    birth_dates = [_date(value) for value in [litter.get("farrowing_date"), detail.get("farrowing_date"),
        *[row.get("date_of_birth") for row in current]] if value]
    if action_date > today or any(value and action_date < value for value in birth_dates):
        return _hold("actual_treatment_date_conflict", missing=["action_date"])
    if not any(birth_dates):
        return _hold("canonical_birth_date_required")
    count = facts.get("total_count")
    if count is not None and (type(count) is not int or count != len(ids)):
        return _hold("reported_treatment_count_conflict", missing=["total_count"])
    male, female = facts.get("male_count"), facts.get("female_count")
    if male is not None or female is not None:
        if (type(male) is not int or type(female) is not int or min(male, female) < 0 or male + female != len(ids)):
            return _hold("reported_treatment_tally_conflict", missing=["male_count", "female_count"])
        if (sum(row.get("sex") in ("Male", "Castrated_Male") for row in current) > male
                or sum(row.get("sex") == "Female" for row in current) > female):
            return _hold("reported_treatment_tally_conflict", missing=["male_count", "female_count"])
    earmarked = facts.get("earmarked")
    if earmarked is not None and type(earmarked) is not bool:
        return _hold("earmark_fact_required", missing=["earmarked"])
    if earmarked is False and any(row.get("earmarked") is True for row in current):
        return _hold("earmark_history_conflict", missing=["earmarked"])
    products = []
    for key in PRODUCT_KEYS:
        ref = _text(facts.get(key))
        if not ref:
            continue
        found = _resolve_product(ref, canonical.get("products") or [])
        if found.get("state") != "resolved":
            return _hold("exact_treatment_product_required", missing=["product"])
        treatment_type = key.removesuffix("_product_ref").title()
        category = _text(found.get("product_category")).casefold()
        if key != "vaccination_product_ref":
            treatment_type = ("Vaccination" if "vacc" in category else "Deworming" if "deworm" in category
                else "Antiparasitic" if "parasite" in category or "antiparasitic" in category else treatment_type)
        products.append({**found, "treatment_type": treatment_type})
    if len({row["product_id"] for row in products}) != len(products):
        return _hold("duplicate_treatment_product", missing=["product"])
    missing = [] if products else ["product"]
    try:
        dose, unit = reported_dose(facts.get("dose"), facts.get("dose_unit"))
    except LitterTreatmentEvidenceError as exc:
        dose, unit = None, ""
        missing.append("dose_unit" if "unit" in str(exc) else "dose")
    if dose is not None and not unit:
        units = {_text(row.get("dose_unit")).casefold() for row in products}
        unit = next(iter(units)) if len(units) == 1 else ""
        if not unit:
            missing.append("dose_unit")
    for key in ("route", "batch_lot_number"):
        if not _text(facts.get(key)):
            missing.append(key)
    if missing:
        return _hold("medical_details_required", missing=missing)
    material = {"contract_version": CONTRACT_VERSION, "principal": principal,
        "provider_message_id": provider_id, "evidence_generation": generation,
        "sow_pig_id": sow["pig_id"], "sow_tag_number": sow.get("tag_number"), "sow_name": sow.get("name"),
        "litter_id": _text(litter["litter_id"]), "action_date": action_date.isoformat(),
        "pig_ids": sorted(ids), "total_count": len(ids), "reported_total_count": count,
        "male_count": male, "female_count": female, "earmarked": earmarked,
        "products": products, "dose": dose, "dose_unit": unit, "route": _text(facts["route"]),
        "batch_lot_number": _text(facts["batch_lot_number"]), "notes": _text(facts.get("notes")),
        "sex_count_scope": "litter_tally_only", "individual_piglet_sexes_assigned": False}
    operation_id = "HERD-LITTER-TREAT-" + treatment_digest(material)[:24].upper()
    preview = {**material, "operation_id": operation_id, "action_kind": ACTION_KIND}
    return {"success": True, "status": "preview_ready", "preview": preview,
        "operation_id": operation_id, "action_kind": ACTION_KIND, "confirmation_required": True, "writes_farm_data": False}


def _resolve_one(reference, rows):
    ref = _text(reference).casefold()
    matches = [dict(row) for row in rows if ref and ref in {_text(row.get(key)).casefold()
        for key in ("pig_id", "tag_number", "name", "pig_name")}]
    if len(matches) != 1:
        return {"state": "missing" if not matches else "ambiguous"}
    row = matches[0]
    return {"state": "resolved", "pig_id": _text(row.get("pig_id")),
        "tag_number": _text(row.get("tag_number")), "name": _text(row.get("name") or row.get("pig_name"))}


def _resolve_product(reference, rows):
    ref = _text(reference).casefold()
    matches = [dict(row) for row in rows if row.get("active", row.get("is_active", True)) is not False
        and ref in {_text(row.get("product_id")).casefold(), _text(row.get("product_name")).casefold()}]
    if len(matches) != 1:
        return {"state": "missing" if not matches else "ambiguous"}
    row = matches[0]
    return {"state": "resolved", **{key: row.get(key) for key in (
        "product_id", "product_name", "product_category", "dose_unit", "default_withdrawal_days")}}


def _hold(status, **extra):
    return {"success": False, "status": status, "writes_farm_data": False, **extra}


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(_text(value))
        return parsed if parsed.isoformat() == _text(value) else None
    except ValueError:
        return None


def _on_farm(value):
    return value is True or value in ("Yes", "yes")


def _text(value):
    return str(value if value is not None else "").strip()

