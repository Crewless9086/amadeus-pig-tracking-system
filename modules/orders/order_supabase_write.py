import os
import sys
from datetime import date, datetime

from services.database_service import DATABASE_URL_ENV
from modules.pig_weights.pig_weights_utils import to_clean_string, to_float


ORDER_FIELD_MAP = {
    "Requested_Quantity": "requested_quantity",
    "Requested_Category": "requested_category",
    "Requested_Weight_Range": "requested_weight_range",
    "Requested_Sex": "requested_sex",
    "Collection_Location": "collection_location",
    "Payment_Method": "payment_method",
    "Conversation_ID": "conversation_id",
    "Notes": "notes",
    "Order_Status": "order_status",
    "Approval_Status": "approval_status",
    "Payment_Status": "payment_status",
    "Reserved_Pig_Count": "reserved_pig_count",
    "Updated_At": "updated_at",
}

LINE_FIELD_MAP = {
    "Unit_Price": "unit_price",
    "Notes": "notes",
    "Line_Status": "line_status",
    "Reserved_Status": "reserved_status",
    "Updated_At": "updated_at",
}


def supabase_order_writes_available():
    if "unittest" in sys.modules and os.getenv("ALLOW_SUPABASE_WRITES_IN_TESTS", "") != "1":
        return False
    return bool(os.getenv(DATABASE_URL_ENV, "").strip())


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _now():
    return datetime.now()


def _date_or_none(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _sheet_date(value):
    parsed = _date_or_none(value)
    return parsed.strftime("%d %b %Y") if parsed else ""


def _order_sheet_row(row):
    if not row:
        return None
    return {
        "Order_ID": to_clean_string(row.get("order_id")),
        "Order_Date": _sheet_date(row.get("order_date")),
        "Customer_Name": to_clean_string(row.get("customer_name")),
        "Customer_Phone": to_clean_string(row.get("customer_phone_raw")),
        "Customer_Channel": to_clean_string(row.get("customer_channel")),
        "Customer_Language": to_clean_string(row.get("customer_language")),
        "Order_Source": to_clean_string(row.get("order_source")),
        "Requested_Category": to_clean_string(row.get("requested_category")),
        "Requested_Weight_Range": to_clean_string(row.get("requested_weight_range")),
        "Requested_Sex": to_clean_string(row.get("requested_sex")),
        "Requested_Quantity": row.get("requested_quantity") or "",
        "Quoted_Total": row.get("quoted_total") or "",
        "Final_Total": row.get("final_total") or "",
        "Order_Status": to_clean_string(row.get("order_status")),
        "Approval_Status": to_clean_string(row.get("approval_status")),
        "Collection_Method": to_clean_string(row.get("collection_method")),
        "Collection_Location": to_clean_string(row.get("collection_location")),
        "Collection_Date": _sheet_date(row.get("collection_date")),
        "Payment_Status": to_clean_string(row.get("payment_status")),
        "Reserved_Pig_Count": row.get("reserved_pig_count") or 0,
        "Notes": to_clean_string(row.get("notes")),
        "Created_By": to_clean_string(row.get("created_by")),
        "Created_At": _sheet_date(row.get("created_at")),
        "Updated_At": _sheet_date(row.get("updated_at")),
        "Payment_Method": to_clean_string(row.get("payment_method")),
        "ConversationId": to_clean_string(row.get("conversation_id")),
    }


def _line_sheet_row(row):
    if not row:
        return None
    return {
        "Order_Line_ID": to_clean_string(row.get("order_line_id")),
        "Order_ID": to_clean_string(row.get("order_id")),
        "Pig_ID": to_clean_string(row.get("pig_id")),
        "Tag_Number": to_clean_string(row.get("tag_number")),
        "Sale_Category": to_clean_string(row.get("sale_category")),
        "Weight_Band": to_clean_string(row.get("weight_band")),
        "Sex": to_clean_string(row.get("sex")),
        "Current_Weight_Kg": row.get("current_weight_kg") if row.get("current_weight_kg") is not None else "",
        "Unit_Price": row.get("unit_price") if row.get("unit_price") is not None else "",
        "Line_Status": to_clean_string(row.get("line_status")),
        "Reserved_Status": to_clean_string(row.get("reserved_status")),
        "Notes": to_clean_string(row.get("notes")),
        "Created_At": _sheet_date(row.get("created_at")),
        "Updated_At": _sheet_date(row.get("updated_at")),
        "Request_Item_Key": to_clean_string(row.get("request_item_key")),
    }


def _fetch_one(cursor, sql, params):
    cursor.execute(sql, params)
    columns = [column.name for column in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def _fetch_all(cursor, sql, params=()):
    cursor.execute(sql, params)
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_order_master_row(order_id, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            row = _fetch_one(cursor, "select * from public.orders where order_id = %s", (to_clean_string(order_id),))
    return _order_sheet_row(row)


def get_order_line_row(order_line_id, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            row = _fetch_one(cursor, "select * from public.order_lines where order_line_id = %s", (to_clean_string(order_line_id),))
    return _line_sheet_row(row)


def list_order_lines(connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(cursor, "select * from public.order_lines")
    return [_line_sheet_row(row) for row in rows]


def insert_order(order_id, cleaned_data, connect_factory=None):
    now = _now()
    params = {
        "order_id": order_id,
        "order_date": _date_or_none(cleaned_data["order_date"]),
        "customer_name": cleaned_data["customer_name"],
        "customer_phone_raw": cleaned_data["customer_phone"],
        "customer_channel": cleaned_data["customer_channel"],
        "customer_language": cleaned_data["customer_language"],
        "order_source": cleaned_data["order_source"],
        "requested_category": cleaned_data["requested_category"],
        "requested_weight_range": cleaned_data["requested_weight_range"],
        "requested_sex": cleaned_data["requested_sex"],
        "requested_quantity": cleaned_data["requested_quantity"],
        "quoted_total": cleaned_data["quoted_total"],
        "final_total": None,
        "order_status": "Draft",
        "approval_status": "Pending",
        "collection_method": "Collection_Only",
        "collection_location": cleaned_data.get("collection_location", ""),
        "payment_status": "Pending",
        "reserved_pig_count": 0,
        "notes": cleaned_data["notes"],
        "created_by": cleaned_data["created_by"],
        "payment_method": cleaned_data.get("payment_method", ""),
        "conversation_id": cleaned_data.get("conversation_id", ""),
        "created_at": now,
        "updated_at": now,
    }
    columns = ", ".join(params.keys())
    placeholders = ", ".join([f"%({key})s" for key in params.keys()])
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"insert into public.orders ({columns}) values ({placeholders})",
                params,
            )


def update_order_fields(order_id, updates, connect_factory=None):
    fields = {}
    for sheet_name, value in updates.items():
        column = ORDER_FIELD_MAP.get(sheet_name)
        if not column:
            continue
        fields[column] = _now() if column == "updated_at" else value
    if not fields:
        return 0
    assignments = ", ".join([f"{column} = %({column})s" for column in fields.keys()])
    fields["order_id"] = to_clean_string(order_id)
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"update public.orders set {assignments} where order_id = %(order_id)s",
                fields,
            )
            return cursor.rowcount


def insert_order_line(order_line_id, cleaned_data, pig, connect_factory=None):
    now = _now()
    params = {
        "order_line_id": order_line_id,
        "order_id": cleaned_data["order_id"],
        "pig_id": pig["pig_id"],
        "tag_number": pig.get("tag_number", ""),
        "sale_category": pig.get("sale_category", ""),
        "weight_band": pig.get("weight_band", ""),
        "sex": pig.get("sex", ""),
        "current_weight_kg": pig.get("current_weight_kg"),
        "unit_price": cleaned_data.get("unit_price"),
        "line_status": "Draft",
        "reserved_status": "Not_Reserved",
        "notes": cleaned_data.get("notes", ""),
        "request_item_key": cleaned_data.get("request_item_key", ""),
        "created_at": now,
        "updated_at": now,
    }
    columns = ", ".join(params.keys())
    placeholders = ", ".join([f"%({key})s" for key in params.keys()])
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"insert into public.order_lines ({columns}) values ({placeholders})",
                params,
            )


def update_order_line_fields(order_line_id, updates, connect_factory=None):
    fields = {}
    for sheet_name, value in updates.items():
        column = LINE_FIELD_MAP.get(sheet_name)
        if not column:
            continue
        fields[column] = _now() if column == "updated_at" else value
    if not fields:
        return 0
    assignments = ", ".join([f"{column} = %({column})s" for column in fields.keys()])
    fields["order_line_id"] = to_clean_string(order_line_id)
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"update public.order_lines set {assignments} where order_line_id = %(order_line_id)s",
                fields,
            )
            return cursor.rowcount


def insert_status_log(status_log_id, order_id, old_status, new_status, changed_by, change_source, notes, connect_factory=None):
    now = _now()
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.order_status_logs (
                    status_log_id, order_id, status_date, old_status, new_status,
                    changed_by, change_source, notes, created_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (status_log_id, order_id, now, old_status, new_status, changed_by, change_source, notes, now),
            )


def sales_pricing_lookup(connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(
                cursor,
                """
                select sale_category, weight_band, unit_price
                from public.sales_pricing
                where active is true
                order by effective_from desc
                """,
            )
    lookup = {}
    for row in rows:
        key = (to_clean_string(row.get("sale_category")), to_clean_string(row.get("weight_band")))
        if key not in lookup:
            lookup[key] = to_float(row.get("unit_price"))
    return lookup


def mark_pigs_sold(pig_ids, connect_factory=None):
    clean_ids = [to_clean_string(pig_id) for pig_id in pig_ids if to_clean_string(pig_id)]
    if not clean_ids:
        return 0
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update public.pigs
                set status = 'Sold',
                    on_farm = false,
                    updated_at = now()
                where pig_id = any(%s)
                """,
                (clean_ids,),
            )
            return cursor.rowcount
