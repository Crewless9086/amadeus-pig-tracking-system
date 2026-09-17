"""Typed, idempotent operational events and deterministic business-state replay."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


DOMAINS = {"leads", "conversations", "orders", "payments", "animals", "campaigns", "missions", "incidents", "approvals", "outcomes"}
AUTHORITY_TIERS = {"read", "observe", "draft", "owner_approved", "bounded_auto", "red_zone"}
PRIVACY_CLASSES = {"internal", "owner_private", "customer_personal", "sensitive_business"}
REQUIRED_FIELDS = {
    "event_type", "domain", "aggregate_type", "aggregate_id", "source_system",
    "authority_tier", "privacy_class", "occurred_at", "payload", "provenance",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def build_event(packet, *, recorded_at=None):
    """Validate and canonicalize one event without writing operational state."""
    packet = dict(packet or {})
    missing = sorted(field for field in REQUIRED_FIELDS if packet.get(field) in (None, ""))
    if missing:
        return {"accepted": False, "status": "event_fields_required", "missing_fields": missing}
    if packet["domain"] not in DOMAINS:
        return {"accepted": False, "status": "event_domain_invalid"}
    if packet["authority_tier"] not in AUTHORITY_TIERS:
        return {"accepted": False, "status": "event_authority_invalid"}
    if packet["privacy_class"] not in PRIVACY_CLASSES:
        return {"accepted": False, "status": "event_privacy_invalid"}
    if not isinstance(packet.get("payload"), dict) or not isinstance(packet.get("provenance"), dict):
        return {"accepted": False, "status": "event_object_fields_invalid"}
    if not packet["provenance"].get("source_ref"):
        return {"accepted": False, "status": "event_provenance_source_required"}
    occurred = _timestamp(packet["occurred_at"])
    recorded = _timestamp(recorded_at or packet.get("recorded_at") or utc_now())
    if not occurred or not recorded:
        return {"accepted": False, "status": "event_timestamp_invalid"}
    canonical = {
        "schema_version": str(packet.get("schema_version") or "1"),
        "event_type": str(packet["event_type"]),
        "domain": str(packet["domain"]),
        "aggregate_type": str(packet["aggregate_type"]),
        "aggregate_id": str(packet["aggregate_id"]),
        "source_system": str(packet["source_system"]),
        "source_record_id": str(packet.get("source_record_id") or ""),
        "authority_tier": str(packet["authority_tier"]),
        "privacy_class": str(packet["privacy_class"]),
        "occurred_at": occurred,
        "recorded_at": recorded,
        "freshness_at": _timestamp(packet.get("freshness_at") or occurred),
        "correlation_id": str(packet.get("correlation_id") or ""),
        "causation_id": str(packet.get("causation_id") or ""),
        "actor_type": str(packet.get("actor_type") or "system"),
        "actor_id": str(packet.get("actor_id") or ""),
        "payload": packet["payload"],
        "provenance": packet["provenance"],
    }
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    canonical["idempotency_key"] = str(packet.get("idempotency_key") or fingerprint)
    canonical["event_id"] = str(packet.get("event_id") or f"EVT-{fingerprint[:24].upper()}")
    canonical["late_event"] = canonical["occurred_at"] < canonical["recorded_at"]
    return {"accepted": True, "status": "event_ready", "event": canonical}


def replay_events(events, reducer=None, initial_state=None):
    """Replay valid unique events in stable business-time order."""
    reducer = reducer or default_projection_reducer
    state = dict(initial_state or {})
    accepted, rejected, seen = [], [], set()
    for raw in events or []:
        result = build_event(raw, recorded_at=(raw or {}).get("recorded_at"))
        if not result.get("accepted"):
            rejected.append(result)
            continue
        event = result["event"]
        key = event["idempotency_key"]
        if key in seen:
            continue
        seen.add(key)
        accepted.append(event)
    accepted.sort(key=lambda item: (item["occurred_at"], item["recorded_at"], item["event_id"]))
    for event in accepted:
        state = reducer(state, event)
    return {"status": "replay_complete", "state": state, "applied_count": len(accepted), "rejected": rejected, "event_ids": [item["event_id"] for item in accepted]}


def default_projection_reducer(state, event):
    state = dict(state or {})
    aggregates = dict(state.get("aggregates") or {})
    key = f"{event['domain']}:{event['aggregate_type']}:{event['aggregate_id']}"
    current = dict(aggregates.get(key) or {})
    current.update(event["payload"])
    current["last_event_id"] = event["event_id"]
    current["last_event_type"] = event["event_type"]
    current["as_of"] = event["occurred_at"]
    current["freshness_at"] = event["freshness_at"]
    aggregates[key] = current
    state["aggregates"] = aggregates
    return state


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""
