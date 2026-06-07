import hashlib
import json
import os
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


PATCH_PROPOSAL_EVENT_TYPES = {"approved_for_patch", "rejected", "review_note"}


def record_patch_proposal(build_request_id, payload, database_url=None):
    build_request_id = _clean_text(build_request_id, 80)
    payload = payload if isinstance(payload, dict) else {}
    if not build_request_id:
        return {"success": False, "status": "build_request_id_required"}, 400

    params = _patch_proposal_params(build_request_id, payload)
    if not params["proposal_text"]:
        return {"success": False, "status": "proposal_text_required"}, 400

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
                    insert into public.oom_sakkie_patch_proposals (
                        patch_proposal_id,
                        build_request_id,
                        proposal_text,
                        proposed_by,
                        risk_notes,
                        files_touched_json,
                        verification_json,
                        applies_patch,
                        deploys,
                        created_at
                    )
                    values (
                        %(patch_proposal_id)s,
                        %(build_request_id)s,
                        %(proposal_text)s,
                        %(proposed_by)s,
                        %(risk_notes)s,
                        %(files_touched_json)s::jsonb,
                        %(verification_json)s::jsonb,
                        %(applies_patch)s,
                        %(deploys)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "patch_proposal_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "patch_proposal_review_only",
        "patch_proposal_id": params["patch_proposal_id"],
        "build_request_id": build_request_id,
        "applies_patch": False,
        "deploys": False,
        "requires_manual_patch_application": True,
    }, 201


def list_patch_proposals(build_request_id="", limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    build_request_id = _clean_text(build_request_id, 80)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "patch_proposals": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "patch_proposals": []}, 500

    params = {"build_request_id": build_request_id, "limit": parsed_limit}
    where_clause = "where pp.build_request_id = %(build_request_id)s" if build_request_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select pp.patch_proposal_id, pp.build_request_id, pp.proposal_text, pp.proposed_by,
                           pp.risk_notes, pp.files_touched_json, pp.verification_json,
                           pp.applies_patch, pp.deploys, pp.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_patch_proposals pp
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_patch_proposal_events e
                        where e.patch_proposal_id = pp.patch_proposal_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    {where_clause}
                    order by pp.created_at desc
                    limit %(limit)s
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "patch_proposal_read_failed",
            "error_type": exc.__class__.__name__,
            "patch_proposals": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "patch_proposal_review_only",
        "applies_patches": False,
        "deploys": False,
        "patch_proposals": [_patch_proposal_row(row) for row in rows],
    }, 200


def record_patch_proposal_event(patch_proposal_id, payload, database_url=None):
    patch_proposal_id = _clean_text(patch_proposal_id, 90)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 40)
    if not patch_proposal_id:
        return {"success": False, "status": "patch_proposal_id_required"}, 400
    if event_type not in PATCH_PROPOSAL_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(PATCH_PROPOSAL_EVENT_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "event_id": _patch_event_id(patch_proposal_id, event_type),
        "patch_proposal_id": patch_proposal_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_patch_proposal_events (
                        event_id,
                        patch_proposal_id,
                        event_type,
                        notes,
                        recorded_by,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(patch_proposal_id)s,
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
            "status": "patch_proposal_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "patch_proposal_id": patch_proposal_id,
        "event_type": event_type,
        "applies_patch": False,
        "deploys": False,
    }, 201


def _patch_proposal_params(build_request_id, payload):
    return {
        "patch_proposal_id": _patch_proposal_id(build_request_id, payload.get("proposal_text", "")),
        "build_request_id": build_request_id,
        "proposal_text": _clean_text(payload.get("proposal_text", ""), 12000),
        "proposed_by": _clean_text(payload.get("proposed_by", "builder"), 80),
        "risk_notes": _clean_text(payload.get("risk_notes", ""), 2000),
        "files_touched_json": _json(_clean_list(payload.get("files_touched"), 40, 240)),
        "verification_json": _json(_clean_list(payload.get("verification"), 20, 300)),
        "applies_patch": False,
        "deploys": False,
    }


def _patch_proposal_row(row):
    (
        patch_proposal_id,
        build_request_id,
        proposal_text,
        proposed_by,
        risk_notes,
        files_touched,
        verification,
        applies_patch,
        deploys,
        created_at,
        event_type,
        event_notes,
        event_recorded_by,
        event_created_at,
    ) = row
    return {
        "patch_proposal_id": patch_proposal_id,
        "build_request_id": build_request_id,
        "mode": "patch_proposal_review_only",
        "proposal_text": proposal_text or "",
        "proposed_by": proposed_by or "",
        "risk_notes": risk_notes or "",
        "files_touched": files_touched or [],
        "verification": verification or [],
        "applies_patch": bool(applies_patch),
        "deploys": bool(deploys),
        "created_at": _iso(created_at),
        "latest_event": {
            "event_type": event_type,
            "notes": event_notes or "",
            "recorded_by": event_recorded_by or "",
            "created_at": _iso(event_created_at),
        } if event_type else None,
    }


def _patch_proposal_id(build_request_id, proposal_text):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{build_request_id}:{proposal_text}:{stamp}".encode("utf-8")).hexdigest()[:8].upper()
    return f"OSK-PATCH-{stamp}-{digest}"


def _patch_event_id(patch_proposal_id, event_type):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{patch_proposal_id}:{event_type}:{stamp}".encode("utf-8")).hexdigest()[:8].upper()
    return f"OSKPE-{stamp}-{digest}"


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 20
    return max(1, min(parsed, 50))


def _clean_list(value, max_items, max_length):
    if not isinstance(value, list):
        return []
    return [_clean_text(item, max_length) for item in value[:max_items] if _clean_text(item, max_length)]


def _clean_text(value, max_length):
    return str(value or "").strip()[:max_length]


def _json(value):
    return json.dumps(value or [], sort_keys=True, default=str)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
