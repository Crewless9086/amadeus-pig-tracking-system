import json
from datetime import date, datetime

from modules.orders import order_supabase_write
from modules.pig_weights.pig_weights_utils import to_clean_string, to_float


def available():
    return order_supabase_write.supabase_order_writes_available()


def _connect(connect_factory=None):
    return order_supabase_write._connect(connect_factory=connect_factory)


def _date_text(value):
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return to_clean_string(value)


def _bool_sheet(value):
    return "Yes" if value is True else "No"


def _json_list_text(value):
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return to_clean_string(value)


def _fetch_all(cursor, sql, params=()):
    cursor.execute(sql, params)
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _intake_row(row):
    return {
        "Intake_ID": to_clean_string(row.get("intake_id")),
        "ConversationId": to_clean_string(row.get("conversation_id")),
        "Account_ID": to_clean_string(row.get("account_id")),
        "Contact_ID": to_clean_string(row.get("contact_id")),
        "Customer_Name": to_clean_string(row.get("customer_name")),
        "Customer_Phone": to_clean_string(row.get("customer_phone_raw")),
        "Customer_Channel": to_clean_string(row.get("customer_channel")),
        "Customer_Language": to_clean_string(row.get("customer_language")),
        "Draft_Order_ID": to_clean_string(row.get("draft_order_id")),
        "Intake_Status": to_clean_string(row.get("intake_status")),
        "Collection_Location": to_clean_string(row.get("collection_location")),
        "Collection_Time_Text": to_clean_string(row.get("collection_time_text")),
        "Collection_Date": _date_text(row.get("collection_date")),
        "Collection_Time": to_clean_string(row.get("collection_time")),
        "Payment_Method": to_clean_string(row.get("payment_method")),
        "Quote_Requested": _bool_sheet(row.get("quote_requested")),
        "Order_Commitment": _bool_sheet(row.get("order_commitment")),
        "Missing_Fields": _json_list_text(row.get("missing_fields")),
        "Next_Action": to_clean_string(row.get("next_action")),
        "Ready_For_Draft": _bool_sheet(row.get("ready_for_draft")),
        "Ready_For_Quote": _bool_sheet(row.get("ready_for_quote")),
        "Last_Customer_Message": to_clean_string(row.get("last_customer_message")),
        "Last_Updated_By": to_clean_string(row.get("last_updated_by")),
        "Created_At": _date_text(row.get("created_at")),
        "Updated_At": _date_text(row.get("updated_at")),
        "Closed_At": _date_text(row.get("closed_at")),
        "Closed_Reason": to_clean_string(row.get("closed_reason")),
        "Notes": to_clean_string(row.get("notes")),
    }


def _item_row(row):
    return {
        "Intake_Item_ID": to_clean_string(row.get("intake_item_id")),
        "Intake_ID": to_clean_string(row.get("intake_id")),
        "ConversationId": to_clean_string(row.get("conversation_id")),
        "Item_Key": to_clean_string(row.get("item_key")),
        "Quantity": row.get("quantity") if row.get("quantity") is not None else "",
        "Category": to_clean_string(row.get("category")),
        "Weight_Range": to_clean_string(row.get("weight_range")),
        "Sex": to_clean_string(row.get("sex")),
        "Intent_Type": to_clean_string(row.get("intent_type")),
        "Status": to_clean_string(row.get("status")),
        "Linked_Order_Line_IDs": _json_list_text(row.get("linked_order_line_ids")),
        "Last_Match_Status": to_clean_string(row.get("last_match_status")),
        "Matched_Quantity": row.get("matched_quantity") if row.get("matched_quantity") is not None else "",
        "Replaced_By_Item_Key": to_clean_string(row.get("replaced_by_item_key")),
        "Removal_Reason": to_clean_string(row.get("removal_reason")),
        "Notes": to_clean_string(row.get("notes")),
        "Created_At": _date_text(row.get("created_at")),
        "Updated_At": _date_text(row.get("updated_at")),
        "Removed_At": _date_text(row.get("removed_at")),
    }


def find_active_intake_by_conversation(conversation_id, open_statuses, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(
                cursor,
                """
                select *
                from public.order_intakes
                where conversation_id = %s
                and intake_status = any(%s)
                order by updated_at desc nulls last, created_at desc
                limit 1
                """,
                (conversation_id, list(open_statuses)),
            )
    return _intake_row(rows[0]) if rows else None


def get_items_for_intake(intake_id, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(
                cursor,
                """
                select *
                from public.order_intake_items
                where intake_id = %s
                order by created_at, intake_item_id
                """,
                (intake_id,),
            )
    return [_item_row(row) for row in rows]


def _sheet_bool(value):
    return str(value or "").strip().lower() in ("yes", "true", "1", "y")


def _split_list(value):
    if isinstance(value, list):
        return value
    text = to_clean_string(value)
    return [part.strip() for part in text.split(",") if part.strip()]


def insert_intake(row, connect_factory=None):
    now = datetime.now()
    params = {
        "intake_id": row["Intake_ID"],
        "conversation_id": row["ConversationId"],
        "account_id": row["Account_ID"],
        "contact_id": row["Contact_ID"],
        "customer_name": row["Customer_Name"],
        "customer_phone_raw": row["Customer_Phone"],
        "customer_channel": row["Customer_Channel"],
        "customer_language": row["Customer_Language"],
        "draft_order_id": None,
        "intake_status": row["Intake_Status"],
        "collection_location": row["Collection_Location"],
        "collection_time_text": row["Collection_Time_Text"],
        "payment_method": row["Payment_Method"],
        "quote_requested": _sheet_bool(row["Quote_Requested"]),
        "order_commitment": _sheet_bool(row["Order_Commitment"]),
        "missing_fields": _split_list(row["Missing_Fields"]),
        "next_action": row["Next_Action"],
        "ready_for_draft": _sheet_bool(row["Ready_For_Draft"]),
        "ready_for_quote": _sheet_bool(row["Ready_For_Quote"]),
        "last_customer_message": row["Last_Customer_Message"],
        "last_updated_by": row["Last_Updated_By"],
        "created_at": now,
        "updated_at": now,
        "notes": row["Notes"],
    }
    columns = ", ".join(params.keys())
    placeholders = ", ".join([f"%({key})s" for key in params.keys()])
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"insert into public.order_intakes ({columns}) values ({placeholders})",
                params,
            )


def insert_item(row, connect_factory=None):
    now = datetime.now()
    params = {
        "intake_item_id": row["Intake_Item_ID"],
        "intake_id": row["Intake_ID"],
        "conversation_id": row["ConversationId"],
        "item_key": row["Item_Key"],
        "quantity": int(to_float(row["Quantity"]) or 0) if row["Quantity"] not in ("", None) else None,
        "category": row["Category"],
        "weight_range": row["Weight_Range"],
        "sex": row["Sex"],
        "intent_type": row["Intent_Type"],
        "status": row["Status"],
        "linked_order_line_ids": _split_list(row["Linked_Order_Line_IDs"]),
        "last_match_status": row["Last_Match_Status"],
        "matched_quantity": int(to_float(row["Matched_Quantity"]) or 0) if row["Matched_Quantity"] not in ("", None) else None,
        "replaced_by_item_key": row["Replaced_By_Item_Key"],
        "removal_reason": row["Removal_Reason"],
        "notes": row["Notes"],
        "created_at": now,
        "updated_at": now,
        "removed_at": now if row["Removed_At"] else None,
    }
    columns = ", ".join(params.keys())
    placeholders = ", ".join([f"%({key})s" for key in params.keys()])
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"insert into public.order_intake_items ({columns}) values ({placeholders})",
                params,
            )


def update_intakes(updates_by_id, connect_factory=None):
    return _update_rows("order_intakes", "intake_id", INTAKE_FIELD_MAP, updates_by_id, connect_factory)


def update_items(updates_by_id, connect_factory=None):
    return _update_rows("order_intake_items", "intake_item_id", ITEM_FIELD_MAP, updates_by_id, connect_factory)


INTAKE_FIELD_MAP = {
    "Account_ID": "account_id",
    "Contact_ID": "contact_id",
    "Customer_Name": "customer_name",
    "Customer_Phone": "customer_phone_raw",
    "Customer_Channel": "customer_channel",
    "Customer_Language": "customer_language",
    "Draft_Order_ID": "draft_order_id",
    "Intake_Status": "intake_status",
    "Collection_Location": "collection_location",
    "Collection_Time_Text": "collection_time_text",
    "Payment_Method": "payment_method",
    "Quote_Requested": "quote_requested",
    "Order_Commitment": "order_commitment",
    "Missing_Fields": "missing_fields",
    "Next_Action": "next_action",
    "Ready_For_Draft": "ready_for_draft",
    "Ready_For_Quote": "ready_for_quote",
    "Last_Customer_Message": "last_customer_message",
    "Last_Updated_By": "last_updated_by",
    "Closed_At": "closed_at",
    "Closed_Reason": "closed_reason",
    "Notes": "notes",
    "Updated_At": "updated_at",
}

ITEM_FIELD_MAP = {
    "Quantity": "quantity",
    "Category": "category",
    "Weight_Range": "weight_range",
    "Sex": "sex",
    "Intent_Type": "intent_type",
    "Status": "status",
    "Linked_Order_Line_IDs": "linked_order_line_ids",
    "Last_Match_Status": "last_match_status",
    "Matched_Quantity": "matched_quantity",
    "Replaced_By_Item_Key": "replaced_by_item_key",
    "Removal_Reason": "removal_reason",
    "Notes": "notes",
    "Updated_At": "updated_at",
    "Removed_At": "removed_at",
}


def _normalize_update_value(column, value):
    if column in {"quote_requested", "order_commitment", "ready_for_draft", "ready_for_quote"}:
        return _sheet_bool(value)
    if column in {"missing_fields", "linked_order_line_ids"}:
        return _split_list(value)
    if column in {"quantity", "matched_quantity"}:
        return int(to_float(value) or 0) if value not in ("", None) else None
    if column in {"updated_at", "closed_at", "removed_at"}:
        return datetime.now() if value else None
    if column == "draft_order_id" and not to_clean_string(value):
        return None
    return value


def _update_rows(table_name, id_column, field_map, updates_by_id, connect_factory=None):
    changed = 0
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            for row_id, updates in updates_by_id.items():
                fields = {}
                for sheet_key, value in updates.items():
                    column = field_map.get(sheet_key)
                    if not column:
                        continue
                    fields[column] = _normalize_update_value(column, value)
                if not fields:
                    continue
                assignments = ", ".join([f"{column} = %({column})s" for column in fields.keys()])
                fields[id_column] = row_id
                cursor.execute(
                    f"update public.{table_name} set {assignments} where {id_column} = %({id_column})s",
                    fields,
                )
                changed += cursor.rowcount
    return changed
