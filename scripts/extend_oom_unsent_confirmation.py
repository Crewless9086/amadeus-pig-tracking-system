"""Manual exact-plan expiry extension; no CLI, credentials or runtime hook.

Only trusted external hooks may authenticate the exact owner-approved plan and
verify loaded prevention. Preparation never grants authority. The injected
transaction writes one audit and expires_at only; ordinary renewal stays used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re

from scripts import correct_oom_presend_timeout as correction

CONTRACT = "oom_unsent_confirmation_extension.v1"
EVENT_TYPE = "protected_unsent_confirmation_expiry_extended"
KEY_PREFIX = "oom-unsent-confirmation-extension:"
TTL_SECONDS = 1800
BOUND = 128
CASE_CLOCKS = {"updated_at", "last_heartbeat_at", "next_reassessment_at"}
PREIMAGE_KEYS = ("case", "claim", "related_claims", "family", "case_events",
                 "claim_audits", "source_history", "animal", "operations", "card_mission_id", "material_evidence")
_require = correction._require
_json = correction._json
_digest = correction._digest
_time = correction._time
_sha = correction._sha
_one = correction._one
_rows = correction._rows


def _material_snapshot(evidence):
    return {k: v for k, v in evidence.items() if k != "as_of_timestamp"}


def _preview(source, evidence):
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
    return prepare_health_loss_owner_preview({
        "gateway_authority": issue_gateway_owner_authority(source["owner_user_id"], source["chat_id"]),
        "provider_message_id": str(source.get("provider_message_id") or ""),
        "provider_timestamp": str(source.get("provider_timestamp") or ""),
        "provider_timezone": "Africa/Johannesburg", "output_language": source.get("output_language") or "af",
        "text": str(source.get("combined_text") or source.get("owner_text_verbatim") or ""),
        **({"report_parts": source["report_parts"]} if source.get("report_parts") else {}),
        **{k: v for k, v in (source.get("semantic_interpretation") or {}).items()
           if k in {"mortality_observation", "welfare_observation", "clinical_observation"}},
    }, evidence)


def _validate_material(evidence, source, claim):
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import _unchanged_retained_preview
    material = {k: evidence[k] for k in ("animals", "matings", "litters")}
    _require(evidence["evidence_generation"] == _digest(material) == claim["evidence_generation"],
             "canonical_evidence_generation_changed")
    current = _unchanged_retained_preview(source, _preview(source, evidence),
        evidence_generation=evidence["evidence_generation"])
    _require(current.get("success") is True and current.get("confirmation_ready") is True
        and current.get("question_count") == 0 and current == source["preview"], "canonical_preview_changed")
    binding = current["confirmation_binding"]
    _require(current["evaluator"]["identity"] == claim["preview_payload"]["identity"]
        and binding["operation_id"] == claim["preview_payload"]["operation_id"]
        and binding["preview_sha256"] == claim["preview_payload"]["preview_sha256"], "canonical_preview_binding_changed")


def _original(plan):
    rebuilt = correction.prepare_plan(plan["preimage"],
        prevention_revision=plan["prevention_revision"], prevention_tree=plan["prevention_tree"],
        authorization_expires_at=plan["authorization_expires_at"])
    _require(plan == rebuilt, "original_correction_plan_mismatch")
    return correction._validate(plan["preimage"])


def _correction_audit(evidence, original):
    old, case, _source = _original(original)
    audits = evidence["claim_audits"]
    _require(len(audits) == 2, "claim_audit_history_unproven")
    renewed = [a for a in audits if a["event_type"] == "retained_protected_preview_expiry_renewed"]
    _require(renewed == original["preimage"]["claim_audits"], "original_renewal_changed")
    corrected = _one([a for a in audits if a["event_type"] == correction.EVENT_TYPE], "original_correction")
    payload = corrected["payload_json"]
    claim_hash = _sha(old["callback_token"])
    _require(corrected["event_id"] == "OOM-PRESEND-CORRECTION-" + claim_hash[:32].upper()
        and corrected["idempotency_key"] == "oom-presend-timeout-correction:" + claim_hash,
        "original_correction_identity_mismatch")
    expected = {"contract_version": correction.CONTRACT, "plan_sha256": correction.plan_digest(original),
        "preimage_sha256": original["preimage_sha256"], "claim_hash": claim_hash,
        "case_id": case["case_id"], "generation": case["generation"],
        "evidence_digest": case["evidence_digest"], "preview_digest": old["preview_digest"],
        "archived_claim_markers": {k: old[k] for k in correction.ARCHIVED_MARKERS},
        "original_renewal": renewed[0], "one_time_only": True,
        "prevention_revision": original["prevention_revision"], "prevention_tree": original["prevention_tree"],
        "provider_attempts": 0, "farm_writes": 0, "scheduler_triggers": 0}
    _require(all(payload.get(k) == v and type(payload.get(k)) is type(v) for k, v in expected.items()),
             "original_correction_binding_mismatch")
    _require(type(payload.get("authority_reference")) is str and payload["authority_reference"].strip()
        and re.fullmatch(r"[0-9a-f]{40}", str(payload.get("deployed_revision") or "")) is not None,
        "original_correction_authority_unproven")
    _require(_time(payload["new_expires_at"]) == _time(corrected["occurred_at"]) + timedelta(seconds=TTL_SECONDS),
             "original_correction_expiry_mismatch")
    return corrected


def _case_material(case):
    return {k: v for k, v in case.items() if k not in CASE_CLOCKS}


def _validate(evidence, original):
    old, old_case, _source = _original(original)
    c = _one(evidence["claim"], "claim")["record"]
    m = _one(evidence["case"], "case")["record"]
    audit = _correction_audit(evidence, original)
    expected_claim = {**old, "status": "active", "delivery_state": "claim_created",
        "expires_at": audit["payload_json"]["new_expires_at"],
        **{k: None for k in correction.ARCHIVED_MARKERS[:4]}}
    _require(correction._same_projection(c, expected_claim, {"expires_at"}), "claim_not_exact_unsent_correction")
    _require(_one(evidence["related_claims"], "related_claim")["record"] == c,
             "related_claim_conflict")
    _require(m["status"] in {"waiting_reassessment", "exception"}
        and all(m[k] is None for k in ("assigned_worker_id", "lease_until", "last_delivery_digest", "last_delivery_at")),
        "case_not_unleased_due_candidate")
    material = {k: v for k, v in _case_material(m).items() if k != "status"}
    original_material = {k: v for k, v in _case_material(old_case).items() if k != "status"}
    _require(material == original_material, "original_case_material_changed")
    _require(evidence["card_mission_id"] == original["preimage"]["card_mission_id"], "card_identity_changed")
    family = _one(evidence["family"], "family")
    _require(all(type(family[k]) is int and family[k] == 0 for k in ("row_count", "effect_rows")),
             "family_history_exists")
    _require(evidence["operations"] == [], "canonical_operation_exists")
    _require(evidence["animal"] == original["preimage"]["animal"], "canonical_material_changed")
    _require(0 < len(evidence["source_history"]) <= BOUND
        and evidence["source_history"] == original["preimage"]["source_history"], "source_history_changed")
    _validate_material(evidence["material_evidence"], evidence["source_history"][0]["record"], c)
    events = evidence["case_events"]
    _require(0 < len(events) <= BOUND, "case_history_bound")
    correction_event = audit["event_id"] + "-REASSESS"
    _require(sum(e["record"]["event_id"] == correction_event for e in events) == 1,
             "original_case_correction_missing")
    for item in events:
        event = item["record"]
        p = event["event_payload"]
        _require(event["case_id"] == m["case_id"] and event["generation"] == m["generation"]
            and _time(event["occurred_at"]) >= _time(audit["occurred_at"]), "case_history_identity_changed")
        if event["event_id"] == correction_event:
            _require(event["event_type"] == "reassessment_scheduled"
                and p.get("correction_audit_event_id") == audit["event_id"]
                and p.get("plan_sha256") == correction.plan_digest(original)
                and p.get("outcome_status") == "proven_presend_timeout_classification_corrected",
                "original_case_correction_mismatch")
            continue
        _require(event["event_type"] in {"claimed", "delegated", "heartbeat", "exception", "reassessment_scheduled"}
            and not p.get("provider_ambiguity_contained") and not p.get("failure_kind")
            and p.get("outcome_status", "") in {"", "manager_cycle_deadline_deferred", "family_message_cycle_deadline_deferred"}
            and (event["event_type"] != "exception" or p.get("outcome_status") in {
                "manager_cycle_deadline_deferred", "family_message_cycle_deadline_deferred"})
            and not any(p.get(k) for k in ("delivery_confirmed", "provider_confirmed", "confirmed_generation_preserved",
                "provider_card_message_id", "delivery_attempt_id", "telegram_sends", "telegram_edits", "writes_farm_data")),
            "unsafe_case_history")
    return c, m, audit


def prepare_plan(preimage, *, original_correction_plan, prevention_revision, prevention_tree,
                 authorization_expires_at):
    """Pure proposal with fixed TTL and exact prior expiry; never grants authority."""
    original = json.loads(_json(original_correction_plan))
    evidence = json.loads(_json({k: preimage[k] for k in PREIMAGE_KEYS}))
    c, _case, audit = _validate(evidence, original)
    _require(all(re.fullmatch(r"[0-9a-f]{40}", value) is not None
                 for value in (prevention_revision, prevention_tree)), "prevention_revision_invalid")
    return {"contract_version": CONTRACT, "preimage": evidence, "preimage_sha256": _digest(evidence),
        "original_correction_plan": original, "original_correction_event_id": audit["event_id"],
        "prevention_revision": prevention_revision, "prevention_tree": prevention_tree,
        "authorization_expires_at": _time(authorization_expires_at).isoformat(), "ttl_seconds": TTL_SECONDS,
        "expected_expires_at": _time(c["expires_at"]).isoformat(), "claim_hash": _sha(c["callback_token"])}


def plan_digest(plan):
    return _digest(plan)


def _validate_authority(plan, authority, claim, now):
    _require(_time(plan["expected_expires_at"]) < now < _time(plan["authorization_expires_at"]),
             "expiry_or_authority_window_invalid")
    _require(isinstance(authority, dict) and type(authority.get("authority_reference")) is str
        and authority["authority_reference"].strip() and authority.get("plan_sha256") == plan_digest(plan)
        and authority.get("owner_user_id") == claim["owner_user_id"]
        and authority.get("private_chat_id") == claim["private_chat_id"]
        and authority.get("authorization_expires_at") == plan["authorization_expires_at"], "authority_attestation_unbound")


def inspect_proposal(plan, *, fresh_preimage, now, authority, loaded_prevention):
    """Pure inspection only, using externally supplied readback and attestations.

    This function does not authenticate, acquire locks or transact. Only the
    manual executor supplies trusted hook results and locked canonical readback.
    """
    plan = deepcopy(plan)
    rebuilt = prepare_plan(plan["preimage"], original_correction_plan=plan["original_correction_plan"],
        prevention_revision=plan["prevention_revision"], prevention_tree=plan["prevention_tree"],
        authorization_expires_at=plan["authorization_expires_at"])
    _require(plan == rebuilt, "plan_binding_mismatch")
    now = _time(now)
    _require(_time(plan["expected_expires_at"]) < now < _time(plan["authorization_expires_at"]),
             "expiry_or_authority_window_invalid")
    c, _case, _audit = _validate(plan["preimage"], plan["original_correction_plan"])
    digest = plan_digest(plan)
    _validate_authority(plan, authority, c, now)
    _require(isinstance(loaded_prevention, dict) and loaded_prevention.get("loaded_tree") == plan["prevention_tree"]
        and re.fullmatch(r"[0-9a-f]{40}", str(loaded_prevention.get("loaded_revision") or "")) is not None,
        "loaded_prevention_attestation_unbound")
    _validate(fresh_preimage, plan["original_correction_plan"])
    expected = plan["preimage"]
    for key in PREIMAGE_KEYS:
        if key == "material_evidence":
            _require(_material_snapshot(fresh_preimage[key]) == _material_snapshot(expected[key]),
                     "fresh_material_evidence_mismatch")
        elif key not in {"case", "case_events"}:
            _require(fresh_preimage[key] == expected[key], "fresh_" + key + "_mismatch")
    case = fresh_preimage["case"][0]["record"]
    prior = expected["case"][0]["record"]
    _require(_case_material(case) == _case_material(prior), "fresh_case_material_mismatch")
    for key in CASE_CLOCKS:
        if case[key] is not None:
            _require((prior[key] is None or _time(case[key]) >= _time(prior[key])) and _time(case[key]) <= now,
                     "case_clock_invalid")
        else:
            _require(prior[key] is None, "case_clock_regressed")
    _require(_time(case["next_reassessment_at"]) <= now, "case_not_due")
    observed = {_digest(e) for e in fresh_preimage["case_events"]}
    _require(all(_digest(e) in observed for e in expected["case_events"]), "case_history_missing")
    return {"status": "proposal_consistent_not_authorized", "metadata_writes": 0,
        "plan_sha256": digest, "proposed_expires_at": (now + timedelta(seconds=TTL_SECONDS)).isoformat()}


class _BorrowedConnection:
    """Canonical readers may borrow the transaction but cannot close/commit it."""
    def __init__(self, db): self.db = db
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.db.cursor()


class _TransactionReader:
    transaction_managed = True
    def __init__(self, db): self.db = db
    def __call__(self, _unused_database_url=None): return _BorrowedConnection(self.db)


def _fresh(cur, original, *, locked=False):
    c, m, source = _original(original)
    providers = original["provider_ids"]
    lock = " for update" if locked else ""
    result = {"card_mission_id": original["preimage"]["card_mission_id"]}
    result["case"] = _rows(cur, "select to_jsonb(m) from app_private.oom_manager_cases m where case_id=%s" + lock,
        (m["case_id"],), ("record",))
    result["claim"] = _rows(cur, "select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s" + lock,
        (c["callback_token"],), ("record",))
    if locked:
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("herdmaster-mortality:" + c["preview_payload"]["operation_id"],))
        cur.execute("select pig_id from public.pigs where pig_id=%s for share",
                    (c["preview_payload"]["identity"]["pig_id"],))
        _require(len(cur.fetchall()) == 1, "canonical_pig_missing")
    result["related_claims"] = _rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
        where mission_id=any(%s) or provider_message_id=any(%s)
          or preview_payload->'provider_message_ids' ?| %s order by callback_token limit 129""",
        ([c["mission_id"], source["mission_id"]], providers, providers), ("record",))
    result["family"] = _rows(cur, """select count(*),count(*) filter (where
        review_json->'family_message_lifecycle'->>'state' in ('delivery_attempted','delivered',
        'update_attempted','updated','contained','notification_attempted','notification_delivered'))
        from public.sam_live_stock_conversation_review_events where event_source=%s and
        (chatwoot_conversation_id=%s or review_json->'family_message_lifecycle'->>'card_mission_id'=%s
         or review_json->'family_message_lifecycle'->>'mission_id'=any(%s))""",
        (correction.FAMILY_SOURCE, result["card_mission_id"], result["card_mission_id"], [c["mission_id"], source["mission_id"]]),
        ("row_count", "effect_rows"))
    result["claim_audits"] = _rows(cur, """select event_id,event_type,idempotency_key,payload_json,occurred_at
        from public.operational_events where aggregate_type='protected_action_claim' and aggregate_id=%s
        order by occurred_at desc,event_id desc limit 129""", (original["claim_hash"],),
        ("event_id", "event_type", "idempotency_key", "payload_json", "occurred_at"))
    audit = _correction_audit(result, original)
    result["case_events"] = _rows(cur, """select to_jsonb(e) from app_private.oom_manager_case_events e
        where case_id=%s and occurred_at >= %s order by occurred_at desc,event_id desc limit 129""",
        (m["case_id"], audit["occurred_at"]), ("record",))
    result["source_history"] = _rows(cur, """select review_event_id,created_at,
        review_json->'herdmaster_health_loss' from public.sam_live_stock_conversation_review_events
        where event_source=%s and (review_json->'herdmaster_health_loss'->>'mission_id'=%s
        or review_json->'herdmaster_health_loss'->>'provider_message_id'=any(%s)
        or review_json->'herdmaster_health_loss'->'consumed_context_missions' ? %s
        or review_json->'herdmaster_health_loss'->'superseded_duplicate_missions' ? %s
        or exists (select 1 from jsonb_array_elements(coalesce(review_json->'herdmaster_health_loss'
        ->'superseded_duplicate_bindings','[]'::jsonb)) b where b->>'mission_id'=%s))
        order by created_at desc,review_event_id desc limit 129""",
        (correction.REPORT_SOURCE, source["mission_id"], providers, source["mission_id"], source["mission_id"], source["mission_id"]),
        ("review_event_id", "created_at", "record"))
    animal = original["preimage"]["animal"][0]["record"]
    result["animal"] = _rows(cur, """select to_jsonb(p) from public.current_canonical_pigs p
        where pig_id=%s or (%s <> '' and lower(to_jsonb(p)->>'tag_number')=lower(%s)) order by pig_id limit 129""",
        (animal["pig_id"], str(animal.get("tag_number") or ""), str(animal.get("tag_number") or "")), ("record",))
    operation = c["preview_payload"]["operation_id"]
    # Mortality commits lifecycle, pig and welfare effects atomically. Inspect
    # welfare/operational evidence too so inconsistent historical data cannot
    # pass merely because its lifecycle row is missing.
    result["operations"] = _rows(cur, """select record from (
        select to_jsonb(e) as record from public.pig_lifecycle_events e
        where idempotency_key=%s or event_payload->>'operation_id'=%s
          or (pig_id=%s and lifecycle_event_type='exited_farm')
        union all select to_jsonb(e) from public.pig_welfare_case_events e
        join public.pig_welfare_cases c using(welfare_case_id)
        where c.pig_id=%s and e.case_state='closed' and e.closure_kind='death'
        union all select to_jsonb(e) from public.operational_events e
        where e.payload_json->>'operation_id'=%s
        ) effect_evidence limit 129""",
        (operation, operation, animal["pig_id"], animal["pig_id"], operation), ("record",))
    return result


def _read_material(db):
    from modules.oom_sakkie.herdmaster_health_loss_runtime import load_canonical_health_loss_evidence
    # The canonical reader receives only this already bounded transaction. Its
    # optional URL argument is ignored and can never create another connection.
    return load_canonical_health_loss_evidence(connect_factory=_TransactionReader(db))


def read_preimage_from_cursor(cursor, original_correction_plan, *, material_evidence):
    """SELECT-only preparation using a caller's coherent read-only snapshot.

    material_evidence must come from the existing canonical health-loss reader
    in that same snapshot. It is evaluated, not accepted as a boolean proof.
    This function takes no locks and does not commit or change transaction mode.
    """
    result = _fresh(cursor, original_correction_plan)
    result["material_evidence"] = deepcopy(material_evidence)
    _validate(result, original_correction_plan)
    return result


def read_preimage(original_correction_plan, *, connect_factory):
    """Read-only preparation; injected connection only, no implicit authority."""
    _original(original_correction_plan)
    with connect_factory() as db:
        _require(db.autocommit is False, "transaction_connection_required")
        with db.cursor() as cur:
            cur.execute("set transaction isolation level repeatable read read only")
            cur.execute("set local statement_timeout='5000ms'")
            cur.execute("set local lock_timeout='5000ms'")
            cur.execute("set local timezone='UTC'")
            return read_preimage_from_cursor(cur, original_correction_plan, material_evidence=_read_material(db))


def apply_extension(plan, *, authorize, verify_prevention, connect_factory):
    """Two atomic metadata writes, or exact replay after progress with zero writes.

    authorize(digest) must authenticate current owner approval for the exact
    manifest and return bound actor/chat/digest/deadline plus an audit reference.
    verify_prevention(candidate, tree) must independently prove the reviewed tree
    is loaded. No file flags or caller booleans may replace either trusted hook.
    The injected connection must be bounded, fresh and non-autocommit.

    Claim/case/operation locks serialize their cooperating writers. Source and
    family appenders do not share these locks: the final fresh read contains all
    then-committed changes, not a guarantee against later independent appends.
    Normal runtime source/evidence/recipient/confirmation gates remain required.
    """
    plan = deepcopy(plan)
    rebuilt = prepare_plan(plan["preimage"], original_correction_plan=plan["original_correction_plan"],
        prevention_revision=plan["prevention_revision"], prevention_tree=plan["prevention_tree"],
        authorization_expires_at=plan["authorization_expires_at"])
    _require(plan == rebuilt, "plan_binding_mismatch")
    _require(datetime.now(timezone.utc) < _time(plan["authorization_expires_at"]), "authorization_expired")
    _require(all(callable(hook) for hook in (authorize, verify_prevention, connect_factory)), "trusted_caller_hooks_required")
    c, m, original_audit = _validate(plan["preimage"], plan["original_correction_plan"])
    digest = plan_digest(plan)
    authority = authorize(digest)
    _validate_authority(plan, authority, c, datetime.now(timezone.utc))
    deployed = verify_prevention(plan["prevention_revision"], plan["prevention_tree"])
    # Check hook binding before crossing the connection boundary.
    inspect_proposal(plan, fresh_preimage=plan["preimage"], now=datetime.now(timezone.utc),
        authority=authority, loaded_prevention=deployed)
    event_id = "OOM-UNSENT-EXTENSION-" + plan["claim_hash"][:32].upper()
    key = KEY_PREFIX + plan["claim_hash"]
    with connect_factory() as db:
        _require(db.autocommit is False, "transaction_connection_required")
        with db.cursor() as cur:
            # A role/connection default of REPEATABLE READ must not hide source
            # appends committed during canonical evaluation from the final read.
            cur.execute("set transaction isolation level read committed")
            cur.execute("set local statement_timeout='5000ms'")
            cur.execute("set local lock_timeout='5000ms'")
            cur.execute("set local timezone='UTC'")
            cur.execute("select pg_advisory_xact_lock(%s)", (int(_sha("protected-claim|" + c["mission_id"])[:15], 16),))
            prior = _rows(cur, "select event_id,payload_json from public.operational_events where idempotency_key=%s",
                (key,), ("event_id", "payload_json"))
            if prior:
                _require(len(prior) == 1 and prior[0]["event_id"] == event_id
                    and prior[0]["payload_json"].get("plan_sha256") == digest, "extension_replay_conflict")
                return {"status": "already_applied", "metadata_writes": 0, "audit_event_id": event_id}
            fresh = _fresh(cur, plan["original_correction_plan"], locked=True)
            fresh["material_evidence"] = _read_material(db)
            _validate(fresh, plan["original_correction_plan"])
            # Re-read append-only safety evidence after potentially slower
            # canonical material evaluation, while retaining the row locks.
            final = _fresh(cur, plan["original_correction_plan"])
            final["material_evidence"] = fresh["material_evidence"]
            cur.execute("select clock_timestamp()")
            now = cur.fetchone()[0]
            inspected = inspect_proposal(plan, fresh_preimage=final, now=now,
                authority=authority, loaded_prevention=deployed)
            expiry = _time(inspected["proposed_expires_at"])
            audit = {"contract_version": CONTRACT, "plan_sha256": digest,
                "preimage_sha256": plan["preimage_sha256"], "claim_hash": plan["claim_hash"],
                "case_id": m["case_id"], "generation": m["generation"], "evidence_digest": m["evidence_digest"],
                "original_correction_event_id": original_audit["event_id"],
                "original_correction_plan_sha256": correction.plan_digest(plan["original_correction_plan"]),
                "original_renewal_consumed": True, "preview_digest": c["preview_digest"],
                "old_expires_at": plan["expected_expires_at"], "new_expires_at": expiry.isoformat(),
                "ttl_seconds": TTL_SECONDS, "one_time_only": True,
                "authority_reference": authority["authority_reference"], "owner_user_id": c["owner_user_id"],
                "prevention_revision": plan["prevention_revision"], "prevention_tree": plan["prevention_tree"],
                "deployed_revision": deployed["loaded_revision"],
                "metadata_writes": 2, "provider_attempts": 0, "farm_writes": 0, "scheduler_triggers": 0}
            cur.execute("""insert into public.operational_events(event_id,idempotency_key,schema_version,
                event_type,domain,aggregate_type,aggregate_id,source_system,source_record_id,authority_tier,
                privacy_class,actor_type,actor_id,correlation_id,causation_id,occurred_at,recorded_at,
                freshness_at,payload_json,provenance_json) values(%s,%s,'1',%s,'incidents',
                'protected_action_claim',%s,'manual_unsent_confirmation_extension',%s,'owner_approved',
                'owner_private','owner',%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) returning payload_json""",
                (event_id, key, EVENT_TYPE, plan["claim_hash"], m["case_id"], c["owner_user_id"], m["case_id"],
                 original_audit["event_id"], now, now, now, _json(audit), _json({"source_ref": "sha256:" + plan["preimage_sha256"]})))
            inserted = cur.fetchone()
            _require(cur.rowcount == 1 and inserted and inserted[0] == audit, "audit_insert_failed")
            cur.execute("""update app_private.oom_protected_action_claims c set expires_at=%s
                where callback_token=%s and to_jsonb(c)=%s::jsonb returning to_jsonb(c)""",
                (expiry, c["callback_token"], _json(final["claim"][0]["record"])))
            updated = cur.fetchone()
            expected = {**final["claim"][0]["record"], "expires_at": expiry.isoformat()}
            _require(cur.rowcount == 1 and updated and correction._same_projection(updated[0], expected, {"expires_at"}),
                     "claim_readback_failed")
    return {"status": "applied", "metadata_writes": 2, "audit_event_id": event_id,
            "new_expires_at": expiry.isoformat(), "provider_attempts": 0, "farm_writes": 0}
