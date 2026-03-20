from flask import Blueprint, jsonify, request

from modules.pig_weights.pig_weights_controller import (
    get_status,
    get_dashboard_data,
    get_sales_dashboard_data,
    list_parent_options,
    list_active_pigs,
    list_sales_availability,
    get_family_tree_profile,
    get_litter_profile,
    list_products,
    list_pens,
    get_pig_profile,
    get_pig_treatment_history,
    get_pig_movement_history,
    get_pig_weight_history,
    get_latest_weight,
    create_new_pig,
    create_new_product,
    create_new_pen,
    create_new_litter,
    create_weight_entry,
    create_treatment_entry,
    create_movement_entry,
)

pig_weights_bp = Blueprint("pig_weights", __name__)


@pig_weights_bp.route("/status", methods=["GET"])
def status():
    return jsonify(get_status())


@pig_weights_bp.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify(get_dashboard_data())


@pig_weights_bp.route("/sales-dashboard", methods=["GET"])
def sales_dashboard():
    return jsonify(get_sales_dashboard_data())


@pig_weights_bp.route("/parent-options", methods=["GET"])
def parent_options():
    return jsonify(list_parent_options())


@pig_weights_bp.route("/pigs", methods=["GET"])
def pigs():
    return jsonify(list_active_pigs())


@pig_weights_bp.route("/sales-availability", methods=["GET"])
def sales_availability():
    return jsonify(list_sales_availability())


@pig_weights_bp.route("/products", methods=["GET"])
def products():
    return jsonify(list_products())


@pig_weights_bp.route("/pens", methods=["GET"])
def pens():
    return jsonify(list_pens())


@pig_weights_bp.route("/pig/<pig_id>", methods=["GET"])
def pig_profile(pig_id):
    result, status_code = get_pig_profile(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/family-tree", methods=["GET"])
def family_tree(pig_id):
    result, status_code = get_family_tree_profile(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/weights", methods=["GET"])
def pig_weights(pig_id):
    result, status_code = get_pig_weight_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/treatments", methods=["GET"])
def pig_treatments(pig_id):
    result, status_code = get_pig_treatment_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/movements", methods=["GET"])
def pig_movements(pig_id):
    result, status_code = get_pig_movement_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/latest-weight", methods=["GET"])
def latest_weight(pig_id):
    return jsonify(get_latest_weight(pig_id))


@pig_weights_bp.route("/litter/<litter_id>", methods=["GET"])
def litter_profile(litter_id):
    result, status_code = get_litter_profile(litter_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/master/pigs", methods=["POST"])
def new_pig():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_new_pig(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/master/products", methods=["POST"])
def new_product():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_new_product(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/master/pens", methods=["POST"])
def new_pen():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_new_pen(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/master/litters", methods=["POST"])
def new_litter():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_new_litter(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/weights", methods=["POST"])
def add_weight():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_weight_entry(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/treatments", methods=["POST"])
def add_treatment():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_treatment_entry(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/movements", methods=["POST"])
def add_movement():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_movement_entry(payload)
    return jsonify(result), status_code