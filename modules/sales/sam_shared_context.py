import json
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.sales_campaign_store import (
    get_active_sales_lead_by_conversation,
    list_sales_campaigns,
    list_sales_outreach_drafts,
)
from modules.sales.sam_farm_knowledge import load_sam_farm_knowledge, meat_sales_knowledge, public_profile


CHATWOOT_BASE_URL_ENV = "CHATWOOT_BASE_URL"
CHATWOOT_ACCOUNT_ID_ENV = "CHATWOOT_ACCOUNT_ID"
CHATWOOT_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
CHATWOOT_TOKEN_FALLBACK_ENV = "CHATWOOT_API_TOKEN"


def build_sam_v3_context_packet(inbound, prior_context=None, *, environ=None, message_fetcher=None, campaign_fetcher=None):
    source = environ if environ is not None else os.environ
    inbound = inbound if isinstance(inbound, dict) else {}
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    attrs = inbound.get("conversation_custom_attributes") if isinstance(inbound.get("conversation_custom_attributes"), dict) else {}
    labels = inbound.get("conversation_labels") if isinstance(inbound.get("conversation_labels"), list) else []
    source_campaign_id = _source_campaign_id(inbound, attrs)
    campaign_context = _campaign_context(
        source_campaign_id,
        attrs,
        environ=source,
        campaign_fetcher=campaign_fetcher,
    )
    recent_messages = _recent_messages(
        inbound,
        environ=source,
        message_fetcher=message_fetcher,
    )
    knowledge_result = load_sam_farm_knowledge(source)
    knowledge = knowledge_result.get("knowledge") if isinstance(knowledge_result.get("knowledge"), dict) else {}
    lead_context = dict(prior_context)
    if not lead_context and inbound.get("conversation_id"):
        lead_context = _active_lead_context(inbound.get("conversation_id"))
    packet = {
        "version": "sam_v3_context_packet_v1",
        "agent": "Sam Meat",
        "current_message": inbound.get("content") or "",
        "customer": {
            "name": inbound.get("customer_name") or "",
            "phone": inbound.get("customer_phone") or "",
            "contact_id": inbound.get("contact_id") or "",
            "channel": inbound.get("channel") or "",
            "conversation_id": inbound.get("conversation_id") or "",
        },
        "chatwoot": {
            "conversation_id": inbound.get("conversation_id") or "",
            "labels": labels,
            "custom_attributes": attrs,
            "whatsapp_window_state": inbound.get("whatsapp_window_state") or "unknown",
        },
        "conversation": {
            "recent_messages": recent_messages,
            "summary": _conversation_summary(recent_messages, inbound.get("content") or ""),
        },
        "lead": {
            "lead_id": lead_context.get("lead_id", ""),
            "interest": lead_context.get("interest") if isinstance(lead_context.get("interest"), dict) else {},
            "latest_event": lead_context.get("latest_event", ""),
        },
        "source_context": campaign_context,
        "farm_knowledge": {
            "public_profile": public_profile(knowledge),
            "meat_sales": meat_sales_knowledge(knowledge),
            "knowledge_status": knowledge_result.get("status", ""),
        },
        "business_rules": _business_rules(knowledge),
        "allowed_actions": [
            "reply_to_customer",
            "update_lead_facts",
            "sync_chatwoot_hygiene",
            "record_unverified_pop",
            "request_missing_fact",
            "handoff_for_owner_review",
            "handoff_to_butcher_or_ledger_when_ready",
        ],
        "blocked_actions": [
            "invent_price",
            "confirm_final_availability",
            "confirm_booking_without_gate",
            "confirm_payment_without_bank_receipt",
            "reserve_stock_without_gate",
            "confirm_slaughter_butcher_or_delivery_booking",
            "post_publicly_or_spend_money",
        ],
    }
    packet["context_quality"] = _context_quality(packet)
    return packet


def _source_campaign_id(inbound, attrs):
    attrs = attrs if isinstance(attrs, dict) else {}
    candidates = [
        attrs.get("meat_source_campaign_id"),
        attrs.get("source_campaign_id"),
        attrs.get("beacon_campaign_id"),
        attrs.get("campaign_id"),
        inbound.get("source_campaign_id"),
        inbound.get("campaign_id"),
    ]
    for value in candidates:
        cleaned = _clean(value, 120)
        if cleaned:
            return cleaned
    return ""


def _campaign_context(campaign_id, attrs, *, environ=None, campaign_fetcher=None):
    campaign_id = _clean(campaign_id, 120)
    attrs = attrs if isinstance(attrs, dict) else {}
    campaign = {}
    draft = {}
    if campaign_fetcher:
        fetched = campaign_fetcher(campaign_id, attrs) or {}
        campaign = fetched.get("campaign") if isinstance(fetched.get("campaign"), dict) else {}
        draft = fetched.get("draft") if isinstance(fetched.get("draft"), dict) else {}
    elif campaign_id:
        campaign = _find_campaign(campaign_id)
        draft = _find_outreach_draft(campaign_id)
    if not campaign and _looks_like_meat_source(attrs):
        campaign = _fallback_meat_campaign_context(attrs)
    if not campaign and not campaign_id:
        return {
            "available": False,
            "source": "none",
            "campaign_id": "",
            "sales_lane": "",
            "product_focus": "",
            "post_text": "",
            "call_to_action": "",
        }
    opportunity = campaign.get("opportunity") if isinstance(campaign.get("opportunity"), dict) else {}
    campaign_draft = campaign.get("draft") if isinstance(campaign.get("draft"), dict) else {}
    return {
        "available": True,
        "source": "beacon_or_sales_campaign",
        "campaign_id": campaign.get("campaign_id") or campaign_id,
        "campaign_title": campaign.get("campaign_title") or campaign.get("title") or "",
        "sales_lane": _sales_lane_from_campaign(campaign, opportunity, attrs),
        "product_focus": _product_focus_from_campaign(campaign, opportunity, campaign_draft, attrs),
        "target_area": _target_area_from_campaign(opportunity, attrs),
        "post_text": _post_text_from_campaign(campaign_draft, draft, attrs),
        "call_to_action": _call_to_action_from_campaign(campaign_draft, draft),
        "latest_event": campaign.get("latest_event") or {},
        "outreach_draft": {
            "draft_id": draft.get("draft_id", ""),
            "audience_label": draft.get("audience_label", ""),
            "draft_text": draft.get("draft_text", ""),
        },
    }


def _find_campaign(campaign_id):
    result, status = list_sales_campaigns(limit=50)
    if status != 200:
        return {}
    for campaign in result.get("sales_campaigns", []):
        if campaign.get("campaign_id") == campaign_id:
            return campaign
    return {}


def _find_outreach_draft(campaign_id):
    result, status = list_sales_outreach_drafts(limit=50)
    if status != 200:
        return {}
    for draft in result.get("outreach_drafts", []):
        if draft.get("campaign_id") == campaign_id:
            return draft
    return {}


def _fallback_meat_campaign_context(attrs):
    return {
        "campaign_id": _clean(attrs.get("meat_source_campaign_id") or attrs.get("source_campaign_id"), 120),
        "campaign_title": "Beacon meat campaign",
        "opportunity": {
            "sales_lane": "meat_preorder",
            "product_focus": _clean(attrs.get("meat_product_focus") or attrs.get("product_focus"), 180)
            or "Amadeus Farm pork freezer options",
            "target_area": _clean(attrs.get("meat_delivery_town") or attrs.get("target_area"), 120),
        },
        "draft": {
            "post_text": _clean(attrs.get("source_post_text") or attrs.get("post_text"), 1200),
            "call_to_action": _clean(attrs.get("source_call_to_action") or "Message Sam for freezer options.", 240),
        },
    }


def _looks_like_meat_source(attrs):
    text = " ".join(_clean(attrs.get(key), 500) for key in attrs).lower()
    return bool(re.search(r"\b(meat|pork|freezer|carcass|set a|set b|beacon)\b", text))


def _recent_messages(inbound, *, environ=None, message_fetcher=None):
    payload_messages = inbound.get("recent_messages") if isinstance(inbound.get("recent_messages"), list) else []
    messages = [_message_snapshot(item) for item in payload_messages]
    if not messages and message_fetcher:
        messages = [_message_snapshot(item) for item in (message_fetcher(inbound.get("conversation_id")) or [])]
    if not messages and _truthy((environ or {}).get("SAM_MEAT_BACKEND_FETCH_CHATWOOT_HISTORY_ENABLED")):
        messages = _fetch_chatwoot_messages(inbound.get("conversation_id"), environ=environ)
    if not messages and inbound.get("content"):
        messages = [{
            "role": "customer",
            "content": inbound.get("content") or "",
            "message_id": inbound.get("message_id") or "",
            "created_at": inbound.get("last_inbound_at") or "",
        }]
    return messages[-12:]


def _fetch_chatwoot_messages(conversation_id, *, environ=None):
    source = environ if environ is not None else os.environ
    conversation_id = _clean(conversation_id, 100)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not conversation_id or not token:
        return []
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    url = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
    req = urllib_request.Request(url, headers={"api_access_token": token})
    try:
        with urllib_request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), list) else data.get("messages")
    return [_message_snapshot(item) for item in (payload if isinstance(payload, list) else [])][-12:]


def _message_snapshot(item):
    item = item if isinstance(item, dict) else {}
    message_type = item.get("message_type")
    if message_type in {0, "incoming"}:
        role = "customer"
    elif message_type in {1, "outgoing"}:
        role = "sam_or_farm"
    else:
        role = "system"
    sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
    return {
        "role": role,
        "content": _clean(item.get("content") or item.get("message") or item.get("text"), 1200),
        "message_id": _clean(item.get("id") or item.get("message_id"), 100),
        "sender": _clean(sender.get("name") or sender.get("type"), 120),
        "created_at": _clean(item.get("created_at") or item.get("timestamp"), 80),
    }


def _active_lead_context(conversation_id):
    result, status = get_active_sales_lead_by_conversation(conversation_id)
    if status != 200:
        return {}
    lead = result.get("lead") if isinstance(result.get("lead"), dict) else {}
    return {
        "lead_id": lead.get("lead_id", ""),
        "interest": lead.get("interest") if isinstance(lead.get("interest"), dict) else {},
        "latest_event": lead.get("latest_event", ""),
    }


def _conversation_summary(messages, current_message):
    usable = [m for m in messages if m.get("content")]
    if not usable:
        return _clean(current_message, 500)
    return " | ".join(f"{m.get('role')}: {m.get('content')}" for m in usable[-6:])[:1600]


def _business_rules(knowledge):
    meat = meat_sales_knowledge(knowledge or {})
    return {
        "payment_rule": meat.get("payment_rule") or meat.get("pilot_payment_rule") or "For meat sales we use EFT only for now.",
        "deposit_rule": meat.get("deposit_rule") or "Deposit may only be requested through the approved payment gate.",
        "pop_rule": meat.get("pop_explanation") or "POP is useful but money is not confirmed until it reflects in the bank.",
        "price_rule": "Never invent prices. Use backend quote/document gates only.",
        "booking_rule": "Never confirm a final booking, stock reservation, slaughter, butcher, or delivery slot without the backend gate.",
        "tone_rule": "Warm, human, concise, useful, not pushy.",
    }


def _context_quality(packet):
    source = packet.get("source_context") if isinstance(packet.get("source_context"), dict) else {}
    lead = packet.get("lead") if isinstance(packet.get("lead"), dict) else {}
    conversation = packet.get("conversation") if isinstance(packet.get("conversation"), dict) else {}
    return {
        "has_campaign_context": bool(source.get("available")),
        "has_lead_context": bool(lead.get("lead_id") or lead.get("interest")),
        "has_recent_messages": bool(conversation.get("recent_messages")),
        "has_farm_knowledge": bool(((packet.get("farm_knowledge") or {}).get("public_profile") or {}).get("farm_name")),
    }


def _sales_lane_from_campaign(campaign, opportunity, attrs):
    text = " ".join([
        _clean(opportunity.get("sales_lane"), 100),
        _clean(campaign.get("campaign_title"), 160),
        _clean(opportunity.get("product_focus"), 200),
        _clean(attrs.get("sales_lane"), 80),
    ]).lower()
    if re.search(r"\b(meat|pork|freezer|carcass|cut)\b", text):
        return "meat_preorder"
    return _clean(opportunity.get("sales_lane") or attrs.get("sales_lane"), 80)


def _product_focus_from_campaign(campaign, opportunity, draft, attrs):
    for value in (
        opportunity.get("product_focus"),
        draft.get("product_focus"),
        attrs.get("meat_product_focus"),
        attrs.get("product_focus"),
        campaign.get("campaign_title"),
    ):
        cleaned = _clean(value, 220)
        if cleaned:
            return cleaned
    return ""


def _target_area_from_campaign(opportunity, attrs):
    value = opportunity.get("target_area") or opportunity.get("area") or attrs.get("target_area") or attrs.get("meat_delivery_town")
    if isinstance(value, list):
        return ", ".join(_clean(item, 80) for item in value if _clean(item, 80))
    return _clean(value, 220)


def _post_text_from_campaign(draft, outreach_draft, attrs):
    for value in (
        draft.get("post_text"),
        draft.get("facebook_post"),
        draft.get("text"),
        outreach_draft.get("draft_text"),
        attrs.get("source_post_text"),
        attrs.get("post_text"),
    ):
        cleaned = _clean(value, 1600)
        if cleaned:
            return cleaned
    return ""


def _call_to_action_from_campaign(draft, outreach_draft):
    for value in (draft.get("call_to_action"), outreach_draft.get("audience_label")):
        cleaned = _clean(value, 240)
        if cleaned:
            return cleaned
    return "Invite the customer into the right Sam sales path without pressure."


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _clean(value, limit=300):
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]

