from datetime import datetime

from services.google_sheets_service import (
    get_all_records,
    get_all_values,
    update_row_by_first_column_match,
    batch_update_rows_by_id,
)
from modules.pig_weights.pig_weights_utils import to_clean_string


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"


def _sheet_headers_and_rows(sheet_name: str):
    all_values = get_all_values(sheet_name)
    if not all_values:
        return [], []
    headers = all_values[0]
    rows = all_values[1:]
    return headers, rows


def _header_index(headers):
    return {header: idx for idx, header in enumerate(headers)}


def _update_sheet_row_by_id(sheet_name: str, row_id: str, updates: dict):
    headers, rows = _sheet_headers_and_rows(sheet_name)

    if not headers:
        raise ValueError(f"Sheet '{sheet_name}' is empty.")

    header_map = _header_index(headers)

    for row in rows:
        if not row:
            continue

        current_id = str(row[0]).strip()
        if current_id != str(row_id).strip():
            continue

        padded_row = row + [""] * (len(headers) - len(row))

        for field_name, field_value in updates.items():
            if field_name not in header_map:
                raise ValueError(f"Missing required column '{field_name}' in '{sheet_name}'.")
            padded_row[header_map[field_name]] = field_value

        update_row_by_first_column_match(sheet_name, row_id, padded_row)
        return

    raise ValueError(f"Row with ID '{row_id}' not found in '{sheet_name}'.")


def _get_order_master_row(order_id: str):
    rows = get_all_records(ORDER_MASTER_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) == str(order_id).strip():
            return row
    return None


def _count_reserved_lines(order_id: str):
    rows = get_all_records(ORDER_LINES_SHEET)
    count = 0

    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) != order_id:
            continue
        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            count += 1

    return count


def reserve_order_lines(order_id: str):
    """
    Reserve all eligible lines for an order.

    Eligibility rules:
    - Lines with Line_Status in (Cancelled, Collected) are skipped.
    - Lines with no Pig_ID are skipped.
    - Lines already Reserved on both fields are a noop.
    - All other active lines with a Pig_ID are reserved in one batch write.
    """
    order_id = str(order_id).strip()

    if not _get_order_master_row(order_id):
        raise ValueError("Order not found.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Reserved_Status", "Updated_At"]:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_lines_in_scope = []
    for row in rows:
        if not row:
            continue
        padded = row + [""] * (len(headers) - len(row))
        if str(padded[idx["Order_ID"]]).strip() == order_id:
            order_lines_in_scope.append(padded)

    if not order_lines_in_scope:
        raise ValueError("Order has no lines to reserve.")

    line_results = []
    updates_map = {}

    for padded_row in order_lines_in_scope:
        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        pig_id = str(padded_row[idx["Pig_ID"]]).strip()
        line_status = str(padded_row[idx["Line_Status"]]).strip()
        reserved_status = str(padded_row[idx["Reserved_Status"]]).strip()

        if not line_id:
            continue

        if line_status in ("Cancelled", "Collected"):
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "skipped",
                "reason": "terminal_line_status",
            })
            continue

        if not pig_id:
            line_results.append({
                "order_line_id": line_id,
                "pig_id": "",
                "action": "skipped",
                "reason": "no_pig_assigned",
            })
            continue

        if reserved_status == "Reserved" and line_status == "Reserved":
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "noop",
                "reason": "already_reserved",
            })
            continue

        updates_map[line_id] = {
            "Reserved_Status": "Reserved",
            "Line_Status": "Reserved",
            "Updated_At": today_str,
        }
        line_results.append({
            "order_line_id": line_id,
            "pig_id": pig_id,
            "action": "reserved",
        })

    reserved_now = sum(1 for r in line_results if r["action"] == "reserved")
    noop_count = sum(1 for r in line_results if r["action"] == "noop")
    skipped_count = sum(1 for r in line_results if r["action"] == "skipped")

    if updates_map:
        batch_update_rows_by_id(ORDER_LINES_SHEET, updates_map)

    reserved_pig_count = _count_reserved_lines(order_id)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Reserved_Pig_Count": reserved_pig_count,
            "Updated_At": today_str,
        },
    )

    success = (reserved_now + noop_count) > 0

    result = {
        "success": success,
        "order_id": order_id,
        "reserved_pig_count": reserved_pig_count,
        "changed_count": len(updates_map),
        "line_results": line_results,
    }

    if success:
        result["message"] = "Order lines reserved successfully." if reserved_now > 0 else "All eligible lines are already reserved."
        if skipped_count > 0:
            skip_reasons: dict = {}
            for r in line_results:
                if r["action"] == "skipped":
                    reason = r.get("reason", "unknown")
                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            parts = [f"{count} line(s) skipped ({reason})" for reason, count in skip_reasons.items()]
            result["warning"] = f"Some lines could not be reserved: {'; '.join(parts)}."
    else:
        result["message"] = "No lines could be reserved."
        result["errors"] = [
            "No eligible lines to reserve. All lines are either cancelled, collected, or have no pig assigned."
        ]

    return result


def release_order_lines(order_id: str):
    """
    Release all reservations for an order.
    """
    order_id = str(order_id).strip()

    if not _get_order_master_row(order_id):
        raise ValueError("Order not found.")

    headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
    if not headers:
        raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Reserved_Status", "Updated_At"]:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    today_str = datetime.now().strftime("%d %b %Y")

    line_results = []
    updates_map = {}

    for row in rows:
        if not row:
            continue

        padded_row = row + [""] * (len(headers) - len(row))
        if str(padded_row[idx["Order_ID"]]).strip() != order_id:
            continue

        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        pig_id = str(padded_row[idx["Pig_ID"]]).strip()
        line_status = str(padded_row[idx["Line_Status"]]).strip()
        reserved_status = str(padded_row[idx["Reserved_Status"]]).strip()

        if not line_id:
            continue

        if line_status == "Collected":
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "skipped",
                "reason": "terminal_line_status",
            })
            continue

        needs_reserved_status_clear = reserved_status == "Reserved"
        needs_line_status_revert = line_status == "Reserved"

        if not needs_reserved_status_clear and not needs_line_status_revert:
            line_results.append({
                "order_line_id": line_id,
                "pig_id": pig_id,
                "action": "noop",
            })
            continue

        field_updates: dict = {"Updated_At": today_str}
        if needs_reserved_status_clear:
            field_updates["Reserved_Status"] = "Not_Reserved"
        if needs_line_status_revert:
            field_updates["Line_Status"] = "Draft"

        updates_map[line_id] = field_updates
        line_results.append({
            "order_line_id": line_id,
            "pig_id": pig_id,
            "action": "released",
        })

    if updates_map:
        batch_update_rows_by_id(ORDER_LINES_SHEET, updates_map)

    reserved_pig_count = _count_reserved_lines(order_id)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Reserved_Pig_Count": reserved_pig_count,
            "Updated_At": today_str,
        },
    )

    changed_count = len(updates_map)

    return {
        "success": True,
        "message": "Order reservations released successfully." if changed_count > 0 else "No active reservations to release.",
        "order_id": order_id,
        "reserved_pig_count": reserved_pig_count,
        "changed_count": changed_count,
        "line_results": line_results,
    }
