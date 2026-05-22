import hashlib
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from modules.telemetry.power_service import INGEST_API_KEY_ENV
from services.database_service import DATABASE_URL_ENV


DEFAULT_WEATHER_SOURCE_ID = "weather-station-main"
DEFAULT_FORECAST_SOURCE_ID = "open-meteo-forecast-main"
ZA_TZ = ZoneInfo("Africa/Johannesburg")


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
