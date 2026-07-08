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


TELEGRAM_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_ESCALATION_SEND_ENABLED"
TELEGRAM_NEW_LEAD_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_NEW_LEAD_SEND_ENABLED"
TELEGRAM_OWNER_REVIEW_SEND_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED"
TELEGRAM_CLEANUP_ENABLED_ENV = "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED"
TELEGRAM_BOT_TOKEN_ENV = "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID"
TELEGRAM_BOT_TOKEN_FALLBACK_ENV = "OOM_SAKKIE_TELEGRAM_BOT_TOKEN"
CHATWOOT_TAKEOVER_WRITE_ENABLED_ENV = "SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED"
ORDER_RESERVATION_ENABLED_ENV = "SAM_LIVE_STOCK_ORDER_RESERVATION_ENABLED"

AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "calls_chatwoot": False,
    "calls_telegram": False,
    "creates_order": False,
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
                        decision_json
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


def build_sam_live_stock_new_lead_packet(event, *, links=None):
    event = event if isinstance(event, dict) else {}
    facts = event.get("facts_json") if isinstance(event.get("facts_json"), dict) else {}
    review = event.get("review_json") if isinstance(event.get("review_json"), dict) else {}
    decision = event.get("decision_json") if isinstance(event.get("decision_json"), dict) else {}
    links = links if isinstance(links, dict) else {}
    conversation_id = _clean(event.get("chatwoot_conversation_id"), 100)
    parts = [
        "SAM Live Stock new lead",
        f"Conversation: {conversation_id or 'unknown'}",
        f"Customer: {_clean(event.get('customer_name') or 'Unknown', 80)}",
        f"Message: {_clean(event.get('customer_message_excerpt'), 300)}",
        "Captured: " + _lead_fact_summary(facts),
        f"Action: {_clean(event.get('recommended_action') or review.get('recommended_action'), 80)}",
    ]
    reply = _clean_multiline(event.get("sam_reply_excerpt") or decision.get("suggested_reply_text"), 400)
    if reply:
        parts.append(f"Draft: {reply}")
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
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "Keep Human", "callback_data": f"sam_live_human:{conversation_id}"},
                    {"text": "Close", "callback_data": f"sam_live_close:{conversation_id}"},
                ]],
            },
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
        f"Wants: {_owner_card_fact_summary(facts)}",
        f"Stock: {_owner_card_stock_summary(decision)}",
        f"Price: {_owner_card_price_summary(decision)}",
        f"Missing: {_owner_card_missing_summary(decision)}",
    ]
    flags = _owner_card_flags(event, review, decision)
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
    if review_event_id and reply:
        keyboard.append([{"text": "Approve Send", "callback_data": f"sam_live_review_approve:{review_event_id}"}])
    chatwoot_url = (
        _clean(links.get("chatwoot_conversation_url"), 500)
        or _chatwoot_conversation_url(conversation_id, source)
    )
    edit_button = {"text": "Edit in Chatwoot", "url": chatwoot_url} if chatwoot_url else {
        "text": "Edit in Chatwoot",
        "callback_data": f"sam_live_review_edit:{review_event_id or conversation_id}",
    }
    keyboard.append([
        edit_button,
        {"text": "Keep Human", "callback_data": f"sam_live_review_human:{review_event_id or conversation_id}"},
    ])
    keyboard.append([{"text": "Close", "callback_data": f"sam_live_review_close:{review_event_id or conversation_id}"}])
    return {
        "version": "sam_live_stock_owner_review_packet_v1",
        "type": "owner_review_send_candidate",
        "review_event_id": review_event_id,
        "conversation_id": conversation_id,
        "telegram_packet": {
            "text": "\n".join(parts),
            "reply_markup": {"inline_keyboard": keyboard},
        },
        **AUTHORITY_FLAGS,
    }


def send_sam_live_stock_new_lead_telegram(event, *, environ=None, telegram_sender=None, links=None):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_new_lead_packet(event, links=links)
    if not _truthy(source.get(TELEGRAM_NEW_LEAD_SEND_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_new_lead_telegram_send_disabled", "packet": packet, **AUTHORITY_FLAGS}, 409
    return _send_sam_live_stock_telegram_packet(packet["telegram_packet"], source, telegram_sender, "sam_live_stock_new_lead_telegram_sent")


def send_sam_live_stock_owner_review_telegram(event, *, environ=None, telegram_sender=None, links=None):
    source = environ if environ is not None else os.environ
    packet = build_sam_live_stock_owner_review_packet(event, links=links, environ=source)
    if not _truthy(source.get(TELEGRAM_OWNER_REVIEW_SEND_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_owner_review_telegram_send_disabled", "packet": packet, **AUTHORITY_FLAGS}, 409
    return _send_sam_live_stock_telegram_packet(packet["telegram_packet"], source, telegram_sender, "sam_live_stock_owner_review_telegram_sent")


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


def process_sam_live_stock_owner_callback(payload, *, environ=None, chatwoot_sender=None, telegram_deleter=None, chatwoot_writer=None, review_event_loader=None):
    payload = payload if isinstance(payload, dict) else {}
    action = _callback_action(payload.get("callback_data") or payload.get("action"))
    escalation_id = _clean(payload.get("escalation_id") or action.get("escalation_id"), 120)
    if action["action"] in {"review_approve_send", "review_edit", "review_human", "review_close"}:
        loaded, load_status = (review_event_loader or get_sam_live_stock_review_event)(escalation_id)
        if load_status >= 400 or not loaded.get("success"):
            return _callback_result(action["action"], loaded, load_status, escalation_id)
        event = loaded.get("event") if isinstance(loaded.get("event"), dict) else {}
        conversation_id = event.get("chatwoot_conversation_id")
        decision_json = _json_value(event.get("decision_json"))
        message = _clean_multiline(decision_json.get("suggested_reply_text") or event.get("sam_reply_excerpt"), 1800)
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
        if action["action"] == "review_human":
            takeover, status = apply_sam_live_stock_chatwoot_takeover(
                conversation_id,
                mode="HUMAN",
                reason="telegram_owner_review_handoff",
                environ=environ,
                chatwoot_writer=chatwoot_writer,
            )
            return _callback_result("review_human", takeover, status, escalation_id)
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
                        updated_at
                    from public.order_intakes
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
        "sam_live_review_close": "review_close",
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
        weight = _clean(item.get("current_weight") or item.get("weight") or item.get("Weight") or item.get("weight_kg"), 30)
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


def _owner_card_missing_summary(decision):
    decision = decision if isinstance(decision, dict) else {}
    missing = decision.get("missing_fields") if isinstance(decision.get("missing_fields"), list) else []
    missing = [_clean(item, 40) for item in missing if _clean(item, 40)]
    return ", ".join(missing) if missing else "none"


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
    if decision.get("reply_source"):
        flags.append(_clean(str(decision.get("reply_source")).replace("_", " "), 80))
    return ", ".join(flags)


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
        "next_action": _clean(row.get("next_action"), 120),
        "last_customer_message": _clean(row.get("last_customer_message"), 500),
        "notes": _clean(row.get("notes"), 500),
        "updated_at": str(row.get("updated_at") or ""),
    }


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
