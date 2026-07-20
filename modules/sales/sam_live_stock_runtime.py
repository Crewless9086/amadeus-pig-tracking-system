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
from modules.orders.order_line_sync import sync_order_lines_from_request
from modules.orders.order_service import create_order_with_lines
from modules.orders.order_validation import validate_new_order_payload, validate_sync_order_lines_payload
from modules.pig_weights.pig_weights_service import get_sales_availability
from modules.sales.sam_farm_knowledge import load_sam_farm_knowledge, public_profile
from modules.sales.sam_pricing import resolve_live_stock_price_rule
from modules.sales.sam_sales_router import LANE_FARM_GENERAL, LANE_LIVE_STOCK, classify_sam_sales_lane
from modules.sales.sam_conversation_state import plan_live_stock_next_action
from modules.sales.sam_live_stock_understanding import understand_live_stock_inbound
from modules.sales.sam_live_stock_media import classify_chatwoot_image, media_policy, transcribe_chatwoot_voice
from modules.charlie.agent_runtime import delegate_to_agent


WEBHOOK_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED"
WEBHOOK_TOKEN_ENV = "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN"
AUTOREPLY_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED"
LLM_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED"
AGENT_V3_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_AGENT_V3_ENABLED"
LLM_MODEL_ENV = "SAM_LIVE_STOCK_BACKEND_LLM_MODEL"
AGENT_V3_MODEL_ENV = "SAM_LIVE_STOCK_BACKEND_AGENT_V3_MODEL"
LLM_URL_ENV = "SAM_LIVE_STOCK_BACKEND_LLM_URL"
LLM_TIMEOUT_ENV = "SAM_LIVE_STOCK_BACKEND_LLM_TIMEOUT_SECONDS"
OWNER_EXAMPLE_RETRIEVAL_ENABLED_ENV = "SAM_LIVE_STOCK_OWNER_EXAMPLE_RETRIEVAL_ENABLED"
MEAT_PUBLIC_OFFER_ENABLED_ENV = "SAM_MEAT_PUBLIC_OFFER_ENABLED"
INTAKE_WRITE_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED"
DRAFT_ORDER_CREATE_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED"
OWNER_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED"
CHATWOOT_BASE_URL_ENV = "CHATWOOT_BASE_URL"
CHATWOOT_ACCOUNT_ID_ENV = "CHATWOOT_ACCOUNT_ID"
CHATWOOT_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
CHATWOOT_TOKEN_FALLBACK_ENV = "CHATWOOT_API_TOKEN"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_LLM_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
MIN_TOKEN_CHARS = 32

RUNTIME_VERSION = "sam_live_stock_read_only_v1"

SAM_LIVE_STOCK_DURABLE_NEXT_ACTIONS = {
    "answer_general_info",
    "answer_location",
    "answer_price",
    "ask_one_missing_detail",
    "prepare_draft_order",
    "update_draft_order",
    "prepare_quote",
    "prepare_picture_response",
    "answer_delivery_policy",
    "confirm_collection",
    "propose_breeding_stock_mix",
    "no_reply_needed",
    "escalate",
}


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
        "llm_enabled": _truthy(source.get(LLM_ENABLED_ENV)) and llm_configured,
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
        "owner_example_retrieval_enabled": _owner_example_retrieval_enabled(source),
        "owner_example_retrieval_env": OWNER_EXAMPLE_RETRIEVAL_ENABLED_ENV,
        "owner_example_retrieval_default": "enabled_unless_env_is_false",
        "meat_public_offer_enabled": _meat_public_offer_enabled(source),
        "meat_public_offer_env": MEAT_PUBLIC_OFFER_ENABLED_ENV,
        "media": media_policy(source),
        "api_key_env": OPENAI_API_KEY_ENV,
        "llm_default_model": DEFAULT_LLM_MODEL,
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
    conversation_history_loader=None,
    availability_loader=None,
    intake_writer=None,
    draft_order_creator=None,
    draft_order_syncer=None,
    llm_drafter=None,
    owner_example_loader=None,
    voice_transcriber=None,
    image_classifier=None,
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

    understanding = understand_live_stock_inbound(
        inbound,
        payload,
        voice_transcriber=voice_transcriber or (lambda attachment, body: transcribe_chatwoot_voice(attachment, body, environ=source)),
        image_classifier=image_classifier or (lambda attachment, body: classify_chatwoot_image(attachment, body, environ=source)),
    )
    inbound["original_content"] = inbound.get("content") or ""
    inbound["content"] = understanding.get("effective_text") or inbound.get("content") or ""
    inbound["understanding"] = understanding

    facts = extract_live_stock_facts(inbound["content"], inbound)
    facts["customer_language"] = understanding.get("language") or "unknown"
    facts["message_intent"] = understanding.get("message_intent") or "unclear"
    facts["media_review_required"] = bool(understanding.get("requires_media_review"))
    context_packet = load_live_stock_read_context(
        inbound,
        facts,
        intake_context_loader=intake_context_loader,
        conversation_history_loader=conversation_history_loader,
        availability_loader=availability_loader,
        environ=source,
    )
    facts = merge_prior_live_stock_context(facts, context_packet.get("prior_context") or {})
    decision = build_sam_live_stock_decision(
        inbound,
        facts,
        context_packet,
        source,
        llm_drafter=llm_drafter,
        owner_example_loader=owner_example_loader,
    )
    conversation_review = review_sam_live_stock_conversation(inbound, facts, decision, context_packet)
    if _llm_reply_needs_fallback(decision, conversation_review):
        decision["llm_draft_review"] = {
            "status": "rejected_by_safety_review",
            "blocked_reasons": conversation_review.get("blocked_reasons", []),
            "escalation_reasons": conversation_review.get("escalation_reasons", []),
            "original_reply_text": decision.get("suggested_reply_text", ""),
        }
        decision["suggested_reply_text"] = decision.get("deterministic_fallback_reply_text", "")
        decision["reply_source"] = "deterministic_fallback_after_llm_review"
        conversation_review = review_sam_live_stock_conversation(inbound, facts, decision, context_packet)
    decision["conversation_review"] = conversation_review
    if conversation_review.get("no_reply_recommended"):
        decision["suggested_reply_text"] = ""
        decision["reply_source"] = "natural_close_no_reply_guard"
        _set_durable_next_action(decision, "no_reply_needed")
    if conversation_review.get("escalation_required"):
        decision["owner_gate_required"] = True
        _set_durable_next_action(decision, "escalate")
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
        draft_order_syncer=draft_order_syncer,
    )
    if draft_order.get("attempted"):
        decision["draft_order"] = draft_order
        if draft_order.get("success"):
            _refresh_owner_action_packet_after_draft_order(inbound, facts, decision, draft_order)
            decision["draft_order_intake_writeback"] = write_live_stock_draft_order_link_to_intake(
                inbound,
                facts,
                draft_order,
                decision,
                intake_writer=intake_writer,
            )
        if not draft_order.get("success"):
            decision.setdefault("blockers", []).append(draft_order.get("status") or "draft_order_failed")
            decision["owner_gate_required"] = True
            _refresh_owner_action_packet_after_failed_draft_order(inbound, facts, decision, draft_order)
    return {
        "success": True,
        "status": "sam_live_stock_read_only_processed",
        "processed": True,
        "sent": False,
        "sam_decision": decision,
        "policy": policy,
        **_authority_flags(
            writes_order_intake=bool(intake_write.get("success")),
            creates_order=bool(draft_order.get("success") and draft_order.get("created_order")),
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
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    if not content and not attachments:
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
        "attachments": attachments,
    }


def extract_live_stock_facts(message, inbound=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    text = _normal_text(message)
    weight_range = _extract_weight_range(text)
    category = _extract_category(text)
    if not category and weight_range:
        category = _category_from_weight_range(weight_range)
    if category == "live_pig":
        category = _category_from_weight_range(weight_range) or category
    facts = {
        "latest_customer_message": _clean(inbound.get("content") or message, 1000),
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
    if (
        route["lane"] in {"unclear", "owner_handoff"}
        or (route["lane"] == LANE_FARM_GENERAL and _has_live_stock_fact_signal(facts))
    ) and (_has_live_stock_fact_signal(facts) or _has_live_stock_followup_signal(text)):
        route = {
            **route,
            "lane": LANE_LIVE_STOCK,
            "confidence": max(float(route.get("confidence") or 0), 0.82),
            "reasons": [
                *(route.get("reasons") if isinstance(route.get("reasons"), list) else []),
                "live_stock_fact_or_followup_signal",
            ],
        }
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
    conversation_history_loader=None,
    availability_loader=None,
    environ=None,
):
    inbound = inbound if isinstance(inbound, dict) else {}
    source = environ if environ is not None else os.environ
    context_errors = []
    prior_context = {}
    intake = {"success": False, "lookup_status": "not_loaded", "items": []}
    chatwoot_history = {"success": False, "status": "not_loaded", "messages": []}
    if inbound.get("conversation_id"):
        try:
            loader = intake_context_loader or get_intake_context
            intake = loader(inbound.get("conversation_id"))
            prior_context = _prior_context_from_intake(intake)
        except Exception as exc:
            context_errors.append(_integration_failure("order_intake_context_read_failed", exc))
            intake = {"success": False, "lookup_status": "read_failed", "items": []}
        try:
            history_loader = conversation_history_loader or load_chatwoot_conversation_history
            chatwoot_history = history_loader(inbound.get("conversation_id"), source)
            prior_context = _merge_prior_context_packets(
                prior_context,
                _prior_context_from_chatwoot_history(chatwoot_history, inbound),
            )
        except Exception as exc:
            context_errors.append(_integration_failure("chatwoot_conversation_history_read_failed", exc))
            chatwoot_history = {"success": False, "status": "read_failed", "messages": []}
    herdmaster_evidence = {}
    try:
        if availability_loader is not None:
            availability_rows = availability_loader()
        else:
            herdmaster_evidence, herdmaster_status = delegate_to_agent("herdmaster", {
                "goal": "Provide governed livestock sales candidates for SAM.",
                "question": str(inbound.get("content") or "Current livestock sales availability"),
                "capability": "sales_availability", "required_freshness": "live",
            })
            if herdmaster_status >= 400:
                raise RuntimeError(herdmaster_evidence.get("status") or "herdmaster_availability_failed")
            availability_rows = herdmaster_evidence.get("availability_rows") or []
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
        "chatwoot_history": _compact_chatwoot_history(chatwoot_history),
        "chatwoot_history_messages": _compact_chatwoot_history_messages(
            chatwoot_history,
            current_message_id=inbound.get("message_id"),
        ),
        "availability": availability,
        "agent_evidence": {"herdmaster": herdmaster_evidence} if herdmaster_evidence else {},
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


def load_chatwoot_conversation_history(conversation_id, environ=None, limit=20):
    source = environ if environ is not None else os.environ
    conversation_id = _clean(conversation_id, 100)
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV), 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV), 80)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not conversation_id:
        return {"success": False, "status": "conversation_id_required", "messages": []}
    if not base_url or not account_id or not token:
        return {"success": False, "status": "chatwoot_history_not_configured", "messages": []}
    request = urllib_request.Request(
        f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages",
        headers={"api_access_token": token},
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw or "{}")
    except urllib_error.HTTPError as exc:
        return {"success": False, "status": f"chatwoot_history_http_{exc.code}", "messages": []}
    payload = parsed.get("payload") if isinstance(parsed, dict) else parsed
    rows = payload if isinstance(payload, list) else []
    messages = []
    for row in rows[-max(int(limit or 20), 1):]:
        if not isinstance(row, dict):
            continue
        content = _clean_multiline(row.get("content"), 800)
        if not content:
            continue
        messages.append({
            "id": _clean(row.get("id"), 100),
            "message_type": row.get("message_type"),
            "content": content,
            "created_at": row.get("created_at"),
        })
    return {"success": True, "status": "loaded", "messages": messages}


def _prior_context_from_chatwoot_history(history, inbound):
    history = history if isinstance(history, dict) else {}
    if not history.get("success"):
        return {}
    current_id = _clean((inbound or {}).get("message_id"), 100)
    incoming_texts = []
    for message in history.get("messages") if isinstance(history.get("messages"), list) else []:
        if not _chatwoot_message_is_incoming(message):
            continue
        if current_id and _clean(message.get("id"), 100) == current_id:
            continue
        content = _clean_multiline(message.get("content"), 500)
        if content:
            incoming_texts.append(content)
    if not incoming_texts:
        return {}
    facts = {}
    for text in incoming_texts[-8:]:
        extracted = extract_live_stock_facts(text, inbound or {})
        for key in (
            "sales_lane",
            "lane_confidence",
            "lane_reasons",
            "quantity",
            "category",
            "sex",
            "weight_range",
            "timing",
            "location",
            "payment_method",
        ):
            if not _blank(extracted.get(key)):
                facts[key] = extracted.get(key)
        for key in ("quote_requested", "order_commitment", "reservation_requested", "breeding_interest"):
            if extracted.get(key):
                facts[key] = True
    interest = {
        "sales_lane": facts.get("sales_lane") if facts.get("sales_lane") == LANE_LIVE_STOCK else "",
        "quantity": facts.get("quantity") or "",
        "category": facts.get("category") or "",
        "sex": facts.get("sex") or "",
        "weight_range": facts.get("weight_range") or "",
        "timing": facts.get("timing") or "",
        "location": facts.get("location") or "",
        "payment_method": facts.get("payment_method") or "",
        "quote_requested": bool(facts.get("quote_requested")),
        "order_commitment": bool(facts.get("order_commitment")),
    }
    return {"interest": interest, "source": "chatwoot_conversation_history"} if any(interest.values()) else {}


def _merge_prior_context_packets(primary, secondary):
    primary_interest = (primary or {}).get("interest") if isinstance((primary or {}).get("interest"), dict) else {}
    secondary_interest = (secondary or {}).get("interest") if isinstance((secondary or {}).get("interest"), dict) else {}
    if not secondary_interest:
        return primary or {}
    merged = dict(primary_interest)
    for key, value in secondary_interest.items():
        if _blank(merged.get(key)) and not _blank(value):
            merged[key] = value
        elif key in {"quote_requested", "order_commitment"} and value:
            merged[key] = True
    return {
        "interest": merged,
        "source": "+".join(source for source in [(primary or {}).get("source"), (secondary or {}).get("source")] if source),
    }


def _compact_chatwoot_history(history):
    history = history if isinstance(history, dict) else {}
    messages = history.get("messages") if isinstance(history.get("messages"), list) else []
    return {
        "success": bool(history.get("success")),
        "status": history.get("status", ""),
        "message_count": len(messages),
        "incoming_count": sum(1 for message in messages if _chatwoot_message_is_incoming(message)),
    }


def _compact_chatwoot_history_messages(history, limit=10, current_message_id=""):
    history = history if isinstance(history, dict) else {}
    messages = history.get("messages") if isinstance(history.get("messages"), list) else []
    current_message_id = _clean(current_message_id, 100)
    compact = []
    for message in messages[-max(int(limit or 10), 1):]:
        if not isinstance(message, dict):
            continue
        if current_message_id and _clean(message.get("id"), 100) == current_message_id:
            continue
        if _chatwoot_message_is_activity(message):
            continue
        content = _clean_multiline(message.get("content"), 500)
        if not content:
            continue
        compact.append({
            "speaker": "customer" if _chatwoot_message_is_incoming(message) else "farm",
            "content": content,
            "created_at": message.get("created_at"),
        })
    return compact


def _chatwoot_message_is_incoming(message):
    if not isinstance(message, dict):
        return False
    value = message.get("message_type")
    return value == 0 or str(value).strip().lower() == "incoming"


def _chatwoot_message_is_activity(message):
    if not isinstance(message, dict):
        return False
    value = message.get("message_type")
    return value == 2 or str(value).strip().lower() == "activity"


def build_sam_live_stock_decision(inbound, facts, context_packet, environ=None, llm_drafter=None, owner_example_loader=None):
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
    availability = context_packet.get("availability") if isinstance(context_packet, dict) else {}
    if route["lane"] == LANE_FARM_GENERAL and facts.get("sales_lane") != LANE_LIVE_STOCK:
        reply = _farm_general_reply(inbound, environ or {})
        durable_action = _durable_farm_general_next_action(inbound)
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
            "sales_lane": LANE_FARM_GENERAL,
            "lane_confidence": route["confidence"],
            "facts": facts,
            "input_understanding": inbound.get("understanding") or {},
            "missing_fields": [],
            "read_context": {
                "prior_context_source": (context_packet.get("prior_context") if isinstance(context_packet.get("prior_context"), dict) else {}).get("source", ""),
                "chatwoot_history": context_packet.get("chatwoot_history") if isinstance(context_packet.get("chatwoot_history"), dict) else {},
                "context_errors": context_packet.get("context_errors") if isinstance(context_packet.get("context_errors"), list) else [],
            },
            "availability": availability,
            "match_packet": {},
            "draft_order_packet": {"draft_ready": False, "owner_review_required": False, "reason": "farm_general_question"},
            "price_answer_packet": {"can_answer_price": False, "reason": "farm_general_question"},
            "suggested_reply_text": reply,
            "reply_source": "deterministic_farm_general_knowledge",
            "next_action": durable_action,
            "internal_next_action": "farm_general_question",
            "recommended_action": "owner_review_send_candidate",
            "owner_review_required": True,
            "safe_to_autosend": False,
            "should_reply": False,
            "customer_send_allowed": False,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "creates_order": False,
            "changes_stock": False,
            "reserves_stock": False,
            "authority_note": "Farm-general replies are owner-review candidates only.",
        }
    intake_context = context_packet.get("intake_context") if isinstance(context_packet.get("intake_context"), dict) else {}
    conversation_plan = plan_live_stock_next_action(intake_context, facts)
    legacy_missing = _missing_live_stock_fields(facts)
    plan_missing = conversation_plan.get("missing_fields") if isinstance(conversation_plan.get("missing_fields"), list) else []
    missing = plan_missing if _planner_has_signal(intake_context, facts) else legacy_missing
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
    ledger_evidence, _ledger_status = delegate_to_agent("ledger", {
        "goal": "Validate the active livestock price evidence for SAM's reply.",
        "question": str(inbound.get("content") or "Validate livestock price"),
        "capability": "livestock_price_evidence",
        "known_context": {"pricing": price_answer_packet.get("pricing") or {}},
    })
    agent_evidence = dict(context_packet.get("agent_evidence") or {})
    agent_evidence["ledger"] = ledger_evidence
    context_packet = {**context_packet, "agent_evidence": agent_evidence}
    durable_action = _durable_live_stock_next_action(
        inbound,
        facts,
        route,
        missing,
        blockers,
        conversation_plan,
        price_answer_packet,
    )
    owner_action_packet = build_live_stock_prepared_owner_action_bundle(
        inbound,
        facts,
        conversation_plan,
        draft_packet,
        price_answer_packet,
    )
    owner_correction_examples = _load_owner_correction_examples(
        inbound,
        environ or {},
        owner_example_loader=owner_example_loader,
        facts=facts,
        conversation_plan=conversation_plan,
    )
    fallback_reply = _safe_reply_draft(facts, route, missing, availability, blockers, price_answer_packet, conversation_plan)
    llm_draft = _build_llm_reply_draft_if_enabled(
        inbound,
        facts,
        context_packet,
        route,
        missing,
        blockers,
        match_packet,
        price_answer_packet,
        fallback_reply,
        environ or {},
        drafter=llm_drafter,
        owner_correction_examples=owner_correction_examples,
        conversation_plan=conversation_plan,
    )
    reply = llm_draft.get("reply_text") if llm_draft.get("used") else fallback_reply
    reply_source = llm_draft.get("reply_source") if llm_draft.get("used") else "deterministic_read_only_guard"
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
        "input_understanding": inbound.get("understanding") or {},
        "missing_fields": missing,
        "conversation_plan": conversation_plan,
        "next_action": durable_action,
        "internal_next_action": conversation_plan.get("next_action") or "",
        "conversation_stage": conversation_plan.get("stage") or "",
        "conversation_goal": conversation_plan.get("goal") or "",
        "read_context": {
            "prior_context_source": (context_packet.get("prior_context") if isinstance(context_packet.get("prior_context"), dict) else {}).get("source", ""),
            "chatwoot_history": context_packet.get("chatwoot_history") if isinstance(context_packet.get("chatwoot_history"), dict) else {},
            "context_errors": context_packet.get("context_errors") if isinstance(context_packet.get("context_errors"), list) else [],
        },
        "availability": availability,
        "match_packet": match_packet,
        "price_answer_packet": price_answer_packet,
        "agent_evidence": agent_evidence,
        "owner_action_packet": owner_action_packet,
        "owner_correction_examples": owner_correction_examples,
        "draft_order_packet": draft_packet,
        "llm_draft": llm_draft,
        "blockers": blockers,
        "ready_for_runtime_next_step": ready_for_runtime_next_step,
        "suggested_reply_text": reply,
        "deterministic_fallback_reply_text": fallback_reply,
        "reply_source": reply_source,
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
        "customer_language": _clean(facts.get("customer_language"), 40),
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


def build_live_stock_prepared_owner_action_bundle(inbound, facts, conversation_plan=None, draft_packet=None, price_answer_packet=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    conversation_plan = conversation_plan if isinstance(conversation_plan, dict) else {}
    draft_packet = draft_packet if isinstance(draft_packet, dict) else {}
    price_answer_packet = price_answer_packet if isinstance(price_answer_packet, dict) else {}
    action = _clean(conversation_plan.get("next_action"), 80)
    durable_action = _durable_live_stock_next_action(
        inbound,
        facts,
        {"lane": LANE_LIVE_STOCK},
        [],
        [],
        conversation_plan,
        price_answer_packet,
    )
    order_state = conversation_plan.get("order_state") if isinstance(conversation_plan.get("order_state"), dict) else {}
    order_id = _clean(order_state.get("draft_order_id") or order_state.get("order_id"), 100)
    conversation_id = _clean(inbound.get("conversation_id") or facts.get("conversation_id"), 100)
    action_packet = build_live_stock_owner_action_packet(order_id=order_id, conversation_id=conversation_id)
    summary = _prepared_owner_action_summary(action, order_id, draft_packet, price_answer_packet)
    return {
        "version": "sam_live_stock_prepared_owner_action_bundle_v1",
        "next_action": durable_action,
        "internal_next_action": action,
        "stage": _clean(conversation_plan.get("stage"), 80),
        "goal": _clean(conversation_plan.get("goal"), 160),
        "order_id": order_id,
        "conversation_id": conversation_id,
        "status": summary["status"],
        "label": summary["label"],
        "detail": summary["detail"],
        "owner_gate_required": True,
        "manual_review_required": True,
        "draft_order_ready": bool(draft_packet.get("draft_ready")),
        "price_ready": bool(price_answer_packet.get("can_answer_price")),
        "routes": action_packet,
        **_authority_flags(),
    }


def _refresh_owner_action_packet_after_draft_order(inbound, facts, decision, draft_order):
    result = draft_order.get("result") if isinstance(draft_order.get("result"), dict) else {}
    order_id = _clean(result.get("order_id") or result.get("Order_ID"), 100)
    if not order_id:
        return
    plan = decision.get("conversation_plan") if isinstance(decision.get("conversation_plan"), dict) else {}
    if plan.get("next_action") == "create_draft_then_quote":
        next_action = "generate_quote"
    elif plan.get("next_action") == "create_draft":
        next_action = "sync_lines"
    else:
        next_action = plan.get("next_action")
    plan = {**plan, "next_action": next_action}
    order_state = plan.get("order_state") if isinstance(plan.get("order_state"), dict) else {}
    plan["order_state"] = {**order_state, "draft_order_id": order_id}
    if plan.get("next_action") == "generate_quote":
        plan["stage"] = "quote"
    elif plan.get("next_action") == "sync_lines":
        plan["stage"] = "draft_order"
    decision["conversation_plan"] = plan
    decision["internal_next_action"] = plan.get("next_action") or decision.get("internal_next_action") or ""
    decision["next_action"] = _durable_live_stock_next_action(
        inbound,
        facts,
        {"lane": decision.get("sales_lane") or LANE_LIVE_STOCK},
        decision.get("missing_fields") if isinstance(decision.get("missing_fields"), list) else [],
        decision.get("blockers") if isinstance(decision.get("blockers"), list) else [],
        plan,
        decision.get("price_answer_packet") if isinstance(decision.get("price_answer_packet"), dict) else {},
    )
    decision["conversation_stage"] = plan.get("stage") or decision.get("conversation_stage") or ""
    decision["owner_action_packet"] = build_live_stock_prepared_owner_action_bundle(
        inbound,
        facts,
        plan,
        decision.get("draft_order_packet") if isinstance(decision.get("draft_order_packet"), dict) else {},
        decision.get("price_answer_packet") if isinstance(decision.get("price_answer_packet"), dict) else {},
    )


def _refresh_owner_action_packet_after_failed_draft_order(inbound, facts, decision, draft_order):
    draft_order = draft_order if isinstance(draft_order, dict) else {}
    order_id = _clean(draft_order.get("reused_draft_order_id"), 100)
    if not order_id:
        return
    status = _clean(draft_order.get("status"), 120)
    if status != "sam_live_stock_draft_order_sync_stale_stock":
        return
    plan = decision.get("conversation_plan") if isinstance(decision.get("conversation_plan"), dict) else {}
    order_state = plan.get("order_state") if isinstance(plan.get("order_state"), dict) else {}
    plan = {
        **plan,
        "next_action": "sync_lines",
        "stage": "draft_order",
        "order_state": {**order_state, "draft_order_id": order_id},
    }
    decision["conversation_plan"] = plan
    decision["next_action"] = "sync_lines"
    decision["conversation_stage"] = "draft_order"
    packet = build_live_stock_prepared_owner_action_bundle(
        inbound,
        facts,
        plan,
        decision.get("draft_order_packet") if isinstance(decision.get("draft_order_packet"), dict) else {},
        decision.get("price_answer_packet") if isinstance(decision.get("price_answer_packet"), dict) else {},
    )
    packet["status"] = "blocked_until_stock_revalidated"
    packet["label"] = "Recheck draft order stock"
    packet["detail"] = "Latest draft-order line sync was not fully fulfilled. Recheck stock before preparing a quote."
    decision["owner_action_packet"] = packet


def write_live_stock_draft_order_link_to_intake(inbound, facts, draft_order, decision=None, intake_writer=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    draft_order = draft_order if isinstance(draft_order, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    result = draft_order.get("result") if isinstance(draft_order.get("result"), dict) else {}
    order_id = _clean(result.get("order_id") or result.get("Order_ID"), 100)
    conversation_id = _clean(inbound.get("conversation_id") or facts.get("conversation_id"), 100)
    if not order_id:
        return {"attempted": False, "success": False, "status": "draft_order_id_missing"}
    if not conversation_id:
        return {"attempted": False, "success": False, "status": "conversation_id_missing"}
    patch = {
        "draft_order_id": order_id,
        "last_customer_message": _clean(inbound.get("content"), 600),
    }
    if decision.get("internal_next_action") == "generate_quote":
        patch["quote_requested"] = True
    payload = {
        "conversation_id": conversation_id,
        "account_id": _clean(inbound.get("account_id"), 100),
        "contact_id": _clean(inbound.get("contact_id"), 100),
        "customer_name": _clean(inbound.get("customer_name"), 120),
        "customer_phone": _clean(inbound.get("customer_phone"), 80),
        "customer_channel": _clean(inbound.get("channel"), 80),
        "customer_language": "",
        "updated_by": "Sam Live Stock",
        "patch": {key: value for key, value in patch.items() if value not in ("", None)},
        "items": [],
    }
    validation = validate_live_stock_intake_payload(payload)
    if not validation["is_valid"]:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_link_validation_failed",
            "errors": validation["errors"],
            "payload": payload,
        }
    try:
        writer = intake_writer or update_intake_state
        result = writer(validation["cleaned_data"])
        return {
            "attempted": True,
            "success": bool((result or {}).get("success")),
            "status": "sam_live_stock_draft_order_link_written" if (result or {}).get("success") else "sam_live_stock_draft_order_link_write_failed",
            "result": result,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_link_exception",
            "error": _clean(str(exc), 240),
            "payload": payload,
        }


def _prepared_owner_action_summary(action, order_id, draft_packet, price_answer_packet):
    if action in {"create_draft", "create_draft_then_quote"}:
        if draft_packet.get("draft_ready"):
            label = "Prepare draft order"
            if action == "create_draft_then_quote":
                label = "Prepare draft order, then quote"
            return {
                "status": "ready_for_owner_prepare",
                "label": label,
                "detail": "SAM has enough detail to prepare the draft order for owner review.",
            }
        errors = draft_packet.get("validation_errors") if isinstance(draft_packet.get("validation_errors"), list) else []
        stock_gate = _clean(draft_packet.get("stock_gate"), 80).replace("_", " ")
        detail = "; ".join(_clean(error, 120) for error in errors[:3] if _clean(error, 120))
        if not detail and stock_gate:
            detail = f"Stock gate: {stock_gate}."
        return {
            "status": "blocked_until_draft_ready",
            "label": "Draft order not ready",
            "detail": detail or "SAM still needs clean order details before a draft order can be prepared.",
        }
    if action in {"generate_quote", "update_draft_then_quote"}:
        if order_id:
            return {
                "status": "ready_for_owner_quote_prepare",
                "label": "Prepare latest quote send",
                "detail": f"Use order {order_id} to generate or verify the latest quote before any customer send.",
            }
        return {
            "status": "blocked_until_order_exists",
            "label": "Quote needs draft order first",
            "detail": "SAM needs a draft order ID before it can prepare the quote send packet.",
        }
    if action == "sync_lines":
        return {
            "status": "ready_for_owner_sync_lines" if order_id else "blocked_until_order_exists",
            "label": "Update draft order lines",
            "detail": f"Use order {order_id} to sync the current requested animals." if order_id else "SAM needs a draft order ID before syncing order lines.",
        }
    if action == "ask_missing_field":
        return {
            "status": "needs_customer_detail",
            "label": "Ask one missing detail",
            "detail": "SAM should ask for the next missing detail before preparing an order action.",
        }
    if action:
        return {
            "status": "owner_review",
            "label": action.replace("_", " "),
            "detail": "Owner review is required before any customer or order action.",
        }
    return {
        "status": "owner_review",
        "label": "Owner review",
        "detail": "No prepared order action is ready yet.",
    }


def _set_durable_next_action(decision, action):
    action = _clean(action, 80)
    if action not in SAM_LIVE_STOCK_DURABLE_NEXT_ACTIONS:
        action = "escalate"
    decision["next_action"] = action
    packet = decision.get("owner_action_packet") if isinstance(decision.get("owner_action_packet"), dict) else {}
    if packet:
        packet["next_action"] = action
        decision["owner_action_packet"] = packet


def _durable_farm_general_next_action(inbound):
    text = _normal_text((inbound or {}).get("content"))
    if _asks_for_pictures_or_ad(text):
        return "prepare_picture_response"
    if _asks_location_question(text):
        return "answer_location"
    return "answer_general_info"


def _durable_live_stock_next_action(inbound, facts, route, missing, blockers, conversation_plan, price_answer_packet):
    facts = facts if isinstance(facts, dict) else {}
    route = route if isinstance(route, dict) else {}
    missing = missing if isinstance(missing, list) else []
    blockers = blockers if isinstance(blockers, list) else []
    conversation_plan = conversation_plan if isinstance(conversation_plan, dict) else {}
    price_answer_packet = price_answer_packet if isinstance(price_answer_packet, dict) else {}
    text = _normal_text((inbound or {}).get("content"))
    if _natural_close_signal(text):
        return "no_reply_needed"
    if route.get("lane") not in {"", LANE_LIVE_STOCK, LANE_FARM_GENERAL} or blockers:
        return "escalate"
    internal_action = _clean(conversation_plan.get("next_action"), 80)
    if price_answer_packet.get("can_answer_price") and _asks_price_question(text):
        return "answer_price"
    if internal_action in {"generate_quote", "update_draft_then_quote"}:
        return "prepare_quote"
    if internal_action in {"create_draft", "create_draft_then_quote"}:
        return "prepare_draft_order"
    if internal_action == "sync_lines":
        return "update_draft_order"
    if internal_action in {
        "answer_location",
        "prepare_picture_response",
        "answer_delivery_policy",
        "confirm_collection",
        "propose_breeding_stock_mix",
        "no_reply_needed",
    }:
        return internal_action
    if price_answer_packet.get("can_answer_price") and (facts.get("quote_requested") or _asks_quote(text)):
        return "answer_price"
    if missing or internal_action == "ask_missing_field":
        return "ask_one_missing_detail"
    return "answer_general_info"


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
        "order_stream": "Livestock",
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


def create_live_stock_draft_order_if_enabled(
    inbound,
    facts,
    decision,
    environ=None,
    draft_order_creator=None,
    draft_order_syncer=None,
):
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
    existing_draft_order_id = _existing_draft_order_id_from_decision(decision)
    order_validation = validate_new_order_payload(packet["order_payload"])
    sync_validation = validate_sync_order_lines_payload(packet["sync_payload"])
    if existing_draft_order_id and not sync_validation.get("is_valid"):
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_validation_failed",
            "errors": list(sync_validation.get("errors") or []),
            "packet": packet,
            "existing_draft_order_id": existing_draft_order_id,
        }
    if existing_draft_order_id:
        try:
            syncer = draft_order_syncer or sync_order_lines_from_request
            result = syncer(existing_draft_order_id, sync_validation["cleaned_data"])
            sync_success = bool((result or {}).get("success"))
            complete_fulfillment = (result or {}).get("complete_fulfillment")
            if sync_success and complete_fulfillment is not True:
                return {
                    "attempted": True,
                    "success": False,
                    "status": "sam_live_stock_draft_order_sync_stale_stock",
                    "result": result,
                    "packet": packet,
                    "created_order": False,
                    "reused_draft_order_id": existing_draft_order_id,
                }
            return {
                "attempted": True,
                "success": sync_success,
                "status": "sam_live_stock_draft_order_synced" if sync_success else "sam_live_stock_draft_order_sync_failed",
                "result": result,
                "packet": packet,
                "created_order": False,
                "reused_draft_order_id": existing_draft_order_id,
            }
        except Exception as exc:
            return {
                "attempted": True,
                "success": False,
                "status": "sam_live_stock_draft_order_sync_exception",
                "error": _clean(str(exc), 240),
                "packet": packet,
                "created_order": False,
                "reused_draft_order_id": existing_draft_order_id,
            }
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
            "created_order": bool((result or {}).get("success")),
        }
    except Exception as exc:
        return {
            "attempted": True,
            "success": False,
            "status": "sam_live_stock_draft_order_exception",
            "error": _clean(str(exc), 240),
            "packet": packet,
        }


def _existing_draft_order_id_from_decision(decision):
    decision = decision if isinstance(decision, dict) else {}
    plan = decision.get("conversation_plan") if isinstance(decision.get("conversation_plan"), dict) else {}
    order_state = plan.get("order_state") if isinstance(plan.get("order_state"), dict) else {}
    return _clean(order_state.get("draft_order_id") or order_state.get("order_id"), 100)


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
        "sales_pack_prepare": {
            "allowed_for_sam_auto": False,
            "route": f"/api/orders/{order_id}/sales-pack/prepare" if order_id else "",
            "method": "POST",
            "rule": "Owner-gated preparation only. Generates or reuses quote, loading sheet, removal certificate, and health declaration; sends nothing.",
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
    if decision.get("sales_lane") not in {LANE_LIVE_STOCK, LANE_FARM_GENERAL}:
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
            (r"\b(for sale|book now|discount|cheap|budget)\b", "unsafe_sales_or_discount_language"),
            (r"\bexact farm|farm pin|our location\b", "shares_or_invites_exact_location"),
        ]
        for pattern, label in unsafe_reply_patterns:
            if re.search(pattern, lowered):
                if label == "implies_reservation" and re.search(
                    r"\b(nothing|not|no animals?|cannot|can't|can not)\b.{0,30}\b(reserved|held|booked)\b",
                    lowered,
                ):
                    continue
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


def _safe_reply_draft(facts, route, missing, availability, blockers, price_answer_packet=None, conversation_plan=None):
    conversation_plan = conversation_plan if isinstance(conversation_plan, dict) else {}
    if route["lane"] != LANE_LIVE_STOCK:
        if route["lane"] == "owner_handoff" and _payment_or_pop_interest(facts):
            return (
                "Thanks, I can note the payment message, but POP does not make live animals yours until the farm confirms the bank receipt "
                "and the owner approves the animals on the system."
            )
        latest = _normal_text(facts.get("latest_customer_message"))
        if _has_any(latest, ("pork", "butcher", "butchery", "carcass", "meat")):
            return (
                "Thanks, I understand this is about pork or butchery. Are you looking to buy live pigs to slaughter yourself, "
                "or are you asking for processed pork? I want to send you down the correct sales path rather than guess."
            )
        return "Thanks. Just so I help you correctly: are you asking about live pigs, farm information, or slaughter help?"
    if facts.get("breeding_interest"):
        return _localized_reply(
            facts,
            "I understand this is for breeding. I can prepare a suitable female-and-male mix and check the recorded relationships, but the farm must review the exact animals before we promise them.",
            "Ek verstaan dit is vir teel. Ek kan 'n geskikte vroulike-en-manlike groep voorberei en die aangetekende verwantskappe nagaan, maar die plaas moet die presiese diere goedkeur voordat ons hulle belowe.",
        )
    if facts.get("reservation_requested"):
        return "I can note your interest, but I cannot confirm those animals for you until the farm approves it on the system."
    action_reply = _reply_for_next_action(facts, conversation_plan, price_answer_packet)
    if action_reply:
        return action_reply
    if facts.get("quote_requested"):
        price_reply = _price_answer_reply(facts, price_answer_packet)
        if price_reply:
            return price_reply
    if missing:
        return _question_for_missing(missing[0])
    if availability.get("success") and int(availability.get("matched_count") or 0) <= 0:
        return "I do not want to over-promise that exact group. I can check nearby suitable options for farm review."
    if availability.get("success") and int(availability.get("matched_count") or 0) > 0:
        fact_reply = _fact_aware_owner_draft(facts, price_answer_packet, availability)
        if fact_reply:
            return fact_reply
    return "I have the main live-pig details. I will check the current list before anything is promised."


def _reply_for_next_action(facts, plan, packet):
    facts = facts if isinstance(facts, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    action = str(plan.get("next_action") or "").strip()
    if action == "no_reply_needed":
        return ""
    if action == "answer_location":
        return _localized_reply(
            facts,
            "We are based in the Riversdale area. Collections are arranged with the farm once the order details are confirmed. What type of pig are you looking for?",
            "Ons is in die Riversdal-omgewing. Afhaal word met die plaas gereël sodra die bestelling se besonderhede bevestig is. Watter tipe vark soek jy?",
        )
    if action == "prepare_picture_response":
        return _localized_reply(
            facts,
            "I can send the right farm photos. Which group would you like to see: piglets, weaners, growers, finishers, or the bigger pigs?",
            "Ek kan die regte plaasfoto's stuur. Watter groep wil jy sien: varkies, speenvarke, groeivarke, slagvarke, of die groter varke?",
        )
    if action == "answer_delivery_policy":
        return _localized_reply(
            facts,
            "Collection from the farm is the standard option. If you need delivery, send the drop-off town or location and I can prepare a distance-based estimate for owner review before anything is promised.",
            "Afhaal by die plaas is die standaard opsie. As jy aflewering nodig het, stuur die dorp of aflaaiplek en ek kan 'n afstand-gebaseerde skatting vir eienaar-goedkeuring voorberei voordat enigiets belowe word.",
        )
    if action == "confirm_collection":
        timing = _clean(facts.get("timing"), 120) or "That time"
        return _localized_reply(
            facts,
            f"{_sentence_case(timing)} can work as a collection option. I will keep the order details together and have the farm confirm the final collection time before we lock it in.",
            f"{_sentence_case(timing)} kan as 'n afhaalopsie werk. Ek hou die bestelling se besonderhede bymekaar en laat die plaas die finale afhaaltyd bevestig voordat ons dit vasmaak.",
        )
    if action == "propose_breeding_stock_mix":
        return _localized_reply(
            facts,
            "I can prepare the requested breeding mix and check the recorded relationships so the proposed male is not closely related to the females. The owner will review the exact animals before anything is confirmed.",
            "Ek kan die gevraagde teelgroep voorberei en die aangetekende verwantskappe nagaan sodat die voorgestelde mannetjie nie naby verwant aan die wyfies is nie. Die eienaar sal die presiese diere nagaan voordat enigiets bevestig word.",
        )
    if action in {"create_draft_then_quote", "update_draft_then_quote", "generate_quote"}:
        price = _price_answer_reply(facts, packet)
        if price:
            return (
                f"{price}\n"
                "I can prepare the quote for owner review next. Nothing is reserved or sent until the farm approves it."
            )
        return "I can prepare the quote for owner review once the last quote details are confirmed. Nothing is reserved or sent yet."
    if action in {"create_draft", "sync_lines"}:
        return "I have enough detail to prepare the draft order for owner review. Nothing is reserved or sent until the farm approves it."
    return ""


def _localized_reply(facts, english, afrikaans):
    language = str((facts or {}).get("customer_language") or "").lower()
    return afrikaans if language == "afrikaans" else english


def _farm_general_reply(inbound, source):
    source = source if isinstance(source, dict) else {}
    try:
        knowledge_result = load_sam_farm_knowledge(source)
        knowledge = knowledge_result.get("knowledge") if isinstance(knowledge_result, dict) else {}
    except Exception:
        knowledge = {}
    profile = public_profile(knowledge)
    faq = (knowledge if isinstance(knowledge, dict) else {}).get("faq") if isinstance((knowledge if isinstance(knowledge, dict) else {}).get("faq"), dict) else {}
    location = _clean(faq.get("where_are_you_based") or profile.get("location_summary"), 300)
    if not location:
        location = "We are based around the Riversdale area."
    customer_name = _first_name((inbound or {}).get("customer_name"))
    greeting = f"Hi {customer_name}, " if customer_name else "Hi, "
    text = _normal_text((inbound or {}).get("content"))
    language = str(((inbound or {}).get("understanding") or {}).get("language") or "english").lower()
    products = _farm_product_menu_summary(knowledge, source)
    if _asks_about_business(text):
        if language == "afrikaans":
            return (
                f"{greeting}ons is Amadeus Plaas in die Riversdal-omgewing. "
                "Ons help met lewende varke, plaas-afhaal en algemene plaasvrae. Vleisverkope is nog nie oop nie. "
                "Sê vir my waarna jy soek en wanneer jy dit nodig het, dan help ek met die regte volgende stap."
            )
        return (
            f"{greeting}we are Amadeus Farm in the Riversdale area. "
            f"{products} "
            "Tell me what you are interested in and roughly when you need it, then I can help with the right next step."
        )
    if _asks_for_pictures_or_ad(text):
        if language == "afrikaans":
            return (
                f"{greeting}ek kan die regte plaasfoto's voorberei. "
                "Sê net watter groep jy wil sien: varkies, speenvarke, groeivarke, slagvarke, of groter varke."
            )
        return (
            f"{greeting}we are Amadeus Farm in the Riversdale area. "
            f"{products} "
            "If you want photos, tell me which group you want to see - piglets, weaners, growers, finishers, or bigger pigs - and I will line up the right farm pictures for owner review."
        )
    if _asks_location_question(text):
        if language == "afrikaans":
            return (
                f"{greeting}ons is in die Riversdal-omgewing. "
                "Afhaal word met die plaas gereël sodra die bestelling se besonderhede bevestig is. "
                "Sê vir my waarna jy soek en wanneer jy wil afhaal."
            )
        followup = (
            "Tell me what you need and when you would like to collect, and I will help from there."
            if "collection" in location.lower()
            else "Collections are arranged with the farm once the order details are confirmed. Tell me what you need and when you would like to collect, and I will help from there."
        )
        return (
            f"{greeting}{location} "
            f"{followup}"
        )
    return (
        f"{greeting}{location} "
        "If you are asking about live pigs, farm collections, or the farm itself, send me what you need and I will help from there."
    )


def _farm_product_menu_summary(knowledge, source=None):
    items = (knowledge if isinstance(knowledge, dict) else {}).get("product_menu")
    meat_open = _meat_public_offer_enabled(source)
    if not isinstance(items, list):
        return _farm_product_menu_fallback(meat_open)
    labels = []
    for item in items[:4]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        label_text = str(item.get("label") or "").strip().lower()
        if not meat_open and ("meat" in key or "pork" in label_text or "meat" in label_text):
            continue
        label = _clean(item.get("label"), 80)
        summary = _clean(item.get("summary"), 140)
        if label and summary:
            labels.append(f"{label}: {summary}")
        elif label:
            labels.append(label)
    if not labels:
        return _farm_product_menu_fallback(meat_open)
    if not meat_open:
        labels.append("Meat sales are not open yet.")
    return " ".join(labels)


def _farm_product_menu_fallback(meat_open):
    if meat_open:
        return "We can help with live pig enquiries, meat preorder questions, and general farm questions."
    return "We can help with live pig enquiries, piglet, weaner, grower and finisher groups, farm location, and collection questions. Meat sales are not open yet."


def _asks_location_question(text):
    return _has_any(
        text,
        (
            "where are you",
            "where are u",
            "where u",
            "where are you guys",
            "where are u guys",
            "where are you located",
            "where are u located",
            "where are you based",
            "where are u based",
            "location",
            "located",
            "province",
            "waar is julle",
            "waar is jy",
            "waar is u",
            "waar",
            "ligging",
            "adres",
            "provinsie",
            "directions",
        ),
    )


def _asks_about_business(text):
    return _has_any(
        text,
        (
            "tell me more",
            "tell me more about",
            "tell me more about your ad",
            "learn more",
            "about your business",
            "your business",
            "what do you do",
            "what do you sell",
            "what are you selling",
            "your ad",
            "your advert",
            "jou advertensie",
            "vertel my meer",
            "wat verkoop julle",
            "wat doen julle",
        ),
    )


def _asks_for_pictures_or_ad(text):
    return _has_any(
        text,
        (
            "send pics",
            "send pictures",
            "pictures",
            "photos",
            "pics",
            "foto",
            "fotos",
            "prentjie",
            "prentjies",
            "big ones",
            "small ones",
        ),
    )


def _planner_has_signal(intake_context, facts):
    intake_context = intake_context if isinstance(intake_context, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    if intake_context.get("intake_id") or intake_context.get("draft_order_id"):
        return True
    if isinstance(intake_context.get("items"), list) and intake_context.get("items"):
        return True
    known = intake_context.get("known_fields") if isinstance(intake_context.get("known_fields"), dict) else {}
    if any(known.get(key) not in ("", None, False) for key in ("order_commitment", "quote_requested", "collection_location", "payment_method")):
        return True
    return bool(facts.get("order_commitment") or facts.get("quote_requested"))


def _fact_aware_owner_draft(facts, packet, availability):
    facts = facts if isinstance(facts, dict) else {}
    packet = packet if isinstance(packet, dict) else {}
    availability = availability if isinstance(availability, dict) else {}
    if not packet.get("can_answer_price"):
        return ""
    quantity = _quantity_number(packet.get("requested_quantity") or facts.get("quantity"))
    if quantity <= 0:
        return ""
    customer_name = _first_name(facts.get("customer_name"))
    category = _live_stock_category_label(
        packet.get("requested_category") or (packet.get("pricing") or {}).get("sale_category") or facts.get("category"),
        quantity,
    )
    weight_band = _human_weight_band(packet.get("requested_weight_range") or (packet.get("pricing") or {}).get("weight_band") or facts.get("weight_range"))
    timing = _clean(facts.get("timing"), 120)
    unit = _money_label(packet.get("unit_price"))
    total = _money_label(packet.get("estimated_total")) if packet.get("estimated_total") not in ("", None) else ""
    quantity_label = _quantity_label(quantity)
    greeting = f"Thanks {customer_name}." if customer_name else "Thanks."
    timing_line = f"{_sentence_case(timing)} can work for collection; let me confirm the final collection time with the farm." if timing else "We can work around a collection time once the farm confirms the group."
    price_line = f"The {quantity_label} {category} ({weight_band}) are {unit} each"
    if total and quantity > 1:
        price_line += f", {total} total"
    price_line += "."
    close_line = "I'll double-check the group before we finalise anything."
    return " ".join([greeting, timing_line, price_line, close_line])


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


def _build_llm_reply_draft_if_enabled(
    inbound,
    facts,
    context_packet,
    route,
    missing,
    blockers,
    match_packet,
    price_answer_packet,
    fallback_reply,
    source,
    *,
    drafter=None,
    owner_correction_examples=None,
    conversation_plan=None,
):
    source = source if isinstance(source, dict) else {}
    if not _truthy(source.get(LLM_ENABLED_ENV)):
        return {"used": False, "status": "llm_disabled"}
    if route.get("lane") != LANE_LIVE_STOCK:
        return {"used": False, "status": "llm_wrong_lane"}
    if not (_configured_model(source) and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip()):
        return {"used": False, "status": "llm_not_configured"}
    caller = drafter or _call_sam_live_stock_reply_llm
    raw = caller(
        _llm_reply_context_packet(
            inbound,
            facts,
            context_packet,
            route,
            missing,
            blockers,
            match_packet,
            price_answer_packet,
            fallback_reply,
            owner_correction_examples=owner_correction_examples,
            meat_public_offer_enabled=_meat_public_offer_enabled(source),
            conversation_plan=conversation_plan,
        ),
        source,
    )
    if not isinstance(raw, dict):
        return {"used": False, "status": "llm_empty_response"}
    if raw.get("_llm_error"):
        return {"used": False, "status": "llm_call_failed", "llm_error": raw.get("_llm_error")}
    reply = _clean_multiline(raw.get("reply_text") or raw.get("suggested_reply_text"), 1800)
    if not reply:
        return {"used": False, "status": "llm_no_reply_text"}
    return {
        "used": True,
        "status": "llm_reply_draft_used",
        "reply_source": "llm_live_stock_reply_draft",
        "reply_text": reply,
        "confidence": raw.get("confidence", ""),
        "notes": _clean(raw.get("notes"), 240),
    }


def _load_owner_correction_examples(inbound, source, owner_example_loader=None, facts=None, conversation_plan=None):
    source = source if isinstance(source, dict) else {}
    if not _owner_example_retrieval_enabled(source):
        return []
    loader = owner_example_loader
    if loader is None:
        try:
            from modules.sales.conversation_learning import list_live_stock_owner_reply_examples
        except Exception:
            return []
        loader = list_live_stock_owner_reply_examples
    try:
        result, _status = loader(
            conversation_id=(inbound or {}).get("conversation_id") or "",
            limit=3,
            customer_message=(inbound or {}).get("content") or "",
            customer_language=(facts or {}).get("customer_language") or "",
            conversation_stage=(conversation_plan or {}).get("stage") or "",
            reply_class=(facts or {}).get("message_intent") or "",
        )
    except TypeError:
        try:
            result, _status = loader(
                conversation_id=(inbound or {}).get("conversation_id") or "",
                limit=3,
                customer_message=(inbound or {}).get("content") or "",
            )
        except TypeError:
            result, _status = loader((inbound or {}).get("conversation_id") or "", 3)
    except Exception:
        return []
    examples = result.get("examples") if isinstance(result, dict) else []
    return examples if isinstance(examples, list) else []


def _llm_reply_context_packet(
    inbound,
    facts,
    context_packet,
    route,
    missing,
    blockers,
    match_packet,
    price_answer_packet,
    fallback_reply,
    owner_correction_examples=None,
    meat_public_offer_enabled=False,
    conversation_plan=None,
):
    context_packet = context_packet if isinstance(context_packet, dict) else {}
    availability = context_packet.get("availability") if isinstance(context_packet.get("availability"), dict) else {}
    chatwoot_history = context_packet.get("chatwoot_history") if isinstance(context_packet.get("chatwoot_history"), dict) else {}
    history_messages = context_packet.get("chatwoot_history_messages")
    if not isinstance(history_messages, list):
        history_messages = chatwoot_history.get("messages") if isinstance(chatwoot_history.get("messages"), list) else []
    compact_history = [
        {
            "speaker": message.get("speaker") or ("customer" if _chatwoot_message_is_incoming(message) else "farm"),
            "content": _clean(message.get("content"), 500),
            "created_at": message.get("created_at"),
        }
        for message in history_messages[-10:]
        if isinstance(message, dict)
    ]
    return {
        "rules": [
            "Write one concise WhatsApp reply in the farm owner's voice.",
            "Use only stock and price facts in this JSON. Do not invent animals, prices, reservations, delivery promises, paperwork, or payment status.",
            "Sound like a helpful farm person on WhatsApp, not a system message. Keep it warm, plain, and practical.",
            "Acknowledge the customer's latest message before asking or answering.",
            "Reply in customer_language. For mixed Afrikaans and English, follow the customer's dominant wording and keep South African phrasing natural.",
            "Use conversation_plan.next_action as the purpose of the reply. Do not restart discovery when the plan already identifies the next action.",
            "When quantity, weight band, timing, and price are known, state them plainly. Do not defer to a later check when the supplied context already has the facts.",
            "If a detail is missing, ask only one useful question.",
            "Do not say animals are reserved, held, booked, available, discounted, cheap, or payment confirmed.",
            "Do not offer pork, meat, freezer packs, carcasses, cuts, or meat delivery unless meat_public_offer_enabled is true.",
            "Do not share exact farm pins or exact private farm location.",
            "Never create orders, quotes, reservations, or commands.",
            "owner_correction_examples are past cases where the owner rewrote a similar draft; mirror the owner's phrasing and structure, not the rejected draft. If none are clearly similar to this customer's question, ignore them.",
        ],
        "meat_public_offer_enabled": bool(meat_public_offer_enabled),
        "inbound": {
            "conversation_id": (inbound or {}).get("conversation_id") or "",
            "customer_name": (inbound or {}).get("customer_name") or "",
            "message": _clean((inbound or {}).get("content"), 1000),
        },
        "route": route,
        "facts": facts if isinstance(facts, dict) else {},
        "customer_language": (facts or {}).get("customer_language") or "unknown",
        "message_intent": (facts or {}).get("message_intent") or "unclear",
        "conversation_plan": conversation_plan if isinstance(conversation_plan, dict) else {},
        "missing_fields": missing if isinstance(missing, list) else [],
        "blockers": blockers if isinstance(blockers, list) else [],
        "match_packet": match_packet if isinstance(match_packet, dict) else {},
        "price_answer_packet": price_answer_packet if isinstance(price_answer_packet, dict) else {},
        "agent_evidence": {
            name: {
                "direct_answer": evidence.get("direct_answer"),
                "facts": evidence.get("facts"),
                "sources": evidence.get("sources"),
                "freshness": evidence.get("freshness"),
                "confidence": evidence.get("confidence"),
                "authority": (evidence.get("agent") or {}).get("authority_tier"),
            }
            for name, evidence in (context_packet.get("agent_evidence") or {}).items()
            if isinstance(evidence, dict)
        },
        "availability_status": {
            "success": availability.get("success"),
            "matched_count": availability.get("matched_count"),
            "total_available_count": availability.get("total_available_count"),
        },
        "recent_chatwoot_history": compact_history,
        "owner_correction_examples": owner_correction_examples if isinstance(owner_correction_examples, list) else [],
        "fallback_reply": fallback_reply,
    }


def _call_sam_live_stock_reply_llm(context_packet, source):
    payload = _llm_reply_payload(context_packet, source)
    req = urllib_request.Request(
        str(source.get(LLM_URL_ENV, DEFAULT_LLM_URL) or DEFAULT_LLM_URL).strip() or DEFAULT_LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {str(source.get(OPENAI_API_KEY_ENV, '') or '').strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=_timeout(source)) as response:
            body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        return _llm_error_payload("http_error", exc)
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        return _llm_error_payload("request_error", exc)
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        return _parse_llm_json_object(str(content or ""), fallback_reply_text=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _llm_reply_payload(context_packet, source):
    system = (
        "You are SAM Live Stock's reply drafter for Amadeus Farm. "
        "Return JSON only with keys reply_text, confidence, notes. "
        "Draft a customer WhatsApp reply using only the supplied context. "
        "Write like a practical farm owner on WhatsApp: warm, direct, short, and human. "
        "Use the supplied learned owner corrections as style guidance when they are relevant. "
        "Never promise availability, reservation, delivery, paperwork, payment, order creation, or exact farm location. "
        "Do not offer meat, pork, freezer packs, carcasses, cuts, or meat delivery unless the context says meat_public_offer_enabled is true. "
        "The owner will review before anything is sent."
    )
    return _with_supported_temperature({
        "model": _configured_model(source),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": _llm_reply_user_content(context_packet)},
        ],
        "response_format": {"type": "json_object"},
    }, source, 0.2)


def _llm_reply_user_content(context_packet, max_chars=8000):
    packet = dict(context_packet) if isinstance(context_packet, dict) else {}
    history = packet.get("recent_chatwoot_history")
    if isinstance(history, list):
        packet["recent_chatwoot_history"] = list(history)
    else:
        packet["recent_chatwoot_history"] = []

    def encoded():
        return json.dumps(packet, ensure_ascii=True, separators=(",", ":"))

    text = encoded()
    while len(text) > max_chars and packet["recent_chatwoot_history"]:
        packet["recent_chatwoot_history"] = packet["recent_chatwoot_history"][1:]
        text = encoded()

    if len(text) > max_chars:
        inbound = packet.get("inbound") if isinstance(packet.get("inbound"), dict) else {}
        if len(str(inbound.get("message") or "")) > 500:
            inbound = dict(inbound)
            inbound["message"] = _clean(inbound.get("message"), 500)
            packet["inbound"] = inbound
            text = encoded()

    if len(text) > max_chars and len(str(packet.get("fallback_reply") or "")) > 300:
        packet["fallback_reply"] = _clean_multiline(packet.get("fallback_reply"), 300)
        text = encoded()

    if len(text) > max_chars:
        match_packet = packet.get("match_packet") if isinstance(packet.get("match_packet"), dict) else {}
        sample = match_packet.get("matched_sample") if isinstance(match_packet.get("matched_sample"), list) else []
        if len(sample) > 3:
            match_packet = dict(match_packet)
            match_packet["matched_sample"] = sample[:3]
            packet["match_packet"] = match_packet
            text = encoded()

    return text


def _llm_reply_needs_fallback(decision, review):
    decision = decision if isinstance(decision, dict) else {}
    review = review if isinstance(review, dict) else {}
    if not str(decision.get("reply_source") or "").startswith("llm_"):
        return False
    return bool(review.get("blocked_reasons"))


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


def _first_name(value):
    text = _clean(value, 80)
    return _sentence_case(text.split()[0]) if text else ""


def _live_stock_category_label(value, quantity=0):
    text = _clean(value, 80)
    if not text:
        return "live pigs"
    lower = text.lower().replace("_", " ")
    if _quantity_number(quantity) != 1:
        singulars = {
            "piglet": "piglets",
            "weaner": "weaners",
            "grower": "growers",
            "finisher": "finishers",
            "live pig": "live pigs",
        }
        return singulars.get(lower, lower)
    return lower


def _sentence_case(value):
    text = _clean(value, 160)
    if not text:
        return ""
    return text[:1].upper() + text[1:]


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
    if re.search(r"\b\d{1,2}\s*(?:week|weeks|wk|wks)\s+old\b", text):
        return "piglet"
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


def _has_live_stock_fact_signal(facts):
    facts = facts if isinstance(facts, dict) else {}
    category = _normal_text(facts.get("category"))
    return bool(
        category in {"piglet", "weaner", "grower", "finisher", "ready for slaughter", "ready_for_slaughter", "live pig"}
        or facts.get("weight_range")
        or facts.get("quantity")
    )


def _has_live_stock_followup_signal(text):
    return _has_any(
        _normal_text(text),
        (
            "how much",
            "price",
            "cost",
            "transport",
            "deliver",
            "delivery",
            "big ones",
            "small ones",
            "available",
            "stock",
        ),
    )


def _extract_quantity(text):
    match = re.search(r"\b(?:for|need|want)\s+(\d{1,3})\b", text)
    if match:
        return int(match.group(1))
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
    known = (
        "riversdale", "albertinia", "still bay", "stilbaai", "jongensfontein", "heidelberg", "mossel bay",
        "port elizabeth", "gqeberha", "east london", "eastern cape", "western cape", "cape town", "george",
    )
    for place in known:
        if place in text:
            labels = {"still bay": "Still Bay", "stilbaai": "Stilbaai", "port elizabeth": "Port Elizabeth", "gqeberha": "Gqeberha"}
            return labels.get(place, place.title())
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


def _asks_price_question(text):
    return _has_any(text, ("price", "cost", "how much", "prys"))


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
    reasons = (review or {}).get("escalation_reasons") or (review or {}).get("blocked_reasons") or []
    score = (review or {}).get("score", "-")
    target = (review or {}).get("confidence_target", 96)
    return _clean(
        "\n".join([
            "SAM Live - Needs human check",
            f"Customer: {(inbound or {}).get('customer_name') or '-'}",
            f"Conversation: {(inbound or {}).get('conversation_id') or '-'}",
            f"Confidence: {score}/{target}",
            f"Reason: {_human_escalation_reasons(reasons)}",
            "",
            "Customer message:",
            _clean((inbound or {}).get("content"), 500),
            "",
            "Suggested reply:",
            _clean_multiline(suggested, 1200),
        ]),
        3500,
    )


def _human_escalation_reasons(reasons):
    labels = {
        "lane_not_live_stock:unclear": "unclear sales lane",
        "lane_not_live_stock:farm_general_question": "general farm question",
        "wrong_or_unclear_lane": "needs lane confirmation",
        "hostile_or_scam_location_challenge": "location trust concern",
        "pricing_challenge_or_negotiation": "price challenge",
        "blocked_reply_content": "draft needs safety check",
    }
    clean = []
    for reason in reasons if isinstance(reasons, list) else []:
        key = str(reason or "").strip()
        if not key:
            continue
        clean.append(labels.get(key, key.replace("lane_not_live_stock:", "").replace("_", " ")))
    return ", ".join(clean[:5]) if clean else "needs owner review"


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
    marker = "sam_live_stock_owner_approved_send"
    body = {
        "content": message,
        "message_type": "outgoing",
        "private": False,
        "source_id": f"sam_live_stock:{hashlib.sha1(f'{conversation_id}|{message}'.encode('utf-8', errors='ignore')).hexdigest()[:16]}",
        "content_attributes": {
            "amadeus_source": marker,
            "sam_live_stock_generated": True,
        },
    }
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
    return str(source.get(AGENT_V3_MODEL_ENV) or source.get(LLM_MODEL_ENV) or DEFAULT_LLM_MODEL).strip()


def _timeout(source):
    source = source or {}
    default_timeout = 12 if _truthy(source.get("RENDER")) else 8
    max_timeout = 15 if _truthy(source.get("RENDER")) else 30
    try:
        return max(1, min(max_timeout, int(source.get(LLM_TIMEOUT_ENV, str(default_timeout)))))
    except (TypeError, ValueError):
        return default_timeout


def _with_supported_temperature(payload, source, temperature):
    payload = dict(payload or {})
    model = str(_configured_model(source)).lower()
    if model.startswith("gpt-5"):
        return payload
    payload["temperature"] = temperature
    return payload


def _strip_code_fence(value):
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _parse_llm_json_object(content, fallback_reply_text=False):
    text = _strip_code_fence(content)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass
    if fallback_reply_text:
        reply = _clean_multiline(text, 1800)
        if reply:
            return {"reply_text": reply, "confidence": 0.72}
    return {}


def _llm_error_payload(kind, exc):
    details = {
        "kind": _clean(kind, 40),
        "type": _clean(exc.__class__.__name__, 80),
        "message": _clean(str(exc), 240),
    }
    if isinstance(exc, urllib_error.HTTPError):
        details["status_code"] = exc.code
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        details["body_excerpt"] = _clean(body, 400)
    return {"_llm_error": details}


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


def _explicitly_false(value):
    return str(value or "").strip().lower() in {"0", "false", "no", "off"}


def _owner_example_retrieval_enabled(source):
    source = source if isinstance(source, dict) else {}
    return not _explicitly_false(source.get(OWNER_EXAMPLE_RETRIEVAL_ENABLED_ENV))


def _meat_public_offer_enabled(source):
    source = source if isinstance(source, dict) else {}
    return _truthy(source.get(MEAT_PUBLIC_OFFER_ENABLED_ENV))


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _clean_multiline(value, limit):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line)[:limit]
