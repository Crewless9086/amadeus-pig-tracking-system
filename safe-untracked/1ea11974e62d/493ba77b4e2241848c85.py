"""Transactional recovery on the existing mission projection and event plane.

An effect receipt is permission to attempt once, never proof of delivery.
Unresolved effects retain their full debit and prevent takeover/reissue.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone

VERSION = "charlie_native_recovery_v1"
REPOSITORY = "Crewless9086/amadeus-pig-tracking-system"
MAX_OPERATIONS = 256


class RecoveryDenied(ValueError):
    def __init__(self, status, code=409):
        self.status, self.code = status, code
        super().__init__(status)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def require(condition, status, code=409):
    if not condition:
        raise RecoveryDenied(status, code)


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value),
            "native_recovery_identity_invalid", 400)
    return value


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "native_recovery_expiry_invalid", 400)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        raise RecoveryDenied("native_recovery_expiry_invalid", 400) from None


def integer(value, maximum):
    require(type(value) is int and 0 < value <= maximum, "native_recovery_limit_invalid", 400)
    return value


def scope_for(mission_id, metadata, runtime):
    """Exact canonical expectations, not a builder-selected contract."""
    native = metadata.get("hermes_native_execution") or {}
    dispatch = metadata.get("dispatch_authorization") or {}
    hold = metadata.get("native_runner_blocker") or {}
    vault = metadata.get("mission_vault") or {}
    frozen = metadata.get("mission_admission_contract") or {}
    external = metadata.get("external_supervisor_state") or {}
    generation = native.get("generation") or dispatch.get("generation")
    require(isinstance(generation, str) and generation, "native_recovery_generation_missing")
    require(isinstance(hold, dict) and (hold.get("notification_identity") or hold.get("blocker_fingerprint")), "native_recovery_hold_missing")
    require(set(runtime) == {"worker_revision", "web_revision"} and all(
        isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v) for v in runtime.values()),
        "native_recovery_runtime_invalid")
    return {"mission_id": mission_id, "generation": generation, "hold": copy.deepcopy(hold),
            "repository": REPOSITORY, "runtime": dict(runtime),
            "native_execution_id": native.get("native_execution_id", ""),
            "worktree_digest": native.get("worktree_digest", ""),
            "branch": native.get("branch", ""),
            "starting_main_sha": native.get("starting_main_sha") or runtime["web_revision"],
            "prior_dispatch_base_sha": dispatch.get("base_sha", ""),
            "owner_instruction_digest": native.get("owner_instruction_digest") or dispatch.get("owner_instruction_digest", ""),
            "allowed_files": native.get("allowed_files") or dispatch.get("allowed_files", []),
            "allowed_effects": native.get("allowed_effects") or dispatch.get("allowed_effects", []),
            "forbidden_files": native.get("forbidden_files") or dispatch.get("forbidden_files", []),
            "forbidden_effects": native.get("forbidden_effects") or dispatch.get("forbidden_effects", []),
            "notifications": {"original_thread": {"channel": external.get("slack_channel_id", ""),
                                "thread_ts": external.get("slack_thread_ts", "")},
                              "owner_approval": {"channel": metadata.get("slack_approval_channel_id", ""), "thread_ts": ""}},
            "candidate": copy.deepcopy(metadata.get("review_packet") or {}),
            "contract": copy.deepcopy(frozen),
            "required_tests": frozen.get("required_tests") or vault.get("test_plan", []),
            "acceptance_criteria": frozen.get("operational_acceptance") if frozen else vault.get("acceptance_criteria", [])}


def _scope_compatible(scope, granted, anchor=None):
    if anchor:
        require(all(scope.get(k) == v for k,v in anchor.items()), "native_recovery_execution_anchor_conflict")
    for key in ("mission_id", "generation", "hold", "repository", "runtime", "owner_instruction_digest",
                "allowed_files", "notifications", "starting_main_sha"):
        require(scope[key] == granted[key], "native_recovery_scope_changed")
    for key in ("required_tests", "acceptance_criteria"):
        require(sorted(scope[key]) == sorted(granted[key]), "native_recovery_scope_changed")
    native_created = not granted["native_execution_id"] and bool(scope["native_execution_id"])
    if native_created:
        expected = hashlib.sha256(f"{scope['mission_id']}:{scope['generation']}:native-1".encode()).hexdigest().upper()
        require(scope["native_execution_id"] == "HNX-" + expected
                and scope["branch"] == f"charlie/{scope['mission_id'].lower()}-native-1"
                and re.fullmatch(r"[0-9a-f]{64}", scope["worktree_digest"]), "native_recovery_execution_changed")
        effects = [{"edit_allowed_documentation": "edit_allowed_files",
                    "open_or_update_draft_pr": "open_draft_pull_request"}.get(v, v)
                   for v in granted["allowed_effects"]]
        require(scope["allowed_effects"] == effects, "native_recovery_effect_scope_changed")
    else:
        for key in ("native_execution_id", "worktree_digest", "branch", "allowed_effects", "forbidden_files", "forbidden_effects"):
            require(scope[key] == granted[key], "native_recovery_execution_changed")
    if granted["contract"]:
        require(scope["contract"] == granted["contract"], "native_recovery_contract_changed")
    elif scope["contract"]:
        contract = scope["contract"]
        require(contract.get("base_sha") == granted["starting_main_sha"]
                and contract.get("generation") == granted["generation"]
                and contract.get("branch") == scope["branch"]
                and sorted(contract.get("allowed_files", [])) == sorted(granted["allowed_files"])
                and sorted(contract.get("allowed_effects", [])) == sorted(scope["allowed_effects"])
                and sorted(contract.get("forbidden_files", [])) == sorted(scope["forbidden_files"])
                and sorted(contract.get("forbidden_effects", [])) == sorted(scope["forbidden_effects"])
                and sorted(contract.get("required_tests", [])) == sorted(granted["required_tests"])
                and sorted(contract.get("operational_acceptance", [])) == sorted(granted["acceptance_criteria"]),
                "native_recovery_contract_changed")
    if granted["candidate"]:
        require(scope["candidate"].get("pr_number") == granted["candidate"].get("pr_number")
                and scope["candidate"].get("branch_name") == granted["candidate"].get("branch_name"),
                "native_recovery_candidate_changed")


def validate_receipt(effect, evidence):
    """Complete exact evidence; a worker boolean or another model's verdict is insufficient."""
    intent = effect["intent"]
    require(evidence.get("intent_sha256") == digest(intent), "native_recovery_receipt_identity_invalid")
    if effect["kind"] == "notification":
        require(set(evidence) == {"intent_sha256", "channel", "thread_ts", "ts", "client_msg_id", "text_sha256"}
                and all(evidence.get(k) == intent.get(k) for k in ("channel", "thread_ts", "client_msg_id", "text_sha256"))
                and isinstance(evidence.get("ts"), str) and re.fullmatch(r"\d+\.\d+", evidence["ts"])
                and isinstance(evidence.get("channel"), str) and evidence["channel"]
                and re.fullmatch(r"[0-9a-f-]{36}", str(evidence.get("client_msg_id")))
                and re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("text_sha256"))),
                "native_recovery_notification_receipt_invalid")
    elif effect["kind"] == "model":
        require(set(evidence) == {"intent_sha256", "request_id", "response_sha256", "provider", "model"}
                and evidence.get("provider") == intent.get("provider")
                and evidence.get("model") == intent.get("model")
                and isinstance(evidence.get("request_id"), str) and evidence["request_id"]
                and re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("response_sha256"))),
                "native_recovery_model_receipt_invalid")
    else:
        require(set(evidence) == {"intent_sha256", "result_sha256", "identity"}
                and evidence.get("identity") == intent.get("identity") and bool(intent.get("identity"))
                and re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("result_sha256"))),
                "native_recovery_effect_receipt_invalid")


def _fence(state, proof, now):
    grant, lease = state.get("grant") or {}, state.get("lease") or {}
    require(isinstance(proof, dict) and set(proof) == {"grant_id", "incarnation", "epoch", "claim_id"},
            "native_recovery_fence_required")
    expected = {k: lease.get(k) for k in proof}
    require(proof == expected and type(proof["epoch"]) is int, "native_recovery_fence_conflict")
    require(not lease.get("released"), "native_recovery_claim_released")
    require(now < timestamp(grant.get("expires_at")) and now < timestamp(lease.get("expires_at")),
            "native_recovery_authority_expired")
    return lease


def mutation_locks(cursor, mission_id):
    cursor.execute("select pg_advisory_xact_lock(hashtextextended('charlie-native-allocation',0))")
    cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (mission_id,))


def legacy_allocation_guard(cursor):
    """Shared allocation lock; called before existing legacy mission locks."""
    cursor.execute("select pg_advisory_xact_lock(hashtextextended('charlie-native-allocation',0))")
    cursor.execute("""select exists(select 1 from public.charlie_missions where
        metadata_json->'native_recovery'->'lease'->>'released'='false'
        or nullif(metadata_json->'hermes_native_execution'->>'worker_claim_id','') is not null)""")
    return cursor.fetchone()[0] is False


def mutation_guard(cursor, mission_id, metadata, proof):
    """Called after locks and row read, inside the actual mutation transaction."""
    try:
        state = metadata.get("native_recovery") or {}
        cursor.execute("select clock_timestamp()")
        now = cursor.fetchone()[0]
        _fence(state, proof, now)
        scope = scope_for(mission_id, metadata, state["grant"]["scope"]["runtime"])
        _scope_compatible(scope, state["grant"]["scope"], state.get("execution_anchor"))
        cursor.execute("select metadata_json from public.charlie_mission_events where mission_id=%s and metadata_json->>'native_recovery_checkpoint'='true' order by (metadata_json->>'sequence')::bigint desc limit 1", (mission_id,))
        checkpoint = cursor.fetchone()
        require(checkpoint is not None and checkpoint[0].get("state_sha256") == digest(state),
                "native_recovery_checkpoint_conflict")
        cursor.execute("""select exists(select 1 from public.charlie_owner_execution_hold_events h
            where h.mission_id=%s and h.event_type='hold_created' and not exists(select 1 from
            public.charlie_owner_execution_hold_events r where r.release_of_event_id=h.event_id and r.event_type='hold_released'))""", (mission_id,))
        require(cursor.fetchone()[0] is False, "native_recovery_owner_hold_or_unavailable", 423)
        require(not metadata.get("portfolio_classification") and not metadata.get("supersession"), "native_recovery_mission_not_current")
        cursor.execute("""select exists(select 1 from public.charlie_missions where mission_id<>%s and (
            metadata_json->'external_supervisor_state'->>'agent_state'='ACTIVE'
            or metadata_json->'external_supervisor_state'->>'run_state' in ('ACTIVE','RUNNING')
            or nullif(metadata_json->'hermes_native_execution'->>'worker_claim_id','') is not null
            or metadata_json->'execution_lease' is not null
            or metadata_json->'native_recovery'->'lease'->>'released'='false'))""", (mission_id,))
        require(cursor.fetchone()[0] is False and not metadata.get("execution_lease"), "native_recovery_competing_writer")
        return None
    except RecoveryDenied as exc:
        return {"success": False, "status": exc.status}, exc.code


def pin_execution(cursor, mission_id, metadata, event):
    state = metadata.get("native_recovery")
    if not state:
        return
    native = metadata["hermes_native_execution"]
    anchor = {k:native[k] for k in ("native_execution_id", "worktree_digest", "branch", "starting_main_sha",
                                  "forbidden_files", "forbidden_effects")}
    require(not state.get("execution_anchor") or state["execution_anchor"] == anchor,
            "native_recovery_execution_anchor_conflict")
    state["execution_anchor"] = anchor
    state["sequence"] += 1
    event(cursor, mission_id, "workflow_updated", "Native execution identity pinned.", {
        "native_recovery_checkpoint": True, "sequence": state["sequence"], "state_sha256": digest(state),
        "operation": "native_execution_pinned"})
    cursor.execute("select metadata_json from public.charlie_mission_events where mission_id=%s and metadata_json->>'native_recovery_checkpoint'='true' order by (metadata_json->>'sequence')::bigint desc limit 1", (mission_id,))
    written = cursor.fetchone()
    require(written is not None and written[0].get("state_sha256") == digest(state), "native_recovery_checkpoint_insert_failed", 503)


def transition(mission_id, metadata, operation, payload, *, principal, now, runtime,
               competing=False):
    """Pure transition; caller MUST hold allocation + mission + row locks."""
    require(isinstance(payload, dict), "native_recovery_payload_invalid", 400)
    original = metadata.get("native_recovery") or {}
    state = copy.deepcopy(original)
    scope = scope_for(mission_id, metadata, runtime)
    if operation == "read":
        return state, {"scope": scope, "state": state}, False
    if operation == "issue":
        require(principal.startswith("owner-admin:") and principal != "owner-admin:local-development",
                "owner_admin_session_required", 403)
        require(set(payload) - {"prior_state_sha256", "pricing_ceiling"} == {"request_id", "scope", "expires_at", "limits", "verification"},
                "native_recovery_grant_contract_invalid", 400)
        identity(payload["request_id"])
        require(payload["scope"] == scope, "native_recovery_scope_conflict")
        native = metadata.get("hermes_native_execution") or {}
        require(not (native.get("execution_status") == "OWNER_DECISION_REQUIRED"
                     and not native.get("worker_claim_id") and native.get("head_sha")
                     and native.get("owner_notification_head") == native.get("head_sha")),
                "native_recovery_obligations_already_complete")
        expiry = timestamp(payload["expires_at"])
        require(now < expiry and (expiry-now).total_seconds() <= 7200, "native_recovery_expiry_invalid")
        limits = payload["limits"]
        require(isinstance(limits, dict) and set(limits) == {"requests", "spend_microusd", "per_request_microusd"},
                "native_recovery_limit_invalid", 400)
        integer(limits["requests"], 128)
        integer(limits["spend_microusd"], 100000000)
        integer(limits["per_request_microusd"], limits["spend_microusd"])
        if "pricing_ceiling" in payload:
            pricing = payload["pricing_ceiling"]
            require(isinstance(pricing, dict) and set(pricing) == {"provider", "model", "input_microusd_per_token",
                    "output_microusd_per_token", "evidence_sha256", "expires_at"}
                    and pricing["provider"] == "openrouter" and pricing["model"] == "openai/gpt-5-mini"
                    and re.fullmatch(r"[0-9a-f]{64}", str(pricing["evidence_sha256"]))
                    and timestamp(pricing["expires_at"]) >= expiry, "native_recovery_pricing_invalid", 400)
            integer(pricing["input_microusd_per_token"], 1000000)
            integer(pricing["output_microusd_per_token"], 1000000)
        verification = payload["verification"]
        require(isinstance(verification, list) and verification and len(verification) <= 20
                and all(isinstance(v, dict) and set(v) == {"name", "argv"}
                        and isinstance(v["argv"], list) and v["argv"]
                        and all(isinstance(a, str) and a and len(a) <= 500 for a in v["argv"])
                        for v in verification), "native_recovery_verification_invalid", 400)
        require(sorted(v["name"] for v in verification) == sorted(scope["required_tests"])
                and bool(scope["acceptance_criteria"]), "native_recovery_verification_contract_conflict")
        request_digest = digest({"payload": payload, "owner": principal})
        if state:
            if state["grant"]["request_digest"] == request_digest:
                return state, {"grant": state["grant"]}, False
            require(payload.get("prior_state_sha256") == digest(original),
                    "native_recovery_existing_grant_requires_reconciliation")
            require(all(e["state"] == "confirmed" for e in state["effects"].values()),
                    "native_recovery_effect_unresolved")
            require(limits["requests"] >= state["requests"] and limits["spend_microusd"] >= state["spend_microusd"],
                    "native_recovery_budget_cannot_reset")
            require(len(state.get("history", [])) < 20, "native_recovery_operation_limit")
        require(not competing, "native_recovery_competing_writer")
        grant = {**copy.deepcopy(payload), "grant_id": "NRG-" + request_digest[:32],
                 "request_digest": request_digest, "issuer": principal, "issued_at": now.isoformat()}
        if state:
            if state.get("execution_anchor"):
                require(all(scope.get(k) == v for k,v in state["execution_anchor"].items()), "native_recovery_execution_anchor_conflict")
            state.setdefault("history", []).append({"grant": state["grant"], "lease": state.pop("lease", {})})
            state.pop("release", None)
            state["grant"] = grant
        else:
            state = {"version": VERSION, "grant": grant, "epoch": 0, "effects": {},
                     "requests": 0, "spend_microusd": 0, "sequence": 0}
            if scope["native_execution_id"]:
                state["execution_anchor"] = {k:scope[k] for k in ("native_execution_id", "worktree_digest", "branch", "starting_main_sha")}
        return state, {"grant": grant}, True
    require(state.get("version") == VERSION, "native_recovery_grant_required")
    grant = state["grant"]
    # Candidate may evolve through exact admitted native stages. Immutable origin
    # remains in grant; each effect also binds the current canonical candidate.
    if operation != "reconcile":
        _scope_compatible(scope, grant["scope"], state.get("execution_anchor"))
        require(not scope["native_execution_id"] or bool(state.get("execution_anchor")), "native_recovery_execution_anchor_missing")
    if operation == "consume":
        require(set(payload) == {"grant_id", "request_id", "incarnation"}, "native_recovery_consume_invalid", 400)
        identity(payload["request_id"]); identity(payload["incarnation"])
        require(payload["grant_id"] == grant["grant_id"], "native_recovery_grant_conflict")
        require(now < timestamp(grant["expires_at"]), "native_recovery_authority_expired")
        lease = state.get("lease")
        if lease:
            require(lease["consume"] == payload and not lease.get("released"), "native_recovery_consume_conflict")
            return state, {"lease": lease, "grant": grant}, False
        require(not competing, "native_recovery_competing_writer")
        state["epoch"] += 1
        lease = {"consume": dict(payload), "grant_id": grant["grant_id"],
                 "incarnation": payload["incarnation"], "epoch": state["epoch"],
                 "claim_id": "HNC-" + digest([mission_id, grant["grant_id"], payload["incarnation"]])[:32],
                 "expires_at": grant["expires_at"], "released": False}
        state["lease"] = lease
        return state, {"lease": lease, "grant": grant}, True
    # Confirmed release replay never clears a subsequent claim.
    if operation == "release" and state.get("release") == payload:
        return state, {"release": state["release"], "lease": state["lease"]}, False
    if operation == "reconcile":
        require(principal.startswith("owner-admin:") and principal != "owner-admin:local-development",
                "owner_admin_session_required", 403)
        require(set(payload) == {"effect_id", "prior_state_sha256", "evidence"}
                and payload["prior_state_sha256"] == digest(original), "native_recovery_reconciliation_conflict")
        effect = state["effects"].get(payload["effect_id"])
        require(effect is not None and effect["state"] != "confirmed", "native_recovery_effect_missing")
        validate_receipt(effect, payload["evidence"])
        effect["reconciliation"] = {"issuer": principal, "previous_receipt": effect.get("receipt"),
                                    "evidence": copy.deepcopy(payload["evidence"]), "at": now.isoformat()}
        effect["state"] = "confirmed"
        effect["receipt"] = {"outcome": "confirmed", "evidence": copy.deepcopy(payload["evidence"])}
        return state, {"effect": effect}, True
    _fence(state, payload.get("proof"), now)
    require(not competing, "native_recovery_competing_writer")
    if operation == "check":
        require(set(payload) == {"proof"}, "native_recovery_payload_invalid", 400)
        return state, {"lease": state["lease"], "grant": grant}, False
    if operation == "begin_admission_dispatch":
        require(principal == "hermes:admission-handler", "native_recovery_operation_invalid", 403)
        require(set(payload) == {"proof", "effect_id", "identity"}, "native_recovery_effect_invalid", 400)
        effect = state["effects"].get(payload["effect_id"])
        require(effect and effect["state"] == "prepared" and effect["kind"] == "canonical"
                and effect["intent"].get("identity") == payload["identity"]
                and effect["intent"].get("candidate") == scope["candidate"]
                and payload["identity"] == {"operation": "admission_dispatch", "mission_id": mission_id,
                    "head_sha": scope["candidate"].get("candidate_revision"),
                    "pr_number": scope["candidate"].get("pr_number")}, "native_recovery_dispatch_intent_conflict")
        require(not effect.get("dispatch_started_at"), "native_recovery_dispatch_requires_reconciliation")
        effect["dispatch_started_at"] = now.isoformat()
        return state, {"effect_id": payload["effect_id"], "may_dispatch": True}, True
    if operation == "reserve":
        require(set(payload) == {"proof", "effect_id", "kind", "intent"}, "native_recovery_effect_invalid", 400)
        effect_id = identity(payload["effect_id"])
        require(payload["kind"] in {"model", "repository", "packaging", "notification", "canonical", "verification"},
                "native_recovery_effect_kind_invalid", 400)
        intent = payload["intent"]
        require(isinstance(intent, dict) and intent and len(json.dumps(intent)) <= 65536,
                "native_recovery_effect_intent_invalid", 400)
        require(intent.get("candidate") == scope["candidate"], "native_recovery_candidate_conflict")
        if payload["kind"] == "notification":
            destination = scope["notifications"].get(intent.get("destination"))
            require(destination and destination["channel"] and intent.get("channel") == destination["channel"]
                    and intent.get("thread_ts") == destination["thread_ts"]
                    and (intent.get("destination") != "original_thread" or bool(destination["thread_ts"]))
                    and intent.get("head_sha") == scope["candidate"].get("candidate_revision"),
                    "native_recovery_notification_destination_conflict")
        # Epoch fences authority, not semantic delivery identity. A regrant
        # cannot make an already confirmed operation executable again.
        exact = digest({"kind": payload["kind"], "intent": intent})
        effects = state["effects"]
        if effect_id in effects:
            require(effects[effect_id]["digest"] == exact, "native_recovery_effect_conflict")
            return state, {"effect": effects[effect_id], "may_execute": False}, False
        require(not any(e["state"] != "confirmed" for e in effects.values()), "native_recovery_effect_unresolved")
        require(len(effects) < MAX_OPERATIONS, "native_recovery_operation_limit")
        cost = 0
        if payload["kind"] == "model":
            cost = grant["limits"]["per_request_microusd"]
            require(state["requests"] < grant["limits"]["requests"]
                    and state["spend_microusd"] + cost <= grant["limits"]["spend_microusd"],
                    "native_recovery_budget_exhausted")
            state["requests"] += 1
            state["spend_microusd"] += cost
        effect = {"effect_id": effect_id, "digest": exact, "kind": payload["kind"],
                  "intent": copy.deepcopy(intent), "state": "prepared", "reserved_at": now.isoformat(),
                  "debit_microusd": cost}
        effects[effect_id] = effect
        return state, {"effect": effect, "may_execute": True}, True
    if operation == "finish":
        require(set(payload) == {"proof", "effect_id", "outcome", "evidence"}, "native_recovery_finish_invalid", 400)
        effect = state["effects"].get(payload["effect_id"])
        require(effect is not None, "native_recovery_effect_missing")
        require(payload["outcome"] in {"confirmed", "ambiguous"} and isinstance(payload["evidence"], dict)
                and payload["evidence"] and len(json.dumps(payload["evidence"])) <= 65536,
                "native_recovery_evidence_invalid", 400)
        receipt = {"outcome": payload["outcome"], "evidence": payload["evidence"]}
        if payload["outcome"] == "confirmed":
            validate_receipt(effect, payload["evidence"])
        if effect.get("receipt"):
            require(effect["receipt"] == receipt, "native_recovery_receipt_conflict")
            return state, {"effect": effect}, False
        effect["receipt"], effect["state"] = receipt, payload["outcome"]
        return state, {"effect": effect}, True
    if operation == "release":
        require(set(payload) == {"proof", "request_id", "native_execution_id", "head_sha"},
                "native_recovery_release_invalid", 400)
        identity(payload["request_id"])
        native = metadata.get("hermes_native_execution") or {}
        require(isinstance(payload["native_execution_id"], str) and payload["native_execution_id"]
                and re.fullmatch(r"[0-9a-f]{40}", str(payload["head_sha"]))
                and native.get("native_execution_id") == payload["native_execution_id"]
                and native.get("execution_status") == "OWNER_DECISION_REQUIRED"
                and native.get("head_sha") == payload["head_sha"]
                and native.get("owner_notification_head") == payload["head_sha"],
                "native_recovery_release_evidence_missing")
        require(all(e["state"] == "confirmed" for e in state["effects"].values()),
                "native_recovery_effect_unresolved")
        notifications = [e for e in state["effects"].values() if e["kind"] == "notification"
                         and e["intent"].get("head_sha") == payload["head_sha"]]
        require({e["intent"].get("destination") for e in notifications} == {"original_thread", "owner_approval"},
                "native_recovery_notifications_incomplete")
        require(native.get("worker_claim_id") == payload["proof"]["claim_id"], "native_recovery_release_claim_conflict")
        state["release"] = copy.deepcopy(payload)
        state["lease"]["released"] = True
        return state, {"release": state["release"], "lease": state["lease"]}, True
    raise RecoveryDenied("native_recovery_operation_invalid", 400)


def transact(mission_id, operation, payload, *, principal, runtime, connect, owner_hold, event):
    """Real PostgreSQL transaction; events and projection either both commit or neither."""
    try:
        identity(mission_id)
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended('charlie-native-allocation',0))")
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (mission_id,))
                cursor.execute("select coalesce(metadata_json,'{}'::jsonb), clock_timestamp() from public.charlie_missions where mission_id=%s for update", (mission_id,))
                row = cursor.fetchone()
                require(row is not None, "not_found", 404)
                metadata, now = dict(row[0]), row[1]
                runtime = dict(runtime)
                if not runtime.get("worker_revision"):
                    current_runtime = (((metadata.get("native_recovery") or {}).get("grant") or {}).get("scope") or {}).get("runtime") or {}
                    if operation == "issue" and isinstance(payload, dict):
                        current_runtime = (payload.get("scope") or {}).get("runtime") or {}
                    runtime["worker_revision"] = current_runtime.get("worker_revision") or (metadata.get("native_runner_blocker") or {}).get("runner_revision", "")
                held, code = owner_hold(mission_id, cursor=cursor)
                require(code == 200 and (held.get("active") is False or operation in {"read", "reconcile"}), "native_recovery_owner_hold_or_unavailable", 423)
                require(not metadata.get("portfolio_classification") and not metadata.get("supersession"),
                        "native_recovery_mission_not_current")
                cursor.execute("select metadata_json from public.charlie_mission_events where mission_id=%s and metadata_json->>'native_recovery_checkpoint'='true' order by (metadata_json->>'sequence')::bigint desc limit 1", (mission_id,))
                checkpoint = cursor.fetchone()
                original = metadata.get("native_recovery") or {}
                require((not original and not checkpoint) or (bool(original) and bool(checkpoint)
                        and checkpoint[0].get("state_sha256") == digest(original)), "native_recovery_checkpoint_conflict")
                cursor.execute("""select exists(select 1 from public.charlie_missions where mission_id<>%s and (
                    metadata_json->'external_supervisor_state'->>'agent_state'='ACTIVE'
                    or metadata_json->'external_supervisor_state'->>'run_state' in ('ACTIVE','RUNNING')
                    or nullif(metadata_json->'hermes_native_execution'->>'worker_claim_id','') is not null
                    or metadata_json->'execution_lease' is not null
                    or (metadata_json->'native_recovery'->'lease' is not null
                        and metadata_json->'native_recovery'->'lease'->>'released'='false')))""", (mission_id,))
                competing = cursor.fetchone()[0]
                retained_claim = (metadata.get("hermes_native_execution") or {}).get("worker_claim_id")
                lease_claim = (original.get("lease") or {}).get("claim_id")
                history = original.get("history") or []
                transfer_claim = ((history[-1].get("lease") or {}).get("claim_id") if history else None)
                exact_owner_transfer = operation == "consume" and retained_claim and retained_claim == transfer_claim and not lease_claim
                competing = competing or bool(metadata.get("execution_lease")) or bool(retained_claim and retained_claim != lease_claim and not exact_owner_transfer)
                state, receipt, changed = transition(mission_id, metadata, operation, payload, principal=principal,
                    now=now, runtime=runtime, competing=competing)
                if changed:
                    state["sequence"] = int(original.get("sequence", 0)) + 1
                    metadata["native_recovery"] = state
                    if operation == "consume" and metadata.get("hermes_native_execution"):
                        native = dict(metadata["hermes_native_execution"])
                        native["worker_claim_id"] = state["lease"]["claim_id"]
                        native["claim_expires_at"] = state["lease"]["expires_at"]
                        native["expires_at"] = state["grant"]["expires_at"]
                        metadata["hermes_native_execution"] = native
                    if operation == "release":
                        native = dict(metadata["hermes_native_execution"])
                        native["worker_claim_id"], native["claim_expires_at"] = "", ""
                        metadata["hermes_native_execution"] = native
                    event(cursor, mission_id, "workflow_updated", "Native recovery " + operation, {
                        "native_recovery_checkpoint": True, "sequence": state["sequence"],
                        "state_sha256": digest(state), "operation": operation,
                        "request_sha256": digest(payload), "principal": principal})
                    cursor.execute("select metadata_json from public.charlie_mission_events where mission_id=%s and metadata_json->>'native_recovery_checkpoint'='true' order by (metadata_json->>'sequence')::bigint desc limit 1", (mission_id,))
                    written = cursor.fetchone()
                    require(written is not None and written[0].get("state_sha256") == digest(state),
                            "native_recovery_checkpoint_insert_failed", 503)
                    cursor.execute("update public.charlie_missions set metadata_json=%s::jsonb, updated_at=now() where mission_id=%s", (json.dumps(metadata), mission_id))
                return {"success": True, "status": "native_recovery_recorded" if changed else "native_recovery_replayed",
                        "mission_id": mission_id, "operation": operation, "request_sha256": digest(payload),
                        "receipt": receipt}, 201 if changed else 200
    except RecoveryDenied as exc:
        return {"success": False, "status": exc.status}, exc.code
    except Exception as exc:
        return {"success": False, "status": "native_recovery_unavailable", "error_type": type(exc).__name__}, 503
