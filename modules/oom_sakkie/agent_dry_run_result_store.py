import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.agent_dry_run_store import allowed_agent_dry_run_slugs, get_agent_dry_run_request
from services.database_service import DATABASE_URL_ENV


AGENT_DRY_RUN_RESULT_EVENT_TYPES = {"accepted_for_learning", "rejected", "review_note"}


def record_agent_dry_run_result(dry_run_request_id, payload, database_url=None):
    dry_run_request_id = _clean_text(dry_run_request_id, 100)
    if not dry_run_request_id:
        return {"success": False, "status": "dry_run_request_id_required"}, 400

    request, request_status = get_agent_dry_run_request(dry_run_request_id, database_url=database_url)
    if request_status != 200:
        return request, request_status
    dry_run_request = request.get("dry_run_request", {})
    specialist_slug = str(dry_run_request.get("specialist_slug") or "").strip().lower()
    if specialist_slug not in allowed_agent_dry_run_slugs():
        return {
            "success": False,
            "status": "dry_run_result_not_approved_for_specialist",
            "allowed_specialists": sorted(allowed_agent_dry_run_slugs()),
        }, 400

    payload = payload if isinstance(payload, dict) else {}
    params = _agent_dry_run_result_params(dry_run_request, payload)
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
                    insert into public.oom_sakkie_agent_dry_run_results (
                        dry_run_result_id,
                        dry_run_request_id,
                        status,
                        mode,
                        specialist_slug,
                        result_text,
                        findings_json,
                        recommended_next_gate,
                        recorded_by,
                        runs_specialist,
                        dispatch_enabled,
                        runs_specialist_llm,
                        runs_specialist_tools,
                        writes,
                        applies_runtime_change,
                        created_at
                    )
                    values (
                        %(dry_run_result_id)s,
                        %(dry_run_request_id)s,
                        %(status)s,
                        %(mode)s,
                        %(specialist_slug)s,
                        %(result_text)s,
                        %(findings_json)s::jsonb,
                        %(recommended_next_gate)s,
                        %(recorded_by)s,
                        %(runs_specialist)s,
                        %(dispatch_enabled)s,
                        %(runs_specialist_llm)s,
                        %(runs_specialist_tools)s,
                        %(writes)s,
                        %(applies_runtime_change)s,
                        now()
                    )
                    on conflict (dry_run_result_id) do nothing
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_result_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dry_run_result_review_only",
        "dry_run_result_id": params["dry_run_result_id"],
        "dry_run_request_id": params["dry_run_request_id"],
        "specialist_slug": params["specialist_slug"],
        "runs_specialist": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "next_gate": params["recommended_next_gate"],
    }, 201


def list_agent_dry_run_results(limit=20, dry_run_request_id="", database_url=None):
    parsed_limit = _bounded_limit(limit)
    dry_run_request_id = _clean_text(dry_run_request_id, 100)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "dry_run_results": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "dry_run_results": []}, 500

    where = "where r.dry_run_request_id = %(dry_run_request_id)s" if dry_run_request_id else ""
    params = {"limit": parsed_limit, "dry_run_request_id": dry_run_request_id}
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select r.dry_run_result_id, r.dry_run_request_id, r.status, r.mode,
                           r.specialist_slug, r.result_text, r.findings_json,
                           r.recommended_next_gate, r.recorded_by,
                           r.runs_specialist, r.dispatch_enabled, r.runs_specialist_llm,
                           r.runs_specialist_tools, r.writes, r.applies_runtime_change,
                           r.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_agent_dry_run_results r
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_agent_dry_run_result_events e
                        where e.dry_run_result_id = r.dry_run_result_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    {where}
                    order by r.created_at desc
                    limit %(limit)s
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_result_read_failed",
            "error_type": exc.__class__.__name__,
            "dry_run_results": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dry_run_result_review_queue",
        "runs_specialist": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dry_run_results": [_agent_dry_run_result_row(row) for row in rows],
    }, 200


def get_agent_dry_run_result(dry_run_result_id, database_url=None):
    dry_run_result_id = _clean_text(dry_run_result_id, 100)
    if not dry_run_result_id:
        return {"success": False, "status": "dry_run_result_id_required"}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "dry_run_result": {}}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "dry_run_result": {}}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select r.dry_run_result_id, r.dry_run_request_id, r.status, r.mode,
                           r.specialist_slug, r.result_text, r.findings_json,
                           r.recommended_next_gate, r.recorded_by,
                           r.runs_specialist, r.dispatch_enabled, r.runs_specialist_llm,
                           r.runs_specialist_tools, r.writes, r.applies_runtime_change,
                           r.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_agent_dry_run_results r
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_agent_dry_run_result_events e
                        where e.dry_run_result_id = r.dry_run_result_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where r.dry_run_result_id = %(dry_run_result_id)s
                    limit 1
                    """,
                    {"dry_run_result_id": dry_run_result_id},
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "agent_dry_run_result_read_failed",
            "error_type": exc.__class__.__name__,
            "dry_run_result": {},
        }, 503

    if not row:
        return {
            "success": False,
            "configured": True,
            "status": "dry_run_result_not_found",
            "dry_run_result_id": dry_run_result_id,
            "dry_run_result": {},
        }, 404

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dry_run_result_detail",
        "runs_specialist": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dry_run_result": _agent_dry_run_result_row(row),
    }, 200


def record_agent_dry_run_result_event(dry_run_result_id, payload, database_url=None):
    dry_run_result_id = _clean_text(dry_run_result_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 40)
    if not dry_run_result_id:
        return {"success": False, "status": "dry_run_result_id_required"}, 400
    if event_type not in AGENT_DRY_RUN_RESULT_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(AGENT_DRY_RUN_RESULT_EVENT_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "event_id": _event_id(dry_run_result_id, event_type),
        "dry_run_result_id": dry_run_result_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_result_events (
                        event_id,
                        dry_run_result_id,
                        event_type,
                        notes,
                        recorded_by,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(dry_run_result_id)s,
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
            "status": "agent_dry_run_result_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "dry_run_result_id": dry_run_result_id,
        "event_type": event_type,
        "runs_specialist": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
    }, 201


def _agent_dry_run_result_params(dry_run_request, payload):
    findings = payload.get("findings") or []
    return {
        "dry_run_result_id": _clean_text(payload.get("dry_run_result_id", ""), 100)
        or _result_id(dry_run_request.get("dry_run_request_id", "")),
        "dry_run_request_id": _clean_text(dry_run_request.get("dry_run_request_id", ""), 100),
        "status": "recorded_for_owner_review",
        "mode": "dry_run_result_review_only",
        "specialist_slug": _clean_text(dry_run_request.get("specialist_slug", ""), 80).lower(),
        "result_text": _clean_text(payload.get("result_text", ""), 6000),
        "findings_json": _json([str(item)[:500] for item in list(findings)[:20]]),
        "recommended_next_gate": _clean_text(
            payload.get("recommended_next_gate", "owner_review_before_learning_or_runtime_change"),
            160,
        ),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
        "runs_specialist": False,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
    }


def _agent_dry_run_result_row(row):
    (
        dry_run_result_id,
        dry_run_request_id,
        status,
        mode,
        specialist_slug,
        result_text,
        findings,
        recommended_next_gate,
        recorded_by,
        runs_specialist,
        dispatch_enabled,
        runs_specialist_llm,
        runs_specialist_tools,
        writes,
        applies_runtime_change,
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
        "dry_run_result_id": dry_run_result_id,
        "dry_run_request_id": dry_run_request_id,
        "status": status,
        "mode": mode,
        "specialist_slug": specialist_slug,
        "result_text": result_text,
        "findings": findings or [],
        "recommended_next_gate": recommended_next_gate,
        "recorded_by": recorded_by,
        "runs_specialist": bool(runs_specialist),
        "dispatch_enabled": bool(dispatch_enabled),
        "runs_specialist_llm": bool(runs_specialist_llm),
        "runs_specialist_tools": bool(runs_specialist_tools),
        "writes": bool(writes),
        "applies_runtime_change": bool(applies_runtime_change),
        "created_at": _iso(created_at),
        "latest_event": latest_event,
    }


def _result_id(dry_run_request_id):
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{dry_run_request_id}:{now}".encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-AGENT-DRYRUN-RESULT-{digest}"


def _event_id(dry_run_result_id, event_type):
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{dry_run_result_id}:{event_type}:{now}".encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-AGENT-DRYRUN-RESULT-EVENT-{digest}"


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
