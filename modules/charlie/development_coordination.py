"""Pure governance contract for minimal CORE development dispatch.

This module plans and reduces durable events. It performs no dispatch, queue
mutation, external action, or authority grant.
"""

from __future__ import annotations

import hashlib
import json

from modules.charlie.adaptive_orchestration import build_orchestration_packet


VERSION = "charlie_development_coordination_v1"
STATES = (
    "proposed", "owner_authorized", "released", "acknowledged", "started",
    "waiting_for_evidence", "contained", "completed_with_artifact",
    "genuinely_blocked",
)
OWNER_AUTHORITIES = {"charl", "charlie"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(prefix, value):
    return prefix + hashlib.sha256(_canonical(value).encode()).hexdigest()[:24].upper()


def plan_development_dispatch(mission):
    """Create a deterministic proposal; planning never releases work."""
    mission = dict(mission or {})
    packet = build_orchestration_packet(mission)
    agents = [row["agent"] for row in packet["selected_agents"]]
    if len(agents) != len(set(agents)):
        raise ValueError("coordination_duplicate_agent")
    plan_material = {
        "version": VERSION,
        "mission": mission,
        "score": packet["coordination_score"],
        "tier": packet["tier"],
        "agents": agents,
        "orchestration_generation": packet["generation_identity"],
    }
    return {
        **plan_material,
        "plan_id": _identity("CORE-PLAN-", plan_material),
        "state": "proposed",
        "orchestration": packet,
        "release_is_pickup": False,
        "acknowledgement_timeout_seconds": min(900, max(60, int(mission.get("acknowledgement_timeout_seconds") or 300))),
        "retry_policy": {"ambiguous_external_effect": "never_retry", "missing_acknowledgement": "one_deduplicated_exception"},
    }


def reduce_coordination(plan, events):
    """Reduce append-only coordination events and fail closed on invalid order."""
    plan = dict(plan or {})
    state = "proposed"
    receipt = None
    completion = None
    exceptions = {}
    seen_workers = []
    for event in events or []:
        event = dict(event or {})
        kind = str(event.get("type") or "")
        event_id = str(event.get("event_id") or _identity("CORE-EVENT-", event))
        if kind in {"authorize", "release"} and str(event.get("authority") or "").lower() not in OWNER_AUTHORITIES:
            raise ValueError("coordination_owner_authority_required")
        if kind == "authorize" and state == "proposed":
            state = "owner_authorized"
        elif kind == "release" and state == "owner_authorized":
            if plan.get("tier") == "T4" and not event.get("exact_protected_authority"):
                raise ValueError("coordination_protected_authority_required")
            state = "released"
        elif kind == "acknowledge" and state == "released":
            required = ("worker_id", "worker_role", "dispatch_id", "acknowledged_at")
            if any(not event.get(field) for field in required):
                raise ValueError("coordination_acknowledgement_incomplete")
            if str(event["worker_role"]).strip().lower() not in set(plan.get("agents") or []):
                raise ValueError("coordination_worker_not_selected")
            worker = str(event["worker_id"])
            if worker in seen_workers:
                raise ValueError("coordination_circular_worker_handoff")
            seen_workers.append(worker)
            receipt = {field: event[field] for field in required}
            state = "acknowledged"
        elif kind == "start" and state == "acknowledged":
            if event.get("dispatch_id") != receipt["dispatch_id"] or not event.get("started_at"):
                raise ValueError("coordination_start_receipt_mismatch")
            state = "started"
        elif kind == "wait_for_evidence" and state in {"started", "waiting_for_evidence"}:
            state = "waiting_for_evidence"
        elif kind == "contain_missing_ack" and state in {"released", "contained"}:
            key = _identity("CORE-EXCEPTION-", {"plan_id": plan.get("plan_id"), "reason": "acknowledgement_timeout"})
            exceptions.setdefault(key, {"exception_id": key, "reason": "acknowledgement_timeout", "retry": False})
            state = "contained"
        elif kind == "contain_ambiguous_external_effect" and state in {"released", "acknowledged", "started", "waiting_for_evidence", "contained"}:
            key = _identity("CORE-EXCEPTION-", {"plan_id": plan.get("plan_id"), "effect": event.get("effect_identity")})
            exceptions.setdefault(key, {"exception_id": key, "reason": "ambiguous_external_effect", "retry": False})
            state = "contained"
        elif kind == "complete" and state in {"started", "waiting_for_evidence"}:
            completion = validate_completion_artifact(event.get("artifact"))
            declared_files = [str(path).strip() for path in ((plan.get("mission") or {}).get("expected_files") or []) if str(path).strip()]
            evidence_text = "\n".join(completion["artifact_evidence"])
            if declared_files and any(path not in evidence_text for path in declared_files):
                raise ValueError("coordination_declared_artifact_required")
            state = "completed_with_artifact"
        elif kind == "block" and state in {"started", "waiting_for_evidence", "contained"}:
            if int(event.get("same_blocker_occurrences") or 0) < 3 or not event.get("owner_or_external_change_required"):
                raise ValueError("coordination_not_genuinely_blocked")
            state = "genuinely_blocked"
        elif kind == "propose" and state == "proposed":
            continue
        else:
            raise ValueError(f"coordination_invalid_transition:{state}:{kind}")
    return {"state": state, "pickup_proven": state in {"acknowledged", "started", "waiting_for_evidence", "completed_with_artifact", "genuinely_blocked"},
            "receipt": receipt, "completion": completion, "exceptions": list(exceptions.values())}


def validate_dispatch_scope(plan, *, plan_id, mission_id, worker_role):
    """Fail closed unless one pickup request exactly matches the selected plan."""
    plan = dict(plan or {})
    if str(plan_id or "") != str(plan.get("plan_id") or ""):
        raise ValueError("coordination_plan_scope_mismatch")
    expected_mission_id = str((plan.get("mission") or {}).get("mission_id") or "")
    if not expected_mission_id or str(mission_id or "") != expected_mission_id:
        raise ValueError("coordination_mission_scope_mismatch")
    if str(worker_role or "").strip().lower() not in set(plan.get("agents") or []):
        raise ValueError("coordination_worker_not_selected")
    return {"plan_id": plan["plan_id"], "mission_id": expected_mission_id,
            "worker_role": str(worker_role).strip().lower(), "single_mission": True}


def validate_completion_artifact(artifact):
    artifact = dict(artifact or {})
    outcome = str(artifact.get("business_outcome") or "").strip()
    if not outcome:
        raise ValueError("coordination_business_outcome_required")
    if outcome.upper() == "NO BUSINESS OUTCOME" and not str(artifact.get("outcome_reason") or "").strip():
        raise ValueError("coordination_no_business_outcome_reason_required")
    evidence = artifact.get("artifact_evidence")
    if not isinstance(evidence, list) or not evidence or any(not str(item).strip() for item in evidence):
        raise ValueError("coordination_artifact_evidence_required")
    if "next_dependency" not in artifact:
        raise ValueError("coordination_next_dependency_required")
    return {"business_outcome": outcome, "outcome_reason": str(artifact.get("outcome_reason") or ""),
            "artifact_evidence": list(evidence), "next_dependency": artifact.get("next_dependency")}


def close_dependency(completion, dependency_id):
    completion = validate_completion_artifact(completion)
    if completion["next_dependency"] not in (None, "", dependency_id):
        raise ValueError("coordination_dependency_mismatch")
    return {"dependency_id": dependency_id, "closed": True,
            "evidence": completion["artifact_evidence"]}


def validate_successor_bindings(bindings):
    predecessors = set()
    successors = set()
    for item in bindings or []:
        predecessor = str((item or {}).get("predecessor_id") or "")
        successor = str((item or {}).get("successor_id") or "")
        if not predecessor or not successor or predecessor in predecessors or successor in successors:
            raise ValueError("coordination_duplicate_or_overlapping_successor")
        predecessors.add(predecessor)
        successors.add(successor)
    return True
