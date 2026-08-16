from copy import deepcopy
from datetime import datetime, timedelta, timezone

from modules.telemetry.rootline_execution_authority import (
    build_execution_eligibility, equivalent_fresh_eligibility,
    validate_execution_eligibility,
)

NOW=datetime(2026,8,8,18,0,tzinfo=timezone.utc)


def inputs(*, rain=0, zone="B12345", debt=2, controller_changes=None,
           weather_at=NOW, water_at=NOW):
    task={"task_id":f"irrigation_{zone}","zone_decision":"Run now",
          "recommendation":"Recommend","planned_duration_minutes":60,
          "requested_total_duration_minutes":120,"expected_segment_count":2,"rank":1,
          "weekly_obligation":{"status":"available","delivery_debt_days":debt,
                               "remaining_weekly_obligation_days":4}}
    plan={"evidence_generation":"PLAN-GEN-1","operating_date":"2026-08-08",
          "candidate_tasks":[task]}
    evidence={"weather":{"observed_at":weather_at.isoformat(),"rain_rate_mm_h":rain,
                         "rain_today_mm":rain},
              "irrigation":{"source":"rootline_daily_advisor",
                  "advisor_generated_at":NOW.isoformat(),
                  "advisor_operating_date":"2026-08-08",
                  "zones":[{"zone_id":zone,"live_rain_release_proven":True,
                            "forecast_planning_quality":"fresh","planning_warnings":[]}]},
              "tanks":{"observed_at":water_at.isoformat(),"reservoir_state":"FULL",
                       "reservoir_fraction":1.0}}
    controller={"device_id":"100204e9bc","online":True,"firmware":"3.8.2",
        "actuation_configuration_safe":True,"timers_enabled":False,"scenes_enabled":False,
        "interlock_enabled":False,"provider_control_calls":0,"trusted_receipt_at":NOW.isoformat(),
        "commissioned_baseline_id":"ROOTLINE-EWELINK-BASELINE-1","response_digest":"READ-1",
        "channels":[{"channel":n,"output_state":"OFF","native_auto_off_enabled":True,
                     "native_auto_off_seconds":3599,"power_restoration_state":"OFF"}
                    for n in range(1,5)]}
    controller.update(controller_changes or {})
    return plan,evidence,controller


def test_fresh_dry_debt_creates_one_typed_single_use_artifact():
    value=build_execution_eligibility(plan=inputs()[0],evidence=inputs()[1],
                                      controller=inputs()[2],now=NOW)
    assert value["eligible"] is True and value["zone_id"]=="B12345"
    assert value["channel"]==1 and value["maximum_duration_seconds"]==3599
    assert value["requested_total_duration_minutes"]==120
    assert value["requested_total_duration_seconds"]==7200
    assert value["governed_executable_duration_seconds"]==7198
    assert value["expected_segment_count"]==2 and value["current_segment"]==1
    assert value["operating_date"]=="2026-08-08"
    assert value["command_mapping"]=={"channel":1,"on":"irrigation_1_ch1_on",
                                       "off":"irrigation_1_ch1_off"}
    assert validate_execution_eligibility(value,now=NOW)==value


def test_stale_forecast_warning_is_digest_bound_but_does_not_block_execution():
    plan,evidence,controller=inputs()
    evidence["irrigation"]["zones"][0].update(
        forecast_planning_quality="degraded",
        planning_warnings=["forecast_stale_or_unavailable"],
    )
    value=build_execution_eligibility(plan=plan,evidence=evidence,
                                      controller=controller,now=NOW)
    assert value["eligible"] is True
    assert value["contract_version"] == "rootline_execution_eligibility.v4"
    assert value["live_rain_release"]["forecast_planning_quality"] == "degraded"
    assert value["live_rain_release"]["planning_warnings"] == ["forecast_stale_or_unavailable"]


def test_rain_hold_and_stale_or_conflicting_evidence_create_no_authority():
    for changes in ({"rain":.25},{"weather_at":NOW-timedelta(minutes=31)},
                    {"water_at":NOW-timedelta(hours=25)},{"debt":0}):
        plan,evidence,controller=inputs(**changes)
        value=build_execution_eligibility(plan=plan,evidence=evidence,
                                           controller=controller,now=NOW)
        assert value["eligible"] is False and value["command_authority"] is False


def test_missing_or_unproven_governed_rain_release_creates_no_authority():
    for irrigation in ({}, {"source":"rootline_daily_advisor",
            "advisor_generated_at":NOW.isoformat(),
            "advisor_operating_date":"2026-08-08",
            "zones":[{"zone_id":"B12345","live_rain_release_proven":False}]},
            {"source":"rootline_daily_advisor",
             "advisor_generated_at":(NOW-timedelta(minutes=31)).isoformat(),
             "advisor_operating_date":"2026-08-08",
             "zones":[{"zone_id":"B12345","live_rain_release_proven":True}]}):
        plan,evidence,controller=inputs(); evidence["irrigation"]=irrigation
        value=build_execution_eligibility(plan=plan,evidence=evidence,
                                           controller=controller,now=NOW)
        assert value["status"]=="live_rain_release_not_proven"
        assert value["eligible"] is False and value["hardware_control"] is False


def test_missing_governed_total_duration_fails_closed():
    plan,evidence,controller=inputs()
    plan["candidate_tasks"][0].pop("requested_total_duration_minutes")
    value=build_execution_eligibility(plan=plan,evidence=evidence,
        controller=controller,now=NOW)
    assert value["status"]=="governed_total_duration_unavailable"
    assert value["command_authority"] is False


def test_persisted_completion_projects_exact_residual_segment_two():
    plan,evidence,controller=inputs()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    event={"job_id":first["job_id"],"segment_number":1,
        "segment_identity":first["segment_identity"],"execution_id":first["execution_id"],
        "state":"Completed","verified_runtime_seconds":3599,
        "shutdown_verified":True,"rearm_readback_off":False}
    second=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,
        now=NOW,job_event_reader=lambda job_id:[event])
    assert second["eligible"] is True and second["current_segment"]==2
    assert second["cumulative_verified_runtime_seconds"]==3599
    assert second["predecessor_off_rearm_verified"] is True
    assert second["segment_identity"]!=first["segment_identity"]


def test_refreshed_plan_preserves_durable_parent_identity_for_segment_two():
    plan,evidence,controller=inputs()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    parent_job={"contract_version":"rootline_irrigation_job.v1",
        "job_id":first["job_id"],"job_sha256":first["job_sha256"],"zone_id":"B12345",
        "operating_date":first["operating_date"],"requested_total_seconds":7200,
        "requested_total_minutes":120,"governed_executable_seconds":7198,
        "maximum_segment_seconds":3599,"expected_segment_count":2,
        "plan_identity":first["plan_generation"]}
    event={"job_id":first["job_id"],"segment_number":1,
        "segment_identity":first["segment_identity"],"execution_id":first["execution_id"],
        "state":"Completed","verified_runtime_seconds":3599,"shutdown_verified":True}
    refreshed=deepcopy(plan); refreshed["evidence_generation"]="REFRESHED"
    refreshed["candidate_tasks"][0]["reason"]="Fresh evidence still supports continuation"
    refreshed["candidate_tasks"][0]["incomplete_parent_job"]={"job":parent_job,
        "projection":{"status":"segment_ready","current_segment":2,
            "cumulative_verified_runtime_seconds":3599,"remaining_seconds":3599},
        "remaining_seconds":3599}
    second=build_execution_eligibility(plan=refreshed,evidence=evidence,
        controller=controller,now=NOW,job_event_reader=lambda _:[event])
    assert second["eligible"] is True and second["job_id"]==first["job_id"]
    assert second["current_segment"]==2 and second["segment_requested_seconds"]==3599
    assert second["cumulative_verified_runtime_seconds"]==3599


def test_incomplete_parent_hold_is_explicit_digest_bound_deferment():
    plan,evidence,controller=inputs()
    task=plan["candidate_tasks"][0]
    task.update(zone_decision="Hold",recommendation="Hold",planned_duration_minutes=None,
        reason="Fresh local rain blocks continuation",
        incomplete_parent_job={"job":{"job_id":"JOB-1","job_sha256":"a"*64,
            "zone_id":"B12345","operating_date":"2026-08-08","expected_segment_count":2},
            "projection":{"current_segment":2,"cumulative_verified_runtime_seconds":3599},
            "remaining_seconds":3599})
    result=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    assert result["status"]=="durable_parent_job_deferred"
    assert result["job_resolution"]["reason"]=="Fresh local rain blocks continuation"
    assert result["command_authority"] is False and result["hardware_control"] is False


def test_controller_drift_or_unexpected_output_creates_no_authority():
    plan,evidence,controller=inputs()
    controller["channels"][1]["output_state"]="ON"
    assert build_execution_eligibility(plan=plan,evidence=evidence,
        controller=controller,now=NOW)["eligible"] is False
    plan,evidence,controller=inputs(controller_changes={"firmware":"3.9.0"})
    assert build_execution_eligibility(plan=plan,evidence=evidence,
        controller=controller,now=NOW)["eligible"] is False


def test_expiry_and_fresh_equivalence_are_exactly_bound():
    plan,evidence,controller=inputs()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    later=build_execution_eligibility(plan=deepcopy(plan),evidence=deepcopy(evidence),
        controller={**controller,"trusted_receipt_at":(NOW+timedelta(minutes=1)).isoformat(),
                    "response_digest":"READ-2"},now=NOW+timedelta(minutes=1))
    assert equivalent_fresh_eligibility(first,later,now=NOW+timedelta(minutes=1))
    changed=deepcopy(plan); changed["candidate_tasks"][0]["weekly_obligation"]["delivery_debt_days"]=3
    newer=build_execution_eligibility(plan=changed,evidence=evidence,controller=controller,now=NOW)
    assert not equivalent_fresh_eligibility(first,newer,now=NOW)
    assert validate_execution_eligibility(first,now=NOW+timedelta(minutes=16)) is None


def test_regenerated_unchanged_decision_keeps_one_durable_consumption_key():
    plan,evidence,controller=inputs()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    controller["trusted_receipt_at"]=(NOW+timedelta(minutes=1)).isoformat()
    second=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,
                                       now=NOW+timedelta(minutes=1))
    assert first["execution_id"] != second["execution_id"]
    assert first["consumption_key"] == second["consumption_key"]


def test_fresh_receipt_generation_is_equivalent_when_decision_and_all_gates_still_pass():
    plan,evidence,controller=inputs()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    refreshed=deepcopy(plan); refreshed["evidence_generation"]="FRESH-REQUEST-GENERATION"
    later_evidence=deepcopy(evidence)
    later_evidence["weather"]["observed_at"]=(NOW+timedelta(minutes=1)).isoformat()
    later_evidence["tanks"]["observed_at"]=(NOW+timedelta(minutes=1)).isoformat()
    later=build_execution_eligibility(plan=refreshed,evidence=later_evidence,
        controller={**controller,"trusted_receipt_at":(NOW+timedelta(minutes=1)).isoformat(),
                    "response_digest":"READ-FRESH"},now=NOW+timedelta(minutes=1))
    assert first["source_plan_generation"] != later["source_plan_generation"]
    assert first["plan_evidence_digest"] != later["plan_evidence_digest"]
    assert equivalent_fresh_eligibility(first,later,now=NOW+timedelta(minutes=1))


def test_weekly_ledger_cutoff_refresh_is_provenance_not_decision_drift():
    plan,evidence,controller=inputs()
    plan["candidate_tasks"][0]["weekly_obligation"]["ledger_complete_through"]=NOW.isoformat()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    fresh=deepcopy(plan)
    fresh["candidate_tasks"][0]["weekly_obligation"]["ledger_complete_through"]=(NOW+timedelta(minutes=1)).isoformat()
    later=build_execution_eligibility(plan=fresh,evidence=evidence,
        controller={**controller,"trusted_receipt_at":(NOW+timedelta(minutes=1)).isoformat(),
                    "response_digest":"READ-LATER"},now=NOW+timedelta(minutes=1))
    assert first["weekly_debt"]["ledger_complete_through"] != later["weekly_debt"]["ledger_complete_through"]
    assert first["plan_generation"] == later["plan_generation"]
    assert equivalent_fresh_eligibility(first,later,now=NOW+timedelta(minutes=1))


def test_power_never_changes_eligibility_but_canonical_generation_remains_bound():
    plan,evidence,controller=inputs()
    first=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    evidence["power"]={"battery_soc_pct":1,"grid_power_w":9999}
    changed=build_execution_eligibility(plan={**plan,"evidence_generation":"POWER-CHANGED"},
        evidence=evidence,controller=controller,now=NOW)
    assert changed["eligible"] is True and "power" not in changed and "battery" not in repr(changed).lower()
    assert changed["eligible"] is True
    assert changed["eligibility_id"] != first["eligibility_id"]
