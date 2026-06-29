import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.pig_weights.pig_weights_utils import format_date_for_json, to_float
from services.google_sheets_service import get_all_records


PIG_MASTER_SHEET = "PIG_MASTER"
PEN_REGISTER_SHEET = "PEN_REGISTER"
WEIGHT_LOG_SHEET = "WEIGHT_LOG"
LOCATION_HISTORY_SHEET = "LOCATION_HISTORY"
MEDICAL_LOG_SHEET = "MEDICAL_LOG"
PRODUCT_REGISTER_SHEET = "PRODUCT_REGISTER"
LITTERS_SHEET = "LITTERS"
MATING_LOG_SHEET = "MATING_LOG"
SYSTEM_SETTINGS_SHEET = "SYSTEM_SETTINGS"

FORMULA_SHEETS = [
    "PIG_OVERVIEW",
    "SALES_AVAILABILITY",
    "SALES_STOCK_DETAIL",
    "SALES_STOCK_SUMMARY",
    "SALES_STOCK_TOTALS",
    "LITTER_OVERVIEW",
    "MATING_OVERVIEW",
]

SOURCE_SHEETS = [
    PIG_MASTER_SHEET,
    PEN_REGISTER_SHEET,
    WEIGHT_LOG_SHEET,
    LOCATION_HISTORY_SHEET,
    MEDICAL_LOG_SHEET,
    PRODUCT_REGISTER_SHEET,
    LITTERS_SHEET,
    MATING_LOG_SHEET,
    SYSTEM_SETTINGS_SHEET,
]

SHEETS = SOURCE_SHEETS + FORMULA_SHEETS
IMPORT_BATCH_ID = "DRY_RUN_ONLY"


def clean(value):
    return str(value or "").strip()


def clean_lower(value):
    return clean(value).lower()


def to_int(value):
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def to_bool(value):
    text = clean_lower(value)
    if not text:
        return None
    if text in {"true", "yes", "y", "1", "active"}:
        return True
    if text in {"false", "no", "n", "0", "inactive"}:
        return False
    return None


def as_date(value):
    return format_date_for_json(value) or None


def first_value(row, *fields):
    for field in fields:
        value = clean(row.get(field))
        if value:
            return value
    return ""


def with_import_trace(payload, source_sheet_row):
    payload["source_sheet_row"] = source_sheet_row
    payload["import_batch_id"] = IMPORT_BATCH_ID
    return payload


def deterministic_id(prefix, *parts):
    raw = "|".join(clean(part) for part in parts if clean(part))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").upper()
    if not slug:
        slug = "UNKNOWN"
    return f"{prefix}-{slug}"[:120]


def make_decision(row_id, decision, reason):
    return {
        "row_id": row_id,
        "decision": decision,
        "reason": reason,
    }


def summarize_decisions(sheet_name, decisions):
    reason_counts = Counter(decision["reason"] for decision in decisions)
    included = sum(1 for decision in decisions if decision["decision"] == "include")
    excluded = sum(1 for decision in decisions if decision["decision"] == "exclude")
    review = sum(1 for decision in decisions if decision["decision"] == "review")
    return {
        "sheet": sheet_name,
        "total_rows": len(decisions),
        "included_rows": included,
        "excluded_rows": excluded,
        "review_rows": review,
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def payload_summary(payloads):
    return {table: len(rows) for table, rows in sorted(payloads.items())}


def classify_required_id(row, field_name):
    row_id = clean(row.get(field_name))
    if not row_id:
        return "", "exclude", f"missing_{field_name.lower()}"
    return row_id, "include", "included"


def map_pen(row, source_sheet_row):
    return with_import_trace({
        "pen_id": clean(row.get("Pen_ID")),
        "pen_name": clean(row.get("Pen_Name")) or None,
        "pen_type": clean(row.get("Pen_Type")) or None,
        "capacity": to_int(row.get("Capacity")),
        "is_active": to_bool(row.get("Is_Active")) if to_bool(row.get("Is_Active")) is not None else True,
        "pen_notes": clean(row.get("Pen_Notes")) or None,
    }, source_sheet_row)


def map_pig(row, source_sheet_row):
    return with_import_trace({
        "pig_id": clean(row.get("Pig_ID")),
        "tag_number": clean(row.get("Tag_Number")) or None,
        "pig_name": clean(row.get("Pig_Name")) or None,
        "status": clean(row.get("Status")) or None,
        "on_farm": to_bool(row.get("On_Farm")),
        "animal_type": clean(row.get("Animal_Type")) or None,
        "sex": clean(row.get("Sex")) or None,
        "date_of_birth": as_date(row.get("Date_Of_Birth")),
        "birth_month": clean(row.get("Birth_Month")) or None,
        "birth_year": to_int(row.get("Birth_Year")),
        "breed_type": clean(row.get("Breed_Type")) or None,
        "colour_markings": clean(row.get("Colour_Markings")) or None,
        "mother_pig_id": first_value(row, "Mother_Pig_ID", "Sow_Pig_ID") or None,
        "father_pig_id": first_value(row, "Father_Pig_ID", "Boar_Pig_ID") or None,
        "litter_id": clean(row.get("Litter_ID")) or None,
        "initial_pen_id": first_value(row, "Initial_Pen_ID", "Current_Pen_ID", "Pen_ID") or None,
        "purpose": clean(row.get("Purpose")) or None,
        "notes": clean(row.get("Notes")) or None,
    }, source_sheet_row)


def map_weight(row, source_sheet_row):
    weight_log_id = clean(row.get("Weight_Log_ID")) or deterministic_id("WGT", row.get("Pig_ID"), row.get("Weight_Date"), source_sheet_row)
    return with_import_trace({
        "weight_event_id": weight_log_id,
        "pig_id": clean(row.get("Pig_ID")),
        "weight_date": as_date(row.get("Weight_Date")),
        "weight_kg": to_float(row.get("Weight_Kg")),
        "weighed_by": clean(row.get("Weighed_By")) or None,
        "scale_used": clean(row.get("Scale_Used")) or None,
        "condition_notes": clean(row.get("Condition_Notes")) or None,
        "stage_at_weighing": clean(row.get("Stage_At_Weighing")) or None,
        "source": "google_sheets_import",
    }, source_sheet_row)


def map_location(row, source_sheet_row):
    move_log_id = clean(row.get("Move_Log_ID")) or deterministic_id("MOVE", row.get("Pig_ID"), row.get("Move_Date"), row.get("To_Pen_ID"), source_sheet_row)
    return with_import_trace({
        "location_event_id": move_log_id,
        "pig_id": clean(row.get("Pig_ID")),
        "move_date": as_date(row.get("Move_Date")),
        "from_pen_id": clean(row.get("From_Pen_ID")) or None,
        "to_pen_id": clean(row.get("To_Pen_ID")) or None,
        "reason_for_move": clean(row.get("Reason_For_Move")) or None,
        "moved_by": clean(row.get("Moved_By")) or None,
        "group_batch_id": clean(row.get("Group_Batch_ID")) or None,
        "move_notes": clean(row.get("Move_Notes")) or None,
        "source": "google_sheets_import",
    }, source_sheet_row)


def map_medical(row, source_sheet_row):
    medical_id = clean(row.get("Medical_Log_ID")) or deterministic_id("MED", row.get("Pig_ID"), row.get("Treatment_Date"), source_sheet_row)
    return with_import_trace({
        "medical_event_id": medical_id,
        "pig_id": clean(row.get("Pig_ID")),
        "treatment_date": as_date(row.get("Treatment_Date")),
        "treatment_type": clean(row.get("Treatment_Type")) or None,
        "product_id": clean(row.get("Product_ID")) or None,
        "product_name": clean(row.get("Product_Name")) or None,
        "dose": clean(row.get("Dose")) or None,
        "dose_unit": clean(row.get("Dose_Unit")) or None,
        "route": clean(row.get("Route")) or None,
        "reason_for_treatment": clean(row.get("Reason_For_Treatment")) or None,
        "batch_lot_number": clean(row.get("Batch_Lot_Number")) or None,
        "withdrawal_days": to_int(row.get("Withdrawal_Days")),
        "withdrawal_end_date": as_date(row.get("Withdrawal_End_Date")),
        "given_by": clean(row.get("Given_By")) or None,
        "follow_up_required": to_bool(row.get("Follow_Up_Required")) or False,
        "follow_up_date": as_date(row.get("Follow_Up_Date")),
        "medical_notes": first_value(row, "Medical_Notes", "Notes") or None,
    }, source_sheet_row)


def map_product(row, source_sheet_row):
    return with_import_trace({
        "product_id": clean(row.get("Product_ID")),
        "product_name": clean(row.get("Product_Name")) or None,
        "product_category": clean(row.get("Product_Category")) or None,
        "default_dose": clean(row.get("Default_Dose")) or None,
        "dose_unit": clean(row.get("Dose_Unit")) or None,
        "default_withdrawal_days": to_int(row.get("Default_Withdrawal_Days")),
        "supplier": clean(row.get("Supplier")) or None,
        "batch_tracking_required": to_bool(row.get("Batch_Tracking_Required")) or False,
        "is_active": to_bool(row.get("Is_Active")) if to_bool(row.get("Is_Active")) is not None else True,
        "product_notes": clean(row.get("Product_Notes")) or None,
    }, source_sheet_row)


def map_litter(row, source_sheet_row):
    return with_import_trace({
        "litter_id": clean(row.get("Litter_ID")),
        "farrowing_date": as_date(row.get("Farrowing_Date")),
        "sow_pig_id": clean(row.get("Sow_Pig_ID")) or None,
        "boar_pig_id": clean(row.get("Boar_Pig_ID")) or None,
        "sow_tag_number": clean(row.get("Sow_Tag_Number")) or None,
        "boar_tag_number": clean(row.get("Boar_Tag_Number")) or None,
        "total_born": to_int(row.get("Total_Born")),
        "born_alive": to_int(row.get("Born_Alive")),
        "stillborn_count": to_int(row.get("Stillborn_Count")),
        "mummified_count": to_int(row.get("Mummified_Count")),
        "male_count": to_int(row.get("Male_Count")),
        "female_count": to_int(row.get("Female_Count")),
        "unknown_sex_count": to_int(row.get("Unknown_Sex_Count")),
        "weaned_count": to_int(row.get("Weaned_Count")),
        "litter_status": clean(row.get("Litter_Status")) or None,
        "litter_notes": first_value(row, "Litter_Notes", "Notes") or None,
    }, source_sheet_row)


def map_mating(row, source_sheet_row):
    return with_import_trace({
        "mating_id": clean(row.get("Mating_ID")),
        "sow_pig_id": clean(row.get("Sow_Pig_ID")) or None,
        "sow_tag_number": clean(row.get("Sow_Tag_Number")) or None,
        "boar_pig_id": clean(row.get("Boar_Pig_ID")) or None,
        "boar_tag_number": clean(row.get("Boar_Tag_Number")) or None,
        "mating_date": as_date(row.get("Mating_Date")),
        "mating_method": clean(row.get("Mating_Method")) or None,
        "exposure_group": clean(row.get("Exposure_Group")) or None,
        "expected_pregnancy_check_date": as_date(row.get("Expected_Pregnancy_Check_Date")),
        "pregnancy_check_date": as_date(row.get("Pregnancy_Check_Date")),
        "pregnancy_check_result": clean(row.get("Pregnancy_Check_Result")) or None,
        "expected_farrowing_date": as_date(row.get("Expected_Farrowing_Date")),
        "farrowing_date": as_date(row.get("Farrowing_Date")),
        "outcome": clean(row.get("Outcome")) or None,
        "related_litter_id": clean(row.get("Related_Litter_ID")) or None,
        "mating_notes": first_value(row, "Mating_Notes", "Notes") or None,
    }, source_sheet_row)


def map_setting(row, source_sheet_row):
    return with_import_trace({
        "setting_key": clean(row.get("Setting_Key")),
        "setting_value": clean(row.get("Setting_Value")) or None,
        "description": clean(row.get("Description")) or None,
    }, source_sheet_row)


MAPPERS = {
    PEN_REGISTER_SHEET: ("pens", "Pen_ID", map_pen),
    PIG_MASTER_SHEET: ("pigs", "Pig_ID", map_pig),
    WEIGHT_LOG_SHEET: ("pig_weight_events", "Pig_ID", map_weight),
    LOCATION_HISTORY_SHEET: ("pig_location_events", "Pig_ID", map_location),
    MEDICAL_LOG_SHEET: ("pig_medical_events", "Pig_ID", map_medical),
    PRODUCT_REGISTER_SHEET: ("farm_products", "Product_ID", map_product),
    LITTERS_SHEET: ("litters", "Litter_ID", map_litter),
    MATING_LOG_SHEET: ("mating_events", "Mating_ID", map_mating),
    SYSTEM_SETTINGS_SHEET: ("app_settings", "Setting_Key", map_setting),
}


def build_payloads_and_decisions(rows):
    payloads = defaultdict(list)
    decisions_by_sheet = {}
    for sheet_name, (target_table, required_field, mapper) in MAPPERS.items():
        decisions = []
        for source_sheet_row, row in enumerate(rows.get(sheet_name, []), start=2):
            row_id, decision, reason = classify_required_id(row, required_field)
            if decision == "include":
                payload = mapper(row, source_sheet_row)
                payloads[target_table].append(payload)
            decisions.append(make_decision(row_id, decision, reason))
        decisions_by_sheet[sheet_name] = decisions
    return dict(payloads), decisions_by_sheet


def collect_link_issues(payloads):
    pig_ids = {row["pig_id"] for row in payloads.get("pigs", []) if clean(row.get("pig_id"))}
    pen_ids = {row["pen_id"] for row in payloads.get("pens", []) if clean(row.get("pen_id"))}
    product_ids = {row["product_id"] for row in payloads.get("farm_products", []) if clean(row.get("product_id"))}
    litter_ids = {row["litter_id"] for row in payloads.get("litters", []) if clean(row.get("litter_id"))}
    issues = defaultdict(Counter)

    for table in ("pig_weight_events", "pig_location_events", "pig_medical_events"):
        for row in payloads.get(table, []):
            if row.get("pig_id") and row["pig_id"] not in pig_ids:
                issues[table]["unknown_pig_id"] += 1

    for row in payloads.get("pig_location_events", []):
        for field in ("from_pen_id", "to_pen_id"):
            if row.get(field) and row[field] not in pen_ids:
                issues["pig_location_events"][f"unknown_{field}"] += 1

    for row in payloads.get("pigs", []):
        if row.get("initial_pen_id") and row["initial_pen_id"] not in pen_ids:
            issues["pigs"]["unknown_initial_pen_id"] += 1
        if row.get("litter_id") and row["litter_id"] not in litter_ids:
            issues["pigs"]["unknown_litter_id"] += 1

    for row in payloads.get("pig_medical_events", []):
        if row.get("product_id") and row["product_id"] not in product_ids:
            issues["pig_medical_events"]["unknown_product_id"] += 1

    for row in payloads.get("litters", []):
        for field in ("sow_pig_id", "boar_pig_id"):
            if row.get(field) and row[field] not in pig_ids:
                issues["litters"][f"unknown_{field}"] += 1

    for row in payloads.get("mating_events", []):
        for field in ("sow_pig_id", "boar_pig_id"):
            if row.get(field) and row[field] not in pig_ids:
                issues["mating_events"][f"unknown_{field}"] += 1
        if row.get("related_litter_id") and row["related_litter_id"] not in litter_ids:
            issues["mating_events"]["unknown_related_litter_id"] += 1

    return {table: dict(sorted(counter.items())) for table, counter in sorted(issues.items())}


def formula_sheet_summary(rows):
    return {
        sheet: {
            "source_rows": len(rows.get(sheet, [])),
            "replacement_strategy": "compare_only_until_formula_equivalence_tests_pass",
        }
        for sheet in FORMULA_SHEETS
    }


def build_farm_import_dry_run(rows):
    payloads, decisions_by_sheet = build_payloads_and_decisions(rows)
    summaries = {
        sheet: summarize_decisions(sheet, decisions)
        for sheet, decisions in decisions_by_sheet.items()
    }
    return {
        "success": True,
        "mode": "dry_run_only",
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "source": "google_sheets",
        "target_boundary": sorted(payloads.keys()),
        "summaries": summaries,
        "formula_sheets": formula_sheet_summary(rows),
        "link_issues": collect_link_issues(payloads),
        "payload_summary": payload_summary(payloads),
        "payloads": payloads,
        "decisions": decisions_by_sheet,
    }


def sample_payloads(payloads, limit):
    return {
        table: rows[:limit]
        for table, rows in sorted(payloads.items())
    }


def load_sheet_rows():
    return {sheet: get_all_records(sheet) for sheet in SHEETS}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Dry-run Google Sheets farm operations migration to canonical Supabase payloads."
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print summaries, link issues, and payload counts without full payload rows.",
    )
    parser.add_argument(
        "--payload-samples",
        type=int,
        default=0,
        help="Include this many mapped payload samples per target table.",
    )
    args = parser.parse_args(argv)

    try:
        sheet_rows = load_sheet_rows()
    except Exception as exc:
        report = {
            "success": False,
            "mode": "dry_run_only",
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "status": "sheet_read_failed",
            "error_type": exc.__class__.__name__,
            "message": "Google Sheets read failed before any migration payload was built.",
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    report = build_farm_import_dry_run(sheet_rows)
    payloads = report["payloads"]
    if args.summary_only:
        report = {
            key: report[key]
            for key in (
                "success",
                "mode",
                "writes_to_supabase",
                "writes_to_sheets",
                "source",
                "target_boundary",
                "summaries",
                "formula_sheets",
                "link_issues",
                "payload_summary",
            )
        }
    if args.payload_samples:
        report["payload_samples"] = sample_payloads(payloads, args.payload_samples)
    report.pop("payloads", None)
    report.pop("decisions", None)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
