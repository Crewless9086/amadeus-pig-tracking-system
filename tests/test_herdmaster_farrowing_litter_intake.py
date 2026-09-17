from modules.pig_weights.herdmaster_farrowing_litter_intake import prepare_farrowing_litter_preview


def evidence(*, matings=(), litters=()):
    return {"evidence_generation": "GEN-1", "animals": [
        {"pig_id": "PIG-2026-5AA8", "tag_number": "Linda", "name": "Linda", "status": "Active", "on_farm": True, "sex": "Female"},
        {"pig_id": "PIG-NUM-22", "tag_number": "22", "name": "22", "status": "Active", "on_farm": True, "sex": "Male"},
        {"pig_id": "PIG-NUM-9", "tag_number": "9", "name": "Nine", "status": "Active", "on_farm": True, "sex": "Male"},
        {"pig_id": "BOAR-1", "tag_number": "Tyson", "name": "Tyson", "status": "Active", "on_farm": True, "sex": "Male"},
    ], "matings": list(matings), "litters": list(litters)}


def report(**overrides):
    facts = {"sow_ref": "Linda", "farrowing_date": "2026-08-22",
             "total_born": 9, "born_alive": 8, "stillborn": None,
             "mummified": 1, "died_after_live_birth": None,
             "mating_ref": None, "father_ref": None}
    facts.update(overrides)
    return {"authenticated": True, "provider_message_id": "TG-07020-CORRECTED",
            "authenticated_principal_id": "OWNER-CHARL", "farrowing_litter": facts}


def test_corrected_linda_facts_resolve_without_numeric_identity_collision():
    result = prepare_farrowing_litter_preview(report(), evidence())
    assert result["success"] is True
    assert result["sow"]["pig_id"] == "PIG-2026-5AA8"
    assert result["counts"] == {"total_born": 9, "born_alive": 8, "stillborn": 0,
        "mummified": 1, "died_after_live_birth": 0, "alive_now": 8,
        "arithmetic": "9=8+0+1"}
    assert result["mating"]["state"] == "unknown"
    assert result["preview"]["father_pig_id"] is None
    assert result["preview"]["piglet_identity_count"] == 8
    assert result["preview"]["mummified_identity_count"] == 0


def test_exactly_one_compatible_unlinked_mating_is_attributed():
    mating = {"mating_id": "MAT-1", "sow_pig_id": "PIG-2026-5AA8",
              "boar_pig_id": "BOAR-1", "mating_date": "2026-04-30",
              "linked_litter_id": None}
    result = prepare_farrowing_litter_preview(report(), evidence(matings=[mating]))
    assert result["mating"] == {"state": "attributed", "mating_id": "MAT-1",
        "boar_pig_id": "BOAR-1", "conflicting_mating_ids": []}


def test_multiple_matings_request_one_candidate_specific_clarification():
    rows = [{"mating_id": key, "sow_pig_id": "PIG-2026-5AA8",
             "boar_pig_id": "BOAR-1", "mating_date": day, "linked_litter_id": None}
            for key, day in (("MAT-A", "2026-04-25"), ("MAT-B", "2026-05-01"))]
    result = prepare_farrowing_litter_preview(report(), evidence(matings=rows))
    assert result["status"] == "mating_clarification_required"
    assert result["question"] == "Which mating applies: MAT-A, MAT-B?"


def test_existing_same_sow_and_date_blocks_duplicate_before_preview():
    result = prepare_farrowing_litter_preview(report(), evidence(litters=[
        {"litter_id": "LIT-EXISTING", "sow_pig_id": "PIG-2026-5AA8",
         "farrowing_date": "2026-08-22"}]))
    assert result["status"] == "canonical_litter_already_exists"


def test_conflicting_father_contains_only_linkage_and_keeps_litter_preview():
    mating = {"mating_id": "MAT-1", "sow_pig_id": "PIG-2026-5AA8",
              "boar_pig_id": "BOAR-1", "mating_date": "2026-04-30",
              "linked_litter_id": None}
    result = prepare_farrowing_litter_preview(
        report(father_ref="A-DIFFERENT-BOAR"), evidence(matings=[mating]))
    assert result["success"] is True
    assert result["mating"]["state"] == "linkage_conflict_contained"
    assert result["preview"]["mating_id"] is None
    assert result["preview"]["father_pig_id"] is None


def test_arithmetic_conflict_fails_closed():
    result = prepare_farrowing_litter_preview(
        report(total_born=9, born_alive=8, stillborn=1, mummified=1), evidence())
    assert result["status"] == "litter_count_arithmetic_conflict"


def test_semantically_selected_linda_ignores_dates_and_counts_as_animal_refs():
    result = prepare_farrowing_litter_preview(report(), evidence())
    assert result["sow"]["candidate_pig_ids"] if result["sow"]["state"] != "resolved" else True
    assert result["sow"]["pig_id"] == "PIG-2026-5AA8"


def test_male_or_inactive_animal_cannot_be_used_as_sow():
    for changes in ({"sex": "Male"}, {"status": "Dead", "on_farm": False}):
        canonical = evidence()
        canonical["animals"][0].update(changes)
        result = prepare_farrowing_litter_preview(report(), canonical)
        assert result["status"] == "current_active_on_farm_sow_required"


def test_terminal_mating_state_is_not_attributed():
    mating = {"mating_id": "MAT-FAILED", "sow_pig_id": "PIG-2026-5AA8",
              "boar_pig_id": "BOAR-1", "mating_date": "2026-04-30",
              "linked_litter_id": None, "outcome": "Failed"}
    result = prepare_farrowing_litter_preview(report(), evidence(matings=[mating]))
    assert result["success"] is True and result["mating"]["state"] == "unknown"


def test_correction_requires_exact_existing_target_and_reason():
    existing = {"litter_id": "LIT-OLD", "sow_pig_id": "PIG-2026-5AA8",
                "farrowing_date": "2026-08-22"}
    missing_reason = prepare_farrowing_litter_preview(
        report(correction_of_litter_id="LIT-OLD"), evidence(litters=[existing]))
    assert missing_reason["status"] == "litter_correction_reason_required"
    corrected = prepare_farrowing_litter_preview(report(
        correction_of_litter_id="LIT-OLD", correction_reason="Owner corrected count"),
        evidence(litters=[existing]))
    assert corrected["success"] is True
    assert corrected["preview"]["correction_of_litter_id"] == "LIT-OLD"
