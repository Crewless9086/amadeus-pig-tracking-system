"""Replay-safe SAM Livestock quote, order, reservation and delivery lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from modules.sales.sam_live_stock_understanding import is_order_commitment_confirmation


CONTRACT_VERSION = "sam_live_stock_sales_lifecycle_v1"
NORMAL_HANDOVER_POINTS = ("Riversdale", "Albertinia")


def build_sales_lifecycle_packet(
    *,
    inbound: Mapping[str, Any],
    chronology: list[Mapping[str, Any]],
    retained_facts: Mapping[str, Any],
    inventory: Mapping[str, Any],
    pricing: Mapping[str, Any],
    order_state: Mapping[str, Any] | None = None,
    document_state: Mapping[str, Any] | None = None,
    claims: list[Mapping[str, Any]] | None = None,
    provider_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind the complete commercial lifecycle evidence without performing effects."""
    inbound = dict(inbound or {})
    chronology = _dedupe_chronology(chronology)
    facts = dict(retained_facts or {})
    order = dict(order_state or {})
    document = dict(document_state or {})
    identity = {
        "account_id": _text(inbound.get("account_id")),
        "inbox_id": _text(inbound.get("inbox_id")),
        "contact_id": _text(inbound.get("contact_id")),
        "conversation_id": _text(inbound.get("conversation_id")),
        "latest_inbound_message_id": _text(inbound.get("message_id")),
    }
    errors = _identity_errors(identity, chronology, provider_identity or {})
    latest_text = _text(inbound.get("content"))
    accepted = bool(facts.get("order_commitment") or is_order_commitment_confirmation(latest_text))
    missing = _missing_qualification(facts)
    selected = _selected_inventory(order, inventory)
    order_id = _text(order.get("order_id") or order.get("Order_ID"))
    document_id = _text(document.get("document_id") or document.get("Document_ID"))
    quote_current = bool(document_id and document.get("current") is not False and document.get("voided") is not True)
    exact_lines = _positive_int(order.get("active_line_count") or order.get("line_count"))
    if not exact_lines:
        exact_lines = len(selected)
    expected = _positive_int(facts.get("quantity"))
    stock_ready = bool(expected and exact_lines == expected and len(selected) == expected)
    price_ready = _pricing_complete(selected, pricing)
    handover_state = _handover_state(facts.get("location"))

    if errors:
        state = "evidence_invalid"
    elif handover_state == "prohibited_farm_collection":
        state = "handover_policy_blocked"
        errors.append("farm_collection_prohibited")
    elif handover_state == "owner_exception_required":
        state = "owner_handover_exception_required"
    elif missing:
        state = "qualification_in_progress"
    elif not accepted:
        state = "awaiting_customer_acceptance"
    elif not order_id or not quote_current:
        state = "ready_to_prepare_order_and_quote"
    elif not stock_ready or not price_ready:
        state = "corrective_replanning_required"
    else:
        state = "owner_decision_required"

    packet = {
        "contract_version": CONTRACT_VERSION,
        "identity": identity,
        "chronology": chronology,
        "chronology_cutoff": max((_timestamp(row) for row in chronology), default=""),
        "retained_facts": facts,
        "accepted": accepted,
        "missing_qualification": missing,
        "inventory": dict(inventory or {}),
        "selected_animals": selected,
        "pricing": dict(pricing or {}),
        "order_state": order,
        "document_state": document,
        "claims": [dict(row) for row in claims or [] if isinstance(row, Mapping)],
        "provider_identity": dict(provider_identity or {}),
        "stock_ready": stock_ready,
        "price_ready": price_ready,
        "handover_state": handover_state,
        "state": state,
        "evidence_errors": errors,
        "normal_handover_points": list(NORMAL_HANDOVER_POINTS),
        "farm_collection_allowed": False,
        "protected_owner_decision": (
            {
                "decision": "approve_or_reject_exact_reservation_and_current_quote_delivery",
                "order_id": order_id,
                "document_id": document_id,
                "selected_pig_ids": [row["pig_id"] for row in selected],
                "reservation_allowed_for_sam_auto": False,
                "document_send_allowed_for_sam_auto": False,
            }
            if state == "owner_decision_required"
            else {}
        ),
        "effects_performed": False,
    }
    packet["evidence_digest"] = _digest(packet)
    return packet


def prepare_order_and_quote_once(
    packet: Mapping[str, Any],
    *,
    create_order: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    prepare_quote: Callable[[str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Create at most one draft and one current quote; never reserve or send."""
    packet = dict(packet or {})
    if packet.get("evidence_errors"):
        return _result("evidence_invalid", packet)
    if packet.get("missing_qualification"):
        return _result("qualification_incomplete", packet)
    if packet.get("accepted") is not True:
        return _result("customer_acceptance_required", packet)
    if packet.get("stock_ready") is not True:
        return _result("exact_or_supported_alternative_stock_required", packet)
    if packet.get("price_ready") is not True:
        return _result("canonical_price_evidence_required", packet)
    if packet.get("handover_state") != "normal_handover":
        return _result("normal_handover_or_owner_exception_required", packet)
    existing_order = dict(packet.get("order_state") or {})
    order_id = _text(existing_order.get("order_id") or existing_order.get("Order_ID"))
    created = False
    if not order_id:
        created_order = dict(create_order(packet) or {})
        order_id = _text(created_order.get("order_id") or created_order.get("Order_ID"))
        if not order_id:
            return _result("draft_order_create_failed", packet)
        created = True
    document = dict(packet.get("document_state") or {})
    document_id = _text(document.get("document_id") or document.get("Document_ID"))
    generated = False
    if not document_id or document.get("current") is False or document.get("voided") is True:
        quote = dict(prepare_quote(order_id) or {})
        document_id = _text(quote.get("document_id") or quote.get("Document_ID"))
        if not document_id:
            return _result("quote_prepare_failed", packet, order_id=order_id, created_order=created)
        generated = True
    return _result(
        "owner_decision_required",
        packet,
        success=True,
        order_id=order_id,
        document_id=document_id,
        created_order=created,
        generated_quote=generated,
        reserves_stock=False,
        sends_customer_message=False,
    )


def execute_approved_reservation_and_delivery_once(
    approval: Mapping[str, Any],
    *,
    current_packet_loader: Callable[[], Mapping[str, Any]],
    reserve: Callable[[str, list[str]], Mapping[str, Any]],
    send_document: Callable[[str, str], Mapping[str, Any]],
    claim_effect: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    record_effect_outcome: Callable[[str, Mapping[str, Any]], Any],
    verify_owner_authority: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute an exact reviewed decision once after fresh evidence revalidation."""
    approval = dict(approval or {})
    current = dict(current_packet_loader() or {})
    expected_digest = _text(approval.get("evidence_digest"))
    if not expected_digest or expected_digest != _text(current.get("evidence_digest")):
        return _result("stale_owner_approval", current)
    if approval.get("decision") != "approve":
        return _result("owner_rejected", current)
    authority = dict(verify_owner_authority(approval, current) or {})
    if authority.get("verified") is not True:
        return _result("owner_authority_unverified", current)
    approval_id = _text(authority.get("approval_id"))
    owner_principal = _text(authority.get("owner_principal"))
    approved_scope = _text(authority.get("scope"))
    if (
        not approval_id
        or not owner_principal
        or approved_scope != "exact_reservation_and_current_quote_delivery"
        or _text(authority.get("evidence_digest")) != _text(current.get("evidence_digest"))
    ):
        return _result("owner_authority_scope_mismatch", current)
    if current.get("state") != "owner_decision_required" or current.get("evidence_errors"):
        return _result("current_evidence_not_executable", current)
    claims = current.get("claims") if isinstance(current.get("claims"), list) else []
    if any(_text(row.get("effect")) in {"reservation", "document_delivery"} for row in claims if isinstance(row, Mapping)):
        return _result("already_claimed_no_replay", current)
    decision = dict(current.get("protected_owner_decision") or {})
    order_id = _text(decision.get("order_id"))
    document_id = _text(decision.get("document_id"))
    pig_ids = [str(value) for value in decision.get("selected_pig_ids") or [] if str(value)]
    effect_identity = {
        "evidence_digest": expected_digest,
        "identity": dict(current.get("identity") or {}),
        "order_id": order_id,
        "document_id": document_id,
        "selected_pig_ids": pig_ids,
        "effects": ["reservation", "document_delivery"],
    }
    claim_identity = {
        **effect_identity,
        "approval_id": approval_id,
        "owner_principal": owner_principal,
        "approved_scope": approved_scope,
    }
    claim_identity["attempt_id"] = "SAM-LIFECYCLE-" + hashlib.sha256(
        json.dumps(effect_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24].upper()
    claimed = dict(claim_effect(claim_identity) or {})
    if claimed.get("created") is not True:
        if isinstance(claimed.get("persisted_result"), Mapping):
            return dict(claimed["persisted_result"])
        return _result("already_claimed_no_replay", current)
    attempt_id = _text(claimed.get("attempt_id") or claim_identity["attempt_id"])
    reserved = dict(reserve(order_id, pig_ids) or {})
    if reserved.get("success") is not True:
        outcome = _result("reservation_failed", current, order_id=order_id, attempt_id=attempt_id)
        record_effect_outcome(attempt_id, outcome)
        return outcome
    delivered = dict(send_document(document_id, current["identity"]["conversation_id"]) or {})
    delivery_state = _text(delivered.get("delivery_state") or delivered.get("status"))
    confirmed = (
        delivered.get("provider_confirmed") is True
        and delivery_state in {
        "provider_confirmed_delivered", "delivered",
        }
        and _text(delivered.get("attempt_id")) == attempt_id
        and _text(delivered.get("account_id")) == current["identity"]["account_id"]
        and _text(delivered.get("inbox_id")) == current["identity"]["inbox_id"]
        and _text(delivered.get("contact_id")) == current["identity"]["contact_id"]
        and _text(delivered.get("conversation_id")) == current["identity"]["conversation_id"]
        and _text(delivered.get("provider_identity_class")) == "genuine_whatsapp"
    )
    if not confirmed:
        outcome = _result(
            "delivery_quarantined_do_not_retry",
            current,
            order_id=order_id,
            document_id=document_id,
            reserved=True,
            delivery=delivered,
            automatic_retry_prohibited=True,
        )
        record_effect_outcome(attempt_id, outcome)
        return outcome
    outcome = _result(
        "completed",
        current,
        success=True,
        order_id=order_id,
        document_id=document_id,
        reserved=True,
        provider_confirmed=True,
        delivery=delivered,
        chatwoot_projection_allowed=True,
    )
    record_effect_outcome(attempt_id, outcome)
    return outcome


def _missing_qualification(facts: Mapping[str, Any]) -> list[str]:
    required = ("quantity", "sex", "location", "timing", "payment_method")
    missing = []
    for key in required:
        value = facts.get(key)
        if value in (None, "", [], {}) or (key == "quantity" and _positive_int(value) == 0):
            missing.append(key)
    return missing


def _handover_state(value):
    normalized = _text(value).lower()
    if not normalized:
        return "missing"
    if "farm" in normalized or "plaas" in normalized:
        return "prohibited_farm_collection"
    if normalized in {"riversdale", "riversdal", "albertinia"}:
        return "normal_handover"
    return "owner_exception_required"


def _identity_errors(identity, chronology, provider_identity):
    errors = [f"{key}_required" for key, value in identity.items() if not value]
    if chronology:
        latest = chronology[-1]
        latest_id = _text(latest.get("id") or latest.get("message_id"))
        if latest_id and latest_id != identity["latest_inbound_message_id"]:
            errors.append("latest_inbound_chronology_mismatch")
    else:
        errors.append("public_chronology_required")
    for key in ("account_id", "inbox_id", "contact_id", "conversation_id"):
        value = _text(provider_identity.get(key))
        if not value:
            errors.append(f"provider_{key}_required")
        elif value != identity[key]:
            errors.append(f"provider_{key}_mismatch")
    provider_class = _text(provider_identity.get("provider_identity_class"))
    if not provider_class:
        errors.append("provider_identity_class_required")
    elif provider_class != "genuine_whatsapp":
        errors.append("authoritative_whatsapp_provider_required")
    return sorted(set(errors))


def _selected_inventory(order, inventory):
    rows = inventory.get("eligible_projection") if isinstance(inventory, Mapping) else []
    rows = [dict(row) for row in rows or [] if isinstance(row, Mapping)]
    wanted = set(order.get("selected_pig_ids") or order.get("pig_ids") or [])
    if not wanted:
        return []
    selected = []
    for row in rows:
        pig_id = _text(row.get("pig_id") or row.get("Pig_ID"))
        if pig_id and (not wanted or pig_id in wanted) and row.get("live_stock_sale_eligible") is True:
            row["pig_id"] = pig_id
            selected.append(row)
    return selected


def _pricing_complete(selected, pricing):
    entries = pricing.get("price_entries") if isinstance(pricing, Mapping) else []
    if not selected or not isinstance(entries, list):
        return False
    categories = {_text(row.get("sale_category") or row.get("suggested_price_category")) for row in selected}
    proven = {_text(row.get("sale_category")) for row in entries if isinstance(row, Mapping) and row.get("active") is not False and row.get("unit_price") not in (None, "")}
    return bool(categories and categories <= proven)


def _dedupe_chronology(rows):
    unique = {}
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        key = _text(row.get("id") or row.get("message_id"))
        if key:
            unique[key] = dict(row)
    return sorted(unique.values(), key=lambda row: (_timestamp(row), _text(row.get("id") or row.get("message_id"))))


def _timestamp(row):
    return _text(row.get("created_at") or row.get("timestamp") or row.get("created_at_utc"))


def _result(status, packet, success=False, **extra):
    return {
        "success": bool(success),
        "status": status,
        "evidence_digest": _text(packet.get("evidence_digest")),
        "automatic_retry_prohibited": True,
        **extra,
    }


def _digest(packet):
    stable = {key: value for key, value in packet.items() if key not in {"evidence_digest", "created_at_utc"}}
    raw = json.dumps(_canonicalize(stable), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _canonicalize(value):
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list):
        items = [_canonicalize(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str))
    return value


def _positive_int(value):
    try:
        value = int(value)
        return value if value > 0 else 0
    except (TypeError, ValueError):
        return 0


def _text(value):
    return " ".join(str(value or "").split())
