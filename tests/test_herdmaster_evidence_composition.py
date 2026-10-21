from datetime import date
import unittest

from modules.oom_sakkie.herd_evidence_composition import (
    SUPPORTED_QUESTION_CATEGORIES,
    compose_herd_evidence_answer,
)


TODAY = date(2026, 7, 30)
ANIMALS = [
    {
        "pig_id": "PIG-SHUPE",
        "tag_number": "Shupe",
        "sex": "Female",
        "status": "Active",
        "on_farm": "Yes",
        "available": "Yes",
        "purpose": "Breeding",
        "current_pen_id": "PEN-3",
        "state_date": "2026-07-29",
    },
    {
        "pig_id": "PIG-BOAR",
        "tag_number": "Prince",
        "sex": "Male",
        "status": "Active",
        "on_farm": "Yes",
        "available": "Unknown",
        "purpose": "Breeding",
        "current_pen_id": "PEN-8",
    },
]
WEIGHTS = {
    "PIG-SHUPE": {"history": [
        {
            "pig_id": "PIG-SHUPE",
            "weight_date_display": "2026-07-20",
            "weight_kg": 72.2,
        },
        {
            "pig_id": "PIG-SHUPE",
            "weight_date_display": "2026-06-01",
            "weight_kg": 68.0,
        },
    ]}
}
MOVEMENTS = {
    "PIG-SHUPE": {"history": [
        {
            "pig_id": "PIG-SHUPE",
            "move_date_display": "2026-07-15",
            "from_pen_id": "PEN-1",
            "to_pen_id": "PEN-3",
            "reason_for_move": "Breeding group",
        }
    ]}
}
MATINGS = [{
    "mating_id": "MAT-1",
    "sow_pig_id": "PIG-SHUPE",
    "boar_pig_id": "PIG-BOAR",
    "mating_date": "2026-07-01",
    "mating_status": "Open",
    "pregnancy_check_result": "Pregnant",
    "pregnancy_check_date": "2026-07-20",
}]
LITTERS = [{
    "litter_id": "LIT-1",
    "sow_pig_id": "PIG-SHUPE",
    "boar_pig_id": "PIG-BOAR",
    "farrowing_date": "2026-03-01",
    "born_alive": 8,
    "weaned_count": 7,
    "litter_status": "Weaned",
}]
MEDICAL = {
    "PIG-SHUPE": {"history": [{
        "pig_id": "PIG-SHUPE",
        "treatment_date_display": "2026-07-25",
        "treatment_type": "Topical",
        "reason_for_treatment": "Small abrasion",
        "withdrawal_days": 7,
        "withdrawal_end_date": "2026-08-01",
        "follow_up_required": "Yes",
        "follow_up_date": "2026-08-02",
    }]}
}
RECOMMENDATIONS = {
    "PIG-SHUPE": {
        "status": "Medical hold",
        "reason": "Active withdrawal evidence outranks breeding advice.",
        "next_action": "Complete the dated medical follow-up.",
        "protected_action_requires_approval": True,
    }
}


def answer(question="What do you know about Shupe? ", **overrides):
    kwargs = {
        "authenticated_owner": True,
        "animals": ANIMALS,
        "weight_history_by_pig": WEIGHTS,
        "movement_history_by_pig": MOVEMENTS,
        "mating_rows": MATINGS,
        "litter_rows": LITTERS,
        "medical_history_by_pig": MEDICAL,
        "recommendation_by_pig": RECOMMENDATIONS,
        "today": TODAY,
    }
    kwargs.update(overrides)
    return compose_herd_evidence_answer(question, **kwargs)


def test_supported_categories_are_bounded():
    assert set(SUPPORTED_QUESTION_CATEGORIES) == {
        "weight_chronology",
        "pen_movement",
        "availability_purpose",
        "mating_litter",
        "medical_withdrawal",
        "missing_evidence_next_action",
    }


def test_owner_authentication_is_required_before_animal_evidence():
    result = answer(authenticated_owner=False)
    assert result["status"] == "owner_authentication_required"
    assert "PIG-SHUPE" not in str(result)


def test_exact_identity_and_ambiguity_fail_privately():
    duplicate = ANIMALS + [{
        **ANIMALS[0], "pig_id": "PIG-OTHER", "tag_number": "Other",
        "name": "Shupe",
    }]
    result = answer(animals=duplicate)
    assert result["status"] == "animal_identity_ambiguous"
    assert result["candidate_count"] == 2
    assert "PIG-OTHER" not in str(result)
    assert "candidates" not in result


def test_malformed_or_duplicate_canonical_identity_fails_closed():
    assert answer(animals=[{**ANIMALS[0], "pig_id": ""}])[
        "status"
    ] == "canonical_identity_unavailable"
    assert answer(animals=ANIMALS + [{**ANIMALS[0]}])[
        "status"
    ] == "canonical_identity_unavailable"


def test_historical_weights_are_ordered_dated_and_concise():
    result = answer("What is Shupe's weight history?")
    facts = result["facts"]["weight_chronology"]
    assert facts["history"][0] == {
        "weight_kg": 72.2,
        "evidence_date": "2026-07-20",
        "observation_time": "Unknown",
    }
    assert facts["history"][1]["weight_kg"] == 68.0
    assert "72.2 kg on 2026-07-20" in result["answer"]
    assert result["evidence_provenance"][0]["source"] == (
        "canonical_weight_events"
    )


def test_stale_weight_blocks_only_weight_freshness_claim():
    stale = {"PIG-SHUPE": {"history": [{
        "pig_id": "PIG-SHUPE",
        "weight_date_display": "2026-01-01",
        "weight_kg": 60,
    }]}}
    result = answer(
        "What is Shupe's weight and purpose?",
        weight_history_by_pig=stale,
    )
    assert "The latest weight is stale." in result["missing_or_stale_evidence"]
    assert result["facts"]["availability_purpose"]["purpose"] == "Breeding"


def test_pen_and_movement_summary_preserves_chronology():
    result = answer("What pen is Shupe in and where was she moved?")
    facts = result["facts"]["pen_movement"]
    assert facts["current_pen_id"] == "PEN-3"
    assert facts["history"][0]["from_pen"] == "PEN-1"
    assert facts["history"][0]["to_pen"] == "PEN-3"
    assert facts["history"][0]["evidence_date"] == "2026-07-15"
    assert "PEN-1 to PEN-3 on 2026-07-15" in result["answer"]


def test_missing_movement_does_not_erase_known_current_pen():
    result = answer(
        "What pen is Shupe in and where was she moved?",
        movement_history_by_pig={},
    )
    assert result["facts"]["pen_movement"]["current_pen_id"] == "PEN-3"
    assert "No canonical movement chronology is recorded." in (
        result["missing_or_stale_evidence"]
    )


def test_availability_presence_and_purpose_are_facts_not_clearance():
    result = answer("Is Shupe on farm, available, and what is her purpose?")
    facts = result["facts"]["availability_purpose"]
    assert facts["on_farm"] == "Yes"
    assert facts["available"] == "Yes"
    assert facts["purpose"] == "Breeding"
    assert facts["clearance_inferred"] is False
    assert "not clearance" in result["answer"]
    assert "as of: 2026-07-29" in result["answer"]


def test_mating_and_litter_chronology_is_sourced_and_read_only():
    result = answer("What is known about Shupe's mating and litter history?")
    facts = result["facts"]["mating_litter"]
    assert facts["animal_role"] == "sow"
    assert facts["matings"][0]["mating_date"] == "2026-07-01"
    assert facts["litters"][0]["farrowing_date"] == "2026-03-01"
    assert facts["pregnancy_evidence"]["state"] == "pregnant"
    assert facts["protected_actions_performed"] is False
    assert "Latest mating: 2026-07-01 with PIG-BOAR" in result["answer"]
    assert "Latest farrowing: 2026-03-01 (LIT-1)" in result["answer"]


def test_female_counterpart_never_inherits_another_sows_pregnancy():
    other_sow_row = {
        **MATINGS[0],
        "mating_id": "MAT-OTHER-SOW",
        "sow_pig_id": "PIG-OTHER-SOW",
        "boar_pig_id": "PIG-SHUPE",
        "mating_date": "2026-07-25",
        "pregnancy_check_date": "2026-07-29",
    }
    result = answer(
        "What is known about Shupe's mating history?",
        mating_rows=MATINGS + [other_sow_row],
    )
    pregnancy = result["facts"]["mating_litter"]["pregnancy_evidence"]
    assert pregnancy["mating_date"] == "2026-07-01"
    assert pregnancy["state"] == "pregnant"


def test_boar_does_not_inherit_sow_pregnancy_evidence():
    result = answer(
        "What is known about Prince's mating and litter history?",
        recommendation_by_pig={},
    )
    pregnancy = result["facts"]["mating_litter"]["pregnancy_evidence"]
    assert pregnancy["state"] == "not_applicable"
    assert pregnancy["currently_applicable"] is False
    assert "canonical sow" in pregnancy["derived_status"]


def test_unrelated_mating_and_litter_rows_are_not_disclosed():
    unrelated_mating = {
        **MATINGS[0],
        "mating_id": "PRIVATE",
        "sow_pig_id": "PIG-OTHER",
        "boar_pig_id": "PIG-OTHER-BOAR",
    }
    unrelated_litter = {
        **LITTERS[0],
        "litter_id": "PRIVATE-LITTER",
        "sow_pig_id": "PIG-OTHER",
        "boar_pig_id": "PIG-OTHER-BOAR",
    }
    result = answer(
        mating_rows=MATINGS + [unrelated_mating],
        litter_rows=LITTERS + [unrelated_litter],
    )
    assert "PRIVATE" not in str(result)
    assert "PIG-OTHER" not in str(result)


def test_medical_summary_preserves_active_withdrawal_without_clearance():
    result = answer("What medical and withdrawal evidence exists for Shupe?")
    facts = result["facts"]["medical_withdrawal"]
    assert facts["event_count"] == 1
    assert facts["withdrawal_state"] == "Active hold"
    assert facts["withdrawal_end_date"] == "2026-08-01"
    assert facts["clearance_inferred"] is False
    assert facts["medical_action_performed"] is False
    assert "Topical on 2026-07-25" in result["answer"]
    assert "withdrawal end: 2026-08-01" in result["answer"]


def test_unknown_withdrawal_blocks_clearance_only():
    unknown = {"PIG-SHUPE": {"history": [{
        "pig_id": "PIG-SHUPE",
        "treatment_date_display": "2026-07-25",
        "treatment_type": "Unknown",
        "withdrawal_days": None,
        "withdrawal_end_date": "",
    }]}}
    result = answer(
        "What medical evidence and purpose exist for Shupe?",
        medical_history_by_pig=unknown,
    )
    assert result["facts"]["medical_withdrawal"]["withdrawal_state"] == "Unknown"
    assert "Current withdrawal status is Unknown." in (
        result["missing_or_stale_evidence"]
    )
    assert result["facts"]["availability_purpose"]["purpose"] == "Breeding"


def test_withdrawal_days_without_end_date_remains_unknown():
    incomplete = {"PIG-SHUPE": {"history": [{
        "pig_id": "PIG-SHUPE",
        "treatment_date_display": "2026-07-25",
        "treatment_type": "Injection",
        "withdrawal_days": 14,
        "withdrawal_end_date": "",
    }]}}
    result = answer(
        "What is Shupe's withdrawal history?",
        medical_history_by_pig=incomplete,
    )
    assert result["facts"]["medical_withdrawal"]["withdrawal_state"] == "Unknown"
    assert "Current withdrawal status is Unknown." in (
        result["missing_or_stale_evidence"]
    )


def test_no_medical_history_is_not_health_clearance():
    result = answer(
        "What medical evidence exists for Shupe?",
        medical_history_by_pig={},
    )
    assert result["facts"]["medical_withdrawal"]["withdrawal_state"] == "Unknown"
    assert "No canonical medical history is recorded." in (
        result["missing_or_stale_evidence"]
    )
    assert "No medical clearance is inferred." in result["answer"]


def test_canonical_recommendation_and_one_action_are_preserved():
    result = answer()
    recommendation = result["recommendation"]
    assert recommendation["next_action"] == (
        "Complete the dated medical follow-up."
    )
    assert recommendation["source"] == "canonical_herdmaster_recommendation"
    assert "requires separate owner approval" in result["answer"]


def test_missing_evidence_fallback_selects_one_small_action():
    result = answer(
        "What medical evidence exists for Shupe?",
        medical_history_by_pig={},
        recommendation_by_pig={},
    )
    assert result["recommendation"]["next_action"] == (
        "Review: No canonical medical history is recorded."
    )


def test_missing_fallback_prioritizes_unknown_withdrawal_over_chronology():
    result = answer(
        movement_history_by_pig={},
        medical_history_by_pig={"PIG-SHUPE": {"history": [{
            "pig_id": "PIG-SHUPE",
            "treatment_date_display": "2026-07-25",
            "withdrawal_days": 7,
            "withdrawal_end_date": "",
        }]}},
        recommendation_by_pig={},
    )
    assert result["recommendation"]["next_action"] == (
        "Review: Current withdrawal status is Unknown."
    )


def test_stale_movement_and_medical_are_reported_without_hiding_facts():
    old_movements = {"PIG-SHUPE": {"history": [{
        "pig_id": "PIG-SHUPE",
        "move_date_display": "2026-01-01",
        "from_pen_id": "PEN-1",
        "to_pen_id": "PEN-3",
    }]}}
    old_medical = {"PIG-SHUPE": {"history": [{
        "pig_id": "PIG-SHUPE",
        "treatment_date_display": "2026-01-01",
        "treatment_type": "Topical",
        "withdrawal_days": 1,
        "withdrawal_end_date": "2026-01-02",
    }]}}
    result = answer(
        movement_history_by_pig=old_movements,
        medical_history_by_pig=old_medical,
    )
    assert "The latest movement evidence is stale." in (
        result["missing_or_stale_evidence"]
    )
    assert "The latest medical evidence is stale." in (
        result["missing_or_stale_evidence"]
    )
    assert result["facts"]["pen_movement"]["history"]
    assert result["facts"]["medical_withdrawal"]["event_count"] == 1


def test_future_and_malformed_nonpregnancy_dates_are_excluded():
    result = answer(
        weight_history_by_pig={"PIG-SHUPE": {"history": [
            {"pig_id": "PIG-SHUPE", "weight_date_display": "2026-08-01", "weight_kg": 90},
            {"pig_id": "PIG-SHUPE", "weight_date_display": "not-a-date", "weight_kg": 91},
        ]}},
        movement_history_by_pig={"PIG-SHUPE": {"history": [{
            "pig_id": "PIG-SHUPE", "move_date_display": "2026-08-01",
            "from_pen_id": "PEN-1", "to_pen_id": "PEN-2",
        }]}},
        medical_history_by_pig={"PIG-SHUPE": {"history": [{
            "pig_id": "PIG-SHUPE", "treatment_date_display": "bad",
            "treatment_type": "Private",
        }]}},
    )
    assert result["facts"]["weight_chronology"]["history"] == []
    assert result["facts"]["pen_movement"]["history"] == []
    assert result["facts"]["medical_withdrawal"]["event_count"] == 0
    assert "Future-dated or malformed weight evidence was excluded." in (
        result["missing_or_stale_evidence"]
    )


def test_identityless_and_unrelated_projection_rows_are_not_attributed():
    result = answer(
        weight_history_by_pig={"PIG-SHUPE": {"history": [
            {"weight_date_display": "2026-07-20", "weight_kg": 999},
            {"pig_id": "PIG-OTHER", "weight_date_display": "2026-07-20", "weight_kg": 998},
        ]}},
        movement_history_by_pig={"PIG-SHUPE": {"history": [
            {"move_date_display": "2026-07-20", "from_pen_id": "X", "to_pen_id": "Y"},
        ]}},
        medical_history_by_pig={"PIG-SHUPE": {"history": [
            {"treatment_date_display": "2026-07-20", "treatment_type": "Private"},
        ]}},
    )
    assert "999" not in str(result)
    assert "998" not in str(result)
    assert "Private" not in str(result)


def test_common_possessive_family_questions_resolve_identity():
    for question in (
        "What is Shupe's availability?",
        "What is Shupe's purpose?",
        "What is Shupe's withdrawal history?",
    ):
        result = answer(question)
        assert result["success"] is True
        assert result["subject"]["pig_id"] == "PIG-SHUPE"


def test_reordered_mapping_keys_have_same_fingerprint():
    animal_reordered = [{key: row[key] for key in reversed(list(row))}
                        for row in ANIMALS]
    assert answer()["response_fingerprint"] == answer(
        animals=animal_reordered
    )["response_fingerprint"]


def test_recognized_protected_recommendation_is_conservatively_flagged():
    result = answer(recommendation_by_pig={"PIG-SHUPE": {
        "status": "Review",
        "reason": "Evidence",
        "next_action": "Treat Shupe now.",
        "protected_action_requires_approval": False,
    }})
    assert result["recommendation"][
        "protected_action_requires_approval"
    ] is True


def test_answer_is_natural_concise_sourced_and_zero_write():
    result = answer()
    assert result["success"] is True
    assert len(result["answer"]) < 1400
    assert len(result["evidence_provenance"]) >= 5
    assert result["read_only"] is True
    assert result["writes_performed"] is False
    assert result["protected_actions_performed"] is False
    assert result["confirmation_required"] is False
    assert "no farm record or protected action changed" in (
        result["answer"].casefold()
    )


def test_same_evidence_has_deterministic_response_fingerprint():
    assert answer()["response_fingerprint"] == answer()["response_fingerprint"]


def test_no_writer_route_network_or_storage_capability_is_exposed():
    result = answer()
    serialized = str(result).casefold()
    assert "writer" not in serialized
    assert "telegram" not in serialized
    assert "render" not in serialized
    assert "n8n" not in serialized


def load_tests(_loader, _tests, _pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite
