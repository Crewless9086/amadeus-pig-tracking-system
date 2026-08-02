"""Exact-once visible lifecycle for authenticated owner farm messages.

The existing Telegram gateway owns authentication and intent reasoning.  This
module only persists a deterministic mission and delivers/edits one owner card;
it creates no router, bot, specialist service, or farm-write authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable, Mapping

EVENT_SOURCE = "oom_sakkie_family_message_lifecycle"


def mission_identity(parsed: Mapping[str, Any], specialist: str) -> str:
    raw = "|".join((str(parsed.get("telegram_user_id") or ""),
                    str(parsed.get("telegram_chat_id") or ""),
                    str(parsed.get("provider_message_id") or ""), specialist))
    return "OOM-FAMILY-" + hashlib.sha256(raw.encode()).hexdigest()[:24].upper()


def deliver_family_result(parsed: Mapping[str, Any], result: Mapping[str, Any], *,
                          specialist: str, mission_id: str = "", card_mission_id: str = "",
                          event_store=None, sender=None, editor=None) -> dict[str, Any]:
    """Persist and visibly deliver one result; duplicate input is a no-op."""
    mission_id = mission_id or mission_identity(parsed, specialist)
    card_mission_id = card_mission_id or mission_id
    store = event_store or _event_store
    events = list(store("load", card_mission_id, None) or [])
    text = str(result.get("answer") or "").strip()
    if not text:
        return {"success": False, "status": "family_message_visible_text_required",
                "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    delivered = next((row for row in events if row.get("state") == "delivered"), None)
    latest = next((row for row in reversed(events) if row.get("state") in {"delivered", "updated"}), delivered)
    card_id = str((latest or {}).get("telegram_message_id") or "")
    if latest and str(latest.get("text_sha256") or "") == text_sha:
        return {"success": True, "status": "family_message_replayed_noop",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 0}

    payload = _event(parsed, mission_id, card_mission_id, specialist,
                     str(result.get("status") or "working"), text_sha)
    if card_id:
        update_id = card_mission_id + "-UPDATE-" + text_sha[:20].upper()
        claimed = store("record", update_id, {**payload, "event_id": update_id,
            "state": "update_attempted", "telegram_message_id": card_id})
        if claimed.get("created") is False:
            return {"success": False, "status": "family_message_update_delivery_ambiguous",
                    "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
        response = (editor or _edit_telegram)(str(parsed.get("telegram_chat_id") or ""), card_id, text)
        if not response.get("success"):
            store("record", update_id + "-CONTAINED", {**payload, "event_id": update_id + "-CONTAINED",
                "state": "contained", "reason": "telegram_edit_unconfirmed"})
            return {"success": False, "status": "family_message_update_contained",
                    "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
        store("record", update_id + "-DELIVERED", {**payload, "event_id": update_id + "-DELIVERED",
            "state": "updated", "telegram_message_id": card_id})
        return {"success": True, "status": "family_message_card_updated",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 1}

    attempt_id = card_mission_id + "-DELIVERY-ATTEMPT"
    claimed = store("record", attempt_id, {**payload, "event_id": attempt_id, "state": "delivery_attempted"})
    if claimed.get("created") is False:
        return {"success": False, "status": "family_message_delivery_ambiguous",
                "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
    response = (sender or _send_telegram)(str(parsed.get("telegram_chat_id") or ""), text)
    message_id = str(response.get("telegram_message_id") or "")
    if not response.get("success") or not message_id:
        store("record", attempt_id + "-CONTAINED", {**payload, "event_id": attempt_id + "-CONTAINED",
            "state": "contained", "reason": "telegram_delivery_unconfirmed"})
        return {"success": False, "status": "family_message_delivery_contained",
                "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
    delivered_id = card_mission_id + "-DELIVERED"
    store("record", delivered_id, {**payload, "event_id": delivered_id, "state": "delivered",
        "telegram_message_id": message_id})
    return {"success": True, "status": "family_message_delivered",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": message_id, "telegram_sends": 1, "telegram_edits": 0}


def bind_existing_card(parsed: Mapping[str, Any], *, specialist: str, mission_id: str,
                       telegram_message_id: str, text_sha256: str,
                       expected_bot_identity: str, provider_evidence_loader,
                       event_store=None):
    """Bind provider-proven legacy delivery without sending or editing it."""
    if not all(str(value or "").strip() for value in
               (mission_id, telegram_message_id, text_sha256, expected_bot_identity)):
        return {"success": False, "status": "existing_card_binding_incomplete"}
    evidence = provider_evidence_loader(str(parsed.get("telegram_chat_id") or ""),
                                        str(telegram_message_id))
    evidence = evidence if isinstance(evidence, Mapping) else {}
    expected = {"delivered": True, "bot_identity": str(expected_bot_identity),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "telegram_message_id": str(telegram_message_id),
        "text_sha256": str(text_sha256).lower()}
    actual = {"delivered": evidence.get("delivered"),
        "bot_identity": str(evidence.get("bot_identity") or ""),
        "chat_id": str(evidence.get("chat_id") or ""),
        "telegram_message_id": str(evidence.get("telegram_message_id") or ""),
        "text_sha256": str(evidence.get("text_sha256") or "").lower()}
    if actual != expected:
        return {"success": False, "status": "existing_card_provider_evidence_mismatch",
                "telegram_sends": 0, "telegram_edits": 0}
    store = event_store or _event_store
    if list(store("load", mission_id, None) or []):
        return {"success": False, "status": "existing_card_binding_conflict"}
    payload = _event(parsed, mission_id, mission_id, specialist,
                     "waiting_for_input", str(text_sha256).lower())
    event_id = mission_id + "-DELIVERED"
    recorded = store("record", event_id, {**payload, "event_id": event_id,
        "state": "delivered", "telegram_message_id": str(telegram_message_id),
        "recovered_provider_delivery": True})
    return {"success": recorded.get("success") is True,
            "status": "existing_card_bound" if recorded.get("success") is True else "existing_card_binding_failed",
            "mission_id": mission_id, "telegram_message_id": str(telegram_message_id),
            "telegram_sends": 0, "telegram_edits": 0}


def _event(parsed, mission_id, card_mission_id, specialist, task_state, text_sha):
    return {"mission_id": mission_id, "card_mission_id": card_mission_id,
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "specialist_identity": specialist, "task_state": task_state,
        "text_sha256": text_sha}


def _event_store(action, identity, payload):
    import psycopg
    if action == "load":
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'family_message_lifecycle'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'family_message_lifecycle'->>'card_mission_id'=%s
                    order by created_at,review_event_id""", (EVENT_SOURCE, identity))
                return [row[0] for row in cursor.fetchall()]
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event({"conversation_id": payload["card_mission_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "family_message_lifecycle"}, event_source=EVENT_SOURCE)
    event["review_event_id"] = identity; event["chatwoot_conversation_id"] = payload["card_mission_id"]
    event["review_json"] = {"family_message_lifecycle": dict(payload)}
    event["decision_json"] = {}; event["facts_json"] = {}; event["customer_message_excerpt"] = ""; event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True}


def _send_telegram(chat_id, text):
    from modules.oom_sakkie.telegram_gateway import _send_owner_task_telegram
    return _send_owner_task_telegram(chat_id, text, os.environ)


def _edit_telegram(chat_id, message_id, text):
    from modules.sales.sam_live_stock_launch_control import _telegram_api
    token = str(os.environ.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"success": False, "status": "telegram_token_not_configured"}
    try:
        response = _telegram_api(token, "editMessageText", {"chat_id": str(chat_id),
            "message_id": str(message_id), "text": str(text), "parse_mode": "HTML",
            "disable_web_page_preview": True})
    except Exception:
        return {"success": False, "status": "telegram_edit_ambiguous"}
    return {"success": response.get("ok") is True,
            "telegram_message_id": str(((response.get("result") or {}).get("message_id") if isinstance(response, dict) else "") or "")}
