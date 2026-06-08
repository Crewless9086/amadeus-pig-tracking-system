import hashlib
import os
from datetime import datetime, timezone

from modules.oom_sakkie.patch_proposal_store import get_patch_proposal
from services.database_service import DATABASE_URL_ENV


DEPLOY_DECISION_TYPES = {"approved_for_manual_deploy", "rejected", "deferred", "review_note"}


def record_deploy_decision(patch_proposal_id, payload, database_url=None):
    patch_proposal_id = _clean_text(patch_proposal_id, 90)
    payload = payload if isinstance(payload, dict) else {}
    decision_type = _clean_text(payload.get("decision_type", ""), 40)
    if not patch_proposal_id:
        return {"success": False, "status": "patch_proposal_id_required"}, 400
    if decision_type not in DEPLOY_DECISION_TYPES:
        return {
            "success": False,
            "status": "invalid_decision_type",
            "allowed_decision_types": sorted(DEPLOY_DECISION_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    patch_result, patch_status = get_patch_proposal(patch_proposal_id, database_url=database_url)
    if patch_status != 200:
        return patch_result, patch_status
    patch = patch_result.get("patch_proposal", {})
    latest_event = patch.get("latest_event") or {}
    if decision_type == "approved_for_manual_deploy" and latest_event.get("event_type") != "approved_for_patch":
        return {
            "success": False,
            "configured": True,
            "status": "patch_not_approved",
            "patch_proposal_id": patch_proposal_id,
            "required_event": "approved_for_patch",
        }, 409

    params = _deploy_decision_params(patch_proposal_id, payload)
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_deploy_decisions (
                        deploy_decision_id,
                        patch_proposal_id,
                        decision_type,
                        environment,
                        notes,
                        verification_summary,
                        approved_by,
                        runs_deploy,
                        deploys_now,
                        created_at
                    )
                    values (
                        %(deploy_decision_id)s,
                        %(patch_proposal_id)s,
                        %(decision_type)s,
                        %(environment)s,
                        %(notes)s,
                        %(verification_summary)s,
                        %(approved_by)s,
                        %(runs_deploy)s,
                        %(deploys_now)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "deploy_decision_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "deploy_approval_record_only",
        "deploy_decision_id": params["deploy_decision_id"],
        "patch_proposal_id": patch_proposal_id,
        "decision_type": decision_type,
        "runs_deploy": False,
        "deploys_now": False,
        "requires_manual_deploy": decision_type == "approved_for_manual_deploy",
    }, 201


def list_deploy_decisions(patch_proposal_id="", limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    patch_proposal_id = _clean_text(patch_proposal_id, 90)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "deploy_decisions": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "deploy_decisions": []}, 500

    params = {"patch_proposal_id": patch_proposal_id, "limit": parsed_limit}
    where_clause = "where patch_proposal_id = %(patch_proposal_id)s" if patch_proposal_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select deploy_decision_id, patch_proposal_id, decision_type, environment,
                           notes, verification_summary, approved_by, runs_deploy,
                           deploys_now, created_at
                    from public.oom_sakkie_deploy_decisions
                    {where_clause}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "deploy_decision_read_failed",
            "error_type": exc.__class__.__name__,
            "deploy_decisions": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "deploy_approval_record_only",
        "runs_deploy": False,
        "deploys_now": False,
        "deploy_decisions": [_deploy_decision_row(row) for row in rows],
    }, 200


def _deploy_decision_params(patch_proposal_id, payload):
    return {
        "deploy_decision_id": _deploy_decision_id(patch_proposal_id, payload.get("decision_type", "")),
        "patch_proposal_id": patch_proposal_id,
        "decision_type": _clean_text(payload.get("decision_type", ""), 40),
        "environment": _clean_text(payload.get("environment", "local"), 40),
        "notes": _clean_text(payload.get("notes", ""), 2000),
        "verification_summary": _clean_text(payload.get("verification_summary", ""), 3000),
        "approved_by": _clean_text(payload.get("approved_by", "owner"), 80),
        "runs_deploy": False,
        "deploys_now": False,
    }


def _deploy_decision_row(row):
    (
        deploy_decision_id,
        patch_proposal_id,
        decision_type,
        environment,
        notes,
        verification_summary,
        approved_by,
        runs_deploy,
        deploys_now,
        created_at,
    ) = row
    return {
        "deploy_decision_id": deploy_decision_id,
        "patch_proposal_id": patch_proposal_id,
        "mode": "deploy_approval_record_only",
        "decision_type": decision_type,
        "environment": environment or "",
        "notes": notes or "",
        "verification_summary": verification_summary or "",
        "approved_by": approved_by or "",
        "runs_deploy": bool(runs_deploy),
        "deploys_now": bool(deploys_now),
        "created_at": _iso(created_at),
    }


def _deploy_decision_id(patch_proposal_id, decision_type):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(f"{patch_proposal_id}:{decision_type}:{stamp}".encode("utf-8")).hexdigest()[:8].upper()
    return f"OSK-DEPLOY-{stamp}-{digest}"


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 20
    return max(1, min(parsed, 50))


def _clean_text(value, max_length):
    return str(value or "").strip()[:max_length]


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
