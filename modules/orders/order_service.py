from datetime import datetime
import uuid

from services.google_sheets_service import get_all_records, append_row
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    to_float,
    format_date_for_json,
    format_date_for_sheet,
    parse_sheet_date,
)

ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
ORDER_OVERVIEW_SHEET = "ORDER_OVERVIEW"
SALES_AVAILABILITY_SHEET = "SALES_AVAILABILITY"


def generate_order_id():
    return f"ORD-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def generate_order_line_id():
    return f"OL-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


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
        order_id,                                           # Order_ID
        format_date_for_sheet(cleaned_data["order_date"]),  # Order_Date
        cleaned_data["customer_name"],                      # Customer_Name
        cleaned_data["customer_phone"],                     # Customer_Phone
        cleaned_data["customer_channel"],                   # Customer_Channel
        cleaned_data["customer_language"],                  # Customer_Language
        cleaned_data["order_source"],                       # Order_Source
        cleaned_data["requested_category"],                 # Requested_Category
        cleaned_data["requested_weight_range"],             # Requested_Weight_Range
        cleaned_data["requested_sex"],                      # Requested_Sex
        cleaned_data["requested_quantity"] if cleaned_data["requested_quantity"] is not None else "",
        cleaned_data["quoted_total"] if cleaned_data["quoted_total"] is not None else "",
        "",                                                 # Final_Total
        "Draft",                                            # Order_Status
        "Pending",                                          # Approval_Status
        "Collection_Only",                                  # Collection_Method
        "",                                                 # Collection_Location
        "",                                                 # Collection_Date
        "Pending",                                          # Payment_Status
        0,                                                  # Reserved_Pig_Count
        cleaned_data["notes"],                              # Notes
        cleaned_data["created_by"],                         # Created_By
        today_str,                                          # Created_At
        today_str,                                          # Updated_At
    ]

    append_row(ORDER_MASTER_SHEET, row_values)

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

    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_order_line_id(),                           # Order_Line_ID
        cleaned_data["order_id"],                           # Order_ID
        pig["pig_id"],                                      # Pig_ID
        pig["tag_number"],                                  # Tag_Number
        pig["sale_category"],                               # Sale_Category
        pig["weight_band"],                                 # Weight_Band
        pig["sex"],                                         # Sex
        pig["current_weight_kg"] if pig["current_weight_kg"] is not None else "",
        cleaned_data["unit_price"] if cleaned_data["unit_price"] is not None else "",
        "Draft",                                            # Line_Status
        "Not_Reserved",                                     # Reserved_Status
        cleaned_data["notes"],                              # Notes
        today_str,                                          # Created_At
        today_str,                                          # Updated_At
    ]

    append_row(ORDER_LINES_SHEET, row_values)

    return {
        "success": True,
        "message": "Order line added successfully."
    }