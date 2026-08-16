from copy import deepcopy
from datetime import date

from modules.pig_weights.herdmaster_full_lifecycle_merit import (
    _safe_route_segment,
    compose_full_lifecycle_merit,
)


def evidence():
    contexts = {f"{name}_context": "comparable" for name in ("management", "season", "environment", "feed", "health")}
    return {
        "cutoff": date(2026, 8, 13),
        "pigs": [
            {"pig_id": "S1", "name": "Bonnie", "tag_number": "TAG-1", "sex": "Female"},
            {"pig_id": "B1", "name": "Prince", "tag_number": "TAG-B", "sex": "Male"},
            {"pig_id": "C1", "name": None, "tag_number": "PIGLET-1", "sex": "Female", "litter_id": "L1"},
        ],
        "litters": [
            {"litter_id": "L0", "sow_pig_id": "S1", "boar_pig_id": "B1", "farrowing_date": "2026-01-01", "litter_status": "Weaned", "born_alive": 7, "weaned_count": 1, **contexts},
            {"litter_id": "L1", "supersedes_litter_id": "L0", "sow_pig_id": "S1", "boar_pig_id": "B1", "farrowing_date": "2026-01-01", "litter_status": "Weaned", "born_alive": 8, "weaned_count": 7, **contexts},
            {"litter_id": "L2", "sow_pig_id": "S1", "boar_pig_id": "B1", "farrowing_date": "2026-03-01", "born_alive": 9, "weaned_count": None, **contexts},
        ],
        "observations": [
            {"observation_event_id": "O1", "pig_id": "S1", "observed_at": "2026-08-01", "factual_note": "old"},
            {"observation_event_id": "O2", "supersedes_observation_event_id": "O1", "pig_id": "S1", "observed_at": "2026-08-02", "factual_note": "corrected"},
        ],
        "lifecycle": [],
        "weights": [{"weight_event_id": "W1", "pig_id": "C1", "weight_date": "2026-06-01", "weight_kg": 20}],
    }


def test_unknown_outcome_stays_null_and_lineage_is_append_only():
    result = compose_full_lifecycle_merit(evidence(), pig_id="S1")
    row = result["rows"][0]
    assert result["writes_performed"] is False
    assert row["identity"]["display_name"] == "Bonnie"
    assert row["litter_outcomes"] == {
        "rate": 7 / 8, "weaned_numerator": 7.0, "born_alive_denominator": 8.0,
        "eligible_litter_count": 1, "observed_litter_count": 2, "missing_litter_count": 1,
    }
    assert result["lineage"]["litters"]["superseded_event_ids"] == ["L0"]
    assert [row["observation_event_id"] for row in result["lineage"]["observations"]["events"]] == ["O1", "O2"]
    assert row["health_observation_context"]["observations"][0]["observation_event_id"] == "O2"


def test_missing_outcomes_never_become_zero_and_named_unknown_fails_closed():
    data = evidence()
    data["litters"] = [{**data["litters"][-1], "litter_id": "L3"}]
    row = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]
    assert row["litter_outcomes"]["rate"] is None
    assert row["litter_outcomes"]["born_alive_denominator"] is None
    assert row["confidence"]["label"] == "Unknown"
    assert compose_full_lifecycle_merit(data, pig_id="NOPE")["reason"] == "unknown_pig_id"


def test_confidence_is_deterministic_monotonic_and_not_a_merit_score():
    data = evidence()
    contexts = {f"{name}_context": "comparable" for name in ("management", "season", "environment", "feed", "health")}
    data["litters"] = [
        {"litter_id": f"L{i}", "sow_pig_id": "S1", "boar_pig_id": "B1", "farrowing_date": f"2026-0{i}-01", "litter_status": "Weaned", "born_alive": 8, "weaned_count": 7, **contexts}
        for i in range(1, 4)
    ]
    first = compose_full_lifecycle_merit(data, pig_id="S1")
    second = compose_full_lifecycle_merit(deepcopy(data), pig_id="S1")
    assert first == second
    assert first["rows"][0]["confidence"]["label"] == "High"
    assert "score" not in first["rows"][0]
    assert "do not prove genetic causation" in first["association_boundary"]


def test_future_and_superseded_evidence_do_not_govern_current_projection():
    data = evidence()
    data["observations"].append({"observation_event_id": "FUTURE", "pig_id": "S1", "observed_at": "2027-01-01", "factual_note": "future"})
    result = compose_full_lifecycle_merit(data, pig_id="S1")
    assert [r["observation_event_id"] for r in result["rows"][0]["health_observation_context"]["observations"]] == ["O2"]
    assert len(result["lineage"]["observations"]["events"]) == 2


def test_named_packet_does_not_expose_other_animal_lineage():
    data = evidence()
    data["pigs"].append({"pig_id": "S2", "pig_name": "Other", "sex": "Female", "purpose": "Breeding"})
    data["observations"].append({"observation_event_id": "OTHER", "pig_id": "S2", "observed_at": "2026-08-01", "factual_note": "private other fact"})
    result = compose_full_lifecycle_merit(data, pig_id="S1")
    assert "OTHER" not in {r["observation_event_id"] for r in result["lineage"]["observations"]["events"]}


def test_planned_wean_and_invalid_counts_remain_unknown():
    data = evidence()
    data["litters"] = [{
        "litter_id": "PLANNED", "sow_pig_id": "S1", "boar_pig_id": "B1",
        "farrowing_date": "2026-07-01", "wean_date": "2026-09-01",
        "born_alive": 8, "weaned_count": 0,
    }]
    planned = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]
    assert planned["litter_outcomes"]["rate"] is None
    assert planned["partner_comparisons"][0]["survival_rate"] is None
    assert planned["time_trend"][0]["survival_rate"] is None
    assert planned["confidence"]["label"] == "Unknown"
    data["litters"][0].update(litter_status="Weaned", weaned_count=9)
    conflicting = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]
    assert conflicting["litter_outcomes"]["rate"] is None
    assert conflicting["partner_comparisons"][0]["survival_rate"] is None
    assert conflicting["time_trend"][0]["survival_rate"] is None


def test_undated_facts_are_warnings_not_governing_evidence():
    data = evidence()
    data["litters"].append({"litter_id": "UNDATED", "sow_pig_id": "S1", "boar_pig_id": "B1", "litter_status": "Weaned", "born_alive": 10, "weaned_count": 0})
    result = compose_full_lifecycle_merit(data, pig_id="S1")
    assert result["data_quality"]["undated_litter_rows"] == 1
    assert "UNDATED" not in result["rows"][0]["evidence_lineage"]["litter_ids"]


def test_exact_parent_participation_resolves_unknown_sex_without_boar_default():
    data = evidence()
    data["pigs"][0]["sex"] = "Unknown"
    result = compose_full_lifecycle_merit(data, pig_id="S1")
    assert result["rows"][0]["breeding_role"] == "sow"
    assert result["rows"][0]["litter_outcomes"]["eligible_litter_count"] == 1


def test_populated_but_different_context_cannot_be_high_confidence():
    data = evidence()
    contexts = ["pen-a", "pen-b", "pen-c"]
    data["litters"] = [{
        "litter_id": f"L{i}", "sow_pig_id": "S1", "boar_pig_id": "B1",
        "farrowing_date": f"2026-0{i}-01", "litter_status": "Weaned",
        "born_alive": 8, "weaned_count": 7,
        "management_context": contexts[i - 1], "season_context": "same",
        "environment_context": "same", "feed_context": "same", "health_context": "same",
    } for i in range(1, 4)]
    result = compose_full_lifecycle_merit(data, pig_id="S1")
    assert result["rows"][0]["confidence"]["label"] == "Limited"


def test_conflicting_exact_parent_roles_fail_closed():
    data = evidence()
    data["litters"].append({
        "litter_id": "CONFLICT", "sow_pig_id": "B1", "boar_pig_id": "S1",
        "farrowing_date": "2026-04-01", "litter_status": "Weaned",
        "born_alive": 8, "weaned_count": 7,
    })
    row = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]
    assert row["breeding_role"] == "Unknown-conflicting"
    assert row["litter_outcomes"]["observed_litter_count"] == 0


def test_human_identity_relationships_are_names_first_and_route_safe():
    contexts = {f"{name}_context": "same governed cohort" for name in (
        "management", "season", "environment", "feed", "health")}
    data = {
        "cutoff": date(2026, 8, 13),
        "pigs": [
            {"pig_id": "PIG-2026-TYSON", "name": "Tyson", "tag_number": "T-014", "animal_type": "Boar"},
            {"pig_id": "PIG-2026-MOLLY", "name": "Molly", "tag_number": "M-027", "animal_type": "Sow"},
            {"pig_id": "PIG-2026-PRINCE", "name": "Prince", "tag_number": "P-009", "animal_type": "Boar"},
            {"pig_id": "PIG-2026-0632", "name": "Bella", "tag_number": "0632", "litter_id": "LIT-2026-5C36"},
            {"pig_id": "PIG/unsafe?next=https://evil.example", "name": None, "tag_number": None,
             "litter_id": "LIT-2026-5C36"},
        ],
        "litters": [{
            "litter_id": "LIT-2026-5C36", "sow_pig_id": "PIG-2026-MOLLY",
            "boar_pig_id": "PIG-2026-TYSON", "farrowing_date": "2026-05-20",
            "litter_status": "Weaned", "born_alive": 8, "weaned_count": 7, **contexts,
        }],
        "observations": [], "lifecycle": [], "matings": [], "weights": [], "medical": [],
    }
    result = compose_full_lifecycle_merit(data, pig_id="PIG-2026-TYSON")
    row = result["rows"][0]

    assert result["identity_contract_version"] == "herdmaster_human_identity_v1"
    assert row["identity"]["display_name"] == "Tyson"
    assert row["identity"]["secondary_identity"] == "T-014"
    assert row["identity"]["technical_identity"] == {"pig_id": "PIG-2026-TYSON"}
    assert row["partner_comparisons"][0]["partner_identity"]["display_name"] == "Molly"
    assert row["partner_comparisons"][0]["destination"]["href"] == "/breeding-analytics/PIG-2026-MOLLY"

    litter = row["time_trend"][0]["litter_identity"]
    assert litter["sow_identity"]["display_name"] == "Molly"
    assert litter["destination"]["href"].startswith("/litter/LIT-2026-5C36?")
    assert "return_to=%2Fbreeding-analytics%2FPIG-2026-TYSON" in litter["destination"]["href"]

    offspring = row["family_relationships"]["offspring_identities"]
    assert offspring[0]["display_name"] == "Bella"
    unknown = next(item for item in offspring if item["pig_id"].startswith("PIG/unsafe"))
    assert unknown["display_name"] == "Unknown"
    assert unknown["presentation_state"] == "unknown"
    assert unknown["technical_identity"]["pig_id"].startswith("PIG/unsafe")
    assert unknown["destination"]["href"] is None
    assert unknown["destination"]["unavailable_reason"] == "unsafe_route_identity"


def test_unresolved_partner_identity_fails_closed_without_a_destination():
    data = evidence()
    data["pigs"] = [row for row in data["pigs"] if row["pig_id"] != "B1"]
    partner = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]["partner_comparisons"][0]
    assert partner["partner_identity"]["display_name"] == "Unknown"
    assert partner["partner_identity"]["technical_identity"] == {"pig_id": "B1"}
    assert partner["destination"]["href"] is None
    assert partner["destination"]["unavailable_reason"] == "canonical_animal_identity_unresolved"


def test_dot_encoded_separator_and_control_route_segments_fail_closed():
    for value in (".", "..", "%2e%2e", "%252e%252e", "pig/child", "pig\\child", "pig\nchild"):
        assert _safe_route_segment(value) is None

    data = evidence()
    data["pigs"][0]["pig_id"] = ".."
    for litter in data["litters"]:
        litter["sow_pig_id"] = ".."
    row = compose_full_lifecycle_merit(data, pig_id="..")["rows"][0]
    assert row["identity"]["destination"]["href"] is None
    assert row["identity"]["destination"]["unavailable_reason"] == "unsafe_route_identity"
    assert all(item["destination"]["href"] is None for item in row["time_trend"])

    data = evidence()
    data["litters"][1]["litter_id"] = "."
    data["litters"][1].pop("supersedes_litter_id")
    row = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]
    unsafe_litter = next(item for item in row["time_trend"] if item["litter_id"] == ".")
    assert unsafe_litter["destination"]["href"] is None


def test_tyson_individual_matings_are_distinct_from_partner_aggregates_and_offspring_keep_state():
    cutoff = date(2026, 8, 13)
    partner_ids = ["PIG-2025-MOLLY", "PIG-2025-BONNIE", "PIG-2025-WAKI", "PIG-2025-TEENA"]
    pigs = [{"pig_id": "PIG-2025-TYSON", "pig_name": "Tyson", "tag_number": "014",
             "animal_type": "Boar", "status": "Active", "purpose": "Breeding", "on_farm": True}]
    pigs.extend({"pig_id": partner, "pig_name": partner.split("-")[-1].title(),
                 "animal_type": "Sow", "status": "Active", "purpose": "Breeding", "on_farm": True}
                for partner in partner_ids)
    litters, matings = [], []
    for index in range(6):
        partner = partner_ids[index % 4]
        litter_id = f"LIT-2026-TYSON-{index + 1:02d}"
        mating_id = f"MAT-2026-TYSON-{index + 1:02d}"
        matings.append({"mating_id": mating_id, "mating_date": f"2026-0{index + 1}-01",
                        "sow_pig_id": partner, "boar_pig_id": "PIG-2025-TYSON",
                        "related_litter_id": litter_id, "status": "Farrowed"})
        litters.append({"litter_id": litter_id, "mating_id": mating_id, "sow_pig_id": partner,
                        "boar_pig_id": "PIG-2025-TYSON", "farrowing_date": f"2026-0{index + 2}-01",
                        "litter_status": "Weaned", "born_alive": 7, "weaned_count": 6})
    for index in range(37):
        pigs.append({"pig_id": f"PIG-2026-TYSON-OFFSPRING-{index + 1:02d}",
                     "pig_name": f"Tyson offspring {index + 1}", "tag_number": f"T{index + 1:03d}",
                     "litter_id": litters[index % 6]["litter_id"], "animal_type": "Weaner",
                     "status": "Active", "purpose": "Grower", "on_farm": index % 5 != 0})
    source = {"cutoff": cutoff, "pigs": pigs, "litters": litters, "litter_history": litters,
              "matings": matings, "observations": [], "lifecycle": [], "weights": [], "medical": []}

    first = compose_full_lifecycle_merit(source, pig_id="PIG-2025-TYSON")
    second = compose_full_lifecycle_merit(source, pig_id="PIG-2025-TYSON")
    row = first["rows"][0]
    assert row["breeding_opportunities"]["observed_count"] == 6
    assert len(row["individual_mating_summaries"]) == 6
    assert [item["mating_id"] for item in row["individual_mating_summaries"]] == sorted(
        item["mating_id"] for item in row["individual_mating_summaries"])
    assert len(row["partner_comparisons"]) == 4
    assert row["partner_comparisons_semantics"] == {
        "structure": "unique_partner_litter_aggregates", "aggregate_count": 4,
        "not_individual_mating_records": True,
    }
    offspring = row["family_relationships"]["offspring_identities"]
    assert len(offspring) == 37
    assert all(item["current_status"] == "Active" and item["purpose"] == "Grower" for item in offspring)
    assert all(item["on_farm"] is not None and item["litter_attribution_state"] == "supported" for item in offspring)
    assert row["offspring"]["operational_summary"]["resolved_identity_count"] == 37
    assert first["semantic_digest"] == second["semantic_digest"]
    assert first["writes_performed"] is False


def test_offspring_operational_unknown_and_conflict_are_explicit_without_breaking_identity():
    data = evidence()
    child = data["pigs"][-1]
    child.update({"status": None, "purpose": "Sale", "purpose_conflict": True,
                  "on_farm": True, "on_farm_conflict": True})
    projected = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]["offspring"]["identities"][0]
    assert projected["current_status"] is None
    assert projected["purpose"] is None
    assert projected["on_farm"] is None
    assert projected["operational_evidence_state"] == {
        "current_status": "Unknown", "purpose": "conflicting", "on_farm": "conflicting",
    }
    assert projected["technical_identity"]["pig_id"] == child["pig_id"]


def test_equivalent_permuted_evidence_has_identical_render_order_and_semantic_digest():
    original = evidence()
    permuted = deepcopy(original)
    for collection in ("pigs", "litters", "litter_history", "matings", "observations",
                       "lifecycle", "weights", "medical"):
        if collection in permuted:
            permuted[collection] = list(reversed(permuted[collection]))
    first = compose_full_lifecycle_merit(original, pig_id="S1")
    second = compose_full_lifecycle_merit(permuted, pig_id="S1")
    assert first["semantic_digest"] == second["semantic_digest"]
    assert first["rows"][0]["time_trend"] == second["rows"][0]["time_trend"]
    assert first["rows"][0]["health_observation_context"] == second["rows"][0]["health_observation_context"]
    assert first["lineage"] == second["lineage"]


def test_individual_mating_litter_binding_fails_closed_on_parent_or_mating_mismatch():
    data = evidence()
    data["matings"] = [{"mating_id": "MAT-EXACT-01", "mating_date": "2026-01-01",
                        "sow_pig_id": "S1", "boar_pig_id": "B1",
                        "related_litter_id": "L1"}]
    data["litters"][1]["mating_id"] = "MAT-DIFFERENT"
    summary = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]["individual_mating_summaries"][0]
    assert summary["litter_attribution_state"] == "conflicting"
    assert summary["litter_identity"] is None

    data["litters"][1]["mating_id"] = "MAT-EXACT-01"
    data["litters"][1]["boar_pig_id"] = "B2"
    summary = compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]["individual_mating_summaries"][0]
    assert summary["litter_attribution_state"] == "conflicting"
    assert summary["litter_identity"] is None
