from datetime import datetime
import uuid

from services.google_sheets_service import (
    get_all_records,
    append_row,
    get_all_values,
    update_row_by_first_column_match,
)
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    format_date_for_json,
    format_date_for_sheet,
    parse_sheet_date,
)

PIG_OVERVIEW_SHEET = "PIG_OVERVIEW"
MATING_LOG_SHEET = "MATING_LOG"
MATING_OVERVIEW_SHEET = "MATING_OVERVIEW"


def generate_mating_id():
    return f"MAT-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def _get_pig_lookup():
    rows = get_all_records(PIG_OVERVIEW_SHEET)
    lookup = {}

    for row in rows:
        pig_id = to_clean_string(row.get("Pig_ID", ""))
        if pig_id:
            lookup[pig_id] = row

    return lookup


def get_breeding_options():
    rows = get_all_records(PIG_OVERVIEW_SHEET)

    sows = []
    boars = []

    for row in rows:
        pig_id = to_clean_string(row.get("Pig_ID", ""))
        tag_number = to_clean_string(row.get("Tag_Number", ""))
        sex = to_clean_string(row.get("Sex", ""))
        status = to_clean_string(row.get("Status", ""))
        on_farm = to_clean_string(row.get("On_Farm", ""))
        purpose = to_clean_string(row.get("Purpose", ""))

        if not pig_id:
            continue

        if status != "Active" or on_farm != "Yes" or purpose != "Breeding":
            continue

        item = {
            "pig_id": pig_id,
            "tag_number": tag_number or pig_id,
        }

        if sex == "Female":
            sows.append(item)

        if sex in ("Male", "Castrated_Male"):
            boars.append(item)

    sows = sorted(sows, key=lambda x: x["tag_number"].lower())
    boars = sorted(boars, key=lambda x: x["tag_number"].lower())

    return {
        "sows": sows,
        "boars": boars,
    }


def get_mating_overview():
    rows = get_all_records(MATING_OVERVIEW_SHEET)

    records = []
    for row in rows:
        mating_id = to_clean_string(row.get("Mating_ID", ""))
        if not mating_id:
            continue

        record = {
            "mating_id": mating_id,
            "sow_pig_id": to_clean_string(row.get("Sow_Pig_ID", "")),
            "sow_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
            "boar_pig_id": to_clean_string(row.get("Boar_Pig_ID", "")),
            "boar_tag_number": to_clean_string(row.get("Boar_Tag_Number", "")),
            "mating_date": format_date_for_json(row.get("Mating_Date", "")),
            "mating_method": to_clean_string(row.get("Mating_Method", "")),
            "exposure_group": to_clean_string(row.get("Exposure_Group", "")),
            "expected_pregnancy_check_date": format_date_for_json(row.get("Expected_Pregnancy_Check_Date", "")),
            "pregnancy_check_date": format_date_for_json(row.get("Pregnancy_Check_Date", "")),
            "pregnancy_check_result": to_clean_string(row.get("Pregnancy_Check_Result", "")),
            "expected_farrowing_date": format_date_for_json(row.get("Expected_Farrowing_Date", "")),
            "actual_farrowing_date": format_date_for_json(row.get("Actual_Farrowing_Date", "")),
            "mating_status": to_clean_string(row.get("Mating_Status", "")),
            "outcome": to_clean_string(row.get("Outcome", "")),
            "linked_litter_id": to_clean_string(row.get("Linked_Litter_ID", "")),
            "days_since_mating": to_clean_string(row.get("Days_Since_Mating", "")),
            "is_open": to_clean_string(row.get("Is_Open", "")),
            "is_overdue_check": to_clean_string(row.get("Is_Overdue_Check", "")),
            "is_overdue_farrowing": to_clean_string(row.get("Is_Overdue_Farrowing", "")),
            "service_notes": to_clean_string(row.get("Service_Notes", "")),
            "created_at": format_date_for_json(row.get("Created_At", "")),
            "updated_at": format_date_for_json(row.get("Updated_At", "")),
        }

        records.append(record)

    def sort_key(item):
        parsed = parse_sheet_date(item["mating_date"])
        return parsed or parse_sheet_date("1900-01-01")

    records = sorted(records, key=sort_key, reverse=True)

    return records


def save_new_mating(cleaned_data: dict):
    pig_lookup = _get_pig_lookup()

    sow_row = pig_lookup.get(cleaned_data["sow_pig_id"], {})
    boar_row = pig_lookup.get(cleaned_data["boar_pig_id"], {}) if cleaned_data["boar_pig_id"] else {}

    sow_tag_number = to_clean_string(sow_row.get("Tag_Number", ""))
    boar_tag_number = to_clean_string(boar_row.get("Tag_Number", ""))

    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_mating_id(),                                 # Mating_ID
        cleaned_data["sow_pig_id"],                          # Sow_Pig_ID
        sow_tag_number,                                      # Sow_Tag_Number
        cleaned_data["boar_pig_id"],                         # Boar_Pig_ID
        boar_tag_number,                                     # Boar_Tag_Number
        format_date_for_sheet(cleaned_data["mating_date"]),  # Mating_Date
        cleaned_data["mating_method"],                       # Mating_Method
        cleaned_data["exposure_group"],                      # Exposure_Group
        "",                                                  # Expected_Pregnancy_Check_Date
        "",                                                  # Pregnancy_Check_Date
        "Pending",                                           # Pregnancy_Check_Result
        "",                                                  # Expected_Farrowing_Date
        "",                                                  # Actual_Farrowing_Date
        "Open",                                              # Mating_Status
        "Pending",                                           # Outcome
        "",                                                  # Linked_Litter_ID
        "",                                                  # Days_Since_Mating
        cleaned_data["service_notes"],                       # Service_Notes
        today_str,                                           # Created_At
        today_str,                                           # Updated_At
    ]

    append_row(MATING_LOG_SHEET, row_values)

    return {
        "success": True,
        "message": "Mating record saved successfully."
    }


def link_litter_to_mating(mating_id: str, litter_id: str, actual_farrowing_date):
    mating_id = str(mating_id).strip()
    litter_id = str(litter_id).strip()

    if not mating_id or not litter_id:
        return

    all_values = get_all_values(MATING_LOG_SHEET)
    if not all_values or len(all_values) < 2:
        raise ValueError("MATING_LOG has no data rows.")

    headers = all_values[0]

    header_index = {header: idx for idx, header in enumerate(headers)}

    required_headers = [
        "Mating_ID",
        "Linked_Litter_ID",
        "Actual_Farrowing_Date",
        "Mating_Status",
        "Outcome",
        "Updated_At",
    ]

    for header in required_headers:
        if header not in header_index:
            raise ValueError(f"Missing required column '{header}' in MATING_LOG.")

    for row in all_values[1:]:
        if not row:
            continue

        row_id = str(row[0]).strip()
        if row_id != mating_id:
            continue

        padded_row = row + [""] * (len(headers) - len(row))

        padded_row[header_index["Linked_Litter_ID"]] = litter_id
        padded_row[header_index["Actual_Farrowing_Date"]] = format_date_for_sheet(actual_farrowing_date)
        padded_row[header_index["Mating_Status"]] = "Farrowed"
        padded_row[header_index["Outcome"]] = "Farrowed"
        padded_row[header_index["Updated_At"]] = datetime.now().strftime("%d %b %Y")

        update_row_by_first_column_match(MATING_LOG_SHEET, mating_id, padded_row)
        return

    raise ValueError(f"Mating_ID '{mating_id}' not found in MATING_LOG.")