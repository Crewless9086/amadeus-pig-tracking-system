"""One livestock quotation aggregate shared by SAM, Orders and Documents.

The pure contract deliberately keeps customer requests, quotations, allocation
proposals, reservations and orders as different records.  Persistence adapters
may store the returned aggregate, but may not mutate an issued snapshot.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from modules.sales.sam_pricing import resolve_live_stock_price_rule


JOURNEYS = {"price_indication", "budgetary_quotation", "sales_quotation"}
FORMAL_JOURNEYS = {"budgetary_quotation", "sales_quotation"}
CONTRACT_VERSION = "livestock_quotation_v1"


def build_quotation_preview(payload, *, price_resolver=None, herdmaster_preview_builder=None,
                            herdmaster_packet=None, now=None):
    payload = payload if isinstance(payload, dict) else {}
    journey = str(payload.get("journey") or "price_indication").strip()
    if journey not in JOURNEYS:
        raise ValueError("journey must be price_indication, budgetary_quotation, or sales_quotation.")
    basis = str(payload.get("quotation_basis") or "").strip()
    if journey == "sales_quotation" and basis != "current_availability":
        raise ValueError("sales_quotation requires quotation_basis=current_availability.")
    if journey != "sales_quotation" and basis:
        raise ValueError("quotation_basis is only valid for sales_quotation.")

    requested_items = _requested_items(payload.get("requested_items"))
    observed = _utc(now)
    resolver = price_resolver or resolve_live_stock_price_rule
    lines = []
    for item in requested_items:
        rule = resolver(item["category"], item["weight_range"], item["sex"], as_of=observed.isoformat())
        if not isinstance(rule, dict) or not rule.get("found"):
            raise ValueError(f"No effective canonical price for requested item {item['request_item_key']}.")
        price = float(rule["unit_price"])
        quantity = item["quantity"]
        lines.append({
            "request_item_key": item["request_item_key"], "category": item["category"],
            "weight_range": item["weight_range"], "sex": item["sex"], "quantity": quantity,
            "unit_price": price, "subtotal": round(quantity * price, 2),
            "currency": rule.get("currency") or "ZAR", "pricing_id": rule.get("pricing_id") or "",
            "price_effective_from": rule.get("effective_from") or "",
            "price_effective_to": rule.get("effective_to") or "", "price_source": rule.get("source") or "",
        })

    allocation = None
    if journey == "sales_quotation":
        if not callable(herdmaster_preview_builder) or not isinstance(herdmaster_packet, dict):
            raise ValueError("Current-availability sales quotation requires current HERDMASTER evidence.")
        allocation = herdmaster_preview_builder(requested_items, herdmaster_packet)

    subtotal = round(sum(line["subtotal"] for line in lines), 2)
    vat_rate = float(payload.get("vat_rate") if payload.get("vat_rate") is not None else 0.15)
    vat_amount = round(subtotal * vat_rate, 2)
    total = round(subtotal + vat_amount, 2)
    preview = {
        "success": True, "contract_version": CONTRACT_VERSION, "journey": journey,
        "quotation_basis": basis or None, "customer_request_id": str(payload.get("customer_request_id") or "").strip() or None,
        "intake_id": str(payload.get("intake_id") or "").strip() or None,
        "requested_items": requested_items, "lines": lines, "currency": "ZAR",
        "subtotal_ex_vat": subtotal, "vat_rate": vat_rate, "vat_amount": vat_amount, "total": total,
        "observed_at": observed.isoformat(), "allocation_proposal": allocation,
        "creates_quotation": False, "creates_order": False, "creates_order_line": False,
        "creates_reservation": False, "generates_document": False,
        "creates_buyer_acknowledgement": False,
        "selects_animals": journey == "sales_quotation" and bool(allocation), "writes_performed": False,
        "document_default": journey in FORMAL_JOURNEYS,
        "authority_boundary": _boundary(journey),
    }
    preview["preview_digest"] = _digest(preview)
    return preview


def issue_quotation(preview, *, validity_days=3, issued_by="App", now=None,
                    previous_quotation_id=None):
    """Create an immutable issue-time snapshot; callers persist it append-only."""
    if not isinstance(preview, dict) or preview.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("A valid livestock quotation preview is required.")
    if preview.get("journey") not in FORMAL_JOURNEYS:
        raise ValueError("price_indication is conversational and is not issued as a quotation by default.")
    issued_at = _utc(now)
    days = int(validity_days)
    if days < 1 or days > 90:
        raise ValueError("validity_days must be between 1 and 90.")
    quotation_id = f"LQ-{issued_at:%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    snapshot = {
        "quotation_id": quotation_id, "status": "issued", "issued_at": issued_at.isoformat(),
        "valid_until": (issued_at + timedelta(days=days)).date().isoformat(),
        "issued_by": str(issued_by or "App"), "supersedes_quotation_id": previous_quotation_id,
        "superseded_by_quotation_id": None, "snapshot": json.loads(json.dumps(preview)),
        "price_snapshot_digest": _digest(preview.get("lines") or []),
        "creates_order": False, "creates_reservation": False,
    }
    snapshot["issue_digest"] = _digest(snapshot)
    return snapshot


def quotation_state(quotation, *, now=None):
    if quotation.get("superseded_by_quotation_id"):
        return "superseded"
    today = _utc(now).date().isoformat()
    return "expired" if str(quotation.get("valid_until") or "") < today else "current"


def conversion_refresh_request(quotation):
    """Conversion never carries old price, allocation or reservation forward."""
    snapshot = quotation.get("snapshot") or {}
    return {
        "source_quotation_id": quotation.get("quotation_id"),
        "requested_items": json.loads(json.dumps(snapshot.get("requested_items") or [])),
        "required_refreshes": ["effective_price", "current_availability"],
        "carries_allocation_forward": False, "carries_reservation_forward": False,
        "creates_order": False,
    }


def classify_quotation_intent(text):
    value = " ".join(str(text or "").lower().split())
    funding = ("funding", "finance approval", "loan", "budget approval", "company approval", "begroting", "finansiering")
    availability = ("available now", "current availability", "in stock", "which pigs", "beskikbaar nou")
    if any(term in value for term in funding):
        return "budgetary_quotation"
    if any(term in value for term in availability):
        return "sales_quotation"
    return "price_indication" if any(term in value for term in ("price", "cost", "how much", "prys", "hoeveel")) else None


def _requested_items(value):
    if not isinstance(value, list) or not value:
        raise ValueError("requested_items must be a non-empty list.")
    result = []
    for index, raw in enumerate(value[:20]):
        raw = raw if isinstance(raw, dict) else {}
        quantity = int(raw.get("quantity") or 0)
        if quantity < 1 or quantity > 100:
            raise ValueError("Each requested item quantity must be between 1 and 100.")
        result.append({
            "request_item_key": str(raw.get("request_item_key") or f"item_{index + 1}"),
            "category": str(raw.get("category") or "Piglet"),
            "weight_range": str(raw.get("weight_range") or ""), "sex": str(raw.get("sex") or "Any"),
            "quantity": quantity, "intent_type": str(raw.get("intent_type") or "primary"), "status": "active",
            "notes": str(raw.get("notes") or ""),
        })
    return result


def _boundary(journey):
    if journey == "budgetary_quotation":
        return "Funding/budget quotation only: no pig selection, live allocation, availability promise, reservation, or order."
    if journey == "sales_quotation":
        return "Current availability may be proposed, but allocation, reservation and order remain separate gated records."
    return "Direct category-price indication only: no PDF by default, availability promise, allocation, reservation, or order."


def _utc(value):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
