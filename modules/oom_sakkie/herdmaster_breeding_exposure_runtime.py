"""Authenticated adapter for grouped HERDMASTER breeding facts.

The adapter owns no parser, Telegram transport, or persistence model.  It
accepts already-resolved semantic rows, creates the existing protected claim,
and delegates confirmed execution to the HERDMASTER grouped contract.
"""
from __future__ import annotations

import hashlib
import json

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import build_buttons, create_claim
from modules.pig_weights.herdmaster_breeding_exposure_recovery import (
    build_grouped_preview,
    execute_grouped_preview,
)


ACTION_KIND = "herdmaster_breeding_grouped"


def handle_grouped_breeding_message(parsed, authority, *, claim_creator=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    rows = semantic.get("breeding_actions")
    if semantic.get("domain") != "herd_management" or not isinstance(rows, list):
        return {"handled": False}, 200
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    if not validates_gateway_owner_authority(authority) or owner != chat or authority.owner_user_id != owner:
        return {"handled": True, "success": False, "status": "breeding_group_owner_required", **_zero()}, 403
    generation = str(semantic.get("evidence_generation") or "").strip()
    if not generation:
        return {"handled": True, "success": False, "status": "breeding_evidence_generation_required",
                "answer": "I need the current herd evidence before I can prepare this group. Nothing was recorded.", **_zero()}, 409
    preview = build_grouped_preview({"rows": rows}, evidence_generation=generation)
    mission = "OOM-HERD-BREED-" + hashlib.sha256(
        f"{owner}|{parsed.get('provider_message_id')}|{json.dumps(rows, sort_keys=True)}".encode()
    ).hexdigest()[:24].upper()
    if preview.get("success") is not True:
        return {"handled": True, "success": False, "status": preview["status"],
                "errors": preview["errors"], "question_count": 1,
                "answer": "I could not bind the complete group. Please correct the listed facts once; nothing was recorded.",
                **_zero()}, 200
    creator = claim_creator or create_claim
    claim = creator(action_kind=ACTION_KIND, owner_user_id=owner, private_chat_id=chat,
                    mission_id=mission, provider_message_id=str(parsed.get("provider_message_id") or ""),
                    evidence_generation=generation, preview_payload=preview)
    return {"handled": True, "success": True, "status": "breeding_grouped_preview_ready",
            "mission_id": mission, "card_mission_id": mission,
            "preview": preview["preview"], "preview_sha256": preview["preview_sha256"],
            "confirmation_required": True, "callback_token": claim["callback_token"],
            "reply_markup": build_buttons(claim["callback_token"], grouped=True),
            "answer": _summary(preview["preview"]["rows"]), **_zero()}, 200


def execute_claimed_group(claimed, *, actor_id, connect_factory):
    preview = claimed.get("preview_payload") or {}
    return execute_grouped_preview(preview,
        confirmed_preview_sha256=str(preview.get("preview_sha256") or ""),
        actor_id=actor_id, connect_factory=connect_factory)


def _summary(rows):
    labels = ", ".join(str(row.get("label") or row.get("pig_id")) for row in rows)
    return (f"HERDMASTER preview: {len(rows)} animals ({labels}). This records only the displayed "
            "exposures or observations. It creates no mating, conception, pregnancy, movement or litter. "
            "Confirm the complete preview once, or request a change.")


def _zero():
    return {"writes_farm_data": False, "writes_matings": False, "writes_movements": False,
            "sends_telegram": False, "protected_actions_performed": False}
