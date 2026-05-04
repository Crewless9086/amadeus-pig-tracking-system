from flask import Blueprint, jsonify, request

from modules.orders.order_service import (
    list_orders,
    get_order_detail,
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
)
from modules.orders.order_validation import (
    validate_new_order_payload,
    validate_update_order_payload,
    validate_new_order_line_payload,
    validate_update_order_line_payload,
    validate_sync_order_lines_payload,
)

orders_bp = Blueprint("orders", __name__)


@orders_bp.route("/orders", methods=["GET"])
def order_list():
    records = list_orders()
    return jsonify({
        "success": True,
        "count": len(records),
        "orders": records
    })


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