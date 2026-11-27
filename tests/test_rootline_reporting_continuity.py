"""Actual gateway/family delivery boundaries under measured live58 stage costs."""
from datetime import datetime, timedelta, timezone
import pytest
from tests.test_rootline_active_supervision import reports
NOW = datetime(2026,11,27,11,tzinfo=timezone.utc)

@pytest.mark.parametrize("old_order", [False, True])
def test_controller_episode_precedes_optional_scans_and_retains_real_delivery_guard(monkeypatch,reports,old_order):
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.oom_sakkie import automatic_reassessment_store as schedules_module
    from modules.telemetry import rootline_controller_availability as availability
    from modules.telemetry import rootline_irrigation_execution_store as execution_store
    from modules.telemetry import rootline_water_energy_plan as plans
    from modules.telemetry import rootline_cycle_budget as budget
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_oom_sakkie_family_message_lifecycle import Memory
    from tests.test_rootline_active_supervision import ScheduleStore,ENV,HEADERS,payload
    from tests.test_rootline_controller_availability import Database,observation,DEVICE
    elapsed=[0.0];order=[];db=Database();schedules=ScheduleStore();memory=Memory();clocks=[]
    monkeypatch.setattr(budget.time,"monotonic",lambda:elapsed[0])
    schedules.rows["prior:outcome"]={"specialist":"ROOTLINE","status":"completed","next_due_at":(NOW+timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(schedules_module,"automatic_reassessment_store",schedules)
    monkeypatch.setattr(plans,"ensure_due_daily_program",lambda **kwargs:({"success":True,"status":"reused"},200))
    def store(action,body):
        assert action=="record_notification_delivery"
        db.rows.append({**body,"action":action,"event_id":"receipt"});return {"success":True}
    monkeypatch.setattr(execution_store,"rootline_irrigation_execution_store",store)
    real_notify=availability.notify_controller_availability
    def notification(**kwargs):
        order.append("controller")
        if old_order:elapsed[0]+=10.428+9.911
        elapsed[0]+=5.155  # observed read/receipt lookup cost before family send
        clocks.append(kwargs["now"])
        return real_notify(**kwargs,connect=db.connect)
    monkeypatch.setattr(availability,"notify_controller_availability",notification)
    def managed(**kwargs):
        # The live58 plan boundary has140-46.811 seconds already consumed.
        elapsed[0]=140-46.811
        at=NOW+timedelta(seconds=30)
        availability.reconcile_controller_availability(DEVICE,observation("offline",at),now=at,connect=db.connect)
        return {"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0}
    def sender(chat,text,*,deadline_monotonic):
        order.append("send");assert deadline_monotonic==140
        elapsed[0]+=2
        return memory.send(chat,text)
    def delivery(parsed,result,**kwargs):
        return deliver_family_result(parsed,result,event_store=memory.store,sender=sender,**kwargs)
    def provider(**kwargs):
        order.append("provider")
        if not old_order:elapsed[0]+=10.428
        return {"success":True,"status":"observed","telegram_sends":0}
    def inputs(**kwargs):
        order.append("input")
        if not old_order:elapsed[0]+=9.911
        return {"success":True,"status":"observed","telegram_sends":0}
    source={**ENV,"ROOTLINE_AUTONOMOUS_BC_ENABLED":"false","ROOTLINE_INPUT_HEALTH_ENABLED":"true"}
    result,status=handle_rootline_reassessment_trigger(
        payload(due_at=NOW.isoformat(),trigger_timestamp=NOW.isoformat(),evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat()),
        HEADERS,source,scheduler_now=NOW,supervision_clock=lambda:NOW+timedelta(seconds=elapsed[0]),
        schedule_store=None,state_store=lambda *args:{"success":True,"created":True},managed_device_cycle=managed,
        family_delivery=delivery,provider_notification_cycle=provider,input_notification_cycle=inputs,
        active_supervision_cycle=lambda **kwargs:{"success":True,"status":"no_active_irrigation","active_execution_found":False},
        equipment_notification_cycle=lambda **kwargs:{"success":True,"status":"observed","telegram_sends":0})
    outcome=list(schedules.rows.values())[-1]
    assert order[0]=="controller" and order.index("provider")<order.index("input")
    assert len(memory.sent)==(0 if old_order else 1)
    assert outcome["controller_notification_status"]==("controller_availability_notifications_deferred" if old_order else "controller_availability_notifications_observed")
    assert outcome["controller_notifications_confirmed"] is (not old_order)
    assert outcome["controller_notification_failure"]=={}
    assert budget.CYCLE_WORK_SECONDS==140 and budget.REPORT_MINIMUM_SECONDS==25
    assert result["hardware_commands"]==0
    assert db.rows[0]["checked_at"]==(NOW+timedelta(seconds=30)).isoformat()
    if old_order:
        assert not memory.rows  # genuine family guard refused before send claim
    else:
        assert order.index("send")<order.index("provider")
        # Existing canonical receipt prevents a later repeat, not a local flag.
        real_notify(notify=lambda *args,**kwargs:pytest.fail("duplicate notice"),
            store=store,now=NOW+timedelta(seconds=elapsed[0]),connect=db.connect)


@pytest.mark.parametrize("defer_poll,plan_failure,extra_cost", [
    (True,None,0),(False,None,0),(True,"error",0),(True,"deadline",0),(True,None,65)])
def test_native_gateway_defers_only_idle_poll_after_nontrivial_plan(monkeypatch,reports,defer_poll,plan_failure,extra_cost):
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_cycle_budget as budget
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from tests.test_rootline_bc_cycle_efficiency import Path as CostedPath, report_inputs
    from tests.test_rootline_active_supervision import ENV,HEADERS,payload
    from tests.test_rootline_execution_runtime import NOW as START
    path=CostedPath(monkeypatch);order=[];polls=[];inventory=[]
    original=runtime.run_rootline_managed_device_reassessment
    def store(action,body):
        inventory.append(action)
        if action=="load_active_auxiliaries":return []
        if action=="load_active_borehole":return None
        pytest.fail("unexpected control write: "+action)
    def poll(*args):
        from modules.telemetry.rootline_owned_deadlines import check_owned_deadline
        check_owned_deadline()
        try:
            if budget.remaining_seconds(15)<15:return
        except budget.RootlineCycleDeadlineExceeded:return
        polls.append(path.clock.elapsed);order.append("poll")
        path.clock.spend("measured live58 idle connectivity",9.449)
        check_owned_deadline()
    monkeypatch.setattr(runtime,"_refresh_one_controller_availability",poll)
    def native(**kwargs):
        order.append("control")
        # Measured live58 pre-plan93.189s, less separately qualified13s
        # connection/unused-read model and the moved9.449s idle poll.
        # This is a latency model, not a claim of measured live59 speed.
        path.clock.spend("unchanged control plus qualified read-cost model",70.740+extra_cost)
        if not defer_poll:kwargs.pop("defer_controller_connectivity",None)
        kwargs.update(environ={},allow_new_starts=False,allow_borehole_starts=False,
            store=store,transport=path.transport,token_store=object(),clock=path.clock.now)
        return original(**kwargs)
    monkeypatch.setattr(runtime,"run_rootline_managed_device_reassessment",native)
    loader,generator=report_inputs(path,plan_seconds=11)
    def costed_plan(current):
        order.append("plan")
        budget.remaining_seconds()
        result=generator(current)
        budget.remaining_seconds()
        if plan_failure=="error":raise ValueError("synthetic plan persistence failure")
        if plan_failure=="deadline":raise budget.RootlineCycleDeadlineExceeded("synthetic plan deadline")
        return result
    source={**ENV,"ROOTLINE_AUTONOMOUS_BC_ENABLED":"false","ROOTLINE_FERTILIZER_MIXING_ENABLED":"true"}
    def invoke():
        return handle_rootline_reassessment_trigger(
            payload(due_at=START.isoformat(),trigger_timestamp=START.isoformat(),evidence_cutoff=(START-timedelta(seconds=1)).isoformat()),
            HEADERS,source,scheduler_now=START,supervision_clock=path.clock.now,
            schedule_store=path.schedules,state_store=path.state,
            specialist_loader=loader,daily_plan_generator=costed_plan,
            active_supervision_cycle=lambda **kw:{"success":True,"status":"no_active_irrigation","active_execution_found":False},
            family_delivery=lambda *a,**k:{"success":True,"telegram_message_id":"synthetic"})
    value,status=invoke()
    assert inventory==["load_active_auxiliaries","load_active_borehole"]*2
    assert value["hardware_commands"]==0 and not path.transport.calls
    assert len(polls)==(0 if extra_cost else 1)
    assert order[0]=="control"
    if extra_cost:
        assert "plan" not in order
    elif defer_poll:
        assert order.index("plan")<order.index("poll")
        if plan_failure is None:assert status==200,value
        else:assert value["success"] is False
    else:
        assert order.index("poll")<order.index("plan")
        assert value["status"]=="scheduled_rootline_reporting_deadline_deferred",value
    before=list(polls)
    invoke()  # durable replay has no retained callback and issues no extra poll
    assert polls==before
    assert budget.work_deadline() is budget.on_deadline() is None


@pytest.mark.parametrize("short", [False,True])
def test_standalone_poll_default_and_short_duty_never_registers(monkeypatch,short):
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_managed_devices_runtime as managed
    calls=[];callbacks=[]
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",lambda **kw:{"success":True,"hardware_commands":0,"short_auxiliary_duty_owned":short})
    monkeypatch.setattr(runtime,"_refresh_one_controller_availability",lambda *args:calls.append("poll"))
    kwargs=dict(environ={},now=NOW,clock=lambda:NOW,transport=object(),token_store=object(),store=lambda *args:None)
    result=runtime.run_rootline_managed_device_reassessment(**kwargs)
    assert calls==([] if short else ["poll"])
    calls.clear()
    result=runtime.run_rootline_managed_device_reassessment(**kwargs,defer_controller_connectivity=callbacks.append)
    assert not calls and len(callbacks)==(0 if short else 1)
    assert all(not callable(value) for value in result.values())
    if callbacks:callbacks.pop()()
    assert calls==([] if short else ["poll"])


@pytest.mark.parametrize("failure", [RuntimeError, __import__("asyncio").CancelledError])
def test_deferred_poll_exception_cannot_leak_callback_into_next_invocation(monkeypatch,reports,failure):
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from tests.test_rootline_active_supervision import ScheduleStore,ENV,HEADERS,payload
    callbacks=[];calls=[];fail=[True]
    def native(**kwargs):
        identity=len(callbacks)
        def poll():
            calls.append(identity)
            if fail[0]:raise failure("synthetic interrupted optional read")
        callbacks.append(poll);kwargs["defer_controller_connectivity"](poll)
        return {"success":True,"hardware_commands":0,"status":"no_eligible_managed_device_task"}
    monkeypatch.setattr(runtime,"run_rootline_managed_device_reassessment",native)
    def invoke(at):
        schedules=ScheduleStore()
        schedules.rows["prior:outcome"]={"specialist":"ROOTLINE","status":"completed","next_due_at":(at+timedelta(minutes=30)).isoformat()}
        return handle_rootline_reassessment_trigger(
            payload(due_at=at.isoformat(),trigger_timestamp=at.isoformat(),evidence_cutoff=(at-timedelta(seconds=1)).isoformat()),
            HEADERS,{**ENV,"ROOTLINE_AUTONOMOUS_BC_ENABLED":"false","ROOTLINE_FERTILIZER_MIXING_ENABLED":"true"},
            scheduler_now=at,supervision_clock=lambda:at,schedule_store=schedules,
            state_store=lambda *args:{"success":True,"created":True},
            active_supervision_cycle=lambda **kw:{"success":True,"status":"no_active_irrigation","active_execution_found":False})
    try:invoke(NOW)
    except failure:pass
    assert calls==[0]
    fail[0]=False
    value,status=invoke(NOW+timedelta(minutes=1))
    assert calls==[0,1] and status==200,value
    assert all(not callable(value) for value in value.values())
