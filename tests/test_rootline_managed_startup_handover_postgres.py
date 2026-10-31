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
            parent={**context,'execution_id':context['zone_execution_id'],'zone_id':'B12345',
                'device_id':'100204e9bc','channel':1,'primary_stop_deadline':context['irrigation_stop_deadline']}
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
    assert result['status']==(('borehole_start_aborted' if kind=='borehole'
        else 'auxiliary_active_persistence_unproven') if late_off else
        ('borehole_started' if kind=='borehole' else 'auxiliary_started'))
    recorded=rows(db,{'execution_id':artifact['execution_id']})
    assert sum(r['action']==family['dispatch'] for r in recorded)==1
    assert sum(r['action']==family['active'] for r in recorded)==(0 if late_off else 1)
    if late_off and kind == 'borehole':
        aborted = next(row for row in recorded if row['action'] == 'record_borehole_aborted')
        assert aborted['on_attempts'] == 1 and aborted['off_attempts'] == 2

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


def borehole_start_artifact(now, registry_generation=2):
    from tests import test_rootline_borehole_commissioning as bh
    return bh.build_borehole_runtime_eligibility(need={'eligible':True},
        baseline={**bh.canonical(),'registry_generation':registry_generation},
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
            return {'native_inching_enabled':False,'native_inching_seconds':1800}
    transport=UnsafeTransport()
    result=managed.run_rootline_managed_device_cycle(evidence={'borehole_execution':artifact},
        transport=transport,store=store.rootline_irrigation_execution_store,
        environ={'ROOTLINE_BOREHOLE_ENABLED':'true'},now=now)
    assert result['status']=='borehole_native_readback_changed' and transport.commands==[]
    assert [row['action'] for row in rows(db,artifact)]==['record_borehole_eligibility']


@pytest.mark.parametrize('configuration',['valid','disabled','changed_duration','missing_duration','wrong_device'])
def test_managed_borehole_uses_real_transport_safety_and_command_contract(db,configuration):
    from copy import deepcopy
    from urllib.parse import urlsplit
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from tests import test_rootline_borehole_commissioning as bh
    now=datetime.now(timezone.utc)
    artifact=bh.build_borehole_runtime_eligibility(need={'eligible':True},
        baseline={**bh.canonical(maximum_routine_runtime_seconds=3600,native_fail_stop_seconds=3600),
            'registry_generation':3},authority={'inside_standing_authority':True},
        provider={'authoritative':True,'state':'OFF'},interlocks={'dry_run_safe':True,
            'low_water_clear':True,'supply_pressure_safe':True,'full_tank_not_blocking':True},
        energy={'eligible':True},requested_seconds=600,now=now)
    snapshot={'device_id':'1002851416','provider_control_calls':0,
        'current_outputs_authoritative':True,'timers_enabled':False,'scenes_enabled':False,
        'interlock_enabled':False,'response_digest':'a'*64,'retrieved_at':now.isoformat(),
        'channels':[{'channel':1,'output_state':'OFF','native_auto_off_enabled':True,
            'native_auto_off_seconds':3600,'power_restoration_state':'OFF'}]}
    target=snapshot['channels'][0]
    if configuration=='disabled':target['native_auto_off_enabled']=False
    if configuration=='changed_duration':target['native_auto_off_seconds']=1800
    if configuration=='missing_duration':target.pop('native_auto_off_seconds')
    if configuration=='wrong_device':snapshot['device_id']='wrong-device'
    requests=[]
    class Response:
        status=200
        def getcode(self):return self.status
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def read(self,_limit):return b'accepted synthetic IFTTT response'
    def no_network_open(request,timeout):
        requests.append(request)
        assert configuration=='valid' and len(requests)==1
        url=urlsplit(request.full_url)
        assert (url.scheme,url.netloc,url.path)==('https','maker.ifttt.com',
            '/trigger/borehole_1_on/with/key/synthetic-only')
        assert request.get_method()=='POST' and timeout==15
        assert json.loads(request.data)=={'value1':artifact['execution_id']+':ON',
            'value2':'1002851416','value3':'1'}
        target['output_state']='ON'
        return Response()
    transport=RootlineIFTTTTransport(token_store=object(),
        environ={'ROOTLINE_BOREHOLE_ENABLED':'true','ROOTLINE_IFTTT_MAKER_KEY':'synthetic-only'},
        http_open=no_network_open,readback=lambda **_:deepcopy(snapshot))
    if configuration!='wrong_device':
        safety=transport.read_safety_configuration(device_id='1002851416',channel=1)
        assert 'native_auto_off_enabled' not in safety and 'native_auto_off_seconds' not in safety
        assert safety['native_inching_enabled']==target['native_auto_off_enabled']
        assert safety['native_inching_seconds']==target.get('native_auto_off_seconds')
    result=managed.run_rootline_managed_device_cycle(evidence={'borehole_execution':artifact},
        transport=transport,store=store.rootline_irrigation_execution_store,
        environ={'ROOTLINE_BOREHOLE_ENABLED':'true'},now=now)
    saved=rows(db,artifact)
    if configuration=='valid':
        assert result['status']=='borehole_started' and len(requests)==1,result
        assert result['execution']['provider_start_evidence']['state']=='ON'
        assert result['execution']['provider_start_evidence']['authoritative'] is True
        assert sum(row['action']=='claim_borehole_dispatch' for row in saved)==1
        assert sum(row['action']=='mark_borehole_active' for row in saved)==1
        assert result['execution']['native_fail_stop_seconds']==3600
    else:
        assert result['status'] in {'borehole_native_readback_changed','borehole_native_readback_unproven'}
        assert requests==[] and [row['action'] for row in saved]==['record_borehole_eligibility']


@pytest.mark.parametrize('winner',['mixer','borehole'])
def test_borehole_and_mixer_admission_serializes_but_both_may_operate(db,monkeypatch,winner):
    now=datetime.now(timezone.utc);artifact=borehole_start_artifact(now)
    seed(db,'record_borehole_eligibility',artifact)
    borehole={**artifact,'state':'claimed','claimed_at':now.isoformat(),
        'primary_stop_deadline':(now+timedelta(seconds=60)).isoformat(),
        'native_fail_stop_deadline':(now+timedelta(seconds=1800)).isoformat(),
        'on_attempts':0,'off_attempts':0}
    mixer={'execution_id':'RACE-MIXER-'+uuid.uuid4().hex,'consumption_key':uuid.uuid4().hex,
        'auxiliary_device_id':'FERTILIZER-MIXER-CH2','device_type':'fertilizer_mixer',
        'device_id':'100204d497','channel':2,'state':'claimed','claimed_at':now.isoformat(),
        'primary_stop_deadline':(now+timedelta(seconds=600)).isoformat(),
        'maximum_duration_seconds':600,'on_attempts':0,'off_attempts':0}
    bodies={'mixer':mixer,'borehole':borehole};loser='mixer' if winner=='borehole' else 'borehole'
    real=bounded.connect_bounded_rootline_postgres;first=[True];inserted=Event();release=Event();competing=Event()
    @contextmanager
    def pause_first_commit(**kwargs):
        owned=first[0];first[0]=False
        with real(**kwargs) as connection:
            yield connection
            if owned:
                inserted.set();assert release.wait(2)
    def claim(kind):
        if kind==loser:competing.set()
        action='claim_borehole_before_on' if kind=='borehole' else 'claim_auxiliary_before_on'
        return store.rootline_irrigation_execution_store(action,bodies[kind])
    with monkeypatch.context() as scoped:
        scoped.setattr(bounded,'connect_bounded_rootline_postgres',pause_first_commit)
        with ThreadPoolExecutor(max_workers=2) as pool:
            winning=pool.submit(claim,winner);assert inserted.wait(2)
            losing=pool.submit(claim,loser);assert competing.wait(2) and not losing.done()
            release.set();assert winning.result(2)['created']
            accepted=losing.result(2);assert accepted['created']
    calls=[]
    for kind in (winner,loser):
        assert dispatch(bodies[kind],kind,lambda kind=kind:calls.append(kind) or {'accepted_unambiguous':True})['accepted_unambiguous']
        assert not dispatch(bodies[kind],kind,lambda:calls.append('duplicate'))['accepted_unambiguous']
    assert calls==[winner,loser]


@pytest.mark.parametrize("phase", ["final_dispatch", "active_supervision"])
@pytest.mark.parametrize("conflict", ["both_bc", "a_on", "unknown", "missing", "read_failure"])
def test_actual_atomic_injector_path_refuses_new_physical_dependency_conflict(db, monkeypatch, phase, conflict):
    from tests import test_rootline_fertilizer_auxiliary as aux
    from tests.test_rootline_ifttt_transport import irrigation_snapshot
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(aux, "NOW", now)
    context = aux.injection_context()
    parent_id = "PARENT-"+uuid.uuid4().hex
    context["zone_execution_id"] = parent_id
    context["zone_start_evidence"]["zone_execution_id"] = parent_id
    context["zone_output_evidence"]["zone_execution_id"] = parent_id
    artifact = aux.build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
        safety=aux.safety(), context=context, flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True}, now=now)
    assert artifact["eligible"]
    parent = {**context, "execution_id":parent_id, "zone_id":"B12345", "device_id":"100204e9bc",
        "channel":1, "primary_stop_deadline":context["irrigation_stop_deadline"]}
    seed(db, "claim_before_on", parent)
    seed(db, "mark_active", {**parent,"state":"Active"})
    class Physical(aux.Transport):
        left_reads = 0
        def read_output_state(self, **kwargs):
            if kwargs["device_id"] != "100204e9bc":
                return super().read_output_state(**kwargs)
            self.left_reads += 1
            value = irrigation_snapshot(now)
            at_conflict = self.left_reads >= (2 if phase == "final_dispatch" else 3)
            if at_conflict:
                if conflict == "read_failure": raise TimeoutError("offline native read failure")
                if conflict == "both_bc": value["channels"][1]["output_state"] = "ON"
                if conflict == "a_on": value["channels"][3]["output_state"] = "ON"
                if conflict == "unknown": value["channels"][2]["output_state"] = "Unknown"
                if conflict == "missing": value["channels"].pop()
            return RootlineIFTTTTransport(token_store=None, environ={},
                readback=lambda **_:value).read_output_state(**kwargs)
    transport = Physical()
    def advance(at):
        return advance_auxiliary_execution(eligibility=artifact,
            store=store.rootline_irrigation_execution_store, transport=transport,
            revalidate=lambda _:context, now=at, clock=lambda:at)
    result = advance(now)
    if phase == "active_supervision":
        assert result["status"] == "auxiliary_started"
        result = advance(now+timedelta(seconds=10))
        assert result["status"] == "auxiliary_emergency_off_verified"
    assert [(row["device_id"],row["channel"],row["state"]) for row in transport.calls] == (
        [("100204d497",1,"ON"),("100204d497",1,"OFF")] if phase == "active_supervision"
        else [("100204d497",1,"OFF")])
    recorded = rows(db, artifact)
    assert sum(r["action"] == store._managed_family(borehole=False)["dispatch"] for r in recorded) == 1
    outcome = next(r["on_outcome"] for r in recorded if r["action"] == "record_auxiliary_on_outcome")
    if phase == "final_dispatch":
        assert outcome["provider_command_attempted"] is False
        assert result["hardware_commands"] == 1
    assert not any(r["action"] == "record_auxiliary_completed" for r in recorded)
    assert store.rootline_irrigation_execution_store("load_active", None)["execution_id"] == parent_id
    command_count = len(transport.calls)
    advance(now+timedelta(seconds=11))
    assert len(transport.calls) == command_count


@pytest.mark.parametrize("completed_pulses,required", [(0,1440),(1,720)])
@pytest.mark.parametrize("margin", [0,1])
def test_atomic_injector_dispatch_revalidates_flush_after_final_read(db,monkeypatch,completed_pulses,required,margin):
    from tests import test_rootline_fertilizer_auxiliary as aux
    from tests.test_rootline_injector_output_guard import PhysicalTransport
    from tests.test_rootline_ifttt_transport import irrigation_snapshot
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(aux,"NOW",now)
    current = [now]
    parent_id = "PARENT-"+uuid.uuid4().hex
    context = aux.injection_context(completed_pulses=completed_pulses,
        zone_execution_id=parent_id,
        irrigation_stop_deadline=(now+timedelta(seconds=required+margin)).isoformat(),
        prior_pulse_shutdown_evidence={"evidence_id":"PRIOR-"+uuid.uuid4().hex,
            "zone_execution_id":parent_id,"shutdown_verified":True,
            "observed_at":(now-timedelta(seconds=600)).isoformat()})
    context["zone_start_evidence"]["zone_execution_id"] = parent_id
    context["zone_output_evidence"]["zone_execution_id"] = parent_id
    artifact = aux.build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
        safety=aux.safety(),context=context,flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=now)
    assert artifact["eligible"]
    parent = {**context,"execution_id":parent_id,"zone_id":"B12345","device_id":"100204e9bc",
        "channel":1,"primary_stop_deadline":context["irrigation_stop_deadline"]}
    seed(db,"claim_before_on",parent)
    seed(db,"mark_active",{**parent,"state":"Active"})
    def after_read(number):
        if number == 2: current[0] = now+timedelta(seconds=1)
    transport = PhysicalTransport([irrigation_snapshot(now)],after_read=after_read)
    def advance():
        return advance_auxiliary_execution(eligibility=artifact,
            store=store.rootline_irrigation_execution_store,transport=transport,
            revalidate=lambda _:context,now=now,clock=lambda:current[0])
    result = advance()
    assert transport.left_reads == 2
    assert result["hardware_commands"] == 1
    assert [(r["device_id"],r["channel"],r["state"]) for r in transport.calls] == [
        ("100204d497",1,"ON" if margin else "OFF")]
    recorded = rows(db,artifact)
    assert sum(r["action"] == store._managed_family(borehole=False)["dispatch"] for r in recorded) == 1
    assert store.rootline_irrigation_execution_store("load_active",None)["execution_id"] == parent_id
    if margin:
        assert result["status"] == "auxiliary_started"
    else:
        outcome = next(r["on_outcome"] for r in recorded if r["action"] == "record_auxiliary_on_outcome")
        assert outcome["provider_command_attempted"] is False
        assert outcome["status"] == "auxiliary_edge_revalidation_failed"
        assert not any(r["action"] == "record_auxiliary_completed" for r in recorded)
        advance()
        assert [r["state"] for r in transport.calls] == ["OFF"]


def failed_borehole_claim(db, *, age_seconds=31, off_slots=0, registry_generation=2):
    at = datetime.now(timezone.utc)
    artifact = borehole_start_artifact(at, registry_generation=registry_generation)
    assert store.rootline_irrigation_execution_store("record_borehole_eligibility", artifact)["success"]
    claim = {**artifact, "claimed_at": (at-timedelta(seconds=age_seconds)).isoformat(),
        "primary_stop_deadline": (at+timedelta(seconds=60)).isoformat(),
        "native_fail_stop_deadline": (at+timedelta(seconds=1800)).isoformat(),
        "state": "claimed", "on_attempts": 0, "off_attempts": 0}
    assert store.rootline_irrigation_execution_store("claim_borehole_before_on", claim)["created"]
    for attempt in range(1, off_slots+1):
        assert store.rootline_irrigation_execution_store("claim_borehole_off_attempt",
            {"execution_id": claim["execution_id"], "attempt": attempt})["created"]
    return claim


def fresh_borehole_off():
    from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
    return output_evidence_from_snapshot({"device_id": "1002851416",
        "channels": [{"channel": 1, "output_state": "OFF"}],
        "current_outputs_authoritative": True, "response_digest": "d"*64,
        "retrieved_at": datetime.now(timezone.utc).isoformat()}, device_id="1002851416", channel=1)


def abort_borehole(claim, reader=fresh_borehole_off):
    return store.rootline_irrigation_execution_store("record_borehole_aborted",
        {**claim, "reason": "restart_without_verified_start", "read_final_off": reader})


def send_borehole_off(claim, sender, attempt=1):
    return store.rootline_irrigation_execution_store("dispatch_borehole_off_edge",
        {"execution_id": claim["execution_id"], "attempt": attempt, "dispatch": sender})


def test_failed_borehole_three_exhausted_off_slots_need_new_proof_not_old_containment(db):
    from modules.telemetry.rootline_borehole_commissioning import (
        advance_borehole_execution, _contain_failed_borehole_start)
    from tests.test_rootline_borehole_commissioning import BoreholeTransport
    claim = failed_borehole_claim(db, off_slots=3)
    old = fresh_borehole_off(); old["retrieved_at"] = "2026-01-01T00:00:00+00:00"
    seed(db, "contain_borehole", {**claim, "shutdown_verified": True,
        "provider_final_off_evidence": old})
    original = rows(db, claim)
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)
    transport = BoreholeTransport()
    result = advance_borehole_execution(eligibility=None, store=store.rootline_irrigation_execution_store,
        transport=transport, now=datetime.now(timezone.utc))
    assert result["status"] == "borehole_start_aborted" and not result["success"]
    assert result["hardware_commands"] == 0 and transport.commands == []
    assert result["writes_farm_data"] is True
    assert store.rootline_irrigation_execution_store("load_active_borehole", None) is None
    saved = rows(db, claim)
    assert saved[:-1] == original and saved[-1]["state"] == "Aborted"
    assert saved[-1]["objective_satisfied"] is False
    assert saved[-1]["on_attempts"] == 0 and saved[-1]["off_attempts"] == 3
    assert saved[-1]["provider_final_off_evidence"]["retrieved_at"] != old["retrieved_at"]
    assert not any(row["action"] in {"mark_borehole_active", "record_borehole_completed"} for row in saved)
    replay = _contain_failed_borehole_start(claim, store.rootline_irrigation_execution_store, transport)
    assert replay["status"] == "borehole_start_aborted" and replay["writes_farm_data"] is False
    assert replay["hardware_commands"] == 0 and rows(db, claim) == saved
    assert not store.rootline_irrigation_execution_store("claim_borehole_before_on", claim)["created"]
    called = []
    assert not dispatch(claim, "borehole", lambda: called.append("ON"))["accepted_unambiguous"]
    assert not send_borehole_off(claim, lambda: called.append("OFF"))["provider_command_attempted"]
    assert called == []
    fresh = failed_borehole_claim(db)
    assert fresh["execution_id"] != claim["execution_id"]


@pytest.mark.parametrize("field,value", [("authoritative", False), ("authoritative", "true"),
    ("state", "ON"), ("device_id", "other"), ("channel", 2), ("channel", True),
    ("evidence_id", ""), ("evidence_id", " "*64), ("evidence_id", "synthetic-generic"),
    ("retrieved_at", None), ("retrieved_at", "bad"), ("retrieved_at", "2026-01-01T00:00:00+00:00"),
    ("retrieved_at", "2099-01-01T00:00:00+00:00"), ("retrieved_at", "2026-10-31T01:00:00"),
    ("execution_id", "other")])
def test_borehole_abort_refuses_inexact_stale_future_or_unbound_off(db, field, value):
    claim = failed_borehole_claim(db, off_slots=1)
    result = abort_borehole(claim, lambda: {**fresh_borehole_off(), field: value})
    assert not result["success"]
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)["execution_id"] == claim["execution_id"]
    assert not any(row["action"] == "record_borehole_aborted" for row in rows(db, claim))
    candidate = borehole_start_artifact(datetime.now(timezone.utc))
    seed(db, "record_borehole_eligibility", candidate)
    assert not store.rootline_irrigation_execution_store("claim_borehole_before_on", candidate)["created"]


def test_borehole_abort_requires_read_after_lock_and_preserves_provider_timestamp(db):
    claim = failed_borehole_claim(db, off_slots=1)
    cached = fresh_borehole_off()
    assert not abort_borehole(claim, lambda: cached)["success"]
    observed = []
    def read():
        proof = fresh_borehole_off(); observed.append(proof); return proof
    result = abort_borehole(claim, read)
    assert result["success"] and result["created"]
    assert result["execution"]["provider_final_off_evidence"]["retrieved_at"] == observed[0]["retrieved_at"]


@pytest.mark.parametrize("conflict", ["no_barrier", "active", "completed", "claim_digest", "consumption", "reader"])
def test_borehole_abort_requires_original_claim_barrier_and_failed_lifecycle(db, conflict):
    claim = failed_borehole_claim(db, off_slots=0 if conflict == "no_barrier" else 1)
    candidate = dict(claim)
    if conflict in {"active", "completed"}:
        seed(db, "mark_borehole_active" if conflict == "active" else "record_borehole_completed",
            {**claim, "state": "Active" if conflict == "active" else "Completed"})
    elif conflict == "claim_digest": candidate["eligibility_sha256"] = "f"*64
    elif conflict == "consumption": candidate["consumption_key"] = "borehole:"+"f"*64
    called = []
    def read(): called.append(True); return fresh_borehole_off()
    result = abort_borehole(candidate, None if conflict == "reader" else read)
    assert not result["success"] and called == []
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)
    assert not any(row["action"] == "record_borehole_aborted" for row in rows(db, claim))


@pytest.mark.parametrize("field", ["state", "shutdown_verified", "canonical_abort_evidence",
    "provider_final_off_evidence", "abort_read_started_at", "consumption_key", "terminal_contract", "event_id"])
def test_malformed_abort_row_never_clears_inventory_or_admission(db, field, monkeypatch):
    from copy import deepcopy
    import psycopg
    claim = failed_borehole_claim(db, off_slots=1)
    captured = []; insert = store._insert_managed_event
    def capture(cursor, action, body):
        if action == "record_borehole_aborted":
            captured.append(deepcopy(body))
            raise RuntimeError("capture valid candidate before append")
        return insert(cursor, action, body)
    with monkeypatch.context() as patch:
        patch.setattr(store, "_insert_managed_event", capture)
        with pytest.raises(RuntimeError, match="capture valid candidate"):
            abort_borehole(claim)
    terminal = captured[0]
    terminal[field] = None
    # Append a deliberately malformed historical envelope without changing or
    # disabling the real append-only trigger or rewriting an existing event.
    with psycopg.connect(db) as connection:
        connection.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
            values (%s,%s,%s,'record_borehole_aborted',%s::jsonb)""",
            (store._event_id("record_borehole_aborted", claim), claim["execution_id"], store.EVENT_SOURCE,
             json.dumps({"rootline_execution": terminal})))
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)
    next_claim = borehole_start_artifact(datetime.now(timezone.utc))
    seed(db, "record_borehole_eligibility", next_claim)
    assert not store.rootline_irrigation_execution_store("claim_borehole_before_on", next_claim)["created"]
    assert not abort_borehole(claim)["success"]


def test_borehole_abort_exact_duplicate_reads_once_and_mismatched_identity_refuses(db):
    claim = failed_borehole_claim(db, off_slots=1); called = []
    def read(): called.append(True); return fresh_borehole_off()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: abort_borehole(claim, read), range(2)))
    assert all(result["success"] for result in results)
    assert sum(result["created"] for result in results) == 1 and called == [True]
    assert results[0]["execution"] == results[1]["execution"]
    assert not abort_borehole({**claim, "consumption_key": "other"}, read)["success"]
    assert called == [True]
    assert sum(row["action"] == "record_borehole_aborted" for row in rows(db, claim)) == 1


def test_borehole_abort_waits_for_inflight_off_and_then_denies_old_off(db):
    claim = failed_borehole_claim(db); entered = Event(); release = Event(); abort_started = Event(); order = []
    def send():
        assert any(row["action"] == "claim_borehole_off_attempt" for row in rows(db, claim))
        order.append("OFF-enter"); entered.set(); assert release.wait(3)
        order.append("OFF-exit"); return {"accepted_unambiguous": True}
    def read(): order.append("READ"); return fresh_borehole_off()
    def retire(): abort_started.set(); return abort_borehole(claim, read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        stopping = pool.submit(send_borehole_off, claim, send)
        assert entered.wait(3)
        retiring = pool.submit(retire); assert abort_started.wait(3)
        assert not retiring.done()
        release.set()
        assert stopping.result(3)["provider_command_attempted"]
        assert retiring.result(3)["success"]
    assert order == ["OFF-enter", "OFF-exit", "READ"]
    new_claim = failed_borehole_claim(db)
    assert not send_borehole_off(claim, lambda: order.append("late-OFF"), attempt=2)["provider_command_attempted"]
    assert not dispatch(claim, "borehole", lambda: order.append("late-ON"))["accepted_unambiguous"]
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)["execution_id"] == new_claim["execution_id"]
    assert order == ["OFF-enter", "OFF-exit", "READ"]


def test_borehole_recovery_waits_for_inflight_on_before_off_and_abort(db):
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    from tests.test_rootline_borehole_commissioning import BoreholeTransport
    claim = failed_borehole_claim(db, age_seconds=0)
    entered = Event(); release = Event(); recovery_started = Event(); order = []
    def on():
        order.append("ON-enter"); entered.set(); assert release.wait(3)
        order.append("ON-exit"); return {"accepted_unambiguous": True}
    class Transport(BoreholeTransport):
        def set_state(self, **kwargs):
            order.append(kwargs["state"]); return super().set_state(**kwargs)
        def read_output_state(self, **kwargs):
            order.append("READ"); return super().read_output_state(**kwargs)
    def recover():
        recovery_started.set()
        return advance_borehole_execution(eligibility=None, store=store.rootline_irrigation_execution_store,
            transport=Transport(), now=datetime.now(timezone.utc)+timedelta(seconds=31))
    with ThreadPoolExecutor(max_workers=2) as pool:
        starting = pool.submit(dispatch, claim, "borehole", on)
        assert entered.wait(3)
        recovering = pool.submit(recover); assert recovery_started.wait(3)
        assert not recovering.done()
        release.set()
        assert starting.result(3)["accepted_unambiguous"]
        assert recovering.result(3)["status"] == "borehole_start_aborted"
    assert order == ["ON-enter", "ON-exit", "OFF", "READ"]
    assert not store.rootline_irrigation_execution_store("mark_borehole_active",
        {**claim, "state": "Active", "on_attempts": 1})["success"]


def test_retirement_between_off_reservation_and_sender_prevents_late_off(db, monkeypatch):
    claim = failed_borehole_claim(db); real = bounded.connect_bounded_rootline_postgres
    connections = 0; called = []; new_claims = []
    def before_second(**kwargs):
        nonlocal connections
        connections += 1
        if connections == 2:
            assert abort_borehole(claim)["success"]
            new_claims.append(failed_borehole_claim(db))
        return real(**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(bounded, "connect_bounded_rootline_postgres", before_second)
        result = send_borehole_off(claim, lambda: called.append("OFF"))
    assert result["status"] == "borehole_execution_retired" and not result["provider_command_attempted"]
    assert called == []
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)["execution_id"] == new_claims[0]["execution_id"]


def test_off_crash_consumes_slot_and_duplicate_never_replays_sender(db, monkeypatch):
    claim = failed_borehole_claim(db); real = bounded.connect_bounded_rootline_postgres
    connections = 0; called = []
    def fail_second(**kwargs):
        nonlocal connections
        connections += 1
        if connections == 2: raise RuntimeError("synthetic crash after OFF slot commit")
        return real(**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(bounded, "connect_bounded_rootline_postgres", fail_second)
        with pytest.raises(RuntimeError, match="after OFF slot"):
            send_borehole_off(claim, lambda: called.append("OFF"))
    assert not send_borehole_off(claim, lambda: called.append("OFF"))["provider_command_attempted"]
    assert called == []
    assert sum(row["action"] == "claim_borehole_off_attempt" for row in rows(db, claim)) == 1
    assert abort_borehole(claim)["success"]


def test_abort_persistence_failure_keeps_claim_and_attempt_evidence(db, monkeypatch):
    claim = failed_borehole_claim(db, off_slots=1); original = rows(db, claim)
    insert = store._insert_managed_event
    def fail_terminal(cursor, action, body):
        result = insert(cursor, action, body)
        if action == "record_borehole_aborted": raise RuntimeError("synthetic terminal persistence failure")
        return result
    with monkeypatch.context() as patch:
        patch.setattr(store, "_insert_managed_event", fail_terminal)
        with pytest.raises(RuntimeError, match="terminal persistence"):
            abort_borehole(claim)
    assert rows(db, claim) == original
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)
    assert abort_borehole(claim)["success"]


@pytest.mark.parametrize("off_slots", [0, 3])
def test_actual_managed_abort_does_not_restart_same_cycle_or_reuse_old_eligibility(db, off_slots):
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    from tests.test_rootline_borehole_commissioning import BoreholeTransport
    claim = failed_borehole_claim(db, off_slots=off_slots); transport = BoreholeTransport()
    recovery_commands = ["OFF"] if off_slots == 0 else []
    def cycle(artifact):
        return run_rootline_managed_device_cycle(evidence={"borehole_execution": artifact},
            transport=transport, store=store.rootline_irrigation_execution_store,
            environ={"ROOTLINE_BOREHOLE_ENABLED": "true"})
    recovered = cycle(claim)
    assert recovered["status"] == "borehole_start_aborted" and not recovered["success"]
    assert recovered["writes_farm_data"] is True and recovered["hardware_commands"] == len(recovery_commands)
    assert [row["state"] for row in transport.commands] == recovery_commands
    assert cycle(claim)["status"] == "borehole_claim_conflict"
    assert [row["state"] for row in transport.commands] == recovery_commands
    fresh = borehole_start_artifact(datetime.now(timezone.utc))
    assert cycle(fresh)["status"] == "borehole_started"
    assert [row["state"] for row in transport.commands] == recovery_commands+["ON"]
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)["execution_id"] == fresh["execution_id"]


@pytest.mark.parametrize("failure", ["ambiguous", "exception"])
def test_failed_borehole_off_is_bounded_across_restart_then_fresh_read_retires(db, failure):
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    claim = failed_borehole_claim(db); commands = []; verified = [False]
    class Transport:
        def set_state(self, **kwargs):
            assert kwargs["state"] == "OFF"; commands.append(kwargs)
            if failure == "exception": raise RuntimeError("synthetic OFF response loss")
            return {"accepted_unambiguous": False}
        def read_output_state(self, **kwargs):
            assert kwargs == {"device_id": "1002851416", "channel": 1}
            return fresh_borehole_off() if verified[0] else {"authoritative": False, "state": "Unknown"}
    def advance():
        return advance_borehole_execution(eligibility=None, store=store.rootline_irrigation_execution_store,
            transport=Transport(), now=datetime.now(timezone.utc))
    first = advance()
    assert first["status"] == "borehole_shutdown_unverified" and first["hardware_commands"] == 3
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)
    assert advance()["hardware_commands"] == 0
    assert len(commands) == 3 and len({row["idempotency_key"] for row in commands}) == 3
    verified[0] = True
    last = advance()
    assert last["status"] == "borehole_start_aborted" and last["hardware_commands"] == 0
    assert len(commands) == 3
    assert not any(row["action"] == "record_borehole_completed" for row in rows(db, claim))


@pytest.mark.parametrize("aborted", [False, True])
def test_borehole_recovery_does_not_block_independent_bc_and_mixer_admission(db, aborted):
    claim = failed_borehole_claim(db, off_slots=1)
    if aborted: assert abort_borehole(claim)["success"]
    suffix = uuid.uuid4().hex; at = datetime.now(timezone.utc)
    job = "INDEPENDENT-JOB-"+suffix
    seed(db, "record_completed", {"execution_id": "PRIOR-"+suffix, "job_id": job,
        "segment_number": 1, "shutdown_verified": True})
    bc = {"execution_id": "INDEPENDENT-BC-"+suffix, "eligibility_id": "ELIG-"+suffix,
        "eligibility_sha256": "b"*64, "operating_date": at.date().isoformat(),
        "zone_id": "B12345", "job_id": job, "segment_number": 2,
        "consumption_key": "BC-CONSUME-"+suffix, "predecessor_off_rearm_verified": True}
    seed(db, "record_eligibility", bc)
    assert store.rootline_irrigation_execution_store("claim_before_on", bc)["created"]
    mixer = {"execution_id": "INDEPENDENT-MIXER-"+suffix, "consumption_key": "MIX-"+suffix,
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2", "device_type": "fertilizer_mixer",
        "device_id": "100204d497", "channel": 2, "state": "claimed", "claimed_at": at.isoformat(),
        "primary_stop_deadline": (at+timedelta(seconds=600)).isoformat(),
        "maximum_duration_seconds": 600, "on_attempts": 0, "off_attempts": 0}
    assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on", mixer)["created"]
    active = store.rootline_irrigation_execution_store("load_active_borehole", None)
    assert active is None if aborted else active["execution_id"] == claim["execution_id"]


def test_borehole_abort_preserves_old_generation_then_new_claim_uses_current_generation(db, monkeypatch):
    from modules.telemetry import rootline_borehole_commissioning as borehole
    claim = failed_borehole_claim(db, off_slots=1, registry_generation=3)
    def forbidden(**kwargs):
        raise AssertionError("Retirement must not replace the original claim with a current registry record")
    with monkeypatch.context() as patch:
        patch.setattr(borehole, "load_registered_borehole_baseline", forbidden)
        result = abort_borehole(claim)
    assert result["success"] and result["execution"]["registry_generation"] == 3
    fresh = borehole_start_artifact(datetime.now(timezone.utc), registry_generation=4)
    seed(db, "record_borehole_eligibility", fresh)
    assert store.rootline_irrigation_execution_store("claim_borehole_before_on", fresh)["created"]
    assert store.rootline_irrigation_execution_store("load_active_borehole", None)["registry_generation"] == 4


def test_borehole_exact_completed_replay_is_acknowledged_and_changed_terminal_refuses(db):
    from tests.test_rootline_borehole_commissioning import BoreholeTransport, advance_borehole_execution
    at = datetime.now(timezone.utc); artifact = borehole_start_artifact(at)
    seed(db, "record_borehole_eligibility", artifact)
    transport = BoreholeTransport()
    started = advance_borehole_execution(eligibility=artifact, store=store.rootline_irrigation_execution_store,
        transport=transport, now=at)
    assert started["status"] == "borehole_started"
    completed = advance_borehole_execution(eligibility=None, store=store.rootline_irrigation_execution_store,
        transport=transport, now=at+timedelta(seconds=61))["execution"]
    replay = store.rootline_irrigation_execution_store("record_borehole_completed", completed)
    assert replay["success"] and not replay["created"]
    changed = {**completed, "completed_at": (at+timedelta(seconds=62)).isoformat()}
    assert not store.rootline_irrigation_execution_store("record_borehole_completed", changed)["success"]
    assert [row["state"] for row in transport.commands] == ["ON", "OFF"]
    assert sum(row["action"] == "record_borehole_completed" for row in rows(db, artifact)) == 1
    aborted_claim = failed_borehole_claim(db, off_slots=1)
    assert abort_borehole(aborted_claim)["success"]
    assert not store.rootline_irrigation_execution_store("record_borehole_completed",
        {**completed, "execution_id": aborted_claim["execution_id"]})["success"]


def test_actual_transport_abort_retains_exact_fresh_provider_identity(db):
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    claim = failed_borehole_claim(db); requests = []; observations = []
    class Response:
        status = 202
        def getcode(self): return self.status
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, limit): return b'accepted synthetic OFF'
    def http_open(request, timeout):
        assert request.get_method() == "POST" and timeout == 15
        assert "/trigger/borehole_1_off/with/key/synthetic-only" in request.full_url
        assert json.loads(request.data)["value1"] == claim["execution_id"]+":OFF:1"
        requests.append(request); return Response()
    def readback(**kwargs):
        snapshot = {"device_id": "1002851416", "provider_control_calls": 0,
            "current_outputs_authoritative": True, "response_digest": "e"*64,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "channels": [{"channel": 1, "output_state": "OFF"}]}
        observations.append(snapshot); return snapshot
    transport = RootlineIFTTTTransport(token_store=object(),
        environ={"ROOTLINE_IFTTT_MAKER_KEY": "synthetic-only"},
        http_open=http_open, readback=readback)
    result = advance_borehole_execution(eligibility=None, store=store.rootline_irrigation_execution_store,
        transport=transport, now=datetime.now(timezone.utc))
    assert result["status"] == "borehole_start_aborted" and result["hardware_commands"] == 1
    assert len(requests) == len(observations) == 1
    proof = result["execution"]["provider_final_off_evidence"]
    assert proof["device_id"] == "1002851416" and proof["channel"] == 1
    assert proof["retrieved_at"] == observations[0]["retrieved_at"]
    assert proof["evidence_id"] == observations[0]["response_digest"]
