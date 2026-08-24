"""Owner-scoped, delivery-aware read-only ROOTLINE reassessment contract."""

from __future__ import annotations
import hashlib, json
import re
from typing import Any, Callable, Mapping
from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan
from modules.oom_sakkie.rootline_material import rootline_material_digest


OWNER_PLAN_FINGERPRINT_VERSION = "rootline_owner_plan_semantics.v2"


def reassess_rootline(*, owner_user_id: str, chat_id: str, trigger: str,
                      specialist_loader: Callable[[], Mapping[str, Any]],
                      state_store: Callable[[str, str, Any], Any], language="en"):
    if not owner_user_id or owner_user_id != chat_id or not str(trigger or "").strip():
        return _contained("reassessment_binding_invalid")
    current = specialist_loader()
    if not isinstance(current, Mapping) or current.get("success") is not True:
        return _contained("rootline_reassessment_unavailable")
    material = _material_digest(current)
    # Material decisions can legitimately recur on a later operating date.
    # Date-scope the notification identity so a recurring decision cannot
    # alias an older delivered packet and fail its immutable date binding.
    operating_date = str(current.get("operating_date") or "")
    result_id = str(current.get("result_id") or "")
    evidence_generation = str(current.get("generation") or current.get("evidence_cutoff") or "")
    binding = hashlib.sha256(
        f"{owner_user_id}|{chat_id}|{operating_date}|{material}|{result_id}|{evidence_generation}".encode()
    ).hexdigest()
    identity = "OOM-ROOTLINE-REASSESS-" + binding[:24].upper()
    legacy_binding = hashlib.sha256(
        f"{owner_user_id}|{chat_id}|{material}".encode()
    ).hexdigest()
    legacy_identity = "OOM-ROOTLINE-REASSESS-" + legacy_binding[:24].upper()
    observation = _typed_observation(current, owner_user_id, chat_id, material)
    observed = state_store("record_observation", observation["identity"], observation)
    if not isinstance(observed, Mapping) or observed.get("success") is not True:
        return _contained("rootline_reassessment_observation_unproven")
    delivered = state_store("load_delivered", f"{owner_user_id}|{chat_id}", None) or {}
    current_identity = state_store("load_identity", identity, None) or {}
    current_answer = compose_daily_rootline_plan(current, language=language)
    current_owner_plan_fingerprint = _owner_plan_fingerprint(current_answer)
    # A fresher generation remains durable observation evidence, but is not
    # owner-notification material by itself. Daily and change rails share the
    # date + material identity and stay silent when the supported action did
    # not change.
    if (delivered.get("material_digest") == material
            and str(delivered.get("operating_date") or "") == operating_date
            and str(delivered.get("provider_message_id") or "")):
        return {**_result("rootline_reassessment_unchanged", material, notify=False),
                "operating_date": operating_date,
                "result_id": result_id,
                "evidence_generation": evidence_generation,
                "next_due_at": _declared_next_due(current),
                "evidence_cutoff": str(current.get("evidence_cutoff") or "")}
    delivered_owner_plan_fingerprint = _delivered_owner_plan_fingerprint(delivered)
    if (_exact_predecessor_binding(delivered, owner_user_id, chat_id, operating_date)
            and delivered_owner_plan_fingerprint
            and delivered_owner_plan_fingerprint == current_owner_plan_fingerprint):
        return {**_result("rootline_reassessment_unchanged", material, notify=False),
                "operating_date": operating_date,
                "result_id": result_id,
                "evidence_generation": evidence_generation,
                "next_due_at": _declared_next_due(current),
                "evidence_cutoff": str(current.get("evidence_cutoff") or "")}
    legacy = state_store("load_identity", legacy_identity, None) or {}
    legacy_state = str(legacy.get("delivery_state") or "")
    if legacy and str(legacy.get("operating_date") or "") == operating_date:
        identity = legacy_identity
    elif legacy_state in {"pending", "ambiguous"}:
        return _contained("rootline_reassessment_legacy_delivery_unresolved")
    packet = {"identity": identity, "owner_user_id": owner_user_id, "chat_id": chat_id,
              "trigger": trigger, "material_digest": material,
              "result_id": str(current.get("result_id") or ""),
              "operating_date": operating_date,
              "evidence_generation": str(current.get("generation") or current.get("evidence_cutoff") or ""),
              "evidence_cutoff": str(current.get("evidence_cutoff") or ""),
              "next_reassessment_at": _declared_next_due(current),
              "zones": _typed_zone_projection(current),
              "answer": current_answer,
              "owner_plan_fingerprint_version": OWNER_PLAN_FINGERPRINT_VERSION,
              "owner_plan_fingerprint": current_owner_plan_fingerprint,
              "delivery_state": "pending"}
    recorded = state_store("claim_pending", identity, packet)
    if not isinstance(recorded, Mapping) or recorded.get("success") is not True:
        return _contained("rootline_reassessment_persistence_unproven")
    existing = state_store("load_identity", identity, None) or packet
    if (any(str(existing.get(key) or "") != str(packet.get(key) or "")
            for key in ("owner_user_id", "chat_id", "material_digest"))
            or (str(existing.get("operating_date") or "")
                and str(existing.get("operating_date")) != operating_date)):
        return _contained("rootline_reassessment_binding_conflict")
    delivery_state = str(existing.get("delivery_state") or "pending")
    if delivery_state == "delivered":
        return _result("rootline_reassessment_replayed_noop", material, notify=False)
    if delivery_state == "ambiguous":
        return _contained("rootline_reassessment_delivery_ambiguous")
    status = "rootline_reassessment_changed" if recorded.get("created") is not False else "rootline_reassessment_delivery_pending"
    return {**_result(status, material, notify=True), "notification_identity": identity,
            "operating_date": operating_date,
            "result_id": packet["result_id"],
            "evidence_generation": packet["evidence_generation"],
            "next_due_at": _declared_next_due(current),
            "evidence_cutoff": str(current.get("evidence_cutoff") or ""),
            "answer": packet["answer"]}


def record_reassessment_delivery(*, identity: str, owner_user_id: str, chat_id: str,
                                 material_digest: str, delivery: Mapping[str, Any],
                                 operating_date: str = "", result_id: str = "",
                                 evidence_generation: str = "",
                                 state_store: Callable[[str, str, Any], Any]):
    if delivery.get("provider_delivery_confirmed") is True and delivery.get("provider_message_id"):
        payload = {"owner_user_id": owner_user_id, "chat_id": chat_id,
                   "material_digest": material_digest,
                   "delivery_state": "delivered",
                   "provider_message_id": str(delivery["provider_message_id"]),
                   "provider_timestamp": str(delivery.get("provider_timestamp") or "")}
        if operating_date:
            payload["operating_date"] = operating_date
        if result_id:
            payload["result_id"] = result_id
        if evidence_generation:
            payload["evidence_generation"] = evidence_generation
        return state_store("mark_delivered", identity, payload)
    if delivery.get("provider_delivery_ambiguous") is True:
        payload = {"owner_user_id": owner_user_id,
            "chat_id": chat_id, "material_digest": material_digest,
            "delivery_state": "ambiguous"}
        if operating_date:
            payload["operating_date"] = operating_date
        if result_id:
            payload["result_id"] = result_id
        if evidence_generation:
            payload["evidence_generation"] = evidence_generation
        return state_store("mark_ambiguous", identity, payload)
    return {"success": False, "status": "delivery_not_proven", "delivery_state": "pending"}


def _result(status, material, *, notify):
    return {"success": True, "status": status, "notify_owner": notify,
            "telegram_sends": 0, "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False, "material_digest": material}


def _material_digest(result):
    return rootline_material_digest(result)


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
            "feasible_window": item.get("preferred_window"),
            "lifecycle": dict(((result.get("irrigation_lifecycle") or {}).get(
                item["subject"]) or {}))})
    return sorted(rows, key=lambda row: row["zone_id"])


def _typed_observation(current, owner_user_id, chat_id, material):
    operating_date = str(current.get("operating_date") or "")
    evidence_generation = str(current.get("generation") or current.get("evidence_cutoff") or "")
    evidence_cutoff = str(current.get("evidence_cutoff") or "")
    result_id = str(current.get("result_id") or "")
    # Material identity deliberately controls owner notification suppression, while
    # observation identity also versions the canonical evidence snapshot.  Thus a
    # fresher unchanged decision is visible to owner status without being announced.
    identity_material = "|".join((owner_user_id, chat_id, operating_date, material,
                                  evidence_generation, evidence_cutoff, result_id))
    identity = "OOM-ROOTLINE-OBS-" + hashlib.sha256(identity_material.encode()).hexdigest()[:24].upper()
    return {"identity": identity, "owner_user_id": owner_user_id, "chat_id": chat_id,
        "operating_date": operating_date, "material_digest": material,
        "result_id": result_id,
        "evidence_generation": evidence_generation,
        "evidence_cutoff": evidence_cutoff,
        "next_reassessment_at": _declared_next_due(current),
        "zones": _typed_zone_projection(current), "delivery_state": "observation_only"}


def _contained(status):
    return {"success": False, "status": status, "notify_owner": False,
            "telegram_sends": 0, "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False}


def _exact_predecessor_binding(delivered, owner_user_id, chat_id, operating_date):
    return (str(delivered.get("delivery_state") or "") == "delivered"
            and str(delivered.get("provider_message_id") or "") != ""
            and str(delivered.get("owner_user_id") or "") == owner_user_id
            and str(delivered.get("chat_id") or "") == chat_id
            and str(delivered.get("operating_date") or "") == operating_date
            and str(delivered.get("identity") or "") != "")


def _stable_owner_plan(value):
    lines = []
    for raw in str(value or "").splitlines():
        line = " ".join(raw.split())
        folded = line.casefold()
        if (folded.startswith("<b>next automatic reassessment")
                or folded.startswith("<b>volgende outomatiese herbeoordeling")):
            # Only an explicitly approximate HH:MM clock token is volatile.
            # Keep the line, language, reassessment mode, conditions and any
            # fixed/deadline wording in the semantic identity.
            line = re.sub(r"\b(around|omtrent)\s+\d{1,2}:\d{2}\b",
                          r"\1 <volatile-clock>", line,
                          flags=re.IGNORECASE)
        lines.append(line)
    return "\n".join(lines).strip()


def _owner_plan_fingerprint(value):
    stable = _stable_owner_plan(value)
    if not stable:
        return ""
    return hashlib.sha256(
        f"{OWNER_PLAN_FINGERPRINT_VERSION}|{stable}".encode()
    ).hexdigest()


def _delivered_owner_plan_fingerprint(delivered):
    version = str(delivered.get("owner_plan_fingerprint_version") or "")
    fingerprint = str(delivered.get("owner_plan_fingerprint") or "")
    if version == OWNER_PLAN_FINGERPRINT_VERSION and len(fingerprint) == 64:
        return fingerprint
    # Exact historical pending packets already preserve the delivered owner
    # text. Derive the same versioned semantic identity for the one-time
    # transition without weakening recipient/date/provider binding.
    return _owner_plan_fingerprint(delivered.get("answer"))
