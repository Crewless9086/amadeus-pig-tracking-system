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
        "execution_id": "ROOTLINE-JOB-CANCELLATION-"+digest[:24].upper(),
        "hardware_commands": 0, "provider_control_calls": 0}


def record_contained_parent_cancellation(*, parent, controller, authorization,
                                         store, now=None):
    packet = build_contained_parent_cancellation(parent=parent, controller=controller,
        authorization=authorization, now=now)
    result = store("record_job_resolution", packet)
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("contained_parent_cancellation_persistence_unproven")
    return {"success": True, "status": "contained_parent_cancelled",
        "resolution": packet, "created": result.get("created") is True,
        "hardware_commands": 0, "provider_control_calls": 0,
        "water_credit_created": False}


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        default=str).encode()).hexdigest()


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
