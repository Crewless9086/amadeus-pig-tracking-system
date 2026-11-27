"""Owner-approved command mode through real coordinator/planner projections; no I/O."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_device_registry import get_device_contract
from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_execution_authority import inputs, NOW

ENV = {"ROOTLINE_TIMED_CONTROL_ENABLED": "true", "ROOTLINE_SONOFF_TRANSPORT": "home_assistant",
    "ROOTLINE_HOME_ASSISTANT_ACCEPTANCE_MODE": ca.MODE}


def route(device="100204e9bc", *, now=NOW, reported="OFF"):
    channels = [1] if device == "1002851416" else [1,2,3,4]
    value = {"contract_version": ca.ROUTE, "acceptance_mode": ca.MODE, "device_id": device,
        "command_route_ready": True, "route_checked_at": now.isoformat(), "retrieved_at": now.isoformat(),
        "current_outputs_authoritative": False, "provider_control_calls": 0,
        "reported_output_state": reported,
        "channels": [{"channel": c, "entity_id": f"switch.{device}_{c}", "output_state": "Unknown"} for c in channels]}
    value["response_digest"] = ca.digest(value)
    return value


def receipt(execution, state, *, at, attempt=1, controller=True):
    value = {"contract_version": ca.RECEIPT, "provider": "home_assistant", "accepted_unambiguous": True,
        "provider_command_attempted": True, "device_id": execution["device_id"], "channel": execution["channel"],
        "entity_id": f"switch.{execution['device_id']}_{execution['channel']}", "requested_state": state,
        "idempotency_key": execution["execution_id"]+(":ON" if state == "ON" else f":OFF:{attempt}"),
        "command_attempted_at": at.isoformat(), "accepted_at": at.isoformat()}
    if controller:
        value["controller_acceptance"] = {"version": "rootline_controller_command.v1", "accepted": True,
            "status": "controller_accepted", "availability": "online", "device_id": execution["device_id"],
            "channel": execution["channel"], "state": state, "attempt_id": value["idempotency_key"],
            "issued_at": at.isoformat(), "expires_at": (at+timedelta(seconds=30)).isoformat(),
            "responded_at": at.isoformat(), "response_digest": "a"*64}
    value["receipt_sha256"] = ca.digest(value)
    return value


def confirm_fixture(execution, *, at):
    """Explicit hypothetical native report; captured on-disk evidence stays unchanged."""
    from modules.telemetry.rootline_camp_confirmation import confirmation
    snap = route(execution["device_id"], now=at)
    row = next(row for row in snap["channels"] if row["channel"] == execution["channel"])
    row["entity_id"] = execution["command_on_receipt"]["entity_id"]
    row["controller_report"] = {"source":"home_assistant_mqtt_subscription", "entity_id":row["entity_id"],
        "topic":f"cube2ha/switch/{execution['device_id']}/toggle_{execution['channel']}/state",
        "reported_at":at.isoformat(), "state":"ON", "retain":False, "qos":0}
    native = {"device_id": execution["device_id"], "observer_qualified": True, "observer_epoch": "a"*32,
        "channels": [{"channel": execution["channel"], "entity_id": row["entity_id"], "output_state": "ON",
            "observation_fresh": True, "observed_at": at.isoformat(), "observation_source": "mdns"}]}
    native["response_digest"] = ca.digest(native)
    snap["controller_observation"] = native
    snap["response_digest"] = ca.digest({k:v for k,v in snap.items() if k != "response_digest"})
    proof = confirmation(execution, snap, now=at)
    assert proof is not None
    execution["controller_confirmation"] = proof
    return execution


class Store:
    def __init__(self):
        self.active = None; self.auxiliary = {}; self.rows = []; self.fail_terminal = False
    def __call__(self, action, body):
        if action == "dispatch_controller_off":
            execution = body["execution"]
            prefix = "auxiliary_" if execution.get("auxiliary_device_id") else ""
            previous = [row for row in self.rows if row.get("execution_id") == execution["execution_id"]
                and row.get("action") == f"record_{prefix}off_outcome"]
            accepted = next((row["outcome"] for row in previous if ca.controller_accepted(row.get("outcome"), execution, "OFF")), None)
            if accepted:
                return {"reused_outcome": accepted}
            attempt = len(previous)+1
            if attempt > 3:
                return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_retry_not_due"}
            result = body["dispatch"](attempt)
            self.rows.append({"execution_id": execution["execution_id"], "attempt": attempt,
                "action": f"record_{prefix}off_outcome", "outcome": result})
            return result
        if action == "dispatch_irrigation_off_edge":
            result = body["dispatch"]()
            self.rows.append({"execution_id":body["execution_id"], "attempt":body["attempt"], "action":"record_off_outcome", "outcome":result})
            return {"provider_command_attempted":True, "outcome":result}
        if action == "confirm_irrigation_controller":
            self("mark_active", body)
            return {"success": True, "created": True, "execution": deepcopy(body)}
        if action == "load_active": return deepcopy(self.active)
        if action == "load_active_auxiliary": return deepcopy(self.auxiliary.get(body))
        if action == "load_auxiliary_executions": return list(self.auxiliary.values())
        if action in {"load_off_attempts", "load_auxiliary_off_attempts"}:
            return [deepcopy(row) for row in self.rows if row.get("execution_id") == body and row["action"] in {
                "claim_off_attempt", "record_off_outcome", "claim_auxiliary_off_attempt", "record_auxiliary_off_outcome"}]
        if action.startswith("load_"): return None
        if action == "record_completed" and self.fail_terminal: raise RuntimeError("offline terminal failure")
        if action == "mark_auxiliary_active" and ca.injector_target_claim(body):
            body = ca.build_injector_target_active(body, body["command_on_receipt"], self.active,
                now=ca.moment(body["command_on_receipt"]["accepted_at"]))
            self.auxiliary[body["auxiliary_device_id"]] = deepcopy(body)
            self.rows.append({**deepcopy(body), "action": action})
            return {"success": True, "created": True, "execution": body}
        if action in {"dispatch_auxiliary_on_edge", "dispatch_irrigation_on_edge"}:
            self.rows.append({**{k:v for k,v in body.items() if k != "dispatch"},
                "action": "claim_auxiliary_dispatch" if action == "dispatch_auxiliary_on_edge" else action})
            return body["dispatch"]()
        if action == "dispatch_auxiliary_off_edge":
            result=body["dispatch"]()
            self.rows.append({"execution_id":body["execution_id"],"attempt":body["attempt"],"action":"record_auxiliary_off_outcome","outcome":result})
            return result
        if action in {"claim_before_on", "mark_active", "mark_stopping"}: self.active = deepcopy(body)
        if action in {"claim_auxiliary_before_on", "mark_auxiliary_active"}: self.auxiliary[body["auxiliary_device_id"]] = deepcopy(body)
        if action == "record_completed": self.active = None
        if action == "record_auxiliary_completed": self.auxiliary.pop(body["auxiliary_device_id"], None)
        if action.startswith("claim_") and any(row["action"] == action and row.get("execution_id") == body.get("execution_id") and row.get("attempt") == body.get("attempt") for row in self.rows):
            if action != "claim_notification" or any(row["action"] == action and row.get("execution_id") == body.get("execution_id") and row.get("notification_state") == body.get("notification_state") for row in self.rows):
                return {"success": True, "created": False}
        self.rows.append({**deepcopy(body), "action": action})
        return {"success": True, "created": True}


class Transport:
    def __init__(self, store, clock): self.store=store; self.clock=clock; self.calls=[]; self.uncertain_on=False; self.reject_off=False; self.controller_on=True
    def read_safety_configuration(self, *, device_id, channel):
        contract = next(get_device_contract(key) for key in ("A12345","B12345","C12345","E12345","FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1")
            if get_device_contract(key)["device_id"] == device_id and get_device_contract(key)["channel"] == channel)
        snap=route(device_id, now=self.clock())
        return {"device_id":device_id,"channel":channel,"zone_id":contract.get("zone_id",contract["identity"]),
            "command_route":snap,"scheduled_generation":contract["contract_sha256"],"response_digest":snap["response_digest"],
            "controller_safety_generation":contract["contract_sha256"],"observed_at":self.clock().isoformat(),"output_state":"Unknown"}
    def read_output_state(self, *, device_id, channel, **kwargs):
        snap = route(device_id,now=self.clock())
        active = self.store.active
        if active and active.get("command_on_receipt") and active.get("device_id") == device_id:
            at = ca.moment(active["command_on_receipt"]["command_attempted_at"]) + timedelta(microseconds=1)
            if at <= self.clock():
                row = next(row for row in snap["channels"] if row["channel"] == active["channel"])
                row["controller_report"] = {"source":"home_assistant_mqtt_subscription", "entity_id":row["entity_id"],
                    "topic":f"cube2ha/switch/{device_id}/toggle_{active['channel']}/state", "reported_at":at.isoformat(),
                    "state":"ON", "retain":False, "qos":0}
                snap["response_digest"] = ca.digest({k:v for k,v in snap.items() if k != "response_digest"})
        return output_evidence_from_snapshot(snap,device_id=device_id,channel=channel)
    def set_state(self, *, device_id, channel, state, idempotency_key):
        self.calls.append((device_id,channel,state,idempotency_key))
        if self.uncertain_on and state == "ON" or self.reject_off and state == "OFF":
            return {"accepted_unambiguous":False,"provider_command_attempted":True,"status":"provider_outcome_ambiguous"}
        execution = next(row for row in reversed(self.store.rows) if row.get("execution_id") == idempotency_key.split(":")[0] and row.get("claimed_at"))
        return receipt(execution,state,at=self.clock(),attempt=int(idempotency_key.rsplit(":",1)[1]) if state=="OFF" else 1,
            controller=state == "OFF" or self.controller_on)


def start(zone="B12345", *, uncertain=False, at=NOW, confirm=True):
    plan,evidence,_ = inputs(zone=zone)
    selected=at.astimezone(timezone(timedelta(hours=2))).date().isoformat()
    plan["operating_date"]=selected
    evidence["weather"]["observed_at"]=at.isoformat(); evidence["tanks"]["observed_at"]=at.isoformat()
    evidence["irrigation"].update(advisor_generated_at=at.isoformat(),advisor_operating_date=selected)
    clock=[at]; store=Store(); transport=Transport(store,lambda:clock[0]); transport.uncertain_on=uncertain
    transport.controller_on = confirm
    with timed_control_scope(ENV):
        artifact=build_execution_eligibility(plan=plan,evidence=evidence,controller=route(now=at),now=at)
        assert artifact["eligible"],artifact
        output,_,identity=runtime._commissioned_output(zone,stop_mode="scheduled")
        packet=runtime._timed_mapping_packet(output,identity)
        decision={"decision_id":"OFFLINE-COMMAND", "decision":"Run now", "standing_authority":True,
            "zone_id":zone, "runtime_minutes":120, "runtime_seconds":7200,"execution_id":artifact["execution_id"],
            "eligibility_id":artifact["eligibility_id"],"evidence_generation":artifact["plan_generation"],
            "assessed_at":at.isoformat(),"commissioning_id":identity,"commissioning_generation":1,"execution_eligibility":artifact}
        decision["decision_sha256"]=coordinator._digest(decision)
        result=coordinator.advance_irrigation_execution(decision_id=decision["decision_id"],commissioning_id=identity,
            decision_reader=lambda _:decision,commissioning_reader=lambda _:packet,store=store,transport=transport,
            notify=lambda *args:{},eligibility_revalidator=lambda _:artifact,now=at,clock=lambda:clock[0])
    if confirm and store.active and store.active.get("state") == "Active":
        clock[0] += timedelta(microseconds=1)
        recover(store, transport, clock)
    return result, artifact, store, transport, clock


def recover(store,transport,clock):
    return coordinator.advance_irrigation_execution(decision_id="",commissioning_id="",decision_reader=lambda _:None,
        commissioning_reader=lambda _:None,store=store,transport=transport,notify=lambda *args:{},now=clock[0],
        clock=lambda:clock[0],active_only=True)


@pytest.mark.parametrize("zone",["A12345","B12345","C12345","E12345"])
def test_start_restart_and_disabled_mode_shutdown_preserve_truth(zone):
    result,artifact,store,transport,clock=start(zone)
    assert result["status"] == "irrigation_on_command_accepted",result
    active=deepcopy(store.active)
    assert ca.active_command(active,now=clock[0])
    clock[0]+=timedelta(seconds=100)
    assert recover(store,transport,clock)["status"]=="irrigation_command_duty_active"
    clock[0]=NOW+timedelta(seconds=7201)
    with timed_control_scope({}): done=recover(store,transport,clock)
    assert done["status"]=="irrigation_off_command_accepted",done
    terminal=done["execution"]
    assert ca.job_completed(terminal) and ca.terminal_matches_rows(terminal,store.rows)
    assert terminal["shutdown_verified"] is False and terminal["verified_runtime_seconds"]==0
    assert terminal["objective_satisfied"] is False
    assert [row[2] for row in transport.calls]==["ON","OFF"]
    assert recover(store,transport,clock)["hardware_commands"]==0


def test_uncertain_on_is_consumed_and_off_closes_without_completion():
    result,artifact,store,transport,clock=start(uncertain=True)
    assert result["status"]=="irrigation_off_command_accepted",result
    assert not ca.job_completed(result["execution"])
    assert result["execution"]["commanded_runtime_seconds"]==0
    assert [row[2] for row in transport.calls]==["ON","OFF"]


def test_persistence_restart_reuses_canonical_off_receipt():
    result,artifact,store,transport,clock=start()
    clock[0]+=timedelta(seconds=7201);store.fail_terminal=True
    with pytest.raises(RuntimeError):recover(store,transport,clock)
    store.fail_terminal=False
    done=recover(store,transport,clock)
    assert done["status"]=="irrigation_off_command_accepted"
    assert [row[2] for row in transport.calls]==["ON","OFF"]


def test_bounded_off_failure_does_not_close_duty():
    _,_,store,transport,clock=start(); transport.reject_off=True; clock[0]+=timedelta(seconds=7201)
    done=recover(store,transport,clock)
    assert done["status"]=="irrigation_off_command_unknown"
    assert [row[2] for row in transport.calls]==["ON","OFF","OFF","OFF"]
    recover(store,transport,clock)
    assert len(transport.calls)==4


def test_command_context_never_asserts_verified_output():
    _,_,store,transport,clock=start();clock[0]+=timedelta(seconds=600)
    from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
    from modules.telemetry.rootline_auxiliary_management import _injection_gate
    context=_active_irrigation_context(store.active,[],True,"BATCH",now=clock[0])
    assert context and context["zone_start_evidence"]["authoritative"] is False
    context.update(premix_command_accepted=True,fertilizer_history_complete_through=clock[0].isoformat())
    context["zone_output_evidence"]=transport.read_output_state(device_id="100204e9bc",channel=1)
    with timed_control_scope(ENV):
        assert _injection_gate(context,clock[0]) is None
        assert _injection_gate({**context,"premix_command_accepted":False},clock[0])=="current_batch_premix_unproven"
        assert _injection_gate({**context,"zone_output_evidence":{}},clock[0])=="active_parent_command_unproven"


def test_injector_actual_start_pulses_postflow_and_premix():
    from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
    from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility, fertilizer_control_progress
    _,_,store,transport,clock=start()
    for index,seconds in enumerate((600,1320,4200,4920),1):
        clock[0]=NOW+timedelta(seconds=seconds)
        context=_active_irrigation_context(store.active,store.rows,True,"BATCH",now=clock[0])
        context.update(premix_command_accepted=True,fertilizer_history_complete_through=clock[0].isoformat())
        context["zone_output_evidence"]=transport.read_output_state(device_id="100204e9bc",channel=1)
        with timed_control_scope(ENV):
            artifact=build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
                safety=transport.read_safety_configuration(device_id="100204d497",channel=1),context=context,
                flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=clock[0])
            assert artifact["eligible"],artifact
            assert artifact["pulse_number"]==index
            result=coordinator.advance_auxiliary_execution(eligibility=artifact,store=store,transport=transport,
                revalidate=lambda _:context,now=clock[0],clock=lambda:clock[0])
            assert result["status"]=="auxiliary_on_command_accepted",result
        clock[0]+=timedelta(seconds=120)
        result=coordinator.advance_auxiliary_execution(eligibility=None,store=store,transport=transport,
            now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        assert result["status"]=="auxiliary_off_command_accepted",result
        assert ca.terminal_matches_rows(result["execution"],store.rows)
        assert result["execution"]["shutdown_verified"] is False
    clock[0]+=timedelta(seconds=600)
    context=_active_irrigation_context(store.active,store.rows,True,"BATCH",now=clock[0])
    context["zone_output_evidence"]=transport.read_output_state(device_id="100204e9bc",channel=1)
    with timed_control_scope(ENV):
        progress=fertilizer_control_progress(context,now=clock[0])
    assert progress["completed"] and progress["status"]=="command_sequence_completed",progress
    assert progress["physical_flow_verified"] is False
    assert [row[2] for row in transport.calls]==["ON"]+["ON","OFF"]*4


def test_command_completion_is_not_partial_parent_or_physical_credit():
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment, IrrigationJobError
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event, project_canonical_irrigation_history
    from modules.telemetry.rootline_adaptive_irrigation import project_weekly_delivery_obligation
    _,artifact,store,transport,clock=start();clock[0]+=timedelta(seconds=7200)
    done=recover(store,transport,clock)["execution"]
    job=build_irrigation_job(zone_id="B12345",operating_date=done["operating_date"],requested_total_seconds=7200,
        maximum_segment_seconds=7200,plan_identity=artifact["plan_generation"],stop_mode="scheduled")
    assert project_next_segment(job,store.rows)["status"]=="command_job_completed"
    tampered={**done,"action":"record_completed","expected_segment_count":2}
    with pytest.raises(IrrigationJobError):project_next_segment(job,[tampered])
    early=ca.terminal(done,receipt(done,"OFF",at=NOW+timedelta(seconds=100)),now=clock[0],reason="primary_deadline_reached")
    early.update(command_program_completed=True,command_job_completed=True)
    assert ca.job_completed(early) is False
    event={"state":"Completed","completed_at":clock[0].isoformat(),"outcome_id":done["execution_id"],
        "operating_date":done["operating_date"],"source":"canonical","command_job_completed":True,
        "command_execution":done,"shutdown_verified":False,"objective_satisfied":False,"verified_runtime_minutes":0}
    obligation=project_weekly_delivery_obligation({"planning_epoch_start":(NOW-timedelta(days=6)).isoformat(),
        "completion_ledger_complete_through":clock[0].isoformat(),"completion_events":[event]},now=clock[0])
    assert obligation["completed_days"]==1 and obligation["verified_runtime_minutes"]==0,obligation
    assert obligation["command_outcome_ids"]==[done["execution_id"]]


def test_early_auxiliary_off_restart_never_creates_premix():
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    original={"execution_id":"MIX-EARLY","acceptance_mode":ca.MODE,"device_id":"100204d497","channel":2,
        "device_type":"fertilizer_mixer","auxiliary_device_id":"FERTILIZER-MIXER-CH2","batch_generation":"BATCH",
        "claimed_at":NOW.isoformat(),"primary_stop_deadline":(NOW+timedelta(seconds=600)).isoformat(),
        "maximum_duration_seconds":600,"state":"Active","on_attempts":1}
    original["command_on_receipt"]=receipt(original,"ON",at=NOW)
    off=receipt(original,"OFF",at=NOW+timedelta(seconds=100))
    terminal=ca.terminal(original,off,now=NOW+timedelta(seconds=700),reason="primary_deadline_reached")
    terminal.update(command_program_completed=True,command_accounted_mixing_seconds=600)
    rows=[{**original,"action":"claim_auxiliary_before_on"},
        {**original,"action":"record_auxiliary_on_outcome","on_outcome":original["command_on_receipt"]},
        {"execution_id":original["execution_id"],"action":"record_auxiliary_off_outcome","outcome":off},
        {**terminal,"action":"record_auxiliary_completed"}]
    result=mixing_daily_accounting(rows,now=NOW+timedelta(seconds=701),batch={"batch_generation":"BATCH","mixed_after":NOW.isoformat()})
    assert result["reserved_seconds"]==600 and result["controller_completed_seconds"]==0
    assert result["premix_command_accepted"] is False and result["premix_verified"] is False


@pytest.mark.parametrize("cutoff,expected",[(NOW.isoformat(),True),((NOW-timedelta(minutes=31)).isoformat(),False),
    ((NOW+timedelta(seconds=1)).isoformat(),False),(None,False),("invalid",False)])
def test_saved_program_reporting_uses_bounded_live_cutoff(cutoff,expected):
    from modules.telemetry.rootline_specialist_result import project_water_energy_plan
    from modules.oom_sakkie.rootline_daily_presentation import _fresh_result
    created=(NOW-timedelta(hours=2)).isoformat()
    plan={"success":True,"operating_date":NOW.date().isoformat(),"evidence_generation":"PLAN", "evidence_observed_at":created,
        "daily_program":{"version":"rootline_saved_daily_program.v1"},"live_evidence_cutoff":cutoff,"candidate_tasks":[]}
    result=project_water_energy_plan(plan,now=NOW)
    assert _fresh_result(result,NOW) is expected
    assert result["plan_creation_evidence_cutoff"]==created


def test_supervisor_and_notifications_accept_commands_without_switch_claims():
    from modules.oom_sakkie.rootline_transition_notifications import transition,compose_transition_notice
    _,_,store,transport,clock=start()
    active={**store.active,"event_id":"canonical-start","action":"mark_active"}
    current=runtime.supervise_rootline_active_execution(notify=lambda *a:{},environ=ENV,
        now=NOW,owner_user_id="owner",chat_id="owner",store=store,transport=transport,clock=lambda:clock[0])
    assert current["success"] and current["status"]=="irrigation_command_duty_active",current
    state,payload=transition(active)
    assert state=="Started" and payload["physical_state"]=="Unverified"
    from modules.oom_sakkie.telegram_gateway import _rootline_irrigation_start_summary
    assert "ON command accepted" in _rootline_irrigation_start_summary("B",active)
    clock[0]+=timedelta(seconds=7200)
    done=recover(store,transport,clock)["execution"]
    state,payload=transition({**done,"action":"record_completed","event_id":"canonical-off"})
    assert state=="Completed"
    from modules.oom_sakkie.telegram_gateway import _rootline_irrigation_completion_summary
    assert "command programme completed" in _rootline_irrigation_completion_summary("B",done)
    assert "OFF verified" not in _rootline_irrigation_completion_summary("B",done)


def completed_command_mix_rows(identity, claimed, recorded, batch_generation):
    original={"execution_id":identity,"acceptance_mode":ca.MODE,"device_id":"100204d497","channel":2,
        "device_type":"fertilizer_mixer","auxiliary_device_id":"FERTILIZER-MIXER-CH2",
        "batch_generation":batch_generation,"claimed_at":claimed.isoformat(),
        "primary_stop_deadline":(claimed+timedelta(seconds=600)).isoformat(),
        "maximum_duration_seconds":600,"state":"Active","on_attempts":1}
    original["command_on_receipt"]=receipt(original,"ON",at=claimed)
    off=receipt(original,"OFF",at=claimed+timedelta(seconds=600))
    terminal=ca.terminal(original,off,now=recorded,reason="primary_deadline_reached")
    terminal.update(command_program_completed=True,command_accounted_mixing_seconds=600)
    rows=[{**original,"action":"claim_auxiliary_before_on"},
        {**original,"action":"record_auxiliary_on_outcome","on_outcome":original["command_on_receipt"]},
        {"execution_id":identity,"action":"record_auxiliary_off_outcome","outcome":off},
        {**terminal,"action":"record_auxiliary_completed"}]
    assert ca.program_completed(terminal) and ca.terminal_matches_rows(terminal,rows)
    return rows


def test_full_mix_delayed_terminal_does_not_cross_same_batch_refill():
    from modules.telemetry.rootline_auxiliary_management import build_fertilizer_batch_lifecycle, mixing_daily_accounting
    observed=[{"event_type":"fertilizer_batch_prepared","observed_at":(NOW-timedelta(hours=1)).isoformat()}]
    check=NOW+timedelta(seconds=901)
    before=build_fertilizer_batch_lifecycle(observations=observed,now=check)
    after=build_fertilizer_batch_lifecycle(observations=observed+[
        {"event_type":"water_only_refill","observed_at":(NOW+timedelta(seconds=800)).isoformat()}],now=check)
    assert before["batch_generation"]==after["batch_generation"]
    rows=completed_command_mix_rows("MIX-REFILL",NOW,NOW+timedelta(seconds=900),before["batch_generation"])
    assert mixing_daily_accounting(rows,now=check,batch=before)["premix_command_accepted"] is True
    result=mixing_daily_accounting(rows,now=check,batch=after)
    assert result["premix_command_accepted"] is False and result["premix_verified"] is False
    assert result["reserved_seconds"]==600 and result["controller_completed_seconds"]==0


@pytest.mark.parametrize("claimed_hour,claimed_minute,expected,seconds",[(21,49,False,0),(21,55,True,300)])
def test_command_premix_original_off_day_boundary(claimed_hour,claimed_minute,expected,seconds):
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    claimed=NOW.replace(hour=claimed_hour,minute=claimed_minute,second=0)
    recorded=NOW.replace(hour=22,minute=15,second=0)  # 00:15 SAST on the following day.
    rows=completed_command_mix_rows("MIX-MIDNIGHT",claimed,recorded,"BATCH")
    result=mixing_daily_accounting(rows,now=recorded+timedelta(seconds=1),
        batch={"batch_generation":"BATCH","mixed_after":NOW.isoformat()})
    assert result["premix_command_accepted"] is expected
    assert result["reserved_seconds"]==seconds and result["controller_completed_seconds"]==0


def test_command_premix_latest_selection_uses_original_off_order():
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    older=completed_command_mix_rows("MIX-OLDER",NOW,NOW+timedelta(seconds=1900),"BATCH")
    newer=completed_command_mix_rows("MIX-NEWER",NOW+timedelta(seconds=700),NOW+timedelta(seconds=1400),"BATCH")
    for rows in (older+newer,newer+older):
        result=mixing_daily_accounting(rows,now=NOW+timedelta(seconds=2000),
            batch={"batch_generation":"BATCH","mixed_after":NOW.isoformat()})
        assert result["command_premix_execution"]["execution_id"]=="MIX-NEWER"
        assert result["reserved_seconds"]==1200 and result["premix_verified"] is False
