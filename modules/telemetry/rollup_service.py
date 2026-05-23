import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.database_service import DATABASE_URL_ENV


ZA_TZ = ZoneInfo("Africa/Johannesburg")
POWER_SOURCE_ID = "sunsynk-main-inverter"
WEATHER_SOURCE_ID = "weather-station-main"
IRRIGATION_SOURCE_ID = "irrigation-controller-main"
EXPECTED_5MIN_SAMPLES_PER_DAY = 288


def get_daily_rollup_compare(rollup_date=None, database_url=None):
    selected_date = _parse_rollup_date(rollup_date)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "source": _source_metadata(),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
            "source": _source_metadata(),
        }, 500

    start_za = datetime(selected_date.year, selected_date.month, selected_date.day, tzinfo=ZA_TZ)
    end_za = start_za + timedelta(days=1)
    start_utc = start_za.astimezone(timezone.utc)
    end_utc = end_za.astimezone(timezone.utc)

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                stored = {
                    "power": _read_power_daily_rollup(cursor, selected_date),
                    "weather": _read_weather_daily_rollup(cursor, selected_date),
                    "irrigation": _read_irrigation_daily_rollup(cursor, selected_date),
                }
                raw_counts = {
                    "power": _read_power_raw_count(cursor, start_utc, end_utc),
                    "weather": _read_weather_raw_count(cursor, start_utc, end_utc),
                    "irrigation_events": _read_irrigation_event_count(cursor, start_utc, end_utc),
                    "irrigation_plan_items": _read_irrigation_plan_item_count(cursor, selected_date),
                }
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "daily_rollup_read_failed",
            "message": "Daily telemetry rollup read failed.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(),
        }, 503

    comparison = _build_comparison(stored, raw_counts)
    found_count = sum(1 for value in stored.values() if value)

    return {
        "success": found_count > 0,
        "configured": True,
        "status": "ok" if found_count > 0 else "unavailable",
        "date": selected_date.isoformat(),
        "timezone": "Africa/Johannesburg",
        "source_window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "expected_5min_samples": EXPECTED_5MIN_SAMPLES_PER_DAY,
        },
        "stored_rollups": stored,
        "raw_counts": raw_counts,
        "comparison": comparison,
        "operator_summary": _operator_summary(selected_date, stored, comparison),
        "source": _source_metadata(),
    }, 200


def _read_power_daily_rollup(cursor, selected_date):
    cursor.execute(
        """
        select rollup_id, source_id, rollup_date, source_window_start, source_window_end,
               sample_count, expected_sample_count, coverage_pct,
               battery_soc_min_pct, battery_soc_max_pct, battery_soc_avg_pct,
               load_power_avg_w, load_power_max_w, solar_power_avg_w, solar_power_max_w,
               grid_active_minutes, generator_active_minutes, no_solar_minutes,
               estimated_solar_kwh, estimated_load_kwh, estimated_grid_import_kwh,
               estimated_grid_export_kwh, estimated_generator_kwh,
               energy_calculation_method, tariff_zar_per_kwh, estimated_value_zar,
               limitations, calculation_version, generated_at
        from public.power_daily_rollups
        where source_id = %s and rollup_date = %s
        """,
        (POWER_SOURCE_ID, selected_date),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "rollup_id": row[0],
        "source_id": row[1],
        "rollup_date": _iso(row[2]),
        "source_window_start": _iso(row[3]),
        "source_window_end": _iso(row[4]),
        "sample_count": row[5],
        "expected_sample_count": row[6],
        "coverage_pct": _num(row[7]),
        "battery_soc_min_pct": _num(row[8]),
        "battery_soc_max_pct": _num(row[9]),
        "battery_soc_avg_pct": _num(row[10]),
        "load_power_avg_w": _num(row[11]),
        "load_power_max_w": _num(row[12]),
        "solar_power_avg_w": _num(row[13]),
        "solar_power_max_w": _num(row[14]),
        "grid_active_minutes": _num(row[15]),
        "generator_active_minutes": _num(row[16]),
        "no_solar_minutes": _num(row[17]),
        "estimated_solar_kwh": _num(row[18]),
        "estimated_load_kwh": _num(row[19]),
        "estimated_grid_import_kwh": _num(row[20]),
        "estimated_grid_export_kwh": _num(row[21]),
        "estimated_generator_kwh": _num(row[22]),
        "energy_calculation_method": row[23],
        "tariff_zar_per_kwh": _num(row[24]),
        "estimated_value_zar": _num(row[25]),
        "limitations": row[26] or [],
        "calculation_version": row[27],
        "generated_at": _iso(row[28]),
        "quality": _quality(row[7]),
        "is_estimated": True,
    }


def _read_weather_daily_rollup(cursor, selected_date):
    cursor.execute(
        """
        select rollup_id, source_id, rollup_date, source_window_start, source_window_end,
               sample_count, expected_sample_count, coverage_pct,
               temperature_min_c, temperature_max_c, temperature_avg_c, humidity_avg_pct,
               rain_total_mm, rain_rate_max_mm_h, wind_speed_max_kmh, wind_gust_max_kmh,
               pressure_min_hpa, pressure_max_hpa, irrigation_caution_minutes,
               flags, calculation_version, generated_at
        from public.weather_daily_rollups
        where source_id = %s and rollup_date = %s
        """,
        (WEATHER_SOURCE_ID, selected_date),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "rollup_id": row[0],
        "source_id": row[1],
        "rollup_date": _iso(row[2]),
        "source_window_start": _iso(row[3]),
        "source_window_end": _iso(row[4]),
        "sample_count": row[5],
        "expected_sample_count": row[6],
        "coverage_pct": _num(row[7]),
        "temperature_min_c": _num(row[8]),
        "temperature_max_c": _num(row[9]),
        "temperature_avg_c": _num(row[10]),
        "humidity_avg_pct": _num(row[11]),
        "rain_total_mm": _num(row[12]),
        "rain_rate_max_mm_h": _num(row[13]),
        "wind_speed_max_kmh": _num(row[14]),
        "wind_gust_max_kmh": _num(row[15]),
        "pressure_min_hpa": _num(row[16]),
        "pressure_max_hpa": _num(row[17]),
        "irrigation_caution_minutes": _num(row[18]),
        "flags": row[19] or {},
        "calculation_version": row[20],
        "generated_at": _iso(row[21]),
        "quality": _quality(row[7]),
    }


def _read_irrigation_daily_rollup(cursor, selected_date):
    cursor.execute(
        """
        select rollup_id, source_id, rollup_date, daily_plan_id, source_window_start, source_window_end,
               planned_zone_count, completed_zone_count, skipped_zone_count, paused_zone_count,
               planned_minutes, completed_minutes, active_runtime_minutes,
               weather_hold_minutes, power_hold_minutes, tank_hold_minutes,
               manual_override_count, event_count,
               fertilizer_injection_minutes, fertilizer_injection_cycles, fertilizer_mixer_minutes,
               tank_full_count, tank_empty_count, tank_status_notes,
               calculation_version, generated_at
        from public.irrigation_daily_rollups
        where source_id = %s and rollup_date = %s
        """,
        (IRRIGATION_SOURCE_ID, selected_date),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "rollup_id": row[0],
        "source_id": row[1],
        "rollup_date": _iso(row[2]),
        "daily_plan_id": row[3],
        "source_window_start": _iso(row[4]),
        "source_window_end": _iso(row[5]),
        "planned_zone_count": row[6],
        "completed_zone_count": row[7],
        "skipped_zone_count": row[8],
        "paused_zone_count": row[9],
        "planned_minutes": _num(row[10]),
        "completed_minutes": _num(row[11]),
        "active_runtime_minutes": _num(row[12]),
        "weather_hold_minutes": _num(row[13]),
        "power_hold_minutes": _num(row[14]),
        "tank_hold_minutes": _num(row[15]),
        "manual_override_count": row[16],
        "event_count": row[17],
        "fertilizer_injection_minutes": _num(row[18]),
        "fertilizer_injection_cycles": row[19],
        "fertilizer_mixer_minutes": _num(row[20]),
        "tank_full_count": row[21],
        "tank_empty_count": row[22],
        "tank_status_notes": row[23],
        "calculation_version": row[24],
        "generated_at": _iso(row[25]),
        "quality": "operational_snapshot",
    }


def _read_power_raw_count(cursor, start_utc, end_utc):
    cursor.execute(
        """
        select count(*)::int
        from public.power_readings_5min
        where source_id = %s
          and reading_at >= %s
          and reading_at < %s
          and raw_payload is not null
        """,
        (POWER_SOURCE_ID, start_utc, end_utc),
    )
    return cursor.fetchone()[0]


def _read_weather_raw_count(cursor, start_utc, end_utc):
    cursor.execute(
        """
        select count(*)::int
        from public.weather_readings
        where source_id = %s
          and reading_at >= %s
          and reading_at < %s
          and coalesce(raw_payload->>'test', 'false') <> 'true'
        """,
        (WEATHER_SOURCE_ID, start_utc, end_utc),
    )
    return cursor.fetchone()[0]


def _read_irrigation_event_count(cursor, start_utc, end_utc):
    cursor.execute(
        """
        select count(*)::int
        from (
            select distinct event_at, zone_id, event_type, planned_minutes, actual_minutes, reason, actor
            from public.irrigation_events
            where source_id = %s
              and event_at >= %s
              and event_at < %s
        ) deduped
        """,
        (IRRIGATION_SOURCE_ID, start_utc, end_utc),
    )
    return cursor.fetchone()[0]


def _read_irrigation_plan_item_count(cursor, selected_date):
    cursor.execute(
        """
        select count(*)::int
        from public.irrigation_plan_items item
        join public.irrigation_daily_plans plan on plan.daily_plan_id = item.daily_plan_id
        where plan.source_id = %s
          and plan.plan_date = %s
          and plan.plan_status not in ('Cancelled', 'Superseded')
        """,
        (IRRIGATION_SOURCE_ID, selected_date),
    )
    return cursor.fetchone()[0]


def _build_comparison(stored, raw_counts):
    return {
        "power": _sample_comparison(stored["power"], raw_counts["power"]),
        "weather": _sample_comparison(stored["weather"], raw_counts["weather"]),
        "irrigation": {
            "rollup_found": bool(stored["irrigation"]),
            "stored_plan_items": stored["irrigation"]["planned_zone_count"] if stored["irrigation"] else None,
            "current_plan_items": raw_counts["irrigation_plan_items"],
            "plan_item_match": (
                stored["irrigation"]["planned_zone_count"] == raw_counts["irrigation_plan_items"]
                if stored["irrigation"] else False
            ),
            "stored_event_count": stored["irrigation"]["event_count"] if stored["irrigation"] else None,
            "current_event_count": raw_counts["irrigation_events"],
            "event_count_match": (
                stored["irrigation"]["event_count"] == raw_counts["irrigation_events"]
                if stored["irrigation"] else False
            ),
        },
    }


def _sample_comparison(stored_rollup, current_count):
    if not stored_rollup:
        return {
            "rollup_found": False,
            "stored_sample_count": None,
            "current_sample_count": current_count,
            "sample_count_match": False,
            "stored_coverage_pct": None,
            "current_coverage_pct": _coverage(current_count),
            "quality": "missing",
        }
    return {
        "rollup_found": True,
        "stored_sample_count": stored_rollup["sample_count"],
        "current_sample_count": current_count,
        "sample_count_match": stored_rollup["sample_count"] == current_count,
        "stored_coverage_pct": stored_rollup["coverage_pct"],
        "current_coverage_pct": _coverage(current_count),
        "quality": stored_rollup["quality"],
    }


def _operator_summary(selected_date, stored, comparison):
    notes = []
    missing = [name for name, rollup in stored.items() if not rollup]
    if missing:
        notes.append(f"Missing rollups: {', '.join(missing)}.")
    for name in ("power", "weather"):
        details = comparison[name]
        if details["rollup_found"] and not details["sample_count_match"]:
            notes.append(
                f"{name.title()} raw sample count changed since rollup: "
                f"{details['stored_sample_count']} stored vs {details['current_sample_count']} current."
            )
        if details["rollup_found"] and details["stored_coverage_pct"] < 75:
            notes.append(f"{name.title()} rollup coverage is below 75%.")
    if stored["power"] and stored["power"]["is_estimated"]:
        notes.append("Power kWh/Rand values are estimated, not confirmed meter totals.")
    if not notes:
        notes.append("Stored daily rollups are present and current counts match.")
    return {
        "headline": f"Daily telemetry rollups for {selected_date.isoformat()}.",
        "notes": notes,
    }


def _parse_rollup_date(value):
    if not value:
        return datetime.now(ZA_TZ).date()
    return date.fromisoformat(str(value))


def _quality(coverage_pct):
    coverage = _num(coverage_pct) or 0
    if coverage >= 95:
        return "complete"
    if coverage >= 75:
        return "usable"
    if coverage > 0:
        return "partial"
    return "missing"


def _coverage(count):
    return round((count / EXPECTED_5MIN_SAMPLES_PER_DAY) * 100, 2)


def _source_metadata():
    return {
        "source": "supabase",
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }


def _num(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
