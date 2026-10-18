"""Typed, default-inert hosted admission for one existing receipt-only CORE scope.

This adapter never admits general coding work. The existing intake service owns
all three business receipt effects and rechecks policy/owner/holds in each
transaction. Render attestations are owner-supplied independent evidence, not
claims made by the worker and not a replacement for provider readback.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
import uuid

from modules.charlie import manager_dependency_intake as intake
from modules.charlie import mission_store

MISSION_ID = "OMQ-20260813-03-CORE-INTAKE-20261010"
POLICY_ID = "core.manager_dependency_intake.20261010"
CASE_IDS = frozenset({"OOM-CASE-0AA47A67BCA8B781902CEF95", "OOM-CASE-B59577B008D2E358F64F8771"})
WORKER_SERVICE = "srv-dacofeoae00c73813eug"
API_SERVICE = "srv-d6sijjkhg0os73f7regg"
CONTRACT = "core.cloud_receipt_intake.v1"
MAX_SECONDS = 1200
MAX_CYCLES = 40
POLL_SECONDS = 30
META_KEY = "cloud_receipt_epoch"
RETIRED_WINDOWS_IDS = (
    "57bba103be48426a897dfe576da1ed62", "c7c152ae5f25421c8b1d847c62bdcfa3",
    "c326ce47f7bf4caabe05f01c3659569a", "e90d2485a18141bc8957dada70f7d794",
    "8001db5061234a658472a35d2a096f9d",
)


class CloudIntakeRefused(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise CloudIntakeRefused(reason)


def shape(value, keys):
    need(isinstance(value, dict) and set(value) == set(keys), "request_shape_invalid")
    return value


def hex_value(value, size=64):
    need(isinstance(value, str) and re.fullmatch("[a-f0-9]{%d}" % size, value), "identity_invalid")
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _one(cur, sql, params, reason):
    cur.execute(sql, params)
    rows = cur.fetchmany(2)
    need(len(rows) == 1, reason)
    return rows[0][0]


def _now(cur):
    return intake._time(_one(cur, "select clock_timestamp()", None, "clock_unavailable"))


def hosted_connection(target):
    """Explicit verified TLS; no dotenv, weaker fallback or worker DB access."""
    import psycopg
    info = psycopg.conninfo.conninfo_to_dict(target)
    allowed = {"host", "port", "dbname", "user", "password", "sslmode", "sslrootcert"}
    need(set(info) <= allowed and all(info.get(k) for k in ("host", "dbname", "user", "password")),
         "database_configuration_invalid")
    ca = Path(os.environ.get("CORE_CLOUD_INTAKE_CA_FILE", ""))
    need(ca.is_absolute() and ca.is_file() and ca.stat().st_size <= 65536, "database_ca_unavailable")
    expected = hex_value(os.environ.get("CORE_CLOUD_INTAKE_CA_SHA256", ""))
    need(hmac.compare_digest(hashlib.sha256(ca.read_bytes()).hexdigest(), expected), "database_ca_changed")
    return psycopg.connect(**{k: v for k, v in info.items() if k not in {"sslmode", "sslrootcert"}},
        sslmode="verify-full", sslrootcert=str(ca), connect_timeout=3, client_encoding="UTF8")


def _open(database_url, connect_factory):
    need(str(os.environ.get("CORE_CLOUD_INTAKE_ENABLED", "")).strip().lower() == "true",
         "cloud_intake_disabled")
    return intake._open(mission_store._database_url(database_url), connect_factory or hosted_connection,
                        time.monotonic() + 10)


def _policy(cur, *, locked=False):
    return _one(cur, "select to_jsonb(p) from public.charlie_delegation_policies p where policy_id=%s"
                + (" for update" if locked else ""), (POLICY_ID,), "policy_missing")


def _epoch(policy):
    value = (policy.get("metadata_json") or {}).get(META_KEY)
    need(isinstance(value, dict) and value.get("contract") == CONTRACT, "cloud_epoch_missing")
    return value


def _fixed_scope(policy):
    scope = intake.validate_scope(policy.get("scope_json"))
    need(policy.get("policy_id") == POLICY_ID and scope["mission_id"] == MISSION_ID
         and len(scope["dependencies"]) == 2
         and {d["case_id"] for d in scope["dependencies"]} == CASE_IDS,
         "fixed_scope_changed")
    need(policy.get("max_actions") == 2 and float(policy.get("max_cost", -1)) == 0
         and policy.get("rollback_required") is True and policy.get("deterministic_gate_required") is True,
         "policy_limits_changed")
    return scope


def _validate_inputs(cur, policy, now):
    scope = _fixed_scope(policy)
    # Reuse the canonical validator without enabling the stored policy.
    prospective = dict(policy, enabled=True, expires_at=(now + timedelta(seconds=1)).isoformat())
    intake._policy_matches(prospective, prospective, now)
    need(scope["owner_binding"] == intake._mortality_owner_binding(), "current_owner_changed")
    principal = intake.resolve_family_principal({"telegram_user_id": scope["owner_user_id"],
        "telegram_chat_id": scope["owner_user_id"], "telegram_chat_type": "private"}, os.environ)
    need(principal.is_owner, "mission_owner_not_current")
    if policy["authority_tier"] == "charlie_delegated":
        need(_one(cur, "select tier from public.charlie_capability_trust where capability_key=%s",
             (intake.CAPABILITY,), "trust_missing") in {"delegated", "auto"}, "trust_not_delegated")
    mission = _one(cur, "select to_jsonb(m) from public.charlie_missions m where m.mission_id=%s and "
        + intake._not_durably_superseded_sql().replace("public.charlie_missions.mission_id", "m.mission_id"),
        (MISSION_ID,), "mission_missing")
    intake._mission_matches(mission, policy, scope)
    created = _one(cur, "select to_jsonb(e) from public.charlie_mission_events e where mission_id=%s and event_type='created' limit 2",
                   (MISSION_ID,), "created_event_missing_or_ambiguous")
    hold, code = mission_store.owner_execution_hold_status(MISSION_ID, cursor=cur)
    need(code == 200 and hold.get("active") is False, "mission_hold_unavailable_or_active")
    for dep in scope["dependencies"]:
        case = _one(cur, "select to_jsonb(c) from app_private.oom_manager_cases c where case_id=%s",
                    (dep["case_id"],), "dependency_missing")
        event = _one(cur, "select to_jsonb(e) from app_private.oom_manager_case_events e where event_id=%s and case_id=%s",
                     (dep["anchor_event_id"], dep["case_id"]), "original_anchor_missing")
        cycle = _one(cur, "select to_jsonb(c) from app_private.oom_manager_worker_cycles c where cycle_id=%s",
                     (dep["anchor_cycle_id"],), "original_cycle_missing")
        intake._dependency_matches(case, event, cycle, scope, dep, now)
        cur.execute("""select to_jsonb(e),to_jsonb(c)
            from app_private.oom_manager_case_events e
            left join app_private.oom_manager_worker_cycles c on c.cycle_id=e.event_payload->>'cycle_id'
            where e.case_id=%s and e.occurred_at>=%s
              and e.event_type in ('delivery_suppressed','delivery_confirmed','exception','contained','completed')
              and coalesce(e.event_payload->>'outcome_status','')<>'manager_engineering_intake_recorded'
            order by e.occurred_at desc,e.event_id desc limit 1""", (dep["case_id"], event["occurred_at"]))
        latest = cur.fetchone()
        need(latest and latest[0] and latest[1], "current_anchor_missing")
        intake._dependency_matches(case, latest[0], latest[1], scope,
            dict(dep, anchor_event_id=latest[0]["event_id"], anchor_cycle_id=latest[1]["cycle_id"]), now)
    return scope, mission, created


def _receipt_counts(cur, policy):
    scope = _fixed_scope(policy)
    records = []
    for dep in scope["dependencies"]:
        command, payload, event, command_id, expected = intake._packets(policy, scope, dep)
        link_id = "OOM-CORE-INTAKE-" + intake.digest({"mission_id": MISSION_ID, "dependency_id": dep["dependency_id"]})[:32].upper()
        cur.execute("""select
            (select count(*) from public.charlie_control_commands where command_id=%s),
            (select count(*) from public.charlie_mission_events where event_id=%s),
            (select count(*) from app_private.oom_manager_case_events where event_id=%s)""",
            (command_id, event["event_id"], link_id))
        counts = cur.fetchone()
        verified = False
        if list(counts) == [1, 1, 1]:
            intake._readback(cur, command, event, command_id, expected)
            link = {"contract": intake.CONTRACT, "dependency_id": dep["dependency_id"],
                "scope_digest": intake.digest(scope), "mission_id": MISSION_ID,
                "event_id": event["event_id"], "command_id": command_id,
                "anchor_event_id": dep["anchor_event_id"], "finding_received": True,
                "worker_selected": False, "worker_picked_up": False, "repair_verified": False}
            expected_link = {"outcome_status": "manager_engineering_intake_recorded", "delivery_confirmed": False,
                             "completion_proven": False, "engineering_intake": link}
            cur.execute("select case_id,generation,event_type,event_payload from app_private.oom_manager_case_events where event_id=%s", (link_id,))
            stored = cur.fetchone()
            need(stored and stored[:3] == (dep["case_id"], dep["generation"], "delivery_suppressed")
                 and intake.digest(stored[3]) == intake.digest(expected_link), "manager_link_readback_conflict")
            verified = True
        records.append({"command_id": command_id, "finding_id": event["event_id"], "link_id": link_id,
                        "counts": list(counts), "verified": verified})
    return records


def _receipt_preimage(policy, receipts):
    return intake.digest({"scope_sha256": intake.digest(policy["scope_json"]), "receipts": receipts})


def _partial_pair(cur, policy, receipts):
    # Only the observed split: committed first pair, missing first link, untouched
    # second dependency. Counts alone never establish that the pair is reusable.
    need([r["counts"] for r in receipts] == [[1, 1, 0], [0, 0, 0]], "recovery_receipt_pattern_refused")
    scope = _fixed_scope(policy)
    command, _, event, command_id, result = intake._packets(policy, scope, scope["dependencies"][0])
    intake._readback(cur, command, event, command_id, result)


def _recovery_material(cur, policy, receipts):
    prior = _epoch(policy)
    need(policy["enabled"] is False and prior["status"] == "revoked"
         and prior.get("recovery") is None, "prior_recovery_not_eligible")
    need(prior["scope_sha256"] == intake.digest(policy["scope_json"])
         and intake._time(prior["expires_at"]) == intake._time(policy["expires_at"]),
         "prior_epoch_binding_changed")
    cycles = prior["cycles"]
    need(len(cycles) == 1 and cycles[0]["status"] == "completed", "prior_failure_not_terminal")
    cycle = cycles[0]
    result = cycle.get("result") or {}
    need(result.get("contract") == CONTRACT and result.get("epoch_id") == prior["epoch_id"]
         and result.get("request_id") == cycle["request_id"] and result.get("success") is False
         and result.get("model_calls") == 0 and result.get("farm_actions") == 0
         and result.get("mission_pickup_attempted") is False
         and result.get("status") == "receipt_cycle_complete"
         and result.get("intake") == {"status": "manager_dependency_intake_checked", "failures": 2,
             "results": [{"status": "manager_dependency_intake_unavailable", "failure_kind": "TimeoutError"}] * 2},
         "prior_failure_not_recoverable")
    _partial_pair(cur, policy, receipts)
    return {"prior_epoch_id": hex_value(prior["epoch_id"], 32),
            "prior_request_id": hex_value(cycle["request_id"], 32),
            "receipt_state_sha256": _receipt_preimage(policy, receipts)}


def _check_epoch_receipt_preimage(cur, policy):
    epoch = _epoch(policy)
    receipts = _receipt_counts(cur, policy)
    need(epoch.get("receipt_preimage_sha256") == _receipt_preimage(policy, receipts),
         "receipt_preimage_changed_before_enable")
    recovery = epoch.get("recovery")
    if recovery is not None:
        _partial_pair(cur, policy, receipts)
        need(recovery["receipt_state_sha256"] == _receipt_preimage(policy, receipts),
             "recovery_preimage_changed_before_enable")


def _public(policy, now):
    epoch = (policy.get("metadata_json") or {}).get(META_KEY)
    packet = {"contract": CONTRACT, "policy_id": POLICY_ID, "mission_id": MISSION_ID,
        "policy_sha256": intake.digest(policy), "scope_sha256": intake.digest(policy.get("scope_json")),
        "server_time": now.isoformat(), "enabled": policy["enabled"] is True,
        "expires_at": intake._time(policy["expires_at"]).isoformat(), "max_model_cost": 0}
    if isinstance(epoch, dict):
        packet["epoch"] = {k: deepcopy(epoch[k]) for k in (
            "epoch_id", "status", "issued_at", "expires_at", "provider", "scope_sha256", "worker_instance", "cycles")}
        if epoch.get("recovery") is not None:
            packet["epoch"]["recovery"] = deepcopy(epoch["recovery"])
    return packet


def readiness(*, database_url=None, connect_factory=None):
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        db.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        policy, now = _policy(cur), _now(cur)
        scope, mission, created = _validate_inputs(cur, policy, now)
        result = _public(policy, now)
        result.update(mission_sha256=intake.digest(mission), created_sha256=intake.digest(created),
                      producer_revision=scope["producer_revision"], receipts=_receipt_counts(cur, policy))
        prior = (policy.get("metadata_json") or {}).get(META_KEY)
        if prior and prior.get("status") == "revoked" and any(r["counts"] != [0, 0, 0] for r in result["receipts"]):
            # A read exposes a proposal only; it cannot renew, replay or enable.
            if any(r["counts"] != [1, 1, 1] for r in result["receipts"]):
                result["recovery"] = _recovery_material(cur, policy, result["receipts"])
        return result


def evidence(epoch_id, *, database_url=None, connect_factory=None):
    """Read revocation preimages even when current business readiness has failed."""
    hex_value(epoch_id, 32)
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        db.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        policy, now = _policy(cur), _now(cur)
        need(_epoch(policy)["epoch_id"] == epoch_id, "epoch_identity_mismatch")
        result = _public(policy, now)
        cur.execute("""select event_id,created_at,metadata_json->>'operation',
                   metadata_json->>'prior_policy_sha256',metadata_json->>'policy_sha256'
            from public.charlie_mission_events
            where mission_id=%s and event_type='review_note'
              and metadata_json->>'contract'=%s and metadata_json->>'epoch_id'=%s
            order by created_at,event_id limit 128""", (MISSION_ID, CONTRACT, epoch_id))
        rows = cur.fetchmany(128)
        need(len(rows) < 128, "epoch_audit_bound")
        result["audits"] = [{"event_id": r[0], "created_at": intake._time(r[1]).isoformat(),
            "operation": r[2], "prior_policy_sha256": r[3], "policy_sha256": r[4]} for r in rows]
        try:
            result["receipts"] = _receipt_counts(cur, policy)
            result["receipt_readback"] = "checked"
        except (CloudIntakeRefused, intake.IntakeRefused):
            result["receipts"] = []
            result["receipt_readback"] = "unverified"
        return result


def _provider(value, now):
    shape(value, {"worker_service_id", "worker_deploy_id", "worker_revision", "api_service_id",
        "api_deploy_id", "api_revision", "observed_at", "evidence_sha256"})
    need(value["worker_service_id"] == WORKER_SERVICE and value["api_service_id"] == API_SERVICE,
         "provider_service_changed")
    for key in ("worker_revision", "api_revision"):
        hex_value(value[key], 40)
    for key in ("worker_deploy_id", "api_deploy_id"):
        need(isinstance(value[key], str) and re.fullmatch(r"dep-[a-z0-9]{10,60}", value[key]), "provider_deploy_invalid")
    hex_value(value["evidence_sha256"])
    need(timedelta(0) <= now - intake._time(value["observed_at"]) <= timedelta(minutes=10), "provider_evidence_stale")
    need(value["api_revision"] == os.environ.get("RENDER_GIT_COMMIT")
         and os.environ.get("RENDER_SERVICE_ID") == API_SERVICE, "hosted_api_identity_mismatch")
    return deepcopy(value)


def _save(cur, db, old, updated, kind, actor, now):
    need(len(encoded(updated).encode()) <= 1048576, "policy_history_bound")
    now = _now(cur)
    if kind in {"epoch_created_disabled", "enabled", "cycle_begun"}:
        need(now < intake._time(updated["expires_at"]), "epoch_expired_before_write")
    cur.execute("""update public.charlie_delegation_policies p
        set enabled=%s,expires_at=%s,metadata_json=%s::jsonb,updated_at=%s
        where policy_id=%s and to_jsonb(p)=%s::jsonb returning to_jsonb(p)""",
        (updated["enabled"], updated["expires_at"], encoded(updated["metadata_json"]), now, POLICY_ID, encoded(old)))
    row = cur.fetchone()
    need(row is not None, "policy_compare_and_swap_refused")
    expected = dict(updated, updated_at=now.isoformat())
    actual = row[0]
    need(set(actual) == set(expected) and all(
        intake._time(actual[k]) == intake._time(expected[k]) if k in {"expires_at", "updated_at", "created_at"}
        else actual[k] == expected[k] for k in expected), "policy_postimage_changed")
    audit = {"contract": CONTRACT, "operation": kind, "epoch_id": _epoch(actual)["epoch_id"],
        "recorded_by": actor, "prior_policy_sha256": intake.digest(old), "policy_sha256": intake.digest(actual),
        "scope_sha256": intake.digest(actual["scope_json"]), "prior_policy": old if kind == "epoch_created_disabled" else None,
        "retired_windows_ids": list(RETIRED_WINDOWS_IDS), "business_effects": []}
    result, code = mission_store.record_mission_event(MISSION_ID, "review_note",
        notes="Cloud receipt-only commissioning: " + kind + ". No coding or farm action.", metadata=audit,
        database_url="borrowed", connect_factory=lambda _: nullcontext(db))
    need(code == 201 and result.get("success") is True, "canonical_audit_refused")
    cur.execute("""select metadata_json from public.charlie_mission_events
        where mission_id=%s and event_type='review_note' and metadata_json=%s::jsonb limit 2""", (MISSION_ID, encoded(audit)))
    need(len(cur.fetchmany(2)) == 1, "canonical_audit_readback_failed")
    return actual


def create_epoch(payload, *, actor, database_url=None, connect_factory=None):
    keys = {"policy_sha256", "mission_sha256", "created_sha256", "scope_sha256", "duration_seconds",
            "provider", "worker_token_sha256"}
    shape(payload, keys | ({"recovery"} if isinstance(payload, dict) and "recovery" in payload else set()))
    if "recovery" in payload:
        shape(payload["recovery"], {"prior_epoch_id", "prior_request_id", "receipt_state_sha256"})
        hex_value(payload["recovery"]["prior_epoch_id"], 32)
        hex_value(payload["recovery"]["prior_request_id"], 32)
        hex_value(payload["recovery"]["receipt_state_sha256"])
    for key in ("policy_sha256", "mission_sha256", "created_sha256", "scope_sha256", "worker_token_sha256"):
        hex_value(payload[key])
    need(isinstance(actor, str) and actor.startswith("owner-admin:") and len(actor) <= 200, "owner_principal_required")
    need(type(payload["duration_seconds"]) is int and 60 <= payload["duration_seconds"] <= MAX_SECONDS, "epoch_duration_invalid")
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        old, now = _policy(cur, locked=True), _now(cur)
        need(old["enabled"] is False and intake.digest(old) == payload["policy_sha256"], "disabled_policy_preimage_changed")
        scope, mission, created = _validate_inputs(cur, old, now)
        need(intake.digest(scope) == payload["scope_sha256"] and intake.digest(mission) == payload["mission_sha256"]
             and intake.digest(created) == payload["created_sha256"], "current_world_changed")
        receipts = _receipt_counts(cur, old)
        recovery = None
        if any(r["counts"] != [0, 0, 0] for r in receipts):
            need("recovery" in payload, "initial_receipts_not_empty")
            recovery = _recovery_material(cur, old, receipts)
            need(payload["recovery"] == recovery, "recovery_preimage_changed")
        else:
            need("recovery" not in payload, "recovery_not_needed")
        previous = (old.get("metadata_json") or {}).get(META_KEY)
        if previous:
            need(previous.get("status") == "revoked" and not any(c["status"] == "begun" for c in previous["cycles"]), "prior_cloud_epoch_unclosed")
            need(previous.get("worker_token_sha256") != payload["worker_token_sha256"], "credential_reuse_refused")
        provider = _provider(payload["provider"], now)
        epoch_id = uuid.uuid4().hex
        expiry = now + timedelta(seconds=payload["duration_seconds"])
        need(intake._time(old["expires_at"]) != expiry, "epoch_expiry_must_change")
        epoch = {"contract": CONTRACT, "epoch_id": epoch_id, "status": "prepared_disabled",
            "issued_at": now.isoformat(), "expires_at": expiry.isoformat(), "owner_principal": actor,
            "provider": provider, "scope_sha256": intake.digest(scope), "worker_token_sha256": payload["worker_token_sha256"],
            "worker_instance": None, "cycles": [], "prior_policy_sha256": intake.digest(old),
            "receipt_preimage_sha256": _receipt_preimage(old, receipts), "recovery": recovery,
            "retired_windows_ids": list(RETIRED_WINDOWS_IDS)}
        updated = deepcopy(old)
        updated["expires_at"] = expiry.isoformat()
        updated["metadata_json"] = dict(old.get("metadata_json") or {}, **{META_KEY: epoch})
        actual = _save(cur, db, old, updated, "epoch_created_disabled", actor, now)
        return _public(actual, now)


def set_enabled(epoch_id, payload, *, enabled, actor, database_url=None, connect_factory=None):
    shape(payload, {"policy_sha256"})
    hex_value(epoch_id, 32)
    hex_value(payload["policy_sha256"])
    need(isinstance(actor, str) and actor.startswith("owner-admin:") and len(actor) <= 200, "owner_principal_required")
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        old, now = _policy(cur, locked=True), _now(cur)
        epoch = _epoch(old)
        need(epoch["epoch_id"] == epoch_id and intake.digest(old) == payload["policy_sha256"], "epoch_preimage_changed")
        updated = deepcopy(old)
        state = _epoch(updated)
        if enabled:
            need(epoch["status"] == "prepared_disabled" and old["enabled"] is False
                 and now < intake._time(epoch["expires_at"]), "epoch_not_enableable")
            _provider(epoch["provider"], now)
            _validate_inputs(cur, old, now)
            _check_epoch_receipt_preimage(cur, old)
            state["status"] = "enabled"
        else:
            state["status"] = "revoked"
        updated["enabled"] = bool(enabled)
        actual = _save(cur, db, old, updated, "enabled" if enabled else "revoked", actor, now)
        return _public(actual, now)


def _authenticate(policy, token, now, *, allow_inactive=False):
    epoch = _epoch(policy)
    need(isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token), "worker_unauthorized")
    need(hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), epoch["worker_token_sha256"]), "worker_unauthorized")
    need(epoch["provider"]["api_revision"] == os.environ.get("RENDER_GIT_COMMIT")
         and os.environ.get("RENDER_SERVICE_ID") == API_SERVICE, "hosted_api_identity_mismatch")
    need(epoch["scope_sha256"] == intake.digest(_fixed_scope(policy))
         and intake._time(epoch["expires_at"]) == intake._time(policy["expires_at"]), "epoch_binding_changed")
    if not allow_inactive:
        need(policy["enabled"] is True and epoch["status"] == "enabled"
             and intake._time(epoch["issued_at"]) <= now < intake._time(epoch["expires_at"]), "epoch_inactive")
    return epoch


def current(token, *, database_url=None, connect_factory=None):
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        db.connection.execute("SET TRANSACTION READ ONLY")
        policy, now = _policy(cur), _now(cur)
        if not (policy.get("metadata_json") or {}).get(META_KEY):
            # Public inert bootstrap status conveys no scope, token or owner data.
            return {"contract": CONTRACT, "status": "awaiting_epoch", "active": False, "poll_seconds": POLL_SECONDS}
        epoch = _authenticate(policy, token, now, allow_inactive=True)
        return {"contract": CONTRACT, "status": epoch["status"], "epoch_id": epoch["epoch_id"], "expires_at": epoch["expires_at"],
            "active": policy["enabled"] is True and epoch["status"] == "enabled" and now < intake._time(epoch["expires_at"]),
            "provider": epoch["provider"], "poll_seconds": POLL_SECONDS, "server_time": now.isoformat()}


def cycle(payload, token, *, database_url=None, connect_factory=None):
    shape(payload, {"epoch_id", "request_id", "worker_instance", "worker_service_id", "worker_revision"})
    for key in ("epoch_id", "request_id", "worker_instance"):
        hex_value(payload[key], 32)
    hex_value(payload["worker_revision"], 40)
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        old, now = _policy(cur, locked=True), _now(cur)
        epoch = _authenticate(old, token, now)
        need(payload["epoch_id"] == epoch["epoch_id"] and payload["worker_service_id"] == WORKER_SERVICE
             and payload["worker_revision"] == epoch["provider"]["worker_revision"], "worker_identity_mismatch")
        need(epoch["worker_instance"] in (None, payload["worker_instance"]), "worker_instance_changed")
        prior = next((c for c in epoch["cycles"] if c["request_id"] == payload["request_id"]), None)
        if prior:
            need(prior["status"] == "completed", "cycle_outcome_pending_owner_readback")
            return deepcopy(prior["result"])
        need(len(epoch["cycles"]) < MAX_CYCLES and not any(c["status"] == "begun" for c in epoch["cycles"]), "cycle_not_available")
        if epoch["cycles"]:
            need(now - intake._time(epoch["cycles"][-1]["started_at"]) >= timedelta(seconds=POLL_SECONDS), "cycle_too_soon")
        updated = deepcopy(old)
        state = _epoch(updated)
        state["worker_instance"] = payload["worker_instance"]
        state["cycles"].append({"request_id": payload["request_id"], "status": "begun", "started_at": now.isoformat(), "result": None})
        expected = _save(cur, db, old, updated, "cycle_begun", "service:core.cloud_receipt_intake", now)
    # Pin this exact policy, not a newly loaded successor epoch. Existing intake
    # rechecks enabled/expiry/scope/current owner/hold in every write transaction.
    consumer_policy = dict(expected, scope=expected["scope_json"])
    context = {key: deepcopy(_epoch(expected)[key]) for key in (
        "contract", "epoch_id", "issued_at", "expires_at", "scope_sha256",
        "worker_token_sha256", "worker_instance", "provider")}
    result = intake.consume_manager_dependencies(mode="active", policies=[consumer_policy],
        database_url=database_url, connect_factory=connect_factory or hosted_connection, cloud_epoch=context)
    reply = {"contract": CONTRACT, "epoch_id": payload["epoch_id"], "request_id": payload["request_id"],
        "success": result.get("failures") == 0, "status": "receipt_cycle_complete", "intake": result,
        "mission_pickup_attempted": False, "model_calls": 0, "farm_actions": 0}
    with _open(database_url, connect_factory) as db, db.cursor() as cur:
        old, now = _policy(cur, locked=True), _now(cur)
        epoch = _authenticate(old, token, now, allow_inactive=True)
        need(epoch["epoch_id"] == payload["epoch_id"], "epoch_changed_before_cycle_readback")
        updated = deepcopy(old)
        entry = next(c for c in _epoch(updated)["cycles"] if c["request_id"] == payload["request_id"])
        need(entry["status"] == "begun", "cycle_completion_conflict")
        entry.update(status="completed", result=reply, finished_at=now.isoformat())
        _save(cur, db, old, updated, "cycle_completed", "service:core.cloud_receipt_intake", now)
    return reply
