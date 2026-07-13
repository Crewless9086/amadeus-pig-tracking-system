import hashlib
import json
import os
import re
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV
from modules.charlie.core_workflow import (
    HANDOFF_VERSION,
    SPECIALIST_AGENTS,
    WORKFLOW_TEMPLATES,
    attach_core_plan_to_metadata,
    build_core_plan,
    build_handoff_report,
    build_income_stream_readiness,
    build_review_board_packet,
    agent_instruction_pack,
    evaluate_core_readiness,
)
from modules.charlie import vault_store
from modules.charlie.mission_governance import ensure_acceptance_matrix


MISSION_STATUSES = {
    "new",
    "triaged",
    "planned",
    "approved",
    "in_progress",
    "blocked",
    "pr_ready",
    "release_approved",
    "release_in_progress",
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
    "mission_updated",
    "vault_updated",
    "workflow_updated",
    "queue_updated",
}
APPROVAL_LEVELS = {"LEVEL 0", "LEVEL 1", "LEVEL 2", "LEVEL 3", "LEVEL 4", "LEVEL 5"}
MISSION_MEDIA_DATA_URL_PATTERN = re.compile(r"^data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=\r\n]+$")
MISSION_MEDIA_DATA_URL_MAX_LEN = 900_000
MISSION_CONTEXT_DOCS = [
    "docs/09-vault-brain/INDEX.md",
    "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
    "docs/09-vault-brain/00-governance/UPDATE_RULES.md",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/01-identity/SYSTEM_HIERARCHY.md",
    "docs/09-vault-brain/01-identity/CHARLIE.md",
    "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
    "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
    "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
    "docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md",
    "docs/00-start-here/CURRENT_STATE.md",
    "docs/00-start-here/NEXT_STEPS.md",
    "docs/00-start-here/WORKFLOW.md",
    "docs/00-start-here/DEPLOYMENT_SOP.md",
    "docs/00-start-here/OWNER_INBOX_GUIDE.md",
]
AGENT_SEQUENCE = ["planner", "architect", "builder", "tester", "reviewer"]
CORE_AGENT_SEQUENCE_V2 = ["planner", "architect", "builder", "tester", "qa_red_team", "reviewer"]
SPECIALIST_AGENT_SEQUENCE = ["idea_expander", "product_architect"]
AGENT_DEFINITIONS = {
    "idea_expander": {
        "purpose": "Expand rough owner idea into a clearer opportunity, user outcome, and non-goals.",
        "handoff_to": "product_architect",
        "mission_types": {"agent build", "system improvement", "workflow", "business plan", "income stream", "content engine"},
    },
    "product_architect": {
        "purpose": "Shape product flow, owner value, user behavior, and acceptance boundaries.",
        "handoff_to": "planner",
        "mission_types": {"agent build", "system improvement", "workflow", "business plan", "income stream", "content engine"},
    },
    "planner": {
        "purpose": "Turn owner concept into scoped mission plan.",
        "handoff_to": "architect",
    },
    "architect": {
        "purpose": "Identify files, data sources, risks, and implementation approach.",
        "handoff_to": "builder",
    },
    "builder": {
        "purpose": "Implement scoped changes under approval level.",
        "handoff_to": "tester",
    },
    "tester": {
        "purpose": "Run tests and pressure checks.",
        "handoff_to": "qa_red_team",
    },
    "qa_red_team": {
        "purpose": "Challenge the work for regressions, unsafe actions, weak evidence, and owner-risk before review.",
        "handoff_to": "reviewer",
    },
    "reviewer": {
        "purpose": "Review diff, unsafe actions, docs, test evidence, QA findings, and release notes.",
        "handoff_to": "owner",
    },
}
for _agent_name, _agent_definition in SPECIALIST_AGENTS.items():
    AGENT_DEFINITIONS.setdefault(_agent_name, {
        "purpose": _agent_definition.get("purpose", ""),
        "handoff_to": "owner",
    })
AGENT_STAGE_MAP = {
    "idea_expander": "idea_expanded",
    "concept_strategist": "concept_defined",
    "product_architect": "product_ready",
    "visual_reference_interpreter": "visual_reference_mapped",
    "creative_ui_designer": "ui_concept_ready",
    "ux_interaction_designer": "interaction_spec_ready",
    "technical_architect": "architecture_ready",
    "source_mapper": "implementation_mapped",
    "business_model_agent": "business_model_ready",
    "risk_agent": "risk_reviewed",
    "planner": "planned",
    "architect": "build_ready",
    "builder": "built",
    "frontend_design_implementer": "frontend_implemented",
    "tester": "tested",
    "qa_red_team": "qa_reviewed",
    "visual_qa_reviewer": "visual_qa_reviewed",
    "security_reviewer": "security_reviewed",
    "evidence_reviewer": "evidence_reviewed",
    "product_reviewer": "product_reviewed",
    "business_reviewer": "business_reviewed",
    "reviewer": "review_ready",
    "publisher": "release_ready",
}
REVIEW_DECISIONS = {
    "approve_final_release",
    "send_back",
    "pause",
    "reject",
    "mark_done",
}
REVIEW_DECISION_STATUS = {
    "approve_final_release": "release_approved",
    "send_back": "approved",
    "pause": "paused",
    "reject": "rejected",
    "mark_done": "done",
}
QUEUE_ORDERED_STATUSES = {"approved", "pr_ready", "blocked", "release_approved"}
OWNER_QUEUE_FILTERS = {"owner_queue", "owner", "active_owner", "actionable"}
OWNER_QUEUE_STATUSES = (
    "in_progress",
    "release_in_progress",
    "pr_ready",
    "blocked",
    "release_approved",
    "approved",
    "new",
)
QUEUE_PRIORITY_DEFAULT = 100
QUEUE_PRIORITY_MAX = 999
OPEN_DUPLICATE_STATUSES = {
    "new",
    "triaged",
    "planned",
    "approved",
    "in_progress",
    "blocked",
    "pr_ready",
    "release_approved",
    "release_in_progress",
}
PLACEHOLDER_MISSION_TITLES = {
    "build charlie relay",
    "charlie relay",
    "<idea>",
}
SYSTEM_TEST_MISSION_MARKERS = (
    "smoke test",
    "validation mission",
    "system validation",
    "runner validation",
    "queue validation",
    "relay validation",
    "test mission",
    "canary mission",
    "no-op mission",
    "noop mission",
)


def record_mission(mission, source_context=None, database_url=None, connect_factory=None):
    mission = mission if isinstance(mission, dict) else {}
    source_context = source_context if isinstance(source_context, dict) else {}
    raw_text = _clean_text(mission.get("raw_text", ""), 3000)
    if not raw_text:
        return {"stored": False, "status": "mission_text_required"}, 400
    intake_quality = _mission_intake_quality(mission, raw_text)
    if intake_quality["blocked"]:
        return {
            "stored": False,
            "status": "mission_intake_too_vague",
            "reason": intake_quality["reason"],
        }, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"stored": False, "configured": False, "status": "not_configured"}, 503

    params = _mission_params(mission, source_context)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                duplicate = _find_open_duplicate_mission(cursor, params)
                if duplicate:
                    _insert_event(cursor, duplicate["mission_id"], "created", "Duplicate mission intake suppressed.", {
                        "source": params["source"],
                        "duplicate_title": params["title"],
                    })
                    return {
                        "stored": False,
                        "configured": True,
                        "status": "duplicate_open_mission",
                        "mission_id": duplicate["mission_id"],
                        "existing_status": duplicate["status"],
                        "title": duplicate["title"],
                    }, 200
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


def list_missions(status="", limit=10, database_url=None, connect_factory=None, compact=False):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "missions": []}, 503

    parsed_limit = _bounded_limit(limit)
    clean_status = _clean_text(status, 40)
    queue_filter = _mission_queue_filter(clean_status)
    params = {"status": clean_status, "limit": parsed_limit}
    where_clause = ""
    if queue_filter == "owner_queue":
        params["owner_queue_statuses"] = list(OWNER_QUEUE_STATUSES)
        where_clause = """
                    where status = any(%(owner_queue_statuses)s)
                      and coalesce(nullif(metadata_json->'intake_quality'->>'queue_class', ''), 'owner_work') = 'owner_work'
                    """
    elif clean_status:
        where_clause = "where status = %(status)s"
    order_clause = _mission_order_clause(clean_status)
    metadata_select = _mission_metadata_select(compact)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select mission_id, status, source, telegram_user_id, telegram_chat_id,
                           raw_text, title, urgency, mission_type, approval_level,
                           selected_next_step, owner_decision, codex_chat_write_status,
                           {metadata_select}, created_at, updated_at
                    from public.charlie_missions
                    {where_clause}
                    {order_clause}
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


def list_owner_work_missions(status, limit=10, database_url=None, connect_factory=None):
    clean_status = _clean_text(status, 40)
    if clean_status not in OWNER_QUEUE_STATUSES:
        return {
            "success": False,
            "configured": True,
            "status": "invalid_owner_queue_status",
            "allowed_statuses": list(OWNER_QUEUE_STATUSES),
            "missions": [],
        }, 400

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "missions": []}, 503

    parsed_limit = _bounded_limit(limit)
    params = {"status": clean_status, "limit": parsed_limit}
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
                    where status = %(status)s
                      and coalesce(nullif(metadata_json->'intake_quality'->>'queue_class', ''), 'owner_work') = 'owner_work'
                    {_mission_order_clause(clean_status)}
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


def update_mission_queue_priority(
    mission_id,
    priority,
    notes="Mission queue priority updated.",
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    clean_priority = _clean_queue_priority(priority)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if clean_priority is None:
        return {
            "success": False,
            "status": "invalid_queue_priority",
            "allowed_range": [1, QUEUE_PRIORITY_MAX],
        }, 400

    loaded, load_status = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if load_status >= 400:
        return loaded, load_status
    mission = loaded.get("mission") or {}
    if mission.get("status") in {"done", "merged", "deployed", "rejected"}:
        return {
            "success": False,
            "status": "mission_queue_priority_not_allowed",
            "mission_status": mission.get("status", ""),
        }, 409

    metadata = dict(mission.get("metadata") or {})
    queue = metadata.get("queue") if isinstance(metadata.get("queue"), dict) else {}
    queue = dict(queue)
    queue.update({
        "priority": clean_priority,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    metadata_update = {"queue": queue}

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update public.charlie_missions
                    set metadata_json = coalesce(metadata_json, '{}'::jsonb) || %(metadata_json)s::jsonb,
                        updated_at = now()
                    where mission_id = %(mission_id)s
                    returning mission_id
                    """,
                    {
                        "mission_id": mission_id,
                        "metadata_json": json.dumps(metadata_update),
                    },
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "configured": True, "status": "not_found", "mission_id": mission_id}, 404
                _insert_event(cursor, mission_id, "queue_updated", notes, {
                    "priority": clean_priority,
                    "source": "owner_api",
                })
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_queue_priority_update_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "queue_priority": clean_priority,
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
    expected_status="",
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
    expected_status = _clean_text(expected_status, 40)
    if expected_status and expected_status not in MISSION_STATUSES:
        return {"success": False, "status": "invalid_expected_status", "allowed_statuses": sorted(MISSION_STATUSES)}, 400
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
    expected_clause = "and status = %(expected_status)s" if expected_status else ""
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.charlie_missions
                    set {set_sql}
                    where mission_id = %(mission_id)s
                    {expected_clause}
                    returning mission_id
                    """,
                    {
                        "mission_id": mission_id,
                        "status": status,
                        "owner_decision": _clean_text(owner_decision, 1000),
                        "approval_level": approval_level,
                        "expected_status": expected_status,
                    },
                )
                rows = cursor.fetchall()
                if not rows:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "status_claim_lost" if expected_status else "not_found",
                        "mission_id": mission_id,
                        "expected_status": expected_status,
                        "attempted_status": status,
                    }, 409 if expected_status else 404
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


def agent_sequence_for_mission(mission_type="", raw_text=""):
    plan = build_core_plan({"mission_type": mission_type, "raw_text": raw_text or mission_type})
    sequence = plan.get("workflow_template", {}).get("agent_order") or []
    runner_sequence = []
    for agent in sequence:
        if agent in AGENT_DEFINITIONS and agent not in runner_sequence:
            runner_sequence.append(agent)
    return runner_sequence or list(CORE_AGENT_SEQUENCE_V2)


def all_agent_names():
    return list(AGENT_DEFINITIONS.keys())


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

    normalized_writes = _write_normalized_vault_records(
        mission_id,
        vault_metadata,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "mission_status": status,
        "vault_keys": sorted(vault_metadata.keys()),
        "normalized_vault_writes": normalized_writes,
    }, 200


def update_new_mission_intake(
    mission_id,
    updates,
    comment="",
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    updates = updates if isinstance(updates, dict) else {}
    comment = _clean_text(comment, 2000)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400

    loaded, load_status = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if load_status >= 400:
        return loaded, load_status
    mission = loaded.get("mission") or {}
    if mission.get("status") != "new":
        return {
            "success": False,
            "status": "mission_edit_not_allowed",
            "mission_status": mission.get("status", ""),
            "allowed_status": "new",
        }, 409

    scalar_fields = {
        "raw_text": ("raw_text", 3000),
        "concept": ("raw_text", 3000),
        "title": ("title", 160),
        "urgency": ("urgency", 20),
        "mission_type": ("mission_type", 60),
        "approval_level": ("approval_level", 40),
    }
    update_values = {}
    changed_fields = []
    previous_values = {}
    for payload_key, (column, max_len) in scalar_fields.items():
        if payload_key not in updates:
            continue
        value = _clean_text(updates.get(payload_key), max_len)
        if column == "approval_level":
            value = normalize_approval_level(value)
            if value and value not in APPROVAL_LEVELS:
                return {"success": False, "status": "invalid_approval_level", "allowed_approval_levels": sorted(APPROVAL_LEVELS)}, 400
        if value and value != _clean_text(mission.get(column, ""), max_len):
            update_values[column] = value
            if column not in changed_fields:
                changed_fields.append(column)
                previous_values[column] = _clean_text(mission.get(column, ""), max_len)

    metadata = dict(mission.get("metadata") or {})
    vault = dict(mission.get("vault") or {})
    vault_field_specs = {
        "desired_outcome": ("desired_outcome", 1200, "text"),
        "scope_summary": ("scope_summary", 1200, "text"),
        "acceptance_criteria": ("acceptance_criteria", 300, "list"),
        "test_plan": ("test_plan", 300, "list"),
        "pressure_test_plan": ("pressure_test_plan", 300, "list"),
        "forbidden_actions": ("forbidden_actions", 300, "list"),
        "owner_decisions_needed": ("owner_decisions_needed", 300, "list"),
        "rollback_plan": ("rollback_plan", 800, "text"),
        "confidence_target": ("confidence_target", 80, "text"),
    }
    for payload_key, (vault_key, max_len, value_type) in vault_field_specs.items():
        if payload_key not in updates:
            continue
        value = _clean_list(updates.get(payload_key), max_len=max_len) if value_type == "list" else _clean_text(updates.get(payload_key), max_len)
        current = vault.get(vault_key, [] if value_type == "list" else "")
        if value != current:
            vault[vault_key] = value
            changed_fields.append(f"mission_vault.{vault_key}")
            previous_values[f"mission_vault.{vault_key}"] = current

    if "media_references" in updates and isinstance(updates.get("media_references"), list):
        media = [_clean_media_reference(item) for item in updates.get("media_references") if _clean_media_reference(item)]
        if media != mission.get("media_references", []):
            metadata["media_references"] = media
            changed_fields.append("media_references")
            previous_values["media_references"] = mission.get("media_references", [])

    if update_values.get("raw_text"):
        vault["problem_statement"] = update_values["raw_text"]
    if comment:
        comments = vault.get("owner_intake_comments") if isinstance(vault.get("owner_intake_comments"), list) else []
        comments = list(comments) + [{
            "comment": comment,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }]
        vault["owner_intake_comments"] = comments[-20:]
        changed_fields.append("mission_vault.owner_intake_comments")

    if not changed_fields:
        return {
            "success": False,
            "status": "mission_update_empty",
            "mission_id": mission_id,
        }, 400

    edit_history = metadata.get("intake_edit_history") if isinstance(metadata.get("intake_edit_history"), list) else []
    edit_record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "changed_fields": changed_fields,
        "comment": comment,
        "previous_values": previous_values,
    }
    metadata["intake_edit_history"] = (list(edit_history) + [edit_record])[-20:]
    metadata["mission_vault"] = vault

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    set_lines = [f"{column} = %({column})s" for column in sorted(update_values)]
    set_lines.extend([
        "metadata_json = %(metadata_json)s::jsonb",
        "updated_at = now()",
    ])
    params = {
        "mission_id": mission_id,
        "metadata_json": json.dumps(metadata),
        **update_values,
    }
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.charlie_missions
                    set {", ".join(set_lines)}
                    where mission_id = %(mission_id)s
                      and status = 'new'
                    returning mission_id
                    """,
                    params,
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "configured": True, "status": "not_found_or_not_new", "mission_id": mission_id}, 404
                _insert_event(cursor, mission_id, "mission_updated", "New-stage mission intake updated.", {
                    "changed_fields": changed_fields,
                    "comment": comment,
                    "source": "owner_api",
                })
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_update_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "mission_status": "new",
        "changed_fields": changed_fields,
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
    if agent not in all_agent_names():
        return {"success": False, "status": "invalid_agent", "allowed_agents": all_agent_names()}, 400
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
    workflow = metadata.get("agent_workflow") if isinstance(metadata.get("agent_workflow"), list) else _default_agent_workflow(mission.get("mission_type", ""))
    updated_workflow = _update_workflow_items(workflow, agent, step_status, findings, next_agent)
    vault = dict(metadata.get("mission_vault") or {})
    if step_status == "complete":
        vault["mission_stage"] = AGENT_STAGE_MAP.get(agent, vault.get("mission_stage", "intake"))
    elif step_status == "blocked":
        vault["mission_stage"] = f"blocked_at_{agent}" if agent else "blocked"
    if findings:
        handoff_notes = vault.get("handoff_notes") if isinstance(vault.get("handoff_notes"), list) else []
        handoff_notes = list(handoff_notes)
        handoff_notes.append({"agent": agent, "status": step_status, "findings": findings})
        vault["handoff_notes"] = handoff_notes[-12:]
        handoff_reports = vault.get("handoff_reports") if isinstance(vault.get("handoff_reports"), list) else []
        handoff_reports = list(handoff_reports)
        handoff_reports.append(build_handoff_report(
            mission,
            agent,
            {
                "summary": findings,
                "status": "pass" if step_status == "complete" else step_status,
                "actions_taken": [f"Workflow step marked {step_status}."],
                "inputs_used": ["mission_vault", "agent_workflow"],
                "vault_sources_used": ["mission_vault"],
                "recommended_next_agent": next_agent,
            },
            stage=AGENT_STAGE_MAP.get(agent, agent),
        ))
        vault["handoff_reports"] = handoff_reports[-20:]
    context_pack = metadata.get("mission_context_pack") if isinstance(metadata.get("mission_context_pack"), dict) else _default_context_pack(mission.get("mission_type", ""))

    status = ""
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    if (
        agent == "reviewer"
        and step_status == "complete"
        and str(review_packet.get("review_status") or "").strip() == "ready_for_owner_review"
    ):
        status = "pr_ready"
    elif step_status == "blocked":
        status = "blocked"

    return update_mission_vault(
        mission_id,
        {
            "mission_vault": vault,
            "agent_workflow": updated_workflow,
            "mission_context_pack": context_pack,
            "charlie_core": {
                **(metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}),
                "readiness": evaluate_core_readiness({
                    "metadata": {
                        **metadata,
                        "mission_vault": vault,
                        "agent_workflow": updated_workflow,
                    },
                    "agent_workflow": updated_workflow,
                    "vault": vault,
                }),
            },
        },
        status=status,
        owner_decision=f"{agent} step marked {step_status}." if status else "",
        notes=f"Mission workflow updated: {agent} -> {step_status}.",
        database_url=database_url,
        connect_factory=connect_factory,
    )


def get_mission_review_packet(mission_id, database_url=None, connect_factory=None):
    loaded, status_code = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return loaded, status_code
    mission = loaded.get("mission") or {}
    return {
        "success": True,
        "configured": loaded.get("configured", True),
        "status": "ok",
        "mission_id": mission.get("mission_id"),
        "review_packet": build_mission_review_packet(mission),
    }, 200


def record_mission_review_decision(
    mission_id,
    decision,
    comments="",
    target_stage="",
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    decision = _clean_text(decision, 40)
    comments = _clean_text(comments, 2000)
    target_stage = _clean_text(target_stage, 80) or "builder"
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if decision not in REVIEW_DECISIONS:
        return {"success": False, "status": "invalid_review_decision", "allowed_decisions": sorted(REVIEW_DECISIONS)}, 400

    loaded, load_status = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if load_status >= 400:
        return loaded, load_status
    mission = loaded.get("mission") or {}
    if decision == "send_back":
        target_stage = _normalize_review_send_back_stage(target_stage, mission.get("agent_workflow") or [])
    metadata = dict(mission.get("metadata") or {})
    decisions = metadata.get("owner_review_decisions") if isinstance(metadata.get("owner_review_decisions"), list) else []
    decision_record = {
        "decision": decision,
        "comments": comments,
        "target_stage": target_stage if decision == "send_back" else "",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    decisions = list(decisions) + [decision_record]
    review_packet = dict(metadata.get("review_packet") or {})
    review_packet.update({
        "last_owner_review_decision": decision_record,
        "review_status": "final_approved" if decision == "approve_final_release" else decision,
    })
    if decision in {"approve_final_release", "mark_done"}:
        visual_review = review_packet.get("visual_review") if isinstance(review_packet.get("visual_review"), dict) else {}
        cleanup = visual_review.get("cleanup") if isinstance(visual_review.get("cleanup"), dict) else {}
        if visual_review:
            cleanup.update({
                "required": bool(cleanup.get("required", visual_review.get("ui_related", False))),
                "status": "cleanup_requested",
                "requested_at": decision_record["recorded_at"],
                "requested_by_decision": decision,
            })
            visual_review["cleanup"] = cleanup
            review_packet["visual_review"] = visual_review
    if decision == "send_back":
        review_packet["return_to_stage"] = target_stage
        review_packet["owner_comments_pending"] = comments

    target_status = REVIEW_DECISION_STATUS[decision]
    approval_level = "LEVEL 4" if decision == "approve_final_release" else mission.get("approval_level", "")
    owner_decision = _review_owner_decision_text(decision, comments, target_stage)
    metadata_update = {
        "review_packet": review_packet,
        "owner_review_decisions": decisions[-20:],
    }
    if decision == "send_back":
        workflow = _return_workflow_to_stage(mission.get("agent_workflow") or [], target_stage, comments)
        vault = dict(mission.get("vault") or {})
        vault["mission_stage"] = f"returned_to_{target_stage}"
        if comments:
            review_comments = vault.get("owner_review_comments") if isinstance(vault.get("owner_review_comments"), list) else []
            review_comments = list(review_comments) + [{"stage": target_stage, "comments": comments}]
            vault["owner_review_comments"] = review_comments[-12:]
        metadata_update["agent_workflow"] = workflow
        metadata_update["mission_vault"] = vault

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                set_lines = [
                    "status = %(status)s",
                    "owner_decision = %(owner_decision)s",
                    "metadata_json = coalesce(metadata_json, '{}'::jsonb) || %(metadata_json)s::jsonb",
                    "updated_at = now()",
                ]
                params = {
                    "mission_id": mission_id,
                    "status": target_status,
                    "owner_decision": owner_decision,
                    "metadata_json": json.dumps(metadata_update),
                }
                if approval_level:
                    set_lines.insert(1, "approval_level = %(approval_level)s")
                    params["approval_level"] = normalize_approval_level(approval_level)
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
                _insert_event(cursor, mission_id, "review_note", owner_decision, {
                    "decision": decision,
                    "comments": comments,
                    "target_stage": target_stage if decision == "send_back" else "",
                    "mission_status": target_status,
                })
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_review_update_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    normalized_decision, _ = vault_store.write_owner_decision(
        mission_id,
        decision,
        approval_level=normalize_approval_level(approval_level),
        comments=comments,
        metadata={"target_stage": target_stage if decision == "send_back" else ""},
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "mission_status": target_status,
        "review_decision": decision,
        "approval_level": normalize_approval_level(approval_level),
        "normalized_owner_decision": normalized_decision,
    }, 200


def build_mission_review_packet(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    review_board = packet.get("review_board") if isinstance(packet.get("review_board"), dict) else core.get("review_board")
    if not isinstance(review_board, dict):
        review_board = build_review_board_packet(mission, packet.get("agent_artifacts") if isinstance(packet.get("agent_artifacts"), dict) else {})
    income_stream_readiness = metadata.get("income_stream_readiness") if isinstance(metadata.get("income_stream_readiness"), dict) else build_income_stream_readiness(mission)
    core_readiness = evaluate_core_readiness(mission)
    return {
        "mission": {
            "mission_id": mission.get("mission_id", ""),
            "title": mission.get("title", ""),
            "status": mission.get("status", ""),
            "urgency": mission.get("urgency", ""),
            "mission_type": mission.get("mission_type", ""),
            "approval_level": mission.get("approval_level", ""),
            "updated_at": mission.get("updated_at", ""),
        },
        "summary": _clean_text(packet.get("summary") or vault.get("desired_outcome") or mission.get("raw_text", ""), 1600),
        "findings": _packet_list(packet, "findings", _workflow_findings(workflow)),
        "errors": _packet_list(packet, "errors", []),
        "bugs": _packet_list(packet, "bugs", []),
        "changed_files": _packet_list(packet, "changed_files", []),
        "test_evidence": _packet_list(packet, "test_evidence", vault.get("test_plan") if isinstance(vault.get("test_plan"), list) else []),
        "local_preview": packet.get("local_preview") if isinstance(packet.get("local_preview"), dict) else {},
        "visual_review": packet.get("visual_review") if isinstance(packet.get("visual_review"), dict) else _default_visual_review(packet),
        "links": packet.get("links") if isinstance(packet.get("links"), dict) else {},
        "release_notes": _packet_list(packet, "release_notes", []),
        "agent_execution": packet.get("agent_execution") if isinstance(packet.get("agent_execution"), dict) else metadata.get("agent_execution", {}),
        "agent_artifacts": packet.get("agent_artifacts") if isinstance(packet.get("agent_artifacts"), dict) else {},
        "quality_gates": packet.get("quality_gates") if isinstance(packet.get("quality_gates"), list) else [],
        "qa_evidence": _packet_list(packet, "qa_evidence", []),
        "handoff_reports": packet.get("handoff_reports") if isinstance(packet.get("handoff_reports"), dict) else vault.get("handoff_reports", []),
        "backflow_events": packet.get("backflow_events") if isinstance(packet.get("backflow_events"), list) else [],
        "charlie_core": core,
        "core_readiness": core_readiness,
        "review_board": review_board,
        "income_stream_readiness": income_stream_readiness,
        "vault_schema": core.get("vault_schema", {}),
        "workflow_template": core.get("workflow_template", {}),
        "blocked_agent": packet.get("blocked_agent", ""),
        "blocked_reason": packet.get("blocked_reason", ""),
        "blocked_summary": packet.get("blocked_summary") if isinstance(packet.get("blocked_summary"), dict) else {},
        "unresolved_blockers": packet.get("unresolved_blockers") if isinstance(packet.get("unresolved_blockers"), list) else [],
        "recommended_next_action": packet.get("recommended_next_action", ""),
        "owner_review_decisions": metadata.get("owner_review_decisions") if isinstance(metadata.get("owner_review_decisions"), list) else [],
        "agent_workflow": workflow,
        "mission_vault": vault,
        "can_approve_final_release": mission.get("status") == "pr_ready",
        "can_send_back": mission.get("status") in {"pr_ready", "blocked"},
        "allowed_decisions": sorted(REVIEW_DECISIONS),
        "execution_boundary": "Dashboard review decisions update mission state only; local Codex/release bridge must execute build, merge, and deploy steps.",
    }


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


def _write_normalized_vault_records(mission_id, vault_metadata, database_url=None, connect_factory=None):
    vault_metadata = vault_metadata if isinstance(vault_metadata, dict) else {}
    writes = []
    mission_vault = vault_metadata.get("mission_vault") if isinstance(vault_metadata.get("mission_vault"), dict) else {}
    review_packet = vault_metadata.get("review_packet") if isinstance(vault_metadata.get("review_packet"), dict) else {}
    charlie_core = vault_metadata.get("charlie_core") if isinstance(vault_metadata.get("charlie_core"), dict) else {}
    project_truth = mission_vault.get("project_truth") if isinstance(mission_vault.get("project_truth"), dict) else charlie_core.get("project_truth", {})

    if isinstance(project_truth, dict) and project_truth:
        result, _ = vault_store.write_project({
            "project_id": project_truth.get("project_key", "charlie_core"),
            "project_key": project_truth.get("project_key", "charlie_core"),
            "name": project_truth.get("project_key", "CHARLIE CORE"),
            "purpose": project_truth.get("purpose", ""),
            "workflow_template": project_truth.get("workflow_template", "software_build"),
            "metadata": project_truth,
        }, database_url=database_url, connect_factory=connect_factory)
        writes.append(_normalized_write_result("project", result))

    handoff_reports = mission_vault.get("handoff_reports") if isinstance(mission_vault.get("handoff_reports"), list) else []
    for report in handoff_reports[-20:]:
        if isinstance(report, dict):
            result, _ = vault_store.write_handoff_report(report, database_url=database_url, connect_factory=connect_factory)
            writes.append(_normalized_write_result("handoff", result))

    agent_execution = vault_metadata.get("agent_execution") if isinstance(vault_metadata.get("agent_execution"), dict) else {}
    execution_id = agent_execution.get("execution_id", "")
    for stage_run in agent_execution.get("stages", []) if isinstance(agent_execution.get("stages"), list) else []:
        if isinstance(stage_run, dict):
            run_payload = dict(stage_run)
            if execution_id:
                run_payload["execution_id"] = execution_id
            result, _ = vault_store.write_agent_run(
                mission_id,
                stage_run.get("agent", ""),
                run_payload,
                stage=stage_run.get("stage") or stage_run.get("agent", ""),
                database_url=database_url,
                connect_factory=connect_factory,
            )
            writes.append(_normalized_write_result("agent_run", result, agent=stage_run.get("agent", "")))

    artifacts = review_packet.get("agent_artifacts") if isinstance(review_packet.get("agent_artifacts"), dict) else {}
    for agent, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        result, _ = vault_store.write_artifact(
            mission_id,
            artifact.get("artifact_type") or f"{agent}_artifact",
            artifact,
            title=artifact.get("title") or f"{agent} artifact",
            summary=artifact.get("summary", ""),
            project_id=project_truth.get("project_key", "") if isinstance(project_truth, dict) else "",
            agent=agent,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        writes.append(_normalized_write_result("artifact", result, agent=agent))
        handoff = artifact.get("handoff_report") if isinstance(artifact.get("handoff_report"), dict) else {}
        canonical = handoff.get("canonical") if isinstance(handoff.get("canonical"), dict) else handoff
        if canonical:
            result, _ = vault_store.write_handoff_report(canonical, database_url=database_url, connect_factory=connect_factory)
            writes.append(_normalized_write_result("handoff", result, agent=agent))

    for gate in review_packet.get("quality_gates", []) if isinstance(review_packet.get("quality_gates"), list) else []:
        if isinstance(gate, dict):
            result, _ = vault_store.write_quality_gate(
                mission_id,
                gate.get("agent") or gate.get("gate_name") or "quality_gate",
                "passed" if gate.get("passed") else "failed",
                reason=gate.get("reason", ""),
                evidence=gate,
                stage=gate.get("agent", ""),
                database_url=database_url,
                connect_factory=connect_factory,
            )
            writes.append(_normalized_write_result("quality_gate", result))

    deployment = vault_metadata.get("deployment_record") if isinstance(vault_metadata.get("deployment_record"), dict) else {}
    if deployment:
        result, _ = vault_store.write_deployment_record(deployment, database_url=database_url, connect_factory=connect_factory)
        writes.append(_normalized_write_result("deployment", result))

    intelligence = vault_metadata.get("intelligence_loop") if isinstance(vault_metadata.get("intelligence_loop"), dict) else {}
    for lesson in intelligence.get("lesson_records", []) if isinstance(intelligence.get("lesson_records"), list) else []:
        if isinstance(lesson, dict):
            result, _ = vault_store.write_lesson(lesson, database_url=database_url, connect_factory=connect_factory)
            writes.append(_normalized_write_result("lesson", result))

    income = vault_metadata.get("income_stream_readiness") if isinstance(vault_metadata.get("income_stream_readiness"), dict) else {}
    if income:
        result, _ = vault_store.write_income_stream_review(
            mission_id,
            income,
            business_model=mission_vault.get("business_model") if isinstance(mission_vault.get("business_model"), dict) else {},
            risk_register=mission_vault.get("risk_register") if isinstance(mission_vault.get("risk_register"), list) else [],
            owner_gate_status="ready" if income.get("ready") else "pending",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        writes.append(_normalized_write_result("income_stream_review", result))

    return writes


def _normalized_write_result(target, result, agent=""):
    item = {
        "target": target,
        "status": result.get("status"),
        "success": bool(result.get("success")),
    }
    if agent:
        item["agent"] = agent
    if result.get("error_type"):
        item["error_type"] = result.get("error_type")
    if result.get("error_message"):
        item["error_message"] = result.get("error_message")
    return item


def _mission_params(mission, source_context):
    raw_text = _clean_text(mission.get("raw_text", ""), 3000)
    now = datetime.now(timezone.utc).isoformat()
    mission_id = _clean_text(mission.get("mission_id", ""), 90) or _mission_id(raw_text, source_context, now)
    metadata = mission.get("metadata", {}) if isinstance(mission.get("metadata"), dict) else {}
    metadata = _mission_metadata(raw_text, mission, source_context, metadata)
    metadata.setdefault("intake_quality", _mission_intake_quality(mission, raw_text))
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
    queue = metadata.get("queue") if isinstance(metadata.get("queue"), dict) else {}
    queue_priority = _clean_queue_priority(queue.get("priority")) if queue else None
    raw_text = row[5]
    title = row[6]
    return {
        "mission_id": row[0],
        "status": row[1],
        "source": row[2],
        "telegram_user_id": row[3],
        "telegram_chat_id": row[4],
        "raw_text": raw_text,
        "title": title,
        "urgency": row[7],
        "mission_type": row[8],
        "approval_level": row[9],
        "selected_next_step": row[10],
        "owner_decision": row[11],
        "codex_chat_write_status": row[12],
        "metadata": metadata,
        "queue": {
            "priority": queue_priority if queue_priority is not None else QUEUE_PRIORITY_DEFAULT,
            "updated_at": _clean_text(queue.get("updated_at", ""), 80) if queue else "",
        },
        "queue_priority": queue_priority if queue_priority is not None else QUEUE_PRIORITY_DEFAULT,
        "queue_class": _mission_queue_class(title, raw_text, metadata),
        "vault": metadata.get("mission_vault", {}) if isinstance(metadata.get("mission_vault"), dict) else {},
        "agent_workflow": metadata.get("agent_workflow", []) if isinstance(metadata.get("agent_workflow"), list) else [],
        "media_references": metadata.get("media_references", []) if isinstance(metadata.get("media_references"), list) else [],
        "mission_context_pack": metadata.get("mission_context_pack", {}) if isinstance(metadata.get("mission_context_pack"), dict) else {},
        "created_at": _iso(row[14]),
        "updated_at": _iso(row[15]),
    }


def _find_open_duplicate_mission(cursor, params):
    cursor.execute(
        """
        select mission_id, status, title, raw_text
        from public.charlie_missions
        where status = any(%(statuses)s)
        order by updated_at desc
        limit 250
        """,
        {"statuses": sorted(OPEN_DUPLICATE_STATUSES)},
    )
    new_title = _normalize_mission_text(params.get("title", ""))
    new_raw = _normalize_mission_text(params.get("raw_text", ""))
    for row in cursor.fetchall():
        existing_title = _normalize_mission_text(row[2])
        existing_raw = _normalize_mission_text(row[3])
        if new_raw and existing_raw == new_raw:
            return {"mission_id": row[0], "status": row[1], "title": row[2]}
        if new_title and existing_title == new_title and len(new_title) >= 18:
            return {"mission_id": row[0], "status": row[1], "title": row[2]}
    return None


def _mission_intake_quality(mission, raw_text):
    title = _normalize_mission_text(mission.get("title") or raw_text)
    raw = _normalize_mission_text(raw_text)
    if title in PLACEHOLDER_MISSION_TITLES and raw in PLACEHOLDER_MISSION_TITLES:
        return {
            "blocked": True,
            "reason": "placeholder_charlie_relay_title_without_specific_goal",
            "queue_class": "system_noise",
        }
    if len(raw) < 12:
        return {
            "blocked": True,
            "reason": "mission_text_too_short",
            "queue_class": "low_signal",
        }
    return {
        "blocked": False,
        "reason": "",
        "queue_class": _mission_queue_class(mission.get("title") or raw_text, raw_text, mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}),
    }


def _mission_queue_class(title, raw_text, metadata=None):
    metadata = metadata if isinstance(metadata, dict) else {}
    intake_quality = metadata.get("intake_quality") if isinstance(metadata.get("intake_quality"), dict) else {}
    if intake_quality.get("queue_class"):
        return str(intake_quality.get("queue_class"))
    normalized_title = _normalize_mission_text(title)
    normalized_raw = _normalize_mission_text(raw_text)
    if normalized_title in PLACEHOLDER_MISSION_TITLES and normalized_raw in PLACEHOLDER_MISSION_TITLES:
        return "system_noise"
    combined_text = f"{normalized_title} {normalized_raw}".strip()
    if any(marker in combined_text for marker in SYSTEM_TEST_MISSION_MARKERS):
        return "system_test"
    return "owner_work"


def _normalize_mission_text(value):
    return " ".join(str(value or "").strip().lower().split())


def _mission_metadata(raw_text, mission, source_context, metadata):
    metadata = dict(metadata or {})
    metadata.setdefault("mission_vault", _default_mission_vault(raw_text, mission))
    metadata.setdefault("agent_workflow", _default_agent_workflow(mission.get("mission_type", ""), raw_text))
    metadata.setdefault("mission_context_pack", _default_context_pack(mission.get("mission_type", ""), raw_text))
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
    metadata = attach_core_plan_to_metadata(
        {
            **mission,
            "raw_text": raw_text,
            "mission_type": mission.get("mission_type", "feature build"),
            "title": mission.get("title", raw_text),
        },
        metadata,
    )
    metadata.setdefault("mission_governance", ensure_acceptance_matrix({
        **mission,
        "raw_text": raw_text,
        "metadata": metadata,
        "vault": metadata.get("mission_vault", {}),
    }))
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


def _default_agent_workflow(mission_type="", raw_text=""):
    sequence = agent_sequence_for_mission(mission_type, raw_text)
    workflow = []
    for index, agent in enumerate(sequence):
        definition = AGENT_DEFINITIONS[agent]
        next_agent = sequence[index + 1] if index + 1 < len(sequence) else definition.get("handoff_to", "owner")
        workflow.append({
            "agent": agent,
            "status": "pending",
            "purpose": definition.get("purpose", ""),
            "handoff_to": next_agent,
            "required_output": HANDOFF_VERSION,
            "instruction_pack": agent_instruction_pack(agent),
            "findings": "",
        })
    if workflow:
        workflow[0]["status"] = "active"
    return workflow


def _default_context_pack(mission_type="", raw_text=""):
    sequence = agent_sequence_for_mission(mission_type, raw_text)
    return {
        "version": "charlie_context_pack_v1",
        "active_truth_docs": list(MISSION_CONTEXT_DOCS),
        "shared_data_rules": [
            "Vault Brain docs under docs/09-vault-brain are the canonical doctrine for agents, workflows, business rules, data rules, standards, and playbooks.",
            "Every CHARLIE CORE mission must cite the Vault Brain docs used before owner review.",
            "Brain Guard must block review-ready status when Vault-sensitive work lacks Vault update evidence or an explicit no-update reason.",
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
        "agent_order": sequence,
        "parallel_work": "disabled_until_phase_6_parallel_controls",
    }


def _mission_order_clause(status):
    if _mission_queue_filter(status) == "owner_queue":
        return """
                    order by
                        case status
                            when 'in_progress' then 0
                            when 'release_in_progress' then 1
                            when 'pr_ready' then 2
                            when 'blocked' then 3
                            when 'release_approved' then 4
                            when 'approved' then 5
                            when 'new' then 6
                            else 7
                        end asc,
                        case
                            when (metadata_json->'queue'->>'priority') ~ '^[0-9]+$'
                            then (metadata_json->'queue'->>'priority')::int
                            else %(default_priority)s
                        end asc,
                        case urgency
                            when 'P0' then 0
                            when 'P1' then 1
                            when 'P2' then 2
                            when 'P3' then 3
                            when 'P4' then 4
                            else 5
                        end asc,
                        created_at asc,
                        mission_id asc
                    """.replace("%(default_priority)s", str(QUEUE_PRIORITY_DEFAULT))
    if status in QUEUE_ORDERED_STATUSES:
        return """
                    order by
                        case
                            when (metadata_json->'queue'->>'priority') ~ '^[0-9]+$'
                            then (metadata_json->'queue'->>'priority')::int
                            else %(default_priority)s
                        end asc,
                        case urgency
                            when 'P0' then 0
                            when 'P1' then 1
                            when 'P2' then 2
                            when 'P3' then 3
                            when 'P4' then 4
                            else 5
                        end asc,
                        created_at asc,
                        mission_id asc
                    """.replace("%(default_priority)s", str(QUEUE_PRIORITY_DEFAULT))
    return "order by created_at desc"


def _mission_metadata_select(compact=False):
    if not compact:
        return "metadata_json"
    workflow_summary = """
        coalesce((
            select jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                'agent', item->>'agent',
                'status', item->>'status',
                'findings', item->>'findings',
                'updated_at', item->>'updated_at'
            )))
            from jsonb_array_elements(coalesce(metadata_json->'agent_workflow', '[]'::jsonb)) as item
        ), '[]'::jsonb)
    """
    return f"""
        jsonb_strip_nulls(jsonb_build_object(
            'review_packet', jsonb_strip_nulls(jsonb_build_object(
                'summary', metadata_json->'review_packet'->'summary',
                'review_status', metadata_json->'review_packet'->'review_status',
                'blocked_agent', metadata_json->'review_packet'->'blocked_agent',
                'blocked_reason', metadata_json->'review_packet'->'blocked_reason',
                'local_preview', metadata_json->'review_packet'->'local_preview',
                'links', metadata_json->'review_packet'->'links',
                'test_evidence', metadata_json->'review_packet'->'test_evidence',
                'visual_review', metadata_json->'review_packet'->'visual_review',
                'recommended_next_action', metadata_json->'review_packet'->'recommended_next_action',
                'backflow_events', metadata_json->'review_packet'->'backflow_events',
                'unresolved_blockers', metadata_json->'review_packet'->'unresolved_blockers'
            )),
            'mission_vault', jsonb_strip_nulls(jsonb_build_object(
                'mission_stage', metadata_json->'mission_vault'->'mission_stage',
                'confidence_target', metadata_json->'mission_vault'->'confidence_target',
                'problem_statement', metadata_json->'mission_vault'->'problem_statement',
                'desired_outcome', metadata_json->'mission_vault'->'desired_outcome',
                'current_agent', metadata_json->'mission_vault'->'current_agent',
                'review_quality', metadata_json->'mission_vault'->'review_quality',
                'vault_readiness', metadata_json->'mission_vault'->'vault_readiness',
                'source_truth', metadata_json->'mission_vault'->'source_truth'
            )),
            'agent_workflow', {workflow_summary},
            'mission_context_pack', jsonb_strip_nulls(jsonb_build_object(
                'version', metadata_json->'mission_context_pack'->'version'
            )),
            'intake_quality', metadata_json->'intake_quality',
            'queue', metadata_json->'queue',
            'mission_governance', metadata_json->'mission_governance',
            'mission_family', metadata_json->'mission_family',
            'media_references', jsonb_path_query_array(
                coalesce(metadata_json->'media_references', '[]'::jsonb),
                '$[*] ? (@.media_type != "image")'
            )
        ))
    """


def _mission_queue_filter(status):
    return "owner_queue" if _clean_text(status, 40).lower() in OWNER_QUEUE_FILTERS else ""


def _clean_queue_priority(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1 or parsed > QUEUE_PRIORITY_MAX:
        return None
    return parsed


def _default_forbidden_actions():
    return [
        "No production data writes unless explicitly approved.",
        "No migrations unless explicitly approved.",
        "No customer sends, public posts, payments, reservations, or lifecycle writes unless explicitly approved.",
        "No .env, secrets, screenshots, external_sources, static/assets, or planning/Prompts.md unless explicitly approved.",
    ]


def _update_workflow_items(workflow, agent, step_status, findings, next_agent):
    known = {}
    for item in workflow:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("agent"), 80).strip().lower()
        if not name:
            continue
        normalized = dict(item)
        normalized["agent"] = name
        known[name] = normalized
    sequence = _workflow_sequence(workflow)
    agent = _clean_text(agent, 80).strip().lower()
    next_agent = _clean_text(next_agent, 80).strip().lower()
    if agent and agent not in sequence:
        sequence.append(agent)
    if next_agent and next_agent not in sequence:
        sequence.append(next_agent)
    for default in _workflow_defaults_for_sequence(sequence):
        known.setdefault(default["agent"], dict(default))
    if agent:
        agent_defaults = _workflow_defaults_for_sequence([agent])
        known.setdefault(agent, dict(agent_defaults[0]) if agent_defaults else {
            "agent": agent,
            "status": "pending",
            "handoff_to": "",
        })
    if next_agent and next_agent in known:
        known[agent]["handoff_to"] = next_agent
    if not agent:
        return [known[name] for name in sequence]
    if step_status in {"active", "blocked", "complete"}:
        for name in sequence:
            if name != agent and known[name].get("status") == "active":
                known[name]["status"] = "pending"
    known[agent]["status"] = step_status
    if findings:
        known[agent]["findings"] = findings
    if step_status == "complete":
        handoff_to = known[agent].get("handoff_to")
        if handoff_to in known and known[handoff_to].get("status") == "pending":
            known[handoff_to]["status"] = "active"
    return [known[name] for name in sequence]


def _return_workflow_to_stage(workflow, target_stage, comments):
    known = {item.get("agent"): dict(item) for item in workflow if isinstance(item, dict)}
    sequence = _workflow_sequence(workflow)
    target_stage = _clean_text(target_stage, 80).strip().lower()
    if target_stage and target_stage not in sequence:
        sequence.append(target_stage)
    for default in _workflow_defaults_for_sequence(sequence):
        known.setdefault(default["agent"], dict(default))
    target_stage = target_stage if target_stage in known else "builder"
    if target_stage not in known:
        sequence.append(target_stage)
        known[target_stage] = _workflow_defaults_for_sequence([target_stage])[0]
    target_seen = False
    for agent in sequence:
        if agent == target_stage:
            target_seen = True
            known[agent]["status"] = "active"
            if comments:
                known[agent]["findings"] = comments
        elif target_seen:
            known[agent]["status"] = "pending"
    return [known[name] for name in sequence]


def _normalize_review_send_back_stage(target_stage, workflow):
    target_stage = _clean_text(target_stage, 80).strip().lower() or "builder"
    sequence = _workflow_sequence(workflow)
    if target_stage in sequence:
        return target_stage
    if target_stage == "frontend_design_implementer" and "builder" in sequence:
        return "builder"
    if target_stage in AGENT_DEFINITIONS or target_stage in AGENT_STAGE_MAP:
        return target_stage
    return "builder" if "builder" in sequence else sequence[0]


def _workflow_sequence(workflow):
    sequence = [
        _clean_text(item.get("agent"), 80).strip().lower()
        for item in workflow
        if isinstance(item, dict) and _clean_text(item.get("agent"), 80).strip()
    ]
    return sequence or list(CORE_AGENT_SEQUENCE_V2)


def _workflow_defaults_for_sequence(sequence):
    defaults = []
    for index, agent in enumerate(sequence):
        definition = AGENT_DEFINITIONS.get(agent, {})
        next_agent = sequence[index + 1] if index + 1 < len(sequence) else definition.get("handoff_to", "owner")
        defaults.append({
            "agent": agent,
            "status": "pending",
            "purpose": definition.get("purpose", ""),
            "handoff_to": next_agent,
            "required_output": HANDOFF_VERSION,
            "instruction_pack": agent_instruction_pack(agent),
            "findings": "",
        })
    return defaults


def _review_owner_decision_text(decision, comments, target_stage):
    labels = {
        "approve_final_release": "Owner approved final release from CHARLIE review.",
        "send_back": f"Owner sent mission back to {target_stage} from CHARLIE review.",
        "pause": "Owner paused mission from CHARLIE review.",
        "reject": "Owner rejected mission from CHARLIE review.",
        "mark_done": "Owner marked mission done from CHARLIE review.",
    }
    text = labels.get(decision, "Owner recorded CHARLIE review decision.")
    return f"{text} Comments: {comments}" if comments else text


def _workflow_findings(workflow):
    findings = []
    for item in workflow:
        if not isinstance(item, dict):
            continue
        finding = _clean_text(item.get("findings", ""), 600)
        if finding:
            findings.append(f"{item.get('agent', 'agent')}: {finding}")
    return findings


def _default_visual_review(packet):
    packet = packet if isinstance(packet, dict) else {}
    local_preview = packet.get("local_preview") if isinstance(packet.get("local_preview"), dict) else {}
    return {
        "contract": "charlie_visual_review_v1",
        "ui_related": False,
        "status": "not_available",
        "summary": "No visual review packet was captured for this mission.",
        "local_preview": local_preview,
        "media": [],
        "stage_evidence": [],
        "cleanup": {"required": False, "status": "not_required"},
    }


def _packet_list(packet, key, fallback):
    value = packet.get(key) if isinstance(packet, dict) else []
    if isinstance(value, list):
        return [_clean_text(item, 600) for item in value if _clean_text(item, 600)]
    if isinstance(value, str):
        return _clean_list(value, max_items=20, max_len=600)
    if isinstance(fallback, list):
        return [_clean_text(item, 600) for item in fallback if _clean_text(item, 600)]
    return []


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
    raw_reference = str(item.get("reference") or item.get("url") or item.get("path") or "").strip()
    media_type = _clean_text(item.get("media_type", "reference"), 40)
    reference = _clean_media_reference_value(raw_reference, media_type)
    if not reference:
        return {}
    return {
        "label": _clean_text(item.get("label") or reference, 120),
        "reference": reference,
        "media_type": media_type,
    }


def _clean_media_reference_value(reference, media_type):
    if media_type == "image" and reference.startswith("data:image/"):
        compact = "".join(reference.split())
        if len(compact) <= MISSION_MEDIA_DATA_URL_MAX_LEN and MISSION_MEDIA_DATA_URL_PATTERN.match(compact):
            return compact
        return ""
    if reference.startswith("data:"):
        return ""
    return _clean_text(reference, 500)


def _database_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _connect(database_url, connect_factory=None):
    if connect_factory:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=3)


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
