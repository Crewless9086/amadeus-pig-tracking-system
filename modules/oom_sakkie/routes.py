from flask import Blueprint, jsonify, request

from modules.oom_sakkie.access import (
    is_message_request_allowed,
    is_review_request_allowed,
    message_access_denied_response,
    review_access_denied_response,
)
from modules.oom_sakkie.agent_runtime import (
    get_agent_activation_plan,
    get_agent_activation_preflight,
    get_agent_authority_matrix,
    get_agent_authority_unlock_readiness,
    get_agent_dispatch_decision_rail_blueprint,
    get_agent_operating_contracts,
    get_agent_runtime_review_packet,
    get_agent_runtime_status,
    recommend_agent_for_text,
    get_learning_influence_consumption_readiness,
)
from modules.oom_sakkie.agent_dry_run_handoff import build_agent_dry_run_handoff
from modules.oom_sakkie.agent_dry_run_store import (
    get_agent_dry_run_request,
    list_agent_dry_run_requests,
    record_agent_dry_run_event,
    record_agent_dry_run_request,
)
from modules.oom_sakkie.agent_dry_run_result_store import (
    get_agent_dry_run_result,
    list_agent_dry_run_results,
    record_agent_dry_run_result,
    record_agent_dry_run_result_event,
)
from modules.oom_sakkie.agent_dry_run_result_review import build_agent_dry_run_result_review_packet
from modules.oom_sakkie.build_request_store import (
    get_build_request,
    list_build_requests,
    record_build_request,
    record_build_request_event,
)
from modules.oom_sakkie.deploy_decision_store import (
    list_deploy_decisions,
    record_deploy_decision,
)
from modules.oom_sakkie.dispatch_decision_store import (
    list_dispatch_requests,
    record_dispatch_decision,
    record_dispatch_request,
)
from modules.oom_sakkie.dispatch_execution_approval_store import (
    list_dispatch_execution_approvals,
    record_dispatch_execution_approval,
    record_dispatch_execution_approval_event,
)
from modules.oom_sakkie.forge_handoff import build_forge_handoff
from modules.oom_sakkie.learning_advisor import get_learning_advisor, run_learning_analysis
from modules.oom_sakkie.learning_packet import (
    approve_build_request,
    build_learning_packet,
    get_implementation_queue,
)
from modules.oom_sakkie.learning_influence_store import (
    list_learning_influence_proposals,
    record_learning_influence_proposal_event,
    record_learning_influence_proposal_from_result,
    record_learning_influence_proposals_from_accepted,
)
from modules.oom_sakkie.patch_proposal_store import (
    list_patch_proposals,
    record_patch_proposal,
    record_patch_proposal_event,
)
from modules.oom_sakkie.policy import get_runtime_policy
from modules.oom_sakkie.review_advisor import get_review_advisor
from modules.oom_sakkie.service import handle_message
from modules.oom_sakkie.sentinel_single_shot_runner import run_sentinel_single_shot_dry_run
from modules.oom_sakkie.specialists import list_specialist_manifests
from modules.oom_sakkie.tools import accepted_agent_learning_snapshot, list_tool_catalog
from modules.oom_sakkie.trace_store import (
    get_trace_review_summary,
    list_recent_traces,
    record_trace_feedback,
)


oom_sakkie_bp = Blueprint("oom_sakkie", __name__)


def _require_review_access():
    if is_review_request_allowed(request.remote_addr):
        return None
    body, status_code = review_access_denied_response(request.remote_addr)
    return jsonify(body), status_code


@oom_sakkie_bp.route("/oom-sakkie/message", methods=["POST"])
def oom_sakkie_message():
    if not is_message_request_allowed(request.remote_addr):
        body, status_code = message_access_denied_response(request.remote_addr)
        return jsonify(body), status_code
    payload = request.get_json(silent=True) or {}
    result, status_code = handle_message(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/tools", methods=["GET"])
def oom_sakkie_tools():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "tools": list_tool_catalog(),
        "policy": {
            "channel": "kiosk",
            "max_risk_level": 0,
            "write_tools_enabled": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/policy", methods=["GET"])
def oom_sakkie_policy():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify(get_runtime_policy()), 200


@oom_sakkie_bp.route("/oom-sakkie/specialists", methods=["GET"])
def oom_sakkie_specialists():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "status": "planned_only",
        "delegation_enabled": False,
        "autonomous_loops_enabled": False,
        "specialists": list_specialist_manifests(),
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents", methods=["GET"])
def oom_sakkie_agents():
    denied = _require_review_access()
    if denied:
        return denied
    return jsonify(get_agent_runtime_status()), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/contracts", methods=["GET"])
def oom_sakkie_agent_contracts():
    denied = _require_review_access()
    if denied:
        return denied
    contracts = get_agent_operating_contracts()
    return jsonify({
        **contracts,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/preflight", methods=["GET"])
def oom_sakkie_agent_preflight():
    denied = _require_review_access()
    if denied:
        return denied
    preflight = get_agent_activation_preflight()
    return jsonify({
        **preflight,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/authority-matrix", methods=["GET"])
def oom_sakkie_agent_authority_matrix():
    denied = _require_review_access()
    if denied:
        return denied
    matrix = get_agent_authority_matrix()
    return jsonify({
        **matrix,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/unlock-readiness", methods=["GET"])
def oom_sakkie_agent_unlock_readiness():
    denied = _require_review_access()
    if denied:
        return denied
    readiness = get_agent_authority_unlock_readiness()
    return jsonify({
        **readiness,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/dispatch-rail-blueprint", methods=["GET"])
def oom_sakkie_agent_dispatch_rail_blueprint():
    denied = _require_review_access()
    if denied:
        return denied
    blueprint = get_agent_dispatch_decision_rail_blueprint()
    return jsonify({
        **blueprint,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/runtime-review-packet", methods=["GET"])
def oom_sakkie_agent_runtime_review_packet():
    denied = _require_review_access()
    if denied:
        return denied
    packet = get_agent_runtime_review_packet()
    return jsonify({
        **packet,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/recommend", methods=["POST"])
def oom_sakkie_agent_recommend():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    return jsonify(recommend_agent_for_text(payload.get("text") or "")), 200


@oom_sakkie_bp.route("/oom-sakkie/agents/activation-plan", methods=["GET"])
def oom_sakkie_agent_activation_plan():
    denied = _require_review_access()
    if denied:
        return denied
    learning = accepted_agent_learning_snapshot(limit=request.args.get("limit", 20))
    return jsonify({
        "success": learning["status_code"] == 200,
        "mode": "agent_activation_plan_panel",
        "activation_plan": get_agent_activation_plan(),
        "accepted_learning": learning["evidence"],
        "accepted_learning_count": learning["accepted_count"],
        "accepted_by_specialist": learning.get("accepted_by_specialist", {}),
        "accepted_learning_status": learning["status"],
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200 if learning["status_code"] == 200 else 503


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs", methods=["GET"])
def oom_sakkie_agent_dry_runs():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_agent_dry_run_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs", methods=["POST"])
def oom_sakkie_agent_dry_run_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_request(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs/<dry_run_request_id>/events", methods=["POST"])
def oom_sakkie_agent_dry_run_events(dry_run_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_event(dry_run_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs/handoff", methods=["POST"])
def oom_sakkie_agent_dry_run_handoff():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    dry_run_request_id = str(payload.get("dry_run_request_id") or "").strip()
    loaded, load_status = get_agent_dry_run_request(dry_run_request_id)
    if load_status != 200:
        return jsonify(loaded), load_status
    dry_run_request = loaded.get("dry_run_request", {})
    result, status_code = build_agent_dry_run_handoff(dry_run_request)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-runs/<dry_run_request_id>/results", methods=["POST"])
def oom_sakkie_agent_dry_run_result_create(dry_run_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_result(dry_run_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-run-results", methods=["GET"])
def oom_sakkie_agent_dry_run_results():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_agent_dry_run_results(
        dry_run_request_id=request.args.get("dry_run_request_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-run-results/<dry_run_result_id>/events", methods=["POST"])
def oom_sakkie_agent_dry_run_result_events(dry_run_result_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_agent_dry_run_result_event(dry_run_result_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-dry-run-results/<dry_run_result_id>/review-packet", methods=["GET"])
def oom_sakkie_agent_dry_run_result_review_packet(dry_run_result_id):
    denied = _require_review_access()
    if denied:
        return denied
    loaded, load_status = get_agent_dry_run_result(dry_run_result_id)
    if load_status != 200:
        return jsonify(loaded), load_status
    dry_run_result = loaded.get("dry_run_result", {})
    result, status_code = build_agent_dry_run_result_review_packet(dry_run_result)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals", methods=["GET"])
def oom_sakkie_learning_influence_proposals():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_learning_influence_proposals(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals/from-accepted", methods=["POST"])
def oom_sakkie_learning_influence_proposals_from_accepted():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_proposals_from_accepted(limit=payload.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals/from-result", methods=["POST"])
def oom_sakkie_learning_influence_proposal_from_result():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_proposal_from_result(payload.get("source_result_id", ""))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/influence-proposals/<proposal_id>/events", methods=["POST"])
def oom_sakkie_learning_influence_proposal_events(proposal_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_learning_influence_proposal_event(proposal_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/agent-learning/consumption-readiness", methods=["GET"])
def oom_sakkie_learning_influence_consumption_readiness():
    denied = _require_review_access()
    if denied:
        return denied
    readiness = get_learning_influence_consumption_readiness()
    return jsonify({
        **readiness,
        "review_guard": {
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
    }), 200


@oom_sakkie_bp.route("/oom-sakkie/review-packet", methods=["GET"])
def oom_sakkie_review_packet():
    denied = _require_review_access()
    if denied:
        return denied
    review_summary, review_status = get_trace_review_summary(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
    )
    recent_traces, traces_status = list_recent_traces(
        limit=request.args.get("limit", 12),
        channel=request.args.get("channel", "kiosk").strip(),
        review=request.args.get("review", "all").strip(),
        search=request.args.get("q", "").strip(),
    )
    return jsonify({
        "success": review_status == 200 and traces_status == 200,
        "policy": get_runtime_policy(),
        "tools": list_tool_catalog(),
        "specialists": list_specialist_manifests(),
        "agent_runtime": get_agent_runtime_status(),
        "review_summary": review_summary,
        "recent_traces": recent_traces,
        "statuses": {
            "review_summary": review_status,
            "recent_traces": traces_status,
        },
    }), max(review_status, traces_status)


@oom_sakkie_bp.route("/oom-sakkie/review-advisor", methods=["GET"])
def oom_sakkie_review_advisor():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_review_advisor(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
        limit=request.args.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor", methods=["GET"])
def oom_sakkie_learning_advisor():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_learning_advisor(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
        limit=request.args.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/analyze", methods=["POST"])
def oom_sakkie_learning_advisor_analyze():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = run_learning_analysis(
        channel=str(payload.get("channel") or "kiosk").strip(),
        days=payload.get("days", 14),
        limit=payload.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/build-packet", methods=["POST"])
def oom_sakkie_learning_advisor_build_packet():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    proposal = payload.get("proposal") if isinstance(payload, dict) else {}
    result, status_code = build_learning_packet(proposal)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/implementation-queue", methods=["GET"])
def oom_sakkie_learning_advisor_implementation_queue():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_implementation_queue(
        channel=request.args.get("channel", "kiosk").strip(),
        days=request.args.get("days", 14),
        limit=request.args.get("limit", 12),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/learning-advisor/approve-build", methods=["POST"])
def oom_sakkie_learning_advisor_approve_build():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    packet = payload.get("packet") if isinstance(payload, dict) else {}
    result, status_code = approve_build_request(
        packet,
        approved_by=str(payload.get("approved_by") or "owner").strip()[:80],
    )
    if status_code == 200:
        store_result, store_status = record_build_request(result)
        result["build_request_store"] = store_result
        if store_status < 500 and store_result.get("stored"):
            event_result, _event_status = record_build_request_event(
                result.get("build_request_id", ""),
                {
                    "event_type": "approved",
                    "notes": "Approved from Oom Sakkie kiosk.",
                    "recorded_by": result.get("approved_by", "owner"),
                },
            )
            result["build_request_event"] = event_result
        if store_status >= 500:
            status_code = store_status
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests", methods=["GET"])
def oom_sakkie_build_requests():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_build_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests/<build_request_id>/events", methods=["POST"])
def oom_sakkie_build_request_events(build_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_build_request_event(build_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests/forge-handoff", methods=["POST"])
def oom_sakkie_build_request_forge_handoff():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    build_request_id = str(payload.get("build_request_id") or "").strip()
    loaded, load_status = get_build_request(build_request_id)
    if load_status != 200:
        return jsonify(loaded), load_status
    build_request = loaded.get("build_request", {})
    result, status_code = build_forge_handoff(build_request)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/build-requests/<build_request_id>/patch-proposals", methods=["POST"])
def oom_sakkie_patch_proposal_create(build_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_patch_proposal(build_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/patch-proposals", methods=["GET"])
def oom_sakkie_patch_proposals():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_patch_proposals(
        build_request_id=request.args.get("build_request_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/patch-proposals/<patch_proposal_id>/events", methods=["POST"])
def oom_sakkie_patch_proposal_events(patch_proposal_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_patch_proposal_event(patch_proposal_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/patch-proposals/<patch_proposal_id>/deploy-decisions", methods=["POST"])
def oom_sakkie_deploy_decision_create(patch_proposal_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_deploy_decision(patch_proposal_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/deploy-decisions", methods=["GET"])
def oom_sakkie_deploy_decisions():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_deploy_decisions(
        patch_proposal_id=request.args.get("patch_proposal_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests", methods=["GET"])
def oom_sakkie_dispatch_requests():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_dispatch_requests(limit=request.args.get("limit", 20))
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests", methods=["POST"])
def oom_sakkie_dispatch_request_create():
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_request(payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests/<dispatch_request_id>/decisions", methods=["POST"])
def oom_sakkie_dispatch_decision_create(dispatch_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_decision(dispatch_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-requests/<dispatch_request_id>/execution-approvals", methods=["POST"])
def oom_sakkie_dispatch_execution_approval_create(dispatch_request_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_execution_approval(dispatch_request_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-execution-approvals", methods=["GET"])
def oom_sakkie_dispatch_execution_approvals():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_dispatch_execution_approvals(
        dispatch_request_id=request.args.get("dispatch_request_id", "").strip(),
        limit=request.args.get("limit", 20),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-execution-approvals/<approval_id>/events", methods=["POST"])
def oom_sakkie_dispatch_execution_approval_events(approval_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_dispatch_execution_approval_event(approval_id, payload)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/dispatch-execution-approvals/<approval_id>/run-sentinel-dry-run", methods=["POST"])
def oom_sakkie_sentinel_single_shot_dry_run(approval_id):
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = run_sentinel_single_shot_dry_run(approval_id)
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/traces", methods=["GET"])
def oom_sakkie_traces():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = list_recent_traces(
        limit=request.args.get("limit", 20),
        channel=request.args.get("channel", "").strip(),
        review=request.args.get("review", "all").strip(),
        search=request.args.get("q", "").strip(),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/traces/review-summary", methods=["GET"])
def oom_sakkie_trace_review_summary():
    denied = _require_review_access()
    if denied:
        return denied
    result, status_code = get_trace_review_summary(
        channel=request.args.get("channel", "").strip(),
        days=request.args.get("days", 14),
    )
    return jsonify(result), status_code


@oom_sakkie_bp.route("/oom-sakkie/traces/<trace_id>/feedback", methods=["POST"])
def oom_sakkie_trace_feedback(trace_id):
    denied = _require_review_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = record_trace_feedback(trace_id, payload)
    return jsonify(result), status_code
