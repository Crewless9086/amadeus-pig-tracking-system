from copy import deepcopy

import pytest

from modules.pig_weights.herdmaster_management_round import build_management_round


def task(pig_id, tag, group, *, priority=18, why="Evidence is unresolved."):
    return {
        "task_id": f"TASK-{pig_id}", "pig_id": pig_id, "tag_number": tag,
        "task_group": group, "priority": priority, "why": why,
        "delay_consequence": "The management decision remains uncertain.",
        "known_evidence": {
            "latest_weight_kg": 100, "latest_weight_date": "2026-07-20",
            "state": "Pregnancy evidence pending",
        },
        "required_checks": ["governed pregnancy check result"],
        "provisional_recommendation": "Pregnancy evidence pending",
        "completed": False, "writes_performed": False,
        "evidence_digest": f"DIGEST-{pig_id}",
    }


def canonical(tasks):
    return {
        "success": True, "writes_performed": False,
        "generated_at": "2026-08-02T11:42:31+00:00",
        "worklist_id": "HERD-WEEK-1", "tasks": tasks,
    }


def pig11_case():
    return {
        "pig_id": "PIG-2026-E88A", "tag_number": "11",
        "current_evidence": ["Owner reported lying down and not eating."],
        "why_it_matters_now": "A current welfare concern is awaiting physical triage.",
        "decision_that_could_change": "Urgency and the next welfare action.",
        "specialist_ownership": "Oom Sakkie active welfare lifecycle",
        "reassessment_trigger": "Authenticated reply to Telegram message 3171",
        "source_identity": "OOM-TASK-2BF8CA3472DBB79367446204",
    }


def owner_observation(pig_id, result, days):
    return {
        "pig_id": pig_id, "operational_result": result,
        "observed_signs": "belly dropping and teats growing" if result == "Assumed Pregnant" else "visual check inconclusive",
        "days_to_expected_farrowing": days,
        "smallest_missing_physical_observation": (
            "One attributable current-cycle pregnancy-check result with date, method and assessor."
        ),
        "decision_that_could_change": "Pregnancy/farrowing follow-up or reproductive-status review.",
        "specialist_ownership": "HERDMASTER pregnancy evidence",
        "reassessment_trigger": "A confirmed current-cycle result or newer canonical cycle evidence.",
        "source_identity": f"OWNER-OBS-{pig_id}",
        "observed_at": "2026-08-01T06:09:01+00:00",
        "canonical_task_id": f"TASK-{pig_id}",
    }


def test_ranks_active_welfare_then_near_term_assumed_pregnant_without_duplicate_question():
    tasks = [
        task("PIG-2026-7DAA", "Baby", "pregnancy check due"),
        task("PIG-2026-D050", "Mona", "pregnancy check due"),
        task("PIG-2026-21BE", "Mysikind", "pregnancy check due"),
        task("PIG-POST", "Teena", "post-litter recovery check"),
    ]
    result = build_management_round(
        canonical(tasks), active_specialist_cases=[pig11_case()],
        attributable_owner_observations=[
            owner_observation("PIG-2026-7DAA", "Inconclusive", 39),
            owner_observation("PIG-2026-D050", "Assumed Pregnant", 22),
            owner_observation("PIG-2026-21BE", "Assumed Pregnant", 22),
        ],
    )
    assert [row["pig_id"] for row in result["ranked_actions"]] == [
        "PIG-2026-E88A", "PIG-2026-21BE", "PIG-2026-D050",
    ]
    welfare = result["ranked_actions"][0]
    assert welfare["question_suppressed"] is True
    assert welfare["smallest_missing_physical_observation"] == (
        "Already requested by Oom Sakkie; do not ask again."
    )
    for pregnancy in result["ranked_actions"][1:]:
        assert "Assumed Pregnant" in pregnancy["current_evidence"][-1]
        assert "not clinically confirmed" in pregnancy["current_evidence"][-1]
    assert "Assumed Pregnant" in result["owner_text"]
    assert "not clinically confirmed" in result["owner_text"]
    assert "acting strangely" not in result["owner_text"]  # exact test fixture uses a shorter welfare fact
    assert "Owner reported lying down" in result["owner_text"]


def test_contained_zigay_case_is_suppressed_not_rewritten():
    result = build_management_round(
        canonical([task("PIG-2026-EEAC", "Zigay", "lifecycle/data-quality conflict")]),
        contained_animal_ids=["PIG-2026-EEAC"],
    )
    assert result["ranked_actions"] == []
    assert result["suppressed"]["contained_data_quality_cases"] == ["PIG-2026-EEAC"]


def test_completed_duplicate_and_lower_ranked_work_are_suppressed():
    completed = task("PIG-DONE", "Done", "pregnancy check due")
    completed["completed"] = True
    result = build_management_round(canonical([
        completed,
        task("PIG-1", "One", "pregnancy check due"),
        task("PIG-2", "Two", "post-litter recovery check"),
        task("PIG-3", "Three", "breeding readiness"),
        task("PIG-4", "Four", "weigh before breeding decision"),
    ]))
    assert result["ranked_action_count"] == 3
    assert "PIG-DONE" not in {row["pig_id"] for row in result["ranked_actions"]}
    assert result["suppressed"]["lower_ranked_count"] == 1


def test_deterministic_publication_and_evidence_change():
    packet = canonical([task("PIG-1", "One", "pregnancy check due")])
    first = build_management_round(deepcopy(packet))
    replay = build_management_round(deepcopy(packet))
    assert first["publication_id"] == replay["publication_id"]
    assert first["deduplication_key"] == replay["deduplication_key"]
    refreshed_at = deepcopy(packet)
    refreshed_at["generated_at"] = "2026-08-02T12:42:31+00:00"
    assert build_management_round(refreshed_at)["publication_id"] == first["publication_id"]
    changed = deepcopy(packet)
    changed["tasks"][0]["why"] = "New canonical evidence."
    assert build_management_round(changed)["publication_id"] != first["publication_id"]
    digest_changed = deepcopy(packet)
    digest_changed["tasks"][0]["evidence_digest"] = "DIGEST-NEW"
    assert build_management_round(digest_changed)["publication_id"] != first["publication_id"]


def test_internal_publication_has_no_delivery_or_farm_authority():
    result = build_management_round(canonical([task("PIG-1", "One", "pregnancy check due")]))
    assert result["publish_to"] == "oom_sakkie_internal_owner_attention"
    assert result["automatic_publication_ready"] is True
    assert result["direct_owner_delivery"] is False
    for key in (
        "zero_io", "writes_farm_data", "sends_telegram", "directly_messages_owner",
        "creates_mating", "changes_lifecycle", "changes_availability",
        "publication_execution_authority",
    ):
        assert result[key] is (key == "zero_io")


def test_duplicate_active_cases_and_observations_fail_closed():
    with pytest.raises(ValueError, match="duplicate_active_specialist_case"):
        build_management_round(
            canonical([]), active_specialist_cases=[pig11_case(), pig11_case()]
        )
    observation = owner_observation("PIG-1", "Assumed Pregnant", 20)
    with pytest.raises(ValueError, match="duplicate_owner_observation"):
        build_management_round(
            canonical([task("PIG-1", "One", "pregnancy check due")]),
            attributable_owner_observations=[observation, {**observation, "operational_result": "Inconclusive"}],
        )


def test_unattributed_future_or_wrong_task_observation_fails_closed():
    base = owner_observation("PIG-1", "Assumed Pregnant", 20)
    packet = canonical([task("PIG-1", "One", "pregnancy check due")])
    for changed, reason in (
        ({**base, "source_identity": ""}, "source_identity"),
        ({**base, "observed_at": "2026-08-03T00:00:00+00:00"}, "future_dated"),
        ({**base, "canonical_task_id": "TASK-OTHER"}, "task_binding_mismatch"),
    ):
        with pytest.raises(ValueError, match=reason):
            build_management_round(packet, attributable_owner_observations=[changed])


def test_duplicate_or_write_capable_canonical_task_fails_closed():
    first = task("PIG-1", "One", "pregnancy check due")
    with pytest.raises(ValueError, match="duplicate_canonical_task_identity"):
        build_management_round(canonical([first, deepcopy(first)]))
    unsafe = {**first, "writes_performed": True}
    with pytest.raises(ValueError, match="canonical_task_read_only_required"):
        build_management_round(canonical([unsafe]))


@pytest.mark.parametrize("mutation", [
    {"success": False}, {"writes_performed": True}, {"generated_at": "bad"},
])
def test_fail_closed_on_noncanonical_or_write_capable_source(mutation):
    packet = {**canonical([]), **mutation}
    with pytest.raises(ValueError):
        build_management_round(packet)
