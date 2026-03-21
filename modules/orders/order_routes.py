from flask import Blueprint, jsonify, request

from modules.orders.order_service import (
    list_orders,
    get_order_detail,
    get_available_pigs_for_orders,
    create_order,
    create_order_line,
)
from modules.orders.order_validation import (
    validate_new_order_payload,
    validate_new_order_line_payload,
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