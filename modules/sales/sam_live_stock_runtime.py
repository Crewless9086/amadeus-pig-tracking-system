import hmac
import hashlib
import json
import os
import re
from datetime import datetime
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.orders.order_intake_service import (
    get_intake_context,
    update_intake_state,
    validate_intake_update_payload,
)
from modules.orders.order_service import create_order_with_lines
from modules.orders.order_validation import validate_new_order_payload, validate_sync_order_lines_payload
from modules.pig_weights.pig_weights_service import get_sales_availability
from modules.sales.sam_pricing import resolve_live_stock_price_rule
from modules.sales.sam_sales_router import LANE_LIVE_STOCK, classify_sam_sales_lane


WEBHOOK_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED"
WEBHOOK_TOKEN_ENV = "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN"
AUTOREPLY_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED"
LLM_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED"
AGENT_V3_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_AGENT_V3_ENABLED"
LLM_MODEL_ENV = "SAM_LIVE_STOCK_BACKEND_LLM_MODEL"
AGENT_V3_MODEL_ENV = "SAM_LIVE_STOCK_BACKEND_AGENT_V3_MODEL"
INTAKE_WRITE_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED"
DRAFT_ORDER_CREATE_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED"
OWNER_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED"
CHATWOOT_BASE_URL_ENV = "CHATWOOT_BASE_URL"
CHATWOOT_ACCOUNT_ID_ENV = "CHATWOOT_ACCOUNT_ID"
CHATWOOT_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
CHATWOOT_TOKEN_FALLBACK_ENV = "CHATWOOT_API_TOKEN"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
MIN_TOKEN_CHARS = 32

RUNTIME_VERSION = "sam_live_stock_read_only_v1"


def sam_live_stock_webhook_policy(environ=None):
    source = environ if environ is not None else os.environ
    token = str(source.get(WEBHOOK_TOKEN_ENV, "") or "").strip()
    llm_configured = bool(str(source.get(OPENAI_API_KEY_ENV, "") or "").strip() and _configured_model(source))
    return {
        "mode": "backend_native_sam_live_stock_chatwoot_read_only",
        "runtime_version": RUNTIME_VERSION,
        "enabled": _truthy(source.get(WEBHOOK_ENABLED_ENV)),
        "token_configured": len(token) >= MIN_TOKEN_CHARS,
        "autoreply_enabled": False,
        "autoreply_explicitly_enabled": _truthy(source.get(AUTOREPLY_ENABLED_ENV)),
        "llm_enabled": False,
        "llm_explicitly_enabled": _truthy(source.get(LLM_ENABLED_ENV)),
        "llm_configured": llm_configured,
        "agent_v3_enabled": False,
        "agent_v3_explicitly_enabled": _truthy(source.get(AGENT_V3_ENABLED_ENV)),
        "enabled_env": WEBHOOK_ENABLED_ENV,
        "token_env": WEBHOOK_TOKEN_ENV,
        "autoreply_env": AUTOREPLY_ENABLED_ENV,
        "llm_enabled_env": LLM_ENABLED_ENV,
        "agent_v3_enabled_env": AGENT_V3_ENABLED_ENV,
        "llm_model_env": LLM_MODEL_ENV,
        "agent_v3_model_env": AGENT_V3_MODEL_ENV,
        "intake_write_enabled": _truthy(source.get(INTAKE_WRITE_ENABLED_ENV)),
        "intake_write_env": INTAKE_WRITE_ENABLED_ENV,
        "draft_order_create_enabled": _truthy(source.get(DRAFT_ORDER_CREATE_ENABLED_ENV)),
        "draft_order_create_env": DRAFT_ORDER_CREATE_ENABLED_ENV,
        "owner_approved_send_enabled": _truthy(source.get(OWNER_SEND_ENABLED_ENV)),
        "owner_approved_send_env": OWNER_SEND_ENABLED_ENV,
        "api_key_env": OPENAI_API_KEY_ENV,
        "read_only": True,
        "writes_allowed": False,
        "customer_send_allowed": False,
        **_authority_flags(),
    }


def authorize_sam_live_stock_webhook(headers, query_args=None, environ=None):
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(WEBHOOK_ENABLED_ENV)):
        return False, _denied("sam_live_stock_backend_webhook_disabled", source)
    expected = str(source.get(WEBHOOK_TOKEN_ENV, "") or "").strip()
    if not expected:
        return False, _denied("sam_live_stock_backend_webhook_token_not_configured", source)
    if len(expected) < MIN_TOKEN_CHARS:
        return False, _denied("sam_live_stock_backend_webhook_token_too_short", source)
    if not _token_matches(headers or {}, query_args or {}, expected):
        return False, _denied("sam_live_stock_backend_webhook_auth_denied", source)
    return True, {}


def handle_sam_live_stock_chatwoot_inbound(
    payload,
    *,
    environ=None,
    intake_context_loader=None,
    availability_loader=None,
    intake_writer=None,
    draft_order_creator=None,
):
    source = environ if environ is not None else os.environ
    inbound = parse_chatwoot_inbound(payload)
    policy = sam_live_stock_webhook_policy(source)
    if not inbound["processable"]:
        return {
            "success": True,
            "status": inbound["status"],
            "processed": False,
            "sent": False,
            "sam_decision": {},
            "policy": policy,
            **_authority_flags(),
        }, 200

    facts = extract_live_stock_facts(inbound["content"], inbound)
    context_packet = load_live_stock_read_context(
        inbound,
        facts,
        intake_context_loader=intake_context_loader,
        availability_loader=availability_loader,
    )
    facts = merge_prior_live_stock_context(facts, context_packet.get("prior_context") or {})
    decision = build_sam_live_stock_decision(inbound, facts, context_packet, source)
    conversation_review = review_sam_live_stock_conversation(inbound, facts, decision, context_packet)
    decision["conversation_review"] = conversation_review
    if conversation_review.get("no_reply_recommended"):
        decision["suggested_reply_text"] = ""
        decision["reply_source"] = "natural_close_no_reply_guard"
    if conversation_review.get("escalation_required"):
        decision["owner_gate_required"] = True
        decision["escalation_packet"] = build_sam_live_stock_escalation_packet(
            inbound,
            facts,
            decision,
            conversation_review,
        )
        if decision["escalation_packet"].get("suggested_response"):
            decision["suggested_reply_text"] = decision["escalation_packet"]["suggested_response"]
    intake_write = write_live_stock_intake_if_enabled(
        inbound,
        facts,
        decision,
        source,
        intake_writer=intake_writer,
    )
    if intake_write.get("attempted"):
        decision["intake_write"] = intake_write
        if not intake_write.get("success"):
            decision.setdefault("blockers", []).append(intake_write.get("status") or "intake_write_failed")
            decision["owner_gate_required"] = True
    draft_order = create_live_stock_draft_order_if_enabled(
        inbound,
        facts,
        decision,
        source,
        draft_order_creator=draft_order_creator,
    )
    if draft_order.get("attempted"):
        decision["draft_order"] = draft_order
        if not draft_order.get("success"):
            decision.setdefault("blockers", []).append(draft_order.get("status") or "draft_order_failed")
            decision["owner_gate_required"] = True
    return {
        "success": True,
        "status": "sam_live_stock_read_only_processed",
        "processed": True,
        "sent": False,
        "sam_decision": decision,
        "policy": policy,
        **_authority_flags(
            writes_order_intake=bool(intake_write.get("success")),
            creates_order=bool(draft_order.get("success")),
        ),
    }, 200


def parse_chatwoot_inbound(payload):
    payload = payload if isinstance(payload, dict) else {}
    message_type = _normal_chatwoot_message_type(payload)
    event = _clean(payload.get("event"), 80).lower()
    content = _clean(payload.get("content") or payload.get("message") or payload.get("text"), 1800)
    conversation = payload.get("conversation") if isinstance(payload.get("conversation"), dict) else {}
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    conversation_id = _clean(
        payload.get("conversation_id")
        or conversation.get("id")
        or (payload.get("conversation") if not isinstance(payload.get("conversation"), dict) else ""),
        100,
    )
    customer_name = _clean(
        payload.get("customer_name") or sender.get("name") or contact.get("name") or sender.get("identifier"),
        120,
    )
    channel = _normal_channel(payload, conversation)
    if message_type and message_type != "incoming":
        return _ignored("ignored_non_incoming_message", event, message_type, content, conversation_id, customer_name, channel)
    if event and event not in {"message_created", "conversation_created"}:
        return _ignored("ignored_non_message_event", event, message_type, content, conversation_id, customer_name, channel)
    if not content:
        return _ignored("ignored_empty_message", event, message_type, content, conversation_id, customer_name, channel)
    custom_attributes = conversation.get("custom_attributes") if isinstance(conversation.get("custom_attributes"), dict) else {}
    return {
        "processable": True,
        "status": "processable",
        "event": event or "message_created",
        "message_type": message_type or "incoming",
        "content": content,
        "conversation_id": conversation_id,
        "contact_id": _clean(payload.get("contact_id") or sender.get("id") or contact.get("id"), 100),
        "account_id": _clean(payload.get("account_id") or account.get("id"), 100),
        "customer_name": customer_name or "Chatwoot customer",
        "customer_phone": _clean(sender.get("phone_number") or contact.get("phone_number"), 80),
        "channel": channel,
        "message_id": _clean(payload.get("id") or payload.get("message_id"), 100),
        "last_inbound_at": _clean(payload.get("created_at") or payload.get("timestamp"), 80),
        "conversation_custom_attributes": custom_attributes,
    }


def extract_live_stock_facts(message, inbound=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    text = _normal_text(message)
    weight_range = _extract_weight_range(text)
    category = _extract_category(text)
    if category == "live_pig":
        category = _category_from_weight_range(weight_range) or category
    facts = {
        "sales_lane": "",
        "category": category,
        "quantity": _extract_quantity(text),
        "sex": _extract_sex(text),
        "weight_range": weight_range,
        "timing": _extract_timing(text),
        "location": _extract_location(text),
        "transport_expectation": _extract_transport(text),
        "payment_method": _extract_payment(text),
        "quote_requested": _asks_quote(text),
        "reservation_requested": _asks_reservation(text),
        "breeding_interest": _has_any(text, ("breeding", "breed", "gilt", "gilts", "boar", "boars", "sow", "sows")),
        "customer_name": inbound.get("customer_name") or "",
        "conversation_id": inbound.get("conversation_id") or "",
        "contact_id": inbound.get("contact_id") or "",
        "channel": inbound.get("channel") or "chatwoot",
        "llm_used": False,
        "llm_status": "not_enabled_read_only_stage",
    }
    route = classify_sam_sales_lane(message)
    facts["sales_lane"] = route["lane"]
    facts["lane_confidence"] = route["confidence"]
    facts["lane_reasons"] = route["reasons"]
    return facts


def merge_prior_live_stock_context(facts, prior_context):
    facts = dict(facts or {})
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    interest = prior_context.get("interest") if isinstance(prior_context.get("interest"), dict) else prior_context
    prior_has_live_stock_item = any(
        not _blank(interest.get(key))
        for key in ("category", "quantity", "sex", "weight_range")
    )
    for key in (
        "category",
        "quantity",
        "sex",
        "weight_range",
        "timing",
        "location",
        "transport_expectation",
        "payment_method",
        "quote_requested",
        "order_commitment",
    ):
        if _blank(facts.get(key)) and not _blank(interest.get(key)):
            facts[key] = interest.get(key)
    if _blank(facts.get("sales_lane")) and not _blank(interest.get("sales_lane")):
        facts["sales_lane"] = interest.get("sales_lane")
    if interest.get("quote_requested") and not facts.get("quote_requested"):
        facts["quote_requested"] = True
    if interest.get("order_commitment") and not facts.get("order_commitment"):
        facts["order_commitment"] = True
    if str(facts.get("sales_lane") or "").strip().lower() in ("", "unclear", "farm_general_question", "owner_handoff") and prior_has_live_stock_item:
        facts["sales_lane"] = LANE_LIVE_STOCK
        facts["lane_confidence"] = max(float(facts.get("lane_confidence") or 0), 0.9)
        reasons = facts.get("lane_reasons") if isinstance(facts.get("lane_reasons"), list) else []
        facts["lane_reasons"] = [*reasons, "live_stock_context:active_order_intake"]
    return facts


def load_live_stock_read_context(
    inbound,
    facts,
    *,
    intake_context_loader=None,
    availability_loader=None,
):
    inbound = inbound if isinstance(inbound, dict) else {}
    context_errors = []
    prior_context = {}
    intake = {"success": False, "lookup_status": "not_loaded", "items": []}
    if inbound.get("conversation_id"):
        try:
            loader = intake_context_loader or get_intake_context
            intake = loader(inbound.get("conversation_id"))
            prior_context = _prior_context_from_intake(intake)
        except Exception as exc:
            context_errors.append(_integration_failure("order_intake_context_read_failed", exc))
            intake = {"success": False, "lookup_status": "read_failed", "items": []}
    try:
        loader = availability_loader or get_sales_availability
        availability_rows = loader()
        availability_facts = merge_prior_live_stock_context(facts, prior_context)
        availability = summarize_live_stock_availability(availability_rows, availability_facts)
    except Exception as exc:
        context_errors.append(_integration_failure("sales_availability_read_failed", exc))
        availability = {"success": False, "status": "read_failed", "rows": [], "matched_count": 0, "summary": {}}
    return {
        "success": not context_errors,
        "read_only": True,
        "prior_context": prior_context,
        "intake_context": intake,
        "availability": availability,
        "context_errors": context_errors,
    }


def summarize_live_stock_availability(rows, facts=None):
    rows = rows if isinstance(rows, list) else []
    facts = facts if isinstance(facts, dict) else {}
    safe_rows = []
    for row in rows:
        if not isinstance(row, dict) or not _row_available_for_live_stock(row):
            continue
        safe_rows.append(row)

    category = _normal_category(facts.get("category"))
    sex = _normal_sex(facts.get("sex"))
    requested_weight_range = facts.get("weight_range") or ""
    matched = []
    for row in safe_rows:
        if category and category not in _row_category_tokens(row):
            continue
        if sex and sex != "any" and sex not in _normal_text(row.get("sex")):
            continue
        if requested_weight_range and not _row_matches_requested_weight(row, requested_weight_range):
            continue
        matched.append(row)

    bucket_counts = {}
    for row in safe_rows:
        label = _clean(row.get("sale_category") or row.get("suggested_price_category") or row.get("calculated_stage") or "Uncategorised", 80)
        bucket_counts[label] = bucket_counts.get(label, 0) + 1
    return {
        "success": True,
        "status": "loaded",
        "read_only": True,
        "total_available_count": len(safe_rows),
        "matched_count": len(matched),
        "summary": bucket_counts,
        "matched_sample": [_availability_public_row(row) for row in matched[:10]],
    }


def build_sam_live_stock_decision(inbound, facts, context_packet, environ=None):
    route = classify_sam_sales_lane(inbound.get("content"), prior_context={"lane": facts.get("sales_lane")})
    if facts.get("sales_lane") == LANE_LIVE_STOCK and route["lane"] != LANE_LIVE_STOCK:
        route = {
            **route,
            "lane": LANE_LIVE_STOCK,
            "confidence": max(float(route.get("confidence") or 0), float(facts.get("lane_confidence") or 0), 0.9),
            "reasons": [
                *(route.get("reasons") if isinstance(route.get("reasons"), list) else []),
                "live_stock_context:merged_prior_intake",
            ],
        }
    missing = _missing_live_stock_fields(facts)
    availability = context_packet.get("availability") if isinstance(context_packet, dict) else {}
    blockers = []
    if route["lane"] != LANE_LIVE_STOCK:
        blockers.append(f"lane_not_live_stock:{route['lane']}")
    if facts.get("breeding_interest"):
        blockers.append("breeding_or_replacement_stock_owner_gate")
    if facts.get("reservation_requested"):
        blockers.append("reservation_request_owner_gate")
    if context_packet.get("context_errors"):
        blockers.append("read_context_error")

    ready_for_runtime_next_step = route["lane"] == LANE_LIVE_STOCK and not missing and not blockers
    match_packet = build_live_stock_match_packet(facts, availability)
    draft_packet = build_live_stock_draft_order_packet(inbound, facts, match_packet)
    price_answer_packet = build_live_stock_price_answer_packet(facts, match_packet)
    reply = _safe_reply_draft(facts, route, missing, availability, blockers, price_answer_packet)
    return {
        "version": RUNTIME_VERSION,
        "agent": "sam_live_stock_backend",
        "mode": "read_only_stage_3",
        "inbound": {
            "conversation_id": inbound.get("conversation_id") or "",
            "message_id": inbound.get("message_id") or "",
            "customer_name": inbound.get("customer_name") or "",
            "customer_phone": inbound.get("customer_phone") or "",
            "channel": inbound.get("channel") or "",
            "content": inbound.get("content") or "",
        },
        "sales_lane": route["lane"],
        "lane_confidence": route["confidence"],
        "facts": facts,
        "missing_fields": missing,
        "availability": availability,
        "match_packet": match_packet,
        "price_answer_packet": price_answer_packet,
        "draft_order_packet": draft_packet,
        "blockers": blockers,
        "ready_for_runtime_next_step": ready_for_runtime_next_step,
        "suggested_reply_text": reply,
        "reply_source": "deterministic_read_only_guard",
        "should_reply": False,
        "writes_allowed": False,
        "intake_write_allowed": _truthy((environ or {}).get(INTAKE_WRITE_ENABLED_ENV)) and route["lane"] == LANE_LIVE_STOCK,
        "draft_order_create_allowed": _truthy((environ or {}).get(DRAFT_ORDER_CREATE_ENABLED_ENV)) and ready_for_runtime_next_step and draft_packet.get("draft_ready"),
        "customer_send_allowed": False,
        "owner_gate_required": bool(blockers or route["lane"] != LANE_LIVE_STOCK or route["confidence"] < 0.96),
        **_authority_flags(),
    }


def build_live_stock_intake_payload(inbound, facts, decision=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    notes = _intake_notes(facts, decision)
    item = _live_stock_intake_item(facts)
    patch = {
        "collection_location": _normal_intake_location(facts.get("location")),
        "collection_time_text": _clean(facts.get("timing"), 120),
        "last_customer_message": _clean(inbound.get("content"), 600),
        "notes": notes,
    }
    if facts.get("quote_requested"):
        patch["quote_requested"] = True
    if facts.get("order_commitment"):
        patch["order_commitment"] = True
    payment_method = _normal_intake_payment(facts.get("payment_method"))
    if payment_method:
        patch["payment_method"] = payment_method
    return {
        "conversation_id": _clean(inbound.get("conversation_id"), 100),
        "account_id": _clean(inbound.get("account_id"), 100),
        "contact_id": _clean(inbound.get("contact_id"), 100),
        "customer_name": _clean(inbound.get("customer_name"), 120),
        "customer_phone": _clean(inbound.get("customer_phone"), 80),
        "customer_channel": _clean(inbound.get("channel"), 80),
        "customer_language": "",
        "updated_by": "Sam Live Stock",
        "patch": {key: value for key, value in patch.items() if value not in ("", None)},
        "items": [item] if item else [],
    }


def validate_live_stock_intake_payload(payload):
    validation = validate_intake_update_payload(payload)
    return {
        "is_valid": bool(validation.get("is_valid")),
        "errors": list(validation.get("errors") or []),
        "cleaned_data": validation.get("cleaned_data") if isinstance(validation.get("cleaned_data"), dict) else {},
    }


def write_live_stock_intake_if_enabled(inbound, facts, decision, environ=None, intake_writer=None):
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(INTAKE_WRITE_ENABLED_ENV)):
        return {"attempted": False, "success": False, "status": "sam_live_stock_intake_write_disabled"}
    if (decision or {}).get("sales_lane") != LANE_LIVE_STOCK:
        return {"attempted": False, "success": False, "status": "sam_live_stock_intake_wrong_lane"}
    if facts.get("breeding_interest"):
        return {"attempted": False, "success": False, "status": "sam_live_stock_intake_owner_gate_breeding"}
    payload = build_live_stock_intake_payload(inbound, facts, decision)
    validation = validate_live_stock_intake_payload(payload)
    if not validation["is_valid"]:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_intake_validation_failed",
            "errors": validation["errors"],
            "payload": payload,
        }
    try:
        writer = intake_writer or update_intake_state
        result = writer(validation["cleaned_data"])
        return {
            "attempted": True,
            "success": bool((result or {}).get("success")),
            "status": "sam_live_stock_intake_written" if (result or {}).get("success") else "sam_live_stock_intake_write_failed",
            "result": result,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_intake_write_exception",
            "error": _clean(str(exc), 240),
            "payload": payload,
        }


def build_live_stock_match_packet(facts, availability):
    facts = facts if isinstance(facts, dict) else {}
    availability = availability if isinstance(availability, dict) else {}
    quantity = facts.get("quantity") if isinstance(facts.get("quantity"), int) else 0
    matched = availability.get("matched_sample") if isinstance(availability.get("matched_sample"), list) else []
    exact_count = int(availability.get("matched_count") or len(matched) or 0)
    status = "not_ready"
    if quantity > 0 and exact_count >= quantity:
        status = "exact_match_available"
    elif quantity > 0 and exact_count > 0:
        status = "partial_match_available"
    elif quantity > 0 and availability.get("success"):
        status = "no_exact_match"
    return {
        "version": "sam_live_stock_match_packet_v1",
        "read_only": True,
        "requested_quantity": quantity,
        "exact_match_count": exact_count,
        "match_status": status,
        "complete_fulfillment": quantity > 0 and exact_count >= quantity,
        "partial_fulfillment": quantity > 0 and 0 < exact_count < quantity,
        "matched_sample": matched[:quantity or 10],
        "owner_review_required": True,
        "can_create_draft_order": quantity > 0 and exact_count > 0,
    }


def build_live_stock_draft_order_packet(inbound, facts, match_packet=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    match_packet = match_packet if isinstance(match_packet, dict) else {}
    item = _live_stock_sync_requested_item(facts)
    price_rule = _live_stock_price_rule_for_packet(facts, match_packet)
    quantity = facts.get("quantity") if isinstance(facts.get("quantity"), int) else 0
    quoted_total = (
        round(float(price_rule["unit_price"]) * quantity, 2)
        if price_rule.get("found") and price_rule.get("unit_price") is not None and quantity > 0
        else ""
    )
    order_payload = {
        "order_date": datetime.now().date().isoformat(),
        "customer_name": _clean(inbound.get("customer_name"), 120),
        "customer_phone": _clean(inbound.get("customer_phone"), 80),
        "customer_channel": _clean(inbound.get("channel"), 80) or "chatwoot",
        "customer_language": "unknown",
        "order_source": "SAM Live Stock",
        "requested_category": _normal_intake_category(facts.get("category")),
        "requested_weight_range": _normal_intake_weight_range(facts.get("weight_range"), _normal_intake_category(facts.get("category"))),
        "requested_sex": _normal_intake_sex(facts.get("sex")),
        "requested_quantity": facts.get("quantity") or "",
        "quoted_total": quoted_total,
        "collection_location": _normal_intake_location(facts.get("location")),
        "payment_method": _normal_intake_payment(facts.get("payment_method")),
        "notes": _clean("source=sam_live_stock_stage_5; owner_review_required=true", 600),
        "created_by": "Sam Live Stock",
        "conversation_id": _clean(inbound.get("conversation_id"), 100),
    }
    sync_payload = {
        "changed_by": "Sam Live Stock",
        "cancel_order_if_no_matches": True,
        "requested_items": [item] if item else [],
    }
    order_validation = validate_new_order_payload(order_payload)
    sync_validation = validate_sync_order_lines_payload(sync_payload)
    errors = list(order_validation.get("errors") or []) + list(sync_validation.get("errors") or [])
    enough_stock = bool(match_packet.get("complete_fulfillment"))
    return {
        "version": "sam_live_stock_draft_order_packet_v1",
        "draft_ready": not errors and enough_stock,
        "owner_review_required": True,
        "order_payload": order_payload,
        "sync_payload": sync_payload,
        "pricing": price_rule,
        "validation_errors": errors,
        "stock_gate": "passed" if enough_stock else (
            "partial_matching_stock" if match_packet.get("partial_fulfillment") else "no_matching_stock"
        ),
        "warnings": [
            "Creates draft order only when explicit env gate is enabled.",
            "Does not reserve pigs.",
            "Does not send quote/customer message.",
        ],
    }


def build_live_stock_price_answer_packet(facts, match_packet=None):
    facts = facts if isinstance(facts, dict) else {}
    match_packet = match_packet if isinstance(match_packet, dict) else {}
    price_rule = _live_stock_price_rule_for_packet(facts, match_packet)
    quantity = _quantity_number(facts.get("quantity"))
    unit_price = price_rule.get("unit_price") if price_rule.get("found") else None
    estimated_total = round(float(unit_price) * quantity, 2) if unit_price is not None and quantity > 0 else ""
    return {
        "version": "sam_live_stock_price_answer_packet_v1",
        "requested_quantity": quantity or "",
        "requested_category": _normal_intake_category(facts.get("category")),
        "requested_weight_range": _normal_intake_weight_range(
            facts.get("weight_range"),
            _normal_intake_category(facts.get("category")),
        ),
        "requested_sex": _normal_intake_sex(facts.get("sex")),
        "pricing": price_rule,
        "unit_price": unit_price if unit_price is not None else "",
        "estimated_total": estimated_total,
        "can_answer_price": bool(price_rule.get("found") and unit_price is not None),
        "owner_review_required": True,
        "customer_send_allowed": False,
        "formal_quote_created": False,
        "reservation_created": False,
        "safety_note": "Price answer is an estimate only. Farm must confirm animals before any promise, reservation, or formal quote.",
        **_authority_flags(),
    }


def create_live_stock_draft_order_if_enabled(inbound, facts, decision, environ=None, draft_order_creator=None):
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(DRAFT_ORDER_CREATE_ENABLED_ENV)):
        return {"attempted": False, "success": False, "status": "sam_live_stock_draft_order_create_disabled"}
    if (decision or {}).get("sales_lane") != LANE_LIVE_STOCK:
        return {"attempted": False, "success": False, "status": "sam_live_stock_draft_order_wrong_lane"}
    if facts.get("breeding_interest"):
        return {"attempted": False, "success": False, "status": "sam_live_stock_draft_order_owner_gate_breeding"}
    packet = (decision or {}).get("draft_order_packet") or build_live_stock_draft_order_packet(
        inbound,
        facts,
        (decision or {}).get("match_packet") or {},
    )
    if not packet.get("draft_ready"):
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_not_ready",
            "packet": packet,
        }
    order_validation = validate_new_order_payload(packet["order_payload"])
    sync_validation = validate_sync_order_lines_payload(packet["sync_payload"])
    if not order_validation.get("is_valid") or not sync_validation.get("is_valid"):
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_validation_failed",
            "errors": list(order_validation.get("errors") or []) + list(sync_validation.get("errors") or []),
            "packet": packet,
        }
    try:
        creator = draft_order_creator or create_order_with_lines
        result = creator(order_validation["cleaned_data"], sync_validation["cleaned_data"])
        return {
            "attempted": True,
            "success": bool((result or {}).get("success")),
            "status": "sam_live_stock_draft_order_created" if (result or {}).get("success") else "sam_live_stock_draft_order_create_failed",
            "result": result,
            "packet": packet,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_exception",
            "error": _clean(str(exc), 240),
            "packet": packet,
        }


def build_live_stock_owner_action_packet(order_id="", conversation_id="", document_id=""):
    order_id = _clean(order_id, 100)
    conversation_id = _clean(conversation_id, 100)
    document_id = _clean(document_id, 100)
    return {
        "version": "sam_live_stock_owner_action_packet_v1",
        "owner_gate_required": True,
        "reservation": {
            "allowed_for_sam_auto": False,
            "route": f"/api/orders/{order_id}/reserve" if order_id else "",
            "method": "POST",
            "rule": "Owner/operator must approve. SAM must not reserve automatically.",
        },
        "send_for_approval": {
            "allowed_for_sam_auto": False,
            "route": f"/api/orders/{order_id}/send-for-approval" if order_id else "",
            "method": "POST",
        },
        "quote_prepare": {
            "allowed_for_sam_auto": False,
            "route": f"/api/orders/{order_id}/quote/prepare-send" if order_id else "",
            "method": "POST",
            "conversation_id": conversation_id,
        },
        "quote_send_confirmed": {
            "allowed_for_sam_auto": False,
            "route": f"/api/orders/{order_id}/quote/send-latest-confirmed" if order_id else "",
            "method": "POST",
            "document_id": document_id,
            "conversation_id": conversation_id,
            "rule": "Only after owner confirms the latest sendable quote.",
        },
    }


def review_sam_live_stock_conversation(inbound, facts, decision, context_packet=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    text = _normal_text(inbound.get("content"))
    reply = _clean(decision.get("suggested_reply_text"), 1800)
    missing = decision.get("missing_fields") if isinstance(decision.get("missing_fields"), list) else []
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    issues = []
    blocked = []
    escalation_reasons = []
    score = 100

    if _hostile_or_scam_signal(text):
        escalation_reasons.append("hostile_or_scam_location_challenge")
        issues.append("close_conversation_recommended")
        score -= 35
    if _price_challenge_signal(text):
        escalation_reasons.append("pricing_challenge_or_negotiation")
        issues.append("no_negotiation_posture")
        score -= 25
    if _natural_close_signal(text):
        issues.append("natural_close_no_reply_needed")
        score -= 5
    if facts.get("breeding_interest"):
        escalation_reasons.append("breeding_or_replacement_interest")
        score -= 30
    if facts.get("reservation_requested"):
        escalation_reasons.append("reservation_request")
        score -= 20
    if blockers:
        escalation_reasons.extend(str(item) for item in blockers)
        score -= min(40, 10 * len(blockers))
    if decision.get("sales_lane") != LANE_LIVE_STOCK:
        escalation_reasons.append("wrong_or_unclear_lane")
        score -= 20
    if missing:
        issues.append("missing_fields:" + ",".join(missing[:5]))
        score -= min(20, 5 * len(missing))
    if reply:
        lowered = reply.lower()
        unsafe_reply_patterns = [
            (r"\breserved\b|\bheld\b|\bbooked\b", "implies_reservation"),
            (r"\bpayment\b.{0,40}\b(confirmed|received|cleared|reflects)\b", "confirms_payment"),
            (r"\b(for sale|available|book now|discount|cheap|budget)\b", "unsafe_sales_or_discount_language"),
            (r"\bexact farm|farm pin|our location\b", "shares_or_invites_exact_location"),
        ]
        for pattern, label in unsafe_reply_patterns:
            if re.search(pattern, lowered):
                blocked.append(label)
                score -= 35
        if reply.count("?") > 1:
            issues.append("asks_more_than_one_question")
            score -= 10
        if len(reply) > 700:
            issues.append("too_long_for_whatsapp")
            score -= 8

    score = max(0, min(100, score))
    safe_to_send = not blocked and score >= 96 and not escalation_reasons and not _natural_close_signal(text)
    if _natural_close_signal(text):
        safe_to_send = False
    return {
        "version": "sam_live_stock_conversation_review_v1",
        "score": score,
        "confidence_target": 96,
        "safe_to_send": safe_to_send,
        "owner_send_required": not safe_to_send and bool(reply),
        "no_reply_recommended": _natural_close_signal(text),
        "escalation_required": bool(escalation_reasons or blocked),
        "escalation_reasons": sorted(set(escalation_reasons)),
        "issues": sorted(set(issues)),
        "blocked_reasons": sorted(set(blocked)),
        "conversation_mode_recommendation": "HUMAN" if escalation_reasons or blocked else "AUTO",
        "recommended_action": _conversation_review_action(text, missing, escalation_reasons, blocked, reply),
    }


def build_sam_live_stock_escalation_packet(inbound, facts, decision, review=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    review = review if isinstance(review, dict) else review_sam_live_stock_conversation(inbound, facts, decision)
    conversation_id = _clean(inbound.get("conversation_id"), 100)
    suggested = _owner_escalation_reply(inbound, facts, decision, review)
    escalation_id = _escalation_id(conversation_id, inbound.get("message_id"), inbound.get("content"))
    return {
        "version": "sam_live_stock_escalation_packet_v1",
        "escalation_id": escalation_id,
        "source_agent": "sam_live_stock",
        "conversation_id": conversation_id,
        "message_id": _clean(inbound.get("message_id"), 100),
        "customer_name": _clean(inbound.get("customer_name"), 120),
        "customer_phone": _clean(inbound.get("customer_phone"), 80),
        "channel": _clean(inbound.get("channel"), 80),
        "customer_message_excerpt": _clean(inbound.get("content"), 500),
        "summary": _live_stock_escalation_summary(facts, review),
        "risk_reasons": review.get("escalation_reasons") or review.get("blocked_reasons") or [],
        "score": review.get("score"),
        "suggested_response": suggested,
        "recommended_mode": review.get("conversation_mode_recommendation") or "HUMAN",
        "owner_actions": [
            "approve_send",
            "edit_send",
            "close_without_reply",
            "keep_human_mode",
            "return_to_auto",
        ],
        "telegram_packet": {
            "text": _telegram_escalation_text(escalation_id, inbound, facts, review, suggested),
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "Approve Send", "callback_data": f"sam_live_approve_send:{escalation_id}"},
                        {"text": "Close", "callback_data": f"sam_live_close:{escalation_id}"},
                    ],
                    [
                        {"text": "Keep Human", "callback_data": f"sam_live_human:{escalation_id}"},
                        {"text": "Resolved", "callback_data": f"sam_live_resolved:{escalation_id}"},
                    ],
                ],
            },
        },
        "chatwoot_takeover": build_sam_live_stock_chatwoot_takeover_payload(conversation_id, mode="HUMAN", reason="sam_live_stock_escalation"),
        **_authority_flags(),
    }


def build_sam_live_stock_chatwoot_takeover_payload(conversation_id, mode="HUMAN", reason=""):
    mode = "HUMAN" if str(mode or "").strip().upper() == "HUMAN" else "AUTO"
    reason = _clean(reason or ("owner_takeover" if mode == "HUMAN" else "owner_resolved"), 120)
    labels = ["sam_live_stock", "owner_handoff"] if mode == "HUMAN" else ["sam_live_stock", "owner_resolved"]
    return {
        "version": "sam_live_stock_chatwoot_takeover_v1",
        "conversation_id": _clean(conversation_id, 100),
        "mode": mode,
        "custom_attributes": {
            "conversation_mode": mode,
            "sales_lane": "live_stock_sales",
            "sam_live_stock_gate": reason,
        },
        "labels": labels,
        "calls_chatwoot": False,
        "rule": "Preserve existing Chatwoot attributes before writing this payload.",
    }


def build_sam_live_stock_owner_send_packet(conversation_id, message, escalation_id="", owner=""):
    return {
        "version": "sam_live_stock_owner_send_packet_v1",
        "conversation_id": _clean(conversation_id, 100),
        "message": _clean_multiline(message, 1800),
        "escalation_id": _clean(escalation_id, 120),
        "owner": _clean(owner or "owner", 120),
        "requires_owner_approval": True,
        "send_env": OWNER_SEND_ENABLED_ENV,
        "authority": {
            **_authority_flags(),
            "sends_customer_message": False,
            "calls_chatwoot": False,
        },
    }


def send_owner_approved_live_stock_reply(conversation_id, message, *, environ=None, chatwoot_sender=None, owner="owner", escalation_id=""):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_owner_send_packet(conversation_id, message, escalation_id=escalation_id, owner=owner)
    if not _truthy(source.get(OWNER_SEND_ENABLED_ENV)):
        return {
            "success": False,
            "status": "sam_live_stock_owner_send_disabled",
            "packet": packet,
            **_authority_flags(),
        }, 409
    if not packet["conversation_id"]:
        return {"success": False, "status": "conversation_id_required", "packet": packet, **_authority_flags()}, 400
    if not packet["message"]:
        return {"success": False, "status": "message_required", "packet": packet, **_authority_flags()}, 400
    try:
        sender = chatwoot_sender or _send_chatwoot_message
        sent = sender(packet["conversation_id"], packet["message"], source)
        return {
            "success": True,
            "status": "sam_live_stock_owner_reply_sent",
            "packet": packet,
            "chatwoot": sent,
            **_authority_flags(),
            "sends_customer_message": True,
            "calls_chatwoot": True,
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "status": "sam_live_stock_owner_reply_send_failed",
            "error_type": exc.__class__.__name__,
            "error": _clean(str(exc), 240),
            "packet": packet,
            **_authority_flags(),
        }, 502


def build_sam_live_stock_resolved_cleanup_packet(escalation_id, telegram_chat_id="", telegram_message_id="", conversation_id=""):
    return {
        "version": "sam_live_stock_resolved_cleanup_packet_v1",
        "escalation_id": _clean(escalation_id, 120),
        "conversation_id": _clean(conversation_id, 100),
        "telegram_chat_id": _clean(telegram_chat_id, 100),
        "telegram_message_id": _clean(telegram_message_id, 100),
        "recommended_action": "delete_telegram_notification" if telegram_chat_id and telegram_message_id else "mark_resolved_no_telegram_delete",
        "delete_allowed": bool(telegram_chat_id and telegram_message_id),
        "rule": "Delete only the escalation notification message that belongs to this escalation. Never delete unrelated Telegram messages.",
        **_authority_flags(),
    }


def build_sam_live_stock_smoke_pack():
    scenarios = [
        {
            "name": "vague_live_pig_interest",
            "message": "Do you have pigs for sale?",
            "expected_lane": LANE_LIVE_STOCK,
            "expected_guard": "ask_category_or_confirm_live_stock",
        },
        {
            "name": "clear_weaner_request",
            "message": "I need 3 female weaners around 10 to 15kg next week in Riversdale.",
            "expected_lane": LANE_LIVE_STOCK,
            "expected_guard": "facts_and_availability_check",
        },
        {
            "name": "mixed_meat_and_live",
            "message": "I want pork for the freezer and maybe two piglets.",
            "expected_lane": "unclear",
            "expected_guard": "clarify_before_write",
        },
        {
            "name": "breeding_stock_gate",
            "message": "I want two breeding gilts.",
            "expected_lane": LANE_LIVE_STOCK,
            "expected_guard": "owner_gate_breeding",
        },
        {
            "name": "reservation_request_gate",
            "message": "Keep those 3 weaners for me.",
            "expected_lane": LANE_LIVE_STOCK,
            "expected_guard": "owner_gate_reservation",
        },
        {
            "name": "meat_wrong_lane",
            "message": "I want pork chops and a freezer pack.",
            "expected_lane": "meat_sales",
            "expected_guard": "wrong_lane_no_live_stock_write",
        },
    ]
    return {
        "version": "sam_live_stock_smoke_pack_v1",
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "required_pass_rate": "100%",
        "must_verify": [
            "no customer sends unless explicitly approved in a future stage",
            "no wrong lane writes",
            "no reservation without owner action",
            "no breeding stock automation",
            "draft order creation only when env gate is enabled and packet validates",
        ],
    }


def build_sam_live_stock_go_live_checklist(environ=None):
    source = environ if environ is not None else os.environ
    checks = {
        "webhook_enabled": _truthy(source.get(WEBHOOK_ENABLED_ENV)),
        "webhook_token_configured": len(str(source.get(WEBHOOK_TOKEN_ENV, "") or "").strip()) >= MIN_TOKEN_CHARS,
        "intake_write_enabled": _truthy(source.get(INTAKE_WRITE_ENABLED_ENV)),
        "draft_order_create_enabled": _truthy(source.get(DRAFT_ORDER_CREATE_ENABLED_ENV)),
        "autoreply_disabled": not _truthy(source.get(AUTOREPLY_ENABLED_ENV)),
        "llm_disabled_for_launch": not _truthy(source.get(LLM_ENABLED_ENV)),
    }
    blockers = []
    if not checks["webhook_enabled"]:
        blockers.append("webhook_disabled")
    if not checks["webhook_token_configured"]:
        blockers.append("webhook_token_missing_or_short")
    if checks["draft_order_create_enabled"]:
        blockers.append("draft_order_create_enabled_requires_owner_same-day_confirmation")
    if not checks["autoreply_disabled"]:
        blockers.append("autoreply_must_remain_disabled_for_first_live_stock_launch")
    return {
        "version": "sam_live_stock_go_live_checklist_v1",
        "checks": checks,
        "blockers": blockers,
        "ready_for_controlled_smoke": not blockers or blockers == ["webhook_disabled"],
        "ready_for_public_launch": False,
        "launch_rule": "Public launch needs owner-confirmed pricing, Beacon compliant post, controlled Chatwoot smoke, and owner command visibility.",
    }
    try:
        writer = intake_writer or update_intake_state
        result = writer(validation["cleaned_data"])
        return {
            "attempted": True,
            "success": bool((result or {}).get("success")),
            "status": "sam_live_stock_intake_written" if (result or {}).get("success") else "sam_live_stock_intake_write_failed",
            "result": result,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_intake_write_exception",
            "error": _clean(str(exc), 240),
            "payload": payload,
        }


def _safe_reply_draft(facts, route, missing, availability, blockers, price_answer_packet=None):
    if route["lane"] != LANE_LIVE_STOCK:
        if route["lane"] == "owner_handoff" and _payment_or_pop_interest(facts):
            return (
                "Thanks, I can note the payment message, but POP does not make live animals yours until the farm confirms the bank receipt "
                "and the owner approves the animals on the system."
            )
        return "Just so I help you correctly: are you looking for live pigs, pork for the freezer, or slaughter help?"
    if facts.get("breeding_interest"):
        return "I can note that, but breeding or replacement animals need farm review before anything is promised."
    if facts.get("reservation_requested"):
        return "I can note your interest, but I cannot confirm those animals for you until the farm approves it on the system."
    if facts.get("quote_requested"):
        price_reply = _price_answer_reply(facts, price_answer_packet)
        if price_reply:
            return price_reply
    if missing:
        return _question_for_missing(missing[0])
    if availability.get("success") and int(availability.get("matched_count") or 0) <= 0:
        return "I do not want to over-promise that exact group. I can check nearby suitable options for farm review."
    return "I have the main live-pig details. I will check the current list before anything is promised."


def _price_answer_reply(facts, packet):
    facts = facts if isinstance(facts, dict) else {}
    packet = packet if isinstance(packet, dict) else {}
    if not packet.get("can_answer_price"):
        if _blank(facts.get("category")):
            return "What size or type are you asking about: piglets, weaners, growers, finishers, or ready-for-slaughter pigs?"
        if _blank(facts.get("weight_range")):
            return "What weight band should I price for you?"
        return "I do not want to guess the price. I can check the current SAM price list for farm review."
    quantity = _quantity_number(packet.get("requested_quantity"))
    quantity_label = f"{_quantity_label(quantity)} x " if quantity > 0 else ""
    sex = packet.get("requested_sex")
    sex_label = "" if str(sex or "").lower() == "any" else f"{sex} "
    category = packet.get("requested_category") or (packet.get("pricing") or {}).get("sale_category") or "live pig"
    weight_band = _human_weight_band(packet.get("requested_weight_range") or (packet.get("pricing") or {}).get("weight_band"))
    unit = _money_label(packet.get("unit_price"))
    lines = [
        "Current SAM Live price estimate:",
        f"- {quantity_label}{sex_label}{category}, {weight_band}: {unit} each",
    ]
    if quantity > 1 and packet.get("estimated_total") not in ("", None):
        lines.append(f"- Estimated total: {_money_label(packet.get('estimated_total'))}")
    lines.append("- This is not a reservation.")
    lines.append("- The farm must confirm the actual animals before anything is promised.")
    return "\n".join(lines)


def _live_stock_price_rule_for_packet(facts, match_packet):
    facts = facts if isinstance(facts, dict) else {}
    match_packet = match_packet if isinstance(match_packet, dict) else {}
    sample = match_packet.get("matched_sample") if isinstance(match_packet.get("matched_sample"), list) else []
    first = sample[0] if sample and isinstance(sample[0], dict) else {}
    category = first.get("sale_category") or facts.get("category")
    weight_band = first.get("weight_band") or _normal_intake_weight_range(
        facts.get("weight_range"),
        _normal_intake_category(facts.get("category")),
    )
    sex = first.get("sex") or facts.get("sex")
    return resolve_live_stock_price_rule(category, weight_band, sex)


def _quantity_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    return int(number) if number.is_integer() else number


def _quantity_label(value):
    number = _quantity_number(value)
    return str(int(number)) if isinstance(number, int) or float(number).is_integer() else str(number)


def _money_label(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "price unavailable"
    if amount.is_integer():
        return f"R{int(amount):,}"
    return f"R{amount:,.2f}"


def _human_weight_band(value):
    text = _clean(value, 80)
    if not text:
        return "weight band not confirmed"
    return text.replace("_to_", "-").replace("_Kg", " kg").replace("_kg", " kg")


def _question_for_missing(field):
    return {
        "category": "What size or type are you looking for: piglets, weaners, growers, or finishers?",
        "quantity": "How many live pigs are you looking for?",
        "sex": "Do you need males, females, or does the sex not matter if the size is right?",
        "timing": "When would you want them?",
        "location": "Where would they need to go?",
    }.get(field, "What detail should I note for the farm?")


def _missing_live_stock_fields(facts):
    missing = []
    for key in ("category", "quantity", "sex", "timing", "location"):
        if _blank(facts.get(key)):
            missing.append(key)
    return missing


def _prior_context_from_intake(intake):
    intake = intake if isinstance(intake, dict) else {}
    known = intake.get("known_fields") if isinstance(intake.get("known_fields"), dict) else {}
    items = intake.get("items") if isinstance(intake.get("items"), list) else []
    interest = {
        "location": known.get("collection_location") or "",
        "timing": known.get("collection_time_text") or known.get("collection_date") or "",
        "payment_method": known.get("payment_method") or "",
        "quote_requested": bool(known.get("quote_requested")),
        "order_commitment": bool(known.get("order_commitment")),
    }
    active_items = [item for item in items if isinstance(item, dict) and str(item.get("status") or "").lower() == "active"]
    if active_items:
        item = active_items[0]
        interest.update({
            "quantity": item.get("quantity") or "",
            "category": item.get("category") or "",
            "weight_range": item.get("weight_range") or "",
            "sex": item.get("sex") or "",
        })
    return {"interest": interest, "source": "order_intake_context"} if any(interest.values()) else {}


def _extract_category(text):
    if _has_any(text, ("piglet", "piglets")):
        return "piglet"
    if _has_any(text, ("weaner", "weaners")):
        return "weaner"
    if _has_any(text, ("grower", "growers")):
        return "grower"
    if _has_any(text, ("finisher", "finishers")):
        return "finisher"
    if _has_any(text, ("ready for slaughter", "slaughter pig", "80kg", "85kg", "90kg")):
        return "ready_for_slaughter"
    if _has_any(text, ("live pig", "live pigs", "pigs to raise", "buy pigs", "pigs for sale", "pig for sale", "pigs available")):
        return "live_pig"
    return ""


def _extract_quantity(text):
    match = re.search(
        r"\b(\d{1,3})\s+(?:x\s+)?(?:(?:live|breeding)\s+)?"
        r"(?:male|female|males|females|piglets|pigs|weaners|growers|finishers|gilts|boars|sows)\b",
        text,
    )
    if match:
        return int(match.group(1))
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    for word, value in number_words.items():
        if re.search(
            rf"\b{word}\s+(?:(?:live|breeding)\s+)?"
            r"(?:male|female|males|females|piglets|pigs|weaners|growers|finishers|gilts|boars|sows)\b",
            text,
        ):
            return value
    return ""


def _extract_sex(text):
    male = _has_any(text, ("male", "males", "boar", "boars"))
    female = _has_any(text, ("female", "females", "gilt", "gilts", "sow", "sows"))
    if male and female:
        return "split"
    if female:
        return "female"
    if male:
        return "male"
    if _has_any(text, ("any sex", "sex does not matter", "doesn't matter", "no preference")):
        return "any"
    return ""


def _extract_weight_range(text):
    range_match = re.search(r"\b(\d{1,3})\s*(?:kg)?\s*(?:-|to|and)\s*(\d{1,3})\s*kg\b", text)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        if low > high:
            low, high = high, low
        return f"{low}-{high} kg"
    single = re.search(r"\b(?:around|about|roughly|\+-)?\s*(\d{1,3})\s*kg\b", text)
    if single:
        weight = int(single.group(1))
        return f"around {weight} kg"
    return ""


def _extract_timing(text):
    for phrase in ("today", "tomorrow", "next week", "this week", "month end", "weekend"):
        if phrase in text:
            return phrase
    weekday = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text)
    if weekday:
        return weekday.group(1)
    return ""


def _extract_location(text):
    known = ("riversdale", "albertinia", "still bay", "stilbaai", "jongensfontein", "heidelberg", "mossel bay")
    for place in known:
        if place in text:
            return "Still Bay" if place == "still bay" else ("Stilbaai" if place == "stilbaai" else place.title())
    return ""


def _extract_transport(text):
    if _has_any(text, ("deliver", "delivery", "bring them", "drop off")):
        return "delivery_requested"
    if _has_any(text, ("collect", "collection", "pick up", "pickup", "afhaal")):
        return "collection_requested"
    return ""


def _extract_payment(text):
    if _has_any(text, ("eft", "bank transfer", "transfer", "oorplasing")):
        return "EFT"
    if _has_any(text, ("cash", "kontant")):
        return "cash_requested"
    return ""


def _asks_quote(text):
    return _has_any(text, ("price", "cost", "how much", "quote", "quotation", "prys"))


def _asks_reservation(text):
    return _has_any(text, (
        "reserve",
        "hold",
        "hold them",
        "hold those",
        "hold the",
        "keep them",
        "keep those",
        "keep the",
        "book them",
        "hou hulle",
    ))


def _payment_or_pop_interest(facts):
    text = _normal_text(" ".join(str(value or "") for value in (facts or {}).values()))
    return _has_any(text, ("pop", "proof of payment", "paid", "payment", "eft"))


def _category_from_weight_range(weight_range):
    weight = _representative_weight(weight_range)
    if not weight:
        return ""
    if weight < 10:
        return "piglet"
    if weight < 25:
        return "weaner"
    if weight < 50:
        return "grower"
    if weight < 75:
        return "finisher"
    return "ready_for_slaughter"


def _representative_weight(weight_range):
    text = str(weight_range or "")
    numbers = [int(value) for value in re.findall(r"\d{1,3}", text)]
    if not numbers:
        return 0
    if len(numbers) >= 2:
        return int(round((numbers[0] + numbers[1]) / 2))
    return numbers[0]


def _row_available_for_live_stock(row):
    if "live_stock_sale_eligible" in row and row.get("live_stock_sale_eligible") is not True:
        return False
    status = _normal_text(row.get("status"))
    on_farm = _normal_text(row.get("on_farm"))
    reserved = _normal_text(row.get("reserved_status"))
    available = _normal_text(row.get("available_for_sale"))
    purpose = _normal_text(row.get("purpose"))
    if status in {"sold", "exited", "dead", "terminal"}:
        return False
    if on_farm and on_farm not in {"yes", "true", "1", "on farm"}:
        return False
    if reserved and reserved not in {"", "available", "no", "not reserved"}:
        return False
    if available and available not in {"yes", "true", "1"}:
        return False
    if purpose and purpose != "sale":
        return False
    return True


def _row_category_tokens(row):
    text = _normal_text(" ".join(str(row.get(key) or "") for key in (
        "sale_category",
        "suggested_price_category",
        "calculated_stage",
        "weight_band",
    )))
    tokens = set()
    if "piglet" in text:
        tokens.add("piglet")
    if "weaner" in text:
        tokens.add("weaner")
    if "grower" in text or "live_sale_candidate" in text:
        tokens.add("grower")
    if "finisher" in text:
        tokens.add("finisher")
    if "slaughter" in text:
        tokens.add("ready_for_slaughter")
    if not tokens:
        tokens.add("live_pig")
    return tokens


def _row_matches_requested_weight(row, requested_weight_range):
    requested = _weight_bounds_from_text(requested_weight_range)
    if not requested:
        return True
    low, high = requested
    row_weight = row.get("current_weight_kg")
    try:
        if row_weight not in ("", None):
            weight = float(row_weight)
            return low <= weight <= high
    except (TypeError, ValueError):
        pass
    row_band = _weight_bounds_from_text(row.get("weight_band") or row.get("suggested_price_category") or "")
    if not row_band:
        return True
    row_low, row_high = row_band
    return row_low <= high and row_high >= low


def _weight_bounds_from_text(value):
    text = _normal_text(value).replace("_", " ")
    numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(numbers) >= 2:
        return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return None


def _availability_public_row(row):
    return {
        "pig_id": _clean(row.get("pig_id"), 80),
        "tag_number": _clean(row.get("tag_number"), 80),
        "sex": _clean(row.get("sex"), 40),
        "current_weight_kg": row.get("current_weight_kg"),
        "weight_band": _clean(row.get("weight_band"), 80),
        "sale_category": _clean(row.get("sale_category"), 120),
        "suggested_price_category": _clean(row.get("suggested_price_category"), 120),
    }


def _normal_category(value):
    text = _normal_text(value)
    aliases = {
        "piglets": "piglet",
        "weaners": "weaner",
        "growers": "grower",
        "finishers": "finisher",
    }
    return aliases.get(text, text)


def _normal_sex(value):
    text = _normal_text(value)
    if text in {"male", "males", "boar", "boars"}:
        return "male"
    if text in {"female", "females", "gilt", "gilts", "sow", "sows"}:
        return "female"
    if text in {"any", "no preference", "split"}:
        return text
    return ""


def _normal_chatwoot_message_type(payload):
    raw = payload.get("message_type_string")
    if raw in (None, ""):
        raw = payload.get("message_type")
    text = _clean(raw, 60).lower()
    if text in {"0", "incoming"}:
        return "incoming"
    if text in {"1", "outgoing"}:
        return "outgoing"
    if text in {"2", "activity", "template"}:
        return "activity"
    return text


def _normal_channel(payload, conversation):
    raw = " ".join([
        str(payload.get("channel") or ""),
        str(payload.get("inbox_channel") or ""),
        str((conversation.get("inbox") or {}).get("channel_type") if isinstance(conversation.get("inbox"), dict) else ""),
    ]).lower()
    if "whatsapp" in raw:
        return "chatwoot_whatsapp"
    if "facebook" in raw or "messenger" in raw:
        return "chatwoot_facebook"
    if "instagram" in raw:
        return "chatwoot_instagram"
    if "email" in raw:
        return "chatwoot_email"
    return "chatwoot"


def _ignored(status, event, message_type, content, conversation_id, customer_name, channel):
    return {
        "processable": False,
        "status": status,
        "event": event,
        "message_type": message_type,
        "content": content,
        "conversation_id": conversation_id,
        "customer_name": customer_name,
        "channel": channel,
    }


def _token_matches(headers, query_args, expected):
    authorization = str(headers.get("Authorization", "") or "").strip()
    if authorization.startswith("Bearer "):
        return hmac.compare_digest(authorization[len("Bearer "):].strip(), expected)
    provided = str(headers.get("X-Amadeus-Sam-Live-Stock-Webhook-Key", "") or "").strip()
    if provided:
        return hmac.compare_digest(provided, expected)
    provided = str(query_args.get("token") or query_args.get("sam_live_stock_token") or "").strip()
    return hmac.compare_digest(provided, expected)


def _denied(status, source):
    return {
        "success": False,
        "status": status,
        "processed": False,
        "sent": False,
        "policy": sam_live_stock_webhook_policy(source),
        **_authority_flags(),
    }


def _authority_flags(writes_order_intake=False, creates_order=False):
    return {
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": bool(creates_order),
        "reserves_stock": False,
        "changes_stock": False,
        "writes_farm_data": False,
        "writes_order_intake": bool(writes_order_intake),
        "writes_sales_transaction": False,
        "dispatch_enabled": False,
        "customer_public_output_enabled": False,
    }


def _live_stock_intake_item(facts):
    category = _normal_intake_category(facts.get("category"))
    quantity = facts.get("quantity")
    sex = _normal_intake_sex(facts.get("sex"))
    weight_range = _normal_intake_weight_range(facts.get("weight_range"), category)
    if not any([category, quantity, sex, weight_range]):
        return {}
    return {
        "item_key": "live_stock_primary",
        "quantity": quantity or "",
        "category": category,
        "weight_range": weight_range,
        "sex": sex,
        "intent_type": "primary",
        "status": "active",
        "last_match_status": "not_matched_stage_4",
        "notes": _clean(f"source=sam_live_stock_stage_4; original_weight_range={facts.get('weight_range') or ''}; transport={facts.get('transport_expectation') or ''}", 600),
    }


def _live_stock_sync_requested_item(facts):
    category = _normal_intake_category(facts.get("category"))
    weight_range = _normal_intake_weight_range(facts.get("weight_range"), category)
    quantity = facts.get("quantity")
    if not category or not weight_range or not quantity:
        return {}
    return {
        "request_item_key": "live_stock_primary",
        "category": category,
        "weight_range": weight_range,
        "sex": _normal_intake_sex(facts.get("sex")),
        "quantity": quantity,
        "intent_type": "primary",
        "status": "active",
        "notes": _clean("source=sam_live_stock_stage_5; owner_review_required=true", 600),
    }


def _normal_intake_category(value):
    category = _normal_category(value)
    return {
        "piglet": "Piglet",
        "weaner": "Weaner",
        "grower": "Grower",
        "finisher": "Finisher",
        "ready_for_slaughter": "Slaughter",
        "live_pig": "",
    }.get(category, "")


def _normal_intake_sex(value):
    sex = _normal_sex(value)
    return {
        "male": "Male",
        "female": "Female",
        "any": "Any",
        "split": "Any",
    }.get(sex, "Any")


def _normal_intake_location(value):
    text = _normal_text(value)
    if text == "riversdale":
        return "Riversdale"
    if text == "albertinia":
        return "Albertinia"
    return "Any"


def _normal_intake_payment(value):
    text = _normal_text(value)
    if text == "eft":
        return "EFT"
    if text == "cash_requested" or text == "cash":
        return "Cash"
    return ""


def _normal_intake_weight_range(value, category):
    text = _normal_text(value)
    numbers = [int(number) for number in re.findall(r"\b\d{1,3}\b", text)]
    if numbers:
        weight = min(numbers)
        return _weight_band_for_kg(weight)
    defaults = {
        "Piglet": "5_to_6_Kg",
        "Weaner": "10_to_14_Kg",
        "Grower": "30_to_34_Kg",
        "Finisher": "60_to_64_Kg",
        "Slaughter": "80_to_84_Kg",
    }
    return defaults.get(category, "")


def _weight_band_for_kg(weight):
    bands = [
        (2, 4, "2_to_4_Kg"),
        (5, 6, "5_to_6_Kg"),
        (7, 9, "7_to_9_Kg"),
        (10, 14, "10_to_14_Kg"),
        (15, 19, "15_to_19_Kg"),
        (20, 24, "20_to_24_Kg"),
        (25, 29, "25_to_29_Kg"),
        (30, 34, "30_to_34_Kg"),
        (35, 39, "35_to_39_Kg"),
        (40, 44, "40_to_44_Kg"),
        (45, 49, "45_to_49_Kg"),
        (50, 54, "50_to_54_Kg"),
        (55, 59, "55_to_59_Kg"),
        (60, 64, "60_to_64_Kg"),
        (65, 69, "65_to_69_Kg"),
        (70, 74, "70_to_74_Kg"),
        (75, 79, "75_to_79_Kg"),
        (80, 84, "80_to_84_Kg"),
        (85, 89, "85_to_89_Kg"),
        (90, 94, "90_to_94_Kg"),
    ]
    for low, high, label in bands:
        if low <= weight <= high:
            return label
    return ""


def _intake_notes(facts, decision):
    pieces = [
        "source=sam_live_stock_stage_4",
        f"lane_confidence={facts.get('lane_confidence', '')}",
        f"original_location={facts.get('location') or ''}",
        f"transport={facts.get('transport_expectation') or ''}",
        f"missing={','.join(decision.get('missing_fields') or []) if isinstance(decision.get('missing_fields'), list) else ''}",
    ]
    return _clean("; ".join(piece for piece in pieces if piece), 600)


def _integration_failure(status, exc):
    return {"status": status, "error": _clean(str(exc), 240)}


def _hostile_or_scam_signal(text):
    text = _normal_text(text)
    return _has_any(text, (
        "scam",
        "scammer",
        "fake",
        "not real",
        "send location now",
        "exact location",
        "farm pin",
        "drop pin",
        "waar is julle plaas",
        "stuur location",
    ))


def _price_challenge_signal(text):
    text = _normal_text(text)
    return _has_any(text, (
        "too expensive",
        "te duur",
        "cheaper",
        "discount",
        "best price",
        "negotiate",
        "your price is too high",
        "i can get cheaper",
    ))


def _natural_close_signal(text):
    text = _normal_text(text)
    if not text:
        return False
    text = re.sub(r"[,.;:!]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return bool(re.fullmatch(
        r"(thanks|thank you|thanks have a good day|thank you have a good day|thx|ok|okay|great|cool|bye|goodbye|have a good day|will let you know|sal laat weet|dankie|reg dankie|goed dankie)[.! ]*",
        text,
    ))


def _conversation_review_action(text, missing, escalation_reasons, blocked, reply):
    if _natural_close_signal(text):
        return "no_reply_natural_close"
    if escalation_reasons or blocked:
        return "owner_handoff"
    if missing:
        return "ask_one_missing_fact"
    if reply:
        return "owner_review_send_candidate"
    return "monitor"


def _owner_escalation_reply(inbound, facts, decision, review):
    text = _normal_text((inbound or {}).get("content"))
    reasons = set(review.get("escalation_reasons") or [])
    if "hostile_or_scam_location_challenge" in reasons or _hostile_or_scam_signal(text):
        return (
            "I understand your concern. In that case it is better that we leave it here. "
            "I do not want to waste your time or mine trying to convince you after you have already made up your mind. "
            "Thanks for showing interest, and have a good day."
        )
    if "pricing_challenge_or_negotiation" in reasons or _price_challenge_signal(text):
        return "I understand that our animals and pricing will not fit everyone's budget. Thanks for showing interest."
    return _clean((decision or {}).get("suggested_reply_text"), 1800)


def _live_stock_escalation_summary(facts, review):
    facts = facts if isinstance(facts, dict) else {}
    review = review if isinstance(review, dict) else {}
    pieces = [
        "SAM Live Stock owner review needed",
        f"score={review.get('score', '')}",
        f"category={facts.get('category') or '-'}",
        f"quantity={facts.get('quantity') or '-'}",
        f"sex={facts.get('sex') or '-'}",
        f"location={facts.get('location') or '-'}",
    ]
    reasons = review.get("escalation_reasons") or review.get("blocked_reasons") or []
    if reasons:
        pieces.append("reasons=" + ",".join(str(item) for item in reasons[:5]))
    return _clean("; ".join(pieces), 500)


def _telegram_escalation_text(escalation_id, inbound, facts, review, suggested):
    return _clean(
        "\n".join([
            "SAM Live Stock escalation",
            f"ID: {escalation_id}",
            f"Conversation: {(inbound or {}).get('conversation_id') or '-'}",
            f"Customer: {(inbound or {}).get('customer_name') or '-'}",
            f"Score: {(review or {}).get('score', '-')}",
            f"Reason: {', '.join((review or {}).get('escalation_reasons') or (review or {}).get('blocked_reasons') or []) or '-'}",
            "",
            f"Customer: {_clean((inbound or {}).get('content'), 350)}",
            "",
            f"Suggested: {suggested}",
        ]),
        3500,
    )


def _escalation_id(conversation_id, message_id, content):
    raw = f"{conversation_id}|{message_id}|{content}"
    return "SAM-LIVE-ESC-" + hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:10].upper()


def _send_chatwoot_message(conversation_id, message, source):
    conversation_id = _clean(conversation_id, 100)
    message = _clean_multiline(message, 1800)
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not conversation_id:
        raise RuntimeError("conversation_id is required")
    if not message:
        raise RuntimeError("message is required")
    if not base_url:
        raise RuntimeError("CHATWOOT_BASE_URL is required")
    if not account_id:
        raise RuntimeError("CHATWOOT_ACCOUNT_ID is required")
    if not token:
        raise RuntimeError("CHATWOOT_API_ACCESS_TOKEN is required")
    body = {"content": message, "message_type": "outgoing", "private": False}
    request = urllib_request.Request(
        f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json", "api_access_token": token},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": getattr(response, "status", 200),
                "body": json.loads(raw or "{}"),
            }
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"chatwoot_http_{exc.code}") from exc


def _configured_model(source):
    return str(source.get(AGENT_V3_MODEL_ENV) or source.get(LLM_MODEL_ENV) or "").strip()


def _normal_text(value):
    text = str(value or "").lower()
    text = text.replace("livestock", "live stock").replace("live-stock", "live stock")
    text = re.sub(r"[^a-z0-9/%+.,;\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_any(text, phrases):
    for phrase in phrases:
        phrase = str(phrase or "").strip()
        if not phrase:
            continue
        if re.fullmatch(r"[a-z0-9]+", phrase):
            if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text):
                return True
        elif phrase in text:
            return True
    return False


def _blank(value):
    return value is None or str(value).strip() == ""


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _clean_multiline(value, limit):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)[:limit]
