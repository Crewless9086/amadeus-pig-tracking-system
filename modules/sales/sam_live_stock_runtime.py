import hmac
import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
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
from modules.sales.sam_pricing import (
    list_live_stock_price_entries,
    resolve_live_stock_price_rule,
)
from modules.sales.sam_sales_router import LANE_FARM_GENERAL, LANE_LIVE_STOCK, LANE_MEAT, classify_sam_sales_lane
from modules.sales.sam_sales_autonomy import (
    bind_authoritative_conversation_evidence,
    evaluate_level1_authority,
    normalize_customer_display_name,
    supporting_claims_are_evidence_backed,
    sales_autonomy_level1_policy,
)
from modules.sales.sam_conversation_state import plan_live_stock_next_action
from modules.sales.sam_live_stock_understanding import (
    is_order_commitment_confirmation,
    understand_live_stock_inbound,
)
from modules.sales.sam_live_stock_contextual_sales import (
    build_contextual_sales_recommendation,
    normalize_livestock_language,
)
from modules.sales.sam_livestock_offer_loop import build_canonical_livestock_offer
from modules.sales.sam_customer_front_door import interpret_customer_front_door
from modules.sales.sam_live_stock_availability_observation import (
    resolve_authoritative_availability,
)
from modules.sales.sam_live_stock_level1_control import (
    load_current_level1_control,
    resolve_level1_runtime_control,
)
from modules.sales.sam_chatwoot_inbox_state import (
    build_chatwoot_inbox_state_plan,
)
from modules.sales.sam_live_stock_continuous_dispatch import (
    build_delivery_owner_exception,
)
from modules.sales.sam_owner_example_projection import (
    read_owner_example_projection,
)
from modules.sales.sam_live_stock_media import classify_chatwoot_image, media_policy, transcribe_chatwoot_voice
from modules.sales.sam_delivery_truth import (
    CHATWOOT_ACCEPTED_UNVERIFIED,
    CONFIRMED_STATES,
    PROVIDER_FAILED,
    PROVIDER_OUTCOME_AMBIGUOUS,
    classify_chatwoot_response,
    classify_dispatch_exception,
)
from modules.charlie.agent_runtime import delegate_to_agent


WEBHOOK_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED"
WEBHOOK_TOKEN_ENV = "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN"
AUTOREPLY_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED"
AUTOREPLY_CANARY_ENABLED_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_ENABLED"
AUTOREPLY_CANARY_CONVERSATION_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONVERSATION_ID"
AUTOREPLY_CANARY_CONTACT_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONTACT_ID"
AUTOREPLY_CANARY_INBOX_ENV = "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_INBOX_ID"
AUTO_GENERAL_CANARY_ENABLED_ENV = "SAM_AUTO_GENERAL_CANARY_ENABLED"
AUTO_GENERAL_AUTOREPLY_ENABLED_ENV = "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED"
AUTO_GENERAL_CANARY_CONVERSATION_ENV = "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID"
AUTO_GENERAL_CANARY_CONTACT_ENV = "SAM_AUTO_GENERAL_CANARY_CONTACT_ID"
AUTO_GENERAL_CANARY_INBOX_ENV = "SAM_AUTO_GENERAL_CANARY_INBOX_ID"
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

RUNTIME_VERSION = "sam_live_stock_conversation_completion_v1"
AUTO_GENERAL = "AUTO_GENERAL"
AUTO_SPECIALIST = "AUTO_SPECIALIST"

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
    level1_policy = sales_autonomy_level1_policy(source)
    return {
        "mode": "backend_native_sam_live_stock_chatwoot_read_only",
        "sales_autonomy_level1": level1_policy,
        "runtime_version": RUNTIME_VERSION,
        "enabled": _truthy(source.get(WEBHOOK_ENABLED_ENV)),
        "token_configured": len(token) >= MIN_TOKEN_CHARS,
        "autoreply_enabled": _truthy(source.get(AUTOREPLY_ENABLED_ENV)),
        "autoreply_explicitly_enabled": _truthy(source.get(AUTOREPLY_ENABLED_ENV)),
        "autoreply_canary": _autoreply_canary_policy(source),
        "auto_general_canary": _auto_general_canary_policy(source),
        "llm_enabled": _truthy(source.get(LLM_ENABLED_ENV)) and llm_configured,
        "llm_explicitly_enabled": _truthy(source.get(LLM_ENABLED_ENV)),
        "llm_configured": llm_configured,
        "llm_runtime_diagnostics": _llm_runtime_diagnostics(source),
        "agent_v3_enabled": False,
        "agent_v3_explicitly_enabled": _truthy(source.get(AGENT_V3_ENABLED_ENV)),
        "enabled_env": WEBHOOK_ENABLED_ENV,
        "token_env": WEBHOOK_TOKEN_ENV,
        "autoreply_env": AUTOREPLY_ENABLED_ENV,
        "autoreply_canary_enabled_env": AUTOREPLY_CANARY_ENABLED_ENV,
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
        "customer_send_allowed": _truthy(source.get(AUTOREPLY_ENABLED_ENV)),
        "routine_reply_rule": "Only a reviewed conversational reply may send; protected actions keep their separate owner gates.",
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
    conversation_identity_loader=None,
    availability_loader=None,
    availability_evidence=None,
    intake_writer=None,
    draft_order_creator=None,
    draft_order_syncer=None,
    llm_drafter=None,
    owner_example_loader=None,
    voice_transcriber=None,
    image_classifier=None,
    chatwoot_sender=None,
    routine_delivery_claim=None,
    routine_delivery_evidence_recorder=None,
    allow_provider_current_backlog=False,
    preclaim_chronology_verifier=None,
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
    newly_supplied_facts = dict(facts)
    facts["customer_language"] = understanding.get("language") or "unknown"
    facts["message_intent"] = understanding.get("message_intent") or "unclear"
    facts["media_review_required"] = bool(understanding.get("requires_media_review"))
    if facts.get("sales_lane") == LANE_MEAT and float(facts.get("lane_confidence") or 0) >= 0.9:
        lane_decision = {
            "version": "sam_sales_lane_decision_v1",
            "current_message_classification": {
                "lane": LANE_MEAT,
                "confidence": float(facts.get("lane_confidence") or 0),
                "evidence_source": "current_message_sales_router",
                "reasons": list(facts.get("lane_reasons") or []),
            },
            "context_state": {"status": "not_read_wrong_lane", "context_influenced_route": False},
            "final_route": LANE_MEAT,
            "cross_lane_handoff_allowed": False,
            "writes_performed": False,
        }
        return {
            "success": True,
            "status": "sam_live_stock_wrong_lane_guard",
            "processed": False,
            "sent": False,
            "inbound": inbound,
            "facts": facts,
            "lane_decision": lane_decision,
            "sam_decision": {},
            "policy": policy,
            **_authority_flags(),
        }, 200
    inbound = resolve_sam_general_inbound_identity(
        inbound,
        payload,
        environ=source,
        conversation_identity_loader=(
            conversation_identity_loader
            or load_chatwoot_conversation_identity
        ),
    )
    general_context = load_sam_general_context(
        inbound,
        conversation_history_loader=conversation_history_loader,
        environ=source,
    )
    contextual_route = resolve_contextual_sales_route(
        inbound,
        facts,
        general_context.get("prior_sales_context"),
    )
    general_context["contextual_sales_route"] = contextual_route
    front_door_packet = build_sam_front_door_adapter_packet(
        inbound,
        general_context,
        source,
    )
    front_door_specialist = front_door_packet.get(
        "next_specialist_recommendation"
    )
    if (
        front_door_packet.get("specialist_response_required") is True
        and front_door_specialist == "livestock"
    ):
        campaign_focus = " ".join(
            str(
                (front_door_packet.get("campaign_or_post_context") or {}).get(key)
                or ""
            )
            for key in ("product_focus", "post_text")
        )
        campaign_category = _campaign_live_stock_category(campaign_focus)
        if campaign_category and _blank(facts.get("category")):
            facts["category"] = campaign_category
            facts["campaign_product_context_retained"] = True
        facts["sales_lane"] = LANE_LIVE_STOCK
        facts["lane_confidence"] = max(
            float(facts.get("lane_confidence") or 0),
            0.96,
        )
        facts["front_door_context_transfer"] = True
    if contextual_route.get("preserve_live_stock_lane") is True:
        facts = merge_prior_live_stock_context(
            facts,
            general_context.get("prior_sales_context") or {},
        )
        facts["sales_lane"] = LANE_LIVE_STOCK
        facts["lane_confidence"] = max(
            float(facts.get("lane_confidence") or 0),
            float(contextual_route.get("confidence") or 0),
        )
        reasons = (
            facts.get("lane_reasons")
            if isinstance(facts.get("lane_reasons"), list)
            else []
        )
        facts["lane_reasons"] = [
            *reasons,
            "live_stock_context:authoritative_contextual_route",
        ]
    if _should_use_auto_general_path(inbound, facts, general_context):
        decision = (
            build_sam_live_stock_decision(
                inbound,
                facts,
                general_context,
                source,
                llm_drafter=llm_drafter,
                owner_example_loader=owner_example_loader,
            )
            if facts.get("sales_lane") == LANE_FARM_GENERAL
            else build_sam_general_decision(
                inbound,
                facts,
                general_context,
                source,
                llm_drafter=llm_drafter,
            )
        )
        decision["normalized_identity_evidence"] = inbound.get("identity_provenance") or {}
        decision["contextual_sales_route"] = contextual_route
        if isinstance(decision.get("inbound"), dict):
            decision["inbound"] = {
                **decision["inbound"],
                "account_id": inbound.get("account_id") or "",
                "conversation_id": inbound.get("conversation_id") or "",
                "contact_id": inbound.get("contact_id") or "",
                "inbox_id": inbound.get("inbox_id") or "",
                "message_id": inbound.get("message_id") or "",
                "last_inbound_at": inbound.get("last_inbound_at") or "",
                "chronology_current": (
                    inbound.get("chronology_current") is True
                ),
                "whatsapp_window_state": (
                    inbound.get("whatsapp_window_state") or ""
                ),
                "whatsapp_window_evidence_authoritative": (
                    inbound.get(
                        "whatsapp_window_evidence_authoritative"
                    )
                    is True
                ),
                "latest_observed_at": (
                    inbound.get("latest_observed_at") or ""
                ),
                "identity_provenance": inbound.get("identity_provenance") or {},
            }
        decision["conversation_ownership"] = AUTO_GENERAL
        decision["handled_autonomously"] = True
        decision["clarification_asked"] = bool(
            decision.get("next_action") == "ask_one_missing_detail"
            or _general_reply_is_clarification(
                decision.get("suggested_reply_text"),
                general_context.get("recovered_reference"),
            )
        )
        decision["specialist_lane_selected"] = False
        decision["specialist_tools_called"] = []
        decision["customer_send_authorized"] = False
        decision.setdefault("reason", "general_conversation_safe")
        conversation_review = review_sam_live_stock_conversation(
            inbound,
            facts,
            decision,
            general_context,
        )
        decision["conversation_review"] = conversation_review
        decision["owner_escalation_required"] = bool(conversation_review.get("escalation_required"))
        decision["handled_autonomously"] = not decision["owner_escalation_required"]
        if decision["owner_escalation_required"]:
            decision["next_action"] = "escalate"
            decision["escalation_packet"] = build_sam_live_stock_escalation_packet(
                inbound,
                facts,
                decision,
                conversation_review,
            )
        decision["owner_authority_required"] = False
        decision["protected_action_reasons"] = []
        if conversation_review.get("no_reply_recommended"):
            decision["suggested_reply_text"] = ""
            decision["should_reply"] = False
            decision["next_action"] = "no_reply_needed"
            decision["reply_source"] = "natural_close_no_reply_guard"
        front_door = front_door_packet
        decision["customer_front_door"] = front_door
        decision["canonical_composition_authorized"] = bool(
            front_door.get("should_reply") is True
            and not front_door.get("identity_errors")
            and front_door.get("customer_reply")
        )
        if decision["canonical_composition_authorized"]:
            decision["suggested_reply_text"] = front_door["customer_reply"]
            decision["should_reply"] = True
            decision["reply_source"] = "canonical_customer_front_door"
        routine_delivery = deliver_sam_live_stock_routine_reply_if_enabled(
            inbound,
            decision,
            conversation_review,
            source,
            chatwoot_sender=chatwoot_sender,
            delivery_claim=routine_delivery_claim,
            delivery_evidence_recorder=routine_delivery_evidence_recorder,
        )
        decision["routine_reply_delivery"] = routine_delivery
        decision["customer_send_authorized"] = routine_delivery.get("canary", {}).get("allowed") is True
        _apply_auto_general_delivery_transition(decision, routine_delivery)
        return {
            "success": True,
            "status": "sam_auto_general_conversation_processed",
            "processed": True,
            "sent": routine_delivery.get("sent") is True,
            "sam_decision": decision,
            "policy": policy,
            **_authority_flags(
                sends_customer_message=routine_delivery.get("sent") is True,
                calls_chatwoot=routine_delivery.get("sent") is True,
            ),
        }, 200
    context_packet = load_live_stock_read_context(
        inbound,
        facts,
        intake_context_loader=intake_context_loader,
        conversation_history_loader=conversation_history_loader,
        availability_loader=availability_loader,
        availability_evidence=availability_evidence,
        environ=source,
    )
    level1_inbound = bind_authoritative_conversation_evidence(
        inbound,
        context_packet.get("chatwoot_authority_messages") or [],
    )
    try:
        loaded_level1_control, loaded_level1_status = (
            load_current_level1_control()
        )
    except Exception:
        loaded_level1_control, loaded_level1_status = {
            "status": "level1_control_storage_unavailable",
            "event": {},
        }, 503
    isolated_level1_runtime = resolve_level1_runtime_control(
        level1_inbound,
        loaded=(
            loaded_level1_control
            if loaded_level1_status < 400
            else {
                "status": "level1_control_storage_unavailable",
                "event": {},
            }
        ),
        allow_provider_current_backlog=allow_provider_current_backlog,
    )
    if _explicit_new_request(inbound.get("content")):
        context_packet["prior_context"] = {}
        context_packet["chatwoot_history_messages"] = []
        context_packet["intake_context"] = {
            "success": True,
            "lookup_status": "context_reset_for_new_request",
            "known_fields": {},
            "items": [],
        }
        context_packet["context_reset"] = {
            "applied": True,
            "reason": "customer_explicit_new_request",
        }
    facts = merge_prior_live_stock_context(facts, context_packet.get("prior_context") or {})
    decision = build_sam_live_stock_decision(
        inbound,
        facts,
        context_packet,
        source,
        llm_drafter=llm_drafter,
        owner_example_loader=owner_example_loader,
    )
    decision["sales_autonomy_level1_inbound_evidence"] = level1_inbound
    decision["contextual_sales_route"] = contextual_route
    decision["customer_front_door"] = front_door_packet
    decision["conversation_ownership"] = AUTO_SPECIALIST
    decision["specialist_lane_selected"] = True
    delivery_owner_exception = build_delivery_owner_exception(
        inbound=inbound,
        facts=facts,
    )
    if delivery_owner_exception.get("eligible") is True:
        decision["delivery_owner_exception"] = delivery_owner_exception
        decision["protected_owner_exception_required"] = True
        if _blank(facts.get("timing")):
            location = _clean(facts.get("location"), 120)
            decision["suggested_reply_text"] = (
                f"Thanks, I’ve noted {location}. Delivery still needs owner "
                "confirmation and is not promised. When would you need them?"
            )
            decision["reply_source"] = (
                "deterministic_delivery_qualification_with_owner_exception"
            )
    decision["specialist_tools_called"] = sorted(
        name
        for name in (decision.get("agent_evidence") or context_packet.get("agent_evidence") or {})
        if name in {"herdmaster", "ledger", "butcher"}
    )
    decision["handled_autonomously"] = True
    decision["clarification_asked"] = decision.get("next_action") == "ask_one_missing_detail"
    decision["owner_escalation_required"] = False
    decision["reason"] = "affirmative_specialist_intent"
    decision["customer_send_authorized"] = False
    llm_draft = decision.get("llm_draft") if isinstance(decision.get("llm_draft"), dict) else {}
    facts["llm_used"] = bool(llm_draft.get("used"))
    facts["llm_status"] = llm_draft.get("status") or facts.get("llm_status") or ""
    conversation_review = review_sam_live_stock_conversation(inbound, facts, decision, context_packet)
    if (
        str(decision.get("reply_source") or "").startswith("llm_")
        and "reservation_owner_authority" in (conversation_review.get("protected_action_reasons") or [])
        and not conversation_review.get("blocked_reasons")
        and not _reservation_protection_explained(decision.get("suggested_reply_text"))
    ):
        original_reply = decision.get("suggested_reply_text", "")
        decision["suggested_reply_text"] = _compose_reservation_protection_reply(facts, original_reply)
        decision["reply_source"] = "llm_live_stock_reply_draft_protected_repair"
        decision["llm_draft_review"] = {
            "status": "composed_with_reservation_owner_authority_acknowledgement",
            "original_reply_text": original_reply,
        }
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
    decision["owner_escalation_required"] = bool(conversation_review.get("escalation_required"))
    decision["handled_autonomously"] = not decision["owner_escalation_required"]
    decision["owner_authority_required"] = bool(conversation_review.get("owner_authority_required"))
    decision["protected_action_reasons"] = list(conversation_review.get("protected_action_reasons") or [])
    if decision["owner_authority_required"]:
        decision["owner_gate_required"] = True
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
    final_canonical_offer = build_canonical_livestock_offer(
        inbound=inbound,
        facts=facts,
        chronology=context_packet.get("chatwoot_authority_messages") or [],
        availability=decision.get("availability") or {},
        match_packet=decision.get("match_packet") or {},
        price_packet=decision.get("price_answer_packet") or {},
        protected_decisions=[
            item
            for item in (
                (
                    decision.get("owner_action_packet")
                    if (
                        _asks_formal_quote(inbound.get("content"))
                        or facts.get("order_commitment")
                        or facts.get("reservation_requested")
                        or facts.get("payment_requested")
                        or facts.get("payment_proof_received")
                    )
                    else None
                ),
                (
                    decision.get("delivery_owner_exception")
                    if (decision.get("delivery_owner_exception") or {}).get(
                        "eligible"
                    )
                    is True
                    else None
                ),
                (
                    decision.get("escalation_packet")
                    if conversation_review.get("escalation_required") is True
                    else None
                ),
            )
            if isinstance(item, dict) and item
        ],
        proposed_reply=decision.get("suggested_reply_text") or "",
        proposed_source=decision.get("reply_source") or "",
        evidence_context={
            "returning_customer_context": context_packet.get("prior_context") or {},
            "newly_supplied_facts": newly_supplied_facts,
            "campaign_or_post_context": context_packet.get("campaign_or_post_context") or {},
            "farm_knowledge": load_sam_farm_knowledge(source).get("knowledge") or {},
            "delivery_claims": context_packet.get("delivery_claims") or [],
            "delivery_outcomes": context_packet.get("delivery_outcomes") or [],
            "quarantines": context_packet.get("quarantines") or [],
        },
    )
    decision["canonical_evidence_offer"] = final_canonical_offer
    decision["canonical_composition_authorized"] = bool(
        final_canonical_offer.get("should_reply")
        and not final_canonical_offer.get("evidence_errors")
        and (final_canonical_offer.get("authority") or {}).get("allowed") is True
    )
    if decision["canonical_composition_authorized"]:
        decision["suggested_reply_text"] = (
            final_canonical_offer.get("customer_reply") or ""
        )
        decision["reply_source"] = "canonical_evidence_to_offer_loop"
    intake_write = write_live_stock_intake_if_enabled(
        inbound,
        facts,
        decision,
        source,
        intake_writer=intake_writer,
        isolated_runtime=isolated_level1_runtime,
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
        isolated_runtime=isolated_level1_runtime,
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
    routine_delivery = deliver_sam_live_stock_routine_reply_if_enabled(
        inbound,
        decision,
        conversation_review,
        source,
        chatwoot_sender=chatwoot_sender,
        delivery_claim=routine_delivery_claim,
        delivery_evidence_recorder=routine_delivery_evidence_recorder,
        isolated_runtime=isolated_level1_runtime,
        preclaim_chronology_verifier=preclaim_chronology_verifier,
    )
    decision["routine_reply_delivery"] = routine_delivery
    decision["chatwoot_inbox_state_plan"] = build_chatwoot_inbox_state_plan(
        inbound=inbound,
        decision=decision,
        provider_state=str(
            (routine_delivery.get("delivery_outcome") or {}).get(
                "delivery_state"
            )
            or ""
        ),
    )
    decision["customer_send_authorized"] = routine_delivery.get("canary", {}).get("allowed") is True
    return {
        "success": True,
        "status": "sam_live_stock_conversation_processed",
        "processed": True,
        "sent": routine_delivery.get("sent") is True,
        "sam_decision": decision,
        "policy": policy,
        **_authority_flags(
            writes_order_intake=bool(intake_write.get("success")),
            creates_order=bool(draft_order.get("success") and draft_order.get("created_order")),
            sends_customer_message=routine_delivery.get("sent") is True,
            calls_chatwoot=routine_delivery.get("sent") is True,
        ),
    }, 200


def deliver_sam_live_stock_routine_reply_if_enabled(
    inbound,
    decision,
    review,
    environ=None,
    chatwoot_sender=None,
    delivery_claim=None,
    delivery_evidence_recorder=None,
    level1_control_loader=None,
    isolated_runtime=None,
    preclaim_chronology_verifier=None,
):
    source = environ if environ is not None else os.environ
    inbound = inbound if isinstance(inbound, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    review = review if isinstance(review, dict) else {}
    read_context = (
        decision.get("read_context")
        if isinstance(decision.get("read_context"), dict)
        else {}
    )
    if (
        read_context.get("context_errors")
        or (
            isinstance(read_context.get("chatwoot_history"), dict)
            and read_context["chatwoot_history"].get(
                "chronology_evidence_complete"
            ) is False
        )
        or "read_context_error" in (decision.get("blockers") or [])
    ):
        return {
            "attempted": False,
            "sent": False,
            "status": "routine_reply_chronology_evidence_unavailable",
        }
    if decision.get("canonical_composition_authorized") is not True:
        return {
            "attempted": False,
            "sent": False,
            "status": "routine_reply_canonical_composition_not_authorized",
        }
    reply = _clean_multiline(decision.get("suggested_reply_text"), 1800)
    legacy_canary = (
        _auto_general_canary_evaluation(inbound, decision, review, source)
        if decision.get("conversation_ownership") == AUTO_GENERAL
        else _autoreply_canary_evaluation(inbound, decision, review, source)
    )
    if not isinstance(isolated_runtime, dict):
        loader = level1_control_loader or load_current_level1_control
        try:
            loaded_control, loaded_status = loader()
        except Exception:
            loaded_control, loaded_status = {
                "status": "level1_control_storage_unavailable",
                "event": {},
            }, 503
        isolated_runtime = resolve_level1_runtime_control(
            (
                decision.get("sales_autonomy_level1_inbound_evidence")
                if isinstance(
                    decision.get("sales_autonomy_level1_inbound_evidence"),
                    dict,
                )
                else inbound
            ),
            loaded=(
                loaded_control
                if loaded_status < 400
                else {
                    "status": "level1_control_storage_unavailable",
                    "event": {},
                }
            ),
        )
    if not (
        decision.get("specialist_lane_selected") is True
        and decision.get("sales_lane") == LANE_LIVE_STOCK
    ):
        isolated_runtime = {
            "allowed": False,
            "control_event_id": "",
            "blockers": ["live_stock_specialist_lane_required"],
        }
    level1 = evaluate_level1_authority(
        lane="live_stock",
        inbound=(
            decision.get("sales_autonomy_level1_inbound_evidence")
            if isinstance(decision.get("sales_autonomy_level1_inbound_evidence"), dict)
            else inbound
        ),
        decision=decision,
        review=review,
        evidence={
            "supporting_evidence_valid": supporting_claims_are_evidence_backed(
                "live_stock",
                decision,
                review_evidence_ready=(
                    review.get("safe_to_send") is True
                    and delivery_claim is not None
                ),
                authoritative_customer_name=inbound.get("customer_name"),
            ),
            "delivery_rail_available": (
                delivery_claim is not None and delivery_evidence_recorder is not None
            ),
            "automatic_retry": False,
            "availability": (
                decision.get("authoritative_availability")
                or decision.get("availability_evidence")
                or {}
            ),
        },
        environ=source,
        isolated_runtime=isolated_runtime,
    )
    decision["sales_autonomy_level1"] = level1
    canary = (
        {
            "allowed": True,
            "status": "sales_autonomy_level1_eligible",
            "checks": level1.get("checks", {}),
            "authority_id": level1.get("authority_id", ""),
            "contains_identity_values": False,
            "contains_secret_values": False,
        }
        if level1.get("dispatch_authorized") is True
        else legacy_canary
    )
    decision["autoreply_canary"] = canary
    if not canary["allowed"]:
        return {"attempted": False, "sent": False, "status": canary["status"], "canary": canary}
    if not decision.get("should_reply") or not reply:
        return {"attempted": False, "sent": False, "status": "routine_reply_not_recommended"}
    if review.get("escalation_required") or not review.get("safe_to_send"):
        return {"attempted": False, "sent": False, "status": "routine_reply_review_blocked"}
    if (
        not str(decision.get("reply_source") or "").startswith(
            ("llm_", "canonical_")
        )
        and level1.get("dispatch_authorized") is not True
    ):
        return {"attempted": False, "sent": False, "status": "routine_reply_requires_llm_draft"}
    conversation_id = _clean(inbound.get("conversation_id"), 100)
    if not conversation_id:
        return {"attempted": False, "sent": False, "status": "routine_reply_conversation_id_missing"}
    if preclaim_chronology_verifier is not None:
        try:
            chronology = preclaim_chronology_verifier(inbound, source)
        except Exception:
            chronology = {"allowed": False}
        if not isinstance(chronology, dict) or chronology.get("allowed") is not True:
            return {
                "attempted": False,
                "sent": False,
                "status": "routine_reply_preclaim_chronology_changed",
            }
    if delivery_claim is None:
        return {"attempted": False, "sent": False, "status": "routine_reply_idempotency_claim_unavailable", "canary": canary}
    claim = delivery_claim(inbound, decision, review)
    if not isinstance(claim, dict) or not claim.get("success"):
        return {"attempted": False, "sent": False, "status": "routine_reply_idempotency_claim_failed", "canary": canary}
    if claim.get("created") is not True:
        return {"attempted": False, "sent": False, "status": "routine_reply_duplicate_withheld", "canary": canary, "claim": claim}
    try:
        sender = chatwoot_sender or (
            lambda target, message, runtime_source: _send_chatwoot_message(
                target,
                message,
                runtime_source,
                amadeus_source="sam_live_stock_routine_reply",
            )
        )
        sent = sender(conversation_id, reply, source)
        outcome = classify_chatwoot_response(sent)
        evidence = _record_delivery_outcome(delivery_evidence_recorder, claim, outcome)
        if evidence.get("success") is not True:
            outcome = {
                **outcome,
                "delivery_state": PROVIDER_OUTCOME_AMBIGUOUS,
                "customer_send_confirmed": False,
                "handled_autonomously": False,
                "failure_class": "delivery_outcome_evidence_not_persisted",
            }
        confirmed = outcome.get("delivery_state") in CONFIRMED_STATES
        accepted = outcome.get("delivery_state") in {
            CHATWOOT_ACCEPTED_UNVERIFIED,
            *CONFIRMED_STATES,
        }
        return {
            "attempted": True,
            "sent": confirmed,
            "chatwoot_accepted": accepted,
            "status": (
                "sam_live_stock_routine_reply_confirmed_delivered"
                if confirmed
                else "sam_live_stock_routine_reply_accepted_unverified"
                if outcome.get("delivery_state") == CHATWOOT_ACCEPTED_UNVERIFIED
                else "sam_live_stock_routine_reply_failed"
                if outcome.get("delivery_state") == PROVIDER_FAILED
                else "sam_live_stock_routine_reply_outcome_ambiguous"
            ),
            "chatwoot": {
                "outgoing_message_id": outcome.get("chatwoot_outgoing_message_id"),
                "response_status": outcome.get("chatwoot_response_status"),
                "provider_identity_class": outcome.get("provider_identity_class"),
                "status_code_class": outcome.get("status_code_class"),
                "contains_raw_provider_identity": False,
            },
            "canary": canary,
            "claim": claim,
            "delivery_outcome": outcome,
            "delivery_evidence": evidence,
            "automatic_retry_prohibited": True,
        }
    except Exception as exc:
        failure_outcome = classify_dispatch_exception(exc)
        evidence = _record_delivery_outcome(delivery_evidence_recorder, claim, failure_outcome)
        return {
            "attempted": True,
            "sent": False,
            "status": "sam_live_stock_routine_reply_outcome_ambiguous",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "canary": canary,
            "claim": claim,
            "delivery_outcome": failure_outcome,
            "delivery_evidence": evidence,
            "automatic_retry_prohibited": True,
        }


def _apply_auto_general_delivery_transition(decision, delivery):
    decision = decision if isinstance(decision, dict) else {}
    delivery = delivery if isinstance(delivery, dict) else {}
    if decision.get("owner_escalation_required") is True:
        transition = {
            "status": "owner_escalation_required",
            "notification_class": "safety_escalation",
            "owner_action_required": True,
            "customer_send_confirmed": False,
            "automatic_retry_prohibited": True,
        }
        decision["handled_autonomously"] = False
        decision["reason"] = "owner_escalation_required"
    elif (delivery.get("delivery_outcome") or {}).get("delivery_state") in CONFIRMED_STATES:
        transition = {
            "status": "routine_reply_confirmed_delivered",
            "notification_class": "none",
            "owner_action_required": False,
            "customer_send_confirmed": True,
            "automatic_retry_prohibited": True,
        }
        decision["handled_autonomously"] = True
        decision["reason"] = "routine_reply_confirmed_delivered"
    elif (delivery.get("delivery_outcome") or {}).get("delivery_state") == CHATWOOT_ACCEPTED_UNVERIFIED:
        transition = {
            "status": "routine_reply_accepted_unverified",
            "notification_class": "delivery_reconciliation",
            "owner_action_required": False,
            "customer_send_confirmed": False,
            "automatic_retry_prohibited": True,
        }
        decision["handled_autonomously"] = False
        decision["reason"] = "routine_reply_accepted_unverified"
    elif delivery.get("attempted") is True:
        state = (delivery.get("delivery_outcome") or {}).get("delivery_state")
        reason = (
            "routine_reply_delivery_failed"
            if state == PROVIDER_FAILED
            else "routine_reply_delivery_ambiguous"
        )
        transition = {
            "status": reason,
            "notification_class": "delivery_exception",
            "owner_action_required": True,
            "customer_send_confirmed": False,
            "automatic_retry_prohibited": True,
        }
        decision["handled_autonomously"] = False
        decision["reason"] = reason
    elif delivery.get("status") == "routine_reply_duplicate_withheld":
        transition = {
            "status": "routine_reply_replay_withheld",
            "notification_class": "claim_owner",
            "owner_action_required": False,
            "customer_send_confirmed": False,
            "automatic_retry_prohibited": True,
        }
        prior_state = (delivery.get("claim") or {}).get("prior_delivery_state")
        if prior_state in CONFIRMED_STATES:
            transition["status"] = "routine_reply_confirmed_delivered"
            transition["notification_class"] = "none"
            decision["handled_autonomously"] = True
            decision["reason"] = "routine_reply_confirmed_delivered"
        elif prior_state == CHATWOOT_ACCEPTED_UNVERIFIED:
            transition["status"] = "routine_reply_accepted_unverified"
            transition["notification_class"] = "delivery_reconciliation"
            decision["handled_autonomously"] = False
            decision["reason"] = "routine_reply_accepted_unverified"
        elif prior_state in {"attempt_claimed", PROVIDER_OUTCOME_AMBIGUOUS, PROVIDER_FAILED}:
            failed = prior_state == PROVIDER_FAILED
            transition["status"] = (
                "routine_reply_delivery_failed"
                if failed
                else "routine_reply_delivery_ambiguous"
            )
            transition["notification_class"] = "delivery_exception"
            transition["owner_action_required"] = True
            decision["handled_autonomously"] = False
            decision["reason"] = transition["status"]
        else:
            decision["handled_autonomously"] = False
            decision["reason"] = "routine_reply_replay_withheld"
    else:
        transition = {
            "status": "routine_reply_waiting_for_owner",
            "notification_class": "owner_review",
            "owner_action_required": True,
            "customer_send_confirmed": False,
            "automatic_retry_prohibited": True,
            "withheld_status": _clean(delivery.get("status"), 120),
        }
        decision["handled_autonomously"] = False
        decision["reason"] = "routine_reply_waiting_for_owner"
    decision["transition_visibility"] = transition
    decision["owner_action_required"] = transition["owner_action_required"]
    decision["customer_send_confirmed"] = transition["customer_send_confirmed"]


def _record_delivery_outcome(recorder, claim, outcome):
    if recorder is None:
        return {"success": False, "status": "delivery_outcome_recorder_unavailable"}
    try:
        recorded = recorder(claim, outcome)
        return recorded if isinstance(recorded, dict) else {"success": False, "status": "delivery_outcome_record_invalid"}
    except Exception as exc:
        return {"success": False, "status": "delivery_outcome_record_failed", "error_type": exc.__class__.__name__}


def _send_failure_confirmed(exc):
    message = str(exc or "").strip().lower()
    return message.startswith("chatwoot_http_") and any(code in message for code in ("400", "401", "403", "404", "409", "422"))


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
    content_attributes = payload.get("content_attributes") if isinstance(payload.get("content_attributes"), dict) else {}
    identity_evidence = _webhook_identity_evidence(payload, conversation, sender, contact)
    return {
        "processable": True,
        "status": "processable",
        "event": event or "message_created",
        "message_type": message_type or "incoming",
        "content": content,
        "conversation_id": identity_evidence["normalized"]["conversation_id"] or conversation_id,
        "contact_id": identity_evidence["normalized"]["contact_id"],
        "inbox_id": identity_evidence["normalized"]["inbox_id"],
        "account_id": _clean(payload.get("account_id") or account.get("id"), 100),
        "customer_name": customer_name or "Chatwoot customer",
        "customer_phone": _clean(sender.get("phone_number") or contact.get("phone_number"), 80),
        "channel": channel,
        "message_id": _clean(payload.get("id") or payload.get("message_id"), 100),
        "last_inbound_at": _clean(payload.get("created_at") or payload.get("timestamp"), 80),
        "conversation_custom_attributes": custom_attributes,
        "message_context": _public_message_context(payload, content_attributes),
        "identity_provenance": identity_evidence,
        "attachments": attachments,
    }


def _webhook_identity_evidence(payload, conversation, sender, contact):
    payload = payload if isinstance(payload, dict) else {}
    conversation = conversation if isinstance(conversation, dict) else {}
    sender = sender if isinstance(sender, dict) else {}
    contact = contact if isinstance(contact, dict) else {}
    top_inbox = payload.get("inbox") if isinstance(payload.get("inbox"), dict) else {}
    conversation_inbox = (
        conversation.get("inbox") if isinstance(conversation.get("inbox"), dict) else {}
    )
    conversation_meta = (
        conversation.get("meta") if isinstance(conversation.get("meta"), dict) else {}
    )
    conversation_sender = (
        conversation_meta.get("sender")
        if isinstance(conversation_meta.get("sender"), dict)
        else {}
    )
    sources = {
        "conversation_id": _identity_source_rows(
            ("payload.conversation_id", payload.get("conversation_id")),
            ("payload.conversation.id", conversation.get("id")),
            (
                "payload.conversation",
                payload.get("conversation") if not isinstance(payload.get("conversation"), dict) else "",
            ),
        ),
        "contact_id": _identity_source_rows(
            ("payload.contact_id", payload.get("contact_id")),
            ("payload.sender.id", sender.get("id")),
            ("payload.contact.id", contact.get("id")),
            ("payload.conversation.meta.sender.id", conversation_sender.get("id")),
        ),
        "inbox_id": _identity_source_rows(
            ("payload.inbox_id", payload.get("inbox_id")),
            ("payload.inbox.id", top_inbox.get("id")),
            ("payload.conversation.inbox_id", conversation.get("inbox_id")),
            ("payload.conversation.inbox.id", conversation_inbox.get("id")),
        ),
    }
    normalized = {}
    conflicts = {}
    for key, rows in sources.items():
        values = sorted({row["value"] for row in rows})
        conflicts[key] = len(values) > 1
        normalized[key] = values[0] if len(values) == 1 else ""
    return {
        "status": "webhook_identity_conflict" if any(conflicts.values()) else "webhook_identity_normalized",
        "normalized": normalized,
        "sources": sources,
        "conflicts": conflicts,
        "authoritative_conversation_lookup": {"attempted": False, "status": "not_attempted"},
        "configured_allowlist_used_as_evidence": False,
    }


def _identity_source_rows(*pairs):
    return [
        {"source": source, "value": value}
        for source, raw in pairs
        if (value := _clean(raw, 100))
    ]


def resolve_sam_general_inbound_identity(
    inbound,
    payload,
    *,
    environ=None,
    conversation_identity_loader=None,
):
    inbound = dict(inbound or {})
    source = environ if environ is not None else os.environ
    evidence = (
        dict(inbound.get("identity_provenance"))
        if isinstance(inbound.get("identity_provenance"), dict)
        else _webhook_identity_evidence(payload or {}, {}, {}, {})
    )
    evidence["normalized"] = dict(evidence.get("normalized") or {})
    evidence["sources"] = {
        key: list((evidence.get("sources") or {}).get(key) or [])
        for key in ("conversation_id", "contact_id", "inbox_id")
    }
    evidence["conflicts"] = dict(evidence.get("conflicts") or {})
    webhook_complete = all(evidence["normalized"].get(key) for key in ("conversation_id", "contact_id", "inbox_id"))
    canary_active = (
        _truthy(source.get(AUTO_GENERAL_AUTOREPLY_ENABLED_ENV))
        and _truthy(source.get(AUTO_GENERAL_CANARY_ENABLED_ENV))
    )
    should_lookup = bool(
        inbound.get("conversation_id")
        and (not webhook_complete or canary_active or conversation_identity_loader is not None)
    )
    authoritative = {"attempted": False, "status": "not_required_webhook_identity_complete"}
    if should_lookup:
        loader = conversation_identity_loader or load_chatwoot_conversation_identity
        try:
            authoritative = loader(inbound.get("conversation_id"), source)
        except TypeError:
            authoritative = loader(inbound.get("conversation_id"))
        except Exception as exc:
            authoritative = _integration_failure("chatwoot_conversation_identity_read_failed", exc)
        authoritative = authoritative if isinstance(authoritative, dict) else {}
        authoritative = {**authoritative, "attempted": True}
        if authoritative.get("success") is True:
            for key in ("conversation_id", "contact_id", "inbox_id"):
                value = _clean(authoritative.get(key), 100)
                if value:
                    evidence["sources"][key].append(
                        {"source": "chatwoot_conversation_record." + key, "value": value}
                    )
    inbound_account = _clean(inbound.get("account_id"), 100)
    authoritative_account = _clean(authoritative.get("account_id"), 100)
    authoritative_field_matches = {
        key: bool(
            authoritative.get("success") is True
            and _clean(authoritative.get(key), 100)
            and _clean(authoritative.get(key), 100)
            == _clean(evidence["normalized"].get(key), 100)
        )
        for key in ("conversation_id", "contact_id", "inbox_id")
    }
    authoritative_identity_complete = bool(
        authoritative.get("success") is True
        and authoritative_account
        and all(_clean(authoritative.get(key), 100) for key in authoritative_field_matches)
    )
    account_matches = bool(
        authoritative.get("success") is True
        and inbound_account
        and authoritative_account
        and inbound_account == authoritative_account
    )
    account_conflict = bool(
        authoritative.get("success") is True
        and inbound_account
        and authoritative_account
        and inbound_account != authoritative_account
    )
    evidence["authoritative_conversation_lookup"] = {
        "attempted": bool(authoritative.get("attempted")),
        "status": _clean(authoritative.get("status"), 120),
        "success": authoritative.get("success") is True,
        "identity_complete": authoritative_identity_complete,
        "account_id_matches": account_matches,
        "field_matches": authoritative_field_matches,
    }
    for key in ("conversation_id", "contact_id", "inbox_id"):
        values = sorted({row["value"] for row in evidence["sources"][key] if row.get("value")})
        evidence["conflicts"][key] = len(values) > 1
        evidence["normalized"][key] = values[0] if len(values) == 1 else ""
    conflict = any(evidence["conflicts"].values()) or account_conflict
    complete = all(evidence["normalized"].get(key) for key in ("conversation_id", "contact_id", "inbox_id"))
    evidence["status"] = (
        "identity_conflict"
        if conflict
        else "identity_verified"
        if complete
        else "identity_evidence_unavailable"
    )
    evidence["configured_allowlist_used_as_evidence"] = False
    inbound["identity_provenance"] = evidence
    inbound["conversation_id"] = evidence["normalized"].get("conversation_id") or ""
    inbound["contact_id"] = evidence["normalized"].get("contact_id") or ""
    inbound["inbox_id"] = evidence["normalized"].get("inbox_id") or ""
    return inbound


def _public_message_context(message, content_attributes=None):
    message = message if isinstance(message, dict) else {}
    attributes = content_attributes if isinstance(content_attributes, dict) else {}
    referral = attributes.get("referral") if isinstance(attributes.get("referral"), dict) else {}
    quoted = (
        attributes.get("in_reply_to")
        or attributes.get("reply_to")
        or attributes.get("quoted_message")
    )
    context = {
        "source_id": _clean(message.get("source_id") or attributes.get("source_id"), 160),
        "quoted_message": _clean_multiline(
            quoted.get("content") if isinstance(quoted, dict) else quoted,
            500,
        ),
        "referral": {
            "source_type": _clean(referral.get("source_type"), 40),
            "source_id": _clean(referral.get("source_id"), 160),
            "source_url": _clean(referral.get("source_url"), 500),
            "headline": _clean(referral.get("headline"), 300),
            "body": _clean_multiline(referral.get("body"), 1200),
            "media_type": _clean(referral.get("media_type"), 40),
        },
    }
    context["referral"] = {key: value for key, value in context["referral"].items() if value}
    return {key: value for key, value in context.items() if value}


def extract_live_stock_facts(message, inbound=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    text = normalize_livestock_language(_normal_text(message))
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
        "sex_split": _extract_sex_split(text),
        "weight_range": weight_range,
        "timing": _extract_timing(text),
        "location": _extract_location(text),
        "transport_expectation": _extract_transport(text),
        "payment_method": _extract_payment(text),
        "quote_requested": _asks_quote(text),
        "order_commitment": is_order_commitment_confirmation(text),
        "reservation_requested": _asks_reservation(text),
        "breeding_interest": _has_any(text, ("breeding", "breed", "gilt", "gilts", "boar", "boars", "sow", "sows")),
        "customer_name": inbound.get("customer_name") or "",
        "conversation_id": inbound.get("conversation_id") or "",
        "contact_id": inbound.get("contact_id") or "",
        "channel": inbound.get("channel") or "chatwoot",
        "llm_used": False,
        "llm_status": "not_enabled_read_only_stage",
        "information_scope": (
            "grower_finisher"
            if _asks_about_big_live_pigs(text)
            else ""
        ),
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
    current_category = _normal_category(facts.get("category"))
    for key in (
        "category",
        "quantity",
        "sex",
        "sex_split",
        "weight_range",
        "timing",
        "location",
        "transport_expectation",
        "payment_method",
        "quote_requested",
        "order_commitment",
    ):
        prior_value = interest.get(key)
        if (
            key == "weight_range"
            and current_category
            and not _blank(prior_value)
        ):
            prior_weight_category = _category_from_weight_range(prior_value)
            if prior_weight_category and prior_weight_category != current_category:
                if (
                    current_category == "piglet"
                    and prior_weight_category == "weaner"
                    and _blank(facts.get("weight_range"))
                    and not _blank(facts.get("timing"))
                    and re.search(
                        r"\bthe\s+piglets\b",
                        _normal_text(facts.get("latest_customer_message")),
                    )
                    and not re.search(
                        r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
                        r"\s*[- ]?\s*(?:days?|weeks?|months?)"
                        r"(?:[\s-]+(?:old|of[\s-]+age))\b",
                        _normal_text(facts.get("latest_customer_message")),
                    )
                    and not _has_any(
                        _normal_text(facts.get("latest_customer_message")),
                        (
                            "small piglet", "weeks old", "week old", "instead",
                            "actually", "weaner", "not ", "rather", "only",
                            "as well",
                        ),
                    )
                ):
                    # Customers commonly continue to call already-qualified
                    # weaners "piglets". A generic noun in a terse follow-up
                    # must not erase the exact retained weight band.
                    facts["category"] = prior_weight_category
                    current_category = prior_weight_category
                else:
                    continue
        if (
            (not facts.get(key) if key == "sex_split" else _blank(facts.get(key)))
            and (bool(prior_value) if key == "sex_split" else not _blank(prior_value))
        ):
            facts[key] = prior_value
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


def load_sam_general_context(inbound, *, conversation_history_loader=None, environ=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    source = environ if environ is not None else os.environ
    history = {"success": False, "status": "not_loaded", "messages": []}
    errors = []
    if inbound.get("conversation_id"):
        try:
            loader = conversation_history_loader or load_chatwoot_conversation_history
            history = loader(inbound.get("conversation_id"), source)
        except Exception as exc:
            errors.append(_integration_failure("chatwoot_conversation_history_read_failed", exc))
            history = {"success": False, "status": "read_failed", "messages": []}
    current_context = inbound.get("message_context") if isinstance(inbound.get("message_context"), dict) else {}
    recovered_reference = _recover_general_reference(current_context, history)
    compact_history = _compact_chatwoot_history(history)
    prior_sales_context = _prior_context_from_chatwoot_history(
        history, inbound
    )
    if (
        history.get("success")
        and compact_history.get("chronology_evidence_complete") is False
    ):
        errors.append({
            "status": "chatwoot_chronology_evidence_unavailable",
            "reason": "chronology_timestamp_unavailable",
        })
    return {
        "success": not errors,
        "read_only": True,
        "current_message_context": current_context,
        "recovered_reference": recovered_reference,
        "prior_sales_context": prior_sales_context,
        "chatwoot_history": compact_history,
        "chatwoot_history_messages": _compact_chatwoot_history_messages(
            history,
            current_message_id=inbound.get("message_id"),
        ),
        "chatwoot_authority_messages": _authority_chatwoot_messages(history),
        "context_errors": errors,
        "specialist_context_loaded": False,
        "specialist_tools_called": [],
    }


def build_sam_front_door_adapter_packet(inbound, context_packet, environ=None):
    """Compose the pure Front Door through the existing authenticated adapter."""
    inbound = inbound if isinstance(inbound, dict) else {}
    context_packet = context_packet if isinstance(context_packet, dict) else {}
    scope = {
        key: _clean(inbound.get(key), 100)
        for key in ("account_id", "inbox_id", "contact_id", "conversation_id")
    }
    chronology = []
    for row in context_packet.get("chatwoot_authority_messages") or []:
        if not isinstance(row, dict):
            continue
        chronology.append({
            "message_id": _clean(row.get("id") or row.get("message_id"), 100),
            "role": (
                "customer"
                if row.get("message_type") == 0
                or row.get("speaker") == "customer"
                else "farm"
            ),
            "content": _clean_multiline(row.get("content"), 1800),
            "created_at": _clean(row.get("created_at"), 80),
            **scope,
        })
    latest = chronology[-1] if chronology else {}
    reference = (
        context_packet.get("recovered_reference")
        if isinstance(context_packet.get("recovered_reference"), dict)
        else {}
    )
    retained = (
        context_packet.get("prior_sales_context")
        if isinstance(context_packet.get("prior_sales_context"), dict)
        else {}
    )
    knowledge_result = load_sam_farm_knowledge(environ or {})
    try:
        with open(knowledge_result.get("path") or "", encoding="utf-8") as source:
            knowledge = json.load(source)
    except (OSError, ValueError, TypeError):
        knowledge = knowledge_result.get("knowledge") or {}
    evidence = {
        "identity": {
            **scope,
            "latest_inbound_message_id": _clean(inbound.get("message_id"), 100),
        },
        "chronology": chronology,
        "latest_inbound": {
            **latest,
            "message_id": _clean(inbound.get("message_id"), 100),
            "content": _clean_multiline(inbound.get("content"), 1800),
            **scope,
        },
        "retained_context": {
            "source": "authoritative_chatwoot_and_intake",
            "version": "v1",
            **scope,
            "specialist": (
                (retained.get("interest") or {}).get("sales_lane")
                if isinstance(retained.get("interest"), dict)
                else ""
            ),
            "facts": retained.get("interest") or {},
        },
        "campaign_or_post": {
            "source": reference.get("source") or "none",
            "version": "v1",
            **scope,
            "post_id": reference.get("source_id") or "",
            "title": reference.get("headline") or reference.get("subject") or "",
            "post_text": reference.get("body") or "",
            "product_focus": reference.get("subject") or "",
            "specialist": (
                "livestock"
                if re.search(
                    r"\b(?:pig|piglet|piggy|weaner|grower|finisher)\w*\b",
                    " ".join(
                        str(reference.get(key) or "")
                        for key in ("headline", "subject", "body")
                    ),
                    re.I,
                )
                else ""
            ),
        },
    }
    return interpret_customer_front_door(evidence, knowledge)


def _campaign_live_stock_category(text):
    normalized = _normal_text(text)
    if re.search(r"\b(?:weaner|weaned piglet)\w*\b", normalized):
        return "weaner"
    if re.search(r"\b(?:piglet|piggy|litter)\w*\b", normalized):
        return "piglet"
    if re.search(r"\bgrower\w*\b", normalized):
        return "grower"
    if re.search(r"\bfinisher\w*\b", normalized):
        return "finisher"
    if re.search(r"\b(?:slaughter|80\s*kg)\b", normalized):
        return "ready_for_slaughter"
    return ""


def _recover_general_reference(current_context, history):
    current_context = current_context if isinstance(current_context, dict) else {}
    current_referral = current_context.get("referral") if isinstance(current_context.get("referral"), dict) else {}
    if current_referral:
        return _reference_from_referral(current_referral, "current_message_referral")
    if current_context.get("quoted_message"):
        return {
            "status": "resolved",
            "source": "current_message_quote",
            "subject": _clean_multiline(current_context.get("quoted_message"), 500),
        }
    history = history if isinstance(history, dict) else {}
    for message in reversed(history.get("messages") if isinstance(history.get("messages"), list) else []):
        context = message.get("message_context") if isinstance(message, dict) and isinstance(message.get("message_context"), dict) else {}
        referral = context.get("referral") if isinstance(context.get("referral"), dict) else {}
        if referral:
            return _reference_from_referral(referral, "recent_chatwoot_referral")
        if context.get("quoted_message"):
            return {
                "status": "resolved",
                "source": "recent_chatwoot_quote",
                "subject": _clean_multiline(context.get("quoted_message"), 500),
            }
    return {"status": "missing", "source": "none", "subject": ""}


def _reference_from_referral(referral, source):
    referral = referral if isinstance(referral, dict) else {}
    headline = _clean(referral.get("headline"), 300)
    body = _clean_multiline(referral.get("body"), 1200)
    subject = headline or _first_sentence(body)
    return {
        "status": "resolved" if subject or referral.get("source_id") else "partial",
        "source": source,
        "source_type": _clean(referral.get("source_type"), 40),
        "source_id": _clean(referral.get("source_id"), 160),
        "source_url": _clean(referral.get("source_url"), 500),
        "headline": headline,
        "body": body,
        "subject": subject,
    }


def _first_sentence(text):
    text = _clean_multiline(text, 500)
    if not text:
        return ""
    return re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]


def _current_message_requires_specialist(inbound, facts):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    text = _normal_text(inbound.get("content"))
    if facts.get("sales_lane") == LANE_MEAT and float(facts.get("lane_confidence") or 0) >= 0.9:
        return True
    if facts.get("sales_lane") != LANE_LIVE_STOCK:
        return bool(
            facts.get("order_commitment")
            or facts.get("quote_requested")
            or facts.get("reservation_requested")
            or facts.get("breeding_interest")
            or facts.get("media_review_required")
            or inbound.get("attachments")
            or any(
                not _blank(facts.get(key))
                for key in ("timing", "location", "transport_expectation")
            )
            or _potential_specialist_followup(text)
        )
    usable_constraints = sum(
        1
        for key in ("category", "quantity", "sex", "weight_range")
        if not _blank(facts.get(key))
    )
    affirmative_language = bool(re.search(
        r"\b(want|need|buy|purchase|sell|order|quote|price|cost|available|availability|"
        r"looking for|interested in|reserve|book|soek|koop|wil h[eê]|prys|beskikbaar)\b",
        text,
    ))
    return bool(
        facts.get("order_commitment")
        or facts.get("quote_requested")
        or facts.get("reservation_requested")
        or facts.get("media_review_required")
        or inbound.get("attachments")
        or _asks_about_big_live_pigs(text)
        or _potential_specialist_followup(text)
        or (affirmative_language and usable_constraints >= 1)
        or (usable_constraints >= 2 and facts.get("quantity"))
        or any(
            not _blank(facts.get(key))
            for key in ("timing", "location", "transport_expectation")
        )
    )


def _should_use_auto_general_path(inbound, facts, context_packet=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    text = _normal_text(inbound.get("content"))
    if facts.get("front_door_context_transfer") is True:
        return False
    contextual_route = (
        context_packet.get("contextual_sales_route")
        if isinstance(context_packet, dict)
        and isinstance(context_packet.get("contextual_sales_route"), dict)
        else {}
    )
    if contextual_route.get("preserve_live_stock_lane") is True:
        return False
    if contextual_route.get("status") == "mixed_intent_requires_clarification":
        return True
    # The contextual router is the lane authority for the current provider-
    # bound message as well as for preserved prior context. A confidently
    # resolved Livestock route must never fall through to AUTO_GENERAL merely
    # because the message contains only a price/quantity question.
    current_route = (
        contextual_route.get("current_route")
        if isinstance(contextual_route.get("current_route"), dict)
        else {}
    )
    topical_only_reasons = {
        "live_stock_sales:pig",
        "live_stock_sales:pigs",
        "live_stock_sales:piglet",
        "live_stock_sales:piglets",
        "live_stock_sales:vark",
        "live_stock_sales:varke",
    }
    current_reasons = {
        str(reason) for reason in (current_route.get("reasons") or [])
    }
    if (
        contextual_route.get("final_route") == LANE_LIVE_STOCK
        and current_reasons
        and not current_reasons.issubset(topical_only_reasons)
    ):
        return False
    if _current_message_requires_specialist(inbound, facts):
        return False
    if _looks_like_customer_qualification_answer(
        text, facts, context_packet=context_packet
    ):
        return False
    if _hostile_or_scam_signal(text) or _price_challenge_signal(text):
        return False
    if facts.get("sales_lane") == LANE_FARM_GENERAL:
        return True
    if _natural_close_signal(text):
        return True
    return facts.get("sales_lane") in {"", "unclear", "owner_handoff", LANE_LIVE_STOCK}


def resolve_contextual_sales_route(
    inbound,
    current_facts,
    prior_context,
    *,
    max_age_seconds=30 * 24 * 60 * 60,
):
    """Preserve a proven Livestock lane without masking genuine lane changes."""
    inbound = inbound if isinstance(inbound, dict) else {}
    current_facts = current_facts if isinstance(current_facts, dict) else {}
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    interest = (
        prior_context.get("interest")
        if isinstance(prior_context.get("interest"), dict)
        else {}
    )
    current_route = classify_sam_sales_lane(inbound.get("content"))
    current_reasons = list(current_route.get("reasons") or [])
    mixed = "mixed_sales_intent" in current_reasons
    prior_confidence = float(
        interest.get("lane_confidence")
        or prior_context.get("lane_confidence")
        or 0
    )
    current_instant = _chatwoot_history_instant(
        inbound.get("last_inbound_at")
    )
    prior_instant = _chatwoot_history_instant(
        prior_context.get("latest_context_at")
    )
    identity_provenance = (
        inbound.get("identity_provenance")
        if isinstance(inbound.get("identity_provenance"), dict)
        else {}
    )
    provenance_normalized = (
        identity_provenance.get("normalized")
        if isinstance(identity_provenance.get("normalized"), dict)
        else {}
    )
    provenance_conflicts = (
        identity_provenance.get("conflicts")
        if isinstance(identity_provenance.get("conflicts"), dict)
        else {}
    )
    authoritative_lookup = (
        identity_provenance.get("authoritative_conversation_lookup")
        if isinstance(
            identity_provenance.get("authoritative_conversation_lookup"),
            dict,
        )
        else {}
    )
    provenance_complete = all(
        _clean(
            provenance_normalized.get(key) or inbound.get(key),
            100,
        )
        for key in ("conversation_id", "contact_id", "inbox_id")
    )
    identities_match = bool(
        identity_provenance.get("status") in {
            "identity_verified",
            "webhook_identity_normalized",
        }
        and authoritative_lookup.get("success") is True
        and authoritative_lookup.get("identity_complete") is True
        and authoritative_lookup.get("account_id_matches") is True
        and all(
            authoritative_lookup.get("field_matches", {}).get(key) is True
            for key in ("conversation_id", "contact_id", "inbox_id")
        )
        and provenance_complete
        and not any(provenance_conflicts.values())
        and
        _clean(prior_context.get("conversation_id"), 100)
        == _clean(inbound.get("conversation_id"), 100)
        and _clean(prior_context.get("contact_id"), 100)
        == _clean(inbound.get("contact_id"), 100)
        and _clean(prior_context.get("inbox_id"), 100)
        == _clean(inbound.get("inbox_id"), 100)
        and _clean(prior_context.get("account_id"), 100)
        == _clean(inbound.get("account_id"), 100)
        and all(
            _clean(inbound.get(key), 100)
            for key in (
                "account_id", "conversation_id", "contact_id", "inbox_id"
            )
        )
    )
    fresh = bool(
        current_instant is not None
        and prior_instant is not None
        and 0 <= current_instant - prior_instant <= max_age_seconds
    )
    prior_valid = bool(
        prior_context.get("evidence_complete") is True
        and interest.get("sales_lane") == LANE_LIVE_STOCK
        and prior_confidence >= 0.9
        and identities_match
        and fresh
    )
    text = _normal_text(inbound.get("content"))
    explicit_change = current_route.get("lane") in {
        LANE_MEAT,
        "slaughter_abattoir_sales",
    }
    preserve = bool(
        prior_valid
        and not _explicit_new_request(text)
        and not _natural_close_signal(text)
        and not mixed
        and current_route.get("lane") != "owner_handoff"
        and not explicit_change
    )
    if preserve:
        status = "authoritative_live_stock_context_preserved"
    elif not prior_valid:
        status = "prior_context_not_authoritative"
    elif mixed:
        status = "mixed_intent_requires_clarification"
    elif explicit_change:
        status = "affirmative_lane_change_preserved"
    elif current_route.get("lane") == "owner_handoff":
        status = "owner_handoff_preserved"
    elif _natural_close_signal(text):
        status = "acknowledgement_or_close_not_reopened"
    else:
        status = "explicit_context_reset"
    return {
        "version": "sam_contextual_sales_route_v1",
        "status": status,
        "preserve_live_stock_lane": preserve,
        "final_route": (
            LANE_LIVE_STOCK if preserve else current_route.get("lane")
        ),
        "confidence": prior_confidence if preserve else current_route.get(
            "confidence", 0
        ),
        "checks": {
            "prior_evidence_complete": (
                prior_context.get("evidence_complete") is True
            ),
            "prior_live_stock_lane": (
                interest.get("sales_lane") == LANE_LIVE_STOCK
            ),
            "prior_high_confidence": prior_confidence >= 0.9,
            "identity_bound": identities_match,
            "fresh": fresh,
            "mixed_intent_absent": not mixed,
            "affirmative_lane_change_absent": not explicit_change,
            "owner_handoff_absent": (
                current_route.get("lane") != "owner_handoff"
            ),
        },
        "current_route": {
            "lane": current_route.get("lane"),
            "confidence": current_route.get("confidence"),
            "reasons": current_reasons,
        },
        "writes_performed": False,
        "sends_customer_message": False,
    }


def _looks_like_customer_qualification_answer(text, facts, context_packet=None):
    """Keep concise customer answers on the Livestock persistence path."""
    words = str(text or "").split()
    if not words or len(words) > 8:
        return False
    if _has_any(text, ("post", "advert", "ad", "picture", "photo", "more info")):
        return False
    has_qualification = any(
        not _blank((facts or {}).get(key))
        for key in ("category", "sex", "weight_range")
    )
    if not has_qualification:
        return False
    if (facts or {}).get("sales_lane") == LANE_LIVE_STOCK:
        return True
    history_evidence = (
        (context_packet or {}).get("chatwoot_history")
        if isinstance(context_packet, dict)
        else {}
    )
    if not isinstance(history_evidence, dict) or (
        history_evidence.get("chronology_evidence_complete") is not True
    ):
        return False
    history = (
        (context_packet or {}).get("chatwoot_history_messages")
        if isinstance(context_packet, dict)
        else []
    )
    farm_messages = [
        row for row in history or []
        if isinstance(row, dict) and row.get("speaker") == "farm"
    ]
    if not farm_messages:
        return False
    prompt = _normal_text(farm_messages[-1].get("content"))
    if not prompt:
        return False
    if not _blank((facts or {}).get("sex")):
        return _has_any(prompt, (
            "male, female, or either",
            "males, females, or either",
            "sex",
            "male or female",
        ))
    if not _blank((facts or {}).get("category")) or not _blank(
        (facts or {}).get("weight_range")
    ):
        return _has_any(prompt, (
            "which size",
            "what size",
            "weight",
            "which category",
            "small piglets",
            "weaned piglets",
        ))
    return False


def _potential_specialist_followup(text):
    return bool(re.search(
        r"\b(location|collection|collect|transport|deliver|delivery|price|quote|"
        r"reserve|reservation|friday|saturday|sunday|monday|tuesday|wednesday|thursday|"
        r"afhaal|aflewer|ligging|prys|kwotasie)\b",
        text or "",
    ))


def build_sam_general_decision(inbound, facts, context_packet, environ=None, llm_drafter=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = dict(facts or {})
    context_packet = context_packet if isinstance(context_packet, dict) else {}
    source = environ if isinstance(environ, Mapping) else {}
    reference = context_packet.get("recovered_reference") if isinstance(context_packet.get("recovered_reference"), dict) else {}
    facts["sales_lane"] = "unclear"
    fallback = _auto_general_fallback_reply(
        inbound,
        reference,
        contextual_route=context_packet.get("contextual_sales_route"),
    )
    llm = _build_auto_general_llm_reply_if_enabled(
        inbound,
        facts,
        context_packet,
        fallback,
        source,
        drafter=llm_drafter,
    )
    llm_reply = _clean_multiline(llm.get("reply_text"), 1800) if llm.get("used") else ""
    reply = llm_reply or fallback
    reply_source = llm.get("reply_source") if llm_reply else "deterministic_auto_general_fallback"
    clarification = _general_reply_is_clarification(reply, reference)
    reason = (
        "general_reference_resolved"
        if reference.get("status") == "resolved"
        else "general_reference_missing_one_clarification"
    )
    return {
        "version": "sam_routine_majority_v1",
        "agent": "sam_general",
        "mode": "read_only_auto_general",
        "conversation_ownership": AUTO_GENERAL,
        "sales_lane": "unclear",
        "lane_confidence": float(facts.get("lane_confidence") or 0),
        "conversational_reply_confidence": llm.get("confidence") if llm.get("used") else 0.98,
        "facts": facts,
        "inbound": {
            "conversation_id": inbound.get("conversation_id") or "",
            "message_id": inbound.get("message_id") or "",
            "customer_name": inbound.get("customer_name") or "",
            "contact_id": inbound.get("contact_id") or "",
            "inbox_id": inbound.get("inbox_id") or "",
            "channel": inbound.get("channel") or "",
            "content": inbound.get("content") or "",
            "identity_provenance": inbound.get("identity_provenance") or {},
        },
        "read_context": context_packet,
        "llm_draft": llm,
        "suggested_reply_text": reply,
        "deterministic_fallback_reply_text": fallback,
        "reply_source": reply_source,
        "next_action": "ask_one_missing_detail" if clarification else "answer_general_info",
        "recommended_action": "auto_general_reply_candidate",
        "should_reply": True,
        "handled_autonomously": True,
        "clarification_asked": clarification,
        "specialist_lane_selected": False,
        "owner_escalation_required": False,
        "reason": reason,
        "specialist_tools_called": [],
        "customer_send_authorized": False,
        "owner_gate_required": False,
        "owner_authority_required": False,
        "availability": {"status": "not_loaded_general_state", "matched_count": 0},
        "match_packet": {},
        "price_answer_packet": {"can_answer_price": False, "reason": "general_state"},
        "draft_order_packet": {"draft_ready": False, "reason": "general_state"},
        "blockers": [],
        "missing_fields": [],
        "creates_order": False,
        "creates_quote": False,
        "reserves_stock": False,
        "changes_stock": False,
        "writes_farm_data": False,
        "confirms_payment": False,
        "assigns_animal": False,
        "writes_order_intake": False,
        "writes_sales_transaction": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
    }


def _auto_general_fallback_reply(
    inbound,
    reference,
    *,
    contextual_route=None,
):
    inbound = inbound if isinstance(inbound, dict) else {}
    reference = reference if isinstance(reference, dict) else {}
    name = _first_name(inbound.get("customer_name"))
    greeting = f"Hi {name}!" if name else "Hi!"
    text = _normal_text(inbound.get("content"))
    contextual_route = (
        contextual_route if isinstance(contextual_route, dict) else {}
    )
    headline = _clean(reference.get("headline") or reference.get("subject"), 300)
    body = _clean_multiline(reference.get("body"), 1200)
    if _general_greeting_only(text):
        return f"{greeting} How can I help you today?"
    if _explicit_human_request(text):
        return f"{greeting} Of course. I will ask Charl to help you."
    if contextual_route.get("status") == "mixed_intent_requires_clarification":
        return (
            f"{greeting} Are you asking about live pigs, pork or meat, "
            "or both?"
        )
    if "still just looking" in text or "just looking for now" in text:
        return f"{greeting} No problem at all. Take your time - I am here if anything catches your eye."
    if reference.get("status") == "resolved":
        if "ms. piggy" in body.lower() and "piglet" in body.lower():
            return f"{greeting} Of course. What would you like to know about Ms. Piggy and her litter of piglets?"
        subject = headline or "the post you responded to"
        return f"{greeting} Of course. What would you like to know about {subject}?"
    if _general_health_age_question(text):
        return (
            f"{greeting} They do look healthy. I do not have their exact age in the conversation, "
            "so I would need to check that detail before giving you a definite answer."
        )
    if "piglet" in text and "post" in text:
        return f"{greeting} Yes, I know the piglet post. What would you like to know about it?"
    if _general_reference_words(text):
        return (
            f"{greeting} Of course. Are you asking about the piglets in the post, "
            "or was there something else on our page you wanted to know more about?"
        )
    return f"{greeting} Of course. What would you like to know more about?"


def _general_greeting_only(text):
    return bool(re.fullmatch(r"(hi|hello|hey|good (morning|afternoon|evening)|hallo)[!. ]*", text or ""))


def _general_reference_words(text):
    return bool(re.search(r"\b(this|that|these|those|it|the post|your post|the ad|your ad)\b", text or ""))


def _general_health_age_question(text):
    return "healthy" in (text or "") and bool(re.search(r"\bhow old\b|\bage\b", text or ""))


def _general_reply_is_clarification(reply, reference):
    return "?" in str(reply or "") and not bool((reference or {}).get("status") == "resolved")


def _explicit_new_request(text):
    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return False
    return any(
        phrase in normalized
        for phrase in (
            "this is a new request",
            "ignore my old request",
            "ignore my previous request",
            "start a new request",
            "hierdie is 'n nuwe versoek",
            "hierdie is ’n nuwe versoek",
            "ignoreer my ou versoek",
            "ignoreer my vorige versoek",
            "begin 'n nuwe versoek",
            "begin ’n nuwe versoek",
        )
    )


def load_live_stock_read_context(
    inbound,
    facts,
    *,
    intake_context_loader=None,
    conversation_history_loader=None,
    availability_loader=None,
    availability_evidence=None,
    environ=None,
):
    inbound = inbound if isinstance(inbound, dict) else {}
    source = environ if environ is not None else os.environ
    context_errors = []
    prior_context = {}
    reset_prior_context = _explicit_new_request(inbound.get("content"))
    intake = {"success": False, "lookup_status": "not_loaded", "items": []}
    chatwoot_history = {"success": False, "status": "not_loaded", "messages": []}
    if inbound.get("conversation_id"):
        try:
            loader = intake_context_loader or get_intake_context
            intake = loader(inbound.get("conversation_id"))
            if not reset_prior_context:
                prior_context = _prior_context_from_intake(intake)
        except Exception as exc:
            context_errors.append(_integration_failure("order_intake_context_read_failed", exc))
            intake = {"success": False, "lookup_status": "read_failed", "items": []}
        try:
            history_loader = conversation_history_loader or load_chatwoot_conversation_history
            chatwoot_history = history_loader(inbound.get("conversation_id"), source)
            if not reset_prior_context:
                history_prior = _prior_context_from_chatwoot_history(
                    chatwoot_history, inbound
                )
                if history_prior.get("evidence_complete") is False:
                    context_errors.append({
                        "status": "chatwoot_chronology_evidence_unavailable",
                        "reason": history_prior.get("reason")
                        or "chronology_ordering_unavailable",
                    })
                else:
                    prior_context = _merge_prior_context_packets(
                        prior_context, history_prior
                    )
        except Exception as exc:
            context_errors.append(_integration_failure("chatwoot_conversation_history_read_failed", exc))
            chatwoot_history = {"success": False, "status": "read_failed", "messages": []}
    herdmaster_evidence = {}
    availability_facts = merge_prior_live_stock_context(facts, prior_context)
    try:
        if availability_loader is not None:
            availability_rows = availability_loader()
            supplied = availability_evidence if isinstance(availability_evidence, dict) else {}
            herdmaster_evidence = {
                "agent": {"agent_id": "herdmaster", "authority_tier": "read_only"},
                "status": "replay_supplied_read_only_evidence",
                "provenance": supplied.get("provenance") or "replay_fixture",
                "freshness": supplied.get("freshness") or "sanitized_fixture",
                "summary": supplied.get("summary") if isinstance(supplied.get("summary"), dict) else {},
                "source_mode": "sanitized_replay_fixture",
            }
        else:
            availability_rows = list(get_sales_availability() or [])
            herdmaster_evidence = {
                "agent": {
                    "agent_id": "herdmaster",
                    "authority_tier": "canonical_read_only_projection",
                },
                "status": "canonical_sales_availability_reader",
                "provenance": "get_sales_availability",
                "canonical_row_count": len(availability_rows),
            }
        availability = summarize_live_stock_availability(availability_rows, availability_facts)
        availability = resolve_authoritative_availability(
            availability_rows,
            availability,
            database_url=source.get("DATABASE_URL"),
        )
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
        "chatwoot_authority_messages": _authority_chatwoot_messages(
            chatwoot_history,
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
    specialist_match_allowed = bool(
        facts.get("sales_lane") != "unclear"
        and (category or requested_weight_range or sex)
    )
    matched = []
    considered = []
    excluded = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        reasons = _availability_exclusion_reasons(row, category, sex, requested_weight_range)
        if not specialist_match_allowed:
            reasons = [*reasons, "affirmative_specialist_intent_and_minimum_constraints_required"]
        public_row = {
            **_availability_public_row(row),
            "selection_status": "excluded" if reasons else "eligible_exact_match",
            "exclusion_reasons": reasons,
        }
        considered.append(public_row)
        if reasons:
            excluded.append(public_row)
        else:
            matched.append(row)
    requested_bounds = _weight_bounds_from_text(requested_weight_range)
    requested_midpoint = sum(requested_bounds) / 2 if requested_bounds else None
    matched.sort(key=lambda row: _availability_rank_key(row, requested_midpoint))

    bucket_counts = {}
    customer_category_counts = {
        label: {"all": 0, "female": 0, "male": 0, "unknown": 0}
        for label in (
            "Young Piglets",
            "Weaner Piglets",
            "Grower Pigs",
            "Finisher Pigs",
            "Ready for Slaughter",
        )
    }
    customer_category_counts_complete = True
    for row in safe_rows:
        label = _customer_sale_category(row)
        if not label:
            customer_category_counts_complete = False
            continue
        bucket_counts[label] = bucket_counts.get(label, 0) + 1
        sex_label = _normal_sex(row.get("sex")) or "unknown"
        category_counts = customer_category_counts.setdefault(
            label,
            {"all": 0, "female": 0, "male": 0, "unknown": 0},
        )
        category_counts["all"] += 1
        category_counts[sex_label if sex_label in ("female", "male") else "unknown"] += 1
    eligible_weight_ages = []
    eligible_weight_evidence_complete = bool(safe_rows)
    for row in safe_rows:
        try:
            age = float(row.get("days_since_weight"))
        except (TypeError, ValueError):
            eligible_weight_evidence_complete = False
            continue
        if not math.isfinite(age) or age < 0:
            eligible_weight_evidence_complete = False
            continue
        if not _weight_evidence_consistent(row):
            eligible_weight_evidence_complete = False
            continue
        eligible_weight_ages.append(age)
    # Freshness belongs to the eligible matched evidence used for the offer.
    # Unmatched/excluded rows may legitimately lack a complete observation and
    # must not erase the timestamp of an otherwise exact, complete match.
    requested_quantity = (
        facts.get("quantity")
        if isinstance(facts.get("quantity"), int)
        else 0
    )
    exact_fulfillment = (
        requested_quantity > 0 and len(matched) >= requested_quantity
    )
    observation_rows = matched if exact_fulfillment else rows
    result_observations = [
        _parse_aware_utc_timestamp(row.get("eligibility_observed_at"))
        for row in observation_rows
        if isinstance(row, dict)
    ]
    observation_timestamp = (
        min(result_observations).isoformat()
        if result_observations and all(result_observations)
        else ""
    )
    return {
        "success": True,
        "status": "loaded",
        "read_only": True,
        "contract_version": "herdmaster_exact_animal_eligibility_v1",
        "observation_timestamp": observation_timestamp,
        "allocation_query_status": next((_clean(row.get("allocation_query_status"), 40) for row in rows if isinstance(row, dict) and row.get("allocation_query_status")), "unavailable"),
        "evidence_complete": bool(matched) and all(
            isinstance(row, dict) and row.get("evidence_complete") is True
            for row in matched
        ),
        "total_available_count": len(safe_rows),
        "matched_count": len(matched),
        "summary": bucket_counts,
        "customer_category_counts": customer_category_counts,
        "customer_category_counts_complete": customer_category_counts_complete,
        "matched_sample": [
            {**_availability_public_row(row), "selection_status": "eligible_exact_match", "exclusion_reasons": []}
            for row in matched[:10]
        ],
        # This complete eligible projection is the canonical alternative pool.
        # It is deliberately separate from the bounded diagnostic samples below.
        "eligible_projection_count": len(safe_rows),
        "eligible_projection": [
            {
                **_availability_offer_row(row),
                "selection_status": "sale_eligible",
                "exclusion_reasons": [],
            }
            for row in safe_rows
        ],
        "eligible_evidence_complete": bool(safe_rows) and all(
            isinstance(row, dict) and row.get("evidence_complete") is True
            for row in safe_rows
        ) and eligible_weight_evidence_complete,
        "weight_freshness_consistent": eligible_weight_evidence_complete,
        "latest_weight_date": max(
            (
                _clean(row.get("latest_weight_date") or row.get("last_weight_date"), 40)
                for row in safe_rows
                if _clean(row.get("latest_weight_date") or row.get("last_weight_date"), 40)
            ),
            default="",
        ),
        "oldest_weight_age_days": (
            max(eligible_weight_ages)
            if eligible_weight_evidence_complete and eligible_weight_ages
            else None
        ),
        "considered_count": len(considered),
        "considered_sample": considered[:25],
        "excluded_count": len(excluded),
        "excluded_sample": excluded[:25],
        "withdrawal_unknown_exclusions": [
            {
                "pig_id": row.get("pig_id"),
                "withdrawal_evidence_state": row.get(
                    "withdrawal_evidence_state"
                ),
                "eligibility_reason": row.get("eligibility_reason"),
            }
            for row in excluded
            if (
                row.get("withdrawal_evidence_state") == "unknown"
                and _normal_text(row.get("purpose")) == "sale"
                and _normal_text(row.get("status")) == "active"
                and _normal_text(row.get("on_farm")) == "yes"
            )
        ],
        "matching_gate": {
            "affirmative_specialist_intent": facts.get("sales_lane") == LANE_LIVE_STOCK,
            "minimum_usable_constraints": specialist_match_allowed,
        },
    }


def _canonical_availability_question(facts, latest_customer_text):
    """Query the existing HERDMASTER reader with retained customer constraints."""
    facts = facts if isinstance(facts, dict) else {}
    parts = ["Current sale-eligible live pigs"]
    for label, key in (
        ("category", "category"),
        ("weight", "weight_range"),
        ("quantity", "quantity"),
        ("sex", "sex"),
        ("timing", "timing"),
        ("location", "location"),
    ):
        value = facts.get(key)
        if not _blank(value):
            parts.append(f"{label}: {value}")
    split = facts.get("sex_split") if isinstance(facts.get("sex_split"), dict) else {}
    if split:
        parts.append(
            f"sex split: {int(split.get('female') or 0)} female, "
            f"{int(split.get('male') or 0)} male"
        )
    if len(parts) == 1 and latest_customer_text:
        parts.append(f"customer request: {_clean(latest_customer_text, 300)}")
    return "; ".join(parts)


def _parse_aware_utc_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _customer_sale_category(row):
    for key in (
        "sale_category",
        "suggested_price_category",
        "calculated_stage",
        "weight_band",
    ):
        category = _customer_sale_category_value(row.get(key))
        if category:
            return category
    return ""


def _customer_sale_category_value(value):
    text = _normal_text(value)
    if "weaner" in text:
        return "Weaner Piglets"
    if "young" in text or "piglet" in text:
        return "Young Piglets"
    if "grower" in text:
        return "Grower Pigs"
    if "finisher" in text:
        return "Finisher Pigs"
    if "ready for slaughter" in text or "ready_for_slaughter" in text:
        return "Ready for Slaughter"
    return ""


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
        attachments = row.get("attachments")
        if not content and not attachments:
            continue
        messages.append({
            "id": _clean(row.get("id"), 100),
            "message_type": row.get("message_type"),
            "private": row.get("private") is True,
            "content": content,
            "created_at": row.get("created_at"),
            "attachments": attachments,
            "message_context": _public_message_context(
                row,
                row.get("content_attributes") if isinstance(row.get("content_attributes"), dict) else {},
            ),
        })
    return {"success": True, "status": "loaded", "messages": messages}


def load_chatwoot_conversation_identity(conversation_id, environ=None):
    source = environ if environ is not None else os.environ
    conversation_id = _clean(conversation_id, 100)
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV), 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV), 80)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not conversation_id:
        return {"success": False, "status": "conversation_id_required"}
    if not base_url or not account_id or not token:
        return {"success": False, "status": "chatwoot_conversation_identity_not_configured"}
    request = urllib_request.Request(
        f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}",
        headers={"api_access_token": token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw or "{}")
    except urllib_error.HTTPError as exc:
        return {"success": False, "status": f"chatwoot_conversation_identity_http_{exc.code}"}
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return _integration_failure("chatwoot_conversation_identity_read_failed", exc)
    conversation = parsed.get("payload") if isinstance(parsed, dict) and isinstance(parsed.get("payload"), dict) else parsed
    conversation = conversation if isinstance(conversation, dict) else {}
    inbox = conversation.get("inbox") if isinstance(conversation.get("inbox"), dict) else {}
    meta = conversation.get("meta") if isinstance(conversation.get("meta"), dict) else {}
    sender = meta.get("sender") if isinstance(meta.get("sender"), dict) else {}
    contact = conversation.get("contact") if isinstance(conversation.get("contact"), dict) else {}
    latest = (
        conversation.get("last_non_activity_message")
        if isinstance(
            conversation.get("last_non_activity_message"), dict
        )
        else {}
    )
    return {
        "success": True,
        "status": "chatwoot_conversation_identity_loaded",
        "account_id": account_id,
        "conversation_id": _clean(conversation.get("id") or conversation_id, 100),
        "contact_id": _clean(sender.get("id") or contact.get("id"), 100),
        "inbox_id": _clean(conversation.get("inbox_id") or inbox.get("id"), 100),
        "can_reply": conversation.get("can_reply") is True,
        "latest_message_id": _clean(latest.get("id"), 100),
        "latest_message_type": latest.get("message_type"),
        "contains_secret_values": False,
    }


def verify_chatwoot_current_inbound(inbound, environ=None):
    """Recheck exact provider chronology immediately before durable claim."""
    inbound = inbound if isinstance(inbound, dict) else {}
    identity = load_chatwoot_conversation_identity(
        inbound.get("conversation_id"), environ
    )
    expected = {
        "account_id": _clean(inbound.get("account_id"), 100),
        "conversation_id": _clean(inbound.get("conversation_id"), 100),
        "contact_id": _clean(inbound.get("contact_id"), 100),
        "inbox_id": _clean(inbound.get("inbox_id"), 100),
    }
    exact_identity = bool(
        identity.get("success") is True
        and all(expected.values())
        and all(
            _clean(identity.get(key), 100) == value
            for key, value in expected.items()
        )
    )
    latest_matches = bool(
        _clean(identity.get("latest_message_id"), 100)
        == _clean(inbound.get("message_id"), 100)
        and identity.get("latest_message_type") in (0, "incoming")
    )
    return {
        "allowed": bool(
            exact_identity
            and latest_matches
            and identity.get("can_reply") is True
        ),
        "identity_exact": exact_identity,
        "latest_inbound_exact": latest_matches,
        "reply_window_open": identity.get("can_reply") is True,
        "contains_identity_values": False,
        "writes_performed": False,
    }


def _prior_context_from_chatwoot_history(history, inbound):
    history = history if isinstance(history, dict) else {}
    if not history.get("success"):
        return {}
    current_id = _clean((inbound or {}).get("message_id"), 100)
    incoming_texts = []
    raw_messages = (
        history.get("messages")
        if isinstance(history.get("messages"), list)
        else []
    )
    relevant_messages = [
        message for message in raw_messages
        if isinstance(message, dict)
        and _chatwoot_message_is_incoming(message)
        and not (
            current_id
            and _clean(message.get("id"), 100) == current_id
        )
    ]
    if any(
        _chatwoot_history_instant(message.get("created_at")) is None
        for message in relevant_messages
    ):
        return {
            "interest": {},
            "source": "chatwoot_conversation_history",
            "evidence_complete": False,
            "reason": "chronology_timestamp_unavailable",
        }
    ordered_messages = sorted(
        relevant_messages,
        key=lambda message: (
            _chatwoot_history_instant(message.get("created_at")),
            _clean(message.get("id"), 100),
        ),
    )
    latest_context_at = (
        ordered_messages[-1].get("created_at")
        if ordered_messages
        else None
    )
    for message in ordered_messages:
        content = _clean_multiline(message.get("content"), 500)
        if content:
            incoming_texts.append(content)
    if not incoming_texts:
        return {}
    latest_reset_index = next(
        (
            index
            for index in range(len(incoming_texts) - 1, -1, -1)
            if _explicit_new_request(incoming_texts[index])
        ),
        None,
    )
    if latest_reset_index is not None:
        incoming_texts = incoming_texts[latest_reset_index:]
    facts = {}
    for text in incoming_texts[-8:]:
        extracted = extract_live_stock_facts(text, inbound or {})
        extracted_lane = extracted.get("sales_lane")
        extracted_confidence = float(
            extracted.get("lane_confidence") or 0
        )
        extracted_reasons = list(extracted.get("lane_reasons") or [])
        if (
            extracted_lane == LANE_LIVE_STOCK
            and extracted_confidence >= 0.9
        ):
            facts["sales_lane"] = extracted_lane
            facts["lane_confidence"] = extracted_confidence
            facts["lane_reasons"] = extracted_reasons
        elif (
            extracted_lane in {
                LANE_MEAT,
                "slaughter_abattoir_sales",
            }
            and extracted_confidence >= 0.8
        ) or "mixed_sales_intent" in extracted_reasons:
            # An affirmative change or genuinely mixed request supersedes the
            # older lane; unclear/terse qualification answers do not.
            facts["sales_lane"] = extracted_lane
            facts["lane_confidence"] = extracted_confidence
            facts["lane_reasons"] = extracted_reasons
        for key in (
            "quantity",
            "category",
            "sex",
            "sex_split",
            "weight_range",
            "timing",
            "location",
            "payment_method",
        ):
            if (
                bool(extracted.get(key))
                if key == "sex_split"
                else not _blank(extracted.get(key))
            ):
                facts[key] = extracted.get(key)
        for key in ("quote_requested", "order_commitment", "reservation_requested", "breeding_interest"):
            if extracted.get(key):
                facts[key] = True
    interest = {
        "sales_lane": facts.get("sales_lane") if facts.get("sales_lane") == LANE_LIVE_STOCK else "",
        "lane_confidence": (
            float(facts.get("lane_confidence") or 0)
            if facts.get("sales_lane") == LANE_LIVE_STOCK
            else 0
        ),
        "quantity": facts.get("quantity") or "",
        "category": facts.get("category") or "",
        "sex": facts.get("sex") or "",
        "sex_split": dict(facts.get("sex_split") or {}),
        "weight_range": facts.get("weight_range") or "",
        "timing": facts.get("timing") or "",
        "location": facts.get("location") or "",
        "payment_method": facts.get("payment_method") or "",
        "quote_requested": bool(facts.get("quote_requested")),
        "order_commitment": bool(facts.get("order_commitment")),
    }
    return {
        "interest": interest,
        "source": "chatwoot_conversation_history",
        "evidence_complete": True,
        "latest_context_at": latest_context_at,
        "conversation_id": _clean((inbound or {}).get("conversation_id"), 100),
        "contact_id": _clean((inbound or {}).get("contact_id"), 100),
        "inbox_id": _clean((inbound or {}).get("inbox_id"), 100),
        "account_id": _clean((inbound or {}).get("account_id"), 100),
    } if any(interest.values()) else {}


def _chatwoot_history_instant(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        instant = float(value)
        return instant if math.isfinite(instant) else None
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            instant = float(text)
            return instant if math.isfinite(instant) else None
        except ValueError:
            parsed = _parse_aware_utc_timestamp(text)
            return parsed.timestamp() if parsed is not None else None
    return None


def _merge_prior_context_packets(primary, secondary):
    primary_interest = (primary or {}).get("interest") if isinstance((primary or {}).get("interest"), dict) else {}
    secondary_interest = (secondary or {}).get("interest") if isinstance((secondary or {}).get("interest"), dict) else {}
    if not secondary_interest:
        return primary or {}
    merged = dict(primary_interest)
    customer_qualification_fields = {
        "quantity", "category", "sex", "sex_split", "weight_range", "timing",
        "location",
    }
    for key, value in secondary_interest.items():
        if key in customer_qualification_fields and (
            bool(value) if key == "sex_split" else not _blank(value)
        ):
            # Customer chronology is authoritative when an intake projection
            # and the customer's own messages overlap.
            if (
                key == "category"
                and _normal_category(merged.get(key)) == _normal_category(value)
            ):
                continue
            merged[key] = value
        elif _blank(merged.get(key)) and not _blank(value):
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
    chronology_rows = [
        message for message in messages
        if isinstance(message, dict)
        and not _chatwoot_message_is_activity(message)
    ]
    return {
        "success": bool(history.get("success")),
        "status": history.get("status", ""),
        "message_count": len(messages),
        "incoming_count": sum(1 for message in messages if _chatwoot_message_is_incoming(message)),
        "chronology_evidence_complete": all(
            _chatwoot_history_instant(message.get("created_at")) is not None
            for message in chronology_rows
        ),
    }


def _compact_chatwoot_history_messages(history, limit=10, current_message_id=""):
    history = history if isinstance(history, dict) else {}
    messages = history.get("messages") if isinstance(history.get("messages"), list) else []
    current_message_id = _clean(current_message_id, 100)
    if all(
        _chatwoot_history_instant(message.get("created_at")) is not None
        for message in messages
        if isinstance(message, dict) and not _chatwoot_message_is_activity(message)
    ):
        messages = sorted(
            messages,
            key=lambda message: (
                _chatwoot_history_instant(message.get("created_at"))
                if isinstance(message, dict)
                and not _chatwoot_message_is_activity(message)
                else float("-inf"),
                _clean(message.get("id"), 100)
                if isinstance(message, dict)
                else "",
            ),
        )
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


def _authority_chatwoot_messages(history, limit=20):
    history = history if isinstance(history, dict) else {}
    messages = history.get("messages") if isinstance(history.get("messages"), list) else []
    authoritative = []
    for message in messages[-max(int(limit or 20), 1):]:
        if not isinstance(message, dict):
            continue
        authoritative.append({
            "id": _clean(message.get("id"), 100),
            "message_type": message.get("message_type"),
            "direction": _clean(message.get("direction"), 20),
            "private": message.get("private") is True,
            "created_at": message.get("created_at"),
            "content": _clean_multiline(message.get("content"), 1800),
            "attachments": (
                message.get("attachments")
            ),
        })
    return authoritative


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
                "account_id": inbound.get("account_id") or "",
                "conversation_id": inbound.get("conversation_id") or "",
                "contact_id": inbound.get("contact_id") or "",
                "inbox_id": inbound.get("inbox_id") or "",
                "message_id": inbound.get("message_id") or "",
                "last_inbound_at": inbound.get("last_inbound_at") or "",
                "customer_name": inbound.get("customer_name") or "",
                "customer_phone": inbound.get("customer_phone") or "",
                "channel": inbound.get("channel") or "",
                "content": inbound.get("content") or "",
                "identity_provenance": (
                    inbound.get("identity_provenance") or {}
                ),
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
    try:
        pricing_projection, pricing_status = list_live_stock_price_entries(
            limit=500,
            database_url=(environ or {}).get("DATABASE_URL"),
        )
    except Exception as exc:
        pricing_projection = {
            "success": False,
            "configured": False,
            "source": "",
            "price_entries": [],
            "status": "canonical_price_projection_unavailable",
            "error_type": exc.__class__.__name__,
        }
        pricing_status = 503
    price_entries = (
        pricing_projection.get("price_entries") or []
        if pricing_status == 200 and isinstance(pricing_projection, dict)
        else []
    )
    match_packet = build_live_stock_match_packet(
        facts, availability, price_entries=price_entries
    )
    draft_packet = build_live_stock_draft_order_packet(
        inbound, facts, match_packet, price_entries=price_entries
    )
    price_answer_packet = build_live_stock_price_answer_packet(
        facts, match_packet, price_entries=price_entries
    )
    ledger_evidence = {
        "agent": {
            "agent_id": "ledger",
            "authority_tier": "canonical_read_only_projection",
        },
        "status": (
            "canonical_price_projection_loaded"
            if pricing_status == 200
            else "canonical_price_projection_unavailable"
        ),
        "source": (
            pricing_projection.get("source")
            if isinstance(pricing_projection, dict)
            else ""
        ),
        "entry_count": len(price_entries),
        "payment": {
            "status": "unknown",
            "reason": "payment_authority_not_requested_for_livestock_composition",
        },
    }
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
        match_packet,
    )
    owner_example_projection = _load_owner_correction_examples(
        inbound,
        environ or {},
        owner_example_loader=owner_example_loader,
        facts=facts,
        conversation_plan=conversation_plan,
    )
    owner_correction_examples = owner_example_projection.get("examples") or []
    information_reply = build_live_stock_information_response(
        facts,
        availability,
        environ=environ,
        price_entries=price_entries,
    )
    contextual_sales = build_contextual_sales_recommendation(
        inbound,
        facts,
        context_packet.get("chatwoot_history_messages") or [],
        availability,
        price_loader=list_live_stock_price_entries,
        price_projection=pricing_projection,
        database_url=(environ or {}).get("DATABASE_URL"),
    )
    customer_guidance = build_live_stock_customer_guidance(inbound, facts)
    qualification_followup = build_live_stock_qualification_followup(
        inbound,
        facts,
        missing,
        conversation_plan=conversation_plan,
        protected_price_unanswered=bool(
            _asks_price_question(inbound.get("content"))
            and price_answer_packet.get("can_answer_price") is not True
            and information_reply.get("status")
            not in {
                "availability_and_pricing_verified",
                "price_only_verified",
            }
            and contextual_sales.get("status")
            == "commercial_evidence_unavailable"
        ),
    )
    customer_guidance_preferred = _prefer_customer_size_guidance(
        customer_guidance=customer_guidance,
        contextual_sales=contextual_sales,
        information_reply=information_reply,
        price_answer_packet=price_answer_packet,
        information_scope=facts.get("information_scope"),
        sales_lane=facts.get("sales_lane"),
        latest_customer_text=inbound.get("content"),
    )
    fallback_reply = (
        customer_guidance.get("reply_text")
        if customer_guidance_preferred
        else qualification_followup.get("reply_text")
        if qualification_followup.get("applicable") is True
        else contextual_sales.get("recommendation")
        if contextual_sales.get("applicable") is True
        else information_reply.get("reply_text") or _safe_reply_draft(
            facts,
            route,
            missing,
            availability,
            blockers,
            price_answer_packet,
            conversation_plan,
        )
    )
    llm_draft = (
        {
            "used": False,
            "status": (
                "deterministic_customer_size_guidance"
                if customer_guidance_preferred
                else "commercial_general_information_fallback_blocked"
            ),
            "reply_text": "",
            "reply_source": "",
        }
        if (
            customer_guidance_preferred
            or qualification_followup.get("applicable") is True
            or contextual_sales.get("general_information_fallback_blocked") is True
        )
        else _build_llm_reply_draft_if_enabled(
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
    )
    if llm_draft.get("used") and _reply_exposes_internal_animal_evidence(llm_draft.get("reply_text"), match_packet):
        llm_draft = {
            **llm_draft,
            "used": False,
            "status": "llm_reply_internal_animal_evidence_blocked",
            "reply_text": "",
            "contains_internal_animal_evidence": True,
        }
    proposed_reply = llm_draft.get("reply_text") if llm_draft.get("used") else fallback_reply
    reply_source = (
        "deterministic_customer_size_guidance"
        if customer_guidance_preferred
        else "deterministic_supported_qualification_followup"
        if qualification_followup.get("applicable") is True
        else "contextual_sales_source_backed_owner_draft"
        if contextual_sales.get("applicable") is True
        else llm_draft.get("reply_source")
        if llm_draft.get("used")
        else "deterministic_read_only_guard"
    )
    # This is a composition candidate only. The exact provider-bound handler
    # rebuilds and authorizes the canonical packet after every later rewrite
    # and immediately before any delivery review or claim.
    evidence_offer = {
        "status": "candidate_only_final_canonical_gate_required",
        "should_reply": False,
    }
    reply = proposed_reply
    return {
        "version": RUNTIME_VERSION,
        "agent": "sam_live_stock_backend",
        "mode": "read_only_stage_3",
        "inbound": {
            "account_id": inbound.get("account_id") or "",
            "conversation_id": inbound.get("conversation_id") or "",
            "contact_id": inbound.get("contact_id") or "",
            "inbox_id": inbound.get("inbox_id") or "",
            "message_id": inbound.get("message_id") or "",
            "last_inbound_at": inbound.get("last_inbound_at") or "",
            "customer_name": inbound.get("customer_name") or "",
            "customer_phone": inbound.get("customer_phone") or "",
            "channel": inbound.get("channel") or "",
            "content": inbound.get("content") or "",
            "identity_provenance": inbound.get("identity_provenance") or {},
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
        "information_response": information_reply,
        "contextual_sales": contextual_sales,
        "customer_guidance": customer_guidance,
        "qualification_followup": qualification_followup,
        "canonical_evidence_offer": evidence_offer,
        "customer_guidance_preferred": customer_guidance_preferred,
        "agent_evidence": agent_evidence,
        "owner_action_packet": owner_action_packet,
        "owner_correction_examples": owner_correction_examples,
        "owner_example_projection": owner_example_projection,
        "draft_order_packet": draft_packet,
        "llm_draft": llm_draft,
        "blockers": blockers,
        "ready_for_runtime_next_step": ready_for_runtime_next_step,
        "suggested_reply_text": reply,
        "deterministic_fallback_reply_text": fallback_reply,
        "reply_source": reply_source,
        "should_reply": bool(reply),
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
    reset_request_context = _explicit_new_request(inbound.get("content"))
    patch = {
        "collection_location": _normal_intake_location(facts.get("location")),
        "collection_time_text": _clean(facts.get("timing"), 120),
        "last_customer_message": _clean(inbound.get("content"), 600),
        "notes": notes,
    }
    if reset_request_context:
        patch.update({
            "collection_location": (
                _normal_intake_location(facts.get("location"))
                if not _blank(facts.get("location"))
                else ""
            ),
            "collection_date": "",
            "collection_time": "",
            "payment_method": "",
            "quote_requested": bool(facts.get("quote_requested")),
            "order_commitment": bool(facts.get("order_commitment")),
        })
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
        "reset_request_context": reset_request_context,
        "patch": (
            patch
            if reset_request_context
            else {key: value for key, value in patch.items() if value not in ("", None)}
        ),
        "items": [item] if item else [],
    }


def validate_live_stock_intake_payload(payload):
    validation = validate_intake_update_payload(payload)
    return {
        "is_valid": bool(validation.get("is_valid")),
        "errors": list(validation.get("errors") or []),
        "cleaned_data": validation.get("cleaned_data") if isinstance(validation.get("cleaned_data"), dict) else {},
    }


def write_live_stock_intake_if_enabled(
    inbound,
    facts,
    decision,
    environ=None,
    intake_writer=None,
    isolated_runtime=None,
):
    source = environ if environ is not None else os.environ
    isolated_control_present = bool(
        isinstance(isolated_runtime, dict)
        and isolated_runtime.get("control_event_id")
    )
    legacy_intake_permitted = bool(
        isinstance(isolated_runtime, dict)
        and isolated_runtime.get("legacy_fallback_permitted") is True
    )
    isolated_intake = bool(
        isolated_control_present
        and isolated_runtime.get("allowed") is True
        and isolated_runtime.get("intake_write_authorized") is True
    )
    if not (
        isolated_intake
        if isolated_control_present
        else (
            _truthy(source.get(INTAKE_WRITE_ENABLED_ENV))
            if isolated_runtime is None or legacy_intake_permitted
            else False
        )
    ):
        return {"attempted": False, "success": False, "status": "sam_live_stock_intake_write_disabled"}
    if (decision or {}).get("sales_lane") != LANE_LIVE_STOCK:
        return {"attempted": False, "success": False, "status": "sam_live_stock_intake_wrong_lane"}
    if "read_context_error" in ((decision or {}).get("blockers") or []):
        return {
            "attempted": False,
            "success": False,
            "status": "sam_live_stock_intake_evidence_unavailable",
        }
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


def build_live_stock_prepared_owner_action_bundle(inbound, facts, conversation_plan=None, draft_packet=None, price_answer_packet=None, match_packet=None):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    conversation_plan = conversation_plan if isinstance(conversation_plan, dict) else {}
    draft_packet = draft_packet if isinstance(draft_packet, dict) else {}
    price_answer_packet = price_answer_packet if isinstance(price_answer_packet, dict) else {}
    match_packet = match_packet if isinstance(match_packet, dict) else {}
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
        "stock_preselection": {
            "selected": list(match_packet.get("matched_sample") or []),
            "excluded": list(match_packet.get("excluded_sample") or []),
            "considered_count": int(match_packet.get("considered_count") or 0),
            "selected_pig_ids": list(match_packet.get("selected_pig_ids") or []),
            "quantity_shortfall": int(match_packet.get("quantity_shortfall") or 0),
            "proposal_only": True,
            "observation_timestamp": _clean(match_packet.get("observation_timestamp"), 40),
            "allocation_query_status": _clean(match_packet.get("allocation_query_status"), 40) or "unavailable",
            "evidence_complete": match_packet.get("evidence_complete") is True,
            "ranking": list(match_packet.get("ranking") or []),
            "proposed_order_lines": list(draft_packet.get("proposed_order_lines") or []),
            "price_evidence": price_answer_packet.get("pricing") if isinstance(price_answer_packet.get("pricing"), dict) else {},
            "exact_animal_assignment_written": False,
            "owner_approval_required": True,
        },
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
        decision.get("match_packet") if isinstance(decision.get("match_packet"), dict) else {},
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
        decision.get("match_packet") if isinstance(decision.get("match_packet"), dict) else {},
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
    if route.get("lane") not in {"", LANE_LIVE_STOCK, LANE_FARM_GENERAL}:
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
    # A known timing/collection acknowledgement must not displace a still
    # missing ordinary qualification fact. Ask the smallest useful question
    # before confirming a later-stage collection action.
    if missing and internal_action == "confirm_collection":
        return "ask_one_missing_detail"
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


def build_live_stock_match_packet(facts, availability, *, price_entries=None):
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
    minimum_constraints = bool(
        facts.get("sales_lane") != "unclear"
        and quantity > 0
        and (not _blank(facts.get("category")) or not _blank(facts.get("weight_range")))
    )
    if not minimum_constraints:
        exact_count = 0
        matched = []
        status = "not_ready"
    selected = matched[:quantity] if minimum_constraints else []
    considered = _rank_and_price_live_stock_alternatives(
        facts,
        list(
            availability.get("eligible_projection")
            or availability.get("considered_sample")
            or []
        ),
        price_entries=price_entries,
    )
    return {
        "version": "sam_live_stock_match_packet_v1",
        "read_only": True,
        "requested_quantity": quantity,
        "exact_match_count": exact_count,
        "match_status": status,
        "complete_fulfillment": quantity > 0 and exact_count >= quantity,
        "partial_fulfillment": quantity > 0 and 0 < exact_count < quantity,
        "quantity_shortfall": max(quantity - exact_count, 0),
        "matched_sample": selected,
        "selected_pig_ids": [row.get("pig_id") for row in selected if row.get("pig_id")],
        "considered_count": int(availability.get("considered_count") or 0),
        "considered_sample": considered,
        "eligible_projection_count": int(
            availability.get("eligible_projection_count") or len(considered)
        ),
        "eligible_projection_complete": (
            int(availability.get("eligible_projection_count") or len(considered))
            == len(considered)
        ),
        "latest_weight_date": _clean(availability.get("latest_weight_date"), 40),
        "oldest_weight_age_days": availability.get("oldest_weight_age_days"),
        "excluded_count": int(availability.get("excluded_count") or 0),
        "excluded_sample": list(availability.get("excluded_sample") or []),
        "owner_review_required": True,
        "can_create_draft_order": quantity > 0 and exact_count > 0,
        "observation_timestamp": _clean(availability.get("observation_timestamp"), 40),
        "allocation_query_status": _clean(availability.get("allocation_query_status"), 40) or "unavailable",
        "evidence_complete": availability.get("evidence_complete") is True,
        "ranking": [
            {"rank": index + 1, "pig_id": row.get("pig_id"), "basis": "weight_distance_then_freshness_then_pig_id"}
            for index, row in enumerate(selected)
        ],
        "proposal_only": True,
        "matching_gate": {
            "affirmative_specialist_intent": facts.get("sales_lane") == LANE_LIVE_STOCK,
            "minimum_usable_constraints": minimum_constraints,
        },
    }


def _rank_and_price_live_stock_alternatives(
    facts, rows, *, price_entries=None
):
    """Produce deterministic, price-provenanced alternatives for composition."""
    facts = facts if isinstance(facts, dict) else {}
    wanted_sex = _normal_text(facts.get("sex"))
    wanted_weight = _weight_midpoint(facts.get("weight_range"))
    eligible = [
        dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("live_stock_sale_eligible") is True
    ]

    def rank_key(row):
        weight = _safe_float(row.get("current_weight_kg"))
        distance = (
            abs(weight - wanted_weight)
            if weight is not None and wanted_weight is not None
            else 999999
        )
        row_sex = _normal_text(row.get("sex"))
        sex_penalty = 0 if (
            not wanted_sex
            or wanted_sex in {"any", "either", "mixture", "mixed"}
            or row_sex == wanted_sex
        ) else 1
        freshness = int(row.get("days_since_weight") or 999999)
        return (
            sex_penalty,
            distance,
            freshness,
            str(row.get("pig_id") or ""),
        )

    eligible.sort(key=rank_key)
    price_cache = {}
    for index, row in enumerate(eligible, 1):
        category = row.get("sale_category") or row.get("suggested_price_category")
        weight_band = row.get("weight_band") or _normal_intake_weight_range(
            row.get("current_weight_kg"),
            _normal_intake_category(category),
        )
        cache_key = (
            str(category or ""),
            str(weight_band or ""),
            str(row.get("sex") or ""),
        )
        if cache_key not in price_cache:
            if price_entries is None:
                price_cache[cache_key] = resolve_live_stock_price_rule(
                    *cache_key,
                )
            else:
                price_cache[cache_key] = resolve_live_stock_price_rule(
                    *cache_key,
                    price_entries=price_entries,
                )
        pricing = price_cache[cache_key]
        row["alternative_rank"] = index
        row["target_weight_kg"] = wanted_weight
        row["weight_distance_kg"] = (
            round(abs(float(row["current_weight_kg"]) - wanted_weight), 3)
            if wanted_weight is not None
            and _safe_float(row.get("current_weight_kg")) is not None
            else None
        )
        row["alternative_ranking_basis"] = (
            "requested_sex_then_absolute_weight_distance_then_weight_freshness_then_pig_id"
        )
        row["pricing"] = dict(pricing) if pricing.get("found") is True else {}
    return eligible


def _weight_midpoint(value):
    numbers = [
        float(item)
        for item in re.findall(r"\d+(?:\.\d+)?", str(value or ""))
    ]
    if not numbers:
        return None
    return sum(numbers[:2]) / min(len(numbers), 2)


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_live_stock_draft_order_packet(
    inbound, facts, match_packet=None, *, price_entries=None
):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    match_packet = match_packet if isinstance(match_packet, dict) else {}
    item = _live_stock_sync_requested_item(facts)
    price_rule = _live_stock_price_rule_for_packet(
        facts, match_packet, price_entries=price_entries
    )
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
    proposed_order_lines = [
        {
            "pig_id": row.get("pig_id"),
            "tag_number": row.get("tag_number"),
            "sex": row.get("sex"),
            "current_weight_kg": row.get("current_weight_kg"),
            "latest_weight_date": row.get("latest_weight_date"),
            "current_pen_id": row.get("current_pen_id"),
            "pricing": price_rule,
            "proposal_only": True,
            "owner_approval_required": True,
        }
        for row in (match_packet.get("matched_sample") or [])
        if isinstance(row, dict) and row.get("pig_id")
    ]
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
        "proposed_order_lines": proposed_order_lines,
        "exact_animal_assignment_written": False,
        "warnings": [
            "Creates draft order only when explicit env gate is enabled.",
            "Does not reserve pigs.",
            "Does not send quote/customer message.",
        ],
    }


def build_live_stock_price_answer_packet(
    facts, match_packet=None, *, price_entries=None
):
    facts = facts if isinstance(facts, dict) else {}
    match_packet = match_packet if isinstance(match_packet, dict) else {}
    price_rule = _live_stock_price_rule_for_packet(
        facts, match_packet, price_entries=price_entries
    )
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


def build_live_stock_information_response(
    facts, availability, *, environ=None, price_entries=None
):
    """Build a bounded owner-review information draft from current truth only."""
    facts = facts if isinstance(facts, dict) else {}
    availability = availability if isinstance(availability, dict) else {}
    if facts.get("information_scope") != "grower_finisher":
        return {
            "version": "sam_live_stock_information_response_v1",
            "applicable": False,
            "reply_text": "",
            "customer_send_allowed": False,
            **_authority_flags(),
        }

    source = environ if isinstance(environ, Mapping) else os.environ
    if not isinstance(price_entries, list):
        listed, status_code = list_live_stock_price_entries(
            limit=500,
            database_url=source.get("DATABASE_URL"),
        )
        price_entries = (
            listed.get("price_entries")
            if status_code == 200 and isinstance(listed, dict)
            else []
        )
        price_entries = price_entries if isinstance(price_entries, list) else []
    now_key = datetime.now(timezone.utc).isoformat()
    categories = ("Grower Pigs", "Finisher Pigs")
    active_prices = {}
    for category in categories:
        rows = []
        for entry in price_entries:
            if not isinstance(entry, dict) or entry.get("active") is False:
                continue
            if _clean(entry.get("sale_category"), 80) != category:
                continue
            effective_from = _clean(entry.get("effective_from"), 60)
            effective_to = _clean(entry.get("effective_to"), 60)
            if effective_from and effective_from > now_key:
                continue
            if effective_to and effective_to <= now_key:
                continue
            if entry.get("unit_price") in ("", None):
                continue
            rows.append(entry)
        if rows:
            active_prices[category] = rows

    summary = availability.get("summary") if isinstance(availability.get("summary"), dict) else {}
    counts = {
        category: sum(
            int(value or 0)
            for label, value in summary.items()
            if _normal_information_category(label) == category
        )
        for category in categories
    }
    availability_known = availability.get("success") is True
    lines = []
    for category in categories:
        prices = active_prices.get(category) or []
        count = counts.get(category, 0)
        if availability_known and count <= 0:
            continue
        if not prices:
            continue
        amounts = sorted({float(row["unit_price"]) for row in prices})
        price_text = (
            _money_label(amounts[0])
            if len(amounts) == 1
            else f"{_money_label(amounts[0])}–{_money_label(amounts[-1])}"
        )
        label = "Growers" if category == "Grower Pigs" else "Finishers"
        if availability_known:
            lines.append(f"- {label}: {count} currently eligible; {price_text}, depending on weight.")
        else:
            lines.append(f"- {label}: {price_text}, depending on weight.")

    if not lines:
        return {
            "version": "sam_live_stock_information_response_v1",
            "applicable": True,
            "status": "authoritative_category_evidence_unavailable",
            "reply_text": "Which approximate weight do you mean by the bigger pigs?",
            "availability_known": availability_known,
            "categories": [],
            "customer_send_allowed": False,
            **_authority_flags(),
        }
    opening = (
        "For the bigger pigs currently eligible, I can verify:"
        if availability_known
        else "Current verified prices for the bigger pig categories are:"
    )
    return {
        "version": "sam_live_stock_information_response_v1",
        "applicable": True,
        "status": "availability_and_pricing_verified" if availability_known else "price_only_verified",
        "reply_text": "\n".join([
            opening,
            *lines,
            "Which approximate weight would suit you?",
        ]),
        "availability_known": availability_known,
        "categories": [
            {
                "sale_category": category,
                "eligible_count": counts.get(category) if availability_known else None,
                "active_price_entry_count": len(active_prices.get(category) or []),
            }
            for category in categories
            if (not availability_known or counts.get(category, 0) > 0)
            and active_prices.get(category)
        ],
        "customer_send_allowed": False,
        **_authority_flags(),
    }


def create_live_stock_draft_order_if_enabled(
    inbound,
    facts,
    decision,
    environ=None,
    draft_order_creator=None,
    draft_order_syncer=None,
    isolated_runtime=None,
):
    source = environ if environ is not None else os.environ
    isolated_control_present = bool(
        isinstance(isolated_runtime, dict)
        and isolated_runtime.get("control_event_id")
    )
    legacy_order_permitted = bool(
        isinstance(isolated_runtime, dict)
        and isolated_runtime.get("legacy_fallback_permitted") is True
    )
    if isolated_control_present:
        return {
            "attempted": False,
            "success": False,
            "status": "sam_live_stock_draft_order_isolated_level1_prohibited",
        }
    if isinstance(isolated_runtime, dict) and not legacy_order_permitted:
        return {
            "attempted": False,
            "success": False,
            "status": "sam_live_stock_draft_order_control_unavailable",
        }
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
    protected_action_reasons = []
    score = 100
    auto_general = decision.get("conversation_ownership") == AUTO_GENERAL

    if _hostile_or_scam_signal(text):
        escalation_reasons.append("hostile_or_scam_location_challenge")
        issues.append("close_conversation_recommended")
        score -= 35
    if auto_general and _explicit_human_request(text):
        escalation_reasons.append("customer_explicitly_requested_human")
        score -= 20
    if _price_challenge_signal(text):
        protected_action_reasons.append("negotiated_price_owner_authority")
        issues.append("negotiated_price_requires_owner_decision")
    if _natural_close_signal(text):
        issues.append("natural_close_no_reply_needed")
        score -= 5
    if facts.get("breeding_interest"):
        protected_action_reasons.append("breeding_stock_owner_authority")
    if facts.get("reservation_requested"):
        protected_action_reasons.append("reservation_owner_authority")
    if facts.get("order_commitment"):
        protected_action_reasons.append("final_order_owner_authority")
    if _payment_confirmation_signal(text):
        protected_action_reasons.append("payment_confirmation_owner_authority")
    if blockers and not auto_general:
        for blocker in blockers:
            blocker = str(blocker)
            if blocker in {"breeding_or_replacement_stock_owner_gate", "reservation_request_owner_gate"}:
                continue
            if blocker.startswith("lane_not_live_stock:"):
                escalation_reasons.append(blocker)
            else:
                issues.append(blocker)
    if not auto_general and decision.get("sales_lane") not in {LANE_LIVE_STOCK, LANE_FARM_GENERAL}:
        escalation_reasons.append("wrong_or_unclear_lane")
        score -= 20
    if missing:
        issues.append("missing_fields:" + ",".join(missing[:5]))
    if reply:
        lowered = reply.lower()
        unsafe_reply_patterns = [
            (r"\breserved\b|\bheld\b|\bbooked\b", "implies_reservation"),
            (
                r"\b(?:once|after|when)\b.{0,20}\bpayment\b.{0,50}\b(?:secure|reserve|hold|confirm)\b"
                r"|\bpayment(?: details?| method)?\b.{0,30}\b(?:will|would|does|can)\b.{0,20}\b(?:secure|reserve|hold|confirm)\b",
                "implies_payment_secures_animal",
            ),
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
        "owner_authority_required": bool(protected_action_reasons),
        "protected_action_reasons": sorted(set(protected_action_reasons)),
        "no_reply_recommended": _natural_close_signal(text),
        "escalation_required": bool(escalation_reasons or blocked),
        "escalation_reasons": sorted(set(escalation_reasons)),
        "issues": sorted(set(issues)),
        "blocked_reasons": sorted(set(blocked)),
        "conversation_mode_recommendation": "HUMAN" if escalation_reasons or blocked else "AUTO",
        "recommended_action": _conversation_review_action(
            text,
            missing,
            escalation_reasons,
            blocked,
            reply,
            protected_action_reasons,
        ),
    }


def _explicit_human_request(text):
    return bool(re.search(
        r"\b(speak|talk|chat)\s+(to|with)\s+(a\s+)?(human|person|owner|charl)\b"
        r"|\b(can|may|could)\s+i\s+(speak|talk)\s+(to|with)\s+(charl|the owner|a human|a person)\b"
        r"|\bput me through to (charl|the owner|a human|a person)\b",
        text or "",
    ))


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
        delivery = classify_chatwoot_response(sent)
        confirmed = delivery.get("delivery_state") in CONFIRMED_STATES
        return {
            "success": True,
            "status": (
                "sam_live_stock_owner_reply_confirmed_delivered"
                if confirmed
                else "sam_live_stock_owner_reply_accepted_unverified"
                if delivery.get("delivery_state") == CHATWOOT_ACCEPTED_UNVERIFIED
                else "sam_live_stock_owner_reply_delivery_ambiguous"
            ),
            "packet": packet,
            "chatwoot": {
                "outgoing_message_id": delivery.get("chatwoot_outgoing_message_id"),
                "response_status": delivery.get("chatwoot_response_status"),
                "provider_identity_class": delivery.get("provider_identity_class"),
                "status_code_class": delivery.get("status_code_class"),
                "contains_raw_provider_identity": False,
            },
            "delivery": delivery,
            "customer_send_confirmed": confirmed,
            "automatic_retry_prohibited": True,
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
        if facts.get("order_commitment"):
            return _localized_reply(
                facts,
                "Thanks, I understand that you are ready to proceed. I have noted your reservation request, but the farm must approve the exact animal before I can confirm or reserve it for you.",
                "Dankie, ek verstaan dat jy gereed is om voort te gaan. Ek het jou reserveringsversoek aangeteken, maar die plaas moet die presiese dier goedkeur voordat ek dit vir jou kan bevestig of reserveer.",
            )
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
            "We are based in the Riversdale area. Normal live-pig handover is arranged in Riversdale or Albertinia. What type of pig are you looking for?",
            "Ons is in die Riversdal-omgewing. Gewone oorhandiging van lewende varke word in Riversdal of Albertinia gereël. Watter tipe vark soek jy?",
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
            "Normal live-pig handover is arranged in Riversdale or Albertinia. Delivery or another arrangement needs an exact owner decision and is not promised.",
            "Gewone oorhandiging van lewende varke word in Riversdal of Albertinia gereël. Aflewering of 'n ander reëling vereis 'n presiese eienaarbesluit en word nie belowe nie.",
        )
    if action == "confirm_collection":
        return _localized_reply(
            facts,
            "Normal live-pig handover is arranged in Riversdale or Albertinia. Any different arrangement needs owner confirmation.",
            "Gewone oorhandiging van lewende varke word in Riversdal of Albertinia gereël. Enige ander reëling vereis eienaarbevestiging.",
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
                "Ons help met lewende varke en algemene plaasvrae. Vleisverkope is nog nie oop nie. "
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
                "Gewone oorhandiging van lewende varke word in Riversdal of Albertinia gereël. "
                "Sê vir my waarna jy soek en wanneer jy dit nodig het."
            )
        followup = (
            "Normal live-pig handover is arranged in Riversdale or Albertinia. "
            "Tell me what you need and when you need it, and I will help from there."
        )
        return (
            f"{greeting}{location} "
            f"{followup}"
        )
    return (
        f"{greeting}{location} "
        "If you are asking about live pigs, handover in Riversdale or Albertinia, or the farm itself, send me what you need and I will help from there."
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


def _asks_availability_question(text):
    return _has_any(
        _normal_text(text),
        ("available", "availability", "in stock", "on hand"),
    )


def _asks_delivery_question(text):
    return _has_any(
        _normal_text(text),
        ("deliver", "delivery", "transport", "courier"),
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
        "Current price estimate:",
        f"- {quantity_label}{sex_label}{category}, {weight_band}: {unit} each",
    ]
    if quantity > 1 and packet.get("estimated_total") not in ("", None):
        lines.append(f"- Estimated total: {_money_label(packet.get('estimated_total'))}")
    lines.append("- This is not a reservation.")
    lines.append("- The farm must confirm the actual animals before anything is promised.")
    return "\n".join(lines)


CUSTOMER_LIVE_STOCK_SIZE_OPTIONS = (
    {
        "customer_label": "Small piglets",
        "weight_text": "approximately 2 to 6 kg",
        "canonical_category": "Young Piglets",
        "minimum_kg": 2,
        "maximum_kg": 6,
    },
    {
        "customer_label": "Weaned piglets",
        "weight_text": "approximately 7 to 19 kg",
        "canonical_category": "Weaner Piglets",
        "minimum_kg": 7,
        "maximum_kg": 19,
    },
    {
        "customer_label": "Growing pigs",
        "weight_text": "approximately 20 to 49 kg",
        "canonical_category": "Grower Pigs",
        "minimum_kg": 20,
        "maximum_kg": 49,
    },
    {
        "customer_label": "Larger pigs",
        "weight_text": "approximately 50 to 79 kg",
        "canonical_category": "Finisher Pigs",
        "minimum_kg": 50,
        "maximum_kg": 79,
    },
    {
        "customer_label": "Slaughter-size pigs",
        "weight_text": "approximately 80 kg and above",
        "canonical_category": "Ready for Slaughter",
        "minimum_kg": 80,
        "maximum_kg": None,
    },
)


def build_live_stock_customer_guidance(inbound, facts):
    """Explain customer-facing sizes while keeping taxonomy mapping internal."""
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    if _normal_text(facts.get("message_intent")) in {
        "location question",
        "location_question",
        "delivery question",
        "delivery_question",
        "timing or collection",
        "timing_or_collection",
        "social acknowledgement",
        "social_acknowledgement",
        "social close",
        "social_close",
    }:
        return {
            "applicable": False,
            "reply_text": "",
            "options": [],
            "canonical_mapping": {},
            "customer_send_allowed": False,
            "guidance_scope": "",
        }
    category = _normal_category(facts.get("category"))
    weight_range = _clean(facts.get("weight_range"), 80)
    customer_text = _normal_text(
        inbound.get("content") or facts.get("latest_customer_message")
    )
    explanation_requested = any(
        marker in customer_text
        for marker in ("what is", "what does", "mean", "understand", "which category")
    )
    vague_all = category in {"", "live pig", "live_pig"}
    vague_piglet = category == "piglet" and not weight_range
    needs_sex = _blank(facts.get("sex"))
    needs_quantity = _quantity_number(facts.get("quantity")) <= 0
    if not (
        vague_all or vague_piglet or explanation_requested
        or needs_sex or needs_quantity
    ):
        return {
            "applicable": False,
            "reply_text": "",
            "options": [],
            "canonical_mapping": {},
            "customer_send_allowed": False,
            "guidance_scope": "",
        }
    options = (
        CUSTOMER_LIVE_STOCK_SIZE_OPTIONS
        if vague_all
        else CUSTOMER_LIVE_STOCK_SIZE_OPTIONS[:2]
        if vague_piglet
        else tuple(
            option for option in CUSTOMER_LIVE_STOCK_SIZE_OPTIONS
            if option["canonical_category"] == {
                "piglet": "Young Piglets",
                "weaner": "Weaner Piglets",
                "grower": "Grower Pigs",
                "finisher": "Finisher Pigs",
                "ready_for_slaughter": "Ready for Slaughter",
            }.get(category)
        )
        if explanation_requested
        else ()
    )
    name = _first_name(inbound.get("customer_name") or facts.get("customer_name"))
    greeting = f"Hi {name}, thanks for your message." if name else "Hi, thanks for your message."
    lines = [greeting]
    questions = []
    if options:
        lines[0] += " Here are practical size ranges to choose from:"
        lines.append("")
        lines.extend(
            f"- {option['customer_label']}: {option['weight_text']}"
            for option in options
        )
        if vague_all or vague_piglet:
            questions.append("Which size would suit you")
    if needs_quantity and not options:
        questions.append("how many do you need")
    elif needs_sex and not options:
        questions.append("Would you prefer a male, female, or either")
    lines.extend(["", _joined_customer_questions(questions)])
    lines.append(
        "Price and current availability still need to be confirmed separately."
    )
    return {
        "contract_version": "customer_size_guidance_v1",
        "claim_types": [],
        "applicable": True,
        "reply_text": "\n".join(lines),
        "options": [
            {
                "customer_label": option["customer_label"],
                "weight_text": option["weight_text"],
            }
            for option in options
        ],
        "canonical_mapping": {
            option["customer_label"]: {
                "category": option["canonical_category"],
                "minimum_kg": option["minimum_kg"],
                "maximum_kg": option["maximum_kg"],
            }
            for option in options
        },
        "questions_asked": questions,
        "guidance_scope": (
            "all_sizes" if vague_all
            else "piglet_sizes" if vague_piglet
            else "category_explanation" if explanation_requested
            else "qualification_only"
        ),
        "availability_claimed": False,
        "price_claimed": False,
        "customer_send_allowed": False,
    }


def build_live_stock_qualification_followup(
    inbound,
    facts,
    missing,
    *,
    conversation_plan=None,
    protected_price_unanswered=False,
):
    """Advance known Livestock interest while protected facts stay pending."""
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    conversation_plan = (
        conversation_plan
        if isinstance(conversation_plan, dict)
        else {}
    )
    fields = {
        (
            "location"
            if str(value).split(".")[-1].strip().lower()
            == "collection_location"
            else str(value).split(".")[-1].strip().lower()
        )
        for value in (missing or [])
        if isinstance(value, str)
    }
    questions = []
    if "quantity" in fields and _quantity_number(facts.get("quantity")) <= 0:
        questions.append("how many do you need")
    elif "location" in fields and _blank(facts.get("location")):
        questions.append("what town or area are you in")
    if (
        not questions
        and "timing" in fields
        and _blank(facts.get("timing"))
    ):
        questions.append("when would you need them")
    if not questions:
        return {
            "applicable": False,
            "reply_text": "",
            "questions_asked": [],
            "customer_send_allowed": False,
        }
    current_text = _normal_text(inbound.get("content"))
    known_selection = bool(
        not _blank(facts.get("category"))
        and _quantity_number(facts.get("quantity")) > 0
        and not _blank(facts.get("sex"))
        and fields
        and fields <= {"location", "timing"}
        and _has_any(current_text, ("weaned piglets", "weaner piglets"))
        and _has_any(current_text, ("male", "males"))
        and _has_any(current_text, ("female", "females"))
    )
    timing_followup_missing_quantity = bool(
        "quantity" in fields
        and _quantity_number(facts.get("quantity")) <= 0
        and not _blank(facts.get("timing"))
        and (
            not _blank(facts.get("category"))
            or not _blank(facts.get("weight_range"))
        )
    )
    collection_followup_missing_quantity = bool(
        conversation_plan.get("next_action") == "confirm_collection"
        and "quantity" in fields
        and _quantity_number(facts.get("quantity")) <= 0
        and (
            not _blank(facts.get("category"))
            or not _blank(facts.get("weight_range"))
        )
    )
    protected_price_followup_missing_quantity = bool(
        protected_price_unanswered
        and _asks_price_question(current_text)
        and "quantity" in fields
        and _quantity_number(facts.get("quantity")) <= 0
        and (
            not _blank(facts.get("category"))
            or not _blank(facts.get("weight_range"))
        )
    )
    if (
        not (
            known_selection
            or timing_followup_missing_quantity
            or collection_followup_missing_quantity
            or protected_price_followup_missing_quantity
        )
        or facts.get("reservation_requested")
        or facts.get("breeding_interest")
        or facts.get("order_commitment")
        or not _blank(facts.get("payment_method"))
    ):
        return {
            "applicable": False,
            "reply_text": "",
            "questions_asked": [],
            "customer_send_allowed": False,
        }
    name = _first_name(
        inbound.get("customer_name") or facts.get("customer_name")
    )
    greeting = f"Hi {name}, thanks" if name else "Thanks"
    reply = (
        f"{greeting} — I have noted the livestock details so far. "
        f"{_sentence_case(_joined_customer_questions(questions))} "
        "Price and current availability still need to be confirmed separately."
    )
    return {
        "contract_version": "supported_qualification_followup_v1",
        "applicable": True,
        "reply_text": reply,
        "questions_asked": questions,
        "availability_claimed": False,
        "price_claimed": False,
        "delivery_promised": False,
        "customer_send_allowed": False,
    }


def _prefer_customer_size_guidance(
    *,
    customer_guidance,
    contextual_sales,
    information_reply,
    price_answer_packet,
    information_scope,
    sales_lane,
    latest_customer_text="",
):
    """Prefer safe guidance only when no stronger source-backed answer exists."""
    latest_customer_text = _normal_text(latest_customer_text)
    return bool(
        customer_guidance.get("applicable") is True
        and sales_lane == LANE_LIVE_STOCK
        and (
            (
                customer_guidance.get("guidance_scope")
                == "qualification_only"
                and customer_guidance.get("questions_asked")
                == ["how many do you need"]
                and bool(customer_guidance.get("canonical_mapping") == {})
                and not _asks_price_question(latest_customer_text)
                and not _asks_quote(latest_customer_text)
                and not (
                    _asks_availability_question(latest_customer_text)
                    and information_reply.get("status")
                    == "availability_and_pricing_verified"
                )
                and not _asks_location_question(latest_customer_text)
                and not _asks_delivery_question(latest_customer_text)
            )
            or (
                not information_scope
                and contextual_sales.get("status") in {
                    "commercial_evidence_unavailable",
                    "not_commercial_livestock",
                }
                and information_reply.get("status") not in {
                    "availability_and_pricing_verified",
                    "price_only_verified",
                }
                and price_answer_packet.get("can_answer_price") is not True
            )
        )
    )


def _joined_customer_questions(questions):
    questions = [str(question).strip() for question in questions if str(question).strip()]
    if not questions:
        return ""
    if len(questions) == 1:
        return questions[0] + "?"
    return ", ".join(questions[:-1]) + ", and " + questions[-1] + "?"


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
    source = source if isinstance(source, Mapping) else {}
    diagnostics = _llm_runtime_diagnostics(source)
    if not _truthy(source.get(LLM_ENABLED_ENV)):
        return {"used": False, "status": "llm_disabled", "runtime_diagnostics": diagnostics}
    if route.get("lane") != LANE_LIVE_STOCK:
        return {"used": False, "status": "llm_wrong_lane", "runtime_diagnostics": diagnostics}
    if not (_configured_model(source) and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip()):
        return {"used": False, "status": "llm_not_configured", "runtime_diagnostics": diagnostics}
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
        return {"used": False, "status": "llm_empty_response", "runtime_diagnostics": diagnostics}
    if raw.get("_llm_error"):
        return {"used": False, "status": "llm_call_failed", "llm_error": raw.get("_llm_error"), "runtime_diagnostics": diagnostics}
    reply = _clean_multiline(raw.get("reply_text") or raw.get("suggested_reply_text"), 1800)
    if not reply:
        return {"used": False, "status": "llm_no_reply_text", "runtime_diagnostics": diagnostics}
    return {
        "used": True,
        "status": "llm_reply_draft_used",
        "reply_source": "llm_live_stock_reply_draft",
        "reply_text": reply,
        "confidence": raw.get("confidence", ""),
        "notes": _clean(raw.get("notes"), 240),
        "runtime_diagnostics": diagnostics,
    }


def _build_auto_general_llm_reply_if_enabled(
    inbound,
    facts,
    context_packet,
    fallback_reply,
    source,
    *,
    drafter=None,
):
    source = source if isinstance(source, Mapping) else {}
    diagnostics = _llm_runtime_diagnostics(source)
    if not _truthy(source.get(LLM_ENABLED_ENV)):
        return {"used": False, "status": "llm_disabled", "runtime_diagnostics": diagnostics}
    if not (_configured_model(source) and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip()):
        return {"used": False, "status": "llm_not_configured", "runtime_diagnostics": diagnostics}
    reference = (
        context_packet.get("recovered_reference")
        if isinstance(context_packet.get("recovered_reference"), dict)
        else {}
    )
    packet = {
        "rules": [
            "Write one short, natural WhatsApp reply as SAM for Amadeus Farm.",
            "General or unknown intent is valid. Greet, acknowledge, answer verified general context, or ask one useful clarification.",
            "Use a resolved referral or quoted-message subject naturally. Do not infer a sales lane from vague pronouns.",
            "Do not claim stock, price, availability, location, performance, age, order, reservation, or payment facts unless explicitly verified here.",
            "Do not invoke or suggest specialist tools or owner escalation merely because the lane is unknown.",
            "Ask at most one question.",
        ],
        "inbound": {
            "customer_name": inbound.get("customer_name") or "",
            "message": _clean(inbound.get("content"), 1000),
        },
        "reference": reference,
        "recent_chatwoot_history": context_packet.get("chatwoot_history_messages") or [],
        "fallback_reply": fallback_reply,
    }
    caller = drafter or _call_sam_live_stock_reply_llm
    raw = caller(packet, source)
    if not isinstance(raw, dict):
        return {"used": False, "status": "llm_empty_response", "runtime_diagnostics": diagnostics}
    if raw.get("_llm_error"):
        return {
            "used": False,
            "status": "llm_call_failed",
            "llm_error": raw.get("_llm_error"),
            "runtime_diagnostics": diagnostics,
        }
    proposed_lane = _clean(raw.get("lane") or raw.get("sales_lane"), 80).lower()
    if proposed_lane and proposed_lane not in {"general", "unknown", "unclear", "auto_general"}:
        return {
            "used": False,
            "status": "llm_wrong_lane_returned_to_auto_general",
            "runtime_diagnostics": diagnostics,
        }
    reply = _clean_multiline(raw.get("reply_text") or raw.get("suggested_reply_text"), 1800)
    if not reply:
        return {"used": False, "status": "llm_no_reply_text", "runtime_diagnostics": diagnostics}
    if reply.count("?") > 1:
        return {
            "used": False,
            "status": "llm_general_multiple_questions_blocked",
            "runtime_diagnostics": diagnostics,
        }
    return {
        "used": True,
        "status": "llm_auto_general_reply_draft_used",
        "reply_source": "llm_auto_general_reply_draft",
        "reply_text": reply,
        "confidence": raw.get("confidence", ""),
        "notes": _clean(raw.get("notes"), 240),
        "runtime_diagnostics": diagnostics,
    }


def _llm_runtime_diagnostics(source):
    supported = isinstance(source, Mapping)
    source = source if supported else {}
    enabled_present = LLM_ENABLED_ENV in source
    model = _configured_model(source) if supported else ""
    api_key_configured = bool(str(source.get(OPENAI_API_KEY_ENV, "") or "").strip())
    return {
        "source_is_mapping": supported,
        "source_is_process_environment": source is os.environ,
        "llm_enabled_key_present": enabled_present,
        "llm_enabled": _truthy(source.get(LLM_ENABLED_ENV)),
        "model_configured": bool(model),
        "api_key_configured": api_key_configured,
        "llm_configured": bool(model and api_key_configured),
        "contains_secret_values": False,
    }


def _load_owner_correction_examples(inbound, source, owner_example_loader=None, facts=None, conversation_plan=None):
    source = source if isinstance(source, dict) else {}
    if not _owner_example_retrieval_enabled(source):
        return {
            "version": "sam_owner_example_projection_v1",
            "projection_id": "",
            "fresh": False,
            "status": "disabled",
            "examples": [],
            "request_blocking_load": False,
            "canonical_authority": False,
        }
    return read_owner_example_projection(loader=owner_example_loader)


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


def _reservation_protection_explained(reply):
    text = _normal_text(reply)
    has_reservation_acknowledgement = bool(re.search(r"\b(reserv(?:e|ation)|reserveer|reservering)\w*\b", text))
    has_farm_approval = bool(re.search(r"\b(farm|plaas)\b.{0,80}\b(approv\w*|goedkeur\w*)\b", text))
    has_before_confirmation = bool(re.search(
        r"\bbefore\b.{0,80}\b(confirm\w*|reserv\w*)\b"
        r"|\bvoordat\b.{0,80}\b(bevestig\w*|reserveer\w*)\b",
        text,
    ))
    return has_reservation_acknowledgement and has_farm_approval and has_before_confirmation


def _compose_reservation_protection_reply(facts, llm_reply):
    acknowledgement = _localized_reply(
        facts,
        "I have noted your reservation request. The farm must approve the exact pig before I can confirm or reserve it for you.",
        "Ek het jou reserveringsversoek aangeteken. Die plaas moet die presiese vark goedkeur voordat ek dit vir jou kan bevestig of reserveer.",
    )
    original = _clean_multiline(llm_reply, 1300)
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", original) if item.strip()]
    has_partial_reservation_wording = bool(re.search(r"\b(reserv\w*|reserveer\w*|reservering\w*)\b", original.lower()))
    question_count = original.count("?")
    if not sentences or has_partial_reservation_wording or question_count > 1:
        return _complete_reservation_protection_reply(facts)

    opening_pattern = re.compile(
        r"^(?:hi|hello|hey|good morning|good afternoon|hallo|goeie m[oô]re|goeiem[oô]re|goeie middag|"
        r"thanks|thank you|dankie|got it|i understand|ek verstaan)\b",
        re.IGNORECASE,
    )
    if opening_pattern.search(sentences[0]):
        composed = [sentences[0], acknowledgement, *sentences[1:]]
    else:
        composed = [acknowledgement, *sentences]
    return _clean_multiline(" ".join(composed), 1800)


def _complete_reservation_protection_reply(facts):
    return _localized_reply(
        facts,
        "Thanks for letting me know you are ready. I have noted your reservation request, but the farm must approve the exact pig before I can confirm or reserve it for you.",
        "Dankie dat jy laat weet het jy is gereed. Ek het jou reserveringsversoek aangeteken, maar die plaas moet die presiese vark goedkeur voordat ek dit vir jou kan bevestig of reserveer.",
    )


def _live_stock_price_rule_for_packet(
    facts, match_packet, *, price_entries=None
):
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
    return resolve_live_stock_price_rule(
        category, weight_band, sex, price_entries=price_entries
    )


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
    text = normalize_customer_display_name(value)
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
    }.get(field, "")


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
        "location": _persisted_customer_qualification(
            known.get("collection_location")
        ),
        "timing": _persisted_customer_qualification(
            known.get("collection_time_text") or known.get("collection_date")
        ),
        "payment_method": _persisted_customer_qualification(
            known.get("payment_method")
        ),
        "quote_requested": bool(known.get("quote_requested")),
        "order_commitment": bool(known.get("order_commitment")),
    }
    active_items = [item for item in items if isinstance(item, dict) and str(item.get("status") or "").lower() == "active"]
    if active_items:
        item = active_items[0]
        persisted_category = _persisted_customer_qualification(
            item.get("category")
        )
        interest.update({
            "quantity": _persisted_customer_qualification(item.get("quantity")),
            "category": persisted_category,
            "weight_range": _persisted_intake_weight_qualification(
                item.get("weight_range"), persisted_category
            ),
            "sex": _persisted_customer_qualification(item.get("sex")),
        })
    return {"interest": interest, "source": "order_intake_context"} if any(interest.values()) else {}


def _persisted_customer_qualification(value):
    """Exclude historical default sentinels from customer-supplied facts."""
    text = _clean(value, 120)
    if _normal_text(text) in {
        "",
        "any",
        "unknown",
        "unspecified",
        "not supplied",
        "not_supplied",
        "default",
        "defaulted",
        "inferred",
        "n/a",
        "na",
    }:
        return ""
    return value


def _persisted_intake_weight_qualification(value, category):
    value = _persisted_customer_qualification(value)
    if _blank(value):
        return ""
    historical_defaults = {
        "piglet": "5_to_6_Kg",
        "weaner": "10_to_14_Kg",
        "grower": "30_to_34_Kg",
        "finisher": "60_to_64_Kg",
        "ready_for_slaughter": "80_to_84_Kg",
    }
    if _clean(value, 80) == historical_defaults.get(_normal_category(category)):
        # Historical rows do not distinguish this manufactured category
        # default from customer evidence, so it must fail closed.
        return ""
    return value


def _extract_category(text):
    if re.search(r"\b\d{1,2}\s*(?:week|weeks|wk|wks)\s+old\b", text):
        return "piglet"
    if _has_any(text, ("weaned piglet", "weaned piglets")):
        return "weaner"
    if _has_any(text, ("small piglet", "small piglets", "piglet", "piglets")):
        return "piglet"
    if _has_any(text, ("weaner", "weaners")):
        return "weaner"
    if _has_any(text, ("growing pig", "growing pigs", "grower", "growers")):
        return "grower"
    if _has_any(text, ("larger pig", "larger pigs", "finisher", "finishers")):
        return "finisher"
    if _has_any(text, ("slaughter-size pig", "slaughter-size pigs", "ready for slaughter", "slaughter pig", "80kg", "85kg", "90kg")):
        return "ready_for_slaughter"
    if _asks_about_big_live_pigs(text):
        return "live_pig"
    if _has_any(text, ("live pig", "live pigs", "female pigs", "male pigs", "pigs to raise", "buy pigs", "pigs for sale", "pig for sale", "pigs available")):
        return "live_pig"
    return ""


def _has_live_stock_fact_signal(facts):
    facts = facts if isinstance(facts, dict) else {}
    category = _normal_text(facts.get("category"))
    return bool(
        category in {"piglet", "weaner", "grower", "finisher", "ready for slaughter", "ready_for_slaughter", "live pig", "live_pig"}
        or facts.get("weight_range")
        or facts.get("quantity")
    )


def _has_live_stock_followup_signal(text):
    return _has_any(
        _normal_text(text),
        (
            "how much",
            "price",
            "pricce",
            "prise",
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
    split_counts = re.search(
        r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+(?:x\s+)?(?:males?|females?|boars?|gilts?|sows?)"
        r"\s+and\s+"
        r"(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+(?:x\s+)?(?:males?|females?|boars?|gilts?|sows?)\b",
        text,
    )
    if split_counts:
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        return sum(
            int(value) if value.isdigit() else number_words[value]
            for value in split_counts.groups()
        )
    match = re.search(
        r"\b(?:buy|purchase|koop)\s+(\d{1,3})(?!\d)"
        r"(?!\s*(?:kg|kilograms?)\b)",
        text,
    )
    if match:
        return int(match.group(1))
    match = re.search(
        r"\b(?:for|need|want)\s+(\d{1,3})(?!\d)"
        r"(?!\s*(?:st|nd|rd|th)\b)"
        r"(?!\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\b)"
        r"(?!\s*(?:kg|kilograms?)\b)",
        text,
    )
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
            r"(?:big\b|male|female|males|females|piglets|pigs|weaners|growers|finishers|gilts|boars|sows)\b",
            text,
        ):
            return value
    return ""


def _extract_sex_split(text):
    """Retain an explicit female/male quantity split across follow-up turns."""
    number_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    matches = re.findall(
        r"\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+(?:x\s+)?(males?|females?|boars?|gilts?|sows?)\b",
        text,
    )
    split = {"female": 0, "male": 0}
    for raw_count, raw_sex in matches:
        count = int(raw_count) if raw_count.isdigit() else number_words[raw_count]
        sex = "female" if raw_sex in {"female", "females", "gilt", "gilts", "sow", "sows"} else "male"
        split[sex] += count
    return split if split["female"] and split["male"] else {}


def _extract_sex(text):
    male = _has_any(text, ("male", "males", "boar", "boars"))
    female = _has_any(text, ("female", "females", "gilt", "gilts", "sow", "sows"))
    explicit_flexibility = _has_any(text, (
        "any sex",
        "sex does not matter",
        "sex doesn't matter",
        "sex is not important",
        "male or female is fine",
        "male or female, no preference",
        "either male or female",
        "either sex",
    ))
    if explicit_flexibility:
        return "any"
    if female and not male:
        return "female"
    if male and not female:
        return "male"
    if male and female:
        if _has_any(text, ("either", "no preference", "doesn't matter")):
            return "any"
        return "split"
    if _has_any(text, (
        "either size",
        "either category",
        "either weaner",
        "either grower",
        "either piglet",
    )):
        return ""
    if _has_any(text, (
        "either",
        "either is fine",
        "doesn't matter",
        "no preference",
    )):
        return "any"
    return ""


def _extract_weight_range(text):
    unit = r"(?:kg|kilograms?)"
    range_match = re.search(
        rf"\b(\d{{1,3}})\s*(?:{unit})?\s*(?:-|to|and)\s*"
        rf"(\d{{1,3}})\s*{unit}\b",
        text,
    )
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        if low > high:
            low, high = high, low
        return f"{low}-{high} kg"
    known_range = re.search(
        r"\b(2\s*(?:-|to)\s*6|7\s*(?:-|to)\s*19|"
        r"20\s*(?:-|to)\s*49|50\s*(?:-|to)\s*79)\b",
        text,
    )
    if known_range:
        low, high = re.findall(r"\d{1,3}", known_range.group(1))
        return f"{int(low)}-{int(high)} kg"
    single = re.search(
        rf"\b(?:around|about|roughly|\+-)?\s*(\d{{1,3}})\s*{unit}\b",
        text,
    )
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
    month = (
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)"
    )
    day = r"(?:0?[1-9]|[12]\d|3[01])"
    dated = re.search(
        rf"\b(?:(?:on|by|before)\s+(?:the\s+)?"
        rf"({day}(?:st|nd|rd|th))|"
        rf"({day}(?:st|nd|rd|th)?\s+{month})|"
        rf"({month}\s+{day}(?:st|nd|rd|th)?))\b",
        text,
    )
    if dated:
        return next(group for group in dated.groups() if group)
    return ""


def _extract_location(text):
    known = (
        "riversdale", "albertinia", "still bay", "stilbaai", "jongensfontein", "heidelberg", "mossel bay",
        "port elizabeth", "gqeberha", "east london", "eastern cape", "western cape", "cape town", "george",
        "worcester",
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
    return _has_any(text, ("price", "pricce", "prise", "cost", "how much", "quote", "quotation", "prys"))


def _asks_formal_quote(text):
    return bool(re.search(r"\b(?:quote|quotation)\b", _normal_text(text)))


def _asks_price_question(text):
    return _has_any(text, ("price", "pricce", "prise", "cost", "how much", "prys"))


def _asks_about_big_live_pigs(text):
    text = _normal_text(text)
    return _has_any(
        text,
        (
            "big one",
            "big ones",
            "bigger one",
            "bigger ones",
            "large pig",
            "large pigs",
        ),
    )


def _normal_information_category(value):
    text = _normal_text(value)
    if "grower" in text:
        return "Grower Pigs"
    if "finisher" in text:
        return "Finisher Pigs"
    return ""


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
        "reserveer",
        "hou hulle",
    ))


def _payment_or_pop_interest(facts):
    text = _normal_text(" ".join(str(value or "") for value in (facts or {}).values()))
    return _has_any(text, ("pop", "proof of payment", "paid", "payment", "eft"))


def _payment_confirmation_signal(text):
    text = _normal_text(text)
    return _has_any(text, (
        "proof of payment",
        "payment confirmed",
        "payment received",
        "payment cleared",
        "money reflects",
        "i have paid",
        "i paid",
        "pop sent",
    ))


def _category_from_weight_range(weight_range):
    weight = _representative_weight(weight_range)
    if not weight:
        return ""
    if weight < 7:
        return "piglet"
    if weight < 20:
        return "weaner"
    if weight < 50:
        return "grower"
    if weight < 80:
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
    # Herdmaster must explicitly classify an animal as Sale before it can
    # support matching, price evidence, or draft/quote preparation.  An
    # omitted purpose is unknown, not an implicit sale approval.
    if _clean(row.get("exact_animal_eligibility_contract_version"), 100) != "herdmaster_exact_animal_eligibility_v1":
        return False
    if row.get("live_stock_sale_eligible") is not True or row.get("evidence_complete") is not True:
        return False
    if _normal_text(row.get("purpose")) != "sale":
        return False
    if _normal_text(row.get("allocation_query_status")) not in {"known", "success"}:
        return False
    if _normal_text(row.get("allocation_evidence_state")) != "known unallocated":
        return False
    if _normal_text(row.get("withdrawal_evidence_state")) not in {"not applicable", "cleared"}:
        return False
    if _normal_text(row.get("medical_status")) != "clear":
        return False
    status = _normal_text(row.get("status"))
    on_farm = _normal_text(row.get("on_farm"))
    reserved = _normal_text(row.get("reserved_status"))
    available = _normal_text(row.get("available_for_sale"))
    if status in {"sold", "exited", "dead", "terminal"}:
        return False
    if on_farm and on_farm not in {"yes", "true", "1", "on farm"}:
        return False
    if reserved not in {"not reserved"}:
        return False
    if available and available not in {"yes", "true", "1"}:
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
        return False
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
        "latest_weight_date": _clean(row.get("latest_weight_date") or row.get("last_weight_date"), 40),
        "days_since_weight": row.get("days_since_weight"),
        "current_pen_id": _clean(row.get("current_pen_id"), 80),
        "current_pen_name": _clean(row.get("current_pen_name"), 120),
        "weight_band": _clean(row.get("weight_band"), 80),
        "sale_category": _clean(row.get("sale_category"), 120),
        "suggested_price_category": _clean(row.get("suggested_price_category"), 120),
        # These fields make the match's eligibility inspectable without
        # exposing private herd or customer notes in an owner review packet.
        "purpose": _clean(row.get("purpose"), 40),
        "status": _clean(row.get("status"), 40),
        "on_farm": _clean(row.get("on_farm"), 40),
        "reserved_status": _clean(row.get("reserved_status"), 40),
        "available_for_sale": _clean(row.get("available_for_sale"), 40),
        "live_stock_sale_eligible": row.get("live_stock_sale_eligible"),
        "exact_animal_eligibility_contract_version": _clean(row.get("exact_animal_eligibility_contract_version"), 100),
        "evidence_complete": row.get("evidence_complete"),
        "eligibility_observed_at": _clean(row.get("eligibility_observed_at"), 40),
        "allocation_query_status": _clean(row.get("allocation_query_status"), 40),
        "allocation_evidence_state": _clean(row.get("allocation_evidence_state"), 60),
        "health_status": _clean(row.get("health_status"), 80),
        "medical_status": _clean(row.get("medical_status"), 80),
        "withdrawal_clear": _clean(row.get("withdrawal_clear"), 40),
        "withdrawal_evidence_state": _clean(row.get("withdrawal_evidence_state"), 40),
        "current_withdrawal_end_date": _clean(row.get("current_withdrawal_end_date"), 40),
        "reserved_for_order_id": _clean(row.get("reserved_for_order_id"), 100),
        "eligibility_reason": _clean(row.get("live_stock_sale_reason") or row.get("sales_notes"), 300),
    }


def _availability_offer_row(row):
    """Minimize the complete internal alternative pool to composition evidence."""
    public = _availability_public_row(row)
    return {
        key: public.get(key)
        for key in (
            "pig_id",
            "sex",
            "current_weight_kg",
            "latest_weight_date",
            "days_since_weight",
            "weight_band",
            "sale_category",
            "suggested_price_category",
            "live_stock_sale_eligible",
            "exact_animal_eligibility_contract_version",
            "evidence_complete",
            "eligibility_observed_at",
            "allocation_query_status",
            "allocation_evidence_state",
            "withdrawal_evidence_state",
        )
    } | {"weight_freshness_consistent": _weight_evidence_consistent(row)}


def _weight_evidence_consistent(row, *, now=None):
    raw_date = _clean(
        row.get("latest_weight_date") or row.get("last_weight_date"), 40
    )
    try:
        reported_age = float(row.get("days_since_weight"))
    except (TypeError, ValueError):
        return False
    if not math.isfinite(reported_age) or reported_age < 0 or not raw_date:
        return False
    try:
        observed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError:
        try:
            observed = datetime.strptime(raw_date, "%Y-%m-%d")
        except ValueError:
            return False
    current_date = (now or datetime.now(timezone.utc)).date()
    observed_date = observed.date()
    actual_age = (current_date - observed_date).days
    return actual_age >= 0 and abs(actual_age - reported_age) <= 1


def _autoreply_canary_policy(source):
    source = source if isinstance(source, Mapping) else {}
    return {
        "enabled": _truthy(source.get(AUTOREPLY_CANARY_ENABLED_ENV)),
        "conversation_configured": bool(_clean(source.get(AUTOREPLY_CANARY_CONVERSATION_ENV), 100)),
        "contact_configured": bool(_clean(source.get(AUTOREPLY_CANARY_CONTACT_ENV), 100)),
        "inbox_configured": bool(_clean(source.get(AUTOREPLY_CANARY_INBOX_ENV), 100)),
        "requires_all_three_exact_identity_matches": True,
        "requires_persistent_idempotency_claim": True,
        "minimum_llm_confidence": 0.96,
        "minimum_lane_confidence": 0.90,
        "contains_identity_values": False,
        "kill_switch": AUTOREPLY_ENABLED_ENV,
    }


def _auto_general_canary_policy(source):
    source = source if isinstance(source, Mapping) else {}
    return {
        "enabled": _truthy(source.get(AUTO_GENERAL_CANARY_ENABLED_ENV)),
        "global_enabled": _truthy(source.get(AUTO_GENERAL_AUTOREPLY_ENABLED_ENV)),
        "conversation_configured": bool(_clean(source.get(AUTO_GENERAL_CANARY_CONVERSATION_ENV), 100)),
        "contact_configured": bool(_clean(source.get(AUTO_GENERAL_CANARY_CONTACT_ENV), 100)),
        "inbox_configured": bool(_clean(source.get(AUTO_GENERAL_CANARY_INBOX_ENV), 100)),
        "requires_all_three_exact_identity_matches": True,
        "requires_reviewed_llm_result": True,
        "requires_persistent_idempotency_claim_before_send": True,
        "delivery_states": [
            "prepared",
            "attempt_claimed",
            "chatwoot_accepted_unverified",
            "provider_delivered",
            "provider_read",
            "provider_failed",
            "provider_outcome_ambiguous",
        ],
        "confirmed_delivery_states": ["provider_delivered", "provider_read"],
        "specialist_and_protected_actions_disabled": True,
        "telegram_exception_only": True,
        "contains_identity_values": False,
        "kill_switch": AUTO_GENERAL_AUTOREPLY_ENABLED_ENV,
    }


def _auto_general_canary_evaluation(inbound, decision, review, source):
    source = source if isinstance(source, Mapping) else {}
    inbound = inbound if isinstance(inbound, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    review = review if isinstance(review, dict) else {}
    llm = decision.get("llm_draft") if isinstance(decision.get("llm_draft"), dict) else {}
    expected = {
        "conversation": _clean(source.get(AUTO_GENERAL_CANARY_CONVERSATION_ENV), 100),
        "contact": _clean(source.get(AUTO_GENERAL_CANARY_CONTACT_ENV), 100),
        "inbox": _clean(source.get(AUTO_GENERAL_CANARY_INBOX_ENV), 100),
    }
    actual = {
        "conversation": _clean(inbound.get("conversation_id"), 100),
        "contact": _clean(inbound.get("contact_id"), 100),
        "inbox": _clean(inbound.get("inbox_id"), 100),
    }
    identity_provenance = (
        inbound.get("identity_provenance")
        if isinstance(inbound.get("identity_provenance"), dict)
        else {}
    )
    identity_status = _clean(identity_provenance.get("status"), 80)
    configured = all(expected.values())
    identity_matches = configured and all(actual[key] == expected[key] for key in expected)
    response_class = _auto_general_low_risk_response_class(inbound, decision)
    claim_free_reply = not _auto_general_reply_has_factual_or_commercial_claim(
        decision.get("suggested_reply_text")
    )
    low_risk_threshold_allowed = (
        response_class in {"greeting", "acknowledgement", "clarification"}
        and claim_free_reply
    )
    minimum_llm_confidence = 0.95 if low_risk_threshold_allowed else 0.96
    protected_keys = (
        "creates_order",
        "creates_quote",
        "reserves_stock",
        "changes_stock",
        "writes_farm_data",
        "confirms_payment",
        "assigns_animal",
        "writes_order_intake",
        "writes_sales_transaction",
    )
    checks = {
        "global_auto_general_enabled": _truthy(source.get(AUTO_GENERAL_AUTOREPLY_ENABLED_ENV)),
        "canary_enabled": _truthy(source.get(AUTO_GENERAL_CANARY_ENABLED_ENV)),
        "all_identities_configured": configured,
        "identity_evidence_available": identity_status not in {"identity_evidence_unavailable", ""},
        "identity_evidence_conflict_absent": identity_status != "identity_conflict",
        "conversation_matches": bool(expected["conversation"] and actual["conversation"] == expected["conversation"]),
        "contact_matches": bool(expected["contact"] and actual["contact"] == expected["contact"]),
        "inbox_matches": bool(expected["inbox"] and actual["inbox"] == expected["inbox"]),
        "auto_general_state": decision.get("conversation_ownership") == AUTO_GENERAL,
        "review_safe": review.get("safe_to_send") is True and not review.get("escalation_required"),
        "reviewed_llm_draft": bool(
            (
                llm.get("used") is True
                and decision.get("reply_source")
                == "llm_auto_general_reply_draft"
            )
            or (
                decision.get("reply_source")
                == "canonical_customer_front_door"
                and decision.get("canonical_composition_authorized") is True
                and (decision.get("customer_front_door") or {}).get(
                    "valid_for_idempotency"
                ) is True
            )
        ),
        "low_risk_response_class": low_risk_threshold_allowed,
        "claim_free_reply": claim_free_reply,
        "llm_confident": bool(
            decision.get("reply_source") == "canonical_customer_front_door"
            or _confidence_at_least(
                llm.get("confidence"), minimum_llm_confidence
            )
        ),
        "low_risk_general_reply": not decision.get("specialist_lane_selected") and not decision.get("owner_escalation_required"),
        "specialist_tools_absent": not list(decision.get("specialist_tools_called") or []),
        "protected_mutation_absent": not any(decision.get(key) is True for key in protected_keys),
        "hostile_content_absent": not _hostile_or_scam_signal(inbound.get("content")),
    }
    authority = {
        "status": "response_class_authority_controller_disabled",
        "allowed": True,
        "blockers": [],
    }
    if _truthy(source.get("SAM_RESPONSE_CLASS_AUTHORITY_CONTROLLER_ENABLED")):
        from modules.sales.sam_response_class_authority import (
            list_latest_authority_events,
            resolve_runtime_authority,
        )
        authority = resolve_runtime_authority(
            response_class,
            current_message_class=response_class,
            delivery_rail_available=True,
            event_loader=list_latest_authority_events,
            environ=source,
        )
        checks["persistent_response_class_authority"] = authority.get("allowed") is True
    allowed = identity_matches and all(checks.values())
    if not checks["global_auto_general_enabled"]:
        status = "auto_general_reply_disabled"
    elif not checks["canary_enabled"]:
        status = "auto_general_canary_disabled"
    elif not configured:
        status = "auto_general_canary_identity_not_configured"
    elif not checks["identity_evidence_conflict_absent"]:
        status = "auto_general_canary_identity_conflict"
    elif not checks["identity_evidence_available"]:
        status = "auto_general_canary_identity_evidence_unavailable"
    elif not identity_matches:
        status = "auto_general_canary_identity_mismatch"
    elif not checks["auto_general_state"]:
        status = "auto_general_canary_wrong_ownership"
    elif not checks["reviewed_llm_draft"]:
        status = "auto_general_canary_requires_reviewed_llm"
    elif not checks["claim_free_reply"]:
        status = "auto_general_canary_factual_claim_blocked"
    elif not checks["llm_confident"]:
        status = "auto_general_canary_llm_confidence_blocked"
    elif not checks["review_safe"]:
        status = "auto_general_canary_review_blocked"
    elif not checks["low_risk_general_reply"]:
        status = "auto_general_canary_risk_blocked"
    elif not checks["specialist_tools_absent"]:
        status = "auto_general_canary_specialist_tool_blocked"
    elif not checks["protected_mutation_absent"]:
        status = "auto_general_canary_protected_action_blocked"
    elif not checks["hostile_content_absent"]:
        status = "auto_general_canary_hostile_content_blocked"
    elif checks.get("persistent_response_class_authority") is False:
        status = "auto_general_response_class_authority_blocked"
    else:
        status = "auto_general_canary_eligible"
    return {
        "allowed": allowed,
        "status": status,
        "checks": checks,
        "response_class": response_class,
        "minimum_llm_confidence": minimum_llm_confidence,
        "response_class_authority": {
            "status": authority.get("status"),
            "authority_event_id": authority.get("authority_event_id", ""),
            "blockers": list(authority.get("blockers") or []),
        },
        "contains_identity_values": False,
        "contains_secret_values": False,
    }


def _auto_general_low_risk_response_class(inbound, decision):
    inbound = inbound if isinstance(inbound, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    text = _normal_text(inbound.get("content"))
    reply = _clean_multiline(decision.get("suggested_reply_text"), 1800)
    if not reply or decision.get("conversation_ownership") != AUTO_GENERAL:
        return "other"
    if _general_greeting_only(text):
        return "greeting"
    if _general_acknowledgement_only(text):
        return "acknowledgement"
    if (
        decision.get("clarification_asked") is True
        and reply.count("?") == 1
        and decision.get("specialist_lane_selected") is not True
    ):
        return "clarification"
    return "other"


def _general_acknowledgement_only(text):
    return bool(re.fullmatch(
        r"(thanks|thank you|thanks so much|okay|ok|got it|cool|great|perfect|"
        r"dankie|reg so|goed)[!. ]*",
        text or "",
    ))


def _auto_general_reply_has_factual_or_commercial_claim(reply):
    text = _normal_text(reply)
    if not text:
        return True
    if re.search(r"\bR\s?\d|\b\d+(?:[.,]\d+)?\s?(?:kg|g|km|days?|weeks?|months?|years?)\b", text, re.IGNORECASE):
        return True
    if re.search(
        r"\b(?:piglets?|pigs?|stock)\s+(?:are|is)\s+"
        r"(?:on hand|ready|available)\b|"
        r"\b(?:on hand|in stock|ready to go)\b|"
        r"\b(?:ready|available)\s+for\s+(?:collection|pickup|delivery)\b|"
        r"\byou\s+can\s+(?:collect|pick\s*up)\b|"
        r"\b(?:collect|pick\s*up)\s+from\b|"
        r"\b(?:we|we're|we are|our farm is)\s+"
        r"(?:based|located)\s+(?:in|near|at)\b|"
        r"\b(?:we|we can|we're able to)\s+"
        r"(?:arrange|offer|provide)\s+(?:transport|delivery)\b|"
        r"\btransport\s+(?:is\s+)?available\b",
        text,
        re.IGNORECASE,
    ):
        return True
    prohibited = (
        "available",
        "availability",
        "in stock",
        "out of stock",
        "price",
        "cost",
        "discount",
        "reserve",
        "reserved",
        "order",
        "quote",
        "payment",
        "paid",
        "bank",
        "collect at",
        "located at",
        "our location is",
        "farm is at",
        "we have",
        "we sell",
        "we deliver",
        "we can deliver",
        "weighs",
        "weight is",
        "performance",
        "growth rate",
        "daily gain",
        "healthy",
        "vaccinated",
        "age is",
        "your order",
        "your payment",
        "you paid",
        "you requested",
    )
    if any(phrase in text for phrase in prohibited):
        return True
    animal_terms = (
        "piglet",
        "piglets",
        "pig",
        "pigs",
        "weaner",
        "weaners",
        "grower",
        "growers",
        "boar",
        "boars",
        "sow",
        "sows",
        "animal",
        "animals",
        "carcass",
        "meat",
    )
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", str(reply or "")) if item.strip()]
    return any(
        any(re.search(rf"\b{re.escape(term)}\b", _normal_text(sentence)) for term in animal_terms)
        and not sentence.rstrip().endswith("?")
        for sentence in sentences
    )


def _autoreply_canary_evaluation(inbound, decision, review, source):
    source = source if isinstance(source, Mapping) else {}
    inbound = inbound if isinstance(inbound, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    review = review if isinstance(review, dict) else {}
    facts = decision.get("facts") if isinstance(decision.get("facts"), dict) else {}
    llm = decision.get("llm_draft") if isinstance(decision.get("llm_draft"), dict) else {}
    expected = {
        "conversation": _clean(source.get(AUTOREPLY_CANARY_CONVERSATION_ENV), 100),
        "contact": _clean(source.get(AUTOREPLY_CANARY_CONTACT_ENV), 100),
        "inbox": _clean(source.get(AUTOREPLY_CANARY_INBOX_ENV), 100),
    }
    actual = {
        "conversation": _clean(inbound.get("conversation_id"), 100),
        "contact": _clean(inbound.get("contact_id"), 100),
        "inbox": _clean(inbound.get("inbox_id"), 100),
    }
    configured = all(expected.values())
    identity_matches = configured and all(actual[key] == expected[key] for key in expected)
    llm_confident = _confidence_at_least(llm.get("confidence"), 0.96)
    lane_confident = _confidence_at_least(facts.get("lane_confidence"), 0.90)
    checks = {
        "global_autoreply_enabled": _truthy(source.get(AUTOREPLY_ENABLED_ENV)),
        "canary_enabled": _truthy(source.get(AUTOREPLY_CANARY_ENABLED_ENV)),
        "all_identities_configured": configured,
        "conversation_matches": bool(expected["conversation"] and actual["conversation"] == expected["conversation"]),
        "contact_matches": bool(expected["contact"] and actual["contact"] == expected["contact"]),
        "inbox_matches": bool(expected["inbox"] and actual["inbox"] == expected["inbox"]),
        "review_safe": review.get("safe_to_send") is True and not review.get("escalation_required"),
        "reviewed_llm_draft": llm.get("used") is True and str(decision.get("reply_source") or "").startswith("llm_"),
        "llm_confident": llm_confident,
        "lane_confident": lane_confident,
        "intent_unambiguous": str(facts.get("message_intent") or "").lower() not in {"", "empty", "unclear"},
        "media_review_not_required": facts.get("media_review_required") is not True,
        "live_stock_lane": facts.get("sales_lane") == LANE_LIVE_STOCK and decision.get("sales_lane", LANE_LIVE_STOCK) == LANE_LIVE_STOCK,
        "hostile_content_absent": not _hostile_or_scam_signal(inbound.get("content")),
        "protected_mutation_absent": not any(decision.get(key) is True for key in ("creates_order", "creates_quote", "reserves_stock", "changes_stock", "writes_farm_data", "confirms_payment", "assigns_animal")),
    }
    allowed = identity_matches and all(checks.values())
    if not checks["global_autoreply_enabled"]:
        status = "routine_reply_disabled"
    elif not checks["canary_enabled"]:
        status = "routine_reply_canary_disabled"
    elif not configured:
        status = "routine_reply_canary_identity_not_configured"
    elif not identity_matches:
        status = "routine_reply_canary_identity_mismatch"
    elif not checks["reviewed_llm_draft"]:
        status = "routine_reply_requires_llm_draft"
    elif not checks["review_safe"]:
        status = "routine_reply_review_blocked"
    elif not llm_confident:
        status = "routine_reply_llm_confidence_blocked"
    elif not lane_confident:
        status = "routine_reply_lane_confidence_blocked"
    elif not checks["intent_unambiguous"]:
        status = "routine_reply_ambiguous_intent_blocked"
    elif not checks["media_review_not_required"]:
        status = "routine_reply_media_review_blocked"
    elif not checks["live_stock_lane"]:
        status = "routine_reply_wrong_lane_blocked"
    elif not checks["hostile_content_absent"]:
        status = "routine_reply_hostile_content_blocked"
    elif not checks["protected_mutation_absent"]:
        status = "routine_reply_protected_mutation_blocked"
    else:
        status = "routine_reply_canary_eligible"
    return {"allowed": allowed, "status": status, "checks": checks, "contains_identity_values": False, "contains_secret_values": False}


def _confidence_at_least(value, minimum):
    try:
        return float(value) >= float(minimum)
    except (TypeError, ValueError):
        return False


def _availability_rank_key(row, requested_midpoint=None):
    try:
        weight = float(row.get("current_weight_kg"))
    except (TypeError, ValueError):
        weight = None
    distance = abs(weight - requested_midpoint) if weight is not None and requested_midpoint is not None else 9999
    try:
        age = float(row.get("days_since_weight"))
    except (TypeError, ValueError):
        age = 9999
    return (distance, age, _clean(row.get("pig_id"), 80))


def _reply_exposes_internal_animal_evidence(reply, match_packet):
    text = str(reply or "").casefold()
    if not text:
        return False
    packet = match_packet if isinstance(match_packet, dict) else {}
    rows = []
    for key in ("matched_sample", "excluded_sample", "considered_sample"):
        rows.extend(packet.get(key) if isinstance(packet.get(key), list) else [])
    sensitive_keys = (
        "pig_id", "tag_number", "current_pen_id", "current_pen_name", "health_status",
        "medical_status", "current_withdrawal_end_date", "reserved_for_order_id",
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in sensitive_keys:
            value = str(row.get(key) or "").strip()
            if len(value) >= 3 and value.casefold() in text:
                return True
    return False


def _availability_exclusion_reasons(row, category, sex, requested_weight_range):
    reasons = []
    if not _row_available_for_live_stock(row):
        reasons.append(_clean(row.get("live_stock_sale_reason") or row.get("sales_notes") or "not currently sale eligible", 300))
        return reasons
    category_tokens = _row_category_tokens(row)
    if category and (not category_tokens or category not in category_tokens):
        reasons.append(f"category_mismatch:{category}")
    row_sex = _normal_sex(row.get("sex"))
    if sex and sex != "any" and sex != row_sex:
        reasons.append(f"sex_mismatch:{sex}")
    if requested_weight_range and not _row_matches_requested_weight(row, requested_weight_range):
        reasons.append(f"weight_mismatch:{_clean(requested_weight_range, 80)}")
    return reasons


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


def _authority_flags(
    writes_order_intake=False,
    creates_order=False,
    sends_customer_message=False,
    calls_chatwoot=False,
):
    return {
        "sends_customer_message": bool(sends_customer_message),
        "calls_chatwoot": bool(calls_chatwoot),
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": bool(creates_order),
        "reserves_stock": False,
        "changes_stock": False,
        "writes_farm_data": False,
        "writes_order_intake": bool(writes_order_intake),
        "writes_sales_transaction": False,
        "dispatch_enabled": bool(sends_customer_message),
        "customer_public_output_enabled": bool(sends_customer_message),
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
    }.get(sex, "")


def _normal_intake_location(value):
    text = _normal_text(value)
    if text == "riversdale":
        return "Riversdale"
    if text == "albertinia":
        return "Albertinia"
    return ""


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
    # Category-derived defaults are not customer-supplied weight evidence.
    return ""


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
        "afslag",
        "best price",
        "better price",
        "better deal",
        "can you do better",
        "could you do better",
        "lower price",
        "lowest price",
        "special price",
        "beter prys",
        "beter aanbod",
        "kan jy beter doen",
        "kan julle beter doen",
        "laer prys",
        "laagste prys",
        "goedkoper maak",
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


def _conversation_review_action(text, missing, escalation_reasons, blocked, reply, protected_action_reasons=None):
    if _natural_close_signal(text):
        return "no_reply_natural_close"
    if escalation_reasons or blocked:
        return "owner_handoff"
    if protected_action_reasons:
        return "owner_authority_decision"
    if missing:
        return "ask_one_missing_fact"
    if reply:
        return "send_routine_reply"
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


def _send_chatwoot_message(conversation_id, message, source, amadeus_source="sam_live_stock_owner_approved_send"):
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
    marker = _clean(amadeus_source, 80) or "sam_live_stock_owner_approved_send"
    body = {
        "content": message,
        "message_type": "outgoing",
        "private": False,
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
