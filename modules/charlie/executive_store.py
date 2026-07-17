"""Supabase persistence for the CHARLIE executive control plane."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from modules.charlie.mission_store import _connect, _database_url


def load_executive_context(database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "not_configured", "policies": [], "goals": []}, 503
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select policy_id, capability, scope_json, authority_tier, enabled,
                           expires_at, max_actions, max_cost, rollback_required,
                           deterministic_gate_required, metadata_json
                    from public.charlie_delegation_policies
                    where enabled = true and (expires_at is null or expires_at > now())
                """)
                policies = [_policy_row(row) for row in cursor.fetchall()]
                cursor.execute("""
                    select goal_id, title, objective, business_area, priority, status,
                           success_metrics_json, constraints_json, created_by, created_at, updated_at
                    from public.charlie_executive_goals where status = 'active'
                    order by priority desc, created_at
                """)
                goals = [_goal_row(row) for row in cursor.fetchall()]
                cursor.execute("""
                    select capability_key,runs,clean_passes,recoveries,escaped_defects,
                           human_edits,rollbacks,tier,last_result,evidence_version,last_evaluated_at
                    from public.charlie_capability_trust
                """)
                trust = [{
                    "capability_key": row[0], "runs": row[1], "clean_passes": row[2], "recoveries": row[3],
                    "escaped_defects": row[4], "human_edits": row[5], "rollbacks": row[6], "tier": row[7],
                    "last_result": row[8], "evidence_version": row[9], "last_evaluated_at": row[10].isoformat() if row[10] else None,
                } for row in cursor.fetchall()]
    except Exception as exc:
        return {"success": False, "status": "executive_context_read_failed", "error_type": exc.__class__.__name__, "policies": [], "goals": []}, 503
    return {"success": True, "status": "ok", "policies": policies, "goals": goals, "trust": trust}, 200


def record_control_command(command, database_url=None, connect_factory=None):
    command = command if isinstance(command, dict) else {}
    key = str(command.get("idempotency_key") or "").strip()
    if not key:
        return {"success": False, "status": "idempotency_key_required"}, 400
    command_id = "CMD-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20].upper()
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_control_commands (
                        command_id, idempotency_key, mission_id, goal_id, command_type,
                        authority_tier, policy_id, status, payload_json
                    ) select %(command_id)s, %(key)s, %(mission_id)s, %(goal_id)s,
                             %(command_type)s, %(authority_tier)s, p.policy_id,
                             %(status)s, %(payload)s::jsonb
                      from public.charlie_delegation_policies p
                     where p.policy_id = %(policy_id)s and p.enabled = true
                       and (p.expires_at is null or p.expires_at > now())
                       and (p.max_actions = 0 or (
                           select count(*) from public.charlie_control_commands c
                           where c.policy_id = p.policy_id
                       ) < p.max_actions)
                    on conflict (idempotency_key) do nothing
                    returning command_id
                """, {
                    "command_id": command_id, "key": key, "mission_id": command.get("mission_id") or None,
                    "goal_id": command.get("goal_id") or None, "command_type": command.get("action") or "unknown",
                    "authority_tier": command.get("authority_tier") or "auto", "policy_id": command.get("policy_id") or "",
                    "status": "authorized", "payload": json.dumps(command),
                })
                created = bool(cursor.fetchall())
    except Exception as exc:
        return {"success": False, "status": "control_command_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "created" if created else "duplicate", "command_id": command_id, "created": created}, 201 if created else 200


def complete_control_command(command_id, *, success, result=None, error="", database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    update public.charlie_control_commands
                    set status = %(status)s, result_json = %(result)s::jsonb,
                        error_text = %(error)s, attempt_count = attempt_count + 1,
                        started_at = coalesce(started_at, now()), completed_at = now()
                    where command_id = %(command_id)s returning command_id
                """, {"status": "succeeded" if success else "failed", "result": json.dumps(result or {}), "error": str(error or "")[:2000], "command_id": command_id})
                found = bool(cursor.fetchall())
    except Exception as exc:
        return {"success": False, "status": "control_command_complete_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": found, "status": "ok" if found else "not_found"}, 200 if found else 404


def upsert_recovery_case(mission_id, decision, database_url=None, connect_factory=None):
    fingerprint = str(decision.get("fingerprint") or "").strip()
    recovery_id = "REC-" + hashlib.sha256(f"{mission_id}:{fingerprint}".encode("utf-8")).hexdigest()[:20].upper()
    now = datetime.now(timezone.utc)
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_recovery_cases (
                        recovery_id, mission_id, fingerprint, block_class, responsible_stage,
                        status, attempt_limit, next_attempt_at, deadline_at, evidence_json
                    ) values (%(id)s, %(mission)s, %(fingerprint)s, %(block_class)s, %(stage)s,
                              'scheduled', 3, %(next)s, %(deadline)s, %(evidence)s::jsonb)
                    on conflict (mission_id, fingerprint) do update set
                        responsible_stage = excluded.responsible_stage,
                        status = case when charlie_recovery_cases.status in ('resolved','cancelled') then charlie_recovery_cases.status else 'running' end,
                        attempt_count = case when charlie_recovery_cases.status in ('resolved','cancelled') then charlie_recovery_cases.attempt_count else charlie_recovery_cases.attempt_count + 1 end,
                        next_attempt_at = case when charlie_recovery_cases.status in ('resolved','cancelled') then charlie_recovery_cases.next_attempt_at else excluded.next_attempt_at end,
                        evidence_json = excluded.evidence_json,
                        updated_at = now()
                    returning recovery_id, status, attempt_count, attempt_limit
                """, {
                    "id": recovery_id, "mission": mission_id, "fingerprint": fingerprint,
                    "block_class": decision.get("block_class") or "system_repair_required",
                    "stage": decision.get("target_stage") or "planner", "next": now,
                    "deadline": now + timedelta(hours=8), "evidence": json.dumps(decision),
                })
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "recovery_case_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "ok", "recovery_id": row[0], "recovery_status": row[1], "attempt_count": row[2], "attempt_limit": row[3]}, 200


def queue_outbox(event_type, payload, *, idempotency_key, channel="telegram", database_url=None, connect_factory=None):
    outbox_id = "OUT-" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:20].upper()
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_notification_outbox
                        (outbox_id, idempotency_key, channel, event_type, payload_json)
                    values (%(id)s, %(key)s, %(channel)s, %(event)s, %(payload)s::jsonb)
                    on conflict (idempotency_key) do nothing returning outbox_id
                """, {"id": outbox_id, "key": idempotency_key, "channel": channel, "event": event_type, "payload": json.dumps(payload or {})})
                created = bool(cursor.fetchall())
    except Exception as exc:
        return {"success": False, "status": "outbox_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "created" if created else "duplicate", "outbox_id": outbox_id}, 201 if created else 200


def claim_pending_outbox(limit=10, database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    with selected as (
                        select outbox_id from public.charlie_notification_outbox
                        where status in ('pending','failed')
                          and (next_attempt_at is null or next_attempt_at <= now())
                          and attempt_count < 5
                        order by created_at for update skip locked limit %(limit)s
                    )
                    update public.charlie_notification_outbox o
                    set status = 'sending', attempt_count = attempt_count + 1
                    from selected where o.outbox_id = selected.outbox_id
                    returning o.outbox_id, o.event_type, o.payload_json, o.attempt_count
                """, {"limit": max(1, min(int(limit or 10), 50))})
                rows = cursor.fetchall()
    except Exception as exc:
        return {"success": False, "status": "outbox_claim_failed", "error_type": exc.__class__.__name__, "items": []}, 503
    return {"success": True, "status": "ok", "items": [{"outbox_id": row[0], "event_type": row[1], "payload": row[2] or {}, "attempt_count": row[3]} for row in rows]}, 200


def complete_outbox(outbox_id, *, sent, error="", database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    update public.charlie_notification_outbox
                    set status = case when %(sent)s then 'sent' when attempt_count >= 5 then 'dead_letter' else 'failed' end,
                        sent_at = case when %(sent)s then now() else sent_at end,
                        next_attempt_at = case when %(sent)s then null else now() + make_interval(secs => least(900, 30 * power(2, attempt_count)::int)) end,
                        last_error = %(error)s
                    where outbox_id = %(id)s returning status
                """, {"sent": bool(sent), "error": str(error or "")[:1000], "id": outbox_id})
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "outbox_complete_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": bool(row), "status": row[0] if row else "not_found"}, 200 if row else 404


def executive_scorecard(database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select
                      count(*) filter (where status = 'active') as active_goals,
                      (select count(*) from public.charlie_recovery_cases where status in ('scheduled','running')),
                      (select count(*) from public.charlie_control_commands where status = 'failed'),
                      (select count(*) from public.charlie_notification_outbox where status in ('failed','dead_letter')),
                      (select count(*) from public.charlie_capability_trust where tier in ('delegated','auto'))
                    from public.charlie_executive_goals
                """)
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "executive_scorecard_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "executive_scorecard_ready", "active_goals": row[0], "open_recoveries": row[1], "failed_commands": row[2], "notification_failures": row[3], "trusted_capabilities": row[4]}, 200


def record_capability_outcome(capability_key, *, clean_pass=False, recovered=False, escaped_defect=False, human_edit=False, rollback=False, evidence_version="", database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_capability_trust (
                        capability_key, runs, clean_passes, recoveries, escaped_defects,
                        human_edits, rollbacks, evidence_version, last_result, last_evaluated_at
                    ) values (%(key)s, 1, %(pass)s, %(recovery)s, %(defect)s, %(edit)s,
                              %(rollback)s, %(version)s, %(result)s, now())
                    on conflict (capability_key) do update set
                        runs = charlie_capability_trust.runs + 1,
                        clean_passes = charlie_capability_trust.clean_passes + excluded.clean_passes,
                        recoveries = charlie_capability_trust.recoveries + excluded.recoveries,
                        escaped_defects = charlie_capability_trust.escaped_defects + excluded.escaped_defects,
                        human_edits = charlie_capability_trust.human_edits + excluded.human_edits,
                        rollbacks = charlie_capability_trust.rollbacks + excluded.rollbacks,
                        evidence_version = excluded.evidence_version,
                        last_result = excluded.last_result,
                        last_evaluated_at = now(), updated_at = now()
                    returning runs, clean_passes, recoveries, escaped_defects, human_edits, rollbacks
                """, {
                    "key": capability_key, "pass": int(bool(clean_pass)), "recovery": int(bool(recovered)),
                    "defect": int(bool(escaped_defect)), "edit": int(bool(human_edit)), "rollback": int(bool(rollback)),
                    "version": evidence_version, "result": "pass" if clean_pass else "recovered" if recovered else "fail",
                })
                row = cursor.fetchone()
                from modules.charlie.executive_control import capability_tier
                tier = capability_tier({"runs": row[0], "clean_passes": row[1], "recoveries": row[2], "escaped_defects": row[3], "human_edits": row[4], "rollbacks": row[5]})
                cursor.execute("update public.charlie_capability_trust set tier = %(tier)s where capability_key = %(key)s", {"tier": tier, "key": capability_key})
    except Exception as exc:
        return {"success": False, "status": "capability_outcome_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": True, "status": "ok", "capability_key": capability_key, "tier": tier, "runs": row[0]}, 200


def list_capability_trust(limit=50, database_url=None, connect_factory=None):
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select capability_key,runs,clean_passes,recoveries,escaped_defects,
                           human_edits,rollbacks,tier,last_result,evidence_version,last_evaluated_at
                    from public.charlie_capability_trust
                    order by runs desc, capability_key limit %(limit)s
                """, {"limit": max(1, min(int(limit or 50), 200))})
                rows = cursor.fetchall()
    except Exception as exc:
        return {"success": False, "status": "capability_trust_read_failed", "error_type": exc.__class__.__name__, "capabilities": []}, 503
    return {"success": True, "status": "capability_trust_ready", "capabilities": [{
        "capability_key": row[0], "runs": row[1], "clean_passes": row[2], "recoveries": row[3],
        "escaped_defects": row[4], "human_edits": row[5], "rollbacks": row[6], "tier": row[7],
        "last_result": row[8], "evidence_version": row[9], "last_evaluated_at": row[10].isoformat() if row[10] else None,
    } for row in rows]}, 200


def register_eval_spec(spec, database_url=None, connect_factory=None):
    spec = spec if isinstance(spec, dict) else {}
    mission_class = str(spec.get("mission_class") or "").strip()
    version = str(spec.get("version") or "").strip()
    if not mission_class or not version:
        return {"success": False, "status": "mission_class_and_version_required"}, 400
    eval_id = "EVAL-" + hashlib.sha256(f"{mission_class}:{version}".encode("utf-8")).hexdigest()[:20].upper()
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_eval_registry
                        (eval_id, mission_class, version, status, scenarios_json, required_gates_json, minimum_pass_rate)
                    values (%(id)s, %(mission_class)s, %(version)s, 'active', %(scenarios)s::jsonb, %(gates)s::jsonb, %(minimum)s)
                    on conflict (mission_class, version) do update set
                        scenarios_json = excluded.scenarios_json,
                        required_gates_json = excluded.required_gates_json,
                        minimum_pass_rate = excluded.minimum_pass_rate,
                        updated_at = now()
                    returning eval_id
                """, {
                    "id": eval_id, "mission_class": mission_class, "version": version,
                    "scenarios": json.dumps(spec.get("scenarios") or []),
                    "gates": json.dumps(spec.get("required_gates") or []),
                    "minimum": float(spec.get("minimum_pass_rate") if spec.get("minimum_pass_rate") is not None else 1),
                })
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "eval_registry_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": bool(row), "status": "ok", "eval_id": row[0] if row else eval_id}, 200


def record_research_observation(observation, database_url=None, connect_factory=None):
    observation = observation if isinstance(observation, dict) else {}
    if observation.get("auto_activate") is not False or observation.get("owner_review_required") is not True:
        return {"success": False, "status": "owner_review_boundary_required"}, 400
    database_url = _database_url(database_url)
    try:
        with _connect(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    insert into public.charlie_research_radar (
                        research_id, business_area, topic, source_url, source_kind,
                        observed_at, summary, applicability, metadata_json
                    ) values (%(id)s, %(area)s, %(topic)s, %(url)s, %(kind)s,
                              %(observed)s, %(summary)s, %(applicability)s, %(metadata)s::jsonb)
                    on conflict (business_area, topic, source_url) do update set
                        observed_at = excluded.observed_at, summary = excluded.summary,
                        applicability = excluded.applicability, metadata_json = excluded.metadata_json
                    returning research_id
                """, {
                    "id": observation.get("research_id"), "area": observation.get("business_area"),
                    "topic": observation.get("topic"), "url": observation.get("source_url"),
                    "kind": observation.get("source_kind"), "observed": observation.get("observed_at"),
                    "summary": observation.get("summary"), "applicability": observation.get("applicability"),
                    "metadata": json.dumps({"owner_review_required": True, "auto_activate": False}),
                })
                row = cursor.fetchone()
    except Exception as exc:
        return {"success": False, "status": "research_radar_write_failed", "error_type": exc.__class__.__name__}, 503
    return {"success": bool(row), "status": "recorded_for_owner_review", "research_id": row[0] if row else ""}, 200


def _policy_row(row):
    return {"policy_id": row[0], "capability": row[1], "scope": row[2] or {}, "authority_tier": row[3], "enabled": row[4], "expires_at": row[5].isoformat() if row[5] else None, "max_actions": row[6], "max_cost": float(row[7] or 0), "rollback_required": row[8], "deterministic_gate_required": row[9], "metadata": row[10] or {}}


def _goal_row(row):
    return {"goal_id": row[0], "title": row[1], "objective": row[2], "business_area": row[3], "priority": row[4], "status": row[5], "success_metrics": row[6] or [], "constraints": row[7] or [], "created_by": row[8], "created_at": row[9].isoformat(), "updated_at": row[10].isoformat()}
