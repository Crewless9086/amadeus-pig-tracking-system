import hashlib
import json
import os
import re
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
MISSION_LANES = {
    "charlie_core": {
        "label": "CHARLIE CORE",
        "description": "Owner command layer, mission runner, governance, and system coordination.",
    },
    "oom_sakkie": {
        "label": "Oom Sakkie",
        "description": "Farm manager and farm operations command surface.",
    },
    "sam": {
        "label": "SAM",
        "description": "Sales agent and meat money-path workflow.",
    },
    "fred": {
        "label": "FRED",
        "description": "AMADEUS Private Transfers customer talking and transport engine.",
    },
    "farm_pig_application": {
        "label": "Farm Pig Application",
        "description": "Pig tracking, litters, weights, breeding, stock, and farm app workflows.",
    },
    "unassigned": {
        "label": "Unassigned / General",
        "description": "Mission lane not selected yet.",
    },
}
CHARLIE_BRAIN_DOCUMENTS = [
    {
        "doc_path": "docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md",
        "title": "CHARLIE Mission Protocol",
        "entity_key": "charlie_core",
        "document_type": "governance",
        "tags": ["mission_control", "approval", "owner_gate", "workflow"],
        "summary": "Mission intake, approval, owner review, and release rules for CHARLIE-controlled work.",
    },
    {
        "doc_path": "docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md",
        "title": "CHARLIE Agent Runner v2",
        "entity_key": "charlie_core",
        "document_type": "runner_sop",
        "tags": ["runner", "agents", "handoff", "quality_gates"],
        "summary": "Agent Runner v2 workflow, stage artifacts, blocked behavior, owner review, and release handling.",
    },
    {
        "doc_path": "docs/00-start-here/CURRENT_STATE.md",
        "title": "Current State",
        "entity_key": "charlie_core",
        "document_type": "state",
        "tags": ["current_truth", "status", "system_state"],
        "summary": "Current project truth and active operational state.",
    },
    {
        "doc_path": "docs/00-start-here/NEXT_STEPS.md",
        "title": "Next Steps",
        "entity_key": "charlie_core",
        "document_type": "planning",
        "tags": ["next_steps", "roadmap", "priorities"],
        "summary": "Current roadmap and prioritized work queue context.",
    },
    {
        "doc_path": "docs/00-start-here/WORKFLOW.md",
        "title": "Workflow",
        "entity_key": "charlie_core",
        "document_type": "workflow",
        "tags": ["workflow", "handoff", "how_we_work"],
        "summary": "How owner notes become scoped work, phases, and controlled execution.",
    },
    {
        "doc_path": "docs/00-start-here/DEPLOYMENT_SOP.md",
        "title": "Deployment SOP",
        "entity_key": "charlie_core",
        "document_type": "sop",
        "tags": ["deployment", "release", "verification"],
        "summary": "Release and deployment safety rules.",
    },
    {
        "doc_path": "docs/00-start-here/OWNER_INBOX_GUIDE.md",
        "title": "Owner Inbox Guide",
        "entity_key": "charlie_core",
        "document_type": "owner_sop",
        "tags": ["owner", "inbox", "intake"],
        "summary": "Owner intake and inbox usage guide.",
    },
]
PROJECT_MEMORY = {
    "charlie_core": {
        "project_key": "charlie_core",
        "entity_key": "charlie_core",
        "name": "CHARLIE CORE",
        "purpose": "Governed AI operating system for Amadeus missions, agents, evidence, owner review, and release control.",
        "active_systems": ["Mission Control", "Agent Runner v2", "Mission Vault", "Telegram Build Relay"],
        "open_priorities": ["runner reliability", "mission vault", "knowledge brain", "owner command center"],
        "known_risks": ["silent stuck runners", "weak evidence", "over-broad automation authority"],
    },
    "oom_sakkie": {
        "project_key": "oom_sakkie",
        "entity_key": "oom_sakkie",
        "name": "Oom Sakkie",
        "purpose": "Farm manager and operations command surface.",
        "active_systems": ["farm operations", "specialist dry-run surface"],
        "open_priorities": ["farm truth", "safe specialist handoffs", "owner-visible command state"],
        "known_risks": ["farm lifecycle writes without owner approval", "stale operational data"],
    },
    "sam": {
        "project_key": "sam",
        "entity_key": "sam",
        "name": "SAM",
        "purpose": "Sales agent and meat money-path workflow.",
        "active_systems": ["meat leads", "quotes", "sales conversation learning"],
        "open_priorities": ["income path clarity", "customer-safe messaging", "evidence-backed sales workflow"],
        "known_risks": ["public/customer output without owner review", "stock/payment/reservation mistakes"],
    },
    "fred": {
        "project_key": "fred",
        "entity_key": "fred",
        "name": "FRED",
        "purpose": "AMADEUS Private Transfers customer talking and transport engine.",
        "active_systems": ["private transfer concept lane"],
        "open_priorities": ["business model", "customer workflow", "quote/reservation boundaries"],
        "known_risks": ["premature customer commitments", "pricing/availability uncertainty"],
    },
    "farm_pig_application": {
        "project_key": "farm_pig_application",
        "entity_key": "farm_pig_application",
        "name": "Farm Pig Application",
        "purpose": "Pig tracking, litters, weights, breeding, stock, and farm app workflows.",
        "active_systems": ["pig records", "litters", "weights", "farm Supabase cutover"],
        "open_priorities": ["data quality", "safe writes", "owner-visible farm truth"],
        "known_risks": ["lifecycle record corruption", "stale sheet/Supabase state"],
    },
    "unassigned": {
        "project_key": "unassigned",
        "entity_key": "unassigned",
        "name": "Unassigned / General",
        "purpose": "General missions that have not yet been mapped to a business lane.",
        "active_systems": [],
        "open_priorities": ["classify lane before deep work"],
        "known_risks": ["unclear ownership", "wrong context loaded"],
    },
}
MISSION_MEDIA_DATA_URL_PATTERN = re.compile(r"^data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=\r\n]+$")
MISSION_MEDIA_DATA_URL_MAX_LEN = 900_000
MISSION_CONTEXT_DOCS = [
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
REVIEW_BOARD_AGENT_SEQUENCE = ["business_reviewer", "product_reviewer", "security_reviewer", "evidence_reviewer"]
WORKFLOW_TEMPLATES = {
    "software_build": {
        "label": "Software Build",
        "mission_type_tokens": {"software build", "feature build", "agent build", "code", "dashboard", "app"},
        "specialist_agents": ["idea_expander", "product_architect"],
        "review_board_agents": ["product_reviewer", "security_reviewer", "evidence_reviewer"],
        "quality_focus": ["user workflow", "regression risk", "security/privacy", "test and PR evidence"],
    },
    "business_plan": {
        "label": "Business Plan",
        "mission_type_tokens": {"business plan", "business", "strategy"},
        "specialist_agents": ["idea_expander", "product_architect"],
        "review_board_agents": ["business_reviewer", "product_reviewer", "evidence_reviewer"],
        "quality_focus": ["income logic", "owner value", "operational fit", "evidence quality"],
    },
    "system_improvement": {
        "label": "System Improvement",
        "mission_type_tokens": {"system improvement", "governance", "runner", "relay", "ops"},
        "specialist_agents": ["idea_expander", "product_architect"],
        "review_board_agents": ["product_reviewer", "security_reviewer", "evidence_reviewer"],
        "quality_focus": ["system truth", "operator workflow", "permission boundary", "rollback evidence"],
    },
    "content_engine": {
        "label": "Content Engine",
        "mission_type_tokens": {"content engine", "content", "marketing", "post"},
        "specialist_agents": ["idea_expander", "product_architect"],
        "review_board_agents": ["business_reviewer", "product_reviewer", "security_reviewer", "evidence_reviewer"],
        "quality_focus": ["brand/business fit", "audience flow", "public-output safety", "evidence"],
    },
    "automation_workflow": {
        "label": "Automation Workflow",
        "mission_type_tokens": {"automation workflow", "automation", "workflow", "n8n"},
        "specialist_agents": ["idea_expander", "product_architect"],
        "review_board_agents": ["product_reviewer", "security_reviewer", "evidence_reviewer"],
        "quality_focus": ["trigger contract", "data boundary", "failure handling", "run evidence"],
    },
    "income_stream": {
        "label": "Income Stream",
        "mission_type_tokens": {"income stream", "income", "revenue", "money path", "sales engine"},
        "specialist_agents": ["idea_expander", "product_architect"],
        "review_board_agents": ["business_reviewer", "product_reviewer", "security_reviewer", "evidence_reviewer"],
        "quality_focus": ["profit path", "customer value", "operational capacity", "risk and evidence"],
    },
}
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
        "handoff_to": "review_board",
    },
    "business_reviewer": {
        "purpose": "Review owner value, income logic, operational fit, pricing assumptions, and business risks.",
        "handoff_to": "product_reviewer",
    },
    "product_reviewer": {
        "purpose": "Review user flow, acceptance fit, command-center clarity, and product completeness.",
        "handoff_to": "security_reviewer",
    },
    "security_reviewer": {
        "purpose": "Review permissions, secrets, data boundaries, public/customer actions, and unsafe automation risk.",
        "handoff_to": "evidence_reviewer",
    },
    "evidence_reviewer": {
        "purpose": "Review proof quality, tests, artifacts, screenshots, PR links, and reproducibility before final review.",
        "handoff_to": "reviewer",
    },
    "reviewer": {
        "purpose": "Review diff, unsafe actions, docs, test evidence, QA findings, and release notes.",
        "handoff_to": "owner",
    },
}
AGENT_STAGE_MAP = {
    "idea_expander": "idea_expanded",
    "product_architect": "product_ready",
    "planner": "planned",
    "architect": "build_ready",
    "builder": "built",
    "tester": "tested",
    "qa_red_team": "qa_reviewed",
    "business_reviewer": "business_reviewed",
    "product_reviewer": "product_reviewed",
    "security_reviewer": "security_reviewed",
    "evidence_reviewer": "evidence_reviewed",
    "reviewer": "review_ready",
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
    "blocked",
    "pr_ready",
    "release_approved",
    "release_in_progress",
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


def list_missions(status="", limit=10, database_url=None, connect_factory=None):
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


def normalize_mission_lane(value):
    raw = _clean_text(value, 80)
    normalized = raw.lower().replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    aliases = {
        "": "unassigned",
        "general": "unassigned",
        "unassigned_general": "unassigned",
        "charlie": "charlie_core",
        "charlie_core": "charlie_core",
        "core": "charlie_core",
        "oom": "oom_sakkie",
        "oom_sakkie": "oom_sakkie",
        "sakkie": "oom_sakkie",
        "sam": "sam",
        "sales": "sam",
        "fred": "fred",
        "transfers": "fred",
        "private_transfers": "fred",
        "amadeus_private_transfers": "fred",
        "farm": "farm_pig_application",
        "farm_pig": "farm_pig_application",
        "farm_pig_application": "farm_pig_application",
        "pig_tracking": "farm_pig_application",
        "pig_tracker": "farm_pig_application",
    }
    lane_id = aliases.get(normalized, normalized)
    if lane_id not in MISSION_LANES:
        lane_id = "unassigned"
    lane = dict(MISSION_LANES[lane_id])
    lane["id"] = lane_id
    return lane


def normalize_workflow_template(value):
    raw = _clean_text(value, 100)
    normalized = raw.lower().replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    aliases = {
        "": "",
        "feature": "software_build",
        "feature_build": "software_build",
        "software": "software_build",
        "software_build": "software_build",
        "agent": "software_build",
        "agent_build": "software_build",
        "app": "software_build",
        "business": "business_plan",
        "business_plan": "business_plan",
        "strategy": "business_plan",
        "system": "system_improvement",
        "system_improvement": "system_improvement",
        "governance": "system_improvement",
        "content": "content_engine",
        "content_engine": "content_engine",
        "marketing": "content_engine",
        "automation": "automation_workflow",
        "automation_workflow": "automation_workflow",
        "workflow": "automation_workflow",
        "n8n": "automation_workflow",
        "income": "income_stream",
        "income_stream": "income_stream",
        "revenue": "income_stream",
        "money_path": "income_stream",
        "sales_engine": "income_stream",
    }
    template_id = aliases.get(normalized, normalized)
    if template_id in WORKFLOW_TEMPLATES:
        return _public_workflow_template(template_id)
    mission_type = raw.lower()
    for candidate_id, template in WORKFLOW_TEMPLATES.items():
        tokens = template.get("mission_type_tokens") or set()
        if any(token in mission_type for token in tokens):
            return _public_workflow_template(candidate_id)
    return _public_workflow_template("software_build")


def _public_workflow_template(template_id):
    template = dict(WORKFLOW_TEMPLATES[template_id])
    template.pop("mission_type_tokens", None)
    template["id"] = template_id
    return template


def agent_sequence_for_mission(mission_type=""):
    template = normalize_workflow_template(mission_type)
    sequence = []
    for agent in template.get("specialist_agents") or []:
        if agent in SPECIALIST_AGENT_SEQUENCE and agent not in sequence:
            sequence.append(agent)
    sequence.extend([agent for agent in CORE_AGENT_SEQUENCE_V2 if agent != "reviewer"])
    for agent in template.get("review_board_agents") or []:
        if agent in REVIEW_BOARD_AGENT_SEQUENCE and agent not in sequence:
            sequence.append(agent)
    sequence.append("reviewer")
    return sequence


def all_agent_names():
    return list(AGENT_DEFINITIONS.keys())


def charlie_brain_registry(entity_key=""):
    entity_key = _clean_text(entity_key, 80).lower() or ""
    documents = []
    for item in CHARLIE_BRAIN_DOCUMENTS:
        if entity_key and item.get("entity_key") not in {entity_key, "charlie_core"}:
            continue
        documents.append({
            "doc_path": item["doc_path"],
            "title": item["title"],
            "entity_key": item["entity_key"],
            "document_type": item["document_type"],
            "tags": list(item.get("tags") or []),
            "summary": item.get("summary", ""),
            "status": "active",
            "owner_approved": True,
            "confidence_level": "working",
        })
    return documents


def project_memory_for_lane(lane):
    lane_id = lane.get("id") if isinstance(lane, dict) else ""
    lane_id = lane_id or normalize_mission_lane(lane)["id"]
    memory = dict(PROJECT_MEMORY.get(lane_id) or PROJECT_MEMORY["unassigned"])
    memory["active_truth_docs"] = [
        item["doc_path"]
        for item in charlie_brain_registry(memory.get("entity_key", ""))
    ]
    return memory


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

    if "mission_lane" in updates or "lane" in updates:
        lane = normalize_mission_lane(updates.get("mission_lane", updates.get("lane", "")))
        if lane != mission.get("mission_lane", normalize_mission_lane("")):
            metadata["mission_lane"] = lane
            changed_fields.append("mission_lane")
            previous_values["mission_lane"] = mission.get("mission_lane", normalize_mission_lane(""))

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
        vault["mission_stage"] = "blocked"
    if findings:
        handoff_notes = vault.get("handoff_notes") if isinstance(vault.get("handoff_notes"), list) else []
        handoff_notes = list(handoff_notes)
        handoff_notes.append({"agent": agent, "status": step_status, "findings": findings})
        vault["handoff_notes"] = handoff_notes[-12:]
    context_pack = metadata.get("mission_context_pack") if isinstance(metadata.get("mission_context_pack"), dict) else _default_context_pack(mission.get("mission_type", ""))

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

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mission_id": mission_id,
        "mission_status": target_status,
        "review_decision": decision,
        "approval_level": normalize_approval_level(approval_level),
    }, 200


def build_mission_review_packet(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    mission_lane = mission.get("mission_lane") if isinstance(mission.get("mission_lane"), dict) else normalize_mission_lane("")
    return {
        "mission": {
            "mission_id": mission.get("mission_id", ""),
            "title": mission.get("title", ""),
            "status": mission.get("status", ""),
            "urgency": mission.get("urgency", ""),
            "mission_type": mission.get("mission_type", ""),
            "mission_lane": mission_lane,
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
        "handoff_reports": packet.get("handoff_reports") if isinstance(packet.get("handoff_reports"), dict) else {},
        "backflow_events": packet.get("backflow_events") if isinstance(packet.get("backflow_events"), list) else [],
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
    mission_lane = normalize_mission_lane(metadata.get("mission_lane") if isinstance(metadata.get("mission_lane"), (str, dict)) else "")
    if isinstance(metadata.get("mission_lane"), dict):
        mission_lane = normalize_mission_lane(metadata["mission_lane"].get("id") or metadata["mission_lane"].get("label"))
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
        "mission_lane": mission_lane,
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
    if "smoke test" in normalized_title or "validation mission" in normalized_title:
        return "system_test"
    return "owner_work"


def _normalize_mission_text(value):
    return " ".join(str(value or "").strip().lower().split())


def _mission_metadata(raw_text, mission, source_context, metadata):
    metadata = dict(metadata or {})
    lane_value = mission.get("mission_lane", mission.get("lane", metadata.get("mission_lane", "")))
    if isinstance(lane_value, dict):
        lane_value = lane_value.get("id") or lane_value.get("label") or ""
    metadata["mission_lane"] = normalize_mission_lane(lane_value)
    template_value = mission.get("workflow_template", mission.get("template", mission.get("mission_type", "")))
    metadata["workflow_template"] = normalize_workflow_template(template_value)
    workflow_template_id = metadata["workflow_template"]["id"]
    metadata.setdefault("mission_vault", _default_mission_vault(raw_text, {**mission, "workflow_template": workflow_template_id}))
    metadata.setdefault("agent_workflow", _default_agent_workflow(workflow_template_id))
    metadata.setdefault("mission_context_pack", _default_context_pack(workflow_template_id, metadata["mission_lane"]))
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
    template = normalize_workflow_template(mission.get("workflow_template", mission.get("template", mission.get("mission_type", ""))))
    return {
        "mission_stage": "intake",
        "workflow_template": template,
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


def _default_agent_workflow(mission_type=""):
    sequence = agent_sequence_for_mission(mission_type)
    workflow = []
    for index, agent in enumerate(sequence):
        definition = AGENT_DEFINITIONS[agent]
        next_agent = sequence[index + 1] if index + 1 < len(sequence) else definition.get("handoff_to", "owner")
        workflow.append({
            "agent": agent,
            "status": "pending",
            "purpose": definition.get("purpose", ""),
            "handoff_to": next_agent,
            "findings": "",
        })
    return workflow


def _default_context_pack(mission_type="", mission_lane=None):
    sequence = agent_sequence_for_mission(mission_type)
    template = normalize_workflow_template(mission_type)
    lane = normalize_mission_lane(mission_lane.get("id") if isinstance(mission_lane, dict) else mission_lane)
    project_memory = project_memory_for_lane(lane)
    brain_docs = charlie_brain_registry(project_memory.get("entity_key", ""))
    return {
        "version": "charlie_context_pack_v1",
        "workflow_template": template,
        "project_memory": project_memory,
        "brain_registry": {
            "version": "charlie_brain_v1",
            "storage": "markdown_truth_docs_plus_supabase_registry",
            "documents": brain_docs,
            "rules": [
                "Markdown docs remain the human-readable brain.",
                "Supabase Brain tables index docs, project memory, mission links, decisions, and evidence.",
                "Agents must cite active truth docs before overriding project assumptions.",
            ],
        },
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
        "agent_order": sequence,
        "specialist_agents": [agent for agent in sequence if agent in SPECIALIST_AGENT_SEQUENCE],
        "review_board_agents": [agent for agent in sequence if agent in REVIEW_BOARD_AGENT_SEQUENCE],
        "quality_focus": list(template.get("quality_focus") or []),
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
    known = {item.get("agent"): dict(item) for item in workflow if isinstance(item, dict)}
    sequence = _workflow_sequence(workflow)
    for default in _workflow_defaults_for_sequence(sequence):
        known.setdefault(default["agent"], dict(default))
    if next_agent and next_agent in known:
        known[agent]["handoff_to"] = next_agent
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
    for default in _workflow_defaults_for_sequence(sequence):
        known.setdefault(default["agent"], dict(default))
    target_stage = target_stage if target_stage in known else "builder"
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


def _workflow_sequence(workflow):
    sequence = [item.get("agent") for item in workflow if isinstance(item, dict) and item.get("agent") in all_agent_names()]
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
