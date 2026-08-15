"""Canonical Control Tower feedback ingress and Shadow worker consumption.

The producer is called only behind the sealed private-action boundary.  The
worker consumes the resulting owner-private operational events.  Neither side
dispatches terminals, changes missions, or performs provider/farm actions.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Mapping

from modules.charlie.mission_store import (
    BOOTSTRAP_PORTFOLIO_ADMISSION,
    BOOTSTRAP_PORTFOLIO_MISSION_ID,
    get_mission,
)
from modules.charlie.environment import alias_environment
from modules.charlie.operational_event_store import append_operational_event, load_operational_events
from modules.charlie.private_policy import is_authenticated_private_action_context
from modules.charlie.shadow_control_tower import (
    compare_human_decision,
    record_shadow_proposal,
    shadow_enabled,
)

VERSION = "control_tower_feedback_ingress_v1"
ACTION = "reconcile_control_tower_feedback"
FEEDBACK_EVENT = "control_tower_feedback_recorded"
DECISION_EVENT = "control_tower_human_decision_recorded"
MISSION_ID = BOOTSTRAP_PORTFOLIO_MISSION_ID
SOURCE_KIND = "owner_pasted_terminal_feedback"
DECISION_SOURCE_KIND = "human_control_tower_decision"


def handle_control_tower_feedback(payload, *, runtime_context=None, environ=None,
                                  database_url=None, connect_factory=None,
                                  mission_reader=None):
    """Persist one authenticated feedback or later human-decision input."""
    if not shadow_enabled(environ):
        return _failure("shadow_control_tower_disabled", 403)
    if not _authenticated(runtime_context, environ):
        return _failure("control_tower_private_authentication_required", 403)
    if (runtime_context.authentication_scope != "core_private_owner"
            or runtime_context.existing_mission_id != MISSION_ID):
        return _failure("control_tower_mission_binding_denied", 409)
    action = payload if isinstance(payload, Mapping) else {}
    if action.get("action") != ACTION:
        return _failure("control_tower_feedback_action_invalid", 400)
    record_type = str(action.get("record_type") or "").strip()
    transaction = action.get("transaction") if isinstance(action.get("transaction"), Mapping) else {}
    error = (_validate_feedback_identity(transaction) if record_type == "feedback"
             else _validate_decision_identity(transaction) if record_type == "human_decision"
             else "")
    if error:
        return _failure(error, 400)
    loaded, loaded_status = (mission_reader or get_mission)(MISSION_ID)
    mission = (loaded.get("mission") or {}) if isinstance(loaded, Mapping) else {}
    if loaded_status >= 400 or not shadow_observation_eligible(mission):
        return _failure("control_tower_shadow_observation_not_eligible", 409)
    if record_type == "feedback":
        packet = _feedback_packet(transaction)
    elif record_type == "human_decision":
        decision = action.get("human_decision") if isinstance(action.get("human_decision"), Mapping) else {}
        required = ("human_decision_id", "actual_next_terminal", "actual_next_action",
                    "actual_continuation_prompt", "actual_owner_visible_result")
        if any(not str(decision.get(key) or "").strip() for key in required):
            return _failure("control_tower_human_decision_fields_required", 400)
        proposal = _proposal_for_feedback(transaction["feedback_transaction_id"],
            database_url=database_url, connect_factory=connect_factory)
        if not proposal:
            return _failure("control_tower_proposal_must_precede_decision", 409)
        original = _source_event(transaction["feedback_transaction_id"], FEEDBACK_EVENT,
            database_url=database_url, connect_factory=connect_factory)
        original_tx = ((original or {}).get("payload") or {}).get("transaction") or {}
        if not _decision_links_original_feedback(transaction, original_tx):
            return _failure("control_tower_decision_feedback_linkage_mismatch", 409)
        packet = _decision_packet(transaction, proposal, decision)
    else:
        return _failure("control_tower_feedback_record_type_invalid", 400)
    result, status = append_operational_event(packet, database_url=database_url,
                                              connect_factory=connect_factory)
    if result.get("success") and result.get("created") is False:
        durable = _source_event(transaction["feedback_transaction_id"], packet["event_type"],
            database_url=database_url, connect_factory=connect_factory)
        if not durable or _digest(durable.get("payload")) != _digest(packet["payload"]):
            return _failure("control_tower_feedback_replay_conflict", 409)
    return {**result, "feedback_transaction_id": transaction["feedback_transaction_id"],
            "observation_only": True, **_zero_authority()}, status


def process_pending_control_tower_feedback(*, environ=None, database_url=None,
                                           connect_factory=None, mission_reader=None):
    """Consume canonical feedback events from the existing durable worker."""
    if not shadow_enabled(environ):
        return {"success": True, "status": "shadow_control_tower_disabled",
                "processed_count": 0, "next_eligible_event": FEEDBACK_EVENT, **_zero_authority()}
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", limit=1000,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return {**loaded, "processed_count": 0, **_zero_authority()}
    mission_result, mission_status = (mission_reader or get_mission)(MISSION_ID)
    mission = (mission_result.get("mission") or {}) if isinstance(mission_result, Mapping) else {}
    if mission_status >= 400 or not shadow_observation_eligible(mission):
        return {"success": False, "status": "control_tower_shadow_observation_not_eligible",
                "processed_count": 0, **_zero_authority()}
    events = list(loaded.get("events") or [])
    trusted_feedback = {str(event.get("aggregate_id") or "") for event in events
        if event.get("event_type") == FEEDBACK_EVENT and _trusted_source_event(event)}
    proposal_feedback = {str(event.get("aggregate_id") or "") for event in events
        if event.get("event_type") == "shadow_control_tower_proposal_recorded"
        and str(event.get("aggregate_id") or "") in trusted_feedback}
    comparison_feedback = {str(event.get("aggregate_id") or "") for event in events
        if event.get("event_type") == "shadow_control_tower_human_comparison_recorded"
        and str(event.get("aggregate_id") or "") in trusted_feedback}
    processed, results = 0, []
    for event in events:
        if not _trusted_source_event(event):
            continue
        feedback_id = str(event.get("aggregate_id") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        if event.get("event_type") == FEEDBACK_EVENT and feedback_id not in proposal_feedback:
            result, code = record_shadow_proposal(payload.get("transaction") or {}, environ=environ,
                database_url=database_url, connect_factory=connect_factory)
            results.append({"feedback_transaction_id": feedback_id, "status": result.get("status"), "code": code})
            if code < 400:
                proposal_feedback.add(feedback_id); processed += 1
        elif event.get("event_type") == DECISION_EVENT and feedback_id not in comparison_feedback:
            result, code = compare_human_decision(payload.get("proposal") or {},
                payload.get("human_decision") or {}, environ=environ,
                database_url=database_url, connect_factory=connect_factory)
            results.append({"feedback_transaction_id": feedback_id, "status": result.get("status"), "code": code})
            if code < 400:
                comparison_feedback.add(feedback_id); processed += 1
    return {"success": all(item["code"] < 400 for item in results),
        "status": "control_tower_feedback_cycle_complete", "processed_count": processed,
        "results": results, "last_independent_result": results[-1] if results else {},
        "next_eligible_event": DECISION_EVENT if proposal_feedback - comparison_feedback else FEEDBACK_EVENT,
        **_zero_authority()}


def shadow_observation_eligible(mission):
    """Allow only the non-runnable CMQ bootstrap to be observed, never executed."""
    item = mission if isinstance(mission, Mapping) else {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    return (
        hmac.compare_digest(str(item.get("mission_id") or ""), MISSION_ID)
        and str(item.get("status") or "") == "paused"
        and metadata.get("portfolio_admission") == BOOTSTRAP_PORTFOLIO_ADMISSION
        and metadata.get("portfolio_classification") is None
        and BOOTSTRAP_PORTFOLIO_ADMISSION.get("runnable") is False
    )


def _authenticated(context, environ):
    if not is_authenticated_private_action_context(context):
        return False
    env = alias_environment(environ if isinstance(environ, Mapping) else os.environ)
    expected = str(env.get("CHARLIE_TELEGRAM_OWNER_USER_ID") or "").split(",")[0].strip()
    return bool(expected) and hmac.compare_digest(
        str(context.authenticated_principal_id or "").strip(), expected)


def _validate_feedback_identity(tx):
    required = ("feedback_transaction_id", "terminal_identity", "existing_mission_id",
        "worktree_identity", "feedback_occurred_at", "control_tower_reconciliation_id",
        "source_kind", "owner_pasted_feedback")
    if any(not str(tx.get(key) or "").strip() for key in required):
        return "control_tower_feedback_identity_required"
    if tx.get("source_kind") != SOURCE_KIND:
        return "control_tower_feedback_source_not_genuine"
    if tx.get("existing_mission_id") != MISSION_ID:
        return "control_tower_feedback_cross_mission_denied"
    try:
        parsed = datetime.fromisoformat(str(tx["feedback_occurred_at"]).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return "control_tower_feedback_timestamp_invalid"
    except (TypeError, ValueError):
        return "control_tower_feedback_timestamp_invalid"
    return ""


def _validate_decision_identity(tx):
    required = ("feedback_transaction_id", "terminal_identity", "existing_mission_id",
        "worktree_identity", "feedback_occurred_at", "feedback_reconciliation_id",
        "control_tower_reconciliation_id",
        "source_kind")
    if any(not str(tx.get(key) or "").strip() for key in required):
        return "control_tower_decision_identity_required"
    if tx.get("source_kind") != DECISION_SOURCE_KIND:
        return "control_tower_decision_source_invalid"
    if tx.get("existing_mission_id") != MISSION_ID:
        return "control_tower_feedback_cross_mission_denied"
    return ""


def _decision_links_original_feedback(decision_tx, original_tx):
    if not isinstance(original_tx, Mapping):
        return False
    for key in ("feedback_transaction_id", "terminal_identity", "existing_mission_id",
                "worktree_identity", "feedback_occurred_at"):
        if not hmac.compare_digest(str(decision_tx.get(key) or ""), str(original_tx.get(key) or "")):
            return False
    return hmac.compare_digest(str(decision_tx.get("feedback_reconciliation_id") or ""),
                               str(original_tx.get("control_tower_reconciliation_id") or ""))


def _feedback_packet(tx):
    feedback_id = str(tx["feedback_transaction_id"]).strip()
    reconciliation_id = str(tx["control_tower_reconciliation_id"]).strip()
    return _packet(FEEDBACK_EVENT, feedback_id, reconciliation_id,
        {"record_type": "feedback", "transaction": dict(tx),
         "owner_pasted_feedback_sha256": _digest(str(tx["owner_pasted_feedback"]))},
        str(tx["feedback_occurred_at"]))


def _decision_packet(tx, proposal, decision):
    feedback_id = str(tx["feedback_transaction_id"]).strip()
    decision_id = str(decision["human_decision_id"]).strip()
    packet = _packet(DECISION_EVENT, feedback_id, decision_id,
        {"record_type": "human_decision", "transaction_identity": _identity(tx),
         "proposal": proposal, "human_decision": dict(decision)},
        datetime.now(timezone.utc).isoformat())
    packet["provenance"]["source_ref"] = DECISION_SOURCE_KIND
    packet["provenance"].pop("owner_pasted", None)
    packet["provenance"]["human_decision_canonical"] = True
    return packet


def _packet(event_type, feedback_id, record_id, payload, occurred_at):
    return {"event_type": event_type, "domain": "missions",
        "aggregate_type": "control_tower_feedback_transaction", "aggregate_id": feedback_id,
        "source_system": VERSION, "source_record_id": record_id, "authority_tier": "observe",
        "privacy_class": "owner_private", "actor_type": "control_tower_reconciler",
        "actor_id": "HUMAN_CONTROL_TOWER", "occurred_at": occurred_at, "payload": payload,
        "provenance": {"source_ref": SOURCE_KIND, "owner_pasted": True,
            "human_control_tower_authoritative": True},
        "idempotency_key": f"{event_type}:{feedback_id}"}


def _trusted_source_event(event):
    expected_source = (SOURCE_KIND if event.get("event_type") == FEEDBACK_EVENT
                       else DECISION_SOURCE_KIND if event.get("event_type") == DECISION_EVENT else "")
    provenance = event.get("provenance") or {}
    source_proven = (provenance.get("owner_pasted") is True if expected_source == SOURCE_KIND
                     else provenance.get("human_decision_canonical") is True)
    return (bool(expected_source)
        and event.get("source_system") == VERSION and event.get("authority_tier") == "observe"
        and event.get("privacy_class") == "owner_private"
        and event.get("actor_type") == "control_tower_reconciler"
        and provenance.get("source_ref") == expected_source and source_proven)


def _source_event(feedback_id, event_type, *, database_url=None, connect_factory=None):
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", aggregate_id=feedback_id, limit=100,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return None
    matches = [event for event in loaded.get("events", []) if event.get("event_type") == event_type]
    return matches[0] if len(matches) == 1 else None


def _proposal_for_feedback(feedback_id, *, database_url=None, connect_factory=None):
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", aggregate_id=feedback_id, limit=100,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return None
    matches = [(event.get("payload") or {}).get("proposal") for event in loaded.get("events", [])
        if event.get("event_type") == "shadow_control_tower_proposal_recorded"]
    return matches[0] if len(matches) == 1 and isinstance(matches[0], Mapping) else None


def _identity(tx):
    return {key: str(tx.get(key) or "").strip() for key in (
        "feedback_transaction_id", "terminal_identity", "existing_mission_id",
        "worktree_identity", "feedback_occurred_at", "feedback_reconciliation_id",
        "control_tower_reconciliation_id")}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode()).hexdigest()


def _failure(status, code):
    return {"success": False, "status": status, **_zero_authority()}, code


def _zero_authority():
    return {"dispatches": 0, "prompts_sent": 0, "terminals_started": 0,
        "processes_spawned": 0, "missions_created": 0, "merges": 0,
        "deployments": 0, "provider_messages": 0, "farm_writes": 0,
        "release_authority_granted": False}
