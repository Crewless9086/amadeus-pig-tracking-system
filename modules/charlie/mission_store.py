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
    "vault_updated",
    "workflow_updated",
}
APPROVAL_LEVELS = {"LEVEL 0", "LEVEL 1", "LEVEL 2", "LEVEL 3", "LEVEL 4", "LEVEL 5"}
MISSION_CONTEXT_DOCS = [
    "docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md",
    "docs/00-start-here/CURRENT_STATE.md",
    "docs/00-start-here/NEXT_STEPS.md",
    "docs/00-start-here/WORKFLOW.md",
    "docs/00-start-here/DEPLOYMENT_SOP.md",
    "docs/00-start-here/OWNER_INBOX_GUIDE.md",
]
AGENT_SEQUENCE = ["planner", "architect", "builder", "tester", "reviewer"]
AGENT_STAGE_MAP = {
    "planner": "planned",
    "architect": "build_ready",
    "builder": "built",
    "tester": "tested",
    "reviewer": "review_ready",
}


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


def update_mission_vault(
    mission_id,
    vault_metadata,
    status="",
    owner_decision="",
    notes="Mission vault updated.",
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if not isinstance(vault_metadata, dict):
        return {"success": False, "status": "mission_vault_metadata_required"}, 400
    status = _clean_text(status, 40)
    if status and status not in MISSION_STATUSES:
        return {"success": False, "status": "invalid_mission_status", "allowed_statuses": sorted(MISSION_STATUSES)}, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    set_lines = [
        "metadata_json = coalesce(metadata_json, '{}'::jsonb) || %(metadata_json)s::jsonb",
        "updated_at = now()",
    ]
    params = {
        "mission_id": mission_id,
        "metadata_json": json.dumps(vault_metadata),
    }
    if status:
        set_lines.insert(0, "status = %(status)s")
        params["status"] = status
    if owner_decision:
        set_lines.insert(0, "owner_decision = %(owner_decision)s")
        params["owner_decision"] = _clean_text(owner_decision, 1000)

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.charlie_missions
                    set {", ".join(set_lines)}
                    where mission_id = %(mission_id)s
                    returning mission_id
                    """,
                    params,
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "configured": True, "status": "not_found", "mission_id": mission_id}, 404
                _insert_event(cursor, mission_id, "vault_updated", notes, {
                    "status": status,
                    "owner_decision": _clean_text(owner_decision, 1000),
                    "vault_keys": sorted(vault_metadata.keys()),
                })
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_vault_update_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "mission_status": status,
        "vault_keys": sorted(vault_metadata.keys()),
    }, 200


def update_mission_workflow_step(
    mission_id,
    agent,
    step_status="complete",
    findings="",
    next_agent="",
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    agent = _clean_text(agent, 40).lower()
    step_status = _clean_text(step_status, 40).lower() or "complete"
    findings = _clean_text(findings, 1200)
    next_agent = _clean_text(next_agent, 40).lower()
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if agent not in AGENT_SEQUENCE:
        return {"success": False, "status": "invalid_agent", "allowed_agents": AGENT_SEQUENCE}, 400
    if step_status not in {"pending", "active", "complete", "blocked"}:
        return {"success": False, "status": "invalid_agent_status"}, 400

    loaded, load_status = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if load_status >= 400:
        return loaded, load_status
    mission = loaded.get("mission") or {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    workflow = metadata.get("agent_workflow") if isinstance(metadata.get("agent_workflow"), list) else _default_agent_workflow()
    updated_workflow = _update_workflow_items(workflow, agent, step_status, findings, next_agent)
    vault = dict(metadata.get("mission_vault") or {})
    if step_status == "complete":
        vault["mission_stage"] = AGENT_STAGE_MAP.get(agent, vault.get("mission_stage", "intake"))
    elif step_status == "blocked":
        vault["mission_stage"] = "blocked"
    if findings:
        handoff_notes = vault.get("handoff_notes") if isinstance(vault.get("handoff_notes"), list) else []
        handoff_notes = list(handoff_notes)
        handoff_notes.append({"agent": agent, "status": step_status, "findings": findings})
        vault["handoff_notes"] = handoff_notes[-12:]
    context_pack = metadata.get("mission_context_pack") if isinstance(metadata.get("mission_context_pack"), dict) else _default_context_pack()

    status = ""
    if agent == "reviewer" and step_status == "complete":
        status = "pr_ready"
    elif step_status == "blocked":
        status = "blocked"

    return update_mission_vault(
        mission_id,
        {
            "mission_vault": vault,
            "agent_workflow": updated_workflow,
            "mission_context_pack": context_pack,
        },
        status=status,
        owner_decision=f"{agent} step marked {step_status}." if status else "",
        notes=f"Mission workflow updated: {agent} -> {step_status}.",
        database_url=database_url,
        connect_factory=connect_factory,
    )


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
    metadata = mission.get("metadata", {}) if isinstance(mission.get("metadata"), dict) else {}
    metadata = _mission_metadata(raw_text, mission, source_context, metadata)
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
        "metadata_json": json.dumps(metadata),
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
    metadata = row[13] if isinstance(row[13], dict) else {}
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
        "metadata": metadata,
        "vault": metadata.get("mission_vault", {}) if isinstance(metadata.get("mission_vault"), dict) else {},
        "agent_workflow": metadata.get("agent_workflow", []) if isinstance(metadata.get("agent_workflow"), list) else [],
        "media_references": metadata.get("media_references", []) if isinstance(metadata.get("media_references"), list) else [],
        "mission_context_pack": metadata.get("mission_context_pack", {}) if isinstance(metadata.get("mission_context_pack"), dict) else {},
        "created_at": _iso(row[14]),
        "updated_at": _iso(row[15]),
    }


def _mission_metadata(raw_text, mission, source_context, metadata):
    metadata = dict(metadata or {})
    metadata.setdefault("mission_vault", _default_mission_vault(raw_text, mission))
    metadata.setdefault("agent_workflow", _default_agent_workflow())
    metadata.setdefault("mission_context_pack", _default_context_pack())
    media_references = mission.get("media_references")
    if isinstance(media_references, list):
        metadata["media_references"] = [_clean_media_reference(item) for item in media_references if _clean_media_reference(item)]
    else:
        metadata.setdefault("media_references", [])
    metadata.setdefault("intake", {
        "source": _clean_text(source_context.get("source", "telegram"), 60) or "telegram",
        "requires_planner": True,
        "requires_builder": True,
        "requires_tester": True,
        "requires_reviewer": True,
    })
    return metadata


def _default_mission_vault(raw_text, mission):
    return {
        "mission_stage": "intake",
        "problem_statement": _clean_text(raw_text, 1200),
        "desired_outcome": _clean_text(mission.get("desired_outcome", ""), 1200),
        "scope_summary": _clean_text(mission.get("scope_summary", ""), 1200),
        "acceptance_criteria": _clean_list(mission.get("acceptance_criteria")),
        "test_plan": _clean_list(mission.get("test_plan")),
        "pressure_test_plan": _clean_list(mission.get("pressure_test_plan")),
        "forbidden_actions": _clean_list(mission.get("forbidden_actions")) or _default_forbidden_actions(),
        "owner_decisions_needed": _clean_list(mission.get("owner_decisions_needed")),
        "confidence_target": _clean_text(mission.get("confidence_target", "98% before owner release review"), 80),
        "rollback_plan": _clean_text(mission.get("rollback_plan", "Revert the scoped PR or pause the mission before release."), 800),
    }


def _default_agent_workflow():
    return [
        {"agent": "planner", "status": "pending", "purpose": "Turn owner concept into scoped mission plan.", "handoff_to": "architect", "findings": ""},
        {"agent": "architect", "status": "pending", "purpose": "Identify files, data sources, risks, and acceptance criteria.", "handoff_to": "builder", "findings": ""},
        {"agent": "builder", "status": "pending", "purpose": "Implement scoped changes under approval level.", "handoff_to": "tester", "findings": ""},
        {"agent": "tester", "status": "pending", "purpose": "Run tests and pressure checks.", "handoff_to": "reviewer", "findings": ""},
        {"agent": "reviewer", "status": "pending", "purpose": "Review diff, unsafe actions, docs, and release notes.", "handoff_to": "owner", "findings": ""},
    ]


def _default_context_pack():
    return {
        "version": "charlie_context_pack_v1",
        "active_truth_docs": list(MISSION_CONTEXT_DOCS),
        "shared_data_rules": [
            "Supabase is the canonical durable source where migrations have cut over the app.",
            "Google Sheets is legacy/reference/export unless a route is explicitly still in fallback mode.",
            "Mission findings must be recorded in the Mission Vault before handoff to the next role.",
            "Builder agents must use the Mission Vault, active docs, acceptance criteria, tests, and forbidden actions before editing.",
        ],
        "approval_rules": [
            "LEVEL 1 is read-only investigation.",
            "LEVEL 2 is docs/planning only.",
            "LEVEL 3 may build, test, commit, push, and open PR; it may not merge.",
            "LEVEL 4 may merge after verified diff/tests; red-zone actions still require explicit approval.",
        ],
        "agent_order": list(AGENT_SEQUENCE),
        "parallel_work": "disabled_until_phase_6_parallel_controls",
    }


def _default_forbidden_actions():
    return [
        "No production data writes unless explicitly approved.",
        "No migrations unless explicitly approved.",
        "No customer sends, public posts, payments, reservations, or lifecycle writes unless explicitly approved.",
        "No .env, secrets, screenshots, external_sources, static/assets, or planning/Prompts.md unless explicitly approved.",
    ]


def _update_workflow_items(workflow, agent, step_status, findings, next_agent):
    known = {item.get("agent"): dict(item) for item in workflow if isinstance(item, dict)}
    for default in _default_agent_workflow():
        known.setdefault(default["agent"], dict(default))
    if next_agent and next_agent in AGENT_SEQUENCE:
        known[agent]["handoff_to"] = next_agent
    known[agent]["status"] = step_status
    if findings:
        known[agent]["findings"] = findings
    if step_status == "complete":
        handoff_to = known[agent].get("handoff_to")
        if handoff_to in known and known[handoff_to].get("status") == "pending":
            known[handoff_to]["status"] = "active"
    return [known[name] for name in AGENT_SEQUENCE]


def _clean_list(value, max_items=12, max_len=300):
    if isinstance(value, str):
        raw_items = [line.strip("- ").strip() for line in value.splitlines()]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    items = []
    for item in raw_items:
        clean = _clean_text(item, max_len)
        if clean:
            items.append(clean)
        if len(items) >= max_items:
            break
    return items


def _clean_media_reference(item):
    if isinstance(item, str):
        text = _clean_text(item, 500)
        return {"label": text[:80], "reference": text} if text else {}
    if not isinstance(item, dict):
        return {}
    reference = _clean_text(item.get("reference") or item.get("url") or item.get("path"), 500)
    if not reference:
        return {}
    return {
        "label": _clean_text(item.get("label") or reference, 120),
        "reference": reference,
        "media_type": _clean_text(item.get("media_type", "reference"), 40),
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
