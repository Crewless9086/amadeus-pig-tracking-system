from services.google_sheets_service import get_all_records, append_row
from modules.pig_weights.pig_weights_config import PIG_WEIGHTS_CONFIG
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    to_float,
    parse_sheet_date,
    format_date_for_json,
    format_date_for_sheet,
    generate_weight_log_id,
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
            }

    return None


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