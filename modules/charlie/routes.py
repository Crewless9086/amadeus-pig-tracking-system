import hmac
import os
import re
import time
import json
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_from_directory, stream_with_context

from modules.charlie import runtime_path_root
from modules.auth.owner_access import (
    require_owner_admin_access,
    require_owner_read_access,
    require_strict_owner_admin_access,
    strict_owner_admin_principal,
)
from modules.charlie.environment import env_value
from modules.charlie.build_relay import (
    build_relay_policy,
    handle_charlie_telegram_webhook,
)
from modules.charlie.runner_control import runner_status as local_runner_status
from modules.charlie.mission_store import (
    get_mission,
    get_mission_review_packet,
    append_mission_admission_event,
    append_mission_control_event,
    bind_external_supervisor_candidate,
    bind_external_supervisor_branch,
    authorize_cursor_workspace_hook,
    invalidate_external_candidate_admission,
    read_external_supervisor_state,
    record_external_supervisor_state,
    prepare_external_dispatch_authorization,
    prepare_external_execution_succession,
    refresh_external_dispatch_authorization_base,
    read_current_mission_admission_authority,
    list_missions,
    list_owner_work_missions,
    create_owner_execution_hold,
    release_owner_execution_hold,
    mission_control_snapshot,
    mission_status_summary,
    record_mission,
    record_mission_review_decision,
    record_mission_outcome_handover,
    record_mission_outcome_evidence,
    update_new_mission_intake,
    update_mission_queue_priority,
    update_mission_workflow_step,
    update_mission_status,
    update_mission_vault,
)
from modules.charlie.cursor_cloud_identity import (
    APPROVED_REPOSITORY,
    CursorIdentityError,
    verify_cursor_oidc_token,
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
from modules.charlie.mission_governance import mission_governance_summary
from modules.charlie.final_readiness import evaluate_final_readiness
from modules.charlie.replay_stress import golden_example_candidate, stress_replay_mission
from modules.charlie.tool_permissions import check_tool_permission, permission_packet, tool_permission_registry
from modules.charlie.vault_retrieval import autonomy_readiness_packet, owner_preference_packet, retrieve_vault_sources
from modules.charlie.source_map import IMPLEMENTATION_SOURCE_MAP, SOURCE_MAP_VERSION, implementation_source_packet
from modules.charlie.improvement_analyst import (
    analyst_scorecard,
    analyze_mission_replay,
    create_owner_gated_improvement_missions,
    generate_and_store_proposals,
    list_improvement_proposals,
    record_proposal_decision,
    run_operational_analyst,
)
from modules.charlie.owner_approval_inbox import (
    list_owner_approval_inbox,
    record_owner_approval_decision,
)
from modules.charlie.agent_workforce import build_agent_workforce_packet
from modules.charlie.executive_runtime import executive_mode, run_executive_cycle
from modules.charlie.executive_store import executive_scorecard, list_capability_trust, mission_outbox_delivery
from modules.charlie.concurrency_control import revision_truth
from modules.charlie.private_policy import private_policy
from modules.charlie.private_runtime import handle_private_telegram_webhook
from modules.charlie.private_runtime import handle_authenticated_private_action
from modules.charlie.control_tower_feedback import (
    ACTION as CONTROL_TOWER_FEEDBACK_ACTION,
    MISSION_ID as CONTROL_TOWER_MISSION_ID,
    control_tower_feedback_readback,
)
from modules.charlie.private_stream import stream_private_turn
from modules.charlie.private_voice import synthesize_private_speech, transcribe_web_audio
from modules.charlie.private_store import decide_bundle, private_owner_snapshot
from modules.sales.conversation_learning import live_stock_learning_scorecard
from modules.beacon.workforce import beacon_workforce_scorecard


charlie_bp = Blueprint("charlie", __name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = runtime_path_root(REPO_ROOT)
REVIEW_MEDIA_DIR = RUNTIME_ROOT / ".charlie_runner" / "review_media"
LEGACY_REVIEW_MEDIA_DIR = RUNTIME_ROOT / ".charlie_runner" / "review-media"
REVIEW_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}
AGENT_WORKFORCE_CACHE = {"expires_at": 0.0, "packet": None}
AGENT_WORKFORCE_CACHE_SECONDS = 30
MISSION_CONTROL_CACHE = {"expires_at": 0.0, "packet": None}
MISSION_CONTROL_CACHE_SECONDS = 15
PRIVATE_DASHBOARD_CACHE = {"expires_at": 0.0, "packet": None}
PRIVATE_DASHBOARD_CACHE_SECONDS = 15


def _require_hermes_gateway_access():
    expected = str(env_value("CHARLIE_HERMES_GATEWAY_TOKEN") or "").strip()
    supplied = str(request.headers.get("Authorization") or "")
    supplied = supplied[7:].strip() if supplied.startswith("Bearer ") else ""
    if len(expected) < 32 or not hmac.compare_digest(expected, supplied):
        return jsonify({"success": False, "status": "hermes_gateway_unauthorized"}), 403
    return None


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
    callback_data = str(((payload.get("callback_query") or {}).get("data") or ""))
    if private_policy().get("explicitly_enabled") and callback_data.startswith("cm:"):
        result, status_code = handle_private_telegram_webhook(payload, headers=request.headers)
        if status_code == 403:
            result, status_code = handle_charlie_telegram_webhook(payload, headers=request.headers)
    elif private_policy().get("explicitly_enabled") and (not callback_data or callback_data.startswith("cp:")):
        result, status_code = handle_private_telegram_webhook(payload, headers=request.headers)
    else:
        result, status_code = handle_charlie_telegram_webhook(payload, headers=request.headers)
    return jsonify(result), status_code


@charlie_bp.route("/charlie/private/policy", methods=["GET"])
def charlie_private_policy_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    policy = private_policy()
    return jsonify({"success": True, "status": "charlie_private_policy", "policy": {key: value for key, value in policy.items() if key not in {"token", "secret"}}}), 200


@charlie_bp.route("/charlie/private/dashboard", methods=["GET"])
def charlie_private_dashboard_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    refresh = str(request.args.get("refresh") or "").lower() in {"1", "true", "yes"}
    now = time.monotonic()
    if not refresh and PRIVATE_DASHBOARD_CACHE.get("packet") and now < float(PRIVATE_DASHBOARD_CACHE.get("expires_at") or 0):
        return jsonify({**PRIVATE_DASHBOARD_CACHE["packet"], "cache": "fresh"}), 200
    with ThreadPoolExecutor(max_workers=5) as pool:
        private_future = pool.submit(private_owner_snapshot, limit=request.args.get("limit", 40))
        mission_future = pool.submit(mission_status_summary)
        executive_future = pool.submit(executive_scorecard)
        analyst_future = pool.submit(analyst_scorecard, limit=50)
        sam_learning_future = pool.submit(live_stock_learning_scorecard, limit=500)
        private, private_status = private_future.result()
        missions, mission_status = mission_future.result()
        executive, executive_status = executive_future.result()
        analyst, analyst_status = analyst_future.result()
        sam_learning, sam_learning_status = sam_learning_future.result()
    runner = local_runner_status(include_git=False, include_ledger=False)
    runner["local_runner_scope"] = "render_cannot_see_laptop_runner" if _running_on_render() else "local_machine"
    policy = private_policy()
    component_status = {"private": private_status, "missions": mission_status, "executive": executive_status, "analyst": analyst_status, "sam_learning": sam_learning_status}
    degraded = any(code >= 400 for code in component_status.values())
    packet = {
        "success": True,
        "status": "charlie_private_dashboard_degraded" if degraded else "charlie_private_dashboard_ready",
        "component_status": component_status,
        "private": private,
        "missions": missions,
        "executive": executive,
        "analyst": analyst,
        "sam_learning": sam_learning,
        "runner": runner,
        "policy": {key: value for key, value in policy.items() if key not in {"token", "secret"}},
    }
    PRIVATE_DASHBOARD_CACHE.update({"expires_at": time.monotonic() + PRIVATE_DASHBOARD_CACHE_SECONDS, "packet": packet})
    return jsonify(packet), 200


@charlie_bp.route("/charlie/private/message", methods=["POST"])
def charlie_private_message_route():
    denied = require_owner_admin_access()
    if denied:
        return denied
    policy = private_policy()
    if not policy.get("enabled"):
        return jsonify({"success": False, "status": "private_charlie_not_ready"}), 503
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return jsonify({"success": False, "status": "message_required"}), 400
    replies = []

    def web_sender(_chat_id, reply_text, **_kwargs):
        replies.append(reply_text)
        return {"success": True, "status": "web_reply_captured"}, 200

    update_id = "WEB-" + uuid.uuid4().hex.upper()
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": int(policy["owner_user_id"]), "username": "charlie_owner_web"},
            "chat": {"id": int(policy["owner_chat_id"]), "type": "private"},
            "text": text,
        },
    }
    result, status_code = handle_private_telegram_webhook(
        payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": policy["secret"]},
        sender=web_sender,
    )
    PRIVATE_DASHBOARD_CACHE.update({"expires_at": 0.0, "packet": None})
    return jsonify({**result, "reply": replies[-1] if replies else result.get("reply", ""), "channel": "owner_web"}), status_code


@charlie_bp.route("/charlie/private/message/stream", methods=["POST"])
def charlie_private_message_stream_route():
    denied = require_owner_admin_access()
    if denied:
        return denied
    policy = private_policy()
    if not policy.get("enabled"):
        return jsonify({"success": False, "status": "private_charlie_not_ready"}), 503
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return jsonify({"success": False, "status": "message_required"}), 400
    update_id = "WEBSTREAM-" + uuid.uuid4().hex.upper()
    payload = {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": int(policy["owner_user_id"]), "username": "charlie_owner_live"},
            "chat": {"id": int(policy["owner_chat_id"]), "type": "private"},
            "text": text,
        },
    }

    def runner(emit):
        def web_sender(_chat_id, _reply_text, **_kwargs):
            return {"success": True, "status": "web_stream_reply_captured"}, 200
        result, status = handle_private_telegram_webhook(
            payload, headers={"X-Telegram-Bot-Api-Secret-Token": policy["secret"]},
            sender=web_sender, event_sink=emit,
        )
        PRIVATE_DASHBOARD_CACHE.update({"expires_at": 0.0, "packet": None})
        return result, status

    response = Response(stream_with_context(stream_private_turn(text, runner)), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


@charlie_bp.route("/charlie/private/voice/transcribe", methods=["POST"])
def charlie_private_voice_transcribe_route():
    denied = require_owner_admin_access()
    if denied:
        return denied
    upload = request.files.get("audio")
    if not upload:
        return jsonify({"success": False, "status": "voice_audio_required"}), 400
    result, status = transcribe_web_audio(upload.read(), upload.filename, upload.mimetype, private_policy())
    return jsonify(result), status


@charlie_bp.route("/charlie/private/voice/speech", methods=["POST"])
def charlie_private_voice_speech_route():
    denied = require_owner_admin_access()
    if denied:
        return denied
    text = str((request.get_json(silent=True) or {}).get("text") or "").strip()
    result, status = synthesize_private_speech(text, private_policy())
    if status >= 400:
        return jsonify({key: value for key, value in result.items() if key != "audio"}), status
    return Response(result["audio"], status=200, mimetype=result.get("content_type") or "audio/mpeg", headers={"Cache-Control": "no-store"})


@charlie_bp.route("/charlie/private/decisions/<bundle_id>", methods=["POST"])
def charlie_private_decision_route(bundle_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    decision = str((request.get_json(silent=True) or {}).get("decision") or "").strip().lower()
    result, status_code = decide_bundle(bundle_id, decision)
    PRIVATE_DASHBOARD_CACHE.update({"expires_at": 0.0, "packet": None})
    return jsonify(result), status_code


@charlie_bp.route("/charlie/control-tower/feedback", methods=["POST"])
def charlie_control_tower_feedback_route():
    """Strict owner-private producer for canonical Control Tower feedback."""
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "status": "control_tower_feedback_mapping_required"}), 400
    policy = private_policy()
    if not policy.get("enabled"):
        return jsonify({"success": False, "status": "private_charlie_not_ready"}), 503
    authentication_payload = {
        "message": {
            "from": {"id": int(policy["owner_user_id"])},
            "chat": {"id": int(policy["owner_chat_id"]), "type": "private"},
        }
    }
    action = {**payload, "action": CONTROL_TOWER_FEEDBACK_ACTION}
    result, status = handle_authenticated_private_action(
        action,
        authentication_payload,
        {"X-Telegram-Bot-Api-Secret-Token": policy["secret"]},
        existing_mission_id=CONTROL_TOWER_MISSION_ID,
    )
    return jsonify(result), status


@charlie_bp.route("/charlie/control-tower/feedback", methods=["GET"])
def charlie_control_tower_feedback_readback_route():
    """Strict owner-private identity-only lifecycle readback."""
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    result, status = control_tower_feedback_readback(
        str(request.args.get("feedback_transaction_id") or "").strip())
    return jsonify(result), status


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


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/control-events", methods=["POST"])
def charlie_mission_control_event_route(mission_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "status": "mission_control_event_mapping_required"}), 400
    result, status = append_mission_control_event(
        mission_id, payload, recorded_by=strict_owner_admin_principal())
    return jsonify(result), status


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
    local_status = _compact_runner_status(local_runner_status(include_orphans=False, include_git=False, include_ledger=not _running_on_render()))
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
    local_status = _compact_runner_status(local_runner_status(include_orphans=False, include_git=False, include_ledger=not _running_on_render()))
    if detailed:
        vault_health, _vault_health_status = vault_tables_health()
        improvements, _improvements_status = list_improvement_proposals(status="pending", limit=8)
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
            "verify_url_configured": bool(env_value("CORE_RELEASE_VERIFY_URL") or os.getenv("AMADEUS_BACKEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_EXTERNAL_HOSTNAME")),
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
    if detailed:
        executive, executive_status = executive_scorecard()
        response["charlie_executive"] = {**executive, "mode": executive_mode(), "http_status": executive_status}
    else:
        response["charlie_executive"] = {"mode": executive_mode(), "status": "detail_required_for_scorecard"}
    response["autonomy_readiness"] = autonomy_readiness_packet(response)
    return jsonify(response), 200


@charlie_bp.route("/charlie/build-relay/mission-control", methods=["GET"])
def charlie_mission_control_snapshot_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    refresh = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
    now = time.monotonic()
    if not refresh and MISSION_CONTROL_CACHE.get("packet") and now < float(MISSION_CONTROL_CACHE.get("expires_at") or 0):
        return jsonify({**MISSION_CONTROL_CACHE["packet"], "cache": "fresh"}), 200
    snapshot, snapshot_status = _retry_dashboard_read(mission_control_snapshot, 100)
    statuses = [snapshot_status]
    if snapshot_status >= 400:
        return jsonify({"success": False, "status": "mission_control_snapshot_unavailable", "statuses": statuses}), 503
    owner_missions = _attach_mission_family_children(snapshot.get("missions", []))
    raw_buckets = _mission_status_buckets(owner_missions)
    packet = {
        "success": True,
        "status": "mission_control_snapshot_ready",
        "counts": snapshot.get("counts", {}),
        "buckets": {
            "active": [
                *raw_buckets.get("in_progress", []),
                *raw_buckets.get("release_in_progress", []),
                *raw_buckets.get("paused", []),
            ],
            "new": raw_buckets.get("new", []),
            "approved": raw_buckets.get("approved", []),
            "review": [*raw_buckets.get("pr_ready", []), *raw_buckets.get("release_approved", [])],
            "blocked": raw_buckets.get("blocked", []),
        },
        "source": "supabase_charlie_missions",
        "authoritative": True,
        "source_statuses": statuses,
        "counts_source": "canonical_owner_queue_snapshot",
        "revision_truth": revision_truth(
            REPO_ROOT,
            render_deployed_commit=str(os.getenv("RENDER_GIT_COMMIT") or os.getenv("RENDER_COMMIT") or ""),
        ),
        "cache": "refreshed",
    }
    MISSION_CONTROL_CACHE.update({"expires_at": time.monotonic() + MISSION_CONTROL_CACHE_SECONDS, "packet": packet})
    return jsonify(packet), 200


def _retry_dashboard_read(loader, *args, attempts=3):
    """Retry transient Render/Supabase read failures without hiding hard errors."""
    result, status_code = loader(*args)
    for attempt in range(1, max(1, int(attempts))):
        if status_code < 500:
            break
        time.sleep(0.2 * attempt)
        result, status_code = loader(*args)
    return result, status_code


def _attach_mission_family_children(missions):
    missions = [dict(mission) for mission in (missions or []) if isinstance(mission, dict)]
    by_id = {mission.get("mission_id"): mission for mission in missions if mission.get("mission_id")}
    for mission in missions:
        metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
        family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
        parent = by_id.get(family.get("parent_mission_id"))
        if not parent:
            continue
        parent_metadata = parent.setdefault("metadata", {})
        parent_family = parent_metadata.get("mission_family") if isinstance(parent_metadata.get("mission_family"), dict) else {}
        parent_family = dict(parent_family)
        children = parent_family.get("children") if isinstance(parent_family.get("children"), list) else []
        children = [item for item in children if isinstance(item, dict) and item.get("mission_id") != mission.get("mission_id")]
        children.append({
            "mission_id": mission.get("mission_id", ""),
            "title": mission.get("title", ""),
            "status": mission.get("status", ""),
            "sequence": family.get("sequence"),
            "finding_family": family.get("finding_family", ""),
        })
        parent_family.update({
            "root_mission_id": family.get("root_mission_id") or parent.get("mission_id", ""),
            "children": sorted(children, key=lambda item: (item.get("sequence") or 999, item.get("mission_id") or "")),
        })
        parent_metadata["mission_family"] = parent_family
    return missions


@charlie_bp.route("/charlie/agent-workforce", methods=["GET"])
def charlie_agent_workforce_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    refresh = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
    now = time.monotonic()
    if not refresh and AGENT_WORKFORCE_CACHE.get("packet") and now < float(AGENT_WORKFORCE_CACHE.get("expires_at") or 0):
        return jsonify({**AGENT_WORKFORCE_CACHE["packet"], "cache": "fresh"}), 200
    limit = request.args.get("limit", 500)
    # Every scorecard is independent. Keep the pool aligned with the number of
    # sources so the fifth source cannot sit behind a slow production read and
    # push the owner-facing Workforce request past Render's timeout.
    with ThreadPoolExecutor(max_workers=5) as pool:
        mission_future = pool.submit(mission_status_summary)
        learning_future = pool.submit(live_stock_learning_scorecard, limit=limit)
        analyst_future = pool.submit(analyst_scorecard, limit=50)
        beacon_future = pool.submit(beacon_workforce_scorecard, limit=limit)
        trust_future = pool.submit(list_capability_trust, limit=200)
        mission_summary, mission_status = mission_future.result()
        sam_learning, sam_status = learning_future.result()
        analyst_learning, analyst_status = analyst_future.result()
        beacon_learning = beacon_future.result()
        herdmaster_learning, herdmaster_status = trust_future.result()
    runner = _compact_runner_status(local_runner_status(include_orphans=False, include_git=False, include_ledger=not _running_on_render()))
    packet = build_agent_workforce_packet(
        mission_summary=mission_summary if mission_status < 400 else {},
        runner=runner,
        sam_learning=sam_learning if sam_status < 400 else {
            "success": False,
            "status": sam_learning.get("status", "scorecard_unavailable"),
            "scorecard": {},
        },
        analyst_learning=analyst_learning if analyst_status < 400 else {
            "success": False,
            "status": analyst_learning.get("status", "analyst_scorecard_unavailable"),
            "scorecard": {},
        },
        beacon_learning=beacon_learning,
        herdmaster_learning=herdmaster_learning if herdmaster_status < 400 else {"success": False, "capabilities": []},
    )
    packet["sources"] = {
        "charlie_missions": {"status_code": mission_status, "authoritative": True},
        "sam_live_stock_learning": {"status_code": sam_status, "authoritative": True},
        "charlie_improvement_analyst": {"status_code": analyst_status, "authoritative": True},
        "beacon_marketing_evidence": {"status_code": 200 if beacon_learning.get("success") else 503, "authoritative": True},
        "agent_registry": {"status_code": 200, "authoritative": True},
        "trust_ledger": {"status_code": herdmaster_status, "authoritative": True},
    }
    packet["cache"] = "refreshed"
    AGENT_WORKFORCE_CACHE.update({"expires_at": time.monotonic() + AGENT_WORKFORCE_CACHE_SECONDS, "packet": packet})
    return jsonify(packet), 200


@charlie_bp.route("/charlie/core/vault-health", methods=["GET"])
def charlie_core_vault_health_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = vault_tables_health()
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/executive", methods=["GET"])
def charlie_core_executive_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = executive_scorecard()
    result["mode"] = executive_mode()
    result["authority_boundary"] = "Only current Supabase delegation policies may authorize non-red internal commands."
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/executive/missions/<mission_id>/delivery", methods=["GET"])
def charlie_core_mission_delivery_route(mission_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = mission_outbox_delivery(mission_id, limit=request.args.get("limit", 20))
    result["authority_boundary"] = "Read-only delivery audit; it cannot resend, approve, or execute protected actions."
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/executive/cycle", methods=["POST"])
def charlie_core_executive_cycle_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = run_executive_cycle(runner={"source": "owner_manual_observation"})
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
    result, status_code = run_operational_analyst(trigger="owner_manual", limit=payload.get("limit", 50))
    return jsonify(result), status_code


@charlie_bp.route("/charlie/core/improvements/scorecard", methods=["GET"])
def charlie_core_improvements_scorecard_route():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = analyst_scorecard(limit=request.args.get("limit", 50))
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


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/external-candidate", methods=["POST"])
def charlie_external_supervisor_candidate_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "status": "external_candidate_binding_invalid"}), 400
    result, status_code = bind_external_supervisor_candidate(
        mission_id, payload, authenticated_principal="hermes:charlie-builder")
    return jsonify(result), status_code


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/protected-admission", methods=["POST"])
def charlie_protected_admission_record_route(mission_id):
    """Record only an exact receipt signed by the existing protected issuer."""
    from scripts.charlie_mission_admission_guard import _validate_external_receipt_envelope
    payload = request.get_json(silent=True) or {}
    envelope = payload.get("envelope")
    try:
        pr_number = int(payload.get("pr_number") or 0)
        if pr_number <= 0 or set(payload) != {"envelope", "pr_number"}:
            raise ValueError("protected_admission_payload_invalid")
        receipt = (envelope or {}).get("receipt") or {}
        candidate = receipt.get("candidate") or {}
        repository = receipt.get("repository") or {}
        verified, identity = _validate_external_receipt_envelope(
            envelope, expected_repository="Crewless9086/amadeus-pig-tracking-system",
            expected_base_sha=str(repository.get("base_sha") or ""),
            expected_head_sha=str(candidate.get("head_sha") or ""),
            expected_changed_files=candidate.get("changed_files") or [])
        if identity.get("mission_id") != mission_id:
            raise ValueError("mission_identity_mismatch")
        loaded, loaded_status = get_mission(mission_id)
        authority, authority_status = read_current_mission_admission_authority(mission_id)
        if loaded_status >= 400 or authority_status >= 400:
            raise ValueError("canonical_authority_unavailable")
        metadata = dict(((loaded.get("mission") or {}).get("metadata") or {}))
        packet = dict(metadata.get("review_packet") or {})
        contract = dict(metadata.get("mission_admission_contract") or {})
        family = dict(metadata.get("mission_family") or {})
        if packet and packet.get("candidate_revision") != identity["head_sha"]:
            current_admission = dict(metadata.get("mission_admission") or {})
            invalidated, invalidated_status = invalidate_external_candidate_admission(
                mission_id, str(packet.get("candidate_revision") or ""), identity["head_sha"],
                authenticated_principal="control_tower_isolated_validator_v2")
            if invalidated_status >= 400:
                raise ValueError(invalidated.get("status") or "candidate_invalidation_failed")
            packet = {}
        if not packet:
            authorization = dict(metadata.get("dispatch_authorization") or {})
            pull_request = urllib.request.Request(
                f"https://api.github.com/repos/Crewless9086/amadeus-pig-tracking-system/pulls/{pr_number}",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "CHARLIE-Canonical-Admission"})
            with urllib.request.urlopen(pull_request, timeout=15) as response:
                pull = json.loads(response.read(1048576))
            if (pull.get("state") != "open" or (pull.get("head") or {}).get("sha") != identity["head_sha"]
                    or (pull.get("head") or {}).get("ref") != candidate.get("branch")
                    or (pull.get("base") or {}).get("sha") != identity["base_sha"]
                    or authorization.get("status") != "valid"):
                raise ValueError("protected_admission_pull_identity_changed")
            binding = {"pr_number": pr_number, "branch_name": candidate["branch"],
                "base_sha": identity["base_sha"], "head_sha": identity["head_sha"],
                "candidate_diff_sha256": candidate["diff_sha256"],
                "changed_files": identity["changed_files"], "generation": identity["generation"],
                "allowed_files": identity["allowed_files"], "forbidden_files": verified["scope"]["forbidden_files"],
                "allowed_effects": identity["allowed_effects"], "forbidden_effects": identity["forbidden_effects"],
                "required_tests": verified["required_tests"],
                "operational_acceptance": verified["operational_acceptance"]["requirements"]}
            bound, bound_status = bind_external_supervisor_candidate(
                mission_id, binding, authenticated_principal="hermes:charlie-builder")
            if bound_status >= 400:
                raise ValueError(bound.get("status") or "external_candidate_binding_failed")
            loaded, loaded_status = get_mission(mission_id)
            metadata = dict(((loaded.get("mission") or {}).get("metadata") or {}))
            packet = dict(metadata.get("review_packet") or {})
            contract = dict(metadata.get("mission_admission_contract") or {})
            family = dict(metadata.get("mission_family") or {})
        if (packet.get("candidate_revision") != identity["head_sha"]
                or packet.get("candidate_diff_sha256") != candidate.get("diff_sha256")
                or sorted(packet.get("changed_files") or []) != sorted(identity["changed_files"])
                or contract.get("base_sha") != identity["base_sha"]
                or contract.get("branch") != candidate.get("branch")
                or sorted(contract.get("allowed_files") or []) != sorted(identity["allowed_files"])
                or family.get("generation") != identity["generation"]
                or authority.get("latest_correction_digest") != verified["owner_instruction_chain"]["latest_correction_digest"]
                or authority.get("collision_snapshot_sha256") != verified["collision_snapshot"]["snapshot_sha256"]):
            raise ValueError("canonical_candidate_linkage_changed")
        admission = {"receipt_id": verified["receipt_id"], "content_sha256": verified["content_sha256"],
            "mission_id": mission_id, "root_mission_id": identity["root_mission_id"],
            "generation": identity["generation"], "base_sha": identity["base_sha"],
            "head_sha": identity["head_sha"], "authority_key_sha256": verified["authority_key_sha256"],
            "latest_correction_digest": verified["owner_instruction_chain"]["latest_correction_digest"],
            "collision_snapshot_sha256": verified["collision_snapshot"]["snapshot_sha256"],
            "signed_receipt": verified}
        result, status = append_mission_admission_event(mission_id, admission,
            authenticated_principal="control_tower_isolated_validator_v2")
        return jsonify(result), status
    except Exception:
        return jsonify({"success": False, "status": "protected_admission_rejected"}), 409


@charlie_bp.route("/charlie/hermes/missions", methods=["POST"])
def charlie_hermes_mission_reconcile_route():
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    required = {"source", "source_event_id", "owner_user_id", "channel_id",
                "thread_ts", "instruction", "idempotency_key"}
    if set(payload) != required or payload.get("source") != "slack":
        return jsonify({"success": False, "status": "hermes_mission_payload_invalid"}), 400
    instruction = str(payload.get("instruction") or "").strip()
    result, status = record_mission({
        "raw_text": instruction, "title": instruction[:160], "urgency": "P2",
        "mission_type": "system improvement", "approval_level": "LEVEL 3",
        "metadata": {"mission_plane": {
            "plane": "software", "coordinator": "CHARLIE", "executor": "Cursor Cloud",
            "classification_source": "authenticated_slack_ingress",
        }, "external_supervisor_state": {
            "slack_event_id": str(payload["source_event_id"]),
            "slack_owner_user_id": str(payload["owner_user_id"]),
            "slack_channel_id": str(payload["channel_id"]),
            "slack_thread_ts": str(payload["thread_ts"]),
        }},
    }, source_context={"source": "slack", "source_message_id": str(payload["source_event_id"]),
                       "telegram_user_id": str(payload["owner_user_id"]),
                       "telegram_chat_id": str(payload["channel_id"])})
    mission_id = result.get("mission_id")
    return jsonify({"success": status < 400, **result, "mission_id": mission_id}), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>", methods=["GET"])
def charlie_hermes_mission_status_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    result, status = get_mission(mission_id)
    return jsonify(result), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/progress", methods=["POST"])
def charlie_hermes_mission_progress_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    result, status = record_external_supervisor_state(
        mission_id, request.get_json(silent=True) or {},
        authenticated_principal="hermes:charlie-builder")
    return jsonify(result), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/dispatch-authorization", methods=["POST"])
def charlie_hermes_dispatch_authorization_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    if (request.get_json(silent=True) or {}) != {}:
        return jsonify({"success": False, "status": "dispatch_authorization_input_forbidden"}), 400
    base_sha = str(env_value("RENDER_GIT_COMMIT") or "")
    result, status = prepare_external_dispatch_authorization(
        mission_id,
        authenticated_principal="hermes:charlie-builder",
        repository="Crewless9086/amadeus-pig-tracking-system",
        base_sha=base_sha,
        owner_user_id=str(env_value("CHARLIE_SLACK_OWNER_USER_ID") or ""),
        channel_id=str(env_value("CHARLIE_SLACK_CHARLIE_CHANNEL_ID") or ""),
    )
    return jsonify(result), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/execution-succession", methods=["POST"])
def charlie_hermes_execution_succession_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    required = {"generation", "predecessor_agent_id", "predecessor_run_id",
                "predecessor_state", "replacement_reason"}
    if set(payload) != required:
        return jsonify({"success": False, "status": "execution_succession_invalid"}), 400
    result, status = prepare_external_execution_succession(
        mission_id, **payload, observed_main_sha=str(env_value("RENDER_GIT_COMMIT") or ""),
        authenticated_principal="hermes:charlie-builder")
    return jsonify(result), status


@charlie_bp.route("/charlie/cursor/hooks/authorize", methods=["POST"])
def charlie_cursor_hook_authorize_route():
    """Authorize one managed Cursor hook operation from signed runtime identity."""
    header = str(request.headers.get("Authorization") or "")
    if not header.startswith("Bearer "):
        return jsonify({"success": False, "permission": "deny", "status": "cursor_oidc_required"}), 401
    try:
        claims = verify_cursor_oidc_token(header[7:].strip())
    except CursorIdentityError as exc:
        return jsonify({"success": False, "permission": "deny", "status": str(exc)}), 401
    payload = request.get_json(silent=True) or {}
    allowed = {"action", "target_path", "command", "changed_files"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        return jsonify({"success": False, "permission": "deny", "status": "cursor_hook_request_invalid"}), 400
    result, status = authorize_cursor_workspace_hook(
        cloud_agent_id=claims["cloud_agent_id"], branch_name=str(claims.get("branch_name") or ""),
        repository=APPROVED_REPOSITORY, action=str(payload.get("action") or ""),
        target_path=str(payload.get("target_path") or ""), command=str(payload.get("command") or ""),
        changed_files=payload.get("changed_files") if isinstance(payload.get("changed_files"), list) else [],
    )
    bounded = {key: result.get(key) for key in
               ("success", "permission", "status", "authorization_id", "branch", "allowed_path", "command")
               if result.get(key) is not None}
    if status >= 400:
        bounded["permission"] = "deny"
    return jsonify(bounded), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/actual-branch", methods=["POST"])
def charlie_hermes_actual_branch_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    if set(payload) != {"generation", "cursor_agent_id", "cursor_run_id", "repository", "branches"}:
        return jsonify({"success": False, "status": "external_branch_binding_invalid"}), 400
    result, status = bind_external_supervisor_branch(
        mission_id, **payload, authenticated_principal="hermes:charlie-builder")
    return jsonify(result), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/refresh-dispatch-base", methods=["POST"])
def charlie_hermes_refresh_dispatch_base_route(mission_id):
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    required = {"generation", "cursor_agent_id", "old_base_sha"}
    if set(payload) != required:
        return jsonify({"success": False, "status": "dispatch_base_refresh_invalid"}), 400
    new_base = str(env_value("RENDER_GIT_COMMIT") or "")
    old_base = str(payload.get("old_base_sha") or "")
    try:
        compare_request = urllib.request.Request(
            f"https://api.github.com/repos/Crewless9086/amadeus-pig-tracking-system/compare/{old_base}...{new_base}",
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(compare_request, timeout=15) as response:
            comparison = json.loads(response.read().decode("utf-8"))
        if comparison.get("status") not in {"ahead", "identical"}:
            raise ValueError("base_not_ancestor")
        changed_files = [str(item.get("filename") or "") for item in comparison.get("files") or []]
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return jsonify({"success": False, "status": "dispatch_base_comparison_unavailable"}), 503
    if old_base == new_base:
        return jsonify({"success": True, "status": "base_current"}), 200
    result, status = refresh_external_dispatch_authorization_base(
        mission_id, generation=payload["generation"], cursor_agent_id=payload["cursor_agent_id"],
        old_base_sha=old_base, new_base_sha=new_base, changed_files=changed_files,
        authenticated_principal="hermes:charlie-builder")
    return jsonify(result), status


@charlie_bp.route("/charlie/hermes/missions/<mission_id>/admission", methods=["POST"])
def charlie_hermes_mission_admission_route(mission_id):
    """Trigger only the protected-main issuer for the canonical bound candidate."""
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    supplied = request.get_json(silent=True) or {}
    if (set(supplied) != {"expected_head_sha", "pr_number"}
            or not re.fullmatch(r"[0-9a-f]{40}", str(supplied.get("expected_head_sha") or ""))
            or not isinstance(supplied.get("pr_number"), int) or supplied["pr_number"] <= 0):
        return jsonify({"success": False, "status": "issuer_request_invalid"}), 400
    loaded, status = get_mission(mission_id)
    if status >= 400:
        return jsonify(loaded), status
    metadata = dict(((loaded.get("mission") or {}).get("metadata") or {}))
    packet = dict(metadata.get("review_packet") or {})
    expected_head = str(supplied["expected_head_sha"])
    authorization = dict(metadata.get("dispatch_authorization") or {})
    if packet.get("candidate_revision") == expected_head and int(packet.get("pr_number") or 0):
        pr_number = int(packet["pr_number"])
    elif authorization.get("status") == "valid":
        pr_number = supplied["pr_number"]
    else:
        return jsonify({"success": False, "status": "canonical_candidate_not_bound"}), 409
    token = str(env_value("CHARLIE_ADMISSION_ISSUER_GITHUB_TOKEN") or "").strip()
    if len(token) < 32:
        return jsonify({"success": False, "status": "protected_issuer_unavailable"}), 503
    body = json.dumps({"ref": "main", "inputs": {
        "pull_request_number": str(pr_number), "expected_head_sha": expected_head,
    }}, separators=(",", ":")).encode()
    issuer_request = urllib.request.Request(
        "https://api.github.com/repos/Crewless9086/amadeus-pig-tracking-system/actions/workflows/mission-admission-issuer.yml/dispatches",
        data=body, method="POST", headers={"Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json", "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(issuer_request, timeout=15) as response:
            if response.status != 204:
                raise OSError("unexpected_status")
    except (urllib.error.URLError, OSError):
        return jsonify({"success": False, "status": "protected_issuer_unavailable"}), 503
    return jsonify({"success": True, "status": "protected_issuer_dispatched",
                    "mission_id": mission_id, "pr_number": pr_number,
                    "expected_head_sha": expected_head}), 202


@charlie_bp.route("/charlie/hermes/dispatch", methods=["GET", "POST"])
def charlie_hermes_dispatch_route():
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    if request.method == "GET":
        result, status = read_external_supervisor_state(request.args.get("idempotency_key", ""))
        return jsonify(result), status
    payload = request.get_json(silent=True) or {}
    mission_id = str(payload.get("mission_id") or "")
    state = {key: value for key, value in payload.items() if key != "mission_id"}
    result, status = record_external_supervisor_state(
        mission_id, state, authenticated_principal="hermes:charlie-builder")
    return jsonify(result), status


@charlie_bp.route("/charlie/hermes/writers", methods=["GET"])
def charlie_hermes_writer_count_route():
    denied = _require_hermes_gateway_access()
    if denied:
        return denied
    missions, status = list_missions(status="in_progress", limit=100, compact=False)
    running = sum(1 for row in missions.get("missions") or []
                  if ((row.get("metadata") or {}).get("external_supervisor_state") or {}).get("agent_state") == "ACTIVE")
    return jsonify({"success": status < 400, "running": running}), status


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/outcome-handover", methods=["POST"])
def charlie_build_relay_mission_outcome_handover_route(mission_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_mission_outcome_handover(
        mission_id, payload, authenticated_principal=strict_owner_admin_principal())
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/outcome-evidence", methods=["POST"])
def charlie_build_relay_mission_outcome_evidence_route(mission_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_mission_outcome_evidence(
        mission_id, str(payload.get("evidence_row") or ""),
        payload.get("evidence_payload") if isinstance(payload.get("evidence_payload"), dict) else {},
        evidence_id=str(payload.get("evidence_id") or ""),
        authenticated_principal=strict_owner_admin_principal(),
        producer_actor_type="external_verifier",
    )
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
    compact = str(request.args.get("compact") or "").strip().lower() in {"1", "true", "yes"}
    result, status_code = get_mission_review_packet(mission_id)
    if isinstance(result, dict) and isinstance(result.get("review_packet"), dict):
        result = dict(result)
        result["review_packet"] = _normalize_review_packet_media(result["review_packet"], mission_id)
        if compact:
            result["review_packet"] = _compact_owner_review_packet(result["review_packet"], mission_id=mission_id)
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
    requests = list(status_limits or [])
    if not requests:
        return buckets, [200]
    with ThreadPoolExecutor(max_workers=min(len(requests), 6)) as pool:
        futures = [pool.submit(_dashboard_owner_work_status_queue, status, limit=limit) for status, limit in requests]
        results = [future.result() for future in futures]
    for (status, _limit), (result, status_code) in zip(requests, results):
        statuses.append(status_code)
        if status_code < 400:
            buckets[status] = result.get("missions", [])
    return buckets, statuses


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
    final_readiness = evaluate_final_readiness(mission)
    review_packet = {**review_packet, "final_readiness": final_readiness}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    owner_action_guidance = _owner_action_guidance(mission, review_packet, workflow)
    stage_telemetry = _stage_telemetry(metadata, workflow)
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
            "block_disposition",
            "runner_recovery",
            "runner_recovery_history",
            "repo_test_command_memory",
            "final_readiness",
            "outcome_closure",
            "unfinished_business",
            "candidate_manifest",
            "evidence_reconciliation",
            "active_blockers",
            "resolved_findings",
            "follow_up_findings",
            "evidence_requiring_refresh",
            "recommended_action",
        )
        if key in review_packet
    }
    compact_review_packet = _compact_review_packet(compact_review_packet, mission_id=mission_id)
    compact_metadata = {}
    if compact_review_packet:
        compact_metadata["review_packet"] = compact_review_packet
    compact_metadata["mission_governance"] = mission_governance_summary(mission)
    compact_metadata["owner_action_guidance"] = owner_action_guidance
    compact_metadata["stage_telemetry"] = stage_telemetry
    mission_family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    if mission_family:
        compact_metadata["mission_family"] = mission_family
    supersession = metadata.get("supersession") if isinstance(metadata.get("supersession"), dict) else {}
    if supersession:
        compact_metadata["supersession"] = supersession
    dependencies = metadata.get("depends_on_mission_ids") if isinstance(metadata.get("depends_on_mission_ids"), list) else []
    if dependencies:
        compact_metadata["depends_on_mission_ids"] = dependencies
    coordinator = metadata.get("mission_coordinator") if isinstance(metadata.get("mission_coordinator"), dict) else {}
    if coordinator:
        compact_metadata["mission_coordinator"] = coordinator
    mission_memory = mission_memory_from_metadata(metadata)
    if mission_memory.get("events") or mission_memory.get("updated_at"):
        events = [item for item in mission_memory.get("events", []) if isinstance(item, dict)]
        attempts = [item for item in mission_memory.get("attempts", []) if isinstance(item, dict)]
        recovery_notes = [item for item in mission_memory.get("recovery_notes", []) if isinstance(item, dict)]
        patterns = [item for item in mission_memory.get("recurring_block_patterns", {}).values() if isinstance(item, dict)]
        sessions = {
            str((item.get("metadata") or {}).get("execution_id") or "").strip()
            for item in events
            if isinstance(item.get("metadata"), dict) and str((item.get("metadata") or {}).get("execution_id") or "").strip()
        }
        last_recovery = recovery_notes[-1] if recovery_notes else {}
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
            "telemetry": {
                "attempt_count": len(attempts),
                "execution_session_count": len(sessions),
                "recovery_count": len(recovery_notes),
                "backflow_count": sum(1 for item in events if str(item.get("type") or "").lower() == "agent_backflow"),
                "repeated_blocker_count": sum(1 for item in patterns if int(item.get("count") or 0) >= 2),
                "highest_blocker_repeat": max([int(item.get("count") or 0) for item in patterns] or [0]),
                "last_progress_at": mission_memory.get("updated_at", ""),
                "last_restart_reason": _short_text(last_recovery.get("summary") or last_recovery.get("reason"), 240),
            },
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
    status = str(mission.get("status") or "").strip().lower()
    owner_decision = str(mission.get("owner_decision") or "").strip()
    resolution = ""
    if status in {"done", "merged", "deployed"}:
        resolution = "resolved_duplicate_or_external" if any(word in owner_decision.lower() for word in ("duplicate", "already merged", "resolved externally")) else "completed"
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
        "terminal_resolution": resolution,
        "created_at": mission.get("created_at", ""),
        "updated_at": mission.get("updated_at", ""),
        "queue_class": mission.get("queue_class", "owner_work"),
        "queue_priority": mission.get("queue_priority"),
        "owner_projection": mission.get("owner_projection", {}),
        "vault": compact_vault,
        "agent_workflow": _compact_workflow(mission.get("agent_workflow", [])),
        "metadata": compact_metadata,
    }


def _stage_telemetry(metadata, workflow):
    metadata = metadata if isinstance(metadata, dict) else {}
    execution = metadata.get("agent_execution") if isinstance(metadata.get("agent_execution"), dict) else {}
    stages = [item for item in execution.get("stages", []) if isinstance(item, dict)]
    memory = mission_memory_from_metadata(metadata)
    attempts = [item for item in memory.get("attempts", []) if isinstance(item, dict)]
    attempt_counts = {}
    for item in attempts:
        agent = str(item.get("agent") or "").strip().lower()
        if agent:
            attempt_counts[agent] = max(attempt_counts.get(agent, 0), int(item.get("attempt") or 1))
    latest = {}
    for item in stages:
        agent = str(item.get("agent") or "").strip().lower()
        if not agent:
            continue
        attempt = int(item.get("attempt") or 1)
        attempt_counts[agent] = max(attempt_counts.get(agent, 0), attempt)
        previous = latest.get(agent)
        if previous is None or attempt >= int(previous.get("attempt") or 1):
            latest[agent] = item
    rows = []
    for workflow_item in workflow:
        workflow_item = workflow_item if isinstance(workflow_item, dict) else {}
        agent = str(workflow_item.get("agent") or "").strip().lower()
        if not agent:
            continue
        stage = latest.get(agent, {})
        changed_files = stage.get("changed_files") if isinstance(stage.get("changed_files"), list) else []
        rows.append({
            "agent": agent,
            "status": str(workflow_item.get("status") or stage.get("status") or "pending"),
            "attempt": max(attempt_counts.get(agent, 0), int(stage.get("attempt") or 0)),
            "started_at": stage.get("started_at", ""),
            "updated_at": stage.get("updated_at", ""),
            "completed_at": stage.get("completed_at", ""),
            "duration_seconds": stage.get("duration_seconds"),
            "changed_files_count": int(stage.get("changed_files_count") or len(changed_files)),
            "current_action": _short_text(stage.get("current_action", ""), 180),
        })
    return {
        "execution_id": execution.get("execution_id", ""),
        "started_at": execution.get("started_at", ""),
        "last_progress_at": execution.get("last_progress_at") or memory.get("updated_at", ""),
        "stages": rows,
    }


def _owner_action_guidance(mission, review_packet, workflow):
    status = str(mission.get("status") or "").strip().lower()
    review_packet = review_packet if isinstance(review_packet, dict) else {}
    workflow_agents = [str(item.get("agent") or "").strip().lower() for item in workflow if isinstance(item, dict)]
    recommendation = str(review_packet.get("recommended_next_action") or "").strip()
    reconciled_action = review_packet.get("recommended_action") if isinstance(review_packet.get("recommended_action"), dict) else {}
    if not recommendation and reconciled_action:
        recommendation = str(reconciled_action.get("reason") or "").strip()
    target = str(review_packet.get("return_to_stage") or "").strip().lower()
    if not target and reconciled_action.get("target_agent") not in {None, "", "owner"}:
        target = str(reconciled_action.get("target_agent") or "").strip().lower()
    disposition = review_packet.get("block_disposition") if isinstance(review_packet.get("block_disposition"), dict) else {}
    if not target and disposition.get("responsible_stage") not in {None, "", "owner"}:
        target = str(disposition.get("responsible_stage") or "").strip().lower()
    if not target and recommendation:
        match = re.search(r"\breturn to\s+([a-z_ -]+?)(?:[.;]|\s+and\b)", recommendation.lower())
        if match:
            target = "_".join(match.group(1).strip().split())
    if status == "blocked":
        missing_target = bool(target) and target not in workflow_agents
        if missing_target:
            return {
                "recommended_action": "approve_rerun",
                "button_label": "Approve Rerun",
                "target_stage": target,
                "reason": f"The required {target.replace('_', ' ').title()} stage is missing from the stored workflow. CORE must refresh routing before retrying.",
                "what_happens": "Completed evidence is preserved, the workflow is refreshed at pickup, and the mission waits behind the currently active mission.",
                "alternative_action": "send_back",
            }
        if target:
            return {
                "recommended_action": "send_back",
                "button_label": f"Send Back to {target.replace('_', ' ').title()}",
                "target_stage": target,
                "reason": recommendation or f"The blocking evidence identifies {target.replace('_', ' ')} as the responsible correction stage.",
                "what_happens": "CORE preserves completed upstream evidence and resumes from the selected correction stage.",
                "alternative_action": "approve_rerun",
            }
        return {
            "recommended_action": "approve_rerun",
            "button_label": "Approve Rerun",
            "target_stage": "",
            "reason": recommendation or "CORE recorded a recoverable block but no reliable send-back target.",
            "what_happens": "CORE recalculates routing at pickup and preserves durable evidence.",
            "alternative_action": "send_back",
        }
    return {"recommended_action": "", "button_label": "", "target_stage": "", "reason": "", "what_happens": "", "alternative_action": ""}


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


def _compact_owner_review_packet(packet, mission_id=""):
    packet = packet if isinstance(packet, dict) else {}
    compact = {
        "mission": packet.get("mission") if isinstance(packet.get("mission"), dict) else {},
        "summary": _short_text(packet.get("summary"), 1600),
        "findings": [_short_text(item, 500) for item in _as_list(packet.get("findings"))[:6]],
        "errors": [_short_text(item, 500) for item in _as_list(packet.get("errors"))[:6]],
        "bugs": [_short_text(item, 500) for item in _as_list(packet.get("bugs"))[:6]],
        "changed_files": [_short_text(item, 240) for item in _as_list(packet.get("changed_files"))[:20]],
        "test_evidence": [_short_text(item, 500) for item in _as_list(packet.get("test_evidence"))[:8]],
        "release_notes": [_short_text(item, 500) for item in _as_list(packet.get("release_notes"))[:8]],
        "links": packet.get("links") if isinstance(packet.get("links"), dict) else {},
        "local_preview": packet.get("local_preview") if isinstance(packet.get("local_preview"), dict) else {},
        "visual_review": _compact_visual_review(packet.get("visual_review"), mission_id=mission_id),
        "blocked_agent": _short_text(packet.get("blocked_agent"), 100),
        "blocked_reason": _short_text(packet.get("blocked_reason"), 800),
        "unresolved_blockers": _compact_event_list(packet.get("unresolved_blockers"), limit=6),
        "recommended_next_action": _short_text(packet.get("recommended_next_action"), 800),
        "candidate_manifest": packet.get("candidate_manifest") if isinstance(packet.get("candidate_manifest"), dict) else {},
        "active_blockers": _compact_event_list(packet.get("active_blockers"), limit=8),
        "resolved_findings": _compact_event_list(packet.get("resolved_findings"), limit=8),
        "follow_up_findings": _compact_event_list(packet.get("follow_up_findings"), limit=8),
        "evidence_requiring_refresh": _compact_event_list(packet.get("evidence_requiring_refresh"), limit=8),
        "recommended_action": packet.get("recommended_action") if isinstance(packet.get("recommended_action"), dict) else {},
        "final_readiness": packet.get("final_readiness") if isinstance(packet.get("final_readiness"), dict) else {},
        "can_approve_final_release": packet.get("can_approve_final_release") is True,
        "can_send_back": packet.get("can_send_back") is True,
        "allowed_decisions": packet.get("allowed_decisions") if isinstance(packet.get("allowed_decisions"), list) else [],
    }
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
            "operating_state",
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
            "supervisor_active",
            "supervisor_owns_runner",
            "supervisor_status",
            "supervisor_pid",
            "supervisor_child_pid",
            "supervisor_generation",
            "owner_process_pid",
            "supervisor_restart_count",
            "supervisor_identical_failure_count",
            "supervisor_latest_failure",
            "supervisor_recommended_action",
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


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/execution-hold", methods=["POST"])
def charlie_build_relay_mission_execution_hold_route(mission_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    owner_principal = strict_owner_admin_principal()
    if not owner_principal or owner_principal == "owner-admin:local-development":
        return jsonify({"success": False, "status": "owner_admin_session_required"}), 403
    if (
        not request.is_json
        or request.headers.get("X-CHARLIE-Owner-Action") != "owner_execution_hold"
    ):
        return jsonify({"success": False, "status": "owner_action_intent_required"}), 403
    payload = request.get_json(silent=True) or {}
    result, status_code = create_owner_execution_hold(
        mission_id,
        str(payload.get("generation_identity") or "").strip(),
        str(payload.get("reason") or "").strip(),
        owner_principal=owner_principal,
    )
    return jsonify(result), status_code


@charlie_bp.route("/charlie/build-relay/missions/<mission_id>/execution-hold/release", methods=["POST"])
def charlie_build_relay_mission_execution_hold_release_route(mission_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    owner_principal = strict_owner_admin_principal()
    if not owner_principal or owner_principal == "owner-admin:local-development":
        return jsonify({"success": False, "status": "owner_admin_session_required"}), 403
    if (
        not request.is_json
        or request.headers.get("X-CHARLIE-Owner-Action") != "owner_execution_hold_release"
    ):
        return jsonify({"success": False, "status": "owner_action_intent_required"}), 403
    payload = request.get_json(silent=True) or {}
    result, status_code = release_owner_execution_hold(
        mission_id,
        str(payload.get("generation_identity") or "").strip(),
        str(payload.get("hold_id") or "").strip(),
        str(payload.get("reason") or "").strip(),
        owner_principal=owner_principal,
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
