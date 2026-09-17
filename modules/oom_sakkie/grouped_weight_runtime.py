"""Authenticated grouped natural-weight preview through existing governed preflight."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.herdmaster_weight_preview import preview_grouped_herd_weights
from modules.oom_sakkie.owner_response_composer import compose_weight_preview
from modules.oom_sakkie.protected_action_claims import build_buttons, canonical_preview_digest, create_claim
from modules.pig_weights.canonical_grouped_preview import preview_prepared_owner_text

_MULTI_WEIGHT = re.compile(r"(?:(?:pig|vark)\s+)?[A-Za-z0-9-]+\s+\d+(?:[.,]\d+)?\s*kg", re.I)

def handle_grouped_weight_message(parsed, authority, *, readiness_loader=None, preflight=None,
                                  pen_loader=None, claim_creator=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    text = str(parsed.get("text") or "")
    if semantic.get("domain") != "herd_management" or len(re.findall(r"\d+(?:[.,]\d+)?\s*kg\b",text,re.I)) < 2:
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
    if pen_loader is None:
        from modules.pig_weights.farm_supabase_read_service import get_pens
        pen_loader=get_pens
    readiness=readiness_loader()
    pen_snapshot=pen_loader() or []
    pen_lookup={}
    for pen in pen_snapshot:
        if not isinstance(pen,dict):continue
        pid=str(pen.get("pen_id") or pen.get("Pen_ID") or "")
        for value in (pid,pen.get("pen_name"),pen.get("Pen_Name"),pen.get("name")):
            if str(value or "").strip():pen_lookup.setdefault(str(value).strip().casefold(),[]).append(pid)
    preview = preview_grouped_herd_weights(text, weight_date=observed.date().isoformat(),
        readiness=readiness, preflight=preflight, pen_lookup=pen_lookup)
    mission = "OOM-HERD-WEIGHTS-" + hashlib.sha256(
        f"{owner}|{parsed.get('provider_message_id')}|{text}".encode()).hexdigest()[:24].upper()
    if preview.get("success") is not True:
        return {"handled": True, "success": False, "status": preview.get("status"),
                "mission_id": mission, "card_mission_id": mission,
                "answer": preview.get("clarification"), "question_count": 1, **_zero()}, 200
    canonical=preview_prepared_owner_text(text,channel="oom_typed",
        effective_date=preview["weight_date"],pigs=readiness["pigs"],pens=pen_snapshot)
    if canonical.get("success") is not True:
        return {"handled":True,"success":False,"status":canonical.get("status"),
                "mission_id":mission,"card_mission_id":mission,
                "answer":"The canonical grouped preview did not accept every interpreted fact. Nothing was recorded.",
                "question_count":1,**_zero()},200
    legacy_rows=[(str(row.get("pig_id") or ""),format(float(row.get("weight_kg")),"g"),
        str(row.get("moved_to_pen_id") or "")) for row in preview["rows"]]
    canonical_rows=[(str(row.get("pig_id") or ""),format(float(row.get("weight_kg")),"g"),
        "" if row.get("moved_to_pen_id")=="Unknown" else str(row.get("moved_to_pen_id") or ""))
        for row in canonical["rows"]]
    if (legacy_rows!=canonical_rows or preview["weight_date"]!=canonical["effective_date"]):
        return {"handled":True,"success":False,"status":"canonical_grouped_preview_diverged",
                "mission_id":mission,"card_mission_id":mission,
                "answer":"The canonical grouped preview did not match every interpreted fact. Nothing was recorded.",
                "question_count":1,**_zero()},200
    payload={key:canonical[key] for key in
             ("contract_version","effective_date","rows","confirmation_required")}
    generation=hashlib.sha256(json.dumps(readiness,sort_keys=True,default=str).encode()).hexdigest()
    creator=claim_creator or create_claim
    try:
        claim=creator(action_kind="grouped_weights",owner_user_id=owner,private_chat_id=chat,
          mission_id=mission,provider_message_id=str(parsed.get("provider_message_id") or ""),
          evidence_generation=generation,preview_payload=payload)
    except Exception:
        return {"handled":True,"success":False,"status":"grouped_weight_claim_unavailable",
                "answer":"I retained the weights, but the protected preview could not be stored safely. Nothing was recorded.",**_zero()},503
    return {"handled": True, "success": True, "status": "grouped_weight_preview_ready",
        "specialist_identity": "HERDMASTER", "mission_id": mission, "card_mission_id": mission,
        "preview_id": preview["preview_id"], "weight_date": canonical["effective_date"],
        "mappings": canonical["rows"], "confirmation_required": canonical["confirmation_required"],
        "preview_digest":str(claim.get("preview_digest") or canonical_preview_digest("grouped_weights",payload)),
        "canonical_preview_digest":canonical["preview_digest"],
        "protected_claim_digest":str(claim.get("preview_digest") or canonical_preview_digest("grouped_weights",payload)),
        "action_kind":str(claim.get("action_kind") or "grouped_weights"),
        "canonical_preview":canonical,"evidence_generation":generation,
        "callback_token":claim["callback_token"],"reply_markup":build_buttons(claim["callback_token"],grouped=True),
        "answer": compose_weight_preview(preview["rows"],
            language="af" if str(semantic.get("language")).startswith("af") else "en",
            weight_date=preview["weight_date"],movement_pen_label=preview.get("movement_pen_label") or ""),
        **_zero()}, 200

def _zero():
    return {"writes_farm_data":False,"writes_weights":False,"hardware_commands":0,
            "protected_actions_performed":False}
