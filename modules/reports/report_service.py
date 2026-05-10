from datetime import date, datetime

from modules.orders.order_service import list_orders
from modules.pig_weights.pig_weights_utils import parse_sheet_date, to_clean_string
from services.google_sheets_service import get_all_records


ORDER_STATUS_LOG_SHEET = "ORDER_STATUS_LOG"


def get_daily_order_summary(report_date=None):
    target_date = _parse_report_date(report_date)
    orders = list_orders()
    status_logs = get_all_records(ORDER_STATUS_LOG_SHEET)
    transitions_today = _build_transition_index(status_logs, target_date)

    sections = {
        "new_drafts": [],
        "drafts_missing_payment_method": [],
        "pending_approval": [],
        "approved": [],
        "cancelled_today": [],
        "completed_today": [],
        "orders_needing_attention": [],
    }

    for order in orders:
        order_id = to_clean_string(order.get("order_id", ""))
        status = to_clean_string(order.get("order_status", ""))
        payment_method = to_clean_string(order.get("payment_method", ""))
        active_line_count = int(order.get("active_line_count") or 0)
        reserved_pig_count = int(float(order.get("reserved_pig_count") or 0))
        created_at = parse_sheet_date(order.get("created_at", ""))

        if status == "Draft" and created_at == target_date:
            sections["new_drafts"].append(_summary_order(order))

        if status == "Draft" and payment_method not in ("Cash", "EFT"):
            sections["drafts_missing_payment_method"].append(
                _summary_order(order, reasons=["missing_payment_method"])
            )

        if status == "Pending_Approval":
            sections["pending_approval"].append(_summary_order(order))

        if status == "Approved":
            sections["approved"].append(_summary_order(order))

        today_transitions = transitions_today.get(order_id, [])
        if _has_transition(today_transitions, "Cancelled"):
            sections["cancelled_today"].append(_summary_order(order))

        if _has_transition(today_transitions, "Completed"):
            sections["completed_today"].append(_summary_order(order))

        attention_reasons = _attention_reasons(
            order=order,
            status=status,
            payment_method=payment_method,
            active_line_count=active_line_count,
            reserved_pig_count=reserved_pig_count,
        )
        if attention_reasons:
            sections["orders_needing_attention"].append(
                _summary_order(order, reasons=attention_reasons)
            )

    return {
        "success": True,
        "report_date": target_date.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {key: len(value) for key, value in sections.items()},
        "sections": sections,
        "rules": {
            "new_drafts": "Draft orders with Created_At on report_date.",
            "drafts_missing_payment_method": "Draft orders where Payment_Method is not Cash or EFT.",
            "pending_approval": "Orders currently in Pending_Approval.",
            "approved": "Orders currently Approved.",
            "cancelled_today": "Orders with an ORDER_STATUS_LOG transition to Cancelled on report_date.",
            "completed_today": "Orders with an ORDER_STATUS_LOG transition to Completed on report_date.",
            "orders_needing_attention": "Drafts missing payment/location/active lines, pending approvals without active lines, or approved orders with reservation shortfall.",
        },
    }


def _parse_report_date(value):
    if not value:
        return date.today()

    parsed = parse_sheet_date(value)
    if not parsed:
        raise ValueError("date must be a valid date, preferably YYYY-MM-DD.")

    return parsed


def _build_transition_index(status_logs, target_date):
    index = {}

    for row in status_logs:
        status_date = parse_sheet_date(row.get("Status_Date", ""))
        if status_date != target_date:
            continue

        order_id = to_clean_string(row.get("Order_ID", ""))
        if not order_id:
            continue

        index.setdefault(order_id, []).append({
            "old_status": to_clean_string(row.get("Old_Status", "")),
            "new_status": to_clean_string(row.get("New_Status", "")),
            "changed_by": to_clean_string(row.get("Changed_By", "")),
            "change_source": to_clean_string(row.get("Change_Source", "")),
            "notes": to_clean_string(row.get("Notes", "")),
        })

    return index


def _has_transition(transitions, target_status):
    target_status = str(target_status or "").strip()
    for transition in transitions:
        new_status = to_clean_string(transition.get("new_status", ""))
        if new_status == target_status or new_status.startswith(f"{target_status} |"):
            return True
    return False


def _attention_reasons(
    order,
    status,
    payment_method,
    active_line_count,
    reserved_pig_count,
):
    reasons = []

    if status == "Draft":
        if payment_method not in ("Cash", "EFT"):
            reasons.append("missing_payment_method")
        if not to_clean_string(order.get("collection_location", "")):
            reasons.append("missing_collection_location")
        if active_line_count <= 0:
            reasons.append("no_active_lines")

    if status == "Pending_Approval" and active_line_count <= 0:
        reasons.append("pending_approval_without_active_lines")

    if status == "Approved" and reserved_pig_count < active_line_count:
        reasons.append("reservation_shortfall")

    return reasons


def _summary_order(order, reasons=None):
    return {
        "order_id": to_clean_string(order.get("order_id", "")),
        "customer_name": to_clean_string(order.get("customer_name", "")),
        "customer_phone": to_clean_string(order.get("customer_phone", "")),
        "customer_channel": to_clean_string(order.get("customer_channel", "")),
        "order_status": to_clean_string(order.get("order_status", "")),
        "approval_status": to_clean_string(order.get("approval_status", "")),
        "payment_status": to_clean_string(order.get("payment_status", "")),
        "payment_method": to_clean_string(order.get("payment_method", "")),
        "collection_location": to_clean_string(order.get("collection_location", "")),
        "requested_category": to_clean_string(order.get("requested_category", "")),
        "requested_weight_range": to_clean_string(order.get("requested_weight_range", "")),
        "requested_sex": to_clean_string(order.get("requested_sex", "")),
        "requested_quantity": order.get("requested_quantity", 0),
        "active_line_count": order.get("active_line_count", 0),
        "cancelled_line_count": order.get("cancelled_line_count", 0),
        "reserved_pig_count": order.get("reserved_pig_count", 0),
        "active_line_total": order.get("active_line_total", 0),
        "order_date": to_clean_string(order.get("order_date", "")),
        "created_at": to_clean_string(order.get("created_at", "")),
        "updated_at": to_clean_string(order.get("updated_at", "")),
        "reasons": reasons or [],
    }
