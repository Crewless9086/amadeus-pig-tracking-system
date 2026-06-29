import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.order_sales_import_dry_run import (
    ORDER_DOCUMENTS_SHEET,
    ORDER_INTAKE_ITEMS_SHEET,
    ORDER_INTAKE_STATE_SHEET,
    ORDER_LINES_SHEET,
    ORDER_MASTER_SHEET,
    ORDER_STATUS_LOG_SHEET,
    SALES_PRICING_SHEET,
    SHEETS,
    classify_child,
    classify_pricing,
    clean,
    collect_link_issues,
    has_test_marker,
    load_sheet_rows,
    make_decision,
    map_document,
    map_intake,
    map_intake_item,
    map_order,
    map_order_line,
    map_pricing,
    map_status_log,
    normalize_customer_name,
    payload_summary,
    sample_payloads,
    summarize_decisions,
)
from scripts.order_sales_shadow_import import TABLE_INSERT_ORDER, _upsert_rows, load_local_env, normalize_shadow_row
from services.database_service import DATABASE_URL_ENV


IMPORT_BATCH_ID = "IMPORT-20260629-LIVE-ORDERS-V1"


def classify_live_order(row):
    order_id = clean(row.get("Order_ID"))
    if not order_id:
        return "exclude", "missing_order_id"
    if normalize_customer_name(row) == "charl n":
        return "exclude", "test_customer_charl_n"
    if has_test_marker(row, ["Notes", "Order_Source", "Created_By"]):
        return "exclude", "test_marker"
    return "include", "included_live_order"


def classify_live_intake(row, included_order_ids, all_order_ids):
    intake_id = clean(row.get("Intake_ID"))
    if not intake_id:
        return "exclude", "missing_intake_id"
    if normalize_customer_name(row) == "charl n":
        return "exclude", "test_customer_charl_n"
    if has_test_marker(row, ["Notes", "Last_Customer_Message", "Last_Updated_By"]):
        return "exclude", "test_marker"
    draft_order_id = clean(row.get("Draft_Order_ID"))
    if not draft_order_id:
        return "include", "included_unlinked_live_intake"
    if draft_order_id not in all_order_ids:
        return "exclude", "missing_parent_order"
    if draft_order_id not in included_order_ids:
        return "exclude", "parent_order_excluded"
    return "include", "included_live_intake"


def included_row_ids(decisions):
    return {
        decision["row_id"]
        for decision in decisions
        if decision["decision"] == "include"
    }


def _with_live_import(rows):
    return [
        dict(row, import_batch_id=IMPORT_BATCH_ID)
        for row in rows
    ]


def _with_live_import_for_table(table_name, rows):
    return [
        normalize_shadow_row(table_name, dict(row, import_batch_id=IMPORT_BATCH_ID))
        for row in rows
    ]


def build_live_order_payloads(rows, decisions_by_sheet):
    included_orders = included_row_ids(decisions_by_sheet[ORDER_MASTER_SHEET])
    included_lines = included_row_ids(decisions_by_sheet[ORDER_LINES_SHEET])
    included_intakes = included_row_ids(decisions_by_sheet[ORDER_INTAKE_STATE_SHEET])
    included_intake_items = included_row_ids(decisions_by_sheet[ORDER_INTAKE_ITEMS_SHEET])
    included_documents = included_row_ids(decisions_by_sheet[ORDER_DOCUMENTS_SHEET])
    included_status_logs = included_row_ids(decisions_by_sheet[ORDER_STATUS_LOG_SHEET])
    included_pricing = included_row_ids(decisions_by_sheet[SALES_PRICING_SHEET])

    return {
        "orders": _with_live_import_for_table("orders", [
            map_order(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_MASTER_SHEET], start=2)
            if clean(row.get("Order_ID")) in included_orders
        ]),
        "order_lines": _with_live_import_for_table("order_lines", [
            map_order_line(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_LINES_SHEET], start=2)
            if clean(row.get("Order_Line_ID")) in included_lines
        ]),
        "order_intakes": _with_live_import_for_table("order_intakes", [
            map_intake(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_INTAKE_STATE_SHEET], start=2)
            if clean(row.get("Intake_ID")) in included_intakes
        ]),
        "order_intake_items": _with_live_import_for_table("order_intake_items", [
            map_intake_item(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_INTAKE_ITEMS_SHEET], start=2)
            if clean(row.get("Intake_Item_ID")) in included_intake_items
        ]),
        "order_documents": _with_live_import_for_table("order_documents", [
            map_document(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_DOCUMENTS_SHEET], start=2)
            if clean(row.get("Document_ID")) in included_documents
        ]),
        "order_status_logs": _with_live_import_for_table("order_status_logs", [
            map_status_log(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[ORDER_STATUS_LOG_SHEET], start=2)
            if clean(row.get("Order_Status_Log_ID")) in included_status_logs
        ]),
        "sales_pricing": _with_live_import_for_table("sales_pricing", [
            map_pricing(row, source_sheet_row)
            for source_sheet_row, row in enumerate(rows[SALES_PRICING_SHEET], start=2)
            if f"{clean(row.get('Sale_Category'))}|{clean(row.get('Weight_Band'))}|row_{source_sheet_row}" in included_pricing
        ]),
    }


def build_live_order_import_plan(sheet_rows):
    rows = {sheet: list(sheet_rows.get(sheet, [])) for sheet in SHEETS}
    order_decisions = []
    included_order_ids = set()
    all_order_ids = set()

    for row in rows[ORDER_MASTER_SHEET]:
        order_id = clean(row.get("Order_ID"))
        if order_id:
            all_order_ids.add(order_id)
        decision, reason = classify_live_order(row)
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
        decision, reason = classify_live_intake(row, included_order_ids, all_order_ids)
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
    for source_sheet_row, row in enumerate(rows[SALES_PRICING_SHEET], start=2):
        decision, reason = classify_pricing(row)
        row_id = f"{clean(row.get('Sale_Category'))}|{clean(row.get('Weight_Band'))}|row_{source_sheet_row}"
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
    payloads = build_live_order_payloads(rows, decisions_by_sheet)
    summaries = {
        sheet: summarize_decisions(sheet, decisions)
        for sheet, decisions in decisions_by_sheet.items()
    }
    return {
        "success": True,
        "mode": "live_order_import_plan",
        "import_batch_id": IMPORT_BATCH_ID,
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "source": "google_sheets",
        "target_boundary": TABLE_INSERT_ORDER,
        "summaries": summaries,
        "link_issues": collect_link_issues(decisions_by_sheet),
        "payload_summary": payload_summary(payloads),
        "payloads": payloads,
        "decisions": decisions_by_sheet,
    }


def apply_live_order_import(sheet_rows, database_url, connect_factory=None):
    if not database_url:
        return {
            "success": False,
            "mode": "apply",
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
        }, 2

    if connect_factory is None:
        import psycopg
        connect_factory = psycopg.connect

    report = build_live_order_import_plan(sheet_rows)
    payloads = report["payloads"]
    upserted = {}
    with connect_factory(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            for table_name in TABLE_INSERT_ORDER:
                upserted[table_name] = _upsert_rows(cursor, table_name, payloads.get(table_name, []))

    return {
        "success": True,
        "mode": "apply",
        "status": "imported",
        "import_batch_id": IMPORT_BATCH_ID,
        "writes_to_supabase": True,
        "writes_to_sheets": False,
        "upserted": upserted,
        "payload_summary": payload_summary(payloads),
    }, 0


def main():
    parser = argparse.ArgumentParser(description="Plan or apply the live order Google Sheets to Supabase import.")
    parser.add_argument("--apply", action="store_true", help="Apply the import to Supabase with upserts.")
    parser.add_argument("--summary-only", action="store_true", help="Print only summaries and link issues.")
    parser.add_argument("--payload-samples", type=int, default=0, help="Include mapped payload samples.")
    args = parser.parse_args()

    sheet_rows = load_sheet_rows()
    if args.apply:
        load_local_env()
        result, status = apply_live_order_import(sheet_rows, os.getenv(DATABASE_URL_ENV, ""))
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(status)

    report = build_live_order_import_plan(sheet_rows)
    payloads = report["payloads"]
    if args.summary_only:
        report = {
            key: report[key]
            for key in (
                "success",
                "mode",
                "import_batch_id",
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
    report.pop("payloads", None)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
