import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.order_sales_shadow_import import (
    IMPORT_BATCH_ID,
    TABLE_INSERT_ORDER,
    load_local_env,
    prepare_shadow_payloads,
)
from scripts.order_sales_import_dry_run import load_sheet_rows
from services.database_service import DATABASE_URL_ENV


COMPARE_FIELDS = {
    "sales_pricing": [
        "pricing_id",
        "sale_category",
        "weight_band",
        "sex",
        "unit_price",
        "currency",
        "active",
        "source_sheet_row",
        "import_batch_id",
    ],
    "orders": [
        "order_id",
        "customer_name",
        "order_status",
        "approval_status",
        "payment_status",
        "payment_method",
        "collection_location",
        "reserved_pig_count",
        "final_total",
        "source_sheet_row",
        "import_batch_id",
    ],
    "order_lines": [
        "order_line_id",
        "order_id",
        "pig_id",
        "tag_number",
        "sale_category",
        "weight_band",
        "sex",
        "current_weight_kg",
        "unit_price",
        "line_status",
        "reserved_status",
        "source_sheet_row",
        "import_batch_id",
    ],
    "order_intakes": ["intake_id", "import_batch_id"],
    "order_intake_items": ["intake_item_id", "import_batch_id"],
    "order_documents": ["document_id", "import_batch_id"],
    "order_status_logs": [
        "status_log_id",
        "order_id",
        "old_status",
        "new_status",
        "changed_by",
        "change_source",
        "source_sheet_row",
        "import_batch_id",
    ],
}

PRIMARY_KEYS = {
    "sales_pricing": "pricing_id",
    "orders": "order_id",
    "order_lines": "order_line_id",
    "order_intakes": "intake_id",
    "order_intake_items": "intake_item_id",
    "order_documents": "document_id",
    "order_status_logs": "status_log_id",
}


def compare_shadow_import(sheet_rows, database_url, import_batch_id=IMPORT_BATCH_ID, connect_factory=None):
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
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
            }, 2
        connect_factory = psycopg.connect

    _report, expected_payloads = prepare_shadow_payloads(sheet_rows)

    try:
        actual_payloads = read_supabase_shadow_rows(
            database_url,
            import_batch_id,
            connect_factory,
        )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "comparison_failed",
            "message": "Shadow read comparison failed.",
            "error_type": exc.__class__.__name__,
        }, 1

    table_results = {
        table_name: compare_table(
            table_name,
            expected_payloads.get(table_name, []),
            actual_payloads.get(table_name, []),
        )
        for table_name in TABLE_INSERT_ORDER
    }
    mismatch_count = sum(result["mismatch_count"] for result in table_results.values())

    return {
        "success": mismatch_count == 0,
        "configured": True,
        "status": "ok" if mismatch_count == 0 else "mismatches_found",
        "import_batch_id": import_batch_id,
        "mismatch_count": mismatch_count,
        "tables": table_results,
    }, 0 if mismatch_count == 0 else 1


def read_supabase_shadow_rows(database_url, import_batch_id, connect_factory):
    actual = {}
    with connect_factory(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            for table_name in TABLE_INSERT_ORDER:
                fields = COMPARE_FIELDS[table_name]
                field_sql = ", ".join(fields)
                primary_key = PRIMARY_KEYS[table_name]
                cursor.execute(
                    f"""
                    select {field_sql}
                    from public.{table_name}
                    where import_batch_id = %s
                    order by {primary_key}
                    """,
                    (import_batch_id,),
                )
                actual[table_name] = [
                    dict(zip(fields, row))
                    for row in cursor.fetchall()
                ]
    return actual


def compare_table(table_name, expected_rows, actual_rows):
    primary_key = PRIMARY_KEYS[table_name]
    fields = COMPARE_FIELDS[table_name]
    expected_by_id = {normalize_value(row.get(primary_key)): row for row in expected_rows}
    actual_by_id = {normalize_value(row.get(primary_key)): row for row in actual_rows}
    expected_ids = set(expected_by_id)
    actual_ids = set(actual_by_id)

    missing_ids = sorted(expected_ids - actual_ids)
    extra_ids = sorted(actual_ids - expected_ids)
    field_mismatches = []

    for row_id in sorted(expected_ids & actual_ids):
        expected = expected_by_id[row_id]
        actual = actual_by_id[row_id]
        for field in fields:
            expected_value = normalize_value(expected.get(field))
            actual_value = normalize_value(actual.get(field))
            if expected_value != actual_value:
                field_mismatches.append({
                    "id": row_id,
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                })
                if len(field_mismatches) >= 20:
                    break
        if len(field_mismatches) >= 20:
            break

    mismatch_count = len(missing_ids) + len(extra_ids) + len(field_mismatches)
    return {
        "expected_count": len(expected_rows),
        "actual_count": len(actual_rows),
        "missing_count": len(missing_ids),
        "extra_count": len(extra_ids),
        "field_mismatch_count": len(field_mismatches),
        "mismatch_count": mismatch_count,
        "missing_sample": missing_ids[:5],
        "extra_sample": extra_ids[:5],
        "field_mismatch_sample": field_mismatches[:5],
    }


def normalize_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 3)
    return str(value).strip()


def main():
    load_local_env()
    report, exit_code = compare_shadow_import(
        load_sheet_rows(),
        os.getenv(DATABASE_URL_ENV, "").strip(),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
