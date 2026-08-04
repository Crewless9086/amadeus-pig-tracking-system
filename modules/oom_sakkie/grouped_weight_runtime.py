"""Authenticated grouped natural-weight preview through existing governed preflight."""
from __future__ import annotations
import hashlib, re
from datetime import datetime
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.herdmaster_weight_preview import preview_grouped_herd_weights
from modules.oom_sakkie.owner_response_composer import compose_weight_preview

_MULTI_WEIGHT = re.compile(r"(?:(?:pig|vark)\s+)?[A-Za-z0-9-]+\s+\d+(?:[.,]\d+)?\s*kg", re.I)

def handle_grouped_weight_message(parsed, authority, *, readiness_loader=None, preflight=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    text = str(parsed.get("text") or "")
    if semantic.get("domain") != "herd_management" or len(_MULTI_WEIGHT.findall(text)) < 2:
        return {"handled": False}, 200
    owner, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    if not validates_gateway_owner_authority(authority) or owner != chat or authority.owner_user_id != owner:
        return {"handled": False}, 200
    try:
        observed = datetime.fromisoformat(str(parsed.get("provider_timestamp") or "").replace("Z", "+00:00"))
    except ValueError:
        return {"handled": True, "success": False, "status": "weight_chronology_invalid", **_zero()}, 409
    if not observed.tzinfo:
        return {"handled": True, "success": False, "status": "weight_chronology_invalid", **_zero()}, 409
    if readiness_loader is None or preflight is None:
        from modules.pig_weights.pig_weights_controller import get_pig_allocation_readiness_data, preview_bulk_weight_entries
        readiness_loader, preflight = get_pig_allocation_readiness_data, preview_bulk_weight_entries
    preview = preview_grouped_herd_weights(text, weight_date=observed.date().isoformat(),
        readiness=readiness_loader(), preflight=preflight)
    mission = "OOM-HERD-WEIGHTS-" + hashlib.sha256(
        f"{owner}|{parsed.get('provider_message_id')}|{text}".encode()).hexdigest()[:24].upper()
    if preview.get("success") is not True:
        return {"handled": True, "success": False, "status": preview.get("status"),
                "mission_id": mission, "card_mission_id": mission,
                "answer": preview.get("clarification"), "question_count": 1, **_zero()}, 200
    return {"handled": True, "success": True, "status": "grouped_weight_preview_ready",
        "specialist_identity": "HERDMASTER", "mission_id": mission, "card_mission_id": mission,
        "preview_id": preview["preview_id"], "weight_date": preview["weight_date"],
        "mappings": preview["rows"], "confirmation_required": True,
        "answer": compose_weight_preview(preview["rows"], language="af" if str(semantic.get("language")).startswith("af") else "en"),
        **_zero()}, 200

def _zero():
    return {"writes_farm_data":False,"writes_weights":False,"hardware_commands":0,
            "protected_actions_performed":False}
