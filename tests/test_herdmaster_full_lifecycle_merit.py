from copy import deepcopy
from datetime import date

from modules.pig_weights.herdmaster_full_lifecycle_merit import compose_full_lifecycle_merit


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
    assert result["rows"][0]["confidence"]["label"] == "Moderate"
