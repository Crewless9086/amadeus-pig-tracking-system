"""Typed read-only handoff from authenticated Oom Sakkie intake to ROOTLINE.

This adapter deliberately owns no Telegram or device transport.  It binds fresh
owner observations to ROOTLINE's canonical read model so a separately governed
execution consumer can decide whether a commissioned segment is eligible.
"""

from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime
import re

from modules.telemetry.rootline_specialist_result import build_current_rootline_specialist_result
from modules.telemetry.rootline_water_energy_plan import record_tank_observation, read_tank_observation
from modules.oom_sakkie.gateway_authority import validates_rootline_observation_write_authority

CONTRACT_VERSION = "rootline_operational_dispatch_result_v1"


def persist_rootline_observations(context: Mapping[str, Any], authority, *, database_url=None) -> dict[str, Any]:
    if (not validates_rootline_observation_write_authority(authority)
            or authority.owner_user_id != str(context.get("owner_user_id") or "")
            or authority.private_chat_id != str(context.get("chat_id") or "")
            or authority.mission_id != str(context.get("mission_id") or "")
            or authority.provider_message_id != str(context.get("provider_message_id") or "")
            or authority.provider_timestamp != str(context.get("provider_timestamp") or "")
            or authority.content_sha256 != str(context.get("content_sha256") or "")):
        return {"success": False, "contract_version": "rootline_owner_observation_bridge_v1",
                "status": "observation_write_authority_denied", "canonical_writes": 0}
    observations = context.get("observations") if isinstance(context.get("observations"), list) else []
    if not observations or not all(_valid_observation(item,context) for item in observations):
        return {"success":False,"contract_version":"rootline_owner_observation_bridge_v1",
                "status":"owner_observation_binding_invalid","canonical_writes":0}
    kinds=[item.get("kind") for item in observations if isinstance(item,Mapping)]
    if len(kinds) != len(set(kinds)):
        return {"success":False,"contract_version":"rootline_owner_observation_bridge_v1",
                "status":"duplicate_water_observation_ambiguous","canonical_writes":0}
    by_kind = {item.get("kind"): item for item in observations if isinstance(item, Mapping)}
    storage = by_kind.get("storage_level")
    reservoir = by_kind.get("reservoir_level")
    if not storage and not reservoir:
        return {"success": True, "contract_version": "rootline_owner_observation_bridge_v1",
                "created": False, "status": "no_water_observation", "canonical_writes": 0}
    provider_id = str(context.get("provider_message_id") or "")
    provider_at = str(context.get("provider_timestamp") or "")
    owner = str(context.get("owner_user_id") or "")
    payload = {"storage_fraction": [storage["numerator"], storage["denominator"]] if storage else None,
        "reservoir_fraction": [reservoir["numerator"], reservoir["denominator"]] if reservoir else None,
        "storage_state": _fraction_state(storage), "reservoir_state": _fraction_state(reservoir),
        "provider_message_id": provider_id, "observed_at": provider_at, "source": "oom_sakkie_owner",
        "idempotency_key": f"telegram:{context.get('mission_id')}:{provider_id}:rootline-water:{context.get('content_sha256')}"}
    actor = "telegram-owner:" + __import__("hashlib").sha256(owner.encode()).hexdigest()[:16]
    result, status = record_tank_observation(payload, actor, database_url)
    if status >= 400 or result.get("success") is not True:
        return {"success": False, "contract_version": "rootline_owner_observation_bridge_v1",
                "status": str(result.get("status") or "canonical_observation_write_failed"),
                "canonical_writes": None if result.get("write_outcome")=="indeterminate" else 0,
                "write_outcome": result.get("write_outcome") or "not_written"}
    readback = read_tank_observation(result.get("observation_id"), database_url)
    expected = {"storage_fraction": payload["storage_fraction"],
        "reservoir_fraction": payload["reservoir_fraction"],
        "provider_message_id": provider_id, "observed_at": provider_at}
    if any(readback.get(key) != value for key, value in expected.items()):
        return {"success": False, "contract_version": "rootline_owner_observation_bridge_v1",
                "status": "canonical_observation_readback_mismatch", "canonical_writes": int(result.get("created") is True),
                "observation_id": result.get("observation_id")}
    return {"success": True, "contract_version": "rootline_owner_observation_bridge_v1",
        "status": str(result.get("status")), "created": result.get("created") is True,
        "canonical_writes": int(result.get("created") is True), "observation_id": result.get("observation_id"),
        "readback": expected}


def _fraction_state(item):
    if not item: return "Unknown"
    if item["numerator"] == 0: return "LOW"
    if item["numerator"] == item["denominator"]: return "FULL"
    return "OK"


def dispatch_rootline_operation(context: Mapping[str, Any]) -> dict[str, Any]:
    expected_authority = {"farm_observation_write": False, "hardware_control": False,
                          "telegram_send": False, "automatic_on_retry": False}
    if not (context.get("contract_version") == "oom_rootline_operational_dispatch_v1"
            and all(str(context.get(key) or "").strip() for key in
                    ("mission_id", "owner_user_id", "chat_id", "provider_message_id",
                     "provider_timestamp", "content_sha256"))
            and str(context.get("owner_user_id")) == str(context.get("chat_id"))
            and _timestamp(context.get("provider_timestamp")) is not None
            and re.fullmatch(r"[0-9a-f]{64}", str(context.get("content_sha256") or ""))
            and context.get("visible_irrigation_need_zone") in (None, "", "C12345")
            and context.get("authority") == expected_authority):
        return _contained("authenticated_operational_binding_invalid")
    observations = context.get("observations") if isinstance(context.get("observations"), list) else []
    if not all(_valid_observation(item, context) for item in observations):
        return _contained("owner_observation_binding_invalid")
    if not observations and not context.get("visible_irrigation_need_zone"):
        return _contained("owner_operational_evidence_required")
    try:
        current = build_current_rootline_specialist_result()
    except Exception:
        return _contained("canonical_rootline_evidence_unavailable")
    if current.get("success") is not True or current.get("contract_version") != "rootline_specialist_result_v1":
        return _contained("canonical_rootline_result_invalid")
    zone = str(context.get("visible_irrigation_need_zone") or "")
    recommendation = next((item for item in current.get("recommendations") or []
                           if str(item.get("subject") or item.get("task_id") or item.get("zone_id") or "") in {zone, f"irrigation_{zone}"}), None)
    canonical_status = str((recommendation or {}).get("recommendation") or (recommendation or {}).get("status") or "Needs Data")
    # Provider-timestamped owner evidence may be recovered later and is not
    # assumed fresh. It triggers, but never substitutes for, a fresh governed
    # eligibility build.
    status = "Reassess" if observations else canonical_status
    labels = {"reservoir_level": "reservoir", "storage_level": "storage tanks"}
    level_text = ", ".join(f"{labels[item['kind']]}: {item['numerator']}/{item['denominator']}" for item in observations)
    return {
        "success": True, "contract_version": CONTRACT_VERSION,
        "specialist_acceptance": True, "recommendation": status,
        "canonical_recommendation_before_observation": canonical_status,
        "rootline_result_id": str(current.get("result_id") or ""),
        "evidence_generation": str(current.get("generation") or current.get("evidence_cutoff") or ""),
        "owner_observations": observations, "visible_irrigation_need_zone": zone or None,
        "observation_binding": "provider_timestamped_owner_evidence_requires_governed_reassessment",
        "owner_answer": (f"<b>ROOTLINE WATER OBSERVATION RECEIVED</b>\n\n"
                         f"Owner observation at {context['provider_timestamp']}: {level_text}. "
                         f"Visible irrigation need: {'C Camp' if zone == 'C12345' else 'not supplied'}. "
                         "ROOTLINE must now revalidate current power, weather, commissioning and channel state. "
                         "No irrigation command was sent by this intake step."),
        "reassessment": current.get("next_reassessment"),
        "unavailable": tuple((current.get("evidence") or {}).get("gaps") or ()),
        "hardware_commands": 0,
        "authority": {"telegram_send": False, "hardware_control": False,
                      "farm_observation_write": False, "automatic_on_retry": False},
    }


def _contained(reason: str) -> dict[str, Any]:
    return {"success": False, "contract_version": CONTRACT_VERSION,
            "specialist_acceptance": False, "reason": reason, "hardware_commands": 0,
            "authority": {"telegram_send": False, "hardware_control": False,
                          "farm_observation_write": False, "automatic_on_retry": False}}


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def _valid_observation(item, context):
    if not isinstance(item, Mapping) or item.get("kind") not in {"reservoir_level", "storage_level"}:
        return False
    if (str(item.get("provider_message_id") or "") != str(context.get("provider_message_id") or "")
            or str(item.get("observed_at") or "") != str(context.get("provider_timestamp") or "")):
        return False
    numerator, denominator = item.get("numerator"), item.get("denominator")
    return (type(numerator) is int and type(denominator) is int and denominator > 0
            and 0 <= numerator <= denominator and item.get("value") == f"{numerator}/{denominator}")
