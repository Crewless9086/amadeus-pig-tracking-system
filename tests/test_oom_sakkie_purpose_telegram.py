"""Owner-facing Telegram purpose journey without providers or model calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
from modules.oom_sakkie import herdmaster_purpose_telegram as runtime
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

NOW = datetime.now(timezone.utc)


def context(groups=3, members=2):
    cases, recs, cohorts = [], {}, []
    for group in range(groups):
        ids = [f"PIG-G{group}-{i}" for i in range(members)]
        binding = dict(case_id=f"CASE-{group}", generation=1, evidence_digest="a"*64,
            cohort_key=f"LITTER-{group}", material_digest="b"*64, member_ids=ids,
            member_count=members, membership_digest=runtime.digest(ids))
        cases.append(dict(case_id=binding["case_id"], generation=1, evidence_digest="a"*64,
            dedupe_key="herdmaster:purpose-review:"+binding["cohort_key"], available=True, membership=binding))
        cohorts.append(dict(cohort_key=binding["cohort_key"], case_key="herdmaster:purpose-review:"+binding["cohort_key"], label=f"Sow {group}"))
        for i, pig in enumerate(ids):
            recs[pig] = dict(pig_id=pig, tag_number=f"T{group}{i}", proposed_purpose="Sale" if i%2 else "Grow_Out",
                suggested_purpose="LivestockSale" if i%2 else "GrowOut", suggested_purpose_confidence="Medium",
                suggested_purpose_reason="Recent post-weaning growth supports this review.", review_status="needs_owner_decision",
                readiness_reason="Fresh weight recorded", latest_weight_date=NOW.date().isoformat(), latest_weight_kg=20,
                growth_class="Good", litter_quality="Good", reasoning=dict(confidence=.92,advisory_only=True,
                    outcome="purpose_review",missing_data=[],contradictions=[]))
    return dict(cases=cases,recommendations=recs,snapshot={"purpose_work":{"cohorts":cohorts}})


class MemoryClaims:
    def __init__(self): self.rows={}; self.counter=0; self.completed=[]
    def create(self, **kw):
        digest=runtime.claims.canonical_preview_digest(kw['action_kind'],kw['preview_payload'])
        for token,row in self.rows.items():
            if row['mission_id']==kw['mission_id'] and row['preview_digest']==digest:
                return dict(success=True,callback_token=token,preview_digest=digest)
            if row['mission_id']==kw['mission_id'] and row['status']=='active':row['status']='changed'
        self.counter+=1;token=f'TOKEN{self.counter:011d}'
        self.rows[token]={**deepcopy(kw),'status':'active','preview_digest':digest,'callback_token':token,
            'preview_card_message_id':'card','confirmation':None}
        return dict(success=True,callback_token=token,preview_digest=digest)
    def callback(self,data,**kw):
        _,token,action=data.split(':');r=self.rows.get(token)
        if not r:return dict(status='protected_callback_unknown'),404
        if kw['owner_user_id']!=r['owner_user_id'] or kw['private_chat_id']!=r['private_chat_id']:return dict(status='protected_callback_unauthorized'),403
        if kw['source_card_message_id']!=r['preview_card_message_id']:return dict(status='protected_callback_card_mismatch'),409
        if r['status']=='expired':return dict(status='protected_callback_expired'),409
        if r['status']=='completed':return dict(status='protected_callback_replayed_noop',result=r['result']),200
        if r['status']=='changed':return {**r,'status':'protected_preview_change_requested'},200
        if action=='details' and r['status']=='active':return {**r,'status':'protected_preview_details'},200
        if action=='cancel':r['status']='cancelled';return {**r,'status':'protected_preview_cancelled'},200
        if action=='confirm':
            if r['status']=='executing' and r['confirmation']!=kw['provider_message_id']:return dict(status='protected_callback_stale'),409
            status='protected_callback_recovered' if r['status']=='executing' else 'protected_callback_claimed'
            r.update(status='executing',confirmation=kw['provider_message_id']);return {**r,'status':status},200
        return dict(status='protected_callback_stale'),409
    def complete(self,token,result,**kw):
        self.rows[token].update(status='completed',result=deepcopy(result));self.completed.append(token)
        return dict(completed=True,result=result)


@pytest.fixture
def journey(monkeypatch):
    memory=MemoryClaims(); data=context()
    monkeypatch.setattr(runtime.claims,'create_claim',memory.create)
    monkeypatch.setattr(runtime.claims,'claim_callback',memory.callback)
    monkeypatch.setattr(runtime.claims,'complete_claim',memory.complete)
    def preview(decisions,**kw):
        effects=[dict(pig_id=d['pig_id'],tag_number=data['recommendations'][d['pig_id']]['tag_number'],
            old_purpose='Unknown',new_purpose=d['purpose'],status='Active',on_farm=True) for d in decisions]
        return dict(success=True,contract_version='herdmaster_purpose_correction_v2',decisions=decisions,effects=effects,
            preview_digest=runtime.digest(effects),confirmation_binding={'synthetic':True},return_to=None),200
    from modules.pig_weights import purpose_correction_batch_service as batches
    monkeypatch.setattr(batches,'preview_correction_batch',preview)
    sequence=[0]
    def invoke(action=None, result=None, **overrides):
        sequence[0]+=1
        parsed=dict(telegram_user_id='42',telegram_chat_id='42',telegram_chat_type='private',provider_message_id=f'input-{sequence[0]}',
            provider_timestamp=NOW.isoformat(),reply_to_message_id='card',output_language='en',text='Review the purpose decisions in Telegram')
        if action:parsed.update(text='',callback_data=runtime.PREFIX+result['callback_token']+':'+action)
        parsed.update(overrides)
        authority=issue_gateway_owner_authority(parsed['telegram_user_id'],parsed['telegram_chat_id'],principal_role=overrides.get('principal_role','owner'))
        return runtime.handle_purpose_message(parsed,authority,now=NOW,context_loader=lambda **kw:data)
    return invoke,memory,data


def actions(result):return [b.get('callback_data','').split(':')[-1] for row in result.get('reply_markup',{}).get('inline_keyboard',[]) for b in row]


def test_three_groups_navigation_and_clean_four_action_initial_card(journey):
    call,store,data=journey
    overview,code=call();assert code==200 and len(actions(overview))==4
    assert all(name in overview['answer'] for name in ('Sow 0','Sow 1','Sow 2'))
    for index in range(3):
        group,code=call(f'group{index}',overview);assert code==200
        assert 'LITTER-' not in group['answer'] and f'Sow {index}' in group['answer']
        assert 'Recent post-weaning growth' in group['answer'] and 'Advisory' in group['answer']
        assert set(actions(group))=={'recommend','change','why','later','overview','cancel'}
        assert group['action_kind']==runtime.REVIEW and group['preview_digest']
        overview,code=call('overview',group);assert code==200
    assert not store.completed


def test_seven_groups_fit_one_overview_page(journey):
    call,store,data=journey;data.update(context(groups=7))
    result,code=call();assert code==200 and len([a for a in actions(result) if a.startswith('group')])==7
    assert not any(a.startswith('page') for a in actions(result))


def test_mixed_advisory_proposal_requires_exact_preview_then_confirmation(journey,monkeypatch):
    call,store,data=journey
    overview,_=call();group,_=call('group0',overview);preview,code=call('recommend',group)
    assert code==200 and preview['action_kind']==runtime.CORRECTION
    payload=store.rows[preview['callback_token']]['preview_payload']
    assert [d['purpose'] for d in payload['batch_preview']['decisions']]==['Grow_Out','Sale']
    assert 'Unknown → Grow out' in preview['answer'] and 'Unknown → Live sale' in preview['answer']
    assert 'confirm' in actions(preview) and not store.completed
    executed=Mock(return_value=({'success':True,'status':'purpose_recorded_verified','answer':'Saved','writes_farm_data':True},200))
    monkeypatch.setattr(runtime,'execute_claimed_purpose',executed)
    saved,code=call('confirm',preview);assert code==200 and saved['success'];executed.assert_called_once()
    replay,code=call('confirm',preview);assert replay['suppress_owner_delivery'] and executed.call_count==1


def test_change_selection_and_purpose_replaces_exact_preview(journey):
    call,store,data=journey
    overview,_=call();group,_=call('group0',overview);selection,_=call('change',group)
    selection,_=call('pick0',selection);preview,code=call('set2',selection)
    p=store.rows[preview['callback_token']]['preview_payload']
    assert code==200 and p['selected']==['PIG-G0-1'] and p['batch_preview']['decisions'][0]['purpose']=='Meat'
    changed,_=call('change',preview);changed,_=call('all',changed);new,_=call('set3',changed)
    assert new['preview_digest']!=preview['preview_digest'] and len(store.rows[new['callback_token']]['preview_payload']['selected'])==2
    stale,code=call('confirm',preview);assert code==409


def test_why_is_read_only_navigation_without_confirmation(journey):
    call,store,data=journey;overview,_=call();group,_=call('group0',overview);before=deepcopy(store.rows)
    why,code=call('why',group)
    assert code==200 and 'growth supports' in why['answer'] and not store.completed
    assert store.rows[why['callback_token']]['action_kind']==runtime.REVIEW


@pytest.mark.parametrize('field,value',[('suggested_purpose_confidence','Low'),('reasoning',{'confidence':.99,'advisory_only':False,'missing_data':['sex']}),
    ('reasoning',{'confidence':.99,'advisory_only':False,'contradictions':['identity']}),('reasoning',{'confidence':True}),
    ('reasoning',{'confidence':float('nan')}),('proposed_purpose','Unrecognized')])
def test_unproven_recommendation_never_becomes_grouped_suggestion(journey,field,value):
    call,store,data=journey;data['recommendations']['PIG-G0-0'][field]=value
    overview,_=call();group,_=call('group0',overview)
    assert 'recommend' not in actions(group)
    result,code=call('recommend',group);assert code==409 and not store.completed


@pytest.mark.parametrize('change',['generation','digest','members','unavailable','recommendation'])
def test_changed_context_refuses_stale_card(journey,change):
    call,store,data=journey;overview,_=call();group,_=call('group0',overview)
    if change=='generation':data['cases'][0]['membership']['generation']=2
    elif change=='digest':data['cases'][0]['membership']['evidence_digest']='c'*64
    elif change=='members':data['cases'][0]['membership']['member_ids'].pop()
    elif change=='unavailable':data['cases'][0]['available']=False
    else:data['recommendations']['PIG-G0-0']['suggested_purpose_reason']='Changed age evidence'
    result,code=call('why',group);assert code==409 and not store.completed


@pytest.mark.parametrize('override',[{'telegram_user_id':'99','telegram_chat_id':'99'}, {'reply_to_message_id':'foreign'},
    {'telegram_chat_type':'group'}, {'principal_role':'farm_manager'}])
def test_foreign_owner_card_chat_role_refused(journey,override):
    call,store,data=journey;overview,_=call();result,code=call('group0',overview,**override)
    assert code>=400 and not store.completed


def test_expired_and_altered_payload_refused(journey):
    call,store,data=journey;overview,_=call();row=store.rows[overview['callback_token']]
    row['status']='expired';assert call('group0',overview)[1]==409
    row['status']='active';row['preview_payload']['cases'][0]['available']=False
    assert call('group0',overview)[0]['status']=='purpose_preview_digest_mismatch'


def test_review_later_explicit_date_is_separately_confirmed(journey,monkeypatch):
    call,store,data=journey;overview,_=call();group,_=call('group0',overview);dates,_=call('later',group)
    choices=[a for a in actions(dates) if a.startswith('date')];assert len(choices)==3 and not store.completed
    deferred,code=call(choices[0],dates);assert code==200 and '08:00 SAST' in deferred['answer']
    assert actions(deferred)[0]=='confirm' and store.rows[deferred['callback_token']]['action_kind']==runtime.REVIEW


def test_large_selected_group_requires_all_effect_pages(journey):
    call,store,data=journey;data.update(context(members=13))
    overview,_=call();group,_=call('group0',overview);preview,_=call('recommend',group)
    assert 'confirm' not in actions(preview)
    for page in (1,2):preview,_=call(f'page{page}',preview)
    assert 'confirm' in actions(preview)
    assert len(store.rows[preview['callback_token']]['preview_payload']['batch_preview']['effects'])==13
    assert all(len(b['callback_data'].encode())<=64 for row in preview['reply_markup']['inline_keyboard'] for b in row)


def test_completion_failure_never_says_nothing_recorded(journey,monkeypatch):
    call,store,data=journey;overview,_=call();group,_=call('group0',overview);preview,_=call('recommend',group)
    monkeypatch.setattr(runtime,'execute_claimed_purpose',lambda *a,**kw:({'success':True,'status':'purpose_recorded_verified','answer':'Verified saved','writes_farm_data':True},200))
    monkeypatch.setattr(runtime.claims,'complete_claim',Mock(side_effect=RuntimeError('response lost')))
    result,code=call('confirm',preview)
    assert code==503 and result['recovery_required'] and result['writes_farm_data'] is None
    assert 'may have completed' in result['answer'] and 'Nothing' not in result['answer']


@pytest.mark.parametrize('phrase',['Review the purpose decisions in Telegram','Show me the purpose groups','Can we review their purposes?',
    'Hersien die doelkeuses asseblief','Wys die doelbesluite','Open purpose review'])
def test_natural_opening_is_deterministic(phrase):
    assert runtime.applicable({'text':phrase})


def test_unrelated_facts_are_not_routed_to_purpose_review():
    assert not runtime.applicable({'text':'Teena body condition score 3 observed today'})


def test_afrikaans_final_family_render_preserves_bound_answer(journey):
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
    call,store,data=journey;overview,code=call(output_language='af')
    result=localize_recipient_result({'output_language':'af'},overview,'HERDMASTER')
    assert code==200 and result['answer']==overview['answer'] and 'Doelbesluite' in result['answer']
    assert 'recipient_language_render_unrecognized' not in result


def test_plain_confirm_never_approves_purpose(journey,monkeypatch):
    from modules.oom_sakkie import protected_action_runtime as protected
    call,store,data=journey;overview,_=call()
    monkeypatch.setattr(protected,'resolve_natural_confirmation',lambda **kw:store.rows[overview['callback_token']])
    result,code=protected.handle_protected_action_input({'telegram_user_id':'42','telegram_chat_id':'42','text':'confirm'},issue_gateway_owner_authority('42','42'))
    assert code==409 and result['status']=='purpose_exact_button_required'


def test_why_explanations_for_all_thirteen_animals_are_navigable(journey):
    call,store,data=journey;data.update(context(members=13))
    overview,_=call();group,_=call('group0',overview);why,code=call('why',group)
    visible=why['answer']
    for page in (1,2):why,code=call(f'page{page}',why);assert code==200;visible+=why['answer']
    assert all('T0'+str(i) in visible for i in range(13)) and 'back' in actions(why) and not store.completed


def test_typed_semantic_synonym_only_opens_read_only_overview(journey):
    from modules.oom_sakkie.semantic_front_door import SemanticInterpretation
    semantic=SemanticInterpretation(domain='herd_management',intent='purpose_review_telegram',message_kind='question',requested_action='open_current_purpose_review')
    assert runtime.applicable({'text':"What should we do with Sophie's piglets?"},semantic)
    assert not runtime.applicable({'text':'approve everything'},SemanticInterpretation(domain='herd_management',intent='purpose_review_telegram',message_kind='confirmation',requested_action='open_current_purpose_review'))


def test_semantic_media_contract_is_not_replaced_by_purpose_intent(monkeypatch):
    from modules.oom_sakkie import semantic_front_door as semantic
    # A disabled media interpreter must retain its pre-existing no-model result;
    # it has no parsed Telegram input and must not access an undefined variable.
    result=semantic.interpret_media_owner_context('purpose review','a'*64,environ={})
    assert result is None


def test_farm_date_is_johannesburg_for_supplied_snapshot(monkeypatch):
    from modules.pig_weights import pig_weights_service as service
    seen=[]
    monkeypatch.setattr(service,'get_pig_allocation_readiness',lambda **kw:seen.append(kw['today']) or {'success':True,'pigs':[]})
    monkeypatch.setattr(service,'get_herdmaster_pig_allocation_alerts',lambda **kw:{'decisions':[]})
    runtime.recommendation_rows({},datetime(2026,10,4,23,30,tzinfo=timezone.utc))
    assert seen[0].isoformat()=='2026-10-05'


def test_unavailable_group_keeps_unique_canonical_name_without_navigation(journey):
    call,store,data=journey
    data['cases'][1].update(available=False,membership=None)
    overview,code=call()
    assert code==200 and 'Sow 1' in overview['answer']
    assert 'group1' not in actions(overview)
    assert overview['writes_farm_data'] is False
    data['snapshot']['purpose_work']['cohorts'].append(dict(data['snapshot']['purpose_work']['cohorts'][1],label='Conflicting sow'))
    overview,code=call()
    assert code==200 and 'Group 2' in overview['answer'] and 'group1' not in actions(overview)


@pytest.mark.parametrize('language',['en','af'])
@pytest.mark.parametrize('reason',['protected_callback_expired','purpose_preview_digest_mismatch','purpose_preview_claim_unavailable','purpose_navigation_stale'])
def test_refusals_keep_owned_language_and_never_invite_confirmation(language,reason):
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
    refused,code=runtime._refusal(reason,language=language)
    rendered=localize_recipient_result({'output_language':language},refused,'HERDMASTER')
    assert code==409 and rendered['answer']==refused['answer']
    assert not rendered.get('recipient_language_render_unrecognized')
    assert 'bevestig' not in rendered['answer'].lower() and 'confirm' not in rendered['answer'].lower()
    assert not rendered.get('reply_markup') and rendered['writes_farm_data'] is False


@pytest.mark.parametrize('language,count,expected',[('en',1,'the purpose for 1 animal.'),
    ('en',2,'the purposes for 2 animals.'),('af',1,'Die doel van 1 dier is'),('af',2,'Die doele van 2 diere is')])
def test_verified_save_uses_localized_singular_and_plural(monkeypatch,language,count,expected):
    from modules.pig_weights import purpose_correction_batch_service as batches
    decisions=[dict(pig_id=f'PIG-SYNTHETIC-{i}',purpose='Sale',reason='Synthetic owner review',note='') for i in range(count)]
    effects=[dict(pig_id=d['pig_id'],old_purpose='Unknown',new_purpose='Sale') for d in decisions]
    preview=dict(contract_version=batches.CONTRACT_VERSION,decisions=decisions,effects=effects,
        preview_digest=batches._preview_digest(decisions,effects,''),return_to=None)
    envelope={k:preview[k] for k in ('contract_version','decisions','effects','preview_digest','return_to')}
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def cursor(self):return self
        def execute(self,*_):pass
        def fetchone(self):return ('B-SYNTHETIC','executed',envelope,'42',batches._decision_hash(decisions))
    execute=Mock(return_value=({'success':True,'rows_updated':0,'canonical_readback':[
        dict(pig_id=d['pig_id'],purpose=d['purpose'],status='Active',on_farm=True) for d in decisions]},200))
    monkeypatch.setattr(batches,'execute_correction_batch',execute)
    claimed=dict(action_kind=runtime.CORRECTION,callback_token='SYNTHETIC-TOKEN',preview_digest='a'*64,
        preview_payload=dict(mode='preview',batch_preview=preview,seen_pages=[0],language=language))
    result,code=runtime.execute_claimed_purpose(claimed,{'telegram_user_id':'42'},now=NOW,connect=Connection)
    assert code==200 and result['status']=='purpose_recorded_verified'
    assert expected in result['answer'] and result['writes_farm_data'] is False
    execute.assert_called_once()
