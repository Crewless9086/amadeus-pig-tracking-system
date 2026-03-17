from modules.pig_weights.pig_weights_service import (
    get_active_pigs,
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