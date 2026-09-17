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


def _mating(pig_id="PIG-SOW", **overrides):
    row = {
        "mating_id": "MAT-CURRENT",
        "sow_pig_id": pig_id,
        "mating_date": "2026-06-01",
        "mating_status": "Open",
        "pregnancy_check_date": "2026-06-24",
        "pregnancy_check_result": "",
        "expected_farrowing_date": "2026-09-23",
        "is_open": "Yes",
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


def test_current_governed_pregnant_result_outranks_pending_case_status():
    result = answer_herd_question(
        "What do you know about Ada?",
        readiness=_readiness(_pig("PIG-ADA", "Ada")),
        matings=[_mating(
            "PIG-ADA",
            pregnancy_check_result="Pregnant",
            pregnancy_check_method="Ultrasound",
            pregnancy_check_assessor="Farm vet",
            pregnancy_check_time="09:30",
        )],
        worklist={
            "cases": [{
                "pig_id": "PIG-ADA",
                "classification": {
                    "state": "Pregnancy evidence pending",
                    "provisional_recommendation": "pregnancy check due",
                },
                "evidence": {
                    "missing": [
                        "pregnancy-check result",
                        "body condition",
                    ]
                },
            }],
            "tasks": [],
        },
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == "Confirmed pregnant"
    assert breeding["pregnancy_check_result"] == "Pregnant"
    assert breeding["pregnancy_result_date"] == "2026-06-24"
    assert breeding["pregnancy_currently_applicable"] is True
    assert breeding["pregnancy_evidence_freshness"] == "current"
    assert result["recommendation"]["action"] == (
        "monitor pregnancy and farrowing milestones"
    )
    assert "Pregnancy evidence pending" not in result["answer"]
    assert not any(
        "pregnancy-check result" in item.casefold()
        for item in result["missing_or_stale_evidence"]
    )
    assert "body condition is missing." in result[
        "missing_or_stale_evidence"
    ]


def test_current_governed_not_pregnant_result_drives_repeat_service_followup():
    result = answer_herd_question(
        "What do you know about Bea?",
        readiness=_readiness(_pig("PIG-BEA", "Bea")),
        matings=[_mating(
            "PIG-BEA",
            pregnancy_check_result="Not Pregnant",
            pregnancy_check_method="Ultrasound",
            pregnancy_check_assessor="Farm vet",
            pregnancy_check_time="10:00",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == "Confirmed not pregnant for latest mating"
    assert breeding["pregnancy_currently_applicable"] is True
    assert result["recommendation"]["action"] == (
        "review return-to-heat or repeat-service evidence"
    )
    assert "monitor pregnancy and farrowing" not in result["answer"]


def test_no_governed_result_is_pending_and_elapsed_days_are_not_diagnosis():
    result = answer_herd_question(
        "What do you know about Cora?",
        readiness=_readiness(_pig("PIG-CORA", "Cora")),
        matings=[_mating(
            "PIG-CORA",
            mating_date="2026-06-01",
            pregnancy_check_date="",
            pregnancy_check_result="",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == "Pregnancy evidence pending"
    assert breeding["pregnancy_check_result"] == "Unknown"
    assert breeding["pregnancy_currently_applicable"] is False
    assert result["recommendation"]["action"] == "pregnancy check due"
    assert "Confirmed pregnant" not in result["answer"]


def test_historical_pregnant_result_does_not_claim_current_pregnancy():
    result = answer_herd_question(
        "What do you know about Dora?",
        readiness=_readiness(_pig("PIG-DORA", "Dora")),
        matings=[_mating(
            "PIG-DORA",
            mating_date="2026-01-12",
            pregnancy_check_date="2026-02-03",
            pregnancy_check_result="Pregnant",
            expected_farrowing_date="2026-05-06",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == (
        "Historical pregnancy result; current status Unknown"
    )
    assert breeding["pregnancy_evidence_freshness"] == "stale"
    assert breeding["pregnancy_currently_applicable"] is False
    assert result["recommendation"]["action"] == (
        "review current reproductive status before a breeding decision"
    )


def test_conflicting_results_fail_closed_to_conflict_followup():
    result = answer_herd_question(
        "What do you know about Ella?",
        readiness=_readiness(_pig("PIG-ELLA", "Ella")),
        matings=[
            _mating("PIG-ELLA", pregnancy_check_result="Pregnant"),
            _mating(
                "PIG-ELLA",
                pregnancy_check_result="Not Pregnant",
                pregnancy_check_date="2026-06-25",
            ),
        ],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == "Conflicting pregnancy evidence"
    assert breeding["pregnancy_check_result"] == "Conflicting"
    assert breeding["pregnancy_currently_applicable"] is False
    assert result["recommendation"]["action"] == (
        "reconcile conflicting pregnancy results for the latest mating"
    )


def test_current_result_with_missing_support_names_only_specific_gaps():
    result = answer_herd_question(
        "What do you know about Faye?",
        readiness=_readiness(_pig("PIG-FAYE", "Faye")),
        matings=[_mating(
            "PIG-FAYE",
            pregnancy_check_result="Pregnant",
            pregnancy_check_method="",
            pregnancy_check_assessor="",
            pregnancy_check_time="",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == "Confirmed pregnant"
    assert breeding["pregnancy_check_method"] == "Unknown"
    assert breeding["pregnancy_check_assessor"] == "Unknown"
    assert breeding["pregnancy_result_time"] == "Unknown"
    assert "Pregnancy-check method is Unknown." in result[
        "missing_or_stale_evidence"
    ]
    assert "Pregnancy-check assessor is Unknown." in result[
        "missing_or_stale_evidence"
    ]
    assert "Pregnancy-check observation time is Unknown." in result[
        "missing_or_stale_evidence"
    ]
    assert "Pregnancy-check result is Unknown." not in result[
        "missing_or_stale_evidence"
    ]


def test_result_without_governed_date_is_unattributed_not_confirmed():
    result = answer_herd_question(
        "What do you know about Gia?",
        readiness=_readiness(_pig("PIG-GIA", "Gia")),
        matings=[_mating(
            "PIG-GIA",
            pregnancy_check_result="Pregnant",
            pregnancy_check_date="",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == "Pregnancy result is provisional or unattributed"
    assert breeding["pregnancy_currently_applicable"] is False
    assert "Pregnancy result date is Unknown." in result[
        "missing_or_stale_evidence"
    ]
    assert result["recommendation"]["action"] == (
        "review current reproductive status before a breeding decision"
    )


def test_pregnancy_precedence_preserves_zero_write_and_private_subject_scope():
    result = answer_herd_question(
        "What do you know about Hana?",
        readiness=_readiness(
            _pig("PIG-HANA", "Hana"),
            _pig("PIG-OTHER", "Other Sow"),
        ),
        matings=[
            _mating(
                "PIG-HANA",
                pregnancy_check_result="Pregnant",
                pregnancy_check_method="Ultrasound",
                pregnancy_check_assessor="Farm vet",
                pregnancy_check_time="11:00",
            ),
            _mating(
                "PIG-OTHER",
                mating_id="MAT-OTHER",
                pregnancy_check_result="Not Pregnant",
            ),
        ],
        today=date(2026, 7, 29),
    )
    assert result["writes_performed"] is False
    assert result["protected_actions_performed"] is False
    assert "Other Sow" not in result["answer"]
    assert "PIG-OTHER" not in result["answer"]


def test_lifecycle_exclusion_outranks_stale_readiness_and_pregnancy_labels():
    result = answer_herd_question(
        "What do you know about Ivy?",
        readiness=_readiness(_pig(
            "PIG-IVY",
            "Ivy",
            status="Retired",
            readiness_bucket="Retain / Breeding Candidate",
        )),
        matings=[_mating(
            "PIG-IVY",
            pregnancy_check_result="Pregnant",
            pregnancy_check_method="Ultrasound",
            pregnancy_check_assessor="Farm vet",
            pregnancy_check_time="12:00",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == (
        "Not currently eligible for breeding: lifecycle excludes breeding"
    )
    assert breeding["readiness_bucket"] == "Retain / Breeding Candidate"
    assert breeding["readiness_currently_applicable"] is False
    assert result["recommendation"]["basis"] == (
        "Canonical breeding exclusion precedence"
    )
    assert "monitor pregnancy and farrowing milestones" not in result["answer"]


def test_future_dated_result_fails_closed_and_is_not_confirmed():
    result = answer_herd_question(
        "What do you know about June?",
        readiness=_readiness(_pig("PIG-JUNE", "June")),
        matings=[_mating(
            "PIG-JUNE",
            pregnancy_check_date="2026-08-01",
            pregnancy_check_result="Pregnant",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["status"] == (
        "Pregnancy evidence is future-dated and not currently applicable"
    )
    assert breeding["pregnancy_currently_applicable"] is False
    assert result["recommendation"]["action"] == (
        "review and correct the future-dated reproductive chronology"
    )


def test_confirmed_pregnancy_names_missing_farrowing_milestone_date():
    result = answer_herd_question(
        "What do you know about Kira?",
        readiness=_readiness(_pig("PIG-KIRA", "Kira")),
        matings=[_mating(
            "PIG-KIRA",
            pregnancy_check_result="Pregnant",
            expected_farrowing_date="",
            pregnancy_check_method="Ultrasound",
            pregnancy_check_assessor="Farm vet",
            pregnancy_check_time="09:00",
        )],
        today=date(2026, 7, 29),
    )
    assert result["facts"]["breeding"]["status"] == "Confirmed pregnant"
    assert "Expected farrowing date is Unknown." in result[
        "missing_or_stale_evidence"
    ]


def test_boar_never_inherits_sows_pregnancy_result_or_recommendation():
    result = answer_herd_question(
        "What do you know about Leo?",
        readiness=_readiness(_pig(
            "PIG-LEO",
            "Leo",
            sex="Male",
        )),
        matings=[_mating(
            "PIG-SOW",
            boar_pig_id="PIG-LEO",
            boar_tag_number="Leo",
            pregnancy_check_result="Pregnant",
            pregnancy_check_method="Ultrasound",
            pregnancy_check_assessor="Farm vet",
            pregnancy_check_time="09:00",
        )],
        today=date(2026, 7, 29),
    )
    breeding = result["facts"]["breeding"]
    assert breeding["pregnancy_evidence_state"] == "not_applicable"
    assert breeding["pregnancy_check_result"] == "Unknown"
    assert breeding["status"] != "Confirmed pregnant"
    assert "monitor pregnancy and farrowing milestones" not in result["answer"]
    assert result["writes_performed"] is False


def load_tests(_loader, _tests, _pattern):
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite
