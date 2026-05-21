import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.database_service import DATABASE_URL_ENV


INGEST_API_KEY_ENV = "TELEMETRY_INGEST_API_KEY"
DEFAULT_POWER_SOURCE_ID = "sunsynk-main-inverter"
ZA_TZ = ZoneInfo("Africa/Johannesburg")


def ingest_power_reading(payload, provided_api_key="", database_url=None):
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

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 500

    try:
        reading = _normalize_power_payload(payload)
    except ValueError as exc:
        return {
            "success": False,
            "configured": True,
            "status": "validation_failed",
            "errors": [str(exc)],
            "source": _source_metadata(writes_to_supabase=False),
        }, 400

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.power_readings_5min (
                        reading_id,
                        source_id,
                        reading_at,
                        battery_soc_pct,
                        battery_power_w,
                        solar_power_w,
                        pv1_power_w,
                        pv2_power_w,
                        load_power_w,
                        grid_power_w,
                        generator_power_w,
                        inverter_output_w,
                        grid_active,
                        generator_active,
                        battery_charging,
                        battery_discharging,
                        raw_payload
                    )
                    values (
                        %(reading_id)s,
                        %(source_id)s,
                        %(reading_at)s,
                        %(battery_soc_pct)s,
                        %(battery_power_w)s,
                        %(solar_power_w)s,
                        %(pv1_power_w)s,
                        %(pv2_power_w)s,
                        %(load_power_w)s,
                        %(grid_power_w)s,
                        %(generator_power_w)s,
                        %(inverter_output_w)s,
                        %(grid_active)s,
                        %(generator_active)s,
                        %(battery_charging)s,
                        %(battery_discharging)s,
                        %(raw_payload)s::jsonb
                    )
                    on conflict (source_id, reading_at) do update set
                        battery_soc_pct = excluded.battery_soc_pct,
                        battery_power_w = excluded.battery_power_w,
                        solar_power_w = excluded.solar_power_w,
                        pv1_power_w = excluded.pv1_power_w,
                        pv2_power_w = excluded.pv2_power_w,
                        load_power_w = excluded.load_power_w,
                        grid_power_w = excluded.grid_power_w,
                        generator_power_w = excluded.generator_power_w,
                        inverter_output_w = excluded.inverter_output_w,
                        grid_active = excluded.grid_active,
                        generator_active = excluded.generator_active,
                        battery_charging = excluded.battery_charging,
                        battery_discharging = excluded.battery_discharging,
                        raw_payload = excluded.raw_payload,
                        ingested_at = now()
                    """,
                    reading,
                )
                cursor.execute(
                    """
                    insert into public.power_latest_state (
                        source_id,
                        reading_at,
                        battery_soc_pct,
                        battery_power_w,
                        solar_power_w,
                        pv1_power_w,
                        pv2_power_w,
                        load_power_w,
                        grid_power_w,
                        generator_power_w,
                        inverter_output_w,
                        battery_state,
                        grid_state,
                        generator_state,
                        flags,
                        summary_status,
                        summary_headline,
                        summary_notes,
                        updated_at
                    )
                    values (
                        %(source_id)s,
                        %(reading_at)s,
                        %(battery_soc_pct)s,
                        %(battery_power_w)s,
                        %(solar_power_w)s,
                        %(pv1_power_w)s,
                        %(pv2_power_w)s,
                        %(load_power_w)s,
                        %(grid_power_w)s,
                        %(generator_power_w)s,
                        %(inverter_output_w)s,
                        %(battery_state)s,
                        %(grid_state)s,
                        %(generator_state)s,
                        %(flags)s::jsonb,
                        %(summary_status)s,
                        %(summary_headline)s,
                        %(summary_notes)s::jsonb,
                        now()
                    )
                    on conflict (source_id) do update set
                        reading_at = excluded.reading_at,
                        battery_soc_pct = excluded.battery_soc_pct,
                        battery_power_w = excluded.battery_power_w,
                        solar_power_w = excluded.solar_power_w,
                        pv1_power_w = excluded.pv1_power_w,
                        pv2_power_w = excluded.pv2_power_w,
                        load_power_w = excluded.load_power_w,
                        grid_power_w = excluded.grid_power_w,
                        generator_power_w = excluded.generator_power_w,
                        inverter_output_w = excluded.inverter_output_w,
                        battery_state = excluded.battery_state,
                        grid_state = excluded.grid_state,
                        generator_state = excluded.generator_state,
                        flags = excluded.flags,
                        summary_status = excluded.summary_status,
                        summary_headline = excluded.summary_headline,
                        summary_notes = excluded.summary_notes,
                        updated_at = now()
                    where excluded.reading_at >= public.power_latest_state.reading_at
                    """,
                    reading,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "power_ingest_failed",
            "message": "Power telemetry ingest failed.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "source_id": reading["source_id"],
        "reading_id": reading["reading_id"],
        "reading_at": reading["reading_at"].isoformat(),
        "source": _source_metadata(writes_to_supabase=True),
    }, 201


def get_current_power_state(database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        ts.source_id,
                        ts.display_name,
                        ts.provider,
                        ts.stale_after_minutes,
                        pls.reading_at,
                        pls.battery_soc_pct,
                        pls.battery_power_w,
                        pls.solar_power_w,
                        pls.pv1_power_w,
                        pls.pv2_power_w,
                        pls.load_power_w,
                        pls.grid_power_w,
                        pls.generator_power_w,
                        pls.inverter_output_w,
                        pls.battery_state,
                        pls.grid_state,
                        pls.generator_state,
                        pls.flags,
                        pls.summary_status,
                        pls.summary_headline,
                        pls.summary_notes
                    from public.telemetry_sources ts
                    left join public.power_latest_state pls on pls.source_id = ts.source_id
                    where ts.source_id = %s
                    """,
                    (DEFAULT_POWER_SOURCE_ID,),
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "power_current_read_failed",
            "message": "Current power telemetry read failed.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    if not row or not row[4]:
        return {
            "success": False,
            "configured": True,
            "status": "unavailable",
            "message": "No current power telemetry reading is available yet.",
            "source": _source_metadata(writes_to_supabase=False),
        }, 200

    return _format_current_power_response(row), 200


def _normalize_power_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")

    source_id = str(payload.get("source_id") or DEFAULT_POWER_SOURCE_ID).strip()
    reading_at = _parse_reading_at(
        payload.get("reading_at")
        or payload.get("timestamp_za")
        or payload.get("timestamp")
        or payload.get("last_reading_at")
    )

    battery_soc = _number_or_none(payload.get("battery_soc_pct", payload.get("soc")))
    battery_power = _number_or_none(payload.get("battery_power_w", payload.get("batt_power")))
    solar_power = _number_or_none(payload.get("solar_power_w", payload.get("pv_total")))
    pv1_power = _number_or_none(payload.get("pv1_power_w", payload.get("pv1")))
    pv2_power = _number_or_none(payload.get("pv2_power_w", payload.get("pv2")))
    load_power = _number_or_none(payload.get("load_power_w", payload.get("load_power")))
    grid_power = _number_or_none(payload.get("grid_power_w", payload.get("grid_power")))
    generator_power = _number_or_none(payload.get("generator_power_w", payload.get("gen_power")))
    inverter_output = _number_or_none(payload.get("inverter_output_w", payload.get("inv_pac")))

    battery_charging = _bool_or_none(payload.get("battery_charging"))
    battery_discharging = _bool_or_none(payload.get("battery_discharging"))
    if battery_charging is None and battery_discharging is None and battery_power is not None:
        battery_charging = battery_power < -50
        battery_discharging = battery_power > 50

    grid_active = _bool_or_none(payload.get("grid_active"))
    if grid_active is None:
        grid_active = abs(grid_power or 0) > 50

    generator_active = _bool_or_none(payload.get("generator_active", payload.get("gen_active")))
    if generator_active is None:
        generator_active = abs(generator_power or 0) > 50

    flags = {
        "solar_active": (solar_power or 0) > 100,
        "battery_charging": bool(battery_charging),
        "battery_discharging": bool(battery_discharging),
        "grid_active": bool(grid_active),
        "generator_active": bool(generator_active),
        "low_battery": battery_soc is not None and battery_soc < 30,
        "high_load": load_power is not None and load_power >= 6000,
        "no_solar": (solar_power or 0) <= 100,
    }
    summary = _build_summary(flags, battery_soc, solar_power, load_power)

    return {
        "reading_id": _reading_id(source_id, reading_at),
        "source_id": source_id,
        "reading_at": reading_at,
        "battery_soc_pct": battery_soc,
        "battery_power_w": battery_power,
        "solar_power_w": solar_power,
        "pv1_power_w": pv1_power,
        "pv2_power_w": pv2_power,
        "load_power_w": load_power,
        "grid_power_w": grid_power,
        "generator_power_w": generator_power,
        "inverter_output_w": inverter_output,
        "grid_active": flags["grid_active"],
        "generator_active": flags["generator_active"],
        "battery_charging": flags["battery_charging"],
        "battery_discharging": flags["battery_discharging"],
        "battery_state": _battery_state(flags),
        "grid_state": _grid_state(flags, grid_power),
        "generator_state": "on" if flags["generator_active"] else "off",
        "flags": json.dumps(flags, separators=(",", ":")),
        "summary_status": summary["status"],
        "summary_headline": summary["headline"],
        "summary_notes": json.dumps(summary["operator_notes"], separators=(",", ":")),
        "raw_payload": _json_param(payload.get("raw_payload")),
    }


def _format_current_power_response(row):
    (
        source_id,
        display_name,
        provider,
        stale_after_minutes,
        reading_at,
        battery_soc,
        battery_power,
        solar_power,
        pv1_power,
        pv2_power,
        load_power,
        grid_power,
        generator_power,
        inverter_output,
        battery_state,
        grid_state,
        generator_state,
        flags,
        summary_status,
        summary_headline,
        summary_notes,
    ) = row

    age_minutes = max(0, int((datetime.now(timezone.utc) - reading_at.astimezone(timezone.utc)).total_seconds() // 60))
    is_stale = age_minutes > int(stale_after_minutes)
    response_status = "stale" if is_stale else summary_status

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
            "battery_soc_pct": _json_value(battery_soc),
            "battery_power_w": _json_value(battery_power),
            "battery_state": battery_state,
            "solar_power_w": _json_value(solar_power),
            "pv1_power_w": _json_value(pv1_power),
            "pv2_power_w": _json_value(pv2_power),
            "load_power_w": _json_value(load_power),
            "grid_power_w": _json_value(grid_power),
            "grid_state": grid_state,
            "generator_power_w": _json_value(generator_power),
            "generator_state": generator_state,
            "inverter_output_w": _json_value(inverter_output),
        },
        "flags": flags or {},
        "summary": {
            "status": response_status,
            "headline": "Power data is stale. Showing the last known state." if is_stale else summary_headline,
            "operator_notes": summary_notes or [],
        },
        "units": {
            "power": "W",
            "battery_soc": "%",
        },
    }


def _parse_reading_at(value):
    if not value:
        raise ValueError("reading_at or timestamp_za is required.")
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("reading_at must be an ISO timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZA_TZ)
    return parsed


def _number_or_none(value):
    if value in (None, ""):
        return None
    return float(value)


def _bool_or_none(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _battery_state(flags):
    if flags["battery_charging"]:
        return "charging"
    if flags["battery_discharging"]:
        return "discharging"
    return "idle"


def _grid_state(flags, grid_power):
    if not flags["grid_active"]:
        return "not_using_grid"
    if grid_power is not None and grid_power < -50:
        return "exporting"
    return "using_grid"


def _build_summary(flags, battery_soc, solar_power, load_power):
    if flags["low_battery"]:
        status = "warning"
        headline = "Battery is low; watch power usage."
    elif flags["solar_active"] and not flags["grid_active"]:
        status = "ok"
        headline = "Solar is carrying the farm load."
    elif flags["grid_active"]:
        status = "warning"
        headline = "The farm is using grid power."
    else:
        status = "ok"
        headline = "Power state is available."

    notes = []
    if battery_soc is not None:
        notes.append(f"Battery is at {battery_soc:g}%.")
    if solar_power is not None:
        notes.append(f"Solar production is {_kw(solar_power)} kW.")
    if load_power is not None:
        notes.append(f"Current load is {_kw(load_power)} kW.")
    if flags["generator_active"]:
        notes.append("Generator use is showing.")
    elif flags["grid_active"]:
        notes.append("Grid use is showing.")
    else:
        notes.append("No grid or generator use is showing.")

    return {
        "status": status,
        "headline": headline,
        "operator_notes": notes,
    }


def _kw(watts):
    return round(float(watts) / 1000, 1)


def _reading_id(source_id, reading_at):
    digest = hashlib.sha1(f"{source_id}|{reading_at.isoformat()}".encode("utf-8")).hexdigest()[:12].upper()
    return f"PWR-{digest}"


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
