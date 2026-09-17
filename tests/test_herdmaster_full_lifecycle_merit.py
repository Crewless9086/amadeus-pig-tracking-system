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


def _disposition_evidence():
    data = evidence()
    data["pigs"] = data["pigs"][:2]
    data["litters"] = [{
        "litter_id": "L-DISP", "sow_pig_id": "S1", "boar_pig_id": "B1",
        "farrowing_date": "2026-01-01", "litter_status": "Weaned",
        "born_alive": 8, "weaned_count": 8,
    }]
    names = ("Farm Child", "Private Sale", "Auction Child", "Slaughter Child",
             "Processed Child", "Deceased Child", "Unknown Child", "Conflict Child")
    for index, name in enumerate(names, 1):
        data["pigs"].append({
            "pig_id": f"C{index}", "name": name, "tag_number": f"TAG-C{index}",
            "litter_id": "L-DISP", "purpose": "Sale" if index == 7 else "Grower",
            "status": "Sold" if index == 7 else "Active",
            "on_farm": index in {1, 8},
        })
    data["sales"] = [
        {"pig_id": "C2", "sale_id": "S-LIVE", "sale_item_id": "I-LIVE",
         "sale_stream": "Livestock", "sale_status": "Completed", "sale_date": "2026-05-01"},
        {"pig_id": "C2", "sale_id": "S-LIVE", "sale_item_id": "I-LIVE-DUP",
         "sale_stream": "Livestock", "sale_status": "Completed", "sale_date": "2026-05-01"},
        {"pig_id": "C3", "sale_id": "S-AUCT", "sale_item_id": "I-AUCT",
         "sale_stream": "Livestock", "sale_channel": "Auction", "sale_status": "Completed", "sale_date": "2026-05-02"},
        {"pig_id": "C4", "sale_id": "S-SLAUGHTER", "sale_item_id": "I-SLAUGHTER",
         "sale_stream": "Slaughter", "sale_status": "Completed", "sale_date": "2026-05-03"},
        {"pig_id": "C7", "sale_id": "S-DRAFT", "sale_item_id": "I-DRAFT",
         "sale_stream": "Livestock", "sale_status": "Draft", "sale_date": "2026-05-04"},
        {"pig_id": "C8", "sale_id": "S-CONFLICT", "sale_item_id": "I-CONFLICT",
         "sale_stream": "Livestock", "sale_status": "Completed", "sale_date": "2026-05-05"},
    ]
    data["meat_processing"] = [
        {"pig_id": "C5", "batch_id": "B-COMPLETE", "batch_pig_id": "BP-5",
         "batch_status": "Completed", "batch_status_at": "2026-05-06",
         "completion_event_id": "ME-5", "event_type": "completed",
         "completion_event_date": "2026-05-06"},
        {"pig_id": "C7", "batch_id": "B-PLANNED", "batch_pig_id": "BP-7",
         "batch_status": "Planned"},
    ]
    data["lifecycle"] = [{
        "lifecycle_event_id": "LIFE-DEAD", "pig_id": "C6",
        "effective_at": "2026-06-01", "lifecycle_event_type": "exited_farm",
        "event_payload": {"resulting_status": "Dead"},
    }]
    return data


def test_offspring_dispositions_cover_every_category_and_reconcile_exactly():
    row = compose_full_lifecycle_merit(_disposition_evidence(), pig_id="S1")["rows"][0]
    projected = {item["identity"]["pig_id"]: item for item in row["offspring"]["dispositions"]}
    assert {pig_id: item["primary_disposition"] for pig_id, item in projected.items()} == {
        "C1": "on_farm", "C2": "livestock_sale", "C3": "auction_sale",
        "C4": "slaughter_pig_sale", "C5": "meat_processed", "C6": "deceased",
        "C7": "other_unresolved", "C8": "other_unresolved",
    }
    assert projected["C2"]["evidence_state"] == "supported"
    assert len(projected["C2"]["evidence"]) == 2
    assert projected["C2"]["evidence"][0]["sale_status"] == "Completed"
    assert projected["C5"]["evidence"][0]["completion_event_date"] == "2026-05-06"
    assert projected["C6"]["evidence"][0]["matched_structured_facts"] == ["dead"]
    assert projected["C7"]["evidence_state"] == "unknown"
    assert projected["C7"]["identity"] == {
        "name": "Unknown Child", "tag_number": "TAG-C7", "pig_id": "C7",
        "display_name": "Unknown Child", "secondary_identity": "TAG-C7",
    }
    assert projected["C8"]["evidence_state"] == "conflicting"
    assert projected["C8"]["candidate_dispositions"] == ["livestock_sale", "on_farm"]
    assert row["offspring"]["disposition_summary"] == {
        "on_farm": 1, "livestock_sale": 1, "auction_sale": 1,
        "slaughter_pig_sale": 1, "meat_processed": 1, "deceased": 1,
        "other_unresolved": 2, "total_recorded": 8, "classified_count": 8,
        "reconciles_to_total": True, "rule_id": "herdmaster_offspring_disposition_v1",
    }


def test_empty_litter_and_permuted_duplicate_evidence_are_deterministic():
    empty = evidence()
    empty["pigs"] = empty["pigs"][:2]
    empty["pigs"][0]["purpose"] = "Breeding"
    empty["litters"] = []
    summary = compose_full_lifecycle_merit(empty, pig_id="S1")["rows"][0]["offspring"]["disposition_summary"]
    assert summary["total_recorded"] == summary["classified_count"] == 0
    assert summary["other_unresolved"] == 0
    assert summary["reconciles_to_total"] is True

    first = _disposition_evidence()
    second = deepcopy(first)
    second["pigs"].reverse()
    second["sales"].reverse()
    second["meat_processing"].reverse()
    second["lifecycle"].reverse()
    assert (compose_full_lifecycle_merit(first, pig_id="S1")["rows"][0]["offspring"] ==
            compose_full_lifecycle_merit(second, pig_id="S1")["rows"][0]["offspring"])


def test_future_free_text_and_cancelled_processing_evidence_fail_closed():
    data = _disposition_evidence()
    data["sales"].append({
        "pig_id": "C7", "sale_id": "S-FUTURE", "sale_item_id": "I-FUTURE",
        "sale_stream": "Livestock", "sale_status": "Completed", "sale_date": "2026-09-01",
    })
    data["meat_processing"].append({
        "pig_id": "C7", "batch_id": "B-FUTURE", "batch_pig_id": "BP-FUTURE",
        "batch_status": "Completed", "batch_status_at": "2026-09-01",
        "completion_event_id": "ME-FUTURE", "event_type": "completed",
        "completion_event_date": "2026-09-01",
    })
    data["lifecycle"].append({
        "lifecycle_event_id": "LIFE-NOTE", "pig_id": "C7", "effective_at": "2026-06-02",
        "lifecycle_event_type": "other", "event_note": "Dead", "event_payload": {},
    })
    data["meat_processing"].append({
        "pig_id": "C8", "batch_id": "B-CANCELLED", "batch_pig_id": "BP-CANCELLED",
        "batch_status": "Cancelled", "batch_status_at": "2026-07-01",
        "completion_event_id": "ME-CANCELLED", "event_type": "completed",
        "completion_event_date": "2026-06-30",
    })
    projected = {
        item["identity"]["pig_id"]: item
        for item in compose_full_lifecycle_merit(data, pig_id="S1")["rows"][0]["offspring"]["dispositions"]
    }
    assert projected["C7"]["primary_disposition"] == "other_unresolved"
    assert projected["C7"]["candidate_dispositions"] == []
    assert projected["C8"]["primary_disposition"] == "other_unresolved"
    assert projected["C8"]["evidence_state"] == "conflicting"
    assert projected["C8"]["conflicts"] == ["cancelled_batch_has_completion_event"]
