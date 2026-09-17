"""Actual services, runtime and PostgreSQL; only synthetic authority and input."""
import copy
from datetime import datetime, timezone, timedelta
import uuid

import psycopg
import pytest

from modules.pig_weights import pig_weights_service as service, farm_supabase_read_service as reader
from modules.oom_sakkie import herdmaster_litter_first_treatment_runtime as runtime
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import bind_claim_card
from tests.first_treatment_test_support import database_url, seed, cleanup, facts, payload, state


@pytest.fixture
def litter():
    j = seed()
    yield j
    cleanup(j)


def test_shared_service_preserves_actual_facts_history_and_exact_replay(litter):
    j = litter
    before = state(j)
    preview, code = service.record_litter_newborn_health(j['litter'], **payload(j))
    assert code == 200 and preview['success'], preview
    assert state(j) == before
    assert preview['preview']['dose'] == 1 and preview['preview']['dose_unit'] == 'ml'
    confirmed = payload(j, dry_run=False, confirmed=True, confirmation_binding=preview['confirmation_binding'])
    result, code = service.record_litter_newborn_health(j['litter'], **confirmed)
    assert code == 200 and result['canonical_readback_verified'], result
    after = state(j)
    assert after['litter'] == before['litter'] and after['sow'] == before['sow']
    assert len(after['medical']) == 2 and len(after['receipts']) == 1
    assert all(float(row[3]) == 1 and row[4] == 'ml' and row[6] == confirmed['changed_by'] for row in after['medical'])
    detail = reader.get_litter_detail(j['litter'])
    assert detail['first_treatment_receipt_verified'] is True
    assert detail['first_treatment_receipt']['male_count'] == detail['first_treatment_receipt']['female_count'] == 1
    assert all(not pig['sex'] for pig in detail['piglets'])
    assert all(pig['earmarked'] and pig['earmark_date'] == j['date'] for pig in detail['piglets'][:2])
    assert after['pigs'][2:] == before['pigs'][2:]
    replay, code = service.record_litter_newborn_health(j['litter'], **confirmed)
    assert code == 200 and replay['replay_withheld'] and replay['treatment_rows_created'] == 0
    assert state(j) == after


def parsed(actor, sequence, supplied=None, **semantic):
    return {'telegram_user_id':actor,'telegram_chat_id':actor,'telegram_chat_type':'private',
        'provider_message_id':str(sequence),'provider_timestamp':datetime.now(timezone.utc).isoformat(),
        'text':'SIMULATED ordinary report ' + str(sequence),'output_language':'af',
        'semantic':{'domain':'herd_management','intent':'record_litter_first_treatment','confidence':0.99,
            'message_kind':'observation','litter_first_treatment':supplied, **semantic}}


def test_runtime_retains_short_correction_and_commits_exact_card(litter):
    j = litter
    actor = str(7500000000 + int(uuid.uuid4().hex[:6], 16))
    authority = issue_gateway_owner_authority(actor,actor,principal_role='farm_manager',capabilities={'treatment'})
    initial = facts(j)
    initial.pop('action_date')
    before = state(j)
    result, code = runtime.handle_litter_first_treatment_message(parsed(actor,1001,initial),authority)
    assert code == 200 and result['question_count'] == 1, result
    assert 'datum' in result['answer'] and result['retained_facts']['dose'] == '1 ml'
    preview, code = runtime.handle_litter_first_treatment_message(parsed(actor,1002,{'action_date':'gister'},continuation=True),authority)
    assert code == 200 and preview.get('callback_token'), preview
    assert j['date'] in preview['answer'] and '1.0 ml' in preview['answer'] and '1 manlik' in preview['answer']
    assert preview['retained_facts']['earmarked'] is True and state(j) == before
    bound = bind_claim_card(preview['callback_token'], '1003')
    assert bound
    confirm = parsed(actor,1004,None,message_kind='confirmation',continuation=True)
    result, code = runtime.handle_litter_first_treatment_message(confirm, authority)
    assert code == 200 and result['success'] and result['canonical_readback_verified'], result
    assert result['changed_by'] == actor and result['recipient_language'] == 'af'
    after = state(j)
    replay, code = runtime.handle_litter_first_treatment_message(confirm, authority)
    assert code == 200 and replay['replay_withheld'], replay
    assert state(j) == after


@pytest.mark.parametrize('change',[
    {'action_date_value':''},{'action_date_value':'2099-01-01'},{'action_date_value':'2024-01-01'},
    {'dose':None},{'dose':'1 mg','dose_unit':'ml'},{'route':''},{'antiparasitic_product_id':''},
    {'batch_lot_number':''},{'male_count':2},{'female_count':None},{'total_count':3},
])
def test_shared_service_missing_or_conflicting_facts_does_not_write(litter,change):
    before = state(litter)
    result,code = service.record_litter_newborn_health(litter['litter'],**payload(litter,**change))
    assert code == 409 and not result['success'], result
    assert state(litter) == before


def test_ambiguous_identity_then_unique_litter_keeps_facts(litter):
    j = litter
    other = seed()
    try:
        with psycopg.connect(database_url()) as db:
            db.execute('update public.pigs set pig_name=%s where pig_id=%s',(j['name'],other['sow']))
        actor = str(7510000000 + int(uuid.uuid4().hex[:6],16))
        authority = issue_gateway_owner_authority(actor,actor,principal_role='farm_manager',capabilities={'treatment'})
        first,code = runtime.handle_litter_first_treatment_message(parsed(actor,2001,facts(j,sow_ref=j['name'])),authority)
        assert code == 200 and first['question_count'] == 1 and 'sog' in first['answer'],first
        second,code = runtime.handle_litter_first_treatment_message(parsed(actor,2002,{'sow_ref':j['sow']},continuation=True),authority)
        assert code == 200 and second.get('callback_token') and second['retained_facts']['dose'] == '1 ml',second
    finally:
        cleanup(other)


@pytest.mark.parametrize('authority_kind',['foreign_actor','foreign_chat','no_permission','forged_object'])
def test_typed_runtime_requires_exact_actor_chat_and_treatment_authority(litter,authority_kind):
    from types import SimpleNamespace
    actor = str(7520000000 + int(uuid.uuid4().hex[:6],16))
    owner = '999999' if authority_kind == 'foreign_actor' else actor
    chat = '999999' if authority_kind == 'foreign_chat' else owner
    authority = issue_gateway_owner_authority(owner,chat,principal_role='farm_manager',
        capabilities={'weaning'} if authority_kind == 'no_permission' else {'treatment'})
    if authority_kind == 'forged_object':
        authority = SimpleNamespace(owner_user_id=actor,private_chat_id=actor,capabilities={'treatment'})
    before = state(litter)
    result,code = runtime.handle_litter_first_treatment_message(parsed(actor,3001,facts(litter)),authority)
    assert code == 403 and not result['writes_farm_data'] and state(litter) == before


def test_correction_invalidates_old_card_and_provider_chronology_is_preserved(litter):
    from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
    actor = str(7530000000 + int(uuid.uuid4().hex[:6],16))
    authority = issue_gateway_owner_authority(actor,actor,principal_role='farm_manager',capabilities={'treatment'})
    initial = parsed(actor,4001,facts(litter))
    result,code = runtime.handle_litter_first_treatment_message(initial,authority)
    assert result.get('callback_token'),result
    assert bind_claim_card(result['callback_token'],'4002')
    correction = parsed(actor,4003,{'route':''},continuation=True,message_kind='correction')
    changed,code = runtime.handle_litter_first_treatment_message(correction,authority)
    assert changed['question_count'] == 1
    stale = parsed(actor,4004,None)
    stale['reply_to_message_id'] = '4002'
    result,code = handle_protected_action_input(stale,authority,callback_data=result['reply_markup']['inline_keyboard'][0][0]['callback_data'])
    assert not result.get('writes_farm_data') and not state(litter)['receipts']
    older = parsed(actor,4000,{'route':'injection'},continuation=True)
    older['provider_timestamp'] = initial['provider_timestamp']
    result,code = runtime.handle_litter_first_treatment_message(older,authority)
    assert code == 409 and result['status'] == 'first_treatment_out_of_order'
    conflicting = copy.deepcopy(correction); conflicting['text'] += ' changed'
    result,code = runtime.handle_litter_first_treatment_message(conflicting,authority)
    assert code == 409 and result['status'] == 'first_treatment_provider_replay_conflict'


def test_fresh_preview_after_commit_or_partial_evidence_is_contained(litter):
    j = litter
    p = payload(j)
    proposed,code = service.record_litter_newborn_health(j['litter'],**p)
    result,code = service.record_litter_newborn_health(j['litter'],**{**p,'dry_run':False,'confirmed':True,'confirmation_binding':proposed['confirmation_binding']})
    assert code == 200
    assert service.record_litter_newborn_health(j['litter'],**p)[1] == 409
    with psycopg.connect(database_url()) as db:
        db.execute('delete from public.pig_medical_events where pig_id=%s',(j['pigs'][0],))
    detail = reader.get_litter_detail(j['litter'])
    assert detail['first_treatment_partial'] and not detail['first_treatment_complete']
    before = state(j)
    assert service.record_litter_newborn_health(j['litter'],**p)[1] == 409
    assert service.skip_litter_first_treatment(j['litter'],'synthetic-manager')[1] == 409
    assert state(j) == before


def test_generic_due_cases_and_explicit_skip_retirement_use_actual_source(litter,monkeypatch):
    from modules.oom_sakkie.manager_case_sources import _herdmaster
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','990000')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','990000')
    j = litter
    def cases():
        return {row['dedupe_key']:row for row in _herdmaster(datetime.now(timezone.utc))}
    key = 'herdmaster:litter-first-treatment:' + j['litter']
    source = cases()
    assert key in source and source[key]['physical_work_ready'] is True,source
    result,code = service.skip_litter_first_treatment(j['litter'],'synthetic-treatment-manager','Synthetic explicit skip')
    assert code == 200 and result['first_treatment_skipped'],result
    assert key not in cases()
    detail = reader.get_litter_detail(j['litter'])
    assert detail['first_treatment_skipped'] and detail['first_treatment_skipped_by'] == 'synthetic-treatment-manager'
    assert not state(j)['medical'] and not state(j)['receipts']


def test_generic_due_retires_on_commit_and_reopens_for_incomplete_operation(litter,monkeypatch):
    from modules.oom_sakkie.manager_case_sources import _herdmaster
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','990000')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','990000')
    j = litter
    other = seed()
    key = 'herdmaster:litter-first-treatment:' + j['litter']
    def cases():
        return {row['dedupe_key']:row for row in _herdmaster(datetime.now(timezone.utc))}
    try:
        assert key in cases()
        p = payload(j,deworming_product_id=other['product'])
        proposed,code = service.record_litter_newborn_health(j['litter'],**p)
        assert code == 200,proposed
        assert service.record_litter_newborn_health(j['litter'],**{**p,'dry_run':False,'confirmed':True,'confirmation_binding':proposed['confirmation_binding']})[1] == 200
        assert key not in cases()
        with psycopg.connect(database_url()) as db:
            db.execute('delete from public.pig_medical_events where pig_id=%s and product_id=%s',(j['pigs'][0],j['product']))
        detail = reader.get_litter_detail(j['litter'])
        assert detail['first_treatment_partial']
        projected = cases()
        assert key in projected and projected[key]['task_class'] == 'status_reconciliation',projected.get(key)
    finally:
        cleanup(j)
        cleanup(other)
