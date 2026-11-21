"""Scheduled ROOTLINE regressions through existing planning, claim and stop rails.

All provider calls and database effects use deterministic offline fixtures.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,os

def test_irrigation_stop_and_restart():
    from modules.telemetry import rootline_irrigation_coordinator as c
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_irrigation_execution_store as store_module
    from modules.telemetry.rootline_timed_control import timed_control_scope
    from modules.telemetry.rootline_execution_authority import build_execution_eligibility
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job, project_next_segment, validate_weather_stopped_execution
    from tests.test_rootline_execution_authority import inputs, NOW
    from tests.test_rootline_active_weather_stop import weather_packet

    class Store:
        def __init__(self, active=None): self.active=deepcopy(active); self.rows=[]; self.fail_terminal=False
        def __call__(self, action, body):
            if action == "load_active": return deepcopy(self.active)
            if action == "load_off_attempts": return [b for a,b in self.rows if a == "claim_off_attempt"]
            if action == "load_zone_containment": return {}
            if action.startswith("load_"): return None
            if action == "record_completed" and self.fail_terminal: raise RuntimeError("simulated crash after stop")
            self.rows.append((action,deepcopy(body)))
            if action in {"claim_before_on","mark_active","mark_stopping"}: self.active=deepcopy(body)
            if action == "record_completed": self.active=None
            return {"success":True,"created":True}

    class Transport:
        def __init__(self, clock, state="OFF"): self.clock=clock;self.state=state;self.calls=[];self.fail_read=False
        def set_state(self, **kwargs): self.calls.append(kwargs);self.state=kwargs["state"];return {"accepted_unambiguous":True}
        def read_safety_configuration(self, **kwargs):
            return {**kwargs,"zone_id":self.zone,"scheduled_authoritative":True,"output_state":self.state,
                "response_digest":"offline-snapshot","observed_at":self.clock().isoformat(),"relevant_outputs_off":True}
        def read_output_state(self, **kwargs):
            if self.fail_read: raise TimeoutError("offline missing observation")
            return {**kwargs,"authoritative":True,"state":self.state,"evidence_id":"offline-"+self.clock().isoformat(),"retrieved_at":self.clock().isoformat()}

    def notify(*a): return {"provider_delivery_confirmed":True}
    def start(zone="B12345"):
        plan,evidence,controller=inputs(zone=zone)
        controller.update(current_outputs_authoritative=True,actuation_configuration_safe=False,timers_enabled=True)
        for row in controller["channels"]: row.update(native_auto_off_enabled=False,native_auto_off_seconds=0)
        clock=[NOW]; transport=Transport(lambda:clock[0]);transport.zone=zone; store=Store()
        with timed_control_scope({"ROOTLINE_TIMED_CONTROL_ENABLED":"true"}):
            artifact=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
            assert artifact["eligible"],artifact
            output,baseline,identity=runtime._commissioned_output(zone,stop_mode="scheduled")
            packet=runtime._timed_mapping_packet(output,identity)
            decision={"decision_id":"OFFLINE-DECISION","decision":"Run now","standing_authority":True,
                "zone_id":zone,"runtime_minutes":120,"runtime_seconds":7200,"execution_id":artifact["execution_id"],
                "eligibility_id":artifact["eligibility_id"],"evidence_generation":artifact["plan_generation"],
                "assessed_at":NOW.isoformat(),"commissioning_id":identity,"commissioning_generation":1,"execution_eligibility":artifact}
            decision["decision_sha256"]=c._digest(decision)
            result=c.advance_irrigation_execution(decision_id=decision["decision_id"],commissioning_id=identity,
                decision_reader=lambda _:decision,commissioning_reader=lambda _:packet,store=store,transport=transport,
                notify=notify,eligibility_revalidator=lambda _:artifact,now=NOW,clock=lambda:clock[0])
            assert result["status"] == "segment_started",result
            claim=next(b for a,b in store.rows if a=="claim_before_on")
            assert store_module._scheduled_irrigation_claim_valid(claim,artifact,NOW)
            assert not store_module._scheduled_irrigation_claim_valid(dict(claim,stop_mode=None),artifact,NOW)
            assert not store_module._scheduled_irrigation_claim_valid(dict(claim,primary_stop_deadline=(NOW+timedelta(seconds=1)).isoformat()),artifact,NOW)
        return artifact,store,transport,clock

    def recover(store,transport,clock,weather=None):
        return c.advance_irrigation_execution(decision_id="",commissioning_id="",decision_reader=lambda _:None,
            commissioning_reader=lambda _:None,store=store,transport=transport,notify=notify,now=clock[0],
            clock=lambda:clock[0],active_only=True,active_weather_revalidator=weather)

    results=[]
    for zone in ("A12345","B12345","C12345","E12345"):
        artifact,store,transport,clock=start(zone)
        assert store.active["stop_mode"]=="scheduled" and store.active["native_fail_stop_deadline"] is None
        clock[0]=NOW+timedelta(seconds=100)
        missing=lambda active:runtime.assess_active_irrigation_weather({},now=clock[0],stop_mode=active["stop_mode"])
        assert recover(store,transport,clock,missing)["status"]=="active_segment_owned"
        deadline=store.active["primary_stop_deadline"]
        clock[0]=NOW+timedelta(seconds=7201)
        with timed_control_scope({"ROOTLINE_TIMED_CONTROL_ENABLED":"false"}): result=recover(store,transport,clock)
        assert result["status"]=="segment_completed",result
        assert result["execution"]["verified_runtime_seconds"]==7200
        assert result["execution"]["primary_stop_deadline"]==deadline
        assert [x["state"] for x in transport.calls]==["ON","OFF"]
        results.append(zone+": continuous7200, missing-read retained, disabled-flag due OFF and exact completion")

    artifact,store,transport,clock=start();clock[0]=NOW+timedelta(seconds=100);transport.state="OFF"
    result=recover(store,transport,clock)
    assert result["status"]=="segment_stopped_external_off",result
    assert validate_weather_stopped_execution(result["execution"])
    assert result["execution"]["verified_runtime_seconds"]==0 and len(transport.calls)==1
    results.append("external OFF closes without another command or planned-runtime credit")

    artifact,store,transport,clock=start();clock[0]=NOW+timedelta(seconds=100);transport.state="OFF";store.fail_terminal=True
    try: recover(store,transport,clock)
    except RuntimeError: pass
    else: raise AssertionError("crash not simulated")
    assert store.active["state"]=="stopping"
    store.fail_terminal=False;clock[0]+=timedelta(seconds=90)
    result=recover(store,transport,clock)
    assert result["status"]=="segment_stopped_external_off",result
    assert validate_weather_stopped_execution(result["execution"])
    assert result["execution"]["verified_runtime_seconds"]==0
    results.append("restart retains original external OFF cause and accepts later final OFF")

    artifact,store,transport,clock=start();clock[0]=NOW+timedelta(seconds=100)
    def rain(active):return runtime.assess_active_irrigation_weather(weather_packet(now=clock[0],rain=1),now=clock[0],stop_mode=active["stop_mode"])
    result=recover(store,transport,clock,rain)
    assert result["status"]=="segment_stopped_for_weather",result
    assert validate_weather_stopped_execution(result["execution"])
    assert result["execution"]["verified_runtime_seconds"]==0
    results.append("fresh rain still stops without full credit")

    plan,evidence,controller=inputs();controller["current_outputs_authoritative"]=True;controller["channels"][1]["output_state"]="ON"
    with timed_control_scope({"ROOTLINE_TIMED_CONTROL_ENABLED":"true"}):
        assert build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)["eligible"] is False
    results.append("external sibling ON blocks another irrigation start")
    assert store_module._same_parent({"stop_mode":"scheduled"},{"stop_mode":None}) is False
    results.append("immutable stop mode cannot be changed at terminal edge")
    artifact,store,transport,clock=start();clock[0]=NOW+timedelta(seconds=7199)
    def crossing(active): clock[0]=NOW+timedelta(seconds=7201);raise TimeoutError("crossed due deadline")
    result=recover(store,transport,clock,crossing)
    assert result["status"]=="segment_completed",result
    results.append("missing callback crossing deadline performs due OFF")

    artifact,store,transport,clock=start();clock[0]=NOW+timedelta(seconds=100);transport.state="OFF"
    original_store=store.__call__
    class RaceStore:
        def __call__(self,action,body):
            if action=="mark_stopping":
                when=clock[0]-timedelta(seconds=1)
                weather=runtime.assess_active_irrigation_weather(weather_packet(now=when,rain=1),now=when,stop_mode="scheduled")
                committed={**body,"weather_stop_evidence":weather,"stop_requested_at":when.isoformat(),"reason":weather["reason"]}
                store.active=committed
                return {"success":True,"created":False,"execution":committed}
            return original_store(action,body)
    result=recover(RaceStore(),transport,clock)
    assert result["status"]=="segment_stopped_for_weather",result
    assert result["execution"]["reason"]=="active_weather_rain_hold"
    assert validate_weather_stopped_execution(result["execution"])
    results.append("competing committed rain stop displaces stale local external OFF observation")

    artifact,store,transport,clock=start();clock[0]=NOW+timedelta(seconds=100);transport.state="OFF"
    result=recover(store,transport,clock)
    events=[dict(artifact,action="record_eligibility")]+[dict(body,action=action) for action,body in store.rows]
    resolution=store_module._weather_terminal_resolution(result["execution"],events)
    assert resolution["resolution"]=="Deferred" and resolution["remaining_seconds"]==7200
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event,project_canonical_irrigation_history
    when=NOW+timedelta(seconds=7201)
    event=build_typed_history_event(event_id="OFFLINE-TIMED-HISTORY",event_at=when,event_type="COMPLETED",zone_id="B12345",
        details={"execution_id":"OFFLINE","start_evidence_id":"ON","shutdown_evidence_id":"OFF",
            "maximum_runtime_minutes":120,"verified_runtime_minutes":120,"shutdown_verified":True,
            "objective_satisfied":True,"evidence_cutoff":when.isoformat(),"provenance":"rootline_execution_coordinator", "stop_mode":"scheduled"},
        planned_minutes=120,actual_minutes=120)
    history=project_canonical_irrigation_history([dict(event,event_at=when)],snapshot_cutoff=when)
    assert history["zones"]["B12345"]["verified_completed_days"]==["2026-08-08"],history
    results.append("v2 stop reconstructs original7200 job; signed120minute history qualifies")


def test_transport_binding_and_owned_off():
    import modules.telemetry.rootline_ifttt_transport as m
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty
    from modules.telemetry.rootline_device_registry import get_device_contract
    now=datetime.now(timezone.utc).isoformat()
    snapshot={"device_id":"100204e9bc","online":True,"current_outputs_authoritative":True,"provider_control_calls":0,"response_digest":"a"*64,"retrieved_at":now,"channels":[{"channel":i,"output_state":"OFF"} for i in range(1,5)]}
    t=m.RootlineIFTTTTransport(token_store=None,environ={"ROOTLINE_TIMED_CONTROL_ENABLED":"true","ROOTLINE_E_ENABLED":"true"})
    t._send_bound_state=lambda **kwargs:{"accepted_unambiguous":True}
    safety=t._safety_from_snapshot(get_device_contract("E12345"),snapshot,"100204e9bc",3)
    assert safety["scheduled_authoritative"] and not safety["authoritative"]
    snapshot["channels"][0]["output_state"]="ON"
    assert not t._safety_from_snapshot(get_device_contract("E12345"),snapshot,"100204e9bc",3)["scheduled_authoritative"]
    assert "irrigation_output_evidence" in m.output_evidence_from_snapshot(snapshot,device_id="100204e9bc",channel=3)
    duty={"stop_mode":"scheduled","execution_id":"owned","zone_id":"E12345","device_id":"100204e9bc","channel":3}
    with execution_duty(duty):
     assert t.set_state(device_id="100204e9bc",channel=3,state="OFF",idempotency_key="owned:OFF:1")["accepted_unambiguous"]
     assert not t.set_state(device_id="100204e9bc",channel=3,state="ON",idempotency_key="owned:ON")["accepted_unambiguous"]
     assert not t.set_state(device_id="100204e9bc",channel=4,state="OFF",idempotency_key="owned:OFF:1")["accepted_unambiguous"]
    duty.update(claimed_at=now,primary_stop_deadline=now)
    with execution_duty(duty):
     assert t.set_state(device_id="100204e9bc",channel=3,state="ON",idempotency_key="owned:ON")["accepted_unambiguous"]
     t.environ["ROOTLINE_TIMED_CONTROL_ENABLED"]="false"
     assert not t.set_state(device_id="100204e9bc",channel=3,state="ON",idempotency_key="owned:ON")["accepted_unambiguous"]
     assert t.set_state(device_id="100204e9bc",channel=3,state="OFF",idempotency_key="owned:OFF:1")["accepted_unambiguous"]


def test_auxiliary_hourly_phases_and_claim():
    from modules.telemetry import rootline_auxiliary_management as aux
    from modules.telemetry.rootline_irrigation_execution_store import _scheduled_auxiliary_claim_valid
    from modules.telemetry.rootline_timed_control import timed_control_scope
    from tests.test_rootline_fertilizer_auxiliary import injection_context,safety,NOW
    from tests.test_rootline_ifttt_transport import irrigation_output
    start=NOW-timedelta(seconds=600)
    with timed_control_scope({"ROOTLINE_TIMED_CONTROL_ENABLED":"true"}):
     for pulse,offset in [(0,600),(1,1320),(2,4200),(3,4920)]:
      at=start+timedelta(seconds=offset)
      context=injection_context(stop_mode="scheduled",planned_runtime_seconds=7200,completed_pulses=pulse,irrigation_stop_deadline=(start+timedelta(seconds=7200)).isoformat(),fertilizer_history_complete_through=at.isoformat(),zone_output_evidence={**irrigation_output(at),"zone_execution_id":"ZONE-EXEC-1","observed_at":at.isoformat(),"state":"ON"},prior_pulse_shutdown_evidence={"evidence_id":"PRIOR","zone_execution_id":"ZONE-EXEC-1","shutdown_verified":True,"observed_at":(at-timedelta(seconds=600)).isoformat()})
      config=safety(authoritative=False,scheduled_authoritative=True,scheduled_generation="mapped",native_inching_enabled=False,commissioned=False,physical_commissioning_generation=None,observed_at=at.isoformat())
      a=aux.build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},safety=config,context=context,flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=at)
      assert a["eligible"],a
      assert a["phase_number"]==pulse//2+1 and a["pulse_number"]==pulse+1
      assert aux.revalidate_auxiliary_execution_edge(a,current_context=context,current_safety=config,now=at)
      claim={**a,"claimed_at":at.isoformat(),"primary_stop_deadline":(at+timedelta(seconds=120)).isoformat()}
      assert _scheduled_auxiliary_claim_valid(claim,a,at)
      assert not _scheduled_auxiliary_claim_valid({**claim,"phase_number":99},a,at)
      if pulse==2:
       context["zone_start_evidence"]["observed_at"]=(start+timedelta(seconds=1)).isoformat()
       assert aux._injection_gate(context,at)=="clean_water_preflow_incomplete"
     at=start+timedelta(seconds=4200)
     skipped=injection_context(stop_mode="scheduled",planned_runtime_seconds=7200,completed_pulses=0,completed_pulse_numbers=[],irrigation_stop_deadline=(start+timedelta(seconds=7200)).isoformat(),fertilizer_history_complete_through=at.isoformat(),zone_output_evidence={**irrigation_output(at),"zone_execution_id":"ZONE-EXEC-1","observed_at":at.isoformat(),"state":"ON"})
     assert aux._next_pulse_index(skipped,at)==2 and aux._injection_gate(skipped,at) is None
     skipped.update(completed_pulses=1,completed_pulse_numbers=[1])
     assert aux._next_pulse_index(skipped,at)==2 and aux._injection_gate(skipped,at) is None
     skipped["prior_pulse_shutdown_evidence"]={"evidence_id":"LATE","zone_execution_id":"ZONE-EXEC-1","shutdown_verified":True,"observed_at":(at-timedelta(seconds=60)).isoformat()}
     assert aux._injection_gate(skipped,at)=="pulse_spacing_incomplete"
     skipped["prior_pulse_shutdown_evidence"]["observed_at"]=(at-timedelta(seconds=600)).isoformat()
     assert aux._injection_gate(skipped,at) is None
     skipped["premix_verified"]=False
     assert aux._injection_gate(skipped,at)=="current_batch_premix_unproven"
     assert aux.build_fertilized_irrigation_sequence(zone_id="B12345",irrigation_runtime_seconds=7200)["max_injection_pulses"]==4
    # Exercise actual claim branch: canonical v2 must reject mode stripping before any insert.
    from modules.telemetry import rootline_irrigation_execution_store as store
    import modules.oom_sakkie.bounded_postgres_read as db
    from unittest.mock import patch
    class Cursor:
     def __enter__(self): return self
     def __exit__(self,*args): pass
     def execute(self,sql,args=None):
      assert "insert into" not in sql.lower()
      self.sql=sql
     def fetchone(self):
      if "clock_timestamp" in self.sql: return (claim_time,)
      if "record_auxiliary_eligibility" in self.sql: return (stored_artifact,)
      return None
    class Connection:
     def __enter__(self): return self
     def __exit__(self,*args): pass
     def cursor(self): return Cursor()
    claim_time=__import__("datetime").datetime.fromisoformat(claim["claimed_at"]); stored_artifact=a
    assert store._scheduled_auxiliary_claim_valid(claim,stored_artifact,claim_time)
    stripped={k:v for k,v in claim.items() if k not in {"stop_mode","eligibility_sha256"}}
    with patch.object(db,"connect_bounded_rootline_postgres",lambda **kwargs:Connection()),patch.object(store,"_not_dispatched_ids",lambda cursor:[]):
     assert store._claim_single_auxiliary(stripped)["status"]=="canonical_auxiliary_claim_unproven"


def test_borehole_timed_cap_and_claim():
    from modules.telemetry import rootline_borehole_commissioning as b
    from modules.telemetry.rootline_irrigation_execution_store import _valid_borehole_eligibility
    from tests.test_rootline_borehole_commissioning import BoreholeStore,BoreholeTransport
    NOW=datetime.now(timezone.utc)
    base={"current":True,"stop_mode":"scheduled","device_key":b.DEVICE_KEY,"maximum_routine_runtime_seconds":36000,"native_fail_stop_seconds":0,"baseline_sha256":"b"*64,"registry_generation":9}
    proof={"authoritative":True,"state":"OFF","device_id":"1002851416","channel":1,"evidence_id":"a"*64,"retrieved_at":NOW.isoformat(),"borehole_configuration":{"online":True}}
    def artifact(provider=proof,interlocks={},requested=36000):
     return b.build_borehole_runtime_eligibility(need={"eligible":True},baseline=base,authority={"inside_standing_authority":True},provider=provider,interlocks=interlocks,energy={"eligible":True},requested_seconds=requested,now=NOW)
    a=artifact(); assert a["eligible"] and _valid_borehole_eligibility(a)
    assert not artifact(provider={**proof,"state":"ON"})["eligible"]
    assert not artifact(requested=36001)["eligible"]
    for fault in [{"manual_isolation_active":True},{"dry_run_safe":False},{"low_water_clear":False},{"supply_pressure_safe":False},{"full_tank_cutoff_fault":True}]: assert not artifact(interlocks=fault)["eligible"]
    assert not _valid_borehole_eligibility({**a,"stop_mode":None})
    class Transport(BoreholeTransport):
     def read_output_state(self,**kwargs): return {**proof,"state":self.state,"retrieved_at":clock[0].isoformat()}
     def read_safety_configuration(self,**kwargs): raise AssertionError("native configuration is optional")
    clock=[NOW]; store=BoreholeStore(); t=Transport()
    first=b.advance_borehole_execution(eligibility=a,store=store,transport=t,now=NOW,clock=lambda:clock[0])
    assert first["status"]=="borehole_started",first
    assert first["execution"]["native_fail_stop_deadline"] is None
    clock[0]=NOW+timedelta(hours=1); t.state="Unknown"
    assert b.advance_borehole_execution(eligibility={},store=store,transport=t,now=clock[0],clock=lambda:clock[0])["status"]=="borehole_active"
    assert len(t.commands)==1
    clock[0]=NOW+timedelta(hours=10)
    assert b.advance_borehole_execution(eligibility={},store=store,transport=t,now=clock[0],clock=lambda:clock[0])["status"]=="borehole_completed"
    assert [x["state"] for x in t.commands]==["ON","OFF"]
    from unittest.mock import patch
    from modules.telemetry import rootline_irrigation_execution_store as es, rootline_execution_runtime as runtime, rootline_managed_devices_runtime as managed
    import modules.oom_sakkie.bounded_postgres_read as db
    import modules.telemetry.rootline_energy_policy as energy
    class Cursor:
     rowcount=1
     def __enter__(self): return self
     def __exit__(self,*args): pass
     def execute(self,sql,args=None): self.sql=sql
     def fetchone(self):
      if "clock_timestamp" in self.sql:return (NOW,)
      if "record_borehole_eligibility" in self.sql:return (a,)
      return None
    class Connection:
     def __enter__(self):return self
     def __exit__(self,*args):pass
     def cursor(self):return Cursor()
    body=first["execution"]
    with patch.object(db,"connect_bounded_rootline_postgres",lambda **kwargs:Connection()),patch.object(es,"_borehole_state_rows",lambda cursor:[]):
     assert es._claim_borehole_material_load(body)["created"]
     for changed in [{"stop_mode":None},{"channel":2},{"primary_stop_deadline":(NOW+timedelta(seconds=1)).isoformat()},{"native_fail_stop_deadline":NOW.isoformat()}]:
      assert not es._claim_borehole_material_load({**body,**changed})["created"]
    clock[0]=NOW; t.state="OFF"
    with patch.object(managed,"run_rootline_managed_device_cycle",lambda **kwargs:kwargs["evidence_factory"](pending_devices=frozenset({"BOREHOLE-1-MINI-R4-CH1"}))),patch.object(runtime,"project_saved_program_for_execution",lambda *args,**kwargs:{"candidate_tasks":[{"task_id":"borehole","recommendation":"Recommend"}]}),patch.object(b,"load_registered_borehole_baseline",lambda **kwargs:base),patch.object(energy,"managed_energy_decision",lambda *args,**kwargs:{"borehole_eligible":True,"mixing_eligible":True}):
     packet=runtime.run_rootline_managed_device_reassessment(environ={"ROOTLINE_TIMED_CONTROL_ENABLED":"true","ROOTLINE_BOREHOLE_ENABLED":"true"},now=NOW,clock=lambda:NOW,transport=t,token_store=object(),evidence_loader=lambda **kwargs:({},NOW.astimezone(runtime.ZA_TZ).date().isoformat(),NOW))
     assert packet["borehole_execution"]["requested_seconds"]==14400


def test_honest_owner_status():
    from modules.telemetry.rootline_owner_status import _fertilizer_projection,_blocker
    from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle
    from unittest.mock import patch
    now=datetime.now(timezone.utc); identity="FERTILIZER-INJECTION-CH1"
    with patch.dict(os.environ,{"ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"}):
     empty=_fertilizer_projection([]);assert empty["injection"]["state"]=="Waiting for next plan"
     active={"auxiliary_device_id":identity,"execution_id":"one","action":"mark_auxiliary_active","state":"Active","start_evidence":{"authoritative":True,"state":"ON"}}
     planned={"auxiliary_device_id":identity,"execution_id":"two","action":"record_auxiliary_eligibility"}
     assert _fertilizer_projection([(now,planned),(now,active)])["injection"]["state"]=="Running"
     stopped={**active,"action":"record_auxiliary_completed","shutdown_verified":True,"shutdown_evidence":{"authoritative":True,"state":"OFF"}}
     projected=_fertilizer_projection([(now,stopped),(now,active)])
     assert projected["injection"]["state"]=="Stopped" and projected["injection"]["provider_output_state"]=="OFF"
    from modules.telemetry import rootline_irrigation_execution_store as es
    old={"auxiliary_device_id":identity,"device_id":"100204d497","channel":1,"execution_id":"old","action":"claim_auxiliary_before_on","provider_capacity_permit":{"permit":"test"}}
    old["event_id"]=es._event_id(old["action"],old)
    outcome={**old,"action":"record_auxiliary_on_outcome","on_outcome":{"provider_command_attempted":False,"accepted_unambiguous":False}}
    outcome["event_id"]=es._event_id(outcome["action"],outcome)
    retired={**old,"action":"record_execution_not_dispatched","terminal_contract":"rootline_proven_no_send.v1","not_dispatched_verified":True,"claim_event_id":old["event_id"],"claim_sha256":es._event_digest(old),"outcome_event_id":outcome["event_id"],"outcome_sha256":es._event_digest(outcome),"read_started_at":now.isoformat(),"retired_at":now.isoformat(),"shutdown_evidence":{"authoritative":True,"state":"OFF","device_id":"100204d497","channel":1,"evidence_id":"a"*64,"retrieved_at":now.isoformat()}}
    retired["event_id"]=es._event_id(retired["action"],retired)
    assert es._verified_not_dispatched(retired,[retired,outcome,old])
    retired_projection=_fertilizer_projection([(now,retired),(now,outcome),(now,old)])["injection"]
    assert retired_projection["state"]=="Stopped" and retired_projection["provider_output_state"]=="OFF"
    assert _fertilizer_projection([(now,retired),(now,active),(now,outcome),(now,old)])["injection"]["execution_id"]=="one"
    assert _blocker({"status":"Recommend","eligibility_blocker":"execution_eligible"}) is None
    assert project_zone_lifecycle(zone_id="E12345",recommendation={"status":"Recommend","eligibility_blocker":"eligible_candidate"})["state"]!="Held"




def test_normal_owner_policy_runtime_and_disabled_start_shutdown():
    from tests import test_rootline_scheduled_planner as fixture
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry.rootline_device_registry import get_device_contract
    from tests.test_rootline_execution_runtime import Store,controller
    from copy import deepcopy
    NOW=fixture.NOW
    for zone in ["B12345","C12345","A12345","E12345"]:
     _,advisor=fixture.payload(NOW)
     evidence={"weather":{"observed_at":NOW.isoformat(),"status":"fresh","rain_rate_mm_h":0,"rain_today_mm":10},"irrigation":{"source":"rootline_daily_advisor","advisor_generated_at":NOW.isoformat(),"advisor_operating_date":NOW.date().isoformat(),"zones":advisor["zones"],"adaptive_management":{"enabled":True,"zones":[{"zone_id":z["zone_id"]} for z in advisor["zones"]]}},"irrigation_history":{"status":"Available","zones":{z["zone_id"]:{"planning_epoch_start":NOW.isoformat(),"epoch_complete_through":NOW.isoformat(),"complete_through":NOW.isoformat(),"events":[]} for z in advisor["zones"]}}}
     evidence['weather']['stale_after_minutes']=30  # canonical local-weather freshness metadata
     # Select each exact zone through its genuine owner enabled flags; B/C share one flag, so mark sibling current need false.
     for z in evidence["irrigation"]["zones"]:
      if z["zone_id"]!=zone:z.update(visible_need="none",visible_need_observed_at=NOW.isoformat(),visible_need_source="owner")
     # Supply the exact current owner-policy material through the real one-time
     # saved-programme transition; live execution still uses actual projection.
     from modules.telemetry import rootline_water_energy_plan as planning
     source={"ROOTLINE_TIMED_CONTROL_ENABLED":"true",get_device_contract(zone)["authority_flag"]:"true"}
     with runtime.timed_control_scope(source):
      legacy=planning.build_water_energy_plan(evidence,NOW.date().isoformat(),now=NOW)
      evidence['saved_daily_plan']=planning._adopt_current_day_program(legacy,planning._as_za(NOW))
     proof=controller();proof.update(trusted_receipt_at=NOW.isoformat(),retrieved_at=NOW.isoformat(),current_outputs_authoritative=True,actuation_configuration_safe=False,timers_enabled=True)
     proof.pop("firmware")
     for row in proof["channels"]:row.update(native_auto_off_enabled=False,native_auto_off_seconds=0)
     clock=[NOW]
     class Transport:
      def __init__(self):self.state="OFF";self.calls=[]
      def read_safety_configuration(self,**kwargs):return {**kwargs,"zone_id":zone,"scheduled_authoritative":True,"output_state":self.state,"response_digest":"a"*64,"observed_at":clock[0].isoformat(),"relevant_outputs_off":True}
      def read_output_state(self,**kwargs):return {**kwargs,"authoritative":True,"state":self.state,"evidence_id":"b"*64,"retrieved_at":clock[0].isoformat()}
      def set_state(self,**kwargs):self.calls.append(kwargs);self.state=kwargs["state"];return {"accepted_unambiguous":True}
     store=Store();transport=Transport()
     kwargs=dict(notify=lambda *a:{"provider_delivery_confirmed":True},environ=source,now=NOW,store=store,token_store=object(),transport=transport,evidence_loader=lambda **k:(deepcopy(evidence),NOW.date().isoformat(),NOW),readback=lambda **k:deepcopy(proof),clock=lambda:clock[0],owner_user_id="42",chat_id="42",observation_store=lambda *a:{"success":True,"created":True},authority_checker=lambda db,artifact:True,active_weather_reader=lambda **k:{})
     result=runtime.run_rootline_execution_cycle(**kwargs)
     assert result.get("status")=="segment_started",(zone,result)
     assert store.active["planned_runtime_seconds"]==7200 and store.active["stop_mode"]=="scheduled"
     clock[0]=NOW+timedelta(seconds=7200);kwargs.update(environ={},now=clock[0])
     stopped=runtime.run_rootline_execution_cycle(**kwargs)
     assert stopped["status"]=="segment_completed",(zone,stopped)
     assert [x["state"] for x in transport.calls]==["ON","OFF"]
     print("PASS real policy-advisor-waterenergy-runtime-authority-coordinator path",zone,"120min, oldrain10mm nothold, nofirmware/inching, disabledstarts dueOFF")


from tests.test_rootline_active_supervision import reports

def test_authenticated_scheduler_admits_e_only(reports):
    from tests.test_rootline_active_supervision import gateway,ExecutionStore,Transport,ENV
    def managed(**kwargs):
        kwargs["after_safety"]({"blocks_bc":False})
        return {"success":True,"status":"no_active_managed_device","hardware_commands":0,"blocks_bc":False}
    value,status,starts,messages=gateway(ExecutionStore(),Transport(),
        source_env={**ENV,"ROOTLINE_AUTONOMOUS_BC_ENABLED":"false","ROOTLINE_A_ENABLED":"false","ROOTLINE_E_ENABLED":"true"},
        managed_device_cycle=managed)
    assert len(starts)==1
