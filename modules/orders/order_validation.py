from modules.pig_weights.pig_weights_utils import parse_sheet_date, to_float


def validate_new_order_payload(payload: dict):
    errors = []

    order_date = payload.get("order_date", "")
    customer_name = str(payload.get("customer_name", "")).strip()
    customer_phone = str(payload.get("customer_phone", "")).strip()
    customer_channel = str(payload.get("customer_channel", "")).strip()
    customer_language = str(payload.get("customer_language", "")).strip()
    order_source = str(payload.get("order_source", "")).strip()
    requested_category = str(payload.get("requested_category", "")).strip()
    requested_weight_range = str(payload.get("requested_weight_range", "")).strip()
    requested_sex = str(payload.get("requested_sex", "")).strip()
    requested_quantity = payload.get("requested_quantity", "")
    quoted_total = payload.get("quoted_total", "")
    notes = str(payload.get("notes", "")).strip()
    created_by = str(payload.get("created_by", "")).strip()

    parsed_order_date = parse_sheet_date(order_date)
    if not parsed_order_date:
        errors.append("Order_Date is required and must be a valid date.")

    if not customer_name:
        errors.append("Customer_Name is required.")

    if not customer_channel:
        errors.append("Customer_Channel is required.")

    if not customer_language:
        errors.append("Customer_Language is required.")

    if not order_source:
        errors.append("Order_Source is required.")

    parsed_requested_quantity = to_float(requested_quantity)
    if parsed_requested_quantity is not None and parsed_requested_quantity < 0:
        errors.append("Requested_Quantity cannot be negative.")

    parsed_quoted_total = to_float(quoted_total)
    if parsed_quoted_total is not None and parsed_quoted_total < 0:
        errors.append("Quoted_Total cannot be negative.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "order_date": parsed_order_date,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_channel": customer_channel,
            "customer_language": customer_language,
            "order_source": order_source,
            "requested_category": requested_category,
            "requested_weight_range": requested_weight_range,
            "requested_sex": requested_sex,
            "requested_quantity": parsed_requested_quantity,
            "quoted_total": parsed_quoted_total,
            "notes": notes,
            "created_by": created_by or "App",
        }
    }


def validate_new_order_line_payload(payload: dict):
    errors = []

    order_id = str(payload.get("order_id", "")).strip()
    pig_id = str(payload.get("pig_id", "")).strip()
    unit_price = payload.get("unit_price", "")
    notes = str(payload.get("notes", "")).strip()

    if not order_id:
        errors.append("Order_ID is required.")

    if not pig_id:
        errors.append("Pig_ID is required.")

    parsed_unit_price = to_float(unit_price)
    if parsed_unit_price is not None and parsed_unit_price < 0:
        errors.append("Unit_Price cannot be negative.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "order_id": order_id,
            "pig_id": pig_id,
            "unit_price": parsed_unit_price,
            "notes": notes,
        }
    }