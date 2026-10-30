"""Durable ROOTLINE coordinator state on the existing append-only audit rail."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import nullcontext

EVENT_SOURCE = "rootline_irrigation_execution"


class RootlineExecutionStoreUnavailable(RuntimeError):
    """Durable execution truth could not be loaded within its read deadline."""

    def __init__(self, action):
        super().__init__("rootline_execution_store_unavailable:" + str(action))
        self.action = str(action)


def rootline_irrigation_execution_store(action, payload):
    if action in {"load_active", "load_off_attempts", "load_zone_containment",
                  "load_active_auxiliary", "load_active_auxiliaries", "load_auxiliary_off_attempts",
                  "load_auxiliary_containment", "load_auxiliary_history",
                  "load_auxiliary_physical_outcome", "load_job_events",
                  "load_active_borehole", "load_borehole_off_attempts", "load_eskom_events"}:
        return _load(action, payload)
    body = dict(payload or {})
    if action in {"dispatch_auxiliary_on_edge", "dispatch_borehole_on_edge"}:
        return _dispatch_managed_on_edge(body, borehole=action == "dispatch_borehole_on_edge")
    if action in {"claim_auxiliary_off_attempt", "claim_borehole_off_attempt",
                  "mark_auxiliary_active", "mark_borehole_active",
                  "contain_auxiliary_device", "contain_borehole",
                  "record_auxiliary_completed", "record_auxiliary_control_pulse_stopped",
                  "record_borehole_completed"}:
        return _guarded_managed_transition(action, body)
    if action == "reconcile_unstarted_auxiliary":
        return _reconcile_unstarted_auxiliary(body)
    if action == "dispatch_eskom_command_edge":
        return _dispatch_eskom_command_edge(body)
    execution_id = str(body.get("execution_id") or "").strip()
    if not execution_id:
        return {"success": False, "created": False}
    if action == "claim_before_on":
        return _bounded_claim(action, _claim_irrigation_output, body)
    if action == "claim_auxiliary_before_on":
        return _bounded_claim(action, _claim_single_auxiliary, body)
    if action == "claim_borehole_before_on":
        return _bounded_claim(action, _claim_borehole_material_load, body)
    if action == "claim_eskom_before_command":
        return _bounded_claim(action, _claim_eskom_command, body)
    if action == "record_eskom_completed":
        return _complete_eskom_command(body)
    if action == "record_completed":
        return _record_parent_terminal_atomic(action, body)
    if action == "record_job_resolution" and body.get("resolution") == "Cancelled":
        return _record_parent_terminal_atomic(action, body)
    history_created = None
    event_id = _event_id(action, body)
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    event = build_sam_live_stock_review_event(
        {"conversation_id": execution_id}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": action},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id,
        "chatwoot_conversation_id": execution_id,
        "review_json": {"rootline_execution": _stored_event_body(action, body, event_id)},
        "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    def connect_for_event():
        connection=connect_bounded_rootline_postgres(
            database_url=os.environ.get("DATABASE_URL"),read_only=False)
        if action in {"mark_active","mark_stopping","record_completed","contain_zone",
                "record_ambiguous_shutdown","record_claim_recovery"}:
            # Serialize parent state transitions with an injection claim's final
            # active-parent check. Lock order is identical everywhere.
            connection.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            connection.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
        if action in {"record_eskom_completed", "record_eskom_command_outcome"}:
            connection.execute("select pg_advisory_xact_lock(%s)",(1874320914,))
        return connection
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=connect_for_event)
    if status >= 500 and str(result.get("error_type") or "") in {
            "OperationalError", "ConnectionTimeout", "PoolTimeout",
            "QueryCanceled", "QueryCanceledError", "LockNotAvailable"}:
        raise RootlineExecutionStoreUnavailable(action)
    success = status < 400 and result.get("success") is True
    if history_created is None:
        history_created = _append_history(action, body) if success else False
    return {**result, "success": success,
            "created": result.get("created", status < 300),
            "history_event_created": history_created}


class _AtomicTerminalWriteFailed(RuntimeError):
    pass


def _record_parent_terminal_atomic(action, body):
    """Serialize cancellation with BOTH completion rails, not just its audit row."""
    from modules.oom_sakkie.bounded_postgres_read import (
        connect_bounded_rootline_postgres, is_database_unavailable,
    )
    body = dict(body)
    controller = body.pop("_current_controller", None)
    try:
        with connect_bounded_rootline_postgres(
                database_url=os.environ.get("DATABASE_URL"), read_only=False) as connection:
            # Same order as parent transitions and auxiliary final-edge checks.
            connection.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            connection.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
            now = connection.execute("select clock_timestamp()").fetchone()[0]
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'rootline_execution',created_at
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and (review_json->'rootline_execution'->>'job_id'=%s
                           or (review_json->'rootline_execution'->>'action'='record_completed'
                               and review_json->'rootline_execution'->>'execution_id'=%s))
                    order by created_at,review_event_id""",
                    (EVENT_SOURCE, body.get("job_id"), body.get("execution_id")))
                rows = cursor.fetchall()
            events = [row[0] for row in rows]
            if action == "record_job_resolution":
                from modules.telemetry.rootline_parent_job_resolution import (
                    _recorded_cancellation, build_contained_parent_cancellation,
                )
                prior = _recorded_cancellation(events, body, expected=body)
                if prior is not None:
                    return {"success": True, "created": False, "resolution": prior,
                            "history_event_created": False}
                parent = _locked_contained_parent(connection, body, rows, now)
                rebuilt = build_contained_parent_cancellation(parent=parent,
                    controller=controller, authorization={
                        "mission_id": body.get("mission_id"),
                        "decision": "cancel_unverified_remainder",
                        "owner_principal": body.get("owner_principal"),
                        "job_id": body.get("job_id"), "job_sha256": body.get("job_sha256")},
                    now=now)
                if body != rebuilt:
                    raise ValueError("contained_parent_cancellation_preimage_changed")
                result = _write_terminal_review(connection, action, rebuilt)
                return {**result, "history_event_created": False}

            # A duplicate callback may still be acknowledged after the remainder
            # was cancelled, but must not repair/create any missing history then.
            existing = _read_terminal_review(connection, action, body)
            if existing is not None:
                if (existing != _stored_event_body(action, body, _event_id(action, body))
                        or not _append_history(action, body, connection=connection, append=False)):
                    raise _AtomicTerminalWriteFailed("canonical_history_completion_unproven")
                return {"success": True, "created": False, "history_event_created": False}
            if any(row.get("action") == "record_completed"
                   and row.get("execution_id") == body.get("execution_id") for row in events):
                raise ValueError("canonical_completion_history_conflict")
            if any(row.get("action") == "record_job_resolution"
                   and row.get("resolution") == "Cancelled" for row in events):
                raise ValueError("cancelled_parent_completion_refused")
            if not _append_history(action, body, connection=connection):
                raise _AtomicTerminalWriteFailed("canonical_history_completion_unproven")
            result = _write_terminal_review(connection, action, body)
            return {**result, "history_event_created": True}
    except _AtomicTerminalWriteFailed as exc:
        # This is outside the connection context: both rails have rolled back.
        return {"success": False, "created": False, "status": str(exc),
                "history_event_created": False}
    except Exception as exc:
        if is_database_unavailable(exc):
            raise RootlineExecutionStoreUnavailable(action) from exc
        raise


def _locked_contained_parent(connection, body, rows, now):
    from modules.telemetry.rootline_irrigation_history import (
        _attach_parent_jobs, project_canonical_irrigation_history,
    )
    events = [row[0] for row in rows]
    # A new active/stopping transition after containment cannot be erased by
    # the contained-parent projector's deliberate exclusion of old claims.
    latest = {}
    transitions = {"claim_before_on", "mark_active", "mark_stopping", "record_completed",
                   "contain_zone", "record_ambiguous_shutdown", "record_claim_recovery"}
    for row in events:
        if row.get("action") in transitions:
            latest[row.get("execution_id")] = row
    if any(row.get("action") in {"claim_before_on", "mark_active", "mark_stopping"}
           for row in latest.values()):
        raise ValueError("contained_parent_execution_changed")
    executions = sorted({str(row.get("execution_id")) for row in events if row.get("execution_id")})
    with connection.cursor() as cursor:
        cursor.execute("""select irrigation_event_id,event_at,event_type,zone_id,
            planned_minutes,actual_minutes,details,source_id,actor,created_at
            from public.irrigation_events
            where details->>'execution_id'=any(%s)
            order by event_at,irrigation_event_id""", (executions,))
        history_rows = cursor.fetchall()
    completed = {row.get("execution_id") for row in events if row.get("action") == "record_completed"}
    if any(row[2] in {"PARTIAL", "COMPLETED"}
           and row[6].get("execution_id") not in completed for row in history_rows):
        # Legacy history-first completion failures remain evidence, not permission
        # to cancel their possibly credited runtime as unverified remainder.
        raise ValueError("contained_parent_completion_history_unreconciled")
    history = project_canonical_irrigation_history(history_rows, snapshot_cutoff=now)
    _attach_parent_jobs(history, events, canonical_ordered=True)
    parents = ((history.get("zones") or {}).get(body.get("zone_id")) or {}).get(
        "contained_parent_jobs") or []
    matches = [parent for parent in parents if
        (parent.get("job") or {}).get("job_id") == body.get("job_id")
        and (parent.get("job") or {}).get("job_sha256") == body.get("job_sha256")]
    if len(matches) != 1:
        raise ValueError("exact_contained_parent_not_current")
    return matches[0]


def _read_terminal_review(connection, action, body):
    with connection.cursor() as cursor:
        cursor.execute("""select review_json->'rootline_execution'
            from public.sam_live_stock_conversation_review_events
            where review_event_id=%s and event_source=%s""", (_event_id(action, body), EVENT_SOURCE))
        row = cursor.fetchone()
    return row[0] if row else None


def _write_terminal_review(connection, action, body):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    execution_id = str(body.get("execution_id") or "")
    event_id = _event_id(action, body)
    event = build_sam_live_stock_review_event(
        {"conversation_id": execution_id}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": action},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id, "chatwoot_conversation_id": execution_id,
        "review_json": {"rootline_execution": _stored_event_body(action, body, event_id)},
        "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    # The canonical writer borrows this connection; only the outer context may
    # commit/rollback. Its caught failures must become an outer rollback.
    # now() would retain the transaction's pre-lock start time and could place
    # a waiting writer before the state it just revalidated.
    recorded_at = connection.execute("select clock_timestamp()").fetchone()[0]
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: nullcontext(connection), created_at=recorded_at)
    if status >= 400 or result.get("success") is not True:
        raise _AtomicTerminalWriteFailed("canonical_terminal_audit_write_unproven")
    stored = _read_terminal_review(connection, action, body)
    if stored != _stored_event_body(action, body, event_id):
        raise _AtomicTerminalWriteFailed("canonical_terminal_audit_readback_mismatch")
    return {**result, "success": True, "resolution": stored}


def _stored_event_body(action, body, event_id):
    """Canonical action is store-owned and cannot be shadowed by loaded state."""
    return {**dict(body or {}), "action": action, "event_id": event_id}


def _event_id(action, body):
    execution = str(body.get("execution_id") or "")
    if action in {"claim_before_on", "claim_auxiliary_before_on", "claim_borehole_before_on", "claim_eskom_before_command"}:
        material = f"{execution}:CLAIM"
    elif action == "claim_notification":
        material = f"{execution}:NOTIFY:{body.get('notification_state')}"
    elif action == "record_fertilizer_sequence_completed":
        material = f"{execution}:CONTROLLER-SEQUENCE-COMPLETED"
    elif action == "record_eskom_completed":
        material = f"{execution}:ESKOM-COMPLETED"
    elif action in {"claim_auxiliary_dispatch", "claim_borehole_dispatch"}:
        material = f"{execution}:MANAGED-DISPATCH"
    elif action == "reconcile_unstarted_auxiliary":
        material = f"{execution}:UNSTARTED-RECONCILIATION"
    elif action == "claim_eskom_dispatch":
        material = f"{execution}:ESKOM-DISPATCH"
    elif (action == "record_job_resolution"
            and body.get("contract_version") == "rootline_parent_job_terminal_resolution.v1"
            and body.get("resolution") == "Cancelled"):
        material = f"{body.get('job_id')}:{body.get('job_sha256')}:CANCELLED"
    elif (action == "record_job_resolution" and body.get("resolution") == "Deferred"
            and body.get("terminal") is True):
        material = f"{body.get('job_id')}:{body.get('job_sha256')}:DEFERRED"
    elif action in {"claim_off_attempt", "claim_auxiliary_off_attempt",
                    "claim_borehole_off_attempt"}:
        material = f"{execution}:OFF:{int(body.get('attempt') or 0)}"
    else:
        material = json.dumps({"action": action, "body": body}, sort_keys=True,
                              separators=(",", ":"), default=str)
    return "ROOTLINE-EXEC-" + hashlib.sha256(material.encode()).hexdigest()[:32].upper()


def _load(action, payload):
    from modules.oom_sakkie.bounded_postgres_read import (
        connect_bounded_rootline_postgres, is_database_unavailable,
    )
    try:
      with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL")) as connection:
        with connection.cursor() as cursor:
            if action == "load_eskom_events":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'rootline_execution'->>'device_key'=%s
                      and review_json->'rootline_execution'->>'action' in
                          ('claim_eskom_before_command','claim_eskom_dispatch','record_eskom_command_outcome','record_eskom_completed')
                    order by created_at,review_event_id""", (EVENT_SOURCE,str(payload or "")))
                return [row[0] if isinstance(row[0],dict) else json.loads(row[0]) for row in cursor.fetchall()]
            if action in {"load_active", "load_active_auxiliary", "load_active_auxiliaries", "load_active_borehole"}:
                borehole=action=="load_active_borehole"
                auxiliary=action in {"load_active_auxiliary", "load_active_auxiliaries"}
                claim_action=("claim_borehole_before_on" if borehole else
                    "claim_auxiliary_before_on" if auxiliary else "claim_before_on")
                active_action=("mark_borehole_active" if borehole else
                    "mark_auxiliary_active" if auxiliary else "mark_active")
                terminal_actions=({"record_borehole_completed","contain_borehole"}
                    if borehole else {"record_auxiliary_completed",
                    "record_auxiliary_control_pulse_stopped","contain_auxiliary_device"}
                    if auxiliary else {"record_completed","contain_zone",
                        "record_ambiguous_shutdown","record_claim_recovery"})
                relevant_actions = terminal_actions | {claim_action, active_action}
                if not auxiliary and not borehole:
                    relevant_actions.add("mark_stopping")
                # Keep malformed and legacy JSON-string envelopes for the existing
                # reducer: filtering them out could turn a failed read into idle.
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and (jsonb_typeof(review_json->'rootline_execution')
                               is distinct from 'object'
                           or jsonb_typeof(review_json->'rootline_execution'->'action')
                               is distinct from 'string'
                           or review_json->'rootline_execution'->>'action'=any(%s))
                    order by created_at desc""", (EVENT_SOURCE, sorted(relevant_actions)))
                terminal = set(); candidates = {}
                for row in cursor.fetchall():
                    item = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    identity = str(item.get("execution_id") or "")
                    if item.get("action") in terminal_actions:
                        if _terminal_closes_active(item, auxiliary=auxiliary, borehole=borehole):
                            terminal.add(identity)
                    elif _recoverable_stopping_candidate(item, auxiliary=auxiliary,
                                                          borehole=borehole):
                        candidates.setdefault(identity,item)
                    elif _is_active_candidate(item, active_action, claim_action):
                        candidates.setdefault(identity, item)
                active = []
                for identity, item in candidates.items():
                    if identity not in terminal:
                        if auxiliary and payload is not None and item.get("auxiliary_device_id") != payload:
                            continue
                        if item.get("action") == claim_action:
                            item = {**item, "state": "claimed_recovery_required"}
                        active.append(item)
                if action == "load_active_auxiliaries":
                    return active
                if auxiliary and len(active) > 1:
                    # A caller without an exact device must never accidentally
                    # supervise a sibling when both independently own work.
                    raise RootlineExecutionStoreUnavailable("auxiliary_device_selector_required")
                return active[0] if active else None
            if action == "load_job_events":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'job_id'=%s
                      and review_json->'rootline_execution'->>'action'
                          in ('claim_before_on','mark_active','record_completed','record_job_resolution')
                    order by created_at,review_event_id""", (EVENT_SOURCE, str(payload or "")))
                return [row[0] if isinstance(row[0],dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action in {"load_off_attempts","load_auxiliary_off_attempts","load_borehole_off_attempts"}:
                outcome_action=("record_borehole_off_outcome" if action=="load_borehole_off_attempts"
                    else "record_auxiliary_off_outcome" if action=="load_auxiliary_off_attempts"
                    else "record_off_outcome")
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'execution_id'=%s
                      and review_json->'rootline_execution'->>'action'=%s
                    order by created_at""", (EVENT_SOURCE, str(payload or ""),outcome_action))
                return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action == "load_auxiliary_containment":
                return _auxiliary_containment_state(cursor, str(payload or ""))
            if action == "load_auxiliary_history":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'action' in (
                          'record_auxiliary_completed','claim_auxiliary_before_on',
                          'mark_auxiliary_active','contain_auxiliary_device')
                      and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                    order by created_at,review_event_id""", (EVENT_SOURCE, str(payload or "")))
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
            cursor.execute("""select created_at,review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'zone_id'=%s
                  and review_json->'rootline_execution'->>'action'
                      in ('contain_zone','release_zone_containment')
                order by created_at desc limit 1""", (EVENT_SOURCE, str(payload or "")))
            row = cursor.fetchone()
            if not row or row[1].get("action") == "release_zone_containment":
                return {"contained": False}
            contained_at, evidence = row
            execution_id = str(evidence.get("execution_id") or "")
            cursor.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'execution_id'=%s
                  and review_json->'rootline_execution'->>'action'
                      in ('record_on_outcome','record_ambiguous_shutdown',
                          'record_completed','record_claim_recovery')
                  and created_at>%s
                order by created_at""", (EVENT_SOURCE, execution_id, contained_at))
            for detail_row in cursor.fetchall():
                detail = detail_row[0]
                if _verified_terminal_containment_resolution(evidence, detail):
                    return {"contained": False, "resolution_evidence": detail}
                if detail.get("action") == "record_on_outcome":
                    evidence["transport_status"] = (detail.get("on_outcome") or {}).get("status")
                elif detail.get("action") == "record_ambiguous_shutdown":
                    evidence["shutdown_verified"] = detail.get("shutdown_verified") is True
                    evidence["shutdown_evidence"] = detail.get("shutdown_evidence")
            return {"contained": True, "evidence": evidence}
    except Exception as exc:
      if is_database_unavailable(exc):
        raise RootlineExecutionStoreUnavailable(action) from exc
      raise


def _verified_terminal_containment_resolution(containment, terminal):
    """Accept only later canonical OFF proof for the exact contained execution."""
    if not isinstance(containment, dict) or not isinstance(terminal, dict):
        return False
    if (terminal.get("action") not in {"record_completed", "record_claim_recovery"}
            or terminal.get("execution_id") != containment.get("execution_id")
            or terminal.get("zone_id") != containment.get("zone_id")
            or terminal.get("shutdown_verified") is not True):
        return False
    shutdown = terminal.get("shutdown_evidence")
    return (isinstance(shutdown, dict)
            and shutdown.get("authoritative") is True
            and shutdown.get("state") == "OFF")


def _terminal_closes_active(item, *, auxiliary=False, borehole=False):
    action = str(item.get("action") or "") if isinstance(item, dict) else ""
    if borehole:
        # Containment records the unresolved safety incident; it cannot prove
        # that the physical pump and water flow stopped.  Only the strict,
        # execution-bound three-domain completion contract releases a borehole
        # claim.
        return _verified_borehole_completion(item)
    if auxiliary:
        return (action in {"record_auxiliary_completed",
                "record_auxiliary_control_pulse_stopped"}
            or (action == "contain_auxiliary_device"
                and item.get("shutdown_verified") is True))
    if action == "record_completed":
        return True
    if action in {"contain_zone", "record_ambiguous_shutdown", "record_claim_recovery"}:
        return item.get("shutdown_verified") is True
    return False


_EVIDENCE_ID_TRIM_CODEPOINTS = (
    9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
    8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
    8232, 8233, 8239, 8287, 12288,
)
_EVIDENCE_ID_TRIM_CHARS = "".join(chr(value) for value in _EVIDENCE_ID_TRIM_CODEPOINTS)
_EVIDENCE_ID_TRIM_SQL = "(" + "||".join(
    f"chr({value})" for value in _EVIDENCE_ID_TRIM_CODEPOINTS) + ")"


def _normalize_evidence_id(value):
    """Apply the explicit evidence-ID boundary contract shared with PostgreSQL."""
    return str(value or "").strip(_EVIDENCE_ID_TRIM_CHARS)


def _verified_borehole_completion(item):
    """Require execution-bound canonical and authoritative provider final OFF."""
    if not isinstance(item, dict) or item.get("action") != "record_borehole_completed":
        return False
    execution_id = str(item.get("execution_id") or "")
    canonical = item.get("canonical_completion_evidence") or {}
    provider = item.get("provider_final_off_evidence") or {}
    physical = item.get("physical_completion_evidence") or {}
    provider_mode = item.get("operational_proof") == "provider_app_on_to_off"
    evidence = (canonical, provider) if provider_mode else (canonical, provider, physical)
    evidence_ids = tuple(_normalize_evidence_id(row.get("evidence_id"))
        for row in evidence)
    identities_match = bool(execution_id) and all(
        str(row.get("execution_id") or "") == execution_id
        for row in evidence)
    evidence_domains_distinct = (all(evidence_ids)
        and len(set(evidence_ids)) == len(evidence_ids))
    return (item.get("shutdown_verified") is True and identities_match
        and evidence_domains_distinct
        and canonical.get("final_state") == "OFF"
        and provider.get("authoritative") is True and provider.get("state") == "OFF"
        and ((provider_mode
              and (item.get("provider_start_evidence") or {}).get("authoritative") is True
              and (item.get("provider_start_evidence") or {}).get("state") == "ON")
             or (not provider_mode and physical.get("pump_stopped") is True
                 and physical.get("water_flow_stopped") is True)))


def _is_active_candidate(item, active_action, claim_action):
    action = item.get("action") if isinstance(item, dict) else None
    return (action == claim_action
            or (action == active_action and item.get("state") == "Active"))


def _recoverable_stopping_candidate(item, *, auxiliary=False, borehole=False):
    """A zone stop belongs only to the B/C loader, never a managed device."""
    return (not auxiliary and not borehole and isinstance(item, dict)
            and item.get("action") == "mark_stopping")


def _bounded_claim(action, claim, body):
    from modules.oom_sakkie.bounded_postgres_read import is_database_unavailable
    try:
        return claim(body)
    except Exception as exc:
        if is_database_unavailable(exc):
            raise RootlineExecutionStoreUnavailable(action) from exc
        raise


def _claim_eskom_command(body):
    """Consume one grid transition; an unresolved claim forbids another one."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    key=str(body.get("device_key") or ""); device=str(body.get("device_id") or "")
    decision=body.get("decision") or {}; previous=body.get("previous_readback") or {}
    if (key != "ifttt_smartlife:smartlife_owner_account:"+device+":1"
            or not device or body.get("desired_state") not in {"ON","OFF"}
            or decision.get("fresh") is not True
            or decision.get("eskom_requested_state") != body.get("desired_state")
            or previous.get("authoritative") is not True or previous.get("device_id") != device
            or previous.get("state") == body.get("desired_state")):
        return {"success":False,"created":False,"status":"eskom_claim_invalid"}
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
            read_only=False) as connection, connection.cursor() as cursor:
        cursor.execute("select pg_advisory_xact_lock(%s)",(1874320914,))
        cursor.execute("""select 1 from app_private.rootline_device_registry r
            where r.device_key=%s and r.evidence_digest=%s
              and r.commissioning_stage='standing_active' and not r.authority_revoked
              and exists(select 1 from app_private.rootline_standing_authorities a
                where a.standing_authority_id=r.standing_authority_id
                  and a.version=r.standing_authority_version and a.active and not a.revoked
                  and not exists(select 1 from app_private.rootline_authority_events e
                    where e.standing_authority_id=a.standing_authority_id and e.version=a.version
                      and e.event_type in ('revoked','superseded')))""",(key,body.get("baseline_sha256")))
        if not cursor.fetchone():
            return {"success":True,"created":False,"status":"eskom_canonical_authority_changed"}
        cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events c
            where c.event_source=%s and c.review_json->'rootline_execution'->>'device_key'=%s
              and c.review_json->'rootline_execution'->>'action'='claim_eskom_before_command'
              and not exists(select 1 from public.sam_live_stock_conversation_review_events t
                where t.event_source=%s and t.review_json->'rootline_execution'->>'action'='record_eskom_completed'
                  and t.review_json->'rootline_execution'->>'execution_id'=c.review_json->'rootline_execution'->>'execution_id')
            limit 1""",(EVENT_SOURCE,key,EVENT_SOURCE))
        if cursor.fetchone():
            return {"success":True,"created":False,"status":"eskom_pending_command"}
        cursor.execute("""select review_json->'rootline_execution'->>'execution_id'
            from public.sam_live_stock_conversation_review_events
            where event_source=%s and review_json->'rootline_execution'->>'device_key'=%s
              and review_json->'rootline_execution'->>'action'='record_eskom_completed'
            order by created_at desc,review_event_id desc limit 1""",(EVENT_SOURCE,key))
        latest=cursor.fetchone()
        if (latest[0] if latest else None)!=body.get("expected_transition_id"):
            return {"success":True,"created":False,"status":"eskom_observation_version_changed"}
        event_id=_event_id("claim_eskom_before_command",body)
        cursor.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,source_agent,event_source,recommended_action,review_json)
            values(%s,%s,'rootline_backend',%s,'claim_eskom_before_command',%s::jsonb)
            on conflict(review_event_id) do nothing""",(event_id,body["execution_id"],EVENT_SOURCE,
                json.dumps({"rootline_execution":_stored_event_body("claim_eskom_before_command",body,event_id)},
                    sort_keys=True,separators=(",",":"),default=str)))
        return {"success":True,"created":cursor.rowcount==1}


def _eskom_locked_events(connection, body):
    connection.execute("select pg_advisory_xact_lock(%s)",(1874320914,))
    return [row[0] for row in connection.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s and review_json->'rootline_execution'->>'device_key'=%s
        order by created_at,review_event_id""",(EVENT_SOURCE,body.get("device_key"))).fetchall()]


def _dispatch_eskom_command_edge(body):
    """Keep the exclusive transition fence until the provider has returned.

    The claim committed earlier is never undone. If this transaction loses its
    outcome, no later tick may resend or complete that unresolved claim.
    """
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_energy_policy import managed_energy_decision
    from datetime import datetime, timedelta
    body=dict(body); dispatch=body.pop("dispatch",None)
    if not callable(dispatch):
        return {"success":False,"dispatched":False}
    # Commit a single-use dispatch reservation before entering the provider
    # transaction. An interrupted sender cannot reopen its edge on rollback.
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
            read_only=False) as connection:
        rows=_eskom_locked_events(connection,body)
        matching=[row for row in rows if row.get("execution_id")==body.get("execution_id")]
        if (not any(row.get("action")=="claim_eskom_before_command" for row in matching)
                or any(row.get("action") in {"claim_eskom_dispatch","record_eskom_command_outcome",
                    "record_eskom_completed"} for row in matching)):
            return {"success":False,"dispatched":False,"status":"eskom_dispatch_already_consumed"}
        _write_terminal_review(connection,"claim_eskom_dispatch",{
            "execution_id":body.get("execution_id"),"device_key":body.get("device_key")})
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
            read_only=False) as connection:
        rows=_eskom_locked_events(connection,body)
        matching=[row for row in rows if row.get("execution_id")==body.get("execution_id")]
        claim=next((row for row in matching if row.get("action")=="claim_eskom_before_command"),None)
        if (claim is None or any(row.get("action") in {"record_eskom_command_outcome",
                "record_eskom_completed"} for row in matching)
                or any(claim.get(key)!=value for key,value in body.items())):
            return {"success":False,"dispatched":False,"status":"eskom_edge_claim_changed"}
        current=connection.execute("select clock_timestamp()").fetchone()[0]
        decision=managed_energy_decision(body.get("power_evidence"),now=current)
        try:
            observed=datetime.fromisoformat(body["previous_readback"]["retrieved_at"].replace("Z","+00:00"))
            fresh=timedelta(0)<=current-observed<=timedelta(minutes=2)
        except (KeyError,TypeError,ValueError): fresh=False
        if not fresh or not decision["fresh"] or decision["eskom_requested_state"]!=body.get("desired_state"):
            return {"success":False,"dispatched":False,"status":"eskom_edge_evidence_stale"}
        authority=connection.execute("""select 1 from app_private.rootline_device_registry r
            where r.device_key=%s and r.evidence_digest=%s
              and r.commissioning_stage='standing_active' and not r.authority_revoked
              and exists(select 1 from app_private.rootline_standing_authorities a
                where a.standing_authority_id=r.standing_authority_id
                  and a.version=r.standing_authority_version and a.active and not a.revoked
                  and not exists(select 1 from app_private.rootline_authority_events e
                    where e.standing_authority_id=a.standing_authority_id and e.version=a.version
                      and e.event_type in ('revoked','superseded')))""",
            (body.get("device_key"),body.get("baseline_sha256"))).fetchone()
        if not authority:
            return {"success":False,"dispatched":False,"status":"eskom_edge_authority_changed"}
        outcome=dispatch()
        returned_at=connection.execute("select clock_timestamp()").fetchone()[0]
        saved=_write_terminal_review(connection,"record_eskom_command_outcome",{
            **body,"outcome":outcome,"dispatch_returned_at":returned_at.isoformat()})
        return {**saved,"dispatched":outcome.get("command_not_sent") is not True}


def _complete_eskom_command(body):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from datetime import datetime, timedelta
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
            read_only=False) as connection:
        rows=_eskom_locked_events(connection,body)
        matching=[row for row in rows if row.get("execution_id")==body.get("execution_id")]
        claim=next((row for row in matching if row.get("action")=="claim_eskom_before_command"),None)
        outcome=next((row for row in matching if row.get("action")=="record_eskom_command_outcome"),None)
        readback=body.get("readback") or {}
        try:
            observed=datetime.fromisoformat(readback["retrieved_at"].replace("Z","+00:00"))
            returned=datetime.fromisoformat(outcome["dispatch_returned_at"].replace("Z","+00:00"))
            current=connection.execute("select clock_timestamp()").fetchone()[0]
            current_after_sender=returned<=observed<=current and current-observed<=timedelta(minutes=2)
        except (KeyError,TypeError,ValueError): current_after_sender=False
        if (not claim or not outcome or (outcome.get("outcome") or {}).get("command_not_sent") is True
                or not current_after_sender
                or readback.get("authoritative") is not True or readback.get("device_id")!=claim.get("device_id")
                or readback.get("state")!=claim.get("desired_state")):
            return {"success":False,"created":False,"status":"eskom_sender_outcome_unproven"}
        return _write_terminal_review(connection,"record_eskom_completed",body)


def _claim_irrigation_output(body):
    """Atomically serialize irrigation and consume one governed output authority."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution_id = str(body["execution_id"])
    consumption_key = str(body.get("consumption_key") or "").strip()
    zone_id = str(body.get("zone_id") or "").strip()
    operating_date = str(body.get("operating_date") or "").strip()
    eligibility_id = str(body.get("eligibility_id") or "").strip()
    eligibility_sha256 = str(body.get("eligibility_sha256") or "").strip()
    try:
        from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract
        commissioned_irrigation_contract(zone_id)
    except ValueError:
        return {"success": False, "created": False,
                "status": "irrigation_output_not_commissioned"}
    if (not consumption_key or not _valid_iso_date(operating_date) or not eligibility_id
            or len(eligibility_sha256) != 64):
        return {"success": False, "created": False,
                "status": "daily_dispatch_identity_incomplete"}
    event_id = _event_id("claim_before_on", body)
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "execution_replay"}
            if body.get("job_id"):
                cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'job_id'=%s
                      and review_json->'rootline_execution'->>'action'='record_job_resolution'
                      and review_json->'rootline_execution'->>'resolution'='Cancelled'
                    limit 1""", (EVENT_SOURCE, str(body["job_id"])))
                if cursor.fetchone():
                    return {"success": True, "created": False, "status": "parent_job_cancelled"}
            cursor.execute("""select 1
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'action'='claim_before_on'
                  and review_json->'rootline_execution'->>'consumption_key'=%s
                limit 1""", (EVENT_SOURCE, consumption_key))
            if cursor.fetchone():
                return {"success": True, "created": False,
                        "status": "eligibility_already_consumed"}
            blocked = _daily_dispatch_blocker(cursor, execution_id=execution_id,
                eligibility_id=eligibility_id, eligibility_sha256=eligibility_sha256,
                zone_id=zone_id, operating_date=operating_date,
                job_id=str(body.get("job_id") or ""),
                segment_number=int(body.get("segment_number") or 0))
            if blocked:
                return {"success": True, "created": False, "status": blocked}
            cursor.execute(f"""select 1
                from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'
                      in ('claim_before_on')
                  and not exists (
                    select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          claim.review_json->'rootline_execution'->>'execution_id'
                      and ((claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                        and (terminal.review_json->'rootline_execution'->>'action'='record_completed'
                          or (terminal.review_json->'rootline_execution'->>'action'
                                in ('contain_zone','record_ambiguous_shutdown','record_claim_recovery')
                              and terminal.review_json->'rootline_execution'->>'shutdown_verified'='true')))
                        or (claim.review_json->'rootline_execution'->>'action'='claim_borehole_before_on'
                          and terminal.review_json->'rootline_execution'->>'action'='record_borehole_completed'
                          and terminal.review_json->'rootline_execution'->>'shutdown_verified'='true'
                          and length(btrim(coalesce(terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0
                          and terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'execution_id'=
                            terminal.review_json->'rootline_execution'->>'execution_id'
                          and terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'final_state'='OFF'
                          and length(btrim(coalesce(terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0
                          and terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'execution_id'=
                            terminal.review_json->'rootline_execution'->>'execution_id'
                          and terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'authoritative'='true'
                          and terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'state'='OFF'
                          and length(btrim(coalesce(terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0
                          and terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'execution_id'=
                            terminal.review_json->'rootline_execution'->>'execution_id'
                          and btrim(terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                            btrim(terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL})
                          and btrim(terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                            btrim(terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL})
                          and btrim(terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                            btrim(terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL})
                          and terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'pump_stopped'='true'
                          and terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'water_flow_stopped'='true')))
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


def _daily_dispatch_blocker(cursor, *, execution_id, eligibility_id,
                            eligibility_sha256, zone_id, operating_date,
                            job_id="", segment_number=0):
    """Evaluate signed authority, completion and accepted-ON under caller's lock."""
    cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
        where event_source=%s
          and review_json->'rootline_execution'->>'action'='record_eligibility'
          and review_json->'rootline_execution'->>'execution_id'=%s
          and review_json->'rootline_execution'->>'eligibility_id'=%s
          and review_json->'rootline_execution'->>'eligibility_sha256'=%s
          and review_json->'rootline_execution'->>'operating_date'=%s
          and review_json->'rootline_execution'->>'zone_id'=%s
          and (%s <= 1 or review_json->'rootline_execution'->>'predecessor_off_rearm_verified'='true')
          limit 1""",
        (EVENT_SOURCE, execution_id, eligibility_id, eligibility_sha256,
         operating_date, zone_id, segment_number))
    if not cursor.fetchone():
        return "canonical_eligibility_unproven"
    if segment_number > 1:
        if not job_id:
            return "job_identity_incomplete"
        cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_execution'->>'action'='record_completed'
              and review_json->'rootline_execution'->>'job_id'=%s
              and (review_json->'rootline_execution'->>'segment_number')::int=%s
              and review_json->'rootline_execution'->>'shutdown_verified'='true'
            limit 1""", (EVENT_SOURCE, job_id, segment_number-1))
        if not cursor.fetchone():
            return "prior_segment_off_rearm_unproven"
        cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_execution'->>'action'='claim_before_on'
              and review_json->'rootline_execution'->>'job_id'=%s
              and (review_json->'rootline_execution'->>'segment_number')::int=%s
            limit 1""", (EVENT_SOURCE, job_id, segment_number))
        return "job_segment_already_claimed" if cursor.fetchone() else None
    # Reuse the canonical typed-history verifier rather than approximating its
    # digest, evidence, cutoff, runtime and replay rules in SQL. These rows and
    # the database clock are read inside the same advisory-locked transaction.
    cursor.execute("select clock_timestamp()")
    snapshot_cutoff = cursor.fetchone()[0]
    cursor.execute("""select irrigation_event_id,event_at,event_type,zone_id,
        planned_minutes,actual_minutes,details,source_id,actor,created_at
        from public.irrigation_events
        where zone_id=%s or event_type='PLANNING_EPOCH_STARTED'
        order by event_at,irrigation_event_id""", (zone_id,))
    from modules.telemetry.rootline_irrigation_history import project_canonical_irrigation_history
    history = project_canonical_irrigation_history(
        cursor.fetchall(), snapshot_cutoff=snapshot_cutoff)
    completed_days = history["zones"][zone_id]["verified_completed_days"]
    if operating_date in completed_days:
        return "zone_daily_completion_already_credited"
    cursor.execute("""select 1
        from public.sam_live_stock_conversation_review_events claim
        where claim.event_source=%s
          and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
          and claim.review_json->'rootline_execution'->>'zone_id'=%s
          and claim.review_json->'rootline_execution'->>'operating_date'=%s
          and exists (select 1
            from public.sam_live_stock_conversation_review_events outcome
            where outcome.event_source=%s
              and outcome.review_json->'rootline_execution'->>'action'='record_on_outcome'
              and outcome.review_json->'rootline_execution'->>'execution_id'=
                  claim.review_json->'rootline_execution'->>'execution_id'
              and outcome.review_json->'rootline_execution'->'on_outcome'->>
                  'accepted_unambiguous'='true') limit 1""",
        (EVENT_SOURCE, zone_id, operating_date, EVENT_SOURCE))
    if cursor.fetchone():
        return "zone_daily_on_already_accepted"
    return None


def _valid_iso_date(value):
    from datetime import date
    try:
        return date.fromisoformat(str(value)).isoformat() == str(value)
    except (TypeError, ValueError):
        return False


def _claim_single_auxiliary(body):
    """Atomically consume one auxiliary artifact without blocking its B/C zone."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution_id=str(body["execution_id"]);consumption_key=str(body.get("consumption_key") or "")
    auxiliary_id=str(body.get("auxiliary_device_id") or "")
    if not consumption_key or not auxiliary_id:
        return {"success":False,"created":False,"status":"auxiliary_claim_incomplete"}
    event_id=_event_id("claim_auxiliary_before_on",body)
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            if body.get("device_type") == "fertilizer_injection_valve":
                job_id=str(body.get("job_id") or "");job_sha=str(body.get("job_sha256") or "")
                segment=str(body.get("segment_identity") or "");zone=str(body.get("zone_id") or "")
                zone_execution=str(body.get("zone_execution_id") or "")
                if (not job_id.startswith("ROOTLINE-IRRIGATION-JOB-") or len(job_sha)!=64
                        or not segment.startswith("ROOTLINE-JOB-SEGMENT-") or not zone
                        or not zone_execution):
                    return {"success":False,"created":False,
                        "status":"irrigation_job_binding_incomplete"}
                cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                    where claim.event_source=%s
                      and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                      and claim.review_json->'rootline_execution'->>'job_id'=%s
                      and claim.review_json->'rootline_execution'->>'job_sha256'=%s
                      and claim.review_json->'rootline_execution'->>'segment_identity'=%s
                      and claim.review_json->'rootline_execution'->>'zone_id'=%s
                      and claim.review_json->'rootline_execution'->>'execution_id'=%s
                      and exists (select 1 from public.sam_live_stock_conversation_review_events active
                        where active.event_source=%s
                          and active.review_json->'rootline_execution'->>'action'='mark_active'
                          and active.review_json->'rootline_execution'->>'execution_id'=
                              claim.review_json->'rootline_execution'->>'execution_id')
                      and not exists (select 1 from public.sam_live_stock_conversation_review_events terminal
                        where terminal.event_source=%s
                          and terminal.review_json->'rootline_execution'->>'execution_id'=
                              claim.review_json->'rootline_execution'->>'execution_id'
                          and terminal.review_json->'rootline_execution'->>'action'
                              in ('record_completed','contain_zone','record_ambiguous_shutdown',
                                  'record_claim_recovery'))
                      and not exists (select 1 from public.sam_live_stock_conversation_review_events stopping
                        where stopping.event_source=%s
                          and stopping.review_json->'rootline_execution'->>'execution_id'=
                              claim.review_json->'rootline_execution'->>'execution_id'
                          and stopping.review_json->'rootline_execution'->>'action'='mark_stopping')
                    limit 1""",(EVENT_SOURCE,job_id,job_sha,segment,zone,zone_execution,
                        EVENT_SOURCE,EVENT_SOURCE,EVENT_SOURCE))
                if not cursor.fetchone():
                    return {"success":True,"created":False,
                        "status":"eligible_irrigation_segment_not_active"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where event_source=%s and (review_event_id=%s or
                  (review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                   and review_json->'rootline_execution'->>'consumption_key'=%s)) limit 1""",
                (EVENT_SOURCE,event_id,consumption_key))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"eligibility_already_consumed"}
            # The global and auxiliary locks serialize these budget checks with
            # every new claim. A changed plan cannot purchase a second pulse or
            # refund a mixer reservation after uncertain/failed execution.
            if body.get("device_type") == "fertilizer_injection_valve":
                cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                      and review_json->'rootline_execution'->>'zone_execution_id'=%s
                      and review_json->'rootline_execution'->>'pulse_number'=%s limit 1""",
                    (EVENT_SOURCE, str(body.get("zone_execution_id") or ""),
                     str(body.get("pulse_number") or "")))
                if cursor.fetchone():
                    return {"success":True,"created":False,"status":"pulse_already_claimed"}
            elif body.get("device_type") == "fertilizer_mixer":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'device_type'='fertilizer_mixer'
                      and review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                    order by created_at,review_event_id""", (EVENT_SOURCE,))
                from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
                from datetime import datetime
                at = datetime.fromisoformat(str(body.get("claimed_at") or ""))
                account = mixing_daily_accounting([row[0] for row in cursor.fetchall()]
                    + [{**body, "action":"claim_auxiliary_before_on"}], now=at)
                if not account["history_valid"] or account["reserved_seconds"] > 1800:
                    return {"success":True,"created":False,"status":"daily_mixing_budget_unavailable"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                  and (claim.review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                    or (claim.review_json->'rootline_execution'->>'device_id'=%s
                        and claim.review_json->'rootline_execution'->>'channel'=%s))
                  and not exists (select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          claim.review_json->'rootline_execution'->>'execution_id'
                      and (terminal.review_json->'rootline_execution'->>'action'
                          in ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped')
                        or (terminal.review_json->'rootline_execution'->>'action'=
                              'contain_auxiliary_device'
                            and terminal.review_json->'rootline_execution'->>
                              'shutdown_verified'='true'))) limit 1""",
                (EVENT_SOURCE,auxiliary_id,str(body.get("device_id") or ""),
                 str(body.get("channel") or ""),EVENT_SOURCE))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"auxiliary_active"}
            if _auxiliary_containment_state(cursor, auxiliary_id)["contained"]:
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


def _claim_borehole_material_load(body):
    """Reserve the existing ROOTLINE material-load rail; this issues no command."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution_id=str(body.get("execution_id") or "")
    digest=str(body.get("eligibility_sha256") or "")
    key=str(body.get("consumption_key") or "")
    if (not execution_id or len(digest)!=64 or key != "borehole:"+digest
            or body.get("device_key") != "ewelink:ewelink_owner_account:1002851416:1"):
        return {"success":False,"created":False,"status":"borehole_claim_incomplete"}
    event_id=_event_id("claim_borehole_before_on",body)
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
      with connection.cursor() as cursor:
        # The common output lock serializes admission, not operating duration.
        # Only a prior borehole claim conflicts; other devices own their outputs.
        cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
        cursor.execute("""select review_json->'rootline_execution'
          from public.sam_live_stock_conversation_review_events
          where event_source=%s and review_json->'rootline_execution'->>'action'='record_borehole_eligibility'
          and review_json->'rootline_execution'->>'execution_id'=%s
          and review_json->'rootline_execution'->>'eligibility_sha256'=%s
          order by created_at desc limit 1""",
          (EVENT_SOURCE,execution_id,digest))
        row=cursor.fetchone()
        canonical=row[0] if row and isinstance(row[0],dict) else None
        immutable=("execution_id","eligibility_sha256","consumption_key","device_key",
          "baseline_sha256","registry_generation","need_sha256","evidence_sha256",
          "requested_seconds","assessed_at","gates","blockers")
        if (not _valid_borehole_eligibility(canonical)
                or any(body.get(field)!=canonical.get(field) for field in immutable)):
            return {"success":True,"created":False,"status":"canonical_borehole_eligibility_unproven"}
        cursor.execute(f"""select 1 from public.sam_live_stock_conversation_review_events c
          where c.event_source=%s and c.review_json->'rootline_execution'->>'action'
            in ('claim_borehole_before_on') and not exists(
              select 1 from public.sam_live_stock_conversation_review_events t
              where t.event_source=%s and t.review_json->'rootline_execution'->>'execution_id'=
                c.review_json->'rootline_execution'->>'execution_id' and
                ((c.review_json->'rootline_execution'->>'action'='claim_before_on' and
                  (t.review_json->'rootline_execution'->>'action'='record_completed' or
                   (t.review_json->'rootline_execution'->>'action'='contain_zone' and
                    t.review_json->'rootline_execution'->>'shutdown_verified'='true'))) or
                 (c.review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on' and
                  (t.review_json->'rootline_execution'->>'action' in
                    ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped') or
                   (t.review_json->'rootline_execution'->>'action'='contain_auxiliary_device' and
                    t.review_json->'rootline_execution'->>'shutdown_verified'='true'))) or
                 (c.review_json->'rootline_execution'->>'action'='claim_borehole_before_on' and
                  t.review_json->'rootline_execution'->>'action'='record_borehole_completed' and
                  t.review_json->'rootline_execution'->>'shutdown_verified'='true' and
                  length(btrim(coalesce(t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0 and
                  t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'execution_id'=
                    t.review_json->'rootline_execution'->>'execution_id' and
                  t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'final_state'='OFF' and
                  length(btrim(coalesce(t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0 and
                  t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'execution_id'=
                    t.review_json->'rootline_execution'->>'execution_id' and
                  t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'authoritative'='true' and
                  t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'state'='OFF' and
                  btrim(t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                    btrim(t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) and
                  ((t.review_json->'rootline_execution'->>'operational_proof'='provider_app_on_to_off' and
                    t.review_json->'rootline_execution'->'provider_start_evidence'->>'authoritative'='true' and
                    t.review_json->'rootline_execution'->'provider_start_evidence'->>'state'='ON') or
                   (length(btrim(coalesce(t.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0 and
                    t.review_json->'rootline_execution'->'physical_completion_evidence'->>'execution_id'=
                      t.review_json->'rootline_execution'->>'execution_id' and
                    btrim(t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                      btrim(t.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) and
                    btrim(t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                      btrim(t.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) and
                    t.review_json->'rootline_execution'->'physical_completion_evidence'->>'pump_stopped'='true' and
                    t.review_json->'rootline_execution'->'physical_completion_evidence'->>'water_flow_stopped'='true'))))) limit 1""",
          (EVENT_SOURCE,EVENT_SOURCE))
        if cursor.fetchone():
            return {"success":True,"created":False,"status":"material_load_active"}
        cursor.execute("""insert into public.sam_live_stock_conversation_review_events
          (review_event_id,chatwoot_conversation_id,source_agent,event_source,recommended_action,review_json)
          values (%s,%s,'rootline_backend',%s,'claim_borehole_before_on',%s::jsonb)
          on conflict(review_event_id) do nothing""",(event_id,execution_id,EVENT_SOURCE,
          json.dumps({"rootline_execution":{"action":"claim_borehole_before_on",
            "event_id":event_id,**body}},sort_keys=True,separators=(",",":"),default=str)))
        return {"success":True,"created":cursor.rowcount==1,
          "status":"claimed" if cursor.rowcount==1 else "execution_replay"}


def _valid_borehole_eligibility(value):
    if not isinstance(value,dict) or value.get("eligible") is not True:
        return False
    material={key:value.get(key) for key in ("contract_version","device_key",
      "baseline_sha256","registry_generation","need_sha256","evidence_sha256",
      "requested_seconds","assessed_at","gates","blockers")}
    version=material["contract_version"]
    if version=="rootline_borehole_runtime_eligibility.v2":
        native=value.get("native_fail_stop_seconds")
        if (type(native) is not int or type(value.get("requested_seconds")) is not int
                or not 0<value["requested_seconds"]<=native<=14400):
            return False
        material["native_fail_stop_seconds"]=native
    digest=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),
      default=str).encode()).hexdigest()
    required_gates={"canonical_need","commissioned_baseline","standing_authority",
      "provider_off","dry_run","low_water","supply_pressure","full_tank",
      "energy","concurrency","bounded_runtime"}
    return (version in {"rootline_borehole_runtime_eligibility.v1","rootline_borehole_runtime_eligibility.v2"}
      and material["device_key"]=="ewelink:ewelink_owner_account:1002851416:1"
      and value.get("eligibility_sha256")==digest
      and value.get("execution_id")=="ROOTLINE-BOREHOLE-"+digest[:24].upper()
      and value.get("consumption_key")=="borehole:"+digest
      and value.get("command_authority") is False
      and isinstance(material["gates"],dict) and set(material["gates"])==required_gates
      and all(passed is True for passed in material["gates"].values())
      and material["blockers"]==[])



_UNSTARTED_RECONCILIATION = "rootline_unstarted_auxiliary_reconciliation.v1"


def _event_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _owner_reconciliation_reference(value):
    return (isinstance(value, dict) and value.get("source") == "owner_codex_chat"
        and isinstance(value.get("reference"), str) and bool(value["reference"].strip())
        and _sha256_text(value.get("artifact_sha256")))


def _sha256_text(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _auxiliary_containment_state(cursor, auxiliary_id):
    """Only an exact canonical no-dispatch reconciliation supersedes its hold."""
    cursor.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
          and review_json->'rootline_execution'->>'action' in
              ('contain_auxiliary_device','reconcile_unstarted_auxiliary')
        order by created_at,review_event_id""", (EVENT_SOURCE, auxiliary_id))
    pending = {}; resolved = None
    for (row,) in cursor.fetchall():
        if not isinstance(row, dict):
            return {"contained": True, "evidence": row}
        if row.get("action") == "contain_auxiliary_device":
            pending[row.get("event_id")] = row
            continue
        held = pending.get(row.get("containment_event_id"))
        if (held is not None and row.get("contract_version") == _UNSTARTED_RECONCILIATION
                and row.get("resolution") == "never_dispatched_verified_off"
                and row.get("execution_id") == held.get("execution_id")
                and row.get("containment_sha256") == _event_digest(held)
                and row.get("reservation_preserved") is True and row.get("on_authority") is False
                and _owner_reconciliation_reference(row.get("owner_instruction"))
                and _sha256_text(row.get("root_review_sha256"))):
            history = _managed_edge_rows(cursor, held["execution_id"])
            if not any(item.get("action") in {"claim_auxiliary_dispatch",
                    "record_auxiliary_on_outcome", "mark_auxiliary_active"} for item in history):
                del pending[row["containment_event_id"]]
                resolved = row
    if pending:
        return {"contained": True, "evidence": list(pending.values())[-1]}
    return {"contained": False, **({"resolution_evidence": resolved} if resolved else {})}


def _reconcile_unstarted_auxiliary(body):
    """Owner-operated, append-only reconciliation; never grants an ON or refunds time."""
    from datetime import datetime, timedelta, timezone
    from modules.telemetry.rootline_device_registry import get_device_contract
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    fields = {"execution_id", "auxiliary_device_id", "claim_event_id", "claim_sha256",
        "containment_event_id", "containment_sha256", "shutdown_evidence",
        "owner_instruction", "root_review_sha256"}
    if (set(body) != fields or not str(body.get("execution_id") or "")
            or body.get("auxiliary_device_id") not in {"FERTILIZER-MIXER-CH2", "FERTILIZER-INJECTION-CH1"}
            or not all(_sha256_text(body.get(key)) for key in
                       ("claim_sha256", "containment_sha256", "root_review_sha256"))
            or not _owner_reconciliation_reference(body.get("owner_instruction"))):
        return {"success": False, "created": False, "status": "reconciliation_binding_invalid"}
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                          read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
            rows = _managed_edge_rows(cursor, body["execution_id"])
            prior = [row for row in rows if row.get("action") == "reconcile_unstarted_auxiliary"]
            if prior:
                exact = len(prior) == 1 and all(prior[0].get(k) == v for k, v in body.items())
                return {"success": exact, "created": False,
                        "status": "already_reconciled" if exact else "reconciliation_conflict"}
            claims = [row for row in rows if row.get("action") == "claim_auxiliary_before_on"]
            held = _auxiliary_containment_state(cursor, body["auxiliary_device_id"])
            containment = held.get("evidence") or {}
            contract = get_device_contract(body["auxiliary_device_id"]) or {}
            if (len(claims) != 1 or not held["contained"]
                    or claims[0].get("event_id") != body["claim_event_id"]
                    or _event_digest(claims[0]) != body["claim_sha256"]
                    or containment.get("event_id") != body["containment_event_id"]
                    or _event_digest(containment) != body["containment_sha256"]
                    or any(containment.get(k) != claims[0].get(k) for k in
                           ("execution_id", "auxiliary_device_id", "device_id", "channel"))
                    or claims[0].get("auxiliary_device_id") != body["auxiliary_device_id"]
                    or claims[0].get("state") != "claimed"
                    or type(claims[0].get("on_attempts")) is not int or claims[0]["on_attempts"] != 0
                    or any(claims[0].get(k) != contract.get(k) for k in ("device_id", "channel", "device_type"))
                    or containment.get("reason") != "restart_or_deadline_ambiguous"
                    or containment.get("shutdown_verified") is not True
                    or any(row.get("action") in {"claim_auxiliary_dispatch", "record_auxiliary_on_outcome",
                        "mark_auxiliary_active", "record_auxiliary_completed",
                        "record_auxiliary_control_pulse_stopped"} for row in rows)):
                return {"success": False, "created": False, "status": "never_dispatched_preimage_unproven"}
            now = datetime.now(timezone.utc)
            proof = body["shutdown_evidence"]
            stamp = _time(proof.get("retrieved_at")) if isinstance(proof, dict) else None
            previous_off = containment.get("shutdown_evidence") or {}
            contained_off = _time(previous_off.get("retrieved_at")) if isinstance(previous_off, dict) else None
            if (not isinstance(proof, dict) or proof.get("authoritative") is not True
                    or proof.get("state") != "OFF" or not _sha256_text(proof.get("evidence_id"))
                    or proof.get("device_id") != contract["device_id"]
                    or type(proof.get("channel")) is not int or proof["channel"] != contract["channel"]
                    or stamp is None or stamp.tzinfo is None
                    or contained_off is None or contained_off.tzinfo is None or stamp < contained_off
                    or previous_off.get("authoritative") is not True or previous_off.get("state") != "OFF"
                    or not timedelta(0) <= now-stamp <= timedelta(seconds=60)):
                return {"success": False, "created": False, "status": "current_exact_off_unproven"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events candidate
                where candidate.event_source=%s
                  and candidate.review_json->'rootline_execution'->>'action'
                      in ('claim_auxiliary_before_on','mark_auxiliary_active')
                  and not exists (select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          candidate.review_json->'rootline_execution'->>'execution_id'
                      and (terminal.review_json->'rootline_execution'->>'action'
                           in ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped')
                           or (terminal.review_json->'rootline_execution'->>'action'='contain_auxiliary_device'
                               and terminal.review_json->'rootline_execution'->>'shutdown_verified'='true')))
                limit 1""", (EVENT_SOURCE, EVENT_SOURCE))
            if cursor.fetchone():
                return {"success": False, "created": False, "status": "auxiliary_owner_still_active"}
            record = {**body, "contract_version": _UNSTARTED_RECONCILIATION,
                "resolution": "never_dispatched_verified_off", "on_authority": False,
                "reservation_preserved": True, "recorded_at": now.isoformat()}
            return {**_insert_managed_event(cursor, "reconcile_unstarted_auxiliary", record),
                    "status": "never_dispatched_reconciled"}

def _managed_family(*, borehole):
    return ({"claim":"claim_borehole_before_on", "dispatch":"claim_borehole_dispatch",
        "active":"mark_borehole_active", "off":"claim_borehole_off_attempt",
        "outcome":"record_borehole_on_outcome",
        "terminals":{"record_borehole_completed", "contain_borehole"}} if borehole else
        {"claim":"claim_auxiliary_before_on", "dispatch":"claim_auxiliary_dispatch",
        "active":"mark_auxiliary_active", "off":"claim_auxiliary_off_attempt",
        "outcome":"record_auxiliary_on_outcome",
        "terminals":{"record_auxiliary_completed", "record_auxiliary_control_pulse_stopped",
                     "contain_auxiliary_device"}})


def _managed_edge_rows(cursor, execution_id):
    cursor.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s and review_json->'rootline_execution'->>'execution_id'=%s
        order by created_at,review_event_id""", (EVENT_SOURCE, str(execution_id)))
    return [row[0] if isinstance(row[0],dict) else json.loads(row[0])
            for row in cursor.fetchall()]


def _managed_claim_matches(rows, body, family):
    claims=[row for row in rows if row.get("action")==family["claim"]]
    if len(claims)!=1:
        return False
    # Every persisted claim field remains immutable at both dispatch and activation.
    claim=claims[0]
    return all(body.get(key)==value for key,value in claim.items()
        if key not in {"action","event_id","state","on_attempts","off_attempts"})


def _managed_edge_retired(rows, family):
    return any(row.get("action") in family["terminals"] | {family["off"]}
               for row in rows)


def _insert_managed_event(cursor, action, body):
    event_id=_event_id(action,body)
    cursor.execute("""insert into public.sam_live_stock_conversation_review_events
        (review_event_id,chatwoot_conversation_id,source_agent,event_source,
         recommended_action,review_json)
        values (%s,%s,'rootline_backend',%s,%s,%s::jsonb)
        on conflict (review_event_id) do nothing""", (event_id,str(body["execution_id"]),
        EVENT_SOURCE,action,json.dumps({"rootline_execution":
            _stored_event_body(action,body,event_id)},sort_keys=True,separators=(",",":"),default=str)))
    return {"success":True,"created":cursor.rowcount==1,"event_id":event_id}


def _guarded_managed_transition(action, body):
    """OFF ownership and activation share the sender's exact existing locks."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    borehole="borehole" in action;family=_managed_family(borehole=borehole)
    if not str(body.get("execution_id") or ""):
        return {"success":False,"created":False,"status":"execution_identity_missing"}
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            rows=_managed_edge_rows(cursor,body["execution_id"])
            if action==family["active"]:
                if (not _managed_claim_matches(rows,body,family)
                        or _managed_edge_retired(rows,family)
                        or not any(row.get("action")==family["dispatch"] for row in rows)
                        or body.get("state")!="Active" or body.get("on_attempts")!=1):
                    return {"success":False,"created":False,"status":"managed_start_ownership_retired"}
            elif action==family["off"]:
                # The loader also supports legacy Active rows whose original
                # claim is unavailable. Preserve their safety OFF, never ON.
                from modules.telemetry.rootline_device_registry import get_device_contract
                def exact_active(row):
                    if row.get("action")!=family["active"] or row.get("state")!="Active":
                        return False
                    if borehole:
                        return row.get("device_key")=="ewelink:ewelink_owner_account:1002851416:1"
                    identity=row.get("auxiliary_device_id")
                    contract=get_device_contract(identity) or {}
                    return (identity in {"FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1"}
                        and all(row.get(key)==contract.get(key)
                            for key in ("device_id","channel","device_type")))
                if (not any(row.get("action")==family["claim"] or exact_active(row) for row in rows)
                        or type(body.get("attempt")) is not int or not 1<=body["attempt"]<=3):
                    return {"success":False,"created":False,"status":"managed_off_claim_invalid"}
            return _insert_managed_event(cursor,action,body)


def _dispatch_auxiliary_on_edge(body):
    # Retain the internal entry point for existing direct callers.
    return _dispatch_managed_on_edge(body,borehole=False)


def _dispatch_managed_on_edge(body, *, borehole):
    """Commit one attempt before I/O; serialize final ON against all OFF claims.

    A crash between the two transactions consumes the attempt without sending.
    A crash/exception after sending cannot make the attempt reusable.
    """
    from datetime import datetime, timedelta, timezone
    from modules.telemetry.rootline_device_registry import get_device_contract
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    body=dict(body);dispatch=body.pop("dispatch",None);family=_managed_family(borehole=borehole)
    identity="BOREHOLE-1-MINI-R4-CH1" if borehole else body.get("auxiliary_device_id")
    contract=get_device_contract(identity) or {}
    if (not callable(dispatch) or identity not in ({"BOREHOLE-1-MINI-R4-CH1"} if borehole
            else {"FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1"})
            or (borehole and body.get("device_key")!="ewelink:ewelink_owner_account:1002851416:1")
            or (not borehole and (body.get("device_id")!=contract.get("device_id")
                or body.get("channel")!=contract.get("channel")
                or body.get("device_type")!=contract.get("device_type")))):
        return {"accepted_unambiguous":False,"status":"atomic_on_edge_invalid"}
    def permitted(rows):
        now=datetime.now(timezone.utc);claimed=_time(body.get("claimed_at"));deadline=_time(body.get("primary_stop_deadline"))
        return (claimed is not None and claimed.tzinfo is not None and deadline is not None
            and deadline.tzinfo is not None and timedelta(0)<=now-claimed<=timedelta(seconds=30)
            and now<deadline and _managed_claim_matches(rows,body,family)
            and not _managed_edge_retired(rows,family)
            and not any(row.get("action") in {family["active"],family["outcome"]} for row in rows))
    # Unique review_event_id is the existing database-backed at-most-once fence.
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            rows=_managed_edge_rows(cursor,body.get("execution_id"))
            if not permitted(rows):
                return {"accepted_unambiguous":False,"status":"managed_start_ownership_retired"}
            if not _insert_managed_event(cursor,family["dispatch"],body)["created"]:
                return {"accepted_unambiguous":False,"status":"managed_dispatch_already_consumed"}
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            rows=_managed_edge_rows(cursor,body["execution_id"])
            if not permitted(rows):
                return {"accepted_unambiguous":False,"status":"managed_start_ownership_retired"}
            if not borehole and body["device_type"]=="fertilizer_injection_valve":
                cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                    where claim.event_source=%s
                      and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                      and claim.review_json->'rootline_execution'->>'execution_id'=%s
                      and claim.review_json->'rootline_execution'->>'job_id'=%s
                      and claim.review_json->'rootline_execution'->>'job_sha256'=%s
                      and claim.review_json->'rootline_execution'->>'segment_identity'=%s
                      and claim.review_json->'rootline_execution'->>'zone_id'=%s
                      and not exists (select 1 from public.sam_live_stock_conversation_review_events stop
                        where stop.event_source=%s
                          and stop.review_json->'rootline_execution'->>'execution_id'=%s
                          and stop.review_json->'rootline_execution'->>'action' in
                            ('mark_stopping','record_completed','contain_zone',
                             'record_ambiguous_shutdown','record_claim_recovery')) limit 1""",
                    (EVENT_SOURCE,body.get("zone_execution_id"),body.get("job_id"),
                     body.get("job_sha256"),body.get("segment_identity"),body.get("zone_id"),
                     EVENT_SOURCE,body.get("zone_execution_id")))
                if not cursor.fetchone():
                    return {"accepted_unambiguous":False,
                        "status":"parent_edge_authority_revoked"}
            try:
                return dispatch()
            except Exception:
                return {"accepted_unambiguous":False,"status":"managed_sender_outcome_unknown"}


def _append_history(action, body, *, connection=None, append=True):
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
        "operating_date": body.get("operating_date"),
        "start_evidence_id": (body.get("start_evidence") or {}).get("evidence_id") or "Unavailable",
        "maximum_runtime_minutes": body.get("planned_runtime_minutes"),
        "verified_runtime_minutes": actual,
        "shutdown_evidence_id": (body.get("shutdown_evidence") or {}).get("evidence_id") or "Unavailable",
        "shutdown_verified": body.get("shutdown_verified") is True,
        "objective_satisfied": body.get("objective_satisfied") is True,
        "job_id": body.get("job_id"),
        "job_sha256": body.get("job_sha256"),
        "job_completed": body.get("job_completed"),
        "segment_number": body.get("segment_number"),
        "cumulative_verified_runtime_seconds": body.get("cumulative_verified_runtime_seconds"),
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
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
        with (nullcontext(connection) if connection is not None else
              connect_bounded_rootline_postgres(
                  database_url=os.environ.get("DATABASE_URL"), read_only=False)) as connection:
            with connection.cursor() as cursor:
                if append:
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
