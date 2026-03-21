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
    format_date_for_json,
    format_date_for_sheet,
    parse_sheet_date,
)

ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
ORDER_STATUS_LOG_SHEET = "ORDER_STATUS_LOG"
ORDER_OVERVIEW_SHEET = "ORDER_OVERVIEW"
SALES_AVAILABILITY_SHEET = "SALES_AVAILABILITY"


def generate_order_id():
    return f"ORD-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def generate_order_line_id():
    return f"OL-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def generate_order_status_log_id():
    return f"OSL-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


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
    rows = get_all_records(ORDER_MASTER_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) == str(order_id).strip():
            return row
    return None


def _get_order_line_row(order_line_id: str):
    rows = get_all_records(ORDER_LINES_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_Line_ID", "")) == str(order_line_id).strip():
            return row
    return None


def _write_order_status_log(order_id: str, old_status: str, new_status: str, changed_by: str, change_source: str, notes: str):
    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_order_status_log_id(),
        order_id,
        today_str,
        old_status,
        new_status,
        changed_by,
        change_source,
        notes,
        today_str,
    ]

    append_row(ORDER_STATUS_LOG_SHEET, row_values)


def _count_reserved_lines(order_id: str):
    rows = get_all_records(ORDER_LINES_SHEET)
    count = 0

    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) != order_id:
            continue
        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            count += 1

    return count


def list_orders():
    rows = get_all_records(ORDER_OVERVIEW_SHEET)
    records = []

    for row in rows:
        order_id = to_clean_string(row.get("Order_ID", ""))
        if not order_id:
            continue

        records.append({
            "order_id": order_id,
            "order_date": format_date_for_json(row.get("Order_Date", "")),
            "customer_name": to_clean_string(row.get("Customer_Name", "")),
            "customer_phone": to_clean_string(row.get("Customer_Phone", "")),
            "customer_channel": to_clean_string(row.get("Customer_Channel", "")),
            "customer_language": to_clean_string(row.get("Customer_Language", "")),
            "order_source": to_clean_string(row.get("Order_Source", "")),
            "requested_category": to_clean_string(row.get("Requested_Category", "")),
            "requested_weight_range": to_clean_string(row.get("Requested_Weight_Range", "")),
            "requested_sex": to_clean_string(row.get("Requested_Sex", "")),
            "requested_quantity": to_float(row.get("Requested_Quantity", "")) or 0,
            "reserved_pig_count": to_float(row.get("Reserved_Pig_Count", "")) or 0,
            "quoted_total": to_float(row.get("Quoted_Total", "")) or 0,
            "final_total": to_float(row.get("Final_Total", "")) or 0,
            "order_status": to_clean_string(row.get("Order_Status", "")),
            "approval_status": to_clean_string(row.get("Approval_Status", "")),
            "payment_status": to_clean_string(row.get("Payment_Status", "")),
            "collection_date": format_date_for_json(row.get("Collection_Date", "")),
            "collection_location": to_clean_string(row.get("Collection_Location", "")),
            "line_count": to_float(row.get("Line_Count", "")) or 0,
            "reserved_line_count": to_float(row.get("Reserved_Line_Count", "")) or 0,
            "confirmed_line_count": to_float(row.get("Confirmed_Line_Count", "")) or 0,
            "collected_line_count": to_float(row.get("Collected_Line_Count", "")) or 0,
            "reserved_pig_ids": to_clean_string(row.get("Reserved_Pig_IDs", "")),
            "reserved_tag_numbers": to_clean_string(row.get("Reserved_Tag_Numbers", "")),
            "notes": to_clean_string(row.get("Notes", "")),
            "created_by": to_clean_string(row.get("Created_By", "")),
            "created_at": format_date_for_json(row.get("Created_At", "")),
            "updated_at": format_date_for_json(row.get("Updated_At", "")),
        })

    def sort_key(item):
        parsed = parse_sheet_date(item["order_date"])
        return parsed or parse_sheet_date("1900-01-01")

    return sorted(records, key=sort_key, reverse=True)


def get_order_detail(order_id: str):
    order_id = str(order_id).strip()

    overview_rows = get_all_records(ORDER_OVERVIEW_SHEET)
    order_record = None

    for row in overview_rows:
        if to_clean_string(row.get("Order_ID", "")) == order_id:
            order_record = {
                "order_id": order_id,
                "order_date": format_date_for_json(row.get("Order_Date", "")),
                "customer_name": to_clean_string(row.get("Customer_Name", "")),
                "customer_phone": to_clean_string(row.get("Customer_Phone", "")),
                "customer_channel": to_clean_string(row.get("Customer_Channel", "")),
                "customer_language": to_clean_string(row.get("Customer_Language", "")),
                "order_source": to_clean_string(row.get("Order_Source", "")),
                "requested_category": to_clean_string(row.get("Requested_Category", "")),
                "requested_weight_range": to_clean_string(row.get("Requested_Weight_Range", "")),
                "requested_sex": to_clean_string(row.get("Requested_Sex", "")),
                "requested_quantity": to_float(row.get("Requested_Quantity", "")) or 0,
                "reserved_pig_count": to_float(row.get("Reserved_Pig_Count", "")) or 0,
                "quoted_total": to_float(row.get("Quoted_Total", "")) or 0,
                "final_total": to_float(row.get("Final_Total", "")) or 0,
                "order_status": to_clean_string(row.get("Order_Status", "")),
                "approval_status": to_clean_string(row.get("Approval_Status", "")),
                "payment_status": to_clean_string(row.get("Payment_Status", "")),
                "collection_date": format_date_for_json(row.get("Collection_Date", "")),
                "collection_location": to_clean_string(row.get("Collection_Location", "")),
                "line_count": to_float(row.get("Line_Count", "")) or 0,
                "reserved_line_count": to_float(row.get("Reserved_Line_Count", "")) or 0,
                "confirmed_line_count": to_float(row.get("Confirmed_Line_Count", "")) or 0,
                "collected_line_count": to_float(row.get("Collected_Line_Count", "")) or 0,
                "reserved_pig_ids": to_clean_string(row.get("Reserved_Pig_IDs", "")),
                "reserved_tag_numbers": to_clean_string(row.get("Reserved_Tag_Numbers", "")),
                "notes": to_clean_string(row.get("Notes", "")),
                "created_by": to_clean_string(row.get("Created_By", "")),
                "created_at": format_date_for_json(row.get("Created_At", "")),
                "updated_at": format_date_for_json(row.get("Updated_At", "")),
            }
            break

    if not order_record:
        return None

    line_rows = get_all_records(ORDER_LINES_SHEET)
    lines = []

    for row in line_rows:
        if to_clean_string(row.get("Order_ID", "")) != order_id:
            continue

        lines.append({
            "order_line_id": to_clean_string(row.get("Order_Line_ID", "")),
            "order_id": to_clean_string(row.get("Order_ID", "")),
            "pig_id": to_clean_string(row.get("Pig_ID", "")),
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "sale_category": to_clean_string(row.get("Sale_Category", "")),
            "weight_band": to_clean_string(row.get("Weight_Band", "")),
            "sex": to_clean_string(row.get("Sex", "")),
            "current_weight_kg": to_float(row.get("Current_Weight_Kg", "")),
            "unit_price": to_float(row.get("Unit_Price", "")) or 0,
            "line_status": to_clean_string(row.get("Line_Status", "")),
            "reserved_status": to_clean_string(row.get("Reserved_Status", "")),
            "notes": to_clean_string(row.get("Notes", "")),
            "created_at": format_date_for_json(row.get("Created_At", "")),
            "updated_at": format_date_for_json(row.get("Updated_At", "")),
        })

    return {
        "order": order_record,
        "lines": lines,
    }


def get_available_pigs_for_orders():
    rows = get_all_records(SALES_AVAILABILITY_SHEET)
    pigs = []

    for row in rows:
        if to_clean_string(row.get("Available_For_Sale", "")) != "Yes":
            continue

        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            continue

        pigs.append({
            "pig_id": to_clean_string(row.get("Pig_ID", "")),
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "sex": to_clean_string(row.get("Sex", "")),
            "current_weight_kg": to_float(row.get("Current_Weight_Kg", "")),
            "weight_band": to_clean_string(row.get("Weight_Band", "")),
            "sale_category": to_clean_string(row.get("Sale_Category", "")),
            "suggested_price_category": to_clean_string(row.get("Suggested_Price_Category", "")),
            "reserved_status": to_clean_string(row.get("Reserved_Status", "")),
        })

    return sorted(pigs, key=lambda x: (x["tag_number"] or x["pig_id"]).lower())


def create_order(cleaned_data: dict):
    order_id = generate_order_id()
    today_str = datetime.now().strftime("%d %b %Y")

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
        "",
        "",
        "Pending",
        0,
        cleaned_data["notes"],
        cleaned_data["created_by"],
        today_str,
        today_str,
    ]

    append_row(ORDER_MASTER_SHEET, row_values)

    _write_order_status_log(
        order_id=order_id,
        old_status="",
        new_status="Draft",
        changed_by=cleaned_data["created_by"],
        change_source="App",
        notes="Order created",
    )

    return {
        "success": True,
        "order_id": order_id,
        "message": "Order created successfully."
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

    existing_lines = get_all_records(ORDER_LINES_SHEET)
    for row in existing_lines:
        if to_clean_string(row.get("Pig_ID", "")) != pig["pig_id"]:
            continue
        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            raise ValueError("Pig is already reserved on another order.")
        if to_clean_string(row.get("Order_ID", "")) == cleaned_data["order_id"] and to_clean_string(row.get("Line_Status", "")) != "Cancelled":
            raise ValueError("Pig is already on this order.")

    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_order_line_id(),
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

    _update_sheet_row_by_id(
        ORDER_LINES_SHEET,
        order_line_id,
        {
            "Unit_Price": cleaned_data["unit_price"] if cleaned_data["unit_price"] is not None else "",
            "Notes": cleaned_data["notes"],
            "Updated_At": today_str,
        }
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

    _update_sheet_row_by_id(
        ORDER_LINES_SHEET,
        order_line_id,
        {
            "Line_Status": "Cancelled",
            "Reserved_Status": "Not_Reserved",
            "Updated_At": today_str,
        }
    )

    return {
        "success": True,
        "message": "Order line removed successfully.",
        "order_line_id": order_line_id,
    }


def reserve_order_lines(order_id: str):
    order_id = str(order_id).strip()

    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    if not detail["lines"]:
        raise ValueError("Order has no lines to reserve.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    required = [
        "Order_Line_ID",
        "Order_ID",
        "Line_Status",
        "Reserved_Status",
        "Updated_At",
    ]
    for field in required:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    today_str = datetime.now().strftime("%d %b %Y")
    changed_count = 0

    for row in rows:
        if not row:
            continue

        padded_row = row + [""] * (len(headers) - len(row))
        row_order_id = str(padded_row[idx["Order_ID"]]).strip()

        if row_order_id != order_id:
            continue

        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        line_status = str(padded_row[idx["Line_Status"]]).strip()
        reserved_status = str(padded_row[idx["Reserved_Status"]]).strip()

        if line_status == "Cancelled":
            continue

        updates = {}
        if reserved_status != "Reserved":
            updates["Reserved_Status"] = "Reserved"
            changed_count += 1

        if line_status in ("", "Draft"):
            updates["Line_Status"] = "Reserved"

        if updates:
            updates["Updated_At"] = today_str
            _update_sheet_row_by_id(ORDER_LINES_SHEET, line_id, updates)

    reserved_count = _count_reserved_lines(order_id)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Reserved_Pig_Count": reserved_count,
            "Updated_At": today_str,
        }
    )

    return {
        "success": True,
        "message": "Order lines reserved successfully.",
        "order_id": order_id,
        "reserved_pig_count": reserved_count,
        "changed_count": changed_count,
    }


def release_order_lines(order_id: str):
    order_id = str(order_id).strip()

    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    required = [
        "Order_Line_ID",
        "Order_ID",
        "Line_Status",
        "Reserved_Status",
        "Updated_At",
    ]
    for field in required:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    today_str = datetime.now().strftime("%d %b %Y")
    changed_count = 0

    for row in rows:
        if not row:
            continue

        padded_row = row + [""] * (len(headers) - len(row))
        row_order_id = str(padded_row[idx["Order_ID"]]).strip()

        if row_order_id != order_id:
            continue

        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        line_status = str(padded_row[idx["Line_Status"]]).strip()
        reserved_status = str(padded_row[idx["Reserved_Status"]]).strip()

        updates = {}
        if reserved_status == "Reserved":
            updates["Reserved_Status"] = "Not_Reserved"
            changed_count += 1

        if line_status == "Reserved":
            updates["Line_Status"] = "Draft"

        if updates:
            updates["Updated_At"] = today_str
            _update_sheet_row_by_id(ORDER_LINES_SHEET, line_id, updates)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Reserved_Pig_Count": 0,
            "Updated_At": today_str,
        }
    )

    return {
        "success": True,
        "message": "Order reservations released successfully.",
        "order_id": order_id,
        "reserved_pig_count": 0,
        "changed_count": changed_count,
    }


def send_order_for_approval(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status == "Cancelled":
        raise ValueError("Cancelled orders cannot be sent for approval.")

    today_str = datetime.now().strftime("%d %b %Y")

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Pending_Approval",
            "Approval_Status": "Pending",
            "Updated_At": today_str,
        }
    )

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Pending_Approval | Pending",
        changed_by=changed_by,
        change_source="App",
        notes="Order sent for approval",
    )

    return {
        "success": True,
        "message": "Order sent for approval.",
        "order_id": order_id,
    }


def approve_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status == "Cancelled":
        raise ValueError("Cancelled orders cannot be approved.")

    today_str = datetime.now().strftime("%d %b %Y")

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Approved",
            "Approval_Status": "Approved",
            "Updated_At": today_str,
        }
    )

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Approved | Approved",
        changed_by=changed_by,
        change_source="App",
        notes="Order approved",
    )

    return {
        "success": True,
        "message": "Order approved successfully.",
        "order_id": order_id,
    }


def reject_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    today_str = datetime.now().strftime("%d %b %Y")

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Cancelled",
            "Approval_Status": "Rejected",
            "Updated_At": today_str,
        }
    )

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Cancelled | Rejected",
        changed_by=changed_by,
        change_source="App",
        notes="Order rejected",
    )

    return {
        "success": True,
        "message": "Order rejected successfully.",
        "order_id": order_id,
    }