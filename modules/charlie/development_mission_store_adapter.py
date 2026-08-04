"""Least-privilege persistence adapter for governed CORE development missions."""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from modules.charlie.development_mission_adapter import (
    VERSION,
    _canonical,
    _event_id,
    _iso,
    _sha,
    create_development_authorization,
    create_development_dispatch_grant,
    prepare_development_mission,
    validate_development_authorization,
    validate_development_dispatch_grant,
)


def _connect(url, connect_factory=None):
    if connect_factory:
        return connect_factory(url)
    import psycopg
    return psycopg.connect(url, connect_timeout=5)


def _url(explicit, env_name):
    return str(explicit if explicit is not None else os.getenv(env_name, "")).strip()


def _event(prepared, state, metadata, identity=""):
    metadata = {"adapter_version": VERSION, "state": state, **metadata}
    metadata_canonical = _canonical(metadata)
    digest = _sha(metadata_canonical)
    return {"event_id": _event_id(prepared, state, identity), "event_digest": digest,
            "notes": f"CORE development coordination: {state}.",
            "metadata_canonical": metadata_canonical,
            "metadata": {**metadata, "event_digest": digest}}


def _command(prepared, operation, **values):
    command_body = {"version": VERSION, "operation": operation,
               "mission_id": prepared["mission"]["mission_id"],
               "proposal_digest": prepared["proposal_digest"],
               "proposal_canonical": _canonical({"version": VERSION, "mission": prepared["mission"], "plan": prepared["plan"]}),
               "plan_id": prepared["plan"]["plan_id"], **values}
    command_canonical = _canonical(command_body)
    command = {**command_body, "command_canonical": command_canonical,
               "command_digest": _sha(command_canonical)}
    return command


def _apply(command, *, database_url=None, connect_factory=None):
    url = _url(database_url, "CHARLIE_DEVELOPMENT_MISSION_WRITER_DATABASE_URL")
    if not url and connect_factory is None:
        return {"success": False, "status": "not_configured"}, 503
    try:
        for attempt in range(2):
            try:
                with _connect(url, connect_factory) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("set local transaction isolation level serializable")
                        cursor.execute("select public.apply_charlie_development_command(%s::jsonb)", (_canonical(command),))
                        result = dict(cursor.fetchone()[0] or {})
                break
            except Exception as exc:
                if getattr(exc, "sqlstate", "") == "40001" and attempt == 0:
                    continue
                raise
    except Exception as exc:
        return {"success": False, "status": "development_command_rejected",
                "error_type": exc.__class__.__name__, "error_code": getattr(exc, "sqlstate", "") or "",
                "error": str(exc).splitlines()[0][:180]}, 409
    return result, 200 if result.get("replayed") else 201


def _verify_repository_lineage(mission, artifact):
    base = str(artifact.get("base_revision") or "")
    candidate = str(artifact.get("candidate_revision") or "")
    expected = sorted(str(path) for path in mission.get("expected_files") or [])
    changed = sorted(str(path) for path in artifact.get("changed_files") or [])
    if base != mission.get("source_base_revision") or len(candidate) != 40 or any(ch not in "0123456789abcdef" for ch in candidate) or changed != expected:
        raise ValueError("development_repository_lineage_invalid")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", base, candidate], cwd=root, capture_output=True, text=True)
    diff = subprocess.run(["git", "diff", "--name-only", f"{base}..{candidate}"], cwd=root, capture_output=True, text=True)
    observed = sorted(line.strip().replace("\\", "/") for line in diff.stdout.splitlines() if line.strip())
    if ancestor.returncode != 0 or diff.returncode != 0 or observed != expected:
        raise ValueError("development_repository_lineage_unproven")
    proof = {"verified_by": "charlie_repo_gate", "mission_id": mission["mission_id"],
             "proposal_digest": prepare_development_mission({"mission": mission})["proposal_digest"], "base_revision": base,
             "candidate_revision": candidate, "changed_files": observed}
    return {**proof, "proof_digest": _sha(_canonical(proof))}


def record_development_authorization(prepared, authorization, *, action, database_url=None,
                                     connect_factory=None, secret=None, now=None):
    validated = validate_development_authorization(
        prepared, authorization, action=action,
        secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_MISSION_AUTH_SECRET", ""), now=now,
    )
    url = _url(database_url, "CHARLIE_DEVELOPMENT_MISSION_AUTHORIZER_DATABASE_URL")
    envelope = {key: value for key, value in validated.items() if key != "authorization_digest"}
    try:
        with _connect(url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select public.append_charlie_development_authorization(%s::jsonb,%s)",
                               (_canonical(envelope), validated["authorization_digest"]))
                recorded = cursor.fetchone()[0]
    except Exception as exc:
        return {"success": False, "status": "development_authorization_record_rejected",
                "error_type": exc.__class__.__name__, "error_code": getattr(exc, "sqlstate", "") or ""}, 409
    return {"success": True, "status": "development_authorization_recorded", "authorization_digest": recorded}, 201


def record_development_dispatch_authorization(prepared, grant, *, database_url=None,
                                              connect_factory=None, secret=None, now=None):
    validated = validate_development_dispatch_grant(
        prepared, grant,
        secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_DISPATCH_SECRET", ""), now=now,
    )
    url = _url(database_url, "CHARLIE_DEVELOPMENT_DISPATCH_AUTHORIZER_DATABASE_URL")
    envelope = {key: value for key, value in validated.items() if key != "dispatch_grant_digest"}
    try:
        with _connect(url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select public.append_charlie_development_dispatch_grant(%s::jsonb,%s)",
                               (_canonical(envelope), validated["dispatch_grant_digest"]))
                recorded = cursor.fetchone()[0]
    except Exception as exc:
        return {"success": False, "status": "development_dispatch_authorization_rejected",
                "error_type": exc.__class__.__name__, "error_code": getattr(exc, "sqlstate", "") or ""}, 409
    return {"success": True, "status": "development_dispatch_authorization_recorded",
            "dispatch_grant_digest": recorded}, 201


def record_development_lineage_authorization(prepared, proof, *, database_url=None, connect_factory=None):
    url = _url(database_url, "CHARLIE_DEVELOPMENT_LINEAGE_AUTHORIZER_DATABASE_URL")
    try:
        with _connect(url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select public.append_charlie_development_lineage_grant(%s,%s,%s::jsonb)",
                               (prepared["mission"]["mission_id"], prepared["proposal_digest"], _canonical(proof)))
                recorded = cursor.fetchone()[0]
    except Exception as exc:
        return {"success": False, "status": "development_lineage_authorization_rejected",
                "error_type": exc.__class__.__name__, "error_code": getattr(exc, "sqlstate", "") or ""}, 409
    return {"success": True, "status": "development_lineage_authorization_recorded", "proof_digest": recorded}, 201


def authorize_and_insert_development_mission(proposal, authorization, *, database_url=None, connect_factory=None, secret=None):
    prepared = prepare_development_mission(proposal)
    validated = validate_development_authorization(prepared, authorization, action="authorize_insert",
                                                   secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_MISSION_AUTH_SECRET", ""))
    mission = prepared["mission"]
    coordination = {"version": VERSION, "state": "owner_authorized",
                    "proposal_digest": prepared["proposal_digest"], "transaction_identity": prepared["transaction_identity"],
                    "plan": prepared["plan"], "selected_worker": prepared["selected_worker"],
                    "scope": mission["expected_files"], "declared_artifacts": mission["expected_files"],
                    "acknowledgement_timeout_seconds": mission["acknowledgement_timeout_seconds"],
                    "parent_lineage": mission.get("parent_lineage"), "authorization_digest": validated["authorization_digest"],
                    "release_authorization_digest": None, "dispatch_grant": None}
    metadata = {"development_coordination": coordination, "orchestration": prepared["orchestration"],
                "agent_workflow": [{"agent": prepared["selected_worker"], "status": "pending"}],
                "agentic_architecture_packet": mission["agentic_architecture_packet"],
                "intake": {"adaptive_orchestration_required": True, "mission_kind": "software_development"}}
    events = [_event(prepared, "proposed", {"proposal_digest": prepared["proposal_digest"]}),
              _event(prepared, "owner_authorized", {"authorization_digest": validated["authorization_digest"]})]
    return _apply(_command(prepared, "authorize_insert", mission=mission, metadata=metadata,
                           authorization_digest=validated["authorization_digest"], events=events),
                  database_url=database_url, connect_factory=connect_factory)


def _current(proposal, *, database_url=None, connect_factory=None):
    prepared = prepare_development_mission(proposal)
    url = _url(database_url, "CHARLIE_DEVELOPMENT_MISSION_WRITER_DATABASE_URL")
    with _connect(url, connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select public.read_charlie_development_mission(%s)", (prepared["mission"]["mission_id"],))
            row = cursor.fetchone()
    loaded = row[0] if row else None
    if not loaded:
        raise ValueError("development_mission_not_found")
    coordination = dict((loaded.get("metadata") or {}).get("development_coordination") or {})
    if coordination.get("proposal_digest") != prepared["proposal_digest"]:
        raise ValueError("development_persisted_contract_mismatch")
    return prepared, loaded.get("status"), dict(loaded.get("metadata") or {}), coordination


def release_development_mission(proposal, authorization, *, database_url=None, connect_factory=None, secret=None):
    prepared, status, metadata, coordination = _current(proposal, database_url=database_url, connect_factory=connect_factory)
    validated = validate_development_authorization(prepared, authorization, action="release",
                                                   secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_MISSION_AUTH_SECRET", ""))
    coordination = {**coordination, "state": "released", "release_authorization_digest": validated["authorization_digest"]}
    return _apply(_command(prepared, "release", expected_state="owner_authorized", new_status="paused",
                           new_coordination=coordination, authorization_digest=validated["authorization_digest"],
                           events=[_event(prepared, "released", {"authorization_digest": validated["authorization_digest"]})]),
                  database_url=database_url, connect_factory=connect_factory)


def record_development_dispatch(proposal, grant, *, database_url=None, connect_factory=None, secret=None, now=None):
    prepared, _status, _metadata, coordination = _current(proposal, database_url=database_url, connect_factory=connect_factory)
    validated = validate_development_dispatch_grant(prepared, grant,
                                                    secret=secret if secret is not None else os.getenv("CHARLIE_DEVELOPMENT_DISPATCH_SECRET", ""), now=now)
    return _apply(_command(prepared, "dispatch", expected_state="released", new_status="paused",
                           dispatch_grant=validated,
                           events=[_event(prepared, "dispatch_granted", {"dispatch_grant_digest": validated["dispatch_grant_digest"]}, validated["dispatch_id"])]),
                  database_url=database_url, connect_factory=connect_factory)


def record_development_state(proposal, event, *, database_url=None, connect_factory=None, now=None, dispatch_secret=None,
                             lineage_verifier=None, lineage_authorizer_database_url=None):
    prepared, status, _metadata, coordination = _current(proposal, database_url=database_url, connect_factory=connect_factory)
    event, observed = dict(event or {}), now or datetime.now(timezone.utc)
    kind, identity = str(event.get("type") or ""), str(event.get("event_id") or "")
    if not identity:
        raise ValueError("development_event_identity_required")
    raw_event_digest = _sha(_canonical(event))
    event_id = _event_id(prepared, kind, identity)
    url = _url(database_url, "CHARLIE_DEVELOPMENT_MISSION_WRITER_DATABASE_URL")
    with _connect(url, connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select public.read_charlie_development_event(%s)", (event_id,))
            replay_row = cursor.fetchone()
    replay_metadata = replay_row[0] if replay_row else None
    if replay_metadata:
        if replay_metadata.get("raw_event_digest") != raw_event_digest:
            raise ValueError("development_event_identity_collision")
        return {"success": True, "status": "development_event_replayed",
                "state": coordination.get("state"), "rows_changed": 0}, 200
    grant = validate_development_dispatch_grant(prepared, event.get("dispatch_grant"),
                                                secret=dispatch_secret if dispatch_secret is not None else os.getenv("CHARLIE_DEVELOPMENT_DISPATCH_SECRET", ""),
                                                now=observed, allow_expired=(coordination.get("state") != "released" or kind == "contain_missing_ack"))
    persisted_grant = coordination.get("dispatch_grant") or {}
    if grant.get("dispatch_grant_digest") != persisted_grant.get("dispatch_grant_digest"):
        raise ValueError("development_dispatch_binding_invalid")
    worker = {key: event.get(key) for key in ("worker_id", "worker_role", "dispatch_id")}
    if worker != {key: grant.get(key) for key in worker}:
        raise ValueError("development_selected_worker_required")
    expected, new_state, new_status, evidence = coordination.get("state"), "", status, {}
    if kind == "acknowledged" and expected == "released":
        if abs((observed - datetime.fromisoformat(event["acknowledged_at"].replace("Z", "+00:00"))).total_seconds()) > 300:
            raise ValueError("development_acknowledgement_stale")
        new_state, evidence = "acknowledged", {**worker, "acknowledged_at": event["acknowledged_at"]}
        coordination["receipt"] = evidence
    elif kind == "started" and expected == "acknowledged":
        if abs((observed - datetime.fromisoformat(event["heartbeat_at"].replace("Z", "+00:00"))).total_seconds()) > 300:
            raise ValueError("development_heartbeat_stale")
        new_state, new_status, evidence = "started", "in_progress", {**worker, "heartbeat_at": event["heartbeat_at"]}
    elif kind == "waiting_for_evidence" and expected in {"started", "waiting_for_evidence"}:
        if abs((observed - datetime.fromisoformat(event["heartbeat_at"].replace("Z", "+00:00"))).total_seconds()) > 300:
            raise ValueError("development_heartbeat_stale")
        new_state, evidence = "waiting_for_evidence", {**worker, "heartbeat_at": event["heartbeat_at"], "progress": event.get("progress", "")}
    elif kind == "completed" and expected in {"started", "waiting_for_evidence"}:
        artifact = dict(event.get("artifact") or {})
        rows = artifact.get("artifact_evidence") if isinstance(artifact.get("artifact_evidence"), list) else []
        if (not artifact.get("business_outcome") or {row.get("path") for row in rows if isinstance(row, dict)} != set(prepared["mission"]["expected_files"])
                or any(not isinstance(row, dict) or len(str(row.get("commit_sha") or "")) != 40 or not row.get("result_identity") for row in rows)
                or "next_dependency" not in artifact):
            raise ValueError("development_declared_artifact_required")
        lineage = (lineage_verifier or _verify_repository_lineage)(prepared["mission"], artifact)
        if not isinstance(lineage, dict) or lineage.get("verified_by") != "charlie_repo_gate" or len(str(lineage.get("proof_digest") or "")) != 64:
            raise ValueError("development_repository_lineage_unproven")
        recorded, recorded_code = record_development_lineage_authorization(
            prepared, lineage, database_url=lineage_authorizer_database_url, connect_factory=connect_factory,
        )
        if recorded_code >= 400:
            return recorded, recorded_code
        artifact["repository_lineage"] = lineage
        new_state, new_status, evidence = "completed_with_artifact", "pr_ready", {**worker, "artifact": artifact}
    elif kind == "contain_missing_ack" and expected in {"released", "contained"}:
        deadline = datetime.fromisoformat(grant["issued_at"].replace("Z", "+00:00")) + timedelta(
            seconds=int(coordination["acknowledgement_timeout_seconds"])
        )
        if observed < deadline:
            raise ValueError("development_acknowledgement_timeout_not_elapsed")
        new_state, new_status, evidence = "contained", "blocked", {
            "reason": "acknowledgement_timeout", "retry": False,
            "observed_at": observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "acknowledgement_deadline": deadline.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            **worker,
        }
    else:
        raise ValueError("development_state_transition_invalid")
    new_coordination = {**coordination, "state": new_state, "last_event_id": identity}
    event_row = _event(prepared, kind, {"resulting_state": new_state, "raw_event_digest": raw_event_digest, **evidence}, identity)
    return _apply(_command(prepared, "event", event_kind=kind, event_identity=identity,
                           expected_state=expected, new_status=new_status, new_coordination=new_coordination,
                           dispatch_grant_digest=grant["dispatch_grant_digest"], events=[event_row]),
                  database_url=database_url, connect_factory=connect_factory)
