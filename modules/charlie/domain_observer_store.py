"""Persistence for proposal-only domain observer telemetry."""

from __future__ import annotations

import json

from modules.charlie.mission_store import _connect, _database_url


def record_observer_run(run, *, database_url=None, connect_factory=None):
    run = run if isinstance(run, dict) else {}
    if run.get("authority_tier") != "observe" or run.get("writes_authorized") is not False or run.get("sends_authorized") is not False:
        return {"success": False, "status": "observer_authority_contract_invalid"}, 400
    required = ("run_id", "observer_key", "domain", "trigger", "status", "ran_at")
    missing = [key for key in required if not run.get(key)]
    if missing:
        return {"success": False, "status": "observer_run_fields_required", "missing_fields": missing}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "observer_store_not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.domain_observer_runs (
                        run_id,observer_key,domain,trigger_type,status,authority_tier,source_refs_json,
                        freshness,facts_json,gaps_json,recommendations_json,writes_authorized,sends_authorized,ran_at
                    ) values (
                        %(run_id)s,%(observer_key)s,%(domain)s,%(trigger)s,%(status)s,'observe',%(sources)s::jsonb,
                        %(freshness)s,%(facts)s::jsonb,%(gaps)s::jsonb,%(recommendations)s::jsonb,false,false,%(ran_at)s
                    ) on conflict (run_id) do nothing returning run_id
                """, {
                    **run,
                    "sources": json.dumps(run.get("source_refs") or []),
                    "facts": json.dumps(run.get("facts") or []),
                    "gaps": json.dumps(run.get("gaps") or []),
                    "recommendations": json.dumps(run.get("recommendations") or []),
                    "freshness": str(run.get("freshness") or "unknown"),
                })
                created = bool(cursor.fetchone())
    except Exception as exc:
        return {"success": False, "status": "observer_run_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "observer_run_recorded" if created else "observer_run_duplicate", "created": created, "run_id": run["run_id"]}, 201 if created else 200


def observer_last_runs(*, database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "observer_store_not_configured", "last_runs": {}}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select observer_key,max(ran_at) from public.domain_observer_runs group by observer_key
                """)
                rows = cursor.fetchall()
    except Exception as exc:
        return {"success": False, "status": "observer_runs_read_failed", "error_type": exc.__class__.__name__, "last_runs": {}}, 503
    return {"success": True, "status": "observer_last_runs_ready", "last_runs": {key: value.isoformat() if hasattr(value, "isoformat") else str(value) for key, value in rows}}, 200
