"""Durable ROOTLINE coordinator state on the existing append-only audit rail."""
from __future__ import annotations

import hashlib
import json
import os

EVENT_SOURCE = "rootline_irrigation_execution"


def rootline_irrigation_execution_store(action, payload):
    if action in {"load_active", "load_off_attempts", "load_zone_containment",
                  "load_active_auxiliary", "load_auxiliary_off_attempts",
                  "load_auxiliary_containment", "load_auxiliary_history",
                  "load_auxiliary_physical_outcome"}:
        return _load(action, payload)
    body = dict(payload or {})
    execution_id = str(body.get("execution_id") or "").strip()
    if not execution_id:
        return {"success": False, "created": False}
    if action == "claim_before_on":
        return _claim_single_controller(body)
    if action == "claim_auxiliary_before_on":
        return _claim_single_auxiliary(body)
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
        "review_json": {"rootline_execution": _stored_event_body(action, body, event_id)},
        "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event)
    success = status < 400 and result.get("success") is True
    if history_created is None:
        history_created = _append_history(action, body) if success else False
    return {**result, "success": success,
            "created": result.get("created", status < 300),
            "history_event_created": history_created}


def _stored_event_body(action, body, event_id):
    """Canonical action is store-owned and cannot be shadowed by loaded state."""
    return {**dict(body or {}), "action": action, "event_id": event_id}


def _event_id(action, body):
    execution = str(body.get("execution_id") or "")
    if action in {"claim_before_on", "claim_auxiliary_before_on"}:
        material = f"{execution}:CLAIM"
    elif action == "claim_notification":
        material = f"{execution}:NOTIFY:{body.get('notification_state')}"
    elif action in {"claim_off_attempt", "claim_auxiliary_off_attempt"}:
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
            if action in {"load_active", "load_active_auxiliary"}:
                auxiliary=action=="load_active_auxiliary"
                claim_action="claim_auxiliary_before_on" if auxiliary else "claim_before_on"
                active_action="mark_auxiliary_active" if auxiliary else "mark_active"
                terminal_actions=({"record_auxiliary_completed","contain_auxiliary_device"}
                    if auxiliary else {"record_completed","contain_zone",
                        "record_ambiguous_shutdown","record_claim_recovery"})
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s order by created_at desc""", (EVENT_SOURCE,))
                terminal = set(); candidates = {}
                for row in cursor.fetchall():
                    item = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    identity = str(item.get("execution_id") or "")
                    if item.get("action") in terminal_actions:
                        terminal.add(identity)
                    elif _is_active_candidate(item, active_action, claim_action):
                        candidates.setdefault(identity, item)
                for identity, item in candidates.items():
                    if identity not in terminal:
                        if item.get("action") == claim_action:
                            item = {**item, "state": "claimed_recovery_required"}
                        return item
                return None
            if action in {"load_off_attempts","load_auxiliary_off_attempts"}:
                outcome_action=("record_auxiliary_off_outcome"
                    if action=="load_auxiliary_off_attempts" else "record_off_outcome")
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'execution_id'=%s
                      and review_json->'rootline_execution'->>'action'=%s
                    order by created_at""", (EVENT_SOURCE, str(payload or ""),outcome_action))
                return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action == "load_auxiliary_containment":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                      and review_json->'rootline_execution'->>'action'='contain_auxiliary_device'
                    order by created_at desc limit 1""", (EVENT_SOURCE,str(payload or "")))
                row=cursor.fetchone()
                return {"contained":True,"evidence":row[0]} if row else {"contained":False}
            if action == "load_auxiliary_history":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'action'=
                          'record_auxiliary_completed'
                      and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                    order by created_at""", (EVENT_SOURCE, str(payload or "")))
                return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action == "load_auxiliary_physical_outcome":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'execution_id'=%s
                      and review_json->'rootline_execution'->>'action'=
                          'record_auxiliary_physical_outcome'
                    order by created_at desc limit 1""", (EVENT_SOURCE, str(payload or "")))
                row = cursor.fetchone()
                return row[0] if row and isinstance(row[0], dict) else json.loads(row[0]) if row else None
            cursor.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'zone_id'=%s
                  and review_json->'rootline_execution'->>'action'
                      in ('contain_zone','release_zone_containment')
                order by created_at desc limit 1""", (EVENT_SOURCE, str(payload or "")))
            row = cursor.fetchone()
            if not row or row[0].get("action") == "release_zone_containment":
                return {"contained": False}
            evidence = row[0]
            execution_id = str(evidence.get("execution_id") or "")
            cursor.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'execution_id'=%s
                  and review_json->'rootline_execution'->>'action'
                      in ('record_on_outcome','record_ambiguous_shutdown')
                order by created_at""", (EVENT_SOURCE, execution_id))
            for detail_row in cursor.fetchall():
                detail = detail_row[0]
                if detail.get("action") == "record_on_outcome":
                    evidence["transport_status"] = (detail.get("on_outcome") or {}).get("status")
                elif detail.get("action") == "record_ambiguous_shutdown":
                    evidence["shutdown_verified"] = detail.get("shutdown_verified") is True
                    evidence["shutdown_evidence"] = detail.get("shutdown_evidence")
            return {"contained": True, "evidence": evidence}


def _is_active_candidate(item, active_action, claim_action):
    action = item.get("action") if isinstance(item, dict) else None
    return (action == claim_action
            or (action == active_action and item.get("state") == "Active"))


def _claim_single_controller(body):
    """Atomically serialize B/C claims with one transaction advisory lock."""
    import psycopg
    execution_id = str(body["execution_id"])
    consumption_key = str(body.get("consumption_key") or "").strip()
    if not consumption_key:
        return {"success": False, "created": False,
                "status": "consumption_key_missing"}
    event_id = _event_id("claim_before_on", body)
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "execution_replay"}
            cursor.execute("""select 1
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'action'='claim_before_on'
                  and review_json->'rootline_execution'->>'consumption_key'=%s
                limit 1""", (EVENT_SOURCE, consumption_key))
            if cursor.fetchone():
                return {"success": True, "created": False,
                        "status": "eligibility_already_consumed"}
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


def _claim_single_auxiliary(body):
    """Atomically consume one auxiliary artifact without blocking its B/C zone."""
    import psycopg
    execution_id=str(body["execution_id"]);consumption_key=str(body.get("consumption_key") or "")
    auxiliary_id=str(body.get("auxiliary_device_id") or "")
    if not consumption_key or not auxiliary_id:
        return {"success":False,"created":False,"status":"auxiliary_claim_incomplete"}
    event_id=_event_id("claim_auxiliary_before_on",body)
    with psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where event_source=%s and (review_event_id=%s or
                  (review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                   and review_json->'rootline_execution'->>'consumption_key'=%s)) limit 1""",
                (EVENT_SOURCE,event_id,consumption_key))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"eligibility_already_consumed"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                  and not exists (select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          claim.review_json->'rootline_execution'->>'execution_id'
                      and terminal.review_json->'rootline_execution'->>'action'
                          in ('record_auxiliary_completed','contain_auxiliary_device')) limit 1""",
                (EVENT_SOURCE,EVENT_SOURCE))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"auxiliary_active"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                  and review_json->'rootline_execution'->>'action'='contain_auxiliary_device' limit 1""",
                (EVENT_SOURCE,auxiliary_id))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"auxiliary_contained"}
            cursor.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,source_agent,event_source,
                 recommended_action,review_json)
                values (%s,%s,'rootline_backend',%s,'claim_auxiliary_before_on',%s::jsonb)
                on conflict (review_event_id) do nothing""",(event_id,execution_id,EVENT_SOURCE,
                json.dumps({"rootline_execution":{"action":"claim_auxiliary_before_on",
                    "event_id":event_id,**body}},sort_keys=True,separators=(",",":"),default=str)))
            return {"success":True,"created":cursor.rowcount==1,
                "status":"claimed" if cursor.rowcount==1 else "execution_replay"}


def _append_history(action, body):
    event_type = {"mark_active": "STARTED", "contain_zone": "AMBIGUOUS",
                  "record_completed": ("COMPLETED" if body.get("objective_satisfied") is True
                                       else "PARTIAL")}.get(action)
    if not event_type:
        return False
    from datetime import datetime, timezone
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event
    event_at = _time(body.get("completed_at") or body.get("claimed_at")) or datetime.now(timezone.utc)
    actual = _verified_runtime(body)
    details = {"execution_id": body.get("execution_id"),
        "start_evidence_id": (body.get("start_evidence") or {}).get("evidence_id") or "Unavailable",
        "maximum_runtime_minutes": body.get("planned_runtime_minutes"),
        "verified_runtime_minutes": actual,
        "shutdown_evidence_id": (body.get("shutdown_evidence") or {}).get("evidence_id") or "Unavailable",
        "shutdown_verified": body.get("shutdown_verified") is True,
        "objective_satisfied": body.get("objective_satisfied") is True,
        "evidence_cutoff": body.get("completed_at") or body.get("claimed_at"),
        "shutdown_observed_at": body.get("completed_at"),
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
                cursor.execute("""select public.rootline_append_typed_irrigation_event(
                    %s::text,%s::timestamptz,%s::text,%s::text,
                    %s::numeric,%s::numeric,%s::jsonb)""",
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
        from decimal import Decimal, ROUND_HALF_UP
        scale = Decimal("0.01")
        return (Decimal(str(left)).quantize(scale, rounding=ROUND_HALF_UP)
                == Decimal(str(right)).quantize(scale, rounding=ROUND_HALF_UP))
    except (TypeError, ValueError):
        return False


def _verified_runtime(body):
    evidence = body.get("objective_evidence")
    if not isinstance(evidence, dict):
        return None
    value = evidence.get("verified_runtime_minutes")
    try:
        runtime = float(value)
        maximum = float(body.get("planned_runtime_minutes") or 0)
    except (TypeError, ValueError):
        return None
    return runtime if 0 <= runtime <= maximum else None
