"""Runtime adapter that lets CHARLIE supervise CORE without bypassing authority."""

from __future__ import annotations

import os
import hashlib

from modules.charlie.block_adjudication import adjudicate_block
from modules.charlie.delegated_governance import delegated_review_assessment, queue_candidate_assessment
from modules.charlie.executive_control import build_executive_cycle
from modules.charlie.executive_store import (
    complete_control_command,
    load_executive_context,
    queue_outbox,
    record_control_command,
    upsert_recovery_case,
)
from modules.charlie.mission_store import get_mission, list_missions, record_mission, transition_mission_review_state, update_mission_status
from modules.charlie.pr_reconciliation import mission_pr_reference, query_pr_state
from modules.charlie.review_readiness import cleared_review_packet, mission_dependency_ids
from modules.charlie.core_workflow import build_workflow_from_template, workflow_template
from modules.charlie.mission_governance import validate_acceptance_scope


def executive_mode():
    value = str(os.getenv("CHARLIE_EXECUTIVE_MODE", "observe") or "observe").strip().lower()
    return value if value in {"off", "observe", "active"} else "observe"


def run_executive_cycle(*, runner=None, database_url=None, connect_factory=None):
    mode = executive_mode()
    if mode == "off":
        return {"success": True, "status": "executive_disabled", "mode": mode}, 200
    loaded, loaded_status = _load_executive_missions(database_url=database_url, connect_factory=connect_factory)
    context, context_status = load_executive_context(database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400 or context_status >= 400:
        return {"success": False, "status": "executive_context_unavailable", "mode": mode, "mission_status": loaded_status, "policy_status": context_status}, 503
    cycle = build_executive_cycle(loaded.get("missions", []), context.get("policies", []), runner=runner, goals=context.get("goals", []), trust=context.get("trust", []))
    results = []
    for command in cycle["commands"]:
        recorded, record_status = record_control_command(command, database_url=database_url, connect_factory=connect_factory)
        if record_status >= 400:
            results.append({"command": command, "status": "record_failed"})
            continue
        if not recorded.get("created"):
            outcome = _command_outcome(command, database_url, connect_factory)
            if outcome.get("satisfied"):
                results.append({"command": command, "status": "duplicate_outcome_confirmed", "outcome": outcome})
                continue
            if mode != "active" or not recorded.get("existing"):
                results.append({"command": command, "status": "duplicate_observed", "outcome": outcome})
                continue
        if mode != "active":
            complete_control_command(recorded["command_id"], success=True, result={"status": "observed_no_execution"}, database_url=database_url, connect_factory=connect_factory)
            results.append({"command": command, "status": "observed"})
            continue
        results.append(_execute_command(command, recorded["command_id"], database_url, connect_factory))
    if mode == "active":
        for escalation in cycle["escalations"]:
            generation = str(escalation.get("notification_fingerprint") or "initial")
            queue_outbox("NEEDS_OWNER_APPROVAL", escalation, idempotency_key=f"owner:{escalation.get('mission_id')}:{escalation.get('block_class')}:{generation}", database_url=database_url, connect_factory=connect_factory)
    return {"success": True, "status": "executive_cycle_complete", "mode": mode, "cycle": cycle, "results": results}, 200


def _command_outcome(command, database_url, connect_factory):
    action = str(command.get("action") or "")
    mission_id = str(command.get("mission_id") or "")
    if action == "ensure_queue_progress" or not mission_id:
        return {"satisfied": True, "reason": "observation_command"}
    loaded, status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if status >= 400:
        return {"satisfied": False, "reason": "mission_reload_failed"}
    mission = loaded.get("mission") or {}
    current = str(mission.get("status") or "")
    targets = {
        "schedule_recovery": {"approved", "in_progress", "pr_ready", "release_approved", "merged", "deployed", "done"},
        "reconcile_pr": {"pr_ready", "release_approved", "merged", "deployed", "done", "blocked"},
        "decompose_acceptance": {"paused"},
        "verify_and_delegate_review": {"release_approved", "merged", "deployed", "done"},
        "approve_next_work": {"approved", "in_progress", "pr_ready", "release_approved", "merged", "deployed", "done"},
        "reconcile_family": {"approved", "in_progress", "pr_ready", "release_approved", "merged", "deployed", "done"},
    }.get(action, set())
    return {"satisfied": current in targets, "reason": "desired_state_present" if current in targets else "desired_state_missing", "mission_status": current}


def _execute_command(command, command_id, database_url, connect_factory):
    action = command.get("action")
    if action == "schedule_recovery":
        return _execute_recovery(command, command_id, database_url, connect_factory)
    if action == "reconcile_pr":
        return _execute_pr_reconciliation(command, command_id, database_url, connect_factory)
    if action == "decompose_acceptance":
        return _execute_decomposition(command, command_id, database_url, connect_factory)
    if action == "verify_and_delegate_review":
        return _execute_delegated_review(command, command_id, database_url, connect_factory)
    if action == "approve_next_work":
        return _execute_queue_selection(command, command_id, database_url, connect_factory)
    if action == "reconcile_family":
        return _execute_family_reconciliation(command, command_id, database_url, connect_factory)
    complete_control_command(command_id, success=True, result={"status": "runner_will_pick_approved_queue"}, database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "queue_progress_observed"}


def _execute_recovery(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    case, case_status = upsert_recovery_case(mission_id, command, database_url=database_url, connect_factory=connect_factory)
    if case_status >= 400:
        if case.get("status") == "recovery_limit_halted":
            loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
            mission = loaded.get("mission") if loaded_status < 400 and isinstance(loaded.get("mission"), dict) else {}
            metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
            packet = dict(metadata.get("review_packet") or {})
            packet.update({
                "review_status": "system_incident_halted",
                "blocked_agent": str(command.get("target_stage") or packet.get("blocked_agent") or "planner"),
                "blocked_reason": "Automatic recovery stopped at the durable mission recovery limit.",
                "recovery_limit": case,
                "recommended_next_action": "Repair the shared failure condition, then explicitly resume this mission.",
            })
            transition_mission_review_state(
                mission_id, "blocked", packet, expected_status="blocked",
                owner_decision="CORE halted repeated automatic recovery.",
                notes="Durable recovery circuit breaker reached its attempt limit.",
                database_url=database_url, connect_factory=connect_factory,
            )
        complete_control_command(command_id, success=False, result=case, error="recovery_budget_exhausted_or_unavailable", database_url=database_url, connect_factory=connect_factory)
        return {"command": command, "status": "system_incident_halted" if case.get("status") == "recovery_limit_halted" else "recovery_state_unavailable", "recovery": case}
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        complete_control_command(command_id, success=False, result=loaded, error="mission_reload_failed", database_url=database_url, connect_factory=connect_factory)
        return {"command": command, "status": "mission_reload_failed", "result": loaded, "recovery": case}
    mission = loaded.get("mission") if isinstance(loaded.get("mission"), dict) else {}
    if int(case.get("attempt_count") or 0) >= int(case.get("attempt_limit") or 3):
        return _execute_alternate_recovery(command, command_id, mission, case, database_url, connect_factory)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    current_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    packet = cleared_review_packet(current_packet, reason="CHARLIE scheduled deterministic internal recovery", return_to_stage=command.get("target_stage") or "planner")
    packet["executive_recovery"] = {"recovery_id": case.get("recovery_id"), "fingerprint": command.get("fingerprint"), "authority_tier": command.get("authority_tier"), "policy_id": command.get("policy_id")}
    result, status = transition_mission_review_state(
        mission_id, "approved", packet,
        notes="CHARLIE executive control plane scheduled a recoverable internal block.",
        expected_status="blocked", database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(command_id, success=success, result=result, error="" if success else result.get("status", "transition_failed"), database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "recovery_queued" if success else "transition_failed", "result": result, "recovery": case}


def _execute_alternate_recovery(command, command_id, mission, case, database_url, connect_factory):
    """Change the repair strategy after repeated identical attempts; never spin or silently stop."""
    decision = adjudicate_block(mission)
    block_class = str(command.get("block_class") or decision.get("block_class") or "").strip()
    if block_class in {"system_repair_required", "environment_retry_required", "branch_repair_required"}:
        result = {
            "success": False,
            "status": "system_incident_halted",
            "mission_id": mission.get("mission_id") or command.get("mission_id"),
            "block_class": block_class,
            "fingerprint": command.get("fingerprint"),
            "attempt_count": case.get("attempt_count"),
            "attempt_limit": case.get("attempt_limit"),
            "next_action": "Repair or change the shared system condition before explicitly resuming this mission.",
        }
        complete_control_command(
            command_id,
            success=True,
            result=result,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        return {"command": command, "status": "system_incident_halted", "result": result, "recovery": case}
    pending = decision.get("pending_rows") if isinstance(decision.get("pending_rows"), list) else []
    if decision.get("action") == "decompose_acceptance" or len(pending) >= 3:
        alternate = {**command, **decision, "action": "decompose_acceptance"}
        return _execute_decomposition(alternate, command_id, database_url, connect_factory)

    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    current_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    original_stage = str(command.get("target_stage") or current_packet.get("return_to_stage") or "builder")
    target_stage = "planner" if original_stage in {"builder", "tester", "qa_red_team", "reviewer"} else "architect"
    packet = cleared_review_packet(
        current_packet,
        reason="CHARLIE changed recovery strategy after the identical repair budget was exhausted.",
        return_to_stage=target_stage,
    )
    packet["executive_recovery"] = {
        "recovery_id": case.get("recovery_id"),
        "fingerprint": command.get("fingerprint"),
        "strategy": "alternate_planning",
        "prior_target_stage": original_stage,
        "authority_tier": command.get("authority_tier"),
        "policy_id": command.get("policy_id"),
    }
    result, status = transition_mission_review_state(
        mission.get("mission_id") or command.get("mission_id"), "approved", packet,
        notes="CHARLIE exhausted an identical repair strategy and routed the mission through fresh planning.",
        expected_status="blocked", database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(
        command_id, success=success, result=result,
        error="" if success else result.get("status", "alternate_recovery_transition_failed"),
        database_url=database_url, connect_factory=connect_factory,
    )
    return {
        "command": command,
        "status": "alternate_recovery_queued" if success else "transition_failed",
        "result": result,
        "recovery": case,
        "target_stage": target_stage,
    }


def _execute_pr_reconciliation(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        return _finish_failure(command, command_id, loaded, "mission_reload_failed", database_url, connect_factory)
    mission = loaded.get("mission") or {}
    pr_state = query_pr_state(mission_pr_reference(mission))
    dependency_states, dependency_error = _load_dependency_states(
        mission, database_url=database_url, connect_factory=connect_factory,
    )
    if dependency_error:
        return _finish_failure(
            command, command_id, dependency_error, "dependency_state_reload_failed",
            database_url, connect_factory,
        )
    decision = adjudicate_block(
        mission, pr_state=pr_state, dependency_states=dependency_states,
    )
    if decision.get("action") == "recover_stage":
        recovery = {**command, **decision, "action": "schedule_recovery"}
        return _execute_recovery(recovery, command_id, database_url, connect_factory)
    if decision.get("action") not in {"reconcile_pr_ready", "reconcile_merged"}:
        return _finish_failure(command, command_id, decision, "pr_not_reconcilable", database_url, connect_factory)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    packet = dict(metadata.get("review_packet") or {})
    pr_decision = decision.get("pr_decision") or {}
    target_status = "merged" if decision["action"] == "reconcile_merged" else "pr_ready"
    packet.update({
        "review_status": "ready_for_owner_review" if target_status == "pr_ready" else "merged",
        "blocked_agent": "", "blocked_reason": "", "unresolved_blockers": [],
        "recommended_owner_decision": "approve_final_release" if target_status == "pr_ready" else "",
        "recommended_next_action": "Review the current green PR." if target_status == "pr_ready" else "PR is merged.",
        "tested_revision": pr_decision.get("head_sha") or pr_state.get("headRefOid"),
        "github_reconciliation": {"status": "authoritative", "head_sha": pr_state.get("headRefOid"), "decision": pr_decision.get("reason")},
        "block_adjudication": decision,
    })
    result, status = transition_mission_review_state(
        mission_id, target_status, packet, expected_status="blocked",
        notes="CHARLIE reconciled stale blocked state against authoritative GitHub evidence.",
        database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(command_id, success=success, result=result, error="" if success else result.get("status", "transition_failed"), database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "pr_reconciled" if success else "transition_failed", "result": result}


def _execute_decomposition(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        return _finish_failure(command, command_id, loaded, "mission_reload_failed", database_url, connect_factory)
    mission = loaded.get("mission") or {}
    decision = adjudicate_block(mission)
    if decision.get("action") != "decompose_acceptance":
        return _finish_failure(command, command_id, decision, "decomposition_no_longer_applicable", database_url, connect_factory)
    rows = decision.get("pending_rows") or []
    groups = [rows[index:index + 2] for index in range(0, min(len(rows), 8), 2)]
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    allowed_files = metadata.get("allowed_files") or vault.get("allowed_files") or vault.get("scope_files") or []
    child_ids = []
    child_results = []
    for index, group in enumerate(groups, start=1):
        scope_validation = validate_acceptance_scope(group, allowed_files)
        if not scope_validation["satisfiable"]:
            return _finish_failure(
                command, command_id,
                {"scope_validation": scope_validation, "slice": index},
                "child_acceptance_scope_unsatisfiable",
                database_url, connect_factory,
            )
        child_id = _child_id(mission_id, group)
        child_ids.append(child_id)
        criteria = [str(row.get("requirement") or row.get("criterion") or row.get("summary") or row.get("id") or "").strip() for row in group]
        recovery_template = workflow_template("software_build")
        recovery_template["agent_order"] = ["source_mapper", "builder", "tester", "evidence_reviewer", "reviewer"]
        child = {
            "mission_id": child_id, "status": "approved",
            "title": f"{mission.get('title') or mission_id} - recovery slice {index}",
            "raw_text": "Complete only this bounded recovery slice:\n- " + "\n- ".join(criteria),
            "urgency": mission.get("urgency") or "P1", "mission_type": mission.get("mission_type") or "system improvement",
            "approval_level": mission.get("approval_level") or "LEVEL 3",
            "metadata": {
                "mission_family": {"parent_mission_id": mission_id, "relationship": "acceptance_recovery"},
                "acceptance_criteria": criteria,
                "mission_governance": {"acceptance_matrix": group, "frozen": True},
                "agent_workflow": build_workflow_from_template(recovery_template),
                "charlie_core": {
                    "workflow_template": {**recovery_template, "pipeline_profile": "bounded_recovery_slice", "right_sized": True},
                    "project_truth": {"workflow_template": "software_build", "pipeline_profile": "bounded_recovery_slice"},
                },
                "allowed_files": allowed_files,
                "charlie_adjudication": {
                    "parent_fingerprint": decision.get("fingerprint"), "slice": index,
                    "scope_validation": scope_validation,
                },
            },
        }
        stored, stored_status = record_mission(child, {"source": "charlie_executive_adjudication", "message_id": child_id}, database_url=database_url, connect_factory=connect_factory)
        child_results.append({"mission_id": child_id, "status_code": stored_status, "result": stored})
        if stored_status >= 400:
            return _finish_failure(command, command_id, {"children": child_results}, "child_creation_failed", database_url, connect_factory)
    packet = dict(metadata.get("review_packet") or {})
    packet.update({
        "review_status": "decomposed_recovery_waiting", "blocked_agent": "", "blocked_reason": "",
        "unresolved_blockers": [], "recommended_owner_decision": "",
        "recommended_next_action": f"CHARLIE created {len(child_ids)} bounded recovery missions. No owner action is required.",
        "block_adjudication": {**decision, "child_mission_ids": child_ids},
    })
    result, status = transition_mission_review_state(
        mission_id, "paused", packet, expected_status="blocked",
        owner_decision="CHARLIE decomposed the oversized recovery; parent waits for bounded child results.",
        notes="CHARLIE decomposed an exhausted oversized failure without escalating false owner work.",
        database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(command_id, success=success, result={"parent": result, "children": child_results}, error="" if success else result.get("status", "transition_failed"), database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "decomposed" if success else "transition_failed", "result": result, "child_mission_ids": child_ids}


def _child_id(parent_id, rows):
    raw = parent_id + ":" + ":".join(str(row.get("id") or row.get("requirement") or "") for row in rows)
    return f"{parent_id}-R{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:8].upper()}"


def _finish_failure(command, command_id, result, error, database_url, connect_factory):
    complete_control_command(command_id, success=False, result=result, error=error, database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": error, "result": result}


def _load_executive_missions(*, database_url=None, connect_factory=None):
    """Load every actionable queue independently so old terminal rows cannot hide work."""
    statuses = ("in_progress", "blocked", "pr_ready", "release_approved", "approved", "new", "paused")
    missions = []
    seen = set()
    for status in statuses:
        result, status_code = list_missions(status=status, limit=100, database_url=database_url, connect_factory=connect_factory)
        if status_code >= 400:
            return {"success": False, "status": "executive_mission_bucket_unavailable", "failed_bucket": status, "missions": []}, status_code
        for mission in result.get("missions", []):
            mission_id = mission.get("mission_id")
            if mission_id and mission_id not in seen:
                seen.add(mission_id)
                missions.append(mission)
    return {"success": True, "status": "ok", "missions": missions}, 200


def _execute_family_reconciliation(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        return _finish_failure(command, command_id, loaded, "mission_reload_failed", database_url, connect_factory)
    child_states = command.get("child_states") if isinstance(command.get("child_states"), dict) else {}
    current_states = {}
    for child_id in child_states:
        child, child_status = get_mission(child_id, database_url=database_url, connect_factory=connect_factory)
        if child_status >= 400:
            return _finish_failure(command, command_id, child, "family_child_reload_failed", database_url, connect_factory)
        current_states[child_id] = str((child.get("mission") or {}).get("status") or "").lower()
    terminal = {"done", "merged", "deployed", "rejected", "cancelled"}
    if not current_states or any(status not in terminal for status in current_states.values()):
        return _finish_failure(command, command_id, {"child_states": current_states}, "family_children_incomplete", database_url, connect_factory)
    mission = loaded.get("mission") or {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    packet = cleared_review_packet(
        metadata.get("review_packet") or {},
        reason="all bounded child repairs reached terminal state and their evidence must be reconciled",
        return_to_stage="evidence_reviewer",
    )
    packet["mission_family_reconciliation"] = {
        "version": "charlie_family_reconciliation_v1",
        "child_states": current_states,
        "closure_owner": "CHARLIE",
    }
    result, status = transition_mission_review_state(
        mission_id, "approved", packet, expected_status="paused",
        notes="CHARLIE resumed the parent after every bounded recovery child reached terminal state.",
        database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(command_id, success=success, result=result, error="" if success else result.get("status", "transition_failed"), database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "family_reconciled" if success else "transition_failed", "result": result}


def _execute_delegated_review(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        return _finish_failure(command, command_id, loaded, "mission_reload_failed", database_url, connect_factory)
    mission = loaded.get("mission") or {}
    preliminary = delegated_review_assessment(mission)
    if not preliminary.get("allowed"):
        return _finish_failure(command, command_id, preliminary, "delegated_review_denied", database_url, connect_factory)
    pr_state = query_pr_state(preliminary.get("pr_reference"))
    dependency_states, dependency_error = _load_dependency_states(
        mission, database_url=database_url, connect_factory=connect_factory,
    )
    if dependency_error:
        return _finish_failure(
            command, command_id, dependency_error, "dependency_state_reload_failed",
            database_url, connect_factory,
        )
    assessment = delegated_review_assessment(
        mission, pr_state=pr_state, dependency_states=dependency_states,
    )
    if not assessment.get("allowed") or assessment.get("action") != "delegate_final_review":
        return _finish_failure(command, command_id, assessment, "delegated_review_verification_failed", database_url, connect_factory)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    packet = dict(metadata.get("review_packet") or {})
    packet.update({
        "review_status": "charlie_delegated_final_approved",
        "recommended_next_action": "CORE release bridge will merge, deploy, and verify the approved low-risk change.",
        "delegated_review": {
            "version": "charlie_delegated_review_v1", "decision": "approve_final_release",
            "authority_tier": command.get("authority_tier"), "policy_id": command.get("policy_id"),
            "reason": assessment.get("reason"), "pr_head_sha": (assessment.get("reconciliation") or {}).get("head_sha"),
        },
    })
    result, status = transition_mission_review_state(
        mission_id, "release_approved", packet, expected_status="pr_ready",
        owner_decision="CHARLIE approved final release under bounded delegated review policy.",
        notes="CHARLIE delegated review passed current PR, evidence, acceptance, and protected-surface gates.",
        database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(command_id, success=success, result={"assessment": assessment, "transition": result}, error="" if success else result.get("status", "transition_failed"), database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "delegated_review_approved" if success else "transition_failed", "result": result}


def _load_dependency_states(mission, *, database_url=None, connect_factory=None):
    states = {}
    for dependency_id in mission_dependency_ids(mission):
        loaded, status = get_mission(
            dependency_id, database_url=database_url, connect_factory=connect_factory,
        )
        if status >= 400:
            return {}, {
                "status": "dependency_state_unavailable",
                "dependency_id": dependency_id,
                "status_code": status,
            }
        dependency = loaded.get("mission") if isinstance(loaded.get("mission"), dict) else {}
        states[dependency_id] = str(dependency.get("status") or "unknown").lower()
    return states, None


def _execute_queue_selection(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        return _finish_failure(command, command_id, loaded, "mission_reload_failed", database_url, connect_factory)
    mission = loaded.get("mission") or {}
    assessment = queue_candidate_assessment(mission)
    if not assessment.get("allowed"):
        return _finish_failure(command, command_id, assessment, "queue_selection_denied", database_url, connect_factory)
    result, status = update_mission_status(
        mission_id, "approved", expected_status="new",
        owner_decision="CHARLIE selected this low-risk mission as the next goal-aligned work item.",
        notes="CHARLIE maintained the bounded three-mission execution runway.",
        metadata={"charlie_queue_selection": {"policy_id": command.get("policy_id"), "priority_score": command.get("priority_score")}},
        database_url=database_url, connect_factory=connect_factory,
    )
    success = status < 400 and result.get("success")
    complete_control_command(command_id, success=success, result=result, error="" if success else result.get("status", "transition_failed"), database_url=database_url, connect_factory=connect_factory)
    return {"command": command, "status": "queue_selected" if success else "transition_failed", "result": result}
