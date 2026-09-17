"""Synthetic conversation handoff regressions; no provider or farm action."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from modules.oom_sakkie import manager_question_runtime as questions
from modules.oom_sakkie import telegram_gateway as gateway
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation

NOW=datetime(2026,9,13,8,0,tzinfo=timezone.utc)
OWNER='990001'
MANAGER='990002'


def _freeze_manager_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (NOW+timedelta(minutes=10)).astimezone(tz or timezone.utc)
    monkeypatch.setattr(questions, 'datetime', Clock)


def setup_question_reply(monkeypatch, *, actor=MANAGER, language='af',
                         specialist_status='preview_ready'):
    _freeze_manager_clock(monkeypatch)
    token='synthetic-dialogue-token-'+'x'*40
    env={'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'1',
        'OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':token,
        'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':OWNER+','+MANAGER,
        'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':OWNER,
        'OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON':json.dumps([{
            'telegram_user_id':MANAGER,'role':'farm_manager','family_key':'dad',
            'permissions':['farm_observation','active_follow_up'],
            'summary_domains':['herd'],'language':'af',
            'authorization_id':'SYNTHETIC-DIALOGUE-AUTH',
            'authorized_by_user_id':OWNER,'authorized_at':'2026-09-01T00:00:00Z'}])}
    text='Hy staan en drink nou.' if language=='af' else 'He is standing and drinking now.'
    question={'daily_identity':'OOM-DAILY-FARM-MANAGER-2026-09-13',
        'telegram_message_id':'700','presented_at':(NOW-timedelta(minutes=5)).isoformat(),
        'question':'Staan en drink die vark nou?' if language=='af' else 'Is the pig standing and drinking now?',
        'question_binding':{'task_id':'SYNTHETIC-WELFARE','dedupe_key':'synthetic-welfare',
            'domain':'herd_health','pig_id':'PIG-TEST-DIALOGUE'}}
    semantic=SemanticInterpretation(domain='herd_health',intent='welfare_follow_up',
        message_kind='observation',continuation=True,observation=text,language=language,confidence=.99)
    answer=('Bevestig die vark se welstandswaarneming.' if language=='af'
        else 'Confirm the pig welfare observation.')
    specialist={'handled':True,'success':True,'status':specialist_status,
        'answer':answer,'tool_used':'herdmaster_health_loss_preview',
        'mission_id':'SYNTHETIC-WELFARE-MISSION','card_mission_id':'SYNTHETIC-WELFARE-CARD',
        'question_count':int(specialist_status=='waiting_for_input'),
        'callback_token':'synthetic-confirmation-token' if specialist_status!='waiting_for_input' else '',
        'reply_markup':{'inline_keyboard':[[{'text':'Bevestig','callback_data':'synthetic-only'}]]},
        'writes_farm_data':False,'hardware_commands':0,'records_audit_trace':True}
    rows={};deliveries=[];bound=[];refreshes=[];health_inputs=[]
    def event_store(identity,record):
        created=identity not in rows
        if created:rows[identity]=record
        return {'success':True,'created':created,'record':rows[identity]}
    def health(parsed,authority):
        health_inputs.append((parsed,authority))
        return dict(specialist),200
    def deliver(parsed,result,**kwargs):
        deliveries.append({'parsed':parsed,'result':result,'kwargs':kwargs})
        return {'success':True,'telegram_message_id':'702','telegram_sends':1,'telegram_edits':0}
    def bind(token,message):
        bound.append((token,message));return True
    def refresh(*args,**kwargs):
        refreshes.append((args,kwargs))
        return {'success':True,'status':'daily_manager_unchanged_silent','telegram_sends':0,'telegram_edits':0}
    monkeypatch.setattr(gateway,'handle_owner_task_input',lambda *a,**k:({'handled':False},200))
    monkeypatch.setattr(gateway,'recover_contextual_specialist_replay',lambda *a,**k:None)
    monkeypatch.setattr(gateway,'handle_protected_action_input',lambda *a,**k:({'handled':False},200))
    monkeypatch.setattr(gateway,'load_active_manager_question',lambda *a,**k:question)
    monkeypatch.setattr(gateway,'interpret_owner_message',lambda *a,**k:semantic)
    monkeypatch.setattr(questions,'manager_question_event_store',event_store)
    monkeypatch.setattr(questions,'_load_manager_question_record',lambda key:rows.get(key,{}))
    monkeypatch.setattr('modules.oom_sakkie.herdmaster_health_loss_runtime.handle_authenticated_health_loss_message',health)
    monkeypatch.setattr('modules.oom_sakkie.morning_runtime.reassess_current_brief_after_owner_answer',refresh)
    monkeypatch.setattr('modules.oom_sakkie.protected_action_claims.bind_claim_card',bind)
    monkeypatch.setattr(gateway,'deliver_family_result',deliver)
    payload={'message':{'message_id':701,'date':int(NOW.timestamp()),'text':text,
        'from':{'id':int(actor)},'chat':{'id':int(actor),'type':'private'},
        'reply_to_message':{'message_id':700}}}
    def invoke():
        return gateway.handle_telegram_gateway_message(payload,
            headers={'Authorization':'Bearer '+token},environ=env)
    return invoke,rows,deliveries,bound,refreshes,health_inputs,specialist


@pytest.mark.parametrize('actor,language',[(OWNER,'en'),(MANAGER,'af')])
@pytest.mark.parametrize('specialist_status',['preview_ready','waiting_for_input'])
def test_plan_reply_preserves_the_specialist_next_step(monkeypatch,actor,language,specialist_status):
    invoke,rows,deliveries,bound,refreshes,health_inputs,specialist=setup_question_reply(
        monkeypatch,actor=actor,language=language,specialist_status=specialist_status)
    result,status=invoke()
    assert status==200
    assert len(rows)==1 and len(health_inputs)==1
    assert health_inputs[0][1].owner_user_id==actor
    assert health_inputs[0][1].principal_role==('owner' if actor==OWNER else 'farm_manager')
    assert result['answer']==specialist['answer']
    assert result['sends_telegram'] is True
    assert len(deliveries)==1 and deliveries[0]['result']['answer']==specialist['answer']
    assert deliveries[0]['kwargs']['specialist']=='HERDMASTER'
    assert deliveries[0]['kwargs']['card_mission_id']=='SYNTHETIC-WELFARE-CARD'
    assert refreshes==[]
    assert bound==([] if specialist_status=='waiting_for_input' else [('synthetic-confirmation-token','702')])
    assert result['message']['writes_farm_data'] is False


def partial_journey(monkeypatch, *, pig=False):
    _freeze_manager_clock(monkeypatch)
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    question={'daily_identity':'OOM-DAILY-FARM-MANAGER-2026-09-13:OWNER:SYNTHETIC',
        'telegram_message_id':'700','presented_at':(NOW-timedelta(minutes=5)).isoformat(),
        'question':'Is the pig eating, standing and drinking?',
        'question_binding':{'task_id':'SYNTHETIC-WELFARE',
            'dedupe_key':'herdmaster:PIG-TEST-DIALOGUE' if pig else 'herdmaster:mortality-current-assessment',
            'domain':'herd',**({'pig_id':'PIG-TEST-DIALOGUE'} if pig else {})}}
    parsed={'text':'He is eating.','telegram_user_id':OWNER,'telegram_chat_id':OWNER,
        'provider_message_id':'701','provider_timestamp':NOW.isoformat(),
        'reply_to_message_id':'700','output_language':'en'}
    semantic=SemanticInterpretation(domain='herd_health',intent='welfare_follow_up',
        message_kind='observation',continuation=True,observation='He is eating.',
        needs_clarification=True,clarification_question='Is he also standing and drinking?',
        language='en',confidence=.99)
    rows={}
    def store(key,record):
        created=key not in rows
        if created:rows[key]=record
        return {'success':True,'created':created,'record':rows[key]}
    monkeypatch.setattr(questions,'manager_question_event_store',store)
    monkeypatch.setattr(questions,'_load_manager_question_record',lambda key:rows.get(key,{}))
    authority=issue_gateway_owner_authority(OWNER,OWNER)
    result,status=questions.handle_manager_question_reply(parsed,authority,semantic,question=question)
    assert status==200 and result['status']=='manager_question_partial_reply_recorded'
    partial=next(iter(rows.values()))
    # This helper represents the clarification after a provider-confirmed send.
    partial={**partial,'clarification_telegram_message_id':'SYNTHETIC-DELIVERED-701',
        'clarification_presented_at':NOW.isoformat()}
    return question,parsed,semantic,authority,rows,partial


def test_interruption_restores_latest_clarification_after_retained_facts(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    context=questions.semantic_context_with_manager_question({**parsed,'provider_message_id':'702',
        'provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()},
        base_context_loader=lambda _: {'recent_turns':[]},
        question={**question,'partial_replies':[partial]})
    turns=context['recent_turns']
    assert partial['clarification_question']==semantic.clarification_question
    assert turns[0]['clarification_question']==question['question']
    assert turns[-2]['observation']=='He is eating.'
    assert turns[-1]['clarification_question']==semantic.clarification_question


def test_late_provider_reply_cannot_complete_a_newer_partial_conversation(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    stale={**parsed,'text':'Yes.','provider_message_id':'699',
        'provider_timestamp':(NOW-timedelta(seconds=1)).isoformat()}
    result,status=questions.handle_manager_question_reply(stale,authority,
        SemanticInterpretation(domain='herd_health',intent='welfare_follow_up',
            message_kind='observation',continuation=True,observation='He is standing and drinking.',
            language='en',confidence=.99),question={**question,'partial_replies':[partial]})
    assert status==409 and result['status']=='manager_question_reply_chronology_conflict'
    assert len(rows)==1


def test_individual_welfare_handoff_preserves_all_facts_and_their_provider_times(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch,pig=True)
    later={**parsed,'text':'Yes.','provider_message_id':'702',
        'provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()}
    captured=[]
    def health(forwarded,actor):
        captured.append(forwarded)
        return {'handled':True,'success':True,'status':'preview_ready',
            'tool_used':'herdmaster_health_loss_preview','answer':'Confirm the observation.',
            'writes_farm_data':False},200
    result,status=questions.handle_manager_question_reply(later,authority,
        SemanticInterpretation(domain='herd_health',intent='welfare_follow_up',
            message_kind='observation',continuation=True,observation='He is standing and drinking.',
            language='en',confidence=.99),question={**question,'partial_replies':[partial]},
        health_handler=health)
    assert status==200 and result['status']=='preview_ready'
    forwarded=captured[0]
    assert forwarded['semantic']['observation']=='He is eating. He is standing and drinking.'
    assert forwarded['semantic']['confidence']==.99
    assert forwarded['semantic']['entity_refs']==['pig:PIG-TEST-DIALOGUE']
    assert forwarded['manager_question_report_parts']==[
        {'text':'He is eating.','provider_timestamp':parsed['provider_timestamp']},
        {'text':'Yes.','provider_timestamp':later['provider_timestamp']}]


def test_actual_completed_group_receipt_retires_only_the_question(monkeypatch):
    from dataclasses import replace
    from modules.oom_sakkie.farm_manager_loop import (Authority,Provenance,
        SpecialistAvailability,SpecialistResult,SpecialistWorkItem,WorkState)
    from modules.oom_sakkie.herdmaster_daily_manager_adapter import reconcile_manager_question_answer
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    later={**parsed,'text':'Yes.','provider_message_id':'702',
        'provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()}
    result,status=questions.handle_manager_question_reply(later,authority,
        SemanticInterpretation(domain='herd_health',intent='welfare_follow_up',
            message_kind='observation',continuation=True,observation='He is standing and drinking.',
            language='en',confidence=.99),question={**question,'partial_replies':[partial]})
    assert status==200
    receipt=[row for row in rows.values() if row['status']=='recorded'][0]
    item=SpecialistWorkItem(item_id=question['question_binding']['task_id'],
        dedupe_key=question['question_binding']['dedupe_key'],domain='herd',title='Welfare check',
        why='A check is open.',next_action='Retain the open welfare follow-up.',
        assignee='charl',state=WorkState.WAITING_EVIDENCE,authority=Authority.ADVISORY,
        provenance=Provenance('herdmaster','SYNTHETIC-RESULT',('synthetic',),NOW,1.0),
        genuine_question=question['question'],question_for='charl')
    current=SpecialistResult('herdmaster','SYNTHETIC-RESULT',NOW,
        SpecialistAvailability.AVAILABLE,work_items=(item,))
    reconciled=reconcile_manager_question_answer(current,receipt)
    assert reconciled.work_items==(replace(item,genuine_question='',question_for=''),)
    assert reconcile_manager_question_answer(current,partial)==current
    assert reconcile_manager_question_answer(current,{**receipt,'dedupe_key':'another-concern'})==current
