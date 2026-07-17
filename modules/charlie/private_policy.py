"""Identity and authority policy for Charl's private CHARLIE interface."""

from __future__ import annotations

import hmac
import os

ENABLED_ENV = "CHARLIE_PRIVATE_EXECUTIVE_ENABLED"
TOKEN_ENV = "CHARLIE_PRIVATE_TELEGRAM_BOT_TOKEN"
SECRET_ENV = "CHARLIE_PRIVATE_TELEGRAM_WEBHOOK_SECRET"
OWNER_USER_ENV = "CHARLIE_PRIVATE_TELEGRAM_OWNER_USER_ID"
OWNER_CHAT_ENV = "CHARLIE_PRIVATE_TELEGRAM_OWNER_CHAT_ID"
LLM_ENABLED_ENV = "CHARLIE_PRIVATE_LLM_ENABLED"
LLM_MODEL_ENV = "CHARLIE_PRIVATE_LLM_MODEL"
LLM_URL_ENV = "CHARLIE_PRIVATE_LLM_URL"
TRANSCRIPTION_ENABLED_ENV = "CHARLIE_PRIVATE_TRANSCRIPTION_ENABLED"
TRANSCRIPTION_MODEL_ENV = "CHARLIE_PRIVATE_TRANSCRIPTION_MODEL"

RED_ZONE_FLAGS = {
    "customer_send", "public_post", "payment", "deposit", "reservation", "stock_write",
    "lifecycle_write", "purpose_write", "destructive_migration", "production_delete", "credential_access",
}


def private_policy(environ=None):
    source = environ if environ is not None else os.environ
    token = str(source.get(TOKEN_ENV) or source.get("CHARLIE_BUILD_RELAY_BOT_TOKEN") or "").strip()
    secret = str(source.get(SECRET_ENV) or source.get("CHARLIE_BUILD_RELAY_WEBHOOK_SECRET") or "").strip()
    owner_user = str(source.get(OWNER_USER_ENV) or source.get("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS") or "").split(",")[0].strip()
    owner_chat = str(source.get(OWNER_CHAT_ENV) or owner_user).strip()
    explicit = _truthy(source.get(ENABLED_ENV))
    return {
        "enabled": explicit and bool(token) and len(secret) >= 32 and bool(owner_user) and bool(owner_chat),
        "explicitly_enabled": explicit,
        "token": token,
        "secret": secret,
        "owner_user_id": owner_user,
        "owner_chat_id": owner_chat,
        "llm_enabled": _truthy(source.get(LLM_ENABLED_ENV)) and bool(source.get(LLM_MODEL_ENV)) and bool(source.get("OPENAI_API_KEY")),
        "llm_model": str(source.get(LLM_MODEL_ENV) or "").strip(),
        "llm_url": str(source.get(LLM_URL_ENV) or "https://api.openai.com/v1/chat/completions").strip(),
        "transcription_enabled": _truthy(source.get(TRANSCRIPTION_ENABLED_ENV)) and bool(source.get(TRANSCRIPTION_MODEL_ENV)) and bool(source.get("OPENAI_API_KEY")),
        "transcription_model": str(source.get(TRANSCRIPTION_MODEL_ENV) or "").strip(),
        "openai_api_key_present": bool(source.get("OPENAI_API_KEY")),
        "single_owner": True,
        "groups_allowed": False,
        "can_run_shell": False,
        "red_zone_requires_exact_confirmation": True,
    }


def authenticate_private_update(payload, headers, environ=None):
    policy = private_policy(environ)
    if not policy["enabled"]:
        return {"allowed": False, "reason": "private_charlie_not_ready", "policy": _public(policy)}
    supplied = str((headers or {}).get("X-Telegram-Bot-Api-Secret-Token") or "")
    if not hmac.compare_digest(supplied, policy["secret"]):
        return {"allowed": False, "reason": "webhook_secret_denied", "policy": _public(policy)}
    message = payload.get("message") or payload.get("edited_message") or {}
    callback = payload.get("callback_query") or {}
    actor = callback.get("from") or message.get("from") or {}
    chat = message.get("chat") or (callback.get("message") or {}).get("chat") or {}
    if str(actor.get("id") or "") != policy["owner_user_id"]:
        return {"allowed": False, "reason": "owner_user_denied", "policy": _public(policy)}
    if str(chat.get("id") or "") != policy["owner_chat_id"] or str(chat.get("type") or "private") != "private":
        return {"allowed": False, "reason": "private_chat_binding_denied", "policy": _public(policy)}
    return {"allowed": True, "reason": "owner_authenticated", "policy": policy, "actor": actor, "chat": chat}


def authority_for_intent(intent_type, risk_flags=None, *, explicit_owner_command=False):
    risks = {str(item).lower() for item in (risk_flags or [])}
    if risks & RED_ZONE_FLAGS:
        return {"allowed": False, "tier": "charl_human", "reason": "exact_owner_confirmation_required"}
    if intent_type.startswith("read_") or intent_type in {"executive_brief", "help", "clarify"}:
        return {"allowed": True, "tier": "auto", "reason": "read_only"}
    if intent_type in {"create_mission", "approve_mission", "pause_mission", "reject_mission", "send_back_mission", "remember_preference", "prepare_order_pack", "prepare_beacon_draft", "schedule_follow_up"}:
        return {"allowed": bool(explicit_owner_command), "tier": "charlie_delegated", "reason": "explicit_owner_command" if explicit_owner_command else "approval_bundle_required"}
    return {"allowed": False, "tier": "charl_human", "reason": "capability_not_delegated"}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _public(policy):
    return {key: value for key, value in policy.items() if key not in {"token", "secret"}}
