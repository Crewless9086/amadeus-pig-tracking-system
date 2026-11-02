"""Durable ROOTLINE coordinator state on the existing append-only audit rail."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import nullcontext
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import socket
import time

EVENT_SOURCE = "rootline_irrigation_execution"


class RootlineExecutionStoreUnavailable(RuntimeError):
    """Durable execution truth could not be loaded within its read deadline."""

    def __init__(self, action):
        super().__init__("rootline_execution_store_unavailable:" + str(action))
        self.action = str(action)


def rootline_irrigation_execution_store(action, payload):
    if action in _A_COMMISSIONING_ACTIONS:
        return _a_commissioning_store(action, payload)
    if action == "record_execution_not_dispatched":
        return {"success": False, "created": False, "status": "use_locked_no_send_retirement"}
    if action in {"load_active", "load_off_attempts", "load_zone_containment",
                  "load_active_auxiliary", "load_active_auxiliaries", "load_auxiliary_off_attempts",
                  "load_auxiliary_containment", "load_auxiliary_history",
                  "load_auxiliary_physical_outcome", "load_job_events",
                  "load_active_borehole", "load_borehole_off_attempts", "load_eskom_events"}:
        return _load(action, payload)
    body = dict(payload or {})
    if action == "dispatch_borehole_off_edge":
        return _dispatch_borehole_off_edge(body)
    if action == "record_borehole_aborted":
        return _record_borehole_aborted(body)
    if action == "retire_not_dispatched_execution":
        return _retire_not_dispatched_execution(body)
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
    if action == "mark_stopping":
        return _mark_parent_stopping(body)
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


_PARENT_IMMUTABLE = ("execution_id", "zone_id", "device_id", "channel", "job_id",
    "job_sha256", "segment_number", "segment_identity", "claimed_at",
    "primary_stop_deadline", "native_fail_stop_deadline", "planned_runtime_seconds",
    "on_attempts", "start_evidence", "cumulative_verified_runtime_seconds",
    "eligibility_id", "eligibility_sha256", "consumption_key", "operating_date",
    "expected_segment_count", "requested_total_duration_seconds", "requested_total_duration_minutes",
    "governed_executable_duration_seconds", "segment_requested_seconds", "commissioning_id",
    "controller_safety_generation")


def _same_parent(left, right):
    return all(left.get(key) == right.get(key) for key in _PARENT_IMMUTABLE)


def _mark_parent_stopping(body):
    """First locked stop wins; stale ticks cannot change its reason or deadlines."""
    from modules.oom_sakkie.bounded_postgres_read import (
        connect_bounded_rootline_postgres, is_database_unavailable,
    )
    try:
        with connect_bounded_rootline_postgres(
                database_url=os.environ.get("DATABASE_URL"), read_only=False) as connection:
            connection.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            connection.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
            rows = [row[0] for row in connection.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s and review_json->'rootline_execution'->>'execution_id'=%s
                order by created_at,review_event_id""", (EVENT_SOURCE, body.get("execution_id"))).fetchall()]
            if any(_terminal_closes_active(row) for row in rows):
                return {"success": True, "created": False, "status": "parent_already_terminal"}
            active = next((row for row in reversed(rows) if row.get("action") == "mark_active"), None)
            if (active is None and body.get("reason") == "restart_after_pre_on_claim"
                    and body.get("weather_stop_evidence") is None):
                active = next((row for row in reversed(rows) if row.get("action") == "claim_before_on"), None)
            if active is None or not _same_parent(active, body):
                return {"success": False, "created": False, "status": "canonical_active_parent_changed"}
            prior = next((row for row in rows if row.get("action") == "mark_stopping"), None)
            if prior is not None:
                if not _same_parent(active, prior):
                    return {"success": False, "created": False, "status": "canonical_stopping_parent_changed"}
                return {"success": True, "created": False, "execution": prior, "active_execution": active}
            result = _write_terminal_review(connection, "mark_stopping", body)
            return {**result, "execution": result["resolution"], "active_execution": active}
    except _AtomicTerminalWriteFailed as exc:
        return {"success": False, "created": False, "status": str(exc)}
    except Exception as exc:
        if is_database_unavailable(exc):
            raise RootlineExecutionStoreUnavailable("mark_stopping") from exc
        raise


def _weather_terminal_resolution(body, events):
    """Close only the original exhausted segment budget, preserving unmet need."""
    from modules.telemetry.rootline_irrigation_job_contract import project_next_segment
    if not body.get("job_id") or not any(row.get("state") == "Stopped" for row in events):
        return None
    from modules.telemetry.rootline_irrigation_history import PARENT_ACCOUNTING_ACTIONS
    events = [row for row in events if row.get("action") in PARENT_ACCOUNTING_ACTIONS]
    authority = next((row for row in events if row.get("action") == "record_eligibility"
        and row.get("job_sha256") == body.get("job_sha256")), {})
    job = {"contract_version": "rootline_irrigation_job.v1", "job_id": body.get("job_id"),
        "job_sha256": body.get("job_sha256"), "zone_id": body.get("zone_id"),
        "operating_date": body.get("operating_date"),
        "requested_total_seconds": body.get("requested_total_duration_seconds"),
        "requested_total_minutes": body.get("requested_total_duration_minutes"),
        "governed_executable_seconds": body.get("governed_executable_duration_seconds"),
        "maximum_segment_seconds": 3599, "expected_segment_count": body.get("expected_segment_count"),
        "plan_identity": authority.get("plan_generation")}
    projection = project_next_segment(job, events, rearm_readback_off=True)
    if projection.get("status") != "job_deferred":
        return None
    material = {"contract_version": "rootline_irrigation_job_resolution.v1",
        "resolution": "Deferred", "terminal": True, "job_id": job["job_id"],
        "job_sha256": job["job_sha256"], "zone_id": job["zone_id"],
        "operating_date": job["operating_date"],
        "current_segment": projection["current_segment"],
        "expected_segment_count": job["expected_segment_count"],
        "cumulative_verified_runtime_seconds": projection["cumulative_verified_runtime_seconds"],
        "remaining_seconds": projection["remaining_seconds"], "reason": projection["reason"]}
    digest = _event_digest(material)
    return {**material, "resolution_sha256": digest,
        "execution_id": "ROOTLINE-JOB-RESOLUTION-" + digest[:24].upper(),
        "next_action_owner": "ROOTLINE", "next_trigger": "next_permitted_normal_irrigation_plan"}


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
                           or review_json->'rootline_execution'->>'execution_id'=%s)
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
                exact = (existing == _stored_event_body(action, body, _event_id(action, body))
                    and _append_history(action, body, connection=connection, append=False))
                if exact:
                    return {"success": True, "created": False, "history_event_created": False}
                from modules.telemetry.rootline_irrigation_job_contract import validate_weather_stopped_execution
                barrier = next((row for row in events if row.get("action") == "mark_stopping"
                    and row.get("execution_id") == body.get("execution_id")), None)
                if (validate_weather_stopped_execution(body) and validate_weather_stopped_execution(existing)
                        and barrier is not None and _same_parent(body, existing)
                        and _same_parent(barrier, existing)
                        and all(body.get(key) == existing.get(key) == barrier.get(key)
                            for key in ("weather_stop_evidence", "stop_requested_at", "reason"))
                        and _append_history(action, existing, connection=connection, append=False)):
                    # The competing payload is refused. Return the immutable first
                    # proof, read under both locks, for truthful coordinator recovery.
                    return {"success": False, "created": False, "history_event_created": False,
                        "status": "canonical_weather_stop_already_committed", "canonical_execution": existing}
                raise _AtomicTerminalWriteFailed("canonical_history_completion_unproven")
            if any(row.get("action") == "record_completed"
                   and row.get("execution_id") == body.get("execution_id") for row in events):
                raise ValueError("canonical_completion_history_conflict")
            if any(row.get("action") == "record_job_resolution"
                   and row.get("resolution") == "Cancelled" for row in events):
                raise ValueError("cancelled_parent_completion_refused")
            barrier = next((row for row in events if row.get("action") == "mark_stopping"
                and row.get("execution_id") == body.get("execution_id")), None)
            weather_stop = body.get("state") == "Stopped" or body.get("weather_stop_evidence") is not None
            if weather_stop:
                from modules.telemetry.rootline_irrigation_job_contract import validate_weather_stopped_execution
                if (not validate_weather_stopped_execution(body) or barrier is None
                        or not _same_parent(barrier, body)
                        or barrier.get("weather_stop_evidence") != body.get("weather_stop_evidence")
                        or barrier.get("stop_requested_at") != body.get("stop_requested_at")
                        or barrier.get("reason") != body.get("reason")):
                    raise ValueError("canonical_weather_stop_preimage_changed")
            elif barrier is not None and barrier.get("weather_stop_evidence") is not None:
                raise ValueError("canonical_weather_stop_cannot_complete")
            terminal_body = _stored_event_body(action, body, _event_id(action, body))
            resolution = _weather_terminal_resolution(terminal_body, [*events, terminal_body])
            if not _append_history(action, body, connection=connection):
                raise _AtomicTerminalWriteFailed("canonical_history_completion_unproven")
            result = _write_terminal_review(connection, action, body)
            if resolution is not None:
                _write_terminal_review(connection, "record_job_resolution", resolution)
            return {**result, "history_event_created": True, "parent_resolution": resolution}
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
    elif action == "record_completed" and body.get("state") == "Stopped":
        material = f"{execution}:WEATHER-STOPPED"
    elif action == "claim_notification":
        material = f"{execution}:NOTIFY:{body.get('notification_state')}"
    elif action == "record_fertilizer_sequence_completed":
        material = f"{execution}:CONTROLLER-SEQUENCE-COMPLETED"
    elif action == "record_eskom_completed":
        material = f"{execution}:ESKOM-COMPLETED"
    elif action in {"claim_auxiliary_dispatch", "claim_borehole_dispatch"}:
        material = f"{execution}:MANAGED-DISPATCH"
    elif action == "record_borehole_aborted":
        material = f"{execution}:BOREHOLE-ABORTED"
    elif action == "record_execution_not_dispatched":
        material = f"{execution}:PROVEN-NO-SEND"
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
                if borehole:
                    return _active_borehole(_borehole_state_rows(cursor))
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
                relevant_actions = terminal_actions | {claim_action, active_action,
                    "record_execution_not_dispatched", "record_on_outcome", "record_auxiliary_on_outcome"}
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
                loaded = [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    for row in cursor.fetchall()]
                terminal = {row.get("execution_id") for row in loaded
                    if _verified_not_dispatched(row, loaded)}
                candidates = {}
                for item in loaded:
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
                        if _no_send_preimage(loaded, identity) is not None:
                            item = {**item, "on_not_dispatched": True}
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
                          in ('claim_before_on','mark_active','record_completed','record_job_resolution',
                              'record_execution_not_dispatched','record_on_outcome')
                    order by created_at,review_event_id""", (EVENT_SOURCE, str(payload or "")))
                events = [row[0] if isinstance(row[0],dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
                retired = {row.get("execution_id") for row in events if _verified_not_dispatched(row, events)}
                return [row for row in events if row.get("execution_id") not in retired]
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
                          'mark_auxiliary_active','contain_auxiliary_device',
                          'record_execution_not_dispatched','record_auxiliary_on_outcome')
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
        # Aborts additionally require the original canonical claim and OFF
        # barrier, checked by _borehole_terminal_proven. A containment summary
        # alone never releases a claim.
        return _verified_borehole_completion(item)
    if auxiliary:
        return (action in {"record_auxiliary_completed",
                "record_auxiliary_control_pulse_stopped"}
            or (action == "contain_auxiliary_device"
                and item.get("shutdown_verified") is True))
    if action == "record_completed":
        if item.get("state") == "Stopped" or item.get("weather_stop_evidence") is not None:
            from modules.telemetry.rootline_irrigation_job_contract import validate_weather_stopped_execution
            return validate_weather_stopped_execution(item)
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


_BOREHOLE_ABORT_CONTRACT = "rootline_borehole_aborted_start.v1"
_BOREHOLE_STATE_ACTIONS = {
    "claim_borehole_before_on", "mark_borehole_active", "claim_borehole_off_attempt",
    "record_borehole_completed", "record_borehole_aborted", "contain_borehole",
    "record_execution_not_dispatched", "record_borehole_on_outcome",
}


def _borehole_state_rows(cursor):
    cursor.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s
          and (jsonb_typeof(review_json->'rootline_execution') is distinct from 'object'
            or jsonb_typeof(review_json->'rootline_execution'->'action') is distinct from 'string'
            or review_json->'rootline_execution'->>'action'=any(%s))
        order by created_at desc,review_event_id""", (EVENT_SOURCE, sorted(_BOREHOLE_STATE_ACTIONS)))
    return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
            for row in cursor.fetchall()]


def _borehole_abort_canonical(claim, barrier, provider, read_started_at, aborted_at):
    evidence = {"execution_id": claim["execution_id"], "device_key": claim["device_key"],
        "consumption_key": claim["consumption_key"], "claim_event_id": claim["event_id"],
        "claim_sha256": _event_digest(claim), "off_barrier_event_id": barrier["event_id"],
        "off_barrier_sha256": _event_digest(barrier), "final_state": "OFF"}
    return {**evidence, "evidence_id": "CANONICAL-ABORT-" + _event_digest({
        **evidence, "provider_final_off_evidence": provider,
        "abort_read_started_at": read_started_at, "aborted_at": aborted_at})}


def _verified_borehole_abort(item, rows):
    """A failed startup retires only with its actual canonical claim and OFF fence."""
    from datetime import timedelta
    if (not isinstance(item, dict) or item.get("action") != "record_borehole_aborted"
            or item.get("terminal_contract") != _BOREHOLE_ABORT_CONTRACT
            or item.get("state") != "Aborted" or item.get("shutdown_verified") is not True
            or item.get("operational_proof") != "startup_aborted_provider_off"
            or item.get("objective_satisfied") is not False
            or item.get("event_id") != _event_id("record_borehole_aborted", item)):
        return False
    identity = item.get("execution_id")
    matching = [row for row in rows if row.get("execution_id") == identity]
    claims = [row for row in matching if row.get("action") == "claim_borehole_before_on"]
    if (len(claims) != 1 or not _valid_borehole_eligibility(claims[0])
            or sum(row.get("action") == "record_borehole_aborted" for row in matching) > 1
            or any(row.get("action") in {"mark_borehole_active", "record_borehole_completed"}
                   for row in matching)):
        return False
    claim = claims[0]
    if (claim.get("event_id") != _event_id("claim_borehole_before_on", claim)
            or not _managed_claim_matches(matching, item, _managed_family(borehole=True))):
        return False
    canonical = item.get("canonical_abort_evidence")
    provider = item.get("provider_final_off_evidence")
    if not isinstance(canonical, dict) or not isinstance(provider, dict):
        return False
    barriers = [row for row in matching if row.get("action") == "claim_borehole_off_attempt"
        and row.get("event_id") == canonical.get("off_barrier_event_id")
        and type(row.get("attempt")) is int and 1 <= row["attempt"] <= 3
        and row.get("event_id") == _event_id("claim_borehole_off_attempt", row)]
    started, observed, finished = map(_time, (item.get("abort_read_started_at"),
        provider.get("retrieved_at"), item.get("aborted_at")))
    if (len(barriers) != 1 or any(at is None or at.tzinfo is None
            for at in (started, observed, finished))
            or not started <= observed <= finished or finished-observed > timedelta(minutes=5)
            or provider.get("execution_id") != identity
            or provider.get("device_id") != "1002851416"
            or type(provider.get("channel")) is not int or provider["channel"] != 1
            or provider.get("authoritative") is not True or provider.get("state") != "OFF"
            or not _sha256_text(provider.get("evidence_id"))):
        return False
    return canonical == _borehole_abort_canonical(claim, barriers[0], provider,
        item["abort_read_started_at"], item["aborted_at"])


def _borehole_terminal_proven(rows):
    return any(_verified_borehole_completion(row) or _verified_borehole_abort(row, rows)
               or _verified_not_dispatched(row, rows)
               for row in rows)


def _active_borehole(rows):
    """Use identical terminal proof for inventory and locked new-claim admission."""
    candidates = {}
    by_execution = {}
    for row in rows:
        if isinstance(row.get("action"), (list, dict)):
            raise RootlineExecutionStoreUnavailable("borehole_event_action_invalid")
        identity = str(row.get("execution_id") or "")
        by_execution.setdefault(identity, []).append(row)
        if _is_active_candidate(row, "mark_borehole_active", "claim_borehole_before_on"):
            candidates.setdefault(identity, row)
    for identity, row in candidates.items():
        if not _borehole_terminal_proven(by_execution[identity]):
            result = ({**row, "state": "claimed_recovery_required"}
                if row.get("action") == "claim_borehole_before_on" else row)
            if _no_send_preimage(by_execution[identity], identity) is not None:
                result = {**result, "on_not_dispatched": True}
            return result
    return None


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


def _no_send_preimage(rows, execution_id):
    matching = [row for row in rows if row.get("execution_id") == execution_id]
    claims = [row for row in matching if row.get("action") in {
        "claim_before_on", "claim_auxiliary_before_on", "claim_borehole_before_on"}]
    outcomes = [row for row in matching if row.get("action") in {
        "record_on_outcome", "record_auxiliary_on_outcome", "record_borehole_on_outcome"}]
    if (len(claims) != 1 or len(outcomes) != 1
            or (outcomes[0].get("on_outcome") or {}).get("provider_command_attempted") is not False
            or (outcomes[0].get("on_outcome") or {}).get("accepted_unambiguous") is not False
            or any(row.get("action") in {"mark_active", "mark_auxiliary_active", "mark_borehole_active"}
                for row in matching)):
        return None
    claim = claims[0]
    if not claim.get("provider_capacity_permit"):
        return None
    return claim, outcomes[0]


def _verified_not_dispatched(item, rows):
    from datetime import timedelta
    if (not isinstance(item, dict) or item.get("action") != "record_execution_not_dispatched"
            or item.get("terminal_contract") != "rootline_proven_no_send.v1"
            or item.get("not_dispatched_verified") is not True
            or item.get("event_id") != _event_id("record_execution_not_dispatched", item)):
        return False
    preimage = _no_send_preimage(rows, item.get("execution_id"))
    if not preimage:
        return False
    claim, outcome = preimage
    evidence = item.get("shutdown_evidence") or {}
    started, observed, finished = map(_time, (item.get("read_started_at"),
        evidence.get("retrieved_at"), item.get("retired_at")))
    device = claim.get("device_id") or ("1002851416" if claim.get("device_key") ==
        "ewelink:ewelink_owner_account:1002851416:1" else None)
    channel = claim.get("channel") or (1 if device == "1002851416" else None)
    return (item.get("claim_event_id") == claim.get("event_id")
        and item.get("claim_sha256") == _event_digest(claim)
        and item.get("outcome_event_id") == outcome.get("event_id")
        and item.get("outcome_sha256") == _event_digest(outcome)
        and evidence.get("authoritative") is True and evidence.get("state") == "OFF"
        and evidence.get("device_id") == device and evidence.get("channel") == channel
        and _sha256_text(evidence.get("evidence_id") or evidence.get("response_digest"))
        and all(at is not None and at.tzinfo is not None for at in (started, observed, finished))
        and started <= observed <= finished and finished-observed <= timedelta(seconds=60))


def _retire_not_dispatched_execution(body):
    """Retire a locally refused ON only after exact canonical no-send and fresh OFF.

    This cannot reconcile an absent/ambiguous response or an historical failed
    startup.  It preserves the claim/outcome and credits no runtime or delivery.
    """
    from datetime import timedelta
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty
    read = body.get("read_final_off")
    identity = str(body.get("execution_id") or "")
    if not identity or not callable(read):
        return {"success": False, "created": False}
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
            read_only=False) as connection, connection.cursor() as cursor:
        cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
        cursor.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
        rows = _managed_edge_rows(cursor, identity)
        existing = next((row for row in rows if _verified_not_dispatched(row, rows)), None)
        if existing:
            return {"success": True, "created": False, "execution": existing}
        preimage = _no_send_preimage(rows, identity)
        if not preimage:
            return {"success": False, "created": False, "status": "no_send_preimage_unproven"}
        claim, outcome = preimage
        started = connection.execute("select clock_timestamp()").fetchone()[0]
        try:
            with execution_duty(claim, deadline=started+timedelta(seconds=8)):
                evidence = read()
        except Exception:
            evidence = {}
        finished = connection.execute("select clock_timestamp()").fetchone()[0]
        retired = {**claim, "state": "NotDispatched", "terminal_contract": "rootline_proven_no_send.v1",
            "not_dispatched_verified": True, "shutdown_verified": True,
            "objective_satisfied": False, "claim_event_id": claim["event_id"],
            "claim_sha256": _event_digest(claim), "outcome_event_id": outcome["event_id"],
            "outcome_sha256": _event_digest(outcome), "shutdown_evidence": evidence,
            "read_started_at": started.isoformat(), "retired_at": finished.isoformat()}
        retired = _stored_event_body("record_execution_not_dispatched", retired,
            _event_id("record_execution_not_dispatched", retired))
        if not _verified_not_dispatched(retired, rows):
            return {"success": False, "created": False, "status": "no_send_off_proof_pending"}
        result = _insert_managed_event(cursor, "record_execution_not_dispatched", retired)
        return {**result, "execution": retired, "status": "execution_not_dispatched"}


def _not_dispatched_ids(cursor):
    """Verify stored terminal markers against their actual canonical preimages."""
    cursor.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s
          and review_json->'rootline_execution'->>'action'='record_execution_not_dispatched'""",
        (EVENT_SOURCE,))
    terminals = [row[0] for row in cursor.fetchall()]
    identities = [row.get("execution_id") for row in terminals if isinstance(row, dict)]
    if not identities:
        return []
    cursor.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s and chatwoot_conversation_id=any(%s)""", (EVENT_SOURCE, identities))
    events = [row[0] for row in cursor.fetchall()]
    return [row["execution_id"] for row in terminals if _verified_not_dispatched(row, events)]


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
            if _a_commissioning_unresolved(connection):
                return {"success": True, "created": False, "status": "a_commissioning_unresolved"}
            retired_no_send = _not_dispatched_ids(cursor)
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "execution_replay"}
            if body.get("job_id"):
                cursor.execute("""select review_json->'rootline_execution'->>'resolution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'job_id'=%s
                      and review_json->'rootline_execution'->>'action'='record_job_resolution'
                      and (review_json->'rootline_execution'->>'resolution'='Cancelled'
                          or (review_json->'rootline_execution'->>'resolution'='Deferred'
                              and review_json->'rootline_execution'->>'terminal'='true'))
                    limit 1""", (EVENT_SOURCE, str(body["job_id"])))
                resolution = cursor.fetchone()
                if resolution:
                    return {"success": True, "created": False,
                        "status": "parent_job_cancelled" if resolution[0] == "Cancelled" else "parent_job_deferred"}
            cursor.execute("""select 1
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'action'='claim_before_on'
                  and review_json->'rootline_execution'->>'consumption_key'=%s
                  and not (review_json->'rootline_execution'->>'execution_id'=any(%s))
                limit 1""", (EVENT_SOURCE, consumption_key, retired_no_send))
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
                  and not (claim.review_json->'rootline_execution'->>'execution_id'=any(%s))
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
                limit 1""", (EVENT_SOURCE, retired_no_send, EVENT_SOURCE))
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
        retired_no_send = _not_dispatched_ids(cursor)
        cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_execution'->>'action'='claim_before_on'
              and review_json->'rootline_execution'->>'job_id'=%s
              and (review_json->'rootline_execution'->>'segment_number')::int=%s
              and not (review_json->'rootline_execution'->>'execution_id'=any(%s))
            limit 1""", (EVENT_SOURCE, job_id, segment_number, retired_no_send))
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
            retired_no_send = _not_dispatched_ids(cursor)
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
                   and review_json->'rootline_execution'->>'consumption_key'=%s
                   and not (review_json->'rootline_execution'->>'execution_id'=any(%s)))) limit 1""",
                (EVENT_SOURCE,event_id,consumption_key,retired_no_send))
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
                      and review_json->'rootline_execution'->>'pulse_number'=%s
                      and not (review_json->'rootline_execution'->>'execution_id'=any(%s)) limit 1""",
                    (EVENT_SOURCE, str(body.get("zone_execution_id") or ""),
                     str(body.get("pulse_number") or ""), retired_no_send))
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
                account = mixing_daily_accounting([row[0] for row in cursor.fetchall()
                    if row[0].get("execution_id") not in retired_no_send]
                    + [{**body, "action":"claim_auxiliary_before_on"}], now=at)
                if not account["history_valid"] or account["reserved_seconds"] > 1800:
                    return {"success":True,"created":False,"status":"daily_mixing_budget_unavailable"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and not (claim.review_json->'rootline_execution'->>'execution_id'=any(%s))
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
                (EVENT_SOURCE,retired_no_send,auxiliary_id,str(body.get("device_id") or ""),
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
        if _active_borehole(_borehole_state_rows(cursor)) is not None:
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
        "terminals":{"record_borehole_completed", "record_borehole_aborted", "contain_borehole",
            "record_execution_not_dispatched"}} if borehole else
        {"claim":"claim_auxiliary_before_on", "dispatch":"claim_auxiliary_dispatch",
        "active":"mark_auxiliary_active", "off":"claim_auxiliary_off_attempt",
        "outcome":"record_auxiliary_on_outcome",
        "terminals":{"record_auxiliary_completed", "record_auxiliary_control_pulse_stopped",
                     "contain_auxiliary_device", "record_execution_not_dispatched"}})


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
            if borehole and action in {family["off"], "record_borehole_completed"}:
                if _borehole_terminal_proven(rows):
                    if action == "record_borehole_completed":
                        event_id = _event_id(action, body)
                        exact = _stored_event_body(action, body, event_id)
                        if any(row == exact and _verified_borehole_completion(row) for row in rows):
                            return {"success":True,"created":False,"event_id":event_id}
                    return {"success":False,"created":False,"status":"borehole_execution_retired"}
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


def _dispatch_borehole_off_edge(body):
    """Consume one existing OFF slot durably, then serialize its sender with retirement."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    dispatch = body.get("dispatch")
    if not callable(dispatch):
        return {"accepted_unambiguous":False, "provider_command_attempted":False,
            "status":"borehole_off_dispatch_invalid"}
    slot = {"execution_id":body.get("execution_id"), "attempt":body.get("attempt")}
    claimed = _guarded_managed_transition("claim_borehole_off_attempt", slot)
    if claimed.get("created") is not True:
        return {"accepted_unambiguous":False, "provider_command_attempted":False,
            "status":"borehole_off_attempt_unavailable"}
    # A crash here consumes the slot. Neither a restart nor a duplicate sender
    # can reuse it. All provider I/O below remains inside the shared locks.
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
            rows = _managed_edge_rows(cursor, slot["execution_id"])
            if _borehole_terminal_proven(rows):
                return {"accepted_unambiguous":False, "provider_command_attempted":False,
                    "status":"borehole_execution_retired"}
            try:
                outcome = dispatch()
            except Exception:
                outcome = {"accepted_unambiguous":False, "status":"borehole_off_outcome_unknown"}
            if not isinstance(outcome, dict):
                outcome = {"accepted_unambiguous":False, "status":"borehole_off_outcome_unknown"}
            _insert_managed_event(cursor, "record_borehole_off_outcome", {**slot, "outcome":outcome})
            return {**outcome, "provider_command_attempted":True}


def _record_borehole_aborted(body):
    """Retire a failed startup from fresh OFF while all old ON/OFF senders are fenced."""
    from datetime import datetime, timezone
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    read_final_off = body.pop("read_final_off", None)
    if not callable(read_final_off) or not str(body.get("execution_id") or ""):
        return {"success":False,"created":False,"status":"borehole_abort_reader_required"}
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
            rows = _managed_edge_rows(cursor, body["execution_id"])
            family = _managed_family(borehole=True)
            claims = [row for row in rows if row.get("action") == family["claim"]]
            if (not _managed_claim_matches(rows, body, family) or len(claims) != 1
                    or not _valid_borehole_eligibility(claims[0])):
                return {"success":False,"created":False,"status":"borehole_abort_claim_unproven"}
            previous = [row for row in rows if row.get("action") == "record_borehole_aborted"]
            if previous:
                if len(previous) == 1 and _verified_borehole_abort(previous[0], rows):
                    return {"success":True,"created":False,"status":"borehole_already_aborted",
                        "execution":previous[0]}
                return {"success":False,"created":False,"status":"borehole_abort_conflict"}
            barriers = [row for row in rows if row.get("action") == family["off"]
                and type(row.get("attempt")) is int and 1 <= row["attempt"] <= 3
                and row.get("event_id") == _event_id(family["off"], row)]
            if (not barriers or any(row.get("action") in {family["active"], "record_borehole_completed"}
                                    for row in rows)):
                return {"success":False,"created":False,"status":"borehole_abort_barrier_unproven"}
            # The barrier is durable before this read and also retires late ON.
            # Waiting OFF senders must recheck this terminal before provider I/O.
            read_started_at = datetime.now(timezone.utc).isoformat()
            try:
                final = read_final_off()
            except Exception:
                final = None
            aborted_at = datetime.now(timezone.utc).isoformat()
            final = dict(final) if isinstance(final, dict) else {}
            if final.get("execution_id", body["execution_id"]) != body["execution_id"]:
                return {"success":False,"created":False,"status":"borehole_abort_off_unproven"}
            provider = {**final, "execution_id":body["execution_id"]}
            claim = claims[0]
            aborted = {**claim, "action":"record_borehole_aborted", "state":"Aborted",
                "terminal_contract":_BOREHOLE_ABORT_CONTRACT, "reason":body.get("reason"),
                # These count durable consumed attempts, not proven HTTP sends
                # or pumping. Keep the original claim and every outcome intact.
                "on_attempts":int(any(row.get("action") in {family["dispatch"], family["outcome"]}
                    for row in rows)),
                "off_attempts":len({row["attempt"] for row in barriers}),
                "abort_read_started_at":read_started_at, "aborted_at":aborted_at,
                "shutdown_verified":True, "objective_satisfied":False,
                "operational_proof":"startup_aborted_provider_off",
                "provider_final_off_evidence":provider,
                "canonical_abort_evidence":_borehole_abort_canonical(claim, barriers[0],
                    provider, read_started_at, aborted_at)}
            aborted["event_id"] = _event_id("record_borehole_aborted", aborted)
            if not _verified_borehole_abort(aborted, rows):
                return {"success":False,"created":False,"status":"borehole_abort_off_unproven",
                    "provider_final_off_evidence":final}
            result = _insert_managed_event(cursor, "record_borehole_aborted", aborted)
            return {**result, "status":"borehole_start_aborted", "execution":
                _stored_event_body("record_borehole_aborted", aborted, result["event_id"])}


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
    if body.get("state") == "Stopped":
        details.update(terminal_contract=body.get("terminal_contract"),
            terminal_sha256=body.get("terminal_sha256"), reason=body.get("reason"),
            remaining_seconds=body.get("remaining_seconds"),
            weather_stop_evidence=body.get("weather_stop_evidence"),
            partial_observation=body.get("partial_observation"),
            next_action_owner="ROOTLINE", next_trigger=body.get("next_trigger"))
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
                return (existing[0] == _time(event["event_at"])
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


# First-use A commissioning is an operator operation, never a watering job.
# The existing review table and irrigation lock own its durable sender fence.
_A_COMMISSIONING_SOURCE = "oom_sakkie_rootline_operational_intake"
_A_COMMISSIONING_VERSION = "rootline_a_commissioning_state.v1"
_A_COMMISSIONING_ACTIONS = frozenset({"load_a_commissioning_operation",
    "claim_a_commissioning_before_on", "dispatch_a_commissioning_on_edge",
    "claim_a_commissioning_off_attempt", "finish_a_commissioning",
    "revoke_a_commissioning", "observe_a_commissioning"})
_A_COMMISSIONING_SENDER = ContextVar("rootline_a_commissioning_sender", default=None)
_A_COMMISSIONING_OBSERVER = ContextVar("rootline_a_commissioning_observer", default=None)
_A_NO_SEND_REASONS = frozenset({"transport_not_configured", "provider_capacity_not_available",
    "a_commissioning_sender_refused", "provider_command_deadline_reached",
    "a_commissioning_binding_changed", "a_commissioning_configuration_read_failed"})
_A_COMMISSIONING_SOURCE_PATHS = (
    "modules/telemetry/rootline_ifttt_transport.py",
    "modules/telemetry/rootline_irrigation_execution_store.py",
    "modules/telemetry/rootline_ewelink_request_budget.py",
    "modules/telemetry/rootline_ewelink_readback.py",
    "modules/telemetry/rootline_device_registry.py",
    "modules/telemetry/rootline_ewelink_commissioned_baseline.py",
)


def _a_need(condition, reason):
    if not condition:
        raise ValueError("a_commissioning_" + reason)


def _a_time(value):
    parsed = _time(value)
    _a_need(parsed is not None and parsed.tzinfo is not None
        and parsed.utcoffset() is not None, "aware_time_required")
    return parsed.astimezone(timezone.utc)


def _a_hex(value, length=64):
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{%d}" % length, value) is not None


def _a_operation(value):
    _a_need(_a_hex(value, 32), "operation_identity_invalid")
    return value


def _a_id(operation, phase):
    return "ROOTLINE-OP-" + _a_operation(operation) + "-" + phase


def _a_rows(connection, operation):
    with connection.cursor() as cursor:
        cursor.execute("""select review_json->'rootline_operational_intake'
            from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_operational_intake'->>'operation_id'=%s
            order by created_at,review_event_id""", (_A_COMMISSIONING_SOURCE, operation))
        rows = [row[0] for row in cursor.fetchall()]
    _a_need(all(isinstance(row, dict) for row in rows), "canonical_rows_invalid")
    return rows


def _a_phase(rows, operation, phase):
    matching = [row for row in rows if row.get("event_id") == _a_id(operation, phase)]
    _a_need(len(matching) <= 1, "duplicate_canonical_phase")
    return matching[0] if matching else None


def is_a_commissioning_duty(value):
    """Exact operator-claim family, never an ordinary execution or bypass flag."""
    operation = value.get("operation_id")
    return (_a_hex(operation, 32) and value.get("version") == _A_COMMISSIONING_VERSION
        and value.get("purpose") == "operator_commissioning" and value.get("phase") == "A-CLAIM"
        and value.get("execution_id") == _a_id(operation, "A-EXECUTION")
        and value.get("device_id") == "100204e9bc" and value.get("channel") == 4
        and value.get("zone_id") == "A12345")


def _a_observation_valid(row, claim, *, target_state):
    from modules.telemetry.rootline_ifttt_transport import (
        a_commissioning_final_off_verified, a_commissioning_start_verified)
    validate = a_commissioning_start_verified if target_state == "ON" else a_commissioning_final_off_verified
    return (_a_time(claim["claimed_at"]) <= _a_time(row.get("database_read_started_at"))
        <= _a_time(row.get("database_read_completed_at")) <= _a_time(row.get("recorded_at"))
        and _a_time(row.get("read_started_at")) <= _a_time(row.get("read_completed_at"))
        and validate(row.get("observation"), now=_a_time(row.get("read_completed_at")),
            after=_a_time(row.get("read_started_at"))))


def _a_projection(rows, operation):
    claim = _a_phase(rows, operation, "A-CLAIM")
    if claim is None:
        _a_need(not any(row.get("version") == _A_COMMISSIONING_VERSION for row in rows),
            "orphan_canonical_phase")
        return {"operation_id": operation, "operation_claim": None,
            "on_spent": False, "off_attempts": 0, "retired": False, "unresolved": False,
            "startup_state": "unclaimed", "delivered_start": None, "known_no_send": None}
    _a_need(is_a_commissioning_duty(claim)
        and type(claim.get("channel")) is int, "canonical_claim_invalid")
    digest = _event_digest(claim)
    phases = [row for row in rows if row.get("version") == _A_COMMISSIONING_VERSION
        and row.get("event_id") != claim["event_id"]]
    allowed = {"A-ON", "A-OFF-1", "A-OFF-2", "A-OFF-3", "A-REVOKED", "A-RETIRED",
        "A-NO-SEND", "A-STARTED"}
    _a_need(all(row.get("phase") in allowed
        and row.get("event_id") == _a_id(operation, row["phase"])
        and row.get("claim_sha256") == digest for row in phases), "canonical_phase_changed")
    on = _a_phase(rows, operation, "A-ON")
    stopped = _a_phase(rows, operation, "A-REVOKED")
    no_send = _a_phase(rows, operation, "A-NO-SEND")
    start = _a_phase(rows, operation, "A-STARTED")
    if no_send is not None:
        attempt = _a_phase(rows, operation, "ATTEMPT") or {}
        grant = (attempt.get("details") or {}).get("a_commissioning_grant") or {}
        expected_source = ((grant.get("runtime") or {}).get("source_pins") or {}).get(
            "modules/telemetry/rootline_ifttt_transport.py")
        _a_need(on is not None and start is None
            and no_send.get("on_slot_sha256") == _event_digest(on)
            and no_send.get("reason") in _A_NO_SEND_REASONS
            and no_send.get("provider_command_attempted") is False
            and no_send.get("provenance") == "installed_a_sender_pre_command_refusal.v1"
            and _a_hex(expected_source) and no_send.get("transport_source_sha256") == expected_source
            and _a_time(on["recorded_at"]) <= _a_time(no_send["recorded_at"]),
            "no_send_provenance_invalid")
    if start is not None:
        _a_need(on is not None and no_send is None
            and start.get("on_slot_sha256") == _event_digest(on)
            and _a_time(on["recorded_at"]) <= _a_time(start.get("database_read_started_at"))
            and _a_observation_valid(start, claim, target_state="ON")
            and start.get("within_startup_window") is (
                _a_time(start["database_read_completed_at"]) <= _a_time(claim["startup_verification_deadline"])),
            "delivered_start_invalid")
    startup = "delivered_start" if start else "source_proven_no_send" if no_send else "outstanding" if on else "never_sent"
    retired = _a_phase(rows, operation, "A-RETIRED")
    if retired is not None:
        _a_need(stopped is not None and startup != "outstanding"
            and retired.get("safe_branch") == startup
            and retired.get("shutdown_verified") is True
            and retired.get("reserve_release_verified") is True
            and retired.get("watering_credit_created") is False
            and _a_time(stopped["recorded_at"]) <= _a_time(retired.get("database_read_started_at"))
            and retired.get("final_off_evidence") == retired.get("observation")
            and _a_observation_valid(retired, claim, target_state="OFF"), "retirement_invalid")
        if start:
            _a_need(retired.get("delivered_start_sha256") == _event_digest(start)
                and _a_time(start["recorded_at"]) <= _a_time(retired["database_read_started_at"])
                and _a_time(start["read_completed_at"]) <= _a_time(retired["read_started_at"]),
                "retirement_precedes_delivered_start")
        elif no_send:
            _a_need(retired.get("known_no_send_sha256") == _event_digest(no_send)
                and _a_time(no_send["recorded_at"]) <= _a_time(retired["database_read_started_at"]),
                "retirement_precedes_no_send")
    return {"operation_id": operation, "operation_claim": claim, "on_spent": on is not None,
        "off_attempts": sum(_a_phase(rows, operation, "A-OFF-" + str(n)) is not None for n in (1, 2, 3)),
        "revoked": stopped is not None, "retired": retired is not None, "unresolved": retired is None,
        "startup_state": startup, "delivered_start": start, "known_no_send": no_send,
        "watering_credit_created": False, "native_auto_off_proven": False}


def _a_commissioning_unresolved(connection):
    # No age, expiry, helper completion or ordinary history can release this fence.
    # Retain each A operation's original ATTEMPT grant as well as its A phases:
    # the unchanged reducer needs that source provenance to verify no-send.
    # Keep malformed A anchors too, even when their operation identity is absent.
    with connection.cursor() as cursor:
        cursor.execute("""with journal as (
            select review_json->'rootline_operational_intake' as body,
                created_at,review_event_id,
                (review_json->'rootline_operational_intake'->>'version'=%s
                 or review_json->'rootline_operational_intake'->>'phase' like 'A-%%') as a_state
            from public.sam_live_stock_conversation_review_events
            where event_source=%s)
            select body from journal where a_state
                or body->>'operation_id' in (
                    select body->>'operation_id' from journal where a_state)
            order by created_at,review_event_id""", (_A_COMMISSIONING_VERSION, _A_COMMISSIONING_SOURCE))
        rows = [row[0] for row in cursor.fetchall()]
    try:
        _a_need(all(isinstance(row, dict) and _a_hex(row.get("operation_id"), 32)
            for row in rows), "fence_rows_invalid")
        for operation in {row["operation_id"] for row in rows}:
            if _a_projection([row for row in rows if row["operation_id"] == operation], operation)["unresolved"]:
                return True
    except (ValueError, TypeError, KeyError):
        return True
    return False


def _a_normal_irrigation_unresolved(connection):
    with connection.cursor() as cursor:
        cursor.execute("""select review_json->'rootline_execution'
            from public.sam_live_stock_conversation_review_events where event_source=%s
            order by created_at,review_event_id""", (EVENT_SOURCE,))
        rows = [row[0] for row in cursor.fetchall()]
    if any(not isinstance(row, dict) or not isinstance(row.get("action"), str) for row in rows):
        return True
    terminal = {row.get("execution_id") for row in rows
        if _terminal_closes_active(row) or _verified_not_dispatched(row, rows)}
    return any(row.get("action") in {"claim_before_on", "mark_active", "mark_stopping"}
        and row.get("execution_id") not in terminal for row in rows)


def _a_write(connection, operation, phase, material):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event)
    now = connection.execute("select clock_timestamp()").fetchone()[0]
    body = {**material, "event_id": _a_id(operation, phase),
        "mission_id": "RMQ-20260813-04", "operation_id": operation,
        "mode": "A_CH4", "version": _A_COMMISSIONING_VERSION,
        "purpose": "operator_commissioning", "phase": phase,
        "recorded_at": now.isoformat(), "watering_credit_created": False}
    event = build_sam_live_stock_review_event({"conversation_id": body["mission_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "rootline_operational_intake"},
        event_source=_A_COMMISSIONING_SOURCE)
    event.update(review_event_id=body["event_id"], chatwoot_conversation_id=body["mission_id"],
        review_json={"rootline_operational_intake": body}, decision_json={}, facts_json={},
        customer_message_excerpt="", sam_reply_excerpt="")
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: nullcontext(connection), created_at=now)
    _a_need(status < 400 and result.get("success") is True
        and result.get("created") is True, "phase_write_unproven")
    _a_need(_a_phase(_a_rows(connection, operation), operation, phase) == body,
        "phase_readback_mismatch")
    return body


def _a_grant(rows, operation, grant_digest, now):
    attempt = _a_phase(rows, operation, "ATTEMPT")
    command = _a_phase(rows, operation, "COMMAND")
    _a_need(isinstance(attempt, dict) and isinstance(command, dict), "root_journal_required")
    grant = (attempt.get("details") or {}).get("a_commissioning_grant")
    _a_need(isinstance(grant, dict) and _a_hex(grant_digest)
        and _event_digest(grant) == grant_digest, "canonical_grant_changed")
    exact = {"contract_version": "rootline_a_operator_grant.v1", "mission_id": "RMQ-20260813-04",
        "operation_id": operation, "zone_id": "A12345", "device_id": "100204e9bc", "channel": 4,
        "provider_account_binding": "ewelink_owner_account", "on_event": "irrigation_1_ch4_on",
        "off_event": "irrigation_1_ch4_off", "native_fail_stop_seconds": 3599,
        "max_on_attempts": 1, "max_off_attempts": 3, "ordinary_a_enabled": False,
        "standing_authority": False, "automatic_on_retry": False}
    _a_need(all(type(grant.get(key)) is type(value) and grant[key] == value
        for key, value in exact.items()), "grant_scope_invalid")
    owner = grant.get("owner_instruction")
    _a_need(isinstance(owner, dict) and owner.get("source") == "owner_codex_chat"
        and isinstance(owner.get("reference"), str) and bool(owner["reference"].strip())
        and _a_hex(owner.get("artifact_sha256")) and _a_hex(grant.get("root_review_sha256")),
        "owner_review_required")
    start, expiry, recovery = (_a_time(grant.get(key))
        for key in ("not_before", "on_expires_at", "recovery_deadline"))
    _a_need(start <= now < expiry <= recovery and recovery > start
        and recovery - start <= timedelta(hours=2)
        and _a_time(grant.get("owner_instruction_received_at")) <= start,
        "grant_window_closed")
    _a_need(type(grant.get("maximum_runtime_seconds")) is int
        and 1 <= grant["maximum_runtime_seconds"] <= 3599, "runtime_limit_invalid")
    _a_need(grant.get("observation_mode") in {"control_pulse", "native_timeout"}
        and type(grant.get("startup_verification_seconds")) is int
        and 1 <= grant["startup_verification_seconds"] <= 30
        and type(grant.get("observation_read_margin_seconds")) is int
        and 1 <= grant["observation_read_margin_seconds"] <= 60
        and expiry < _a_time(grant.get("observation_deadline")) < recovery,
        "observation_window_invalid")
    if grant["observation_mode"] == "native_timeout":
        _a_need(grant["maximum_runtime_seconds"] == 3599, "native_setting_changed")
    _a_need(type(grant.get("configuration_generation")) is int
        and grant["configuration_generation"] >= 1
        and _a_hex(grant.get("configuration_baseline_sha256"))
        and _a_hex(grant.get("configuration_sha256"))
        and _a_hex(grant.get("provider_account_digest"))
        and isinstance(grant.get("firmware"), str) and bool(grant["firmware"]),
        "configuration_binding_invalid")
    runtime = grant.get("runtime") or {}
    _a_need(_a_hex(runtime.get("revision"), 40)
        and runtime["revision"] == os.environ.get("RENDER_GIT_COMMIT")
        and runtime.get("service_id") == os.environ.get("RENDER_SERVICE_ID")
        and bool(runtime.get("service_id"))
        and runtime.get("hostname") == socket.gethostname()
        and str(os.environ.get("ROOTLINE_A_ENABLED") or "").lower() != "true",
        "loaded_runtime_changed")
    pins = runtime.get("source_pins")
    _a_need(isinstance(pins, dict) and set(pins) == set(_A_COMMISSIONING_SOURCE_PATHS),
        "source_pins_required")
    root = Path(__file__).resolve().parents[2]
    _a_need(all(_a_hex(pin) and hashlib.sha256((root / name).read_bytes()).hexdigest() == pin
        for name, pin in pins.items()), "installed_source_changed")
    for row, phase in ((attempt, "ATTEMPT"), (command, "COMMAND")):
        _a_need(row.get("version") == "rootline_owner_operator_commissioning.v1"
            and row.get("mode") == "A_CH4" and row.get("mission_id") == grant["mission_id"]
            and row.get("source") == "owner_codex_operator"
            and row.get("state") == "operator_commissioning_" + phase.lower()
            and row.get("owner_instruction") == owner
            and row.get("owner_instruction_received_at") == grant["owner_instruction_received_at"]
            and row.get("source_revision") == runtime["revision"]
            and row.get("deployed_revision") == runtime["revision"]
            and row.get("root_review_sha256") == grant["root_review_sha256"]
            and start <= _a_time(row.get("recorded_at")) <= now, "root_journal_binding_changed")
    _a_need((command.get("details") or {}).get("a_commissioning_grant_sha256") == grant_digest,
        "command_grant_changed")
    _a_need(not any(_a_phase(rows, operation, phase) is not None
        for phase in ("REVOKED", "RECOVERY", "CONTAINED", "COMPLETED", "A-REVOKED",
                      "A-OFF-1", "A-OFF-2", "A-OFF-3", "A-RETIRED")), "on_grant_stopped")
    return grant, command


def _a_claim_matches(state, supplied):
    _a_need(isinstance(supplied, dict) and state["operation_claim"] == supplied,
        "canonical_claim_changed")
    _a_need(not state["retired"], "operation_retired")
    return state["operation_claim"]


def _a_on_permitted(connection, rows, claim, configuration):
    from modules.telemetry.rootline_ifttt_transport import validate_a_commissioning_configuration
    now = connection.execute("select clock_timestamp()").fetchone()[0]
    grant, _ = _a_grant(rows, claim["operation_id"], claim["grant_sha256"], now)
    _a_need(timedelta(0) <= now - _a_time(claim["claimed_at"]) <= timedelta(seconds=30)
        and now < _a_time(claim["primary_stop_deadline"]), "on_edge_expired")
    validate_a_commissioning_configuration(configuration, grant=grant, now=now,
        after=_a_time(claim["claimed_at"]))
    _a_need(not _a_normal_irrigation_unresolved(connection), "normal_irrigation_unresolved")
    return grant


def authorize_a_commissioning_sender(operation_claim, state, idempotency_key, configuration=None):
    """Private locked capability; a dict, boolean or replayed claim cannot send."""
    context = _A_COMMISSIONING_SENDER.get()
    _a_need(isinstance(context, _ACommissioningSender) and not context.used
        and context.state == state and context.claim == operation_claim
        and idempotency_key == context.key, "locked_sender_required")
    connection, claim = context.connection, context.claim
    operation = claim["operation_id"]
    rows = _a_rows(connection, operation)
    projection = _a_projection(rows, operation)
    _a_claim_matches(projection, claim)
    _a_need(_a_phase(rows, operation, context.phase) == context.slot, "consumed_slot_changed")
    if state == "ON":
        grant = _a_on_permitted(connection, rows, claim, configuration)
        deadline = min(_a_time(grant["on_expires_at"]),
            _a_time(claim["claimed_at"]) + timedelta(seconds=30),
            _a_time(claim["primary_stop_deadline"]))
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        _a_need(remaining > 0, "on_edge_expired")
        edge_deadline = time.monotonic() + remaining
    else:
        _a_need(state == "OFF" and context.phase in {"A-OFF-1", "A-OFF-2", "A-OFF-3"},
            "owned_off_slot_required")
        # Exact owned OFF survives expiry, revocation and unavailable A proof.
        edge_deadline = None
    context.used = True
    return edge_deadline


class _ACommissioningSender:
    def __init__(self, connection, claim, state, phase, slot):
        self.connection, self.claim, self.state = connection, claim, state
        self.phase, self.slot, self.used = phase, slot, False
        self.network_attempted, self.known_no_send = False, None
        suffix = ":ON" if state == "ON" else ":OFF:" + phase.rsplit("-", 1)[1]
        self.key = claim["execution_id"] + suffix


    def note_known_no_send(self, reason):
        _a_need(not self.network_attempted and reason in _A_NO_SEND_REASONS, "no_send_marker_invalid")
        if self.state == "ON": self.known_no_send = reason

    def note_network_attempt(self):
        _a_need(self.known_no_send is None, "no_send_marker_conflict")
        self.network_attempted = True


class _ACommissioningObserver:
    def __init__(self, claim):
        self.claim, self.read_performed = claim, False
        self.safe_to_release, self.final_evidence = False, None


def _a_read_observation(connection, claim, transport, context):
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty
    database_start = connection.execute("select clock_timestamp()").fetchone()[0]
    _a_need(database_start <= _a_time(claim["recovery_deadline"]), "observation_window_closed")
    app_start = datetime.now(timezone.utc)
    with execution_duty(claim, deadline=claim["recovery_deadline"]):
        value = transport.read_a_commissioning_output(operation_claim=claim)
    app_end = datetime.now(timezone.utc)
    database_end = connection.execute("select clock_timestamp()").fetchone()[0]
    _a_need(database_end <= _a_time(claim["recovery_deadline"]), "observation_window_closed")
    _a_need(context.read_performed, "typed_observation_unproven")
    return {"observation": value, "read_started_at": app_start.isoformat(),
        "read_completed_at": app_end.isoformat(), "database_read_started_at": database_start.isoformat(),
        "database_read_completed_at": database_end.isoformat()}


def _a_commissioning_store(action, payload):
    from modules.oom_sakkie.bounded_postgres_read import (
        connect_bounded_rootline_postgres, is_database_unavailable)
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty
    body = dict(payload or {})
    operation = body.get("operation_id") or (body.get("operation_claim") or {}).get("operation_id")
    observer = None
    try:
        operation = _a_operation(operation)
        def connect():
            return connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                read_only=action == "load_a_commissioning_operation")
        with connect() as connection:
            if action != "load_a_commissioning_operation":
                connection.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            rows = _a_rows(connection, operation)
            state = _a_projection(rows, operation)
            if action == "load_a_commissioning_operation":
                return {"success": True, **state}
            if action == "claim_a_commissioning_before_on":
                _a_need(set(body) == {"operation_id", "grant_sha256", "configuration",
                    "provider_capacity_permit"}, "claim_shape_invalid")
                _a_need(state["operation_claim"] is None, "operation_already_claimed")
                now = connection.execute("select clock_timestamp()").fetchone()[0]
                grant, command = _a_grant(rows, operation, body["grant_sha256"], now)
                from modules.telemetry.rootline_ifttt_transport import validate_a_commissioning_configuration
                validate_a_commissioning_configuration(body["configuration"], grant=grant, now=now)
                _a_need((command.get("details") or {}).get("configuration_snapshot_sha256")
                    == _event_digest(body["configuration"]), "command_snapshot_changed")
                _a_need(not _a_commissioning_unresolved(connection)
                    and not _a_normal_irrigation_unresolved(connection), "controller_unresolved")
                _a_need(isinstance(body["provider_capacity_permit"], str)
                    and bool(body["provider_capacity_permit"]), "provider_capacity_required")
                on_admission = min(now + timedelta(seconds=30), _a_time(grant["on_expires_at"]))
                startup = on_admission + timedelta(seconds=grant["startup_verification_seconds"])
                observation = _a_time(grant["observation_deadline"])
                if grant["observation_mode"] == "native_timeout":
                    # IFTTT admission is not physical ON. This is a planned
                    # ceiling only; the helper must prove timely actual ON and
                    # derive its native interval from that first own receipt.
                    _a_need(observation >= startup + timedelta(seconds=3599),
                        "native_observation_window_too_short")
                    primary = min(observation, startup + timedelta(
                        seconds=3599 + grant["observation_read_margin_seconds"]))
                else:
                    primary = now + timedelta(seconds=grant["maximum_runtime_seconds"])
                    _a_need(primary <= observation, "pulse_observation_window_too_short")
                _a_need(primary < _a_time(grant["recovery_deadline"]), "recovery_window_too_short")
                claim = _a_write(connection, operation, "A-CLAIM", {
                    "execution_id": _a_id(operation, "A-EXECUTION"), "zone_id": "A12345",
                    "device_id": "100204e9bc", "channel": 4,
                    "grant_sha256": body["grant_sha256"],
                    "provider_capacity_permit": body["provider_capacity_permit"],
                    "claimed_at": now.isoformat(),
                    "primary_stop_deadline": primary.isoformat(),
                    "on_admission_deadline": on_admission.isoformat(),
                    "startup_verification_deadline": min(startup, primary).isoformat(),
                    "commissioning_observation_deadline": primary.isoformat(),
                    "recovery_deadline": grant["recovery_deadline"],
                    "observation_mode": grant["observation_mode"],
                    "observation_read_margin_seconds": grant["observation_read_margin_seconds"],
                    "native_fail_stop_seconds": 3599,
                    "configuration": body["configuration"]})
                return {"success": True, "created": True, "operation_claim": claim,
                    "history_event_created": False}
            claim = _a_claim_matches(state, body.get("operation_claim"))
            if action == "revoke_a_commissioning":
                _a_need(not state.get("revoked"), "already_revoked")
                row = _a_write(connection, operation, "A-REVOKED", {"claim_sha256": _event_digest(claim)})
                return {"success": True, "created": True, "revocation": row}
            transport = body.get("transport")
            from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
            _a_need(type(transport) is RootlineIFTTTTransport, "installed_transport_required")
            if action in {"observe_a_commissioning", "finish_a_commissioning"}:
                _a_need(set(body) == {"operation_claim", "transport"}, "observation_shape_invalid")
                finishing = action == "finish_a_commissioning"
                if finishing and state["startup_state"] == "outstanding":
                    return {"success": False, "created": False,
                        "status": "a_commissioning_startup_outstanding", "startup_state": "outstanding",
                        "provider_read_performed": False, "unresolved": True, "reserve_released": False}
                if finishing and not state["revoked"]:
                    # The same lock fences both not-yet-consumed and delayed
                    # local senders. A committed retirement can never race ON.
                    _a_write(connection, operation, "A-REVOKED", {"claim_sha256": _event_digest(claim)})
                context = observer = _ACommissioningObserver(claim)
                token = _A_COMMISSIONING_OBSERVER.set(context)
                try:
                    material = _a_read_observation(connection, claim, transport, context)
                    current = _a_projection(_a_rows(connection, operation), operation)
                    _a_claim_matches(current, claim)
                    if not finishing:
                        from modules.telemetry.rootline_ifttt_transport import a_commissioning_start_verified
                        if (current["on_spent"] and current["known_no_send"] is None
                                and current["delivered_start"] is None
                                and a_commissioning_start_verified(material["observation"],
                                    now=_a_time(material["read_completed_at"]),
                                    after=_a_time(material["read_started_at"]))):
                            _a_write(connection, operation, "A-STARTED", {
                                **material, "claim_sha256": _event_digest(claim),
                                "on_slot_sha256": _event_digest(_a_phase(rows, operation, "A-ON")),
                                "within_startup_window": _a_time(material["database_read_completed_at"])
                                    <= _a_time(claim["startup_verification_deadline"])})
                            current = _a_projection(_a_rows(connection, operation), operation)
                        return {"success": True, "created": current["delivered_start"] != state["delivered_start"],
                            "observation": material["observation"], "delivered_start": current["delivered_start"],
                            "startup_state": current["startup_state"], "provider_read_performed": True,
                            "unresolved": True, "reserve_released": False, "history_event_created": False}
                    from modules.telemetry.rootline_ifttt_transport import a_commissioning_final_off_verified
                    _a_need(current["startup_state"] != "outstanding"
                        and a_commissioning_final_off_verified(material["observation"],
                            now=_a_time(material["read_completed_at"]),
                            after=_a_time(material["read_started_at"])), "final_off_unproven")
                    start, no_send = current["delivered_start"], current["known_no_send"]
                    if start:
                        _a_need(_a_time(start["recorded_at"]) <= _a_time(material["database_read_started_at"])
                            and _a_time(start["read_completed_at"]) <= _a_time(material["read_started_at"]),
                            "final_off_precedes_start")
                    context.safe_to_release, context.final_evidence = True, material["observation"]
                    try:
                        with execution_duty(claim, deadline=claim["recovery_deadline"]):
                            released = transport.release_a_commissioning_capacity(
                                operation_claim=claim, evidence=material["observation"])
                        _a_need(released is True, "reserve_release_unproven")
                    except Exception:
                        return {"success": False, "created": False,
                            "status": "a_commissioning_reserve_release_unresolved", "provider_read_performed": True,
                            "observation": material["observation"], "unresolved": True, "reserve_released": False}
                    row = _a_write(connection, operation, "A-RETIRED", {
                        **material, "claim_sha256": _event_digest(claim), "shutdown_verified": True,
                        "final_off_evidence": material["observation"], "safe_branch": current["startup_state"],
                        "delivered_start_sha256": _event_digest(start) if start else None,
                        "known_no_send_sha256": _event_digest(no_send) if no_send else None,
                        "reserve_release_verified": True, "on_spent": current["on_spent"],
                        "off_attempts": current["off_attempts"], "native_auto_off_proven": False})
                    _a_need(_a_projection(_a_rows(connection, operation), operation)["retired"], "retirement_readback_failed")
                    return {"success": True, "created": True, "retirement": row,
                        "provider_read_performed": True, "reserve_released": True, "history_event_created": False}
                finally:
                    _A_COMMISSIONING_OBSERVER.reset(token)
            if action == "dispatch_a_commissioning_on_edge":
                _a_need(not state["on_spent"], "on_already_consumed")
                # Grant is checked before consumption and once more at the final
                # sender edge. The fresh provider snapshot is taken in txn 2.
                now = connection.execute("select clock_timestamp()").fetchone()[0]
                _a_grant(rows, operation, claim["grant_sha256"], now)
                _a_need(timedelta(0) <= now - _a_time(claim["claimed_at"]) <= timedelta(seconds=30),
                    "on_edge_expired")
                phase, desired = "A-ON", "ON"
            else:
                _a_need(action == "claim_a_commissioning_off_attempt", "action_invalid")
                attempt = body.get("attempt")
                _a_need(type(attempt) is int and 1 <= attempt <= 3
                    and attempt == state["off_attempts"] + 1, "off_slot_exhausted_or_replayed")
                phase, desired = "A-OFF-" + str(attempt), "OFF"
            slot = _a_write(connection, operation, phase, {"claim_sha256": _event_digest(claim)})
        # The consumed slot is committed BEFORE the sender transaction. A crash
        # or rollback after network I/O cannot make it reusable.
        with connect() as connection:
            connection.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            rows = _a_rows(connection, operation)
            current = _a_projection(rows, operation)
            _a_claim_matches(current, claim)
            _a_need(_a_phase(rows, operation, phase) == slot, "consumed_slot_changed")
            context = _ACommissioningSender(connection, claim, desired, phase, slot)
            token = _A_COMMISSIONING_SENDER.set(context)
            try:
                with execution_duty(claim):
                    result = transport.set_a_commissioning_state(operation_claim=claim,
                        state=desired, idempotency_key=context.key)
            finally:
                _A_COMMISSIONING_SENDER.reset(token)
            if desired == "ON" and context.known_no_send is not None and not context.network_attempted:
                _a_write(connection, operation, "A-NO-SEND", {
                    "claim_sha256": _event_digest(claim), "on_slot_sha256": _event_digest(slot),
                    "reason": context.known_no_send, "provider_command_attempted": False,
                    "provenance": "installed_a_sender_pre_command_refusal.v1",
                    "transport_source_sha256": hashlib.sha256((Path(__file__).resolve().parents[2]
                        / "modules/telemetry/rootline_ifttt_transport.py").read_bytes()).hexdigest()})
            settled = _a_projection(_a_rows(connection, operation), operation)
            return {"success": True, "created": True, "slot": slot,
                "sender_authorized": context.used, "outcome": result,
                "startup_state": settled["startup_state"], "known_no_send": settled["known_no_send"],
                "history_event_created": False}
    except (ValueError, TypeError, KeyError) as exc:
        return {"success": False, "created": False, "status": str(exc),
            "accepted_unambiguous": False,
            "provider_read_performed": bool(observer and observer.read_performed)}
    except Exception as exc:
        if is_database_unavailable(exc):
            raise RootlineExecutionStoreUnavailable(action) from exc
        # A spent phase stays spent even if the transport or post-send read fails.
        return {"success": False, "created": False, "status": "a_commissioning_outcome_unknown",
            "accepted_unambiguous": False,
            "provider_read_performed": bool(observer and observer.read_performed)}
