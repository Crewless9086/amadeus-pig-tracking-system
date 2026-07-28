"""Owner-confirmed SAM Meat pilot offer and prepare-only quote rules."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

PRICE_PER_KG_INCLUDING_VAT = Decimal("130.00")
DEPOSIT_PERCENT = Decimal("50")

COLLECTIONS = {
    "Set A": {"name": "Amadeus Signature Collection", "summary": "Boneless neck steaks, additional forequarter stew meat, loin chops, bone-in rib rashers, whole pork belly, two half legs, cut shanks, and standard stew meat."},
    "Set B": {"name": "Amadeus Ember Collection", "summary": "Thick rib chops, shoulder chops, loin chops, whole pork rib, whole pork belly, one half leg, leg chops, cut shanks, and standard stew meat."},
    "Set C": {"name": "Amadeus Grand Cut Collection", "summary": "Neck chops, loin chops, whole pork rib, whole pork belly, whole pork leg, whole pork shanks (Eisbein), and standard stew meat."},
}
RETIRED_COLLECTIONS = {"Set D"}

def collection_description(code):
    item = COLLECTIONS.get(str(code or "").strip())
    return f"{item['name']}: {item['summary']}" if item else ""

def build_estimated_quote_preview(*, packed_weight_kg, weight_evidence_id):
    """Build a non-binding estimate only from bound packed-weight evidence."""
    weight_text = str(packed_weight_kg or "").strip()
    range_matches = re.findall(
        r"(\d+(?:[.,]\d+)?)\s*(?:-|–|to)\s*(\d+(?:[.,]\d+)?)\s*kg\b",
        weight_text,
        re.I,
    )
    if range_matches:
        values = list(range_matches[-1])
    elif re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*(?:kg)?\s*", weight_text, re.I):
        values = re.findall(r"\d+(?:[.,]\d+)?", weight_text)
    else:
        values = []
    try:
        weights = sorted(Decimal(value.replace(",", ".")) for value in values[:2])
    except (InvalidOperation, TypeError, ValueError):
        weights = []
    evidence_id = str(weight_evidence_id or "").strip()
    if not weights or any(value <= 0 for value in weights) or not evidence_id:
        return {
            "status": "Unavailable", "estimate_available": False,
            "blockers": ["authoritative_packed_weight_evidence_required"],
            "estimated_total": None, "estimated_deposit": None, "final_total": None,
        }
    totals = [(value * PRICE_PER_KG_INCLUDING_VAT).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for value in weights]
    deposits = [(value * DEPOSIT_PERCENT / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for value in totals]
    return {
        "status": "estimated_owner_review_only", "estimate_available": True,
        "packed_weight_kg": float(weights[0]) if len(weights) == 1 else None,
        "packed_weight_range_kg": [float(value) for value in weights] if len(weights) == 2 else [],
        "packed_weight_evidence_id": evidence_id,
        "price_per_kg": float(PRICE_PER_KG_INCLUDING_VAT), "vat_included": True,
        "estimated_total": float(totals[0]) if len(totals) == 1 else None,
        "estimated_total_range": [float(value) for value in totals] if len(totals) == 2 else [],
        "deposit_percent": float(DEPOSIT_PERCENT),
        "estimated_deposit": float(deposits[0]) if len(deposits) == 1 else None,
        "estimated_deposit_range": [float(value) for value in deposits] if len(deposits) == 2 else [],
        "final_total": None, "final_billing_basis": "butcher_confirmed_final_packed_weight",
        "delivery_fee": None, "delivery_timing": None, "binding_quote_created": False,
    }


def commercial_authority():
    return {key: False for key in ("customer_send", "binding_quote_creation", "order_creation", "deposit_confirmation", "reservation", "allocation", "slaughter_eligibility", "slaughter_booking", "availability_promise", "delivery_promise", "farm_write")}
