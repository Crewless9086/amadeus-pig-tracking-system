from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle


def rec(status="Recommend", reason="Water is due.", **extra):
    return {"status": status, "reason": reason, **extra}


def test_completed_history_outranks_a_later_hold_recommendation():
    lifecycle = project_zone_lifecycle(zone_id="C12345", recommendation=rec("Hold"),
        history={"events": [{"qualifies_as_completed_watering": True,
            "shutdown_verified": True, "verified_runtime_minutes": 59.98}]})
    assert lifecycle["state"] == "Completed"
    assert "59.98" in lifecycle["reason"]


def test_completed_segment_with_remaining_parent_is_revalidating_not_complete():
    lifecycle = project_zone_lifecycle(zone_id="C12345", recommendation=rec(),
        history={"incomplete_parent_job": {"job": {"job_id": "JOB-1"}},
                 "events": [{"qualifies_as_completed_watering": True,
                    "shutdown_verified": True, "verified_runtime_minutes": 59.98}]})
    assert lifecycle["state"] == "Revalidating"


def test_safely_stopped_partial_execution_is_not_parent_completion():
    partial = project_zone_lifecycle(zone_id="C12345", recommendation=rec(),
        execution={"action": "record_completed", "state": "Completed",
                   "shutdown_verified": True, "objective_satisfied": False})
    whole = project_zone_lifecycle(zone_id="C12345", recommendation=rec(),
        execution={"action": "record_completed", "state": "Completed",
                   "shutdown_verified": True, "objective_satisfied": True})
    assert partial["state"] == "Recommended"
    assert whole["state"] == "Completed"


def test_recommendation_and_exact_hold_reason_are_truthful():
    recommended = project_zone_lifecycle(zone_id="B12345", recommendation=rec())
    held = project_zone_lifecycle(zone_id="B12345",
        recommendation=rec("Hold", "Fresh observed rain."))
    unknown = project_zone_lifecycle(zone_id="B12345", recommendation={"status": "Hold"})
    assert recommended["state"] == "Recommended"
    assert held["state"] == "Held" and held["reason"] == "Fresh observed rain."
    assert unknown["state"] == "Held" and unknown["reason"] == "Unknown"
    assert all(row["next_action_owner"] == "ROOTLINE" for row in (recommended, held, unknown))


def test_progression_and_failure_precedence():
    assert project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        eligibility={"eligible": True})["state"] == "Eligible"
    assert project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        execution={"action": "claim_before_on"})["state"] == "Authorized"
    assert project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        execution={"action": "mark_active"})["state"] == "Started"
    assert project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        execution={"action": "contain_zone", "transport_status": "ambiguous"})["state"] == "Failed"


def test_incomplete_parent_revalidates_and_stale_tank_is_not_a_hold_reason():
    lifecycle = project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        history={"incomplete_parent_job": {"job": {"job_id": "JOB-1"}}})
    assert lifecycle["state"] == "Revalidating"
    assert "tank" not in lifecycle["reason"].casefold()
