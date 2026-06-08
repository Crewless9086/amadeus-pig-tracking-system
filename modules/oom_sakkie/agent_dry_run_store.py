import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.specialists import list_specialist_manifests
from services.database_service import DATABASE_URL_ENV


AGENT_DRY_RUN_EVENT_TYPES = {"approved", "cancelled", "review_note"}
_ALLOWED_DRY_RUN_SLUGS = {"sentinel"}


def record_agent_dry_run_request(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _agent_dry_run_request_params(payload)
    if not params["specialist_slug"]:
        return {"success": False, "status": "specialist_slug_required"}, 400
    if params["specialist_slug"] not in _allowed_specialist_slugs():
        return {
            "success": False,
            "status": "specialist_not_available",
            "allowed_specialists": sorted(_allowed_specialist_slugs()),
        }, 400
    if params["specialist_slug"] not in _ALLOWED_DRY_RUN_SLUGS:
        return {
            "success": False,
            "status": "specialist_dry_run_not_approved_yet",
            "allowed_specialists": sorted(_ALLOWED_DRY_RUN_SLUGS),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id,
                        status,
                        mode,
                        specialist_slug,
                        requested_by,
                        owner_text,
                        purpose,
                        source_trace_id,
                        allowed_tools_json,
                        guardrails_json,
                        next_gate,
                        dry_run_enabled,
                        dispatch_enabled,
                        runs_specialist_llm,
                        runs_specialist_tools,
                        writes,
                        created_at
                    )
                    values (
                        %(dry_run_request_id)s,
                        %(status)s,
                        %(mode)s,
                        %(specialist_slug)s,
                        %(requested_by)s,
                        %(owner_text)s,
                        %(purpose)s,
                        %(source_trace_id)s,
                        %(allowed_tools_json)s::jsonb,
                        %(guardrails_json)s::jsonb,
                        %(next_gate)s,
                        %(dry_run_enabled)s,
                        %(dispatch_enabled)s,
                        %(runs_specialist_llm)s,
                        %(runs_specialist_tools)s,
                        %(writes)s,
                        now()
                    )
                    on conflict (dry_run_request_id) do nothing
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_request_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "read_only_dry_run_request_only",
        "dry_run_request_id": params["dry_run_request_id"],
        "specialist_slug": params["specialist_slug"],
        "dry_run_enabled": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "next_gate": params["next_gate"],
    }, 201


def list_agent_dry_run_requests(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "dry_run_requests": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "dry_run_requests": []}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select dr.dry_run_request_id, dr.status, dr.mode, dr.specialist_slug,
                           dr.requested_by, dr.owner_text, dr.purpose, dr.source_trace_id,
                           dr.allowed_tools_json, dr.guardrails_json, dr.next_gate,
                           dr.dry_run_enabled, dr.dispatch_enabled, dr.runs_specialist_llm,
                           dr.runs_specialist_tools, dr.writes, dr.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_agent_dry_run_requests dr
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_agent_dry_run_events e
                        where e.dry_run_request_id = dr.dry_run_request_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    order by dr.created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_request_read_failed",
            "error_type": exc.__class__.__name__,
            "dry_run_requests": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "read_only_dry_run_request_queue",
        "dry_run_enabled": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "dry_run_requests": [_agent_dry_run_request_row(row) for row in rows],
    }, 200


def get_agent_dry_run_request(dry_run_request_id, database_url=None):
    dry_run_request_id = _clean_text(dry_run_request_id, 100)
    if not dry_run_request_id:
        return {"success": False, "status": "dry_run_request_id_required"}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select dr.dry_run_request_id, dr.status, dr.mode, dr.specialist_slug,
                           dr.requested_by, dr.owner_text, dr.purpose, dr.source_trace_id,
                           dr.allowed_tools_json, dr.guardrails_json, dr.next_gate,
                           dr.dry_run_enabled, dr.dispatch_enabled, dr.runs_specialist_llm,
                           dr.runs_specialist_tools, dr.writes, dr.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_agent_dry_run_requests dr
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_agent_dry_run_events e
                        where e.dry_run_request_id = dr.dry_run_request_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where dr.dry_run_request_id = %(dry_run_request_id)s
                    limit 1
                    """,
                    {"dry_run_request_id": dry_run_request_id},
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_request_read_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    if not row:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_request_not_found",
            "dry_run_request_id": dry_run_request_id,
        }, 404

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "dry_run_request": _agent_dry_run_request_row(row),
    }, 200


def record_agent_dry_run_event(dry_run_request_id, payload, database_url=None):
    dry_run_request_id = _clean_text(dry_run_request_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 40)
    if not dry_run_request_id:
        return {"success": False, "status": "dry_run_request_id_required"}, 400
    if event_type not in AGENT_DRY_RUN_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(AGENT_DRY_RUN_EVENT_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "event_id": _event_id(dry_run_request_id, event_type),
        "dry_run_request_id": dry_run_request_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_events (
                        event_id,
                        dry_run_request_id,
                        event_type,
                        notes,
                        recorded_by,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(dry_run_request_id)s,
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
            "status": "agent_dry_run_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "dry_run_request_id": dry_run_request_id,
        "event_type": event_type,
        "dry_run_enabled": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
    }, 201


def _agent_dry_run_request_params(payload):
    specialist_slug = _clean_text(payload.get("specialist_slug", "sentinel"), 80).lower()
    allowed_tools = payload.get("allowed_tools") or _default_allowed_tools(specialist_slug)
    guardrails = payload.get("guardrails") or [
        "No live specialist dispatch.",
        "No specialist LLM execution.",
        "No specialist tool execution.",
        "No write, post, sale, control, patch, or deploy.",
        "Owner must review the future dry-run output manually.",
    ]
    return {
        "dry_run_request_id": _clean_text(payload.get("dry_run_request_id", ""), 100) or _request_id(specialist_slug),
        "status": "approved_for_read_only_dry_run",
        "mode": "read_only_dry_run_request_only",
        "specialist_slug": specialist_slug,
        "requested_by": _clean_text(payload.get("requested_by", "owner"), 80),
        "owner_text": _clean_text(payload.get("owner_text", ""), 2000),
        "purpose": _clean_text(payload.get("purpose", "First read-only specialist dry-run approval record."), 1200),
        "source_trace_id": _clean_text(payload.get("source_trace_id", ""), 80),
        "allowed_tools_json": _json([str(item)[:100] for item in list(allowed_tools)[:12]]),
        "guardrails_json": _json([str(item)[:240] for item in list(guardrails)[:12]]),
        "next_gate": "manual_review_before_any_specialist_execution",
        "dry_run_enabled": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
    }


def _agent_dry_run_request_row(row):
    (
        dry_run_request_id,
        status,
        mode,
        specialist_slug,
        requested_by,
        owner_text,
        purpose,
        source_trace_id,
        allowed_tools,
        guardrails,
        next_gate,
        dry_run_enabled,
        dispatch_enabled,
        runs_specialist_llm,
        runs_specialist_tools,
        writes,
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
        "dry_run_request_id": dry_run_request_id,
        "status": status,
        "mode": mode,
        "specialist_slug": specialist_slug,
        "requested_by": requested_by,
        "owner_text": owner_text,
        "purpose": purpose,
        "source_trace_id": source_trace_id,
        "allowed_tools": allowed_tools or [],
        "guardrails": guardrails or [],
        "next_gate": next_gate,
        "dry_run_enabled": bool(dry_run_enabled),
        "dispatch_enabled": bool(dispatch_enabled),
        "runs_specialist_llm": bool(runs_specialist_llm),
        "runs_specialist_tools": bool(runs_specialist_tools),
        "writes": bool(writes),
        "created_at": _iso(created_at),
        "latest_event": latest_event,
    }


def _default_allowed_tools(specialist_slug):
    if specialist_slug == "sentinel":
        return ["system_work_status", "farm_operating_brief", "sentinel_dry_run_review"]
    return []


def _allowed_specialist_slugs():
    return {item["slug"] for item in list_specialist_manifests()}


def _request_id(specialist_slug):
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{specialist_slug}:{now}".encode("utf-8")).hexdigest()[:10].upper()
    return f"OSK-AGENT-DRYRUN-{digest}"


def _event_id(dry_run_request_id, event_type):
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{dry_run_request_id}:{event_type}:{now}".encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-AGENT-DRYRUN-EVENT-{digest}"


def _bounded_limit(value):
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError):
        return 20


def _clean_text(value, limit):
    return str(value or "").strip()[:limit]


def _json(value):
    return json.dumps(value, default=str, ensure_ascii=True)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
