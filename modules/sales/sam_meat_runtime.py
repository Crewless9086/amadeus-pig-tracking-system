import hashlib
import hmac
import json
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.sales_campaign_store import (
    get_active_sales_lead_by_conversation,
    get_sales_lead_preorder_contract,
    record_customer_booking_confirmation,
    record_sales_lead_event,
    record_sam_meat_intake_lead,
    _send_chatwoot_message,
)
from modules.sales.meat_ops import get_meat_ops_status, record_meat_deposit_event
from modules.sales.meat_documents import (
    BANK_ACCOUNT_NAME_ENV,
    BANK_ACCOUNT_NUMBER_ENV,
    BANK_ACCOUNT_TYPE_ENV,
    BANK_BRANCH_CODE_ENV,
    BANK_NAME_ENV,
    DOCUMENT_AUTOSEND_ENABLED_ENV,
    LEGACY_BANK_ACCOUNT_NAME_ENV,
    LEGACY_BANK_ACCOUNT_NUMBER_ENV,
    LEGACY_BANK_ACCOUNT_TYPE_ENV,
    LEGACY_BANK_BRANCH_CODE_ENV,
    LEGACY_BANK_NAME_ENV,
    bank_details as _shared_bank_details,
    build_meat_estimated_quote_packet,
    payment_reference as _shared_payment_reference,
    send_meat_estimated_quote_to_chatwoot,
)
from modules.sales.meat_fulfillment import record_meat_fulfillment_event
from modules.sales.chatwoot_hygiene import (
    HYGIENE_ENABLED_ENV,
    sync_sam_meat_chatwoot_hygiene,
)
from modules.sales.conversation_learning import record_learning_event_from_sam_result
from modules.sales.sam_farm_knowledge import (
    load_sam_farm_knowledge,
    meat_sales_knowledge,
    product_menu_text,
    public_profile,
)


WEBHOOK_ENABLED_ENV = "SAM_MEAT_BACKEND_WEBHOOK_ENABLED"
WEBHOOK_TOKEN_ENV = "SAM_MEAT_BACKEND_WEBHOOK_TOKEN"
AUTOREPLY_ENABLED_ENV = "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED"
LLM_ENABLED_ENV = "SAM_MEAT_BACKEND_LLM_ENABLED"
AGENT_V2_ENABLED_ENV = "SAM_MEAT_BACKEND_AGENT_V2_ENABLED"
LLM_MODEL_ENV = "SAM_MEAT_BACKEND_LLM_MODEL"
LLM_URL_ENV = "SAM_MEAT_BACKEND_LLM_URL"
LLM_TIMEOUT_ENV = "SAM_MEAT_BACKEND_LLM_TIMEOUT_SECONDS"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_LLM_URL = "https://api.openai.com/v1/chat/completions"
MIN_TOKEN_CHARS = 32
CUT_SET_MENU = {
    "Set A": "Family Freezer Pack: pork chops, leg portions or roasts, shoulder roasts, belly strips, ribs, mince or stew meat, and bones for soup or stock.",
    "Set B": "Braai Pack: chops, rashers or belly strips, ribs, shoulder steaks, sosatie or stew cubes, and mince or sausage meat option.",
    "Set C": "Lean Pack: lean chops, leg steaks, lean shoulder cuts, mince, stew cubes, and fewer fatty belly cuts.",
    "Set D": "Budget Bulk Pack: larger roasting cuts, mince, stew meat, soup bones, shoulder, mixed chops, and less detailed trimming.",
}


def sam_meat_webhook_policy(environ=None):
    source = environ if environ is not None else os.environ
    enabled = _truthy(source.get(WEBHOOK_ENABLED_ENV))
    token = str(source.get(WEBHOOK_TOKEN_ENV, "") or "").strip()
    autoreply_enabled = _truthy(source.get(AUTOREPLY_ENABLED_ENV))
    llm_enabled = _truthy(source.get(LLM_ENABLED_ENV))
    agent_v2_enabled = _truthy(source.get(AGENT_V2_ENABLED_ENV))
    hygiene_enabled = _truthy(source.get(HYGIENE_ENABLED_ENV))
    llm_configured = bool(str(source.get(LLM_MODEL_ENV, "") or "").strip() and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip())
    return {
        "enabled": enabled,
        "token_configured": len(token) >= MIN_TOKEN_CHARS,
        "autoreply_enabled": autoreply_enabled,
        "chatwoot_hygiene_enabled": hygiene_enabled,
        "llm_enabled": llm_enabled and llm_configured,
        "agent_v2_enabled": agent_v2_enabled and llm_configured,
        "agent_v2_explicitly_enabled": agent_v2_enabled,
        "llm_explicitly_enabled": llm_enabled,
        "llm_configured": llm_configured,
        "enabled_env": WEBHOOK_ENABLED_ENV,
        "token_env": WEBHOOK_TOKEN_ENV,
        "autoreply_env": AUTOREPLY_ENABLED_ENV,
        "chatwoot_hygiene_env": HYGIENE_ENABLED_ENV,
        "llm_enabled_env": LLM_ENABLED_ENV,
        "agent_v2_enabled_env": AGENT_V2_ENABLED_ENV,
        "llm_model_env": LLM_MODEL_ENV,
        "api_key_env": OPENAI_API_KEY_ENV,
        "bank_details_configured": _bank_details_configured(source),
        "bank_detail_envs": [
            BANK_ACCOUNT_NAME_ENV,
            BANK_NAME_ENV,
            BANK_ACCOUNT_NUMBER_ENV,
            BANK_BRANCH_CODE_ENV,
            BANK_ACCOUNT_TYPE_ENV,
            LEGACY_BANK_ACCOUNT_NAME_ENV,
            LEGACY_BANK_NAME_ENV,
            LEGACY_BANK_ACCOUNT_NUMBER_ENV,
            LEGACY_BANK_BRANCH_CODE_ENV,
            LEGACY_BANK_ACCOUNT_TYPE_ENV,
        ],
        "mode": "backend_native_sam_meat_chatwoot",
    }


def authorize_sam_meat_webhook(headers, query_args=None, environ=None):
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(WEBHOOK_ENABLED_ENV)):
        return False, _denied("sam_meat_backend_webhook_disabled")
    expected = str(source.get(WEBHOOK_TOKEN_ENV, "") or "").strip()
    if not expected:
        return False, _denied("sam_meat_backend_webhook_token_not_configured")
    if len(expected) < MIN_TOKEN_CHARS:
        return False, _denied("sam_meat_backend_webhook_token_too_short")
    if not _token_matches(headers or {}, query_args or {}, expected):
        return False, _denied("sam_meat_backend_webhook_auth_denied")
    return True, {}


def handle_sam_meat_chatwoot_inbound(
    payload,
    *,
    environ=None,
    chatwoot_sender=None,
    document_sender=None,
    llm_extractor=None,
    llm_agent_decider=None,
):
    source = environ if environ is not None else os.environ
    inbound = parse_chatwoot_inbound(payload)
    if not inbound["processable"]:
        return {
            "success": True,
            "status": inbound["status"],
            "processed": False,
            "sent": False,
            "sam_decision": {},
            "policy": sam_meat_webhook_policy(source),
            **_authority_flags(False, False),
        }, 200

    facts = extract_meat_facts(inbound["content"], inbound, environ=source, llm_extractor=llm_extractor)
    prior_context = _conversation_lead_context(inbound.get("conversation_id"))
    facts = _merge_prior_context(facts, prior_context)
    agent_decision = _build_agent_v2_decision_if_enabled(
        inbound,
        facts,
        prior_context,
        source,
        decider=llm_agent_decider,
    )
    if agent_decision.get("used"):
        facts = _merge_agent_fact_patch(facts, agent_decision)
    lead_payload = build_sam_meat_lead_payload_from_inbound(inbound, facts)
    if prior_context.get("lead_id"):
        lead_payload["lead_id"] = prior_context["lead_id"]
    else:
        lead_payload["lead_id"] = _fresh_lead_id(inbound, facts)
    record_result, record_status = record_sam_meat_intake_lead(lead_payload)
    booking_confirmation = _record_booking_confirmation_if_ready(inbound, prior_context)
    decision = build_sam_meat_decision(
        inbound,
        facts,
        record_result,
        record_status,
        environ=source,
        prior_context=prior_context,
        agent_decision=agent_decision,
    )
    if booking_confirmation.get("recorded"):
        deposit_instruction = _build_deposit_instruction_if_ready(booking_confirmation.get("lead_id"), source)
        if deposit_instruction.get("ready"):
            decision["reply_text"] = deposit_instruction["message"]
            decision["deposit_payment_instruction"] = deposit_instruction
            decision["blocked_actions"] = [
                item for item in decision.get("blocked_actions", [])
                if item != "no_deposit_request"
            ]
        else:
            decision["reply_text"] = (
                "Thanks, I have noted your confirmation for final booking review. "
                "The farm will prepare the next booking step."
            )
            decision["deposit_payment_instruction"] = deposit_instruction
    pop_capture = _record_pop_if_ready(inbound, prior_context, source)
    if pop_capture.get("recorded") or pop_capture.get("detected"):
        decision["reply_text"] = (
            "Thanks, I have received the payment proof. "
            "The booking only moves forward once the money reflects in the farm account."
        )
        decision["pop_capture"] = pop_capture
    fulfillment_capture = _record_delivery_address_if_ready(decision.get("lead_id"), inbound, facts)
    chatwoot_hygiene = sync_sam_meat_chatwoot_hygiene(
        inbound.get("conversation_id"),
        lead_payload=lead_payload,
        facts=facts,
        inbound=inbound,
        decision=decision,
        prior_context=prior_context,
        booking_confirmation=booking_confirmation,
        pop_capture=pop_capture,
        environ=source,
    )

    send_result = {}
    document_send_result = {}
    sent = False
    document_sent = False
    send_status = "autoreply_not_enabled"
    document_send_status = "not_requested"
    if decision["should_reply"] and _truthy(source.get(AUTOREPLY_ENABLED_ENV)):
        if inbound["whatsapp_window_state"] != "open":
            send_status = "whatsapp_window_not_open"
            document_send_status = "whatsapp_window_not_open"
        else:
            sender = chatwoot_sender or _send_chatwoot_message
            _record_autoreply_event(decision.get("lead_id"), "sam_meat_autoreply_attempted", decision["reply_text"], {
                "conversation_id": inbound["conversation_id"],
            })
            try:
                send_result = sender(inbound["conversation_id"], decision["reply_text"])
                sent = True
                send_status = "sent"
                _record_autoreply_event(decision.get("lead_id"), "sam_meat_autoreply_sent", decision["reply_text"], send_result)
                if decision.get("document_send_requested"):
                    try:
                        document_payload = {"conversation_id": inbound["conversation_id"]}
                        if decision.get("document_force_resend_requested"):
                            document_payload["force_resend"] = True
                        document_send_result, document_status_code = send_meat_estimated_quote_to_chatwoot(
                            decision.get("lead_id"),
                            document_payload,
                            environ=source,
                            chatwoot_sender=document_sender,
                        )
                        document_sent = bool(document_send_result.get("sent"))
                        document_send_status = document_send_result.get("status") or f"status_{document_status_code}"
                    except Exception as exc:
                        document_send_result = {"error_type": exc.__class__.__name__, "error": str(exc)[:180]}
                        document_send_status = "document_send_failed"
            except Exception as exc:
                send_result = {"error_type": exc.__class__.__name__, "error": str(exc)[:180]}
                send_status = "chatwoot_send_failed"
                document_send_status = "skipped_autoreply_failed"
                _record_autoreply_event(decision.get("lead_id"), "sam_meat_autoreply_failed", decision["reply_text"], send_result)

    status_code = 200 if record_status in {200, 201, 400} else record_status
    result = {
        "success": record_status in {200, 201, 400},
        "status": "processed",
        "processed": True,
        "inbound": inbound,
        "facts": facts,
        "agent_decision": agent_decision,
        "prior_context": prior_context,
        "lead_payload": lead_payload,
        "lead_result": record_result,
        "lead_status_code": record_status,
        "booking_confirmation": booking_confirmation,
        "pop_capture": pop_capture,
        "fulfillment_capture": fulfillment_capture,
        "chatwoot_hygiene": chatwoot_hygiene,
        "sam_decision": decision,
        "sent": sent,
        "send_status": send_status,
        "chatwoot_send": send_result,
        "document_sent": document_sent,
        "document_send_status": document_send_status,
        "document_send": document_send_result,
        "policy": sam_meat_webhook_policy(source),
        **_authority_flags(sent or document_sent, sent or document_sent),
    }
    learning_result, learning_status = record_learning_event_from_sam_result(result)
    result["conversation_learning"] = {
        "status_code": learning_status,
        "status": learning_result.get("status"),
        "success": learning_result.get("success") is True,
        "learning_event_id": learning_result.get("learning_event_id", ""),
        "next_gate": learning_result.get("next_gate", ""),
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
    }
    return result, status_code


def parse_chatwoot_inbound(payload):
    payload = payload if isinstance(payload, dict) else {}
    message_type = _normal_chatwoot_message_type(payload)
    event = _clean(payload.get("event"), 80).lower()
    content = _clean(payload.get("content") or payload.get("message") or payload.get("text"), 1800)
    shared_location = _extract_shared_location(payload)
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
    custom_attributes = conversation.get("custom_attributes") if isinstance(conversation.get("custom_attributes"), dict) else {}
    explicit_window_state = _normal_whatsapp_window_state(
        payload.get("whatsapp_window_state")
        or payload.get("service_window_state")
        or payload.get("conversation_window_state")
        or custom_attributes.get("whatsapp_window_state")
    )
    if not content and shared_location.get("summary"):
        content = shared_location["summary"]
    if not content:
        return _ignored("ignored_empty_message", event, message_type, content, conversation_id, customer_name, channel)
    return {
        "processable": True,
        "status": "processable",
        "event": event or "message_created",
        "message_type": message_type or "incoming",
        "content": content,
        "shared_location": shared_location,
        "conversation_id": conversation_id,
        "contact_id": _clean(payload.get("contact_id") or sender.get("id") or contact.get("id"), 100),
        "account_id": _clean(payload.get("account_id") or account.get("id"), 100),
        "customer_name": customer_name or "Chatwoot customer",
        "customer_phone": _clean(sender.get("phone_number") or contact.get("phone_number"), 80),
        "channel": channel,
        "whatsapp_window_state": explicit_window_state or "open",
        "message_id": _clean(payload.get("id") or payload.get("message_id"), 100),
        "last_inbound_at": _clean(payload.get("created_at") or payload.get("timestamp"), 80),
    }


def extract_meat_facts(message, inbound=None, *, environ=None, llm_extractor=None):
    source = environ if environ is not None else os.environ
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = _deterministic_extract(message)
    facts["customer_name"] = inbound.get("customer_name") or ""
    facts["conversation_id"] = inbound.get("conversation_id") or ""
    facts["contact_id"] = inbound.get("contact_id") or ""
    facts["channel"] = inbound.get("channel") or "chatwoot_whatsapp"
    shared_location = inbound.get("shared_location") if isinstance(inbound.get("shared_location"), dict) else {}
    if shared_location:
        facts.update(_shared_location_fact_patch(shared_location, facts))
    facts["llm_used"] = False
    facts["llm_status"] = "not_enabled"

    llm_patch = {}
    if _truthy(source.get(LLM_ENABLED_ENV)):
        extractor = llm_extractor or _call_sam_meat_llm
        llm_patch = extractor(message, inbound, source) or {}
        if llm_patch:
            facts.update(_safe_llm_fact_patch(llm_patch))
            facts["llm_used"] = True
            facts["llm_status"] = "used"
        else:
            facts["llm_status"] = "fallback_deterministic"
    return _apply_meat_pilot_defaults(facts)


def build_sam_meat_lead_payload_from_inbound(inbound, facts):
    product_type = facts.get("product_type") or "unknown"
    product_label = {
        "half_carcass": "Half Carcass",
        "full_carcass": "Full Carcass",
        "custom_cut": "Custom Cut",
        "assisted_slaughter": "Assisted Slaughter",
    }.get(product_type, "")
    return {
        "customer_name": inbound.get("customer_name") or facts.get("customer_name") or "Chatwoot customer",
        "conversation_id": inbound.get("conversation_id") or facts.get("conversation_id"),
        "contact_id": inbound.get("contact_id") or facts.get("contact_id"),
        "channel": inbound.get("channel") or facts.get("channel") or "chatwoot_whatsapp",
        "whatsapp_window_state": inbound.get("whatsapp_window_state") or "open",
        "product": product_label,
        "product_type": product_type,
        "cut_set": facts.get("cut_set") or "",
        "location": facts.get("location") or "",
        "timing": facts.get("timing") or "",
        "delivery_or_collection": facts.get("delivery_or_collection") or "",
        "delivery_address_line_1": facts.get("delivery_address_line_1") or "",
        "delivery_town": facts.get("delivery_town") or facts.get("location") or "",
        "delivery_area": facts.get("delivery_area") or "",
        "delivery_notes": facts.get("delivery_notes") or "",
        "delivery_place_name": facts.get("delivery_place_name") or "",
        "delivery_location_latitude": facts.get("delivery_location_latitude") or "",
        "delivery_location_longitude": facts.get("delivery_location_longitude") or "",
        "delivery_maps_url": facts.get("delivery_maps_url") or "",
        "payment_method": facts.get("payment_method") or "",
        "budget_amount": facts.get("budget_amount") or "",
        "target_packed_kg": facts.get("target_packed_kg") or "",
        "match_preference": facts.get("match_preference") or "",
        "notes": inbound.get("content") or "",
        "status": "interested" if product_type != "unknown" else "new",
        "last_inbound_at": inbound.get("last_inbound_at") or "",
    }


def _fresh_lead_id(inbound, facts):
    seed = json.dumps(
        {
            "source": "sam_meat_backend_fresh_inbound",
            "conversation_id": inbound.get("conversation_id") or facts.get("conversation_id") or "",
            "contact_id": inbound.get("contact_id") or facts.get("contact_id") or "",
            "message_id": inbound.get("message_id") or "",
            "last_inbound_at": inbound.get("last_inbound_at") or "",
            "content": inbound.get("content") or "",
        },
        sort_keys=True,
        default=str,
    )
    return "OSK-SALES-LEAD-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()


def build_sam_meat_decision(inbound, facts, record_result, record_status, environ=None, prior_context=None, agent_decision=None):
    source = environ if environ is not None else os.environ
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    facts = _apply_meat_pilot_defaults(facts)
    knowledge_result = load_sam_farm_knowledge(source)
    knowledge = knowledge_result.get("knowledge") if isinstance(knowledge_result.get("knowledge"), dict) else {}
    reply = ""
    should_reply = True
    lead_id = _clean(record_result.get("lead_id") if isinstance(record_result, dict) else "", 100)
    document_send_requested = False
    document_force_resend_requested = False
    quote_or_document_requested = _asks_money_or_document(inbound.get("content"))
    vague_meat_interest_reply = _vague_meat_interest_reply(inbound.get("content"), facts, knowledge)
    non_pork_reply = _non_pork_guard_reply(inbound.get("content"))
    frustration_reply = _frustration_guard_reply(inbound.get("content"), facts, knowledge)
    cut_menu_reply = _cut_menu_reply(inbound.get("content"), facts)
    deposit_question_reply = _deposit_question_reply(inbound.get("content"), facts, knowledge)
    payment_state_reply = _payment_state_reply(inbound.get("content"), facts, prior_context, knowledge)
    price_or_document_reply = _price_or_document_guard_reply(inbound.get("content"), facts)
    agent_decision = agent_decision if isinstance(agent_decision, dict) else {}
    agent_reply = _validated_agent_reply(agent_decision)
    agent_wants_no_reply = agent_decision.get("used") and agent_decision.get("should_reply") is False
    if non_pork_reply:
        reply = non_pork_reply
        should_reply = True
    elif frustration_reply:
        reply = frustration_reply
        should_reply = True
    elif cut_menu_reply:
        reply = cut_menu_reply
        should_reply = True
    elif deposit_question_reply:
        reply = deposit_question_reply
        should_reply = True
    elif payment_state_reply:
        reply = payment_state_reply
        should_reply = True
    elif price_or_document_reply:
        reply = price_or_document_reply
        should_reply = True
    elif vague_meat_interest_reply:
        reply = vague_meat_interest_reply
        should_reply = True
    elif agent_wants_no_reply:
        reply = ""
        should_reply = False
    elif agent_reply:
        reply = agent_reply
        should_reply = True
    elif record_status == 400 and record_result.get("sam_next_question"):
        reply = record_result["sam_next_question"]
        should_reply = True
    elif facts.get("product_type") == "unknown":
        reply = _sam_intro_options_reply(knowledge)
    elif facts.get("product_type") in {"half_carcass", "full_carcass", "custom_cut"} and not facts.get("cut_set"):
        reply = "I can help with that. Which cut set would you prefer? Set A is the family freezer pack, or I can explain the available sets."
    elif not facts.get("location"):
        reply = "Which town or area would you prefer for collection or delivery? I use that to keep the farm run practical."
    elif not facts.get("delivery_or_collection"):
        reply = "Would you prefer collection or delivery? For meat orders we plan this carefully around the farm run."
    elif facts.get("delivery_or_collection") == "delivery" and not facts.get("delivery_address_line_1"):
        reply = "Please send the delivery street address or farm name, town, and any useful directions for the driver."
    elif not facts.get("timing"):
        reply = "When would you ideally like the pork: this week, next week, or the next available farm run?"
    elif facts.get("payment_method") == "Cash":
        rule = meat_sales_knowledge(knowledge).get("payment_rule") or meat_sales_knowledge(knowledge).get("pilot_payment_rule") or "For meat sales we use EFT only so the reference and payment trail stay clean."
        reply = f"{rule} EFT is the only payment option for now."
    elif not facts.get("payment_method"):
        rule = meat_sales_knowledge(knowledge).get("payment_rule") or meat_sales_knowledge(knowledge).get("pilot_payment_rule") or "For meat sales we use EFT only so the reference and payment trail stay clean."
        reply = f"{rule} Is EFT fine for the deposit and final balance?"
    else:
        reply = (
            "Thanks, I have noted your pork interest for the farm to review. "
            "This is pre-booked Amadeus Farm pork, so I still need the farm to confirm price, timing, and the deposit rule before quoting or booking anything."
        )

    if lead_id:
        contract, status_code = get_sales_lead_preorder_contract(lead_id)
        if status_code == 200:
            contract_body = contract.get("contract") if isinstance(contract.get("contract"), dict) else {}
            if contract_body.get("contract_status") == "owner_money_path_ready" or quote_or_document_requested:
                quote_packet, quote_status = build_meat_estimated_quote_packet(lead_id)
                if (
                    quote_status == 200
                    and quote_packet.get("quote_safe")
                    and _truthy(source.get(DOCUMENT_AUTOSEND_ENABLED_ENV))
                ):
                    reply = quote_packet.get("sam_preparing_message") or (
                        "I am preparing your estimated quote now and will send it through shortly."
                    )
                    document_send_requested = True
                    document_force_resend_requested = quote_or_document_requested
                elif quote_status == 200 and quote_packet.get("quote_safe"):
                    reply = (
                        "I have the details needed for your estimated quote. "
                        "The farm document send step is not enabled yet, so the team will send it once that is switched on."
                    )
                elif quote_or_document_requested:
                    blockers = quote_packet.get("blockers") if isinstance(quote_packet, dict) else []
                    blocker_text = _quote_blocker_reply(blockers)
                    reply = blocker_text or (
                        "I am not able to prepare the estimated quote yet because the farm document gate is incomplete."
                    )
                else:
                    reply = (
                        "I have your meat preorder details. I still need the farm document setup to be completed "
                        "before I can send the estimated quote."
                    )

    return {
        "agent": "sam_meat_backend",
        "decision": "reply" if should_reply else "no_reply",
        "should_reply": should_reply,
        "reply_text": reply,
        "lead_id": lead_id,
        "agent_v2": _agent_decision_summary(agent_decision),
        "document_send_requested": document_send_requested,
        "document_force_resend_requested": document_force_resend_requested,
        "records_tracking_lead": bool(lead_id),
        "blocked_actions": [
            "no_price_quote_without_owner_approval",
            "no_deposit_request",
            "no_order_creation",
            "no_stock_reservation",
            "no_stock_change",
        ],
    }


def _call_sam_meat_llm(message, inbound, source):
    if not (str(source.get(LLM_MODEL_ENV, "") or "").strip() and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip()):
        return {}
    payload = _llm_payload(message, inbound, source)
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
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError):
        return {}
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        return json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _llm_payload(message, inbound, source):
    system = (
        "You are Sam Meat's backend extractor. Return JSON facts only. "
        "Allowed keys: product_type, cut_set, location, timing, delivery_or_collection, "
        "delivery_address_line_1, delivery_town, delivery_area, delivery_notes, payment_method, "
        "budget_amount, target_packed_kg, match_preference. "
        "Allowed product_type: half_carcass, full_carcass, custom_cut, assisted_slaughter, unknown. "
        "Allowed match_preference: heaviest, soonest, cheapest, best_fit, closest_weight, budget_fit, or blank. "
        "Never include prices, deposit promises, order creation, stock reservation, or customer-send commands."
    )
    return {
        "model": str(source.get(LLM_MODEL_ENV, "") or "").strip(),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"message": str(message or "")[:1800], "inbound": inbound}, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }


def _build_agent_v2_decision_if_enabled(inbound, facts, prior_context, source, decider=None):
    if not _truthy(source.get(AGENT_V2_ENABLED_ENV)):
        return {"used": False, "status": "agent_v2_disabled"}
    if not (str(source.get(LLM_MODEL_ENV, "") or "").strip() and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip()):
        return {"used": False, "status": "agent_v2_not_configured"}
    caller = decider or _call_sam_meat_agent_llm
    raw = caller(inbound, facts, prior_context, source)
    if not isinstance(raw, dict) or not raw:
        return {"used": False, "status": "agent_v2_no_decision"}
    decision = _safe_sam_agent_decision(raw)
    decision["used"] = bool(decision.get("status") == "agent_v2_decision_accepted")
    return decision


def _call_sam_meat_agent_llm(inbound, facts, prior_context, source):
    payload = _agent_v2_payload(inbound, facts, prior_context, source)
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
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError):
        return {}
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        return json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _agent_v2_payload(inbound, facts, prior_context, source):
    knowledge_result = load_sam_farm_knowledge(source)
    knowledge = knowledge_result.get("knowledge") if isinstance(knowledge_result.get("knowledge"), dict) else {}
    system = (
        "You are Sam, the human-feeling sales agent for Amadeus Farm. "
        "You sell by listening first, keeping WhatsApp replies short, warm, practical, and clear. "
        "You may answer farm, pork, delivery, payment, and preorder questions, then gently steer back to the useful sales next step. "
        "If there is no clear customer intent or no useful next question, set should_reply false. "
        "Never assume uncertain facts; ask one natural confirmation question instead. "
        "Never use the word pilot. Never invent prices, stock, weights, availability, booking status, payment status, slaughter dates, butcher slots, or delivery dates. "
        "Only return JSON."
    )
    schema_note = {
        "required_json_shape": {
            "intent": "meat_preorder|live_sales|farm_info|payment|document_request|general|unknown",
            "should_reply": True,
            "reply_text": "short customer-facing WhatsApp reply",
            "facts_patch": {
                "product_type": "half_carcass|full_carcass|custom_cut|assisted_slaughter|unknown",
                "cut_set": "Set A|Set B|Set C|Set D",
                "location": "town or area",
                "timing": "this week|next week|next available farm run|customer wording",
                "delivery_or_collection": "delivery|collection",
                "delivery_address_line_1": "street address or farm name",
                "delivery_town": "town",
                "delivery_area": "area/suburb",
                "delivery_notes": "short driver notes",
                "payment_method": "EFT|Cash",
                "budget_amount": "number only",
                "target_packed_kg": "number only",
                "match_preference": "heaviest|soonest|cheapest|best_fit|closest_weight|budget_fit",
            },
            "missing_fields": ["field_name"],
            "confidence": 0.0,
            "requires_confirmation": False,
            "risk_flags": [],
        }
    }
    return {
        "model": str(source.get(LLM_MODEL_ENV, "") or "").strip(),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "customer_message": inbound.get("content") or "",
                        "current_known_facts": facts,
                        "prior_context": prior_context,
                        "farm_knowledge": knowledge,
                        "business_rules": {
                            "payment_rule": meat_sales_knowledge(knowledge).get("payment_rule")
                            or meat_sales_knowledge(knowledge).get("pilot_payment_rule")
                            or "For meat sales we use EFT only for now.",
                            "must_not_assume": True,
                            "ask_one_question_at_a_time": True,
                            "if_customer_asks_farm_info_answer_briefly_then_steer_to_sales": True,
                            "if_no_intent_do_not_force_reply": True,
                        },
                        **schema_note,
                    },
                    separators=(",", ":"),
                    ensure_ascii=True,
                )[:9000],
            },
        ],
        "response_format": {"type": "json_object"},
    }


def _safe_sam_agent_decision(raw):
    raw = raw if isinstance(raw, dict) else {}
    reply = _clean(raw.get("reply_text"), 1800)
    confidence = _normal_confidence(raw.get("confidence"))
    should_reply = raw.get("should_reply")
    should_reply = False if should_reply is False else bool(reply)
    risk_flags = [_clean(item, 80) for item in (raw.get("risk_flags") if isinstance(raw.get("risk_flags"), list) else [])]
    facts_patch = _safe_llm_fact_patch(raw.get("facts_patch") if isinstance(raw.get("facts_patch"), dict) else {})
    requires_confirmation = bool(raw.get("requires_confirmation"))
    if confidence < 0.70:
        facts_patch = {}
    if requires_confirmation and confidence < 0.85:
        facts_patch = {}
    intent = _clean(raw.get("intent"), 80)
    has_decision = bool(reply or facts_patch or (should_reply is False and intent and confidence >= 0.75))
    if not has_decision:
        return {
            "used": False,
            "status": "agent_v2_no_actionable_decision",
            "should_reply": False,
            "reply_text": "",
            "facts_patch": {},
            "confidence": confidence,
            "requires_confirmation": requires_confirmation,
            "risk_flags": risk_flags,
        }
    blocked = _agent_reply_blockers(reply)
    if blocked:
        return {
            "used": False,
            "status": "agent_v2_reply_blocked",
            "should_reply": True,
            "reply_text": "",
            "facts_patch": facts_patch,
            "confidence": confidence,
            "requires_confirmation": requires_confirmation,
            "risk_flags": [*risk_flags, *blocked],
        }
    return {
        "used": True,
        "status": "agent_v2_decision_accepted",
        "intent": intent,
        "should_reply": should_reply,
        "reply_text": reply,
        "facts_patch": facts_patch,
        "missing_fields": [_clean(item, 80) for item in (raw.get("missing_fields") if isinstance(raw.get("missing_fields"), list) else [])],
        "confidence": confidence,
        "requires_confirmation": requires_confirmation,
        "risk_flags": risk_flags,
    }


def _merge_agent_fact_patch(facts, agent_decision):
    facts = dict(facts or {})
    patch = agent_decision.get("facts_patch") if isinstance(agent_decision.get("facts_patch"), dict) else {}
    for key, value in patch.items():
        cleaned = _clean(value, 700)
        if cleaned:
            facts[key] = value
    return _apply_meat_pilot_defaults(facts)


def _validated_agent_reply(agent_decision):
    if not agent_decision.get("used"):
        return ""
    reply = _clean(agent_decision.get("reply_text"), 1800)
    if not reply or _agent_reply_blockers(reply):
        return ""
    return reply


def _agent_reply_blockers(reply):
    text = str(reply or "").lower()
    blockers = []
    if "pilot" in text:
        blockers.append("uses_pilot_word")
    unsafe_patterns = [
        (r"\br\s*\d", "mentions_money_amount"),
        (r"\b(booking|order|reservation)\b.{0,40}\b(confirmed|final|booked|reserved)\b", "confirms_booking_without_gate"),
        (r"\b(payment|money|deposit)\b.{0,40}\b(received|confirmed|cleared|reflects)\b", "confirms_payment_without_bank_gate"),
        (r"\b(slaughter|butcher|delivery|collection)\b.{0,40}\b(booked|confirmed|scheduled)\b", "confirms_fulfillment_without_gate"),
    ]
    for pattern, label in unsafe_patterns:
        if re.search(pattern, text):
            blockers.append(label)
    return blockers


def _agent_decision_summary(agent_decision):
    agent_decision = agent_decision if isinstance(agent_decision, dict) else {}
    return {
        "used": bool(agent_decision.get("used")),
        "status": _clean(agent_decision.get("status"), 120),
        "intent": _clean(agent_decision.get("intent"), 80),
        "confidence": agent_decision.get("confidence", 0),
        "requires_confirmation": bool(agent_decision.get("requires_confirmation")),
        "risk_flags": agent_decision.get("risk_flags") if isinstance(agent_decision.get("risk_flags"), list) else [],
    }


def _normal_confidence(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _record_autoreply_event(lead_id, event_type, message, extra=None):
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return
    notes = {
        "source": "backend_native_sam_meat",
        "kind": event_type,
        "message": _clean(message, 1200),
        **(extra if isinstance(extra, dict) else {}),
    }
    record_sales_lead_event(
        lead_id,
        {
            "event_type": event_type,
            "status_observed": "interested",
            "recorded_by": "backend_sam_meat",
            "notes": json.dumps(notes, ensure_ascii=True, sort_keys=True),
        },
    )


def _deterministic_extract(message):
    text = str(message or "")
    lower = text.lower()
    normalized = _normalized_customer_text(text)
    product_type = "unknown"
    if re.search(r"\bhalf\s+(?:pig\s+)?carcass|half\s+carcase|half\s+pork\b|\bhalf\s+pig\b", normalized):
        product_type = "half_carcass"
    elif re.search(r"\bfull\s+(?:pig\s+)?carcass|whole\s+(?:pig|carcass)\b", normalized):
        product_type = "full_carcass"
    elif re.search(r"\bcut|cuts|set\s+[abcd]\b", normalized):
        product_type = "custom_cut"
    elif "assisted slaughter" in normalized:
        product_type = "assisted_slaughter"

    cut_set = ""
    match = re.search(r"\bset\s*([abcd])\b", normalized)
    if match:
        cut_set = f"Set {match.group(1).upper()}"

    location = ""
    for place in ("Riversdale", "Albertinia"):
        if place.lower() in normalized:
            location = place
            break

    timing = ""
    if "next available farm run" in normalized:
        timing = "next available farm run"
    elif "next available week" in normalized:
        timing = "next available week"
    elif "next week" in normalized:
        timing = "next week"
    elif "this week" in normalized:
        timing = "this week"

    delivery_or_collection = ""
    if re.search(r"\bcollect|collection|pickup|pick up\b", normalized):
        delivery_or_collection = "collection"
    elif re.search(r"\bdeliver|delivery\b", normalized):
        delivery_or_collection = "delivery"

    payment_method = ""
    if re.search(r"\beft\b", normalized):
        payment_method = "EFT"
    elif re.search(r"\bcash\b", normalized):
        payment_method = "Cash"

    budget_amount = _budget_amount_from_text(text)
    target_packed_kg = _target_packed_kg_from_text(text)
    match_preference = _match_preference_from_text(text, budget_amount, target_packed_kg)

    delivery_address_line_1 = ""
    address_match = re.search(
        r"\b(?:address|deliver(?:y)?\s+(?:to|at))\s*(?:is|:|-)?\s*([^.,\n]+(?:\s+(?:street|straat|road|rd|avenue|ave|lane|ln|farm|plot|smallholding)\b[^.,\n]*)?)",
        text,
        re.I,
    )
    if address_match:
        delivery_address_line_1 = address_match.group(1).strip(" .,:;-")
    elif delivery_or_collection == "delivery":
        simple_address = re.search(r"\b(\d{1,5}\s+[A-Za-z][A-Za-z0-9 '\-]{2,80})", text)
        if simple_address:
            delivery_address_line_1 = simple_address.group(1).strip(" .,:;-")
    maps_location = _maps_location_from_text(text)
    if delivery_or_collection == "delivery" and not delivery_address_line_1 and maps_location:
        delivery_address_line_1 = maps_location.get("place_name") or "Shared Google Maps location"

    return {
        "product_type": product_type,
        "cut_set": cut_set,
        "location": location,
        "timing": timing,
        "delivery_or_collection": delivery_or_collection,
        "delivery_address_line_1": _clean(delivery_address_line_1, 240),
        "delivery_town": location or _town_from_text(maps_location.get("place_name", "")),
        "delivery_area": "",
        "delivery_notes": "",
        "delivery_place_name": maps_location.get("place_name", ""),
        "delivery_location_latitude": maps_location.get("latitude", ""),
        "delivery_location_longitude": maps_location.get("longitude", ""),
        "delivery_maps_url": maps_location.get("maps_url", ""),
        "payment_method": payment_method,
        "budget_amount": budget_amount,
        "target_packed_kg": target_packed_kg,
        "match_preference": match_preference,
    }


def _cut_menu_reply(message, facts):
    text = str(message or "").lower()
    asks_cut_menu = bool(re.search(r"\bwhat\b.*\b(set|cut|cuts)\b|\b(set|cut|cuts)\b.*\b(include|includes|mean|option|difference)\b|\bcut\s*menu\b", text))
    if not asks_cut_menu:
        return ""
    cut_set = facts.get("cut_set") or _mentioned_cut_set(text)
    if cut_set and cut_set in CUT_SET_MENU:
        return (
            f"{cut_set} is the {CUT_SET_MENU[cut_set]} "
            "I can note your preference, but the farm still needs to confirm price, timing, and any deposit rule before quoting or booking anything."
        )
    menu = " ".join(f"{key}: {description}" for key, description in CUT_SET_MENU.items())
    return (
        f"The current pork cut options are: {menu} "
        "I can note which one you prefer, but price, timing, and deposit still need farm approval before a quote or booking."
    )


def _sam_intro_options_reply(knowledge=None):
    profile = public_profile(knowledge or {})
    menu = product_menu_text(knowledge or {})
    intro = profile.get("short_intro") or "Hi, I am Sam from Amadeus Farm."
    story = profile.get("one_line_story") or "I can help you find the right farm sales path."
    if not menu:
        menu = "Pork meat sales, live pig sales, or farm information."
    return (
        f"{intro} {story} "
        f"I can help with {menu}. "
        "Tell me what you are looking for and I will guide you from there."
    )


def _vague_meat_interest_reply(message, facts, knowledge=None):
    if facts.get("product_type") != "unknown":
        return ""
    normalized = _normalized_customer_text(message)
    if not _meat_interest_detected(normalized):
        return ""
    if re.search(r"\bcarcass\b", normalized):
        return (
            "Yes, we can help with pork carcass orders. "
            "Are you thinking half carcass or full carcass?"
        )
    if re.search(r"\b(option|options|available|what.*have|what.*sell)\b", normalized):
        return (
            "Yes, we do pork for freezer orders. The usual starting points are a half carcass, "
            "a full carcass, or a cut-set pack like Set A. "
            "Are you looking for freezer stock, a half carcass, or a smaller cut set?"
        )
    if re.search(r"\bdo\s+you\s+sell\b|\bsell\s+meat\b", normalized):
        return (
            "Yes, we sell pork from planned farm runs. "
            "Would you like me to guide you through half carcass, full carcass, or cut-set options?"
        )
    if re.search(r"\b(i\s+want|i'?m\s+looking|looking\s+for|need)\b", normalized):
        return (
            "Good, I can help with pork for the freezer. "
            "Should I work around a half carcass, a full carcass, or a cut-set pack?"
        )
    return (
        "I can help with pork meat orders. "
        "Would you like a half carcass, full carcass, or a cut-set pack?"
    )


def _meat_interest_detected(normalized_text):
    return bool(re.search(
        r"\b(pork|pig\s+meat|meat|freezer|carcass|carcase|karkas|vleis|varkvleis)\b",
        str(normalized_text or "").lower(),
    ))


def _non_pork_guard_reply(message):
    text = str(message or "").lower()
    if not re.search(r"\b(beef|mutton|lamb|chicken|goat)\b", text):
        return ""
    if re.search(r"\b(pork|pig|carcass|carcase|half|full)\b", text):
        return ""
    return (
        "At the moment I can help with pork orders only. "
        "For pork, are you interested in a half carcass, full carcass, custom cuts, or assisted slaughter?"
    )


def _frustration_guard_reply(message, facts, knowledge=None):
    text = str(message or "").lower()
    if not re.search(r"\b(annoying|frustrated|frustrating|upset|irritated|nobody|shit|fuck|ridiculous|stupid)\b", text):
        return ""
    profile = public_profile(knowledge or {})
    acknowledgement = ((knowledge or {}).get("voice") or {}).get("frustration_acknowledgement") or "I hear you. I will keep this practical."
    farm_name = profile.get("farm_name") or "Amadeus Farm"
    if not re.search(r"\b(price|cost|quote|invoice|how much)\b", text):
        if facts.get("product_type") != "unknown":
            next_step = _next_fact_question(facts)
            return (
                f"{acknowledgement} I am Sam from {farm_name}. "
                f"{next_step}"
            )
        return (
            f"{acknowledgement} I am Sam from {farm_name}. "
            "Are you looking for pork meat sales, live pig sales, or just general farm information?"
        )
    if facts.get("product_type") == "unknown":
        return (
            "I understand, and I do not want to waste your time. "
            "I need the pork option first so the farm does not give you the wrong price: "
            "half carcass, full carcass, custom cuts, or assisted slaughter?"
        )
    return (
        "I understand, and I do not want to waste your time. "
        "The farm still has to approve price, timing, and any deposit rule before I quote or book anything."
    )


def _deposit_question_reply(message, facts, knowledge=None):
    text = str(message or "").lower()
    if not re.search(r"\b(why|what|how)\b.*\b(deposit|pay|payment)\b|\bdeposit\b.*\b(why|for what|needed)\b", text):
        return ""
    meat = meat_sales_knowledge(knowledge or {})
    explanation = meat.get("deposit_explanation") or "The deposit is there to hold your place in the preorder run and to help the farm plan properly."
    return (
        f"{explanation} "
        "It is still not treated as a final booking until the money reflects in the farm account and the farm confirms the available run."
    )


def _payment_state_reply(message, facts, prior_context, knowledge=None):
    text = str(message or "").lower()
    latest_event = _clean((prior_context or {}).get("latest_event"), 100)
    asks_payment_state = bool(re.search(
        r"\b(already paid|i paid|paid the deposit|sent pop|sent proof|proof sent|pop sent|"
        r"money reflect|reflects|how long|how long does that take|when.*delivery|release delivery)\b",
        text,
    ))
    if not asks_payment_state:
        return ""
    if latest_event in {"deposit_followup_needed", "pop_received_unverified", "customer_followup_sent", "estimated_quote_chatwoot_accepted"} or facts.get("product_type") != "unknown":
        pop_explanation = meat_sales_knowledge(knowledge or {}).get("pop_explanation") or "POP is useful, but I cannot mark the deposit as received until the money reflects in the farm account."
        return (
            f"Thanks for checking. {pop_explanation} "
            "Once the farm confirms the bank receipt, the booking can move to the carcass and delivery planning steps."
        )
    return ""


def _next_fact_question(facts):
    if facts.get("product_type") in {"half_carcass", "full_carcass", "custom_cut"} and not facts.get("cut_set"):
        return "Which cut set would you prefer? Set A is the family freezer pack, or I can explain the available sets."
    if not facts.get("location"):
        return "Which town or area should I use for collection or delivery?"
    if not facts.get("delivery_or_collection"):
        return "Would you prefer collection or delivery?"
    if facts.get("delivery_or_collection") == "delivery" and not facts.get("delivery_address_line_1"):
        return "Please send the delivery street address or farm name, town, and any useful directions for the driver."
    if not facts.get("timing"):
        return "When would you ideally like the pork: this week, next week, or the next available farm run?"
    if not facts.get("payment_method"):
        return "For meat sales we use EFT only for now. Is EFT fine for the deposit and final balance?"
    return "I have the core details and will keep the next step clear."


def _price_or_document_guard_reply(message, facts):
    text = str(message or "").lower()
    asks_money_or_document = _asks_money_or_document(text)
    if not asks_money_or_document or facts.get("product_type") == "unknown":
        return ""
    missing = []
    if not facts.get("delivery_or_collection"):
        missing.append("delivery or collection")
    if facts.get("delivery_or_collection") == "delivery" and not facts.get("delivery_address_line_1"):
        missing.append("delivery address")
    if not facts.get("timing"):
        missing.append("timing")
    if not facts.get("payment_method"):
        missing.append("payment method")
    missing_text = f" I still need {', '.join(missing)}." if missing else ""
    return (
        "I can note the request, but the farm must confirm price, timing, and any deposit rule "
        f"before quoting, invoicing, or booking anything.{missing_text}"
    )


def _asks_money_or_document(message):
    return bool(re.search(r"\b(price|cost|quote|invoice|how much|estimate|estimated)\b", str(message or "").lower()))


def _quote_blocker_reply(blockers):
    blockers = blockers if isinstance(blockers, list) else []
    labels = {
        "price_per_kg_required": "price per kg",
        "estimated_weight_kg_required": "estimated weight",
        "deposit_percent_required": "deposit rule",
        "bank_details_required": "bank details",
        "customer_name_required": "customer name",
        "payment_reference_required": "payment reference",
    }
    missing = [labels.get(str(item), str(item).replace("_", " ")) for item in blockers if str(item).strip()]
    if not missing:
        return ""
    return (
        "I am not able to prepare the estimated quote yet because the farm document gate is missing "
        f"{', '.join(missing)}."
    )


def _mentioned_cut_set(text):
    match = re.search(r"\bset\s*([abcd])\b", str(text or ""), re.I)
    return f"Set {match.group(1).upper()}" if match else ""


def _safe_llm_fact_patch(value):
    value = value if isinstance(value, dict) else {}
    product_type = _clean(value.get("product_type"), 80)
    if product_type not in {"half_carcass", "full_carcass", "custom_cut", "assisted_slaughter", "unknown"}:
        product_type = ""
    patch = {
        "product_type": product_type,
        "cut_set": _normal_cut_set(value.get("cut_set")),
        "location": _normal_location(value.get("location")),
        "timing": _clean(value.get("timing"), 120),
        "delivery_or_collection": _normal_delivery(value.get("delivery_or_collection")),
        "delivery_address_line_1": _clean(value.get("delivery_address_line_1"), 240),
        "delivery_town": _normal_location(value.get("delivery_town")),
        "delivery_area": _clean(value.get("delivery_area"), 120),
        "delivery_notes": _clean(value.get("delivery_notes"), 600),
        "payment_method": _normal_payment(value.get("payment_method")),
        "budget_amount": _normal_money_amount(value.get("budget_amount")),
        "target_packed_kg": _normal_kg_amount(value.get("target_packed_kg")),
        "match_preference": _normal_match_preference(value.get("match_preference")),
    }
    return {key: val for key, val in patch.items() if val}


def _conversation_lead_context(conversation_id):
    conversation_id = _clean(conversation_id, 100)
    if not conversation_id:
        return {}
    result, status_code = get_active_sales_lead_by_conversation(conversation_id)
    if status_code != 200 or not isinstance(result, dict):
        return {}
    lead = result.get("lead") if isinstance(result.get("lead"), dict) else {}
    if not lead:
        return {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    return {
        "lead_id": _clean(lead.get("lead_id"), 100),
        "interest": interest,
        "latest_event": _latest_event_type(lead),
    }


def _latest_event_type(lead):
    latest_event = lead.get("latest_event") if isinstance(lead, dict) else ""
    if isinstance(latest_event, dict):
        return _clean(latest_event.get("event_type"), 100)
    return _clean(latest_event, 100)


def _record_booking_confirmation_if_ready(inbound, prior_context):
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    lead_id = _clean(prior_context.get("lead_id"), 100)
    if not lead_id:
        return {"recorded": False, "status": "lead_context_required"}
    if not _customer_yes_intent(inbound.get("content")):
        return {"recorded": False, "status": "not_customer_confirmation"}
    if prior_context.get("latest_event") != "customer_followup_sent":
        return {
            "recorded": False,
            "status": "customer_followup_not_sent",
            "latest_event": prior_context.get("latest_event") or "",
        }
    result, status_code = record_customer_booking_confirmation(
        lead_id,
        {
            "customer_confirmation": inbound.get("content") or "",
            "confirmed_by": "Sam Meat",
            "confirmation_channel": inbound.get("channel") or "chatwoot",
        },
    )
    return {
        "recorded": status_code in {200, 201},
        "status_code": status_code,
        "status": result.get("status") if isinstance(result, dict) else "",
        "lead_id": lead_id,
    }


def _customer_yes_intent(message):
    text = str(message or "").strip().lower()
    if not text:
        return False
    if re.search(r"\b(no|not now|hold|cancel|stop|wait)\b", text):
        return False
    return bool(re.search(
        r"\b(yes|ja|yep|yeah|correct|confirmed?|confirm|please proceed|go ahead|book it|"
        r"send it|final booking|happy with that|that works)\b",
        text,
    ))


def _merge_prior_context(facts, prior_context):
    facts = dict(facts or {})
    interest = prior_context.get("interest") if isinstance(prior_context, dict) else {}
    if not isinstance(interest, dict) or not interest:
        return facts
    for key in (
        "product_type",
        "cut_set",
        "location",
        "timing",
        "delivery_or_collection",
        "delivery_address_line_1",
        "delivery_town",
        "delivery_area",
        "delivery_notes",
        "delivery_place_name",
        "delivery_location_latitude",
        "delivery_location_longitude",
        "delivery_maps_url",
        "payment_method",
        "budget_amount",
        "target_packed_kg",
        "match_preference",
    ):
        current = _clean(facts.get(key), 600)
        prior = _clean(interest.get(key), 600)
        if key == "product_type" and current == "unknown" and prior:
            facts[key] = prior
        elif not current and prior:
            facts[key] = prior
    if not facts.get("delivery_town") and facts.get("location"):
        facts["delivery_town"] = facts["location"]
    return _apply_meat_pilot_defaults(facts)


def _apply_meat_pilot_defaults(facts):
    facts = dict(facts or {})
    if (
        not facts.get("payment_method")
        and facts.get("product_type") in {"half_carcass", "full_carcass", "custom_cut", "assisted_slaughter"}
    ):
        facts["payment_method"] = "EFT"
    return facts


def _record_delivery_address_if_ready(lead_id, inbound, facts):
    lead_id = _clean(lead_id, 100)
    if not lead_id or facts.get("delivery_or_collection") != "delivery":
        return {"recorded": False, "status": "not_delivery"}
    address = _clean(facts.get("delivery_address_line_1"), 240)
    town = _clean(facts.get("delivery_town") or facts.get("location"), 120)
    if not address or not town:
        return {"recorded": False, "status": "delivery_address_incomplete"}
    payload = {
        "event_type": "delivery_address_captured",
        "address_line_1": address,
        "town": town,
        "area": facts.get("delivery_area") or "",
        "delivery_notes": _delivery_notes_with_location(facts),
        "contact_name": inbound.get("customer_name") or facts.get("customer_name") or "",
        "contact_phone": inbound.get("customer_phone") or "",
        "actor_role": "sam",
        "actor_label": "Sam Meat",
        "customer_channel": inbound.get("channel") or "chatwoot_whatsapp",
        "whatsapp_window_state": inbound.get("whatsapp_window_state") or "open",
    }
    result, status_code = record_meat_fulfillment_event(lead_id, payload)
    return {
        "recorded": status_code in {200, 201},
        "status_code": status_code,
        "status": result.get("status") if isinstance(result, dict) else "",
    }


def _build_deposit_instruction_if_ready(lead_id, source):
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"ready": False, "status": "lead_context_required"}
    bank = _bank_details(source)
    if not bank.get("configured"):
        return {
            "ready": False,
            "status": "bank_details_not_configured",
            "missing_envs": bank.get("missing_envs", []),
        }
    contract_result, status_code = get_sales_lead_preorder_contract(lead_id)
    if status_code != 200:
        return {"ready": False, "status": "contract_not_ready", "status_code": status_code}
    contract = contract_result.get("contract") if isinstance(contract_result.get("contract"), dict) else {}
    if contract.get("contract_status") != "owner_money_path_ready":
        return {
            "ready": False,
            "status": "owner_money_path_not_ready",
            "contract_status": contract.get("contract_status", ""),
        }
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    required = contract.get("required_before_money_path") if isinstance(contract.get("required_before_money_path"), dict) else {}
    reference = _payment_reference(lead_id, source)
    estimate = _deposit_estimate(required)
    buyer = summary.get("buyer_or_contact") or "there"
    amount_line = (
        f"Deposit amount: {estimate['label']}"
        if estimate.get("label")
        else f"Deposit rule: {required.get('deposit_amount_or_rule') or 'approved farm deposit rule'}"
    )
    message = (
        f"Thanks {buyer}, I can send the booking payment details.\n"
        f"{amount_line}\n"
        f"Reference: {reference}\n"
        f"Account name: {bank['account_name']}\n"
        f"Bank: {bank['bank_name']}\n"
        f"Account number: {bank['account_number']}\n"
        f"Branch code: {bank['branch_code']}\n"
        f"Account type: {bank['account_type']}\n"
        "Please send proof of payment here once done. "
        "The booking only moves forward once the money reflects in the farm account."
    )
    _record_deposit_instruction_event(lead_id, message, reference, estimate)
    return {
        "ready": True,
        "status": "deposit_payment_instruction_ready",
        "lead_id": lead_id,
        "payment_reference": reference,
        "deposit_estimate": estimate,
        "message": _clean(message, 1600),
    }


def _record_deposit_instruction_event(lead_id, message, reference, estimate):
    notes = {
        "source": "backend_native_sam_meat",
        "kind": "deposit_payment_instruction_prepared",
        "message": _clean(message, 1200),
        "payment_reference": reference,
        "deposit_estimate": estimate if isinstance(estimate, dict) else {},
    }
    record_sales_lead_event(
        lead_id,
        {
            "event_type": "deposit_followup_needed",
            "status_observed": "deposit_pending",
            "recorded_by": "backend_sam_meat",
            "notes": json.dumps(notes, ensure_ascii=True, sort_keys=True),
        },
    )


def _record_pop_if_ready(inbound, prior_context, source):
    if not _pop_or_payment_proof_intent(inbound.get("content")):
        return {"recorded": False, "detected": False, "status": "not_payment_proof"}
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    lead_id = _clean(prior_context.get("lead_id"), 100)
    if not lead_id:
        return {"recorded": False, "detected": True, "status": "lead_context_required"}
    ops, status_code = get_meat_ops_status(lead_id)
    if status_code != 200:
        return {"recorded": False, "detected": True, "status": "meat_ops_not_ready", "status_code": status_code}
    reservation = _active_reservation_for_pop(ops.get("reservations") or [])
    if not reservation:
        return {"recorded": False, "detected": True, "status": "active_reservation_required"}
    reference = _extract_payment_reference(inbound.get("content")) or _payment_reference(lead_id, source)
    result, deposit_status = record_meat_deposit_event(
        lead_id,
        {
            "reservation_id": reservation.get("reservation_id"),
            "event_type": "pop_received_unverified",
            "payment_reference": reference,
            "payment_method": "EFT",
            "notes": _clean(inbound.get("content"), 500),
            "recorded_by": "Sam Meat",
        },
    )
    return {
        "recorded": deposit_status in {200, 201},
        "detected": True,
        "status_code": deposit_status,
        "status": result.get("status") if isinstance(result, dict) else "",
        "lead_id": lead_id,
        "reservation_id": reservation.get("reservation_id"),
        "payment_reference": reference,
    }


def _active_reservation_for_pop(reservations):
    active_statuses = {"half_reserved_pending_pair", "full_carcass_committed", "deposit_pending", "ready_for_slaughter_booking"}
    candidates = [
        item for item in reservations or []
        if item.get("reservation_id")
        and item.get("effective_status", item.get("status")) in active_statuses
    ]
    if not candidates:
        return {}
    candidates.sort(key=lambda row: (
        1 if row.get("status") == "full_carcass_committed" else 0,
        row.get("created_at", ""),
    ), reverse=True)
    return candidates[0]


def _pop_or_payment_proof_intent(message):
    text = str(message or "").lower()
    return bool(re.search(
        r"\b(pop|proof of payment|payment proof|paid|i paid|eft done|sent proof|receipt|bank proof)\b",
        text,
    ))


def _extract_payment_reference(message):
    text = str(message or "")
    match = re.search(r"\b(?:ref(?:erence)?|reference|pop)\s*(?:is|:|-)?\s*([A-Z0-9][A-Z0-9\-_/]{3,40})\b", text, re.I)
    return _clean(match.group(1), 80).upper() if match else ""


def _bank_details(source):
    return _shared_bank_details(source if source is not None else os.environ)


def _bank_details_configured(source):
    return bool(_bank_details(source).get("configured"))


def _payment_reference(lead_id, source):
    return _shared_payment_reference(lead_id)


def _deposit_estimate(required):
    required = required if isinstance(required, dict) else {}
    price = _first_number(required.get("price_per_kg"))
    weight = _average_weight_kg(required.get("estimated_weight_or_size"))
    percent = _first_number(required.get("deposit_amount_or_rule"))
    if price and weight and percent:
        total = price * weight
        deposit = total * (percent / 100)
        return {
            "amount": round(deposit, 2),
            "label": f"about R{deposit:,.2f} ({percent:g}% deposit estimate)",
            "basis": "estimated_weight_x_price_x_deposit_percent",
        }
    return {"amount": None, "label": "", "basis": "rule_only"}


def _average_weight_kg(value):
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", str(value or ""))]
    if not numbers:
        return None
    if len(numbers) >= 2:
        return (numbers[0] + numbers[1]) / 2
    return numbers[0]


def _first_number(value):
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else None


def _ignored(status, event, message_type, content, conversation_id, customer_name, channel):
    return {
        "processable": False,
        "status": status,
        "event": event,
        "message_type": message_type,
        "content": content,
        "shared_location": {},
        "conversation_id": conversation_id,
        "customer_name": customer_name,
        "channel": channel,
        "whatsapp_window_state": "unknown",
    }


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


def _normal_whatsapp_window_state(value):
    text = str(value or "").strip().lower()
    if text in {"open", "active", "service_window_open", "within_24h", "within_24_hours"}:
        return "open"
    if text in {"closed", "expired", "service_window_closed", "outside_24h", "outside_24_hours"}:
        return "closed"
    if text in {"template_required", "requires_template", "template"}:
        return "template_required"
    if text in {"manual_owner_only", "owner_manual_only", "manual"}:
        return "manual_owner_only"
    if text == "unknown":
        return "unknown"
    return ""


def _normal_chatwoot_message_type(payload):
    payload = payload if isinstance(payload, dict) else {}
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


def _normalized_customer_text(value):
    text = str(value or "").lower()
    replacements = {
        "hlaf": "half",
        "carcas": "carcass",
        "carcasse": "carcass",
        "carcase": "carcass",
        "rivrsdale": "riversdale",
        "colect": "collect",
        "collet": "collect",
        "nxt": "next",
        "afhaal": "collection",
        "haal": "collect",
        "volgende week": "next week",
        "halwe": "half",
        "karkas": "carcass",
        "karkasse": "carcass",
        "vark": "pork",
        "varkvleis": "pork",
        "kontant": "cash",
        "oorplasing": "eft",
        "eft": "eft",
    }
    for source, target in replacements.items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    return text


def _maps_location_from_text(value):
    text = str(value or "")
    url_match = re.search(r"https?://(?:www\.)?(?:maps\.google\.[^\s]+|goo\.gl/maps/[^\s]+|maps\.app\.goo\.gl/[^\s]+)", text, re.I)
    coord_match = re.search(r"(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)", text)
    if not url_match and not coord_match:
        return {}
    maps_url = url_match.group(0).rstrip(".,);") if url_match else ""
    latitude = coord_match.group(1) if coord_match else ""
    longitude = coord_match.group(2) if coord_match else ""
    return {
        "maps_url": maps_url or f"https://maps.google.com/?q={latitude},{longitude}",
        "latitude": latitude,
        "longitude": longitude,
        "place_name": "Shared Google Maps location",
    }


def _town_from_text(value):
    text = str(value or "").lower()
    if "riversdale" in text:
        return "Riversdale"
    if "albertinia" in text:
        return "Albertinia"
    return ""


def _normal_cut_set(value):
    match = re.search(r"\bset\s*([abcd])\b", str(value or ""), re.I)
    return f"Set {match.group(1).upper()}" if match else ""


def _normal_location(value):
    text = str(value or "").lower()
    if "riversdale" in text:
        return "Riversdale"
    if "albertinia" in text:
        return "Albertinia"
    return _clean(value, 80)


def _normal_delivery(value):
    text = str(value or "").lower()
    if "collect" in text or "pickup" in text:
        return "collection"
    if "deliver" in text:
        return "delivery"
    return ""


def _normal_payment(value):
    text = str(value or "").lower()
    if "eft" in text:
        return "EFT"
    if "cash" in text:
        return "Cash"
    return ""


def _budget_amount_from_text(value):
    text = str(value or "")
    match = re.search(
        r"(?:\b(?:budget|spend|around|about|under|below|max(?:imum)?|up to)\b[^\d]{0,24})?"
        r"(?:r|zar)\s*([0-9][0-9\s,.]{1,12})\b",
        text,
        re.I,
    )
    if not match:
        match = re.search(r"\b(?:budget|spend|under|below|max(?:imum)?|up to)\b[^\d]{0,24}([0-9][0-9\s,.]{2,12})\b", text, re.I)
    return _normal_money_amount(match.group(1)) if match else ""


def _target_packed_kg_from_text(value):
    text = str(value or "")
    match = re.search(
        r"\b(?:around|about|roughly|approx(?:imately)?|looking\s+for|want|need)?\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*kg\b(?:\s*(?:packed|processed|pork|meat))?",
        text,
        re.I,
    )
    if not match:
        return ""
    kg = _normal_kg_amount(match.group(1))
    if not kg:
        return ""
    nearby = text[max(0, match.start() - 20):match.end() + 30].lower()
    if "live" in nearby and "packed" not in nearby:
        return ""
    return kg


def _match_preference_from_text(value, budget_amount="", target_packed_kg=""):
    text = str(value or "").lower()
    if re.search(r"\b(heaviest|biggest|largest|heavy one|largest one)\b", text):
        return "heaviest"
    if re.search(r"\b(soonest|quickest|as soon as possible|asap|next available|first available)\b", text):
        return "soonest"
    if re.search(r"\b(cheapest|lowest price|most affordable|budget option|cheap)\b", text):
        return "cheapest"
    if re.search(r"\b(best fit|best match|recommend|you choose|closest match)\b", text):
        return "best_fit"
    if target_packed_kg:
        return "closest_weight"
    if budget_amount:
        return "budget_fit"
    return ""


def _normal_money_amount(value):
    text = str(value or "").replace(" ", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return ""
    amount = float(match.group(0))
    if amount <= 0 or amount > 1000000:
        return ""
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _normal_kg_amount(value):
    text = str(value or "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return ""
    amount = float(match.group(0))
    if amount <= 0 or amount > 500:
        return ""
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _normal_match_preference(value):
    text = str(value or "").strip().lower()
    aliases = {
        "heavy": "heaviest",
        "biggest": "heaviest",
        "largest": "heaviest",
        "quickest": "soonest",
        "asap": "soonest",
        "budget": "budget_fit",
        "budget_fit": "budget_fit",
        "closest": "closest_weight",
        "closest_weight": "closest_weight",
        "affordable": "cheapest",
        "cheap": "cheapest",
        "best": "best_fit",
        "best_fit": "best_fit",
    }
    normalized = aliases.get(text, text)
    return normalized if normalized in {"heaviest", "soonest", "cheapest", "best_fit", "closest_weight", "budget_fit"} else ""


def _extract_shared_location(payload):
    payload = payload if isinstance(payload, dict) else {}
    candidates = []
    for key in ("location", "coordinates", "content_attributes", "additional_attributes"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for item in payload.get("attachments") or []:
        if isinstance(item, dict):
            candidates.append(item)
            if isinstance(item.get("coordinates"), dict):
                candidates.append(item["coordinates"])
            if isinstance(item.get("location"), dict):
                candidates.append(item["location"])

    merged = {}
    for item in candidates:
        lat = item.get("latitude") or item.get("lat")
        lng = item.get("longitude") or item.get("lng") or item.get("lon")
        raw_maps_url = item.get("maps_url") or item.get("map_url") or item.get("url") or item.get("data_url")
        maps_url = raw_maps_url if _looks_like_map_url(raw_maps_url) else ""
        place = item.get("name") or item.get("place_name") or item.get("title") or item.get("address")
        type_hint = " ".join(
            str(item.get(key) or "")
            for key in ("file_type", "type", "attachment_type", "content_type", "message_type")
        ).lower()
        location_hint = "location" in type_hint or "map" in type_hint
        if lat in (None, "") and lng in (None, "") and not maps_url and not location_hint:
            continue
        if lat not in (None, "") and lng not in (None, ""):
            merged["latitude"] = _clean(lat, 40)
            merged["longitude"] = _clean(lng, 40)
        if maps_url:
            merged["maps_url"] = _clean(maps_url, 500)
        if place and (location_hint or maps_url or (lat not in (None, "") and lng not in (None, ""))):
            merged["place_name"] = _clean(place, 240)
    if not merged:
        return {}
    if not merged.get("maps_url") and merged.get("latitude") and merged.get("longitude"):
        merged["maps_url"] = f"https://maps.google.com/?q={merged['latitude']},{merged['longitude']}"
    merged["summary"] = _clean(
        merged.get("place_name")
        or f"Shared location pin {merged.get('latitude', '')},{merged.get('longitude', '')}",
        300,
    )
    return merged


def _looks_like_map_url(value):
    return bool(re.search(r"https?://(?:www\.)?(?:maps\.google\.|goo\.gl/maps/|maps\.app\.goo\.gl/)", str(value or ""), re.I))


def _shared_location_fact_patch(shared_location, facts):
    patch = {
        "delivery_or_collection": facts.get("delivery_or_collection") or "delivery",
        "delivery_place_name": shared_location.get("place_name") or "",
        "delivery_location_latitude": shared_location.get("latitude") or "",
        "delivery_location_longitude": shared_location.get("longitude") or "",
        "delivery_maps_url": shared_location.get("maps_url") or "",
    }
    if not facts.get("delivery_address_line_1"):
        patch["delivery_address_line_1"] = shared_location.get("place_name") or "Shared location pin"
    return {key: value for key, value in patch.items() if value}


def _delivery_notes_with_location(facts):
    notes = _clean(facts.get("delivery_notes"), 600)
    location_bits = []
    if facts.get("delivery_place_name"):
        location_bits.append(f"Place: {facts.get('delivery_place_name')}")
    if facts.get("delivery_location_latitude") and facts.get("delivery_location_longitude"):
        location_bits.append(f"Pin: {facts.get('delivery_location_latitude')},{facts.get('delivery_location_longitude')}")
    if facts.get("delivery_maps_url"):
        location_bits.append(f"Map: {facts.get('delivery_maps_url')}")
    combined = "; ".join([item for item in [notes, *location_bits] if item])
    return _clean(combined, 600)


def _token_matches(headers, query_args, expected):
    authorization = str(headers.get("Authorization", "") or "").strip()
    if authorization.startswith("Bearer "):
        return hmac.compare_digest(authorization[len("Bearer "):].strip(), expected)
    provided = str(headers.get("X-Amadeus-Sam-Meat-Webhook-Key", "") or "").strip()
    if provided:
        return hmac.compare_digest(provided, expected)
    provided = str(query_args.get("token") or query_args.get("sam_meat_token") or "").strip()
    return hmac.compare_digest(provided, expected)


def _denied(status):
    return {
        "success": False,
        "status": status,
        "processed": False,
        "sent": False,
        "policy": sam_meat_webhook_policy(),
        **_authority_flags(False, False),
    }


def _authority_flags(sends_customer_message, calls_chatwoot):
    return {
        "sends_customer_message": bool(sends_customer_message),
        "calls_chatwoot": bool(calls_chatwoot),
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes_farm_data": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _timeout(source):
    try:
        return max(1, min(30, int(source.get(LLM_TIMEOUT_ENV, "8"))))
    except (TypeError, ValueError):
        return 8


def _strip_code_fence(value):
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]
