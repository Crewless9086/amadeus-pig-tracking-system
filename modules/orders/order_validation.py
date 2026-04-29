from modules.pig_weights.pig_weights_utils import parse_sheet_date, to_float


ALLOWED_REQUESTED_CATEGORIES = {
    "Piglet",
    "Weaner",
    "Grower",
    "Finisher",
    "Slaughter",
}


ALLOWED_SYNC_ITEM_CATEGORIES = {
    "Piglet",
    "Weaner",
    "Grower",
    "Finisher",
    "Slaughter",
    "Young Piglets",
    "Weaner Piglets",
    "Grower Pigs",
    "Finisher Pigs",
    "Ready for Slaughter",
}


ALLOWED_REQUESTED_WEIGHT_RANGES = {
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
}


ALLOWED_REQUESTED_SEX = {
    "Male",
    "Female",
    "Any",
}


ALLOWED_COLLECTION_LOCATIONS = {
    "Riversdale",
    "Albertinia",
    "Any",
}


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
    request_item_key = str(payload.get("request_item_key", "")).strip()

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
            "request_item_key": request_item_key,
        }
    }


def validate_update_order_line_payload(payload: dict):
    errors = []

    unit_price = payload.get("unit_price", "")
    notes = str(payload.get("notes", "")).strip()

    parsed_unit_price = to_float(unit_price)
    if parsed_unit_price is not None and parsed_unit_price < 0:
        errors.append("Unit_Price cannot be negative.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "unit_price": parsed_unit_price,
            "notes": notes,
        }
    }


def validate_update_order_payload(payload: dict):
    errors = []
    cleaned_data = {}

    allowed_keys = {
        "requested_quantity",
        "requested_category",
        "requested_weight_range",
        "requested_sex",
        "collection_location",
        "notes",
        "changed_by",
        "payment_method",
    }

    for key in payload.keys():
        if key not in allowed_keys:
            errors.append(f"Field '{key}' is not allowed for order update.")

    if "requested_quantity" in payload:
        raw_quantity = payload.get("requested_quantity", "")
        if raw_quantity == "" or raw_quantity is None:
            cleaned_data["requested_quantity"] = ""
        else:
            parsed_requested_quantity = to_float(raw_quantity)
            if parsed_requested_quantity is None:
                errors.append("Requested_Quantity must be a valid number.")
            elif parsed_requested_quantity < 0:
                errors.append("Requested_Quantity cannot be negative.")
            else:
                cleaned_data["requested_quantity"] = parsed_requested_quantity

    if "requested_category" in payload:
        requested_category = str(payload.get("requested_category", "")).strip()
        if requested_category and requested_category not in ALLOWED_REQUESTED_CATEGORIES:
            errors.append(
                "Requested_Category must be one of: "
                + ", ".join(sorted(ALLOWED_REQUESTED_CATEGORIES))
                + "."
            )
        else:
            cleaned_data["requested_category"] = requested_category

    if "requested_weight_range" in payload:
        requested_weight_range = str(payload.get("requested_weight_range", "")).strip()
        if requested_weight_range and requested_weight_range not in ALLOWED_REQUESTED_WEIGHT_RANGES:
            errors.append(
                "Requested_Weight_Range must be one of the approved stored values."
            )
        else:
            cleaned_data["requested_weight_range"] = requested_weight_range

    if "requested_sex" in payload:
        requested_sex = str(payload.get("requested_sex", "")).strip()
        if requested_sex and requested_sex not in ALLOWED_REQUESTED_SEX:
            errors.append(
                "Requested_Sex must be one of: "
                + ", ".join(sorted(ALLOWED_REQUESTED_SEX))
                + "."
            )
        else:
            cleaned_data["requested_sex"] = requested_sex

    if "collection_location" in payload:
        collection_location = str(payload.get("collection_location", "")).strip()
        if collection_location and collection_location not in ALLOWED_COLLECTION_LOCATIONS:
            errors.append(
                "Collection_Location must be one of: "
                + ", ".join(sorted(ALLOWED_COLLECTION_LOCATIONS))
                + "."
            )
        else:
            cleaned_data["collection_location"] = collection_location

    if "notes" in payload:
        cleaned_data["notes"] = str(payload.get("notes", "")).strip()

    if "payment_method" in payload:
        pm = str(payload.get("payment_method", "")).strip()
        if pm and pm not in ("Cash", "EFT"):
            errors.append("payment_method must be Cash or EFT.")
        else:
            cleaned_data["payment_method"] = pm

    cleaned_data["changed_by"] = str(payload.get("changed_by", "App")).strip() or "App"

    updatable_fields_present = any(
        key in cleaned_data
        for key in (
            "requested_quantity",
            "requested_category",
            "requested_weight_range",
            "requested_sex",
            "collection_location",
            "notes",
            "payment_method",
        )
    )

    if not updatable_fields_present:
        errors.append("At least one allowed order field must be provided for update.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": cleaned_data,
    }


def validate_sync_order_lines_payload(payload: dict):
    errors = []

    requested_items = payload.get("requested_items", [])
    changed_by = str(payload.get("changed_by", "App")).strip() or "App"

    if not isinstance(requested_items, list) or len(requested_items) == 0:
        errors.append("requested_items is required and must be a non-empty list.")
        return {
            "is_valid": False,
            "errors": errors,
            "cleaned_data": {
                "changed_by": changed_by,
                "requested_items": [],
            }
        }

    cleaned_items = []

    for index, item in enumerate(requested_items):
        if not isinstance(item, dict):
            errors.append(f"requested_items[{index}] must be an object.")
            continue

        request_item_key = str(item.get("request_item_key", "")).strip()
        category = str(item.get("category", "")).strip()
        weight_range = str(item.get("weight_range", "")).strip()
        sex = str(item.get("sex", "")).strip()
        quantity_raw = item.get("quantity", "")
        intent_type = str(item.get("intent_type", "")).strip()
        status = str(item.get("status", "active")).strip() or "active"
        notes = str(item.get("notes", "")).strip()

        if not request_item_key:
            errors.append(f"requested_items[{index}].request_item_key is required.")

        if not category:
            errors.append(f"requested_items[{index}].category is required.")
        elif category not in ALLOWED_SYNC_ITEM_CATEGORIES:
            errors.append(
                f"requested_items[{index}].category must be one of the approved category values."
            )

        if not weight_range:
            errors.append(f"requested_items[{index}].weight_range is required.")
        elif weight_range not in ALLOWED_REQUESTED_WEIGHT_RANGES:
            errors.append(
                f"requested_items[{index}].weight_range must be one of the approved stored values."
            )

        if sex and sex not in ALLOWED_REQUESTED_SEX:
            errors.append(
                f"requested_items[{index}].sex must be one of: "
                + ", ".join(sorted(ALLOWED_REQUESTED_SEX))
                + "."
            )

        parsed_quantity = to_float(quantity_raw)
        if parsed_quantity is None:
            errors.append(f"requested_items[{index}].quantity is required and must be a number.")
        elif parsed_quantity <= 0:
            errors.append(f"requested_items[{index}].quantity must be greater than 0.")
        elif int(parsed_quantity) != parsed_quantity:
            errors.append(f"requested_items[{index}].quantity must be a whole number.")

        cleaned_items.append({
            "request_item_key": request_item_key,
            "category": category,
            "weight_range": weight_range,
            "sex": sex,
            "quantity": int(parsed_quantity) if parsed_quantity is not None and parsed_quantity > 0 and int(parsed_quantity) == parsed_quantity else None,
            "intent_type": intent_type,
            "status": status,
            "notes": notes,
        })

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "changed_by": changed_by,
            "requested_items": cleaned_items,
        }
    }