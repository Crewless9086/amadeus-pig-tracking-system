import logging
import tempfile
from io import BytesIO
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from modules.orders.order_service import (
    list_orders,
    get_order_detail,
    search_orders,
    get_order_operator_summary,
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
from modules.documents.loading_sheet_service import (
    generate_loading_sheet_for_order,
    send_loading_sheet_to_owner_telegram,
)
from modules.documents.movement_documents_service import (
    generate_health_declaration_for_order,
    generate_removal_certificate_for_order,
)
from modules.documents.document_service import (
    get_latest_non_voided_quote,
    get_order_document,
    get_order_documents,
    send_order_document,
)
from services.google_drive_service import download_drive_file
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
from modules.orders.order_shadow_read import compare_shadow_order
from modules.sales.sam_live_stock_sales_pack import prepare_live_stock_sales_pack

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


@orders_bp.route("/orders/search", methods=["GET"])
def order_search():
    try:
        result = search_orders(
            order_id=request.args.get("order_id", ""),
            customer_phone=request.args.get("customer_phone", ""),
            customer_name=request.args.get("customer_name", ""),
            conversation_id=request.args.get("conversation_id", ""),
            status_scope=request.args.get("status_scope", "active"),
            limit=request.args.get("limit", 5),
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "search_orders",
            "errors": [str(exc)]
        }), 400


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


@orders_bp.route("/shadow/orders/<order_id>/compare", methods=["GET"])
def shadow_order_compare(order_id):
    try:
        result, status_code = compare_shadow_order(
            order_id,
            import_batch_id=request.args.get("import_batch_id", "").strip() or None,
        )
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "status": "invalid_request",
            "errors": [str(exc)],
        }), 400


@orders_bp.route("/orders/<order_id>/operator-summary", methods=["GET"])
def order_operator_summary(order_id):
    result = get_order_operator_summary(order_id)

    if not result:
        return jsonify({
            "success": False,
            "action": "get_order_operator_summary",
            "lookup_status": "no_match",
            "order_id": order_id,
            "error": "Order not found.",
        }), 404

    return jsonify(result), 200


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
        result = auto_generate_quote_if_ready(order_id, created_by=created_by)
        if not result.get("quote_ready"):
            return jsonify(result), 400
        return jsonify(result), 201 if result.get("generated") else 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "generate_quote",
            "order_id": order_id,
            "errors": [str(exc)]
        }), 400
    except Exception as exc:
        logger.exception("Unexpected quote generation failure for order %s", order_id)
        return jsonify({
            "success": False,
            "action": "generate_quote",
            "order_id": order_id,
            "errors": [f"{exc.__class__.__name__}: {str(exc)[:240]}"],
            "message": "Quote generation failed unexpectedly. The order was not changed by this failed attempt.",
        }), 500


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


@orders_bp.route("/orders/<order_id>/quote/prepare-send", methods=["POST"])
def prepare_latest_quote_send(order_id):
    payload = request.get_json(silent=True) or {}
    conversation_id = str(payload.get("conversation_id", "")).strip()
    requested_by = str(payload.get("requested_by", payload.get("changed_by", "Oom Sakkie"))).strip() or "Oom Sakkie"

    try:
        result = _prepare_latest_quote_send_context(
            order_id,
            conversation_id=conversation_id,
            requested_by=requested_by,
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "prepare_latest_quote_send",
            "order_id": order_id,
            "send_ready": False,
            "errors": [str(exc)],
        }), 400


@orders_bp.route("/orders/<order_id>/quote/send-latest-confirmed", methods=["POST"])
def send_latest_quote_confirmed(order_id):
    payload = request.get_json(silent=True) or {}
    document_id = str(payload.get("document_id", "")).strip()
    conversation_id = str(payload.get("conversation_id", "")).strip()
    sent_by = str(payload.get("sent_by", payload.get("changed_by", "Oom Sakkie"))).strip() or "Oom Sakkie"
    account_id = str(payload.get("account_id", "147387")).strip() or "147387"
    confirmation_source = str(payload.get("confirmation_source", "")).strip()
    telegram_user_id = str(payload.get("telegram_user_id", "")).strip()
    force_resend = _truthy(payload.get("force_resend"))

    try:
        result = _send_latest_quote_confirmed(
            order_id,
            document_id=document_id,
            conversation_id=conversation_id,
            sent_by=sent_by,
            account_id=account_id,
            confirmation_source=confirmation_source,
            telegram_user_id=telegram_user_id,
            force_resend=force_resend,
        )
        status_code = 200 if result.get("success") else 502
        if result.get("skipped") and result.get("reason") != "already_sent":
            status_code = 400
        return jsonify(result), status_code
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "send_latest_quote_confirmed",
            "order_id": order_id,
            "document_id": document_id,
            "conversation_id": conversation_id,
            "errors": [str(exc)],
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


@orders_bp.route("/orders/<order_id>/loading-sheet", methods=["POST"])
def generate_loading_sheet(order_id):
    payload = request.get_json(silent=True) or {}
    created_by = str(payload.get("created_by", payload.get("changed_by", "App"))).strip() or "App"

    try:
        result = generate_loading_sheet_for_order(order_id, created_by=created_by)
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "generate_loading_sheet",
            "order_id": order_id,
            "errors": [str(exc)]
        }), 400
    except Exception as exc:
        logger.exception("Unexpected loading sheet generation failure for order %s", order_id)
        return jsonify({
            "success": False,
            "action": "generate_loading_sheet",
            "order_id": order_id,
            "errors": [f"{exc.__class__.__name__}: {str(exc)[:240]}"],
            "message": "Loading sheet generation failed unexpectedly.",
        }), 500


@orders_bp.route("/orders/<order_id>/sales-pack/prepare", methods=["POST"])
def prepare_live_stock_order_sales_pack(order_id):
    payload = request.get_json(silent=True) or {}
    try:
        result = prepare_live_stock_sales_pack(order_id, payload)
        return jsonify(result), 200 if result.get("success") else 400
    except ValueError as exc:
        return jsonify({
            "success": False,
            "status": "sam_live_stock_sales_pack_invalid",
            "order_id": order_id,
            "errors": [str(exc)],
            "customer_send_allowed": False,
        }), 400
    except Exception as exc:
        logger.exception("Unexpected live-stock sales-pack preparation failure for order %s", order_id)
        return jsonify({
            "success": False,
            "status": "sam_live_stock_sales_pack_failed",
            "order_id": order_id,
            "errors": [f"{exc.__class__.__name__}: {str(exc)[:240]}"],
            "customer_send_allowed": False,
        }), 500


@orders_bp.route("/orders/<order_id>/removal-certificate", methods=["POST"])
def generate_removal_certificate(order_id):
    payload = request.get_json(silent=True) or {}
    created_by = str(payload.get("created_by", payload.get("changed_by", "App"))).strip() or "App"
    form_data = payload.get("form_data") if isinstance(payload.get("form_data"), dict) else payload

    try:
        result = generate_removal_certificate_for_order(order_id, form_data=form_data, created_by=created_by)
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "generate_removal_certificate",
            "order_id": order_id,
            "errors": [str(exc)]
        }), 400
    except Exception as exc:
        logger.exception("Unexpected removal certificate generation failure for order %s", order_id)
        return jsonify({
            "success": False,
            "action": "generate_removal_certificate",
            "order_id": order_id,
            "errors": [f"{exc.__class__.__name__}: {str(exc)[:240]}"],
        }), 500


@orders_bp.route("/orders/<order_id>/health-declaration", methods=["POST"])
def generate_health_declaration(order_id):
    payload = request.get_json(silent=True) or {}
    created_by = str(payload.get("created_by", payload.get("changed_by", "App"))).strip() or "App"
    form_data = payload.get("form_data") if isinstance(payload.get("form_data"), dict) else payload

    try:
        result = generate_health_declaration_for_order(order_id, form_data=form_data, created_by=created_by)
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "generate_health_declaration",
            "order_id": order_id,
            "errors": [str(exc)]
        }), 400
    except Exception as exc:
        logger.exception("Unexpected health declaration generation failure for order %s", order_id)
        return jsonify({
            "success": False,
            "action": "generate_health_declaration",
            "order_id": order_id,
            "errors": [f"{exc.__class__.__name__}: {str(exc)[:240]}"],
        }), 500


@orders_bp.route("/order-documents/<document_id>/download", methods=["GET"])
def download_order_document(document_id):
    try:
        document = get_order_document(document_id)
        if not document:
            return jsonify({"success": False, "errors": ["Document not found."]}), 404
        drive_file_id = str(document.get("Google_Drive_File_ID", "")).strip()
        if not drive_file_id:
            return jsonify({"success": False, "errors": ["Document is missing a Google Drive file ID."]}), 400
        file_name = _safe_download_filename(str(document.get("File_Name", "")).strip() or f"{document_id}.pdf")
        with tempfile.TemporaryDirectory(prefix="amadeus-order-document-") as temp_dir:
            pdf_path = Path(temp_dir) / file_name
            download_drive_file(drive_file_id, pdf_path)
            pdf_bytes = pdf_path.read_bytes()
            return send_file(
                BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=False,
                download_name=file_name,
            )
    except ValueError as exc:
        return jsonify({"success": False, "errors": [str(exc)]}), 400
    except Exception as exc:
        logger.exception("Unexpected document download failure for document %s", document_id)
        return jsonify({
            "success": False,
            "errors": [f"{exc.__class__.__name__}: {str(exc)[:240]}"],
        }), 500


@orders_bp.route("/order-documents/<document_id>/send-telegram", methods=["POST"])
def send_loading_sheet_telegram(document_id):
    payload = request.get_json(silent=True) or {}
    sent_by = str(payload.get("sent_by", payload.get("changed_by", "App"))).strip() or "App"
    chat_id = str(payload.get("chat_id", "")).strip()

    try:
        result = send_loading_sheet_to_owner_telegram(
            document_id,
            sent_by=sent_by,
            chat_id=chat_id,
        )
        return jsonify(result), 200 if result.get("success") else 502
    except ValueError as exc:
        return jsonify({
            "success": False,
            "action": "send_loading_sheet_telegram",
            "document_id": document_id,
            "errors": [str(exc)]
        }), 400


@orders_bp.route("/order-documents/<document_id>/send", methods=["POST"])
def send_document(document_id):
    payload = request.get_json(silent=True) or {}
    conversation_id = str(payload.get("conversation_id", "")).strip()
    sent_by = str(payload.get("sent_by", payload.get("changed_by", "App"))).strip() or "App"
    account_id = str(payload.get("account_id", "147387")).strip() or "147387"
    force_resend = _truthy(payload.get("force_resend"))

    try:
        result = send_order_document(
            document_id,
            conversation_id=conversation_id,
            sent_by=sent_by,
            account_id=account_id,
            force_resend=force_resend,
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


def _safe_download_filename(value):
    cleaned = str(value or "").strip() or "document.pdf"
    cleaned = cleaned.replace("\\", "_").replace("/", "_").replace(":", "_")
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


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


def _prepare_latest_quote_send_context(order_id, conversation_id="", requested_by="Oom Sakkie"):
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("order_id is required.")

    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    order = detail.get("order") or {}
    _ensure_order_allows_quote_send(order)
    order_conversation_id = str(order.get("conversation_id", "")).strip()
    destination_conversation_id = str(conversation_id or "").strip() or order_conversation_id
    destination_source = "operator_input" if str(conversation_id or "").strip() else "order_record"

    if not destination_conversation_id:
        raise ValueError("No confirmed customer conversation is available for this order.")

    quote = get_latest_non_voided_quote(order_id)
    if not quote:
        raise ValueError("No generated quote is available for this order.")

    document_id = str(quote.get("Document_ID", "")).strip()
    document_ref = str(quote.get("Document_Ref", "")).strip()
    document_status = str(quote.get("Document_Status", "")).strip()
    document_type = str(quote.get("Document_Type", "")).strip()

    if not document_id:
        raise ValueError("Latest quote is missing a document ID.")
    if document_type != "Quote":
        raise ValueError("Latest sendable document is not a quote.")
    if document_status == "Voided":
        raise ValueError("Voided quotes cannot be sent.")
    if document_status == "Superseded":
        raise ValueError("Superseded quotes cannot be sent.")

    total = quote.get("Total", "")
    customer_name = str(order.get("customer_name", "")).strip()
    message = (
        f"Quote {document_ref} is ready for {customer_name or 'the customer'}. "
        f"Total R{total}. Send it to the customer?"
    )

    return {
        "success": True,
        "action": "prepare_latest_quote_send",
        "send_ready": True,
        "order_id": order_id,
        "customer_name": customer_name,
        "requested_by": str(requested_by or "").strip() or "Oom Sakkie",
        "destination": {
            "conversation_id": destination_conversation_id,
            "source": destination_source,
            "confirmed": True,
        },
        "document": {
            "document_id": document_id,
            "document_type": document_type,
            "document_ref": document_ref,
            "document_status": document_status,
            "total": total,
            "valid_until": str(quote.get("Valid_Until", "")).strip(),
        },
        "button_context": {
            "send_label": "Send quote to customer",
            "cancel_label": "Cancel",
            "callback_action": "send_latest_quote_confirmed",
            "callback_data": (
                f"quote_send|{order_id}|{document_id}|{destination_conversation_id}"
            ),
            "cancel_callback_data": f"quote_cancel|{order_id}|{document_id}",
        },
        "message": message,
    }


def _send_latest_quote_confirmed(
    order_id,
    document_id,
    conversation_id,
    sent_by="Oom Sakkie",
    account_id="147387",
    confirmation_source="",
    telegram_user_id="",
    force_resend=False,
):
    order_id = str(order_id or "").strip()
    document_id = str(document_id or "").strip()
    conversation_id = str(conversation_id or "").strip()

    if not order_id:
        raise ValueError("order_id is required.")
    if not document_id:
        raise ValueError("document_id is required.")
    if not conversation_id:
        raise ValueError("conversation_id is required.")

    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")
    _ensure_order_allows_quote_send(detail.get("order") or {})

    quote = get_latest_non_voided_quote(order_id)
    if not quote:
        raise ValueError("No generated quote is available for this order.")

    latest_document_id = str(quote.get("Document_ID", "")).strip()
    document_type = str(quote.get("Document_Type", "")).strip()
    document_status = str(quote.get("Document_Status", "")).strip()

    if latest_document_id != document_id:
        raise ValueError("The selected quote is no longer the latest sendable quote. Refresh the order documents before sending.")
    if document_type != "Quote":
        raise ValueError("Latest sendable document is not a quote.")
    if document_status == "Voided":
        raise ValueError("Voided quotes cannot be sent.")
    if document_status == "Superseded":
        raise ValueError("Superseded quotes cannot be sent.")

    result = send_order_document(
        document_id,
        conversation_id=conversation_id,
        sent_by=sent_by,
        account_id=account_id,
        force_resend=force_resend,
    )
    result["action"] = "send_latest_quote_confirmed"
    result["order_id"] = str(result.get("order_id") or order_id).strip()
    result["document_id"] = str(result.get("document_id") or document_id).strip()
    result["conversation_id"] = str(result.get("conversation_id") or conversation_id).strip()
    result["confirmation_source"] = str(confirmation_source or "").strip()
    result["telegram_user_id"] = str(telegram_user_id or "").strip()
    return result


def _ensure_order_allows_quote_send(order):
    order_status = str(order.get("order_status", order.get("Order_Status", ""))).strip()
    approval_status = str(order.get("approval_status", order.get("Approval_Status", ""))).strip()
    terminal_statuses = {"Cancelled", "Completed", "Rejected"}

    if order_status in terminal_statuses:
        raise ValueError(f"Quote cannot be sent because order is {order_status}.")
    if approval_status == "Rejected":
        raise ValueError("Quote cannot be sent because order approval was rejected.")


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
