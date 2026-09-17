"""Non-actuating append-only resolution for an explicitly contained parent job."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

CONTRACT_VERSION = "rootline_parent_job_terminal_resolution.v1"


def build_contained_parent_cancellation(*, parent, controller, authorization, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    parent = dict(parent or {})
    job = dict(parent.get("job") or {})
    projection = dict(parent.get("projection") or {})
    authorization = dict(authorization or {})
    if (job.get("zone_id") != "B12345"
            or projection.get("status") != "segment_contained"
            or authorization.get("mission_id") != "RMQ-20260813-04"
            or authorization.get("decision") != "cancel_unverified_remainder"
            or not str(authorization.get("owner_principal") or "")
            or authorization.get("job_id") != job.get("job_id")
            or authorization.get("job_sha256") != job.get("job_sha256")):
        raise ValueError("contained_parent_cancellation_authority_invalid")
    retrieved = _time((controller or {}).get("retrieved_at")
                      or (controller or {}).get("trusted_receipt_at"))
    channels = list((controller or {}).get("channels") or ())
    if (retrieved is None or now < retrieved or now-retrieved > timedelta(minutes=5)
            or (controller or {}).get("online") is not True
            or len(channels) != 4
            or any(row.get("output_state") != "OFF" for row in channels)
            or not str((controller or {}).get("response_digest") or "")):
        raise ValueError("current_provider_off_evidence_invalid")
    material = {"contract_version": CONTRACT_VERSION, "resolution": "Cancelled",
        "terminal": True, "mission_id": "RMQ-20260813-04",
        "job_id": job["job_id"], "job_sha256": job["job_sha256"],
        "zone_id": "B12345", "current_segment": projection.get("current_segment"),
        "expected_segment_count": job.get("expected_segment_count"),
        "cumulative_verified_runtime_seconds": int(
            projection.get("cumulative_verified_runtime_seconds") or 0),
        "cancelled_unverified_remaining_seconds": int(parent.get("remaining_seconds") or 0),
        "remaining_seconds": 0, "provider_off_verified": True,
        "provider_off_evidence_digest": str(controller["response_digest"]),
        "provider_off_observed_at": retrieved.isoformat(),
        "fabricated_runtime_seconds": 0, "water_credit_created": False,
        "next_attempt_requires_fresh_execution_identity": True,
        "reason": "owner_authorized_terminal_cancellation_of_unverified_contained_remainder"}
    digest = _digest(material)
    return {**material, "resolution_sha256": digest,
        "execution_id": _cancellation_identity(job["job_id"], job["job_sha256"]),
        "owner_principal": str(authorization["owner_principal"]),
        "hardware_commands": 0, "provider_control_calls": 0}


def record_contained_parent_cancellation(*, parent, controller, authorization,
                                         store, now=None):
    packet = build_contained_parent_cancellation(parent=parent, controller=controller,
        authorization=authorization, now=now)
    result = store("record_job_resolution", packet)
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("contained_parent_cancellation_persistence_unproven")
    events = store("load_job_events", packet["job_id"])
    matches = [dict(row) for row in (events or ()) if isinstance(row, dict)
        and row.get("action") == "record_job_resolution"
        and row.get("resolution") == "Cancelled"
        and row.get("job_id") == packet["job_id"]
        and row.get("job_sha256") == packet["job_sha256"]]
    if len(matches) != 1 or not _valid_recorded_cancellation(matches[0]):
        raise RuntimeError("contained_parent_cancellation_persistence_unproven")
    return {"success": True, "status": "contained_parent_cancelled",
        "resolution": matches[0], "created": result.get("created") is True,
        "hardware_commands": 0, "provider_control_calls": 0,
        "water_credit_created": False}


def resolve_current_contained_b_parent(request, owner_principal, *, history_loader=None,
                                       readback_loader=None, store=None, now=None):
    """Resolve only the exact current canonical B containment, without control."""
    request = dict(request or {})
    if (request.get("contract_version") != "rootline_parent_job_terminal_resolution_request.v1"
            or request.get("mission_id") != "RMQ-20260813-04"
            or request.get("decision") != "cancel_unverified_remainder"
            or request.get("zone_id") != "B12345"
            or not str(owner_principal or "")
            or not str(request.get("job_id") or "")
            or not str(request.get("job_sha256") or "")):
        return {"success": False, "status": "contained_parent_cancellation_request_invalid",
            "hardware_commands": 0, "provider_control_calls": 0}, 400
    if history_loader is None:
        from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history
        history_loader = read_canonical_irrigation_history
    history = history_loader()
    if not isinstance(history, dict) or history.get("status") != "Available":
        return {"success": False, "status": "canonical_irrigation_history_unavailable",
            "hardware_commands": 0, "provider_control_calls": 0}, 503
    parents = list((((history.get("zones") or {}).get("B12345") or {})
        .get("contained_parent_jobs") or ()))
    matches = [parent for parent in parents
        if (parent.get("job") or {}).get("job_id") == request["job_id"]
        and (parent.get("job") or {}).get("job_sha256") == request["job_sha256"]]
    if len(matches) != 1:
        return {"success": False, "status": "exact_contained_parent_not_current",
            "hardware_commands": 0, "provider_control_calls": 0}, 409
    if readback_loader is None:
        from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
        from modules.telemetry.rootline_ewelink_readback import read_registered_device
        readback_loader = lambda: read_registered_device(
            "100204e9bc", token_store=PostgresOAuthTokenStore())
    try:
        controller = readback_loader()
        if store is None:
            from modules.telemetry.rootline_irrigation_execution_store import (
                rootline_irrigation_execution_store,
            )
            store = rootline_irrigation_execution_store
        result = record_contained_parent_cancellation(parent=matches[0],
            controller=controller, authorization={"mission_id": request["mission_id"],
                "decision": request["decision"], "job_id": request["job_id"],
                "job_sha256": request["job_sha256"],
                "owner_principal": str(owner_principal)}, store=store, now=now)
    except ValueError as exc:
        return {"success": False, "status": str(exc), "hardware_commands": 0,
            "provider_control_calls": 0}, 409
    except Exception:
        return {"success": False, "status": "contained_parent_cancellation_unavailable",
            "hardware_commands": 0, "provider_control_calls": 0}, 503
    return result, 201 if result.get("created") is True else 200


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        default=str).encode()).hexdigest()


def _cancellation_identity(job_id, job_sha256):
    digest = hashlib.sha256(f"{job_id}|{job_sha256}|Cancelled".encode()).hexdigest()
    return "ROOTLINE-JOB-CANCELLATION-" + digest[:24].upper()


def _valid_recorded_cancellation(row):
    keys=("contract_version","resolution","terminal","mission_id","job_id","job_sha256",
        "zone_id","current_segment","expected_segment_count","cumulative_verified_runtime_seconds",
        "cancelled_unverified_remaining_seconds","remaining_seconds","provider_off_verified",
        "provider_off_evidence_digest","provider_off_observed_at","fabricated_runtime_seconds",
        "water_credit_created","next_attempt_requires_fresh_execution_identity","reason")
    material={key:row.get(key) for key in keys}
    return (row.get("resolution_sha256") == _digest(material)
        and row.get("execution_id") == _cancellation_identity(
            row.get("job_id"), row.get("job_sha256")))


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("aware_time_required")
    return value.astimezone(timezone.utc)


def _time(value):
    try:
        parsed=datetime.fromisoformat(str(value or "").replace("Z","+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError,ValueError):
        return None
