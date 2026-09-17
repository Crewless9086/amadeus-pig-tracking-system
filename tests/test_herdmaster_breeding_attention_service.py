from datetime import date

from modules.pig_weights.herdmaster_breeding_attention_service import (
    build_bounded_family_evidence,
    build_breeding_attention,
)


def female(**overrides):
    row = {
        "pig_id": "PIG-SOW-1", "tag_number": "51", "sex": "Female",
        "animal_type": "Sow", "status": "Active", "on_farm": "Yes",
        "medical_status": "Clear", "withdrawal_evidence_state": "cleared",
        "available_for_breeding": "available", "purpose": "Breeding",
    }
    row.update(overrides)
    return row


def packet(row=None, **kwargs):
    return build_breeding_attention(
        {"success": True, "pigs": [row or female()], "source": "supabase_canonical", "generated_date": "2026-07-27"},
        matings={"success": True, "records": kwargs.pop("matings", [])},
        litters={"success": True, "litters": kwargs.pop("litters", [])},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {"PIG-SOW-1": {"mother": {"pig_id": "DAM"}, "father": {"pig_id": "SIRE"}}}},
        observations={"success": True, "by_pig": kwargs.pop("observations", {"PIG-SOW-1": {"heat_state": "observed", "body_condition_score": 3}})},
        today=date(2026, 7, 27),
        **kwargs,
    )


def test_complete_current_evidence_is_ready_for_human_review_only():
    result = packet()
    assert result["animals"][0]["current_state"] == "Ready for review"
    assert result["animals"][0]["advisory_only"] is True
    assert result["writes_performed"] is False


def test_missing_envelope_is_unavailable_not_zero():
    result = build_breeding_attention(None)
    assert result["female_count"] is None
    assert result["source_status"] == "Unavailable"


def test_missing_heat_and_body_condition_are_optional_for_current_review():
    result = packet(female(), observations={"PIG-SOW-1": {}})
    assert result["animals"][0]["current_state"] == "Ready for review"
    assert "current heat observation" not in result["animals"][0]["missing_facts"]
    assert "body condition" not in result["animals"][0]["missing_facts"]


def test_stale_mating_does_not_assert_recently_mated():
    result = packet(matings=[{"sow_pig_id": "PIG-SOW-1", "mating_date": "2025-01-01"}])
    assert result["animals"][0]["current_state"] == "Ready for review"


def test_recent_mating_is_evidence_not_mating_recommendation():
    result = packet(matings=[{"sow_pig_id": "PIG-SOW-1", "mating_date": "2026-07-10"}])
    row = result["animals"][0]
    assert row["current_state"] == "Recently mated"
    assert row["recommended_human_action"] == "verify mating history"


def test_conflicting_pregnancy_evidence_needs_data():
    result = packet(matings=[{"sow_pig_id": "PIG-SOW-1", "pregnancy_check_result": "Pregnant"}])
    assert result["animals"][0]["current_state"] == "Needs Data"
    assert result["animals"][0]["confidence"] == "Low"


def test_medical_or_withdrawal_hold_has_priority():
    result = packet(female(medical_status="Hold", withdrawal_evidence_state="hold"))
    assert result["animals"][0]["current_state"] == "Hold"
    assert result["animals"][0]["recommended_human_action"] == "veterinary/medical review required"


def test_recent_litter_requires_recovery_review():
    result = packet(litters=[{"sow_pig_id": "PIG-SOW-1", "farrowing_date": "2026-07-01"}])
    assert result["animals"][0]["current_state"] == "Post-litter recovery"


def test_missing_family_tree_fails_closed():
    result = build_breeding_attention(
        {"success": True, "pigs": [female()], "generated_date": "2026-07-27"},
        matings={"success": True, "records": []},
        litters={"success": True, "litters": []},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {}},
        observations={"success": True, "by_pig": {}}, today=date(2026, 7, 27),
    )
    assert result["animals"][0]["current_state"] == "Needs Data"
    assert "family-tree constraints" in result["animals"][0]["missing_facts"]


def test_idle_complete_animal_is_not_omitted():
    result = packet()
    assert result["female_count"] == 1
    assert result["counts"]["Ready for review"] == 1


def test_non_current_or_non_female_animals_are_excluded():
    result = build_breeding_attention(
        {"success": True, "pigs": [female(sex="Male"), female(status="Exited")], "generated_date": "2026-07-27"},
        matings={"success": True, "records": []}, litters={"success": True, "litters": []},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {}}, observations={"success": True, "by_pig": {}},
        today=date(2026, 7, 27),
    )
    assert result["female_count"] == 0


def test_failed_or_malformed_dependency_is_unavailable_not_zero():
    result = build_breeding_attention(
        {"success": False, "pigs": []},
        matings={"success": True, "records": []}, litters={"success": True, "litters": []},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {}}, observations={"success": True, "by_pig": {}},
    )
    assert result["female_count"] is None
    assert result["source_status"] == "Unavailable"


def test_stale_source_is_not_fresh():
    result = build_breeding_attention(
        {"success": True, "pigs": [female()], "generated_date": "2026-07-20"},
        matings={"success": True, "records": []}, litters={"success": True, "litters": []},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {"PIG-SOW-1": {"mother": {}, "father": {}}}},
        observations={"success": True, "by_pig": {"PIG-SOW-1": {}}},
        today=date(2026, 7, 27),
    )
    assert result["animals"][0]["freshness"] == "Stale"


def test_overdue_check_remains_visible_in_declared_pregnancy_filter():
    result = packet(matings=[{
        "sow_pig_id": "PIG-SOW-1", "mating_date": "2026-06-01",
        "is_overdue_check": "Yes", "mating_status": "Open",
    }])
    row = result["animals"][0]
    assert row["current_state"] == "Pregnancy check overdue"
    assert row["filter_state"] == "Pregnancy evidence"
    assert result["counts"]["Pregnancy evidence"] == 1


def test_unavailable_observation_source_fails_closed_globally():
    result = build_breeding_attention(
        {"success": True, "pigs": [female()], "generated_date": "2026-07-27"},
        matings={"success": True, "records": []}, litters={"success": True, "litters": []},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "by_pig": {}},
        observations={"success": False},
    )
    assert result["source_status"] == "Unavailable"
    assert result["female_count"] is None


def _master(pig_id, mother="", father=""):
    return {"Pig_ID": pig_id, "Mother_Pig_ID": mother, "Father_Pig_ID": father}


def test_batched_lineage_large_shared_family_is_one_query_and_deterministic():
    rows = [_master("DAM"), _master("SIRE")]
    roots = []
    for index in range(100):
        pig_id = f"SOW-{index:03d}"
        roots.append(pig_id)
        rows.append(_master(pig_id, "DAM", "SIRE"))
    first = build_bounded_family_evidence(rows, reversed(roots), max_depth=1, max_nodes=256)
    second = build_bounded_family_evidence(rows, roots, max_depth=1, max_nodes=256)
    assert first == second
    assert first["query_count"] == 1
    assert list(first["by_pig"]) == sorted(roots)


def test_lineage_cycle_is_partial_for_only_affected_animal():
    result = build_bounded_family_evidence(
        [_master("SOW-1", "DAM", "SIRE"), _master("DAM", "SOW-1", "SIRE"), _master("SIRE")],
        ["SOW-1"], max_depth=3,
    )
    assert result["status"] == "partial"
    assert "lineage_cycle" in result["by_pig"]["SOW-1"]["reasons"]


def test_missing_parent_is_partial_not_inventory_loss():
    result = build_bounded_family_evidence(
        [_master("SOW-1", "MISSING", "SIRE"), _master("SIRE")], ["SOW-1"], max_depth=1,
    )
    assert result["requested_count"] == 1
    assert result["partial_count"] == 1
    assert result["by_pig"]["SOW-1"]["mother"] is None


def test_duplicate_identity_is_malformed_and_fail_closed():
    result = build_bounded_family_evidence(
        [_master("SOW-1", "DAM", "SIRE"), _master("SOW-1", "OTHER", "SIRE")], ["SOW-1"],
    )
    assert result["by_pig"]["SOW-1"]["lineage_status"] == "partial"
    assert "current_animal_link_missing_or_malformed" in result["by_pig"]["SOW-1"]["reasons"]


def test_node_limit_and_deadline_exhaustion_preserve_partial_results():
    chain = [_master(f"P{index}", f"P{index + 1}", f"F{index}") for index in range(20)]
    chain += [_master(f"F{index}") for index in range(20)]
    node_limited = build_bounded_family_evidence(chain, ["P0"], max_depth=20, max_nodes=4)
    assert "lineage_node_limit_exhausted" in node_limited["by_pig"]["P0"]["missing_links"]
    ticks = iter([0.0, 0.0, 0.0, 2.0, 2.0, 2.0])
    deadline = build_bounded_family_evidence(
        [_master("SOW-1", "DAM", "SIRE"), _master("DAM"), _master("SIRE")],
        ["SOW-1"], deadline_seconds=1.0, now_fn=lambda: next(ticks),
    )
    assert deadline["status"] == "partial"
    assert "lineage_deadline_exhausted" in deadline["by_pig"]["SOW-1"]["missing_links"]


def test_partial_family_evidence_keeps_complete_inventory_and_reconciled_counts():
    result = build_breeding_attention(
        {"success": True, "pigs": [female()], "generated_date": "2026-07-27"},
        matings={"success": True, "records": []}, litters={"success": True, "litters": []},
        analytics={"success": True, "sows": []},
        family_trees={"success": True, "status": "partial", "by_pig": {
            "PIG-SOW-1": {
                "mother": {"pig_id": "DAM"}, "father": {"pig_id": "SIRE"},
                "lineage_status": "partial",
            }
        }},
        observations={"success": True, "by_pig": {"PIG-SOW-1": {"heat_state": "standing", "body_condition_score": 3}}},
        today=date(2026, 7, 27),
    )
    assert result["female_count"] == 1
    assert result["inventory_status"] == "complete"
    assert result["evidence_status"] == "partial"
    assert result["counts_reconcile"] is True
    assert result["animals"][0]["current_state"] == "Needs Data"


def test_owner_payload_has_no_medical_details_and_zero_authority():
    result = packet(female(private_medical_note="secret", customer_name="private"))
    serialized = str(result)
    assert "secret" not in serialized and "private_medical_note" not in serialized
    assert "customer_name" not in serialized
    assert result["protected_actions_performed"] is False
