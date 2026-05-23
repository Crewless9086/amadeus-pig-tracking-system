import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.database_service import DATABASE_URL_ENV


ZA_TZ = ZoneInfo("Africa/Johannesburg")
POWER_SOURCE_ID = "sunsynk-main-inverter"
WEATHER_SOURCE_ID = "weather-station-main"
IRRIGATION_SOURCE_ID = "irrigation-controller-main"
EXPECTED_5MIN_SAMPLES_PER_DAY = 288
SAMPLE_MINUTES = 5
PLANNING_TARIFF_ZAR_PER_KWH = 9.10
CALCULATION_VERSION = "daily_rollup_plan_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only daily telemetry rollup plan.")
    parser.add_argument("--date", dest="rollup_date", help="Local ZA date in YYYY-MM-DD format.")
    parser.add_argument(
        "--previous-day",
        action="store_true",
        help="Use yesterday's ZA date. Intended for scheduled after-midnight rollups.",
    )
    parser.add_argument("--apply", action="store_true", help="Upsert the selected date's daily rollups.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow apply for today/future dates. Intended only for explicit manual testing.",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    rollup_date = _previous_day_za().isoformat() if args.previous_day else args.rollup_date
    if args.apply:
        report, exit_code = apply_daily_rollups(
            rollup_date,
            database_url,
            allow_partial=args.allow_partial,
        )
    else:
        report, exit_code = build_daily_rollup_plan(rollup_date, database_url)
    print(json.dumps(report, indent=2, default=_json_default))
    return exit_code


def build_daily_rollup_plan(rollup_date=None, database_url="", connect_factory=None):
    selected_date = _parse_rollup_date(rollup_date)
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "mode": "plan_only",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }, 2

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
            "mode": "plan_only",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }, 2

    connect = connect_factory or psycopg.connect
    start_za = datetime(selected_date.year, selected_date.month, selected_date.day, tzinfo=ZA_TZ)
    end_za = start_za + timedelta(days=1)
    start_utc = start_za.astimezone(timezone.utc)
    end_utc = end_za.astimezone(timezone.utc)

    try:
        with connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                power_rows = _fetch_power_rows(cursor, start_utc, end_utc)
                weather_rows = _fetch_weather_rows(cursor, start_utc, end_utc)
                irrigation_data = _fetch_irrigation_data(cursor, selected_date, start_utc, end_utc)
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "daily_rollup_plan_failed",
            "message": "Daily telemetry rollup plan failed.",
            "error_type": exc.__class__.__name__,
            "mode": "plan_only",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }, 2

    payloads = {
        "power_daily_rollups": [_build_power_daily_rollup(selected_date, start_utc, end_utc, power_rows)],
        "weather_daily_rollups": [_build_weather_daily_rollup(selected_date, start_utc, end_utc, weather_rows)],
        "irrigation_daily_rollups": [
            _build_irrigation_daily_rollup(selected_date, start_utc, end_utc, irrigation_data)
        ],
    }
    summary = {
        table: {
            "rows": len(rows),
            "sample_ids": [row["rollup_id"] for row in rows[:3]],
        }
        for table, rows in payloads.items()
    }

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "plan_only",
        "rollup_date": selected_date.isoformat(),
        "timezone": "Africa/Johannesburg",
        "calculation_version": CALCULATION_VERSION,
        "writes_to_sheets": False,
        "writes_to_supabase": False,
        "source_window": {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "sample_interval_minutes_assumed": SAMPLE_MINUTES,
        },
        "payload_summary": summary,
        "payloads": payloads,
        "warnings": _warnings(payloads),
    }, 0


def apply_daily_rollups(rollup_date=None, database_url="", connect_factory=None, allow_partial=False):
    selected_date = _parse_rollup_date(rollup_date)
    if not allow_partial and not _is_closed_local_day(selected_date):
        return {
            "success": False,
            "configured": True,
            "status": "day_not_closed",
            "message": "Refusing to apply a daily rollup before the selected ZA day is closed.",
            "mode": "apply",
            "rollup_date": selected_date.isoformat(),
            "today_za": datetime.now(ZA_TZ).date().isoformat(),
            "allow_partial_required": True,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }, 2

    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "mode": "apply",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }, 2

    if connect_factory is None:
        try:
            import psycopg
        except ImportError:
            return {
                "success": False,
                "configured": True,
                "status": "dependency_missing",
                "message": "Python database dependency is not installed.",
                "mode": "apply",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            }, 2
        connect_factory = psycopg.connect

    plan_report, plan_exit_code = build_daily_rollup_plan(
        selected_date.isoformat(),
        database_url,
        connect_factory=connect_factory,
    )
    if plan_exit_code != 0:
        plan_report["mode"] = "apply"
        return plan_report, plan_exit_code

    payloads = plan_report["payloads"]
    inserted_or_updated = {}

    try:
        with connect_factory(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                for table_name in DAILY_ROLLUP_TABLES:
                    inserted_or_updated[table_name] = _upsert_rollup_rows(
                        cursor,
                        table_name,
                        payloads[table_name],
                    )
            connection.commit()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "daily_rollup_apply_failed",
            "message": "Daily telemetry rollup apply failed and transaction was rolled back.",
            "error_type": exc.__class__.__name__,
            "mode": "apply",
            "rollup_date": plan_report["rollup_date"],
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }, 1

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "apply",
        "rollup_date": plan_report["rollup_date"],
        "timezone": plan_report["timezone"],
        "calculation_version": plan_report["calculation_version"],
        "partial_apply_allowed": bool(allow_partial),
        "writes_to_sheets": False,
        "writes_to_supabase": True,
        "inserted_or_updated": inserted_or_updated,
        "payload_summary": plan_report["payload_summary"],
        "warnings": plan_report["warnings"],
    }, 0


def _fetch_power_rows(cursor, start_utc, end_utc):
    cursor.execute(
        """
        select reading_at, battery_soc_pct, solar_power_w, load_power_w,
               grid_power_w, generator_power_w, grid_active, generator_active
        from public.power_readings_5min
        where source_id = %s
          and reading_at >= %s
          and reading_at < %s
          and raw_payload is not null
        order by reading_at asc
        """,
        (POWER_SOURCE_ID, start_utc, end_utc),
    )
    return [
        {
            "reading_at": row[0],
            "battery_soc_pct": _float_or_none(row[1]),
            "solar_power_w": _float_or_none(row[2]),
            "load_power_w": _float_or_none(row[3]),
            "grid_power_w": _float_or_none(row[4]),
            "generator_power_w": _float_or_none(row[5]),
            "grid_active": bool(row[6]),
            "generator_active": bool(row[7]),
        }
        for row in cursor.fetchall()
    ]


def _fetch_weather_rows(cursor, start_utc, end_utc):
    cursor.execute(
        """
        select reading_at, temperature_c, humidity_pct, rain_rate_mm_h, rain_today_mm,
               wind_speed_kmh, wind_gust_kmh, pressure_hpa
        from public.weather_readings
        where source_id = %s
          and reading_at >= %s
          and reading_at < %s
          and coalesce(raw_payload->>'test', 'false') <> 'true'
        order by reading_at asc
        """,
        (WEATHER_SOURCE_ID, start_utc, end_utc),
    )
    return [
        {
            "reading_at": row[0],
            "temperature_c": _float_or_none(row[1]),
            "humidity_pct": _float_or_none(row[2]),
            "rain_rate_mm_h": _float_or_none(row[3]),
            "rain_today_mm": _float_or_none(row[4]),
            "wind_speed_kmh": _float_or_none(row[5]),
            "wind_gust_kmh": _float_or_none(row[6]),
            "pressure_hpa": _float_or_none(row[7]),
        }
        for row in cursor.fetchall()
    ]


def _fetch_irrigation_data(cursor, selected_date, start_utc, end_utc):
    cursor.execute(
        """
        select daily_plan_id, source_id
        from public.irrigation_daily_plans
        where plan_date = %s
          and plan_status not in ('Cancelled', 'Superseded')
        order by created_at desc, daily_plan_id desc
        limit 1
        """,
        (selected_date,),
    )
    daily_plan = cursor.fetchone()

    plan_items = []
    if daily_plan:
        cursor.execute(
            """
            select item_status, planned_minutes, actual_minutes, actual_start_at, actual_end_at
            from public.irrigation_plan_items
            where daily_plan_id = %s
            """,
            (daily_plan[0],),
        )
        plan_items = [
            {
                "item_status": str(row[0] or ""),
                "planned_minutes": _float_or_none(row[1]) or 0,
                "actual_minutes": _float_or_none(row[2]) or 0,
                "actual_start_at": row[3],
                "actual_end_at": row[4],
            }
            for row in cursor.fetchall()
        ]

    cursor.execute(
        """
        select event_at, zone_id, event_type, planned_minutes, actual_minutes, reason, actor
        from public.irrigation_events
        where source_id = %s
          and event_at >= %s
          and event_at < %s
        """,
        (IRRIGATION_SOURCE_ID, start_utc, end_utc),
    )
    events = [
        {
            "event_at": row[0],
            "zone_id": str(row[1] or ""),
            "event_type": str(row[2] or ""),
            "planned_minutes": _float_or_none(row[3]) or 0,
            "actual_minutes": _float_or_none(row[4]) or 0,
            "reason": str(row[5] or ""),
            "actor": str(row[6] or ""),
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        select d.device_type, t.planned_minutes, t.actual_start_at, t.actual_end_at, t.task_status
        from public.irrigation_auxiliary_tasks t
        join public.irrigation_auxiliary_devices d on d.auxiliary_device_id = t.auxiliary_device_id
        where t.task_date = %s
        """,
        (selected_date,),
    )
    auxiliary_tasks = [
        {
            "device_type": str(row[0] or ""),
            "planned_minutes": _float_or_none(row[1]) or 0,
            "actual_start_at": row[2],
            "actual_end_at": row[3],
            "task_status": str(row[4] or ""),
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        select sensor_type, status
        from public.irrigation_sensor_states
        where source_id = %s
          and reading_at >= %s
          and reading_at < %s
        """,
        (IRRIGATION_SOURCE_ID, start_utc, end_utc),
    )
    sensor_states = [
        {
            "sensor_type": str(row[0] or ""),
            "status": str(row[1] or ""),
        }
        for row in cursor.fetchall()
    ]

    return {
        "daily_plan": {
            "daily_plan_id": daily_plan[0],
            "source_id": daily_plan[1],
        } if daily_plan else {},
        "plan_items": plan_items,
        "events": _dedupe_irrigation_events(events),
        "auxiliary_tasks": auxiliary_tasks,
        "sensor_states": sensor_states,
    }


def _build_power_daily_rollup(selected_date, start_utc, end_utc, rows):
    solar_values = _values(rows, "solar_power_w")
    load_values = _values(rows, "load_power_w")
    battery_values = _values(rows, "battery_soc_pct")
    grid_values = _values(rows, "grid_power_w")
    generator_values = _values(rows, "generator_power_w")
    estimated_load_kwh = _estimate_kwh(load_values)
    estimated_solar_kwh = _estimate_kwh(solar_values)
    estimated_grid_import_kwh = _estimate_kwh([max(value, 0) for value in grid_values])
    estimated_grid_export_kwh = _estimate_kwh([abs(min(value, 0)) for value in grid_values])
    estimated_generator_kwh = _estimate_kwh([max(value, 0) for value in generator_values])

    return {
        "rollup_id": f"PWRDAY-{selected_date.isoformat()}-{POWER_SOURCE_ID}",
        "source_id": POWER_SOURCE_ID,
        "rollup_date": selected_date.isoformat(),
        "source_window_start": start_utc.isoformat(),
        "source_window_end": end_utc.isoformat(),
        "sample_count": len(rows),
        "expected_sample_count": EXPECTED_5MIN_SAMPLES_PER_DAY,
        "coverage_pct": _coverage(len(rows)),
        "battery_soc_min_pct": _min(battery_values),
        "battery_soc_max_pct": _max(battery_values),
        "battery_soc_avg_pct": _avg(battery_values),
        "load_power_avg_w": _avg(load_values),
        "load_power_max_w": _max(load_values),
        "solar_power_avg_w": _avg(solar_values),
        "solar_power_max_w": _max(solar_values),
        "grid_active_minutes": _count_minutes(row.get("grid_active") for row in rows),
        "generator_active_minutes": _count_minutes(row.get("generator_active") for row in rows),
        "no_solar_minutes": _count_minutes((row.get("solar_power_w") or 0) <= 0 for row in rows),
        "estimated_solar_kwh": estimated_solar_kwh,
        "estimated_load_kwh": estimated_load_kwh,
        "estimated_grid_import_kwh": estimated_grid_import_kwh,
        "estimated_grid_export_kwh": estimated_grid_export_kwh,
        "estimated_generator_kwh": estimated_generator_kwh,
        "energy_calculation_method": "sample_integration_estimated",
        "tariff_zar_per_kwh": PLANNING_TARIFF_ZAR_PER_KWH,
        "estimated_value_zar": _round_money(estimated_solar_kwh * PLANNING_TARIFF_ZAR_PER_KWH)
        if estimated_solar_kwh is not None else None,
        "limitations": [
            "kWh and Rand values are estimated from 5-minute W samples.",
            "Use confirmed Sunsynk energy counters later if available.",
        ],
        "calculation_version": CALCULATION_VERSION,
        "metadata": {"mode": "plan_only", "raw_retention_days_planned": 90},
    }


def _build_weather_daily_rollup(selected_date, start_utc, end_utc, rows):
    temperature_values = _values(rows, "temperature_c")
    humidity_values = _values(rows, "humidity_pct")
    rain_rate_values = _values(rows, "rain_rate_mm_h")
    rain_today_values = _values(rows, "rain_today_mm")
    wind_values = _values(rows, "wind_speed_kmh")
    gust_values = _values(rows, "wind_gust_kmh")
    pressure_values = _values(rows, "pressure_hpa")
    rain_total = _max(rain_today_values)
    flags = {
        "rain_observed": any((value or 0) > 0 for value in rain_rate_values) or (rain_total or 0) > 0,
        "wind_caution": (_max(wind_values) or 0) >= 30 or (_max(gust_values) or 0) >= 40,
        "irrigation_caution": (_max(rain_rate_values) or 0) > 0 or (rain_total or 0) >= 0.5
        or (_max(wind_values) or 0) >= 30 or (_max(gust_values) or 0) >= 40,
    }

    return {
        "rollup_id": f"WTHDAY-{selected_date.isoformat()}-{WEATHER_SOURCE_ID}",
        "source_id": WEATHER_SOURCE_ID,
        "rollup_date": selected_date.isoformat(),
        "source_window_start": start_utc.isoformat(),
        "source_window_end": end_utc.isoformat(),
        "sample_count": len(rows),
        "expected_sample_count": EXPECTED_5MIN_SAMPLES_PER_DAY,
        "coverage_pct": _coverage(len(rows)),
        "temperature_min_c": _min(temperature_values),
        "temperature_max_c": _max(temperature_values),
        "temperature_avg_c": _avg(temperature_values),
        "humidity_avg_pct": _avg(humidity_values),
        "rain_total_mm": rain_total,
        "rain_rate_max_mm_h": _max(rain_rate_values),
        "wind_speed_max_kmh": _max(wind_values),
        "wind_gust_max_kmh": _max(gust_values),
        "pressure_min_hpa": _min(pressure_values),
        "pressure_max_hpa": _max(pressure_values),
        "irrigation_caution_minutes": len(rows) * SAMPLE_MINUTES if flags["irrigation_caution"] else 0,
        "flags": flags,
        "calculation_version": CALCULATION_VERSION,
        "metadata": {"mode": "plan_only", "raw_retention_days_planned": 90},
    }


def _build_irrigation_daily_rollup(selected_date, start_utc, end_utc, data):
    plan_items = data["plan_items"]
    events = data["events"]
    auxiliary_tasks = data["auxiliary_tasks"]
    sensor_states = data["sensor_states"]
    statuses = [item["item_status"].upper() for item in plan_items]
    completed_statuses = {"DONE", "COMPLETED"}
    skipped_statuses = {"SKIPPED", "CANCELLED", "BLOCKED"}
    paused_statuses = {"PAUSED"}
    injection_tasks = [
        task for task in auxiliary_tasks if task["device_type"] == "fertilizer_injection_valve"
    ]
    mixer_tasks = [task for task in auxiliary_tasks if task["device_type"] == "fertilizer_mixer"]

    return {
        "rollup_id": f"IRRDAY-{selected_date.isoformat()}-{IRRIGATION_SOURCE_ID}",
        "source_id": IRRIGATION_SOURCE_ID,
        "rollup_date": selected_date.isoformat(),
        "daily_plan_id": data["daily_plan"].get("daily_plan_id"),
        "source_window_start": start_utc.isoformat(),
        "source_window_end": end_utc.isoformat(),
        "planned_zone_count": len(plan_items),
        "completed_zone_count": sum(status in completed_statuses for status in statuses),
        "skipped_zone_count": sum(status in skipped_statuses for status in statuses),
        "paused_zone_count": sum(status in paused_statuses for status in statuses),
        "planned_minutes": _round(sum(item["planned_minutes"] for item in plan_items), 2),
        "completed_minutes": _round(
            sum(
                item["actual_minutes"] or item["planned_minutes"]
                for item in plan_items
                if item["item_status"].upper() in completed_statuses
            ),
            2,
        ),
        "active_runtime_minutes": _round(sum(item["actual_minutes"] for item in plan_items), 2),
        "weather_hold_minutes": _event_minutes(events, "weather"),
        "power_hold_minutes": _event_minutes(events, "power"),
        "tank_hold_minutes": _event_minutes(events, "tank"),
        "manual_override_count": sum("manual" in event["event_type"].lower() for event in events),
        "event_count": len(events),
        "fertilizer_injection_minutes": _auxiliary_minutes(injection_tasks),
        "fertilizer_injection_cycles": len(injection_tasks),
        "fertilizer_mixer_minutes": _auxiliary_minutes(mixer_tasks),
        "tank_full_count": _sensor_count(sensor_states, "tank_full"),
        "tank_empty_count": _sensor_count(sensor_states, "tank_empty"),
        "tank_status_notes": _tank_notes(sensor_states),
        "notes": "Plan-only rollup candidate; no database writes performed.",
        "calculation_version": CALCULATION_VERSION,
        "metadata": {"mode": "plan_only"},
    }


def _parse_rollup_date(value):
    if not value:
        return datetime.now(ZA_TZ).date()
    return date.fromisoformat(str(value))


def _is_closed_local_day(selected_date):
    return selected_date < datetime.now(ZA_TZ).date()


def _previous_day_za():
    return datetime.now(ZA_TZ).date() - timedelta(days=1)


def _values(rows, key):
    return [row[key] for row in rows if row.get(key) is not None]


def _min(values):
    return _round(min(values), 2) if values else None


def _max(values):
    return _round(max(values), 2) if values else None


def _avg(values):
    return _round(sum(values) / len(values), 2) if values else None


def _coverage(count):
    return _round((count / EXPECTED_5MIN_SAMPLES_PER_DAY) * 100, 2)


def _count_minutes(values):
    return sum(1 for value in values if value) * SAMPLE_MINUTES


def _estimate_kwh(power_values):
    if not power_values:
        return None
    return _round(sum(power_values) * (SAMPLE_MINUTES / 60) / 1000, 4)


def _event_minutes(events, keyword):
    return _round(
        sum(
            event["actual_minutes"] or event["planned_minutes"]
            for event in events
            if keyword in event["event_type"].lower() or keyword in event["reason"].lower()
        ),
        2,
    )


def _auxiliary_minutes(tasks):
    return _round(sum(task["planned_minutes"] for task in tasks), 2)


def _sensor_count(sensor_states, sensor_type):
    return sum(state["sensor_type"] == sensor_type for state in sensor_states)


def _dedupe_irrigation_events(events):
    deduped = []
    seen = set()
    for event in events:
        key = (
            event["event_at"],
            event["zone_id"],
            event["event_type"],
            event["planned_minutes"],
            event["actual_minutes"],
            event["reason"],
            event["actor"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def _tank_notes(sensor_states):
    if not sensor_states:
        return None
    return "; ".join(
        f"{state['sensor_type']}={state['status']}"
        for state in sensor_states
        if state["sensor_type"].startswith("tank_")
    ) or None


def _warnings(payloads):
    warnings = []
    for table, rows in payloads.items():
        if rows and rows[0].get("sample_count") == 0:
            warnings.append(f"{table} has no raw samples for the selected date.")
        if rows and rows[0].get("coverage_pct") is not None and rows[0]["coverage_pct"] < 75:
            warnings.append(f"{table} coverage is below 75%.")
    return warnings


def _float_or_none(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round(value, digits):
    return round(float(value), digits)


def _round_money(value):
    return _round(value, 2)


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


DAILY_ROLLUP_TABLES = [
    "power_daily_rollups",
    "weather_daily_rollups",
    "irrigation_daily_rollups",
]


def _json_safe_value(value):
    if isinstance(value, (list, dict)):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def _upsert_rollup_rows(cursor, table_name, rows):
    if not rows:
        return 0

    from psycopg import sql

    columns = list(rows[0].keys())
    conflict_columns = ["source_id", "rollup_date"]
    update_columns = [column for column in columns if column not in {"rollup_id", "source_id", "rollup_date"}]
    update_columns.append("updated_at")
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    column_sql = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    update_sql = sql.SQL(", ").join(
        sql.SQL("{} = {}").format(
            sql.Identifier(column),
            sql.SQL("now()") if column == "updated_at" else sql.SQL("excluded.{}").format(sql.Identifier(column)),
        )
        for column in update_columns
    )
    conflict_sql = sql.SQL(", ").join(sql.Identifier(column) for column in conflict_columns)

    statement = sql.SQL(
        """
        insert into public.{table} ({columns})
        values ({placeholders})
        on conflict ({conflict_columns}) do update set {updates}
        """
    ).format(
        table=sql.Identifier(table_name),
        columns=column_sql,
        placeholders=placeholders,
        conflict_columns=conflict_sql,
        updates=update_sql,
    )

    cursor.executemany(
        statement,
        [
            tuple(_json_safe_value(row.get(column)) for column in columns)
            for row in rows
        ],
    )
    return len(rows)


if __name__ == "__main__":
    raise SystemExit(main())
