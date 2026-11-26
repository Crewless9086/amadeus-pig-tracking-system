from contextlib import contextmanager
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_ifttt_transport as transport
from tests.test_rootline_execution_runtime import NOW
import pytest

@pytest.mark.parametrize('native',[True,False])
def test_stop_only_exposes_only_preparation(monkeypatch,native):
    sentinel=object()
    class Adapter:
        prepare_no_send_off=sentinel if native else None
        def set_state(self,**kwargs):return kwargs
    def advance(**kwargs):
        wrapper=kwargs['transport']
        assert wrapper.prepare_no_send_off is (sentinel if native else None)
        with pytest.raises(ValueError,match='forbids_on'):wrapper.set_state(state='ON')
        assert wrapper.set_state(state='OFF')=={'state':'OFF'}
        assert not hasattr(wrapper,'prepare_execution_capacity')
        return {'success':True,'status':'offline_checked'}
    monkeypatch.setattr(runtime,'advance_irrigation_execution',advance)
    runtime.supervise_rootline_active_execution(notify=lambda *a:None,
        transport=Adapter(),store=lambda *a:None,owner_user_id='42',chat_id='42',now=NOW)


def test_native_callback_qualified_without_replacing_identity(monkeypatch):
    callback=transport._NATIVE_CONTROLLER_READBACK
    native=transport.RootlineIFTTTTransport(token_store=object(),environ={'EWELINK_EXPECTED_DEVICE_ID':'100204e9bc'},readback=callback)
    assert callable(native.prepare_no_send_off)
    assert native.readback is callback
    custom=transport.RootlineIFTTTTransport(token_store=object(),environ={},readback=lambda **k:{})
    assert custom.prepare_no_send_off is None
    with pytest.raises(ValueError,match='no_send_target_changed'):
        with native.prepare_no_send_off(device_id='wrong',channel=1,binding={}):pass

@pytest.mark.parametrize('bad',[{'no_send_stage':'secret','no_send_reason':'deadline'},
    {'no_send_stage':{},'no_send_reason':[]}, {'no_send_stage':'family','no_send_reason':'raw secret SQL'}])
def test_recovery_projection_rejects_arbitrary_diagnostics(bad):
    from modules.telemetry.rootline_failure_diagnostics import sanitize_no_send
    assert sanitize_no_send(bad)=={}


def test_active_cycle_prioritizes_notifications_and_defers_plan_after_deadline(monkeypatch):
    from modules.telemetry import rootline_cycle_budget as budget
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_rootline_visible_operation import Events,current,plan_store,schedule_store,scheduled_payload,ENV,HEADERS,NOW
    elapsed=[0]; order=[]; events=Events([])
    monkeypatch.setattr(budget.time,'monotonic',lambda:elapsed[0])
    def supervise(**kwargs):
        order.append('safety');elapsed[0]+=90
        return {'success':True,'status':'active_segment_owned','active_execution_found':True,'hardware_commands':0}
    def loader():
        order.append('plan_read');elapsed[0]+=5;return current()
    def sender(chat,text,**kwargs):
        order.append('plan_send');return {'success':True,'telegram_message_id':'OFFLINE-PLAN'}
    def deliver(parsed,result,**kwargs):
        return deliver_family_result(parsed,result,event_store=events.delivery,sender=sender,**kwargs)
    def backlog(**kwargs):
        order.append('backlog');elapsed[0]+=60
        budget.remaining_seconds(minimum=5)
    rows,schedules=schedule_store()
    result,_=handle_rootline_reassessment_trigger({**scheduled_payload(due_at=NOW.isoformat()),
        'owner_user_id':'42','chat_id':'42','trigger':'declared_time','trigger_id':NOW.isoformat(),
        'trigger_timestamp':NOW.isoformat()},HEADERS,ENV,scheduler_now=NOW,
        specialist_loader=loader,state_store=plan_store()[1],schedule_store=schedules,
        family_delivery=deliver,equipment_notification_cycle=backlog,active_supervision_cycle=supervise)
    assert order==['safety','backlog']
    assert result['status']=='scheduled_rootline_reporting_deadline_deferred'
    assert result['telegram_sends']==0
    assert result['equipment_notification_status']=='rootline_transition_notifications_deferred'
    assert result['hardware_commands']==0


@pytest.mark.parametrize('stage,reason',[('family','ewelink_active_recovery_capacity_deferred'),
    ('optional_budget','rootline_cycle_deadline_exceeded')])
def test_recovery_reason_survives_gateway_and_durable_schedule(stage,reason):
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from tests.test_rootline_visible_operation import current,plan_store,schedule_store,scheduled_payload,ENV,HEADERS,NOW
    rows,schedules=schedule_store()
    result,_=handle_rootline_reassessment_trigger({**scheduled_payload(due_at=NOW.isoformat()),
        'owner_user_id':'42','chat_id':'42','trigger':'declared_time','trigger_id':NOW.isoformat(),
        'trigger_timestamp':NOW.isoformat()},HEADERS,ENV,scheduler_now=NOW,
        specialist_loader=current,state_store=plan_store()[1],schedule_store=schedules,
        family_delivery=lambda *a,**k:{'success':False},
        active_supervision_cycle=lambda **k:{'success':False,'status':'no_send_off_proof_pending',
            'active_execution_found':True,'hardware_commands':0,'no_send_stage':stage,'no_send_reason':reason})
    assert result['no_send_stage']==stage and result['no_send_reason']==reason
    outcome=next(value for key,value in rows.items() if key.endswith('-OUTCOME'))
    assert outcome['no_send_stage']==stage and outcome['no_send_reason']==reason
    assert outcome['error_type']=='no_send_'+stage+'_'+reason
