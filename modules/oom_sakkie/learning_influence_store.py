import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.agent_dry_run_result_store import list_agent_dry_run_results
from services.database_service import DATABASE_URL_ENV


LEARNING_INFLUENCE_EVENT_TYPES = {"approved_for_future_planning", "rejected", "review_note"}


def record_learning_influence_proposals_from_accepted(limit=20, database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    accepted = _accepted_results(limit=limit, database_url=database_url)
    if accepted["status_code"] != 200:
        return {
            "success": False,
            "configured": accepted.get("configured", False),
            "status": accepted["status"],
            "learning_influence_proposals": [],
            "created_count": 0,
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, accepted["status_code"]

    if not database_url:
        return _unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    params = [_learning_influence_params(item) for item in accepted["accepted_results"]]
    if not params:
        return {
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "learning_influence_proposal_queue",
            "created_count": 0,
            "accepted_count": 0,
            "learning_influence_proposals": [],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
            "next_gate": "owner_review_before_learning_influence_is_used",
        }, 200

    created_ids = []
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                for param in params:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_learning_influence_proposals (
                            proposal_id,
                            source_result_id,
                            status,
                            mode,
                            specialist_slug,
                            proposal_title,
                            proposal_text,
                            evidence_json,
                            proposed_rules_json,
                            next_gate,
                            proposed_by,
                            applies_learning_now,
                            changes_prompt_now,
                            changes_runtime_now,
                            dispatch_enabled,
                            writes,
                            created_at
                        )
                        values (
                            %(proposal_id)s,
                            %(source_result_id)s,
                            %(status)s,
                            %(mode)s,
                            %(specialist_slug)s,
                            %(proposal_title)s,
                            %(proposal_text)s,
                            %(evidence_json)s::jsonb,
                            %(proposed_rules_json)s::jsonb,
                            %(next_gate)s,
                            %(proposed_by)s,
                            %(applies_learning_now)s,
                            %(changes_prompt_now)s,
                            %(changes_runtime_now)s,
                            %(dispatch_enabled)s,
                            %(writes)s,
                            now()
                        )
                        on conflict (source_result_id) do nothing
                        returning proposal_id
                        """,
                        param,
                    )
                    row = cursor.fetchone()
                    if row:
                        created_ids.append(row[0])
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_proposal_write_failed",
            "error_type": exc.__class__.__name__,
            "learning_influence_proposals": [],
            "created_count": 0,
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 503

    listed, list_status = list_learning_influence_proposals(limit=max(20, len(params)), database_url=database_url)
    if list_status != 200:
        return listed, list_status
    proposals = [
        item for item in listed.get("learning_influence_proposals", [])
        if item.get("proposal_id") in set(created_ids)
    ]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "learning_influence_proposal_queue",
        "created_count": len(created_ids),
        "accepted_count": len(params),
        "learning_influence_proposals": proposals,
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
        "next_gate": "owner_review_before_learning_influence_is_used",
    }, 201


def list_learning_influence_proposals(limit=20, database_url=None):
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
                    select p.proposal_id, p.source_result_id, p.status, p.mode,
                           p.specialist_slug, p.proposal_title, p.proposal_text,
                           p.evidence_json, p.proposed_rules_json, p.next_gate,
                           p.proposed_by, p.applies_learning_now, p.changes_prompt_now,
                           p.changes_runtime_now, p.dispatch_enabled, p.writes,
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
                    order by p.created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_proposal_read_failed",
            "error_type": exc.__class__.__name__,
            "learning_influence_proposals": [],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "learning_influence_proposal_queue",
        "learning_influence_proposals": [_learning_influence_row(row) for row in rows],
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }, 200


def record_learning_influence_proposal_event(proposal_id, payload, database_url=None):
    proposal_id = _clean_text(proposal_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 50)
    if not proposal_id:
        return {"success": False, "status": "proposal_id_required"}, 400
    if event_type not in LEARNING_INFLUENCE_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(LEARNING_INFLUENCE_EVENT_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "event_id": _event_id(proposal_id, event_type),
        "proposal_id": proposal_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_proposal_events (
                        event_id,
                        proposal_id,
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
                        %(proposal_id)s,
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
            "status": "learning_influence_proposal_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "proposal_id": proposal_id,
        "event_type": event_type,
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }, 201


def _accepted_results(limit=20, database_url=None):
    results_result, status_code = list_agent_dry_run_results(limit=limit, database_url=database_url)
    dry_run_results = results_result.get("dry_run_results", []) if isinstance(results_result, dict) else []
    accepted = [
        item for item in dry_run_results
        if (item.get("latest_event") or {}).get("event_type") == "accepted_for_learning"
    ]
    return {
        "status_code": status_code,
        "status": results_result.get("status", "unavailable") if isinstance(results_result, dict) else "unavailable",
        "configured": results_result.get("configured", False) if isinstance(results_result, dict) else False,
        "accepted_results": accepted[:8],
    }


def _learning_influence_params(result):
    source_result_id = _clean_text(result.get("dry_run_result_id", ""), 100)
    specialist_slug = _clean_text(result.get("specialist_slug", "unknown"), 80).lower() or "unknown"
    findings = [str(item).strip()[:500] for item in list(result.get("findings") or [])[:8] if str(item).strip()]
    result_text = _clean_text(result.get("result_text", ""), 1200)
    accepted_note = _clean_text((result.get("latest_event") or {}).get("notes", ""), 500)
    title = f"Learning proposal from {specialist_slug} evidence"
    proposal_text = _clean_text(
        "Use accepted evidence as planning input only. "
        f"Source result {source_result_id}: {result_text or 'No result text provided.'} "
        f"Owner acceptance note: {accepted_note or 'No owner note.'}",
        4000,
    )
    evidence = {
        "dry_run_result_id": source_result_id,
        "dry_run_request_id": _clean_text(result.get("dry_run_request_id", ""), 100),
        "specialist_slug": specialist_slug,
        "result_text": result_text,
        "findings": findings,
        "accepted_at": (result.get("latest_event") or {}).get("created_at", ""),
        "accepted_note": accepted_note,
    }
    proposed_rules = [
        "Use this accepted evidence to shape future planning questions only.",
        "Do not change prompts, routes, runtime flags, tools, farm data, public output, dispatch, deploy, Telegram, physical controls, or financial behavior.",
        "Require a separate owner and Claude-reviewed gate before any learning influence is applied to behavior.",
    ]
    return {
        "proposal_id": _proposal_id(source_result_id),
        "source_result_id": source_result_id,
        "status": "proposed_for_owner_review",
        "mode": "learning_influence_proposal_only",
        "specialist_slug": specialist_slug,
        "proposal_title": title,
        "proposal_text": proposal_text,
        "evidence_json": _json(evidence),
        "proposed_rules_json": _json(proposed_rules),
        "next_gate": "owner_review_before_learning_influence_is_used",
        "proposed_by": "oom_sakkie_learning_influence",
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }


def _learning_influence_row(row):
    (
        proposal_id,
        source_result_id,
        status,
        mode,
        specialist_slug,
        proposal_title,
        proposal_text,
        evidence,
        proposed_rules,
        next_gate,
        proposed_by,
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
        "proposal_id": proposal_id,
        "source_result_id": source_result_id,
        "status": status,
        "mode": mode,
        "specialist_slug": specialist_slug,
        "proposal_title": proposal_title,
        "proposal_text": proposal_text,
        "evidence": evidence or {},
        "proposed_rules": proposed_rules or [],
        "next_gate": next_gate,
        "proposed_by": proposed_by,
        "applies_learning_now": bool(applies_learning_now),
        "changes_prompt_now": bool(changes_prompt_now),
        "changes_runtime_now": bool(changes_runtime_now),
        "dispatch_enabled": bool(dispatch_enabled),
        "writes": bool(writes),
        "created_at": _iso(created_at),
        "latest_event": latest_event,
    }


def _unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "learning_influence_proposals": [],
        "created_count": 0,
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }


def _proposal_id(source_result_id):
    digest = hashlib.sha256(str(source_result_id or "").encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-LEARNING-INFLUENCE-{digest}"


def _event_id(proposal_id, event_type):
    seed = f"{proposal_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-LEARNING-INFLUENCE-EVENT-{digest}"


def _bounded_limit(value, default=20, maximum=50):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(maximum, parsed))


def _clean_text(value, limit):
    return str(value or "").strip()[:limit]


def _json(value):
    return json.dumps(value or [], default=str, separators=(",", ":"))


def _iso(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)
