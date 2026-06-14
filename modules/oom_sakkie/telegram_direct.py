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

    message_result, message_status = handle_message({
        "text": parsed["text"][:MAX_TELEGRAM_TEXT_CHARS],
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
        text=message_result.get("answer", ""),
        environ=environ,
    )
    body, _ = _direct_result(send_result.get("success") is True, send_result.get("status", "telegram_send_failed"), policy, send_status)
    body.update({
        "telegram_user_id": parsed["telegram_user_id"],
        "telegram_chat_id": parsed["telegram_chat_id"],
        "text": parsed["text"],
        "answer": message_result.get("answer", ""),
        "message": message_result,
        "telegram_send": send_result,
    })
    return body, send_status


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
