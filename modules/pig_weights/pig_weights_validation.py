from modules.pig_weights.pig_weights_utils import to_float, parse_sheet_date


def validate_weight_payload(payload: dict):
    errors = []

    pig_id = str(payload.get("pig_id", "")).strip()
    weight_date = payload.get("weight_date", "")
    weight_kg = payload.get("weight_kg", "")
    condition_notes = str(payload.get("condition_notes", "")).strip()
    weighed_by = str(payload.get("weighed_by", "")).strip()

    if not pig_id:
        errors.append("Pig_ID is required.")

    parsed_date = parse_sheet_date(weight_date)
    if not parsed_date:
        errors.append("Weight_Date is required and must be a valid date.")

    parsed_weight = to_float(weight_kg)
    if parsed_weight is None:
        errors.append("Weight_Kg is required and must be a valid number.")
    elif parsed_weight <= 0:
        errors.append("Weight_Kg must be greater than 0.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "pig_id": pig_id,
            "weight_date": parsed_date,
            "weight_kg": parsed_weight,
            "condition_notes": condition_notes,
            "weighed_by": weighed_by,
        }
    }