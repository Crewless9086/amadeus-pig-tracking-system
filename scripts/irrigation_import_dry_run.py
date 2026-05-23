import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.pig_weights.pig_weights_utils import format_date_for_json, to_float
from services.google_sheets_service import get_all_records_from_spreadsheet
from services.database_service import DATABASE_URL_ENV


DEFAULT_IRRIGATION_SHEET_NAME = "Amadeus_Irrigation_Logs"
IRRIGATION_SOURCE_ID = "irrigation-controller-main"
PLAN_ONLY_BATCH_ID = "DRY_RUN_ONLY"
APPLY_IMPORT_BATCH_ID = "IMPORT-20260523-IRRIGATION-SHEET-V1"
STATE_IMPORT_STRATEGY = "latest_state_upsert"
TABLE_PRIMARY_KEYS = {
    "irrigation_zones": "zone_id",
    "irrigation_daily_plans": "daily_plan_id",
    "irrigation_plan_items": "plan_item_id",
    "irrigation_state_snapshots": "state_snapshot_id",
    "irrigation_events": "irrigation_event_id",
}
TABLE_INSERT_ORDER = [
    "irrigation_zones",
    "irrigation_daily_plans",
    "irrigation_plan_items",
    "irrigation_state_snapshots",
    "irrigation_events",
]

ZONES_SHEET = "ZONES"
DAILY_PLAN_SHEET = "DAILY_PLAN"
STATE_SHEET = "STATE"
LOG_SHEET = "LOG"


def clean(value):
    return str(value or "").strip()


def clean_lower(value):
    return clean(value).lower()


def optional_float(value):
    number = to_float(value)
    return number if number is not None else None


def optional_int(value):
    number = to_float(value)
    return int(number) if number is not None else None


def optional_date(value):
    text = clean(value)
    if not text:
        return None
    return (format_date_for_json(text) or text)[:10]


def optional_timestamp(value):
    text = clean(value)
    if not text:
        return None
    return format_date_for_json(text) or text


def normalize_zone_type(row):
    haystack = " ".join(
        clean_lower(row.get(field))
        for field in ("zone_type", "type", "irrigation_type", "method", "name", "zone_name")
    )
    if "drip" in haystack:
        return "drip"
    if "sprinkler" in haystack or "spray" in haystack:
        return "sprinkler"
    if "support" in haystack:
        return "support"
    if haystack:
        return "watering"
    return "unknown"


def normalize_plan_status(value):
    status = clean(value)
    status_lower = status.lower()
    mapping = {
        "draft": "Draft",
        "planned": "Planned",
        "running": "Running",
        "completed": "Completed",
        "complete": "Completed",
        "done": "Completed",
        "paused": "Paused",
        "cancelled": "Cancelled",
        "canceled": "Cancelled",
        "superseded": "Superseded",
    }
    return mapping.get(status_lower, "Planned" if not status_lower else None)


def normalize_item_status(value):
    status = clean(value)
    status_upper = status.upper()
    mapping = {
        "PLANNED": "Planned",
        "RUNNING": "Running",
        "DONE": "Done",
        "COMPLETED": "Completed",
        "COMPLETE": "Completed",
        "PAUSED": "Paused",
        "SKIPPED": "Skipped",
        "CANCELLED": "Cancelled",
        "CANCELED": "Cancelled",
        "BLOCKED": "Blocked",
    }
    return mapping.get(status_upper, "Planned" if not status_upper else None)


def normalize_current_status(value):
    status = clean(value).upper()
    allowed = {"IDLE", "RUNNING", "PAUSED", "BLOCKED", "PLANNED", "DONE", "COMPLETED", "SKIPPED", "UNKNOWN"}
    if not status:
        return "UNKNOWN"
    return status if status in allowed else None


def load_local_env(load_dotenv_func=None):
    if load_dotenv_func is None:
        try:
            from dotenv import load_dotenv as load_dotenv_func
        except ImportError:
            return False

    return load_dotenv_func(ROOT_DIR / ".env")


def with_trace(payload, source_sheet_row, import_batch_id=PLAN_ONLY_BATCH_ID):
    payload["source_sheet_row"] = source_sheet_row
    payload["import_batch_id"] = import_batch_id
    return payload


def source_summary(sheet_name, rows):
    return {
        "sheet": sheet_name,
        "total_rows": len(rows),
        "non_empty_rows": sum(1 for row in rows if any(clean(value) for value in row.values())),
    }


def map_zone(row, source_sheet_row, import_batch_id=PLAN_ONLY_BATCH_ID):
    zone_id = clean(row.get("zone_id") or row.get("Zone_ID") or row.get("Zone ID"))
    zone_name = clean(row.get("name") or row.get("zone_name") or row.get("Zone_Name") or row.get("Zone Name"))
    if not zone_id:
        return None, "missing_zone_id"
    if not zone_name:
        return None, "missing_zone_name"

    return with_trace({
        "zone_id": zone_id,
        "source_id": IRRIGATION_SOURCE_ID,
        "zone_name": zone_name,
        "zone_type": normalize_zone_type(row),
        "crop_context": clean(row.get("crop_context") or row.get("crop") or row.get("planted")) or None,
        "location_notes": clean(row.get("location_notes") or row.get("notes")) or None,
        "summer_minutes": optional_float(row.get("summer_minutes") or row.get("summer_time") or row.get("summer")),
        "winter_minutes": optional_float(row.get("winter_minutes") or row.get("winter_time") or row.get("winter")),
        "priority": optional_int(row.get("priority")),
        "active": clean_lower(row.get("active")) not in {"false", "no", "0", "inactive"},
        "metadata": {},
    }, source_sheet_row, import_batch_id), "included_zone"


def plan_header_id(plan_date):
    return f"IRRPLAN-{plan_date}"


def map_daily_plan_item(row, source_sheet_row, zone_ids, import_batch_id=PLAN_ONLY_BATCH_ID):
    plan_id = clean(row.get("plan_id"))
    plan_date = optional_date(row.get("date"))
    zone_id = clean(row.get("zone_id"))
    if not plan_id:
        return None, None, "missing_plan_id"
    if not plan_date:
        return None, None, "missing_plan_date"

    item_status = normalize_item_status(row.get("status"))
    if item_status is None:
        return None, None, "unknown_item_status"

    daily_plan_id = plan_header_id(plan_date)
    header = {
        "daily_plan_id": daily_plan_id,
        "plan_date": plan_date,
        "source_id": IRRIGATION_SOURCE_ID,
        "plan_status": "Planned",
        "plan_source": "n8n",
        "total_planned_minutes": None,
        "created_reason": "Mapped from irrigation DAILY_PLAN sheet dry-run.",
        "weather_snapshot": {},
        "power_snapshot": {},
        "metadata": {},
        "source_sheet_row": None,
        "import_batch_id": import_batch_id,
    }

    issue = None
    if zone_id and zone_id not in zone_ids:
        issue = "missing_zone_link"

    item = with_trace({
        "plan_item_id": plan_id,
        "daily_plan_id": daily_plan_id,
        "zone_id": zone_id or None,
        "planned_start_at": optional_timestamp(row.get("planned_start")),
        "planned_minutes": optional_float(row.get("planned_minutes")),
        "actual_start_at": optional_timestamp(row.get("actual_start")),
        "actual_end_at": optional_timestamp(row.get("actual_end")),
        "actual_minutes": None,
        "item_status": item_status,
        "water_score": optional_float(row.get("water_score")),
        "priority": None,
        "reason": clean(row.get("reason")) or None,
        "metadata": {"zone_link_issue": issue} if issue else {},
    }, source_sheet_row, import_batch_id)
    return header, item, issue or "included_plan_item"


def map_state_snapshot(row, source_sheet_row, zone_ids, import_batch_id=PLAN_ONLY_BATCH_ID):
    has_state = any(
        clean(row.get(field))
        for field in ("state_id", "current_zone_id", "current_status", "next_zone_id", "last_update")
    )
    if not has_state:
        return None, "empty_state_row"

    current_status = normalize_current_status(row.get("current_status"))
    if current_status is None:
        return None, "unknown_current_status"

    current_zone_id = clean(row.get("current_zone_id"))
    next_zone_id = clean(row.get("next_zone_id"))
    issues = []
    if current_zone_id and current_zone_id not in zone_ids:
        issues.append("current_zone_missing")
    if next_zone_id and next_zone_id not in zone_ids:
        issues.append("next_zone_missing")

    snapshot_id = clean(row.get("state_id")) or f"STATE-{source_sheet_row}"
    payload = with_trace({
        "state_snapshot_id": f"IRRSTATE-{snapshot_id}",
        "source_id": IRRIGATION_SOURCE_ID,
        "snapshot_at": optional_timestamp(row.get("last_update")) or None,
        "current_status": current_status,
        "current_zone_id": current_zone_id or None,
        "next_zone_id": next_zone_id or None,
        "last_zone_completed": clean(row.get("last_zone_completed")) or None,
        "remaining_minutes": optional_float(row.get("remaining_minutes")),
        "pause_reason": clean(row.get("pause_reason")) or None,
        "raw_state": row,
    }, source_sheet_row, import_batch_id)

    return payload, "included_state_snapshot" if not issues else ",".join(issues)


def map_event(row, source_sheet_row, zone_ids, daily_plan_ids, import_batch_id=PLAN_ONLY_BATCH_ID):
    event_at = optional_timestamp(row.get("timestamp"))
    event_type = clean(row.get("event"))
    if not event_at:
        return None, "missing_event_at"
    if not event_type:
        return None, "missing_event_type"

    zone_id = clean(row.get("zone_id"))
    plan_id = clean(row.get("plan_id"))
    daily_plan_id = None
    if plan_id and "_" in plan_id:
        daily_plan_id = plan_header_id(plan_id.split("_", 1)[0])

    issues = []
    if zone_id and zone_id not in zone_ids and zone_id != "SYSTEM":
        issues.append("missing_zone_link")
    if daily_plan_id and daily_plan_id not in daily_plan_ids:
        issues.append("missing_daily_plan_link")

    event_id = f"IRREVT-{source_sheet_row}-{event_at.replace(':', '').replace('-', '').replace('+', '')}"
    payload = with_trace({
        "irrigation_event_id": event_id,
        "source_id": IRRIGATION_SOURCE_ID,
        "event_at": event_at,
        "event_type": event_type,
        "actor": clean(row.get("actor")) or None,
        "daily_plan_id": daily_plan_id,
        "plan_item_id": plan_id or None,
        "zone_id": None if zone_id == "SYSTEM" else zone_id or None,
        "planned_minutes": optional_float(row.get("run_minutes_planned")),
        "actual_minutes": optional_float(row.get("run_minutes_actual")),
        "reason": clean(row.get("reason")) or None,
        "weather_snapshot": {},
        "power_snapshot": {},
        "details": {"link_issues": issues} if issues else {},
    }, source_sheet_row, import_batch_id)
    return payload, "included_event" if not issues else ",".join(issues)


def build_irrigation_dry_run_payload(records, import_batch_id=PLAN_ONLY_BATCH_ID):
    zones_rows = records.get(ZONES_SHEET, [])
    plan_rows = records.get(DAILY_PLAN_SHEET, [])
    state_rows = records.get(STATE_SHEET, [])
    log_rows = records.get(LOG_SHEET, [])

    source_summaries = {
        sheet_name: source_summary(sheet_name, rows)
        for sheet_name, rows in records.items()
    }
    reason_counts = {
        "zones": Counter(),
        "plan_items": Counter(),
        "state_snapshots": Counter(),
        "events": Counter(),
    }

    zones = []
    seen_zone_ids = set()
    duplicate_zone_ids = []
    for row_number, row in enumerate(zones_rows, start=2):
        payload, reason = map_zone(row, row_number, import_batch_id)
        reason_counts["zones"][reason] += 1
        if payload:
            if payload["zone_id"] in seen_zone_ids:
                duplicate_zone_ids.append(payload["zone_id"])
            seen_zone_ids.add(payload["zone_id"])
            zones.append(payload)

    zone_ids = {zone["zone_id"] for zone in zones}
    daily_plans_by_id = {}
    plan_items = []
    for row_number, row in enumerate(plan_rows, start=2):
        header, item, reason = map_daily_plan_item(row, row_number, zone_ids, import_batch_id)
        reason_counts["plan_items"][reason] += 1
        if header:
            existing = daily_plans_by_id.get(header["daily_plan_id"])
            if existing is None:
                daily_plans_by_id[header["daily_plan_id"]] = header
            planned = optional_float(row.get("planned_minutes")) or 0
            daily_plans_by_id[header["daily_plan_id"]]["total_planned_minutes"] = (
                daily_plans_by_id[header["daily_plan_id"]]["total_planned_minutes"] or 0
            ) + planned
        if item:
            plan_items.append(item)

    daily_plans = list(daily_plans_by_id.values())
    daily_plan_ids = {plan["daily_plan_id"] for plan in daily_plans}

    state_snapshots = []
    for row_number, row in enumerate(state_rows, start=2):
        payload, reason = map_state_snapshot(row, row_number, zone_ids, import_batch_id)
        reason_counts["state_snapshots"][reason] += 1
        if payload:
            state_snapshots.append(payload)

    events = []
    for row_number, row in enumerate(log_rows, start=2):
        payload, reason = map_event(row, row_number, zone_ids, daily_plan_ids, import_batch_id)
        reason_counts["events"][reason] += 1
        if payload:
            events.append(payload)

    payloads = {
        "irrigation_zones": zones,
        "irrigation_daily_plans": daily_plans,
        "irrigation_plan_items": plan_items,
        "irrigation_state_snapshots": state_snapshots,
        "irrigation_events": events,
        "irrigation_auxiliary_devices": [],
        "irrigation_auxiliary_tasks": [],
        "irrigation_sensor_states": [],
    }

    link_issues = {
        group: {
            reason: count
            for reason, count in counts.items()
            if reason not in {
                "included_zone",
                "included_plan_item",
                "included_state_snapshot",
                "included_event",
                "empty_state_row",
            }
        }
        for group, counts in reason_counts.items()
    }
    link_issues = {group: issues for group, issues in link_issues.items() if issues}

    return {
        "success": True,
        "mode": "plan_only",
        "import_batch_id": import_batch_id,
        "source": {
            "spreadsheet_name": DEFAULT_IRRIGATION_SHEET_NAME,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
        "import_strategy": {
            "state": STATE_IMPORT_STRATEGY,
            "state_truth_model": "latest controller state by state_id",
            "state_history_model": "use irrigation_events and plan items for history",
            "apply_behavior": "upsert irrigation_state_snapshots by state_snapshot_id; do not append timestamped state rows",
        },
        "source_summaries": source_summaries,
        "payload_summary": {
            table: {
                "rows": len(rows),
                "sample_ids": [
                    rows[index].get(_id_field_for_table(table))
                    for index in range(min(3, len(rows)))
                ],
            }
            for table, rows in payloads.items()
        },
        "payload_samples": {
            table: rows[:3]
            for table, rows in payloads.items()
        },
        "reason_counts": {
            group: dict(sorted(counts.items()))
            for group, counts in reason_counts.items()
        },
        "link_issues": link_issues,
        "duplicates": {
            "zone_ids": sorted(set(duplicate_zone_ids)),
        },
        "writes_to_sheets": False,
        "writes_to_supabase": False,
        "payloads": payloads,
    }


def _id_field_for_table(table):
    return {
        "irrigation_zones": "zone_id",
        "irrigation_daily_plans": "daily_plan_id",
        "irrigation_plan_items": "plan_item_id",
        "irrigation_state_snapshots": "state_snapshot_id",
        "irrigation_events": "irrigation_event_id",
        "irrigation_auxiliary_devices": "auxiliary_device_id",
        "irrigation_auxiliary_tasks": "auxiliary_task_id",
        "irrigation_sensor_states": "sensor_state_id",
    }[table]


def run_dry_run(spreadsheet_name=DEFAULT_IRRIGATION_SHEET_NAME, import_batch_id=PLAN_ONLY_BATCH_ID):
    records = {
        ZONES_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, ZONES_SHEET),
        DAILY_PLAN_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, DAILY_PLAN_SHEET),
        STATE_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, STATE_SHEET),
        LOG_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, LOG_SHEET),
    }
    result = build_irrigation_dry_run_payload(records, import_batch_id=import_batch_id)
    result["source"]["spreadsheet_name"] = spreadsheet_name
    return result


def _report_without_payloads(report):
    report = dict(report)
    report.pop("payloads", None)
    return report


def _json_safe_value(value):
    if isinstance(value, (list, dict)):
        from psycopg.types.json import Jsonb

        return Jsonb(value)
    return value


def _upsert_rows(cursor, table_name, rows):
    if not rows:
        return 0

    from psycopg import sql

    primary_key = TABLE_PRIMARY_KEYS[table_name]
    columns = list(rows[0].keys())
    update_columns = [column for column in columns if column != primary_key]
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    column_sql = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    update_sql = sql.SQL(", ").join(
        sql.SQL("{} = excluded.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in update_columns
    )

    statement = sql.SQL(
        """
        insert into public.{table} ({columns})
        values ({placeholders})
        on conflict ({primary_key}) do update set {updates}
        """
    ).format(
        table=sql.Identifier(table_name),
        columns=column_sql,
        placeholders=placeholders,
        primary_key=sql.Identifier(primary_key),
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


def apply_irrigation_import(records, database_url, connect_factory=None):
    if not database_url:
        return {
            "success": False,
            "mode": "apply",
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
        }, 2

    if connect_factory is None:
        try:
            import psycopg
        except ImportError:
            return {
                "success": False,
                "mode": "apply",
                "writes_to_supabase": False,
                "writes_to_sheets": False,
                "status": "dependency_missing",
                "message": "Python database dependency is not installed.",
            }, 2
        connect_factory = psycopg.connect

    report = build_irrigation_dry_run_payload(records, import_batch_id=APPLY_IMPORT_BATCH_ID)
    payloads = report["payloads"]
    inserted_or_updated = {}

    try:
        with connect_factory(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                for table_name in TABLE_INSERT_ORDER:
                    inserted_or_updated[table_name] = _upsert_rows(
                        cursor,
                        table_name,
                        payloads[table_name],
                    )
            connection.commit()
    except Exception as exc:
        return {
            "success": False,
            "mode": "apply",
            "import_batch_id": APPLY_IMPORT_BATCH_ID,
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "status": "import_failed",
            "message": "Irrigation import failed and transaction was rolled back.",
            "error_type": exc.__class__.__name__,
        }, 1

    return {
        "success": True,
        "mode": "apply",
        "import_batch_id": APPLY_IMPORT_BATCH_ID,
        "writes_to_supabase": True,
        "writes_to_sheets": False,
        "status": "ok",
        "import_strategy": report["import_strategy"],
        "inserted_or_updated": inserted_or_updated,
        "payload_summary": report["payload_summary"],
        "source_summaries": report["source_summaries"],
        "link_issues": report["link_issues"],
        "duplicates": report["duplicates"],
    }, 0


def main():
    parser = argparse.ArgumentParser(description="Dry-run irrigation sheet to Supabase-shaped payload mapping.")
    parser.add_argument("--spreadsheet-name", default=DEFAULT_IRRIGATION_SHEET_NAME)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write mapped irrigation payloads to Supabase using DATABASE_URL.",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    load_local_env()

    records = {
        ZONES_SHEET: get_all_records_from_spreadsheet(args.spreadsheet_name, ZONES_SHEET),
        DAILY_PLAN_SHEET: get_all_records_from_spreadsheet(args.spreadsheet_name, DAILY_PLAN_SHEET),
        STATE_SHEET: get_all_records_from_spreadsheet(args.spreadsheet_name, STATE_SHEET),
        LOG_SHEET: get_all_records_from_spreadsheet(args.spreadsheet_name, LOG_SHEET),
    }
    if args.apply:
        result, exit_code = apply_irrigation_import(
            records,
            os.getenv(DATABASE_URL_ENV, "").strip(),
        )
    else:
        result = _report_without_payloads(
            build_irrigation_dry_run_payload(records, import_batch_id=PLAN_ONLY_BATCH_ID)
        )
        result["source"]["spreadsheet_name"] = args.spreadsheet_name
        exit_code = 0

    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
