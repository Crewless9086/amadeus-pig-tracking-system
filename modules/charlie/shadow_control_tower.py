"""Disabled-by-default, observation-only Control Tower decision shadow.

This module creates and records advisory proposals and later human-decision
comparisons. It has no dispatch, terminal, process, mission-creation, provider,
release, or farm mutation capability.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Mapping

from modules.charlie.operational_event_store import append_operational_event, load_operational_events

VERSION = "shadow_control_tower_phase_a_v1"
ENABLE_ENV = "CHARLIE_SHADOW_CONTROL_TOWER_ENABLED"
TERMINAL_STATES = frozenset({"actively_working", "idle_open", "released", "blocked",
    "waiting_for_real_event", "waiting_for_owner", "not_launched"})
WORKTREE_CLASSES = frozenset({"clean_releasable", "clean_retained", "dirty_preserved",
    "unique_preserved", "conflicting_preserved", "not_applicable", "unknown"})
EVIDENCE_CLASSES = ("documented", "runtime_loaded", "provider_verified", "physical")
NEXT_ACTIONS = frozenset({"SEND_NOTHING", "ADDENDUM", "CONTINUE", "NEW_MISSION",
    "WAIT_FOR_INPUT", "CLOSE"})


def shadow_enabled(environ=None):
    env = os.environ if environ is None else environ
    return str(env.get(ENABLE_ENV, "") or "").strip().lower() in {"1", "true", "yes"}


def propose_shadow_decision(transaction, *, environ=None):
    """Return one deterministic non-authoritative proposal; never dispatch it."""
    if not shadow_enabled(environ):
        return _disabled()
    tx = transaction if isinstance(transaction, Mapping) else {}
    error = _validate_transaction(tx)
    if error:
        return {"success": False, "status": error, **_zero_authority()}
    normalized = _normalized_transaction(tx)
    reasons = [str(value).strip() for value in tx.get("reasons", []) if str(value).strip()][:12]
    proposal = {
        "schema_version": VERSION,
        "authority": "non_authoritative_shadow_proposal",
        "human_control_tower_is_sole_dispatcher": True,
        "feedback_transaction_id": normalized["feedback_transaction_id"],
        "terminal_identity": normalized["terminal_identity"],
        "terminal_state": normalized["terminal_state"],
        "deployed_agent_identity": normalized["deployed_agent_identity"],
        "existing_mission_id": normalized["existing_mission_id"],
        "business_status": normalized["business_status"],
        "evidence": normalized["evidence"],
        "worktree_classification": normalized["worktree_classification"],
        "collision_assessment": normalized["collision_assessment"],
        "proposed_next_terminal": normalized["proposed_next_terminal"],
        "proposed_next_action": normalized["proposed_next_action"],
        "proposed_continuation_prompt": normalized["proposed_continuation_prompt"],
        "expected_owner_visible_result": normalized["expected_owner_visible_result"],
        "confidence": normalized["confidence"],
        "reasons": reasons,
        **_zero_authority(),
    }
    proposal["proposal_id"] = "SCTP-" + _digest(proposal)[:24].upper()
    return {"success": True, "status": "shadow_proposal_ready", "proposal": proposal,
        **_zero_authority()}


def record_shadow_proposal(transaction, *, environ=None, database_url=None, connect_factory=None):
    ready = propose_shadow_decision(transaction, environ=environ)
    if not ready.get("success"):
        return ready, 403 if ready.get("status") == "shadow_control_tower_disabled" else 400
    proposal = ready["proposal"]
    stable_record_id = "SCTF-" + _digest({"feedback_transaction_id": proposal["feedback_transaction_id"]})[:24].upper()
    result, status = append_operational_event(_event_packet(
        event_type="shadow_control_tower_proposal_recorded", proposal=proposal,
        payload={"record_type": "proposal", "proposal": proposal},
        source_record_id=stable_record_id),
        database_url=database_url, connect_factory=connect_factory)
    if result.get("success") and result.get("created") is False:
        durable, durable_status = _persisted_proposal_for_feedback(
            proposal["feedback_transaction_id"], database_url=database_url,
            connect_factory=connect_factory)
        if durable_status >= 400:
            return durable, durable_status
        if _digest(durable["proposal"]) != _digest(proposal):
            return {"success": False, "status": "shadow_feedback_transaction_replay_conflict",
                **_zero_authority()}, 409
        proposal = durable["proposal"]
    return {**result, "proposal_id": proposal["proposal_id"], **_zero_authority()}, status


def compare_human_decision(proposal, actual_decision, *, environ=None,
                           database_url=None, connect_factory=None):
    """Record deterministic comparison; never apply the actual or proposed decision."""
    if not shadow_enabled(environ):
        return _disabled(), 403
    proposal_ref = proposal if isinstance(proposal, Mapping) else {}
    actual = actual_decision if isinstance(actual_decision, Mapping) else {}
    proposal_id = str(proposal_ref.get("proposal_id") or "").strip()
    feedback_id = str(proposal_ref.get("feedback_transaction_id") or "").strip()
    if not proposal_id or not feedback_id:
        return {"success": False, "status": "shadow_proposal_required", **_zero_authority()}, 400
    persisted, persisted_status = _persisted_proposal(proposal_id, feedback_id,
        database_url=database_url, connect_factory=connect_factory)
    if persisted_status >= 400:
        return persisted, persisted_status
    proposal = persisted["proposal"]
    if _digest(proposal_ref) != _digest(proposal):
        return {"success": False, "status": "shadow_proposal_content_mismatch",
            **_zero_authority()}, 409
    required = ("human_decision_id", "actual_next_terminal", "actual_next_action",
        "actual_continuation_prompt", "actual_owner_visible_result")
    if any(not str(actual.get(key) or "").strip() for key in required):
        return {"success": False, "status": "human_control_tower_decision_fields_required",
            **_zero_authority()}, 400
    if actual["actual_next_action"] not in NEXT_ACTIONS:
        return {"success": False, "status": "human_control_tower_action_invalid", **_zero_authority()}, 400
    fields = {
        "next_terminal": (proposal["proposed_next_terminal"], str(actual["actual_next_terminal"]).strip()),
        "next_action": (proposal["proposed_next_action"], actual["actual_next_action"]),
        "continuation_prompt": (proposal["proposed_continuation_prompt"], str(actual["actual_continuation_prompt"]).strip()),
        "owner_visible_result": (proposal["expected_owner_visible_result"], str(actual["actual_owner_visible_result"]).strip()),
    }
    matches = {name: expected == observed for name, (expected, observed) in fields.items()}
    comparison = {
        "schema_version": VERSION,
        "record_type": "human_control_tower_comparison",
        "proposal_id": proposal["proposal_id"],
        "feedback_transaction_id": proposal["feedback_transaction_id"],
        "human_decision_id": str(actual["human_decision_id"]).strip(),
        "field_matches": matches,
        "matched_field_count": sum(matches.values()),
        "compared_field_count": len(matches),
        "exact_match": all(matches.values()),
        "actual_decision": {key: str(actual[key]).strip() for key in required},
        "human_control_tower_remained_authoritative": True,
        **_zero_authority(),
    }
    comparison["comparison_id"] = "SCTC-" + _digest({"proposal_id":proposal["proposal_id"],
        "feedback_transaction_id":proposal["feedback_transaction_id"],
        "human_decision_id":comparison["human_decision_id"]})[:24].upper()
    prior = [event.get("payload") for event in persisted.get("events", [])
        if event.get("event_type") == "shadow_control_tower_human_comparison_recorded"
        and (event.get("payload") or {}).get("comparison_id") == comparison["comparison_id"]]
    if prior and any(_digest(value) != _digest(comparison) for value in prior):
        return {"success": False, "status": "human_decision_replay_conflict",
            **_zero_authority()}, 409
    result, status = append_operational_event(_event_packet(
        event_type="shadow_control_tower_human_comparison_recorded", proposal=proposal,
        payload=comparison, source_record_id=comparison["comparison_id"]),
        database_url=database_url, connect_factory=connect_factory)
    if result.get("success") and result.get("created") is False:
        durable, durable_status = _persisted_comparison(comparison["comparison_id"], feedback_id,
            database_url=database_url, connect_factory=connect_factory)
        if durable_status >= 400:
            return durable, durable_status
        if _digest(durable["comparison"]) != _digest(comparison):
            return {"success": False, "status": "human_decision_replay_conflict",
                **_zero_authority()}, 409
        comparison = durable["comparison"]
    return {**result, "comparison": comparison, **_zero_authority()}, status


def comparison_readiness(*, database_url=None, connect_factory=None):
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", limit=1000,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return loaded, status
    proposals = {(event.get("aggregate_id"), (event.get("payload") or {}).get("proposal", {}).get("proposal_id"))
        for event in loaded["events"] if event.get("event_type") == "shadow_control_tower_proposal_recorded"}
    comparisons = {(event.get("aggregate_id"), (event.get("payload") or {}).get("proposal_id"))
        for event in loaded["events"] if event.get("event_type") == "shadow_control_tower_human_comparison_recorded"}
    valid_pairs = {pair for pair in comparisons if pair in proposals and all(pair)}
    valid_feedback_transactions = {feedback_id for feedback_id, _proposal_id in valid_pairs}
    return {"success": True, "status": "shadow_comparison_readiness",
        "comparison_count": len(valid_feedback_transactions), "target_count": 10,
        "target_reached": len(valid_feedback_transactions) >= 10,
        "learning_success_claimed": False, **_zero_authority()}, 200


def _persisted_proposal(proposal_id, feedback_id, *, database_url=None, connect_factory=None):
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", aggregate_id=feedback_id, limit=100,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return loaded, status
    matches = []
    for event in loaded.get("events", []):
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        candidate = payload.get("proposal") if isinstance(payload.get("proposal"), Mapping) else {}
        if (event.get("event_type") == "shadow_control_tower_proposal_recorded"
                and candidate.get("proposal_id") == proposal_id
                and candidate.get("feedback_transaction_id") == feedback_id):
            matches.append(dict(candidate))
    if len(matches) != 1:
        return {"success": False, "status": "persisted_shadow_proposal_not_found",
            **_zero_authority()}, 409
    return {"success": True, "status": "persisted_shadow_proposal_ready",
        "proposal": matches[0], "events": loaded.get("events", [])}, 200


def _persisted_proposal_for_feedback(feedback_id, *, database_url=None, connect_factory=None):
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", aggregate_id=feedback_id, limit=100,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return loaded, status
    matches = [dict((event.get("payload") or {}).get("proposal") or {})
        for event in loaded.get("events", [])
        if event.get("event_type") == "shadow_control_tower_proposal_recorded"
        and isinstance((event.get("payload") or {}).get("proposal"), Mapping)]
    if len(matches) != 1:
        return {"success": False, "status": "persisted_shadow_feedback_proposal_not_unique",
            **_zero_authority()}, 409
    return {"success": True, "status": "persisted_shadow_proposal_ready",
        "proposal": matches[0]}, 200


def _persisted_comparison(comparison_id, feedback_id, *, database_url=None, connect_factory=None):
    loaded, status = load_operational_events(domain="missions",
        aggregate_type="control_tower_feedback_transaction", aggregate_id=feedback_id, limit=100,
        database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return loaded, status
    matches = [dict(event["payload"]) for event in loaded.get("events", [])
        if event.get("event_type") == "shadow_control_tower_human_comparison_recorded"
        and isinstance(event.get("payload"), Mapping)
        and event["payload"].get("comparison_id") == comparison_id]
    if len(matches) != 1:
        return {"success": False, "status": "persisted_shadow_comparison_not_found",
            **_zero_authority()}, 409
    return {"success": True, "status": "persisted_shadow_comparison_ready",
        "comparison": matches[0]}, 200


def _validate_transaction(tx):
    required = ("feedback_transaction_id", "terminal_identity", "terminal_state",
        "deployed_agent_identity", "existing_mission_id", "business_status", "evidence",
        "worktree_classification", "collision_assessment", "proposed_next_terminal",
        "proposed_next_action", "proposed_continuation_prompt", "expected_owner_visible_result",
        "confidence", "reasons")
    if any(tx.get(key) in (None, "") for key in required):
        return "shadow_feedback_transaction_fields_required"
    if tx["terminal_state"] not in TERMINAL_STATES:
        return "shadow_terminal_state_invalid"
    if tx["worktree_classification"] not in WORKTREE_CLASSES:
        return "shadow_worktree_classification_invalid"
    if tx["proposed_next_action"] not in NEXT_ACTIONS:
        return "shadow_next_action_invalid"
    if not isinstance(tx["evidence"], Mapping) or set(tx["evidence"]) != set(EVIDENCE_CLASSES):
        return "shadow_evidence_classification_invalid"
    if not all(isinstance(tx["evidence"][key], list) for key in EVIDENCE_CLASSES):
        return "shadow_evidence_classification_invalid"
    try:
        confidence = float(tx["confidence"])
    except (TypeError, ValueError):
        return "shadow_confidence_invalid"
    if not 0 <= confidence <= 1 or not isinstance(tx["reasons"], list):
        return "shadow_confidence_invalid"
    return ""


def _normalized_transaction(tx):
    keys = ("feedback_transaction_id", "terminal_identity", "terminal_state",
        "deployed_agent_identity", "existing_mission_id", "business_status",
        "worktree_classification", "collision_assessment", "proposed_next_terminal",
        "proposed_next_action", "proposed_continuation_prompt", "expected_owner_visible_result")
    result = {key: str(tx[key]).strip() for key in keys}
    result["confidence"] = round(float(tx["confidence"]), 6)
    result["evidence"] = {key: [str(value).strip() for value in tx["evidence"][key]
        if str(value).strip()][:20] for key in EVIDENCE_CLASSES}
    return result


def _event_packet(*, event_type, proposal, payload, source_record_id=""):
    occurred = str(proposal.get("occurred_at") or datetime.now(timezone.utc).isoformat())
    record_id = source_record_id or proposal["proposal_id"]
    return {"event_type": event_type, "domain": "missions",
        "aggregate_type": "control_tower_feedback_transaction",
        "aggregate_id": proposal["feedback_transaction_id"], "source_system": VERSION,
        "source_record_id": record_id, "authority_tier": "observe", "privacy_class": "owner_private",
        "actor_type": "shadow_observer", "actor_id": "CORE_SHADOW_CONTROL_TOWER",
        "occurred_at": occurred, "payload": payload,
        "provenance": {"source_ref": "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md",
            "human_control_tower_authoritative": True},
        "idempotency_key": f"{event_type}:{record_id}"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()


def _disabled():
    return {"success": False, "status": "shadow_control_tower_disabled",
        "kill_switch": ENABLE_ENV, **_zero_authority()}


def _zero_authority():
    return {"dispatches": 0, "prompts_sent": 0, "terminals_started": 0,
        "processes_spawned": 0, "missions_created": 0, "merges": 0, "deployments": 0,
        "provider_messages": 0, "farm_writes": 0, "release_authority_granted": False}
