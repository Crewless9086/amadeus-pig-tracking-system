from services.google_sheets_service import get_all_records, append_row
from modules.pig_weights.pig_weights_config import PIG_WEIGHTS_CONFIG
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    to_float,
    parse_sheet_date,
    format_date_for_json,
    format_date_for_sheet,
    generate_weight_log_id,
    generate_medical_log_id,
    generate_move_log_id,
)


def get_active_pigs():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    active_pigs = []
    for row in rows:
        if (
            str(row.get(columns["status"], "")).strip() == "Active"
            and str(row.get(columns["on_farm"], "")).strip() == "Yes"
        ):
            active_pigs.append({
                "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
                "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
                "status": to_clean_string(row.get(columns["status"], "")),
                "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
                "current_weight_kg": row.get(columns["current_weight"], ""),
                "last_weight_date": format_date_for_json(row.get(columns["last_weight_date"], "")),
            })

    return active_pigs


def get_pig_detail(pig_id: str):
    pig_id = str(pig_id).strip()

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            return {
                "pig_id": row_pig_id,
                "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
                "status": to_clean_string(row.get(columns["status"], "")),
                "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
                "animal_type": to_clean_string(row.get("Animal_Type", "")),
                "sex": to_clean_string(row.get("Sex", "")),
                "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
                "age_days": row.get("Age_Days", ""),
                "litter_id": to_clean_string(row.get("Litter_ID", "")),
                "mother_pig_id": to_clean_string(row.get("Mother_Pig_ID", "")),
                "father_pig_id": to_clean_string(row.get("Father_Pig_ID", "")),
                "current_pen_id": to_clean_string(row.get("Current_Pen_ID", "")),
                "purpose": to_clean_string(row.get("Purpose", "")),
                "current_weight_kg": row.get("Current_Weight_Kg", ""),
                "last_weight_date": format_date_for_json(row.get("Last_Weight_Date", "")),
                "calculated_stage": to_clean_string(row.get("Calculated_Stage", "")),
                "weight_band": to_clean_string(row.get("Weight_Band", "")),
                "is_sale_ready": to_clean_string(row.get("Is_Sale_Ready", "")),
                "reserved_status": to_clean_string(row.get("Reserved_Status", "")),
                "general_notes": to_clean_string(row.get("General_Notes", "")),
                "last_treatment_date": format_date_for_json(row.get("Last_Treatment_Date", "")),
                "last_product_name": to_clean_string(row.get("Last_Product_Name", "")),
                "current_withdrawal_end_date": format_date_for_json(row.get("Current_Withdrawal_End_Date", "")),
                "withdrawal_clear": to_clean_string(row.get("Withdrawal_Clear", "")),
            }

    return None


def get_products():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["product_register"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    products = []
    for row in rows:
        if str(row.get(columns["is_active"], "")).strip() != "Yes":
            continue

        products.append({
            "product_id": to_clean_string(row.get(columns["product_id"], "")),
            "product_name": to_clean_string(row.get(columns["product_name"], "")),
            "product_category": to_clean_string(row.get(columns["product_category"], "")),
            "default_dose": to_float(row.get(columns["default_dose"], "")),
            "dose_unit": to_clean_string(row.get(columns["dose_unit"], "")),
            "default_withdrawal_days": to_float(row.get(columns["default_withdrawal_days"], "")),
            "supplier": to_clean_string(row.get(columns["supplier"], "")),
        })

    return sorted(products, key=lambda x: x["product_name"].lower())


def get_product_by_id(product_id: str):
    product_id = str(product_id).strip()
    products = get_products()

    for product in products:
        if product["product_id"] == product_id:
            return product

    return None


def get_pens():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    pens = []
    for row in rows:
        if str(row.get(columns["is_active"], "")).strip() != "Yes":
            continue

        pens.append({
            "pen_id": to_clean_string(row.get(columns["pen_id"], "")),
            "pen_name": to_clean_string(row.get(columns["pen_name"], "")),
            "pen_type": to_clean_string(row.get(columns["pen_type"], "")),
            "capacity": to_float(row.get(columns["capacity"], "")),
            "pen_notes": to_clean_string(row.get(columns["pen_notes"], "")),
        })

    return sorted(pens, key=lambda x: x["pen_name"].lower())


def get_pen_by_id(pen_id: str):
    pen_id = str(pen_id).strip()
    pens = get_pens()

    for pen in pens:
        if pen["pen_id"] == pen_id:
            return pen

    return None


def get_treatment_history_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    medical_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    tag_number = ""
    overview_rows = get_all_records(overview_sheet)
    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            tag_number = to_clean_string(row.get(columns["tag_number"], ""))
            break

    treatment_rows = get_all_records(medical_log_sheet)

    history = []
    for row in treatment_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id != pig_id:
            continue

        treatment_date = parse_sheet_date(row.get(columns["treatment_date"], ""))
        history.append({
            "medical_log_id": to_clean_string(row.get(columns["medical_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "treatment_date": treatment_date,
            "treatment_date_display": format_date_for_json(row.get(columns["treatment_date"], "")),
            "treatment_type": to_clean_string(row.get(columns["treatment_type"], "")),
            "product_id": to_clean_string(row.get(columns["product_id"], "")),
            "product_name": to_clean_string(row.get(columns["product_name"], "")),
            "dose": to_float(row.get(columns["dose"], "")),
            "dose_unit": to_clean_string(row.get(columns["dose_unit"], "")),
            "route": to_clean_string(row.get(columns["route"], "")),
            "reason_for_treatment": to_clean_string(row.get(columns["reason_for_treatment"], "")),
            "batch_lot_number": to_clean_string(row.get(columns["batch_lot_number"], "")),
            "withdrawal_days": to_float(row.get(columns["withdrawal_days"], "")),
            "withdrawal_end_date": format_date_for_json(row.get(columns["withdrawal_end_date"], "")),
            "given_by": to_clean_string(row.get(columns["given_by"], "")),
            "follow_up_required": to_clean_string(row.get(columns["follow_up_required"], "")),
            "follow_up_date": format_date_for_json(row.get(columns["follow_up_date"], "")),
            "medical_notes": to_clean_string(row.get(columns["medical_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: x["treatment_date"] if x["treatment_date"] else parse_sheet_date("1900-01-01"),
        reverse=True
    )

    for entry in history:
        entry.pop("treatment_date", None)

    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "count": len(history),
        "history": history,
    }


def get_movement_history_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    location_history_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["location_history"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    tag_number = ""
    current_pen_id = ""

    overview_rows = get_all_records(overview_sheet)
    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            tag_number = to_clean_string(row.get(columns["tag_number"], ""))
            current_pen_id = to_clean_string(row.get("Current_Pen_ID", ""))
            break

    movement_rows = get_all_records(location_history_sheet)
    history = []

    for row in movement_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id != pig_id:
            continue

        move_date = parse_sheet_date(row.get(columns["move_date"], ""))
        from_pen_id = to_clean_string(row.get(columns["from_pen_id"], ""))
        to_pen_id = to_clean_string(row.get(columns["to_pen_id"], ""))

        from_pen = get_pen_by_id(from_pen_id)
        to_pen = get_pen_by_id(to_pen_id)

        history.append({
            "move_log_id": to_clean_string(row.get(columns["move_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "move_date": move_date,
            "move_date_display": format_date_for_json(row.get(columns["move_date"], "")),
            "from_pen_id": from_pen_id,
            "to_pen_id": to_pen_id,
            "from_pen_name": from_pen["pen_name"] if from_pen else from_pen_id,
            "to_pen_name": to_pen["pen_name"] if to_pen else to_pen_id,
            "reason_for_move": to_clean_string(row.get(columns["reason_for_move"], "")),
            "moved_by": to_clean_string(row.get(columns["moved_by"], "")),
            "move_notes": to_clean_string(row.get(columns["move_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: x["move_date"] if x["move_date"] else parse_sheet_date("1900-01-01"),
        reverse=True
    )

    for entry in history:
        entry.pop("move_date", None)

    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "current_pen_id": current_pen_id,
        "count": len(history),
        "history": history,
    }


def get_weight_history_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    weight_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    tag_number = ""
    overview_rows = get_all_records(overview_sheet)
    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            tag_number = to_clean_string(row.get(columns["tag_number"], ""))
            break

    weight_rows = get_all_records(weight_log_sheet)

    history = []
    for row in weight_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id != pig_id:
            continue

        weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
        weight_kg = to_float(row.get(columns["weight_kg"], ""))

        history.append({
            "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "weight_date": weight_date,
            "weight_date_display": format_date_for_json(row.get(columns["weight_date"], "")),
            "weight_kg": weight_kg,
            "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
            "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: x["weight_date"] if x["weight_date"] else parse_sheet_date("1900-01-01"),
        reverse=True
    )

    for index, entry in enumerate(history):
        previous_entry = history[index + 1] if index + 1 < len(history) else None

        if previous_entry and entry["weight_kg"] is not None and previous_entry["weight_kg"] is not None:
            entry["difference_kg"] = round(entry["weight_kg"] - previous_entry["weight_kg"], 2)
        else:
            entry["difference_kg"] = None

        if previous_entry and entry["weight_date"] and previous_entry["weight_date"]:
            entry["days_since_previous"] = (entry["weight_date"] - previous_entry["weight_date"]).days
        else:
            entry["days_since_previous"] = None

        if (
            entry["difference_kg"] is not None
            and entry["days_since_previous"] is not None
            and entry["days_since_previous"] > 0
        ):
            entry["growth_rate_kg_day"] = round(entry["difference_kg"] / entry["days_since_previous"], 3)
        else:
            entry["growth_rate_kg_day"] = None

        entry.pop("weight_date", None)

    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "count": len(history),
        "history": history,
    }


def get_latest_weight_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    weight_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    overview_rows = get_all_records(overview_sheet)

    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            return {
                "pig_id": pig_id,
                "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
                "previous_weight_kg": to_float(row.get(columns["current_weight"], "")),
                "previous_weight_date": format_date_for_json(row.get(columns["last_weight_date"], "")),
            }

    weight_rows = get_all_records(weight_log_sheet)

    matching_rows = []
    for row in weight_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
            weight_kg = to_float(row.get(columns["weight_kg"], ""))
            if weight_date and weight_kg is not None:
                matching_rows.append({
                    "pig_id": pig_id,
                    "tag_number": "",
                    "previous_weight_kg": weight_kg,
                    "previous_weight_date": weight_date,
                })

    if not matching_rows:
        return {
            "pig_id": pig_id,
            "tag_number": "",
            "previous_weight_kg": None,
            "previous_weight_date": "",
        }

    latest_row = sorted(
        matching_rows,
        key=lambda x: x["previous_weight_date"],
        reverse=True
    )[0]

    return {
        "pig_id": latest_row["pig_id"],
        "tag_number": latest_row["tag_number"],
        "previous_weight_kg": latest_row["previous_weight_kg"],
        "previous_weight_date": latest_row["previous_weight_date"].isoformat(),
    }


def save_weight_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]

    row_values = [
        generate_weight_log_id(),
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["weight_date"]),
        cleaned_data["weight_kg"],
        cleaned_data["weighed_by"],
        "",
        cleaned_data["condition_notes"],
        "",
        format_date_for_sheet(cleaned_data["weight_date"]),
    ]

    append_row(sheet_name, row_values)

    latest_info = get_latest_weight_for_pig(cleaned_data["pig_id"])

    return {
        "success": True,
        "message": "Weight entry saved successfully.",
        "saved": {
            "pig_id": cleaned_data["pig_id"],
            "weight_date": format_date_for_json(cleaned_data["weight_date"]),
            "weight_kg": cleaned_data["weight_kg"],
            "condition_notes": cleaned_data["condition_notes"],
            "weighed_by": cleaned_data["weighed_by"],
        },
        "latest": latest_info
    }


def save_treatment_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"]
    product = get_product_by_id(cleaned_data["product_id"])

    product_name = product["product_name"] if product else ""
    default_dose_unit = product["dose_unit"] if product else ""
    withdrawal_days = product["default_withdrawal_days"] if product else None

    dose_unit = cleaned_data["dose_unit"] or default_dose_unit
    withdrawal_days_int = int(withdrawal_days) if withdrawal_days not in (None, "") else ""
    withdrawal_end_date = ""

    if cleaned_data["treatment_date"] and withdrawal_days_int != "":
        withdrawal_end_date = cleaned_data["treatment_date"].fromordinal(
            cleaned_data["treatment_date"].toordinal() + withdrawal_days_int
        )

    row_values = [
        generate_medical_log_id(),
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["treatment_date"]),
        cleaned_data["treatment_type"],
        cleaned_data["product_id"],
        product_name,
        cleaned_data["dose"] if cleaned_data["dose"] is not None else "",
        dose_unit,
        cleaned_data["route"],
        cleaned_data["reason_for_treatment"],
        cleaned_data["batch_lot_number"],
        withdrawal_days_int,
        format_date_for_sheet(withdrawal_end_date),
        cleaned_data["given_by"],
        cleaned_data["follow_up_required"],
        format_date_for_sheet(cleaned_data["follow_up_date"]),
        cleaned_data["medical_notes"],
        format_date_for_sheet(cleaned_data["treatment_date"]),
    ]

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Treatment entry saved successfully.",
        "saved": {
            "pig_id": cleaned_data["pig_id"],
            "treatment_date": format_date_for_json(cleaned_data["treatment_date"]),
            "treatment_type": cleaned_data["treatment_type"],
            "product_id": cleaned_data["product_id"],
            "product_name": product_name,
            "dose": cleaned_data["dose"],
            "dose_unit": dose_unit,
            "route": cleaned_data["route"],
            "reason_for_treatment": cleaned_data["reason_for_treatment"],
            "withdrawal_days": withdrawal_days_int,
            "withdrawal_end_date": format_date_for_json(withdrawal_end_date),
            "given_by": cleaned_data["given_by"],
            "follow_up_required": cleaned_data["follow_up_required"],
            "follow_up_date": format_date_for_json(cleaned_data["follow_up_date"]),
            "medical_notes": cleaned_data["medical_notes"],
        }
    }


def save_movement_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["location_history"]

    row_values = [
        generate_move_log_id(),                                   # Move_Log_ID
        cleaned_data["pig_id"],                                   # Pig_ID
        format_date_for_sheet(cleaned_data["move_date"]),         # Move_Date
        cleaned_data["from_pen_id"],                              # From_Pen_ID
        cleaned_data["to_pen_id"],                                # To_Pen_ID
        cleaned_data["reason_for_move"],                          # Reason_For_Move
        cleaned_data["moved_by"],                                 # Moved_By
        "",                                                       # Group_Batch_ID
        cleaned_data["move_notes"],                               # Move_Notes
        format_date_for_sheet(cleaned_data["move_date"]),         # Created_At
    ]

    append_row(sheet_name, row_values)

    from_pen = get_pen_by_id(cleaned_data["from_pen_id"])
    to_pen = get_pen_by_id(cleaned_data["to_pen_id"])

    return {
        "success": True,
        "message": "Movement entry saved successfully.",
        "saved": {
            "pig_id": cleaned_data["pig_id"],
            "move_date": format_date_for_json(cleaned_data["move_date"]),
            "from_pen_id": cleaned_data["from_pen_id"],
            "from_pen_name": from_pen["pen_name"] if from_pen else cleaned_data["from_pen_id"],
            "to_pen_id": cleaned_data["to_pen_id"],
            "to_pen_name": to_pen["pen_name"] if to_pen else cleaned_data["to_pen_id"],
            "reason_for_move": cleaned_data["reason_for_move"],
            "moved_by": cleaned_data["moved_by"],
            "move_notes": cleaned_data["move_notes"],
        }
    }