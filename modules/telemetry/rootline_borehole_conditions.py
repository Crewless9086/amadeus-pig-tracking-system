"""Borehole-only continuous policy on the existing execution/event rail."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

VERSION = "rootline_borehole_runtime_eligibility.v5"
MODE = "conditions"
IDENTITY = "BOREHOLE-1-MINI-R4-CH1"
DEVICE_KEY = "ewelink:ewelink_owner_account:1002851416:1"
POLICY = "rootline_borehole_continuous_authority.v1"


def continuous_borehole(value):
    return (isinstance(value, dict) and value.get("contract_version") == VERSION
        and value.get("stop_mode") == MODE and value.get("device_key") == DEVICE_KEY
        and value.get("device_id") == "1002851416" and type(value.get("channel")) is int
        and value["channel"] == 1 and value.get("auxiliary_device_id") == IDENTITY
        and value.get("requested_seconds") is None and value.get("native_fail_stop_seconds") == 0)


def continuous_device_profile(record):
    return (record.get("stop_mode") == MODE and record.get("provider") == "ewelink"
        and record.get("provider_account_binding") == "ewelink_owner_account"
        and record.get("device_id") == "1002851416" and type(record.get("channel")) is int
        and record["channel"] == 1 and record.get("device_type") == "pump"
        and record.get("adapter_profile") == "ewelink_borehole_conditions_v1"
        and type(record.get("maximum_runtime_seconds")) is int
        and record["maximum_runtime_seconds"] == 0
        and type(record.get("native_fail_stop_seconds")) is int
        and record["native_fail_stop_seconds"] == 0)


def continuous_policy_valid(record, resolved):
    policy = resolved.get("policy_payload") or {}
    expected = {"contract_version": POLICY, "stop_mode": MODE,
        "device_keys": [DEVICE_KEY], "device_identities": [IDENTITY],
        "allowed_channels": [1], "provider": "ewelink",
        "provider_account_binding": "ewelink_owner_account", "device_id": "1002851416",
        "maximum_runtime_seconds": 0, "native_fail_stop_seconds": 0,
        "application_stop_ownership_required": True, "automatic_on_retry": False,
        "solar_proxy_w": 1500, "battery_floor_soc_pct": 30,
        "forecast_start_deferral_seconds": 3600, "forecast_deferral_once_per_opportunity": True,
        "rain_reassessment_seconds": 3600, "rain_free_resume_seconds": 3600,
        "grid_cost_estimate_zar_per_kwh": 9.2, "missing_readings_alone_stop": False}
    return (continuous_device_profile(record) and isinstance(policy, dict)
        and all(type(policy.get(k)) is type(v) and policy.get(k) == v for k, v in expected.items())
        and digest(policy) == resolved.get("policy_sha256"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def moment(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def assess_weather(snapshot, *, now):
    """Use one source-coherent hour snapshot; missing samples cannot make it dry."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    weather = snapshot.get("weather_current") or {}
    source = weather.get("source") or {}
    release = snapshot.get("rain_release") or {}
    observed = moment(source.get("last_reading_at"))
    cutoff = moment(snapshot.get("snapshot_cutoff"))
    stale = number(source.get("stale_after_minutes"))
    rate = number((weather.get("current") or {}).get("rain_rate_mm_h"))
    from modules.telemetry.weather_service import DEFAULT_WEATHER_SOURCE_ID
    fresh = (snapshot.get("success") is True and weather.get("success") is True
        and source.get("source_id") == DEFAULT_WEATHER_SOURCE_ID
        and release.get("source_id") == DEFAULT_WEATHER_SOURCE_ID
        and observed is not None and cutoff is not None and observed <= cutoff <= now
        and stale is not None and stale > 0 and now-observed <= timedelta(minutes=min(30, stale))
        and release.get("source_healthy") is True
        and rate is not None and rate >= 0)
    readings = release.get("station_readings") or []
    times = [moment(row.get("observed_at")) for row in readings if isinstance(row, dict)]
    # Live station evidence on 2026-11-16 showed ordinary gaps of193..371s.
    # Two nominal five-minute slots tolerate sampling jitter; >600s is an
    # unknown interval. This bounds observational coverage, not pump runtime.
    dry_hour = (fresh and rate == 0 and len(times) == len(readings) and len(times) >= 2
        and all(at is not None for at in times) and times[-1] == observed
        and times[-1]-times[0] >= timedelta(hours=1)
        and all(timedelta(0) < b-a <= timedelta(seconds=600) for a,b in zip(times,times[1:]))
        and all(number(row.get("rain_rate_mm_h")) == 0 for row in readings))
    return {"fresh": bool(fresh), "observed_at": observed.isoformat() if observed else None,
        "rain_detected": bool(fresh and rate > 0), "dry_hour": bool(dry_hour),
        "rain_rate_mm_h": rate if fresh else None,
        "dry_interval_start_at": times[0].isoformat() if dry_hour else None,
        "snapshot_sha256": digest(snapshot)}


def heavy_forecast(forecast, *, now):
    """Reuse the weather service's existing heavy-rain threshold, not its general rain signal."""
    from modules.telemetry.weather_service import ALERT_FORECAST_HEAVY_RAIN_MM
    forecast = forecast if isinstance(forecast, dict) else {}
    at = moment(forecast.get("observed_at"))
    days = forecast.get("days") or []
    rain = number(days[0].get("rain_sum_mm")) if days and isinstance(days[0], dict) else None
    return (at is not None and timedelta(0) <= now-at <= timedelta(hours=6)
        and rain is not None and rain >= ALERT_FORECAST_HEAVY_RAIN_MM)


def advance_conditions(prior, *, weather, forecast, active, now):
    """Pure projection; the existing store serializes persistence and claims.

    A forecast opportunity ends only when an actual owned claim has existed.
    Failed preparation, unknown telemetry, new forecasts and midnight do not
    renew it. Rain hold survives every execution/terminal and restart.
    """
    prior = dict(prior or {})
    state = {key: prior.get(key) for key in ("opportunity_id", "forecast_deferred_at",
        "forecast_defer_until", "forecast_deferral_consumed", "last_owned_execution_id",
        "rain_hold", "last_rain_at", "next_rain_assessment_at",
        "forecast_evidence", "forecast_outcome", "forecast_outcome_at")}
    previous_owned = state.get("last_owned_execution_id")
    active_id = active.get("execution_id") if isinstance(active, dict) else None
    if not state.get("opportunity_id") or previous_owned and not active_id:
        state.update(opportunity_id=digest({"previous": state.get("opportunity_id"),
            "completed_execution": previous_owned, "created_at": now.isoformat()}),
            forecast_deferred_at=None, forecast_defer_until=None,
            forecast_deferral_consumed=False, last_owned_execution_id=None,
            forecast_evidence=None, forecast_outcome=None, forecast_outcome_at=None)
    if active_id:
        state["last_owned_execution_id"] = active_id
    rain_at = moment(weather.get("observed_at"))
    if weather.get("rain_detected") is True:
        state.update(rain_hold=True, last_rain_at=weather.get("observed_at"))
        if not prior.get("rain_hold"):
            state["next_rain_assessment_at"] = (now+timedelta(hours=1)).isoformat()
    due = moment(state.get("next_rain_assessment_at"))
    if state.get("rain_hold") and due is not None and now >= due:
        start = moment(weather.get("dry_interval_start_at"))
        last_rain = moment(state.get("last_rain_at"))
        if (weather.get("dry_hour") is True and start is not None
                and (last_rain is None or start >= last_rain)):
            state.update(rain_hold=False, next_rain_assessment_at=None)
        else:
            state["next_rain_assessment_at"] = (now+timedelta(hours=1)).isoformat()
    if (not active_id and not state.get("rain_hold") and not state.get("forecast_deferral_consumed")
            and heavy_forecast(forecast, now=now)):
        state.update(forecast_deferral_consumed=True, forecast_deferred_at=now.isoformat(),
            forecast_defer_until=(now+timedelta(hours=1)).isoformat(),
            forecast_evidence=dict(forecast or {}), forecast_outcome="pending", forecast_outcome_at=None)
    until = moment(state.get("forecast_defer_until"))
    if state.get("forecast_outcome") in {"pending", "local_observation_unavailable"}:
        if weather.get("rain_detected") is True:
            state.update(forecast_outcome="local_rain_observed", forecast_outcome_at=weather.get("observed_at"))
        elif until is not None and now >= until:
            state.update(forecast_outcome=("no_local_rain_at_reassessment" if weather.get("fresh") is True
                else "local_observation_unavailable"), forecast_outcome_at=now.isoformat())
    reason = ("observed_rain" if weather.get("rain_detected") else
        "rain_free_hour_pending" if state.get("rain_hold") else
        "forecast_start_deferred" if until is not None and now < until else
        "local_weather_unavailable" if weather.get("fresh") is not True else "conditions_allow_start")
    return {**state, "contract_version": "rootline_borehole_conditions.v1",
        "device_key": DEVICE_KEY, "start_eligible": reason == "conditions_allow_start",
        "stop_required": bool(weather.get("rain_detected") is True or state.get("rain_hold")),
        "reason": reason, "weather": dict(weather), "assessed_at": now.isoformat(),
        "next_assessment_at": state.get("next_rain_assessment_at") or
            (until.isoformat() if until is not None and now < until else None)}
