"""Telegram adapter for the shared canonical litter first-treatment command."""
from __future__ import annotations

from typing import Mapping

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import create_claim
from modules.pig_weights.herdmaster_litter_first_treatment_action import (
    execute_first_treatment,
    load_first_treatment_evidence,
    preview_first_treatment,
    render_first_treatment_preview,
)
from modules.pig_weights.herdmaster_litter_first_treatment_intake import ACTION_KIND


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
        result, result_status = preview_first_treatment(
            facts,
            actor_id=owner,
            channel="telegram",
            source_reference=str(parsed.get("provider_message_id") or ""),
            connect_factory=connect_factory,
            evidence_loader=evidence_loader or load_first_treatment_evidence,
        )
    except (RuntimeError, OSError, ValueError):
        return {"handled": True, "success": False, "status": "litter_treatment_evidence_unavailable",
                "answer": "HERDMASTER could not safely refresh the litter evidence. Nothing was recorded.",
                "writes_farm_data": False}, 503
    if result.get("success") is not True:
        question = str(result.get("question") or "")
        gap = str(result.get("status") or "").startswith(
            "canonical_first_treatment_protocol"
        )
        return {"handled": True, **result,
                "answer": question or (
                    "The approved stock-standard first-treatment protocol is "
                    "not completely configured in canonical Farm settings. "
                    "Nothing was recorded; Anton does not need to repeat "
                    "product, dose, route or batch details."
                    if gap
                    else "The litter treatment facts conflict with canonical evidence. Nothing was recorded."
                ),
                "question_count": 1 if question else 0}, result_status
    preview = result["preview"]
    mission_id = "OOM-" + result["operation_id"]
    claim = (claim_creator or create_claim)(action_kind=ACTION_KIND, owner_user_id=owner,
        private_chat_id=chat, mission_id=mission_id,
        provider_message_id=str(parsed.get("provider_message_id") or ""),
        evidence_generation=preview["evidence_generation"], preview_payload=preview,
        connect_factory=connect_factory)
    return {"handled": True, "success": True, "status": "litter_first_treatment_preview_ready",
        "answer": render_first_treatment_preview(preview), "question_count": 0, "mission_id": mission_id,
        "card_mission_id": mission_id, "callback_token": claim["callback_token"],
        "preview_digest": claim["preview_digest"], "action_kind": ACTION_KIND,
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm and record", "callback_data": f"oompa:{claim['callback_token']}:confirm"},
            {"text": "Change", "callback_data": f"oompa:{claim['callback_token']}:change"},
            {"text": "Cancel", "callback_data": f"oompa:{claim['callback_token']}:cancel"}]]},
        "writes_farm_data": False}, 200


def execute_claimed_litter_first_treatment(claimed, parsed, *, connect_factory=None):
    preview = dict(claimed.get("preview_payload") or {})
    result, status = execute_first_treatment(
        preview.get("request") or {},
        actor_id=str(parsed.get("telegram_user_id") or ""),
        channel="telegram",
        source_reference=str(preview.get("source_reference") or ""),
        confirmation_binding=preview.get("confirmation_binding") or {},
        connect_factory=connect_factory,
    )
    if result.get("success") is not True:
        return result, status
    identity = preview.get("sow_name") or preview.get("sow_tag_number") or "the sow"
    answer = (f"First treatment recorded once for {identity}'s litter: "
              f"{preview['total_count']} canonical active piglets. "
              "HERDMASTER will reassess the litter through the existing follow-up cycle.")
    return {**result, "answer": answer,
            "follow_up_owner": "HERDMASTER", "reply_markup": {"inline_keyboard": []}}, status


def load_canonical_litter_treatment_evidence(*, connect_factory=None):
    """Backward-compatible name for the now shared evidence loader."""
    return load_first_treatment_evidence(connect_factory=connect_factory)

