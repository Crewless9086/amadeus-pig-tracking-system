"""Protected, append-only capture for Herdmaster evidence and advisory intent."""

import os
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5


DATABASE_URL_ENV = "DATABASE_URL"
OBSERVATION_CATEGORIES = {"health", "welfare", "growth", "behaviour", "housing", "other"}
SEVERITIES = {"low", "medium", "high", "critical"}
INTENT_TYPES = {"sell_after_weaning", "sell_when_ready", "retain_for_breeding", "hold_for_review", "other"}


class IdempotencyCollisionError(RuntimeError):
    """A reused key must identify the same immutable capture request."""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _timestamp(value, field):
    text = _text(value)
    if not text:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _confidence(value):
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be a number from 0 to 1") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be a number from 0 to 1")
    return confidence


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory:
        return connect_factory(database_url)
    if not database_url:
        raise RuntimeError("observation_capture_not_configured")
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _insert_or_existing(cursor, insert_sql, insert_params, table, id_column, idempotency_key, stored_columns, expected_values):
    cursor.execute(insert_sql, insert_params)
    row = cursor.fetchone()
    if row:
        return row[0], False
    cursor.execute(
        f"select {id_column}, {', '.join(stored_columns)} from public.{table} where idempotency_key = %s",
        (idempotency_key,),
    )
    existing = cursor.fetchone()
    if not existing:
        raise RuntimeError("append_only_capture_not_persisted")
    if tuple(existing[1:]) != tuple(expected_values):
        raise IdempotencyCollisionError("idempotency_key_content_mismatch")
    return existing[0], True


def record_observation(payload, author_reference, connect_factory=None):
    payload = payload if isinstance(payload, dict) else {}
    author_reference = _text(author_reference)
    pig_id, note, key = (_text(payload.get(name)) for name in ("pig_id", "note", "idempotency_key"))
    category, severity = _text(payload.get("category")).lower(), _text(payload.get("severity")).lower()
    if not pig_id or not note or not key or not author_reference:
        return {"success": False, "status": "invalid_observation", "error": "pig_id, note, idempotency_key and server author are required"}, 400
    if category not in OBSERVATION_CATEGORIES or severity not in SEVERITIES:
        return {"success": False, "status": "invalid_observation", "error": "category or severity is not allowed"}, 400
    try:
        observed_at, confidence = _timestamp(payload.get("observed_at"), "observed_at"), _confidence(payload.get("confidence"))
    except ValueError as exc:
        return {"success": False, "status": "invalid_observation", "error": str(exc)}, 400
    event_id = str(uuid5(NAMESPACE_URL, f"pig-observation:{key}"))
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                evidence_reference = _text(payload.get("evidence_reference")) or None
                expected_values = (pig_id, observed_at, author_reference, category, severity, note, confidence, evidence_reference, "owner", author_reference, key)
                stored_id, replayed = _insert_or_existing(cursor, """
                    insert into public.pig_observation_events
                    (observation_event_id, pig_id, observed_at, author_reference, category, severity, note, confidence, evidence_reference, source_system, source_reference, idempotency_key)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'owner', %s, %s)
                    on conflict (idempotency_key) do nothing returning observation_event_id
                """, (event_id, pig_id, observed_at, author_reference, category, severity, note, confidence, evidence_reference, author_reference, key), "pig_observation_events", "observation_event_id", key,
                    ("pig_id", "observed_at", "author_reference", "category", "severity", "note", "confidence", "evidence_reference", "source_system", "source_reference", "idempotency_key"), expected_values)
        return {"success": True, "status": "observation_recorded", "observation_event_id": stored_id, "replayed": replayed, "writes_to_pigs": False, "executes_action": False}, 201
    except IdempotencyCollisionError as exc:
        return {"success": False, "status": str(exc), "writes_to_pigs": False, "executes_action": False}, 409
    except RuntimeError as exc:
        return {"success": False, "status": str(exc), "writes_to_pigs": False, "executes_action": False}, 503
    except Exception:
        return {"success": False, "status": "observation_capture_failed", "writes_to_pigs": False, "executes_action": False}, 500


def record_management_intent(payload, author_reference, connect_factory=None):
    payload = payload if isinstance(payload, dict) else {}
    author_reference = _text(author_reference)
    pig_id, rationale, key = (_text(payload.get(name)) for name in ("pig_id", "rationale", "idempotency_key"))
    intent_type = _text(payload.get("intent_type")).lower()
    if not pig_id or not rationale or not key or not author_reference:
        return {"success": False, "status": "invalid_management_intent", "error": "pig_id, rationale, idempotency_key and server author are required"}, 400
    if intent_type not in INTENT_TYPES:
        return {"success": False, "status": "invalid_management_intent", "error": "intent_type is not allowed"}, 400
    try:
        intended_at, confidence = _timestamp(payload.get("intended_at"), "intended_at"), _confidence(payload.get("confidence"))
    except ValueError as exc:
        return {"success": False, "status": "invalid_management_intent", "error": str(exc)}, 400
    event_id = str(uuid5(NAMESPACE_URL, f"pig-management-intent:{key}"))
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                observation_event_id = _text(payload.get("observation_event_id")) or None
                evidence_reference = _text(payload.get("evidence_reference")) or None
                expected_values = (pig_id, intended_at, author_reference, intent_type, rationale, confidence, observation_event_id, evidence_reference, "owner", author_reference, key)
                stored_id, replayed = _insert_or_existing(cursor, """
                    insert into public.pig_management_intent_events
                    (management_intent_event_id, pig_id, intended_at, author_reference, intent_type, rationale, confidence, observation_event_id, evidence_reference, source_system, source_reference, idempotency_key)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'owner', %s, %s)
                    on conflict (idempotency_key) do nothing returning management_intent_event_id
                """, (event_id, pig_id, intended_at, author_reference, intent_type, rationale, confidence, observation_event_id, evidence_reference, author_reference, key), "pig_management_intent_events", "management_intent_event_id", key,
                    ("pig_id", "intended_at", "author_reference", "intent_type", "rationale", "confidence", "observation_event_id", "evidence_reference", "source_system", "source_reference", "idempotency_key"), expected_values)
        return {"success": True, "status": "management_intent_recorded", "management_intent_event_id": stored_id, "replayed": replayed, "advisory_only": True, "writes_to_pigs": False, "executes_action": False}, 201
    except IdempotencyCollisionError as exc:
        return {"success": False, "status": str(exc), "advisory_only": True, "writes_to_pigs": False, "executes_action": False}, 409
    except RuntimeError as exc:
        return {"success": False, "status": str(exc), "advisory_only": True, "writes_to_pigs": False, "executes_action": False}, 503
    except Exception:
        return {"success": False, "status": "management_intent_capture_failed", "advisory_only": True, "writes_to_pigs": False, "executes_action": False}, 500
