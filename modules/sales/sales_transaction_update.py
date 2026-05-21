import os
from datetime import date, datetime, timezone
from decimal import Decimal

from modules.pig_weights.pig_weights_utils import parse_sheet_date, to_float
from modules.sales.sales_transaction_validation import (
    ALLOWED_PAYMENT_STATUSES,
    ALLOWED_SALE_STATUSES,
)
from services.database_service import DATABASE_URL_ENV


def update_slaughter_sale_payment(sale_id, payload=None, database_url=None):
    sale_id = str(sale_id or "").strip()
    payload = dict(payload or {})

    updated_by = str(payload.get("updated_by", payload.get("created_by", ""))).strip()
    update_reason = str(payload.get("update_reason", payload.get("reason", ""))).strip()
    payment_status = str(payload.get("payment_status", "")).strip()
    sale_status = str(payload.get("sale_status", "")).strip()
    payment_method = str(payload.get("payment_method", "")).strip()
    line_total = _parse_money(payload.get("line_total", payload.get("unit_price", "")))
    carcass_weight_kg = _parse_optional_number(payload.get("carcass_weight_kg", ""))
    payment_date = _parse_optional_date(payload.get("payment_date", ""))

    errors = []
    if not sale_id:
        errors.append("sale_id is required.")
    if not updated_by:
        errors.append("updated_by is required.")
    if not update_reason:
        errors.append("update_reason is required.")
    if payment_status not in ALLOWED_PAYMENT_STATUSES:
        errors.append("payment_status must be Unpaid, Deposit_Paid, Part_Paid, Paid, or Cancelled.")
    if sale_status not in ALLOWED_SALE_STATUSES:
        errors.append("sale_status must be Draft, Confirmed, Completed, or Cancelled.")
    if sale_status == "Cancelled" or payment_status == "Cancelled":
        errors.append("Use the cancel endpoint for cancelled transactions.")
    if line_total is None:
        errors.append("line_total is required and must be a number.")
    elif line_total < 0:
        errors.append("line_total cannot be negative.")
    if payment_date == "invalid":
        errors.append("payment_date must be a valid date.")
    if payment_status == "Paid" and not payment_date:
        errors.append("payment_date is required when payment_status is Paid.")
    if carcass_weight_kg is not None and carcass_weight_kg < 0:
        errors.append("carcass_weight_kg cannot be negative.")
    if errors:
        return _failure("validation_failed", errors, 400)

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
                current = _fetch_slaughter_transaction_for_update(cursor, sale_id)
                if not current:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "not_found",
                        "message": "Slaughter sales transaction was not found.",
                        "sale_id": sale_id,
                        "source": _source_metadata(writes_to_supabase=False),
                    }, 404

                if current[2] == "Cancelled":
                    return {
                        "success": False,
                        "configured": True,
                        "status": "already_cancelled",
                        "message": "Cancelled transactions cannot be updated.",
                        "sale_id": sale_id,
                        "source": _source_metadata(writes_to_supabase=False),
                    }, 409

                items = _fetch_items_for_update(cursor, sale_id)
                if not items:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "item_not_found",
                        "message": "Sales transaction item was not found.",
                        "sale_id": sale_id,
                        "source": _source_metadata(writes_to_supabase=False),
                    }, 404

                note = _build_update_note(
                    current[5],
                    updated_by,
                    update_reason,
                    current_line_total=current[4],
                    new_line_total=line_total,
                    current_payment_status=current[3],
                    new_payment_status=payment_status,
                    current_sale_status=current[2],
                    new_sale_status=sale_status,
                    payment_date=payment_date,
                )
                updated_header = _update_transaction_header(
                    cursor,
                    sale_id,
                    payment_status,
                    payment_method,
                    sale_status,
                    line_total,
                    payment_date,
                    note,
                )
                updated_item = None
                if len(items) == 1:
                    updated_item = _update_first_item(
                        cursor,
                        items[0][0],
                        line_total,
                        carcass_weight_kg,
                    )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_transaction_update_failed",
            "message": "Sales transaction update failed and was rolled back.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "updated",
        "sale_id": sale_id,
        "sales_transaction": _row_to_transaction(updated_header),
        "item": _row_to_item(updated_item) if updated_item else None,
        "items_updated": 1 if updated_item else 0,
        "source": _source_metadata(writes_to_supabase=True),
    }, 200


def _fetch_slaughter_transaction_for_update(cursor, sale_id):
    cursor.execute(
        """
        select
            sale_id,
            sale_stream,
            sale_status,
            payment_status,
            gross_total,
            notes
        from public.sales_transactions
        where sale_id = %s
        and sale_stream = 'Slaughter'
        for update
        """,
        (sale_id,),
    )
    return cursor.fetchone()


def _fetch_items_for_update(cursor, sale_id):
    cursor.execute(
        """
        select
            sale_item_id,
            line_total,
            carcass_weight_kg
        from public.sales_transaction_items
        where sale_id = %s
        order by created_at asc, sale_item_id asc
        for update
        """,
        (sale_id,),
    )
    return cursor.fetchall()


def _update_transaction_header(cursor, sale_id, payment_status, payment_method, sale_status, line_total, payment_date, note):
    cursor.execute(
        """
        update public.sales_transactions
        set
            gross_total = %s,
            net_total = %s,
            payment_status = %s,
            payment_method = %s,
            payment_date = %s,
            sale_status = %s,
            notes = %s,
            updated_at = now()
        where sale_id = %s
        returning
            sale_id,
            gross_total,
            net_total,
            payment_status,
            payment_method,
            payment_date,
            sale_status,
            notes,
            updated_at
        """,
        (
            line_total,
            line_total,
            payment_status,
            payment_method,
            payment_date,
            sale_status,
            note,
            sale_id,
        ),
    )
    return cursor.fetchone()


def _update_first_item(cursor, sale_item_id, line_total, carcass_weight_kg):
    cursor.execute(
        """
        update public.sales_transaction_items
        set
            unit_price = %s,
            line_total = %s,
            carcass_weight_kg = %s,
            updated_at = now()
        where sale_item_id = %s
        returning
            sale_item_id,
            unit_price,
            line_total,
            carcass_weight_kg,
            updated_at
        """,
        (
            line_total,
            line_total,
            carcass_weight_kg,
            sale_item_id,
        ),
    )
    return cursor.fetchone()


def _build_update_note(
    existing_notes,
    updated_by,
    update_reason,
    current_line_total,
    new_line_total,
    current_payment_status,
    new_payment_status,
    current_sale_status,
    new_sale_status,
    payment_date,
):
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    audit_note = (
        f"Payment update {timestamp} by {updated_by}: {update_reason}. "
        f"Amount {current_line_total} -> {new_line_total}; "
        f"payment {current_payment_status} -> {new_payment_status}; "
        f"status {current_sale_status} -> {new_sale_status}; "
        f"payment date {payment_date or 'not set'}."
    )
    existing_notes = str(existing_notes or "").strip()
    if not existing_notes:
        return audit_note
    return f"{existing_notes}\n\n{audit_note}"


def _parse_money(value):
    parsed = _parse_optional_number(value)
    if parsed is None:
        return None
    return round(parsed, 2)


def _parse_optional_number(value):
    if value in (None, ""):
        return None
    return to_float(value)


def _parse_optional_date(value):
    if value in (None, ""):
        return None
    parsed = parse_sheet_date(value)
    if not parsed:
        return "invalid"
    return _date_iso(parsed)


def _date_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _row_to_transaction(row):
    return _json_safe_row({
        "sale_id": row[0],
        "gross_total": row[1],
        "net_total": row[2],
        "payment_status": row[3],
        "payment_method": row[4],
        "payment_date": row[5],
        "sale_status": row[6],
        "notes": row[7],
        "updated_at": row[8],
    })


def _row_to_item(row):
    return _json_safe_row({
        "sale_item_id": row[0],
        "unit_price": row[1],
        "line_total": row[2],
        "carcass_weight_kg": row[3],
        "updated_at": row[4],
    })


def _failure(status, errors, status_code):
    return {
        "success": False,
        "status": status,
        "errors": errors,
        "source": _source_metadata(writes_to_supabase=False),
    }, status_code


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


def _source_metadata(writes_to_supabase):
    return {
        "source": "supabase",
        "writes_to_sheets": False,
        "writes_to_supabase": writes_to_supabase,
    }
