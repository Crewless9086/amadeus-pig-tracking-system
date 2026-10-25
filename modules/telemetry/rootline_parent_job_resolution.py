"""Non-actuating append-only resolution for an explicitly contained parent job."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

CONTRACT_VERSION = "rootline_parent_job_terminal_resolution.v1"
REQUEST_VERSION = "rootline_parent_job_terminal_resolution_request.v1"
ZONES = frozenset({"B12345", "C12345"})
SEMANTIC_KEYS = ("contract_version", "resolution", "terminal", "mission_id",
    "job_id", "job_sha256", "zone_id", "current_segment", "expected_segment_count",
    "cumulative_verified_runtime_seconds", "cancelled_unverified_remaining_seconds",
    "remaining_seconds", "fabricated_runtime_seconds", "water_credit_created",
    "next_attempt_requires_fresh_execution_identity", "reason", "owner_principal")


def build_contained_parent_cancellation(*, parent, controller, authorization, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    parent = dict(parent or {})
    job = dict(parent.get("job") or {})
    projection = dict(parent.get("projection") or {})
    authorization = dict(authorization or {})
    if (job.get("zone_id") not in ZONES
            or projection.get("status") != "segment_contained"
            or authorization.get("mission_id") != "RMQ-20260813-04"
            or authorization.get("decision") != "cancel_unverified_remainder"
            or not str(authorization.get("owner_principal") or "")
            or authorization.get("job_id") != job.get("job_id")
            or authorization.get("job_sha256") != job.get("job_sha256")):
        raise ValueError("contained_parent_cancellation_authority_invalid")
    _validate_parent_totals(parent)
    from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract
    binding = commissioned_irrigation_contract(job["zone_id"])
    retrieved = _time((controller or {}).get("retrieved_at")
                      or (controller or {}).get("trusted_receipt_at"))
    provider_time = (controller or {}).get("provider_observed_at")
    observed = _time(provider_time) if provider_time is not None else None
    channels = list((controller or {}).get("channels") or ())
    if (retrieved is None or now < retrieved or now-retrieved > timedelta(minutes=5)
            or (provider_time is not None and (observed is None
                or not timedelta(seconds=-30) <= now-observed <= timedelta(minutes=5)))
            or (controller or {}).get("online") is not True
            or (controller or {}).get("device_id") != binding["device_id"]
            or (controller or {}).get("observation_fresh") is not True
            or (controller or {}).get("current_outputs_authoritative") is not True
            or len(channels) != 4
            or any(not isinstance(row, dict) for row in channels)
            or any(type(row.get("channel")) is not int for row in channels)
            or {row.get("channel") for row in channels} != {1, 2, 3, 4}
            or binding["channel"] not in {row.get("channel") for row in channels}
            or any(row.get("output_state") != "OFF" for row in channels)
            or not str((controller or {}).get("response_digest") or "")):
        raise ValueError("current_provider_off_evidence_invalid")
    material = {"contract_version": CONTRACT_VERSION, "resolution": "Cancelled",
        "terminal": True, "mission_id": "RMQ-20260813-04",
        "job_id": job["job_id"], "job_sha256": job["job_sha256"],
        "zone_id": job["zone_id"], "current_segment": projection.get("current_segment"),
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
    result = store("record_job_resolution", {**packet, "_current_controller": controller})
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("contained_parent_cancellation_persistence_unproven")
    events = store("load_job_events", packet["job_id"])
    saved = _recorded_cancellation(events, packet, expected=packet)
    if saved is None:
        raise RuntimeError("contained_parent_cancellation_persistence_unproven")
    return _success(saved, created=result.get("created") is True)


def resolve_current_contained_parent(request, owner_principal, *, history_loader=None,
                                     readback_loader=None, store=None, now=None):
    """Cancel an exact current B/C remainder, or read back its original decision."""
    if not isinstance(request, dict):
        return _failure("contained_parent_cancellation_request_invalid"), 400
    request = dict(request)
    if (request.get("contract_version") != REQUEST_VERSION
            or request.get("mission_id") != "RMQ-20260813-04"
            or request.get("decision") != "cancel_unverified_remainder"
            or request.get("zone_id") not in ZONES
            or not str(owner_principal or "").strip()
            or not str(request.get("job_id") or "").strip()
            or not str(request.get("job_sha256") or "").strip()):
        return _failure("contained_parent_cancellation_request_invalid"), 400
    if history_loader is None:
        from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history
        history_loader = read_canonical_irrigation_history
    if store is None:
        from modules.telemetry.rootline_irrigation_execution_store import (
            rootline_irrigation_execution_store,
        )
        store = rootline_irrigation_execution_store
    authorization = {**request, "owner_principal": str(owner_principal)}
    try:
        # Replaying a recorded decision is read-only even after the resolved job
        # disappears from current history. It cannot acquire new provider evidence.
        prior = _recorded_cancellation(store("load_job_events", request["job_id"]),
                                       authorization)
        if prior is not None:
            return _success(prior, created=False), 200
        history = history_loader()
        if not isinstance(history, dict) or history.get("status") != "Available":
            return _failure("canonical_irrigation_history_unavailable"), 503
        parents = (((history.get("zones") or {}).get(request["zone_id"]) or {})
                   .get("contained_parent_jobs") or ())
        matches = [parent for parent in parents if isinstance(parent, dict)
            and (parent.get("job") or {}).get("job_id") == request["job_id"]
            and (parent.get("job") or {}).get("job_sha256") == request["job_sha256"]
            and (parent.get("job") or {}).get("zone_id") == request["zone_id"]]
        if len(matches) != 1:
            return _failure("exact_contained_parent_not_current"), 409
        if readback_loader is None:
            from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract
            from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
            from modules.telemetry.rootline_ewelink_readback import read_registered_device
            device_id = commissioned_irrigation_contract(request["zone_id"])["device_id"]
            readback_loader = lambda: read_registered_device(
                device_id, token_store=PostgresOAuthTokenStore())
        result = record_contained_parent_cancellation(parent=matches[0],
            controller=readback_loader(), authorization=authorization, store=store, now=now)
    except ValueError as exc:
        return _failure(str(exc)), 409
    except Exception:
        return _failure("contained_parent_cancellation_unavailable"), 503
    return result, 201 if result.get("created") is True else 200


def resolve_current_contained_b_parent(request, owner_principal, **kwargs):
    """Compatibility entry point retains its original B-only boundary."""
    if not isinstance(request, dict) or request.get("zone_id") != "B12345":
        return _failure("contained_parent_cancellation_request_invalid"), 400
    return resolve_current_contained_parent(request, owner_principal, **kwargs)


def _failure(status):
    return {"success": False, "status": status,
            "hardware_commands": 0, "provider_control_calls": 0}


def _success(row, *, created):
    return {"success": True, "status": "contained_parent_cancelled",
            "resolution": row, "created": created, "hardware_commands": 0,
            "provider_control_calls": 0, "water_credit_created": False}


def _validate_parent_totals(parent):
    from modules.telemetry.rootline_irrigation_job_contract import _validate
    job = _validate(parent["job"])
    projection = parent.get("projection") or {}
    credited = projection.get("cumulative_verified_runtime_seconds")
    remaining = parent.get("remaining_seconds")
    segment = projection.get("current_segment")
    if (any(type(value) is not int for value in (credited, remaining, segment))
            or credited < 0 or remaining <= 0
            or credited + remaining != job["governed_executable_seconds"]
            or not 1 <= segment <= job["expected_segment_count"]):
        raise ValueError("contained_parent_accounting_unproven")


def _recorded_cancellation(events, binding, *, expected=None):
    if not isinstance(events, (list, tuple)):
        raise ValueError("contained_parent_cancellation_history_invalid")
    rows = [row for row in events if isinstance(row, dict)
        and row.get("action") == "record_job_resolution"
        and row.get("resolution") == "Cancelled"]
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("contained_parent_cancellation_history_conflict")
    row = rows[0]
    if (not _valid_recorded_cancellation(row)
            or any(row.get(key) != binding.get(key) for key in
                   ("job_id", "job_sha256", "zone_id", "mission_id", "owner_principal"))
            or row.get("contract_version") != CONTRACT_VERSION
            or row.get("terminal") is not True
            or row.get("provider_off_verified") is not True
            or row.get("fabricated_runtime_seconds") != 0
            or row.get("water_credit_created") is not False
            or row.get("next_attempt_requires_fresh_execution_identity") is not True
            or row.get("remaining_seconds") != 0
            or not str(row.get("provider_off_evidence_digest") or "").strip()
            or _time(row.get("provider_off_observed_at")) is None
            or (expected is not None and any(row.get(key) != expected.get(key)
                                             for key in SEMANTIC_KEYS))):
        raise ValueError("contained_parent_cancellation_history_conflict")
    return row


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
