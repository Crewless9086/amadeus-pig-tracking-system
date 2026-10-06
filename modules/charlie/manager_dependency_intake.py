"""Default-inert, explicitly admitted manager findings on existing CORE rails.

This records an engineering intake receipt, not a worker claim or a repair.
No mission status, manager projection, lease, hold or original proof is changed.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import sys
import os
from contextlib import nullcontext
from datetime import datetime, timedelta

from modules.oom_sakkie.family_access import resolve_family_principal

from modules.charlie.executive_store import record_control_command, complete_control_command
from modules.charlie.mission_control import build_mission_control_event, canonical_event_equal
from modules.charlie.mission_store import (
    _connect, _database_url, append_mission_control_event, owner_execution_hold_status,
    mission_runtime_eligible, _not_durably_superseded_sql,
)
from modules.oom_sakkie.herdmaster_case_disposition import (
    MortalityReconciliationPending, _mortality_owner_binding, is_legacy_mortality_case,
)

CAPABILITY = "core.manager_dependency_intake"
CONTRACT = "core.manager_dependency_intake.v1"
ACTOR = "service:core.manager_dependency_intake.v1"
MAX_DEPENDENCIES = 8
INTAKE_BUDGET_SECONDS = 10
_EFFECTS = ["core_finding_append", "core_command_receipt", "manager_receipt_link"]
_SCOPE_KEYS = {"contract", "mission_id", "mission_identity_digest", "owner_user_id", "owner_binding",
               "producer_revision", "dependencies", "allowed_effects"}
_DEPENDENCY_KEYS = {"case_id", "generation", "evidence_digest", "evidence_refs_digest",
                    "dependency_id", "anchor_event_id", "anchor_cycle_id"}


class IntakeRefused(ValueError):
    """Stable internal reason, never raw database or owner text."""


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("manager_dependency_intake_deadline")
    return remaining


class _BudgetCursor:
    def __init__(self, cursor, deadline): self.cursor, self.deadline = cursor, deadline
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self, *args): return self.cursor.__exit__(*args)
    def execute(self, sql, params=None):
        remaining_ms = max(1, int(_remaining(self.deadline) * 1000))
        self.cursor.execute("select set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                            (str(min(3000, remaining_ms)), str(min(1000, remaining_ms))))
        _remaining(self.deadline)
        return self.cursor.execute(sql, params)
    def __getattr__(self, name): return getattr(self.cursor, name)


class _BudgetConnection:
    def __init__(self, connection, deadline): self.connection, self.deadline = connection, deadline
    def __enter__(self):
        try:
            self.connection.__enter__()
            _remaining(self.deadline)
            return self
        except BaseException:
            self.connection.close()
            raise
    def __exit__(self, kind, value, traceback):
        if kind is None:
            try: _remaining(self.deadline)
            except TimeoutError:
                self.connection.__exit__(*sys.exc_info())
                raise
        return self.connection.__exit__(kind, value, traceback)
    def cursor(self): return _BudgetCursor(self.connection.cursor(), self.deadline)
    def close(self): self.connection.close()


def _open(url, factory, deadline):
    # Reuse the existing bounded acquisition rail. Abandoned connections are
    # closed by that rail; no database work runs in its connector thread.
    from modules.oom_sakkie.bounded_postgres_read import _connect_with_wall_clock_deadline
    connection = _connect_with_wall_clock_deadline(
        lambda target, **kw: _connect(url, factory), url, {}, min(3, _remaining(deadline)))
    return _BudgetConnection(connection, deadline)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, default=str).encode()).hexdigest()


def _require(condition, reason):
    if not condition:
        raise IntakeRefused(reason)


def _time(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    _require(result.utcoffset() is not None, "aware_time_required")
    return result


def mission_identity_digest(mission):
    """Bind the existing work/admission, excluding only this derived projection."""
    metadata = dict(mission.get("metadata_json") or mission.get("metadata") or {})
    metadata.pop("mission_control_projection", None)
    metadata.pop("manager_dependency_intake", None)
    fields = ("mission_id", "source", "telegram_user_id", "telegram_chat_id", "raw_text",
              "title", "mission_type", "approval_level", "owner_decision", "selected_next_step")
    return digest({**{key: mission.get(key) for key in fields}, "metadata": metadata})


def validate_scope(scope):
    _require(isinstance(scope, dict) and set(scope) == _SCOPE_KEYS, "scope_invalid")
    _require(scope["contract"] == CONTRACT and scope["allowed_effects"] == _EFFECTS, "scope_effects_invalid")
    for key in ("mission_identity_digest", "owner_binding"):
        _require(bool(re.fullmatch(r"[a-f0-9]{64}", str(scope[key]))), "scope_digest_invalid")
    _require(bool(re.fullmatch(r"[a-f0-9]{40}", str(scope["producer_revision"]))), "source_revision_invalid")
    _require(isinstance(scope["mission_id"], str) and 0 < len(scope["mission_id"]) <= 90
             and isinstance(scope["owner_user_id"], str) and scope["owner_user_id"].isdigit(), "scope_identity_invalid")
    deps = scope["dependencies"]
    _require(isinstance(deps, list) and 0 < len(deps) <= MAX_DEPENDENCIES, "scope_dependencies_invalid")
    for dep in deps:
        _require(isinstance(dep, dict) and set(dep) == _DEPENDENCY_KEYS, "dependency_scope_invalid")
        _require(type(dep["generation"]) is int and dep["generation"] > 0, "dependency_generation_invalid")
        for key in ("evidence_digest", "evidence_refs_digest"):
            _require(bool(re.fullmatch(r"[a-f0-9]{64}", str(dep[key]))), "dependency_digest_invalid")
        for key in ("case_id", "dependency_id", "anchor_event_id", "anchor_cycle_id"):
            _require(isinstance(dep[key], str) and 0 < len(dep[key]) <= 160, "dependency_identity_invalid")
    _require(len({d["case_id"] for d in deps}) == len(deps)
             and len({d["dependency_id"] for d in deps}) == len(deps), "dependency_scope_duplicate")
    return scope


def _policy_material(policy):
    return {key: policy.get(key) for key in ("policy_id", "capability", "authority_tier", "enabled",
             "expires_at", "max_actions", "max_cost", "rollback_required", "deterministic_gate_required") } | {
             "scope": policy.get("scope_json", policy.get("scope"))}


def _policy_matches(current, expected, now):
    # Compare semantic time/numeric values; the context serializes these fields.
    left, right = _policy_material(current), _policy_material(expected)
    for packet in (left, right):
        packet["expires_at"] = _time(packet["expires_at"]).isoformat()
        packet["max_cost"] = str(float(packet["max_cost"]))
    _require(left == right, "policy_changed")
    _require(current["capability"] == CAPABILITY and current["enabled"] is True
             and current["authority_tier"] in {"auto", "charlie_delegated"}
             and _time(current["expires_at"]) > now
             and type(current["max_actions"]) is int and 0 < current["max_actions"] <= MAX_DEPENDENCIES
             and float(current["max_cost"]) == 0 and current["rollback_required"] is True
             and current["deterministic_gate_required"] is True, "policy_not_authorized")
    return validate_scope(left["scope"])


def _mission_matches(mission, policy, scope):
    metadata = mission.get("metadata_json") or {}
    _require(mission["mission_id"] == scope["mission_id"] and mission["status"] == "approved"
             and mission_runtime_eligible({"metadata": metadata}) and not metadata.get("execution_lease"),
             "mission_not_idle_approved")
    _require(str(mission.get("telegram_user_id")) == scope["owner_user_id"]
             and str(mission.get("telegram_chat_id")) == scope["owner_user_id"]
             and mission_identity_digest(mission) == scope["mission_identity_digest"], "mission_identity_changed")
    admission = metadata.get("manager_dependency_intake")
    _require(isinstance(admission, dict) and set(admission) == {
        "contract", "policy_id", "scope_digest", "authorization_identity"}
        and admission["contract"] == CONTRACT and admission["policy_id"] == policy["policy_id"]
        and admission["scope_digest"] == digest(scope)
        and isinstance(admission["authorization_identity"], str)
        and 0 < len(admission["authorization_identity"]) <= 180, "mission_service_admission_missing")


def _dependency_matches(case, event, cycle, scope, dep, now):
    _require(is_legacy_mortality_case(case) and case.get("status") == "waiting_reassessment"
             and not case.get("assigned_worker_id") and case.get("lease_until") is None,
             "dependency_not_idle_pending")
    for key in ("case_id", "generation", "evidence_digest"):
        _require(case.get(key) == dep[key], "dependency_generation_changed")
    _require(digest(case["evidence_refs"]) == dep["evidence_refs_digest"], "dependency_refs_changed")
    observed = next(v[9:] for v in case["evidence_refs"] if v.startswith("observed:"))
    _require(_time(observed) <= now, "dependency_observation_future")
    expected = MortalityReconciliationPending(json.dumps(case), scope["owner_binding"], now).metadata()
    _require(expected["dependency_id"] == dep["dependency_id"], "dependency_identity_changed")
    payload = event.get("event_payload") or {}
    _require(event.get("event_id") == dep["anchor_event_id"] and event.get("case_id") == dep["case_id"]
             and event.get("generation") == dep["generation"] and event.get("event_type") == "delivery_suppressed"
             and payload.get("outcome_status") == "herdmaster_owning_reconciliation_pending"
             and payload.get("delivery_confirmed") is False and digest(payload.get("technical_dependency")) == digest(expected)
             and payload.get("cycle_id") == dep["anchor_cycle_id"], "pending_anchor_unproven")
    _require(cycle.get("cycle_id") == dep["anchor_cycle_id"] and cycle.get("status") == "completed"
             and cycle.get("source_revision") == scope["producer_revision"]
             and cycle.get("worker_id") == "oom-sakkie-general-manager-v1"
             and cycle.get("trigger_identity") == "oom-sakkie-morning-scheduler:general-manager"
             and _time(cycle["started_at"]) <= _time(event["occurred_at"]) <= now
             and _time(event["occurred_at"]) <= _time(cycle["started_at"]) + timedelta(minutes=2),
             "pending_cycle_unproven")
    return expected


def _locked_inputs(cur, expected_policy, dep):
    cur.execute("select to_jsonb(p) from public.charlie_delegation_policies p where policy_id=%s for update",
                (expected_policy["policy_id"],))
    row = cur.fetchone()
    _require(row is not None, "policy_missing")
    policy = row[0]
    cur.execute("select clock_timestamp()")
    now = cur.fetchone()[0]
    scope = _policy_matches(policy, expected_policy, now)
    _require(dep in scope["dependencies"] and scope["owner_binding"] == _mortality_owner_binding(), "current_owner_changed")
    principal = resolve_family_principal({"telegram_user_id": scope["owner_user_id"],
        "telegram_chat_id": scope["owner_user_id"], "telegram_chat_type": "private"}, os.environ)
    _require(principal.is_owner, "mission_owner_not_current")
    if policy["authority_tier"] == "charlie_delegated":
        cur.execute("select tier from public.charlie_capability_trust where capability_key=%s for share", (CAPABILITY,))
        trust = cur.fetchone()
        _require(trust is not None and trust[0] in {"delegated", "auto"}, "capability_trust_not_promoted")
    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (scope["mission_id"],))
    cur.execute("select to_jsonb(m) from public.charlie_missions m "
                "where m.mission_id=%s and " + _not_durably_superseded_sql().replace(
                    "public.charlie_missions.mission_id", "m.mission_id") + " for update", (scope["mission_id"],))
    row = cur.fetchone()
    _require(row is not None, "mission_missing")
    _mission_matches(row[0], policy, scope)
    hold, status = owner_execution_hold_status(scope["mission_id"], cursor=cur)
    _require(status == 200 and hold.get("active") is False, "mission_hold_unavailable_or_active")
    cur.execute("select to_jsonb(m) from app_private.oom_manager_cases m where case_id=%s for update", (dep["case_id"],))
    row = cur.fetchone()
    _require(row is not None, "dependency_case_missing")
    case = row[0]
    cur.execute("select to_jsonb(e) from app_private.oom_manager_case_events e where event_id=%s and case_id=%s", (dep["anchor_event_id"], dep["case_id"]))
    row = cur.fetchone()
    _require(row is not None, "pending_anchor_missing")
    event = row[0]
    cur.execute("select to_jsonb(c) from app_private.oom_manager_worker_cycles c where cycle_id=%s", (dep["anchor_cycle_id"],))
    row = cur.fetchone()
    _require(row is not None, "pending_cycle_missing")
    # Recheck wall clock after all potentially waiting locks/reads.
    cur.execute("select clock_timestamp()")
    now = cur.fetchone()[0]
    _policy_matches(policy, expected_policy, now)
    _dependency_matches(case, event, row[0], scope, dep, now)
    cur.execute("""select to_jsonb(e),to_jsonb(c)
        from app_private.oom_manager_case_events e
        left join app_private.oom_manager_worker_cycles c on c.cycle_id=e.event_payload->>'cycle_id'
        where e.case_id=%s and e.occurred_at>=%s
          and e.event_type in ('delivery_suppressed','delivery_confirmed','exception','contained','completed')
          and coalesce(e.event_payload->>'outcome_status','')<>'manager_engineering_intake_recorded'
        order by e.occurred_at desc,e.event_id desc limit 1""", (dep["case_id"], event["occurred_at"]))
    latest = cur.fetchone()
    _require(latest is not None and latest[1] is not None, "current_pending_outcome_missing")
    current_dep = {**dep, "anchor_event_id": latest[0]["event_id"],
                   "anchor_cycle_id": latest[1]["cycle_id"]}
    _dependency_matches(case, latest[0], latest[1], scope, current_dep, now)
    now = _fresh_policy_clock(cur, policy, expected_policy)
    return policy, scope, now


def _fresh_policy_clock(cur, policy, expected):
    cur.execute("select clock_timestamp()")
    now = cur.fetchone()[0]
    _policy_matches(policy, expected, now)
    return now


def _packets(policy, scope, dep):
    key = "manager-dependency:" + digest({"mission": scope["mission_id"], "dependency": dep["dependency_id"]})
    command = {"action": "record_manager_dependency_finding", "capability": CAPABILITY,
               "mission_id": scope["mission_id"], "authority_tier": policy["authority_tier"],
               "policy_id": policy["policy_id"], "idempotency_key": key,
               "scope_digest": digest(scope), "dependency": dep}
    payload = {"event_type": "finding_recorded", "idempotency_key": key,
               "summary": "Manager mortality review lineage is unproven. Engineering intake only; welfare review, worker pickup and repair remain unproven.",
               "evidence_refs": ["manager_dependency:" + dep["dependency_id"], "manager_event:" + dep["anchor_event_id"],
                   "manager_cycle:" + dep["anchor_cycle_id"], "source_revision:" + scope["producer_revision"],
                   "intake_scope:" + digest(scope), "intake_command:" + digest(command)]}
    event = build_mission_control_event(scope["mission_id"], payload, recorded_by=ACTOR)
    command_id = "CMD-" + hashlib.sha256(key.encode()).hexdigest()[:20].upper()
    result = {"contract": CONTRACT, "event_id": event["event_id"], "dependency_id": dep["dependency_id"],
              "finding_received": True, "worker_selected": False, "worker_picked_up": False, "repair_verified": False}
    return command, payload, event, command_id, result


def _readback(cur, command, event, command_id, result):
    cur.execute("select mission_id,event_type,recorded_by,metadata_json,notes,created_at from public.charlie_mission_events where event_id=%s", (event["event_id"],))
    stored = cur.fetchone()
    _require(stored is not None and stored[:3] == (event["mission_id"], "finding_recorded", ACTOR)
             and canonical_event_equal(stored[3], event) and stored[4] == event["summary"]
             and _time(stored[5]) == _time(stored[3]["recorded_at"]), "core_event_readback_conflict")
    cur.execute("select mission_id,policy_id,status,payload_json,result_json,command_type,authority_tier,idempotency_key,goal_id from public.charlie_control_commands where command_id=%s", (command_id,))
    stored = cur.fetchone()
    _require(stored is not None and stored[:3] == (event["mission_id"], command["policy_id"], "succeeded")
             and digest(stored[3]) == digest(command) and digest(stored[4]) == digest(result)
             and stored[5:] == (command["action"], command["authority_tier"], command["idempotency_key"], None),
             "core_command_readback_conflict")


def _one_dependency(expected_policy, dep, url, connect_factory, deadline):
    with _open(url, connect_factory, deadline) as db, db.cursor() as cur:
        policy, scope, _ = _locked_inputs(cur, expected_policy, dep)
        command, payload, event, command_id, result = _packets(policy, scope, dep)
        borrowed = lambda _url: nullcontext(db)
        recorded, status = record_control_command(command, database_url=url, connect_factory=borrowed)
        _require(status < 400 and recorded.get("success"), "command_admission_failed")
        if recorded["created"]:
            _fresh_policy_clock(cur, policy, expected_policy)
            written, status = append_mission_control_event(scope["mission_id"], payload, recorded_by=ACTOR,
                                                           database_url=url, connect_factory=borrowed)
            _require(status < 400 and written.get("success"), "finding_append_failed")
            finished, status = complete_control_command(command_id, success=True, result=result,
                                                        database_url=url, connect_factory=borrowed)
            _require(status < 400 and finished.get("success"), "command_receipt_failed")
        _readback(cur, command, event, command_id, result)
        _fresh_policy_clock(cur, policy, expected_policy)
    # This is a new transaction: no acknowledgement from an uncommitted API result.
    # A crash here is safe: the immutable command/finding above replays exactly.
    with _open(url, connect_factory, deadline) as db, db.cursor() as cur:
        policy, scope, now = _locked_inputs(cur, expected_policy, dep)
        _readback(cur, command, event, command_id, result)
        now = _fresh_policy_clock(cur, policy, expected_policy)
        link = {"contract": CONTRACT, "dependency_id": dep["dependency_id"], "scope_digest": digest(scope),
                "mission_id": scope["mission_id"], "event_id": event["event_id"], "command_id": command_id,
                "anchor_event_id": dep["anchor_event_id"], "finding_received": True,
                "worker_selected": False, "worker_picked_up": False, "repair_verified": False}
        link_id = "OOM-CORE-INTAKE-" + digest({"mission_id": scope["mission_id"], "dependency_id": dep["dependency_id"]})[:32].upper()
        link_payload = {"outcome_status": "manager_engineering_intake_recorded", "delivery_confirmed": False,
                        "completion_proven": False, "engineering_intake": link}
        cur.execute("""insert into app_private.oom_manager_case_events
            (event_id,case_id,generation,event_type,event_payload,occurred_at)
            values (%s,%s,%s,'delivery_suppressed',%s::jsonb,%s)
            on conflict(event_id) do nothing returning event_id""",
            (link_id, dep["case_id"], dep["generation"], json.dumps(link_payload), now))
        linked = cur.fetchone() is not None
        cur.execute("select case_id,generation,event_type,event_payload from app_private.oom_manager_case_events where event_id=%s", (link_id,))
        stored_link = cur.fetchone()
        _require(stored_link is not None and stored_link[:3] == (dep["case_id"], dep["generation"], "delivery_suppressed")
                 and digest(stored_link[3]) == digest(link_payload), "manager_link_conflict")
        _fresh_policy_clock(cur, policy, expected_policy)
    return {**result, "command_id": command_id, "manager_link_event_id": link_id,
            "status": "intake_linked" if linked else "intake_exact_replay", "link_created": linked}


def consume_manager_dependencies(*, mode, policies, database_url=None, connect_factory=None):
    """Only the existing active executive and an exact service admission can write."""
    candidates = [p for p in policies or [] if isinstance(p, dict) and p.get("capability") == CAPABILITY and p.get("enabled") is True]
    if mode != "active" or not candidates:
        return {"status": "manager_dependency_intake_disabled", "results": [], "failures": 0}
    if len(candidates) != 1:
        return {"status": "manager_dependency_policy_ambiguous", "results": [], "failures": 1}
    policy = candidates[0]
    try:
        scope = validate_scope(policy.get("scope"))
    except (ValueError, TypeError, KeyError):
        return {"status": "manager_dependency_scope_invalid", "results": [], "failures": 1}
    deadline = time.monotonic() + INTAKE_BUDGET_SECONDS
    results = []
    for dep in scope["dependencies"]:
        try:
            result = _one_dependency(policy, dep, _database_url(database_url), connect_factory, deadline)
        except IntakeRefused as exc:
            result = {"status": "manager_dependency_intake_refused", "reason": str(exc)}
        except Exception as exc:
            result = {"status": "manager_dependency_intake_unavailable", "failure_kind": type(exc).__name__}
        results.append(result)
    return {"status": "manager_dependency_intake_checked", "results": results,
            "failures": sum(v["status"] not in {"intake_linked", "intake_exact_replay"} for v in results)}
