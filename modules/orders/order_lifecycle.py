import json
import os
from datetime import datetime
from urllib import request as urllib_request
from urllib import error as urllib_error

from services.google_sheets_service import (
    get_all_records,
    get_all_values,
    update_row_by_first_column_match,
    batch_update_rows_by_id,
)
from modules.pig_weights.pig_weights_utils import to_clean_string
from modules.orders.order_status_log import write_order_status_log
from modules.orders.order_reservation import reserve_order_lines
from modules.orders.order_line_sync import _cancel_order_lines
from modules.orders import order_supabase_write


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
PIG_MASTER_SHEET = "PIG_MASTER"

ORDER_APPROVAL_WEBHOOK_URL = os.getenv(
    "ORDER_APPROVAL_WEBHOOK_URL",
    "https://charln.app.n8n.cloud/webhook/46935f6b-2921-4d51-a477-1db5ac1024f7",
)
ORDER_NOTIFICATION_WEBHOOK_URL = os.getenv("ORDER_NOTIFICATION_WEBHOOK_URL", "").strip()

APPROVAL_CUSTOMER_MESSAGE = (
    "Your order has been approved. We have reserved the pigs linked to your order "
    "and will keep you posted on the next step."
)
REJECTION_CUSTOMER_MESSAGE = (
    "Your order was reviewed, but we cannot approve it at this stage. We will "
    "follow up if there is another suitable option."
)


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
    if order_supabase_write.supabase_order_writes_available():
        if sheet_name == ORDER_MASTER_SHEET:
            changed = order_supabase_write.update_order_fields(row_id, updates)
        elif sheet_name == ORDER_LINES_SHEET:
            changed = order_supabase_write.update_order_line_fields(row_id, updates)
        else:
            changed = 0
        if changed == 0:
            raise ValueError(f"Row with ID '{row_id}' not found in '{sheet_name}'.")
        return

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
    if order_supabase_write.supabase_order_writes_available():
        return order_supabase_write.get_order_master_row(order_id)

    rows = get_all_records(ORDER_MASTER_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) == str(order_id).strip():
            return row
    return None


def _write_order_status_log(order_id: str, old_status: str, new_status: str, changed_by: str, change_source: str, notes: str):
    write_order_status_log(
        order_id=order_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        change_source=change_source,
        notes=notes,
    )


def _notify_n8n_order_approval_request(order_id: str, changed_by: str):
    payload = {
        "event_type": "order_approval_requested",
        "order_id": order_id,
        "changed_by": changed_by,
        "timestamp": datetime.now().isoformat(),
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        ORDER_APPROVAL_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return {
                "sent": 200 <= resp.status < 300,
                "status_code": resp.status,
                "body": body,
            }
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError) as exc:
        return {
            "sent": False,
            "error": str(exc),
        }


def _notify_order_customer_notification(
    order_id: str,
    event_type: str,
    message_text: str,
    changed_by: str,
    order_row: dict,
    extra_payload: dict = None,
):
    if not ORDER_NOTIFICATION_WEBHOOK_URL:
        return {
            "sent": False,
            "skipped": True,
            "error": "ORDER_NOTIFICATION_WEBHOOK_URL is not configured.",
        }

    payload = {
        "event_type": event_type,
        "order_id": order_id,
        "changed_by": changed_by,
        "message_text": message_text,
        "order": order_row or {},
        "timestamp": datetime.now().isoformat(),
    }
    if extra_payload:
        payload.update(extra_payload)

    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        ORDER_NOTIFICATION_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return {
                "sent": 200 <= resp.status < 300,
                "status_code": resp.status,
                "body": body,
            }
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError) as exc:
        return {
            "sent": False,
            "error": str(exc),
        }


def _add_notification_result_to_response(
    result: dict,
    order_id: str,
    changed_by: str,
    notification_result: dict,
    log_note: str,
    status_for_log: str,
):
    result["customer_notification_sent"] = notification_result.get("sent", False)

    if notification_result.get("sent", False):
        return

    result["notification_warning"] = (
        "Customer notification was not sent: "
        + notification_result.get("error", "Unknown error")
    )

    try:
        _write_order_status_log(
            order_id=order_id,
            old_status=status_for_log,
            new_status=status_for_log,
            changed_by=changed_by,
            change_source="App",
            notes=log_note + ": " + notification_result.get("error", "Unknown error"),
        )
    except Exception as exc:
        result["notification_status_log_warning"] = (
            "Customer notification warning could not be written to ORDER_STATUS_LOG: "
            + str(exc)
        )


def send_order_for_approval(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status != "Draft":
        raise ValueError(
            f"Only Draft orders can be sent for approval. Current status: {old_status}."
        )

    payment_method = to_clean_string(row.get("Payment_Method", ""))
    if payment_method not in ("Cash", "EFT"):
        raise ValueError(
            "Payment method must be set to Cash or EFT before sending for approval."
        )

    customer_name = to_clean_string(row.get("Customer_Name", ""))
    if not customer_name:
        raise ValueError("Customer name is required before sending for approval.")

    collection_location = to_clean_string(row.get("Collection_Location", ""))
    if not collection_location:
        raise ValueError(
            "Collection location is required before sending for approval."
        )

    all_lines = (
        order_supabase_write.list_order_lines()
        if order_supabase_write.supabase_order_writes_available()
        else get_all_records(ORDER_LINES_SHEET)
    )
    active_lines = [
        line for line in all_lines
        if to_clean_string(line.get("Order_ID", "")) == order_id
        and to_clean_string(line.get("Line_Status", "")) != "Cancelled"
    ]
    if not active_lines:
        raise ValueError(
            "At least one active order line is required before sending for approval."
        )

    today_str = datetime.now().strftime("%d %b %Y")

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Pending_Approval",
            "Approval_Status": "Pending",
            "Updated_At": today_str,
        }
    )

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Pending_Approval | Pending",
        changed_by=changed_by,
        change_source="App",
        notes="Order sent for approval",
    )

    webhook_result = _notify_n8n_order_approval_request(order_id, changed_by)

    result = {
        "success": True,
        "message": "Order sent for approval.",
        "order_id": order_id,
        "n8n_notified": webhook_result.get("sent", False),
    }

    if not webhook_result.get("sent", False):
        result["warning"] = "Order status updated, but approval notification could not be sent to n8n."
        result["n8n_error"] = webhook_result.get("error", "Unknown error")

    return result


def approve_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status != "Pending_Approval":
        raise ValueError(
            f"Only Pending_Approval orders can be approved. Current status: {old_status}."
        )

    today_str = datetime.now().strftime("%d %b %Y")

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Approved",
            "Approval_Status": "Approved",
            "Updated_At": today_str,
        }
    )

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Approved | Approved",
        changed_by=changed_by,
        change_source="App",
        notes="Order approved",
    )

    result = {
        "success": True,
        "message": "Order approved successfully.",
        "order_id": order_id,
    }

    reserve_result = None
    reserve_warning = ""

    try:
        reserve_result = reserve_order_lines(order_id)
        result["auto_reserve"] = reserve_result

        if not reserve_result.get("success"):
            reserve_warning = (
                reserve_result.get("message")
                or "; ".join(reserve_result.get("errors", []))
                or "Auto-reservation did not reserve any order lines."
            )
        elif reserve_result.get("warning"):
            reserve_warning = reserve_result["warning"]

    except Exception as exc:
        reserve_warning = f"Auto-reservation failed after approval: {str(exc)}"

    if reserve_warning:
        result["reserve_warning"] = reserve_warning
        result["warning"] = reserve_warning

        try:
            _write_order_status_log(
                order_id=order_id,
                old_status="Approved | Approved",
                new_status="Approved | Approved",
                changed_by=changed_by,
                change_source="App",
                notes=f"Approval completed, but reservation needs manual follow-up: {reserve_warning}",
            )
        except Exception as exc:
            result["status_log_warning"] = (
                "Reservation warning could not be written to ORDER_STATUS_LOG: "
                + str(exc)
            )

    notification_row = _get_order_master_row(order_id) or row
    notification_result = _notify_order_customer_notification(
        order_id=order_id,
        event_type="order_approved",
        message_text=APPROVAL_CUSTOMER_MESSAGE,
        changed_by=changed_by,
        order_row=notification_row,
        extra_payload={
            "reserve_warning": reserve_warning,
            "auto_reserve": reserve_result,
        },
    )
    _add_notification_result_to_response(
        result=result,
        order_id=order_id,
        changed_by=changed_by,
        notification_result=notification_result,
        log_note="Approval completed, but customer notification needs manual follow-up",
        status_for_log="Approved | Approved",
    )

    return result


def reject_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status == "Completed":
        raise ValueError("Completed orders cannot be rejected.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_line_rows = (
        order_supabase_write.list_order_lines()
        if order_supabase_write.supabase_order_writes_available()
        else get_all_records(ORDER_LINES_SHEET)
    )
    line_ids_to_cancel = []

    for line in order_line_rows:
        if to_clean_string(line.get("Order_ID", "")) != order_id:
            continue

        line_status = to_clean_string(line.get("Line_Status", ""))
        if line_status in ("Cancelled", "Collected"):
            continue

        line_id = to_clean_string(line.get("Order_Line_ID", ""))
        if line_id:
            line_ids_to_cancel.append(line_id)

    cancelled_line_count = _cancel_order_lines(line_ids_to_cancel)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Cancelled",
            "Approval_Status": "Rejected",
            "Reserved_Pig_Count": 0,
            "Updated_At": today_str,
        }
    )

    if old_status != "Cancelled" or old_approval != "Rejected" or cancelled_line_count:
        _write_order_status_log(
            order_id=order_id,
            old_status=f"{old_status} | {old_approval}",
            new_status="Cancelled | Rejected",
            changed_by=changed_by,
            change_source="App",
            notes=f"Order rejected; {cancelled_line_count} line(s) cancelled and reservations released",
        )

    result = {
        "success": True,
        "message": "Order rejected successfully.",
        "order_id": order_id,
        "cancelled_line_count": cancelled_line_count,
        "reserved_pig_count": 0,
    }

    notification_row = _get_order_master_row(order_id) or row
    notification_result = _notify_order_customer_notification(
        order_id=order_id,
        event_type="order_rejected",
        message_text=REJECTION_CUSTOMER_MESSAGE,
        changed_by=changed_by,
        order_row=notification_row,
        extra_payload={
            "cancelled_line_count": cancelled_line_count,
            "reserved_pig_count": 0,
        },
    )
    _add_notification_result_to_response(
        result=result,
        order_id=order_id,
        changed_by=changed_by,
        notification_result=notification_result,
        log_note="Rejection completed, but customer notification needs manual follow-up",
        status_for_log="Cancelled | Rejected",
    )

    return result


def cancel_order(order_id: str, changed_by: str = "App", reason: str = ""):
    order_id = str(order_id).strip()
    row = _get_order_master_row(order_id)

    if not row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(row.get("Order_Status", ""))
    old_approval = to_clean_string(row.get("Approval_Status", ""))

    if old_status == "Completed":
        raise ValueError("Completed orders cannot be cancelled.")

    if old_status == "Cancelled" and old_approval == "Rejected":
        raise ValueError("Rejected orders are already cancelled and cannot be customer-cancelled.")

    today_str = datetime.now().strftime("%d %b %Y")

    order_line_rows = (
        order_supabase_write.list_order_lines()
        if order_supabase_write.supabase_order_writes_available()
        else get_all_records(ORDER_LINES_SHEET)
    )
    line_ids_to_cancel = []

    for line in order_line_rows:
        if to_clean_string(line.get("Order_ID", "")) != order_id:
            continue

        line_status = to_clean_string(line.get("Line_Status", ""))
        if line_status in ("Cancelled", "Collected"):
            continue

        line_id = to_clean_string(line.get("Order_Line_ID", ""))
        if line_id:
            line_ids_to_cancel.append(line_id)

    cancelled_line_count = _cancel_order_lines(line_ids_to_cancel)

    _update_sheet_row_by_id(
        ORDER_MASTER_SHEET,
        order_id,
        {
            "Order_Status": "Cancelled",
            "Approval_Status": "Not_Required",
            "Payment_Status": "Cancelled",
            "Reserved_Pig_Count": 0,
            "Updated_At": today_str,
        }
    )

    if old_status != "Cancelled" or old_approval != "Not_Required" or cancelled_line_count:
        log_note = f"Order cancelled by customer; {cancelled_line_count} line(s) cancelled and reservations released"
        clean_reason = str(reason or "").strip()
        if clean_reason:
            log_note = f"{log_note}. Reason: {clean_reason}"

        _write_order_status_log(
            order_id=order_id,
            old_status=f"{old_status} | {old_approval}",
            new_status="Cancelled | Not_Required",
            changed_by=changed_by,
            change_source="Customer",
            notes=log_note,
        )

    return {
        "success": True,
        "message": "Order cancelled successfully.",
        "order_id": order_id,
        "cancelled_line_count": cancelled_line_count,
        "reserved_pig_count": 0,
        "payment_status": "Cancelled",
        "approval_status": "Not_Required",
    }


def complete_order(order_id: str, changed_by: str = "App"):
    order_id = str(order_id).strip()
    order_row = _get_order_master_row(order_id)

    if not order_row:
        raise ValueError("Order not found.")

    old_status = to_clean_string(order_row.get("Order_Status", ""))
    old_approval = to_clean_string(order_row.get("Approval_Status", ""))

    if old_status != "Approved":
        raise ValueError(f"Only Approved orders can be completed. Current status: {old_status}.")

    if order_supabase_write.supabase_order_writes_available():
        headers = ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Reserved_Status", "Updated_At"]
        rows = [
            [row.get(field, "") for field in headers]
            for row in order_supabase_write.list_order_lines()
        ]
    else:
        headers, rows = _sheet_headers_and_rows(ORDER_LINES_SHEET)
        if not headers:
            raise ValueError("ORDER_LINES is empty.")

    idx = _header_index(headers)
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Updated_At"]:
        if field not in idx:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    active_lines = []
    for row in rows:
        if not row:
            continue
        padded_row = row + [""] * (len(headers) - len(row))
        if str(padded_row[idx["Order_ID"]]).strip() != order_id:
            continue
        if str(padded_row[idx["Line_Status"]]).strip() == "Cancelled":
            continue
        line_id = str(padded_row[idx["Order_Line_ID"]]).strip()
        pig_id = str(padded_row[idx["Pig_ID"]]).strip()
        if not line_id:
            continue
        active_lines.append({"line_id": line_id, "pig_id": pig_id})

    if not active_lines:
        raise ValueError("Order has no active lines to complete.")

    missing_pig = [l["line_id"] for l in active_lines if not l["pig_id"]]
    if missing_pig:
        raise ValueError(f"The following lines have no Pig_ID and cannot be completed: {', '.join(missing_pig)}")

    today_str = datetime.now().strftime("%d %b %Y")

    order_lines_updates = {
        line["line_id"]: {
            "Line_Status":     "Collected",
            "Reserved_Status": "Collected",
            "Updated_At":      today_str,
        }
        for line in active_lines
    }
    if order_supabase_write.supabase_order_writes_available():
        for line_id, updates in order_lines_updates.items():
            order_supabase_write.update_order_line_fields(line_id, updates)
    else:
        batch_update_rows_by_id(ORDER_LINES_SHEET, order_lines_updates)

    pig_updates = {
        line["pig_id"]: {
            "Status": "Sold",
            "On_Farm": "No",
            "Exit_Date": today_str,
            "Exit_Reason": "Sold",
            "Exit_Order_ID": order_id,
            "Updated_At": today_str,
        }
        for line in active_lines
    }
    if order_supabase_write.supabase_order_writes_available():
        order_supabase_write.mark_pigs_sold([line["pig_id"] for line in active_lines])
    else:
        batch_update_rows_by_id(PIG_MASTER_SHEET, pig_updates)

    _update_sheet_row_by_id(ORDER_MASTER_SHEET, order_id, {
        "Order_Status": "Completed",
        "Updated_At": today_str,
    })

    _write_order_status_log(
        order_id=order_id,
        old_status=f"{old_status} | {old_approval}",
        new_status="Completed | Approved",
        changed_by=changed_by,
        change_source="App",
        notes=f"Order completed - {len(active_lines)} pig(s) marked as sold",
    )

    return {
        "success": True,
        "message": "Order completed successfully.",
        "order_id": order_id,
        "pigs_marked_sold": len(active_lines),
    }
