"""Read-only, fail-closed Meta referral attribution for SAM."""

from datetime import datetime, timedelta, timezone
from typing import Mapping

CONTRACT_VERSION = "sam_meta_inbound_attribution_v1"


def evaluate_meta_inbound_attribution(payload, *, expected_page_id="",
                                      expected_attribution_identity="", now=None,
                                      max_age_days=30):
    payload = payload if isinstance(payload, Mapping) else {}
    conversation = _mapping(payload.get("conversation"))
    content = _mapping(payload.get("content_attributes"))
    referral = _mapping(content.get("referral"))
    rows = (content, referral, _mapping(conversation.get("custom_attributes")),
            _mapping(conversation.get("additional_attributes")), payload)
    attribution_id = _first(rows, "attribution_identity")
    sam_boundary = _first(rows, "sam_boundary")
    target_page_id = _first(rows, "target_page_id", "page_id", "recipient_id")
    post_id = _first(rows, "post_id", "source_post_id", "source_id")
    published = _instant(_first(rows, "publication_time", "published_at"))
    observed = _instant(payload.get("created_at") or payload.get("timestamp"))
    current = _aware(now or datetime.now(timezone.utc))
    status, reason = "attributed", "exact_beacon_meta_identity_bound"
    if not attribution_id:
        status, reason = "absent", "attribution_identity_absent"
    elif not target_page_id:
        status, reason = "unverified", "target_page_identity_absent"
    elif expected_page_id and target_page_id != str(expected_page_id).strip():
        status, reason = "rejected", "target_page_identity_mismatch"
    elif expected_attribution_identity and attribution_id != str(expected_attribution_identity).strip():
        status, reason = "rejected", "attribution_identity_mismatch"
    elif not post_id:
        status, reason = "unverified", "source_post_identity_absent"
    elif published and (published > current or current - published > timedelta(days=max_age_days)):
        status, reason = "stale", "publication_outside_attribution_window"
    elif published and observed and observed < published:
        status, reason = "rejected", "inbound_precedes_publication"
    return {
        "contract_version": CONTRACT_VERSION, "status": status, "reason": reason,
        "campaign_id": attribution_id, "attribution_identity": attribution_id,
        "post_id": post_id, "target_page_id": target_page_id,
        "sam_boundary": sam_boundary,
        "publication_time": published.isoformat() if published else "",
        "inbound_time": observed.isoformat() if observed else "",
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
