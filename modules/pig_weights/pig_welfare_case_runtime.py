"""Bounded adapter for the canonical pig welfare-case lifecycle.

This module owns no observation, treatment, movement, mortality, disposal,
manager, attention-queue or channel semantics.  It stores coordination state
and projects reference-only work from the three tables created by migration
202608200002.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping


OPEN_STATES = ("open", "monitoring", "escalated")


def welfare_case_runtime_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Enable the migrated canonical runtime unless explicitly contained.

    Migration 202608200002 is mandatory on the production migration rail. An
    exact ``false`` remains a kill switch; malformed configured values fail
    closed instead of silently activating.
    """
    source = os.environ if environ is None else environ
    if "PIG_WELFARE_CASE_RUNTIME_ENABLED" not in source:
        return bool(str(source.get("DATABASE_URL") or "").strip())
    value = str(source.get("PIG_WELFARE_CASE_RUNTIME_ENABLED") or "").strip().lower()
    return value == "true"


def load_open_welfare_case_contexts(chat_id: str, owner_user_id: str, *, connect_factory=None):
    """Load open contexts without an elapsed-time cutoff.

    Channel and principal bindings are checked in SQL and again in process.
    Closed cases are deliberately excluded: silence can never manufacture a
    close, while an explicit close can never capture later unrelated speech.
    """
    if not str(chat_id or "").strip() or not str(owner_user_id or "").strip():
        return []
    cm = connect_factory() if connect_factory else _connect()
    with cm as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select c.welfare_case_id, current.case_state,
                   current.urgency,current.responsible_owner,current.next_check_at,
                   current.escalation_reason,e.provenance_json,e.recorded_at
            from public.pig_welfare_case_current current
            join public.pig_welfare_cases c using (welfare_case_id)
            join lateral (
              select event.provenance_json,event.recorded_at,event.sequence_no
              from public.pig_welfare_case_events event
              where event.welfare_case_id=c.welfare_case_id
              order by event.sequence_no desc limit 1
            ) e on true
            where current.case_state = any(%s)
              and e.provenance_json->'intake_context'->>'chat_id'=%s
              and e.provenance_json->'intake_context'->>'owner_user_id'=%s
            order by e.recorded_at desc,c.welfare_case_id
            """,
            (list(OPEN_STATES), str(chat_id), str(owner_user_id)),
        )
        rows = cursor.fetchall()
    result = []
    for case_id, state, urgency, owner, next_check, escalation, provenance, _recorded in rows:
        context = (provenance or {}).get("intake_context") if isinstance(provenance, Mapping) else None
        if not isinstance(context, Mapping):
            continue
        if str(context.get("chat_id") or "") != str(chat_id) or str(context.get("owner_user_id") or "") != str(owner_user_id):
            continue
        result.append({**dict(context), "welfare_case_id": str(case_id),
                       "welfare_case_state": str(state), "welfare_case_urgency": str(urgency),
                       "welfare_case_owner": str(owner),
                       "welfare_case_next_check_at": next_check.isoformat() if next_check else None,
                       "welfare_case_escalation_reason": escalation})
    return result


def load_open_welfare_attention_cases(*, connect_factory=None):
    """Load every current welfare case for the shared manager projection.

    This read-only specialist adapter has no channel cutoff: an authenticated
    owner-attention view must not lose active work created through another
    supported channel.
    """
    cm = connect_factory() if connect_factory else _connect()
    with cm as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select current.welfare_case_id,current.pig_id,current.case_state,
                   current.urgency,current.responsible_owner,current.next_check_at,
                   current.escalation_reason,current.state_occurred_at,
                   event.provenance_json
            from public.pig_welfare_case_current current
            join public.pig_welfare_case_events event
              on event.welfare_case_event_id=current.welfare_case_event_id
            where current.case_state = any(%s)
            order by current.state_occurred_at desc,current.welfare_case_id
            """,
            (list(OPEN_STATES),),
        )
        rows = cursor.fetchall()
    return [{"welfare_case_id": str(row[0]), "pig_id": str(row[1]),
             "welfare_case_state": str(row[2]), "welfare_case_urgency": str(row[3]),
             "welfare_case_owner": str(row[4]),
             "welfare_case_next_check_at": row[5].isoformat() if row[5] else None,
             "welfare_case_escalation_reason": row[6],
             "welfare_case_observed_at": row[7].isoformat(),
             "welfare_case_provenance": row[8] or {}}
            for row in rows]


def append_welfare_case_context(lifecycle: Mapping[str, Any], *, connect_factory=None):
    """Open or append one case event, exactly once per provider generation."""
    preview = lifecycle.get("preview") if isinstance(lifecycle.get("preview"), Mapping) else {}
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    pig_id = str(identity.get("pig_id") or "").strip()
    mission_id = str(lifecycle.get("mission_id") or "").strip()
    provider_id = str(lifecycle.get("provider_message_id") or "").strip()
    occurred = str(lifecycle.get("provider_timestamp") or "").strip()
    if not all((pig_id, mission_id, provider_id, occurred)):
        return {"success": False, "status": "welfare_case_identity_incomplete", "rows_created": 0}
    case_id = "WELFARE-" + hashlib.sha256(mission_id.encode()).hexdigest()[:24].upper()
    concern = _concern_key(evaluator)
    event_key = f"welfare-context:{case_id}:{provider_id}:{lifecycle.get('event_phase') or 'context'}"
    event_id = "WELFARE-EVENT-" + hashlib.sha256(event_key.encode()).hexdigest()[:24].upper()
    urgency = _urgency(evaluator)
    next_check = _next_check(occurred, urgency)
    provenance = json.dumps({"contract_version": "pig_welfare_case_runtime_v1",
                             "intake_context": dict(lifecycle)}, sort_keys=True, default=str)
    try:
        cm = connect_factory() if connect_factory else _connect()
        with cm as connection, connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (case_id,))
            cursor.execute(
                """select welfare_case_id,pig_id,created_by,
                          provenance_json->'intake_context'->>'chat_id',
                          provenance_json->'intake_context'->>'owner_user_id'
                   from public.pig_welfare_cases where idempotency_key=%s""",
                ("case:" + mission_id,),
            )
            existing_case = cursor.fetchone()
            if not existing_case:
                cursor.execute(
                    """insert into public.pig_welfare_cases(
                    welfare_case_id,pig_id,episode_key,concern_key,episode_started_at,
                    first_reported_at,created_by,source_system,source_reference,
                    provenance_json,idempotency_key)
                    values(%s,%s,%s,%s,%s::timestamptz,%s::timestamptz,%s,'oom_sakkie',%s,%s::jsonb,%s)""",
                    (case_id,pig_id,mission_id,concern,occurred,occurred,
                     "owner:" + str(lifecycle.get("owner_user_id") or ""),provider_id,
                     provenance,"case:" + mission_id),
                )
            else:
                expected_owner = "owner:" + str(lifecycle.get("owner_user_id") or "")
                if (str(existing_case[1]) != pig_id
                        or str(existing_case[2]) != expected_owner
                        or str(existing_case[3] or "") != str(lifecycle.get("chat_id") or "")
                        or str(existing_case[4] or "") != str(lifecycle.get("owner_user_id") or "")):
                    return {"success": False, "status": "welfare_case_identity_binding_mismatch", "rows_created": 0}
                case_id = str(existing_case[0])
            cursor.execute("select welfare_case_event_id from public.pig_welfare_case_events where idempotency_key=%s", (event_key,))
            if cursor.fetchone():
                return {"success": True, "status": "welfare_case_context_replay", "welfare_case_id": case_id, "rows_created": 0}
            cursor.execute("select case_state from public.pig_welfare_case_current where welfare_case_id=%s", (case_id,))
            current = cursor.fetchone()
            if current and str(current[0]) == "closed":
                return {"success": True, "status": "welfare_case_already_closed",
                        "welfare_case_id": case_id, "rows_created": 0}
            # Intake completion means the observation was captured, not that
            # the underlying welfare concern recovered or was resolved.
            case_state = "open" if urgency in ("critical", "urgent") else "monitoring"
            event_type = "opened" if not current else "evidence_added"
            cursor.execute(
                """insert into public.pig_welfare_case_events(
                welfare_case_event_id,welfare_case_id,event_type,case_state,urgency,
                responsible_owner,next_check_at,closure_kind,closure_reason,
                occurred_at,actor_reference,source_system,source_reference,
                provenance_json,idempotency_key)
                values(%s,%s,%s,%s,%s,'HERDMASTER',%s::timestamptz,%s,%s,
                       %s::timestamptz,%s,'oom_sakkie',%s,%s::jsonb,%s)""",
                (event_id,case_id,event_type,case_state,urgency,
                 next_check, None, None,
                 occurred,"owner:" + str(lifecycle.get("owner_user_id") or ""),
                 provider_id,provenance,event_key),
            )
        return {"success": True, "status": "welfare_case_context_appended",
                "welfare_case_id": case_id, "welfare_case_event_id": event_id, "rows_created": 1}
    except Exception:
        return {"success": False, "status": "welfare_case_store_unavailable", "rows_created": 0}


def project_welfare_case_attention(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project the same case identity into the existing shared-attention contract."""
    case_id = str(row.get("welfare_case_id") or "")
    task_class = "physical_action_due" if _explicit_physical_weighing(row) else "status_reconciliation"
    return {"work_identity": case_id, "case_identity": case_id,
            "category": "pig_welfare", "specialist_owner": "HERDMASTER",
            "task_class": task_class,
            "lifecycle_state": "open", "priority": str(row.get("welfare_case_urgency") or "due"),
            "next_check_at": row.get("welfare_case_next_check_at"),
            "evidence_provenance": {"source": "pig_welfare_case_current", "welfare_case_id": case_id}}


def _explicit_physical_weighing(row: Mapping[str, Any]) -> bool:
    """Require explicit specialist evidence before assigning physical weighing."""
    provenance = row.get("welfare_case_provenance")
    context = provenance.get("intake_context") if isinstance(provenance, Mapping) else {}
    preview = context.get("preview") if isinstance(context, Mapping) else {}
    evaluator = preview.get("evaluator") if isinstance(preview, Mapping) else {}
    immediate = evaluator.get("immediate_welfare_priority") if isinstance(evaluator, Mapping) else {}
    evidence = str(immediate.get("action") or "").casefold() if isinstance(immediate, Mapping) else ""
    return evidence.startswith(("weigh now", "physical weighing due", "record weight now"))


def welfare_case_readiness(*, connect_factory=None):
    """Read-only schema/capability probe; it never reads or returns business rows."""
    try:
        cm = connect_factory() if connect_factory else _connect()
        with cm as connection, connection.cursor() as cursor:
            cursor.execute("""select to_regclass('public.pig_welfare_cases') is not null,
              to_regclass('public.pig_welfare_case_events') is not null,
              to_regclass('public.pig_welfare_case_current') is not null""")
            present = tuple(cursor.fetchone() or ())
        ready = present == (True, True, True)
        return {"success": ready, "status": "welfare_case_capability_ready" if ready else "welfare_case_schema_incomplete",
                "read_only": True, "business_rows_read": 0, "business_rows_written": 0}, 200 if ready else 503
    except Exception:
        return {"success": False, "status": "welfare_case_capability_unavailable",
                "read_only": True, "business_rows_read": 0, "business_rows_written": 0}, 503


def _concern_key(evaluator):
    facts = [str(item.get("fact") or "") for effect in evaluator.get("canonical_effects") or []
             for item in (effect.get("facts") or {}).get("observed", []) if isinstance(item, Mapping)]
    return "concern-" + hashlib.sha256("|".join(sorted(set(facts))).encode()).hexdigest()[:20]


def _urgency(evaluator):
    level = str((evaluator.get("immediate_welfare_priority") or {}).get("level") or "")
    return {"emergency": "critical", "urgent_follow_up": "urgent", "prompt_check": "due"}.get(level, "watch")


def _next_check(occurred, urgency):
    from datetime import timedelta
    instant = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
    return (instant + {"critical": timedelta(minutes=15), "urgent": timedelta(hours=1),
                       "due": timedelta(hours=4), "watch": timedelta(hours=12)}[urgency]).isoformat()


def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)
