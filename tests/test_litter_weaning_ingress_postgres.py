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
from modules.oom_sakkie.herdmaster_litter_weaning_runtime import load_weaning_context
from modules.sales import sam_live_stock_launch_control
from tests.weaning_test_support import database_url, seed, state


@pytest.fixture
def ingress(monkeypatch):
    j = seed()
    actor = str(7300000000 + int(uuid.uuid4().hex[:7], 16))
    token = 'SYNTHETIC-weaning-gateway-' + 'g' * 40
    values = {'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':'990000',
        'OOM_SAKKIE_TELEGRAM_BOT_TOKEN':'SYNTHETIC-weaning-bot',
        'OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON':json.dumps([{'telegram_user_id':actor,
            'family_key':'dad','role':'farm_manager','permissions':['farm_observation','weaning'],
            'summary_domains':['herd'],'language':'af','authorization_id':'SYNTHETIC-WEANING-ONLY',
            'authorized_by_user_id':'990000','authorized_at':'2026-09-01T00:00:00+02:00'}]),
        'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'true','OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':token,
        'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':actor+',990000',
        'OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED':'true','OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED':'true',
        'OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET':token,'OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED':'true',
        'OOM_SAKKIE_LLM_ROUTER_MODEL':'SIMULATED-local','OPENAI_API_KEY':'SIMULATED-no-provider-key'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with psycopg.connect(database_url()) as db:
        db.execute(Path('supabase/migrations/202609110001_allow_herdmaster_weaning_protected_claims.sql').read_text())
    deliveries = []
    def provider(_token, method, body, **kwargs):
        assert _token == 'SYNTHETIC-weaning-bot'
        assert method in ('sendMessage', 'editMessageText')
        # Telegram issues positive chat-local message IDs; edits retain that card.
        if method == 'sendMessage':
            j['message_sequence'] = j.get('message_sequence', 1000) + 1
        message_id = int(body.get('message_id') or j['message_sequence'])
        deliveries.append({'method': method, 'body': body, 'message_id': str(message_id)})
        return {'ok': True, 'result': {'message_id': message_id, 'date': int(time.time()),
            'chat': {'id': int(actor), 'type': 'private'}, 'text': body['text']}}
    monkeypatch.setattr(sam_live_stock_launch_control, '_telegram_api', provider)
    monkeypatch.setattr(telegram_direct, 'acknowledge_telegram_callback',
        lambda *args, **kwargs: ({'success':True,'status':'SIMULATED-provider-ack'},200))
    j.update(actor=actor, token=token, deliveries=deliveries, client=app.test_client())
    return j


def semantic(monkeypatch, facts=None, **extra):
    envelope = {'domain':'herd_management', 'intent':'record_litter_weaning', 'message_kind':'observation',
        'confidence':0.99, 'language':'af', 'litter_weaning':facts, **extra}
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


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
@pytest.mark.parametrize('words', ['Ek het al die varkies gister gespeen.', 'The whole current litter came off the sow yesterday.'])
def test_real_ingress_and_provider_delivery_commit_once_in_afrikaans(ingress, monkeypatch, transport, words):
    j = ingress
    semantic(monkeypatch, {'sow_ref': j['sow'], 'action_date':'gister', 'scope':'all_current'})
    before = state(j)
    rejected, _ = post(j, transport, words, bad_auth=True)
    assert rejected.status_code == 403 and state(j) == before
    response, original = post(j, transport, words)
    result = action(response)
    assert response.status_code == 200 and result['status'] == 'litter_weaning_preview_ready', response.get_json()
    assert len(j['deliveries']) == 1 and 'Bevestig hierdie presiese' in j['deliveries'][0]['body']['text']
    assert j['pigs'][0] in j['deliveries'][0]['body']['text'] and state(j) == before
    replay, _ = post(j, transport, envelope=original)
    assert replay.status_code == 200 and len(j['deliveries']) == 1, replay.get_json()
    callback = {'callback_query': {'id':'SIMULATED-CB-'+uuid.uuid4().hex, 'from': {'id':int(j['actor'])},
        'data': result['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': int(j['deliveries'][0]['message_id']), 'date': int(time.time()),
            'chat': {'id':int(j['actor']), 'type':'private'}, 'text':'SIMULATED preview card'}}}
    foreign = copy.deepcopy(callback)
    foreign['callback_query']['from']['id'] = 990000
    foreign['callback_query']['message']['chat']['id'] = 990000
    rejected, _ = post(j, transport, envelope=foreign)
    assert rejected.status_code == 403 and state(j) == before, rejected.get_json()
    confirmed, _ = post(j, transport, envelope=callback)
    completed = action(confirmed)
    assert confirmed.status_code == 200 and completed['canonical_readback_verified'], confirmed.get_json()
    after = state(j)
    assert after['receipts'] == 1 and after['pigs'][2:] == before['pigs'][2:]
    assert after['active_herd'] == before['active_herd'] and after['sow'] == before['sow']
    assert 'Speen is gestoor en teruggelees' in j['deliveries'][-1]['body']['text']
    assert j['deliveries'][-1]['body']['reply_markup'] == {'inline_keyboard': []}
    delivery_count = len(j['deliveries'])
    repeated, _ = post(j, transport, envelope=callback)
    assert repeated.status_code == 200 and state(j) == after, json.dumps(repeated.get_json()['delivery'])
    assert len(j['deliveries']) == delivery_count


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_retained_clarification_correction_and_semantic_confirmation(ingress, monkeypatch, transport):
    j = ingress
    semantic(monkeypatch, {'sow_ref':j['name'], 'action_date':'gister', 'notes':'Almal drink water.'})
    response, _ = post(j, transport, 'Ek het die varkies gister gespeen. Almal drink water.')
    first = action(response)
    assert response.status_code == 200 and first['question_count'] == 1, response.get_json()
    retained = load_weaning_context({'telegram_user_id':j['actor'], 'telegram_chat_id':j['actor'],
        'provider_timestamp':datetime.now(timezone.utc).isoformat()})
    assert retained['facts']['notes'] == 'Almal drink water.'
    assert retained['facts']['action_date'] == (datetime.now(ZoneInfo('Africa/Johannesburg')).date()-timedelta(days=1)).isoformat()
    semantic(monkeypatch, {'scope':'all_current','total_count':3}, continuation=True)
    response, _ = post(j, transport, 'Ja, die hele werpsel; drie.')
    assert action(response)['question_count'] == 1
    semantic(monkeypatch, {'total_count':2}, continuation=True, message_kind='correction')
    response, _ = post(j, transport, 'Ekskuus, twee.')
    proposed = action(response)
    assert proposed['status'] == 'litter_weaning_preview_ready', response.get_json()
    assert proposed['retained_facts']['notes'] == 'Almal drink water.'
    semantic(monkeypatch, {}, continuation=True, message_kind='confirmation')
    response, confirmation = post(j, transport, 'Ja, daardie besonderhede is reg; teken dit so aan.', reply=j['deliveries'][-1]['message_id'])
    assert response.status_code == 200 and action(response)['canonical_readback_verified'], response.get_json()
    assert state(j)['receipts'] == 1
    after = state(j); deliveries = len(j['deliveries'])
    response, _ = post(j, transport, envelope=confirmation)
    assert response.status_code == 200 and action(response)['canonical_readback_verified'], response.get_json()
    assert state(j) == after and len(j['deliveries']) == deliveries


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_configured_english_preserves_exact_preview_and_dead_sow_wording(ingress,monkeypatch,transport):
    j=ingress
    import os
    binding=json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON'])
    binding[0]['language']='en'
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON',json.dumps(binding))
    with psycopg.connect(database_url()) as db:
        db.execute("update public.pigs set status='Dead',on_farm=false where pig_id=%s",(j['sow'],))
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'yesterday','scope':'all_current'})
    response,_=post(j,transport,'I weaned the whole litter yesterday.')
    assert response.status_code == 200, response.get_json()
    text=j['deliveries'][-1]['body']['text']
    assert j['litter'] in text and all(pig in text for pig in j['pigs'][:2])
    assert 'Confirm this exact' in text and 'Dead, not on farm' in text
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    response,_=post(j,transport,'Please save that exact record.',reply=j['deliveries'][-1]['message_id'])
    assert response.status_code == 200 and action(response)['canonical_readback_verified'], response.get_json()
    assert 'Weaning saved and read back' in j['deliveries'][-1]['body']['text']
    assert 'Dead, not on farm' in j['deliveries'][-1]['body']['text']


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
@pytest.mark.parametrize('permissions', [[],['farm_observation'],['mortality_confirmation']])
def test_weaning_needs_explicit_delegation(ingress,monkeypatch,transport,permissions):
    j=ingress
    import os
    binding=json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON'])
    binding[0]['permissions']=permissions
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON',json.dumps(binding))
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    before=state(j)
    response,_=post(j,transport,'Almal is gister gespeen.')
    assert response.status_code == 403, response.get_json()
    assert state(j) == before


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_ambiguous_identity_interruption_and_stale_correction_do_not_select_a_litter(ingress,monkeypatch,transport):
    j=ingress; second=seed()
    with psycopg.connect(database_url()) as db:
        db.execute('update public.pigs set pig_name=%s where pig_id=%s',(j['name'],second['sow']))
    semantic(monkeypatch,{'sow_ref':j['name'],'action_date':'gister','scope':'all_current','notes':'Retain this reported fact.'})
    response,_=post(j,transport,'Die hele werpsel is gister gespeen.')
    assert action(response)['question_count'] == 1
    semantic(monkeypatch,None,intent='general_farm_query',message_kind='question',needs_clarification=True)
    post(j,transport,'En die besproeiing?')
    semantic(monkeypatch,{'sow_ref':j['sow']},continuation=True,message_kind='correction')
    response,_=post(j,transport,'Ek bedoel hierdie sog se ID.')
    preview=action(response)
    assert preview['status'] == 'litter_weaning_preview_ready', response.get_json()
    assert preview['retained_facts']['notes'] == 'Retain this reported fact.'
    old_token=preview['callback_token']
    semantic(monkeypatch,{'total_count':3},continuation=True,message_kind='correction')
    response,_=post(j,transport,'Wag, ek tel drie.')
    assert action(response)['question_count'] == 1
    with psycopg.connect(database_url()) as db:
        assert db.execute('select status from app_private.oom_protected_action_claims where callback_token=%s',(old_token,)).fetchone()[0] == 'changed'
    assert state(j)['receipts'] == state(second)['receipts'] == 0


@pytest.mark.parametrize('transport',['gateway','direct'])
def test_non_private_reports_never_create_weaning_claims(ingress,monkeypatch,transport):
    j=ingress; before=state(j)
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    envelope={'message':{'message_id':5001,'date':int(time.time()),'from':{'id':int(j['actor'])},
        'chat':{'id':-10098765,'type':'supergroup'},'text':'Almal is gespeen.'}}
    response,_=post(j,transport,envelope=envelope)
    assert response.status_code in (200,403) and state(j) == before
    with psycopg.connect(database_url()) as db:
        assert db.execute("select count(*) from app_private.oom_protected_action_claims where owner_user_id=%s",(j['actor'],)).fetchone()[0] == 0


def test_actual_farm_login_legacy_route_exact_weights_csrf_and_revocation(ingress,monkeypatch):
    import os
    import re
    from tests.test_herdmaster_mortality_journey_postgres import signed_init
    j=ingress; client=j['client']; path='/api/pig-weights/litter/'+j['litter']+'/mark-weaned'
    before=state(j)
    assert client.post(path,json={'wean_date':'2026-09-10'}).status_code == 403
    login=client.post('/owner/telegram/login',json={'init_data':signed_init(j['actor'])},headers={'X-Farm-Login':'telegram'})
    assert login.status_code == 200,login.get_json()
    page=client.get('/litter/'+j['litter']).get_data(as_text=True)
    csrf=re.search(r'data-weaning-csrf="([^"]+)"',page).group(1)
    headers={'X-Weaning-CSRF':csrf}
    p={'wean_date':'2026-09-10','dry_run':True,'changed_by':'forged-client',
       'wean_weights':{j['pigs'][0]:7.8},'use_latest_weights_as_wean_weights':False}
    assert client.post(path,json=p).status_code == 403
    assert client.post(path,json={**p,'use_latest_weights_as_wean_weights':True},headers=headers).status_code == 409
    response=client.post(path,json=p,headers=headers); proposed=response.get_json()
    assert response.status_code == 200,proposed
    assert proposed['changed_by'] == j['actor'] and proposed['weight_count'] == 1
    assert state(j) == before
    response=client.post(path,json={**p,'dry_run':False,'confirmed':True,'confirmation_binding':proposed['confirmation_binding']},headers=headers)
    assert response.status_code == 200 and response.get_json()['canonical_readback_verified'],response.get_json()
    assert float(state(j)['pigs'][0][5]) == 7.8 and state(j)['pigs'][1][5] is None
    # Existing farm session is rechecked against delegation on every request.
    binding=json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON']); binding[0]['permissions']=['mortality_confirmation']
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON',json.dumps(binding))
    assert client.post(path,json=p,headers=headers).status_code == 403


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_incomplete_optional_treatment_retains_weight_and_actual_date(ingress,monkeypatch,transport):
    j=ingress; product='PRODUCT-'+j['litter']
    with psycopg.connect(database_url()) as db:
        db.execute("insert into public.farm_products(product_id,product_name,dose_unit,default_dose) values(%s,'Synthetic dewormer','ml','999')",(product,))
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current',
        'assignments':[{'pig_ref':j['pigs'][0],'wean_weight_kg':8.1}],
        'medicine':{'deworming_product_id':product,'notes':'Reported actual treatment.'}})
    response,_=post(j,transport,'Alles gister gespeen; die eerste een weeg 8.1 kg en ek het ontwurm.')
    assert action(response)['question_count'] == 1
    retained=action(response)['retained_facts']
    semantic(monkeypatch,{'medicine':{'dose':1.2,'route':'Oral','batch_lot_number':'TEST-BATCH'}},continuation=True)
    response,_=post(j,transport,'1.2 ml per mond, lot TEST-BATCH.')
    preview=action(response)
    assert preview['status'] == 'litter_weaning_preview_ready',response.get_json()
    assert preview['retained_facts']['action_date'] == retained['action_date']
    assert '8.1 kg' in preview['answer'] and '1.2 ml' in preview['answer'] and 'Reported actual treatment.' in preview['answer']
    assert '999 ml' not in preview['answer'] and state(j)['receipts'] == 0


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_semantic_confirmation_recovers_crash_after_commit_before_claim_completion(ingress,monkeypatch,transport):
    from modules.oom_sakkie import protected_action_runtime
    j=ingress
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    response,_=post(j,transport,'Die hele werpsel is gister gespeen.')
    assert action(response)['status'] == 'litter_weaning_preview_ready'
    original=protected_action_runtime.complete_claim
    def crash(*args,**kwargs):
        raise ConnectionError('SIMULATED process loss after the real weaning commit')
    monkeypatch.setattr(protected_action_runtime,'complete_claim',crash)
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    response,envelope=post(j,transport,'Teken hierdie presiese verslag aan.',reply=j['deliveries'][-1]['message_id'])
    assert response.status_code == 503 and state(j)['receipts'] == 1,response.get_json()
    monkeypatch.setattr(protected_action_runtime,'complete_claim',original)
    after=state(j)
    response,_=post(j,transport,envelope=envelope)
    assert response.status_code == 200 and action(response)['canonical_readback_verified'],response.get_json()
    assert state(j) == after
