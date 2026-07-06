import math
from datetime import datetime, timedelta

from services.google_sheets_service import (
    append_row,
    batch_update_rows_by_id,
    ensure_worksheet,
    get_all_records,
    get_all_values,
    update_row_by_first_column_match,
)
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
    generate_pig_id,
    generate_product_id,
    generate_pen_id,
    generate_litter_id,
)
from modules.pig_weights.mating_service import link_litter_to_mating
from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights import farm_supabase_write_service
from modules.sales.sales_transaction_read import get_monthly_sales_transaction_summary

TERMINAL_PIG_STATUSES = {"Sold", "Slaughtered", "Dead", "Removed"}
LIFECYCLE_REMOVAL_REASONS = {
    "Died": "Dead",
    "Culled": "Dead",
    "Lost": "Dead",
    "Stillborn": "Dead",
    "Died after birth": "Dead",
    "Crushed by sow": "Dead",
    "Weak piglet": "Dead",
    "Unknown": "Dead",
    "Removed": "Removed",
    "Other": "Removed",
}
LITTER_PIGLET_DEATH_REASONS = {
    "Stillborn",
    "Died after birth",
    "Crushed by sow",
    "Weak piglet",
    "Unknown",
}
STILLBORN_RECLASSIFY_CANDIDATE_REASONS = {"Died", "Died after birth", "Unknown", ""}
LITTER_HEALTH_EARMARK_FIELDS = ("Earmarked", "Earmark_Date")
DEFAULT_LITTER_WEAN_AGE_DAYS = 35
WEAN_TAG_ATTENTION_WINDOW_DAYS = 3
POST_WEAN_PURPOSE_REVIEW_DAYS = 14
LIVE_SALE_TARGET_KG = 60
MEAT_TARGET_MIN_KG = 60
MEAT_TARGET_MAX_KG = 80
SLAUGHTER_TARGET_MIN_KG = 80
SLAUGHTER_TARGET_MAX_KG = None
STALE_WEIGHT_DAYS = 30
LIVE_STOCK_SALE_PURPOSE = "sale"
LIVE_STOCK_MIN_SALE_WEIGHT_KG = 2
BULK_WEIGHT_BATCH_AUDIT_SHEET = "BULK_WEIGHT_BATCH_LOG"
BULK_WEIGHT_ROW_AUDIT_SHEET = "BULK_WEIGHT_BATCH_ROWS"
BULK_WEIGHT_BATCH_AUDIT_HEADERS = [
    "Batch_ID",
    "Uploaded_At",
    "Weight_Date",
    "Uploaded_By",
    "Submitted_Rows",
    "Saved_Weights",
    "Saved_Movements",
    "Duplicate_Weights_Protected",
    "Skipped_Rows",
    "Blocked_Rows",
    "Failed_Rows",
    "Message",
]
BULK_WEIGHT_ROW_AUDIT_HEADERS = [
    "Batch_ID",
    "Uploaded_At",
    "Event_Type",
    "Row_Index",
    "Pig_ID",
    "Tag_Number",
    "Weight_Date",
    "Weight_Kg",
    "From_Pen_ID",
    "To_Pen_ID",
    "Reason",
]
ALLOCATION_BUCKET_ORDER = {
    "Needs Data": 0,
    "Needs Classification": 1,
    "Growing": 2,
    "Livestock Candidate": 3,
    "Slaughter Candidate": 4,
    "Meat Candidate": 5,
    "Retain / Breeding Candidate": 6,
    "Allocated": 7,
    "Exited": 8,
}
EXCEPTIONAL_GROWER_ADG_KG_DAY = 0.50
GOOD_GROWER_ADG_KG_DAY = 0.40
STEADY_GROWER_ADG_KG_DAY = 0.30
SLOW_GROWER_ADG_KG_DAY = 0.20
EXTREMELY_SLOW_GROWER_ADG_KG_DAY = 0.10
GOOD_LITTER_SURVIVAL_RATE = 0.80

DEFAULT_ALLOCATION_SETTINGS = {
    "source": "code_defaults",
    "writes_enabled": False,
    "live_sale_target_kg": LIVE_SALE_TARGET_KG,
    "meat_target_min_kg": MEAT_TARGET_MIN_KG,
    "meat_target_max_kg": MEAT_TARGET_MAX_KG,
    "slaughter_target_min_kg": SLAUGHTER_TARGET_MIN_KG,
    "slaughter_target_max_kg": SLAUGHTER_TARGET_MAX_KG,
    "meat_window_upper_exclusive": True,
    "abattoir_window_upper_unbounded": True,
    "fresh_weight_days": 14,
    "exceptional_grower_adg_kg_day": EXCEPTIONAL_GROWER_ADG_KG_DAY,
    "good_grower_adg_kg_day": GOOD_GROWER_ADG_KG_DAY,
    "steady_grower_adg_kg_day": STEADY_GROWER_ADG_KG_DAY,
    "slow_grower_adg_kg_day": SLOW_GROWER_ADG_KG_DAY,
    "extremely_slow_grower_adg_kg_day": EXTREMELY_SLOW_GROWER_ADG_KG_DAY,
    "good_litter_survival_rate": GOOD_LITTER_SURVIVAL_RATE,
    "stale_weight_days": STALE_WEIGHT_DAYS,
}
PURPOSE_REVIEW_ALLOWED_PURPOSES = {
    "Breeding",
    "Grow_Out",
    "Sale",
    "Replacement",
    "House_Use",
    "Unknown",
}
SUGGESTED_PURPOSE_TO_STORED_PURPOSE = {
    "Grow Out": "Grow_Out",
    "Livestock Sale": "Sale",
    "Meat": "Grow_Out",
    "Abattoir Slaughter": "Grow_Out",
    "Breeding Review": "Breeding",
}


def _allocation_settings():
    return dict(DEFAULT_ALLOCATION_SETTINGS)


def _try_supabase_read(reader, *args):
    if not farm_supabase_read_service.farm_supabase_reads_available():
        return None
    try:
        return reader(*args)
    except Exception:
        return None


def _try_supabase_litter_update(litter_id, updates):
    if not farm_supabase_write_service.farm_supabase_writes_available():
        return None
    try:
        return farm_supabase_write_service.update_litter_by_id(litter_id, updates)
    except Exception:
        return None


def _try_supabase_pig_updates(updates):
    if not farm_supabase_write_service.farm_supabase_writes_available():
        return None
    try:
        return farm_supabase_write_service.update_pigs_by_id(updates)
    except Exception:
        return None


def _get_pig_master_rows():
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_pig_master_rows)
    if supabase_result is not None:
        return supabase_result
    return get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])


def _get_litter_register_rows():
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_litter_register_rows)
    if supabase_result is not None:
        return supabase_result
    return get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"])


def _get_litter_overview_rows():
    supabase_result = _try_supabase_read(farm_supabase_read_service.list_litter_overview)
    if supabase_result is not None:
        return [{
            "Litter_ID": item.get("litter_id", ""),
            "Sow_Pig_ID": item.get("sow_pig_id", ""),
            "Sow_Tag_Number": item.get("sow_tag_number", ""),
            "Boar_Pig_ID": item.get("boar_pig_id", ""),
            "Boar_Tag_Number": item.get("boar_tag_number", ""),
            "Current_Pen_ID": item.get("current_pen_id", ""),
            "Farrowing_Date": item.get("farrowing_date", ""),
            "Wean_Date": item.get("wean_date", ""),
            "Litter_Status": item.get("litter_status", ""),
            "Needs_Attention": item.get("needs_attention", ""),
            "Born_Alive": item.get("born_alive", ""),
            "Total_Born": item.get("total_born", ""),
            "Weaned_Count": item.get("weaned_count", ""),
            "Tagged_Pig_Count": item.get("tagged_pig_count", ""),
            "Untagged_Pig_Count": item.get("untagged_pig_count", ""),
            "Average_Current_Weight_Kg": item.get("average_current_weight_kg", ""),
            "source": "supabase_canonical",
        } for item in supabase_result.get("litters", [])]
    return get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_overview"])


def _build_pig_lookup(rows, columns):
    pig_lookup = {}
    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id:
            pig_lookup[row_pig_id] = row
    return pig_lookup


def _pig_summary_card(row, columns):
    return {
        "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
        "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
        "sex": to_clean_string(row.get("Sex", "")),
        "status": to_clean_string(row.get(columns["status"], "")),
        "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
        "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
        "age_days": row.get("Age_Days", ""),
        "current_weight_kg": to_float(row.get(columns["current_weight"], "")),
        "calculated_stage": to_clean_string(row.get("Calculated_Stage", "")),
        "current_pen_id": to_clean_string(row.get("Current_Pen_ID", "")),
        "litter_id": to_clean_string(row.get("Litter_ID", "")),
    }


def _build_pen_lookup():
    lookup = {}

    for row in get_pens():
        pen_id = to_clean_string(row.get("pen_id", row.get("Pen_ID", "")))
        if not pen_id:
            continue
        lookup[pen_id] = {
            "pen_id": pen_id,
            "pen_name": to_clean_string(row.get("pen_name", row.get("Pen_Name", ""))),
            "pen_type": to_clean_string(row.get("pen_type", row.get("Pen_Type", ""))),
        }

    return lookup


def _pen_name_for_id(pen_lookup, pen_id):
    pen = pen_lookup.get(to_clean_string(pen_id), {})
    return to_clean_string(pen.get("pen_name", ""))


def _sale_stream_for_exit(row):
    status = to_clean_string(row.get("Status", "")).lower().replace("-", "_").replace(" ", "_")
    exit_reason = to_clean_string(row.get("Exit_Reason", "")).lower().replace("-", "_").replace(" ", "_")

    slaughter_reasons = {
        "slaughter",
        "slaughtered",
        "abattoir",
        "abattoir_sale",
        "sold_to_abattoir",
    }
    meat_reasons = {
        "meat",
        "meat_sale",
        "carcass",
        "carcass_sale",
        "pork_sale",
        "processed_meat_sale",
    }
    livestock_reasons = {
        "sold",
        "livestock",
        "livestock_sale",
        "live_sale",
    }

    if exit_reason in meat_reasons:
        return "meat"
    if exit_reason in slaughter_reasons or status == "slaughtered":
        return "slaughter"
    if exit_reason in livestock_reasons or status == "sold":
        return "livestock"
    return ""


def _lifecycle_outcome_for_exit(row):
    status = to_clean_string(row.get("Status", "")).lower().replace("-", "_").replace(" ", "_")
    exit_reason = to_clean_string(row.get("Exit_Reason", "")).lower().replace("-", "_").replace(" ", "_")

    if status in {"dead", "died", "deceased"} or exit_reason in {"died", "dead", "deceased", "culled", "lost", "stillborn", "died_after_birth", "crushed_by_sow", "weak_piglet", "unknown"}:
        return "dead"
    if status in {"removed", "disposed"} or exit_reason in {"removed", "disposed", "disposal", "other"}:
        return "removed"
    if status == "slaughtered" or exit_reason in {"slaughter", "slaughtered", "abattoir", "abattoir_sale", "sold_to_abattoir"}:
        return "slaughtered"
    if status in {"sold", "completed_sale"} or exit_reason in {"sold", "completed_sale", "sale_completed", "livestock", "livestock_sale", "live_sale", "meat", "meat_sale", "carcass", "carcass_sale", "pork_sale", "processed_meat_sale"}:
        return "sold"
    if exit_reason:
        return "other"
    return ""


def _empty_litter_lifecycle_outcomes():
    return {
        "active": 0,
        "sold": 0,
        "slaughtered": 0,
        "dead": 0,
        "removed": 0,
        "other": 0,
        "total": 0,
    }


def _estimated_wean_date_from_birth(birth_date):
    if not birth_date:
        return None
    return birth_date + timedelta(days=DEFAULT_LITTER_WEAN_AGE_DAYS)


def _wean_tag_attention_start_date(estimated_wean_date):
    if not estimated_wean_date:
        return None
    return estimated_wean_date - timedelta(days=WEAN_TAG_ATTENTION_WINDOW_DAYS)


def _litter_birth_date_from_row(row):
    return (
        parse_sheet_date(row.get("Farrowing_Date", ""))
        or parse_sheet_date(row.get("Date_Of_Birth", ""))
        or parse_sheet_date(row.get("Birth_Date", ""))
    )


def _litter_wean_timing(row, today=None):
    today = today or datetime.now().date()
    birth_date = _litter_birth_date_from_row(row)
    estimated_wean_date = _estimated_wean_date_from_birth(birth_date)
    attention_start_date = _wean_tag_attention_start_date(estimated_wean_date)
    planning_monday = None
    if estimated_wean_date:
        planning_monday = estimated_wean_date - timedelta(days=estimated_wean_date.weekday())

    return {
        "birth_date": birth_date,
        "estimated_wean_date": estimated_wean_date,
        "wean_tag_attention_start_date": attention_start_date,
        "wean_planning_monday": planning_monday,
        "wean_tag_attention_due": bool(attention_start_date and today >= attention_start_date),
        "days_until_estimated_wean": (estimated_wean_date - today).days if estimated_wean_date else None,
    }


def _format_optional_json_date(value):
    return format_date_for_json(value) if value else ""


def _litter_wean_timing_json(row, today=None):
    timing = _litter_wean_timing(row, today=today)
    return {
        "birth_date": _format_optional_json_date(timing["birth_date"]),
        "estimated_wean_date": _format_optional_json_date(timing["estimated_wean_date"]),
        "wean_tag_attention_start_date": _format_optional_json_date(timing["wean_tag_attention_start_date"]),
        "wean_planning_monday": _format_optional_json_date(timing["wean_planning_monday"]),
        "wean_tag_attention_due": timing["wean_tag_attention_due"],
        "days_until_estimated_wean": timing["days_until_estimated_wean"],
        "default_wean_age_days": DEFAULT_LITTER_WEAN_AGE_DAYS,
        "attention_window_days": WEAN_TAG_ATTENTION_WINDOW_DAYS,
    }


def _is_tag_number_attention(reason):
    return "tag" in to_clean_string(reason).lower()


def _wean_tag_attention_is_not_due(wean_timing):
    return bool(wean_timing["wean_tag_attention_start_date"] and not wean_timing["wean_tag_attention_due"])


def _litter_lifecycle_outcomes(litter_id, pig_master_rows):
    outcomes = _empty_litter_lifecycle_outcomes()
    for row in pig_master_rows:
        if to_clean_string(row.get("Litter_ID", "")) != litter_id:
            continue
        outcomes["total"] += 1
        outcome = _lifecycle_outcome_for_exit(row)
        status = to_clean_string(row.get("Status", ""))
        on_farm = to_clean_string(row.get("On_Farm", ""))
        if outcome:
            outcomes[outcome] += 1
        elif status == "Active" and on_farm == "Yes":
            outcomes["active"] += 1
        else:
            outcomes["other"] += 1
    return outcomes


def _derive_litter_status(row, reconciliation, lifecycle_outcomes):
    explicit_status = to_clean_string(row.get("Litter_Status", ""))
    if explicit_status and explicit_status.lower() != "unknown":
        return explicit_status
    if int(lifecycle_outcomes.get("total") or 0) <= 0:
        return "No piglets recorded"
    if int(lifecycle_outcomes.get("active") or 0) > 0:
        return "Active"
    if (to_float(row.get("Weaned_Count", "")) or to_float(row.get("Litter_Size_Weaned", "")) or 0) > 0:
        return "Weaned"
    terminal_count = sum(int(lifecycle_outcomes.get(key) or 0) for key in ("sold", "slaughtered", "dead", "removed"))
    if terminal_count >= int(lifecycle_outcomes.get("total") or 0):
        return "Completed"
    if int(reconciliation.get("linked_pig_records") or 0) > 0:
        return "Review"
    return "Unknown"


def get_dashboard_summary():
    now = datetime.now()
    supabase_summary = _try_supabase_read(farm_supabase_read_service.get_dashboard_summary, now.date())
    if supabase_summary is not None:
        transaction_summary, _transaction_status_code = get_monthly_sales_transaction_summary(now.date())
        transaction_streams = transaction_summary.get("streams", {})
        transaction_totals = transaction_summary.get("totals", {})
        livestock_transactions = transaction_streams.get("livestock", {})
        slaughter_transactions = transaction_streams.get("slaughter", {})
        meat_transactions = transaction_streams.get("meat", {})
        supabase_summary.update({
            "sales_transaction_summary_status": transaction_summary.get("status", "unknown"),
            "sales_transaction_summary_configured": bool(transaction_summary.get("configured")),
            "sales_transaction_count_this_month": transaction_totals.get("transaction_count", 0),
            "sales_transaction_value_this_month": transaction_totals.get("net_total", 0.0),
            "livestock_sales_this_month": livestock_transactions.get("transaction_count", 0),
            "livestock_sales_value_this_month": livestock_transactions.get("net_total", 0.0),
            "slaughter_sales_this_month": slaughter_transactions.get("transaction_count", 0),
            "slaughter_sales_value_this_month": slaughter_transactions.get("net_total", 0.0),
            "meat_sales_this_month": meat_transactions.get("transaction_count", 0),
            "meat_sales_value_this_month": meat_transactions.get("net_total", 0.0),
        })
        return supabase_summary

    columns = PIG_WEIGHTS_CONFIG["columns"]

    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    sales_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["sales_availability"])
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])

    on_farm_pigs = 0
    boars = 0
    sows = 0
    gilts = 0
    piglets = 0
    weaners = 0
    growers = 0
    finishers = 0
    reserved_count = 0
    withdrawal_hold_count = 0

    for row in pig_rows:
        on_farm = to_clean_string(row.get(columns["on_farm"], ""))
        animal_type = to_clean_string(row.get("Animal_Type", ""))
        reserved_status = to_clean_string(row.get(columns["reserved_status"], ""))
        withdrawal_clear = to_clean_string(row.get(columns["withdrawal_clear"], ""))

        if on_farm == "Yes":
            on_farm_pigs += 1
            if animal_type == "Boar":
                boars += 1
            elif animal_type == "Sow":
                sows += 1
            elif animal_type == "Gilt":
                gilts += 1
            elif animal_type == "Piglet":
                piglets += 1
            elif animal_type == "Weaner":
                weaners += 1
            elif animal_type == "Grower":
                growers += 1
            elif animal_type == "Finisher":
                finishers += 1

        if reserved_status == "Reserved":
            reserved_count += 1
        if withdrawal_clear == "No":
            withdrawal_hold_count += 1

    available_for_sale_count = 0

    for row in sales_rows:
        available_for_sale = to_clean_string(row.get(columns["available_for_sale"], ""))
        if available_for_sale == "Yes":
            available_for_sale_count += 1

    sales_this_month = {
        "livestock": 0,
        "slaughter": 0,
        "meat": 0,
    }
    lifecycle_outcomes_this_month = {
        "sold": 0,
        "slaughtered": 0,
        "dead": 0,
        "removed": 0,
        "other": 0,
    }

    for row in pig_master_rows:
        exit_date = parse_sheet_date(row.get("Exit_Date", ""))
        if not exit_date or exit_date.year != now.year or exit_date.month != now.month:
            continue

        lifecycle_outcome = _lifecycle_outcome_for_exit(row)
        if lifecycle_outcome:
            lifecycle_outcomes_this_month[lifecycle_outcome] += 1

        sale_stream = _sale_stream_for_exit(row)
        if sale_stream:
            sales_this_month[sale_stream] += 1

    sold_this_month = sum(sales_this_month.values())
    total_lifecycle_outcomes_this_month = sum(lifecycle_outcomes_this_month.values())
    transaction_summary, _transaction_status_code = get_monthly_sales_transaction_summary(now.date())
    transaction_streams = transaction_summary.get("streams", {})
    transaction_totals = transaction_summary.get("totals", {})
    livestock_transactions = transaction_streams.get("livestock", {})
    slaughter_transactions = transaction_streams.get("slaughter", {})
    meat_transactions = transaction_streams.get("meat", {})

    return {
        "on_farm_pigs": on_farm_pigs,
        "boars": boars,
        "sows": sows,
        "gilts": gilts,
        "piglets": piglets,
        "weaners": weaners,
        "growers": growers,
        "finishers": finishers,
        "sold_this_month": sold_this_month,
        "livestock_sold_this_month": sales_this_month["livestock"],
        "slaughter_sold_this_month": sales_this_month["slaughter"],
        "meat_sold_this_month": sales_this_month["meat"],
        "pig_exit_sold_this_month": sold_this_month,
        "pig_exit_livestock_sold_this_month": sales_this_month["livestock"],
        "pig_exit_slaughter_sold_this_month": sales_this_month["slaughter"],
        "pig_exit_meat_sold_this_month": sales_this_month["meat"],
        "lifecycle_outcomes_this_month": total_lifecycle_outcomes_this_month,
        "lifecycle_sold_this_month": lifecycle_outcomes_this_month["sold"],
        "lifecycle_slaughtered_this_month": lifecycle_outcomes_this_month["slaughtered"],
        "lifecycle_dead_this_month": lifecycle_outcomes_this_month["dead"],
        "lifecycle_removed_this_month": lifecycle_outcomes_this_month["removed"],
        "lifecycle_other_this_month": lifecycle_outcomes_this_month["other"],
        "sales_transaction_summary_status": transaction_summary.get("status", "unknown"),
        "sales_transaction_summary_configured": bool(transaction_summary.get("configured")),
        "sales_transaction_count_this_month": transaction_totals.get("transaction_count", 0),
        "sales_transaction_value_this_month": transaction_totals.get("net_total", 0.0),
        "livestock_sales_this_month": livestock_transactions.get("transaction_count", 0),
        "livestock_sales_value_this_month": livestock_transactions.get("net_total", 0.0),
        "slaughter_sales_this_month": slaughter_transactions.get("transaction_count", 0),
        "slaughter_sales_value_this_month": slaughter_transactions.get("net_total", 0.0),
        "meat_sales_this_month": meat_transactions.get("transaction_count", 0),
        "meat_sales_value_this_month": meat_transactions.get("net_total", 0.0),
        "available_for_sale_pigs": available_for_sale_count,
        "reserved_pigs": reserved_count,
        "withdrawal_hold_pigs": withdrawal_hold_count,
    }


def get_litter_attention_summary(limit: int = 5, today=None):
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_litter_attention_summary, limit)
    if supabase_result is not None:
        return supabase_result

    today = today or datetime.now().date()
    overview = list_litter_overview()
    rows = overview.get("litters", [])
    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
    medical_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"])
    newborn_products = _newborn_health_product_ids()
    items = []

    for row in rows:
        litter_id = to_clean_string(row.get("litter_id", row.get("Litter_ID", "")))
        if not litter_id:
            continue

        needs_attention = to_clean_string(row.get("needs_attention", row.get("Needs_Attention", "")))
        litter_status = to_clean_string(row.get("litter_status", row.get("Litter_Status", "")))
        active_pig_count = to_float(row.get("active_pig_records", row.get("Active_Pig_Count", ""))) or 0
        wean_date = row.get("wean_date", row.get("Wean_Date", ""))
        summary_timing_row = {
            "Farrowing_Date": row.get("farrowing_date", row.get("Farrowing_Date", "")),
            "Wean_Date": wean_date,
        }
        wean_timing = _litter_wean_timing(summary_timing_row, today=today)
        reconciliation = row.get("reconciliation") or {}

        reason = ""
        action_type = ""
        recommended_action = ""
        purpose_attention = None
        newborn_attention = _litter_newborn_health_attention(
            litter_id,
            litter_status,
            wean_date,
            pig_master_rows,
            medical_rows,
            newborn_products,
        )
        if newborn_attention:
            reason = newborn_attention["reason"]
            action_type = newborn_attention["action_type"]
            recommended_action = newborn_attention["recommended_action"]
        elif reconciliation.get("formula_conflict"):
            reason = ""
        elif needs_attention == "Yes":
            reason = row.get("attention_reason") or reconciliation.get("recommended_action") or _litter_attention_reason(row, reconciliation)
            if _is_tag_number_attention(reason) and _wean_tag_attention_is_not_due(wean_timing):
                reason = ""
        elif litter_status == "Weaned":
            purpose_attention = _litter_purpose_review_attention(
                litter_id,
                pig_rows=pig_rows,
                pig_master_rows=pig_master_rows,
                today=today,
            )
            if purpose_attention:
                reason = purpose_attention["reason"]
                action_type = purpose_attention["action_type"]
                recommended_action = purpose_attention["recommended_action"]

        if not reason:
            continue

        items.append({
            "litter_id": litter_id,
            "sow_tag_number": to_clean_string(row.get("sow_tag_number", row.get("Sow_Tag_Number", ""))),
            "farrowing_date": format_date_for_json(row.get("farrowing_date", row.get("Farrowing_Date", ""))),
            "wean_date": format_date_for_json(wean_date),
            "litter_status": litter_status,
            "needs_attention": needs_attention,
            "reason": reason,
            "action_type": action_type,
            "recommended_action": recommended_action,
            "active_pig_count": active_pig_count,
            "weaned_count": to_float(row.get("weaned_count", row.get("Weaned_Count", ""))),
            "youngest_age_days": row.get("youngest_age_days", row.get("Youngest_Age_Days", "")),
            "oldest_age_days": row.get("oldest_age_days", row.get("Oldest_Age_Days", "")),
            "estimated_wean_date": _format_optional_json_date(wean_timing["estimated_wean_date"]),
            "wean_tag_attention_start_date": _format_optional_json_date(wean_timing["wean_tag_attention_start_date"]),
            "wean_planning_monday": _format_optional_json_date(wean_timing["wean_planning_monday"]),
            "days_until_estimated_wean": wean_timing["days_until_estimated_wean"],
        })

    return {
        "count": len(items),
        "items": items[:limit],
    }


def _litter_birth_reconciliation(row):
    born_alive = to_float(row.get("Born_Alive", ""))
    total_born = to_float(row.get("Total_Born", ""))
    stillborn_count = to_float(row.get("Stillborn_Count", "")) or 0
    mummified_count = to_float(row.get("Mummified_Count", "")) or 0
    pig_master_count = to_float(row.get("Pig_Master_Row_Count", ""))
    active_pig_count = to_float(row.get("Active_Pig_Count", "")) or 0
    exited_pig_count = to_float(row.get("Exited_Pig_Count", "")) or 0
    linked_count = int(pig_master_count or 0)
    born_alive_int = int(born_alive) if born_alive is not None else None
    total_born_int = int(total_born) if total_born is not None else None
    stillborn_int = int(stillborn_count)
    mummified_int = int(mummified_count)
    non_live_count = stillborn_int + mummified_int
    source_counts_total = born_alive_int + non_live_count if born_alive_int is not None else None
    source_counts_consistent = (
        total_born_int is not None
        and source_counts_total is not None
        and source_counts_total == total_born_int
    )
    formula_conflict = (
        non_live_count > 0
        and source_counts_consistent
        and linked_count == total_born_int
        and born_alive_int != linked_count
    )
    mismatch = (
        born_alive is not None
        and pig_master_count is not None
        and born_alive != pig_master_count
        and not formula_conflict
    )
    suggested_born_alive = linked_count if mismatch else born_alive_int

    return {
        "born_alive": born_alive_int,
        "total_born": total_born_int,
        "stillborn_count": stillborn_int,
        "mummified_count": mummified_int,
        "non_live_count": non_live_count,
        "linked_pig_records": linked_count,
        "active_pig_records": int(active_pig_count),
        "exited_pig_records": int(exited_pig_count),
        "suggested_born_alive": suggested_born_alive,
        "mismatch": mismatch,
        "formula_conflict": formula_conflict,
        "source_counts_consistent": source_counts_consistent,
        "can_reconcile_birth_count": mismatch,
        "delta": int(pig_master_count - born_alive) if (mismatch or formula_conflict) else 0,
        "sheet_needs_attention": to_clean_string(row.get("Needs_Attention", "")),
        "sheet_attention_reason": to_clean_string(row.get("Attention_Reason", "")),
        "rule": "Born_Alive must match linked PIG_MASTER rows for the current Google Sheets attention formula.",
        "recommended_action": (
            "Do not change Born_Alive. The source counts reconcile as Total_Born = Born_Alive + Stillborn/Mummified, "
            "but the overview formula is counting non-live pig records as linked rows."
            if formula_conflict
            else "Preview the Born_Alive correction before saving."
            if mismatch
            else "No birth-count correction needed."
        ),
    }


def _litter_master_rows_for_litter(litter_id, pig_master_rows):
    return [
        row for row in (pig_master_rows or [])
        if to_clean_string(row.get("Litter_ID", "")) == litter_id
    ]


def _is_stillborn_history_row(row):
    return to_clean_string(row.get("Exit_Reason", "")).lower() == "stillborn"


def _is_stillborn_reclassify_candidate(row):
    exit_reason = to_clean_string(row.get("Exit_Reason", ""))
    return (
        to_clean_string(row.get("Status", "")) == "Dead"
        and to_clean_string(row.get("On_Farm", "")) == "No"
        and exit_reason in STILLBORN_RECLASSIFY_CANDIDATE_REASONS
        and exit_reason != "Stillborn"
    )


def _is_birth_count_attention_reason(reason):
    normalized = to_clean_string(reason).lower()
    return (
        "born alive" in normalized
        or "birth count" in normalized
        or "linked pig records" in normalized
        or "linked live pig records" in normalized
    )


def _piglet_correction_summary(row):
    return {
        "pig_id": to_clean_string(row.get("Pig_ID", "")),
        "tag_number": to_clean_string(row.get("Tag_Number", "")),
        "sex": to_clean_string(row.get("Sex", "")),
        "status": to_clean_string(row.get("Status", "")),
        "on_farm": to_clean_string(row.get("On_Farm", "")),
        "exit_date": format_date_for_json(row.get("Exit_Date", "")) or to_clean_string(row.get("Exit_Date", "")),
        "exit_reason": to_clean_string(row.get("Exit_Reason", "")),
    }


def _augment_litter_birth_reconciliation_with_history(litter_id, reconciliation, pig_master_rows):
    reconciliation = dict(reconciliation or {})
    litter_rows = _litter_master_rows_for_litter(litter_id, pig_master_rows)
    stillborn_rows = [row for row in litter_rows if _is_stillborn_history_row(row)]
    candidates = [row for row in litter_rows if _is_stillborn_reclassify_candidate(row)]
    candidates.sort(key=lambda row: (
        to_clean_string(row.get("Tag_Number", "")),
        to_clean_string(row.get("Pig_ID", "")),
    ))
    lifecycle_outcomes = _litter_lifecycle_outcomes(litter_id, pig_master_rows)

    born_alive = reconciliation.get("born_alive")
    linked_records = len(litter_rows)
    existing_stillborn = len(stillborn_rows)
    live_linked_records = linked_records - existing_stillborn
    accounted_terminal_live = sum(
        int(lifecycle_outcomes.get(key) or 0)
        for key in ("sold", "slaughtered", "removed")
    )
    stillborn_count = int(reconciliation.get("stillborn_count") or 0)
    stillborn_shortfall = max(stillborn_count - existing_stillborn, 0)
    non_live_count = int(reconciliation.get("non_live_count") or 0)
    source_counts_consistent = reconciliation.get("source_counts_consistent") is True
    non_live_source_accounted = bool(
        source_counts_consistent
        and born_alive is not None
        and live_linked_records == int(born_alive)
        and non_live_count > existing_stillborn
    )
    source_count_conflict = bool(
        reconciliation.get("total_born") is not None
        and born_alive is not None
        and int(reconciliation.get("total_born") or 0) != int(born_alive) + non_live_count
    )
    history_mismatch = (
        born_alive is not None
        and linked_records > 0
        and live_linked_records != int(born_alive)
    )
    formula_conflict = (
        born_alive is not None
        and linked_records > 0
        and reconciliation.get("sheet_needs_attention") == "Yes"
        and _is_birth_count_attention_reason(reconciliation.get("sheet_attention_reason", ""))
        and source_counts_consistent
        and linked_records != int(born_alive)
        and live_linked_records == int(born_alive)
    )
    can_reclassify = (
        history_mismatch
        and stillborn_shortfall > 0
        and len(candidates) >= stillborn_shortfall
    )

    reconciliation.update({
        "linked_pig_records": linked_records or reconciliation.get("linked_pig_records", 0),
        "live_linked_pig_records": live_linked_records,
        "accounted_terminal_live_pig_records": accounted_terminal_live,
        "stillborn_history_count": existing_stillborn,
        "stillborn_history_shortfall": stillborn_shortfall,
        "non_live_source_accounted": non_live_source_accounted,
        "dead_reclassify_candidate_count": len(candidates),
        "mismatch": (history_mismatch or source_count_conflict) and not formula_conflict,
        "formula_conflict": formula_conflict,
        "can_reclassify_stillborn": can_reclassify,
        "can_reconcile_birth_count": (history_mismatch or source_count_conflict) and not formula_conflict and not can_reclassify,
        "suggested_born_alive": live_linked_records if history_mismatch else born_alive,
        "delta": live_linked_records - int(born_alive) if born_alive is not None else 0,
        "source_count_conflict": source_count_conflict,
        "stillborn_reclassify_candidates": [_piglet_correction_summary(row) for row in candidates[:10]],
    })

    if formula_conflict:
        reconciliation["recommended_action"] = (
            "Do not change Born_Alive. The pig history already has the right number of stillborn rows; "
            "the sheet formula is counting non-live rows as linked live records."
        )
    elif can_reclassify:
        reconciliation["recommended_action"] = (
            f"Preview reclassifying {stillborn_shortfall} dead piglet row(s) as Stillborn. "
            "This keeps Total Born history intact and clears the live-count mismatch."
        )
    elif (
        source_count_conflict
    ):
        reconciliation["recommended_action"] = "Review litter source counts: Total Born must equal Born Alive plus Stillborn/Mummified."
    elif history_mismatch:
        reconciliation["recommended_action"] = (
            "Review missing or extra live-born piglet history before changing the Born_Alive count. "
            "Sold, slaughtered, disposed, removed, and completed-sale piglets with terminal rows are already counted as accounted outcomes."
        )
    else:
        reconciliation["recommended_action"] = "No birth-count correction needed."

    return reconciliation


def _litter_birth_reconciliation_for_id(litter_id):
    rows = _get_litter_overview_rows()
    for row in rows:
        if to_clean_string(row.get("Litter_ID", "")) == litter_id:
            return _litter_birth_reconciliation(row)
    return {
        "born_alive": None,
        "total_born": None,
        "stillborn_count": 0,
        "mummified_count": 0,
        "linked_pig_records": 0,
        "active_pig_records": 0,
        "exited_pig_records": 0,
        "suggested_born_alive": 0,
        "mismatch": False,
        "formula_conflict": False,
        "source_counts_consistent": False,
        "can_reconcile_birth_count": False,
        "delta": 0,
        "rule": "Litter overview row was not found.",
        "recommended_action": "No litter overview row was found.",
    }


def list_litter_overview():
    supabase_result = _try_supabase_read(farm_supabase_read_service.list_litter_overview)
    if supabase_result is not None:
        return supabase_result

    rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_overview"])
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
    litters = []

    for row in rows:
        litter_id = to_clean_string(row.get("Litter_ID", ""))
        if not litter_id:
            continue

        reconciliation = _augment_litter_birth_reconciliation_with_history(
            litter_id,
            _litter_birth_reconciliation(row),
            pig_master_rows,
        )
        lifecycle_outcomes = _litter_lifecycle_outcomes(litter_id, pig_master_rows)
        sheet_needs_attention = to_clean_string(row.get("Needs_Attention", ""))
        effective_needs_attention = sheet_needs_attention
        if (
            reconciliation["formula_conflict"]
            or (
                sheet_needs_attention == "Yes"
                and not reconciliation["mismatch"]
                and reconciliation.get("born_alive") is not None
                and _is_birth_count_attention_reason(reconciliation.get("sheet_attention_reason", ""))
            )
        ):
            effective_needs_attention = ""

        litters.append({
            "litter_id": litter_id,
            "sow_pig_id": to_clean_string(row.get("Sow_Pig_ID", "")),
            "sow_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
            "boar_pig_id": to_clean_string(row.get("Boar_Pig_ID", "")),
            "boar_tag_number": to_clean_string(row.get("Boar_Tag_Number", "")),
            "current_pen_id": to_clean_string(row.get("Current_Pen_ID", "")),
            "farrowing_date": format_date_for_json(row.get("Farrowing_Date", "")),
            "wean_date": format_date_for_json(row.get("Wean_Date", "")),
            "litter_status": _derive_litter_status(row, reconciliation, lifecycle_outcomes),
            "needs_attention": effective_needs_attention,
            "sheet_needs_attention": sheet_needs_attention,
            "attention_reason": _litter_attention_reason(row, reconciliation) if effective_needs_attention == "Yes" else "",
            "born_alive": reconciliation["born_alive"],
            "total_born": reconciliation["total_born"],
            "linked_pig_records": reconciliation["linked_pig_records"],
            "active_pig_records": reconciliation["active_pig_records"],
            "exited_pig_records": reconciliation["exited_pig_records"],
            "tagged_pig_count": int(to_float(row.get("Tagged_Pig_Count", "")) or 0),
            "untagged_pig_count": int(to_float(row.get("Untagged_Pig_Count", "")) or 0),
            "average_current_weight_kg": to_float(row.get("Average_Current_Weight_Kg", "")),
            "lifecycle_outcomes": lifecycle_outcomes,
            "reconciliation": reconciliation,
        })

    litters.sort(key=lambda item: (
        item["needs_attention"] != "Yes",
        item["farrowing_date"] or "9999-12-31",
        item["litter_id"],
    ))

    return {
        "success": True,
        "count": len(litters),
        "attention_count": sum(1 for item in litters if item["needs_attention"] == "Yes"),
        "mismatch_count": sum(1 for item in litters if item["reconciliation"]["mismatch"]),
        "formula_conflict_count": sum(1 for item in litters if item["reconciliation"]["formula_conflict"]),
        "litters": litters,
        "source": {
            "reads_from": "LITTER_OVERVIEW",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
    }


def _litter_register_row(litter_id):
    supabase_rows = _try_supabase_read(farm_supabase_read_service.get_litter_register_rows)
    if supabase_rows is not None:
        headers = [
            "Litter_ID",
            "Farrowing_Date",
            "Sow_Pig_ID",
            "Boar_Pig_ID",
            "Total_Born",
            "Born_Alive",
            "Stillborn_Count",
            "Mummified_Count",
            "Male_Count",
            "Female_Count",
            "Unknown_Sex_Count",
            "Weaned_Count",
            "Litter_Size_Weaned",
            "Wean_Date",
            "Litter_Status",
            "Litter_Notes",
            "Updated_At",
        ]
        for row in supabase_rows:
            if to_clean_string(row.get("Litter_ID", "")) == litter_id:
                padded_row = [row.get(header, "") for header in headers]
                return headers, row, padded_row
        return headers, None, None

    return _litter_register_row_from_sheets(litter_id)


def _litter_register_row_from_sheets(litter_id):
    all_values = get_all_values(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"])
    if not all_values or len(all_values) < 2:
        return None, None, None

    headers = all_values[0]
    for row in all_values[1:]:
        if row and to_clean_string(row[0]) == litter_id:
            padded_row = list(row) + [""] * (len(headers) - len(row))
            return headers, {header: padded_row[index] for index, header in enumerate(headers)}, padded_row

    return headers, None, None


def _append_litter_correction_note(existing_notes, changed_by, reason, previous_born_alive, new_born_alive):
    clean_existing = to_clean_string(existing_notes)
    changed_by = to_clean_string(changed_by) or "web_app"
    reason = to_clean_string(reason) or "Birth count reconciled from litter detail."
    entry = (
        f"{format_date_for_sheet(datetime.now().date())} birth-count correction by {changed_by}: "
        f"Born_Alive {previous_born_alive or '-'} -> {new_born_alive}. {reason}"
    )
    return f"{clean_existing}\n{entry}" if clean_existing else entry


def _append_stillborn_reclassification_note(existing_notes, changed_by, reason, previous_exit_reason, previous_exit_date):
    clean_existing = to_clean_string(existing_notes)
    changed_by = to_clean_string(changed_by) or "web_app"
    reason = to_clean_string(reason) or "Corrected litter birth history from litter detail."
    entry = (
        f"{format_date_for_sheet(datetime.now().date())} stillborn correction by {changed_by}: "
        f"reclassified from {previous_exit_reason or '-'} to Stillborn. "
        f"Previous exit date: {previous_exit_date or '-'}. {reason}"
    )
    return f"{clean_existing}\n{entry}" if clean_existing else entry


def reclassify_litter_dead_piglets_as_stillborn(
    litter_id: str,
    pig_ids=None,
    count=None,
    changed_by: str = "web_app",
    reason: str = "",
    dry_run: bool = True,
):
    litter_id = to_clean_string(litter_id)
    changed_by = to_clean_string(changed_by) or "web_app"
    pig_ids = [to_clean_string(pig_id) for pig_id in (pig_ids or []) if to_clean_string(pig_id)]
    dry_run = dry_run is True

    if not litter_id:
        return {"success": False, "errors": ["Litter ID is required."]}, 400

    overview_rows = _get_litter_overview_rows()
    overview_row = next(
        (row for row in overview_rows if to_clean_string(row.get("Litter_ID", "")) == litter_id),
        None,
    )
    if not overview_row:
        return {"success": False, "errors": [f"Litter '{litter_id}' was not found in LITTER_OVERVIEW."]}, 404

    farrowing_date = _litter_birth_date_from_row(overview_row)
    if not farrowing_date:
        return {
            "success": False,
            "errors": ["Farrowing date is required before stillborn rows can be corrected."],
        }, 409

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    pig_master_rows = _get_pig_master_rows()
    reconciliation = _augment_litter_birth_reconciliation_with_history(
        litter_id,
        _litter_birth_reconciliation(overview_row),
        pig_master_rows,
    )
    stillborn_shortfall = int(reconciliation.get("stillborn_history_shortfall") or 0)
    if stillborn_shortfall <= 0:
        return {
            "success": False,
            "errors": ["This litter already has the required Stillborn piglet history rows."],
            "litter_id": litter_id,
            "reconciliation": reconciliation,
        }, 409

    target_count = to_float(count)
    if target_count is None:
        target_count = len(pig_ids) if pig_ids else stillborn_shortfall
    if target_count < 1 or int(target_count) != target_count:
        return {"success": False, "errors": ["Correction count must be a whole number greater than zero."]}, 400
    target_count = int(target_count)
    if target_count != stillborn_shortfall:
        return {
            "success": False,
            "errors": [f"This correction must reclassify exactly {stillborn_shortfall} piglet row(s)."],
            "litter_id": litter_id,
            "requested_count": target_count,
            "reconciliation": reconciliation,
        }, 409

    litter_rows = _litter_master_rows_for_litter(litter_id, pig_master_rows)
    candidates = [row for row in litter_rows if _is_stillborn_reclassify_candidate(row)]
    candidates.sort(key=lambda row: (
        to_clean_string(row.get("Tag_Number", "")),
        to_clean_string(row.get("Pig_ID", "")),
    ))
    candidate_lookup = {
        to_clean_string(row.get("Pig_ID", "")): row
        for row in candidates
        if to_clean_string(row.get("Pig_ID", ""))
    }

    if pig_ids:
        missing = [pig_id for pig_id in pig_ids if pig_id not in candidate_lookup]
        if missing:
            return {
                "success": False,
                "errors": ["Selected piglet rows are not valid dead-row Stillborn correction candidates."],
                "invalid_pig_ids": missing,
                "available_candidates": [_piglet_correction_summary(row) for row in candidates],
            }, 409
        selected_rows = [candidate_lookup[pig_id] for pig_id in pig_ids]
    else:
        selected_rows = candidates[:target_count]

    if len(selected_rows) != target_count:
        return {
            "success": False,
            "errors": [f"Only {len(selected_rows)} valid correction candidate(s) were found; {target_count} required."],
            "available_candidates": [_piglet_correction_summary(row) for row in candidates],
            "reconciliation": reconciliation,
        }, 409

    today_sheet = format_date_for_sheet(datetime.now().date())
    farrowing_date_sheet = format_date_for_sheet(farrowing_date)
    planned_updates = {}
    selected_piglets = []
    for row in selected_rows:
        pig_id = to_clean_string(row.get("Pig_ID", ""))
        previous_exit_reason = to_clean_string(row.get("Exit_Reason", ""))
        previous_exit_date = to_clean_string(row.get("Exit_Date", ""))
        planned_updates[pig_id] = {
            "Status": "Dead",
            "On_Farm": "No",
            "Exit_Date": farrowing_date_sheet,
            "Exit_Reason": "Stillborn",
            "Updated_At": today_sheet,
            "General_Notes": _append_stillborn_reclassification_note(
                row.get("General_Notes", ""),
                changed_by,
                reason,
                previous_exit_reason,
                previous_exit_date,
            ),
        }
        selected_piglets.append(_piglet_correction_summary(row))

    rows_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_rows_updated = _try_supabase_pig_updates(planned_updates)
        if supabase_rows_updated is not None:
            rows_updated = supabase_rows_updated
            writes_to_supabase = True
        else:
            rows_updated = batch_update_rows_by_id(pig_master_sheet, planned_updates)

    return {
        "success": True,
        "action": "reclassify_litter_dead_piglets_as_stillborn",
        "dry_run": dry_run,
        "litter_id": litter_id,
        "changed_by": changed_by,
        "reason": to_clean_string(reason),
        "correction_count": target_count,
        "selected_piglets": selected_piglets,
        "planned_updates": planned_updates,
        "rows_updated": rows_updated,
        "reconciliation": reconciliation,
        "source": {
            "reads_from": ["LITTER_OVERVIEW", "PIG_MASTER"],
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Stillborn correction previewed for {target_count} piglet row(s)."
            if dry_run
            else f"Stillborn correction saved for {target_count} piglet row(s)."
        ),
    }, 200


def reconcile_litter_birth_counts(litter_id: str, target_born_alive=None, changed_by: str = "web_app", reason: str = "", dry_run: bool = True):
    litter_id = to_clean_string(litter_id)
    changed_by = to_clean_string(changed_by) or "web_app"
    dry_run = dry_run is True

    if not litter_id:
        return {"success": False, "errors": ["Litter ID is required."]}, 400

    overview_rows = _get_litter_overview_rows()
    overview_row = None
    for row in overview_rows:
        if to_clean_string(row.get("Litter_ID", "")) == litter_id:
            overview_row = row
            break

    if not overview_row:
        return {"success": False, "errors": [f"Litter '{litter_id}' was not found in LITTER_OVERVIEW."]}, 404

    reconciliation = _litter_birth_reconciliation(overview_row)
    current_born_alive = reconciliation["born_alive"]
    linked_pig_records = reconciliation["linked_pig_records"]
    if reconciliation.get("formula_conflict"):
        return {
            "success": False,
            "errors": [reconciliation["recommended_action"]],
            "litter_id": litter_id,
            "reconciliation": reconciliation,
            "source": {
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }, 409

    target_value = to_float(target_born_alive)
    if target_value is None:
        target_value = linked_pig_records
    if target_value < 0 or int(target_value) != target_value:
        return {"success": False, "errors": ["Target born alive must be a whole number zero or greater."]}, 400

    target_int = int(target_value)
    if target_int != linked_pig_records:
        return {
            "success": False,
            "errors": [
                "This reconcile action only clears the current count mismatch when Born_Alive matches linked pig records. "
                "Use a future piglet-record correction workflow if the linked pig records are wrong."
            ],
            "litter_id": litter_id,
            "target_born_alive": target_int,
            "linked_pig_records": linked_pig_records,
        }, 409

    headers, register_row, padded_row = _litter_register_row(litter_id)
    if not register_row:
        return {"success": False, "errors": [f"Litter '{litter_id}' was not found in LITTERS."]}, 404

    required_columns = {"Born_Alive", "Litter_Notes"}
    missing_columns = sorted(required_columns - set(headers))
    if missing_columns:
        return {
            "success": False,
            "errors": ["LITTERS is missing required columns for safe reconciliation."],
            "missing_columns": missing_columns,
        }, 409

    planned_updates = {
        "Born_Alive": target_int,
        "Litter_Notes": _append_litter_correction_note(
            register_row.get("Litter_Notes", ""),
            changed_by,
            reason,
            current_born_alive,
            target_int,
        ),
    }
    if "Updated_At" in headers:
        planned_updates["Updated_At"] = format_date_for_sheet(datetime.now().date())

    updated_row = list(padded_row)
    header_map = {header: index for index, header in enumerate(headers)}
    for field_name, field_value in planned_updates.items():
        updated_row[header_map[field_name]] = field_value

    row_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_row_updated = _try_supabase_litter_update(litter_id, planned_updates)
        if supabase_row_updated is not None:
            row_updated = supabase_row_updated
            writes_to_supabase = True
        else:
            sheet_headers, _sheet_register_row, sheet_padded_row = _litter_register_row_from_sheets(litter_id)
            if not _sheet_register_row:
                return {"success": False, "errors": [f"Litter '{litter_id}' was not found in LITTERS."]}, 404
            sheet_header_map = {header: index for index, header in enumerate(sheet_headers)}
            for field_name, field_value in planned_updates.items():
                if field_name not in sheet_header_map:
                    raise ValueError(f"Missing required column '{field_name}' in LITTERS.")
                sheet_padded_row[sheet_header_map[field_name]] = field_value
            row_updated = update_row_by_first_column_match(
                PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"],
                litter_id,
                sheet_padded_row,
            )

    return {
        "success": True,
        "action": "reconcile_litter_birth_counts",
        "dry_run": dry_run,
        "litter_id": litter_id,
        "changed_by": changed_by,
        "reason": to_clean_string(reason),
        "previous": {
            "born_alive": current_born_alive,
            "linked_pig_records": linked_pig_records,
        },
        "target_born_alive": target_int,
        "planned_updates": planned_updates,
        "row_updated": row_updated,
        "source": {
            "reads_from": ["LITTER_OVERVIEW", "LITTERS"],
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Litter {litter_id} birth-count correction previewed."
            if dry_run
            else f"Litter {litter_id} birth count was reconciled."
        ),
    }, 200


def _litter_attention_reason(row, reconciliation=None):
    reconciliation = reconciliation or _litter_birth_reconciliation(row)
    if reconciliation.get("formula_conflict"):
        return ""
    if reconciliation.get("can_reclassify_stillborn"):
        return "Dead piglet rows need Stillborn history correction"

    explicit_reason = to_clean_string(row.get("Attention_Reason", ""))
    if explicit_reason:
        return explicit_reason

    total_born = to_float(row.get("Total_Born", ""))
    born_alive = to_float(row.get("Born_Alive", ""))
    pig_master_count = to_float(row.get("Pig_Master_Row_Count", ""))
    tagged_count = to_float(row.get("Tagged_Pig_Count", ""))

    if born_alive is None and total_born is not None:
        return "Born alive count missing"
    if born_alive is not None and pig_master_count is not None and pig_master_count != born_alive:
        return "Linked pig records do not match born alive count"
    if pig_master_count and tagged_count == 0:
        return "Piglets need tag numbers"
    return "Needs attention"


def _purpose_needs_review(purpose):
    normalized = to_clean_string(purpose).lower()
    return normalized in ("", "unknown")


def _stored_purpose_for_suggestion(suggested_purpose):
    return SUGGESTED_PURPOSE_TO_STORED_PURPOSE.get(to_clean_string(suggested_purpose), "")


def _purpose_review_status(row):
    purpose = to_clean_string(row.get("purpose", ""))
    if _purpose_needs_review(purpose):
        if row.get("readiness_bucket") == "Needs Data":
            return "needs_data"
        return "needs_owner_decision"
    return "classified"


def _purpose_review_row(row):
    proposed_purpose = _stored_purpose_for_suggestion(row.get("suggested_purpose", ""))
    review_status = _purpose_review_status(row)
    if review_status == "needs_data":
        owner_action = "Complete missing tag, sex, pen, or weight data before approving purpose."
    elif proposed_purpose:
        owner_action = f"Review Herdmaster suggestion and approve {proposed_purpose}, override it, or recheck."
    elif review_status == "needs_owner_decision":
        owner_action = "Review manually; the current data is not strong enough for a trusted auto-suggestion."
    else:
        owner_action = "Already classified; no purpose approval is required."

    return {
        "pig_id": row.get("pig_id", ""),
        "tag_number": row.get("tag_number", ""),
        "litter_id": row.get("litter_id", ""),
        "sow_tag_number": row.get("sow_tag_number", ""),
        "boar_tag_number": row.get("boar_tag_number", ""),
        "animal_type": row.get("animal_type", ""),
        "sex": row.get("sex", ""),
        "status": row.get("status", ""),
        "on_farm": row.get("on_farm", ""),
        "current_pen_id": row.get("current_pen_id", ""),
        "current_pen_name": row.get("current_pen_name", ""),
        "purpose": row.get("purpose", ""),
        "proposed_purpose": proposed_purpose,
        "suggested_purpose": row.get("suggested_purpose", ""),
        "suggested_purpose_reason": row.get("suggested_purpose_reason", ""),
        "suggested_purpose_confidence": row.get("suggested_purpose_confidence", ""),
        "readiness_bucket": row.get("readiness_bucket", ""),
        "readiness_reason": row.get("readiness_reason", ""),
        "review_status": review_status,
        "owner_action": owner_action,
        "latest_weight_kg": row.get("latest_weight_kg"),
        "latest_weight_date": row.get("latest_weight_date", ""),
        "days_since_weight": row.get("days_since_weight"),
        "wean_date": row.get("wean_date", ""),
        "wean_weight_kg": row.get("wean_weight_kg"),
        "days_since_wean": row.get("days_since_wean"),
        "average_daily_gain_kg": row.get("average_daily_gain_kg"),
        "post_wean_daily_gain_kg": row.get("post_wean_daily_gain_kg"),
        "growth_class": row.get("growth_class", ""),
        "growth_reason": row.get("growth_reason", ""),
        "litter_quality": row.get("litter_quality", ""),
        "litter_quality_reason": row.get("litter_quality_reason", ""),
        "litter_survival_rate": row.get("litter_survival_rate"),
        "outlet_priority": row.get("outlet_priority", ""),
        "recommended_action": row.get("recommended_action", ""),
        "marketing_readiness": row.get("marketing_readiness", ""),
        "existing_link": row.get("existing_link", ""),
    }


def get_purpose_review_queue(litter_id: str = "", today=None):
    litter_id = to_clean_string(litter_id)
    allocation = get_pig_allocation_readiness(today=today)
    review_rows = []

    for row in allocation.get("pigs", []):
        if row.get("status") != "Active" or row.get("on_farm") != "Yes":
            continue
        if litter_id and row.get("litter_id") != litter_id:
            continue
        if not litter_id and not _purpose_needs_review(row.get("purpose", "")):
            continue
        review_rows.append(_purpose_review_row(row))

    summary = {
        "total": len(review_rows),
        "needs_owner_decision": sum(1 for row in review_rows if row["review_status"] == "needs_owner_decision"),
        "needs_data": sum(1 for row in review_rows if row["review_status"] == "needs_data"),
        "classified": sum(1 for row in review_rows if row["review_status"] == "classified"),
    }

    return {
        "success": True,
        "mode": "herdmaster_purpose_review_queue",
        "owner_agent": "Herdmaster",
        "litter_id": litter_id,
        "generated_date": allocation.get("generated_date", ""),
        "summary": summary,
        "business_rules": allocation.get("business_rules", {}),
        "allowed_purposes": sorted(PURPOSE_REVIEW_ALLOWED_PURPOSES),
        "pigs": review_rows,
        "writes_to_sheets": False,
        "writes_to_supabase": False,
        "message": "Purpose review queue loaded. Suggestions are advisory until approved by a human.",
    }


def _append_purpose_review_note(existing_notes, changed_at, changed_by, old_purpose, new_purpose, reason, note):
    clean_existing = to_clean_string(existing_notes)
    reason = to_clean_string(reason)
    note = to_clean_string(note)
    entry = (
        f"{format_date_for_sheet(changed_at)} purpose review: {old_purpose or 'Unknown'} "
        f"to {new_purpose} approved by {changed_by}."
    )
    if reason:
        entry = f"{entry} Reason: {reason}"
    if note:
        entry = f"{entry} Note: {note}"
    return f"{clean_existing}\n{entry}" if clean_existing else entry


def apply_purpose_review_decisions(decisions, changed_by: str = "web_app", dry_run: bool = True, allow_reclassify: bool = False):
    changed_by = to_clean_string(changed_by) or "web_app"
    dry_run = dry_run is True
    allow_reclassify = allow_reclassify is True
    if not isinstance(decisions, list) or not decisions:
        return {"success": False, "errors": ["At least one purpose review decision is required."]}, 400

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    requested_pig_ids = [
        to_clean_string(decision.get("pig_id", ""))
        for decision in decisions
        if isinstance(decision, dict) and to_clean_string(decision.get("pig_id", ""))
    ]
    pig_rows = _try_supabase_read(farm_supabase_read_service.get_pig_master_rows_by_ids, requested_pig_ids)
    if pig_rows is None:
        pig_rows = _get_pig_master_rows()
    pig_lookup = _build_pig_lookup(pig_rows, columns)
    today = datetime.now().date()
    today_sheet = format_date_for_sheet(today)
    updates = {}
    approved = []
    errors = []

    for index, decision in enumerate(decisions, start=1):
        decision = decision or {}
        pig_id = to_clean_string(decision.get("pig_id", ""))
        new_purpose = to_clean_string(decision.get("purpose", ""))
        reason = to_clean_string(decision.get("reason", ""))
        note = to_clean_string(decision.get("note", ""))

        if not pig_id:
            errors.append(f"Decision {index}: Pig ID is required.")
            continue
        if new_purpose not in PURPOSE_REVIEW_ALLOWED_PURPOSES:
            errors.append(f"Decision {index}: Purpose must be one of {', '.join(sorted(PURPOSE_REVIEW_ALLOWED_PURPOSES))}.")
            continue

        pig = pig_lookup.get(pig_id)
        if not pig:
            errors.append(f"Decision {index}: Pig '{pig_id}' was not found.")
            continue

        current_status = to_clean_string(pig.get(columns["status"], ""))
        current_on_farm = to_clean_string(pig.get(columns["on_farm"], ""))
        old_purpose = to_clean_string(pig.get("Purpose", ""))
        if current_status != "Active" or current_on_farm != "Yes":
            errors.append(f"Decision {index}: Pig '{pig_id}' is not active/on-farm.")
            continue
        if not allow_reclassify and not _purpose_needs_review(old_purpose):
            errors.append(f"Decision {index}: Pig '{pig_id}' already has purpose '{old_purpose}'. Use a future reclassification workflow.")
            continue

        updates[pig_id] = {
            "Purpose": new_purpose,
            "Updated_At": today_sheet,
            "General_Notes": _append_purpose_review_note(
                pig.get("General_Notes", ""),
                today,
                changed_by,
                old_purpose,
                new_purpose,
                reason,
                note,
            ),
        }
        approved.append({
            "pig_id": pig_id,
            "tag_number": to_clean_string(pig.get("Tag_Number", "")),
            "litter_id": to_clean_string(pig.get("Litter_ID", "")),
            "old_purpose": old_purpose or "Unknown",
            "new_purpose": new_purpose,
            "reason": reason,
        })

    if errors:
        return {
            "success": False,
            "errors": errors,
            "approved_count": len(approved),
            "planned_updates": updates,
            "source": {
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }, 409

    rows_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_rows_updated = _try_supabase_pig_updates(updates)
        if supabase_rows_updated is not None:
            rows_updated = supabase_rows_updated
            writes_to_supabase = True
        else:
            rows_updated = batch_update_rows_by_id(pig_master_sheet, updates)

    return {
        "success": True,
        "action": "apply_purpose_review_decisions",
        "dry_run": dry_run,
        "changed_by": changed_by,
        "approved_count": len(approved),
        "approved": approved,
        "rows_updated": rows_updated,
        "planned_updates": updates,
        "source": {
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
            "writes_orders": False,
            "writes_sales": False,
            "writes_slaughter": False,
        },
        "message": (
            f"Purpose review previewed for {len(approved)} pig(s)."
            if dry_run
            else f"Purpose review saved for {len(approved)} pig(s)."
        ),
    }, 200


def build_purpose_review_recheck(pig_id: str, question: str = "", today=None):
    pig_id = to_clean_string(pig_id)
    question = to_clean_string(question)
    if not pig_id:
        return {"success": False, "errors": ["Pig ID is required."]}, 400

    allocation = get_pig_allocation_readiness(today=today)
    row = next((item for item in allocation.get("pigs", []) if item.get("pig_id") == pig_id), None)
    if not row:
        return {"success": False, "errors": [f"Pig '{pig_id}' was not found in allocation readiness."]}, 404

    review_row = _purpose_review_row(row)
    focus = [
        review_row["readiness_reason"],
        review_row["suggested_purpose_reason"],
        review_row["growth_reason"],
        review_row["litter_quality_reason"],
        review_row["recommended_action"],
    ]
    return {
        "success": True,
        "mode": "herdmaster_purpose_review_recheck",
        "owner_agent": "Herdmaster",
        "pig_id": pig_id,
        "question": question,
        "review": review_row,
        "analysis_points": [item for item in focus if item],
        "writes_to_sheets": False,
        "writes_to_supabase": False,
        "message": "Herdmaster recheck packet built from current allocation signals. No records were changed.",
    }, 200


def _litter_needs_purpose_review(litter_id, pig_rows=None):
    litter_id = to_clean_string(litter_id)
    if not litter_id:
        return False

    if pig_rows is None:
        pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])

    for pig in pig_rows:
        if to_clean_string(pig.get("Litter_ID", "")) != litter_id:
            continue
        if to_clean_string(pig.get("Status", "")) != "Active":
            continue
        if to_clean_string(pig.get("On_Farm", "")) != "Yes":
            continue
        if _purpose_needs_review(pig.get("Purpose", "")):
            return True

    return False


def _litter_purpose_review_attention(litter_id, pig_rows=None, pig_master_rows=None, today=None):
    today = today or datetime.now().date()
    litter_id = to_clean_string(litter_id)
    if not litter_id:
        return None

    if pig_rows is None:
        pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    if pig_master_rows is None:
        pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])

    columns = PIG_WEIGHTS_CONFIG["columns"]
    master_lookup = _build_pig_lookup(pig_master_rows, columns)
    candidates = []
    for pig in pig_rows:
        if to_clean_string(pig.get("Litter_ID", "")) != litter_id:
            continue
        if to_clean_string(pig.get("Status", "")) != "Active":
            continue
        if to_clean_string(pig.get("On_Farm", "")) != "Yes":
            continue
        if _purpose_needs_review(pig.get("Purpose", "")):
            candidates.append(pig)

    if not candidates:
        return None

    missing_wean_data = []
    not_due_count = 0
    missing_post_wean_weight = []
    due_for_review = []

    for pig in candidates:
        pig_id = to_clean_string(pig.get(columns["pig_id"], ""))
        master = master_lookup.get(pig_id, {})
        wean_date = parse_sheet_date(master.get("Wean_Date", "")) or parse_sheet_date(pig.get("Wean_Date", ""))
        wean_weight_kg = to_float(master.get("Wean_Weight_Kg", ""))
        if wean_weight_kg is None:
            wean_weight_kg = to_float(pig.get("Wean_Weight_Kg", ""))

        if not wean_date or wean_weight_kg is None:
            missing_wean_data.append(pig_id or to_clean_string(pig.get("Tag_Number", "")))
            continue

        days_since_wean = (today - wean_date).days
        if days_since_wean < POST_WEAN_PURPOSE_REVIEW_DAYS:
            not_due_count += 1
            continue

        latest_weight_date = parse_sheet_date(pig.get("Last_Weight_Date", ""))
        if not latest_weight_date or latest_weight_date <= wean_date:
            missing_post_wean_weight.append(pig_id or to_clean_string(pig.get("Tag_Number", "")))
            continue

        due_for_review.append(pig_id or to_clean_string(pig.get("Tag_Number", "")))

    if missing_wean_data:
        return {
            "reason": "Weaned - complete wean data",
            "recommended_action": "Complete piglet wean date and wean weight before Herdmaster purpose review.",
            "action_type": "complete_wean_data",
            "affected_pig_count": len(missing_wean_data),
            "due_after_days": POST_WEAN_PURPOSE_REVIEW_DAYS,
        }

    if missing_post_wean_weight:
        return {
            "reason": "Post-wean weight needed",
            "recommended_action": (
                f"Capture a post-wean weight at least {POST_WEAN_PURPOSE_REVIEW_DAYS} days after weaning "
                "before final purpose review."
            ),
            "action_type": "record_post_wean_weight",
            "affected_pig_count": len(missing_post_wean_weight),
            "due_after_days": POST_WEAN_PURPOSE_REVIEW_DAYS,
        }

    if due_for_review:
        return {
            "reason": "Purpose review due",
            "recommended_action": "Herdmaster has enough post-wean context for owner purpose review.",
            "action_type": "review_purpose",
            "affected_pig_count": len(due_for_review),
            "due_after_days": POST_WEAN_PURPOSE_REVIEW_DAYS,
        }

    return None


def _newborn_health_product_ids(products=None):
    products = products if products is not None else get_products()
    result = {
        "antiparasitic": set(),
        "deworming": set(),
    }
    for product in products:
        product_id = to_clean_string(product.get("product_id", ""))
        if not product_id:
            continue
        text = f"{product.get('product_name', '')} {product.get('product_category', '')}".lower()
        if "ecomectin" in text or "antiparasitic" in text or "parasite" in text:
            result["antiparasitic"].add(product_id)
        if "panacur" in text or "deworm" in text:
            result["deworming"].add(product_id)
    return result


def _litter_newborn_health_attention(litter_id, litter_status, wean_date_value, pig_master_rows, medical_rows, newborn_products):
    if to_clean_string(litter_status) == "Weaned" or parse_sheet_date(wean_date_value):
        return None

    active_piglets = [
        row for row in pig_master_rows
        if to_clean_string(row.get("Litter_ID", "")) == litter_id
        and to_clean_string(row.get("Status", "")) == "Active"
        and to_clean_string(row.get("On_Farm", "")) == "Yes"
    ]
    if not active_piglets:
        return None

    treatments_by_pig = {}
    for row in medical_rows:
        pig_id = to_clean_string(row.get("Pig_ID", ""))
        product_id = to_clean_string(row.get("Product_ID", ""))
        if pig_id and product_id:
            treatments_by_pig.setdefault(pig_id, set()).add(product_id)

    antiparasitic_ids = newborn_products.get("antiparasitic", set())
    deworming_ids = newborn_products.get("deworming", set())
    missing_count = 0
    for pig in active_piglets:
        pig_id = to_clean_string(pig.get("Pig_ID", ""))
        product_ids = treatments_by_pig.get(pig_id, set())
        antiparasitic_missing = bool(antiparasitic_ids) and product_ids.isdisjoint(antiparasitic_ids)
        deworming_missing = bool(deworming_ids) and product_ids.isdisjoint(deworming_ids)
        if antiparasitic_missing or deworming_missing:
            missing_count += 1

    if not missing_count:
        return None

    return {
        "reason": "Piglets need newborn health records",
        "recommended_action": "Record Ecomectin and Panacur newborn treatments.",
        "action_type": "record_litter_newborn_health",
        "missing_piglet_count": missing_count,
    }


def _build_litter_attention(row, pig_rows=None, pig_master_rows=None, medical_rows=None, newborn_products=None, today=None):
    today = today or datetime.now().date()
    litter_id = to_clean_string(row.get("Litter_ID", ""))
    needs_attention = to_clean_string(row.get("Needs_Attention", ""))
    litter_status = to_clean_string(row.get("Litter_Status", ""))
    active_pig_count = to_float(row.get("Active_Pig_Count", "")) or 0

    reason = ""
    recommended_action = ""
    action_type = ""
    wean_timing = _litter_wean_timing(row, today=today)

    newborn_attention = None
    if pig_master_rows is not None and medical_rows is not None:
        newborn_attention = _litter_newborn_health_attention(
            litter_id,
            litter_status,
            row.get("Wean_Date", ""),
            pig_master_rows,
            medical_rows,
            newborn_products or _newborn_health_product_ids(),
        )

    if newborn_attention:
        reason = newborn_attention["reason"]
        recommended_action = newborn_attention["recommended_action"]
        action_type = newborn_attention["action_type"]
    else:
        reconciliation = _litter_birth_reconciliation(row)
        if pig_master_rows is not None:
            reconciliation = _augment_litter_birth_reconciliation_with_history(litter_id, reconciliation, pig_master_rows)

    if (
        not newborn_attention
        and (
            reconciliation.get("formula_conflict")
            or (
                pig_master_rows is not None
                and
                needs_attention == "Yes"
                and not reconciliation.get("mismatch")
                and reconciliation.get("born_alive") is not None
                and _is_birth_count_attention_reason(reconciliation.get("sheet_attention_reason", ""))
            )
        )
    ):
        reason = ""
        recommended_action = ""
        action_type = ""
    elif not newborn_attention and needs_attention == "Yes":
        reason = _litter_attention_reason(row, reconciliation)
        reason_lower = reason.lower()
        if "linked pig records" in reason_lower:
            recommended_action = (
                "Reconcile Born Alive against linked pig records. Add the missing born-alive/death records "
                "or correct the litter count before using weaning actions."
            )
            action_type = "reconcile_litter_records"
        elif "born alive" in reason_lower:
            recommended_action = "Complete the born-alive count before resolving this litter attention item."
            action_type = "complete_born_alive"
        elif "tag" in reason_lower:
            if not _wean_tag_attention_is_not_due(wean_timing):
                recommended_action = "Assign tag numbers and earmarks to the linked piglets around weaning."
                action_type = "assign_tag_numbers"
            else:
                reason = ""
                recommended_action = ""
                action_type = ""
        else:
            recommended_action = "Review this litter and correct the source data shown in the attention reason."
            action_type = "review_litter"
    elif litter_status == "Weaned":
        purpose_attention = _litter_purpose_review_attention(
            litter_id,
            pig_rows=pig_rows,
            pig_master_rows=pig_master_rows,
            today=today,
        )
        if purpose_attention:
            reason = purpose_attention["reason"]
            recommended_action = purpose_attention["recommended_action"]
            action_type = purpose_attention["action_type"]
    elif litter_status != "Weaned" and active_pig_count > 0 and not _wean_tag_attention_is_not_due(wean_timing):
        reason = ""
        recommended_action = "Confirm the litter status and mark it as weaned once the weaning date is known."
        action_type = "mark_weaned"

    return {
        "needs_attention": needs_attention,
        "reason": reason,
        "recommended_action": recommended_action,
        "action_type": action_type,
        "litter_status": litter_status,
        "wean_date": format_date_for_json(row.get("Wean_Date", "")),
        "active_pig_count": active_pig_count,
        "weaned_count": to_float(row.get("Weaned_Count", "")),
        **_litter_wean_timing_json(row, today=today),
    }


def _litter_attention_for_id(litter_id):
    rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_overview"])
    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
    medical_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"])
    newborn_products = _newborn_health_product_ids()

    for row in rows:
        if to_clean_string(row.get("Litter_ID", "")) == litter_id:
            return _build_litter_attention(row, pig_rows, pig_master_rows, medical_rows, newborn_products)

    return {
        "needs_attention": "",
        "reason": "",
        "recommended_action": "",
        "action_type": "",
        "litter_status": "",
        "wean_date": "",
        "active_pig_count": 0,
        "weaned_count": None,
    }


def _update_litter_weaning_fields(litter_id, wean_date, weaned_count):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"]
    all_values = get_all_values(sheet_name)

    if not all_values or len(all_values) < 2:
        raise ValueError("No litter rows found.")

    headers = all_values[0]
    header_map = {header: index for index, header in enumerate(headers)}

    matched_row = None
    for row in all_values[1:]:
        if row and to_clean_string(row[0]) == litter_id:
            matched_row = list(row)
            break

    if matched_row is None:
        raise ValueError(f"Litter '{litter_id}' was not found.")

    padded_row = matched_row + [""] * (len(headers) - len(matched_row))
    sheet_wean_date = format_date_for_sheet(wean_date)
    today = format_date_for_sheet(datetime.now().date())

    for field_name, field_value in {
        "Weaned_Count": weaned_count,
        "Litter_Size_Weaned": weaned_count,
        "Wean_Date": sheet_wean_date,
        "Updated_At": today,
    }.items():
        if field_name in header_map:
            padded_row[header_map[field_name]] = field_value

    return update_row_by_first_column_match(sheet_name, litter_id, padded_row)


def _wean_weight_updates_for_piglets(active_piglet_rows, latest_weights, explicit_wean_weights=None):
    explicit_wean_weights = explicit_wean_weights or {}
    updates = {}
    selected = []
    missing = []
    columns = PIG_WEIGHTS_CONFIG["columns"]

    for row in active_piglet_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if not pig_id:
            continue

        explicit_value = explicit_wean_weights.get(pig_id)
        weight_kg = to_float(explicit_value) if explicit_value not in (None, "") else None
        source = "explicit"
        weight_date = None

        if weight_kg is None:
            latest = latest_weights.get(pig_id, {})
            weight_kg = latest.get("weight_kg")
            weight_date = latest.get("weight_date")
            source = "latest_weight_log"

        if weight_kg is None:
            missing.append(pig_id)
            continue

        updates[pig_id] = weight_kg
        selected.append({
            "pig_id": pig_id,
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "wean_weight_kg": weight_kg,
            "weight_date": weight_date.isoformat() if weight_date else "",
            "source": source,
        })

    return updates, selected, missing


def mark_litter_weaned(
    litter_id: str,
    wean_date_value,
    changed_by: str = "web_app",
    use_latest_weights_as_wean_weights: bool = False,
    wean_weights=None,
):
    litter_id = str(litter_id or "").strip()
    wean_date = parse_sheet_date(wean_date_value)
    use_latest_weights_as_wean_weights = use_latest_weights_as_wean_weights is True
    wean_weights = wean_weights if isinstance(wean_weights, dict) else {}

    if not litter_id:
        return {"success": False, "errors": ["Litter ID is required."]}, 400

    if not wean_date:
        return {"success": False, "errors": ["A valid wean date is required."]}, 400

    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    pig_rows = _get_pig_master_rows()

    active_piglets = []
    active_piglet_rows = []
    for row in pig_rows:
        if to_clean_string(row.get("Litter_ID", "")) != litter_id:
            continue
        if to_clean_string(row.get(columns["status"], "")) != "Active":
            continue
        if to_clean_string(row.get(columns["on_farm"], "")) != "Yes":
            continue

        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if pig_id:
            active_piglets.append(pig_id)
            active_piglet_rows.append(row)

    if not active_piglets:
        return {
            "success": False,
            "errors": ["No active on-farm piglets were found for this litter."],
        }, 409

    latest_weights = {}
    wean_weight_updates = {}
    wean_weight_rows = []
    missing_wean_weight_pig_ids = []
    should_capture_wean_weights = use_latest_weights_as_wean_weights or bool(wean_weights)
    if should_capture_wean_weights:
        latest_weights = {
            to_clean_string(row.get(columns["pig_id"], "")): {
                "weight_kg": to_float(row.get(columns["current_weight"], "")),
                "weight_date": parse_sheet_date(row.get(columns["last_weight_date"], "")),
            }
            for row in active_piglet_rows
            if to_clean_string(row.get(columns["pig_id"], ""))
        }
        if any(not latest.get("weight_kg") for latest in latest_weights.values()):
            weight_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"])
            latest_weights = _latest_weights_by_pig(weight_rows, columns)
        wean_weight_updates, wean_weight_rows, missing_wean_weight_pig_ids = _wean_weight_updates_for_piglets(
            active_piglet_rows,
            latest_weights,
            explicit_wean_weights=wean_weights,
        )
        if missing_wean_weight_pig_ids:
            return {
                "success": False,
                "errors": [
                    "Wean weights were requested, but these piglets do not have explicit or latest weights: "
                    + ", ".join(missing_wean_weight_pig_ids)
                ],
                "missing_wean_weight_pig_ids": missing_wean_weight_pig_ids,
                "source": {
                    "writes_to_sheets": False,
                    "writes_to_supabase": False,
                },
            }, 409

    sheet_wean_date = format_date_for_sheet(wean_date)
    today = format_date_for_sheet(datetime.now().date())
    updated_by = to_clean_string(changed_by) or "web_app"
    weaned_count = len(active_piglets)
    litter_updates = {
        "Weaned_Count": weaned_count,
        "Litter_Size_Weaned": weaned_count,
        "Wean_Date": sheet_wean_date,
        "Updated_At": today,
    }

    pig_updates = {
        pig_id: {
            "Litter_Size_Weaned": weaned_count,
            "Wean_Date": sheet_wean_date,
            "Updated_At": today,
        }
        for pig_id in active_piglets
    }
    for pig_id, weight_kg in wean_weight_updates.items():
        pig_updates[pig_id]["Wean_Weight_Kg"] = weight_kg

    writes_to_supabase = False
    litter_row_updated = _try_supabase_litter_update(litter_id, litter_updates)
    if litter_row_updated is not None:
        pig_rows_updated = _try_supabase_pig_updates(pig_updates)
        if pig_rows_updated is None:
            pig_rows_updated = 0
        writes_to_supabase = True
    else:
        litter_row_updated = _update_litter_weaning_fields(litter_id, wean_date, weaned_count)
        pig_rows_updated = batch_update_rows_by_id(pig_master_sheet, pig_updates)

    return {
        "success": True,
        "action": "mark_litter_weaned",
        "litter_id": litter_id,
        "wean_date": wean_date.isoformat(),
        "weaned_count": weaned_count,
        "wean_weights_captured": len(wean_weight_updates),
        "wean_weight_rows": wean_weight_rows,
        "litter_row_updated": litter_row_updated,
        "pig_rows_updated": pig_rows_updated,
        "changed_by": updated_by,
        "source": {
            "writes_to_sheets": not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Litter {litter_id} was marked as weaned with {weaned_count} active piglet(s) "
            f"and {len(wean_weight_updates)} wean weight(s)."
            if wean_weight_updates
            else f"Litter {litter_id} was marked as weaned with {weaned_count} active piglet(s)."
        ),
    }, 200


def _append_lifecycle_note(existing_notes, event_date, reason, changed_by, notes):
    clean_existing = to_clean_string(existing_notes)
    clean_notes = to_clean_string(notes)
    changed_by = to_clean_string(changed_by) or "web_app"
    entry = f"{format_date_for_sheet(event_date)} lifecycle outcome: {reason} recorded by {changed_by}."
    if clean_notes:
        entry = f"{entry} Notes: {clean_notes}"
    return f"{clean_existing}\n{entry}" if clean_existing else entry


def mark_pig_death_or_removal(
    pig_id: str,
    event_date_value,
    reason: str,
    changed_by: str = "web_app",
    notes: str = "",
    dry_run: bool = False,
):
    pig_id = to_clean_string(pig_id)
    event_date = parse_sheet_date(event_date_value)
    reason = to_clean_string(reason)
    changed_by = to_clean_string(changed_by) or "web_app"

    errors = []
    if not pig_id:
        errors.append("Pig ID is required.")
    if not event_date:
        errors.append("A valid event date is required.")
    if reason not in LIFECYCLE_REMOVAL_REASONS:
        errors.append("Reason must be Died, Culled, Lost, Removed, or Other.")
    if not changed_by:
        errors.append("changed_by is required.")
    if errors:
        return {"success": False, "errors": errors}, 400

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_rows = _get_pig_master_rows()
    pig_lookup = _build_pig_lookup(pig_rows, columns)
    pig = pig_lookup.get(pig_id)

    if not pig:
        return {
            "success": False,
            "errors": [f"Pig '{pig_id}' was not found."],
        }, 404

    current_status = to_clean_string(pig.get(columns["status"], ""))
    current_on_farm = to_clean_string(pig.get(columns["on_farm"], ""))

    if current_status in TERMINAL_PIG_STATUSES or current_on_farm != "Yes":
        return {
            "success": False,
            "errors": ["Pig is already terminal or not on farm. Use a future correction workflow for historical fixes."],
            "pig_id": pig_id,
            "current_status": current_status,
            "current_on_farm": current_on_farm,
        }, 409

    new_status = LIFECYCLE_REMOVAL_REASONS[reason]
    event_date_sheet = format_date_for_sheet(event_date)
    today = format_date_for_sheet(datetime.now().date())
    updated_notes = _append_lifecycle_note(
        pig.get("General_Notes", ""),
        event_date,
        reason,
        changed_by,
        notes,
    )
    updates = {
        "Status": new_status,
        "On_Farm": "No",
        "Exit_Date": event_date_sheet,
        "Exit_Reason": reason,
        "General_Notes": updated_notes,
        "Updated_At": today,
    }
    rows_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_rows_updated = _try_supabase_pig_updates({pig_id: updates})
        if supabase_rows_updated is not None:
            rows_updated = supabase_rows_updated
            writes_to_supabase = True
        else:
            rows_updated = batch_update_rows_by_id(
                pig_master_sheet,
                {
                    pig_id: updates
                },
            )

    return {
        "success": True,
        "action": "mark_pig_death_or_removal",
        "dry_run": dry_run,
        "pig_id": pig_id,
        "status": new_status,
        "on_farm": "No",
        "exit_date": event_date.isoformat(),
        "exit_reason": reason,
        "rows_updated": rows_updated,
        "planned_updates": updates,
        "previous": {
            "status": current_status,
            "on_farm": current_on_farm,
        },
        "changed_by": changed_by,
        "source": {
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Pig {pig_id} would be marked as {new_status}."
            if dry_run
            else f"Pig {pig_id} was marked as {new_status}."
        ),
    }, 200


def _selected_litter_piglet_death_candidates(active_piglets, count, male_count, female_count, pig_ids):
    pig_ids = [to_clean_string(pig_id) for pig_id in (pig_ids or []) if to_clean_string(pig_id)]
    by_id = {
        to_clean_string(row.get("Pig_ID", "")): row
        for row in active_piglets
        if to_clean_string(row.get("Pig_ID", ""))
    }

    if pig_ids:
        missing = [pig_id for pig_id in pig_ids if pig_id not in by_id]
        if missing:
            return None, [f"Selected piglet(s) are not active/on-farm in this litter: {', '.join(missing)}."]
        return [by_id[pig_id] for pig_id in pig_ids], []

    male_count = int(male_count or 0)
    female_count = int(female_count or 0)
    if male_count or female_count:
        selected = []
        for sex, required_count in (("Male", male_count), ("Female", female_count)):
            if not required_count:
                continue
            matches = [
                row for row in active_piglets
                if to_clean_string(row.get("Sex", "")) == sex
            ]
            if len(matches) < required_count:
                return None, [f"Only {len(matches)} active {sex.lower()} piglet(s) are available for this litter."]
            selected.extend(matches[:required_count])
        return selected, []

    if count is None or int(count or 0) <= 0:
        return None, ["Enter a piglet count or select specific piglets."]

    tagged = [
        row for row in active_piglets
        if to_clean_string(row.get("Tag_Number", ""))
    ]
    if tagged:
        return None, ["Tagged piglets must be selected specifically before recording a death."]

    sexed = [
        row for row in active_piglets
        if to_clean_string(row.get("Sex", ""))
    ]
    if sexed:
        return None, ["This litter has sexed piglets. Enter male/female counts or select specific piglets."]

    if len(active_piglets) < count:
        return None, [f"Only {len(active_piglets)} active untagged piglet(s) are available for this litter."]

    return active_piglets[:count], []


def mark_litter_piglets_dead(
    litter_id: str,
    event_date_value,
    reason: str,
    count=None,
    male_count=None,
    female_count=None,
    pig_ids=None,
    changed_by: str = "web_app",
    notes: str = "",
    dry_run: bool = True,
):
    litter_id = to_clean_string(litter_id)
    event_date = parse_sheet_date(event_date_value)
    reason = to_clean_string(reason)
    changed_by = to_clean_string(changed_by) or "web_app"
    notes = to_clean_string(notes)
    dry_run = dry_run is True

    errors = []
    if not litter_id:
        errors.append("Litter ID is required.")
    if not event_date:
        errors.append("A valid event date is required.")
    if reason not in LITTER_PIGLET_DEATH_REASONS:
        errors.append("Reason must be Stillborn, Died after birth, Crushed by sow, Weak piglet, or Unknown.")

    count_value = to_float(count)
    male_count_value = to_float(male_count)
    female_count_value = to_float(female_count)
    if count not in (None, "") and (count_value is None or count_value <= 0):
        errors.append("Count must be a positive number.")
    if male_count not in (None, "") and (male_count_value is None or male_count_value < 0):
        errors.append("Male count cannot be negative.")
    if female_count not in (None, "") and (female_count_value is None or female_count_value < 0):
        errors.append("Female count cannot be negative.")
    if errors:
        return {"success": False, "errors": errors}, 400

    count_int = int(count_value) if count_value is not None else None
    male_count_int = int(male_count_value) if male_count_value is not None else 0
    female_count_int = int(female_count_value) if female_count_value is not None else 0

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_rows = _get_pig_master_rows()
    active_piglets = [
        row for row in pig_rows
        if to_clean_string(row.get("Litter_ID", "")) == litter_id
        and to_clean_string(row.get(columns["status"], "")) == "Active"
        and to_clean_string(row.get(columns["on_farm"], "")) == "Yes"
    ]
    active_piglets.sort(key=lambda row: (
        to_clean_string(row.get("Tag_Number", "")),
        to_clean_string(row.get(columns["pig_id"], "")),
    ))

    if not active_piglets:
        return {
            "success": False,
            "errors": ["No active on-farm piglets were found for this litter."],
            "litter_id": litter_id,
        }, 409

    selected, selection_errors = _selected_litter_piglet_death_candidates(
        active_piglets,
        count_int,
        male_count_int,
        female_count_int,
        pig_ids,
    )
    if selection_errors:
        return {
            "success": False,
            "errors": selection_errors,
            "litter_id": litter_id,
            "active_piglet_count": len(active_piglets),
        }, 409

    event_date_sheet = format_date_for_sheet(event_date)
    today = format_date_for_sheet(datetime.now().date())
    pig_updates = {}
    selected_piglets = []
    for row in selected:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        updated_notes = _append_lifecycle_note(
            row.get("General_Notes", ""),
            event_date,
            reason,
            changed_by,
            notes,
        )
        pig_updates[pig_id] = {
            "Status": "Dead",
            "On_Farm": "No",
            "Exit_Date": event_date_sheet,
            "Exit_Reason": reason,
            "General_Notes": updated_notes,
            "Updated_At": today,
        }
        selected_piglets.append({
            "pig_id": pig_id,
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "sex": to_clean_string(row.get("Sex", "")),
        })

    rows_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_rows_updated = _try_supabase_pig_updates(pig_updates)
        if supabase_rows_updated is not None:
            rows_updated = supabase_rows_updated
            writes_to_supabase = True
        else:
            rows_updated = batch_update_rows_by_id(pig_master_sheet, pig_updates)

    return {
        "success": True,
        "action": "mark_litter_piglets_dead",
        "dry_run": dry_run,
        "litter_id": litter_id,
        "event_date": event_date.isoformat(),
        "reason": reason,
        "piglet_count": len(selected_piglets),
        "selected_piglets": selected_piglets,
        "pig_ids": [piglet["pig_id"] for piglet in selected_piglets],
        "rows_updated": rows_updated,
        "planned_updates": pig_updates,
        "changed_by": changed_by,
        "source": {
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Litter {litter_id} piglet death action previewed for {len(selected_piglets)} piglet(s)."
            if dry_run
            else f"Litter {litter_id} piglet death action saved for {len(selected_piglets)} piglet(s)."
        ),
    }, 200


def _append_sex_count_note(existing_notes, action_date, changed_by, notes):
    note = f"Sex counts recorded on {format_date_for_sheet(action_date)} by {changed_by}."
    if notes:
        note = f"{note} Notes: {notes}"
    existing = to_clean_string(existing_notes)
    return f"{existing} | {note}" if existing else note


def record_litter_piglet_sex_counts(
    litter_id: str,
    action_date_value,
    male_count=None,
    female_count=None,
    changed_by: str = "web_app",
    notes: str = "",
    dry_run: bool = True,
):
    litter_id = to_clean_string(litter_id)
    action_date = parse_sheet_date(action_date_value)
    changed_by = to_clean_string(changed_by) or "web_app"
    notes = to_clean_string(notes)
    dry_run = dry_run is True

    male_count_value = to_float(male_count)
    female_count_value = to_float(female_count)
    errors = []
    if not litter_id:
        errors.append("Litter ID is required.")
    if not action_date:
        errors.append("A valid action date is required.")
    if male_count_value is None or male_count_value < 0:
        errors.append("Male count must be zero or greater.")
    if female_count_value is None or female_count_value < 0:
        errors.append("Female count must be zero or greater.")
    if errors:
        return {"success": False, "errors": errors}, 400

    male_count_int = int(male_count_value)
    female_count_int = int(female_count_value)
    total_count = male_count_int + female_count_int
    if total_count <= 0:
        return {
            "success": False,
            "errors": ["Enter at least one male or female piglet before previewing."],
        }, 400

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_rows = _get_pig_master_rows()
    active_piglets = [
        row for row in pig_rows
        if to_clean_string(row.get("Litter_ID", "")) == litter_id
        and to_clean_string(row.get(columns["status"], "")) == "Active"
        and to_clean_string(row.get(columns["on_farm"], "")) == "Yes"
    ]
    active_piglets.sort(key=lambda row: (
        to_clean_string(row.get("Tag_Number", "")),
        to_clean_string(row.get(columns["pig_id"], "")),
    ))
    unsexed_piglets = [
        row for row in active_piglets
        if not to_clean_string(row.get(columns["sex"], ""))
    ]

    if not active_piglets:
        return {
            "success": False,
            "errors": ["No active on-farm piglets were found for this litter."],
            "litter_id": litter_id,
        }, 409
    if len(unsexed_piglets) < total_count:
        return {
            "success": False,
            "errors": [
                f"Only {len(unsexed_piglets)} active piglet(s) still have blank sex. "
                f"You entered {total_count}."
            ],
            "litter_id": litter_id,
            "active_piglet_count": len(active_piglets),
            "unsexed_piglet_count": len(unsexed_piglets),
        }, 409

    selected_piglets = []
    pig_updates = {}
    action_date_sheet = format_date_for_sheet(action_date)
    today = format_date_for_sheet(datetime.now().date())
    selected_rows = (
        [("Male", row) for row in unsexed_piglets[:male_count_int]]
        + [("Female", row) for row in unsexed_piglets[male_count_int:total_count]]
    )
    for sex, row in selected_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        pig_updates[pig_id] = {
            "Sex": sex,
            "Updated_At": today,
            "General_Notes": _append_sex_count_note(
                row.get("General_Notes", ""),
                action_date,
                changed_by,
                notes,
            ),
        }
        selected_piglets.append({
            "pig_id": pig_id,
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "sex": sex,
        })

    rows_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_rows_updated = _try_supabase_pig_updates(pig_updates)
        if supabase_rows_updated is not None:
            rows_updated = supabase_rows_updated
            writes_to_supabase = True
        else:
            rows_updated = batch_update_rows_by_id(pig_master_sheet, pig_updates)

    return {
        "success": True,
        "action": "record_litter_piglet_sex_counts",
        "dry_run": dry_run,
        "litter_id": litter_id,
        "action_date": action_date.isoformat(),
        "male_count": male_count_int,
        "female_count": female_count_int,
        "piglet_count": total_count,
        "selected_piglets": selected_piglets,
        "pig_ids": [piglet["pig_id"] for piglet in selected_piglets],
        "rows_updated": rows_updated,
        "planned_updates": pig_updates,
        "changed_by": changed_by,
        "source": {
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Litter {litter_id} sex-count action previewed for {total_count} piglet(s)."
            if dry_run
            else f"Litter {litter_id} sex-count action saved for {total_count} piglet(s)."
        ),
        "summary": (
            f"{male_count_int} male and {female_count_int} female piglet(s) will be assigned."
            if dry_run
            else f"{male_count_int} male and {female_count_int} female piglet(s) were assigned."
        ),
        "recorded_date": action_date_sheet,
    }, 200


def _append_tag_assignment_note(existing_notes, action_date, changed_by, notes):
    note = f"Tag number assigned on {format_date_for_sheet(action_date)} by {changed_by}."
    if notes:
        note = f"{note} Notes: {notes}"
    existing = to_clean_string(existing_notes)
    return f"{existing} | {note}" if existing else note


def assign_litter_piglet_tag_numbers(
    litter_id: str,
    tag_numbers=None,
    assignments=None,
    action_date_value=None,
    changed_by: str = "web_app",
    notes: str = "",
    dry_run: bool = True,
):
    litter_id = to_clean_string(litter_id)
    action_date = parse_sheet_date(action_date_value) or datetime.now().date()
    changed_by = to_clean_string(changed_by) or "web_app"
    notes = to_clean_string(notes)
    dry_run = dry_run is True
    assignments = assignments if isinstance(assignments, list) else []
    tag_numbers = [to_clean_string(tag) for tag in (tag_numbers or []) if to_clean_string(tag)]

    errors = []
    if not litter_id:
        errors.append("Litter ID is required.")
    if not assignments and not tag_numbers:
        errors.append("Enter at least one tag number.")
    duplicate_direct_tags = sorted({tag for tag in tag_numbers if tag_numbers.count(tag) > 1})
    if duplicate_direct_tags:
        errors.append(f"Duplicate tag number(s) in this request: {', '.join(duplicate_direct_tags)}.")
    if errors:
        return {"success": False, "errors": errors}, 400

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_rows = _get_pig_master_rows()
    active_litter_piglets = [
        row for row in pig_rows
        if to_clean_string(row.get("Litter_ID", "")) == litter_id
        and to_clean_string(row.get(columns["status"], "")) == "Active"
        and to_clean_string(row.get(columns["on_farm"], "")) == "Yes"
    ]
    active_litter_piglets.sort(key=lambda row: (
        to_clean_string(row.get("Sex", "")),
        to_clean_string(row.get(columns["pig_id"], "")),
    ))
    untagged_piglets = [
        row for row in active_litter_piglets
        if not to_clean_string(row.get("Tag_Number", ""))
    ]
    untagged_by_id = {
        to_clean_string(row.get(columns["pig_id"], "")): row
        for row in untagged_piglets
        if to_clean_string(row.get(columns["pig_id"], ""))
    }

    if not active_litter_piglets:
        return {
            "success": False,
            "errors": ["No active on-farm piglets were found for this litter."],
            "litter_id": litter_id,
        }, 409

    if assignments:
        assignment_map = {}
        unknown_pig_ids = []
        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            pig_id = to_clean_string(assignment.get("pig_id", ""))
            tag_number = to_clean_string(assignment.get("tag_number", ""))
            if not pig_id and not tag_number:
                continue
            if pig_id not in untagged_by_id:
                unknown_pig_ids.append(pig_id or "(blank)")
                continue
            if tag_number:
                assignment_map[pig_id] = tag_number
        if unknown_pig_ids:
            return {
                "success": False,
                "errors": [f"These piglet rows are not active untagged piglets in this litter: {', '.join(unknown_pig_ids)}."],
                "litter_id": litter_id,
            }, 409
        missing_pig_ids = [pig_id for pig_id in untagged_by_id if pig_id not in assignment_map]
        if missing_pig_ids:
            return {
                "success": False,
                "errors": [f"Enter tag numbers for every active untagged piglet: {', '.join(missing_pig_ids)}."],
                "litter_id": litter_id,
                "untagged_piglet_count": len(untagged_piglets),
            }, 409
        selected_rows_and_tags = [(row, assignment_map[to_clean_string(row.get(columns["pig_id"], ""))]) for row in untagged_piglets]
        tag_numbers = [tag for _row, tag in selected_rows_and_tags]
    else:
        if len(tag_numbers) != len(untagged_piglets):
            return {
                "success": False,
                "errors": [
                    f"Enter exactly {len(untagged_piglets)} tag number(s) for the active untagged piglet(s). "
                    f"You entered {len(tag_numbers)}."
                ],
                "litter_id": litter_id,
                "active_piglet_count": len(active_litter_piglets),
                "untagged_piglet_count": len(untagged_piglets),
            }, 409
        selected_rows_and_tags = list(zip(untagged_piglets, tag_numbers))

    duplicate_input_tags = sorted({tag for tag in tag_numbers if tag_numbers.count(tag) > 1})
    if duplicate_input_tags:
        return {
            "success": False,
            "errors": [f"Duplicate tag number(s) in this request: {', '.join(duplicate_input_tags)}."],
            "litter_id": litter_id,
        }, 400

    existing_tags = {
        to_clean_string(row.get("Tag_Number", ""))
        for row in pig_rows
        if to_clean_string(row.get("Tag_Number", ""))
    }
    duplicate_existing_tags = [tag for tag in tag_numbers if tag in existing_tags]
    if duplicate_existing_tags:
        return {
            "success": False,
            "errors": [f"Tag number(s) already exist in PIG_MASTER: {', '.join(duplicate_existing_tags)}."],
            "litter_id": litter_id,
        }, 409

    action_date_sheet = format_date_for_sheet(action_date)
    today = format_date_for_sheet(datetime.now().date())
    pig_updates = {}
    selected_piglets = []
    for row, tag_number in selected_rows_and_tags:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        pig_updates[pig_id] = {
            "Tag_Number": tag_number,
            "Earmarked": "Yes",
            "Earmark_Date": action_date_sheet,
            "Updated_At": today,
            "General_Notes": _append_tag_assignment_note(
                row.get("General_Notes", ""),
                action_date,
                changed_by,
                notes,
            ),
        }
        selected_piglets.append({
            "pig_id": pig_id,
            "tag_number": tag_number,
            "sex": to_clean_string(row.get("Sex", "")),
        })

    rows_updated = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_rows_updated = _try_supabase_pig_updates(pig_updates)
        if supabase_rows_updated is not None:
            rows_updated = supabase_rows_updated
            writes_to_supabase = True
        else:
            rows_updated = batch_update_rows_by_id(pig_master_sheet, pig_updates)

    return {
        "success": True,
        "action": "assign_litter_piglet_tag_numbers",
        "dry_run": dry_run,
        "litter_id": litter_id,
        "action_date": action_date.isoformat(),
        "piglet_count": len(selected_piglets),
        "selected_piglets": selected_piglets,
        "pig_ids": [piglet["pig_id"] for piglet in selected_piglets],
        "tag_numbers": tag_numbers,
        "rows_updated": rows_updated,
        "planned_updates": pig_updates,
        "changed_by": changed_by,
        "source": {
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Litter {litter_id} tag assignment previewed for {len(selected_piglets)} piglet(s)."
            if dry_run
            else f"Litter {litter_id} tag numbers saved for {len(selected_piglets)} piglet(s)."
        ),
    }, 200


def record_litter_newborn_health(
    litter_id: str,
    action_date_value,
    changed_by: str = "web_app",
    earmarked: bool = False,
    antiparasitic_product_id: str = "",
    deworming_product_id: str = "",
    vaccination_product_id: str = "",
    dose=None,
    route: str = "",
    batch_lot_number: str = "",
    notes: str = "",
    dry_run: bool = True,
):
    litter_id = to_clean_string(litter_id)
    action_date = parse_sheet_date(action_date_value)
    changed_by = to_clean_string(changed_by) or "web_app"
    antiparasitic_product_id = to_clean_string(antiparasitic_product_id)
    deworming_product_id = to_clean_string(deworming_product_id)
    vaccination_product_id = to_clean_string(vaccination_product_id)
    route = to_clean_string(route)
    batch_lot_number = to_clean_string(batch_lot_number)
    notes = to_clean_string(notes)
    dose_value = to_float(dose)
    dry_run = dry_run is True

    errors = []
    if not litter_id:
        errors.append("Litter ID is required.")
    if not action_date:
        errors.append("A valid action date is required.")
    if not changed_by:
        errors.append("changed_by is required.")
    if not earmarked and not antiparasitic_product_id and not deworming_product_id and not vaccination_product_id:
        errors.append("Select earmarking, antiparasitic/deworming product, or vaccination product before saving.")
    if errors:
        return {"success": False, "errors": errors}, 400

    products = {
        product["product_id"]: product
        for product in get_products()
    }
    if antiparasitic_product_id and antiparasitic_product_id not in products:
        errors.append(f"Antiparasitic product '{antiparasitic_product_id}' was not found or is inactive.")
    if deworming_product_id and deworming_product_id not in products:
        errors.append(f"Deworming product '{deworming_product_id}' was not found or is inactive.")
    if vaccination_product_id and vaccination_product_id not in products:
        errors.append(f"Vaccination product '{vaccination_product_id}' was not found or is inactive.")
    if errors:
        return {"success": False, "errors": errors}, 400

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    medical_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_rows = _get_pig_master_rows()
    active_piglets = [
        row for row in pig_rows
        if to_clean_string(row.get("Litter_ID", "")) == litter_id
        and to_clean_string(row.get(columns["status"], "")) == "Active"
        and to_clean_string(row.get(columns["on_farm"], "")) == "Yes"
    ]

    if not active_piglets:
        return {
            "success": False,
            "errors": ["No active on-farm piglets were found for this litter."],
            "litter_id": litter_id,
        }, 409

    if earmarked:
        headers = set()
        for row in pig_rows:
            headers.update(row.keys())
        missing_fields = [field for field in LITTER_HEALTH_EARMARK_FIELDS if field not in headers]
        if missing_fields:
            return {
                "success": False,
                "errors": [
                    "PIG_MASTER is missing earmark columns: " + ", ".join(missing_fields) + "."
                ],
                "missing_columns": missing_fields,
                "source": {
                    "writes_to_sheets": False,
                    "writes_to_supabase": False,
                },
            }, 409

    action_date_sheet = format_date_for_sheet(action_date)
    today = format_date_for_sheet(datetime.now().date())
    pig_updates = {}
    treatment_rows = []

    for row in active_piglets:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if earmarked:
            pig_updates[pig_id] = {
                "Earmarked": "Yes",
                "Earmark_Date": action_date_sheet,
                "Updated_At": today,
            }

        if antiparasitic_product_id:
            antiparasitic_product = products[antiparasitic_product_id]
            treatment_rows.append(_build_litter_health_treatment_row(
                pig_id=pig_id,
                action_date=action_date,
                treatment_type=_litter_health_treatment_type_for_product(antiparasitic_product, default_type="Antiparasitic"),
                product=antiparasitic_product,
                dose_value=dose_value,
                route=route,
                batch_lot_number=batch_lot_number,
                given_by=changed_by,
                notes=notes,
                litter_id=litter_id,
            ))
        if deworming_product_id:
            deworming_product = products[deworming_product_id]
            treatment_rows.append(_build_litter_health_treatment_row(
                pig_id=pig_id,
                action_date=action_date,
                treatment_type=_litter_health_treatment_type_for_product(deworming_product, default_type="Deworming"),
                product=deworming_product,
                dose_value=dose_value,
                route=route,
                batch_lot_number=batch_lot_number,
                given_by=changed_by,
                notes=notes,
                litter_id=litter_id,
            ))
        if vaccination_product_id:
            treatment_rows.append(_build_litter_health_treatment_row(
                pig_id=pig_id,
                action_date=action_date,
                treatment_type="Vaccination",
                product=products[vaccination_product_id],
                dose_value=dose_value,
                route=route,
                batch_lot_number=batch_lot_number,
                given_by=changed_by,
                notes=notes,
                litter_id=litter_id,
            ))

    pig_rows_updated = 0
    treatment_rows_created = 0
    writes_to_supabase = False
    if not dry_run:
        supabase_available = farm_supabase_write_service.farm_supabase_writes_available()
        if supabase_available:
            pig_rows_updated = _try_supabase_pig_updates(pig_updates) if pig_updates else 0
            if pig_rows_updated is None:
                pig_rows_updated = 0
            for row_values in treatment_rows:
                farm_supabase_write_service.insert_medical_event_from_sheet_row(row_values)
                treatment_rows_created += 1
            writes_to_supabase = True
        else:
            pig_rows_updated = batch_update_rows_by_id(pig_master_sheet, pig_updates) if pig_updates else 0
            for row_values in treatment_rows:
                append_row(medical_log_sheet, row_values)
                treatment_rows_created += 1

    return {
        "success": True,
        "action": "record_litter_newborn_health",
        "dry_run": dry_run,
        "litter_id": litter_id,
        "piglet_count": len(active_piglets),
        "pig_ids": [to_clean_string(row.get(columns["pig_id"], "")) for row in active_piglets],
        "earmarked": earmarked,
        "treatment_rows_planned": len(treatment_rows),
        "pig_rows_updated": pig_rows_updated,
        "treatment_rows_created": treatment_rows_created,
        "planned_pig_updates": pig_updates,
        "planned_treatment_rows": treatment_rows,
        "source": {
            "writes_to_sheets": (not dry_run) and not writes_to_supabase,
            "writes_to_supabase": writes_to_supabase,
        },
        "message": (
            f"Litter {litter_id} newborn health action previewed for {len(active_piglets)} piglet(s)."
            if dry_run
            else f"Litter {litter_id} newborn health action saved for {len(active_piglets)} piglet(s)."
        ),
    }, 200


def _build_litter_health_treatment_row(
    pig_id,
    action_date,
    treatment_type,
    product,
    dose_value,
    route,
    batch_lot_number,
    given_by,
    notes,
    litter_id,
):
    withdrawal_days = product.get("default_withdrawal_days")
    withdrawal_days_int = int(withdrawal_days) if withdrawal_days not in (None, "") else ""
    withdrawal_end_date = ""
    if withdrawal_days_int != "":
        withdrawal_end_date = action_date.fromordinal(action_date.toordinal() + withdrawal_days_int)

    dose = dose_value if dose_value is not None else product.get("default_dose")
    medical_notes = f"Litter {litter_id} newborn health action."
    if notes:
        medical_notes = f"{medical_notes} Notes: {notes}"

    return [
        generate_medical_log_id(),
        pig_id,
        format_date_for_sheet(action_date),
        treatment_type,
        product["product_id"],
        product["product_name"],
        dose if dose is not None else "",
        product.get("dose_unit", ""),
        route,
        f"{treatment_type} during litter newborn health action",
        batch_lot_number,
        withdrawal_days_int,
        format_date_for_sheet(withdrawal_end_date),
        given_by,
        "No",
        "",
        medical_notes,
        format_date_for_sheet(action_date),
    ]


def _litter_health_treatment_type_for_product(product, default_type):
    category = to_clean_string(product.get("product_category", "")).lower()
    if "vacc" in category:
        return "Vaccination"
    if "deworm" in category:
        return "Deworming"
    if "parasite" in category or "antiparasitic" in category:
        return "Antiparasitic"
    return default_type


def get_sales_stock_summary():
    supabase_result = _sales_stock_summary_from_supabase_allocation()
    if supabase_result is not None:
        return supabase_result

    rows = get_all_records("SALES_STOCK_SUMMARY")
    records = []

    for row in rows:
        sale_category = to_clean_string(row.get("Sale_Category", ""))
        weight_band = to_clean_string(row.get("Weight_Band", ""))

        if not sale_category or not weight_band:
            continue

        records.append({
            "sale_category": sale_category,
            "category_code": to_clean_string(row.get("Category_Code", "")),
            "age_range": to_clean_string(row.get("Age_Range", "")),
            "weight_band": weight_band,
            "qty_available": to_float(row.get("Qty_Available", "")) or 0,
            "male_qty": to_float(row.get("Male_Qty", "")) or 0,
            "female_qty": to_float(row.get("Female_Qty", "")) or 0,
            "castrated_male_qty": to_float(row.get("Castrated_Male_Qty", "")) or 0,
            "price_range": to_clean_string(row.get("Price_Range", "")),
            "status": to_clean_string(row.get("Status", "")),
        })

    return records


def get_sales_stock_totals():
    supabase_result = _sales_stock_totals_from_supabase_allocation()
    if supabase_result is not None:
        return supabase_result

    rows = get_all_records("SALES_STOCK_TOTALS")
    records = []

    for row in rows:
        sale_category = to_clean_string(row.get("Sale_Category", ""))

        if not sale_category:
            continue

        records.append({
            "sale_category": sale_category,
            "category_code": to_clean_string(row.get("Category_Code", "")),
            "age_range": to_clean_string(row.get("Age_Range", "")),
            "weight_range": to_clean_string(row.get("Weight_Range", "")),
            "qty_available": to_float(row.get("Qty_Available", "")) or 0,
            "male_qty": to_float(row.get("Male_Qty", "")) or 0,
            "female_qty": to_float(row.get("Female_Qty", "")) or 0,
            "castrated_male_qty": to_float(row.get("Castrated_Male_Qty", "")) or 0,
            "price_range": to_clean_string(row.get("Price_Range", "")),
            "status": to_clean_string(row.get("Status", "")),
        })

    return records


def _sex_counts_for_pigs(pigs):
    counts = {"male": 0, "female": 0, "castrated_male": 0}
    for pig in pigs:
        sex = to_clean_string(pig.get("sex", ""))
        if sex == "Male":
            counts["male"] += 1
        elif sex == "Female":
            counts["female"] += 1
        elif sex == "Castrated_Male":
            counts["castrated_male"] += 1
    return counts


def _sales_category_for_meat_ready(classification):
    category_key = classification.get("category_key", "")
    if category_key == "meat_window_candidate":
        return "Meat Window Candidate", "meat_window_candidate", "Ready for meat planning"
    if category_key == "abattoir_cull_candidate":
        return "Ready for Slaughter", "abattoir_cull_candidate", "Ready for abattoir/cull planning"
    if category_key == "live_sale_candidate":
        return "Live Sale Candidate", "live_sale_candidate", "Review for live sale"
    if category_key == "slow_grower_review":
        return "Slow Grower Review", "slow_grower_review", "Review before continued feeding"
    if category_key == "hold_grow_longer":
        return "Hold / Grow Longer", "hold_grow_longer", "Not ready yet"
    return "Excluded / No Reliable Value Yet", "excluded", "Excluded from sales availability"


def _allocation_is_supabase(allocation):
    return isinstance(allocation, dict) and allocation.get("source") == "supabase_canonical"


def _sales_stock_summary_from_supabase_allocation():
    allocation = get_pig_allocation_readiness()
    if not _allocation_is_supabase(allocation):
        return None

    grouped = {}
    for pig in allocation.get("pigs", []) if isinstance(allocation.get("pigs"), list) else []:
        classification = _meat_ready_classification(pig)
        sale_category, category_code, status = _sales_category_for_meat_ready(classification)
        if category_code == "excluded":
            continue
        key = (sale_category, pig.get("weight_band") or "Unknown")
        group = grouped.setdefault(key, {
            "sale_category": sale_category,
            "category_code": category_code,
            "age_range": "",
            "weight_band": pig.get("weight_band") or "Unknown",
            "pigs": [],
            "price_range": "pricing not configured",
            "status": status,
        })
        group["pigs"].append(pig)

    records = []
    for group in grouped.values():
        sex_counts = _sex_counts_for_pigs(group["pigs"])
        records.append({
            "sale_category": group["sale_category"],
            "category_code": group["category_code"],
            "age_range": group["age_range"],
            "weight_band": group["weight_band"],
            "qty_available": len(group["pigs"]),
            "male_qty": sex_counts["male"],
            "female_qty": sex_counts["female"],
            "castrated_male_qty": sex_counts["castrated_male"],
            "price_range": group["price_range"],
            "status": group["status"],
            "source": "supabase_allocation_readiness",
        })

    records.sort(key=lambda item: (item["sale_category"], item["weight_band"]))
    return records


def _sales_stock_totals_from_supabase_allocation():
    allocation = get_pig_allocation_readiness()
    if not _allocation_is_supabase(allocation):
        return None

    grouped = {}
    for pig in allocation.get("pigs", []) if isinstance(allocation.get("pigs"), list) else []:
        classification = _meat_ready_classification(pig)
        sale_category, category_code, status = _sales_category_for_meat_ready(classification)
        if category_code == "excluded":
            continue
        group = grouped.setdefault(sale_category, {
            "sale_category": sale_category,
            "category_code": category_code,
            "age_range": "",
            "weight_range": "",
            "pigs": [],
            "price_range": "pricing not configured",
            "status": status,
        })
        group["pigs"].append(pig)

    records = []
    for group in grouped.values():
        weights = [
            pig.get("latest_weight_kg")
            for pig in group["pigs"]
            if pig.get("latest_weight_kg") is not None
        ]
        sex_counts = _sex_counts_for_pigs(group["pigs"])
        weight_range = ""
        if weights:
            weight_range = f"{min(weights):g}-{max(weights):g} kg" if min(weights) != max(weights) else f"{weights[0]:g} kg"
        records.append({
            "sale_category": group["sale_category"],
            "category_code": group["category_code"],
            "age_range": group["age_range"],
            "weight_range": weight_range,
            "qty_available": len(group["pigs"]),
            "male_qty": sex_counts["male"],
            "female_qty": sex_counts["female"],
            "castrated_male_qty": sex_counts["castrated_male"],
            "price_range": group["price_range"],
            "status": group["status"],
            "source": "supabase_allocation_readiness",
        })

    records.sort(key=lambda item: item["sale_category"])
    return records


def get_parent_options():
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_parent_options)
    if supabase_result is not None:
        return supabase_result

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    rows = get_all_records(sheet_name)
    pen_lookup = _build_pen_lookup()

    mother_options = [{
        "pig_id": "Unknown",
        "tag_number": "Unknown",
        "sex": "Female",
        "status": "Active",
        "purpose": "Breeding",
        "current_pen_id": "",
    }]
    father_options = [{
        "pig_id": "Unknown",
        "tag_number": "Unknown",
        "sex": "Male",
        "status": "Active",
        "purpose": "Breeding",
        "current_pen_id": "",
    }]

    for row in rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        tag_number = to_clean_string(row.get(columns["tag_number"], ""))
        sex = to_clean_string(row.get("Sex", ""))
        status = to_clean_string(row.get(columns["status"], ""))
        purpose = to_clean_string(row.get("Purpose", ""))
        current_pen_id = to_clean_string(row.get(columns["current_pen_id"], ""))

        if not pig_id:
            continue

        option = {
            "pig_id": pig_id,
            "tag_number": tag_number or pig_id,
            "sex": sex,
            "status": status,
            "purpose": purpose,
            "current_pen_id": current_pen_id,
            "current_pen_name": _pen_name_for_id(pen_lookup, current_pen_id),
        }

        if sex == "Female" and status == "Active" and purpose == "Breeding":
            mother_options.append(option)

        if sex in ("Male", "Castrated_Male") and status == "Active" and purpose == "Breeding":
            father_options.append(option)

    return {
        "mothers": mother_options,
        "fathers": father_options,
    }


def get_active_pigs():
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_active_pigs)
    if supabase_result is not None:
        return supabase_result

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)
    pen_lookup = _build_pen_lookup()

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
                "current_pen_id": to_clean_string(row.get(columns["current_pen_id"], "")),
                "current_pen_name": _pen_name_for_id(
                    pen_lookup,
                    row.get(columns["current_pen_id"], ""),
                ),
            })

    return active_pigs


def get_sales_availability():
    supabase_result = _sales_availability_from_supabase_allocation()
    if supabase_result is not None:
        return supabase_result

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["sales_availability"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)
    sales_rows = []

    for row in rows:
        sales_rows.append({
            "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "sex": to_clean_string(row.get(columns["sex"], "")),
            "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
            "age_days": row.get(columns["age_days"], ""),
            "current_weight_kg": to_float(row.get(columns["current_weight"], "")),
            "last_weight_date": format_date_for_json(row.get(columns["last_weight_date"], "")),
            "average_daily_gain_kg": to_float(row.get(columns["average_daily_gain"], "")),
            "calculated_stage": to_clean_string(row.get(columns["calculated_stage"], "")),
            "weight_band": to_clean_string(row.get(columns["weight_band"], "")),
            "current_pen_id": to_clean_string(row.get(columns["current_pen_id"], "")),
            "status": to_clean_string(row.get(columns["status"], "")),
            "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
            "withdrawal_clear": to_clean_string(row.get(columns["withdrawal_clear"], "")),
            "reserved_status": to_clean_string(row.get(columns["reserved_status"], "")),
            "reserved_for_order_id": to_clean_string(row.get(columns["reserved_for_order_id"], "")),
            "available_for_sale": to_clean_string(row.get(columns["available_for_sale"], "")),
            "sale_category": to_clean_string(row.get(columns["sale_category"], "")),
            "suggested_price_category": to_clean_string(row.get(columns["suggested_price_category"], "")),
            "sales_notes": to_clean_string(row.get(columns["sales_notes"], "")),
        })

    return sales_rows


def _sales_availability_from_supabase_allocation():
    allocation = get_pig_allocation_readiness()
    if not _allocation_is_supabase(allocation):
        return None

    sales_rows = []
    for pig in allocation.get("pigs", []) if isinstance(allocation.get("pigs"), list) else []:
        eligibility = _live_stock_sale_eligibility(pig)
        sales_rows.append({
            "pig_id": pig.get("pig_id", ""),
            "tag_number": pig.get("tag_number", ""),
            "sex": pig.get("sex", ""),
            "date_of_birth": pig.get("birth_date", ""),
            "age_days": pig.get("age_days"),
            "current_weight_kg": pig.get("latest_weight_kg"),
            "last_weight_date": pig.get("latest_weight_date", ""),
            "average_daily_gain_kg": pig.get("average_daily_gain_kg"),
            "calculated_stage": pig.get("calculated_stage", ""),
            "weight_band": pig.get("weight_band", ""),
            "current_pen_id": pig.get("current_pen_id", ""),
            "status": pig.get("status", ""),
            "on_farm": pig.get("on_farm", ""),
            "withdrawal_clear": "",
            "reserved_status": pig.get("reserved_status", ""),
            "reserved_for_order_id": pig.get("reserved_for_order_id", ""),
            "purpose": pig.get("purpose", ""),
            "available_for_sale": "Yes" if eligibility["eligible"] else "No",
            "live_stock_sale_eligible": eligibility["eligible"],
            "live_stock_sale_reason": eligibility["reason"],
            "sale_category": eligibility["sale_category"],
            "suggested_price_category": eligibility["suggested_price_category"],
            "sales_notes": eligibility["status"],
            "source": "supabase_allocation_readiness",
        })

    return sales_rows


def _live_stock_sale_eligibility(pig):
    status = to_clean_string(pig.get("status", ""))
    normalized_status = status.lower()
    on_farm = to_clean_string(pig.get("on_farm", "")).lower()
    purpose = to_clean_string(pig.get("purpose", ""))
    normalized_purpose = purpose.lower().replace("-", "_").replace(" ", "_")
    reserved_status = to_clean_string(pig.get("reserved_status", "")).lower()
    reserved_for_order_id = to_clean_string(pig.get("reserved_for_order_id", ""))
    animal_type = to_clean_string(pig.get("animal_type", ""))
    calculated_stage = to_clean_string(pig.get("calculated_stage", ""))
    latest_weight_kg = to_float(pig.get("latest_weight_kg"))
    weight_band = to_clean_string(pig.get("weight_band", ""))
    wean_date = to_clean_string(pig.get("wean_date", ""))

    if normalized_status != "active" or normalized_status in {value.lower() for value in TERMINAL_PIG_STATUSES}:
        return _live_stock_sale_block("not_active", "Pig is not active.")
    if on_farm not in {"yes", "true", "1", "on farm"}:
        return _live_stock_sale_block("not_on_farm", "Pig is not currently on farm.")
    if reserved_status == "reserved" or reserved_for_order_id:
        return _live_stock_sale_block("reserved", "Pig is already reserved or linked to an order.")
    if normalized_purpose != LIVE_STOCK_SALE_PURPOSE:
        return _live_stock_sale_block("not_sale_purpose", "Only pigs with Purpose = Sale may enter SAM Live stock sales.")
    if _is_breeding_or_retained_stage(animal_type, calculated_stage):
        return _live_stock_sale_block("breeding_or_retained", "Breeding and retained animals are excluded from SAM Live stock sales.")
    if latest_weight_kg is None:
        return _live_stock_sale_block("missing_weight", "Latest weight is required before SAM can quote live stock.")
    if latest_weight_kg < LIVE_STOCK_MIN_SALE_WEIGHT_KG:
        return _live_stock_sale_block("below_sale_weight", "Newborn or very light piglets are not sold while still with the sow.")
    if _is_unweaned_newborn_or_suckling(animal_type, calculated_stage, wean_date):
        return _live_stock_sale_block("not_weaned", "Piglets still with the sow are not sold through SAM Live.")

    category, derived_band = _live_stock_sale_category_for_weight(latest_weight_kg)
    if not category:
        return _live_stock_sale_block("price_band_missing", "No live-stock price band matched the latest weight.")
    effective_band = weight_band or derived_band
    return {
        "eligible": True,
        "reason": "Purpose = Sale, active/on-farm, not reserved, weaned or sale-stage, and current weight maps to a live-stock price band.",
        "status": "SAM Live sale-ready",
        "sale_category": category,
        "suggested_price_category": f"{category}|{effective_band}",
    }


def _live_stock_sale_block(code, reason):
    return {
        "eligible": False,
        "reason": reason,
        "status": f"Not SAM Live sale-ready: {code}",
        "sale_category": "Not SAM Live Sale Ready",
        "suggested_price_category": code,
    }


def _is_breeding_or_retained_stage(animal_type, calculated_stage):
    text = f"{animal_type} {calculated_stage}".lower()
    return any(token in text for token in ("sow", "boar", "breeding", "replacement", "retained"))


def _is_unweaned_newborn_or_suckling(animal_type, calculated_stage, wean_date):
    text = f"{animal_type} {calculated_stage}".lower()
    return not wean_date and any(token in text for token in ("newborn", "suckling", "lactating"))


def _live_stock_sale_category_for_weight(weight_kg):
    weight = to_float(weight_kg)
    if weight is None:
        return "", ""
    if 2 <= weight < 5:
        return "Young Piglets", "2_to_4_Kg"
    if 5 <= weight < 7:
        return "Young Piglets", "5_to_6_Kg"
    if 7 <= weight < 10:
        return "Weaner Piglets", "7_to_9_Kg"
    if 10 <= weight < 15:
        return "Weaner Piglets", "10_to_14_Kg"
    if 15 <= weight < 20:
        return "Weaner Piglets", "15_to_19_Kg"
    if 20 <= weight < 25:
        return "Grower Pigs", "20_to_24_Kg"
    if 25 <= weight < 30:
        return "Grower Pigs", "25_to_29_Kg"
    if 30 <= weight < 35:
        return "Grower Pigs", "30_to_34_Kg"
    if 35 <= weight < 40:
        return "Grower Pigs", "35_to_39_Kg"
    if 40 <= weight < 45:
        return "Grower Pigs", "40_to_44_Kg"
    if 45 <= weight < 50:
        return "Grower Pigs", "45_to_49_Kg"
    if 50 <= weight < 55:
        return "Finisher Pigs", "50_to_54_Kg"
    if 55 <= weight < 60:
        return "Finisher Pigs", "55_to_59_Kg"
    if 60 <= weight < 65:
        return "Finisher Pigs", "60_to_64_Kg"
    if 65 <= weight < 70:
        return "Finisher Pigs", "65_to_69_Kg"
    if 70 <= weight < 75:
        return "Finisher Pigs", "70_to_74_Kg"
    if 75 <= weight < 80:
        return "Finisher Pigs", "75_to_79_Kg"
    if 80 <= weight < 85:
        return "Ready for Slaughter", "80_to_84_Kg"
    if 85 <= weight < 90:
        return "Ready for Slaughter", "85_to_89_Kg"
    if 90 <= weight < 95:
        return "Ready for Slaughter", "90_to_94_Kg"
    return "", ""


def _latest_weights_by_pig(weight_rows, columns):
    latest = {}
    for row in weight_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
        weight_kg = to_float(row.get(columns["weight_kg"], ""))

        if not pig_id or not weight_date or weight_kg is None:
            continue

        current = latest.get(pig_id)
        if not current or weight_date > current["weight_date"]:
            latest[pig_id] = {
                "weight_date": weight_date,
                "weight_kg": weight_kg,
                "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
            }

    return latest


def _sales_availability_by_pig(rows, columns):
    lookup = {}
    for row in rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if not pig_id:
            continue
        lookup[pig_id] = {
            "available_for_sale": to_clean_string(row.get(columns["available_for_sale"], "")),
            "reserved_status": to_clean_string(row.get(columns["reserved_status"], "")),
            "reserved_for_order_id": to_clean_string(row.get(columns["reserved_for_order_id"], "")),
            "sale_category": to_clean_string(row.get(columns["sale_category"], "")),
            "suggested_price_category": to_clean_string(row.get(columns["suggested_price_category"], "")),
            "sales_notes": to_clean_string(row.get(columns["sales_notes"], "")),
        }
    return lookup


def _pig_sort_key(value):
    raw = to_clean_string(value)
    if raw.isdigit():
        return (0, int(raw))
    return (1, raw)


def _litter_overview_by_id(rows):
    lookup = {}
    for row in rows:
        litter_id = to_clean_string(row.get("Litter_ID", ""))
        if litter_id:
            lookup[litter_id] = row
    return lookup


def _litter_quality_summary(litter_row, settings=None):
    settings = settings or _allocation_settings()
    if not litter_row:
        return {
            "litter_quality": "Unknown",
            "litter_quality_reason": "No litter overview row found.",
            "litter_survival_rate": None,
            "born_alive": None,
            "weaned_count": None,
            "sow_pig_id": "",
            "sow_tag_number": "",
            "boar_pig_id": "",
            "boar_tag_number": "",
        }

    born_alive = to_float(litter_row.get("Born_Alive", ""))
    weaned_count = to_float(litter_row.get("Weaned_Count", ""))
    survival_rate = None
    if born_alive and born_alive > 0 and weaned_count is not None:
        survival_rate = round(weaned_count / born_alive, 3)

    if survival_rate is None:
        quality = "Unknown"
        reason = "Missing born-alive or weaned count."
    elif survival_rate >= settings["good_litter_survival_rate"]:
        quality = "Good"
        reason = f"Survival to weaning is {round(survival_rate * 100)}%."
    else:
        quality = "Review"
        reason = f"Survival to weaning is {round(survival_rate * 100)}%, below the first good-litter threshold."

    return {
        "litter_quality": quality,
        "litter_quality_reason": reason,
        "litter_survival_rate": survival_rate,
        "born_alive": born_alive,
        "weaned_count": weaned_count,
        "sow_pig_id": to_clean_string(litter_row.get("Sow_Pig_ID", "")),
        "sow_tag_number": to_clean_string(litter_row.get("Sow_Tag_Number", "")),
        "boar_pig_id": to_clean_string(litter_row.get("Boar_Pig_ID", "")),
        "boar_tag_number": to_clean_string(litter_row.get("Boar_Tag_Number", "")),
    }


def _growth_class_for_adg(average_daily_gain, settings=None):
    settings = settings or _allocation_settings()
    if average_daily_gain is None:
        return "Unknown", "Missing enough weight/age history to calculate growth rate."
    if average_daily_gain < settings["extremely_slow_grower_adg_kg_day"]:
        return "Extremely Slow", f"Lifetime ADG is {average_daily_gain:.3f} kg/day, below {settings['extremely_slow_grower_adg_kg_day']:.3f} kg/day."
    if average_daily_gain < settings["slow_grower_adg_kg_day"]:
        return "Slow", f"Lifetime ADG is {average_daily_gain:.3f} kg/day, below {settings['slow_grower_adg_kg_day']:.3f} kg/day."
    if average_daily_gain < settings["steady_grower_adg_kg_day"]:
        return "Below Target", f"Lifetime ADG is {average_daily_gain:.3f} kg/day, below {settings['steady_grower_adg_kg_day']:.3f} kg/day."
    if average_daily_gain < settings["good_grower_adg_kg_day"]:
        return "Steady", f"Lifetime ADG is {average_daily_gain:.3f} kg/day, below {settings['good_grower_adg_kg_day']:.3f} kg/day."
    if average_daily_gain < settings["exceptional_grower_adg_kg_day"]:
        return "Good", f"Lifetime ADG is {average_daily_gain:.3f} kg/day, below the {settings['exceptional_grower_adg_kg_day']:.3f} kg/day target."
    return "Exceptional", f"Lifetime ADG is {average_daily_gain:.3f} kg/day, at or above the {settings['exceptional_grower_adg_kg_day']:.3f} kg/day target."


def _estimated_target_date(current_weight_kg, target_weight_kg, daily_gain_kg, basis_date, today):
    if current_weight_kg is None or daily_gain_kg is None or daily_gain_kg <= 0 or not basis_date:
        return {
            "target_weight_kg": target_weight_kg,
            "estimated_date": "",
            "days_until": None,
            "status": "Unknown",
        }

    if current_weight_kg >= target_weight_kg:
        return {
            "target_weight_kg": target_weight_kg,
            "estimated_date": today.isoformat(),
            "days_until": 0,
            "status": "Ready now",
        }

    days_needed = math.ceil((target_weight_kg - current_weight_kg) / daily_gain_kg)
    estimated_date = basis_date + timedelta(days=days_needed)
    return {
        "target_weight_kg": target_weight_kg,
        "estimated_date": estimated_date.isoformat(),
        "days_until": (estimated_date - today).days,
        "status": "Estimated",
    }


def _readiness_timing(growth, today, settings=None):
    settings = settings or _allocation_settings()
    latest_weight_kg = growth.get("latest_weight_kg")
    daily_gain = growth.get("average_daily_gain_kg")
    latest_weight_date = growth.get("latest_weight_date")

    meat_ready = _estimated_target_date(latest_weight_kg, settings["meat_target_min_kg"], daily_gain, latest_weight_date, today)
    slaughter_ready = _estimated_target_date(latest_weight_kg, settings["slaughter_target_min_kg"], daily_gain, latest_weight_date, today)

    if latest_weight_kg is None:
        meat_status = "Unknown"
    elif latest_weight_kg < settings["meat_target_min_kg"]:
        meat_status = "Before meat window"
    elif latest_weight_kg < settings["meat_target_max_kg"]:
        meat_status = "In meat window"
    else:
        meat_status = "Past meat window"

    if latest_weight_kg is None:
        slaughter_status = "Unknown"
    elif latest_weight_kg < settings["slaughter_target_min_kg"]:
        slaughter_status = "Before abattoir window"
    elif settings.get("slaughter_target_max_kg") is None or latest_weight_kg <= settings["slaughter_target_max_kg"]:
        slaughter_status = "In abattoir window"
    else:
        slaughter_status = "Past abattoir window"

    return {
        "meat_window_status": meat_status,
        "estimated_meat_ready_date": meat_ready["estimated_date"],
        "days_until_meat_ready": meat_ready["days_until"],
        "meat_target_min_kg": settings["meat_target_min_kg"],
        "meat_target_max_kg": settings["meat_target_max_kg"],
        "abattoir_window_status": slaughter_status,
        "estimated_abattoir_ready_date": slaughter_ready["estimated_date"],
        "days_until_abattoir_ready": slaughter_ready["days_until"],
        "abattoir_target_min_kg": settings["slaughter_target_min_kg"],
        "abattoir_target_max_kg": settings["slaughter_target_max_kg"],
    }


def _weight_window_label(min_kg, max_kg=None, *, upper_exclusive=False, upper_unbounded=False):
    if upper_unbounded or max_kg is None:
        return f"{min_kg:g} kg+"
    separator = "-<" if upper_exclusive else "-"
    return f"{min_kg:g}{separator}{max_kg:g} kg"

def _recommended_outlet_action(bucket, growth, timing, litter_quality):
    growth_class = growth.get("growth_class", "Unknown")
    meat_status = timing.get("meat_window_status", "Unknown")
    abattoir_status = timing.get("abattoir_window_status", "Unknown")

    if bucket == "Allocated":
        return {
            "outlet_priority": "Already Allocated",
            "recommended_action": "Do not market. Pig is already linked or reserved.",
            "marketing_readiness": "Blocked",
        }
    if bucket == "Exited":
        return {
            "outlet_priority": "Exited",
            "recommended_action": "No sale action. Pig is no longer active/on farm.",
            "marketing_readiness": "Closed",
        }
    if bucket in {"Needs Data", "Needs Classification"}:
        return {
            "outlet_priority": "Fix Data First",
            "recommended_action": "Complete missing data/classification before selling or marketing.",
            "marketing_readiness": "Not Ready",
        }
    if bucket == "Retain / Breeding Candidate":
        return {
            "outlet_priority": "Breeding Review",
            "recommended_action": "Review for retention before offering as meat or slaughter.",
            "marketing_readiness": "Internal Review",
        }
    if growth_class in {"Extremely Slow", "Slow"}:
        return {
            "outlet_priority": "Livestock Sale",
            "recommended_action": "Prepare for livestock sale as soon as practical to reduce feed cost.",
            "marketing_readiness": "Ready For Listing",
        }
    if bucket == "Meat Candidate" or meat_status == "In meat window":
        return {
            "outlet_priority": "Meat Preorder",
            "recommended_action": "Prioritize for meat preorder marketing before the pig passes the meat window.",
            "marketing_readiness": "Ready For Interest",
        }
    if meat_status == "Past meat window" or bucket == "Slaughter Candidate" or abattoir_status == "In abattoir window":
        return {
            "outlet_priority": "Abattoir Slaughter",
            "recommended_action": "Plan for abattoir/slaughter unless a better confirmed sale exists.",
            "marketing_readiness": "Internal Planning",
        }
    if bucket == "Growing":
        return {
            "outlet_priority": "Keep Growing",
            "recommended_action": "Monitor growth and wait for meat, abattoir, or livestock trigger.",
            "marketing_readiness": "Not Ready",
        }

    return {
        "outlet_priority": "Review",
        "recommended_action": "Review manually before marketing or allocation.",
        "marketing_readiness": "Review",
    }


def _suggested_purpose_signal(bucket, outlet_action, growth, timing, litter_quality):
    if bucket == "Allocated":
        return {
            "suggested_purpose": "Already Allocated",
            "suggested_purpose_reason": "Pig is already linked or reserved; do not change purpose from this view.",
            "suggested_purpose_confidence": "High",
        }
    if bucket == "Exited":
        return {
            "suggested_purpose": "Closed",
            "suggested_purpose_reason": "Pig is no longer active/on farm.",
            "suggested_purpose_confidence": "High",
        }
    if bucket == "Needs Data":
        return {
            "suggested_purpose": "Needs Review",
            "suggested_purpose_reason": "Complete missing data or confirm classification before assigning a business purpose.",
            "suggested_purpose_confidence": "Low",
        }

    if bucket == "Needs Classification":
        has_wean_context = bool(growth.get("wean_date") and growth.get("wean_weight_kg") is not None)
        confidence = "Medium" if has_wean_context else "Low"
        growth_class = growth.get("growth_class", "Unknown")
        latest_weight_kg = growth.get("latest_weight_kg")

        if growth_class in {"Good", "Exceptional"} and litter_quality.get("litter_quality") == "Good":
            return {
                "suggested_purpose": "Breeding Review",
                "suggested_purpose_reason": "Purpose is unknown, but growth and litter quality justify reviewing retention before meat, slaughter, or livestock sale.",
                "suggested_purpose_confidence": confidence,
            }
        if growth_class in {"Extremely Slow", "Slow"}:
            return {
                "suggested_purpose": "Livestock Sale",
                "suggested_purpose_reason": "Purpose is unknown and growth is slow; review for livestock sale instead of long grow-out if condition and market fit.",
                "suggested_purpose_confidence": confidence,
            }
        if latest_weight_kg is not None and timing.get("meat_window_status") == "In meat window":
            return {
                "suggested_purpose": "Meat",
                "suggested_purpose_reason": "Purpose is unknown, but weight is in the meat window; review for preorder demand before fallback outlets.",
                "suggested_purpose_confidence": confidence,
            }
        if latest_weight_kg is not None and timing.get("abattoir_window_status") in {"In abattoir window", "Past abattoir window"}:
            return {
                "suggested_purpose": "Abattoir Slaughter",
                "suggested_purpose_reason": "Purpose is unknown, but weight is in or past the abattoir planning window.",
                "suggested_purpose_confidence": confidence,
            }
        return {
            "suggested_purpose": "Grow Out",
            "suggested_purpose_reason": "Purpose is unknown; current data supports keeping this pig growing until a clearer outlet or breeding signal appears.",
            "suggested_purpose_confidence": confidence,
        }
    if bucket == "Retain / Breeding Candidate":
        return {
            "suggested_purpose": "Breeding Review",
            "suggested_purpose_reason": "Growth and litter quality justify reviewing retention before meat, slaughter, or livestock sale.",
            "suggested_purpose_confidence": "Medium",
        }
    if bucket == "Livestock Candidate" or outlet_action.get("outlet_priority") == "Livestock Sale":
        return {
            "suggested_purpose": "Livestock Sale",
            "suggested_purpose_reason": "Slow-growth or sale-availability signal suggests moving this pig as livestock.",
            "suggested_purpose_confidence": "Medium",
        }
    if bucket == "Meat Candidate" or outlet_action.get("outlet_priority") == "Meat Preorder":
        return {
            "suggested_purpose": "Meat",
            "suggested_purpose_reason": "Pig is in or near the meat window and should be prioritised for preorder demand.",
            "suggested_purpose_confidence": "Medium",
        }
    if bucket == "Slaughter Candidate" or outlet_action.get("outlet_priority") == "Abattoir Slaughter":
        return {
            "suggested_purpose": "Abattoir Slaughter",
            "suggested_purpose_reason": "Pig is in or past the abattoir planning window, or has missed the meat opportunity.",
            "suggested_purpose_confidence": "Medium",
        }
    if bucket == "Growing":
        return {
            "suggested_purpose": "Grow Out",
            "suggested_purpose_reason": "Pig is active/on farm but not yet in a current outlet window.",
            "suggested_purpose_confidence": "Medium",
        }

    return {
        "suggested_purpose": "Manual Review",
        "suggested_purpose_reason": "No trusted suggested-purpose rule matched this pig.",
        "suggested_purpose_confidence": "Low",
    }


def _growth_profile(row, latest_weight, today, settings=None):
    settings = settings or _allocation_settings()
    latest_weight_date = latest_weight.get("weight_date") or parse_sheet_date(row.get("Last_Weight_Date", ""))
    latest_weight_kg = latest_weight.get("weight_kg")
    if latest_weight_kg is None:
        latest_weight_kg = to_float(row.get("Current_Weight_Kg", ""))

    birth_date = parse_sheet_date(row.get("Date_Of_Birth", ""))
    age_days = to_float(row.get("Age_Days", ""))
    if age_days is None and birth_date:
        age_days = (today - birth_date).days
    wean_date = parse_sheet_date(row.get("Wean_Date", ""))
    wean_weight_kg = to_float(row.get("Wean_Weight_Kg", ""))
    lifetime_daily_gain = None
    if latest_weight_kg is not None and age_days and age_days > 0:
        lifetime_daily_gain = round(latest_weight_kg / age_days, 3)

    post_wean_daily_gain = to_float(row.get("Average_Daily_Gain_Kg", ""))
    if post_wean_daily_gain is None and latest_weight_kg is not None and wean_weight_kg is not None and latest_weight_date and wean_date:
        days_since_wean = (latest_weight_date - wean_date).days
        if days_since_wean > 0:
            post_wean_daily_gain = round((latest_weight_kg - wean_weight_kg) / days_since_wean, 3)

    growth_class, growth_reason = _growth_class_for_adg(lifetime_daily_gain, settings)

    return {
        "latest_weight_kg": latest_weight_kg,
        "latest_weight_date": latest_weight_date,
        "days_since_weight": (today - latest_weight_date).days if latest_weight_date else None,
        "birth_date": birth_date,
        "age_days": age_days,
        "wean_date": wean_date,
        "wean_weight_kg": wean_weight_kg,
        "days_since_wean": (today - wean_date).days if wean_date else None,
        "average_daily_gain_kg": lifetime_daily_gain,
        "post_wean_daily_gain_kg": post_wean_daily_gain,
        "growth_basis": "Lifetime ADG",
        "growth_class": growth_class,
        "growth_reason": growth_reason,
    }


def _allocation_source_row(overview_row, master_row):
    if not master_row:
        return overview_row

    row = dict(overview_row)
    for field_name in (
        "Wean_Date",
        "Wean_Weight_Kg",
        "Litter_Size_Weaned",
        "Birth_Weight_Kg",
        "General_Notes",
    ):
        master_value = master_row.get(field_name, "")
        if master_value not in (None, ""):
            row[field_name] = master_value
    return row


def _readiness_bucket(row, growth, sales_meta, litter_quality, today, settings=None):
    settings = settings or _allocation_settings()
    status = to_clean_string(row.get("Status", ""))
    on_farm = to_clean_string(row.get("On_Farm", ""))
    purpose = to_clean_string(row.get("Purpose", ""))
    animal_type = to_clean_string(row.get("Animal_Type", ""))
    sex = to_clean_string(row.get("Sex", ""))
    tag_number = to_clean_string(row.get("Tag_Number", ""))
    weight_kg = growth.get("latest_weight_kg")
    last_weight_date = growth.get("latest_weight_date")
    growth_class = growth.get("growth_class", "Unknown")
    reserved_status = to_clean_string(sales_meta.get("reserved_status", ""))
    reserved_for_order_id = to_clean_string(sales_meta.get("reserved_for_order_id", ""))
    available_for_sale = to_clean_string(sales_meta.get("available_for_sale", ""))
    normalized_purpose = purpose.lower().replace("-", "_").replace(" ", "_")
    normalized_status = status.lower()

    if normalized_status in {value.lower() for value in TERMINAL_PIG_STATUSES} or on_farm.lower() != "yes":
        return "Exited", "Pig is not active/on farm, or already has a terminal status."

    if reserved_status.lower() == "reserved" or reserved_for_order_id:
        return "Allocated", "Pig is already reserved or linked to an order."

    if normalized_purpose in {"breeding", "retain", "retained", "breeding_candidate"}:
        return "Retain / Breeding Candidate", "Current purpose is breeding or retention."

    missing = []
    if not tag_number:
        missing.append("tag")
    if not sex:
        missing.append("sex")
    if weight_kg is None:
        missing.append("weight")
    if missing:
        return "Needs Data", f"Missing {', '.join(missing)} before allocation can be trusted."

    if not purpose or normalized_purpose == "unknown":
        return "Needs Classification", "Purpose is still unknown; review wean weight, growth class, litter quality, and current outlet demand."

    if last_weight_date:
        days_since_weight = (today - last_weight_date).days
        if days_since_weight > settings["stale_weight_days"]:
            return "Needs Data", f"Latest weight is {days_since_weight} days old."

    if growth_class in {"Good", "Exceptional"} and litter_quality.get("litter_quality") == "Good":
        return "Retain / Breeding Candidate", "Good or exceptional lifetime grower from a good litter; review for breeding before meat/slaughter allocation."

    if growth_class in {"Extremely Slow", "Slow"} and animal_type in {"Grower", "Finisher", "Weaner"}:
        return "Livestock Candidate", "Slow lifetime grower; consider live sale to reduce feed cost and free capacity."

    if available_for_sale.lower() == "yes" and weight_kg >= settings["live_sale_target_kg"]:
        return "Livestock Candidate", "Sales availability says this pig is available and weight is at or above live-sale target."

    if settings["meat_target_min_kg"] <= weight_kg < settings["meat_target_max_kg"]:
        return "Meat Candidate", "Weight is in the first planned meat-candidate range."

    if weight_kg >= settings["slaughter_target_min_kg"] and (settings.get("slaughter_target_max_kg") is None or weight_kg <= settings["slaughter_target_max_kg"]):
        return "Slaughter Candidate", "Weight is in the first planned slaughter-candidate range."

    if animal_type in {"Grower", "Finisher", "Weaner"}:
        return "Growing", "Pig is active/on farm but not in a current candidate range."

    return "Needs Data", "No trusted allocation rule matched this pig yet."


def get_pig_allocation_readiness(today=None):
    today = today or datetime.now().date()
    settings = _allocation_settings()
    columns = PIG_WEIGHTS_CONFIG["columns"]
    supabase_inputs = _try_supabase_read(farm_supabase_read_service.get_allocation_input_rows)
    if supabase_inputs is not None:
        overview_rows = supabase_inputs.get("overview_rows", [])
        pig_master_rows = supabase_inputs.get("pig_master_rows", [])
        weight_rows = supabase_inputs.get("weight_rows", [])
        sales_rows = supabase_inputs.get("sales_rows", [])
        litter_rows = supabase_inputs.get("litter_rows", [])
        pen_lookup = supabase_inputs.get("pen_lookup", {})
        source = supabase_inputs.get("source", "supabase_canonical")
    else:
        overview_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
        pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
        weight_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"])
        sales_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["sales_availability"])
        litter_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_overview"])
        pen_lookup = _build_pen_lookup()
        source = "google_sheets"
    master_lookup = _build_pig_lookup(pig_master_rows, columns)
    latest_weights = _latest_weights_by_pig(weight_rows, columns)
    sales_lookup = _sales_availability_by_pig(sales_rows, columns)
    litter_lookup = _litter_overview_by_id(litter_rows)

    buckets = {
        "Needs Data": 0,
        "Needs Classification": 0,
        "Growing": 0,
        "Livestock Candidate": 0,
        "Slaughter Candidate": 0,
        "Meat Candidate": 0,
        "Retain / Breeding Candidate": 0,
        "Allocated": 0,
        "Exited": 0,
    }
    rows = []

    for row in overview_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if not pig_id:
            continue

        row = _allocation_source_row(row, master_lookup.get(pig_id, {}))
        latest_weight = latest_weights.get(pig_id, {})
        sales_meta = sales_lookup.get(pig_id, {})
        growth = _growth_profile(row, latest_weight, today, settings)
        timing = _readiness_timing(growth, today, settings)
        litter_id = to_clean_string(row.get("Litter_ID", ""))
        litter_quality = _litter_quality_summary(litter_lookup.get(litter_id), settings)
        bucket, reason = _readiness_bucket(row, growth, sales_meta, litter_quality, today, settings)
        outlet_action = _recommended_outlet_action(bucket, growth, timing, litter_quality)
        suggested_purpose = _suggested_purpose_signal(bucket, outlet_action, growth, timing, litter_quality)
        buckets[bucket] = buckets.get(bucket, 0) + 1

        current_pen_id = to_clean_string(row.get(columns["current_pen_id"], ""))

        rows.append({
            "pig_id": pig_id,
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "animal_type": to_clean_string(row.get("Animal_Type", "")),
            "sex": to_clean_string(row.get(columns["sex"], "")),
            "status": to_clean_string(row.get(columns["status"], "")),
            "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
            "purpose": to_clean_string(row.get("Purpose", "")),
            "current_pen_id": current_pen_id,
            "current_pen_name": _pen_name_for_id(pen_lookup, current_pen_id),
            "latest_weight_kg": growth["latest_weight_kg"],
            "latest_weight_date": growth["latest_weight_date"].isoformat() if growth["latest_weight_date"] else "",
            "days_since_weight": growth["days_since_weight"],
            "birth_date": growth["birth_date"].isoformat() if growth["birth_date"] else "",
            "age_days": growth["age_days"],
            "wean_date": growth["wean_date"].isoformat() if growth["wean_date"] else "",
            "wean_weight_kg": growth["wean_weight_kg"],
            "days_since_wean": growth["days_since_wean"],
            "average_daily_gain_kg": growth["average_daily_gain_kg"],
            "post_wean_daily_gain_kg": growth["post_wean_daily_gain_kg"],
            "growth_basis": growth["growth_basis"],
            "growth_class": growth["growth_class"],
            "growth_reason": growth["growth_reason"],
            "meat_window_status": timing["meat_window_status"],
            "estimated_meat_ready_date": timing["estimated_meat_ready_date"],
            "days_until_meat_ready": timing["days_until_meat_ready"],
            "meat_target_min_kg": timing["meat_target_min_kg"],
            "meat_target_max_kg": timing["meat_target_max_kg"],
            "abattoir_window_status": timing["abattoir_window_status"],
            "estimated_abattoir_ready_date": timing["estimated_abattoir_ready_date"],
            "days_until_abattoir_ready": timing["days_until_abattoir_ready"],
            "abattoir_target_min_kg": timing["abattoir_target_min_kg"],
            "abattoir_target_max_kg": timing["abattoir_target_max_kg"],
            "calculated_stage": to_clean_string(row.get(columns["calculated_stage"], "")),
            "weight_band": to_clean_string(row.get(columns["weight_band"], "")),
            "litter_id": litter_id,
            "mother_id": to_clean_string(row.get("Mother_Pig_ID", "")),
            "father_id": to_clean_string(row.get("Father_Pig_ID", "")),
            "sow_pig_id": litter_quality["sow_pig_id"],
            "sow_tag_number": litter_quality["sow_tag_number"],
            "boar_pig_id": litter_quality["boar_pig_id"],
            "boar_tag_number": litter_quality["boar_tag_number"],
            "litter_quality": litter_quality["litter_quality"],
            "litter_quality_reason": litter_quality["litter_quality_reason"],
            "litter_survival_rate": litter_quality["litter_survival_rate"],
            "born_alive": litter_quality["born_alive"],
            "weaned_count": litter_quality["weaned_count"],
            "readiness_bucket": bucket,
            "readiness_reason": reason,
            "outlet_priority": outlet_action["outlet_priority"],
            "recommended_action": outlet_action["recommended_action"],
            "marketing_readiness": outlet_action["marketing_readiness"],
            "suggested_purpose": suggested_purpose["suggested_purpose"],
            "suggested_purpose_reason": suggested_purpose["suggested_purpose_reason"],
            "suggested_purpose_confidence": suggested_purpose["suggested_purpose_confidence"],
            "available_for_sale": sales_meta.get("available_for_sale", ""),
            "reserved_status": sales_meta.get("reserved_status", ""),
            "reserved_for_order_id": sales_meta.get("reserved_for_order_id", ""),
            "sale_category": sales_meta.get("sale_category", ""),
            "suggested_price_category": sales_meta.get("suggested_price_category", ""),
            "existing_link": sales_meta.get("reserved_for_order_id", ""),
        })

    rows.sort(key=lambda item: (
        ALLOCATION_BUCKET_ORDER.get(item["readiness_bucket"], 99),
        item["current_pen_name"] or item["current_pen_id"],
        _pig_sort_key(item["tag_number"] or item["pig_id"]),
    ))

    return {
        "success": True,
        "generated_date": today.isoformat(),
        "source": source,
        "thresholds": settings,
        "business_rules": {
            "source": settings["source"],
            "writes_enabled": settings["writes_enabled"],
            "meat_window_label": _weight_window_label(settings["meat_target_min_kg"], settings["meat_target_max_kg"], upper_exclusive=settings.get("meat_window_upper_exclusive")),
            "abattoir_window_label": _weight_window_label(settings["slaughter_target_min_kg"], settings.get("slaughter_target_max_kg"), upper_unbounded=settings.get("abattoir_window_upper_unbounded")),
            "live_sale_label": f"{settings['live_sale_target_kg']} kg+ when available for sale, or slow-growth fallback",
            "target_growth_label": f"{settings['exceptional_grower_adg_kg_day']:.3f} kg/day target",
            "slow_growth_label": f"Under {settings['slow_grower_adg_kg_day']:.3f} kg/day",
            "good_litter_label": f"{round(settings['good_litter_survival_rate'] * 100)}%+ survival to weaning",
            "stale_weight_label": f"{settings['stale_weight_days']} days",
        },
        "summary": {
            "total": len(rows),
            "buckets": buckets,
        },
        "pigs": rows,
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }


def get_meat_ready_stock_summary(today=None, allocation=None, price_entries=None):
    today = today or datetime.now().date()
    allocation = allocation if isinstance(allocation, dict) else get_pig_allocation_readiness(today=today)
    if price_entries is None:
        price_entries = _read_current_meat_price_entries()
    groups = _empty_meat_ready_groups()
    rows = []

    for pig in allocation.get("pigs", []) if isinstance(allocation.get("pigs"), list) else []:
        classification = _meat_ready_classification(pig)
        freshness = _weight_freshness(pig.get("days_since_weight"), allocation.get("thresholds", {}))
        price_rule = _stock_value_price_rule(classification["category_key"], price_entries)
        estimated_value = _stock_value_estimate(pig, freshness, price_rule)
        row = {
            "pig_id": pig.get("pig_id", ""),
            "tag_number": pig.get("tag_number", ""),
            "category": classification["category"],
            "category_key": classification["category_key"],
            "reason": classification["reason"],
            "latest_weight_kg": pig.get("latest_weight_kg"),
            "latest_weight_date": pig.get("latest_weight_date", ""),
            "days_since_weight": pig.get("days_since_weight"),
            "weight_freshness": freshness["status"],
            "weight_freshness_label": freshness["label"],
            "valuation_status": estimated_value["status"],
            "estimated_value": estimated_value["value"],
            "price_source": price_rule.get("source", "pricing_not_configured"),
            "price_label": price_rule.get("label", "pricing not configured"),
            "excluded_from_sam_availability": True,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        }
        rows.append(row)
        group = groups[row["category_key"]]
        group["count"] += 1
        if row["estimated_value"] is not None:
            group["estimated_value"] = round(group["estimated_value"] + row["estimated_value"], 2)
        if row["valuation_status"] != "valued":
            group["warnings"].append(f"{row['tag_number'] or row['pig_id']}: {row['valuation_status']}")

    return {
        "success": True,
        "source": "pig_allocation_readiness",
        "generated_date": today.isoformat(),
        "settings": allocation.get("business_rules", {}),
        "groups": list(groups.values()),
        "pigs": rows,
        "summary": {
            "total_pigs_reviewed": len(rows),
            "total_estimated_value": round(sum(group["estimated_value"] for group in groups.values()), 2),
            "pricing_not_configured_count": len([row for row in rows if row["valuation_status"] == "pricing_not_configured"]),
            "stale_or_missing_weight_count": len([row for row in rows if row["valuation_status"] in {"stale_weight_review", "not_valuation_ready", "missing_weight"}]),
        },
        "no_feed_cost_included": True,
        "customer_promise_enabled": False,
        "sam_availability_enabled": False,
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }


def _empty_meat_ready_groups():
    labels = [
        ("meat_window_candidate", "Meat Window Candidate Value"),
        ("abattoir_cull_candidate", "Abattoir/Cull Candidate Value"),
        ("live_sale_candidate", "Live Sale Candidate Value"),
        ("hold_grow_longer", "Hold/Grow Longer Review Value"),
        ("slow_grower_review", "Slow Grower Review List"),
        ("excluded", "Excluded / No Reliable Value Yet"),
    ]
    return {key: {"category_key": key, "category": label, "count": 0, "estimated_value": 0.0, "warnings": []} for key, label in labels}


def _meat_ready_classification(pig):
    status = to_clean_string(pig.get("status", "")).lower()
    on_farm = to_clean_string(pig.get("on_farm", "")).lower()
    reserved = to_clean_string(pig.get("reserved_status", "")).lower() == "reserved" or bool(pig.get("reserved_for_order_id"))
    if status in {value.lower() for value in TERMINAL_PIG_STATUSES} or on_farm != "yes" or reserved or pig.get("readiness_bucket") in {"Allocated", "Exited"}:
        return {"category_key": "excluded", "category": "Excluded / No Reliable Value Yet", "reason": "reserved_sold_dead_removed_or_not_on_farm"}
    if pig.get("readiness_bucket") == "Meat Candidate" or pig.get("meat_window_status") == "In meat window":
        return {"category_key": "meat_window_candidate", "category": "Meat Window Candidate Value", "reason": "weight_in_meat_window"}
    if pig.get("readiness_bucket") == "Slaughter Candidate" or pig.get("abattoir_window_status") == "In abattoir window":
        return {"category_key": "abattoir_cull_candidate", "category": "Abattoir/Cull Candidate Value", "reason": "weight_in_abattoir_or_cull_window"}
    if pig.get("readiness_bucket") == "Livestock Candidate":
        if pig.get("growth_class") in {"Slow", "Extremely Slow"}:
            return {"category_key": "slow_grower_review", "category": "Slow Grower Review List", "reason": "slow_grower_consuming_feed"}
        return {"category_key": "live_sale_candidate", "category": "Live Sale Candidate Value", "reason": "livestock_sale_candidate"}
    return {"category_key": "hold_grow_longer", "category": "Hold/Grow Longer Review Value", "reason": "not_ready_or_better_value_later"}


def _weight_freshness(days_since_weight, settings):
    if days_since_weight is None:
        return {"status": "missing", "label": "missing latest weight"}
    fresh_days = int((settings or {}).get("fresh_weight_days") or 14)
    stale_days = int((settings or {}).get("stale_weight_days") or 30)
    if days_since_weight <= fresh_days:
        return {"status": "fresh", "label": "fresh weight"}
    if days_since_weight <= stale_days:
        return {"status": "stale_warning", "label": "stale warning"}
    return {"status": "expired", "label": "not valuation-ready"}


def _read_current_meat_price_entries():
    try:
        from modules.oom_sakkie.sales_campaign_store import list_meat_price_book_entries
        result, status = list_meat_price_book_entries(limit=100)
    except Exception:
        return []
    if status != 200 or not isinstance(result, dict):
        return []
    return result.get("entries", []) if isinstance(result.get("entries"), list) else []


def _stock_value_price_rule(category_key, price_entries):
    product_type = "half_carcass" if category_key == "meat_window_candidate" else "assisted_slaughter" if category_key == "abattoir_cull_candidate" else "live_pig"
    for entry in price_entries if isinstance(price_entries, list) else []:
        if entry.get("active") is False:
            continue
        if entry.get("product_type") != product_type:
            continue
        amount = to_float(entry.get("price_amount"))
        if amount is None:
            continue
        return {
            "amount": amount,
            "unit": entry.get("price_unit") or "per_kg",
            "source": entry.get("source") or "meat_price_book",
            "label": f"R{amount:,.2f}/kg" if entry.get("price_unit") != "per_pig_fee" else f"R{amount:,.2f} fee",
        }
    return {"amount": None, "unit": "", "source": "pricing_not_configured", "label": "pricing not configured"}


def _stock_value_estimate(pig, freshness, price_rule):
    weight = pig.get("latest_weight_kg")
    if weight is None:
        return {"status": "missing_weight", "value": None}
    if freshness["status"] == "expired":
        return {"status": "not_valuation_ready", "value": None}
    amount = price_rule.get("amount")
    if amount is None:
        return {"status": "pricing_not_configured", "value": None}
    if price_rule.get("unit") == "per_pig_fee":
        value = amount
    else:
        value = float(weight) * float(amount)
    return {"status": "stale_weight_review" if freshness["status"] == "stale_warning" else "valued", "value": round(value, 2)}

def _meat_planning_bucket(row):
    suggested_purpose = to_clean_string(row.get("suggested_purpose", ""))
    meat_status = to_clean_string(row.get("meat_window_status", ""))
    days_until_meat_ready = row.get("days_until_meat_ready")
    outlet_priority = to_clean_string(row.get("outlet_priority", ""))

    if suggested_purpose == "Meat" or outlet_priority == "Meat Preorder":
        if meat_status == "In meat window" or days_until_meat_ready == 0:
            return "ready_now"
        if isinstance(days_until_meat_ready, (int, float)):
            if days_until_meat_ready <= 14:
                return "next_14_days"
            if days_until_meat_ready <= 30:
                return "next_30_days"
        return "future"

    if suggested_purpose == "Abattoir Slaughter" or outlet_priority == "Abattoir Slaughter":
        return "fallback_abattoir"

    return ""


def _meat_planning_row(row, planning_bucket):
    return {
        "planning_bucket": planning_bucket,
        "pig_id": row.get("pig_id", ""),
        "tag_number": row.get("tag_number", ""),
        "current_pen_id": row.get("current_pen_id", ""),
        "current_pen_name": row.get("current_pen_name", ""),
        "latest_weight_kg": row.get("latest_weight_kg"),
        "latest_weight_date": row.get("latest_weight_date", ""),
        "average_daily_gain_kg": row.get("average_daily_gain_kg"),
        "growth_class": row.get("growth_class", ""),
        "meat_window_status": row.get("meat_window_status", ""),
        "estimated_meat_ready_date": row.get("estimated_meat_ready_date", ""),
        "days_until_meat_ready": row.get("days_until_meat_ready"),
        "estimated_abattoir_ready_date": row.get("estimated_abattoir_ready_date", ""),
        "days_until_abattoir_ready": row.get("days_until_abattoir_ready"),
        "suggested_purpose": row.get("suggested_purpose", ""),
        "suggested_purpose_reason": row.get("suggested_purpose_reason", ""),
        "outlet_priority": row.get("outlet_priority", ""),
        "recommended_action": row.get("recommended_action", ""),
        "marketing_readiness": row.get("marketing_readiness", ""),
        "litter_id": row.get("litter_id", ""),
        "litter_quality": row.get("litter_quality", ""),
        "litter_survival_rate": row.get("litter_survival_rate"),
        "sex": row.get("sex", ""),
        "animal_type": row.get("animal_type", ""),
    }


def get_meat_planning_summary(today=None):
    allocation = get_pig_allocation_readiness(today=today)
    planning_rows = []
    buckets = {
        "ready_now": 0,
        "next_14_days": 0,
        "next_30_days": 0,
        "future": 0,
        "fallback_abattoir": 0,
    }

    for row in allocation.get("pigs", []):
        planning_bucket = _meat_planning_bucket(row)
        if not planning_bucket:
            continue
        buckets[planning_bucket] += 1
        planning_rows.append(_meat_planning_row(row, planning_bucket))

    planning_rows.sort(key=lambda item: (
        {
            "ready_now": 0,
            "next_14_days": 1,
            "next_30_days": 2,
            "future": 3,
            "fallback_abattoir": 4,
        }.get(item["planning_bucket"], 99),
        item["days_until_meat_ready"] if item["days_until_meat_ready"] is not None else 9999,
        _pig_sort_key(item["tag_number"] or item["pig_id"]),
    ))

    meat_pipeline_count = buckets["ready_now"] + buckets["next_14_days"] + buckets["next_30_days"] + buckets["future"]

    return {
        "success": True,
        "generated_date": allocation.get("generated_date", ""),
        "source": "pig_allocation_readiness",
        "business_rules": allocation.get("business_rules", {}),
        "thresholds": allocation.get("thresholds", {}),
        "summary": {
            "meat_pipeline_count": meat_pipeline_count,
            "ready_now": buckets["ready_now"],
            "next_14_days": buckets["next_14_days"],
            "next_30_days": buckets["next_30_days"],
            "future": buckets["future"],
            "fallback_abattoir": buckets["fallback_abattoir"],
            "minimum_preorder_needed_now": buckets["ready_now"],
            "minimum_preorder_needed_30_days": buckets["ready_now"] + buckets["next_14_days"] + buckets["next_30_days"],
        },
        "buckets": buckets,
        "pigs": planning_rows,
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }


def get_family_tree(pig_id: str):
    pig_id = str(pig_id).strip()
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_family_tree, pig_id)
    if supabase_result is not None:
        return supabase_result

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    rows = get_all_records(sheet_name)

    pig_lookup = _build_pig_lookup(rows, columns)
    current_row = pig_lookup.get(pig_id)

    if not current_row:
        return None

    current_pig = _pig_summary_card(current_row, columns)

    mother_pig_id = to_clean_string(current_row.get("Mother_Pig_ID", ""))
    father_pig_id = to_clean_string(current_row.get("Father_Pig_ID", ""))
    litter_id = to_clean_string(current_row.get("Litter_ID", ""))

    mother_row = pig_lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = pig_lookup.get(father_pig_id) if father_pig_id else None

    mother = _pig_summary_card(mother_row, columns) if mother_row else None
    father = _pig_summary_card(father_row, columns) if father_row else None

    siblings = []
    if litter_id:
        for row in rows:
            row_litter_id = to_clean_string(row.get("Litter_ID", ""))
            row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
            if row_litter_id == litter_id and row_pig_id != pig_id:
                siblings.append(_pig_summary_card(row, columns))

    siblings = sorted(
        siblings,
        key=lambda x: (x["tag_number"] or x["pig_id"]).lower()
    )

    return {
        "pig_id": pig_id,
        "current_pig": current_pig,
        "mother": mother,
        "father": father,
        "siblings": siblings,
        "litter_id": litter_id,
        "sibling_count": len(siblings),
    }


def get_litter_detail(litter_id: str):
    litter_id = str(litter_id).strip()

    if not litter_id:
        return None

    supabase_result = _try_supabase_read(farm_supabase_read_service.get_litter_detail, litter_id)
    if supabase_result is not None:
        return supabase_result

    attention = _litter_attention_for_id(litter_id)
    reconciliation = _litter_birth_reconciliation_for_id(litter_id)
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
    reconciliation = _augment_litter_birth_reconciliation_with_history(litter_id, reconciliation, pig_master_rows)
    lifecycle_outcomes = _litter_lifecycle_outcomes(litter_id, pig_master_rows)

    pig_lookup = {}
    litter_rows = []

    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id:
            pig_lookup[row_pig_id] = row

        row_litter_id = to_clean_string(row.get("Litter_ID", ""))
        if row_litter_id == litter_id:
            litter_rows.append(row)

    if not litter_rows:
        litter_rows_sheet = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"])
        for row in litter_rows_sheet:
            if to_clean_string(row.get("Litter_ID", "")) == litter_id:
                wean_timing = _litter_wean_timing_json(row)
                return {
                    "litter_id": litter_id,
                    "mother_pig_id": to_clean_string(row.get("Sow_Pig_ID", "")),
                    "mother_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
                    "father_pig_id": to_clean_string(row.get("Boar_Pig_ID", "")),
                    "father_tag_number": to_clean_string(row.get("Boar_Tag_Number", "")),
                    "count": 0,
                    "male_count": row.get("Male_Count", ""),
                    "female_count": row.get("Female_Count", ""),
                    "active_count": 0,
                    "average_weight_kg": None,
                    "piglets": [],
                    "attention": attention,
                    "reconciliation": reconciliation,
                    "lifecycle_outcomes": lifecycle_outcomes,
                    "litter_status": _derive_litter_status(row, reconciliation, lifecycle_outcomes),
                    **wean_timing,
                }
        return None

    first_row = litter_rows[0]
    wean_timing = _litter_wean_timing_json(first_row)

    mother_pig_id = to_clean_string(first_row.get("Mother_Pig_ID", ""))
    father_pig_id = to_clean_string(first_row.get("Father_Pig_ID", ""))

    mother_row = pig_lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = pig_lookup.get(father_pig_id) if father_pig_id else None

    mother_tag_number = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
    father_tag_number = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""

    piglets = []
    male_count = 0
    female_count = 0
    active_count = 0
    weight_values = []

    for row in litter_rows:
        sex = to_clean_string(row.get("Sex", ""))
        status = to_clean_string(row.get(columns["status"], ""))
        current_weight = to_float(row.get(columns["current_weight"], ""))

        if sex == "Male":
            male_count += 1
        elif sex == "Female":
            female_count += 1

        if status == "Active":
            active_count += 1

        if current_weight is not None:
            weight_values.append(current_weight)

        piglets.append({
            "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "sex": sex,
            "status": status,
            "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
            "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
            "age_days": row.get("Age_Days", ""),
            "current_weight_kg": current_weight,
            "calculated_stage": to_clean_string(row.get("Calculated_Stage", "")),
            "current_pen_id": to_clean_string(row.get("Current_Pen_ID", "")),
        })

    piglets = sorted(
        piglets,
        key=lambda x: (x["tag_number"] or x["pig_id"]).lower()
    )

    average_weight = round(sum(weight_values) / len(weight_values), 2) if weight_values else None

    return {
        "litter_id": litter_id,
        "mother_pig_id": mother_pig_id,
        "mother_tag_number": mother_tag_number,
        "father_pig_id": father_pig_id,
        "father_tag_number": father_tag_number,
        "litter_status": _derive_litter_status(first_row, reconciliation, lifecycle_outcomes),
        "count": len(piglets),
        "male_count": male_count,
        "female_count": female_count,
        "active_count": active_count,
        "average_weight_kg": average_weight,
        "piglets": piglets,
        "attention": attention,
        "reconciliation": reconciliation,
        "lifecycle_outcomes": lifecycle_outcomes,
        **wean_timing,
    }


def get_pig_detail(pig_id: str):
    pig_id = str(pig_id).strip()
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_pig_detail, pig_id)
    if supabase_result is not None:
        return supabase_result

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])

    pig_lookup = {}
    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id:
            pig_lookup[row_pig_id] = row

    pig = pig_lookup.get(pig_id)
    if not pig:
        return None
    master_pig = _build_pig_lookup(pig_master_rows, columns).get(pig_id, {})

    mother_pig_id = to_clean_string(pig.get("Mother_Pig_ID", ""))
    father_pig_id = to_clean_string(pig.get("Father_Pig_ID", ""))
    litter_id = to_clean_string(pig.get("Litter_ID", ""))

    mother_row = pig_lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = pig_lookup.get(father_pig_id) if father_pig_id else None

    mother_tag_number = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
    father_tag_number = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""
    lifecycle_status = to_clean_string(master_pig.get(columns["status"], pig.get(columns["status"], "")))
    lifecycle_on_farm = to_clean_string(master_pig.get(columns["on_farm"], pig.get(columns["on_farm"], "")))

    return {
        "pig_id": to_clean_string(pig.get(columns["pig_id"], "")),
        "tag_number": to_clean_string(pig.get(columns["tag_number"], "")),
        "status": to_clean_string(pig.get(columns["status"], "")),
        "on_farm": to_clean_string(pig.get(columns["on_farm"], "")),
        "animal_type": to_clean_string(pig.get("Animal_Type", "")),
        "sex": to_clean_string(pig.get("Sex", "")),
        "date_of_birth": format_date_for_json(pig.get("Date_Of_Birth", "")),
        "age_days": pig.get("Age_Days", ""),
        "litter_id": litter_id,
        "mother_pig_id": mother_pig_id,
        "mother_tag_number": mother_tag_number,
        "father_pig_id": father_pig_id,
        "father_tag_number": father_tag_number,
        "current_pen_id": to_clean_string(pig.get("Current_Pen_ID", "")),
        "purpose": to_clean_string(pig.get("Purpose", "")),
        "current_weight_kg": pig.get("Current_Weight_Kg", ""),
        "last_weight_date": format_date_for_json(pig.get("Last_Weight_Date", "")),
        "calculated_stage": to_clean_string(pig.get("Calculated_Stage", "")),
        "weight_band": to_clean_string(pig.get("Weight_Band", "")),
        "is_sale_ready": to_clean_string(pig.get("Is_Sale_Ready", "")),
        "reserved_status": to_clean_string(pig.get("Reserved_Status", "")),
        "general_notes": to_clean_string(pig.get("General_Notes", "")),
        "last_treatment_date": format_date_for_json(pig.get("Last_Treatment_Date", "")),
        "last_product_name": to_clean_string(pig.get("Last_Product_Name", "")),
        "current_withdrawal_end_date": format_date_for_json(pig.get("Current_Withdrawal_End_Date", "")),
        "withdrawal_clear": to_clean_string(pig.get("Withdrawal_Clear", "")),
        "lifecycle": {
            "status": lifecycle_status,
            "on_farm": lifecycle_on_farm,
            "wean_date": format_date_for_json(master_pig.get("Wean_Date", "")),
            "wean_weight_kg": to_float(master_pig.get("Wean_Weight_Kg", "")),
            "exit_date": format_date_for_json(master_pig.get("Exit_Date", "")),
            "exit_reason": to_clean_string(master_pig.get("Exit_Reason", "")),
            "exit_order_id": to_clean_string(master_pig.get("Exit_Order_ID", "")),
            "carcass_weight_kg": to_float(master_pig.get("Carcass_Weight_Kg", "")),
        },
    }


def _get_products_from_sheets():
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


def get_products():
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_products)
    if supabase_result is not None:
        return supabase_result

    return _get_products_from_sheets()


def get_product_by_id(product_id: str):
    product_id = str(product_id).strip()
    products = get_products()

    for product in products:
        if product["product_id"] == product_id:
            return product

    return None


def get_pens():
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_pens)
    if supabase_result is not None:
        return supabase_result

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    pens = []
    for row in rows:
        active_value = str(row.get(columns["is_active"], "")).strip()
        if active_value and active_value != "Yes":
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
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_treatment_history_for_pig, pig_id)
    if supabase_result is not None:
        return supabase_result

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
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_movement_history_for_pig, pig_id)
    if supabase_result is not None:
        return supabase_result

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
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_weight_history_for_pig, pig_id)
    if supabase_result is not None:
        return supabase_result

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

def get_weight_entries_by_date(weight_date: str):
    parsed_target_date = parse_sheet_date(weight_date)

    if not parsed_target_date:
        return {
            "weight_date": "",
            "count": 0,
            "history": [],
        }
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_weight_entries_by_date, parsed_target_date.isoformat())
    if supabase_result is not None:
        return supabase_result

    weight_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    overview_rows = get_all_records(overview_sheet)
    pig_lookup = {}

    for row in overview_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if not pig_id:
            continue

        pig_lookup[pig_id] = {
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "current_pen_id": to_clean_string(row.get(columns["current_pen_id"], "")),
        }

    weight_rows = get_all_records(weight_log_sheet)

    history = []
    for row in weight_rows:
        row_date = parse_sheet_date(row.get(columns["weight_date"], ""))
        if row_date != parsed_target_date:
            continue

        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        pig_meta = pig_lookup.get(pig_id, {})

        history.append({
            "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": pig_meta.get("tag_number", ""),
            "current_pen_id": pig_meta.get("current_pen_id", ""),
            "weight_date_display": format_date_for_json(row.get(columns["weight_date"], "")),
            "weight_kg": to_float(row.get(columns["weight_kg"], "")),
            "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
            "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: ((x["tag_number"] or x["pig_id"]).lower(), x["pig_id"].lower())
    )

    return {
        "weight_date": parsed_target_date.isoformat(),
        "count": len(history),
        "history": history,
    }


def _average(values):
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return None
    return round(sum(clean_values) / len(clean_values), 2)


def _tag_sort_key(tag_number, pig_id):
    raw = to_clean_string(tag_number or pig_id)
    if raw.isdigit():
        return raw.zfill(8)
    return raw.lower()


def _build_weight_report_pig_lookup(overview_rows, columns, pen_lookup):
    lookup = {}

    for row in overview_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if not pig_id:
            continue

        current_pen_id = to_clean_string(row.get(columns["current_pen_id"], ""))
        lookup[pig_id] = {
            "pig_id": pig_id,
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "status": to_clean_string(row.get(columns["status"], "")),
            "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
            "current_pen_id": current_pen_id,
            "current_pen_name": _pen_name_for_id(pen_lookup, current_pen_id),
            "calculated_stage": to_clean_string(row.get(columns["calculated_stage"], "")),
            "weight_band": to_clean_string(row.get(columns["weight_band"], "")),
        }

    return lookup


def _is_active_on_farm_pig(pig_meta):
    return (
        to_clean_string(pig_meta.get("status", "")).lower() == "active"
        and to_clean_string(pig_meta.get("on_farm", "")).lower() == "yes"
    )


def get_weight_report(date_from: str = "", date_to: str = "", pen_id: str = ""):
    parsed_from = parse_sheet_date(date_from) if date_from else datetime.now().date()
    parsed_to = parse_sheet_date(date_to) if date_to else parsed_from

    if not parsed_from or not parsed_to:
        raise ValueError("date_from and date_to must be valid dates.")

    if parsed_from > parsed_to:
        raise ValueError("date_from must be on or before date_to.")

    selected_pen_id = to_clean_string(pen_id)
    supabase_result = _try_supabase_read(
        farm_supabase_read_service.get_weight_report,
        parsed_from,
        parsed_to,
        selected_pen_id,
    )
    if supabase_result is not None:
        return supabase_result

    columns = PIG_WEIGHTS_CONFIG["columns"]
    weight_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"])
    overview_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    pen_lookup = _build_pen_lookup()
    pig_lookup = _build_weight_report_pig_lookup(overview_rows, columns, pen_lookup)

    weights_by_pig = {}
    for row in weight_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
        weight_kg = to_float(row.get(columns["weight_kg"], ""))

        if not pig_id or not weight_date or weight_kg is None:
            continue

        weights_by_pig.setdefault(pig_id, []).append({
            "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
            "pig_id": pig_id,
            "weight_date": weight_date,
            "weight_kg": weight_kg,
            "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
            "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
        })

    for pig_weights in weights_by_pig.values():
        pig_weights.sort(key=lambda item: item["weight_date"])

    same_day_counts = {}
    for pig_id, pig_weights in weights_by_pig.items():
        for item in pig_weights:
            key = (pig_id, item["weight_date"].isoformat())
            same_day_counts[key] = same_day_counts.get(key, 0) + 1

    entries = []
    for pig_id, pig_weights in weights_by_pig.items():
        pig_meta = pig_lookup.get(pig_id, {})
        if selected_pen_id and pig_meta.get("current_pen_id") != selected_pen_id:
            continue

        for index, item in enumerate(pig_weights):
            if item["weight_date"] < parsed_from or item["weight_date"] > parsed_to:
                continue

            previous_entry = None
            for previous_index in range(index - 1, -1, -1):
                candidate = pig_weights[previous_index]
                if candidate["weight_date"] < item["weight_date"]:
                    previous_entry = candidate
                    break

            difference_kg = None
            days_since_previous = None
            growth_rate_kg_day = None

            if previous_entry:
                difference_kg = round(item["weight_kg"] - previous_entry["weight_kg"], 2)
                days_since_previous = (item["weight_date"] - previous_entry["weight_date"]).days
                if days_since_previous > 0:
                    growth_rate_kg_day = round(difference_kg / days_since_previous, 3)

            duplicate_entry_count = same_day_counts.get((pig_id, item["weight_date"].isoformat()), 0)
            entries.append({
                "weight_log_id": item["weight_log_id"],
                "pig_id": pig_id,
                "tag_number": pig_meta.get("tag_number", ""),
                "status": pig_meta.get("status", ""),
                "on_farm": pig_meta.get("on_farm", ""),
                "active_on_farm": _is_active_on_farm_pig(pig_meta),
                "weight_date": item["weight_date"].isoformat(),
                "weight_kg": item["weight_kg"],
                "previous_weight_kg": previous_entry["weight_kg"] if previous_entry else None,
                "previous_weight_date": previous_entry["weight_date"].isoformat() if previous_entry else "",
                "difference_kg": difference_kg,
                "days_since_previous": days_since_previous,
                "growth_rate_kg_day": growth_rate_kg_day,
                "current_pen_id": pig_meta.get("current_pen_id", ""),
                "current_pen_name": pig_meta.get("current_pen_name", ""),
                "calculated_stage": pig_meta.get("calculated_stage", ""),
                "weight_band": pig_meta.get("weight_band", ""),
                "weighed_by": item["weighed_by"],
                "condition_notes": item["condition_notes"],
                "duplicate_same_day": duplicate_entry_count > 1,
                "duplicate_entry_count": duplicate_entry_count,
            })

    entries.sort(key=lambda item: (
        item["current_pen_name"] or item["current_pen_id"],
        _tag_sort_key(item["tag_number"], item["pig_id"]),
        item["pig_id"],
        item["weight_date"],
    ))

    pen_groups = {}
    for entry in entries:
        group_key = entry["current_pen_id"] or "Unknown"
        group = pen_groups.setdefault(group_key, {
            "pen_id": entry["current_pen_id"],
            "pen_name": entry["current_pen_name"],
            "entry_count": 0,
            "pig_ids": set(),
            "weights": [],
            "differences": [],
            "weight_loss_count": 0,
        })
        group["entry_count"] += 1
        group["pig_ids"].add(entry["pig_id"])
        group["weights"].append(entry["weight_kg"])
        group["differences"].append(entry["difference_kg"])
        if entry["difference_kg"] is not None and entry["difference_kg"] < 0:
            group["weight_loss_count"] += 1

    pen_summary = []
    for group in pen_groups.values():
        pen_summary.append({
            "pen_id": group["pen_id"],
            "pen_name": group["pen_name"],
            "entry_count": group["entry_count"],
            "unique_pigs": len(group["pig_ids"]),
            "average_weight_kg": _average(group["weights"]),
            "average_difference_kg": _average(group["differences"]),
            "weight_loss_count": group["weight_loss_count"],
        })

    pen_summary.sort(key=lambda item: (item["pen_name"] or item["pen_id"] or ""))

    unique_pig_ids = {entry["pig_id"] for entry in entries}
    differences = [entry["difference_kg"] for entry in entries]
    growth_rates = [entry["growth_rate_kg_day"] for entry in entries]
    loss_flags = [
        entry for entry in entries
        if entry["difference_kg"] is not None and entry["difference_kg"] < 0
    ]
    duplicate_same_day_count = len([entry for entry in entries if entry["duplicate_same_day"]])

    return {
        "success": True,
        "date_from": parsed_from.isoformat(),
        "date_to": parsed_to.isoformat(),
        "pen_id": selected_pen_id,
        "summary": {
            "total_entries": len(entries),
            "unique_pigs": len(unique_pig_ids),
            "average_weight_kg": _average([entry["weight_kg"] for entry in entries]),
            "average_difference_kg": _average(differences),
            "average_growth_rate_kg_day": _average(growth_rates),
            "weight_loss_count": len(loss_flags),
            "weight_gain_count": len([
                entry for entry in entries
                if entry["difference_kg"] is not None and entry["difference_kg"] > 0
            ]),
            "no_previous_weight_count": len([
                entry for entry in entries
                if entry["previous_weight_kg"] is None
            ]),
            "duplicate_same_day_count": duplicate_same_day_count,
            "not_active_on_farm_count": len([
                entry for entry in entries
                if not entry["active_on_farm"]
            ]),
        },
        "pen_summary": pen_summary,
        "loss_flags": loss_flags,
        "entries": entries,
    }

def get_latest_weight_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()
    supabase_result = _try_supabase_read(farm_supabase_read_service.get_latest_weight_for_pig, pig_id)
    if supabase_result is not None:
        return supabase_result

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


def save_new_pig(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]

    mother_pig_id = "" if cleaned_data["mother_pig_id"] == "Unknown" else cleaned_data["mother_pig_id"]
    father_pig_id = "" if cleaned_data["father_pig_id"] == "Unknown" else cleaned_data["father_pig_id"]
    litter_id = "" if cleaned_data["litter_id"] == "Unknown" else cleaned_data["litter_id"]

    parent_options = get_parent_options()
    mother_lookup = {row["pig_id"]: row["tag_number"] for row in parent_options["mothers"]}
    father_lookup = {row["pig_id"]: row["tag_number"] for row in parent_options["fathers"]}

    mother_tag_number = mother_lookup.get(cleaned_data["mother_pig_id"], "") if mother_pig_id else ""
    father_tag_number = father_lookup.get(cleaned_data["father_pig_id"], "") if father_pig_id else ""

    birth_month = cleaned_data["date_of_birth"].strftime("%m") if cleaned_data["date_of_birth"] else ""
    birth_year = cleaned_data["date_of_birth"].strftime("%Y") if cleaned_data["date_of_birth"] else ""

    today_str = datetime.now().strftime("%d %b %Y")

    pig_id = generate_pig_id()
    row_values = [
        pig_id,
        cleaned_data["tag_number"],
        cleaned_data["pig_name"],
        cleaned_data["status"],
        cleaned_data["on_farm"],
        cleaned_data["animal_type"],
        cleaned_data["sex"],
        format_date_for_sheet(cleaned_data["date_of_birth"]),
        birth_month,
        birth_year,
        cleaned_data["breed_type"],
        cleaned_data["colour_markings"],
        litter_id,
        cleaned_data["litter_size_born"] if cleaned_data["litter_size_born"] is not None else "",
        cleaned_data["litter_size_weaned"] if cleaned_data["litter_size_weaned"] is not None else "",
        mother_pig_id,
        father_pig_id,
        mother_tag_number,
        father_tag_number,
        "",
        "",
        cleaned_data["purpose"],
        "",
        cleaned_data["current_pen_id"],
        cleaned_data["source"],
        format_date_for_sheet(cleaned_data["acquisition_date"]),
        cleaned_data["birth_weight_kg"] if cleaned_data["birth_weight_kg"] is not None else "",
        format_date_for_sheet(cleaned_data["wean_date"]),
        cleaned_data["wean_weight_kg"] if cleaned_data["wean_weight_kg"] is not None else "",
        format_date_for_sheet(cleaned_data["exit_date"]),
        cleaned_data["exit_reason"],
        cleaned_data["exit_order_id"],
        cleaned_data["carcass_weight_kg"] if cleaned_data["carcass_weight_kg"] is not None else "",
        cleaned_data["general_notes"],
        today_str,
        today_str,
    ]

    if farm_supabase_write_service.farm_supabase_writes_available():
        try:
            farm_supabase_write_service.insert_pig(
                pig_id,
                cleaned_data,
                mother_tag_number=mother_tag_number,
                father_tag_number=father_tag_number,
            )
            return {
                "success": True,
                "message": "Pig created successfully.",
                "pig_id": pig_id,
                "source": {
                    "writes_to_google_sheets": False,
                    "writes_to_supabase": True,
                },
            }
        except Exception:
            pass

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Pig created successfully.",
        "pig_id": pig_id,
    }


def save_new_product(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["product_register"]
    product_id = generate_product_id()

    row_values = [
        product_id,
        cleaned_data["product_name"],
        cleaned_data["product_category"],
        cleaned_data["default_dose"] if cleaned_data["default_dose"] is not None else "",
        cleaned_data["dose_unit"],
        cleaned_data["default_withdrawal_days"] if cleaned_data["default_withdrawal_days"] is not None else "",
        cleaned_data["supplier"],
        cleaned_data["batch_tracking_required"],
        cleaned_data["is_active"],
        cleaned_data["product_notes"],
    ]

    if farm_supabase_write_service.farm_supabase_writes_available():
        try:
            farm_supabase_write_service.insert_product(product_id, cleaned_data)
            return {
                "success": True,
                "message": "Product created successfully.",
                "product_id": product_id,
                "source": {
                    "writes_to_google_sheets": False,
                    "writes_to_supabase": True,
                },
            }
        except Exception:
            pass

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Product created successfully.",
        "product_id": product_id,
    }


def save_new_pen(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"]
    pen_id = generate_pen_id()

    row_values = [
        pen_id,
        cleaned_data["pen_name"],
        cleaned_data["pen_type"],
        cleaned_data["capacity"] if cleaned_data["capacity"] is not None else "",
        cleaned_data["is_active"],
        cleaned_data["pen_notes"],
    ]

    if farm_supabase_write_service.farm_supabase_writes_available():
        try:
            farm_supabase_write_service.insert_pen(pen_id, cleaned_data)
            return {
                "success": True,
                "message": "Pen created successfully.",
                "pen_id": pen_id,
                "source": {
                    "writes_to_google_sheets": False,
                    "writes_to_supabase": True,
                },
            }
        except Exception:
            pass

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Pen created successfully.",
        "pen_id": pen_id,
    }

def _create_pig_rows_for_litter(
    litter_id: str,
    mother_pig_id: str,
    father_pig_id: str,
    mother_tag: str,
    father_tag: str,
    farrowing_date,
    total_born,
    current_pen_id: str,
    born_alive=None,
    stillborn_count=None,
):
    if not litter_id or not mother_pig_id or not farrowing_date or total_born in (None, "", 0):
        return 0

    try:
        total_born_int = int(total_born)
    except (TypeError, ValueError):
        return 0

    if total_born_int <= 0:
        return 0

    def _positive_int_or_none(value):
        if value in (None, ""):
            return None
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            return None
        return max(parsed_value, 0)

    born_alive_int = _positive_int_or_none(born_alive)
    stillborn_int = _positive_int_or_none(stillborn_count) or 0

    if born_alive_int is None:
        born_alive_int = max(total_born_int - stillborn_int, 0)

    if born_alive_int + stillborn_int > total_born_int:
        stillborn_int = max(total_born_int - born_alive_int, 0)

    if born_alive_int > total_born_int:
        born_alive_int = total_born_int

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    existing_rows = get_all_records(pig_master_sheet)

    existing_for_litter = 0
    for row in existing_rows:
        if to_clean_string(row.get("Litter_ID", "")) == litter_id:
            existing_for_litter += 1

    if existing_for_litter > 0:
        return 0

    today_str = datetime.now().strftime("%d %b %Y")
    birth_month = farrowing_date.strftime("%m") if farrowing_date else ""
    birth_year = farrowing_date.strftime("%Y") if farrowing_date else ""

    created_count = 0

    def _append_generated_piglet(status, on_farm, exit_date="", exit_reason="", notes=""):
        row_values = [
            generate_pig_id(),                                 # Pig_ID
            "",                                                # Tag_Number
            "",                                                # Pig_Name
            status,                                            # Status
            on_farm,                                           # On_Farm
            "Piglet",                                          # Animal_Type
            "",                                                # Sex
            format_date_for_sheet(farrowing_date),             # Date_Of_Birth
            birth_month,                                       # Birth_Month
            birth_year,                                        # Birth_Year
            "",                                                # Breed_Type
            "",                                                # Colour_Markings
            litter_id,                                         # Litter_ID
            total_born_int,                                    # Litter_Size_Born
            "",                                                # Litter_Size_Weaned
            mother_pig_id,                                     # Mother_Pig_ID
            father_pig_id,                                     # Father_Pig_ID
            mother_tag,                                        # Mother_Tag_Number
            father_tag,                                        # Father_Tag_Number
            "",                                                # Maternal_Line
            "",                                                # Paternal_Line
            "Unknown",                                         # Purpose
            "",                                                # Current_Stage
            current_pen_id,                                    # Current_Pen_ID
            "Born_on_Farm",                                    # Source
            "",                                                # Acquisition_Date
            "",                                                # Birth_Weight_Kg
            "",                                                # Wean_Date
            "",                                                # Wean_Weight_Kg
            exit_date,                                         # Exit_Date
            exit_reason,                                       # Exit_Reason
            "",                                                # Exit_Order_ID
            "",                                                # Carcass_Weight_Kg
            notes,                                             # General_Notes
            today_str,                                         # Created_At
            today_str,                                         # Updated_At
        ]

        append_row(pig_master_sheet, row_values)
        return 1

    for _ in range(born_alive_int):
        created_count += _append_generated_piglet(
            status="Active",
            on_farm="Yes",
        )

    stillborn_exit_date = format_date_for_sheet(farrowing_date)
    for _ in range(stillborn_int):
        created_count += _append_generated_piglet(
            status="Dead",
            on_farm="No",
            exit_date=stillborn_exit_date,
            exit_reason="Stillborn",
            notes="Stillborn recorded at litter creation.",
        )

    return created_count


def _litter_generated_piglet_count(total_born, born_alive=None, stillborn_count=None):
    if total_born in (None, "", 0):
        return 0
    try:
        total_born_int = int(total_born)
    except (TypeError, ValueError):
        return 0
    if total_born_int <= 0:
        return 0

    def _positive_int_or_none(value):
        if value in (None, ""):
            return None
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            return None
        return max(parsed_value, 0)

    born_alive_int = _positive_int_or_none(born_alive)
    stillborn_int = _positive_int_or_none(stillborn_count) or 0
    if born_alive_int is None:
        born_alive_int = max(total_born_int - stillborn_int, 0)
    if born_alive_int > total_born_int:
        born_alive_int = total_born_int
    if born_alive_int + stillborn_int > total_born_int:
        stillborn_int = max(total_born_int - born_alive_int, 0)
    return born_alive_int + stillborn_int


def save_new_litter(cleaned_data: dict):
    parent_ids = [
        cleaned_data["mother_pig_id"],
        cleaned_data["father_pig_id"],
    ]
    supabase_parent_rows = _try_supabase_read(
        farm_supabase_read_service.get_pig_master_rows_by_ids,
        parent_ids,
    )
    if (
        supabase_parent_rows is not None
        and farm_supabase_write_service.farm_supabase_writes_available()
    ):
        columns = PIG_WEIGHTS_CONFIG["columns"]
        pig_lookup = _build_pig_lookup(supabase_parent_rows, columns)
        mother_row = pig_lookup.get(cleaned_data["mother_pig_id"])
        father_row = pig_lookup.get(cleaned_data["father_pig_id"]) if cleaned_data["father_pig_id"] else None
        mother_tag = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
        father_tag = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""
        litter_id = generate_litter_id()
        piglet_count = _litter_generated_piglet_count(
            cleaned_data["total_born"],
            cleaned_data["born_alive"],
            cleaned_data["stillborn_count"],
        )
        try:
            result = farm_supabase_write_service.create_litter_with_generated_piglets(
                litter_id,
                cleaned_data,
                mother_tag=mother_tag,
                father_tag=father_tag,
                pig_ids=[generate_pig_id() for _ in range(piglet_count)],
            )

            mating_id = str(cleaned_data.get("mating_id", "")).strip()
            if mating_id:
                link_litter_to_mating(
                    mating_id=mating_id,
                    litter_id=litter_id,
                    actual_farrowing_date=cleaned_data["farrowing_date"]
                )

            return {
                "success": True,
                "message": "Litter created successfully.",
                "litter_id": litter_id,
                "pig_rows_created": result.get("pig_rows_created", 0),
                "source": {
                    "writes_to_supabase": True,
                    "writes_to_sheets": False,
                },
            }
        except Exception:
            pass

    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_lookup = _build_pig_lookup(pig_rows, columns)

    mother_row = pig_lookup.get(cleaned_data["mother_pig_id"])
    father_row = pig_lookup.get(cleaned_data["father_pig_id"]) if cleaned_data["father_pig_id"] else None

    mother_tag = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
    father_tag = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"]
    litter_id = generate_litter_id()

    row_values = [
        litter_id,
        format_date_for_sheet(cleaned_data["farrowing_date"]),
        cleaned_data["mother_pig_id"],
        cleaned_data["father_pig_id"],
        mother_tag,
        father_tag,
        cleaned_data["total_born"] if cleaned_data["total_born"] is not None else "",
        cleaned_data["born_alive"] if cleaned_data["born_alive"] is not None else "",
        cleaned_data["stillborn_count"] if cleaned_data["stillborn_count"] is not None else "",
        cleaned_data["mummified_count"] if cleaned_data["mummified_count"] is not None else "",
        cleaned_data["male_count"] if cleaned_data["male_count"] is not None else "",
        cleaned_data["female_count"] if cleaned_data["female_count"] is not None else "",
        cleaned_data["fostered_in_count"] if cleaned_data["fostered_in_count"] is not None else "",
        cleaned_data["fostered_out_count"] if cleaned_data["fostered_out_count"] is not None else "",
        cleaned_data["weaned_count"] if cleaned_data["weaned_count"] is not None else "",
        format_date_for_sheet(cleaned_data["wean_date"]),
        cleaned_data["average_wean_weight_kg"] if cleaned_data["average_wean_weight_kg"] is not None else "",
        cleaned_data["notes"],
        datetime.now().strftime("%d %b %Y"),
        cleaned_data["current_pen_id"],
    ]

    append_row(sheet_name, row_values)

    pig_rows_created = _create_pig_rows_for_litter(
        litter_id=litter_id,
        mother_pig_id=cleaned_data["mother_pig_id"],
        father_pig_id=cleaned_data["father_pig_id"],
        mother_tag=mother_tag,
        father_tag=father_tag,
        farrowing_date=cleaned_data["farrowing_date"],
        total_born=cleaned_data["total_born"],
        current_pen_id=cleaned_data["current_pen_id"],
        born_alive=cleaned_data["born_alive"],
        stillborn_count=cleaned_data["stillborn_count"],
    )

    mating_id = str(cleaned_data.get("mating_id", "")).strip()
    if mating_id:
        link_litter_to_mating(
            mating_id=mating_id,
            litter_id=litter_id,
            actual_farrowing_date=cleaned_data["farrowing_date"]
        )

    return {
        "success": True,
        "message": "Litter created successfully.",
        "litter_id": litter_id,
        "pig_rows_created": pig_rows_created,
        "source": {
            "writes_to_supabase": False,
            "writes_to_sheets": True,
        },
    }


def save_weight_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    target_date = cleaned_data["weight_date"]

    if not cleaned_data.get("allow_duplicate", False):
        supabase_duplicate_checked = False
        if farm_supabase_write_service.farm_supabase_writes_available():
            try:
                existing = farm_supabase_write_service.get_weight_event(
                    cleaned_data["pig_id"],
                    target_date,
                )
                supabase_duplicate_checked = True
                if existing:
                    return {
                        "success": False,
                        "duplicate_weight": True,
                        "message": "Already recorded for this date.",
                        "existing": {
                            "weight_log_id": to_clean_string(existing.get("weight_event_id", "")),
                            "pig_id": to_clean_string(existing.get("pig_id", "")),
                            "weight_date": format_date_for_json(existing.get("weight_date", "")),
                            "weight_kg": to_float(existing.get("weight_kg", "")),
                            "weighed_by": to_clean_string(existing.get("weighed_by", "")),
                            "condition_notes": to_clean_string(existing.get("condition_notes", "")),
                        },
                    }
            except Exception:
                pass

        if not supabase_duplicate_checked:
            weight_rows = get_all_records(sheet_name)
            for row in weight_rows:
                row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
                row_date = parse_sheet_date(row.get(columns["weight_date"], ""))

                if row_pig_id == cleaned_data["pig_id"] and row_date == target_date:
                    return {
                        "success": False,
                        "duplicate_weight": True,
                        "message": "Already recorded for this date.",
                        "existing": {
                            "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
                            "pig_id": row_pig_id,
                            "weight_date": format_date_for_json(row.get(columns["weight_date"], "")),
                            "weight_kg": to_float(row.get(columns["weight_kg"], "")),
                            "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
                            "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
                        },
                    }

    weight_log_id = generate_weight_log_id()
    row_values = [
        weight_log_id,
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["weight_date"]),
        cleaned_data["weight_kg"],
        cleaned_data["weighed_by"],
        "",
        cleaned_data["condition_notes"],
        "",
        format_date_for_sheet(cleaned_data["weight_date"]),
    ]

    if farm_supabase_write_service.farm_supabase_writes_available():
        try:
            farm_supabase_write_service.insert_weight_event(weight_log_id, cleaned_data)
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
                "latest": latest_info,
                "source": {
                    "writes_to_google_sheets": False,
                    "writes_to_supabase": True,
                },
            }
        except Exception:
            pass

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

def save_weight_entry_with_optional_move(cleaned_data: dict):
    weight_result = save_weight_entry({
        "pig_id": cleaned_data["pig_id"],
        "weight_date": cleaned_data["weight_date"],
        "weight_kg": cleaned_data["weight_kg"],
        "condition_notes": cleaned_data["condition_notes"],
        "weighed_by": cleaned_data["weighed_by"],
        "allow_duplicate": cleaned_data.get("allow_duplicate", False),
    })

    if not weight_result.get("success"):
        return weight_result

    moved_to_pen_id = to_clean_string(cleaned_data.get("moved_to_pen_id", ""))
    movement_logged = False
    movement_result = None

    if moved_to_pen_id:
        current_pen_id = ""
        if farm_supabase_write_service.farm_supabase_writes_available():
            try:
                current_pen_id = farm_supabase_write_service.get_current_pen_id(cleaned_data["pig_id"])
            except Exception:
                current_pen_id = ""
        if not current_pen_id:
            overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
            columns = PIG_WEIGHTS_CONFIG["columns"]
            overview_rows = get_all_records(overview_sheet)

            for row in overview_rows:
                row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
                if row_pig_id == cleaned_data["pig_id"]:
                    current_pen_id = to_clean_string(row.get(columns["current_pen_id"], ""))
                    break

        if moved_to_pen_id != current_pen_id:
            movement_result = save_movement_entry({
                "pig_id": cleaned_data["pig_id"],
                "move_date": cleaned_data["weight_date"],
                "from_pen_id": current_pen_id,
                "to_pen_id": moved_to_pen_id,
                "reason_for_move": "Moved during weight capture",
                "moved_by": "WebApp",
                "move_notes": "",
            })
            movement_logged = True

    return {
        "success": True,
        "message": "Weight entry saved successfully.",
        "saved": weight_result.get("saved", {}),
        "latest": weight_result.get("latest", {}),
        "movement_logged": movement_logged,
        "movement": movement_result.get("saved", {}) if movement_result else None,
    }


def _bulk_weight_existing_key(row, columns):
    pig_id = to_clean_string(row.get(columns["pig_id"], ""))
    weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
    return (pig_id, weight_date)


def _bulk_batch_id(batch_date):
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    date_part = batch_date.strftime("%Y%m%d") if batch_date else "nodate"
    return f"BWB-{date_part}-{stamp}"


def _bulk_audit_headers(sheet_name):
    if sheet_name == BULK_WEIGHT_BATCH_AUDIT_SHEET:
        return BULK_WEIGHT_BATCH_AUDIT_HEADERS
    if sheet_name == BULK_WEIGHT_ROW_AUDIT_SHEET:
        return BULK_WEIGHT_ROW_AUDIT_HEADERS
    return []


def _bulk_audit_append(sheet_name, row_values):
    try:
        ensure_worksheet(sheet_name, _bulk_audit_headers(sheet_name))
        append_row(sheet_name, row_values)
        return {"success": True, "sheet": sheet_name}
    except Exception as exc:
        return {
            "success": False,
            "sheet": sheet_name,
            "error": str(exc),
        }


def _write_bulk_batch_audit(batch_id, payload, result, batch_date):
    uploaded_at = datetime.now()
    audit = {
        "batch_log": None,
        "row_log": None,
        "warnings": [],
    }
    rows = payload.get("rows", [])
    batch_log = _bulk_audit_append(BULK_WEIGHT_BATCH_AUDIT_SHEET, [
        batch_id,
        uploaded_at.isoformat(timespec="seconds"),
        format_date_for_sheet(batch_date),
        to_clean_string(payload.get("weighed_by", "")) or "WebApp",
        len(rows) if isinstance(rows, list) else 0,
        result.get("saved_count", 0),
        result.get("movement_count", 0),
        result.get("duplicate_weight_count", 0),
        result.get("skipped_count", 0),
        result.get("blocked_count", 0),
        result.get("failed_count", 0),
        result.get("message", ""),
    ])
    audit["batch_log"] = batch_log
    if not batch_log.get("success"):
        audit["warnings"].append(
            f"Could not write {BULK_WEIGHT_BATCH_AUDIT_SHEET}: {batch_log.get('error')}"
        )

    row_log_results = []
    row_events = []
    for row in result.get("saved_rows", []):
        row_events.append(("saved_weight", row))
    for row in result.get("movement_rows", []):
        row_events.append(("saved_movement", row))
    for row in result.get("blocked_rows", []):
        row_events.append(("blocked", row))
    for row in result.get("failed_rows", []):
        row_events.append(("failed", row.get("row", row)))

    for event_type, row in row_events:
        row_log_results.append(_bulk_audit_append(BULK_WEIGHT_ROW_AUDIT_SHEET, [
            batch_id,
            uploaded_at.isoformat(timespec="seconds"),
            event_type,
            row.get("row_index", ""),
            row.get("pig_id", ""),
            row.get("tag_number", ""),
            format_date_for_sheet(batch_date),
            row.get("weight_kg", ""),
            row.get("from_pen_id", row.get("current_pen_id", "")),
            row.get("to_pen_id", row.get("moved_to_pen_id", "")),
            row.get("reason", row.get("condition_notes", "")),
        ]))

    failed_row_logs = [item for item in row_log_results if not item.get("success")]
    audit["row_log"] = {
        "attempted": len(row_log_results),
        "written": len(row_log_results) - len(failed_row_logs),
        "failed": len(failed_row_logs),
    }
    if failed_row_logs:
        audit["warnings"].append(
            f"Could not write {len(failed_row_logs)} {BULK_WEIGHT_ROW_AUDIT_SHEET} row audit item(s)."
        )

    return audit


def preflight_bulk_weight_entries(payload: dict):
    columns = PIG_WEIGHTS_CONFIG["columns"]
    batch_date = parse_sheet_date(payload.get("weight_date", ""))
    weighed_by = to_clean_string(payload.get("weighed_by", "")) or "WebApp"
    source_rows = payload.get("rows", [])

    if not batch_date:
        return {
            "ok": False,
            "success": False,
            "error": "validation_error",
            "errors": ["Weight_Date is required and must be a valid date."],
            "submitted_count": len(source_rows) if isinstance(source_rows, list) else 0,
            "visible_count": len(source_rows) if isinstance(source_rows, list) else 0,
            "expected_count": 0,
            "accepted_rows": [],
            "blocked_rows": [],
            "skipped_rows": [],
        }, 400

    if not isinstance(source_rows, list):
        return {
            "ok": False,
            "success": False,
            "error": "validation_error",
            "errors": ["Rows must be a list."],
            "submitted_count": 0,
            "visible_count": 0,
            "expected_count": 0,
            "accepted_rows": [],
            "blocked_rows": [],
            "skipped_rows": [],
        }, 400

    active_pigs = {pig["pig_id"]: pig for pig in get_active_pigs()}
    active_pen_ids = {pen["pen_id"] for pen in get_pens()}
    weight_rows = _try_supabase_read(farm_supabase_read_service.get_weight_events_for_date, batch_date)
    if weight_rows is None:
        weight_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"])
    existing_weights = {_bulk_weight_existing_key(row, columns): row for row in weight_rows}

    accepted_rows = []
    blocked_rows = []
    skipped_rows = []
    seen_batch_keys = set()

    for index, row in enumerate(source_rows):
        if not isinstance(row, dict):
            blocked_rows.append({
                "row_index": index,
                "pig_id": "",
                "tag_number": "",
                "reason": "Row must be an object.",
            })
            continue

        pig_id = to_clean_string(row.get("pig_id", ""))
        tag_number = to_clean_string(row.get("tag_number", ""))
        weight_value = row.get("weight_kg", "")
        moved_to_pen_id = to_clean_string(row.get("moved_to_pen_id", ""))
        condition_notes = to_clean_string(row.get("condition_notes", ""))

        errors = []
        parsed_weight = to_float(weight_value)
        has_weight = not (weight_value in (None, "") or str(weight_value).strip() == "")

        if not pig_id or pig_id not in active_pigs:
            errors.append("Pig is not active/on-farm or could not be found.")
        if has_weight and parsed_weight is None:
            errors.append("Weight must be a valid number.")
        elif has_weight and parsed_weight <= 0:
            errors.append("Weight must be greater than 0.")
        if moved_to_pen_id and moved_to_pen_id not in active_pen_ids:
            errors.append("Selected new pen is not active or could not be found.")

        batch_key = (pig_id, batch_date)
        if batch_key in seen_batch_keys:
            errors.append("This pig appears more than once in this batch.")

        pig = active_pigs.get(pig_id, {})
        current_pen_id = to_clean_string(pig.get("current_pen_id", ""))
        has_pen_change = bool(moved_to_pen_id and moved_to_pen_id != current_pen_id)
        duplicate_weight = bool(has_weight and batch_key in existing_weights)
        if duplicate_weight and not has_pen_change:
            errors.append("Already recorded for this date.")

        if errors:
            existing = existing_weights.get(batch_key, {})
            blocked_rows.append({
                "row_index": index,
                "pig_id": pig_id,
                "tag_number": tag_number or active_pigs.get(pig_id, {}).get("tag_number", ""),
                "weight_kg": parsed_weight,
                "moved_to_pen_id": moved_to_pen_id,
                "condition_notes": condition_notes,
                "reason": " ".join(errors),
                "existing": {
                    "weight_log_id": to_clean_string(existing.get(columns["weight_log_id"], "")),
                    "weight_date": format_date_for_json(existing.get(columns["weight_date"], "")),
                    "weight_kg": to_float(existing.get(columns["weight_kg"], "")),
                } if existing else {},
            })
            continue

        if not has_weight and not has_pen_change:
            skipped_rows.append({
                "row_index": index,
                "pig_id": pig_id,
                "tag_number": tag_number or pig.get("tag_number", ""),
                "reason": "No new weight or pen change entered.",
            })
            continue

        if not has_weight and moved_to_pen_id and not has_pen_change:
            skipped_rows.append({
                "row_index": index,
                "pig_id": pig_id,
                "tag_number": tag_number or pig.get("tag_number", ""),
                "reason": "No weight entered and selected pen is already current.",
            })
            continue

        if has_weight:
            seen_batch_keys.add(batch_key)
        action_type = "weight"
        if duplicate_weight and has_pen_change:
            action_type = "duplicate_weight_movement"
        elif not has_weight and has_pen_change:
            action_type = "movement_only"

        accepted_rows.append({
            "row_index": index,
            "action_type": action_type,
            "pig_id": pig_id,
            "tag_number": tag_number or pig.get("tag_number", ""),
            "weight_date": format_date_for_json(batch_date),
            "weight_kg": parsed_weight if has_weight else None,
            "weighed_by": weighed_by,
            "moved_to_pen_id": moved_to_pen_id,
            "condition_notes": condition_notes,
            "current_pen_id": current_pen_id,
            "current_pen_name": pig.get("current_pen_name", ""),
            "duplicate_weight": duplicate_weight,
            "movement_planned": has_pen_change,
            "existing_weight": {
                "weight_log_id": to_clean_string(existing_weights.get(batch_key, {}).get(columns["weight_log_id"], "")),
                "weight_date": format_date_for_json(existing_weights.get(batch_key, {}).get(columns["weight_date"], "")),
                "weight_kg": to_float(existing_weights.get(batch_key, {}).get(columns["weight_kg"], "")),
            } if duplicate_weight else {},
        })

    preflight_success = len(blocked_rows) == 0
    return {
        "ok": preflight_success,
        "success": preflight_success,
        "message": "Batch preflight passed." if len(blocked_rows) == 0 else "Batch has rows that need attention.",
        "submitted_count": len(source_rows),
        "visible_count": len(source_rows),
        "expected_count": len(accepted_rows),
        "processed_count": 0,
        "success_count": 0,
        "failed_count": 0,
        "accepted_count": len(accepted_rows),
        "weight_count": sum(1 for row in accepted_rows if row["action_type"] == "weight"),
        "movement_only_count": sum(1 for row in accepted_rows if row["action_type"] == "movement_only"),
        "duplicate_weight_movement_count": sum(1 for row in accepted_rows if row["action_type"] == "duplicate_weight_movement"),
        "blocked_count": len(blocked_rows),
        "skipped_count": len(skipped_rows),
        "accepted_rows": accepted_rows,
        "blocked_rows": blocked_rows,
        "skipped_rows": skipped_rows,
        "writes_to_google_sheets": False,
    }, 200


def save_bulk_weight_entries(payload: dict):
    preflight, status_code = preflight_bulk_weight_entries(payload)
    if status_code != 200:
        return preflight, status_code

    batch_date = parse_sheet_date(payload.get("weight_date", ""))
    batch_id = _bulk_batch_id(batch_date)
    accepted_rows = preflight.get("accepted_rows", [])
    if preflight.get("accepted_count", 0) == 0:
        return {
            "ok": False,
            "success": False,
            "error": "no_bulk_rows_ready",
            "status": "no_bulk_rows_ready",
            "batch_id": batch_id,
            "operation_id": batch_id,
            "message": "No new weight rows were ready to upload.",
            "submitted_count": len(payload.get("rows", []) if isinstance(payload.get("rows"), list) else []),
            "expected_count": 0,
            "processed_count": 0,
            "success_count": 0,
            "saved_count": 0,
            "movement_count": 0,
            "skipped_count": preflight.get("skipped_count", 0),
            "blocked_count": preflight.get("blocked_count", 0),
            "failed_count": 0,
            "duplicate_weight_count": 0,
            "blocked_rows": preflight.get("blocked_rows", []),
            "skipped_rows": preflight.get("skipped_rows", []),
            "failed_rows": [],
            "row_results": _bulk_row_results([], [], [], preflight.get("blocked_rows", []), preflight.get("skipped_rows", [])),
            "retry_safe": True,
            "idempotency_basis": "pig_id + weight_date duplicate preflight protection",
            "writes_to_google_sheets": False,
            "writes_to_supabase": False,
        }, 409 if preflight.get("blocked_count", 0) else 400

    saved_rows = []
    movement_rows = []
    failed_rows = []
    movement_count = 0
    duplicate_weight_count = 0

    for row in accepted_rows:
        action_type = row.get("action_type", "weight")
        if row.get("duplicate_weight"):
            duplicate_weight_count += 1

        if action_type in {"movement_only", "duplicate_weight_movement"}:
            try:
                movement_result = save_movement_entry({
                    "pig_id": row["pig_id"],
                    "move_date": parse_sheet_date(row["weight_date"]),
                    "from_pen_id": row.get("current_pen_id", ""),
                    "to_pen_id": row.get("moved_to_pen_id", ""),
                    "reason_for_move": (
                        "Moved during duplicate weight review"
                        if action_type == "duplicate_weight_movement"
                        else "Moved during bulk capture"
                    ),
                    "moved_by": "WebApp",
                    "move_notes": row.get("condition_notes", ""),
                })
            except Exception as exc:
                failed_rows.append({
                    "row": row,
                    "error": {"success": False, "status": "movement_save_exception", "message": str(exc)},
                })
                continue

            if not movement_result.get("success", True):
                failed_rows.append({
                    "row": row,
                    "error": movement_result,
                })
                continue

            movement_count += 1
            saved_movement = {
                **row,
                **movement_result.get("saved", {}),
            }
            movement_rows.append(saved_movement)
            continue

        try:
            result = save_weight_entry_with_optional_move({
                "pig_id": row["pig_id"],
                "weight_date": parse_sheet_date(row["weight_date"]),
                "weight_kg": row["weight_kg"],
                "condition_notes": row.get("condition_notes", ""),
                "weighed_by": row.get("weighed_by", "WebApp"),
                "moved_to_pen_id": row.get("moved_to_pen_id", ""),
                "allow_duplicate": False,
            })
        except Exception as exc:
            failed_rows.append({
                "row": row,
                "error": {"success": False, "status": "weight_save_exception", "message": str(exc)},
            })
            continue

        if not result.get("success"):
            failed_rows.append({
                "row": row,
                "error": result,
            })
            continue

        if result.get("movement_logged"):
            movement_count += 1
            movement_rows.append({
                **row,
                **(result.get("movement") or {}),
            })
        saved_rows.append({
            **row,
            **result.get("saved", {}),
        })

    blocked_count = preflight.get("blocked_count", 0)
    failed_count = len(failed_rows)
    skipped_count = preflight.get("skipped_count", 0)
    processed_count = len(accepted_rows)
    success_count = len(saved_rows) + len(movement_rows)
    partial_count = blocked_count + failed_count
    success = partial_count == 0 and success_count > 0
    status_text = "ok" if success else "partial_failure" if success_count else "failed"
    message = (
        "Bulk weight batch uploaded successfully."
        if success else
        "Bulk weight batch has rows that need owner review. No silent partial success was reported."
        if success_count else
        "No new weight rows were uploaded. Review failed, blocked, or skipped rows."
    )
    result = {
        "ok": success,
        "success": success,
        "error": "" if success else status_text,
        "status": status_text,
        "batch_id": batch_id,
        "operation_id": batch_id,
        "message": message,
        "submitted_count": len(payload.get("rows", []) if isinstance(payload.get("rows"), list) else []),
        "expected_count": len(accepted_rows),
        "processed_count": processed_count,
        "success_count": success_count,
        "saved_count": len(saved_rows),
        "movement_count": movement_count,
        "movement_only_count": len([row for row in movement_rows if row.get("action_type") == "movement_only"]),
        "duplicate_weight_count": duplicate_weight_count,
        "skipped_count": skipped_count,
        "blocked_count": blocked_count,
        "failed_count": failed_count,
        "saved_rows": saved_rows,
        "movement_rows": movement_rows,
        "blocked_rows": preflight.get("blocked_rows", []),
        "skipped_rows": preflight.get("skipped_rows", []),
        "failed_rows": failed_rows,
        "row_results": _bulk_row_results(saved_rows, movement_rows, failed_rows, preflight.get("blocked_rows", []), preflight.get("skipped_rows", [])),
        "retry_safe": True,
        "idempotency_basis": "pig_id + weight_date duplicate preflight protection",
        "writes_to_google_sheets": bool(success_count),
        "writes_to_supabase": False,
    }
    try:
        result["audit"] = _write_bulk_batch_audit(batch_id, payload, result, batch_date)
    except Exception as exc:
        result["audit"] = {
            "batch_log": {"success": False, "error": str(exc)},
            "row_log": {"attempted": 0, "written": 0, "failed": 0},
            "warnings": [f"Could not write bulk batch audit: {exc}"],
        }
        if result["success"]:
            result["ok"] = False
            result["success"] = False
            result["error"] = "audit_write_failed"
            result["status"] = "partial_failure"
            result["message"] = "Bulk rows were processed, but the audit trail failed. Draft kept for owner review."
    return result, 201 if result.get("success") else 207 if success_count else 409


def _bulk_row_results(saved_rows, movement_rows, failed_rows, blocked_rows, skipped_rows):
    row_results = []
    for row in saved_rows or []:
        row_results.append(_bulk_row_result("saved_weight", row, "Weight saved."))
    for row in movement_rows or []:
        row_results.append(_bulk_row_result("saved_movement", row, "Movement saved."))
    for item in failed_rows or []:
        row = item.get("row", {}) if isinstance(item, dict) else {}
        error = item.get("error", {}) if isinstance(item, dict) and isinstance(item.get("error"), dict) else {}
        row_results.append(_bulk_row_result("failed", row, error.get("message") or error.get("status") or "Save failed."))
    for row in blocked_rows or []:
        row_results.append(_bulk_row_result("blocked", row, row.get("reason") or "Blocked by preflight."))
    for row in skipped_rows or []:
        row_results.append(_bulk_row_result("skipped", row, row.get("reason") or "Skipped by preflight."))
    return sorted(row_results, key=lambda item: item.get("row_index") if item.get("row_index") is not None else 999999)


def _bulk_row_result(status, row, message):
    row = row if isinstance(row, dict) else {}
    return {
        "row_index": row.get("row_index"),
        "pig_id": row.get("pig_id", ""),
        "tag_number": row.get("tag_number", ""),
        "action_type": row.get("action_type", ""),
        "status": status,
        "message": to_clean_string(message),
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

    medical_log_id = generate_medical_log_id()
    row_values = [
        medical_log_id,
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

    if farm_supabase_write_service.farm_supabase_writes_available():
        try:
            farm_supabase_write_service.insert_medical_event(
                medical_log_id,
                cleaned_data,
                product=product,
                withdrawal_days=withdrawal_days_int,
                withdrawal_end_date=withdrawal_end_date,
            )
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
                },
                "source": {
                    "writes_to_google_sheets": False,
                    "writes_to_supabase": True,
                },
            }
        except Exception:
            pass

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
    movement_log_id = generate_move_log_id()

    row_values = [
        movement_log_id,
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["move_date"]),
        cleaned_data["from_pen_id"],
        cleaned_data["to_pen_id"],
        cleaned_data["reason_for_move"],
        cleaned_data["moved_by"],
        "",
        cleaned_data["move_notes"],
        format_date_for_sheet(cleaned_data["move_date"]),
    ]

    if farm_supabase_write_service.farm_supabase_writes_available():
        try:
            farm_supabase_write_service.insert_location_event(movement_log_id, cleaned_data)
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
                },
                "source": {
                    "writes_to_google_sheets": False,
                    "writes_to_supabase": True,
                },
            }
        except Exception:
            pass

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
