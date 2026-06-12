import hmac
import os
import time

from modules.oom_sakkie.service import handle_message


TRUTHY = {"1", "true", "yes", "on"}
ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED"
TOKEN_ENV = "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN"
ALLOWED_USER_IDS_ENV = "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"
MAX_TELEGRAM_TEXT_CHARS = 2000
MIN_TOKEN_CHARS = 32
AUTH_FAILURE_LIMIT = 8
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_LOCKOUT_SECONDS = 300
_AUTH_FAILURE_TIMES = []
_AUTH_LOCKED_UNTIL = 0.0


def telegram_gateway_policy(environ=None):
    source = environ if environ is not None else os.environ
    explicitly_enabled = _env_truthy(source.get(ENABLED_ENV))
    token = str(source.get(TOKEN_ENV, "") or "").strip()
    token_configured = bool(token)
    token_meets_minimum = len(token) >= MIN_TOKEN_CHARS
    allowed_ids = _allowed_user_ids(source)
    auth_locked = _auth_locked()
    return {
        "enabled": explicitly_enabled and token_configured and token_meets_minimum and bool(allowed_ids) and not auth_locked,
        "explicitly_enabled": explicitly_enabled,
        "configured": token_configured,
        "token_meets_minimum_entropy": token_meets_minimum,
        "minimum_token_chars": MIN_TOKEN_CHARS,
        "mode": "read_only_owner_gateway",
        "route": "POST /api/oom-sakkie/channels/telegram/message",
        "auth": "bearer_or_x_oom_sakkie_telegram_token",
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
        "sends_telegram": False,
        "reply_transport": "caller_handles_telegram_send",
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "minimum_token_entropy": "Requires a long random token of at least 32 characters before the gateway can enable.",
        "direct_bot_cutover_enabled": False,
        "writes": False,
        "records_audit_trace": True,
        "writes_note": "writes=false means no farm/control/public-output write; successful messages still append the normal Oom Sakkie audit trace.",
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def handle_telegram_gateway_message(payload, headers=None, environ=None):
    policy = telegram_gateway_policy(environ=environ)
    if not policy["explicitly_enabled"]:
        return _gateway_result(False, "telegram_gateway_disabled", policy, 503)
    if not policy["configured"]:
        return _gateway_result(False, "telegram_gateway_token_not_configured", policy, 503)
    if not policy["token_meets_minimum_entropy"]:
        return _gateway_result(False, "telegram_gateway_token_too_short", policy, 503)
    if not policy["allowed_user_ids_configured"]:
        return _gateway_result(False, "telegram_gateway_allowed_user_ids_required", policy, 503)
    if policy["auth_rate_limit"]["locked"]:
        return _gateway_result(False, "telegram_gateway_auth_rate_limited", policy, 429)
    if not _token_matches(headers or {}, environ=environ):
        _record_auth_failure()
        return _gateway_result(False, "telegram_gateway_auth_denied", policy, 403)

    parsed = parse_telegram_gateway_payload(payload)
    if not parsed["text"]:
        return _gateway_result(False, "telegram_text_required", policy, 400)
    allowed_ids = _allowed_user_ids(environ if environ is not None else os.environ)
    if allowed_ids and parsed["telegram_user_id"] not in allowed_ids:
        body, status_code = _gateway_result(False, "telegram_user_not_allowed", policy, 403)
        body["telegram_user_id"] = parsed["telegram_user_id"]
        return body, status_code

    message_result, message_status = handle_message({
        "text": parsed["text"],
        "channel": "telegram_read_only",
        "session_id": parsed["session_id"],
    })
    body, _ = _gateway_result(bool(message_result.get("success")), "answered", policy, message_status)
    body.update({
        "telegram_user_id": parsed["telegram_user_id"],
        "telegram_chat_id": parsed["telegram_chat_id"],
        "text": parsed["text"],
        "answer": message_result.get("answer", ""),
        "message": message_result,
        "reply": {
            "chat_id": parsed["telegram_chat_id"],
            "text": message_result.get("answer", ""),
            "parse_mode": None,
            "sends_telegram": False,
        },
    })
    return body, message_status


def parse_telegram_gateway_payload(payload):
    payload = payload or {}
    message = payload.get("message") or payload.get("edited_message") or {}
    from_user = message.get("from") or payload.get("from") or {}
    chat = message.get("chat") or payload.get("chat") or {}
    text = payload.get("text") or message.get("text") or message.get("caption") or ""
    telegram_user_id = payload.get("telegram_user_id") or payload.get("from_user_id") or from_user.get("id") or ""
    telegram_chat_id = payload.get("telegram_chat_id") or payload.get("chat_id") or chat.get("id") or ""
    session_id = payload.get("session_id") or telegram_chat_id or telegram_user_id or ""
    return {
        "text": str(text or "").strip()[:MAX_TELEGRAM_TEXT_CHARS],
        "telegram_user_id": str(telegram_user_id or "").strip()[:80],
        "telegram_chat_id": str(telegram_chat_id or "").strip()[:80],
        "session_id": f"telegram-{str(session_id or '').strip()[:100]}",
    }


def _gateway_result(success, status, policy, status_code):
    return {
        "success": success,
        "status": status,
        "mode": "telegram_read_only_gateway",
        "telegram_gateway": policy,
        "sends_telegram": False,
        "reply_transport": "caller_handles_telegram_send",
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": True,
        "writes_note": "writes=false means no farm/control/public-output write; successful messages still append the normal Oom Sakkie audit trace.",
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }, status_code


def _token_matches(headers, environ=None):
    source = environ if environ is not None else os.environ
    expected = str(source.get(TOKEN_ENV, "") or "").strip()
    if not expected:
        return False
    authorization = str(_header_value(headers, "Authorization") or "").strip()
    bearer_prefix = "Bearer "
    if authorization.startswith(bearer_prefix) and hmac.compare_digest(authorization[len(bearer_prefix):].strip(), expected):
        return True
    provided = str(_header_value(headers, "X-Oom-Sakkie-Telegram-Token") or "").strip()
    return hmac.compare_digest(provided, expected)


def _header_value(headers, name):
    if hasattr(headers, "get"):
        return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
    return ""


def _allowed_user_ids(source):
    raw = str(source.get(ALLOWED_USER_IDS_ENV, "") or "")
    return {
        item.strip()
        for item in raw.split(",")
        if item.strip()
    }


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


def _reset_auth_rate_limit_for_tests():
    global _AUTH_LOCKED_UNTIL
    _AUTH_FAILURE_TIMES.clear()
    _AUTH_LOCKED_UNTIL = 0.0
