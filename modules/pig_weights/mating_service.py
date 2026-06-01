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
    to_float,
    format_date_for_json,
    format_date_for_sheet,
    parse_sheet_date,
    generate_move_log_id,
)

PIG_OVERVIEW_SHEET = "PIG_OVERVIEW"
MATING_LOG_SHEET = "MATING_LOG"
MATING_OVERVIEW_SHEET = "MATING_OVERVIEW"
LITTER_OVERVIEW_SHEET = "LITTER_OVERVIEW"
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
            "pen_type": to_clean_string(row.get("Pen_Type", "")),
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


def _write_movement_if_needed(pig_id: str, current_pen_id: str, target_pen_id: str, move_date, reason: str, moved_by: str = "Mating Form") -> bool:
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
        moved_by,
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


def _blank_breeding_metric(pig_id, tag_number):
    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "mating_count": 0,
        "confirmed_pregnant_count": 0,
        "repeat_service_count": 0,
        "farrowed_count": 0,
        "open_count": 0,
        "litter_count": 0,
        "born_alive_total": 0,
        "weaned_total": 0,
        "average_born_alive": None,
        "average_weaned": None,
        "survival_pct": None,
    }


def _metric_for(metrics, pig_id, tag_number):
    if not pig_id:
        return None
    if pig_id not in metrics:
        metrics[pig_id] = _blank_breeding_metric(pig_id, tag_number)
    if tag_number and not metrics[pig_id]["tag_number"]:
        metrics[pig_id]["tag_number"] = tag_number
    return metrics[pig_id]


def _finish_breeding_metrics(metrics):
    rows = []
    for metric in metrics.values():
        litter_count = metric["litter_count"]
        born_alive_total = metric["born_alive_total"]
        weaned_total = metric["weaned_total"]

        if litter_count:
            metric["average_born_alive"] = round(born_alive_total / litter_count, 2)
            metric["average_weaned"] = round(weaned_total / litter_count, 2)
        if born_alive_total:
            metric["survival_pct"] = round((weaned_total / born_alive_total) * 100, 1)

        rows.append(metric)

    return sorted(
        rows,
        key=lambda item: (
            -item["litter_count"],
            -item["farrowed_count"],
            str(item["tag_number"] or item["pig_id"]).lower(),
        ),
    )


def get_breeding_analytics():
    mating_rows = get_mating_overview()
    litter_rows = get_all_records(LITTER_OVERVIEW_SHEET)

    sow_metrics = {}
    boar_metrics = {}

    for row in mating_rows:
        sow_metric = _metric_for(sow_metrics, row.get("sow_pig_id", ""), row.get("sow_tag_number", ""))
        boar_metric = _metric_for(boar_metrics, row.get("boar_pig_id", ""), row.get("boar_tag_number", ""))
        metric_targets = [metric for metric in (sow_metric, boar_metric) if metric]

        pregnancy_result = to_clean_string(row.get("pregnancy_check_result", "")).lower()
        mating_status = to_clean_string(row.get("mating_status", "")).lower()
        outcome = to_clean_string(row.get("outcome", "")).lower()
        linked_litter_id = to_clean_string(row.get("linked_litter_id", ""))

        confirmed = (
            pregnancy_result == "pregnant"
            or mating_status in {"confirmed_pregnant", "farrowed"}
            or outcome in {"pregnant", "farrowed"}
        )
        repeat_service = (
            pregnancy_result == "not_pregnant"
            or mating_status == "repeat_service"
            or outcome == "repeat_required"
        )
        farrowed = bool(linked_litter_id) or mating_status == "farrowed" or outcome == "farrowed"
        is_open = to_clean_string(row.get("is_open", "")) == "Yes"

        for metric in metric_targets:
            metric["mating_count"] += 1
            if confirmed:
                metric["confirmed_pregnant_count"] += 1
            if repeat_service:
                metric["repeat_service_count"] += 1
            if farrowed:
                metric["farrowed_count"] += 1
            if is_open:
                metric["open_count"] += 1

    for row in litter_rows:
        sow_metric = _metric_for(
            sow_metrics,
            to_clean_string(row.get("Sow_Pig_ID", "")),
            to_clean_string(row.get("Sow_Tag_Number", "")),
        )
        boar_metric = _metric_for(
            boar_metrics,
            to_clean_string(row.get("Boar_Pig_ID", "")),
            to_clean_string(row.get("Boar_Tag_Number", "")),
        )
        born_alive = to_float(row.get("Born_Alive", "")) or 0
        weaned_count = to_float(row.get("Weaned_Count", "")) or 0

        for metric in [metric for metric in (sow_metric, boar_metric) if metric]:
            metric["litter_count"] += 1
            metric["born_alive_total"] += born_alive
            metric["weaned_total"] += weaned_count

    sows = _finish_breeding_metrics(sow_metrics)
    boars = _finish_breeding_metrics(boar_metrics)

    return {
        "success": True,
        "mode": "read_only",
        "summary": {
            "sow_count": len(sows),
            "boar_count": len(boars),
            "mating_count": len(mating_rows),
            "litter_count": len(litter_rows),
        },
        "sows": sows,
        "boars": boars,
        "source": {
            "mating_source": MATING_OVERVIEW_SHEET,
            "litter_source": LITTER_OVERVIEW_SHEET,
            "writes_to_google_sheets": False,
            "writes_to_supabase": False,
        },
    }


def _animal_role_for_litter(row, pig_id):
    if to_clean_string(row.get("Sow_Pig_ID", "")) == pig_id:
        return "sow"
    if to_clean_string(row.get("Boar_Pig_ID", "")) == pig_id:
        return "boar"
    return ""


def _animal_role_for_mating(row, pig_id):
    if to_clean_string(row.get("sow_pig_id", "")) == pig_id:
        return "sow"
    if to_clean_string(row.get("boar_pig_id", "")) == pig_id:
        return "boar"
    return ""


def _litter_quality_flags(row):
    flags = []
    born_alive_raw = to_clean_string(row.get("Born_Alive", ""))
    weaned_raw = to_clean_string(row.get("Weaned_Count", ""))
    pig_master_count = to_float(row.get("Pig_Master_Row_Count", ""))
    born_alive = to_float(row.get("Born_Alive", ""))

    if not born_alive_raw:
        flags.append("Missing born alive")
    if not weaned_raw:
        flags.append("Missing weaned count")
    if born_alive is not None and pig_master_count is not None and pig_master_count != born_alive:
        flags.append("Pig records do not match born alive")
    if to_clean_string(row.get("Needs_Attention", "")) == "Yes":
        reason = to_clean_string(row.get("Attention_Reason", "")) or "Needs attention"
        flags.append(reason)

    return flags


def _mating_quality_flags(row):
    flags = []
    is_open = to_clean_string(row.get("is_open", ""))
    linked_litter_id = to_clean_string(row.get("linked_litter_id", ""))
    mating_status = to_clean_string(row.get("mating_status", ""))
    pregnancy_result = to_clean_string(row.get("pregnancy_check_result", "")).lower().replace(" ", "_")

    if is_open == "Yes" and to_clean_string(row.get("is_overdue_check", "")) == "Yes":
        flags.append("Pregnancy check overdue")
    if is_open == "Yes" and to_clean_string(row.get("is_overdue_farrowing", "")) == "Yes":
        flags.append("Farrowing overdue")
    if mating_status == "Farrowed" and not linked_litter_id:
        flags.append("Farrowed without linked litter")
    if is_open == "No" and not linked_litter_id and pregnancy_result != "not_pregnant":
        flags.append("Closed without clear litter or repeat-service outcome")

    return flags


def get_breeding_animal_detail(pig_id: str):
    pig_id = to_clean_string(pig_id)
    if not pig_id:
        return {
            "success": False,
            "errors": ["Pig ID is required."],
        }, 400

    analytics = get_breeding_analytics()
    animal = None
    animal_type = ""

    for row in analytics["sows"]:
        if row["pig_id"] == pig_id:
            animal = row
            animal_type = "sow"
            break
    if not animal:
        for row in analytics["boars"]:
            if row["pig_id"] == pig_id:
                animal = row
                animal_type = "boar"
                break

    if not animal:
        return {
            "success": False,
            "errors": [f"Breeding analytics not found for pig '{pig_id}'."],
        }, 404

    mating_rows = []
    for row in get_mating_overview():
        role = _animal_role_for_mating(row, pig_id)
        if not role:
            continue

        mating_rows.append({
            "role": role,
            "mating_id": row.get("mating_id", ""),
            "mating_date": row.get("mating_date", ""),
            "sow_pig_id": row.get("sow_pig_id", ""),
            "sow_tag_number": row.get("sow_tag_number", ""),
            "boar_pig_id": row.get("boar_pig_id", ""),
            "boar_tag_number": row.get("boar_tag_number", ""),
            "pregnancy_check_result": row.get("pregnancy_check_result", ""),
            "mating_status": row.get("mating_status", ""),
            "outcome": row.get("outcome", ""),
            "linked_litter_id": row.get("linked_litter_id", ""),
            "expected_farrowing_date": row.get("expected_farrowing_date", ""),
            "actual_farrowing_date": row.get("actual_farrowing_date", ""),
            "is_open": row.get("is_open", ""),
            "quality_flags": _mating_quality_flags(row),
        })

    litter_rows = []
    for row in get_all_records(LITTER_OVERVIEW_SHEET):
        role = _animal_role_for_litter(row, pig_id)
        if not role:
            continue

        born_alive = to_float(row.get("Born_Alive", ""))
        weaned_count = to_float(row.get("Weaned_Count", ""))
        survival_pct = None
        if born_alive:
            survival_pct = round(((weaned_count or 0) / born_alive) * 100, 1)

        litter_rows.append({
            "role": role,
            "litter_id": to_clean_string(row.get("Litter_ID", "")),
            "farrowing_date": format_date_for_json(row.get("Farrowing_Date", "")),
            "sow_pig_id": to_clean_string(row.get("Sow_Pig_ID", "")),
            "sow_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
            "boar_pig_id": to_clean_string(row.get("Boar_Pig_ID", "")),
            "boar_tag_number": to_clean_string(row.get("Boar_Tag_Number", "")),
            "born_alive": born_alive,
            "weaned_count": weaned_count,
            "active_pig_count": to_float(row.get("Active_Pig_Count", "")),
            "exited_pig_count": to_float(row.get("Exited_Pig_Count", "")),
            "average_current_weight_kg": to_float(row.get("Average_Current_Weight_Kg", "")),
            "survival_pct": survival_pct,
            "litter_status": to_clean_string(row.get("Litter_Status", "")),
            "needs_attention": to_clean_string(row.get("Needs_Attention", "")),
            "quality_flags": _litter_quality_flags(row),
        })

    data_quality_flags = []
    for row in mating_rows:
        data_quality_flags.extend(row["quality_flags"])
    for row in litter_rows:
        data_quality_flags.extend(row["quality_flags"])

    return {
        "success": True,
        "mode": "read_only",
        "animal_type": animal_type,
        "animal": animal,
        "matings": mating_rows,
        "litters": litter_rows,
        "data_quality": {
            "flag_count": len(data_quality_flags),
            "flags": sorted(set(data_quality_flags)),
        },
        "source": {
            "mating_source": MATING_OVERVIEW_SHEET,
            "litter_source": LITTER_OVERVIEW_SHEET,
            "writes_to_google_sheets": False,
            "writes_to_supabase": False,
        },
    }, 200


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

        if target_pen_id:
            pen_lookup = _get_pen_lookup()
            target_pen = pen_lookup.get(target_pen_id)
            if not target_pen:
                raise ValueError(f"Pen '{target_pen_id}' not found in PEN_REGISTER.")
            if target_pen.get("pen_type") != "Farrowing":
                raise ValueError("Target pen must be a Farrowing pen.")

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
                    moved_by=moved_by,
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


def mark_not_pregnant(mating_id: str, target_pen_id: str, moved_by: str, dry_run: bool = False):
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
        "Actual_Farrowing_Date", "Mating_Status", "Outcome",
        "Linked_Litter_ID", "Updated_At",
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
        linked_litter_id = to_clean_string(padded_row[header_index["Linked_Litter_ID"]])
        actual_farrowing_date = to_clean_string(padded_row[header_index["Actual_Farrowing_Date"]])

        if current_status != "Confirmed_Pregnant":
            raise ValueError("Only Confirmed_Pregnant matings can be marked not pregnant.")

        if linked_litter_id:
            raise ValueError("Cannot mark not pregnant because a litter is already linked.")

        if actual_farrowing_date:
            raise ValueError("Cannot mark not pregnant because actual farrowing is already recorded.")

        if target_pen_id:
            pen_lookup = _get_pen_lookup()
            target_pen = pen_lookup.get(target_pen_id)
            if not target_pen:
                raise ValueError(f"Pen '{target_pen_id}' not found in PEN_REGISTER.")
            if target_pen.get("pen_type") == "Farrowing":
                raise ValueError("Target pen must not be a Farrowing pen.")

        planned_updates = {
            "Pregnancy_Check_Date": today_str,
            "Pregnancy_Check_Result": "Not_Pregnant",
            "Mating_Status": "Repeat_Service",
            "Outcome": "Repeat_Required",
            "Updated_At": today_str,
        }

        for field, value in planned_updates.items():
            padded_row[header_index[field]] = value

        sow_pig_id = to_clean_string(padded_row[header_index["Sow_Pig_ID"]])
        movement_planned = False
        current_pen_id = ""
        if target_pen_id and sow_pig_id:
            pig_lookup = _get_pig_lookup()
            sow_row = pig_lookup.get(sow_pig_id, {})
            current_pen_id = to_clean_string(sow_row.get("Current_Pen_ID", ""))
            movement_planned = current_pen_id != target_pen_id

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "message": "Dry run passed. No mating or movement rows were changed.",
                "mating_id": mating_id,
                "planned_updates": planned_updates,
                "movement_planned": movement_planned,
                "movement_logged": False,
                "sow_pig_id": sow_pig_id,
                "current_pen_id": current_pen_id,
                "target_pen_id": target_pen_id,
            }

        update_row_by_first_column_match(MATING_LOG_SHEET, mating_id, padded_row)

        movement_logged = False
        if target_pen_id and sow_pig_id:
            movement_logged = _write_movement_if_needed(
                pig_id=sow_pig_id,
                current_pen_id=current_pen_id,
                target_pen_id=target_pen_id,
                move_date=datetime.now().date(),
                reason="Moved for repeat service",
                moved_by=moved_by,
            )

        message = "Mating updated to Repeat_Service."
        if movement_logged:
            message += " Sow movement logged."

        return {
            "success": True,
            "message": message,
            "mating_id": mating_id,
            "movement_logged": movement_logged,
        }

    raise ValueError(f"Mating_ID '{mating_id}' not found in MATING_LOG.")
