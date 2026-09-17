"""Evidence-bound Chatwoot state plans for SAM Livestock."""

from __future__ import annotations

from typing import Mapping


CONTRACT_VERSION = "sam_chatwoot_inbox_state_v1"
LIVESTOCK_LANE = "live_stock_sales"
CONFIRMED_PROVIDER_STATES = {"provider_delivered", "provider_read"}
QUARANTINED_PROVIDER_STATES = {
    "chatwoot_accepted_unverified",
    "provider_outcome_ambiguous",
}
SAM_STATE_LABELS = {
    "new_customer_inbound",
    "awaiting_customer",
    "qualification_in_progress",
    "owner_decision_required",
    "delivery_quarantined_do_not_retry",
    "closed_window_reengagement_required",
    "handled",
}


def build_chatwoot_inbox_state_plan(
    *,
    inbound: Mapping,
    decision: Mapping,
    provider_state: str,
    authoritative_latest_inbound_id: str = "",
    explicit_reviewed_disposition: bool = False,
) -> dict:
    """Build an exact-conversation plan; this function performs no writes."""
    inbound = dict(inbound or {})
    decision = dict(decision or {})
    identity = {
        "account_id": _clean(inbound.get("account_id")),
        "inbox_id": _clean(inbound.get("inbox_id")),
        "conversation_id": _clean(inbound.get("conversation_id")),
        "contact_id": _clean(inbound.get("contact_id")),
        "inbound_message_id": _clean(inbound.get("message_id")),
    }
    identity_complete = all(identity.values())
    chronology_current = bool(
        _clean(authoritative_latest_inbound_id)
        and _clean(authoritative_latest_inbound_id)
        == identity["inbound_message_id"]
    )
    livestock = (
        decision.get("sales_lane") == LIVESTOCK_LANE
        and decision.get("specialist_lane_selected") is True
    )
    confirmed = provider_state in CONFIRMED_PROVIDER_STATES
    quarantined = provider_state in QUARANTINED_PROVIDER_STATES
    missing = {
        _field_name(value)
        for value in decision.get("missing_fields") or []
        if isinstance(value, str)
    }
    protected = bool(
        decision.get("owner_gate_required")
        or decision.get("protected_owner_exception_required")
        or decision.get("owner_review_required")
    )
    labels = set()
    if livestock and quarantined:
        labels.add("delivery_quarantined_do_not_retry")
    elif livestock and confirmed:
        labels.add("awaiting_customer")
        if missing:
            labels.add("qualification_in_progress")
        if protected:
            labels.add("owner_decision_required")
    elif livestock and explicit_reviewed_disposition and protected:
        labels.add("owner_decision_required")

    mark_seen = bool(
        identity_complete
        and chronology_current
        and livestock
        and (confirmed or explicit_reviewed_disposition)
        and not quarantined
    )
    allowed = bool(
        identity_complete
        and chronology_current
        and livestock
        and (confirmed or quarantined)
    )
    return {
        "version": CONTRACT_VERSION,
        "allowed": allowed,
        "identity": identity,
        "provider_state": provider_state,
        "mark_exact_inbound_seen": mark_seen,
        "update_last_seen_request": (
            {
                "method": "POST",
                "path": (
                    f"/api/v1/accounts/{identity['account_id']}/conversations/"
                    f"{identity['conversation_id']}/update_last_seen"
                ),
                "bound_inbound_message_id": identity["inbound_message_id"],
            }
            if mark_seen
            else {}
        ),
        "replace_sam_state_labels": sorted(labels),
        "preserve_non_sam_labels": True,
        "preserve_assignment": True,
        "preserve_status": True,
        "close_or_resolve": False,
        "broad_cleanup": False,
        "automatic_retry_prohibited": quarantined,
        "writes_performed": False,
        "blockers": [
            name
            for name, passed in (
                ("exact_identity_complete", identity_complete),
                ("authoritative_latest_inbound_matches", chronology_current),
                ("livestock_specialist_lane", livestock),
                (
                    "provider_confirmed_or_quarantined",
                    confirmed or quarantined,
                ),
            )
            if not passed
        ],
    }


def build_new_inbound_reactivation_plan(*, inbound: Mapping, prior_labels) -> dict:
    """Return the exact label transition for a genuinely new inbound."""
    inbound = dict(inbound or {})
    conversation_id = _clean(inbound.get("conversation_id"))
    inbound_message_id = _clean(inbound.get("message_id"))
    labels = {str(value).strip() for value in (prior_labels or []) if str(value).strip()}
    preserved = labels - SAM_STATE_LABELS
    preserved.add("new_customer_inbound")
    return {
        "version": CONTRACT_VERSION,
        "allowed": bool(conversation_id and inbound_message_id),
        "conversation_id": conversation_id,
        "inbound_message_id": inbound_message_id,
        "replace_sam_state_labels": sorted(preserved),
        "removed_sam_state_labels": sorted(labels & SAM_STATE_LABELS),
        "preserve_non_sam_labels": True,
        "preserve_assignment": True,
        "preserve_status": True,
        "mark_seen": False,
        "writes_performed": False,
    }


def _field_name(value):
    return str(value).split(".")[-1].strip().lower()


def _clean(value):
    return str(value or "").strip()[:120]
