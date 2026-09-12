from flask import Blueprint, current_app, jsonify, request

from modules.auth.owner_access import (
    require_weaning_session, weaning_session_identity,
    require_treatment_session, treatment_session_identity,
    correction_batch_owner_admin_principal,
    require_correction_batch_owner_admin_access,
    require_owner_admin_access,
    require_strict_owner_admin_access,
    require_owner_read_access,
    owner_admin_principal,
    strict_owner_admin_principal,
    mortality_session_identity,
    require_mortality_session,
)
from modules.pig_weights.bulk_weight_batch_service import (
    get_bulk_weight_batch_status,
    process_bulk_weight_batch,
    retry_failed_bulk_weight_batch,
    stage_bulk_weight_batch,
)
from modules.pig_weights.bulk_body_condition_service import record_body_condition_batch
from modules.pig_weights.herdmaster_piglet_observation_action import (
    execute_action as execute_piglet_observations,
    preview_authoritative as preview_piglet_observations,
)

from modules.pig_weights.pig_weights_controller import (
    get_status,
    get_dashboard_data,
    get_sales_dashboard_data,
    get_pig_allocation_readiness_data,
    get_pig_allocation_alerts_data,
    get_riversdale_auction_recommendation_data,
    record_riversdale_auction_decision_data,
    record_riversdale_candidate_review_data,
    get_riversdale_auction_list_data,
    update_riversdale_auction_list_data,
    get_purpose_review_queue_data,
    apply_purpose_review_queue_decisions,
    create_purpose_correction_batch,
    approve_purpose_correction_batch,
    execute_purpose_correction_batch,
    get_purpose_review_recheck_packet,
    get_meat_planning_data,
    list_parent_options,
    list_active_pigs,
    list_sales_availability,
    list_litters,
    get_family_tree_profile,
    get_litter_profile,
    mark_litter_profile_weaned,
    process_litter_profile_weaning_day,
    record_litter_profile_newborn_health,
    skip_litter_profile_first_treatment,
    mark_litter_profile_piglets_dead,
    record_litter_profile_piglet_sex_counts,
    assign_litter_profile_piglet_tag_numbers,
    reconcile_litter_profile_birth_counts,
    reclassify_litter_profile_stillborn,
    mark_pig_lifecycle_death,
    list_products,
    list_pens,
    get_pig_profile,
    get_pig_treatment_history,
    get_pig_movement_history,
    get_pig_weight_history,
    get_weights_by_date,
    get_weight_report_data,
    get_latest_weight,
    create_new_pig,
    create_new_product,
    create_new_pen,
    create_new_litter,
    create_weight_entry,
    create_weight_entry_with_optional_move,
    create_bulk_weight_entries,
    preview_bulk_weight_entries,
    create_treatment_entry,
    create_movement_entry,
)

pig_weights_bp = Blueprint("pig_weights", __name__)


def _bulk_json_failure(error, status_code=500, payload=None, endpoint=""):
    rows = (payload or {}).get("rows", [])
    submitted_count = len(rows) if isinstance(rows, list) else 0
    safe_error = str(error) if error else "Bulk upload failed."
    return jsonify({
        "ok": False,
        "success": False,
        "error": "bulk_upload_exception",
        "status": "upload_failed",
        "endpoint": endpoint,
        "message": "Bulk weight upload failed before completion. Draft kept; no complete upload confirmation was returned.",
        "detail": safe_error[:240],
        "submitted_count": submitted_count,
        "visible_count": submitted_count,
        "expected_count": 0,
        "processed_count": 0,
        "success_count": 0,
        "saved_count": 0,
        "movement_count": 0,
        "movement_only_count": 0,
        "skipped_count": 0,
        "blocked_count": 0,
        "failed_count": submitted_count,
        "failed_rows": [],
        "row_results": [],
        "retry_safe": True,
        "writes_to_google_sheets": False,
        "writes_to_supabase": False,
    }), status_code


@pig_weights_bp.route("/status", methods=["GET"])
def status():
    return jsonify(get_status())


@pig_weights_bp.route("/dashboard", methods=["GET"])
def dashboard():
    return jsonify(get_dashboard_data())


@pig_weights_bp.route("/sales-dashboard", methods=["GET"])
def sales_dashboard():
    return jsonify(get_sales_dashboard_data())


@pig_weights_bp.route("/pig-allocation-readiness", methods=["GET"])
def pig_allocation_readiness():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify(get_pig_allocation_readiness_data())


@pig_weights_bp.route("/pig-allocation-alerts", methods=["GET"])
def pig_allocation_alerts():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify(get_pig_allocation_alerts_data())


@pig_weights_bp.route("/riversdale-auction-recommendation", methods=["GET"])
def riversdale_auction_recommendation():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify(get_riversdale_auction_recommendation_data())


@pig_weights_bp.route("/riversdale-auction-confirmation", methods=["POST"])
def riversdale_auction_confirmation():
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_riversdale_auction_decision_data(
        request.get_json(silent=True) or {}, actor_id=owner_admin_principal()
    )
    return jsonify(result), status_code


@pig_weights_bp.route("/riversdale-auction-candidate-reviews", methods=["POST"])
def riversdale_auction_candidate_review():
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_riversdale_candidate_review_data(
        request.get_json(silent=True) or {}, actor_id=owner_admin_principal()
    )
    return jsonify(result), status_code


@pig_weights_bp.route("/riversdale-auction-list", methods=["GET"])
def riversdale_auction_list():
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status_code = get_riversdale_auction_list_data()
    return jsonify(result), status_code


@pig_weights_bp.route("/riversdale-auction-list/events", methods=["POST"])
def riversdale_auction_list_events():
    denied = require_owner_admin_access()
    if denied:
        return denied
    result, status_code = update_riversdale_auction_list_data(
        request.get_json(silent=True) or {}, actor_id=owner_admin_principal()
    )
    return jsonify(result), status_code


@pig_weights_bp.route("/purpose-review", methods=["GET"])
def purpose_review_queue():
    return jsonify(get_purpose_review_queue_data(litter_id=request.args.get("litter_id", "")))


@pig_weights_bp.route("/purpose-review/apply", methods=["POST"])
def purpose_review_apply():
    denied = require_correction_batch_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = apply_purpose_review_queue_decisions(
        payload, actor_id=correction_batch_owner_admin_principal())
    return jsonify(result), status_code


@pig_weights_bp.route("/purpose-review/correction-batches", methods=["POST"])
def purpose_review_correction_batch_create():
    denied = require_correction_batch_owner_admin_access()
    if denied:
        return denied
    result, status_code = create_purpose_correction_batch(
        request.get_json(silent=True) or {}, actor_id=correction_batch_owner_admin_principal()
    )
    return jsonify(result), status_code


@pig_weights_bp.route("/purpose-review/correction-batches/<batch_id>/approve", methods=["POST"])
def purpose_review_correction_batch_approve(batch_id):
    denied = require_correction_batch_owner_admin_access()
    if denied:
        return denied
    result, status_code = approve_purpose_correction_batch(batch_id, actor_id=correction_batch_owner_admin_principal())
    return jsonify(result), status_code


@pig_weights_bp.route("/purpose-review/correction-batches/<batch_id>/execute", methods=["POST"])
def purpose_review_correction_batch_execute(batch_id):
    denied = require_correction_batch_owner_admin_access()
    if denied:
        return denied
    result, status_code = execute_purpose_correction_batch(batch_id, actor_id=correction_batch_owner_admin_principal())
    return jsonify(result), status_code


@pig_weights_bp.route("/purpose-review/recheck", methods=["POST"])
def purpose_review_recheck():
    payload = request.get_json(silent=True) or {}
    result, status_code = get_purpose_review_recheck_packet(payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/meat-planning", methods=["GET"])
def meat_planning():
    return jsonify(get_meat_planning_data())


@pig_weights_bp.route("/parent-options", methods=["GET"])
def parent_options():
    return jsonify(list_parent_options())


@pig_weights_bp.route("/pigs", methods=["GET"])
def pigs():
    return jsonify(list_active_pigs())


@pig_weights_bp.route("/sales-availability", methods=["GET"])
def sales_availability():
    denied = require_owner_read_access()
    if denied:
        return denied
    return jsonify(list_sales_availability())


@pig_weights_bp.route("/litters", methods=["GET"])
def litters():
    return jsonify(list_litters())


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


@pig_weights_bp.route("/pig/<pig_id>/lifecycle/death", methods=["GET", "POST"])
def pig_lifecycle_death(pig_id):
    payload = request.get_json(silent=True) or {}
    # Preserve the existing non-mortality removal journey under its admin guard.
    if request.method == "POST" and payload.get("reason") in {"Culled", "Lost", "Removed", "Other"}:
        denied = require_owner_admin_access()
        if denied:
            return denied
        payload = {**payload, "changed_by": owner_admin_principal()}
        result, status_code = mark_pig_lifecycle_death(pig_id, payload)
        return jsonify(result), status_code
    identity = mortality_session_identity()
    if not identity:
        return jsonify(success=False, status="authenticated_mortality_permission_required"), 403
    denied = require_mortality_session() if request.method == "POST" else None
    if denied:
        return denied
    from modules.oom_sakkie.herdmaster_health_loss_runtime import handle_application_mortality
    try:
        result, status_code = handle_application_mortality(pig_id, payload, identity,
            resume=request.method == "GET")
    except Exception:
        return jsonify(success=False, status="mortality_service_unavailable"), 503
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/family-tree", methods=["GET"])
def family_tree(pig_id):
    result, status_code = get_family_tree_profile(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/pig/<pig_id>/weights", methods=["GET"])
def pig_weights(pig_id):
    result, status_code = get_pig_weight_history(pig_id)
    return jsonify(result), status_code


@pig_weights_bp.route("/weights-by-date", methods=["GET"])
def weights_by_date():
    weight_date = request.args.get("weight_date", "")
    result, status_code = get_weights_by_date(weight_date)
    return jsonify(result), status_code


@pig_weights_bp.route("/weight-report", methods=["GET"])
def weight_report():
    result, status_code = get_weight_report_data(
        date_from=request.args.get("date_from", ""),
        date_to=request.args.get("date_to", ""),
        pen_id=request.args.get("pen_id", ""),
        batch_id=request.args.get("batch_id", ""),
    )
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


@pig_weights_bp.route("/litter/<litter_id>/mark-weaned", methods=["POST"])
def mark_litter_weaned_route(litter_id):
    return litter_weaning_day_route(litter_id)


@pig_weights_bp.route("/litter/<litter_id>/weaning-day", methods=["POST"])
def litter_weaning_day_route(litter_id):
    denied = require_weaning_session()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, status="weaning_request_invalid"), 400
    payload = dict(payload)
    if request.path.endswith("/mark-weaned"):
        if payload.pop("use_latest_weights_as_wean_weights", False):
            return jsonify(success=False, status="explicit_weaning_weights_required",
                operation_committed=False, errors=["Supply actual weights; historical weights are not copied."]), 409
        weights = payload.pop("wean_weights", None)
        if weights is not None:
            if not isinstance(weights, dict) or "assignments" in payload:
                return jsonify(success=False, status="weaning_request_invalid", operation_committed=False), 400
            payload["assignments"] = [{"pig_id": key, "wean_weight_kg": value} for key, value in weights.items()]
    # Audit identity is always derived from the authenticated server session.
    # A browser-supplied changed_by value has no authority.
    payload["changed_by"] = weaning_session_identity()["actor_id"]
    try:
        result, status_code = process_litter_profile_weaning_day(litter_id, payload)
        return jsonify(result), status_code
    except Exception as exc:
        current_app.logger.exception("Weaning day workflow failed for litter %s", litter_id)
        return jsonify({
            "success": False,
            "status": "weaning_day_unexpected_failure",
            "errors": [
                "The Weaning Day request could not be completed. Reload the "
                "litter to verify its current state before any retry."
            ],
            "error_type": type(exc).__name__,
            "litter_id": litter_id,
            "operation_committed": None,
            "operation_state": "unknown_verify_before_retry",
            "writes_to_sheets": None,
            "writes_to_supabase": None,
        }), 500


@pig_weights_bp.route("/litter/<litter_id>/piglet-observations", methods=["POST"])
def litter_piglet_observations_route(litter_id):
    denied = require_owner_admin_access()
    if not denied:
        denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = dict(request.get_json(silent=True) or {})
    payload["litter_id"] = litter_id
    actor_id = owner_admin_principal() or strict_owner_admin_principal()
    if payload.get("dry_run", True) is True:
        result, status = preview_piglet_observations(payload, actor_id=actor_id, channel="application")
    else:
        result, status = execute_piglet_observations(
            payload, actor_id=actor_id, channel="application",
            confirmation_binding=payload.get("confirmation_binding"),
        )
    return jsonify(result), status


@pig_weights_bp.route("/litter/<litter_id>/newborn-health", methods=["POST"])
def litter_newborn_health_route(litter_id):
    denied = require_treatment_session()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, status="first_treatment_request_invalid"), 400
    payload["changed_by"] = treatment_session_identity()["actor_id"]
    result, status_code = record_litter_profile_newborn_health(litter_id, payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/litter/<litter_id>/first-treatment/skip", methods=["POST"])
def litter_first_treatment_skip_route(litter_id):
    denied = require_treatment_session()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("confirmed") is not True:
        return jsonify(success=False, status="explicit_treatment_skip_confirmation_required"), 409
    payload["changed_by"] = treatment_session_identity()["actor_id"]
    result, status_code = skip_litter_profile_first_treatment(litter_id, payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/litter/<litter_id>/piglet-deaths", methods=["POST"])
def litter_piglet_deaths_route(litter_id):
    denied = require_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result, status_code = mark_litter_profile_piglets_dead(litter_id, payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/litter/<litter_id>/sex-counts", methods=["POST"])
def litter_sex_counts_route(litter_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = record_litter_profile_piglet_sex_counts(litter_id, payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/litter/<litter_id>/tag-numbers", methods=["POST"])
def litter_tag_numbers_route(litter_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = assign_litter_profile_piglet_tag_numbers(litter_id, payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/litter/<litter_id>/reconcile-birth-counts", methods=["POST"])
def litter_reconcile_birth_counts_route(litter_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = reconcile_litter_profile_birth_counts(litter_id, payload)
    return jsonify(result), status_code


@pig_weights_bp.route("/litter/<litter_id>/reclassify-stillborn", methods=["POST"])
def litter_reclassify_stillborn_route(litter_id):
    payload = request.get_json(silent=True) or {}
    result, status_code = reclassify_litter_profile_stillborn(litter_id, payload)
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


@pig_weights_bp.route("/weights-with-optional-move", methods=["POST"])
def add_weight_with_optional_move():
    payload = request.get_json(silent=True) or {}
    result, status_code = create_weight_entry_with_optional_move(payload)
    return jsonify(result), status_code



@pig_weights_bp.route("/bulk-batches", methods=["POST"])
def stage_weights_batch():
    payload = request.get_json(silent=True) or {}
    try:
        result, status_code = stage_bulk_weight_batch(payload)
        return jsonify(result), status_code
    except Exception as exc:
        return _bulk_json_failure(exc, status_code=500, payload=payload, endpoint="/api/pig-weights/bulk-batches")


@pig_weights_bp.route("/bulk-body-condition", methods=["POST"])
def add_bulk_body_condition():
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    result, status_code = record_body_condition_batch(
        request.get_json(silent=True) or {},
        actor_id=strict_owner_admin_principal(),
    )
    return jsonify(result), status_code


@pig_weights_bp.route("/bulk-batches/<batch_id>", methods=["GET"])
def bulk_batch_status(batch_id):
    try:
        result, status_code = get_bulk_weight_batch_status(batch_id)
        return jsonify(result), status_code
    except Exception as exc:
        return _bulk_json_failure(exc, status_code=500, payload={}, endpoint=f"/api/pig-weights/bulk-batches/{batch_id}")


@pig_weights_bp.route("/bulk-batches/<batch_id>/process", methods=["POST"])
def bulk_batch_process(batch_id):
    payload = request.get_json(silent=True) or {}
    try:
        result, status_code = process_bulk_weight_batch(batch_id, chunk_size=payload.get("chunk_size", 3))
        return jsonify(result), status_code
    except Exception as exc:
        return _bulk_json_failure(exc, status_code=500, payload=payload, endpoint=f"/api/pig-weights/bulk-batches/{batch_id}/process")


@pig_weights_bp.route("/bulk-batches/<batch_id>/retry-failed", methods=["POST"])
def bulk_batch_retry_failed(batch_id):
    payload = request.get_json(silent=True) or {}
    try:
        result, status_code = retry_failed_bulk_weight_batch(batch_id, chunk_size=payload.get("chunk_size", 3))
        return jsonify(result), status_code
    except Exception as exc:
        return _bulk_json_failure(exc, status_code=500, payload=payload, endpoint=f"/api/pig-weights/bulk-batches/{batch_id}/retry-failed")

@pig_weights_bp.route("/weights-batch/preflight", methods=["POST"])
def preflight_weights_batch():
    payload = request.get_json(silent=True) or {}
    try:
        result, status_code = preview_bulk_weight_entries(payload)
        return jsonify(result), status_code
    except Exception as exc:
        return _bulk_json_failure(exc, status_code=500, payload=payload, endpoint="/api/pig-weights/weights-batch/preflight")


@pig_weights_bp.route("/weights-batch", methods=["POST"])
def add_weights_batch():
    payload = request.get_json(silent=True) or {}
    try:
        result, status_code = create_bulk_weight_entries(payload)
        return jsonify(result), status_code
    except Exception as exc:
        return _bulk_json_failure(exc, status_code=500, payload=payload, endpoint="/api/pig-weights/weights-batch")


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
