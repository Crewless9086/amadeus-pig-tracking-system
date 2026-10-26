from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle
import pytest


def rec(status="Recommend", reason="Water is due.", **extra):
    return {"status": status, "reason": reason, **extra}


def test_current_hold_outranks_historical_completed_watering():
    lifecycle = project_zone_lifecycle(zone_id="C12345", recommendation=rec("Hold"),
        history={"events": [{"qualifies_as_completed_watering": True,
            "shutdown_verified": True, "verified_runtime_minutes": 59.98}]})
    assert lifecycle["state"] == "Held"
    assert "completion_evidence" not in lifecycle


def test_newer_active_execution_outranks_historical_completion():
    lifecycle = project_zone_lifecycle(zone_id="C12345", recommendation=rec("Hold"),
        history={"events": [{"qualifies_as_completed_watering": True,
            "shutdown_verified": True, "verified_runtime_minutes": 59.9833}]},
        execution={"action": "mark_active", "state": "Active",
                   "execution_id": "ROOTLINE-EXECUTION-CURRENT"})
    assert lifecycle["state"] == "Started"
    assert lifecycle["next_action_owner"] == "ROOTLINE"


def test_ambiguous_current_execution_fails_closed_over_historical_completion():
    lifecycle = project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        history={"events": [{"qualifies_as_completed_watering": True,
            "shutdown_verified": True, "verified_runtime_minutes": 59.9833}]},
        execution={"state": "ambiguous", "reason": "conflicting_active_executions"})
    assert lifecycle["state"] == "Failed"
    assert lifecycle["reason"] == "conflicting_active_executions"


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


@pytest.mark.parametrize('remaining', [False, True])
def test_canonical_terminal_execution_does_not_reuse_its_old_eligibility(remaining):
    terminal = {'action': 'record_completed', 'state': 'Completed',
        'execution_id': 'EXEC-1', 'eligibility_id': 'OLD-ELIGIBILITY',
        'shutdown_verified': True, 'objective_satisfied': True}
    history = {'incomplete_parent_job': {'job': {'job_id': 'JOB-1'}}} if remaining else {}
    value = project_zone_lifecycle(zone_id='C12345', recommendation=rec(),
        history=history, execution=terminal)
    assert value['state'] == ('Revalidating' if remaining else 'Completed')
    assert 'claim' not in value['next_action'].casefold()


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
@pytest.mark.parametrize("recommendation", [
    rec("Hold", "Observed rain."), rec("Needs Data", "Weather is stale."),
    rec("Do Not Run", "Contained parent needs recovery."),
    rec(eligibility_blocker="controller_safety_not_dispatchable"),
    {"zone_decision": "Run later", "recommendation": "Recommend", "reason": "Wait for the planned window."},
])
@pytest.mark.parametrize("prior", ["eligibility", "completion"])
def test_current_block_cannot_be_overridden_by_execution_history(zone, recommendation, prior):
    execution = {"eligibility_id": "HISTORICAL-ELIGIBILITY"}
    if prior == "completion":
        execution.update(action="record_completed", state="Completed",
                         shutdown_verified=True, objective_satisfied=True)
    value = project_zone_lifecycle(zone_id=zone, recommendation=recommendation,
        execution=execution, eligibility={"eligible": True})
    assert value["state"] == "Held"
    assert "claim" not in value["next_action"].lower()
    assert "completion_evidence" not in value


@pytest.mark.parametrize("state", ["claimed", "claimed_recovery_required"])
def test_old_eligibility_reference_without_a_current_artifact_is_not_eligibility(state):
    value = project_zone_lifecycle(zone_id="B12345", recommendation=rec(),
        evidence_cutoff="2026-10-25T21:00:00+00:00",
        execution={"action": "record_claim_recovery", "state": state,
            "zone_id": "B12345", "execution_id": "SYNTHETIC-OLD",
            "eligibility_id": "OLD", "shutdown_verified": True,
            "claimed_at": "2026-10-25T20:00:00+00:00",
            "shutdown_evidence": {"authoritative": True, "state": "OFF",
                "retrieved_at": "2026-10-25T20:30:00+00:00"}})
    assert value["state"] == "Recommended"


@pytest.mark.parametrize("action,state,expected", [
    ("claim_before_on", "claimed", "Authorized"),
    ("mark_active", "Active", "Started"),
    ("contain_zone", "ambiguous", "Failed"),
])
def test_execution_safety_state_still_precedes_blocked_plan_and_parents(action,state,expected):
    value = project_zone_lifecycle(zone_id="C12345", recommendation=rec("Do Not Run"),
        history={"contained_parent_jobs": [{"job": {"job_id": "OLD"}}]},
        execution={"action": action, "state": state, "eligibility_id": "OLD"})
    assert value["state"] == expected
    assert value["next_action_owner"] == "ROOTLINE"


def test_fresh_eligibility_can_advance_a_current_remaining_parent():
    value = project_zone_lifecycle(zone_id="C12345", recommendation=rec(),
        history={"incomplete_parent_job": {"job": {"job_id": "CURRENT"}}},
        eligibility={"eligible": True})
    assert value["state"] == "Eligible"


@pytest.mark.parametrize("obstruction", [
    {"history": {"contained_parent_jobs": [{"job": {"job_id": "OLD"}}]}},
    {"history": {"stale_incomplete_parent_jobs": [{"job": {"job_id": "OLD"}}]}},
    {"status": "Hold"}, {"status": "Needs Data"},
    {"eligibility_blocker": "controller_safety_not_dispatchable"},
])
def test_typed_completion_does_not_clear_unresolved_parent_or_current_safety_hold(obstruction):
    value = project_zone_lifecycle(zone_id="B12345",
        recommendation={"status": "Do Not Run", "zone_decision": "Completed",
            **{key: val for key, val in obstruction.items() if key != "history"}},
        history=obstruction.get("history"),
        execution={"action": "record_completed", "state": "Completed",
            "shutdown_verified": True, "objective_satisfied": True})
    assert value["state"] == "Held" and "completion_evidence" not in value


def test_typed_completion_without_canonical_proof_is_not_completion_or_eligibility():
    value = project_zone_lifecycle(zone_id="B12345",
        recommendation={"status": "Do Not Run", "zone_decision": "Completed"},
        eligibility={"eligible": True})
    assert value["state"] == "Held" and "completion_evidence" not in value


@pytest.mark.parametrize("state,expected", [("claimed", "Authorized"), ("Active", "Started")])
def test_unverified_recovery_does_not_hide_claimed_or_active_safety_reporting(state, expected):
    value = project_zone_lifecycle(zone_id="B12345", recommendation=rec("Hold"),
        execution={"action": "record_claim_recovery", "state": state, "shutdown_verified": False})
    assert value["state"] == expected
