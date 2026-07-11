from modules.pig_weights.pig_weights_service import (
    get_dashboard_summary,
    get_litter_attention_summary,
    get_sales_stock_summary,
    get_sales_stock_totals,
    get_meat_ready_stock_summary,
    get_pig_allocation_readiness,
    get_herdmaster_pig_allocation_alerts,
    get_purpose_review_queue,
    apply_purpose_review_decisions,
    build_purpose_review_recheck,
    get_meat_planning_summary,
    get_parent_options,
    get_active_pigs,
    get_sales_availability,
    list_litter_overview,
    get_family_tree,
    get_litter_detail,
    reconcile_litter_birth_counts,
    reclassify_litter_dead_piglets_as_stillborn,
    process_litter_weaning_day,
    mark_litter_weaned,
    mark_pig_death_or_removal,
    mark_litter_piglets_dead,
    record_litter_newborn_health,
    record_litter_piglet_sex_counts,
    assign_litter_piglet_tag_numbers,
    get_pig_detail,
    get_products,
    get_pens,
    get_treatment_history_for_pig,
    get_movement_history_for_pig,
    get_weight_history_for_pig,
    get_weight_entries_by_date,
    get_weight_report,
    get_latest_weight_for_pig,
    preflight_bulk_weight_entries,
    save_new_pig,
    save_new_product,
    save_new_pen,
    save_new_litter,
    save_bulk_weight_entries,
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
        "summary": get_dashboard_summary(),
        "litter_attention": get_litter_attention_summary(),
    }


def get_sales_dashboard_data():
    return {
        "success": True,
        "totals": get_sales_stock_totals(),
        "summary": get_sales_stock_summary(),
        "meat_ready_stock": get_meat_ready_stock_summary(),
    }


def get_pig_allocation_readiness_data():
    return get_pig_allocation_readiness()


def get_pig_allocation_alerts_data():
    return get_herdmaster_pig_allocation_alerts()


def get_purpose_review_queue_data(litter_id: str = ""):
    return get_purpose_review_queue(litter_id=litter_id)


def apply_purpose_review_queue_decisions(payload: dict):
    payload = payload or {}
    return apply_purpose_review_decisions(
        decisions=payload.get("decisions", []),
        changed_by=payload.get("changed_by", "web_app"),
        dry_run=payload.get("dry_run", True) is True,
        allow_reclassify=payload.get("allow_reclassify", False) is True,
    )


def get_purpose_review_recheck_packet(payload: dict):
    payload = payload or {}
    return build_purpose_review_recheck(
        pig_id=payload.get("pig_id", ""),
        question=payload.get("question", ""),
    )


def get_meat_planning_data():
    return get_meat_planning_summary()


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


def list_litters():
    return list_litter_overview()


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


def mark_litter_profile_weaned(litter_id: str, payload: dict):
    payload = payload or {}
    return mark_litter_weaned(
        litter_id=litter_id,
        wean_date_value=payload.get("wean_date", ""),
        changed_by=payload.get("changed_by", "web_app"),
        use_latest_weights_as_wean_weights=payload.get("use_latest_weights_as_wean_weights", False) is True,
        wean_weights=payload.get("wean_weights", {}),
    )


def process_litter_profile_weaning_day(litter_id: str, payload: dict):
    return process_litter_weaning_day(litter_id, payload or {})


def record_litter_profile_newborn_health(litter_id: str, payload: dict):
    payload = payload or {}
    return record_litter_newborn_health(
        litter_id=litter_id,
        action_date_value=payload.get("action_date", ""),
        changed_by=payload.get("changed_by", "web_app"),
        earmarked=payload.get("earmarked", False) is True,
        antiparasitic_product_id=payload.get("antiparasitic_product_id", ""),
        deworming_product_id=payload.get("deworming_product_id", ""),
        vaccination_product_id=payload.get("vaccination_product_id", ""),
        dose=payload.get("dose", None),
        route=payload.get("route", ""),
        batch_lot_number=payload.get("batch_lot_number", ""),
        notes=payload.get("notes", ""),
        dry_run=payload.get("dry_run", True) is True,
    )


def mark_litter_profile_piglets_dead(litter_id: str, payload: dict):
    payload = payload or {}
    return mark_litter_piglets_dead(
        litter_id=litter_id,
        event_date_value=payload.get("event_date", ""),
        reason=payload.get("reason", ""),
        count=payload.get("count", None),
        male_count=payload.get("male_count", None),
        female_count=payload.get("female_count", None),
        pig_ids=payload.get("pig_ids", []),
        changed_by=payload.get("changed_by", "web_app"),
        notes=payload.get("notes", ""),
        dry_run=payload.get("dry_run", True) is True,
    )


def record_litter_profile_piglet_sex_counts(litter_id: str, payload: dict):
    payload = payload or {}
    return record_litter_piglet_sex_counts(
        litter_id=litter_id,
        action_date_value=payload.get("action_date", ""),
        male_count=payload.get("male_count", None),
        female_count=payload.get("female_count", None),
        changed_by=payload.get("changed_by", "web_app"),
        notes=payload.get("notes", ""),
        dry_run=payload.get("dry_run", True) is True,
    )


def assign_litter_profile_piglet_tag_numbers(litter_id: str, payload: dict):
    payload = payload or {}
    return assign_litter_piglet_tag_numbers(
        litter_id=litter_id,
        tag_numbers=payload.get("tag_numbers", []),
        assignments=payload.get("assignments", []),
        action_date_value=payload.get("action_date", None),
        changed_by=payload.get("changed_by", "web_app"),
        notes=payload.get("notes", ""),
        dry_run=payload.get("dry_run", True) is True,
    )


def reconcile_litter_profile_birth_counts(litter_id: str, payload: dict):
    payload = payload or {}
    return reconcile_litter_birth_counts(
        litter_id=litter_id,
        target_born_alive=payload.get("target_born_alive", None),
        changed_by=payload.get("changed_by", "web_app"),
        reason=payload.get("reason", ""),
        dry_run=payload.get("dry_run", True) is True,
    )


def reclassify_litter_profile_stillborn(litter_id: str, payload: dict):
    payload = payload or {}
    return reclassify_litter_dead_piglets_as_stillborn(
        litter_id=litter_id,
        pig_ids=payload.get("pig_ids", []),
        count=payload.get("count", None),
        changed_by=payload.get("changed_by", "web_app"),
        reason=payload.get("reason", ""),
        dry_run=payload.get("dry_run", True) is True,
    )


def mark_pig_lifecycle_death(pig_id: str, payload: dict):
    payload = payload or {}
    return mark_pig_death_or_removal(
        pig_id=pig_id,
        event_date_value=payload.get("event_date", ""),
        reason=payload.get("reason", ""),
        changed_by=payload.get("changed_by", "web_app"),
        notes=payload.get("notes", ""),
        dry_run=payload.get("dry_run", False) is True,
    )


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


def get_weight_report_data(date_from: str = "", date_to: str = "", pen_id: str = ""):
    try:
        return get_weight_report(date_from=date_from, date_to=date_to, pen_id=pen_id), 200
    except ValueError as exc:
        return {
            "success": False,
            "errors": [str(exc)],
        }, 400


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
    return result, 409 if result.get("duplicate_weight") else 201


def create_weight_entry_with_optional_move(payload: dict):
    validation = validate_weight_with_optional_move_payload(payload)

    if not validation["is_valid"]:
        return {
            "success": False,
            "errors": validation["errors"]
        }, 400

    result = save_weight_entry_with_optional_move(validation["cleaned_data"])
    return result, 409 if result.get("duplicate_weight") else 201


def preview_bulk_weight_entries(payload: dict):
    result, status_code = preflight_bulk_weight_entries(payload)
    return result, status_code


def create_bulk_weight_entries(payload: dict):
    result, status_code = save_bulk_weight_entries(payload)
    return result, status_code


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
