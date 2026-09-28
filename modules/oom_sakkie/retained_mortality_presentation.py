"""One retained-mortality presentation window at the real provider boundary.

Preparation objects are immutable, ephemeral hints, never provider authority.
Admission reloads canonical source, history, identity and facts under the source
fence; only its committed claim/audit transaction owns an attempt.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import time
import uuid

from modules.oom_sakkie import herdmaster_source_transaction as source_tx
from modules.oom_sakkie import retained_mortality_history as history

CONTRACT = "retained_mortality_presentation_window.v1"
KEY_PREFIX = "retained-mortality-window:"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class RetainedMortalityPresentation:
    source_json: str
    request_json: str
    case_json: str
    callback_token: str
    preview_digest: str


def stage(source, requested, claim, case):
    """Capture a provisional immutable rendering; the admission re-reads it."""
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    source_tx.require(requested.get("action_kind") == "mortality"
        and requested["preview_payload"].get("effect_kind") == "mortality"
        and source.get("status") == "preview_ready"
        and (source.get("retained_repreview") or {}).get("contract_version") == "retained_health_preview_v1"
        and canonical_preview_digest("mortality", requested["preview_payload"]) == claim["preview_digest"],
        "retained_mortality_stage_binding_unproven")
    return RetainedMortalityPresentation(_json(source), _json(requested),
        _json({key: case[key] for key in ("case_id", "dedupe_key", "generation", "evidence_digest")}),
        claim["callback_token"], claim["preview_digest"])


def _read_rows(cur, query, params):
    cur.execute(query, params)
    return [row[0] for row in cur.fetchall()]


def validate_material(source, claim, evidence):
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import _unchanged_retained_preview
    material = {key: evidence[key] for key in ("animals", "matings", "litters")}
    source_tx.require(evidence["evidence_generation"] == source_tx.digest(material)
        == claim["evidence_generation"], "retained_mortality_canonical_generation_changed")
    current = prepare_health_loss_owner_preview({
        "gateway_authority": issue_gateway_owner_authority(source["owner_user_id"], source["chat_id"]),
        "provider_message_id": source["provider_message_id"], "provider_timestamp": source["provider_timestamp"],
        "provider_timezone": "Africa/Johannesburg", "output_language": source.get("output_language") or "af",
        "text": source.get("combined_text") or source.get("owner_text_verbatim") or "",
        **({"report_parts": source["report_parts"]} if source.get("report_parts") else {}),
        **{key: value for key, value in (source.get("semantic_interpretation") or {}).items()
            if key in {"mortality_observation", "welfare_observation", "clinical_observation"}},
    }, evidence)
    current = _unchanged_retained_preview(source, current, evidence_generation=evidence["evidence_generation"])
    source_tx.require(current.get("success") is True and current.get("confirmation_ready") is True
        and current.get("question_count") == 0 and current == source["preview"],
        "retained_mortality_canonical_preview_changed")
    binding = current["confirmation_binding"]
    source_tx.require(current["evaluator"]["identity"] == claim["preview_payload"]["identity"]
        and binding["operation_id"] == claim["preview_payload"]["operation_id"]
        and binding["preview_sha256"] == claim["preview_payload"]["preview_sha256"],
        "retained_mortality_canonical_binding_changed")
    return current


def _validate_source(source, claim):
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    bridge = source.get("retained_repreview") or {}
    binding = (source.get("preview") or {}).get("confirmation_binding") or {}
    source_tx.require(source.get("status") == "preview_ready"
        and str(source.get("event_phase") or "").startswith("retained_preview_generated:")
        and (source["owner_user_id"], source["chat_id"], source["provider_message_id"]) ==
            (claim["owner_user_id"], claim["private_chat_id"], claim["provider_message_id"])
        and claim["action_kind"] == "mortality" and claim["preview_payload"].get("effect_kind") == "mortality"
        and claim["preview_digest"] == canonical_preview_digest("mortality", claim["preview_payload"])
        and source.get("operation_id") == binding.get("operation_id") == claim["preview_payload"]["operation_id"]
        and binding.get("preview_sha256") == claim["preview_payload"]["preview_sha256"]
        and bridge.get("contract_version") == "retained_health_preview_v1"
        and bridge.get("source_binding") == retained_report_binding([source])
        and bridge.get("claim_mission_id") == claim["mission_id"]
        and bridge.get("claim_preview_digest") == claim["preview_digest"]
        and bridge.get("claim_evidence_generation") == claim["evidence_generation"]
        and not any(source.get(key) for key in ("correction_digest", "invalidated_operation_ids",
            "consumed_context_missions", "superseded_duplicate_missions", "superseded_duplicate_bindings")),
        "retained_mortality_source_binding_unproven")


def _histories(cur, claim, source, source_history, expected_case, observed_at):
    from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
    providers = sorted({str(item["record"].get("provider_message_id") or "") for item in source_history} - {""})
    missions = [source["mission_id"], claim["mission_id"]]
    related = _read_rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
        where mission_id=any(%s) or (owner_user_id=%s and private_chat_id=%s
          and (provider_message_id=any(%s) or preview_payload->'provider_message_ids' ?| %s))
        order by callback_token limit 129""",
        (missions, claim["owner_user_id"], claim["private_chat_id"], providers, providers))
    source_tx.require(related == [claim], "retained_mortality_competing_claim")
    cases = _read_rows(cur, "select to_jsonb(m) from app_private.oom_manager_cases m where case_id=%s for update",
        (expected_case["case_id"],))
    case = history._one(cases, "retained_mortality_case")
    source_tx.require(all(case.get(key) == value for key, value in expected_case.items())
        and case["specialist"] == "HERDMASTER" and case["status"] in {"open", "delegated", "waiting_reassessment", "exception"}
        and case["dedupe_key"] == "herdmaster:retained-mortality:" + claim["provider_message_id"]
        and case["last_delivery_digest"] is None and case["last_delivery_at"] is None
        and "pig:" + claim["preview_payload"]["identity"]["pig_id"] in case["evidence_refs"],
        "retained_mortality_case_changed")
    family_missions = missions + [protected_card_mission_id(claim["mission_id"], claim["preview_digest"])]
    cur.execute("""select review_event_id,created_at,review_json->'family_message_lifecycle'
        from public.sam_live_stock_conversation_review_events where event_source=%s and
        (chatwoot_conversation_id=any(%s) or review_json->'family_message_lifecycle'->>'mission_id'=any(%s)
          or review_json->'family_message_lifecycle'->>'card_mission_id'=any(%s))
        order by created_at desc,review_event_id desc limit 129""",
        ("oom_sakkie_family_message_lifecycle", family_missions, family_missions, family_missions))
    family = [{"review_event_id": row[0], "created_at": row[1], "record": row[2]} for row in cur.fetchall()]
    history._validate_family_history(family, source_history, claim, family_missions[-1])
    claim_hash = history._sha(claim["callback_token"])
    audits = _read_rows(cur, """select to_jsonb(e) from public.operational_events e
        where aggregate_type='protected_action_claim' and aggregate_id=%s
        order by occurred_at,event_id limit 129""", (claim_hash,))
    chain = history.validate_audit_chain(claim, case, source, audits, observed_at=observed_at)
    events = _read_rows(cur, """select to_jsonb(e) from app_private.oom_manager_case_events e
        where case_id=%s order by occurred_at,event_id limit 4097""", (case["case_id"],))
    cycle = None
    if chain[0]:
        cycles = _read_rows(cur, "select to_jsonb(c) from app_private.oom_manager_worker_cycles c where cycle_id=%s",
            (chain[0]["causation_id"],))
        cycle = history._one(cycles, "historical_presend_cycle")
    history.validate_case_history(events, claim, case, chain, cycle, observed_at=observed_at)
    return {"source_history_sha256": source_tx.digest(source_history), "family_history_sha256": source_tx.digest(family),
        "claim_history_sha256": source_tx.digest(audits), "case_history_sha256": source_tx.digest(events)}


def claim_presentation(policy, *, callback_token, preview_digest, owner_user_id, private_chat_id,
                       action_kind, factory, start_attempt, deadline_monotonic):
    from modules.oom_sakkie.protected_delivery_lifecycle import _safe, _attempt_identity
    source_tx.require(type(policy) is RetainedMortalityPresentation, "retained_mortality_policy_invalid")
    source, requested, case = json.loads(policy.source_json), json.loads(policy.request_json), json.loads(policy.case_json)
    source_tx.require((callback_token, preview_digest, owner_user_id, private_chat_id, action_kind) ==
        (policy.callback_token, policy.preview_digest, requested["owner_user_id"], requested["private_chat_id"], "mortality"),
        "retained_mortality_policy_binding_mismatch")
    if not start_attempt:
        # No expiry mutation and no effects: family history/rendering precede the
        # only authoritative material read at the provider boundary below.
        return None
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_recipient_authorized, _delivery_context
    from modules.oom_sakkie.herdmaster_health_loss_runtime import load_canonical_health_loss_evidence
    require_admission_reserve(deadline_monotonic)
    deferred = None
    with factory() as db:
        try:
            with db.cursor() as raw_cur:
                cur = AdmissionCursor(raw_cur, deadline_monotonic)
                source_tx.begin(cur)
                source_tx.lock_sources(cur, owner_user_id, private_chat_id, [source["mission_id"]])
                source_history = source_tx.read_history(cur, [source["mission_id"]])
                source = validate_staged_source(source_history, source)
                claims = _read_rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
                    where callback_token=%s for update""", (callback_token,))
                claim = history._one(claims, "retained_mortality_claim")
                source_tx.require(all(claim.get(key) == value for key, value in requested.items())
                    and claim["preview_digest"] == preview_digest, "retained_mortality_claim_changed")
                if claim["delivery_state"] in {"delivery_pending", "provider_accepted", "delivery_ambiguous", "delivery_confirmed"}:
                    return {**_safe("retained_mortality_window_already_started"), "success": False,
                        "do_not_retry_provider_effect": True}
                source_tx.require(claim["status"] in {"active", "expired"}
                    and claim["delivery_state"] in {None, "claim_created", "expired"}
                    and all(key in claim and claim[key] is None for key in history.EMPTY_MARKERS),
                    "retained_mortality_attempt_or_terminal_history")
                cur.execute("select clock_timestamp()")
                observed_at = cur.fetchone()[0]
                source_tx.require(history._time(claim["created_at"]) <= observed_at
                    and all(history._time(item["created_at"]) <= observed_at for item in source_history),
                    "retained_mortality_history_future")
                _validate_source(source, claim)
                validate_origin(source_history, source, claim, observed_at)
                proofs = _histories(cur, claim, source, source_history, case, observed_at)
                operation = claim["preview_payload"]["operation_id"]
                cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("herdmaster-mortality:" + operation,))
                cur.execute("""select 1 from (
                    select 1 from public.pig_lifecycle_events where idempotency_key=%s
                      or event_payload->>'operation_id'=%s or (pig_id=%s and lifecycle_event_type='exited_farm')
                    union all select 1 from public.pig_welfare_case_events e
                      join public.pig_welfare_cases c using(welfare_case_id)
                      where c.pig_id=%s and e.case_state='closed' and e.closure_kind='death'
                    union all select 1 from public.operational_events where payload_json->>'operation_id'=%s
                    ) effect_evidence limit 1""", (operation, operation, claim["preview_payload"]["identity"]["pig_id"],
                        claim["preview_payload"]["identity"]["pig_id"], operation))
                source_tx.require(cur.fetchone() is None, "retained_mortality_operation_already_exists")
                remaining = None if deadline_monotonic is None else deadline_monotonic - time.monotonic() - 30
                if remaining is not None and remaining <= 0:
                    return {**_safe("family_message_cycle_deadline_deferred"), "success": False,
                        "delivery_definitely_not_sent": True}
                try:
                    evidence = load_canonical_health_loss_evidence(connect_factory=source_tx.TransactionReader(db),
                        **({"deadline_seconds": remaining} if remaining is not None else {}))
                except Exception as exc:
                    if _statement_timeout(exc):
                        raise _StatementTimeout("retained_mortality_canonical_statement_timeout") from exc
                    if isinstance(exc, TimeoutError):
                        raise PresentationDeadline("retained_mortality_canonical_read_deadline") from exc
                    raise
                validate_material(source, claim, evidence)
                source_tx.require(retained_recipient_authorized(_delivery_context(source)), "retained_mortality_recipient_changed")
                # Canonical writers have no global shared fence. This is the accepted
                # fresh validation boundary; confirmation revalidates before farm writes.
                if deadline_monotonic is not None and time.monotonic() + 30 >= deadline_monotonic:
                    return {**_safe("family_message_cycle_deadline_deferred"), "success": False,
                        "delivery_definitely_not_sent": True}
                cur.execute("select clock_timestamp()")
                now = cur.fetchone()[0]
                expiry = now + timedelta(seconds=history.TTL_SECONDS)
                attempt = _attempt_identity(callback_token, preview_digest, nonce=uuid.uuid4().hex)
                claim_hash = history._sha(callback_token)
                event_id = "OOM-MORTALITY-WINDOW-" + claim_hash[:32].upper()
                audit = {"contract_version": CONTRACT, "claim_hash": claim_hash, "source_mission_id": source["mission_id"],
                    "source_binding": source["retained_repreview"]["source_binding"], "case_id": case["case_id"],
                    "generation": case["generation"], "evidence_digest": case["evidence_digest"],
                    "preview_digest": preview_digest, "evidence_generation": claim["evidence_generation"],
                    "operation_id": operation, "old_expires_at": claim["expires_at"], "old_status": claim["status"],
                    "old_delivery_state": claim["delivery_state"], "attempt_id": attempt,
                    "started_at": now.isoformat(), "new_expires_at": expiry.isoformat(),
                    "ttl_seconds": history.TTL_SECONDS, "one_time_only": True, **proofs}
                cur.execute("""insert into public.operational_events(event_id,idempotency_key,schema_version,event_type,domain,
                    aggregate_type,aggregate_id,source_system,source_record_id,authority_tier,privacy_class,actor_type,actor_id,
                    correlation_id,causation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json)
                    values(%s,%s,'1',%s,'approvals','protected_action_claim',%s,'oom_sakkie',%s,'bounded_auto',
                        'owner_private','system','retained_mortality_presentation',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                    returning event_id""", (event_id, KEY_PREFIX + claim_hash, history.WINDOW, claim_hash, case["case_id"],
                        claim["mission_id"], source["mission_id"], now, now, now, _json(audit),
                        _json({"source_ref": source["retained_repreview"]["source_binding"]})))
                source_tx.require(cur.rowcount == 1 and cur.fetchone() == (event_id,), "retained_mortality_window_audit_failed")
                cur.execute("""update app_private.oom_protected_action_claims c set status='active',expires_at=%s,
                    delivery_state='delivery_pending',delivery_attempt_id=%s,delivery_attempted_at=%s
                    where callback_token=%s and to_jsonb(c)=%s::jsonb returning expires_at,delivery_attempted_at""",
                    (expiry, attempt, now, callback_token, _json(claim)))
                source_tx.require(cur.rowcount == 1 and cur.fetchone() == (expiry, now), "retained_mortality_window_claim_failed")
                # Charge the clock/audit/CAS work too. Raising is essential here: a
                # normal return would commit the window despite losing admission time.
                require_admission_reserve(deadline_monotonic)

        except (_StatementTimeout, PresentationDeadline) as exc:
            # This is inside the connection context, before it can commit. If
            # rollback or later context exit fails, the typed deferral is never
            # emitted and the wrapper keeps the result closed to retry.
            db.rollback()
            deferred = exc
    if isinstance(deferred, _StatementTimeout):
        raise PresendStatementDeferred("retained_mortality_presend_statement_deferred") from deferred
    if deferred is not None:
        raise deferred
    return {"attempt_owned": True, "attempt_id": attempt}


def validate_staged_source(rows, staged):
    current = source_tx.require_current(rows, staged)
    source_tx.require(current == source_tx.record_body(staged), "retained_mortality_staged_source_changed")
    return current


def validate_origin(rows, source, claim, observed_at):
    own = [item for item in rows if item["record"].get("mission_id") == source["mission_id"]]
    created = history._time(claim["created_at"])
    source_tx.require(own and len({item["review_event_id"] for item in rows}) == len(rows)
        and history._time(own[-1]["created_at"]) <= created <= history._time(own[0]["created_at"]) <= observed_at
        and created < history._time(claim["expires_at"]), "retained_mortality_origin_chronology_unproven")
    source_tx.require(all(item["record"].get("status") in
        {"waiting_for_input", "preview_ready", "waiting_for_confirmation"}
        and not any(item["record"].get(key) for key in
            ("invalidated_operation_ids", "correction_digest", "consumed_context_missions",
                "superseded_duplicate_missions", "superseded_duplicate_bindings"))
        for item in own), "retained_mortality_terminal_or_corrected_source_history")


class PresentationDeadline(TimeoutError):
    """Admission ran out of reserve before ownership escaped its transaction."""


def require_admission_reserve(deadline):
    if deadline is not None and time.monotonic() + 30 >= deadline:
        raise PresentationDeadline("retained_mortality_admission_deadline")


class AdmissionCursor:
    """Bound each metadata query; the canonical snapshot has its own total budget."""
    def __init__(self, cursor, deadline):
        self.cursor, self.deadline = cursor, deadline
    def execute(self, *args, **kwargs):
        require_admission_reserve(self.deadline)
        try:
            return self.cursor.execute(*args, **kwargs)
        except Exception as exc:
            if _statement_timeout(exc):
                raise _StatementTimeout("retained_mortality_bounded_statement_timeout") from exc
            raise
    def __getattr__(self, key):
        return getattr(self.cursor, key)


class _StatementTimeout(Exception):
    pass


class PresendStatementDeferred(Exception):
    """A known body SQL timeout was explicitly rolled back and context exited."""


def _statement_timeout(exc):
    return (type(exc).__module__.split(".", 1)[0] == "psycopg"
        and type(exc).__name__ in {"LockNotAvailable", "QueryCanceled"}
        and getattr(exc, "sqlstate", None) in {"55P03", "57014"})
