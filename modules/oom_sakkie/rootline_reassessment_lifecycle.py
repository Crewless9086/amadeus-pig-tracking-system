"""Owner-scoped, delivery-aware read-only ROOTLINE reassessment contract."""

from __future__ import annotations
import hashlib, json
from typing import Any, Callable, Mapping
from modules.oom_sakkie.owner_response_composer import compose_rootline


def reassess_rootline(*, owner_user_id: str, chat_id: str, trigger: str,
                      specialist_loader: Callable[[], Mapping[str, Any]],
                      state_store: Callable[[str, str, Any], Any], language="en"):
    if not owner_user_id or owner_user_id != chat_id or not str(trigger or "").strip():
        return _contained("reassessment_binding_invalid")
    current = specialist_loader()
    if not isinstance(current, Mapping) or current.get("success") is not True:
        return _contained("rootline_reassessment_unavailable")
    material = _material_digest(current)
    binding = hashlib.sha256(f"{owner_user_id}|{chat_id}|{material}".encode()).hexdigest()
    identity = "OOM-ROOTLINE-REASSESS-" + binding[:24].upper()
    delivered = state_store("load_delivered", f"{owner_user_id}|{chat_id}", None) or {}
    if delivered.get("material_digest") == material:
        return _result("rootline_reassessment_unchanged", material, notify=False)
    packet = {"identity": identity, "owner_user_id": owner_user_id, "chat_id": chat_id,
              "trigger": trigger, "material_digest": material,
              "result_id": str(current.get("result_id") or ""),
              "evidence_generation": str(current.get("generation") or current.get("evidence_cutoff") or ""),
              "answer": compose_rootline(current, language=language), "delivery_state": "pending"}
    recorded = state_store("claim_pending", identity, packet)
    if not isinstance(recorded, Mapping) or recorded.get("success") is not True:
        return _contained("rootline_reassessment_persistence_unproven")
    existing = state_store("load_identity", identity, None) or packet
    if any(str(existing.get(key) or "") != str(packet.get(key) or "")
           for key in ("owner_user_id", "chat_id", "material_digest")):
        return _contained("rootline_reassessment_binding_conflict")
    delivery_state = str(existing.get("delivery_state") or "pending")
    if delivery_state == "delivered":
        return _result("rootline_reassessment_replayed_noop", material, notify=False)
    if delivery_state == "ambiguous":
        return _contained("rootline_reassessment_delivery_ambiguous")
    status = "rootline_reassessment_changed" if recorded.get("created") is not False else "rootline_reassessment_delivery_pending"
    return {**_result(status, material, notify=True), "notification_identity": identity,
            "answer": packet["answer"]}


def record_reassessment_delivery(*, identity: str, owner_user_id: str, chat_id: str,
                                 material_digest: str, delivery: Mapping[str, Any],
                                 state_store: Callable[[str, str, Any], Any]):
    if delivery.get("provider_delivery_confirmed") is True and delivery.get("provider_message_id"):
        payload = {"owner_user_id": owner_user_id, "chat_id": chat_id,
                   "material_digest": material_digest, "delivery_state": "delivered",
                   "provider_message_id": str(delivery["provider_message_id"]),
                   "provider_timestamp": str(delivery.get("provider_timestamp") or "")}
        return state_store("mark_delivered", identity, payload)
    if delivery.get("provider_delivery_ambiguous") is True:
        return state_store("mark_ambiguous", identity, {"owner_user_id": owner_user_id,
            "chat_id": chat_id, "material_digest": material_digest, "delivery_state": "ambiguous"})
    return {"success": False, "status": "delivery_not_proven", "delivery_state": "pending"}


def _result(status, material, *, notify):
    return {"success": True, "status": status, "notify_owner": notify,
            "telegram_sends": 0, "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False, "material_digest": material}


def _material_digest(result):
    selected = {"overall_status": result.get("overall_status"),
        "recommendations": [{key: row.get(key) for key in ("subject", "status", "recommendation", "reason")}
                            for row in result.get("recommendations") or () if isinstance(row, Mapping)],
        "next_reassessment": result.get("next_reassessment"),
        "owner_question": (result.get("owner_brief") or {}).get("family_fact_needed")}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _contained(status):
    return {"success": False, "status": status, "notify_owner": False,
            "telegram_sends": 0, "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False}
