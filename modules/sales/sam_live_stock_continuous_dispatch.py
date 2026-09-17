"""Narrow Chatwoot-to-SAM Livestock continuous dispatch contract."""

from __future__ import annotations

import hashlib
from typing import Mapping


CONTRACT_VERSION = "sam_live_stock_continuous_dispatch_v1"


def build_continuous_dispatch(
    payload: Mapping,
    *,
    expected_account_id: str,
    expected_inbox_id: str,
    presented_webhook_token: str = "",
    expected_webhook_token: str = "",
    prior_consumed_inbound_ids=(),
    quarantined_inbound_ids=(),
) -> dict:
    """Validate one webhook event and preserve its exact inbound identity."""
    payload = dict(payload or {})
    conversation = (
        payload.get("conversation")
        if isinstance(payload.get("conversation"), Mapping)
        else {}
    )
    inbox = (
        conversation.get("inbox")
        if isinstance(conversation.get("inbox"), Mapping)
        else {}
    )
    sender = (
        payload.get("sender")
        if isinstance(payload.get("sender"), Mapping)
        else {}
    )
    message_id = _clean(payload.get("id"))
    conversation_id = _clean(conversation.get("id"))
    account_id = _clean(
        (payload.get("account") or {}).get("id")
        if isinstance(payload.get("account"), Mapping)
        else payload.get("account_id")
    )
    inbox_id = _clean(inbox.get("id") or conversation.get("inbox_id"))
    contact_id = _clean(sender.get("id"))
    message_type = str(payload.get("message_type") or "").strip().lower()
    incoming = message_type in {"0", "incoming"}
    public = payload.get("private") is not True
    event = _clean(payload.get("event")).lower()
    channel = _clean(inbox.get("channel_type")).lower()
    identity_complete = all(
        (account_id, inbox_id, conversation_id, contact_id, message_id)
    )
    same_inbound_consumed = message_id in {
        _clean(value) for value in prior_consumed_inbound_ids
    }
    same_inbound_quarantined = message_id in {
        _clean(value) for value in quarantined_inbound_ids
    }
    checks = {
        "webhook_authenticated": bool(
            len(expected_webhook_token) >= 32
            and presented_webhook_token == expected_webhook_token
        ),
        "message_created": event == "message_created",
        "incoming_public": incoming and public,
        "expected_account": account_id == _clean(expected_account_id),
        "expected_inbox": inbox_id == _clean(expected_inbox_id),
        "whatsapp_channel": channel in {
            "channel::whatsapp",
            "channel::whatsappcloud",
        },
        "exact_identity_complete": identity_complete,
        "same_inbound_not_consumed": not same_inbound_consumed,
        "same_inbound_not_quarantined": not same_inbound_quarantined,
    }
    should_relay = all(checks.values())
    return {
        "version": CONTRACT_VERSION,
        "should_relay": should_relay,
        "identity": {
            "account_id": account_id,
            "inbox_id": inbox_id,
            "conversation_id": conversation_id,
            "contact_id": contact_id,
            "inbound_message_id": message_id,
            "operation_id": _operation_id(
                account_id, inbox_id, conversation_id, contact_id, message_id
            ),
        },
        "checks": checks,
        "blockers": [name for name, passed in checks.items() if not passed],
        "prior_other_inbound_id_does_not_block": not same_inbound_consumed,
        "relay_path": (
            "/api/sales/channels/chatwoot/sam-live-stock/inbound"
            if should_relay
            else ""
        ),
        "automatic_retry_authorized": False,
        "writes_performed": False,
    }


def build_delivery_owner_exception(*, inbound: Mapping, facts: Mapping) -> dict:
    """Build one precise owner question without promising delivery."""
    inbound = dict(inbound or {})
    facts = dict(facts or {})
    location = _clean(facts.get("location"))
    delivery_requested = (
        facts.get("transport_expectation") == "delivery_requested"
    )
    eligible = bool(
        _clean(inbound.get("conversation_id"))
        and _clean(inbound.get("message_id"))
        and location
        and delivery_requested
    )
    return {
        "version": "sam_delivery_owner_exception_v1",
        "eligible": eligible,
        "conversation_id": _clean(inbound.get("conversation_id")),
        "inbound_message_id": _clean(inbound.get("message_id")),
        "location": location,
        "decision_required": (
            f"Confirm whether delivery to {location} can be offered and, "
            "if so, provide the approved non-binding delivery estimate."
            if eligible
            else ""
        ),
        "customer_delivery_promised": False,
        "customer_send_allowed": False,
        "telegram_required": eligible,
        "telegram_deduplication_key": (
            _operation_id(
                _clean(inbound.get("account_id")),
                _clean(inbound.get("inbox_id")),
                _clean(inbound.get("conversation_id")),
                _clean(inbound.get("contact_id")),
                _clean(inbound.get("message_id")),
            )
            if eligible
            else ""
        ),
        "writes_performed": False,
    }


def _operation_id(*parts):
    material = "|".join(parts)
    return "SAM-CONTINUOUS-" + hashlib.sha256(material.encode()).hexdigest()[:24].upper()


def _clean(value):
    return str(value or "").strip()[:160]
