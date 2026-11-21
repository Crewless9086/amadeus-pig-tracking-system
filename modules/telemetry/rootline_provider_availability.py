"""Read eWeLink availability evidence from the existing canonical audit rail.

No provider requests, credentials, commands, scheduler or new persistence store.
An outage episode is the first failed snapshot after the preceding proven
restoration, never the changing request-budget retry generation.
"""
from datetime import datetime, timezone
from hashlib import sha256
import re

from modules.telemetry.rootline_ewelink_request_budget import EVENT_SOURCE, LEDGER_ID

CONTRACT = "rootline_provider_availability.v1"
RECOVERY_FRESH_SECONDS = 900
TABLE = "public.sam_live_stock_conversation_review_events"


def _time(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _event(row):
    if not row:
        return None
    identity, observed, payload = row
    observed = _time(observed)
    if not isinstance(identity, str) or not identity or observed is None or not isinstance(payload, dict):
        raise ValueError("provider_availability_event_invalid")
    return {"event_id": identity, "observed_at": observed.isoformat(), "payload": payload}


def project_scope(scope, latest, failure, restoration, *, now):
    """Validate production-shaped envelopes before exposing a bounded projection."""
    now = _time(now)
    if now is None or not re.fullmatch(r"[0-9a-f]{64}", str(scope)):
        raise ValueError("provider_availability_scope_invalid")
    latest = _event(latest)
    if latest is None or _time(latest["observed_at"]) > now:
        raise ValueError("provider_availability_latest_invalid")
    body = latest["payload"]
    state = body.get("state")
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("provider_availability_state_invalid")
    current = (state.get("scopes") or {}).get(scope)
    if not isinstance(current, dict):
        raise ValueError("provider_availability_scope_missing")
    failure = _event(failure)
    if failure is None:
        if current.get("category"):
            raise ValueError("provider_availability_incident_unproven")
        return None
    failed = failure["payload"]
    detail = failed.get("detail") or {}
    category = (detail.get("failure") or {}).get("category") if failed.get("action") == "request_completed" else detail.get("category")
    if (failed.get("action") not in {"request_completed", "snapshot_validation_failed"}
            or detail.get("scope") != scope or not isinstance(category, str) or not category
            or not ((failed.get("state") or {}).get("scopes") or {}).get(scope, {}).get("category")
            or _time(failure["observed_at"]) > _time(latest["observed_at"])):
        raise ValueError("provider_availability_failure_invalid")
    identity = "ROOTLINE-PROVIDER-" + sha256((scope + "|" + failure["event_id"]).encode()).hexdigest()[:32].upper()
    result = {"contract": CONTRACT, "scope": scope, "incident_id": identity,
        "failure_event_id": failure["event_id"], "outage_started_at": failure["observed_at"],
        "state": "unavailable", "category": category,
        "latest_event_id": latest["event_id"], "latest_observed_at": latest["observed_at"],
        "next_probe_at": current.get("next_probe_at"), "provider_reset_at": "Unknown"}
    if current.get("category"):
        return result
    restored = _event(restoration)
    if restored is None:
        raise ValueError("provider_availability_restoration_unproven")
    proof = restored["payload"]
    restored_scope = ((proof.get("state") or {}).get("scopes") or {}).get(scope)
    restored_at = _time(restored["observed_at"])
    if (proof.get("action") != "complete_snapshot_restored_availability"
            or (proof.get("detail") or {}).get("scope") != scope
            or not (proof.get("detail") or {}).get("group_id")
            or not isinstance(restored_scope, dict) or restored_scope.get("category") is not None
            or restored_scope.get("failures") != 0
            or not (_time(failure["observed_at"]) <= restored_at <= _time(latest["observed_at"]) <= now)):
        raise ValueError("provider_availability_restoration_invalid")
    return {**result, "state": "restored", "restored_at": restored["observed_at"],
        "restoration_event_id": restored["event_id"],
        "recovery_fresh": (now - restored_at).total_seconds() <= RECOVERY_FRESH_SECONDS}


def read_provider_availability(*, database_url=None, now=None, connect=None, environ=None):
    """Bounded, cutoff-aware canonical reads; no network access to eWeLink."""
    from modules.telemetry.rootline_input_health import input_health_enabled
    if not input_health_enabled(environ):
        return {"contract": CONTRACT, "status": "unknown", "reason": "not_enabled", "scopes": []}
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    now = _time(now or datetime.now(timezone.utc))
    if now is None:
        raise ValueError("aware_time_required")
    connect = connect or connect_bounded_rootline_postgres
    with connect(database_url=database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"""select review_event_id,created_at,review_json->'ewelink_request_budget'
                from {TABLE} where event_source=%s and chatwoot_conversation_id=%s
                  and created_at<=%s order by created_at desc,review_event_id desc limit 1""",
                (EVENT_SOURCE, LEDGER_ID, now))
            latest = cursor.fetchone()
            if latest is None:
                return {"contract": CONTRACT, "status": "unobserved", "scopes": []}
            body = _event(latest)["payload"]
            scopes = (body.get("state") or {}).get("scopes")
            if not isinstance(scopes, dict) or len(scopes) > 16:
                raise ValueError("provider_availability_scopes_invalid")
            projected = []
            for scope, current in sorted(scopes.items()):
                if not isinstance(current, dict):
                    raise ValueError("provider_availability_scope_invalid")
                cursor.execute(f"""select review_event_id,created_at,review_json->'ewelink_request_budget'
                    from {TABLE} where event_source=%s and chatwoot_conversation_id=%s
                      and created_at<=%s and review_json->'ewelink_request_budget'->>'action'=
                        'complete_snapshot_restored_availability'
                      and review_json->'ewelink_request_budget'->'detail'->>'scope'=%s
                    order by created_at desc,review_event_id desc limit 2""",
                    (EVENT_SOURCE, LEDGER_ID, now, scope))
                recoveries = cursor.fetchall()
                # An open incident follows the latest restoration. A restored
                # incident began between the previous and latest restoration.
                restored = recoveries[0] if recoveries and not current.get("category") else None
                boundary = (recoveries[0] if recoveries else None) if current.get("category") else (
                    recoveries[1] if len(recoveries) > 1 else None)
                lower = boundary[1] if boundary else datetime.min.replace(tzinfo=timezone.utc)
                lower_id = boundary[0] if boundary else ""
                upper = restored[1] if restored else latest[1]
                upper_id = restored[0] if restored else latest[0]
                cursor.execute(f"""select review_event_id,created_at,review_json->'ewelink_request_budget'
                    from {TABLE} where event_source=%s and chatwoot_conversation_id=%s
                      and (created_at,review_event_id)>(%s,%s)
                      and (created_at,review_event_id)<=(%s,%s)
                      and review_json->'ewelink_request_budget'->>'action' in
                        ('request_completed','snapshot_validation_failed')
                      and review_json->'ewelink_request_budget'->'detail'->>'scope'=%s
                      and review_json->'ewelink_request_budget'->'state'->'scopes'
                          ->(review_json->'ewelink_request_budget'->'detail'->>'scope')->>'category' is not null
                    order by created_at,review_event_id limit 1""",
                    (EVENT_SOURCE, LEDGER_ID, lower, lower_id, upper, upper_id, scope))
                value = project_scope(scope, latest, cursor.fetchone(), restored, now=now)
                if value:
                    projected.append(value)
    return {"contract": CONTRACT, "status": "unavailable" if any(
        row["state"] == "unavailable" for row in projected) else "restored" if projected else "unobserved",
        "observed_at": now.isoformat(), "scopes": projected}


def read_notification_receipt(identity, *, database_url=None, connect=None, environ=None):
    """Read the existing execution notification receipt, preferring confirmation."""
    from modules.telemetry.rootline_input_health import input_health_enabled
    if not input_health_enabled(environ):
        return {}
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    if not isinstance(identity, str) or not re.fullmatch(
            r"ROOTLINE-PROVIDER-[0-9A-F]{32}:(?:unavailable|restored|safety:[0-9a-f]{24})", identity):
        raise ValueError("provider_notification_identity_invalid")
    incident = identity.partition(":")[0]
    connect = connect or connect_bounded_rootline_postgres
    with connect(database_url=database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"""select review_json->'rootline_execution' from {TABLE}
                where event_source='rootline_irrigation_execution'
                  and chatwoot_conversation_id=%s
                  and review_json->'rootline_execution'->>'action'='record_notification_delivery'
                  and review_json->'rootline_execution'->>'notification_identity'=%s
                order by (coalesce(review_json->'rootline_execution'->>'delivery_confirmed','false')='true') desc,
                    (coalesce(review_json->'rootline_execution'->>'delivery_ambiguous','false')='true') desc,
                    created_at desc,review_event_id desc limit 1""", (incident, identity))
            row = cursor.fetchone()
    return row[0] if row else {}
