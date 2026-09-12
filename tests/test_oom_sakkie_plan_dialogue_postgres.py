"""Synthetic plan conversations using real PostgreSQL, gateway and farm services.

Only semantic-model output and Telegram transport are simulated. No live send.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import uuid
from urllib.parse import urlparse

import psycopg
import pytest

from modules.oom_sakkie import daily_farm_manager as daily
from modules.oom_sakkie import manager_question_runtime as questions
from modules.oom_sakkie import telegram_gateway as gateway
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie.farm_manager_loop import (Authority, Provenance,
    SpecialistAvailability, SpecialistResult, SpecialistWorkItem, WorkState)
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation

DSN=os.environ.get('CHARLIE_DISPOSABLE_POSTGRES_URL','')
pytestmark=pytest.mark.skipif(not DSN,reason='explicit disposable PostgreSQL required')
NOW=datetime(2026,9,12,8,0,tzinfo=timezone.utc)


@pytest.fixture
def journey(monkeypatch):
    url=urlparse(DSN)
    assert url.hostname in {'127.0.0.1','localhost'} and 'test' in url.path
    owner=str(9000000000+int(uuid.uuid4().hex[:7],16))
    actor=str(int(owner)+1)
    pig='PIG-2026-'+uuid.uuid4().hex[:4].upper()
    tag='DIALOGUE-'+uuid.uuid4().hex[:8].upper()
    pen='PEN-'+uuid.uuid4().hex
    token='synthetic-dialogue-gateway-'+'x'*40
    env={'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'1',
        'OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':token,
        'OOM_SAKKIE_TELEGRAM_BOT_TOKEN':'synthetic-dialogue-bot-token',
        'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':owner+','+actor,
        'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':owner,
        'OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON':json.dumps([{
            'telegram_user_id':actor,'family_key':'dad','role':'farm_manager',
            'permissions':['farm_observation','active_follow_up'],
            'summary_domains':['herd'],'language':'af',
            'authorization_id':'SYNTHETIC-DIALOGUE','authorized_by_user_id':owner,
            'authorized_at':'2026-09-01T00:00:00Z'}])}
    for key,value in env.items():monkeypatch.setenv(key,value)
    with psycopg.connect(DSN) as db:
        db.execute('insert into public.pens(pen_id,pen_name) values(%s,%s)',(pen,'Synthetic dialogue pen'))
        db.execute('''insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,
            initial_pen_id,purpose,date_of_birth,notes)
            values(%s,%s,'Synthetic dialogue animal','Active',true,%s,'Sale','2026-01-01',
                   'Preserve prior farm history')''',(pig,tag,pen))
    provider=[];provider_clock=[NOW]
    def telegram_api(_token,method,body):
        provider.append({'method':method,'body':dict(body)})
        if method in {'deleteMessage','answerCallbackQuery'}:return {'ok':True,'result':True}
        assert method in {'sendMessage','editMessageText','editMessageReplyMarkup'},method
        message=str(body.get('message_id') or 1000+len(provider))
        return {'ok':True,'result':{'message_id':message,
            'date':int(provider_clock[0].timestamp()),'edit_date':int(provider_clock[0].timestamp())}}
    monkeypatch.setattr('modules.sales.sam_live_stock_launch_control._telegram_api',telegram_api)
    semantic_contexts=[]
    semantic_holder={}
    def interpret(parsed,**kwargs):
        loader=kwargs.get('context_loader')
        if loader:semantic_contexts.append(loader(parsed))
        return semantic_holder['value']
    monkeypatch.setattr(gateway,'interpret_owner_message',interpret)
    return {'owner':owner,'actor':actor,'pig':pig,'tag':tag,'token':token,
        'provider':provider,'provider_clock':provider_clock,'semantic':semantic_holder,'contexts':semantic_contexts}


def work(j,language,*,individual=False):
    af=language=='af'
    item=SpecialistWorkItem(item_id='SYNTHETIC-QUESTION-'+j['pig'],
        dedupe_key='herdmaster:'+j['pig'] if individual else 'synthetic-group:'+j['pig'],
        domain='herd',title='Welstandskontrole' if af else 'Welfare check',
        why='Die welstandskontrole is oop.' if af else 'The welfare check is open.',
        next_action='Gaan die waarneming na.' if af else 'Check the observation.',
        assignee='charl',state=WorkState.WAITING_EVIDENCE,authority=Authority.ADVISORY,
        provenance=Provenance('herdmaster','SYNTHETIC-RESULT-'+j['pig'],
            ('pig:'+j['pig'],) if individual else ('synthetic-group',),NOW,1.0),
        genuine_question='Eet, staan en drink hy nou?' if af else 'Is he eating, standing and drinking now?',
        question_for='charl')
    return SpecialistResult('herdmaster','SYNTHETIC-RESULT-'+j['pig'],NOW,
        SpecialistAvailability.AVAILABLE,work_items=(item,))


def present(j,actor,language,*,individual=False):
    result=work(j,language,individual=individual)
    value=daily.run_daily_farm_manager(owner_user_id=actor,chat_id=actor,
        specialist_results=[result],litter_rows=[],deliver=family.deliver_family_result,
        now=NOW,language=language)
    assert value['success'] and value['status']=='daily_manager_presented',value
    rows=questions._load_questions(actor,actor)
    assert len(rows)==1 and rows[0]['question']==result.work_items[0].genuine_question,rows
    return result,rows[0]


def reply(j,actor,language,text,message,at,card,*,partial=False,clinical=False):
    j['provider_clock'][0]=at
    af=language=='af'
    j['semantic']['value']=SemanticInterpretation(domain='herd_health',intent='welfare_follow_up',
        message_kind='observation',continuation=True,
        observation=('Hy eet.' if af else 'He is eating.') if partial else
                    ('Hy staan en drink water.' if af else 'He is standing and drinking water.'),
        welfare_observation={'eating':'yes'} if partial else {'standing':'yes','drinking':'yes',
            **({'breathing':'yes'} if clinical else {})},
        clinical_observation={'bleeding':'yes'} if partial and clinical else None,
        needs_clarification=partial,
        clarification_question=(('Staan hy, drink hy water en haal hy normaal asem?' if af else
            'Is he standing, drinking water and breathing normally?') if clinical else
            ('Staan hy ook en drink hy water?' if af else 'Is he also standing and drinking water?')) if partial else '',
        language=language,confidence=.99)
    payload={'message':{'message_id':message,'date':int(at.timestamp()),'text':text,
        'from':{'id':int(actor)},'chat':{'id':int(actor),'type':'private'},
        'reply_to_message':{'message_id':int(card)}}}
    return gateway.handle_telegram_gateway_message(payload,
        headers={'Authorization':'Bearer '+j['token']},environ=os.environ)


@pytest.mark.parametrize('language',['en','af'])
def test_group_plan_partial_restart_answer_retirement_and_next_cycle(journey,language):
    j=journey;actor=j['actor'] if language=='af' else j['owner']
    result,question=present(j,actor,language)
    partial,status=reply(j,actor,language,'Hy eet.' if language=='af' else 'He is eating.',
        701,NOW+timedelta(minutes=1),question['telegram_message_id'],partial=True)
    assert status==200 and partial['status']=='manager_question_partial_reply_recorded',partial
    assert j['provider'][-1]['body']['text']==j['semantic']['value'].clarification_question
    delivered_count=len(j['provider'])
    duplicate,status=reply(j,actor,language,'Hy eet.' if language=='af' else 'He is eating.',
        701,NOW+timedelta(minutes=1),question['telegram_message_id'],partial=True)
    assert status==200 and len(j['provider'])==delivered_count,duplicate
    partial_card=partial['delivery']['telegram_message_id']
    reloaded=questions._load_questions(actor,actor)
    assert len(reloaded)==1 and len(reloaded[0]['partial_replies'])==1
    assert reloaded[0]['partial_replies'][0]['clarification_presented_at']
    assert reloaded[0]['partial_replies'][0]['clarification_question']==j['semantic']['value'].clarification_question
    # Reply to the question actually delivered after the partial answer.
    complete,status=reply(j,actor,language,'Ja.' if language=='af' else 'Yes.',
        702,NOW+timedelta(minutes=2),partial_card)
    assert status==200 and complete['message']['status']=='manager_question_reply_recorded',complete
    assert j['contexts'][-1]['recent_turns'][-1]['clarification_question']==reloaded[0]['partial_replies'][0]['clarification_question']
    delivered_count=len(j['provider'])
    duplicate,status=reply(j,actor,language,'Ja.' if language=='af' else 'Yes.',
        702,NOW+timedelta(minutes=2),partial_card)
    assert status==200 and len(j['provider'])==delivered_count,duplicate
    assert questions._load_questions(actor,actor)==[]
    receipts=daily._load_answered_questions({'owner_user_id':actor,'chat_id':actor,
        'daily_identity':question['daily_identity']})
    assert len(receipts)==1 and len(receipts[0]['accumulated_semantic_facts']['observations'])==2
    retired=daily._retire_answered_questions([result],receipts)[0]
    assert retired.work_items==(replace(result.work_items[0],genuine_question='',question_for=''),)
    assert daily._load_answered_questions({'owner_user_id':j['owner'] if language=='af' else j['actor'],
        'chat_id':j['owner'] if language=='af' else j['actor']})==()
    current=daily.run_daily_farm_manager(owner_user_id=actor,chat_id=actor,
        specialist_results=[result],litter_rows=[],deliver=family.deliver_family_result,
        now=NOW+timedelta(minutes=5),language=language)
    assert current['success'],current
    delivered_count=len(j['provider'])
    unchanged=daily.run_daily_farm_manager(owner_user_id=actor,chat_id=actor,
        specialist_results=[result],litter_rows=[],deliver=family.deliver_family_result,
        now=NOW+timedelta(minutes=10),language=language)
    assert unchanged['status']=='daily_manager_unchanged_silent'
    assert len(j['provider'])==delivered_count
    with psycopg.connect(DSN) as db:
        assert db.execute('select count(*) from public.pig_observation_events where pig_id=%s',(j['pig'],)).fetchone()[0]==0


@pytest.mark.parametrize('language',['en','af'])
@pytest.mark.parametrize('fault',['none','manager_receipt','claim_binding'])
@pytest.mark.parametrize('clinical',[False,True])
def test_individual_plan_partial_restart_reaches_real_bound_welfare_preview(journey,language,monkeypatch,fault,clinical):
    j=journey;actor=j['actor'] if language=='af' else j['owner']
    _,question=present(j,actor,language,individual=True)
    original=('Hy bloei, maar hy eet.' if language=='af' else 'He is bleeding, but he is eating.') if clinical else (
        'Hy eet.' if language=='af' else 'He is eating.')
    partial,status=reply(j,actor,language,original,
        701,NOW+timedelta(minutes=1),question['telegram_message_id'],partial=True,clinical=clinical)
    assert status==200,partial
    if clinical:
        assert ('Dringend:' if language=='af' else 'Physically assess') in partial['answer']
        assert partial['message']['question_count']==1
    sent=len(j['provider'])
    partial_replay,replay_status=reply(j,actor,language,original,
        701,NOW+timedelta(minutes=1),question['telegram_message_id'],partial=True,clinical=clinical)
    assert replay_status==200 and partial_replay['answer']==partial['answer']
    assert len(j['provider'])==sent
    failures=[]
    if fault=='manager_receipt':
        real_store=questions.manager_question_event_store
        def fail_once(event_id,record):
            if record.get('status')=='recorded' and not failures:
                failures.append(event_id)
                return {'success':False,'status':'synthetic_receipt_interruption'}
            return real_store(event_id,record)
        monkeypatch.setattr(questions,'manager_question_event_store',fail_once)
    elif fault=='claim_binding':
        from modules.oom_sakkie import protected_action_claims as claims
        real_bind=claims.bind_claim_card
        def fail_once(*args,**kwargs):
            if not failures:
                failures.append('claim_binding')
                return False
            return real_bind(*args,**kwargs)
        monkeypatch.setattr(claims,'bind_claim_card',fail_once)
    complete,status=reply(j,actor,language,'Ja.' if language=='af' else 'Yes.',
        702,NOW+timedelta(minutes=2),partial['delivery']['telegram_message_id'],clinical=clinical)
    if fault!='none':
        assert status in {202,503} and len(failures)==1,complete
        if fault=='manager_receipt':
            with psycopg.connect(DSN) as db:
                retained=db.execute('''select callback_token,preview_digest,expires_at from
                    app_private.oom_protected_action_claims where owner_user_id=%s''',(actor,)).fetchall()
                assert len(retained)==1
        sends_before=len(j['provider'])
        complete,status=reply(j,actor,language,'Ja.' if language=='af' else 'Yes.',
            702,NOW+timedelta(minutes=2),partial['delivery']['telegram_message_id'],clinical=clinical)
        if fault=='claim_binding':
            assert len(j['provider'])==sends_before,complete
        else:
            with psycopg.connect(DSN) as db:
                assert db.execute('''select callback_token,preview_digest,expires_at from
                    app_private.oom_protected_action_claims where owner_user_id=%s''',(actor,)).fetchall()==retained
    assert status==200 and complete['status']=='preview_ready',json.dumps(complete,ensure_ascii=True)
    assert complete['answer'] and complete['delivery']['delivery_confirmed']
    assert complete['sends_telegram'] is (fault!='claim_binding')
    assert complete['message']['callback_token']
    expected_words=('eet: Ja','staan: Ja','drink water: Ja') if language=='af' else (
        'eating reported: Yes','standing reported: Yes','drinking reported: Yes')
    assert all(word in j['provider'][-1]['body']['text'] for word in expected_words)
    if clinical:
        assert ('bloei: Ja' if language=='af' else 'bleeding: Yes') in complete['answer']
        assert ('Dringend:' if language=='af' else 'Physically assess') in complete['answer']
    delivered_count=len(j['provider'])
    duplicate,status=reply(j,actor,language,'Ja.' if language=='af' else 'Yes.',
        702,NOW+timedelta(minutes=2),partial['delivery']['telegram_message_id'],clinical=clinical)
    assert status==200 and len(j['provider'])==delivered_count,duplicate
    with psycopg.connect(DSN) as db:
        assert db.execute('select count(*) from public.pig_observation_events where pig_id=%s',(j['pig'],)).fetchone()[0]==0
        claim=db.execute('''select owner_user_id,private_chat_id,preview_card_message_id,status
            from app_private.oom_protected_action_claims where callback_token=%s''',
            (complete['message']['callback_token'],)).fetchone()
        assert claim[:3]==(actor,actor,complete['delivery']['telegram_message_id']),claim
    callback={'callback_query':{'id':'SYNTHETIC-CALLBACK-'+uuid.uuid4().hex,
        'from':{'id':int(actor)},'data':complete['message']['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message':{'message_id':complete['delivery']['telegram_message_id'],
            'date':int((NOW+timedelta(minutes=3)).timestamp()),'text':'Synthetic preview',
            'chat':{'id':int(actor),'type':'private'}}}}
    confirmed,status=gateway.handle_telegram_gateway_message(callback,
        headers={'Authorization':'Bearer '+j['token']},environ=os.environ)
    assert status==201 and confirmed['message']['success'],json.dumps(confirmed,default=str)
    assert 'death' not in confirmed['answer'].lower() and 'dood' not in confirmed['answer'].lower()
    completed_answer=confirmed['answer']
    replay,status=gateway.handle_telegram_gateway_message(callback,
        headers={'Authorization':'Bearer '+j['token']},environ=os.environ)
    assert status==200,json.dumps(replay,default=str)
    assert replay['answer']==completed_answer
    with psycopg.connect(DSN) as db:
        observations=db.execute('''select observer_reference,measurements_json
            from public.pig_observation_events where pig_id=%s''',(j['pig'],)).fetchall()
        assert len(observations)==1 and observations[0][0]==actor
        observed={row['fact']:row['value'] for row in observations[0][1]['observed']}
        assert observed['eating_reported'] and observed['standing_reported'] and observed['drinking_reported']
        if clinical:
            assert observed['bleeding'] and observed['breathing_reported']
            assert observations[0][1]['reviewed_event_family']=='injured'
        assert observations[0][1]['owner_report_parts'][0]['text']==original
        assert db.execute('select status,on_farm,notes from public.pigs where pig_id=%s',
            (j['pig'],)).fetchone()==('Active',True,'Preserve prior farm history')
    from modules.pig_weights.pig_weights_controller import get_pig_profile
    application_readback,status=get_pig_profile(j['pig'])
    assert status==200 and application_readback['pig']['pig_id']==j['pig'],application_readback
    from flask import Flask
    from modules.pig_weights.pig_weights_routes import pig_weights_bp
    from modules.auth.owner_access import configure_owner_access,telegram_farm_login_post
    import hashlib,hmac,time
    from urllib.parse import urlencode
    application=Flask(__name__);configure_owner_access(application)
    application.register_blueprint(pig_weights_bp,url_prefix='/api/pig-weights')
    application.add_url_rule('/owner/telegram/login',view_func=telegram_farm_login_post,methods=['POST'])
    client=application.test_client()
    path='/api/pig-weights/pig/'+j['pig']+'/welfare-observations'
    assert client.get(path).status_code==403
    fields={'auth_date':str(int(time.time())),'user':json.dumps({'id':int(actor)})}
    key=hmac.new(b'WebAppData',os.environ['OOM_SAKKIE_TELEGRAM_BOT_TOKEN'].encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(key,'\n'.join(f'{key}={fields[key]}' for key in sorted(fields)).encode(),hashlib.sha256).hexdigest()
    login=client.post('/owner/telegram/login',json={'init_data':urlencode(fields)},
        headers={'X-Farm-Login':'telegram'})
    assert login.status_code==200,login.get_json()
    response=client.get(path)
    assert response.status_code==200,response.get_json()
    history=response.get_json()['history']
    assert len(history)==1 and history[0]['observed']==observations[0][1]['observed']
    assert history[0]['owner_report_parts'][0]['text']==original
    assert response.get_json()['writes_farm_data'] is False
