"""Real PostgreSQL/gateway dialogue; synthetic semantic responses and provider transport."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from threading import Barrier
from urllib.parse import urlparse

import psycopg
import pytest

from modules.oom_sakkie import daily_farm_manager as daily
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import manager_question_runtime as manager
from modules.oom_sakkie import operational_specialist_intake as intake
from modules.oom_sakkie import owner_operational_continuation as continuation
from modules.oom_sakkie import rootline_operational_adapter as adapter
from modules.oom_sakkie import semantic_front_door as front
from modules.oom_sakkie import telegram_gateway as gateway
from modules.oom_sakkie.farm_manager_loop import (Authority, Provenance,
    SpecialistAvailability, SpecialistResult, SpecialistWorkItem, WorkState)
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from tests.test_oom_sakkie_plan_dialogue_postgres import journey as plan_journey

DSN = os.environ.get('CHARLIE_DISPOSABLE_POSTGRES_URL', '')
pytestmark = pytest.mark.skipif(not DSN, reason='explicit disposable PostgreSQL required')
NOW = datetime(2026,9,12,8,0,tzinfo=timezone.utc)


class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self):
        return json.dumps({'choices':[{'message':{'content':json.dumps(asdict(self.value))}}]}).encode()


@pytest.fixture
def irrigation(monkeypatch):
    assert urlparse(DSN).hostname in {'127.0.0.1','localhost'}
    assert urlparse(DSN).path == '/irrigation_dialogue_test'
    j = plan_journey.__wrapped__(monkeypatch)
    def interpret(parsed, **kwargs):
        environment = {**os.environ, 'OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED':'1',
            'OOM_SAKKIE_LLM_ROUTER_MODEL':'synthetic', 'OPENAI_API_KEY':'synthetic-only'}
        return front.interpret_owner_message(parsed, environ=environment,
            context_loader=kwargs.get('context_loader'), http_open=lambda *a,**k: Response(j['semantic']['value']))
    monkeypatch.setattr(gateway, 'interpret_owner_message', interpret)
    monkeypatch.setattr(adapter, 'build_current_rootline_specialist_result', lambda: {
        'success':True, 'contract_version':'rootline_specialist_result_v1',
        'result_id':'SYNTHETIC-ROOTLINE-READ-MODEL', 'generation':'SYNTHETIC-READ-GENERATION',
        'recommendations':[], 'evidence':{}, 'next_reassessment':None})
    return j


def work(j, language, subject='storage_tanks'):
    af = language == 'af'; reservoir = subject == 'reservoir'
    question = ('Hoe vol is die reservoir?' if reservoir else 'Hoe vol is die opgaartenks?') if af else (
        'How full is the reservoir?' if reservoir else 'How full are the storage tanks?')
    item = SpecialistWorkItem(item_id='SYNTHETIC-WATER-'+j['owner']+'-'+subject,
        dedupe_key='rootline:synthetic:'+j['owner']+':'+subject, domain='rootline',
        title='Watervlak' if af else 'Water level', why=question, next_action=question,
        assignee='charl', state=WorkState.WAITING_EVIDENCE, authority=Authority.ADVISORY,
        provenance=Provenance('rootline','SYNTHETIC-ROOTLINE-'+j['owner'],('synthetic-water',),NOW,1.0),
        genuine_question=question, question_for='charl')
    return SpecialistResult('rootline','SYNTHETIC-ROOTLINE-'+j['owner'],NOW,
        SpecialistAvailability.AVAILABLE,work_items=(item,))


def present(j, language, *, subject='storage_tanks', fault=False, original=True, at=NOW):
    j['provider_clock'][0] = at
    def store(action, identity, payload):
        if fault and action == 'record_daily':
            return {'success':False, 'created':False}
        if not original and action == 'claim_daily':
            payload = {key:value for key,value in payload.items()
                if key not in {'question','question_binding','answer_sha256'}}
        return daily.daily_farm_manager_store(action, identity, payload)
    result = daily.run_daily_farm_manager(owner_user_id=j['owner'],chat_id=j['owner'],
        specialist_results=[work(j,language,subject)],litter_rows=[],
        deliver=family.deliver_family_result,store=store,now=at,language=language)
    assert result['telegram_message_id'],result
    if fault:
        assert result['success'] is False and result['status'] == 'daily_manager_provider_confirmed_lifecycle_unavailable',result
    else:
        assert result['success'] is True,result
    questions = manager._load_questions(j['owner'],j['owner'])
    assert len(questions) == 1,questions
    return questions[0]


def meaning(j, language, facts, *, basis=None, clarification=''):
    j['semantic']['value'] = front.SemanticInterpretation(domain='rootline', intent='water_levels_observed',
        message_kind='observation',continuation=True,observation='Current independently reported water levels.',
        observation_facts=tuple(facts), water_observation_context=basis or {'source':'current_message'},
        language=language,confidence=.99,needs_clarification=any(row.get('state') == 'UNKNOWN' for row in facts),
        clarification_question=clarification)
    return j['semantic']['value']


def reply(j, text, provider, at, card=''):
    j['provider_clock'][0] = at
    body = {'message_id':provider,'date':int(at.timestamp()),'text':text,
        'from':{'id':int(j['owner'])},'chat':{'id':int(j['owner']),'type':'private'}}
    if card: body['reply_to_message'] = {'message_id':int(card)}
    return gateway.handle_telegram_gateway_message({'message':body},
        headers={'Authorization':'Bearer '+j['token']},environ=os.environ)


def observations(j):
    actor = 'telegram-owner:'+sha256(j['owner'].encode()).hexdigest()[:16]
    with psycopg.connect(DSN) as db:
        return db.execute('''select observation_id,provider_message_id,observed_at,
            storage_state,reservoir_state,storage_fraction_numerator,storage_fraction_denominator,
            reservoir_fraction_numerator,reservoir_fraction_denominator
            from public.rootline_tank_observations where reporter_identity=%s
            order by observed_at,provider_message_id,observation_id''',(actor,)).fetchall()


@pytest.mark.parametrize('language',['en','af'])
@pytest.mark.parametrize('fault',[False,True])
def test_morning_reply_partial_restart_and_duplicate_keep_independent_water_rows(irrigation,language,fault):
    j = irrigation; question = present(j,language,fault=fault)
    text = 'Die opgaartenks is vol; ek weet nie hoe vol die reservoir is nie.' if language == 'af' else \
        'Storage tanks are full; the reservoir level is unknown.'
    meaning(j,language,[{'subject':'storage_tanks','state':'FULL'},{'subject':'reservoir','state':'UNKNOWN'}],
        clarification='Hoe vol is die reservoir?' if language == 'af' else 'How full is the reservoir?')
    first,status = reply(j,text,701,NOW+timedelta(minutes=1),question['telegram_message_id'])
    assert status == 200 and first['status'] == 'manager_question_partial_reply_recorded',first
    assert len(observations(j)) == 1 and observations(j)[0][1] == '701'
    delivered = len(j['provider'])
    replay,status = reply(j,text,701,NOW+timedelta(minutes=1),question['telegram_message_id'])
    assert status == 200 and len(j['provider']) == delivered,replay
    reloaded = manager._load_questions(j['owner'],j['owner'])
    assert len(reloaded) == 1 and len(reloaded[0]['partial_replies']) == 1,reloaded
    partial = reloaded[0]['partial_replies'][0]
    assert partial['clarification_telegram_message_id']
    meaning(j,language,[{'subject':'reservoir','numerator':1,'denominator':2}])
    second,status = reply(j,'Die reservoir is halfvol.' if language == 'af' else 'The reservoir is half full.',
        702,NOW+timedelta(minutes=2),partial['clarification_telegram_message_id'])
    assert status == 200 and second['message']['manager_question_status'] == 'manager_question_reply_recorded',second
    actual = observations(j)
    assert len(actual) == 2 and [row[1] for row in actual] == ['701','702']
    assert actual[0][2] == NOW+timedelta(minutes=1) and actual[1][2] == NOW+timedelta(minutes=2)
    assert actual[0][3:5] == ('FULL','Unknown') and actual[1][3:5] == ('Unknown','OK')
    assert actual[1][7:9] == (1,2)
    assert manager._load_questions(j['owner'],j['owner']) == []
    delivered = len(j['provider'])
    duplicate,status = reply(j,'Die reservoir is halfvol.' if language == 'af' else 'The reservoir is half full.',
        702,NOW+timedelta(minutes=2),partial['clarification_telegram_message_id'])
    assert status == 200 and observations(j) == actual and len(j['provider']) == delivered,duplicate


@pytest.mark.parametrize('language',['en','af'])
def test_new_delivered_generation_with_missing_outcome_replaces_old_question(irrigation,language):
    j = irrigation; old = present(j,language)
    current = present(j,language,subject='reservoir',fault=True,at=NOW+timedelta(minutes=1))
    assert current['telegram_message_id'] != old['telegram_message_id']
    assert current['question'] == work(j,language,'reservoir').work_items[0].genuine_question
    meaning(j,language,[{'subject':'reservoir','state':'FULL'}],
        basis={'source':'active_question','telegram_message_id':current['telegram_message_id']})
    result,status = reply(j,'Ja.' if language == 'af' else 'Yes.',701,NOW+timedelta(minutes=2))
    assert status == 200 and result['message']['manager_question_status'] == 'manager_question_reply_recorded',result
    actual = observations(j)
    assert len(actual) == 1 and actual[0][3:5] == ('Unknown','FULL')


def test_missing_original_question_never_infers_yes_but_accepts_explicit_current_fact(irrigation):
    j = irrigation; question = present(j,'en',fault=True,original=False)
    assert question['question_binding']['contextual_card_recovery'] is True
    meaning(j,'en',[{'subject':'storage_tanks','state':'FULL'}],
        basis={'source':'active_question','telegram_message_id':question['telegram_message_id']})
    result,status = reply(j,'Yes.',701,NOW+timedelta(minutes=1),question['telegram_message_id'])
    assert status == 409 and observations(j) == [],result
    meaning(j,'en',[{'subject':'storage_tanks','state':'FULL'}])
    result,status = reply(j,'The storage tanks are full.',702,NOW+timedelta(minutes=2),question['telegram_message_id'])
    assert status == 200 and len(observations(j)) == 1,result


@pytest.mark.parametrize('language',['en','af'])
def test_real_post_commit_interruption_reconciles_same_rows_without_specialist_retry(irrigation,language,monkeypatch):
    j = irrigation; question = present(j,language)
    semantic = meaning(j,language,[{'subject':'storage_tanks','state':'FULL'}])
    text = 'Die opgaartenks is vol.' if language == 'af' else 'The storage tanks are full.'
    at = NOW+timedelta(minutes=1)
    parsed = {'telegram_user_id':j['owner'],'telegram_chat_id':j['owner'],
        'provider_message_id':'701','provider_timestamp':at.isoformat(),'text':text,
        'reply_to_message_id':question['telegram_message_id'],'output_language':language,'semantic':semantic.as_hint()}
    def store(identity,record):
        if identity.endswith('-COMPLETED'): raise RuntimeError('synthetic manager interruption after commit')
        return manager.manager_question_event_store(identity,record)
    with pytest.raises(RuntimeError,match='after commit'):
        manager.handle_manager_question_reply(parsed,issue_gateway_owner_authority(j['owner'],j['owner']),
            semantic,question=question,event_store=store,event_loader=manager._load_manager_question_record)
    before = observations(j)
    assert len(before) == 1
    monkeypatch.setattr(intake,'handle_operational_specialist_message',lambda *_: pytest.fail('must not redispatch'))
    result,status = reply(j,text,701,at,question['telegram_message_id'])
    assert status == 200 and result['status'] == 'rootline_observation_reconciled',result
    assert result['message']['writes_farm_data'] is False and observations(j) == before
    assert manager._load_questions(j['owner'],j['owner']) == []


def test_two_concurrent_camp_clarifications_have_one_immutable_resolution(irrigation):
    j = irrigation; owner = j['owner']; authority = issue_gateway_owner_authority(owner,owner)
    active = [{'domain':'irrigation','entity_id':zone+'12345','mission_id':'SYNTHETIC-'+owner+'-'+zone,
        'card_mission_id':'SYNTHETIC-'+owner+'-'+zone+'-CARD','execution_id':'SYNTHETIC-'+owner+'-'+zone+'-EXEC',
        'execution_started_at':(NOW-timedelta(minutes=5)).isoformat(),'state':'Active',
        'telegram_message_id':str(801+index)} for index,zone in enumerate(('B','C'))]
    original = {'telegram_user_id':owner,'telegram_chat_id':owner,'provider_message_id':'701',
        'provider_timestamp':NOW.isoformat(),'reply_to_message_id':'','text':'The water stopped.',
        'semantic':front.SemanticInterpretation(domain='rootline',intent='irrigation_status',
            message_kind='observation',confidence=.99,irrigation_observation={'state':'stopped'}).as_hint()}
    result,status = continuation.handle_owner_operational_continuation(original,authority,
        lifecycle_loader=lambda *_:([],active,[]),now=NOW)
    assert status == 200
    with psycopg.connect(DSN) as db:
        pending = db.execute("""select review_json->'owner_operational_context'
            from public.sam_live_stock_conversation_review_events
            where review_event_id=%s""",(result['mission_id']+'-PENDING',)).fetchone()[0]
    pending.update({'telegram_message_id':'900','clarification_delivered_at':(NOW+timedelta(seconds=2)).isoformat()})
    barrier = Barrier(2)
    def clarify(index):
        zone = active[index]['entity_id']; at = NOW+timedelta(seconds=5+index)
        parsed = {**original,'provider_message_id':str(702+index),'provider_timestamp':at.isoformat(),
            'reply_to_message_id':'900','text':zone,
            'semantic':front.SemanticInterpretation(domain='rootline',intent='clarification_answer',
                message_kind='confirmation',continuation=True,confidence=.99,entity_refs=(zone,)).as_hint()}
        def store(action,identity,payload):
            barrier.wait(timeout=10)
            return continuation._context_store(action,identity,payload)
        return continuation.handle_owner_operational_continuation(parsed,authority,
            lifecycle_loader=lambda *_:([deepcopy(pending)],active,[]),context_store=store,now=at)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(clarify,index) for index in (0,1)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(status for _,status in results) == [200,409],results
    with psycopg.connect(DSN) as db:
        rows = db.execute("""select review_json->'owner_operational_context'
            from public.sam_live_stock_conversation_review_events where review_event_id=%s""",
            (pending['mission_id']+'-PHYSICAL_STOP_REPORTED',)).fetchall()
    assert len(rows) == 1 and rows[0][0]['observation_provider_message_id'] == '701'
    assert rows[0][0]['owner_evidence'] == 'The water stopped.'
    assert all(result.get('hardware_commands') == 0 for result,_ in results)
