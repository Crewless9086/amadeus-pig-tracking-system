from datetime import date, datetime

from modules.pig_weights.pig_weights_utils import parse_sheet_date, to_float


ALLOWED_SALE_STREAMS = {"Livestock", "Slaughter", "Meat"}
ALLOWED_PAYMENT_STATUSES = {"Unpaid", "Deposit_Paid", "Part_Paid", "Paid", "Cancelled"}
ALLOWED_SALE_STATUSES = {"Draft", "Confirmed", "Completed", "Cancelled"}
ALLOWED_ITEM_TYPES = {"Pig", "Carcass", "Cut", "Box", "Other"}
ALLOWED_PRICING_BASIS = {"Per_Pig", "Per_Kg_Live", "Per_Kg_Carcass", "Per_Kg_Packed", "Per_Item"}


def validate_sales_transaction_payload(payload):
    errors = []

    sale_date = payload.get("sale_date", "")
    sale_stream = str(payload.get("sale_stream", "")).strip()
    buyer_name = str(payload.get("buyer_name", "")).strip()
    buyer_phone = str(payload.get("buyer_phone", payload.get("buyer_phone_raw", ""))).strip()
    destination = str(payload.get("destination", "")).strip()
    linked_order_id = str(payload.get("linked_order_id", "")).strip()
    payment_status = str(payload.get("payment_status", "Unpaid")).strip() or "Unpaid"
    payment_method = str(payload.get("payment_method", "")).strip()
    sale_status = str(payload.get("sale_status", "Draft")).strip() or "Draft"
    notes = str(payload.get("notes", "")).strip()
    created_by = str(payload.get("created_by", "App")).strip() or "App"
    deductions_total = _parse_optional_money(payload.get("deductions_total", 0), "deductions_total", errors)
    items_payload = payload.get("items", [])

    parsed_sale_date = parse_sheet_date(sale_date)
    if not parsed_sale_date:
        errors.append("sale_date is required and must be a valid date.")

    if sale_stream not in ALLOWED_SALE_STREAMS:
        errors.append("sale_stream must be Livestock, Slaughter, or Meat.")

    if payment_status not in ALLOWED_PAYMENT_STATUSES:
        errors.append("payment_status must be Unpaid, Deposit_Paid, Part_Paid, Paid, or Cancelled.")

    if sale_status not in ALLOWED_SALE_STATUSES:
        errors.append("sale_status must be Draft, Confirmed, Completed, or Cancelled.")

    if not isinstance(items_payload, list) or not items_payload:
        errors.append("items must contain at least one sale item.")
        items_payload = []

    cleaned_items = []
    gross_total = 0.0

    for index, item in enumerate(items_payload, start=1):
        cleaned_item = _validate_item(item if isinstance(item, dict) else {}, index, errors)
        cleaned_items.append(cleaned_item)
        if cleaned_item["line_total"] is not None:
            gross_total += cleaned_item["line_total"]

    deductions_total = deductions_total if deductions_total is not None else 0.0
    net_total = gross_total - deductions_total
    if net_total < 0:
        errors.append("net_total cannot be negative after deductions.")

    pig_count = sum(1 for item in cleaned_items if item["item_type"] == "Pig" and item["pig_id"])

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "sale_date": _date_iso(parsed_sale_date),
            "sale_stream": sale_stream,
            "buyer_name": buyer_name,
            "buyer_phone_raw": buyer_phone,
            "buyer_phone_normalized": _normalize_phone(buyer_phone),
            "destination": destination,
            "linked_order_id": linked_order_id,
            "pig_count": pig_count,
            "gross_total": round(gross_total, 2),
            "deductions_total": round(deductions_total, 2),
            "net_total": round(net_total, 2),
            "currency": "ZAR",
            "payment_status": payment_status,
            "payment_method": payment_method,
            "sale_status": sale_status,
            "notes": notes,
            "created_by": created_by,
            "items": cleaned_items,
        },
    }


def _validate_item(item, index, errors):
    item_type = str(item.get("item_type", "Pig")).strip() or "Pig"
    pig_id = str(item.get("pig_id", "")).strip()
    tag_number = str(item.get("tag_number", "")).strip()
    order_line_id = str(item.get("order_line_id", "")).strip()
    description = str(item.get("description", "")).strip()
    pricing_basis = str(item.get("pricing_basis", "")).strip()
    notes = str(item.get("notes", "")).strip()

    quantity = _parse_optional_number(item.get("quantity", 1), f"items[{index}].quantity", errors)
    live_weight_kg = _parse_optional_number(item.get("live_weight_kg", ""), f"items[{index}].live_weight_kg", errors)
    carcass_weight_kg = _parse_optional_number(item.get("carcass_weight_kg", ""), f"items[{index}].carcass_weight_kg", errors)
    packed_weight_kg = _parse_optional_number(item.get("packed_weight_kg", ""), f"items[{index}].packed_weight_kg", errors)
    unit_price = _parse_optional_money(item.get("unit_price", ""), f"items[{index}].unit_price", errors)
    line_total = _parse_optional_money(item.get("line_total", ""), f"items[{index}].line_total", errors)

    if item_type not in ALLOWED_ITEM_TYPES:
        errors.append(f"items[{index}].item_type must be Pig, Carcass, Cut, Box, or Other.")

    if pricing_basis and pricing_basis not in ALLOWED_PRICING_BASIS:
        errors.append(f"items[{index}].pricing_basis is not supported.")

    if item_type == "Pig" and not pig_id:
        errors.append(f"items[{index}].pig_id is required when item_type is Pig.")

    if quantity is not None and quantity < 0:
        errors.append(f"items[{index}].quantity cannot be negative.")

    if unit_price is not None and unit_price < 0:
        errors.append(f"items[{index}].unit_price cannot be negative.")

    if line_total is None and unit_price is not None and quantity is not None:
        line_total = unit_price * quantity

    if line_total is None:
        errors.append(f"items[{index}].line_total is required unless quantity and unit_price are provided.")
    elif line_total < 0:
        errors.append(f"items[{index}].line_total cannot be negative.")

    return {
        "item_type": item_type,
        "pig_id": pig_id,
        "tag_number": tag_number,
        "order_line_id": order_line_id,
        "description": description,
        "quantity": round(quantity if quantity is not None else 0, 3),
        "live_weight_kg": _round_optional(live_weight_kg, 3),
        "carcass_weight_kg": _round_optional(carcass_weight_kg, 3),
        "packed_weight_kg": _round_optional(packed_weight_kg, 3),
        "unit_price": _round_optional(unit_price, 2),
        "pricing_basis": pricing_basis,
        "line_total": _round_optional(line_total, 2),
        "notes": notes,
    }


def _parse_optional_number(value, field_name, errors):
    if value in (None, ""):
        return None
    parsed = to_float(value)
    if parsed is None:
        errors.append(f"{field_name} must be a number.")
    return parsed


def _parse_optional_money(value, field_name, errors):
    parsed = _parse_optional_number(value, field_name, errors)
    return parsed


def _round_optional(value, places):
    if value is None:
        return None
    return round(value, places)


def _date_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _normalize_phone(value):
    return "".join(char for char in str(value or "") if char.isdigit())
