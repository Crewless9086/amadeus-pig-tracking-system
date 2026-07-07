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
        "sam_reply_excerpt": _clean(decision.get("suggested_reply_text"), 500),
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
        return {
            "success": True,
            "status": "sam_live_stock_review_event_recorded" if created else "sam_live_stock_review_event_already_recorded",
            "review_event_id": params["review_event_id"],
            "created": created,
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


def send_sam_live_stock_telegram_escalation(packet, *, environ=None, telegram_sender=None):
    source = environ if environ is not None else os.environ
    packet = packet if isinstance(packet, dict) else {}
    telegram_packet = packet.get("telegram_packet") if isinstance(packet.get("telegram_packet"), dict) else packet
    if not _truthy(source.get(TELEGRAM_SEND_ENABLED_ENV)):
        return {"success": False, "status": "sam_live_stock_telegram_send_disabled", "packet": telegram_packet, **AUTHORITY_FLAGS}, 409
    chat_id = _clean(source.get(TELEGRAM_CHAT_ID_ENV), 100)
    token = _telegram_token(source)
    if not token:
        return {"success": False, "status": "sam_live_stock_telegram_token_required", **AUTHORITY_FLAGS}, 503
    if not chat_id:
        return {"success": False, "status": "sam_live_stock_telegram_owner_chat_required", **AUTHORITY_FLAGS}, 503
    text = _clean(telegram_packet.get("text"), 3500)
    if not text:
        return {"success": False, "status": "telegram_text_required", **AUTHORITY_FLAGS}, 400
    sender = telegram_sender or _telegram_send_message
    try:
        sent = sender(token, chat_id, text, telegram_packet.get("reply_markup") if isinstance(telegram_packet.get("reply_markup"), dict) else {})
        return {"success": True, "status": "sam_live_stock_telegram_escalation_sent", "telegram": sent, **AUTHORITY_FLAGS, "calls_telegram": True}, 200
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


def process_sam_live_stock_owner_callback(payload, *, environ=None, chatwoot_sender=None, telegram_deleter=None, chatwoot_writer=None):
    payload = payload if isinstance(payload, dict) else {}
    action = _callback_action(payload.get("callback_data") or payload.get("action"))
    escalation_id = _clean(payload.get("escalation_id") or action.get("escalation_id"), 120)
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


def _telegram_token(source):
    return _clean(source.get(TELEGRAM_BOT_TOKEN_ENV) or source.get(TELEGRAM_BOT_TOKEN_FALLBACK_ENV), 300)


def _stable_id(prefix, parts):
    raw = "|".join(str(part or "") for part in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8', errors='ignore')).hexdigest()[:12].upper()}"


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]
