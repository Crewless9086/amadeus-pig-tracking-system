"""Advisory delivery-fee policy for SAM Live Stock.

This module deliberately has no persistence or outbound side effects.  It prepares an
owner-reviewable option only after a customer has asked about transport.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


DEFAULT_RATE_RANDS_PER_ONE_WAY_KM = Decimal("20.00")
POLICY_SOURCE = "owner_policy_sam_live_stock_delivery_v1"
SAFE_CUSTOMER_WORDING = (
    "Collection is the normal option. Because you asked about delivery, I can prepare "
    "a transport estimate for farm-owner review. It is not confirmed until the owner approves it."
)

AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "creates_quote": False,
    "reserves_stock": False,
    "writes_order": False,
    "writes_farm_data": False,
}


def live_stock_delivery_policy():
    """Expose the durable collection-first policy and its commercial source."""
    return {
        "policy_id": "sam_live_stock_delivery_v1",
        "collection_first": True,
        "openly_offer_delivery": False,
        "customer_request_required": True,
        "owner_review_required": True,
        "rate_rands_per_one_way_km": DEFAULT_RATE_RANDS_PER_ONE_WAY_KM,
        "rate_source": POLICY_SOURCE,
        "round_trip_recovery_basis": True,
        "customer_auto_send_allowed": False,
        "quote_send_allowed": False,
        "reservation_allowed": False,
        "safe_customer_wording": SAFE_CUSTOMER_WORDING,
        **AUTHORITY_FLAGS,
    }


def calculate_live_stock_delivery_option(
    *,
    customer_requested_delivery,
    one_way_km=None,
    distance_source="",
    destination=None,
    delivery_eligible=True,
    eligibility_reason="",
    owner_override_amount=None,
    owner_override_rate=None,
    owner_override_approved=False,
    owner_override_reason="",
    owner_override_source="",
):
    """Prepare a non-binding delivery estimate and full review/audit shape.

    A fixed amount override takes precedence over an override rate.  Override values
    are ignored unless explicitly owner-approved and source/reason are supplied.
    """
    destination = _destination(destination)
    base = {
        "delivery_requested_by_customer": bool(customer_requested_delivery),
        "delivery_eligible": bool(delivery_eligible),
        "eligibility_reason": str(eligibility_reason or "").strip(),
        "destination": destination,
        "distance_source": str(distance_source or "").strip(),
        "one_way_km": None,
        "rate_rands_per_one_way_km": DEFAULT_RATE_RANDS_PER_ONE_WAY_KM,
        "rate_source": POLICY_SOURCE,
        "estimated_delivery_charge_rands": None,
        "fee_source": "not_calculated",
        "owner_override": {
            "approved": bool(owner_override_approved),
            "amount_rands": _optional_non_negative(owner_override_amount, "owner_override_amount"),
            "rate_rands_per_one_way_km": _optional_non_negative(owner_override_rate, "owner_override_rate"),
            "reason": str(owner_override_reason or "").strip(),
            "source": str(owner_override_source or "").strip(),
        },
        "owner_review_required": True,
        "customer_send_allowed": False,
        "safe_customer_wording": SAFE_CUSTOMER_WORDING,
        **AUTHORITY_FLAGS,
    }

    if not customer_requested_delivery:
        return {**base, "status": "collection_first_not_requested"}
    if not delivery_eligible:
        return {**base, "status": "delivery_not_eligible"}

    override = base["owner_override"]
    has_override = override["amount_rands"] is not None or override["rate_rands_per_one_way_km"] is not None
    if has_override and not (override["approved"] and override["reason"] and override["source"]):
        return {**base, "status": "owner_override_incomplete"}

    km = _optional_non_negative(one_way_km, "one_way_km")
    base["one_way_km"] = km
    if override["approved"] and override["amount_rands"] is not None:
        base.update(
            status="estimate_ready_for_owner_review",
            estimated_delivery_charge_rands=_money(override["amount_rands"]),
            fee_source="owner_override_amount",
        )
        return base
    if km is None:
        return {**base, "status": "one_way_km_required"}
    if not base["distance_source"]:
        return {**base, "status": "distance_source_required"}

    uses_override_rate = override["approved"] and override["rate_rands_per_one_way_km"] is not None
    rate = override["rate_rands_per_one_way_km"] if uses_override_rate else DEFAULT_RATE_RANDS_PER_ONE_WAY_KM
    base.update(
        status="estimate_ready_for_owner_review",
        rate_rands_per_one_way_km=_money(rate),
        rate_source=override["source"] if uses_override_rate else POLICY_SOURCE,
        estimated_delivery_charge_rands=_money(km * rate),
        fee_source="owner_override_rate" if uses_override_rate else "default_policy_rate",
    )
    return base


def _destination(value):
    value = value if isinstance(value, dict) else {}
    return {
        "address_line_1": str(value.get("address_line_1") or "").strip(),
        "place_name": str(value.get("place_name") or "").strip(),
        "town": str(value.get("town") or "").strip(),
        "area": str(value.get("area") or "").strip(),
        "latitude": str(value.get("latitude") or "").strip(),
        "longitude": str(value.get("longitude") or "").strip(),
        "maps_url": str(value.get("maps_url") or "").strip(),
        "notes": str(value.get("notes") or "").strip(),
    }


def _optional_non_negative(value, field):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} must be a non-negative finite number")
    return number


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
