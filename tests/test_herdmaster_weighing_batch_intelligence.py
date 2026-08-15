from datetime import date, datetime
from unittest.mock import patch

from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights.herdmaster_weighing_batch_intelligence import build_weighing_batch_intelligence


def build(rows=None, history=None, expected=None, contexts=None, status="complete", lineage=None):
    rows = rows if rows is not None else [
        {"row_id":"R1", "status":"success", "pig_id":"P1", "pig_name":"Bonnie", "weight_kg":64.4, "pen_name":"D3", "litter_id":"L1"},
        {"row_id":"R2", "status":"success", "pig_id":"P2", "pig_name":"Waki", "weight_kg":70, "pen_name":"D3", "litter_id":"L1"},
    ]
    history = history if history is not None else [
        {"weight_event_id":"W1", "pig_id":"P1", "weight_date":"2026-07-28", "weight_kg":62.0},
        {"weight_event_id":"W2", "pig_id":"P2", "weight_date":"2026-07-28", "weight_kg":71.0},
    ]
    expected = expected if expected is not None else [
        {"pig_id":"P1", "name":"Bonnie", "pen_name":"D3"}, {"pig_id":"P2", "name":"Waki", "pen_name":"D3"}]
    return build_weighing_batch_intelligence(batch={"batch_id":"B1", "status":status, "weight_date":"2026-08-11"},
        batch_rows=rows, weight_history=history, expected_animals=expected, contexts=contexts or [], correction_lineage=lineage)


def test_requires_one_completed_canonical_batch():
    assert build(status="partial")["reason"] == "completed_canonical_batch_required"


def test_read_adapter_binds_complete_batch_and_keeps_missing_weight_unknown():
    batch = {"batch_id": "11111111-1111-1111-1111-111111111111", "weight_date": date(2026, 8, 11),
             "status": "complete", "completed_at": datetime(2026, 8, 11, 10, 0),
             "visible_row_count": 2, "success_count": 1, "failed_count": 0,
             "duplicate_count": 0, "skipped_row_count": 1, "weight_row_count": 1,
             "actionable_row_count": 1, "movement_row_count": 0}
    rows = [{"row_id": "ROW-1", "pig_id": "PIG-1", "pig_name": "Bonnie", "weight_kg": 64.4,
             "from_pen_id": "D3", "litter_id": "LIT-1", "outcome": "Weaned",
             "status": "success", "weight_event_id": "WGT-NEW", "event_count": 1,
             "movement_event_count": 0, "result_json": {"has_weight": True}},
            {"row_id": "ROW-2", "pig_id": "PIG-2", "pig_name": "Waki", "weight_kg": None,
             "from_pen_id": "D3", "status": "skipped", "event_count": 0,
             "movement_event_count": 0, "result_json": {"has_weight": False}}]
    history = [{"weight_event_id": "WGT-OLD", "pig_id": "PIG-1", "weight_date": date(2026, 7, 28),
                "weight_kg": 62.0}, {"weight_event_id": "WGT-NEW", "pig_id": "PIG-1",
                "weight_date": date(2026, 8, 11), "weight_kg": 64.4}]
    with patch.object(farm_supabase_read_service, "_fetch_one", return_value=batch), \
         patch.object(farm_supabase_read_service, "_fetch_all", side_effect=[rows, history]):
        packet = farm_supabase_read_service._completed_batch_intelligence(batch["batch_id"])
    assert packet["success"] is True
    assert packet["metrics"]["coverage_pct"] == 50.0
    assert packet["missing_expected_animals"][0]["weight_kg"] is None
    assert packet["animals"][0]["pen_id"] == "D3"
    assert packet["animals"][0]["cohort_id"] == "LIT-1"
    assert packet["animals"][0]["reproductive_state"] == "Weaned"
    assert packet["writes_performed"] is False


def test_completed_batch_manifest_or_event_mismatch_fails_closed():
    batch = {"batch_id": "B1", "visible_row_count": 1, "success_count": 1, "failed_count": 0,
             "duplicate_count": 0, "skipped_row_count": 0, "weight_row_count": 1,
             "actionable_row_count": 1, "movement_row_count": 0}
    row = {"row_id": "R1", "status": "success", "event_count": 0,
           "result_json": {"has_weight": True}}
    assert farm_supabase_read_service._batch_integrity_error(batch, []) == "completed_batch_row_manifest_mismatch"
    assert farm_supabase_read_service._batch_integrity_error(batch, [row]) == "completed_batch_weight_event_binding_mismatch"
    assert farm_supabase_read_service._batch_integrity_error({**batch, "visible_row_count": 2}, [row, row]) == "completed_batch_row_manifest_mismatch"


def test_completed_manifest_rejects_unknown_status_and_movement_binding_mismatch():
    batch = {"visible_row_count": 1, "success_count": 1, "failed_count": 0, "duplicate_count": 0,
             "skipped_row_count": 0, "weight_row_count": 0, "actionable_row_count": 1,
             "movement_row_count": 1}
    row = {"row_id": "R1", "status": "success", "event_count": 0, "movement_event_count": 0,
           "result_json": {"has_weight": False, "has_pen_change": True}}
    assert farm_supabase_read_service._batch_integrity_error(batch, [{**row, "status": "tampered"}]) == "completed_batch_status_manifest_mismatch"
    assert farm_supabase_read_service._batch_integrity_error(batch, [row]) == "completed_batch_movement_event_binding_mismatch"
    assert farm_supabase_read_service._batch_integrity_error(batch, [{**row, "movement_event_count": 2}]) == "completed_batch_movement_event_binding_mismatch"


def test_reproductive_state_prefers_terminal_outcome_and_ignores_post_batch_litter():
    cutoff = date(2026, 8, 11)
    terminal = {"pregnancy_check_result": "Pregnant", "outcome": "Farrowed",
                "latest_mating_id": "MAT-1"}
    assert farm_supabase_read_service._batch_reproductive_state(terminal, cutoff) == "Farrowed"
    future_litter = {"batch_litter_id": "LIT-FUTURE", "batch_litter_farrowing_date": date(2026, 8, 12),
                     "pregnancy_check_result": "Inconclusive", "latest_mating_id": "MAT-2"}
    assert farm_supabase_read_service._batch_reproductive_state(future_litter, cutoff) == "Inconclusive"


def test_reproductive_state_reconstructs_weaning_relative_to_batch_date():
    cutoff = date(2026, 8, 11)
    litter = {"batch_litter_id": "LIT-1", "batch_litter_farrowing_date": date(2026, 7, 1),
              "batch_litter_status": "Weaned", "batch_litter_wean_date": date(2026, 8, 12)}
    assert farm_supabase_read_service._batch_reproductive_state(litter, cutoff) == "Nursing"
    assert farm_supabase_read_service._batch_reproductive_state(
        {**litter, "batch_litter_wean_date": cutoff}, cutoff) == "Unknown"


def test_exact_change_growth_coverage_and_missing_is_not_zero():
    result = build(expected=[{"pig_id":"P1","name":"Bonnie","pen_name":"D3"},
        {"pig_id":"P2","name":"Waki","pen_name":"D3"}, {"pig_id":"P3","name":"Teena","pen_name":"D3"}])
    assert result["metrics"]["coverage_pct"] == 66.7
    assert result["animals"][0]["change_kg"] == 2.4
    assert result["animals"][0]["elapsed_days"] == 14
    assert result["animals"][0]["growth_rate_kg_day"] == 0.171
    assert result["missing_expected_animals"] == [{"pig_id":"P3","name":"Teena","pen_name":"D3","weight_kg":None,"classification":"not_weighed"}]


def test_no_previous_weight_remains_unknown_not_zero():
    result = build(history=[])
    assert result["metrics"]["no_comparison_count"] == 2
    assert all(row["previous_weight_kg"] is None and row["change_kg"] is None for row in result["animals"])


def test_slow_growth_requires_an_evidence_qualified_threshold():
    result = build(rows=[{"row_id": "R1", "status": "success", "pig_id": "P1", "weight_kg": 62.7,
                          "pen_name": "D3", "expected_growth_min_kg_day": 0.1}],
                   history=[{"pig_id": "P1", "weight_date": "2026-07-28", "weight_kg": 62.0}],
                   expected=[{"pig_id": "P1"}])
    assert result["animals"][0]["classification"] == "slow_growth"
    assert result["metrics"]["slow_growth_count"] == 1


def test_same_day_duplicate_and_implausible_measurement_require_reweigh():
    rows = [{"row_id":"R1","status":"success","pig_id":"P1","weight_kg":64,"pen_name":"D3"},
        {"row_id":"R2","status":"success","pig_id":"P1","weight_kg":640,"pen_name":"D3"}]
    result = build(rows=rows, expected=[{"pig_id":"P1"}])
    assert result["metrics"]["reweigh_count"] == 2
    assert all(row["reweigh_required"] for row in result["animals"])


def test_repeated_decline_is_measured_without_diagnosis():
    history = [{"pig_id":"P1","weight_date":"2026-07-01","weight_kg":70},
        {"pig_id":"P1","weight_date":"2026-07-20","weight_kg":68}]
    result = build(rows=[{"row_id":"R1","status":"success","pig_id":"P1","weight_kg":65,"pen_name":"D3"}], history=history,
        expected=[{"pig_id":"P1"}])
    assert result["metrics"]["repeated_decline_count"] == 1
    assert "cause" not in result["findings"][0]["finding"].lower()


def test_pen_pattern_is_association_and_weather_never_becomes_cause():
    rows = [{"row_id":"R1","status":"success","pig_id":"P1","weight_kg":60,"pen_name":"D3"},
        {"row_id":"R2","status":"success","pig_id":"P2","weight_kg":60,"pen_name":"D3"}]
    history = [{"pig_id":"P1","weight_date":"2026-07-28","weight_kg":65},
        {"pig_id":"P2","weight_date":"2026-07-28","weight_kg":66}]
    result = build(rows=rows, history=history, contexts=[{"context_type":"weather","summary":"Cold nights observed",
        "source":"ROOTLINE","source_id":"WX1","observed_at":"2026-08-05"}])
    assert any(row["classification"] == "Associated" for row in result["findings"])
    assert result["context"][0]["classification"] == "Associated"
    assert "oorsaak" in result["owner_summary_af"]


def test_absent_feed_evidence_can_produce_only_one_grouped_question():
    result = build(expected=[{"pig_id":"P1"},{"pig_id":"P2"},{"pig_id":"P3"}])
    assert result["grouped_question"].startswith("Het die voer")
    assert result["owner_summary_af"].count("Een vraag:") == 1


def test_attributable_feed_context_suppresses_repeated_question():
    result = build(expected=[{"pig_id":"P1"},{"pig_id":"P2"},{"pig_id":"P3"}],
        contexts=[{"context_type":"feed","summary":"Ration unchanged","source":"owner observation","observed_at":"2026-08-01"}])
    assert result["grouped_question"] is None


def test_nursing_and_weaned_states_are_preserved_not_reclassified():
    rows = [{"row_id":"R1","status":"success","pig_id":"P1","weight_kg":64,"lifecycle_state":"Active","reproductive_state":"Nursing"},
        {"row_id":"R2","status":"success","pig_id":"P2","weight_kg":70,"lifecycle_state":"Active","reproductive_state":"Weaned"}]
    result = build(rows=rows, history=[])
    assert [row["reproductive_state"] for row in result["animals"]] == ["Nursing", "Weaned"]


def test_identity_lineage_and_replay_are_deterministic_and_zero_authority():
    first = build(lineage={"supersedes_batch_id":"B0"})
    second = build(lineage={"supersedes_batch_id":"B0"})
    assert first["analysis_id"] == second["analysis_id"]
    assert first["replay_identity"] == second["replay_identity"]
    assert first["correction_lineage"] == {"supersedes_batch_id":"B0"}
    assert first["writes_performed"] is first["telegram_delivery_enabled"] is first["protected_actions_performed"] is False


def test_replay_identity_is_independent_of_equivalent_evidence_order():
    rows = [{"row_id": "R1", "status": "success", "pig_id": "P1", "weight_kg": 64},
            {"row_id": "R2", "status": "success", "pig_id": "P2", "weight_kg": 70}]
    history = [{"pig_id": "P1", "weight_date": "2026-07-28", "weight_kg": 62},
               {"pig_id": "P2", "weight_date": "2026-07-28", "weight_kg": 69}]
    expected = [{"pig_id": "P1"}, {"pig_id": "P2"}]
    first = build(rows=rows, history=history, expected=expected)
    second = build(rows=list(reversed(rows)), history=list(reversed(history)), expected=list(reversed(expected)))
    assert first["evidence_digest"] == second["evidence_digest"]
    assert first["delivery_deduplication_key"] == second["delivery_deduplication_key"]


def test_owner_supplied_d3_weights_are_reconciliation_evidence_not_completion():
    rows = [
        {"row_id": "R1", "status": "success", "pig_id": "BONNIE", "pig_name": "Bonnie", "weight_kg": 64.4, "pen_name": "D3"},
        {"row_id": "R2", "status": "success", "pig_id": "WAKI", "pig_name": "Waki", "weight_kg": 70.0, "pen_name": "D3"},
        {"row_id": "R3", "status": "success", "pig_id": "ZIGAY", "pig_name": "Zigay", "weight_kg": 71.4, "pen_name": "D3"},
        {"row_id": "R4", "status": "success", "pig_id": "TEENA", "pig_name": "Teena", "weight_kg": 69.2, "pen_name": "D3"},
    ]
    result = build(rows=rows, history=[], expected=[{"pig_id": row["pig_id"]} for row in rows])
    assert result["metrics"]["unique_pigs_weighed"] == 4
    assert result["metrics"]["average_weight_kg"] == 68.75
    assert result["metrics"]["no_comparison_count"] == 4
    assert result["telegram_delivery_enabled"] is False
