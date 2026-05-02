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
    generate_move_log_id,
)

PIG_OVERVIEW_SHEET = "PIG_OVERVIEW"
MATING_LOG_SHEET = "MATING_LOG"
MATING_OVERVIEW_SHEET = "MATING_OVERVIEW"
PEN_REGISTER_SHEET = "PEN_REGISTER"
LOCATION_HISTORY_SHEET = "LOCATION_HISTORY"


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


def _get_pen_lookup():
    rows = get_all_records(PEN_REGISTER_SHEET)
    lookup = {}

    for row in rows:
        pen_id = to_clean_string(row.get("Pen_ID", ""))
        if not pen_id:
            continue

        lookup[pen_id] = {
            "pen_id": pen_id,
            "pen_name": to_clean_string(row.get("Pen_Name", "")),
        }

    return lookup


def _pen_context(pig_id, pig_lookup, pen_lookup):
    pig = pig_lookup.get(to_clean_string(pig_id), {})
    pen_id = to_clean_string(pig.get("Current_Pen_ID", ""))
    pen = pen_lookup.get(pen_id, {})

    return {
        "current_pen_id": pen_id,
        "current_pen_name": to_clean_string(pen.get("pen_name", "")),
    }


def _write_movement_if_needed(pig_id: str, current_pen_id: str, target_pen_id: str, move_date, reason: str) -> bool:
    target_pen_id = to_clean_string(target_pen_id)
    current_pen_id = to_clean_string(current_pen_id)

    if not target_pen_id or target_pen_id == current_pen_id:
        return False

    row_values = [
        generate_move_log_id(),
        pig_id,
        format_date_for_sheet(move_date),
        current_pen_id,
        target_pen_id,
        reason,
        "Mating Form",
        "",
        "",
        format_date_for_sheet(move_date),
    ]
    append_row(LOCATION_HISTORY_SHEET, row_values)
    return True


def get_breeding_options():
    rows = get_all_records(PIG_OVERVIEW_SHEET)
    pen_lookup = _get_pen_lookup()

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

        pen_id = to_clean_string(row.get("Current_Pen_ID", ""))
        pen = pen_lookup.get(pen_id, {})

        item = {
            "pig_id": pig_id,
            "tag_number": tag_number or pig_id,
            "current_pen_id": pen_id,
            "current_pen_name": to_clean_string(pen.get("pen_name", "")),
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
    pig_lookup = _get_pig_lookup()
    pen_lookup = _get_pen_lookup()

    records = []
    for row in rows:
        mating_id = to_clean_string(row.get("Mating_ID", ""))
        if not mating_id:
            continue

        sow_pig_id = to_clean_string(row.get("Sow_Pig_ID", ""))
        boar_pig_id = to_clean_string(row.get("Boar_Pig_ID", ""))
        sow_pen = _pen_context(sow_pig_id, pig_lookup, pen_lookup)
        boar_pen = _pen_context(boar_pig_id, pig_lookup, pen_lookup)

        record = {
            "mating_id": mating_id,
            "sow_pig_id": sow_pig_id,
            "sow_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
            "sow_current_pen_id": sow_pen["current_pen_id"],
            "sow_current_pen_name": sow_pen["current_pen_name"],
            "boar_pig_id": boar_pig_id,
            "boar_tag_number": to_clean_string(row.get("Boar_Tag_Number", "")),
            "boar_current_pen_id": boar_pen["current_pen_id"],
            "boar_current_pen_name": boar_pen["current_pen_name"],
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
    mating_date = cleaned_data["mating_date"]

    row_values = [
        generate_mating_id(),                                 # Mating_ID
        cleaned_data["sow_pig_id"],                          # Sow_Pig_ID
        sow_tag_number,                                      # Sow_Tag_Number
        cleaned_data["boar_pig_id"],                         # Boar_Pig_ID
        boar_tag_number,                                     # Boar_Tag_Number
        format_date_for_sheet(mating_date),                  # Mating_Date
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

    sow_moved = False
    boar_moved = False

    sow_move_to = to_clean_string(cleaned_data.get("sow_move_to_pen_id", ""))
    if sow_move_to and cleaned_data["sow_pig_id"]:
        sow_current_pen = to_clean_string(sow_row.get("Current_Pen_ID", ""))
        sow_moved = _write_movement_if_needed(
            pig_id=cleaned_data["sow_pig_id"],
            current_pen_id=sow_current_pen,
            target_pen_id=sow_move_to,
            move_date=mating_date,
            reason="Moved during mating log",
        )

    boar_move_to = to_clean_string(cleaned_data.get("boar_move_to_pen_id", ""))
    if boar_move_to and cleaned_data["boar_pig_id"]:
        boar_current_pen = to_clean_string(boar_row.get("Current_Pen_ID", ""))
        boar_moved = _write_movement_if_needed(
            pig_id=cleaned_data["boar_pig_id"],
            current_pen_id=boar_current_pen,
            target_pen_id=boar_move_to,
            move_date=mating_date,
            reason="Moved during mating log",
        )

    message = "Mating record saved successfully."
    if sow_moved and boar_moved:
        message += " Sow and boar movements logged."
    elif sow_moved:
        message += " Sow movement logged."
    elif boar_moved:
        message += " Boar movement logged."

    return {
        "success": True,
        "message": message,
        "sow_moved": sow_moved,
        "boar_moved": boar_moved,
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


_ASSUME_PREGNANT_BLOCKED = {"Farrowed", "Cancelled", "Closed"}


def assume_pregnant(mating_id: str, target_pen_id: str, moved_by: str):
    mating_id = str(mating_id).strip()
    target_pen_id = to_clean_string(target_pen_id)
    moved_by = to_clean_string(moved_by) or "WebApp"

    all_values = get_all_values(MATING_LOG_SHEET)
    if not all_values or len(all_values) < 2:
        raise ValueError("MATING_LOG has no data rows.")

    headers = all_values[0]
    header_index = {h: i for i, h in enumerate(headers)}

    required_headers = [
        "Mating_ID", "Sow_Pig_ID",
        "Pregnancy_Check_Date", "Pregnancy_Check_Result",
        "Mating_Status", "Outcome", "Updated_At",
    ]
    for h in required_headers:
        if h not in header_index:
            raise ValueError(f"Missing column '{h}' in MATING_LOG.")

    today_str = datetime.now().strftime("%d %b %Y")

    for row in all_values[1:]:
        if not row:
            continue

        row_id = to_clean_string(row[0])
        if row_id != mating_id:
            continue

        padded_row = list(row) + [""] * (len(headers) - len(row))
        current_status = to_clean_string(padded_row[header_index["Mating_Status"]])

        if current_status in _ASSUME_PREGNANT_BLOCKED:
            raise ValueError(f"Cannot update mating: status is already {current_status}.")

        padded_row[header_index["Pregnancy_Check_Date"]] = today_str
        padded_row[header_index["Pregnancy_Check_Result"]] = "Pregnant"
        padded_row[header_index["Mating_Status"]] = "Confirmed_Pregnant"
        padded_row[header_index["Outcome"]] = "Pregnant"
        padded_row[header_index["Updated_At"]] = today_str

        update_row_by_first_column_match(MATING_LOG_SHEET, mating_id, padded_row)

        movement_logged = False
        if target_pen_id:
            sow_pig_id = to_clean_string(padded_row[header_index["Sow_Pig_ID"]])
            if sow_pig_id:
                pig_lookup = _get_pig_lookup()
                sow_row = pig_lookup.get(sow_pig_id, {})
                current_pen_id = to_clean_string(sow_row.get("Current_Pen_ID", ""))
                movement_logged = _write_movement_if_needed(
                    pig_id=sow_pig_id,
                    current_pen_id=current_pen_id,
                    target_pen_id=target_pen_id,
                    move_date=datetime.now().date(),
                    reason="Moved to farrowing pen",
                )

        message = "Mating updated to Confirmed_Pregnant."
        if movement_logged:
            message += " Sow movement logged."

        return {
            "success": True,
            "message": message,
            "mating_id": mating_id,
            "movement_logged": movement_logged,
        }

    raise ValueError(f"Mating_ID '{mating_id}' not found in MATING_LOG.")