"""Immutable owner-approved family bindings on the existing canonical spine."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping

from modules.oom_sakkie.family_access import family_access_policy


EVENT_SOURCE = "oom_sakkie_family_authorization"
CONTRACT_VERSION = "oom_sakkie_family_authorization_v1"


def record_binding_decision(binding: Mapping[str, Any], *, environ=None, event_store=None) -> dict[str, Any]:
    """Record one exact binding once; replay is silent and conflicts fail closed."""
    source = dict(os.environ if environ is None else environ)
    canonical = _canonical(binding)
    source["OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"] = json.dumps([canonical])
    if not family_access_policy(source)["configuration_valid"]:
        return _safe("family_binding_invalid", success=False)
    identity = "OOM-FAMILY-AUTH-" + hashlib.sha256(
        canonical["telegram_user_id"].encode()).hexdigest()[:24].upper()
    digest = _digest(canonical)
    store = event_store or _event_store
    existing = list(store("load", identity, None) or ())
    if existing:
        exact = [row for row in existing if row.get("decision_digest") == digest]
        return {**_safe("family_binding_replay_noop" if len(exact) == len(existing)
                        else "family_binding_conflict", success=bool(exact) and len(exact) == len(existing)),
                "identity": identity, "decision_digest": digest, "created": False}
    payload = {"contract_version": CONTRACT_VERSION, "identity": identity,
        "decision_digest": digest, "binding": canonical, "state": "authorized"}
    recorded = store("record", identity, payload)
    if (not isinstance(recorded, Mapping) or recorded.get("success") is not True
            or recorded.get("created") is False):
        # A concurrent winner may now exist; compare it before returning ambiguity.
        concurrent = list(store("load", identity, None) or ())
        if len(concurrent) == 1 and concurrent[0].get("decision_digest") == digest:
            return {**_safe("family_binding_replay_noop"), "identity": identity,
                    "decision_digest": digest, "created": False}
        status = "family_binding_conflict" if concurrent else "family_binding_persistence_unavailable"
        return {**_safe(status, success=False),
                "identity": identity, "decision_digest": digest, "created": False}
    return {**_safe("family_binding_recorded"), "identity": identity,
            "decision_digest": digest, "created": True}


def _canonical(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {key: binding.get(key) for key in (
        "telegram_user_id", "role", "family_key", "permissions", "summary_domains",
        "authorization_id", "authorized_by_user_id", "authorized_at", "language")}


def _event_store(action: str, identity: str, payload: Mapping[str, Any] | None):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    if action == "load":
        with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL")) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'family_authorization'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_event_id=%s
                    order by created_at,review_event_id""", (EVENT_SOURCE, identity))
                return [row[0] for row in cursor.fetchall()]
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event)
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "family_authorization"},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": identity, "chatwoot_conversation_id": identity,
        "review_json": {"family_authorization": dict(payload or {})}, "decision_json": {},
        "facts_json": {}, "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: connect_bounded_rootline_postgres(
            database_url=os.environ.get("DATABASE_URL"), read_only=False))
    return {**result, "success": status < 400 and result.get("success") is True}


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _safe(status: str, *, success=True) -> dict[str, Any]:
    return {"success": success, "status": status, "telegram_sends": 0,
            "farm_writes": 0, "hardware_commands": 0}
