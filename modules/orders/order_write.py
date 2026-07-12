from datetime import datetime
import uuid

from services.google_sheets_service import (
    get_all_records,
    get_all_values,
    append_row,
    update_row_by_first_column_match,
)
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    to_float,
    format_date_for_sheet,
)
from modules.orders.order_status_log import write_order_status_log
from modules.orders import order_supabase_write
from modules.pig_weights.pig_weights_service import get_sales_availability


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
SALES_AVAILABILITY_SHEET = "SALES_AVAILABILITY"


def generate_order_id():
    return f"ORD-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def generate_order_line_id():
    return f"OL-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def _sheet_headers_and_rows(sheet_name: str):
    all_values = get_all_values(sheet_name)
    if not all_values:
        return [], []
    headers = all_values[0]
    rows = all_values[1:]
    return headers, rows


def _header_index(headers):
    return {header: idx for idx, header in enumerate(headers)}


def _update_sheet_row_by_id(sheet_name: str, row_id: str, updates: dict):
    headers, rows = _sheet_headers_and_rows(sheet_name)

    if not headers:
        raise ValueError(f"Sheet '{sheet_name}' is empty.")

    header_map = _header_index(headers)

    for row in rows:
        if not row:
            continue

        current_id = str(row[0]).strip()
        if current_id != str(row_id).strip():
            continue

        padded_row = row + [""] * (len(headers) - len(row))

        for field_name, field_value in updates.items():
            if field_name not in header_map:
                raise ValueError(f"Missing required column '{field_name}' in '{sheet_name}'.")
            padded_row[header_map[field_name]] = field_value

        update_row_by_first_column_match(sheet_name, row_id, padded_row)
        return

    raise ValueError(f"Row with ID '{row_id}' not found in '{sheet_name}'.")


def _get_order_master_row(order_id: str):
    if order_supabase_write.supabase_order_writes_available():
        return order_supabase_write.get_order_master_row(order_id)

    rows = get_all_records(ORDER_MASTER_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) == str(order_id).strip():
            return row
    return None


def _get_order_line_row(order_line_id: str):
    if order_supabase_write.supabase_order_writes_available():
        return order_supabase_write.get_order_line_row(order_line_id)

    rows = get_all_records(ORDER_LINES_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_Line_ID", "")) == str(order_line_id).strip():
            return row
    return None


def get_available_pigs_for_orders():
    if order_supabase_write.supabase_order_writes_available():
        rows = get_sales_availability()
        return _available_pigs_from_sales_rows(rows)

    rows = get_all_records(SALES_AVAILABILITY_SHEET)
    return _available_pigs_from_sales_rows(rows)


def _available_pigs_from_sales_rows(rows):
    pigs = []

    for row in rows:
        available = to_clean_string(row.get("Available_For_Sale", row.get("available_for_sale", "")))
        if available != "Yes":
            continue

        reserved_status = to_clean_string(row.get("Reserved_Status", row.get("reserved_status", "")))
        if reserved_status == "Reserved":
            continue

        pigs.append({
            "pig_id": to_clean_string(row.get("Pig_ID", row.get("pig_id", ""))),
            "tag_number": to_clean_string(row.get("Tag_Number", row.get("tag_number", ""))),
            "sex": to_clean_string(row.get("Sex", row.get("sex", ""))),
            "current_weight_kg": to_float(row.get("Current_Weight_Kg", row.get("current_weight_kg", ""))),
            "weight_band": to_clean_string(row.get("Weight_Band", row.get("weight_band", ""))),
            "sale_category": to_clean_string(row.get("Sale_Category", row.get("sale_category", ""))),
            "suggested_price_category": to_clean_string(row.get("Suggested_Price_Category", row.get("suggested_price_category", ""))),
            "reserved_status": reserved_status,
        })

    return sorted(pigs, key=lambda x: (x["tag_number"] or x["pig_id"]).lower())


def create_order(cleaned_data: dict):
    order_id = generate_order_id()
    today_str = datetime.now().strftime("%d %b %Y")

    if order_supabase_write.supabase_order_writes_available():
        order_supabase_write.insert_order(order_id, cleaned_data)
    else:
        row_values = [
            order_id,
            format_date_for_sheet(cleaned_data["order_date"]),
            cleaned_data["customer_name"],
            cleaned_data["customer_phone"],
            cleaned_data["customer_channel"],
            cleaned_data["customer_language"],
            cleaned_data["order_source"],
            cleaned_data["requested_category"],
            cleaned_data["requested_weight_range"],
            cleaned_data["requested_sex"],
            cleaned_data["requested_quantity"] if cleaned_data["requested_quantity"] is not None else "",
            cleaned_data["quoted_total"] if cleaned_data["quoted_total"] is not None else "",
            "",
            "Draft",
            "Pending",
            "Collection_Only",
            cleaned_data.get("collection_location", ""),
            "",
            "Pending",
            0,
            cleaned_data["notes"],
            cleaned_data["created_by"],
            today_str,
            today_str,
            cleaned_data.get("payment_method", ""),
            cleaned_data.get("conversation_id", ""),
        ]

        append_row(ORDER_MASTER_SHEET, row_values)

    status_log_warning = ""

    try:
        write_order_status_log(
            order_id=order_id,
            old_status="",
            new_status="Draft",
            changed_by=cleaned_data["created_by"],
            change_source="App",
            notes="Order created",
        )
    except Exception as exc:
        status_log_warning = f"Order created, but status log could not be written: {str(exc)}"

    result = {
        "success": True,
        "order_id": order_id,
        "message": "Order created successfully."
    }

    if status_log_warning:
        result["warning"] = status_log_warning

    return result


def update_order(order_id: str, cleaned_data: dict):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    order_status = to_clean_string(row.get("Order_Status", ""))

    if order_status in ("Cancelled", "Completed"):
        raise ValueError("This order can no longer be edited.")

    today_str = datetime.now().strftime("%d %b %Y")

    update_map = {}
    updated_fields = []

    if "requested_quantity" in cleaned_data:
        update_map["Requested_Quantity"] = cleaned_data["requested_quantity"]
        updated_fields.append("requested_quantity")

    if "requested_category" in cleaned_data:
        update_map["Requested_Category"] = cleaned_data["requested_category"]
        updated_fields.append("requested_category")

    if "requested_weight_range" in cleaned_data:
        update_map["Requested_Weight_Range"] = cleaned_data["requested_weight_range"]
        updated_fields.append("requested_weight_range")

    if "requested_sex" in cleaned_data:
        update_map["Requested_Sex"] = cleaned_data["requested_sex"]
        updated_fields.append("requested_sex")

    if "collection_location" in cleaned_data:
        update_map["Collection_Location"] = cleaned_data["collection_location"]
        updated_fields.append("collection_location")

    if "notes" in cleaned_data:
        update_map["Notes"] = cleaned_data["notes"]
        updated_fields.append("notes")

    if "payment_method" in cleaned_data:
        pm = str(cleaned_data["payment_method"]).strip()
        if pm not in ("Cash", "EFT"):
            raise ValueError("payment_method must be Cash or EFT.")
        if order_status != "Draft":
            raise ValueError("Payment method cannot be changed once the order is beyond Draft status.")
        update_map["Payment_Method"] = pm
        updated_fields.append("payment_method")

    if not updated_fields:
        raise ValueError("No valid order fields were provided for update.")

    update_map["Updated_At"] = today_str

    if order_supabase_write.supabase_order_writes_available():
        if order_supabase_write.update_order_fields(order_id, update_map) == 0:
            raise ValueError("Order not found.")
    else:
        _update_sheet_row_by_id(
            ORDER_MASTER_SHEET,
            order_id,
            update_map,
        )

    return {
        "success": True,
        "message": "Order updated successfully.",
        "order_id": order_id,
        "updated_fields": updated_fields,
        "changed_by": cleaned_data.get("changed_by", "App"),
    }


def create_order_line(cleaned_data: dict):
    available_pigs = get_available_pigs_for_orders()

    pig = None
    for item in available_pigs:
        if item["pig_id"] == cleaned_data["pig_id"]:
            pig = item
            break

    if not pig:
        raise ValueError("Pig is not available for order selection.")

    if cleaned_data.get("unit_price") is None:
        from modules.sales.sam_pricing import resolve_live_stock_price_rule

        price_rule = resolve_live_stock_price_rule(
            pig.get("sale_category"),
            pig.get("weight_band"),
            pig.get("sex"),
        )
        if not price_rule.get("found") or price_rule.get("unit_price") is None:
            raise ValueError(
                f"No active price found for {pig.get('sale_category')} / {pig.get('weight_band')}."
            )
        cleaned_data = {**cleaned_data, "unit_price": float(price_rule["unit_price"])}

    existing_lines = (
        order_supabase_write.list_order_lines()
        if order_supabase_write.supabase_order_writes_available()
        else get_all_records(ORDER_LINES_SHEET)
    )
    for row in existing_lines:
        if to_clean_string(row.get("Pig_ID", "")) != pig["pig_id"]:
            continue
        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            raise ValueError("Pig is already reserved on another order.")
        if to_clean_string(row.get("Order_ID", "")) == cleaned_data["order_id"] and to_clean_string(row.get("Line_Status", "")) != "Cancelled":
            raise ValueError("Pig is already on this order.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_line_id = generate_order_line_id()

    if order_supabase_write.supabase_order_writes_available():
        order_supabase_write.insert_order_line(order_line_id, cleaned_data, pig)
    else:
        row_values = [
            order_line_id,
            cleaned_data["order_id"],
            pig["pig_id"],
            pig["tag_number"],
            pig["sale_category"],
            pig["weight_band"],
            pig["sex"],
            pig["current_weight_kg"] if pig["current_weight_kg"] is not None else "",
            cleaned_data["unit_price"] if cleaned_data["unit_price"] is not None else "",
            "Draft",
            "Not_Reserved",
            cleaned_data["notes"],
            today_str,
            today_str,
            cleaned_data.get("request_item_key", ""),
        ]

        append_row(ORDER_LINES_SHEET, row_values)

    return {
        "success": True,
        "message": "Order line added successfully."
    }


def update_order_line(order_line_id: str, cleaned_data: dict):
    order_line_id = str(order_line_id).strip()
    row = _get_order_line_row(order_line_id)

    if not row:
        raise ValueError("Order line not found.")

    line_status = to_clean_string(row.get("Line_Status", ""))
    today_str = datetime.now().strftime("%d %b %Y")

    if line_status in ("Collected", "Cancelled"):
        raise ValueError("This order line can no longer be edited.")

    updates = {
        "Unit_Price": cleaned_data["unit_price"] if cleaned_data["unit_price"] is not None else "",
        "Notes": cleaned_data["notes"],
        "Updated_At": today_str,
    }
    if order_supabase_write.supabase_order_writes_available():
        if order_supabase_write.update_order_line_fields(order_line_id, updates) == 0:
            raise ValueError("Order line not found.")
    else:
        _update_sheet_row_by_id(
            ORDER_LINES_SHEET,
            order_line_id,
            updates,
        )

    return {
        "success": True,
        "message": "Order line updated successfully.",
        "order_line_id": order_line_id,
    }


def delete_order_line(order_line_id: str):
    order_line_id = str(order_line_id).strip()
    row = _get_order_line_row(order_line_id)

    if not row:
        raise ValueError("Order line not found.")

    line_status = to_clean_string(row.get("Line_Status", ""))
    reserved_status = to_clean_string(row.get("Reserved_Status", ""))

    if reserved_status == "Reserved" or line_status == "Reserved":
        raise ValueError("Release this line before deleting it.")

    if line_status in ("Collected", "Cancelled"):
        raise ValueError("This order line can no longer be deleted.")

    today_str = datetime.now().strftime("%d %b %Y")

    updates = {
        "Line_Status": "Cancelled",
        "Reserved_Status": "Not_Reserved",
        "Updated_At": today_str,
    }
    if order_supabase_write.supabase_order_writes_available():
        if order_supabase_write.update_order_line_fields(order_line_id, updates) == 0:
            raise ValueError("Order line not found.")
    else:
        _update_sheet_row_by_id(
            ORDER_LINES_SHEET,
            order_line_id,
            updates,
        )

    return {
        "success": True,
        "message": "Order line removed successfully.",
        "order_line_id": order_line_id,
    }
