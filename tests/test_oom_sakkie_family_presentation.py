from modules.oom_sakkie.family_presentation import animal_label, date_label, envelope, message
import hashlib
import pytest


def test_presentation_preserves_material_body_and_is_idempotent():
    source = '<b>Birth review</b>\n\n12 born; 11 alive; 1 stillborn. Not recorded.'
    rendered = envelope(source)
    assert rendered == '<b>🌿 Birth review</b>\n\n12 born; 11 alive; 1 stillborn. Not recorded.'
    assert envelope(rendered) == rendered
    warning = envelope('⚠️ <b>Hold</b>\nExpiry 14:30 UTC. Do not confirm.')
    assert warning == '<b>⚠️ Hold</b>\nExpiry 14:30 UTC. Do not confirm.'


def test_canonical_tag_precedes_legacy_display_and_internal_identity_is_not_prose():
    assert animal_label({'pig_id':'PIG-INTERNAL','tag_number':'Mona','sow_display_name':'Old name'}) == 'Mona'
    assert animal_label({'pig_id':'PIG-INTERNAL','name':'Mona','tag_number':'41'}) == 'Mona'
    assert animal_label({'pig_id':'PIG-INTERNAL','label':'PIG-INTERNAL'}) == 'Unknown animal'


def test_protected_label_map_handles_casefold_name_tag_and_fallback_collisions():
    from modules.oom_sakkie.family_presentation import protected_animal_labels
    rows=[{'pig_id':'A','name':'Mona','tag_number':'S-1'},
        {'pig_id':'B','name':'mona','tag_number':'S-2'},
        {'pig_id':'C','tag_number':'s-1'}]
    labels=protected_animal_labels(rows)
    assert labels=={'A':'A','B':'S-2','C':'C'}
    assert protected_animal_labels(rows+rows)==labels
    assert protected_animal_labels([{'pig_id':'PIG-1','name':'PIG-1','tag_number':'146'}])=={'PIG-1':'146'}
    with pytest.raises(ValueError,match='identity_conflict'):
        protected_animal_labels(rows+[{'pig_id':'A','name':'Different'}])


def test_calendar_dates_and_escaped_typed_facts_keep_unknown_distinct_from_zero():
    assert date_label('2026-08-26') == '26 August 2026'
    assert date_label('2026-08-26', language='af') == '26 Augustus 2026'
    assert date_label('Unknown') == 'Unknown'
    rendered = message('Mona & May', bullets=['12 born', 'Unknown father'],
        status='Unconfirmed — not recorded.', question='Are these details correct?')
    assert 'Mona &amp; May' in rendered and '• Unknown father' in rendered
    assert '0 father' not in rendered


@pytest.mark.parametrize('language', ['en','af'])
def test_old_mortality_completion_and_changed_replay_status_stays_quiet(monkeypatch,language):
    from modules.oom_sakkie import family_presentation as presentation
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from modules.oom_sakkie.herdmaster_health_loss_runtime import mortality_completion_recovery_result
    from tests.test_oom_sakkie_family_message_lifecycle import Memory, PARSED
    memory=Memory();parsed={**PARSED,'output_language':language}
    old=('<b>VARK 126 AANGETEKEN</b>\n\nDie bevestigde afsterwe is een keer aangeteken en die vark is nie meer op die plaas beskikbaar nie.'
         if language=='af' else '<b>126 - DEATH RECORDED</b>\n\nThe confirmed death was recorded once and the pig is no longer available on farm.')
    stored={'success':True,'status':'mortality_lifecycle_recorded','answer':old,
        'canonical_readback_verified':True,'recipient_render_contract':'specialist_structured_recipient_v1',
        'recipient_language':language,'owner_visible_completion_policy':'verified_edit_or_new_message'}
    kwargs=dict(specialist='HERDMASTER',mission_id='OLD-COMPLETION',event_store=memory.store,sender=memory.send,editor=memory.edit)
    with monkeypatch.context() as old_runtime:
        old_runtime.setattr(presentation,'envelope',lambda text,**_:text)
        assert deliver_family_result(parsed,stored,**kwargs)['telegram_sends']==1
    current=mortality_completion_recovery_result({**stored,'status':'completed'}, {'identity':{'tag_number':'126'}},language)
    result=deliver_family_result(parsed,current,**kwargs)
    assert result['status']=='family_message_completion_replayed_noop'
    assert len(memory.sent)==1 and memory.edited==[]
    assert memory.sent[0][1]==old


def test_actual_first_treatment_af_product_and_notes_survive_delivery():
    from modules.oom_sakkie.herdmaster_litter_first_treatment_runtime import _preview_answer, _answer
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_oom_sakkie_family_message_lifecycle import Memory, PARSED
    packet={'sow_name':'Mona','sow_pig_id':'PIG-INTERNAL','litter_id':'LITTER-1',
        'action_date':'2026-08-26','total_count':2,'pig_ids':['PIG-A','PIG-B'],
        'products':[{'product_name':'Iron supplement','product_id':'MED-1'}],
        'dose':1,'dose_unit':'ml','route':'intramuscular','batch_lot_number':'LOT-1',
        'notes':'Left side as reported','earmarked':False}
    result=_answer('first_treatment_committed',_preview_answer(packet,'af'),success=True,
        canonical_readback_verified=True)
    memory=Memory();delivered=deliver_family_result({**PARSED,'output_language':'af'},result,
        specialist='HERDMASTER',event_store=memory.store,sender=memory.send)
    assert delivered['telegram_sends']==1
    text=memory.sent[0][1]
    for detail in ['Iron supplement','1 ml','intramuscular','LOT-1','Left side as reported','26 Augustus 2026','2 huidige varkies']:
        assert detail in text
    assert 'PIG-' not in text and text.startswith('<b>🌿 Eerste behandeling</b>')


def test_plain_transport_keeps_known_html_as_readable_text():
    from modules.oom_sakkie.telegram_direct import format_telegram_owner_reply
    answer=message('Mona & May',bullets=['118 kg','Unconfirmed — not recorded.'],emoji='🐷')
    rendered=format_telegram_owner_reply({'answer':answer})
    assert rendered.startswith('🐷 Mona & May') and '<b>' not in rendered and '&amp;' not in rendered
    assert '118 kg' in rendered and 'Unconfirmed — not recorded.' in rendered


def test_grouped_weights_reject_indistinguishable_visible_labels():
    from modules.oom_sakkie.owner_response_composer import compose_weight_preview
    with pytest.raises(ValueError,match='identity_ambiguous'):
        compose_weight_preview([{'pig_id':'PIG-A','tag_number':'Mona','weight_kg':100},
            {'pig_id':'PIG-B','tag_number':'Mona','weight_kg':101}])


def test_owner_task_journal_and_reconciler_bind_actual_presented_bytes():
    from modules.oom_sakkie.owner_task_lifecycle import _deliver_once
    from tests.test_oom_sakkie_owner_task_lifecycle import Rail,request
    rail=Rail();req=request();envelope_value={'owner_user_id':'42','chat_id':'42',
        'message_id':'123','provider_message_at':'2026-10-01T12:00:00+00:00','item_kind':'text'}
    sent=[];proofs=[]
    def failed(chat,text,purpose):sent.append(text);return {'success':False}
    options=dict(task_id='STYLE-TASK',request=req,envelope=envelope_value,
        record=rail.record,purpose='ack',state='received',text='<b>Received</b>\n2 photos retained.',detail={})
    _deliver_once(existing=[],sender=failed,reconciler=None,**options)
    attempt=next(row for row in rail.events.values() if row['event_id'].endswith('-ATTEMPT'))
    assert attempt['detail']['text_sha256']==hashlib.sha256(sent[0].encode()).hexdigest()
    assert sent[0].startswith('<b>🌿 Received</b>')
    _deliver_once(existing=list(rail.events.values()),sender=failed,
        reconciler=lambda proof:proofs.append(proof) or {'status':'ambiguous'},**options)
    assert proofs[0]['text_sha256']==attempt['detail']['text_sha256'] and len(sent)==1


def test_same_inbound_held_card_still_becomes_verified_completion():
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_oom_sakkie_family_message_lifecycle import Memory, PARSED
    memory=Memory();kwargs=dict(specialist='HERDMASTER',mission_id='HELD',
        event_store=memory.store,sender=memory.send,editor=memory.edit)
    deliver_family_result(PARSED,{'success':False,'status':'readback_unavailable','answer':'Result not yet proved.'},**kwargs)
    completed={'success':True,'status':'completed','answer':'<b>Birth recorded</b>\n11 born alive.',
        'canonical_readback_verified':True,'owner_visible_completion_policy':'verified_edit_or_new_message'}
    result=deliver_family_result(PARSED,completed,**kwargs)
    assert result['telegram_edits']==1 and len(memory.sent)==1
    assert '11 born alive' in memory.edited[0][2]


def test_lost_owner_task_claim_does_not_reconcile_unproven_projection():
    from modules.oom_sakkie.owner_task_lifecycle import _deliver_once
    from tests.test_oom_sakkie_owner_task_lifecycle import request
    result=_deliver_once('LOST',request(),{'owner_user_id':'42','chat_id':'42',
        'message_id':'123','provider_message_at':'2026-10-01T12:00:00+00:00','item_kind':'text'},[],
        lambda _: {'success':True,'created':False},
        lambda *_:pytest.fail('loser sent'),lambda *_:pytest.fail('unproven winner hash'),
        purpose='ack',state='received',text='<b>Received</b>\n2 photos.',detail={})
    assert result==(0,False)
    legacy='<b>Received</b>\n2 photos.'
    token=hashlib.sha256(b'LOST|ack').hexdigest()[:20].upper()
    winner={'event_id':f'OOM-TASK-DELIVERY-{token}-ATTEMPT',
        'detail':{'text_sha256':hashlib.sha256(legacy.encode()).hexdigest()}}
    seen=[]
    replay=_deliver_once('LOST',request(),{'owner_user_id':'42','chat_id':'42'},[winner],
        lambda _:pytest.fail('ambiguous winner receipt changed'),lambda *_:pytest.fail('duplicate send'),
        lambda proof:seen.append(proof) or {'status':'ambiguous'},
        purpose='ack',state='received',text=legacy,detail={})
    assert replay==(0,False) and seen[0]['text_sha256']==winner['detail']['text_sha256']


@pytest.mark.parametrize('winner_state',['delivered','ambiguous','conclusively_absent'])
def test_dispatch_claim_loser_defers_then_reconciles_fresh_winner_without_duplicate(winner_state):
    from modules.oom_sakkie.owner_task_lifecycle import handle_owner_task_input
    from tests.test_oom_sakkie_owner_task_lifecycle import Rail,request,photo,ENV,NOW,RESULT_HTML
    rail=Rail(); req=request(1,['4'*64]); req.pop('prepared_result_sha256')
    base={'mission_id':'M1','target_worker_id':'rootline-agent','release_digest':'d'*64}
    events=[{**base,'event_id':'a','state':'release_requested','occurred_at':'2026-08-01T17:00:00+00:00'},
        {**base,'event_id':'b','state':'released','occurred_at':'2026-08-01T17:00:01+00:00','acknowledgement_deadline_at':'2026-08-01T17:01:00+00:00','start_deadline_at':'2026-08-01T17:02:00+00:00'},
        {**base,'event_id':'c','state':'delivery_acknowledged','occurred_at':'2026-08-01T17:00:02+00:00','delivery_receipt_id':'r'},
        {**base,'event_id':'d','state':'started','occurred_at':'2026-08-01T17:00:03+00:00','heartbeat_at':'2026-08-01T17:00:03+00:00','activity_observed_at':'2026-08-01T17:00:03+00:00','activity_id':'a'},
        {**base,'event_id':'e','state':'completed','occurred_at':'2026-08-01T17:00:04+00:00','outcome_artifact_id':'o1','outcome_artifact_sha256':'e'*64,'outcome_status':'completed'}]
    packet={'delivery_receipt_id':'r','events':events,'owner_result_html':RESULT_HTML}
    def lost(event):
        result=rail.record(event)
        return {'success':True,'created':False} if event['event_id'].endswith('-DISPATCH-ATTEMPT') else result
    common=dict(environ=ENV,request_loader=lambda _:req,event_loader=rail.load,
        media_reader=lambda *_:{'content_sha256':'4'*64,'readback_verified':True},telegram_sender=rail.send,now=NOW)
    first,code=handle_owner_task_input(photo(11,'u11'),event_recorder=lost,
        specialist_dispatcher=lambda _:pytest.fail('loser dispatched'),
        dispatch_reconciler=lambda _:pytest.fail('loser reconciled stale snapshot'),**common)
    assert code==202 and first['dispatches']==0 and first['results']==0
    assert first['status']=='owner_task_dispatch_delivery_unresolved'
    if winner_state=='delivered':
        attempt=next(row for row in rail.events.values() if row['event_id'].endswith('-DISPATCH-ATTEMPT'))
        rail.record({**attempt,'event_id':attempt['event_id'].removesuffix('-ATTEMPT')+'-DELIVERED',
            'detail':{'dispatch_packet':packet,'delivery_receipt_id':'r'}})
    calls=[]
    def dispatch(_):
        assert winner_state=='conclusively_absent'
        calls.append(1); return packet
    result,code=handle_owner_task_input(photo(11,'u11'),event_recorder=rail.record,
        specialist_dispatcher=dispatch,dispatch_reconciler=lambda _:{'status':winner_state},**common)
    assert calls==([1] if winner_state=='conclusively_absent' else [])
    assert code==(202 if winner_state=='ambiguous' else 200)
    assert len([m for m in rail.messages if m[2]=='completion'])==(0 if winner_state=='ambiguous' else 1)


def test_linked_birth_preview_preserves_recognizable_father_and_mating():
    from modules.oom_sakkie.herdmaster_farrowing_runtime import _preview_answer
    from modules.pig_weights.herdmaster_farrowing_litter_intake import prepare_farrowing_litter_preview
    canonical={'evidence_generation':'E','animals':[
        {'pig_id':'PIG-SOW','name':'Mona','tag_number':'S-A','status':'Active','on_farm':True,'sex':'Female'},
        {'pig_id':'PIG-BOAR','name':'Ben','tag_number':'B-1','status':'Active','on_farm':True,'sex':'Male'}],
        'matings':[{'mating_id':'MATING-1','sow_pig_id':'PIG-SOW','boar_pig_id':'PIG-BOAR','mating_date':'2026-05-07','outcome':'Mated'}], 'litters':[]}
    prepared=prepare_farrowing_litter_preview({'authenticated':True,'authenticated_principal_id':'42',
        'provider_message_id':'123','reported_on':'2026-08-26','language':'en',
        'farrowing_litter':{'sow_ref':'Mona','farrowing_date':'2026-08-26','total_born':12,
            'born_alive':11,'stillborn':1,'mummified':0,'died_after_live_birth':0}},canonical)
    assert prepared['success'] and prepared['preview']['father_pig_id']=='PIG-BOAR'
    text=_preview_answer(prepared,canonical=canonical)
    assert 'Father: Ben' in text and '7 May 2026' in text and 'MATING-1' in text
    assert 'PIG-BOAR' not in text and '11 born alive' in text and '0 died after live birth' in text
    assert 'PIG-BOAR' in _preview_answer(prepared)


@pytest.mark.parametrize('language',['en','af'])
def test_retry_authority_uses_final_localized_provider_bytes(monkeypatch,language):
    from modules.oom_sakkie import family_message_lifecycle as family
    from modules.oom_sakkie.herdmaster_request_runtime import delivery_retry_authority_for
    from tests.test_oom_sakkie_family_message_lifecycle import Memory, PARSED
    memory=Memory();parsed={**PARSED,'output_language':language}
    result={'success':True,'status':'preview_ready','answer':'<b>Preview</b>\nReview the bound details.',
        'mission_id':'RETRY','card_mission_id':'RETRY','weight_date':'2026-08-26'}
    kwargs=dict(specialist='HERDMASTER',mission_id='RETRY',card_mission_id='RETRY',event_store=memory.store)
    seen=[]
    def failed(chat,text,**_):seen.append(text);return {'success':False,'delivery_definitely_not_sent':True}
    family.deliver_family_result(parsed,result,sender=failed,**kwargs)
    monkeypatch.setattr(family,'load_family_lifecycle',lambda _:list(memory.rows.values()))
    authority=delivery_retry_authority_for(result,parsed=parsed)
    second=family.deliver_family_result(parsed,result,delivery_retry_authority=authority,sender=memory.send,**kwargs)
    assert second['telegram_sends']==1 and memory.sent[0][1]==seen[0]


def test_completed_brief_restyle_keeps_same_generation_and_provider_card():
    from modules.oom_sakkie.family_message_lifecycle import replace_current_brief
    from tests.test_oom_sakkie_family_message_lifecycle import Memory, PARSED
    memory=Memory();memory.rows['prior']={'event_id':'prior','state':'delivered',
        'card_mission_id':'DAILY','telegram_message_id':'100','owner_user_id':'42','chat_id':'42',
        'specialist_identity':'OOM_SAKKIE','task_state':'daily_farm_manager_ready'}
    kwargs=dict(mission_id='DAILY:G2',card_mission_id='DAILY',previous_message_id='100',
        generation_digest='a'*64,event_store=memory.store,sender=memory.send,
        deleter=lambda *_:{'success':True})
    first=replace_current_brief(PARSED,{'answer':'<b>Old plan</b>\nCheck the tank.',
        'status':'daily_farm_manager_ready','rolling_brief_replacement':True},**kwargs)
    assert first['telegram_sends']==1
    replay=replace_current_brief(PARSED,{'answer':'<b>🌿 Farm plan</b>\n• Check the tank.',
        'status':'daily_farm_manager_ready','rolling_brief_replacement':True},**kwargs)
    assert replay['telegram_sends']==0 and replay['telegram_edits']==0 and len(memory.sent)==1
