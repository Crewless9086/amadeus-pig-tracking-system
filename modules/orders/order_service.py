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
    batch_update_rows_by_id,
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
PIG_MASTER_SHEET = "PIG_MASTER"

ORDER_APPROVAL_WEBHOOK_URL = os.getenv(
    "ORDER_APPROVAL_WEBHOOK_URL",
    "https://charln.app.n8n.cloud/webhook/46935f6b-2921-4d51-a477-1db5ac1024f7",
)
ORDER_NOTIFICATION_WEBHOOK_URL = os.getenv("ORDER_NOTIFICATION_WEBHOOK_URL", "").strip()

APPROVAL_CUSTOMER_MESSAGE = (
    "Your order has been approved. We have reserved the pigs linked to your order "
    "and will keep you posted on the next step."
)
REJECTION_CUSTOMER_MESSAGE = (
    "Your order was reviewed, but we cannot approve it at this stage. We will "
    "follow up if there is another suitable option."
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


def _notify_order_customer_notification(
    order_id: str,
    event_type: str,
    message_text: str,
    changed_by: str,
    order_row=None,
    extra_payload=None,
):
    if not ORDER_NOTIFICATION_WEBHOOK_URL:
        return {
            "sent": False,
            "skipped": True,
            "error": "ORDER_NOTIFICATION_WEBHOOK_URL is not configured.",
        }

    order_row = order_row or {}
    payload = {
        "event_type": str(event_type).strip(),
        "order_id": str(order_id).strip(),
        "conversation_id": to_clean_string(order_row.get("ConversationId", "")),
        "customer_name": to_clean_string(order_row.get("Customer_Name", "")),
        "customer_phone": to_clean_string(order_row.get("Customer_Phone", "")),
        "customer_channel": to_clean_string(order_row.get("Customer_Channel", "")),
        "order_status": to_clean_string(order_row.get("Order_Status", "")),
        "approval_status": to_clean_string(order_row.get("Approval_Status", "")),
        "changed_by": str(changed_by).strip() or "App",
        "message_text": str(message_text).strip(),
        "trigger_source": "Flask App",
        "extra": extra_payload or {},
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib_request.Request(
        ORDER_NOTIFICATION_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=5) as response:
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


def _add_notification_result_to_response(
    result: dict,
    order_id: str,
    changed_by: str,
    notification_result: dict,
    log_note: str,
    status_for_log: str,
):
    result["customer_notification_sent"] = notification_result.get("sent", False)

    if notification_result.get("sent", False):
        return

    result["notification_warning"] = (
        "Customer notification was not sent: "
        + notification_result.get("error", "Unknown error")
    )

    try:
        _write_order_status_log(
            order_id=order_id,
            old_status=status_for_log,
            new_status=status_for_log,
            changed_by=changed_by,
            change_source="App",
            notes=log_note + ": " + notification_result.get("error", "Unknown error"),
        )
    except Exception as exc:
        result["notification_status_log_warning"] = (
            "Customer notification warning could not be written to ORDER_STATUS_LOG: "
            + str(exc)
        )


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


def _cancel_order_lines(order_line_ids, order_lines_cache=None):
    """
    Cancel lines by ID. When order_lines_cache is provided (mutable list of row dicts),
    resolve rows from cache first to avoid a full ORDER_LINES read per line — needed
    when syncing multiple requested_items in one request (Sheets read quota).
    """
    today_str = datetime.now().strftime("%d %b %Y")
    cancelled_count = 0

    for order_line_id in order_line_ids:
        oid = str(order_line_id).strip()
        row = None
        if order_lines_cache is not None:
            for r in order_lines_cache:
                if to_clean_string(r.get("Order_Line_ID", "")) == oid:
                    row = r
                    break
        if row is None:
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
        row["Line_Status"] = "Cancelled"
        row["Reserved_Status"] = "Not_Reserved"
        row["Updated_At"] = today_str
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


def _get_matching_available_pigs(sales_rows, blocked_pig_ids, category: str, weight_range: str, sex: str, own_pig_ids: set = None):
    own_pig_ids = own_pig_ids or set()
    target_categories = _sales_categories_for_request(category)
    matches = []

    for row in sales_rows:
        if to_clean_string(row.get("Available_For_Sale", "")) != "Yes":
            continue

        row_pig_id = to_clean_string(row.get("Pig_ID", ""))

        # Allow pigs already reserved for this item to re-enter the candidate pool
        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            if row_pig_id not in own_pig_ids:
                continue

        row_sale_category = to_clean_string(row.get("Sale_Category", ""))
        row_weight_band = to_clean_string(row.get("Weight_Band", ""))
        row_sex = to_clean_string(row.get("Sex", ""))

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
    order_line_id = generate_order_line_id()
    wkg = pig["current_weight_kg"] if pig["current_weight_kg"] is not None else ""

    row_values = [
        order_line_id,
        order_id,
        pig["pig_id"],
        pig["tag_number"],
        pig["sale_category"],
        pig["weight_band"],
        pig["sex"],
        wkg,
        unit_price,
        "Draft",
        "Not_Reserved",
        notes,
        today_str,
        today_str,
        request_item_key,
    ]

    append_row(ORDER_LINES_SHEET, row_values)

    cache_row = {
        "Order_Line_ID": order_line_id,
        "Order_ID": str(order_id).strip(),
        "Pig_ID": to_clean_string(pig["pig_id"]),
        "Tag_Number": to_clean_string(pig.get("tag_number", "")),
        "Sale_Category": to_clean_string(pig["sale_category"]),
        "Weight_Band": to_clean_string(pig["weight_band"]),
        "Sex": to_clean_string(pig["sex"]),
        "Current_Weight_Kg": wkg,
        "Unit_Price": unit_price,
        "Line_Status": "Draft",
        "Reserved_Status": "Not_Reserved",
        "Notes": to_clean_string(notes),
        "Created_At": today_str,
        "Updated_At": today_str,
        "Request_Item_Key": str(request_item_key).strip(),
    }

    return {
        "order_line_id": order_line_id,
        "pig_id": pig["pig_id"],
        "tag_number": pig["tag_number"],
        "sale_category": pig["sale_category"],
        "weight_band": pig["weight_band"],
        "unit_price": unit_price,
        "cache_row": cache_row,
    }


def list_orders():
    rows = get_all_records(ORDER_OVERVIEW_SHEET)
    line_rollups = _build_order_line_rollups()
    master_rows = {
        to_clean_string(row.get("Order_ID", "")): row
        for row in get_all_records(ORDER_MASTER_SHEET)
        if to_clean_string(row.get("Order_ID", ""))
    }
    records = []

    for row in rows:
        order_id = to_clean_string(row.get("Order_ID", ""))
        if not order_id:
            continue

        rollup = line_rollups.get(order_id, _empty_order_line_rollup())
        master_row = master_rows.get(order_id, {})

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
            "payment_method": to_clean_string(master_row.get("Payment_Method", "")),
            "conversation_id": to_clean_string(master_row.get("ConversationId", "")),
            "collection_date": format_date_for_json(row.get("Collection_Date", "")),
            "collection_location": to_clean_string(row.get("Collection_Location", "")),
            "line_count": to_float(row.get("Line_Count", "")) or 0,
            "active_line_count": rollup["active_line_count"],
            "cancelled_line_count": rollup["cancelled_line_count"],
            "active_line_total": rollup["active_line_total"],
            "all_line_total": rollup["all_line_total"],
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

    master_row = _get_order_master_row(order_id)
    order_record["payment_method"] = (
        to_clean_string(master_row.get("Payment_Method", "")) if master_row else ""
    )
    order_record["conversation_id"] = (
        to_clean_string(master_row.get("ConversationId", "")) if master_row else ""
    )

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

    active_line_count = sum(
        1 for line in lines if to_clean_string(line.get("line_status", "")) != "Cancelled"
    )
    active_line_total = sum(
        float(line.get("unit_price") or 0)
        for line in lines
        if to_clean_string(line.get("line_status", "")) != "Cancelled"
    )
    all_line_total = sum(float(line.get("unit_price") or 0) for line in lines)
    order_record["active_line_count"] = active_line_count
    order_record["cancelled_line_count"] = len(lines) - active_line_count
    order_record["active_line_total"] = active_line_total
    order_record["all_line_total"] = all_line_total
    order_record["line_count_includes_cancelled"] = True

    return {
        "order": order_record,
        "lines": lines,
    }


def _build_order_line_rollups():
    rows = get_all_records(ORDER_LINES_SHEET)
    rollups = {}

    for row in rows:
        order_id = to_clean_string(row.get("Order_ID", ""))
        if not order_id:
            continue

        rollup = rollups.setdefault(order_id, _empty_order_line_rollup())
        line_status = to_clean_string(row.get("Line_Status", ""))
        unit_price = to_float(row.get("Unit_Price", "")) or 0

        rollup["all_line_count"] += 1
        rollup["all_line_total"] += unit_price

        if line_status == "Cancelled":
            rollup["cancelled_line_count"] += 1
            continue

        rollup["active_line_count"] += 1
        rollup["active_line_total"] += unit_price

    return rollups


def _empty_order_line_rollup():
    return {
        "all_line_count": 0,
        "active_line_count": 0,
        "cancelled_line_count": 0,
        "active_line_total": 0,
        "all_line_total": 0,
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
        _write_order_status_log(
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

    if not isinstance(requested_items, list) or len(requested_items) == 0:
        raise ValueError("requested_items must be a non-empty list.")

    order_row = _get_order_master_row(order_id)
    if not order_row:
        raise ValueError("Order not found.")

    order_status = to_clean_string(order_row.get("Order_Status", ""))
    if order_status not in ("Draft", ""):
        raise ValueError("Only draft orders can sync order lines.")

    pricing_lookup = _build_sales_pricing_lookup()
    results = []
    had_errors = False

    # One snapshot per sync avoids Google Sheets read quota bursts when multiple
    # requested_items each re-fetched SALES_AVAILABILITY + ORDER_LINES (and cancel
    # used a full ORDER_LINES read per line).
    sales_rows = get_all_records(SALES_AVAILABILITY_SHEET)
    order_lines_rows = list(get_all_records(ORDER_LINES_SHEET))

    for item in requested_items:
        request_item_key = to_clean_string(item.get("request_item_key", ""))
        category = to_clean_string(item.get("category", ""))
        weight_range = to_clean_string(item.get("weight_range", ""))
        sex = to_clean_string(item.get("sex", ""))
        notes = to_clean_string(item.get("notes", ""))

        try:
            quantity_raw = item.get("quantity", 0)
            requested_quantity = int(quantity_raw)

            if not request_item_key:
                raise ValueError("request_item_key is required.")
            if not category:
                raise ValueError(f"{request_item_key}: category is required.")
            if not weight_range:
                raise ValueError(f"{request_item_key}: weight_range is required.")
            if requested_quantity <= 0:
                raise ValueError(f"{request_item_key}: quantity must be greater than 0.")

            # Live state within this sync: refresh from in-memory snapshots + rows
            # appended/cancelled in earlier iterations.

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

            # Pigs already reserved for THIS item — allowed back into the candidate pool
            # so that re-syncing after a reserve call doesn't break split-item orders
            existing_active_pig_ids = {
                to_clean_string(row.get("Pig_ID", ""))
                for row in existing_active_lines
                if to_clean_string(row.get("Pig_ID", ""))
            }

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
                own_pig_ids=existing_active_pig_ids,
            )

            matched_quantity = len(matches)
            alternatives = _build_same_category_alternatives(
                sales_rows=sales_rows,
                blocked_pig_ids=blocked_pig_ids,
                category=category,
                requested_weight_range=weight_range,
                sex=sex,
            )

            # Exact match
            if matched_quantity >= requested_quantity:
                selected_matches = matches[:requested_quantity]

                cancelled_line_count = 0
                if existing_active_line_ids:
                    cancelled_line_count = _cancel_order_lines(
                        existing_active_line_ids, order_lines_rows
                    )

                created_lines = []
                for pig in selected_matches:
                    appended = _append_order_line_from_match(
                        order_id=order_id,
                        request_item_key=request_item_key,
                        pig=pig,
                        notes=notes,
                        pricing_lookup=pricing_lookup,
                    )
                    order_lines_rows.append(appended["cache_row"])
                    created_lines.append(
                        {k: v for k, v in appended.items() if k != "cache_row"}
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
                    "error": "",
                })
                continue

            # Partial match — allocate as many lines as we can (stock < requested)
            if matched_quantity > 0:
                take = min(matched_quantity, requested_quantity)
                selected_matches = matches[:take]

                cancelled_line_count = 0
                if existing_active_line_ids:
                    cancelled_line_count = _cancel_order_lines(
                        existing_active_line_ids, order_lines_rows
                    )

                created_lines = []
                for pig in selected_matches:
                    appended = _append_order_line_from_match(
                        order_id=order_id,
                        request_item_key=request_item_key,
                        pig=pig,
                        notes=notes,
                        pricing_lookup=pricing_lookup,
                    )
                    order_lines_rows.append(appended["cache_row"])
                    created_lines.append(
                        {k: v for k, v in appended.items() if k != "cache_row"}
                    )

                results.append({
                    "request_item_key": request_item_key,
                    "match_status": "partial_match",
                    "requested_quantity": requested_quantity,
                    "matched_quantity": len(created_lines),
                    "available_quantity": matched_quantity,
                    "existing_active_line_count": len(existing_active_lines),
                    "cancelled_line_count": cancelled_line_count,
                    "created_line_count": len(created_lines),
                    "matched_pig_ids": [line["pig_id"] for line in created_lines],
                    "alternatives": alternatives,
                    "error": "",
                })
                continue

            # No match
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
                "error": "",
            })

        except Exception as exc:
            had_errors = True
            results.append({
                "request_item_key": request_item_key or "",
                "match_status": "error",
                "requested_quantity": item.get("quantity", ""),
                "matched_quantity": 0,
                "existing_active_line_count": 0,
                "cancelled_line_count": 0,
                "created_line_count": 0,
                "matched_pig_ids": [],
                "alternatives": [],
                "error": str(exc),
            })

    partial_fulfillment = any(
        r.get("match_status") == "partial_match" for r in results
    )

    return {
        "success": not had_errors,
        "action": "sync_order_lines_from_request",
        "order_id": order_id,
        "changed_by": changed_by,
        "results": results,
        "partial_fulfillment": partial_fulfillment,
        "message": "Order line sync completed." if not had_errors else "Order line sync completed with errors.",
    }


def reserve_order_lines(order_id: str):
    """
    Reserve all eligible lines for an order.

    Eligibility rules:
    - Lines with Line_Status in (Cancelled, Collected) are skipped — terminal states.
    - Lines with no Pig_ID are skipped — placeholder lines cannot hold inventory.
    - Lines already Reserved on both fields are a noop — idempotent reserve.
    - All other active lines with a Pig_ID are reserved in one batch write.

    success=True when at least one line is or becomes Reserved.
    success=False when nothing could be reserved (all skipped, none eligible).
    A warning is returned when success=True but some lines were skipped.
    changed_count = rows written to ORDER_LINES.
    """
    order_id = str(order_id).strip()

    if not _get_order_master_row(order_id):
        raise ValueError("Order not found.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Reserved_Status", "Updated_At"]:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_lines_in_scope = []
    for row in rows:
        if not row:
            continue
        padded = row + [""] * (len(headers) - len(row))
        if str(padded[idx["Order_ID"]]).strip() == order_id:
            order_lines_in_scope.append(padded)

    if not order_lines_in_scope:
        raise ValueError("Order has no lines to reserve.")

    line_results = []
    updates_map = {}

    for padded_row in order_lines_in_scope:
        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        pig_id = str(padded_row[idx["Pig_ID"]]).strip()
        line_status = str(padded_row[idx["Line_Status"]]).strip()
        reserved_status = str(padded_row[idx["Reserved_Status"]]).strip()

        if not line_id:
            continue

        # Terminal states — never touch
        if line_status in ("Cancelled", "Collected"):
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "skipped",
                "reason": "terminal_line_status",
            })
            continue

        # Must have a pig assigned before holding inventory
        if not pig_id:
            line_results.append({
                "order_line_id": line_id,
                "pig_id": "",
                "action": "skipped",
                "reason": "no_pig_assigned",
            })
            continue

        # Already fully reserved — idempotent noop
        if reserved_status == "Reserved" and line_status == "Reserved":
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "noop",
                "reason": "already_reserved",
            })
            continue

        updates_map[line_id] = {
            "Reserved_Status": "Reserved",
            "Line_Status": "Reserved",
            "Updated_At": today_str,
        }
        line_results.append({
            "order_line_id": line_id,
            "pig_id": pig_id,
            "action": "reserved",
        })

    reserved_now = sum(1 for r in line_results if r["action"] == "reserved")
    noop_count = sum(1 for r in line_results if r["action"] == "noop")
    skipped_count = sum(1 for r in line_results if r["action"] == "skipped")

    if updates_map:
        batch_update_rows_by_id(ORDER_LINES_SHEET, updates_map)

    reserved_pig_count = _count_reserved_lines(order_id)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Reserved_Pig_Count": reserved_pig_count,
            "Updated_At": today_str,
        },
    )

    # success=True when at least one line is now or already reserved
    success = (reserved_now + noop_count) > 0

    result = {
        "success": success,
        "order_id": order_id,
        "reserved_pig_count": reserved_pig_count,
        "changed_count": len(updates_map),
        "line_results": line_results,
    }

    if success:
        result["message"] = "Order lines reserved successfully." if reserved_now > 0 else "All eligible lines are already reserved."
        if skipped_count > 0:
            skip_reasons: dict = {}
            for r in line_results:
                if r["action"] == "skipped":
                    reason = r.get("reason", "unknown")
                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            parts = [f"{count} line(s) skipped ({reason})" for reason, count in skip_reasons.items()]
            result["warning"] = f"Some lines could not be reserved: {'; '.join(parts)}."
    else:
        result["message"] = "No lines could be reserved."
        result["errors"] = [
            "No eligible lines to reserve. All lines are either cancelled, collected, or have no pig assigned."
        ]

    return result


def release_order_lines(order_id: str):
    """
    Release all reservations for an order.

    Rules:
    - Collected lines are terminal — never touched.
    - Reserved_Status is cleared to Not_Reserved only where it equals Reserved.
    - Line_Status is reverted from Reserved to Draft only where applicable
      (Cancelled lines keep their Cancelled status; only active Reserved lines revert).
    - Calling release twice succeeds and reports only noops on the second call.
    - ORDER_MASTER.Reserved_Pig_Count is set to the actual post-release count.
    - changed_count = rows written to ORDER_LINES.
    """
    order_id = str(order_id).strip()

    if not _get_order_master_row(order_id):
        raise ValueError("Order not found.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Reserved_Status", "Updated_At"]:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    today_str = datetime.now().strftime("%d %b %Y")

    line_results = []
    updates_map = {}

    for row in rows:
        if not row:
            continue

        padded_row = row + [""] * (len(headers) - len(row))
        if str(padded_row[idx["Order_ID"]]).strip() != order_id:
            continue

        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        pig_id = str(padded_row[idx["Pig_ID"]]).strip()
        line_status = str(padded_row[idx["Line_Status"]]).strip()
        reserved_status = str(padded_row[idx["Reserved_Status"]]).strip()

        if not line_id:
            continue

        # Collected lines are terminal — do not revert
        if line_status == "Collected":
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "skipped",
                "reason": "terminal_line_status",
            })
            continue

        needs_reserved_status_clear = reserved_status == "Reserved"
        # Only revert Line_Status from Reserved → Draft for non-Cancelled active lines
        needs_line_status_revert = line_status == "Reserved"

        if not needs_reserved_status_clear and not needs_line_status_revert:
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "noop",
            })
            continue

        field_updates: dict = {"Updated_At": today_str}
        if needs_reserved_status_clear:
            field_updates["Reserved_Status"] = "Not_Reserved"
        if needs_line_status_revert:
            field_updates["Line_Status"] = "Draft"

        updates_map[line_id] = field_updates
        line_results.append({
            "order_line_id": line_id,
            "pig_id": pig_id,
            "action": "released",
        })

    if updates_map:
        batch_update_rows_by_id(ORDER_LINES_SHEET, updates_map)

    reserved_pig_count = _count_reserved_lines(order_id)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Reserved_Pig_Count": reserved_pig_count,
            "Updated_At": today_str,
        },
    )

    changed_count = len(updates_map)

    return {
        "success": True,
        "message": "Order reservations released successfully." if changed_count > 0 else "No active reservations to release.",
        "order_id": order_id,
        "reserved_pig_count": reserved_pig_count,
        "changed_count": changed_count,
        "line_results": line_results,
    }


def send_order_for_approval(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status != "Draft":
        raise ValueError(
            f"Only Draft orders can be sent for approval. Current status: {old_status}."
        )

    payment_method = to_clean_string(row.get("Payment_Method", ""))
    if payment_method not in ("Cash", "EFT"):
        raise ValueError(
            "Payment method must be set to Cash or EFT before sending for approval."
        )

    customer_name = to_clean_string(row.get("Customer_Name", ""))
    if not customer_name:
        raise ValueError("Customer name is required before sending for approval.")

    collection_location = to_clean_string(row.get("Collection_Location", ""))
    if not collection_location:
        raise ValueError(
            "Collection location is required before sending for approval."
        )

    all_lines = get_all_records(ORDER_LINES_SHEET)
    active_lines = [
        line for line in all_lines
        if to_clean_string(line.get("Order_ID", "")) == order_id
        and to_clean_string(line.get("Line_Status", "")) != "Cancelled"
    ]
    if not active_lines:
        raise ValueError(
            "At least one active order line is required before sending for approval."
        )

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

    if old_status != "Pending_Approval":
        raise ValueError(
            f"Only Pending_Approval orders can be approved. Current status: {old_status}."
        )

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

    result = {
        "success": True,
        "message": "Order approved successfully.",
        "order_id": order_id,
    }

    reserve_result = None
    reserve_warning = ""

    try:
        reserve_result = reserve_order_lines(order_id)
        result["auto_reserve"] = reserve_result

        if not reserve_result.get("success"):
            reserve_warning = (
                reserve_result.get("message")
                or "; ".join(reserve_result.get("errors", []))
                or "Auto-reservation did not reserve any order lines."
            )
        elif reserve_result.get("warning"):
            reserve_warning = reserve_result["warning"]

    except Exception as exc:
        reserve_warning = f"Auto-reservation failed after approval: {str(exc)}"

    if reserve_warning:
        result["reserve_warning"] = reserve_warning
        result["warning"] = reserve_warning

        try:
            _write_order_status_log(
                order_id=order_id,
                old_status="Approved | Approved",
                new_status="Approved | Approved",
                changed_by=changed_by,
                change_source="App",
                notes=f"Approval completed, but reservation needs manual follow-up: {reserve_warning}",
            )
        except Exception as exc:
            result["status_log_warning"] = (
                "Reservation warning could not be written to ORDER_STATUS_LOG: "
                + str(exc)
            )

    notification_row = _get_order_master_row(order_id) or row
    notification_result = _notify_order_customer_notification(
        order_id=order_id,
        event_type="order_approved",
        message_text=APPROVAL_CUSTOMER_MESSAGE,
        changed_by=changed_by,
        order_row=notification_row,
        extra_payload={
            "reserve_warning": reserve_warning,
            "auto_reserve": reserve_result,
        },
    )
    _add_notification_result_to_response(
        result=result,
        order_id=order_id,
        changed_by=changed_by,
        notification_result=notification_result,
        log_note="Approval completed, but customer notification needs manual follow-up",
        status_for_log="Approved | Approved",
    )

    return result


def reject_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status == "Completed":
        raise ValueError("Completed orders cannot be rejected.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_line_rows = get_all_records(ORDER_LINES_SHEET)
    line_ids_to_cancel = []

    for line in order_line_rows:
        if to_clean_string(line.get("Order_ID", "")) != order_id:
            continue

        line_status = to_clean_string(line.get("Line_Status", ""))
        if line_status in ("Cancelled", "Collected"):
            continue

        line_id = to_clean_string(line.get("Order_Line_ID", ""))
        if line_id:
            line_ids_to_cancel.append(line_id)

    cancelled_line_count = _cancel_order_lines(line_ids_to_cancel)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Cancelled",
            "Approval_Status": "Rejected",
            "Reserved_Pig_Count": 0,
            "Updated_At": today_str,
        }
    )

    if old_status != "Cancelled" or old_approval != "Rejected" or cancelled_line_count:
        _write_order_status_log(
            order_id=order_id,
            old_status=f"{old_status} | {old_approval}",
            new_status="Cancelled | Rejected",
            changed_by=changed_by,
            change_source="App",
            notes=f"Order rejected; {cancelled_line_count} line(s) cancelled and reservations released",
        )

    result = {
        "success": True,
        "message": "Order rejected successfully.",
        "order_id": order_id,
        "cancelled_line_count": cancelled_line_count,
        "reserved_pig_count": 0,
    }

    notification_row = _get_order_master_row(order_id) or row
    notification_result = _notify_order_customer_notification(
        order_id=order_id,
        event_type="order_rejected",
        message_text=REJECTION_CUSTOMER_MESSAGE,
        changed_by=changed_by,
        order_row=notification_row,
        extra_payload={
            "cancelled_line_count": cancelled_line_count,
            "reserved_pig_count": 0,
        },
    )
    _add_notification_result_to_response(
        result=result,
        order_id=order_id,
        changed_by=changed_by,
        notification_result=notification_result,
        log_note="Rejection completed, but customer notification needs manual follow-up",
        status_for_log="Cancelled | Rejected",
    )

    return result


def cancel_order(order_id: str, changed_by: str = "App", reason: str = ""):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status == "Completed":
        raise ValueError("Completed orders cannot be cancelled.")

    if old_status == "Cancelled" and old_approval == "Rejected":
        raise ValueError("Rejected orders are already cancelled and cannot be customer-cancelled.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_line_rows = get_all_records(ORDER_LINES_SHEET)
    line_ids_to_cancel = []

    for line in order_line_rows:
        if to_clean_string(line.get("Order_ID", "")) != order_id:
            continue

        line_status = to_clean_string(line.get("Line_Status", ""))
        if line_status in ("Cancelled", "Collected"):
            continue

        line_id = to_clean_string(line.get("Order_Line_ID", ""))
        if line_id:
            line_ids_to_cancel.append(line_id)

    cancelled_line_count = _cancel_order_lines(line_ids_to_cancel)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Cancelled",
            "Approval_Status": "Not_Required",
            "Payment_Status": "Cancelled",
            "Reserved_Pig_Count": 0,
            "Updated_At": today_str,
        }
    )

    if old_status != "Cancelled" or old_approval != "Not_Required" or cancelled_line_count:
        log_note = f"Order cancelled by customer; {cancelled_line_count} line(s) cancelled and reservations released"
        clean_reason = str(reason or "").strip()
        if clean_reason:
            log_note = f"{log_note}. Reason: {clean_reason}"

        _write_order_status_log(
            order_id=order_id,
            old_status=f"{old_status} | {old_approval}",
            new_status="Cancelled | Not_Required",
            changed_by=changed_by,
            change_source="Customer",
            notes=log_note,
        )

    return {
        "success": True,
        "message": "Order cancelled successfully.",
        "order_id": order_id,
        "cancelled_line_count": cancelled_line_count,
        "reserved_pig_count": 0,
        "payment_status": "Cancelled",
        "approval_status": "Not_Required",
    }


def complete_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    order_row = _get_order_master_row(order_id)

    if not order_row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(order_row.get("Order_Status", ""))
    old_approval = to_clean_string(order_row.get("Approval_Status", ""))

    if old_status != "Approved":
        raise ValueError(f"Only Approved orders can be completed. Current status: {old_status}.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Updated_At"]:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    active_lines = []
    for row in rows:
        if not row:
            continue
        padded_row = row + [""] * (len(headers) - len(row))
        if str(padded_row[idx["Order_ID"]]).strip() != order_id:
            continue
        if str(padded_row[idx["Line_Status"]]).strip() == "Cancelled":
            continue
        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        pig_id = str(padded_row[idx["Pig_ID"]]).strip()
        if not line_id:
            continue
        active_lines.append({"line_id": line_id, "pig_id": pig_id})

    if not active_lines:
        raise ValueError("Order has no active lines to complete.")

    missing_pig = [l["line_id"] for l in active_lines if not l["pig_id"]]
    if missing_pig:
        raise ValueError(f"The following lines have no Pig_ID and cannot be completed: {', '.join(missing_pig)}")

    today_str = datetime.now().strftime("%d %b %Y")

    # Build and apply all ORDER_LINES updates in a single API call
    order_lines_updates = {
        line["line_id"]: {
            "Line_Status":     "Collected",
            "Reserved_Status": "Collected",
            "Updated_At":      today_str,
        }
        for line in active_lines
    }
    batch_update_rows_by_id(ORDER_LINES_SHEET, order_lines_updates)

    # Build and apply all PIG_MASTER updates in a single API call
    pig_updates = {
        line["pig_id"]: {
            "Status": "Sold",
            "On_Farm": "No",
            "Exit_Date": today_str,
            "Exit_Reason": "Sold",
            "Exit_Order_ID": order_id,
            "Updated_At": today_str,
        }
        for line in active_lines
    }
    batch_update_rows_by_id(PIG_MASTER_SHEET, pig_updates)

    _update_sheet_row_by_id(ORDER_MASTER_SHEET, order_id, {
        "Order_Status": "Completed",
        "Updated_At": today_str,
    })

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Completed | Approved",
        changed_by=changed_by,
        change_source="App",
        notes=f"Order completed — {len(active_lines)} pig(s) marked as sold",
    )

    return {
        "success": True,
        "message": "Order completed successfully.",
        "order_id": order_id,
        "pigs_marked_sold": len(active_lines),
    }
