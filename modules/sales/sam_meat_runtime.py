import hashlib
import hmac
import json
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.sales_campaign_store import (
    get_sales_lead_preorder_contract,
    list_sales_leads,
    record_customer_booking_confirmation,
    record_sales_lead_event,
    record_sam_meat_intake_lead,
    _send_chatwoot_message,
)
from modules.sales.meat_ops import get_meat_ops_status, record_meat_deposit_event
from modules.sales.meat_fulfillment import record_meat_fulfillment_event
from modules.sales.chatwoot_hygiene import (
    HYGIENE_ENABLED_ENV,
    sync_sam_meat_chatwoot_hygiene,
)


WEBHOOK_ENABLED_ENV = "SAM_MEAT_BACKEND_WEBHOOK_ENABLED"
WEBHOOK_TOKEN_ENV = "SAM_MEAT_BACKEND_WEBHOOK_TOKEN"
AUTOREPLY_ENABLED_ENV = "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED"
LLM_ENABLED_ENV = "SAM_MEAT_BACKEND_LLM_ENABLED"
LLM_MODEL_ENV = "SAM_MEAT_BACKEND_LLM_MODEL"
LLM_URL_ENV = "SAM_MEAT_BACKEND_LLM_URL"
LLM_TIMEOUT_ENV = "SAM_MEAT_BACKEND_LLM_TIMEOUT_SECONDS"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_LLM_URL = "https://api.openai.com/v1/chat/completions"
BANK_ACCOUNT_NAME_ENV = "MEAT_SALES_BANK_ACCOUNT_NAME"
BANK_NAME_ENV = "MEAT_SALES_BANK_NAME"
BANK_ACCOUNT_NUMBER_ENV = "MEAT_SALES_BANK_ACCOUNT_NUMBER"
BANK_BRANCH_CODE_ENV = "MEAT_SALES_BANK_BRANCH_CODE"
BANK_ACCOUNT_TYPE_ENV = "MEAT_SALES_BANK_ACCOUNT_TYPE"
PAYMENT_REFERENCE_PREFIX_ENV = "MEAT_SALES_PAYMENT_REFERENCE_PREFIX"
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
    hygiene_enabled = _truthy(source.get(HYGIENE_ENABLED_ENV))
    llm_configured = bool(str(source.get(LLM_MODEL_ENV, "") or "").strip() and str(source.get(OPENAI_API_KEY_ENV, "") or "").strip())
    return {
        "enabled": enabled,
        "token_configured": len(token) >= MIN_TOKEN_CHARS,
        "autoreply_enabled": autoreply_enabled,
        "chatwoot_hygiene_enabled": hygiene_enabled,
        "llm_enabled": llm_enabled and llm_configured,
        "llm_explicitly_enabled": llm_enabled,
        "llm_configured": llm_configured,
        "enabled_env": WEBHOOK_ENABLED_ENV,
        "token_env": WEBHOOK_TOKEN_ENV,
        "autoreply_env": AUTOREPLY_ENABLED_ENV,
        "chatwoot_hygiene_env": HYGIENE_ENABLED_ENV,
        "llm_enabled_env": LLM_ENABLED_ENV,
        "llm_model_env": LLM_MODEL_ENV,
        "api_key_env": OPENAI_API_KEY_ENV,
        "bank_details_configured": _bank_details_configured(source),
        "bank_detail_envs": [
            BANK_ACCOUNT_NAME_ENV,
            BANK_NAME_ENV,
            BANK_ACCOUNT_NUMBER_ENV,
            BANK_BRANCH_CODE_ENV,
            BANK_ACCOUNT_TYPE_ENV,
            PAYMENT_REFERENCE_PREFIX_ENV,
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


def handle_sam_meat_chatwoot_inbound(payload, *, environ=None, chatwoot_sender=None, llm_extractor=None):
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
    lead_payload = build_sam_meat_lead_payload_from_inbound(inbound, facts)
    if prior_context.get("lead_id"):
        lead_payload["lead_id"] = prior_context["lead_id"]
    else:
        lead_payload["lead_id"] = _fresh_lead_id(inbound, facts)
    record_result, record_status = record_sam_meat_intake_lead(lead_payload)
    booking_confirmation = _record_booking_confirmation_if_ready(inbound, prior_context)
    decision = build_sam_meat_decision(inbound, facts, record_result, record_status)
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
    sent = False
    send_status = "autoreply_not_enabled"
    if decision["should_reply"] and _truthy(source.get(AUTOREPLY_ENABLED_ENV)):
        if inbound["whatsapp_window_state"] != "open":
            send_status = "whatsapp_window_not_open"
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
            except Exception as exc:
                send_result = {"error_type": exc.__class__.__name__, "error": str(exc)[:180]}
                send_status = "chatwoot_send_failed"
                _record_autoreply_event(decision.get("lead_id"), "sam_meat_autoreply_failed", decision["reply_text"], send_result)

    status_code = 200 if record_status in {200, 201, 400} else record_status
    return {
        "success": record_status in {200, 201, 400},
        "status": "processed",
        "processed": True,
        "inbound": inbound,
        "facts": facts,
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
        "policy": sam_meat_webhook_policy(source),
        **_authority_flags(sent, sent),
    }, status_code


def parse_chatwoot_inbound(payload):
    payload = payload if isinstance(payload, dict) else {}
    message_type = _clean(payload.get("message_type") or payload.get("message_type_string"), 60).lower()
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
        "whatsapp_window_state": "open",
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
    return facts


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


def build_sam_meat_decision(inbound, facts, record_result, record_status):
    reply = ""
    should_reply = True
    lead_id = _clean(record_result.get("lead_id") if isinstance(record_result, dict) else "", 100)
    cut_menu_reply = _cut_menu_reply(inbound.get("content"), facts)
    price_or_document_reply = _price_or_document_guard_reply(inbound.get("content"), facts)
    if cut_menu_reply:
        reply = cut_menu_reply
    elif price_or_document_reply:
        reply = price_or_document_reply
    elif record_status == 400 and record_result.get("sam_next_question"):
        reply = record_result["sam_next_question"]
    elif facts.get("product_type") == "unknown":
        reply = "Are you interested in a pork half carcass, full carcass, custom cuts, or assisted slaughter?"
    elif facts.get("product_type") in {"half_carcass", "full_carcass", "custom_cut"} and not facts.get("cut_set"):
        reply = "Which cut set would you prefer? Set A is the family freezer pack, or I can explain the available sets."
    elif not facts.get("location"):
        reply = "Which town or area would you prefer for collection or delivery?"
    elif not facts.get("delivery_or_collection"):
        reply = "Would you prefer collection or delivery?"
    elif facts.get("delivery_or_collection") == "delivery" and not facts.get("delivery_address_line_1"):
        reply = "Please send the delivery street address or farm name, town, and any useful directions for the driver."
    elif not facts.get("timing"):
        reply = "When would you ideally like the pork: this week, next week, or the next available farm run?"
    elif not facts.get("payment_method"):
        reply = "Would EFT or cash work best once the farm confirms the approved details?"
    else:
        reply = (
            "Thanks, I have noted your pork interest for the farm to review. "
            "I still need the farm to confirm price, timing, and any deposit rule before quoting or booking anything."
        )

    if lead_id:
        contract, status_code = get_sales_lead_preorder_contract(lead_id)
        if status_code == 200:
            contract_body = contract.get("contract") if isinstance(contract.get("contract"), dict) else {}
            if contract_body.get("contract_status") == "owner_money_path_ready":
                reply = (
                    "I have your meat preorder details on the farm review list. "
                    "The farm will only send approved price and booking details through the approved follow-up step."
                )

    return {
        "agent": "sam_meat_backend",
        "decision": "reply" if should_reply else "no_reply",
        "should_reply": should_reply,
        "reply_text": reply,
        "lead_id": lead_id,
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
    product_type = "unknown"
    if re.search(r"\bhalf\s+(?:pig\s+)?carcass|half\s+carcase|half\s+pork\b", lower):
        product_type = "half_carcass"
    elif re.search(r"\bfull\s+(?:pig\s+)?carcass|whole\s+(?:pig|carcass)\b", lower):
        product_type = "full_carcass"
    elif re.search(r"\bcut|cuts|set\s+[abcd]\b", lower):
        product_type = "custom_cut"
    elif "assisted slaughter" in lower:
        product_type = "assisted_slaughter"

    cut_set = ""
    match = re.search(r"\bset\s*([abcd])\b", lower)
    if match:
        cut_set = f"Set {match.group(1).upper()}"

    location = ""
    for place in ("Riversdale", "Albertinia"):
        if place.lower() in lower:
            location = place
            break

    timing = ""
    if "next available farm run" in lower:
        timing = "next available farm run"
    elif "next available week" in lower:
        timing = "next available week"
    elif "next week" in lower:
        timing = "next week"
    elif "this week" in lower:
        timing = "this week"

    delivery_or_collection = ""
    if re.search(r"\bcollect|collection|pickup|pick up\b", lower):
        delivery_or_collection = "collection"
    elif re.search(r"\bdeliver|delivery\b", lower):
        delivery_or_collection = "delivery"

    payment_method = ""
    if re.search(r"\beft\b", lower):
        payment_method = "EFT"
    elif re.search(r"\bcash\b", lower):
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

    return {
        "product_type": product_type,
        "cut_set": cut_set,
        "location": location,
        "timing": timing,
        "delivery_or_collection": delivery_or_collection,
        "delivery_address_line_1": _clean(delivery_address_line_1, 240),
        "delivery_town": location,
        "delivery_area": "",
        "delivery_notes": "",
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


def _price_or_document_guard_reply(message, facts):
    text = str(message or "").lower()
    asks_money_or_document = bool(re.search(r"\b(price|cost|quote|invoice|how much)\b", text))
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
    result, status_code = list_sales_leads(limit=50, status_filter="launch_test")
    if status_code != 200 or not isinstance(result, dict):
        return {}
    matches = []
    for lead in result.get("sales_leads") or []:
        if _clean(lead.get("chatwoot_conversation_id"), 100) != conversation_id:
            continue
        if _latest_event_type(lead) == "closed":
            continue
        matches.append(lead)
    if not matches:
        return {}
    matches.sort(key=_lead_context_score, reverse=True)
    lead = matches[0]
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    return {
        "lead_id": _clean(lead.get("lead_id"), 100),
        "interest": interest,
        "latest_event": _latest_event_type(lead),
    }


def _lead_context_score(lead):
    latest_event = _latest_event_type(lead)
    event_scores = {
        "customer_booking_confirmed": 100,
        "draft_order_created": 90,
        "customer_followup_sent": 80,
        "customer_followup_send_attempted": 70,
        "owner_customer_followup_send_approved": 60,
        "owner_money_path_approved": 50,
        "delivery_address_captured": 25,
        "sam_meat_autoreply_sent": 10,
        "sam_meat_autoreply_attempted": 8,
    }
    score = event_scores.get(latest_event, 0)
    if lead.get("created_at"):
        score += 1
    return score


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
    source = source if source is not None else os.environ
    values = {
        "account_name": _clean(source.get(BANK_ACCOUNT_NAME_ENV), 160),
        "bank_name": _clean(source.get(BANK_NAME_ENV), 120),
        "account_number": _clean(source.get(BANK_ACCOUNT_NUMBER_ENV), 80),
        "branch_code": _clean(source.get(BANK_BRANCH_CODE_ENV), 80),
        "account_type": _clean(source.get(BANK_ACCOUNT_TYPE_ENV) or "Business account", 80),
    }
    required = {
        BANK_ACCOUNT_NAME_ENV: values["account_name"],
        BANK_NAME_ENV: values["bank_name"],
        BANK_ACCOUNT_NUMBER_ENV: values["account_number"],
        BANK_BRANCH_CODE_ENV: values["branch_code"],
    }
    missing = [key for key, value in required.items() if not value]
    return {**values, "configured": not missing, "missing_envs": missing}


def _bank_details_configured(source):
    return bool(_bank_details(source).get("configured"))


def _payment_reference(lead_id, source):
    prefix = _clean((source if source is not None else os.environ).get(PAYMENT_REFERENCE_PREFIX_ENV) or "AMADEUS-MEAT", 40)
    suffix = re.sub(r"[^A-Z0-9]", "", str(lead_id or "").upper())[-8:] or "MEAT"
    return f"{prefix}-{suffix}"[:80]


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
        maps_url = item.get("maps_url") or item.get("map_url") or item.get("url") or item.get("data_url")
        place = item.get("name") or item.get("place_name") or item.get("title") or item.get("address")
        if lat not in (None, "") and lng not in (None, ""):
            merged["latitude"] = _clean(lat, 40)
            merged["longitude"] = _clean(lng, 40)
        if maps_url:
            merged["maps_url"] = _clean(maps_url, 500)
        if place:
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
