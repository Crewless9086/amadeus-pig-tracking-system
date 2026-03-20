from flask import Blueprint, jsonify, request

from modules.pig_weights.mating_service import (
    get_breeding_options,
    get_mating_overview,
    save_new_mating,
)
from modules.pig_weights.mating_validation import validate_new_mating_payload

mating_bp = Blueprint("mating", __name__)


@mating_bp.route("/breeding-options", methods=["GET"])
def breeding_options():
    return jsonify({
        "success": True,
        "options": get_breeding_options()
    })


@mating_bp.route("/matings", methods=["GET"])
def mating_list():
    records = get_mating_overview()
    return jsonify({
        "success": True,
        "count": len(records),
        "records": records
    })


@mating_bp.route("/master/matings", methods=["POST"])
def create_mating():
    payload = request.get_json(silent=True) or {}
    validation = validate_new_mating_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    result = save_new_mating(validation["cleaned_data"])
    return jsonify(result), 201