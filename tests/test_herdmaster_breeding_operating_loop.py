from copy import deepcopy
from datetime import date, datetime, timezone

from modules.pig_weights.herdmaster_breeding_operating_loop import (
    build_breeding_operating_loop,
    preview_conversational_inspection,
)

TODAY = date(2026, 7, 28)


def female(**updates):
    row = {
        "pig_id": "PIG-MS", "tag_number": "Ms Piggy", "sex": "Female",
        "animal_type": "Sow", "status": "Active", "on_farm": "Yes",
        "purpose": "Breeding", "medical_status": "Clear",
        "withdrawal_evidence_state": "cleared",
        "available_for_breeding": "available",
        "mother_id": "DAM-MS", "father_id": "SIRE-MS",
        "latest_weight_kg": 126.4, "latest_weight_date": "2026-07-20",
        "days_since_weight": 8,
    }
    row.update(updates)
    return row


def male(pig_id="BOAR-1", tag="Prince", **updates):
    row = {
        "pig_id": pig_id, "tag_number": tag, "sex": "Male",
        "animal_type": "Boar", "status": "Active", "on_farm": "Yes",
        "purpose": "Breeding", "medical_status": "Clear",
        "withdrawal_evidence_state": "cleared",
        "available_for_breeding": "available",
        "mother_id": f"DAM-{pig_id}", "father_id": f"SIRE-{pig_id}",
    }
    row.update(updates)
    return row


def attention(**updates):
    row = {
        "pig_id": "PIG-MS", "tag_number": "Ms Piggy",
        "animal_href": "/pig/PIG-MS", "current_state": "Needs observation",
        "recommended_human_action": "observe for standing heat",
        "confidence": "Limited", "missing_facts": [],
        "conflicting_facts": [],
        "evidence_dates": {"observed_at": "2026-07-28"},
    }
    row.update(updates)
    return row


def obs(pig_id="PIG-MS", when="2026-07-28T14:19:00+00:00", **facts):
    return {
        "pig_id": pig_id,
        "observed_at": datetime.fromisoformat(when),
        "observation_category": "other",
        "measurements_json": {
            "contract_version": "herdmaster_breeding_observation_v1",
            **facts,
        },
        "observation_event_id": "HERD-OBS-ONE",
    }


def build(
    female_row=None, *, attention_row=None, males=None, matings=None,
    litters=None, observations=None, projected_observations=None,
    family_trees=None,
):
    female_row = female_row or female()
    male_rows = males or [male()]
    observation_rows = observations or []
    if projected_observations is None:
        projected_observations = {}
        for row in observation_rows:
            facts = row.get("measurements_json") or {}
            projected = projected_observations.setdefault(row["pig_id"], {})
            heat = facts.get("standing_heat")
            if heat not in (None, "", "not_recorded"):
                projected["heat_state"] = (
                    "standing" if heat == "observed" else heat
                )
                projected["heat_observed_at"] = row["observed_at"].isoformat()
                projected["heat_observation_event_id"] = row[
                    "observation_event_id"
                ]
            if facts.get("body_condition_score") is not None:
                projected["body_condition_score"] = facts[
                    "body_condition_score"
                ]
            physical = projected.setdefault("fresh_physical_facts", {})
            for key in ("visible_build", "feet_legs_movement", "visible_injury"):
                if facts.get(key) not in (None, "", "not_recorded"):
                    physical[key] = {
                        "value": facts[key],
                        "observed_at": row["observed_at"].isoformat(),
                        "observation_event_id": row["observation_event_id"],
                    }
    if family_trees is None:
        rows = [female_row, *male_rows]
        family_trees = {
            "success": True,
            "by_pig": {
                row["pig_id"]: {
                    "lineage_status": "complete",
                    "ancestor_ids": [
                        row["mother_id"], row["father_id"],
                    ],
                }
                for row in rows
            },
        }
    return build_breeding_operating_loop(
        {
            "success": True,
            "animals": [attention_row or attention()],
        },
        readiness={
            "success": True,
            "pigs": [female_row, *male_rows],
        },
        matings=matings or [],
        litters=litters or [],
        observations=observation_rows,
        projected_observations=projected_observations,
        family_trees=family_trees,
        generated_at="2026-07-28T15:00:00+00:00",
        today=TODAY,
    )


def test_ms_piggy_real_observation_closes_physical_recovery_check():
    result = build(
        observations=[obs(
            body_condition_score=3, visible_build="even",
            feet_legs_movement="no_visible_concern",
            visible_injury="none_observed", standing_heat="not_observed",
        )],
        litters=[{
            "litter_id": "LIT-MS", "sow_pig_id": "PIG-MS",
            "farrowing_date": "2026-07-01", "born_alive": 10,
            "weaned_count": 9, "litter_status": "Weaned",
        }],
    )
    assert result["task_count"] == 0
    case = result["cases"][0]
    assert case["classification"]["state"] == "Observe for heat"
    assert case["classification"]["current_heat"] == "not_observed"
    assert result["writes_performed"] is False


def test_ms_piggy_immutable_observation_asks_only_unresolved_nonphysical_facts():
    observation = obs(
        body_condition_score=3,
        visible_build="even",
        feet_legs_movement="no_visible_concern",
        visible_injury="none_observed",
        standing_heat="not_observed",
    )
    observation["observation_event_id"] = (
        "HERD-OBS-F9F01AF68E805C94B2533DA30CF3C801"
    )
    result = build(
        female_row=female(
            available_for_breeding="",
            withdrawal_evidence_state="",
            mother_id="",
            father_id="",
        ),
        observations=[observation],
    )
    task = result["tasks"][0]
    case = result["cases"][0]
    assert case["classification"]["readiness"] == "Needs Data"
    assert case["classification"]["current_heat"] == "not_observed"
    assert set(task["required_checks"]) == {
        "withdrawal evidence",
        "breeding availability",
        "family-tree evidence",
    }
    assert not {
        "body condition", "movement", "visible concerns", "heat signs",
    }.intersection(task["required_checks"])
    assert case["observation_history"][0]["observation_event_id"] == (
        "HERD-OBS-F9F01AF68E805C94B2533DA30CF3C801"
    )


def test_post_litter_natural_reply_previews_direct_facts_and_can_close_task():
    result = build(
        litters=[{
            "litter_id": "LIT-MS", "sow_pig_id": "PIG-MS",
            "farrowing_date": "2026-07-01",
        }],
    )
    preview = preview_conversational_inspection(
        result,
        "Ms Piggy body condition 3, moving well, no injury and no heat today.",
    )
    assert preview["success"] is True
    assert preview["facts"]["body_condition_score"] == 3
    assert preview["facts"]["standing_heat"] == "not_observed"
    assert preview["task_would_close"] is True
    assert preview["recording_contract"]["recording_enabled"] is False


def test_missing_or_stale_weight_requests_weighing():
    result = build(female(days_since_weight=45))
    assert result["tasks"][0]["task_group"] == "weigh before breeding decision"


def test_observed_heat_with_complete_evidence_ranks_compatible_male():
    result = build(observations=[obs(
        body_condition_score=3, standing_heat="observed"
    )])
    task = result["tasks"][0]
    assert result["cases"][0]["classification"]["readiness"] == "Ready"
    assert task["provisional_recommendation"] == "Ready for mating review"
    assert task["male_recommendation"]["recommended"]["tag_number"] == "Prince"
    packet = result["cases"][0]["approval_packet"]
    assert packet["known_fields_autofilled"] is True
    assert packet["execution_enabled"] is False
    assert packet["stale_approval_rejected"] is True
    assert packet["exact_replay_withheld"] is True


def test_not_observed_heat_never_becomes_ready():
    result = build(observations=[obs(
        body_condition_score=3, standing_heat="not_observed"
    )])
    assert result["cases"][0]["classification"]["state"] == "Observe for heat"
    assert result["task_count"] == 0


def test_stale_heat_and_body_condition_never_suppress_current_checks():
    stale = obs(
        when="2026-05-01T10:00:00+00:00",
        body_condition_score=3,
        standing_heat="observed",
        feet_legs_movement="no_visible_concern",
    )
    result = build(
        observations=[stale],
        projected_observations={},
    )
    case = result["cases"][0]
    assert case["classification"]["readiness"] == "Needs Data"
    assert case["classification"]["current_heat"] == "unknown"
    assert result["tasks"][0]["task_group"] == "inspect for breeding readiness"
    assert "body condition" in result["tasks"][0]["required_checks"]


def test_reported_male_exposure_is_not_a_canonical_mating():
    result = build(observations=[obs(
        body_condition_score=3, reported_male_exposure={
            "source": "owner_report", "approximate_date": "2026-07-10"
        },
    )])
    case = result["cases"][0]
    assert case["classification"]["canonical_mating_exists"] is False
    assert case["mating_history"] == []


def test_canonical_mating_creates_milestones_without_writes():
    result = build(matings=[{
        "mating_id": "MAT-1", "sow_pig_id": "PIG-MS",
        "boar_pig_id": "BOAR-1", "boar_tag_number": "Prince",
        "mating_date": "2026-07-20", "mating_status": "Open",
    }])
    case = result["cases"][0]
    assert case["classification"]["canonical_mating_exists"] is True
    assert len(case["milestones"]) == 3
    assert result["reminder_plan"]["sent_count"] == 0


def test_due_pregnancy_check_is_worklist_attention():
    result = build(matings=[{
        "mating_id": "MAT-1", "sow_pig_id": "PIG-MS",
        "mating_date": "2026-06-20", "mating_status": "Open",
        "expected_pregnancy_check_date": "2026-07-18",
        "is_overdue_check": "Yes",
    }])
    assert result["tasks"][0]["task_group"] == "pregnancy check due"


def test_repeat_service_requires_decision_but_never_disposition():
    result = build(matings=[
        {
            "mating_id": "MAT-2", "sow_pig_id": "PIG-MS",
            "mating_date": "2026-06-01",
            "mating_status": "Repeat_Service",
        },
        {
            "mating_id": "MAT-1", "sow_pig_id": "PIG-MS",
            "mating_date": "2026-04-01",
            "pregnancy_check_result": "Not_Pregnant",
        },
    ])
    classification = result["cases"][0]["classification"]
    assert classification["state"] == "Repeat-service decision required"
    assert result["cases"][0]["approval_packet"]["execution_enabled"] is False


def test_medical_or_withdrawal_hold_blocks_readiness():
    result = build(female(medical_status="Hold"))
    assert result["cases"][0]["classification"]["readiness"] == "Hold"
    assert result["tasks"][0]["provisional_recommendation"] == (
        "Hold for medical/withdrawal evidence"
    )


def test_family_conflict_excludes_male():
    result = build(
        observations=[obs(body_condition_score=3, standing_heat="observed")],
        males=[male(mother_id="DAM-MS")],
    )
    recommendation = result["tasks"][0]["male_recommendation"]
    assert recommendation["status"] == "Unavailable"
    assert recommendation["recommended"] is None


def test_father_daughter_and_incomplete_lineage_fail_closed():
    sire = male(pig_id="SIRE-MS", tag="Sire")
    trees = {
        "success": True,
        "by_pig": {
            "PIG-MS": {
                "lineage_status": "complete",
                "ancestor_ids": ["DAM-MS", "SIRE-MS"],
            },
            "SIRE-MS": {
                "lineage_status": "complete",
                "ancestor_ids": ["DAM-SIRE", "SIRE-SIRE"],
            },
        },
    }
    result = build(
        observations=[obs(body_condition_score=3, standing_heat="observed")],
        males=[sire],
        family_trees=trees,
    )
    assert result["tasks"][0]["male_recommendation"]["status"] == "Unavailable"
    trees["by_pig"]["SIRE-MS"] = {
        "lineage_status": "partial",
        "ancestor_ids": [],
        "cycle_nodes": ["SIRE-MS"],
    }
    partial = build(
        observations=[obs(body_condition_score=3, standing_heat="observed")],
        males=[sire],
        family_trees=trees,
    )
    assert partial["tasks"][0]["male_recommendation"]["status"] == "Unavailable"


def test_equal_male_evidence_requires_owner_choice():
    result = build(
        observations=[obs(body_condition_score=3, standing_heat="observed")],
        males=[male(), male("BOAR-2", "Duke")],
    )
    recommendation = result["tasks"][0]["male_recommendation"]
    assert recommendation["status"] == "Owner choice required"
    assert recommendation["recommended"] is None


def test_monday_worklist_is_deterministic_and_idempotent():
    first = build()
    second = build()
    assert first["worklist_id"] == second["worklist_id"]
    assert first["tasks"][0]["task_id"] == second["tasks"][0]["task_id"]
    assert first["tasks"][0]["notification"]["deduplication_key"] == (
        second["tasks"][0]["notification"]["deduplication_key"]
    )


def test_approval_identity_is_stable_and_changes_with_exact_evidence_or_male():
    first = build(observations=[obs(
        body_condition_score=3, standing_heat="observed"
    )])
    second = build(observations=[obs(
        body_condition_score=3, standing_heat="observed"
    )])
    first_packet = first["cases"][0]["approval_packet"]
    assert first_packet["approval_packet_id"] == (
        second["cases"][0]["approval_packet"]["approval_packet_id"]
    )
    changed = build(observations=[obs(
        body_condition_score=3.5, standing_heat="observed"
    )])
    assert first_packet["approval_packet_id"] != (
        changed["cases"][0]["approval_packet"]["approval_packet_id"]
    )
    changed_male = build(
        observations=[obs(body_condition_score=3, standing_heat="observed")],
        males=[male("BOAR-2", "Duke")],
    )
    assert first_packet["approval_packet_id"] != (
        changed_male["cases"][0]["approval_packet"]["approval_packet_id"]
    )


def test_ambiguous_reply_does_not_append_or_guess():
    result = build()
    preview = preview_conversational_inspection(
        result, "She might be in heat and looks okay."
    )
    assert preview["success"] is False
    assert preview["writes_performed"] is False


def test_no_duplicate_observation_mating_or_reminder_authority():
    serialized = str(build())
    assert "'observation_recording_enabled': False" in serialized
    assert "'mating_execution_enabled': False" in serialized
    assert "'delivery_operational': False" in serialized


def test_unavailable_evidence_is_not_zero():
    result = build_breeding_operating_loop(
        None, readiness=None, matings=[], litters=[], observations=[]
    )
    assert result["task_count"] is None
    assert result["worklist_status"] == "Unavailable"
