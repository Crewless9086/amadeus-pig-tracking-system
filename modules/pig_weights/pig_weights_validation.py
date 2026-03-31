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

def validate_weight_with_optional_move_payload(payload: dict):
    errors = []

    pig_id = str(payload.get("pig_id", "")).strip()
    weight_date = payload.get("weight_date", "")
    weight_kg = payload.get("weight_kg", "")
    condition_notes = str(payload.get("condition_notes", "")).strip()
    weighed_by = str(payload.get("weighed_by", "")).strip()
    moved_to_pen_id = str(payload.get("moved_to_pen_id", "")).strip()

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
            "weighed_by": weighed_by or "WebApp",
            "moved_to_pen_id": moved_to_pen_id,
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


def validate_movement_payload(payload: dict):
    errors = []

    pig_id = str(payload.get("pig_id", "")).strip()
    move_date = payload.get("move_date", "")
    from_pen_id = str(payload.get("from_pen_id", "")).strip()
    to_pen_id = str(payload.get("to_pen_id", "")).strip()
    reason_for_move = str(payload.get("reason_for_move", "")).strip()
    moved_by = str(payload.get("moved_by", "")).strip()
    move_notes = str(payload.get("move_notes", "")).strip()

    if not pig_id:
        errors.append("Pig_ID is required.")

    parsed_move_date = parse_sheet_date(move_date)
    if not parsed_move_date:
        errors.append("Move_Date is required and must be a valid date.")

    if not to_pen_id:
        errors.append("To_Pen_ID is required.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "pig_id": pig_id,
            "move_date": parsed_move_date,
            "from_pen_id": from_pen_id,
            "to_pen_id": to_pen_id,
            "reason_for_move": reason_for_move,
            "moved_by": moved_by,
            "move_notes": move_notes,
        }
    }


def validate_new_pig_payload(payload: dict):
    errors = []

    tag_number = str(payload.get("tag_number", "")).strip()
    status = str(payload.get("status", "")).strip()
    on_farm = str(payload.get("on_farm", "")).strip()
    animal_type = str(payload.get("animal_type", "")).strip()
    sex = str(payload.get("sex", "")).strip()
    date_of_birth = payload.get("date_of_birth", "")
    purpose = str(payload.get("purpose", "")).strip()
    source = str(payload.get("source", "")).strip()

    if not tag_number:
        errors.append("Tag_Number is required.")
    if not status:
        errors.append("Status is required.")
    if not on_farm:
        errors.append("On_Farm is required.")
    if not animal_type:
        errors.append("Animal_Type is required.")
    if not sex:
        errors.append("Sex is required.")
    if not purpose:
        errors.append("Purpose is required.")
    if not source:
        errors.append("Source is required.")

    parsed_dob = parse_sheet_date(date_of_birth) if date_of_birth not in (None, "") else None

    parsed_acquisition_date = None
    acquisition_date = payload.get("acquisition_date", "")
    if acquisition_date not in (None, ""):
        parsed_acquisition_date = parse_sheet_date(acquisition_date)
        if not parsed_acquisition_date:
            errors.append("Acquisition_Date must be valid if provided.")

    parsed_wean_date = None
    wean_date = payload.get("wean_date", "")
    if wean_date not in (None, ""):
        parsed_wean_date = parse_sheet_date(wean_date)
        if not parsed_wean_date:
            errors.append("Wean_Date must be valid if provided.")

    parsed_exit_date = None
    exit_date = payload.get("exit_date", "")
    if exit_date not in (None, ""):
        parsed_exit_date = parse_sheet_date(exit_date)
        if not parsed_exit_date:
            errors.append("Exit_Date must be valid if provided.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "tag_number": tag_number,
            "pig_name": str(payload.get("pig_name", "")).strip(),
            "status": status,
            "on_farm": on_farm,
            "animal_type": animal_type,
            "sex": sex,
            "date_of_birth": parsed_dob,
            "breed_type": str(payload.get("breed_type", "")).strip(),
            "colour_markings": str(payload.get("colour_markings", "")).strip(),
            "litter_id": str(payload.get("litter_id", "")).strip(),
            "litter_size_born": to_float(payload.get("litter_size_born", "")),
            "litter_size_weaned": to_float(payload.get("litter_size_weaned", "")),
            "mother_pig_id": str(payload.get("mother_pig_id", "")).strip(),
            "father_pig_id": str(payload.get("father_pig_id", "")).strip(),
            "maternal_line": str(payload.get("maternal_line", "")).strip(),
            "paternal_line": str(payload.get("paternal_line", "")).strip(),
            "purpose": purpose,
            "current_pen_id": str(payload.get("current_pen_id", "")).strip(),
            "source": source,
            "acquisition_date": parsed_acquisition_date,
            "birth_weight_kg": to_float(payload.get("birth_weight_kg", "")),
            "wean_date": parsed_wean_date,
            "wean_weight_kg": to_float(payload.get("wean_weight_kg", "")),
            "exit_date": parsed_exit_date,
            "exit_reason": str(payload.get("exit_reason", "")).strip(),
            "exit_order_id": str(payload.get("exit_order_id", "")).strip(),
            "carcass_weight_kg": to_float(payload.get("carcass_weight_kg", "")),
            "general_notes": str(payload.get("general_notes", "")).strip(),
        }
    }


def validate_new_product_payload(payload: dict):
    errors = []

    product_name = str(payload.get("product_name", "")).strip()
    product_category = str(payload.get("product_category", "")).strip()

    if not product_name:
        errors.append("Product_Name is required.")
    if not product_category:
        errors.append("Product_Category is required.")

    default_dose = to_float(payload.get("default_dose", ""))
    default_withdrawal_days = to_float(payload.get("default_withdrawal_days", ""))

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "product_name": product_name,
            "product_category": product_category,
            "default_dose": default_dose,
            "dose_unit": str(payload.get("dose_unit", "")).strip(),
            "default_withdrawal_days": default_withdrawal_days,
            "supplier": str(payload.get("supplier", "")).strip(),
            "batch_tracking_required": str(payload.get("batch_tracking_required", "No")).strip() or "No",
            "is_active": str(payload.get("is_active", "Yes")).strip() or "Yes",
            "product_notes": str(payload.get("product_notes", "")).strip(),
        }
    }


def validate_new_pen_payload(payload: dict):
    errors = []

    pen_name = str(payload.get("pen_name", "")).strip()
    pen_type = str(payload.get("pen_type", "")).strip()

    if not pen_name:
        errors.append("Pen_Name is required.")
    if not pen_type:
        errors.append("Pen_Type is required.")

    capacity = to_float(payload.get("capacity", ""))

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "pen_name": pen_name,
            "pen_type": pen_type,
            "capacity": capacity,
            "is_active": str(payload.get("is_active", "Yes")).strip() or "Yes",
            "pen_notes": str(payload.get("pen_notes", "")).strip(),
        }
    }


def validate_new_litter_payload(payload: dict):
    errors = []

    mother_pig_id = str(payload.get("mother_pig_id", "")).strip()
    father_pig_id = str(payload.get("father_pig_id", "")).strip()
    current_pen_id = str(payload.get("current_pen_id", "")).strip()
    farrowing_date = payload.get("farrowing_date", "")

    if not mother_pig_id:
        errors.append("Mother_Pig_ID is required.")

    parsed_farrowing_date = parse_sheet_date(farrowing_date)
    if not parsed_farrowing_date:
        errors.append("Farrowing_Date is required and must be valid.")

    wean_date = payload.get("wean_date", "")
    parsed_wean_date = None
    if wean_date not in (None, ""):
        parsed_wean_date = parse_sheet_date(wean_date)
        if not parsed_wean_date:
            errors.append("Wean_Date must be a valid date if provided.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "mating_id": str(payload.get("mating_id", "")).strip(),
            "mother_pig_id": mother_pig_id,
            "father_pig_id": father_pig_id,
            "current_pen_id": current_pen_id,
            "farrowing_date": parsed_farrowing_date,
            "total_born": to_float(payload.get("total_born", "")),
            "born_alive": to_float(payload.get("born_alive", "")),
            "stillborn_count": to_float(payload.get("stillborn_count", "")),
            "mummified_count": to_float(payload.get("mummified_count", "")),
            "male_count": to_float(payload.get("male_count", "")),
            "female_count": to_float(payload.get("female_count", "")),
            "fostered_in_count": to_float(payload.get("fostered_in_count", "")),
            "fostered_out_count": to_float(payload.get("fostered_out_count", "")),
            "weaned_count": to_float(payload.get("weaned_count", "")),
            "wean_date": parsed_wean_date,
            "average_wean_weight_kg": to_float(payload.get("average_wean_weight_kg", "")),
            "notes": str(payload.get("notes", "")).strip(),
        }
    }