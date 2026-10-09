"""Pure admission and executive wiring tests; no external effects."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
from modules.charlie import manager_dependency_intake as intake
from modules.charlie import executive_runtime as executive
from modules.oom_sakkie.herdmaster_case_disposition import MortalityReconciliationPending
from tests.test_oom_sakkie_mortality_reconciliation import legacy

NOW = datetime(2026, 10, 6, 9, tzinfo=timezone.utc)


def packets(now=NOW):
    case = {**legacy(now), "case_id": "CASE-SYNTHETIC", "generation": 3,
            "evidence_digest": "c"*64, "status": "waiting_reassessment",
            "assigned_worker_id": None, "lease_until": None}
    proof = MortalityReconciliationPending(__import__("json").dumps(case), "a"*64, now).metadata()
    dep = {key: proof[key] for key in ("case_id", "generation", "evidence_digest", "evidence_refs_digest", "dependency_id")}
    dep.update(anchor_event_id="EVENT-PENDING", anchor_cycle_id="CYCLE-NATURAL")
    scope = {"contract": intake.CONTRACT, "mission_id": "CORE-SYNTHETIC", "mission_identity_digest": "b"*64,
             "owner_user_id": "42", "owner_binding": "a"*64, "producer_revision": "d"*40,
             "dependencies": [dep], "allowed_effects": list(intake._EFFECTS)}
    policy = {"policy_id": "POLICY-SYNTHETIC", "capability": intake.CAPABILITY, "scope": scope,
              "enabled": True, "authority_tier": "auto", "expires_at": (now+timedelta(hours=1)).isoformat(),
              "max_actions": 2, "max_cost": 0, "rollback_required": True, "deterministic_gate_required": True}
    event = {"event_id": dep["anchor_event_id"], "case_id": case["case_id"], "generation": 3,
             "occurred_at": now.isoformat(), "event_type": "delivery_suppressed",
             "event_payload": {"cycle_id": dep["anchor_cycle_id"], "delivery_confirmed": False,
                 "outcome_status": "herdmaster_owning_reconciliation_pending", "technical_dependency": proof}}
    cycle = {"cycle_id": dep["anchor_cycle_id"], "status": "completed", "started_at": now.isoformat(),
             "source_revision": "d"*40, "worker_id": "oom-sakkie-general-manager-v1",
             "trigger_identity": "oom-sakkie-morning-scheduler:general-manager"}
    return case, event, cycle, policy


@pytest.mark.parametrize("mode,policies", [("active", []), ("observe", [packets()[3]]), ("off", [packets()[3]]),
    ("active", [{"capability": "core.queue_continue", "enabled": True}])])
def test_default_and_generic_policy_never_open_connection(mode, policies):
    connect = Mock(side_effect=AssertionError("no DB"))
    result = intake.consume_manager_dependencies(mode=mode, policies=policies, connect_factory=connect)
    assert result["status"] == "manager_dependency_intake_disabled" and result["failures"] == 0
    connect.assert_not_called()


@pytest.mark.parametrize("mutation", ["effects", "unknown_key", "empty", "duplicate", "bool_generation", "bad_revision", "bad_refdigest"])
def test_scope_cannot_widen_or_omit_binding(mutation):
    scope = deepcopy(packets()[3]["scope"])
    if mutation == "effects": scope["allowed_effects"].append("mission_status_write")
    elif mutation == "unknown_key": scope["all_missions"] = True
    elif mutation == "empty": scope["dependencies"] = []
    elif mutation == "duplicate": scope["dependencies"] *= 2
    elif mutation == "bool_generation": scope["dependencies"][0]["generation"] = True
    elif mutation == "bad_revision": scope["producer_revision"] = "main"
    else: scope["dependencies"][0]["evidence_refs_digest"] = "unknown"
    with pytest.raises(intake.IntakeRefused): intake.validate_scope(scope)


@pytest.mark.parametrize("mutation", ["owner", "expired", "disabled", "budget", "tier", "scope"])
def test_authoritative_policy_snapshot_must_match_and_still_authorize(mutation):
    p = packets()[3]; current = deepcopy(p)
    if mutation == "owner": current["scope"]["owner_binding"] = "e"*64
    elif mutation == "expired": current["expires_at"] = (NOW-timedelta(seconds=1)).isoformat()
    elif mutation == "disabled": current["enabled"] = False
    elif mutation == "budget": current["max_actions"] = 0
    elif mutation == "tier": current["authority_tier"] = "charl_human"
    else: current["scope"]["dependencies"][0]["generation"] += 1
    with pytest.raises(intake.IntakeRefused): intake._policy_matches(current, p, NOW)


@pytest.mark.parametrize("mutation", ["generation", "refs", "lease", "expired_lease", "status", "false_flag", "untyped_false", "digest", "owner", "source", "trigger", "missing_cycle", "future", "wrong_family"])
def test_exact_source_proof_and_current_case_required(mutation):
    case, event, cycle, policy = packets(); scope=policy["scope"]; dep=scope["dependencies"][0]
    if mutation == "generation": case["generation"] += 1
    elif mutation == "refs": case["evidence_refs"].append("event:other")
    elif mutation in {"lease", "expired_lease"}: case["lease_until"] = (NOW+timedelta(seconds=1 if mutation=="lease" else -1)).isoformat()
    elif mutation == "status": case["status"] = "exception"
    elif mutation == "false_flag": event["event_payload"]["technical_dependency"]["core_acknowledged"] = True
    elif mutation == "untyped_false": event["event_payload"]["technical_dependency"]["core_acknowledged"] = 0
    elif mutation == "digest": event["event_payload"]["technical_dependency"]["evidence_digest"] = "f"*64
    elif mutation == "owner": event["event_payload"]["technical_dependency"]["owner_binding"] = "e"*64
    elif mutation == "source": cycle["source_revision"] = "e"*40
    elif mutation == "trigger": cycle["trigger_identity"] = "manual"
    elif mutation == "missing_cycle": cycle["status"] = "started"
    elif mutation == "future": event["occurred_at"] = (NOW+timedelta(seconds=1)).isoformat()
    else: case["dedupe_key"] = "herdmaster:purpose-review:new"
    with pytest.raises(intake.IntakeRefused): intake._dependency_matches(case,event,cycle,scope,dep,NOW)


def test_canonical_pending_receipt_is_accepted_without_upgrading_false_flags():
    case,event,cycle,p = packets(); before=deepcopy(event)
    got=intake._dependency_matches(case,event,cycle,p["scope"],p["scope"]["dependencies"][0],NOW)
    assert not got["core_acknowledged"] and not got["completion_proven"] and event==before


def test_replayed_packet_identity_excludes_recording_clock_and_no_pickup_claim():
    case,event,cycle,p=packets(); a=intake._packets(p,p["scope"],p["scope"]["dependencies"][0]); b=intake._packets(p,p["scope"],p["scope"]["dependencies"][0])
    assert intake.canonical_event_equal(a[2],b[2]) and a[0]==b[0]
    assert a[4]["finding_received"] and not any(a[4][k] for k in ("worker_selected","worker_picked_up","repair_verified"))


def test_existing_executive_hook_passes_mode_and_exact_context_without_changing_queue(monkeypatch):
    monkeypatch.setenv("CHARLIE_EXECUTIVE_MODE","active")
    p=packets()[3]; consume=Mock(return_value={"status":"checked","results":[],"failures":0})
    monkeypatch.setattr(executive,"consume_manager_dependencies",consume)
    monkeypatch.setattr(executive,"_load_executive_missions",lambda **kw:({"missions":[]},200))
    monkeypatch.setattr(executive,"load_executive_context",lambda **kw:({"policies":[p]},200))
    monkeypatch.setattr(executive,"build_executive_cycle",lambda *a,**kw:{"commands":[],"escalations":[]})
    result,status=executive.run_executive_cycle(database_url="synthetic")
    assert status==200 and result["manager_dependency_intake"]["status"]=="checked"
    assert consume.call_args.kwargs["policies"]==[p] and consume.call_args.kwargs["mode"]=="active"



def _actual_pickup_heartbeat_branch(result):
    # Execute the exact caller condition/body, without importing or invoking the
    # pickup runtime, preparing worktrees, writing heartbeat files or networking.
    import ast
    from pathlib import Path
    source=Path(__file__).parents[1]/"scripts/charlie_mission_pickup.py"
    tree=ast.parse(source.read_text(encoding="utf-8"))
    branches=[node for node in ast.walk(tree) if isinstance(node,ast.If)
              and "executive_disabled" in ast.dump(node.test)
              and "executive_cycle_complete" in ast.dump(node.test)]
    assert len(branches)==1
    captured=[]
    code=ast.fix_missing_locations(ast.Module(body=branches,type_ignores=[]))
    exec(compile(code,str(source),"exec"),{"executive":deepcopy(result),"checks":5,
        "write_runner_heartbeat":captured.append})
    return captured


@pytest.mark.parametrize("mode,failures,observed",[("active",1,True),("active",0,False),
    ("observe",0,False),("off",0,False)])
def test_actual_pickup_heartbeat_condition_records_intake_only_failure(monkeypatch,mode,failures,observed):
    monkeypatch.setenv("CHARLIE_EXECUTIVE_MODE",mode)
    component={"status":"manager_dependency_intake_checked","results":[],"failures":failures}
    consume=Mock(return_value=component)
    monkeypatch.setattr(executive,"consume_manager_dependencies",consume)
    monkeypatch.setattr(executive,"_load_executive_missions",lambda **kw:({"missions":[]},200))
    monkeypatch.setattr(executive,"load_executive_context",lambda **kw:({"policies":[]},200))
    monkeypatch.setattr(executive,"build_executive_cycle",lambda *a,**kw:{"commands":[],"escalations":[]})
    notify=Mock(side_effect=AssertionError("intake failure is not owner notification"))
    monkeypatch.setattr(executive,"queue_outbox",notify)
    result,status=executive.run_executive_cycle()
    heartbeat=_actual_pickup_heartbeat_branch(result)
    assert bool(heartbeat) is observed
    assert result["success"] is (not bool(failures))
    assert status==(503 if failures else 200)
    if failures:
        assert result["status"]=="executive_cycle_component_failed"
        assert heartbeat[0]["executive"]["manager_dependency_intake"]["failures"]==1
        assert heartbeat[0]["executive"]["results"]==[]
    if mode=="off": consume.assert_not_called()
    notify.assert_not_called()


def test_intake_component_failure_keeps_unrelated_successful_command_and_evidence(monkeypatch):
    monkeypatch.setenv("CHARLIE_EXECUTIVE_MODE","active")
    monkeypatch.setattr(executive,"consume_manager_dependencies",lambda **kw:{"failures":1,"results":[]})
    monkeypatch.setattr(executive,"_load_executive_missions",lambda **kw:({"missions":[]},200))
    monkeypatch.setattr(executive,"load_executive_context",lambda **kw:({"policies":[]},200))
    command={"action":"ensure_queue_progress","mission_id":"UNRELATED"}
    monkeypatch.setattr(executive,"build_executive_cycle",lambda *a,**kw:{"commands":[command],"escalations":[]})
    monkeypatch.setattr(executive,"record_control_command",lambda *a,**kw:({"created":True,"command_id":"CMD"},201))
    executed=Mock(return_value={"command":command,"status":"queue_progress_observed"})
    monkeypatch.setattr(executive,"_execute_command",executed)
    result,status=executive.run_executive_cycle()
    assert status==503 and result["success"] is False
    executed.assert_called_once()
    assert result["results"]==[{"command":command,"status":"queue_progress_observed"}]
    assert _actual_pickup_heartbeat_branch(result)[0]["executive"]["results"]==result["results"]
