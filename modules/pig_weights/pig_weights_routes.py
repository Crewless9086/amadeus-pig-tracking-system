from flask import Blueprint, jsonify, request
from modules.pig_weights.pig_weights_controller import (
    get_status,
    list_active_pigs,
    list_sales_availability,
    get_litter_profile,
    list_products,
    list_pens,
    get_pig_profile,
    get_pig_treatment_history,
    get_pig_movement_history,
    get_pig_weight_history,
    get_latest_weight,
    create_weight_entry,
    create_treatment_entry,
    create_movement_entry,
)

pig_weights_bp = Blueprint("pig_weights", __name__)


@pig_weights_bp.route("/status", methods=["GET"])
def status():
    return jsonify(get_status())


@pig_weights_bp.route("/pigs", methods=["GET"])
def pigs():
    return jsonify(list_active_pigs())


@pig_weights_bp.route("/sales-availability", methods=["GET"])
def sales_availability():
    return jsonify(list_sales_availability())


@pig_weights_bp.route("/litter/<litter_id>/detail", methods=["GET"])
def litter_detail(litter_id):
    result, status_code = get_litter_profile(litter_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/products", methods=["GET"])
def products():
    return jsonify(list_products())


@pig_weights_bp.route("/pens", methods=["GET"])
def pens():
    return jsonify(list_pens())


@pig_weights_bp.route("/<pig_id>/detail", methods=["GET"])
def pig_detail(pig_id):
    result, status_code = get_pig_profile(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/<pig_id>/history", methods=["GET"])
def pig_history(pig_id):
    result, status_code = get_pig_weight_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/<pig_id>/treatments", methods=["GET"])
def pig_treatments(pig_id):
    result, status_code = get_pig_treatment_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/<pig_id>/movements", methods=["GET"])
def pig_movements(pig_id):
    result, status_code = get_pig_movement_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/<pig_id>/latest", methods=["GET"])
def latest_weight(pig_id):
    return jsonify(get_latest_weight(pig_id))


@pig_weights_bp.route("", methods=["POST"])
def create_weight():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_weight_entry(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/treatments", methods=["POST"])
def create_treatment():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_treatment_entry(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/movements", methods=["POST"])
def create_movement():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_movement_entry(payload)
    return jsonify(result), status_code