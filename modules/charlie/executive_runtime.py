"""Runtime adapter that lets CHARLIE supervise CORE without bypassing authority."""

from __future__ import annotations

import os

from modules.charlie.executive_control import build_executive_cycle
from modules.charlie.executive_store import (
    complete_control_command,
    load_executive_context,
    queue_outbox,
    record_control_command,
    upsert_recovery_case,
)
from modules.charlie.mission_store import get_mission, list_missions, transition_mission_review_state
from modules.charlie.review_readiness import cleared_review_packet


def executive_mode():
    value = str(os.getenv("CHARLIE_EXECUTIVE_MODE", "observe") or "observe").strip().lower()
    return value if value in {"off", "observe", "active"} else "observe"


def run_executive_cycle(*, runner=None, database_url=None, connect_factory=None):
    mode = executive_mode()
    if mode == "off":
        return {"success": True, "status": "executive_disabled", "mode": mode}, 200
    loaded, loaded_status = list_missions(limit=100, database_url=database_url, connect_factory=connect_factory)
    context, context_status = load_executive_context(database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400 or context_status >= 400:
        return {"success": False, "status": "executive_context_unavailable", "mode": mode, "mission_status": loaded_status, "policy_status": context_status}, 503
    cycle = build_executive_cycle(loaded.get("missions", []), context.get("policies", []), runner=runner, goals=context.get("goals", []))
    results = []
    for command in cycle["commands"]:
        recorded, record_status = record_control_command(command, database_url=database_url, connect_factory=connect_factory)
        if record_status >= 400:
            results.append({"command": command, "status": "record_failed"})
            continue
        if not recorded.get("created"):
            results.append({"command": command, "status": "duplicate_skipped"})
            continue
        if mode != "active":
            complete_control_command(recorded["command_id"], success=True, result={"status": "observed_no_execution"}, database_url=database_url, connect_factory=connect_factory)
            results.append({"command": command, "status": "observed"})
            continue
        if command.get("action") == "schedule_recovery":
            results.append(_execute_recovery(command, recorded["command_id"], database_url, connect_factory))
        else:
            complete_control_command(recorded["command_id"], success=True, result={"status": "runner_will_pick_approved_queue"}, database_url=database_url, connect_factory=connect_factory)
            results.append({"command": command, "status": "queue_progress_observed"})
    if mode == "active":
        for escalation in cycle["escalations"]:
            queue_outbox("NEEDS_OWNER_APPROVAL", escalation, idempotency_key=f"owner:{escalation.get('mission_id')}:{escalation.get('block_class')}", database_url=database_url, connect_factory=connect_factory)
    return {"success": True, "status": "executive_cycle_complete", "mode": mode, "cycle": cycle, "results": results}, 200


def _execute_recovery(command, command_id, database_url, connect_factory):
    mission_id = command.get("mission_id")
    case, case_status = upsert_recovery_case(mission_id, command, database_url=database_url, connect_factory=connect_factory)
    if case_status >= 400 or int(case.get("attempt_count") or 0) > int(case.get("attempt_limit") or 3):
        complete_control_command(command_id, success=False, result=case, error="recovery_budget_exhausted_or_unavailable", database_url=database_url, connect_factory=connect_factory)
        queue_outbox("NEEDS_OWNER_APPROVAL", {"mission_id": mission_id, "reason": "recovery_budget_exhausted"}, idempotency_key=f"recovery-exhausted:{mission_id}:{command.get('fingerprint')}", database_url=database_url, connect_factory=connect_factory)
        return {"command": command, "status": "owner_required", "recovery": case}
    loaded, loaded_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if loaded_status >= 400:
        complete_control_command(command_id, success=False, result=loaded, error="mission_reload_failed", database_url=database_url, connect_factory=connect_factory)
        return {"command": command, "status": "mission_reload_failed", "result": loaded, "recovery": case}
    mission = loaded.get("mission") if isinstance(loaded.get("mission"), dict) else {}
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
