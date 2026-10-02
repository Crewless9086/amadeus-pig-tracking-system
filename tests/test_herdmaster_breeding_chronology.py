"""Production-shaped read-only breeding chronology reconciliation."""
from copy import deepcopy
from datetime import date

import pytest

from modules.pig_weights.herdmaster_breeding_operating_loop import build_breeding_operating_loop
from modules.pig_weights.herdmaster_breeding_attention_service import build_breeding_attention
from modules.oom_sakkie.herdmaster_request_runtime import render_breeding_plan


TODAY = date(2026, 9, 29)
LITTER = {"litter_id": "LITTER-CURRENT", "sow_pig_id": "SOW-ONE",
          "farrowing_date": "2026-08-22", "wean_date": None,
          "weaned_count": None, "litter_status": "Active"}
FEMALE = {"pig_id": "SOW-ONE", "tag_number": "Sow One", "sex": "Female",
          "animal_type": "Sow", "status": "Active", "on_farm": "Yes",
          "purpose": "Breeding", "medical_status": "Clear",
          "withdrawal_evidence_state": "cleared", "available_for_breeding": "available"}


def loop(observed_at="2026-08-12T11:41:25+00:00", *, litters=None, projected=None,
         female=None, exposures=None, today=TODAY, generated_at="2026-09-29T18:00:00+00:00"):
    projection = {"near_farrowing": "observed", "near_farrowing_observed_at": observed_at,
                  "near_farrowing_observation_event_id": "OBSERVATION-ONE",
                  "body_condition_score": 3}
    projection.update(projected or {})
    rows = deepcopy([LITTER] if litters is None else litters)
    before = deepcopy(rows)
    result = build_breeding_operating_loop(
        {"success": True, "animals": [{"pig_id": "SOW-ONE", "tag_number": "Sow One"}]},
        readiness={"success": True, "pigs": [female or FEMALE]},
        matings=[], litters=rows, observations=[],
        projected_observations={"SOW-ONE": projection}, exposures=exposures or [],
        family_trees={"success": True, "by_pig": {}}, today=today,
        generated_at=generated_at)
    assert rows == before
    assert result["writes_performed"] is False
    assert result["mating_execution_enabled"] is False
    return result


def case(result):
    return result["cases"][0]["classification"]


def test_prebirth_observation_becomes_historical_after_same_sow_canonical_birth():
    result = loop()
    row = case(result)
    assert row["state"] == "Nursing"
    assert row["near_farrowing"] == "observed"  # retain the actual recorded fact
    assert row["near_farrowing_evidence"]["state"] == "historical_birth"
    assert row["near_farrowing_evidence"]["observation_event_id"] == "OBSERVATION-ONE"
    assert row["near_farrowing_evidence"]["observed_at"] == "2026-08-12T11:41:25+00:00"
    assert row["latest_mating_id"] is None and row["expected_farrowing"] is None
    assert row["proposed_placement_date"] is None
    assert "prepare and monitor" not in render_breeding_plan(result)[0]
    assert "Still nursing; wait for recorded weaning" in render_breeding_plan(result)[0]


@pytest.mark.parametrize("when", [
    "2026-08-22", "2026-08-22T00:01:00+02:00",  # birth has only date precision
    "2026-08-21T23:30:00Z",  # already birth day on the farm
    "2026-08-23T09:00:00Z", None, "not a date", "2026-08-12T11:00:00",
    "2026-09-30T09:00:00Z", "2026-09-29T19:00:00Z",  # future day / instant
])
def test_unresolved_observation_order_cannot_assert_pregnancy_or_placement(when):
    result = loop(when)
    row = case(result)
    assert row["state"] == "Needs Data"
    assert row["near_farrowing_evidence"]["state"] == "unresolved"
    assert row["near_farrowing_evidence"]["reason"] in row["conflicting"]
    assert row["proposed_placement_date"] is None and row["weaning_date"] is None
    assert row["latest_mating_id"] is None and row["expected_farrowing"] is None
    assert result["cases"][0]["male_recommendation"]["recommended"] is None
    assert "attributable farrowing observation chronology" in result["tasks"][0]["required_checks"]
    assert "prepare and monitor" not in render_breeding_plan(result)[0]


def test_another_sows_litter_cannot_retire_this_sows_observation():
    row = case(loop(litters=[{**LITTER, "sow_pig_id": "OTHER-SOW"}]))
    assert row["state"] == "Near farrowing observation"
    assert row["near_farrowing_evidence"]["litter_id"] is None


def test_observation_after_older_completed_cycle_remains_current_without_invented_mating():
    old = {**LITTER, "farrowing_date": "2026-06-18", "wean_date": "2026-07-27",
           "litter_status": "Weaned", "weaned_count": 8}
    row = case(loop(litters=[old]))
    assert row["state"] == "Near farrowing observation"
    assert row["near_farrowing_evidence"]["state"] == "active"
    assert row["proposed_placement_date"] is None and row["latest_mating_id"] is None


@pytest.mark.parametrize("updates", [
    {"litter_id": None}, {"farrowing_date": None}, {"farrowing_date": "bad"},
    {"farrowing_date": "2026-10-01"},
])
def test_missing_or_invalid_attributable_litter_chronology_stays_unknown(updates):
    row = case(loop(litters=[{**LITTER, **updates}]))
    assert row["state"] == "Needs Data" and row["proposed_placement_date"] is None
    assert row["near_farrowing_evidence"]["state"] == "unresolved"


@pytest.mark.parametrize("observed_at", ["2026-08-12T11:41:25Z", "2026-08-22T10:00:00Z"])
@pytest.mark.parametrize("projection, expected", [
    ({"recovery_hold": "active"}, "Recovery hold"),
    ({"body_condition_score": 2}, "Body condition recovery"),
])
def test_reconciliation_never_releases_a_current_recovery_or_condition_hold(observed_at, projection, expected):
    row = case(loop(observed_at, projected=projection))
    assert row["state"] == expected and row["proposed_placement_date"] is None


def test_current_medical_hold_keeps_priority_over_chronology_conflict():
    row = case(loop("2026-08-22", female={**FEMALE, "medical_status": "Hold"}))
    assert row["state"] == "Hold for medical/withdrawal evidence"
    assert row["near_farrowing_evidence"]["reason"] in row["conflicting"]
    assert row["proposed_placement_date"] is None


@pytest.mark.parametrize("count", [None, 4])
def test_past_planned_weaning_or_partial_count_does_not_complete_an_active_litter(count):
    row = case(loop(litters=[{**LITTER, "wean_date": "2026-09-11", "weaned_count": count}]))
    assert row["state"] == "Nursing"
    assert row["weaning_evidence"]["state"] == "not_completed"
    assert row["weaning_evidence"]["planned_wean_date"] == "2026-09-11"
    assert row["weaning_evidence"]["weaned_count"] is count
    assert row["weaning_date"] is None and row["days_since_weaning"] is None
    assert row["proposed_placement_date"] is None


@pytest.mark.parametrize("wean_date", [None, "invalid", "2026-08-21", "2026-10-01"])
def test_terminal_litter_without_valid_actual_weaning_date_cannot_start_a_placement_clock(wean_date):
    row = case(loop(litters=[{**LITTER, "litter_status": "Weaned", "wean_date": wean_date}]))
    assert row["state"] == "Needs Data"
    assert row["weaning_evidence"]["state"] == "unresolved"
    assert row["weaning_evidence"]["reason"] in row["conflicting"]
    assert row["proposed_placement_date"] is None


def test_completed_litter_with_actual_weaning_preserves_the_existing_review_clock():
    row = case(loop(litters=[{**LITTER, "litter_status": "Completed", "wean_date": "2026-09-21", "weaned_count": 8}]))
    assert row["state"] == "Ready for mating review"
    assert row["near_farrowing_evidence"]["state"] == "historical_birth"
    assert row["weaning_date"] == "2026-09-21" and row["days_since_weaning"] == 8
    assert row["proposed_placement_date"] == "2026-09-29"


@pytest.mark.parametrize("status, wean, expected", [
    ("Active", "2026-09-11", "Post-litter recovery"),
    ("Weaned", "2026-09-11", "Ready for review"),
    ("Weaned", None, "Needs Data"),
    ("Weaned", "2026-10-01", "Needs Data"),
])
def test_attention_and_operating_loop_share_governed_weaning_semantics(status, wean, expected):
    result = build_breeding_attention(
        {"success": True, "pigs": [FEMALE], "generated_date": TODAY.isoformat()},
        matings={"success": True, "records": []},
        litters={"success": True, "litters": [{**LITTER, "litter_status": status, "wean_date": wean}]},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {"SOW-ONE": {"mother": {"pig_id": "DAM"}, "father": {"pig_id": "SIRE"}}}},
        observations={"success": True, "by_pig": {}}, today=TODAY)
    row = result["animals"][0]
    assert row["current_state"] == expected
    assert row["weaning_date"] == (wean if expected == "Ready for review" else None)
    assert result["writes_performed"] is False


def test_owner_breeding_reason_uses_word_boundaries_and_escapes_markup():
    reason = "<unknown> " + "attributable " * 14
    answer, _ = render_breeding_plan({"tasks": [{"tag_number": "Sow One", "task_group": "review evidence", "why": reason}]})
    assert "&lt;unknown&gt;" in answer and "<unknown>" not in answer
    why_line = next(line for line in answer.splitlines() if "&lt;unknown&gt;" in line)
    source_note = why_line.split("Source note: ", 1)[1].split(" Complete placement evidence", 1)[0]
    assert source_note.rstrip().endswith("attributable.")
    assert "Complete placement evidence is unavailable." in why_line
    assert "attribu." not in why_line


def test_unattributed_completed_litter_cannot_start_the_placement_clock_without_a_near_farrow_flag():
    row = case(loop(litters=[{**LITTER, "litter_id": "", "litter_status": "Weaned", "wean_date": "2026-09-11"}],
                    projected={"near_farrowing": "unknown"}))
    assert row["state"] == "Needs Data"
    assert row["weaning_evidence"]["state"] == "unresolved"
    assert row["proposed_placement_date"] is None


def test_default_business_day_uses_farm_timezone_at_utc_midnight_boundary():
    result = loop("2026-09-29T22:10:00Z", litters=[], today=None,
                  generated_at="2026-09-29T22:30:00Z")
    row = case(result)
    assert row["state"] == "Near farrowing observation"
    assert row["near_farrowing_evidence"]["observed_local_date"] == "2026-09-30"
    assert row["near_farrowing_evidence"]["state"] == "active"


def test_explicit_business_day_is_preserved_for_historical_qualification():
    row = case(loop("2026-09-29T22:10:00Z", litters=[], today=TODAY,
                    generated_at="2026-09-29T22:30:00Z"))
    assert row["near_farrowing_evidence"]["state"] == "unresolved"


def test_same_day_completed_weaning_and_observation_retain_date_precision_uncertainty():
    row = case(loop("2026-09-21T10:00:00Z", litters=[{**LITTER, "litter_status": "Weaned", "wean_date": "2026-09-21"}]))
    assert row["state"] == "Needs Data"
    assert row["weaning_evidence"]["state"] == "completed"
    assert "uncompleted" not in row["near_farrowing_evidence"]["reason"]
    assert row["proposed_placement_date"] is None
