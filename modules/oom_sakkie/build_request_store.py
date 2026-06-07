import json
import os
from datetime import datetime, timezone
import hashlib

from services.database_service import DATABASE_URL_ENV


BUILD_REQUEST_EVENT_TYPES = {"approved", "ignored", "review_note"}


def record_build_request(build_request, database_url=None):
    build_request = build_request if isinstance(build_request, dict) else {}
    request_id = _clean_text(build_request.get("build_request_id", ""), 80)
    if not request_id:
        return {"stored": False, "status": "build_request_id_required"}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"stored": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"stored": False, "configured": True, "status": "dependency_missing"}, 500

    params = _build_request_params(build_request)
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_build_requests (
                        build_request_id,
                        status,
                        mode,
                        approved_by,
                        proposal_json,
                        brief,
                        recommended_files_json,
                        verification_json,
                        next_gate,
                        builder_enabled,
                        writes_code_now,
                        applies_changes_now,
                        created_at
                    )
                    values (
                        %(build_request_id)s,
                        %(status)s,
                        %(mode)s,
                        %(approved_by)s,
                        %(proposal_json)s::jsonb,
                        %(brief)s,
                        %(recommended_files_json)s::jsonb,
                        %(verification_json)s::jsonb,
                        %(next_gate)s,
                        %(builder_enabled)s,
                        %(writes_code_now)s,
                        %(applies_changes_now)s,
                        now()
                    )
                    on conflict (build_request_id) do nothing
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "stored": False,
            "configured": True,
            "status": "build_request_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "stored": True,
        "configured": True,
        "status": "ok",
        "build_request_id": request_id,
    }, 201


def list_build_requests(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "build_requests": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "build_requests": []}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select br.build_request_id, br.status, br.mode, br.approved_by, br.proposal_json,
                           br.brief, br.recommended_files_json, br.verification_json, br.next_gate,
                           br.builder_enabled, br.writes_code_now, br.applies_changes_now, br.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_build_requests
                    br
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_build_request_events e
                        where e.build_request_id = br.build_request_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    order by br.created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "build_request_read_failed",
            "error_type": exc.__class__.__name__,
            "build_requests": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "build_requests": [_build_request_row(row) for row in rows],
    }, 200


def get_build_request(build_request_id, database_url=None):
    build_request_id = _clean_text(build_request_id, 80)
    if not build_request_id:
        return {"success": False, "status": "build_request_id_required"}, 400

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
                    select br.build_request_id, br.status, br.mode, br.approved_by, br.proposal_json,
                           br.brief, br.recommended_files_json, br.verification_json, br.next_gate,
                           br.builder_enabled, br.writes_code_now, br.applies_changes_now, br.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_build_requests br
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_build_request_events e
                        where e.build_request_id = br.build_request_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where br.build_request_id = %(build_request_id)s
                    limit 1
                    """,
                    {"build_request_id": build_request_id},
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "build_request_read_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    if not row:
        return {
            "success": False,
            "configured": True,
            "status": "build_request_not_found",
            "build_request_id": build_request_id,
        }, 404
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "build_request": _build_request_row(row),
    }, 200


def record_build_request_event(build_request_id, payload, database_url=None):
    build_request_id = _clean_text(build_request_id, 80)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 40)
    if not build_request_id:
        return {"success": False, "status": "build_request_id_required"}, 400
    if event_type not in BUILD_REQUEST_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(BUILD_REQUEST_EVENT_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "event_id": _build_event_id(build_request_id, event_type),
        "build_request_id": build_request_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1000),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_build_request_events (
                        event_id,
                        build_request_id,
                        event_type,
                        notes,
                        recorded_by,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(build_request_id)s,
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
            "status": "build_request_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "build_request_id": build_request_id,
        "event_type": event_type,
    }, 201


def _build_request_params(build_request):
    return {
        "build_request_id": _clean_text(build_request.get("build_request_id", ""), 80),
        "status": _clean_text(build_request.get("status", "approved_for_build"), 80),
        "mode": _clean_text(build_request.get("mode", "build_request_only"), 80),
        "approved_by": _clean_text(build_request.get("approved_by", "owner"), 80),
        "proposal_json": _json(build_request.get("proposal") or {}),
        "brief": _clean_text(build_request.get("brief", ""), 8000),
        "recommended_files_json": _json(build_request.get("recommended_files") or []),
        "verification_json": _json(build_request.get("verification") or []),
        "next_gate": _clean_text(build_request.get("requires_next_gate", ""), 120),
        "builder_enabled": bool(build_request.get("builder_enabled")),
        "writes_code_now": bool(build_request.get("writes_code_now")),
        "applies_changes_now": bool(build_request.get("applies_changes_now")),
    }


def _build_request_row(row):
    (
        build_request_id,
        status,
        mode,
        approved_by,
        proposal,
        brief,
        recommended_files,
        verification,
        next_gate,
        builder_enabled,
        writes_code_now,
        applies_changes_now,
        created_at,
        event_type,
        event_notes,
        event_recorded_by,
        event_created_at,
    ) = row
    return {
        "build_request_id": build_request_id,
        "status": status,
        "mode": mode,
        "approved_by": approved_by,
        "proposal": proposal or {},
        "brief": brief or "",
        "recommended_files": recommended_files or [],
        "verification": verification or [],
        "requires_next_gate": next_gate,
        "builder_enabled": bool(builder_enabled),
        "writes_code_now": bool(writes_code_now),
        "applies_changes_now": bool(applies_changes_now),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
        "latest_event": {
            "event_type": event_type,
            "notes": event_notes or "",
            "recorded_by": event_recorded_by or "",
            "created_at": event_created_at.isoformat() if hasattr(event_created_at, "isoformat") else str(event_created_at or ""),
        } if event_type else None,
    }


def _json(value):
    return json.dumps(value or {}, sort_keys=True, default=str)


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 20
    return max(1, min(parsed, 50))


def _clean_text(value, max_length):
    return str(value or "").strip()[:max_length]


def _build_event_id(build_request_id, event_type):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{build_request_id}:{event_type}:{stamp}".encode("utf-8")).hexdigest()[:8].upper()
    return f"OSKBRE-{stamp}-{digest}"
