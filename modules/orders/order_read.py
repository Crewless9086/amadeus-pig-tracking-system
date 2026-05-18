from services.google_sheets_service import get_all_records
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    to_float,
    format_date_for_json,
    parse_sheet_date,
)


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_LINES_SHEET = "ORDER_LINES"
ORDER_OVERVIEW_SHEET = "ORDER_OVERVIEW"

ACTIVE_ORDER_STATUSES_FOR_REVIEW = {
    "Draft",
    "Pending_Approval",
    "Approved",
}
HISTORY_ORDER_STATUSES_FOR_REVIEW = {
    "Cancelled",
    "Completed",
    "Rejected",
}
VALID_ORDER_SEARCH_STATUS_SCOPES = {
    "active",
    "history",
    "all",
}

WEIGHT_BAND_ORDER = [
    "N/A",
    "2_to_4_Kg",
    "5_to_6_Kg",
    "7_to_9_Kg",
    "10_to_14_Kg",
    "15_to_19_Kg",
    "20_to_24_Kg",
    "25_to_29_Kg",
    "30_to_34_Kg",
    "35_to_39_Kg",
    "40_to_44_Kg",
    "45_to_49_Kg",
    "50_to_54_Kg",
    "55_to_59_Kg",
    "60_to_64_Kg",
    "65_to_69_Kg",
    "70_to_74_Kg",
    "75_to_79_Kg",
    "80_to_84_Kg",
    "85_to_89_Kg",
    "90_to_94_Kg",
]


def _get_order_master_row(order_id: str):
    rows = get_all_records(ORDER_MASTER_SHEET)
    for row in rows:
        if to_clean_string(row.get("Order_ID", "")) == str(order_id).strip():
            return row
    return None


def list_orders():
    rows = get_all_records(ORDER_OVERVIEW_SHEET)
    line_rollups = _build_order_line_rollups()
    master_rows = {
        to_clean_string(row.get("Order_ID", "")): row
        for row in get_all_records(ORDER_MASTER_SHEET)
        if to_clean_string(row.get("Order_ID", ""))
    }
    records = []

    for row in rows:
        order_id = to_clean_string(row.get("Order_ID", ""))
        if not order_id:
            continue

        rollup = line_rollups.get(order_id, _empty_order_line_rollup())
        master_row = master_rows.get(order_id, {})

        records.append({
            "order_id": order_id,
            "order_date": format_date_for_json(row.get("Order_Date", "")),
            "customer_name": to_clean_string(row.get("Customer_Name", "")),
            "customer_phone": to_clean_string(row.get("Customer_Phone", "")),
            "customer_channel": to_clean_string(row.get("Customer_Channel", "")),
            "customer_language": to_clean_string(row.get("Customer_Language", "")),
            "order_source": to_clean_string(row.get("Order_Source", "")),
            "requested_category": to_clean_string(row.get("Requested_Category", "")),
            "requested_weight_range": to_clean_string(row.get("Requested_Weight_Range", "")),
            "requested_sex": to_clean_string(row.get("Requested_Sex", "")),
            "requested_quantity": to_float(row.get("Requested_Quantity", "")) or 0,
            "reserved_pig_count": to_float(row.get("Reserved_Pig_Count", "")) or 0,
            "quoted_total": to_float(row.get("Quoted_Total", "")) or 0,
            "final_total": to_float(row.get("Final_Total", "")) or 0,
            "order_status": to_clean_string(row.get("Order_Status", "")),
            "approval_status": to_clean_string(row.get("Approval_Status", "")),
            "payment_status": to_clean_string(row.get("Payment_Status", "")),
            "payment_method": to_clean_string(master_row.get("Payment_Method", "")),
            "conversation_id": to_clean_string(master_row.get("ConversationId", "")),
            "collection_date": format_date_for_json(row.get("Collection_Date", "")),
            "collection_location": to_clean_string(row.get("Collection_Location", "")),
            "line_count": to_float(row.get("Line_Count", "")) or 0,
            "active_line_count": rollup["active_line_count"],
            "cancelled_line_count": rollup["cancelled_line_count"],
            "active_line_total": rollup["active_line_total"],
            "all_line_total": rollup["all_line_total"],
            "reserved_line_count": to_float(row.get("Reserved_Line_Count", "")) or 0,
            "confirmed_line_count": to_float(row.get("Confirmed_Line_Count", "")) or 0,
            "collected_line_count": to_float(row.get("Collected_Line_Count", "")) or 0,
            "reserved_pig_ids": to_clean_string(row.get("Reserved_Pig_IDs", "")),
            "reserved_tag_numbers": to_clean_string(row.get("Reserved_Tag_Numbers", "")),
            "notes": to_clean_string(row.get("Notes", "")),
            "created_by": to_clean_string(row.get("Created_By", "")),
            "created_at": format_date_for_json(row.get("Created_At", "")),
            "updated_at": format_date_for_json(row.get("Updated_At", "")),
        })

    def sort_key(item):
        parsed = parse_sheet_date(item["order_date"])
        return parsed or parse_sheet_date("1900-01-01")

    return sorted(records, key=sort_key, reverse=True)


def get_order_detail(order_id: str):
    order_id = str(order_id).strip()

    overview_rows = get_all_records(ORDER_OVERVIEW_SHEET)
    order_record = None

    for row in overview_rows:
        if to_clean_string(row.get("Order_ID", "")) == order_id:
            order_record = {
                "order_id": order_id,
                "order_date": format_date_for_json(row.get("Order_Date", "")),
                "customer_name": to_clean_string(row.get("Customer_Name", "")),
                "customer_phone": to_clean_string(row.get("Customer_Phone", "")),
                "customer_channel": to_clean_string(row.get("Customer_Channel", "")),
                "customer_language": to_clean_string(row.get("Customer_Language", "")),
                "order_source": to_clean_string(row.get("Order_Source", "")),
                "requested_category": to_clean_string(row.get("Requested_Category", "")),
                "requested_weight_range": to_clean_string(row.get("Requested_Weight_Range", "")),
                "requested_sex": to_clean_string(row.get("Requested_Sex", "")),
                "requested_quantity": to_float(row.get("Requested_Quantity", "")) or 0,
                "reserved_pig_count": to_float(row.get("Reserved_Pig_Count", "")) or 0,
                "quoted_total": to_float(row.get("Quoted_Total", "")) or 0,
                "final_total": to_float(row.get("Final_Total", "")) or 0,
                "order_status": to_clean_string(row.get("Order_Status", "")),
                "approval_status": to_clean_string(row.get("Approval_Status", "")),
                "payment_status": to_clean_string(row.get("Payment_Status", "")),
                "collection_date": format_date_for_json(row.get("Collection_Date", "")),
                "collection_location": to_clean_string(row.get("Collection_Location", "")),
                "line_count": to_float(row.get("Line_Count", "")) or 0,
                "reserved_line_count": to_float(row.get("Reserved_Line_Count", "")) or 0,
                "confirmed_line_count": to_float(row.get("Confirmed_Line_Count", "")) or 0,
                "collected_line_count": to_float(row.get("Collected_Line_Count", "")) or 0,
                "reserved_pig_ids": to_clean_string(row.get("Reserved_Pig_IDs", "")),
                "reserved_tag_numbers": to_clean_string(row.get("Reserved_Tag_Numbers", "")),
                "notes": to_clean_string(row.get("Notes", "")),
                "created_by": to_clean_string(row.get("Created_By", "")),
                "created_at": format_date_for_json(row.get("Created_At", "")),
                "updated_at": format_date_for_json(row.get("Updated_At", "")),
            }
            break

    if not order_record:
        return None

    master_row = _get_order_master_row(order_id)
    order_record["payment_method"] = (
        to_clean_string(master_row.get("Payment_Method", "")) if master_row else ""
    )
    order_record["conversation_id"] = (
        to_clean_string(master_row.get("ConversationId", "")) if master_row else ""
    )

    line_rows = get_all_records(ORDER_LINES_SHEET)
    lines = []

    for row in line_rows:
        if to_clean_string(row.get("Order_ID", "")) != order_id:
            continue

        lines.append({
            "order_line_id": to_clean_string(row.get("Order_Line_ID", "")),
            "order_id": to_clean_string(row.get("Order_ID", "")),
            "pig_id": to_clean_string(row.get("Pig_ID", "")),
            "tag_number": to_clean_string(row.get("Tag_Number", "")),
            "sale_category": to_clean_string(row.get("Sale_Category", "")),
            "weight_band": to_clean_string(row.get("Weight_Band", "")),
            "sex": to_clean_string(row.get("Sex", "")),
            "current_weight_kg": to_float(row.get("Current_Weight_Kg", "")),
            "unit_price": to_float(row.get("Unit_Price", "")) or 0,
            "line_status": to_clean_string(row.get("Line_Status", "")),
            "reserved_status": to_clean_string(row.get("Reserved_Status", "")),
            "notes": to_clean_string(row.get("Notes", "")),
            "request_item_key": to_clean_string(row.get("Request_Item_Key", "")),
            "created_at": format_date_for_json(row.get("Created_At", "")),
            "updated_at": format_date_for_json(row.get("Updated_At", "")),
        })

    active_line_count = sum(
        1 for line in lines if to_clean_string(line.get("line_status", "")) != "Cancelled"
    )
    active_line_total = sum(
        float(line.get("unit_price") or 0)
        for line in lines
        if to_clean_string(line.get("line_status", "")) != "Cancelled"
    )
    all_line_total = sum(float(line.get("unit_price") or 0) for line in lines)
    order_record["active_line_count"] = active_line_count
    order_record["cancelled_line_count"] = len(lines) - active_line_count
    order_record["active_line_total"] = active_line_total
    order_record["all_line_total"] = all_line_total
    order_record["line_count_includes_cancelled"] = True

    return {
        "order": order_record,
        "lines": lines,
    }


def search_orders(
    order_id: str = "",
    customer_phone: str = "",
    customer_name: str = "",
    conversation_id: str = "",
    status_scope: str = "active",
    limit=5,
):
    order_id = to_clean_string(order_id)
    customer_phone = _normalize_phone_for_lookup(customer_phone)
    customer_name = to_clean_string(customer_name).lower()
    conversation_id = to_clean_string(conversation_id)
    status_scope = to_clean_string(status_scope).lower() or "active"
    limit = _normalize_search_limit(limit)

    if status_scope not in VALID_ORDER_SEARCH_STATUS_SCOPES:
        raise ValueError("status_scope must be active, history, or all.")

    if not any((order_id, customer_phone, customer_name, conversation_id)):
        raise ValueError("Provide order_id, customer_phone, customer_name, or conversation_id.")

    if order_id:
        detail = get_order_detail(order_id)
        if not detail:
            return _order_search_response(
                lookup_status="no_match",
                status_scope=status_scope,
                query=_order_search_query(order_id, customer_phone, customer_name, conversation_id, limit),
                matches=[],
                message="No matching order was found.",
            )

        order = detail.get("order", {})
        lookup_status = "single_match" if _order_matches_status_scope(order, status_scope) else "terminal_order"
        return _order_search_response(
            lookup_status=lookup_status,
            status_scope=status_scope,
            query=_order_search_query(order_id, customer_phone, customer_name, conversation_id, limit),
            matches=[_operator_order_match_summary(order, get_order_documents_for_summary(order_id))],
            message=(
                "Matching order found."
                if lookup_status == "single_match"
                else "The matching order is outside the requested status scope."
            ),
        )

    records = list_orders()
    candidates = []

    for record in records:
        if not _order_matches_status_scope(record, status_scope):
            continue
        if conversation_id and to_clean_string(record.get("conversation_id", "")) != conversation_id:
            continue
        if customer_phone and _normalize_phone_for_lookup(record.get("customer_phone", "")) != customer_phone:
            continue
        if customer_name and customer_name not in to_clean_string(record.get("customer_name", "")).lower():
            continue
        candidates.append(record)

    candidates = _dedupe_and_sort_order_records(candidates)
    limited = candidates[:limit]
    matches = [
        _operator_order_match_summary(
            candidate,
            get_order_documents_for_summary(candidate.get("order_id", "")),
        )
        for candidate in limited
    ]

    if not candidates:
        lookup_status = "no_match"
        message = "No matching order was found."
    elif len(candidates) == 1:
        lookup_status = "single_match"
        message = "One matching order was found."
    else:
        lookup_status = "multiple_matches"
        message = "Multiple matching orders were found."

    return _order_search_response(
        lookup_status=lookup_status,
        status_scope=status_scope,
        query=_order_search_query(order_id, customer_phone, customer_name, conversation_id, limit),
        matches=matches,
        message=message,
        match_count=len(candidates),
    )


def get_order_operator_summary(order_id: str, documents=None):
    order_id = to_clean_string(order_id)
    detail = get_order_detail(order_id)

    if not detail:
        return None

    documents = documents if documents is not None else get_order_documents_for_summary(order_id)
    order = detail.get("order", {})
    lines = detail.get("lines", [])
    active_lines = [
        line for line in lines
        if to_clean_string(line.get("line_status", "")) != "Cancelled"
    ]

    return {
        "success": True,
        "action": "get_order_operator_summary",
        "lookup_status": "single_match",
        "order_id": order_id,
        "order_summary": _operator_order_summary(order),
        "line_summary": _summarize_lines_for_review(active_lines),
        "document_summary": _operator_document_summary(documents),
        "outstanding_actions": _outstanding_actions_for_order(order),
        "safe_document_actions": _safe_document_actions(documents),
    }


def get_order_documents_for_summary(order_id: str):
    from modules.documents.document_service import get_order_documents

    return get_order_documents(to_clean_string(order_id))


def get_active_customer_order_context(
    order_id: str = "",
    conversation_id: str = "",
    customer_phone: str = "",
):
    order_id = to_clean_string(order_id)
    conversation_id = to_clean_string(conversation_id)
    customer_phone = _normalize_phone_for_lookup(customer_phone)

    if not any((order_id, conversation_id, customer_phone)):
        raise ValueError("Provide order_id, conversation_id, or customer_phone for order lookup.")

    if order_id:
        detail = get_order_detail(order_id)
        if not detail:
            return _empty_customer_order_lookup("No order was found for that order reference.")

        order = detail["order"]
        if not _is_active_order_for_review(order):
            return {
                "success": True,
                "lookup_status": "terminal_order",
                "match_count": 0,
                "order_id": order_id,
                "message": "The matching order is not active.",
                "order_context": None,
                "matches": [_safe_order_match_summary(order)],
            }

        return {
            "success": True,
            "lookup_status": "single_match",
            "match_count": 1,
            "order_id": order_id,
            "message": "Active order context found.",
            "order_context": _safe_order_context_from_detail(detail),
            "matches": [],
        }

    records = list_orders()

    active_records = [
        record
        for record in records
        if _is_active_order_for_review(record)
    ]

    if conversation_id:
        candidates = [
            record
            for record in active_records
            if to_clean_string(record.get("conversation_id", "")) == conversation_id
        ]
        if candidates:
            return _active_customer_order_lookup_from_candidates(candidates)

    candidates = []
    if customer_phone:
        candidates = [
            record
            for record in active_records
            if _normalize_phone_for_lookup(record.get("customer_phone", "")) == customer_phone
        ]

    return _active_customer_order_lookup_from_candidates(candidates)


def _active_customer_order_lookup_from_candidates(candidates):
    unique_candidates = {}
    for candidate in candidates:
        candidate_order_id = to_clean_string(candidate.get("order_id", ""))
        if candidate_order_id:
            unique_candidates[candidate_order_id] = candidate

    candidates = list(unique_candidates.values())

    if not candidates:
        return _empty_customer_order_lookup("No active customer order was found.")

    candidates = sorted(
        candidates,
        key=lambda item: parse_sheet_date(item.get("order_date", "")) or parse_sheet_date("1900-01-01"),
        reverse=True,
    )

    if len(candidates) == 1:
        matched_order_id = to_clean_string(candidates[0].get("order_id", ""))
        detail = get_order_detail(matched_order_id)
        if not detail:
            return _empty_customer_order_lookup("The matching order could not be loaded.")

        return {
            "success": True,
            "lookup_status": "single_match",
            "match_count": 1,
            "order_id": matched_order_id,
            "message": "Active order context found.",
            "order_context": _safe_order_context_from_detail(detail),
            "matches": [],
        }

    return {
        "success": True,
        "lookup_status": "multiple_matches",
        "match_count": len(candidates),
        "order_id": "",
        "message": "Multiple active customer orders were found.",
        "order_context": None,
        "matches": [_safe_order_match_summary(candidate) for candidate in candidates[:5]],
    }


def _empty_customer_order_lookup(message: str):
    return {
        "success": True,
        "lookup_status": "no_match",
        "match_count": 0,
        "order_id": "",
        "message": message,
        "order_context": None,
        "matches": [],
    }


def _is_active_order_for_review(order: dict):
    return to_clean_string(order.get("order_status", "")) in ACTIVE_ORDER_STATUSES_FOR_REVIEW


def _normalize_phone_for_lookup(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_search_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 5
    return max(1, min(limit, 10))


def _order_search_query(order_id, customer_phone, customer_name, conversation_id, limit):
    return {
        "order_id": to_clean_string(order_id),
        "customer_phone": to_clean_string(customer_phone),
        "customer_name": to_clean_string(customer_name),
        "conversation_id": to_clean_string(conversation_id),
        "limit": limit,
    }


def _order_search_response(
    lookup_status,
    status_scope,
    query,
    matches,
    message,
    match_count=None,
):
    return {
        "success": True,
        "action": "search_orders",
        "lookup_status": lookup_status,
        "match_count": len(matches) if match_count is None else match_count,
        "status_scope": status_scope,
        "query": query,
        "matches": matches,
        "message": message,
    }


def _dedupe_and_sort_order_records(records):
    unique_records = {}
    for record in records:
        record_order_id = to_clean_string(record.get("order_id", ""))
        if record_order_id:
            unique_records[record_order_id] = record

    return sorted(
        unique_records.values(),
        key=lambda item: parse_sheet_date(item.get("order_date", "")) or parse_sheet_date("1900-01-01"),
        reverse=True,
    )


def _order_matches_status_scope(order, status_scope):
    order_status = to_clean_string(order.get("order_status", ""))
    if status_scope == "all":
        return True
    if status_scope == "active":
        return order_status in ACTIVE_ORDER_STATUSES_FOR_REVIEW
    if status_scope == "history":
        return order_status in HISTORY_ORDER_STATUSES_FOR_REVIEW
    return False


def _operator_order_match_summary(order, documents=None):
    documents = documents or []
    latest_quote = _latest_document(documents, "Quote")
    return {
        "order_id": to_clean_string(order.get("order_id", "")),
        "order_date": format_date_for_json(order.get("order_date", "")),
        "customer_name": to_clean_string(order.get("customer_name", "")),
        "customer_phone": to_clean_string(order.get("customer_phone", "")),
        "order_status": to_clean_string(order.get("order_status", "")),
        "approval_status": to_clean_string(order.get("approval_status", "")),
        "payment_status": to_clean_string(order.get("payment_status", "")),
        "payment_method": to_clean_string(order.get("payment_method", "")),
        "collection_location": to_clean_string(order.get("collection_location", "")),
        "collection_date": format_date_for_json(order.get("collection_date", "")),
        "active_line_count": to_float(order.get("active_line_count", "")) or 0,
        "active_line_total": to_float(order.get("active_line_total", "")) or 0,
        "document_count": len(documents),
        "latest_quote_ref": to_clean_string(latest_quote.get("Document_Ref", "")) if latest_quote else "",
        "latest_quote_status": to_clean_string(latest_quote.get("Document_Status", "")) if latest_quote else "",
        "outstanding_actions": [
            action["code"] for action in _outstanding_actions_for_order(order)
        ],
    }


def _operator_order_summary(order):
    return {
        "order_id": to_clean_string(order.get("order_id", "")),
        "order_date": format_date_for_json(order.get("order_date", "")),
        "customer_name": to_clean_string(order.get("customer_name", "")),
        "customer_phone": to_clean_string(order.get("customer_phone", "")),
        "order_status": to_clean_string(order.get("order_status", "")),
        "approval_status": to_clean_string(order.get("approval_status", "")),
        "payment_status": to_clean_string(order.get("payment_status", "")),
        "payment_method": to_clean_string(order.get("payment_method", "")),
        "collection_location": to_clean_string(order.get("collection_location", "")),
        "collection_date": format_date_for_json(order.get("collection_date", "")),
        "active_line_count": to_float(order.get("active_line_count", "")) or 0,
        "cancelled_line_count": to_float(order.get("cancelled_line_count", "")) or 0,
        "active_line_total": to_float(order.get("active_line_total", "")) or 0,
        "notes": to_clean_string(order.get("notes", "")),
    }


def _operator_document_summary(documents):
    return [
        {
            "document_id": to_clean_string(row.get("Document_ID", "")),
            "document_type": to_clean_string(row.get("Document_Type", "")),
            "document_ref": to_clean_string(row.get("Document_Ref", "")),
            "version": row.get("Version", ""),
            "document_status": to_clean_string(row.get("Document_Status", "")),
            "payment_method": to_clean_string(row.get("Payment_Method", "")),
            "total": to_float(row.get("Total", "")) or 0,
            "valid_until": format_date_for_json(row.get("Valid_Until", "")),
            "created_at": format_date_for_json(row.get("Created_At", "")),
            "sent_at": format_date_for_json(row.get("Sent_At", "")),
            "sent_by": to_clean_string(row.get("Sent_By", "")),
        }
        for row in _sort_documents(documents)
    ]


def _safe_document_actions(documents):
    return [
        {
            "action": "view_document_record",
            "document_id": to_clean_string(row.get("Document_ID", "")),
            "document_ref": to_clean_string(row.get("Document_Ref", "")),
        }
        for row in _sort_documents(documents)
        if to_clean_string(row.get("Document_ID", "")) and to_clean_string(row.get("Document_Ref", ""))
    ]


def _outstanding_actions_for_order(order):
    order_status = to_clean_string(order.get("order_status", ""))
    payment_method = to_clean_string(order.get("payment_method", ""))
    collection_location = to_clean_string(order.get("collection_location", ""))
    active_line_count = to_float(order.get("active_line_count", "")) or 0
    reserved_pig_count = to_float(order.get("reserved_pig_count", "")) or 0

    if order_status == "Draft":
        actions = []
        if payment_method not in {"Cash", "EFT"}:
            actions.append(_outstanding_action("missing_payment_method", "Payment method is still missing."))
        if not collection_location:
            actions.append(_outstanding_action("missing_collection_location", "Collection location is still missing."))
        if active_line_count <= 0:
            actions.append(_outstanding_action("missing_active_lines", "Order has no active lines."))
        if not actions:
            actions.append(_outstanding_action(
                "send_for_approval_when_ready",
                "Order can be sent for approval once operator confirms details.",
            ))
        return actions

    if order_status == "Pending_Approval":
        return [_outstanding_action("awaiting_approval", "Order is waiting for approval.")]

    if order_status == "Approved":
        if reserved_pig_count < active_line_count:
            return [_outstanding_action(
                "reservation_follow_up",
                "Approved order needs reservation follow-up.",
            )]
        return [_outstanding_action(
            "ready_for_collection_or_completion",
            "Approved order is ready for collection or completion handling.",
        )]

    if order_status in {"Cancelled", "Completed"}:
        return [_outstanding_action("terminal_order", "Order is closed.")]

    return []


def _outstanding_action(code, label):
    return {
        "code": code,
        "label": label,
    }


def _latest_document(documents, document_type):
    matching = [
        row for row in documents
        if to_clean_string(row.get("Document_Type", "")).lower() == document_type.lower()
        and to_clean_string(row.get("Document_Status", "")) != "Voided"
    ]
    sorted_docs = _sort_documents(matching)
    return sorted_docs[0] if sorted_docs else None


def _sort_documents(documents):
    def sort_key(row):
        try:
            version = int(row.get("Version") or 0)
        except (TypeError, ValueError):
            version = 0
        return (
            to_clean_string(row.get("Document_Type", "")),
            version,
            to_clean_string(row.get("Created_At", "")),
        )

    return sorted(documents or [], key=sort_key, reverse=True)


def _safe_order_match_summary(order: dict):
    return {
        "order_id": to_clean_string(order.get("order_id", "")),
        "order_date": format_date_for_json(order.get("order_date", "")),
        "order_status": to_clean_string(order.get("order_status", "")),
        "approval_status": to_clean_string(order.get("approval_status", "")),
        "payment_status": to_clean_string(order.get("payment_status", "")),
        "requested_category": to_clean_string(order.get("requested_category", "")),
        "requested_weight_range": to_clean_string(order.get("requested_weight_range", "")),
        "requested_sex": to_clean_string(order.get("requested_sex", "")),
        "requested_quantity": to_float(order.get("requested_quantity", "")) or 0,
        "active_line_count": to_float(order.get("active_line_count", "")) or 0,
        "active_line_total": to_float(order.get("active_line_total", "")) or 0,
        "collection_location": to_clean_string(order.get("collection_location", "")),
        "payment_method": to_clean_string(order.get("payment_method", "")),
    }


def _safe_order_context_from_detail(detail: dict):
    order = detail.get("order", {}) if isinstance(detail, dict) else {}
    lines = detail.get("lines", []) if isinstance(detail, dict) else []

    active_lines = [
        line for line in lines
        if to_clean_string(line.get("line_status", "")) != "Cancelled"
    ]

    return {
        "order": _safe_order_match_summary(order),
        "line_groups": _summarize_lines_for_review(active_lines),
        "line_count_includes_cancelled": True,
        "cancelled_line_count": to_float(order.get("cancelled_line_count", "")) or 0,
    }


def _summarize_lines_for_review(lines):
    groups = {}

    for line in lines:
        key = (
            to_clean_string(line.get("sale_category", "")),
            to_clean_string(line.get("weight_band", "")),
            to_clean_string(line.get("sex", "")),
            to_clean_string(line.get("line_status", "")),
            to_clean_string(line.get("reserved_status", "")),
            to_float(line.get("unit_price", "")) or 0,
        )
        group = groups.setdefault(key, {
            "sale_category": key[0],
            "weight_band": key[1],
            "sex": key[2],
            "line_status": key[3],
            "reserved_status": key[4],
            "unit_price": key[5],
            "quantity": 0,
            "total": 0,
        })
        group["quantity"] += 1
        group["total"] += key[5]

    return sorted(
        groups.values(),
        key=lambda item: (
            WEIGHT_BAND_ORDER.index(item["weight_band"])
            if item["weight_band"] in WEIGHT_BAND_ORDER
            else 999,
            item["sale_category"],
            item["sex"],
            item["line_status"],
        ),
    )


def _build_order_line_rollups():
    rows = get_all_records(ORDER_LINES_SHEET)
    rollups = {}

    for row in rows:
        order_id = to_clean_string(row.get("Order_ID", ""))
        if not order_id:
            continue

        rollup = rollups.setdefault(order_id, _empty_order_line_rollup())
        line_status = to_clean_string(row.get("Line_Status", ""))
        unit_price = to_float(row.get("Unit_Price", "")) or 0

        rollup["all_line_count"] += 1
        rollup["all_line_total"] += unit_price

        if line_status == "Cancelled":
            rollup["cancelled_line_count"] += 1
            continue

        rollup["active_line_count"] += 1
        rollup["active_line_total"] += unit_price

    return rollups


def _empty_order_line_rollup():
    return {
        "all_line_count": 0,
        "active_line_count": 0,
        "cancelled_line_count": 0,
        "active_line_total": 0,
        "all_line_total": 0,
    }
