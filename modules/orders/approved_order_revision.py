import hashlib
import json

from modules.documents.document_service import (
    DOCUMENT_TYPE_HEALTH_DECLARATION,
    DOCUMENT_TYPE_LOADING_SHEET,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
    DOCUMENT_TYPE_QUOTE,
)
from modules.documents.loading_sheet_service import send_loading_sheet_to_owner_telegram
from modules.orders.order_read import get_order_detail
from modules.orders import order_supabase_read
from modules.orders.order_status_log import write_order_status_log
from modules.orders.order_write import update_order
from modules.orders.order_line_sync import sync_order_lines_from_request
from modules.orders.order_reservation import reserve_order_lines
from modules.pig_weights.pig_weights_utils import to_clean_string, to_float
from services.google_sheets_service import get_all_records


REVISION_FINGERPRINT_PREFIX = "Approved_Order_Revision_Fingerprint:"
REVISION_DOCUMENT_TYPES = (
    DOCUMENT_TYPE_QUOTE,
    DOCUMENT_TYPE_LOADING_SHEET,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
    DOCUMENT_TYPE_HEALTH_DECLARATION,
)
ORDER_STATUS_LOG_SHEET = "ORDER_STATUS_LOG"


def revise_approved_livestock_order(
    order_id,
    payload,
    *,
    quote_generator,
    loading_sheet_generator,
    removal_certificate_generator,
    health_declaration_generator,
    quote_send_preparer,
    document_lookup,
):
    order_id = to_clean_string(order_id)
    if not order_id:
        raise ValueError("order_id is required.")

    changed_by = to_clean_string(payload.get("changed_by", "Oom Sakkie")) or "Oom Sakkie"
    requested_items = payload.get("requested_items") or []
    order_updates = payload.get("order_updates") if isinstance(payload.get("order_updates"), dict) else {}
    correction = payload.get("sale_readiness_correction") if isinstance(payload.get("sale_readiness_correction"), dict) else {}
    movement_form_data = payload.get("movement_form_data") if isinstance(payload.get("movement_form_data"), dict) else {}
    send_owner_telegram = _truthy(payload.get("send_owner_telegram", True))
    prepare_customer_quote = _truthy(payload.get("prepare_customer_quote", True))
    force = _truthy(payload.get("force"))

    if not isinstance(requested_items, list) or not requested_items:
        raise ValueError("requested_items is required and must be a non-empty list.")

    detail_before = get_order_detail(order_id)
    if not detail_before:
        raise ValueError("Order not found.")

    order_before = detail_before.get("order") or {}
    order_status = to_clean_string(order_before.get("order_status"))
    approval_status = to_clean_string(order_before.get("approval_status"))
    if order_status != "Approved" or approval_status not in {"Approved", ""}:
        raise ValueError("Only approved orders can use the approved-order revision action.")

    correction_summary = _correction_summary(correction)
    revision_fingerprint = _revision_fingerprint(order_id, requested_items, order_updates, correction_summary, movement_form_data)
    documents_before = document_lookup(order_id) or []
    already_applied = _revision_fingerprint_already_logged(order_id, revision_fingerprint)

    updates_result = None
    if order_updates:
        update_payload = dict(order_updates)
        update_payload["changed_by"] = changed_by
        updates_result = update_order(order_id, update_payload)

    detail_after_update = get_order_detail(order_id) or detail_before
    lines_already_match = _active_lines_match_requested_items(
        detail_after_update.get("lines") or [],
        requested_items,
    )

    line_sync_result = {
        "success": True,
        "skipped": True,
        "reason": "active_lines_already_match_revision",
        "order_id": order_id,
    }
    if force or not lines_already_match:
        sync_payload = {
            "changed_by": changed_by,
            "requested_items": requested_items,
            "allowed_order_statuses": ("Approved",),
        }
        line_sync_result = sync_order_lines_from_request(order_id, sync_payload)

    reserve_result = reserve_order_lines(order_id)

    documents = []
    if already_applied and not force:
        document_results = {
            doc_type: _document_skipped(doc_type, revision_fingerprint)
            for doc_type in REVISION_DOCUMENT_TYPES
        }
    else:
        document_results = {
            DOCUMENT_TYPE_QUOTE: quote_generator(order_id, created_by=changed_by),
            DOCUMENT_TYPE_LOADING_SHEET: loading_sheet_generator(order_id, created_by=changed_by),
            DOCUMENT_TYPE_REMOVAL_CERTIFICATE: removal_certificate_generator(order_id, form_data=movement_form_data, created_by=changed_by),
            DOCUMENT_TYPE_HEALTH_DECLARATION: health_declaration_generator(order_id, form_data=movement_form_data, created_by=changed_by),
        }

    for doc_type in REVISION_DOCUMENT_TYPES:
        documents.append(_document_result_summary(doc_type, document_results.get(doc_type) or {}))

    owner_telegram_results = []
    if send_owner_telegram:
        for item in documents:
            document_id = to_clean_string(item.get("document_id"))
            if not document_id:
                continue
            if item.get("skipped"):
                continue
            owner_telegram_results.append(
                send_loading_sheet_to_owner_telegram(document_id, sent_by=changed_by)
            )

    quote_prepare_result = None
    if prepare_customer_quote:
        quote_prepare_result = quote_send_preparer(
            order_id,
            conversation_id=to_clean_string(payload.get("conversation_id", "")),
            requested_by=changed_by,
        )

    status_log_result = _write_revision_log(
        order_id=order_id,
        changed_by=changed_by,
        revision_fingerprint=revision_fingerprint,
        line_sync_result=line_sync_result,
        reserve_result=reserve_result,
        correction_summary=correction_summary,
        already_applied=already_applied and not force,
    )

    return {
        "success": True,
        "action": "revise_approved_livestock_order",
        "order_id": order_id,
        "changed_by": changed_by,
        "revision_fingerprint": revision_fingerprint,
        "already_applied": already_applied and not force,
        "order_update": updates_result,
        "sale_readiness_correction": correction_summary,
        "line_sync": line_sync_result,
        "reservation": reserve_result,
        "documents": documents,
        "owner_telegram": {
            "requested": send_owner_telegram,
            "results": owner_telegram_results,
        },
        "customer_quote_send": {
            "prepared_only": bool(quote_prepare_result),
            "sent": False,
            "owner_instruction_required": True,
            "prepare_result": quote_prepare_result,
        },
        "status_log": status_log_result,
        "message": "Approved livestock order revision completed. Customer quote send is prepared only and still requires owner confirmation.",
    }


def _active_lines_match_requested_items(lines, requested_items):
    active_lines = [
        line for line in lines
        if to_clean_string(line.get("line_status")) != "Cancelled"
    ]
    grouped = {}
    for line in active_lines:
        key = to_clean_string(line.get("request_item_key"))
        grouped.setdefault(key, []).append(line)

    requested_keys = {to_clean_string(item.get("request_item_key")) for item in requested_items}
    if set(grouped.keys()) != requested_keys:
        return False

    for item in requested_items:
        key = to_clean_string(item.get("request_item_key"))
        lines_for_key = grouped.get(key, [])
        try:
            quantity = int(item.get("quantity") or 0)
        except (TypeError, ValueError):
            return False
        if len(lines_for_key) != quantity:
            return False
        expected_category = _sync_category_to_sale_category(item.get("category"))
        expected_weight = to_clean_string(item.get("weight_range"))
        expected_sex = to_clean_string(item.get("sex"))
        for line in lines_for_key:
            if expected_category and to_clean_string(line.get("sale_category")) != expected_category:
                return False
            if expected_weight and to_clean_string(line.get("weight_band")) != expected_weight:
                return False
            if expected_sex and expected_sex != "Any" and to_clean_string(line.get("sex")) != expected_sex:
                return False
    return True


def _sync_category_to_sale_category(category):
    category = to_clean_string(category)
    return {
        "Piglet": "Young Piglets",
        "Weaner": "Weaner Piglets",
        "Grower": "Grower Pigs",
        "Finisher": "Finisher Pigs",
        "Slaughter": "Ready for Slaughter",
    }.get(category, category)


def _correction_summary(correction):
    if not correction:
        return {
            "recorded": False,
            "writes_performed_by_revision_service": False,
        }
    return {
        "recorded": True,
        "pig_id": to_clean_string(correction.get("pig_id")),
        "tag_number": to_clean_string(correction.get("tag_number")),
        "weight_kg": to_float(correction.get("weight_kg")),
        "purpose": to_clean_string(correction.get("purpose", "Sale")) or "Sale",
        "correction_date": to_clean_string(correction.get("correction_date")),
        "notes": to_clean_string(correction.get("notes")),
        "writes_performed_by_revision_service": False,
        "message": "Correction evidence is recorded in the revision packet; farm weight/purpose writes remain on the approved farm-write rails.",
    }


def _revision_fingerprint(order_id, requested_items, order_updates, correction_summary, movement_form_data):
    payload = {
        "order_id": order_id,
        "requested_items": requested_items,
        "order_updates": order_updates,
        "sale_readiness_correction": correction_summary,
        "movement_form_data": movement_form_data,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _documents_have_revision_fingerprint(documents, revision_fingerprint):
    needle = f"{REVISION_FINGERPRINT_PREFIX} {revision_fingerprint}"
    for document in documents or []:
        if needle in str(document.get("Notes", "")):
            return True
    return False


def _revision_fingerprint_already_logged(order_id, revision_fingerprint):
    needle = f"{REVISION_FINGERPRINT_PREFIX} {revision_fingerprint}"
    try:
        if order_supabase_read.supabase_order_reads_available():
            logs = order_supabase_read.list_order_status_logs()
        else:
            logs = get_all_records(ORDER_STATUS_LOG_SHEET)
    except Exception:
        logs = get_all_records(ORDER_STATUS_LOG_SHEET)
    for row in logs or []:
        if to_clean_string(row.get("Order_ID")) != order_id:
            continue
        if needle in str(row.get("Notes", "")):
            return True
    return False


def _document_result_summary(document_type, result):
    return {
        "document_type": document_type,
        "success": result.get("success") is True,
        "skipped": result.get("skipped") is True,
        "reason": to_clean_string(result.get("reason")),
        "document_id": to_clean_string(result.get("document_id") or (result.get("document") or {}).get("document_id")),
        "document_ref": to_clean_string(result.get("document_ref") or (result.get("document") or {}).get("document_ref")),
        "version": result.get("version", ""),
        "google_drive_url": to_clean_string(result.get("google_drive_url") or (result.get("document") or {}).get("google_drive_url")),
    }


def _document_skipped(document_type, revision_fingerprint):
    return {
        "success": True,
        "skipped": True,
        "reason": "revision_fingerprint_already_applied",
        "document_type": document_type,
        "revision_fingerprint": revision_fingerprint,
    }


def _write_revision_log(
    order_id,
    changed_by,
    revision_fingerprint,
    line_sync_result,
    reserve_result,
    correction_summary,
    already_applied,
):
    notes = (
        f"{REVISION_FINGERPRINT_PREFIX} {revision_fingerprint}; "
        f"approved livestock order revision; "
        f"line_sync={line_sync_result.get('fulfillment_status', line_sync_result.get('reason', 'unknown'))}; "
        f"reserved_count={reserve_result.get('reserved_pig_count', '')}; "
        f"correction_recorded={correction_summary.get('recorded')}; "
        f"already_applied={already_applied}"
    )
    try:
        write_order_status_log(
            order_id=order_id,
            old_status="Approved | Approved",
            new_status="Approved | Approved",
            changed_by=changed_by,
            change_source="Oom Sakkie",
            notes=notes,
        )
    except Exception as exc:
        return {
            "success": False,
            "warning": str(exc),
        }
    return {
        "success": True,
        "revision_fingerprint": revision_fingerprint,
    }


def _truthy(value):
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}
