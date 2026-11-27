"""One consumed idle reporting recovery, never a second hardware owner."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
from threading import Lock
import pytest
from modules.oom_sakkie import automatic_reassessment_scheduler as scheduler
NOW=datetime(2026,11,27,17,10,tzinfo=timezone.utc)


def record(at,**changes):
    due=scheduler._bucket(at)
    identity=f"OOM-SCHEDULE-ROOTLINE-{due.strftime('%Y%m%dT%H%M%S%z')}"
    receipt=hashlib.sha256(f"{scheduler.CONTRACT_VERSION}|{scheduler.SCHEDULER_IDENTITY}|ROOTLINE|{due.isoformat()}".encode()).hexdigest()
    return {"contract_version":scheduler.CONTRACT_VERSION,"scheduler_identity":scheduler.SCHEDULER_IDENTITY,
        "specialist":"ROOTLINE","schedule_identity":identity,"identity":identity,"invocation_receipt":receipt,
        "due_at":due.isoformat(),"invoked_at":at.isoformat(),"evidence_cutoff":at.isoformat(),
        "status":"contained","report_work_due":True,"daily_plan_stage":"evidence_load",
        "daily_plan_error_type":"RootlineReadGroupDeadlineExceeded",
        "terminal_outcome":"scheduled_rootline_reporting_deadline_deferred",
        "report_effects_unknown":True,"writes_farm_data":None,**changes}


class Memory:
    def __init__(self,prior):self.rows={prior["identity"]+"-OUTCOME":deepcopy(prior)};self.consumed={};self.lock=Lock()
    def __call__(self,action,identity,payload):
        with self.lock:
            if action=="load_latest_outcome":
                outcomes=[v for k,v in self.rows.items() if k.endswith("-OUTCOME")]
                return deepcopy(outcomes[-1]) if outcomes else None
            if action=="load_schedule":return deepcopy(self.rows.get(identity+"-OUTCOME") or self.rows.get(identity))
            key=identity if action=="claim_schedule" else identity+"-OUTCOME"
            if key in self.rows:return {"success":True,"created":False}
            body=deepcopy(payload);candidate=body.pop("report_recovery_candidate",None)
            if candidate:
                source=(candidate["source_identity"],candidate["source_receipt"])
                if source not in self.consumed:self.consumed[source]=candidate;body["report_recovery"]=candidate
            self.rows[key]=body
            return {"success":True,"created":True}


def invoke(memory,at,full,recovery):
    return scheduler.run_due_reassessment(payload=record(at),now=at,store=memory,invoke=full,
        invoke_report_recovery=recovery)


def test_unknown_prior_plan_effects_allow_one_recovery_then_full_control():
    prior=record(NOW-timedelta(minutes=1));memory=Memory(prior);calls=[]
    def full():calls.append("full");return {"success":True,"status":"normal_control"}
    def recovery():calls.append("recovery");return {"success":False,"status":"still_pending"}
    first=invoke(memory,NOW,full,recovery)
    assert calls==["recovery"] and first.get("hardware_commands",0)==0
    invoke(memory,NOW+timedelta(minutes=1),full,recovery)
    assert calls==["recovery","full"] and len(memory.consumed)==1
    invoke(memory,NOW,full,recovery)
    assert calls==["recovery","full"]


@pytest.mark.parametrize("changes",[{"daily_plan_error_type":"other"},{"daily_plan_error_type":"QueryCanceled"},
    {"daily_plan_stage":"receipt_readback"},{"report_work_due":False},{"status":"completed"},
    {"report_recovery":{"mode":"idle_report_recovery"}},{"invocation_receipt":"bad"}])
def test_unproven_source_does_not_suppress_full_control(changes):
    memory=Memory(record(NOW-timedelta(minutes=1),**changes));calls=[]
    invoke(memory,NOW,lambda:calls.append("full") or {"success":True},lambda:pytest.fail("ineligible recovery"))
    assert calls==["full"]


@pytest.mark.parametrize("source_at",[NOW,NOW+timedelta(minutes=1),NOW-timedelta(minutes=6),NOW-timedelta(days=1)])
def test_source_age_and_order_are_bounded(source_at):
    assert scheduler.report_recovery_source(record(source_at),now=NOW,target_due=NOW) is None


def test_claimed_recovery_crash_consumes_source_even_without_outcome():
    memory=Memory(record(NOW-timedelta(minutes=1)))
    class Crash(BaseException):pass
    with pytest.raises(Crash):invoke(memory,NOW,lambda:pytest.fail("full"),lambda:(_ for _ in ()).throw(Crash()))
    calls=[]
    invoke(memory,NOW+timedelta(minutes=1),lambda:calls.append("full") or {"success":True},lambda:pytest.fail("consumed recovery"))
    assert calls==["full"] and len(memory.consumed)==1


@pytest.mark.parametrize("prior_committed",[False,True])
@pytest.mark.parametrize("manager_failure",[False,True])
@pytest.mark.parametrize("borehole",["absent","active","fault"])
def test_real_gateway_idle_recovery_refreshes_canonical_plan_with_25s_evidence(monkeypatch,prior_committed,manager_failure,borehole):
    from modules.oom_sakkie import telegram_gateway as gateway,automatic_reassessment_store as schedules_module
    from modules.oom_sakkie import rootline_operational_adapter as adapter
    from modules.telemetry import rootline_execution_runtime as runtime,rootline_managed_devices_runtime as managed
    from modules.telemetry import rootline_specialist_result as specialist,rootline_water_energy_plan as plan
    from modules.telemetry import rootline_cycle_budget as budget,rootline_owner_controls as controls
    from modules.telemetry import rootline_controller_availability as availability
    from modules.oom_sakkie import bounded_postgres_read as bounded
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_oom_sakkie_family_message_lifecycle import Memory as DeliveryMemory
    from tests.test_rootline_water_energy_plan import MemoryProgrammeDB,daily_program_facts
    from tests.test_rootline_active_supervision import ENV,HEADERS,payload
    # Unrelated reporting domains have no pending work; ROOTLINE refresh/delivery remains real.
    monkeypatch.setattr("modules.oom_sakkie.documents_green_followup_runtime.recover_documents_green_physical_follow_up",lambda **kw:{"handled":False})
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.reassess_due_mixer_presence",lambda **kw:{"status":"no_reassessable_mixer_presence"})
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",lambda *a:{})
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_breeding_attention_source_snapshot",lambda **kw:{})
    monkeypatch.setattr("modules.sales.sales_transaction_read.list_sales_transactions",lambda:({"success":True,"sales_transactions":[]},200))
    monkeypatch.setattr("modules.oom_sakkie.daily_farm_manager.run_daily_farm_manager",lambda **kw:{"success":not manager_failure,"status":"daily_farm_manager_database_unavailable" if manager_failure else "daily_farm_manager_unchanged"})
    monkeypatch.setattr("modules.oom_sakkie.rootline_fertilizer_commissioning_runtime.recover_fertilizer_commissioning",lambda **kw:{"status":"no_active_fertilizer_commissioning"})
    elapsed=[0.0];events=[];generations=[];cutoff=NOW
    monkeypatch.setattr(budget.time,"monotonic",lambda:elapsed[0])
    def spend(name,seconds):events.append(name);elapsed[0]+=seconds;budget.remaining_seconds()
    db=MemoryProgrammeDB();facts=daily_program_facts(NOW)
    saved=plan.build_daily_program(facts,NOW.date().isoformat(),now=NOW-timedelta(minutes=30))
    saved["generation"]=1;db.plans[saved["operating_date"]]=deepcopy(saved)
    original_connect=db.connect
    def connect(**kwargs):
        connection=original_connect();original_cursor=connection.cursor
        def cursor():
            value=original_cursor();execute=value.execute
            def query(sql,params=None):
                if sql.strip()=="select 1":connection.rows=[(1,)];return
                if "where i.operating_date=%s" in sql and len(params)==2:params=(params[-1],)
                return execute(sql,params)
            value.execute=query;return value
        connection.cursor=cursor;return connection
    monkeypatch.setattr(bounded,"connect_bounded_rootline_postgres",connect)
    monkeypatch.setattr(bounded,"connect_bounded_read",connect)
    monkeypatch.setenv("DATABASE_URL","synthetic-plan64")
    # A fresh owner pause changes the remaining programme through the REAL CAS path.
    owner=controls.project_owner_controls([],now=NOW)
    owner["devices"]["camp_a"].update(mode="paused",reason="Owner paused A",scope="today")
    facts["owner_controls"]=owner
    def evidence(**kwargs):
        assert kwargs["evidence_cutoff"]==cutoff
        spend("fresh evidence",25)
        kwargs["_reporting_results"].update(presentation_provider_availability={"status":"unknown","scopes":[]},presentation_input_health={"inputs":{}})
        return deepcopy(facts),NOW.date().isoformat(),NOW
    monkeypatch.setattr(specialist,"read_current_water_energy_evidence",evidence)
    ensure=plan.ensure_saved_daily_program
    def fresh(*args,**kwargs):
        spend("fresh programme",3)
        value=ensure(*args,**kwargs);generations.append(value[0].get("generation"));return value
    monkeypatch.setattr(plan,"ensure_saved_daily_program",fresh)
    if prior_committed:
        # Prior caller loses its response AFTER canonical append/readback.
        prior=specialist.refresh_current_rootline_specialist_result(database_url="synthetic-plan64",now=NOW,evidence_cutoff=NOW)
        assert prior["success"] is True and db.appends==1
        committed=deepcopy(db.plans[NOW.date().isoformat()]);elapsed[0]=0;events.clear();generations.clear()
    else:committed=None
    schedules=Memory(record(NOW-timedelta(minutes=1)))
    monkeypatch.setattr(schedules_module,"automatic_reassessment_store",schedules)
    monkeypatch.setattr(adapter,"recover_pending_manager_rootline_observation",lambda **kw:spend("manager recovery",1) or {"success":True})
    monkeypatch.setattr(availability,"notify_controller_availability",lambda **kw:{"success":True,"status":"controller_availability_notifications_observed","telegram_sends":0})
    state_rows={};delivery=DeliveryMemory();commands=[];starts=[]
    def state(action,identity,body):
        if action=="load_identity":return state_rows.get(identity)
        if action=="load_delivered":return None
        created=identity not in state_rows;state_rows.setdefault(identity,deepcopy(body or {}));return {"success":True,"created":created}
    def store(action,body):
        if action in {"load_active","load_active_auxiliaries","load_active_borehole"}:
            spend(action,5)
            return [] if action=="load_active_auxiliaries" else None
        pytest.fail(action)
    class Transport:
        def set_state(self,**kwargs):commands.append(kwargs);pytest.fail("idle recovery cannot command")
    transport=Transport()
    from tests.test_rootline_borehole_observation_bookmark import Case
    from tests.test_rootline_borehole_external_off import reported
    borehole_case=Case()
    borehole_case.transport.report=reported(now=NOW,state="ON")
    original_command=borehole_case.transport.set_state
    def command(**kw):
        events.append("borehole "+kw["state"])
        return original_command(**kw)
    borehole_case.transport.set_state=command
    original_observation=borehole_case.transport.read_output_state
    def observation(**kw):
        spend("borehole provider observation",9)
        return original_observation(**kw)
    borehole_case.transport.read_output_state=observation
    def active(**kwargs):return runtime.supervise_rootline_active_execution(**kwargs,store=store,transport=transport,clock=lambda:NOW+timedelta(seconds=elapsed[0]))
    def short(**kwargs):return managed.supervise_owned_injector(store=store,transport=transport,clock=lambda:NOW+timedelta(seconds=elapsed[0]))
    def managed_cycle(**kwargs):
        assert kwargs["allow_new_starts"] is False and kwargs["allow_borehole_starts"] is False and kwargs["after_safety"] is None
        if borehole!="absent":
            def owned_store(action,body):
                if action in {"load_active_auxiliaries","load_active_borehole","load_owner_control_stop"}:spend(action,2)
                return borehole_case.store(action,body)
            def energy():
                spend("fresh borehole energy",2)
                return {"continuous_borehole_fresh":True,"continuous_borehole_eligible":True,"borehole_fresh":True,"borehole_eligible":True}
            def protection():
                spend("fresh borehole protection",2)
                return {"safe":borehole!="fault"}
            def conditions(**kw):
                spend("fresh borehole conditions",3)
                return {"success":True,"stop_required":False}
            return managed.run_rootline_managed_device_cycle(evidence={},store=owned_store,transport=borehole_case.transport,
                environ=kwargs["environ"],canonical_loader=lambda key:None,now=NOW,clock=lambda:NOW+timedelta(seconds=elapsed[0]),
                energy_reader=energy,borehole_safety_reader=protection,borehole_conditions_reader=conditions,
                allow_new_starts=False,allow_borehole_starts=False,after_safety=None)
        return runtime.run_rootline_managed_device_reassessment(**kwargs,store=store,transport=transport,token_store=object(),clock=lambda:NOW+timedelta(seconds=elapsed[0]),evidence_loader=lambda **kw:pytest.fail("no new managed planning"))
    def sender(chat,text,*,deadline_monotonic):
        assert deadline_monotonic==140 and budget.remaining_seconds()>30
        spend("provider delivery",2);return delivery.send(chat,text)
    def deliver(parsed,result,**kwargs):return deliver_family_result(parsed,result,event_store=delivery.store,sender=sender,**kwargs)
    # The real gateway must retain this exact typed failure in its durable outcome.
    from modules.telemetry.rootline_bounded_read_group import RootlineReadGroupDeadlineExceeded
    failed_at=NOW-timedelta(minutes=1)
    schedules.rows={}
    def failed_loader():raise RootlineReadGroupDeadlineExceeded("synthetic read deadline")
    failed_result,_=gateway.handle_rootline_reassessment_trigger(payload(due_at=failed_at.isoformat(),trigger_timestamp=failed_at.isoformat(),evidence_cutoff=failed_at.isoformat()),HEADERS,
        {**ENV,"DATABASE_URL":"synthetic-plan64","ROOTLINE_INPUT_HEALTH_ENABLED":"false"},scheduler_now=failed_at,
        supervision_clock=lambda:failed_at,schedule_store=None,state_store=state,active_supervision_cycle=active,
        short_auxiliary_supervision_cycle=short,managed_device_cycle=lambda **kw:{"success":True,"status":"no_active_managed_device","hardware_commands":0},
        execution_cycle=lambda **kw:{"success":True,"status":"no_new_task"},specialist_loader=failed_loader,
        family_delivery=deliver,equipment_notification_cycle=lambda **kw:{"success":True,"telegram_sends":0})
    persisted=schedules("load_latest_outcome","ROOTLINE",None)
    assert persisted["daily_plan_error_type"]=="RootlineReadGroupDeadlineExceeded",persisted
    assert scheduler.report_recovery_source(persisted,now=NOW,target_due=NOW) is not None,persisted
    assert not delivery.sent
    elapsed[0]=0;events.clear()
    result,status=gateway.handle_rootline_reassessment_trigger(payload(due_at=NOW.isoformat(),trigger_timestamp=NOW.isoformat(),evidence_cutoff=NOW.isoformat()),HEADERS,
        {**ENV,"DATABASE_URL":"synthetic-plan64","ROOTLINE_BOREHOLE_ENABLED":"true","ROOTLINE_INPUT_HEALTH_ENABLED":"false"},
        scheduler_now=NOW,supervision_clock=lambda:NOW+timedelta(seconds=elapsed[0]),schedule_store=None,state_store=state,
        active_supervision_cycle=active,short_auxiliary_supervision_cycle=short,managed_device_cycle=managed_cycle,
        execution_cycle=lambda **kw:starts.append(kw) or pytest.fail("no new admission"),family_delivery=deliver,
        equipment_notification_cycle=lambda **kw:{"success":True,"status":"observed","telegram_sends":0})
    if manager_failure:
        assert status==202 and result["success"] is False
        assert result["status"]=="scheduled_reassessment_database_unavailable"
    else:
        assert status==200 and result["success"] is True,result
        assert result["daily_presentation_status"]=="daily_farm_manager_unchanged"
    assert result["idle_report_recovery_eligible"] is True
    assert result["plan_delivery_status"]=="delivered_current_irrigation_plan",result
    assert len(delivery.sent)==1 and not commands and not starts
    if borehole!="absent":
        assert "fresh borehole energy" in events and "fresh borehole protection" in events and "fresh borehole conditions" in events
        assert events.index("fresh borehole conditions")<events.index("fresh evidence")
        assert borehole_case.store.owner_reads==1
        assert [c["state"] for c in borehole_case.transport.commands]==(["OFF"] if borehole=="fault" else [])
        assert borehole_case.transport.reads==(0 if borehole=="fault" else 1)
        if borehole=="fault":assert events.index("borehole OFF")<events.index("fresh evidence")
    assert "fresh evidence" in events and "fresh programme" in events and "provider delivery" in events
    assert elapsed[0]<140 and budget.CYCLE_WORK_SECONDS==140 and budget.REPORT_MINIMUM_SECONDS==25
    assert db.appends==1
    if prior_committed:
        assert generations[0]==committed["generation"] and db.plans[NOW.date().isoformat()]["generation"]==committed["generation"]


@pytest.mark.parametrize("owned",["camp","mixer","inventory_failure"])
def test_recovery_selection_preserves_normal_control_when_fresh_inventory_not_idle(monkeypatch,owned):
    from modules.oom_sakkie import telegram_gateway as gateway,automatic_reassessment_store as schedules_module
    from modules.telemetry import rootline_execution_runtime as runtime,rootline_managed_devices_runtime as managed
    from tests.test_rootline_active_supervision import ENV,HEADERS,payload,ExecutionStore,Transport,active
    from tests.test_rootline_active_weather_stop import dry_weather_reader
    from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable
    schedules=Memory(record(NOW-timedelta(minutes=1)))
    monkeypatch.setattr(schedules_module,"automatic_reassessment_store",schedules)
    row=active(due=False) if owned=="camp" else None
    if row:
        row.update(claimed_at=(NOW-timedelta(seconds=100)).isoformat(),primary_stop_deadline=(NOW+timedelta(minutes=50)).isoformat(),native_fail_stop_deadline=(NOW+timedelta(minutes=50)).isoformat())
        row["start_evidence"]["retrieved_at"]=(NOW-timedelta(seconds=99)).isoformat()
    store=ExecutionStore(row)
    if owned=="mixer":store.auxiliary={"auxiliary_device_id":"FERTILIZER-MIXER-CH2","state":"Active"}
    if owned=="inventory_failure":store.fail="load_active_auxiliaries"
    transport=Transport(state="ON");calls=[]
    def short(**kw):return managed.supervise_owned_injector(store=store,transport=transport,clock=lambda:NOW)
    def supervise(**kw):return runtime.supervise_rootline_active_execution(**kw,store=store,transport=transport,clock=lambda:NOW,active_weather_reader=dry_weather_reader,token_store=object())
    def control(**kw):
        calls.append(kw)
        # Recovery selection must not suppress the normal camp/mixer continuation owner.
        if owned!="inventory_failure":
            assert kw["allow_new_starts"] is True and callable(kw["after_safety"])
        return {"success":True,"status":"normal_control_observed","hardware_commands":0}
    result,_=gateway.handle_rootline_reassessment_trigger(payload(due_at=NOW.isoformat(),trigger_timestamp=NOW.isoformat(),evidence_cutoff=NOW.isoformat()),HEADERS,
        {**ENV,"DATABASE_URL":"synthetic-exclusions64"},scheduler_now=NOW,supervision_clock=lambda:NOW,
        schedule_store=None,state_store=lambda *a:None,active_supervision_cycle=supervise,short_auxiliary_supervision_cycle=short,
        managed_device_cycle=control,specialist_loader=lambda:(_ for _ in ()).throw(RootlineExecutionStoreUnavailable("synthetic reporting unavailable")),
        equipment_notification_cycle=lambda **kw:{"success":True,"telegram_sends":0},execution_cycle=lambda **kw:{"success":True,"status":"no_new_task"})
    assert result.get("idle_report_recovery_eligible") is False
    assert calls and not transport.calls
    if owned=="mixer":assert short()["auxiliary_inventory_empty"] is False
