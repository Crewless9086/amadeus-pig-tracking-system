"""Audited replacement of one expired, never-attempted legacy mortality claim.

The old preview is not declared equivalent to the new one. Its complete claim
preimage is preserved in an immutable audit; only its status becomes changed.
The fresh successor requires the ordinary presentation and confirmation gates.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
import time

from modules.oom_sakkie import herdmaster_source_transaction as tx
from modules.oom_sakkie import retained_mortality_history as history

CONTRACT = "retained_mortality_orphan_replacement.v1"
EVENT = "retained_mortality_orphan_replaced"
FIELD = "orphan_predecessor"
KEY = "retained-mortality-orphan:"
BOUND = 128
CASE_BOUND = 8192


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _archive(claim):
    return {"claim_hash": history._sha(claim["callback_token"]),
        **{key: value for key, value in claim.items() if key != "callback_token"}}


def _identity(claim):
    return {"claim_hash": history._sha(claim["callback_token"]), **{key: claim[key] for key in
        ("action_kind", "owner_user_id", "private_chat_id", "mission_id", "provider_message_id",
         "preview_digest", "evidence_generation", "preview_payload", "created_at")}}


def _rows(cur, sql, params):
    cur.execute(sql, params)
    return [row[0] for row in cur.fetchall()]


def read_claims(cur, source, *, lock=False, extra_missions=()):
    """Do not drop terminal predecessors or same-provider competing claims."""
    missions = [source["mission_id"], *extra_missions]
    bridge = source.get("retained_repreview") or {}
    if bridge.get("claim_mission_id"):
        missions.append(bridge["claim_mission_id"])
    return _rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
        where mission_id=any(%s) or (owner_user_id=%s and private_chat_id=%s
          and (provider_message_id=%s or preview_payload->'provider_message_ids' ? %s))
        order by callback_token limit 129""" + (" for update" if lock else ""),
        (missions, source["owner_user_id"], source["chat_id"], source["provider_message_id"],
            source["provider_message_id"]))


def _original(source):
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_identity_reassessment_needed
    tx.require(retained_identity_reassessment_needed(source)
        and source.get("event_phase") == "preview_generated" and not source.get("operation_id")
        and not source.get("retained_repreview")
        and bool(source.get("provider_timestamp")) and bool(source.get("owner_text_verbatim"))
        and not tx.superseded_missions(source), "retained_orphan_original_source_unproven")


def _unattempted(claim, source, now):
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    payload = claim.get("preview_payload") or {}
    identity = payload.get("identity") or {}
    tx.require(claim["status"] == "active" and claim["delivery_state"] == "claim_created"
        and all(key in claim and claim[key] is None for key in history.EMPTY_MARKERS)
        and history._time(claim["created_at"]) < history._time(claim["expires_at"]) <= now
        and (claim["owner_user_id"], claim["private_chat_id"], claim["provider_message_id"])
            == (source["owner_user_id"], source["chat_id"], source["provider_message_id"])
        and claim["action_kind"] == "mortality" and payload.get("effect_kind") == "mortality"
        and payload.get("event_family") == "found_dead" and identity.get("resolved") is True
        and identity.get("pig_id") and identity.get("tag_number")
        and set(payload) == {"operation_id", "preview_sha256", "identity", "event_family", "effect_kind"}
        and payload.get("operation_id") and payload.get("preview_sha256") and claim["evidence_generation"]
        and claim["preview_digest"] == canonical_preview_digest("mortality", payload),
        "retained_orphan_predecessor_not_unattempted_expired")


def _case_events(cur, case, *, through=None):
    # The immutable anchor is checked independently of later manager noise.
    return _rows(cur, """select to_jsonb(e) from app_private.oom_manager_case_events e
        where case_id=%s""" + (" and occurred_at<=%s" if through else "") +
        " order by occurred_at,event_id limit 8193",
        (case["case_id"], through) if through else (case["case_id"],))


def continuation_events(cur, case, started, generation, now):
    """Verify old anchor in full; aggregate only exact, unchanged retry noise.

    Every other later event is retained under the existing continuation bound.
    The aggregate is an exact count/hash, not a truncated sample. This keeps a
    long-lived delivered card reviewable when routine manager retries grow.
    """
    prefix = _case_events(cur, case, through=started)
    tx.require(len(prefix) <= CASE_BOUND, "retained_orphan_case_history_incomplete")
    cur.execute("""with boundary as materialized (
        select min(occurred_at) as changed_at from app_private.oom_manager_case_events
        where case_id=%s and event_type='evidence_changed' and generation=%s+1), tail as materialized (
        select e.*,coalesce(
          e.generation=%s and e.occurred_at<=%s and
          e.occurred_at<=coalesce(b.changed_at,'infinity') and
          e.event_payload->>'case_id'=e.case_id and e.event_payload->'generation'=to_jsonb(e.generation) and
          e.event_payload->>'event_type'=e.event_type and
          e.event_payload->>'occurred_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' and
          (e.event_payload->>'occurred_at')::timestamptz=e.occurred_at and
          (not e.event_payload ? 'failure_kind' or e.event_payload->'failure_kind'='""'::jsonb) and
          (e.event_payload->'provider_ambiguity_contained' is null or
            e.event_payload->'provider_ambiguity_contained' in ('false'::jsonb,'null'::jsonb)) and
          e.event_payload-array['case_id','generation','event_type','occurred_at','cycle_id','specialist',
            'next_reassessment_at','outcome_status','failure_kind','provider_ambiguity_contained',
            'confirmed_generation_preserved']='{}'::jsonb and
          ((e.event_type in ('claimed','delegated','heartbeat','reassessment_scheduled') and
              (not e.event_payload ? 'outcome_status' or e.event_payload->'outcome_status'='""'::jsonb)) or
           (e.event_type in ('delivery_suppressed','reassessment_scheduled') and
              e.event_payload->>'outcome_status' in ('manager_delivery_duplicate_suppressed',
                'retained_mortality_continuation_owner_review'))),false) as quiet
        from app_private.oom_manager_case_events e cross join boundary b where e.case_id=%s and e.occurred_at>%s),
        significant as (select * from tail where not quiet order by occurred_at,event_id limit 4097)
        select (select coalesce(jsonb_agg(to_jsonb(s)-'quiet' order by occurred_at,event_id),'[]'::jsonb) from significant s),
          count(*),encode(sha256(convert_to(coalesce(string_agg((to_jsonb(t)-'quiet')::text,E'\\n' order by occurred_at,event_id),''),'UTF8')),'hex')
        from tail t where quiet""", (case["case_id"], generation, generation, now, case["case_id"], started))
    later, count, digest = cur.fetchone()
    tx.require(len(later) <= history.CASE_HISTORY_BOUND, "retained_continuation_case_history_bound")
    return prefix + later, {"unchanged_manager_events": count, "sha256": digest,
        "after": history._time(started).isoformat(), "through": history._time(now).isoformat(),
        "generation": generation}


def validate_case_history(events, case, now):
    """Only known pre-provider failures and monotonic manager generations."""
    tx.require(0 < len(events) <= CASE_BOUND
        and len({e["event_id"] for e in events}) == len(events)
        and sum(e["event_type"] == "created" for e in events) == 1,
        "retained_orphan_case_history_incomplete")
    transitions = sorted((e for e in events if e["event_type"] in {"created", "evidence_changed"}),
        key=lambda e: e["generation"])
    tx.require([e["generation"] for e in transitions] == list(range(1, int(case["generation"]) + 1)),
        "retained_orphan_case_generations_unproven")
    boundaries = {e["generation"]: history._time(e["occurred_at"]) for e in transitions}
    tx.require(list(boundaries.values()) == sorted(boundaries.values()), "retained_orphan_case_chronology_unproven")
    safe_failures = {"manager_delivery_refresh_unavailable", "retained_claim_current_preview_mismatch",
        "manager_cycle_deadline_deferred", "family_message_cycle_deadline_deferred",
        "retained_mortality_presend_statement_deferred", "retained_mortality_removed_disposal_required",
        "retained_protected_repreview_unproven"}
    safe_success = {"retained_mortality_prepared_not_presented", "manager_delivery_refreshed_generation_deferred"}
    for event in events:
        payload = event["event_payload"]
        at, generation, kind = history._time(event["occurred_at"]), event["generation"], event["event_type"]
        outcome, failure = payload.get("outcome_status") or "", payload.get("failure_kind") or ""
        tx.require(event["case_id"] == payload.get("case_id") == case["case_id"]
            and generation == payload.get("generation") and generation in boundaries
            and kind == payload.get("event_type") and at == history._time(payload["occurred_at"]) <= now
            and boundaries[generation] <= at
            and (generation == case["generation"] or at <= boundaries[generation + 1])
            and not any(payload.get(k) for k in ("provider_ambiguity_contained", "delivery_confirmed",
                "provider_confirmed", "confirmed_generation_preserved", "provider_card_message_id",
                "delivery_attempt_id", "telegram_sends", "telegram_edits", "writes_farm_data"))
            and ((kind in {"created", "evidence_changed", "claimed", "delegated", "heartbeat", "reassessment_scheduled"}
                    and outcome == "" and failure == "")
                or (kind in {"exception", "delivery_suppressed", "reassessment_scheduled"}
                    and outcome in safe_failures and failure in {"", outcome})
                or (kind in {"delivery_suppressed", "reassessment_scheduled"}
                    and outcome in safe_success and failure == "")
                or (kind == "delivery_suppressed" and outcome == "mortality_preview_ready" and failure == ""
                    and payload.get("provider_ambiguity_contained") is False
                    and set(payload) == {"case_id", "cycle_id", "event_type", "failure_kind", "generation",
                        "occurred_at", "outcome_status", "provider_ambiguity_contained"})),
            "retained_orphan_unsafe_case_history")
        if outcome == "retained_mortality_presend_statement_deferred":
            tx.require(history._is_presend_statement_guard(event), "retained_orphan_statement_history_unproven")


def _family_rows(cur, source, claims):
    from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
    scopes = sorted({source["mission_id"], *[c["mission_id"] for c in claims],
        *[protected_card_mission_id(c["mission_id"], c["preview_digest"]) for c in claims]})
    cur.execute("""select review_event_id,created_at,review_json->'family_message_lifecycle'
        from public.sam_live_stock_conversation_review_events where event_source=%s and
        (chatwoot_conversation_id=any(%s) or review_json#>>'{family_message_lifecycle,mission_id}'=any(%s)
         or review_json#>>'{family_message_lifecycle,card_mission_id}'=any(%s))
        order by created_at,review_event_id limit 129""",
        ("oom_sakkie_family_message_lifecycle", scopes, scopes, scopes))
    return [{"review_event_id": r[0], "created_at": r[1], "record": r[2]} for r in cur.fetchall()]


def _no_effects(cur, predecessor, successor=None):
    pig = predecessor["preview_payload"]["identity"]["pig_id"]
    operations = sorted({c["preview_payload"]["operation_id"] for c in (predecessor, successor) if c})
    for operation in operations:
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("herdmaster-mortality:" + operation,))
    cur.execute("""select 1 from (
        select 1 from public.pig_lifecycle_events where idempotency_key=any(%s)
            or event_payload->>'operation_id'=any(%s) or (pig_id=%s and lifecycle_event_type='exited_farm')
        union all select 1 from public.pig_welfare_case_events e join public.pig_welfare_cases c using(welfare_case_id)
            where c.pig_id=%s and e.case_state='closed' and e.closure_kind='death'
        union all select 1 from public.operational_events where payload_json->>'operation_id'=any(%s)
        ) effects limit 1""", (operations, operations, pig, pig, operations))
    tx.require(cur.fetchone() is None, "retained_orphan_operation_effect_exists")


def _staged(source, preview, request, successor, event_id, predecessor_hash, now):
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    binding = preview["confirmation_binding"]
    return {**source, "status": "preview_ready", "event_phase": "retained_preview_generated:" + successor["preview_digest"][:24],
        "operation_id": binding["operation_id"], "preview": preview, "owner_text": preview["owner_text"],
        "evidence_generation": binding["evidence_generation"], "retained_repreview": {
            "contract_version": "retained_health_preview_v1", "source_binding": retained_report_binding([source]),
            "claim_mission_id": successor["mission_id"], "claim_preview_digest": successor["preview_digest"],
            "claim_evidence_generation": successor["evidence_generation"], "generated_at": history._time(now).isoformat(),
            FIELD: {"contract_version": CONTRACT, "event_id": event_id, "predecessor_claim_hash": predecessor_hash}}}


class _DeadlineCursor:
    def __init__(self, cursor, deadline):
        self.cursor, self.deadline = cursor, deadline
    def __enter__(self):
        self.cursor.__enter__()
        return self
    def __exit__(self, *args):
        return self.cursor.__exit__(*args)
    def execute(self, query, params=None):
        from modules.oom_sakkie.retained_mortality_presentation import require_admission_reserve
        require_admission_reserve(self.deadline)
        budget = 5000 if self.deadline is None else max(1, min(5000, int((self.deadline-time.monotonic()-30)*1000)))
        self.cursor.execute("select set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
            (str(budget), str(budget)))
        return self.cursor.execute(query, params)
    def __getattr__(self, key):
        return getattr(self.cursor, key)


class _DeadlineConnection(tx.BorrowedConnection):
    def __init__(self, connection, deadline):
        super().__init__(connection)
        self.deadline = deadline
    def cursor(self):
        return _DeadlineCursor(self.connection.cursor(), self.deadline)


class _RolledBackPreparation(Exception):
    pass


@contextmanager
def _preparation_transaction(factory):
    from modules.oom_sakkie.retained_mortality_presentation import _statement_timeout
    deferred = None
    with factory() as db:
        try:
            yield db
        except Exception as exc:
            if not (isinstance(exc, TimeoutError) or _statement_timeout(exc)):
                raise
            db.rollback()
            deferred = exc
    if deferred is not None:
        raise _RolledBackPreparation() from deferred


def prepare(source, case, *, deadline_monotonic=None, connect_factory=None):
    try:
        return _prepare(source, case, deadline_monotonic=deadline_monotonic, connect_factory=connect_factory)
    except _RolledBackPreparation:
        return {"success":False,"status":"manager_cycle_deadline_deferred","suppress_owner_delivery":True,
            "telegram_sends":0,"telegram_edits":0,"writes_farm_data":False,
            "protected_actions_performed":False,"delivery_definitely_not_sent":True}


def _prepare(source, case, *, deadline_monotonic=None, connect_factory=None):
    """One atomic metadata transition; never a provider attempt or confirmation."""
    from modules.oom_sakkie.protected_delivery_lifecycle import _connect
    from modules.oom_sakkie.protected_action_claims import create_claim
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as retained
    from modules.oom_sakkie.herdmaster_health_loss_runtime import load_canonical_health_loss_evidence, _record_lifecycle_event
    from modules.oom_sakkie.retained_mortality_presentation import require_admission_reserve
    with _preparation_transaction(connect_factory or _connect) as db, db.cursor() as cur:
        require_admission_reserve(deadline_monotonic)
        tx.begin(cur)
        cur = _DeadlineCursor(cur, deadline_monotonic)
        tx.lock_sources(cur, source["owner_user_id"], source["chat_id"], [source["mission_id"]])
        rows = tx.read_history(cur, [source["mission_id"]])
        source = tx.require_current(rows, source)
        _original(source)
        tx.require(all(item["record"] == source for item in rows), "retained_orphan_original_history_changed")
        claims = read_claims(cur, source, lock=True)
        predecessor = history._one(claims, "retained_orphan_predecessor")
        cur.execute("select clock_timestamp()")
        now = cur.fetchone()[0]
        tx.require(all(history._time(r["created_at"]) <= history._time(predecessor["created_at"]) for r in rows),
            "retained_orphan_source_chronology_unproven")
        _unattempted(predecessor, source, now)
        tx.require(retained.retained_recipient_authorized(retained._delivery_context(source)), "retained_orphan_recipient_changed")
        current = history._one(_rows(cur, """select to_jsonb(c) from app_private.oom_manager_cases c
            where case_id=%s for update""", (case["case_id"],)), "retained_orphan_case")
        tx.require(all(current.get(k) == case.get(k) for k in ("case_id", "dedupe_key", "generation", "evidence_digest"))
            and current["specialist"] == "HERDMASTER" and current["status"] in {"open", "delegated", "waiting_reassessment", "exception"}
            and current["dedupe_key"] == "herdmaster:retained-mortality:" + source["provider_message_id"]
            and current["last_delivery_digest"] is None and current["last_delivery_at"] is None,
            "retained_orphan_case_changed")
        events = _case_events(cur, current)
        validate_case_history(events, current, now)
        # No missing/partial historical provider ledger licenses replacement.
        family = _family_rows(cur, source, claims)
        tx.require(not family, "retained_orphan_family_history_requires_review")
        old_hash = history._sha(predecessor["callback_token"])
        audits = _rows(cur, """select to_jsonb(e) from public.operational_events e
            where aggregate_type='protected_action_claim' and aggregate_id=%s limit 129""", (old_hash,))
        tx.require(not audits, "retained_orphan_prior_audit_exists")
        reader = tx.TransactionReader(_DeadlineConnection(db, deadline_monotonic))
        budget = 6 if deadline_monotonic is None else min(6, deadline_monotonic-time.monotonic()-30)
        require_admission_reserve(deadline_monotonic)
        evidence = load_canonical_health_loss_evidence(connect_factory=reader, deadline_seconds=budget)
        preview = retained._prepare_retained_report(source, evidence)
        evaluated, binding = preview.get("evaluator") or {}, preview.get("confirmation_binding") or {}
        identity = evaluated.get("identity") or {}
        tx.require(preview.get("success") is True and preview.get("confirmation_ready") is True
            and preview.get("question_count") == 0 and evaluated.get("event_family") == "found_dead"
            and identity == predecessor["preview_payload"]["identity"] and binding.get("operation_id")
            and {r for r in current["evidence_refs"] if r.startswith("pig:")} == {"pig:" + identity["pig_id"]}
            and {r for r in current["evidence_refs"] if r.startswith("tag:")} == {"tag:" + identity["tag_number"]}
            and retained.retained_report_binding([source]) in current["evidence_refs"],
            "retained_orphan_fresh_report_unproven")
        operation = binding["operation_id"]
        mission = "OOM-HERDMASTER-MORTALITY-" + hashlib.sha256(
            (source["provider_message_id"] + "|" + identity["pig_id"] + "|" + operation).encode()).hexdigest()[:24].upper()
        request = {"action_kind": "mortality", "owner_user_id": source["owner_user_id"], "private_chat_id": source["chat_id"],
            "mission_id": mission, "provider_message_id": source["provider_message_id"], "evidence_generation": evidence["evidence_generation"],
            "preview_payload": {"operation_id": operation, "preview_sha256": binding["preview_sha256"], "identity": identity,
                "event_family": "found_dead", "effect_kind": "mortality"}}
        tx.require(mission != predecessor["mission_id"], "retained_orphan_successor_mission_not_distinct")
        tx.require(request["preview_payload"] != predecessor["preview_payload"], "retained_orphan_exact_claim_requires_reuse")
        lock_material = hashlib.sha256(("protected-claim|" + mission).encode()).hexdigest()
        cur.execute("select pg_advisory_xact_lock(%s)", (int(lock_material[:15], 16),))
        tx.require(read_claims(cur, source, lock=True, extra_missions=[predecessor["mission_id"], mission]) == [predecessor],
            "retained_orphan_competing_claim")
        _no_effects(cur, predecessor, request)
        require_admission_reserve(deadline_monotonic)
        tx.require(retained.retained_recipient_authorized(retained._delivery_context(source)), "retained_orphan_recipient_changed")
        cur.execute("""update app_private.oom_protected_action_claims c set status='changed'
            where callback_token=%s and to_jsonb(c)=%s::jsonb returning callback_token""",
            (predecessor["callback_token"], _json(predecessor)))
        tx.require(cur.rowcount == 1 and cur.fetchone() == (predecessor["callback_token"],), "retained_orphan_retirement_failed")
        created = create_claim(**request, connect_factory=reader, supersede_active=False)
        successor = history._one(_rows(cur, "select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s",
            (created["callback_token"],)), "retained_orphan_successor")
        event_id = "OOM-MORTALITY-ORPHAN-" + old_hash[:32].upper()
        next_source = tx.record_body(_staged(source, preview, request, successor, event_id, old_hash, now))
        payload = {"contract_version": CONTRACT, "predecessor": _archive(predecessor), "successor": _identity(successor),
            "source_before": source, "source_after": next_source, "case": current,
            "source_history_sha256": tx.digest(rows), "case_history_sha256": tx.digest(events),
            "family_history_sha256": tx.digest(family), "prior_audit_sha256": tx.digest(audits),
            "provider_attempts": 0, "farm_writes": 0, "confirmation_required": True, "equivalence_claimed": False}
        cur.execute("""insert into public.operational_events(event_id,idempotency_key,schema_version,event_type,domain,
            aggregate_type,aggregate_id,source_system,source_record_id,authority_tier,privacy_class,actor_type,actor_id,
            correlation_id,causation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json)
            values(%s,%s,'1',%s,'approvals','protected_action_claim',%s,'oom_sakkie',%s,'bounded_auto',
                'owner_private','system','retained_mortality_orphan_recovery',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            returning event_id""", (event_id, KEY + old_hash, EVENT, old_hash, current["case_id"], successor["mission_id"],
                source["mission_id"], now, now, now, _json(payload), _json({"source_ref": retained.retained_report_binding([source])})))
        tx.require(cur.rowcount == 1 and cur.fetchone() == (event_id,), "retained_orphan_audit_failed")
        saved = _record_lifecycle_event(next_source, expected_sources={source["mission_id"]: tx.digest(source)}, connect_factory=reader)
        tx.require(saved.get("success") is True, "retained_orphan_source_append_failed")
        current_rows = tx.read_history(cur, [source["mission_id"]])
        cur.execute("select clock_timestamp()")
        checked_at = cur.fetchone()[0]
        validate_lineage(cur, next_source, read_claims(cur, next_source), successor, checked_at, current_rows)
        require_admission_reserve(deadline_monotonic)
    return {"success": True, "status": "retained_mortality_prepared_not_presented", "suppress_owner_delivery": True,
        "telegram_sends": 0, "telegram_edits": 0, "writes_farm_data": False, "protected_actions_performed": False}


def validate_lineage(cur, source, claims, current, now, source_history):
    """Return the active ancestry only after verifying the exact retired edge."""
    link = (source.get("retained_repreview") or {}).get(FIELD)
    tx.require(isinstance(link, dict) and set(link) == {"contract_version", "event_id", "predecessor_claim_hash"}
        and link["contract_version"] == CONTRACT and 2 <= len(claims) <= BOUND,
        "retained_orphan_lineage_missing")
    audit = history._one(_rows(cur, "select to_jsonb(e) from public.operational_events e where event_id=%s limit 2",
        (link["event_id"],)), "retained_orphan_audit")
    p = audit["payload_json"]
    old_hash = link["predecessor_claim_hash"]
    old = history._one([c for c in claims if history._sha(c["callback_token"]) == old_hash], "retained_orphan_retired_claim")
    roots = [c for c in claims if history._sha(c["callback_token"]) == (p.get("successor") or {}).get("claim_hash")]
    root = history._one(roots, "retained_orphan_root_claim")
    before, after = p.get("source_before") or {}, p.get("source_after") or {}
    at = history._time(audit["occurred_at"])
    _original(before)
    preserved = {**old, "status": (p.get("predecessor") or {}).get("status")}
    _unattempted(preserved, before, at)
    tx.require(old["status"] == "changed" and _archive(preserved) == p.get("predecessor")
        and _identity(root) == p.get("successor") and root["callback_token"] != old["callback_token"]
        and root["preview_payload"]["identity"] == old["preview_payload"]["identity"]
        and all(root[k] == old[k] for k in ("owner_user_id", "private_chat_id", "provider_message_id", "action_kind"))
        and audit["event_type"] == EVENT and audit["idempotency_key"] == KEY + old_hash
        and audit["aggregate_type"] == "protected_action_claim" and audit["aggregate_id"] == old_hash
        and audit["source_system"] == "oom_sakkie" and audit["actor_type"] == "system"
        and audit["actor_id"] == "retained_mortality_orphan_recovery" and audit["authority_tier"] == "bounded_auto"
        and audit["correlation_id"] == root["mission_id"] and audit["causation_id"] == before["mission_id"]
        and audit["source_record_id"] == (p.get("case") or {}).get("case_id")
        and p.get("contract_version") == CONTRACT and p.get("provider_attempts") == 0 and p.get("farm_writes") == 0
        and p.get("confirmation_required") is True and p.get("equivalence_claimed") is False and at <= now,
        "retained_orphan_audit_changed")
    expected = _staged(before, after.get("preview") or {}, {}, root, audit["event_id"], old_hash, at)
    tx.require(after == expected, "retained_orphan_source_staging_changed")
    tx.require(before["mission_id"] == source["mission_id"] and source.get("preview") == after["preview"],
        "retained_orphan_current_source_changed")
    tx.require(all(any(r["record"] == body for r in source_history) for body in (before, after)),
        "retained_orphan_source_edge_changed")
    tx.require(tx.digest([r for r in source_history if history._time(r["created_at"]) <= at]) == p.get("source_history_sha256"),
        "retained_orphan_original_source_history_changed")
    retired_audits = _rows(cur, """select to_jsonb(e) from public.operational_events e
        where aggregate_type='protected_action_claim' and aggregate_id=%s order by occurred_at,event_id limit 129""", (old_hash,))
    tx.require(retired_audits == [audit] and p.get("prior_audit_sha256") == tx.digest([]), "retained_orphan_predecessor_audits_changed")
    archived = _case_events(cur, p["case"], through=at)
    tx.require(tx.digest(archived) == p.get("case_history_sha256"), "retained_orphan_original_case_history_changed")
    validate_case_history(archived, p["case"], at)
    family = _family_rows(cur, before, [old])
    tx.require(not family and p.get("family_history_sha256") == tx.digest([]), "retained_orphan_predecessor_family_changed")
    remaining = [c for c in claims if c["callback_token"] != old["callback_token"]]
    tx.require(current in remaining, "retained_orphan_current_claim_missing")
    return remaining, audit


def verify_completed_ancestry(cur, claim, result):
    """Read-only completion proof shared by native and scheduled retries."""
    mission = result["source_mission_id"]
    tx.lock_sources(cur, claim["owner_user_id"], claim["private_chat_id"], [mission])
    rows = tx.read_history(cur, [mission])
    if not any((r["record"].get("retained_repreview") or {}).get(FIELD) for r in rows):
        return
    source = tx.latest_for(rows, mission)
    tx.require(source is not None, "retained_orphan_completed_source_missing")
    tx.require_current(rows, source)
    bridge = source.get("retained_repreview") or {}
    tx.require(source["status"] == "completed" and bridge.get("claim_mission_id") == claim["mission_id"]
        and bridge.get("claim_preview_digest") == claim["preview_digest"]
        and source.get("operation_id") == result["operation_id"]
        and (source.get("recording_result") or {}).get("lifecycle_event_id") == result["lifecycle_event_id"],
        "retained_orphan_completed_source_changed")
    current = history._one(_rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
        where callback_token=%s for update""", (claim["callback_token"],)), "retained_orphan_completed_claim")
    # The recovery worker supplies a projection plus canonical readback hints,
    # not a whole claim row. Bind that projection, then validate the locked row.
    tx.require(all(current.get(k) == claim.get(k) for k in ("callback_token", "action_kind", "owner_user_id",
        "private_chat_id", "mission_id", "preview_digest", "evidence_generation", "preview_payload", "status",
        "result_payload", "preview_card_message_id", "confirmation_provider_message_id"))
        and history._time(current["confirmation_provider_timestamp"]) == history._time(claim["confirmation_provider_timestamp"])
        and current["status"] == "completed" and current["result_payload"] == result
        and source.get("provider_message_id") == current["confirmation_provider_message_id"]
        and history._time(source["provider_timestamp"]) == history._time(current["confirmation_provider_timestamp"]),
        "retained_orphan_completed_claim_changed")
    related = read_claims(cur, {**source, "provider_message_id": current["provider_message_id"]}, lock=True)
    cur.execute("select clock_timestamp()")
    observed = cur.fetchone()[0]
    if bridge.get("owner_requested_continuation"):
        from modules.oom_sakkie.retained_mortality_continuation import validate_lineage as continued_lineage
        continued_lineage(cur, source, related, current, observed, rows)
    else:
        active, _audit = validate_lineage(cur, source, related, current, observed, rows)
        tx.require(active == [current], "retained_orphan_competing_claim")


def verify_completed_callback(claimed, owner, chat, *, connect_factory=None):
    from modules.oom_sakkie.protected_delivery_lifecycle import _connect
    from modules.oom_sakkie.protected_payment_recovery import _verify_retained_completion
    factory = connect_factory or _connect
    with factory() as db, db.cursor() as cur:
        tx.begin(cur)
        current = history._one(_rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
            where mission_id=%s and preview_digest=%s and owner_user_id=%s and private_chat_id=%s limit 2""",
            (claimed["mission_id"], claimed["preview_digest"], owner, chat)), "retained_completed_callback_claim")
        tx.require(current["preview_payload"] == claimed["preview_payload"]
            and current["result_payload"] == claimed["result"], "retained_completed_callback_changed")
        _verify_retained_completion(current, claimed["result"], tx.TransactionReader(db))
