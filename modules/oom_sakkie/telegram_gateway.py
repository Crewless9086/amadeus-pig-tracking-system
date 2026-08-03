import hmac
import os
import time
from datetime import datetime, timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.service import TELEGRAM_OWNER_AUTHORITY, handle_message
from modules.oom_sakkie.owner_task_lifecycle import handle_owner_task_input
from modules.oom_sakkie.herdmaster_health_loss_runtime import handle_authenticated_health_loss_message
from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.farm_manager_runtime import handle_farm_manager_round
from modules.oom_sakkie.owner_conversation_front_door import build_owner_clarification


TRUTHY = {"1", "true", "yes", "on"}
ENABLED_ENV = "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED"
TOKEN_ENV = "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN"
ALLOWED_USER_IDS_ENV = "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"
TLS_CONFIRMED_ENV = "OOM_SAKKIE_TELEGRAM_TLS_CONFIRMED"
RATE_LIMIT_MODEL_ACCEPTED_ENV = "OOM_SAKKIE_TELEGRAM_RATE_LIMIT_MODEL_ACCEPTED"
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
    owner_task_bot_configured = bool(_owner_task_bot_token(source))
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
        "reply_transport": "caller_or_provider_bound_family_lifecycle",
        "owner_task_lifecycle": {
            "enabled": owner_task_bot_configured,
            "canonical_bot": "existing_sam_oom_owner_bot",
            "sends_telegram": owner_task_bot_configured,
            "reply_transport": "backend_handles_owner_task_delivery",
            "scope": "authenticated_active_owner_request_acknowledgement_result_or_systemic_exception_only",
            "requires_provider_message_identity": True,
            "ambiguous_delivery_retries": False,
        },
        "provider_bound_family_delivery": {
            "enabled": bool(str(source.get("DATABASE_URL") or "").strip()),
            "requires_authenticated_private_owner": True,
            "requires_provider_message_identity": True,
            "deduplicated": True,
            "scope": "visible_acknowledgement_or_consolidated_read_only_result",
        },
        "deterministic_only": True,
        "can_trigger_outbound_llm": False,
        "minimum_token_entropy": "Requires a long random token of at least 32 characters before the gateway can enable.",
        "direct_bot_cutover_enabled": False,
        "writes": False,
        "records_audit_trace": None,
        "audit_trace_mode": "tool_dependent",
        "writes_note": (
            "writes=false means no farm/control/public-output write. Ordinary "
            "tools append their normal audit trace; ROOTLINE intentionally "
            "returns not_stored_rootline_zero_write."
        ),
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def telegram_gateway_exposure_preflight(environ=None):
    source = environ if environ is not None else os.environ
    policy = telegram_gateway_policy(environ=source)
    automated_checks = [
        _check("explicitly_enabled", policy["explicitly_enabled"], "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED is truthy."),
        _check("token_configured", policy["configured"], "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN is configured."),
        _check("token_minimum_length", policy["token_meets_minimum_entropy"], f"Token is at least {MIN_TOKEN_CHARS} characters."),
        _check("allowed_user_ids_configured", policy["allowed_user_ids_configured"], "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS is configured."),
        _check("constant_time_compare", True, "Token comparison uses hmac.compare_digest."),
        _check("auth_lockout_enabled", policy["auth_rate_limit"]["enabled"], "Repeated bad tokens trigger a fail-closed lockout."),
        _check("deterministic_only", policy["deterministic_only"], "telegram_read_only never uses LLM router or answer composer."),
        _check("no_outbound_llm", not policy["can_trigger_outbound_llm"], "Gateway cannot trigger outbound LLM calls."),
        _check("ordinary_reply_transport_bounded", not policy["sends_telegram"] and not policy["direct_bot_cutover_enabled"],
               "The gateway itself has no ambient send authority; authenticated provider-bound family lifecycles may deliver through the existing owner bot."),
        _check("owner_task_send_is_scoped", not policy["owner_task_lifecycle"]["enabled"] or (
               policy["owner_task_lifecycle"]["requires_provider_message_identity"]
               and not policy["owner_task_lifecycle"]["ambiguous_delivery_retries"]),
               "When configured, owner-task sends use the existing owner bot, require provider identity, and never retry ambiguity."),
        _check("no_farm_control_write", not policy["writes"] and not policy["dispatch_enabled"], "Gateway does not write farm/control/public output or dispatch."),
        _check(
            "audit_trace_disclosed",
            policy["audit_trace_mode"] == "tool_dependent",
            "Audit storage is reported from the selected tool's trace_store result.",
        ),
    ]
    manual_checks = [
        _check("tls_termination_confirmed", _env_truthy(source.get(TLS_CONFIRMED_ENV)), "Confirm HTTPS/TLS terminates before public traffic reaches the route."),
        _check("rate_limit_model_accepted", _env_truthy(source.get(RATE_LIMIT_MODEL_ACCEPTED_ENV)), "Accept current in-process global lockout, or replace it with shared per-IP throttling before multi-worker production."),
    ]
    automated_ready = all(item["pass"] for item in automated_checks)
    public_ready = automated_ready and all(item["pass"] for item in manual_checks)
    if public_ready:
        status = "public_exposure_ready"
    elif automated_ready:
        status = "private_test_ready_manual_public_checks_pending"
    else:
        status = "blocked"
    return {
        "success": True,
        "status": status,
        "mode": "telegram_gateway_exposure_preflight_only",
        "telegram_gateway": policy,
        "private_test_ready": automated_ready,
        "public_exposure_ready": public_ready,
        "automated_checks": automated_checks,
        "manual_checks": manual_checks,
        "manual_confirm_envs": [TLS_CONFIRMED_ENV, RATE_LIMIT_MODEL_ACCEPTED_ENV],
        "rate_limit_note": "Current auth lockout is in-process and global: acceptable for the local/private trial, but not owner-immune or shared across multiple workers.",
        "sends_telegram": False,
        "direct_bot_cutover_enabled": False,
        "can_trigger_outbound_llm": False,
        "writes": False,
        "records_audit_trace": policy["records_audit_trace"],
        "audit_trace_mode": policy["audit_trace_mode"],
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

    source = environ if environ is not None else os.environ
    owner_task, owner_task_status = handle_owner_task_input(
        payload,
        environ=source,
        telegram_sender=lambda chat_id, text, purpose: _send_owner_task_telegram(
            chat_id, text, source),
    )
    if owner_task.get("handled"):
        owner_task.update({
            "mode": "authenticated_gateway_owner_task",
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": any(int(owner_task.get(key) or 0) > 0 for key in
                                  ("acknowledgements", "results", "systemic_exceptions")),
            "direct_bot_cutover_enabled": False,
            "can_trigger_outbound_llm": False,
            "writes": False,
            "records_audit_trace": True,
            "dispatch_enabled": False,
            "changes_runtime_now": False,
            "changes_prompt_now": False,
            "physical_controls_enabled": False,
            "customer_public_output_enabled": False,
        })
        return owner_task, owner_task_status

    parsed = parse_telegram_gateway_payload(payload)
    if not parsed["text"]:
        return _gateway_result(False, "telegram_text_required", policy, 400)
    allowed_ids = _allowed_user_ids(environ if environ is not None else os.environ)
    if allowed_ids and parsed["telegram_user_id"] not in allowed_ids:
        body, status_code = _gateway_result(False, "telegram_user_not_allowed", policy, 403)
        body["telegram_user_id"] = parsed["telegram_user_id"]
        return body, status_code
    gateway_authority = issue_gateway_owner_authority(
        parsed["telegram_user_id"],
        parsed["telegram_chat_id"],
    )
    if parsed["telegram_chat_type"] != "private":
        gateway_authority = None

    operational_result, operational_status = handle_operational_specialist_message(
        parsed, gateway_authority,
    )
    if operational_result.get("handled"):
        answer = str(operational_result.get("answer") or "")
        delivery = deliver_family_result(
            parsed, operational_result,
            specialist=str(operational_result.get("specialist_identity") or "OOM_SAKKIE"),
            mission_id=str(operational_result.get("mission_id") or ""),
            card_mission_id=str(operational_result.get("card_mission_id") or ""),
        )
        body, _ = _gateway_result(
            delivery.get("success") is True,
            str(operational_result.get("status") or "contained"), policy, operational_status,
        )
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": answer, "message": operational_result, "delivery": delivery,
            "records_audit_trace": True, "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        body["writes"] = operational_result.get("writes_farm_data")
        body["writes_unknown"] = operational_result.get("writes_farm_data_unknown") is True
        return body, 200 if delivery.get("success") else 202

    health_result, health_status = handle_authenticated_health_loss_message(
        parsed,
        gateway_authority,
    )
    if health_result.get("handled"):
        answer = str(health_result.get("answer") or "")
        if not answer and health_result.get("success") is not True:
            answer = ("⚠️ <b>HERDMASTER FOLLOW-UP CONTAINED</b>\n\n"
                      "Your message reached Oom Sakkie, but safe HERDMASTER processing was not proven. "
                      "Nothing was recorded; one technical follow-up is required.")
            health_result = {**health_result, "answer": answer,
                             "status": str(health_result.get("status") or "contained")}
        body, _ = _gateway_result(
            health_result.get("success") is True,
            str(health_result.get("status") or "health_loss_contained"),
            policy,
            health_status,
        )
        delivery = ({"success": True, "telegram_sends": 0, "telegram_edits": 0,
                     "status": "owner_delivery_suppressed_existing_card_unchanged"}
                    if health_result.get("suppress_owner_delivery") is True else
                    deliver_family_result(
                        parsed, health_result, specialist="HERDMASTER",
                        mission_id=str(health_result.get("mission_id") or ""),
                        card_mission_id=str(health_result.get("card_mission_id") or "")))
        body.update({
            "telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"],
            "text": parsed["text"],
            "answer": answer,
            "message": health_result,
            "records_audit_trace": health_result.get("records_audit_trace") is True,
            "audit_trace_status": "stored" if health_result.get("records_audit_trace") is True else "not_written",
            "reply": {
                "chat_id": parsed["telegram_chat_id"],
                "text": answer,
                "parse_mode": "HTML",
                "sends_telegram": False,
            },
            "delivery": delivery,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0,
        })
        return body, health_status if delivery.get("success") else 202

    manager_result, manager_status = handle_farm_manager_round(parsed, gateway_authority)
    if manager_result.get("handled"):
        answer = str(manager_result.get("answer") or "")
        delivery = deliver_family_result(parsed, manager_result, specialist="OOM_SAKKIE",
            mission_id=str(manager_result.get("mission_id") or ""),
            card_mission_id=str(manager_result.get("card_mission_id") or "")) \
            if manager_result.get("success") else {"success": False, "telegram_sends": 0}
        body, _ = _gateway_result(bool(manager_result.get("success")),
            str(manager_result.get("status") or "farm_manager_contained"), policy, manager_status)
        body.update({"telegram_user_id": parsed["telegram_user_id"],
            "telegram_chat_id": parsed["telegram_chat_id"], "text": parsed["text"],
            "answer": answer, "message": manager_result, "delivery": delivery,
            "records_audit_trace": True, "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        return body, manager_status if delivery.get("success") else 202

    message_result, message_status = handle_message({
        "text": parsed["text"],
        "channel": "telegram_read_only",
        "session_id": parsed["session_id"],
        "authenticated_owner": TELEGRAM_OWNER_AUTHORITY,
        "gateway_authority": gateway_authority,
    })
    if (gateway_authority is not None
            and message_result.get("needs_clarification") is True
            and not str(message_result.get("tool_used") or "").strip()):
        message_result = build_owner_clarification(parsed)
        message_status = 200
    rootline_auth_denied = (
        message_result.get("tool_used") == "rootline_water_energy_plan"
        and message_result.get("success") is not True
    )
    response_status = (
        "protected_reader_authentication_denied"
        if rootline_auth_denied
        else "answered"
    )
    response_code = 403 if rootline_auth_denied else message_status
    trace_store = message_result.get("trace_store") or {}
    body, _ = _gateway_result(
        bool(message_result.get("success")),
        response_status,
        policy,
        response_code,
    )
    body.update({
        "telegram_user_id": parsed["telegram_user_id"],
        "telegram_chat_id": parsed["telegram_chat_id"],
        "text": parsed["text"],
        "answer": message_result.get("answer", ""),
        "message": message_result,
        "records_audit_trace": trace_store.get("stored") is True,
        "audit_trace_status": str(trace_store.get("status") or "not_written"),
        "reply": {
            "chat_id": parsed["telegram_chat_id"],
            "text": message_result.get("answer", ""),
            "parse_mode": None,
            "sends_telegram": False,
        },
    })
    durable_delivery_ready = bool(str(os.environ.get("DATABASE_URL") or "").strip()
                                  and str(parsed.get("provider_message_id") or "").strip()
                                  and str(parsed.get("provider_timestamp") or "").strip())
    if body.get("success") and str(body.get("answer") or "").strip() and durable_delivery_ready:
        specialist = str(message_result.get("tool_used") or "OOM_SAKKIE").upper()
        delivery = deliver_family_result(
            parsed, message_result, specialist=specialist,
            mission_id=str(message_result.get("mission_id") or ""),
            card_mission_id=str(message_result.get("card_mission_id") or ""))
        body.update({"delivery": delivery,
            "reply_transport": "backend_handles_owner_task_delivery",
            "sends_telegram": int(delivery.get("telegram_sends") or 0) > 0})
        if not delivery.get("success"):
            return body, 202
    return body, response_code


def parse_telegram_gateway_payload(payload):
    payload = payload or {}
    message = payload.get("message") or payload.get("edited_message") or {}
    from_user = message.get("from") or payload.get("from") or {}
    chat = message.get("chat") or payload.get("chat") or {}
    text = payload.get("text") or message.get("text") or message.get("caption") or ""
    telegram_user_id = payload.get("telegram_user_id") or payload.get("from_user_id") or from_user.get("id") or ""
    telegram_chat_id = payload.get("telegram_chat_id") or payload.get("chat_id") or chat.get("id") or ""
    session_id = payload.get("session_id") or telegram_chat_id or telegram_user_id or ""
    telegram_chat_type = payload.get("telegram_chat_type") or chat.get("type") or ""
    if not telegram_chat_type and str(telegram_chat_id) == str(telegram_user_id):
        telegram_chat_type = "private"
    return {
        "text": str(text or "").strip()[:MAX_TELEGRAM_TEXT_CHARS],
        "telegram_user_id": str(telegram_user_id or "").strip()[:80],
        "telegram_chat_id": str(telegram_chat_id or "").strip()[:80],
        "telegram_chat_type": str(telegram_chat_type or "").strip()[:20],
        "session_id": f"telegram-{str(session_id or '').strip()[:100]}",
        "provider_message_id": str(message.get("message_id") or payload.get("message_id") or "").strip()[:120],
        "provider_timestamp": (
            datetime.fromtimestamp(float(message.get("date")), timezone.utc).isoformat()
            if isinstance(message.get("date"), (int, float)) else ""
        ),
        "reply_to_message_id": str(
            (message.get("reply_to_message") or {}).get("message_id") or ""
        ).strip()[:120],
    }


def _send_owner_task_telegram(chat_id, text, source):
    from modules.sales.sam_live_stock_launch_control import _telegram_api
    token = _owner_task_bot_token(source)
    if not token:
        return {"success": False, "status": "owner_task_telegram_token_not_configured"}
    try:
        response = _telegram_api(token, "sendMessage", {
            "chat_id": str(chat_id), "text": str(text), "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
    except Exception:
        return {"success": False, "status": "owner_task_telegram_delivery_ambiguous"}
    result = response.get("result") if isinstance(response, dict) else {}
    message_id = str((result or {}).get("message_id") or "")
    return {"success": response.get("ok") is True and bool(message_id),
            "status": "owner_task_telegram_delivered" if message_id else "owner_task_telegram_delivery_unconfirmed",
            "telegram_message_id": message_id}


def _owner_task_bot_token(source):
    return str(source.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN")
               or source.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "").strip()


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
        "records_audit_trace": False,
        "audit_trace_mode": policy.get("audit_trace_mode", "tool_dependent"),
        "writes_note": policy.get("writes_note", ""),
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


def _check(name, passed, note):
    return {
        "name": name,
        "pass": bool(passed),
        "note": note,
    }


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
