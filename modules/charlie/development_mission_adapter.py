"""Atomic adapter from frozen CORE plans to the existing mission/event store.

This module creates no queue or dispatcher. It writes only ``charlie_missions``
and ``charlie_mission_events`` through one exact-mission, owner-gated contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from modules.charlie.development_coordination import plan_development_dispatch, validate_completion_artifact


VERSION = "charlie_development_mission_adapter_v1"
MAX_AUTHORIZATION_SECONDS = 900
OWNER_AUTHORITIES = {"charl", "charlie"}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _iso(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value or "").strip()


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("development_coordination_time_invalid") from exc


def prepare_development_mission(proposal):
    proposal = dict(proposal or {})
    mission = dict(proposal.get("mission") or proposal)
    required = ("mission_id", "title", "raw_text", "mission_type", "urgency", "expected_files", "stop_condition", "source_base_revision")
    if any(mission.get(key) in (None, "", []) for key in required):
        raise ValueError("development_proposal_incomplete")
    if mission.get("mission_kind") != "software_development":
        raise ValueError("development_software_mission_required")
    architecture = mission.get("agentic_architecture_packet") if isinstance(mission.get("agentic_architecture_packet"), dict) else {}
    if (architecture.get("owning_agent"), architecture.get("coordinating_agent")) != ("CORE", "CHARLIE"):
        raise ValueError("development_architecture_ownership_invalid")
    if architecture.get("ordinary_farm_routing") is not False or architecture.get("governed_actions"):
        raise ValueError("development_operational_routing_forbidden")
    if len(str(mission.get("source_base_revision") or "")) != 40 or any(ch not in "0123456789abcdef" for ch in mission["source_base_revision"]):
        raise ValueError("development_source_base_revision_invalid")
    if not isinstance(mission.get("acknowledgement_timeout_seconds"), int) or not 60 <= mission["acknowledgement_timeout_seconds"] <= 900:
        raise ValueError("development_acknowledgement_timeout_invalid")
    plan = plan_development_dispatch(mission)
    proof = proposal.get("planning_proof") if isinstance(proposal.get("planning_proof"), dict) else {}
    exact = {
        "plan_id": plan["plan_id"], "score_total": plan["score"]["total"],
        "tier": plan["tier"], "agents": plan["agents"],
        "orchestration_generation": plan["orchestration_generation"],
    }
    if proof and any(proof.get(key) != value for key, value in exact.items()):
        raise ValueError("development_frozen_plan_mismatch")
    if len(plan["agents"]) != 1:
        raise ValueError("development_direct_adapter_requires_one_worker")
    material = {"version": VERSION, "mission": mission, "plan": exact}
    digest = _sha(_canonical(material))
    orchestration = dict(plan["orchestration"])
    orchestration.pop("created_at", None)
    return {
        **material, "proposal_digest": digest,
        "transaction_identity": "CORE-DEVELOPMENT-" + digest[:24].upper(),
        "selected_worker": plan["agents"][0], "orchestration": orchestration,
    }


def create_development_authorization(prepared, *, action, owner_principal, secret, issued_at=None, expires_at=None):
    if action not in {"authorize_insert", "release"} or str(owner_principal or "").lower() not in OWNER_AUTHORITIES:
        raise ValueError("development_owner_authority_required")
    secret = str(secret or "")
    if len(secret) < 32:
        raise ValueError("development_owner_authority_not_configured")
    issued = issued_at or datetime.now(timezone.utc)
    expires = expires_at or issued + timedelta(minutes=10)
    if expires <= issued or (expires - issued).total_seconds() > MAX_AUTHORIZATION_SECONDS:
        raise ValueError("development_authorization_window_invalid")
    body = {
        "version": VERSION, "action": action,
        "transaction_identity": prepared["transaction_identity"],
        "proposal_digest": prepared["proposal_digest"],
        "mission_id": prepared["mission"]["mission_id"],
        "plan_id": prepared["plan"]["plan_id"],
        "owner_identity_hash": _sha(str(owner_principal).lower()),
        "issued_at": _iso(issued), "expires_at": _iso(expires),
    }
    signature = hmac.new(secret.encode(), _canonical(body).encode(), hashlib.sha256).hexdigest()
    signed = {**body, "signature": signature}
    return {**signed, "authorization_digest": _sha(_canonical(signed))}


def validate_development_authorization(prepared, authorization, *, action, secret, now=None):
    authorization = dict(authorization or {})
    signature = str(authorization.pop("signature", ""))
    digest = str(authorization.pop("authorization_digest", ""))
    expected = {
        "version": VERSION, "action": action,
        "transaction_identity": prepared["transaction_identity"],
        "proposal_digest": prepared["proposal_digest"],
        "mission_id": prepared["mission"]["mission_id"],
        "plan_id": prepared["plan"]["plan_id"],
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ValueError("development_authorization_binding_invalid")
    secret = str(secret or "")
    expected_signature = hmac.new(secret.encode(), _canonical(authorization).encode(), hashlib.sha256).hexdigest()
    if len(secret) < 32 or not hmac.compare_digest(signature, expected_signature):
        raise ValueError("development_authorization_signature_invalid")
    signed = {**authorization, "signature": signature}
    if not hmac.compare_digest(digest, _sha(_canonical(signed))):
        raise ValueError("development_authorization_digest_invalid")
    observed = now or datetime.now(timezone.utc)
    issued, expires = _parse_time(authorization.get("issued_at")), _parse_time(authorization.get("expires_at"))
    if issued > observed + timedelta(seconds=30) or expires <= observed or expires > issued + timedelta(seconds=MAX_AUTHORIZATION_SECONDS):
        raise ValueError("development_authorization_stale")
    return {**signed, "authorization_digest": digest}


def create_development_dispatch_grant(prepared, *, worker_id, worker_role, dispatch_id, secret, issued_at=None, expires_at=None):
    if worker_role != prepared["selected_worker"] or not worker_id or not dispatch_id:
        raise ValueError("development_selected_worker_required")
    issued = issued_at or datetime.now(timezone.utc)
    expires = expires_at or issued + timedelta(minutes=15)
    body = {"version": VERSION, "proposal_digest": prepared["proposal_digest"],
            "mission_id": prepared["mission"]["mission_id"], "plan_id": prepared["plan"]["plan_id"],
            "worker_id": worker_id, "worker_role": worker_role, "dispatch_id": dispatch_id,
            "issued_at": _iso(issued), "expires_at": _iso(expires)}
    secret = str(secret or "")
    if len(secret) < 32 or expires <= issued or (expires - issued).total_seconds() > MAX_AUTHORIZATION_SECONDS:
        raise ValueError("development_dispatch_authority_invalid")
    signature = hmac.new(secret.encode(), _canonical(body).encode(), hashlib.sha256).hexdigest()
    signed = {**body, "signature": signature}
    return {**signed, "dispatch_grant_digest": _sha(_canonical(signed))}


def validate_development_dispatch_grant(prepared, grant, *, secret, now=None, allow_expired=False):
    grant = dict(grant or {})
    signature, digest = str(grant.pop("signature", "")), str(grant.pop("dispatch_grant_digest", ""))
    expected = {"version": VERSION, "proposal_digest": prepared["proposal_digest"],
                "mission_id": prepared["mission"]["mission_id"], "plan_id": prepared["plan"]["plan_id"],
                "worker_role": prepared["selected_worker"]}
    if any(grant.get(key) != value for key, value in expected.items()) or not grant.get("worker_id") or not grant.get("dispatch_id"):
        raise ValueError("development_dispatch_binding_invalid")
    secret = str(secret or "")
    expected_signature = hmac.new(secret.encode(), _canonical(grant).encode(), hashlib.sha256).hexdigest()
    signed = {**grant, "signature": signature}
    if len(secret) < 32 or not hmac.compare_digest(signature, expected_signature) or not hmac.compare_digest(digest, _sha(_canonical(signed))):
        raise ValueError("development_dispatch_signature_invalid")
    observed, issued, expires = now or datetime.now(timezone.utc), _parse_time(grant["issued_at"]), _parse_time(grant["expires_at"])
    if issued > observed + timedelta(seconds=30) or (expires <= observed and not allow_expired) or expires > issued + timedelta(seconds=MAX_AUTHORIZATION_SECONDS):
        raise ValueError("development_dispatch_grant_stale")
    return {**signed, "dispatch_grant_digest": digest}


def _event_id(prepared, state, identity=""):
    return "CORE-DEVELOPMENT-EVENT-" + _sha("|".join((prepared["proposal_digest"], state, identity)))[:24].upper()


def _insert_event(cursor, prepared, state, evidence, identity=""):
    cursor.execute(
        """insert into public.charlie_mission_events
           (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
           values (%s,%s,'mission_updated',%s,'charlie_core_adapter',%s::jsonb,now())
           on conflict (event_id) do nothing returning event_id""",
        (_event_id(prepared, state, identity), prepared["mission"]["mission_id"],
         f"CORE development coordination: {state}.", _canonical({"adapter_version": VERSION, "state": state, **evidence})),
    )
    return bool(cursor.fetchone())


def _connect(database_url, connect_factory=None):
    if connect_factory:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=5)


def _url(database_url):
    return str(database_url if database_url is not None else os.getenv("CHARLIE_DEVELOPMENT_MISSION_WRITER_DATABASE_URL", "")).strip()


def _retired_direct_authorize_and_insert(proposal, authorization, *, database_url=None, connect_factory=None, secret=None):
    raise RuntimeError("secure_development_mission_store_adapter_required")
    prepared = prepare_development_mission(proposal)
    validated = validate_development_authorization(prepared, authorization, action="authorize_insert",
                                                   secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_MISSION_AUTH_SECRET", ""))
    url = _url(database_url)
    if not url and connect_factory is None:
        return {"success": False, "status": "not_configured"}, 503
    mission = prepared["mission"]
    coordination = {
        "version": VERSION, "state": "owner_authorized", "proposal_digest": prepared["proposal_digest"],
        "transaction_identity": prepared["transaction_identity"], "plan": prepared["plan"],
        "selected_worker": prepared["selected_worker"], "scope": mission.get("expected_files"),
        "declared_artifacts": mission.get("expected_files"), "parent_lineage": mission.get("parent_lineage"),
        "authorization_digest": validated["authorization_digest"], "authorization": validated,
        "release_authorization_digest": None, "release_authorization": None,
    }
    metadata = {"development_coordination": coordination, "orchestration": prepared["orchestration"],
                "agent_workflow": [{"agent": prepared["selected_worker"], "status": "pending"}],
                "agentic_architecture_packet": mission["agentic_architecture_packet"],
                "intake": {"adaptive_orchestration_required": True, "mission_kind": "software_development"}}
    try:
        with _connect(url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtext(%s))", (mission["mission_id"],))
                cursor.execute("select status,metadata_json from public.charlie_missions where mission_id=%s for update", (mission["mission_id"],))
                row = cursor.fetchone()
                if row:
                    existing = (row[1] or {}).get("development_coordination") or {}
                    if existing.get("proposal_digest") == prepared["proposal_digest"] and existing.get("authorization_digest") == validated["authorization_digest"]:
                        return {"success": True, "status": "development_mission_replayed", "mission_id": mission["mission_id"], "rows_changed": 0}, 200
                    raise ValueError("development_mission_identity_collision")
                cursor.execute(
                    """insert into public.charlie_missions
                       (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json,created_at,updated_at)
                       values (%s,'paused','charlie_core_governed',%s,%s,%s,%s,'LEVEL 3',%s::jsonb,now(),now())""",
                    (mission["mission_id"], mission["raw_text"], mission["title"], mission["urgency"], mission["mission_type"], _canonical(metadata)),
                )
                _insert_event(cursor, prepared, "proposed", {"proposal_digest": prepared["proposal_digest"]})
                _insert_event(cursor, prepared, "owner_authorized", {"authorization_digest": validated["authorization_digest"]})
    except Exception as exc:
        return {"success": False, "status": "development_mission_insert_rejected", "error_type": exc.__class__.__name__, "error": str(exc)[:160]}, 409
    return {"success": True, "status": "development_mission_authorized", "mission_id": mission["mission_id"], "mission_status": "paused", "state": "owner_authorized", "rows_changed": 1}, 201


def _load_locked(cursor, prepared):
    cursor.execute("select status,metadata_json from public.charlie_missions where mission_id=%s for update", (prepared["mission"]["mission_id"],))
    row = cursor.fetchone()
    if not row:
        raise ValueError("development_mission_not_found")
    metadata = dict(row[1] or {})
    coordination = dict(metadata.get("development_coordination") or {})
    if coordination.get("proposal_digest") != prepared["proposal_digest"] or coordination.get("plan") != prepared["plan"]:
        raise ValueError("development_persisted_contract_mismatch")
    return row[0], metadata, coordination


def _retired_direct_release(proposal, authorization, *, database_url=None, connect_factory=None, secret=None):
    raise RuntimeError("secure_development_mission_store_adapter_required")
    prepared = prepare_development_mission(proposal)
    validated = validate_development_authorization(prepared, authorization, action="release",
                                                   secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_MISSION_AUTH_SECRET", ""))
    try:
        with _connect(_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtext(%s))", (prepared["mission"]["mission_id"],))
                status, metadata, coordination = _load_locked(cursor, prepared)
                if coordination.get("state") == "released" and coordination.get("release_authorization_digest") == validated["authorization_digest"]:
                    return {"success": True, "status": "development_release_replayed", "rows_changed": 0, "pickup_proven": False}, 200
                if status != "paused" or coordination.get("state") != "owner_authorized":
                    raise ValueError("development_release_state_invalid")
                coordination.update({"state": "released", "release_authorization_digest": validated["authorization_digest"],
                                     "release_authorization": validated})
                metadata["development_coordination"] = coordination
                cursor.execute("update public.charlie_missions set metadata_json=%s::jsonb,updated_at=now() where mission_id=%s", (_canonical(metadata), prepared["mission"]["mission_id"]))
                _insert_event(cursor, prepared, "released", {"authorization_digest": validated["authorization_digest"]})
    except Exception as exc:
        return {"success": False, "status": "development_release_rejected", "error_type": exc.__class__.__name__, "error": str(exc)[:160]}, 409
    return {"success": True, "status": "development_mission_released", "mission_status": "paused", "state": "released", "pickup_proven": False, "rows_changed": 1}, 200


def _retired_direct_dispatch(proposal, grant, *, database_url=None, connect_factory=None, secret=None, now=None):
    raise RuntimeError("secure_development_mission_store_adapter_required")
    prepared = prepare_development_mission(proposal)
    validated = validate_development_dispatch_grant(
        prepared, grant, secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_DISPATCH_SECRET", ""), now=now,
    )
    try:
        with _connect(_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtext(%s))", (prepared["mission"]["mission_id"],))
                status, metadata, coordination = _load_locked(cursor, prepared)
                if status != "paused" or coordination.get("state") != "released":
                    raise ValueError("development_dispatch_state_invalid")
                existing = coordination.get("dispatch_grant") or {}
                if existing:
                    if existing.get("dispatch_grant_digest") == validated["dispatch_grant_digest"]:
                        return {"success": True, "status": "development_dispatch_replayed", "rows_changed": 0}, 200
                    raise ValueError("development_dispatch_conflict")
                coordination["dispatch_grant"] = validated
                metadata["development_coordination"] = coordination
                cursor.execute("update public.charlie_missions set metadata_json=%s::jsonb,updated_at=now() where mission_id=%s", (_canonical(metadata), prepared["mission"]["mission_id"]))
                if not _insert_event(cursor, prepared, "released", {"dispatch_grant": validated}, validated["dispatch_id"]):
                    raise ValueError("development_dispatch_event_incomplete")
    except Exception as exc:
        return {"success": False, "status": "development_dispatch_rejected", "error_type": exc.__class__.__name__, "error": str(exc)[:160]}, 409
    return {"success": True, "status": "development_dispatch_recorded", "state": "released", "pickup_proven": False, "dispatch_id": validated["dispatch_id"], "rows_changed": 1}, 201


def _retired_direct_state(proposal, event, *, database_url=None, connect_factory=None, now=None, dispatch_secret=None):
    raise RuntimeError("secure_development_mission_store_adapter_required")
    prepared, event = prepare_development_mission(proposal), dict(event or {})
    kind, event_identity = str(event.get("type") or ""), str(event.get("event_id") or "")
    requested_kind = kind
    if not event_identity:
        raise ValueError("development_event_identity_required")
    observed = now or datetime.now(timezone.utc)
    try:
        with _connect(_url(database_url), connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtext(%s))", (prepared["mission"]["mission_id"],))
                status, metadata, coordination = _load_locked(cursor, prepared)
                raw_event_digest = _sha(_canonical(event))
                cursor.execute("select metadata_json from public.charlie_mission_events where event_id=%s", (_event_id(prepared, kind, event_identity),))
                replay_row = cursor.fetchone()
                if replay_row:
                    if (replay_row[0] or {}).get("raw_event_digest") != raw_event_digest:
                        raise ValueError("development_event_identity_collision")
                    return {"success": True, "status": "development_event_replayed", "state": coordination["state"], "rows_changed": 0}, 200
                state, evidence, next_status = coordination.get("state"), {}, status
                if kind in {"started", "waiting_for_evidence", "completed"}:
                    continued_grant = validate_development_dispatch_grant(
                        prepared, event.get("dispatch_grant"),
                        secret=dispatch_secret if dispatch_secret is not None else os.getenv("CHARLIE_DEVELOPMENT_DISPATCH_SECRET", ""), now=observed,
                    )
                    if continued_grant.get("dispatch_grant_digest") != (coordination.get("dispatch_grant") or {}).get("dispatch_grant_digest"):
                        raise ValueError("development_dispatch_binding_invalid")
                if kind == "acknowledged" and state == "released":
                    grant = validate_development_dispatch_grant(
                        prepared, event.get("dispatch_grant"),
                        secret=dispatch_secret if dispatch_secret is not None else os.getenv("CHARLIE_DEVELOPMENT_DISPATCH_SECRET", ""), now=observed,
                    )
                    persisted_grant = coordination.get("dispatch_grant") or {}
                    if (grant.get("dispatch_grant_digest") != persisted_grant.get("dispatch_grant_digest")
                            or event.get("worker_role") != grant.get("worker_role")
                            or event.get("worker_id") != grant.get("worker_id")
                            or event.get("dispatch_id") != grant.get("dispatch_id")):
                        raise ValueError("development_selected_worker_required")
                    acknowledged_at = _parse_time(event.get("acknowledged_at"))
                    if abs((observed - acknowledged_at).total_seconds()) > 300:
                        raise ValueError("development_acknowledgement_stale")
                    evidence = {key: event[key] for key in ("worker_id", "worker_role", "dispatch_id", "acknowledged_at")}
                    coordination["receipt"] = evidence
                elif kind == "started" and state == "acknowledged":
                    receipt = coordination.get("receipt") or {}
                    if (event.get("dispatch_id") != receipt.get("dispatch_id")
                            or event.get("worker_id") != receipt.get("worker_id")
                            or event.get("worker_role") != receipt.get("worker_role")
                            or not event.get("heartbeat_at")):
                        raise ValueError("development_start_receipt_invalid")
                    if abs((observed - _parse_time(event["heartbeat_at"])).total_seconds()) > 300:
                        raise ValueError("development_heartbeat_stale")
                    evidence, next_status = {"dispatch_id": event["dispatch_id"], "heartbeat_at": event["heartbeat_at"]}, "in_progress"
                elif kind == "waiting_for_evidence" and state in {"started", "waiting_for_evidence"}:
                    receipt = coordination.get("receipt") or {}
                    if (event.get("dispatch_id") != receipt.get("dispatch_id")
                            or event.get("worker_id") != receipt.get("worker_id")
                            or event.get("worker_role") != receipt.get("worker_role")
                            or not event.get("heartbeat_at")
                            or abs((observed - _parse_time(event["heartbeat_at"])).total_seconds()) > 300):
                        raise ValueError("development_heartbeat_stale")
                    evidence = {"heartbeat_at": event["heartbeat_at"], "progress": str(event.get("progress") or "")}
                elif kind == "completed" and state in {"started", "waiting_for_evidence"}:
                    receipt = coordination.get("receipt") or {}
                    if (event.get("dispatch_id") != receipt.get("dispatch_id")
                            or event.get("worker_id") != receipt.get("worker_id")
                            or event.get("worker_role") != receipt.get("worker_role")):
                        raise ValueError("development_completion_worker_mismatch")
                    artifact = dict(event.get("artifact") or {})
                    outcome = str(artifact.get("business_outcome") or "").strip()
                    rows = artifact.get("artifact_evidence") if isinstance(artifact.get("artifact_evidence"), list) else []
                    paths = [row.get("path") for row in rows if isinstance(row, dict)]
                    if (not outcome or set(paths) != set(prepared["mission"]["expected_files"])
                            or any(not row.get("commit_sha") or len(str(row.get("commit_sha"))) != 40
                                   or not row.get("result_identity") for row in rows if isinstance(row, dict))):
                        raise ValueError("development_declared_artifact_required")
                    if "next_dependency" not in artifact:
                        raise ValueError("development_next_dependency_required")
                    evidence, next_status, kind = {"artifact": artifact}, "pr_ready", "completed_with_artifact"
                elif kind == "contain_missing_ack" and state in {"released", "contained"}:
                    evidence, next_status, kind = {"reason": "acknowledgement_timeout", "retry": False}, "blocked", "contained"
                elif kind == "contained" and state in {"released", "acknowledged", "started", "waiting_for_evidence"}:
                    evidence, next_status = {"reason": str(event.get("reason") or "contained"), "retry": False}, "blocked"
                else:
                    raise ValueError("development_state_transition_invalid")
                evidence["raw_event_digest"] = raw_event_digest
                coordination["state"] = kind
                coordination["last_event_id"] = event_identity
                metadata["development_coordination"] = coordination
                cursor.execute("update public.charlie_missions set status=%s,metadata_json=%s::jsonb,updated_at=now() where mission_id=%s", (next_status, _canonical(metadata), prepared["mission"]["mission_id"]))
                inserted = _insert_event(cursor, prepared, requested_kind, {"resulting_state": kind, **evidence}, event_identity)
                if not inserted:
                    raise ValueError("development_event_incomplete")
    except Exception as exc:
        return {"success": False, "status": "development_state_rejected", "error_type": exc.__class__.__name__, "error": str(exc)[:160]}, 409
    return {"success": True, "status": "development_state_recorded", "state": kind, "mission_status": next_status, "rows_changed": 1}, 200
