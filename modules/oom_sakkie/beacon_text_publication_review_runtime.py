"""Protected Oom Sakkie review adapter for canonical BEACON text-only packets."""
from __future__ import annotations

import html
from typing import Mapping

from modules.beacon.text_only_organic_review import (
    PACKET_CLASS, validate_text_only_owner_review,
)
from modules.beacon.weekly_owner_review_decisions import (
    record_weekly_owner_review_decision,
)
from modules.oom_sakkie.protected_action_claims import CALLBACK_PREFIX, create_claim


ACTION_KIND = "beacon_text_only_publication_review"
ZERO = {"posts_publicly": False, "calls_meta": False, "spends_money": False,
        "boosts_post": False, "schedules_post": False,
        "sends_customer_message": False, "writes_farm_data": False}


def present_text_only_publication_review(packet, parsed, *, connect_factory=None):
    """Create a bound claim and owner card model; never deliver or publish it."""
    mismatch = validate_text_only_owner_review(packet)
    if mismatch:
        return {"success": False, "status": mismatch, **ZERO}, 409
    parsed = parsed if isinstance(parsed, Mapping) else {}
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    provider_id = str(parsed.get("provider_message_id") or "")
    source = packet.get("source_identity") or {}
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    language = str(semantic.get("language") or packet.get("locale") or "en")
    af = language.casefold().startswith("af") or language.casefold() == "mixed"
    if not owner or owner != chat or owner != str(source.get("owner_user_id") or ""):
        return {"success": False, "status": "text_only_review_owner_binding_mismatch", **ZERO}, 403
    if chat != str(source.get("private_chat_id") or "") or not provider_id:
        return {"success": False, "status": "text_only_review_chat_binding_mismatch", **ZERO}, 403
    preview = {
        "contract_version": PACKET_CLASS,
        "packet_id": packet["packet_id"],
        "canonical_sha256": packet["canonical_sha256"],
        "proposal_id": packet["proposal_id"],
        "proposal_result_digest": packet["proposal_result_digest"],
        "page_id": packet["page_id"],
        "page_name": packet["page_name"],
        "channel": packet["channel"],
        "caption": packet["caption"],
        "caption_sha256": packet["caption_sha256"],
        "campaign_purpose": packet["campaign_purpose"],
        "review_expires_at": packet["review_expires_at"],
        "approval_replay_identity": packet["approval_replay_identity"],
        "owner_user_id": owner,
        "private_chat_id": chat,
        "media": [],
        "ui_language": "af" if af else "en",
    }
    claim = create_claim(
        action_kind=ACTION_KIND, owner_user_id=owner, private_chat_id=chat,
        mission_id=packet["packet_id"], provider_message_id=provider_id,
        evidence_generation=packet["canonical_sha256"], preview_payload=preview,
        ttl_minutes=_ttl_minutes(packet), connect_factory=connect_factory,
        supersede_active=False,
    )
    token = claim["callback_token"]
    buttons = {"inline_keyboard": [[
        {"text": "Keur goed" if af else "Approve", "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
        {"text": "Korrigeer" if af else "Correct", "callback_data": f"{CALLBACK_PREFIX}{token}:change"},
        {"text": "Wys af" if af else "Decline", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"},
    ]]}
    return {
        "handled": True, "success": True, "status": "text_only_publication_review_ready",
        "specialist": "BEACON", "mission_id": packet["packet_id"],
        "card_mission_id": packet["packet_id"], "packet": packet,
        "answer": render_text_only_owner_review(packet, language=language), "reply_markup": buttons,
        "callback_token": token, "preview_digest": claim["preview_digest"],
        "review_expires_at": claim["expires_at"], **ZERO,
    }, 200


def execute_text_only_publication_review(claimed, parsed, *,
                                         decision_recorder=record_weekly_owner_review_decision):
    """Record only the immutable weekly decision selected by a bound callback."""
    preview = claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"), Mapping) else {}
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    if (preview.get("contract_version") != PACKET_CLASS
            or claimed.get("evidence_generation") != preview.get("canonical_sha256")
            or claimed.get("mission_id") != preview.get("packet_id")
            or owner != str(preview.get("owner_user_id") or "")
            or chat != str(preview.get("private_chat_id") or "")
            or preview.get("media") != []):
        return {"success": False, "status": "text_only_review_claim_binding_mismatch", **ZERO}, 409
    selected = claimed.get("selected_action")
    mapped = {"approve": "approve", "decline": "reject"}.get(selected)
    if not mapped:
        return {"success": False, "status": "text_only_review_decision_invalid", **ZERO}, 400
    payload = {
        "packet_class": PACKET_CLASS, "packet_id": preview["packet_id"],
        "packet_version": "TEXT-ONLY-V1", "canonical_sha256": preview["canonical_sha256"],
        "caption_sha256": preview["caption_sha256"], "exact_caption": preview["caption"],
        "ordered_media_ids": [], "owner_confirmed_subject": "",
        "album_story": preview["campaign_purpose"], "channel": preview["channel"],
        "supersedes_packet_id": "",
        "decision": mapped,
        "owner_notes": "",
        "proposed_publication_datetime": "", "proposed_timezone": "",
    }
    result, status = decision_recorder(payload, owner_identity=owner)
    if result.get("success") is not True:
        return {**result, **ZERO}, status
    af = preview.get("ui_language") == "af"
    consequence = ({
        "approve": "Hierdie presiese hersieningspakket is goedgekeur. Niks is gepubliseer nie.",
        "decline": "Afgewys. Geen publikasiegesag is geskep nie.",
    } if af else {
        "approve": "Approved this exact review packet only. Nothing was published.",
        "decline": "Declined. No publication authority was created.",
    })[selected]
    return {
        **result, "status": "text_only_owner_decision_recorded",
        "selected_action": selected, "answer": consequence,
        "specialist": "BEACON", "mission_id": preview["packet_id"],
        "card_mission_id": preview["packet_id"],
        "reply_markup": {"inline_keyboard": []},
        "owner_visible_completion_policy": "verified_edit_or_new_message", **ZERO,
    }, status


def render_text_only_owner_review(packet, *, language="en"):
    af = str(language).casefold().startswith("af") or str(language).casefold()=="mixed"
    evidence = "; ".join(f"{key.replace('_', ' ')}: {value}" for key, value in packet["evidence"].items())
    if af:
        return "\n".join([
            "<b>BEACON — TEKS-ALLEEN ORGANIESE HERSIENING</b>", "",
            f"<b>Gehoor:</b> {html.escape(packet['audience'])}",
            f"<b>Doel:</b> {html.escape(packet['campaign_purpose'])}",
            f"<b>Blad/kanaal:</b> {html.escape(packet['page_name'])} ({html.escape(packet['page_id'])}) — Facebook organies",
            f"<b>Presiese kopie:</b> {html.escape(packet['caption'])}",
            "<b>Media:</b> Geen. Dit is 'n uitdruklike teks-alleen klas en maak geen media-aanspraak nie.",
            f"<b>Bewyse:</b> {html.escape(evidence)}",
            f"<b>Grens:</b> {html.escape(packet['evidence_boundary'])}",
            f"<b>SAM-roetering:</b> {html.escape(packet['sam_attribution_and_routing'])}",
            f"<b>Besluit-sperdatum:</b> {html.escape(packet['review_expires_at'])}",
            "<b>Meet later:</b> Bereik, betrokkenheid, gekwalifiseerde SAM-leidrade, omskakelings, voltooide verkope en toeskryfbare bruto wins bly Onbekend tot egte bewyse bestaan.",
            "<b>Keur goed:</b> teken slegs goedkeuring van hierdie presiese pakket aan; verskafferuitvoering bly 'n latere beskermde stap.",
            "<b>Korrigeer:</b> vereis 'n nuwe onveranderlike pakket en digest. <b>Wys af:</b> skep geen publikasiegesag nie.",
            "Geen plasing, skedulering, hupstoot, besteding, kliënteverbintenis of plaas-skrywe vind uit hierdie hersiening plaas nie.",
        ])
    return "\n".join([
        "<b>BEACON — TEXT-ONLY ORGANIC REVIEW</b>", "",
        f"<b>Audience:</b> {html.escape(packet['audience'])}",
        f"<b>Purpose:</b> {html.escape(packet['campaign_purpose'])}",
        f"<b>Page/channel:</b> {html.escape(packet['page_name'])} ({html.escape(packet['page_id'])}) — Facebook organic",
        f"<b>Exact copy:</b> {html.escape(packet['caption'])}",
        "<b>Media:</b> None. This is an explicit text-only class and makes no media claim.",
        f"<b>Evidence:</b> {html.escape(evidence)}",
        f"<b>Boundary:</b> {html.escape(packet['evidence_boundary'])}",
        f"<b>SAM routing:</b> {html.escape(packet['sam_attribution_and_routing'])}",
        f"<b>Decision deadline:</b> {html.escape(packet['review_expires_at'])}",
        "<b>Measure later:</b> Reach, engagement, qualified SAM leads, conversions, completed sales and attributable gross profit remain Unknown until genuine evidence exists.",
        "<b>Approve:</b> records approval of this exact packet only; provider execution remains a later protected step.",
        "<b>Correct:</b> requires a new immutable packet and digest. <b>Decline:</b> creates no publication authority.",
        "No post, schedule, boost, spend, customer commitment or farm write occurs from this review.",
    ])


def _ttl_minutes(packet):
    from datetime import datetime, timezone
    expiry = datetime.fromisoformat(packet["review_expires_at"])
    seconds = (expiry - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        raise ValueError("text_only_review_expired")
    return max(1, int(seconds // 60))
