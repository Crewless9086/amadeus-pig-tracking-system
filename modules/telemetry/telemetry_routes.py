from flask import Blueprint, jsonify, request

from modules.telemetry.power_service import (
    evaluate_power_alerts,
    get_current_power_state,
    get_recent_power_profile,
    ingest_power_reading,
)
from modules.telemetry.irrigation_service import get_irrigation_status
from modules.telemetry.rollup_service import get_daily_rollup_compare
from modules.telemetry.rootline_daily_brief import get_rootline_daily_brief
from modules.telemetry.rootline_daily_advisor import get_rootline_daily_advisor
from modules.telemetry.irrigation_daily_plan_service import get_current_daily_plan
from modules.telemetry.irrigation_command_service import (
    approve_plan_only_command,
    cancel_plan_only_command,
    create_plan_only_command,
    list_plan_only_commands,
)
from modules.auth.owner_access import (
    owner_admin_principal,
    require_owner_admin_access,
    require_owner_read_access,
)
from modules.telemetry.weather_service import (
    evaluate_weather_alerts,
    get_current_weather_state,
    get_weather_today_summary,
    get_weather_forecast,
    ingest_weather_forecast,
    ingest_weather_reading,
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


@telemetry_bp.route("/telemetry/power/alerts/evaluate", methods=["POST"])
def telemetry_power_alerts_evaluate():
    payload = request.get_json(silent=True) or {}
    provided_key = _telemetry_key_from_request()
    result, status_code = evaluate_power_alerts(payload, provided_key)
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/weather/current", methods=["GET"])
def telemetry_weather_current():
    result, status_code = get_current_weather_state()
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/irrigation/status", methods=["GET"])
def telemetry_irrigation_status():
    result, status_code = get_irrigation_status(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/weather/forecast", methods=["GET"])
def telemetry_weather_forecast():
    result, status_code = get_weather_forecast(request.args.get("days", 3))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/weather/today", methods=["GET"])
def telemetry_weather_today():
    result, status_code = get_weather_today_summary(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/weather/ingest", methods=["POST"])
def telemetry_weather_ingest():
    payload = request.get_json(silent=True) or {}
    provided_key = _telemetry_key_from_request()
    result, status_code = ingest_weather_reading(payload, provided_key)
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/weather/forecast/ingest", methods=["POST"])
def telemetry_weather_forecast_ingest():
    payload = request.get_json(silent=True) or {}
    provided_key = _telemetry_key_from_request()
    result, status_code = ingest_weather_forecast(payload, provided_key)
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/weather/alerts/evaluate", methods=["POST"])
def telemetry_weather_alerts_evaluate():
    payload = request.get_json(silent=True) or {}
    provided_key = _telemetry_key_from_request()
    result, status_code = evaluate_weather_alerts(payload, provided_key)
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rollups/daily", methods=["GET"])
def telemetry_daily_rollups():
    result, status_code = get_daily_rollup_compare(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/daily-brief", methods=["GET"])
def telemetry_rootline_daily_brief():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_rootline_daily_brief(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/daily-advisor", methods=["GET"])
def telemetry_rootline_daily_advisor():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_rootline_daily_advisor(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/daily-irrigation-plan", methods=["GET"])
def telemetry_rootline_daily_irrigation_plan():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = get_current_daily_plan(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/irrigation-commands", methods=["GET"])
def telemetry_rootline_irrigation_commands():
    guard = require_owner_read_access()
    if guard:
        return guard
    result, status_code = list_plan_only_commands(limit=request.args.get("limit", 50))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/irrigation-commands", methods=["POST"])
def telemetry_rootline_irrigation_command_create():
    guard = require_owner_admin_access()
    if guard:
        return guard
    result, status_code = create_plan_only_command(
        request.get_json(silent=True) or {}, owner_admin_principal()
    )
    return jsonify(result), status_code


@telemetry_bp.route(
    "/telemetry/rootline/irrigation-commands/<command_id>/approve", methods=["POST"]
)
def telemetry_rootline_irrigation_command_approve(command_id):
    guard = require_owner_admin_access()
    if guard:
        return guard
    result, status_code = approve_plan_only_command(command_id, owner_admin_principal())
    return jsonify(result), status_code


@telemetry_bp.route(
    "/telemetry/rootline/irrigation-commands/<command_id>/cancel", methods=["POST"]
)
def telemetry_rootline_irrigation_command_cancel(command_id):
    guard = require_owner_admin_access()
    if guard:
        return guard
    result, status_code = cancel_plan_only_command(command_id, owner_admin_principal())
    return jsonify(result), status_code


def _telemetry_key_from_request():
    provided_key = request.headers.get("X-Amadeus-Telemetry-Key", "")
    if not provided_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            provided_key = auth_header[7:].strip()
    return provided_key
