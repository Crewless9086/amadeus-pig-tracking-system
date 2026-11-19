"""Production gateway + canonical transition projection + real family delivery, zero external I/O."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import pytest
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from modules.oom_sakkie.rootline_transition_notifications import recover_transition_notifications, transition, compose_transition_notice
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.telemetry.rootline_cycle_budget import cycle_budget
from tests.test_oom_sakkie_automatic_reassessment_scheduler import memory_store as schedule_store, scheduled_payload, NOW
from tests.test_oom_sakkie_rootline_reassessment_delivery import memory_store as plan_store, ENV, HEADERS


class Events:
    def __init__(self, transitions):
        self.transitions = transitions
        self.notifications = []
        self.family = {}
        self.lock = Lock()
    def store(self, action, payload):
        if action == 'load_notification_transitions':
            return {'epoch':{'since':NOW.isoformat()},'transitions':[{'transition': row, 'notification': next((r for r in reversed(self.notifications)
                if r.get('transition_event_id') == row['event_id']), {})} for row in self.transitions]}
        assert action == 'record_notification_delivery'
        with self.lock:
            self.notifications.append({**payload,'event_id':f'N{len(self.notifications)}'})
        return {'success':True,'created':True}
    def delivery(self, action, identity, payload):
        with self.lock:
            if action == 'load':
                return [v for v in self.family.values() if v.get('card_mission_id') == identity]
            assert action == 'record'
            created = identity not in self.family
            self.family.setdefault(identity, payload)
            return {'success':True,'created':created}


def edges(kind='borehole'):
    device, channel = ('1002851416',1) if kind=='borehole' else (
        ('100204d497',2 if kind=='mixer' else 1) if kind in {'mixer','injector'} else
        ('private-grid-device',None) if kind=='eskom' else ('100204e9bc',{'A':4,'B':1,'C':2,'E':3}[kind]))
    execution = {'execution_id':'EXEC-'+kind,'device_id':device,'channel':channel}
    if kind in {'mixer','injector'}:execution['auxiliary_device_id']='FERTILIZER-MIXER-CH2' if kind=='mixer' else 'FERTILIZER-INJECTION-CH1'
    if kind in {'A','B','C','E'}:execution['zone_id']=kind+'12345'
    actions = ('mark_borehole_active','record_borehole_completed') if kind=='borehole' else (
        ('mark_auxiliary_active','record_auxiliary_completed') if kind in {'mixer','injector'} else
        ('record_eskom_completed','record_eskom_completed') if kind=='eskom' else ('mark_active','record_completed'))
    rows=[]
    for i,(state,action) in enumerate(zip(('ON','OFF'),actions)):
        proof={'authoritative':True,'state':state,'device_id':device,'channel':channel,
            'retrieved_at':(NOW-timedelta(minutes=2-i)).isoformat()}
        key=('readback' if kind=='eskom' else ('provider_start_evidence' if i==0 else 'provider_final_off_evidence')
            if kind=='borehole' else ('start_evidence' if i==0 else 'shutdown_evidence'))
        rows.append({**execution,'event_id':f'{kind}-{state}','action':action,key:proof,
            'state':'Active' if i==0 else 'Completed','shutdown_verified':i==1,
            **({'desired_state':state,'execution_id':f'EXEC-eskom-{state}'} if kind=='eskom' else {})})
    return rows


def current():
    return {'success':True,'operating_date':'2026-08-05','result_id':'R1','generation':'G1',
        'evidence_cutoff':'2026-08-05T08:14:00+00:00','owner_brief':{'family_fact_needed':''},
        'irrigation_lifecycle':{'B12345':{'state':'Eligible'}},
        'recommendations':[{'subject':'B12345','status':'Recommend','planned_duration_minutes':120,
            'preferred_window':'now','reason':'Weekly target due.'}]}


def gateway(events, sender, *, now=NOW, schedules=None, plans=None, control_success=False, unrelated=False):
    def deliver(parsed, result, **kwargs):
        return deliver_family_result(parsed,result,event_store=events.delivery,sender=sender,**kwargs)
    def reporter(**kwargs):return recover_transition_notifications(store=events.store,**kwargs)
    return handle_rootline_reassessment_trigger({**scheduled_payload(due_at=now.isoformat()),
        'owner_user_id':'42','chat_id':'42','trigger':'declared_time','trigger_id':now.isoformat(),
        'trigger_timestamp':now.isoformat()},HEADERS,ENV,scheduler_now=now,
        specialist_loader=current,state_store=plans or plan_store()[1],schedule_store=schedules or schedule_store()[1],
        family_delivery=deliver,equipment_notification_cycle=reporter,
        active_supervision_cycle=lambda **k:{'success':control_success,'status':'no_active_irrigation' if control_success else 'execution_cycle_deadline_deferred',
            'active_execution_found':False,'hardware_commands':0,'writes_farm_data':False})


@pytest.mark.parametrize('kind',['A','B','C','E','mixer','injector','borehole','eskom'])
def test_verified_all_device_edges_recover_after_restart_without_duplicate(kind):
    events=Events(edges(kind)); sends=[]
    def send(chat,text,**kwargs):
        sends.append(text);return {'success':True,'telegram_message_id':str(len(sends))}
    _,plans=plan_store();_,schedules=schedule_store()
    first,http=gateway(events,send,plans=plans,schedules=schedules)
    assert http==202 and first['success'] is False # Failed control stays failed despite successful notices.
    assert first['plan_delivery_status']=='delivered_current_irrigation_plan'
    assert len(sends)==3 and all(r['delivery_confirmed'] for r in events.notifications)
    assert 'plan below remains intended work' in sends[0]
    assert 'ON' in sends[1] and 'OFF' in sends[2]
    assert first['hardware_commands']==0
    again,_=gateway(events,send,now=NOW+timedelta(minutes=1),plans=plans,schedules=schedules)
    assert len(sends)==3
    assert again['plan_delivery_status']=='current_irrigation_plan_unchanged'
    assert again['telegram_sends']==0


@pytest.mark.parametrize('damage',['acceptance_only','wrong_state','wrong_device','wrong_channel','no_time','naive_time'])
def test_unproven_edges_never_notify(damage):
    row=edges('injector')[0]; proof=row['start_evidence']
    if damage=='acceptance_only':proof.clear();proof['accepted_unambiguous']=True
    if damage=='wrong_state':proof['state']='OFF'
    if damage=='wrong_device':proof['device_id']='other'
    if damage=='wrong_channel':proof['channel']=4
    if damage=='no_time':proof.pop('retrieved_at')
    if damage=='naive_time':proof['retrieved_at']='2026-08-05T08:13:00'
    assert transition(row) is None


def test_ambiguous_send_and_restart_never_send_again():
    events=Events(edges('borehole')[:1]);sends=[]
    def send(chat,text,**kwargs):sends.append(text);return {'success':False}
    gateway(events,send)
    gateway(events,send,now=NOW+timedelta(minutes=1))
    # One device attempt and one plan attempt. The same family identities contain both.
    assert len(sends)==2
    assert events.notifications[0]['delivery_ambiguous'] is True


def test_crash_after_family_receipt_before_notification_record_recovers_proof_without_send():
    events=Events(edges('borehole')[:1]);sends=[];original=events.store;crashed=[False]
    def crash(action,payload):
        if action=='record_notification_delivery' and not crashed[0]:
            crashed[0]=True;raise RuntimeError('crash after provider receipt')
        return original(action,payload)
    events.store=crash
    def send(chat,text,**kwargs):sends.append(text);return {'success':True,'telegram_message_id':str(len(sends))}
    gateway(events,send)
    gateway(events,send,now=NOW+timedelta(minutes=1))
    assert len(sends)==2 and events.notifications[-1]['delivery_confirmed'] is True


def test_definitely_unsent_device_attempt_has_only_one_existing_retry():
    events=Events(edges('mixer')[:1]);sends=[]
    def send(chat,text,**kwargs):
        sends.append(text)
        return {'success':False,'delivery_definitely_not_sent':True}
    for i in range(4):gateway(events,send,now=NOW+timedelta(minutes=i))
    device=[x for x in sends if 'Fertilizer mixer' in x]
    assert len(device)==2


def test_two_concurrent_workers_cannot_duplicate_transition_send():
    events=Events(edges('borehole')[:1]);sends=[]
    def send(chat,text,**kwargs):sends.append(text);return {'success':True,'telegram_message_id':str(len(sends))}
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda i:gateway(events,send,now=NOW+timedelta(minutes=i)),range(2)))
    assert len([x for x in sends if 'Borehole supply' in x])==1


def test_expired_optional_budget_never_delivers_or_loads_notifications():
    import time
    with cycle_budget(time.monotonic()-1),pytest.raises(TimeoutError):
        recover_transition_notifications(now=NOW,store=lambda *a:pytest.fail('read after deadline'),
            notify=lambda *a:pytest.fail('send after deadline'))


def test_continuous_borehole_message_has_no_fabricated_stop_or_volume():
    state,row=transition(edges('borehole')[0]);text=compose_transition_notice(state,row)
    assert 'ON verified' in text and 'SAST' in text
    assert not any(word in text.lower() for word in ('litre','water delivered','hour','stop at','completed'))
    assert 'AAN bevestig' in compose_transition_notice(state,row,language='af')


@pytest.mark.parametrize('damage',['both_device_missing','empty_device','both_channel_missing','string_channel','bool_channel','unknown_auxiliary','wrong_binding'])
def test_malformed_identity_never_projects_verified_edge(damage):
    row=edges('injector')[0];proof=row['start_evidence']
    if damage=='both_device_missing':row.pop('device_id');proof.pop('device_id')
    if damage=='empty_device':row['device_id']=proof['device_id']=''
    if damage=='both_channel_missing':row.pop('channel');proof.pop('channel')
    if damage=='string_channel':row['channel']=proof['channel']='1'
    if damage=='bool_channel':row['channel']=proof['channel']=True
    if damage=='unknown_auxiliary':row['auxiliary_device_id']='UNKNOWN'
    if damage=='wrong_binding':row['device_id']=proof['device_id']='unknown-device'
    assert transition(row) is None
