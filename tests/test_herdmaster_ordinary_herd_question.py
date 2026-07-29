from datetime import date
import unittest

from modules.oom_sakkie.herd_question import answer_herd_question
from modules.oom_sakkie.service import classify_intent


def _readiness(*pigs):
    return {
        "success": True,
        "generated_date": "2026-07-29",
        "source": "supabase_canonical",
        "pigs": list(pigs),
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }


def _pig(pig_id, tag, **overrides):
    row = {
        "pig_id": pig_id,
        "tag_number": tag,
        "sex": "Female",
        "status": "Active",
        "on_farm": "Yes",
        "purpose": "Breeding",
        "latest_weight_kg": 72.2,
        "latest_weight_date": "2026-07-20",
        "days_since_weight": 9,
        "readiness_bucket": "Retain / Breeding Candidate",
        "readiness_reason": "Current purpose is breeding or retention.",
        "recommended_action": (
            "Review for retention before offering as meat or slaughter."
        ),
    }
    row.update(overrides)
    return row


def test_ordinary_question_routes_to_deterministic_herd_tool():
    match = classify_intent(
        "Oom Sakkie, what do you currently know about Shupe, what is her "
        "latest recorded weight, what is her breeding status, what evidence "
        "is still missing, and what is the next recommended action?"
    )
    assert match is not None
    assert match.tool_name == "herdmaster_herd_question"
    assert match.confidence == 0.99


def test_answer_separates_dated_facts_missing_evidence_and_recommendation():
    result = answer_herd_question(
        "What do you currently know about Shupe?",
        readiness=_readiness(_pig("PIG-2026-34BF", "Shupe")),
        matings=[],
        worklist={"success": True, "generated_at": "2026-07-29T08:00:00Z"},
        today=date(2026, 7, 29),
    )
    assert result["success"] is True
    assert result["subject"] == {
        "tag_number": "Shupe",
        "pig_id": "PIG-2026-34BF",
    }
    assert result["facts"]["latest_weight"] == {
        "weight_kg": 72.2,
        "evidence_date": "2026-07-20",
        "observation_time": "Unknown",
        "days_old": 9,
        "stale": False,
    }
    assert result["facts"]["breeding"]["status"] == (
        "Breeding animal; no canonical mating event found"
    )
    assert result["facts"]["breeding"]["mating_event_count"] == 0
    assert "No canonical mating chronology is recorded." in (
        result["missing_or_stale_evidence"]
    )
    assert result["recommendation"]["action"].startswith("Review for retention")
    assert result["writes_performed"] is False
    assert result["protected_actions_performed"] is False
    assert "Facts — Shupe" in result["answer"]
    assert "Missing or stale evidence —" in result["answer"]
    assert "Recommendation —" in result["answer"]


def test_latest_mating_and_worklist_task_override_generic_readiness_action():
    result = answer_herd_question(
        "What do you know about Mona?",
        readiness=_readiness(_pig("PIG-MONA", "Mona")),
        matings=[
            {
                "mating_id": "MAT-1",
                "sow_pig_id": "PIG-MONA",
                "mating_date": "2026-05-02",
                "mating_status": "Served",
                "pregnancy_check_result": "",
                "is_open": "Yes",
            }
        ],
        worklist={
            "success": True,
            "generated_at": "2026-07-29T08:00:00Z",
            "tasks": [
                {
                    "pig_id": "PIG-MONA",
                    "task_group": "pregnancy_check_due",
                    "priority": 18,
                    "due_date": "2026-05-23",
                }
            ],
            "cases": [],
        },
        today=date(2026, 7, 29),
    )
    assert result["facts"]["breeding"]["latest_mating_date"] == "2026-05-02"
    assert result["facts"]["breeding"]["mating_event_count"] == 1
    assert result["facts"]["breeding"]["pregnancy_check_result"] == "Unknown"
    assert "Pregnancy-check result is Unknown." in (
        result["missing_or_stale_evidence"]
    )
    assert result["recommendation"] == {
        "action": "pregnancy_check_due",
        "basis": "Current HERDMASTER breeding worklist",
        "priority": 18,
        "due_date": "2026-05-23",
        "fact": False,
    }


def test_multi_pig_question_resolves_exact_named_subject_only():
    result = answer_herd_question(
        "What do you currently know about Shupe?",
        readiness=_readiness(
            _pig("PIG-2026-34BF", "Shupe"),
            _pig("PIG-2026-ABCD", "Mona", latest_weight_kg=81),
            _pig("PIG-2026-EFGH", "Baby", latest_weight_kg=65),
        ),
        matings=[],
        today=date(2026, 7, 29),
    )
    assert result["success"] is True
    assert result["subject"]["pig_id"] == "PIG-2026-34BF"
    assert "Mona" not in result["answer"]
    assert "Baby" not in result["answer"]


def test_ambiguous_tag_fails_closed_without_disclosing_animal_facts():
    result = answer_herd_question(
        "What do you know about Spot?",
        readiness=_readiness(
            _pig("PIG-001", "Spot"),
            _pig("PIG-002", "Spot"),
        ),
        matings=[],
        today=date(2026, 7, 29),
    )
    assert result["success"] is False
    assert result["status"] == "animal_identity_ambiguous"
    assert result["writes_performed"] is False
    assert "facts" not in result
    assert result["candidates"] == [
        {"pig_id": "PIG-001", "tag_number": "Spot"},
        {"pig_id": "PIG-002", "tag_number": "Spot"},
    ]


def test_missing_identity_and_unavailable_canonical_source_fail_closed():
    no_identity = answer_herd_question(
        "What is the latest recorded weight?",
        readiness=_readiness(_pig("PIG-001", "Spot")),
        matings=[],
    )
    unavailable = answer_herd_question(
        "What do you know about Spot?",
        readiness={"success": False, "pigs": []},
        matings=[],
    )
    assert no_identity["status"] == "animal_identity_required"
    assert unavailable["status"] == "canonical_herd_evidence_unavailable"
    assert no_identity["writes_performed"] is False
    assert unavailable["writes_performed"] is False


def test_common_possessive_and_for_subject_phrasings_resolve():
    readiness = _readiness(_pig("PIG-2026-34BF", "Shupe"))
    possessive = answer_herd_question(
        "What is Shupe's latest recorded weight?",
        readiness=readiness,
        matings=[],
    )
    for_phrase = answer_herd_question(
        "What is the breeding status for Shupe?",
        readiness=readiness,
        matings=[],
    )
    assert possessive["success"] is True
    assert for_phrase["success"] is True
    assert possessive["subject"]["pig_id"] == "PIG-2026-34BF"
    assert for_phrase["subject"]["pig_id"] == "PIG-2026-34BF"


def test_stale_or_absent_weight_is_explicit_and_never_inferred():
    stale = answer_herd_question(
        "What do you know about Old Sow?",
        readiness=_readiness(
            _pig(
                "PIG-OLD",
                "Old Sow",
                latest_weight_kg=90,
                latest_weight_date="2026-05-01",
                days_since_weight=89,
            )
        ),
        matings=[],
        today=date(2026, 7, 29),
    )
    absent = answer_herd_question(
        "What do you know about New Gilt?",
        readiness=_readiness(
            _pig(
                "PIG-NEW",
                "New Gilt",
                latest_weight_kg=None,
                latest_weight_date="",
                days_since_weight=None,
            )
        ),
        matings=[],
        today=date(2026, 7, 29),
    )
    assert stale["facts"]["latest_weight"]["stale"] is True
    assert any("stale" in item for item in stale["missing_or_stale_evidence"])
    assert absent["facts"]["latest_weight"]["weight_kg"] == "Unknown"
    assert absent["facts"]["latest_weight"]["evidence_date"] == "Unknown"
    assert "Latest weight date is Unknown." in (
        absent["missing_or_stale_evidence"]
    )


def load_tests(_loader, _tests, _pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite
