from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_irrigation_history import (
    CONTRACT, EPOCH_EVENT, project_canonical_irrigation_history, _event_digest,
    _attach_parent_jobs, read_canonical_irrigation_history,
)
from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle
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


def test_late_midnight_completion_keeps_parent_date_and_bounded_segment_two_continuity():
    cutoff = datetime(2026, 8, 24, 0, 16, tzinfo=ZA)
    history = project_canonical_irrigation_history([
        epoch("B12345"), completed(execution="EXEC-LATE",
            at=datetime(2026, 8, 24, 0, 1, tzinfo=ZA))], snapshot_cutoff=cutoff)
    job = build_irrigation_job(zone_id="B12345", operating_date="2026-08-23",
        requested_total_seconds=7200, requested_total_minutes=120,
        maximum_segment_seconds=3599, expected_segment_count=2, plan_identity="PLAN-LATE")
    segment = project_next_segment(job, [])
    eligibility = {"action": "record_eligibility", **job,
        "requested_total_duration_seconds": 7200, "requested_total_duration_minutes": 120,
        "governed_executable_duration_seconds": 7198, "plan_generation": "PLAN-LATE"}
    completion = {"action": "record_completed", "job_id": job["job_id"],
        "operating_date": "2026-08-23", "segment_number": 1,
        "segment_identity": segment["segment_identity"], "execution_id": "EXEC-LATE",
        "state": "Completed", "verified_runtime_seconds": 3599,
        "shutdown_verified": True, "completed_at": datetime(
            2026, 8, 24, 0, 1, tzinfo=ZA).isoformat()}
    _attach_parent_jobs(history, [eligibility, completion])
    zone = history["zones"]["B12345"]
    assert zone["verified_completed_days"] == ["2026-08-23"]
    parent = zone["incomplete_parent_job"]
    assert parent["job"]["operating_date"] == "2026-08-23"
    assert parent["cross_operating_date_continuation"] is True
    assert parent["projection"]["status"] == "segment_ready"


def test_expired_midnight_parent_terminal_defer_disappears_idempotently():
    history = project_canonical_irrigation_history([epoch("B12345")],
        snapshot_cutoff=datetime(2026, 8, 24, 1, 0, tzinfo=ZA))
    job = build_irrigation_job(zone_id="B12345", operating_date="2026-08-23",
        requested_total_seconds=7200, maximum_segment_seconds=3599,
        expected_segment_count=2, plan_identity="PLAN-OLD")
    segment = project_next_segment(job, [])
    eligibility = {"action": "record_eligibility", **job,
        "requested_total_duration_seconds": 7200, "requested_total_duration_minutes": 120,
        "governed_executable_duration_seconds": 7198, "plan_generation": "PLAN-OLD"}
    completion = {"action": "record_completed", "job_id": job["job_id"],
        "operating_date": "2026-08-23", "segment_number": 1,
        "segment_identity": segment["segment_identity"], "execution_id": "EXEC-OLD",
        "state": "Completed", "verified_runtime_seconds": 3599,
        "shutdown_verified": True, "completed_at": "2026-08-24T00:01:00+02:00"}
    material = {"contract_version": "rootline_irrigation_job_resolution.v1",
        "resolution": "Deferred", "terminal": True, "job_id": job["job_id"],
        "job_sha256": job["job_sha256"], "zone_id": "B12345",
        "operating_date": "2026-08-23", "current_segment": 2,
        "expected_segment_count": 2, "cumulative_verified_runtime_seconds": 3599,
        "remaining_seconds": 3599,
        "reason": "parent_operating_date_elapsed_before_remaining_objective_completed"}
    import hashlib, json
    resolution = {**material, "resolution_sha256": hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "action": "record_job_resolution"}
    _attach_parent_jobs(history, [eligibility, completion, resolution, dict(resolution)])
    zone = history["zones"]["B12345"]
    assert "incomplete_parent_job" not in zone
    assert not zone.get("stale_incomplete_parent_jobs")


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


def test_contained_segment_parent_is_explicit_but_never_dispatchable():
    history=project_canonical_irrigation_history([epoch("B12345")],snapshot_cutoff=NOW)
    job=build_irrigation_job(zone_id="B12345",operating_date="2026-08-05",
        requested_total_seconds=7200,requested_total_minutes=120,
        maximum_segment_seconds=3599,expected_segment_count=2,plan_identity="PLAN-CONTAINED")
    eligibility={"action":"record_eligibility",**job,
        "requested_total_duration_seconds":7200,"requested_total_duration_minutes":120,
        "governed_executable_duration_seconds":7198,"plan_generation":"PLAN-CONTAINED"}
    contained={"action":"contain_zone","job_id":job["job_id"],"segment_number":1,
        "execution_id":"EXEC-CONTAINED","state":"ambiguous","shutdown_verified":False}
    _attach_parent_jobs(history,[eligibility,contained])
    zone=history["zones"]["B12345"]
    assert "incomplete_parent_job" not in zone
    parent=zone["contained_parent_jobs"][0]
    assert parent["remaining_seconds"]==7198
    assert parent["projection"]["command_authority"] is False
    assert parent["resolution_reason"]=="segment_contained_without_verified_shutdown_or_runtime"


def test_second_segment_containment_preserves_first_runtime_and_defers_residual():
    history=project_canonical_irrigation_history([epoch("C12345")],snapshot_cutoff=NOW)
    job=build_irrigation_job(zone_id="C12345",operating_date="2026-08-05",
        requested_total_seconds=7200,requested_total_minutes=120,
        maximum_segment_seconds=3599,expected_segment_count=2,plan_identity="PLAN-TWO")
    one=project_next_segment(job,[])
    complete={"action":"record_completed","job_id":job["job_id"],"segment_number":1,
        "segment_identity":one["segment_identity"],"execution_id":"EXEC-ONE",
        "state":"Completed","verified_runtime_seconds":3599,"shutdown_verified":True}
    two=project_next_segment(job,[complete],rearm_readback_off=True)
    rows=[{"action":"record_eligibility",**job,
        "requested_total_duration_seconds":7200,"requested_total_duration_minutes":120,
        "governed_executable_duration_seconds":7198,"plan_generation":"PLAN-TWO"},complete,
        {"action":"claim_before_on","job_id":job["job_id"],"segment_number":2,
         "segment_identity":two["segment_identity"],"execution_id":"EXEC-TWO","state":"claimed"},
        {"action":"contain_zone","job_id":job["job_id"],"segment_number":2,
         "execution_id":"EXEC-TWO","state":"ambiguous","shutdown_verified":False}]
    _attach_parent_jobs(history,rows)
    parent=history["zones"]["C12345"]["contained_parent_jobs"][0]
    assert parent["completed_segment_count"]==1
    assert parent["projection"]["current_segment"]==2
    assert parent["projection"]["cumulative_verified_runtime_seconds"]==3599
    assert parent["remaining_seconds"]==3599


def test_latest_same_zone_execution_projects_active_then_exact_terminal():
    history=project_canonical_irrigation_history(
        [epoch("C12345"),completed(execution="HISTORICAL")],snapshot_cutoff=NOW)
    active={"action":"mark_active","execution_id":"EXEC-CURRENT","zone_id":"C12345",
        "state":"Active","claimed_at":"2026-08-05T08:17:30+00:00"}
    _attach_parent_jobs(history,[active])
    assert history["zones"]["C12345"]["latest_execution"]==active
    closed={**active,"action":"record_completed","state":"Completed",
        "shutdown_verified":True,"objective_satisfied":True}
    _attach_parent_jobs(history,[active,closed])
    assert history["zones"]["C12345"]["latest_execution"]==closed


def test_multiple_same_zone_active_executions_fail_closed_without_cross_zone_leakage():
    history=project_canonical_irrigation_history(
        [epoch("B12345"),epoch("C12345")],snapshot_cutoff=NOW)
    rows=[{"action":"mark_active","execution_id":"EXEC-B-1","zone_id":"B12345",
           "state":"Active"},
          {"action":"mark_active","execution_id":"EXEC-B-2","zone_id":"B12345",
           "state":"Active"},
          {"action":"mark_active","execution_id":"EXEC-C","zone_id":"C12345",
           "state":"Active"}]
    _attach_parent_jobs(history,rows)
    b=history["zones"]["B12345"]
    assert b["execution_projection_conflict"] is True
    assert b["latest_execution"]["state"]=="ambiguous"
    assert history["zones"]["C12345"]["latest_execution"]["execution_id"]=="EXEC-C"


def test_production_loader_fetches_claim_recovery_and_preserves_verified_boundary():
    irrigation_rows=[epoch("B12345"),completed(zone="B12345",execution="OLD-B"),
                     epoch("C12345")]
    active_b={"action":"mark_active","execution_id":"EXEC-B","zone_id":"B12345",
              "state":"Active"}
    recovered_b={"action":"record_claim_recovery","execution_id":"EXEC-B",
                 "zone_id":"B12345","shutdown_verified":True,
                 "reason":"provider_off_verified"}
    active_c={"action":"mark_active","execution_id":"EXEC-C","zone_id":"C12345",
              "state":"Active"}
    class Cursor:
        def __init__(self): self.query=""; self.queries=[]
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def execute(self,query,params=None): self.query=query; self.queries.append(query)
        def fetchone(self): return (NOW,)
        def fetchall(self):
            if "irrigation_water_credit_events" in self.query: return []
            if "from public.irrigation_events" in self.query: return irrigation_rows
            if "sam_live_stock_conversation_review_events" in self.query:
                return [(active_b,),(recovered_b,),(active_c,)]
            raise AssertionError(self.query)
    cursor=Cursor()
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def cursor(self): return cursor
    history=read_canonical_irrigation_history(connect=lambda:Connection(),now=NOW)
    assert any("record_claim_recovery" in query for query in cursor.queries)
    b=project_zone_lifecycle(zone_id="B12345",recommendation={"status":"Hold"},
        history=history["zones"]["B12345"],
        execution=history["zones"]["B12345"].get("latest_execution"))
    c=project_zone_lifecycle(zone_id="C12345",recommendation={"status":"Hold"},
        history=history["zones"]["C12345"],
        execution=history["zones"]["C12345"].get("latest_execution"))
    assert b["state"] != "Started"
    assert history["zones"]["B12345"]["latest_execution"] == recovered_b
    assert c["state"] == "Started"


def test_unverified_claim_recovery_cannot_close_active_projection():
    history=project_canonical_irrigation_history([epoch("B12345")],snapshot_cutoff=NOW)
    active={"action":"mark_active","execution_id":"EXEC-B","zone_id":"B12345",
            "state":"Active"}
    unverified={"action":"record_claim_recovery","execution_id":"EXEC-B",
                "zone_id":"B12345","shutdown_verified":False}
    _attach_parent_jobs(history,[active,unverified])
    lifecycle=project_zone_lifecycle(zone_id="B12345",recommendation={"status":"Hold"},
        history=history["zones"]["B12345"],
        execution=history["zones"]["B12345"].get("latest_execution"))
    assert history["zones"]["B12345"]["latest_execution"] == active
    assert lifecycle["state"] == "Started"
    assert lifecycle["next_action_owner"] == "ROOTLINE"
