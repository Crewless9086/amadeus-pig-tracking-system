"""Typed, command-inert dispatch for authenticated operational owner messages."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Callable, Mapping

from modules.oom_sakkie.gateway_authority import (
    ROOTLINE_READ_ONLY_TOOL,
    bind_gateway_owner_authority,
    validates_rootline_gateway_authority,
)
from modules.oom_sakkie.rootline_commissioning_adapter import accept_supervised_commissioning_presence

CONTRACT_VERSION = "oom_sakkie_operational_specialist_intake_v1"
ROOTLINE_PRESENCE_MAX_AGE_SECONDS = 300
_ROOTLINE_PRESENCE = re.compile(
    r"\bB and C valve area\b.*\bobserve both camps\b.*\bintervene immediately\b.*\bsupervised commissioning\b",
    re.I,
)
ZERO_AUTHORITY = {"writes_farm_data": False, "hardware_commands": 0,
                  "protected_actions_performed": False, "sends_telegram": False}


def handle_operational_specialist_message(
    parsed: Mapping[str, Any], gateway_authority: Any, *, now: datetime | None = None,
    rootline_dispatcher: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = accept_supervised_commissioning_presence,
) -> tuple[dict[str, Any], int]:
    text = str((parsed or {}).get("text") or "").strip()
    if not _ROOTLINE_PRESENCE.search(text):
        return {"handled": False, "status": "operational_specialist_intake_not_applicable"}, 200
    provider_id = str(parsed.get("provider_message_id") or "").strip()
    provider_at = _time(parsed.get("provider_timestamp"))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bound = bind_gateway_owner_authority(gateway_authority, ROOTLINE_READ_ONLY_TOOL)
    if not provider_id or provider_at is None or not validates_rootline_gateway_authority(bound):
        return _contained(parsed, "operational_specialist_auth_or_chronology_invalid", now), 409
    age = (now - provider_at).total_seconds()
    if age < 0 or age > ROOTLINE_PRESENCE_MAX_AGE_SECONDS:
        result = _contained(parsed, "rootline_physical_presence_stale", now)
        result["answer"] = ("⚠️ <b>ROOTLINE PRESENCE EXPIRED</b>\n\n"
            "I retained your earlier B/C valve-area message, but physical presence is valid for only five minutes. "
            "No hardware action was taken. I will ask again only when ROOTLINE is immediately ready to commission.")
        result["dispatch_state"] = "contained"
        return result, 200
    if rootline_dispatcher is None:
        result = _contained(parsed, "rootline_deployed_adapter_unavailable", now)
        result["answer"] = ("⚠️ <b>ROOTLINE CONTINUATION UNAVAILABLE</b>\n\n"
            "I received and retained your current presence confirmation, but the deployed ROOTLINE adapter did not accept it. "
            "No hardware action was taken; one technical exception is being tracked.")
        return result, 503
    try:
        evidence = dict(rootline_dispatcher({"owner_user_id": str(parsed.get("telegram_user_id") or ""),
            "chat_id": str(parsed.get("telegram_chat_id") or "")}) or {})
    except Exception:
        evidence = {}
    authority = evidence.get("authority") if isinstance(evidence.get("authority"), Mapping) else {}
    if (not evidence or evidence.get("success") is not True
            or str(evidence.get("contract_version") or "") != "rootline_commissioning_continuation_adapter_v1"
            or evidence.get("writes_performed") is not False
            or authority != {"hardware_control": False, "configuration_write": False, "telegram_send": False}
            or type(evidence.get("hardware_commands")) is not int
            or evidence.get("hardware_commands") != 0
            or evidence.get("authorization_current") is not True
            or evidence.get("specialist_acceptance") is not True):
        result = _contained(parsed, "rootline_deployed_adapter_result_invalid", now)
        result["answer"] = ("⚠️ <b>ROOTLINE CONTINUATION CONTAINED</b>\n\n"
            "Your presence confirmation is retained, but safe ROOTLINE acceptance was not proven. No hardware action was taken.")
        return result, 503
    digest = _digest(evidence)
    mission = _mission(parsed)
    return ({"handled": True, "success": True, "status": "working",
        "dispatch_state": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": mission, "card_mission_id": mission,
        "provider_message_id": provider_id, "provider_timestamp": provider_at.isoformat(),
        "evidence_generation": str(evidence.get("evidence_cutoff") or evidence.get("observed_at") or ""),
        "adapter_version": CONTRACT_VERSION, "result_digest": digest,
        "answer": ("✅ <b>ROOTLINE PRESENCE RECEIVED</b>\n\n"
            "I retained your current B/C valve-area confirmation and ROOTLINE accepted the read-only continuation. "
            "No hardware command has been issued. ROOTLINE must still preserve every governed safety boundary during the supervised continuation."),
        **ZERO_AUTHORITY}, 200)


def _contained(parsed, reason, now):
    mission = _mission(parsed)
    return {"handled": True, "success": False, "status": "contained",
        "systemic_exception": reason, "dispatch_state": "contained",
        "specialist_identity": "ROOTLINE", "mission_id": mission, "card_mission_id": mission,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "adapter_version": CONTRACT_VERSION, "result_digest": _digest({"reason": reason, "mission": mission}),
        "evidence_generation": now.isoformat(), "answer": "", **ZERO_AUTHORITY}


def _mission(parsed):
    return "OOM-ROOTLINE-" + _digest({"owner": str(parsed.get("telegram_user_id") or ""),
        "chat": str(parsed.get("telegram_chat_id") or ""),
        "message": str(parsed.get("provider_message_id") or "")})[:24].upper()


def _time(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
