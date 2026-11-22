"""Real scheduled gateway and family pre-attempt rail under the 140s request budget."""
from copy import deepcopy
from datetime import timedelta
import time
from functools import partial
import pytest
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from tests.test_rootline_active_supervision import NOW,ENV,HEADERS,payload,current,ScheduleStore,reports
from tests.test_oom_sakkie_rootline_reassessment_delivery import memory_store

@pytest.fixture
def timed_gateway(monkeypatch,reports):
    costs={"state":3,"evidence":20,"safety":10,"ambiguous":False};clock=[0.0];trace=[];events={};sends=[];schedules=ScheduleStore();states,state_store=memory_store()
    monkeypatch.setattr(time,"monotonic",lambda:clock[0])
    def spend(label,seconds):clock[0]+=seconds;trace.append((label,clock[0]))
    def state(action,identity,body):
        spend("state:"+action,costs["state"])
        return state_store(action,identity,body)
    def event_store(action,identity,body):
        if action=="load":
            spend("family_load",4)
            return [v for v in events.values() if v.get("card_mission_id")==identity]
        trace.append(("family:"+body["state"],clock[0]))
        created=identity not in events
        if created:events[identity]=deepcopy(body)
        return {"success":True,"created":created}
    def sender(*args,**kwargs):
        trace.append(("send",clock[0]));sends.append(args)
        assert kwargs["deadline_monotonic"]-clock[0]>=30
        return ({"success":False,"status":"synthetic_ambiguous"} if costs["ambiguous"] else {"success":True,"telegram_message_id":str(8000+len(sends))})
    delivery=partial(deliver_family_result,event_store=event_store,sender=sender)
    monkeypatch.setattr("modules.oom_sakkie.automatic_reassessment_store.automatic_reassessment_store",schedules)
    def program(**kwargs):spend("due_program",5);return {"success":True,"status":"ready"},200
    monkeypatch.setattr("modules.telemetry.rootline_water_energy_plan.ensure_due_daily_program",program)
    def unavailable(**kwargs):raise RuntimeError("synthetic unrelated reporting unavailable")
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_read",unavailable)
    def safety(**kwargs):spend("mandatory_off",costs["safety"]);return {"success":True,"status":"no_active_irrigation","active_execution_found":False}
    def control(**kwargs):spend("control",30);return {"success":True,"status":"planner_hold_or_no_dispatchable_zone","hardware_commands":0,"writes_farm_data":False}
    def managed(**kwargs):kwargs["after_safety"]({});return {"success":True,"status":"managed_safe"}
    def loader():spend("current_evidence",costs["evidence"]);return current()
    def receipt(_):return {"success":True,"status":"canonical_rootline_plan_bound","readback_bound":True,
        "daily_plan":{"daily_plan_id":"P","operating_date":NOW.date().isoformat(),"generation":"G","evidence_sha256":"a"*64}}
    pending=[True]
    def provider(**kwargs):spend("provider_scan",10);return {"success":True,"status":"provider_unchanged"}
    def inputs(**kwargs):
        spend("input_scan",15)
        if not pending[0]:return {"success":True,"status":"input_unchanged"}
        result=kwargs["notify"]("InputRestored",{"notification_identity":"SYNTHETIC-INPUT-RESTORED","kind":"weather","recovery":{"observed_at":NOW.isoformat()}})
        if result.get("provider_delivery_confirmed"):pending[0]=False
        return {**result,"status":"input_restored" if not pending[0] else "input_pending"}
    def run(minute=0):
        clock[0]=0
        return handle_rootline_reassessment_trigger(payload(trigger_id="CYCLE-"+str(minute),due_at=(NOW+timedelta(minutes=minute)).isoformat(),trigger_timestamp=(NOW+timedelta(minutes=minute)).isoformat()),HEADERS,
            {**ENV,"ROOTLINE_INPUT_HEALTH_ENABLED":"true"},specialist_loader=loader,state_store=state,
            scheduler_now=NOW+timedelta(minutes=minute),family_delivery=delivery,
            active_supervision_cycle=safety,execution_cycle=control,managed_device_cycle=managed,
            daily_plan_generator=receipt,provider_notification_cycle=provider,input_notification_cycle=inputs,
            equipment_notification_cycle=lambda **k:{"success":True,"status":"none"})
    return run,trace,events,sends,states,schedules,pending,costs

def test_current_plan_reaches_real_family_attempt_before_optional_scans(timed_gateway):
    run,trace,events,sends,states,schedules,pending,costs=timed_gateway
    result,_=run()
    assert result["plan_delivery_status"]=="delivered_current_irrigation_plan",(result,trace)
    assert result["plan_delivery_recorded"] is True
    assert any(row.get("delivery_state")=="delivered" for row in states.values())
    attempt=next(t for name,t in trace if name=="family:delivery_attempted")
    assert attempt<=110
    assert next(i for i,(name,_) in enumerate(trace) if name=="send") < next(i for i,(name,_) in enumerate(trace) if name=="provider_scan")
    assert trace[0][0]=="mandatory_off"

def test_stable_next_cycle_drains_retained_input_notice_without_duplicate_plan(timed_gateway):
    run,trace,events,sends,states,schedules,pending,costs=timed_gateway
    first,_=run();assert first["plan_delivery_recorded"] is True
    assert pending[0] is True
    second,_=run(1)
    assert second["plan_delivery_status"]=="current_irrigation_plan_unchanged"
    assert pending[0] is False
    assert len(sends)==2
    assert len([r for r in events.values() if r.get("state")=="delivery_attempted"])==2


def test_real_family_deadline_refusal_is_preserved_in_schedule_without_attempt(timed_gateway):
    run,trace,events,sends,states,schedules,pending,costs=timed_gateway
    costs["state"]=7
    result,_=run()
    assert result["plan_delivery_underlying_status"]=="family_message_cycle_deadline_deferred"
    outcomes=[row for key,row in schedules.rows.items() if key.endswith(":outcome")]
    assert outcomes[-1]["plan_delivery_underlying_status"]=="family_message_cycle_deadline_deferred"
    assert not any(row.get("task_state")=="rootline_reassessment_changed" for row in events.values())
    assert not sends


def test_plan_evidence_budget_exhaustion_never_relabels_old_plan_fresh(timed_gateway):
    run,trace,events,sends,states,schedules,pending,costs=timed_gateway
    costs["evidence"]=41
    result,_=run()
    assert result["daily_plan_error_type"]=="RootlineCycleDeadlineExceeded"
    assert result["plan_delivery_status"]=="current_irrigation_plan_delivery_unconfirmed"
    assert not any(row.get("delivery_state")=="delivered" for row in states.values())
    assert trace[0][0]=="mandatory_off"


def test_ambiguous_provider_attempt_is_not_repeated_next_cycle(timed_gateway):
    run,trace,events,sends,states,schedules,pending,costs=timed_gateway
    costs["ambiguous"]=True
    result,_=run()
    assert result["plan_delivery_underlying_status"]=="family_message_delivery_contained"
    assert len(sends)==1
    # A later unrelated input notice can send, but the uncertain plan cannot.
    second,_=run(1)
    attempts=[row for row in events.values() if row.get("state")=="delivery_attempted" and row.get("task_state")=="rootline_reassessment_changed"]
    assert len(attempts)==1
    assert second["plan_delivery_status"]=="current_irrigation_plan_delivery_unconfirmed"


def test_expired_reporting_budget_does_not_skip_mandatory_safety(timed_gateway):
    run,trace,events,sends,states,schedules,pending,costs=timed_gateway
    costs["safety"]=141
    result,_=run()
    assert trace[0]==("mandatory_off",141)
    assert result["active_supervision_status"]=="no_active_irrigation"
    assert result["status"]=="scheduled_rootline_reporting_deadline_deferred"
    assert not sends
