from datetime import datetime
import uuid

from services.google_sheets_service import append_row


ORDER_STATUS_LOG_SHEET = "ORDER_STATUS_LOG"


def generate_order_status_log_id():
    return f"OSL-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def write_order_status_log(
    order_id: str,
    old_status: str,
    new_status: str,
    changed_by: str,
    change_source: str,
    notes: str,
):
    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_order_status_log_id(),
        order_id,
        today_str,
        old_status,
        new_status,
        changed_by,
        change_source,
        notes,
        today_str,
    ]

    append_row(ORDER_STATUS_LOG_SHEET, row_values)
