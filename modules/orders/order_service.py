import json
import os
from datetime import datetime
import uuid
from urllib import request as urllib_request
from urllib import error as urllib_error

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
SALES_PRICING_SHEET = "SALES_PRICING"

ORDER_APPROVAL_WEBHOOK_URL = os.getenv(
    "ORDER_APPROVAL_WEBHOOK_URL",
    "https://charln.app.n8n.cloud/webhook/46935f6b-2921-4d51-a477-1db5ac1024f7",
)

CATEGORY_REQUEST_TO_SALES = {
    "Piglet": ["Young Piglets"],
    "Weaner": ["Weaner Piglets"],
    "Grower": ["Grower Pigs"],
    "Finisher": ["Finisher Pigs"],
    "Slaughter": ["Ready for Slaughter"],
    "Young Piglets": ["Young Piglets"],
    "Weaner Piglets": ["Weaner Piglets"],
    "Grower Pigs": ["Grower Pigs"],
    "Finisher Pigs": ["Finisher Pigs"],
    "Ready for Slaughter": ["Ready for Slaughter"],
}

WEIGHT_BAND_ORDER = [
    "N/A",
    "2_to_4_Kg",
    "5_to_6_Kg",
    "7_to_9_Kg",
    "10_to_14_Kg",
    "15_to_19_Kg",
    "20_to_24_Kg",
    "25_to_29_Kg",
    "30_to_34_Kg",
    "35_to_39_Kg",
    "40_to_44_Kg",
    "45_to_49_Kg",
    "50_to_54_Kg",
    "55_to_59_Kg",
    "60_to_64_Kg",
    "65_to_69_Kg",
    "70_to_74_Kg",
    "75_to_79_Kg",
    "80_to_84_Kg",
    "85_to_89_Kg",
    "90_to_94_Kg",
]


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

def _get_active_order_lines_by_request_item_from_rows(order_lines_rows, order_id: str, request_item_key: str):
    active_lines = []

    for row in order_lines_rows:
        if to_clean_string(row.get("Order_ID", "")) != str(order_id).strip():
            continue
        if to_clean_string(row.get("Request_Item_Key", "")) != str(request_item_key).strip():
            continue
        if not _row_is_active_order_line(row):
            continue

        active_lines.append(row)

    return active_lines


def _get_active_pig_ids_on_order_from_rows(order_lines_rows, order_id: str, exclude_request_item_key: str = ""):
    pig_ids = set()

    for row in order_lines_rows:
        if to_clean_string(row.get("Order_ID", "")) != str(order_id).strip():
            continue
        if not _row_is_active_order_line(row):
            continue

        row_request_item_key = to_clean_string(row.get("Request_Item_Key", ""))
        if exclude_request_item_key and row_request_item_key == exclude_request_item_key:
            continue

        pig_id = to_clean_string(row.get("Pig_ID", ""))
        if pig_id:
            pig_ids.add(pig_id)

    return pig_ids

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


def _notify_n8n_order_approval_request(order_id: str, changed_by: str):
    payload = {
        "action": "request_order_approval",
        "order_id": str(order_id).strip(),
        "changed_by": str(changed_by).strip() or "App",
        "trigger_source": "Flask App",
        "notes": "Order sent for approval from app",
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib_request.Request(
        ORDER_APPROVAL_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return {
                "sent": True,
                "status_code": getattr(response, "status", 200),
                "body": body,
            }
    except urllib_error.HTTPError as exc:
        return {
            "sent": False,
            "error": f"HTTPError {exc.code}: {exc.reason}",
        }
    except urllib_error.URLError as exc:
        return {
            "sent": False,
            "error": f"URLError: {exc.reason}",
        }
    except Exception as exc:
        return {
            "sent": False,
            "error": str(exc),
        }


def _weight_band_sort_key(weight_band: str):
    try:
        return WEIGHT_BAND_ORDER.index(to_clean_string(weight_band))
    except ValueError:
        return 9999


def _sales_categories_for_request(category: str):
    category = to_clean_string(category)
    return CATEGORY_REQUEST_TO_SALES.get(category, [category])


def _row_is_active_order_line(row: dict):
    return to_clean_string(row.get("Line_Status", "")) != "Cancelled"


def _get_active_order_lines_by_request_item(order_id: str, request_item_key: str):
    rows = get_all_records(ORDER_LINES_SHEET)
    active_lines = []

    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) != str(order_id).strip():
            continue
        if to_clean_string(row.get("Request_Item_Key", "")) != str(request_item_key).strip():
            continue
        if not _row_is_active_order_line(row):
            continue

        active_lines.append(row)

    return active_lines


def _get_active_pig_ids_on_order(order_id: str, exclude_request_item_key: str = ""):
    rows = get_all_records(ORDER_LINES_SHEET)
    pig_ids = set()

    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) != str(order_id).strip():
            continue
        if not _row_is_active_order_line(row):
            continue

        row_request_item_key = to_clean_string(row.get("Request_Item_Key", ""))
        if exclude_request_item_key and row_request_item_key == exclude_request_item_key:
            continue

        pig_id = to_clean_string(row.get("Pig_ID", ""))
        if pig_id:
            pig_ids.add(pig_id)

    return pig_ids


def _cancel_order_lines(order_line_ids):
    today_str = datetime.now().strftime("%d %b %Y")
    cancelled_count = 0

    for order_line_id in order_line_ids:
        row = _get_order_line_row(order_line_id)
        if not row:
            continue

        if to_clean_string(row.get("Line_Status", "")) == "Cancelled":
            continue

        _update_sheet_row_by_id(
            ORDER_LINES_SHEET,
            order_line_id,
            {
                "Line_Status": "Cancelled",
                "Reserved_Status": "Not_Reserved",
                "Updated_At": today_str,
            }
        )
        cancelled_count += 1

    return cancelled_count

def _build_sales_pricing_lookup():
    rows = get_all_records(SALES_PRICING_SHEET)
    pricing_lookup = {}

    for row in rows:
        sale_category = to_clean_string(row.get("Sale_Category", ""))
        weight_band = to_clean_string(row.get("Weight_Band", ""))
        price_value = to_float(row.get("Price_Range", ""))

        if not sale_category or not weight_band:
            continue

        if price_value is None:
            continue

        pricing_lookup[(sale_category, weight_band)] = price_value

    return pricing_lookup

def _lookup_unit_price(pricing_lookup: dict, sale_category: str, weight_band: str):
    key = (to_clean_string(sale_category), to_clean_string(weight_band))

    if key not in pricing_lookup:
        raise ValueError(
            f"No pricing found in SALES_PRICING for {sale_category} / {weight_band}."
        )

    return pricing_lookup[key]


def _get_matching_available_pigs(sales_rows, blocked_pig_ids, category: str, weight_range: str, sex: str):
    target_categories = _sales_categories_for_request(category)
    matches = []

    for row in sales_rows:
        if to_clean_string(row.get("Available_For_Sale", "")) != "Yes":
            continue

        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            continue

        row_sale_category = to_clean_string(row.get("Sale_Category", ""))
        row_weight_band = to_clean_string(row.get("Weight_Band", ""))
        row_sex = to_clean_string(row.get("Sex", ""))
        row_pig_id = to_clean_string(row.get("Pig_ID", ""))

        if row_sale_category not in target_categories:
            continue

        if row_weight_band != to_clean_string(weight_range):
            continue

        if sex and sex != "Any" and row_sex != sex:
            continue

        if row_pig_id in blocked_pig_ids:
            continue

        matches.append({
            "pig_id": row_pig_id,
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "sex": row_sex,
            "current_weight_kg": to_float(row.get("Current_Weight_Kg", "")),
            "weight_band": row_weight_band,
            "sale_category": row_sale_category,
        })

    return sorted(matches, key=lambda x: ((x["tag_number"] or "").lower(), (x["pig_id"] or "").lower()))


def _build_same_category_alternatives(sales_rows, blocked_pig_ids, category: str, requested_weight_range: str, sex: str):
    target_categories = _sales_categories_for_request(category)
    grouped = {}

    for row in sales_rows:
        if to_clean_string(row.get("Available_For_Sale", "")) != "Yes":
            continue

        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            continue

        row_sale_category = to_clean_string(row.get("Sale_Category", ""))
        row_weight_band = to_clean_string(row.get("Weight_Band", ""))
        row_sex = to_clean_string(row.get("Sex", ""))
        row_pig_id = to_clean_string(row.get("Pig_ID", ""))

        if row_sale_category not in target_categories:
            continue

        if row_weight_band == to_clean_string(requested_weight_range):
            continue

        if sex and sex != "Any" and row_sex != sex:
            continue

        if row_pig_id in blocked_pig_ids:
            continue

        key = (row_sale_category, row_weight_band)
        grouped[key] = grouped.get(key, 0) + 1

    alternatives = []
    for (sale_category, weight_band), available_count in grouped.items():
        alternatives.append({
            "sale_category": sale_category,
            "weight_band": weight_band,
            "available_count": available_count,
        })

    return sorted(
        alternatives,
        key=lambda x: (_weight_band_sort_key(x["weight_band"]), (x["sale_category"] or "").lower())
    )


def _append_order_line_from_match(order_id: str, request_item_key: str, pig: dict, notes: str, pricing_lookup: dict):
    unit_price = _lookup_unit_price(pricing_lookup, pig["sale_category"], pig["weight_band"])
    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_order_line_id(),
        order_id,
        pig["pig_id"],
        pig["tag_number"],
        pig["sale_category"],
        pig["weight_band"],
        pig["sex"],
        pig["current_weight_kg"] if pig["current_weight_kg"] is not None else "",
        unit_price,
        "Draft",
        "Not_Reserved",
        notes,
        today_str,
        today_str,
        request_item_key,
    ]

    append_row(ORDER_LINES_SHEET, row_values)

    return {
        "pig_id": pig["pig_id"],
        "tag_number": pig["tag_number"],
        "sale_category": pig["sale_category"],
        "weight_band": pig["weight_band"],
        "unit_price": unit_price,
    }


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
            "request_item_key": to_clean_string(row.get("Request_Item_Key", "")),
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

    if not updated_fields:
        raise ValueError("No valid order fields were provided for update.")

    update_map["Updated_At"] = today_str

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


def sync_order_lines_from_request(order_id: str, cleaned_data: dict):
    order_id = str(order_id).strip()
    changed_by = str(cleaned_data.get("changed_by", "App")).strip() or "App"
    requested_items = cleaned_data.get("requested_items", [])

    order_row = _get_order_master_row(order_id)
    if not order_row:
        raise ValueError("Order not found.")

    order_status = to_clean_string(order_row.get("Order_Status", ""))
    if order_status not in ("Draft", ""):
        raise ValueError("Only draft orders can sync order lines.")

    pricing_lookup = _build_sales_pricing_lookup()
    sales_rows = get_all_records(SALES_AVAILABILITY_SHEET)
    order_lines_rows = get_all_records(ORDER_LINES_SHEET)

    results = []

    for item in requested_items:
        request_item_key = to_clean_string(item.get("request_item_key", ""))
        category = to_clean_string(item.get("category", ""))
        weight_range = to_clean_string(item.get("weight_range", ""))
        sex = to_clean_string(item.get("sex", ""))
        quantity = item.get("quantity", 0)
        notes = to_clean_string(item.get("notes", ""))

        existing_active_lines = _get_active_order_lines_by_request_item_from_rows(
            order_lines_rows,
            order_id,
            request_item_key,
        )
        existing_active_line_ids = [
            to_clean_string(row.get("Order_Line_ID", ""))
            for row in existing_active_lines
            if to_clean_string(row.get("Order_Line_ID", ""))
        ]

        blocked_pig_ids = _get_active_pig_ids_on_order_from_rows(
            order_lines_rows,
            order_id,
            exclude_request_item_key=request_item_key,
        )

        matches = _get_matching_available_pigs(
            sales_rows=sales_rows,
            blocked_pig_ids=blocked_pig_ids,
            category=category,
            weight_range=weight_range,
            sex=sex,
        )

        requested_quantity = int(quantity)
        matched_quantity = len(matches)
        alternatives = _build_same_category_alternatives(
            sales_rows=sales_rows,
            blocked_pig_ids=blocked_pig_ids,
            category=category,
            requested_weight_range=weight_range,
            sex=sex,
        )

        if matched_quantity >= requested_quantity:
            selected_matches = matches[:requested_quantity]

            cancelled_line_count = 0
            if existing_active_line_ids:
                cancelled_line_count = _cancel_order_lines(existing_active_line_ids)

            created_lines = []
            for pig in selected_matches:
                created_lines.append(
                    _append_order_line_from_match(
                        order_id=order_id,
                        request_item_key=request_item_key,
                        pig=pig,
                        notes=notes,
                        pricing_lookup=pricing_lookup,
                    )
                )

            match_status = "exact_match"

            if requested_quantity == 1 and matched_quantity == 1:
                match_status = "specific_acceptance_match"

            results.append({
                "request_item_key": request_item_key,
                "match_status": match_status,
                "requested_quantity": requested_quantity,
                "matched_quantity": requested_quantity,
                "existing_active_line_count": len(existing_active_lines),
                "cancelled_line_count": cancelled_line_count,
                "created_line_count": len(created_lines),
                "matched_pig_ids": [line["pig_id"] for line in created_lines],
                "alternatives": [],
            })
            continue

        if matched_quantity > 0:
            results.append({
                "request_item_key": request_item_key,
                "match_status": "partial_match",
                "requested_quantity": requested_quantity,
                "matched_quantity": matched_quantity,
                "existing_active_line_count": len(existing_active_lines),
                "cancelled_line_count": 0,
                "created_line_count": 0,
                "matched_pig_ids": [pig["pig_id"] for pig in matches],
                "alternatives": alternatives,
            })
            continue

        results.append({
            "request_item_key": request_item_key,
            "match_status": "no_match",
            "requested_quantity": requested_quantity,
            "matched_quantity": 0,
            "existing_active_line_count": len(existing_active_lines),
            "cancelled_line_count": 0,
            "created_line_count": 0,
            "matched_pig_ids": [],
            "alternatives": alternatives,
        })

    return {
        "success": True,
        "action": "sync_order_lines_from_request",
        "order_id": order_id,
        "changed_by": changed_by,
        "results": results,
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

    if old_status == "Pending_Approval":
        raise ValueError("Order is already pending approval.")

    if old_status == "Approved":
        raise ValueError("Approved orders cannot be sent for approval again.")

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

    webhook_result = _notify_n8n_order_approval_request(order_id, changed_by)

    result = {
        "success": True,
        "message": "Order sent for approval.",
        "order_id": order_id,
        "n8n_notified": webhook_result.get("sent", False),
    }

    if not webhook_result.get("sent", False):
        result["warning"] = "Order status updated, but approval notification could not be sent to n8n."
        result["n8n_error"] = webhook_result.get("error", "Unknown error")

    return result


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