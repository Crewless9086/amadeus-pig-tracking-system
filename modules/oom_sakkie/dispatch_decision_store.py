import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.agent_dry_run_store import allowed_agent_dry_run_slugs
from services.database_service import DATABASE_URL_ENV


DISPATCH_DECISION_TYPES = {"approved_for_design_review", "rejected", "deferred", "review_note"}


def record_dispatch_request(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _dispatch_request_params(payload)
    if not params["specialist_slug"]:
        return {"success": False, "status": "specialist_slug_required"}, 400
    if params["specialist_slug"] not in allowed_agent_dry_run_slugs():
        return {
            "success": False,
            "status": "specialist_dispatch_design_not_approved_yet",
            "allowed_specialists": sorted(allowed_agent_dry_run_slugs()),
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
                    insert into public.oom_sakkie_dispatch_requests (
                        dispatch_request_id,
                        status,
                        mode,
                        specialist_slug,
                        requested_by,
                        owner_text,
                        purpose,
                        source_trace_id,
                        proposed_scope_json,
                        guardrails_json,
                        next_gate,
                        dispatch_enabled,
                        runs_specialist_llm,
                        runs_specialist_tools,
                        writes,
                        applies_runtime_change,
                        created_at
                    )
                    values (
                        %(dispatch_request_id)s,
                        %(status)s,
                        %(mode)s,
                        %(specialist_slug)s,
                        %(requested_by)s,
                        %(owner_text)s,
                        %(purpose)s,
                        %(source_trace_id)s,
                        %(proposed_scope_json)s::jsonb,
                        %(guardrails_json)s::jsonb,
                        %(next_gate)s,
                        %(dispatch_enabled)s,
                        %(runs_specialist_llm)s,
                        %(runs_specialist_tools)s,
                        %(writes)s,
                        %(applies_runtime_change)s,
                        now()
                    )
                    on conflict (dispatch_request_id) do nothing
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_request_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dispatch_decision_request_only",
        "dispatch_request_id": params["dispatch_request_id"],
        "specialist_slug": params["specialist_slug"],
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "next_gate": params["next_gate"],
    }, 201


def list_dispatch_requests(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "dispatch_requests": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "dispatch_requests": []}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select dr.dispatch_request_id, dr.status, dr.mode, dr.specialist_slug,
                           dr.requested_by, dr.owner_text, dr.purpose, dr.source_trace_id,
                           dr.proposed_scope_json, dr.guardrails_json, dr.next_gate,
                           dr.dispatch_enabled, dr.runs_specialist_llm, dr.runs_specialist_tools,
                           dr.writes, dr.applies_runtime_change, dr.created_at,
                           dd.decision_type, dd.notes, dd.recorded_by, dd.created_at
                    from public.oom_sakkie_dispatch_requests dr
                    left join lateral (
                        select decision_type, notes, recorded_by, created_at
                        from public.oom_sakkie_dispatch_decisions d
                        where d.dispatch_request_id = dr.dispatch_request_id
                        order by created_at desc
                        limit 1
                    ) dd on true
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
            "status": "dispatch_request_read_failed",
            "error_type": exc.__class__.__name__,
            "dispatch_requests": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dispatch_decision_request_queue",
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatch_requests": [_dispatch_request_row(row) for row in rows],
    }, 200


def get_dispatch_request(dispatch_request_id, database_url=None):
    dispatch_request_id = _clean_text(dispatch_request_id, 100)
    if not dispatch_request_id:
        return {"success": False, "status": "dispatch_request_id_required"}, 400

    result, status_code = list_dispatch_requests(limit=100, database_url=database_url)
    if status_code != 200:
        return result, status_code
    for item in result.get("dispatch_requests", []):
        if item.get("dispatch_request_id") == dispatch_request_id:
            return {"success": True, "configured": True, "status": "ok", "dispatch_request": item}, 200
    return {
        "success": False,
        "configured": True,
        "status": "dispatch_request_not_found",
        "dispatch_request_id": dispatch_request_id,
    }, 404


def record_dispatch_decision(dispatch_request_id, payload, database_url=None):
    dispatch_request_id = _clean_text(dispatch_request_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    decision_type = _clean_text(payload.get("decision_type", ""), 60)
    if not dispatch_request_id:
        return {"success": False, "status": "dispatch_request_id_required"}, 400
    if decision_type not in DISPATCH_DECISION_TYPES:
        return {
            "success": False,
            "status": "invalid_decision_type",
            "allowed_decision_types": sorted(DISPATCH_DECISION_TYPES),
        }, 400

    request_result, request_status = get_dispatch_request(dispatch_request_id, database_url=database_url)
    if request_status != 200:
        return request_result, request_status

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "decision_id": _decision_id(dispatch_request_id, decision_type),
        "dispatch_request_id": dispatch_request_id,
        "decision_type": decision_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_decisions (
                        decision_id,
                        dispatch_request_id,
                        decision_type,
                        notes,
                        recorded_by,
                        dispatch_enabled,
                        runs_specialist_llm,
                        runs_specialist_tools,
                        writes,
                        applies_runtime_change,
                        created_at
                    )
                    values (
                        %(decision_id)s,
                        %(dispatch_request_id)s,
                        %(decision_type)s,
                        %(notes)s,
                        %(recorded_by)s,
                        %(dispatch_enabled)s,
                        %(runs_specialist_llm)s,
                        %(runs_specialist_tools)s,
                        %(writes)s,
                        %(applies_runtime_change)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "dispatch_decision_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "decision_id": params["decision_id"],
        "dispatch_request_id": dispatch_request_id,
        "decision_type": decision_type,
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
    }, 201


def _dispatch_request_params(payload):
    specialist_slug = _clean_text(payload.get("specialist_slug", "sentinel"), 80).lower()
    guardrails = payload.get("guardrails") or [
        "No live specialist dispatch.",
        "No specialist LLM execution.",
        "No specialist tool execution.",
        "No farm-data writes.",
        "Owner and Claude must review before any runtime flag can change.",
    ]
    scope = payload.get("proposed_scope") if isinstance(payload.get("proposed_scope"), dict) else {}
    return {
        "dispatch_request_id": _clean_text(payload.get("dispatch_request_id", ""), 100) or _request_id(specialist_slug),
        "status": "requested_for_dispatch_design_review",
        "mode": "dispatch_decision_request_only",
        "specialist_slug": specialist_slug,
        "requested_by": _clean_text(payload.get("requested_by", "owner"), 80),
        "owner_text": _clean_text(payload.get("owner_text", ""), 2000),
        "purpose": _clean_text(payload.get("purpose", "Request to design-review a future live specialist dispatch boundary."), 1200),
        "source_trace_id": _clean_text(payload.get("source_trace_id", ""), 80),
        "proposed_scope_json": _json(scope),
        "guardrails_json": _json([str(item)[:240] for item in list(guardrails)[:12]]),
        "next_gate": "owner_and_claude_review_before_any_dispatch_runtime_code",
        "dispatch_enabled": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
    }


def _dispatch_request_row(row):
    (
        dispatch_request_id,
        status,
        mode,
        specialist_slug,
        requested_by,
        owner_text,
        purpose,
        source_trace_id,
        proposed_scope_json,
        guardrails_json,
        next_gate,
        dispatch_enabled,
        runs_specialist_llm,
        runs_specialist_tools,
        writes,
        applies_runtime_change,
        created_at,
        decision_type,
        decision_notes,
        decision_recorded_by,
        decision_created_at,
    ) = row
    return {
        "dispatch_request_id": dispatch_request_id,
        "status": status,
        "mode": mode,
        "specialist_slug": specialist_slug,
        "requested_by": requested_by,
        "owner_text": owner_text,
        "purpose": purpose,
        "source_trace_id": source_trace_id,
        "proposed_scope": _json_value(proposed_scope_json, {}),
        "guardrails": _json_value(guardrails_json, []),
        "next_gate": next_gate,
        "dispatch_enabled": bool(dispatch_enabled),
        "runs_specialist_llm": bool(runs_specialist_llm),
        "runs_specialist_tools": bool(runs_specialist_tools),
        "writes": bool(writes),
        "applies_runtime_change": bool(applies_runtime_change),
        "created_at": _iso(created_at),
        "latest_decision": {
            "decision_type": decision_type,
            "notes": decision_notes,
            "recorded_by": decision_recorded_by,
            "created_at": _iso(decision_created_at),
        } if decision_type else None,
    }


def _request_id(specialist_slug):
    digest = hashlib.sha1(f"{specialist_slug}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()[:10].upper()
    return f"OSK-DISPATCH-REQ-{digest}"


def _decision_id(dispatch_request_id, decision_type):
    digest = hashlib.sha1(f"{dispatch_request_id}|{decision_type}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()[:10].upper()
    return f"OSK-DISPATCH-DECISION-{digest}"


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
