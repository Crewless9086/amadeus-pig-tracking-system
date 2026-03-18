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


def validate_treatment_payload(payload: dict):
    errors = []

    pig_id = str(payload.get("pig_id", "")).strip()
    treatment_date = payload.get("treatment_date", "")
    treatment_type = str(payload.get("treatment_type", "")).strip()
    product_id = str(payload.get("product_id", "")).strip()
    dose = payload.get("dose", "")
    dose_unit = str(payload.get("dose_unit", "")).strip()
    route = str(payload.get("route", "")).strip()
    reason_for_treatment = str(payload.get("reason_for_treatment", "")).strip()
    batch_lot_number = str(payload.get("batch_lot_number", "")).strip()
    given_by = str(payload.get("given_by", "")).strip()
    follow_up_required = str(payload.get("follow_up_required", "")).strip()
    follow_up_date = payload.get("follow_up_date", "")
    medical_notes = str(payload.get("medical_notes", "")).strip()

    if not pig_id:
        errors.append("Pig_ID is required.")

    parsed_treatment_date = parse_sheet_date(treatment_date)
    if not parsed_treatment_date:
        errors.append("Treatment_Date is required and must be a valid date.")

    if not treatment_type:
        errors.append("Treatment_Type is required.")

    if not product_id:
        errors.append("Product_ID is required.")

    parsed_dose = to_float(dose)
    if parsed_dose is not None and parsed_dose < 0:
        errors.append("Dose cannot be negative.")

    parsed_follow_up_date = None
    if follow_up_date not in (None, ""):
        parsed_follow_up_date = parse_sheet_date(follow_up_date)
        if not parsed_follow_up_date:
            errors.append("Follow_Up_Date must be a valid date if provided.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "pig_id": pig_id,
            "treatment_date": parsed_treatment_date,
            "treatment_type": treatment_type,
            "product_id": product_id,
            "dose": parsed_dose,
            "dose_unit": dose_unit,
            "route": route,
            "reason_for_treatment": reason_for_treatment,
            "batch_lot_number": batch_lot_number,
            "given_by": given_by,
            "follow_up_required": follow_up_required,
            "follow_up_date": parsed_follow_up_date,
            "medical_notes": medical_notes,
        }
    }