"""Exact-conversation Chatwoot workflow-state mutations for SAM Livestock."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Mapping

from modules.sales.sam_chatwoot_inbox_state import (
    SAM_STATE_LABELS,
    build_chatwoot_inbox_state_plan,
    build_new_inbound_reactivation_plan,
)


def apply_new_inbound_state(
    inbound: Mapping,
    *,
    environ=None,
    conversation_loader: Callable | None = None,
    label_writer: Callable | None = None,
) -> dict:
    """Reactivate only the exact conversation; never mark it read."""
    source = environ if environ is not None else os.environ
    conversation = _load_conversation(
        inbound, source, conversation_loader=conversation_loader
    )
    labels = _labels(conversation)
    plan = build_new_inbound_reactivation_plan(
        inbound=inbound, prior_labels=labels
    )
    if not plan["allowed"]:
        return {**plan, "applied": False}
    writer = label_writer or (
        lambda conversation_id, values: _write_labels(
            conversation_id, values, source
        )
    )
    result = writer(
        plan["conversation_id"], plan["replace_sam_state_labels"]
    )
    return {**plan, "applied": result.get("success") is True}


def apply_delivery_state(
    inbound: Mapping,
    decision: Mapping,
    provider_state: str,
    *,
    authoritative_latest_inbound_id: str,
    environ=None,
    conversation_loader: Callable | None = None,
    chronology_loader: Callable | None = None,
    label_writer: Callable | None = None,
    last_seen_writer: Callable | None = None,
) -> dict:
    """Apply labels and optional last-seen only after an exact fresh check."""
    source = environ if environ is not None else os.environ
    conversation = _load_conversation(
        inbound, source, conversation_loader=conversation_loader
    )
    existing = _labels(conversation)
    plan = build_chatwoot_inbox_state_plan(
        inbound=inbound,
        decision=decision,
        provider_state=provider_state,
        authoritative_latest_inbound_id=authoritative_latest_inbound_id,
    )
    if not plan["allowed"]:
        return {**plan, "applied": False}
    conversation_id = plan["identity"]["conversation_id"]
    if not _exact_latest_inbound(
        conversation_id,
        authoritative_latest_inbound_id,
        source,
        chronology_loader,
    ):
        return {
            **plan,
            "applied": False,
            "status": "chronology_changed_before_label_write",
        }
    labels = sorted(
        (set(existing) - SAM_STATE_LABELS)
        | set(plan["replace_sam_state_labels"])
    )
    writer = label_writer or (
        lambda conversation_id, values: _write_labels(
            conversation_id, values, source
        )
    )
    label_result = writer(conversation_id, labels)
    seen_result = {"success": False, "skipped": True}
    if plan["mark_exact_inbound_seen"]:
        if not _exact_latest_inbound(
            conversation_id,
            authoritative_latest_inbound_id,
            source,
            chronology_loader,
        ):
            return {
                **plan,
                "applied": False,
                "status": "chronology_changed_before_last_seen",
                "labels_after": labels,
                "last_seen_applied": False,
            }
        seen = last_seen_writer or (
            lambda conversation_id: _update_last_seen(
                conversation_id, source
            )
        )
        seen_result = seen(plan["identity"]["conversation_id"])
    return {
        **plan,
        "applied": (
            label_result.get("success") is True
            and (
                seen_result.get("success") is True
                if plan["mark_exact_inbound_seen"]
                else True
            )
        ),
        "labels_after": labels,
        "last_seen_applied": seen_result.get("success") is True,
    }


def _exact_latest_inbound(
    conversation_id, expected_inbound_id, environ, chronology_loader=None
):
    loader = chronology_loader or (
        lambda cid: _request(
            "GET",
            f"/api/v1/accounts/{_account(environ)}/conversations/{cid}/messages",
            environ,
        )
    )
    packet = loader(conversation_id) or {}
    messages = (
        packet.get("messages") or packet.get("payload")
        if isinstance(packet, Mapping)
        else None
    )
    if not isinstance(messages, list):
        return False
    public = [
        item for item in messages
        if isinstance(item, Mapping)
        and not bool(item.get("private"))
        and item.get("message_type") in (0, 1, "incoming", "outgoing")
    ]
    try:
        public.sort(
            key=lambda item: (
                int(item.get("created_at") or 0),
                int(item.get("id") or 0),
            )
        )
    except (TypeError, ValueError):
        return False
    incoming = [
        item for item in public
        if item.get("message_type") in (0, "incoming")
    ]
    if not incoming:
        return False
    return str(incoming[-1].get("id") or "") == str(expected_inbound_id or "")


def _load_conversation(inbound, environ, *, conversation_loader=None):
    conversation_id = str((inbound or {}).get("conversation_id") or "")
    if not conversation_id:
        return {}
    if conversation_loader:
        return conversation_loader(conversation_id) or {}
    return _request(
        "GET",
        f"/api/v1/accounts/{_account(environ)}/conversations/{conversation_id}",
        environ,
    )


def _labels(conversation):
    labels = conversation.get("labels") if isinstance(conversation, Mapping) else []
    return [str(value).strip() for value in (labels or []) if str(value).strip()]


def _write_labels(conversation_id, labels, environ):
    _request(
        "POST",
        f"/api/v1/accounts/{_account(environ)}/conversations/{conversation_id}/labels",
        environ,
        {"labels": list(labels)},
    )
    return {"success": True}


def _update_last_seen(conversation_id, environ):
    _request(
        "POST",
        f"/api/v1/accounts/{_account(environ)}/conversations/{conversation_id}/update_last_seen",
        environ,
        {},
    )
    return {"success": True}


def _request(method, path, environ, body=None):
    base = str(environ.get("CHATWOOT_BASE_URL") or "").rstrip("/")
    token = str(
        environ.get("CHATWOOT_API_ACCESS_TOKEN")
        or environ.get("CHATWOOT_API_TOKEN")
        or ""
    )
    if not base.startswith("https://") or not token:
        raise RuntimeError("chatwoot_state_configuration_unavailable")
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path,
        method=method,
        data=data,
        headers={
            "api_access_token": token,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def _account(environ):
    return str(environ.get("CHATWOOT_ACCOUNT_ID") or "147387")
