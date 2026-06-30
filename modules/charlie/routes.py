from flask import Blueprint, jsonify, request

from modules.auth.owner_access import require_owner_read_access
from modules.charlie.build_relay import (
    build_relay_policy,
    handle_charlie_telegram_webhook,
)
from modules.charlie.mission_store import get_mission, list_missions, mission_status_summary, update_mission_status


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
    if active_mission:
        runner_status = "active_mission_in_progress"
        next_action = "Codex is expected to finish or debrief the active mission before another approved mission is picked up."
    elif next_approved:
        runner_status = "approved_waiting_for_local_runner"
        next_action = "Start or keep the local Codex runner active so it can pick up this approved mission."
    else:
        runner_status = "idle_no_approved_mission"
        next_action = "Create or approve a mission from Telegram or CHARLIE Mission Control."

    return jsonify({
        "success": True,
        "status": runner_status,
        "active_mission": active_mission,
        "next_approved_mission": next_approved,
        "next_action": next_action,
        "local_runner_command": ".\\venv\\Scripts\\python.exe scripts\\charlie_mission_pickup.py --watch --continuous --notify --interval-seconds 30",
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
