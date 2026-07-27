from datetime import datetime, timezone
from math import isfinite
from time import monotonic

from flask import Blueprint, current_app, jsonify, render_template, request

from modules.auth.owner_access import require_owner_read_access
from modules.pig_weights.herdmaster_breeding_attention_service import (
    build_bounded_family_evidence,
    build_breeding_attention,
)
from modules.pig_weights.farm_supabase_read_service import (
    build_breeding_analytics_from_evidence,
    get_breeding_attention_source_snapshot,
    project_mating_overview,
)
from modules.pig_weights.mating_service import (
    get_breeding_options,
    get_breeding_analytics,
    get_breeding_animal_detail,
    get_mating_overview,
    save_new_mating,
    assume_pregnant,
    mark_not_pregnant,
)
from modules.pig_weights.pig_weights_service import get_pig_allocation_readiness
from modules.pig_weights.mating_validation import (
    validate_new_mating_payload,
    validate_assume_pregnant_payload,
    validate_mark_not_pregnant_payload,
)

mating_bp = Blueprint("mating", __name__)
BREEDING_ATTENTION_READ_DEADLINE_SECONDS = 20


def _bounded_read_connection(database_url):
    import psycopg
    return psycopg.connect(
        database_url,
        connect_timeout=3,
        options="-c default_transaction_read_only=on -c statement_timeout=3000",
    )


def _deadline_read(started, reader, *args, **kwargs):
    if monotonic() - started >= BREEDING_ATTENTION_READ_DEADLINE_SECONDS:
        raise TimeoutError("breeding attention read deadline exhausted")
    result = reader(*args, **kwargs)
    if monotonic() - started > BREEDING_ATTENTION_READ_DEADLINE_SECONDS:
        raise TimeoutError("breeding attention read deadline exhausted")
    return result


def _project_breeding_observations(rows, now=None):
    now = now or datetime.now(timezone.utc)
    by_pig = {}
    seen = set()
    for row in rows:
        if isinstance(row, dict):
            raw_pig_id = row.get("pig_id")
            observed_at = row.get("observed_at")
            raw_category = row.get("observation_category")
            measurements = row.get("measurements_json")
        else:
            raw_pig_id, observed_at, raw_category, measurements, _event_id = row
        pig_id, category = str(raw_pig_id), str(raw_category)
        key = (pig_id, category)
        if key in seen:
            continue
        seen.add(key)
        measurements = measurements if isinstance(measurements, dict) else {}
        item = by_pig.setdefault(pig_id, {})
        age_seconds = (now - observed_at).total_seconds() if isinstance(observed_at, datetime) else float("inf")
        if category == "behaviour" and measurements.get("standing_heat_observed") is True and 0 <= age_seconds <= 172800:
            item["heat_state"] = "standing"
            item["heat_observed_at"] = observed_at.isoformat()
        score = measurements.get("body_condition_score")
        if (
            category == "body_condition"
            and not isinstance(score, bool)
            and isinstance(score, (int, float))
            and isfinite(score)
            and 1 <= score <= 5
            and 0 <= age_seconds <= 2592000
        ):
            item["body_condition_score"] = score
            item["body_condition_observed_at"] = observed_at.isoformat()
    return by_pig


def _snapshot_litter_overview(rows):
    litters = [{
        "litter_id": row.get("Litter_ID", ""),
        "sow_pig_id": row.get("Sow_Pig_ID", ""),
        "sow_tag_number": row.get("Sow_Tag_Number", ""),
        "boar_pig_id": row.get("Boar_Pig_ID", ""),
        "boar_tag_number": row.get("Boar_Tag_Number", ""),
        "farrowing_date": row.get("Farrowing_Date", ""),
        "wean_date": row.get("Wean_Date", ""),
        "born_alive": row.get("Born_Alive"),
        "weaned_count": row.get("Weaned_Count"),
        "litter_status": row.get("Litter_Status", ""),
    } for row in rows if isinstance(row, dict)]
    return {
        "success": True,
        "count": len(litters),
        "litters": litters,
        "source": "supabase_canonical",
    }


def _route_stage(progress, name, started, completed, row_count, deadline_started):
    progress.append({
        "stage": name,
        "connection_acquisition_seconds": 0.0,
        "sql_seconds": 0.0,
        "projection_seconds": round(completed - started, 4),
        "bounded_row_count": int(row_count),
        "state": "complete",
        "remaining_deadline_seconds": round(max(
            0.0,
            BREEDING_ATTENTION_READ_DEADLINE_SECONDS - (completed - deadline_started),
        ), 4),
    })


def _require_route_deadline(started):
    if monotonic() - started >= BREEDING_ATTENTION_READ_DEADLINE_SECONDS:
        raise TimeoutError("breeding attention absolute deadline exhausted")


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


@mating_bp.route("/breeding-analytics", methods=["GET"])
def breeding_analytics():
    return jsonify(get_breeding_analytics())


@mating_bp.route("/breeding-attention", methods=["GET"])
def breeding_attention():
    denied = require_owner_read_access()
    if denied:
        return denied
    try:
        started = monotonic()
        snapshot = get_breeding_attention_source_snapshot(
            connect_factory=_bounded_read_connection,
            deadline_seconds=BREEDING_ATTENTION_READ_DEADLINE_SECONDS,
            started_at=started,
        )
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("success") is not True
            or not isinstance(snapshot.get("read_progress"), dict)
            or snapshot["read_progress"].get("status") != "complete"
        ):
            raise RuntimeError("breeding attention snapshot is incomplete")
        route_progress = []
        stage_started = monotonic()
        inputs = snapshot["allocation_inputs"]
        readiness = get_pig_allocation_readiness(
            allow_sheet_fallback=False,
            canonical_inputs=inputs,
        )
        if readiness.get("success") is not True:
            raise RuntimeError("canonical readiness projection is unavailable")
        _route_stage(route_progress, "readiness_projection", stage_started, monotonic(), len(readiness.get("pigs", [])), started)
        _require_route_deadline(started)

        stage_started = monotonic()
        state_rows = [{
            "pig_id": row.get("Pig_ID", ""),
            "current_pen_id": row.get("Current_Pen_ID", ""),
            "current_pen_name": row.get("Current_Pen_Name", ""),
        } for row in inputs.get("overview_rows", [])]
        mating_rows = project_mating_overview(snapshot["mating_rows"], state_rows)
        litters = _snapshot_litter_overview(inputs.get("litter_rows", []))
        analytics = build_breeding_analytics_from_evidence(mating_rows, litters)
        _route_stage(route_progress, "breeding_projection", stage_started, monotonic(), len(mating_rows), started)
        _require_route_deadline(started)

        master_rows = inputs.get("pig_master_rows", [])
        observations = {
            "success": True,
            "by_pig": _project_breeding_observations(snapshot["observation_rows"]),
        }
        stage_started = monotonic()
        master = {str(row.get("Pig_ID") or ""): row for row in master_rows if isinstance(row, dict)}
        for row in readiness.get("pigs", []):
            source = master.get(str(row.get("pig_id") or ""), {})
            row["available_for_breeding"] = source.get("Available_For_Breeding")
        female_ids = [
            str(row.get("pig_id") or "")
            for row in readiness.get("pigs", [])
            if str(row.get("sex") or "").lower() == "female"
            and str(row.get("animal_type") or "").lower() in {"sow", "gilt"}
            and str(row.get("status") or "").lower() == "active"
            and str(row.get("on_farm") or "").lower() in {"yes", "true", "1"}
        ]
        family_evidence = build_bounded_family_evidence(master_rows, female_ids)
        _route_stage(route_progress, "family_expansion", stage_started, monotonic(), len(female_ids), started)
        _require_route_deadline(started)

        stage_started = monotonic()
        packet = build_breeding_attention(
            readiness,
            matings={"success": True, "records": mating_rows},
            analytics=analytics,
            litters=litters,
            family_trees=family_evidence,
            observations=observations,
        )
        packet["source_read_progress"] = {
            **snapshot["read_progress"],
            "route_stages": route_progress,
        }
        _route_stage(route_progress, "attention_projection", stage_started, monotonic(), len(packet.get("animals", [])), started)
        _require_route_deadline(started)

        serialized = current_app.json.dumps(packet)
        _require_route_deadline(started)
        return current_app.response_class(serialized, status=200, mimetype="application/json")
    except Exception:
        packet = build_breeding_attention(None)
        return jsonify(packet), 503


@mating_bp.route("/breeding-attention/view", methods=["GET"])
def breeding_attention_view():
    denied = require_owner_read_access()
    if denied:
        return denied
    return render_template("breeding-attention.html")

@mating_bp.route("/breeding-analytics/<pig_id>", methods=["GET"])
def breeding_animal_detail(pig_id):
    result, status_code = get_breeding_animal_detail(pig_id)
    return jsonify(result), status_code


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


@mating_bp.route("/master/matings/<mating_id>/mark-not-pregnant", methods=["POST"])
def mark_not_pregnant_route(mating_id):
    payload = request.get_json(silent=True) or {}
    validation = validate_mark_not_pregnant_payload(payload)

    if not validation["is_valid"]:
        return jsonify({
            "success": False,
            "errors": validation["errors"]
        }), 400

    try:
        result = mark_not_pregnant(
            mating_id=mating_id,
            target_pen_id=validation["cleaned_data"]["target_pen_id"],
            moved_by=validation["cleaned_data"]["moved_by"],
            dry_run=validation["cleaned_data"]["dry_run"],
        )
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({
            "success": False,
            "errors": [str(exc)]
        }), 400
