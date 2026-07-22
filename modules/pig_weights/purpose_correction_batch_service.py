"""Owner-approved, Supabase-only purpose correction batches.

This is deliberately separate from the advisory purpose-review queue.  It has
no Sheets fallback: a missing audit rail is a safe failure, never a write.
"""
import hashlib
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

from services.database_service import DATABASE_URL_ENV
from modules.pig_weights.pig_weights_utils import to_clean_string

STALE_WEIGHT_DAYS = 30
ALLOWED_PURPOSES = {"Breeding", "Grow_Out", "Meat", "Sale", "Slaughter"}


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory:
        return connect_factory(database_url)
    if not database_url:
        raise RuntimeError("correction_batch_store_not_configured")
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _decisions(value):
    if not isinstance(value, list) or not value:
        return None, ["At least one correction decision is required."]
    clean, seen, errors = [], set(), []
    for index, raw in enumerate(value, 1):
        raw = raw if isinstance(raw, dict) else {}
        pig_id, purpose = to_clean_string(raw.get("pig_id")), to_clean_string(raw.get("purpose"))
        if not pig_id or purpose not in ALLOWED_PURPOSES or pig_id in seen:
            errors.append(f"Decision {index} is invalid, unsupported, or duplicates a pig.")
            continue
        seen.add(pig_id)
        clean.append({"pig_id": pig_id, "purpose": purpose, "reason": to_clean_string(raw.get("reason"))[:500], "note": to_clean_string(raw.get("note"))[:1000]})
    return (clean, errors) if not errors else (None, errors)


def create_correction_batch(decisions, *, idempotency_key, actor_id="owner_admin_session", connect_factory=None):
    clean, errors = _decisions(decisions)
    key = to_clean_string(idempotency_key)
    if errors or not key:
        return {"success": False, "status": "correction_batch_invalid", "errors": errors or ["Idempotency key is required."]}, 400
    batch_id = f"PURPOSE-CORRECTION-{uuid.uuid4().hex[:20].upper()}"
    digest = hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""insert into public.pig_purpose_correction_batches
                    (batch_id, idempotency_key, status, decisions_json, decision_hash, created_by)
                    values (%s,%s,'draft',%s::jsonb,%s,%s)
                    on conflict (idempotency_key) do nothing returning batch_id,status""", (batch_id, key, json.dumps(clean), digest, actor_id))
                row = cursor.fetchone()
                if not row:
                    cursor.execute("select batch_id,status from public.pig_purpose_correction_batches where idempotency_key=%s", (key,))
                    row = cursor.fetchone()
                return {"success": True, "status": "correction_batch_created" if row[0] == batch_id else "correction_batch_duplicate", "batch_id": row[0], "batch_status": row[1], "writes_to_sheets": False}, 201 if row[0] == batch_id else 200
    except Exception:
        return {"success": False, "status": "correction_batch_store_unavailable", "writes_to_sheets": False}, 503


def approve_correction_batch(batch_id, *, actor_id="owner_admin_session", connect_factory=None):
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""update public.pig_purpose_correction_batches set status='owner_approved', owner_approved_at=now(), owner_approved_by=%s
                    where batch_id=%s and status='draft' returning batch_id""", (actor_id, batch_id))
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "correction_batch_not_approvable"}, 409
        return {"success": True, "status": "correction_batch_owner_approved", "batch_id": batch_id, "writes_to_sheets": False}, 200
    except Exception:
        return {"success": False, "status": "correction_batch_store_unavailable", "writes_to_sheets": False}, 503


def execute_correction_batch(batch_id, *, actor_id="owner_admin_session", connect_factory=None, today=None):
    today = today or date.today()
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status, decisions_json, decision_hash, owner_approved_at, owner_approved_by from public.pig_purpose_correction_batches where batch_id=%s for update", (batch_id,))
                batch = cursor.fetchone()
                if not batch:
                    return {"success": False, "status": "correction_batch_not_found"}, 404
                status, decisions, digest, approved_at, approved_by = batch
                if status == "executed":
                    return {"success": True, "status": "correction_batch_duplicate_execution", "batch_id": batch_id, "writes_to_sheets": False}, 200
                if status != "owner_approved" or not approved_at or not approved_by:
                    return {"success": False, "status": "correction_batch_not_owner_approved"}, 409
                decisions = decisions if isinstance(decisions, list) else json.loads(decisions)
                pig_ids = [item["pig_id"] for item in decisions]
                cursor.execute("""select pig.pig_id,pig.status,pig.on_farm,pig.purpose,latest.weight_date,latest.weight_kg
                    from public.pigs pig
                    left join lateral (
                        select weight_date,weight_kg from public.pig_weight_events
                        where pig_id=pig.pig_id order by weight_date desc,created_at desc,weight_event_id desc limit 1
                    ) latest on true
                    where pig.pig_id = any(%s) for update of pig""", (pig_ids,))
                pigs = {row[0]: row for row in cursor.fetchall()}
                errors = []
                for item in decisions:
                    pig = pigs.get(item["pig_id"])
                    if not pig or pig[1] != "Active" or not pig[2] or pig[4] is None or pig[5] is None or (today - pig[4]).days > STALE_WEIGHT_DAYS:
                        errors.append(item["pig_id"])
                if errors:
                    return {"success": False, "status": "correction_batch_weight_not_fresh", "blocked_pig_ids": errors, "writes_to_sheets": False}, 409
                event_ids = []
                now = datetime.now(timezone.utc)
                for item in decisions:
                    pig = pigs[item["pig_id"]]
                    event_id = f"EVT-{uuid.uuid4().hex[:24].upper()}"
                    event_key = hashlib.sha256(f"{batch_id}|{item['pig_id']}|{digest}".encode()).hexdigest()
                    payload = {"batch_id": batch_id, "old_purpose": pig[3] or "Unknown", "new_purpose": item["purpose"], "reason": item["reason"], "note": item["note"], "approved_by": approved_by, "approved_at": approved_at.isoformat()}
                    cursor.execute("update public.pigs set purpose=%s, updated_at=now() where pig_id=%s", (item["purpose"], item["pig_id"]))
                    cursor.execute("""insert into public.operational_events (event_id,idempotency_key,event_type,domain,aggregate_type,aggregate_id,source_system,authority_tier,privacy_class,actor_type,actor_id,correlation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json)
                        values (%s,%s,'pig.purpose_corrected','animals','pig',%s,'herdmaster_purpose_correction','owner_approved','owner_private','owner',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""", (event_id, event_key, item["pig_id"], actor_id, batch_id, now, now, now, json.dumps(payload), json.dumps({"source_ref": "pig_current_state", "weight_date": pig[4].isoformat()})))
                    event_ids.append(event_id)
                cursor.execute("update public.pig_purpose_correction_batches set status='executed', executed_at=now(), executed_by=%s where batch_id=%s", (actor_id, batch_id))
        return {"success": True, "status": "correction_batch_executed", "batch_id": batch_id, "event_ids": event_ids, "writes_to_sheets": False, "writes_to_supabase": True}, 200
    except Exception:
        return {"success": False, "status": "correction_batch_atomic_execution_failed", "writes_to_sheets": False}, 503
