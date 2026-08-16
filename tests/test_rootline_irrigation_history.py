from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_irrigation_history import (
    CONTRACT, EPOCH_EVENT, project_canonical_irrigation_history, _event_digest,
    _attach_parent_jobs,
)
from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment

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


def test_pre_scale_typed_digest_remains_verifiable_after_database_rounding():
    event = completed(verified_runtime_minutes=3599 / 60)
    event["actual_minutes"] = 3599 / 60
    # Reproduce the original writer's pre-storage digest.
    from modules.telemetry.rootline_irrigation_history import _digest, _digest_timestamp, _number
    details = event["details"]
    details["event_sha256"] = _digest({
        "irrigation_event_id": event["irrigation_event_id"],
        "event_at": _digest_timestamp(event["event_at"]),
        "event_type": event["event_type"], "zone_id": event["zone_id"],
        "planned_minutes": _number(event["planned_minutes"]),
        "actual_minutes": _number(event["actual_minutes"]),
        "details": {key: details.get(key) for key in sorted(details) if key != "event_sha256"},
    })
    event["actual_minutes"] = 59.98
    result = project_canonical_irrigation_history(
        [epoch("B12345"), event], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 1


def test_pre_scale_digest_rejects_persisted_column_detail_mismatch():
    event = completed(verified_runtime_minutes=3599 / 60)
    event["actual_minutes"] = 3599 / 60
    from modules.telemetry.rootline_irrigation_history import _digest, _digest_timestamp, _number
    details = event["details"]
    details["event_sha256"] = _digest({
        "irrigation_event_id": event["irrigation_event_id"],
        "event_at": _digest_timestamp(event["event_at"]),
        "event_type": event["event_type"], "zone_id": event["zone_id"],
        "planned_minutes": _number(event["planned_minutes"]),
        "actual_minutes": _number(event["actual_minutes"]),
        "details": {key: details.get(key) for key in sorted(details) if key != "event_sha256"},
    })
    event["actual_minutes"] = 1.0
    result = project_canonical_irrigation_history(
        [epoch("B12345"), event], snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 0
    assert result["events"][-1]["classification"] == "typed_writer_or_digest_untrusted"


def test_missing_shutdown_start_or_cutoff_never_qualifies():
    rows = [epoch("B12345"),
            completed(execution="NO-START", start_evidence_id=""),
            completed(execution="NO-STOP", shutdown_verified=False),
            completed(execution="FUTURE", evidence_cutoff=NOW.replace(hour=11).isoformat())]
    result = project_canonical_irrigation_history(rows, snapshot_cutoff=NOW)["zones"]["B12345"]
    assert result["verified_completed_day_count"] == 0
    assert all(not event["qualifies_as_completed_watering"] for event in result["events"])


def test_parent_projection_survives_segment_level_completed_today():
    history=project_canonical_irrigation_history(
        [epoch("B12345"),completed()],snapshot_cutoff=NOW)
    job=build_irrigation_job(zone_id="B12345",operating_date="2026-08-05",
        requested_total_seconds=7200,requested_total_minutes=120,
        maximum_segment_seconds=3599,expected_segment_count=2,plan_identity="PLAN-1")
    segment=project_next_segment(job,[])
    eligibility={"action":"record_eligibility",**job,
        "requested_total_duration_seconds":7200,"requested_total_duration_minutes":120,
        "governed_executable_duration_seconds":7198,"plan_generation":"PLAN-1"}
    completion={"action":"record_completed","job_id":job["job_id"],
        "segment_number":1,"segment_identity":segment["segment_identity"],
        "execution_id":"EXEC-1","state":"Completed","verified_runtime_seconds":3599,
        "shutdown_verified":True}
    _attach_parent_jobs(history,[eligibility,completion])
    parent=history["zones"]["B12345"]["incomplete_parent_job"]
    assert parent["job"]["job_id"]==job["job_id"]
    assert parent["completed_segment_count"]==1
    assert parent["remaining_seconds"]==3599
    assert parent["projection"]["status"]=="segment_ready"


def test_eligibility_only_history_never_becomes_continuing_parent():
    history=project_canonical_irrigation_history([epoch("B12345")],snapshot_cutoff=NOW)
    job=build_irrigation_job(zone_id="B12345",operating_date="2026-08-05",
        requested_total_seconds=7200,requested_total_minutes=120,
        maximum_segment_seconds=3599,expected_segment_count=2,plan_identity="PLAN-OLD")
    eligibility={"action":"record_eligibility",**job,
        "requested_total_duration_seconds":7200,"requested_total_duration_minutes":120,
        "governed_executable_duration_seconds":7198,"plan_generation":"PLAN-OLD"}
    _attach_parent_jobs(history,[eligibility])
    assert "incomplete_parent_job" not in history["zones"]["B12345"]


def test_current_parent_is_selected_and_older_parent_remains_explicit():
    history=project_canonical_irrigation_history([epoch("C12345")],snapshot_cutoff=NOW)
    rows=[]
    for date,identity in (("2026-08-04","OLD"),("2026-08-05","CURRENT")):
        job=build_irrigation_job(zone_id="C12345",operating_date=date,
            requested_total_seconds=7200,requested_total_minutes=120,
            maximum_segment_seconds=3599,expected_segment_count=2,plan_identity=identity)
        segment=project_next_segment(job,[])
        rows.extend([{"action":"record_eligibility",**job,
            "requested_total_duration_seconds":7200,"requested_total_duration_minutes":120,
            "governed_executable_duration_seconds":7198,"plan_generation":identity},
            {"action":"record_completed","job_id":job["job_id"],"segment_number":1,
             "segment_identity":segment["segment_identity"],"execution_id":"EXEC-"+identity,
             "state":"Completed","verified_runtime_seconds":3599,"shutdown_verified":True}])
    _attach_parent_jobs(history,rows)
    zone=history["zones"]["C12345"]
    assert zone["incomplete_parent_job"]["job"]["operating_date"]=="2026-08-05"
    assert [item["job"]["operating_date"] for item in zone["stale_incomplete_parent_jobs"]]==[
        "2026-08-04"]
