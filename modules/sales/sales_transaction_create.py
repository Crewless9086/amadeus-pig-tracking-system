import os
import uuid
from datetime import datetime
from decimal import Decimal

from modules.sales.sales_transaction_validation import validate_sales_transaction_payload
from services.database_service import DATABASE_URL_ENV


def create_sales_transaction(payload, database_url=None):
    payload = dict(payload or {})
    payload.setdefault("sale_stream", "Slaughter")
    payload.setdefault("sale_status", "Confirmed")
    payload.setdefault("payment_status", "Unpaid")

    created_by = str(payload.get("created_by", "")).strip()
    if not created_by:
        return _failure(
            "validation_failed",
            ["created_by is required."],
            400,
        )

    validation = validate_sales_transaction_payload(payload)
    if not validation["is_valid"]:
        return _failure("validation_failed", validation["errors"], 400)

    cleaned = validation["cleaned_data"]
    if cleaned["sale_stream"] != "Slaughter":
        return _failure(
            "validation_failed",
            ["The first sales transaction write slice supports Slaughter only."],
            400,
        )

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

    sale_id = generate_sale_id()
    items = [
        {
            **item,
            "sale_item_id": generate_sale_item_id(),
            "sale_id": sale_id,
        }
        for item in cleaned["items"]
    ]

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                duplicate_rows = _find_duplicate_pigs(cursor, items)
                if duplicate_rows:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "duplicate_pig",
                        "message": "One or more pigs are already linked to a non-cancelled sales transaction.",
                        "duplicates": [
                            {"pig_id": row[0], "sale_id": row[1]}
                            for row in duplicate_rows
                        ],
                        "source": _source_metadata(writes_to_supabase=False),
                    }, 409

                _insert_transaction(cursor, sale_id, cleaned)
                for item in items:
                    _insert_item(cursor, item)
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_transaction_create_failed",
            "message": "Sales transaction create failed and was rolled back.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(writes_to_supabase=False),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "created",
        "sale_id": sale_id,
        "created_counts": {
            "sales_transactions": 1,
            "sales_transaction_items": len(items),
        },
        "sales_transaction": _json_safe_row({
            key: value
            for key, value in cleaned.items()
            if key != "items"
        } | {"sale_id": sale_id}),
        "items": [_json_safe_row(item) for item in items],
        "source": _source_metadata(writes_to_supabase=True),
    }, 201


def generate_sale_id():
    return f"SALE-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def generate_sale_item_id():
    return f"SALEITEM-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def _find_duplicate_pigs(cursor, items):
    pig_ids = sorted({
        item["pig_id"]
        for item in items
        if item["item_type"] == "Pig" and item.get("pig_id")
    })
    if not pig_ids:
        return []

    cursor.execute(
        """
        select sti.pig_id, st.sale_id
        from public.sales_transaction_items sti
        join public.sales_transactions st on st.sale_id = sti.sale_id
        where sti.pig_id = any(%s)
        and st.sale_status <> 'Cancelled'
        order by sti.pig_id, st.sale_id
        """,
        (pig_ids,),
    )
    return cursor.fetchall()


def _insert_transaction(cursor, sale_id, cleaned):
    cursor.execute(
        """
        insert into public.sales_transactions (
            sale_id,
            sale_date,
            sale_stream,
            buyer_name,
            buyer_phone_raw,
            buyer_phone_normalized,
            destination,
            linked_order_id,
            pig_count,
            gross_total,
            deductions_total,
            net_total,
            currency,
            payment_status,
            payment_method,
            sale_status,
            notes,
            created_by
        )
        values (
            %s, %s, %s, %s, %s, %s, %s, nullif(%s, ''),
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            sale_id,
            cleaned["sale_date"],
            cleaned["sale_stream"],
            cleaned["buyer_name"],
            cleaned["buyer_phone_raw"],
            cleaned["buyer_phone_normalized"],
            cleaned["destination"],
            cleaned["linked_order_id"],
            cleaned["pig_count"],
            cleaned["gross_total"],
            cleaned["deductions_total"],
            cleaned["net_total"],
            cleaned["currency"],
            cleaned["payment_status"],
            cleaned["payment_method"],
            cleaned["sale_status"],
            cleaned["notes"],
            cleaned["created_by"],
        ),
    )


def _insert_item(cursor, item):
    cursor.execute(
        """
        insert into public.sales_transaction_items (
            sale_item_id,
            sale_id,
            item_type,
            pig_id,
            tag_number,
            order_line_id,
            description,
            quantity,
            live_weight_kg,
            carcass_weight_kg,
            packed_weight_kg,
            unit_price,
            pricing_basis,
            line_total,
            notes
        )
        values (
            %s, %s, %s, nullif(%s, ''), %s, nullif(%s, ''), %s,
            %s, %s, %s, %s, %s, nullif(%s, ''), %s, %s
        )
        """,
        (
            item["sale_item_id"],
            item["sale_id"],
            item["item_type"],
            item["pig_id"],
            item["tag_number"],
            item["order_line_id"],
            item["description"],
            item["quantity"],
            item["live_weight_kg"],
            item["carcass_weight_kg"],
            item["packed_weight_kg"],
            item["unit_price"],
            item["pricing_basis"],
            item["line_total"],
            item["notes"],
        ),
    )


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
