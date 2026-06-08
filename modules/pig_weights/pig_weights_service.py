import math
from datetime import datetime, timedelta

from services.google_sheets_service import (
    append_row,
    batch_update_rows_by_id,
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
LITTER_HEALTH_EARMARK_FIELDS = ("Earmarked", "Earmark_Date")
DEFAULT_LITTER_WEAN_AGE_DAYS = 35
WEAN_TAG_ATTENTION_WINDOW_DAYS = 3
LIVE_SALE_TARGET_KG = 60
MEAT_TARGET_MIN_KG = 55
MEAT_TARGET_MAX_KG = 70
SLAUGHTER_TARGET_MIN_KG = 80
SLAUGHTER_TARGET_MAX_KG = 95
STALE_WEIGHT_DAYS = 45
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
    "exceptional_grower_adg_kg_day": EXCEPTIONAL_GROWER_ADG_KG_DAY,
    "good_grower_adg_kg_day": GOOD_GROWER_ADG_KG_DAY,
    "steady_grower_adg_kg_day": STEADY_GROWER_ADG_KG_DAY,
    "slow_grower_adg_kg_day": SLOW_GROWER_ADG_KG_DAY,
    "extremely_slow_grower_adg_kg_day": EXTREMELY_SLOW_GROWER_ADG_KG_DAY,
    "good_litter_survival_rate": GOOD_LITTER_SURVIVAL_RATE,
    "stale_weight_days": STALE_WEIGHT_DAYS,
}


def _allocation_settings():
    return dict(DEFAULT_ALLOCATION_SETTINGS)


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
    rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"])
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


def _pen_name_for_id(pen_lookup, pen_id):
    pen = pen_lookup.get(to_clean_string(pen_id), {})
    return to_clean_string(pen.get("pen_name", ""))


def _sale_stream_for_exit(row):
    status = to_clean_string(row.get("Status", "")).lower()
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
    status = to_clean_string(row.get("Status", "")).lower()
    exit_reason = to_clean_string(row.get("Exit_Reason", "")).lower().replace("-", "_").replace(" ", "_")

    if status == "dead" or exit_reason in {"died", "culled", "lost", "stillborn", "died_after_birth", "crushed_by_sow", "weak_piglet", "unknown"}:
        return "dead"
    if status == "removed" or exit_reason in {"removed", "other"}:
        return "removed"
    if status == "slaughtered" or exit_reason in {"slaughter", "slaughtered", "abattoir", "abattoir_sale", "sold_to_abattoir"}:
        return "slaughtered"
    if status == "sold" or exit_reason in {"sold", "livestock", "livestock_sale", "live_sale", "meat", "meat_sale", "carcass", "carcass_sale", "pork_sale", "processed_meat_sale"}:
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


def get_dashboard_summary():
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

    now = datetime.now()
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
    today = today or datetime.now().date()
    rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_overview"])
    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
    medical_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"])
    newborn_products = _newborn_health_product_ids()
    items = []

    for row in rows:
        litter_id = to_clean_string(row.get("Litter_ID", ""))
        if not litter_id:
            continue

        needs_attention = to_clean_string(row.get("Needs_Attention", ""))
        litter_status = to_clean_string(row.get("Litter_Status", ""))
        active_pig_count = to_float(row.get("Active_Pig_Count", "")) or 0
        wean_timing = _litter_wean_timing(row, today=today)

        reason = ""
        action_type = ""
        newborn_attention = _litter_newborn_health_attention(
            litter_id,
            litter_status,
            row.get("Wean_Date", ""),
            pig_master_rows,
            medical_rows,
            newborn_products,
        )
        if newborn_attention:
            reason = newborn_attention["reason"]
            action_type = newborn_attention["action_type"]
        elif needs_attention == "Yes":
            reason = _litter_attention_reason(row)
            if _is_tag_number_attention(reason) and _wean_tag_attention_is_not_due(wean_timing):
                reason = ""
        elif litter_status == "Weaned" and _litter_needs_purpose_review(litter_id, pig_rows):
            reason = "Weaned - review purpose"

        if not reason:
            continue

        items.append({
            "litter_id": litter_id,
            "sow_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
            "farrowing_date": format_date_for_json(row.get("Farrowing_Date", "")),
            "wean_date": format_date_for_json(row.get("Wean_Date", "")),
            "litter_status": litter_status,
            "needs_attention": needs_attention,
            "reason": reason,
            "action_type": action_type,
            "active_pig_count": active_pig_count,
            "weaned_count": to_float(row.get("Weaned_Count", "")),
            "youngest_age_days": row.get("Youngest_Age_Days", ""),
            "oldest_age_days": row.get("Oldest_Age_Days", ""),
            "estimated_wean_date": _format_optional_json_date(wean_timing["estimated_wean_date"]),
            "wean_tag_attention_start_date": _format_optional_json_date(wean_timing["wean_tag_attention_start_date"]),
            "wean_planning_monday": _format_optional_json_date(wean_timing["wean_planning_monday"]),
            "days_until_estimated_wean": wean_timing["days_until_estimated_wean"],
        })

    return {
        "count": len(items),
        "items": items[:limit],
    }


def _litter_attention_reason(row):
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


def _build_litter_attention(row, pig_master_rows=None, medical_rows=None, newborn_products=None, today=None):
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
    elif needs_attention == "Yes":
        reason = _litter_attention_reason(row)
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
    elif litter_status == "Weaned" and _litter_needs_purpose_review(litter_id):
        reason = "Weaned - review purpose"
        recommended_action = "Litter is already weaned. Review linked piglet purpose/sales classification next."
        action_type = "review_purpose"
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
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
    medical_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"])
    newborn_products = _newborn_health_product_ids()

    for row in rows:
        if to_clean_string(row.get("Litter_ID", "")) == litter_id:
            return _build_litter_attention(row, pig_master_rows, medical_rows, newborn_products)

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


def mark_litter_weaned(litter_id: str, wean_date_value, changed_by: str = "web_app"):
    litter_id = str(litter_id or "").strip()
    wean_date = parse_sheet_date(wean_date_value)

    if not litter_id:
        return {"success": False, "errors": ["Litter ID is required."]}, 400

    if not wean_date:
        return {"success": False, "errors": ["A valid wean date is required."]}, 400

    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    pig_rows = get_all_records(pig_master_sheet)

    active_piglets = []
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

    if not active_piglets:
        return {
            "success": False,
            "errors": ["No active on-farm piglets were found for this litter."],
        }, 409

    weaned_count = len(active_piglets)
    litter_row_updated = _update_litter_weaning_fields(litter_id, wean_date, weaned_count)
    sheet_wean_date = format_date_for_sheet(wean_date)
    today = format_date_for_sheet(datetime.now().date())
    updated_by = to_clean_string(changed_by) or "web_app"

    pig_updates = {
        pig_id: {
            "Litter_Size_Weaned": weaned_count,
            "Wean_Date": sheet_wean_date,
            "Updated_At": today,
        }
        for pig_id in active_piglets
    }
    pig_rows_updated = batch_update_rows_by_id(pig_master_sheet, pig_updates)

    return {
        "success": True,
        "action": "mark_litter_weaned",
        "litter_id": litter_id,
        "wean_date": wean_date.isoformat(),
        "weaned_count": weaned_count,
        "litter_row_updated": litter_row_updated,
        "pig_rows_updated": pig_rows_updated,
        "changed_by": updated_by,
        "message": f"Litter {litter_id} was marked as weaned with {weaned_count} active piglet(s).",
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
    pig_rows = get_all_records(pig_master_sheet)
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
    if not dry_run:
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
    pig_rows = get_all_records(pig_master_sheet)
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
    if not dry_run:
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
            "writes_to_sheets": not dry_run,
            "writes_to_supabase": False,
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
    pig_rows = get_all_records(pig_master_sheet)
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
    if not dry_run:
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
            "writes_to_sheets": not dry_run,
            "writes_to_supabase": False,
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
    pig_rows = get_all_records(pig_master_sheet)
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
    if not dry_run:
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
            "writes_to_sheets": not dry_run,
            "writes_to_supabase": False,
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


def get_parent_options():
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
    elif latest_weight_kg <= settings["meat_target_max_kg"]:
        meat_status = "In meat window"
    else:
        meat_status = "Past meat window"

    if latest_weight_kg is None:
        slaughter_status = "Unknown"
    elif latest_weight_kg < settings["slaughter_target_min_kg"]:
        slaughter_status = "Before abattoir window"
    elif latest_weight_kg <= settings["slaughter_target_max_kg"]:
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
    if bucket in {"Needs Data", "Needs Classification"}:
        return {
            "suggested_purpose": "Needs Review",
            "suggested_purpose_reason": "Complete missing data or confirm classification before assigning a business purpose.",
            "suggested_purpose_confidence": "Low",
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

    if settings["meat_target_min_kg"] <= weight_kg <= settings["meat_target_max_kg"]:
        return "Meat Candidate", "Weight is in the first planned meat-candidate range."

    if settings["slaughter_target_min_kg"] <= weight_kg <= settings["slaughter_target_max_kg"]:
        return "Slaughter Candidate", "Weight is in the first planned slaughter-candidate range."

    if animal_type in {"Grower", "Finisher", "Weaner"}:
        return "Growing", "Pig is active/on farm but not in a current candidate range."

    return "Needs Data", "No trusted allocation rule matched this pig yet."


def get_pig_allocation_readiness(today=None):
    today = today or datetime.now().date()
    settings = _allocation_settings()
    columns = PIG_WEIGHTS_CONFIG["columns"]
    overview_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    weight_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"])
    sales_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["sales_availability"])
    litter_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_overview"])
    pen_lookup = _build_pen_lookup()
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
        "thresholds": settings,
        "business_rules": {
            "source": settings["source"],
            "writes_enabled": settings["writes_enabled"],
            "meat_window_label": f"{settings['meat_target_min_kg']}-{settings['meat_target_max_kg']} kg",
            "abattoir_window_label": f"{settings['slaughter_target_min_kg']}-{settings['slaughter_target_max_kg']} kg",
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

    attention = _litter_attention_for_id(litter_id)
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)
    pig_master_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"])
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
                    "lifecycle_outcomes": lifecycle_outcomes,
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
        "count": len(piglets),
        "male_count": male_count,
        "female_count": female_count,
        "active_count": active_count,
        "average_weight_kg": average_weight,
        "piglets": piglets,
        "attention": attention,
        "lifecycle_outcomes": lifecycle_outcomes,
        **wean_timing,
    }


def get_pig_detail(pig_id: str):
    pig_id = str(pig_id).strip()

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

def get_weight_entries_by_date(weight_date: str):
    parsed_target_date = parse_sheet_date(weight_date)

    if not parsed_target_date:
        return {
            "weight_date": "",
            "count": 0,
            "history": [],
        }

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

    row_values = [
        generate_pig_id(),
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

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Pig created successfully."
    }


def save_new_product(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["product_register"]

    row_values = [
        generate_product_id(),
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

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Product created successfully."
    }


def save_new_pen(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"]

    row_values = [
        generate_pen_id(),
        cleaned_data["pen_name"],
        cleaned_data["pen_type"],
        cleaned_data["capacity"] if cleaned_data["capacity"] is not None else "",
        cleaned_data["is_active"],
        cleaned_data["pen_notes"],
    ]

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Pen created successfully."
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

def save_new_litter(cleaned_data: dict):
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
    }


def save_weight_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    target_date = cleaned_data["weight_date"]

    if not cleaned_data.get("allow_duplicate", False):
        weight_rows = get_all_records(sheet_name)
        for row in weight_rows:
            row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
            row_date = parse_sheet_date(row.get(columns["weight_date"], ""))

            if row_pig_id == cleaned_data["pig_id"] and row_date == target_date:
                return {
                    "success": False,
                    "duplicate_weight": True,
                    "message": "This pig already has a weight entry for this date.",
                    "existing": {
                        "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
                        "pig_id": row_pig_id,
                        "weight_date": format_date_for_json(row.get(columns["weight_date"], "")),
                        "weight_kg": to_float(row.get(columns["weight_kg"], "")),
                        "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
                        "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
                    },
                }

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
        overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
        columns = PIG_WEIGHTS_CONFIG["columns"]
        overview_rows = get_all_records(overview_sheet)

        current_pen_id = ""
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


def preflight_bulk_weight_entries(payload: dict):
    columns = PIG_WEIGHTS_CONFIG["columns"]
    batch_date = parse_sheet_date(payload.get("weight_date", ""))
    weighed_by = to_clean_string(payload.get("weighed_by", "")) or "WebApp"
    source_rows = payload.get("rows", [])

    if not batch_date:
        return {
            "success": False,
            "errors": ["Weight_Date is required and must be a valid date."],
            "accepted_rows": [],
            "blocked_rows": [],
            "skipped_rows": [],
        }, 400

    if not isinstance(source_rows, list):
        return {
            "success": False,
            "errors": ["Rows must be a list."],
            "accepted_rows": [],
            "blocked_rows": [],
            "skipped_rows": [],
        }, 400

    active_pigs = {pig["pig_id"]: pig for pig in get_active_pigs()}
    active_pen_ids = {pen["pen_id"] for pen in get_pens()}
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

        if weight_value in (None, "") or str(weight_value).strip() == "":
            skipped_rows.append({
                "row_index": index,
                "pig_id": pig_id,
                "tag_number": tag_number,
                "reason": "No weight entered.",
            })
            continue

        errors = []
        parsed_weight = to_float(weight_value)

        if not pig_id or pig_id not in active_pigs:
            errors.append("Pig is not active/on-farm or could not be found.")
        if parsed_weight is None:
            errors.append("Weight must be a valid number.")
        elif parsed_weight <= 0:
            errors.append("Weight must be greater than 0.")
        if moved_to_pen_id and moved_to_pen_id not in active_pen_ids:
            errors.append("Selected new pen is not active or could not be found.")

        batch_key = (pig_id, batch_date)
        if batch_key in seen_batch_keys:
            errors.append("This pig appears more than once in this batch.")
        if batch_key in existing_weights:
            errors.append("This pig already has a weight entry for this date.")

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

        seen_batch_keys.add(batch_key)
        pig = active_pigs[pig_id]
        accepted_rows.append({
            "row_index": index,
            "pig_id": pig_id,
            "tag_number": tag_number or pig.get("tag_number", ""),
            "weight_date": format_date_for_json(batch_date),
            "weight_kg": parsed_weight,
            "weighed_by": weighed_by,
            "moved_to_pen_id": moved_to_pen_id,
            "condition_notes": condition_notes,
            "current_pen_id": pig.get("current_pen_id", ""),
            "current_pen_name": pig.get("current_pen_name", ""),
        })

    return {
        "success": len(blocked_rows) == 0,
        "message": "Batch preflight passed." if len(blocked_rows) == 0 else "Batch has rows that need attention.",
        "accepted_count": len(accepted_rows),
        "blocked_count": len(blocked_rows),
        "skipped_count": len(skipped_rows),
        "accepted_rows": accepted_rows,
        "blocked_rows": blocked_rows,
        "skipped_rows": skipped_rows,
        "writes_to_google_sheets": False,
    }, 200


def save_bulk_weight_entries(payload: dict):
    preflight, status_code = preflight_bulk_weight_entries(payload)
    if status_code != 200 or not preflight.get("success"):
        return preflight, 409 if preflight.get("blocked_count", 0) else status_code
    if preflight.get("accepted_count", 0) == 0:
        return {
            "success": False,
            "message": "No weights entered. Nothing to upload.",
            "saved_count": 0,
            "skipped_count": preflight.get("skipped_count", 0),
        }, 400

    saved_rows = []
    movement_count = 0

    for row in preflight.get("accepted_rows", []):
        result = save_weight_entry_with_optional_move({
            "pig_id": row["pig_id"],
            "weight_date": parse_sheet_date(row["weight_date"]),
            "weight_kg": row["weight_kg"],
            "condition_notes": row.get("condition_notes", ""),
            "weighed_by": row.get("weighed_by", "WebApp"),
            "moved_to_pen_id": row.get("moved_to_pen_id", ""),
            "allow_duplicate": False,
        })

        if not result.get("success"):
            return {
                "success": False,
                "message": "Batch upload stopped because a row failed during save.",
                "saved_count": len(saved_rows),
                "saved_rows": saved_rows,
                "failed_row": row,
                "error": result,
            }, 409 if result.get("duplicate_weight") else 500

        if result.get("movement_logged"):
            movement_count += 1
        saved_rows.append(result.get("saved", {}))

    return {
        "success": True,
        "message": "Bulk weight batch uploaded successfully.",
        "saved_count": len(saved_rows),
        "movement_count": movement_count,
        "skipped_count": preflight.get("skipped_count", 0),
        "saved_rows": saved_rows,
    }, 201


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
        generate_move_log_id(),
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
