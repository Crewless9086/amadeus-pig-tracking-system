"""Canonical, non-executing Facebook organic text-only owner-review packet.

This module defines a distinct packet class.  It does not record a decision,
schedule work, call Meta, or grant publication authority.  Its output mirrors
the immutable fields consumed by Beacon's existing weekly review and organic
publication binding rails without pretending that absent media is approved
media.
"""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os

from modules.beacon.public_livestock_content_policy import assess_public_livestock_content


PACKET_CLASS = "beacon_facebook_organic_text_only_review/v1"
PACKET_VERSION = "TEXT-ONLY-V1"
CHANNEL = "Facebook Page organic"
AUTHORITY = {
    "publish": False,
    "meta_call": False,
    "upload": False,
    "scheduled": False,
    "send": False,
    "spend": False,
    "boost": False,
    "customer_commitment": False,
    "farm_write": False,
}
UNKNOWN_MEASURES = {
    "reach": "Unknown",
    "engagement": "Unknown",
    "qualified_sam_leads": "Unknown",
    "conversions": "Unknown",
    "completed_sales": "Unknown",
    "attributable_gross_profit": "Unknown",
}


def build_text_only_owner_review(result_envelope, *, page_id, page_name, now=None):
    """Translate one exact BMQ-04 result into an immutable text-only review."""
    envelope = result_envelope if isinstance(result_envelope, dict) else {}
    proposal = envelope.get("proposal")
    if not isinstance(proposal, dict):
        return _withheld("text_only_proposal_required")
    result_digest = _digest_text(envelope.get("result_digest"))
    if not result_digest:
        return _withheld("text_only_result_digest_required")
    supplied_media = proposal.get("media")
    text_only_media = (
        supplied_media in (None, [], {"assets": [], "exact_order": []})
        or (isinstance(supplied_media, dict)
            and supplied_media.get("status") == "text_only"
            and not supplied_media.get("asset_id"))
    )
    if not text_only_media:
        return _withheld("text_only_media_forbidden")
    if proposal.get("selected_media") not in (None, []):
        return _withheld("text_only_media_forbidden")
    source_binding = envelope.get("binding") if isinstance(envelope.get("binding"), dict) else {}
    proposal_id = _text(proposal.get("proposal_id") or proposal.get("packet_id"), 180)
    caption = _multiline(proposal.get("recommended_copy") or proposal.get("draft_caption"), 4000)
    locale = _text(proposal.get("language") or proposal.get("locale"), 40)
    audience = _text(proposal.get("audience"), 500)
    purpose = _text(
        proposal.get("campaign_purpose") or proposal.get("commercial_objective") or proposal.get("objective"),
        800,
    )
    evidence = proposal.get("evidence") or proposal.get("capacity_context")
    evidence_boundary = _text(proposal.get("evidence_boundary") or (
        "Awareness only; no price, stock, availability, reservation or sale claim."
        if (evidence or {}).get("sale_availability_inferred") is False else ""
    ), 1200)
    sam_routing = _text(proposal.get("sam_routing"), 800)
    missing = [
        name
        for name, value in (
            ("proposal_id", proposal_id), ("caption", caption),
            ("locale", locale), ("audience", audience),
            ("campaign_purpose", purpose), ("evidence_boundary", evidence_boundary),
            ("sam_routing", sam_routing), ("page_id", _text(page_id, 180)),
            ("page_name", _text(page_name, 180)),
            ("source_owner", _text(source_binding.get("owner"), 180)),
            ("source_chat", _text(source_binding.get("chat"), 180)),
            ("source_provider_message", _text(source_binding.get("provider_message_id"), 180)),
        )
        if not value
    ]
    if missing or not isinstance(evidence, dict):
        return _withheld("text_only_required_fields_missing", missing)
    sale_inferred = proposal.get("sale_availability_inferred")
    if sale_inferred is None and isinstance(evidence, dict):
        sale_inferred = evidence.get("sale_availability_inferred")
    if sale_inferred is not False:
        return _withheld("text_only_non_availability_boundary_required")
    if (proposal.get("channel") or proposal.get("intended_channel")) not in (CHANNEL, "Facebook Page"):
        return _withheld("text_only_channel_unsupported")
    if proposal.get("timing") not in (None, "owner_selection_required", "immediate_only"):
        return _withheld("text_only_scheduling_forbidden")
    if not _evidence_is_explicit(evidence):
        return _withheld("text_only_evidence_not_explicit")
    policy = assess_public_livestock_content(
        caption, objective="farm_awareness", campaign_lane="live_stock_awareness", media=[]
    )
    if not policy.get("allowed"):
        return _withheld("text_only_public_policy_failed", policy.get("blockers", []))
    expires_at = _expiry(now)
    core = {
        "packet_class": PACKET_CLASS,
        "packet_version": PACKET_VERSION,
        "proposal_id": proposal_id,
        "proposal_result_digest": result_digest,
        "source_identity": {
            "owner_user_id": _text(source_binding.get("owner"), 180),
            "private_chat_id": _text(source_binding.get("chat"), 180),
            "provider_message_id": _text(source_binding.get("provider_message_id"), 180),
        },
        "channel": CHANNEL,
        "page_id": _text(page_id, 180),
        "page_name": _text(page_name, 180),
        "caption": caption,
        "caption_sha256": sha256(caption.encode("utf-8")).hexdigest(),
        "locale": locale,
        "audience": audience,
        "campaign_purpose": purpose,
        "evidence": deepcopy(evidence),
        "evidence_boundary": evidence_boundary,
        "sale_availability_inferred": False,
        "sam_attribution_and_routing": sam_routing,
        "media": {"exact_order": [], "assets": []},
        "owner_confirmed_subject": "",
        "organic_only": True,
        "performance": deepcopy(UNKNOWN_MEASURES),
        "public_livestock_policy": deepcopy(policy),
        "approval_contract": {
            "action_kind": "beacon_text_only_organic_review",
            "owner_chat_card_binding_required": True,
            "expires_at": expires_at,
        },
        "authority": deepcopy(AUTHORITY),
        "next_gate": "protected_exact_owner_decision_required",
    }
    canonical_sha = sha256(_canonical(core)).hexdigest()
    packet_id = "BEACON-TEXT-ONLY-" + canonical_sha[:24].upper()
    return {
        **core,
        "packet_id": packet_id,
        "canonical_sha256": canonical_sha,
        "review_status": "awaiting_exact_owner_review",
        "review_expires_at": expires_at,
        "approval_replay_identity": packet_id + ":OWNER-DECISION",
        "choices": {
            "approve": "Authorise one later protected organic publication attempt for this exact digest only.",
            "correct": "Create a new immutable packet and digest; this packet remains unpublished.",
            "decline": "Record no publication authority and publish nothing.",
        },
    }


def validate_text_only_owner_review(packet):
    """Fail closed if any immutable or zero-authority field has drifted."""
    packet = packet if isinstance(packet, dict) else {}
    if packet.get("packet_class") != PACKET_CLASS or packet.get("packet_version") != PACKET_VERSION:
        return "text_only_packet_class_invalid"
    if packet.get("media") != {"exact_order": [], "assets": []} or packet.get("owner_confirmed_subject") != "":
        return "text_only_media_forbidden"
    if packet.get("channel") != CHANNEL or packet.get("organic_only") is not True:
        return "text_only_channel_unsupported"
    if packet.get("performance") != UNKNOWN_MEASURES:
        return "text_only_performance_must_be_unknown"
    if packet.get("authority") != AUTHORITY:
        return "text_only_authority_invalid"
    if packet.get("caption_sha256") != sha256(str(packet.get("caption") or "").encode("utf-8")).hexdigest():
        return "text_only_caption_drift"
    core = {key: deepcopy(packet.get(key)) for key in _CORE_FIELDS}
    if packet.get("canonical_sha256") != sha256(_canonical(core)).hexdigest():
        return "text_only_packet_digest_drift"
    expected_id = "BEACON-TEXT-ONLY-" + packet["canonical_sha256"][:24].upper()
    if packet.get("packet_id") != expected_id:
        return "text_only_packet_identity_drift"
    if packet.get("approval_replay_identity") != expected_id + ":OWNER-DECISION":
        return "text_only_approval_identity_drift"
    try:
        expiry = packet.get("approval_contract", {}).get("expires_at")
        if expiry != packet.get("review_expires_at"):
            return "text_only_review_expiry_drift"
        if datetime.fromisoformat(str(expiry)) <= datetime.now(timezone.utc):
            return "text_only_review_expired"
    except (TypeError, ValueError):
        return "text_only_review_expiry_invalid"
    return ""


def build_text_only_execution_packet(packet, *, publish_packet_id):
    """Produce the exact existing execution-envelope shape without executing it."""
    mismatch = validate_text_only_owner_review(packet)
    if mismatch:
        return {"success": False, "status": mismatch, **deepcopy(AUTHORITY)}
    publish_packet_id = _text(publish_packet_id, 180)
    if not publish_packet_id:
        return {"success": False, "status": "execution_packet_id_required", **deepcopy(AUTHORITY)}
    return {
        "success": True,
        "status": "text_only_execution_binding_candidate",
        "packet_class": PACKET_CLASS,
        "publish_packet_id": publish_packet_id,
        "weekly_packet_id": packet["packet_id"],
        "canonical_sha256": packet["canonical_sha256"],
        "selected_draft": {"exact_text": packet["caption"]},
        "exact_text": packet["caption"],
        "selected_assets": [],
        "owner_confirmed_subject": "",
        "campaign_lane": "live_stock_awareness",
        "objective": "farm_awareness",
        "channel": CHANNEL,
        "target_page_id": packet["page_id"],
        "approval_required": True,
        "owner_confirmation": "",
        "authorization_generation_id": "",
        "publication_execution_identity": "",
        "zero_spend": True,
        "execution_authorized": False,
        **deepcopy(AUTHORITY),
    }


def _evidence_is_explicit(evidence):
    if not evidence:
        return False
    for value in evidence.values():
        if value is None or value == "":
            return False
    return any(str(value).strip().lower() == "unknown" for value in evidence.values())


def load_text_only_owner_review(packet_id, *, database_url=None, environ=None):
    """Rebuild one packet only from the durable BMQ-04 Supabase result event."""
    source = environ if environ is not None else os.environ
    database_url = str(database_url or source.get("DATABASE_URL") or "").strip()
    if not database_url:
        return _withheld("text_only_canonical_store_unavailable")
    try:
        import psycopg
        with psycopg.connect(
            database_url, connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select review_json->'beacon_request', created_at
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_beacon_request'
                    order by created_at desc
                """)
                rows = cursor.fetchall()
    except Exception:
        return _withheld("text_only_canonical_store_unavailable")
    page_id = _text(source.get("FACEBOOK_PAGE_ID"), 180)
    page_name = _text(source.get("BEACON_FACEBOOK_PAGE_NAME"), 180)
    for stored, created_at in rows:
        result = stored.get("result") if isinstance(stored, dict) else None
        if not isinstance(result, dict):
            continue
        proposal = result.get("proposal") or {}
        if proposal.get("packet_type") != "live_stock_awareness_proposal":
            continue
        packet = build_text_only_owner_review(
            result, page_id=page_id, page_name=page_name,
            now=created_at if isinstance(created_at, datetime) else None,
        )
        if not packet_id or packet.get("packet_id") == packet_id:
            return packet
    return _withheld("text_only_canonical_packet_not_found")


def _withheld(status, blockers=None):
    return {
        "success": False, "review_status": "withheld", "status": status,
        "blockers": list(blockers or []), "media": {"exact_order": [], "assets": []},
        "performance": deepcopy(UNKNOWN_MEASURES), "authority": deepcopy(AUTHORITY),
    }


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest_text(value):
    value = str(value or "").strip().lower()
    return value if len(value) == 64 and all(c in "0123456789abcdef" for c in value) else ""


def _text(value, limit):
    return " ".join(str(value or "").strip().split())[:limit]


def _multiline(value, limit):
    return "\n".join(line.strip() for line in str(value or "").strip().splitlines())[:limit]


def _expiry(now):
    from datetime import timedelta
    instant = now or datetime.now(timezone.utc)
    return (instant + timedelta(days=7)).isoformat()


_CORE_FIELDS = (
    "packet_class", "packet_version", "proposal_id", "proposal_result_digest", "source_identity",
    "channel", "page_id", "page_name", "caption", "caption_sha256", "locale",
    "audience", "campaign_purpose", "evidence", "evidence_boundary",
    "sale_availability_inferred", "sam_attribution_and_routing", "media",
    "owner_confirmed_subject", "organic_only", "performance", "public_livestock_policy", "approval_contract",
    "authority", "next_gate",
)
