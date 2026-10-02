"""Historical report replies use real local PostgreSQL, never provider/farm effects."""
from copy import deepcopy
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import pytest
from psycopg.types.json import Jsonb

from tests.test_oom_sakkie_retained_farrowing_review_postgres import (
    journey, store, ready, snapshot, NOW, MISSION, KIND, URL)
from modules.oom_sakkie import herdmaster_farrowing_runtime as runtime
from modules.oom_sakkie import retained_farrowing_review_context as context
from modules.oom_sakkie.herdmaster_farrowing_conversation import PostgresFarrowingStore
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

pytestmark = pytest.mark.skipif(not URL, reason='explicit disposable PostgreSQL required')


def delivered(journey, *, delivered_at=NOW):
    case = ready(journey)
    receipt = {'state':'delivered', 'mission_id':case['case_id']+':G'+str(case['generation']),
        'card_mission_id':case['case_id'], 'owner_user_id':'900','chat_id':'900',
        'specialist_identity':'HERDMASTER','task_state':'retained_farrowing_owner_attention',
        'telegram_message_id':'700','delivery_provider_timestamp':delivered_at.isoformat()}
    receipt['provider_message_id'] = 'scheduled:'+receipt['mission_id']
    with journey['store']() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set status='waiting_reassessment',last_delivery_digest=evidence_digest where case_id=%s",(case['case_id'],))
        cur.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,event_source,review_json,created_at) values('shown',
            'oom_sakkie_family_message_lifecycle',%s,%s)""",(Jsonb({'family_message_lifecycle':receipt}),delivered_at))
    return case,receipt


def incoming(**changes):
    return {'telegram_user_id':'900','telegram_chat_id':'900','provider_message_id':'701',
        'provider_timestamp':(NOW+timedelta(minutes=1)).isoformat(),
        'reply_to_message_id':'700','text':'Yes, those details are correct.','output_language':'en',
        'semantic':{'intent':'record_farrowing_litter','continuation':True,
            'message_kind':'observation','confidence':0.99,'needs_clarification':False,
            'farrowing_litter':{}}, **changes}


def canonical(**_):
    return {'evidence_generation':'CURRENT', 'animals':[{'pig_id':'SOW-A',
        'name':'Linda','tag_number':'S-A','sex':'Female','status':'Active','on_farm':True}],
        'matings':[],'litters':[]}


def handle(journey, parsed):
    return runtime.handle_farrowing_litter_message(parsed,issue_gateway_owner_authority('900','900'),
        context_store=PostgresFarrowingStore(journey['store']),
        evidence_loader=canonical, now=NOW+timedelta(minutes=1))


def test_unrelated_question_can_read_historical_data_without_preparation(journey,monkeypatch):
    delivered(journey)
    monkeypatch.setattr(runtime,'PostgresFarrowingStore',lambda *_:PostgresFarrowingStore(journey['store']))
    monkeypatch.setattr(runtime,'create_claim',lambda **_:pytest.fail('unrelated claim creation'))
    monkeypatch.setattr(runtime,'prepare_farrowing_litter_preview',lambda *_:pytest.fail('unrelated preview'))
    monkeypatch.setattr(runtime,'load_canonical_farrowing_evidence',lambda **_:pytest.fail('discovery canonical export'))
    before=snapshot(journey['store'])
    question=incoming(text='How many pigs are on the farm?',reply_to_message_id='',
        semantic={'intent':'herd_inventory','message_kind':'question'})
    found=runtime.load_farrowing_context(question)
    assert found['historical_review'] is True and found['facts']['born_alive']==11
    result,code=runtime.handle_farrowing_litter_message(question,issue_gateway_owner_authority('900','900'))
    assert code==200 and result['handled'] is False
    assert snapshot(journey['store'])==before


@pytest.mark.parametrize('correction',[False,True])
def test_delivered_owner_reply_prepares_new_preview_only_and_replays(journey,correction):
    delivered(journey);before=snapshot(journey['store'])
    parsed=incoming()
    if correction:
        parsed['text']='Actually 10 born alive and 2 stillborn.'
        parsed['semantic'].update(message_kind='correction',farrowing_litter={'born_alive':10,'stillborn':2})
    result,code=handle(journey,parsed)
    assert code==200 and result['status']=='farrowing_litter_preview_ready'
    assert result['writes_farm_data'] is False and result['protected_actions_performed'] is False
    assert result['retained_facts']['born_alive']==(10 if correction else 11)
    assert 'PIG-' not in result['answer'] and 'Linda' in result['answer']
    after=snapshot(journey['store'])
    old={r[0]['callback_token']:r[0] for r in before[0]}
    current={r[0]['callback_token']:r[0] for r in after[0]}
    assert all(current[k]==v for k,v in old.items()) and len(current)==len(old)+1
    assert after[1:]==before[1:]
    replay,code=handle(journey,parsed)
    assert code==200 and replay['callback_token']==result['callback_token']
    assert snapshot(journey['store'])==after
    with journey['store'](True) as db,db.cursor() as cur:
        cur.execute("select review_json->'farrowing_litter' from public.sam_live_stock_conversation_review_events where event_source='oom_sakkie_farrowing_litter'")
        rows=cur.fetchall()
    assert len(rows)==1
    binding=rows[0][0]['historical_review_binding']
    assert binding['source_mission']==MISSION and binding['reporting_principal']=='42'
    assert binding['owner']=='900' and binding['card_message_id']=='700'


@pytest.mark.parametrize('drift',['source','generation','owner','card','age','completed','canonical','uncertain','confirmation'])
def test_changed_or_unauthorized_context_cannot_prepare(journey,monkeypatch,drift):
    case,_=delivered(journey,delivered_at=NOW-timedelta(hours=7) if drift=='age' else NOW);parsed=incoming()
    with journey['store']() as db,db.cursor() as cur:
        if drift=='source':cur.execute("update app_private.oom_protected_action_claims set status='cancelled' where callback_token='original'")
        if drift=='generation':cur.execute('update app_private.oom_manager_cases set generation=generation+1 where case_id=%s',(case['case_id'],))
        if drift=='completed':cur.execute("update app_private.oom_manager_cases set status='completed' where case_id=%s",(case['case_id'],))
        if drift=='canonical':cur.execute("insert into public.litters(litter_id,sow_pig_id,farrowing_date,litter_status) values('BIRTH','SOW-A','2026-09-01','Active')")
    if drift=='owner':monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','901')
    if drift=='card':parsed['reply_to_message_id']='699'
    if drift=='uncertain':parsed['semantic']['needs_clarification']=True
    if drift=='confirmation':parsed['semantic']['message_kind']='confirmation'
    monkeypatch.setattr(runtime,'create_claim',lambda **_:pytest.fail('unproven source claim'))
    before=snapshot(journey['store']);result,code=handle(journey,parsed)
    assert not result.get('callback_token') and result['writes_farm_data'] is False
    assert snapshot(journey['store'])==before


def test_many_irrelevant_old_reviews_do_not_hide_explicit_current_card(journey):
    case,receipt=delivered(journey)
    with journey['store']() as db,db.cursor() as cur:
        for number in range(20):
            old_id='000-old-'+str(number)
            cur.execute("""insert into app_private.oom_manager_cases
                select (jsonb_populate_record(null::app_private.oom_manager_cases,
                    to_jsonb(c)||%s)).* from app_private.oom_manager_cases c where case_id=%s""",
                (Jsonb({'case_id':old_id,'dedupe_key':'old-'+str(number),'status':'completed'}),case['case_id']))
            old={**receipt,'card_mission_id':old_id,'telegram_message_id':str(number)}
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json,created_at) values(%s,
                'oom_sakkie_family_message_lifecycle',%s,%s)""",(old_id,Jsonb({'family_message_lifecycle':old}),NOW))
    result=context.discover_retained_farrowing_review_context(incoming())
    assert result['context_id']=='HISTORICAL-REVIEW-'+case['case_id']
    assert result['context_authority']=='historical_data_only'


def test_concurrent_same_reply_has_one_preview_and_no_farm_effect(journey):
    delivered(journey);before=snapshot(journey['store'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:handle(journey,incoming()),range(2)))
    assert all(code==200 for _,code in results)
    assert len({r['callback_token'] for r,_ in results})==1
    after=snapshot(journey['store'])
    assert len(after[0])==len(before[0])+1 and after[1:]==before[1:]


def test_correction_with_current_tag_and_current_name_binds_same_sow(journey):
    delivered(journey);parsed=incoming(text='S-A had 10 born alive and 2 stillborn.')
    parsed['semantic'].update(message_kind='correction',farrowing_litter={'sow_ref':'S-A','born_alive':10,'stillborn':2})
    result,code=handle(journey,parsed)
    assert code==200 and result['status']=='farrowing_litter_preview_ready'
    assert result['retained_facts']['sow_ref']=='S-A' and result['writes_farm_data'] is False
