import json
import os
import time
from urllib import request as urllib_request
from urllib import error as urllib_error

from modules.oom_sakkie.service import handle_message
from modules.oom_sakkie.telegram_gateway import (
    ALLOWED_USER_IDS_ENV,
    MAX_TELEGRAM_TEXT_CHARS,
    MIN_TOKEN_CHARS,
    TRUTHY,
    parse_telegram_gateway_payload,
)


DIRECT_ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED"
DIRECT_SEND_ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED"
BOT_TOKEN_ENV = "OOM_SAKKIE_TELEGRAM_BOT_TOKEN"
WEBHOOK_SECRET_ENV = "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET"
PROACTIVE_ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_PROACTIVE_ENABLED"
DAILY_BRIEF_ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_DAILY_BRIEF_ENABLED"
MAX_REPLY_CHARS = 3900
AUTH_FAILURE_LIMIT = 8
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_LOCKOUT_SECONDS = 300
_AUTH_FAILURE_TIMES = []
_AUTH_LOCKED_UNTIL = 0.0


def telegram_direct_policy(environ=None):
    source = environ if environ is not None else os.environ
    explicitly_enabled = _env_truthy(source.get(DIRECT_ENABLED_ENV))
    send_enabled = _env_truthy(source.get(DIRECT_SEND_ENABLED_ENV))
    bot_token = str(source.get(BOT_TOKEN_ENV, "") or "").strip()
    webhook_secret = str(source.get(WEBHOOK_SECRET_ENV, "") or "").strip()
    allowed_ids = _allowed_user_ids(source)
    auth_locked = _auth_locked()
    configured = bool(bot_token)
    secret_configured = bool(webhook_secret)
    secret_meets_minimum = len(webhook_secret) >= MIN_TOKEN_CHARS
    ready = (
        explicitly_enabled
        and send_enabled
        and configured
        and secret_configured
        and secret_meets_minimum
        and bool(allowed_ids)
        and not auth_locked
    )
    return {
        "enabled": ready,
        "explicitly_enabled": explicitly_enabled,
        "send_enabled": send_enabled,
        "configured": configured,
        "webhook_secret_configured": secret_configured,
        "webhook_secret_meets_minimum_entropy": secret_meets_minimum,
        "minimum_webhook_secret_chars": MIN_TOKEN_CHARS,
        "mode": "owner_only_direct_telegram_bot",
        "route": "POST /api/oom-sakkie/channels/telegram/direct-webhook",
        "auth": "x_telegram_bot_api_secret_token",
        "allowed_user_ids_required": True,
        "allowed_user_ids_configured": bool(allowed_ids),
        "allowed_user_ids_count": len(allowed_ids),
        "auth_rate_limit": {
            "enabled": True,
            "failure_limit": AUTH_FAILURE_LIMIT,
            "window_seconds": AUTH_FAILURE_WINDOW_SECONDS,
            "lockout_seconds": AUTH_LOCKOUT_SECONDS,
            "locked": auth_locked,
        },
        "sends_telegram": ready,
        "reply_transport": "backend_sends_owner_telegram_reply" if ready else "disabled",
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "direct_bot_cutover_enabled": ready,
        "writes": False,
        "records_audit_trace": True,
        "writes_note": "writes=false means no farm/control/public-output write; when enabled this path sends a Telegram reply only to an allowlisted owner chat and appends the normal Oom Sakkie audit trace.",
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
        "proactive": {
            "enabled": _env_truthy(source.get(PROACTIVE_ENABLED_ENV)),
            "daily_brief_enabled": _env_truthy(source.get(DAILY_BRIEF_ENABLED_ENV)),
            "mode": "script_or_scheduler_invoked_only",
            "background_loop_enabled": False,
            "allowed_user_ids_count": len(allowed_ids),
            "sends_telegram_when_invoked": ready
            and _env_truthy(source.get(PROACTIVE_ENABLED_ENV))
            and _env_truthy(source.get(DAILY_BRIEF_ENABLED_ENV)),
            "writes": False,
            "dispatch_enabled": False,
            "can_trigger_outbound_llm": False,
        },
    }


def telegram_direct_parity_report(environ=None):
    policy = telegram_direct_policy(environ=environ)
    return {
        "success": True,
        "status": "direct_telegram_parity_report",
        "mode": "owner_only_backend_direct_telegram",
        "telegram_direct": policy,
        "backend_owns_oom_sakkie_chat": policy["enabled"],
        "n8n_required_for_oom_sakkie_chat": False,
        "n8n_still_required_for": [
            "Sam sales/order workflows",
            "Existing non-Oom-Sakkie Telegram approval workflows",
            "Legacy GateKeeper rollback path if the direct bot webhook is deleted",
        ],
        "carried_over_backend_capabilities": _carried_over_capabilities(),
        "telegram_commands": _telegram_command_catalog(),
        "not_carried_over_yet": [
            "Telegram inline buttons and callback actions",
            "Telegram voice-note transcription",
            "Persistent task/reminder/project memory",
            "Write actions, dispatch, runtime changes, physical controls, or financial actions",
        ],
        "proactive_daily_brief": policy["proactive"],
        "sends_telegram": policy["sends_telegram"],
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": True,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def handle_telegram_direct_webhook(payload, headers=None, environ=None):
    policy = telegram_direct_policy(environ=environ)
    if not policy["explicitly_enabled"]:
        return _direct_result(False, "telegram_direct_disabled", policy, 503)
    if not policy["send_enabled"]:
        return _direct_result(False, "telegram_direct_send_disabled", policy, 503)
    if not policy["configured"]:
        return _direct_result(False, "telegram_direct_bot_token_not_configured", policy, 503)
    if not policy["webhook_secret_configured"]:
        return _direct_result(False, "telegram_direct_webhook_secret_not_configured", policy, 503)
    if not policy["webhook_secret_meets_minimum_entropy"]:
        return _direct_result(False, "telegram_direct_webhook_secret_too_short", policy, 503)
    if not policy["allowed_user_ids_configured"]:
        return _direct_result(False, "telegram_direct_allowed_user_ids_required", policy, 503)
    if policy["auth_rate_limit"]["locked"]:
        return _direct_result(False, "telegram_direct_auth_rate_limited", policy, 429)
    if not _secret_matches(headers or {}, environ=environ):
        _record_auth_failure()
        return _direct_result(False, "telegram_direct_auth_denied", policy, 403)

    parsed = parse_telegram_gateway_payload(payload)
    if not parsed["text"]:
        return _direct_result(False, "telegram_text_required", policy, 400)
    allowed_ids = _allowed_user_ids(environ if environ is not None else os.environ)
    if parsed["telegram_user_id"] not in allowed_ids:
        body, status_code = _direct_result(False, "telegram_user_not_allowed", policy, 403)
        body["telegram_user_id"] = parsed["telegram_user_id"]
        return body, status_code

    command = _telegram_command_for_text(parsed["text"])
    if command["kind"] == "help":
        message_result, message_status = _help_message_result(parsed["text"]), 200
    else:
        routed_text = command["text"] or parsed["text"]
        message_result, message_status = handle_message({
            "text": routed_text[:MAX_TELEGRAM_TEXT_CHARS],
            "channel": "telegram_read_only",
            "session_id": parsed["session_id"],
        })
    if message_status >= 400 or not message_result.get("success"):
        body, _ = _direct_result(False, "telegram_direct_answer_failed", policy, message_status)
        body.update({
            "telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"],
            "message": message_result,
        })
        return body, message_status

    send_result, send_status = send_owner_telegram_reply(
        chat_id=parsed["telegram_chat_id"],
        text=format_telegram_owner_reply(message_result),
        environ=environ,
    )
    body, _ = _direct_result(send_result.get("success") is True, send_result.get("status", "telegram_send_failed"), policy, send_status)
    body.update({
        "telegram_user_id": parsed["telegram_user_id"],
        "telegram_chat_id": parsed["telegram_chat_id"],
        "text": parsed["text"],
        "answer": message_result.get("answer", ""),
        "telegram_text": format_telegram_owner_reply(message_result),
        "message": message_result,
        "telegram_send": send_result,
    })
    return body, send_status


def send_daily_brief_to_allowed_owners(environ=None):
    source = environ if environ is not None else os.environ
    policy = telegram_direct_policy(environ=source)
    if not policy["enabled"]:
        return _proactive_result(False, "telegram_direct_not_ready", policy, []), 503
    if not _env_truthy(source.get(PROACTIVE_ENABLED_ENV)):
        return _proactive_result(False, "telegram_proactive_disabled", policy, []), 503
    if not _env_truthy(source.get(DAILY_BRIEF_ENABLED_ENV)):
        return _proactive_result(False, "telegram_daily_brief_disabled", policy, []), 503

    allowed_ids = sorted(_allowed_user_ids(source))
    if not allowed_ids:
        return _proactive_result(False, "telegram_direct_allowed_user_ids_required", policy, []), 503

    message_result, message_status = handle_message({
        "text": "daily command brief",
        "channel": "telegram_read_only",
        "session_id": "telegram-proactive-daily-brief",
    })
    if message_status >= 400 or not message_result.get("success"):
        return _proactive_result(False, "telegram_daily_brief_answer_failed", policy, [], message_result), message_status

    text = format_telegram_owner_reply(
        message_result,
        title="Oom Sakkie Daily Brief",
        footer="Proactive brief only. No write, dispatch, runtime, or physical action was performed.",
    )
    deliveries = []
    overall_success = True
    for chat_id in allowed_ids:
        send_result, send_status = send_owner_telegram_reply(chat_id=chat_id, text=text, environ=source)
        deliveries.append({
            "chat_id": chat_id,
            "success": send_result.get("success") is True,
            "status": send_result.get("status"),
            "status_code": send_status,
            "sends_telegram": send_result.get("sends_telegram") is True,
        })
        overall_success = overall_success and send_result.get("success") is True
    return _proactive_result(overall_success, "telegram_daily_brief_sent" if overall_success else "telegram_daily_brief_partial", policy, deliveries, message_result), 200 if overall_success else 502


def format_telegram_owner_reply(message_result, title="Oom Sakkie", footer=None):
    message_result = message_result or {}
    compact = _compact_telegram_reply(message_result, title=title, footer=footer)
    if compact:
        return compact[:MAX_REPLY_CHARS]
    answer = str(message_result.get("answer") or "").strip()
    tool_used = str(message_result.get("tool_used") or "").strip()
    safety_notes = [str(note).strip() for note in (message_result.get("safety_notes") or []) if str(note).strip()]
    lines = [title, ""]
    lines.append(answer or "I could not build a useful answer for that yet.")
    if tool_used:
        lines.extend(["", f"Check: {tool_used}"])
    if safety_notes:
        lines.extend(["", "Safety:", *[f"- {note}" for note in safety_notes[:3]]])
    lines.extend(["", footer or "No farm/control write, dispatch, runtime change, or physical action was performed."])
    return "\n".join(lines).strip()[:MAX_REPLY_CHARS]


def _compact_telegram_reply(message_result, title="Oom Sakkie", footer=None):
    tool_used = str(message_result.get("tool_used") or "").strip()
    context = message_result.get("tool_context") or {}
    if tool_used == "jarvis_daily_command_brief":
        return _format_daily_command_brief(context, title=title, footer=footer)
    if tool_used == "jarvis_safety_gate_board":
        return _format_safety_gate_board(context, title=title, footer=footer)
    if tool_used == "agent_command_center":
        return _format_agent_command_center(context, title=title, footer=footer)
    return ""


def _format_daily_command_brief(context, title="Oom Sakkie", footer=None):
    sections = (context or {}).get("sections") or {}
    if not sections:
        return ""
    farm = ((sections.get("farm") or {}).get("llm_context") or {}).get("sections") or {}
    business = (sections.get("business") or {}).get("llm_context") or {}
    command = (sections.get("command_center") or {}).get("llm_context") or {}
    command_center = command.get("command_center") or {}
    next_actions = list((context or {}).get("next_actions") or [])[:2]
    lines = [title, "", "Daily Command Brief", ""]
    if farm:
        lines.extend([
            "Farm",
            f"- Attention: {_summary(farm, 'attention')}",
            f"- Power: {_summary(farm, 'power')}",
            f"- Weather: {_summary(farm, 'weather')}",
            f"- Irrigation: {_summary(farm, 'irrigation')}",
            "",
        ])
    if business:
        counts = business.get("counts") or {}
        owner_question = str(business.get("owner_question") or "").strip()
        lines.extend([
            "Business",
            f"- Marketable stock: {counts.get('marketable_sales_stock', 0)}",
            f"- Meat ready now: {counts.get('meat_ready_now', 0)}",
            f"- Next: {_clip(owner_question, 180) if owner_question else _clip(str(business.get('next_action') or ''), 180)}",
            "",
        ])
    if command_center:
        lines.extend([
            "Command Center",
            f"- Jarvis progress: {command_center.get('overall_percent', 0)}%",
            "- Live authority: locked",
            f"- Next gate: {_clip(str(command_center.get('next_gate') or 'owner review before live authority'), 160)}",
            "",
        ])
    if next_actions:
        lines.append("Next")
        lines.extend(f"- {_clip(action, 180)}" for action in next_actions)
        lines.append("")
    lines.append(footer or "Read-only brief. No write, dispatch, runtime change, or physical action was performed.")
    return "\n".join(line for line in lines if line is not None).strip()


def _format_safety_gate_board(context, title="Oom Sakkie", footer=None):
    board = (context or {}).get("gate_board") or {}
    if not board:
        return ""
    gates = board.get("gates") or []
    lines = [
        title,
        "",
        "Safety Gates",
        f"- Configured: {board.get('configured_count', 0)}",
        f"- Locked authority gates: {board.get('locked_count', 0)}",
        f"- Manual checks: {board.get('manual_check_count', 0)}",
        "",
        "Gates",
    ]
    for gate in gates[:5]:
        lines.append(f"- {gate.get('label')}: {gate.get('status')}")
    lines.extend([
        "",
        footer or "Read-only gate board. No write, dispatch, runtime change, or physical action was performed.",
    ])
    return "\n".join(lines).strip()


def _format_agent_command_center(context, title="Oom Sakkie", footer=None):
    center = (context or {}).get("command_center") or {}
    if not center:
        return ""
    queues = (context or {}).get("queue_snapshots") or {}
    work_counts = ((queues.get("system_work_status") or {}).get("counts") or {})
    pending = sum(int(work_counts.get(key) or 0) for key in (
        "pending_build_requests",
        "pending_patch_reviews",
        "pending_dispatch_design_requests",
    ))
    lines = [
        title,
        "",
        "Agent Command Center",
        f"- Jarvis progress: {center.get('overall_percent', 0)}%",
        f"- Visible lanes: {len(center.get('lanes') or [])}",
        "- Live authority: locked",
        f"- Pending approval/design: {pending}",
        "",
        "Lanes",
    ]
    for lane in (center.get("lanes") or [])[:6]:
        lines.append(f"- {lane.get('label')}: {lane.get('current_state')}")
    lines.extend([
        "",
        footer or "Read-only command center. No specialist ran and no write, dispatch, runtime change, or physical action was performed.",
    ])
    return "\n".join(lines).strip()


def _summary(sections, name):
    return _clip(str(((sections.get(name) or {}).get("summary")) or "unavailable"), 180)


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    return text[: max(0, limit - 1)].rstrip() + ("..." if len(text) > limit else "")


def _telegram_command_for_text(text):
    clean = str(text or "").strip().lower()
    clean = clean.split("@", 1)[0] if clean.startswith("/") else clean
    aliases = {
        "/start": ("help", ""),
        "/help": ("help", ""),
        "help": ("help", ""),
        "menu": ("help", ""),
        "/menu": ("help", ""),
        "/brief": ("ask", "daily command brief"),
        "brief": ("ask", "daily command brief"),
        "/attention": ("ask", "what needs attention today"),
        "attention": ("ask", "what needs attention today"),
        "/gates": ("ask", "safety gates"),
        "gates": ("ask", "safety gates"),
        "/agents": ("ask", "agent command center"),
        "agents": ("ask", "agent command center"),
        "/progress": ("ask", "jarvis progress"),
        "progress": ("ask", "jarvis progress"),
        "/approvals": ("ask", "what needs my approval"),
        "approvals": ("ask", "what needs my approval"),
        "/learning": ("ask", "self learning status"),
        "learning": ("ask", "self learning status"),
    }
    kind, routed = aliases.get(clean, ("ask", ""))
    return {"kind": kind, "text": routed}


def _help_message_result(text):
    answer = (
        "I am live on backend direct Telegram for owner-only read-only checks.\n\n"
        "Try:\n"
        "/brief - daily command brief\n"
        "/attention - what needs attention today\n"
        "/gates - safety and CI gates\n"
        "/agents - command center\n"
        "/approvals - owner approval queue\n"
        "/progress - Jarvis progress\n"
        "/learning - learning backlog status\n\n"
        "You can also ask normal questions like: weather today, power now, irrigation status, sales stock, meat planning, or how are the pigs?"
    )
    return {
        "success": True,
        "answer": answer,
        "tool_used": "telegram_direct_help",
        "risk_level": 0,
        "trace_id": "",
        "safety_notes": ["Direct Telegram is read-only except for sending this owner reply."],
        "pipeline": {
            "route_source": "telegram_direct_command",
            "answer_source": "local",
            "llm_router_used": False,
            "llm_answer_used": False,
        },
        "links": [],
        "stale_warnings": [],
        "needs_clarification": False,
    }


def send_owner_telegram_reply(chat_id, text, environ=None):
    source = environ if environ is not None else os.environ
    policy = telegram_direct_policy(environ=source)
    if not policy["enabled"]:
        return _send_result(False, "telegram_direct_not_ready", policy), 503
    chat_id = str(chat_id or "").strip()
    text = str(text or "").strip()[:MAX_REPLY_CHARS]
    if not chat_id:
        return _send_result(False, "telegram_chat_id_required", policy), 400
    if not text:
        return _send_result(False, "telegram_reply_text_required", policy), 400

    token = str(source.get(BOT_TOKEN_ENV, "") or "").strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            response_body = json.loads(response.read().decode("utf-8") or "{}")
            status_code = response.status
    except urllib_error.HTTPError as error:
        try:
            response_body = json.loads(error.read().decode("utf-8") or "{}")
        except ValueError:
            response_body = {}
        result = _send_result(False, "telegram_api_rejected", policy)
        result["telegram_status_code"] = error.code
        result["telegram_ok"] = response_body.get("ok") is True
        result["telegram_error_code"] = response_body.get("error_code")
        result["telegram_description"] = str(response_body.get("description") or "")[:300]
        return result, 502
    except OSError:
        return _send_result(False, "telegram_api_unreachable", policy), 502

    result = _send_result(status_code == 200 and response_body.get("ok") is True, "telegram_sent", policy)
    result["telegram_status_code"] = status_code
    result["telegram_ok"] = response_body.get("ok") is True
    result["telegram_message_id"] = ((response_body.get("result") or {}).get("message_id"))
    return result, 200 if result["success"] else 502


def _send_result(success, status, policy):
    return {
        "success": success,
        "status": status,
        "mode": "owner_only_direct_telegram_send",
        "sends_telegram": success,
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
        "telegram_direct": _public_policy(policy),
    }


def _proactive_result(success, status, policy, deliveries, message=None):
    return {
        "success": success,
        "status": status,
        "mode": "owner_only_direct_telegram_proactive_daily_brief",
        "telegram_direct": _public_policy(policy),
        "deliveries": deliveries,
        "delivery_count": len(deliveries),
        "message": message or {},
        "sends_telegram": any(item.get("sends_telegram") for item in deliveries),
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": True,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
        "background_loop_enabled": False,
    }


def _direct_result(success, status, policy, status_code):
    return {
        "success": success,
        "status": status,
        "mode": "owner_only_direct_telegram_webhook",
        "telegram_direct": _public_policy(policy),
        "sends_telegram": success and policy["enabled"],
        "reply_transport": "backend_sends_owner_telegram_reply" if policy["enabled"] else "disabled",
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": True,
        "writes_note": policy["writes_note"],
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }, status_code


def _public_policy(policy):
    return dict(policy)


def _secret_matches(headers, environ=None):
    source = environ if environ is not None else os.environ
    expected = str(source.get(WEBHOOK_SECRET_ENV, "") or "").strip()
    provided = str(_header_value(headers, "X-Telegram-Bot-Api-Secret-Token") or "").strip()
    if not expected:
        return False
    import hmac
    return hmac.compare_digest(provided, expected)


def _header_value(headers, name):
    if hasattr(headers, "get"):
        return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
    return ""


def _allowed_user_ids(source):
    raw = str(source.get(ALLOWED_USER_IDS_ENV, "") or "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _carried_over_capabilities():
    return [
        "farm attention",
        "daily command brief",
        "farm operating brief",
        "power status",
        "weather",
        "irrigation",
        "farm dashboard summary",
        "pig allocation readiness",
        "meat planning",
        "sales dashboard",
        "business growth brief",
        "agent command center",
        "safety gates",
        "review packet",
        "dry-run and learning backlog status",
    ]


def _telegram_command_catalog():
    return [
        {"command": "/help", "text": "Show direct Telegram menu."},
        {"command": "/brief", "text": "Run the daily command brief."},
        {"command": "/attention", "text": "Show what needs attention today."},
        {"command": "/gates", "text": "Show safety and CI gate status."},
        {"command": "/agents", "text": "Show the agent command center."},
        {"command": "/approvals", "text": "Show owner approval queue/status."},
        {"command": "/progress", "text": "Show Jarvis progress."},
        {"command": "/learning", "text": "Show learning backlog status."},
    ]


def _env_truthy(value):
    return str(value or "").strip().lower() in TRUTHY


def _auth_locked(now=None):
    now = time.monotonic() if now is None else now
    return now < _AUTH_LOCKED_UNTIL


def _record_auth_failure(now=None):
    global _AUTH_LOCKED_UNTIL
    now = time.monotonic() if now is None else now
    cutoff = now - AUTH_FAILURE_WINDOW_SECONDS
    kept = [stamp for stamp in _AUTH_FAILURE_TIMES if stamp >= cutoff]
    kept.append(now)
    _AUTH_FAILURE_TIMES[:] = kept
    if len(_AUTH_FAILURE_TIMES) >= AUTH_FAILURE_LIMIT:
        _AUTH_LOCKED_UNTIL = now + AUTH_LOCKOUT_SECONDS


def _reset_direct_auth_rate_limit_for_tests():
    global _AUTH_LOCKED_UNTIL
    _AUTH_FAILURE_TIMES[:] = []
    _AUTH_LOCKED_UNTIL = 0.0
