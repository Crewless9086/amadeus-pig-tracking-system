"""Durable append/read adapter for the unified operational event fabric."""

from __future__ import annotations

import json

from modules.charlie.mission_store import _connect, _database_url
from modules.charlie.operational_events import build_event


def append_operational_event(packet, *, database_url=None, connect_factory=None):
    ready = build_event(packet)
    if not ready.get("accepted"):
        return {"success": False, **ready}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "operational_event_store_not_configured"}, 503
    event = ready["event"]
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.operational_events (
                        event_id,idempotency_key,schema_version,event_type,domain,aggregate_type,aggregate_id,
                        source_system,source_record_id,authority_tier,privacy_class,actor_type,actor_id,
                        correlation_id,causation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json
                    ) values (
                        %(event_id)s,%(idempotency_key)s,%(schema_version)s,%(event_type)s,%(domain)s,%(aggregate_type)s,%(aggregate_id)s,
                        %(source_system)s,%(source_record_id)s,%(authority_tier)s,%(privacy_class)s,%(actor_type)s,%(actor_id)s,
                        %(correlation_id)s,%(causation_id)s,%(occurred_at)s,%(recorded_at)s,%(freshness_at)s,%(payload)s::jsonb,%(provenance)s::jsonb
                    ) on conflict (idempotency_key) do nothing returning event_id
                """, {**event, "payload": json.dumps(event["payload"]), "provenance": json.dumps(event["provenance"])})
                row = cursor.fetchone()
                created = bool(row)
                event_id = row[0] if row else ""
                if not created:
                    cursor.execute(
                        "select event_id from public.operational_events where idempotency_key=%(key)s",
                        {"key": event["idempotency_key"]},
                    )
                    existing = cursor.fetchone()
                    event_id = existing[0] if existing else ""
    except Exception as exc:
        return {"success": False, "status": "operational_event_append_failed", "error_type": exc.__class__.__name__}, 503
    return {
        "success": bool(event_id),
        "status": "operational_event_appended" if created else "operational_event_duplicate",
        "created": created,
        "event_id": event_id,
        "idempotency_key": event["idempotency_key"],
    }, 201 if created else 200


def load_operational_events(*, domain="", aggregate_type="", aggregate_id="", limit=1000, database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "operational_event_store_not_configured", "events": []}, 503
    limit = max(1, min(int(limit or 1000), 10000))
    filters, params = [], {"limit": limit}
    for column, value in (("domain", domain), ("aggregate_type", aggregate_type), ("aggregate_id", aggregate_id)):
        if str(value or "").strip():
            filters.append(f"{column}=%({column})s")
            params[column] = str(value).strip()
    where = " where " + " and ".join(filters) if filters else ""
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    select event_id,idempotency_key,schema_version,event_type,domain,aggregate_type,aggregate_id,
                           source_system,source_record_id,authority_tier,privacy_class,actor_type,actor_id,
                           correlation_id,causation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json
                    from public.operational_events{where}
                    order by occurred_at,recorded_at,event_id limit %(limit)s
                """, params)
                events = [_event_row(row) for row in cursor.fetchall()]
    except Exception as exc:
        return {"success": False, "status": "operational_event_read_failed", "error_type": exc.__class__.__name__, "events": []}, 503
    return {"success": True, "status": "operational_events_ready", "events": events}, 200


def _event_row(row):
    keys = ("event_id", "idempotency_key", "schema_version", "event_type", "domain", "aggregate_type", "aggregate_id", "source_system", "source_record_id", "authority_tier", "privacy_class", "actor_type", "actor_id", "correlation_id", "causation_id", "occurred_at", "recorded_at", "freshness_at", "payload", "provenance")
    result = dict(zip(keys, row))
    for key in ("occurred_at", "recorded_at", "freshness_at"):
        if hasattr(result.get(key), "isoformat"):
            result[key] = result[key].isoformat()
    return result
