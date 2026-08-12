from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_irrigation_history import (
    CONTRACT, EPOCH_EVENT, project_canonical_irrigation_history, _event_digest,
)

ZA = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 8, 5, 10, 0, tzinfo=ZA)


def row(identity, zone, event_type, at, details=None, actual=60):
    return {"irrigation_event_id": identity, "event_at": at,
            "event_type": event_type, "zone_id": zone, "planned_minutes": 60,
            "actual_minutes": actual, "details": details or {},
            "source_id": "irrigation-controller-main", "actor": "ROOTLINE",
            "created_at": at}


def epoch(zone):
    start=NOW.replace(day=3,hour=0)
    details={
        "contract_version": CONTRACT, "epoch_start": start.isoformat(),
        "provenance": "reviewed_reconciliation"}
    result=row(f"EPOCH-{zone}", zone, EPOCH_EVENT, start, details)
    details["event_sha256"]=_event_digest(result)
    return result


def completed(zone="B12345", execution="EXEC-B", at=None, **changes):
    at = at or NOW.replace(hour=8)
    details = {"contract_version": CONTRACT, "execution_id": execution,
        "start_evidence_id": execution + "-START", "maximum_runtime_minutes": 60,
        "verified_runtime_minutes": 60, "shutdown_evidence_id": execution + "-STOP",
        "shutdown_verified": True, "objective_satisfied": True,
        "evidence_cutoff": at.isoformat(), "provenance": "canonical_execution"}
    details.update(changes)
    result=row(execution + "-COMPLETED", zone, "COMPLETED", at, details)
    details["event_sha256"]=_event_digest(result)
    return result


def test_epoch_makes_snapshot_absence_authoritative_per_zone():
    result = project_canonical_irrigation_history(
        [epoch("B12345"), epoch("C12345")], snapshot_cutoff=NOW)
    for zone in result["zones"].values():
        assert zone["coverage_status"] == "complete"
        assert zone["complete_through"] == NOW.isoformat()
        assert zone["verified_completed_day_count"] == 0


def test_midweek_epoch_does_not_assert_absence_before_coverage():
    marker=epoch("B12345")
    marker["details"]["epoch_start"]=NOW.replace(hour=0).isoformat()
    marker["event_at"]=NOW.replace(hour=0)
    marker["details"]["event_sha256"]=_event_digest(marker)
    zone=project_canonical_irrigation_history([marker],snapshot_cutoff=NOW)["zones"]["B12345"]
    assert zone["coverage_status"]=="Unavailable" and zone["complete_through"] is None


def test_legacy_short_completions_and_partial_events_do_not_discharge_debt():
    legacy = row("LEGACY", "B12345", "ZONE_COMPLETED", NOW.replace(hour=1), {}, actual=1)
    partial = completed(execution="PARTIAL", objective_satisfied=False)
    result = project_canonical_irrigation_history(
        [epoch("B12345"), legacy, partial], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 0
    assert {event["classification"] for event in result["events"]} >= {
        "legacy_completion_unsupported", "objective_not_satisfied"}


def test_exact_unique_completion_discharges_only_bound_zone_and_day():
    event = completed()
    result = project_canonical_irrigation_history(
        [epoch("B12345"), epoch("C12345"), event], snapshot_cutoff=NOW)["zones"]
    assert result["B12345"]["verified_completed_days"] == ["2026-08-05"]
    assert result["C12345"]["verified_completed_days"] == []


def test_exact_replay_deduplicates_and_conflicting_replay_removes_coverage():
    event = completed()
    exact = project_canonical_irrigation_history(
        [epoch("B12345"), event, dict(event)], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert exact["verified_completed_day_count"] == 1 and not exact["conflicts"]
    conflict = dict(event); conflict["details"] = {**event["details"], "objective_satisfied": False}
    bad = project_canonical_irrigation_history(
        [epoch("B12345"), event, conflict], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert bad["coverage_status"] == "Unavailable"
    assert bad["complete_through"] is None and bad["conflicts"]


def test_typed_digest_cannot_be_rebound_to_another_zone_or_day():
    event=completed()
    rebound=dict(event); rebound["zone_id"]="C12345"
    result=project_canonical_irrigation_history(
        [epoch("C12345"),rebound],snapshot_cutoff=NOW)["zones"]["C12345"]
    assert result["verified_completed_day_count"]==0
    assert any(item["classification"]=="typed_writer_or_digest_untrusted"
               for item in result["events"])


def test_typed_digest_binds_instant_across_database_timezone_normalization():
    event = completed()
    database_row = dict(event)
    database_row["event_at"] = event["event_at"].astimezone(timezone.utc)
    result = project_canonical_irrigation_history(
        [epoch("B12345"), database_row], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 1


def test_typed_digest_binds_numeric_columns_after_database_scale_normalization():
    event = completed(verified_runtime_minutes=3599 / 60)
    event["actual_minutes"] = 3599 / 60
    event["details"]["event_sha256"] = _event_digest(event)
    database_row = dict(event)
    database_row["actual_minutes"] = 59.98
    result = project_canonical_irrigation_history(
        [epoch("B12345"), database_row], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 1


def test_missing_shutdown_start_or_cutoff_never_qualifies():
    rows = [epoch("B12345"),
            completed(execution="NO-START", start_evidence_id=""),
            completed(execution="NO-STOP", shutdown_verified=False),
            completed(execution="FUTURE", evidence_cutoff=NOW.replace(hour=11).isoformat())]
    result = project_canonical_irrigation_history(rows, snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 0
    assert all(not event["qualifies_as_completed_watering"] for event in result["events"])
