from flask import Blueprint, jsonify, request

from modules.oom_sakkie.access import is_review_request_allowed, review_access_denied_response
from modules.oom_sakkie.policy import get_runtime_policy
from modules.oom_sakkie.review_advisor import get_review_advisor
from modules.oom_sakkie.service import handle_message
from modules.oom_sakkie.specialists import list_specialist_manifests
from modules.oom_sakkie.tools import list_tool_catalog
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
