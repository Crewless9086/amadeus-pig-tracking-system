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
from modules.charlie.mission_outcome_gate import evaluate_outcome_handover, mission_lifecycle_projection
from modules.charlie.final_readiness import evaluate_final_readiness
from modules.charlie.evidence_reconciliation import (
    applicable_passing_agents,
    targeted_workflow_return,
)
from modules.charlie.adaptive_orchestration import validate_orchestration_binding
from modules.charlie.mission_control import (
    apply_event_to_projection, build_mission_control_event, canonical_event_equal,
    validate_mission_control_event,
)
from modules.charlie.operational_events import build_event


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
    "outcome_handover_recorded",
}
APPROVAL_LEVELS = {"LEVEL 0", "LEVEL 1", "LEVEL 2", "LEVEL 3", "LEVEL 4", "LEVEL 5"}
MISSION_LIFECYCLE_HISTORY_LIMIT = 100
MISSION_OUTCOME_HANDOVER_BYTES_LIMIT = 65536
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
    "paused",
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
BOOTSTRAP_PORTFOLIO_MISSION_ID = "CMQ-20260813-05"
BOOTSTRAP_PORTFOLIO_ADMISSION = {
    "portfolio_epoch": "CORE-CURRENT-2026-08-14",
    "classification": "current",
    "lifecycle_state": "WORKING",
    "admission_version": "portfolio_admission_v1",
    "admission_evidence": "owner_approved_cmq_20260813_05_bootstrap",
    "decision_authority": "human_control_tower",
    "dispatch_authority": "human_control_tower",
    "runnable": False,
}


def record_mission(mission, source_context=None, database_url=None, connect_factory=None,
                   exact_identity=False):
    mission = mission if isinstance(mission, dict) else {}
    source_context = source_context if isinstance(source_context, dict) else {}
    raw_text = _clean_text(mission.get("raw_text", ""), 3000)
    if not raw_text:
        return {"stored": False, "status": "mission_text_required"}, 400
    if exact_identity and not _clean_text(mission.get("mission_id", ""), 90):
        return {"stored": False, "status": "exact_mission_identity_required"}, 400
    intake_quality = _mission_intake_quality(mission, raw_text)
    if intake_quality["blocked"]:
        return {
            "stored": False,
            "status": "mission_intake_too_vague",
            "reason": intake_quality["reason"],
        }, 400
    admission = (mission.get("metadata") or {}).get("portfolio_admission") \
        if isinstance(mission.get("metadata"), dict) else None
    if (exact_identity and mission.get("mission_id") == BOOTSTRAP_PORTFOLIO_MISSION_ID
            and admission is None):
        return {"stored": False, "configured": True,
            "status": "portfolio_admission_required"}, 409
    if admission is not None and not (
            exact_identity
            and mission.get("mission_id") == BOOTSTRAP_PORTFOLIO_MISSION_ID
            and mission.get("status") == "paused"
            and admission == BOOTSTRAP_PORTFOLIO_ADMISSION):
        return {"stored": False, "configured": True,
            "status": "portfolio_admission_not_authorized"}, 409

    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"stored": False, "configured": False, "status": "not_configured"}, 503

    try:
        params = _mission_params(mission, source_context)
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                _lock_mission_intake_title(cursor, params)
                exact_result = (_resolve_exact_identity_intake(cursor, params)
                    if exact_identity else None)
                if exact_result:
                    return exact_result
                duplicate = None if exact_identity else _find_open_duplicate_mission(cursor, params)
                replacement = None
                if duplicate:
                    duplicate_contract = _duplicate_contract_state(duplicate)
                    if duplicate_contract["status"] == "current_contract_reusable":
                        duplicate_metadata = duplicate.get("metadata") if isinstance(duplicate.get("metadata"), dict) else {}
                        if not duplicate_metadata.get("opaque_identity_owner_approved"):
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
                    if duplicate_contract["status"] == "legacy_duplicate_active":
                        return {
                            "stored": False,
                            "configured": True,
                            "status": "legacy_duplicate_active_not_superseded",
                            "reason": duplicate_contract["reason"],
                            "mission_id": duplicate["mission_id"],
                            "existing_status": duplicate["status"],
                        }, 409
                    if duplicate_contract["status"] != "legacy_duplicate_not_reusable":
                        return {
                            "stored": False,
                            "configured": True,
                            "status": duplicate_contract["status"],
                            "reason": duplicate_contract["reason"],
                            "mission_id": duplicate["mission_id"],
                        }, 409
                    replacement = _legacy_replacement_params(params, duplicate)
                    if not replacement.get("valid"):
                        return {
                            "stored": False,
                            "configured": True,
                            "status": "legacy_duplicate_replacement_blocked",
                            "reason": replacement.get("reason"),
                            "mission_id": duplicate["mission_id"],
                        }, 409
                    params = replacement["params"]
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
                    on conflict (mission_id) do nothing
                    returning mission_id
                    """,
                    params,
                )
                inserted = cursor.fetchone()
                if not inserted:
                    if replacement:
                        cursor.execute(
                            """select metadata_json from public.charlie_missions
                               where mission_id = %(mission_id)s for update""",
                            {"mission_id": params["mission_id"]},
                        )
                        rows = cursor.fetchall()
                        existing_metadata = (
                            rows[0][0]
                            if rows and isinstance(rows[0][0], dict)
                            else {}
                        )
                        if not _replacement_metadata_matches(
                            existing_metadata,
                            replacement["supersedes_mission_id"],
                            replacement["replacement_identity"],
                        ):
                            raise ValueError("legacy_replacement_identity_conflict")
                        return {
                            "stored": False,
                            "configured": True,
                            "status": "legacy_duplicate_replacement_reused",
                            "classification": "legacy_duplicate_not_reusable",
                            "mission_id": params["mission_id"],
                            "supersedes_mission_id": replacement["supersedes_mission_id"],
                            "orchestration_generation": (
                                existing_metadata.get("orchestration") or {}
                            ).get("generation_identity"),
                        }, 200
                    return {
                        "stored": False, "configured": True, "status": "duplicate_open_mission",
                        "mission_id": params["mission_id"], "existing_status": "new", "title": params["title"],
                    }, 200
                cursor.execute(
                    """select metadata_json from public.charlie_missions
                       where mission_id = %(mission_id)s for update""",
                    {"mission_id": params["mission_id"]},
                )
                persisted_rows = cursor.fetchall()
                persisted_metadata = (
                    persisted_rows[0][0]
                    if persisted_rows and isinstance(persisted_rows[0][0], dict)
                    else {}
                )
                persisted_binding = validate_orchestration_binding(
                    persisted_metadata.get("orchestration"),
                    persisted_metadata.get("agent_workflow"),
                )
                expected_binding = (
                    persisted_metadata.get("orchestration_binding")
                    if isinstance(persisted_metadata.get("orchestration_binding"), dict)
                    else {}
                )
                if (
                    not persisted_binding.get("valid")
                    or persisted_binding.get("identity") != expected_binding.get("identity")
                    or expected_binding.get("generation_identity")
                    != (persisted_metadata.get("orchestration") or {}).get("generation_identity")
                ):
                    raise ValueError("orchestration_persistence_verification_failed")
                _insert_event(cursor, params["mission_id"], "created", "Mission intake recorded.", {
                    "source": params["source"],
                    "telegram_user_id": params["telegram_user_id"],
                    "orchestration_generation": expected_binding.get("generation_identity"),
                    "orchestration_binding_identity": expected_binding.get("identity"),
                    **({
                        "classification": "legacy_duplicate_not_reusable",
                        "supersedes_mission_id": replacement["supersedes_mission_id"],
                        "replacement_identity": replacement["replacement_identity"],
                    } if replacement else {}),
                })
                admission = persisted_metadata.get("portfolio_admission")
                if isinstance(admission, dict):
                    _insert_event(cursor, params["mission_id"], "portfolio_admitted",
                        "Owner-approved bootstrap portfolio admission recorded.", admission)
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
        "status": "legacy_duplicate_replacement_created" if replacement else "ok",
        "mission_id": params["mission_id"],
        **({
            "classification": "legacy_duplicate_not_reusable",
            "supersedes_mission_id": replacement["supersedes_mission_id"],
            "orchestration_generation": (
                json.loads(params["metadata_json"]).get("orchestration") or {}
            ).get("generation_identity"),
        } if replacement else {}),
    }, 201


def mission_runtime_eligible(mission):
    """Fail closed for structured portfolio admissions not yet made runnable."""
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    # Phase A authorizes no runnable portfolio admission. Legacy rows without
    # this key retain their established status-based behavior; any present,
    # malformed, forged or future contract remains ineligible until a later
    # reviewed enforcement stage explicitly validates and enables it.
    return "portfolio_admission" not in metadata and "portfolio_classification" not in metadata


def list_missions(
    status="",
    limit=10,
    database_url=None,
    connect_factory=None,
    compact=False,
    outcome_candidates=False,
    exclude_superseded=False,
    exclude_execution_held=False,
):
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
    if exclude_superseded:
        where_clause += (" and " if where_clause else "where ") + _not_durably_superseded_sql()
    if exclude_execution_held:
        where_clause += (" and " if where_clause else "where ") + _not_execution_held_sql()
    if outcome_candidates:
        candidate_filter = """
                    (
                        jsonb_typeof(metadata_json->'review_packet'->'changed_files') = 'array'
                        and jsonb_array_length(metadata_json->'review_packet'->'changed_files') > 0
                        or jsonb_typeof(metadata_json->'review_packet'->'protected_operations') = 'array'
                        and jsonb_array_length(metadata_json->'review_packet'->'protected_operations') > 0
                        or jsonb_typeof(metadata_json->'protected_operations') = 'array'
                        and jsonb_array_length(metadata_json->'protected_operations') > 0
                    )
                    and (
                        coalesce((metadata_json->'outcome_closure_tracking'->>'enabled')::boolean, false)
                        or coalesce((metadata_json->'outcome_closure'->>'unfinished')::boolean, false)
                    )
                    and (
                        metadata_json->'outcome_closure' is null
                        or coalesce((metadata_json->'outcome_closure'->>'unfinished')::boolean, false)
                    )
                    """
        where_clause += (" and " if where_clause else "where ") + candidate_filter
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
                      and metadata_json->'portfolio_classification' is null
                      and {_not_durably_superseded_sql()}
                      and {_not_execution_held_sql()}
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


def _not_durably_superseded_sql():
    """Keep immutable legacy rows visible generally but out of execution queues."""
    return """
                      not exists (
                          select 1
                          from public.charlie_missions as replacement
                          where replacement.metadata_json->'supersession'->>'status' = 'current_contract_replacement'
                            and replacement.metadata_json->'supersession'->>'supersedes_mission_id'
                                = public.charlie_missions.mission_id
                            and coalesce(
                                (replacement.metadata_json->'orchestration_binding'->>'validated')::boolean,
                                false
                            )
                            and replacement.metadata_json->'orchestration_binding'->>'generation_identity'
                                = replacement.metadata_json->'orchestration'->>'generation_identity'
                      )
                    """


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


def append_mission_control_event(mission_id, payload, *, recorded_by,
                                 database_url=None, connect_factory=None):
    """Append one governed event and atomically refresh its derived owner projection."""
    mission_id = _clean_text(mission_id, 90)
    try:
        event = build_mission_control_event(mission_id, payload, recorded_by=recorded_by)
    except ValueError as exc:
        return {"success": False, "status": str(exc)}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select mission_id,status,source,telegram_user_id,telegram_chat_id,
                    raw_text,title,urgency,mission_type,approval_level,selected_next_step,
                    owner_decision,codex_chat_write_status,metadata_json,created_at,updated_at
                    from public.charlie_missions where mission_id=%(mission_id)s for update""",
                    {"mission_id": mission_id})
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                mission = _mission_row(row)
                if event["event_type"] == "owner_correction_recorded":
                    cursor.execute("""select metadata_json from public.charlie_mission_events
                        where event_id=%(event_id)s and mission_id=%(mission_id)s limit 1""", {
                        "event_id": event["corrects_event_id"], "mission_id": mission_id})
                    if cursor.fetchone() is None:
                        return {"success": False, "status": "correction_target_not_found_on_mission",
                                "mission_id": mission_id}, 409
                cursor.execute("""insert into public.charlie_mission_events
                    (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
                    values (%(event_id)s,%(mission_id)s,%(event_type)s,%(notes)s,%(recorded_by)s,%(metadata)s::jsonb,%(created_at)s)
                    on conflict (event_id) do nothing returning event_id""", {
                    "event_id": event["event_id"], "mission_id": mission_id,
                    "event_type": event["event_type"], "notes": event["summary"],
                    "recorded_by": recorded_by, "metadata": json.dumps(event, sort_keys=True),
                    "created_at": event["recorded_at"],
                })
                created = cursor.fetchone() is not None
                if created:
                    projection = apply_event_to_projection(mission, event)
                    metadata = dict(mission.get("metadata") or {})
                    metadata["mission_control_projection"] = projection
                    cursor.execute("""update public.charlie_missions
                        set metadata_json=%(metadata)s::jsonb,updated_at=now()
                        where mission_id=%(mission_id)s""", {
                        "metadata": json.dumps(metadata, sort_keys=True), "mission_id": mission_id})
                else:
                    cursor.execute("""select metadata_json from public.charlie_mission_events
                        where event_id=%(event_id)s and mission_id=%(mission_id)s limit 1""", {
                        "event_id": event["event_id"], "mission_id": mission_id})
                    stored_row = cursor.fetchone()
                    stored = stored_row[0] if stored_row and isinstance(stored_row[0], dict) else {}
                    if not canonical_event_equal(stored, event):
                        return {"success": False, "status": "mission_control_event_idempotency_conflict",
                                "mission_id": mission_id, "event_id": event["event_id"]}, 409
                    projection = mission.get("owner_projection") or {}
        return {"success": True, "status": "recorded" if created else "exact_replay",
                "created": created, "event": event, "owner_projection": projection}, 201 if created else 200
    except Exception as exc:
        return {"success": False, "status": "mission_control_event_write_failed",
                "error_type": exc.__class__.__name__}, 503


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
    if status not in {"in_progress", "release_in_progress"}:
        set_lines.append("metadata_json = coalesce(metadata_json, '{}'::jsonb) - 'execution_lease'")
    if approval_level:
        set_lines.append("approval_level = %(approval_level)s")
    set_lines.append("updated_at = now()")
    set_sql = ",\n                        ".join(set_lines)
    expected_clause = "and status = %(expected_status)s" if expected_status else ""
    hold_clause = f"and {_not_execution_held_sql()}"
    portfolio_clause = "and metadata_json->'portfolio_classification' is null"
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    with mission_hold_lock as (
                        select pg_advisory_xact_lock(hashtextextended(%(mission_id)s, 0))
                    )
                    update public.charlie_missions
                    set {set_sql}
                    from mission_hold_lock
                    where mission_id = %(mission_id)s
                    {expected_clause}
                    {hold_clause}
                    {portfolio_clause}
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
                    held, held_status = owner_execution_hold_status(mission_id, cursor=cursor)
                    if held_status < 400 and held.get("active"):
                        return {
                            "success": False,
                            "configured": True,
                            "status": "owner_execution_hold_active",
                            "mission_id": mission_id,
                            "hold": _public_owner_execution_hold(held.get("hold")),
                        }, 423
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


def record_mission_outcome_evidence(mission_id, evidence_row, evidence_payload, *, evidence_id,
                                    authenticated_principal, producer_actor_type="external_verifier",
                                    database_url=None, connect_factory=None):
    """Append one producer-bound canonical outcome-evidence event."""
    from modules.charlie.mission_outcome_gate import EVIDENCE_ROWS
    mission_id = _clean_text(mission_id, 90)
    evidence_id = _clean_text(evidence_id, 160)
    producer_identity = _clean_text(authenticated_principal, 200)
    producer_actor_type = _clean_text(producer_actor_type, 40).lower()
    if (not mission_id or not evidence_id or evidence_row not in EVIDENCE_ROWS
            or producer_actor_type not in {"deployed_agent", "external_verifier"}
            or not producer_identity or not isinstance(evidence_payload, dict)):
        return {"success": False, "status": "invalid_outcome_evidence_contract"}, 400
    payload_digest = hashlib.sha256(json.dumps(
        evidence_payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")).hexdigest()
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    metadata = {"outcome_evidence_row": evidence_row, "evidence_payload_digest": payload_digest,
                "producer_identity": producer_identity, "producer_actor_type": producer_actor_type}
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select mission_id from public.charlie_missions where mission_id=%(mission_id)s for update",
                               {"mission_id": mission_id})
                if not cursor.fetchall():
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                cursor.execute(
                    """insert into public.charlie_mission_events
                       (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
                       values (%(event_id)s,%(mission_id)s,'outcome_evidence_recorded',
                               'Producer-bound canonical mission outcome evidence.',%(recorded_by)s,%(metadata)s::jsonb,now())
                       on conflict (event_id) do nothing
                       returning mission_id,metadata_json->>'evidence_payload_digest'""",
                    {"event_id": evidence_id, "mission_id": mission_id,
                     "recorded_by": producer_identity, "metadata": json.dumps(metadata)},
                )
                inserted = cursor.fetchall()
                if not inserted:
                    cursor.execute(
                        """select mission_id,metadata_json->>'evidence_payload_digest',
                                  metadata_json->>'outcome_evidence_row',metadata_json->>'producer_identity',
                                  metadata_json->>'producer_actor_type'
                           from public.charlie_mission_events where event_id=%(event_id)s for update""",
                        {"event_id": evidence_id},
                    )
                    existing = cursor.fetchall()
                    if (not existing or existing[0][0] != mission_id or existing[0][1] != payload_digest
                            or existing[0][2] != evidence_row or existing[0][3] != producer_identity
                            or existing[0][4] != producer_actor_type):
                        return {"success": False, "status": "outcome_evidence_replay_conflict",
                                "mission_id": mission_id}, 409
    except Exception as exc:
        return {"success": False, "status": "outcome_evidence_write_failed",
                "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "outcome_evidence_recorded", "mission_id": mission_id,
            "evidence_id": evidence_id, "payload_digest": payload_digest}, 201


def record_mission_outcome_handover(mission_id, handover, *, authenticated_principal="",
                                    database_url=None, connect_factory=None):
    """Atomically append a handover evaluation; technical status is never business truth."""
    mission_id = _clean_text(mission_id, 90)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if not isinstance(handover, dict):
        return {"success": False, "status": "handover_contract_required"}, 400
    handover_id = _clean_text(handover.get("handover_id"), 160)
    handover_mission_id = _clean_text(handover.get("mission_id"), 90)
    if not handover_id:
        return {"success": False, "status": "handover_id_required", "mission_id": mission_id}, 400
    if handover_mission_id != mission_id:
        return {"success": False, "status": "handover_mission_identity_mismatch", "mission_id": mission_id}, 409
    if len(json.dumps(handover, separators=(",", ":"), default=str).encode("utf-8")) > MISSION_OUTCOME_HANDOVER_BYTES_LIMIT:
        return {"success": False, "status": "handover_contract_too_large", "mission_id": mission_id}, 413
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select status,coalesce(metadata_json,'{}'::jsonb)
                       from public.charlie_missions where mission_id=%(mission_id)s for update""",
                    {"mission_id": mission_id},
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                technical_status, metadata = rows[0][0], dict(rows[0][1] or {})
                prior = metadata.get("mission_lifecycle") if isinstance(metadata.get("mission_lifecycle"), dict) else {}
                history = list(metadata.get("mission_lifecycle_history") or [])
                submitted_digest = hashlib.sha256(json.dumps(
                    handover, sort_keys=True, separators=(",", ":"), default=str
                ).encode("utf-8")).hexdigest()
                cursor.execute(
                    """select coalesce(metadata_json,'{}'::jsonb)
                       from public.charlie_mission_events
                       where mission_id=%(mission_id)s
                         and event_type='outcome_handover_recorded'
                         and metadata_json->>'handover_id'=%(handover_id)s
                       order by created_at asc limit 1""",
                    {"mission_id": mission_id, "handover_id": handover_id},
                )
                replay_rows = cursor.fetchall()
                if replay_rows:
                    recorded_evaluation = dict(replay_rows[0][0] or {})
                    if recorded_evaluation.get("handover_digest") != submitted_digest:
                        return {"success": False, "status": "handover_replay_conflict", "mission_id": mission_id}, 409
                    replay_valid = recorded_evaluation.get("handover_status") == "VALID_HANDOVER"
                    return {"success": replay_valid, "status": "handover_already_recorded", "mission_id": mission_id,
                            "technical_status": technical_status, "mission_lifecycle": recorded_evaluation}, 200 if replay_valid else 422
                evidence = handover.get("evidence") if isinstance(handover.get("evidence"), dict) else {}
                evidence_ids = sorted({str(value.get("evidence_id")) for value in evidence.values()
                                       if isinstance(value, dict) and value.get("evidence_id")})
                cursor.execute(
                    """select event_id,event_type,coalesce(metadata_json,'{}'::jsonb),created_at
                       from public.charlie_mission_events
                       where mission_id=%(mission_id)s and event_id=any(%(evidence_ids)s)""",
                    {"mission_id": mission_id, "evidence_ids": evidence_ids},
                )
                canonical_evidence = {}
                for event_id, event_type, event_metadata, created_at in cursor.fetchall():
                    event_metadata = dict(event_metadata or {})
                    canonical_evidence[str(event_id)] = {
                        "event_type": event_type,
                        "evidence_row": event_metadata.get("outcome_evidence_row"),
                        "mission_bound": event_type == "outcome_evidence_recorded",
                        "payload_digest": event_metadata.get("evidence_payload_digest"),
                        "producer_identity": event_metadata.get("producer_identity"),
                        "producer_actor_type": event_metadata.get("producer_actor_type"),
                        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
                    }
                evaluation = evaluate_outcome_handover(
                    handover, mission_id=mission_id, prior=prior,
                    canonical_evidence=canonical_evidence,
                    authenticated_actor_type="control_tower",
                    authenticated_principal=authenticated_principal,
                )
                same_id = next((row for row in history if row.get("handover_id") and row.get("handover_id") == evaluation["handover_id"]), None)
                if same_id:
                    if same_id.get("handover_digest") != evaluation.get("handover_digest"):
                        return {"success": False, "status": "handover_replay_conflict", "mission_id": mission_id}, 409
                    return {"success": True, "status": "handover_already_recorded", "mission_id": mission_id,
                            "technical_status": technical_status, "mission_lifecycle": same_id}, 200
                history.append(evaluation)
                if len(history) > MISSION_LIFECYCLE_HISTORY_LIMIT:
                    archived = history.pop(0)
                    prior_digest = str(metadata.get("mission_lifecycle_history_archive_digest") or "")
                    metadata["mission_lifecycle_history_archive_digest"] = hashlib.sha256(
                        f"{prior_digest}:{archived.get('handover_digest', '')}".encode("utf-8")
                    ).hexdigest()
                    metadata["mission_lifecycle_history_archived_count"] = int(
                        metadata.get("mission_lifecycle_history_archived_count") or 0
                    ) + 1
                if evaluation["handover_status"] == "VALID_HANDOVER":
                    metadata["mission_lifecycle"] = evaluation
                metadata["mission_lifecycle_history"] = history
                cursor.execute(
                    """update public.charlie_missions set metadata_json=%(metadata)s::jsonb,updated_at=now()
                       where mission_id=%(mission_id)s""",
                    {"mission_id": mission_id, "metadata": json.dumps(metadata)},
                )
                _insert_event(cursor, mission_id, "outcome_handover_recorded",
                              "CORE evaluated a structured mission outcome handover.", evaluation)
    except Exception as exc:
        return {"success": False, "status": "outcome_handover_write_failed", "error_type": exc.__class__.__name__}, 503
    code = 200 if evaluation["handover_status"] == "VALID_HANDOVER" else 422
    return {"success": code == 200, "status": evaluation["handover_status"], "mission_id": mission_id,
            "technical_status": technical_status, "mission_lifecycle": evaluation}, code


def transition_mission_review_state(
    mission_id,
    status,
    review_packet,
    *,
    expected_status="",
    owner_decision="",
    notes="",
    database_url=None,
    connect_factory=None,
):
    """Atomically change mission status and its authoritative review packet."""
    mission_id = _clean_text(mission_id, 90)
    status = _clean_text(status, 40)
    expected_status = _clean_text(expected_status, 40)
    if not mission_id or status not in MISSION_STATUSES:
        return {"success": False, "status": "invalid_review_transition"}, 400
    if not isinstance(review_packet, dict):
        return {"success": False, "status": "review_packet_required"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    expected_clause = "and status = %(expected_status)s" if expected_status else ""
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    update public.charlie_missions
                    set status = %(status)s,
                        owner_decision = %(owner_decision)s,
                        metadata_json = (coalesce(metadata_json, '{{}}'::jsonb) - 'execution_lease') || jsonb_build_object('review_packet', %(review_packet)s::jsonb),
                        updated_at = now()
                    where mission_id = %(mission_id)s
                    {expected_clause}
                    and metadata_json->'portfolio_classification' is null
                    returning mission_id
                    """,
                    {
                        "mission_id": mission_id,
                        "status": status,
                        "owner_decision": _clean_text(owner_decision, 1000),
                        "review_packet": json.dumps(review_packet),
                        "expected_status": expected_status,
                    },
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "status": "status_claim_lost", "mission_id": mission_id}, 409
                _insert_event(cursor, mission_id, "status_changed", notes or f"Review state changed atomically to {status}.", {
                    "status": status,
                    "review_status": review_packet.get("review_status", ""),
                    "atomic_review_transition": True,
                })
    except Exception as exc:
        return {"success": False, "status": "review_transition_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "review_state_transitioned", "mission_id": mission_id, "mission_status": status}, 200


def finalize_owner_review_transaction(
    mission_id,
    review_packet,
    *,
    execution_id,
    candidate_revision,
    expected_status="in_progress",
    database_url=None,
    connect_factory=None,
):
    """Atomically publish the only legal automated transition to ``pr_ready``.

    Workflow helpers deliberately cannot promote a mission.  This transaction
    locks the mission row, rechecks the durable workflow and candidate-bound
    evidence, and writes the packet/status/event together.
    """


    mission_id = _clean_text(mission_id, 90)
    execution_id = _clean_text(execution_id, 120)
    candidate_revision = _clean_text(candidate_revision, 120)
    expected_status = _clean_text(expected_status, 40) or "in_progress"
    if not mission_id or not execution_id or not candidate_revision:
        return {"success": False, "status": "finalization_identity_required"}, 400
    if not isinstance(review_packet, dict):
        return {"success": False, "status": "review_packet_required"}, 400
    reconciliation = review_packet.get("evidence_reconciliation") if isinstance(review_packet.get("evidence_reconciliation"), dict) else {}
    manifest = reconciliation.get("candidate_manifest") if isinstance(reconciliation.get("candidate_manifest"), dict) else {}
    github_gate = review_packet.get("github_gate") if isinstance(review_packet.get("github_gate"), dict) else {}
    packet_execution = review_packet.get("execution_artifacts") if isinstance(review_packet.get("execution_artifacts"), dict) else {}
    tested_revision = _clean_text(review_packet.get("tested_revision"), 120)
    if (
        reconciliation.get("passed") is not True
        or reconciliation.get("active_blockers")
        or reconciliation.get("requires_revalidation")
    ):
        return {"success": False, "status": "finalization_evidence_not_ready"}, 409
    if _clean_text(manifest.get("source_commit"), 120) != candidate_revision or tested_revision != candidate_revision:
        return {"success": False, "status": "finalization_candidate_mismatch"}, 409
    if github_gate.get("passed") is not True or _clean_text(github_gate.get("head_revision"), 120) != candidate_revision:
        return {"success": False, "status": "finalization_github_gate_not_ready"}, 409
    if _clean_text(packet_execution.get("execution_id"), 120) != execution_id:
        return {"success": False, "status": "finalization_execution_mismatch"}, 409
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select status, coalesce(metadata_json, '{}'::jsonb)
                    from public.charlie_missions
                    where mission_id = %(mission_id)s
                    for update
                    """,
                    {"mission_id": mission_id},
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found"}, 404
                current_status, metadata = row[0], row[1] or {}
                if "portfolio_classification" in metadata:
                    return {"success": False, "status": "portfolio_classified_mission_ineligible"}, 409
                if current_status != expected_status:
                    return {
                        "success": False,
                        "status": "status_claim_lost",
                        "expected_status": expected_status,
                        "current_status": current_status,
                    }, 409
                workflow = metadata.get("agent_workflow") if isinstance(metadata.get("agent_workflow"), list) else []
                incomplete = [
                    str(item.get("agent") or "") for item in workflow
                    if isinstance(item, dict) and str(item.get("status") or "").strip().lower() != "complete"
                ]
                if not workflow or incomplete:
                    return {"success": False, "status": "finalization_workflow_not_complete", "agents": incomplete}, 409
                # This is a durable review-generation identity, not a timestamp.  A
                # mission can legitimately return to owner review at the same PR head;
                # its new execution still needs one fresh owner brief.
                review_packet = dict(review_packet)
                review_packet["review_generation"] = f"{execution_id}:{candidate_revision}"
                cursor.execute(
                    """
                    update public.charlie_missions
                    set status = 'pr_ready',
                        owner_decision = 'CORE atomically finalised owner review.',
                        metadata_json = (coalesce(metadata_json, '{}'::jsonb) - 'execution_lease')
                            || jsonb_build_object(
                                'review_packet', %(review_packet)s::jsonb,
                                'outcome_closure_tracking', jsonb_build_object(
                                    'version', 'charlie-operational-outcome-v1',
                                    'enabled', true
                                )
                            ),
                        updated_at = now()
                    where mission_id = %(mission_id)s and status = %(expected_status)s
                    returning mission_id
                    """,
                    {
                        "mission_id": mission_id,
                        "expected_status": expected_status,
                        "review_packet": json.dumps(review_packet),
                    },
                )
                if not cursor.fetchall():
                    return {"success": False, "status": "status_claim_lost"}, 409
                _insert_event(cursor, mission_id, "status_changed", "CORE atomically finalised owner review.", {
                    "status": "pr_ready",
                    "review_status": "ready_for_owner_review",
                    "atomic_finalisation": True,
                    "execution_id": execution_id,
                    "candidate_revision": candidate_revision,
                })
    except Exception as exc:
        return {"success": False, "status": "owner_review_finalization_failed", "error_type": exc.__class__.__name__}, 503
    return {
        "success": True,
        "status": "owner_review_finalized",
        "mission_id": mission_id,
        "mission_status": "pr_ready",
        "execution_id": execution_id,
        "candidate_revision": candidate_revision,
    }, 200


def _not_execution_held_sql():
    return """
        not exists (
            select 1 from public.charlie_owner_execution_hold_events as hold_event
            where hold_event.mission_id = public.charlie_missions.mission_id
              and hold_event.event_type = 'hold_created'
              and not exists (
                  select 1 from public.charlie_owner_execution_hold_events as release_event
                  where release_event.event_type = 'hold_released'
                    and release_event.release_of_event_id = hold_event.event_id
              )
        )
        and public.charlie_missions.metadata_json->'portfolio_classification' is null
    """


def owner_execution_hold_status(mission_id, database_url=None, connect_factory=None, cursor=None):
    mission_id = _clean_text(mission_id, 90)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None and cursor is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    query = """
        select event_id, hold_id, mission_id, generation_identity, reason,
               owner_identity_hash, authorization_identity, created_at
        from public.charlie_owner_execution_hold_events as hold_event
        where mission_id = %(mission_id)s and event_type = 'hold_created'
          and not exists (
              select 1 from public.charlie_owner_execution_hold_events as release_event
              where release_event.event_type = 'hold_released'
                and release_event.release_of_event_id = hold_event.event_id
          )
        order by created_at desc limit 1
    """
    try:
        if cursor is not None:
            cursor.execute(query, {"mission_id": mission_id})
            row = cursor.fetchone()
        else:
            with _connect(database_url, connect_factory) as connection:
                with connection.cursor() as own_cursor:
                    own_cursor.execute(query, {"mission_id": mission_id})
                    row = own_cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "owner_execution_hold_read_failed", "error_type": exc.__class__.__name__}, 503
    if not row or len(row) < 8:
        return {"success": True, "status": "not_held", "mission_id": mission_id, "active": False}, 200
    return {
        "success": True, "status": "owner_execution_hold_active",
        "mission_id": mission_id, "active": True,
        "hold": {
            "event_id": row[0], "hold_id": row[1], "mission_id": row[2],
            "generation_identity": row[3], "reason": row[4],
            "owner_identity_hash": row[5], "authorization_identity": row[6],
            "created_at": row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7]),
        },
    }, 200


def _public_owner_execution_hold(hold):
    if not isinstance(hold, dict):
        return {}
    return {
        key: hold.get(key)
        for key in (
            "event_id", "hold_id", "mission_id", "generation_identity",
            "reason", "created_at",
        )
        if hold.get(key) not in (None, "")
    }


def create_owner_execution_hold(mission_id, generation_identity, reason, *, owner_principal, database_url=None, connect_factory=None):
    mission_id = _clean_text(mission_id, 90)
    generation_identity = _clean_text(generation_identity, 120)
    reason = _clean_text(reason, 200)
    owner_principal = _clean_text(owner_principal, 500)
    if not all((mission_id, generation_identity, reason, owner_principal)):
        return {"success": False, "status": "owner_execution_hold_identity_required"}, 400
    database_url = _owner_execution_hold_writer_database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    owner_hash = hashlib.sha256(owner_principal.encode("utf-8")).hexdigest()
    hold_id = "CHARLIE-HOLD-" + hashlib.sha256(
        f"{mission_id}|{generation_identity}|{reason}".encode("utf-8")
    ).hexdigest()[:24].upper()
    event_id = hold_id + "-CREATE"
    authorization_identity = (
        hashlib.md5(f"hold|{hold_id}|{owner_hash}".encode("utf-8")).hexdigest()
        + hashlib.md5(f"hold-proof|{hold_id}|{owner_hash}".encode("utf-8")).hexdigest()
    )
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%(mission_id)s, 0))",
                    {"mission_id": mission_id},
                )
                cursor.execute(
                    """
                    select status, coalesce(metadata_json, '{}'::jsonb),
                           not exists (
                               select 1 from public.charlie_missions as replacement
                               where replacement.metadata_json->'supersession'->>'status' = 'current_contract_replacement'
                                 and replacement.metadata_json->'supersession'->>'supersedes_mission_id' = %(mission_id)s
                                 and coalesce((replacement.metadata_json->'orchestration_binding'->>'validated')::boolean, false)
                                 and replacement.metadata_json->'orchestration_binding'->>'generation_identity'
                                     = replacement.metadata_json->'orchestration'->>'generation_identity'
                           ) as not_superseded
                    from public.charlie_missions
                    where mission_id=%(mission_id)s
                    """,
                    {"mission_id": mission_id},
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found"}, 404
                status, metadata = row[0], dict(row[1] or {})
                current_generation = _clean_text((metadata.get("orchestration") or {}).get("generation_identity"), 120)
                if status != "approved":
                    return {"success": False, "status": "owner_execution_hold_status_conflict", "mission_status": status}, 409
                disposition = metadata.get("portfolio_disposition") if isinstance(metadata.get("portfolio_disposition"), dict) else {}
                if str(disposition.get("status") or "").strip().lower() == "superseded" or row[2] is not True:
                    return {"success": False, "status": "owner_execution_hold_mission_superseded"}, 409
                if current_generation != generation_identity:
                    return {"success": False, "status": "owner_execution_hold_stale_generation", "current_generation": current_generation}, 409
                active, active_code = owner_execution_hold_status(mission_id, cursor=cursor)
                if active_code >= 400:
                    return active, active_code
                if active.get("active"):
                    existing = active["hold"]
                    if (
                        existing.get("hold_id") == hold_id
                        and existing.get("authorization_identity") == authorization_identity
                    ):
                        return {
                            "success": True,
                            "status": "owner_execution_hold_replayed",
                            "mission_id": mission_id,
                            "hold": _public_owner_execution_hold(existing),
                        }, 200
                    return {
                        "success": False,
                        "status": "owner_execution_hold_conflict",
                        "active_hold": _public_owner_execution_hold(existing),
                    }, 409
                cursor.execute(
                    """select public.append_charlie_owner_execution_hold(
                           %(event_id)s,%(hold_id)s,%(mission_id)s,%(generation)s,
                           %(reason)s,%(owner_hash)s,%(evidence)s::jsonb)""",
                    {
                        "event_id": event_id, "hold_id": hold_id, "mission_id": mission_id,
                        "generation": generation_identity, "reason": reason,
                        "owner_hash": owner_hash, "authorization": authorization_identity,
                        "evidence": json.dumps({"mission_status": "approved", "generation_identity": generation_identity}),
                    },
                )
    except Exception as exc:
        return {"success": False, "status": "owner_execution_hold_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "owner_execution_hold_created", "mission_id": mission_id,
            "hold": {"event_id": event_id, "hold_id": hold_id, "generation_identity": generation_identity, "reason": reason}}, 201


def release_owner_execution_hold(mission_id, generation_identity, hold_id, reason, *, owner_principal, database_url=None, connect_factory=None):
    mission_id = _clean_text(mission_id, 90)
    generation_identity = _clean_text(generation_identity, 120)
    hold_id = _clean_text(hold_id, 120)
    reason = _clean_text(reason, 200)
    owner_principal = _clean_text(owner_principal, 500)
    if not all((mission_id, generation_identity, hold_id, reason, owner_principal)):
        return {"success": False, "status": "owner_execution_hold_release_identity_required"}, 400
    database_url = _owner_execution_hold_writer_database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    owner_hash = hashlib.sha256(owner_principal.encode("utf-8")).hexdigest()
    release_event_id = hold_id + "-RELEASE"
    authorization_identity = (
        hashlib.md5(
            f"release|{hold_id}|{generation_identity}|{owner_hash}".encode("utf-8")
        ).hexdigest()
        + hashlib.md5(
            f"release-proof|{hold_id}|{generation_identity}|{owner_hash}".encode("utf-8")
        ).hexdigest()
    )
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%(mission_id)s, 0))",
                    {"mission_id": mission_id},
                )
                cursor.execute(
                    "select status,coalesce(metadata_json,'{}'::jsonb) from public.charlie_missions where mission_id=%(mission_id)s",
                    {"mission_id": mission_id},
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found"}, 404
                current_generation = _clean_text((dict(row[1] or {}).get("orchestration") or {}).get("generation_identity"), 120)
                if current_generation != generation_identity:
                    return {"success": False, "status": "owner_execution_hold_stale_generation", "current_generation": current_generation}, 409
                cursor.execute(
                    "select event_id,generation_identity from public.charlie_owner_execution_hold_events where hold_id=%(hold_id)s and mission_id=%(mission_id)s and event_type='hold_created'",
                    {"hold_id": hold_id, "mission_id": mission_id},
                )
                hold = cursor.fetchone()
                if not hold or hold[1] != generation_identity:
                    return {"success": False, "status": "owner_execution_hold_not_found"}, 404
                cursor.execute(
                    "select event_id, reason, authorization_identity from public.charlie_owner_execution_hold_events where release_of_event_id=%(event_id)s",
                    {"event_id": hold[0]},
                )
                replay = cursor.fetchone()
                if replay:
                    if replay[1] != reason or replay[2] != authorization_identity:
                        return {"success": False, "status": "owner_execution_hold_release_conflict"}, 409
                    return {"success": True, "status": "owner_execution_hold_release_replayed", "mission_id": mission_id, "release_event_id": replay[0]}, 200
                cursor.execute(
                    """select public.append_charlie_owner_execution_hold_release(
                           %(event_id)s,%(hold_id)s,%(mission_id)s,%(generation)s,
                           %(reason)s,%(owner_hash)s,%(release_of)s,%(evidence)s::jsonb)""",
                    {
                        "event_id": release_event_id, "hold_id": hold_id, "mission_id": mission_id,
                        "generation": generation_identity, "reason": reason, "owner_hash": owner_hash,
                        "authorization": authorization_identity, "release_of": hold[0],
                        "evidence": json.dumps({"explicit_owner_release": True, "generation_identity": generation_identity}),
                    },
                )
    except Exception as exc:
        return {"success": False, "status": "owner_execution_hold_release_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "owner_execution_hold_released", "mission_id": mission_id, "release_event_id": release_event_id}, 201


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


def append_mission_admission_event(
    mission_id,
    admission,
    *,
    authenticated_principal,
    database_url=None,
    connect_factory=None,
):
    """Append one immutable admission event and project it on the mission row."""
    mission_id = _clean_text(mission_id, 90)
    principal = _clean_text(authenticated_principal, 200)
    admission = admission if isinstance(admission, dict) else {}
    required = {
        "receipt_id",
        "content_sha256",
        "mission_id",
        "root_mission_id",
        "generation",
        "base_sha",
        "head_sha",
        "authority_key_sha256",
        "latest_correction_digest",
        "collision_snapshot_sha256",
    }
    optional = {"signed_receipt"}
    if (
        not mission_id
        or not principal
        or not required.issubset(admission)
        or set(admission) - required - optional
        or not str(admission.get("receipt_id") or "").startswith("MAR-")
        or not re.fullmatch(r"[0-9a-f]{64}", str(admission.get("content_sha256") or ""))
        or not re.fullmatch(r"[0-9a-f]{40}", str(admission.get("base_sha") or ""))
        or not re.fullmatch(r"[0-9a-f]{40}", str(admission.get("head_sha") or ""))
        or not re.fullmatch(r"[0-9a-f]{64}", str(admission.get("authority_key_sha256") or ""))
        or not re.fullmatch(r"[0-9a-f]{64}", str(admission.get("latest_correction_digest") or ""))
        or not re.fullmatch(r"[0-9a-f]{64}", str(admission.get("collision_snapshot_sha256") or ""))
        or admission.get("mission_id") != mission_id
        or (
            "signed_receipt" in admission
            and not isinstance(admission.get("signed_receipt"), dict)
        )
        or not _clean_text(admission.get("root_mission_id"), 90)
        or not _clean_text(admission.get("generation"), 200)
    ):
        return {"success": False, "status": "invalid_mission_admission_event"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    projection = {
        **admission,
        "status": "valid",
        "recorded_by": principal,
    }
    event = _mission_admission_operational_event(
        mission_id, "mission_admission_recorded", projection, principal
    )
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select coalesce(metadata_json,'{}'::jsonb)
                       from public.charlie_missions
                       where mission_id=%(mission_id)s for update""",
                    {"mission_id": mission_id},
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                metadata = dict(row[0] or {})
                if admission["root_mission_id"] != _mission_root_identity(
                    mission_id, metadata
                ):
                    return {
                        "success": False,
                        "status": "mission_admission_root_mismatch",
                        "mission_id": mission_id,
                    }, 409
                current = metadata.get("mission_admission")
                if isinstance(current, dict) and current.get("status") == "valid":
                    if current.get("receipt_id") == projection["receipt_id"]:
                        return {
                            "success": True,
                            "status": "exact_replay",
                            "mission_id": mission_id,
                            "admission": current,
                        }, 200
                    return {
                        "success": False,
                        "status": "mission_admission_conflict",
                        "mission_id": mission_id,
                    }, 409
                created = _insert_operational_event(cursor, event)
                if not created:
                    stored = _load_operational_event(cursor, event["idempotency_key"])
                    if not _same_operational_event(stored, event):
                        return {
                            "success": False,
                            "status": "mission_admission_event_replay_conflict",
                            "mission_id": mission_id,
                        }, 409
                metadata["mission_admission"] = projection
                cursor.execute(
                    """update public.charlie_missions
                       set metadata_json=%(metadata)s::jsonb,updated_at=now()
                       where mission_id=%(mission_id)s""",
                    {
                        "metadata": json.dumps(metadata, sort_keys=True),
                        "mission_id": mission_id,
                    },
                )
    except Exception as exc:
        return {
            "success": False,
            "status": "mission_admission_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    return {
        "success": True,
        "status": "mission_admission_recorded",
        "mission_id": mission_id,
        "event_id": event["event_id"],
        "admission": projection,
    }, 201


def bind_external_supervisor_candidate(
    mission_id,
    binding,
    *,
    authenticated_principal,
    database_url=None,
    connect_factory=None,
):
    """Bind one externally supervised PR candidate without exposing raw storage."""
    mission_id = _clean_text(mission_id, 90)
    principal = _clean_text(authenticated_principal, 200)
    binding = binding if isinstance(binding, dict) else {}
    required = {
        "pr_number", "branch_name", "base_sha", "head_sha",
        "candidate_diff_sha256", "changed_files", "generation",
        "allowed_files", "forbidden_files", "allowed_effects",
        "forbidden_effects", "required_tests", "operational_acceptance",
    }
    sha40 = lambda value: bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "")))
    sha64 = lambda value: bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))
    paths = sorted({_clean_text(item, 500) for item in binding.get("changed_files") or [] if _clean_text(item, 500)})
    allowed = sorted({_clean_text(item, 500) for item in binding.get("allowed_files") or [] if _clean_text(item, 500)})
    if (not mission_id or not principal or set(binding) != required
            or not isinstance(binding.get("pr_number"), int) or binding["pr_number"] <= 0
            or not _clean_text(binding.get("branch_name"), 240)
            or not sha40(binding.get("base_sha")) or not sha40(binding.get("head_sha"))
            or not sha64(binding.get("candidate_diff_sha256")) or paths != allowed
            or not paths or not _clean_text(binding.get("generation"), 200)
            or not all(isinstance(binding.get(key), list) for key in (
                "forbidden_files", "allowed_effects", "forbidden_effects",
                "required_tests", "operational_acceptance"))):
        return {"success": False, "status": "external_candidate_binding_invalid"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    packet = {
        "pr_number": binding["pr_number"], "branch_name": binding["branch_name"],
        "candidate_revision": binding["head_sha"],
        "candidate_diff_sha256": binding["candidate_diff_sha256"],
        "changed_files": paths,
    }
    contract = {
        "generation": binding["generation"], "branch": binding["branch_name"],
        "base_sha": binding["base_sha"], "allowed_files": allowed,
        **{key: sorted(binding[key]) for key in (
            "forbidden_files", "allowed_effects", "forbidden_effects",
            "required_tests", "operational_acceptance")},
    }
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select status,coalesce(metadata_json,'{}'::jsonb)
                    from public.charlie_missions where mission_id=%(mission_id)s for update""",
                    {"mission_id": mission_id})
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found"}, 404
                if row[0] not in {"approved", "in_progress", "pr_ready"}:
                    return {"success": False, "status": "external_candidate_binding_state_invalid"}, 409
                metadata = dict(row[1] or {})
                existing = metadata.get("review_packet")
                if isinstance(existing, dict) and existing:
                    if existing == packet and metadata.get("mission_admission_contract") == contract:
                        return {"success": True, "status": "exact_replay", "mission_id": mission_id}, 200
                    current_admission = metadata.get("mission_admission") \
                        if isinstance(metadata.get("mission_admission"), dict) else {}
                    if current_admission.get("status") not in {"revoked", "invalidated", "consumed"}:
                        return {"success": False, "status": "external_candidate_binding_conflict"}, 409
                family = dict(metadata.get("mission_family") or {})
                family["root_mission_id"] = family.get("root_mission_id") or mission_id
                family["generation"] = binding["generation"]
                metadata.update({"review_packet": packet, "mission_admission_contract": contract,
                                 "mission_family": family, "external_supervisor": {
                                     "principal": principal, "transport": "hermes_cursor_cloud_v1"}})
                cursor.execute("""update public.charlie_missions set metadata_json=%(metadata)s::jsonb,
                    updated_at=now() where mission_id=%(mission_id)s""",
                    {"metadata": json.dumps(metadata, sort_keys=True), "mission_id": mission_id})
                _insert_event(cursor, mission_id, "workflow_updated",
                    "Externally supervised exact PR candidate bound.",
                    {"pr_number": binding["pr_number"], "head_sha": binding["head_sha"],
                     "generation": binding["generation"], "recorded_by": principal})
    except Exception as exc:
        return {"success": False, "status": "external_candidate_binding_failed",
                "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "external_candidate_bound",
            "mission_id": mission_id, "pr_number": binding["pr_number"],
            "head_sha": binding["head_sha"]}, 201


def record_external_supervisor_state(mission_id, state, *, authenticated_principal,
                                     database_url=None, connect_factory=None):
    """Persist bounded Hermes linkage/progress in the canonical mission row."""
    mission_id = _clean_text(mission_id, 90)
    principal = _clean_text(authenticated_principal, 200)
    state = state if isinstance(state, dict) else {}
    allowed = {"idempotency_key", "generation", "cursor_agent_id", "cursor_run_id",
               "slack_channel_id", "slack_thread_ts", "branch", "pr_number",
               "head_sha", "agent_state", "run_state", "stalled", "event",
               "failed_attempts", "checks", "independent_review", "branches",
               "ci_stalled", "stalled_checks"}
    if not mission_id or not principal or not state or set(state) - allowed:
        return {"success": False, "status": "external_supervisor_state_invalid"}, 400
    key = _clean_text(state.get("idempotency_key"), 300)
    if key and not key.startswith(mission_id + ":"):
        return {"success": False, "status": "external_supervisor_identity_conflict"}, 409
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select coalesce(metadata_json,'{}'::jsonb) from public.charlie_missions
                    where mission_id=%(mission_id)s for update""", {"mission_id": mission_id})
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found"}, 404
                metadata = dict(row[0] or {})
                current = dict(metadata.get("external_supervisor_state") or {})
                if key and current.get("idempotency_key") == key and current.get("cursor_agent_id"):
                    if state.get("cursor_agent_id") and state["cursor_agent_id"] != current.get("cursor_agent_id"):
                        return {"success": False, "status": "external_supervisor_dispatch_conflict"}, 409
                merged = {**current, **state, "recorded_by": principal,
                          "updated_at": datetime.now(timezone.utc).isoformat()}
                metadata["external_supervisor_state"] = merged
                cursor.execute("""update public.charlie_missions set metadata_json=%(metadata)s::jsonb,
                    updated_at=now() where mission_id=%(mission_id)s""",
                    {"metadata": json.dumps(metadata, sort_keys=True), "mission_id": mission_id})
                _insert_event(cursor, mission_id, "workflow_updated", "External supervisor state recorded.",
                              {key: merged.get(key) for key in ("cursor_agent_id", "cursor_run_id", "pr_number", "head_sha", "event")})
    except Exception as exc:
        return {"success": False, "status": "external_supervisor_state_write_failed",
                "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "external_supervisor_state_recorded",
            "mission_id": mission_id, "dispatch": merged}, 201


def read_external_supervisor_state(idempotency_key="", *, database_url=None, connect_factory=None):
    key = _clean_text(idempotency_key, 300)
    database_url = _database_url(database_url)
    if not key or (not database_url and connect_factory is None):
        return {"success": False, "status": "external_supervisor_identity_required"}, 400
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select mission_id,metadata_json->'external_supervisor_state'
                    from public.charlie_missions where metadata_json->'external_supervisor_state'->>'idempotency_key'=%(key)s limit 1""",
                    {"key": key})
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "external_supervisor_state_read_failed",
                "error_type": exc.__class__.__name__}, 503
    return ({"success": True, "status": "ok", "mission_id": row[0], "dispatch": row[1] or {}}, 200) \
        if row else ({"success": True, "status": "not_found", "dispatch": {}}, 200)


def invalidate_mission_admission_for_owner_correction(
    mission_id,
    new_generation,
    *,
    owner_authentication,
    correction_payload,
    database_url=None,
    connect_factory=None,
):
    """Record an authenticated owner correction and invalidate admission atomically."""
    mission_id = _clean_text(mission_id, 90)
    new_generation = _clean_text(new_generation, 200)
    authentication = owner_authentication if isinstance(owner_authentication, dict) else {}
    if (
        not mission_id
        or not new_generation
        or set(authentication) != {
            "authenticated",
            "principal_type",
            "principal_id",
        }
        or authentication.get("authenticated") is not True
        or authentication.get("principal_type") != "owner_admin"
        or not _clean_text(authentication.get("principal_id"), 200)
    ):
        return {"success": False, "status": "authenticated_owner_correction_required"}, 403
    principal = _clean_text(authentication["principal_id"], 200)
    try:
        correction = build_mission_control_event(
            mission_id,
            correction_payload,
            recorded_by=principal,
        )
    except ValueError as exc:
        return {"success": False, "status": str(exc)}, 400
    if correction.get("event_type") != "owner_correction_recorded":
        return {"success": False, "status": "owner_correction_event_required"}, 400
    correction_digest = hashlib.sha256(json.dumps(
        {
            key: value
            for key, value in correction.items()
            if key != "recorded_at"
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select coalesce(metadata_json,'{}'::jsonb)
                       from public.charlie_missions
                       where mission_id=%(mission_id)s for update""",
                    {"mission_id": mission_id},
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                metadata = dict(row[0] or {})
                current = metadata.get("mission_admission")
                if (
                    isinstance(current, dict)
                    and current.get("status") == "invalidated"
                    and current.get("invalidated_by_correction_event_id")
                    == correction["event_id"]
                    and current.get("correction_digest") == correction_digest
                    and current.get("replacement_generation") == new_generation
                ):
                    return {
                        "success": True,
                        "status": "exact_replay",
                        "mission_id": mission_id,
                        "correction_event_id": correction["event_id"],
                        "correction_digest": correction_digest,
                        "admission": current,
                    }, 200
                if not isinstance(current, dict) or current.get("status") != "valid":
                    return {
                        "success": False,
                        "status": "current_mission_admission_missing",
                        "mission_id": mission_id,
                    }, 409
                cursor.execute(
                    """insert into public.charlie_mission_events
                       (event_id,mission_id,event_type,notes,recorded_by,
                        metadata_json,created_at)
                       values (%(event_id)s,%(mission_id)s,
                               'owner_correction_recorded',%(notes)s,
                               %(principal)s,%(metadata)s::jsonb,%(created_at)s)
                       on conflict (event_id) do nothing returning event_id""",
                    {
                        "event_id": correction["event_id"],
                        "mission_id": mission_id,
                        "notes": correction["summary"],
                        "principal": principal,
                        "metadata": json.dumps(correction, sort_keys=True),
                        "created_at": correction["recorded_at"],
                    },
                )
                correction_created = cursor.fetchone() is not None
                if not correction_created:
                    cursor.execute(
                        """select coalesce(metadata_json,'{}'::jsonb)
                           from public.charlie_mission_events
                           where event_id=%(event_id)s
                             and mission_id=%(mission_id)s
                             and event_type='owner_correction_recorded'
                             and recorded_by=%(principal)s
                           limit 1""",
                        {
                            "event_id": correction["event_id"],
                            "mission_id": mission_id,
                            "principal": principal,
                        },
                    )
                    stored = cursor.fetchone()
                    stored_event = (
                        stored[0]
                        if stored and isinstance(stored[0], dict)
                        else {}
                    )
                    if not canonical_event_equal(stored_event, correction):
                        return {
                            "success": False,
                            "status": "owner_correction_replay_conflict",
                            "mission_id": mission_id,
                        }, 409
                if current.get("generation") == new_generation:
                    return {
                        "success": True,
                        "status": (
                            "owner_correction_recorded"
                            if correction_created
                            else "exact_replay"
                        ),
                        "mission_id": mission_id,
                        "correction_event_id": correction["event_id"],
                        "correction_digest": correction_digest,
                        "admission": current,
                    }, 201 if correction_created else 200
                invalidated = {
                    **current,
                    "status": "invalidated",
                    "invalidated_by_correction_event_id": correction["event_id"],
                    "correction_digest": correction_digest,
                    "replacement_generation": new_generation,
                }
                event = _mission_admission_operational_event(
                    mission_id,
                    "mission_admission_invalidated",
                    invalidated,
                    principal,
                )
                created = _insert_operational_event(cursor, event)
                if not created:
                    stored = _load_operational_event(cursor, event["idempotency_key"])
                    if not _same_operational_event(stored, event):
                        return {
                            "success": False,
                            "status": "mission_admission_event_replay_conflict",
                            "mission_id": mission_id,
                        }, 409
                metadata["mission_admission"] = invalidated
                cursor.execute(
                    """update public.charlie_missions
                       set metadata_json=%(metadata)s::jsonb,updated_at=now()
                       where mission_id=%(mission_id)s""",
                    {
                        "metadata": json.dumps(metadata, sort_keys=True),
                        "mission_id": mission_id,
                    },
                )
    except Exception as exc:
        return {
            "success": False,
            "status": "mission_admission_invalidation_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    return {
        "success": True,
        "status": "mission_admission_invalidated",
        "mission_id": mission_id,
        "event_id": event["event_id"],
        "correction_event_id": correction["event_id"],
        "correction_digest": correction_digest,
        "admission": invalidated,
    }, 201


def read_mission_admission_events(
    mission_id,
    *,
    limit=100,
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        parsed_limit = max(1, min(int(limit or 100), 1000))
    except (TypeError, ValueError):
        return {"success": False, "status": "invalid_limit"}, 400
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select event_id,event_type,occurred_at,recorded_at,
                              payload_json,provenance_json,actor_type,actor_id
                       from public.operational_events
                       where domain='missions'
                         and aggregate_type='charlie_mission'
                         and aggregate_id=%(mission_id)s
                         and event_type in (
                             'mission_admission_recorded',
                             'mission_admission_invalidated',
                             'mission_admission_consumed',
                             'mission_admission_revoked'
                         )
                       order by occurred_at,recorded_at,event_id
                       limit %(limit)s""",
                    {"mission_id": mission_id, "limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "status": "mission_admission_read_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    events = [
        {
            "event_id": row[0],
            "event_type": row[1],
            "occurred_at": _iso(row[2]),
            "recorded_at": _iso(row[3]),
            "payload": row[4] if isinstance(row[4], dict) else {},
            "provenance": row[5] if isinstance(row[5], dict) else {},
            "actor_type": row[6],
            "actor_id": row[7],
        }
        for row in rows
    ]
    return {
        "success": True,
        "status": "mission_admission_events_ready",
        "mission_id": mission_id,
        "events": events,
    }, 200


def consume_mission_admission(
    mission_id,
    receipt_id,
    *,
    authenticated_principal,
    database_url=None,
    connect_factory=None,
):
    return _transition_mission_admission(
        mission_id,
        receipt_id,
        "consumed",
        authenticated_principal=authenticated_principal,
        database_url=database_url,
        connect_factory=connect_factory,
    )


def revoke_mission_admission(
    mission_id,
    receipt_id,
    *,
    owner_authentication,
    database_url=None,
    connect_factory=None,
):
    authentication = owner_authentication if isinstance(owner_authentication, dict) else {}
    if (
        set(authentication) != {"authenticated", "principal_type", "principal_id"}
        or authentication.get("authenticated") is not True
        or authentication.get("principal_type") != "owner_admin"
        or not _clean_text(authentication.get("principal_id"), 200)
    ):
        return {"success": False, "status": "authenticated_owner_revocation_required"}, 403
    return _transition_mission_admission(
        mission_id,
        receipt_id,
        "revoked",
        authenticated_principal=authentication["principal_id"],
        database_url=database_url,
        connect_factory=connect_factory,
    )


def read_current_mission_admission_authority(
    mission_id,
    *,
    database_url=None,
    connect_factory=None,
):
    """Read current admission, owner correction, and active collision claims."""
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
                    """select status,coalesce(metadata_json,'{}'::jsonb),updated_at
                       from public.charlie_missions
                       where mission_id=%(mission_id)s limit 1""",
                    {"mission_id": mission_id},
                )
                mission_row = cursor.fetchone()
                if not mission_row:
                    return {
                        "success": False,
                        "status": "not_found",
                        "mission_id": mission_id,
                    }, 404
                metadata = dict(mission_row[1] or {})
                cursor.execute(
                    """select event_id,coalesce(metadata_json,'{}'::jsonb),
                              recorded_by
                       from public.charlie_mission_events
                       where mission_id=%(mission_id)s
                         and event_type='owner_correction_recorded'
                       order by created_at desc,event_id desc limit 1""",
                    {"mission_id": mission_id},
                )
                correction_row = cursor.fetchone()
                cursor.execute(
                    """select mission_id,status,coalesce(metadata_json,'{}'::jsonb),
                              updated_at
                       from public.charlie_missions
                       where status = any(%(statuses)s)
                       order by mission_id""",
                    {"statuses": sorted(OPEN_DUPLICATE_STATUSES)},
                )
                claim_rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "status": "mission_admission_authority_read_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    admission = (
        dict(metadata.get("mission_admission") or {})
        if isinstance(metadata.get("mission_admission"), dict)
        else {}
    )
    correction_event = (
        dict(correction_row[1] or {})
        if correction_row and isinstance(correction_row[1], dict)
        else {}
    )
    if not correction_event:
        return {
            "success": False,
            "status": "canonical_owner_correction_unavailable",
            "mission_id": mission_id,
        }, 409
    correction_valid, _correction_reason = validate_mission_control_event(
        correction_event
    )
    if (
        not correction_valid
        or correction_event.get("mission_id") != mission_id
        or correction_event.get("event_type") != "owner_correction_recorded"
        or correction_event.get("recorded_by") != correction_row[2]
    ):
        return {
            "success": False,
            "status": "canonical_owner_correction_invalid",
            "mission_id": mission_id,
        }, 409
    correction_digest = hashlib.sha256(json.dumps(
        {
            key: value
            for key, value in correction_event.items()
            if key != "recorded_at"
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    active_claims = _mission_admission_active_claims(claim_rows)
    active_claim_ids = {claim["mission_id"] for claim in active_claims}
    collision_observed_at = max(
        [
            _iso(row[3])
            for row in claim_rows
            if (
                len(row) > 3
                and row[3] is not None
                and str(row[0]) in active_claim_ids
            )
        ]
        or [str(correction_event.get("recorded_at") or _iso(mission_row[2]))]
    )
    collision_observed_at = collision_observed_at.replace("+00:00", "Z")
    collision_digest = hashlib.sha256(json.dumps(
        {
            "captured_at": collision_observed_at,
            "active_claims": active_claims,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "success": True,
        "status": "mission_admission_authority_ready",
        "mission_id": mission_id,
        "root_mission_id": _mission_root_identity(mission_id, metadata),
        "mission_status": mission_row[0],
        "admission": admission,
        "latest_owner_correction_event_id": (
            correction_row[0] if correction_row else ""
        ),
        "latest_correction_digest": correction_digest,
        "active_claims": active_claims,
        "collision_observed_at": collision_observed_at,
        "collision_snapshot_sha256": collision_digest,
    }, 200


def _transition_mission_admission(
    mission_id,
    receipt_id,
    target_status,
    *,
    authenticated_principal,
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean_text(mission_id, 90)
    receipt_id = _clean_text(receipt_id, 80)
    principal = _clean_text(authenticated_principal, 200)
    if (
        not mission_id
        or not re.fullmatch(r"MAR-[0-9A-F]{64}", receipt_id)
        or target_status not in {"consumed", "revoked"}
        or not principal
    ):
        return {"success": False, "status": "mission_admission_transition_invalid"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select coalesce(metadata_json,'{}'::jsonb)
                       from public.charlie_missions
                       where mission_id=%(mission_id)s for update""",
                    {"mission_id": mission_id},
                )
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found"}, 404
                metadata = dict(row[0] or {})
                current = (
                    dict(metadata.get("mission_admission") or {})
                    if isinstance(metadata.get("mission_admission"), dict)
                    else {}
                )
                if current.get("receipt_id") != receipt_id:
                    return {
                        "success": False,
                        "status": "mission_admission_receipt_mismatch",
                    }, 409
                if current.get("status") == target_status:
                    return {
                        "success": True,
                        "status": "exact_replay",
                        "mission_id": mission_id,
                        "admission": current,
                    }, 200
                if current.get("status") != "valid":
                    return {
                        "success": False,
                        "status": "mission_admission_not_active",
                        "current_status": current.get("status"),
                    }, 409
                transitioned = {
                    **current,
                    "status": target_status,
                    f"{target_status}_by": principal,
                }
                event = _mission_admission_operational_event(
                    mission_id,
                    f"mission_admission_{target_status}",
                    transitioned,
                    principal,
                )
                if not _insert_operational_event(cursor, event):
                    stored = _load_operational_event(
                        cursor, event["idempotency_key"]
                    )
                    if not _same_operational_event(stored, event):
                        return {
                            "success": False,
                            "status": "mission_admission_event_replay_conflict",
                        }, 409
                metadata["mission_admission"] = transitioned
                cursor.execute(
                    """update public.charlie_missions
                       set metadata_json=%(metadata)s::jsonb,updated_at=now()
                       where mission_id=%(mission_id)s""",
                    {
                        "metadata": json.dumps(metadata, sort_keys=True),
                        "mission_id": mission_id,
                    },
                )
    except Exception as exc:
        return {
            "success": False,
            "status": "mission_admission_transition_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    return {
        "success": True,
        "status": f"mission_admission_{target_status}",
        "mission_id": mission_id,
        "event_id": event["event_id"],
        "admission": transitioned,
    }, 201


def _mission_admission_active_claims(rows):
    claims = []
    for mission_id, status, raw_metadata, _updated_at in rows or []:
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        review = (
            metadata.get("review_packet")
            if isinstance(metadata.get("review_packet"), dict)
            else {}
        )
        paths = sorted({
            str(path or "").strip().replace("\\", "/")
            for path in review.get("changed_files", [])
            if str(path or "").strip()
        })
        effects = sorted({
            str(effect or "").strip()
            for effect in (
                list(review.get("protected_operations") or [])
                + list(metadata.get("protected_operations") or [])
            )
            if str(effect or "").strip()
        })
        lease = (
            metadata.get("execution_lease")
            if isinstance(metadata.get("execution_lease"), dict)
            else {}
        )
        if lease:
            effects = sorted(set(effects + ["execution_lease"]))
        if paths or effects or lease:
            claims.append({
                "mission_id": str(mission_id),
                "status": str(status),
                "paths": paths,
                "effects": effects,
                "lease_id": str(lease.get("lease_id") or ""),
            })
    return claims


def update_mission_vault(
    mission_id,
    vault_metadata,
    status="",
    owner_decision="",
    notes="Mission vault updated.",
    database_url=None,
    connect_factory=None,
    expected_status="",
):
    mission_id = _clean_text(mission_id, 90)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if not isinstance(vault_metadata, dict):
        return {"success": False, "status": "mission_vault_metadata_required"}, 400
    status = _clean_text(status, 40)
    expected_status = _clean_text(expected_status, 40)
    if status and status not in MISSION_STATUSES:
        return {"success": False, "status": "invalid_mission_status", "allowed_statuses": sorted(MISSION_STATUSES)}, 400
    if expected_status and expected_status not in MISSION_STATUSES:
        return {"success": False, "status": "invalid_expected_mission_status", "allowed_statuses": sorted(MISSION_STATUSES)}, 400

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
    where = "mission_id = %(mission_id)s"
    if expected_status:
        where += " and status = %(expected_status)s"
        params["expected_status"] = expected_status
    if status:
        set_lines.insert(0, "status = %(status)s")
        params["status"] = status
    where += f" and {_not_execution_held_sql()}"
    if owner_decision:
        set_lines.insert(0, "owner_decision = %(owner_decision)s")
        params["owner_decision"] = _clean_text(owner_decision, 1000)

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    with mission_hold_lock as (
                        select pg_advisory_xact_lock(hashtextextended(%(mission_id)s, 0))
                    )
                    update public.charlie_missions
                    set {", ".join(set_lines)}
                    from mission_hold_lock
                    where {where}
                    returning mission_id
                    """,
                    params,
                )
                rows = cursor.fetchall()
                if not rows:
                    held, held_status = owner_execution_hold_status(mission_id, cursor=cursor)
                    if held_status < 400 and held.get("active"):
                        return {
                            "success": False, "configured": True,
                            "status": "owner_execution_hold_active",
                            "mission_id": mission_id,
                            "hold": _public_owner_execution_hold(held.get("hold")),
                        }, 423
                    if expected_status:
                        return {
                            "success": False, "configured": True, "status": "status_claim_lost",
                            "mission_id": mission_id, "expected_status": expected_status,
                        }, 409
                    return {"success": False, "configured": True, "status": "not_found", "mission_id": mission_id}, 404
                event_type = "status_changed" if status and expected_status else "vault_updated"
                _insert_event(cursor, mission_id, event_type, notes, {
                    "status": status,
                    "expected_status": expected_status,
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


def consume_final_agent_artifact(
    mission_id,
    agent,
    execution_id,
    attempt,
    artifact,
    artifact_sha256,
    transition_target="",
    transition_status="complete",
    database_url=None,
    connect_factory=None,
):
    """Atomically persist one valid stage artifact before changing workflow state."""
    mission_id = _clean_text(mission_id, 90)
    agent = _clean_text(agent, 40).lower()
    execution_id = _clean_text(execution_id, 160)
    artifact_sha256 = _clean_text(artifact_sha256, 64).lower()
    if not mission_id or not agent or not execution_id or not artifact_sha256:
        return {"success": False, "status": "artifact_identity_required"}, 400
    if not isinstance(artifact, dict):
        return {"success": False, "status": "final_artifact_required"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    consumed_at = datetime.now(timezone.utc).isoformat()
    attempt = int(attempt or 1)
    transition_target = _clean_text(transition_target, 40).lower()
    transition_status = _clean_text(transition_status, 40).lower() or "complete"
    protected_agents = {"risk_agent", "architect", "builder", "tester", "qa_red_team", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "visual_qa_reviewer", "reviewer", "publisher"}
    artifact = dict(artifact)
    lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
    source_revision = _clean_text(artifact.get("source_revision") or artifact.get("source_commit") or lineage.get("source_commit"), 40).lower()
    candidate_revision = _clean_text(artifact.get("candidate_revision") or source_revision, 40).lower()
    expected_revision = _clean_text(artifact.get("expected_revision") or candidate_revision, 40).lower()
    tested_revision = _clean_text(artifact.get("tested_revision"), 40).lower()
    candidate_fingerprint = _clean_text(artifact.get("candidate_fingerprint") or lineage.get("candidate_fingerprint"), 128)
    input_artifact_ids = [_clean_text(value, 500) for value in (artifact.get("input_artifact_ids") or []) if _clean_text(value, 500)]
    parent_artifact_id = _clean_text(artifact.get("parent_artifact_id"), 500)
    if parent_artifact_id and parent_artifact_id not in input_artifact_ids:
        input_artifact_ids.insert(0, parent_artifact_id)
    sha_pattern = re.compile(r"^[0-9a-f]{40}$")
    missing_binding = []
    if agent in protected_agents:
        if not sha_pattern.fullmatch(source_revision): missing_binding.append("source_revision")
        if not sha_pattern.fullmatch(candidate_revision): missing_binding.append("candidate_revision")
        if not sha_pattern.fullmatch(expected_revision): missing_binding.append("expected_revision")
        if agent in {"tester", "qa_red_team", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "visual_qa_reviewer", "reviewer", "publisher"} and not sha_pattern.fullmatch(tested_revision): missing_binding.append("tested_revision")
        if not candidate_fingerprint: missing_binding.append("candidate_fingerprint")
        if agent not in {"risk_agent", "architect"} and not input_artifact_ids: missing_binding.append("input_artifact_ids")
        compared = [value for value in (source_revision, candidate_revision, expected_revision, tested_revision) if value]
        if compared and any(value != compared[0] for value in compared[1:]): missing_binding.append("revision_mismatch")
    if missing_binding:
        return record_final_artifact_rejection(
            mission_id,
            agent,
            execution_id,
            attempt,
            artifact,
            artifact_sha256,
            sorted(set(missing_binding)),
            database_url=database_url,
            connect_factory=connect_factory,
        )
    identity = f"{mission_id}:{execution_id}:{agent}:{attempt}:{candidate_revision}:{candidate_fingerprint}:{artifact_sha256}"
    artifact.update({"mission_id": mission_id, "execution_id": execution_id, "producing_stage": agent, "agent": agent, "attempt": attempt, "source_revision": source_revision, "source_commit": source_revision, "candidate_revision": candidate_revision, "expected_revision": expected_revision, "candidate_fingerprint": candidate_fingerprint, "parent_artifact_id": parent_artifact_id, "input_artifact_ids": input_artifact_ids, "completed_at": _clean_text(artifact.get("completed_at"), 80) or consumed_at, "created_at": _clean_text(artifact.get("created_at") or lineage.get("created_at"), 80) or consumed_at, "artifact_identity": identity})
    if tested_revision:
        artifact["tested_revision"] = tested_revision
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select metadata_json from public.charlie_missions
                       where mission_id = %(mission_id)s for update""",
                    {"mission_id": mission_id},
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                if "portfolio_classification" in dict(rows[0][0] or {}):
                    return {"success": False, "status": "portfolio_classified_mission_ineligible"}, 409
                metadata = dict(rows[0][0] or {})
                ingestion = dict(metadata.get("final_artifact_ingestion") or {})
                claims = list(ingestion.get("claims") or [])
                existing = next((item for item in claims if isinstance(item, dict) and item.get("identity") == identity), None)
                if existing:
                    return {
                        "success": True,
                        "status": "final_artifact_already_consumed",
                        "mission_id": mission_id,
                        "agent": agent,
                        "claim": existing,
                    }, 200
                workflow = list(metadata.get("agent_workflow") or [])
                first_incomplete = next(
                    (str(item.get("agent") or "").lower() for item in workflow
                     if isinstance(item, dict) and str(item.get("status") or "").lower() != "complete"),
                    "",
                )
                artifact_stage = next(
                    (item for item in workflow if isinstance(item, dict) and str(item.get("agent") or "").lower() == agent),
                    {},
                )
                artifact_stage_status = str(artifact_stage.get("status") or "").lower()
                stage_already_complete = artifact_stage_status == "complete"
                stage_is_active = artifact_stage_status == "active"
                if first_incomplete != agent and not stage_already_complete and not stage_is_active:
                    return {
                        "success": False,
                        "status": "final_artifact_stage_mismatch",
                        "expected_agent": first_incomplete,
                        "artifact_agent": agent,
                    }, 409
                next_agent = ""
                seen = False
                updated_workflow = []
                target_seen = False
                for item in workflow:
                    current = dict(item) if isinstance(item, dict) else item
                    if not isinstance(current, dict):
                        updated_workflow.append(current)
                        continue
                    current_agent = str(current.get("agent") or "").lower()
                    if transition_target:
                        if current_agent == transition_target:
                            current.update({"status": "active", "completed_at": None})
                            next_agent = transition_target
                            target_seen = True
                        elif target_seen:
                            current.update({"status": "pending", "completed_at": None})
                    elif current_agent == agent:
                        current.update({"status": transition_status, "findings": _clean_text(artifact.get("summary"), 1200), "completed_at": consumed_at})
                        seen = True
                    else:
                        if str(current.get("status") or "").lower() == "active": current["status"] = "pending"
                    if (not transition_target and transition_status == "complete" and current_agent != agent and seen and not next_agent and str(current.get("status") or "").lower() != "complete"):
                        current["status"] = "active"
                        next_agent = current_agent
                    updated_workflow.append(current)
                claim = {
                    "identity": identity,
                    "execution_id": execution_id,
                    "agent": agent,
                    "attempt": int(attempt or 1),
                    "sha256": artifact_sha256,
                    "candidate_revision": candidate_revision,
                    "candidate_fingerprint": candidate_fingerprint,
                    "parent_artifact_id": parent_artifact_id,
                    "input_artifact_ids": input_artifact_ids,
                    "consumed_at": consumed_at,
                    "next_agent": next_agent,
                    "transition_status": transition_status,
                    "transition_target": transition_target,
                    "reconciled_after_advance": stage_already_complete,
                }
                claims.append(claim)
                ingestion.update({"version": "charlie_final_artifact_ingestion_v1", "claims": claims[-100:], "last_claim": claim})
                review_packet = dict(metadata.get("review_packet") or {})
                agent_artifacts = dict(review_packet.get("agent_artifacts") or {})
                artifact_history = list(review_packet.get("agent_artifact_history") or [])
                agent_artifacts[agent] = artifact
                review_packet["agent_artifacts"] = agent_artifacts
                artifact_history.append(artifact)
                review_packet["agent_artifact_history"] = artifact_history[-120:]
                vault = dict(metadata.get("mission_vault") or {})
                handoffs = list(vault.get("handoff_notes") or [])
                handoffs.append({"agent": agent, "status": "complete", "findings": _clean_text(artifact.get("summary"), 1200), "artifact_identity": identity})
                vault["handoff_notes"] = handoffs[-20:]
                memory = dict(metadata.get("mission_memory") or {})
                notes = list(memory.get("latest_agent_notes") or [])
                notes.append({"agent": agent, "type": "agent_complete", "attempt": int(attempt or 1), "summary": _clean_text(artifact.get("summary"), 1200), "quality_gate": artifact.get("quality_gate") or {}, "artifact_identity": identity})
                memory.update({"version": memory.get("version") or "charlie_mission_memory_v1", "status": "active", "updated_at": consumed_at, "latest_agent_notes": notes[-20:]})
                updated_metadata = {
                    **metadata,
                    "agent_workflow": updated_workflow,
                    "review_packet": review_packet,
                    "mission_vault": vault,
                    "mission_memory": memory,
                    "final_artifact_ingestion": ingestion,
                }
                cursor.execute(
                    """update public.charlie_missions set metadata_json = %(metadata_json)s::jsonb,
                       updated_at = now() where mission_id = %(mission_id)s""",
                    {"mission_id": mission_id, "metadata_json": json.dumps(updated_metadata)},
                )
                _insert_event(cursor, mission_id, "workflow_updated", f"Consumed {agent} final artifact and activated {next_agent or 'workflow completion'}.", claim)
    except Exception as exc:
        return {"success": False, "status": "final_artifact_ingestion_failed", "error_type": exc.__class__.__name__}, 503
    return {
        "success": True,
        "status": "final_artifact_reconciled_after_advance" if claim.get("reconciled_after_advance") else "final_artifact_consumed",
        "mission_id": mission_id,
        "agent": agent,
        "next_agent": next_agent,
        "claim": claim,
    }, 200


def record_final_artifact_rejection(
    mission_id,
    agent,
    execution_id,
    attempt,
    artifact,
    artifact_sha256,
    missing_or_invalid,
    database_url=None,
    connect_factory=None,
):
    """Durably record a rejected final file without accepting it as stage evidence."""
    mission_id = _clean_text(mission_id, 90)
    agent = _clean_text(agent, 40).lower()
    execution_id = _clean_text(execution_id, 160)
    artifact_sha256 = _clean_text(artifact_sha256, 64).lower()
    artifact = dict(artifact) if isinstance(artifact, dict) else {}
    missing_or_invalid = sorted({
        _clean_text(value, 80)
        for value in (missing_or_invalid or [])
        if _clean_text(value, 80)
    })
    if not mission_id or not agent or not execution_id or not artifact_sha256:
        return {"success": False, "status": "artifact_identity_required"}, 400
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    observed_at = datetime.now(timezone.utc).isoformat()
    attempt = int(attempt or 1)
    lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
    binding = {
        "source_revision": _clean_text(
            artifact.get("source_revision") or artifact.get("source_commit") or lineage.get("source_commit"),
            40,
        ).lower(),
        "candidate_revision": _clean_text(artifact.get("candidate_revision"), 40).lower(),
        "expected_revision": _clean_text(artifact.get("expected_revision"), 40).lower(),
        "tested_revision": _clean_text(artifact.get("tested_revision"), 40).lower(),
        "candidate_fingerprint": _clean_text(
            artifact.get("candidate_fingerprint") or lineage.get("candidate_fingerprint"),
            128,
        ),
        "parent_artifact_id": _clean_text(artifact.get("parent_artifact_id"), 500),
        "input_artifact_ids": sorted({
            _clean_text(value, 500)
            for value in (artifact.get("input_artifact_ids") or [])
            if _clean_text(value, 500)
        }),
    }
    observation_identity = hashlib.sha256(json.dumps({
        "mission_id": mission_id,
        "execution_id": execution_id,
        "producing_stage": agent,
        "attempt": attempt,
        "artifact_sha256": artifact_sha256,
        "failure_class": "final_artifact_binding_invalid",
    }, sort_keys=True).encode("utf-8")).hexdigest()

    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select metadata_json from public.charlie_missions
                       where mission_id = %(mission_id)s for update""",
                    {"mission_id": mission_id},
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "status": "not_found", "mission_id": mission_id}, 404
                metadata = dict(rows[0][0] or {})
                if "portfolio_classification" in metadata:
                    return {"success": False, "status": "portfolio_classified_mission_ineligible"}, 409
                review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
                evidence_generation = _clean_text(
                    review_packet.get("review_generation")
                    or review_packet.get("evidence_generation")
                    or metadata.get("execution_generation"),
                    180,
                )
                semantic_identity = hashlib.sha256(json.dumps({
                    "mission_id": mission_id,
                    "producing_stage": agent,
                    "evidence_generation": evidence_generation,
                    "failure_class": "final_artifact_binding_invalid",
                    "missing_or_invalid": missing_or_invalid,
                    "binding": binding,
                }, sort_keys=True).encode("utf-8")).hexdigest()
                rejection = dict(metadata.get("final_artifact_rejections") or {})
                observations = list(rejection.get("observations") or [])
                semantic_rejections = list(rejection.get("semantic_rejections") or [])
                existing_observation = next(
                    (
                        item for item in observations
                        if isinstance(item, dict) and item.get("identity") == observation_identity
                    ),
                    None,
                )
                existing_semantic = next(
                    (
                        item for item in semantic_rejections
                        if isinstance(item, dict) and item.get("identity") == semantic_identity
                    ),
                    None,
                )
                if existing_observation:
                    return {
                        "success": False,
                        "status": "final_artifact_binding_invalid",
                        "mission_id": mission_id,
                        "agent": agent,
                        "attempt": attempt,
                        "missing_or_invalid": missing_or_invalid,
                        "rejection": existing_observation,
                        "semantic_rejection": existing_semantic or {},
                        "rejection_already_recorded": True,
                    }, 422
                observation = {
                    "identity": observation_identity,
                    "semantic_identity": semantic_identity,
                    "execution_id": execution_id,
                    "producing_stage": agent,
                    "attempt": attempt,
                    "artifact_sha256": artifact_sha256,
                    "failure_class": "final_artifact_binding_invalid",
                    "missing_or_invalid": missing_or_invalid,
                    "binding": binding,
                    "evidence_generation": evidence_generation,
                    "return_to_stage": agent,
                    "observed_at": observed_at,
                }
                observations.append(observation)
                if existing_semantic:
                    existing_semantic["last_observed_at"] = observed_at
                    existing_semantic["observation_count"] = int(existing_semantic.get("observation_count") or 0) + 1
                    existing_semantic["latest_observation_identity"] = observation_identity
                    semantic_record = existing_semantic
                else:
                    semantic_record = {
                        "identity": semantic_identity,
                        "mission_id": mission_id,
                        "producing_stage": agent,
                        "failure_class": "final_artifact_binding_invalid",
                        "missing_or_invalid": missing_or_invalid,
                        "binding": binding,
                        "evidence_generation": evidence_generation,
                        "return_to_stage": agent,
                        "status": "ingestion_blocked",
                        "first_observed_at": observed_at,
                        "last_observed_at": observed_at,
                        "observation_count": 1,
                        "latest_observation_identity": observation_identity,
                    }
                    semantic_rejections.append(semantic_record)
                rejection.update({
                    "version": "charlie_final_artifact_rejections_v1",
                    "observations": observations[-120:],
                    "semantic_rejections": semantic_rejections[-80:],
                    "last_rejection": semantic_record,
                })
                cursor.execute(
                    """update public.charlie_missions
                       set metadata_json = jsonb_set(
                           coalesce(metadata_json, '{}'::jsonb),
                           '{final_artifact_rejections}',
                           %(rejections_json)s::jsonb,
                           true
                       ),
                       updated_at = now()
                       where mission_id = %(mission_id)s""",
                    {
                        "mission_id": mission_id,
                        "rejections_json": json.dumps(rejection),
                    },
                )
                _insert_event(
                    cursor,
                    mission_id,
                    "workflow_updated",
                    f"Rejected unbound {agent} final artifact before workflow transition.",
                    {
                        "failure_class": "final_artifact_binding_invalid",
                        "producing_stage": agent,
                        "observation_identity": observation_identity,
                        "semantic_rejection_identity": semantic_identity,
                        "return_to_stage": agent,
                        "missing_or_invalid": missing_or_invalid,
                    },
                )
    except Exception as exc:
        return {
            "success": False,
            "status": "final_artifact_rejection_persistence_failed",
            "error_type": exc.__class__.__name__,
        }, 503
    return {
        "success": False,
        "status": "final_artifact_binding_invalid",
        "mission_id": mission_id,
        "agent": agent,
        "attempt": attempt,
        "missing_or_invalid": missing_or_invalid,
        "rejection": observation,
        "semantic_rejection": semantic_record,
        "rejection_already_recorded": False,
    }, 422


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
    if not mission_runtime_eligible(mission):
        return {"success": False, "status": "portfolio_classified_mission_ineligible"}, 409
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
    if step_status == "blocked":
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
    expected_review_generation="",
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
    review_packet_before_decision = dict((mission.get("metadata") or {}).get("review_packet") or {})
    current_review_generation = _clean_text(review_packet_before_decision.get("review_generation", ""), 180)
    expected_review_generation = _clean_text(expected_review_generation, 180)
    if decision == "approve_final_release" and (not current_review_generation or (expected_review_generation and expected_review_generation != current_review_generation)):
        return {"success": False, "configured": True, "status": "stale_review_generation", "mission_id": mission_id}, 409
    final_readiness = evaluate_final_readiness(mission)
    if decision == "approve_final_release" and not final_readiness.get("can_authorize_release"):
        return {
            "success": False,
            "configured": True,
            "status": "final_approval_not_ready",
            "mission_id": mission_id,
            "final_readiness": final_readiness,
            "next_action": final_readiness.get("next_action", "Complete the pending readiness gates."),
        }, 409
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
        agent_artifacts = review_packet.get("agent_artifacts") if isinstance(review_packet.get("agent_artifacts"), dict) else {}
        candidate_manifest = review_packet.get("candidate_manifest") if isinstance(review_packet.get("candidate_manifest"), dict) else {}
        preserved_agents = applicable_passing_agents(agent_artifacts, candidate_manifest)
        workflow = targeted_workflow_return(
            mission.get("agent_workflow") or [],
            target_stage,
            comments,
            preserve_agents=preserved_agents,
        )
        vault = dict(mission.get("vault") or {})
        vault["mission_stage"] = f"returned_to_{target_stage}"
        if comments:
            review_comments = vault.get("owner_review_comments") if isinstance(vault.get("owner_review_comments"), list) else []
            review_comments = list(review_comments) + [{"stage": target_stage, "comments": comments}]
            vault["owner_review_comments"] = review_comments[-12:]
        metadata_update["agent_workflow"] = workflow
        metadata_update["mission_vault"] = vault
        metadata_update["targeted_invalidation"] = {
            "version": "charlie_targeted_invalidation_v1",
            "target_agent": target_stage,
            "preserved_agents": preserved_agents,
            "candidate_fingerprint": candidate_manifest.get("candidate_fingerprint", ""),
            "recorded_at": decision_record["recorded_at"],
        }

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
                    "expected_status": mission.get("status", ""),
                }
                where_clauses = ["mission_id = %(mission_id)s", "status = %(expected_status)s"]
                if decision == "approve_final_release":
                    params["expected_review_generation"] = current_review_generation
                    where_clauses.append("metadata_json->'review_packet'->>'review_generation' = %(expected_review_generation)s")
                if approval_level:
                    set_lines.insert(1, "approval_level = %(approval_level)s")
                    params["approval_level"] = normalize_approval_level(approval_level)
                cursor.execute(
                    f"""
                    update public.charlie_missions
                    set {", ".join(set_lines)}
                    where {" and ".join(where_clauses)}
                    returning mission_id
                    """,
                    params,
                )
                rows = cursor.fetchall()
                if not rows:
                    return {"success": False, "configured": True, "status": "review_decision_claim_lost", "mission_id": mission_id}, 409
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
    final_readiness = evaluate_final_readiness(mission)
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
        "candidate_manifest": packet.get("candidate_manifest") if isinstance(packet.get("candidate_manifest"), dict) else {},
        "evidence_reconciliation": packet.get("evidence_reconciliation") if isinstance(packet.get("evidence_reconciliation"), dict) else {},
        "active_blockers": packet.get("active_blockers") if isinstance(packet.get("active_blockers"), list) else [],
        "resolved_findings": packet.get("resolved_findings") if isinstance(packet.get("resolved_findings"), list) else [],
        "follow_up_findings": packet.get("follow_up_findings") if isinstance(packet.get("follow_up_findings"), list) else [],
        "evidence_requiring_refresh": packet.get("evidence_requiring_refresh") if isinstance(packet.get("evidence_requiring_refresh"), list) else [],
        "recommended_action": packet.get("recommended_action") if isinstance(packet.get("recommended_action"), dict) else {},
        "quality_gates": packet.get("quality_gates") if isinstance(packet.get("quality_gates"), list) else [],
        "qa_evidence": _packet_list(packet, "qa_evidence", []),
        "handoff_reports": packet.get("handoff_reports") if isinstance(packet.get("handoff_reports"), dict) else vault.get("handoff_reports", []),
        "backflow_events": packet.get("backflow_events") if isinstance(packet.get("backflow_events"), list) else [],
        "charlie_core": core,
        "orchestration": metadata.get("orchestration") if isinstance(metadata.get("orchestration"), dict) else {},
        "orchestration_binding": metadata.get("orchestration_binding") if isinstance(metadata.get("orchestration_binding"), dict) else {},
        "supersession": metadata.get("supersession") if isinstance(metadata.get("supersession"), dict) else {},
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
        "final_readiness": final_readiness,
        "can_approve_final_release": final_readiness.get("can_authorize_release") is True,
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
                cursor.execute(
                    """
                    select mission_id, status, metadata_json, created_at, updated_at
                    from public.charlie_missions
                    order by created_at desc
                    limit 500
                    """
                )
                throughput_rows = cursor.fetchall()
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
        "orchestration_throughput": _orchestration_throughput_rows(throughput_rows),
    }, 200


def mission_control_snapshot(limit=100, database_url=None, connect_factory=None):
    """Read the owner queue and its counts over one canonical DB connection."""
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "counts": {}, "missions": []}, 503

    parsed_limit = _bounded_limit(limit)
    params = {"owner_queue_statuses": list(OWNER_QUEUE_STATUSES), "limit": parsed_limit}
    metadata_select = _mission_metadata_select(compact=True)
    owner_filter = """
        status = any(%(owner_queue_statuses)s)
        and coalesce(nullif(metadata_json->'intake_quality'->>'queue_class', ''), 'owner_work') = 'owner_work'
    """
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    with eligible_mission_ids as materialized (
                        select mission_id
                        from public.charlie_missions
                        where {owner_filter}
                          and jsonb_typeof(metadata_json->'mission_control_projection') = 'object'
                          and metadata_json->'mission_control_projection' ? 'latest_event_id'
                        {_mission_order_clause("owner_queue")}
                        limit %(limit)s
                    )
                    select mission_id, status, source, telegram_user_id, telegram_chat_id,
                           raw_text, title, urgency, mission_type, approval_level,
                           selected_next_step, owner_decision, codex_chat_write_status,
                           {metadata_select}, created_at, updated_at
                    from public.charlie_missions
                    join eligible_mission_ids using (mission_id)
                    {_mission_order_clause("owner_queue")}
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "mission_control_snapshot_failed",
            "error_type": exc.__class__.__name__,
            "counts": {},
            "missions": [],
        }, 503

    missions = [_mission_row(row) for row in rows]
    counts = {}
    for mission in missions:
        status = str(mission.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "counts": counts,
        "missions": missions,
    }, 200


def _orchestration_throughput_rows(rows):
    """Derive owner-visible durable metrics from the existing mission ledger."""
    missions = []
    by_tier = {}
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        mission_id, status, raw_metadata, created_at, updated_at = row[:5]
        if isinstance(raw_metadata, dict):
            metadata = raw_metadata
        elif isinstance(raw_metadata, str):
            try:
                metadata = json.loads(raw_metadata)
            except (TypeError, ValueError):
                metadata = {}
        else:
            metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        packet = metadata.get("orchestration") if isinstance(metadata.get("orchestration"), dict) else {}
        execution = metadata.get("agent_execution") if isinstance(metadata.get("agent_execution"), dict) else {}
        selected = packet.get("selected_agents") if isinstance(packet.get("selected_agents"), list) else None
        skipped = packet.get("skipped_agents") if isinstance(packet.get("skipped_agents"), list) else None
        stages = execution.get("stages") if isinstance(execution.get("stages"), list) else None
        history = packet.get("expansion_history") if isinstance(packet.get("expansion_history"), list) else None
        elapsed = packet.get("elapsed_seconds")
        if elapsed is None and created_at and updated_at:
            try:
                elapsed = max(0, int((updated_at - created_at).total_seconds()))
            except (AttributeError, TypeError):
                elapsed = None
        item = {
            "mission_id": str(mission_id or ""),
            "tier": packet.get("tier") or "Unavailable",
            "selected_agent_count": len(selected) if selected is not None else "Unavailable",
            "skipped_agent_count": len(skipped) if skipped is not None else "Unavailable",
            "elapsed_seconds": elapsed if elapsed is not None else "Unavailable",
            "stage_elapsed_seconds": {
                str(stage.get("agent") or stage.get("stage") or "unknown"): stage.get("elapsed_seconds", "Unavailable")
                for stage in (stages or []) if isinstance(stage, dict)
            } if stages is not None else "Unavailable",
            "attempts": sum(int(stage.get("attempt") or 1) for stage in stages if isinstance(stage, dict)) if stages is not None else "Unavailable",
            "backflows": len(execution.get("backflow_events") or []) if isinstance(execution.get("backflow_events"), list) else packet.get("backflow_count", "Unavailable"),
            "expansion_generations": (1 + len(history)) if history is not None else "Unavailable",
            "final_outcome": packet.get("final_outcome") or status or "Unavailable",
            "owner_interventions": len(metadata.get("owner_review_decisions") or []) if isinstance(metadata.get("owner_review_decisions"), list) else "Unavailable",
            "blocked_reason": (metadata.get("review_packet") or {}).get("blocked_reason", "Unavailable") if isinstance(metadata.get("review_packet"), dict) else "Unavailable",
        }
        missions.append(item)
        tier = item["tier"]
        bucket = by_tier.setdefault(tier, {"missions": 0, "known_elapsed_missions": 0, "elapsed_seconds": 0})
        bucket["missions"] += 1
        if isinstance(item["elapsed_seconds"], int):
            bucket["known_elapsed_missions"] += 1
            bucket["elapsed_seconds"] += item["elapsed_seconds"]
    for bucket in by_tier.values():
        known = bucket["known_elapsed_missions"]
        bucket["average_elapsed_seconds"] = bucket["elapsed_seconds"] / known if known else "Unavailable"
    return {"version": "charlie_orchestration_throughput_v1", "missions": missions, "by_tier": by_tier}


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


def _mission_admission_operational_event(mission_id, event_type, payload, principal):
    now = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(json.dumps(
        {
            "mission_id": mission_id,
            "event_type": event_type,
            "payload": payload,
            "principal": principal,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    built = build_event({
        "event_id": f"EVT-MISSION-ADMISSION-{digest[:24].upper()}",
        "idempotency_key": f"mission-admission:{mission_id}:{digest}",
        "event_type": event_type,
        "domain": "missions",
        "aggregate_type": "charlie_mission",
        "aggregate_id": mission_id,
        "source_system": "charlie_mission_store",
        "source_record_id": payload.get("receipt_id", ""),
        "authority_tier": "owner_approved",
        "privacy_class": "owner_private",
        "actor_type": (
            "owner"
            if event_type.endswith(("invalidated", "revoked"))
            else "execution_bridge"
            if event_type.endswith("consumed")
            else "control_tower"
        ),
        "actor_id": principal,
        "occurred_at": now,
        "payload": payload,
        "provenance": {
            "source_ref": "modules/charlie/mission_store.py",
            "content_sha256": payload.get("content_sha256", ""),
        },
    }, recorded_at=now)
    if not built.get("accepted"):
        raise ValueError(built.get("status") or "mission_admission_event_invalid")
    return built["event"]


def _mission_root_identity(mission_id, metadata):
    family = (
        metadata.get("mission_family")
        if isinstance(metadata.get("mission_family"), dict)
        else {}
    )
    return _clean_text(
        family.get("root_mission_id")
        or metadata.get("root_mission_id")
        or mission_id,
        90,
    )


def _insert_operational_event(cursor, event):
    cursor.execute(
        """insert into public.operational_events (
               event_id,idempotency_key,schema_version,event_type,domain,
               aggregate_type,aggregate_id,source_system,source_record_id,
               authority_tier,privacy_class,actor_type,actor_id,correlation_id,
               causation_id,occurred_at,recorded_at,freshness_at,payload_json,
               provenance_json
           ) values (
               %(event_id)s,%(idempotency_key)s,%(schema_version)s,%(event_type)s,
               %(domain)s,%(aggregate_type)s,%(aggregate_id)s,%(source_system)s,
               %(source_record_id)s,%(authority_tier)s,%(privacy_class)s,
               %(actor_type)s,%(actor_id)s,%(correlation_id)s,%(causation_id)s,
               %(occurred_at)s,%(recorded_at)s,%(freshness_at)s,
               %(payload)s::jsonb,%(provenance)s::jsonb
           ) on conflict (idempotency_key) do nothing returning event_id""",
        {
            **event,
            "payload": json.dumps(event["payload"], sort_keys=True),
            "provenance": json.dumps(event["provenance"], sort_keys=True),
        },
    )
    return cursor.fetchone() is not None


def _load_operational_event(cursor, idempotency_key):
    cursor.execute(
        """select event_id,idempotency_key,schema_version,event_type,domain,
                  aggregate_type,aggregate_id,source_system,source_record_id,
                  authority_tier,privacy_class,actor_type,actor_id,correlation_id,
                  causation_id,occurred_at,recorded_at,freshness_at,payload_json,
                  provenance_json
           from public.operational_events
           where idempotency_key=%(idempotency_key)s limit 1""",
        {"idempotency_key": idempotency_key},
    )
    row = cursor.fetchone()
    if not row:
        return {}
    keys = (
        "event_id", "idempotency_key", "schema_version", "event_type", "domain",
        "aggregate_type", "aggregate_id", "source_system", "source_record_id",
        "authority_tier", "privacy_class", "actor_type", "actor_id",
        "correlation_id", "causation_id", "occurred_at", "recorded_at",
        "freshness_at", "payload", "provenance",
    )
    result = dict(zip(keys, row))
    for key in ("occurred_at", "recorded_at", "freshness_at"):
        result[key] = _iso(result.get(key))
    return result


def _same_operational_event(left, right):
    if not isinstance(left, dict):
        return False
    comparable = {
        key: value
        for key, value in right.items()
        if key != "late_event"
    }
    return all(left.get(key) == value for key, value in comparable.items())


def _mission_row(row):
    metadata = row[13] if isinstance(row[13], dict) else {}
    queue = metadata.get("queue") if isinstance(metadata.get("queue"), dict) else {}
    queue_priority = _clean_queue_priority(queue.get("priority")) if queue else None
    raw_text = row[5]
    title = row[6]
    result = {
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
    result["technical_status"] = result["status"]
    result["mission_lifecycle"] = mission_lifecycle_projection(result)
    from modules.charlie.mission_control import owner_projection
    result["owner_projection"] = owner_projection(result)
    return result


def _find_open_duplicate_mission(cursor, params):
    cursor.execute(
        """
        select mission_id, status, title, raw_text, metadata_json
        from public.charlie_missions
        where status = any(%(statuses)s)
        order by updated_at desc
        limit 250
        """,
        {"statuses": sorted(OPEN_DUPLICATE_STATUSES)},
    )
    new_title = _normalize_mission_text(params.get("title", ""))
    new_raw = _normalize_mission_text(params.get("raw_text", ""))
    new_metadata = params.get("metadata_json")
    try:
        new_metadata = json.loads(new_metadata) if isinstance(new_metadata, str) else dict(new_metadata or {})
    except (TypeError, ValueError):
        new_metadata = {}
    new_family_key = _mission_family_scope_key(new_metadata)
    for row in cursor.fetchall():
        existing_title = _normalize_mission_text(row[2])
        existing_raw = _normalize_mission_text(row[3])
        if new_raw and existing_raw == new_raw:
            return _duplicate_row(row)
        if new_title and existing_title == new_title and len(new_title) >= 18:
            return _duplicate_row(row)
        existing_metadata = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}
        if new_family_key and _mission_family_scope_key(existing_metadata) == new_family_key:
            return _duplicate_row(row)
    return None


def _resolve_exact_identity_intake(cursor, params):
    """Serialize owner-approved identity/title and fail before unrelated writes."""
    mission_id = params["mission_id"]
    normalized_title = _normalize_mission_text(params.get("title", ""))
    cursor.execute(
        "select pg_advisory_xact_lock(hashtextextended(%(lock_key)s, 0))",
        {"lock_key": f"mission-id:{mission_id}"},
    )
    cursor.execute(
        """select mission_id, status, title, raw_text, metadata_json
           from public.charlie_missions
           where mission_id = %(mission_id)s
           for update""",
        {"mission_id": mission_id},
    )
    exact_rows = cursor.fetchall()
    if exact_rows:
        row = exact_rows[0]
        expected_metadata = json.loads(params.get("metadata_json") or "{}")
        expected_admission = expected_metadata.get("portfolio_admission")
        persisted_metadata = row[4] if isinstance(row[4], dict) else {}
        persisted_admission = persisted_metadata.get("portfolio_admission")
        admission_matches = (
            expected_admission is None and persisted_admission is None
            or expected_admission is not None and persisted_admission is not None
            and row[1] == params.get("status")
            and persisted_admission == expected_admission)
        if (row[2] == params.get("title") and row[3] == params.get("raw_text")
                and admission_matches):
            return ({"stored": False, "configured": True,
                "status": "duplicate_exact_mission", "mission_id": mission_id,
                "existing_status": row[1], "title": row[2]}, 200)
        return ({"stored": False, "configured": True,
            "status": "exact_mission_identity_conflict", "mission_id": mission_id}, 409)
    cursor.execute(
        """select mission_id, status, title
           from public.charlie_missions
           where status = any(%(statuses)s)
           order by updated_at desc""",
        {"statuses": sorted(OPEN_DUPLICATE_STATUSES)},
    )
    for row in cursor.fetchall():
        if (_normalize_mission_text(row[2]) == normalized_title
                and row[0] != mission_id):
            return ({"stored": False, "configured": True,
                "status": "exact_mission_title_conflict",
                "mission_id": mission_id, "conflicting_mission_id": row[0]}, 409)
    return None


def _lock_mission_intake_title(cursor, params):
    normalized_title = _normalize_mission_text(params.get("title", ""))
    cursor.execute(
        "select pg_advisory_xact_lock(hashtextextended(%(lock_key)s, 0))",
        {"lock_key": f"mission-title:{normalized_title}"},
    )


def _duplicate_row(row):
    return {
        "mission_id": row[0],
        "status": row[1],
        "title": row[2],
        "raw_text": row[3] if len(row) > 3 else "",
        "metadata": row[4] if len(row) > 4 and isinstance(row[4], dict) else {},
    }


def _duplicate_contract_state(duplicate, now=None):
    metadata = duplicate.get("metadata") if isinstance(duplicate.get("metadata"), dict) else {}
    packet = metadata.get("orchestration")
    workflow = metadata.get("agent_workflow")
    expected_binding = metadata.get("orchestration_binding")
    if isinstance(packet, dict) or isinstance(expected_binding, dict):
        binding = validate_orchestration_binding(packet, workflow)
        if (
            binding.get("valid")
            and isinstance(expected_binding, dict)
            and expected_binding.get("identity") == binding.get("identity")
            and expected_binding.get("generation_identity") == packet.get("generation_identity")
        ):
            return {"status": "current_contract_reusable", "reason": "durable_current_contract"}
        return {"status": "duplicate_contract_invalid", "reason": binding.get("reason") or "binding_invalid"}
    if _duplicate_has_active_lease(metadata, now=now):
        return {"status": "legacy_duplicate_active", "reason": "active_execution_lease"}
    return {
        "status": "legacy_duplicate_not_reusable",
        "reason": "required_orchestration_packet_and_binding_missing",
    }


def _duplicate_has_active_lease(metadata, now=None):
    metadata = metadata if isinstance(metadata, dict) else {}
    lease = metadata.get("execution_lease") if isinstance(metadata.get("execution_lease"), dict) else {}
    expires_at = str(lease.get("expires_at") or "").strip()
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry > observed


def _legacy_replacement_params(params, duplicate):
    metadata = json.loads(params["metadata_json"])
    packet = metadata.get("orchestration") if isinstance(metadata.get("orchestration"), dict) else {}
    binding = metadata.get("orchestration_binding") if isinstance(metadata.get("orchestration_binding"), dict) else {}
    source_revision = _clean_text(
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("RENDER_COMMIT")
        or os.getenv("CORE_SOURCE_COMMIT"),
        40,
    ).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        return {"valid": False, "reason": "current_source_revision_unavailable"}
    generation = str(packet.get("generation_identity") or "")
    if (
        not generation
        or binding.get("generation_identity") != generation
        or not binding.get("validated")
    ):
        return {"valid": False, "reason": "replacement_orchestration_binding_invalid"}
    supersedes_mission_id = duplicate["mission_id"]
    business_identity = hashlib.sha256(
        _normalize_mission_text(duplicate.get("raw_text") or params["raw_text"]).encode("utf-8")
    ).hexdigest()[:24]
    replacement_identity = hashlib.sha256(
        f"{supersedes_mission_id}|{business_identity}|{generation}".encode("utf-8")
    ).hexdigest()[:24]
    replacement_mission_id = "CHARLIE-REPLACEMENT-" + replacement_identity.upper()
    existing_family = (
        duplicate.get("metadata", {}).get("mission_family")
        if isinstance(duplicate.get("metadata", {}).get("mission_family"), dict)
        else {}
    )
    metadata["mission_family"] = {
        "root_mission_id": existing_family.get("root_mission_id") or supersedes_mission_id,
        "parent_mission_id": supersedes_mission_id,
        "relationship": "legacy_contract_supersession",
        "business_identity": business_identity,
        "finding_family": existing_family.get("finding_family") or "legacy_duplicate_intake",
    }
    metadata["supersession"] = {
        "version": "charlie_legacy_duplicate_supersession_v1",
        "status": "current_contract_replacement",
        "reason": "legacy_duplicate_not_reusable",
        "supersedes_mission_id": supersedes_mission_id,
        "replacement_mission_id": replacement_mission_id,
        "replacement_identity": replacement_identity,
        "business_identity": business_identity,
        "source_revision": source_revision,
        "candidate_revision": source_revision,
        "orchestration_generation": generation,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    replacement_params = dict(params)
    replacement_params["mission_id"] = replacement_mission_id
    replacement_params["metadata_json"] = json.dumps(metadata)
    return {
        "valid": True,
        "params": replacement_params,
        "supersedes_mission_id": supersedes_mission_id,
        "replacement_identity": replacement_identity,
    }


def _replacement_metadata_matches(metadata, supersedes_mission_id, replacement_identity):
    metadata = metadata if isinstance(metadata, dict) else {}
    supersession = metadata.get("supersession") if isinstance(metadata.get("supersession"), dict) else {}
    binding = validate_orchestration_binding(
        metadata.get("orchestration"),
        metadata.get("agent_workflow"),
    )
    return bool(
        binding.get("valid")
        and supersession.get("supersedes_mission_id") == supersedes_mission_id
        and supersession.get("replacement_identity") == replacement_identity
        and supersession.get("orchestration_generation")
        == (metadata.get("orchestration") or {}).get("generation_identity")
    )


def _mission_family_scope_key(metadata):
    metadata = metadata if isinstance(metadata, dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    root_id = str(family.get("root_mission_id") or "").strip().lower()
    scope = str(family.get("finding_family") or (metadata.get("pre_builder_scope") or {}).get("scope") or "").strip().lower()
    return f"{root_id}|{scope}" if root_id and scope else ""


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
    metadata.setdefault("mission_context_pack", _default_context_pack(mission.get("mission_type", ""), raw_text))
    media_references = mission.get("media_references")
    if isinstance(media_references, list):
        metadata["media_references"] = [_clean_media_reference(item) for item in media_references if _clean_media_reference(item)]
    else:
        metadata.setdefault("media_references", [])
    metadata["intake"] = {
        "source": _clean_text(source_context.get("source", "telegram"), 60) or "telegram",
        "adaptive_orchestration_required": True,
    }
    plan_mission = {
        **mission,
        "raw_text": raw_text,
        "mission_type": mission.get("mission_type", "feature build"),
        "title": mission.get("title", raw_text),
    }
    plan = build_core_plan(plan_mission)
    metadata.pop("agent_workflow", None)
    metadata.pop("orchestration", None)
    metadata = attach_core_plan_to_metadata(plan_mission, metadata)
    metadata["agent_workflow"] = plan["agent_workflow"]
    metadata["orchestration"] = plan["orchestration"]
    binding = validate_orchestration_binding(
        metadata["orchestration"], metadata["agent_workflow"]
    )
    if not binding.get("valid"):
        raise ValueError(binding.get("reason") or "orchestration_binding_invalid")
    metadata["orchestration_binding"] = {
        "version": "charlie_orchestration_binding_v1",
        "identity": binding["identity"],
        "generation_identity": metadata["orchestration"]["generation_identity"],
        "validated": True,
    }
    selected = [item["agent"] for item in metadata["orchestration"]["selected_agents"]]
    metadata["intake"].update({
        "requires_planner": "planner" in selected,
        "requires_builder": "builder" in selected,
        "requires_tester": "tester" in selected,
        "requires_reviewer": "reviewer" in selected,
    })
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
                            when 'paused' then 2
                            when 'pr_ready' then 3
                            when 'blocked' then 4
                            when 'release_approved' then 5
                            when 'approved' then 6
                            when 'new' then 7
                            else 8
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
                ,'changed_files', metadata_json->'review_packet'->'changed_files'
                ,'release_readiness', metadata_json->'review_packet'->'release_readiness'
                ,'deployment_watch', metadata_json->'review_packet'->'deployment_watch'
                ,'operational_evidence', metadata_json->'review_packet'->'operational_evidence'
                ,'merge_commit', metadata_json->'review_packet'->'merge_commit'
                ,'protected_operations', metadata_json->'review_packet'->'protected_operations'
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
            'mission_control_projection', metadata_json->'mission_control_projection',
            'outcome_closure', metadata_json->'outcome_closure',
            'unfinished_business', metadata_json->'unfinished_business',
            'outcome_closure_tracking', metadata_json->'outcome_closure_tracking',
            'protected_operations', metadata_json->'protected_operations',
            'migration_owner_approved', metadata_json->'migration_owner_approved',
            'migration_approved', metadata_json->'migration_approved',
            'migration_applied', metadata_json->'migration_applied',
            'migrations_applied', metadata_json->'migrations_applied',
            'deployment_verified', metadata_json->'deployment_verified',
            'deployed', metadata_json->'deployed',
            'live_smoke_passed', metadata_json->'live_smoke_passed',
            'production_smoke_passed', metadata_json->'production_smoke_passed',
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
    if agent and next_agent and next_agent in known:
        known[agent]["handoff_to"] = next_agent
    if not agent:
        return [known[name] for name in sequence]
    if step_status in {"active", "blocked", "complete"}:
        for name in sequence:
            if name != agent and known[name].get("status") == "active":
                known[name]["status"] = "pending"
    known[agent]["status"] = step_status
    if step_status == "active":
        known[agent].pop("completed_at", None)
    elif step_status == "complete":
        known[agent]["completed_at"] = datetime.now(timezone.utc).isoformat()
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
            known[agent].pop("completed_at", None)
            if comments:
                known[agent]["findings"] = comments
        elif target_seen:
            known[agent]["status"] = "pending"
        elif known[agent].get("status") == "active":
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


def _owner_execution_hold_writer_database_url(database_url):
    if database_url is not None:
        return str(database_url or "").strip()
    return os.getenv("CHARLIE_OWNER_EXECUTION_HOLD_DATABASE_URL", "").strip()


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
