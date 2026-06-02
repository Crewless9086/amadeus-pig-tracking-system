from datetime import datetime

from modules.pig_weights.pig_weights_config import PIG_WEIGHTS_CONFIG
from modules.pig_weights.pig_weights_utils import (
    format_date_for_sheet,
    parse_sheet_date,
    to_clean_string,
)
from modules.sales.sales_transaction_read import get_sales_transaction
from services.google_sheets_service import batch_update_rows_by_id, get_all_records


TERMINAL_PIG_STATUSES = {"Sold", "Slaughtered", "Dead", "Removed"}
CLOSED_SALE_STATUSES = {"Completed", "Cancelled"}


def confirm_slaughter_pig_exits(sale_id, payload=None):
    sale_id = to_clean_string(sale_id)
    payload = dict(payload or {})
    changed_by = to_clean_string(payload.get("changed_by", "")) or "web_app"
    notes = to_clean_string(payload.get("notes", ""))

    if not sale_id:
        return _failure(["sale_id is required."], 400)

    sale_result, sale_status_code = get_sales_transaction(sale_id)
    if not sale_result.get("success"):
        return sale_result, sale_status_code

    sale = sale_result.get("sales_transaction", {}) or {}
    items = sale_result.get("items", []) or []

    if to_clean_string(sale.get("sale_stream", "")) != "Slaughter":
        return _failure(["Only Slaughter transactions can confirm slaughter pig exits."], 400)
    sale_status = to_clean_string(sale.get("sale_status", ""))
    payment_status = to_clean_string(sale.get("payment_status", ""))
    if sale_status in CLOSED_SALE_STATUSES or payment_status == "Paid":
        return _failure(["Completed, cancelled, or paid slaughter transactions are closed for pig-exit confirmation."], 409)

    exit_date = parse_sheet_date(payload.get("exit_date", "")) or parse_sheet_date(sale.get("sale_date", ""))
    if not exit_date:
        return _failure(["A valid exit_date or sale_date is required."], 400)

    pig_items = [item for item in items if to_clean_string(item.get("pig_id", ""))]
    if not pig_items:
        return _failure(["No linked pig items were found for this slaughter transaction."], 409)

    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    pig_rows = get_all_records(pig_master_sheet)
    pig_lookup = {
        to_clean_string(row.get(columns["pig_id"], "")): row
        for row in pig_rows
        if to_clean_string(row.get(columns["pig_id"], ""))
    }

    blocked = []
    missing = []
    for item in pig_items:
        pig_id = to_clean_string(item.get("pig_id", ""))
        pig = pig_lookup.get(pig_id)
        if not pig:
            missing.append(pig_id)
            continue
        current_status = to_clean_string(pig.get(columns["status"], ""))
        current_on_farm = to_clean_string(pig.get(columns["on_farm"], ""))
        if current_status in TERMINAL_PIG_STATUSES or current_on_farm != "Yes":
            blocked.append({
                "pig_id": pig_id,
                "status": current_status,
                "on_farm": current_on_farm,
            })

    if missing or blocked:
        return {
            "success": False,
            "status": "pig_exit_blocked",
            "sale_id": sale_id,
            "errors": ["One or more linked pigs are missing, terminal, or not on farm."],
            "missing_pig_ids": missing,
            "blocked_pigs": blocked,
            "source": _source_metadata(writes_to_sheets=False),
        }, 409

    exit_date_sheet = format_date_for_sheet(exit_date)
    today = format_date_for_sheet(datetime.now().date())
    updates = {}
    for item in pig_items:
        pig_id = to_clean_string(item.get("pig_id", ""))
        pig = pig_lookup[pig_id]
        carcass_weight = item.get("carcass_weight_kg")
        update = {
            "Status": "Slaughtered",
            "On_Farm": "No",
            "Exit_Date": exit_date_sheet,
            "Exit_Reason": "Sold to Abattoir",
            "General_Notes": _append_exit_note(
                pig.get("General_Notes", ""),
                sale_id,
                exit_date,
                changed_by,
                notes,
            ),
            "Updated_At": today,
        }
        if carcass_weight not in (None, ""):
            update["Carcass_Weight_Kg"] = carcass_weight
        updates[pig_id] = update

    rows_updated = batch_update_rows_by_id(pig_master_sheet, updates)

    return {
        "success": True,
        "status": "pig_exits_confirmed",
        "sale_id": sale_id,
        "exit_date": exit_date.isoformat(),
        "exit_reason": "Sold to Abattoir",
        "pigs_updated": rows_updated,
        "pig_ids": sorted(updates.keys()),
        "changed_by": changed_by,
        "source": _source_metadata(writes_to_sheets=True),
    }, 200


def reconcile_closed_slaughter_pig_exits(sale_id, payload=None):
    sale_id = to_clean_string(sale_id)
    payload = dict(payload or {})
    changed_by = to_clean_string(payload.get("changed_by", "")) or "web_app"
    dry_run = bool(payload.get("dry_run", True))

    if not sale_id:
        return _failure(["sale_id is required."], 400)

    sale_result, sale_status_code = get_sales_transaction(sale_id)
    if not sale_result.get("success"):
        return sale_result, sale_status_code

    sale = sale_result.get("sales_transaction", {}) or {}
    items = sale_result.get("items", []) or []
    sale_status = to_clean_string(sale.get("sale_status", ""))
    payment_status = to_clean_string(sale.get("payment_status", ""))

    if to_clean_string(sale.get("sale_stream", "")) != "Slaughter":
        return _failure(["Only Slaughter transactions can reconcile slaughter pig exits."], 400)
    if sale_status == "Cancelled":
        return _failure(["Cancelled slaughter transactions cannot reconcile pig exits."], 409)
    if sale_status != "Completed" and payment_status != "Paid":
        return _failure(["Only completed or paid slaughter transactions can use closed-sale reconciliation."], 409)

    exit_date = parse_sheet_date(sale.get("sale_date", ""))
    if not exit_date:
        return _failure(["A valid sale_date is required to reconcile pig exits."], 400)

    pig_items = [item for item in items if to_clean_string(item.get("pig_id", ""))]
    if not pig_items:
        return _failure(["No linked pig items were found for this slaughter transaction."], 409)

    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    pig_rows = get_all_records(pig_master_sheet)
    pig_lookup = {
        to_clean_string(row.get(columns["pig_id"], "")): row
        for row in pig_rows
        if to_clean_string(row.get(columns["pig_id"], ""))
    }

    missing = []
    blocked = []
    updates = {}
    today = format_date_for_sheet(datetime.now().date())
    exit_date_sheet = format_date_for_sheet(exit_date)
    for item in pig_items:
        pig_id = to_clean_string(item.get("pig_id", ""))
        pig = pig_lookup.get(pig_id)
        if not pig:
            missing.append(pig_id)
            continue

        current_status = to_clean_string(pig.get(columns["status"], ""))
        current_on_farm = to_clean_string(pig.get(columns["on_farm"], ""))
        if current_status != "Slaughtered" or current_on_farm != "No":
            blocked.append({
                "pig_id": pig_id,
                "status": current_status,
                "on_farm": current_on_farm,
            })
            continue

        update = {}
        if format_date_for_sheet(pig.get("Exit_Date", "")) != exit_date_sheet:
            update["Exit_Date"] = exit_date_sheet
        if to_clean_string(pig.get("Exit_Reason", "")) != "Sold to Abattoir":
            update["Exit_Reason"] = "Sold to Abattoir"
        if to_clean_string(pig.get("Exit_Order_ID", "")) != sale_id:
            update["Exit_Order_ID"] = sale_id
        carcass_weight = item.get("carcass_weight_kg")
        if carcass_weight not in (None, "") and pig.get("Carcass_Weight_Kg", "") != carcass_weight:
            update["Carcass_Weight_Kg"] = carcass_weight
        if update:
            existing_notes = to_clean_string(pig.get("General_Notes", ""))
            if sale_id not in existing_notes:
                update["General_Notes"] = _append_exit_note(
                    existing_notes,
                    sale_id,
                    exit_date,
                    changed_by,
                    "Closed slaughter sale lifecycle fields reconciled.",
                )
            update["Updated_At"] = today
            updates[pig_id] = update

    if missing or blocked:
        return {
            "success": False,
            "status": "pig_exit_reconcile_blocked",
            "sale_id": sale_id,
            "errors": ["One or more linked pigs are missing or are not already slaughtered/off farm."],
            "missing_pig_ids": missing,
            "blocked_pigs": blocked,
            "source": _source_metadata(writes_to_sheets=False),
        }, 409

    rows_updated = 0
    if updates and not dry_run:
        rows_updated = batch_update_rows_by_id(pig_master_sheet, updates)

    return {
        "success": True,
        "status": "pig_exits_reconciled" if not dry_run else "pig_exits_reconcile_preview",
        "sale_id": sale_id,
        "dry_run": dry_run,
        "pigs_checked": len(pig_items),
        "pigs_needing_updates": len(updates),
        "pigs_updated": rows_updated,
        "updates": updates,
        "source": _source_metadata(writes_to_sheets=bool(updates and not dry_run)),
    }, 200


def _append_exit_note(existing_notes, sale_id, exit_date, changed_by, notes):
    clean_existing = to_clean_string(existing_notes)
    entry = (
        f"{format_date_for_sheet(exit_date)} slaughter exit confirmed from {sale_id} "
        f"by {changed_by}."
    )
    if notes:
        entry = f"{entry} Notes: {notes}"
    return f"{clean_existing}\n{entry}" if clean_existing else entry


def _failure(errors, status_code):
    return {
        "success": False,
        "errors": errors,
        "source": _source_metadata(writes_to_sheets=False),
    }, status_code


def _source_metadata(writes_to_sheets):
    return {
        "source": "supabase_sales_transaction_to_google_sheets_pig_master",
        "writes_to_sheets": writes_to_sheets,
        "writes_to_supabase": False,
    }
