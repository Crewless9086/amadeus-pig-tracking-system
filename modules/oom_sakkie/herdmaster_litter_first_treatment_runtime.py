"""Protected Telegram runtime for an existing litter's first treatment."""
from __future__ import annotations

import os
import hashlib
import json
from typing import Mapping

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest, create_claim
from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights.herdmaster_litter_first_treatment_intake import (
    ACTION_KIND, LitterTreatmentEvidenceError, prepare_litter_first_treatment_preview,
)
from modules.pig_weights.pig_weights_service import record_litter_newborn_health


def handle_litter_first_treatment_message(parsed: Mapping, authority, *, connect_factory=None,
                                          evidence_loader=None, claim_creator=None):
    parsed = dict(parsed or {})
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    facts = semantic.get("litter_first_treatment")
    if semantic.get("intent") != "record_litter_first_treatment" or not isinstance(facts, Mapping):
        return {"handled": False, "status": "litter_first_treatment_not_applicable"}, 200
    owner, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    if (not validates_gateway_owner_authority(authority) or not owner or owner != chat
            or "treatment" not in frozenset(getattr(authority, "capabilities", ()))):
        return {"handled": True, "success": False, "status": "litter_treatment_authority_required",
                "writes_farm_data": False}, 403
    try:
        evidence = (evidence_loader or load_canonical_litter_treatment_evidence)(connect_factory=connect_factory)
        result = prepare_litter_first_treatment_preview({"authenticated": True,
            "authenticated_principal_id": owner,
            "provider_message_id": str(parsed.get("provider_message_id") or ""),
            "litter_first_treatment": facts}, evidence)
    except (LitterTreatmentEvidenceError, RuntimeError, OSError, ValueError):
        return {"handled": True, "success": False, "status": "litter_treatment_evidence_unavailable",
                "answer": "HERDMASTER could not safely refresh the litter evidence. Nothing was recorded.",
                "writes_farm_data": False}, 503
    if result.get("success") is not True:
        question = str(result.get("question") or "")
        return {"handled": True, **result,
                "answer": question or "The litter treatment facts conflict with canonical evidence. Nothing was recorded.",
                "question_count": 1 if question else 0}, 200 if question else 409
    preview = result["preview"]
    mission_id = "OOM-" + result["operation_id"]
    claim = (claim_creator or create_claim)(action_kind=ACTION_KIND, owner_user_id=owner,
        private_chat_id=chat, mission_id=mission_id,
        provider_message_id=str(parsed.get("provider_message_id") or ""),
        evidence_generation=preview["evidence_generation"], preview_payload=preview,
        connect_factory=connect_factory)
    return {"handled": True, "success": True, "status": "litter_first_treatment_preview_ready",
        "answer": _preview_answer(preview), "question_count": 0, "mission_id": mission_id,
        "card_mission_id": mission_id, "callback_token": claim["callback_token"],
        "preview_digest": claim["preview_digest"], "action_kind": ACTION_KIND,
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
            {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
            {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"}]]},
        "writes_farm_data": False}, 200


def execute_claimed_litter_first_treatment(claimed, parsed, *, connect_factory=None):
    preview = dict(claimed.get("preview_payload") or {})
    fresh = load_canonical_litter_treatment_evidence(connect_factory=connect_factory)
    facts = {"sow_ref": preview.get("sow_pig_id"), "litter_ref": preview.get("litter_id"),
        "action_date": preview.get("action_date"),
        "earmarked": preview.get("earmarked"), "dose": preview.get("dose"),
        "route": preview.get("route"), "batch_lot_number": preview.get("batch_lot_number"),
        "notes": preview.get("notes")}
    for product in preview.get("products") or []:
        facts[product["treatment_type"] + "_product_ref"] = product.get("product_id")
    refreshed = prepare_litter_first_treatment_preview({"authenticated": True,
        "authenticated_principal_id": str(parsed.get("telegram_user_id") or ""),
        "provider_message_id": preview.get("provider_message_id"),
        "litter_first_treatment": facts}, fresh)
    if (refreshed.get("success") is not True or canonical_preview_digest(
            ACTION_KIND, refreshed.get("preview") or {}) != claimed.get("preview_digest")):
        return {"success": False, "status": "litter_treatment_evidence_changed_repreview_required",
                "writes_farm_data": False}, 409
    products = {item["treatment_type"]: item for item in preview.get("products") or []}
    detail = next(row["detail"] for row in fresh["litters"] if row["litter_id"] == preview["litter_id"])
    result, status = record_litter_newborn_health(preview["litter_id"], preview["action_date"],
        changed_by=str(parsed.get("telegram_user_id") or ""), earmarked=preview["earmarked"],
        antiparasitic_product_id=(products.get("antiparasitic") or {}).get("product_id", ""),
        deworming_product_id=(products.get("deworming") or {}).get("product_id", ""),
        vaccination_product_id=(products.get("vaccination") or {}).get("product_id", ""),
        dose=preview["dose"], route=preview["route"], batch_lot_number=preview["batch_lot_number"],
        notes=preview["notes"],
        dry_run=False, require_supabase=True, canonical_detail=detail,
        canonical_products=fresh["products"], protected_operation_id=claimed["mission_id"])
    if result.get("success") is not True:
        return {**result, "writes_farm_data": False}, status
    readback = farm_supabase_read_service.get_litter_detail(preview["litter_id"], connect_factory=connect_factory)
    if (not readback or readback.get("first_treatment_complete") is not True):
        return {**result, "success": False, "status": "litter_treatment_readback_recovery_required",
                "recovery_required": True}, 503
    identity = preview.get("sow_name") or preview.get("sow_tag_number") or "the sow"
    answer = (f"First treatment recorded once for {identity}'s litter: "
              f"{preview['total_count']} canonical active piglets. "
              "HERDMASTER will reassess the litter through the existing follow-up cycle.")
    return {**result, "answer": answer, "canonical_readback": readback,
            "follow_up_owner": "HERDMASTER", "reply_markup": {"inline_keyboard": []}}, 201


def load_canonical_litter_treatment_evidence(*, connect_factory=None):
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("select pig_id,tag_number,pig_name as name from public.current_canonical_pigs")
            animals = _rows(cursor)
    products = farm_supabase_read_service.get_products(connect_factory=connect_factory)
    litters = []
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("select litter_id from public.current_canonical_litters where lower(litter_status)='active'")
            litter_ids = [row[0] for row in cursor.fetchall()]
    for litter_id in litter_ids:
        detail = farm_supabase_read_service.get_litter_detail(litter_id, connect_factory=connect_factory)
        if detail:
            litters.append({"litter_id": litter_id, "sow_pig_id": detail.get("mother_pig_id"),
                "litter_status": detail.get("litter_status"), "active_count": detail.get("active_count"),
                "first_treatment_complete": detail.get("first_treatment_complete"),
                "first_treatment_partial": detail.get("first_treatment_partial"), "detail": detail})
    generation = "litter-treatment:" + hashlib.sha256(json.dumps(sorted(
        (row["litter_id"], row.get("active_count"), row.get("first_treatment_complete"),
         row.get("first_treatment_partial")) for row in litters), separators=(",", ":")).encode()).hexdigest()
    return {"evidence_generation": generation, "animals": animals, "litters": litters, "products": products}


def _connect(factory):
    if factory: return factory()
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _rows(cursor):
    names = [item.name if hasattr(item, "name") else item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _preview_answer(preview):
    identity = preview.get("sow_name") or preview.get("sow_tag_number") or "the sow"
    products = ", ".join(item["product_name"] for item in preview["products"])
    return (f"HERDMASTER first-treatment preview for {identity}'s litter: "
            f"{preview['total_count']} canonical active piglets; "
            f"{products}, {preview['dose']}, {preview['route']}, batch {preview['batch_lot_number']}. Confirm the exact protected record.")

