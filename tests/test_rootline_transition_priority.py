"""Actual gateway reporting order preserves control and canonical family reserve."""
import pytest
from tests.test_rootline_active_supervision import reports, gateway, ExecutionStore, Transport, ScheduleStore, active, current, ENV
from tests.test_rootline_parent_deadline import clocks
from tests.test_rootline_notice47_delivery import Rail
from modules.oom_sakkie import family_message_lifecycle as family

@pytest.mark.parametrize("later_failure", [False, True])
def test_transition_precedes_expensive_reports_after_control(monkeypatch, reports, later_failure):
    wall, mono, advance = clocks(monkeypatch)
    trace=[]; rail=Rail(mono); sends=[]; notices=[]; schedules=ScheduleStore()
    def supervisor(**kwargs):
        trace.append("safety")
        return {"success":True,"status":"no_active_irrigation","active_execution_found":False,"hardware_commands":0}
    def admission(**kwargs):
        trace.append("irrigation")
        return {"success":True,"status":"planner_hold_or_no_dispatchable_zone","hardware_commands":0,"writes_farm_data":False}
    def managed(**kwargs):
        kwargs["after_safety"]({"success":True,"blocks_bc":False})
        trace.append("managed_admission");advance(60)
        return {"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0}
    def event_store(action, identity, payload):
        if action=="load":
            return [row for row in rail.rows.values() if row.get("card_mission_id")==identity]
        return rail.store(action,identity,payload)
    def delivery(*args,**kwargs):
        return family.deliver_family_result(*args,**kwargs,event_store=event_store,
            sender=lambda *a,**kw: sends.append(mono[0]) or {"success":True,"telegram_message_id":"priority-message"})
    def equipment(**kwargs):
        trace.append("transition")
        notices.append(kwargs["notify"]("Started",active(due=False)))
        return {"success":True,"status":"rootline_transition_notifications_observed","telegram_sends":notices[-1].get("telegram_sends",0)}
    def loader():
        trace.append("plan");advance(17)
        return current()
    def provider(**kwargs):
        trace.append("provider");advance(12)
        return {"success":True,"status":"observed","telegram_sends":0}
    def inputs(**kwargs):
        trace.append("input");advance(10)
        if later_failure:raise RuntimeError("synthetic later scan failure")
        return {"success":True,"status":"observed","telegram_sends":0}
    result,_,_,_=gateway(ExecutionStore(None),Transport(),schedules=schedules,
        source_env={**ENV,"ROOTLINE_INPUT_HEALTH_ENABLED":"true"},
        active_supervision_cycle=supervisor,execution_cycle=admission,
        managed_device_cycle=managed,equipment_notification_cycle=equipment,
        specialist_loader=loader,provider_notification_cycle=provider,
        input_notification_cycle=inputs,family_delivery=delivery)
    assert trace.index("safety")<trace.index("irrigation")<trace.index("managed_admission")<trace.index("transition")
    assert trace.index("transition")<trace.index("plan")<trace.index("provider")<trace.index("input")
    assert trace.count("transition")==1
    assert notices[0]["provider_delivery_confirmed"] is True
    assert sends[0]==1060 and len([r for r in rail.rows.values() if r.get("state")=="delivered"])>=1
    outcome=next(v for k,v in schedules.rows.items() if k.endswith(":outcome"))
    assert result["telegram_sends"]==len(sends)==outcome["telegram_sends"]
    # Former position after these scans has39seconds: existing40second gate refuses.
    later=Rail(mono);mono[0]=1101
    from tests.test_rootline_notice47_delivery import call
    refused=call(later,deadline_monotonic=1140,sender=lambda *a,**k:pytest.fail("reserve unchanged"))
    assert refused["status"]=="family_message_cycle_deadline_deferred" and not later.rows


def test_failed_transition_turn_not_reentered_by_late_reports(monkeypatch,reports):
    calls=[]
    def equipment(**kwargs):
        calls.append(1);raise RuntimeError("private failure detail")
    result,_,_,_=gateway(ExecutionStore(active()),Transport(),equipment_notification_cycle=equipment)
    assert calls==[1]
    assert result["equipment_notification_status"]=="rootline_transition_notifications_unavailable"
    assert result["hardware_commands"]==1
    assert "private failure detail" not in str(result.get("equipment_notification_failure"))


def test_parent_budget_still_prevents_early_transition_claim(monkeypatch,reports):
    from tests.test_rootline_parent_deadline import test_actual_family_reserve_uses_parent_notification_deadline
    test_actual_family_reserve_uses_parent_notification_deadline(monkeypatch,reports)
