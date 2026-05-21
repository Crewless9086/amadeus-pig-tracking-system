import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
import re

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.pig_weights.pig_weights_utils import format_date_for_json, to_float
from services.google_sheets_service import get_all_records


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
ORDER_INTAKE_STATE_SHEET = "ORDER_INTAKE_STATE"
ORDER_INTAKE_ITEMS_SHEET = "ORDER_INTAKE_ITEMS"
ORDER_DOCUMENTS_SHEET = "ORDER_DOCUMENTS"
ORDER_STATUS_LOG_SHEET = "ORDER_STATUS_LOG"
SALES_PRICING_SHEET = "SALES_PRICING"

SHEETS = [
    ORDER_MASTER_SHEET,
    ORDER_LINES_SHEET,
    ORDER_INTAKE_STATE_SHEET,
    ORDER_INTAKE_ITEMS_SHEET,
    ORDER_DOCUMENTS_SHEET,
    ORDER_STATUS_LOG_SHEET,
    SALES_PRICING_SHEET,
]

TEST_CUSTOMER_NAMES = {"charl n"}
TEST_MARKERS = ("test", "dry-run", "dry run", "phase smoke", "smoke test")


def clean(value):
    return str(value or "").strip()


def clean_lower(value):
    return clean(value).lower()


def normalize_phone(value):
    digits = re.sub(r"\D+", "", clean(value))
    return digits


def to_int(value):
    number = to_float(value)
    if number is None:
        return None
    return int(number)


def to_money(value):
    number = to_float(value)
    if number is None:
        return None
    return round(number, 2)


def to_bool(value):
    text = clean_lower(value)
    return text in {"true", "yes", "y", "1"}


def to_json_list(value):
    text = clean(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in re.split(r"[,;]", text) if part.strip()]


def as_timestamp(value):
    return format_date_for_json(value) or None


def as_date(value):
    return format_date_for_json(value) or None


def deterministic_pricing_id(row):
    raw = "|".join([
        clean(row.get("Sale_Category")),
        clean(row.get("Weight_Band")),
        clean(row.get("Sex") or "Any"),
    ])
    slug = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").upper()
    return f"PRICE-{slug}"[:80]


def with_import_trace(payload, source_sheet_row):
    payload["source_sheet_row"] = source_sheet_row
    payload["import_batch_id"] = "DRY_RUN_ONLY"
    return payload


def has_any_text(row, fields):
    return any(clean(row.get(field)) for field in fields)


def has_test_marker(row, fields):
    haystack = " ".join(clean_lower(row.get(field)) for field in fields)
    return any(marker in haystack for marker in TEST_MARKERS)


def normalize_customer_name(row):
    return clean_lower(row.get("Customer_Name"))


def classify_order(row, document_order_ids, status_log_order_ids):
    order_id = clean(row.get("Order_ID"))
    if not order_id:
        return "exclude", "missing_order_id"

    if normalize_customer_name(row) in TEST_CUSTOMER_NAMES:
        return "exclude", "test_customer_charl_n"

    if has_test_marker(row, ["Notes", "Order_Source", "Created_By"]):
        return "exclude", "test_marker"

    status = clean_lower(row.get("Order_Status"))
    if status != "completed":
        return "exclude", "not_completed_order"

    return "include", "included_order"


def classify_child(row, row_id_field, parent_id, included_parent_ids, all_parent_ids, parent_kind):
    row_id = clean(row.get(row_id_field))
    if not row_id:
        return "exclude", f"missing_{row_id_field.lower()}"

    if not parent_id:
        return "exclude", f"missing_{parent_kind}_id"

    if parent_id not in all_parent_ids:
        return "exclude", f"missing_parent_{parent_kind}"

    if parent_id not in included_parent_ids:
        return "exclude", f"parent_{parent_kind}_excluded"

    return "include", f"included_with_{parent_kind}"


def classify_intake(row, included_order_ids, all_order_ids):
    intake_id = clean(row.get("Intake_ID"))
    if not intake_id:
        return "exclude", "missing_intake_id"

    if normalize_customer_name(row) in TEST_CUSTOMER_NAMES:
        return "exclude", "test_customer_charl_n"

    if has_test_marker(row, ["Notes", "Last_Customer_Message", "Last_Updated_By"]):
        return "exclude", "test_marker"

    draft_order_id = clean(row.get("Draft_Order_ID"))
    if not draft_order_id:
        return "exclude", "unlinked_intake_without_order"

    if draft_order_id:
        if draft_order_id not in all_order_ids:
            return "exclude", "missing_parent_order"
        if draft_order_id not in included_order_ids:
            return "exclude", "parent_order_excluded"

    return "include", "included_intake"


def classify_pricing(row):
    if not clean(row.get("Sale_Category")):
        return "exclude", "missing_sale_category"
    if not clean(row.get("Weight_Band")):
        return "exclude", "missing_weight_band"
    if not clean(row.get("Price_Range")):
        return "exclude", "missing_price"
    return "include", "included_pricing"


def summarize_decisions(sheet_name, decisions):
    reason_counts = Counter(decision["reason"] for decision in decisions)
    included = sum(1 for decision in decisions if decision["decision"] == "include")
    excluded = sum(1 for decision in decisions if decision["decision"] == "exclude")

    return {
        "sheet": sheet_name,
        "total_rows": len(decisions),
        "included_rows": included,
        "excluded_rows": excluded,
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def make_decision(row_id, decision, reason):
    return {
        "row_id": row_id,
        "decision": decision,
        "reason": reason,
    }


def map_order(row, source_sheet_row):
    return with_import_trace({
        "order_id": clean(row.get("Order_ID")),
        "order_date": as_timestamp(row.get("Order_Date")),
        "customer_name": clean(row.get("Customer_Name")) or None,
        "customer_phone_raw": clean(row.get("Customer_Phone")) or None,
        "customer_phone_normalized": normalize_phone(row.get("Customer_Phone")) or None,
        "customer_channel": clean(row.get("Customer_Channel")) or None,
        "customer_language": clean(row.get("Customer_Language")) or None,
        "order_source": clean(row.get("Order_Source")) or None,
        "requested_category": clean(row.get("Requested_Category")) or None,
        "requested_weight_range": clean(row.get("Requested_Weight_Range")) or None,
        "requested_sex": clean(row.get("Requested_Sex")) or None,
        "requested_quantity": to_int(row.get("Requested_Quantity")),
        "quoted_total": to_money(row.get("Quoted_Total")),
        "final_total": to_money(row.get("Final_Total")),
        "order_status": clean(row.get("Order_Status")) or "Draft",
        "approval_status": clean(row.get("Approval_Status")) or None,
        "payment_status": clean(row.get("Payment_Status")) or None,
        "payment_method": clean(row.get("Payment_Method")) or None,
        "collection_method": clean(row.get("Collection_Method")) or None,
        "collection_location": clean(row.get("Collection_Location")) or None,
        "collection_date": as_timestamp(row.get("Collection_Date")),
        "reserved_pig_count": to_int(row.get("Reserved_Pig_Count")) or 0,
        "conversation_id": clean(row.get("ConversationId")) or None,
        "notes": clean(row.get("Notes")) or None,
        "created_by": clean(row.get("Created_By")) or None,
        "created_at": as_timestamp(row.get("Created_At")),
        "updated_at": as_timestamp(row.get("Updated_At")),
    }, source_sheet_row)


def map_order_line(row, source_sheet_row):
    return with_import_trace({
        "order_line_id": clean(row.get("Order_Line_ID")),
        "order_id": clean(row.get("Order_ID")),
        "pig_id": clean(row.get("Pig_ID")) or None,
        "tag_number": clean(row.get("Tag_Number")) or None,
        "sale_category": clean(row.get("Sale_Category")) or None,
        "weight_band": clean(row.get("Weight_Band")) or None,
        "sex": clean(row.get("Sex")) or None,
        "current_weight_kg": to_float(row.get("Current_Weight_Kg")),
        "unit_price": to_money(row.get("Unit_Price")),
        "pricing_id": None,
        "line_status": clean(row.get("Line_Status")) or "Draft",
        "reserved_status": clean(row.get("Reserved_Status")) or "Not_Reserved",
        "request_item_key": clean(row.get("Request_Item_Key")) or None,
        "notes": clean(row.get("Notes")) or None,
        "created_at": as_timestamp(row.get("Created_At")),
        "updated_at": as_timestamp(row.get("Updated_At")),
    }, source_sheet_row)


def map_intake(row, source_sheet_row):
    return with_import_trace({
        "intake_id": clean(row.get("Intake_ID")),
        "conversation_id": clean(row.get("ConversationId")),
        "account_id": clean(row.get("Account_ID")) or None,
        "contact_id": clean(row.get("Contact_ID")) or None,
        "customer_name": clean(row.get("Customer_Name")) or None,
        "customer_phone_raw": clean(row.get("Customer_Phone")) or None,
        "customer_phone_normalized": normalize_phone(row.get("Customer_Phone")) or None,
        "customer_channel": clean(row.get("Customer_Channel")) or None,
        "customer_language": clean(row.get("Customer_Language")) or None,
        "draft_order_id": clean(row.get("Draft_Order_ID")) or None,
        "intake_status": clean(row.get("Intake_Status")) or "Open",
        "collection_location": clean(row.get("Collection_Location")) or None,
        "collection_time_text": clean(row.get("Collection_Time_Text")) or None,
        "collection_date": as_date(row.get("Collection_Date")),
        "collection_time": clean(row.get("Collection_Time")) or None,
        "payment_method": clean(row.get("Payment_Method")) or None,
        "quote_requested": to_bool(row.get("Quote_Requested")),
        "order_commitment": to_bool(row.get("Order_Commitment")),
        "missing_fields": to_json_list(row.get("Missing_Fields")),
        "next_action": clean(row.get("Next_Action")) or None,
        "ready_for_draft": to_bool(row.get("Ready_For_Draft")),
        "ready_for_quote": to_bool(row.get("Ready_For_Quote")),
        "last_customer_message": clean(row.get("Last_Customer_Message")) or None,
        "last_updated_by": clean(row.get("Last_Updated_By")) or None,
        "created_at": as_timestamp(row.get("Created_At")),
        "updated_at": as_timestamp(row.get("Updated_At")),
        "closed_at": as_timestamp(row.get("Closed_At")),
        "closed_reason": clean(row.get("Closed_Reason")) or None,
        "notes": clean(row.get("Notes")) or None,
    }, source_sheet_row)


def map_intake_item(row, source_sheet_row):
    return with_import_trace({
        "intake_item_id": clean(row.get("Intake_Item_ID")),
        "intake_id": clean(row.get("Intake_ID")),
        "conversation_id": clean(row.get("ConversationId")) or None,
        "item_key": clean(row.get("Item_Key")),
        "quantity": to_int(row.get("Quantity")),
        "category": clean(row.get("Category")) or None,
        "weight_range": clean(row.get("Weight_Range")) or None,
        "sex": clean(row.get("Sex")) or None,
        "intent_type": clean(row.get("Intent_Type")) or None,
        "status": clean(row.get("Status")) or "active",
        "linked_order_line_ids": to_json_list(row.get("Linked_Order_Line_IDs")),
        "last_match_status": clean(row.get("Last_Match_Status")) or None,
        "matched_quantity": to_int(row.get("Matched_Quantity")),
        "replaced_by_item_key": clean(row.get("Replaced_By_Item_Key")) or None,
        "removal_reason": clean(row.get("Removal_Reason")) or None,
        "notes": clean(row.get("Notes")) or None,
        "created_at": as_timestamp(row.get("Created_At")),
        "updated_at": as_timestamp(row.get("Updated_At")),
        "removed_at": as_timestamp(row.get("Removed_At")),
    }, source_sheet_row)


def map_document(row, source_sheet_row):
    return with_import_trace({
        "document_id": clean(row.get("Document_ID")),
        "order_id": clean(row.get("Order_ID")),
        "document_type": clean(row.get("Document_Type")),
        "document_ref": clean(row.get("Document_Ref")),
        "payment_ref": clean(row.get("Payment_Ref")) or None,
        "version": to_int(row.get("Version")) or 1,
        "document_status": clean(row.get("Document_Status")) or "Generated",
        "payment_method": clean(row.get("Payment_Method")) or None,
        "vat_rate": to_float(row.get("VAT_Rate")),
        "subtotal_ex_vat": to_money(row.get("Subtotal_Ex_VAT")),
        "vat_amount": to_money(row.get("VAT_Amount")),
        "total": to_money(row.get("Total")),
        "valid_until": as_date(row.get("Valid_Until")),
        "google_drive_file_id": clean(row.get("Google_Drive_File_ID")) or None,
        "google_drive_url": clean(row.get("Google_Drive_URL")) or None,
        "file_name": clean(row.get("File_Name")) or None,
        "future_storage_bucket": None,
        "future_storage_path": None,
        "created_at": as_timestamp(row.get("Created_At")),
        "created_by": clean(row.get("Created_By")) or None,
        "sent_at": as_timestamp(row.get("Sent_At")),
        "sent_by": clean(row.get("Sent_By")) or None,
        "notes": clean(row.get("Notes")) or None,
    }, source_sheet_row)


def map_status_log(row, source_sheet_row):
    return with_import_trace({
        "status_log_id": clean(row.get("Order_Status_Log_ID")),
        "order_id": clean(row.get("Order_ID")) or None,
        "status_date": as_timestamp(row.get("Status_Date")),
        "old_status": clean(row.get("Old_Status")) or None,
        "new_status": clean(row.get("New_Status")) or None,
        "changed_by": clean(row.get("Changed_By")) or None,
        "change_source": clean(row.get("Change_Source")) or None,
        "notes": clean(row.get("Notes")) or None,
        "created_at": as_timestamp(row.get("Created_At")),
    }, source_sheet_row)


def map_pricing(row, source_sheet_row):
    return with_import_trace({
        "pricing_id": deterministic_pricing_id(row),
        "sale_category": clean(row.get("Sale_Category")),
        "weight_band": clean(row.get("Weight_Band")),
        "sex": clean(row.get("Sex")) or None,
        "unit_price": to_money(row.get("Price_Range")),
        "currency": "ZAR",
        "effective_from": "2026-05-21",
        "effective_to": None,
        "active": True,
        "change_reason": "Initial dry-run mapping from SALES_PRICING.",
        "created_by": "migration_dry_run",
        "created_at": None,
        "updated_at": None,
    }, source_sheet_row)


def payload_summary(payloads_by_table):
    id_fields = {
        "orders": "order_id",
        "order_lines": "order_line_id",
        "order_intakes": "intake_id",
        "order_intake_items": "intake_item_id",
        "order_documents": "document_id",
        "order_status_logs": "status_log_id",
        "sales_pricing": "pricing_id",
    }
    return {
        table: {
            "rows": len(rows),
            "sample_ids": [
                rows[index].get(id_fields[table])
                for index in range(min(3, len(rows)))
            ],
        }
        for table, rows in payloads_by_table.items()
    }


def sample_payloads(payloads_by_table, sample_limit):
    if sample_limit <= 0:
        return {}
    return {
        table: rows[:sample_limit]
        for table, rows in payloads_by_table.items()
    }


def build_order_sales_import_dry_run(sheet_rows):
    rows = {sheet: list(sheet_rows.get(sheet, [])) for sheet in SHEETS}

    document_order_ids = {
        clean(row.get("Order_ID"))
        for row in rows[ORDER_DOCUMENTS_SHEET]
        if clean(row.get("Order_ID"))
    }
    status_log_order_ids = {
        clean(row.get("Order_ID"))
        for row in rows[ORDER_STATUS_LOG_SHEET]
        if clean(row.get("Order_ID"))
    }

    order_decisions = []
    included_order_ids = set()
    all_order_ids = set()

    for row in rows[ORDER_MASTER_SHEET]:
        order_id = clean(row.get("Order_ID"))
        if order_id:
            all_order_ids.add(order_id)
        decision, reason = classify_order(row, document_order_ids, status_log_order_ids)
        if decision == "include" and order_id:
            included_order_ids.add(order_id)
        order_decisions.append(make_decision(order_id, decision, reason))

    line_decisions = []
    for row in rows[ORDER_LINES_SHEET]:
        order_id = clean(row.get("Order_ID"))
        decision, reason = classify_child(
            row,
            "Order_Line_ID",
            order_id,
            included_order_ids,
            all_order_ids,
            "order",
        )
        line_decisions.append(make_decision(clean(row.get("Order_Line_ID")), decision, reason))

    document_decisions = []
    for row in rows[ORDER_DOCUMENTS_SHEET]:
        order_id = clean(row.get("Order_ID"))
        decision, reason = classify_child(
            row,
            "Document_ID",
            order_id,
            included_order_ids,
            all_order_ids,
            "order",
        )
        document_decisions.append(make_decision(clean(row.get("Document_ID")), decision, reason))

    status_log_decisions = []
    for row in rows[ORDER_STATUS_LOG_SHEET]:
        order_id = clean(row.get("Order_ID"))
        decision, reason = classify_child(
            row,
            "Order_Status_Log_ID",
            order_id,
            included_order_ids,
            all_order_ids,
            "order",
        )
        status_log_decisions.append(make_decision(clean(row.get("Order_Status_Log_ID")), decision, reason))

    intake_decisions = []
    included_intake_ids = set()
    all_intake_ids = set()

    for row in rows[ORDER_INTAKE_STATE_SHEET]:
        intake_id = clean(row.get("Intake_ID"))
        if intake_id:
            all_intake_ids.add(intake_id)
        decision, reason = classify_intake(row, included_order_ids, all_order_ids)
        if decision == "include" and intake_id:
            included_intake_ids.add(intake_id)
        intake_decisions.append(make_decision(intake_id, decision, reason))

    intake_item_decisions = []
    for row in rows[ORDER_INTAKE_ITEMS_SHEET]:
        intake_id = clean(row.get("Intake_ID"))
        decision, reason = classify_child(
            row,
            "Intake_Item_ID",
            intake_id,
            included_intake_ids,
            all_intake_ids,
            "intake",
        )
        intake_item_decisions.append(make_decision(clean(row.get("Intake_Item_ID")), decision, reason))

    pricing_decisions = []
    for index, row in enumerate(rows[SALES_PRICING_SHEET], start=2):
        decision, reason = classify_pricing(row)
        row_id = f"{clean(row.get('Sale_Category'))}|{clean(row.get('Weight_Band'))}|row_{index}"
        pricing_decisions.append(make_decision(row_id, decision, reason))

    decisions_by_sheet = {
        ORDER_MASTER_SHEET: order_decisions,
        ORDER_LINES_SHEET: line_decisions,
        ORDER_INTAKE_STATE_SHEET: intake_decisions,
        ORDER_INTAKE_ITEMS_SHEET: intake_item_decisions,
        ORDER_DOCUMENTS_SHEET: document_decisions,
        ORDER_STATUS_LOG_SHEET: status_log_decisions,
        SALES_PRICING_SHEET: pricing_decisions,
    }

    link_issues = collect_link_issues(decisions_by_sheet)
    summaries = {
        sheet: summarize_decisions(sheet, decisions)
        for sheet, decisions in decisions_by_sheet.items()
    }
    payloads = build_payloads(rows, decisions_by_sheet)

    return {
        "success": True,
        "mode": "dry_run_only",
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "source": "google_sheets",
        "target_boundary": [
            "orders",
            "order_lines",
            "order_intakes",
            "order_intake_items",
            "order_documents",
            "order_status_logs",
            "sales_pricing",
        ],
        "summaries": summaries,
        "link_issues": link_issues,
        "payload_summary": payload_summary(payloads),
        "payloads": payloads,
        "decisions": decisions_by_sheet,
    }


def included_row_ids(decisions):
    return {
        decision["row_id"]
        for decision in decisions
        if decision["decision"] == "include"
    }


def build_payloads(rows, decisions_by_sheet):
    included_orders = included_row_ids(decisions_by_sheet[ORDER_MASTER_SHEET])
    included_lines = included_row_ids(decisions_by_sheet[ORDER_LINES_SHEET])
    included_intakes = included_row_ids(decisions_by_sheet[ORDER_INTAKE_STATE_SHEET])
    included_intake_items = included_row_ids(decisions_by_sheet[ORDER_INTAKE_ITEMS_SHEET])
    included_documents = included_row_ids(decisions_by_sheet[ORDER_DOCUMENTS_SHEET])
    included_status_logs = included_row_ids(decisions_by_sheet[ORDER_STATUS_LOG_SHEET])
    included_pricing = included_row_ids(decisions_by_sheet[SALES_PRICING_SHEET])

    return {
        "orders": [
            map_order(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_MASTER_SHEET], start=2)
            if clean(row.get("Order_ID")) in included_orders
        ],
        "order_lines": [
            map_order_line(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_LINES_SHEET], start=2)
            if clean(row.get("Order_Line_ID")) in included_lines
        ],
        "order_intakes": [
            map_intake(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_INTAKE_STATE_SHEET], start=2)
            if clean(row.get("Intake_ID")) in included_intakes
        ],
        "order_intake_items": [
            map_intake_item(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_INTAKE_ITEMS_SHEET], start=2)
            if clean(row.get("Intake_Item_ID")) in included_intake_items
        ],
        "order_documents": [
            map_document(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_DOCUMENTS_SHEET], start=2)
            if clean(row.get("Document_ID")) in included_documents
        ],
        "order_status_logs": [
            map_status_log(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_STATUS_LOG_SHEET], start=2)
            if clean(row.get("Order_Status_Log_ID")) in included_status_logs
        ],
        "sales_pricing": [
            map_pricing(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[SALES_PRICING_SHEET], start=2)
            if f"{clean(row.get('Sale_Category'))}|{clean(row.get('Weight_Band'))}|row_{source_sheet_row}" in included_pricing
        ],
    }


def collect_link_issues(decisions_by_sheet):
    issue_reasons = {
        "missing_parent_order",
        "parent_order_excluded",
        "missing_parent_intake",
        "parent_intake_excluded",
        "missing_order_id",
        "missing_intake_id",
    }
    issues = defaultdict(Counter)
    for sheet, decisions in decisions_by_sheet.items():
        for decision in decisions:
            if decision["reason"] in issue_reasons:
                issues[sheet][decision["reason"]] += 1

    return {
        sheet: dict(sorted(counter.items()))
        for sheet, counter in sorted(issues.items())
    }


def load_sheet_rows():
    return {sheet: get_all_records(sheet) for sheet in SHEETS}


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run the order/sales Google Sheets to Supabase import selection."
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print only summaries and link issues, not every row decision.",
    )
    parser.add_argument(
        "--payload-samples",
        type=int,
        default=0,
        help="Include this many mapped payload samples per target table.",
    )
    args = parser.parse_args()

    report = build_order_sales_import_dry_run(load_sheet_rows())
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
                "link_issues",
                "payload_summary",
            )
        }
    if args.payload_samples:
        report["payload_samples"] = sample_payloads(payloads, args.payload_samples)
    if args.summary_only:
        report.pop("payloads", None)

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
