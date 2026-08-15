from copy import deepcopy

import pytest

from modules.pig_weights.herdmaster_whole_herd_packet import build_whole_herd_packet


def canonical():
    return {"success": True, "writes_performed": False,
        "evidence_generation": "2026-08-03T06:00:00+02:00",
        "evidence_identity": "HERD-CANONICAL-20260803-A"}


def active(pig_id, tag, card):
    return {"pig_id": pig_id, "tag_number": tag, "lifecycle_id": f"LIFE-{pig_id}",
        "state": "waiting_for_confirmation", "specialist_owner": "Oom Sakkie",
        "current_evidence": ["Existing authenticated lifecycle is active."],
        "existing_question_or_card_id": card,
        "reassessment_trigger": "authenticated reply or exact confirmation on the existing card"}


def reproductive(pig_id, tag, status):
    base = {"pig_id": pig_id, "tag_number": tag, "operational_status": status,
        "current_evidence": [f"Attributable owner observation: {status}."],
        "observed_at": "2026-08-01T08:09:01+02:00", "source_identity": f"OWNER-{pig_id}",
        "smallest_next_observation": "Current appetite, comfort and any return to heat or labour sign.",
        "clinical_confirmation": "Optional higher-confidence fact; not clinically confirmed.",
        "current_applicability": status == "Assumed Pregnant"}
    if status == "Assumed Pregnant":
        base.update(mating_id=f"MAT-{pig_id}", mating_date="2026-05-02",
            observed_signs="belly dropping and teat growth",
            projected_farrowing_range={"start": "2026-08-22", "end": "2026-08-26", "uncertainty": "approximately 114 +/- 2 days"},
            preparation_window={"start": "2026-08-08", "end": "2026-08-15", "uncertainty": "prepare proportionally"},
            change_triggers=["return to heat", "illness", "early labour", "farrowing"],
            prohibited_without_more_evidence=["clinical-confirmation claim", "mating", "movement", "farm write"])
    return base


def full_packet():
    return build_whole_herd_packet(canonical(),
        active_lifecycles=[
            active("PIG-2026-E88A", "Pig 11", "3171"),
            active("PIG-2026-BCEB", "Pig 125", "3184"),
            active("PIG-2026-127X", "Pig 127", "ACTIVE-127"),
        ],
        monday_weighing_candidates=[
            {"pig_id": "PIG-W41", "tag_number": "41", "why_now": "Current weight is stale for readiness review.",
             "latest_weight_kg": 18.2, "latest_weight_date": "2026-07-01", "source_identity": "WEIGHT-41"},
            {"pig_id": "PIG-W52", "tag_number": "52", "why_now": "No current decision-bearing weight.",
             "latest_weight_kg": None, "latest_weight_date": None, "source_identity": "WEIGHT-52"},
        ],
        reproductive_reviews=[
            reproductive("PIG-2026-D050", "Mona", "Assumed Pregnant"),
            reproductive("PIG-2026-21BE", "Mysikind", "Assumed Pregnant"),
            reproductive("PIG-2026-7DAA", "Baby", "Inconclusive"),
        ],
        breeding_reviews=[{
            "pig_id": "PIG-BONNIE", "tag_number": "Bonnie", "classification": "needs_data",
            "current_evidence": ["Canonical identity known; present readiness not proven."],
            "readiness_evidence_complete": False, "smallest_missing_observation": "Current heat signs and body condition.",
            "compatible_males": [], "source_identity": "BREED-BONNIE",
        }],
        data_quality_matters=[{
            "pig_id": "PIG-2026-EEAC", "tag_number": "Zigay", "status": "unresolved",
            "current_evidence": ["Duplicate-litter correction remains contained."],
            "smallest_missing_evidence": "Governed supersession consumer resolution.", "source_identity": "DQ-ZIGAY",
        }])


def test_whole_herd_round_preserves_active_cases_and_publishes_only_three_new_actions():
    result = full_packet()
    assert [row["pig_id"] for row in result["protected_active_lifecycles"]] == [
        "PIG-2026-127X", "PIG-2026-BCEB", "PIG-2026-E88A"]
    assert all(row["question_suppressed"] and not row["new_case_created"] for row in result["protected_active_lifecycles"])
    assert [row["pig_id"] for row in result["ranked_new_actions"]] == [
        "PIG-2026-21BE", "PIG-2026-D050", "HERD-MONDAY-WEIGHTS"]
    assert result["ranked_new_action_count"] == 3
    assert "3171" not in result["owner_text"] or "do not ask again" in result["owner_text"]
    assert "projected farrowing approximately 2026-08-22 to 2026-08-26" in result["owner_text"]
    assert "prepare approximately 2026-08-08 to 2026-08-15" in result["owner_text"]


def test_mona_and_mysikind_retain_attributable_assumed_pregnant_planning_and_baby_inconclusive():
    result = full_packet()
    reviews = {row["pig_id"]: row for row in result["reproductive_reviews"]}
    for pig_id in ("PIG-2026-D050", "PIG-2026-21BE"):
        row = reviews[pig_id]
        assert row["operational_status"] == "Assumed Pregnant"
        assert row["mating_date"] == "2026-05-02"
        assert row["observed_signs"] == "belly dropping and teat growth"
        assert row["projected_farrowing_range"]["start"] == "2026-08-22"
        assert row["projected_farrowing_range"]["end"] == "2026-08-26"
        assert row["preparation_window"]["start"] == "2026-08-08"
        assert row["preparation_window"]["end"] == "2026-08-15"
        assert "not clinically confirmed" in row["clinical_confirmation"]
    assert reviews["PIG-2026-7DAA"]["operational_status"] == "Inconclusive"
    assert reviews["PIG-2026-7DAA"]["current_applicability"] is False


def test_monday_bulk_weight_journey_is_one_natural_request_with_governed_preview_confirmation_and_replay():
    journey = full_packet()["monday_weighing_journey"]
    assert journey["candidate_count"] == 2
    assert "one message" in journey["single_family_request"]
    assert "41 (PIG-W41)" in journey["single_family_request"]
    assert "52 (PIG-W52)" in journey["single_family_request"]
    assert journey["preview_contract"]["one_consolidated_before_after_preview"] is True
    assert journey["preview_contract"]["confirmation_bound_to_preview_hash_and_evidence_generation"] is True
    assert journey["preview_contract"]["replay_additional_fact_count"] == 0
    assert journey["preview_contract"]["future_persistence"] == "existing_governed_conversational_weight_writer_only"


def test_active_lifecycle_candidate_is_suppressed_from_weighing_and_overlap_fails_closed_elsewhere():
    result = build_whole_herd_packet(canonical(),
        active_lifecycles=[active("PIG-1", "1", "CARD-1")],
        monday_weighing_candidates=[{"pig_id": "PIG-1", "tag_number": "1", "why_now": "Stale weight",
            "source_identity": "WEIGHT-1"}])
    assert result["monday_weighing_journey"]["candidate_count"] == 0
    with pytest.raises(ValueError, match="active_lifecycle_reproductive_overlap"):
        build_whole_herd_packet(canonical(), active_lifecycles=[active("PIG-1", "1", "CARD-1")],
            reproductive_reviews=[reproductive("PIG-1", "1", "Inconclusive")])


def test_attributable_reproductive_observations_are_required_and_future_evidence_fails_closed():
    base = reproductive("PIG-1", "One", "Assumed Pregnant")
    for changed, reason in (
        ({**base, "source_identity": ""}, "reproductive_source"),
        ({**base, "observed_signs": ""}, "observed_signs"),
        ({**base, "observed_at": "2026-08-04T00:00:00+02:00"}, "future_dated"),
    ):
        with pytest.raises(ValueError, match=reason):
            build_whole_herd_packet(canonical(), reproductive_reviews=[changed])


def test_breeding_male_is_never_recommended_without_complete_readiness_evidence():
    unsupported = {"pig_id": "PIG-F", "tag_number": "Female", "classification": "needs_data",
        "current_evidence": [], "readiness_evidence_complete": False,
        "smallest_missing_observation": "Current heat signs and condition.", "source_identity": "BREED-F",
        "compatible_males": [{"pig_id": "PIG-M", "tag_number": "Male",
            "compatibility_evidence": "No close shared ancestor proven.", "performance_reason": "Growth evidence."}]}
    with pytest.raises(ValueError, match="unsupported_male_recommendation"):
        build_whole_herd_packet(canonical(), breeding_reviews=[unsupported])

    supported = {**unsupported, "classification": "conditionally_ready_after_inspection",
        "readiness_evidence_complete": True}
    result = build_whole_herd_packet(canonical(), breeding_reviews=[supported])
    male = result["breeding_reviews"][0]["conditional_male_shortlist"][0]
    assert male["actionable_mating_recommendation"] is False
    assert result["breeding_reviews"][0]["requires_owner_confirmed_mating_preview"] is True
    assert result["breeding_reviews"][0]["mating_authority"] is False


def test_replay_is_deterministic_and_all_write_send_authority_is_zero():
    first = full_packet()
    replay = full_packet()
    assert first["packet_identity"] == replay["packet_identity"]
    assert first["deduplication_key"] == replay["deduplication_key"]
    for key in ("writes_farm_data", "sends_telegram", "creates_owner_question", "creates_mating",
                "changes_pregnancy", "changes_lifecycle", "changes_movement", "changes_health",
                "changes_availability", "publication_execution_authority"):
        assert first[key] is False
    assert first["zero_io"] is True
    changed = deepcopy(canonical())
    changed["evidence_identity"] = "HERD-CANONICAL-20260803-B"
    assert build_whole_herd_packet(changed)["packet_identity"] != build_whole_herd_packet(canonical())["packet_identity"]


@pytest.mark.parametrize("mutation", [
    {"success": False}, {"writes_performed": True}, {"evidence_generation": "not-a-time"},
])
def test_noncanonical_or_write_capable_evidence_fails_closed(mutation):
    with pytest.raises(ValueError):
        build_whole_herd_packet({**canonical(), **mutation})
