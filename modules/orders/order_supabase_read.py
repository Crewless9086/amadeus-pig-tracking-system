import os
from datetime import date, datetime

from services.database_service import DATABASE_URL_ENV


def supabase_order_reads_available():
    return bool(os.getenv(DATABASE_URL_ENV, "").strip())


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _fetch_all(sql, params=(), connect_factory=None):
    if not supabase_order_reads_available() and connect_factory is None:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured.")
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction read only")
            cursor.execute(sql, params)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_one(sql, params=(), connect_factory=None):
    rows = _fetch_all(sql, params=params, connect_factory=connect_factory)
    return rows[0] if rows else None


def _text(value):
    return "" if value is None else str(value).strip()


def _date_text(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return _text(value)


def _float_or_zero(value):
    if value in (None, ""):
        return 0
    return float(value)


def _line_rollup(lines):
    active = [line for line in lines if _text(line.get("line_status")) != "Cancelled"]
    return {
        "line_count": len(lines),
        "active_line_count": len(active),
        "cancelled_line_count": len(lines) - len(active),
        "active_line_total": sum(_float_or_zero(line.get("unit_price")) for line in active),
        "all_line_total": sum(_float_or_zero(line.get("unit_price")) for line in lines),
        "reserved_line_count": len([line for line in lines if _text(line.get("reserved_status")) == "Reserved"]),
        "confirmed_line_count": len([line for line in lines if _text(line.get("line_status")) == "Confirmed"]),
        "collected_line_count": len([line for line in lines if _text(line.get("line_status")) == "Collected"]),
        "reserved_pig_ids": ", ".join([
            _text(line.get("pig_id"))
            for line in lines
            if _text(line.get("reserved_status")) == "Reserved" and _text(line.get("pig_id"))
        ]),
        "reserved_tag_numbers": ", ".join([
            _text(line.get("tag_number"))
            for line in lines
            if _text(line.get("reserved_status")) == "Reserved" and _text(line.get("tag_number"))
        ]),
    }


def _order_record(row, lines):
    rollup = _line_rollup(lines)
    return {
        "order_id": _text(row.get("order_id")),
        "order_date": _date_text(row.get("order_date")),
        "customer_name": _text(row.get("customer_name")),
        "customer_phone": _text(row.get("customer_phone_raw")),
        "customer_channel": _text(row.get("customer_channel")),
        "customer_language": _text(row.get("customer_language")),
        "order_source": _text(row.get("order_source")),
        "requested_category": _text(row.get("requested_category")),
        "requested_weight_range": _text(row.get("requested_weight_range")),
        "requested_sex": _text(row.get("requested_sex")),
        "requested_quantity": _float_or_zero(row.get("requested_quantity")),
        "reserved_pig_count": _float_or_zero(row.get("reserved_pig_count")),
        "quoted_total": _float_or_zero(row.get("quoted_total")),
        "final_total": _float_or_zero(row.get("final_total")),
        "order_status": _text(row.get("order_status")),
        "approval_status": _text(row.get("approval_status")),
        "payment_status": _text(row.get("payment_status")),
        "payment_method": _text(row.get("payment_method")),
        "conversation_id": _text(row.get("conversation_id")),
        "collection_date": _date_text(row.get("collection_date")),
        "collection_location": _text(row.get("collection_location")),
        "line_count": rollup["line_count"],
        "active_line_count": rollup["active_line_count"],
        "cancelled_line_count": rollup["cancelled_line_count"],
        "active_line_total": rollup["active_line_total"],
        "all_line_total": rollup["all_line_total"],
        "reserved_line_count": rollup["reserved_line_count"],
        "confirmed_line_count": rollup["confirmed_line_count"],
        "collected_line_count": rollup["collected_line_count"],
        "reserved_pig_ids": rollup["reserved_pig_ids"],
        "reserved_tag_numbers": rollup["reserved_tag_numbers"],
        "notes": _text(row.get("notes")),
        "created_by": _text(row.get("created_by")),
        "created_at": _date_text(row.get("created_at")),
        "updated_at": _date_text(row.get("updated_at")),
    }


def _line_record(row):
    return {
        "order_line_id": _text(row.get("order_line_id")),
        "order_id": _text(row.get("order_id")),
        "pig_id": _text(row.get("pig_id")),
        "tag_number": _text(row.get("tag_number")),
        "sale_category": _text(row.get("sale_category")),
        "weight_band": _text(row.get("weight_band")),
        "sex": _text(row.get("sex")),
        "current_weight_kg": None if row.get("current_weight_kg") is None else float(row.get("current_weight_kg")),
        "unit_price": _float_or_zero(row.get("unit_price")),
        "line_status": _text(row.get("line_status")),
        "reserved_status": _text(row.get("reserved_status")),
        "notes": _text(row.get("notes")),
        "request_item_key": _text(row.get("request_item_key")),
        "created_at": _date_text(row.get("created_at")),
        "updated_at": _date_text(row.get("updated_at")),
    }


def _all_lines_by_order(connect_factory=None):
    rows = _fetch_all(
        """
        select *
        from public.order_lines
        order by order_id, order_line_id
        """,
        connect_factory=connect_factory,
    )
    grouped = {}
    for row in rows:
        grouped.setdefault(_text(row.get("order_id")), []).append(row)
    return grouped


def list_orders(connect_factory=None):
    orders = _fetch_all(
        """
        select *
        from public.orders
        order by order_date desc nulls last, created_at desc, order_id desc
        """,
        connect_factory=connect_factory,
    )
    lines_by_order = _all_lines_by_order(connect_factory=connect_factory)
    return [
        _order_record(row, lines_by_order.get(_text(row.get("order_id")), []))
        for row in orders
    ]


def get_order_detail(order_id, connect_factory=None):
    order_id = _text(order_id)
    if not order_id:
        return None
    order = _fetch_one(
        """
        select *
        from public.orders
        where order_id = %s
        """,
        (order_id,),
        connect_factory=connect_factory,
    )
    if not order:
        return None
    line_rows = _fetch_all(
        """
        select *
        from public.order_lines
        where order_id = %s
        order by order_line_id
        """,
        (order_id,),
        connect_factory=connect_factory,
    )
    lines = [_line_record(row) for row in line_rows]
    return {
        "order": _order_record(order, line_rows) | {"line_count_includes_cancelled": True},
        "lines": lines,
        "source": "supabase_canonical",
    }


def get_order_master_row(order_id, connect_factory=None):
    detail = get_order_detail(order_id, connect_factory=connect_factory)
    if not detail:
        return None
    order = detail["order"]
    return {
        "Order_ID": order.get("order_id", ""),
        "Order_Date": order.get("order_date", ""),
        "Customer_Name": order.get("customer_name", ""),
        "Customer_Phone": order.get("customer_phone", ""),
        "Customer_Channel": order.get("customer_channel", ""),
        "Customer_Language": order.get("customer_language", ""),
        "Order_Source": order.get("order_source", ""),
        "Requested_Category": order.get("requested_category", ""),
        "Requested_Weight_Range": order.get("requested_weight_range", ""),
        "Requested_Sex": order.get("requested_sex", ""),
        "Requested_Quantity": order.get("requested_quantity", ""),
        "Quoted_Total": order.get("quoted_total", ""),
        "Final_Total": order.get("final_total", ""),
        "Order_Status": order.get("order_status", ""),
        "Approval_Status": order.get("approval_status", ""),
        "Payment_Status": order.get("payment_status", ""),
        "Payment_Method": order.get("payment_method", ""),
        "Collection_Date": order.get("collection_date", ""),
        "Collection_Location": order.get("collection_location", ""),
        "Reserved_Pig_Count": order.get("reserved_pig_count", ""),
        "ConversationId": order.get("conversation_id", ""),
        "Notes": order.get("notes", ""),
        "Created_By": order.get("created_by", ""),
        "Created_At": order.get("created_at", ""),
        "Updated_At": order.get("updated_at", ""),
    }


def list_order_status_logs(connect_factory=None):
    rows = _fetch_all(
        """
        select *
        from public.order_status_logs
        order by status_date desc nulls last, created_at desc, status_log_id desc
        """,
        connect_factory=connect_factory,
    )
    return [{
        "Order_Status_Log_ID": _text(row.get("status_log_id")),
        "Order_ID": _text(row.get("order_id")),
        "Status_Date": _date_text(row.get("status_date")),
        "Old_Status": _text(row.get("old_status")),
        "New_Status": _text(row.get("new_status")),
        "Changed_By": _text(row.get("changed_by")),
        "Change_Source": _text(row.get("change_source")),
        "Notes": _text(row.get("notes")),
        "Created_At": _date_text(row.get("created_at")),
    } for row in rows]
