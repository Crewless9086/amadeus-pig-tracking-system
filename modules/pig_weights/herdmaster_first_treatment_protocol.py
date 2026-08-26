"""Canonical stock-standard protocol resolver for litter first treatment."""
from __future__ import annotations

import json
from typing import Mapping, Sequence


SETTING_KEY = "herdmaster_first_treatment_protocol_v1"
CONTRACT_VERSION = "herdmaster_first_treatment_protocol_v1"
ROLES = {"antiparasitic", "deworming", "vaccination"}


class FirstTreatmentProtocolError(ValueError):
    """Canonical protocol evidence is absent, malformed, or contradictory."""


def resolve_first_treatment_protocol(canonical: Mapping) -> dict:
    """Resolve one exact approved protocol; never infer treatment facts."""
    if not isinstance(canonical, Mapping):
        raise FirstTreatmentProtocolError("canonical_protocol_evidence_required")
    raw = _setting_value(canonical.get("settings"))
    if raw is None:
        raise FirstTreatmentProtocolError(
            "canonical_first_treatment_protocol_missing"
        )
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FirstTreatmentProtocolError(
                "canonical_first_treatment_protocol_malformed"
            ) from exc
    if not isinstance(raw, Mapping):
        raise FirstTreatmentProtocolError(
            "canonical_first_treatment_protocol_malformed"
        )

    protocol_id = _text(raw.get("protocol_id"))
    version = _text(raw.get("version"))
    notes = raw.get("notes")
    earmarked = raw.get("earmarked")
    treatments = raw.get("treatments")
    if (
        not protocol_id
        or not version
        or type(earmarked) is not bool
        or not isinstance(notes, str)
        or not isinstance(treatments, list)
        or not treatments
    ):
        raise FirstTreatmentProtocolError(
            "canonical_first_treatment_protocol_incomplete"
        )

    products = {
        _text(row.get("product_id")): dict(row)
        for row in canonical.get("products") or []
        if isinstance(row, Mapping)
        and _text(row.get("product_id"))
        and row.get("active", row.get("is_active", True)) is not False
    }
    resolved = []
    seen_roles = set()
    seen_products = set()
    for item in treatments:
        if not isinstance(item, Mapping):
            raise FirstTreatmentProtocolError(
                "canonical_first_treatment_protocol_incomplete"
            )
        role = _text(item.get("role")).casefold()
        product_id = _text(item.get("product_id"))
        product = products.get(product_id)
        if (
            role not in ROLES
            or role in seen_roles
            or not product
            or product_id in seen_products
        ):
            raise FirstTreatmentProtocolError(
                "canonical_first_treatment_protocol_product_conflict"
            )
        dose = item.get("dose", product.get("default_dose"))
        dose_unit = _text(item.get("dose_unit") or product.get("dose_unit"))
        route = _text(item.get("route"))
        batch = _text(item.get("batch_lot_number"))
        if dose in (None, "") or not dose_unit or not route or not batch:
            raise FirstTreatmentProtocolError(
                "canonical_first_treatment_protocol_medical_detail_missing"
            )
        seen_roles.add(role)
        seen_products.add(product_id)
        resolved.append(
            {
                "role": role,
                "product_id": product_id,
                "product_name": _text(product.get("product_name")) or product_id,
                "dose": dose,
                "dose_unit": dose_unit,
                "route": route,
                "batch_lot_number": batch,
            }
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "setting_key": SETTING_KEY,
        "protocol_id": protocol_id,
        "version": version,
        "earmarked": earmarked,
        "notes": notes.strip(),
        "treatments": sorted(resolved, key=lambda row: (row["role"], row["product_id"])),
    }


def _setting_value(settings):
    if isinstance(settings, Mapping):
        return settings.get(SETTING_KEY)
    if isinstance(settings, Sequence) and not isinstance(settings, (str, bytes)):
        matches = [
            row.get("setting_value")
            for row in settings
            if isinstance(row, Mapping)
            and _text(row.get("setting_key")) == SETTING_KEY
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _text(value):
    return str(value or "").strip()
