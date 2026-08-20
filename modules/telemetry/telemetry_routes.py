from flask import Blueprint, current_app, jsonify, request

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
from modules.telemetry.rootline_water_energy_plan import (
    append_water_energy_plan,
    build_current_water_energy_plan,
    get_current_water_energy_plan,
    get_oom_sakkie_water_energy_summary,
    record_tank_observation,
)
from modules.telemetry.rootline_operating_policy import (
    activate_policy,
    list_policy_review,
    policy_review_contract,
    preview_policy_effect,
    propose_policy,
    review_policy,
)
from modules.telemetry.rootline_parent_job_resolution import (
    resolve_current_contained_b_parent,
)
from modules.telemetry.rootline_ewelink_oauth import (
    OAuthFailure,
    complete_authorization,
    create_authorization_request,
    oauth_readiness,
)
from modules.telemetry.rootline_ewelink_oauth_store import (
    PostgresOAuthStateStore,
    PostgresOAuthTokenStore,
)
from modules.telemetry.rootline_ewelink_readback import (
    read_current_device, read_registered_device,
)
from modules.telemetry.irrigation_daily_plan_service import get_current_daily_plan
from modules.telemetry.irrigation_command_service import (
    approve_plan_only_command,
    cancel_plan_only_command,
    create_plan_only_command,
    list_plan_only_commands,
)
from modules.auth.owner_access import (
    owner_admin_principal,
    strict_owner_admin_principal,
    owner_session_is_valid,
    require_owner_admin_access,
    require_owner_read_access,
    require_strict_owner_admin_access,
    require_strict_owner_read_access,
    strict_owner_read_principal,
)
from modules.telemetry.rootline_operational_evidence import build_rootline_operational_evidence
from modules.telemetry.weather_service import (
    evaluate_weather_alerts,
    get_current_weather_state,
    get_weather_today_summary,
    get_weather_forecast,
    ingest_weather_forecast,
    ingest_weather_reading,
)


telemetry_bp = Blueprint("telemetry", __name__)


@telemetry_bp.route("/rootline/provider/ewelink/oauth/readiness", methods=["GET"])
def rootline_ewelink_oauth_readiness():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    result = oauth_readiness()
    return jsonify(result), 200 if result["status"] == "ready" else 503


@telemetry_bp.route("/rootline/provider/ewelink/oauth/start", methods=["POST"])
def rootline_ewelink_oauth_start():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    try:
        result = create_authorization_request(
            principal=strict_owner_admin_principal(),
            state_store=PostgresOAuthStateStore(),
        )
    except OAuthFailure as exc:
        return jsonify({"status": "rejected", "reason": str(exc)}), 409
    except Exception:
        return jsonify({"status": "unavailable", "reason": "oauth_state_persistence_failed"}), 503
    return jsonify(result), 201


@telemetry_bp.route("/rootline/provider/ewelink/oauth/callback", methods=["GET"])
def rootline_ewelink_oauth_callback():
    try:
        result = complete_authorization(
            query=request.args,
            state_store=PostgresOAuthStateStore(),
            token_store=PostgresOAuthTokenStore(),
        )
    except OAuthFailure as exc:
        return jsonify({"status": "rejected", "reason": str(exc), "secrets_exposed": False}), 400
    except Exception:
        return jsonify({"status": "unavailable", "reason": "oauth_callback_persistence_failed",
                        "secrets_exposed": False}), 503
    return jsonify(result), 200


@telemetry_bp.route("/rootline/provider/ewelink/readback", methods=["GET"])
def rootline_ewelink_readback():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    try:
        requested = str(request.args.get("device_id") or "").strip()
        result = (read_registered_device(
            requested, token_store=PostgresOAuthTokenStore())
            if requested else read_current_device(token_store=PostgresOAuthTokenStore()))
    except OAuthFailure as exc:
        return jsonify({"status": "rejected", "reason": str(exc),
                        "secrets_exposed": False}), 409
    except Exception:
        return jsonify({"status": "unavailable", "reason": "ewelink_readback_failed",
                        "secrets_exposed": False}), 503
    return jsonify(result), 200


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
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    result, status_code = get_irrigation_status(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/operational-evidence", methods=["GET"])
def telemetry_rootline_operational_evidence():
    """Expose exact current B evidence with no execution or write capability."""
    guard = require_strict_owner_read_access()
    if guard:
        current_app.logger.warning("rootline operational evidence read denied remote=%s",
                                   request.remote_addr or "Unknown")
        return guard
    def provider_reader(device_id):
        return read_registered_device(device_id, token_store=PostgresOAuthTokenStore(),
                                      allow_token_refresh=False)
    result, status_code = build_rootline_operational_evidence(
        requester=strict_owner_read_principal(), provider_reader=provider_reader)
    current_app.logger.info("rootline operational evidence read audit_id=%s requester=%s revision=%s",
        (result.get("audit") or {}).get("audit_id"),
        (result.get("audit") or {}).get("requester"), result.get("requested_revision"))
    if isinstance(result.get("audit"), dict):
        result["audit"]["emitted"] = True
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response, status_code


@telemetry_bp.route("/telemetry/irrigation/status/legacy-audit", methods=["GET"])
def telemetry_irrigation_status_legacy_audit():
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    result, status_code = get_irrigation_status(
        request.args.get("date"), spreadsheet_name="Amadeus_Irrigation_Logs")
    result.setdefault("source", {})["operational_truth"] = False
    result["source"]["classification"] = "legacy_read_only_audit"
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


@telemetry_bp.route("/telemetry/rootline/water-energy-plan", methods=["GET"])
def telemetry_rootline_water_energy_plan():
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    result, status_code = get_current_water_energy_plan(request.args.get("date"))
    result["owner_can_administer"] = owner_session_is_valid("admin")
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/water-energy-summary", methods=["GET"])
def telemetry_rootline_water_energy_summary():
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    result, status_code = get_oom_sakkie_water_energy_summary(request.args.get("date"))
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/water-energy-plan/refresh", methods=["POST"])
def telemetry_rootline_water_energy_plan_refresh():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    candidate = build_current_water_energy_plan(payload.get("date"))
    result, status_code = append_water_energy_plan(
        candidate, strict_owner_admin_principal()
    )
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/tank-observations", methods=["POST"])
def telemetry_rootline_tank_observation():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    result, status_code = record_tank_observation(
        request.get_json(silent=True) or {}, strict_owner_admin_principal()
    )
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/contained-parent-resolution", methods=["POST"])
def telemetry_rootline_contained_parent_resolution():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    result, status_code = resolve_current_contained_b_parent(
        request.get_json(silent=True) or {}, strict_owner_admin_principal())
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/operating-policy", methods=["GET"])
def telemetry_rootline_operating_policy():
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    result, status_code = list_policy_review()
    result["owner_can_administer"] = owner_session_is_valid("admin")
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/operating-policy/contract", methods=["GET"])
def telemetry_rootline_operating_policy_contract():
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    return jsonify(policy_review_contract()), 200


@telemetry_bp.route("/telemetry/rootline/operating-policy/preview", methods=["POST"])
def telemetry_rootline_operating_policy_preview():
    guard = require_strict_owner_read_access()
    if guard:
        return guard
    payload = request.get_json(silent=True) or {}
    advisor, _status = get_rootline_daily_advisor(request.args.get("date"))
    result, status_code = preview_policy_effect(payload.get("policy"), advisor)
    return jsonify(result), status_code


@telemetry_bp.route("/telemetry/rootline/operating-policy/proposals", methods=["POST"])
def telemetry_rootline_operating_policy_propose():
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    result, status_code = propose_policy(
        request.get_json(silent=True) or {}, strict_owner_admin_principal()
    )
    return jsonify(result), status_code


@telemetry_bp.route(
    "/telemetry/rootline/operating-policy/proposals/<proposal_id>/review",
    methods=["POST"],
)
def telemetry_rootline_operating_policy_review(proposal_id):
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    result, status_code = review_policy(
        proposal_id, request.get_json(silent=True) or {}, strict_owner_admin_principal()
    )
    return jsonify(result), status_code


@telemetry_bp.route(
    "/telemetry/rootline/operating-policy/proposals/<proposal_id>/activate",
    methods=["POST"],
)
def telemetry_rootline_operating_policy_activate(proposal_id):
    guard = require_strict_owner_admin_access()
    if guard:
        return guard
    result, status_code = activate_policy(
        proposal_id, request.get_json(silent=True) or {}, strict_owner_admin_principal()
    )
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
