import hashlib
import json
import os
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


LEARNING_INFLUENCE_CONSUMPTION_TARGET_KINDS = {
    "planning_context_note",
    "routing_hint_review_note",
    "answer_style_review_note",
}
LEARNING_INFLUENCE_CONSUMPTION_EVENT_TYPES = {
    "review_note",
    "approved_for_design_review",
    "rejected",
    "consumed_for_patch_proposal",
}


def list_learning_influence_consumption_requests(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select r.consumption_request_id, r.proposal_id, r.source_result_id,
                           r.status, r.mode, r.requested_target_kind,
                           r.requested_target_field, r.request_note,
                           r.review_note_artifact_json, r.requested_by,
                           r.applies_learning_now, r.changes_prompt_now,
                           r.changes_runtime_now, r.dispatch_enabled, r.writes,
                           r.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_learning_influence_consumption_requests r
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_learning_influence_consumption_events e
                        where e.consumption_request_id = r.consumption_request_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    order by r.created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_consumption_request_read_failed",
            "error_type": exc.__class__.__name__,
            "learning_influence_consumption_requests": [],
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "learning_influence_consumption_request_queue",
        "learning_influence_consumption_requests": [_consumption_request_row(row) for row in rows],
        **_false_flags(),
    }, 200


def record_learning_influence_consumption_request(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    proposal_id = _clean_text(payload.get("proposal_id", ""), 100)
    target_kind = _clean_text(payload.get("requested_target_kind", ""), 80)
    target_field = _clean_text(payload.get("requested_target_field", ""), 120)
    if not proposal_id:
        return {"success": False, "status": "proposal_id_required", **_false_flags()}, 400
    if target_kind not in LEARNING_INFLUENCE_CONSUMPTION_TARGET_KINDS:
        return {
            "success": False,
            "status": "invalid_requested_target_kind",
            "allowed_target_kinds": sorted(LEARNING_INFLUENCE_CONSUMPTION_TARGET_KINDS),
            **_false_flags(),
        }, 400
    if not target_field:
        return {"success": False, "status": "requested_target_field_required", **_false_flags()}, 400

    proposal, proposal_status = _get_learning_influence_proposal(proposal_id, database_url=database_url)
    if proposal_status != 200:
        return proposal, proposal_status
    latest_event = proposal.get("learning_influence_proposal", {}).get("latest_event") or {}
    if latest_event.get("event_type") != "approved_for_future_planning":
        return {
            "success": False,
            "configured": True,
            "status": "proposal_not_approved_for_future_planning",
            "proposal_id": proposal_id,
            "latest_event": latest_event,
            **_false_flags(),
        }, 409

    params = _consumption_request_params(proposal["learning_influence_proposal"], payload)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    created_count = 0
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_consumption_requests (
                        consumption_request_id,
                        proposal_id,
                        source_result_id,
                        status,
                        mode,
                        requested_target_kind,
                        requested_target_field,
                        request_note,
                        review_note_artifact_json,
                        requested_by,
                        applies_learning_now,
                        changes_prompt_now,
                        changes_runtime_now,
                        dispatch_enabled,
                        writes,
                        created_at
                    )
                    values (
                        %(consumption_request_id)s,
                        %(proposal_id)s,
                        %(source_result_id)s,
                        %(status)s,
                        %(mode)s,
                        %(requested_target_kind)s,
                        %(requested_target_field)s,
                        %(request_note)s,
                        %(review_note_artifact_json)s::jsonb,
                        %(requested_by)s,
                        %(applies_learning_now)s,
                        %(changes_prompt_now)s,
                        %(changes_runtime_now)s,
                        %(dispatch_enabled)s,
                        %(writes)s,
                        now()
                    )
                    on conflict (proposal_id, requested_target_kind, requested_target_field) do nothing
                    returning consumption_request_id
                    """,
                    params,
                )
                created_count = 1 if cursor.fetchone() else 0
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_consumption_request_write_failed",
            "error_type": exc.__class__.__name__,
            "created_count": 0,
            "learning_influence_consumption_requests": [],
            **_false_flags(),
        }, 503

    listed, list_status = list_learning_influence_consumption_requests(limit=50, database_url=database_url)
    if list_status != 200:
        return listed, list_status
    requests = [
        item for item in listed.get("learning_influence_consumption_requests", [])
        if item.get("proposal_id") == params["proposal_id"]
        and item.get("requested_target_kind") == params["requested_target_kind"]
        and item.get("requested_target_field") == params["requested_target_field"]
    ]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "learning_influence_consumption_request_queue",
        "created_count": created_count,
        "learning_influence_consumption_requests": requests,
        "review_note_artifact_only": True,
        "next_gate": "owner_and_claude_review_before_any_learning_consumer_or_patch_diff",
        **_false_flags(),
    }, 201


def record_learning_influence_consumption_event(consumption_request_id, payload, database_url=None, allow_consumed=False):
    consumption_request_id = _clean_text(consumption_request_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 80)
    if not consumption_request_id:
        return {"success": False, "status": "consumption_request_id_required", **_false_flags()}, 400
    if event_type not in LEARNING_INFLUENCE_CONSUMPTION_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(LEARNING_INFLUENCE_CONSUMPTION_EVENT_TYPES),
            **_false_flags(),
        }, 400
    if event_type == "consumed_for_patch_proposal" and not allow_consumed:
        return {
            "success": False,
            "status": "consumed_event_is_future_consumer_only",
            **_false_flags(),
        }, 403

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", **_false_flags()}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", **_false_flags()}, 500

    params = {
        "event_id": _event_id(consumption_request_id, event_type),
        "consumption_request_id": consumption_request_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
        **_false_flags(),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_consumption_events (
                        event_id,
                        consumption_request_id,
                        event_type,
                        notes,
                        recorded_by,
                        applies_learning_now,
                        changes_prompt_now,
                        changes_runtime_now,
                        dispatch_enabled,
                        writes,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(consumption_request_id)s,
                        %(event_type)s,
                        %(notes)s,
                        %(recorded_by)s,
                        %(applies_learning_now)s,
                        %(changes_prompt_now)s,
                        %(changes_runtime_now)s,
                        %(dispatch_enabled)s,
                        %(writes)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_consumption_event_write_failed",
            "error_type": exc.__class__.__name__,
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "consumption_request_id": consumption_request_id,
        "event_type": event_type,
        **_false_flags(),
    }, 201


def _get_learning_influence_proposal(proposal_id, database_url=None):
    proposal_id = _clean_text(proposal_id, 100)
    if not proposal_id:
        return {"success": False, "status": "proposal_id_required", "learning_influence_proposal": {}, **_false_flags()}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "learning_influence_proposal": {}, **_false_flags()}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "learning_influence_proposal": {}, **_false_flags()}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select p.proposal_id, p.source_result_id, p.specialist_slug,
                           p.proposal_title, p.proposal_text, p.evidence_json,
                           p.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_learning_influence_proposals p
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_learning_influence_proposal_events e
                        where e.proposal_id = p.proposal_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where p.proposal_id = %(proposal_id)s
                    limit 1
                    """,
                    {"proposal_id": proposal_id},
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_proposal_read_failed",
            "error_type": exc.__class__.__name__,
            "learning_influence_proposal": {},
            **_false_flags(),
        }, 503

    if not row:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_proposal_not_found",
            "proposal_id": proposal_id,
            "learning_influence_proposal": {},
            **_false_flags(),
        }, 404
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "learning_influence_proposal": _proposal_row(row),
        **_false_flags(),
    }, 200


def _consumption_request_params(proposal, payload):
    target_kind = _clean_text(payload.get("requested_target_kind", ""), 80)
    target_field = _clean_text(payload.get("requested_target_field", ""), 120)
    request_note = _clean_text(payload.get("request_note", ""), 1200)
    proposal_text = _clean_text(proposal.get("proposal_text", ""), 500)
    artifact = {
        "kind": "review_note_only",
        "proposal_text_is_untrusted": True,
        "must_include_source_provenance": True,
        "single_target_field": True,
        "max_diff_chars": 1200,
        "max_source_excerpt_chars": 500,
        "source": {
            "proposal_id": proposal.get("proposal_id", ""),
            "source_result_id": proposal.get("source_result_id", ""),
            "specialist_slug": proposal.get("specialist_slug", ""),
            "approved_event": proposal.get("latest_event") or {},
        },
        "target": {
            "requested_target_kind": target_kind,
            "requested_target_field": target_field,
        },
        "source_excerpt": proposal_text,
        "request_note": request_note,
        "non_goal": "No prompt, route, runtime, tool, farm-data, public-output, deploy, Telegram, physical-control, or financial change is applied.",
    }
    return {
        "consumption_request_id": _consumption_request_id(proposal.get("proposal_id", ""), target_kind, target_field),
        "proposal_id": proposal.get("proposal_id", ""),
        "source_result_id": proposal.get("source_result_id", ""),
        "status": "requested_for_consumption_design_review",
        "mode": "learning_influence_consumption_request_only",
        "requested_target_kind": target_kind,
        "requested_target_field": target_field,
        "request_note": request_note,
        "review_note_artifact_json": _json(artifact),
        "requested_by": _clean_text(payload.get("requested_by", "owner"), 80),
        **_false_flags(),
    }


def _proposal_row(row):
    (
        proposal_id,
        source_result_id,
        specialist_slug,
        proposal_title,
        proposal_text,
        evidence,
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
        "proposal_id": proposal_id,
        "source_result_id": source_result_id,
        "specialist_slug": specialist_slug,
        "proposal_title": proposal_title,
        "proposal_text": proposal_text,
        "evidence": evidence or {},
        "created_at": _iso(created_at),
        "latest_event": latest_event,
    }


def _consumption_request_row(row):
    (
        consumption_request_id,
        proposal_id,
        source_result_id,
        status,
        mode,
        requested_target_kind,
        requested_target_field,
        request_note,
        review_note_artifact,
        requested_by,
        applies_learning_now,
        changes_prompt_now,
        changes_runtime_now,
        dispatch_enabled,
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
        "consumption_request_id": consumption_request_id,
        "proposal_id": proposal_id,
        "source_result_id": source_result_id,
        "status": status,
        "mode": mode,
        "requested_target_kind": requested_target_kind,
        "requested_target_field": requested_target_field,
        "request_note": request_note,
        "review_note_artifact": review_note_artifact or {},
        "requested_by": requested_by,
        "applies_learning_now": bool(applies_learning_now),
        "changes_prompt_now": bool(changes_prompt_now),
        "changes_runtime_now": bool(changes_runtime_now),
        "dispatch_enabled": bool(dispatch_enabled),
        "writes": bool(writes),
        "created_at": _iso(created_at),
        "latest_event": latest_event,
    }


def _consumption_request_id(proposal_id, target_kind, target_field):
    seed = f"{proposal_id}|{target_kind}|{target_field}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-LEARNING-CONSUME-{digest}"


def _event_id(consumption_request_id, event_type):
    seed = f"{consumption_request_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-LEARNING-CONSUME-EVENT-{digest}"


def _bounded_limit(value, default=20, maximum=50):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(maximum, parsed))


def _clean_text(value, limit):
    return str(value or "").strip()[:limit]


def _json(value):
    return json.dumps(value or {}, default=str, separators=(",", ":"))


def _iso(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _false_flags():
    return {
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }


def _unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "learning_influence_consumption_requests": [],
        "created_count": 0,
        **_false_flags(),
    }
