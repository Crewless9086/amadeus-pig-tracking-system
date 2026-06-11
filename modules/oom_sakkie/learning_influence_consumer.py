import os

from services.database_service import DATABASE_URL_ENV

from modules.oom_sakkie.learning_influence_consumption_store import (
    LEARNING_INFLUENCE_CONSUMPTION_TARGET_KINDS,
    record_learning_influence_consumption_event,
)


def produce_learning_influence_review_note_artifact(consumption_request_id, payload=None, database_url=None):
    consumption_request_id = _clean_text(consumption_request_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    if not consumption_request_id:
        return {"success": False, "status": "consumption_request_id_required", **_false_flags()}, 400

    record, status_code = _load_consumption_design_record(consumption_request_id, database_url=database_url)
    if status_code != 200:
        return record, status_code

    if record.get("has_consumed_marker"):
        return _already_consumed(consumption_request_id), 409

    request_latest = record.get("request_latest_event") or {}
    if request_latest.get("event_type") != "approved_for_design_review":
        return {
            "success": False,
            "configured": True,
            "status": "consumption_request_not_approved_for_design_review",
            "consumption_request_id": consumption_request_id,
            "latest_event": request_latest,
            "review_note_artifact_only": True,
            **_false_flags(),
        }, 409

    proposal_latest = record.get("proposal_latest_event") or {}
    if proposal_latest.get("event_type") != "approved_for_future_planning":
        return {
            "success": False,
            "configured": True,
            "status": "source_proposal_not_approved_for_future_planning",
            "consumption_request_id": consumption_request_id,
            "proposal_id": record.get("proposal_id", ""),
            "latest_event": proposal_latest,
            "review_note_artifact_only": True,
            **_false_flags(),
        }, 409

    if record.get("requested_target_kind") not in LEARNING_INFLUENCE_CONSUMPTION_TARGET_KINDS or not record.get("requested_target_field"):
        return {
            "success": False,
            "configured": True,
            "status": "consumption_target_not_allowlisted",
            "consumption_request_id": consumption_request_id,
            "review_note_artifact_only": True,
            **_false_flags(),
        }, 409

    consumed, consumed_status = record_learning_influence_consumption_event(
        consumption_request_id,
        {
            "event_type": "consumed_for_patch_proposal",
            "notes": _clean_text(payload.get("notes", "review-note artifact produced by reviewed consumer"), 1200),
            "recorded_by": _clean_text(payload.get("recorded_by", "learning_influence_review_note_consumer"), 80),
        },
        database_url=database_url,
        allow_consumed=True,
    )
    if consumed_status != 201:
        if consumed.get("error_type") in {"UniqueViolation", "IntegrityError"}:
            return _already_consumed(consumption_request_id), 409
        return consumed, consumed_status

    artifact = _review_note_artifact(record, payload)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "learning_influence_review_note_consumer_only",
        "consumption_request_id": consumption_request_id,
        "event_id": consumed.get("event_id", ""),
        "review_note_artifact": artifact,
        "review_note_artifact_only": True,
        "manual_application_outside_kiosk_only": True,
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
        "next_gate": "manual_owner_review_outside_kiosk_no_prompt_route_runtime_apply",
    }, 201


def _load_consumption_design_record(consumption_request_id, database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", **_false_flags()}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", **_false_flags()}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select r.consumption_request_id, r.proposal_id, r.source_result_id,
                           r.requested_target_kind, r.requested_target_field,
                           r.request_note, r.review_note_artifact_json,
                           req_ev.event_type, req_ev.notes, req_ev.recorded_by, req_ev.created_at,
                           p.specialist_slug, p.proposal_text,
                           prop_ev.event_type, prop_ev.notes, prop_ev.recorded_by, prop_ev.created_at,
                           exists (
                               select 1
                               from public.oom_sakkie_learning_influence_consumption_events consumed
                               where consumed.consumption_request_id = r.consumption_request_id
                                 and consumed.event_type = 'consumed_for_patch_proposal'
                           ) as has_consumed_marker
                    from public.oom_sakkie_learning_influence_consumption_requests r
                    join public.oom_sakkie_learning_influence_proposals p
                      on p.proposal_id = r.proposal_id
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_learning_influence_consumption_events e
                        where e.consumption_request_id = r.consumption_request_id
                        order by created_at desc
                        limit 1
                    ) req_ev on true
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_learning_influence_proposal_events e
                        where e.proposal_id = p.proposal_id
                        order by created_at desc
                        limit 1
                    ) prop_ev on true
                    where r.consumption_request_id = %(consumption_request_id)s
                    limit 1
                    """,
                    {"consumption_request_id": consumption_request_id},
                )
                row = cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "learning_influence_consumer_read_failed",
            "error_type": exc.__class__.__name__,
            **_false_flags(),
        }, 503

    if not row:
        return {
            "success": False,
            "configured": True,
            "status": "consumption_request_not_found",
            "consumption_request_id": consumption_request_id,
            **_false_flags(),
        }, 404
    return {"success": True, "configured": True, "status": "ok", **_row_record(row), **_false_flags()}, 200


def _row_record(row):
    (
        consumption_request_id,
        proposal_id,
        source_result_id,
        requested_target_kind,
        requested_target_field,
        request_note,
        review_note_artifact,
        req_event_type,
        req_event_notes,
        req_recorded_by,
        req_created_at,
        specialist_slug,
        proposal_text,
        prop_event_type,
        prop_event_notes,
        prop_recorded_by,
        prop_created_at,
        has_consumed_marker,
    ) = row
    return {
        "consumption_request_id": consumption_request_id,
        "proposal_id": proposal_id,
        "source_result_id": source_result_id,
        "specialist_slug": specialist_slug or "",
        "requested_target_kind": requested_target_kind,
        "requested_target_field": requested_target_field,
        "request_note": request_note or "",
        "proposal_text": proposal_text or "",
        "review_note_artifact": review_note_artifact or {},
        "request_latest_event": _event(req_event_type, req_event_notes, req_recorded_by, req_created_at),
        "proposal_latest_event": _event(prop_event_type, prop_event_notes, prop_recorded_by, prop_created_at),
        "has_consumed_marker": bool(has_consumed_marker),
    }


def _review_note_artifact(record, payload):
    source_excerpt = _clean_text(
        (record.get("review_note_artifact") or {}).get("source_excerpt") or record.get("proposal_text", ""),
        500,
    )
    proposed_text = _clean_text(
        payload.get("proposed_review_note_text")
        or record.get("request_note")
        or f"{record.get('requested_target_kind')}::{record.get('requested_target_field')} review note: {source_excerpt}",
        1200,
    )
    previous_text = _clean_text(payload.get("previous_review_note_text", ""), 1200)
    return {
        "kind": "review_note_only",
        "target_kind": record.get("requested_target_kind", ""),
        "target_field": record.get("requested_target_field", ""),
        "proposed_review_note_text": proposed_text,
        "source_excerpt": source_excerpt,
        "source_provenance": {
            "consumption_request_id": record.get("consumption_request_id", ""),
            "proposal_id": record.get("proposal_id", ""),
            "source_result_id": record.get("source_result_id", ""),
            "specialist_slug": record.get("specialist_slug", ""),
            "request_latest_event": record.get("request_latest_event") or {},
            "proposal_latest_event": record.get("proposal_latest_event") or {},
        },
        "rollback_artifact": {
            "target_kind": record.get("requested_target_kind", ""),
            "target_field": record.get("requested_target_field", ""),
            "previous_review_note_text": previous_text,
            "rollback_text": previous_text,
            "manual_application_steps": "If the owner manually used this note outside the kiosk, restore previous_review_note_text manually outside the kiosk.",
        },
        "proposal_text_is_untrusted": True,
        "manual_application_outside_kiosk_only": True,
        "forbidden_fields_present": False,
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }


def _already_consumed(consumption_request_id):
    return {
        "success": False,
        "configured": True,
        "status": "already_consumed",
        "consumption_request_id": consumption_request_id,
        "review_note_artifact": {},
        "review_note_artifact_only": True,
        **_false_flags(),
    }


def _event(event_type, notes, recorded_by, created_at):
    if not event_type:
        return None
    return {
        "event_type": event_type,
        "notes": notes or "",
        "recorded_by": recorded_by or "",
        "created_at": str(created_at or ""),
    }


def _clean_text(value, limit):
    return str(value or "").strip()[:limit]


def _false_flags():
    return {
        "applies_learning_now": False,
        "changes_prompt_now": False,
        "changes_runtime_now": False,
        "dispatch_enabled": False,
        "writes": False,
    }
