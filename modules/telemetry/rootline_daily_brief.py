"""Read-only Rootline evidence composition for the owner daily brief."""

from datetime import datetime
from zoneinfo import ZoneInfo

from modules.telemetry.irrigation_service import get_irrigation_status
from modules.telemetry.power_service import get_current_power_state
from modules.telemetry.rollup_service import get_daily_rollup_compare
from modules.telemetry.weather_service import (
    get_current_weather_state,
    get_weather_forecast,
    get_weather_today_summary,
)


ZA_TZ = ZoneInfo("Africa/Johannesburg")
SPRINKLER_WIND_CAUTION_KMH = 30
RAIN_CAUTION_MM = 0.5


def get_rootline_daily_brief(brief_date=None, readers=None):
    selected_date = str(brief_date or datetime.now(ZA_TZ).date().isoformat())[:10]
    readers = readers or {
        "weather_current": lambda: get_current_weather_state(),
        "weather_today": lambda: get_weather_today_summary(selected_date),
        "forecast": lambda: get_weather_forecast(3),
        "power": lambda: get_current_power_state(),
        "irrigation": lambda: get_irrigation_status(selected_date),
        "rollups": lambda: get_daily_rollup_compare(selected_date),
    }
    evidence = {name: _safe_read(reader) for name, reader in readers.items()}
    return build_rootline_daily_brief(evidence, selected_date), 200


def build_rootline_daily_brief(evidence, brief_date):
    weather = _usable(evidence.get("weather_current"))
    today = _usable(evidence.get("weather_today"))
    forecast = _usable(evidence.get("forecast"))
    power = _usable(evidence.get("power"))
    irrigation = _usable(evidence.get("irrigation"))
    rollups = _usable(evidence.get("rollups"))
    tank = _usable(evidence.get("tank"))
    pump = _usable(evidence.get("pump"))
    borehole = _usable(evidence.get("borehole"))

    unresolved = []
    for key, label in (
        ("weather_current", "Current local weather"),
        ("weather_today", "Today's weather coverage"),
        ("forecast", "Three-day forecast"),
        ("power", "Current power"),
        ("irrigation", "Irrigation plan and state"),
        ("rollups", "Daily telemetry rollups"),
    ):
        if not _usable(evidence.get(key)):
            unresolved.append(f"{label}: Unavailable.")

    weather_stale = bool(weather.get("source", {}).get("is_stale")) if weather else None
    forecast_stale = bool(forecast.get("source", {}).get("is_stale")) if forecast else None
    power_stale = bool(power.get("source", {}).get("is_stale")) if power else None
    if weather_stale:
        unresolved.append("Current local weather is stale; last-known values cannot prove present safety.")
    if forecast_stale:
        unresolved.append("Three-day forecast is stale; no next safe window is asserted.")
    if power_stale:
        unresolved.append("Power telemetry is stale; irrigation power readiness requires owner review.")

    if not tank:
        unresolved.append("Tank level evidence: Unavailable.")
    if not pump:
        unresolved.append("Pump state evidence: Unavailable.")
    if not borehole:
        unresolved.append("Borehole state/window evidence: Unavailable.")
    unresolved.append("Alert delivery and cooldown state: Unavailable (evaluation/send routes were not invoked).")

    weather_values = weather.get("current", {}) if weather else {}
    today_flags = today.get("flags", {}) if today else {}
    rain_caution = bool(today_flags.get("irrigation_caution") and (
        _number(today.get("rain", {}).get("total_mm")) >= RAIN_CAUTION_MM
    )) if today else False
    wind_speed = max(
        _number(weather_values.get("wind_speed_kmh")),
        _number(today.get("wind", {}).get("max_speed_kmh")) if today else 0,
    )
    wind_caution = wind_speed >= SPRINKLER_WIND_CAUTION_KMH
    power_flags = power.get("flags", {}) if power else {}
    power_status = str(power.get("summary", {}).get("status") or "").lower() if power else ""
    power_values = power.get("current", {}) if power else {}
    all_zero_keys = ("battery_soc_pct", "solar_power_w", "load_power_w", "grid_power_w", "generator_power_w")
    all_zero_power = bool(
        power
        and all(key in power_values for key in all_zero_keys)
        and all(_number(power_values.get(key)) == 0 for key in all_zero_keys)
    )
    if all_zero_power:
        unresolved.append(
            "Power packet is all-zero and therefore suspicious/unverified; it is not proof of an empty battery, no load, no generation, or healthy power."
        )
    power_hold = bool(
        power and not power_stale and (
            all_zero_power
            or
            power_status in {"warning", "critical", "offline", "no_power", "hold"}
            or any(power_flags.get(key) for key in ("grid_down", "power_unavailable", "load_shed", "inverter_offline"))
        )
    )
    conflict = bool(irrigation.get("today", {}).get("next_zone_mismatch")) if irrigation else False
    if conflict:
        unresolved.append("Irrigation STATE and computed priority disagree on the next zone.")

    zones = []
    plan = irrigation.get("today", {}).get("plan", []) if irrigation else []
    for item in plan:
        zones.append(_zone_recommendation(
            item, rain_caution, wind_caution, power_hold,
            weather_available=bool(weather and today and not weather_stale),
            power_available=bool(power and not power_stale),
            infrastructure_available=bool(tank and pump and borehole),
            conflict=conflict,
        ))

    missed = [
        zone for zone in zones
        if zone["work_state"] in {"missed", "skipped", "paused"}
    ]
    missed.sort(key=lambda item: (-_number(item.get("water_score")), item["zone_id"]))

    next_window = _next_safe_window(forecast, forecast_stale)
    if next_window is None:
        unresolved.append("Next safe irrigation window: Unavailable.")

    decisions = []
    if conflict:
        decisions.append("Confirm which next-zone source is authoritative before irrigation proceeds.")
    for zone in zones:
        if zone["recommendation"] == "review":
            decisions.append(f"Decide whether {zone['zone_name']} should remain held or be manually reprioritized.")
    if not irrigation:
        decisions.append("Restore or confirm the irrigation plan/state source.")
    if not power or power_stale:
        decisions.append("Confirm current power availability before any irrigation run.")
    if any("Tank level" in item for item in unresolved):
        decisions.append("Confirm tank level and pump readiness before acting on this brief.")
    decisions = list(dict.fromkeys(decisions))

    headline = _executive_summary(
        zones, missed, weather_stale, rain_caution, wind_caution, power_hold, unresolved
    )
    return {
        "success": True,
        "status": "review_required" if unresolved or any(z["recommendation"] != "proceed" for z in zones) else "ready",
        "mode": "owner_read_only",
        "brief_date": brief_date,
        "executive_summary": headline,
        "current_conditions": {
            "availability": "Available" if weather else "Unavailable",
            "freshness": _freshness(weather),
            "last_reading_at": weather.get("source", {}).get("last_reading_at") if weather else None,
            "data_age_minutes": weather.get("source", {}).get("data_age_minutes") if weather else None,
            "temperature_c": weather_values.get("temperature_c") if weather else None,
            "humidity_pct": weather_values.get("humidity_pct") if weather else None,
            "rain_rate_mm_h": weather_values.get("rain_rate_mm_h") if weather else None,
            "rain_today_mm": weather_values.get("rain_today_mm") if weather else None,
            "wind_speed_kmh": weather_values.get("wind_speed_kmh") if weather else None,
            "wind_gust_kmh": weather_values.get("wind_gust_kmh") if weather else None,
            "pressure_hpa": weather_values.get("pressure_hpa") if weather else None,
        },
        "today_weather": {
            "availability": "Available" if today else "Unavailable",
            "coverage_pct": today.get("window", {}).get("coverage_pct") if today else None,
            "first_reading_at": today.get("window", {}).get("first_reading_at") if today else None,
            "last_reading_at": today.get("window", {}).get("last_reading_at") if today else None,
            "rain_total_mm": today.get("rain", {}).get("total_mm") if today else None,
        },
        "forecast": {
            "availability": "Available" if forecast else "Unavailable",
            "freshness": _freshness(forecast),
            "last_forecast_run_at": forecast.get("source", {}).get("last_forecast_run_at") if forecast else None,
            "data_age_minutes": forecast.get("source", {}).get("data_age_minutes") if forecast else None,
            "returned_days": forecast.get("window", {}).get("returned_days") if forecast else None,
        },
        "power": {
            "availability": "Available" if power else "Unavailable",
            "freshness": _freshness(power),
            "last_reading_at": power.get("source", {}).get("last_reading_at") if power else None,
            "data_age_minutes": power.get("source", {}).get("data_age_minutes") if power else None,
            "status": power.get("summary", {}).get("status") if power else None,
            "headline": power.get("summary", {}).get("headline") if power else None,
            "interpretation": (
                "Suspicious/unverified all-zero telemetry; do not treat these zeroes as physical truth."
                if all_zero_power else
                power.get("summary", {}).get("headline") if power else None
            ),
            "battery_soc_pct": power.get("current", {}).get("battery_soc_pct") if power else None,
            "grid_state": power.get("current", {}).get("grid_state") if power else None,
            "generator_state": power.get("current", {}).get("generator_state") if power else None,
        },
        "irrigation": {
            "availability": "Available" if irrigation else "Unavailable",
            "current_status": irrigation.get("current", {}).get("status") if irrigation else None,
            "planned_count": irrigation.get("today", {}).get("total_plan_rows") if irrigation else None,
            "completed_count": irrigation.get("today", {}).get("done_count") if irrigation else None,
            "skipped_count": irrigation.get("today", {}).get("skipped_count") if irrigation else None,
            "paused_count": irrigation.get("today", {}).get("paused_count") if irrigation else None,
            "planned_minutes": irrigation.get("today", {}).get("total_planned_minutes") if irrigation else None,
            "completed_minutes": irrigation.get("today", {}).get("completed_minutes") if irrigation else None,
            "zones": zones,
            "missed_reprioritization": missed,
        },
        "holds": {
            "rain_caution": rain_caution,
            "wind_sprinkler_caution": wind_caution,
            "power_hold": power_hold,
            "tank": "Available" if tank else "Unavailable",
            "pump": "Available" if pump else "Unavailable",
            "borehole": "Available" if borehole else "Unavailable",
        },
        "next_safe_window": next_window or {"status": "Unavailable"},
        "daily_rollups": {
            "availability": "Available" if rollups else "Unavailable",
            "comparison": rollups.get("comparison") if rollups else None,
        },
        "unresolved_evidence": list(dict.fromkeys(unresolved)),
        "owner_decisions_needed": decisions,
        "authority": {
            "writes_performed": False,
            "hardware_control_performed": False,
            "schedule_mutation_performed": False,
            "alert_send_performed": False,
            "telegram_action_performed": False,
        },
        "source": {
            "composed_from_existing_readers": True,
            "writes_to_supabase": False,
            "writes_to_sheets": False,
        },
    }


def _zone_recommendation(
    item, rain, wind, power_hold, weather_available, power_available,
    infrastructure_available, conflict,
):
    status = str(item.get("status") or "unknown").strip().lower()
    zone_name = item.get("zone_name") or item.get("zone_id") or "Unnamed zone"
    work_state = "completed" if status in {"done", "completed"} else (
        "skipped" if status == "skipped" else "paused" if status in {"paused", "blocked"} else
        "missed" if status in {"missed", "overdue"} else "planned"
    )
    reasons = []
    recommendation = "proceed"
    if work_state == "completed":
        recommendation = "proceed"
        reasons.append("Already completed; no further run is recommended.")
    elif conflict:
        recommendation = "review"
        reasons.append("Plan priority conflicts with controller state.")
    elif not weather_available or not power_available:
        recommendation = "review"
        reasons.append("Fresh weather and power evidence are both required.")
    elif not infrastructure_available:
        recommendation = "review"
        reasons.append("Tank, pump, and borehole readiness evidence is required before proceeding.")
    elif power_hold:
        recommendation = "hold"
        reasons.append("Power evidence indicates a hold.")
    elif rain:
        recommendation = "hold"
        reasons.append("Observed rain supports delaying irrigation.")
    elif wind and "sprinkler" in zone_name.lower():
        recommendation = "hold"
        reasons.append("High wind makes sprinkler irrigation inefficient.")
    else:
        reasons.append("No deterministic weather or power hold is present in available evidence.")
    return {
        "zone_id": item.get("zone_id") or "",
        "zone_name": zone_name,
        "work_state": work_state,
        "recommendation": recommendation,
        "planned_minutes": item.get("planned_minutes"),
        "water_score": item.get("water_score"),
        "reasoning": reasons,
    }


def _next_safe_window(forecast, stale):
    if not forecast or stale:
        return None
    for day in forecast.get("days", []):
        if _number(day.get("rain_sum_mm")) < RAIN_CAUTION_MM and _number(day.get("wind_max_kmh")) < SPRINKLER_WIND_CAUTION_KMH:
            return {
                "status": "supported_forecast_day",
                "date": day.get("forecast_date"),
                "basis": "Forecast rain and maximum wind are below Rootline caution thresholds; confirm live conditions before acting.",
            }
    return None


def _executive_summary(zones, missed, stale, rain, wind, power_hold, unresolved):
    if not zones:
        return "Rootline cannot confirm today's irrigation work because the plan is unavailable. Hold action until the listed evidence and owner decisions are resolved."
    completed = sum(zone["work_state"] == "completed" for zone in zones)
    held = sum(zone["recommendation"] == "hold" for zone in zones)
    conditions = []
    if stale:
        conditions.append("local weather is stale")
    if rain:
        conditions.append("rain supports caution")
    if wind:
        conditions.append("wind affects sprinklers")
    if power_hold:
        conditions.append("power evidence requires a hold")
    context = "; ".join(conditions) or "no supported weather or power hold is present"
    return (
        f"Rootline found {len(zones)} planned zone(s): {completed} completed, "
        f"{len(missed)} missed/skipped/paused, and {held} held. {context.capitalize()}. "
        f"{len(unresolved)} evidence gap(s) still require explicit review."
    )


def _safe_read(reader):
    try:
        result = reader()
        payload, status = result if isinstance(result, tuple) else (result, 200)
        if status >= 400 or not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        return None


def _usable(value):
    return value if isinstance(value, dict) and value.get("success") is True else None


def _freshness(value):
    if not value:
        return "Unavailable"
    return "stale" if value.get("source", {}).get("is_stale") else "fresh"


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
