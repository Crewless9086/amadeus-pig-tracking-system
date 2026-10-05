"""Production-shaped overview receipts never stand in for purpose approval."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import hashlib
import time

import pytest

from modules.oom_sakkie import herdmaster_purpose_overview as overview
from modules.oom_sakkie import herdmaster_purpose_membership as membership
from modules.oom_sakkie import herdmaster_purpose_telegram as telegram
from modules.oom_sakkie import protected_action_claims as claims
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import general_manager_worker as worker
from tests.test_herdmaster_purpose_work import inputs, DAY
from modules.pig_weights.herdmaster_purpose_work import build_purpose_work


def production_packet(now, count=7, first_group_members=2):
    allocation, checks, _ = inputs(count=first_group_members+2*(count-1), weight_day=DAY-timedelta(days=1))
    for i, row in enumerate(allocation['pigs']):
        group = 0 if i < first_group_members else 1+(i-first_group_members)//2
        row['litter_id'] = 'COHORT-'+str(group)
        row['sow_tag_number'] = 'Example '+str(group)
    work = build_purpose_work(allocation, checks, analysis_date=DAY)
    snapshot = {'purpose_work': work, 'snapshot_observed_at': now}
    raw = sources._purpose_review_candidates(snapshot, now=now, today=DAY, observed_at=now)
    cases = []
    for r in raw:
        case = {**worker.normalize_candidate(r, now=now), 'generation': 1, 'status': 'waiting_reassessment',
            'assigned_worker_id': None, 'lease_until': None, 'last_delivery_digest':None}
        record = membership.build_record(case, generation=1, now=now)
        event = {'case_id': case['case_id'], 'generation': 1, 'event_type': 'created',
            'occurred_at': now, 'event_payload': {'case_id': case['case_id'], 'generation': 1, 'purpose_membership': record}}
        binding = membership.verify_current_membership(case, snapshot, membership_events=[event], now=now)
        cases.append({**case, 'membership': binding, 'available': True})
    return raw, {'snapshot': snapshot, 'cases': cases}


class Memory:
    def __init__(self):
        self.events, self.sent, self.lock = {}, [], Lock()
    def store(self, action, identity, payload):
        with self.lock:
            if action == 'load': return deepcopy([e for e in self.events.values() if e['card_mission_id'] == identity])
            created = identity not in self.events
            if created: self.events[identity] = deepcopy(payload)
            return {'success': True, 'created': created}
    def read(self, *, mission=None, manifest=None, owner_id=None, **kwargs):
        with self.lock:
            return deepcopy([e for e in self.events.values() if e['mission_id'] == mission
                or (mission is None and any(m in e.get(overview.FIELD, {}).get('manifest', []) for m in (manifest or [])))])
    def send(self, chat, text, **kwargs):
        with self.lock: self.sent.append((chat, text))
        return {'success': True, 'telegram_message_id': str(9000+len(self.sent)), 'provider_timestamp': '2026-10-05T00:00:00Z'}


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID', '42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS', '77,42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE', 'en')
    now = datetime.now(timezone.utc)
    raw, context = production_packet(now)
    memory = Memory()
    monkeypatch.setattr(overview, '_read_events', memory.read)
    monkeypatch.setattr(overview, '_deferrals', lambda *a, **k: [])
    monkeypatch.setattr(overview, '_current_rows', lambda *a, **k: True)
    monkeypatch.setattr(claims, 'bind_claim_card', lambda *a, **k: True)
    def create(**kwargs):
        digest = claims.canonical_preview_digest(kwargs['action_kind'], kwargs['preview_payload'])
        return {'success': True, 'callback_token': 't'+digest[:15], 'preview_digest': digest,
            'action_kind': kwargs['action_kind']}
    monkeypatch.setattr(claims, 'create_claim', create)
    def run(**kwargs):
        return overview.dispatch_purpose_overview(raw, cycle_id='CYCLE-A', now=now,
            deadline_monotonic=time.monotonic()+80, context=context, event_store=memory.store,
            sender=memory.send, clock=lambda:now,
            protected_delivery=lambda **k:k['deliver'](), **kwargs)
    return run, memory, raw, context, now


@pytest.mark.parametrize('language', ['en', 'af'])
def test_real_producer_seven_groups_one_family_card_all_exact_coverage_and_quiet_replay(harness, monkeypatch, language):
    run, memory, raw, context, _ = harness
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE', language)
    original = deepcopy(context)
    first = run()
    assert first['success'] is True, first
    assert len(first['coverage']) == 7 and first['telegram_sends'] == 1
    assert first['delivery_confirmed'] is False and first['writes_farm_data'] is False
    assert all(row['receipt']['language'] == language for row in first['coverage'])
    assert len(memory.sent) == 1 and '7' in memory.sent[0][1]
    assert context == original  # No sibling delivered/approved/completed mutation.
    before = deepcopy(memory.events)
    raw.reverse()
    again = run()
    assert again['success'] is True and again['telegram_sends'] == again['telegram_edits'] == 0
    assert again['manifest'] == first['manifest'] and memory.events == before and len(memory.sent) == 1


@pytest.mark.parametrize('change', ['owner', 'chat', 'mission', 'card', 'state', 'text', 'message', 'manifest', 'extra', 'missing', 'digest', 'language'])
def test_forged_or_incomplete_family_history_cannot_claim_coverage(harness, change):
    run, _, _, _, _ = harness
    first = run(); assert first['success'], first
    events = deepcopy(first['receipt_events']); end = next(e for e in events if e['state'] == 'purpose_overview_verified')
    if change in {'owner','chat','mission','card','text','message'}:
        key = {'owner':'owner_user_id','chat':'chat_id','mission':'mission_id','card':'card_mission_id','text':'text_sha256','message':'telegram_message_id'}[change]
        end[key] = 'foreign'
    elif change == 'state': end['state'] = 'contained'
    elif change == 'manifest': end[overview.FIELD]['manifest'][0]['generation'] += 1
    elif change == 'extra': events.append({**end, 'event_id':'competing', 'state':'delivery_attempted'})
    elif change == 'missing': events = [e for e in events if e['state'] != 'delivery_attempted']
    elif change == 'digest': end[overview.FIELD]['preview_digest'] = ''
    elif change == 'language': end[overview.FIELD]['language'] = 'de'
    assert overview.verify_overview_receipt(events, manifest=first['manifest'], owner_id='42', occurrence_id='initial') is None


@pytest.mark.parametrize('definitely_not_sent', [False, True])
def test_unconfirmed_send_is_not_coverage_and_never_falls_back_or_blindly_retries(harness, definitely_not_sent):
    run, memory, _, _, _ = harness
    memory.send = lambda *a, **k:{'success':False,'delivery_definitely_not_sent':definitely_not_sent}
    first = run(); before = deepcopy(memory.events)
    again = run()
    assert first['coverage'] == again['coverage'] == []
    assert first['telegram_sends'] == again['telegram_sends'] == 0
    assert again['status'] == 'purpose_overview_prior_attempt_contained' and memory.events == before


def test_concurrent_overview_attempts_at_most_one_provider_effect(harness):
    run, memory, _, _, _ = harness
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:run(), range(2)))
    assert len(memory.sent) == 1
    assert sum(r['telegram_sends'] for r in results) == 1
    assert any(r['coverage'] for r in results)


@pytest.mark.parametrize('change', ['no_owner','allowlist_only','unavailable','changed_material','duplicate','deadline','expired_fence','missing_snapshot'])
def test_unproven_current_context_never_creates_provider_effect(harness, monkeypatch, change):
    run, memory, raw, context, now = harness
    if change == 'no_owner': monkeypatch.delenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID')
    elif change == 'allowlist_only': monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','99')
    elif change == 'unavailable':
        for row in context['cases']: row['available'] = False
    elif change == 'changed_material': context['cases'][0]['evidence_digest'] = '0'*64
    elif change == 'duplicate': raw.append(deepcopy(raw[0]))
    elif change == 'expired_fence': monkeypatch.setattr(overview, '_current_rows',lambda *a,**k:False)
    if change in {'deadline','missing_snapshot'}:
        if change == 'missing_snapshot':
            for r in raw:r.pop('_purpose_source_snapshot',None)
        result = overview.dispatch_purpose_overview(raw, cycle_id='CYCLE-A', now=now,
            deadline_monotonic=time.monotonic()+(29 if change == 'deadline' else 80))
    else: result = run()
    assert result['coverage'] == [] and memory.sent == []


def test_owner_change_between_preparation_and_send_is_contained(harness, monkeypatch):
    run, memory, _, _, _ = harness
    real = overview.current_purpose_owner
    reads = []
    def owner():
        reads.append(1)
        return real() if len(reads)==1 else None
    monkeypatch.setattr(overview,'current_purpose_owner',owner)
    assert run()['coverage'] == [] and memory.sent == []


def test_due_owner_requested_occurrence_once_without_changing_case_material(harness, monkeypatch):
    run, memory, _, context, now = harness
    initial=run(); assert initial['success'],initial
    request = {'case_id':context['cases'][0]['case_id'],'request_id':'a'*64,'review_at':now.isoformat()}
    monkeypatch.setattr(overview,'_deferrals',lambda *a,**k:[request])
    due=run(); assert due['success'],due
    assert due['occurrence_id'] != 'initial' and len(due['manifest']) == 1
    assert due['manifest'][0] in initial['manifest']
    assert due['telegram_sends'] == 1 and len(memory.sent)==2
    assert ('requested' in memory.sent[-1][1].lower() or 'review' in memory.sent[-1][1].lower())
    after=run(); assert after['telegram_sends']==0 and len(memory.sent)==2
    assert all(c['generation']==1 for c in context['cases'])


class ReadRows:
    def __init__(self, rows): self.rows,self.sql=rows,[]
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def cursor(self):return self
    def execute(self,sql,params=None):self.sql.append((sql,params))
    def fetchall(self):return self.rows


def defer_event(member, now, index=1, day=1):
    request = hashlib.sha256(str(index).encode()).hexdigest()
    value={**member,'contract':'herdmaster.purpose_deferment.v1','request_id':request,
        'owner_user_id':'42','private_chat_id':'42','provider_message_id':str(index),'source_card_message_id':'999',
        'requested_at':now.isoformat(),'review_at':(now+timedelta(days=day)).isoformat(),'reason':'owner_requested_review'}
    return (member['case_id'],member['generation'],'OOM-PURPOSE-DEFER-'+request[:32].upper(),{'purpose_review_deferred':value},now)


def test_latest_request_supersedes_prior_date_and_equal_time_is_ambiguous(harness):
    run,_,_,_,now=harness
    member=run()['manifest'][0]
    old=defer_event(member,now-timedelta(hours=2),1,1)
    new=defer_event(member,now-timedelta(hours=1),2,3)
    # Call original production function rather than the harness seam.
    rows=ReadRows([new,old])
    value=REAL_DEFERRALS([member],owner_id='42',connect=lambda:rows,deadline=time.monotonic()+6,now=now)
    assert value==[new[3]['purpose_review_deferred']] and value[0]['review_at'] != old[3]['purpose_review_deferred']['review_at']
    assert all(sql.lstrip().startswith(('select','set')) for sql,_ in rows.sql)
    with pytest.raises(ValueError,match='ambiguous'):
        REAL_DEFERRALS([member],owner_id='42',connect=lambda:ReadRows([new,defer_event(member,new[4],3)]),deadline=time.monotonic()+6,now=now)


REAL_DEFERRALS = overview._deferrals

# Real SQL, protected claim lifecycle and family receipt persistence. Only table
# namespaces are relocated; migrations supply the actual storage contracts.
from tests.test_oom_sakkie_purpose_decision import pg


@pytest.fixture
def overview_db(pg):
    from pathlib import Path
    import psycopg
    from tests.test_oom_sakkie_general_manager_postgres import _IsolatedConnection, _IsolatedCursor, URL
    class Cursor(_IsolatedCursor):
        def execute(self, sql, params=None):
            return super().execute(sql.replace('public.sam_live_stock_conversation_review_events',
                self.owner.schema+'.sam_live_stock_conversation_review_events'), params)
    class Connection(_IsolatedConnection):
        def cursor(self): return Cursor(self.connection.cursor(), self.owner)
    def connect(): return Connection(psycopg.connect(URL,connect_timeout=3),pg)
    folder=Path(__file__).parents[1]/'supabase'/'migrations'
    with connect() as db:
        db.execute('alter table app_private.beacon_protected_publication_consumers drop constraint beacon_protected_publication_consumers_callback_token_fkey')
        db.execute('drop table app_private.oom_protected_action_claims')
        canonical=(folder/'202608110001_create_oom_protected_action_claims.sql').read_text(encoding='utf-8')
        canonical=canonical.split('create table if not exists public.pig_lifecycle_corrections')[0]
        # Latest additive action-kind migration is qualified by the owning
        # journey tests; this fixture isolates the two allowed review kinds.
        canonical=canonical.replace("'mortality','grouped_weights'", "'mortality','grouped_weights','herdmaster_purpose_review','herdmaster_purpose_correction'")
        db.execute(canonical)
        db.execute('alter table app_private.beacon_protected_publication_consumers add constraint beacon_protected_publication_consumers_callback_token_fkey foreign key(callback_token) references app_private.oom_protected_action_claims(callback_token)')
        db.execute((folder/'202608160004_add_protected_delivery_lifecycle.sql').read_text(encoding='utf-8'))
        db.execute((folder/'202607070001_create_sam_live_stock_conversation_review_events.sql').read_text(encoding='utf-8').split(';')[0])
    pg.store=worker.PostgresManagerCaseStore(connect_factory=connect)
    return pg,connect


def configure_owner(monkeypatch):
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','77,42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE','en')
    monkeypatch.setattr(worker,'build_scheduled_brain_guard_audit',lambda **k:{'passed':True})


@pytest.mark.parametrize('old_delivered',[False,True])
def test_postgres_default_worker_collector_seven_cases_one_overview_old_receipts_preserved_and_quiet(overview_db,monkeypatch,old_delivered):
    pg,connect=overview_db
    configure_owner(monkeypatch)
    raw,context=production_packet(pg.now)
    pg.seed(raw)
    with connect() as db:
        if old_delivered:
            db.execute("update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s",(pg.now-timedelta(days=1),))
        before=db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall()
    sent=[]
    if old_delivered:
        def unused_history(**kwargs):
            pytest.fail('already-delivered default worker must not read family history')
        monkeypatch.setattr(overview, '_read_events', unused_history)
    from modules.oom_sakkie import family_message_lifecycle as family
    def send(chat,text,**kw):
        sent.append((chat,text,kw));return {'success':True,'telegram_message_id':'SYNTHETIC-901','provider_timestamp':pg.now.isoformat()}
    monkeypatch.setattr(family,'_send_telegram',send)
    def collector(now):
        return sources._purpose_review_candidates(context['snapshot'],now=now,today=DAY,observed_at=now)
    first=worker.run_general_manager_cycle(now=pg.now,source_revision='synthetic-overview',store=pg.store,
        collectors=[collector],deliver=worker.deliver_farm_manager_case)
    assert first['success'] is True,first
    if old_delivered:
        assert sent==[] and first['purpose_overview']['telegram_sends']==0
        assert first['exceptions']==first['purpose_overview']['exceptions']==0
        with connect() as db:
            assert db.execute('select count(*) from app_private.oom_protected_action_claims').fetchone()[0]==0
            assert db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall()==before
        return
    assert len(sent)==1,first
    assert first['purpose_overview']['telegram_sends']==1
    with connect() as db:
        after=db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall()
        covered=db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_overview_coverage'").fetchone()[0]
        claim=db.execute('select action_kind,delivery_state,preview_card_message_id,preview_payload from app_private.oom_protected_action_claims').fetchone()
    assert after==before and covered==7
    assert claim[:3]==('herdmaster_purpose_review','delivery_confirmed','SYNTHETIC-901')
    assert len(claim[3]['cases'])==7 and claim[3]['mode']=='overview'
    # A genuine later review edit is ordinary family history, not another
    # overview attempt. Keep that stored history while reading the exact trio.
    with connect() as db:
        delivered=db.execute("select review_json->'family_message_lifecycle' from public.sam_live_stock_conversation_review_events where review_json->'family_message_lifecycle'->>'state'='delivered'").fetchone()[0]
        later={**delivered,'event_id':'SYNTHETIC-NAVIGATION','state':'updated','task_state':'purpose_telegram_group'}
        later.pop(overview.FIELD)
        import json
        db.execute("insert into public.sam_live_stock_conversation_review_events(review_event_id,event_source,review_json) values(%s,%s,%s::jsonb)",
            ('SYNTHETIC-NAVIGATION',family.EVENT_SOURCE,json.dumps({'family_message_lifecycle':later})))
    second=worker.run_general_manager_cycle(now=pg.now+timedelta(minutes=5),source_revision='synthetic-overview',
        store=pg.store,collectors=[collector],deliver=worker.deliver_farm_manager_case)
    assert second['success'] is True,second
    assert len(sent)==1 and second['purpose_overview']['telegram_sends']==0
    with connect() as db:
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_overview_coverage'").fetchone()[0]==7
        assert db.execute('select count(*) from app_private.oom_protected_action_claims').fetchone()[0]==1
        assert db.execute('select count(*) from public.sam_live_stock_conversation_review_events').fetchone()[0]==4


@pytest.mark.parametrize('ambiguous',[True,False])
def test_postgres_exact_attempt_restart_never_seven_fallbacks_or_receipt_borrowing(overview_db,monkeypatch,ambiguous):
    pg,connect=overview_db;configure_owner(monkeypatch)
    raw,_=production_packet(pg.now);pg.seed(raw);sent=[]
    def sender(*a,**k):
        sent.append(1)
        return {'success':False,'delivery_definitely_not_sent':not ambiguous}
    first=overview.dispatch_purpose_overview(raw,cycle_id='SYNTHETIC-CYCLE',now=pg.now,
        deadline_monotonic=time.monotonic()+80,connect=connect,sender=sender)
    assert first['coverage']==[] and len(sent)==1,first
    second=overview.dispatch_purpose_overview(raw,cycle_id='SYNTHETIC-CYCLE2',now=pg.now,
        deadline_monotonic=time.monotonic()+80,connect=connect,sender=sender)
    assert second['coverage']==[] and len(sent)==1
    assert second['status']=='purpose_overview_prior_attempt_contained'
    with connect() as db:
        assert db.execute('select delivery_state from app_private.oom_protected_action_claims').fetchone()[0]=='delivery_ambiguous'
        assert db.execute('select count(*) from app_private.oom_manager_case_events where event_type=\'delivery_confirmed\'').fetchone()[0]==0


def test_postgres_concurrent_dispatch_exact_one_send_and_one_claim(overview_db,monkeypatch):
    pg,connect=overview_db;configure_owner(monkeypatch)
    raw,_=production_packet(pg.now);pg.seed(raw);sent=[];lock=Lock()
    def sender(*a,**k):
        with lock:sent.append(1)
        return {'success':True,'telegram_message_id':'SYNTHETIC-902'}
    def invoke(_):
        return overview.dispatch_purpose_overview(raw,cycle_id='SYNTHETIC-CYCLE',now=pg.now,
            deadline_monotonic=time.monotonic()+80,connect=connect,sender=sender)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(invoke,range(2)))
    assert len(sent)==1 and any(r['coverage'] for r in results),results
    with connect() as db:
        assert db.execute('select count(*) from app_private.oom_protected_action_claims').fetchone()[0]==1
        assert db.execute('select count(*) from public.sam_live_stock_conversation_review_events').fetchone()[0]==3

@pytest.mark.parametrize('change',['new_request','same_time_conflict','foreign_cycle','expired_lease','new_generation','missing'])
def test_presend_current_read_rejects_superseded_request_or_lease(harness,change):
    run,_,_,_,now=harness;member=run()['manifest'][0]
    defer=defer_event(member,now-timedelta(hours=1))
    current=[member['case_id'],member['generation'],member['evidence_digest'],'delegated','CYCLE-A',now+timedelta(minutes=1),[[defer[3]['purpose_review_deferred']['request_id'],defer[4].isoformat()]]]
    if change=='new_request':current[6][0][0]='b'*64
    elif change=='same_time_conflict':current[6].append(['b'*64,current[6][0][1]])
    elif change=='foreign_cycle':current[4]='OTHER'
    elif change=='expired_lease':current[5]=now-timedelta(seconds=1)
    elif change=='new_generation':current[1]+=1
    rows=[] if change=='missing' else [current]
    assert not REAL_CURRENT([member],cycle_id='CYCLE-A',now=now,connect=lambda:ReadRows(rows),
        deadline=time.monotonic()+6,deferrals=[defer[3]['purpose_review_deferred']])


def test_before_requested_date_remains_quiet_and_consumption_follows_exact_receipt(harness,monkeypatch):
    run,memory,_,context,now=harness
    initial=run();assert initial['success']
    monkeypatch.setattr(overview,'_deferrals',lambda *a,**k:[{'case_id':r['case_id'],'request_id':hashlib.sha256(r['case_id'].encode()).hexdigest(),'review_at':(now+timedelta(days=1)).isoformat()} for r in context['cases']])
    again=run()
    assert again['telegram_sends']==0 and len(memory.sent)==1
    assert again['occurrence_id']=='initial'


def test_provider_ack_remains_counted_when_final_receipt_record_fails(harness):
    run,memory,_,_,_=harness
    original=memory.store
    def fail_record(action,identity,payload):
        if action=='record' and identity.endswith('-PURPOSE-VERIFIED'):
            raise TimeoutError('synthetic post-provider deadline')
        return original(action,identity,payload)
    memory.store=fail_record
    result=run()
    assert result['telegram_sends']==1 and result['coverage']==[] and len(memory.sent)==1
    again=run()
    assert again['telegram_sends']==0 and again['coverage']==[] and len(memory.sent)==1


@pytest.mark.parametrize('manifest',[None,{},[None],[True],[{'case_id':None}],[]])
def test_malformed_manifest_is_false_without_throwing(manifest):
    assert overview.verify_overview_receipt([],manifest=manifest,owner_id='42',occurrence_id='initial') is None


REAL_CURRENT=overview._current_rows

@pytest.mark.parametrize('language',['en','af'])
def test_mixed_old_new_and_future_deferred_groups_only_show_eligible_new_work(harness,monkeypatch,language):
    run,memory,_,context,now=harness
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE',language)
    for row in context['cases'][:4]:row['last_delivery_digest']=row['evidence_digest']
    future=context['cases'][4]
    monkeypatch.setattr(overview,'_deferrals',lambda *a,**k:[{'case_id':future['case_id'],'request_id':'e'*64,'review_at':(now+timedelta(days=1)).isoformat()}])
    result=run();assert result['success'],result
    assert {m['case_id'] for m in result['manifest']}=={r['case_id'] for r in context['cases'][5:]}
    assert len(memory.sent)==1 and len(result['coverage'])==2
    again=run();assert again['telegram_sends']==0 and len(memory.sent)==1


def test_mixed_due_old_group_and_new_group_share_one_exact_occurrence(harness,monkeypatch):
    run,memory,_,context,now=harness
    for row in context['cases'][:6]:row['last_delivery_digest']=row['evidence_digest']
    due=context['cases'][0];future=context['cases'][1]
    monkeypatch.setattr(overview,'_deferrals',lambda *a,**k:[
        {'case_id':due['case_id'],'request_id':'d'*64,'review_at':now.isoformat()},
        {'case_id':future['case_id'],'request_id':'e'*64,'review_at':(now+timedelta(days=1)).isoformat()}])
    result=run();assert result['success'],result
    assert {m['case_id'] for m in result['manifest']}=={due['case_id'],context['cases'][6]['case_id']}
    assert result['occurrence_id'].startswith('review:') and len(memory.sent)==1
    assert run()['telegram_sends']==0 and len(memory.sent)==1


def test_one_changed_generation_does_not_notify_six_previously_overviewed_siblings(harness):
    run,memory,raw,context,now=harness
    first=run();assert first['success']
    raw[0]['summary'] += ' Current evidence changed.'
    identity=worker.normalize_candidate(raw[0],now=now)
    current=next(c for c in context['cases'] if c['case_id']==identity['case_id'])
    current.update(generation=2,evidence_digest=identity['evidence_digest'])
    current['membership']['evidence_digest']=identity['evidence_digest']
    second=run();assert second['success'],second
    assert len(second['coverage'])==1 and second['coverage'][0]['case_id']==current['case_id']
    assert len(memory.sent)==2
    assert run()['telegram_sends']==0 and len(memory.sent)==2


def test_known_unavailable_membership_does_not_erase_six_proven_siblings(harness):
    run,memory,_,context,_=harness
    unknown=context['cases'][0];unknown.update(available=False,reason='purpose_membership_event_missing_or_ambiguous')
    unknown.pop('membership')
    result=run();assert result['success'],result
    assert len(result['coverage'])==6 and unknown['case_id'] not in {m['case_id'] for m in result['manifest']}
    assert len(memory.sent)==1 and '6 groups' in memory.sent[0][1]
    assert unknown['available'] is False


def test_postgres_capped_legacy_group_keeps_history_while_proven_sibling_notifies(overview_db,monkeypatch):
    pg,connect=overview_db;configure_owner(monkeypatch)
    raw,_=production_packet(pg.now,count=2,first_group_members=13)
    legacy=raw[0];legacy.pop('_purpose_membership');pg.seed(raw)
    legacy_id=worker.normalize_candidate(legacy,now=pg.now)['case_id']
    with connect() as db:
        before=db.execute('select generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases where case_id=%s',(legacy_id,)).fetchone()
    sent=[]
    result=overview.dispatch_purpose_overview(raw,cycle_id='SYNTHETIC-CYCLE',now=pg.now,
        deadline_monotonic=time.monotonic()+80,connect=connect,
        sender=lambda *a,**k:sent.append(a) or {'success':True,'telegram_message_id':'SYNTHETIC-PROVEN-SIBLING'})
    assert result['success'] and len(result['coverage'])==1,result
    assert result['coverage'][0]['case_id']!=legacy_id and len(sent)==1
    with connect() as db:
        assert db.execute('select generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases where case_id=%s',(legacy_id,)).fetchone()==before
        assert db.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_payload ? 'purpose_membership'",(legacy_id,)).fetchone()[0]==0
        payload=db.execute('select preview_payload from app_private.oom_protected_action_claims').fetchone()[0]
        assert len(payload['cases'])==1 and payload['cases'][0]['membership']['member_count']==2


@pytest.mark.parametrize('future_request', [False, True])
def test_already_delivered_quiet_history_not_read_even_if_history_would_timeout(harness, monkeypatch, future_request):
    from unittest.mock import Mock
    run, memory, _, context, now = harness
    for row in context['cases']:
        row['last_delivery_digest'] = row['evidence_digest']
    original = deepcopy(context)
    member = {k: context['cases'][0][k] for k in ('case_id', 'generation', 'evidence_digest')}
    member['membership_digest'] = context['cases'][0]['membership']['membership_digest']
    requests = [defer_event(member, now-timedelta(hours=1), day=3)] if future_request else []
    def validated(*args, **kwargs):
        return REAL_DEFERRALS(*args, **{**kwargs, 'connect': lambda: ReadRows(requests)})
    monkeypatch.setattr(overview, '_deferrals', validated)
    history = Mock(side_effect=TimeoutError('private SQL details must never be retained'))
    monkeypatch.setattr(overview, '_read_events', history)
    result = run()
    assert result['success'] is True and result['status'] == 'purpose_overview_no_unnotified_due_work'
    assert result['coverage'] == [] and result['telegram_sends'] == result['telegram_edits'] == 0
    assert result['delivery_confirmed'] is False and result['writes_farm_data'] is False
    assert memory.sent == [] and memory.events == {} and context == original
    history.assert_not_called()


def test_missing_delivery_field_refuses_before_reading_history(harness, monkeypatch):
    from unittest.mock import Mock
    run, memory, _, context, _ = harness
    for row in context['cases']:
        row['last_delivery_digest'] = row['evidence_digest']
    context['cases'][0].pop('last_delivery_digest')
    history = Mock(side_effect=AssertionError('history must not precede delivery-state validation'))
    monkeypatch.setattr(overview, '_read_events', history)
    result = run()
    assert result['success'] is False and result['failure_kind'] == 'ValueError'
    assert result['failure_stage'] == 'delivery_state' and result['coverage'] == []
    assert not memory.sent and not memory.events
    history.assert_not_called()


@pytest.mark.parametrize('reason', ['new_group', 'due_review'])
def test_new_or_due_work_still_requires_exact_family_history(harness, monkeypatch, reason):
    from unittest.mock import Mock
    run, memory, _, context, now = harness
    for row in context['cases']:
        row['last_delivery_digest'] = row['evidence_digest']
    if reason == 'new_group':
        context['cases'][0]['last_delivery_digest'] = None
    else:
        member = {k: context['cases'][0][k] for k in ('case_id', 'generation', 'evidence_digest')}
        member['membership_digest'] = context['cases'][0]['membership']['membership_digest']
        request = defer_event(member, now-timedelta(days=2), day=1)
        monkeypatch.setattr(overview, '_deferrals', lambda *a, **k: REAL_DEFERRALS(*a,
            **{**k, 'connect': lambda: ReadRows([request])}))
    history = Mock(side_effect=TimeoutError('private SQL details must never be retained'))
    monkeypatch.setattr(overview, '_read_events', history)
    result = run()
    assert result['success'] is False and result['failure_kind'] == 'TimeoutError'
    assert result['failure_stage'] == 'history' and result['coverage'] == []
    assert 'private SQL' not in str(result) and not memory.sent and not memory.events
    history.assert_called_once()


@pytest.mark.parametrize('stage', ['membership', 'deferrals', 'history'])
def test_caught_source_failures_keep_fixed_stage_and_only_exception_type(harness, monkeypatch, stage):
    run, memory, raw, context, now = harness
    def fail(*args, **kwargs):
        raise TimeoutError('private SQL, animal or owner data must not be copied')
    if stage == 'membership':
        monkeypatch.setattr(membership, 'list_current_review_cases', fail)
        result = overview.dispatch_purpose_overview(raw, cycle_id='CYCLE-A', now=now,
            deadline_monotonic=time.monotonic()+80)
    else:
        monkeypatch.setattr(overview, '_deferrals' if stage == 'deferrals' else '_read_events', fail)
        result = run()
    assert result['failure_kind'] == 'TimeoutError' and result['failure_stage'] == stage
    assert result['success'] is False and result['coverage'] == []
    assert 'private SQL' not in str(result) and not memory.sent and not memory.events


@pytest.mark.parametrize('stage', ['membership', 'deferrals', 'history', 'dispatch', 'coverage'])
def test_postgres_contained_overview_exception_persists_once_without_per_case_failure(overview_db, monkeypatch, stage):
    import json
    pg, connect = overview_db
    configure_owner(monkeypatch)
    raw, context = production_packet(pg.now)
    pg.seed(raw)
    with connect() as db:
        db.execute('update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s', (pg.now-timedelta(days=1),))
        before = db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall()
    def fail(*args, **kwargs):
        raise TimeoutError('private SQL details must never be retained')
    if stage == 'membership':
        monkeypatch.setattr(membership, 'list_current_review_cases', fail)
    elif stage == 'deferrals':
        monkeypatch.setattr(overview, '_deferrals', fail)
    elif stage == 'history':
        # A real attributable due request forces history even for old URL cards.
        member = {k: context['cases'][0][k] for k in ('case_id', 'generation', 'evidence_digest')}
        member['membership_digest'] = context['cases'][0]['membership']['membership_digest']
        request = defer_event(member, pg.now-timedelta(days=2), day=1)
        with connect() as db:
            db.execute("insert into app_private.oom_manager_case_events(event_id,case_id,generation,event_type,event_payload,occurred_at) values(%s,%s,%s,'reassessment_scheduled',%s::jsonb,%s)",
                (request[2], request[0], request[1], json.dumps(request[3]), request[4]))
        monkeypatch.setattr(overview, '_read_events', fail)
    elif stage == 'dispatch':
        monkeypatch.setattr(overview, 'dispatch_purpose_overview', fail)
    else:
        monkeypatch.setattr(pg.store, '_record_purpose_overview_coverage', fail)
    from modules.oom_sakkie import family_message_lifecycle as family
    monkeypatch.setattr(family, '_send_telegram', lambda *a, **k: pytest.fail('no provider effect is allowed'))
    result = worker.run_general_manager_cycle(now=pg.now, source_revision='synthetic-continuity', store=pg.store,
        collectors=[lambda now: sources._purpose_review_candidates(context['snapshot'], now=now, today=DAY, observed_at=now)],
        deliver=worker.deliver_farm_manager_case)
    assert result['success'] is True  # Existing contained worker completion semantics.
    assert result['exceptions'] == 1 and result['deadline_deferrals'] == 0
    component = result['purpose_overview']
    assert component['success'] is False and component['exceptions'] == 1
    assert component['failure_kind'] == 'TimeoutError' and component['failure_stage'] == stage
    assert component['telegram_sends'] == component['telegram_edits'] == component['covered_cases'] == 0
    assert all(r['outcome_status'] == 'manager_delivery_duplicate_suppressed' for r in result['case_results'])
    with connect() as db:
        status, counts = db.execute('select status,case_counts from app_private.oom_manager_worker_cycles where cycle_id=%s', (result['cycle_id'],)).fetchone()
        assert status == 'completed' and counts['exceptions'] == 1 and counts['purpose_overview'] == component
        assert db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall() == before
        assert db.execute('select count(*) from app_private.oom_protected_action_claims').fetchone()[0] == 0
        assert db.execute('select count(*) from public.sam_live_stock_conversation_review_events').fetchone()[0] == 0
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_overview_coverage' or event_type='delivery_confirmed'").fetchone()[0] == 0
    assert 'private SQL' not in json.dumps(counts)


@pytest.mark.parametrize('status', ['purpose_overview_deadline_deferred', 'purpose_overview_prior_attempt_contained', 'purpose_overview_delivery_unproven'])
def test_postgres_expected_no_send_without_exception_is_not_counted_as_exception(overview_db, monkeypatch, status):
    pg, connect = overview_db
    configure_owner(monkeypatch)
    raw, context = production_packet(pg.now)
    pg.seed(raw)
    with connect() as db:
        db.execute('update app_private.oom_manager_cases set last_delivery_digest=evidence_digest')
    monkeypatch.setattr(overview, 'dispatch_purpose_overview', lambda *a, **k: overview._empty(status))
    result = worker.run_general_manager_cycle(now=pg.now, source_revision='synthetic-contained-outcome', store=pg.store,
        collectors=[lambda now: sources._purpose_review_candidates(context['snapshot'], now=now, today=DAY, observed_at=now)],
        deliver=worker.deliver_farm_manager_case)
    assert result['success'] and result['exceptions'] == result['purpose_overview']['exceptions'] == 0
    assert result['purpose_overview']['status'] == status and result['purpose_overview']['success'] is False
    assert 'failure_kind' not in result['purpose_overview'] and 'failure_stage' not in result['purpose_overview']
    with connect() as db:
        counts = db.execute('select case_counts from app_private.oom_manager_worker_cycles where cycle_id=%s', (result['cycle_id'],)).fetchone()[0]
        assert counts['exceptions'] == 0 and counts['purpose_overview'] == result['purpose_overview']
        assert db.execute('select count(*) from app_private.oom_protected_action_claims').fetchone()[0] == 0
        assert db.execute('select count(*) from public.sam_live_stock_conversation_review_events').fetchone()[0] == 0
