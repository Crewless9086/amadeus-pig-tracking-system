"""Question answers distinguish a due task from coverage and whole-register data."""
from copy import deepcopy
from datetime import date

import pytest

from modules.oom_sakkie.herd_read_queries import answer_herd_read_query
from modules.pig_weights.herdmaster_daily_manager_evidence import build_daily_manager_evidence


def evidence(*, checked=True, due=False, conflict=False):
    pigs = [
        {"pig_id": "PIG-TEST-1", "tag_number": "12", "status": "Active", "on_farm": True, "animal_type": "Grower"},
        {"pig_id": "PIG-TEST-2", "tag_number": "Olive", "status": "Active", "on_farm": True, "animal_type": "Sow"},
        {"pig_id": "PIG-TEST-3", "tag_number": "Unknown", "status": "Active", "on_farm": True, "animal_type": "Piglet"},
        {"pig_id": "PIG-TEST-4", "tag_number": "44", "status": "Unknown", "on_farm": None, "animal_type": "Grower"},
        {"pig_id": "PIG-TEST-5", "tag_number": "55", "status": "Sold", "on_farm": False, "animal_type": "Grower"},
    ]
    weights = [{"weight_event_id": "W1", "pig_id": "PIG-TEST-1", "weight_date": "2026-09-14", "weight_kg": 12}]
    events = [{"pig_id": "PIG-TEST-1", "event_type": "individual_weighing_due", "effective_at": "2026-09-29"}] if due else []
    window = [{"pig_id": "PIG-TEST-1", "weight_date": "2026-09-29", "weight_kg": kg} for kg in (12, 14)] if conflict else []
    return build_daily_manager_evidence(pigs=pigs, window_weights=window, prior_weights=weights,
        lifecycle_events=events, reconciliation_rows={"latest_weights": weights} if checked else None,
        analysis_date=date(2026, 10, 2))


@pytest.mark.parametrize("language", ["en", "af"])
def test_production_packet_keeps_scope_and_history_without_creating_work(language):
    packet = evidence()
    before = deepcopy(packet)
    result = answer_herd_read_query("weight_attention", language=language, loader=lambda _cap: packet)
    text = result["answer"]
    assert result["success"] and result["read_only"] and not result["writes_performed"]
    assert packet == before
    assert "0/1" in text and "29 September 2026" in text and "30 September 2026" in text
    assert "5 animal records across the full register; 1 remains unresolved" in text if language == "en" else "5 dierrekords in die volledige register; 1 is nog onopgelos" in text
    assert "1 without usable visible tags" in text if language == "en" else "1 sonder bruikbare sigbare tags" in text
    assert "Unknown, Unknown" not in text and "PIG-TEST" not in text
    assert "Olive: 12" not in text and "have a latest weight" not in text
    assert "Weigh now" not in text and "Weeg nou" not in text
    assert len(text) < 1000


@pytest.mark.parametrize("language", ["en", "af"])
def test_recorded_task_names_animal_and_reason_without_broadening_to_whole_cohort(language):
    result = answer_herd_read_query("weight_attention", language=language, loader=lambda _cap: evidence(due=True))
    text = result["answer"]
    assert result["success"]
    assert "schedule is due: 12" in text if language == "en" else "weegtaak is verskuldig: 12" in text
    assert "Olive" not in text and "55" not in text
    assert text.index("12") < text.index("0/1")


@pytest.mark.parametrize("language", ["en", "af"])
def test_missing_reconciliation_never_claims_no_due_tasks(language):
    result = answer_herd_read_query("weight_attention", language=language, loader=lambda _cap: evidence(checked=False, due=True))
    text = result["answer"]
    assert result["success"]
    assert "checks are unavailable" in text if language == "en" else "kontroles onbeskikbaar" in text
    assert "currently confirmed due" not in text and "records checked" not in text
    assert "Weigh now" not in text and "Weeg nou" not in text


def test_conflicting_weights_keep_review_visible_and_block_weigh_now():
    result = answer_herd_read_query("weight_attention", loader=lambda _cap: evidence(due=True, conflict=True))
    assert result["success"]
    assert "Conflicting weights need evidence review: 1 — 12" in result["answer"]
    assert "Weigh now" not in result["answer"]
