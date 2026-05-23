import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.irrigation_import_dry_run import (
    DAILY_PLAN_SHEET,
    DEFAULT_IRRIGATION_SHEET_NAME,
    LOG_SHEET,
    PLAN_ONLY_BATCH_ID,
    STATE_SHEET,
    TABLE_INSERT_ORDER,
    ZONES_SHEET,
    _report_without_payloads,
    _upsert_rows,
    build_irrigation_dry_run_payload,
    load_local_env,
)
from services.database_service import DATABASE_URL_ENV
from services.google_sheets_service import get_all_records_from_spreadsheet


ZA_TZ = ZoneInfo("Africa/Johannesburg")


def today_za():
    return datetime.now(ZA_TZ).date().isoformat()


def _clean(value):
    return str(value or "").strip()


def _date_part(value):
    return _clean(value)[:10]


def filter_daily_sync_records(records, sync_date):
    plan_rows = [
        row for row in records.get(DAILY_PLAN_SHEET, [])
        if _date_part(row.get("date")) == sync_date and _clean(row.get("plan_id"))
    ]
    today_plan_ids = {_clean(row.get("plan_id")) for row in plan_rows}
    log_rows = []
    for row in records.get(LOG_SHEET, []):
        timestamp_date = _date_part(row.get("timestamp"))
        plan_id = _clean(row.get("plan_id"))
        reason = _clean(row.get("reason"))
        if timestamp_date == sync_date or plan_id in today_plan_ids or sync_date in reason:
            log_rows.append(row)

    return {
        ZONES_SHEET: records.get(ZONES_SHEET, []),
        DAILY_PLAN_SHEET: plan_rows,
        STATE_SHEET: records.get(STATE_SHEET, []),
        LOG_SHEET: log_rows,
    }


def load_sheet_rows(spreadsheet_name=DEFAULT_IRRIGATION_SHEET_NAME):
    return {
        ZONES_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, ZONES_SHEET),
        DAILY_PLAN_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, DAILY_PLAN_SHEET),
        STATE_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, STATE_SHEET),
        LOG_SHEET: get_all_records_from_spreadsheet(spreadsheet_name, LOG_SHEET),
    }


def build_daily_sync_plan(records, sync_date, import_batch_id=None):
    import_batch_id = import_batch_id or f"SYNC-IRRIGATION-{sync_date}"
    filtered_records = filter_daily_sync_records(records, sync_date)
    report = build_irrigation_dry_run_payload(filtered_records, import_batch_id=import_batch_id)
    report["mode"] = "plan_only"
    report["sync_date"] = sync_date
    report["sync_scope"] = {
        "zones": "all active/configured rows from ZONES",
        "daily_plan": "requested date only",
        "state": "latest STATE rows, upserted by state_snapshot_id on apply",
        "events": "rows dated for the requested date or linked to the requested date's plan rows",
    }
    return report


def apply_daily_sync(records, sync_date, database_url, connect_factory=None):
    if not database_url:
        return {
            "success": False,
            "mode": "apply",
            "sync_date": sync_date,
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
                "sync_date": sync_date,
                "writes_to_supabase": False,
                "writes_to_sheets": False,
                "status": "dependency_missing",
                "message": "Python database dependency is not installed.",
            }, 2
        connect_factory = psycopg.connect

    import_batch_id = f"SYNC-IRRIGATION-{sync_date}"
    report = build_daily_sync_plan(records, sync_date, import_batch_id=import_batch_id)
    payloads = report["payloads"]
    inserted_or_updated = {}

    try:
        with connect_factory(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                for table_name in TABLE_INSERT_ORDER:
                    inserted_or_updated[table_name] = _upsert_rows(cursor, table_name, payloads[table_name])
            connection.commit()
    except Exception as exc:
        return {
            "success": False,
            "mode": "apply",
            "sync_date": sync_date,
            "import_batch_id": import_batch_id,
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "status": "sync_failed",
            "message": "Irrigation daily sync failed and transaction was rolled back.",
            "error_type": exc.__class__.__name__,
        }, 1

    return {
        "success": True,
        "mode": "apply",
        "sync_date": sync_date,
        "import_batch_id": import_batch_id,
        "writes_to_supabase": True,
        "writes_to_sheets": False,
        "status": "ok",
        "inserted_or_updated": inserted_or_updated,
        "payload_summary": report["payload_summary"],
        "source_summaries": report["source_summaries"],
        "link_issues": report["link_issues"],
        "duplicates": report["duplicates"],
        "sync_scope": report["sync_scope"],
        "import_strategy": report["import_strategy"],
    }, 0


def main():
    parser = argparse.ArgumentParser(description="Sync today's irrigation sheet plan/state/events into Supabase.")
    parser.add_argument("--spreadsheet-name", default=DEFAULT_IRRIGATION_SHEET_NAME)
    parser.add_argument("--date", default=today_za())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    load_local_env()

    records = load_sheet_rows(args.spreadsheet_name)
    if args.apply:
        result, exit_code = apply_daily_sync(
            records,
            args.date,
            os.getenv(DATABASE_URL_ENV, "").strip(),
        )
    else:
        result = _report_without_payloads(
            build_daily_sync_plan(records, args.date, import_batch_id=PLAN_ONLY_BATCH_ID)
        )
        result["source"]["spreadsheet_name"] = args.spreadsheet_name
        exit_code = 0

    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
