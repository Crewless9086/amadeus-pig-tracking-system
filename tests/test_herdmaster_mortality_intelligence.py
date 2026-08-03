from datetime import date

from modules.pig_weights.herdmaster_mortality_intelligence import build_mortality_intelligence, build_oom_sakkie_mortality_packet


END = date(2026, 8, 3)


def event(identity, pig, day, **extra):
    result = {"event_id": identity, "pig_id": pig, "effective_date": day, "event_kind": "individual_death", "confirmation": "confirmed", "canonical_status": "current"}
    result.update(extra)
    return result


def test_litter_pen_growth_and_observed_cold_patterns_are_associations():
    evidence = {
        "mortality_events": [event("E1", "P1", "2026-08-01", litter_id="L1", pen_id="A"), event("E2", "P2", "2026-08-02", litter_id="L1", pen_id="A")],
        "weights": {"P1": [{"date": "2026-07-20", "kg": 6}, {"date": "2026-07-30", "kg": 5}]},
        "rootline_observations": [{"date": "2026-08-01", "temperature_min_c": 4, "coverage_pct": 100}],
        "rootline_forecasts": [{"date": "2026-08-04", "temperature_min_c": 1}],
    }
    result = build_mortality_intelligence(evidence, analysis_end=END)
    kinds = {p["pattern"] for p in result["detected_patterns"]}
    assert kinds == {"litter_cluster", "pen_cluster", "weak_growth_association", "observed_cold_weather_overlap"}
    assert all(p["causality"] == "not established" for p in result["detected_patterns"])
    assert result["forecast_evidence"] == evidence["rootline_forecasts"]


def test_incomplete_conflicting_duplicate_superseded_and_undated_records_are_visible_not_counted():
    evidence = {"mortality_events": [
        event("E1", "P1", "2026-08-01"),
        event("E1", "P1", "2026-08-01"),
        event("E2", "P2", "2026-08-01", confirmation="conflicting"),
        event("E3", "P3", None),
        event("E4", "P4", "2026-08-01", canonical_status="superseded"),
    ], "recording_quality": {"complete_from": "2026-07-01"}}
    result = build_mortality_intelligence(evidence, analysis_end=END)
    assert result["rolling_counts"]["7"]["total"] == 1
    assert len(result["excluded_events"]) == 4
    assert result["historical_baseline"]["reliable"] is False


def test_no_pattern_and_missing_inputs_yield_one_grouped_question_not_a_diagnosis():
    result = build_mortality_intelligence({"mortality_events": [event("E1", "P1", "2026-08-01")]}, analysis_end=END)
    assert result["detected_patterns"] == []
    assert "No reliable shared pattern" in result["family_assessment_en"]
    assert result["smallest_grouped_question"].count("?") == 1
    assert "diagnoses" in result["family_assessment_en"]


def test_stillbirth_is_counted_separately_from_later_death():
    evidence = {"mortality_events": [event("S1", "P1", "2026-08-01", event_kind="stillbirth"), event("D1", "P2", "2026-08-02", event_kind="piglet_later_death")]}
    result = build_mortality_intelligence(evidence, analysis_end=END)
    assert result["rolling_counts"]["7"]["by_kind"] == {"piglet_later_death": 1, "stillbirth": 1}


def test_unchanged_replay_is_deterministic_and_zero_authority():
    evidence = {"mortality_events": [event("E1", "P1", "2026-08-01")]}
    first = build_mortality_intelligence(evidence, analysis_end=END)
    replay = build_mortality_intelligence(evidence, analysis_end=END)
    assert replay == first
    assert first["unchanged_replay_action"] == "suppress_duplicate_alert"
    assert not any(first["authority"].values())


def test_material_change_refreshes_same_review_identity_only():
    first = build_mortality_intelligence({"mortality_events": [event("E1", "P1", "2026-08-01")]}, analysis_end=END)
    changed = build_mortality_intelligence({"mortality_events": [event("E1", "P1", "2026-08-01"), event("E2", "P2", "2026-08-02")]}, analysis_end=END)
    assert changed["review_identity"] == first["review_identity"]
    assert changed["evidence_digest"] != first["evidence_digest"]


def test_undated_historical_and_superseded_duplicate_are_accounted_without_dates():
    evidence = {"mortality_events": [event("OLD", "P1", None), event("DUP", "P2", "2026-08-01", canonical_status="superseded")],
                "undated_identity_accounting": [{"pig_id": "P1", "classification": "legitimate_undated_historical_loss", "effective_date": None}]}
    result = build_mortality_intelligence(evidence, analysis_end=END)
    assert result["rolling_counts"]["7"]["total"] == 0
    assert result["undated_identity_accounting"][0]["effective_date"] is None
    assert {reason for item in result["excluded_events"] for reason in item["exclusion_reasons"]} >= {"effective date Unknown", "superseded history"}


def test_authenticated_owner_report_is_not_canonical_mortality():
    evidence = {"mortality_events": [], "owner_reported_events": [{"report_identity": "TG-3210", "pig_id": "P127", "reported_at": "2026-08-03T10:00:00+02:00", "reported_facts": ["owner reported death"]}]}
    result = build_mortality_intelligence(evidence, analysis_end=END)
    assert result["rolling_counts"]["7"]["total"] == 0
    assert result["owner_reported_not_canonical"][0]["canonical_mortality"] is False


def test_missing_herd_at_risk_denominator_is_explicit():
    result = build_mortality_intelligence({"mortality_events": []}, analysis_end=END)
    assert result["herd_at_risk_denominator"]["reconstructable"] is False
    assert "lifecycle intervals" in result["herd_at_risk_denominator"]["minimum_requirement"]


def test_weak_growth_hypothesis_retains_counter_evidence_and_no_cause():
    evidence = {"mortality_events": [event("E1", "P1", "2026-08-01")], "weights": {"P1": [{"date": "2026-07-20", "kg": 6}, {"date": "2026-07-30", "kg": 5}]}}
    result = build_mortality_intelligence(evidence, analysis_end=END)
    hypothesis = next(h for h in result["hypotheses"] if h["supporting_evidence"]["pattern"] == "weak_growth_association")
    assert "No causal diagnosis" in hypothesis["contradicting_evidence"]


def test_typed_oom_sakkie_packet_is_bilingual_bounded_and_zero_write():
    evidence = {"mortality_events": [event("E1", "P1", "2026-08-01")]}
    packet = build_oom_sakkie_mortality_packet(evidence, analysis_end=END)
    assert packet["packet_type"] == "herdmaster.mortality_intelligence.v1"
    assert packet["english"] and packet["afrikaans"]
    assert len(packet["actions"]) <= 3
    assert packet["question"].count("?") <= 1
    assert not any(packet["authority"].values())
    assert build_oom_sakkie_mortality_packet(evidence, analysis_end=END) == packet
