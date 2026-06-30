import hashlib
import json
import os
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


MISSION_STATUSES = {
    "new",
    "triaged",
    "planned",
    "approved",
    "in_progress",
    "blocked",
    "pr_ready",
    "merged",
    "deployed",
    "done",
    "paused",
    "rejected",
}
MISSION_EVENT_TYPES = {
    "created",
    "selected_next_step",
    "codex_chat_write",
    "status_changed",
    "approval_decision",
    "review_note",
}
APPROVAL_LEVELS = {"LEVEL 0", "LEVEL 1", "LEVEL 2", "LEVEL 3", "LEVEL 4", "LEVEL 5"}


def record_mission(mission, source_context=None, database_url=None, connect_factory=None):
    mission = mission if isinstance(mission, dict) else {}
    source_context = source_context if isinstance(source_context, dict) else {}
    raw_text = _clean_text(mission.get("raw_text", ""), 3000)
    if not raw_text:
        return {"stored": False, "status": "mission_text_required"}, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"stored": False, "configured": False, "status": "not_configured"}, 503

    params = _mission_params(mission, source_context)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.charlie_missions (
                        mission_id,
                        status,
                        source,
                        source_message_id,
                        telegram_user_id,
                        telegram_chat_id,
                        raw_text,
                        title,
                        urgency,
                        mission_type,
                        approval_level,
                        selected_next_step,
                        owner_decision,
                        codex_chat_write_status,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    values (
                        %(mission_id)s,
                        %(status)s,
                        %(source)s,
                        %(source_message_id)s,
                        %(telegram_user_id)s,
                        %(telegram_chat_id)s,
                        %(raw_text)s,
                        %(title)s,
                        %(urgency)s,
                        %(mission_type)s,
                        %(approval_level)s,
                        %(selected_next_step)s,
                        %(owner_decision)s,
                        %(codex_chat_write_status)s,
                        %(metadata_json)s::jsonb,
                        now(),
                        now()
                    )
                    on conflict (mission_id) do update set
                        updated_at = now()
                    """,
                    params,
                )
                _insert_event(cursor, params["mission_id"], "created", "Mission intake recorded.", {
                    "source": params["source"],
                    "telegram_user_id": params["telegram_user_id"],
                })
    except Exception as exc:
        return {
            "stored": False,
            "configured": True,
            "status": "mission_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "stored": True,
        "configured": True,
        "status": "ok",
        "mission_id": params["mission_id"],
    }, 201


def list_missions(status="", limit=10, database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "missions": []}, 503

    parsed_limit = _bounded_limit(limit)
    clean_status = _clean_text(status, 40)
    params = {"status": clean_status, "limit": parsed_limit}
    where_clause = "where status = %(status)s" if clean_status else ""
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select mission_id, status, source, telegram_user_id, telegram_chat_id,
                           raw_text, title, urgency, mission_type, approval_level,
                           selected_next_step, owner_decision, codex_chat_write_status,
                           metadata_json, created_at, updated_at
                    from public.charlie_missions
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
            "status": "mission_read_failed",
            "error_type": exc.__class__.__name__,
            "missions": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "missions": [_mission_row(row) for row in rows],
    }, 200


def get_mission(mission_id, database_url=None, connect_factory=None):
    mission_id = _clean_text(mission_id, 90)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select mission_id, status, source, telegram_user_id, telegram_chat_id,
                           raw_text, title, urgency, mission_type, approval_level,
                           selected_next_step, owner_decision, codex_chat_write_status,
                           metadata_json, created_at, updated_at
                    from public.charlie_missions
                    where mission_id = %(mission_id)s
                    limit 1
                    """,
                    {"mission_id": mission_id},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_read_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    if not rows:
        return {"success": False, "configured": True, "status": "not_found", "mission_id": mission_id}, 404
    return {"success": True, "configured": True, "status": "ok", "mission": _mission_row(rows[0])}, 200


def update_mission_status(
    mission_id,
    status,
    owner_decision="",
    approval_level="",
    event_type="status_changed",
    notes="",
    metadata=None,
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    status = _clean_text(status, 40)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if status not in MISSION_STATUSES:
        return {"success": False, "status": "invalid_mission_status", "allowed_statuses": sorted(MISSION_STATUSES)}, 400
    if event_type not in MISSION_EVENT_TYPES:
        return {"success": False, "status": "invalid_event_type", "allowed_event_types": sorted(MISSION_EVENT_TYPES)}, 400
    approval_level = normalize_approval_level(approval_level)
    if approval_level and approval_level not in APPROVAL_LEVELS:
        return {"success": False, "status": "invalid_approval_level", "allowed_approval_levels": sorted(APPROVAL_LEVELS)}, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    set_lines = [
        "status = %(status)s",
        "owner_decision = %(owner_decision)s",
    ]
    if approval_level:
        set_lines.append("approval_level = %(approval_level)s")
    set_lines.append("updated_at = now()")
    set_sql = ",\n                        ".join(set_lines)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.charlie_missions
                    set {set_sql}
                    where mission_id = %(mission_id)s
                    returning mission_id
                    """,
                    {
                        "mission_id": mission_id,
                        "status": status,
                        "owner_decision": _clean_text(owner_decision, 1000),
                        "approval_level": approval_level,
                    },
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "configured": True, "status": "not_found", "mission_id": mission_id}, 404
                _insert_event(cursor, mission_id, event_type, notes or f"Mission status changed to {status}.", {
                    "status": status,
                    "approval_level": approval_level,
                    "owner_decision": _clean_text(owner_decision, 1000),
                    **(metadata if isinstance(metadata, dict) else {}),
                })
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_status_update_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "mission_status": status,
        "approval_level": approval_level,
    }, 200


def normalize_approval_level(value):
    raw = _clean_text(value, 40).upper().replace("_", " ").replace("-", " ")
    if not raw:
        return ""
    compact = " ".join(raw.split())
    if compact.startswith("LEVEL "):
        return compact
    if compact.startswith("LEVEL") and compact[5:].strip().isdigit():
        return f"LEVEL {compact[5:].strip()}"
    if compact in {"0", "1", "2", "3", "4", "5"}:
        return f"LEVEL {compact}"
    return compact


def record_mission_event(mission_id, event_type, notes="", metadata=None, database_url=None, connect_factory=None):
    mission_id = _clean_text(mission_id, 90)
    event_type = _clean_text(event_type, 40)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if event_type not in MISSION_EVENT_TYPES:
        return {"success": False, "status": "invalid_event_type", "allowed_event_types": sorted(MISSION_EVENT_TYPES)}, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                _insert_event(cursor, mission_id, event_type, notes, metadata or {})
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_event_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {"success": True, "configured": True, "status": "ok", "mission_id": mission_id}, 201


def mission_status_summary(database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "counts": {}}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select status, count(*)
                    from public.charlie_missions
                    group by status
                    order by status
                    """
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_summary_failed",
            "error_type": exc.__class__.__name__,
            "counts": {},
        }, 503
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "counts": {str(row[0]): int(row[1] or 0) for row in rows},
    }, 200


def _mission_params(mission, source_context):
    raw_text = _clean_text(mission.get("raw_text", ""), 3000)
    now = datetime.now(timezone.utc).isoformat()
    mission_id = _clean_text(mission.get("mission_id", ""), 90) or _mission_id(raw_text, source_context, now)
    return {
        "mission_id": mission_id,
        "status": _clean_text(mission.get("status", "new"), 40) or "new",
        "source": _clean_text(source_context.get("source", "telegram"), 60) or "telegram",
        "source_message_id": _clean_text(source_context.get("message_id", ""), 120),
        "telegram_user_id": _clean_text(source_context.get("telegram_user_id", ""), 80),
        "telegram_chat_id": _clean_text(source_context.get("telegram_chat_id", ""), 80),
        "raw_text": raw_text,
        "title": _clean_text(mission.get("title", raw_text), 160),
        "urgency": _clean_text(mission.get("urgency", "P2"), 20),
        "mission_type": _clean_text(mission.get("mission_type", "feature build"), 60),
        "approval_level": _clean_text(mission.get("approval_level", "LEVEL 3"), 40),
        "selected_next_step": _clean_text(mission.get("selected_next_step", ""), 1000),
        "owner_decision": _clean_text(mission.get("owner_decision", ""), 1000),
        "codex_chat_write_status": _clean_text(mission.get("codex_chat_write_status", ""), 80),
        "metadata_json": json.dumps(mission.get("metadata", {}) if isinstance(mission.get("metadata"), dict) else {}),
    }


def _insert_event(cursor, mission_id, event_type, notes, metadata):
    params = {
        "event_id": _event_id(mission_id, event_type),
        "mission_id": mission_id,
        "event_type": event_type,
        "notes": _clean_text(notes, 1000),
        "metadata_json": json.dumps(metadata if isinstance(metadata, dict) else {}),
    }
    cursor.execute(
        """
        insert into public.charlie_mission_events (
            event_id,
            mission_id,
            event_type,
            notes,
            metadata_json,
            created_at
        )
        values (
            %(event_id)s,
            %(mission_id)s,
            %(event_type)s,
            %(notes)s,
            %(metadata_json)s::jsonb,
            now()
        )
        on conflict (event_id) do nothing
        """,
        params,
    )


def _mission_row(row):
    return {
        "mission_id": row[0],
        "status": row[1],
        "source": row[2],
        "telegram_user_id": row[3],
        "telegram_chat_id": row[4],
        "raw_text": row[5],
        "title": row[6],
        "urgency": row[7],
        "mission_type": row[8],
        "approval_level": row[9],
        "selected_next_step": row[10],
        "owner_decision": row[11],
        "codex_chat_write_status": row[12],
        "metadata": row[13] if isinstance(row[13], dict) else {},
        "created_at": _iso(row[14]),
        "updated_at": _iso(row[15]),
    }


def _database_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _connect(database_url, connect_factory=None):
    if connect_factory:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _mission_id(raw_text, source_context, created_at):
    seed = "|".join([
        raw_text,
        _clean_text(source_context.get("telegram_user_id", ""), 80),
        _clean_text(source_context.get("telegram_chat_id", ""), 80),
        created_at,
    ])
    return "CHARLIE-MISSION-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()


def _event_id(mission_id, event_type):
    seed = f"{mission_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}"
    return "CHARLIE-MISSION-EVENT-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:18].upper()


def _bounded_limit(limit):
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, 50))


def _clean_text(value, max_len):
    return str(value or "").strip()[:max_len]


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
