"""Protected confirmation boundary for the existing ROOTLINE Mixer spine."""
from __future__ import annotations

from hashlib import sha256
import json

from modules.oom_sakkie.protected_action_claims import (
    CALLBACK_PREFIX, canonical_preview_digest, create_claim,
)
from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
    CONTRACT_VERSION as RUNTIME_CONTRACT,
    DEVICE_ID, MISSION_ID, MIXER_ID,
)
from modules.telemetry.rootline_auxiliary_management import ELIGIBILITY_CONTRACT

ACTION_KIND = "rootline_fertilizer_mixer_commissioning"
PREVIEW_CONTRACT = "oom_rootline_protected_mixer.v1"
BOUND_KEYS = ("contract_version", "eligibility_contract_version", "mission_id",
    "owner_user_id", "private_chat_id", "presence_provider_message_id",
    "presence_provider_timestamp", "presence_text_sha256", "auxiliary_device_id",
    "device_id", "channel", "maximum_duration_seconds", "native_auto_off_seconds",
    "emergency_off_required", "injection_enabled", "execution_id", "consumption_key",
    "eligibility_sha256", "plan_generation", "controller_safety_generation")


def create_mixer_preview(*, owner_result, parsed, gateway_authority, now=None,
                         connect_factory=None, prepare=None, **runtime_overrides):
    if prepare is None:
        from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
            prepare_fertilizer_commissioning,
        )
        prepare = prepare_fertilizer_commissioning
    prepared = prepare(owner_result=owner_result, parsed=parsed,
        gateway_authority=gateway_authority, now=now, **runtime_overrides)
    if prepared.get("status") != "commissioning_protected_preview_ready":
        return prepared
    artifact = prepared.get("eligibility")
    payload = build_preview_payload(artifact, parsed)
    claim = create_claim(action_kind=ACTION_KIND,
        owner_user_id=payload["owner_user_id"],
        private_chat_id=payload["private_chat_id"], mission_id=MISSION_ID,
        provider_message_id=payload["presence_provider_message_id"],
        evidence_generation=payload["plan_generation"], preview_payload=payload,
        ttl_minutes=5, connect_factory=connect_factory, supersede_active=False)
    token = claim["callback_token"]
    buttons = [[
        {"text": "Confirm", "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
        {"text": "Cancel", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"},
    ]]
    return {**prepared, **claim, "status": "mixer_protected_preview_created",
        "answer": ("<b>MIXER CH2 — SUPERVISED TEST</b>\n\n"
            "Mixer CH2 is ready for one supervised five-minute test. "
            "Nothing has started yet.\n\nConfirm / Cancel."),
        "reply_markup": {"inline_keyboard": buttons},
        "requires_visible_notification": True, "question_count": 0,
        "mission_id": MISSION_ID,
        "card_mission_id": protected_card_mission_id(claim["preview_digest"]),
        "preview_payload": payload, "hardware_commands": 0,
        "provider_control_calls": 0, "writes_farm_data": False}


def build_preview_payload(artifact, parsed):
    if not isinstance(artifact, dict):
        raise ValueError("mixer_preview_eligibility_missing")
    payload = {"contract_version": PREVIEW_CONTRACT,
        "eligibility_contract_version": artifact.get("contract_version"),
        "mission_id": MISSION_ID,
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "private_chat_id": str(parsed.get("telegram_chat_id") or ""),
        "presence_provider_message_id": str(parsed.get("provider_message_id") or ""),
        "presence_provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "presence_text_sha256": sha256(str(parsed.get("text") or "").encode()).hexdigest(),
        "auxiliary_device_id": artifact.get("auxiliary_device_id"),
        "device_id": artifact.get("device_id"), "channel": artifact.get("channel"),
        "maximum_duration_seconds": artifact.get("maximum_duration_seconds"),
        "native_auto_off_seconds": 300, "emergency_off_required": True,
        "injection_enabled": False, "no_on_retry": True,
        "provider_off_verification_required": True,
        "physical_observations_required": ["normal_recirculation", "pump_stopped"],
        "execution_id": artifact.get("execution_id"),
        "consumption_key": artifact.get("consumption_key"),
        "eligibility_sha256": artifact.get("eligibility_sha256"),
        "plan_generation": artifact.get("plan_generation"),
        "controller_safety_generation": artifact.get("controller_safety_generation"),
        "eligibility": artifact}
    if (payload["contract_version"] != PREVIEW_CONTRACT
            or payload["eligibility_contract_version"] != ELIGIBILITY_CONTRACT
            or payload["owner_user_id"] != "5721652188"
            or payload["private_chat_id"] != payload["owner_user_id"]
            or not payload["presence_provider_message_id"]
            or payload["auxiliary_device_id"] != MIXER_ID
            or payload["device_id"] != DEVICE_ID or payload["channel"] != 2
            or payload["maximum_duration_seconds"] != 300
            or payload["injection_enabled"] is not False):
        raise ValueError("mixer_preview_binding_invalid")
    return payload


def execute_claimed_mixer(claim, *, parsed, runner=None, **runtime_overrides):
    payload = claim.get("preview_payload") if isinstance(claim.get("preview_payload"), dict) else {}
    try:
        bound = {key: payload.get(key) for key in BOUND_KEYS}
        rebuilt = build_preview_payload(payload.get("eligibility"), {
            "telegram_user_id": payload.get("owner_user_id"),
            "telegram_chat_id": payload.get("private_chat_id"),
            "provider_message_id": payload.get("presence_provider_message_id"),
            "provider_timestamp": payload.get("presence_provider_timestamp"),
            "text": "",
        })
        rebuilt["presence_text_sha256"] = payload.get("presence_text_sha256")
    except (TypeError, ValueError):
        return _safe("mixer_protected_binding_mismatch"), 409
    if (bound != {key: rebuilt.get(key) for key in BOUND_KEYS}
            or rebuilt != payload
            or canonical_preview_digest(ACTION_KIND, payload) != claim.get("preview_digest")
            or str(claim.get("mission_id") or "") != MISSION_ID
            or str(parsed.get("telegram_user_id") or "") != payload["owner_user_id"]
            or str(parsed.get("telegram_chat_id") or "") != payload["private_chat_id"]):
        return _safe("mixer_protected_binding_mismatch"), 409
    if runner is None:
        from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
            execute_protected_fertilizer_commissioning,
        )
        runner = execute_protected_fertilizer_commissioning
    result = runner(eligibility=payload["eligibility"], parsed=parsed, **runtime_overrides)
    return result, 200 if result.get("success") is True else 409


def protected_card_mission_id(digest):
    return MISSION_ID + ":PROTECTED:" + str(digest)[:24].upper()


def _safe(status):
    return {"success": False, "handled": True, "status": status,
        "hardware_commands": 0, "provider_control_calls": 0,
        "writes_farm_data": False, "injection_enabled": False}
