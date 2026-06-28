from __future__ import annotations

import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV
from modules.pig_weights import pig_weights_service
from modules.pig_weights.pig_weights_service import (
    parse_sheet_date,
    save_movement_entry,
    save_weight_entry_with_optional_move,
    to_clean_string,
)

DEFAULT_CHUNK_SIZE = 10
BATCH_STATUSES = {"staged", "processing", "partial", "complete", "failed", "cancelled"}
ROW_STATUSES = {"staged", "skipped", "processing", "success", "failed", "duplicate", "blocked"}
_MEMORY_BATCHES = {}
_MEMORY_ROWS = {}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _new_id():
    return str(uuid.uuid4())


def _store_mode():
    return os.getenv("BULK_WEIGHT_BATCH_STORE", "").strip().lower()


def _database_url():
    return os.getenv(DATABASE_URL_ENV, "").strip()


def _connect():
    database_url = _database_url()
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured for durable bulk batches.")
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _jsonb(value):
    try:
        from psycopg.types.json import Jsonb
        return Jsonb(value)
    except Exception:
        import json
        return json.dumps(value or {})


def _safe_rows(payload):
    rows = (payload or {}).get("rows", [])
    return rows if isinstance(rows, list) else []


def _row_has_action(row):
    return bool(
        str((row or {}).get("weight_kg", "")).strip()
        or str((row or {}).get("moved_to_pen_id", "")).strip()
        or str((row or {}).get("condition_notes", "")).strip()
    )


def _counts_from_records(row_records):
    visible = len(row_records)
    actionable = len([row for row in row_records if row.get("status") != "skipped"])
    weight_rows = len([row for row in row_records if row.get("result_json", {}).get("has_weight")])
    movement_rows = len([row for row in row_records if row.get("result_json", {}).get("has_pen_change")])
    skipped = len([row for row in row_records if row.get("status") == "skipped"])
    success = len([row for row in row_records if row.get("status") == "success"])
    failed = len([row for row in row_records if row.get("status") == "failed"])
    duplicate = len([row for row in row_records if row.get("status") == "duplicate"])
    blocked = len([row for row in row_records if row.get("status") == "blocked"])
    staged = len([row for row in row_records if row.get("status") == "staged"])
    processing = len([row for row in row_records if row.get("status") == "processing"])
    return {
        "visible_row_count": visible,
        "actionable_row_count": actionable,
        "weight_row_count": weight_rows,
        "movement_row_count": movement_rows,
        "skipped_row_count": skipped,
        "success_count": success,
        "failed_count": failed,
        "duplicate_count": duplicate,
        "blocked_count": blocked,
        "staged_count": staged,
        "processing_count": processing,
        "remaining_count": staged + processing,
    }


def _batch_status_from_counts(counts):
    if counts["remaining_count"] > 0 and (counts["success_count"] or counts["failed_count"]):
        return "processing"
    if counts["remaining_count"] > 0:
        return "staged"
    if counts["failed_count"] > 0 and counts["success_count"] > 0:
        return "partial"
    if counts["failed_count"] > 0:
        return "failed"
    return "complete"


def _build_row_records(batch_id, payload, preflight):
    source_rows = _safe_rows(payload)
    by_index = {}
    for item in preflight.get("accepted_rows", []):
        by_index[item.get("row_index")] = ("staged", item.get("action_type", "weight"), item.get("reason", ""), item)
    for item in preflight.get("blocked_rows", []):
        by_index[item.get("row_index")] = ("blocked", "blocked", item.get("reason", "Blocked by preflight."), item)
    for item in preflight.get("skipped_rows", []):
        by_index[item.get("row_index")] = ("skipped", "skipped", item.get("reason", "Skipped by preflight."), item)

    records = []
    for index, original in enumerate(source_rows):
        status, action_type, reason, preflight_row = by_index.get(index, ("skipped", "skipped", "No action detected.", original if isinstance(original, dict) else {}))
        original = original if isinstance(original, dict) else {}
        row = preflight_row if isinstance(preflight_row, dict) else original
        weight_value = row.get("weight_kg") if row.get("weight_kg") is not None else original.get("weight_kg")
        to_pen_id = to_clean_string(row.get("moved_to_pen_id", original.get("moved_to_pen_id", "")))
        from_pen_id = to_clean_string(row.get("current_pen_id", original.get("current_pen_id", "")))
        has_weight = bool(str(weight_value if weight_value is not None else "").strip()) and action_type != "movement_only"
        has_pen_change = bool(to_pen_id and to_pen_id != from_pen_id)
        result_json = {
            "action_type": action_type,
            "has_weight": has_weight,
            "has_pen_change": has_pen_change,
            "preflight": row,
        }
        row_id = _new_id()
        records.append({
            "row_id": row_id,
            "batch_id": batch_id,
            "row_index": index,
            "pig_id": to_clean_string(row.get("pig_id", original.get("pig_id", ""))),
            "pig_name": to_clean_string(row.get("pig_name", original.get("pig_name", ""))),
            "tag_number": to_clean_string(row.get("tag_number", original.get("tag_number", ""))),
            "weight_kg": weight_value if has_weight else None,
            "from_pen_id": from_pen_id,
            "to_pen_id": to_pen_id,
            "movement_type": "pen_change" if has_pen_change else "",
            "status": status,
            "status_reason": reason,
            "processed_at": None,
            "result_json": result_json,
            "original_row_json": original,
            "idempotency_key": f"{batch_id}:{index}",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })
    return records


def _memory_stage(batch, rows):
    _MEMORY_BATCHES[batch["batch_id"]] = deepcopy(batch)
    _MEMORY_ROWS[batch["batch_id"]] = deepcopy(rows)


def _memory_get(batch_id):
    batch = deepcopy(_MEMORY_BATCHES.get(batch_id))
    rows = deepcopy(_MEMORY_ROWS.get(batch_id, []))
    if not batch:
        return None, []
    return batch, rows


def _memory_save(batch, rows):
    _MEMORY_BATCHES[batch["batch_id"]] = deepcopy(batch)
    _MEMORY_ROWS[batch["batch_id"]] = deepcopy(rows)


def _pg_stage(batch, rows):
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.bulk_weight_batches (
                    batch_id, client_draft_id, weight_date, status, visible_row_count, actionable_row_count,
                    weight_row_count, movement_row_count, skipped_row_count, success_count, failed_count,
                    duplicate_count, source, notes, error_summary, payload_summary_json
                ) values (%(batch_id)s::uuid, %(client_draft_id)s, %(weight_date)s, %(status)s, %(visible_row_count)s,
                    %(actionable_row_count)s, %(weight_row_count)s, %(movement_row_count)s, %(skipped_row_count)s,
                    %(success_count)s, %(failed_count)s, %(duplicate_count)s, %(source)s, %(notes)s,
                    %(error_summary)s, %(payload_summary_json)s::jsonb)
                """,
                {**batch, "payload_summary_json": _jsonb(batch.get("payload_summary_json", {}))},
            )
            for row in rows:
                cursor.execute(
                    """
                    insert into public.bulk_weight_batch_rows (
                        row_id, batch_id, row_index, pig_id, pig_name, weight_kg, from_pen_id, to_pen_id,
                        movement_type, status, status_reason, processed_at, result_json, original_row_json,
                        idempotency_key
                    ) values (%(row_id)s::uuid, %(batch_id)s::uuid, %(row_index)s, %(pig_id)s, %(pig_name)s,
                        %(weight_kg)s, %(from_pen_id)s, %(to_pen_id)s, %(movement_type)s, %(status)s,
                        %(status_reason)s, %(processed_at)s, %(result_json)s::jsonb, %(original_row_json)s::jsonb,
                        %(idempotency_key)s)
                    """,
                    {**row, "result_json": _jsonb(row.get("result_json", {})), "original_row_json": _jsonb(row.get("original_row_json", {}))},
                )


def _pg_get(batch_id):
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select batch_id::text, client_draft_id, weight_date::text, status, visible_row_count,
                    actionable_row_count, weight_row_count, movement_row_count, skipped_row_count, success_count,
                    failed_count, duplicate_count, source, notes, error_summary, payload_summary_json,
                    created_at::text, updated_at::text, completed_at::text
                from public.bulk_weight_batches where batch_id = %s::uuid
                """,
                (batch_id,),
            )
            item = cursor.fetchone()
            if not item:
                return None, []
            keys = ["batch_id", "client_draft_id", "weight_date", "status", "visible_row_count", "actionable_row_count", "weight_row_count", "movement_row_count", "skipped_row_count", "success_count", "failed_count", "duplicate_count", "source", "notes", "error_summary", "payload_summary_json", "created_at", "updated_at", "completed_at"]
            batch = dict(zip(keys, item))
            cursor.execute(
                """
                select row_id::text, batch_id::text, row_index, pig_id, pig_name, weight_kg, from_pen_id, to_pen_id,
                    movement_type, status, status_reason, processed_at::text, result_json, original_row_json,
                    idempotency_key, created_at::text, updated_at::text
                from public.bulk_weight_batch_rows where batch_id = %s::uuid order by row_index
                """,
                (batch_id,),
            )
            row_keys = ["row_id", "batch_id", "row_index", "pig_id", "pig_name", "weight_kg", "from_pen_id", "to_pen_id", "movement_type", "status", "status_reason", "processed_at", "result_json", "original_row_json", "idempotency_key", "created_at", "updated_at"]
            rows = [dict(zip(row_keys, row)) for row in cursor.fetchall()]
            return batch, rows


def _pg_save(batch, rows):
    counts = _counts_from_records(rows)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update public.bulk_weight_batches set status=%(status)s, visible_row_count=%(visible_row_count)s,
                    actionable_row_count=%(actionable_row_count)s, weight_row_count=%(weight_row_count)s,
                    movement_row_count=%(movement_row_count)s, skipped_row_count=%(skipped_row_count)s,
                    success_count=%(success_count)s, failed_count=%(failed_count)s, duplicate_count=%(duplicate_count)s,
                    error_summary=%(error_summary)s, payload_summary_json=%(payload_summary_json)s::jsonb,
                    updated_at=now(), completed_at=case when %(completed)s then now() else completed_at end
                where batch_id=%(batch_id)s::uuid
                """,
                {**batch, **counts, "payload_summary_json": _jsonb(batch.get("payload_summary_json", {})), "completed": batch.get("status") in {"complete", "failed", "partial"}},
            )
            for row in rows:
                cursor.execute(
                    """
                    update public.bulk_weight_batch_rows set status=%(status)s, status_reason=%(status_reason)s,
                        processed_at=%(processed_at)s, result_json=%(result_json)s::jsonb, updated_at=now()
                    where row_id=%(row_id)s::uuid
                    """,
                    {**row, "result_json": _jsonb(row.get("result_json", {}))},
                )


def _stage_store(batch, rows):
    if _store_mode() == "memory":
        _memory_stage(batch, rows)
    else:
        _pg_stage(batch, rows)


def _get_store(batch_id):
    if _store_mode() == "memory":
        return _memory_get(batch_id)
    return _pg_get(batch_id)


def _save_store(batch, rows):
    if _store_mode() == "memory":
        _memory_save(batch, rows)
    else:
        _pg_save(batch, rows)


def stage_bulk_weight_batch(payload: dict):
    payload = payload or {}
    rows = _safe_rows(payload)
    preflight, status_code = pig_weights_service.preflight_bulk_weight_entries(payload)
    if status_code != 200:
        return {**preflight, "next_action": "fix_validation", "writes_to_google_sheets": False, "writes_to_supabase": False}, status_code

    batch_id = _new_id()
    row_records = _build_row_records(batch_id, payload, preflight)
    counts = _counts_from_records(row_records)
    batch = {
        "batch_id": batch_id,
        "client_draft_id": to_clean_string(payload.get("draft_id", payload.get("client_draft_id", ""))),
        "weight_date": str(payload.get("weight_date", "")),
        "status": "staged" if counts["staged_count"] else _batch_status_from_counts(counts),
        **counts,
        "source": "bulk_weights_web",
        "notes": to_clean_string(payload.get("notes", "")),
        "error_summary": "",
        "payload_summary_json": {
            "submitted_count": len(rows),
            "preflight": {key: preflight.get(key) for key in ["accepted_count", "weight_count", "movement_only_count", "duplicate_weight_movement_count", "blocked_count", "skipped_count"]},
        },
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": None,
    }
    try:
        _stage_store(batch, row_records)
    except Exception as exc:
        return {
            "ok": False,
            "success": False,
            "error": "bulk_batch_stage_failed",
            "status": "stage_failed",
            "message": "Could not stage the bulk batch durably. Draft kept on this device.",
            "detail": str(exc)[:240],
            "counts": counts,
            "writes_to_google_sheets": False,
            "writes_to_supabase": False,
        }, 503

    return _batch_response(batch, row_records, ok=True, next_action="process" if counts["staged_count"] else "review"), 201


def get_bulk_weight_batch_status(batch_id: str):
    batch, rows = _get_store(batch_id)
    if not batch:
        return {"ok": False, "success": False, "error": "batch_not_found", "message": "Bulk batch was not found."}, 404
    return _batch_response(batch, rows, ok=True, next_action="process" if _counts_from_records(rows)["staged_count"] else "review"), 200


def process_bulk_weight_batch(batch_id: str, chunk_size: int = DEFAULT_CHUNK_SIZE, retry_failed: bool = False):
    batch, rows = _get_store(batch_id)
    if not batch:
        return {"ok": False, "success": False, "error": "batch_not_found", "message": "Bulk batch was not found."}, 404
    try:
        chunk_size = max(1, min(int(chunk_size or DEFAULT_CHUNK_SIZE), 25))
    except Exception:
        chunk_size = DEFAULT_CHUNK_SIZE

    eligible_statuses = {"failed"} if retry_failed else {"staged"}
    candidates = [row for row in rows if row.get("status") in eligible_statuses]
    chunk = candidates[:chunk_size]
    if not chunk:
        counts = _counts_from_records(rows)
        batch["status"] = _batch_status_from_counts(counts)
        _save_store(batch, rows)
        return _batch_response(batch, rows, ok=True, next_action="complete" if batch["status"] == "complete" else "review"), 200

    batch["status"] = "processing"
    for row in chunk:
        row["status"] = "processing"
        row["updated_at"] = _now_iso()
    _save_store(batch, rows)

    for row in chunk:
        _process_one_row(row)
    counts = _counts_from_records(rows)
    batch["status"] = "processing" if counts["staged_count"] else _batch_status_from_counts(counts)
    batch["error_summary"] = "" if counts["failed_count"] == 0 else f"{counts['failed_count']} row(s) need retry or review."
    batch["payload_summary_json"] = {**(batch.get("payload_summary_json") or {}), "last_processed_at": _now_iso(), "last_chunk_size": len(chunk)}
    _save_store(batch, rows)
    next_action = "process" if _counts_from_records(rows)["staged_count"] else "review" if _counts_from_records(rows)["failed_count"] else "complete"
    return _batch_response(batch, rows, ok=True, next_action=next_action), 200


def retry_failed_bulk_weight_batch(batch_id: str, chunk_size: int = DEFAULT_CHUNK_SIZE):
    return process_bulk_weight_batch(batch_id, chunk_size=chunk_size, retry_failed=True)


def _process_one_row(row):
    result_json = row.get("result_json") or {}
    action_type = result_json.get("action_type", "weight")
    preflight = result_json.get("preflight") or {}
    try:
        if action_type in {"movement_only", "duplicate_weight_movement"}:
            result = save_movement_entry({
                "pig_id": row.get("pig_id", ""),
                "move_date": parse_sheet_date(preflight.get("weight_date", "") or row.get("original_row_json", {}).get("weight_date", "")),
                "from_pen_id": row.get("from_pen_id", ""),
                "to_pen_id": row.get("to_pen_id", ""),
                "reason_for_move": "Moved during durable bulk capture" if action_type == "movement_only" else "Moved during durable duplicate weight review",
                "moved_by": "WebApp",
                "move_notes": preflight.get("condition_notes", ""),
            })
            if not result.get("success", True):
                raise RuntimeError(result.get("message") or result.get("status") or "Movement save failed")
            row["status"] = "success"
            row["status_reason"] = "Movement saved."
            row["result_json"] = {**result_json, "process_result": result}
        else:
            result = save_weight_entry_with_optional_move({
                "pig_id": row.get("pig_id", ""),
                "weight_date": parse_sheet_date(preflight.get("weight_date", "") or row.get("original_row_json", {}).get("weight_date", "")),
                "weight_kg": row.get("weight_kg"),
                "condition_notes": preflight.get("condition_notes", ""),
                "weighed_by": preflight.get("weighed_by", "WebApp"),
                "moved_to_pen_id": row.get("to_pen_id", ""),
                "allow_duplicate": False,
            })
            if not result.get("success"):
                raise RuntimeError(result.get("message") or result.get("status") or "Weight save failed")
            row["status"] = "success"
            row["status_reason"] = "Weight saved." + (" Movement saved." if result.get("movement_logged") else "")
            row["result_json"] = {**result_json, "process_result": result}
    except Exception as exc:
        row["status"] = "failed"
        row["status_reason"] = str(exc)[:240]
        row["result_json"] = {**result_json, "process_error": {"message": str(exc), "type": exc.__class__.__name__}}
    row["processed_at"] = _now_iso()
    row["updated_at"] = _now_iso()


def _batch_response(batch, rows, ok=True, next_action="review"):
    counts = _counts_from_records(rows)
    row_summaries = [
        {
            "row_id": row.get("row_id"),
            "row_index": row.get("row_index"),
            "pig_id": row.get("pig_id", ""),
            "tag_number": row.get("tag_number", ""),
            "weight_kg": row.get("weight_kg"),
            "from_pen_id": row.get("from_pen_id", ""),
            "to_pen_id": row.get("to_pen_id", ""),
            "status": row.get("status", ""),
            "status_reason": row.get("status_reason", ""),
            "action_type": (row.get("result_json") or {}).get("action_type", ""),
        }
        for row in sorted(rows, key=lambda item: item.get("row_index", 0))
    ]
    return {
        "ok": ok,
        "success": ok,
        "batch_id": batch.get("batch_id"),
        "operation_id": batch.get("batch_id"),
        "status": batch.get("status", _batch_status_from_counts(counts)),
        "next_action": next_action,
        "counts": counts,
        "visible_row_count": counts["visible_row_count"],
        "actionable_row_count": counts["actionable_row_count"],
        "weight_row_count": counts["weight_row_count"],
        "movement_row_count": counts["movement_row_count"],
        "skipped_row_count": counts["skipped_row_count"],
        "success_count": counts["success_count"],
        "failed_count": counts["failed_count"],
        "duplicate_count": counts["duplicate_count"],
        "remaining_count": counts["remaining_count"],
        "rows": row_summaries,
        "row_results": row_summaries,
        "writes_to_supabase": True,
        "writes_to_google_sheets": counts["success_count"] > 0,
    }
