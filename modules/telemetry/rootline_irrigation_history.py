"""Canonical append-only ROOTLINE irrigation-history projection.

Uses the existing ``irrigation_events`` surface. Legacy rows are retained and
classified, never rewritten into successful watering. A planning epoch makes
absence authoritative only from its exact SAST cutoff through the transaction
snapshot cutoff.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
ZONES = {"B12345", "C12345"}
CONTRACT = "rootline_irrigation_outcome_v1"
EPOCH_EVENT = "PLANNING_EPOCH_STARTED"
QUALIFYING_FIELDS = (
    "execution_id", "start_evidence_id", "maximum_runtime_minutes",
    "shutdown_evidence_id", "evidence_cutoff", "provenance",
)


def read_canonical_irrigation_history(database_url=None, *, connect=None, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    if connect is None:
        import os
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
        url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
        if not url:
            return _unavailable("database_url_unavailable")
        connect = lambda: connect_bounded_rootline_postgres(database_url=url)
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select credit_json
                    from public.irrigation_water_credit_events
                    order by created_at,credit_id""")
                credit_rows = [row[0] for row in cursor.fetchall()]
                cursor.execute("select clock_timestamp()")
                snapshot_cutoff = _aware(cursor.fetchone()[0])
                cursor.execute("""select irrigation_event_id,event_at,event_type,zone_id,
                    planned_minutes,actual_minutes,details,source_id,actor,created_at
                    from public.irrigation_events
                    where zone_id in ('B12345','C12345') or event_type=%s
                    order by event_at,irrigation_event_id""", (EPOCH_EVENT,))
                rows = cursor.fetchall()
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='rootline_irrigation_execution'
                      and review_json->'rootline_execution'->>'action'
                          in ('record_eligibility','claim_before_on','mark_active','record_completed',
                              'record_job_resolution','contain_zone','record_ambiguous_shutdown')
                    order by created_at,review_event_id""")
                execution_rows = [row[0] for row in cursor.fetchall()]
        result = project_canonical_irrigation_history(rows, snapshot_cutoff=min(now, snapshot_cutoff))
        _attach_parent_jobs(result, execution_rows)
        from modules.telemetry.rootline_water_credit import project_water_credits
        result["water_credits"] = project_water_credits(credit_rows)
        _attach_water_credits(result)
        return result
    except Exception as exc:
        return _unavailable(exc.__class__.__name__)


def project_canonical_irrigation_history(rows, *, snapshot_cutoff):
    cutoff = _aware(snapshot_cutoff)
    normalized = [_row(row) for row in rows]
    zones = {}
    for zone in sorted(ZONES):
        zone_rows = [row for row in normalized if row["zone_id"] == zone]
        epochs = [row for row in zone_rows if row["event_type"] == EPOCH_EVENT
                  and _trusted_typed_row(row)]
        epoch = max((_timestamp(row["details"].get("epoch_start")) for row in epochs), default=None)
        local_cutoff = cutoff.astimezone(SAST)
        week_start = (local_cutoff - timedelta(
            days=local_cutoff.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        events, conflicts, seen = [], [], {}
        for row in zone_rows:
            details = row["details"]
            execution = str(details.get("execution_id") or "").strip()
            if not execution:
                events.append(_classified(row, _legacy_class(row), False))
                continue
            identity = f"{execution}|{row['event_type']}|{details.get('attempt', '')}"
            digest = _digest({key: row[key] for key in (
                "event_at", "event_type", "zone_id", "planned_minutes", "actual_minutes", "details")})
            if identity in seen:
                if seen[identity] != digest:
                    conflicts.append(identity)
                continue
            seen[identity] = digest
            qualifies, reason = _qualifies(row, cutoff)
            events.append(_classified(row, reason, qualifies))
        completed_days = sorted({event["event_at_sast"][:10] for event in events
                                 if event["qualifies_as_completed_watering"]})
        complete = epoch is not None and epoch.astimezone(SAST) <= week_start and not conflicts
        zones[zone] = {
            "planning_epoch_start": epoch.isoformat() if epoch else None,
            "complete_from": epoch.isoformat() if epoch else None,
            "complete_through": cutoff.isoformat() if complete else None,
            "coverage_status": "complete" if complete else "Unavailable",
            "verified_completed_days": completed_days,
            "verified_completed_day_count": len(completed_days),
            "events": events,
            "conflicts": conflicts,
        }
    return {"status": "Available", "contract_version": CONTRACT,
            "snapshot_cutoff": cutoff.isoformat(), "zones": zones,
            "delivered_volume_inferred": False, "flow_inferred": False}


def _attach_water_credits(history):
    credits = (history.get("water_credits") or {}).get("by_execution") or {}
    for zone in (history.get("zones") or {}).values():
        for event in zone.get("events") or []:
            credit = credits.get(event.get("execution_id"))
            event["water_credit"] = ({"status": "Available", "credit_id": credit["credit_id"],
                "delivered_volume_litres": credit["delivered_volume_litres"],
                "credit_method": credit["credit_method"]} if credit else {
                "status": "Unknown", "delivered_volume_litres": "Unknown",
                "dependency": "measured_volume_or_supported_calibration_required"})


def _attach_parent_jobs(history, rows):
    """Project incomplete immutable jobs without treating a segment as a day close."""
    from modules.telemetry.rootline_irrigation_job_contract import project_next_segment
    grouped = {}
    for raw in rows or ():
        row = raw if isinstance(raw, dict) else {}
        job_id = str(row.get("job_id") or "")
        if job_id:
            grouped.setdefault(job_id, []).append(row)
    by_zone = {}
    stale_by_zone = {zone: [] for zone in ZONES}
    contained_by_zone = {zone: [] for zone in ZONES}
    cutoff = _timestamp(history.get("snapshot_cutoff"))
    current_date = cutoff.astimezone(SAST).date().isoformat() if cutoff else None
    for events in grouped.values():
        authority = next((row for row in events
            if row.get("action") == "record_eligibility" and row.get("job_sha256")), None)
        if not authority:
            continue
        job = {"contract_version": "rootline_irrigation_job.v1",
            "job_id": authority.get("job_id"), "job_sha256": authority.get("job_sha256"),
            "zone_id": authority.get("zone_id"), "operating_date": authority.get("operating_date"),
            "requested_total_seconds": authority.get("requested_total_duration_seconds"),
            "requested_total_minutes": authority.get("requested_total_duration_minutes"),
            "governed_executable_seconds": authority.get("governed_executable_duration_seconds"),
            "maximum_segment_seconds": 3599,
            "expected_segment_count": authority.get("expected_segment_count"),
            "plan_identity": authority.get("plan_generation")}
        try:
            projection = project_next_segment(job, events, rearm_readback_off=True)
        except Exception:
            projection = {"status": "canonical_job_history_invalid", "command_authority": False}
        if projection.get("status") == "job_completed":
            continue
        completed_segments = [row for row in events
            if row.get("action") == "record_completed"
            and row.get("state") == "Completed"
            and row.get("shutdown_verified") is True]
        contained = [row for row in events if row.get("action") in {
            "contain_zone", "record_ambiguous_shutdown"}]
        if contained:
            zone = str(job.get("zone_id") or "")
            contained_ids = {str(row.get("execution_id") or "") for row in contained}
            prior_events = [row for row in events if not (
                str(row.get("execution_id") or "") in contained_ids
                and row.get("action") in {"claim_before_on", "mark_active",
                    "contain_zone", "record_ambiguous_shutdown"})]
            try:
                prior = project_next_segment(job, prior_events, rearm_readback_off=True)
            except Exception:
                prior = {"current_segment": None,
                    "cumulative_verified_runtime_seconds": None,
                    "remaining_seconds": None}
            if zone in ZONES:
                contained_by_zone[zone].append({"job": job,
                    "projection": {"status": "segment_contained",
                        "command_authority": False,
                        "current_segment": prior.get("current_segment"),
                        "cumulative_verified_runtime_seconds": prior.get(
                            "cumulative_verified_runtime_seconds")},
                    "completed_segment_count": len(completed_segments),
                    "remaining_seconds": prior.get("remaining_seconds"),
                    "resolution_reason": "segment_contained_without_verified_shutdown_or_runtime"})
            continue
        # A never-started eligibility is not a continuing parent. Continuity
        # begins only after a canonical segment completed and proved shutdown.
        if not completed_segments:
            continue
        zone = str(job.get("zone_id") or "")
        candidate = {"job": job, "projection": projection,
            "completed_segment_count": len(completed_segments),
            "remaining_seconds": projection.get("remaining_seconds")}
        if zone in ZONES:
            if current_date and job.get("operating_date") != current_date:
                stale_by_zone[zone].append(candidate)
                continue
            if zone in by_zone:
                by_zone[zone] = {"job": {"job_id": "conflicting_incomplete_parent_jobs",
                    "zone_id": zone}, "projection": {
                        "status": "conflicting_incomplete_parent_jobs",
                        "command_authority": False}, "remaining_seconds": None}
            else:
                by_zone[zone] = candidate
    for zone, value in by_zone.items():
        history["zones"][zone]["incomplete_parent_job"] = value
    for zone, values in stale_by_zone.items():
        if values:
            history["zones"][zone]["stale_incomplete_parent_jobs"] = values
    for zone, values in contained_by_zone.items():
        if values:
            history["zones"][zone]["contained_parent_jobs"] = values


def build_typed_history_event(*, event_id, event_at, event_type, zone_id, details,
                              planned_minutes=None, actual_minutes=None):
    if zone_id not in ZONES or not str(event_id or "").strip():
        raise ValueError("canonical_zone_and_event_identity_required")
    payload = dict(details or {})
    payload["contract_version"] = CONTRACT
    result = {"irrigation_event_id": event_id, "event_at": _aware(event_at).isoformat(),
            "event_type": event_type, "zone_id": zone_id,
            "planned_minutes": planned_minutes, "actual_minutes": actual_minutes,
            "details": payload, "source_id": "irrigation-controller-main",
            "actor": "ROOTLINE"}
    payload["event_sha256"] = _event_digest(result)
    return result


def _qualifies(row, cutoff):
    details = row["details"]
    if details.get("contract_version") != CONTRACT:
        return False, _legacy_class(row)
    if not _trusted_typed_row(row):
        return False, "typed_writer_or_digest_untrusted"
    if row["event_type"] != "COMPLETED":
        return False, str(details.get("classification") or row["event_type"]).lower()
    if any(not str(details.get(field) or "").strip() for field in QUALIFYING_FIELDS):
        return False, "completion_evidence_incomplete"
    evidence_cutoff = _timestamp(details.get("evidence_cutoff"))
    if evidence_cutoff is None or evidence_cutoff > cutoff or row["event_at"] > cutoff:
        return False, "completion_cutoff_invalid"
    runtime = _number(details.get("verified_runtime_minutes"))
    maximum = _number(details.get("maximum_runtime_minutes"))
    if not (0 < (runtime or 0) <= (maximum or 0) <= 60):
        return False, "runtime_or_fail_stop_invalid"
    if details.get("shutdown_verified") is not True:
        return False, "shutdown_unverified"
    if details.get("objective_satisfied") is not True:
        return False, "objective_not_satisfied"
    return True, "verified_completed_watering"


def _trusted_typed_row(row):
    details = row["details"]
    supplied = details.get("event_sha256")
    return (row.get("source_id") == "irrigation-controller-main" and row.get("actor") == "ROOTLINE"
            and details.get("contract_version") == CONTRACT
            and supplied in {_event_digest(row), _pre_scale_event_digest(row)})


def _pre_scale_event_digest(row):
    """Verify rows signed before numeric(8,2) storage normalization.

    The precise runtime remains digest-bound in typed details, allowing the
    original writer payload to be reconstructed without trusting a rounded
    database column or weakening any identity/evidence field.
    """
    details = row.get("details") if isinstance(row.get("details"), dict) else {}
    precise_actual = details.get("verified_runtime_minutes")
    precise_planned = details.get("maximum_runtime_minutes")
    if (_stored_minutes(row.get("planned_minutes")) != _stored_minutes(precise_planned)
            or _stored_minutes(row.get("actual_minutes")) != _stored_minutes(precise_actual)):
        return None
    return _digest({"irrigation_event_id": row.get("irrigation_event_id"),
        "event_at": _digest_timestamp(row.get("event_at")),
        "event_type": row.get("event_type"), "zone_id": row.get("zone_id"),
        "planned_minutes": _number(precise_planned if precise_planned is not None
                                   else row.get("planned_minutes")),
        "actual_minutes": _number(precise_actual if precise_actual is not None
                                  else row.get("actual_minutes")),
        "details": {key:details.get(key) for key in sorted(details) if key!="event_sha256"}})


def _event_digest(row):
    details = row.get("details") if isinstance(row.get("details"), dict) else {}
    return _digest({"irrigation_event_id": row.get("irrigation_event_id"),
        # PostgreSQL normalizes timestamptz values to the connection timezone.
        # Bind the instant, not the caller/connection's equivalent offset string.
        "event_at": _digest_timestamp(row.get("event_at")),
        "event_type": row.get("event_type"), "zone_id": row.get("zone_id"),
        # These columns are numeric(8,2). Bind the value PostgreSQL persists,
        # otherwise sub-minute runtime precision makes a valid typed row fail
        # its read-time integrity check after database normalization.
        "planned_minutes": _stored_minutes(row.get("planned_minutes")),
        "actual_minutes": _stored_minutes(row.get("actual_minutes")),
        "details": {key:details.get(key) for key in sorted(details) if key!="event_sha256"}})


def _stored_minutes(value):
    if value is None:
        return None
    try:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return _number(value)


def _digest_timestamp(value):
    parsed = _timestamp(value)
    return parsed.astimezone(timezone.utc).isoformat() if parsed else None


def _legacy_class(row):
    if row["event_type"].upper() in {"ZONE_COMPLETED", "COMPLETED", "DONE"}:
        return "legacy_completion_unsupported"
    if "TEST" in row["event_type"].upper() or "COMMISSION" in row["event_type"].upper():
        return "commissioning_or_test"
    return "legacy_or_unsupported"


def _classified(row, classification, qualifies):
    return {"irrigation_event_id": row["irrigation_event_id"],
            "event_at_sast": row["event_at"].astimezone(SAST).isoformat(),
            "event_type": row["event_type"], "execution_id": row["details"].get("execution_id"),
            "classification": classification,
            "qualifies_as_completed_watering": qualifies,
            "shutdown_verified": row["details"].get("shutdown_verified") is True,
            "objective_satisfied": row["details"].get("objective_satisfied") is True,
            "verified_runtime_minutes": row["details"].get("verified_runtime_minutes"),
            "maximum_runtime_minutes": row["details"].get("maximum_runtime_minutes"),
            "start_evidence_id": row["details"].get("start_evidence_id"),
            "shutdown_evidence_id": row["details"].get("shutdown_evidence_id"),
            "evidence_cutoff": row["details"].get("evidence_cutoff"),
            "provenance": row["details"].get("provenance"),
            "delivered_volume": "Unavailable", "flow": "Unavailable"}


def _row(row):
    if isinstance(row, dict):
        value = dict(row)
    else:
        keys = ("irrigation_event_id","event_at","event_type","zone_id","planned_minutes",
                "actual_minutes","details","source_id","actor","created_at")
        value = dict(zip(keys, row))
    value["event_at"] = _aware(value["event_at"])
    value["details"] = value.get("details") if isinstance(value.get("details"), dict) else {}
    return value


def _timestamp(value):
    try:
        return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str,
                             separators=(",", ":")).encode()).hexdigest()


def _unavailable(reason):
    return {"status": "Unavailable", "reason": reason, "contract_version": CONTRACT,
            "zones": {zone: {"coverage_status": "Unavailable", "complete_through": None,
                              "verified_completed_days": [], "events": []}
                      for zone in sorted(ZONES)}}
