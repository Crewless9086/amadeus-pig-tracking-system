"""Durable ROOTLINE coordinator state on the existing append-only audit rail."""
from __future__ import annotations

import hashlib
import json
import os

EVENT_SOURCE = "rootline_irrigation_execution"


def rootline_irrigation_execution_store(action, payload):
    if action in {"load_active", "load_off_attempts", "load_zone_containment"}:
        return _load(action, payload)
    body = dict(payload or {})
    execution_id = str(body.get("execution_id") or "").strip()
    if not execution_id:
        return {"success": False, "created": False}
    if action == "claim_before_on":
        return _claim_single_controller(body)
    history_created = None
    if action == "record_completed":
        history_created = _append_history(action, body)
        if history_created is not True:
            return {"success": False, "created": False,
                    "status": "canonical_history_completion_unproven"}
    event_id = _event_id(action, body)
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    event = build_sam_live_stock_review_event(
        {"conversation_id": execution_id}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": action},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id,
        "chatwoot_conversation_id": execution_id,
        "review_json": {"rootline_execution": {
            "action": action, "event_id": event_id, **body}},
        "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event)
    success = status < 400 and result.get("success") is True
    if history_created is None:
        history_created = _append_history(action, body) if success else False
    return {**result, "success": success,
            "created": result.get("created", status < 300),
            "history_event_created": history_created}


def _event_id(action, body):
    execution = str(body.get("execution_id") or "")
    if action == "claim_before_on":
        material = f"{execution}:CLAIM"
    elif action == "claim_notification":
        material = f"{execution}:NOTIFY:{body.get('notification_state')}"
    elif action == "claim_off_attempt":
        material = f"{execution}:OFF:{int(body.get('attempt') or 0)}"
    else:
        material = json.dumps({"action": action, "body": body}, sort_keys=True,
                              separators=(",", ":"), default=str)
    return "ROOTLINE-EXEC-" + hashlib.sha256(material.encode()).hexdigest()[:32].upper()


def _load(action, payload):
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            if action == "load_active":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s order by created_at desc""", (EVENT_SOURCE,))
                terminal = set(); candidates = {}
                for row in cursor.fetchall():
                    item = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    identity = str(item.get("execution_id") or "")
                    if (item.get("action") == "record_completed"
                            or (item.get("action") in {"contain_zone", "record_ambiguous_shutdown",
                                                       "record_claim_recovery"}
                                and item.get("shutdown_verified") is True)):
                        terminal.add(identity)
                    elif item.get("action") in {"mark_active", "claim_before_on"}:
                        candidates.setdefault(identity, item)
                for identity, item in candidates.items():
                    if identity not in terminal:
                        if item.get("action") == "claim_before_on":
                            item = {**item, "state": "claimed_recovery_required"}
                        return item
                return None
            if action == "load_off_attempts":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'execution_id'=%s
                      and review_json->'rootline_execution'->>'action'='record_off_outcome'
                    order by created_at""", (EVENT_SOURCE, str(payload or "")))
                return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            cursor.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'zone_id'=%s
                  and review_json->'rootline_execution'->>'action'='contain_zone'
                order by created_at desc limit 1""", (EVENT_SOURCE, str(payload or "")))
            row = cursor.fetchone()
            return {"contained": True, "evidence": row[0]} if row else {"contained": False}


def _claim_single_controller(body):
    """Atomically serialize B/C claims with one transaction advisory lock."""
    import psycopg
    execution_id = str(body["execution_id"])
    event_id = _event_id("claim_before_on", body)
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "execution_replay"}
            cursor.execute("""select 1
                from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                  and not exists (
                    select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          claim.review_json->'rootline_execution'->>'execution_id'
                      and (terminal.review_json->'rootline_execution'->>'action'='record_completed'
                        or (terminal.review_json->'rootline_execution'->>'action'
                              in ('contain_zone','record_ambiguous_shutdown','record_claim_recovery')
                            and terminal.review_json->'rootline_execution'->>'shutdown_verified'='true')))
                limit 1""", (EVENT_SOURCE, EVENT_SOURCE))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "controller_active"}
            cursor.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id, chatwoot_conversation_id, source_agent, event_source,
                 recommended_action, review_json)
                values (%s,%s,'rootline_backend',%s,'claim_before_on',%s::jsonb)
                on conflict (review_event_id) do nothing""",
                (event_id, execution_id, EVENT_SOURCE, json.dumps({
                    "rootline_execution": {"action": "claim_before_on",
                                           "event_id": event_id, **body}},
                    sort_keys=True, separators=(",", ":"), default=str)))
            return {"success": True, "created": cursor.rowcount == 1,
                    "status": "claimed" if cursor.rowcount == 1 else "execution_replay"}


def _append_history(action, body):
    event_type = {"mark_active": "STARTED", "contain_zone": "AMBIGUOUS",
                  "record_completed": ("COMPLETED" if body.get("objective_satisfied") is True
                                       else "PARTIAL")}.get(action)
    if not event_type:
        return False
    from datetime import datetime, timezone
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event
    event_at = _time(body.get("completed_at") or body.get("claimed_at")) or datetime.now(timezone.utc)
    claimed = _time(body.get("claimed_at")); completed = _time(body.get("completed_at"))
    actual = ((completed-claimed).total_seconds()/60 if claimed and completed else None)
    details = {"execution_id": body.get("execution_id"),
        "start_evidence_id": (body.get("start_evidence") or {}).get("evidence_id") or "Unavailable",
        "maximum_runtime_minutes": body.get("planned_runtime_minutes"),
        "verified_runtime_minutes": actual,
        "shutdown_evidence_id": (body.get("shutdown_evidence") or {}).get("evidence_id") or "Unavailable",
        "shutdown_verified": body.get("shutdown_verified") is True,
        "objective_satisfied": body.get("objective_satisfied") is True,
        "evidence_cutoff": body.get("completed_at") or body.get("claimed_at"),
        "provenance": "rootline_execution_coordinator",
        "classification": event_type.lower()}
    event_id = "ROOTLINE-HISTORY-" + hashlib.sha256(
        f"{body.get('execution_id')}:{event_type}".encode()).hexdigest()[:24].upper()
    event = build_typed_history_event(event_id=event_id,event_at=event_at,event_type=event_type,
        zone_id=str(body.get("zone_id") or ""),details=details,
        planned_minutes=body.get("planned_runtime_minutes"),actual_minutes=actual)
    try:
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select public.rootline_append_typed_irrigation_event(%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (event["irrigation_event_id"],event["event_at"],event["event_type"],event["zone_id"],
                     event["planned_minutes"],event["actual_minutes"],json.dumps(event["details"],
                     sort_keys=True,separators=(",",":"),default=str)))
                row=cursor.fetchone()
                if row and row[0]:
                    return True
                cursor.execute("""select event_at,event_type,zone_id,planned_minutes,
                    actual_minutes,details from public.irrigation_events
                    where irrigation_event_id=%s""", (event["irrigation_event_id"],))
                existing = cursor.fetchone()
                if not existing:
                    return False
                existing_details = (existing[5] if isinstance(existing[5], dict)
                                    else json.loads(existing[5]))
                return (existing[0].isoformat() == event["event_at"]
                        and existing[1] == event["event_type"]
                        and existing[2] == event["zone_id"]
                        and _numeric_equal(existing[3], event["planned_minutes"])
                        and _numeric_equal(existing[4], event["actual_minutes"])
                        and existing_details == event["details"])
    except Exception:
        return False


def _time(value):
    try: return __import__("datetime").datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError): return None


def _numeric_equal(left, right):
    if left is None or right is None:
        return left is None and right is None
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False
