from flask import Blueprint, jsonify, request

from modules.telemetry.power_service import (
    get_current_power_state,
    get_recent_power_profile,
    ingest_power_reading,
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


@telemetry_bp.route("/telemetry/weather/current", methods=["GET"])
def telemetry_weather_current():
    result, status_code = get_current_weather_state()
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


def _telemetry_key_from_request():
    provided_key = request.headers.get("X-Amadeus-Telemetry-Key", "")
    if not provided_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            provided_key = auth_header[7:].strip()
    return provided_key
