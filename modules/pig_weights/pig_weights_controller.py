from modules.pig_weights.pig_weights_service import (
    get_active_pigs,
    get_pig_detail,
    get_weight_history_for_pig,
    get_latest_weight_for_pig,
    save_weight_entry,
)
from modules.pig_weights.pig_weights_validation import validate_weight_payload


def get_status():
    return {
        "module": "pig_weights",
        "status": "running"
    }


def list_active_pigs():
    pigs = get_active_pigs()
    return {
        "count": len(pigs),
        "pigs": pigs
    }


def get_pig_profile(pig_id: str):
    pig = get_pig_detail(pig_id)
    if not pig:
        return {
            "success": False,
            "error": "Pig not found."
        }, 404

    return {
        "success": True,
        "pig": pig
    }, 200


def get_pig_weight_history(pig_id: str):
    history = get_weight_history_for_pig(pig_id)
    return {
        "success": True,
        "pig_id": history["pig_id"],
        "tag_number": history["tag_number"],
        "count": history["count"],
        "history": history["history"],
    }, 200


def get_latest_weight(pig_id: str):
    return get_latest_weight_for_pig(pig_id)


def create_weight_entry(payload: dict):
    validation = validate_weight_payload(payload)

    if not validation["is_valid"]:
        return {
            "success": False,
            "errors": validation["errors"]
        }, 400

    result = save_weight_entry(validation["cleaned_data"])
    return result, 201