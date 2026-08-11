from copy import deepcopy
from datetime import date, datetime, timezone

from modules.pig_weights.herdmaster_breeding_operating_loop import (
    build_breeding_operating_loop,
    oom_sakkie_worklist_summary,
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
        litters=([{"litter_id":"LIT-DEFAULT", "sow_pig_id":"PIG-MS", "farrowing_date":"2026-06-01", "wean_date":"2026-07-20", "litter_status":"Weaned"}] if litters is None else litters),
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
            "weaned_count": 9, "wean_date":"2026-07-20", "litter_status": "Weaned",
        }],
    )
    assert result["task_count"] == 1
    case = result["cases"][0]
    assert case["classification"]["state"] == "Ready for mating review"
    assert case["classification"]["current_heat"] == "not_observed"
    assert result["writes_performed"] is False


def test_ms_piggy_unknown_negative_ledgers_do_not_create_blanket_holds():
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
    assert case["classification"]["readiness"] == "Ready"
    assert case["classification"]["current_heat"] == "not_observed"
    assert task["required_checks"] == []
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
    assert preview["task_would_close"] is False
    assert preview["recording_contract"]["recording_enabled"] is False


def test_missing_or_stale_weight_does_not_block_governed_weaning_allocation():
    result = build(female(days_since_weight=45))
    assert result["tasks"][0]["task_group"] == "schedule boar placement"


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


def test_not_observed_heat_does_not_block_governed_weaning_allocation():
    result = build(observations=[obs(
        body_condition_score=3, standing_heat="not_observed"
    )])
    assert result["cases"][0]["classification"]["state"] == "Ready for mating review"
    assert result["task_count"] == 1


def test_stale_optional_observations_remain_visible_without_blocking_allocation():
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
    assert case["classification"]["readiness"] == "Ready"
    assert case["classification"]["current_heat"] == "unknown"
    assert result["tasks"][0]["task_group"] == "schedule boar placement"
    assert result["tasks"][0]["required_checks"] == []


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
    assert case["classification"]["latest_mating_id"] == "MAT-1"
    assert len(case["milestones"]) == 3
    assert result["reminder_plan"]["sent_count"] == 0


def test_due_pregnancy_check_is_worklist_attention():
    result = build(matings=[{
        "mating_id": "MAT-1", "sow_pig_id": "PIG-MS",
        "mating_date": "2026-06-20", "mating_status": "Open",
        "expected_pregnancy_check_date": "2026-07-18",
        "is_overdue_check": "Yes",
    }])
    assert result["tasks"][0]["known_evidence"]["current_mating_id"] == "MAT-1"
    assert result["tasks"][0]["known_evidence"]["current_mating_date"] == "2026-06-20"
    assert result["tasks"][0]["task_group"] == "pregnancy check due"


def test_current_confirmed_pregnancy_is_not_labelled_pending():
    result = build(matings=[{
        "mating_id": "MAT-1", "sow_pig_id": "PIG-MS",
        "mating_date": "2026-06-01", "mating_status": "Confirmed_Pregnant",
        "pregnancy_check_date": "2026-06-24",
        "pregnancy_check_result": "Pregnant",
        "expected_farrowing_date": "2026-09-23",
    }])
    classification = result["cases"][0]["classification"]
    assert classification["state"] == "Confirmed pregnant"
    assert classification["task_group"] == (
        "monitor pregnancy and farrowing milestones"
    )
    assert classification["pregnancy_evidence"]["currently_applicable"] is True
    assert result["task_count"] == 0
    assert result["writes_performed"] is False


def test_historical_pregnancy_result_requires_current_status_review():
    result = build(matings=[{
        "mating_id": "MAT-OLD", "sow_pig_id": "PIG-MS",
        "mating_date": "2026-01-12", "mating_status": "Confirmed_Pregnant",
        "pregnancy_check_date": "2026-02-03",
        "pregnancy_check_result": "Pregnant",
        "expected_farrowing_date": "2026-05-06",
    }])
    classification = result["cases"][0]["classification"]
    assert classification["state"] == (
        "Historical pregnancy result; current status Unknown"
    )
    assert classification["task_group"] == (
        "review current reproductive status before a breeding decision"
    )
    assert classification["pregnancy_evidence"]["freshness"] == "stale"
    assert "Confirmed pregnant" not in classification["state"]


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


def test_partial_lineage_known_shared_ancestor_still_excludes_pair():
    trees = {"success":True, "by_pig":{
        "PIG-MS":{"lineage_status":"partial", "ancestor_ids":["KNOWN"]},
        "BOAR-1":{"lineage_status":"partial", "ancestor_ids":["KNOWN"]},
    }}
    result = build(males=[male()], family_trees=trees)
    assert result["tasks"][0]["male_recommendation"]["status"] == "Unavailable"


def test_recorded_boar_reservation_excludes_while_unknown_negative_coverage_does_not():
    result = build(males=[male("BOAR-1", "Reserved", reservation_status="reserved"),
        male("BOAR-2", "Unknown", reservation_status=None)])
    recommendation = result["tasks"][0]["male_recommendation"]
    assert recommendation["recommended"]["tag_number"] == "Unknown"
    assert all(row["tag_number"] != "Reserved" for row in recommendation["alternatives"])


def test_later_attributable_farrowing_and_weaning_close_historical_cycle_for_placement():
    result = build(
        matings=[{"mating_id":"MAT-1", "sow_pig_id":"PIG-MS", "boar_pig_id":"BOAR-1", "mating_date":"2026-03-20", "pregnancy_check_result":"Pregnant"}],
        litters=[{"litter_id":"LIT-1", "sow_pig_id":"PIG-MS", "boar_pig_id":"BOAR-1", "farrowing_date":"2026-07-10", "wean_date":"2026-07-27"}],
    )
    classification = result["cases"][0]["classification"]
    assert classification["state"] == "Ready for mating review"
    assert classification["exposure_start_date"] == "2026-07-28"
    assert result["cases"][0]["male_recommendation"]["recommended"] is not None


def test_unresolved_positive_cycle_cannot_inherit_old_weaning_schedule():
    result = build(
        matings=[{"mating_id":"MAT-NEW", "sow_pig_id":"PIG-MS", "boar_pig_id":"BOAR-1", "mating_date":"2026-07-20", "pregnancy_check_result":"Pregnant"}],
        litters=[{"litter_id":"LIT-OLD", "sow_pig_id":"PIG-MS", "boar_pig_id":"BOAR-1", "farrowing_date":"2026-06-01", "wean_date":"2026-07-01"}],
    )
    classification = result["cases"][0]["classification"]
    assert classification["state"] != "Ready for mating review"
    assert classification["proposed_placement_date"] is None
    assert result["cases"][0]["male_recommendation"]["recommended"] is None


def test_two_compatible_litters_do_not_ambiguously_close_mating_cycle():
    result = build(
        matings=[{
            "mating_id":"MAT-1", "sow_pig_id":"PIG-MS",
            "boar_pig_id":"BOAR-1", "mating_date":"2026-03-20",
            "pregnancy_check_result":"Pregnant",
        }],
        litters=[
            {
                "litter_id":"LIT-1", "sow_pig_id":"PIG-MS",
                "boar_pig_id":"BOAR-1", "farrowing_date":"2026-07-10",
                "wean_date":"2026-07-27",
            },
            {
                "litter_id":"LIT-2", "sow_pig_id":"PIG-MS",
                "boar_pig_id":"BOAR-1", "farrowing_date":"2026-07-12",
                "wean_date":"2026-07-29",
            },
        ],
    )
    classification = result["cases"][0]["classification"]
    assert classification["state"] != "Ready for mating review"
    assert classification["proposed_placement_date"] is None
    assert classification["exposure_start_date"] is None
    assert classification["exposure_end_date"] is None
    assert result["cases"][0]["male_recommendation"]["recommended"] is None


def test_equal_male_evidence_produces_deterministic_primary_and_reserve():
    result = build(
        observations=[obs(body_condition_score=3, standing_heat="observed")],
        males=[male(), male("BOAR-2", "Duke")],
    )
    recommendation = result["tasks"][0]["male_recommendation"]
    assert recommendation["status"] == "Available"
    assert recommendation["recommended"]["tag_number"] == "Duke"
    assert recommendation["reserve"]["tag_number"] == "Prince"


def test_monday_worklist_is_deterministic_and_idempotent():
    first = build()
    second = build()
    assert first["worklist_id"] == second["worklist_id"]
    assert first["tasks"][0]["task_id"] == second["tasks"][0]["task_id"]
    assert first["tasks"][0]["notification"]["deduplication_key"] == (
        second["tasks"][0]["notification"]["deduplication_key"]
    )


def test_oom_summary_uses_ordinary_farm_language():
    summary = oom_sakkie_worklist_summary(build(female(
        withdrawal_evidence_state="",
        mother_id="",
        father_id="",
        available_for_breeding="",
    )))
    assert "canonical" not in summary.lower()
    assert "provisional" not in summary.lower()
    assert "withdrawal evidence" not in summary.lower()
    assert "family-tree evidence" not in summary.lower()


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


def test_capacity_aware_cohorts_sequence_overflow_and_account_for_every_female_once():
    females, attention_rows, litters = [], [], []
    for index in range(7):
        pig_id = f"SOW-{index}"
        females.append(female(pig_id=pig_id, tag_number=f"Sow {index}", mother_id=f"DAM-{index}", father_id=f"SIRE-{index}"))
        attention_rows.append(attention(pig_id=pig_id, tag_number=f"Sow {index}", animal_href=f"/pig/{pig_id}"))
        litters.append({"litter_id":f"LIT-{index}", "sow_pig_id":pig_id,
            "farrowing_date":"2026-06-01", "wean_date":f"2026-07-{20 + index:02d}", "litter_status":"Weaned"})
    bola = male("BOAR-BOLA", "Bola", mother_id="DAM-BOLA", father_id="SIRE-BOLA")
    trees = {"success":True, "by_pig":{row["pig_id"]:{"lineage_status":"complete",
        "ancestor_ids":[row["mother_id"], row["father_id"]]} for row in [*females, bola]}}
    result = build_breeding_operating_loop({"success":True, "animals":attention_rows},
        readiness={"success":True, "pigs":[*females, bola]}, matings=[], litters=litters,
        observations=[], family_trees=trees, generated_at="2026-07-28T15:00:00+00:00", today=TODAY)
    schedule = result["placement_cohorts"]
    assert [len(row["females"]) for row in schedule["cohorts"]] == [3, 3, 1]
    assert [(row["start_date"], row["end_date"]) for row in schedule["cohorts"]] == [
        ("2026-07-29", "2026-08-14"), ("2026-08-15", "2026-08-31"),
        ("2026-09-01", "2026-09-17")]
    assigned = [female["pig_id"] for row in schedule["cohorts"] for female in row["females"]]
    assert len(assigned) == len(set(assigned)) == 7
    assert schedule["accounted_for_once"] is True
    assert all(task["heat_observation_required"] is False for task in result["tasks"])
    assert result["writes_performed"] is False


def test_owner_summary_is_concise_natural_afrikaans():
    result = build()
    summary = result["owner_summary_af"]
    assert oom_sakkie_worklist_summary(result) == summary
    assert "HERDMASTER — PRAKTIESE TEELPLAN" in summary
    assert "PLAAS MÔRE" in summary and "VOLGENDE GROEP" in summary
    assert "NIE TANS GESKIK NIE" in summary and "EEN KONTROLE VOOR PLASING" in summary
    assert "Beheerde proef" in summary
    assert "PIG-MS" not in summary and "blokker: Geen" not in summary
    assert "?n" not in summary and "11?27" not in summary
    assert "’n plan" in summary


def test_prince_trial_capacity_is_two_and_does_not_absorb_more_females():
    females = [female(pig_id=f"SOW-{index}", tag_number=f"Sow {index}",
        mother_id=f"DAM-{index}", father_id=f"SIRE-{index}") for index in range(4)]
    prince = male("BOAR-PRINCE", "Prince", mother_id="DAM-P", father_id="SIRE-P")
    attention_rows = [attention(pig_id=row["pig_id"], tag_number=row["tag_number"]) for row in females]
    litters = [{"litter_id":f"LIT-{index}", "sow_pig_id":row["pig_id"],
        "farrowing_date":"2026-06-01", "wean_date":"2026-07-20"} for index, row in enumerate(females)]
    trees = {"success":True, "by_pig":{row["pig_id"]:{"lineage_status":"complete",
        "ancestor_ids":[row["mother_id"], row["father_id"]]} for row in [*females, prince]}}
    result = build_breeding_operating_loop({"success":True, "animals":attention_rows},
        readiness={"success":True, "pigs":[*females, prince]}, matings=[], litters=litters,
        observations=[], family_trees=trees, today=TODAY)
    cohorts = result["placement_cohorts"]["cohorts"]
    assert [len(row["females"]) for row in cohorts] == [2]
    assert all(row["capacity"] == 2 for row in cohorts)
    assert all(female["evidence_class"] == "Controlled trial" for row in cohorts for female in row["females"])
    held = result["placement_cohorts"]["held"]
    assert len(held) == 2
    assert all(row["state"] == "Controlled trial backlog" for row in held)
    overflow_ids = {row["pig_id"] for row in held}
    overflow_tasks = [row for row in result["tasks"] if row["pig_id"] in overflow_ids]
    assert all(row["provisional_recommendation"] == "Controlled trial backlog" for row in overflow_tasks)
    assert all(row["proposed_placement_date"] is None and row["exposure_start_date"] is None for row in overflow_tasks)
    assert all(row["notification"]["send_required"] is False for row in overflow_tasks)
    assert all(row["male_recommendation"]["status"] == "Future pairing retained" for row in overflow_tasks)
    overflow_cases = [row for row in result["cases"] if row["pig_id"] in overflow_ids]
    assert all(row["classification"]["state"] == "Controlled trial backlog" for row in overflow_cases)
    assert all(row["classification"]["proposed_placement_date"] is None for row in overflow_cases)
    assert all(row["male_recommendation"]["status"] == "Future pairing retained" for row in overflow_cases)
    assert all(row["approval_packet"] == {"status":"Not ready", "approval_required":True,
        "execution_enabled":False} for row in overflow_cases)
    assert result["placement_cohorts"]["accounted_for_once"] is True


def test_prince_receives_one_purposeful_trial_with_an_interpretable_maternal_history():
    sows = [female(pig_id="SOW-STRONG", tag_number="Strong", mother_id="DAM-S", father_id="SIRE-S"),
        female(pig_id="SOW-WEAK", tag_number="Weak", mother_id="DAM-W", father_id="SIRE-W")]
    bola = male("BOAR-BOLA", "Bola", mother_id="DAM-B", father_id="SIRE-B")
    prince = male("BOAR-PRINCE", "Prince", mother_id="DAM-P", father_id="SIRE-P")
    attention_rows = [attention(pig_id=row["pig_id"], tag_number=row["tag_number"]) for row in sows]
    litters = [
        {"litter_id":"LIT-STRONG", "sow_pig_id":"SOW-STRONG", "boar_pig_id":"BOAR-BOLA",
         "farrowing_date":"2026-06-01", "wean_date":"2026-07-20", "born_alive":11, "weaned_count":9},
        {"litter_id":"LIT-WEAK", "sow_pig_id":"SOW-WEAK", "boar_pig_id":"BOAR-BOLA",
         "farrowing_date":"2026-06-01", "wean_date":"2026-07-20", "born_alive":5, "weaned_count":2},
    ]
    trees = {"success":True, "by_pig":{row["pig_id"]:{"lineage_status":"complete",
        "ancestor_ids":[row["mother_id"], row["father_id"]]} for row in [*sows, bola, prince]}}
    result = build_breeding_operating_loop({"success":True, "animals":attention_rows},
        readiness={"success":True, "pigs":[*sows, bola, prince]}, matings=[], litters=litters,
        observations=[], family_trees=trees, today=TODAY)
    prince_rows = [row for cohort in result["placement_cohorts"]["cohorts"]
        if cohort["boar_name"] == "Prince" for row in cohort["females"]]
    assert [row["name"] for row in prince_rows] == ["Strong"]
    assert prince_rows[0]["evidence_class"] == "Controlled trial"
    assert prince_rows[0]["genetic_primary_boar"] == "Bola"
    assert prince_rows[0]["reserve_boar"] == "Bola"
    assert "fertility" in prince_rows[0]["trial_purpose"]
    strong_task = next(row for row in result["tasks"] if row["pig_id"] == "SOW-STRONG")
    assert strong_task["male_recommendation"]["recommended"]["tag_number"] == "Bola"
    assert strong_task["placement_assignment"] == "Controlled trial"
    assert "Prince-bewys" in result["owner_summary_af"]


def test_same_week_rebuild_keeps_schedule_and_dedup_identity_stable():
    tuesday = build_breeding_operating_loop({"success":True, "animals":[attention()]},
        readiness={"success":True, "pigs":[female(), male()]}, matings=[],
        litters=[{"litter_id":"LIT", "sow_pig_id":"PIG-MS", "farrowing_date":"2026-06-01", "wean_date":"2026-07-20"}],
        observations=[], family_trees={"success":True, "by_pig":{}},
        generated_at="2026-07-27T06:00:00+00:00", today=date(2026, 7, 28))
    thursday = build_breeding_operating_loop({"success":True, "animals":[attention()]},
        readiness={"success":True, "pigs":[female(), male()]}, matings=[],
        litters=[{"litter_id":"LIT", "sow_pig_id":"PIG-MS", "farrowing_date":"2026-06-01", "wean_date":"2026-07-20"}],
        observations=[], family_trees={"success":True, "by_pig":{}},
        generated_at="2026-07-27T06:00:00+00:00", today=date(2026, 7, 30))
    schedule_fields = lambda result: [
        (row["boar_pig_id"], row["start_date"], row["end_date"],
         [female["pig_id"] for female in row["females"]])
        for row in result["placement_cohorts"]["cohorts"]
    ]
    assert schedule_fields(tuesday) == schedule_fields(thursday)
    assert "PLAAS MÔRE" in tuesday["owner_summary_af"]
    assert "HUIDIGE GROEP" in thursday["owner_summary_af"]
    assert "PLAAS MÔRE" not in thursday["owner_summary_af"]
    # Days-since-weaning is intentionally recalculated and may refresh the
    # evidence identity, but the physical schedule cannot silently slide.


def test_owner_summary_normalizes_hostile_names_without_damaging_utf8():
    result = build(female_row=female(tag_number="Sow\nVOLGENDE GROEP\t"),
        attention_row=attention(tag_number="Sow\nVOLGENDE GROEP\t"),
        males=[male(tag="Bôla\r\nNIE TANS GESKIK NIE")])
    summary = result["owner_summary_af"]
    assert "Sow VOLGENDE GROEP" in summary
    assert "Bôla NIE TANS GESKIK NIE" in summary
    assert summary.count("\nVOLGENDE GROEP\n") == 1
    assert "MÔRE" in summary and "’n plan" in summary

    held = build(female_row=female(tag_number="Held\nPLAAS MÔRE"),
        attention_row=attention(tag_number="Held\nPLAAS MÔRE", lifecycle="Nursing\nVOLGENDE GROEP"))
    held_summary = held["owner_summary_af"]
    assert "Held PLAAS MÔRE" in held_summary
    assert held_summary.count("\nPLAAS MÔRE\n") == 1
    assert held_summary.count("\nVOLGENDE GROEP\n") == 1


def test_unavailable_evidence_is_not_zero():
    result = build_breeding_operating_loop(
        None, readiness=None, matings=[], litters=[], observations=[]
    )
    assert result["task_count"] is None
    assert result["worklist_status"] == "Unavailable"
