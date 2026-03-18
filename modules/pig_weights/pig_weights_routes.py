from flask import Blueprint, jsonify, request
from modules.pig_weights.pig_weights_controller import (
    get_status,
    list_active_pigs,
    get_pig_profile,
    get_pig_weight_history,
    get_latest_weight,
    create_weight_entry,
)

pig_weights_bp = Blueprint("pig_weights", __name__)


@pig_weights_bp.route("/status", methods=["GET"])
def status():
    return jsonify(get_status())


@pig_weights_bp.route("/pigs", methods=["GET"])
def pigs():
    return jsonify(list_active_pigs())


@pig_weights_bp.route("/<pig_id>/detail", methods=["GET"])
def pig_detail(pig_id):
    result, status_code = get_pig_profile(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/<pig_id>/history", methods=["GET"])
def pig_history(pig_id):
    result, status_code = get_pig_weight_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/<pig_id>/latest", methods=["GET"])
def latest_weight(pig_id):
    return jsonify(get_latest_weight(pig_id))


@pig_weights_bp.route("", methods=["POST"])
def create_weight():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_weight_entry(payload)
    return jsonify(result), status_code