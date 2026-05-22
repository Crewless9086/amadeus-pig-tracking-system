from flask import Blueprint, jsonify, request

from modules.telemetry.power_service import (
    get_current_power_state,
    get_recent_power_profile,
    ingest_power_reading,
)


telemetry_bp = Blueprint("telemetry", __name__)


@telemetry_bp.route("/telemetry/power/current", methods=["GET"])
def telemetry_power_current():
    result, status_code = get_current_power_state()
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/power/recent", methods=["GET"])
def telemetry_power_recent():
    result, status_code = get_recent_power_profile(request.args.get("hours", 24))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/power/ingest", methods=["POST"])
def telemetry_power_ingest():
    payload = request.get_json(silent=True) or {}
    provided_key = request.headers.get("X-Amadeus-Telemetry-Key", "")
    if not provided_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            provided_key = auth_header[7:].strip()
    result, status_code = ingest_power_reading(payload, provided_key)
    return jsonify(result), status_code
