import json
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request


HYGIENE_ENABLED_ENV = "SAM_MEAT_CHATWOOT_HYGIENE_ENABLED"
CHATWOOT_BASE_URL_ENV = "CHATWOOT_BASE_URL"
CHATWOOT_ACCOUNT_ID_ENV = "CHATWOOT_ACCOUNT_ID"
CHATWOOT_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
CHATWOOT_TOKEN_FALLBACK_ENV = "CHATWOOT_API_TOKEN"

MEAT_ATTRIBUTE_KEYS = {
    "sales_lane",
    "meat_product_type",
    "meat_cut_set",
    "meat_delivery_mode",
    "meat_delivery_town",
    "meat_lead_id",
    "meat_order_id",
    "meat_payment_state",
    "meat_next_gate",
    "meat_followup_due_at",
    "meat_last_customer_intent",
    "meat_budget_amount",
    "meat_target_packed_kg",
    "meat_match_preference",
}


def build_sam_meat_chatwoot_hygiene_payload(
    *,
    lead_payload=None,
    facts=None,
    inbound=None,
    decision=None,
    prior_context=None,
    booking_confirmation=None,
    pop_capture=None,
):
    lead_payload = lead_payload if isinstance(lead_payload, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    inbound = inbound if isinstance(inbound, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    booking_confirmation = booking_confirmation if isinstance(booking_confirmation, dict) else {}
    pop_capture = pop_capture if isinstance(pop_capture, dict) else {}

    product_type = _clean(facts.get("product_type") or lead_payload.get("product_type"), 80)
    cut_set = _clean(facts.get("cut_set") or lead_payload.get("cut_set"), 40)
    delivery_mode = _clean(facts.get("delivery_or_collection") or lead_payload.get("delivery_or_collection"), 40)
    delivery_town = _clean(
        facts.get("delivery_town")
        or lead_payload.get("delivery_town")
        or facts.get("location")
        or lead_payload.get("location"),
        120,
    )
    lead_id = _clean(
        decision.get("lead_id")
        or lead_payload.get("lead_id")
        or prior_context.get("lead_id")
        or (booking_confirmation.get("lead_id") if booking_confirmation.get("recorded") else ""),
        100,
    )
    order_id = _clean(lead_payload.get("order_id") or facts.get("order_id"), 100)
    budget_amount = _clean(facts.get("budget_amount") or lead_payload.get("budget_amount"), 80)
    target_packed_kg = _clean(facts.get("target_packed_kg") or lead_payload.get("target_packed_kg"), 80)
    match_preference = _clean(facts.get("match_preference") or lead_payload.get("match_preference"), 80)
    attrs = {
        "sales_lane": "meat_preorder",
        "meat_product_type": product_type if product_type != "unknown" else "",
        "meat_cut_set": cut_set,
        "meat_delivery_mode": delivery_mode,
        "meat_delivery_town": delivery_town,
        "meat_lead_id": lead_id,
        "meat_order_id": order_id,
        "meat_payment_state": _payment_state(booking_confirmation, pop_capture, decision, prior_context),
        "meat_next_gate": _next_gate(facts, booking_confirmation, pop_capture, decision, prior_context),
        "meat_followup_due_at": "",
        "meat_last_customer_intent": _customer_intent(inbound, facts, booking_confirmation, pop_capture),
        "meat_budget_amount": budget_amount,
        "meat_target_packed_kg": target_packed_kg,
        "meat_match_preference": match_preference,
    }
    labels = _labels(attrs, inbound, lead_payload, facts, decision, booking_confirmation, pop_capture)
    return {
        "custom_attributes": attrs,
        "labels": sorted(labels),
    }


def sync_sam_meat_chatwoot_hygiene(
    conversation_id,
    *,
    lead_payload=None,
    facts=None,
    inbound=None,
    decision=None,
    prior_context=None,
    booking_confirmation=None,
    pop_capture=None,
    environ=None,
    transport=None,
):
    source = environ if environ is not None else os.environ
    conversation_id = _clean(conversation_id, 100)
    if not conversation_id:
        return {"success": False, "enabled": _truthy(source.get(HYGIENE_ENABLED_ENV)), "status": "conversation_id_required"}
    if not _truthy(source.get(HYGIENE_ENABLED_ENV)) and transport is None:
        return {"success": True, "enabled": False, "status": "chatwoot_hygiene_disabled"}

    payload = build_sam_meat_chatwoot_hygiene_payload(
        lead_payload=lead_payload,
        facts=facts,
        inbound=inbound,
        decision=decision,
        prior_context=prior_context,
        booking_confirmation=booking_confirmation,
        pop_capture=pop_capture,
    )
    sender = transport or _chatwoot_transport
    try:
        existing = sender("GET", conversation_id, None, source)
        existing_attrs = _conversation_custom_attributes(existing)
        existing_labels = _conversation_labels(existing)
        merged_attrs = {**existing_attrs, **payload["custom_attributes"]}
        merged_labels = sorted(existing_labels | set(payload["labels"]))
        attr_result = sender("POST", conversation_id, {"custom_attributes": merged_attrs}, source, suffix="custom_attributes")
        label_result = sender("POST", conversation_id, {"labels": merged_labels}, source, suffix="labels")
        return {
            "success": True,
            "enabled": True,
            "status": "chatwoot_hygiene_synced",
            "conversation_id": conversation_id,
            "labels": merged_labels,
            "custom_attributes": {key: merged_attrs.get(key, "") for key in sorted(MEAT_ATTRIBUTE_KEYS)},
            "preserved_attribute_count": len([key for key in existing_attrs if key not in MEAT_ATTRIBUTE_KEYS]),
            "preserved_label_count": len(existing_labels - set(payload["labels"])),
            "chatwoot": {
                "custom_attributes": _result_summary(attr_result),
                "labels": _result_summary(label_result),
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "enabled": True,
            "status": "chatwoot_hygiene_failed",
            "conversation_id": conversation_id,
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:180],
            "planned_payload": payload,
        }


def _chatwoot_transport(method, conversation_id, body, source, suffix=""):
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not base_url:
        raise RuntimeError("CHATWOOT_BASE_URL is required")
    if not account_id:
        raise RuntimeError("CHATWOOT_ACCOUNT_ID is required")
    if not token:
        raise RuntimeError("CHATWOOT_API_ACCESS_TOKEN is required")
    path = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}"
    if suffix:
        path = f"{path}/{suffix}"
    data = json.dumps(body or {}, ensure_ascii=True, sort_keys=True).encode("utf-8") if body is not None else None
    headers = {"api_access_token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(path, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": getattr(response, "status", 200),
                "body": _parse_json(raw),
            }
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"chatwoot_http_{exc.code}") from exc


def _conversation_custom_attributes(value):
    body = _body(value)
    candidates = [
        body.get("custom_attributes"),
        (body.get("conversation") if isinstance(body.get("conversation"), dict) else {}).get("custom_attributes"),
        (body.get("data") if isinstance(body.get("data"), dict) else {}).get("custom_attributes"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def _conversation_labels(value):
    body = _body(value)
    candidates = [
        body.get("labels"),
        (body.get("conversation") if isinstance(body.get("conversation"), dict) else {}).get("labels"),
        (body.get("data") if isinstance(body.get("data"), dict) else {}).get("labels"),
    ]
    labels = set()
    for candidate in candidates:
        if not isinstance(candidate, list):
            continue
        for item in candidate:
            if isinstance(item, dict):
                label = _clean(item.get("title") or item.get("name"), 80)
            else:
                label = _clean(item, 80)
            if label:
                labels.add(label)
    return labels


def _labels(attrs, inbound, lead_payload, facts, decision, booking_confirmation, pop_capture):
    labels = {"meat_lead"}
    product_type = attrs.get("meat_product_type")
    if product_type in {"half_carcass", "full_carcass"}:
        labels.add(product_type)
    elif product_type == "custom_cut":
        labels.add("custom_cut")
    cut_set = attrs.get("meat_cut_set")
    if cut_set:
        labels.add(cut_set.lower().replace(" ", "_"))
    if attrs.get("meat_delivery_mode") in {"delivery", "collection"}:
        labels.add(attrs["meat_delivery_mode"])
    payment_state = attrs.get("meat_payment_state")
    if payment_state in {"deposit_pending", "pop_received_unverified", "deposit_confirmed", "balance_due"}:
        labels.add(payment_state)
    if attrs.get("meat_next_gate") in {
        "collect_missing_facts",
        "owner_price_review",
        "await_customer_yes",
        "send_deposit_instruction",
        "await_pop",
        "confirm_bank_receipt",
    }:
        labels.add("needs_followup")
    joined = " ".join(
        _clean(source.get(key), 1000)
        for source in (inbound, lead_payload, facts, decision)
        if isinstance(source, dict)
        for key in ("content", "notes", "reply_text")
    ).lower()
    if "test flow" in joined or "delete after test" in joined:
        labels.add("test_flow")
    if booking_confirmation.get("recorded"):
        labels.add("deposit_pending")
    if pop_capture.get("recorded") or pop_capture.get("detected"):
        labels.add("pop_received_unverified")
    return labels


def _payment_state(booking_confirmation, pop_capture, decision, prior_context):
    if pop_capture.get("recorded") or pop_capture.get("detected"):
        return "pop_received_unverified"
    if booking_confirmation.get("recorded") or decision.get("deposit_payment_instruction"):
        return "deposit_pending"
    if prior_context.get("latest_event") == "deposit_followup_needed":
        return "deposit_pending"
    return "not_requested"


def _next_gate(facts, booking_confirmation, pop_capture, decision, prior_context):
    if pop_capture.get("recorded") or pop_capture.get("detected"):
        return "confirm_bank_receipt"
    if decision.get("deposit_payment_instruction"):
        return "await_pop"
    if booking_confirmation.get("recorded"):
        return "send_deposit_instruction"
    if prior_context.get("latest_event") == "customer_followup_sent":
        return "await_customer_yes"
    required = ("product_type", "cut_set", "location", "delivery_or_collection", "timing", "payment_method")
    for key in required:
        value = _clean(facts.get(key), 120)
        if not value or (key == "product_type" and value == "unknown"):
            return "collect_missing_facts"
    if facts.get("delivery_or_collection") == "delivery" and not _clean(facts.get("delivery_address_line_1"), 240):
        return "collect_missing_facts"
    return "owner_price_review"


def _customer_intent(inbound, facts, booking_confirmation, pop_capture):
    if pop_capture.get("recorded") or pop_capture.get("detected"):
        return "sends_pop"
    if booking_confirmation.get("recorded"):
        return "confirms_booking"
    text = _clean(inbound.get("content") if isinstance(inbound, dict) else "", 1200).lower()
    if re.search(r"\b(price|cost|quote|how much)\b", text):
        return "asks_price"
    if re.search(r"\b(option|available|have|include|set)\b", text):
        return "asks_options"
    if facts.get("product_type") and facts.get("product_type") != "unknown":
        return "states_meat_interest"
    return "unknown"


def _result_summary(value):
    if isinstance(value, dict):
        return {
            "status_code": value.get("status_code"),
            "has_body": bool(value.get("body")),
        }
    return {"status_code": "", "has_body": False}


def _body(value):
    if not isinstance(value, dict):
        return {}
    body = value.get("body") if isinstance(value.get("body"), dict) else value
    return body if isinstance(body, dict) else {}


def _parse_json(value):
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _clean(value, limit=200):
    return str(value or "").strip()[:limit]
