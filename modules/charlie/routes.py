import os
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from modules.auth.owner_access import require_owner_read_access
from modules.charlie.build_relay import (
    build_relay_policy,
    handle_charlie_telegram_webhook,
)
from modules.charlie.runner_control import runner_status as local_runner_status
from modules.charlie.mission_store import (
    get_mission,
    get_mission_review_packet,
    list_missions,
    list_owner_work_missions,
    mission_status_summary,
    record_mission,
    record_mission_review_decision,
    update_new_mission_intake,
    update_mission_queue_priority,
    update_mission_workflow_step,
    update_mission_status,
    update_mission_vault,
)
from modules.charlie.core_workflow import (
    CHARLIE_CORE_VERSION,
    VAULT_SCHEMA,
    WORKFLOW_TEMPLATES,
    build_core_plan,
    evaluate_core_readiness,
)
from modules.charlie.vault_store import vault_tables_health
from modules.charlie.model_registry import choose_model, estimate_model_cost, model_registry_packet
from modules.charlie.tool_permissions import check_tool_permission, permission_packet, tool_permission_registry
from modules.charlie.improvement_analyst import (
    generate_and_store_proposals,
    list_improvement_proposals,
    record_proposal_decision,
)


charlie_bp = Blueprint("charlie", __name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_MEDIA_DIR = REPO_ROOT / ".charlie_runner" / "review_media"
REVIEW_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}


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
    approved, approved_status = _owner_work_missions_for_status("approved", limit=1)
    approved_queue, approved_queue_status = _owner_work_missions_for_status("approved", limit=5)
    in_progress, in_progress_status = _owner_work_missions_for_status("in_progress", limit=1)
    pr_ready, pr_ready_status = _owner_work_missions_for_status("pr_ready", limit=20)
    release_approved, release_approved_status = _owner_work_missions_for_status("release_approved", limit=1)
    release_in_progress, release_in_progress_status = _owner_work_missions_for_status("release_in_progress", limit=1)
    if max(approved_status, approved_queue_status, in_progress_status, pr_ready_status, release_approved_status, release_in_progress_status) >= 400:
        return jsonify({
            "success": False,
            "status": "runner_handoff_unavailable",
            "approved_status": approved.get("status"),
            "approved_queue_status": approved_queue.get("status"),
            "in_progress_status": in_progress.get("status"),
            "pr_ready_status": pr_ready.get("status"),
            "release_approved_status": release_approved.get("status"),
            "release_in_progress_status": release_in_progress.get("status"),
            "can_run_shell_from_web": False,
        }), 503

    active_mission = _first_mission(in_progress) or _first_mission(release_in_progress)
    review_backlog = pr_ready.get("missions", [])
    next_approved = _first_mission(approved)
    next_release_approved = _first_mission(release_approved)
    local_status = local_runner_status()
    local_runner_scope = "render_cannot_see_laptop_runner" if _running_on_render() else "local_machine"
    if active_mission:
        runner_status = "active_mission_in_progress"
        next_action = "Codex is expected to finish or debrief the active mission before another approved mission is picked up."
    elif next_release_approved:
        runner_status = "release_approved_waiting_for_local_release_bridge"
        next_action = "Final owner approval is recorded. The full local runner release bridge can merge a referenced PR, or block safely if release evidence is missing."
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
        "review_backlog": review_backlog,
        "next_approved_mission": next_approved,
        "approved_queue": approved_queue.get("missions", []),
        "next_release_approved_mission": next_release_approved,
        "next_action": next_action,
        "local_runner": local_status,
        "local_runner_scope": local_runner_scope,
        "local_runner_visibility_note": (
            "Render cannot see the laptop .charlie_runner heartbeat. Check local dashboard or scripts\\charlie_runner_control.py status for true local runner state."
            if local_runner_scope == "render_cannot_see_laptop_runner"
            else "This dashboard can read the local .charlie_runner heartbeat."
        ),
        "local_runner_command": ".\\venv\\Scripts\\python.exe scripts\\charlie_mission_pickup.py --watch --continuous --notify --execute-codex --watch-release --auto-merge-pr --interval-seconds 30",
        "local_runner_control_commands": {
            "status": ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py status",
            "start": ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py start",
            "stop": ".\\venv\\Scripts\\python.exe scripts\\charlie_runner_control.py stop",
        },
        "can_run_shell_from_web": False,
        "can_commit_from_web": False,
        "can_merge_from_web": False,
        "execution_boundary": "A local Codex/Cursor session or local runner process must execute pickup/build work. Missions at pr_ready remain in owner review and do not block the next approved build pickup.",
    }), 200


@charlie_bp.route("/charlie/build-relay/command-center", methods=["GET"])
def charlie_build_relay_command_center_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    summary, summary_status = mission_status_summary()
    recent, recent_status = list_missions(status="owner_queue", limit=8)
    approved_queue, approved_status = _owner_work_missions_for_status("approved", limit=20)
    review_ready, review_status = _owner_work_missions_for_status("pr_ready", limit=5)
    blocked, blocked_status = _owner_work_missions_for_status("blocked", limit=5)
    release_approved, release_approved_status = _owner_work_missions_for_status("release_approved", limit=5)
    release_in_progress, release_progress_status = _owner_work_missions_for_status("release_in_progress", limit=5)
    merged, merged_status = list_missions(status="merged", limit=5)
    deployed, deployed_status = list_missions(status="deployed", limit=5)
    statuses = [
        summary_status,
        recent_status,
        approved_status,
        review_status,
        blocked_status,
        release_approved_status,
        release_progress_status,
        merged_status,
        deployed_status,
    ]
    if max(statuses) >= 400:
        return jsonify({
            "success": False,
            "status": "command_center_unavailable",
            "statuses": statuses,
        }), 503
    local_status = local_runner_status()
    vault_health, _vault_health_status = vault_tables_health()
    improvements, _improvements_status = list_improvement_proposals(limit=8)
    readiness_items = []
    for mission in recent.get("missions", []):
        readiness_items.append({
            "mission_id": mission.get("mission_id", ""),
            "title": mission.get("title", ""),
            "status": mission.get("status", ""),
            "core_readiness": evaluate_core_readiness(mission),
        })
    return jsonify({
        "success": True,
        "status": "ok",
        "charlie_core": {
            "version": CHARLIE_CORE_VERSION,
            "overall_target": "90%+ workflow readiness before deep income-stream missions",
            "templates": sorted(WORKFLOW_TEMPLATES.keys()),
            "recent_readiness": readiness_items,
            "model_registry": model_registry_packet(),
            "tool_permissions": tool_permission_registry(),
        },
        "counts": summary.get("counts", {}),
        "vault": {
            "version": "charlie_vault_v1",
            "storage": "metadata_json_active_structured_tables_available",
            "health": vault_health,
            "structured_tables": [
                "charlie_vault_projects",
                "charlie_vault_artifacts",
                "charlie_agent_runs",
                "charlie_handoff_reports",
                "charlie_quality_gates",
                "charlie_owner_decisions",
                "charlie_deployments",
                "charlie_audit_log",
            ],
        },
        "release": {
            "waiting_final_bridge": release_approved.get("missions", []),
            "in_progress": release_in_progress.get("missions", []),
            "merged_waiting_live_verify": merged.get("missions", []),
            "deployed": deployed.get("missions", []),
            "verify_url_configured": bool(os.getenv("CHARLIE_RELEASE_VERIFY_URL") or os.getenv("AMADEUS_BACKEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_EXTERNAL_HOSTNAME")),
        },
        "queue": {
            "approved": approved_queue.get("missions", []),
            "ordering": "queue.priority asc, urgency asc, created_at asc",
            "execution_boundary": "Local runner picks only one approved mission at a time and waits while a mission is active or in release.",
        },
        "review": {
            "ready": review_ready.get("missions", []),
            "blocked": blocked.get("missions", []),
        },
        "improvements": {
            "proposals": improvements.get("proposals", []),
            "pending": [proposal for proposal in improvements.get("proposals", []) if proposal.get("status") == "pending"],
            "status": improvements.get("status", "unavailable"),
            "execution_boundary": improvements.get("execution_boundary", "Improvement proposals are advisory records only."),
        },
        "recent_missions": recent.get("missions", []),
        "local_runner": local_status,
        "local_runner_scope": "render_cannot_see_laptop_runner" if _running_on_render() else "local_machine",
        "execution_boundary": "Dashboard records decisions and evidence. Local runner/Codex executes builds and release bridge actions.",
    }), 200


@charlie_bp.route("/charlie/core/vault-health", methods=["GET"])
def charlie_core_vault_health_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = vault_tables_health()
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/improvements", methods=["GET"])
def charlie_core_improvements_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = list_improvement_proposals(
        status=request.args.get("status", ""),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/improvements/analyze", methods=["POST"])
def charlie_core_improvements_analyze_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = generate_and_store_proposals(limit=payload.get("limit", 50))
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/improvements/<proposal_id>/decision", methods=["POST"])
def charlie_core_improvement_decision_route(proposal_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_proposal_decision(
        proposal_id,
        decision=str(payload.get("decision") or "").strip(),
        comments=str(payload.get("comments") or "").strip(),
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/model-registry", methods=["GET"])
def charlie_core_model_registry_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    task_type = request.args.get("task_type", "")
    risk_level = request.args.get("risk_level", "medium")
    use_case = request.args.get("use_case", "")
    model = choose_model(task_type=task_type, risk_level=risk_level, required_use_case=use_case)
    cost = estimate_model_cost(
        model.get("registry_key", "default_reasoning"),
        input_tokens=request.args.get("input_tokens", 0),
        output_tokens=request.args.get("output_tokens", 0),
    )
    return jsonify({
        "success": True,
        "status": "ok",
        "registry": model_registry_packet(),
        "selected_model": model,
        "cost_estimate": cost,
    }), 200


@charlie_bp.route("/charlie/core/tool-permissions", methods=["GET"])
def charlie_core_tool_permissions_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    agent = request.args.get("agent", "")
    tool_class = request.args.get("tool_class", "")
    owner_approved = str(request.args.get("owner_approved", "")).strip().lower() in {"1", "true", "yes", "on"}
    return jsonify({
        "success": True,
        "status": "ok",
        "registry": tool_permission_registry(),
        "agent_permissions": permission_packet(agent) if agent else {},
        "permission_check": check_tool_permission(agent, tool_class, owner_approved=owner_approved) if agent and tool_class else {},
    }), 200


@charlie_bp.route("/charlie/core/templates", methods=["GET"])
def charlie_core_templates_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "status": "ok",
        "version": CHARLIE_CORE_VERSION,
        "vault_schema": VAULT_SCHEMA,
        "workflow_templates": WORKFLOW_TEMPLATES,
    }), 200


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/core-readiness", methods=["GET"])
def charlie_core_mission_readiness_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_mission(mission_id)
    if status_code >= 400:
        return jsonify(result), status_code
    mission = result.get("mission") or {}
    return jsonify({
        "success": True,
        "status": "ok",
        "mission_id": mission.get("mission_id", mission_id),
        "core_plan": build_core_plan(mission),
        "core_readiness": evaluate_core_readiness(mission),
    }), 200


def _running_on_render():
    return bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_HOSTNAME"))


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>", methods=["GET"])
def charlie_build_relay_mission_detail_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_mission(mission_id)
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>", methods=["PATCH"])
def charlie_build_relay_mission_update_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates") if isinstance(payload.get("updates"), dict) else payload
    result, status_code = update_new_mission_intake(
        mission_id,
        updates=updates,
        comment=str(payload.get("comment") or "").strip(),
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/review", methods=["GET"])
def charlie_build_relay_mission_review_packet_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_mission_review_packet(mission_id)
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/review-media/<mission_id>/<filename>", methods=["GET"])
def charlie_build_relay_review_media_route(mission_id, filename):
    denied = require_owner_read_access()
    if denied:
        return denied
    safe_mission_id = "".join(char if char.isalnum() or char in "_.-" else "-" for char in str(mission_id or ""))[:120]
    safe_filename = Path(str(filename or "")).name
    if not safe_mission_id or not safe_filename or Path(safe_filename).suffix.lower() not in REVIEW_MEDIA_EXTENSIONS:
        return jsonify({"success": False, "status": "review_media_not_found"}), 404
    media_dir = REVIEW_MEDIA_DIR / safe_mission_id
    try:
        resolved_dir = media_dir.resolve()
        resolved_root = REVIEW_MEDIA_DIR.resolve()
    except OSError:
        return jsonify({"success": False, "status": "review_media_not_found"}), 404
    if resolved_root not in resolved_dir.parents:
        return jsonify({"success": False, "status": "review_media_not_found"}), 404
    media_path = resolved_dir / safe_filename
    if not media_path.exists() or not media_path.is_file():
        return jsonify({"success": False, "status": "review_media_not_found"}), 404
    return send_from_directory(resolved_dir, safe_filename)


def _owner_work_missions_for_status(status, limit=1):
    parsed_limit = max(int(limit or 1), 1)
    return list_owner_work_missions(status, limit=parsed_limit)


def _first_mission(result):
    missions = result.get("missions") if isinstance(result, dict) else result
    missions = missions or []
    return missions[0] if missions else None


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/review", methods=["POST"])
def charlie_build_relay_mission_review_decision_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision") or "").strip()
    result, status_code = record_mission_review_decision(
        mission_id,
        decision=decision,
        comments=str(payload.get("comments") or "").strip(),
        target_stage=str(payload.get("target_stage") or "builder").strip(),
    )
    return jsonify(result), status_code


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


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/queue", methods=["POST"])
def charlie_build_relay_mission_queue_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = update_mission_queue_priority(
        mission_id,
        priority=payload.get("priority"),
        notes=str(payload.get("notes") or "Mission queue priority updated from CHARLIE Mission Control.").strip(),
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
