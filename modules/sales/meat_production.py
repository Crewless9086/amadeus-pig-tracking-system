import json
import os
import uuid
from collections import defaultdict
from datetime import date

from services.database_service import DATABASE_URL_ENV


BATCH_KINDS = {"Internal_Pilot", "Customer_Order", "Stock_Production"}
BATCH_STATUSES = {
    "Planned", "Selected", "Sent_To_Abattoir", "Carcass_Received",
    "At_Butcher", "Cutting", "Packed", "Completed", "Cancelled",
}
DISPOSITIONS = {"Internal_Use", "Customer_Sale", "Stock"}
EVENT_TYPES = {
    "batch_created", "pig_selected", "departed_farm", "arrived_abattoir",
    "slaughtered", "carcass_weighed", "delivered_to_butcher",
    "cutting_started", "packed", "completed", "note",
}
COST_TYPES = {
    "Pig_Production", "Transport", "Abattoir", "Butchery",
    "Packaging", "Cold_Storage", "Labour", "Other",
}
OUTPUT_TYPES = {"Cut", "Offal", "Bone", "Fat", "Head", "Waste", "Other"}
OUTPUT_DISPOSITIONS = {"Internal_Use", "Frozen", "Sample", "Sold", "Waste", "Other"}

EVENT_STATUS = {
    "pig_selected": "Selected",
    "departed_farm": "Sent_To_Abattoir",
    "arrived_abattoir": "Sent_To_Abattoir",
    "slaughtered": "Carcass_Received",
    "carcass_weighed": "Carcass_Received",
    "delivered_to_butcher": "At_Butcher",
    "cutting_started": "Cutting",
    "packed": "Packed",
    "completed": "Completed",
}


def list_meat_processing_batches(database_url=None):
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable(), 503
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(database_url, connect_timeout=10, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select b.*,
                           coalesce((select json_agg(bp.pig_id order by bp.pig_id) from public.meat_processing_batch_pigs bp where bp.batch_id = b.batch_id), '[]'::json) as pig_ids,
                           coalesce((select count(*) from public.meat_processing_batch_pigs bp where bp.batch_id = b.batch_id), 0) as pig_count,
                           coalesce((select sum(bp.live_weight_kg) from public.meat_processing_batch_pigs bp where bp.batch_id = b.batch_id), 0) as live_weight_kg,
                           coalesce((select sum(bp.carcass_weight_kg) from public.meat_processing_batch_pigs bp where bp.batch_id = b.batch_id), 0) as carcass_weight_kg,
                           coalesce((select sum(c.amount) from public.meat_processing_batch_costs c where c.batch_id = b.batch_id), 0) as total_cost,
                           coalesce((select sum(o.weight_kg) from public.meat_processing_batch_outputs o where o.batch_id = b.batch_id and o.counts_toward_packed_yield), 0) as packed_weight_kg
                    from public.meat_processing_batches b
                    order by b.updated_at desc, b.created_at desc
                    """
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return _failed("meat_processing_batch_list_failed", exc), 503
    return {
        "success": True,
        "status": "ok",
        "batches": [_json_safe(row) for row in rows],
        "count": len(rows),
        **_authority(False),
    }, 200


def get_meat_processing_batch(batch_id, database_url=None):
    batch_id = _clean(batch_id, 100)
    if not batch_id:
        return _validation("batch_id_required"), 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable(), 503
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(database_url, connect_timeout=10, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select * from public.meat_processing_batches where batch_id = %s", (batch_id,))
                batch = cursor.fetchone()
                if not batch:
                    return _validation("batch_not_found"), 404
                cursor.execute(
                    "select * from public.meat_processing_batch_pigs where batch_id = %s order by tag_number, pig_id",
                    (batch_id,),
                )
                pigs = cursor.fetchall()
                cursor.execute(
                    "select * from public.meat_processing_batch_events where batch_id = %s order by event_date, created_at",
                    (batch_id,),
                )
                events = cursor.fetchall()
                cursor.execute(
                    "select * from public.meat_processing_batch_costs where batch_id = %s order by cost_date, created_at",
                    (batch_id,),
                )
                costs = cursor.fetchall()
                cursor.execute(
                    "select * from public.meat_processing_batch_outputs where batch_id = %s order by created_at, cut_name",
                    (batch_id,),
                )
                outputs = cursor.fetchall()
    except Exception as exc:
        return _failed("meat_processing_batch_read_failed", exc), 503
    metrics = calculate_batch_metrics(pigs, costs, outputs)
    return {
        "success": True,
        "status": "ok",
        "batch": _json_safe(batch),
        "pigs": [_json_safe(row) for row in pigs],
        "events": [_json_safe(row) for row in events],
        "costs": [_json_safe(row) for row in costs],
        "outputs": [_json_safe(row) for row in outputs],
        "metrics": metrics,
        "next_capture": _next_capture(batch, costs, outputs),
        **_authority(False),
    }, 200


def create_meat_processing_batch(payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    batch_code = _clean(payload.get("batch_code"), 100)
    batch_kind = _clean(payload.get("batch_kind") or "Internal_Pilot", 40)
    status = _clean(payload.get("status") or "Planned", 40)
    disposition = _clean(payload.get("intended_disposition") or "Internal_Use", 40)
    created_by = _clean(payload.get("created_by"), 100)
    pigs = payload.get("pigs") if isinstance(payload.get("pigs"), list) else []
    if not batch_code or not created_by or not pigs:
        return _validation("batch_code_created_by_and_pigs_required"), 400
    if batch_kind not in BATCH_KINDS or status not in BATCH_STATUSES or disposition not in DISPOSITIONS:
        return _validation("invalid_batch_classification"), 400
    clean_pigs = []
    seen = set()
    for item in pigs:
        item = item if isinstance(item, dict) else {}
        pig_id = _clean(item.get("pig_id"), 100)
        if not pig_id or pig_id in seen:
            return _validation("pig_id_required_and_unique"), 400
        seen.add(pig_id)
        clean_pigs.append({
            "pig_id": pig_id,
            "tag_number": _clean(item.get("tag_number"), 100),
            "live_weight_kg": _positive_number(item.get("live_weight_kg"), allow_zero=False),
            "carcass_weight_kg": _positive_number(item.get("carcass_weight_kg"), allow_zero=False),
            "head_included": bool(item.get("head_included")),
            "notes": _clean(item.get("notes"), 1000),
        })
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable(), 503
    batch_id = _id("MEATBATCH")
    event_date = _date(payload.get("event_date") or payload.get("slaughter_date"))
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                pig_ids = [item["pig_id"] for item in clean_pigs]
                cursor.execute("select pig_id, tag_number from public.pig_current_state where pig_id = any(%s)", (pig_ids,))
                canonical = {row[0]: row[1] for row in cursor.fetchall()}
                missing = [pig_id for pig_id in pig_ids if pig_id not in canonical]
                if missing:
                    return {**_validation("canonical_pig_not_found"), "pig_ids": missing}, 404
                cursor.execute(
                    """
                    select distinct bp.pig_id, b.batch_code
                    from public.meat_processing_batch_pigs bp
                    join public.meat_processing_batches b on b.batch_id = bp.batch_id
                    where bp.pig_id = any(%s) and b.status <> 'Cancelled'
                    """,
                    (pig_ids,),
                )
                duplicates = cursor.fetchall()
                if duplicates:
                    return {
                        **_validation("pig_already_in_meat_batch"),
                        "duplicates": [{"pig_id": row[0], "batch_code": row[1]} for row in duplicates],
                    }, 409
                cursor.execute(
                    """
                    insert into public.meat_processing_batches (
                        batch_id, batch_code, batch_kind, status, intended_disposition,
                        abattoir_name, butcher_name, slaughter_date, butcher_date,
                        notes, created_by
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        batch_id, batch_code, batch_kind, status, disposition,
                        _clean(payload.get("abattoir_name"), 160),
                        _clean(payload.get("butcher_name"), 160),
                        _date(payload.get("slaughter_date")),
                        _date(payload.get("butcher_date")),
                        _clean(payload.get("notes"), 3000), created_by,
                    ),
                )
                for item in clean_pigs:
                    tag_number = item["tag_number"] or canonical[item["pig_id"]] or ""
                    cursor.execute(
                        """
                        insert into public.meat_processing_batch_pigs (
                            batch_pig_id, batch_id, pig_id, tag_number, live_weight_kg,
                            carcass_weight_kg, head_included, notes
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            _id("MEATBATCHPIG"), batch_id, item["pig_id"], tag_number,
                            item["live_weight_kg"], item["carcass_weight_kg"],
                            item["head_included"], item["notes"],
                        ),
                    )
                _insert_event(cursor, batch_id, {
                    "event_type": "batch_created",
                    "event_date": event_date,
                    "location_label": _clean(payload.get("abattoir_name"), 160),
                    "notes": "Meat production batch created.",
                    "recorded_by": created_by,
                    "metadata": {"batch_kind": batch_kind, "intended_disposition": disposition},
                })
    except Exception as exc:
        return _failed("meat_processing_batch_create_failed", exc), 503
    result, _ = get_meat_processing_batch(batch_id, database_url=database_url)
    result.update(_authority(True))
    return result, 201


def record_meat_processing_event(batch_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean(payload.get("event_type"), 60)
    event_date = _date(payload.get("event_date"))
    recorded_by = _clean(payload.get("recorded_by"), 100)
    if event_type not in EVENT_TYPES or not event_date or not recorded_by:
        return _validation("valid_event_type_date_and_recorded_by_required"), 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable(), 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status from public.meat_processing_batches where batch_id = %s for update", (batch_id,))
                row = cursor.fetchone()
                if not row:
                    return _validation("batch_not_found"), 404
                pig_id = _clean(payload.get("pig_id"), 100)
                live_weight = _positive_number(payload.get("live_weight_kg"), allow_zero=False)
                carcass_weight = _positive_number(payload.get("carcass_weight_kg"), allow_zero=False)
                if live_weight is not None or carcass_weight is not None:
                    if not pig_id:
                        return _validation("pig_id_required_for_weight_update"), 400
                    cursor.execute(
                        """
                        update public.meat_processing_batch_pigs
                        set live_weight_kg = coalesce(%s, live_weight_kg),
                            carcass_weight_kg = coalesce(%s, carcass_weight_kg),
                            head_included = coalesce(%s, head_included), updated_at = now()
                        where batch_id = %s and pig_id = %s
                        """,
                        (
                            live_weight, carcass_weight,
                            bool(payload.get("head_included")) if "head_included" in payload else None,
                            batch_id, pig_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        return _validation("batch_pig_not_found"), 404
                _insert_event(cursor, batch_id, {
                    **payload,
                    "event_type": event_type,
                    "event_date": event_date,
                    "recorded_by": recorded_by,
                    "metadata": {
                        "live_weight_kg": live_weight,
                        "carcass_weight_kg": carcass_weight,
                        "head_included": payload.get("head_included"),
                    },
                })
                assignments = ["updated_at = now()"]
                params = {"batch_id": batch_id}
                if EVENT_STATUS.get(event_type):
                    assignments.append("status = %(status)s")
                    params["status"] = EVENT_STATUS[event_type]
                if event_type in {"slaughtered", "carcass_weighed"}:
                    assignments.append("slaughter_date = coalesce(slaughter_date, %(event_date)s)")
                    params["event_date"] = event_date
                if event_type in {"delivered_to_butcher", "cutting_started"}:
                    assignments.append("butcher_date = coalesce(butcher_date, %(event_date)s)")
                    params["event_date"] = event_date
                    butcher_name = _clean(payload.get("butcher_name") or payload.get("location_label"), 160)
                    if butcher_name:
                        assignments.append("butcher_name = coalesce(nullif(butcher_name, ''), %(butcher_name)s)")
                        params["butcher_name"] = butcher_name
                cursor.execute(
                    f"update public.meat_processing_batches set {', '.join(assignments)} where batch_id = %(batch_id)s",
                    params,
                )
    except Exception as exc:
        return _failed("meat_processing_event_write_failed", exc), 503
    result, _ = get_meat_processing_batch(batch_id, database_url=database_url)
    result.update(_authority(True))
    return result, 201


def record_meat_processing_cost(batch_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    cost_type = _clean(payload.get("cost_type"), 60)
    amount = _positive_number(payload.get("amount"), allow_zero=True)
    cost_date = _date(payload.get("cost_date"))
    recorded_by = _clean(payload.get("recorded_by"), 100)
    if cost_type not in COST_TYPES or amount is None or not cost_date or not recorded_by:
        return _validation("valid_cost_type_amount_date_and_recorded_by_required"), 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable(), 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1 from public.meat_processing_batches where batch_id = %s", (batch_id,))
                if not cursor.fetchone():
                    return _validation("batch_not_found"), 404
                cursor.execute(
                    """
                    insert into public.meat_processing_batch_costs (
                        cost_id, batch_id, cost_type, supplier_name, amount,
                        cost_date, notes, recorded_by
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        _id("MEATCOST"), batch_id, cost_type,
                        _clean(payload.get("supplier_name"), 160), amount, cost_date,
                        _clean(payload.get("notes"), 1000), recorded_by,
                    ),
                )
                cursor.execute("update public.meat_processing_batches set updated_at = now() where batch_id = %s", (batch_id,))
    except Exception as exc:
        return _failed("meat_processing_cost_write_failed", exc), 503
    result, _ = get_meat_processing_batch(batch_id, database_url=database_url)
    result.update(_authority(True))
    return result, 201


def record_meat_processing_output(batch_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    output_type = _clean(payload.get("output_type") or "Cut", 40)
    cut_name = _clean(payload.get("cut_name"), 160)
    weight_kg = _positive_number(payload.get("weight_kg"), allow_zero=False)
    disposition = _clean(payload.get("disposition") or "Internal_Use", 40)
    recorded_by = _clean(payload.get("recorded_by"), 100)
    pack_count = _whole_number(payload.get("pack_count"), default=0)
    if (
        output_type not in OUTPUT_TYPES or not cut_name or weight_kg is None
        or disposition not in OUTPUT_DISPOSITIONS or not recorded_by or pack_count is None
    ):
        return _validation("valid_output_details_required"), 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable(), 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1 from public.meat_processing_batches where batch_id = %s", (batch_id,))
                if not cursor.fetchone():
                    return _validation("batch_not_found"), 404
                cursor.execute(
                    """
                    insert into public.meat_processing_batch_outputs (
                        output_id, batch_id, output_type, cut_name, pack_count,
                        weight_kg, counts_toward_packed_yield, disposition, notes, recorded_by
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        _id("MEATOUTPUT"), batch_id, output_type, cut_name, pack_count,
                        weight_kg, bool(payload.get("counts_toward_packed_yield", True)), disposition,
                        _clean(payload.get("notes"), 1000), recorded_by,
                    ),
                )
                cursor.execute("update public.meat_processing_batches set updated_at = now() where batch_id = %s", (batch_id,))
    except Exception as exc:
        return _failed("meat_processing_output_write_failed", exc), 503
    result, _ = get_meat_processing_batch(batch_id, database_url=database_url)
    result.update(_authority(True))
    return result, 201


def calculate_batch_metrics(pigs, costs, outputs):
    outputs_recorded = bool(outputs)
    live_weight = sum(_number(row.get("live_weight_kg")) or 0 for row in pigs or [])
    carcass_weight = sum(_number(row.get("carcass_weight_kg")) or 0 for row in pigs or [])
    total_output = sum(_number(row.get("weight_kg")) or 0 for row in outputs or [])
    packed_weight = sum(
        _number(row.get("weight_kg")) or 0
        for row in outputs or []
        if row.get("counts_toward_packed_yield") is True
    )
    total_cost = sum(_number(row.get("amount")) or 0 for row in costs or [])
    cost_breakdown = defaultdict(float)
    for row in costs or []:
        cost_breakdown[str(row.get("cost_type") or "Other")] += _number(row.get("amount")) or 0
    return {
        "pig_count": len(pigs or []),
        "live_weight_kg": _round(live_weight, 3),
        "carcass_weight_kg": _round(carcass_weight, 3),
        "total_output_weight_kg": _round(total_output, 3),
        "packed_weight_kg": _round(packed_weight, 3),
        "dressing_yield_pct": _ratio(carcass_weight, live_weight),
        "packed_yield_live_pct": _ratio(packed_weight, live_weight) if outputs_recorded else None,
        "packed_yield_carcass_pct": _ratio(packed_weight, carcass_weight) if outputs_recorded else None,
        "total_cost": _round(total_cost, 2),
        "cost_per_carcass_kg": _per_kg(total_cost, carcass_weight),
        "cost_per_packed_kg": _per_kg(total_cost, packed_weight),
        "cost_breakdown": {key: _round(value, 2) for key, value in sorted(cost_breakdown.items())},
        "revenue": 0.0,
        "margin": _round(-total_cost, 2),
        "revenue_note": "Internal-use batches record no sales revenue.",
    }


def _next_capture(batch, costs, outputs):
    cost_types = {row.get("cost_type") for row in costs or []}
    missing = []
    if not batch.get("butcher_name"):
        missing.append("butcher_name")
    if "Butchery" not in cost_types:
        missing.append("butchery_cost")
    if "Transport" not in cost_types:
        missing.append("transport_cost")
    if not outputs:
        missing.append("cut_outputs")
    status = batch.get("status") or ""
    if status in {"At_Butcher", "Carcass_Received"}:
        action = "Record cutting start, butcher details, costs, and each finished cut weight."
    elif status == "Cutting":
        action = "Record each cut/pack output, then mark the batch packed."
    elif status == "Packed":
        action = "Review yields and costs, then mark the pilot completed."
    else:
        action = "Record the next verified production stage."
    return {"action": action, "missing": missing, "ready_to_complete": status == "Packed" and bool(outputs)}


def _insert_event(cursor, batch_id, payload):
    cursor.execute(
        """
        insert into public.meat_processing_batch_events (
            event_id, batch_id, pig_id, event_type, event_date,
            location_label, notes, metadata_json, recorded_by
        ) values (%s, %s, nullif(%s, ''), %s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            _id("MEATEVENT"), batch_id, _clean(payload.get("pig_id"), 100),
            payload["event_type"], payload["event_date"],
            _clean(payload.get("location_label"), 160),
            _clean(payload.get("notes"), 2000),
            json.dumps(payload.get("metadata") or {}, sort_keys=True),
            payload["recorded_by"],
        ),
    )


def _authority(writes):
    return {
        "records_meat_production": bool(writes),
        "creates_sale": False,
        "records_revenue": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "creates_order": False,
        "reserves_stock": False,
        "changes_pig_lifecycle": False,
        "posts_publicly": False,
    }


def _validation(status):
    return {"success": False, "status": status, **_authority(False)}


def _unavailable():
    return {"success": False, "configured": False, "status": "not_configured", **_authority(False)}


def _failed(status, exc):
    return {
        "success": False,
        "configured": True,
        "status": status,
        "error_type": exc.__class__.__name__,
        **_authority(False),
    }


def _db_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _clean(value, limit):
    return str(value or "").strip()[:limit]


def _date(value):
    text = str(value or "").strip()
    if not text:
        return date.today().isoformat()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_number(value, allow_zero):
    number = _number(value)
    if number is None or number < 0 or (number == 0 and not allow_zero):
        return None
    return round(number, 3)


def _whole_number(value, default=0):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return _round((numerator / denominator) * 100, 1)


def _per_kg(total, weight):
    if not weight:
        return None
    return _round(total / weight, 2)


def _round(value, places):
    return round(float(value or 0), places)


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value
