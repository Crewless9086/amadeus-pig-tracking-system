"""Read capability semantics and source uncertainty; no production side effects."""
import json
from datetime import date
from unittest.mock import Mock

import pytest

from modules.oom_sakkie.herd_read_queries import answer_herd_read_query, load_herd_read_evidence
from modules.oom_sakkie.semantic_front_door import parse_semantic_response, _payload
from modules.pig_weights.herdmaster_daily_manager_evidence import build_daily_manager_evidence


def parse(query, **extra):
    value = {"domain": "manager_round", "intent": "read", "message_kind": "question",
        "confidence": .99, "language": "en", "read_query": query, **extra}
    return parse_semantic_response(json.dumps({"choices": [{"message": {"content": json.dumps(value)}}]}))


@pytest.mark.parametrize("capability", ["herd_inventory", "pen_occupancy", "weight_attention", "litter_attention", "breeding_plan"])
def test_model_contract_preserves_capability_through_normalization(capability):
    parsed = parse({"kind": "herd_query", "capability": capability}, intent="breeding_plan")
    assert parsed.domain == "herd_management" and parsed.read_query["capability"] == capability
    assert parsed.intent == "herd_query"
    assert capability in _payload({}, {}, {})["messages"][0]["content"]


@pytest.mark.parametrize("extra", [{"message_kind": "command"}, {"message_kind": "observation"},
    {"message_kind": "confirmation"}, {"protected_preview_required": True},
    {"confirmation_facts": {"interlock_off": True}},
    {"breeding_actions": [{"action": "start_exposure", "female_refs": ["Hazel"]}]}])
def test_read_query_cannot_transport_effect_or_confirm_farm_action(extra):
    assert parse({"kind": "herd_query", "capability": "herd_inventory"}, **extra) is None


@pytest.mark.parametrize("query", [
    {"kind": "herd_query", "capability": "execute_sql"},
    {"kind": "herd_query", "capability": "record_death"},
    {"kind": "herd_query", "capability": "herd_inventory", "subject": "148"},
    {"kind": "herd_query", "capability": "herd_inventory", "specialist": "SAM"},
    {"kind": "farm_brief", "capability": "herd_inventory"},
    {"kind": "herd_query"}, {"kind": "herd_query", "capability": ["herd_inventory"]},
])
def test_invalid_capability_scope_fails_closed(query):
    assert parse(query) is None


def test_scoped_owner_work_keeps_specialist():
    value = parse({"kind": "work_split", "specialist": "HERDMASTER"})
    assert value.read_query == {"kind": "work_split", "specialist": "HERDMASTER"}


def pig(identity, **extra):
    return {"Pig_ID": identity, "Tag_Number": identity, "On_Farm": "Yes", "Status": "Active",
        "Current_Pen_ID": "PEN-1", "Animal_Type": "Grower", **extra}


def answer(capability, evidence, language="en"):
    return answer_herd_read_query(capability, language=language, loader=lambda selected: evidence)


def test_inventory_reports_lifecycle_conflict_and_unknown_without_relabelling():
    result = answer("herd_inventory", {"pig_rows": [pig("A"), pig("B", Status="Dead"), pig("C", On_Farm="")]})
    assert "2 pigs recorded" in result["answer"] and "1 are also Active" in result["answer"]
    assert "lifecycle conflict" in result["answer"] and "unknown on-farm status" in result["answer"]
    assert result["writes_performed"] is False


def test_pen_capacity_uses_exact_id_even_if_names_differ_and_does_not_infer_litter_units():
    result = answer("pen_occupancy", {"pig_rows": [pig("sow", Animal_Type="Sow"), pig("piglet", Animal_Type="Piglet")],
        "pens": [{"pen_id": "PEN-1", "pen_name": "Maternity", "capacity": 1}]})
    assert "Maternity: 2 recorded animals (1 Piglet, 1 Sow); capacity 1; unit unresolved" in result["answer"]
    assert "no overcrowding calculation" in result["answer"] and "not established" in result["answer"]
    assert "exceeds recorded capacity" not in result["answer"]


@pytest.mark.parametrize("capacity", [None, "", 0, -1, float("nan"), float("inf")])
def test_absent_or_invalid_pen_capacity_is_unknown_not_zero_or_overcrowded(capacity):
    result = answer("pen_occupancy", {"pig_rows": [pig("A")],
        "pens": [{"pen_id": "PEN-1", "pen_name": "North", "capacity": capacity}]})
    assert "Capacity/location is missing" in result["answer"]
    assert "exceeds recorded capacity" not in result["answer"]


def test_litter_render_keeps_total_due_reason_planning_and_truncation_distinct():
    result = answer("litter_attention", {"litter_attention": {"count": 9, "items": [
        {"litter_id": f"L{i}", "sow_name": f"Sow{i}", "reason": "Weaning due",
         "recommended_action": "Review litter", "estimated_wean_date": "2026-10-02", "weaned_count": None}
        for i in range(6)]}})
    assert "9 litter(s)" in result["answer"] and "Sow5: Weaning due" in result["answer"]
    assert "2026-10-02" in result["answer"] and "Another 3 item(s)" in result["answer"]
    assert "does not mean weaning is completed" in result["answer"]
    assert "weaned: 0" not in result["answer"]


@pytest.mark.parametrize("packet", [{}, {"count": None, "items": []}, {"count": 3, "items": []}])
def test_missing_litter_evidence_cannot_report_no_work(packet):
    result = answer("litter_attention", {"litter_attention": packet})
    assert not result["success"] and "does not mean" in result["answer"]


def test_weight_question_uses_governed_schedules_conflict_and_eligibility():
    pigs = [{"pig_id": f"P{i}", "tag_number": str(100+i), "status": "Active", "on_farm": True,
        "animal_type": "Sow" if i == 3 else "Grower"} for i in range(1, 5)]
    packet = build_daily_manager_evidence(pigs=pigs, analysis_date=date(2026,9,29), prior_weights=[],
        window_weights=[{"pig_id": "P4", "weight_date": "2026-09-29", "weight_kg": kg} for kg in (10,11)],
        lifecycle_events=[{"pig_id": "P1", "event_type": "individual_weighing_due", "effective_at": "2026-09-29"}])
    result = answer("weight_attention", packet)
    assert "schedule is due: 101" in result["answer"]
    assert "reconcile sale/order status before instructing reweighing: 102" in result["answer"]
    assert "Conflicting weights need evidence review: 1 — 104" in result["answer"]
    assert "1 breeding animal(s)" in result["answer"]
    assert "schedule is due: 104" not in result["answer"]


@pytest.mark.parametrize("capability", ["herd_inventory", "pen_occupancy", "weight_attention", "litter_attention"])
def test_reader_failure_is_explicit_and_relevant_in_both_languages(capability):
    for language in ("en", "af"):
        result = answer_herd_read_query(capability, language=language,
            loader=Mock(side_effect=TimeoutError("bounded_timeout")))
        assert not result["success"] and "HERDMASTER" in result["answer"]
        assert "TODAY" not in result["answer"] and result["writes_performed"] is False


def test_canonical_loader_requests_weight_only_without_mortality_fanout(monkeypatch):
    from modules.pig_weights import herdmaster_daily_manager_evidence as daily
    loader = Mock(return_value={"packet_type": "test"})
    monkeypatch.setattr(daily, "load_daily_manager_evidence", loader)
    assert load_herd_read_evidence("weight_attention") == {"packet_type": "test"}
    assert loader.call_args.kwargs["include_mortality"] is False


def test_typed_capability_cannot_be_overridden_by_unrelated_words():
    from modules.agents.herdmaster import run_herdmaster
    result = run_herdmaster({"question": "Do not give weights or a breeding plan. Count animals.",
        "capability": "herd_inventory"}, readers={"pig_rows": lambda: [pig("A")]})
    assert result["capability"] == "herd_inventory"


def test_breeding_plan_shows_due_checks_not_fabricated_placement_and_retains_remainder():
    from modules.oom_sakkie.herdmaster_request_runtime import render_breeding_plan
    tasks = [{"task_id": f"T{i}", "tag_number": f"Sow{i}", "priority": i+1,
        "task_group": "pregnancy check due", "why": "Result date is missing",
        "required_checks": ["pregnancy result"], "male_recommendation": {}} for i in range(8)]
    text, selected = render_breeding_plan({"tasks": tasks})
    assert "Sow0" in text and "pregnancy check due" in text and "Result date is missing" in text
    assert "Missing observations: pregnancy result" in text
    assert "Another 2 breeding task(s)" in text and len(selected) == 6
    assert "planned placement" not in text and "No evidence-supported placement" in text


@pytest.mark.parametrize("evidence", [{}, {"pig_rows": None}, {"pig_rows": "unknown"}])
def test_missing_inventory_evidence_never_becomes_zero_or_an_unrequested_reader(evidence, monkeypatch):
    from modules.agents import herdmaster
    monkeypatch.setattr(herdmaster, "run_herdmaster", lambda *_a, **_kw: pytest.fail("no fallback reader"))
    result = answer("herd_inventory", evidence)
    assert not result["success"] and "cannot read" in result["answer"]
    assert "0 pigs" not in result["answer"]


def test_maternity_headcounts_do_not_hide_comparable_pen_records():
    rows = [pig(f"M{i}", Current_Pen_ID=f"MAT-{i}", Animal_Type="Sow") for i in range(10)]
    rows += [pig(f"G{i}", Current_Pen_ID="GROW") for i in range(7)]
    pens = [{"pen_id": f"MAT-{i}", "pen_name": f"Kraam {i}", "pen_type": "Farrowing", "capacity": 1} for i in range(10)]
    pens.append({"pen_id": "GROW", "pen_name": "Growers", "pen_type": "Grower", "capacity": 5})
    result = answer("pen_occupancy", {"pig_rows": rows, "pens": pens})
    text = result["answer"]
    assert "Growers: 7 / 5" in text and text.index("Growers:") < text.index("Kraam")
    assert "unit unresolved" in text and "Another 7 item(s)" in text
    assert text.count("exceeds recorded capacity") == 1


def test_pen_count_discloses_unknown_on_farm_status():
    result = answer("pen_occupancy", {"pig_rows": [pig("A", On_Farm="")],
        "pens": [{"pen_id": "PEN-1", "pen_name": "North", "capacity": 5}]})
    assert "unknown on-farm status; pen occupancy is incomplete" in result["answer"]


def test_scoped_owner_brief_does_not_promote_stale_owner_question():
    from datetime import datetime, timedelta, timezone
    from modules.oom_sakkie.farm_manager_loop import (build_family_brief, Provenance,
        SpecialistResult, SpecialistWorkItem, SpecialistAvailability, Authority, WorkState)
    now = datetime.now(timezone.utc)
    proof = Provenance("herdmaster", "stale", ("canonical",), now-timedelta(days=3), 1)
    item = SpecialistWorkItem("Q", "herd:Q", "herd", "Old observation", "Old missing fact",
        "What was observed?", "charl", WorkState.WAITING_EVIDENCE, Authority.READ_ONLY,
        proof, genuine_question="What was observed?", question_for="charl")
    result = SpecialistResult("herdmaster", "stale", now-timedelta(days=3),
        availability=SpecialistAvailability.STALE, work_items=(item,))
    brief = build_family_brief([result], now=now, owner_dependencies_only=True)
    assert not brief.queue and brief.suppressed["stale_refreshed"] == ("Q",)
