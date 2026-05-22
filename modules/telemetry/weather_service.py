import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from modules.telemetry.power_service import INGEST_API_KEY_ENV
from services.database_service import DATABASE_URL_ENV


DEFAULT_WEATHER_SOURCE_ID = "weather-station-main"
DEFAULT_FORECAST_SOURCE_ID = "open-meteo-forecast-main"
ZA_TZ = ZoneInfo("Africa/Johannesburg")
WEATHER_ALERT_SOURCE_IDS = (DEFAULT_WEATHER_SOURCE_ID, DEFAULT_FORECAST_SOURCE_ID)

ALERT_STALE_MINUTES = 30
ALERT_RAIN_TODAY_MM = 2
ALERT_HEAVY_RAIN_RATE_MM_H = 10
ALERT_WIND_SUSTAINED_KMH = 40
ALERT_GUST_HIGH_KMH = 60
ALERT_TEMP_LOW_C = 10
ALERT_TEMP_HIGH_C = 28
ALERT_FORECAST_RAIN_PROBABILITY_PCT = 60
ALERT_FORECAST_RAIN_MM = 3
ALERT_FORECAST_HEAVY_RAIN_MM = 10
ALERT_FORECAST_WIND_KMH = 35
ALERT_FORECAST_GUST_KMH = 50
ALERT_FORECAST_STRONG_GUST_KMH = 65
QUIET_HOURS_START = 21
QUIET_HOURS_END = 6


def ingest_weather_reading(payload, provided_api_key="", database_url=None):
    auth_error = _validate_ingest_request(provided_api_key)
    if auth_error:
        return auth_error

    database_url = _database_url(database_url)
    if not database_url:
        return _not_configured()

    try:
        import psycopg
    except ImportError:
        return _dependency_missing()

    try:
        reading = _normalize_weather_payload(payload)
    except ValueError as exc:
        return _validation_error(str(exc))

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.weather_readings (
                        reading_id, source_id, reading_at, temperature_c, humidity_pct,
                        wind_speed_kmh, wind_gust_kmh, wind_direction_deg, rain_rate_mm_h,
                        rain_today_mm, pressure_hpa, raw_payload
                    )
                    values (
                        %(reading_id)s, %(source_id)s, %(reading_at)s, %(temperature_c)s, %(humidity_pct)s,
                        %(wind_speed_kmh)s, %(wind_gust_kmh)s, %(wind_direction_deg)s, %(rain_rate_mm_h)s,
                        %(rain_today_mm)s, %(pressure_hpa)s, %(raw_payload)s::jsonb
                    )
                    on conflict (source_id, reading_at) do update set
                        temperature_c = excluded.temperature_c,
                        humidity_pct = excluded.humidity_pct,
                        wind_speed_kmh = excluded.wind_speed_kmh,
                        wind_gust_kmh = excluded.wind_gust_kmh,
                        wind_direction_deg = excluded.wind_direction_deg,
                        rain_rate_mm_h = excluded.rain_rate_mm_h,
                        rain_today_mm = excluded.rain_today_mm,
                        pressure_hpa = excluded.pressure_hpa,
                        raw_payload = excluded.raw_payload,
                        ingested_at = now()
                    """,
                    reading,
                )
                cursor.execute(
                    """
                    insert into public.weather_latest_state (
                        source_id, reading_at, temperature_c, humidity_pct,
                        wind_speed_kmh, wind_gust_kmh, wind_direction_deg, rain_rate_mm_h,
                        rain_today_mm, pressure_hpa, flags, summary_status, summary_headline,
                        summary_notes, updated_at
                    )
                    values (
                        %(source_id)s, %(reading_at)s, %(temperature_c)s, %(humidity_pct)s,
                        %(wind_speed_kmh)s, %(wind_gust_kmh)s, %(wind_direction_deg)s, %(rain_rate_mm_h)s,
                        %(rain_today_mm)s, %(pressure_hpa)s, %(flags)s::jsonb, %(summary_status)s,
                        %(summary_headline)s, %(summary_notes)s::jsonb, now()
                    )
                    on conflict (source_id) do update set
                        reading_at = excluded.reading_at,
                        temperature_c = excluded.temperature_c,
                        humidity_pct = excluded.humidity_pct,
                        wind_speed_kmh = excluded.wind_speed_kmh,
                        wind_gust_kmh = excluded.wind_gust_kmh,
                        wind_direction_deg = excluded.wind_direction_deg,
                        rain_rate_mm_h = excluded.rain_rate_mm_h,
                        rain_today_mm = excluded.rain_today_mm,
                        pressure_hpa = excluded.pressure_hpa,
                        flags = excluded.flags,
                        summary_status = excluded.summary_status,
                        summary_headline = excluded.summary_headline,
                        summary_notes = excluded.summary_notes,
                        updated_at = now()
                    where excluded.reading_at >= public.weather_latest_state.reading_at
                    """,
                    reading,
                )
    except Exception as exc:
        return _service_failed("weather_ingest_failed", "Weather telemetry ingest failed.", exc)

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "source_id": reading["source_id"],
        "reading_id": reading["reading_id"],
        "reading_at": reading["reading_at"].isoformat(),
        "source": _source_metadata(writes_to_supabase=True),
    }, 201


def ingest_weather_forecast(payload, provided_api_key="", database_url=None):
    auth_error = _validate_ingest_request(provided_api_key)
    if auth_error:
        return auth_error

    database_url = _database_url(database_url)
    if not database_url:
        return _not_configured()

    try:
        import psycopg
    except ImportError:
        return _dependency_missing()

    try:
        rows = _normalize_forecast_payload(payload)
    except ValueError as exc:
        return _validation_error(str(exc))

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                for row in rows:
                    cursor.execute(
                        """
                        insert into public.weather_forecast_snapshots (
                            forecast_snapshot_id, source_id, forecast_run_at, timezone,
                            forecast_date, offset_days, temp_max_c, temp_min_c,
                            rain_sum_mm, rain_probability_max_pct, wind_max_kmh,
                            gust_max_kmh, flags, raw_payload
                        )
                        values (
                            %(forecast_snapshot_id)s, %(source_id)s, %(forecast_run_at)s, %(timezone)s,
                            %(forecast_date)s, %(offset_days)s, %(temp_max_c)s, %(temp_min_c)s,
                            %(rain_sum_mm)s, %(rain_probability_max_pct)s, %(wind_max_kmh)s,
                            %(gust_max_kmh)s, %(flags)s::jsonb, %(raw_payload)s::jsonb
                        )
                        on conflict (source_id, forecast_run_at, forecast_date) do update set
                            timezone = excluded.timezone,
                            offset_days = excluded.offset_days,
                            temp_max_c = excluded.temp_max_c,
                            temp_min_c = excluded.temp_min_c,
                            rain_sum_mm = excluded.rain_sum_mm,
                            rain_probability_max_pct = excluded.rain_probability_max_pct,
                            wind_max_kmh = excluded.wind_max_kmh,
                            gust_max_kmh = excluded.gust_max_kmh,
                            flags = excluded.flags,
                            raw_payload = excluded.raw_payload,
                            ingested_at = now()
                        """,
                        row,
                    )
    except Exception as exc:
        return _service_failed("weather_forecast_ingest_failed", "Weather forecast ingest failed.", exc)

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "source_id": rows[0]["source_id"],
        "forecast_run_at": rows[0]["forecast_run_at"].isoformat(),
        "rows": len(rows),
        "source": _source_metadata(writes_to_supabase=True),
    }, 201


def get_current_weather_state(database_url=None):
    database_url = _database_url(database_url)
    if not database_url:
        return _not_configured()

    try:
        import psycopg
    except ImportError:
        return _dependency_missing()

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        ts.source_id, ts.display_name, ts.provider, ts.stale_after_minutes,
                        wls.reading_at, wls.temperature_c, wls.humidity_pct,
                        wls.wind_speed_kmh, wls.wind_gust_kmh, wls.wind_direction_deg,
                        wls.rain_rate_mm_h, wls.rain_today_mm, wls.pressure_hpa,
                        wls.flags, wls.summary_status, wls.summary_headline, wls.summary_notes
                    from public.telemetry_sources ts
                    left join public.weather_latest_state wls on wls.source_id = ts.source_id
                    where ts.source_id = %s
                    """,
                    (DEFAULT_WEATHER_SOURCE_ID,),
                )
                row = cursor.fetchone()
    except Exception as exc:
        return _service_failed("weather_current_read_failed", "Current weather telemetry read failed.", exc)

    if not row or not row[4]:
        return {
            "success": False,
            "configured": True,
            "status": "unavailable",
            "message": "No current weather reading is available yet.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 200

    return _format_current_weather_response(row), 200


def get_weather_forecast(days=3, database_url=None):
    days = _bounded_days(days)
    database_url = _database_url(database_url)
    if not database_url:
        return _not_configured()

    try:
        import psycopg
    except ImportError:
        return _dependency_missing()

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select source_id, display_name, provider, stale_after_minutes
                    from public.telemetry_sources
                    where source_id = %s
                    """,
                    (DEFAULT_FORECAST_SOURCE_ID,),
                )
                source_row = cursor.fetchone()
                cursor.execute(
                    """
                    select forecast_run_at, timezone, forecast_date, offset_days,
                           temp_max_c, temp_min_c, rain_sum_mm, rain_probability_max_pct,
                           wind_max_kmh, gust_max_kmh, flags
                    from public.weather_forecast_snapshots
                    where source_id = %s
                      and forecast_run_at = (
                          select max(forecast_run_at)
                          from public.weather_forecast_snapshots
                          where source_id = %s
                      )
                    order by forecast_date asc
                    limit %s
                    """,
                    (DEFAULT_FORECAST_SOURCE_ID, DEFAULT_FORECAST_SOURCE_ID, days),
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return _service_failed("weather_forecast_read_failed", "Weather forecast read failed.", exc)

    if not rows:
        return {
            "success": False,
            "configured": True,
            "status": "unavailable",
            "message": "No forecast snapshot is available yet.",
            "source": _source_metadata(writes_to_supabase=False),
            "window": {"requested_days": days, "returned_days": 0},
        }, 200

    return _format_forecast_response(source_row, rows, days), 200


def get_weather_today_summary(summary_date=None, database_url=None):
    selected_date = _parse_optional_summary_date(summary_date)
    database_url = _database_url(database_url)
    if not database_url:
        return _not_configured()

    try:
        import psycopg
    except ImportError:
        return _dependency_missing()

    start_za = datetime(selected_date.year, selected_date.month, selected_date.day, tzinfo=ZA_TZ)
    end_za = start_za.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_utc = start_za.astimezone(timezone.utc)
    end_utc_exclusive = (start_za.replace(hour=0) + _one_day()).astimezone(timezone.utc)

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select source_id, display_name, provider, stale_after_minutes
                    from public.telemetry_sources
                    where source_id = %s
                    """,
                    (DEFAULT_WEATHER_SOURCE_ID,),
                )
                source_row = cursor.fetchone()
                cursor.execute(
                    """
                    select
                        count(*)::int as reading_count,
                        min(reading_at) as first_reading_at,
                        max(reading_at) as last_reading_at,
                        min(temperature_c) as min_temperature_c,
                        max(temperature_c) as max_temperature_c,
                        avg(temperature_c) as avg_temperature_c,
                        avg(humidity_pct) as avg_humidity_pct,
                        max(wind_speed_kmh) as max_wind_speed_kmh,
                        max(wind_gust_kmh) as max_wind_gust_kmh,
                        max(rain_rate_mm_h) as max_rain_rate_mm_h,
                        max(rain_today_mm) as rain_today_total_mm,
                        bool_or(coalesce(rain_rate_mm_h, 0) > 0) as raining_observed
                    from public.weather_readings
                    where source_id = %s
                      and reading_at >= %s
                      and reading_at < %s
                      and coalesce(raw_payload->>'test', 'false') <> 'true'
                    """,
                    (DEFAULT_WEATHER_SOURCE_ID, start_utc, end_utc_exclusive),
                )
                summary_row = cursor.fetchone()
    except Exception as exc:
        return _service_failed("weather_today_read_failed", "Today weather telemetry read failed.", exc)

    if not summary_row or not summary_row[0]:
        return {
            "success": False,
            "configured": True,
            "status": "unavailable",
            "message": "No weather readings are available for the selected day.",
            "source": _source_metadata(writes_to_supabase=False),
            "window": {
                "date": selected_date.isoformat(),
                "timezone": "Africa/Johannesburg",
                "returned_readings": 0,
            },
        }, 200

    return _format_today_weather_response(source_row, summary_row, selected_date, start_za, end_za), 200


def evaluate_weather_alerts(payload=None, provided_api_key="", database_url=None):
    auth_error = _validate_ingest_request(provided_api_key)
    if auth_error:
        return auth_error

    database_url = _database_url(database_url)
    if not database_url:
        return _not_configured()

    try:
        import psycopg
    except ImportError:
        return _dependency_missing()

    options = payload if isinstance(payload, dict) else {}
    dry_run = bool(options.get("dry_run", False))
    now_utc = datetime.now(timezone.utc)

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                context = _read_weather_alert_context(cursor, now_utc)
                candidates = _build_weather_alert_candidates(context, now_utc)
                recent_alerts = _read_recent_weather_alerts(cursor)
                evaluation = _apply_weather_alert_policy(candidates, recent_alerts, now_utc)

                written_alerts = []
                if not dry_run:
                    for alert in evaluation["sendable_alerts"]:
                        _insert_weather_alert(cursor, alert)
                        written_alerts.append(alert["alert_id"])
    except Exception as exc:
        return _service_failed("weather_alert_evaluation_failed", "Weather alert evaluation failed.", exc)

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dry_run" if dry_run else "apply",
        "source": {
            "source": "supabase",
            "writes_to_sheets": False,
            "writes_to_supabase": not dry_run,
        },
        "evaluated_at": now_utc.isoformat(),
        "quiet_hours": {
            "timezone": "Africa/Johannesburg",
            "start_hour": QUIET_HOURS_START,
            "end_hour": QUIET_HOURS_END,
            "active": _is_quiet_hours(now_utc),
        },
        "candidate_count": len(candidates),
        "sendable_count": len(evaluation["sendable_alerts"]),
        "held_count": len(evaluation["held_alerts"]),
        "suppressed_count": len(evaluation["suppressed_alerts"]),
        "written_alert_ids": written_alerts,
        "sendable_alerts": evaluation["sendable_alerts"],
        "held_alerts": evaluation["held_alerts"],
        "suppressed_alerts": evaluation["suppressed_alerts"],
        "rules": _weather_alert_rule_defaults(),
    }, 200


def _normalize_weather_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")
    reading_at = _parse_datetime(payload.get("reading_at") or payload.get("timestamp_za") or payload.get("timestamp"))
    source_id = str(payload.get("source_id") or DEFAULT_WEATHER_SOURCE_ID).strip()
    reading = {
        "source_id": source_id,
        "reading_at": reading_at,
        "temperature_c": _number_or_none(payload.get("temperature_c", payload.get("temp_c"))),
        "humidity_pct": _number_or_none(payload.get("humidity_pct", payload.get("humidity"))),
        "wind_speed_kmh": _number_or_none(payload.get("wind_speed_kmh", payload.get("wind_kph"))),
        "wind_gust_kmh": _number_or_none(payload.get("wind_gust_kmh", payload.get("wind_gust"))),
        "wind_direction_deg": _number_or_none(payload.get("wind_direction_deg", payload.get("winddir"))),
        "rain_rate_mm_h": _number_or_none(payload.get("rain_rate_mm_h", payload.get("precipRate"))),
        "rain_today_mm": _number_or_none(payload.get("rain_today_mm", payload.get("precipTotal"))),
        "pressure_hpa": _number_or_none(payload.get("pressure_hpa", payload.get("pressure"))),
        "raw_payload": _json_param(payload.get("raw_payload", payload)),
    }
    flags = _weather_flags(reading)
    summary = _weather_summary(flags, reading)
    reading.update({
        "reading_id": _hash_id("WTH", source_id, reading_at.isoformat()),
        "flags": json.dumps(flags, separators=(",", ":")),
        "summary_status": summary["status"],
        "summary_headline": summary["headline"],
        "summary_notes": json.dumps(summary["operator_notes"], separators=(",", ":")),
    })
    return reading


def _normalize_forecast_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")
    source_id = str(payload.get("source_id") or DEFAULT_FORECAST_SOURCE_ID).strip()
    forecast_run_at = _parse_datetime(payload.get("forecast_run_at") or payload.get("run_timestamp") or payload.get("timestamp"))
    timezone_name = str(payload.get("timezone") or "Africa/Johannesburg")
    periods = payload.get("days") or payload.get("periods") or []
    if not periods:
        raise ValueError("Forecast payload must include days.")

    rows = []
    for index, period in enumerate(periods):
        forecast_date = _parse_date(period.get("forecast_date") or period.get("date"))
        row = {
            "source_id": source_id,
            "forecast_run_at": forecast_run_at,
            "timezone": timezone_name,
            "forecast_date": forecast_date,
            "offset_days": int(period.get("offset_days", index)),
            "temp_max_c": _number_or_none(period.get("temp_max_c")),
            "temp_min_c": _number_or_none(period.get("temp_min_c")),
            "rain_sum_mm": _number_or_none(period.get("rain_sum_mm")),
            "rain_probability_max_pct": _number_or_none(period.get("rain_probability_max_pct", period.get("rain_prob_max_pct"))),
            "wind_max_kmh": _number_or_none(period.get("wind_max_kmh")),
            "gust_max_kmh": _number_or_none(period.get("gust_max_kmh")),
            "raw_payload": _json_param(period),
        }
        flags = _forecast_flags(row)
        row["flags"] = json.dumps(flags, separators=(",", ":"))
        row["forecast_snapshot_id"] = _hash_id("FCST", source_id, forecast_run_at.isoformat(), forecast_date.isoformat())
        rows.append(row)
    return rows


def _format_current_weather_response(row):
    (
        source_id, display_name, provider, stale_after_minutes, reading_at,
        temperature, humidity, wind_speed, wind_gust, wind_direction,
        rain_rate, rain_today, pressure, flags, summary_status, summary_headline, summary_notes,
    ) = row
    age_minutes = max(0, int((datetime.now(timezone.utc) - reading_at.astimezone(timezone.utc)).total_seconds() // 60))
    is_stale = age_minutes > int(stale_after_minutes)
    flags = dict(flags or {})
    flags["station_stale"] = is_stale
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "source": {
            "source": "supabase",
            "source_id": source_id,
            "source_name": display_name,
            "provider": provider,
            "last_reading_at": reading_at.isoformat(),
            "data_age_minutes": age_minutes,
            "is_stale": is_stale,
            "stale_after_minutes": stale_after_minutes,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
        "current": {
            "temperature_c": _json_value(temperature),
            "humidity_pct": _json_value(humidity),
            "wind_speed_kmh": _json_value(wind_speed),
            "wind_gust_kmh": _json_value(wind_gust),
            "wind_direction_deg": _json_value(wind_direction),
            "rain_rate_mm_h": _json_value(rain_rate),
            "rain_today_mm": _json_value(rain_today),
            "pressure_hpa": _json_value(pressure),
        },
        "flags": flags,
        "summary": {
            "status": "stale" if is_stale else summary_status,
            "headline": "Weather station data is stale. Showing the last known state." if is_stale else summary_headline,
            "operator_notes": summary_notes or [],
        },
        "units": _weather_units(),
    }


def _format_forecast_response(source_row, rows, requested_days):
    source_id, display_name, provider, stale_after_minutes = source_row or (
        DEFAULT_FORECAST_SOURCE_ID, "Amadeus Forecast", "open_meteo", 360
    )
    forecast_run_at = rows[0][0]
    age_minutes = max(0, int((datetime.now(timezone.utc) - forecast_run_at.astimezone(timezone.utc)).total_seconds() // 60))
    is_stale = age_minutes > int(stale_after_minutes)
    days = []
    for row in rows:
        _, timezone_name, forecast_date, offset_days, temp_max, temp_min, rain_sum, rain_prob, wind_max, gust_max, flags = row
        flags = dict(flags or {})
        flags["forecast_stale"] = is_stale
        days.append({
            "forecast_date": forecast_date.isoformat(),
            "offset_days": offset_days,
            "temp_max_c": _json_value(temp_max),
            "temp_min_c": _json_value(temp_min),
            "rain_sum_mm": _json_value(rain_sum),
            "rain_probability_max_pct": _json_value(rain_prob),
            "wind_max_kmh": _json_value(wind_max),
            "gust_max_kmh": _json_value(gust_max),
            "flags": flags,
        })
    summary = _forecast_summary(days, is_stale)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "source": {
            "source": "supabase",
            "source_id": source_id,
            "source_name": display_name,
            "provider": provider,
            "last_forecast_run_at": forecast_run_at.isoformat(),
            "data_age_minutes": age_minutes,
            "is_stale": is_stale,
            "stale_after_minutes": stale_after_minutes,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
        "window": {
            "requested_days": requested_days,
            "returned_days": len(days),
            "timezone": rows[0][1],
        },
        "days": days,
        "summary": summary,
        "units": {"temperature": "C", "wind": "km/h", "rain": "mm", "probability": "%"},
    }


def _format_today_weather_response(source_row, row, selected_date, start_za, end_za):
    source_id, display_name, provider, stale_after_minutes = source_row or (
        DEFAULT_WEATHER_SOURCE_ID, "Amadeus Local Weather Station", "weather_com_pws", 30
    )
    (
        reading_count, first_reading_at, last_reading_at, min_temp, max_temp, avg_temp,
        avg_humidity, max_wind_speed, max_wind_gust, max_rain_rate, rain_total,
        raining_observed,
    ) = row
    now_za = datetime.now(ZA_TZ)
    is_today = selected_date == now_za.date()
    expected_until = min(now_za, end_za) if is_today else end_za
    expected_samples = max(1, int((expected_until - start_za).total_seconds() // (5 * 60)) + 1)
    coverage_pct = round((reading_count / expected_samples) * 100, 1)
    flags = {
        "rain_observed": bool(raining_observed),
        "rain_today": (rain_total or 0) > 0,
        "high_wind": (max_wind_speed or 0) >= 30,
        "gust_risk": (max_wind_gust or 0) >= 40,
        "hot": max_temp is not None and max_temp >= 32,
        "cold": min_temp is not None and min_temp <= 5,
        "irrigation_caution": (rain_total or 0) >= 0.5 or (max_wind_speed or 0) >= 30 or (max_wind_gust or 0) >= 40,
    }
    summary = _today_weather_summary(flags, row, coverage_pct)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "source": {
            "source": "supabase",
            "source_id": source_id,
            "source_name": display_name,
            "provider": provider,
            "stale_after_minutes": stale_after_minutes,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
        "window": {
            "date": selected_date.isoformat(),
            "timezone": "Africa/Johannesburg",
            "first_reading_at": first_reading_at.isoformat() if first_reading_at else None,
            "last_reading_at": last_reading_at.isoformat() if last_reading_at else None,
            "reading_count": reading_count,
            "expected_samples": expected_samples,
            "coverage_pct": coverage_pct,
            "sample_interval_minutes_assumed": 5,
        },
        "temperature": {
            "min_c": _json_value(min_temp),
            "max_c": _json_value(max_temp),
            "avg_c": _rounded_json_value(avg_temp),
        },
        "humidity": {
            "avg_pct": _rounded_json_value(avg_humidity),
        },
        "wind": {
            "max_speed_kmh": _json_value(max_wind_speed),
            "max_gust_kmh": _json_value(max_wind_gust),
        },
        "rain": {
            "total_mm": _json_value(rain_total),
            "max_rate_mm_h": _json_value(max_rain_rate),
            "raining_observed": bool(raining_observed),
        },
        "flags": flags,
        "summary": summary,
        "units": _weather_units(),
        "limitations": [
            "This endpoint summarizes station samples for the selected local day.",
            "Rain total uses the highest station daily rain value seen in the selected day.",
        ],
    }


def _weather_flags(reading):
    rain_rate = reading.get("rain_rate_mm_h") or 0
    rain_today = reading.get("rain_today_mm") or 0
    wind_speed = reading.get("wind_speed_kmh") or 0
    wind_gust = reading.get("wind_gust_kmh") or 0
    temperature = reading.get("temperature_c")
    return {
        "station_stale": False,
        "raining_now": rain_rate > 0,
        "rain_today": rain_today > 0,
        "high_wind": wind_speed >= 30,
        "gust_risk": wind_gust >= 40,
        "hot": temperature is not None and temperature >= 32,
        "cold": temperature is not None and temperature <= 5,
        "irrigation_caution": rain_rate > 0 or rain_today >= 0.5 or wind_speed >= 30 or wind_gust >= 40,
    }


def _forecast_flags(row):
    rain_sum = row.get("rain_sum_mm") or 0
    rain_probability = row.get("rain_probability_max_pct") or 0
    wind_max = row.get("wind_max_kmh") or 0
    gust_max = row.get("gust_max_kmh") or 0
    temp_max = row.get("temp_max_c")
    temp_min = row.get("temp_min_c")
    return {
        "rain_expected": rain_sum > 0 or rain_probability >= 30,
        "strong_wind": wind_max >= 30,
        "gust_risk": gust_max >= 40,
        "hot": temp_max is not None and temp_max >= 32,
        "cold": temp_min is not None and temp_min <= 5,
        "irrigation_caution": rain_sum > 0 or rain_probability >= 30 or wind_max >= 30 or gust_max >= 40,
        "work_caution": rain_sum >= 5 or wind_max >= 30 or gust_max >= 40 or (temp_max is not None and temp_max >= 32) or (temp_min is not None and temp_min <= 5),
    }


def _weather_summary(flags, reading):
    status = "ok"
    headline = "Weather station data is current."
    if flags["gust_risk"] or flags["high_wind"]:
        status = "warning"
        headline = "Wind conditions need attention."
    elif flags["raining_now"] or flags["rain_today"] or flags["irrigation_caution"]:
        status = "caution"
        headline = "Weather is usable, but rain or irrigation caution is showing."
    notes = []
    if reading.get("temperature_c") is not None:
        notes.append(f"Temperature is {reading['temperature_c']:g} C.")
    if reading.get("rain_today_mm") is not None:
        notes.append(f"Rain today is {reading['rain_today_mm']:g} mm.")
    if reading.get("wind_speed_kmh") is not None:
        notes.append(f"Wind is {reading['wind_speed_kmh']:g} km/h.")
    if flags["irrigation_caution"]:
        notes.append("Irrigation may need caution based on rain or wind conditions.")
    return {"status": status, "headline": headline, "operator_notes": notes}


def _forecast_summary(days, is_stale):
    rain_days = [day for day in days if day["flags"].get("rain_expected")]
    wind_days = [day for day in days if day["flags"].get("strong_wind") or day["flags"].get("gust_risk")]
    status = "stale" if is_stale else ("caution" if rain_days or wind_days else "ok")
    headline = "Forecast data is stale. Showing the last known forecast." if is_stale else "Forecast looks clear for the selected window."
    if not is_stale and rain_days:
        headline = f"Rain is possible on {len(rain_days)} day(s) in the selected window."
    if not is_stale and wind_days:
        headline = "Wind may need attention in the selected window."
    notes = []
    if rain_days:
        notes.append(f"Rain is expected or possible on {len(rain_days)} day(s).")
    if wind_days:
        notes.append(f"Wind caution appears on {len(wind_days)} day(s).")
    if not notes:
        notes.append("No major rain or wind warning is showing in the selected window.")
    return {"status": status, "headline": headline, "operator_notes": notes}


def _today_weather_summary(flags, row, coverage_pct):
    reading_count = row[0]
    max_temp = row[4]
    max_wind = row[7]
    max_gust = row[8]
    rain_total = row[10]
    status = "ok"
    headline = "Weather readings are available for today."
    if flags["gust_risk"] or flags["high_wind"]:
        status = "warning"
        headline = "Wind conditions need attention today."
    elif flags["rain_today"] or flags["rain_observed"] or flags["irrigation_caution"]:
        status = "caution"
        headline = "Rain or irrigation caution is showing today."
    notes = [
        f"{reading_count} readings found for the selected day.",
        f"Coverage is about {coverage_pct:g}% of expected 5-minute samples.",
    ]
    if max_temp is not None:
        notes.append(f"Maximum temperature was {_format_number(max_temp)} C.")
    if rain_total is not None:
        notes.append(f"Rain total so far is {_format_number(rain_total)} mm.")
    if max_wind is not None:
        notes.append(f"Maximum wind speed was {_format_number(max_wind)} km/h.")
    if max_gust is not None:
        notes.append(f"Maximum gust was {_format_number(max_gust)} km/h.")
    return {"status": status, "headline": headline, "operator_notes": notes}


def _read_weather_alert_context(cursor, now_utc):
    cursor.execute(
        """
        select
            wls.source_id, ts.display_name, ts.provider, ts.stale_after_minutes,
            wls.reading_at, wls.temperature_c, wls.humidity_pct,
            wls.wind_speed_kmh, wls.wind_gust_kmh, wls.wind_direction_deg,
            wls.rain_rate_mm_h, wls.rain_today_mm, wls.pressure_hpa
        from public.weather_latest_state wls
        join public.telemetry_sources ts on ts.source_id = wls.source_id
        where wls.source_id = %s
        """,
        (DEFAULT_WEATHER_SOURCE_ID,),
    )
    latest_row = cursor.fetchone()
    cursor.execute(
        """
        select reading_at, wind_speed_kmh
        from public.weather_readings
        where source_id = %s
          and reading_at >= %s
          and coalesce(raw_payload->>'test', 'false') <> 'true'
        order by reading_at desc
        limit 6
        """,
        (DEFAULT_WEATHER_SOURCE_ID, now_utc - timedelta(minutes=45)),
    )
    recent_wind_rows = cursor.fetchall()
    cursor.execute(
        """
        select
            forecast_run_at, forecast_date, offset_days, temp_max_c, temp_min_c,
            rain_sum_mm, rain_probability_max_pct, wind_max_kmh, gust_max_kmh
        from public.weather_forecast_snapshots
        where source_id = %s
          and forecast_run_at = (
              select max(forecast_run_at)
              from public.weather_forecast_snapshots
              where source_id = %s
          )
          and offset_days <= 3
        order by forecast_date asc
        """,
        (DEFAULT_FORECAST_SOURCE_ID, DEFAULT_FORECAST_SOURCE_ID),
    )
    forecast_rows = cursor.fetchall()
    return {
        "latest": latest_row,
        "recent_wind_rows": recent_wind_rows,
        "forecast_rows": forecast_rows,
    }


def _read_recent_weather_alerts(cursor):
    cursor.execute(
        """
        select alert_type, severity, message, event_at, status, details
        from public.telemetry_alerts
        where area in ('weather', 'forecast')
          and event_at >= now() - interval '24 hours'
        order by event_at desc
        """,
    )
    return cursor.fetchall()


def _build_weather_alert_candidates(context, now_utc):
    candidates = []
    latest = context.get("latest")
    if latest:
        (
            source_id, source_name, provider, stale_after_minutes, reading_at,
            temperature, _humidity, wind_speed, wind_gust, _wind_direction,
            rain_rate, rain_today, _pressure,
        ) = latest
        age_minutes = max(0, int((now_utc - reading_at.astimezone(timezone.utc)).total_seconds() // 60))
        stale_threshold = int(stale_after_minutes or ALERT_STALE_MINUTES)

        if age_minutes > stale_threshold:
            candidates.append(_weather_alert_candidate(
                "station_stale",
                "STATION_STALE",
                "critical",
                source_id,
                source_name,
                reading_at,
                240,
                f"Weather station has not logged for {age_minutes} minutes. Last reading: {_format_alert_time(reading_at)}.",
                {"age_minutes": age_minutes, "threshold_minutes": stale_threshold, "provider": provider},
                bypass_quiet_hours=True,
            ))
        if _num(rain_rate) > 0:
            candidates.append(_weather_alert_candidate(
                "raining_now",
                "RAINING_NOW",
                "warning",
                source_id,
                source_name,
                reading_at,
                60,
                f"It is raining at Amadeus Farm. Rain rate: {_format_number(rain_rate)} mm/h.",
                {"rain_rate_mm_h": _json_value(rain_rate)},
            ))
        if _num(rain_rate) >= ALERT_HEAVY_RAIN_RATE_MM_H:
            candidates.append(_weather_alert_candidate(
                "heavy_rain_now",
                "HEAVY_RAIN_NOW",
                "critical",
                source_id,
                source_name,
                reading_at,
                60,
                f"Heavy rain is showing now. Rain rate: {_format_number(rain_rate)} mm/h.",
                {"rain_rate_mm_h": _json_value(rain_rate), "threshold_mm_h": ALERT_HEAVY_RAIN_RATE_MM_H},
                bypass_quiet_hours=True,
            ))
        if _num(rain_today) >= ALERT_RAIN_TODAY_MM:
            candidates.append(_weather_alert_candidate(
                "rain_today",
                "RAIN_TODAY",
                "info",
                source_id,
                source_name,
                reading_at,
                180,
                f"Rain total today is {_format_number(rain_today)} mm.",
                {"rain_today_mm": _json_value(rain_today), "threshold_mm": ALERT_RAIN_TODAY_MM},
            ))
        if _num(wind_gust) > ALERT_GUST_HIGH_KMH:
            candidates.append(_weather_alert_candidate(
                "high_gust",
                "HIGH_GUST",
                "critical",
                source_id,
                source_name,
                reading_at,
                120,
                f"High wind gust detected. Gust: {_format_number(wind_gust)} km/h.",
                {"wind_gust_kmh": _json_value(wind_gust), "threshold_kmh": ALERT_GUST_HIGH_KMH},
                bypass_quiet_hours=True,
            ))
        if temperature is not None and _num(temperature) < ALERT_TEMP_LOW_C:
            candidates.append(_weather_alert_candidate(
                "low_temperature",
                "LOW_TEMPERATURE",
                "critical",
                source_id,
                source_name,
                reading_at,
                120,
                f"Low temperature detected. Temperature: {_format_number(temperature)} C.",
                {"temperature_c": _json_value(temperature), "threshold_c": ALERT_TEMP_LOW_C},
                bypass_quiet_hours=True,
            ))
        if temperature is not None and _num(temperature) > ALERT_TEMP_HIGH_C:
            candidates.append(_weather_alert_candidate(
                "high_temperature",
                "HIGH_TEMPERATURE",
                "warning",
                source_id,
                source_name,
                reading_at,
                120,
                f"High temperature detected. Temperature: {_format_number(temperature)} C.",
                {"temperature_c": _json_value(temperature), "threshold_c": ALERT_TEMP_HIGH_C},
            ))

    if _has_sustained_wind(context.get("recent_wind_rows", [])):
        latest_event_at = context["recent_wind_rows"][0][0]
        candidates.append(_weather_alert_candidate(
            "high_wind_sustained",
            "HIGH_WIND_SUSTAINED",
            "critical",
            DEFAULT_WEATHER_SOURCE_ID,
            "Amadeus Local Weather Station",
            latest_event_at,
            120,
            f"Sustained wind above {ALERT_WIND_SUSTAINED_KMH} km/h detected across consecutive readings.",
            {"threshold_kmh": ALERT_WIND_SUSTAINED_KMH},
            bypass_quiet_hours=True,
        ))

    for candidate in _forecast_alert_candidates(context.get("forecast_rows", [])):
        candidates.append(candidate)
    return candidates


def _forecast_alert_candidates(rows):
    candidates = []
    for row in rows:
        forecast_run_at, forecast_date, offset_days, temp_max, temp_min, rain_sum, rain_prob, wind_max, gust_max = row
        label = forecast_date.isoformat() if hasattr(forecast_date, "isoformat") else str(forecast_date)
        next_12h = int(offset_days or 0) == 0
        if _num(rain_prob) >= ALERT_FORECAST_RAIN_PROBABILITY_PCT or _num(rain_sum) >= ALERT_FORECAST_RAIN_MM:
            candidates.append(_weather_alert_candidate(
                f"forecast_rain_{label}",
                "FORECAST_RAIN",
                "warning",
                DEFAULT_FORECAST_SOURCE_ID,
                "Amadeus Forecast",
                forecast_run_at,
                720,
                f"Forecast rain risk for {label}: {_format_number(rain_sum)} mm, probability {_format_number(rain_prob)}%.",
                {"forecast_date": label, "rain_sum_mm": _json_value(rain_sum), "rain_probability_max_pct": _json_value(rain_prob)},
            ))
        if _num(rain_sum) >= ALERT_FORECAST_HEAVY_RAIN_MM:
            candidates.append(_weather_alert_candidate(
                f"forecast_heavy_rain_{label}",
                "FORECAST_HEAVY_RAIN",
                "critical",
                DEFAULT_FORECAST_SOURCE_ID,
                "Amadeus Forecast",
                forecast_run_at,
                720,
                f"Forecast heavy rain risk for {label}: {_format_number(rain_sum)} mm.",
                {"forecast_date": label, "rain_sum_mm": _json_value(rain_sum), "threshold_mm": ALERT_FORECAST_HEAVY_RAIN_MM},
                bypass_quiet_hours=next_12h,
            ))
        if _num(gust_max) >= ALERT_FORECAST_GUST_KMH or _num(wind_max) >= ALERT_FORECAST_WIND_KMH:
            candidates.append(_weather_alert_candidate(
                f"forecast_wind_{label}",
                "FORECAST_WIND",
                "warning",
                DEFAULT_FORECAST_SOURCE_ID,
                "Amadeus Forecast",
                forecast_run_at,
                720,
                f"Forecast wind risk for {label}: wind {_format_number(wind_max)} km/h, gust {_format_number(gust_max)} km/h.",
                {"forecast_date": label, "wind_max_kmh": _json_value(wind_max), "gust_max_kmh": _json_value(gust_max)},
            ))
        if _num(gust_max) >= ALERT_FORECAST_STRONG_GUST_KMH:
            candidates.append(_weather_alert_candidate(
                f"forecast_strong_wind_{label}",
                "FORECAST_STRONG_WIND",
                "critical",
                DEFAULT_FORECAST_SOURCE_ID,
                "Amadeus Forecast",
                forecast_run_at,
                720,
                f"Forecast strong wind risk for {label}: gust {_format_number(gust_max)} km/h.",
                {"forecast_date": label, "gust_max_kmh": _json_value(gust_max), "threshold_kmh": ALERT_FORECAST_STRONG_GUST_KMH},
                bypass_quiet_hours=next_12h,
            ))
    return candidates


def _weather_alert_candidate(alert_key, alert_type, severity, source_id, source_name, event_at, cooldown_min, message, details, bypass_quiet_hours=False):
    event_at = event_at if isinstance(event_at, datetime) else datetime.now(timezone.utc)
    event_at_utc = event_at.astimezone(timezone.utc)
    alert = {
        "alert_id": _hash_id("ALT", alert_key, event_at_utc.isoformat()),
        "source_id": source_id,
        "source_name": source_name,
        "area": "forecast" if source_id == DEFAULT_FORECAST_SOURCE_ID else "weather",
        "alert_key": alert_key,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "event_at": event_at_utc.isoformat(),
        "cooldown_min": cooldown_min,
        "bypass_quiet_hours": bypass_quiet_hours,
        "details": {
            **details,
            "alert_key": alert_key,
            "cooldown_min": cooldown_min,
            "bypass_quiet_hours": bypass_quiet_hours,
        },
    }
    return alert


def _apply_weather_alert_policy(candidates, recent_alerts, now_utc):
    recent_by_key = {}
    for alert_type, severity, _message, event_at, status, details in recent_alerts:
        details = _dict_or_empty(details)
        key = details.get("alert_key") or alert_type
        if key not in recent_by_key:
            recent_by_key[key] = {
                "alert_type": alert_type,
                "severity": severity,
                "event_at": event_at,
                "status": status,
                "details": details,
            }

    quiet = _is_quiet_hours(now_utc)
    sendable = []
    held = []
    suppressed = []
    for candidate in candidates:
        recent = recent_by_key.get(candidate["alert_key"])
        if recent and not _cooldown_expired(candidate, recent, now_utc):
            suppressed.append({**candidate, "suppression_reason": "cooldown_active"})
            continue
        if quiet and not candidate["bypass_quiet_hours"]:
            held.append({**candidate, "hold_reason": "quiet_hours"})
            continue
        sendable.append(candidate)
    return {"sendable_alerts": sendable, "held_alerts": held, "suppressed_alerts": suppressed}


def _insert_weather_alert(cursor, alert):
    cursor.execute(
        """
        insert into public.telemetry_alerts (
            alert_id, source_id, area, alert_type, severity, message, event_at, status, details
        )
        values (
            %(alert_id)s, %(source_id)s, %(area)s, %(alert_type)s, %(severity)s,
            %(message)s, %(event_at)s, 'Open', %(details)s::jsonb
        )
        on conflict (alert_id) do nothing
        """,
        {
            "alert_id": alert["alert_id"],
            "source_id": alert["source_id"],
            "area": alert["area"],
            "alert_type": alert["alert_type"],
            "severity": alert["severity"],
            "message": alert["message"],
            "event_at": alert["event_at"],
            "details": json.dumps(alert["details"], separators=(",", ":")),
        },
    )


def _cooldown_expired(candidate, recent, now_utc):
    event_at = recent.get("event_at")
    if not isinstance(event_at, datetime):
        return True
    elapsed_minutes = (now_utc - event_at.astimezone(timezone.utc)).total_seconds() / 60
    if elapsed_minutes >= int(candidate["cooldown_min"]):
        return True
    severity_rank = {"info": 1, "warning": 2, "critical": 3}
    return severity_rank.get(candidate["severity"], 0) > severity_rank.get(recent.get("severity"), 0)


def _has_sustained_wind(rows):
    normalized = [
        (reading_at, _num(wind_speed))
        for reading_at, wind_speed in rows
        if reading_at is not None and _num(wind_speed) is not None
    ]
    normalized.sort(key=lambda item: item[0], reverse=True)
    if len(normalized) < 2:
        return False
    latest, previous = normalized[0], normalized[1]
    diff_minutes = abs((latest[0] - previous[0]).total_seconds()) / 60
    return diff_minutes <= 12 and latest[1] > ALERT_WIND_SUSTAINED_KMH and previous[1] > ALERT_WIND_SUSTAINED_KMH


def _is_quiet_hours(now_utc):
    hour = now_utc.astimezone(ZA_TZ).hour
    return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END


def _weather_alert_rule_defaults():
    return {
        "station_stale_minutes": ALERT_STALE_MINUTES,
        "rain_today_mm": ALERT_RAIN_TODAY_MM,
        "heavy_rain_rate_mm_h": ALERT_HEAVY_RAIN_RATE_MM_H,
        "wind_sustained_kmh": ALERT_WIND_SUSTAINED_KMH,
        "gust_high_kmh": ALERT_GUST_HIGH_KMH,
        "temperature_low_c": ALERT_TEMP_LOW_C,
        "temperature_high_c": ALERT_TEMP_HIGH_C,
        "forecast_rain_probability_pct": ALERT_FORECAST_RAIN_PROBABILITY_PCT,
        "forecast_rain_mm": ALERT_FORECAST_RAIN_MM,
        "forecast_heavy_rain_mm": ALERT_FORECAST_HEAVY_RAIN_MM,
        "forecast_wind_kmh": ALERT_FORECAST_WIND_KMH,
        "forecast_gust_kmh": ALERT_FORECAST_GUST_KMH,
        "forecast_strong_gust_kmh": ALERT_FORECAST_STRONG_GUST_KMH,
    }


def _num(value):
    if value is None:
        return 0
    return float(value)


def _format_alert_time(value):
    if not isinstance(value, datetime):
        return "unknown"
    return value.astimezone(ZA_TZ).strftime("%Y-%m-%d %H:%M")


def _dict_or_empty(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _validate_ingest_request(provided_api_key):
    configured_key = os.getenv(INGEST_API_KEY_ENV, "").strip()
    if not configured_key:
        return {
            "success": False,
            "configured": False,
            "status": "ingest_key_not_configured",
            "message": f"{INGEST_API_KEY_ENV} is not configured.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 503
    if not provided_api_key or provided_api_key.strip() != configured_key:
        return {
            "success": False,
            "configured": True,
            "status": "unauthorized",
            "message": "Telemetry ingest key is invalid.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 401
    return None


def _database_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _not_configured():
    return {
        "success": False,
        "configured": False,
        "status": "not_configured",
        "message": f"{DATABASE_URL_ENV} is not configured.",
        "source": _source_metadata(writes_to_supabase=False),
    }, 503


def _dependency_missing():
    return {
        "success": False,
        "configured": True,
        "status": "dependency_missing",
        "message": "Python database dependency is not installed.",
        "source": _source_metadata(writes_to_supabase=False),
    }, 500


def _validation_error(message):
    return {
        "success": False,
        "configured": True,
        "status": "validation_failed",
        "errors": [message],
        "source": _source_metadata(writes_to_supabase=False),
    }, 400


def _service_failed(status, message, exc):
    return {
        "success": False,
        "configured": True,
        "status": status,
        "message": message,
        "error_type": exc.__class__.__name__,
        "source": _source_metadata(writes_to_supabase=False),
    }, 503


def _parse_datetime(value):
    if not value:
        raise ValueError("reading_at, forecast_run_at, or timestamp is required.")
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Timestamp must be an ISO datetime.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZA_TZ)
    return parsed


def _parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        raise ValueError("forecast_date is required.")
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError("forecast_date must be an ISO date.") from exc


def _parse_optional_summary_date(value):
    if not value:
        return datetime.now(ZA_TZ).date()
    return _parse_date(value)


def _number_or_none(value):
    if value in (None, ""):
        return None
    return float(value)


def _bounded_days(value):
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = 3
    return max(1, min(days, 10))


def _hash_id(prefix, *parts):
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def _json_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _rounded_json_value(value):
    value = _json_value(value)
    if isinstance(value, float):
        return round(value, 2)
    return value


def _format_number(value):
    value = _json_value(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _json_param(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def _source_metadata(writes_to_supabase):
    return {
        "source": "supabase",
        "writes_to_sheets": False,
        "writes_to_supabase": writes_to_supabase,
    }


def _weather_units():
    return {
        "temperature": "C",
        "wind": "km/h",
        "rain": "mm",
        "rain_rate": "mm/h",
        "pressure": "hPa",
        "humidity": "%",
    }
