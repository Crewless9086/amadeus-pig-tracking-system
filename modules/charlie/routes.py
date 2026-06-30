from flask import Blueprint, jsonify, request

from modules.auth.owner_access import require_owner_read_access
from modules.charlie.build_relay import (
    build_relay_policy,
    handle_charlie_telegram_webhook,
)
from modules.charlie.runner_control import runner_status as local_runner_status
from modules.charlie.mission_store import (
    get_mission,
    list_missions,
    mission_status_summary,
    record_mission,
    update_mission_workflow_step,
    update_mission_status,
    update_mission_vault,
)


charlie_bp = Blueprint("charlie", __name__)


@charlie_bp.route("/charlie/build-relay/policy", methods=["GET"])
def charlie_build_relay_policy_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "status": "charlie_build_relay_policy",
        "charlie_build_relay": build_relay_policy(),
    }), 200


@charlie_bp.route("/charlie/build-relay/telegram/webhook", methods=["POST"])
def charlie_build_relay_telegram_webhook_route():
    payload = request.get_json(silent=True) or {}
    result, status_code = handle_charlie_telegram_webhook(payload, headers=request.headers)
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions", methods=["GET"])
def charlie_build_relay_missions_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = list_missions(
        status=request.args.get("status", ""),
        limit=request.args.get("limit", 10),
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions", methods=["POST"])
def charlie_build_relay_mission_create_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    raw_text = str(payload.get("raw_text") or payload.get("concept") or "").strip()
    if not raw_text:
        return jsonify({"success": False, "status": "mission_text_required"}), 400
    mission = {
        "raw_text": raw_text,
        "title": str(payload.get("title") or raw_text).strip(),
        "urgency": str(payload.get("urgency") or "P2").strip(),
        "mission_type": str(payload.get("mission_type") or "feature build").strip(),
        "approval_level": str(payload.get("approval_level") or "LEVEL 3").strip(),
        "desired_outcome": str(payload.get("desired_outcome") or "").strip(),
        "scope_summary": str(payload.get("scope_summary") or "").strip(),
        "acceptance_criteria": payload.get("acceptance_criteria") or [],
        "test_plan": payload.get("test_plan") or [],
        "pressure_test_plan": payload.get("pressure_test_plan") or [],
        "forbidden_actions": payload.get("forbidden_actions") or [],
        "owner_decisions_needed": payload.get("owner_decisions_needed") or [],
        "media_references": payload.get("media_references") or [],
        "metadata": {
            "created_from": "charlie_dashboard",
        },
    }
    result, status_code = record_mission(mission, source_context={"source": "charlie_dashboard"})
    response = {
        "success": result.get("stored") is True,
        **result,
    }
    return jsonify(response), status_code


@charlie_bp.route("/charlie/build-relay/missions/summary", methods=["GET"])
def charlie_build_relay_mission_summary_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = mission_status_summary()
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/runner/status", methods=["GET"])
def charlie_build_relay_runner_status_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    approved, approved_status = list_missions(status="approved", limit=1)
    in_progress, in_progress_status = list_missions(status="in_progress", limit=1)
    pr_ready, pr_ready_status = list_missions(status="pr_ready", limit=1)
    if max(approved_status, in_progress_status, pr_ready_status) >= 400:
        return jsonify({
            "success": False,
            "status": "runner_handoff_unavailable",
            "approved_status": approved.get("status"),
            "in_progress_status": in_progress.get("status"),
            "pr_ready_status": pr_ready.get("status"),
            "can_run_shell_from_web": False,
        }), 503

    active_mission = _first_mission(in_progress) or _first_mission(pr_ready)
    next_approved = _first_mission(approved)
    local_status = local_runner_status()
    if active_mission:
        runner_status = "active_mission_in_progress"
        next_action = "Codex is expected to finish or debrief the active mission before another approved mission is picked up."
    elif next_approved:
        runner_status = "approved_waiting_for_local_runner"
        next_action = (
            "Approved mission is waiting. The local runner is active and should pick it up shortly."
            if local_status.get("active")
            else "Approved mission is waiting. Start the local CHARLIE runner before expecting automatic pickup."
        )
    else:
        runner_status = "idle_no_approved_mission"
        next_action = "Create or approve a mission from Telegram or CHARLIE Mission Control."

    return jsonify({
        "success": True,
        "status": runner_status,
        "active_mission": active_mission,
        "next_approved_mission": next_approved,
        "next_action": next_action,
        "local_runner": local_status,
        "local_runner_command": ".\\venv\\Scripts\\python.exe scripts\\charlie_mission_pickup.py --watch --continuous --notify --interval-seconds 30",
        "local_runner_control_commands": {
            "status": ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py status",
            "start": ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py start",
            "stop": ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py stop",
        },
        "can_run_shell_from_web": False,
        "can_commit_from_web": False,
        "can_merge_from_web": False,
        "execution_boundary": "A local Codex/Cursor session or local runner process must execute pickup/build work.",
    }), 200


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>", methods=["GET"])
def charlie_build_relay_mission_detail_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_mission(mission_id)
    return jsonify(result), status_code


def _first_mission(result):
    missions = result.get("missions") or []
    return missions[0] if missions else None


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/decision", methods=["POST"])
def charlie_build_relay_mission_decision_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", "") or "").strip()
    owner_decision = str(payload.get("owner_decision", "") or "").strip()
    approval_level = str(payload.get("approval_level", "") or "").strip()
    result, status_code = update_mission_status(
        mission_id,
        status,
        owner_decision=owner_decision or f"Owner set mission status to {status}.",
        approval_level=approval_level,
        event_type="approval_decision",
        notes=owner_decision or f"Owner set mission status to {status}.",
        metadata={"source": "owner_api", "approval_level": approval_level},
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/vault", methods=["POST"])
def charlie_build_relay_mission_vault_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    vault_metadata = {
        "mission_vault": payload.get("mission_vault") if isinstance(payload.get("mission_vault"), dict) else {},
        "agent_workflow": payload.get("agent_workflow") if isinstance(payload.get("agent_workflow"), list) else [],
        "media_references": payload.get("media_references") if isinstance(payload.get("media_references"), list) else [],
    }
    vault_metadata = {key: value for key, value in vault_metadata.items() if value}
    if not vault_metadata:
        return jsonify({"success": False, "status": "mission_vault_metadata_required"}), 400
    result, status_code = update_mission_vault(
        mission_id,
        vault_metadata,
        status=str(payload.get("status") or "").strip(),
        owner_decision=str(payload.get("owner_decision") or "").strip(),
        notes=str(payload.get("notes") or "Mission vault updated from CHARLIE Mission Control.").strip(),
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/workflow", methods=["POST"])
def charlie_build_relay_mission_workflow_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = update_mission_workflow_step(
        mission_id,
        agent=str(payload.get("agent") or "").strip(),
        step_status=str(payload.get("step_status") or "complete").strip(),
        findings=str(payload.get("findings") or "").strip(),
        next_agent=str(payload.get("next_agent") or "").strip(),
    )
    return jsonify(result), status_code
