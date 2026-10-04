from datetime import date

from modules.pig_weights.herdmaster_breeding_exposure_recovery import (
    build_grouped_preview,
    exposure_cycle_window,
    planned_exposure_removal_on,
    build_active_cycle_correction_preview,
)
from modules.pig_weights.herdmaster_breeding_operating_loop import build_breeding_operating_loop
from modules.pig_weights.pig_weights_validation import validate_new_litter_payload
from pathlib import Path


def test_shared_channel_invariant_inclusive_removal_date():
    assert planned_exposure_removal_on("2026-08-12", 17) == "2026-08-28"


def test_removal_preview_uses_windows_without_exact_service_or_conception():
    result = build_grouped_preview({"rows": [{
        "pig_id":"SOW-1","label":"Sophie","action":"exposure_removal",
        "boar_pig_id":"BOAR-1","exposure_identity":"EXP-1",
        "exposure_group_identity":"GROUP-1","exposure_started_on":"2026-08-12",
        "actual_removed_on":"2026-08-28",
    }]}, evidence_generation="GEN-REMOVAL")
    assert result["success"] is True
    row=result["preview"]["rows"][0]
    assert exposure_cycle_window("2026-08-12","2026-08-28") == {
        "service_window_start":"2026-08-12","service_window_end":"2026-08-28",
        "expected_farrowing_window_start":"2026-12-04",
        "expected_farrowing_window_end":"2026-12-20",
        "service_date_basis":"exposure_window_estimate","exact_service_date":None}
    assert row["exact_service_date"] is None
    assert result["creates_breeding_cycle"] is True
    assert result["asserts_service_date"] is False


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
    assert result["preview"]["exposure_group_identity"].startswith("HERD-EXPOSURE-GROUP-")
    assert result["preview"]["rows"][0]["exposure_group_identity"] == result["preview"]["exposure_group_identity"]
    assert result["creates_mating"] is False
    assert result["asserts_service_date"] is False
    linda = result["preview"]["rows"][2]
    assert linda["father_pig_id"] is None
    assert linda["historical_mating_date"] is None


def test_grouped_placement_deduplicates_shared_boar_movement():
    result=build_grouped_preview({"rows":[
        {"pig_id":"SOW-1","label":"Olive","action":"exposure","boar_pig_id":"BOAR-1",
         "exposure_started_on":"2026-08-12","planned_removal_on":"2026-08-28",
         "placement_pen_id":"PEN-4","placement_pen_name":"Kraam Saal 04",
         "sow_current_pen_id":"D3","boar_current_pen_id":"D4"},
        {"pig_id":"SOW-2","label":"Lucy","action":"exposure","boar_pig_id":"BOAR-1",
         "exposure_started_on":"2026-08-12","planned_removal_on":"2026-08-28",
         "placement_pen_id":"PEN-4","placement_pen_name":"Kraam Saal 04",
         "sow_current_pen_id":"D3","boar_current_pen_id":"D4"}]},evidence_generation="GEN-MOVE")
    assert result["success"] is True
    assert result["creates_movement"] is True
    assert len(result["preview"]["movements"]) == 3
    assert [row["pig_id"] for row in result["preview"]["movements"]].count("BOAR-1") == 1
    assert result["asserts_service_date"] is False


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


def test_removed_exposure_restores_review_but_missing_condition_still_blocks():
    result = _loop({}, exposures=[
        {"exposure_event_id":"EXP-EVT-1","exposure_identity":"EXP-1","event_kind":"started",
         "sow_pig_id":"SOW-1","boar_pig_id":"BOAR-1","occurred_on":"2026-07-20",
         "planned_removal_on":"2026-08-05"},
        {"exposure_event_id":"EXP-EVT-2","exposure_identity":"EXP-1","event_kind":"removed",
         "sow_pig_id":"SOW-1","boar_pig_id":"BOAR-1","occurred_on":"2026-08-05",
         "planned_removal_on":None},
    ])
    case = result["cases"][0]["classification"]
    assert case["state"] == "Needs current condition"
    assert case["active_exposure"] is None
    assert case["proposed_placement_date"] is None


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


def test_cycle_window_migration_extends_canonical_mating_without_exact_date():
    sql=Path("supabase/migrations/202608120004_add_exposure_breeding_cycle_windows.sql").read_text()
    assert "alter table public.mating_events" in sql
    assert "source_exposure_identity" in sql
    assert "mating_date is null" in sql
    assert "expected_farrowing_date is null" in sql
    assert "expected_farrowing_window_start = service_window_start + 114" in sql


def test_existing_exposure_cycle_correction_preview_is_exact_and_unknown_safe():
    rows=[{"exposure_identity":f"EXP-{i}","sow_pig_id":f"SOW-{i}","boar_pig_id":"BOAR-1",
           "occurred_on":"2026-08-12","planned_removal_on":"2026-08-28"} for i in range(5)]
    result=build_active_cycle_correction_preview(rows,exposure_group_identity="GROUP-1")
    assert result["success"] is True
    assert {row["state"] for row in result["preview"]["rows"]} == {"Exposure Active"}
    assert {row["expected_farrowing_window_start"] for row in result["preview"]["rows"]} == {"2026-12-04"}
    assert {row["expected_farrowing_window_end"] for row in result["preview"]["rows"]} == {"2026-12-20"}
    assert all(row["exact_service_date"] is row["conception"] is row["pregnancy"] is None for row in result["preview"]["rows"])


import copy
import pytest
from datetime import datetime, timezone
from modules.pig_weights.herdmaster_breeding_exposure_recovery import execute_grouped_preview, observation_time


def _condition_preview(**facts):
    return build_grouped_preview({'rows':[{'pig_id':'SOW-T','label':'Teena','action':'condition_observation',
        'body_condition_score':3,'observed_on':'2026-10-03','factual_note':'Owner reports BCS 3.',**facts}]},
        evidence_generation='SOURCE-1',reported_at='2026-10-03T10:00:00Z')


def test_plain_condition_is_not_a_hold_or_clearance_and_does_not_make_other_effects():
    result=_condition_preview()
    assert result['success'] and not result['creates_movement'] and not result['creates_breeding_cycle']
    assert not result['asserts_service_date'] and not result['asserts_pregnancy']
    assert result['preview']['rows'][0]['action']=='condition_observation'
    assert result['preview']['movements']==[]


@pytest.mark.parametrize('value',[1,2,2.5,3,4,5])
def test_observation_accepts_finite_full_bcs_scale_without_hold_policy(value):
    result=_condition_preview(body_condition_score=value)
    assert result['success'] and result['preview']['rows'][0]['body_condition_score']==value


def test_date_precision_uses_farm_day_and_deterministic_storage_not_physical_clock():
    timed=observation_time('2026-10-03',reported_at='2026-10-02T22:01:00Z')
    assert timed=={'observed_at':'2026-10-02T22:00:00+00:00','observation_date':'2026-10-03',
        'observation_precision':'date','observation_timezone':'Africa/Johannesburg'}
    with pytest.raises(ValueError,match='future'):
        observation_time('2026-10-03',reported_at='2026-10-02T21:59:00Z')
    with pytest.raises(ValueError,match='conflict'):
        observation_time('2026-10-02T22:01:00Z',observed_on='2026-10-02')


@pytest.mark.parametrize('field,value',[('body_condition_score',4),('observed_at','2026-10-03T10:00:00Z'),
    ('observation_precision','instant'),('observation_date','2026-10-02'),('pig_id','OTHER'),('action','recovery_clearance')])
def test_condition_confirmation_tamper_is_rejected_without_connect(field,value):
    preview=_condition_preview();preview['preview']['rows'][0][field]=value
    result,status=execute_grouped_preview(preview,confirmed_preview_sha256=preview['preview_sha256'],actor_id='owner',
        connect_factory=lambda:pytest.fail('must not connect'))
    assert status==409 and result['rows_changed']==0


def test_condition_reconstructed_invalid_precision_is_rejected_without_connect():
    import hashlib,json
    from modules.pig_weights.herdmaster_breeding_exposure_recovery import _stable
    preview=_condition_preview();preview['preview']['rows'][0]['observed_at']='2026-10-03T10:00:00+00:00'
    digest=hashlib.sha256(json.dumps(preview['preview'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    preview.update(preview_sha256=digest,operation_id=_stable('HERD-BREED-GROUP-',digest))
    result,status=execute_grouped_preview(preview,confirmed_preview_sha256=digest,actor_id='owner',
        connect_factory=lambda:pytest.fail('must not connect'))
    assert status==409 and result['status']=='corrected_observation_preview_required'


@pytest.mark.parametrize('field,value',[('boar_pig_id','B1'),('placement_pen_id','P1'),
    ('recovery_hold_action','cleared'),('supersedes_observation_event_id','HOLD-1'),('planned_days',17)])
def test_condition_cannot_smuggle_hold_exposure_or_movement_fields(field,value):
    assert not _condition_preview(**{field:value})['success']
    import hashlib,json
    from modules.pig_weights.herdmaster_breeding_exposure_recovery import _stable
    preview=_condition_preview();preview['preview']['rows'][0][field]=value
    digest=hashlib.sha256(json.dumps(preview['preview'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    preview.update(preview_sha256=digest,operation_id=_stable('HERD-BREED-GROUP-',digest))
    result,status=execute_grouped_preview(preview,confirmed_preview_sha256=digest,actor_id='owner',
        connect_factory=lambda:pytest.fail('must not connect'))
    assert status==409 and result['status']=='corrected_observation_preview_required'


def test_condition_only_cannot_hide_a_foreign_pig_movement_in_resealed_preview():
    import hashlib,json
    from modules.pig_weights.herdmaster_breeding_exposure_recovery import _stable
    preview=_condition_preview()
    preview['preview']['movements']=[{'pig_id':'OTHER','from_pen_id':'A','to_pen_id':'B',
                                      'to_pen_name':'B','move_date':'2026-10-03'}]
    digest=hashlib.sha256(json.dumps(preview['preview'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    preview.update(preview_sha256=digest,operation_id=_stable('HERD-BREED-GROUP-',digest))
    result,status=execute_grouped_preview(preview,confirmed_preview_sha256=digest,actor_id='owner',
        connect_factory=lambda:pytest.fail('must not connect'))
    assert status==409 and result['status']=='corrected_observation_preview_required'


def test_mixed_exposure_and_condition_keeps_only_producer_bound_movements():
    condition=_condition_preview()['preview']['rows'][0]
    # Preserve date precision while passing the original supplied facts to builder.
    condition['observed_at']=condition['observation_date']
    exposure={'pig_id':'OTHER-SOW','label':'Mona','action':'exposure','boar_pig_id':'BOAR-1',
        'exposure_started_on':'2026-10-03','planned_removal_on':'2026-10-19',
        'placement_pen_id':'PEN-B','placement_pen_name':'Pen B',
        'sow_current_pen_id':'PEN-A','boar_current_pen_id':'PEN-C'}
    preview=build_grouped_preview({'rows':[condition,exposure]},evidence_generation='MIXED',
                                 reported_at='2026-10-03T10:00:00Z')
    assert preview['success']
    assert {row['pig_id'] for row in preview['preview']['movements']}=={'OTHER-SOW','BOAR-1'}
    class ReachedCanonicalStore(Exception): pass
    def connect(): raise ReachedCanonicalStore()
    # All pre-transaction exact-effect checks pass; canonical DB guards follow.
    with pytest.raises(ReachedCanonicalStore):
        execute_grouped_preview(preview,confirmed_preview_sha256=preview['preview_sha256'],
                               actor_id='owner',connect_factory=connect)
