"""Manual, exact-preimage metadata correction; no CLI, credentials or runtime hook.

The reviewed incident wrapper must authenticate current owner write/transport
authority and verify the deployed prevention revision. File contents, source
pins and booleans are never authority. This module only checks and transacts the
already authenticated plan through an injected bounded connection. It neither
sends nor triggers work. Ordinary manager evidence/recipient/confirmation gates
remain authoritative after the case becomes due.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from modules.oom_sakkie.protected_action_claims import (
    canonical_preview_digest, protected_card_mission_id,
)
from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding

CONTRACT = "oom_presend_timeout_correction.v1"
REPORT_SOURCE = "oom_sakkie_herdmaster_health_loss_runtime"
FAMILY_SOURCE = "oom_sakkie_family_message_lifecycle"
EVENT_TYPE = "protected_presend_timeout_classification_corrected"
TTL_SECONDS = 1800
BOUND = 128
PREIMAGE_KEYS = ("case", "claim", "related_claims", "family", "case_events",
                 "claim_audits", "source_history", "animal", "cycle", "card_mission_id")
EMPTY_MARKERS = ("preview_card_message_id", "provider_accepted_at", "delivery_confirmed_at",
                 "confirmation_provider_message_id", "confirmation_provider_timestamp",
                 "completed_at", "result_payload")
ARCHIVED_MARKERS = ("delivery_attempt_id", "delivery_attempted_at", "delivery_ambiguous_at",
                    "delivery_result", "expires_at", "status", "delivery_state")


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _time(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    _require(result.tzinfo is not None, "timezone_required")
    return result.astimezone(timezone.utc)


def _sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def _same_projection(actual, expected, timestamp_fields):
    """Postgres JSON may trim fractional zeros; other fields stay byte-semantic."""
    return (set(actual) == set(expected)
            and all((_time(actual[k]) == _time(expected[k]) if k in timestamp_fields
                     else actual[k] == expected[k]) for k in expected))


def _one(rows, name):
    _require(isinstance(rows, list) and len(rows) == 1, name + "_not_unique")
    return rows[0]


def _validate(preimage):
    """Pure proof checks; identifiers come only from the authenticated preimage."""
    c = _one(preimage["claim"], "claim")["record"]
    m = _one(preimage["case"], "case")["record"]
    animal = _one(preimage["animal"], "animal")["record"]
    cycle = _one(preimage["cycle"], "cycle")
    _require(_one(preimage["related_claims"], "related_claim")["record"] == c,
             "related_claim_mismatch")
    counts = _one(preimage["family"], "family")
    _require(all(type(counts[k]) is int and counts[k] == 0 for k in ("row_count", "effect_rows")),
             "family_history_exists")
    _require(c["action_kind"] == "mortality" and c["status"] in {"active", "expired"}
             and c["delivery_state"] == "delivery_ambiguous", "claim_state_invalid")
    _require(all(key in c and c[key] is None for key in EMPTY_MARKERS), "effect_marker_exists")
    expected = {"success": False, "status": "family_message_cycle_deadline_deferred",
                "telegram_message_id": None, "telegram_sends": 0, "telegram_edits": 0}
    result = c["delivery_result"]
    _require(result == expected and result["success"] is False
             and type(result["telegram_sends"]) is int and type(result["telegram_edits"]) is int,
             "initial_presend_result_unproven")
    _require(c["delivery_attempt_id"] == _sha(
        "oom_protected_delivery.v1|" + c["callback_token"] + "|" + c["preview_digest"]),
        "legacy_attempt_identity_mismatch")
    _require(_time(c["delivery_attempted_at"]) <= _time(c["delivery_ambiguous_at"])
             <= _time(c["expires_at"]), "attempt_chronology_invalid")
    _require(c["owner_user_id"] and c["owner_user_id"] == c["private_chat_id"],
             "private_principal_unproven")
    _require(c["preview_digest"] == canonical_preview_digest("mortality", c["preview_payload"]),
             "preview_digest_mismatch")
    _require(preimage["card_mission_id"] == protected_card_mission_id(c["mission_id"], c["preview_digest"]),
             "card_identity_mismatch")
    _require(m["status"] == "contained" and m["specialist"] == "HERDMASTER"
             and type(m["generation"]) is int and m["generation"] > 0
             and all(m[k] is None for k in ("assigned_worker_id", "lease_until",
                                           "last_delivery_digest", "last_delivery_at")),
             "case_not_unleased_contained")
    provider = c["provider_message_id"]
    _require(m["dedupe_key"] == "herdmaster:retained-mortality:" + provider,
             "case_provider_mismatch")
    payload = c["preview_payload"]
    _require(payload["effect_kind"] == "mortality" and payload["operation_id"]
             and payload["identity"]["pig_id"] == animal["pig_id"]
             and animal["status"] == "Active" and animal["on_farm"] is True,
             "animal_identity_unproven")
    _require("pig:" + animal["pig_id"] in m["evidence_refs"]
             and {r for r in m["evidence_refs"] if r.startswith("provider_message:")}
             == {"provider_message:" + provider}, "case_incident_mismatch")
    history = preimage["source_history"]
    _require(0 < len(history) <= BOUND, "source_history_bound")
    rows = [r["record"] for r in history]
    latest = rows[0]
    _require(all(r["mission_id"] == latest["mission_id"]
                 and r["owner_user_id"] == c["owner_user_id"]
                 and r["chat_id"] == c["private_chat_id"]
                 and not any(r.get(k) for k in ("correction_digest", "invalidated_operation_ids",
                     "consumed_context_missions", "superseded_duplicate_bindings",
                     "superseded_duplicate_missions")) for r in rows), "source_lineage_conflict")
    bridge = latest["retained_repreview"]
    binding = latest["preview"]["confirmation_binding"]
    _require(latest["status"] == "preview_ready"
             and latest["event_phase"].startswith("retained_preview_generated:")
             and latest["provider_message_id"] == provider
             and latest["operation_id"] == payload["operation_id"] == binding["operation_id"]
             and payload["preview_sha256"] == binding["preview_sha256"], "retained_preview_mismatch")
    source_binding = retained_report_binding([latest])
    _require(bridge["contract_version"] == "retained_health_preview_v1"
             and bridge["claim_mission_id"] == c["mission_id"]
             and bridge["claim_preview_digest"] == c["preview_digest"]
             and bridge["claim_evidence_generation"] == c["evidence_generation"]
             and bridge["source_binding"] == source_binding
             and {r for r in m["evidence_refs"] if r.startswith("retained_report_binding:")}
             == {source_binding}, "retained_bridge_mismatch")
    audit = _one(preimage["claim_audits"], "renewal")
    renewal = audit["payload_json"]
    _require(audit["event_type"] == "retained_protected_preview_expiry_renewed"
             and renewal["claim_hash"] == _sha(c["callback_token"])
             and renewal["mission_id"] == c["mission_id"]
             and renewal["preview_digest"] == c["preview_digest"]
             and renewal["evidence_generation"] == c["evidence_generation"]
             and renewal["source_binding"] == source_binding
             and _time(renewal["new_expires_at"]) == _time(c["expires_at"])
             and renewal["one_time_only"] is True and renewal["provider_attempts"] == 0
             and renewal["farm_writes"] == 0, "renewal_binding_mismatch")
    _require(re.fullmatch(r"[0-9a-f]{40}", cycle["source_revision"]) is not None
             and _time(cycle["started_at"]) <= _time(c["delivery_attempted_at"]),
             "historical_cycle_unproven")
    events = preimage["case_events"]
    _require(0 < len(events) <= 6 and any(
        e["record"]["case_id"] == m["case_id"]
        and e["record"]["generation"] == m["generation"]
        and e["record"]["event_type"] == "contained"
        and e["record"]["event_payload"].get("cycle_id") == cycle["cycle_id"]
        and e["record"]["event_payload"].get("outcome_status") == "protected_delivery_ambiguous"
        and e["record"]["event_payload"].get("provider_ambiguity_contained") is True
        for e in events), "contained_cycle_unproven")
    return c, m, latest


def prepare_plan(preimage, *, prevention_revision, prevention_tree, authorization_expires_at):
    """Pure preparation, never an authority grant. Input has diagnostic shape."""
    evidence = json.loads(_json({k: preimage[k] for k in PREIMAGE_KEYS}))
    c, _m, source = _validate(evidence)
    _require(all(re.fullmatch(r"[0-9a-f]{40}", value) is not None
                 for value in (prevention_revision, prevention_tree)),
             "prevention_revision_invalid")
    providers = sorted({str(r["record"]["provider_message_id"]) for r in evidence["source_history"]})
    _require(all(p.isascii() and p.isdecimal() for p in providers), "provider_identity_invalid")
    return {"contract_version": CONTRACT, "preimage": evidence,
            "preimage_sha256": _digest(evidence), "prevention_revision": prevention_revision,
            "prevention_tree": prevention_tree,
            "authorization_expires_at": _time(authorization_expires_at).isoformat(),
            "ttl_seconds": TTL_SECONDS, "source_mission_id": source["mission_id"],
            "provider_ids": providers, "claim_hash": _sha(c["callback_token"])}


def plan_digest(plan):
    return _digest(plan)


def _rows(cur, query, params, columns):
    cur.execute(query, params)
    return json.loads(_json([dict(zip(columns, row)) for row in cur.fetchall()]))


def _fresh(cur, plan, claim_rows, case_rows):
    p = plan["preimage"]; c = p["claim"][0]["record"]
    result = {"claim": claim_rows, "case": case_rows, "card_mission_id": p["card_mission_id"]}
    result["related_claims"] = _rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
        where mission_id=%s or provider_message_id=any(%s)
          or preview_payload->'provider_message_ids' ?| %s limit 129""",
        (c["mission_id"], plan["provider_ids"], plan["provider_ids"]), ("record",))
    result["family"] = _rows(cur, """select count(*),count(*) filter (where
        review_json->'family_message_lifecycle'->>'state' in ('delivery_attempted','delivered',
        'update_attempted','updated','contained','notification_attempted','notification_delivered'))
        from public.sam_live_stock_conversation_review_events where event_source=%s and
        (chatwoot_conversation_id=%s or review_json->'family_message_lifecycle'->>'card_mission_id'=%s)""",
        (FAMILY_SOURCE, p["card_mission_id"], p["card_mission_id"]), ("row_count", "effect_rows"))
    result["case_events"] = _rows(cur, """select to_jsonb(e) from app_private.oom_manager_case_events e
        where case_id=%s order by occurred_at desc,event_id desc limit 6""",
        (p["case"][0]["record"]["case_id"],), ("record",))
    result["claim_audits"] = _rows(cur, """select event_id,event_type,idempotency_key,payload_json,occurred_at
        from public.operational_events where aggregate_type='protected_action_claim'
        and aggregate_id=%s order by occurred_at desc limit 129""", (plan["claim_hash"],),
        ("event_id", "event_type", "idempotency_key", "payload_json", "occurred_at"))
    result["source_history"] = _rows(cur, """select review_event_id,created_at,
        review_json->'herdmaster_health_loss' from public.sam_live_stock_conversation_review_events
        where event_source=%s and (review_json->'herdmaster_health_loss'->>'mission_id'=%s
        or review_json->'herdmaster_health_loss'->'consumed_context_missions' ? %s
        or exists (select 1 from jsonb_array_elements(coalesce(review_json->'herdmaster_health_loss'
        ->'superseded_duplicate_bindings','[]'::jsonb)) b where b->>'mission_id'=%s))
        order by created_at desc,review_event_id desc limit 129""",
        (REPORT_SOURCE, plan["source_mission_id"], plan["source_mission_id"], plan["source_mission_id"]),
        ("review_event_id", "created_at", "record"))
    result["animal"] = _rows(cur, "select to_jsonb(p) from public.current_canonical_pigs p where pig_id=%s",
        (p["animal"][0]["record"]["pig_id"],), ("record",))
    result["cycle"] = _rows(cur, """select cycle_id,source_revision,status,started_at,case_counts
        from app_private.oom_manager_worker_cycles where cycle_id=%s""",
        (p["cycle"][0]["cycle_id"],), ("cycle_id", "source_revision", "status", "started_at", "case_counts"))
    return result


def apply_correction(plan, *, authorize, verify_prevention, connect_factory):
    """Apply four atomic metadata writes, or replay with zero writes.

    Mandatory trusted caller hooks run BEFORE connection: authorize(digest)
    authenticates genuine current owner/transport authority for the exact plan
    (including reviewed historical call-path proof) and returns its audit ref;
    verify_prevention(candidate_revision, tree) proves provider and app are loaded
    with that exact tree, returning loaded_revision/loaded_tree. A protected merge
    SHA may differ from the candidate SHA. Exceptions/refusals stop before DB access. Neither hook
    may substitute a plan/file boolean for external authority/deployment proof.
    The injected connection must be fresh, non-autocommit and bounded on connect.
    """
    plan = deepcopy(plan)
    rebuilt = prepare_plan(plan["preimage"], prevention_revision=plan["prevention_revision"],
                           prevention_tree=plan["prevention_tree"],
                           authorization_expires_at=plan["authorization_expires_at"])
    _require(plan == rebuilt, "plan_binding_mismatch")
    _require(datetime.now(timezone.utc) < _time(plan["authorization_expires_at"]),
             "authorization_expired")
    digest = plan_digest(plan)
    _require(callable(authorize) and callable(verify_prevention) and callable(connect_factory),
             "trusted_caller_hooks_required")
    authority = authorize(digest)
    _require(type(authority) is str and bool(authority.strip()), "owner_authority_required")
    deployed = verify_prevention(plan["prevention_revision"], plan["prevention_tree"])
    _require(isinstance(deployed, dict) and deployed.get("loaded_tree") == plan["prevention_tree"]
             and re.fullmatch(r"[0-9a-f]{40}", str(deployed.get("loaded_revision") or "")) is not None,
             "deployed_prevention_unproven")
    c, m, _source = _validate(plan["preimage"])
    key = "oom-presend-timeout-correction:" + plan["claim_hash"]
    event_id = "OOM-PRESEND-CORRECTION-" + plan["claim_hash"][:32].upper()
    with connect_factory() as db:
        _require(db.autocommit is False, "transaction_connection_required")
        with db.cursor() as cur:
            cur.execute("set local statement_timeout='5000ms'")
            cur.execute("set local lock_timeout='5000ms'")
            cur.execute("set local timezone='UTC'")
            lock = int(_sha("protected-claim|" + c["mission_id"])[:15], 16)
            cur.execute("select pg_advisory_xact_lock(%s)", (lock,))
            prior = _rows(cur, """select event_id,payload_json from public.operational_events
                where idempotency_key=%s""", (key,), ("event_id", "payload_json"))
            if prior:
                _require(len(prior) == 1 and prior[0]["event_id"] == event_id
                         and prior[0]["payload_json"].get("plan_sha256") == digest,
                         "correction_replay_conflict")
                return {"status": "already_applied", "metadata_writes": 0, "audit_event_id": event_id}
            cases = _rows(cur, """select to_jsonb(m) from app_private.oom_manager_cases m
                where case_id=%s for update""", (m["case_id"],), ("record",))
            claims = _rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
                where callback_token=%s for update""", (c["callback_token"],), ("record",))
            fresh = _fresh(cur, plan, claims, cases)
            _require(_digest(fresh) == plan["preimage_sha256"], "fresh_preimage_mismatch")
            _validate(fresh)
            cur.execute("select clock_timestamp()")
            now = cur.fetchone()[0]
            _require(_time(c["expires_at"]) < now < _time(plan["authorization_expires_at"]),
                     "expiry_or_authority_window_invalid")
            expiry = now + timedelta(seconds=TTL_SECONDS)
            archive = {k: c[k] for k in ARCHIVED_MARKERS}
            audit = {"contract_version": CONTRACT, "plan_sha256": digest,
                     "preimage_sha256": plan["preimage_sha256"], "claim_hash": plan["claim_hash"],
                     "case_id": m["case_id"], "generation": m["generation"],
                     "evidence_digest": m["evidence_digest"], "preview_digest": c["preview_digest"],
                     "archived_claim_markers": archive, "original_renewal": fresh["claim_audits"][0],
                     "new_expires_at": expiry.isoformat(), "one_time_only": True,
                     "authority_reference": authority, "prevention_revision": plan["prevention_revision"],
                     "prevention_tree": plan["prevention_tree"], "deployed_revision": deployed["loaded_revision"],
                     "provider_attempts": 0, "farm_writes": 0, "scheduler_triggers": 0}
            cur.execute("""insert into public.operational_events(event_id,idempotency_key,schema_version,
                event_type,domain,aggregate_type,aggregate_id,source_system,source_record_id,authority_tier,
                privacy_class,actor_type,actor_id,correlation_id,causation_id,occurred_at,recorded_at,
                freshness_at,payload_json,provenance_json) values(%s,%s,'1',%s,'incidents',
                'protected_action_claim',%s,'manual_presend_timeout_correction',%s,'owner_approved',
                'owner_private','owner','authenticated_operator',%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                returning payload_json""",
                (event_id, key, EVENT_TYPE, plan["claim_hash"], m["case_id"], m["case_id"],
                 fresh["cycle"][0]["cycle_id"], now, now, now, _json(audit),
                 _json({"source_ref": "sha256:" + plan["preimage_sha256"]})))
            inserted = cur.fetchone()
            _require(cur.rowcount == 1 and inserted and inserted[0] == audit, "audit_insert_failed")
            cur.execute("""update app_private.oom_protected_action_claims c set status='active',
                delivery_state='claim_created',expires_at=%s,delivery_attempt_id=null,
                delivery_attempted_at=null,delivery_ambiguous_at=null,delivery_result=null
                where callback_token=%s and to_jsonb(c)=%s::jsonb returning to_jsonb(c)""",
                (expiry, c["callback_token"], _json(c)))
            updated = cur.fetchone()
            _require(cur.rowcount == 1 and updated, "claim_cas_failed")
            expected = {**c, "status": "active", "delivery_state": "claim_created",
                        "expires_at": expiry.isoformat(), **{k: None for k in ARCHIVED_MARKERS[:4]}}
            _require(_same_projection(updated[0], expected, {"expires_at"}), "claim_readback_failed")
            cur.execute("""update app_private.oom_manager_cases m set status='waiting_reassessment',
                next_reassessment_at=%s,updated_at=%s where case_id=%s and to_jsonb(m)=%s::jsonb
                returning to_jsonb(m)""", (now, now, m["case_id"], _json(m)))
            updated_case = cur.fetchone()
            _require(cur.rowcount == 1 and updated_case, "case_cas_failed")
            expected_case = {**m, "status": "waiting_reassessment",
                             "next_reassessment_at": now.isoformat(), "updated_at": now.isoformat()}
            _require(_same_projection(updated_case[0], expected_case,
                                     {"next_reassessment_at", "updated_at"}), "case_readback_failed")
            manager_event = {"case_id": m["case_id"], "generation": m["generation"],
                "event_type": "reassessment_scheduled", "occurred_at": now.isoformat(),
                "contract_version": CONTRACT, "correction_audit_event_id": event_id,
                "plan_sha256": digest, "next_reassessment_at": now.isoformat(),
                "outcome_status": "proven_presend_timeout_classification_corrected"}
            cur.execute("""insert into app_private.oom_manager_case_events
                (event_id,case_id,generation,event_type,event_payload,occurred_at)
                values(%s,%s,%s,'reassessment_scheduled',%s::jsonb,%s) returning event_payload""",
                (event_id + "-REASSESS", m["case_id"], m["generation"], _json(manager_event), now))
            inserted = cur.fetchone()
            _require(cur.rowcount == 1 and inserted and inserted[0] == manager_event,
                     "case_event_insert_failed")
    return {"status": "applied", "metadata_writes": 4, "audit_event_id": event_id,
            "new_expires_at": expiry.isoformat(), "provider_attempts": 0, "farm_writes": 0}
