from flask import Blueprint, jsonify, request

from modules.pig_weights.mating_service import (
    get_breeding_options,
    get_mating_overview,
    save_new_mating,
    assume_pregnant,
)
from modules.pig_weights.mating_validation import (
    validate_new_mating_payload,
    validate_assume_pregnant_payload,
)

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


@mating_bp.route("/master/matings/<mating_id>/assume-pregnant", methods=["POST"])
def assume_pregnant_route(mating_id):
    payload = request.get_json(silent=True) or {}
    validation = validate_assume_pregnant_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = assume_pregnant(
            mating_id=mating_id,
            target_pen_id=validation["cleaned_data"]["target_pen_id"],
            moved_by=validation["cleaned_data"]["moved_by"],
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400