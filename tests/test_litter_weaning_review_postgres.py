"""Independent-review regressions through real ingress, claims and PostgreSQL.

Only identity/semantic/provider boundaries are simulated, as in the original
ingress qualification. No production database or provider is used.
"""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import psycopg
import pytest

from modules.oom_sakkie import family_message_lifecycle, protected_action_runtime
from modules.sales import sam_live_stock_launch_control
from tests.test_litter_weaning_ingress_postgres import ingress, semantic, post, action
from tests.weaning_test_support import database_url, seed, state


def evidence(name, value):
    directory = os.environ.get('WEANING_REVIEW_EVIDENCE_DIR')
    if directory:
        target = Path(directory).resolve()
        assert target.is_relative_to(Path('C:/tmp/amadeus-weaning-20260911/runtime/review-2').resolve())
        (target/(name+'.json')).write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')


def claim_states(j):
    with psycopg.connect(database_url()) as db:
        return db.execute("""select callback_token,status,confirmation_provider_message_id,
            preview_card_message_id from app_private.oom_protected_action_claims
            where owner_user_id=%s order by created_at,callback_token""",(j['actor'],)).fetchall()


def at(j,transport,text,sequence,stamp):
    j['message_sequence'] = max(j.get('message_sequence',0),sequence)
    return post(j,transport,envelope={'message':{'message_id':sequence,'date':stamp,
        'from':{'id':int(j['actor'])},'chat':{'id':int(j['actor']),'type':'private'},'text':text}})


@pytest.fixture
def numeric_provider(ingress,monkeypatch):
    j=ingress
    def provider(token,method,body,**kwargs):
        assert token == 'SYNTHETIC-weaning-bot' and method in ('sendMessage','editMessageText')
        if method == 'sendMessage':
            j['message_sequence'] = j.get('message_sequence',1000)+1
        card=str(body.get('message_id') or j['message_sequence'])
        j['deliveries'].append({'method':method,'body':body,'message_id':card})
        return {'ok':True,'result':{'message_id':int(card),'date':int(time.time()),
            'chat':{'id':int(j['actor']),'type':'private'},'text':body['text']}}
    monkeypatch.setattr(sam_live_stock_launch_control,'_telegram_api',provider)
    return j


@pytest.mark.parametrize('transport',['gateway','direct'])
@pytest.mark.parametrize('order',['older_timestamp','same_second'])
def test_delayed_replyless_confirmation_never_executes_newer_corrected_preview(numeric_provider,monkeypatch,transport,order):
    j=numeric_provider; stamp=int(time.time())-5
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current','notes':'Original facts.'})
    first,_=at(j,transport,'Alles is gister gespeen.',1001,stamp)
    assert action(first)['status'] == 'litter_weaning_preview_ready'
    semantic(monkeypatch,{'notes':'Later corrected facts.'},continuation=True,message_kind='correction')
    corrected,_=at(j,transport,'Wag, verander die nota.',1004,stamp if order=='same_second' else stamp+2)
    assert action(corrected)['status'] == 'litter_weaning_preview_ready'
    before=state(j); claims_before=claim_states(j)
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    delayed,envelope=at(j,transport,'Ja, teken dit so aan.',1003,stamp if order=='same_second' else stamp+1)
    evidence('delayed-'+transport+'-'+order,{'fixture':j['litter'],'envelope':envelope,
        'corrected':action(corrected),'http_status':delayed.status_code,'response':delayed.get_json(),
        'before':before,'after':state(j),'claims_before':claims_before,'claims_after':claim_states(j)})
    assert delayed.status_code == 409,delayed.get_json()
    assert state(j) == before and claim_states(j) == claims_before
    assert all(row[2] is None for row in claim_states(j))


@pytest.mark.parametrize('transport',['gateway','direct'])
@pytest.mark.parametrize('failure',['ambiguous','orphaned','bounded'])
def test_completion_edit_recovers_once_after_real_commit(ingress,monkeypatch,transport,failure):
    j=ingress
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    response,_=post(j,transport,'Die hele werpsel is gister gespeen.')
    preview=action(response); card=j['deliveries'][0]['message_id']
    assert preview['status'] == 'litter_weaning_preview_ready'
    provider=sam_live_stock_launch_control._telegram_api
    event_store=family_message_lifecycle._event_store
    edits=[]
    orphaned=False
    def lose_delivery_receipt(operation,identity,payload):
        nonlocal orphaned
        if (failure == 'orphaned' and not orphaned and operation == 'record'
                and (payload or {}).get('state') == 'updated'):
            orphaned=True
            raise RuntimeError('SIMULATED process loss after edit acknowledgement before its durable receipt')
        return event_store(operation,identity,payload)
    monkeypatch.setattr(family_message_lifecycle,'_event_store',lose_delivery_receipt)
    def flaky(token,method,body,**kwargs):
        if method == 'editMessageText':
            edits.append(copy.deepcopy(body))
            if (len(edits) == 1 and failure == 'ambiguous') or failure == 'bounded':
                return {'ok':False,'description':'SIMULATED ambiguous edit; no provider acknowledgement'}
        return provider(token,method,body,**kwargs)
    monkeypatch.setattr(sam_live_stock_launch_control,'_telegram_api',flaky)
    callback={'callback_query':{'id':'REVIEW-CB-'+j['litter'],'from':{'id':int(j['actor'])},
        'data':preview['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message':{'message_id':card,'date':int(time.time()),'chat':{'id':int(j['actor']),'type':'private'},'text':'Synthetic exact preview'}}}
    first,_=post(j,transport,envelope=callback)
    assert state(j)['receipts'] == 1
    after=state(j)
    second,_=post(j,transport,envelope=callback)
    third,_=post(j,transport,envelope=callback)
    evidence('completion-'+transport+'-'+failure,{'litter':j['litter'],'first':first.get_json(),
        'second':second.get_json(),'third':third.get_json(),'edit_attempts':edits,'state':state(j),
        'claim_states':claim_states(j)})
    assert len(edits) == 2,second.get_json()
    assert failure != 'orphaned' or orphaned
    if failure == 'bounded':
        assert not second.get_json()['delivery']['success'] and not third.get_json()['delivery']['success']
    else:
        assert second.status_code == third.status_code == 200
        assert second.get_json()['delivery']['success'] and third.get_json()['delivery']['success']
    assert state(j) == after and state(j)['receipts'] == 1
    assert all(str(body['message_id']) == card and body['reply_markup'] == {'inline_keyboard':[]} for body in edits)
    assert len([row for row in j['deliveries'] if row['method']=='sendMessage']) == 1


@pytest.mark.parametrize('transport',['gateway','direct'])
@pytest.mark.parametrize('recovery',['completed','executing'])
@pytest.mark.parametrize('reply_mode',['replyless','explicit'])
def test_valid_natural_confirmation_keeps_native_reply_and_recovers_its_receipt(
        numeric_provider,monkeypatch,transport,recovery,reply_mode):
    j=numeric_provider
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    preview,_=post(j,transport,'Alles is gister gespeen.')
    token=action(preview)['callback_token']; card=j['deliveries'][-1]['message_id']
    complete=protected_action_runtime.complete_claim
    if recovery == 'executing':
        def interrupted(*args,**kwargs):
            raise RuntimeError('SIMULATED interruption after farm commit, before claim completion')
        monkeypatch.setattr(protected_action_runtime,'complete_claim',interrupted)
    execute=protected_action_runtime.handle_protected_action_input
    received=[]
    def observe_native(parsed,*args,**kwargs):
        received.append({'reply':parsed.get('reply_to_message_id') or '',
            'provider':parsed.get('provider_message_id'), 'semantic_mode':kwargs.get('weaning_semantic_confirmation')})
        return execute(parsed,*args,**kwargs)
    monkeypatch.setattr(protected_action_runtime,'handle_protected_action_input',observe_native)
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    confirmed,envelope=post(j,transport,'Ja, teken dit so aan.',reply=card if reply_mode=='explicit' else '')
    assert confirmed.status_code == (503 if recovery=='executing' else 200),confirmed.get_json()
    assert state(j)['receipts'] == 1
    assert received[-1]['reply'] == (card if reply_mode=='explicit' else '')
    assert received[-1]['semantic_mode'] is True
    monkeypatch.setattr(protected_action_runtime,'complete_claim',complete)
    # A newer unrelated litter preview must not absorb this exact old receipt.
    other=seed()
    semantic(monkeypatch,{'sow_ref':other['sow'],'action_date':'gister','scope':'all_current'})
    newer,_=post(j,transport,'Hierdie ander werpsel is ook gister gespeen.')
    assert action(newer)['status'] == 'litter_weaning_preview_ready',newer.get_json()
    before=state(j); other_before=state(other)
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    repeated,_=post(j,transport,envelope=envelope)
    again,_=post(j,transport,envelope=envelope)
    assert repeated.status_code == again.status_code == 200,repeated.get_json()
    assert action(repeated)['canonical_readback_verified'] and action(again)['canonical_readback_verified']
    assert state(j) == before and state(other) == other_before and other_before['receipts'] == 0
    claims=claim_states(j)
    assert next(row[1] for row in claims if row[0]==token) == 'completed'
    assert next(row[1] for row in claims if row[0]==action(newer)['callback_token']) == 'active'
    assert all(row['reply'] == (card if reply_mode=='explicit' else '') for row in received)
    evidence('valid-'+transport+'-'+recovery+'-'+reply_mode,{'litter':j['litter'],'other_litter':other['litter'],
        'confirmation_envelope':envelope,'first':confirmed.get_json(),'recovery':repeated.get_json(),
        'repeat':again.get_json(),'native_executor_input':received,'claims':claims,'state':state(j),'other_state':state(other)})


@pytest.mark.parametrize('transport',['gateway','direct'])
@pytest.mark.parametrize('provenance',['before_card','before_card_reply','older_time','opaque_id','missing_source','wrong_reply'])
def test_ambiguous_first_arrival_provenance_never_claims(numeric_provider,monkeypatch,transport,provenance):
    j=numeric_provider; stamp=int(time.time())-3
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    preview,_=at(j,transport,'Alles is gister gespeen.',1001,stamp)
    assert action(preview)['status'] == 'litter_weaning_preview_ready'
    card=j['deliveries'][-1]['message_id']
    if provenance=='missing_source':
        with psycopg.connect(database_url()) as db:
            db.execute("""update app_private.oom_protected_action_claims
                set preview_payload=preview_payload-'provider_message_id' where callback_token=%s""",
                (action(preview)['callback_token'],))
    before=state(j); claims=claim_states(j)
    envelope={'message':{'message_id':int(card) if provenance in {'before_card','before_card_reply'} else 'opaque-confirm' if provenance=='opaque_id' else 1003,
        'date':stamp-1 if provenance=='older_time' else stamp,
        'from':{'id':int(j['actor'])},'chat':{'id':int(j['actor']),'type':'private'},'text':'Ja, teken dit so aan.'}}
    if provenance=='wrong_reply':
        envelope['message']['reply_to_message']={'message_id':999}
    elif provenance=='before_card_reply':
        envelope['message']['reply_to_message']={'message_id':int(card)}
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    response,_=post(j,transport,envelope=envelope)
    assert response.status_code == 409,response.get_json()
    assert state(j) == before and claim_states(j) == claims
    assert action(response)['answer'] and not action(response)['writes_farm_data']
    evidence('provenance-'+transport+'-'+provenance,{'litter':j['litter'],'envelope':envelope,
        'response':response.get_json(),'before':before,'after':state(j),'claims_before':claims,'claims_after':claim_states(j)})


@pytest.mark.parametrize('transport',['gateway','direct'])
@pytest.mark.parametrize('boundary',['other_actor','other_chat','group'])
def test_semantic_confirmation_preserves_actor_and_private_chat_boundaries(numeric_provider,monkeypatch,transport,boundary):
    j=numeric_provider
    semantic(monkeypatch,{'sow_ref':j['sow'],'action_date':'gister','scope':'all_current'})
    preview,_=post(j,transport,'Alles is gister gespeen.')
    assert action(preview)['status'] == 'litter_weaning_preview_ready'
    binding=json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON'])
    foreign='7999999998'
    binding.append({**binding[0],'telegram_user_id':foreign})
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON',json.dumps(binding))
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS',os.environ['OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS']+','+foreign)
    before=state(j); claims=claim_states(j)
    envelope={'message':{'message_id':1003,'date':int(time.time()),
        'from':{'id':int(foreign if boundary=='other_actor' else j['actor'])},
        'chat':{'id':int(foreign if boundary in {'other_actor','other_chat'} else j['actor']),
            'type':'group' if boundary=='group' else 'private'},
        'reply_to_message':{'message_id':int(j['deliveries'][-1]['message_id'])},'text':'Ja, teken dit so aan.'}}
    semantic(monkeypatch,{},continuation=True,message_kind='confirmation')
    response,_=post(j,transport,envelope=envelope)
    assert response.status_code >= 400,response.get_json()
    assert state(j) == before and claim_states(j) == claims
    evidence('boundary-'+transport+'-'+boundary,{'litter':j['litter'],'envelope':envelope,
        'response':response.get_json(),'before':before,'after':state(j),'claims_before':claims,'claims_after':claim_states(j)})
