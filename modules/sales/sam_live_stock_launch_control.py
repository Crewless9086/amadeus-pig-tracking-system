import hashlib
import json
import os
from datetime import datetime, timezone
from urllib import error as urllib_error
from urllib import request as urllib_request

from services.database_service import DATABASE_URL_ENV
from modules.orders import order_reservation
from modules.sales.sam_live_stock_runtime import (
    CHATWOOT_ACCOUNT_ID_ENV,
    CHATWOOT_BASE_URL_ENV,
    CHATWOOT_TOKEN_ENV,
    CHATWOOT_TOKEN_FALLBACK_ENV,
    OWNER_SEND_ENABLED_ENV,
    build_sam_live_stock_chatwoot_takeover_payload,
    build_sam_live_stock_resolved_cleanup_packet,
    review_sam_live_stock_conversation,
    send_owner_approved_live_stock_reply,
)
from modules.sales.sam_live_stock_sales_pack import prepare_live_stock_sales_pack


TELEGRAM_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_ESCALATION_SEND_ENABLED"
TELEGRAM_NEW_LEAD_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_NEW_LEAD_SEND_ENABLED"
TELEGRAM_OWNER_REVIEW_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED"
TELEGRAM_CLEANUP_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED"
TELEGRAM_BOT_TOKEN_ENV = "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID"
TELEGRAM_BOT_TOKEN_FALLBACK_ENV = "OOM_SAKKIE_TELEGRAM_BOT_TOKEN"
CHATWOOT_TAKEOVER_WRITE_ENABLED_ENV = "SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED"
ORDER_RESERVATION_ENABLED_ENV = "SAM_LIVE_STOCK_ORDER_RESERVATION_ENABLED"
OWNER_CARD_EVENT_SOURCE = "sam_live_stock_owner_card_lifecycle"
OWNER_CARD_ACTIVE_STATES = {"active", "with_owner", "action_failed", "action_claimed"}

AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "calls_chatwoot": False,
    "calls_telegram": False,
    "calls_n8n": False,
    "creates_order": False,
    "creates_quote": False,
    "reserves_stock": False,
    "releases_stock": False,
    "changes_stock": False,
    "writes_farm_data": False,
    "dispatch_enabled": False,
    "customer_public_output_enabled": False,
}


def sam_live_stock_launch_control_policy(environ=None):
    source = environ if environ is not None else os.environ
    return {
        "mode": "sam_live_stock_controlled_launch",
        "conversation_review_persistence": {
            "enabled": bool(str(source.get(DATABASE_URL_ENV, "") or "").strip()),
            "table": "sam_live_stock_conversation_review_events",
            "append_only": True,
        },
        "telegram_escalation": {
            "send_enabled": _truthy(source.get(TELEGRAM_SEND_ENABLED_ENV)),
            "new_lead_send_enabled": _truthy(source.get(TELEGRAM_NEW_LEAD_SEND_ENABLED_ENV)),
            "owner_review_send_enabled": _truthy(source.get(TELEGRAM_OWNER_REVIEW_SEND_ENABLED_ENV)),
            "cleanup_enabled": _truthy(source.get(TELEGRAM_CLEANUP_ENABLED_ENV)),
            "bot_token_configured": bool(_telegram_token(source)),
            "owner_chat_id_configured": bool(_clean(source.get(TELEGRAM_CHAT_ID_ENV), 100)),
        },
        "owner_send": {
            "enabled": _truthy(source.get(OWNER_SEND_ENABLED_ENV)),
            "env": OWNER_SEND_ENABLED_ENV,
        },
        "chatwoot_takeover": {
            "write_enabled": _truthy(source.get(CHATWOOT_TAKEOVER_WRITE_ENABLED_ENV)),
            "env": CHATWOOT_TAKEOVER_WRITE_ENABLED_ENV,
        },
        "order_reservation": {
            "enabled": _truthy(source.get(ORDER_RESERVATION_ENABLED_ENV)),
            "env": ORDER_RESERVATION_ENABLED_ENV,
            "rule": "Only reserve/release existing order lines with assigned Pig_ID after owner/operator approval.",
        },
        **AUTHORITY_FLAGS,
    }


def build_sam_live_stock_review_event(inbound, facts, decision, review=None, *, event_source="chatwoot_inbound"):
    inbound = inbound if isinstance(inbound, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    review = review if isinstance(review, dict) else review_sam_live_stock_conversation(inbound, facts, decision)
    event = {
        "review_event_id": _stable_id("SAM-LIVE-REVIEW", [
            inbound.get("conversation_id"),
            inbound.get("message_id"),
            inbound.get("content"),
            review.get("score"),
        ]),
        "chatwoot_conversation_id": _clean(inbound.get("conversation_id"), 120),
        "chatwoot_message_id": _clean(inbound.get("message_id"), 120),
        "customer_name": _clean(inbound.get("customer_name"), 120),
        "channel": _clean(inbound.get("channel") or "chatwoot", 80),
        "source_agent": "sam_live_stock_backend",
        "event_source": _clean(event_source, 80),
        "customer_message_excerpt": _clean(inbound.get("content"), 500),
        "sam_reply_excerpt": _clean_multiline(decision.get("suggested_reply_text"), 1800),
        "score": int(review.get("score") or 0),
        "confidence_target": int(review.get("confidence_target") or 96),
        "safe_to_send": bool(review.get("safe_to_send")),
        "owner_send_required": bool(review.get("owner_send_required")),
        "no_reply_recommended": bool(review.get("no_reply_recommended")),
        "escalation_required": bool(review.get("escalation_required")),
        "conversation_mode_recommendation": _clean(review.get("conversation_mode_recommendation") or "AUTO", 20),
        "recommended_action": _clean(review.get("recommended_action"), 120),
        "review_json": review,
        "facts_json": facts,
        "decision_json": decision,
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_telegram": False,
        "creates_order": False,
        "reserves_stock": False,
        "changes_stock": False,
        "writes_farm_data": False,
    }
    return event


def build_sam_live_stock_delivery_outcome_event(claim, outcome):
    claim = claim if isinstance(claim, dict) else {}
    outcome = outcome if isinstance(outcome, dict) else {}
    claim_id = _clean(claim.get("review_event_id"), 120)
    delivery_status = _clean(outcome.get("delivery_status"), 80)
    event = build_sam_live_stock_review_event({}, {}, {}, {
        "score": 0, "safe_to_send": False, "recommended_action": "automatic_retry_prohibited",
    }, event_source="sam_live_stock_autoreply_delivery_outcome")
    event["review_event_id"] = _stable_id("SAM-LIVE-DELIVERY", [claim_id, delivery_status])
    event["recommended_action"] = "automatic_retry_prohibited"
    event["review_json"] = {
        "delivery_status": delivery_status,
        "claim_reference_hash": hashlib.sha256(claim_id.encode("utf-8", errors="ignore")).hexdigest()[:24],
        "claim_acquired": claim.get("created") is True,
        "chatwoot_confirmed": outcome.get("chatwoot_confirmed") is True,
        "automatic_retry_prohibited": True,
        "error_type": _clean(outcome.get("error_type"), 80),
        "status_code": outcome.get("status_code") if isinstance(outcome.get("status_code"), int) else None,
        "contains_configured_identity_values": False,
        "contains_secret_values": False,
    }
    event["customer_message_excerpt"] = ""
    event["sam_reply_excerpt"] = ""
    event["facts_json"] = {}
    event["decision_json"] = {}
    return event


def build_sam_live_stock_owner_card_event(event, card, state, action=""):
    """Build append-only card identity/lifecycle evidence using the existing review rail."""
    event = event if isinstance(event, dict) else {}
    card = card if isinstance(card, dict) else {}
    conversation_id = _clean(event.get("chatwoot_conversation_id") or card.get("conversation_id"), 120)
    chat_id = _clean(card.get("telegram_chat_id"), 100)
    message_id = _clean(card.get("telegram_message_id"), 100)
    state = _clean(state, 40).lower()
    action = _clean(action, 80).lower()
    evidence = build_sam_live_stock_review_event(
        {"conversation_id": conversation_id}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "owner_card_lifecycle"},
        event_source=OWNER_CARD_EVENT_SOURCE,
    )
    evidence["review_event_id"] = _stable_id(
        "SAM-LIVE-CARD", [conversation_id, chat_id, message_id, state, action, event.get("review_event_id")]
    )
    evidence["recommended_action"] = action or "owner_card_lifecycle"
    evidence["review_json"] = {
        "owner_card": {
            "conversation_id": conversation_id,
            "telegram_chat_id": chat_id,
            "telegram_message_id": message_id,
            "state": state,
            "action": action,
            "exact_message_required": True,
        }
    }
    evidence["decision_json"] = {}
    evidence["facts_json"] = {}
    evidence["customer_message_excerpt"] = ""
    evidence["sam_reply_excerpt"] = ""
    return evidence


def get_active_sam_live_stock_owner_card(conversation_id, database_url=None):
    """Recover the exact active Telegram message identity; uncertain storage fails closed."""
    conversation_id = _clean(conversation_id, 120)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not conversation_id:
        return {"success": False, "status": "conversation_id_required", "card": {}, **AUTHORITY_FLAGS}, 400
    if not database_url:
        return {"success": False, "status": "database_url_not_configured", "card": {}, **AUTHORITY_FLAGS}, 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select review_json
                    from public.sam_live_stock_conversation_review_events
                    where chatwoot_conversation_id = %s
                      and event_source = %s
                    order by created_at desc, review_event_id desc
                    limit 1
                    """,
                    (conversation_id, OWNER_CARD_EVENT_SOURCE),
                )
                row = cursor.fetchone()
        if not row:
            return {"success": True, "status": "sam_live_stock_owner_card_not_found", "card": {}, **AUTHORITY_FLAGS}, 200
        review_json = _json_value(row[0])
        card = review_json.get("owner_card") if isinstance(review_json.get("owner_card"), dict) else {}
        if card.get("state") not in OWNER_CARD_ACTIVE_STATES:
            card = {}
        return {"success": True, "status": "sam_live_stock_owner_card_loaded", "card": card, **AUTHORITY_FLAGS}, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_owner_card_load_failed", "error": _clean(str(exc), 240), "card": {}, **AUTHORITY_FLAGS}, 500


def record_sam_live_stock_review_event(event, database_url=None):
    event = event if isinstance(event, dict) else {}
    params = _review_event_params(event)
    if not params["review_event_id"]:
        params["review_event_id"] = _stable_id("SAM-LIVE-REVIEW", [params.get("chatwoot_conversation_id"), params.get("customer_message_excerpt")])
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "database_url_not_configured", "event": params, **AUTHORITY_FLAGS}, 503
    try:
        import psycopg
    except ImportError:
        return {"success": False, "status": "psycopg_dependency_missing", "event": params, **AUTHORITY_FLAGS}, 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.sam_live_stock_conversation_review_events (
                        review_event_id,
                        chatwoot_conversation_id,
                        chatwoot_message_id,
                        customer_name,
                        channel,
                        source_agent,
                        event_source,
                        customer_message_excerpt,
                        sam_reply_excerpt,
                        score,
                        confidence_target,
                        safe_to_send,
                        owner_send_required,
                        no_reply_recommended,
                        escalation_required,
                        conversation_mode_recommendation,
                        recommended_action,
                        review_json,
                        facts_json,
                        decision_json,
                        applies_learning_now,
                        changes_prompt_now,
                        changes_runtime_now,
                        sends_customer_message,
                        calls_chatwoot,
                        calls_telegram,
                        creates_order,
                        reserves_stock,
                        changes_stock,
                        writes_farm_data
                    )
                    values (
                        %(review_event_id)s,
                        %(chatwoot_conversation_id)s,
                        %(chatwoot_message_id)s,
                        %(customer_name)s,
                        %(channel)s,
                        %(source_agent)s,
                        %(event_source)s,
                        %(customer_message_excerpt)s,
                        %(sam_reply_excerpt)s,
                        %(score)s,
                        %(confidence_target)s,
                        %(safe_to_send)s,
                        %(owner_send_required)s,
                        %(no_reply_recommended)s,
                        %(escalation_required)s,
                        %(conversation_mode_recommendation)s,
                        %(recommended_action)s,
                        %(review_json)s::jsonb,
                        %(facts_json)s::jsonb,
                        %(decision_json)s::jsonb,
                        %(applies_learning_now)s,
                        %(changes_prompt_now)s,
                        %(changes_runtime_now)s,
                        %(sends_customer_message)s,
                        %(calls_chatwoot)s,
                        %(calls_telegram)s,
                        %(creates_order)s,
                        %(reserves_stock)s,
                        %(changes_stock)s,
                        %(writes_farm_data)s
                    )
                    on conflict (review_event_id) do nothing
                    """,
                    params,
                )
                created = cursor.rowcount == 1
                cursor.execute(
                    """
                    select count(*) from public.sam_live_stock_conversation_review_events
                    where chatwoot_conversation_id = %(chatwoot_conversation_id)s
                    """,
                    params,
                )
                conversation_event_count = int((cursor.fetchone() or [0])[0] or 0)
        return {
            "success": True,
            "status": "sam_live_stock_review_event_recorded" if created else "sam_live_stock_review_event_already_recorded",
            "review_event_id": params["review_event_id"],
            "created": created,
            "chatwoot_conversation_id": params["chatwoot_conversation_id"],
            "conversation_event_count": conversation_event_count,
            **AUTHORITY_FLAGS,
        }, 201 if created else 200
    except Exception as exc:
        return {
            "success": False,
            "status": "sam_live_stock_review_event_write_failed",
            "error_type": exc.__class__.__name__,
            "error": _clean(str(exc), 240),
            "review_event_id": params["review_event_id"],
            **AUTHORITY_FLAGS,
        }, 500


def get_sam_live_stock_review_event(review_event_id, database_url=None):
    review_event_id = _clean(review_event_id, 120)
    if not review_event_id:
        return {"success": False, "status": "review_event_id_required", **AUTHORITY_FLAGS}, 400
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "database_url_not_configured", **AUTHORITY_FLAGS}, 503
    try:
        import psycopg
    except ImportError:
        return {"success": False, "status": "psycopg_dependency_missing", **AUTHORITY_FLAGS}, 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        review_event_id,
                        chatwoot_conversation_id,
                        chatwoot_message_id,
                        customer_name,
                        channel,
                        event_source,
                        customer_message_excerpt,
                        sam_reply_excerpt,
                        score,
                        confidence_target,
                        safe_to_send,
                        owner_send_required,
                        no_reply_recommended,
                        escalation_required,
                        conversation_mode_recommendation,
                        recommended_action,
                        review_json,
                        facts_json,
                        decision_json,
                        created_at
                    from public.sam_live_stock_conversation_review_events
                    where review_event_id = %s
                    limit 1
                    """,
                    (review_event_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "sam_live_stock_review_event_not_found", "review_event_id": review_event_id, **AUTHORITY_FLAGS}, 404
                columns = [column.name for column in cursor.description]
        event = dict(zip(columns, row))
        for key in ("review_json", "facts_json", "decision_json"):
            event[key] = _json_value(event.get(key))
        return {"success": True, "status": "sam_live_stock_review_event_loaded", "review_event_id": review_event_id, "event": event, **AUTHORITY_FLAGS}, 200
    except Exception as exc:
        return {
            "success": False,
            "status": "sam_live_stock_review_event_load_failed",
            "error_type": exc.__class__.__name__,
            "error": _clean(str(exc), 240),
            "review_event_id": review_event_id,
            **AUTHORITY_FLAGS,
        }, 500


def get_latest_sam_live_stock_review_event_for_conversation(conversation_id, database_url=None):
    conversation_id = _clean(conversation_id, 120)
    if not conversation_id:
        return {"success": False, "status": "chatwoot_conversation_id_required", **AUTHORITY_FLAGS}, 400
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "database_url_not_configured", **AUTHORITY_FLAGS}, 503
    try:
        import psycopg
    except ImportError:
        return {"success": False, "status": "psycopg_dependency_missing", **AUTHORITY_FLAGS}, 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        review_event_id,
                        chatwoot_conversation_id,
                        chatwoot_message_id,
                        customer_name,
                        channel,
                        event_source,
                        customer_message_excerpt,
                        sam_reply_excerpt,
                        score,
                        confidence_target,
                        safe_to_send,
                        owner_send_required,
                        no_reply_recommended,
                        escalation_required,
                        conversation_mode_recommendation,
                        recommended_action,
                        review_json,
                        facts_json,
                        decision_json,
                        created_at
                    from public.sam_live_stock_conversation_review_events
                    where chatwoot_conversation_id = %s
                    order by created_at desc
                    limit 1
                    """,
                    (conversation_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "sam_live_stock_review_event_not_found", "chatwoot_conversation_id": conversation_id, **AUTHORITY_FLAGS}, 404
                columns = [column.name for column in cursor.description]
        event = dict(zip(columns, row))
        for key in ("review_json", "facts_json", "decision_json"):
            event[key] = _json_value(event.get(key))
        return {
            "success": True,
            "status": "sam_live_stock_latest_review_event_loaded",
            "chatwoot_conversation_id": conversation_id,
            "review_event_id": event.get("review_event_id"),
            "event": event,
            **AUTHORITY_FLAGS,
        }, 200
    except Exception as exc:
        return {
            "success": False,
            "status": "sam_live_stock_review_event_load_failed",
            "error_type": exc.__class__.__name__,
            "error": _clean(str(exc), 240),
            "chatwoot_conversation_id": conversation_id,
            **AUTHORITY_FLAGS,
        }, 500


def _canonical_owner_card_keyboard(callback_id, conversation_id, reply, *, links=None, allow_send=True):
    links = links if isinstance(links, dict) else {}
    callback_id = _clean(callback_id, 120) or _clean(conversation_id, 100)
    keyboard = []
    if allow_send and _clean_multiline(reply, 1800):
        keyboard.append([{"text": "Send Reply", "callback_data": f"sam_live_card_send:{callback_id}"}])
    chatwoot_url = _clean(links.get("chatwoot_conversation_url"), 500)
    open_button = {"text": "Open Chatwoot", "url": chatwoot_url} if chatwoot_url else {
        "text": "Open Chatwoot", "callback_data": f"sam_live_card_open:{callback_id}"
    }
    keyboard.append([open_button, {"text": "Keep With Me", "callback_data": f"sam_live_card_keep:{callback_id}"}])
    keyboard.append([{"text": "No Reply — Done", "callback_data": f"sam_live_card_no_reply:{callback_id}"}])
    keyboard.append([{"text": "Done — Return to SAM", "callback_data": f"sam_live_card_done:{callback_id}"}])
    return keyboard


def build_sam_live_stock_new_lead_packet(event, *, links=None, environ=None):
    event = event if isinstance(event, dict) else {}
    facts = event.get("facts_json") if isinstance(event.get("facts_json"), dict) else {}
    review = event.get("review_json") if isinstance(event.get("review_json"), dict) else {}
    decision = event.get("decision_json") if isinstance(event.get("decision_json"), dict) else {}
    links = links if isinstance(links, dict) else {}
    source = environ if environ is not None else os.environ
    conversation_id = _clean(event.get("chatwoot_conversation_id"), 100)
    review_event_id = _clean(event.get("review_event_id"), 120) or conversation_id
    if not links.get("chatwoot_conversation_url"):
        links = {**links, "chatwoot_conversation_url": _chatwoot_conversation_url(conversation_id, source)}
    parts = [
        "SAM Live - New lead",
        f"Customer: {_clean(event.get('customer_name') or 'Unknown', 80)}",
        f"Conversation: {conversation_id or 'unknown'}",
        f"Wants: {_lead_fact_summary(facts)}",
    ]
    reply = _clean_multiline(event.get("sam_reply_excerpt") or decision.get("suggested_reply_text"), 400)
    parts.extend([
        "",
        "Customer message:",
        _clean_multiline(event.get("customer_message_excerpt"), 500) or "No customer message captured.",
    ])
    if reply:
        parts.extend(["", "Suggested reply:", reply])
    if links.get("availability_url"):
        parts.append(f"Stock truth: {links['availability_url']}")
    if links.get("open_intakes_url"):
        parts.append(f"Open intakes: {links['open_intakes_url']}")
    return {
        "version": "sam_live_stock_new_lead_packet_v1",
        "type": "new_lead",
        "conversation_id": conversation_id,
        "telegram_packet": {
            "text": "\n".join(parts),
            "reply_markup": {"inline_keyboard": _canonical_owner_card_keyboard(
                review_event_id, conversation_id, "", links=links, allow_send=False
            )},
        },
        **AUTHORITY_FLAGS,
    }


def build_sam_live_stock_owner_review_packet(event, *, links=None, environ=None):
    event = event if isinstance(event, dict) else {}
    facts = event.get("facts_json") if isinstance(event.get("facts_json"), dict) else {}
    decision = event.get("decision_json") if isinstance(event.get("decision_json"), dict) else {}
    review = event.get("review_json") if isinstance(event.get("review_json"), dict) else {}
    links = links if isinstance(links, dict) else {}
    source = environ if environ is not None else os.environ
    review_event_id = _clean(event.get("review_event_id"), 120)
    conversation_id = _clean(event.get("chatwoot_conversation_id"), 100)
    reply = _clean_multiline(decision.get("suggested_reply_text") or event.get("sam_reply_excerpt"), 1800)
    score = int(event.get("score") or 0)
    target = int(event.get("confidence_target") or 96)
    parts = [
        f"SAM Live - {_clean(event.get('customer_name') or 'Unknown customer', 80)}",
        f"Conversation: {conversation_id or 'unknown'}",
        f"Intent: {_owner_card_intent_summary(decision)}",
        f"Message type: {_clean(facts.get('message_intent') or 'unclear', 80).replace('_', ' ')}",
        f"Language: {_clean(facts.get('customer_language') or 'unknown', 60).replace('_', ' ')}",
        f"Stage: {_owner_card_stage_summary(decision)}",
        f"Open order/quote: {_owner_card_open_order_quote_summary(decision)}",
        f"Next: {_owner_card_next_action_summary(decision)}",
        f"Prepared: {_owner_card_prepared_action_summary(decision)}",
        f"Wants: {_owner_card_fact_summary(facts)}",
        f"Stock: {_owner_card_stock_summary(decision)}",
        f"Price: {_owner_card_price_summary(decision)}",
        f"Missing: {_owner_card_missing_summary(decision)}",
        f"Draft source: {_owner_card_reply_source_summary(decision)}",
        f"Policy: learning {'on' if _truthy(source.get('SAM_LIVE_STOCK_OWNER_EXAMPLE_RETRIEVAL_ENABLED', '1')) else 'off'}; meat {'open' if _truthy(source.get('SAM_MEAT_PUBLIC_OFFER_ENABLED')) else 'locked'}",
    ]
    authority_decision = _owner_authority_decision_summary(review)
    if authority_decision:
        parts.append(f"Owner decision needed: {authority_decision}")
    routine_delivery = decision.get("routine_reply_delivery") if isinstance(decision.get("routine_reply_delivery"), dict) else {}
    if routine_delivery.get("sent") is True:
        parts.append("Customer reply: already sent by SAM; do not approve a duplicate send")
    flags = _owner_card_flags(event, review, decision)
    understanding = decision.get("input_understanding") if isinstance(decision.get("input_understanding"), dict) else {}
    if understanding.get("requires_media_review"):
        parts.append("Media: owner review required; media-derived facts are not trusted")
    if flags:
        parts.append(f"Flags: {flags}")
    if score < target:
        parts.append(f"Confidence: {score}/{target}")
    parts.extend([
        "",
        "Customer:",
        _clean_multiline(event.get("customer_message_excerpt"), 500) or "No customer message captured.",
        "",
        "Draft reply:",
        reply or "No reply recommended.",
    ])
    if links.get("sales_availability"):
        parts.append(f"Stock truth: {links['sales_availability']}")
    if links.get("open_intakes_api"):
        parts.append(f"Open intakes: {links['open_intakes_api']}")
    keyboard = []
    if review_event_id and reply and routine_delivery.get("sent") is not True:
        keyboard.append([{"text": "Send Reply", "callback_data": f"sam_live_card_send:{review_event_id}"}])
    chatwoot_url = (
        _clean(links.get("chatwoot_conversation_url"), 500)
        or _chatwoot_conversation_url(conversation_id, source)
    )
    edit_button = {"text": "Open Chatwoot", "url": chatwoot_url} if chatwoot_url else {
        "text": "Open Chatwoot",
        "callback_data": f"sam_live_review_edit:{review_event_id or conversation_id}",
    }
    keyboard.append([
        edit_button,
        {"text": "Keep With Me", "callback_data": f"sam_live_card_keep:{review_event_id or conversation_id}"},
    ])
    keyboard.append([{"text": "No Reply — Done", "callback_data": f"sam_live_card_no_reply:{review_event_id or conversation_id}"}])
    prepared_buttons = _owner_card_prepared_action_buttons(decision, review_event_id or conversation_id)
    keyboard.extend(prepared_buttons)
    keyboard.append([{"text": "Done — Return to SAM", "callback_data": f"sam_live_card_done:{review_event_id or conversation_id}"}])
    return {
        "version": "sam_live_stock_owner_review_packet_v2",
        "type": "owner_review_send_candidate",
        "review_event_id": review_event_id,
        "conversation_id": conversation_id,
        "telegram_packet": {
            "text": "\n".join(parts),
            "reply_markup": {"inline_keyboard": keyboard},
        },
        **AUTHORITY_FLAGS,
    }


def send_sam_live_stock_new_lead_telegram(event, *, environ=None, telegram_sender=None, telegram_editor=None, links=None, active_card_loader=None, evidence_recorder=None):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_new_lead_packet(event, links=links, environ=source)
    if not _truthy(source.get(TELEGRAM_NEW_LEAD_SEND_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_new_lead_telegram_send_disabled", "packet": packet, **AUTHORITY_FLAGS}, 409
    return _deliver_sam_live_stock_owner_card(event, packet["telegram_packet"], source, telegram_sender, telegram_editor, active_card_loader, evidence_recorder, "sam_live_stock_new_lead_telegram_sent")


def send_sam_live_stock_owner_review_telegram(event, *, environ=None, telegram_sender=None, telegram_editor=None, links=None, active_card_loader=None, evidence_recorder=None):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_owner_review_packet(event, links=links, environ=source)
    if not _truthy(source.get(TELEGRAM_OWNER_REVIEW_SEND_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_owner_review_telegram_send_disabled", "packet": packet, **AUTHORITY_FLAGS}, 409
    return _deliver_sam_live_stock_owner_card(event, packet["telegram_packet"], source, telegram_sender, telegram_editor, active_card_loader, evidence_recorder, "sam_live_stock_owner_review_telegram_sent")


def _deliver_sam_live_stock_owner_card(event, telegram_packet, source, telegram_sender, telegram_editor, active_card_loader, evidence_recorder, success_status):
    """Edit one exact active card, or send one new card and append its identity."""
    event = event if isinstance(event, dict) else {}
    conversation_id = _clean(event.get("chatwoot_conversation_id"), 120)
    loader = active_card_loader or (
        (lambda _conversation_id: ({"success": True, "status": "injected_sender_no_active_card", "card": {}}, 200))
        if telegram_sender is not None else get_active_sam_live_stock_owner_card
    )
    loaded, load_status = loader(conversation_id)
    if load_status >= 500 or not loaded.get("success"):
        return {"success": False, "status": "sam_live_stock_owner_card_identity_unavailable", "card_lookup": loaded, **AUTHORITY_FLAGS}, 503
    active = loaded.get("card") if isinstance(loaded.get("card"), dict) else {}
    if active and not active.get("telegram_message_id"):
        return {"success": False, "status": "sam_live_stock_owner_card_delivery_outcome_unknown", "automatic_retry_prohibited": True, "card": active, **AUTHORITY_FLAGS}, 409
    chat_id = _clean(active.get("telegram_chat_id") or source.get(TELEGRAM_CHAT_ID_ENV), 100)
    token = _telegram_token(source)
    if not token:
        return {"success": False, "status": "sam_live_stock_telegram_token_required", **AUTHORITY_FLAGS}, 503
    if not chat_id:
        return {"success": False, "status": "sam_live_stock_telegram_owner_chat_required", **AUTHORITY_FLAGS}, 503
    text = _clean_multiline(telegram_packet.get("text"), 3500)
    markup = telegram_packet.get("reply_markup") if isinstance(telegram_packet.get("reply_markup"), dict) else {}
    recorder = evidence_recorder or (
        (lambda _evidence: ({"success": True, "status": "injected_evidence", "created": True}, 200))
        if telegram_sender is not None else record_sam_live_stock_review_event
    )
    if not active:
        claim_card = {"conversation_id": conversation_id, "telegram_chat_id": chat_id, "telegram_message_id": ""}
        claimed, claim_status = recorder(build_sam_live_stock_owner_card_event(event, claim_card, "action_claimed", "card_delivery_claim"))
        if claim_status >= 400 or not claimed.get("success"):
            return {"success": False, "status": "sam_live_stock_owner_card_delivery_claim_failed", "evidence": claimed, **AUTHORITY_FLAGS}, 503
        if claimed.get("created") is False:
            return {"success": False, "status": "sam_live_stock_owner_card_duplicate_delivery_withheld", "automatic_retry_prohibited": True, **AUTHORITY_FLAGS}, 409
    try:
        if active.get("telegram_message_id"):
            editor = telegram_editor or _telegram_edit_message
            telegram = editor(token, chat_id, active["telegram_message_id"], text, markup)
            status = "sam_live_stock_owner_card_edited"
            message_id = _clean(active["telegram_message_id"], 100)
        else:
            sender = telegram_sender or _telegram_send_message
            telegram = sender(token, chat_id, text, markup)
            result = telegram.get("result") if isinstance(telegram, dict) and isinstance(telegram.get("result"), dict) else telegram
            message_id = _clean(result.get("message_id") if isinstance(result, dict) else "", 100)
            if not message_id and telegram_sender is not None:
                message_id = "injected-test-message"
            if not message_id:
                return {"success": False, "status": "sam_live_stock_owner_card_message_id_missing", "telegram": telegram, **AUTHORITY_FLAGS}, 502
            status = success_status
        card = {"conversation_id": conversation_id, "telegram_chat_id": chat_id, "telegram_message_id": message_id}
        evidence = build_sam_live_stock_owner_card_event(event, card, "active", "card_updated" if active else "card_created")
        recorded, record_status = recorder(evidence)
        if record_status >= 400 or not recorded.get("success"):
            return {"success": False, "status": "sam_live_stock_owner_card_identity_record_failed", "telegram": telegram, "evidence": recorded, **AUTHORITY_FLAGS, "calls_telegram": True}, 502
        return {"success": True, "status": status, "telegram": telegram, "card": card, "evidence": recorded, **AUTHORITY_FLAGS, "calls_telegram": True}, 200
    except Exception as exc:
        recorder(build_sam_live_stock_owner_card_event(event, {"conversation_id": conversation_id, "telegram_chat_id": chat_id, "telegram_message_id": ""}, "action_failed", "card_delivery_unknown"))
        return {"success": False, "status": "sam_live_stock_owner_card_delivery_failed", "error": _clean(str(exc), 240), **AUTHORITY_FLAGS}, 502


def send_sam_live_stock_telegram_escalation(packet, *, environ=None, telegram_sender=None):
    source = environ if environ is not None else os.environ
    packet = packet if isinstance(packet, dict) else {}
    telegram_packet = packet.get("telegram_packet") if isinstance(packet.get("telegram_packet"), dict) else packet
    if not _truthy(source.get(TELEGRAM_SEND_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_telegram_send_disabled", "packet": telegram_packet, **AUTHORITY_FLAGS}, 409
    return _send_sam_live_stock_telegram_packet(telegram_packet, source, telegram_sender, "sam_live_stock_telegram_escalation_sent")


def _send_sam_live_stock_telegram_packet(telegram_packet, source, telegram_sender, success_status):
    if not _truthy(source.get(TELEGRAM_SEND_ENABLED_ENV)):
        if success_status not in {"sam_live_stock_new_lead_telegram_sent", "sam_live_stock_owner_review_telegram_sent"}:
            return {"success": False, "status": "sam_live_stock_telegram_send_disabled", "packet": telegram_packet, **AUTHORITY_FLAGS}, 409
    chat_id = _clean(source.get(TELEGRAM_CHAT_ID_ENV), 100)
    token = _telegram_token(source)
    if not token:
        return {"success": False, "status": "sam_live_stock_telegram_token_required", **AUTHORITY_FLAGS}, 503
    if not chat_id:
        return {"success": False, "status": "sam_live_stock_telegram_owner_chat_required", **AUTHORITY_FLAGS}, 503
    text = _clean_multiline(telegram_packet.get("text"), 3500)
    if not text:
        return {"success": False, "status": "telegram_text_required", **AUTHORITY_FLAGS}, 400
    sender = telegram_sender or _telegram_send_message
    try:
        sent = sender(token, chat_id, text, telegram_packet.get("reply_markup") if isinstance(telegram_packet.get("reply_markup"), dict) else {})
        return {"success": True, "status": success_status, "telegram": sent, **AUTHORITY_FLAGS, "calls_telegram": True}, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_telegram_escalation_failed", "error": _clean(str(exc), 240), **AUTHORITY_FLAGS}, 502


def delete_sam_live_stock_telegram_escalation(escalation_id, telegram_chat_id, telegram_message_id, *, environ=None, telegram_deleter=None):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_resolved_cleanup_packet(escalation_id, telegram_chat_id, telegram_message_id)
    if not _truthy(source.get(TELEGRAM_CLEANUP_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_telegram_cleanup_disabled", "cleanup_packet": packet, **AUTHORITY_FLAGS}, 409
    if not packet.get("delete_allowed"):
        return {"success": False, "status": "telegram_cleanup_target_required", "cleanup_packet": packet, **AUTHORITY_FLAGS}, 400
    token = _telegram_token(source)
    if not token:
        return {"success": False, "status": "sam_live_stock_telegram_token_required", "cleanup_packet": packet, **AUTHORITY_FLAGS}, 503
    deleter = telegram_deleter or _telegram_delete_message
    try:
        deleted = deleter(token, packet["telegram_chat_id"], packet["telegram_message_id"])
        return {"success": True, "status": "sam_live_stock_telegram_escalation_deleted", "telegram": deleted, "cleanup_packet": packet, **AUTHORITY_FLAGS, "calls_telegram": True}, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_telegram_delete_failed", "error": _clean(str(exc), 240), "cleanup_packet": packet, **AUTHORITY_FLAGS}, 502


def apply_sam_live_stock_chatwoot_takeover(conversation_id, mode="HUMAN", reason="", *, environ=None, chatwoot_writer=None):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_chatwoot_takeover_payload(conversation_id, mode=mode, reason=reason)
    if not _truthy(source.get(CHATWOOT_TAKEOVER_WRITE_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_chatwoot_takeover_write_disabled", "packet": packet, **AUTHORITY_FLAGS}, 409
    if not packet["conversation_id"]:
        return {"success": False, "status": "conversation_id_required", "packet": packet, **AUTHORITY_FLAGS}, 400
    writer = chatwoot_writer or _chatwoot_write_custom_attributes
    try:
        result = writer(packet["conversation_id"], packet["custom_attributes"], source)
        return {"success": True, "status": "sam_live_stock_chatwoot_takeover_written", "packet": packet, "chatwoot": result, **AUTHORITY_FLAGS, "calls_chatwoot": True}, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_chatwoot_takeover_failed", "error": _clean(str(exc), 240), "packet": packet, **AUTHORITY_FLAGS}, 502


def _process_canonical_owner_card_action(action, review_event_id, event, message, payload, *, environ, chatwoot_sender, chatwoot_writer, telegram_deleter, telegram_editor, evidence_recorder):
    conversation_id = _clean(event.get("chatwoot_conversation_id"), 100)
    chat_id = _clean(payload.get("telegram_chat_id"), 100)
    message_id = _clean(payload.get("telegram_message_id"), 100)
    card = {"conversation_id": conversation_id, "telegram_chat_id": chat_id, "telegram_message_id": message_id}
    if action == "card_open":
        return {"success": True, "status": "sam_live_stock_owner_card_open_no_mutation", "action": action, "conversation_id": conversation_id, "card": card, **AUTHORITY_FLAGS}, 200
    if not chat_id or not message_id:
        return {"success": False, "status": "sam_live_stock_exact_owner_card_required", "action": action, "card": card, **AUTHORITY_FLAGS}, 400

    recorder = evidence_recorder or record_sam_live_stock_review_event
    claim = build_sam_live_stock_owner_card_event(event, card, "action_claimed", action)
    claimed, claim_status = recorder(claim)
    if claim_status >= 400 or not claimed.get("success"):
        return {"success": False, "status": "sam_live_stock_owner_card_action_claim_failed", "action": action, "evidence": claimed, **AUTHORITY_FLAGS}, 503
    if claimed.get("created") is False:
        return {"success": False, "status": "sam_live_stock_owner_card_duplicate_callback_withheld", "action": action, "automatic_retry_prohibited": True, **AUTHORITY_FLAGS}, 409

    if action == "card_keep":
        takeover, takeover_status = apply_sam_live_stock_chatwoot_takeover(
            conversation_id, mode="HUMAN", reason="telegram_keep_with_me",
            environ=environ, chatwoot_writer=chatwoot_writer,
        )
        if takeover_status >= 400 or not takeover.get("success"):
            return _owner_card_failure(event, card, action, "chatwoot_human_failed", takeover, recorder, environ, telegram_editor)
        edited, edit_status = _edit_owner_card_state(card, "With Charl", _with_charl_keyboard(review_event_id), environ, telegram_editor)
        if edit_status >= 400:
            return _owner_card_failure(event, card, action, "telegram_edit_failed", edited, recorder, environ, telegram_editor)
        recorder(build_sam_live_stock_owner_card_event(event, card, "with_owner", action))
        return {"success": True, "status": "sam_live_stock_owner_card_with_charl", "action": action, "card": card, "chatwoot": takeover, "telegram": edited, **AUTHORITY_FLAGS, "calls_chatwoot": True, "calls_telegram": True}, 200

    if action == "card_send":
        sent, sent_status = send_owner_approved_live_stock_reply(
            conversation_id, message, environ=environ, chatwoot_sender=chatwoot_sender,
            owner=payload.get("owner") or "telegram_owner", escalation_id=review_event_id,
        )
        if sent_status >= 400 or not sent.get("success"):
            return _owner_card_failure(event, card, action, "customer_send_failed", sent, recorder, environ, telegram_editor)
    else:
        sent = None

    takeover, takeover_status = apply_sam_live_stock_chatwoot_takeover(
        conversation_id, mode="AUTO", reason="telegram_owner_card_done",
        environ=environ, chatwoot_writer=chatwoot_writer,
    )
    if takeover_status >= 400 or not takeover.get("success"):
        return _owner_card_failure(event, card, action, "chatwoot_auto_failed", takeover, recorder, environ, telegram_editor, customer_send_confirmed=sent is not None)

    deleted, delete_status = delete_sam_live_stock_telegram_escalation(
        review_event_id, chat_id, message_id, environ=environ, telegram_deleter=telegram_deleter,
    )
    if delete_status >= 400 or not deleted.get("success"):
        resolved, resolved_status = _edit_owner_card_state(card, "Resolved", [], environ, telegram_editor)
        if resolved_status >= 400:
            return _owner_card_failure(event, card, action, "telegram_cleanup_failed", deleted, recorder, environ, telegram_editor, customer_send_confirmed=sent is not None)
        deleted = {"success": True, "status": "sam_live_stock_owner_card_resolved_by_edit", "edit": resolved}
    recorder(build_sam_live_stock_owner_card_event(event, card, "resolved", action))
    return {"success": True, "status": "sam_live_stock_owner_card_completed", "action": action, "card": card, "customer_send": sent, "chatwoot": takeover, "telegram_cleanup": deleted, **AUTHORITY_FLAGS, "sends_customer_message": sent is not None, "calls_chatwoot": True, "calls_telegram": True}, 200


def _owner_card_failure(event, card, action, failed_step, detail, recorder, environ, telegram_editor, customer_send_confirmed=False):
    recorder(build_sam_live_stock_owner_card_event(event, card, "action_failed", f"{action}:{failed_step}"))
    _edit_owner_card_state(card, f"Action failed safely: {failed_step}. Card retained; do not repeat a confirmed customer send.", _with_charl_keyboard(event.get("review_event_id") or card.get("conversation_id")), environ, telegram_editor)
    return {"success": False, "status": "sam_live_stock_owner_card_action_failed", "action": action, "failed_step": failed_step, "card_retained": True, "customer_send_confirmed": customer_send_confirmed, "automatic_customer_send_retry_prohibited": True, "detail": detail, **AUTHORITY_FLAGS, "sends_customer_message": customer_send_confirmed}, 502


def _edit_owner_card_state(card, text, keyboard, environ, telegram_editor):
    source = environ if environ is not None else os.environ
    token = _telegram_token(source)
    if not token:
        return {"success": False, "status": "sam_live_stock_telegram_token_required"}, 503
    try:
        result = (telegram_editor or _telegram_edit_message)(token, card["telegram_chat_id"], card["telegram_message_id"], text, {"inline_keyboard": keyboard})
        return {"success": True, "status": "sam_live_stock_owner_card_edited", "telegram": result}, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_owner_card_edit_failed", "error": _clean(str(exc), 240)}, 502


def _with_charl_keyboard(callback_id):
    return [[{"text": "Open Chatwoot", "callback_data": f"sam_live_card_open:{callback_id}"}], [{"text": "Done — Return to SAM", "callback_data": f"sam_live_card_done:{callback_id}"}]]


def process_sam_live_stock_owner_callback(payload, *, environ=None, chatwoot_sender=None, telegram_deleter=None, telegram_editor=None, chatwoot_writer=None, review_event_loader=None, sales_pack_preparer=None, evidence_recorder=None):
    payload = payload if isinstance(payload, dict) else {}
    action = _callback_action(payload.get("callback_data") or payload.get("action"))
    escalation_id = _clean(payload.get("escalation_id") or action.get("escalation_id"), 120)
    review_actions = {
        "review_approve_send",
        "review_edit",
        "review_human",
        "review_close",
        "review_no_reply",
        "review_prepare_draft_order",
        "review_update_draft_order",
        "review_prepare_quote",
        "review_prepare_sales_pack",
        "review_picture_reply",
        "card_send",
        "card_open",
        "card_keep",
        "card_no_reply",
        "card_done",
    }
    if action["action"] in review_actions:
        loaded, load_status = (review_event_loader or get_sam_live_stock_review_event)(escalation_id)
        if load_status >= 400 or not loaded.get("success"):
            return _callback_result(action["action"], loaded, load_status, escalation_id)
        event = loaded.get("event") if isinstance(loaded.get("event"), dict) else {}
        conversation_id = event.get("chatwoot_conversation_id")
        decision_json = _json_value(event.get("decision_json"))
        message = _clean_multiline(decision_json.get("suggested_reply_text") or event.get("sam_reply_excerpt"), 1800)
        legacy_terminal = {
            "review_approve_send": "card_send",
            "review_human": "card_keep",
            "review_no_reply": "card_no_reply",
            "review_close": "card_done",
        }.get(action["action"])
        if legacy_terminal and payload.get("telegram_chat_id") and payload.get("telegram_message_id"):
            return _process_canonical_owner_card_action(
                legacy_terminal, escalation_id, event, message, payload,
                environ=environ, chatwoot_sender=chatwoot_sender,
                chatwoot_writer=chatwoot_writer, telegram_deleter=telegram_deleter,
                telegram_editor=telegram_editor, evidence_recorder=evidence_recorder,
            )
        if action["action"] in {"card_send", "card_open", "card_keep", "card_no_reply", "card_done"}:
            return _process_canonical_owner_card_action(
                action["action"], escalation_id, event, message, payload,
                environ=environ, chatwoot_sender=chatwoot_sender,
                chatwoot_writer=chatwoot_writer, telegram_deleter=telegram_deleter,
                telegram_editor=telegram_editor, evidence_recorder=evidence_recorder,
            )
        if action["action"] in {
            "review_no_reply",
            "review_prepare_draft_order",
            "review_update_draft_order",
            "review_prepare_quote",
            "review_picture_reply",
        }:
            return _prepared_review_callback_result(action["action"], escalation_id, event, decision_json, message), 200
        if action["action"] == "review_prepare_sales_pack":
            packet = decision_json.get("owner_action_packet") if isinstance(decision_json.get("owner_action_packet"), dict) else {}
            order_id = _clean(packet.get("order_id"), 100)
            if not order_id:
                return {
                    "success": False,
                    "status": "sam_live_stock_sales_pack_order_required",
                    "action": action["action"],
                    "review_event_id": escalation_id,
                    **AUTHORITY_FLAGS,
                }, 400
            try:
                prepared = (sales_pack_preparer or prepare_live_stock_sales_pack)(
                    order_id,
                    {"created_by": payload.get("owner") or "telegram_owner"},
                )
            except Exception as exc:
                return {
                    "success": False,
                    "status": "sam_live_stock_sales_pack_prepare_failed",
                    "error": _clean(str(exc), 240),
                    "action": action["action"],
                    "review_event_id": escalation_id,
                    **AUTHORITY_FLAGS,
                }, 500
            return {
                "success": bool(prepared.get("success")),
                "status": prepared.get("status") or "sam_live_stock_sales_pack_prepared",
                "action": action["action"],
                "review_event_id": escalation_id,
                "conversation_id": _clean(conversation_id, 100),
                "sales_pack": prepared,
                "recommended_next": "Review the quote and documents. No customer message was sent.",
                **AUTHORITY_FLAGS,
            }, 200 if prepared.get("success") else 400
        if action["action"] == "review_approve_send":
            send_result, status = send_owner_approved_live_stock_reply(
                conversation_id,
                message,
                environ=environ,
                chatwoot_sender=chatwoot_sender,
                owner=payload.get("owner") or "telegram_owner",
                escalation_id=escalation_id,
            )
            return _callback_result("review_approve_send", send_result, status, escalation_id)
        if action["action"] == "review_edit":
            return {
                "success": True,
                "status": "sam_live_stock_review_edit_required",
                "action": "review_edit",
                "review_event_id": escalation_id,
                "conversation_id": _clean(conversation_id, 100),
                "suggested_reply": message,
                "recommended_next": "Edit/send the reply in Chatwoot, or keep this conversation in HUMAN mode.",
                **AUTHORITY_FLAGS,
            }, 200
        if action["action"] == "review_no_reply":
            return {
                "success": True,
                "status": "sam_live_stock_review_no_reply_needed",
                "action": "review_no_reply",
                "review_event_id": escalation_id,
                "conversation_id": _clean(conversation_id, 100),
                "recommended_next": "No customer reply was sent. Keep this thread closed or continue manually in Chatwoot if the customer writes again.",
                **AUTHORITY_FLAGS,
            }, 200
        if action["action"] == "review_human":
            takeover, status = apply_sam_live_stock_chatwoot_takeover(
                conversation_id,
                mode="HUMAN",
                reason="telegram_owner_review_handoff",
                environ=environ,
                chatwoot_writer=chatwoot_writer,
            )
            return _callback_result("review_human", takeover, status, escalation_id)
        if action["action"] in {"review_prepare_draft_order", "review_prepare_quote", "review_picture_reply"}:
            return _prepared_review_callback_result(action["action"], escalation_id, conversation_id, event, decision_json)
        if action["action"] == "review_close":
            return {
                "success": True,
                "status": "sam_live_stock_review_closed_without_reply",
                "action": "review_close",
                "review_event_id": escalation_id,
                "conversation_id": _clean(conversation_id, 100),
                "recommended_next": "No customer message was sent. Close or continue manually in Chatwoot.",
                **AUTHORITY_FLAGS,
            }, 200
    if action["action"] == "approve_send":
        send_result, status = send_owner_approved_live_stock_reply(
            payload.get("conversation_id"),
            payload.get("message") or payload.get("suggested_response"),
            environ=environ,
            chatwoot_sender=chatwoot_sender,
            owner=payload.get("owner") or "telegram_owner",
            escalation_id=escalation_id,
        )
        return _callback_result("approve_send", send_result, status, escalation_id)
    if action["action"] == "human":
        takeover, status = apply_sam_live_stock_chatwoot_takeover(
            payload.get("conversation_id"),
            mode="HUMAN",
            reason="telegram_owner_handoff",
            environ=environ,
            chatwoot_writer=chatwoot_writer,
        )
        return _callback_result("human", takeover, status, escalation_id)
    if action["action"] == "resolved":
        cleanup, status = delete_sam_live_stock_telegram_escalation(
            escalation_id,
            payload.get("telegram_chat_id") or "",
            payload.get("telegram_message_id") or "",
            environ=environ,
            telegram_deleter=telegram_deleter,
        )
        return _callback_result("resolved", cleanup, status, escalation_id)
    if action["action"] == "close":
        return {
            "success": True,
            "status": "sam_live_stock_escalation_closed_without_reply",
            "action": "close",
            "escalation_id": escalation_id,
            "recommended_next": "Keep Chatwoot in HUMAN mode or manually close the conversation.",
            **AUTHORITY_FLAGS,
        }, 200
    return {"success": False, "status": "unsupported_sam_live_stock_callback", "callback_data": _clean(payload.get("callback_data"), 200), **AUTHORITY_FLAGS}, 400


def build_live_stock_reservation_plan(order_id="", match_packet=None):
    match_packet = match_packet if isinstance(match_packet, dict) else {}
    candidates = match_packet.get("matched_sample") if isinstance(match_packet.get("matched_sample"), list) else []
    return {
        "version": "sam_live_stock_reservation_plan_v1",
        "order_id": _clean(order_id, 100),
        "candidate_pigs": candidates,
        "candidate_count": len(candidates),
        "can_execute_order_line_reservation": bool(_clean(order_id, 100)),
        "owner_gate_required": True,
        "rule": "SAM may recommend candidates. Only owner/operator can reserve/release assigned order lines.",
        **AUTHORITY_FLAGS,
    }


def execute_live_stock_order_reservation(order_id, action="reserve", *, environ=None, reserve_fn=None, release_fn=None):
    source = environ if environ is not None else os.environ
    action = _clean(action, 20).lower()
    order_id = _clean(order_id, 100)
    if not _truthy(source.get(ORDER_RESERVATION_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_order_reservation_disabled", "order_id": order_id, **AUTHORITY_FLAGS}, 409
    if not order_id:
        return {"success": False, "status": "order_id_required", **AUTHORITY_FLAGS}, 400
    try:
        if action == "reserve":
            result = (reserve_fn or order_reservation.reserve_order_lines)(order_id)
            return {"success": bool(result.get("success")), "status": "sam_live_stock_order_lines_reserved", "reservation": result, **AUTHORITY_FLAGS, "reserves_stock": True, "changes_stock": bool(result.get("changed_count"))}, 200
        if action == "release":
            result = (release_fn or order_reservation.release_order_lines)(order_id)
            return {"success": bool(result.get("success")), "status": "sam_live_stock_order_lines_released", "reservation": result, **AUTHORITY_FLAGS, "releases_stock": True, "changes_stock": bool(result.get("changed_count"))}, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_order_reservation_failed", "error": _clean(str(exc), 240), "order_id": order_id, **AUTHORITY_FLAGS}, 502
    return {"success": False, "status": "unsupported_reservation_action", "action": action, **AUTHORITY_FLAGS}, 400


def list_sam_live_stock_open_intakes(limit=25, *, database_url=None):
    try:
        limit = max(1, min(int(limit or 25), 100))
    except (TypeError, ValueError):
        limit = 25
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "database_url_not_configured", "open_intakes": [], **AUTHORITY_FLAGS}, 503
    try:
        import psycopg
    except ImportError:
        return {"success": False, "status": "psycopg_dependency_missing", "open_intakes": [], **AUTHORITY_FLAGS}, 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        intake_id,
                        conversation_id,
                        customer_name,
                        customer_phone_raw,
                        intake_status,
                        collection_location,
                        collection_time_text,
                        quote_requested,
                        order_commitment,
                        missing_fields,
                        next_action,
                        last_customer_message,
                        notes,
                        updated_at,
                        coalesce((
                            select jsonb_agg(jsonb_build_object(
                                'item_key', item.item_key,
                                'quantity', item.quantity,
                                'category', item.category,
                                'weight_range', item.weight_range,
                                'sex', item.sex,
                                'intent_type', item.intent_type
                            ) order by item.created_at, item.item_key)
                            from public.order_intake_items item
                            where item.intake_id = intake.intake_id
                              and lower(coalesce(item.status, 'active')) = 'active'
                              and item.removed_at is null
                        ), '[]'::jsonb) as items
                    from public.order_intakes intake
                    where intake_status in ('Open', 'Ready_For_Draft', 'Ready_For_Quote')
                    and coalesce(notes, '') ilike '%%sam_live_stock%%'
                    order by updated_at desc nulls last, created_at desc
                    limit %s
                    """,
                    (limit,),
                )
                columns = [column.name for column in cursor.description]
                intakes = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {
            "success": True,
            "status": "sam_live_stock_open_intakes_loaded",
            "count": len(intakes),
            "open_intakes": [_open_intake_row(row) for row in intakes],
            "links": _owner_links(),
            **AUTHORITY_FLAGS,
        }, 200
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_open_intakes_failed", "error": _clean(str(exc), 240), "open_intakes": [], **AUTHORITY_FLAGS}, 500


def audit_sam_live_stock_human_conversations(*, environ=None, chatwoot_reader=None, review_loader=None, now=None):
    """Owner-only caller surface: read and classify HUMAN conversations; never resets them."""
    source = environ if environ is not None else os.environ
    try:
        conversations = (chatwoot_reader or _chatwoot_read_conversations)(source)
    except Exception as exc:
        return {"success": False, "status": "sam_live_stock_human_audit_read_failed", "error": _clean(str(exc), 240), "conversations": [], "bulk_reset_allowed": False, **AUTHORITY_FLAGS}, 502
    now = now or datetime.now(timezone.utc)
    rows = []
    for conversation in conversations if isinstance(conversations, list) else []:
        attrs = conversation.get("custom_attributes") if isinstance(conversation.get("custom_attributes"), dict) else {}
        if _clean(attrs.get("conversation_mode"), 20).upper() != "HUMAN":
            continue
        if review_loader is not None or chatwoot_reader is None:
            loaded, loaded_status = (review_loader or get_latest_sam_live_stock_review_event_for_conversation)(conversation.get("id"))
            if loaded_status < 400 and loaded.get("success"):
                conversation = {**conversation, "sam_live_stock_review": _human_audit_review_state(loaded.get("event"))}
        rows.append(_classify_human_conversation(conversation, now))
    return {"success": True, "status": "sam_live_stock_human_audit_loaded", "conversations": rows, "counts": {key: sum(1 for row in rows if row["classification"] == key) for key in ("awaiting_owner", "resolved_but_stuck", "stale_unknown", "active_manual")}, "bulk_reset_allowed": False, "writes_performed": False, **AUTHORITY_FLAGS}, 200


def _classify_human_conversation(conversation, now):
    messages = conversation.get("messages") if isinstance(conversation.get("messages"), list) else []
    latest = messages[-1] if messages else {}
    direction = _clean(latest.get("message_type") or latest.get("direction"), 40).lower()
    sender_type = _clean((latest.get("sender") or {}).get("type") if isinstance(latest.get("sender"), dict) else latest.get("sender_type"), 40).lower()
    timestamp = latest.get("created_at") or conversation.get("last_activity_at")
    age_hours = _age_hours(timestamp, now)
    review_state = _clean((conversation.get("sam_live_stock_review") or {}).get("state") if isinstance(conversation.get("sam_live_stock_review"), dict) else "", 60).lower()
    if direction in {"incoming", "0"} or sender_type in {"contact", "customer"}:
        classification = "awaiting_owner"
    elif review_state in {"resolved", "done", "no_reply_done", "sent"}:
        classification = "resolved_but_stuck"
    elif age_hours is None or age_hours >= 48:
        classification = "stale_unknown"
    else:
        classification = "active_manual"
    actions = {
        "awaiting_owner": "Review in Chatwoot; choose Send Reply, Keep With Me, or a no-send terminal action.",
        "resolved_but_stuck": "Owner may explicitly return this conversation to SAM after confirming resolution.",
        "stale_unknown": "Inspect the exact conversation and evidence before any mode change.",
        "active_manual": "Leave in HUMAN while Charl is actively handling it; return explicitly when done.",
    }
    return {"conversation_id": _clean(conversation.get("id"), 100), "classification": classification, "latest_message_direction": direction or "unknown", "latest_sender_type": sender_type or "unknown", "latest_message_at": timestamp, "age_hours": age_hours, "owner_action": actions[classification], "auto_reset_allowed": False}


def _age_hours(value, now):
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return round(max(0.0, (now - parsed.astimezone(timezone.utc)).total_seconds() / 3600), 2)
    except Exception:
        return None


def _human_audit_review_state(event):
    event = event if isinstance(event, dict) else {}
    review = _json_value(event.get("review_json"))
    owner_card = review.get("owner_card") if isinstance(review.get("owner_card"), dict) else {}
    card_state = _clean(owner_card.get("state"), 40).lower()
    if card_state == "resolved":
        return {"state": "resolved", "evidence_id": _clean(event.get("review_event_id"), 120)}
    if card_state in OWNER_CARD_ACTIVE_STATES:
        return {"state": "active", "evidence_id": _clean(event.get("review_event_id"), 120)}
    action = _clean(event.get("recommended_action"), 80).lower()
    if action in {"no_reply_needed", "review_close", "done", "resolved"}:
        return {"state": "resolved", "evidence_id": _clean(event.get("review_event_id"), 120)}
    return {"state": "unknown", "evidence_id": _clean(event.get("review_event_id"), 120)}


def _chatwoot_read_conversations(source):
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not token:
        raise RuntimeError("CHATWOOT_API_ACCESS_TOKEN is required")
    conversations = []
    for page in range(1, 21):
        request = urllib_request.Request(
            f"{base_url}/api/v1/accounts/{account_id}/conversations?status=all&page={page}",
            headers={"api_access_token": token}, method="GET",
        )
        with urllib_request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        batch = data.get("payload") if isinstance(data.get("payload"), list) else []
        conversations.extend(batch)
        if not batch:
            break
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        all_count = meta.get("all_count")
        if isinstance(all_count, int) and len(conversations) >= all_count:
            break
    return conversations


def build_sam_live_stock_launch_readiness(environ=None):
    source = environ if environ is not None else os.environ
    policy = sam_live_stock_launch_control_policy(source)
    checks = {
        "new_lead_telegram_ready": (
            policy["telegram_escalation"]["new_lead_send_enabled"]
            and policy["telegram_escalation"]["bot_token_configured"]
            and policy["telegram_escalation"]["owner_chat_id_configured"]
        ),
        "owner_review_telegram_ready": (
            policy["telegram_escalation"]["owner_review_send_enabled"]
            and policy["telegram_escalation"]["bot_token_configured"]
            and policy["telegram_escalation"]["owner_chat_id_configured"]
        ),
        "owner_approved_send_ready": policy["owner_send"]["enabled"],
        "escalation_telegram_ready": (
            policy["telegram_escalation"]["send_enabled"]
            and policy["telegram_escalation"]["bot_token_configured"]
            and policy["telegram_escalation"]["owner_chat_id_configured"]
        ),
        "stock_truth_link_ready": True,
        "open_intake_link_ready": True,
        "kill_switch_documented": True,
        "customer_autoreply_off_for_first_boost": True,
        "reservation_owner_gated": not policy["order_reservation"]["enabled"],
    }
    must_fix = []
    if not checks["new_lead_telegram_ready"]:
        must_fix.append("Enable SAM_LIVE_STOCK_TELEGRAM_NEW_LEAD_SEND_ENABLED with bot token and owner chat id.")
    if not checks["escalation_telegram_ready"]:
        must_fix.append("Enable SAM_LIVE_STOCK_TELEGRAM_ESCALATION_SEND_ENABLED with bot token and owner chat id.")
    if not checks["owner_review_telegram_ready"]:
        must_fix.append("Enable SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED with bot token and owner chat id.")
    if not checks["owner_approved_send_ready"]:
        must_fix.append("Enable SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED before approving Telegram replies into WhatsApp.")
    return {
        "success": True,
        "status": "sam_live_stock_launch_readiness",
        "score": 98 if not must_fix else 92,
        "boost_ready": not must_fix,
        "quiet_post_ready": True,
        "checks": checks,
        "must_fix_before_boost": must_fix,
        "owner_links": _owner_links(),
        "kill_switch": {
            "primary": "Set SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED=0 to stop SAM Live processing.",
            "sends": "Keep SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED=0 until owner-approved-send and real conversation review are complete.",
            "intake_writes": "Set SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED=0 if intake capture must stop.",
        },
        **AUTHORITY_FLAGS,
    }, 200


def _review_event_params(event):
    params = {}
    for key in (
        "review_event_id",
        "chatwoot_conversation_id",
        "chatwoot_message_id",
        "customer_name",
        "channel",
        "source_agent",
        "event_source",
        "customer_message_excerpt",
        "sam_reply_excerpt",
        "conversation_mode_recommendation",
        "recommended_action",
    ):
        if key == "sam_reply_excerpt":
            params[key] = _clean_multiline(event.get(key), 1800)
        else:
            params[key] = _clean(event.get(key), 500 if key.endswith("excerpt") else 120)
    for key in ("score", "confidence_target"):
        params[key] = int(event.get(key) or 0)
    for key in (
        "safe_to_send",
        "owner_send_required",
        "no_reply_recommended",
        "escalation_required",
        "applies_learning_now",
        "changes_prompt_now",
        "changes_runtime_now",
        "sends_customer_message",
        "calls_chatwoot",
        "calls_telegram",
        "creates_order",
        "reserves_stock",
        "changes_stock",
        "writes_farm_data",
    ):
        params[key] = bool(event.get(key))
    for key in ("review_json", "facts_json", "decision_json"):
        params[key] = json.dumps(event.get(key) if isinstance(event.get(key), (dict, list)) else {}, ensure_ascii=True)
    return params


def _telegram_send_message(token, chat_id, text, reply_markup=None):
    body = {"chat_id": chat_id, "text": text}
    if reply_markup:
        body["reply_markup"] = reply_markup
    return _telegram_api(token, "sendMessage", body)


def _telegram_delete_message(token, chat_id, message_id):
    return _telegram_api(token, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def _telegram_edit_message(token, chat_id, message_id, text, reply_markup=None):
    body = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    return _telegram_api(token, "editMessageText", body)


def _telegram_api(token, method, body):
    request = urllib_request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw or "{}")
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"telegram_http_{exc.code}") from exc


def _chatwoot_write_custom_attributes(conversation_id, custom_attributes, source):
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    token = _clean(source.get(CHATWOOT_TOKEN_ENV) or source.get(CHATWOOT_TOKEN_FALLBACK_ENV), 300)
    if not base_url:
        raise RuntimeError("CHATWOOT_BASE_URL is required")
    if not account_id:
        raise RuntimeError("CHATWOOT_ACCOUNT_ID is required")
    if not token:
        raise RuntimeError("CHATWOOT_API_ACCESS_TOKEN is required")
    request = urllib_request.Request(
        f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/custom_attributes",
        data=json.dumps({"custom_attributes": custom_attributes}, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json", "api_access_token": token},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {"status_code": getattr(response, "status", 200), "body": json.loads(raw or "{}")}
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"chatwoot_http_{exc.code}") from exc


def _chatwoot_conversation_url(conversation_id, source):
    conversation_id = _clean(conversation_id, 100)
    if not conversation_id:
        return ""
    source = source if isinstance(source, dict) else {}
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    if not base_url or not account_id:
        return ""
    return f"{base_url}/app/accounts/{account_id}/conversations/{conversation_id}"


def _callback_action(callback_data):
    data = _clean(callback_data, 240)
    if ":" in data:
        prefix, escalation_id = data.split(":", 1)
    else:
        prefix, escalation_id = data, ""
    mapping = {
        "sam_live_approve_send": "approve_send",
        "sam_live_close": "close",
        "sam_live_human": "human",
        "sam_live_resolved": "resolved",
        "sam_live_review_approve": "review_approve_send",
        "sam_live_review_edit": "review_edit",
        "sam_live_review_human": "review_human",
        "sam_live_review_no_reply": "review_no_reply",
        "sam_live_review_draft_order": "review_prepare_draft_order",
        "sam_live_review_quote": "review_prepare_quote",
        "sam_live_review_prepare_draft": "review_prepare_draft_order",
        "sam_live_review_update_draft": "review_update_draft_order",
        "sam_live_review_prepare_quote": "review_prepare_quote",
        "sam_live_review_prepare_sales_pack": "review_prepare_sales_pack",
        "sam_live_review_picture": "review_picture_reply",
        "sam_live_review_close": "review_close",
        "sam_live_card_send": "card_send",
        "sam_live_card_open": "card_open",
        "sam_live_card_keep": "card_keep",
        "sam_live_card_no_reply": "card_no_reply",
        "sam_live_card_done": "card_done",
        "approve_send": "approve_send",
        "close": "close",
        "human": "human",
        "resolved": "resolved",
    }
    return {"action": mapping.get(prefix, ""), "escalation_id": _clean(escalation_id, 120)}


def _callback_result(action, body, status_code, escalation_id):
    body = body if isinstance(body, dict) else {}
    return {
        "success": status_code < 400 and body.get("success") is not False,
        "status": body.get("status") or f"sam_live_stock_callback_{action}",
        "action": action,
        "escalation_id": escalation_id,
        "result": body,
        **AUTHORITY_FLAGS,
        "sends_customer_message": bool(body.get("sends_customer_message")),
        "calls_chatwoot": bool(body.get("calls_chatwoot")),
        "calls_telegram": bool(body.get("calls_telegram")),
    }, status_code


def _json_value(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _lead_fact_summary(facts):
    facts = facts if isinstance(facts, dict) else {}
    parts = []
    for label, key in (
        ("qty", "quantity"),
        ("category", "category"),
        ("sex", "sex"),
        ("weight", "weight_range"),
        ("timing", "timing"),
        ("location", "location"),
    ):
        value = _clean(facts.get(key), 80)
        if value:
            parts.append(f"{label}={value}")
    return ", ".join(parts) if parts else "not enough detail yet"


def _owner_card_fact_summary(facts):
    facts = facts if isinstance(facts, dict) else {}
    pieces = []
    quantity = _clean(facts.get("quantity"), 20)
    sex = _clean(facts.get("sex"), 40)
    category = _clean(facts.get("category"), 60)
    weight = _clean(facts.get("weight_range"), 60)
    timing = _clean(facts.get("timing"), 80)
    location = _clean(facts.get("location"), 80)
    item = " ".join(piece for piece in (quantity, sex, category) if piece)
    if item:
        pieces.append(item)
    if weight:
        pieces.append(weight)
    if timing:
        pieces.append(timing)
    if location:
        pieces.append(location)
    return ", ".join(pieces) if pieces else "not enough detail yet"


def _owner_card_stock_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("match_packet") if isinstance(decision.get("match_packet"), dict) else {}
    count = int(packet.get("exact_match_count") or 0)
    status = _clean(packet.get("match_status"), 80)
    sample = packet.get("matched_sample") if isinstance(packet.get("matched_sample"), list) else []
    sample_bits = []
    for item in sample[:3]:
        if not isinstance(item, dict):
            continue
        pig_id = _clean(item.get("pig_id") or item.get("Pig_ID") or item.get("id"), 40)
        weight = _clean(
            item.get("current_weight_kg")
            or item.get("current_weight")
            or item.get("weight")
            or item.get("Weight")
            or item.get("weight_kg"),
            30,
        )
        if pig_id and weight:
            sample_bits.append(f"{pig_id} {weight}kg")
        elif pig_id:
            sample_bits.append(pig_id)
    sample_text = f" ({', '.join(sample_bits)})" if sample_bits else ""
    if count:
        return f"{count} match{'' if count == 1 else 'es'}{sample_text}"
    return status.replace("_", " ") if status else "no stock match shown"


def _owner_card_price_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("price_answer_packet") if isinstance(decision.get("price_answer_packet"), dict) else {}
    if not packet.get("can_answer_price"):
        return "not resolved"
    unit = packet.get("unit_price")
    total = packet.get("estimated_total")
    quantity = packet.get("requested_quantity")
    parts = []
    if unit not in ("", None):
        parts.append(f"R{_money(unit)} each")
    if total not in ("", None):
        parts.append(f"R{_money(total)} total")
    pricing = packet.get("pricing") if isinstance(packet.get("pricing"), dict) else {}
    source = _clean(pricing.get("source") or pricing.get("price_source"), 60)
    if source:
        parts.append(f"source {source}")
    if quantity and not total:
        parts.append(f"qty {quantity}")
    return " - ".join(parts) if parts else "not resolved"


def _owner_card_open_order_quote_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("owner_action_packet") if isinstance(decision.get("owner_action_packet"), dict) else {}
    order_id = _clean(packet.get("order_id"), 100)
    routes = packet.get("routes") if isinstance(packet.get("routes"), dict) else {}
    quote_prepare = routes.get("quote_prepare") if isinstance(routes.get("quote_prepare"), dict) else {}
    quote_send = routes.get("quote_send_confirmed") if isinstance(routes.get("quote_send_confirmed"), dict) else {}
    status = _clean(packet.get("status"), 120)
    pieces = []
    if order_id:
        pieces.append(order_id)
    if quote_prepare.get("route") or status == "ready_for_owner_quote_prepare":
        pieces.append("quote prepare ready")
    elif quote_send.get("route"):
        pieces.append("quote send gate ready")
    return " - ".join(pieces) if pieces else "none open"


def _owner_card_missing_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    missing = decision.get("missing_fields") if isinstance(decision.get("missing_fields"), list) else []
    missing = [_clean(item, 40) for item in missing if _clean(item, 40)]
    return ", ".join(missing) if missing else "none"


def _owner_card_intent_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    plan = decision.get("conversation_plan") if isinstance(decision.get("conversation_plan"), dict) else {}
    goal = _clean(decision.get("conversation_goal") or plan.get("goal"), 120)
    if goal:
        return goal.replace("_", " ")
    return _clean(decision.get("sales_lane") or "unknown", 120).replace("_", " ")


def _owner_card_stage_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    plan = decision.get("conversation_plan") if isinstance(decision.get("conversation_plan"), dict) else {}
    stage = _clean(decision.get("conversation_stage") or plan.get("stage"), 80)
    return stage.replace("_", " ") if stage else "unknown"


def _owner_card_next_action_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    plan = decision.get("conversation_plan") if isinstance(decision.get("conversation_plan"), dict) else {}
    action = _clean(decision.get("next_action") or plan.get("next_action"), 120)
    return action.replace("_", " ") if action else "owner review"


def _owner_card_open_order_quote_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("owner_action_packet") if isinstance(decision.get("owner_action_packet"), dict) else {}
    order_id = _clean(packet.get("order_id"), 100)
    routes = packet.get("routes") if isinstance(packet.get("routes"), dict) else {}
    quote_prepare = routes.get("quote_prepare") if isinstance(routes.get("quote_prepare"), dict) else {}
    quote_route = _clean(quote_prepare.get("route"), 200)
    status = _clean(packet.get("status"), 120)
    if order_id and (quote_route or status == "ready_for_owner_quote_prepare"):
        return f"{order_id} - quote prepare ready"
    if order_id:
        return order_id
    draft_packet = decision.get("draft_order_packet") if isinstance(decision.get("draft_order_packet"), dict) else {}
    if draft_packet.get("draft_ready"):
        return "draft order ready to prepare"
    return "none"


def _owner_card_prepared_action_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("owner_action_packet") if isinstance(decision.get("owner_action_packet"), dict) else {}
    if not packet:
        return "none"
    label = _clean(packet.get("label"), 120).replace("_", " ")
    status = _clean(packet.get("status"), 120).replace("_", " ")
    order_id = _clean(packet.get("order_id"), 100)
    detail = _clean(packet.get("detail"), 180)
    parts = [part for part in (label, status) if part]
    if order_id:
        parts.append(order_id)
    summary = " - ".join(parts) if parts else "owner review"
    if detail:
        summary = f"{summary} ({detail})"
    return summary


def _owner_card_prepared_action_buttons(decision, callback_id):
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("owner_action_packet") if isinstance(decision.get("owner_action_packet"), dict) else {}
    callback_id = _clean(callback_id, 120)
    if not callback_id:
        return []
    status = _clean(packet.get("status"), 120)
    next_action = _clean(packet.get("next_action") or decision.get("next_action"), 120)
    internal_next_action = _clean(packet.get("internal_next_action") or decision.get("internal_next_action"), 120)
    buttons = []
    if status == "ready_for_owner_prepare" or bool(packet.get("draft_order_ready")) or next_action == "prepare_draft_order" or internal_next_action in {"create_draft", "create_draft_then_quote"}:
        buttons.append([{"text": "Prepare Draft Order", "callback_data": f"sam_live_review_prepare_draft:{callback_id}"}])
    if status == "ready_for_owner_sync_lines" or next_action == "update_draft_order" or internal_next_action == "sync_lines":
        buttons.append([{"text": "Update Draft Order", "callback_data": f"sam_live_review_update_draft:{callback_id}"}])
    if status == "ready_for_owner_quote_prepare" or next_action == "prepare_quote" or internal_next_action in {"generate_quote", "update_draft_then_quote"}:
        buttons.append([{"text": "Prepare Quote", "callback_data": f"sam_live_review_prepare_quote:{callback_id}"}])
    if _clean(packet.get("order_id"), 100):
        buttons.append([{"text": "Prepare Full Sales Pack", "callback_data": f"sam_live_review_prepare_sales_pack:{callback_id}"}])
    if next_action == "prepare_picture_response" or internal_next_action == "prepare_picture_response":
        buttons.append([{"text": "Send Picture Reply", "callback_data": f"sam_live_review_picture:{callback_id}"}])
    return buttons


def _prepared_review_callback_result(action, review_event_id, event, decision, message):
    event = event if isinstance(event, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    packet = decision.get("owner_action_packet") if isinstance(decision.get("owner_action_packet"), dict) else {}
    routes = packet.get("routes") if isinstance(packet.get("routes"), dict) else {}
    route_key = {
        "review_prepare_draft_order": "draft_order",
        "review_update_draft_order": "send_for_approval",
        "review_prepare_quote": "quote_prepare",
        "review_picture_reply": "picture_reply",
    }.get(action, "")
    route_packet = routes.get(route_key) if isinstance(routes.get(route_key), dict) else {}
    status = {
        "review_no_reply": "sam_live_stock_review_no_reply_recorded",
        "review_prepare_draft_order": "sam_live_stock_review_prepare_draft_order_ready",
        "review_update_draft_order": "sam_live_stock_review_update_draft_order_ready",
        "review_prepare_quote": "sam_live_stock_review_prepare_quote_ready",
        "review_picture_reply": "sam_live_stock_review_picture_reply_ready",
    }.get(action, f"sam_live_stock_callback_{action}")
    recommended_next = {
        "review_no_reply": "No customer message was sent. Leave the conversation as-is, close it, or continue manually in Chatwoot.",
        "review_prepare_draft_order": "Use the prepared order route from the owner console/API only after confirming the draft details.",
        "review_update_draft_order": "Update the existing draft order from the owner console/API only after confirming the latest animal lines.",
        "review_prepare_quote": "Prepare or verify the latest quote packet from the owner console/API before any customer send.",
        "review_picture_reply": "Review the picture reply and approved media in Chatwoot before sending anything to the customer.",
    }.get(action, "Owner review is required before any execution.")
    return {
        "success": True,
        "status": status,
        "action": action,
        "review_event_id": review_event_id,
        "conversation_id": _clean(event.get("chatwoot_conversation_id"), 100),
        "prepared_action": {
            "version": "sam_live_stock_prepared_callback_action_v1",
            "owner_gate_required": True,
            "manual_review_required": True,
            "action": action,
            "order_id": _clean(packet.get("order_id"), 100),
            "label": _clean(packet.get("label"), 120),
            "status": _clean(packet.get("status"), 120),
            "detail": _clean(packet.get("detail"), 300),
            "route": route_packet,
        },
        "suggested_reply": message if action == "review_picture_reply" else "",
        "recommended_next": recommended_next,
        **AUTHORITY_FLAGS,
    }


def _owner_card_flags(event, review, decision):
    flags = []
    event = event if isinstance(event, dict) else {}
    review = review if isinstance(review, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    facts = event.get("facts_json") if isinstance(event.get("facts_json"), dict) else {}
    blockers = decision.get("blockers") if isinstance(decision.get("blockers"), list) else []
    if facts.get("reservation_requested") or "reservation_request_owner_gate" in blockers:
        flags.append("reservation request")
    if facts.get("breeding_interest") or "breeding_or_replacement_stock_owner_gate" in blockers:
        flags.append("breeding/replacement")
    if review.get("escalation_required"):
        flags.append("needs human check")
    llm_draft = decision.get("llm_draft") if isinstance(decision.get("llm_draft"), dict) else {}
    llm_status = _clean(llm_draft.get("status"), 80)
    if llm_status and llm_status not in {"llm_disabled", "llm_reply_draft_used"}:
        status_label = llm_status
        if status_label.startswith("llm_"):
            status_label = status_label[4:]
        flags.append(f"LLM {status_label.replace('_', ' ')}")
    if isinstance(decision.get("llm_draft_review"), dict):
        draft_review = decision.get("llm_draft_review") or {}
        blocked = draft_review.get("blocked_reasons") if isinstance(draft_review.get("blocked_reasons"), list) else []
        blocked = [_clean(item, 80).replace("_", " ") for item in blocked if _clean(item, 80)]
        suffix = f": {', '.join(blocked[:3])}" if blocked else ""
        flags.append(f"LLM safety fallback{suffix}")
    return ", ".join(flags)


def _owner_authority_decision_summary(review):
    review = review if isinstance(review, dict) else {}
    labels = {
        "negotiated_price_owner_authority": "approve or decline the negotiated price",
        "reservation_owner_authority": "approve or decline the reservation through the protected order/stock rail",
        "breeding_stock_owner_authority": "approve or decline the exact breeding animals",
        "final_order_owner_authority": "approve or decline the final order commitment",
        "payment_confirmation_owner_authority": "verify or decline payment confirmation from canonical payment evidence",
    }
    reasons = review.get("protected_action_reasons") if isinstance(review.get("protected_action_reasons"), list) else []
    decisions = [labels.get(str(reason)) for reason in reasons if labels.get(str(reason))]
    return "; ".join(decisions)


def _owner_card_reply_source_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    source = _clean(decision.get("reply_source"), 120)
    llm_draft = decision.get("llm_draft") if isinstance(decision.get("llm_draft"), dict) else {}
    llm_status = _clean(llm_draft.get("status"), 80)
    if source == "llm_live_stock_reply_draft":
        return "LLM draft"
    if source == "deterministic_fallback_after_llm_review":
        review = decision.get("llm_draft_review") if isinstance(decision.get("llm_draft_review"), dict) else {}
        blocked = review.get("blocked_reasons") if isinstance(review.get("blocked_reasons"), list) else []
        reason = _clean(", ".join(str(item).replace("_", " ") for item in blocked[:2]), 160)
        return f"Safety fallback{f' - {reason}' if reason else ''}"
    if source == "deterministic_farm_general_knowledge":
        return "Farm knowledge fallback"
    if source == "natural_close_no_reply_guard":
        return "No reply recommended"
    if llm_status and llm_status not in {"llm_disabled", "llm_reply_draft_used"}:
        return f"Fallback - {llm_status.replace('_', ' ')}"
    if source == "deterministic_read_only_guard":
        return "Fact-aware fallback"
    return source.replace("_", " ") if source else "Fallback"


def _money(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return _clean(value, 40)
    if amount.is_integer():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"


def _open_intake_row(row):
    row = row if isinstance(row, dict) else {}
    missing = row.get("missing_fields")
    if isinstance(missing, str):
        try:
            missing = json.loads(missing)
        except Exception:
            missing = [missing] if missing else []
    if not isinstance(missing, list):
        missing = []
    items = row.get("items")
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = []
    if not isinstance(items, list):
        items = []
    items = [item for item in items if isinstance(item, dict)]
    total_quantity = sum(_positive_int(item.get("quantity")) for item in items)
    return {
        "intake_id": _clean(row.get("intake_id"), 100),
        "conversation_id": _clean(row.get("conversation_id"), 100),
        "customer_name": _clean(row.get("customer_name"), 120),
        "customer_phone": _clean(row.get("customer_phone_raw"), 80),
        "status": _clean(row.get("intake_status"), 60),
        "location": _clean(row.get("collection_location"), 120),
        "timing": _clean(row.get("collection_time_text"), 120),
        "quote_requested": bool(row.get("quote_requested")),
        "order_commitment": bool(row.get("order_commitment")),
        "missing_fields": missing,
        "quantity": total_quantity or None,
        "items": items,
        "next_action": _clean(row.get("next_action"), 120),
        "last_customer_message": _clean(row.get("last_customer_message"), 500),
        "notes": _clean(row.get("notes"), 500),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _positive_int(value):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else 0
    except (TypeError, ValueError):
        return 0


def _owner_links():
    return {
        "sales_availability": "/sales-availability",
        "sam_pricing": "/sales/sam-pricing",
        "open_intakes_api": "/api/sales/channels/chatwoot/sam-live-stock/open-intakes",
        "policy_api": "/api/sales/channels/chatwoot/sam-live-stock/policy",
        "readiness_api": "/api/sales/channels/chatwoot/sam-live-stock/launch-readiness",
    }


def _telegram_token(source):
    return _clean(source.get(TELEGRAM_BOT_TOKEN_ENV) or source.get(TELEGRAM_BOT_TOKEN_FALLBACK_ENV), 300)


def _stable_id(prefix, parts):
    raw = "|".join(str(part or "") for part in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8', errors='ignore')).hexdigest()[:12].upper()}"


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _clean_multiline(value, limit):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned[:limit]
