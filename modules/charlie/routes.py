from flask import Blueprint, jsonify, request

from modules.auth.owner_access import require_owner_read_access
from modules.charlie.build_relay import (
    build_relay_policy,
    handle_charlie_telegram_webhook,
)
from modules.charlie.mission_store import list_missions


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
