"""Controller-local recovery through existing admission and owner-stop rails."""
from copy import deepcopy
from datetime import timedelta

from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_command_mode import ENV, NOW, route, start, recover
from tests.test_rootline_execution_authority import inputs


def test_offline_camp_controller_defers_without_claim_then_online_is_eligible():
    plan, evidence, _ = inputs(zone="E12345")
    offline = route(now=NOW)
    offline["command_route_ready"] = False
    from modules.telemetry.rootline_command_acceptance import digest
    offline["response_digest"] = digest({k:v for k,v in offline.items() if k != "response_digest"})
    with timed_control_scope(ENV):
        held = build_execution_eligibility(plan=plan, evidence=evidence, controller=offline, now=NOW)
        ready = build_execution_eligibility(plan=plan, evidence=evidence, controller=route(now=NOW), now=NOW)
    assert not held["eligible"] and "job_resolution" not in held
    assert ready["eligible"] and ready["zone_id"] == "E12345"


def test_owner_paused_a_does_not_block_independently_eligible_e():
    plan, evidence, _ = inputs(zone="E12345")
    paused = deepcopy(plan["candidate_tasks"][0])
    paused.update(task_id="irrigation_A12345", rank=1, zone_decision="Hold",
        reason="owner_automatic_start_paused", incomplete_parent_job={"job": {
            "job_id": "OWNER-STOPPED-A", "zone_id": "A12345", "operating_date": plan["operating_date"]}})
    plan["candidate_tasks"].insert(0, paused)
    with timed_control_scope(ENV):
        result = build_execution_eligibility(plan=plan, evidence=evidence, controller=route(now=NOW), now=NOW)
    assert result["eligible"] and result["zone_id"] == "E12345"


def test_owner_stopped_a_stays_terminal_after_connectivity_returns():
    _, _, memory, transport, clock = start("A12345")
    original_id = memory.active["execution_id"]
    def store(action, body):
        if action == "load_owner_control_stop":
            return {"request_id": "owner-stop-a", "change": {"kind": "stop",
                "changes": {"execution_id": original_id}}}
        return memory(action, body)
    clock[0] += timedelta(minutes=1)
    stopped = recover(store, transport, clock)
    assert stopped["execution"]["reason"] == "owner_requested_stop"
    assert memory.active is None
    before = deepcopy(memory.rows)
    clock[0] += timedelta(minutes=5)
    recover(store, transport, clock)
    assert memory.active is None and memory.rows == before
    assert [call[2] for call in transport.calls] == ["ON", "OFF"]
