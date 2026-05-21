import os
from decimal import Decimal

from modules.orders.order_read import get_order_detail
from services.database_service import DATABASE_URL_ENV


DEFAULT_SHADOW_IMPORT_BATCH_ID = "IMPORT-20260521-COMPLETED-ORDERS-V1"
ORDER_COMPARE_FIELDS = [
    "order_id",
    "customer_name",
    "order_status",
    "approval_status",
    "payment_status",
    "payment_method",
    "collection_location",
    "reserved_pig_count",
    "final_total",
]
LINE_COMPARE_FIELDS = [
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
]


def compare_shadow_order(order_id, import_batch_id=DEFAULT_SHADOW_IMPORT_BATCH_ID, database_url=None):
    order_id = str(order_id or "").strip()
    import_batch_id = str(import_batch_id or DEFAULT_SHADOW_IMPORT_BATCH_ID).strip()
    if not order_id:
        raise ValueError("order_id is required.")

    sheet_detail = get_order_detail(order_id)
    shadow_result, status_code = get_shadow_order_detail(
        order_id,
        import_batch_id=import_batch_id,
        database_url=database_url,
    )
    if status_code != 200:
        return shadow_result, status_code

    if not sheet_detail:
        return {
            "success": False,
            "status": "sheet_order_missing",
            "order_id": order_id,
            "message": "Order exists in Supabase shadow data but not in Google Sheets.",
        }, 404

    comparison = compare_order_details(
        sheet_detail,
        shadow_result["shadow_detail"],
    )

    return {
        "success": comparison["mismatch_count"] == 0,
        "status": "ok" if comparison["mismatch_count"] == 0 else "mismatches_found",
        "mode": "shadow_compare",
        "order_id": order_id,
        "import_batch_id": import_batch_id,
        "comparison": comparison,
        "source": {
            "live_source": "google_sheets",
            "shadow_source": "supabase",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
    }, 200


def get_shadow_order_detail(order_id, import_batch_id=DEFAULT_SHADOW_IMPORT_BATCH_ID, database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                order = _fetch_one_dict(
                    cursor,
                    """
                    select *
                    from public.orders
                    where order_id = %s and import_batch_id = %s
                    """,
                    (order_id, import_batch_id),
                )
                if not order:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "shadow_order_missing",
                        "order_id": order_id,
                        "import_batch_id": import_batch_id,
                        "message": "Order was not found in Supabase shadow data.",
                    }, 404

                lines = _fetch_all_dicts(
                    cursor,
                    """
                    select *
                    from public.order_lines
                    where order_id = %s and import_batch_id = %s
                    order by order_line_id
                    """,
                    (order_id, import_batch_id),
                )
                status_logs = _fetch_all_dicts(
                    cursor,
                    """
                    select *
                    from public.order_status_logs
                    where order_id = %s and import_batch_id = %s
                    order by status_log_id
                    """,
                    (order_id, import_batch_id),
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "shadow_read_failed",
            "message": "Supabase shadow order read failed.",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "order_id": order_id,
        "import_batch_id": import_batch_id,
        "shadow_detail": {
            "order": _json_safe_row(order),
            "lines": [_json_safe_row(row) for row in lines],
            "status_logs": [_json_safe_row(row) for row in status_logs],
        },
    }, 200


def compare_order_details(sheet_detail, shadow_detail):
    sheet_order = sheet_detail.get("order", {})
    shadow_order = shadow_detail.get("order", {})
    sheet_lines = sheet_detail.get("lines", [])
    shadow_lines = shadow_detail.get("lines", [])

    order_mismatches = compare_fields(
        "order",
        sheet_order,
        shadow_order,
        ORDER_COMPARE_FIELDS,
        row_id=sheet_order.get("order_id") or shadow_order.get("order_id"),
    )
    line_result = compare_lines(sheet_lines, shadow_lines)
    mismatch_count = len(order_mismatches) + line_result["mismatch_count"]

    return {
        "mismatch_count": mismatch_count,
        "order_field_mismatches": order_mismatches,
        "line_comparison": line_result,
    }


def compare_lines(sheet_lines, shadow_lines):
    sheet_by_id = {normalize_value(row.get("order_line_id")): row for row in sheet_lines}
    shadow_by_id = {normalize_value(row.get("order_line_id")): row for row in shadow_lines}
    sheet_ids = set(sheet_by_id)
    shadow_ids = set(shadow_by_id)
    missing_ids = sorted(sheet_ids - shadow_ids)
    extra_ids = sorted(shadow_ids - sheet_ids)
    field_mismatches = []

    for line_id in sorted(sheet_ids & shadow_ids):
        field_mismatches.extend(compare_fields(
            "order_line",
            sheet_by_id[line_id],
            shadow_by_id[line_id],
            LINE_COMPARE_FIELDS,
            row_id=line_id,
        ))
        if len(field_mismatches) >= 20:
            break

    mismatch_count = len(missing_ids) + len(extra_ids) + len(field_mismatches)
    return {
        "sheet_count": len(sheet_lines),
        "shadow_count": len(shadow_lines),
        "missing_count": len(missing_ids),
        "extra_count": len(extra_ids),
        "field_mismatch_count": len(field_mismatches),
        "mismatch_count": mismatch_count,
        "missing_sample": missing_ids[:5],
        "extra_sample": extra_ids[:5],
        "field_mismatch_sample": field_mismatches[:5],
    }


def compare_fields(kind, expected, actual, fields, row_id=""):
    mismatches = []
    for field in fields:
        expected_value = normalize_value(expected.get(field))
        actual_value = normalize_value(actual.get(field))
        if expected_value != actual_value:
            mismatches.append({
                "kind": kind,
                "id": normalize_value(row_id),
                "field": field,
                "expected": expected_value,
                "actual": actual_value,
            })
    return mismatches


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
    return str(value).strip() or None


def _fetch_one_dict(cursor, query, params):
    rows = _fetch_all_dicts(cursor, query, params)
    return rows[0] if rows else None


def _fetch_all_dicts(cursor, query, params):
    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _json_safe_row(row):
    return {
        key: _json_safe_value(value)
        for key, value in row.items()
    }


def _json_safe_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
