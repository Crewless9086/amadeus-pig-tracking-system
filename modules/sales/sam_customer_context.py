"""Canonical retained customer context projected from SAM's durable event rail."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Mapping


DATABASE_URL_ENV = "DATABASE_URL"
CONTEXT_VERSION = "sam_canonical_customer_context_v1"
RETAINED_FACT_FIELDS = (
    "customer_language",
    "sales_lane",
    "category",
    "quantity",
    "sex",
    "sex_split",
    "weight_range",
    "cuts",
    "animal_requirements",
    "location",
    "town",
    "timing",
    "delivery_timing",
    "campaign_id",
    "campaign_source",
    "source_context",
    "quote_id",
    "quote_status",
    "order_id",
    "order_status",
    "payment_status",
    "current_conversation_goal",
    "last_unanswered_question",
)


def canonical_customer_identity(inbound: Mapping[str, Any]) -> dict[str, Any]:
    """Return a non-reversible identity from verified provider evidence."""
    inbound = inbound if isinstance(inbound, Mapping) else {}
    account_id = _clean(inbound.get("account_id"), 100)
    phone = _normal_phone(inbound.get("customer_phone"))
    contact_id = _clean(inbound.get("contact_id"), 100)
    if not account_id:
        return {"resolved": False, "status": "account_identity_required"}
    if phone:
        identity_type, value = "normalized_phone", phone
    elif contact_id:
        identity_type, value = "provider_contact", contact_id
    else:
        return {"resolved": False, "status": "customer_identity_evidence_required"}
    digest = hashlib.sha256(f"{account_id}|{identity_type}|{value}".encode()).hexdigest()
    return {
        "resolved": True,
        "status": "canonical_customer_identity_resolved",
        "canonical_customer_id": f"SAM-CUSTOMER-{digest[:32].upper()}",
        "identity_type": identity_type,
        "account_id": account_id,
        "contains_private_identity": False,
    }


def load_canonical_customer_context(
    inbound: Mapping[str, Any],
    database_url: str | None = None,
    *,
    connect_factory=None,
    limit: int = 80,
) -> dict[str, Any]:
    """Read retained facts across conversations; never writes or sends."""
    inbound = dict(inbound or {})
    identity = canonical_customer_identity(inbound)
    if not identity.get("resolved"):
        return _empty(identity.get("status") or "identity_unresolved", identity)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url and connect_factory is None:
        return _empty("database_url_not_configured", identity)
    try:
        if connect_factory is None:
            import psycopg
            connection_context = psycopg.connect(database_url, connect_timeout=10)
        else:
            connection_context = connect_factory()
        with connection_context as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select chatwoot_conversation_id, chatwoot_message_id,
                           channel, facts_json, decision_json, created_at
                    from public.sam_live_stock_conversation_review_events
                    where source_agent = 'sam_live_stock_backend'
                      and event_source in ('chatwoot_inbound', 'sam_live_stock_direct_inbound')
                      and coalesce(decision_json->'inbound'->>'account_id', '') = %s
                      and (
                        (%s <> '' and regexp_replace(
                          coalesce(decision_json->'inbound'->>'customer_phone', ''),
                          '[^0-9]', '', 'g'
                        ) = %s)
                        or
                        (%s = '' and %s <> '' and
                          coalesce(decision_json->'inbound'->>'contact_id', '') = %s)
                      )
                    order by created_at desc, review_event_id desc
                    limit %s
                    """,
                    (
                        identity["account_id"],
                        _normal_phone(inbound.get("customer_phone")),
                        _normal_phone(inbound.get("customer_phone")),
                        _normal_phone(inbound.get("customer_phone")),
                        _clean(inbound.get("contact_id"), 100),
                        _clean(inbound.get("contact_id"), 100),
                        max(1, min(int(limit), 200)),
                    ),
                )
                rows = list(cursor.fetchall() or [])
    except Exception as exc:
        return {
            **_empty("canonical_customer_context_read_failed", identity),
            "error_type": exc.__class__.__name__,
        }
    return project_canonical_customer_context(rows, identity=identity)


def project_canonical_customer_context(rows, *, identity=None) -> dict[str, Any]:
    """Pure chronological projection used by runtime and application readers."""
    retained: dict[str, Any] = {}
    conversations: list[str] = []
    latest_goal = ""
    last_question = ""
    latest_at = ""
    for row in reversed(list(rows or [])):
        conversation_id, _message_id, _channel, raw_facts, raw_decision, created_at = row
        facts = _json_object(raw_facts)
        decision = _json_object(raw_decision)
        decision_inbound = decision.get("inbound") if isinstance(decision.get("inbound"), dict) else {}
        for key in RETAINED_FACT_FIELDS:
            value = facts.get(key)
            if _present(value):
                retained[key] = value
        if _present(decision_inbound.get("customer_name")):
            retained["customer_name"] = decision_inbound["customer_name"]
        goal = _clean(decision.get("next_action"), 120)
        if goal and goal not in {"no_reply_needed", "escalate"}:
            latest_goal = goal
        reply = _clean_multiline(decision.get("suggested_reply_text"), 1800)
        if "?" in reply:
            last_question = reply.rsplit("?", 1)[0].rsplit(".", 1)[-1].strip() + "?"
        elif decision.get("customer_send_confirmed") is True:
            last_question = ""
        conversation_id = _clean(conversation_id, 100)
        if conversation_id and conversation_id not in conversations:
            conversations.append(conversation_id)
        latest_at = str(created_at or latest_at)
    if latest_goal:
        retained["current_conversation_goal"] = latest_goal
    if last_question:
        retained["last_unanswered_question"] = last_question
    return {
        "success": True,
        "status": "canonical_customer_context_loaded" if rows else "canonical_customer_context_empty",
        "version": CONTEXT_VERSION,
        "read_only": True,
        "canonical_identity": dict(identity or {}),
        "interest": retained,
        "conversation_ids": conversations,
        "source": "supabase.sam_live_stock_conversation_review_events",
        "latest_evidence_at": latest_at,
        "event_count": len(list(rows or [])),
        "writes_performed": False,
    }


def _empty(status, identity):
    return {
        "success": status == "canonical_customer_context_empty",
        "status": status,
        "version": CONTEXT_VERSION,
        "read_only": True,
        "canonical_identity": dict(identity or {}),
        "interest": {},
        "conversation_ids": [],
        "source": "supabase.sam_live_stock_conversation_review_events",
        "writes_performed": False,
    }


def _json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _normal_phone(value):
    return re.sub(r"[^0-9]", "", str(value or ""))[:30]


def _present(value):
    return bool(value) if isinstance(value, (dict, list, bool)) else bool(str(value or "").strip())


def _clean(value, limit=300):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _clean_multiline(value, limit=1800):
    return "\n".join(line.strip() for line in str(value or "").splitlines() if line.strip())[:limit]
