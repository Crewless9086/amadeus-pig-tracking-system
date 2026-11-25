"""Authenticated browser API; all effects remain in the canonical controller."""
from flask import Blueprint, jsonify, request
from modules.auth.owner_access import (
    require_strict_owner_read_access, strict_owner_admin_principal,
)
from modules.auth.rootline_access import rootline_csrf_token, require_rootline_mutation

rootline_owner_controls_bp = Blueprint("rootline_owner_controls", __name__)


def _response(payload, status):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, status


@rootline_owner_controls_bp.get("/telemetry/rootline/owner-controls")
def owner_controls_read():
    guard = require_strict_owner_read_access()
    if guard is not None:
        return guard
    from modules.telemetry.rootline_owner_controls import get_owner_controls
    panel = request.args.get("panel")
    if panel not in {None, "forecast", "devices", "plan", "history"}:
        return _response({"success": False, "status": "unknown_panel"}, 400)
    payload, status = get_owner_controls(panel=panel)
    payload = dict(payload)
    payload["owner_can_administer"] = bool(strict_owner_admin_principal())
    payload["csrf_token"] = rootline_csrf_token()
    return _response(payload, status)


@rootline_owner_controls_bp.post("/telemetry/rootline/owner-controls/preview")
def owner_controls_preview():
    guard = require_rootline_mutation()
    if guard is not None:
        return guard
    from modules.telemetry.rootline_owner_controls import preview_owner_control
    return _response(*preview_owner_control(request.get_json(), strict_owner_admin_principal()))


@rootline_owner_controls_bp.post("/telemetry/rootline/owner-controls/apply")
def owner_controls_apply():
    guard = require_rootline_mutation()
    if guard is not None:
        return guard
    from modules.telemetry.rootline_owner_controls import apply_owner_control
    return _response(*apply_owner_control(request.get_json(), strict_owner_admin_principal()))
