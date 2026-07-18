"""Single-ingress private CHARLIE Telegram executive runtime."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from modules.charlie.private_media import normalize_private_media, transcribe_voice
from modules.charlie.private_executive import build_executive_plan, compose_executive_reply, context_after_plan, run_executive_plan
from modules.charlie.private_planner import plan_owner_intent
from modules.charlie.private_policy import authenticate_private_update, authority_for_intent, private_policy
from modules.charlie.private_store import (
    bind_owner, claim_update, complete_update, create_approval_bundle, decide_bundle,
    recent_context, record_intent, record_message, record_tool_execution, stable_id,
    remember_preference,
    update_thread_context,
)
from modules.charlie.private_tools import TOOL_FOR_INTENT, execute_private_tool
from modules.charlie.private_response import build_executive_response_packet
from modules.charlie.executive_store import record_capability_outcome

CALLBACK_PREFIX = "cp:"


def handle_private_telegram_webhook(payload, headers=None, *, environ=None, sender=None, callback_answerer=None, store=None, event_sink=None):
    auth = authenticate_private_update(payload or {}, headers or {}, environ)
    if not auth["allowed"]:
        if auth["reason"] in {"owner_user_denied", "private_chat_binding_denied"}:
            return {"success": True, "status": "unauthorized_update_ignored"}, 200
        return {"success": False, "status": auth["reason"]}, 403
    update_id = str((payload or {}).get("update_id") or "")
    callback = (payload or {}).get("callback_query") or {}
    callback_id = str(callback.get("id") or "")
    store = store or _StoreFacade()
    claimed, claim_status = store.claim_update(update_id, callback_id)
    if claim_status >= 400:
        return claimed, claim_status
    if not claimed.get("created"):
        return {"success": True, "status": "duplicate_update_ignored"}, 200
    update_key = claimed["update_key"]
    actor, chat = auth["actor"], auth["chat"]
    binding, status = store.bind_owner(str(actor.get("id")), str(chat.get("id")), metadata={"username": str(actor.get("username") or "")[:120]})
    if status >= 400:
        store.complete_update(update_key, status="failed", result=binding)
        return binding, status
    try:
        if callback:
            result, status = _handle_callback(callback, binding, store, callback_answerer, sender, environ)
        else:
            result, status = _handle_message(payload, binding, store, sender, environ, event_sink=event_sink)
    except Exception as exc:
        result, status = {"success": False, "status": "private_charlie_runtime_failed", "error_type": exc.__class__.__name__}, 500
    store.complete_update(update_key, status="processed" if status < 400 else "failed", result={"status": result.get("status")})
    return result, status


def _handle_message(payload, binding, store, sender, environ, *, event_sink=None):
    message = payload.get("message") or payload.get("edited_message") or {}
    update_id = str(payload.get("update_id") or "")
    text = str(message.get("text") or message.get("caption") or "").strip()
    media = normalize_private_media(payload)
    if not text and any(item.get("kind") == "voice" for item in media):
        transcription = transcribe_voice(media, private_policy(environ), environ=environ)
        text = transcription.get("text") or ""
        if not text:
            return _reply(binding, "I received the voice note, but private voice transcription is not enabled yet. Please type the instruction for now.", store, sender, update_id, media, environ)
    if not text:
        return _reply(binding, "I received the attachment. Tell me what you want me to inspect or do with it.", store, sender, update_id, media, environ)
    owner_message, message_status = store.record_message(binding["thread_id"], "owner", text, update_id=update_id, telegram_message_id=str(message.get("message_id") or ""), media=media)
    if message_status >= 400:
        return owner_message, message_status
    context, _ = store.recent_context(binding["thread_id"])
    intent = plan_owner_intent(text, context, environ=environ)
    if event_sink:
        event_sink("intent_understood", {"intent_type": intent.get("type"), "confidence": intent.get("confidence"), "risk_flags": list(intent.get("risk_flags") or [])})
    intent_record, intent_status = store.record_intent(binding["thread_id"], owner_message["message_id"], intent)
    if intent_status >= 400:
        return intent_record, intent_status
    authority = authority_for_intent(intent["type"], intent.get("risk_flags"), explicit_owner_command=intent.get("explicit_owner_command", False))
    if intent["type"] == "help":
        reply = "I am CHARLIE, your private executive interface. Ask me for a CORE status, morning brief, blocked missions, owner decisions, ANALYST, workforce, or a specific mission. You can also explicitly create, approve, pause, reject, or send back a CORE mission."
        return _reply(binding, reply, store, sender, update_id, [], environ)
    if intent["type"] == "clarify":
        return _reply(binding, intent["args"].get("question") or "What outcome do you want?", store, sender, update_id, [], environ)
    if intent["type"] == "remember_preference" and authority["allowed"]:
        remembered, remember_status = store.remember_preference(intent["args"].get("key"), intent["args"].get("value"), owner_message["message_id"], approved=True)
        reply = "I have saved that as an approved owner preference." if remember_status < 400 else "I could not save that preference safely."
        return _reply(binding, reply, store, sender, update_id, [], environ, status_code=remember_status)
    if not authority["allowed"]:
        bundle = _approval_for_intent(binding["thread_id"], intent, store)
        reply = "I have prepared this as an owner decision instead of executing it. Confirm it from the decision card after checking the exact action."
        return _reply(binding, reply, store, sender, update_id, [], environ, reply_markup=_bundle_keyboard(bundle))
    if intent["type"] == "schedule_follow_up":
        delay = max(1, min(int(intent["args"].get("delay_minutes") or 1), 10080))
        due_at = datetime.now(timezone.utc) + timedelta(minutes=delay)
        open_context = dict(context.get("open_context") or {})
        pending = list(open_context.get("pending_follow_ups") or [])
        follow_up = {
            "follow_up_id": stable_id("FOLLOWUP", binding["thread_id"], owner_message["message_id"], due_at.isoformat()),
            "request": str(intent["args"].get("request") or "Check current executive status")[:1000],
            "due_at": due_at.isoformat(), "status": "pending", "source_message_id": owner_message["message_id"],
        }
        open_context.update({"goal": follow_up["request"], "stage": "monitoring", "pending_follow_ups": [*pending, follow_up][-20:], "updated_at": datetime.now(timezone.utc).isoformat()})
        updated, updated_status = store.update_thread_context(binding["thread_id"], open_context, summary=follow_up["request"])
        result = {"success": updated_status < 400, "status": updated.get("status"), "summary": f"I will check {follow_up['request']} again in {delay} minute(s) and report through your private CHARLIE channel.", "follow_up": follow_up}
        store.record_tool_execution(intent_record["intent_id"], "schedule_follow_up", authority["tier"], intent.get("args") or {}, result, status="succeeded" if updated_status < 400 else "failed")
        return _reply(binding, result["summary"], store, sender, update_id, [], environ, status_code=updated_status)
    if intent["type"].startswith("read_") or intent["type"] in {"investigate", "executive_brief"}:
        plan = build_executive_plan(text, intent, context)
        evidence = run_executive_plan(plan, intent_record["intent_id"], recorder=store.record_tool_execution, event_sink=event_sink)
        reply = compose_executive_reply(plan, evidence, environ=environ)
        durable_context = context_after_plan(plan, evidence)
        if hasattr(store, "update_thread_context"):
            store.update_thread_context(binding["thread_id"], durable_context, summary=str(durable_context.get("goal") or "")[:1000])
        status_code = 200 if evidence and evidence[0].get("success") else int((evidence[0] if evidence else {}).get("status") or 503)
        packet = build_executive_response_packet(reply, plan=plan, evidence=evidence, context=durable_context, action_status_code=status_code)
        return _reply(binding, reply, store, sender, update_id, [], environ, status_code=status_code, executive_packet=packet)
    result, status = execute_private_tool(intent["type"], intent.get("args") or {})
    store.record_tool_execution(intent_record["intent_id"], TOOL_FOR_INTENT.get(intent["type"], intent["type"]), authority["tier"], intent.get("args") or {}, result, status="succeeded" if status < 400 else "failed")
    if hasattr(store, "update_thread_context"):
        plan = build_executive_plan(text, intent, context)
        durable_context = context_after_plan(plan, [{
            "step": 1, "intent_type": intent["type"], "tool": TOOL_FOR_INTENT.get(intent["type"], intent["type"]),
            "success": status < 400 and result.get("success") is not False, "status": status, "result": result,
        }])
        store.update_thread_context(binding["thread_id"], durable_context, summary=str(durable_context.get("goal") or "")[:1000])
    if hasattr(store, "record_capability_outcome"):
        store.record_capability_outcome(
            f"private.{TOOL_FOR_INTENT.get(intent['type'], intent['type'])}",
            clean_pass=status < 400 and result.get("success") is not False,
            escaped_defect=status >= 500,
            evidence_version="charlie_private_executive_v2",
        )
    reply = result.get("summary") or "The action completed." if status < 400 else result.get("summary") or "I could not complete that safely."
    packet = build_executive_response_packet(reply, plan=plan if 'plan' in locals() else None, evidence=[{
        "intent_type": intent["type"], "tool": TOOL_FOR_INTENT.get(intent["type"], intent["type"]), "success": status < 400 and result.get("success") is not False, "status": status, "result": result,
    }], context=durable_context if 'durable_context' in locals() else {}, action_status_code=status)
    return _reply(binding, reply, store, sender, update_id, [], environ, status_code=status, executive_packet=packet)


def _handle_callback(callback, binding, store, callback_answerer, sender, environ):
    data = str(callback.get("data") or "")
    if not data.startswith(CALLBACK_PREFIX):
        return {"success": False, "status": "private_callback_invalid"}, 400
    parts = data.split(":")
    if len(parts) != 3 or parts[2] not in {"approve", "reject", "defer"}:
        return {"success": False, "status": "private_callback_invalid"}, 400
    answer = callback_answerer or answer_private_callback
    answer(str(callback.get("id") or ""), environ=environ)
    decided, status = store.decide_bundle(parts[1], parts[2])
    if status >= 400:
        return _reply(binding, "That decision is stale, expired, or already handled. I made no change.", store, sender, f"callback-{callback.get('id')}", [], environ)
    if hasattr(store, "record_capability_outcome"):
        store.record_capability_outcome(
            "charlie.owner_decision_quality", clean_pass=parts[2] == "approve",
            human_edit=parts[2] == "reject", evidence_version="charlie_private_executive_v2",
        )
    # Bundles deliberately record the decision. Red-zone execution remains outside this runtime.
    text = {"approve": "Decision approved and recorded. The protected action has not been executed automatically.", "reject": "Decision rejected and recorded.", "defer": "Decision deferred. I will leave it pending for your next review."}[parts[2]]
    return _reply(binding, text, store, sender, f"callback-{callback.get('id')}", [], environ)


def _approval_for_intent(thread_id, intent, store):
    state_hash = stable_id("STATE", intent["type"], json.dumps(intent.get("args") or {}, sort_keys=True))
    args = intent.get("args") or {}
    protected = str(args.get("protected_action") or "protected action").replace("_", " ")
    target = args.get("order_id") or args.get("conversation_id") or args.get("mission_id") or "target not supplied"
    title = {
        "customer_send": "Customer message authority",
        "public_post": "Public post authority",
        "payment": "Payment authority",
        "reservation": "Stock reservation authority",
        "lifecycle_write": "Farm lifecycle authority",
    }.get(args.get("protected_action"), "Protected business authority")
    summary = f"{args.get('action_summary') or protected}. Target: {target}."
    result, _ = store.create_approval_bundle(thread_id, title, summary, [{"intent": intent["type"], "args": args}], {"recommended": f"Review the {protected}, confirm the target, then authorize."}, state_hash)
    return result


def _bundle_keyboard(bundle):
    bundle_id = str(bundle.get("bundle_id") or "")
    if not bundle_id:
        return None
    return {"inline_keyboard": [[
        {"text": "Approve", "callback_data": f"{CALLBACK_PREFIX}{bundle_id}:approve"},
        {"text": "Reject", "callback_data": f"{CALLBACK_PREFIX}{bundle_id}:reject"},
        {"text": "Later", "callback_data": f"{CALLBACK_PREFIX}{bundle_id}:defer"},
    ]]}


def _reply(binding, text, store, sender, update_id, media, environ, *, reply_markup=None, status_code=200, executive_packet=None):
    text = str(text or "")[:3900]
    packet = executive_packet or build_executive_response_packet(text, action_status_code=status_code)
    send = sender or send_private_telegram_message
    sent, send_status = send(binding.get("telegram_chat_id") or "", text, reply_markup=reply_markup, environ=environ)
    store.record_message(binding["thread_id"], "charlie", text, update_id=f"reply-{update_id}", media=media, metadata={"send_status": sent.get("status"), "executive_packet": packet})
    return {
        "success": send_status < 400,
        "status": sent.get("status") if send_status >= 400 else "private_charlie_replied",
        "action_status_code": status_code,
        "reply": text,
        "executive_packet": packet,
    }, send_status


def send_private_telegram_message(chat_id, text, reply_markup=None, environ=None):
    policy = private_policy(environ)
    if not policy["enabled"]:
        return {"success": False, "status": "private_charlie_not_ready"}, 503
    body = {"chat_id": str(chat_id), "text": str(text)[:3900], "disable_web_page_preview": True}
    if reply_markup:
        body["reply_markup"] = reply_markup
    request = urllib.request.Request(f"https://api.telegram.org/bot{policy['token']}/sendMessage", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            parsed = json.loads(response.read().decode() or "{}")
    except (OSError, ValueError, urllib.error.HTTPError):
        return {"success": False, "status": "private_telegram_send_failed"}, 502
    return {"success": parsed.get("ok") is True, "status": "private_telegram_sent" if parsed.get("ok") is True else "private_telegram_rejected"}, 200 if parsed.get("ok") is True else 502


def answer_private_callback(callback_id, *, environ=None):
    policy = private_policy(environ)
    if not policy["enabled"] or not callback_id:
        return {"success": False, "status": "private_callback_not_ready"}, 503
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{policy['token']}/answerCallbackQuery",
        data=json.dumps({"callback_query_id": str(callback_id)}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            parsed = json.loads(response.read().decode() or "{}")
    except (OSError, ValueError, urllib.error.HTTPError):
        return {"success": False, "status": "private_callback_ack_failed"}, 502
    return {"success": parsed.get("ok") is True, "status": "private_callback_acknowledged"}, 200 if parsed.get("ok") is True else 502


class _StoreFacade:
    claim_update = staticmethod(claim_update)
    complete_update = staticmethod(complete_update)
    bind_owner = staticmethod(bind_owner)
    record_message = staticmethod(record_message)
    recent_context = staticmethod(recent_context)
    record_intent = staticmethod(record_intent)
    record_tool_execution = staticmethod(record_tool_execution)
    create_approval_bundle = staticmethod(create_approval_bundle)
    decide_bundle = staticmethod(decide_bundle)
    remember_preference = staticmethod(remember_preference)
    update_thread_context = staticmethod(update_thread_context)
    record_capability_outcome = staticmethod(record_capability_outcome)
