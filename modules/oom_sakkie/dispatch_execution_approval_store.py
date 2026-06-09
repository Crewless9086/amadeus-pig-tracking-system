import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.dispatch_decision_store import get_dispatch_request
from services.database_service import DATABASE_URL_ENV


DISPATCH_EXECUTION_APPROVAL_TYPES = {
    "approved_for_single_dry_run_execution",
    "rejected",
    "deferred",
    "review_note",
}
DISPATCH_EXECUTION_APPROVAL_EVENT_TYPES = {"review_note", "consumed_by_single_dry_run_result"}


def record_dispatch_execution_approval(dispatch_request_id, payload, database_url=None):
    dispatch_request_id = _clean_text(dispatch_request_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    approval_type = _clean_text(payload.get("approval_type", ""), 80)
    if not dispatch_request_id:
        return {"success": False, "status": "dispatch_request_id_required"}, 400
    if approval_type not in DISPATCH_EXECUTION_APPROVAL_TYPES:
        return {
            "success": False,
            "status": "invalid_approval_type",
            "allowed_approval_types": sorted(DISPATCH_EXECUTION_APPROVAL_TYPES),
        }, 400

    request_result, request_status = get_dispatch_request(dispatch_request_id, database_url=database_url)
    if request_status != 200:
        return request_result, request_status
    dispatch_request = request_result.get("dispatch_request", {})
    specialist_slug = _clean_text(dispatch_request.get("specialist_slug", ""), 80).lower()
    if specialist_slug != "sentinel":
        return {
            "success": False,
            "status": "single_dry_run_execution_gate_is_sentinel_only",
            "specialist_slug": specialist_slug,
        }, 400
    if approval_type == "approved_for_single_dry_run_execution":
        latest_decision = dispatch_request.get("latest_decision") or {}
        if latest_decision.get("decision_type") != "approved_for_design_review":
            return {
                "success": False,
                "status": "dispatch_design_not_approved",
                "required_decision": "approved_for_design_review",
                "latest_decision": latest_decision,
            }, 409

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = _dispatch_execution_approval_params(dispatch_request, payload)
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_execution_approvals (
                        approval_id,
                        dispatch_request_id,
                        status,
                        mode,
                        specialist_slug,
                        approval_type,
                        notes,
                        approved_by,
                        one_shot_scope_json,
                        next_gate,
                        executes_now,
                        dispatch_enabled,
                        runs_specialist_llm,
                        runs_specialist_tools,
                        writes,
                        applies_runtime_change,
                        dispatches_further,
                        created_at
                    )
                    values (
                        %(approval_id)s,
                        %(dispatch_request_id)s,
                        %(status)s,
                        %(mode)s,
                        %(specialist_slug)s,
                        %(approval_type)s,
                        %(notes)s,
                        %(approved_by)s,
                        %(one_shot_scope_json)s::jsonb,
                        %(next_gate)s,
                        %(executes_now)s,
                        %(dispatch_enabled)s,
                        %(runs_specialist_llm)s,
                        %(runs_specialist_tools)s,
                        %(writes)s,
                        %(applies_runtime_change)s,
                        %(dispatches_further)s,
                        now()
                    )
                    on conflict (approval_id) do nothing
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_execution_approval_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "single_dry_run_execution_approval_only",
        "approval_id": params["approval_id"],
        "dispatch_request_id": dispatch_request_id,
        "specialist_slug": params["specialist_slug"],
        "approval_type": params["approval_type"],
        "executes_now": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatches_further": False,
        "next_gate": params["next_gate"],
    }, 201


def list_dispatch_execution_approvals(limit=20, dispatch_request_id="", database_url=None):
    parsed_limit = _bounded_limit(limit)
    dispatch_request_id = _clean_text(dispatch_request_id, 100)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "execution_approvals": [],
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "execution_approvals": [],
        }, 500

    where = "where a.dispatch_request_id = %(dispatch_request_id)s" if dispatch_request_id else ""
    params = {"limit": parsed_limit, "dispatch_request_id": dispatch_request_id}
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select a.approval_id, a.dispatch_request_id, a.status, a.mode,
                           a.specialist_slug, a.approval_type, a.notes, a.approved_by,
                           a.one_shot_scope_json, a.next_gate,
                           a.executes_now, a.dispatch_enabled, a.runs_specialist_llm,
                           a.runs_specialist_tools, a.writes, a.applies_runtime_change,
                           a.dispatches_further, a.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_dispatch_execution_approvals a
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_dispatch_execution_approval_events e
                        where e.approval_id = a.approval_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    {where}
                    order by a.created_at desc
                    limit %(limit)s
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_execution_approval_read_failed",
            "error_type": exc.__class__.__name__,
            "execution_approvals": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "single_dry_run_execution_approval_queue",
        "executes_now": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatches_further": False,
        "execution_approvals": [_dispatch_execution_approval_row(row) for row in rows],
    }, 200


def get_dispatch_execution_approval(approval_id, database_url=None):
    approval_id = _clean_text(approval_id, 100)
    if not approval_id:
        return {"success": False, "status": "approval_id_required", "execution_approval": {}}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "execution_approval": {}}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "execution_approval": {}}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select a.approval_id, a.dispatch_request_id, a.status, a.mode,
                           a.specialist_slug, a.approval_type, a.notes, a.approved_by,
                           a.one_shot_scope_json, a.next_gate,
                           a.executes_now, a.dispatch_enabled, a.runs_specialist_llm,
                           a.runs_specialist_tools, a.writes, a.applies_runtime_change,
                           a.dispatches_further, a.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_dispatch_execution_approvals a
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_dispatch_execution_approval_events e
                        where e.approval_id = a.approval_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where a.approval_id = %(approval_id)s
                    limit 1
                    """,
                    {"approval_id": approval_id},
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_execution_approval_read_failed",
            "error_type": exc.__class__.__name__,
            "execution_approval": {},
        }, 503

    if not row:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_execution_approval_not_found",
            "approval_id": approval_id,
            "execution_approval": {},
        }, 404
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "single_dry_run_execution_approval_detail",
        "executes_now": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatches_further": False,
        "execution_approval": _dispatch_execution_approval_row(row),
    }, 200


def dispatch_execution_approval_consumed(approval_id, database_url=None):
    approval_id = _clean_text(approval_id, 100)
    if not approval_id:
        return {"success": False, "status": "approval_id_required", "consumed": False}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "consumed": False}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "consumed": False}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select exists (
                        select 1
                        from public.oom_sakkie_dispatch_execution_approval_events
                        where approval_id = %(approval_id)s
                          and event_type = 'consumed_by_single_dry_run_result'
                    )
                    """,
                    {"approval_id": approval_id},
                )
                consumed = bool(cursor.fetchone()[0])
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_execution_approval_event_read_failed",
            "error_type": exc.__class__.__name__,
            "consumed": False,
        }, 503

    return {"success": True, "configured": True, "status": "ok", "consumed": consumed}, 200


def record_dispatch_execution_approval_event(approval_id, payload, database_url=None, allow_consumed=False):
    approval_id = _clean_text(approval_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 60)
    if not approval_id:
        return {"success": False, "status": "approval_id_required"}, 400
    if event_type not in DISPATCH_EXECUTION_APPROVAL_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(DISPATCH_EXECUTION_APPROVAL_EVENT_TYPES),
        }, 400
    if event_type == "consumed_by_single_dry_run_result" and not allow_consumed:
        return {
            "success": False,
            "status": "consumed_event_is_runner_only",
        }, 403

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "event_id": _event_id(approval_id, event_type),
        "approval_id": approval_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_execution_approval_events (
                        event_id,
                        approval_id,
                        event_type,
                        notes,
                        recorded_by,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(approval_id)s,
                        %(event_type)s,
                        %(notes)s,
                        %(recorded_by)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_execution_approval_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "approval_id": approval_id,
        "event_type": event_type,
        "executes_now": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatches_further": False,
    }, 201


def _dispatch_execution_approval_params(dispatch_request, payload):
    scope = payload.get("one_shot_scope") if isinstance(payload.get("one_shot_scope"), dict) else {}
    approval_type = _clean_text(payload.get("approval_type", ""), 80)
    return {
        "approval_id": _clean_text(payload.get("approval_id", ""), 100)
        or _approval_id(dispatch_request.get("dispatch_request_id", ""), approval_type),
        "dispatch_request_id": _clean_text(dispatch_request.get("dispatch_request_id", ""), 100),
        "status": "recorded_for_single_dry_run_execution_gate",
        "mode": "single_dry_run_execution_approval_only",
        "specialist_slug": _clean_text(dispatch_request.get("specialist_slug", ""), 80).lower(),
        "approval_type": approval_type,
        "notes": _clean_text(payload.get("notes", ""), 1600),
        "approved_by": _clean_text(payload.get("approved_by", "owner"), 80),
        "one_shot_scope_json": _json(scope),
        "next_gate": "implementation_diff_review_before_any_specialist_llm_call",
        "executes_now": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatches_further": False,
    }


def _dispatch_execution_approval_row(row):
    (
        approval_id,
        dispatch_request_id,
        status,
        mode,
        specialist_slug,
        approval_type,
        notes,
        approved_by,
        one_shot_scope_json,
        next_gate,
        executes_now,
        dispatch_enabled,
        runs_specialist_llm,
        runs_specialist_tools,
        writes,
        applies_runtime_change,
        dispatches_further,
        created_at,
        event_type,
        event_notes,
        event_recorded_by,
        event_created_at,
    ) = row
    latest_event = None
    if event_type:
        latest_event = {
            "event_type": event_type,
            "notes": event_notes or "",
            "recorded_by": event_recorded_by or "",
            "created_at": _iso(event_created_at),
        }
    return {
        "approval_id": approval_id,
        "dispatch_request_id": dispatch_request_id,
        "status": status,
        "mode": mode,
        "specialist_slug": specialist_slug,
        "approval_type": approval_type,
        "notes": notes,
        "approved_by": approved_by,
        "one_shot_scope": _json_value(one_shot_scope_json, {}),
        "next_gate": next_gate,
        "executes_now": bool(executes_now),
        "dispatch_enabled": bool(dispatch_enabled),
        "runs_specialist_llm": bool(runs_specialist_llm),
        "runs_specialist_tools": bool(runs_specialist_tools),
        "writes": bool(writes),
        "applies_runtime_change": bool(applies_runtime_change),
        "dispatches_further": bool(dispatches_further),
        "created_at": _iso(created_at),
        "latest_event": latest_event,
    }


def _approval_id(dispatch_request_id, approval_type):
    digest = hashlib.sha1(
        f"{dispatch_request_id}|{approval_type}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
    ).hexdigest()[:10].upper()
    return f"OSK-DISPATCH-EXEC-APPROVAL-{digest}"


def _event_id(approval_id, event_type):
    digest = hashlib.sha1(
        f"{approval_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
    ).hexdigest()[:10].upper()
    return f"OSK-DISPATCH-EXEC-EVENT-{digest}"


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 20
    return max(1, min(parsed, 100))


def _clean_text(value, max_len):
    return str(value or "").strip()[:max_len]


def _json(value):
    return json.dumps(value if value is not None else {}, default=str)


def _json_value(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _iso(value):
    if not value:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
