"""Protected, append-only Herdmaster observation and intent capture.

This module never changes the ``pigs`` current-state projection or any
lifecycle, commercial, reservation, customer, or stock record.  It is usable
only after the separately owner-authorized additive migration is applied.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from modules.pig_weights.pig_weights_utils import to_clean_string
from services.database_service import DATABASE_URL_ENV


OBSERVATION_CATEGORIES = {"behaviour", "body_condition", "feeding_drinking", "environment", "welfare", "data_quality", "other"}
SEVERITIES = {"low", "medium", "high", "critical"}
INTENT_TYPES = {"sell_after_weaning", "sell_when_ready", "retain_for_breeding", "hold_for_review", "other"}


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory:
        return connect_factory(database_url)
    if not database_url:
        raise RuntimeError("pig_observation_capture_store_not_configured")
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _timestamp(value, field, errors):
    try:
        parsed = datetime.fromisoformat(to_clean_string(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp with timezone.")
        return None


def _common(payload, timestamp_field):
    payload = payload if isinstance(payload, dict) else {}
    errors = []
    timestamp = _timestamp(payload.get(timestamp_field), timestamp_field, errors)
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("confidence must be a number from 0 to 1.")
    measurements = payload.get("measurements", {})
    if not isinstance(measurements, dict):
        errors.append("measurements must be an object.")
    result = {
        "timestamp": timestamp,
        "confidence": confidence if not isinstance(confidence, bool) else None,
        "measurements": measurements if isinstance(measurements, dict) else {},
        "idempotency_key": to_clean_string(payload.get("idempotency_key")),
        "evidence_reference": to_clean_string(payload.get("evidence_reference"))[:500] or None,
        "source_reference": to_clean_string(payload.get("source_reference"))[:500],
    }
    if not result["idempotency_key"]:
        errors.append("idempotency_key is required.")
    return result, errors


def _observation(payload):
    clean, errors = _common(payload, "observed_at")
    payload = payload if isinstance(payload, dict) else {}
    clean.update({
        "category": to_clean_string(payload.get("category")),
        "severity": to_clean_string(payload.get("severity")),
        "note": to_clean_string(payload.get("note"))[:4000],
        "supersedes": to_clean_string(payload.get("supersedes_observation_event_id")) or None,
    })
    if clean["category"] not in OBSERVATION_CATEGORIES:
        errors.append("category is unsupported.")
    if clean["severity"] not in SEVERITIES:
        errors.append("severity is unsupported.")
    if not clean["note"]:
        errors.append("note is required.")
    return clean, errors


def _intent(payload):
    clean, errors = _common(payload, "intended_at")
    payload = payload if isinstance(payload, dict) else {}
    clean.update({
        "intent_type": to_clean_string(payload.get("intent_type")),
        "intent_status": to_clean_string(payload.get("intent_status") or "advisory"),
        "rationale": to_clean_string(payload.get("rationale"))[:4000],
        "observation_event_id": to_clean_string(payload.get("observation_event_id")) or None,
        "supersedes": to_clean_string(payload.get("supersedes_management_intent_event_id")) or None,
    })
    if clean["intent_type"] not in INTENT_TYPES:
        errors.append("intent_type is unsupported.")
    if clean["intent_status"] != "advisory":
        errors.append("intent_status must be advisory.")
    if not clean["rationale"]:
        errors.append("rationale is required.")
    return clean, errors


def _invalid(kind, errors):
    return {"success": False, "status": f"pig_{kind}_capture_invalid", "errors": errors, "writes_to_supabase": False, "changes_pig_current_state": False}, 400


def _existing(cursor, table, key):
    cursor.execute(f"select pig_id, idempotency_key from public.{table} where idempotency_key=%s", (key,))
    return cursor.fetchone()


def _matches_existing(cursor, table, pig_id, clean, kind):
    if kind == "observation":
        cursor.execute(
            """select 1 from public.pig_observation_events where idempotency_key=%s and pig_id=%s
            and observed_at=%s and category=%s and severity=%s and note=%s and measurements_json=%s::jsonb
            and confidence=%s and evidence_reference is not distinct from %s and source_reference=%s
            and supersedes_observation_event_id is not distinct from %s""",
            (clean["idempotency_key"], pig_id, clean["timestamp"], clean["category"], clean["severity"], clean["note"],
             json.dumps(clean["measurements"]), clean["confidence"], clean["evidence_reference"], clean["source_reference"], clean["supersedes"]),
        )
    else:
        cursor.execute(
            """select 1 from public.pig_management_intent_events where idempotency_key=%s and pig_id=%s
            and intended_at=%s and intent_type=%s and intent_status='advisory' and rationale=%s and confidence=%s
            and observation_event_id is not distinct from %s and evidence_reference is not distinct from %s
            and source_reference=%s and supersedes_management_intent_event_id is not distinct from %s""",
            (clean["idempotency_key"], pig_id, clean["timestamp"], clean["intent_type"], clean["rationale"],
             clean["confidence"], clean["observation_event_id"], clean["evidence_reference"], clean["source_reference"], clean["supersedes"]),
        )
    return bool(cursor.fetchone())


def _capture(pig_id, payload, actor_id, *, kind, connect_factory=None):
    pig_id, actor_id = to_clean_string(pig_id), to_clean_string(actor_id)
    clean, errors = (_observation(payload) if kind == "observation" else _intent(payload))
    if not pig_id:
        errors.append("pig_id is required.")
    if not actor_id:
        errors.append("owner principal is required.")
    if errors:
        return _invalid(kind, errors)
    table = "pig_observation_events" if kind == "observation" else "pig_management_intent_events"
    event_column = "observation_event_id" if kind == "observation" else "management_intent_event_id"
    event_id = ("OBS-" if kind == "observation" else "INT-") + uuid.uuid4().hex.upper()
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pig_id from public.pigs where pig_id=%s", (pig_id,))
                if not cursor.fetchone():
                    return {"success": False, "status": "pig_observation_capture_pig_not_found", "writes_to_supabase": False, "changes_pig_current_state": False}, 404
                existing = _existing(cursor, table, clean["idempotency_key"])
                if existing:
                    if existing[0] == pig_id and _matches_existing(cursor, table, pig_id, clean, kind):
                        return {"success": True, "status": f"pig_{kind}_capture_duplicate", "pig_id": pig_id, "writes_to_supabase": False, "changes_pig_current_state": False}, 200
                    return {"success": False, "status": f"pig_{kind}_capture_idempotency_conflict", "writes_to_supabase": False, "changes_pig_current_state": False}, 409
                if kind == "observation":
                    cursor.execute("""insert into public.pig_observation_events
                        (observation_event_id,pig_id,observed_at,author_reference,category,severity,note,measurements_json,confidence,evidence_reference,source_system,source_reference,idempotency_key,supersedes_observation_event_id)
                        values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,'owner',%s,%s,%s)""",
                        (event_id, pig_id, clean["timestamp"], actor_id, clean["category"], clean["severity"], clean["note"], json.dumps(clean["measurements"]), clean["confidence"], clean["evidence_reference"], clean["source_reference"], clean["idempotency_key"], clean["supersedes"]))
                else:
                    cursor.execute("""insert into public.pig_management_intent_events
                        (management_intent_event_id,pig_id,intended_at,author_reference,intent_type,intent_status,rationale,confidence,observation_event_id,evidence_reference,source_system,source_reference,idempotency_key,supersedes_management_intent_event_id)
                        values (%s,%s,%s,%s,%s,'advisory',%s,%s,%s,%s,'owner',%s,%s,%s)""",
                        (event_id, pig_id, clean["timestamp"], actor_id, clean["intent_type"], clean["rationale"], clean["confidence"], clean["observation_event_id"], clean["evidence_reference"], clean["source_reference"], clean["idempotency_key"], clean["supersedes"]))
        return {"success": True, "status": f"pig_{kind}_captured", "pig_id": pig_id, event_column: event_id, "writes_to_supabase": True, "changes_pig_current_state": False}, 201
    except Exception:
        return {"success": False, "status": "pig_observation_capture_schema_unavailable", "writes_to_supabase": False, "changes_pig_current_state": False}, 503


def capture_observation(pig_id, payload, *, actor_id, connect_factory=None):
    return _capture(pig_id, payload, actor_id, kind="observation", connect_factory=connect_factory)


def capture_management_intent(pig_id, payload, *, actor_id, connect_factory=None):
    return _capture(pig_id, payload, actor_id, kind="management_intent", connect_factory=connect_factory)
