from datetime import datetime, timedelta, timezone
from unittest import mock

from modules.telemetry.rootline_execution_runtime import run_rootline_execution_cycle

NOW=datetime(2026,8,8,18,0,tzinfo=timezone.utc)


def plan():
    return {"evidence_generation":"PLAN-GEN-1","candidate_tasks":[{
        "task_id":"irrigation_B12345","zone_decision":"Run now","recommendation":"Recommend",
        "planned_duration_minutes":60,"rank":1,"weekly_obligation":{"status":"available",
            "delivery_debt_days":2,"remaining_weekly_obligation_days":4}}]}


def evidence(rain=0):
    return {"weather":{"observed_at":NOW.isoformat(),"rain_rate_mm_h":rain,"rain_today_mm":rain},
            "tanks":{"observed_at":NOW.isoformat(),"reservoir_state":"FULL","reservoir_fraction":1.0}}


def controller():
    return {"device_id":"100204e9bc","online":True,"firmware":"3.8.2",
        "actuation_configuration_safe":True,"timers_enabled":False,"scenes_enabled":False,
        "interlock_enabled":False,"provider_control_calls":0,"trusted_receipt_at":NOW.isoformat(),
        "commissioned_baseline_id":"ROOTLINE-EWELINK-BASELINE-1AB8753412B8851C4513D6CC",
        "response_digest":"READ-1","channels":[{"channel":n,"output_state":"OFF",
            "native_auto_off_enabled":True,"native_auto_off_seconds":3599,
            "power_restoration_state":"OFF"} for n in range(1,5)]}


class Store:
    def __init__(self): self.active=None; self.rows=[]; self.contained=set()
    def __call__(self,action,payload):
        if action=="load_active": return self.active
        if action=="load_zone_containment": return {"contained":payload in self.contained}
        if action=="load_off_attempts": return []
        if action=="claim_before_on":
            if any(name==action and row["execution_id"]==payload["execution_id"] for name,row in self.rows):
                return {"created":False,"success":True}
            self.active=payload; self.rows.append((action,payload)); return {"created":True,"success":True}
        self.rows.append((action,payload))
        if action=="mark_active": self.active=payload
        if action=="contain_zone": self.contained.add(payload["zone_id"])
        if action=="record_completed": self.active=None
        return {"created":True,"success":True}


class Transport:
    def __init__(self): self.calls=[]
    def read_safety_configuration(self,**kwargs):
        return {"authoritative":True,"zone_id":"B12345","channel":1,
            "native_inching_enabled":True,"native_inching_seconds":3599,
            "power_restoration_state":"OFF","schedules_enabled":False,
            "interlock_enabled":False,"scenes_enabled":False}
    def set_state(self,**kwargs): self.calls.append(kwargs); return {"accepted_unambiguous":True}
    def read_output_state(self,**kwargs): return {"authoritative":True,"state":"ON","evidence_id":"OUT-1"}


def run(store,transport,rain=0,notify=None,clock=lambda:NOW):
    loader=lambda **_kwargs:(evidence(rain),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.build_water_energy_plan",
                    return_value=plan()):
        return run_rootline_execution_cycle(notify=notify or (lambda *_:{"success":True,
            "provider_delivery_confirmed":True,"provider_message_id":"MSG-1"}),
            environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,store=store,
            token_store=object(),transport=transport,evidence_loader=loader,
            readback=lambda **_kwargs:controller(),clock=clock)


def test_rain_hold_creates_no_artifact_command_or_notification():
    store=Store(); transport=Transport(); notices=[]
    value=run(store,transport,rain=.25,notify=lambda *args:notices.append(args))
    assert value["status"]=="observed_weather_not_fresh_and_dry"
    assert transport.calls==[] and notices==[]
    assert not any(name=="record_eligibility" for name,_ in store.rows)


def test_dry_b_creates_artifact_and_exactly_one_coordinator_execution():
    store=Store(); transport=Transport()
    first=run(store,transport); replay=run(store,transport)
    assert first["status"]=="segment_started" and first["telegram_messages"]==1
    assert replay["status"]=="active_segment_owned"
    assert [call["state"] for call in transport.calls]==["ON"]
    artifacts=[row for name,row in store.rows if name=="record_eligibility"]
    assert len(artifacts)==1 and artifacts[0]["zone_id"]=="B12345"


def test_notification_ambiguity_is_quarantined_without_retry_or_false_count():
    store=Store(); transport=Transport(); attempts=[]
    first=run(store,transport,notify=lambda *args:(attempts.append(args) or {
        "success":False,"status":"family_message_delivery_ambiguous",
        "provider_delivery_ambiguous":True}))
    replay=run(store,transport,notify=lambda *args:attempts.append(args))
    assert first["notification"]["ambiguous"] is True and first["telegram_messages"]==0
    assert replay["status"]=="active_segment_owned" and len(attempts)==1


def test_disabled_flag_is_zero_effect():
    store=Store(); transport=Transport()
    value=run_rootline_execution_cycle(notify=lambda *_:None,
        environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"false"},now=NOW,
        store=store,token_store=object(),transport=transport)
    assert value["status"]=="autonomous_bc_disabled" and store.rows==[] and transport.calls==[]


def test_expired_artifact_at_real_preclaim_time_creates_no_on():
    store=Store(); transport=Transport()
    later=NOW+timedelta(minutes=16)
    value=run(store,transport,clock=lambda:later)
    assert value["status"]=="execution_eligibility_changed"
    assert transport.calls==[]
