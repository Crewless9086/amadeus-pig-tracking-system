import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.order_sales_import_dry_run import (
    build_order_sales_import_dry_run,
    load_sheet_rows,
    payload_summary,
)
from services.database_service import DATABASE_URL_ENV


IMPORT_BATCH_ID = "IMPORT-20260521-COMPLETED-ORDERS-V1"
IMPORT_TIMESTAMP = "2026-05-21T00:00:00+00:00"
TABLE_PRIMARY_KEYS = {
    "sales_pricing": "pricing_id",
    "orders": "order_id",
    "order_lines": "order_line_id",
    "order_intakes": "intake_id",
    "order_intake_items": "intake_item_id",
    "order_documents": "document_id",
    "order_status_logs": "status_log_id",
}
TABLE_INSERT_ORDER = [
    "sales_pricing",
    "orders",
    "order_lines",
    "order_intakes",
    "order_intake_items",
    "order_documents",
    "order_status_logs",
]


def load_local_env(load_dotenv_func=None):
    if load_dotenv_func is None:
        try:
            from dotenv import load_dotenv as load_dotenv_func
        except ImportError:
            return False

    return load_dotenv_func(ROOT_DIR / ".env")


def prepare_shadow_payloads(sheet_rows):
    report = build_order_sales_import_dry_run(sheet_rows)
    payloads = {
        table: [
            normalize_shadow_row(table, dict(row, import_batch_id=IMPORT_BATCH_ID))
            for row in rows
        ]
        for table, rows in report["payloads"].items()
    }
    return report, payloads


def normalize_shadow_row(table_name, row):
    if table_name == "sales_pricing":
        row["created_at"] = row.get("created_at") or row.get("effective_from") or IMPORT_TIMESTAMP
        row["updated_at"] = row.get("updated_at") or row["created_at"]
    elif table_name == "orders":
        row["created_at"] = row.get("created_at") or row.get("order_date") or IMPORT_TIMESTAMP
        row["updated_at"] = row.get("updated_at") or row["created_at"]
    elif table_name == "order_lines":
        row["created_at"] = row.get("created_at") or IMPORT_TIMESTAMP
        row["updated_at"] = row.get("updated_at") or row["created_at"]
    elif table_name == "order_intakes":
        row["created_at"] = row.get("created_at") or IMPORT_TIMESTAMP
        row["updated_at"] = row.get("updated_at") or row["created_at"]
    elif table_name == "order_intake_items":
        row["created_at"] = row.get("created_at") or IMPORT_TIMESTAMP
        row["updated_at"] = row.get("updated_at") or row["created_at"]
    elif table_name == "order_documents":
        row["created_at"] = row.get("created_at") or IMPORT_TIMESTAMP
    elif table_name == "order_status_logs":
        row["created_at"] = row.get("created_at") or row.get("status_date") or IMPORT_TIMESTAMP
    return row


def import_plan(sheet_rows):
    report, payloads = prepare_shadow_payloads(sheet_rows)
    return {
        "success": True,
        "mode": "plan_only",
        "import_batch_id": IMPORT_BATCH_ID,
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "payload_summary": payload_summary(payloads),
        "summaries": report["summaries"],
        "link_issues": report["link_issues"],
    }


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


def apply_shadow_import(sheet_rows, database_url, connect_factory=None):
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

    report, payloads = prepare_shadow_payloads(sheet_rows)
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
            "import_batch_id": IMPORT_BATCH_ID,
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "status": "import_failed",
            "message": "Shadow import failed and transaction was rolled back.",
            "error_type": exc.__class__.__name__,
        }, 1

    return {
        "success": True,
        "mode": "apply",
        "import_batch_id": IMPORT_BATCH_ID,
        "writes_to_supabase": True,
        "writes_to_sheets": False,
        "status": "ok",
        "inserted_or_updated": inserted_or_updated,
        "payload_summary": payload_summary(payloads),
        "source_summaries": report["summaries"],
    }, 0


def main():
    parser = argparse.ArgumentParser(
        description="Shadow-import the approved completed-order sales boundary into Supabase."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the approved shadow import payloads to Supabase using DATABASE_URL.",
    )
    parser.add_argument(
        "--payload-samples",
        type=int,
        default=0,
        help="Include this many payload samples per target table in plan mode.",
    )
    args = parser.parse_args()
    load_local_env()

    sheet_rows = load_sheet_rows()
    if args.apply:
        report, exit_code = apply_shadow_import(
            sheet_rows,
            os.getenv(DATABASE_URL_ENV, "").strip(),
        )
    else:
        report = import_plan(sheet_rows)
        if args.payload_samples:
            _, payloads = prepare_shadow_payloads(sheet_rows)
            report["payload_samples"] = {
                table: rows[: args.payload_samples]
                for table, rows in payloads.items()
            }
        exit_code = 0

    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
