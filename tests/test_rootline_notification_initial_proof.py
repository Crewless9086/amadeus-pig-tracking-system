"""Real coordinator-to-family retry proof regression; no external I/O."""
from copy import deepcopy
from tests.test_rootline_visible_operation import Events,edges,NOW
from modules.telemetry.rootline_irrigation_coordinator import _notify
from modules.oom_sakkie.rootline_transition_notifications import transition,compose_transition_notice,recover_transition_notifications
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result,localize_recipient_result
from modules.oom_sakkie.family_presentation import envelope
from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority

def run(kind):
    event=edges('mixer')[0];state,payload=transition(event)
    events=Events([event]);calls=[];cards=[];proofs=[]
    def sender(*a,**k):
        calls.append(1)
        if len(calls)==1:return {'success':False,'delivery_definitely_not_sent':kind=='definite'}
        return {'success':True,'telegram_message_id':'synthetic-receipt'}
    def notice(state,body,*,retry_proof_identity=''):
        card=(body.get('notification_identity') or body['execution_id'])+':'+state.upper();cards.append(card);proofs.append(retry_proof_identity)
        parsed={'telegram_user_id':'synthetic-owner','telegram_chat_id':'synthetic-chat','language':'en'}
        visible={'success':True,'status':state.lower(),'answer':compose_transition_notice(state,body),'recipient_render_contract':'specialist_structured_recipient_v1','recipient_language':'en'}
        authority=None
        if retry_proof_identity:
            localized=localize_recipient_result(parsed,visible,'ROOTLINE')
            authority=issue_delivery_retry_authority(mission_id=card,card_mission_id=card,text=envelope(localized['answer']),proof_identity=retry_proof_identity)
        delivery=deliver_family_result(parsed,visible,specialist='ROOTLINE',mission_id=card,card_mission_id=card,event_store=events.delivery,sender=sender,delivery_retry_authority=authority)
        return {**delivery,'provider_delivery_confirmed':bool(delivery.get('telegram_message_id')) and delivery.get('success') is True,'provider_delivery_ambiguous':'ambiguous' in delivery.get('status',''),'provider_message_id':delivery.get('telegram_message_id','')}
    def store(action,body):
        if action=='claim_notification':return {'success':True,'created':True}
        if action=='record_notification_delivery' and 'transition_event_id' not in body:body={**body,'transition_event_id':event['event_id']}
        return events.store(action,body)
    initial=_notify(notice,store,state,payload)
    first=deepcopy(events.notifications[-1])
    assert first['delivery_definitely_not_sent'] is (kind=='definite')
    recovery=recover_transition_notifications(notify=notice,now=NOW,store=store)
    replay=recover_transition_notifications(notify=notice,now=NOW,store=store)
    assert len(set(cards))==1
    if kind=='definite':
        assert len(calls)==2 and events.notifications[-1]['delivery_confirmed'] is True and proofs[-1]
    else:
        assert len(calls)==1 and events.notifications[-1]['delivery_ambiguous'] is True
    return {'case':kind,'initial':initial,'initial_notice_flags':{k:first.get(k) for k in ('delivery_confirmed','delivery_ambiguous','delivery_definitely_not_sent')},'provider_stub_calls':len(calls),'same_card':len(set(cards))==1,'recovery_status':recovery['status'],'final_confirmed':events.notifications[-1].get('delivery_confirmed'),'final_ambiguous':events.notifications[-1].get('delivery_ambiguous')}


import pytest

@pytest.mark.parametrize("kind", ["definite", "ambiguous"])
def test_real_initial_notice_family_recovery_preserves_proof(kind):
    result = run(kind)
    assert result["same_card"]
    assert result["provider_stub_calls"] == (2 if kind == "definite" else 1)

@pytest.mark.parametrize("response", [
    {"success":False,"delivery_definitely_not_sent":True,"provider_delivery_ambiguous":True},
    {"success":False,"delivery_definitely_not_sent":True,"status":"delivery_ambiguous"},
    {"success":True,"delivery_definitely_not_sent":True,"provider_delivery_confirmed":True,"provider_message_id":"receipt"},
    {"success":False,"delivery_definitely_not_sent":True,"provider_message_id":"receipt"},
    {"success":False,"delivery_definitely_not_sent":"true"},
])
def test_conflicting_or_unproven_initial_response_cannot_grant_retry(response):
    rows=[]
    def store(action,body):
        if action=="claim_notification":return {"success":True,"created":True}
        assert action=="record_notification_delivery"
        rows.append(body)
    _notify(lambda *args:response,store,"Started",{"execution_id":"synthetic"})
    assert rows[0]["delivery_definitely_not_sent"] is False

from tests.test_rootline_active_supervision import reports

@pytest.mark.parametrize("error", [TypeError, TimeoutError])
def test_real_gateway_scheduler_retains_equipment_failure_classification(reports, error):
    from tests.test_rootline_active_supervision import ExecutionStore, Transport, ScheduleStore, gateway
    schedules=ScheduleStore()
    def failed(**kwargs):
        raise error("private exception text and identifiers must not escape")
    value,status,starts,messages=gateway(ExecutionStore(None),Transport(),schedules=schedules,
        equipment_notification_cycle=failed,
        managed_device_cycle=lambda **kwargs:{"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0})
    assert status==200
    outcomes=[row for key,row in schedules.rows.items() if key.endswith(":outcome")]
    assert len(outcomes)==1
    outcome=outcomes[0]
    assert outcome["equipment_notification_status"]=="rootline_transition_notifications_unavailable"
    assert outcome["equipment_notification_failure"]=={"error_type":error.__name__}
    assert "private exception" not in str(outcome)
