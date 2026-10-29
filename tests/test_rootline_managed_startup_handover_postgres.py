"""Real database interleavings of canonical managed-output ON and OFF ownership."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
from threading import Event
import uuid

import pytest

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
bounded = importlib.import_module('modules.oom_sakkie.bounded_postgres_read')
pytestmark = pytest.mark.skipif(not os.getenv('ROOTLINE_DISPOSABLE_POSTGRES_URL'),
                              reason='isolated ROOTLINE PostgreSQL required')

@pytest.fixture
def db(monkeypatch):
    import psycopg
    url=os.environ['ROOTLINE_DISPOSABLE_POSTGRES_URL']
    assert '127.0.0.1:' in url and url.endswith('/rootline_managed')
    with psycopg.connect(url) as c:
        c.execute((Path(__file__).resolve().parents[1]/'supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql').read_text())
    monkeypatch.setenv('DATABASE_URL',url)
    monkeypatch.setattr(store,'EVENT_SOURCE','startup-test-'+uuid.uuid4().hex)
    return url

def seed(db, action, body):
    import psycopg
    with psycopg.connect(db) as c:
        with c.cursor() as cursor:
            return store._insert_managed_event(cursor,action,body)

def execution(db, kind):
    now=datetime.now(timezone.utc)
    body={'execution_id':'TEST-'+uuid.uuid4().hex,'claimed_at':now.isoformat(),
          'primary_stop_deadline':(now+timedelta(seconds=600)).isoformat(),
          'maximum_duration_seconds':600,'state':'claimed','on_attempts':0,'off_attempts':0}
    if kind=='borehole':
        body['device_key']='ewelink:ewelink_owner_account:1002851416:1'
    else:
        body.update(auxiliary_device_id='FERTILIZER-MIXER-CH2' if kind=='mixer' else 'FERTILIZER-INJECTION-CH1',
                    device_type='fertilizer_mixer' if kind=='mixer' else 'fertilizer_injection_valve',
                    device_id='100204d497',channel=2 if kind=='mixer' else 1)
    if kind=='injector':
        body.update(zone_execution_id='PARENT-'+uuid.uuid4().hex,job_id='JOB',job_sha256='a'*64,
                    segment_identity='SEGMENT',zone_id='B12345')
        seed(db,'claim_before_on',{**body,'execution_id':body['zone_execution_id']})
    family=store._managed_family(borehole=kind=='borehole')
    seed(db,family['claim'],body)
    return body,family

def dispatch(body,kind,fn):
    return store.rootline_irrigation_execution_store('dispatch_borehole_on_edge' if kind=='borehole'
        else 'dispatch_auxiliary_on_edge',{**body,'dispatch':fn})

def off(body,family):
    return store.rootline_irrigation_execution_store(family['off'],{'execution_id':body['execution_id'],'attempt':1})

def rows(db,body):
    import psycopg
    with psycopg.connect(db) as c:
        with c.cursor() as cur:return store._managed_edge_rows(cur,body['execution_id'])

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_off_wins_and_late_active_cannot_resurrect(db,kind):
    body,family=execution(db,kind);called=[]
    assert off(body,family)['created']
    assert not dispatch(body,kind,lambda:called.append('ON'))['accepted_unambiguous']
    active=store.rootline_irrigation_execution_store(family['active'],{**body,'state':'Active','on_attempts':1})
    assert not active['success'] and called==[]

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_on_final_edge_serializes_off_claim_and_commits_attempt_before_io(db,kind):
    body,family=execution(db,kind);entered=Event();release=Event();off_entered=Event();order=[]
    def send():
        # A separate real session sees the committed marker while ON's transaction is open.
        assert sum(r['action']==family['dispatch'] for r in rows(db,body))==1
        order.append('ON');entered.set();assert release.wait(2)
        return {'accepted_unambiguous':True}
    def stop():
        off_entered.set(); result=off(body,family);order.append('OFF-CLAIM');return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        start=pool.submit(dispatch,body,kind,send)
        assert entered.wait(2)
        stopping=pool.submit(stop);assert off_entered.wait(2)
        assert not stopping.done()
        release.set()
        assert start.result(2)['accepted_unambiguous'];assert stopping.result(2)['created']
    assert order==['ON','OFF-CLAIM']
    assert not store.rootline_irrigation_execution_store(family['active'],
        {**body,'state':'Active','on_attempts':1})['success']

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_concurrent_duplicate_dispatch_and_unknown_sender_never_resend(db,kind):
    body,family=execution(db,kind);calls=[]
    def send():calls.append('ON');return {'accepted_unambiguous':True}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:dispatch(body,kind,send),range(2)))
    assert sum(r['accepted_unambiguous'] for r in results)==1 and calls==['ON']
    body,family=execution(db,kind);calls=[]
    def unknown():calls.append('ON');raise TimeoutError('synthetic ambiguous provider response')
    assert not dispatch(body,kind,unknown)['accepted_unambiguous']
    assert not dispatch(body,kind,unknown)['accepted_unambiguous'] and calls==['ON']
    assert sum(r['action']==family['dispatch'] for r in rows(db,body))==1

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_crash_after_committed_marker_and_off_between_transactions(db,kind,monkeypatch):
    body,family=execution(db,kind);real=bounded.connect_bounded_rootline_postgres;calls=[];n=0
    def fail_second(**kwargs):
        nonlocal n
        n+=1
        if n==2:raise RuntimeError('synthetic crash after commit')
        return real(**kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(bounded,'connect_bounded_rootline_postgres',fail_second)
        with pytest.raises(RuntimeError,match='after commit'):dispatch(body,kind,lambda:calls.append('ON'))
    assert sum(r['action']==family['dispatch'] for r in rows(db,body))==1
    assert not dispatch(body,kind,lambda:calls.append('ON'))['accepted_unambiguous'] and calls==[]
    body,family=execution(db,kind);n=0
    def stop_second(**kwargs):
        nonlocal n
        n+=1
        if n==2:
            with real(**kwargs) as c:
                with c.cursor() as cur:store._insert_managed_event(cur,family['off'],{'execution_id':body['execution_id'],'attempt':1})
        return real(**kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(bounded,'connect_bounded_rootline_postgres',stop_second)
        assert not dispatch(body,kind,lambda:calls.append('ON'))['accepted_unambiguous']
    assert calls==[]

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_exact_claim_and_age_are_rechecked_and_terminal_blocks_activation(db,kind):
    body,family=execution(db,kind);calls=[]
    assert not dispatch({**body,'maximum_duration_seconds':601},kind,lambda:calls.append('ON'))['accepted_unambiguous']
    assert dispatch(body,kind,lambda:{'accepted_unambiguous':True})['accepted_unambiguous']
    assert store.rootline_irrigation_execution_store(family['active'],{**body,'state':'Active','on_attempts':1})['success']
    assert not dispatch(body,kind,lambda:calls.append('ON'))['accepted_unambiguous']
    body,family=execution(db,kind)
    terminal='contain_borehole' if kind=='borehole' else 'contain_auxiliary_device'
    assert store.rootline_irrigation_execution_store(terminal,body)['success']
    assert not store.rootline_irrigation_execution_store(family['active'],{**body,'state':'Active','on_attempts':1})['success']
    assert calls==[]

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_actual_loader_fresh_claim_gets_grace_then_real_recovery(db,kind):
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    body,family=execution(db,kind);calls=[]
    class Transport:
        def set_state(self,**kwargs):calls.append(kwargs['state']);return {'accepted_unambiguous':True}
        def read_output_state(self,**kwargs):return {'authoritative':True,'state':'OFF'}
    run=advance_borehole_execution if kind=='borehole' else advance_auxiliary_execution
    now=datetime.fromisoformat(body['claimed_at'])
    got=run(eligibility=None,store=store.rootline_irrigation_execution_store,transport=Transport(),now=now)
    assert got['status'].endswith('claim_in_progress') and calls==[]
    got=run(eligibility=None,store=store.rootline_irrigation_execution_store,transport=Transport(),now=now+timedelta(seconds=31))
    assert calls==['OFF'] and 'started' not in got['status']
    assert not dispatch(body,kind,lambda:calls.append('ON'))['accepted_unambiguous']


def test_injector_parent_stop_remains_a_fence_mixer_has_no_parent(db):
    body,family=execution(db,'injector')
    seed(db,'mark_stopping',{'execution_id':body['zone_execution_id']})
    assert dispatch(body,'injector',lambda:{'accepted_unambiguous':True})['status']=='parent_edge_authority_revoked'
    mixer,_=execution(db,'mixer')
    assert dispatch(mixer,'mixer',lambda:{'accepted_unambiguous':True})['accepted_unambiguous']

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
@pytest.mark.parametrize('late_off',[False,True])
def test_actual_coordinator_claim_dispatch_and_late_mark_path(db,kind,late_off,monkeypatch):
    from tests import test_rootline_fertilizer_auxiliary as aux
    from tests import test_rootline_borehole_commissioning as bh
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(aux,'NOW',now);monkeypatch.setattr(bh,'NOW',now)
    if kind=='borehole':
        artifact=bh.build_borehole_runtime_eligibility(need={'eligible':True},
            baseline={**bh.canonical(),'registry_generation':2},
            authority={'inside_standing_authority':True},provider={'authoritative':True,'state':'OFF'},
            interlocks={'dry_run_safe':True,'low_water_clear':True,'supply_pressure_safe':True,'full_tank_not_blocking':True},
            energy={'eligible':True},requested_seconds=60,now=now)
        seed(db,'record_borehole_eligibility',artifact)
        transport=bh.BoreholeTransport();run=bh.advance_borehole_execution;extra={}
    else:
        transport=aux.Transport();run=advance_auxiliary_execution
        if kind=='injector':
            context=aux.injection_context();parent_id='PARENT-'+uuid.uuid4().hex
            context['zone_execution_id']=parent_id
            context['zone_start_evidence']['zone_execution_id']=parent_id
            context['zone_output_evidence']['zone_execution_id']=parent_id
            artifact=aux.build_auxiliary_eligibility(task={'auxiliary_device_id':'FERTILIZER-INJECTION-CH1'},
                safety=aux.safety(),context=context,flags={'ROOTLINE_FERTILIZER_INJECTION_ENABLED':True},now=now)
            parent={**context,'execution_id':context['zone_execution_id'],'zone_id':'B12345'}
            seed(db,'claim_before_on',parent);seed(db,'mark_active',{**parent,'state':'Active'})
        else:
            artifact=aux.mixer_eligibility()
            context={'plan_generation':'PLAN-MIX-1','injection_active':False,
                'verified_mixing_minutes_today':0,'verified_mixing_sessions_today':0,
                'mixing_history_valid':True,'reserved_mixing_seconds_today':0,
                'mixing_history_complete_through':now.isoformat(),'power_suitable':True}
        extra={'revalidate':lambda _:context}
    family=store._managed_family(borehole=kind=='borehole')
    def actual_store(action,body):
        if late_off and action==family['active']:
            # Recovery wins after provider ON/readback but before Active publication.
            assert off(body,family)['created']
        return store.rootline_irrigation_execution_store(action,body)
    result=run(eligibility=artifact,store=actual_store,transport=transport,now=now,**extra)
    calls=transport.commands if kind=='borehole' else transport.calls
    assert [c['state'] for c in calls]==(['ON','OFF'] if late_off else ['ON']), result
    assert result['status']==(('borehole_start_failure_contained' if kind=='borehole'
        else 'auxiliary_active_persistence_unproven') if late_off else
        ('borehole_started' if kind=='borehole' else 'auxiliary_started'))
    recorded=rows(db,{'execution_id':artifact['execution_id']})
    assert sum(r['action']==family['dispatch'] for r in recorded)==1
    assert sum(r['action']==family['active'] for r in recorded)==(0 if late_off else 1)

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_expired_exact_claim_never_sends(db,kind):
    body,family=execution(db,kind)
    body={**body,'execution_id':'EXPIRED-'+uuid.uuid4().hex,
          'claimed_at':(datetime.now(timezone.utc)-timedelta(seconds=31)).isoformat()}
    seed(db,family['claim'],body);calls=[]
    assert not dispatch(body,kind,lambda:calls.append('ON'))['accepted_unambiguous']
    assert calls==[] and not any(r['action']==family['dispatch'] for r in rows(db,body))

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_legacy_on_outcome_without_new_marker_is_already_consumed(db,kind):
    body,family=execution(db,kind)
    seed(db,family['outcome'],{**body,'on_attempts':1,'on_outcome':{'accepted_unambiguous':False}})
    calls=[]
    assert not dispatch(body,kind,lambda:calls.append('ON'))['accepted_unambiguous']
    assert calls==[] and not any(r['action']==family['dispatch'] for r in rows(db,body))


@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_legacy_active_without_claim_keeps_safety_off(db,kind):
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    now=datetime.now(timezone.utc)
    row={'execution_id':'ORPHAN-'+__import__('uuid').uuid4().hex,'state':'Active',
         'claimed_at':(now-timedelta(seconds=601)).isoformat(),
         'primary_stop_deadline':(now-timedelta(seconds=1)).isoformat(),
         'maximum_duration_seconds':600,'on_attempts':1,
         'start_evidence':{'authoritative':True,'state':'ON','retrieved_at':(now-timedelta(seconds=601)).isoformat()},
         'provider_start_evidence':{'authoritative':True,'state':'ON'},
         'auxiliary_device_id':'FERTILIZER-MIXER-CH2','device_type':'fertilizer_mixer',
         'device_id':'100204d497','channel':2}
    if kind=='borehole':row['device_key']='ewelink:ewelink_owner_account:1002851416:1'
    if kind=='injector':row.update(auxiliary_device_id='FERTILIZER-INJECTION-CH1',device_type='fertilizer_injection_valve',channel=1)
    seed(db,'mark_borehole_active' if kind=='borehole' else 'mark_auxiliary_active',row)
    calls=[]
    class Transport:
        def set_state(self,**kw):calls.append(kw['state']);return {'accepted_unambiguous':True}
        def read_output_state(self,**kw):return {'authoritative':True,'state':'OFF' if calls else 'ON',
            'evidence_id':'ACTUAL-SYNTHETIC','retrieved_at':datetime.now(timezone.utc).isoformat()}
    fn=advance_borehole_execution if kind=='borehole' else advance_auxiliary_execution
    result=fn(eligibility=None,store=store.rootline_irrigation_execution_store,transport=Transport(),now=now)
    assert calls==['OFF'],result

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
@pytest.mark.parametrize('mismatch',['device','family','state','execution'])
def test_orphan_off_requires_exact_active_identity(db,kind,mismatch):
    body,family=execution(db,kind)
    # Give the orphan a fresh identity so no canonical claim can mask this check.
    body={**body,'execution_id':'ORPHAN-BAD-'+uuid.uuid4().hex,'state':'Active'}
    action=family['active']
    if mismatch=='device':
        if kind=='borehole':body['device_key']='ewelink:ewelink_owner_account:wrong:1'
        else:body['channel']=4
    elif mismatch=='family':action='mark_auxiliary_active' if kind=='borehole' else 'mark_borehole_active'
    elif mismatch=='state':body['state']='Unknown'
    seed(db,action,body)
    target={**body,'execution_id':'OTHER-'+uuid.uuid4().hex} if mismatch=='execution' else body
    assert not off(target,family)['created']
    assert not dispatch(body,kind,lambda:{'accepted_unambiguous':True})['accepted_unambiguous']

@pytest.mark.parametrize('attempt',[0,4,True,'1'])
def test_orphan_off_retains_numeric_attempt_bound_and_unique_marker(db,attempt):
    body,family=execution(db,'mixer');body={**body,'execution_id':'ORPHAN-LIMIT-'+uuid.uuid4().hex,'state':'Active'}
    seed(db,family['active'],body)
    assert not store.rootline_irrigation_execution_store(family['off'],{'execution_id':body['execution_id'],'attempt':attempt})['created']
    assert off(body,family)['created']
    assert not off(body,family)['created']


def borehole_start_artifact(now):
    from tests import test_rootline_borehole_commissioning as bh
    return bh.build_borehole_runtime_eligibility(need={'eligible':True},
        baseline={**bh.canonical(),'registry_generation':2},
        authority={'inside_standing_authority':True},provider={'authoritative':True,'state':'OFF'},
        interlocks={'dry_run_safe':True,'low_water_clear':True,'supply_pressure_safe':True,
            'full_tank_not_blocking':True},energy={'eligible':True},requested_seconds=60,now=now)


def test_managed_borehole_persists_exact_eligibility_and_claims_after_delayed_reads(db,monkeypatch):
    from functools import partial
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from tests import test_rootline_borehole_commissioning as bh
    scheduler_time=datetime.now(timezone.utc)-timedelta(seconds=31)
    artifact=borehole_start_artifact(scheduler_time); events=[]; safety_finished=[]
    class DelayedTransport(bh.BoreholeTransport):
        def read_safety_configuration(self,**kwargs):
            # Virtual provider latency: no sleeps and no change to the store's real clock.
            safety_finished.append(datetime.now(timezone.utc))
            return super().read_safety_configuration(**kwargs)
    def claim_clock():
        assert safety_finished, 'claim clock must be read after native safety'
        return safety_finished[-1]
    def actual_store(action,body):
        events.append(action)
        return store.rootline_irrigation_execution_store(action,body)
    monkeypatch.setattr(managed,'advance_borehole_execution',partial(
        bh.advance_borehole_execution,clock=claim_clock))
    transport=DelayedTransport()
    result=managed.run_rootline_managed_device_cycle(evidence=None,transport=transport,
        evidence_factory=lambda:{'borehole_execution':artifact},store=actual_store,
        environ={'ROOTLINE_BOREHOLE_ENABLED':'true'},now=scheduler_time)
    assert result['status']=='borehole_started',result
    assert [row['state'] for row in transport.commands]==['ON']
    saved=rows(db,artifact)
    canonical=next(row for row in saved if row['action']=='record_borehole_eligibility')
    claimed=next(row for row in saved if row['action']=='claim_borehole_before_on')
    assert all(canonical[key]==value for key,value in artifact.items())
    assert all(claimed[key]==value for key,value in artifact.items())
    assert datetime.fromisoformat(claimed['claimed_at'])==safety_finished[0]
    assert datetime.fromisoformat(claimed['claimed_at'])-scheduler_time>=timedelta(seconds=31)
    assert datetime.fromisoformat(claimed['primary_stop_deadline'])==safety_finished[0]+timedelta(seconds=60)
    assert datetime.fromisoformat(claimed['native_fail_stop_deadline'])==safety_finished[0]+timedelta(seconds=1800)
    assert claimed['assessed_at']==scheduler_time.isoformat()
    assert events.index('record_borehole_eligibility')<events.index('claim_borehole_before_on')
    assert sum(row['action']=='claim_borehole_dispatch' for row in saved)==1


def test_borehole_direct_unrecorded_eligibility_is_still_refused_by_real_claim(db):
    from tests import test_rootline_borehole_commissioning as bh
    now=datetime.now(timezone.utc);artifact=borehole_start_artifact(now);transport=bh.BoreholeTransport()
    result=bh.advance_borehole_execution(eligibility=artifact,store=store.rootline_irrigation_execution_store,
        transport=transport,now=now)
    assert result['status']=='borehole_claim_conflict'
    assert transport.commands==[] and rows(db,artifact)==[]


@pytest.mark.parametrize('failure',[None,{'success':False},'unavailable'])
def test_managed_borehole_eligibility_persistence_denial_never_claims(db,failure):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from tests import test_rootline_borehole_commissioning as bh
    now=datetime.now(timezone.utc);artifact=borehole_start_artifact(now);transport=bh.BoreholeTransport();actions=[]
    def failing_store(action,body):
        actions.append(action)
        if action=='record_borehole_eligibility':
            assert body==artifact
            if failure=='unavailable':raise store.RootlineExecutionStoreUnavailable('synthetic persistence failure')
            return failure
        return store.rootline_irrigation_execution_store(action,body)
    result=managed.run_rootline_managed_device_cycle(evidence={'borehole_execution':artifact},
        transport=transport,store=failing_store,environ={'ROOTLINE_BOREHOLE_ENABLED':'true'},now=now)
    assert not result['success'] and result['status']=='borehole_eligibility_persistence_unproven'
    assert not result['blocks_bc'] and transport.commands==[] and rows(db,artifact)==[]
    assert 'claim_borehole_before_on' not in actions


@pytest.mark.parametrize('gate',['active_only','disabled','ineligible'])
def test_managed_borehole_start_gates_do_not_record_or_command(db,gate):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from tests import test_rootline_borehole_commissioning as bh
    now=datetime.now(timezone.utc);artifact=borehole_start_artifact(now);transport=bh.BoreholeTransport();actions=[]
    def actual_store(action,body):
        actions.append(action)
        return store.rootline_irrigation_execution_store(action,body)
    def factory():
        assert gate!='active_only','active-only must not invoke the planner'
        return {'borehole_execution':{**artifact,'eligible':gate!='ineligible'}}
    result=managed.run_rootline_managed_device_cycle(evidence=None,evidence_factory=factory,
        transport=transport,store=actual_store,environ={'ROOTLINE_BOREHOLE_ENABLED':str(gate!='disabled').lower()},
        now=now,allow_new_starts=gate!='active_only')
    assert result['hardware_commands']==0 and transport.commands==[] and rows(db,artifact)==[]
    assert not any(action.startswith(('record_','claim_','dispatch_')) for action in actions)


def test_managed_borehole_native_safety_refusal_stays_before_claim(db):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from tests import test_rootline_borehole_commissioning as bh
    now=datetime.now(timezone.utc);artifact=borehole_start_artifact(now)
    class UnsafeTransport(bh.BoreholeTransport):
        def read_safety_configuration(self,**kwargs):
            return {'native_auto_off_enabled':False,'native_auto_off_seconds':1800}
    transport=UnsafeTransport()
    result=managed.run_rootline_managed_device_cycle(evidence={'borehole_execution':artifact},
        transport=transport,store=store.rootline_irrigation_execution_store,
        environ={'ROOTLINE_BOREHOLE_ENABLED':'true'},now=now)
    assert result['status']=='borehole_native_readback_changed' and transport.commands==[]
    assert [row['action'] for row in rows(db,artifact)]==['record_borehole_eligibility']
