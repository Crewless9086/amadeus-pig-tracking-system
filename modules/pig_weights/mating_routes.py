import os
from datetime import datetime, timezone
from math import isfinite
from time import monotonic

from flask import Blueprint, current_app, jsonify, render_template, request

from modules.auth.owner_access import (
    require_owner_read_access,
    require_strict_owner_admin_access,
    strict_owner_admin_principal,
)
from modules.pig_weights.herdmaster_breeding_attention_service import (
    build_bounded_family_evidence,
    build_breeding_attention,
)
from modules.pig_weights.herdmaster_breeding_operating_loop import (
    build_breeding_operating_loop,
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
from modules.pig_weights.herdmaster_breeding_observation_service import (
    CONTRACT_VERSION as BREEDING_OBSERVATION_VERSION,
    list_observations,
    observation_event_id,
    preview_observation,
    record_observation,
    validate_observation,
)
from modules.pig_weights.herdmaster_breeding_exposure_recovery import (
    build_grouped_preview,
    execute_grouped_preview,
)
from services.database_service import DATABASE_URL_ENV
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


def _breeding_write_connection():
    import psycopg
    return psycopg.connect(os.environ[DATABASE_URL_ENV], connect_timeout=10)


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
    seen_heat = set()
    seen_body_condition = set()
    seen_recovery_hold = set()
    seen_near_farrowing = set()
    def chronological_key(row):
        if isinstance(row, dict):
            observed = row.get("observed_at")
            event_id = row.get("observation_event_id")
        else:
            observed = row[1] if len(row) > 1 else None
            event_id = row[4] if len(row) > 4 else ""
        instant = observed.timestamp() if isinstance(observed, datetime) else float("-inf")
        return instant, str(event_id or "")

    for row in sorted(list(rows), key=chronological_key, reverse=True):
        if isinstance(row, dict):
            raw_pig_id = row.get("pig_id")
            observed_at = row.get("observed_at")
            raw_category = row.get("observation_category")
            measurements = row.get("measurements_json")
            event_id = row.get("observation_event_id")
        else:
            raw_pig_id, observed_at, raw_category, measurements, event_id = row
        pig_id, category = str(raw_pig_id), str(raw_category)
        measurements = measurements if isinstance(measurements, dict) else {}
        age_seconds = (now - observed_at).total_seconds() if isinstance(observed_at, datetime) else float("inf")
        is_breeding_observation = (
            measurements.get("contract_version") == BREEDING_OBSERVATION_VERSION
        )
        if category == "other" and not is_breeding_observation:
            continue
        item = by_pig.setdefault(pig_id, {})
        if pig_id not in seen_recovery_hold:
            hold_action = str(measurements.get("recovery_hold_action") or "").strip().lower()
            if hold_action in {"active", "cleared"}:
                seen_recovery_hold.add(pig_id)
                item["recovery_hold"] = hold_action
                item["recovery_hold_observed_at"] = observed_at.isoformat()
                item["recovery_hold_observation_event_id"] = str(event_id or "")
        if pig_id not in seen_near_farrowing:
            farrowing = str(measurements.get("near_farrowing") or "").strip().lower()
            if farrowing in {"observed", "not_observed"}:
                seen_near_farrowing.add(pig_id)
                item["near_farrowing"] = farrowing
                item["near_farrowing_observed_at"] = observed_at.isoformat()
                item["near_farrowing_observation_event_id"] = str(event_id or "")
        if pig_id not in seen_heat:
            heat_value = (
                measurements.get("standing_heat")
                if is_breeding_observation
                else (
                    "observed"
                    if measurements.get("standing_heat_observed") is True
                    else "not_observed"
                    if measurements.get("standing_heat_observed") is False
                    else "not_recorded"
                )
            )
            if (category == "behaviour" or is_breeding_observation) and heat_value != "not_recorded":
                seen_heat.add(pig_id)
                if 0 <= age_seconds <= 172800:
                    item["heat_state"] = (
                        "standing" if heat_value == "observed" else heat_value
                    )
                    item["heat_observed_at"] = observed_at.isoformat()
                    item["heat_observation_event_id"] = str(event_id or "")
        score = measurements.get("body_condition_score")
        if (
            pig_id not in seen_body_condition
            and
            (category == "body_condition" or is_breeding_observation)
            and not isinstance(score, bool)
            and isinstance(score, (int, float))
            and isfinite(score)
            and 1 <= score <= 5
            and 0 <= age_seconds <= 2592000
        ):
            seen_body_condition.add(pig_id)
            item["body_condition_score"] = score
            item["body_condition_observed_at"] = observed_at.isoformat()
            item["body_condition_observation_event_id"] = str(event_id or "")
        if is_breeding_observation and 0 <= age_seconds <= 2592000:
            physical = item.setdefault("fresh_physical_facts", {})
            for key in (
                "visible_build", "feet_legs_movement", "visible_injury",
                "temperament", "suitability_concern",
            ):
                value = measurements.get(key)
                if (
                    key not in physical
                    and value not in (None, "", "not_recorded")
                ):
                    physical[key] = {
                        "value": value,
                        "observed_at": observed_at.isoformat(),
                        "observation_event_id": str(event_id or ""),
                    }
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


def _build_breeding_attention_packets(proposed_observation=None):
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
        breeding_ids = [
            str(row.get("pig_id") or "")
            for row in readiness.get("pigs", [])
            if (
                (
                    str(row.get("sex") or "").lower() == "female"
                    and str(row.get("animal_type") or "").lower()
                    in {"sow", "gilt"}
                )
                or str(row.get("sex") or "").lower() == "male"
            )
            and str(row.get("status") or "").lower() == "active"
            and str(row.get("on_farm") or "").lower() in {"yes", "true", "1"}
        ]
        family_evidence = build_bounded_family_evidence(master_rows, breeding_ids)
        _route_stage(route_progress, "family_expansion", stage_started, monotonic(), len(breeding_ids), started)
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
        packet["operating_loop"] = build_breeding_operating_loop(
            packet,
            readiness=readiness,
            matings=mating_rows,
            litters=litters["litters"],
            observations=snapshot["observation_rows"],
            projected_observations=observations["by_pig"],
            exposures=snapshot.get("exposure_rows", []),
            family_trees=family_evidence,
        )
        packet["source_read_progress"] = {
            **snapshot["read_progress"],
            "route_stages": route_progress,
        }
        _route_stage(route_progress, "attention_projection", stage_started, monotonic(), len(packet.get("animals", [])), started)
        _require_route_deadline(started)
        hypothetical = None
        if proposed_observation:
            proposed_rows = list(snapshot["observation_rows"])
            proposed_rows.append({
                "pig_id": proposed_observation["pig_id"],
                "observed_at": proposed_observation["observed_at"],
                "observation_category": "other",
                "measurements_json": proposed_observation["measurements"],
                "observation_event_id": observation_event_id(
                    proposed_observation["idempotency_key"]
                ),
            })
            hypothetical = build_breeding_attention(
                readiness,
                matings={"success": True, "records": mating_rows},
                analytics=analytics,
                litters=litters,
                family_trees=family_evidence,
                observations={
                    "success": True,
                    "by_pig": _project_breeding_observations(proposed_rows),
                },
            )
            _require_route_deadline(started)
        return packet, hypothetical, started


def load_current_breeding_operating_loop():
    """Return the current complete read-only HERDMASTER operating loop."""
    packet, _hypothetical, _started = _build_breeding_attention_packets()
    loop = packet.get("operating_loop") if isinstance(packet, dict) else None
    if not isinstance(loop, dict) or loop.get("success") is not True or loop.get("writes_performed") is not False:
        raise RuntimeError("herdmaster_operating_loop_incomplete")
    return loop


@mating_bp.route("/breeding-attention", methods=["GET"])
def breeding_attention():
    denied = require_owner_read_access()
    if denied:
        return denied
    try:
        packet, _hypothetical, started = _build_breeding_attention_packets()
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


@mating_bp.route("/breeding-attention/<pig_id>/observations", methods=["GET"])
def breeding_attention_observations(pig_id):
    denied = require_owner_read_access()
    if denied:
        return denied
    result, status = list_observations(pig_id)
    return jsonify(result), status


@mating_bp.route("/breeding-attention/<pig_id>/observations/preview", methods=["POST"])
def breeding_attention_observation_preview(pig_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    payload["pig_id"] = pig_id
    payload.pop("current_attention", None)
    clean, validation_error = validate_observation(payload)
    if validation_error:
        result, status = preview_observation(payload)
        return jsonify(result), status
    try:
        attention_packet, hypothetical_packet, _started = _build_breeding_attention_packets(
            proposed_observation=clean,
        )
    except Exception:
        return jsonify({
            "success": False,
            "status": "current_attention_evidence_unavailable",
            "advisory_only": True,
        }), 503
    authoritative_attention = next((
        row for row in attention_packet.get("animals", [])
        if isinstance(row, dict) and str(row.get("pig_id") or "") == pig_id
    ), None)
    hypothetical_attention = next((
        row for row in (hypothetical_packet or {}).get("animals", [])
        if isinstance(row, dict) and str(row.get("pig_id") or "") == pig_id
    ), None)
    result, status = preview_observation(
        payload,
        authoritative_attention=authoritative_attention,
        hypothetical_attention=hypothetical_attention,
    )
    return jsonify(result), status


@mating_bp.route("/breeding-attention/<pig_id>/observations", methods=["POST"])
def breeding_attention_observation_record(pig_id):
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    payload["pig_id"] = pig_id
    result, status = record_observation(
        payload, actor_id=strict_owner_admin_principal(),
    )
    return jsonify(result), status


@mating_bp.route("/breeding-attention/grouped-actions/preview", methods=["POST"])
def breeding_grouped_action_preview():
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    result = build_grouped_preview(
        payload, evidence_generation=str(payload.get("evidence_generation") or "")
    )
    return jsonify(result), 200 if result["success"] else 400


@mating_bp.route("/breeding-attention/exposures", methods=["GET"])
def breeding_exposure_list():
    denied = require_owner_read_access()
    if denied:
        return denied
    try:
        snapshot = get_breeding_attention_source_snapshot()
    except Exception:
        return jsonify({"success": False, "status": "breeding_exposure_evidence_unavailable"}), 503
    master = ((snapshot or {}).get("allocation_inputs") or {}).get("pig_master_rows") or []
    labels = {str(row.get("Pig_ID") or row.get("pig_id") or ""): str(
        row.get("Name") or row.get("Tag_Number") or row.get("tag_number") or
        row.get("Pig_ID") or row.get("pig_id") or "") for row in master}
    rows = list((snapshot or {}).get("exposure_rows") or ())
    removed = {str(row.get("exposure_identity") or "") for row in rows
               if row.get("event_kind") == "removed"}
    active = [{**row,
        "sow_label": labels.get(str(row.get("sow_pig_id") or ""), str(row.get("sow_pig_id") or "")),
        "boar_label": labels.get(str(row.get("boar_pig_id") or ""), str(row.get("boar_pig_id") or ""))}
        for row in rows if row.get("event_kind") == "started"
        and str(row.get("exposure_identity") or "") not in removed]
    return jsonify({"success": True, "records": active, "writes_performed": False}), 200


@mating_bp.route("/breeding-attention/grouped-actions/execute", methods=["POST"])
def breeding_grouped_action_execute():
    denied = require_strict_owner_admin_access()
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    preview = build_grouped_preview(
        payload, evidence_generation=str(payload.get("evidence_generation") or "")
    )
    result, status = execute_grouped_preview(
        preview,
        confirmed_preview_sha256=str(payload.get("confirmed_preview_sha256") or ""),
        actor_id=strict_owner_admin_principal(),
        connect_factory=_breeding_write_connection,
    )
    return jsonify(result), status

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
