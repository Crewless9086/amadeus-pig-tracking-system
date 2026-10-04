"""Purpose decisions retain owner follow-through without inventing missing facts."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import time
from unittest.mock import Mock

import pytest

from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import herdmaster_purpose_decision as purpose
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import family_message_lifecycle as family
from tests.test_herdmaster_purpose_work import inputs, DAY, NOW
from modules.pig_weights.herdmaster_purpose_work import build_purpose_work

_REAL_PURPOSE_EVENT_LOADER = purpose.load_purpose_delivery_events


def candidate(*, weight=True, key="COHORT-A", now=None):
    allocation, checks, _ = inputs(weight_day=DAY-timedelta(days=1) if weight else None)
    for row in allocation['pigs']:
        row['litter_id'] = key
        row['sow_tag_number'] = 'Example sow'
    work = build_purpose_work(allocation, checks, analysis_date=DAY)
    return sources._purpose_review_candidates({'purpose_work': work}, now=now or NOW,
        today=DAY, observed_at=now or NOW)[0]


def case_and_receipt(raw=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    raw = raw or candidate(now=now)
    case = {**worker.normalize_candidate(raw, now=now), 'generation': 1,
        'status': 'delegated', 'last_delivery_digest': None, '_manager_cycle_id': 'TEST-CYCLE'}
    case['_purpose_review_refresh'] = purpose.purpose_refresh_receipt(raw,case,now=now,cycle_id='TEST-CYCLE')
    return case


def lease_row(case):
    refreshed=datetime.fromisoformat(case['_purpose_review_refresh']['refreshed_at'])
    return ['delegated',case['generation'],case['evidence_digest'],case['_manager_cycle_id'],
        refreshed+worker.LEASE,refreshed,None,case['evidence_refs'],[]]


@pytest.fixture(autouse=True)
def no_ambient_retry_reads(monkeypatch):
    monkeypatch.setattr(purpose,'load_purpose_delivery_events',lambda *a,**k:[])


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','99,42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE','en')
    monkeypatch.setenv('AMADEUS_BACKEND_URL','https://farm.example')
    return purpose.current_purpose_owner()


def bind_fence(monkeypatch, row):
    statements=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def execute(self,sql,params=None): statements.append((sql,params))
        def fetchone(self): return row
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def cursor(self): return Cursor()
    monkeypatch.setattr(purpose,'connect_bounded_read',Connection)
    return statements


def test_real_producer_normalization_retains_decision_semantics_without_digest_churn():
    raw=candidate(); normalized=worker.normalize_candidate(raw,now=NOW)
    assert raw['task_class']=='protected_decision' and raw['owner_question_eligible'] is True
    assert normalized['unknowns']==[] and 'task_class' not in normalized
    assert purpose.purpose_decision_binding(normalized)['cohort_key']=='COHORT-A'
    old=deepcopy(raw); old.pop('_purpose_review')
    assert worker.normalize_candidate(old,now=NOW)==normalized
    assert purpose.purpose_decision_binding(worker.normalize_candidate(candidate(weight=False),now=NOW)) is None


def invalid_case(change):
    value=case_and_receipt(); refs=value['evidence_refs']
    if change=='other_specialist': value['specialist']='ROOTLINE'
    elif change=='unknown': value['unknowns']=['weight unproven']
    elif change=='family': value['message_family']='other'
    elif change=='missing_family': refs[:]=[r for r in refs if not r.startswith('manager_message_family:')]
    elif change=='multiple_family': refs.append('manager_message_family:other')
    elif change=='phase': refs[:]=[r.replace('phase:owner_decision','phase:post_wean_weight') for r in refs]
    elif change=='multiple_phase': refs.append('phase:held')
    elif change=='rule': refs[:]=[r.replace('rule_day:14','rule_day:13') for r in refs]
    elif change=='material': refs[:]=[r for r in refs if not r.startswith('purpose_evidence:')]
    elif change=='bad_material': refs[:]=['purpose_evidence:not-a-digest' if r.startswith('purpose_evidence:') else r for r in refs]
    elif change=='duplicate_material': refs.append('purpose_evidence:'+'a'*64)
    elif change=='cohort': value['dedupe_key']='herdmaster:purpose-review:OTHER'
    elif change=='litter': refs[:]=[r.replace('litter:COHORT-A','litter:OTHER') for r in refs]
    elif change=='no_pigs': refs[:]=[r for r in refs if not r.startswith('pig:')]
    elif change=='foreign_pig': refs.append('pig:not-canonical')
    elif change=='unsafe_key': value['dedupe_key']='herdmaster:purpose-review:../../x'
    elif change=='synthetic_old_sibling': value['dedupe_key']='herdmaster:purpose:legacy'; value['message_family']=''
    return value


INVALID = ['other_specialist','unknown','family','missing_family','multiple_family','phase',
    'multiple_phase','rule','material','bad_material','duplicate_material','cohort','litter',
    'no_pigs','foreign_pig','unsafe_key','synthetic_old_sibling']


@pytest.mark.parametrize('change',INVALID)
def test_nondecision_quiet_or_unproven_refs_never_gain_decision_admission(change):
    assert purpose.purpose_decision_binding(invalid_case(change)) is None


@pytest.mark.parametrize('language',['en','af'])
def test_owner_ready_decision_has_concise_localized_existing_review_link(owner,monkeypatch,language):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE',language)
    case=case_and_receipt(); statements=bind_fence(monkeypatch,lease_row(case)); captured={}
    def deliver(parsed,result,**kwargs):
        captured.update(parsed=parsed,result=result,kwargs=kwargs)
        return {'success':True,'provider_delivery_confirmed':True,'telegram_message_id':'test-card','telegram_sends':1}
    result=worker.deliver_farm_manager_case(case,deliver=deliver)
    assert result['delivery_confirmed'] is True
    assert captured['parsed']['telegram_user_id']==captured['parsed']['telegram_chat_id']=='42'
    assert captured['parsed']['telegram_chat_type']=='private'
    rendered=captured['result']; assert rendered['recipient_language']==language
    assert len(rendered['answer'])<750 and 'Still unknown' not in rendered['answer']
    assert '2' in rendered['answer'] and 'Example sow' in rendered['answer']
    assert rendered['writes_farm_data'] is False
    assert rendered['reply_markup']['inline_keyboard'][0][0]['url']=='https://farm.example/pig-allocation?mode=purpose-review&litter_id=COHORT-A'
    assert 'callback' not in json.dumps(rendered)
    assert any('set transaction read only' in sql for sql,_ in statements)
    if language=='af':
        localized=family.localize_recipient_result(captured['parsed'],rendered,'HERDMASTER')
        assert localized['answer']==rendered['answer']
        assert 'recipient_language_render_unrecognized' not in localized
        assert 'Niks is goedgekeur' in rendered['answer']


@pytest.mark.parametrize('owner_id,allowed',[('', '99,42'),('', '99'),('42','99'),('99','42')])
def test_owner_absent_or_not_currently_authorized_cannot_deliver(monkeypatch,owner_id,allowed):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID',owner_id)
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS',allowed)
    monkeypatch.setattr(purpose,'connect_bounded_read',lambda:pytest.fail('no read without owner'))
    result=worker.deliver_farm_manager_case(case_and_receipt(),deliver=lambda *a,**k:pytest.fail('no delivery'))
    assert result['success'] is False and result['telegram_sends']==0


@pytest.mark.parametrize('change',['generation','digest','phase','lease','worker','heartbeat','already_delivered','owner','destination'])
@pytest.mark.parametrize('operation',['sender','editor'])
def test_provider_boundary_rejects_changed_context_or_recipient(owner,monkeypatch,change,operation):
    case=case_and_receipt(); row=lease_row(case); bind_fence(monkeypatch,row)
    monkeypatch.setattr(family,'_send_telegram',lambda *a,**k:pytest.fail('provider must not run'))
    monkeypatch.setattr(family,'_edit_telegram',lambda *a,**k:pytest.fail('provider must not run'))
    def deliver(parsed,result,**kwargs):
        if change=='generation': row[1]+=1
        elif change=='digest': row[2]='changed'
        elif change=='phase': row[7]=[r.replace('phase:owner_decision','phase:held') for r in row[7]]
        elif change=='lease': row[4]=datetime.now(timezone.utc)-timedelta(seconds=1)
        elif change=='worker': row[3]='OTHER-CYCLE'
        elif change=='heartbeat': row[5]+=timedelta(seconds=1)
        elif change=='already_delivered': row[6]=row[2]
        elif change=='owner': monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','99')
        args=('99' if change=='destination' else '42',)
        if operation=='editor': args+=('existing-card',)
        return kwargs[operation](*args,result['answer'])
    result=worker.deliver_farm_manager_case(case,deliver=deliver)
    assert result['success'] is False and result['delivery_definitely_not_sent'] is True


@pytest.mark.parametrize('change',['missing','stale','future','foreign_digest','foreign_case','foreign_cycle'])
def test_missing_or_stale_refresh_receipt_never_reaches_database_or_provider(owner,monkeypatch,change):
    case=case_and_receipt(); receipt=case['_purpose_review_refresh']
    if change=='missing': case.pop('_purpose_review_refresh')
    elif change=='stale': receipt['refreshed_at']=(datetime.now(timezone.utc)-worker.LEASE).isoformat()
    elif change=='future': receipt['refreshed_at']=(datetime.now(timezone.utc)+worker.LEASE).isoformat()
    elif change=='foreign_digest': receipt['evidence_digest']='other'
    elif change=='foreign_case': receipt['case_id']='other'
    elif change=='foreign_cycle': receipt['cycle_id']='other'
    monkeypatch.setattr(purpose,'connect_bounded_read',lambda:pytest.fail('no read with invalid receipt'))
    result=worker.deliver_farm_manager_case(case,deliver=lambda *a,**k:pytest.fail('no delivery'))
    assert result['success'] is False and result['telegram_sends']==0


def test_deadline_never_extended_and_read_failure_stays_contained(owner,monkeypatch):
    case=case_and_receipt()
    denied=Mock(side_effect=RuntimeError('private database text'))
    monkeypatch.setattr(purpose,'connect_bounded_read',denied)
    result=worker.deliver_farm_manager_case(case,deadline_monotonic=time.monotonic()+1)
    assert result['success'] is False; denied.assert_not_called()
    result=worker.deliver_farm_manager_case(case)
    assert result['success'] is False and 'private database text' not in str(result)


def family_delivery(monkeypatch, effects):
    events={}
    def store(action,identity,payload):
        if action=='load': return list(events.values())
        created=identity not in events
        if created: events[identity]=dict(payload)
        return {'success':True,'created':created}
    def provider(destination,text,**kwargs):
        effects.append((destination,text,kwargs))
        return {'success':True,'telegram_message_id':'9001'}
    monkeypatch.setattr(purpose,'load_purpose_delivery_events',lambda *a,**k:list(events.values())[:3])
    monkeypatch.setattr(family,'_send_telegram',provider)
    monkeypatch.setattr(family,'_edit_telegram',lambda *a,**k:pytest.fail('no duplicate edit'))
    def deliver(parsed,result,**kwargs):
        return family.deliver_family_result(parsed,result,event_store=store,**kwargs)
    return deliver,events


def test_actual_family_rail_sends_once_keeps_url_button_and_replays_without_effect(owner,monkeypatch):
    case=case_and_receipt(); bind_fence(monkeypatch,lease_row(case)); effects=[]
    deliver,events=family_delivery(monkeypatch,effects)
    assert worker.deliver_farm_manager_case(case,deliver=deliver)['delivery_confirmed'] is True
    before=deepcopy(events)
    repeated=worker.deliver_farm_manager_case(case,deliver=deliver)
    assert repeated['success'] and repeated['delivery_confirmed'] is False
    assert len(effects)==1 and events==before
    assert effects[0][0]=='42'
    assert effects[0][2]['reply_markup']['inline_keyboard'][0][0]['url'].endswith('litter_id=COHORT-A')


@pytest.fixture
def pg():
    from tests.test_oom_sakkie_general_manager_postgres import (
        URL, SchedulerRecoveryPostgresTests, _disposable_connection_info)
    if not URL: pytest.skip('explicit isolated PostgreSQL URL required')
    _disposable_connection_info()
    harness=SchedulerRecoveryPostgresTests(methodName='runTest')
    harness.setUp()
    try: yield harness
    finally: harness.doCleanups()


@pytest.mark.parametrize('change',[None,*[v for v in INVALID if v!='family']])
def test_real_postgres_admission_matches_reference_contract(pg,change):
    case=invalid_case(change) if change else case_and_receipt()
    with pg.db() as db:
        actual=db.execute('select '+purpose.PURPOSE_DECISION_SQL+''' from
            (select %s::text specialist,%s::text dedupe_key,%s::jsonb unknowns,%s::jsonb evidence_refs) m''',
            (case['specialist'],case['dedupe_key'],json.dumps(case['unknowns']),json.dumps(case['evidence_refs']))).fetchone()[0]
    assert actual is bool(purpose.purpose_decision_binding(case))


def test_real_postgres_producer_store_refresh_family_delivery_then_no_duplicate(pg,owner,monkeypatch):
    raw=candidate(now=pg.now); effects=[]; deliver,events=family_delivery(monkeypatch,effects)
    monkeypatch.setattr(purpose,'connect_bounded_read',pg.db)
    def present(case,**kwargs): return worker.deliver_farm_manager_case(case,deliver=deliver,**kwargs)
    started=time.monotonic()
    first=pg.cycle([raw],refresh=lambda _:raw,deliver=present)
    assert first['success'] and len(effects)==1
    elapsed=time.monotonic()-started
    pg.now+=timedelta(minutes=6)
    second=pg.cycle([raw],refresh=lambda _:pytest.fail('confirmed material should not refresh'),deliver=present)
    assert second['success'] and len(effects)==1
    with pg.db() as db:
        row=db.execute('select generation,last_delivery_digest,evidence_digest from app_private.oom_manager_cases').fetchone()
    assert row[0]==1 and row[1]==row[2]
    # Only the existing normal owning refresh runs; the provider guard is a
    # narrow lease SELECT. No broad herd collector can run in this harness.
    assert elapsed < worker.CASE_COMPLETION_RESERVE_SECONDS


def test_real_postgres_purpose_decisions_precede_quiet_work_but_not_fresh_protected_urgency(pg):
    ready=candidate(now=pg.now)
    urgent=pg.value('protected',dedupe_key='herdmaster:retained-mortality:test',urgency='urgent',
        message_family='retained_protected_recovery',evidence_refs=['event:protected'],next_reassessment_at=pg.now)
    quiet=[pg.value('quiet-'+str(i),next_reassessment_at=pg.now-timedelta(days=4),
        dedupe_key='herdmaster:purpose:old-'+str(i)) for i in range(8)]
    selected=[]
    values=[ready,urgent,*quiet]
    by_key={v['dedupe_key']:v for v in values}
    pg.cycle(values,refresh=lambda c:by_key[c['dedupe_key']],deliver=lambda c:
        selected.append(c['dedupe_key']) or {'success':True,'delivery_confirmed':False,'telegram_sends':0})
    assert selected[0]==urgent['dedupe_key'] and selected[1]==ready['dedupe_key']
    assert len(selected)==worker.CLAIM_LIMIT


@pytest.mark.parametrize('change',['missing','phase','material','cohort','count','boolean_count','label'])
def test_refresh_facts_must_match_the_same_supported_decision(owner,monkeypatch,change):
    case=case_and_receipt(); facts=case['_purpose_review_refresh']['facts']
    if change=='missing': case['_purpose_review_refresh'].pop('facts')
    elif change=='phase': facts['phase']='weight_due'
    elif change=='material': facts['material_digest']='0'*64
    elif change=='cohort': facts['cohort_key']='other'
    elif change=='count': facts['member_count']=0
    elif change=='boolean_count': facts['member_count']=True
    elif change=='label': facts['label']=None
    monkeypatch.setattr(purpose,'connect_bounded_read',lambda:pytest.fail('invalid receipt'))
    result=worker.deliver_farm_manager_case(case,deliver=lambda *a,**k:pytest.fail('no delivery'))
    assert result['success'] is False


@pytest.mark.parametrize('base',['','javascript:alert(1)','http://farm.example',
    'https://user:password@farm.example','https://farm.example/?secret=value',
    'https://farm.example/other','https://[bad'])
def test_missing_or_unsafe_detail_base_keeps_safe_text_without_callback(owner,monkeypatch,base):
    case=case_and_receipt(); bind_fence(monkeypatch,lease_row(case))
    monkeypatch.setenv('AMADEUS_BACKEND_URL',base)
    monkeypatch.delenv('RENDER_EXTERNAL_URL',raising=False)
    result=purpose.build_purpose_review(case,principal=owner)
    assert result['success'] is True and 'reply_markup' not in result
    assert 'Pig Allocation' in result['answer']


def test_canonical_single_pig_cohort_has_same_decision_contract(owner,monkeypatch):
    raw=candidate(key=''); case=case_and_receipt(raw)
    binding=purpose.purpose_decision_binding(case)
    assert binding['cohort_key'].startswith('PIG-') and binding['litter_id']==''
    bind_fence(monkeypatch,lease_row(case))
    result=purpose.build_purpose_review(case,principal=owner)
    assert result['reply_markup']['inline_keyboard'][0][0]['url']=='https://farm.example/pig-allocation?mode=purpose-review'


@pytest.mark.parametrize('replacement',['weight_due','held','missing'])
def test_real_postgres_current_phase_or_material_change_defers_without_owner_send(pg,owner,monkeypatch,replacement):
    original=candidate(now=pg.now)
    changed=candidate(weight=False,now=pg.now) if replacement=='weight_due' else deepcopy(original)
    if replacement=='held':
        changed['evidence_refs']=[r.replace('phase:owner_decision','phase:held') for r in changed['evidence_refs']]
        changed['unknowns']=['canonical_status_unproven']
        changed['_purpose_review']['phase']='held'
    if replacement=='missing': changed=None
    result=pg.cycle([original],refresh=lambda _:changed,deliver=lambda *_a,**_k:pytest.fail('stale decision cannot deliver'))
    assert result['success'] is True
    with pg.db() as db:
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='delivery_confirmed'").fetchone()[0]==0


def test_real_postgres_confirmed_decision_stays_behind_unconfirmed_current_work(pg):
    ready=candidate(now=pg.now); pg.seed([ready])
    with pg.db() as db:
        db.execute('update app_private.oom_manager_cases set last_delivery_digest=evidence_digest')
    other=[pg.value('question-'+str(i),unknowns=['current physical fact'],
        next_reassessment_at=pg.now,dedupe_key='herdmaster:question:'+str(i)) for i in range(6)]
    by_key={v['dedupe_key']:v for v in other}; selected=[]
    pg.cycle([ready,*other],refresh=lambda c:by_key[c['dedupe_key']],deliver=lambda c:
        selected.append(c['dedupe_key']) or {'success':True,'delivery_confirmed':False,'telegram_sends':0})
    assert ready['dedupe_key'] not in selected and len(selected)==worker.CLAIM_LIMIT


@pytest.mark.parametrize('extra',[None,42,{},[],True])
def test_real_postgres_nonstring_reference_cannot_gain_priority(pg,extra):
    case=case_and_receipt(); case['evidence_refs'].append(extra)
    assert purpose.purpose_decision_binding(case) is None
    with pg.db() as db:
        actual=db.execute('select '+purpose.PURPOSE_DECISION_SQL+""" from
            (select %s::text specialist,%s::text dedupe_key,%s::jsonb unknowns,%s::jsonb evidence_refs) m""",
            (case['specialist'],case['dedupe_key'],json.dumps(case['unknowns']),json.dumps(case['evidence_refs']))).fetchone()[0]
    assert actual is False


@pytest.mark.parametrize('operation',['sender','editor'])
def test_lease_expiring_during_provider_fence_read_cannot_authorize_effect(owner,monkeypatch,operation):
    now=datetime.now(timezone.utc); case=case_and_receipt(now=now)
    row=lease_row(case); row[4]=now+timedelta(seconds=1)
    instant=[now]; reads=[]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return instant[0]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def execute(self,*_): pass
        def fetchone(self):
            reads.append(True)
            if len(reads)==2: instant[0]=now+timedelta(seconds=2)
            return row
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*_): return False
        def cursor(self): return Cursor()
    monkeypatch.setattr(purpose,'datetime',Clock)
    monkeypatch.setattr(purpose,'connect_bounded_read',Connection)
    monkeypatch.setattr(family,'_send_telegram',lambda *a,**k:pytest.fail('expired send'))
    monkeypatch.setattr(family,'_edit_telegram',lambda *a,**k:pytest.fail('expired edit'))
    def deliver(parsed,result,**kwargs):
        args=('42',) + (('existing-card',) if operation=='editor' else ())
        return kwargs[operation](*args,result['answer'])
    result=worker.deliver_farm_manager_case(case,now=now,deliver=deliver)
    assert result['success'] is False and result['delivery_definitely_not_sent'] is True
    assert len(reads)==2


@pytest.mark.parametrize('outcome',['recovered','ambiguous','retry_exhausted'])
def test_real_postgres_natural_cycle_bounded_zero_send_recovery(pg,owner,monkeypatch,outcome):
    effects=[]; deliver,events=family_delivery(monkeypatch,effects)
    monkeypatch.setattr(purpose,'connect_bounded_read',pg.db)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return pg.now
    monkeypatch.setattr(purpose,'datetime',Clock)
    monkeypatch.setattr(worker,'datetime',Clock)
    actual_fence=purpose.purpose_delivery_current; fence_calls=[]
    def fence(*args,**kwargs):
        fence_calls.append(True)
        valid=actual_fence(*args,**kwargs)
        if len(fence_calls)==2 or (outcome=='retry_exhausted' and len(fence_calls)==4):
            return False
        return valid
    monkeypatch.setattr(purpose,'purpose_delivery_current',fence)
    raw=candidate(now=pg.now)
    def present(case,**kwargs): return worker.deliver_farm_manager_case(case,deliver=deliver,**kwargs)
    first=pg.cycle([raw],refresh=lambda _:raw,deliver=present)
    assert first['success'] and effects==[]
    assert len(events)==2
    proof=next(e for e in events.values() if e['state']=='contained')
    assert proof['reason']=='telegram_delivery_definitely_not_sent'
    if outcome=='ambiguous': proof['reason']='telegram_delivery_unconfirmed'
    pg.now+=timedelta(minutes=6)
    second=pg.cycle([raw],refresh=lambda _:raw,deliver=present)
    assert second['success']
    assert len(effects)==(1 if outcome=='recovered' else 0)
    pg.now+=timedelta(minutes=6)
    third=pg.cycle([raw],refresh=lambda _:raw,deliver=present)
    assert third['success']
    assert len(effects)==(1 if outcome=='recovered' else 0)
    assert sum(e['state']=='delivery_attempted' for e in events.values())==(1 if outcome=='ambiguous' else 2)
    with pg.db() as db:
        row=db.execute('select generation,last_delivery_digest,evidence_digest from app_private.oom_manager_cases').fetchone()
    assert row[0]==1
    assert (row[1]==row[2]) is (outcome=='recovered')


@pytest.mark.parametrize('change',[None,'text','owner','mission','card','timestamp','specialist',
    'provider_message','digest','extra','delivered','updated','receipt','duplicate','retry2','ambiguous','language'])
@pytest.mark.parametrize('language',['en','af'])
def test_retry_authority_requires_exact_durable_initial_zero_send_proof(owner,monkeypatch,change,language):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE',language)
    case=case_and_receipt(); row=lease_row(case); bind_fence(monkeypatch,row)
    effects=[]; real_deliver,events=family_delivery(monkeypatch,effects); captured={}
    def stop_before_provider(parsed,result,**kwargs):
        captured.update(parsed=deepcopy(parsed),result=deepcopy(result),mission_id=kwargs['mission_id'])
        row[4]=datetime.now(timezone.utc)-timedelta(seconds=1)
        return real_deliver(parsed,result,**kwargs)
    first=worker.deliver_farm_manager_case(case,deliver=stop_before_provider)
    assert first['delivery_definitely_not_sent'] is True and effects==[]
    parsed=captured['parsed']; result=captured['result']; mission=captured['mission_id']
    if change=='text': result['answer']+=' Changed recommendation.'
    elif change=='owner':
        monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','99')
        parsed.update(telegram_user_id='99',telegram_chat_id='99')
    elif change=='mission': mission+='OTHER'
    elif change=='card': case['case_id']='OTHER'
    elif change=='timestamp': parsed['provider_timestamp']='2020-01-01T00:00:00+00:00'
    elif change=='specialist': next(iter(events.values()))['specialist_identity']='SAM'
    elif change=='provider_message': parsed['provider_message_id']='another-input'
    elif change=='digest': result['result_digest']='different'
    elif change=='extra': events['extra']={'event_id':'extra','state':'working'}
    elif change in ('delivered','updated'): next(iter(events.values()))['state']=change
    elif change=='receipt': next(iter(events.values()))['telegram_message_id']='provider-card'
    elif change=='duplicate':
        rows=list(events.values()); events.clear(); events['one']=rows[0]; events['two']=dict(rows[0])
    elif change=='retry2': next(iter(events.values()))['event_id']=case['case_id']+'-DELIVERY-RETRY-2'
    elif change=='ambiguous': next(e for e in events.values() if e['state']=='contained')['reason']='telegram_delivery_unconfirmed'
    elif change=='language':
        changed='af' if language=='en' else 'en'
        monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE',changed)
        row[4]=datetime.now(timezone.utc)+worker.LEASE
        parsed['output_language']=changed
        result=purpose.build_purpose_review(case,principal=purpose.current_purpose_owner())
    authority=purpose.purpose_delivery_retry_authority(case,parsed,result,mission_id=mission)
    assert (authority is not None) is (change is None)
    if authority:
        from modules.oom_sakkie.delivery_retry_authority import validates_delivery_retry_authority
        from modules.oom_sakkie.family_presentation import envelope
        assert validates_delivery_retry_authority(authority,mission_id=mission,
            card_mission_id=case['case_id'],text=envelope(result['answer']))
        assert authority.attempt_ordinal==2


def test_real_postgres_retry_history_read_is_bounded_and_detects_extra_row(pg,monkeypatch):
    from modules.oom_sakkie.family_message_lifecycle import EVENT_SOURCE
    with pg.db() as db:
        db.execute('create table app_private.purpose_events(review_event_id text primary key,event_source text,review_json jsonb,created_at timestamptz default now())')
        for i in range(5):
            db.execute('insert into app_private.purpose_events(review_event_id,event_source,review_json) values(%s,%s,%s::jsonb)',
                (str(i),EVENT_SOURCE,json.dumps({'family_message_lifecycle':{'card_mission_id':'CARD','event_id':str(i)}})))
        db.execute('insert into app_private.purpose_events(review_event_id,event_source,review_json) values(%s,%s,%s::jsonb)',
            ('unrelated',EVENT_SOURCE,json.dumps({'family_message_lifecycle':{'card_mission_id':'OTHER'}})))
    class Cursor:
        def __init__(self,raw): self.raw=raw
        def __enter__(self): self.raw.__enter__(); return self
        def __exit__(self,*args): return self.raw.__exit__(*args)
        def execute(self,sql,params=None):
            return self.raw.execute(sql.replace('public.sam_live_stock_conversation_review_events',
                'app_private.purpose_events'),params)
        def fetchall(self): return self.raw.fetchall()
    class Connection:
        def __enter__(self): self.db=pg.db(); self.db.__enter__(); return self
        def __exit__(self,*args): return self.db.__exit__(*args)
        def cursor(self): return Cursor(self.db.cursor())
    monkeypatch.setattr(purpose,'connect_bounded_read',Connection)
    rows=_REAL_PURPOSE_EVENT_LOADER('CARD')
    assert [row['event_id'] for row in rows]==['0','1','2']
    assert _REAL_PURPOSE_EVENT_LOADER('MISSING')==[]
