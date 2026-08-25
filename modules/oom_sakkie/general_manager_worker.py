"""Durable, zero-authority Oom Sakkie manager case worker.

The worker coordinates existing specialist truth.  It never performs a domain
write, customer/provider send, publication, callback, or hardware command.
Those effects remain owned by the existing protected and specialist rails.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import os
import re
import uuid
from typing import Any, Callable, Iterable, Mapping

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres

CONTRACT_VERSION = "oom_sakkie_general_manager_worker.v1"
BRAIN_GUARD_AUDIT_VERSION = "scheduled_brain_guard_audit.v1"
WORKER_ID = "oom-sakkie-general-manager-v1"
TRIGGER_IDENTITY = "oom-sakkie-morning-scheduler:general-manager"
CADENCE = timedelta(minutes=5)
LEASE = timedelta(minutes=4)
SPECIALISTS = frozenset({"ROOTLINE", "HERDMASTER", "SAM", "BEACON", "RUNTIME"})
URGENCIES = frozenset({"critical", "urgent", "due", "planned", "watch"})
OPEN_STATES = frozenset({"open", "delegated", "waiting_reassessment", "exception"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class ManagerCaseError(ValueError):
    pass


def build_scheduled_brain_guard_audit(*, source_revision: str, now: datetime,
                                      alignment_result: Mapping[str, Any] | None = None):
    """Build a read-only, revision-bound Vault alignment result for one cycle."""
    if alignment_result is None:
        from modules.charlie.vault_alignment import evaluate_vault_alignment
        alignment_result = evaluate_vault_alignment()
    findings = sorted(str(value) for value in alignment_result.get("findings") or ())
    checked_files = sorted(str(value) for value in alignment_result.get("checked_files") or ())
    material = {
        "contract_version": BRAIN_GUARD_AUDIT_VERSION,
        "alignment_version": str(alignment_result.get("version") or "unknown"),
        "source_revision": str(source_revision or "unknown"),
        "passed": alignment_result.get("passed") is True,
        "findings": findings,
        "checked_files": checked_files,
    }
    return {
        **material,
        "status": ("brain_guard_alignment_passed" if material["passed"]
                   else "brain_guard_alignment_failed"),
        "observed_at": _aware(now).isoformat(),
        "evidence_digest": _digest(material),
        "checked_count": len(checked_files),
    }


def normalize_candidate(raw: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    specialist = str(raw.get("specialist") or "").upper().strip()
    urgency = str(raw.get("urgency") or "").lower().strip()
    dedupe = _identity(raw.get("dedupe_key"), "dedupe_key")
    if specialist not in SPECIALISTS:
        raise ManagerCaseError("unsupported_specialist")
    if urgency not in URGENCIES:
        raise ManagerCaseError("unsupported_urgency")
    refs = _bounded_strings(raw.get("evidence_refs"), "evidence_refs", required=True)
    unknowns = _bounded_strings(raw.get("unknowns") or (), "unknowns")
    summary = _text(raw.get("summary"), "summary", 500)
    next_action = _text(raw.get("next_action"), "next_action", 500)
    next_at = _time(raw.get("next_reassessment_at"), "next_reassessment_at")
    terminal_state = str(raw.get("terminal_state") or "").strip().lower()
    if terminal_state not in {"", "completed"}:
        raise ManagerCaseError("unsupported_terminal_state")
    if next_at < now - timedelta(minutes=5):
        next_at = now
    material = {
        "contract_version": CONTRACT_VERSION,
        "dedupe_key": dedupe,
        "specialist": specialist,
        "urgency": urgency,
        "evidence_refs": refs,
        "unknowns": unknowns,
        "summary": summary,
        "next_action": next_action,
        "next_reassessment_at": next_at.isoformat(),
        "terminal_state": terminal_state,
    }
    # Scheduling is worker state, not new domain evidence.  Excluding it keeps a
    # repeated collector observation an exact replay instead of manufacturing a
    # new case generation every five minutes.
    digest_material = {key: value for key, value in material.items()
                       if key != "next_reassessment_at"}
    digest_material["evidence_refs"] = [ref for ref in refs
                                        if not str(ref).startswith("observed:")]
    digest = _digest(digest_material)
    return {**material, "case_id": "OOM-CASE-" + hashlib.sha256(dedupe.encode()).hexdigest()[:24].upper(),
            "evidence_digest": digest}


class PostgresManagerCaseStore:
    def __init__(self, connect_factory=None):
        self.connect_factory = connect_factory or (
            lambda: connect_bounded_postgres(read_only=False))

    def run_cycle(self, candidates: Iterable[Mapping[str, Any]], *, now: datetime,
                  source_revision: str, deliver: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                  refresh: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
                  brain_guard_audit: Mapping[str, Any] | None = None):
        now = _aware(now)
        brain_guard = dict(brain_guard_audit or build_scheduled_brain_guard_audit(
            source_revision=source_revision, now=now))
        cycle_id = ("OOM-MANAGER-CYCLE-" + now.strftime("%Y%m%dT%H%M%S%fZ-")
                    + uuid.uuid4().hex.upper())
        next_cycle = now + CADENCE
        created = changed = replayed = 0
        claimed: list[dict[str, Any]] = []
        connection = None
        try:
            with self.connect_factory() as audit_connection:
                with audit_connection.cursor() as cur:
                    cur.execute("""insert into app_private.oom_manager_worker_cycles
                        (cycle_id,worker_id,trigger_identity,source_revision,started_at,heartbeat_at,
                         next_cycle_at,status,case_counts) values(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                        (cycle_id, WORKER_ID, TRIGGER_IDENTITY, source_revision, now, now,
                         next_cycle, "started",
                         json.dumps({"brain_guard": brain_guard})))
            if brain_guard.get("passed") is not True:
                raise ManagerCaseError("scheduled_brain_guard_alignment_failed")
            connection = self.connect_factory()
            with connection:
                with connection.cursor() as cur:
                    normalized_candidates = sorted(
                        (normalize_candidate(raw, now=now) for raw in candidates),
                        key=lambda item: item["case_id"])
                    for candidate in normalized_candidates:
                        result = self._reconcile(cur, candidate, now)
                        if candidate["specialist"] == "BEACON":
                            self._retire_stale_beacon_claims(cur, candidate["dedupe_key"], now)
                        created += result == "created"
                        changed += result == "changed"
                        replayed += result == "replayed"
                    cur.execute("""select case_id,dedupe_key,specialist,urgency,status,evidence_digest,
                            evidence_refs,unknowns,summary,next_action,next_reassessment_at,generation,
                            last_delivery_digest
                        from app_private.oom_manager_cases
                        where status in ('open','delegated','waiting_reassessment','exception')
                          and next_reassessment_at<=%s
                          and (lease_until is null or lease_until<%s)
                        order by case when specialist='BEACON' then 0 else 1 end,
                            case urgency when 'critical' then 0 when 'urgent' then 1
                            when 'due' then 2 when 'planned' then 3 else 4 end,
                            next_reassessment_at,case_id
                        for update skip locked limit 20""", (now, now))
                    for row in cur.fetchall():
                        case = _case_row(row)
                        cur.execute("""update app_private.oom_manager_cases set
                            assigned_worker_id=%s,lease_until=%s,last_heartbeat_at=%s,
                            status='delegated',updated_at=%s where case_id=%s""",
                            (cycle_id, now + LEASE, now, now, case["case_id"]))
                        self._event(cur, case, "claimed", now, cycle_id=cycle_id)
                        self._event(cur, case, "delegated", now, cycle_id=cycle_id,
                                    specialist=case["specialist"])
                        claimed.append(case)
            delivered = suppressed = exceptions = 0
            case_results = []
            for case in claimed:
                current_case = case
                refresh_eligible = case.get("specialist") in {"HERDMASTER", "ROOTLINE", "BEACON"}
                if (deliver and refresh_eligible
                        and case.get("last_delivery_digest") != case["evidence_digest"]):
                    current_case = (self._refresh_claim(case, refresh(case),
                        _aware(datetime.now(timezone.utc)), cycle_id) if refresh else None)
                if current_case is None:
                    current_case = case
                    outcome = {"success": False,
                        "status": "manager_delivery_refresh_unavailable",
                        "delivery_confirmed": False, "telegram_sends": 0}
                elif current_case.pop("_refreshed_generation", False):
                    outcome = {"success": True,
                        "status": "manager_delivery_refreshed_generation_deferred",
                        "delivery_confirmed": False, "telegram_sends": 0}
                elif (deliver and current_case.get("last_delivery_digest")
                        != current_case["evidence_digest"]):
                    outcome = dict(deliver(current_case) or {})
                else:
                    duplicate = (current_case.get("last_delivery_digest")
                                 == current_case["evidence_digest"])
                    outcome = {
                    "success": True, "status": "manager_delivery_disabled",
                    "delivery_confirmed": False, "telegram_sends": 0,
                    "next_reassessment_at": (now + CADENCE).isoformat(),
                    }
                    if duplicate:
                        outcome["status"] = "manager_delivery_duplicate_suppressed"
                provider_confirmed = bool(outcome.get("success") is True
                    and outcome.get("delivery_confirmed") is True)
                persisted = self._finish_claim(current_case, outcome,
                    _aware(datetime.now(timezone.utc)), cycle_id)
                confirmed = provider_confirmed and persisted
                if provider_confirmed and not persisted:
                    outcome = {**outcome, "success": False,
                        "status": "manager_delivery_confirmation_persistence_unproven"}
                delivered += confirmed
                suppressed += not confirmed
                exceptions += outcome.get("success") is False
                case_results.append({"case_id": current_case["case_id"],
                    "specialist": current_case["specialist"], "urgency": current_case["urgency"],
                    "summary": current_case["summary"], "next_action": current_case["next_action"],
                    "unknowns": current_case["unknowns"], "outcome_status": outcome.get("status"),
                    "delivery_confirmed": confirmed,
                    "next_reassessment_at": str(outcome.get("next_reassessment_at")
                        or current_case["next_reassessment_at"])})
            counts = {"candidates_created": created, "candidates_changed": changed,
                "candidate_replays": replayed, "cases_claimed": len(claimed),
                "deliveries_confirmed": delivered, "deliveries_suppressed": suppressed,
                "exceptions": exceptions, "brain_guard": brain_guard}
            with self.connect_factory() as cycle_connection:
                with cycle_connection.cursor() as cur:
                    cur.execute("""update app_private.oom_manager_worker_cycles set heartbeat_at=%s,
                        next_cycle_at=%s,status='completed',case_counts=%s::jsonb,completed_at=%s
                        where cycle_id=%s""", (now, next_cycle, json.dumps(counts), now, cycle_id))
            return {"success": True, "status": "general_manager_cycle_completed",
                "contract_version": CONTRACT_VERSION, "worker_id": WORKER_ID,
                "cycle_id": cycle_id, "heartbeat_at": now.isoformat(),
                "next_cycle_at": next_cycle.isoformat(), "case_results": case_results,
                **counts, **_zero_effects()}
        except Exception as exc:
            failure = {"kind": exc.__class__.__name__}
            sqlstate = str(getattr(exc, "sqlstate", "") or "").strip()
            if sqlstate:
                failure["sqlstate"] = sqlstate
            if isinstance(exc, ManagerCaseError):
                failure["code"] = str(exc)
            failure_counts = {"brain_guard": brain_guard, "failure": failure}
            try:
                with self.connect_factory() as failure_connection:
                    with failure_connection.cursor() as cur:
                        cur.execute("""insert into app_private.oom_manager_worker_cycles
                            (cycle_id,worker_id,trigger_identity,source_revision,started_at,heartbeat_at,
                             next_cycle_at,status,case_counts,completed_at)
                            values(%s,%s,%s,%s,%s,%s,%s,'failed',%s::jsonb,%s)
                            on conflict(cycle_id) do update set status='failed',heartbeat_at=excluded.heartbeat_at,
                              next_cycle_at=excluded.next_cycle_at,case_counts=excluded.case_counts,
                              completed_at=excluded.completed_at""",
                            (cycle_id, WORKER_ID, TRIGGER_IDENTITY, source_revision, now, now,
                             next_cycle, json.dumps(failure_counts), now))
            except Exception:
                pass
            return {"success": False, "status": "general_manager_cycle_failed",
                "failure_kind": exc.__class__.__name__,
                "worker_id": WORKER_ID, "cycle_id": cycle_id,
                "heartbeat_at": now.isoformat(), "next_cycle_at": next_cycle.isoformat(),
                "brain_guard": brain_guard,
                **_zero_effects()}
        finally:
            if connection is not None:
                connection.close()

    def _reconcile(self, cur, candidate, now, *, lease_owner=None,
                   replace_delegated_owner=False):
        cur.execute("""select evidence_digest,generation,status,assigned_worker_id,lease_until,
                evidence_refs
            from app_private.oom_manager_cases where dedupe_key=%s for update""",
                    (candidate["dedupe_key"],))
        prior = cur.fetchone()
        if candidate.get("terminal_state") == "completed":
            if not prior:
                return "replayed"
            if prior[2] == "completed" and prior[0] == candidate["evidence_digest"]:
                return "replayed"
            generation = int(prior[1]) + 1
            cur.execute("""update app_private.oom_manager_cases set status='completed',
                evidence_digest=%s,evidence_refs=%s::jsonb,unknowns='[]'::jsonb,
                summary=%s,next_action=%s,next_reassessment_at=%s,generation=%s,
                assigned_worker_id=null,lease_until=null,updated_at=%s where dedupe_key=%s""",
                (candidate["evidence_digest"], json.dumps(candidate["evidence_refs"]),
                 candidate["summary"], candidate["next_action"],
                 _time(candidate["next_reassessment_at"], "next_reassessment_at"),
                 generation, now, candidate["dedupe_key"]))
            self._event(cur, {**candidate, "generation": generation}, "completed", now)
            return "changed"
        if (prior and candidate["specialist"] == "BEACON"
                and prior[0] != candidate["evidence_digest"]):
            current_provider = f"scheduled:{candidate['case_id']}:G{int(prior[1])}"
            cur.execute("""select 1
                from app_private.beacon_protected_publication_consumers p
                join app_private.oom_protected_action_claims c
                  on c.callback_token=p.callback_token
                where p.status='claimed' and c.action_kind='beacon_campaign_review'
                  and c.provider_message_id=%s limit 1""", (current_provider,))
            if cur.fetchone():
                return "deferred"
        if (prior and prior[4] and prior[4] >= now
                and str(prior[3] or "") != str(lease_owner or "")):
            return "deferred"
        if prior and prior[0] == candidate["evidence_digest"]:
            candidate_epoch = _evidence_epoch(candidate["evidence_refs"])
            prior_epoch = _evidence_epoch(prior[5])
            if candidate_epoch and (not prior_epoch or candidate_epoch > prior_epoch):
                cur.execute("""update app_private.oom_manager_cases
                    set evidence_refs=%s::jsonb,updated_at=%s where dedupe_key=%s""",
                    (json.dumps(candidate["evidence_refs"]), now, candidate["dedupe_key"]))
            return "replayed"
        if (prior and _evidence_epoch(candidate["evidence_refs"])
                and _evidence_epoch(prior[5])
                and _evidence_epoch(candidate["evidence_refs"]) < _evidence_epoch(prior[5])):
            return "stale"
        # A delegated generation owns immutable evidence until its delivery
        # lifecycle finishes.  An expired lease may be reclaimed only for that
        # same generation; it must never permit a newer generation while an old
        # process could still resume at the provider boundary.
        if (prior and prior[2] == "delegated" and (
                str(prior[3] or "") != str(lease_owner or "")
                or not replace_delegated_owner)):
            return "replayed"
        generation = int(prior[1]) + 1 if prior else 1
        cur.execute("""insert into app_private.oom_manager_cases
            (case_id,dedupe_key,specialist,urgency,status,evidence_digest,evidence_refs,unknowns,
             summary,next_action,next_reassessment_at,generation,created_at,updated_at)
            values(%s,%s,%s,%s,'open',%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s)
            on conflict(dedupe_key) do update set specialist=excluded.specialist,
              urgency=excluded.urgency,status='open',evidence_digest=excluded.evidence_digest,
              evidence_refs=excluded.evidence_refs,unknowns=excluded.unknowns,summary=excluded.summary,
              next_action=excluded.next_action,next_reassessment_at=excluded.next_reassessment_at,
              generation=excluded.generation,assigned_worker_id=null,lease_until=null,
              updated_at=excluded.updated_at""", (candidate["case_id"], candidate["dedupe_key"],
              candidate["specialist"], candidate["urgency"], candidate["evidence_digest"],
              json.dumps(candidate["evidence_refs"]), json.dumps(candidate["unknowns"]),
              candidate["summary"], candidate["next_action"],
              _time(candidate["next_reassessment_at"], "next_reassessment_at"), generation, now, now))
        event_case = {**candidate, "generation": generation}
        self._event(cur, event_case, "created" if not prior else "evidence_changed", now)
        return "created" if not prior else "changed"

    @staticmethod
    def _retire_stale_beacon_claims(cur, dedupe_key, now):
        """Make every older scheduled BEACON card permanently non-actionable."""
        cur.execute("""select case_id,generation from app_private.oom_manager_cases
            where dedupe_key=%s and specialist='BEACON' for update""", (dedupe_key,))
        current = cur.fetchone()
        if not current:
            raise ManagerCaseError("beacon_manager_case_missing_during_claim_retirement")
        current_provider = f"scheduled:{current[0]}:G{int(current[1])}"
        case_provider_pattern = f"scheduled:{current[0]}:G%"
        reason = json.dumps({
            "status": "beacon_campaign_claim_superseded_by_current_manager_generation",
            "current_manager_case_id": str(current[0]),
            "current_generation": int(current[1]),
            "invalidated_at": now.isoformat(),
            "publishes": False,
            "spends_money": False,
        }, sort_keys=True)
        cur.execute("""update app_private.oom_protected_action_claims c
            set status='changed',
                result_payload=coalesce(result_payload,'{}'::jsonb) || %s::jsonb,
                completed_at=coalesce(completed_at,%s)
            where c.action_kind='beacon_campaign_review'
              and c.provider_message_id like 'scheduled:%%'
              and c.provider_message_id like %s
              and c.provider_message_id<>%s
              and c.status in ('active','executing','completed')
              and not exists (
                select 1 from app_private.beacon_protected_publication_consumers p
                where p.callback_token=c.callback_token)""",
            (reason, now, case_provider_pattern, current_provider))

    def _finish_claim(self, case, outcome, now, cycle_id):
        confirmed = bool(outcome.get("success") is True
                         and outcome.get("delivery_confirmed") is True)
        failed = outcome.get("success") is False
        provider_ambiguity_contained = bool(
            failed
            and outcome.get("provider_outcome_ambiguous") is True
            and outcome.get("do_not_retry_provider_effect") is True)
        state = "contained" if provider_ambiguity_contained else (
            "exception" if failed else "waiting_reassessment")
        event_type = "contained" if provider_ambiguity_contained else (
            "exception" if failed else ("delivery_confirmed" if confirmed else "delivery_suppressed"))
        next_at = _time(outcome.get("next_reassessment_at") or case["next_reassessment_at"], "next_reassessment_at")
        # Provider ambiguity is a terminal boundary for this immutable
        # generation.  The case stays visibly contained and unconfirmed, while
        # exact replay cannot repeatedly approach the provider.  Genuinely
        # changed canonical evidence still reopens a successor in _reconcile.
        with self.connect_factory() as connection:
            with connection.cursor() as cur:
                cur.execute("""select generation,evidence_digest,last_delivery_digest,status,
                        assigned_worker_id,lease_until
                    from app_private.oom_manager_cases where case_id=%s for update""",
                            (case["case_id"],))
                current = cur.fetchone()
                if (not current or int(current[0]) != int(case["generation"])
                        or current[1] != case["evidence_digest"]
                        or str(current[4] or "") != cycle_id
                        or not current[5] or current[5] < now):
                    return False
                # Provider-confirmed delivery is monotonic for one immutable
                # generation.  A reclaimed expired-lease worker may finish
                # later, but its ambiguous/failed outcome cannot downgrade the
                # already confirmed result.
                if (current[2] == case["evidence_digest"] and not confirmed
                        and outcome.get("status") != "manager_delivery_duplicate_suppressed"):
                    return True
                delivery_digest = case["evidence_digest"] if confirmed else None
                cur.execute("""update app_private.oom_manager_cases set status=%s,
                    next_reassessment_at=%s,assigned_worker_id=null,lease_until=null,last_heartbeat_at=%s,
                    last_delivery_digest=coalesce(%s,last_delivery_digest),
                    last_delivery_at=case when %s then %s else last_delivery_at end,updated_at=%s
                    where case_id=%s""", (state, next_at, now, delivery_digest, confirmed, now, now, case["case_id"]))
                self._event(cur, case, event_type, now, cycle_id=cycle_id,
                            outcome_status=str(outcome.get("status") or ""),
                            provider_ambiguity_contained=provider_ambiguity_contained)
                self._event(cur, case, "reassessment_scheduled", now,
                            next_reassessment_at=next_at.isoformat())
        return True

    def _refresh_claim(self, claimed, raw, now, cycle_id):
        """Bind delivery to the newest canonical generation under the case lock."""
        if raw is None:
            return None
        candidate = normalize_candidate(raw, now=now)
        if candidate["dedupe_key"] != claimed["dedupe_key"]:
            raise ManagerCaseError("refreshed_dedupe_key_mismatch")
        with self.connect_factory() as connection:
            with connection.cursor() as cur:
                cur.execute("""select generation,evidence_digest,assigned_worker_id,lease_until
                    from app_private.oom_manager_cases where dedupe_key=%s for update""",
                    (candidate["dedupe_key"],))
                ownership = cur.fetchone()
                if (not ownership
                        or int(ownership[0]) != int(claimed["generation"])
                        or ownership[1] != claimed["evidence_digest"]
                        or str(ownership[2] or "") != cycle_id
                        or not ownership[3] or ownership[3] < now):
                    return None
                self._reconcile(cur, candidate, now, lease_owner=cycle_id,
                    replace_delegated_owner=claimed.get("status") != "delegated")
                if candidate["specialist"] == "BEACON":
                    self._retire_stale_beacon_claims(cur, candidate["dedupe_key"], now)
                cur.execute("""select case_id,dedupe_key,specialist,urgency,status,evidence_digest,
                        evidence_refs,unknowns,summary,next_action,next_reassessment_at,generation,
                        last_delivery_digest
                    from app_private.oom_manager_cases where dedupe_key=%s for update""",
                    (candidate["dedupe_key"],))
                current = _case_row(cur.fetchone())
                cur.execute("""update app_private.oom_manager_cases set
                    assigned_worker_id=%s,lease_until=%s,last_heartbeat_at=%s,
                    status='delegated',updated_at=%s where case_id=%s""",
                    (cycle_id, now + LEASE, now, now, current["case_id"]))
                refreshed_generation = (
                    int(current["generation"]) != int(claimed["generation"])
                    or current["evidence_digest"] != candidate["evidence_digest"])
                if refreshed_generation:
                    self._event(cur, current, "claimed", now, cycle_id=cycle_id)
                    self._event(cur, current, "delegated", now, cycle_id=cycle_id,
                                specialist=current["specialist"])
        return {**current, "_refreshed_generation": refreshed_generation}

    @staticmethod
    def _event(cur, case, event_type, now, **payload):
        material = {"case_id": case["case_id"], "generation": int(case["generation"]),
                    "event_type": event_type, "occurred_at": now.isoformat(), **payload}
        event_id = "OOM-MANAGER-EVENT-" + _digest(material)[:32].upper()
        cur.execute("""insert into app_private.oom_manager_case_events
            (event_id,case_id,generation,event_type,event_payload,occurred_at)
            values(%s,%s,%s,%s,%s::jsonb,%s) on conflict(event_id) do nothing""",
            (event_id, case["case_id"], int(case["generation"]), event_type,
             json.dumps(material, sort_keys=True), now))


def run_general_manager_cycle(*, candidates=None, now=None, source_revision=None,
                              store=None, collectors=None, deliver=None):
    now = _aware(now or datetime.now(timezone.utc))
    refresh = None
    if candidates is None:
        from modules.oom_sakkie.manager_case_sources import (
            collect_manager_candidate, collect_manager_candidates)
        candidates = collect_manager_candidates(now=now, collectors=collectors)
        if collectors is None:
            from modules.telemetry.rootline_mixer_readiness_observer import (
                collect_mixer_readiness,
            )
            try:
                candidates.extend(collect_mixer_readiness(now=now))
            except Exception as exc:
                candidates.append({
                    "dedupe_key": "rootline-readiness:fertilizer-mixer-ch2",
                    "specialist": "ROOTLINE", "urgency": "urgent",
                    "evidence_refs": [f"collector:mixer_readiness:{exc.__class__.__name__}"],
                    "unknowns": ["current_provider_mixer_readiness"],
                    "summary": "ROOTLINE fertilizer mixer readiness could not be observed.",
                    "next_action": ("Keep mixer execution fail-closed and retry the existing "
                                    "zero-control-call readback on the next manager cycle."),
                    "next_reassessment_at": (now + CADENCE).isoformat(),
                })
        def refresh(case):
            if str(case.get("dedupe_key") or "").startswith("rootline-readiness:"):
                from modules.telemetry.rootline_mixer_readiness_observer import (
                    collect_mixer_readiness,
                )
                rows = collect_mixer_readiness(now=datetime.now(timezone.utc))
                return next((row for row in rows
                    if row.get("dedupe_key") == case.get("dedupe_key")), None)
            return collect_manager_candidate(now=datetime.now(timezone.utc),
                dedupe_key=case["dedupe_key"], specialist=case["specialist"],
                collectors=collectors)
    revision = str(source_revision or os.getenv("RENDER_GIT_COMMIT") or os.getenv("RENDER_COMMIT") or "unknown")
    brain_guard = build_scheduled_brain_guard_audit(source_revision=revision, now=now)
    return (store or PostgresManagerCaseStore()).run_cycle(
        candidates, now=now, source_revision=revision, deliver=deliver,
        refresh=refresh, brain_guard_audit=brain_guard)


def deliver_farm_manager_case(case: Mapping[str, Any], *, now=None, deliver=None):
    """Present changed farm cases through the existing owner-only lifecycle."""
    if str(case.get("dedupe_key") or "").startswith("rootline-readiness:"):
        return {"success": True, "status": "readiness_attention_only",
                "delivery_confirmed": False, "telegram_sends": 0,
                "customer_sends": 0, "provider_actions": 0,
                "hardware_commands": 0, "writes_farm_data": False}
    specialist = str(case.get("specialist") or "").upper()
    if specialist not in {"HERDMASTER", "ROOTLINE", "BEACON"}:
        return {"success": True, "status": "non_farm_case_delivery_suppressed",
                "delivery_confirmed": False, "telegram_sends": 0}
    owners = [value.strip() for value in str(
        os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",")
        if value.strip()]
    if not owners:
        return {"success": False, "status": "manager_owner_binding_unavailable",
                "delivery_confirmed": False, "telegram_sends": 0}
    owner = owners[0]
    observed = _generation_timestamp(case["case_id"], int(case["generation"]))
    mission_id = f"{case['case_id']}:G{int(case['generation'])}"
    if specialist == "BEACON":
        from modules.oom_sakkie.beacon_request_runtime import (
            build_scheduled_sale_ready_stock_result, prepare_campaign_owner_card,
        )
        try:
            result = build_scheduled_sale_ready_stock_result()
        except Exception as exc:
            return {"success": False, "status": "beacon_canonical_evidence_unavailable",
                    "failure_kind": exc.__class__.__name__, "delivery_confirmed": False,
                    "telegram_sends": 0, "customer_sends": 0, "publishes": False,
                    "spends_money": False, "writes_farm_data": False}
        expected = next((str(value).split(":", 1)[1] for value in case.get("evidence_refs") or ()
                         if str(value).startswith("beacon_result:")), "")
        if not expected or result.get("result_digest") != expected:
            return {"success": False, "status": "beacon_material_evidence_changed_before_delivery",
                    "delivery_confirmed": False, "telegram_sends": 0, "customer_sends": 0,
                    "publishes": False, "spends_money": False, "writes_farm_data": False}
        if (result.get("proposal") or {}).get("protected_campaign_package"):
            try:
                result.update(prepare_campaign_owner_card(result["proposal"],
                    owner_user_id=owner, private_chat_id=owner,
                    provider_message_id="scheduled:" + mission_id,
                    packet_generation=f"G{int(case['generation'])}"))
            except Exception as exc:
                return {"success": False, "status": "beacon_protected_card_contained",
                    "failure_kind": exc.__class__.__name__, "delivery_confirmed": False,
                    "telegram_sends": 0, "customer_sends": 0, "publishes": False,
                    "spends_money": False, "writes_farm_data": False}
    else:
        result = None
    unknowns = tuple(str(value) for value in case.get("unknowns") or ())
    if result is None and not unknowns:
        return {"success": True, "status": "no_owner_question_delivery_suppressed",
                "delivery_confirmed": False, "telegram_sends": 0,
                "writes_farm_data": False, "hardware_commands": 0}
    lines = [f"<b>OOM SAKKIE — {specialist} CURRENT CASE</b>", "",
             html.escape(str(case.get("summary") or "Current farm case.")), "",
             "<b>Next:</b> " + html.escape(str(case.get("next_action") or "Reassess current canonical evidence.")),
             "Oom Sakkie will check this again automatically."]
    if unknowns:
        lines.extend(("", "<b>Still unproven:</b> " + html.escape("; ".join(unknowns))))
    if result is None:
        result = {"success": True, "status": "general_manager_case_ready",
                  "answer": "\n".join(lines), "result_digest": case["evidence_digest"],
                  "hardware_commands": 0, "writes_farm_data": False}
    parsed = {"telegram_user_id": owner, "telegram_chat_id": owner,
              "provider_message_id": "scheduled:" + mission_id,
              "provider_timestamp": observed.isoformat(), "text": "General Manager case"}
    if deliver is None:
        from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
        deliver = deliver_family_result
    outcome = dict(deliver(parsed, result, specialist=specialist,
                           mission_id=mission_id, card_mission_id=case["case_id"]) or {})
    if result.get("callback_token") and outcome.get("telegram_message_id"):
        from modules.oom_sakkie.protected_action_claims import bind_claim_card
        if not bind_claim_card(result["callback_token"], outcome["telegram_message_id"]):
            return {**outcome, "success": False, "delivery_confirmed": False,
                "status": "beacon_protected_card_binding_failed"}
    confirmed = bool(outcome.get("telegram_message_id") and (
        outcome.get("provider_delivery_confirmed") is True
        or (outcome.get("success") is True and int(outcome.get("telegram_edits") or 0) == 1)))
    return {**outcome, "delivery_confirmed": confirmed,
            "success": outcome.get("success") is True and confirmed}


def _case_row(row):
    keys = ("case_id","dedupe_key","specialist","urgency","status","evidence_digest",
            "evidence_refs","unknowns","summary","next_action","next_reassessment_at",
            "generation","last_delivery_digest")
    value = dict(zip(keys, row)); value["next_reassessment_at"] = value["next_reassessment_at"].isoformat()
    return value


def _identity(value, field):
    text = str(value or "").strip()
    if not _ID.fullmatch(text): raise ManagerCaseError(field + "_invalid")
    return text


def _text(value, field, limit):
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit: raise ManagerCaseError(field + "_invalid")
    return text


def _bounded_strings(value, field, required=False):
    if not isinstance(value, (list, tuple)): raise ManagerCaseError(field + "_invalid")
    result = tuple(sorted({_text(item, field, 240) for item in value}))
    if required and not result: raise ManagerCaseError(field + "_required")
    if len(result) > 20: raise ManagerCaseError(field + "_too_many")
    return list(result)


def _time(value, field):
    try: parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc: raise ManagerCaseError(field + "_invalid") from exc
    if parsed.tzinfo is None: raise ManagerCaseError(field + "_timezone_required")
    return parsed.astimezone(timezone.utc)


def _aware(value):
    if value.tzinfo is None: raise ManagerCaseError("now_timezone_required")
    return value.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _evidence_epoch(refs):
    values = []
    for ref in refs or ():
        if not str(ref).startswith("observed:"):
            continue
        try:
            values.append(_time(str(ref).split(":", 1)[1], "evidence_observed_at"))
        except ManagerCaseError:
            continue
    return max(values) if values else None


def _generation_timestamp(case_id, generation):
    seconds = int(hashlib.sha256(f"{case_id}:G{generation}".encode()).hexdigest()[:8], 16)
    return datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)


def _zero_effects():
    return {"telegram_sends": 0, "telegram_edits": 0, "customer_sends": 0,
            "provider_actions": 0, "hardware_commands": 0, "writes_farm_data": False,
            "publishes": False, "callbacks_enabled": False}
