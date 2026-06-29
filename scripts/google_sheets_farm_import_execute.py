import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.google_sheets_farm_import_dry_run import (
    build_policy_backfill_verifier,
    load_sheet_rows,
)
from services.database_service import DATABASE_URL_ENV


IMPORT_BATCH_ID = "GS-MIG-5-2026-06-29"

IMPORT_ORDER = [
    "pens",
    "pigs",
    "farm_products",
    "app_settings",
    "litters",
    "mating_events",
    "pig_weight_events",
    "pig_location_events",
    "pig_medical_events",
]

TABLE_COLUMNS = {
    "pens": [
        "pen_id", "pen_name", "pen_type", "capacity", "is_active", "pen_notes",
        "source_sheet_row", "import_batch_id",
    ],
    "pigs": [
        "pig_id", "tag_number", "pig_name", "status", "on_farm", "animal_type", "sex",
        "date_of_birth", "birth_month", "birth_year", "breed_type", "colour_markings",
        "mother_pig_id", "father_pig_id", "litter_id", "initial_pen_id", "purpose",
        "notes", "source_sheet_row", "import_batch_id",
    ],
    "farm_products": [
        "product_id", "product_name", "product_category", "default_dose", "dose_unit",
        "default_withdrawal_days", "supplier", "batch_tracking_required", "is_active",
        "product_notes", "source_sheet_row", "import_batch_id",
    ],
    "app_settings": [
        "setting_key", "setting_value", "description", "source_sheet_row", "import_batch_id",
    ],
    "litters": [
        "litter_id", "farrowing_date", "sow_pig_id", "boar_pig_id", "sow_tag_number",
        "boar_tag_number", "total_born", "born_alive", "stillborn_count", "mummified_count",
        "male_count", "female_count", "unknown_sex_count", "weaned_count", "litter_status",
        "litter_notes", "source_sheet_row", "import_batch_id",
    ],
    "mating_events": [
        "mating_id", "sow_pig_id", "sow_tag_number", "boar_pig_id", "boar_tag_number",
        "mating_date", "mating_method", "exposure_group", "expected_pregnancy_check_date",
        "pregnancy_check_date", "pregnancy_check_result", "expected_farrowing_date",
        "farrowing_date", "outcome", "related_litter_id", "mating_notes",
        "source_sheet_row", "import_batch_id",
    ],
    "pig_weight_events": [
        "weight_event_id", "pig_id", "weight_date", "weight_kg", "weighed_by",
        "scale_used", "condition_notes", "stage_at_weighing", "source",
        "source_sheet_row", "import_batch_id",
    ],
    "pig_location_events": [
        "location_event_id", "pig_id", "move_date", "from_pen_id", "to_pen_id",
        "reason_for_move", "moved_by", "group_batch_id", "move_notes", "source",
        "source_sheet_row", "import_batch_id",
    ],
    "pig_medical_events": [
        "medical_event_id", "pig_id", "treatment_date", "treatment_type", "product_id",
        "product_name", "dose", "dose_unit", "route", "reason_for_treatment",
        "batch_lot_number", "withdrawal_days", "withdrawal_end_date", "given_by",
        "follow_up_required", "follow_up_date", "medical_notes", "source_sheet_row",
        "import_batch_id",
    ],
}


def clean_payload_row(table, row, import_batch_id):
    allowed = set(TABLE_COLUMNS[table])
    clean_row = {key: row.get(key) for key in TABLE_COLUMNS[table] if key in allowed}
    if "import_batch_id" in allowed:
        clean_row["import_batch_id"] = import_batch_id
    return clean_row


def build_import_payloads(sheet_rows, import_batch_id=IMPORT_BATCH_ID):
    verifier = build_policy_backfill_verifier(sheet_rows)
    review_summary = verifier["review_summary"]
    if review_summary["by_type"].get("missing_pig_id_weight", 0):
        raise ValueError("Refusing import while missing-Pig_ID weight rows remain.")

    payloads = {}
    for table in IMPORT_ORDER:
        payloads[table] = [
            clean_payload_row(table, row, import_batch_id)
            for row in verifier["canonical_payloads"].get(table, [])
        ]

    return {
        "success": True,
        "mode": "controlled_import_plan",
        "import_batch_id": import_batch_id,
        "payloads": payloads,
        "payload_summary": {table: len(rows) for table, rows in payloads.items()},
        "review_summary": review_summary,
        "verification": verifier["verification"],
        "writes_to_sheets": False,
    }


def get_database_url():
    load_dotenv(ROOT_DIR / ".env")
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured.")
    return database_url


def count_tables(cursor):
    counts = {}
    for table in IMPORT_ORDER:
        cursor.execute(f"select count(*) from public.{table}")
        counts[table] = cursor.fetchone()[0]
    return counts


def insert_rows(cursor, table, rows):
    if not rows:
        return 0
    columns = TABLE_COLUMNS[table]
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_target = columns[0]
    sql = f"""
        insert into public.{table} ({column_sql})
        values ({placeholders})
        on conflict ({conflict_target}) do nothing
    """
    values = [tuple(row.get(column) for column in columns) for row in rows]
    cursor.executemany(sql, values)
    return len(rows)


def execute_import(payloads):
    import psycopg

    database_url = get_database_url()
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            before_counts = count_tables(cursor)
            non_empty = {table: count for table, count in before_counts.items() if count}
            if non_empty:
                raise RuntimeError(f"Refusing import because canonical tables are not empty: {non_empty}")

            inserted = {}
            for table in IMPORT_ORDER:
                inserted[table] = insert_rows(cursor, table, payloads[table])

            after_counts = count_tables(cursor)

    return {
        "before_counts": before_counts,
        "inserted": inserted,
        "after_counts": after_counts,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the controlled GS-MIG-5 Google Sheets farm data import."
    )
    parser.add_argument("--execute", action="store_true", help="Write clean canonical rows to Supabase.")
    parser.add_argument("--import-batch-id", default=IMPORT_BATCH_ID)
    args = parser.parse_args(argv)

    try:
        sheet_rows = load_sheet_rows()
        plan = build_import_payloads(sheet_rows, args.import_batch_id)
        report = {
            "success": True,
            "mode": "execute" if args.execute else "dry_run",
            "import_batch_id": args.import_batch_id,
            "writes_to_supabase": bool(args.execute),
            "writes_to_sheets": False,
            "payload_summary": plan["payload_summary"],
            "review_summary": plan["review_summary"],
            "verification": plan["verification"],
        }

        if args.execute:
            report["database_result"] = execute_import(plan["payloads"])
            report["verification"]["no_write_performed"] = False
    except Exception as exc:
        report = {
            "success": False,
            "mode": "execute" if args and args.execute else "dry_run",
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
