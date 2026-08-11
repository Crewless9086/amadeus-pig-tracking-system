from copy import deepcopy

import pytest

from modules.pig_weights.herdmaster_natural_health_loss_intake import (
    IntakeEvidenceError,
    evaluate_health_loss_intake,
)


TIME = "2026-08-01T08:30:00+02:00"


def animal(pig_id="PIG-2026-MAYA", name="Maya", tag="Maya", **overrides):
    row = {
        "pig_id": pig_id, "name": name, "tag_number": tag,
        "lifecycle_status": "Active", "on_farm": True,
        "availability": "Breeding", "pen": "Farrowing 1",
    }
    row.update(overrides)
    return row


def evidence(*animals, matings=()):
    return {
        "evidence_generation": "GEN-1", "animals": list(animals),
        "as_of_timestamp": "2026-08-01T08:31:00+02:00",
        "matings": list(matings), "litters": [],
    }


def report(text, message_id="MSG-1"):
    return {
        "authenticated": True, "text": text,
        "provider_timestamp": TIME, "provider_timezone": "Africa/Johannesburg",
        "provider_message_id": message_id,
        "authenticated_principal_id": "OWNER-CHARL",
    }


def maya_packet():
    maya = animal()
    mating = {
        "mating_id": "MAT-MAYA-1", "sow_pig_id": maya["pig_id"],
        "boar_pig_id": "PIG-BOAR-1", "date": "2026-04-09", "is_open": True,
    }
    return maya, evidence(maya, matings=[mating])


def test_maya_compound_preview_preserves_counts_and_suspicion_boundary():
    maya, canonical = maya_packet()
    result = evaluate_health_loss_intake(report(
        "Maya died yesterday after complications while farrowing. "
        "All 10 piglets were stillborn. We believe she had a uterine infection."
    ), canonical)
    assert result["status"] == "partial_preview_ready"
    assert result["event_family"] == "compound_event"
    observed = {x["fact"]: x["value"] for x in result["observed_facts"]}
    assert {key: observed[key] for key in (
        "total_born", "born_alive", "stillborn", "later_deaths", "event_date"
    )} == {
        "total_born": 10, "born_alive": 0, "stillborn": 10,
        "later_deaths": 0, "event_date": "2026-07-31",
    }
    assert result["owner_suspected_cause"] == [{
        "cause": "a uterine infection", "classification": "owner_suspected_not_diagnosed",
    }]
    assert result["veterinary_evidence"] == []
    assert result["agent_inference"] == []
    effects = {x["area"]: x for x in result["canonical_effects"]}
    assert effects["lifecycle"]["action"] == "record_death"
    assert effects["mating"]["facts"]["mating_id"] == "MAT-MAYA-1"
    assert effects["litter"]["facts"] == {
        "farrowing_date": "2026-07-31", "total_born": 10,
        "born_alive": 0, "stillborn": 10, "later_deaths": 0,
        "generated_identity_disposition": "stillborn_not_live_birth; later_deaths_require_distinct_live_birth_identity",
    }
    assert effects["medical_observation"]["facts"]["diagnosis_inferred"] is False
    assert effects["movement_pen"]["supported"] is False
    assert "removed from the pen" in result["smallest_missing_follow_up_question"]
    assert result["writes_performed"] is False
    assert result["farm_write_authority"] is False


def test_maya_is_not_hard_coded_and_yesterday_uses_provider_timezone():
    sow = animal("PIG-2026-OTHER", "Tessa", "Tessa")
    canonical = evidence(sow, matings=[{
        "mating_id": "MAT-TESSA", "sow_pig_id": sow["pig_id"],
        "date": "2026-04-10", "is_open": True,
    }])
    result = evaluate_health_loss_intake(report(
        "Tessa died yesterday while farrowing. All 3 piglets were stillborn."
    ), canonical)
    assert result["identity"]["pig_id"] == sow["pig_id"]
    assert result["preview"]["event_date"] == "2026-07-31"
    assert result["operation_id"].startswith("HERD-HEALTH-LOSS-")


@pytest.mark.parametrize("text,tag,family,observed", [
    ("Tag 51 looks sick and is not eating.", "51", "sick", "not_eating"),
    ("Pig 83 is limping.", "83", "injured", "limping"),
    ("I found tag 22 dead this morning.", "22", "found_dead", "animal_reported_dead"),
])
def test_ordinary_journeys(text, tag, family, observed):
    pig = animal(f"PIG-2026-{tag.zfill(4)}", tag, tag)
    result = evaluate_health_loss_intake(report(text), evidence(pig))
    assert result["event_family"] == family
    assert observed in {row["fact"] for row in result["observed_facts"]}
    assert result["zero_io"] is True


def test_ambiguous_name_asks_one_precise_identity_question_and_no_effects():
    result = evaluate_health_loss_intake(
        report("Maya looks sick."),
        evidence(animal("PIG-1", "Maya"), animal("PIG-2", "Maya")),
    )
    assert result["status"] == "identity_required"
    assert result["identity"]["candidate_pig_ids"] == ["PIG-1", "PIG-2"]
    assert result["smallest_missing_follow_up_question"].count("?") == 1
    assert result["canonical_effects"] == []


def test_no_repeated_question_for_known_maya_counts_date_cause_and_cycle():
    _maya, canonical = maya_packet()
    result = evaluate_health_loss_intake(report(
        "Maya died yesterday while farrowing. All 10 piglets were stillborn. "
        "We suspect infection."
    ), canonical)
    question = result["smallest_missing_follow_up_question"].casefold()
    for repeated in ("how many", "when did", "cause", "which mating"):
        assert repeated not in question


def test_stillborn_and_later_death_are_distinct():
    sow = animal("PIG-SOW", "Luna", "Luna")
    canonical = evidence(sow, matings=[{
        "mating_id": "MAT-LUNA", "sow_pig_id": "PIG-SOW",
        "date": "2026-04-10", "is_open": True,
    }])
    later = evaluate_health_loss_intake(
        report("Luna was farrowing. 2 piglets were born alive but then died."), canonical
    )
    litter = next(x for x in later["canonical_effects"] if x["area"] == "litter")
    assert litter["supported"] is False
    assert "In total" in later["smallest_missing_follow_up_question"]


def test_explicit_complete_mixed_birth_outcomes_are_one_atomic_litter():
    sow = animal("PIG-SOW", "Luna", "Luna")
    canonical = evidence(sow, matings=[{
        "mating_id": "MAT-LUNA", "sow_pig_id": "PIG-SOW",
        "date": "2026-04-10", "is_open": True,
    }])
    result = evaluate_health_loss_intake(report(
        "Luna was farrowing. Total born: 5; 2 piglets were stillborn and "
        "3 piglets were born alive but then died."
    ), canonical)
    litter = next(x for x in result["canonical_effects"] if x["area"] == "litter")
    assert litter["supported"] is True
    assert litter["facts"]["total_born"] == 5
    assert litter["facts"]["born_alive"] == 3
    assert litter["facts"]["stillborn"] == 2
    assert litter["facts"]["later_deaths"] == 3


def test_partial_farrowing_asks_only_for_birth_outcomes():
    sow = animal("PIG-SOW", "Luna", "Luna")
    result = evaluate_health_loss_intake(
        report("Luna had complications while farrowing."), evidence(sow)
    )
    assert result["status"] == "partial_preview_ready"
    assert result["smallest_missing_follow_up_question"] == (
        "In total, how many were born alive, stillborn, mummified, or died after live birth?"
    )
    unsupported = [x for x in result["canonical_effects"] if not x["supported"]]
    assert {x["area"] for x in unsupported} >= {"mating", "litter"}


def test_stale_chronology_fails_closed():
    maya = animal(lifecycle_effective_date="2026-08-01")
    result = evaluate_health_loss_intake(
        report("Maya died yesterday."), evidence(maya)
    )
    assert result["status"] == "chronology_conflict"
    assert result["canonical_effects"] == []
    assert result["required_confirmations"] == []


def test_stale_open_mating_cannot_be_closed_as_current_farrowing():
    maya = animal()
    stale = evidence(maya, matings=[{
        "mating_id": "MAT-STALE", "sow_pig_id": maya["pig_id"],
        "date": "2026-01-01", "is_open": True,
    }])
    result = evaluate_health_loss_intake(
        report("Maya had complications while farrowing yesterday."), stale
    )
    assert result["status"] == "chronology_conflict"
    assert any(
        "outside the governed farrowing cycle boundary" in conflict
        for conflict in result["chronology_conflicts"]
    )
    assert result["canonical_effects"] == []


def test_deterministic_replay_identity_and_evidence_change():
    _maya, canonical = maya_packet()
    natural = report("Maya died yesterday while farrowing. All 10 piglets were stillborn.")
    first = evaluate_health_loss_intake(deepcopy(natural), deepcopy(canonical))
    second = evaluate_health_loss_intake(deepcopy(natural), deepcopy(canonical))
    assert first["operation_id"] == second["operation_id"]
    changed = evaluate_health_loss_intake({**natural, "provider_message_id": "MSG-2"}, canonical)
    assert changed["operation_id"] != first["operation_id"]
    newer_evidence = evaluate_health_loss_intake(natural, {**canonical, "evidence_generation": "GEN-2"})
    assert newer_evidence["operation_id"] != first["operation_id"]


def test_veterinary_diagnosis_is_separate_from_owner_suspicion():
    pig = animal("PIG-51", "51", "51")
    result = evaluate_health_loss_intake(
        report("Tag 51 is sick. The vet diagnosed pneumonia. We think it started yesterday."),
        evidence(pig),
    )
    assert result["veterinary_evidence"] == [{
        "diagnosis": "pneumonia", "attribution": "owner_reported_veterinary_evidence",
    }]
    assert result["agent_inference"] == []


def test_authentication_and_provider_time_are_required():
    pig = animal("PIG-51", "51", "51")
    with pytest.raises(IntakeEvidenceError, match="authenticated_report_required"):
        evaluate_health_loss_intake({**report("Tag 51 is sick."), "authenticated": False}, evidence(pig))
    with pytest.raises(IntakeEvidenceError, match="provider_timestamp_required"):
        evaluate_health_loss_intake({**report("Tag 51 is sick."), "provider_timestamp": ""}, evidence(pig))
    with pytest.raises(IntakeEvidenceError, match="provider_message_id_required"):
        evaluate_health_loss_intake({**report("Tag 51 is sick."), "provider_message_id": ""}, evidence(pig))
    with pytest.raises(IntakeEvidenceError, match="authenticated_principal_required"):
        evaluate_health_loss_intake({**report("Tag 51 is sick."), "authenticated_principal_id": ""}, evidence(pig))
    with pytest.raises(IntakeEvidenceError, match="evidence_generation_required"):
        evaluate_health_loss_intake(report("Tag 51 is sick."), {**evidence(pig), "evidence_generation": ""})


def test_found_dead_supports_deceased_date_but_not_exact_death_time():
    pig = animal("PIG-22", "22", "22")
    result = evaluate_health_loss_intake(report("I found tag 22 dead this morning."), evidence(pig))
    lifecycle = next(x for x in result["canonical_effects"] if x["area"] == "lifecycle")
    assert lifecycle["supported"] is True
    assert lifecycle["action"] == "record_death"
    assert lifecycle["facts"]["date"] == "2026-08-01"
    assert lifecycle["facts"]["time"] == "Unknown"
    assert result["smallest_missing_follow_up_question"].startswith("Has 22")


def test_was_dead_discovery_language_supports_date_not_time():
    pig = animal("PIG-22", "Maya", "Maya")
    result = evaluate_health_loss_intake(
        report("Maya was dead when I found her this morning."), evidence(pig)
    )
    lifecycle = next(x for x in result["canonical_effects"] if x["area"] == "lifecycle")
    assert lifecycle["supported"] is True
    assert lifecycle["facts"]["date"] == "2026-08-01"
    assert lifecycle["facts"]["time"] == "Unknown"


def test_existing_terminal_lifecycle_and_duplicate_litter_fail_closed():
    dead = animal(lifecycle_status="Dead", lifecycle_effective_date="2026-07-30")
    with_litter = evidence(dead, matings=[{
        "mating_id": "MAT-MAYA-1", "sow_pig_id": dead["pig_id"],
        "date": "2026-04-09", "is_open": True,
    }])
    with_litter["litters"] = [{
        "litter_id": "LIT-1", "sow_pig_id": dead["pig_id"],
        "farrowing_date": "2026-07-31",
    }]
    result = evaluate_health_loss_intake(
        report("Maya died yesterday while farrowing. All 10 piglets were stillborn."),
        with_litter,
    )
    assert result["status"] == "chronology_conflict"
    assert result["canonical_effects"] == []


def test_confirmation_binds_exact_preview_and_protected_set():
    _maya, canonical = maya_packet()
    result = evaluate_health_loss_intake(report(
        "Maya died yesterday while farrowing. All 10 piglets were stillborn."
    ), canonical)
    binding = result["confirmation_binding"]
    assert binding["operation_id"] == result["operation_id"]
    assert binding["preview_sha256"] == result["preview_sha256"]
    assert binding["required_confirmations"] == result["required_confirmations"]
    assert result["preview"]["after"]


def test_output_has_no_authority_for_every_supported_family():
    pig = animal("PIG-51", "51", "51")
    result = evaluate_health_loss_intake(report("Tag 51 is injured and bleeding."), evidence(pig))
    for key in (
        "writes_performed", "farm_write_authority", "medical_authority",
        "lifecycle_authority", "mating_authority", "litter_authority",
        "movement_authority", "availability_authority", "customer_authority",
    ):
        assert result[key] is False


def test_natural_reassuring_welfare_reply_is_retained_without_repeated_question():
    pig = animal("PIG-2026-E88A", "", "11")
    result = evaluate_health_loss_intake(report(
        "Pig 11 is not eating. Follow-up: Yes, Pig 11 is standing and moving around, "
        "drinking water and breathing normal.", message_id="3174"
    ), evidence(pig))
    observed = {row["fact"]: row["value"] for row in result["observed_facts"]}
    assert observed["not_eating"] is True
    assert observed["standing_reported"] is True
    assert observed["moving_reported"] is True
    assert observed["drinking_reported"] is True
    assert observed["breathing_reported"] is True
    assert result["smallest_missing_follow_up_question"] == ""
    assert result["immediate_welfare_priority"]["level"] == "monitor_closely"
    assert "reassuring" in result["immediate_welfare_priority"]["action"]
    assert "appetite" in result["immediate_welfare_priority"]["action"]

@pytest.mark.parametrize("phrase,fact", [
    ("Pig 11 is not standing.", "standing_reported"),
    ("Pig 11 is not moving around.", "moving_reported"),
    ("Pig 11 is not breathing normally.", "breathing_reported"),
    ("Pig 11 is not drinking water.", "drinking_reported"),
])
def test_negative_welfare_phrasing_is_never_converted_to_reassuring_positive(phrase, fact):
    pig = animal("PIG-2026-E88A", "", "11")
    result = evaluate_health_loss_intake(report("Pig 11 is not eating. Follow-up: " + phrase), evidence(pig))
    assert fact not in {row["fact"] for row in result["observed_facts"]}
    assert result["immediate_welfare_priority"]["level"] != "monitor_closely"

@pytest.mark.parametrize("severe", [
    "injured and bleeding",
    "vomiting",
    "has diarrhea",
    "has a fever",
])
def test_positive_core_checks_never_downgrade_serious_welfare_signs(severe):
    pig = animal("PIG-2026-E88A", "", "11")
    result = evaluate_health_loss_intake(report(
        f"Pig 11 is {severe}, but is standing, moving around, drinking water and breathing normal."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] == "urgent_assessment"

@pytest.mark.parametrize("history,fact,expected", [
    ("It was standing earlier but is not standing now.", "standing_reported", False),
    ("It was breathing normally earlier but is not breathing normally now.", "breathing_reported", False),
    ("It was not standing earlier but is standing now.", "standing_reported", True),
    ("It was not breathing normally earlier but is breathing normally now.", "breathing_reported", True),
])
def test_latest_explicit_welfare_state_wins_over_earlier_clause(history, fact, expected):
    pig = animal("PIG-2026-E88A", "", "11")
    result = evaluate_health_loss_intake(report(
        "Pig 11 is not eating. " + history + " It is drinking water."
    ), evidence(pig))
    observed = {row["fact"] for row in result["observed_facts"]}
    assert (fact in observed) is expected
    if not expected:
        assert result["immediate_welfare_priority"]["level"] != "monitor_closely"
@pytest.mark.parametrize("negative", [
    "stopped breathing normally",
    "no longer breathing normally",
    "no longer drinking",
    "cannot move",
])
def test_current_negative_core_phrasing_never_becomes_reassuring(negative):
    pig = animal("PIG-2026-E88A", "", "11")
    result = evaluate_health_loss_intake(report(
        f"Pig 11 is not eating. It is standing and drinking water but {negative}."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] != "monitor_closely"


@pytest.mark.parametrize("reassuring_negative", [
    "not vomiting",
    "no fever",
    "not bleeding",
    "no diarrhea",
    "not coughing",
])
def test_negated_serious_signs_do_not_force_urgent_assessment(reassuring_negative):
    pig = animal("PIG-2026-OTHER", "", "12")
    result = evaluate_health_loss_intake(report(
        "Pig 12 is not eating. She is standing, moving around, drinking water "
        f"and breathing normal. She is {reassuring_negative}."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] == "monitor_closely"


def test_latest_positive_serious_sign_after_negation_remains_urgent():
    pig = animal("PIG-2026-OTHER", "", "12")
    result = evaluate_health_loss_intake(report(
        "Pig 12 had no fever earlier but has fever now. She is standing, "
        "moving around, drinking water and breathing normal."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] == "urgent_assessment"
@pytest.mark.parametrize("compound_negative", [
    "no fever or bleeding",
    "no vomiting, diarrhea, or coughing",
])
def test_coordinated_negated_serious_signs_remain_reassuring(compound_negative):
    pig = animal("PIG-2026-OTHER", "", "12")
    result = evaluate_health_loss_intake(report(
        "Pig 12 is not eating. She is standing, moving around, drinking water "
        f"and breathing normal. She has {compound_negative}."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] == "monitor_closely"


def test_positive_serious_sign_after_coordinated_negation_remains_urgent():
    pig = animal("PIG-2026-OTHER", "", "12")
    result = evaluate_health_loss_intake(report(
        "Pig 12 had no fever or bleeding earlier, but is bleeding now. She is "
        "standing, drinking water and breathing normal."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] == "urgent_assessment"


@pytest.mark.parametrize("limited", [
    "drinking no water",
    "barely drinking",
    "hardly drinking",
    "barely able to stand",
    "hardly able to stand",
])
def test_limited_core_welfare_phrasing_cannot_prove_reassurance(limited):
    pig = animal("PIG-2026-E88A", "", "11")
    result = evaluate_health_loss_intake(report(
        f"Pig 11 is not eating. It is standing, drinking water and breathing normally but is {limited}."
    ), evidence(pig))
    assert result["immediate_welfare_priority"]["level"] != "monitor_closely"


def test_unknown_identity_question_preserves_unicode_punctuation():
    result = evaluate_health_loss_intake(report("A pig is not eating."), evidence())
    assert result["identity"]["question"] == "Which exact pig is this—please give its Pig ID or tag?"

@pytest.mark.parametrize("history,expected_level,has_not_drinking", [
    ("was not drinking earlier but is drinking water now", "monitor_closely", False),
    ("was drinking water earlier but is not drinking now", "urgent_assessment", True),
])
def test_latest_drinking_state_is_consistent_across_facts_and_urgency(history, expected_level, has_not_drinking):
    pig = animal("PIG-2026-OTHER", "", "12")
    result = evaluate_health_loss_intake(report(
        f"Pig 12 is not eating. She {history}. She is standing and breathing normally."
    ), evidence(pig))
    facts = {row["fact"] for row in result["observed_facts"]}
    assert result["immediate_welfare_priority"]["level"] == expected_level
    assert ("not_drinking" in facts) is has_not_drinking
    assert ("drinking_reported" in facts) is (not has_not_drinking)


@pytest.mark.parametrize("history,has_not_eating", [
    ("was not eating earlier but is eating now", False),
    ("was eating earlier but is not eating now", True),
])
def test_latest_appetite_state_does_not_emit_contradictory_current_fact(history, has_not_eating):
    pig = animal("PIG-2026-OTHER", "", "12")
    result = evaluate_health_loss_intake(report(
        f"Pig 12 {history}. She is standing, drinking water and breathing normally."
    ), evidence(pig))
    facts = {row["fact"] for row in result["observed_facts"]}
    assert ("not_eating" in facts) is has_not_eating


def test_explicit_owner_reported_mortality_date_outranks_intake_date():
    pig = animal("PIG-2026-6DD4", "", "130")
    owner_report = report(
        "Pig 130 was found dead in the pen on 2026-08-06. Pig 130 was removed and buried "
        "on 2026-08-06. No other pigs show visible signs and the pens were cleaned."
    )
    owner_report["provider_timestamp"] = "2026-08-11T14:30:00+02:00"
    canonical = evidence(pig)
    canonical["as_of_timestamp"] = "2026-08-11T14:31:00+02:00"
    result = evaluate_health_loss_intake(owner_report, canonical)
    assert result["preview"]["event_date"] == "2026-08-06"
    observed = {row["fact"]: row["value"] for row in result["observed_facts"]}
    assert observed["no_visible_signs_in_other_pigs_reported"] is True
    assert observed["pen_cleaning_reported"] is True
