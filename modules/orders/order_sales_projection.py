import hashlib
import os
from decimal import Decimal, InvalidOperation

from services.database_service import DATABASE_URL_ENV


PAYMENT_STATUS_MAP = {
    "paid": "Paid",
    "deposit_paid": "Deposit_Paid",
    "deposit paid": "Deposit_Paid",
    "part_paid": "Part_Paid",
    "part paid": "Part_Paid",
    "partially_paid": "Part_Paid",
}


def project_completed_order_to_sale(order_id, changed_by="App", database_url=None, connect_factory=None):
    """Atomically reconcile one Completed order into one linked sales transaction."""
    clean_order_id = str(order_id or "").strip()
    if not clean_order_id:
        raise ValueError("order_id is required for sales projection.")

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url and connect_factory is None:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured for sales projection.")

    if connect_factory is None:
        import psycopg
        connect_factory = lambda url: psycopg.connect(url, connect_timeout=10)

    with connect_factory(database_url) as connection:
        with connection.cursor() as cursor:
            order, lines = _load_completed_order(cursor, clean_order_id)
            projection = build_projection(order, lines, changed_by)
            sale_id = _upsert_header(cursor, projection)
            _reconcile_items(cursor, sale_id, projection["items"])

    return {
        "success": True,
        "status": "reconciled",
        "sale_id": sale_id,
        "linked_order_id": clean_order_id,
        "sale_stream": projection["sale_stream"],
        "pig_count": projection["pig_count"],
        "item_count": len(projection["items"]),
    }


def build_projection(order, lines, changed_by="App"):
    if not order or str(order.get("order_status", "")).strip() != "Completed":
        raise ValueError("Only Completed orders can be projected to sales transactions.")

    collected = [line for line in (lines or []) if str(line.get("line_status", "")).strip() == "Collected"]
    if not collected:
        raise ValueError("Completed order has no Collected lines to project.")

    line_total = sum((_money(line.get("unit_price")) for line in collected), Decimal("0.00"))
    final_total = _optional_money(order.get("final_total"))
    net_total = final_total if final_total is not None else line_total
    if final_total is not None and final_total > line_total:
        raise ValueError("Order final_total exceeds collected line snapshots and cannot be reconciled.")
    gross_total = line_total
    deductions_total = gross_total - net_total
    sale_stream = classify_sale_stream(order, collected)

    items = []
    for line in collected:
        order_line_id = str(line.get("order_line_id", "")).strip()
        if not order_line_id:
            raise ValueError("Collected order line is missing order_line_id.")
        unit_price = _optional_money(line.get("unit_price"))
        items.append({
            "sale_item_id": _stable_id("SALEITEM", order_line_id),
            "order_line_id": order_line_id,
            "item_type": _item_type(sale_stream),
            "pig_id": _clean(line.get("pig_id")),
            "tag_number": _clean(line.get("tag_number")),
            "description": _clean(line.get("sale_category")) or "Order line",
            "quantity": Decimal("1"),
            "live_weight_kg": line.get("current_weight_kg"),
            "unit_price": unit_price,
            "pricing_basis": "Per_Pig" if unit_price is not None else None,
            "line_total": unit_price,
            "notes": _clean(line.get("notes")),
        })

    return {
        "sale_id": _stable_id("SALE", order["order_id"]),
        "sale_date": order.get("collection_date") or order.get("updated_at") or order.get("order_date"),
        "sale_stream": sale_stream,
        "buyer_name": _clean(order.get("customer_name")),
        "buyer_phone_raw": _clean(order.get("customer_phone_raw")),
        "buyer_phone_normalized": _clean(order.get("customer_phone_normalized")),
        "destination": _clean(order.get("collection_location")),
        "linked_order_id": order["order_id"],
        "pig_count": sum(1 for item in items if item["pig_id"]),
        "gross_total": gross_total,
        "deductions_total": deductions_total,
        "net_total": net_total,
        "payment_status": map_payment_status(order.get("payment_status")),
        "payment_method": _clean(order.get("payment_method")),
        "notes": f"Projected from completed order {order['order_id']}",
        "created_by": _clean(changed_by) or "App",
        "items": items,
    }


def classify_sale_stream(order, lines):
    context = " ".join(str(value or "") for value in (
        order.get("requested_category"), order.get("order_source"), order.get("notes"),
        *(line.get("sale_category") for line in lines),
    )).lower()
    if any(word in context for word in ("slaughter", "abattoir")):
        return "Slaughter"
    if any(word in context for word in ("meat", "carcass", "pork", "cut set", "freezer")):
        return "Meat"
    return "Livestock"


def map_payment_status(value):
    return PAYMENT_STATUS_MAP.get(str(value or "").strip().lower(), "Unpaid")


def _load_completed_order(cursor, order_id):
    cursor.execute("select * from public.orders where order_id = %s for update", (order_id,))
    order = _dict_row(cursor)
    if not order:
        raise ValueError("Order not found for sales projection.")
    cursor.execute(
        "select * from public.order_lines where order_id = %s and line_status = 'Collected' order by order_line_id",
        (order_id,),
    )
    columns = [column.name for column in cursor.description]
    return order, [dict(zip(columns, row)) for row in cursor.fetchall()]


def _upsert_header(cursor, data):
    cursor.execute(
        """
        insert into public.sales_transactions (
            sale_id, sale_date, sale_stream, buyer_name, buyer_phone_raw,
            buyer_phone_normalized, destination, linked_order_id, pig_count,
            gross_total, deductions_total, net_total, currency, payment_status,
            payment_method, sale_status, notes, created_by
        ) values (
            %(sale_id)s, coalesce(%(sale_date)s, now()), %(sale_stream)s, %(buyer_name)s,
            %(buyer_phone_raw)s, %(buyer_phone_normalized)s, %(destination)s,
            %(linked_order_id)s, %(pig_count)s, %(gross_total)s, %(deductions_total)s,
            %(net_total)s, 'ZAR', %(payment_status)s, %(payment_method)s, 'Completed',
            %(notes)s, %(created_by)s
        )
        on conflict (linked_order_id) where linked_order_id is not null do update set
            sale_date = excluded.sale_date, sale_stream = excluded.sale_stream,
            buyer_name = excluded.buyer_name, buyer_phone_raw = excluded.buyer_phone_raw,
            buyer_phone_normalized = excluded.buyer_phone_normalized,
            destination = excluded.destination, pig_count = excluded.pig_count,
            gross_total = excluded.gross_total, deductions_total = excluded.deductions_total,
            net_total = excluded.net_total, payment_status = excluded.payment_status,
            payment_method = excluded.payment_method, sale_status = 'Completed',
            notes = excluded.notes, updated_at = now()
        returning sale_id
        """,
        data,
    )
    return cursor.fetchone()[0]


def _reconcile_items(cursor, sale_id, items):
    line_ids = [item["order_line_id"] for item in items]
    cursor.execute(
        "delete from public.sales_transaction_items where sale_id = %s and not (order_line_id = any(%s))",
        (sale_id, line_ids),
    )
    for item in items:
        cursor.execute(
            """
            insert into public.sales_transaction_items (
                sale_item_id, sale_id, item_type, pig_id, tag_number, order_line_id,
                description, quantity, live_weight_kg, unit_price, pricing_basis,
                line_total, notes
            ) values (
                %(sale_item_id)s, %(sale_id)s, %(item_type)s, nullif(%(pig_id)s, ''),
                %(tag_number)s, %(order_line_id)s, %(description)s, %(quantity)s,
                %(live_weight_kg)s, %(unit_price)s, %(pricing_basis)s, %(line_total)s, %(notes)s
            )
            on conflict (sale_id, order_line_id) where order_line_id is not null do update set
                item_type = excluded.item_type, pig_id = excluded.pig_id,
                tag_number = excluded.tag_number, description = excluded.description,
                quantity = excluded.quantity, live_weight_kg = excluded.live_weight_kg,
                unit_price = excluded.unit_price, pricing_basis = excluded.pricing_basis,
                line_total = excluded.line_total, notes = excluded.notes, updated_at = now()
            """,
            {**item, "sale_id": sale_id},
        )


def _dict_row(cursor):
    columns = [column.name for column in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def _stable_id(prefix, value):
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def _item_type(stream):
    return "Pig" if stream == "Livestock" else ("Carcass" if stream == "Slaughter" else "Other")


def _clean(value):
    return str(value or "").strip()


def _optional_money(value):
    if value is None or str(value).strip() == "":
        return None
    return _money(value)


def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid money value: {value}")
