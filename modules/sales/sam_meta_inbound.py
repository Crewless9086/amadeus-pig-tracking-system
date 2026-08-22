"""Read-only, fail-closed Meta referral attribution for SAM."""

from datetime import datetime, timedelta, timezone
from typing import Mapping

CONTRACT_VERSION = "sam_meta_inbound_attribution_v1"


def evaluate_meta_inbound_attribution(payload, *, expected_binding=None,
                                      binding_resolution=None, now=None,
                                      max_age_days=30):
    payload = payload if isinstance(payload, Mapping) else {}
    conversation = _mapping(payload.get("conversation"))
    content = _mapping(payload.get("content_attributes"))
    referral = _mapping(content.get("referral"))
    rows = (content, referral, _mapping(conversation.get("custom_attributes")),
            _mapping(conversation.get("additional_attributes")), payload)
    attribution_id = _first(rows, "attribution_identity")
    target_page_id = _first(rows, "target_page_id", "page_id", "recipient_id")
    post_id = _first(rows, "post_id", "source_post_id", "source_id")
    publication_value = _first(rows, "publication_time", "published_at")
    inbound_value = payload.get("created_at") or payload.get("timestamp")
    published = _instant(publication_value)
    observed = _instant(inbound_value)
    current = _aware(now or datetime.now(timezone.utc))
    expected = _mapping(expected_binding)
    resolution = _mapping(binding_resolution)
    expected_publication = _instant(expected.get("publication_time"))
    status, reason = "attributed", "exact_beacon_meta_identity_bound"
    if not attribution_id:
        status, reason = "absent", "attribution_identity_absent"
    elif resolution.get("success") is not True or resolution.get("status") != "resolved":
        status = "rejected" if resolution.get("status") == "rejected" else "unverified"
        reason = str(resolution.get("reason") or "canonical_publication_binding_unavailable")[:160]
    elif not all(expected.get(key) for key in (
            "attribution_identity", "post_id", "target_page_id",
            "publication_time", "publish_packet_id", "publication_binding_id")):
        status, reason = "unverified", "canonical_publication_binding_incomplete"
    elif not target_page_id:
        status, reason = "unverified", "target_page_identity_absent"
    elif target_page_id != str(expected.get("target_page_id") or "").strip():
        status, reason = "rejected", "target_page_identity_mismatch"
    elif attribution_id != str(expected.get("attribution_identity") or "").strip():
        status, reason = "rejected", "attribution_identity_mismatch"
    elif not post_id:
        status, reason = "unverified", "source_post_identity_absent"
    elif post_id != str(expected.get("post_id") or "").strip():
        status, reason = "rejected", "source_post_identity_mismatch"
    elif not publication_value:
        status, reason = "unverified", "publication_time_absent"
    elif not published:
        status, reason = "rejected", "publication_time_invalid"
    elif not expected_publication:
        status, reason = "unverified", "canonical_publication_time_invalid"
    elif published != expected_publication:
        status, reason = "rejected", "publication_time_mismatch"
    elif not inbound_value:
        status, reason = "unverified", "inbound_time_absent"
    elif not observed:
        status, reason = "rejected", "inbound_time_invalid"
    elif published > current or current - published > timedelta(days=max_age_days):
        status, reason = "stale", "publication_outside_attribution_window"
    elif observed > current:
        status, reason = "rejected", "inbound_time_in_future"
    elif observed < published:
        status, reason = "rejected", "inbound_precedes_publication"
    trusted = status == "attributed"
    return {
        "contract_version": CONTRACT_VERSION, "status": status, "reason": reason,
        "campaign_id": expected.get("attribution_identity", "") if trusted else "",
        "attribution_identity": expected.get("attribution_identity", "") if trusted else "",
        "post_id": expected.get("post_id", "") if trusted else "",
        "target_page_id": expected.get("target_page_id", "") if trusted else "",
        "sam_boundary": expected.get("sam_boundary", "") if trusted else "",
        "post_text": expected.get("post_text", "") if trusted else "",
        "publish_packet_id": expected.get("publish_packet_id", "") if trusted else "",
        "publication_binding_id": expected.get("publication_binding_id", "") if trusted else "",
        "binding_source": expected.get("binding_source", "") if trusted else "",
        "publication_time": expected_publication.isoformat() if trusted else "",
        "inbound_time": observed.isoformat() if observed else "",
        "binding_resolution_status": str(resolution.get("status") or "")[:80],
        "binding_resolution_reason": str(resolution.get("reason") or "")[:160],
        "customer_response_authority_granted": False, "creates_lead": False,
        "creates_order": False, "sends_message": False,
        "contains_customer_content": False,
    }


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _first(rows, *keys):
    for row in rows:
        for key in keys:
            value = str(row.get(key) or "").strip()
            if value:
                return value[:500]
    return ""


def _instant(value):
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return _aware(datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")))
    except (ValueError, TypeError, OSError):
        return None


def _aware(value):
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
