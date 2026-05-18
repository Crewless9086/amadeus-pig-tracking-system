"""
Compatibility facade for order services.

Phase 7.0C moved order behavior into focused modules. This file keeps the
existing import surface stable for routes, document services, reports, and
workflow-facing code while orchestration is cleaned up one step at a time.
"""

from modules.pig_weights.pig_weights_utils import to_clean_string
from modules.orders.order_read import (
    ORDER_LINES_SHEET,
    _get_order_master_row,
    list_orders,
    get_order_detail,
    get_active_customer_order_context,
)
from modules.orders.order_write import (
    get_available_pigs_for_orders,
    create_order,
    update_order,
    create_order_line,
    update_order_line,
    delete_order_line,
)
from modules.orders.order_reservation import (
    reserve_order_lines,
    release_order_lines,
)
from modules.orders.order_line_sync import sync_order_lines_from_request
from modules.orders.order_lifecycle import (
    send_order_for_approval,
    approve_order,
    reject_order,
    cancel_order,
    complete_order,
)


def create_order_with_lines(order_data: dict, sync_data: dict):
    create_result = create_order(order_data)
    order_id = to_clean_string(create_result.get("order_id", ""))

    if not order_id:
        raise ValueError("Order could not be created.")

    sync_payload = dict(sync_data)
    sync_payload["cancel_order_if_no_matches"] = True

    try:
        sync_result = sync_order_lines_from_request(order_id, sync_payload)
    except Exception as exc:
        cancel_result = None
        try:
            cancel_result = cancel_order(
                order_id,
                changed_by=sync_payload.get("changed_by", order_data.get("created_by", "App")),
                reason="Auto-cancelled because create-with-lines sync failed: " + str(exc),
            )
        except Exception as cancel_exc:
            cancel_result = {
                "success": False,
                "error": str(cancel_exc),
            }

        return {
            "success": False,
            "action": "create_order_with_lines",
            "order_id": order_id,
            "order_status": "Cancelled" if cancel_result.get("success") else "Draft",
            "create_success": create_result.get("success") is True,
            "sync_success": False,
            "cancelled_empty_order": cancel_result.get("success") is True,
            "cancel_result": cancel_result,
            "error": str(exc),
            "message": "Order was created, but line sync failed. The new draft was cancelled.",
        }

    cancelled_empty_order = sync_result.get("cancelled_empty_order") is True
    complete_success = (
        create_result.get("success") is True
        and sync_result.get("success") is True
        and not cancelled_empty_order
    )

    return {
        "success": complete_success,
        "action": "create_order_with_lines",
        "order_id": order_id,
        "order_status": sync_result.get("order_status", "Draft"),
        "status": sync_result.get("order_status", "Draft"),
        "create_success": create_result.get("success") is True,
        "sync_success": sync_result.get("success") is True,
        "message": (
            "Order created and lines synced successfully."
            if complete_success
            else "Order created, but no matching pigs were available. The empty draft was cancelled."
        ),
        "sync_results": sync_result.get("results", []),
        "results": sync_result.get("results", []),
        "partial_fulfillment": sync_result.get("partial_fulfillment", False),
        "complete_fulfillment": sync_result.get("complete_fulfillment", False),
        "fulfillment_status": sync_result.get("fulfillment_status", ""),
        "requested_total": sync_result.get("requested_total", 0),
        "matched_total": sync_result.get("matched_total", 0),
        "unmatched_total": sync_result.get("unmatched_total", 0),
        "incomplete_items": sync_result.get("incomplete_items", []),
        "cancelled_empty_order": cancelled_empty_order,
        "cancel_result": sync_result.get("cancel_result"),
        "sync_message": sync_result.get("message", ""),
    }
