from datetime import date
import unittest

from modules.oom_sakkie.herd_fact_intake_contract import (
    CONDITIONAL_CANONICAL_WORKFLOW_CATEGORIES,
    PROTECTED_INFERENCES,
    SUPPORTED_FACT_CATEGORIES,
    prepare_confirmed_fact_execution,
    preview_conversational_herd_fact,
    verify_recorded_fact_outcome,
)


TODAY = date(2026, 7, 29)


def _animal(pig_id, tag, *, sex="Female", name=""):
    return {
        "pig_id": pig_id,
        "tag_number": tag,
        "name": name,
        "sex": sex,
        "status": "Active",
        "on_farm": "Yes",
    }


ANIMALS = [
    _animal("PIG-2026-34BF", "Shupe"),
    _animal("PIG-TEENA", "Teena"),
    _animal("PIG-MONA", "Mona"),
    _animal("PIG-BOAR", "Prince", sex="Male"),
]


STATE = {
    "PIG-2026-34BF": {
        "latest_weight": {
            "weight_kg": 70.0,
            "evidence_date": "2026-07-01",
            "observation_time": "Unknown",
        },
        "current_pen_id": "PEN-1",
        "on_farm": "Yes",
    },
    "PIG-TEENA": {
        "latest_observations": {
            "movement_observation": "Unknown",
            "visible_concern": "Unknown",
        },
        "current_pen_id": "PEN-2",
    },
    "PIG-MONA": {
        "latest_mating": {
            "mating_id": "MAT-MONA",
            "sow_pig_id": "PIG-MONA",
            "mating_date": "2026-06-20",
            "expected_farrowing_date": "2026-10-12",
            "pregnancy_check_result": "Pending",
        },
        "current_pen_id": "PEN-3",
        "available_for_breeding": "Unknown",
        "on_farm": "Yes",
    },
}


RECOMMENDATIONS = {
    "PIG-2026-34BF": {
        "status": "Retain / Breeding Candidate",
        "next_action": "Review breeding retention evidence.",
    }
}


def preview(text, *, animals=None, state=None, recommendations=None):
    return preview_conversational_herd_fact(
        text,
        animals=ANIMALS if animals is None else animals,
        canonical_state_by_pig=STATE if state is None else state,
        recommendation_by_pig=(
            RECOMMENDATIONS if recommendations is None else recommendations
        ),
        governed_pregnancy_assessors=["Dr Ndlovu"],
        today=TODAY,
    )


def test_supported_scope_is_bounded_and_conditional_workflows_are_separate():
    assert set(SUPPORTED_FACT_CATEGORIES) == {
        "weight",
        "physical_condition",
        "movement_observation",
        "visible_concern",
        "heat_observation",
        "pregnancy_check",
        "availability",
        "farm_presence",
        "pen_location",
        "pen_movement",
        "mating",
    }
    assert CONDITIONAL_CANONICAL_WORKFLOW_CATEGORIES == (
        "litter", "lifecycle"
    )


def test_shupe_weight_fact_builds_canonical_before_after_preview():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026.")
    assert result["success"] is True
    assert result["subject"] == {
        "pig_id": "PIG-2026-34BF",
        "tag_number": "Shupe",
    }
    assert result["facts"] == [{
        "category": "weight",
        "weight_kg": 72.2,
        "evidence_date": "2026-07-20",
        "observation_time": "Unknown",
    }]
    assert result["canonical_before"]["weight"]["weight_kg"] == 70.0
    assert result["canonical_after_preview"]["weight"] == {
        "weight_kg": 72.2,
        "evidence_date": "2026-07-20",
        "observation_time": "Unknown",
    }
    assert result["confirmation"]["required"] is True
    assert result["writes_performed"] is False


def test_identical_fact_has_deterministic_idempotency_and_preview_identity():
    first = preview("Shupe weighed 72.2 kg on 20 July 2026.")
    second = preview("  Shupe   weighed 72.2kg on 20 July 2026  ")
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["preview_id"] == second["preview_id"]


def test_same_name_identity_ambiguity_fails_without_animal_context():
    animals = [
        _animal("PIG-A", "Spot"),
        _animal("PIG-B", "Spot"),
    ]
    result = preview(
        "Spot weighed 20 kg on 20 July 2026",
        animals=animals,
        state={},
    )
    assert result["success"] is False
    assert result["status"] == "animal_identity_ambiguous"
    assert result["candidate_count"] == 2
    assert "canonical_before" not in result
    assert result["writes_performed"] is False


def test_missing_or_future_weight_date_is_rejected():
    missing = preview("Shupe weighed 72.2 kg")
    future = preview("Shupe weighed 72.2 kg on 30 July 2026")
    assert missing["status"] == "unsupported_or_malformed_herd_fact"
    assert future["status"] == "fact_date_invalid"


def test_compound_direct_observation_keeps_two_supported_facts():
    result = preview(
        "Teena was moving normally this morning and no injury was visible."
    )
    assert result["success"] is True
    assert result["fact_categories"] == [
        "movement_observation", "visible_concern"
    ]
    assert result["facts"][0]["movement"] == "normal"
    assert result["facts"][1]["visible_injury"] == "none_visible"
    assert all(
        item["evidence_date"] == "2026-07-29"
        and item["observation_time"] == "Morning"
        for item in result["facts"]
    )


def test_body_condition_and_visible_concern_require_direct_values_and_dates():
    condition = preview(
        "Teena had body condition score 3 on 29 July 2026"
    )
    concern = preview(
        "Teena had a visible injury: left foreleg scrape on 29 July 2026"
    )
    assert condition["facts"][0]["body_condition_score"] == 3.0
    assert concern["facts"][0]["detail"] == "left foreleg scrape"
    assert condition["writes_performed"] is False
    assert concern["writes_performed"] is False


def test_standalone_movement_and_no_injury_observations_are_supported():
    movement = preview("Teena was limping today")
    no_injury = preview("Teena had no visible injury today")
    assert movement["facts"][0]["movement"] == "concern"
    assert movement["facts"][0]["detail"] == "Limping"
    assert no_injury["facts"][0]["visible_injury"] == "none_visible"


def test_heat_observed_and_not_observed_are_exact_distinct_facts():
    observed = preview("Mona heat was observed today")
    absent = preview("Mona heat was not observed today")
    assert observed["facts"][0]["heat_observed"] is True
    assert absent["facts"][0]["heat_observed"] is False
    assert observed["idempotency_key"] != absent["idempotency_key"]


def test_contradictory_heat_statement_is_rejected():
    result = preview(
        "Mona heat was observed and heat was not observed today"
    )
    assert result["status"] == "contradictory_heat_observation"
    assert result["writes_performed"] is False


def test_governed_pregnancy_check_requires_current_sow_cycle_and_provenance():
    result = preview(
        "Mona had an ultrasound by Dr Ndlovu on 20 July 2026; "
        "result: Pregnant"
    )
    fact = result["facts"][0]
    assert result["success"] is True
    assert fact == {
        "category": "pregnancy_check",
        "method": "Ultrasound",
        "assessor": "Dr Ndlovu",
        "governance_status": "Canonical assessor and method validated",
        "result": "Pregnant",
        "evidence_date": "2026-07-20",
        "observation_time": "Unknown",
    }
    assert result["protected_inferences"]["pregnancy"] == "Not inferred"
    assert result["future_execution"]["adapter_keys"] == [
        "canonical_pregnancy_check_writer"
    ]


def test_pregnancy_check_missing_assessor_or_date_is_rejected():
    missing_assessor = preview(
        "Mona had an ultrasound on 20 July 2026; result: Pregnant"
    )
    missing_date = preview(
        "Mona had an ultrasound by Dr Ndlovu; result: Pregnant"
    )
    assert missing_assessor["success"] is False
    assert missing_date["success"] is False


def test_pregnancy_check_rejects_male_stale_or_resolved_cycle():
    male = preview(
        "Prince had an ultrasound by Dr Ndlovu on 20 July 2026; "
        "result: Pregnant"
    )
    stale_state = {
        **STATE,
        "PIG-MONA": {
            "latest_mating": {
                "mating_id": "MAT-OLD",
                "sow_pig_id": "PIG-MONA",
                "mating_date": "2026-01-01",
                "pregnancy_check_result": "Pending",
            }
        },
    }
    stale = preview(
        "Mona had an ultrasound by Dr Ndlovu on 20 July 2026; "
        "result: Pregnant",
        state=stale_state,
    )
    assert male["status"] == "pregnancy_subject_must_be_female"
    assert stale["status"] == "pregnancy_cycle_stale_or_resolved"


def test_pregnancy_result_conflicting_with_same_governed_check_is_rejected():
    state = {
        **STATE,
        "PIG-MONA": {
            "latest_mating": {
                **STATE["PIG-MONA"]["latest_mating"],
                "pregnancy_check_date": "2026-07-20",
                "pregnancy_check_result": "Not Pregnant",
            }
        },
    }
    result = preview(
        "Mona had an ultrasound by Dr Ndlovu on 20 July 2026; "
        "result: Pregnant",
        state=state,
    )
    assert result["status"] == "pregnancy_result_conflict"
    assert result["writes_performed"] is False


def test_availability_and_presence_do_not_infer_clearance_or_readiness():
    available = preview("Mona is available for breeding as of today")
    present = preview("Mona is on farm as of today")
    assert available["facts"][0]["available"] is True
    assert present["facts"][0]["on_farm"] is True
    for result in (available, present):
        assert all(
            value == "Not inferred"
            for value in result["protected_inferences"].values()
        )


def test_pen_location_and_movement_have_canonical_before_after():
    location = preview("Mona is in pen PEN-4 as of today")
    movement = preview("Mona moved from PEN-3 to PEN-4 on 29 July 2026")
    assert location["canonical_before"]["current_pen_id"] == "PEN-3"
    assert location["canonical_after_preview"]["current_pen_id"] == "PEN-4"
    assert movement["canonical_before"]["current_pen_id"] == "PEN-3"
    assert movement["canonical_after_preview"]["current_pen_id"] == "PEN-4"


def test_pen_movement_conflict_and_same_pen_are_rejected():
    stale_source = preview(
        "Mona moved from PEN-2 to PEN-4 on 29 July 2026"
    )
    same_pen = preview(
        "Mona moved from PEN-3 to PEN-3 on 29 July 2026"
    )
    assert stale_source["status"] == "movement_source_pen_conflict"
    assert same_pen["status"] == "pen_movement_contradictory"


def test_mating_is_preview_only_with_exact_female_male_and_date():
    result = preview("Mona was mated with Prince on 20 July 2026")
    fact = result["facts"][0]
    assert result["success"] is True
    assert fact["female_pig_id"] == "PIG-MONA"
    assert fact["male_pig_id"] == "PIG-BOAR"
    assert fact["evidence_date"] == "2026-07-20"
    assert fact["family_compatibility"] == "Not evaluated"
    assert fact["execution_requires_separate_approval"] is True
    assert result["future_execution"]["execution_enabled"] is False


def test_mating_rejects_wrong_role_and_ambiguous_male():
    wrong_role = preview("Prince was mated with Mona on 20 July 2026")
    animals = [
        *ANIMALS,
        _animal("PIG-BOAR-2", "Prince", sex="Male"),
    ]
    ambiguous = preview(
        "Mona was mated with Prince on 20 July 2026",
        animals=animals,
    )
    assert wrong_role["status"] == "mating_subject_must_be_female"
    assert ambiguous["status"] == "mating_male_identity_ambiguous"


def test_litter_and_lifecycle_delegate_to_existing_canonical_workflows():
    litter = preview("Mona farrowed a litter today")
    lifecycle = preview("Mona died today")
    assert litter["status"] == "canonical_workflow_adapter_required"
    assert lifecycle["status"] == "canonical_workflow_adapter_required"
    assert litter["writes_performed"] is False
    assert lifecycle["writes_performed"] is False


def test_unsupported_inference_is_rejected_without_blocking_direct_facts():
    inferred = preview("Mona is healthy and safe to breed")
    direct = preview("Mona heat was not observed today")
    assert inferred["status"] == "unsupported_inference"
    assert direct["success"] is True
    assert set(PROTECTED_INFERENCES) == {
        "pregnancy",
        "fertility",
        "health_clearance",
        "withdrawal_clearance",
        "breeding_readiness",
        "family_compatibility",
    }


def test_confirmation_must_match_exact_preview_text():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    denied = prepare_confirmed_fact_execution(result, "yes")
    assert denied["status"] == "exact_confirmation_required"
    assert denied["writes_performed"] is False


def test_exact_confirmation_prepares_but_never_executes_writer_packet():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    plan = prepare_confirmed_fact_execution(
        result,
        result["confirmation"]["exact_text"],
        persisted_preview_verified=True,
        actor_chat_binding_verified=True,
        canonical_state_revalidated=True,
        idempotency_claim_status="claimed",
    )
    assert plan["status"] == "confirmed_execution_plan_ready"
    assert plan["write_authorized_by_confirmation"] is True
    assert plan["execution_required"] is True
    assert plan["execution_performed"] is False
    assert plan["writes_performed"] is False


def test_completed_idempotency_identity_makes_exact_replay_noop():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    replay = prepare_confirmed_fact_execution(
        result,
        result["confirmation"]["exact_text"],
        persisted_preview_verified=True,
        actor_chat_binding_verified=True,
        canonical_state_revalidated=True,
        idempotency_claim_status="completed",
    )
    assert replay["status"] == "confirmed_replay_noop"
    assert replay["additional_facts_expected"] == 0
    assert replay["execution_required"] is False
    assert replay["writes_performed"] is False


def test_verified_outcome_requires_unique_fact_zero_replay_and_next_action():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    verified = verify_recorded_fact_outcome(
        result,
        matching_canonical_facts=[{
            "pig_id": "PIG-2026-34BF",
            "idempotency_key": result["idempotency_key"],
            **result["facts"][0],
        }],
        replay_additional_fact_count=0,
        recommendation_after={
            "status": "Breeding review",
            "next_action": "Inspect body condition before breeding decision.",
        },
    )
    assert verified["success"] is True
    assert verified["matching_canonical_fact_count"] == 1
    assert verified["replay_additional_fact_count"] == 0
    assert verified["next_action"] == (
        "Inspect body condition before breeding decision."
    )
    assert verified["writes_performed_by_verifier"] is False


def test_outcome_verification_fails_without_exact_once_or_next_action():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    duplicate = verify_recorded_fact_outcome(
        result,
        matching_canonical_facts=[{}, {}],
        replay_additional_fact_count=1,
        recommendation_after={},
    )
    assert duplicate["status"] == "recorded_outcome_not_proven"
    assert duplicate["writes_performed"] is False


def test_successful_preview_contains_no_unrelated_animal_context():
    result = preview("Teena was moving normally today and no injury was visible")
    serialized = str(result)
    assert "PIG-MONA" not in serialized
    assert "PIG-BOAR" not in serialized
    assert "Prince" not in serialized
    assert result["subject"]["pig_id"] == "PIG-TEENA"


def test_human_preview_contains_identity_before_after_and_exact_confirmation():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    text = result["canonical_preview_text"]
    assert "Shupe (PIG-2026-34BF)" in text
    assert '"weight_kg": 70.0' in text
    assert '"weight_kg": 72.2' in text
    assert '"evidence_date": "2026-07-20"' in text
    assert '"observation_time": "Unknown"' in text
    assert result["confirmation"]["exact_text"] in text


def test_human_availability_preview_disclaims_clearance():
    result = preview("Mona is available for breeding as of today")
    text = result["canonical_preview_text"]
    assert "availability fact" in text
    assert "not health, withdrawal, fertility, or breeding-readiness clearance" in text


def test_human_mating_preview_requires_separate_governed_approval():
    result = preview("Mona was mated with Prince on 20 July 2026")
    assert "protected action requiring separate governed approval" in (
        result["canonical_preview_text"]
    )


def test_pregnancy_before_preview_has_comparable_provenance():
    result = preview(
        "Mona had an ultrasound by Dr Ndlovu on 20 July 2026; "
        "result: Pregnant"
    )
    before = result["canonical_before"]["pregnancy_check"]
    assert before == {
        "result": "Pending",
        "evidence_date": "Unknown",
        "method": "Unknown",
        "assessor": "Unknown",
        "observation_time": "Unknown",
    }


def test_mating_confirmation_never_authorizes_protected_action():
    result = preview("Mona was mated with Prince on 20 July 2026")
    plan = prepare_confirmed_fact_execution(
        result,
        result["confirmation"]["exact_text"],
        persisted_preview_verified=True,
        actor_chat_binding_verified=True,
        canonical_state_revalidated=True,
        idempotency_claim_status="claimed",
    )
    assert plan["status"] == "protected_action_approval_required"
    assert plan["write_authorized_by_confirmation"] is False
    assert plan["execution_required"] is False
    assert plan["separate_governed_approval_required"] is True


def test_forged_or_unbound_preview_cannot_authorize_execution():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    forged = dict(result)
    forged["facts"] = [dict(result["facts"][0], weight_kg=999)]
    denied_forged = prepare_confirmed_fact_execution(
        forged, forged["confirmation"]["exact_text"]
    )
    denied_unbound = prepare_confirmed_fact_execution(
        result, result["confirmation"]["exact_text"]
    )
    assert denied_forged["status"] == "valid_preview_required"
    assert denied_unbound["status"] == "persisted_preview_verification_required"


def test_confirmation_and_adapter_fields_cannot_be_tampered():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    tampered = dict(result)
    tampered["confirmation"] = {"exact_text": "YES"}
    tampered["future_execution"] = {
        **result["future_execution"],
        "adapter_keys": ["arbitrary_writer"],
    }
    denied = prepare_confirmed_fact_execution(
        tampered,
        "YES",
        persisted_preview_verified=True,
        actor_chat_binding_verified=True,
        canonical_state_revalidated=True,
        idempotency_claim_status="claimed",
    )
    assert denied["status"] == "exact_confirmation_required"
    plan = prepare_confirmed_fact_execution(
        tampered,
        f"CONFIRM {result['preview_id']}",
        persisted_preview_verified=True,
        actor_chat_binding_verified=True,
        canonical_state_revalidated=True,
        idempotency_claim_status="claimed",
    )
    assert plan["adapter_keys"] == ["canonical_weight_writer"]


def test_compound_outcome_requires_every_fact_exactly_once():
    result = preview(
        "Teena was moving normally today and no injury was visible"
    )
    plan = prepare_confirmed_fact_execution(
        result,
        result["confirmation"]["exact_text"],
        persisted_preview_verified=True,
        actor_chat_binding_verified=True,
        canonical_state_revalidated=True,
        idempotency_claim_status="claimed",
    )
    assert plan["post_write_requirements"]["matching_fact_count"] == 2
    canonical = [{
        "pig_id": "PIG-TEENA",
        "idempotency_key": result["idempotency_key"],
        **fact,
    } for fact in result["facts"]]
    verified = verify_recorded_fact_outcome(
        result,
        matching_canonical_facts=canonical,
        replay_additional_fact_count=0,
        recommendation_after={"next_action": "Continue routine observation."},
    )
    missing = verify_recorded_fact_outcome(
        result,
        matching_canonical_facts=canonical[:1],
        replay_additional_fact_count=0,
        recommendation_after={"next_action": "Continue routine observation."},
    )
    assert verified["matching_canonical_fact_count"] == 2
    assert missing["status"] == "recorded_outcome_not_proven"


def test_ambiguity_response_does_not_disclose_candidate_records():
    animals = ANIMALS + [_animal("PIG-OTHER-SHUPE", "Other", name="Shupe")]
    result = preview(
        "Shupe weighed 72.2 kg on 20 July 2026", animals=animals
    )
    assert result["status"] == "animal_identity_ambiguous"
    assert result["candidate_count"] == 2
    assert "candidates" not in result
    assert "PIG-OTHER-SHUPE" not in str(result)


def test_unauthorized_pregnancy_assessor_is_rejected():
    result = preview_conversational_herd_fact(
        "Mona had an ultrasound by Unknown Person on 20 July 2026; "
        "result: Pregnant",
        animals=ANIMALS,
        canonical_state_by_pig=STATE,
        governed_pregnancy_assessors=["Dr Ndlovu"],
        today=TODAY,
    )
    assert result["status"] == "pregnancy_assessor_not_governed"


def test_malformed_identity_and_state_fail_closed():
    missing_id = [_animal("", "Shupe")]
    duplicate_id = ANIMALS + [_animal("PIG-MONA", "Duplicate")]
    assert preview(
        "Shupe weighed 72.2 kg on 20 July 2026", animals=missing_id
    )["status"] == "canonical_herd_identity_unavailable"
    assert preview(
        "Shupe weighed 72.2 kg on 20 July 2026", animals=duplicate_id
    )["status"] == "canonical_herd_identity_unavailable"
    assert preview(
        "Shupe weighed 72.2 kg on 20 July 2026",
        state={"PIG-2026-34BF": []},
    )["status"] == "canonical_herd_state_invalid"


def test_oversized_input_and_concern_detail_are_rejected():
    oversized = preview("Shupe " + ("x" * 1001))
    concern = preview(
        "Teena had a visible concern: "
        + ("x" * 241)
        + " on 29 July 2026"
    )
    assert oversized["status"] == "herd_fact_too_long"
    assert concern["status"] == "visible_concern_detail_too_long"


def test_outcome_rejects_unrelated_canonical_fact():
    result = preview("Shupe weighed 72.2 kg on 20 July 2026")
    denied = verify_recorded_fact_outcome(
        result,
        matching_canonical_facts=[{
            "pig_id": "PIG-MONA",
            "idempotency_key": result["idempotency_key"],
            **result["facts"][0],
        }],
        replay_additional_fact_count=0,
        recommendation_after={"next_action": "Anything"},
    )
    assert denied["status"] == "recorded_outcome_not_proven"


def load_tests(_loader, _tests, _pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite
