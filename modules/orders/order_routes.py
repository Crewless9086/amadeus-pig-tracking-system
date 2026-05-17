import logging

from flask import Blueprint, jsonify, request

from modules.orders.order_service import (
    list_orders,
    get_order_detail,
    get_active_customer_order_context,
    get_available_pigs_for_orders,
    create_order,
    update_order,
    create_order_line,
    update_order_line,
    delete_order_line,
    reserve_order_lines,
    release_order_lines,
    send_order_for_approval,
    approve_order,
    reject_order,
    cancel_order,
    complete_order,
    sync_order_lines_from_request,
    create_order_with_lines,
)
from modules.documents.quote_service import (
    auto_generate_quote_if_ready,
    auto_generate_quote_if_ready_with_retry,
    generate_quote_for_order,
)
from modules.documents.invoice_service import generate_invoice_for_order
from modules.documents.document_service import (
    get_latest_non_voided_quote,
    get_order_documents,
    send_order_document,
)
from modules.orders.order_intake_service import (
    get_intake_context,
    update_intake_state,
    reset_intake,
    validate_intake_update_payload,
)
from modules.orders.order_validation import (
    validate_new_order_payload,
    validate_update_order_payload,
    validate_new_order_line_payload,
    validate_update_order_line_payload,
    validate_sync_order_lines_payload,
)

orders_bp = Blueprint("orders", __name__)
logger = logging.getLogger(__name__)


@orders_bp.route("/orders", methods=["GET"])
def order_list():
    records = list_orders()
    return jsonify({
        "success": True,
        "count": len(records),
        "orders": records
    })


@orders_bp.route("/order-intake/context", methods=["GET"])
def order_intake_context():
    try:
        result = get_intake_context(
            conversation_id=request.args.get("conversation_id", ""),
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/order-intake/update", methods=["POST"])
def order_intake_update():
    payload = request.get_json(silent=True) or {}
    validation = validate_intake_update_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = update_intake_state(validation["cleaned_data"])
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/order-intake/<conversation_id>/reset", methods=["POST"])
def order_intake_reset(conversation_id):
    payload = request.get_json(silent=True) or {}
    closed_reason = str(payload.get("closed_reason", "admin_reset")).strip() or "admin_reset"
    updated_by = str(payload.get("updated_by", payload.get("changed_by", "App"))).strip() or "App"

    try:
        result = reset_intake(
            conversation_id,
            closed_reason=closed_reason,
            updated_by=updated_by,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/active-customer-context", methods=["GET"])
def active_customer_order_context():
    try:
        result = get_active_customer_order_context(
            order_id=request.args.get("order_id", ""),
            conversation_id=request.args.get("conversation_id", ""),
            customer_phone=request.args.get("customer_phone", ""),
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>", methods=["GET"])
def order_detail(order_id):
    detail = get_order_detail(order_id)

    if not detail:
        return jsonify({
            "success": False,
            "error": "Order not found."
        }), 404

    return jsonify({
        "success": True,
        "order": detail["order"],
        "lines": detail["lines"],
        "documents": _serialize_order_documents(get_order_documents(order_id)),
    })


@orders_bp.route("/orders/available-pigs", methods=["GET"])
def available_pigs():
    pigs = get_available_pigs_for_orders()
    return jsonify({
        "success": True,
        "count": len(pigs),
        "pigs": pigs,
    })


@orders_bp.route("/orders/<order_id>/reserve", methods=["POST"])
def reserve_order(order_id):
    try:
        result = reserve_order_lines(order_id)
        status_code = 200 if result.get("success") else 422
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/release", methods=["POST"])
def release_order(order_id):
    try:
        result = release_order_lines(order_id)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/send-for-approval", methods=["POST"])
def send_for_approval(order_id):
    payload = request.get_json(silent=True) or {}
    changed_by = str(payload.get("changed_by", "App")).strip() or "App"

    try:
        result = send_order_for_approval(order_id, changed_by=changed_by)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/approve", methods=["POST"])
def approve(order_id):
    payload = request.get_json(silent=True) or {}
    changed_by = str(payload.get("changed_by", "App")).strip() or "App"

    try:
        result = approve_order(order_id, changed_by=changed_by)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/reject", methods=["POST"])
def reject(order_id):
    payload = request.get_json(silent=True) or {}
    changed_by = str(payload.get("changed_by", "App")).strip() or "App"

    try:
        result = reject_order(order_id, changed_by=changed_by)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/cancel", methods=["POST"])
def cancel(order_id):
    payload = request.get_json(silent=True) or {}
    changed_by = str(payload.get("changed_by", "App")).strip() or "App"
    reason = str(payload.get("reason", "")).strip()

    try:
        result = cancel_order(order_id, changed_by=changed_by, reason=reason)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/complete", methods=["POST"])
def complete(order_id):
    payload = request.get_json(silent=True) or {}
    changed_by = str(payload.get("changed_by", "App")).strip() or "App"

    try:
        result = complete_order(order_id, changed_by=changed_by)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/quote", methods=["POST"])
def generate_quote(order_id):
    payload = request.get_json(silent=True) or {}
    created_by = str(payload.get("created_by", payload.get("changed_by", "App"))).strip() or "App"

    try:
        result = generate_quote_for_order(order_id, created_by=created_by)
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/quote/send-latest", methods=["POST"])
def send_latest_quote(order_id):
    payload = request.get_json(silent=True) or {}
    conversation_id = str(payload.get("conversation_id", "")).strip()
    sent_by = str(payload.get("sent_by", payload.get("changed_by", "App"))).strip() or "App"
    account_id = str(payload.get("account_id", "147387")).strip() or "147387"

    try:
        quote = get_latest_non_voided_quote(order_id)
        ensure_result = None
        if not quote:
            ensure_result = auto_generate_quote_if_ready_with_retry(
                order_id,
                created_by=sent_by,
            )
            if not ensure_result.get("quote_ready"):
                missing = ensure_result.get("missing_fields", [])
                detail = f" Missing fields: {', '.join(missing)}." if missing else ""
                raise ValueError("No generated quote was found and the order is not quote-ready." + detail)
            quote = get_latest_non_voided_quote(order_id)
            if not quote:
                raise ValueError("Quote generation did not create a sendable quote document.")

        document_id = str(quote.get("Document_ID", "")).strip()
        if not document_id:
            raise ValueError("Latest quote is missing a document ID.")

        result = send_order_document(
            document_id,
            conversation_id=conversation_id,
            sent_by=sent_by,
            account_id=account_id,
        )
        result["action"] = "send_latest_quote"
        result["order_id"] = str(result.get("order_id") or order_id).strip()
        if ensure_result:
            result["quote_ensured"] = True
            result["ensure_quote_reason"] = str(ensure_result.get("reason", "")).strip()
        status_code = 200 if result.get("success") else 502
        if result.get("skipped") and result.get("reason") != "already_sent":
            status_code = 400
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "send_latest_quote",
            "order_id": order_id,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/orders/<order_id>/invoice", methods=["POST"])
def generate_invoice(order_id):
    payload = request.get_json(silent=True) or {}
    created_by = str(payload.get("created_by", payload.get("changed_by", "App"))).strip() or "App"

    try:
        result = generate_invoice_for_order(order_id, created_by=created_by)
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/order-documents/<document_id>/send", methods=["POST"])
def send_document(document_id):
    payload = request.get_json(silent=True) or {}
    conversation_id = str(payload.get("conversation_id", "")).strip()
    sent_by = str(payload.get("sent_by", payload.get("changed_by", "App"))).strip() or "App"
    account_id = str(payload.get("account_id", "147387")).strip() or "147387"

    try:
        result = send_order_document(
            document_id,
            conversation_id=conversation_id,
            sent_by=sent_by,
            account_id=account_id,
        )
        status_code = 200 if result.get("success") else 502
        if result.get("skipped") and result.get("reason") != "already_sent":
            status_code = 400
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/master/orders", methods=["POST"])
def new_order():
    payload = request.get_json(silent=True) or {}
    validation = validate_new_order_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    result = create_order(validation["cleaned_data"])
    return jsonify(result), 201


@orders_bp.route("/master/orders/create-with-lines", methods=["POST"])
def new_order_with_lines():
    payload = request.get_json(silent=True) or {}
    order_validation = validate_new_order_payload(payload)
    sync_validation = validate_sync_order_lines_payload(payload)

    errors = []
    if not order_validation["is_valid"]:
        errors.extend(order_validation["errors"])
    if not sync_validation["is_valid"]:
        errors.extend(sync_validation["errors"])

    if errors:
        return jsonify({
            "success": False,
            "errors": errors,
        }), 400

    try:
        result = create_order_with_lines(
            order_validation["cleaned_data"],
            sync_validation["cleaned_data"],
        )
        _attach_auto_quote_result(
            result,
            result.get("order_id", ""),
            changed_by=order_validation["cleaned_data"].get("created_by", "App"),
        )
        _attach_quote_send_result(
            result,
            send_quote_if_ready=_truthy(payload.get("send_quote_if_ready")),
            conversation_id=payload.get("conversation_id", ""),
            account_id=payload.get("account_id", "147387"),
            sent_by=payload.get(
                "sent_by",
                payload.get(
                    "changed_by",
                    order_validation["cleaned_data"].get("created_by", "App"),
                ),
            ),
        )
        status_code = 201 if result.get("create_success") else 400
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/master/orders/<order_id>", methods=["PATCH"])
def edit_order(order_id):
    payload = request.get_json(silent=True) or {}
    validation = validate_update_order_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = update_order(order_id, validation["cleaned_data"])
        _attach_auto_quote_result(
            result,
            order_id,
            changed_by=validation["cleaned_data"].get("changed_by", "App"),
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/master/orders/<order_id>/sync-lines", methods=["POST"])
def sync_order_lines(order_id):
    payload = request.get_json(silent=True) or {}
    validation = validate_sync_order_lines_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = sync_order_lines_from_request(order_id, validation["cleaned_data"])
        _attach_auto_quote_result(
            result,
            order_id,
            changed_by=validation["cleaned_data"].get("changed_by", "App"),
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/master/order-lines", methods=["POST"])
def new_order_line():
    payload = request.get_json(silent=True) or {}
    validation = validate_new_order_line_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = create_order_line(validation["cleaned_data"])
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/master/order-lines/<order_line_id>", methods=["PATCH"])
def edit_order_line(order_line_id):
    payload = request.get_json(silent=True) or {}
    validation = validate_update_order_line_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = update_order_line(order_line_id, validation["cleaned_data"])
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/master/order-lines/<order_line_id>", methods=["DELETE"])
def remove_order_line(order_line_id):
    try:
        result = delete_order_line(order_line_id)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400


def _serialize_order_documents(documents):
    serialized = []

    for row in documents:
        serialized.append({
            "document_id": str(row.get("Document_ID", "")).strip(),
            "order_id": str(row.get("Order_ID", "")).strip(),
            "document_type": str(row.get("Document_Type", "")).strip(),
            "document_ref": str(row.get("Document_Ref", "")).strip(),
            "payment_ref": str(row.get("Payment_Ref", "")).strip(),
            "version": row.get("Version", ""),
            "document_status": str(row.get("Document_Status", "")).strip(),
            "payment_method": str(row.get("Payment_Method", "")).strip(),
            "vat_rate": row.get("VAT_Rate", ""),
            "subtotal_ex_vat": row.get("Subtotal_Ex_VAT", ""),
            "vat_amount": row.get("VAT_Amount", ""),
            "total": row.get("Total", ""),
            "valid_until": str(row.get("Valid_Until", "")).strip(),
            "google_drive_file_id": str(row.get("Google_Drive_File_ID", "")).strip(),
            "google_drive_url": str(row.get("Google_Drive_URL", "")).strip(),
            "file_name": str(row.get("File_Name", "")).strip(),
            "created_at": str(row.get("Created_At", "")).strip(),
            "created_by": str(row.get("Created_By", "")).strip(),
            "sent_at": str(row.get("Sent_At", "")).strip(),
            "sent_by": str(row.get("Sent_By", "")).strip(),
            "notes": str(row.get("Notes", "")).strip(),
        })

    def sort_key(item):
        try:
            version = int(item.get("version") or 0)
        except (TypeError, ValueError):
            version = 0
        return (item.get("document_type", ""), version, item.get("created_at", ""))

    return sorted(serialized, key=sort_key, reverse=True)


def _attach_auto_quote_result(result, order_id, changed_by="App"):
    if not result or not order_id:
        return
    if result.get("cancelled_empty_order") is True:
        return
    if result.get("success") is not True and result.get("sync_success") is not True:
        return
    if result.get("partial_fulfillment") is True:
        result["auto_quote"] = _auto_quote_skipped_incomplete(order_id)
        return
    if "complete_fulfillment" in result and result.get("complete_fulfillment") is not True:
        result["auto_quote"] = _auto_quote_skipped_incomplete(order_id)
        return

    try:
        result["auto_quote"] = auto_generate_quote_if_ready(
            order_id,
            created_by=changed_by or "App",
        )
    except Exception as exc:
        logger.exception("Automatic quote generation failed for order %s", order_id)
        result["auto_quote"] = {
            "success": False,
            "action": "auto_generate_quote_if_ready",
            "quote_ready": False,
            "generated": False,
            "skipped": True,
            "reason": "auto_quote_error",
            "order_id": order_id,
            "errors": [str(exc)],
            "message": "Automatic quote generation failed after the order update.",
        }


def _attach_quote_send_result(
    result,
    send_quote_if_ready=False,
    conversation_id="",
    account_id="147387",
    sent_by="App",
):
    if not result or not send_quote_if_ready:
        return

    document = (result.get("auto_quote") or {}).get("document") or {}
    document_id = str(document.get("document_id", "")).strip()
    if not document_id:
        ensure_result = auto_generate_quote_if_ready_with_retry(
            str(result.get("order_id", "")).strip(),
            created_by=sent_by or "App",
        )
        result["auto_quote"] = ensure_result
        document = (ensure_result or {}).get("document") or {}
        document_id = str(document.get("document_id", "")).strip()

    if not document_id:
        result["quote_send"] = {
            "success": False,
            "skipped": True,
            "reason": "quote_not_ready",
            "order_id": str(result.get("order_id", "")).strip(),
            "message": "Quote was not generated, so it could not be sent.",
        }
        return

    try:
        quote_send = send_order_document(
            document_id,
            conversation_id=str(conversation_id or "").strip(),
            sent_by=str(sent_by or "App").strip() or "App",
            account_id=str(account_id or "147387").strip() or "147387",
        )
        quote_send["action"] = "send_latest_quote"
        result["quote_send"] = quote_send
    except Exception as exc:
        logger.exception(
            "Automatic quote send failed for order %s",
            result.get("order_id", ""),
        )
        result["quote_send"] = {
            "success": False,
            "action": "send_latest_quote",
            "order_id": str(result.get("order_id", "")).strip(),
            "document_id": document_id,
            "errors": [str(exc)],
            "message": "Quote was generated but could not be sent automatically.",
        }


def _truthy(value):
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}


def _auto_quote_skipped_incomplete(order_id):
    return {
        "success": True,
        "action": "auto_generate_quote_if_ready",
        "quote_ready": False,
        "generated": False,
        "skipped": True,
        "reason": "incomplete_fulfillment",
        "order_id": order_id,
        "missing_fields": ["complete_order_lines"],
        "message": "Quote was not generated because the draft lines do not fully match the requested quantity.",
    }
