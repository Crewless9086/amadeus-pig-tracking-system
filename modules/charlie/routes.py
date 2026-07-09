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
from modules.charlie.mission_memory import (
    final_artifact_contract_packet,
    mission_memory_from_metadata,
    parallel_agent_planning_packet,
    partial_recovery_contract_packet,
    replay_packet,
)
from modules.charlie.mission_quality import score_mission_quality
from modules.charlie.replay_stress import golden_example_candidate, stress_replay_mission
from modules.charlie.tool_permissions import check_tool_permission, permission_packet, tool_permission_registry
from modules.charlie.vault_retrieval import autonomy_readiness_packet, owner_preference_packet, retrieve_vault_sources
from modules.charlie.source_map import IMPLEMENTATION_SOURCE_MAP, SOURCE_MAP_VERSION, implementation_source_packet
from modules.charlie.improvement_analyst import (
    analyze_mission_replay,
    create_owner_gated_improvement_missions,
    generate_and_store_proposals,
    list_improvement_proposals,
    record_proposal_decision,
)
from modules.charlie.owner_approval_inbox import (
    list_owner_approval_inbox,
    record_owner_approval_decision,
)


charlie_bp = Blueprint("charlie", __name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_MEDIA_DIR = REPO_ROOT / ".charlie_runner" / "review_media"
LEGACY_REVIEW_MEDIA_DIR = REPO_ROOT / ".charlie_runner" / "review-media"
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
        compact=str(request.args.get("compact") or "").strip().lower() in {"1", "true", "yes"},
    )
    compact = str(request.args.get("compact") or "").strip().lower() in {"1", "true", "yes"}
    if compact and isinstance(result, dict) and isinstance(result.get("missions"), list):
        result = {**result, "missions": [_mission_dashboard_summary(mission) for mission in result.get("missions", [])]}
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
    buckets, bucket_statuses = _dashboard_owner_work_buckets([
        ("in_progress", 1),
        ("release_in_progress", 1),
        ("pr_ready", 5),
        ("release_approved", 1),
        ("approved", 5),
    ])
    if max(bucket_statuses) >= 400:
        return jsonify({
            "success": False,
            "status": "runner_handoff_unavailable",
            "owner_queue_status": "owner_work_status_bucket_unavailable",
            "statuses": bucket_statuses,
            "can_run_shell_from_web": False,
        }), 503
    approved_queue = buckets.get("approved", [])
    in_progress = buckets.get("in_progress", [])
    pr_ready = buckets.get("pr_ready", [])
    release_approved = buckets.get("release_approved", [])
    release_in_progress = buckets.get("release_in_progress", [])

    active_mission = _first_mission(in_progress) or _first_mission(release_in_progress)
    review_backlog = pr_ready
    next_approved = _first_mission(approved_queue)
    next_release_approved = _first_mission(release_approved)
    local_status = _compact_runner_status(local_runner_status(include_orphans=False, include_git=False, include_ledger=False))
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
        "approved_queue": approved_queue,
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
    recent, recent_status = _dashboard_owner_queue(limit=8)
    recent_missions = recent.get("missions", [])
    buckets, bucket_statuses = _dashboard_owner_work_buckets([
        ("approved", 20),
        ("pr_ready", 5),
        ("blocked", 5),
        ("release_approved", 5),
        ("release_in_progress", 5),
    ])
    approved_queue = buckets.get("approved", [])
    review_ready = buckets.get("pr_ready", [])
    blocked = buckets.get("blocked", [])
    release_approved = buckets.get("release_approved", [])
    release_in_progress = buckets.get("release_in_progress", [])
    merged = {"success": True, "status": "skipped_for_fast_dashboard_refresh", "missions": []}
    deployed = {"success": True, "status": "skipped_for_fast_dashboard_refresh", "missions": []}
    merged_status = 200
    deployed_status = 200
    statuses = [
        summary_status,
        recent_status,
        *bucket_statuses,
        merged_status,
        deployed_status,
    ]
    if max(statuses) >= 400:
        return jsonify({
            "success": False,
            "status": "command_center_unavailable",
            "statuses": statuses,
        }), 503
    detailed = str(request.args.get("detail") or "").strip().lower() in {"1", "true", "yes", "full"}
    local_status = _compact_runner_status(local_runner_status(include_orphans=False, include_git=False, include_ledger=False))
    if detailed:
        vault_health, _vault_health_status = vault_tables_health()
        improvements, _improvements_status = list_improvement_proposals(limit=8)
    else:
        vault_health = {
            "success": True,
            "status": "fast_refresh_not_checked",
            "missing_tables": [],
            "tables": {},
        }
        improvements = {
            "success": True,
            "status": "fast_refresh_not_checked",
            "proposals": [],
            "execution_boundary": "Improvement proposals are loaded in full detail mode.",
        }
    readiness_items = []
    readiness_missions = recent.get("missions", [])[:3 if detailed else 0]
    for mission in readiness_missions:
        retrieval = retrieve_vault_sources(mission, limit=8, excerpt_chars=0)
        readiness_items.append({
            "mission_id": mission.get("mission_id", ""),
            "title": mission.get("title", ""),
            "status": mission.get("status", ""),
            "core_readiness": evaluate_core_readiness(mission),
            "vault_retrieval": {
                "workflow_template": retrieval.get("workflow_template", ""),
                "selected_count": retrieval.get("selected_count", 0),
                "sources": [{"path": item.get("path", ""), "score": item.get("score", 0), "reasons": item.get("reasons", [])} for item in retrieval.get("sources", [])],
                "implementation_sources": retrieval.get("implementation_sources", {}),
                "missing_docs": retrieval.get("missing_docs", []),
            },
        })
    response = {
        "success": True,
        "status": "ok",
        "charlie_core": {
            "version": CHARLIE_CORE_VERSION,
            "overall_target": "90%+ workflow readiness before deep income-stream missions",
            "templates": sorted(WORKFLOW_TEMPLATES.keys()),
            "recent_readiness": readiness_items,
            "readiness_detail": "full" if detailed else "summary_only_fast_refresh",
            "model_registry": _compact_model_registry_packet(),
            "final_artifact_contract": final_artifact_contract_packet(),
            "partial_recovery_contract": partial_recovery_contract_packet(),
            "tool_permissions": _compact_tool_permission_registry(),
            "owner_preferences": _compact_owner_preference_packet(),
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
            "waiting_final_bridge": release_approved,
            "in_progress": release_in_progress,
            "merged_waiting_live_verify": merged.get("missions", []),
            "deployed": deployed.get("missions", []),
            "verify_url_configured": bool(os.getenv("CHARLIE_RELEASE_VERIFY_URL") or os.getenv("AMADEUS_BACKEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_EXTERNAL_HOSTNAME")),
        },
        "queue": {
            "approved": approved_queue,
            "ordering": "queue.priority asc, urgency asc, created_at asc",
            "execution_boundary": "Local runner picks only one approved mission at a time and waits while a mission is active or in release.",
        },
        "review": {
            "ready": review_ready,
            "blocked": blocked,
        },
        "improvements": {
            "proposals": improvements.get("proposals", []),
            "pending": [proposal for proposal in improvements.get("proposals", []) if proposal.get("status") == "pending"],
            "status": improvements.get("status", "unavailable"),
            "execution_boundary": improvements.get("execution_boundary", "Improvement proposals are advisory records only."),
        },
        "recent_missions": recent_missions,
        "local_runner": local_status,
        "local_runner_scope": "render_cannot_see_laptop_runner" if _running_on_render() else "local_machine",
        "execution_boundary": "Dashboard records decisions and evidence. Local runner/Codex executes builds and release bridge actions.",
    }
    response["autonomy_readiness"] = autonomy_readiness_packet(response)
    return jsonify(response), 200


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


@charlie_bp.route("/charlie/core/improvements/analyze-mission/<mission_id>", methods=["POST"])
def charlie_core_improvements_analyze_mission_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    loaded, load_status = get_mission(mission_id)
    if load_status >= 400:
        return jsonify(loaded), load_status
    result, status_code = analyze_mission_replay(loaded.get("mission") or {})
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/improvements/create-owner-gated", methods=["POST"])
def charlie_core_improvements_create_owner_gated_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = create_owner_gated_improvement_missions(
        limit=payload.get("limit", 50),
        max_create=payload.get("max_create", 3),
    )
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


@charlie_bp.route("/charlie/owner-approval-inbox", methods=["GET"])
def charlie_owner_approval_inbox_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = list_owner_approval_inbox(limit_per_status=request.args.get("limit_per_status", 12))
    return jsonify(result), status_code


@charlie_bp.route("/charlie/owner-approval-inbox/<mission_id>/<approval_id>/decision", methods=["POST"])
def charlie_owner_approval_inbox_decision_route(mission_id, approval_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_owner_approval_decision(
        mission_id,
        approval_id,
        decision=str(payload.get("decision") or "").strip(),
        comments=str(payload.get("comments") or "").strip(),
        edited_text=str(payload.get("edited_text") or "").strip(),
    )
    return jsonify(result), status_code


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


@charlie_bp.route("/charlie/core/source-map", methods=["GET"])
def charlie_core_source_map_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    mission = {
        "mission_type": request.args.get("mission_type", ""),
        "title": request.args.get("title", ""),
        "raw_text": request.args.get("q", ""),
    }
    return jsonify({
        "success": True,
        "status": "ok",
        "version": SOURCE_MAP_VERSION,
        "source_map": IMPLEMENTATION_SOURCE_MAP,
        "matched": implementation_source_packet(mission) if any(mission.values()) else {},
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
        "parallel_planning": parallel_agent_planning_packet([
            item.get("agent", "")
            for item in mission.get("agent_workflow", [])
            if isinstance(item, dict)
        ]),
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
    if isinstance(result, dict) and isinstance(result.get("review_packet"), dict):
        result = dict(result)
        result["review_packet"] = _normalize_review_packet_media(result["review_packet"], mission_id)
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/replay", methods=["GET"])
def charlie_build_relay_mission_replay_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_mission(mission_id)
    if status_code >= 400:
        return jsonify(result), status_code
    mission = result.get("mission") or {}
    packet = replay_packet(mission)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    agent_execution = metadata.get("agent_execution") if isinstance(metadata.get("agent_execution"), dict) else review_packet.get("agent_execution", {})
    packet.update({
        "success": True,
        "status": "ok",
        "final_artifact_contract": final_artifact_contract_packet(),
        "partial_recovery_contract": partial_recovery_contract_packet(),
        "mission_quality": review_packet.get("mission_quality") or score_mission_quality(mission, review_packet, agent_execution),
        "recovery_packet": review_packet.get("recovery_packet") or review_packet.get("partial_recovery") or {},
        "parallel_planning": parallel_agent_planning_packet([
            item.get("agent", "")
            for item in mission.get("agent_workflow", [])
            if isinstance(item, dict)
        ]),
    })
    return jsonify(packet), 200


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/replay/stress", methods=["GET"])
def charlie_build_relay_mission_replay_stress_route(mission_id):
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
        "stress": stress_replay_mission(mission),
        "golden_example_candidate": golden_example_candidate(mission),
    }), 200


@charlie_bp.route("/charlie/build-relay/review-media/<mission_id>/<filename>", methods=["GET"])
def charlie_build_relay_review_media_route(mission_id, filename):
    denied = require_owner_read_access()
    if denied:
        return denied
    safe_mission_id = "".join(char if char.isalnum() or char in "_.-" else "-" for char in str(mission_id or ""))[:120]
    safe_filename = Path(str(filename or "")).name
    if not safe_mission_id or not safe_filename or Path(safe_filename).suffix.lower() not in REVIEW_MEDIA_EXTENSIONS:
        return jsonify({"success": False, "status": "review_media_not_found"}), 404
    for root in (REVIEW_MEDIA_DIR, LEGACY_REVIEW_MEDIA_DIR):
        media_dir = root / safe_mission_id
        try:
            resolved_dir = media_dir.resolve()
            resolved_root = root.resolve()
        except OSError:
            continue
        if resolved_dir != resolved_root and resolved_root not in resolved_dir.parents:
            continue
        media_path = resolved_dir / safe_filename
        if media_path.exists() and media_path.is_file():
            return send_from_directory(resolved_dir, safe_filename)
    return jsonify({"success": False, "status": "review_media_not_found"}), 404


def _owner_work_missions_for_status(status, limit=1):
    parsed_limit = max(int(limit or 1), 1)
    return list_owner_work_missions(status, limit=parsed_limit)


def _dashboard_owner_work_status_queue(status, limit=1):
    result, status_code = _owner_work_missions_for_status(status, limit=limit)
    if status_code >= 400:
        return result, status_code
    return {
        **result,
        "missions": [_mission_dashboard_summary(mission) for mission in result.get("missions", [])],
    }, status_code


def _dashboard_owner_work_buckets(status_limits):
    buckets = {}
    statuses = []
    for status, limit in status_limits:
        result, status_code = _dashboard_owner_work_status_queue(status, limit=limit)
        statuses.append(status_code)
        if status_code < 400:
            buckets[status] = result.get("missions", [])
    return buckets, statuses or [200]


def _dashboard_owner_queue(limit=8):
    result, status_code = list_missions(status="owner_queue", limit=limit, compact=True)
    if status_code >= 400:
        return result, status_code
    return {
        **result,
        "missions": [_mission_dashboard_summary(mission) for mission in result.get("missions", [])],
    }, status_code


def _compact_model_registry_packet():
    registry = model_registry_packet()
    models = registry.get("models") if isinstance(registry.get("models"), dict) else {}
    return {
        "version": registry.get("version", ""),
        "models": {key: {"registry_key": key} for key in models},
        "safety_note": registry.get("safety_note", "Manual routing"),
    }


def _compact_tool_permission_registry():
    registry = tool_permission_registry()
    allowlist = registry.get("agent_tool_allowlist") if isinstance(registry.get("agent_tool_allowlist"), dict) else {}
    red_zone = registry.get("red_zone_tools") if isinstance(registry.get("red_zone_tools"), list) else []
    return {
        "version": registry.get("version", ""),
        "agent_tool_allowlist": {agent: [] for agent in allowlist},
        "red_zone_tools": red_zone[:12],
    }


def _compact_owner_preference_packet():
    packet = owner_preference_packet()
    return {
        "version": packet.get("version", ""),
        "summary": _short_text(packet.get("summary"), 300),
        "source": packet.get("source", ""),
    }


def _first_mission(result):
    missions = result.get("missions") if isinstance(result, dict) else result
    missions = missions or []
    return missions[0] if missions else None


def _mission_status_buckets(missions):
    buckets = {}
    for mission in missions or []:
        if not isinstance(mission, dict):
            continue
        status = str(mission.get("status") or "").strip()
        if not status:
            continue
        buckets.setdefault(status, []).append(mission)
    return buckets


def _mission_dashboard_summary(mission):
    mission = mission if isinstance(mission, dict) else {}
    mission_id = str(mission.get("mission_id") or "").strip()
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    compact_review_packet = {
        key: review_packet.get(key)
        for key in (
            "summary",
            "review_status",
            "blocked_agent",
            "blocked_reason",
            "local_preview",
            "links",
            "test_evidence",
            "visual_review",
            "recommended_next_action",
            "backflow_events",
            "unresolved_blockers",
            "mission_quality",
            "recovery_packet",
            "repo_test_command_memory",
        )
        if key in review_packet
    }
    compact_review_packet = _compact_review_packet(compact_review_packet, mission_id=mission_id)
    compact_metadata = {}
    if compact_review_packet:
        compact_metadata["review_packet"] = compact_review_packet
    mission_memory = mission_memory_from_metadata(metadata)
    if mission_memory.get("events") or mission_memory.get("updated_at"):
        compact_metadata["mission_memory"] = {
            "version": mission_memory.get("version", ""),
            "updated_at": mission_memory.get("updated_at", ""),
            "latest_by_agent": {
                agent: {
                    "type": item.get("type", ""),
                    "attempt": item.get("attempt", 1),
                    "summary": _short_text(item.get("summary", ""), 220),
                    "quality_gate": item.get("quality_gate", {}),
                }
                for agent, item in mission_memory.get("latest_by_agent", {}).items()
                if isinstance(item, dict)
            },
            "recent_recovery_notes": _compact_event_list(mission_memory.get("recovery_notes"), limit=3),
        }
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    compact_vault = {
        key: vault.get(key)
        for key in (
            "mission_stage",
            "confidence_target",
            "problem_statement",
            "desired_outcome",
            "current_agent",
            "review_quality",
            "vault_readiness",
            "source_truth",
        )
        if key in vault
    }
    for key in ("problem_statement", "desired_outcome", "source_truth"):
        if key in compact_vault:
            compact_vault[key] = _short_text(compact_vault.get(key), 500)
    return {
        "mission_id": mission.get("mission_id", ""),
        "status": mission.get("status", ""),
        "source": mission.get("source", ""),
        "raw_text": _short_text(mission.get("raw_text", ""), 700),
        "title": _short_text(mission.get("title", ""), 180),
        "urgency": mission.get("urgency", ""),
        "mission_type": mission.get("mission_type", ""),
        "approval_level": mission.get("approval_level", ""),
        "selected_next_step": _short_text(mission.get("selected_next_step", ""), 300),
        "owner_decision": _short_text(mission.get("owner_decision", ""), 300),
        "created_at": mission.get("created_at", ""),
        "updated_at": mission.get("updated_at", ""),
        "queue_class": mission.get("queue_class", "owner_work"),
        "queue_priority": mission.get("queue_priority"),
        "vault": compact_vault,
        "agent_workflow": _compact_workflow(mission.get("agent_workflow", [])),
        "metadata": compact_metadata,
    }


def _compact_workflow(workflow):
    items = workflow if isinstance(workflow, list) else []
    compact = []
    for item in items[:24]:
        item = item if isinstance(item, dict) else {}
        compact.append({
            "agent": _short_text(item.get("agent", ""), 60),
            "status": _short_text(item.get("status", "pending"), 40),
            "findings": _short_text(item.get("findings", ""), 220),
            "updated_at": _short_text(item.get("updated_at", ""), 60),
        })
    return compact


def _compact_review_packet(packet, mission_id=""):
    packet = packet if isinstance(packet, dict) else {}
    compact = dict(packet)
    if "summary" in compact:
        compact["summary"] = _short_text(compact.get("summary"), 900)
    if "blocked_reason" in compact:
        compact["blocked_reason"] = _short_text(compact.get("blocked_reason"), 500)
    if "test_evidence" in compact:
        compact["test_evidence"] = [_short_text(item, 350) for item in _as_list(compact.get("test_evidence"))[:4]]
    if "backflow_events" in compact:
        compact["backflow_events"] = _compact_event_list(compact.get("backflow_events"), limit=3)
    if "unresolved_blockers" in compact:
        compact["unresolved_blockers"] = _compact_event_list(compact.get("unresolved_blockers"), limit=5)
    if "visual_review" in compact:
        compact["visual_review"] = _compact_visual_review(compact.get("visual_review"), mission_id=mission_id)
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_visual_review(visual_review, mission_id=""):
    review = visual_review if isinstance(visual_review, dict) else {}
    media = []
    for item in _as_list(review.get("media"))[:4]:
        item = item if isinstance(item, dict) else {}
        reference = str(item.get("reference") or item.get("url") or "").strip()
        if reference.startswith("data:image/"):
            reference = ""
        reference = _dashboard_review_media_reference(mission_id, reference)
        media.append({
            "label": _short_text(item.get("label") or item.get("filename") or "Review media", 90),
            "reference": reference,
            "media_type": item.get("media_type") or "image",
        })
    capture = review.get("capture") if isinstance(review.get("capture"), dict) else {}
    return {
        "status": review.get("status", ""),
        "summary": _short_text(review.get("summary"), 600),
        "capture_source": review.get("capture_source") or capture.get("capture_source", ""),
        "local_preview": review.get("local_preview") if isinstance(review.get("local_preview"), dict) else {},
        "media": [item for item in media if item.get("reference")],
        "stage_evidence": _compact_event_list(review.get("stage_evidence"), limit=4),
    }


def _normalize_review_packet_media(packet, mission_id=""):
    packet = dict(packet if isinstance(packet, dict) else {})
    visual_review = packet.get("visual_review") if isinstance(packet.get("visual_review"), dict) else {}
    if visual_review:
        visual_review = dict(visual_review)
        normalized_media = []
        for item in _as_list(visual_review.get("media")):
            item = dict(item if isinstance(item, dict) else {})
            reference = str(item.get("reference") or item.get("url") or "").strip()
            if reference.startswith("data:image/"):
                reference = ""
            item["reference"] = _dashboard_review_media_reference(mission_id, reference)
            if item.get("reference"):
                normalized_media.append(item)
        visual_review["media"] = normalized_media
        packet["visual_review"] = visual_review
    return packet


def _dashboard_review_media_reference(mission_id, reference):
    reference = str(reference or "").strip()
    if not reference:
        return ""
    if reference.startswith(("/api/", "http://", "https://")):
        return reference
    if not mission_id:
        return reference
    safe_mission_id = "".join(char if char.isalnum() or char in "_.-" else "-" for char in str(mission_id or ""))[:120]
    safe_filename = Path(reference).name
    if not safe_mission_id or not safe_filename or Path(safe_filename).suffix.lower() not in REVIEW_MEDIA_EXTENSIONS:
        return reference
    for root in (REVIEW_MEDIA_DIR, LEGACY_REVIEW_MEDIA_DIR):
        review_path = root / safe_mission_id / safe_filename
        if review_path.exists() and review_path.is_file():
            return f"/api/charlie/build-relay/review-media/{safe_mission_id}/{safe_filename}"
    return reference


def _compact_runner_status(status):
    status = status if isinstance(status, dict) else {}
    compact = {
        key: status.get(key)
        for key in (
            "success",
            "status",
            "active",
            "pid",
            "process_alive",
            "heartbeat_fresh",
            "last_seen",
            "age_seconds",
            "last_result_status",
            "last_mission_id",
            "elapsed_seconds",
            "changed_files_count",
            "final_artifact_present",
            "execution_artifact",
            "agent_runner_version",
            "runner_source_commit",
            "current_source_commit",
            "runner_code_stale",
            "current_agent",
            "current_action",
            "agent_ledger_path",
            "log_path",
            "heartbeat_path",
            "command",
            "next_action",
            "can_start_from_web",
            "can_stop_from_web",
        )
        if key in status
    }
    compact["stdout_tail"] = _short_text(status.get("stdout_tail"), 500)
    compact["stderr_tail"] = _short_text(status.get("stderr_tail"), 500)
    compact["orphan_processes"] = _compact_event_list(status.get("orphan_processes"), limit=3)
    compact["agent_ledger"] = _compact_agent_ledger(status.get("agent_ledger"))
    return compact


def _compact_agent_ledger(ledger):
    ledger = ledger if isinstance(ledger, dict) else {}
    latest = ledger.get("latest_stage") if isinstance(ledger.get("latest_stage"), dict) else {}
    return {
        "version": ledger.get("version", ""),
        "execution_id": ledger.get("execution_id", ""),
        "status": ledger.get("status", ""),
        "last_progress_at": ledger.get("last_progress_at", ""),
        "blocked_agent": ledger.get("blocked_agent", ""),
        "blocked_reason": _short_text(ledger.get("blocked_reason"), 400),
        "backflow_events": _compact_event_list(ledger.get("backflow_events"), limit=3),
        "latest_stage": {
            "agent": latest.get("agent", ""),
            "status": latest.get("status", ""),
            "attempt": latest.get("attempt", 1),
            "current_action": _short_text(latest.get("current_action"), 220),
            "commands_run": [_short_text(item, 180) for item in _as_list(latest.get("commands_run"))[-3:]],
            "files_inspected": [_short_text(item, 160) for item in _as_list(latest.get("files_inspected"))[-5:]],
            "changed_files": [_short_text(item, 160) for item in _as_list(latest.get("changed_files"))[-5:]],
            "stdout_tail": _short_text(latest.get("stdout_tail"), 500),
            "stderr_tail": _short_text(latest.get("stderr_tail"), 500),
            "quality_gate": latest.get("quality_gate") if isinstance(latest.get("quality_gate"), dict) else {},
        },
    }


def _compact_event_list(items, limit=5):
    compact = []
    for item in _as_list(items)[:limit]:
        if isinstance(item, dict):
            compact.append({str(key): _short_text(value, 300) for key, value in item.items() if key not in {"reference", "image", "data_url"}})
        else:
            compact.append(_short_text(item, 300))
    return compact


def _as_list(value):
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _short_text(value, limit=500):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}..."


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
