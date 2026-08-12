from datetime import date

from modules.pig_weights.herdmaster_breeding_exposure_recovery import (
    build_grouped_preview,
    planned_exposure_removal_on,
)
from modules.pig_weights.herdmaster_breeding_operating_loop import build_breeding_operating_loop
from modules.pig_weights.pig_weights_validation import validate_new_litter_payload
from pathlib import Path


def test_shared_channel_invariant_inclusive_removal_date():
    assert planned_exposure_removal_on("2026-08-12", 17) == "2026-08-28"


def test_preview_rejects_noncanonical_seventeen_day_removal():
    result = build_grouped_preview({"rows": [{
        "pig_id":"SOW-1","label":"Sow One","action":"exposure","boar_pig_id":"BOAR-1",
        "exposure_started_on":"2026-08-12","planned_removal_on":"2026-08-29",
    }]}, evidence_generation="GEN-OLD")
    assert result["success"] is False
    assert result["errors"] == ["row_1_exact_exposure_required"]


def test_grouped_preview_separates_exposure_hold_and_near_farrowing():
    result = build_grouped_preview({"rows": [
        {"pig_id": "SOW-1", "label": "Sow One", "action": "exposure", "boar_pig_id": "BOAR-1",
         "exposure_started_on": "2026-08-12", "planned_removal_on": "2026-08-28"},
        {"pig_id": "SOW-2", "label": "Ms Piggy", "action": "recovery_hold", "body_condition_score": 2,
         "observed_at": "2026-08-12T08:00:00+02:00", "factual_note": "Body condition scored 2."},
        {"pig_id": "SOW-3", "label": "Linda", "action": "near_farrowing",
         "observed_at": "2026-08-12T08:00:00+02:00", "factual_note": "Appears close to farrowing."},
    ]}, evidence_generation="GEN-1")
    assert result["success"] is True
    assert result["preview"]["row_count"] == 3
    assert len({row["pig_id"] for row in result["preview"]["rows"]}) == 3
    assert result["creates_mating"] is False
    assert result["asserts_service_date"] is False
    linda = result["preview"]["rows"][2]
    assert linda["father_pig_id"] is None
    assert linda["historical_mating_date"] is None


def test_group_is_all_or_nothing_and_clearance_requires_fresh_bcs_three():
    partial = build_grouped_preview({"rows": [
        {"pig_id": "SOW-1", "action": "exposure", "boar_pig_id": "",
         "exposure_started_on": "2026-08-12", "planned_removal_on": "2026-08-28"},
        {"pig_id": "SOW-2", "action": "recovery_clearance", "body_condition_score": 2,
         "observed_at": "2026-08-12T08:00:00+02:00", "factual_note": "Still lean."},
    ]}, evidence_generation="GEN-1")
    assert partial["success"] is False
    assert partial["writes_performed"] is False
    assert "row_1_exact_exposure_required" in partial["errors"]
    assert "row_2_clearance_requires_bcs_3_or_higher" in partial["errors"]


def _loop(projected, exposures=None):
    female = {"pig_id":"SOW-1","tag_number":"Ms Piggy","sex":"Female","animal_type":"Sow",
              "status":"Active","on_farm":"Yes","purpose":"Breeding","medical_status":"Clear",
              "withdrawal_evidence_state":"cleared","available_for_breeding":"available"}
    boar = {"pig_id":"BOAR-1","tag_number":"Bola","sex":"Male","animal_type":"Boar",
            "status":"Active","on_farm":"Yes","purpose":"Breeding","medical_status":"Clear",
            "withdrawal_evidence_state":"cleared","available_for_breeding":"available"}
    return build_breeding_operating_loop(
        {"success":True,"animals":[{"pig_id":"SOW-1","tag_number":"Ms Piggy","missing_facts":[],"conflicting_facts":[]}]},
        readiness={"success":True,"pigs":[female,boar]}, matings=[],
        litters=[{"litter_id":"LIT-1","sow_pig_id":"SOW-1","farrowing_date":"2026-06-18","wean_date":"2026-07-27","litter_status":"Weaned"}],
        observations=[], projected_observations={"SOW-1":projected},
        exposures=exposures or [],
        family_trees={"success":True,"by_pig":{}}, today=date(2026,8,12),
        generated_at="2026-08-12T08:00:00+00:00")


def test_active_hold_excludes_actionable_and_time_does_not_clear_it():
    result = _loop({"body_condition_score": 3, "recovery_hold":"active",
                    "recovery_hold_observed_at":"2026-07-28T10:00:00+00:00"})
    case = result["cases"][0]["classification"]
    assert case["state"] == "Recovery hold"
    assert case["readiness"] == "Hold"
    assert case["proposed_placement_date"] is None


def test_explicit_clearance_releases_hold_but_does_not_create_mating():
    result = _loop({"body_condition_score": 3, "recovery_hold":"cleared",
                    "recovery_hold_observed_at":"2026-08-12T06:00:00+00:00"})
    case = result["cases"][0]["classification"]
    assert case["state"] == "Ready for mating review"
    assert result["mating_execution_enabled"] is False


def test_near_farrowing_excludes_new_boar_without_inventing_cycle():
    result = _loop({"near_farrowing":"observed", "near_farrowing_observed_at":"2026-08-12T06:00:00+00:00"})
    case = result["cases"][0]["classification"]
    assert case["state"] == "Near farrowing observation"
    assert case["latest_mating_id"] is None
    assert case["expected_farrowing"] is None
    assert case["proposed_placement_date"] is None


def test_active_exposure_refreshes_worklist_without_inventing_service():
    result = _loop({}, exposures=[{
        "exposure_event_id": "EXP-EVT-1",
        "exposure_identity": "EXP-1",
        "event_kind": "started",
        "sow_pig_id": "SOW-1",
        "boar_pig_id": "BOAR-1",
        "occurred_on": "2026-08-12",
        "planned_removal_on": "2026-08-28",
    }])
    case = result["cases"][0]["classification"]
    assert case["state"] == "Boar exposure active"
    assert case["readiness"] == "Hold"
    assert case["active_exposure"]["boar_pig_id"] == "BOAR-1"
    assert case["active_exposure"]["asserts_service_date"] is False
    assert case["latest_mating_id"] is None
    assert case["proposed_placement_date"] is None


def test_removed_exposure_no_longer_blocks_recommendation_refresh():
    result = _loop({}, exposures=[
        {"exposure_event_id":"EXP-EVT-1","exposure_identity":"EXP-1","event_kind":"started",
         "sow_pig_id":"SOW-1","boar_pig_id":"BOAR-1","occurred_on":"2026-07-20",
         "planned_removal_on":"2026-08-05"},
        {"exposure_event_id":"EXP-EVT-2","exposure_identity":"EXP-1","event_kind":"removed",
         "sow_pig_id":"SOW-1","boar_pig_id":"BOAR-1","occurred_on":"2026-08-05",
         "planned_removal_on":None},
    ])
    case = result["cases"][0]["classification"]
    assert case["state"] == "Ready for mating review"
    assert case["active_exposure"] is None


def test_litter_validation_accepts_unknown_father_and_no_mating_id():
    validation = validate_new_litter_payload({"mother_pig_id":"SOW-1", "father_pig_id":"",
        "mating_id":"", "farrowing_date":"2026-08-20", "total_born":8, "born_alive":8})
    assert validation["is_valid"] is True
    assert validation["cleaned_data"]["father_pig_id"] == ""
    assert validation["cleaned_data"]["mating_id"] == ""


def test_exposure_migration_is_append_only_and_not_a_mating_ledger():
    sql = Path("supabase/migrations/202608120001_create_breeding_exposure_events.sql").read_text()
    assert "pig_breeding_exposure_events" in sql
    assert "event_kind in ('started','removed')" in sql
    assert "grant select, insert" in sql
    assert "grant update" not in sql
    assert "mating_date" not in sql
    assert "expected_farrowing" not in sql
