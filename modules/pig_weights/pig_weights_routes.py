from flask import Blueprint, jsonify
from modules.pig_weights.pig_weights_controller import get_status

pig_weights_bp = Blueprint("pig_weights", __name__)


@pig_weights_bp.route("/status", methods=["GET"])
def status():
    return jsonify(get_status())