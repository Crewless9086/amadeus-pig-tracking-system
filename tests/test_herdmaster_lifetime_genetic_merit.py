from datetime import date

from modules.pig_weights.herdmaster_lifetime_genetic_merit import (
    build_explainable_pair_profiles,
    build_lifetime_outcome_packet,
)

CUTOFF = date(2026, 8, 11)


def snapshot():
    return {
        "matings": [
            {"mating_id": "M1", "sow_pig_id": "S1", "boar_pig_id": "B1", "mating_date": "2026-01-01", "outcome_complete": True},
            {"mating_id": "M2", "sow_pig_id": "S1", "boar_pig_id": "B1", "mating_date": "2026-04-01", "outcome": "Not Pregnant", "outcome_complete": True},
            {"mating_id": "M3", "sow_pig_id": "S2", "boar_pig_id": "B1", "mating_date": "2026-05-01", "outcome_complete": False},
        ],
        "litters": [
            {"litter_id": "L1", "mating_id": "M1", "sow_pig_id": "S1", "boar_pig_id": "B1",
             "farrowing_date": "2026-04-25", "total_born": 4, "born_alive": 4, "weaned_count": 3},
        ],
        "pigs": [
            {"pig_id": "C1", "litter_id": "L1", "wean_date": "2026-05-25", "wean_weight_kg": 8,
             "status": "Active", "purpose": "Breeding"},
            {"pig_id": "C2", "litter_id": "L1", "wean_date": "2026-05-25", "wean_weight_kg": 9,
             "status": "Sold", "exit_date": "2026-08-01", "exit_reason": "Auction Sale"},
            {"pig_id": "C3", "litter_id": "L1", "wean_date": "2026-05-25", "wean_weight_kg": 7,
             "status": "Dead", "exit_date": "2026-07-01", "exit_reason": "Died"},
            {"pig_id": "C4", "litter_id": "L1", "status": "Dead", "exit_date": "2026-05-01", "exit_reason": "Died"},
        ],
        "weight_events": [
            {"weight_event_id": "W1", "pig_id": "C1", "weight_date": "2026-06-24", "weight_kg": 20},
            {"weight_event_id": "W2", "pig_id": "C2", "weight_date": "2026-06-25", "weight_kg": 19},
            {"weight_event_id": "W-AGE-BIASED", "pig_id": "C3", "weight_date": "2026-07-20", "weight_kg": 50},
        ],
        "sales_transactions": [{"sale_id": "SALE1", "net_total": 4470.51, "gross_total": 4180}],
        "sales_items": [{"sale_item_id": "I1", "sale_id": "SALE1", "pig_id": "C2", "line_total": None}],
        "attributable_costs": [],
    }


def test_complete_chain_preserves_counts_coverage_growth_mortality_and_lot_value():
    packet = build_lifetime_outcome_packet(snapshot(), cutoff=CUTOFF)
    cohort = packet["cohorts"][0]
    assert packet["success"] is True
    assert cohort["conception_outcome"] == "supported_by_attributable_farrowing"
    assert cohort["survival_to_weaning_pct"] == 75.0
    assert cohort["weaning_weight"] == {"covered": 3, "missing": 0, "mean": 8.0, "median": 8.0, "minimum": 7.0, "maximum": 9.0}
    assert cohort["post_weaning_growth"]["30"]["covered"] == 2
    assert cohort["mortality"] == {"stillborn": 0, "pre_weaning": 1, "post_weaning": 1, "undated": 0}
    assert cohort["financial"]["attributable_individual_value"] == 0.0
    assert cohort["financial"]["lot_value_unallocated"] == 4470.51
    assert cohort["financial"]["profit_or_margin"] is None


def test_silence_never_becomes_conception_failure_and_rates_need_complete_through_coverage():
    packet = build_lifetime_outcome_packet(snapshot(), cutoff=CUTOFF)
    s2 = next(row for row in packet["opportunities"] if row["mating_id"] == "M3")
    b1 = next(row for row in packet["boar_profiles"] if row["boar_pig_id"] == "B1")
    assert s2["outcome_state"] == "Unknown"
    assert b1["conception_rate_pct"] is None
    assert b1["coverage"]["conception_complete"] is False


def test_missing_weaning_is_unknown_not_zero_and_post_weaning_age_comparison_is_bounded():
    evidence = snapshot()
    evidence["litters"][0]["weaned_count"] = None
    packet = build_lifetime_outcome_packet(evidence, cutoff=CUTOFF)
    cohort = packet["cohorts"][0]
    assert cohort["weaned_count"] is None
    assert cohort["survival_to_weaning_pct"] is None
    assert cohort["post_weaning_growth"]["60"]["covered"] == 1
    assert cohort["post_weaning_growth"]["30"]["covered"] == 2


def test_superseded_litter_and_children_never_double_count_current_evidence():
    evidence = snapshot()
    evidence["litters"].append({"litter_id": "L-DUP", "mating_id": "M1", "sow_pig_id": "S1", "boar_pig_id": "B1",
                                "farrowing_date": "2026-04-25", "born_alive": 10, "weaned_count": 10})
    evidence["pigs"].append({"pig_id": "C-DUP", "litter_id": "L-DUP", "status": "Active"})
    evidence["superseded_litter_ids"] = ["L-DUP"]
    evidence["superseded_pig_ids"] = ["C-DUP"]
    packet = build_lifetime_outcome_packet(evidence, cutoff=CUTOFF)
    assert [row["litter_id"] for row in packet["cohorts"]] == ["L1"]
    assert packet["pair_profiles"][0]["born_alive"] == 4


def test_mixed_lot_value_is_not_attributed_to_one_litter_or_divided_per_pig():
    evidence = snapshot()
    evidence["pigs"].append({"pig_id": "OTHER", "status": "Sold"})
    evidence["sales_items"].append({"sale_item_id": "I2", "sale_id": "SALE1", "pig_id": "OTHER", "line_total": None})
    cohort = build_lifetime_outcome_packet(evidence, cutoff=CUTOFF)["cohorts"][0]
    assert cohort["financial"]["lot_value_unallocated"] == 0
    assert cohort["financial"]["mixed_or_external_lot_ids"] == ["SALE1"]
    assert cohort["financial"]["profit_or_margin"] is None


def test_pair_profiles_separate_exact_sow_boar_evidence_and_known_relationship_exclusion():
    packet = build_lifetime_outcome_packet(snapshot(), cutoff=CUTOFF)
    result = build_explainable_pair_profiles(
        packet,
        females=[{"pig_id": "S1", "name": "Lolly", "eligible": True}],
        boars=[{"pig_id": "B1", "name": "Bola", "available": True},
               {"pig_id": "B2", "name": "Prince", "available": True, "controlled_trial_eligible": True}],
        relationships=[{"sow_pig_id": "S1", "boar_pig_id": "B1", "status": "excluded", "reasons": ["known shared ancestor"]}],
    )
    bola = next(row for row in result["profiles"] if row["boar_pig_id"] == "B1")
    prince = next(row for row in result["profiles"] if row["boar_pig_id"] == "B2")
    assert bola["classification"] == "Held/excluded"
    assert bola["exact_pair"]["attributable_litter_count"] == 1
    assert prince["classification"] == "Controlled trial"
    assert result["controlled_trials"][0]["boar_name"] == "Prince"
    assert result["female_rankings"][0]["primary_boar_pig_id"] is None
    assert result["mating_execution_enabled"] is False


def test_controlled_trial_uses_well_documented_sow_and_capacity_is_bounded():
    packet = build_lifetime_outcome_packet(snapshot(), cutoff=CUTOFF)
    result = build_explainable_pair_profiles(
        packet,
        females=[{"pig_id": "S1", "name": "Lolly", "eligible": True},
                 {"pig_id": "S2", "name": "New Sow", "eligible": True}],
        boars=[{"pig_id": "B2", "name": "Prince", "available": True, "controlled_trial_eligible": True}],
        controlled_trial_capacity=1,
    )
    assert len(result["controlled_trials"]) == 1
    assert result["controlled_trials"][0]["sow_pig_id"] == "S1"
    limited = next(row for row in result["profiles"] if row["sow_pig_id"] == "S2")
    assert limited["classification"] == "Limited evidence"


def test_proven_or_supported_pair_ranks_before_unproven_trial_without_using_workload():
    packet = build_lifetime_outcome_packet(snapshot(), cutoff=CUTOFF)
    result = build_explainable_pair_profiles(
        packet, females=[{"pig_id": "S1", "name": "Lolly", "eligible": True}],
        boars=[{"pig_id": "B1", "name": "Bola", "available": True},
               {"pig_id": "B2", "name": "Prince", "available": True, "controlled_trial_eligible": True}],
    )
    ranking = result["female_rankings"][0]
    assert ranking["primary_boar_pig_id"] == "B1"
    assert ranking["ranked_boar_ids"] == ["B1"]
    assert result["controlled_trials"][0]["boar_pig_id"] == "B2"


def test_conflicting_litter_counts_fail_survival_axis_to_unknown_not_impossible_rate():
    evidence = snapshot(); evidence["litters"][0]["weaned_count"] = 5
    packet = build_lifetime_outcome_packet(evidence, cutoff=CUTOFF)
    cohort = packet["cohorts"][0]
    assert cohort["count_conflict"] is True
    assert cohort["survival_to_weaning_pct"] is None
    assert any(row["source_family"] == "litter_count_chronology" for row in packet["attribution_gaps"])


def test_one_small_litter_remains_supported_not_proven_and_exposes_sample_size():
    packet = build_lifetime_outcome_packet(snapshot(), cutoff=CUTOFF)
    result = build_explainable_pair_profiles(
        packet, females=[{"pig_id": "S1", "name": "Lolly", "eligible": True}],
        boars=[{"pig_id": "B1", "name": "Bola", "available": True}],
    )
    profile = result["profiles"][0]
    assert profile["classification"] == "Supported cross"
    assert profile["exact_pair"]["attributable_litter_count"] == 1
    assert profile["axes"]["survival_robustness"]["value"] == 75.0


def test_replay_is_deterministic_and_zero_authority_when_input_order_changes():
    evidence = snapshot()
    first = build_lifetime_outcome_packet(evidence, cutoff=CUTOFF)
    reordered = {**evidence, "matings": list(reversed(evidence["matings"])),
                 "pigs": list(reversed(evidence["pigs"])), "weight_events": list(reversed(evidence["weight_events"]))}
    second = build_lifetime_outcome_packet(reordered, cutoff=CUTOFF)
    assert first["packet_id"] == second["packet_id"]
    assert first["writes_performed"] is first["delivery_enabled"] is first["mating_execution_enabled"] is False


def test_new_weaning_materially_refreshes_packet_identity():
    before = snapshot(); before["litters"][0]["weaned_count"] = None
    after = snapshot()
    assert build_lifetime_outcome_packet(before, cutoff=CUTOFF)["packet_id"] != build_lifetime_outcome_packet(after, cutoff=CUTOFF)["packet_id"]
