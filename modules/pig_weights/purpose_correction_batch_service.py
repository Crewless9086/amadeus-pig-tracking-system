"""Owner-approved, Supabase-only purpose correction batches.

This is deliberately separate from the advisory purpose-review queue.  It has
no Sheets fallback: a missing audit rail is a safe failure, never a write.
"""
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from services.database_service import DATABASE_URL_ENV
from modules.pig_weights.pig_weights_utils import to_clean_string

STALE_WEIGHT_DAYS = 30
ALLOWED_PURPOSES = {"Breeding", "Grow_Out", "Meat", "Sale", "Slaughter"}
CONTRACT_VERSION = "herdmaster_purpose_correction_v2"
PREVIEW_TTL_SECONDS = 30 * 60
SAFE_ORDER_RETURN = re.compile(r"^/orders/[A-Za-z0-9][A-Za-z0-9-]{2,79}$")


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


def _decision_hash(decisions):
    return hashlib.sha256(
        json.dumps(decisions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_pigs(cursor, pig_ids, *, lock=False):
    cursor.execute(f"""select pig.pig_id,coalesce(pig.tag_number,''),pig.status,
        pig.on_farm,coalesce(pig.purpose,''),latest.weight_date,latest.weight_kg
        from public.current_canonical_pigs pig
        left join lateral (
            select weight_date,weight_kg from public.pig_weight_events
            where pig_id=pig.pig_id
            order by weight_date desc,created_at desc,weight_event_id desc limit 1
        ) latest on true
        where pig.pig_id = any(%s){' for update of pig' if lock else ''}""", (pig_ids,))
    return {row[0]: row for row in cursor.fetchall()}


def _snapshot(decisions, pigs):
    return [{
        "pig_id": item["pig_id"], "tag_number": pigs[item["pig_id"]][1],
        "old_purpose": pigs[item["pig_id"]][4] or "Unknown",
        "new_purpose": item["purpose"], "reason": item["reason"],
        "note": item["note"],
        "status": pigs[item["pig_id"]][2],
        "on_farm": bool(pigs[item["pig_id"]][3]),
        "latest_weight_date": pigs[item["pig_id"]][5].isoformat() if pigs[item["pig_id"]][5] else None,
        "latest_weight_kg": float(pigs[item["pig_id"]][6]) if pigs[item["pig_id"]][6] is not None else None,
    } for item in decisions]


def _preview_digest(decisions, effects, return_to):
    return hashlib.sha256(json.dumps({
        "contract_version": CONTRACT_VERSION, "decisions": decisions,
        "effects": effects, "return_to": return_to,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _confirmation_binding(digest, actor_id, *, now=None):
    now = now or datetime.now(timezone.utc)
    issued_at = int(now.timestamp())
    material = f"{CONTRACT_VERSION}|{digest}|{actor_id}|{issued_at}"
    secret = str(os.getenv("OWNER_SESSION_SECRET") or os.getenv("SECRET_KEY") or "").encode()
    signature = hmac.new(secret, material.encode(), hashlib.sha256).hexdigest() if secret else ""
    return {"contract_version": CONTRACT_VERSION, "preview_digest": digest,
            "actor_id": actor_id, "issued_at": issued_at, "signature": signature}


def _valid_confirmation(binding, digest, actor_id, *, now=None):
    if not isinstance(binding, dict):
        return False
    now = now or datetime.now(timezone.utc)
    try:
        issued_at = int(binding.get("issued_at"))
    except (TypeError, ValueError):
        return False
    age = int(now.timestamp()) - issued_at
    expected = _confirmation_binding(
        digest, actor_id, now=datetime.fromtimestamp(issued_at, timezone.utc))
    return (0 <= age <= PREVIEW_TTL_SECONDS
            and str(binding.get("preview_digest") or "") == digest
            and str(binding.get("actor_id") or "") == actor_id
            and bool(expected["signature"])
            and hmac.compare_digest(str(binding.get("signature") or ""), expected["signature"]))


def preview_correction_batch(decisions, *, actor_id, return_to="", connect_factory=None, now=None):
    clean, errors = _decisions(decisions)
    actor_id = to_clean_string(actor_id)
    return_to = to_clean_string(return_to)
    if return_to and not SAFE_ORDER_RETURN.fullmatch(return_to):
        errors = [*(errors or []), "Return destination must be an internal order-detail path."]
    if errors or not actor_id:
        return {"success": False, "status": "correction_preview_invalid",
                "errors": errors or ["Owner principal is required."], "writes_performed": False}, 400
    try:
        with _connect(connect_factory) as connection:
            connection.execute("set transaction isolation level repeatable read read only")
            with connection.cursor() as cursor:
                pigs = _load_pigs(cursor, [item["pig_id"] for item in clean])
                if set(pigs) != {item["pig_id"] for item in clean}:
                    return {"success": False, "status": "correction_preview_identity_mismatch",
                            "writes_performed": False}, 409
                effects = _snapshot(clean, pigs)
                blocked = [row["pig_id"] for row in effects if row["status"] != "Active" or not row["on_farm"]]
                if blocked:
                    return {"success": False, "status": "correction_preview_not_active_on_farm",
                            "blocked_pig_ids": blocked, "writes_performed": False}, 409
    except Exception:
        return {"success": False, "status": "correction_batch_store_unavailable",
                "writes_performed": False}, 503
    digest = _preview_digest(clean, effects, return_to)
    return {"success": True, "status": "correction_preview_ready",
            "contract_version": CONTRACT_VERSION, "decisions": clean,
            "effects": effects, "approved_count": len(effects),
            "preview_digest": digest,
            "confirmation_binding": _confirmation_binding(digest, actor_id, now=now),
            "return_to": return_to or None, "writes_performed": False,
            "writes_to_sheets": False}, 200


def create_correction_batch(decisions, *, idempotency_key, actor_id,
                            confirmation_binding=None, return_to="", connect_factory=None):
    clean, errors = _decisions(decisions)
    key, actor_id = to_clean_string(idempotency_key), to_clean_string(actor_id)
    return_to = to_clean_string(return_to)
    if return_to and not SAFE_ORDER_RETURN.fullmatch(return_to):
        errors = [*(errors or []), "Return destination must be an internal order-detail path."]
    if errors or not key or not actor_id:
        return {"success": False, "status": "correction_batch_invalid", "errors": errors or ["Idempotency key and owner principal are required."]}, 400
    batch_id = f"PURPOSE-CORRECTION-{uuid.uuid4().hex[:20].upper()}"
    digest = _decision_hash(clean)
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                pigs = _load_pigs(cursor, [item["pig_id"] for item in clean])
                if set(pigs) != {item["pig_id"] for item in clean}:
                    return {"success": False, "status": "correction_preview_stale_or_altered", "writes_to_sheets": False}, 409
                effects = _snapshot(clean, pigs)
                preview_digest = _preview_digest(clean, effects, return_to)
                if not _valid_confirmation(confirmation_binding, preview_digest, actor_id):
                    return {"success": False, "status": "exact_preview_confirmation_required", "writes_to_sheets": False}, 409
                envelope = {
                    "contract_version": CONTRACT_VERSION,
                    "decisions": clean,
                    "effects": effects,
                    "preview_digest": preview_digest,
                    "return_to": return_to or None,
                }
                cursor.execute("""insert into public.pig_purpose_correction_batches
                    (batch_id, idempotency_key, status, decisions_json, decision_hash, created_by)
                    values (%s,%s,'draft',%s::jsonb,%s,%s)
                    on conflict (idempotency_key) do nothing returning batch_id,status""", (batch_id, key, json.dumps(envelope), digest, actor_id))
                row = cursor.fetchone()
                if not row:
                    cursor.execute("""select batch_id,status,decisions_json,decision_hash,created_by
                        from public.pig_purpose_correction_batches where idempotency_key=%s""", (key,))
                    row = cursor.fetchone()
                    stored = row[2] if isinstance(row[2], dict) else json.loads(row[2])
                    if (stored != envelope or str(row[3] or "") != digest
                            or str(row[4] or "") != actor_id):
                        return {"success": False, "status": "correction_batch_idempotency_conflict",
                                "writes_to_sheets": False}, 409
                return {"success": True, "status": "correction_batch_created" if row[0] == batch_id else "correction_batch_duplicate", "batch_id": row[0], "batch_status": row[1], "preview_digest": preview_digest, "return_to": return_to or None, "writes_to_sheets": False}, 201 if row[0] == batch_id else 200
    except Exception:
        return {"success": False, "status": "correction_batch_store_unavailable", "writes_to_sheets": False}, 503


def approve_correction_batch(batch_id, *, actor_id, connect_factory=None):
    actor_id = to_clean_string(actor_id)
    if not actor_id:
        return {"success": False, "status": "correction_batch_owner_principal_required", "writes_to_sheets": False}, 403
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""update public.pig_purpose_correction_batches set status='owner_approved', owner_approved_at=now(), owner_approved_by=%s
                    where batch_id=%s and status='draft' and created_by=%s returning batch_id""",
                               (actor_id, batch_id, actor_id))
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "correction_batch_not_approvable"}, 409
        return {"success": True, "status": "correction_batch_owner_approved", "batch_id": batch_id, "writes_to_sheets": False}, 200
    except Exception:
        return {"success": False, "status": "correction_batch_store_unavailable", "writes_to_sheets": False}, 503


def execute_correction_batch(batch_id, *, actor_id, connect_factory=None, today=None):
    actor_id = to_clean_string(actor_id)
    if not actor_id:
        return {"success": False, "status": "correction_batch_owner_principal_required", "writes_to_sheets": False}, 403
    today = today or date.today()
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                               ("purpose-correction:" + to_clean_string(batch_id),))
                cursor.execute("""select status,decisions_json,decision_hash,owner_approved_at,
                    owner_approved_by,created_by,executed_by
                    from public.pig_purpose_correction_batches where batch_id=%s for update""", (batch_id,))
                batch = cursor.fetchone()
                if not batch:
                    return {"success": False, "status": "correction_batch_not_found"}, 404
                status, stored_payload, digest, approved_at, approved_by, created_by, executed_by = batch
                if str(created_by or "") != actor_id or (approved_by and str(approved_by) != actor_id):
                    return {"success": False, "status": "correction_batch_owner_mismatch",
                            "writes_to_sheets": False, "writes_to_supabase": False}, 403
                envelope = stored_payload if isinstance(stored_payload, dict) else json.loads(stored_payload)
                if not isinstance(envelope, dict) or envelope.get("contract_version") != CONTRACT_VERSION:
                    return {"success": False, "status": "correction_batch_preview_binding_missing",
                            "writes_to_sheets": False, "writes_to_supabase": False}, 409
                decisions = envelope.get("decisions")
                if status == "executed":
                    if str(executed_by or "") != actor_id:
                        return {"success": False, "status": "correction_batch_owner_mismatch",
                                "writes_to_sheets": False, "writes_to_supabase": False}, 403
                    pig_ids = [item["pig_id"] for item in decisions]
                    cursor.execute("select pig_id,coalesce(tag_number,''),coalesce(purpose,''),status,on_farm from public.pigs where pig_id=any(%s) order by pig_id", (pig_ids,))
                    readback = [{"pig_id": row[0], "tag_number": row[1], "purpose": row[2],
                                 "status": row[3], "on_farm": bool(row[4]), "replay": True}
                                for row in cursor.fetchall()]
                    return {"success": True, "status": "correction_batch_duplicate_execution",
                            "batch_id": batch_id, "rows_updated": 0,
                            "requested_count": len(decisions), "canonical_readback": readback,
                            "writes_to_sheets": False, "writes_to_supabase": False}, 200
                if status != "owner_approved" or not approved_at or not approved_by:
                    return {"success": False, "status": "correction_batch_not_owner_approved"}, 409
                clean_decisions, decision_errors = _decisions(decisions)
                if decision_errors or clean_decisions != decisions or _decision_hash(clean_decisions) != str(digest or ""):
                    return {
                        "success": False,
                        "status": "correction_batch_decision_tampered",
                        "writes_to_sheets": False,
                    }, 409
                decisions = clean_decisions
                pig_ids = [item["pig_id"] for item in decisions]
                loaded = _load_pigs(cursor, pig_ids, lock=True)
                current_effects = _snapshot(decisions, loaded) if set(loaded) == set(pig_ids) else []
                if (current_effects != envelope.get("effects")
                        or _preview_digest(decisions, current_effects, envelope.get("return_to") or "")
                        != envelope.get("preview_digest")):
                    return {"success": False, "status": "correction_batch_preview_stale_or_altered",
                            "rows_updated": 0, "writes_to_sheets": False,
                            "writes_to_supabase": False}, 409
                pigs = {pig_id: (row[0], row[2], row[3], row[4], row[5], row[6])
                        for pig_id, row in loaded.items()}
                errors = []
                for item in decisions:
                    pig = pigs.get(item["pig_id"])
                    if not pig or pig[1] != "Active" or not pig[2] or pig[4] is None or pig[5] is None or (today - pig[4]).days > STALE_WEIGHT_DAYS:
                        errors.append(item["pig_id"])
                if errors:
                    return {"success": False, "status": "correction_batch_weight_not_fresh", "blocked_pig_ids": errors, "writes_to_sheets": False}, 409
                event_ids = []
                rows_updated = 0
                now = datetime.now(timezone.utc)
                for item in decisions:
                    pig = pigs[item["pig_id"]]
                    event_id = f"EVT-{uuid.uuid4().hex[:24].upper()}"
                    event_key = hashlib.sha256(f"{batch_id}|{item['pig_id']}|{digest}".encode()).hexdigest()
                    payload = {"batch_id": batch_id, "old_purpose": pig[3] or "Unknown", "new_purpose": item["purpose"], "reason": item["reason"], "note": item["note"], "approved_by": approved_by, "approved_at": approved_at.isoformat()}
                    cursor.execute("""update public.pigs set purpose=%s, updated_at=now()
                        where pig_id=%s and status='Active' and on_farm is true
                          and purpose is not distinct from %s""",
                                   (item["purpose"], item["pig_id"], pig[3]))
                    if cursor.rowcount != 1:
                        raise ValueError("purpose_correction_partial_write")
                    rows_updated += cursor.rowcount
                    cursor.execute("""insert into public.operational_events (event_id,idempotency_key,event_type,domain,aggregate_type,aggregate_id,source_system,authority_tier,privacy_class,actor_type,actor_id,correlation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json)
                        values (%s,%s,'pig.purpose_corrected','animals','pig',%s,'herdmaster_purpose_correction','owner_approved','owner_private','owner',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""", (event_id, event_key, item["pig_id"], actor_id, batch_id, now, now, now, json.dumps(payload), json.dumps({"source_ref": "pig_current_state", "weight_date": pig[4].isoformat()})))
                    event_ids.append(event_id)
                cursor.execute("update public.pig_purpose_correction_batches set status='executed', executed_at=now(), executed_by=%s where batch_id=%s", (actor_id, batch_id))
                if cursor.rowcount != 1 or rows_updated != len(decisions) or len(event_ids) != len(decisions):
                    raise ValueError("purpose_correction_partial_write")
                cursor.execute("select pig_id,coalesce(tag_number,''),coalesce(purpose,''),status,on_farm from public.pigs where pig_id=any(%s) order by pig_id", (pig_ids,))
                readback = [{"pig_id": row[0], "tag_number": row[1], "purpose": row[2],
                             "status": row[3], "on_farm": bool(row[4]), "replay": False}
                            for row in cursor.fetchall()]
                if (len(readback) != len(decisions)
                        or any(row["purpose"] != next(item["purpose"] for item in decisions if item["pig_id"] == row["pig_id"])
                               for row in readback)):
                    raise ValueError("purpose_correction_readback_mismatch")
        return {"success": True, "status": "correction_batch_executed", "batch_id": batch_id,
                "event_ids": event_ids, "requested_count": len(decisions),
                "rows_updated": rows_updated, "canonical_readback": readback,
                "writes_to_sheets": False, "writes_to_supabase": True}, 200
    except ValueError as exc:
        return {"success": False, "status": str(exc), "rows_updated": 0,
                "writes_to_sheets": False, "writes_to_supabase": False}, 409
    except Exception as exc:
        if getattr(exc, "sqlstate", "") in {"40001", "40P01", "23505"}:
            return {"success": False, "status": "correction_batch_concurrency_retry_required",
                    "rows_updated": 0, "writes_to_sheets": False, "writes_to_supabase": False}, 409
        return {"success": False, "status": "correction_batch_atomic_execution_failed", "writes_to_sheets": False}, 503
