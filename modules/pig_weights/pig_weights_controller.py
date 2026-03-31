from modules.pig_weights.pig_weights_service import (
    get_dashboard_summary,
    get_sales_stock_summary,
    get_sales_stock_totals,
    get_parent_options,
    get_active_pigs,
    get_sales_availability,
    get_family_tree,
    get_litter_detail,
    get_pig_detail,
    get_products,
    get_pens,
    get_treatment_history_for_pig,
    get_movement_history_for_pig,
    get_weight_history_for_pig,
    get_weight_entries_by_date,
    get_latest_weight_for_pig,
    save_new_pig,
    save_new_product,
    save_new_pen,
    save_new_litter,
    save_weight_entry,
    save_weight_entry_with_optional_move,
    save_treatment_entry,
    save_movement_entry,
)
from modules.pig_weights.pig_weights_validation import (
    validate_weight_payload,
    validate_weight_with_optional_move_payload,
    validate_treatment_payload,
    validate_movement_payload,
    validate_new_pig_payload,
    validate_new_product_payload,
    validate_new_pen_payload,
    validate_new_litter_payload,
)


def get_status():
    return {
        "module": "pig_weights",
        "status": "running"
    }


def get_dashboard_data():
    return {
        "success": True,
        "summary": get_dashboard_summary()
    }


def get_sales_dashboard_data():
    return {
        "success": True,
        "totals": get_sales_stock_totals(),
        "summary": get_sales_stock_summary(),
    }


def list_parent_options():
    return {
        "success": True,
        "options": get_parent_options()
    }


def list_active_pigs():
    pigs = get_active_pigs()
    return {
        "count": len(pigs),
        "pigs": pigs
    }


def list_sales_availability():
    pigs = get_sales_availability()
    return {
        "count": len(pigs),
        "pigs": pigs
    }


def get_family_tree_profile(pig_id: str):
    tree = get_family_tree(pig_id)

    if not tree:
        return {
            "success": False,
            "error": "Family tree not found."
        }, 404

    return {
        "success": True,
        "tree": tree
    }, 200


def get_litter_profile(litter_id: str):
    litter = get_litter_detail(litter_id)

    if not litter:
        return {
            "success": False,
            "error": "Litter not found."
        }, 404

    return {
        "success": True,
        "litter": litter
    }, 200


def list_products():
    products = get_products()
    return {
        "count": len(products),
        "products": products
    }


def list_pens():
    pens = get_pens()
    return {
        "count": len(pens),
        "pens": pens
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


def get_pig_treatment_history(pig_id: str):
    history = get_treatment_history_for_pig(pig_id)
    return {
        "success": True,
        "pig_id": history["pig_id"],
        "tag_number": history["tag_number"],
        "count": history["count"],
        "history": history["history"],
    }, 200


def get_pig_movement_history(pig_id: str):
    history = get_movement_history_for_pig(pig_id)
    return {
        "success": True,
        "pig_id": history["pig_id"],
        "tag_number": history["tag_number"],
        "current_pen_id": history["current_pen_id"],
        "count": history["count"],
        "history": history["history"],
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


def get_weights_by_date(weight_date: str):
    history = get_weight_entries_by_date(weight_date)
    return {
        "success": True,
        "weight_date": history["weight_date"],
        "count": history["count"],
        "history": history["history"],
    }, 200


def get_latest_weight(pig_id: str):
    return get_latest_weight_for_pig(pig_id)


def create_new_pig(payload: dict):
    validation = validate_new_pig_payload(payload)
    if not validation["is_valid"]:
        return {"success": False, "errors": validation["errors"]}, 400
    result = save_new_pig(validation["cleaned_data"])
    return result, 201


def create_new_product(payload: dict):
    validation = validate_new_product_payload(payload)
    if not validation["is_valid"]:
        return {"success": False, "errors": validation["errors"]}, 400
    result = save_new_product(validation["cleaned_data"])
    return result, 201


def create_new_pen(payload: dict):
    validation = validate_new_pen_payload(payload)
    if not validation["is_valid"]:
        return {"success": False, "errors": validation["errors"]}, 400
    result = save_new_pen(validation["cleaned_data"])
    return result, 201


def create_new_litter(payload: dict):
    validation = validate_new_litter_payload(payload)
    if not validation["is_valid"]:
        return {"success": False, "errors": validation["errors"]}, 400
    result = save_new_litter(validation["cleaned_data"])
    return result, 201


def create_weight_entry(payload: dict):
    validation = validate_weight_payload(payload)

    if not validation["is_valid"]:
        return {
            "success": False,
            "errors": validation["errors"]
        }, 400

    result = save_weight_entry(validation["cleaned_data"])
    return result, 201


def create_weight_entry_with_optional_move(payload: dict):
    validation = validate_weight_with_optional_move_payload(payload)

    if not validation["is_valid"]:
        return {
            "success": False,
            "errors": validation["errors"]
        }, 400

    result = save_weight_entry_with_optional_move(validation["cleaned_data"])
    return result, 201


def create_treatment_entry(payload: dict):
    validation = validate_treatment_payload(payload)

    if not validation["is_valid"]:
        return {
            "success": False,
            "errors": validation["errors"]
        }, 400

    result = save_treatment_entry(validation["cleaned_data"])
    return result, 201


def create_movement_entry(payload: dict):
    validation = validate_movement_payload(payload)

    if not validation["is_valid"]:
        return {
            "success": False,
            "errors": validation["errors"]
        }, 400

    result = save_movement_entry(validation["cleaned_data"])
    return result, 201