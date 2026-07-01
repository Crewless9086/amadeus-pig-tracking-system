import hashlib
import json
import os
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


VAULT_TABLES = [
    "charlie_vault_projects",
    "charlie_vault_artifacts",
    "charlie_agent_runs",
    "charlie_handoff_reports",
    "charlie_quality_gates",
    "charlie_owner_decisions",
    "charlie_deployments",
    "charlie_audit_log",
    "charlie_lessons",
    "charlie_income_stream_reviews",
]


def vault_tables_health(database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "tables": {}}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select table_name
                    from information_schema.tables
                    where table_schema = 'public'
                      and table_name = any(%(tables)s)
                    """,
                    {"tables": VAULT_TABLES},
                )
                found = {row[0] for row in cursor.fetchall()}
    except Exception as exc:
        return {"success": False, "configured": True, "status": "vault_health_failed", "error_type": exc.__class__.__name__, "tables": {}}, 503
    tables = {name: name in found for name in VAULT_TABLES}
    missing = [name for name, present in tables.items() if not present]
    return {
        "success": not missing,
        "configured": True,
        "status": "ok" if not missing else "missing_tables",
        "tables": tables,
        "missing_tables": missing,
    }, 200 if not missing else 503


def write_project(project, database_url=None, connect_factory=None):
    project = project if isinstance(project, dict) else {}
    project_id = _clean(project.get("project_id") or project.get("project_key") or "charlie_core", 120)
    params = {
        "project_id": project_id,
        "project_key": _clean(project.get("project_key") or project_id, 120),
        "name": _clean(project.get("name") or project.get("project_key") or project_id, 160),
        "purpose": _clean(project.get("purpose") or "", 1200),
        "owner_label": _clean(project.get("owner_label") or "CHARL", 80),
        "workflow_template": _clean(project.get("workflow_template") or "software_build", 100),
        "status": _clean(project.get("status") or "active", 80),
        "metadata_json": _json(project.get("metadata") or project),
    }
    sql = """
        insert into public.charlie_vault_projects (
            project_id, project_key, name, purpose, owner_label, workflow_template, status, metadata_json, created_at, updated_at
        ) values (
            %(project_id)s, %(project_key)s, %(name)s, %(purpose)s, %(owner_label)s, %(workflow_template)s, %(status)s, %(metadata_json)s::jsonb, now(), now()
        )
        on conflict (project_id) do update set
            project_key = excluded.project_key,
            name = excluded.name,
            purpose = excluded.purpose,
            owner_label = excluded.owner_label,
            workflow_template = excluded.workflow_template,
            status = excluded.status,
            metadata_json = excluded.metadata_json,
            updated_at = now()
    """
    return _execute_write(sql, params, "project_written", database_url, connect_factory)


def write_artifact(mission_id, artifact_type, content, title="", summary="", project_id="", agent="",
                   database_url=None, connect_factory=None):
    mission_id = _clean(mission_id, 120)
    artifact_type = _clean(artifact_type, 120)
    if not mission_id or not artifact_type:
        return {"success": False, "status": "mission_id_and_artifact_type_required"}, 400
    content = content if isinstance(content, dict) else {"value": content}
    params = {
        "artifact_id": _stable_id("artifact", mission_id, artifact_type, title or summary or json.dumps(content, sort_keys=True)),
        "mission_id": mission_id,
        "project_id": _clean(project_id, 120),
        "artifact_type": artifact_type,
        "title": _clean(title, 240),
        "summary": _clean(summary or content.get("summary") or "", 1600),
        "content_json": _json(content),
        "source_refs": _json(content.get("source_refs") if isinstance(content.get("source_refs"), list) else []),
        "confidence": _clean(content.get("confidence") or "", 80),
        "created_by_agent": _clean(agent, 120),
    }
    sql = """
        insert into public.charlie_vault_artifacts (
            artifact_id, mission_id, project_id, artifact_type, title, summary, content_json, source_refs, confidence, created_by_agent, created_at
        ) values (
            %(artifact_id)s, %(mission_id)s, nullif(%(project_id)s, ''), %(artifact_type)s, %(title)s, %(summary)s,
            %(content_json)s::jsonb, %(source_refs)s::jsonb, %(confidence)s, %(created_by_agent)s, now()
        )
        on conflict (artifact_id) do update set
            title = excluded.title,
            summary = excluded.summary,
            content_json = excluded.content_json,
            source_refs = excluded.source_refs,
            confidence = excluded.confidence,
            created_by_agent = excluded.created_by_agent
    """
    return _execute_write(sql, params, "artifact_written", database_url, connect_factory)


def write_agent_run(mission_id, agent, run, stage="", database_url=None, connect_factory=None):
    mission_id = _clean(mission_id, 120)
    agent = _clean(agent, 120)
    run = run if isinstance(run, dict) else {}
    if not mission_id or not agent:
        return {"success": False, "status": "mission_id_and_agent_required"}, 400
    run_id = _clean(run.get("run_id"), 160) or _stable_id(
        "agent_run",
        mission_id,
        agent,
        run.get("execution_id") or "",
        run.get("attempt") or "",
        run.get("started_at") or "",
    )
    params = {
        "run_id": run_id,
        "mission_id": mission_id,
        "agent": agent,
        "stage": _clean(stage or run.get("stage") or agent, 120),
        "status": _clean(run.get("status") or "pending", 80),
        "model_provider": _clean(run.get("model_provider") or "", 120),
        "model_name": _clean(run.get("model_name") or "", 160),
        "started_at": _clean(run.get("started_at") or "", 80),
        "completed_at": _clean(run.get("completed_at") or run.get("updated_at") or "", 80),
        "cost_estimate": run.get("cost_estimate") if isinstance(run.get("cost_estimate"), (int, float)) else None,
        "token_usage_json": _json(run.get("token_usage") if isinstance(run.get("token_usage"), dict) else {}),
        "tool_calls_json": _json(run.get("tool_calls") if isinstance(run.get("tool_calls"), list) else []),
        "metadata_json": _json(run),
    }
    sql = """
        insert into public.charlie_agent_runs (
            run_id, mission_id, agent, stage, status, model_provider, model_name, started_at, completed_at,
            cost_estimate, token_usage_json, tool_calls_json, metadata_json
        ) values (
            %(run_id)s, %(mission_id)s, %(agent)s, %(stage)s, %(status)s, %(model_provider)s, %(model_name)s,
            nullif(%(started_at)s, '')::timestamptz, nullif(%(completed_at)s, '')::timestamptz,
            %(cost_estimate)s, %(token_usage_json)s::jsonb, %(tool_calls_json)s::jsonb, %(metadata_json)s::jsonb
        )
        on conflict (run_id) do update set
            status = excluded.status,
            completed_at = excluded.completed_at,
            cost_estimate = excluded.cost_estimate,
            token_usage_json = excluded.token_usage_json,
            tool_calls_json = excluded.tool_calls_json,
            metadata_json = excluded.metadata_json
    """
    return _execute_write(sql, params, "agent_run_written", database_url, connect_factory)


def write_handoff_report(report, database_url=None, connect_factory=None):
    report = report if isinstance(report, dict) else {}
    mission_id = _clean(report.get("mission_id"), 120)
    agent = _clean(report.get("agent"), 120)
    stage = _clean(report.get("stage") or agent, 120)
    if not mission_id or not agent:
        return {"success": False, "status": "mission_id_and_agent_required"}, 400
    params = {
        "handoff_id": _stable_id("handoff", mission_id, agent, stage, report.get("recorded_at") or ""),
        "mission_id": mission_id,
        "agent": agent,
        "stage": stage,
        "status": _clean(report.get("pass_fail_status") or report.get("status") or "", 80),
        "report_json": _json(report),
        "validation_json": _json(report.get("validation") if isinstance(report.get("validation"), dict) else {}),
    }
    sql = """
        insert into public.charlie_handoff_reports (
            handoff_id, mission_id, agent, stage, status, report_json, validation_json, created_at
        ) values (
            %(handoff_id)s, %(mission_id)s, %(agent)s, %(stage)s, %(status)s, %(report_json)s::jsonb, %(validation_json)s::jsonb, now()
        )
        on conflict (handoff_id) do update set
            status = excluded.status,
            report_json = excluded.report_json,
            validation_json = excluded.validation_json
    """
    return _execute_write(sql, params, "handoff_written", database_url, connect_factory)


def write_quality_gate(mission_id, gate_name, status, reason="", evidence=None, stage="",
                       database_url=None, connect_factory=None):
    mission_id = _clean(mission_id, 120)
    gate_name = _clean(gate_name, 160)
    if not mission_id or not gate_name:
        return {"success": False, "status": "mission_id_and_gate_name_required"}, 400
    params = {
        "gate_id": _stable_id("gate", mission_id, gate_name, stage),
        "mission_id": mission_id,
        "gate_name": gate_name,
        "stage": _clean(stage, 120),
        "status": _clean(status, 80),
        "reason": _clean(reason, 1200),
        "evidence_json": _json(evidence if isinstance(evidence, dict) else {}),
    }
    sql = """
        insert into public.charlie_quality_gates (
            gate_id, mission_id, gate_name, stage, status, reason, evidence_json, created_at
        ) values (
            %(gate_id)s, %(mission_id)s, %(gate_name)s, %(stage)s, %(status)s, %(reason)s, %(evidence_json)s::jsonb, now()
        )
        on conflict (gate_id) do update set
            status = excluded.status,
            reason = excluded.reason,
            evidence_json = excluded.evidence_json
    """
    return _execute_write(sql, params, "quality_gate_written", database_url, connect_factory)


def write_owner_decision(mission_id, decision, approval_level="", comments="", metadata=None,
                         database_url=None, connect_factory=None):
    mission_id = _clean(mission_id, 120)
    decision = _clean(decision, 160)
    if not mission_id or not decision:
        return {"success": False, "status": "mission_id_and_decision_required"}, 400
    params = {
        "decision_id": _stable_id("decision", mission_id, decision, datetime.now(timezone.utc).isoformat()),
        "mission_id": mission_id,
        "decision": decision,
        "approval_level": _clean(approval_level, 80),
        "comments": _clean(comments, 2000),
        "metadata_json": _json(metadata if isinstance(metadata, dict) else {}),
    }
    sql = """
        insert into public.charlie_owner_decisions (
            decision_id, mission_id, decision, approval_level, comments, metadata_json, created_at
        ) values (
            %(decision_id)s, %(mission_id)s, %(decision)s, %(approval_level)s, %(comments)s, %(metadata_json)s::jsonb, now()
        )
    """
    return _execute_write(sql, params, "owner_decision_written", database_url, connect_factory)


def write_deployment_record(record, database_url=None, connect_factory=None):
    record = record if isinstance(record, dict) else {}
    mission_id = _clean(record.get("mission_id"), 120)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    params = {
        "deployment_id": _stable_id("deployment", mission_id, record.get("commit_sha") or "", record.get("verify_url") or ""),
        "mission_id": mission_id,
        "commit_sha": _clean(record.get("commit_sha"), 120),
        "pr_url": _clean(record.get("pr_url"), 500),
        "verify_url": _clean(record.get("verify_url"), 500),
        "status": _clean(record.get("status") or "pending", 80),
        "metadata_json": _json(record),
    }
    sql = """
        insert into public.charlie_deployments (
            deployment_id, mission_id, commit_sha, pr_url, verify_url, status, metadata_json, created_at
        ) values (
            %(deployment_id)s, %(mission_id)s, %(commit_sha)s, %(pr_url)s, %(verify_url)s, %(status)s, %(metadata_json)s::jsonb, now()
        )
        on conflict (deployment_id) do update set
            status = excluded.status,
            metadata_json = excluded.metadata_json
    """
    return _execute_write(sql, params, "deployment_written", database_url, connect_factory)


def write_audit_event(action, mission_id="", actor="charlie_core", target="", risk_level="", metadata=None,
                      database_url=None, connect_factory=None):
    action = _clean(action, 160)
    if not action:
        return {"success": False, "status": "action_required"}, 400
    params = {
        "audit_id": _stable_id("audit", mission_id, actor, action, datetime.now(timezone.utc).isoformat()),
        "mission_id": _clean(mission_id, 120),
        "actor": _clean(actor or "charlie_core", 120),
        "action": action,
        "target": _clean(target, 240),
        "risk_level": _clean(risk_level, 80),
        "metadata_json": _json(metadata if isinstance(metadata, dict) else {}),
    }
    sql = """
        insert into public.charlie_audit_log (
            audit_id, mission_id, actor, action, target, risk_level, metadata_json, created_at
        ) values (
            %(audit_id)s, nullif(%(mission_id)s, ''), %(actor)s, %(action)s, %(target)s, %(risk_level)s, %(metadata_json)s::jsonb, now()
        )
    """
    return _execute_write(sql, params, "audit_event_written", database_url, connect_factory)


def write_lesson(lesson, database_url=None, connect_factory=None):
    lesson = lesson if isinstance(lesson, dict) else {}
    params = {
        "lesson_id": _stable_id("lesson", lesson.get("mission_id") or "", lesson.get("source_stage") or "", lesson.get("failure") or ""),
        "mission_id": _clean(lesson.get("mission_id"), 120),
        "source_stage": _clean(lesson.get("source_stage"), 120),
        "failure": _clean(lesson.get("failure"), 2000),
        "improvement": _clean(lesson.get("improvement"), 2000),
        "target": _clean(lesson.get("target") or "prompt_or_test_or_workflow_update", 160),
        "status": _clean(lesson.get("status") or "queued", 80),
        "metadata_json": _json(lesson),
    }
    sql = """
        insert into public.charlie_lessons (
            lesson_id, mission_id, source_stage, failure, improvement, target, status, metadata_json, created_at
        ) values (
            %(lesson_id)s, nullif(%(mission_id)s, ''), %(source_stage)s, %(failure)s, %(improvement)s, %(target)s, %(status)s, %(metadata_json)s::jsonb, now()
        )
        on conflict (lesson_id) do update set
            improvement = excluded.improvement,
            status = excluded.status,
            metadata_json = excluded.metadata_json
    """
    return _execute_write(sql, params, "lesson_written", database_url, connect_factory)


def write_income_stream_review(mission_id, readiness, business_model=None, risk_register=None,
                               owner_gate_status="pending", database_url=None, connect_factory=None):
    mission_id = _clean(mission_id, 120)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    params = {
        "review_id": _stable_id("income", mission_id),
        "mission_id": mission_id,
        "business_model_json": _json(business_model if isinstance(business_model, dict) else {}),
        "risk_register_json": _json(risk_register if isinstance(risk_register, list) else []),
        "readiness_json": _json(readiness if isinstance(readiness, dict) else {}),
        "owner_gate_status": _clean(owner_gate_status, 80),
    }
    sql = """
        insert into public.charlie_income_stream_reviews (
            review_id, mission_id, business_model_json, risk_register_json, readiness_json, owner_gate_status, created_at, updated_at
        ) values (
            %(review_id)s, %(mission_id)s, %(business_model_json)s::jsonb, %(risk_register_json)s::jsonb,
            %(readiness_json)s::jsonb, %(owner_gate_status)s, now(), now()
        )
        on conflict (review_id) do update set
            business_model_json = excluded.business_model_json,
            risk_register_json = excluded.risk_register_json,
            readiness_json = excluded.readiness_json,
            owner_gate_status = excluded.owner_gate_status,
            updated_at = now()
    """
    return _execute_write(sql, params, "income_stream_review_written", database_url, connect_factory)


def _execute_write(sql, params, status, database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
    except Exception as exc:
        return {"success": False, "configured": True, "status": f"{status}_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "configured": True, "status": status}, 200


def _database_url(database_url=None):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _connect(database_url, connect_factory=None):
    if connect_factory:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _json(value):
    return json.dumps(value if value is not None else {})


def _clean(value, max_len=1000):
    return " ".join(str(value or "").strip().split())[:max_len]


def _stable_id(*parts):
    raw = ":".join(_clean(part, 1000) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    prefix = _clean(parts[0] if parts else "charlie", 20).upper()
    return f"CHARLIE-{prefix}-{digest}"
