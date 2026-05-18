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
)


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
SALES_AVAILABILITY_SHEET = "SALES_AVAILABILITY"
SALES_PRICING_SHEET = "SALES_PRICING"

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


def _row_is_active_order_line(row: dict):
    return to_clean_string(row.get("Line_Status", "")) != "Cancelled"


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


def _weight_band_sort_key(weight_band: str):
    try:
        return WEIGHT_BAND_ORDER.index(to_clean_string(weight_band))
    except ValueError:
        return 9999


def _sales_categories_for_request(category: str):
    category = to_clean_string(category)
    return CATEGORY_REQUEST_TO_SALES.get(category, [category])


def _cancel_order_lines(order_line_ids, order_lines_cache=None):
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


def sync_order_lines_from_request(order_id: str, cleaned_data: dict):
    order_id = str(order_id).strip()
    changed_by = str(cleaned_data.get("changed_by", "App")).strip() or "App"
    requested_items = cleaned_data.get("requested_items", [])
    cancel_order_if_no_matches = cleaned_data.get("cancel_order_if_no_matches") is True

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

    def _qty(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

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

    requested_total = sum(max(0, _qty(r.get("requested_quantity"))) for r in results)
    matched_total = sum(max(0, _qty(r.get("matched_quantity"))) for r in results)
    unmatched_total = max(0, requested_total - matched_total)

    incomplete_items = []
    for r in results:
        requested_quantity = max(0, _qty(r.get("requested_quantity")))
        matched_quantity = max(0, _qty(r.get("matched_quantity")))
        status = to_clean_string(r.get("match_status", ""))
        if status in ("partial_match", "no_match", "error") or matched_quantity < requested_quantity:
            incomplete_items.append({
                "request_item_key": r.get("request_item_key", ""),
                "match_status": status,
                "requested_quantity": requested_quantity,
                "matched_quantity": matched_quantity,
                "unmatched_quantity": max(0, requested_quantity - matched_quantity),
                "alternatives": r.get("alternatives", []),
                "error": r.get("error", ""),
            })

    complete_fulfillment = (
        not had_errors
        and requested_total > 0
        and unmatched_total == 0
        and len(incomplete_items) == 0
    )
    partial_fulfillment = not complete_fulfillment

    if had_errors:
        fulfillment_status = "error"
    elif complete_fulfillment:
        fulfillment_status = "complete"
    elif matched_total > 0:
        fulfillment_status = "partial"
    else:
        fulfillment_status = "no_match"

    cancelled_empty_order = False
    cancel_result = None
    if cancel_order_if_no_matches and matched_total == 0 and not had_errors:
        from modules.orders.order_service import cancel_order

        cancel_result = cancel_order(
            order_id,
            changed_by=changed_by,
            reason="Auto-cancelled because create-with-lines matched zero requested pigs.",
        )
        cancelled_empty_order = cancel_result.get("success") is True

    return {
        "success": not had_errors,
        "action": "sync_order_lines_from_request",
        "order_id": order_id,
        "order_status": "Cancelled" if cancelled_empty_order else order_status,
        "changed_by": changed_by,
        "results": results,
        "partial_fulfillment": partial_fulfillment,
        "complete_fulfillment": complete_fulfillment,
        "fulfillment_status": fulfillment_status,
        "requested_total": requested_total,
        "matched_total": matched_total,
        "unmatched_total": unmatched_total,
        "incomplete_items": incomplete_items,
        "cancelled_empty_order": cancelled_empty_order,
        "cancel_result": cancel_result,
        "message": "Order line sync completed." if not had_errors else "Order line sync completed with errors.",
    }
