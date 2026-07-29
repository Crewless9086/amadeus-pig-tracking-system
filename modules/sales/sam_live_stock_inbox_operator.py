"""Provider-chronology-driven autonomous SAM Livestock inbox operation."""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Mapping

from modules.sales.sam_live_stock_runtime import (
    extract_live_stock_facts,
    load_sam_general_context,
    parse_chatwoot_inbound,
    resolve_contextual_sales_route,
    resolve_sam_general_inbound_identity,
)
from modules.sales.sam_sales_router import classify_sam_sales_lane


def operate_livestock_inbox(
    *,
    environ=None,
    conversation_page_loader: Callable | None = None,
    history_loader: Callable,
    inbound_processor: Callable,
    claim_exists: Callable,
    now=None,
) -> dict:
    """Process every independently eligible current inbound exactly once."""
    source = environ if environ is not None else os.environ
    clock = now or datetime.now(timezone.utc)
    page_loader = conversation_page_loader or (
        lambda page: _conversation_page(page, source)
    )
    first = page_loader(1)
    meta = (first.get("data") or {}).get("meta") or {}
    provider_total = int(meta.get("all_count") or 0)
    first_payload = (first.get("data") or {}).get("payload")
    if not isinstance(first_payload, list) or provider_total < len(first_payload):
        raise RuntimeError("chatwoot_inventory_page_invalid")
    rows = list(first_payload)
    page_count = max(1, math.ceil(provider_total / 25))

    def load_page(page):
        body = page_loader(page)
        data = body.get("data") if isinstance(body.get("data"), Mapping) else {}
        next_meta = data.get("meta") if isinstance(data.get("meta"), Mapping) else {}
        next_payload = data.get("payload")
        if (
            not isinstance(next_payload, list)
            or int(next_meta.get("all_count") or -1) != provider_total
        ):
            raise RuntimeError("chatwoot_inventory_changed")
        return page, list(next_payload)

    loaded = {}
    if page_count > 1:
        with ThreadPoolExecutor(max_workers=min(12, page_count - 1)) as pool:
            futures = [
                pool.submit(load_page, page)
                for page in range(2, page_count + 1)
            ]
            for future in as_completed(futures):
                page, payload = future.result()
                loaded[page] = payload
    for page in range(2, page_count + 1):
        rows.extend(loaded[page])
    identities = [str(row.get("id") or "") for row in rows]
    if not all(identities) or len(set(identities)) != len(identities):
        raise RuntimeError("chatwoot_inventory_identity_conflict")
    if len(identities) != provider_total:
        raise RuntimeError("chatwoot_inventory_incomplete")

    dispositions = []
    for row in rows:
        disposition = _inspect_and_operate(
            row,
            source=source,
            history_loader=history_loader,
            inbound_processor=inbound_processor,
            claim_exists=claim_exists,
            now=clock,
        )
        if disposition["queue_relevant"]:
            dispositions.append(disposition)
    summary = build_sam_status_summary(dispositions, observed_at=clock)
    return {
        "status": "sam_live_stock_inbox_operated",
        "inventory_count": len(rows),
        "provider_conversation_count": provider_total,
        "inventory_scope": "full_provider_conversation_inventory",
        "dispositions": dispositions,
        "customers_answered": sum(
            item.get("provider_confirmed") is True for item in dispositions
        ),
        "quarantines": sum(
            item.get("provider_state") == "provider_outcome_ambiguous"
            for item in dispositions
        ),
        "owner_decisions": sum(
            item.get("owner_decision_required") is True
            for item in dispositions
        ),
        "lane_active": True,
        "automatic_retry_authorized": False,
        "protected_authority": False,
        "owner_status_summary": summary,
    }


def _inspect_and_operate(
    row,
    *,
    source,
    history_loader,
    inbound_processor,
    claim_exists,
    now,
):
    conversation_id = str(row.get("id") or "")
    provider_latest = (
        row.get("last_non_activity_message")
        if isinstance(row.get("last_non_activity_message"), Mapping)
        else {}
    )
    provider_incoming = provider_latest.get("message_type") in (0, "incoming")
    provider_inbound_id = (
        str(provider_latest.get("id") or "") if provider_incoming else ""
    )
    if (
        provider_latest
        and (
            row.get("can_reply") is not True
            or not provider_incoming
            or not provider_inbound_id
        )
    ):
        return {
            "conversation_id": conversation_id,
            "inbound_message_id": provider_inbound_id,
            "queue_relevant": False,
            "eligible": False,
            "disposition": (
                "closed_window_reengagement_required"
                if row.get("can_reply") is not True
                else "awaiting_customer"
            ),
            "final_route": "",
            "provider_state": "",
            "provider_confirmed": False,
            "owner_decision_required": False,
            "reply": "",
            "latest_inbound_at": int(
                provider_latest.get("created_at") or 0
            ),
        }
    if (
        provider_inbound_id
        and claim_exists(conversation_id, provider_inbound_id)
    ):
        return {
            "conversation_id": conversation_id,
            "inbound_message_id": provider_inbound_id,
            "queue_relevant": True,
            "eligible": False,
            "disposition": "already_claimed",
            "final_route": "AUTO_SPECIALIST",
            "provider_state": "",
            "provider_confirmed": False,
            "owner_decision_required": False,
            "reply": "",
            "latest_inbound_at": int(
                provider_latest.get("created_at") or 0
            ),
        }
    history, status = history_loader(conversation_id, source)
    messages = [
        item
        for item in (history.get("messages") or [])
        if isinstance(item, Mapping)
        and item.get("message_type") in (0, 1, "incoming", "outgoing")
        and not bool(item.get("private"))
    ]
    messages.sort(
        key=lambda item: (
            int(item.get("created_at") or 0),
            int(item.get("id") or 0),
        )
    )
    latest = messages[-1] if messages else {}
    latest_incoming = latest.get("message_type") in (0, "incoming")
    inbound_id = str(latest.get("id") or "") if latest_incoming else ""
    meta = row.get("meta") if isinstance(row.get("meta"), Mapping) else {}
    sender = meta.get("sender") if isinstance(meta.get("sender"), Mapping) else {}
    payload = {
        **latest,
        "event": "message_created",
        "account": {"id": row.get("account_id") or "147387"},
        "conversation": {
            "id": conversation_id,
            "inbox": {
                "id": row.get("inbox_id"),
                "channel_type": "Channel::Whatsapp",
            },
        },
        "sender": {"id": sender.get("id"), "name": sender.get("name")},
    }
    parsed = parse_chatwoot_inbound(payload) if latest_incoming else {}
    if parsed:
        parsed = resolve_sam_general_inbound_identity(
            parsed,
            payload,
            environ=source,
            conversation_identity_loader=lambda _cid, _env=None: {
                "success": True,
                "status": "provider_inventory_identity_verified",
                "account_id": str(row.get("account_id") or "147387"),
                "conversation_id": conversation_id,
                "contact_id": str(sender.get("id") or ""),
                "inbox_id": str(row.get("inbox_id") or ""),
            },
        )
    facts = extract_live_stock_facts(parsed.get("content"), parsed) if parsed else {}
    raw_route = classify_sam_sales_lane(parsed.get("content") or "") if parsed else {}
    context = (
        load_sam_general_context(
            parsed,
            conversation_history_loader=lambda *_args, **_kwargs: history,
            environ=source,
        )
        if parsed
        else {}
    )
    contextual = (
        resolve_contextual_sales_route(
            parsed, facts, context.get("prior_sales_context")
        )
        if parsed
        else {}
    )
    livestock = bool(
        raw_route.get("lane") == "live_stock_sales"
        and float(raw_route.get("confidence") or 0) >= 0.8
    ) or contextual.get("preserve_live_stock_lane") is True
    exact_claim = bool(
        inbound_id and claim_exists(conversation_id, inbound_id)
    )
    open_window = bool(row.get("can_reply") is True)
    eligible = bool(
        status == 200
        and _history_is_complete(history)
        and latest_incoming
        and inbound_id
        and livestock
        and open_window
        and not exact_claim
    )
    result = inbound_processor(payload) if eligible else {}
    decision = result.get("sam_decision") if isinstance(result.get("sam_decision"), Mapping) else {}
    delivery = decision.get("routine_reply_delivery") if isinstance(decision.get("routine_reply_delivery"), Mapping) else {}
    outcome = delivery.get("delivery_outcome") if isinstance(delivery.get("delivery_outcome"), Mapping) else {}
    provider_state = str(outcome.get("delivery_state") or "")
    queue_relevant = bool(livestock or exact_claim)
    return {
        "conversation_id": conversation_id,
        "inbound_message_id": inbound_id,
        "queue_relevant": queue_relevant,
        "eligible": eligible,
        "disposition": (
            "processed"
            if eligible
            else "already_claimed"
            if exact_claim
            else "awaiting_customer"
            if livestock and not latest_incoming
            else "closed_window_reengagement_required"
            if livestock and not open_window
            else "not_livestock"
        ),
        "final_route": (
            "AUTO_SPECIALIST"
            if livestock
            else contextual.get("final_route") or raw_route.get("lane")
        ),
        "provider_state": provider_state,
        "provider_confirmed": provider_state in {
            "provider_delivered", "provider_read"
        },
        "owner_decision_required": bool(
            decision.get("protected_owner_exception_required")
            or decision.get("owner_gate_required")
        ),
        "reply": decision.get("suggested_reply_text") or "",
        "latest_inbound_at": int(latest.get("created_at") or 0),
    }


def _history_is_complete(history):
    """Accept the real Chatwoot history shape only when chronology is auditable."""
    if not isinstance(history, Mapping) or history.get("success") is False:
        return False
    messages = history.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    public = [
        item for item in messages
        if isinstance(item, Mapping) and not bool(item.get("private"))
    ]
    if not public:
        return False
    try:
        return all(
            str(item.get("id") or "").strip()
            and int(item.get("created_at")) >= 0
            for item in public
        )
    except (TypeError, ValueError):
        return False


def build_sam_status_summary(dispositions, *, observed_at=None):
    """Build the compact owner-facing status used by the safe brief path."""
    rows = list(dispositions or [])
    eligible = [row for row in rows if row.get("eligible") is True]
    awaiting_customer = [
        row for row in rows
        if row.get("disposition") == "awaiting_customer"
        or row.get("provider_confirmed") is True
    ]
    owner = [
        row for row in rows if row.get("owner_decision_required") is True
    ]
    quarantined = [
        row for row in rows
        if row.get("provider_state") == "provider_outcome_ambiguous"
        or row.get("disposition") == "already_claimed"
    ]
    closed = [
        row for row in rows
        if row.get("disposition")
        == "closed_window_reengagement_required"
    ]
    oldest = min(
        eligible,
        key=lambda row: int(row.get("latest_inbound_at") or 0),
        default={},
    )
    return {
        "lane_state": "active",
        "customers_answered_today": sum(
            row.get("provider_confirmed") is True for row in rows
        ),
        "customers_awaiting_sam": sum(
            row.get("eligible") is True
            and row.get("provider_confirmed") is not True
            for row in rows
        ),
        "customers_awaiting_customer_reply": len(awaiting_customer),
        "owner_decisions": len(owner),
        "quarantines": len(quarantined),
        "closed_window_reengagement": len(closed),
        "oldest_eligible_unanswered_lead": (
            str(oldest.get("conversation_id") or "")
        ),
        "last_successful_webhook_processing_time": (
            (observed_at or datetime.now(timezone.utc)).isoformat()
            if any(row.get("provider_confirmed") is True for row in rows)
            else ""
        ),
    }


def _conversation_page(page, environ):
    account = str(environ.get("CHATWOOT_ACCOUNT_ID") or "147387")
    inbox = str(environ.get("SAM_LIVE_STOCK_CHATWOOT_INBOX_ID") or "96568")
    query = urllib.parse.urlencode(
        {
            "inbox_id": inbox,
            "status": "all",
            "sort_by": "last_activity_at",
            "page": page,
        }
    )
    return _request(
        f"/api/v1/accounts/{account}/conversations?{query}", environ
    )


def _request(path, environ):
    base = str(environ.get("CHATWOOT_BASE_URL") or "").rstrip("/")
    token = str(
        environ.get("CHATWOOT_API_ACCESS_TOKEN")
        or environ.get("CHATWOOT_API_TOKEN")
        or ""
    )
    if not base.startswith("https://") or not token:
        raise RuntimeError("chatwoot_inventory_configuration_unavailable")
    request = urllib.request.Request(
        base + path,
        headers={"api_access_token": token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)
