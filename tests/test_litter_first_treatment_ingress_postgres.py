"""Real ingress, semantic parsing, claims, services and delivery persistence.

Only identity credentials, the LLM response and Telegram HTTP provider replies
are simulated. This is terminal-invoked qualification, not a genuine farm run.
"""
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import time
import uuid
from zoneinfo import ZoneInfo

import psycopg
import pytest

from app import app
from modules.oom_sakkie import semantic_front_door, telegram_direct, telegram_gateway
from modules.oom_sakkie.herdmaster_litter_first_treatment_runtime import load_first_treatment_context
from modules.sales import sam_live_stock_launch_control
from tests.first_treatment_test_support import database_url, seed, cleanup, facts, payload, state


@pytest.fixture
def ingress(monkeypatch):
    j = seed()
    actor = str(7300000000 + int(uuid.uuid4().hex[:7], 16))
    token = 'SYNTHETIC-first_treatment-gateway-' + 'g' * 40
    values = {'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':'990000',
        'OOM_SAKKIE_TELEGRAM_BOT_TOKEN':'SYNTHETIC-first_treatment-bot',
        'OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON':json.dumps([{'telegram_user_id':actor,
            'family_key':'dad','role':'farm_manager','permissions':['farm_observation','treatment'],
            'summary_domains':['herd'],'language':'af','authorization_id':'SYNTHETIC-FIRST-TREATMENT-ONLY',
            'authorized_by_user_id':'990000','authorized_at':'2026-09-01T00:00:00+02:00'}]),
        'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'true','OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':token,
        'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':actor+',990000',
        'OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED':'true','OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED':'true',
        'OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET':token,'OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED':'true',
        'OOM_SAKKIE_LLM_ROUTER_MODEL':'SIMULATED-local','OPENAI_API_KEY':'SIMULATED-no-provider-key'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    deliveries = []
    def provider(_token, method, body, **kwargs):
        assert _token == 'SYNTHETIC-first_treatment-bot'
        assert method in ('sendMessage', 'editMessageText')
        message_id = str(body.get('message_id') or (j.get('message_sequence', 1000) + 1))
        j['message_sequence'] = max(j.get('message_sequence', 1000), int(message_id))
        deliveries.append({'method': method, 'body': body, 'message_id': message_id})
        return {'ok': True, 'result': {'message_id': message_id, 'date': int(time.time()),
            'chat': {'id': int(actor), 'type': 'private'}, 'text': body['text']}}
    monkeypatch.setattr(sam_live_stock_launch_control, '_telegram_api', provider)
    monkeypatch.setattr(telegram_direct, 'acknowledge_telegram_callback',
        lambda *args, **kwargs: ({'success':True,'status':'SIMULATED-provider-ack'},200))
    j.update(actor=actor, token=token, deliveries=deliveries, client=app.test_client())
    yield j
    cleanup(j)


def semantic(monkeypatch, facts=None, **extra):
    envelope = {'domain':'herd_management', 'intent':'record_litter_first_treatment', 'message_kind':'observation',
        'confidence':0.99, 'language':'af', 'litter_first_treatment':facts, **extra}
    body = json.dumps({'choices':[{'message':{'content':json.dumps(envelope)}}]})
    interpreted = semantic_front_door.parse_semantic_response(body)
    assert interpreted is not None
    monkeypatch.setattr(telegram_gateway, 'interpret_owner_message', lambda *args, **kwargs: interpreted)
    monkeypatch.setattr(semantic_front_door, 'interpret_owner_message', lambda *args, **kwargs: interpreted)
    return interpreted


def post(j, transport, text='', *, envelope=None, reply='', stamp=None, bad_auth=False):
    if envelope is None:
        j['message_sequence'] = j.get('message_sequence', 1000) + 1
        envelope = {'message': {'message_id': j['message_sequence'],
            'date': stamp or int(time.time()), 'from': {'id': int(j['actor'])},
            'chat': {'id': int(j['actor']), 'type':'private'}, 'text': text}}
        if reply:
            envelope['message']['reply_to_message'] = {'message_id': reply}
    path = '/api/oom-sakkie/channels/telegram/message' if transport == 'gateway' else '/api/oom-sakkie/channels/telegram/direct-webhook'
    headers = {'Authorization': 'Bearer ' + j['token']} if transport == 'gateway' else {'X-Telegram-Bot-Api-Secret-Token': j['token']}
    if bad_auth:
        headers = {key:'wrong' for key in headers}
    response = j['client'].post(path, json=envelope, headers=headers)
    return response, envelope


def action(response):
    body = response.get_json()
    return body.get('message') or body.get('protected_action') or body


def callback(j, preview, callback_id=None):
    return {'callback_query': {'id':callback_id or 'SIMULATED-CB-'+uuid.uuid4().hex,
        'from':{'id':int(j['actor'])}, 'data':preview['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message':{'message_id':j['deliveries'][-1]['message_id'],'date':int(time.time()),
            'chat':{'id':int(j['actor']),'type':'private'},'text':'SIMULATED preview card'}}}


@pytest.mark.parametrize('transport',['gateway','direct'])
@pytest.mark.parametrize('words',[
    'Ek het die werpsel gister vir die eerste keer behandel: 1 ml per varkie, gemerk, een manlik en een vroulik.',
    'I gave the current litter its first treatment yesterday, one ml each, earmarked, one male and one female.',
])
def test_actual_ingress_provider_delivery_and_canonical_readback_once(ingress,monkeypatch,transport,words):
    j = ingress
    semantic(monkeypatch,facts(j,action_date='gister'))
    before = state(j)
    rejected,_ = post(j,transport,words,bad_auth=True)
    assert rejected.status_code == 403 and state(j) == before
    response, original = post(j,transport,words)
    result = action(response)
    assert response.status_code == 200 and result['status'] == 'litter_first_treatment_preview_ready',response.get_json()
    assert state(j) == before and len(j['deliveries']) == 1
    text = j['deliveries'][-1]['body']['text']
    assert all(value in text for value in (j['litter'],j['date'],'1.0 ml','1 manlik','1 vroulik','Oormerke aangebring: ja','SYNTHETIC-LOT'))
    repeated,_ = post(j,transport,envelope=original)
    assert repeated.status_code == 200 and len(j['deliveries']) == 1, repeated.get_json()
    envelope = callback(j,result)
    foreign = copy.deepcopy(envelope)
    foreign['callback_query']['from']['id'] = 990000
    foreign['callback_query']['message']['chat']['id'] = 990000
    rejected,_ = post(j,transport,envelope=foreign)
    assert rejected.status_code == 403 and state(j) == before,rejected.get_json()
    confirmed,_ = post(j,transport,envelope=envelope)
    completed = action(confirmed)
    assert confirmed.status_code == 200 and completed['canonical_readback_verified'],confirmed.get_json().get('delivery')
    after = state(j)
    assert len(after['receipts']) == 1 and len(after['medical']) == 2
    assert all(row[6] == j['actor'] and float(row[3]) == 1 for row in after['medical'])
    assert after['sow'] == before['sow'] and after['litter'] == before['litter'] and after['pigs'][2:] == before['pigs'][2:]
    assert 'Eerste behandeling is gestoor en teruggelees' in j['deliveries'][-1]['body']['text']
    assert j['deliveries'][-1]['body']['reply_markup'] == {'inline_keyboard':[]}
    deliveries = len(j['deliveries'])
    repeated,_ = post(j,transport,envelope=envelope)
    assert repeated.status_code == 200 and state(j) == after,repeated.get_json()
    assert len(j['deliveries']) == deliveries,repeated.get_json()['delivery']


@pytest.mark.parametrize('transport',['gateway','direct'])
def test_retained_short_corrections_and_natural_confirmation_without_reply(ingress,monkeypatch,transport):
    j = ingress
    supplied = facts(j)
    supplied.pop('action_date'); supplied.pop('route')
    semantic(monkeypatch,supplied)
    response,_ = post(j,transport,'Eerste behandeling gedoen. Een ml, lot SYNTHETIC-LOT. Een van elke geslag, gemerk.')
    first = action(response)
    assert response.status_code == 200 and first['question_count'] == 1 and 'datum' in first['answer']
    semantic(monkeypatch,{'action_date':'2099-01-01'},continuation=True,message_kind='correction')
    response,_ = post(j,transport,'Op 1 Januarie 2099.')
    assert action(response)['question_count'] == 1 and 'datum' in action(response)['answer']
    semantic(monkeypatch,{'action_date':'gister'},continuation=True,message_kind='correction')
    response,_ = post(j,transport,'Ekskuus, gister.')
    assert 'toedieningsroete' in action(response)['answer'] and action(response)['retained_facts']['dose'] == '1 ml'
    semantic(monkeypatch,{'route':'injection','dose':'1,5 ml'},continuation=True,message_kind='correction')
    response,_ = post(j,transport,'Ingespuit, en die dosis was eintlik 1,5 ml.')
    proposed = action(response)
    assert proposed['status'] == 'litter_first_treatment_preview_ready',response.get_json()
    assert proposed['retained_facts']['earmarked'] is True and proposed['retained_facts']['action_date'] == j['date']
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    response,confirm = post(j,transport,'Ja, daardie presiese besonderhede is reg; teken dit so aan.')
    assert response.status_code == 200 and action(response)['canonical_readback_verified'],response.get_json().get('delivery')
    after = state(j)
    assert all(float(row[3]) == 1.5 for row in after['medical'])
    deliveries = len(j['deliveries'])
    response,_ = post(j,transport,envelope=confirm)
    assert response.status_code == 200 and state(j) == after and len(j['deliveries']) == deliveries,response.get_json()


@pytest.mark.parametrize('transport',['gateway','direct'])
def test_delayed_replyless_consent_cannot_confirm_a_later_correction(ingress,monkeypatch,transport):
    j = ingress
    semantic(monkeypatch,facts(j,notes='Actual English treatment notes must remain exact.'))
    response,_ = post(j,transport,'Die eerste behandeling is gedoen.')
    assert action(response)['callback_token']
    assert 'Actual English treatment notes must remain exact.' in j['deliveries'][-1]['body']['text']
    j['message_sequence'] += 1
    delayed = {'message':{'message_id':j['message_sequence'],'date':int(time.time()),
        'from':{'id':int(j['actor'])},'chat':{'id':int(j['actor']),'type':'private'},'text':'Ja, teken daardie feite aan.'}}
    semantic(monkeypatch,{'dose':'1,5 ml'},continuation=True,message_kind='correction')
    response,_ = post(j,transport,'Korreksie: die dosis was 1,5 ml.')
    latest = action(response)
    assert latest['callback_token'] and '1.5 ml' in latest['answer']
    before = state(j)
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    response,_ = post(j,transport,envelope=delayed)
    assert not action(response).get('writes_farm_data') and state(j) == before,response.get_json()
    with psycopg.connect(database_url()) as db:
        assert db.execute('select status from app_private.oom_protected_action_claims where callback_token=%s',
            (latest['callback_token'],)).fetchone()[0] == 'active'
    response,_ = post(j,transport,'Ja, die nuutste voorskou met 1,5 ml is presies reg.')
    assert response.status_code == 200 and action(response)['canonical_readback_verified'],response.get_json()
    assert all(float(row[3]) == 1.5 for row in state(j)['medical'])


@pytest.mark.parametrize('transport',['gateway','direct'])
def test_completion_failure_after_real_commit_recovers_on_same_provider_id(ingress,monkeypatch,transport):
    from modules.oom_sakkie import protected_action_runtime
    j = ingress
    semantic(monkeypatch,facts(j))
    response,_ = post(j,transport,'Die eerste behandeling is gedoen met die opgegewe feite.')
    envelope = callback(j,action(response))
    real = protected_action_runtime.complete_claim
    with monkeypatch.context() as patch:
        patch.setattr(protected_action_runtime,'complete_claim',lambda *args,**kwargs: (_ for _ in ()).throw(ConnectionError('SIMULATED interruption after farm commit')))
        response,_ = post(j,transport,envelope=envelope)
    assert response.status_code == 503 and action(response)['operation_committed'],response.get_json()
    after = state(j)
    assert len(after['medical']) == 2 and len(after['receipts']) == 1
    response,_ = post(j,transport,envelope=envelope)
    assert response.status_code == 200 and action(response)['canonical_readback_verified'],response.get_json()
    assert state(j) == after


@pytest.mark.parametrize('transport',['gateway','direct'])
def test_provider_completion_failure_recovers_without_reapplying(ingress,monkeypatch,transport):
    j = ingress
    semantic(monkeypatch,facts(j))
    response,_ = post(j,transport,'Die eerste behandeling is gedoen.')
    envelope = callback(j,action(response))
    with monkeypatch.context() as patch:
        patch.setattr(sam_live_stock_launch_control,'_telegram_api',lambda *args,**kwargs:{'ok':False,'error_code':503,'description':'SIMULATED unavailable'})
        response,_ = post(j,transport,envelope=envelope)
    assert response.status_code in (202,503),response.get_json()
    after = state(j)
    assert len(after['receipts']) == 1
    response,_ = post(j,transport,envelope=envelope)
    assert response.status_code == 200 and action(response)['canonical_readback_verified'],response.get_json()
    assert state(j) == after and 'gestoor en teruggelees' in j['deliveries'][-1]['body']['text']


@pytest.mark.parametrize('transport',['gateway','direct'])
def test_configured_english_and_nonprivate_authority(ingress,monkeypatch,transport):
    import os
    j = ingress
    binding = json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON'])
    binding[0]['language'] = 'en'
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON',json.dumps(binding))
    semantic(monkeypatch,facts(j))
    response,envelope = post(j,transport,'I administered the first treatment with the reported facts.')
    assert response.status_code == 200 and action(response)['recipient_language'] == 'en',response.get_json()
    assert 'Actually treated' in j['deliveries'][-1]['body']['text'] and 'Reported tally' in j['deliveries'][-1]['body']['text']
    envelope['message']['chat'] = {'id':-999999,'type':'group'}
    before = state(j)
    response,_ = post(j,transport,envelope=envelope)
    assert not action(response).get('writes_farm_data') and state(j) == before,response.get_json()


def app_headers(j):
    import os
    import re
    from tests.first_treatment_test_support import login
    response = login(j['client'],j['actor'],os.environ['OOM_SAKKIE_TELEGRAM_BOT_TOKEN'])
    assert response.status_code == 200,response.get_json()
    page = j['client'].get('/litter/'+j['litter'])
    assert page.status_code == 200
    csrf = re.search(r'data-treatment-csrf="([^"]+)"',page.get_data(as_text=True)).group(1)
    return {'X-Treatment-CSRF':csrf}


def test_actual_app_server_actor_exact_confirmation_and_separate_weaning_permission(ingress):
    j = ingress
    before = state(j)
    route = '/api/pig-weights/litter/'+j['litter']+'/newborn-health'
    p = payload(j,changed_by='forged-client-actor')
    p['action_date'] = p.pop('action_date_value')
    assert j['client'].post(route,json=p).status_code == 403
    headers = app_headers(j)
    assert j['client'].post(route,json=p).status_code == 403
    assert j['client'].post(route,json=[],headers=headers).status_code == 400
    response = j['client'].post(route,json=p,headers=headers)
    assert response.status_code == 200,response.get_json()
    preview = response.get_json()
    assert preview['preview']['principal'] == j['actor'] and state(j) == before
    confirmed = {**p,'dry_run':False,'confirmed':True,'confirmation_binding':preview['confirmation_binding']}
    tampered = copy.deepcopy(confirmed); tampered['dose'] = '2 ml'
    assert j['client'].post(route,json=tampered,headers=headers).status_code == 409
    assert j['client'].post('/api/pig-weights/litter/'+j['litter']+'/weaning-day',json={'dry_run':True},headers=headers).status_code == 403
    response = j['client'].post(route,json=confirmed,headers=headers)
    assert response.status_code == 200 and response.get_json()['canonical_readback_verified'],response.get_json()
    after = state(j)
    assert all(row[6] == j['actor'] for row in after['medical'])
    response = j['client'].post(route,json=confirmed,headers=headers)
    assert response.status_code == 200 and response.get_json()['replay_withheld'] and state(j) == after


def test_app_cross_actor_binding_and_explicit_skip_guard(ingress,monkeypatch):
    import os
    j = ingress
    headers = app_headers(j)
    route = '/api/pig-weights/litter/'+j['litter']+'/newborn-health'
    p = payload(j); p['action_date'] = p.pop('action_date_value')
    response = j['client'].post(route,json=p,headers=headers)
    assert response.status_code == 200
    confirmed = {**p,'dry_run':False,'confirmed':True,'confirmation_binding':response.get_json()['confirmation_binding']}
    bindings = json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON'])
    j['actor'] = str(int(j['actor']) + 1000000000)
    bindings[0]['telegram_user_id'] = j['actor']
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON',json.dumps(bindings))
    headers = app_headers(j)
    before = state(j)
    assert j['client'].post(route,json=confirmed,headers=headers).status_code == 409
    assert state(j) == before
    skip_route = '/api/pig-weights/litter/'+j['litter']+'/first-treatment/skip'
    assert j['client'].post(skip_route,json={},headers=headers).status_code == 409
    result = j['client'].post(skip_route,json={'confirmed':True,'changed_by':'forged'},headers=headers)
    assert result.status_code == 200,result.get_json()
    from modules.pig_weights.farm_supabase_read_service import get_litter_detail
    detail = get_litter_detail(j['litter'])
    assert detail['first_treatment_skipped_by'] == j['actor'] and not state(j)['medical']
