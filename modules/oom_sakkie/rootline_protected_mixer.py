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
PRESENCE_ACTION_KIND = "rootline_fertilizer_mixer_presence_refresh"
PREVIEW_CONTRACT = "oom_rootline_protected_mixer.v1"
BOUND_KEYS = ("contract_version", "eligibility_contract_version", "mission_id",
    "owner_user_id", "private_chat_id", "presence_provider_message_id",
    "presence_provider_timestamp", "presence_text_sha256", "auxiliary_device_id",
    "device_id", "channel", "maximum_duration_seconds", "native_auto_off_seconds",
    "emergency_off_required", "injection_enabled", "execution_id", "consumption_key",
    "eligibility_sha256", "plan_generation", "controller_safety_generation")


def create_mixer_preview(*, owner_result, parsed, gateway_authority, now=None,
                         connect_factory=None, prepare=None,
                         parent_claim_token="", **runtime_overrides):
    from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import _bound
    if _bound(owner_result, parsed, gateway_authority):
        from modules.oom_sakkie.protected_action_claims import load_active_presence_claim
        prior = load_active_presence_claim(action_kind=ACTION_KIND, mission_id=MISSION_ID,
            owner_user_id=str(parsed.get("telegram_user_id") or ""),
            private_chat_id=str(parsed.get("telegram_chat_id") or ""),
            provider_message_id=str(parsed.get("provider_message_id") or ""),
            connect_factory=connect_factory)
        if prior is not None:
            return _existing_mixer_preview(prior, parsed)
    if prepare is None:
        from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
            prepare_fertilizer_commissioning,
        )
        prepare = prepare_fertilizer_commissioning
    prepared = prepare(owner_result=owner_result, parsed=parsed,
        gateway_authority=gateway_authority, now=now, **runtime_overrides)
    if prepared.get("status") == "commissioning_presence_expired":
        return create_presence_refresh_notice(owner_result=owner_result, parsed=parsed,
            connect_factory=connect_factory)
    if prepared.get("status") != "commissioning_protected_preview_ready":
        return prepared
    artifact = prepared.get("eligibility")
    payload = build_preview_payload(artifact, parsed)
    if parent_claim_token:
        payload["presence_refresh_claim_token"] = str(parent_claim_token)
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


def _existing_mixer_preview(prior, parsed):
    if prior.get("success") is not True:
        return _safe(str(prior.get("status") or "mixer_preview_recovery_unavailable"))
    payload = prior.get("preview_payload") if isinstance(prior.get("preview_payload"), dict) else {}
    try:
        rebuilt = build_preview_payload(payload.get("eligibility"), parsed)
        if payload.get("presence_refresh_claim_token"):
            rebuilt["presence_refresh_claim_token"] = payload["presence_refresh_claim_token"]
    except (TypeError, ValueError):
        return _safe("mixer_preview_recovery_binding_mismatch")
    if (rebuilt != payload or canonical_preview_digest(ACTION_KIND, payload) != prior.get("preview_digest")):
        return _safe("mixer_preview_recovery_binding_mismatch")
    token = prior["callback_token"]
    return {**prior, "success": True, "handled": True,
        "status": "mixer_protected_preview_created",
        "answer": ("<b>MIXER CH2 — SUPERVISED TEST</b>\n\n"
            "Mixer CH2 is ready for one supervised five-minute test. "
            "Nothing has started yet.\n\nConfirm / Cancel."),
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm", "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
            {"text": "Cancel", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"}]]},
        "requires_visible_notification": True, "question_count": 0,
        "mission_id": MISSION_ID,
        "card_mission_id": protected_card_mission_id(prior["preview_digest"]),
        "hardware_commands": 0, "provider_control_calls": 0, "writes_farm_data": False}


def create_presence_refresh_notice(*, owner_result, parsed, connect_factory=None):
    payload = {"contract_version": "oom_rootline_mixer_presence_refresh.v1",
        "mission_id": MISSION_ID,
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "private_chat_id": str(parsed.get("telegram_chat_id") or ""),
        "lost_presence_provider_message_id": str(parsed.get("provider_message_id") or ""),
        "lost_presence_provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "lost_presence_text_sha256": sha256(str(parsed.get("text") or "").encode()).hexdigest(),
        "specialist_identity": str(owner_result.get("specialist_identity") or ""),
        "next_specialist_step": str(owner_result.get("next_specialist_step") or "")}
    if (payload["owner_user_id"] != "5721652188"
            or payload["private_chat_id"] != payload["owner_user_id"]
            or payload["specialist_identity"] != "ROOTLINE"
            or payload["next_specialist_step"] != "supervised_fertilizer_mixer_proof"
            or not payload["lost_presence_provider_message_id"]):
        return _safe("mixer_presence_refresh_binding_invalid")
    generation = sha256(json.dumps(payload, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    claim = create_claim(action_kind=PRESENCE_ACTION_KIND,
        owner_user_id=payload["owner_user_id"], private_chat_id=payload["private_chat_id"],
        mission_id=MISSION_ID, provider_message_id=payload["lost_presence_provider_message_id"],
        evidence_generation=generation, preview_payload=payload, ttl_minutes=1440,
        connect_factory=connect_factory, supersede_active=False)
    token = claim["callback_token"]
    return {**claim, "success": True, "handled": True,
        "status": "mixer_presence_refresh_required", "preview_payload": payload,
        "answer": ("<b>MIXER CH2 — REPAIR READY</b>\n\n"
            "ROOTLINE retained your earlier response, but its safe presence window expired "
            "before the confirmation card was created. Nothing started.\n\n"
            "Press the button once when you are at the fertilizer valves."),
        "reply_markup": {"inline_keyboard": [[
            {"text": "I am ready now", "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
            {"text": "Cancel", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"}]]},
        "requires_visible_notification": True, "question_count": 0,
        "mission_id": MISSION_ID,
        "card_mission_id": MISSION_ID + ":PRESENCE:" + generation[:24].upper(),
        "hardware_commands": 0, "provider_control_calls": 0, "writes_farm_data": False}


def execute_presence_refresh(claim, *, parsed, gateway_authority, connect_factory=None,
                             prepare=None, now=None, **runtime_overrides):
    payload = claim.get("preview_payload") if isinstance(claim.get("preview_payload"), dict) else {}
    if (payload.get("contract_version") != "oom_rootline_mixer_presence_refresh.v1"
            or payload.get("mission_id") != MISSION_ID
            or payload.get("owner_user_id") != str(parsed.get("telegram_user_id") or "")
            or payload.get("private_chat_id") != str(parsed.get("telegram_chat_id") or "")
            or payload.get("owner_user_id") != "5721652188"
            or canonical_preview_digest(PRESENCE_ACTION_KIND, payload) != claim.get("preview_digest")):
        return _safe("mixer_presence_refresh_binding_mismatch"), 409
    from modules.oom_sakkie.protected_action_claims import load_active_child_claim
    child = load_active_child_claim(action_kind=ACTION_KIND, mission_id=MISSION_ID,
        parent_claim_token=str(claim.get("callback_token") or ""),
        owner_user_id=payload["owner_user_id"], private_chat_id=payload["private_chat_id"],
        connect_factory=connect_factory)
    if child is not None:
        if child.get("success") is not True:
            return _safe(str(child.get("status") or "mixer_presence_child_unavailable")), 409
        child_payload = child.get("preview_payload") if isinstance(
            child.get("preview_payload"), dict) else {}
        try:
            rebuilt_child = build_preview_payload(child_payload.get("eligibility"), {
                "telegram_user_id": payload["owner_user_id"],
                "telegram_chat_id": payload["private_chat_id"],
                "provider_message_id": child_payload.get("presence_provider_message_id"),
                "provider_timestamp": child_payload.get("presence_provider_timestamp"),
                "text": ""})
            rebuilt_child["presence_text_sha256"] = child_payload.get("presence_text_sha256")
            rebuilt_child["presence_refresh_claim_token"] = str(claim.get("callback_token") or "")
        except (TypeError, ValueError):
            return _safe("mixer_presence_child_binding_mismatch"), 409
        if (rebuilt_child != child_payload
                or canonical_preview_digest(ACTION_KIND, child_payload) != child.get("preview_digest")):
            return _safe("mixer_presence_child_binding_mismatch"), 409
        return {**child, "handled": True, "status": "mixer_protected_preview_created",
            "answer": ("<b>MIXER CH2 — SUPERVISED TEST</b>\n\n"
                "Mixer CH2 is ready for one supervised five-minute test. "
                "Nothing has started yet.\n\nConfirm / Cancel."),
            "reply_markup": {"inline_keyboard": [[
                {"text": "Confirm", "callback_data":
                    f"{CALLBACK_PREFIX}{child['callback_token']}:confirm"},
                {"text": "Cancel", "callback_data":
                    f"{CALLBACK_PREFIX}{child['callback_token']}:cancel"}]]},
            "requires_visible_notification": True, "question_count": 0,
            "mission_id": MISSION_ID,
            "card_mission_id": protected_card_mission_id(child["preview_digest"]),
            "hardware_commands": 0, "provider_control_calls": 0,
            "writes_farm_data": False}, 200
    owner_result = {"handled": True, "status": "specialist_accepted",
        "specialist_identity": "ROOTLINE", "mission_id": MISSION_ID,
        "card_mission_id": MISSION_ID,
        "next_specialist_step": "supervised_fertilizer_mixer_proof",
        "ready_for_supervised_proof": True,
        "authority": {"configuration_write": False, "hardware_control": False,
            "farm_write": False, "telegram_send": False}}
    current = {**parsed, "text": "protected current Mixer presence"}
    overrides = {**runtime_overrides, "acceptance_loader": lambda *_args: True}
    result = create_mixer_preview(owner_result=owner_result, parsed=current,
        gateway_authority=gateway_authority, now=now, connect_factory=connect_factory,
        prepare=prepare, parent_claim_token=str(claim.get("callback_token") or ""),
        **overrides)
    return result, 200 if result.get("success") is True else 409


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
        if payload.get("presence_refresh_claim_token"):
            rebuilt["presence_refresh_claim_token"] = payload["presence_refresh_claim_token"]
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
