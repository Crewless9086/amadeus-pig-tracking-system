import os
from datetime import datetime, timezone
from decimal import Decimal

from services.database_service import DATABASE_URL_ENV


def cancel_sales_transaction(sale_id, payload=None, database_url=None):
    sale_id = str(sale_id or "").strip()
    payload = dict(payload or {})
    cancelled_by = str(payload.get("cancelled_by", payload.get("created_by", ""))).strip()
    cancel_reason = str(payload.get("cancel_reason", payload.get("reason", ""))).strip()

    errors = []
    if not sale_id:
        errors.append("sale_id is required.")
    if not cancelled_by:
        errors.append("cancelled_by is required.")
    if not cancel_reason:
        errors.append("cancel_reason is required.")
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
                current = _fetch_transaction_for_update(cursor, sale_id)
                if not current:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "not_found",
                        "message": "Sales transaction was not found.",
                        "sale_id": sale_id,
                        "source": _source_metadata(writes_to_supabase=False),
                    }, 404

                current_status = current[1]
                if current_status == "Cancelled":
                    return {
                        "success": True,
                        "configured": True,
                        "status": "already_cancelled",
                        "sale_id": sale_id,
                        "sales_transaction": _row_to_transaction(current),
                        "source": _source_metadata(writes_to_supabase=False),
                    }, 200

                note = _build_cancel_note(current[3], cancelled_by, cancel_reason)
                updated = _mark_cancelled(cursor, sale_id, note)
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_transaction_cancel_failed",
            "message": "Sales transaction cancel failed and was rolled back.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "cancelled",
        "sale_id": sale_id,
        "sales_transaction": _row_to_transaction(updated),
        "source": _source_metadata(writes_to_supabase=True),
    }, 200


def _fetch_transaction_for_update(cursor, sale_id):
    cursor.execute(
        """
        select
            sale_id,
            sale_status,
            payment_status,
            notes,
            updated_at
        from public.sales_transactions
        where sale_id = %s
        for update
        """,
        (sale_id,),
    )
    return cursor.fetchone()


def _mark_cancelled(cursor, sale_id, note):
    cursor.execute(
        """
        update public.sales_transactions
        set
            sale_status = 'Cancelled',
            payment_status = 'Cancelled',
            notes = %s,
            updated_at = now()
        where sale_id = %s
        returning
            sale_id,
            sale_status,
            payment_status,
            notes,
            updated_at
        """,
        (note, sale_id),
    )
    return cursor.fetchone()


def _build_cancel_note(existing_notes, cancelled_by, cancel_reason):
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    audit_note = f"Cancelled {timestamp} by {cancelled_by}: {cancel_reason}"
    existing_notes = str(existing_notes or "").strip()
    if not existing_notes:
        return audit_note
    return f"{existing_notes}\n\n{audit_note}"


def _row_to_transaction(row):
    return _json_safe_row({
        "sale_id": row[0],
        "sale_status": row[1],
        "payment_status": row[2],
        "notes": row[3],
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
