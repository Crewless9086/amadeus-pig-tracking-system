"""Owner-scoped, delivery-aware read-only ROOTLINE reassessment contract."""

from __future__ import annotations
import hashlib, json
from typing import Any, Callable, Mapping
from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan
from modules.oom_sakkie.rootline_material import rootline_material_digest, stable_reassessment


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
        return {**_result("rootline_reassessment_unchanged", material, notify=False),
                "next_due_at": _declared_next_due(current),
                "evidence_cutoff": str(current.get("evidence_cutoff") or "")}
    packet = {"identity": identity, "owner_user_id": owner_user_id, "chat_id": chat_id,
              "trigger": trigger, "material_digest": material,
              "result_id": str(current.get("result_id") or ""),
              "evidence_generation": str(current.get("generation") or current.get("evidence_cutoff") or ""),
              "evidence_cutoff": str(current.get("evidence_cutoff") or ""),
              "next_reassessment_at": _declared_next_due(current),
              "zones": _typed_zone_projection(current),
              "answer": compose_daily_rootline_plan(current, language=language), "delivery_state": "pending"}
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
            "next_due_at": _declared_next_due(current),
            "evidence_cutoff": str(current.get("evidence_cutoff") or ""),
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
    return rootline_material_digest(result)


def _stable_reassessment(value):
    return stable_reassessment(value)


def _declared_next_due(result):
    value = result.get("next_reassessment") if isinstance(result, Mapping) else None
    return str((value or {}).get("at") or "") if isinstance(value, Mapping) else ""


def _typed_zone_projection(result):
    rows = []
    recommendations = result.get("recommendations") if isinstance(result, Mapping) else None
    for item in recommendations if isinstance(recommendations, list) else []:
        if not isinstance(item, Mapping) or item.get("subject") not in {"B12345", "C12345"}:
            continue
        decision = {"Recommend": "Run", "Do Not Run": "Not Due", "Hold": "Hold",
                    "Needs Data": "Needs Data"}.get(str(item.get("status") or ""), "Needs Data")
        rows.append({"zone_id": item["subject"], "decision": decision,
            "reason": str(item.get("reason") or "Canonical reason unavailable."),
            "planned_duration_minutes": item.get("planned_duration_minutes"),
            "feasible_window": item.get("preferred_window")})
    return sorted(rows, key=lambda row: row["zone_id"])


def _contained(status):
    return {"success": False, "status": status, "notify_owner": False,
            "telegram_sends": 0, "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False}
