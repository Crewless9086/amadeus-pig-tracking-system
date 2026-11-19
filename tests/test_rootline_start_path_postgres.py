"""Complete native accounting, canonical execution persistence, and recovery on local PostgreSQL.
Planning/weather/authority and HTTP response bodies are synthetic; production
snapshot normalization, quota/fence/audit, claims, outcomes, and retirement run.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json, os
import pytest
import psycopg
from tests.test_rootline_capacity_edge_postgres import RealReserveJourney, URL, isolated
from modules.sales import sam_live_stock_launch_control as sales
from modules.telemetry import rootline_irrigation_execution_store as es
from modules.telemetry import rootline_ewelink_readback as provider_module
NATIVE_BOUND_READ=provider_module._read_bound_device
pytestmark=pytest.mark.skipif(not URL,reason='explicit disposable PostgreSQL URL required')

def native_journey(monkeypatch,extra_seconds=0,change=None):
    from tests.test_rootline_ewelink_readback import Store,env,provider
    from modules.telemetry import rootline_ewelink_oauth as oauth
    from urllib.parse import urlparse
    from copy import deepcopy
    import datetime
    import psycopg
    with psycopg.connect(URL) as connection:
        connection.execute('create schema if not exists app_private')
        connection.execute('create table if not exists app_private.migration_log (migration_id text primary key,description text not null,applied_at timestamptz not null default now())')
        for migration in ('202605210005_create_telemetry_power_tables.sql','202605230001_create_irrigation_tables.sql'):
            connection.execute((Path('supabase/migrations') / migration).read_text())
        connection.execute('truncate public.irrigation_events')
    recorder=sales.record_sam_live_stock_review_event
    j=RealReserveJourney(monkeypatch,sql_seconds=.35,connect_seconds=.8,
        prior_safety_seconds=extra_seconds)
    monkeypatch.setattr(sales,'record_sam_live_stock_review_event',recorder)
    monkeypatch.setenv('DATABASE_URL',URL)
    j.store=es.rootline_irrigation_execution_store
    j.source.update(env(DATABASE_URL=URL))
    if change=='authority_revoked':j.revoke=True
    thing_count=[0];status_count=[0]
    record=Store(j.source).record
    record['access_expires_at']=j.now+datetime.timedelta(hours=1)
    def latest():
        j.spend('token latest',2)
        return record
    j.tokens.latest=latest
    monkeypatch.setattr(provider_module,'_read_bound_device',NATIVE_BOUND_READ)
    monkeypatch.setattr(provider_module,'datetime',datetime.datetime)
    request,_=provider()
    class Response:
        def __init__(self,url,packet):self.url,self.packet=url,packet
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def geturl(self):return self.url
        def read(self,*a):return json.dumps({'error':0,'data':self.packet}).encode()
    class Opener:
        def open(self,req,timeout):
            path=urlparse(req.full_url).path
            packet=deepcopy(request(req.method,req.full_url))
            j.spend('provider GET '+path,1)
            if path=='/v2/device/thing':
                thing_count[0]+=1
                d=packet['thingList'][0]['itemData'];d['extra']={'uiid':4};d['updatedAt']=j.now.isoformat()
                if thing_count[0]==2 and change=='account':d['apikey']='wrong-account'
                if thing_count[0]==2 and change=='class':d['extra']['uiid']=138
            if path=='/v2/device/thing/status':
                status_count[0]+=1
                on=(j.output=='ON' or (status_count[0]==2 and change=='final_ON'))
                packet={'params':{'switches':[{'outlet':i,'switch':('on' if i==0 and on else 'off')} for i in range(4)]}}
            return Response(req.full_url,packet)
    monkeypatch.setattr(oauth.urllib.request,'build_opener',lambda *a:Opener())
    value,status=j.gateway()
    return j,value,status

@pytest.mark.parametrize('extra_seconds',[0,20])
def test_full_native_start_keeps_original_deadline_with_latency_margin(monkeypatch,extra_seconds):
    j,value,status=native_journey(monkeypatch,extra_seconds)
    assert j.controls and j.controls[0]['status']=='segment_started',value
    assert [c['state'] for c in j.calls]==['ON']
    on_at=next(t for kind,t,_ in j.events if kind=='HTTP ON')
    assert on_at==pytest.approx(107.9+extra_seconds) and on_at<140
    assert j.borehole_checks==1
    assert sum(kind=='provider GET /v2/device/thing/status' for kind,_,_ in j.events)==3
    assert not any(kind=='provider GET /v2/family' for kind,_,_ in j.events)
    assert len(j.sql_trace)==105
    with psycopg.connect(URL) as c:
        ledger=[r[0] for r in c.execute("select review_json->'ewelink_request_budget' from public.sam_live_stock_conversation_review_events where event_source='rootline_provider_availability'")]
        execution=[r[0] for r in c.execute("select review_json->'rootline_execution' from public.sam_live_stock_conversation_review_events where event_source=%s",(es.EVENT_SOURCE,))]
    assert sum(r['action']=='claim_before_on' for r in execution)==1
    assert sum(r['action']=='mark_active' for r in execution)==1
    reserve=next(r for r in ledger if r['action']=='active_duty_reserved')['state']['reserves']
    entry=next(iter(reserve.values()))
    assert (datetime.fromisoformat(entry['admit_until'])-datetime.fromisoformat(entry['reserved_at'])).total_seconds()==30


def test_slower_native_start_defers_without_on_or_deadline_extension(monkeypatch):
    j,value,status=native_journey(monkeypatch,40)
    assert not any(c['state']=='ON' for c in j.calls),value
    assert j.controls[0]['status']=='execution_cycle_deadline_deferred'

from tests import test_rootline_no_send_preparation_postgres as prepared_fixture
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_execution_store as executions
from modules.telemetry import rootline_ewelink_readback as readback
from modules.telemetry import rootline_cycle_budget as cycle
from modules.oom_sakkie import bounded_postgres_read as bounded


@pytest.mark.parametrize('fault',[None,'late_status','contradictory_outcome'])
def test_native_stop_only_retires_nine_row_unsent_claim(monkeypatch,fault):
    monkeypatch.setattr(prepared_fixture,'DATABASE_URL',URL)
    monkeypatch.setenv('DATABASE_URL',URL)
    with psycopg.connect(URL) as connection:
        connection.execute('create schema if not exists app_private')
        connection.execute('create table if not exists app_private.migration_log (migration_id text primary key,description text not null,applied_at timestamptz not null default now())')
        for name in ('202608060001_create_rootline_ewelink_oauth_vault.sql','202608130001_serialize_rootline_ewelink_refresh.sql'):
            connection.execute((Path('supabase/migrations')/name).read_text(encoding='utf-8'))
        connection.execute('truncate app_private.rootline_ewelink_oauth_tokens')
        connection.execute('truncate app_private.rootline_ewelink_account_binding')
    subject=prepared_fixture.FamilySubject(monkeypatch,'irrigation')
    from tests.test_rootline_execution_authority import inputs
    from modules.telemetry.rootline_execution_authority import build_execution_eligibility
    from modules.telemetry.rootline_timed_control import timed_control_scope
    def fresh_artifact(at):
        plan,evidence,controller=inputs(weather_at=at,water_at=at)
        day=at.astimezone(runtime.ZA_TZ).date().isoformat()
        plan['operating_date']=day
        evidence['irrigation'].update(advisor_generated_at=at.isoformat(),advisor_operating_date=day)
        controller.update(current_outputs_authoritative=True,retrieved_at=at.isoformat(),
            trusted_receipt_at=at.isoformat(),response_digest='READ-'+at.isoformat())
        with timed_control_scope({'ROOTLINE_TIMED_CONTROL_ENABLED':'true'}):
            artifact=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=at,
                job_event_reader=lambda job:executions.rootline_irrigation_execution_store('load_job_events',job),
                zone_containment_reader=lambda zone:executions.rootline_irrigation_execution_store('load_zone_containment',zone))
        assert artifact['eligible'],artifact
        return artifact
    def claim_for(artifact,at):
        return {**artifact,'device_id':'100204e9bc','device_type':'irrigation_zone_valve',
            'segment_number':artifact['current_segment'],'state':'claimed','on_attempts':0,'off_attempts':0,
            'claimed_at':at.isoformat(),'planned_runtime_seconds':artifact['maximum_duration_seconds'],
            'planned_runtime_minutes':artifact['maximum_duration_seconds']//60,
            'primary_stop_deadline':(at+timedelta(seconds=artifact['maximum_duration_seconds'])).isoformat(),
            'native_fail_stop_deadline':None}
    with psycopg.connect(URL) as connection:
        connection.execute('truncate public.sam_live_stock_conversation_review_events')
        for name in ('202605210005_create_telemetry_power_tables.sql','202605230001_create_irrigation_tables.sql'):
            connection.execute((Path('supabase/migrations')/name).read_text(encoding='utf-8'))
        connection.execute('truncate public.irrigation_events')
    initial_at=datetime.now(timezone.utc)
    artifact=fresh_artifact(initial_at)
    subject.claim=claim_for(artifact,initial_at)
    subject.claim['provider_capacity_permit']=subject.client.reserve_for_on(
        execution_id=artifact['execution_id'],device_id='100204e9bc',channel=1,
        device_type='irrigation_zone_valve',region='eu')
    subject.client.begin_on(execution_id=artifact['execution_id'],permit=subject.claim['provider_capacity_permit'],
        device_id='100204e9bc',channel=1,claimed_at=subject.claim['claimed_at'],
        primary_stop_deadline=subject.claim['primary_stop_deadline'])
    # Same nine-action predecessor shape: no ON, three exhausted protective OFFs.
    with psycopg.connect(URL) as connection,connection.cursor() as cursor:
        executions._insert_managed_event(cursor,'record_eligibility',artifact)
        executions._insert_managed_event(cursor,'claim_before_on',subject.claim)
        executions._insert_managed_event(cursor,'record_on_outcome',{**subject.claim,'on_outcome':subject.outcome['on_outcome']})
        for attempt in (1,2,3):
            executions._insert_managed_event(cursor,'claim_off_attempt',{'execution_id':subject.claim['execution_id'],'attempt':attempt})
            executions._insert_managed_event(cursor,'record_off_outcome',{'execution_id':subject.claim['execution_id'],'attempt':attempt,'off_outcome':{'accepted_unambiguous':True}})
    # FamilySubject uses the legacy observed UIID for this no-send-only path.
    elapsed=[0.0]; events=[]; start=datetime.now(timezone.utc)
    class ClockType(type):
        def __instancecheck__(cls,value):return isinstance(value,datetime)
    class Clock(datetime,metaclass=ClockType):
        @classmethod
        def now(cls,tz=None):
            value=start+timedelta(seconds=elapsed[0])
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)
    def spend(kind,seconds):
        events.append((kind,elapsed[0],seconds));elapsed[0]+=seconds
    monkeypatch.setattr(cycle.time,'monotonic',lambda:elapsed[0])
    monkeypatch.setattr(readback,'datetime',Clock)
    monkeypatch.setattr(executions,'datetime',Clock)
    original_connect=bounded.connect_bounded_rootline_postgres
    def connect(**kwargs):
        assert kwargs['database_url']==URL
        spend('connection',.8)
        return original_connect(**kwargs)
    monkeypatch.setattr(bounded,'connect_bounded_rootline_postgres',connect)
    original_execute=bounded._CycleBudgetCursor._execute_measured
    def execute(self,statement,*args,**kwargs):
        self._timing_statement=str(statement)
        spend('SQL '+str(statement).splitlines()[0],.35)
        return original_execute(self,statement,*args,**kwargs)
    monkeypatch.setattr(bounded._CycleBudgetCursor,'_execute_measured',execute)
    original_fetch=bounded._CycleBudgetCursor.fetchone
    def fetch(self):
        row=original_fetch(self)
        if row and 'clock_timestamp()' in self.__dict__.get('_timing_statement','').lower():
            return tuple(Clock.now(timezone.utc) if isinstance(v,datetime) else v for v in row)
        return row
    monkeypatch.setattr(bounded._CycleBudgetCursor,'fetchone',fetch)
    for path in ('/v2/family','/v2/device/thing','/v2/device/thing/status'):
        subject.hooks[path]=lambda path=path:spend('HTTP '+path,1)
    if fault:
        def status_hook():
            spend('HTTP /v2/device/thing/status',10 if fault=='late_status' else 1)
            if fault=='contradictory_outcome':
                with psycopg.connect(URL) as connection,connection.cursor() as cursor:
                    executions._insert_managed_event(cursor,'record_on_outcome',
                        {**subject.claim,'on_outcome':{'accepted_unambiguous':True,'status':'accepted'}})
        subject.hooks['/v2/device/thing/status']=status_hook
    with cycle.cycle_budget(deadline=140):
        result=runtime.supervise_rootline_active_execution(notify=lambda *a:{'success':True},
            environ=subject.source,transport=subject.transport,owner_user_id='42',chat_id='42',
            now=start,clock=lambda:Clock.now(timezone.utc))
    rows=subject.rows()
    output={'result':result,'events':events,'calls':subject.calls,'rows':rows,'elapsed':elapsed[0]}
    target=os.getenv('ROOTLINE_NO_SEND_RESULT')
    if target:Path(target).write_text(json.dumps(output,default=str,indent=2),encoding='utf-8')
    if fault:
        assert result['status']!='execution_not_dispatched',output
        assert not any(row['action']=='record_execution_not_dispatched' for row in rows)
        assert result['hardware_commands']==0
        return
    assert result['status']=='execution_not_dispatched',output
    terminal=[row for row in rows if row['action']=='record_execution_not_dispatched']
    assert len(terminal)==1 and executions._verified_not_dispatched(terminal[0],rows)
    assert subject.calls==['/v2/family','/v2/device/thing','/v2/device/thing/status']
    assert result['hardware_commands']==0

    assert executions.rootline_irrigation_execution_store('load_active',None) is None
    assert executions.rootline_irrigation_execution_store('load_job_events',artifact['job_id']) == []
    before_calls=list(subject.calls)
    replay=runtime.supervise_rootline_active_execution(notify=lambda *a:pytest.fail('unexpected replay notice'),
        environ=subject.source,transport=subject.transport,owner_user_id='42',chat_id='42',
        now=Clock.now(timezone.utc),clock=lambda:Clock.now(timezone.utc))
    assert replay['status']=='no_active_irrigation' and subject.calls==before_calls
    with cycle.cycle_budget(deadline=elapsed[0]+140):
        next_artifact=fresh_artifact(Clock.now(timezone.utc))
        assert next_artifact['execution_id'] != artifact['execution_id']
        for key in ('job_id','segment_identity','consumption_key'):
            assert next_artifact[key]==artifact[key]
        assert executions.rootline_irrigation_execution_store('record_eligibility',next_artifact)['success']
        next_claim=claim_for(next_artifact,Clock.now(timezone.utc))
        assert executions._scheduled_irrigation_claim_valid(next_claim,next_artifact,Clock.now(timezone.utc)),(next_claim,next_artifact,Clock.now(timezone.utc))
        claimed=executions.rootline_irrigation_execution_store('claim_before_on',next_claim)
        assert claimed['created'] is True,claimed
        assert executions.rootline_irrigation_execution_store('claim_before_on',next_claim)['created'] is False
        assert subject.calls==before_calls # Fresh claim proof does not replay the old ON.

    if target:
        output['continuation']={'replay_status':replay['status'],'fresh_claim':claimed,'same_job':True,'same_consumption':True,'old_on_replayed':False}
        Path(target).write_text(json.dumps(output,default=str,indent=2),encoding='utf-8')

@pytest.mark.parametrize('action',['active_duty_reserved','active_duty_on_attempt_reserved',
    'request_attempt_reserved','request_completed'])
def test_every_audit_action_uses_exact_receipt_and_independent_commit(monkeypatch,action):
    from modules.telemetry import rootline_ewelink_request_budget as budget
    original=sales.record_sam_live_stock_review_event
    observed=[]
    def record(event,**kwargs):
        assert kwargs.get('durable_receipt') is True and 'created_at' not in kwargs
        value,status=original(event,**kwargs)
        with psycopg.connect(URL) as observer:
            assert observer.execute('select count(*) from public.sam_live_stock_conversation_review_events where review_event_id=%s',
                (event['review_event_id'],)).fetchone()[0]==0
        observed.append(value['persisted_receipt'])
        return value,status
    monkeypatch.setattr(sales,'record_sam_live_stock_review_event',record)
    client=budget.RequestBudget({'DATABASE_URL':URL,'EWELINK_CLIENT_ID':'offline-receipt-app'})
    client._append({'version':1,'reserves':{}},action=action,attempt_units=1)
    with psycopg.connect(URL) as observer:
        row=observer.execute('select review_event_id,review_json,created_at from public.sam_live_stock_conversation_review_events').fetchone()
    assert row[0]==observed[0]['review_event_id'] and row[1]==observed[0]['review_json']
    assert row[2].tzinfo is not None


@pytest.mark.parametrize('fault',['receipt_id','receipt_payload','rollback','lost_commit_ack'])
def test_audit_failure_never_reports_acknowledged_success(monkeypatch,fault):
    from modules.telemetry import rootline_ewelink_request_budget as budget
    original=sales.record_sam_live_stock_review_event
    def record(event,**kwargs):
        value,status=original(event,**kwargs)
        if fault.startswith('receipt_'):
            receipt=dict(value['persisted_receipt'])
            receipt['review_event_id' if fault=='receipt_id' else 'review_json']='wrong'
            value={**value,'persisted_receipt':receipt}
        return value,status
    monkeypatch.setattr(sales,'record_sam_live_stock_review_event',record)
    class Connection:
        def __init__(self):self.inner=psycopg.connect(URL)
        def __getattr__(self,key):return getattr(self.inner,key)
        def __enter__(self):self.inner.__enter__();return self
        def __exit__(self,kind,value,tb):
            if kind is None and fault=='rollback':
                self.inner.__exit__(RuntimeError,RuntimeError('offline rollback'),None)
                raise psycopg.OperationalError('offline commit failure')
            result=self.inner.__exit__(kind,value,tb)
            if kind is None and fault=='lost_commit_ack':
                raise psycopg.OperationalError('offline lost acknowledgement')
            return result
    client=budget.RequestBudget({'DATABASE_URL':URL,'EWELINK_CLIENT_ID':'offline-receipt-app'},connect_factory=Connection)
    error=budget.RequestBudgetUnavailable if fault.startswith('receipt_') else psycopg.OperationalError
    with pytest.raises(error):client._append({'version':1,'reserves':{}},action='request_attempt_reserved',attempt_units=1)
    with psycopg.connect(URL) as observer:
        count=observer.execute('select count(*) from public.sam_live_stock_conversation_review_events').fetchone()[0]
    assert count==(1 if fault=='lost_commit_ack' else 0)


def test_conflicting_audit_identity_cannot_masquerade_as_a_durable_receipt(monkeypatch):
    from modules.telemetry import rootline_ewelink_request_budget as budget
    class Identity:hex='offline-fixed-identity'
    monkeypatch.setattr(budget.uuid,'uuid4',lambda:Identity())
    client=budget.RequestBudget({'DATABASE_URL':URL,'EWELINK_CLIENT_ID':'offline-receipt-app'})
    client._append({'version':1,'reserves':{}},action='request_attempt_reserved',attempt_units=1)
    with pytest.raises(budget.RequestBudgetUnavailable,match='accounting_unavailable'):
        client._append({'version':1,'reserves':{'changed':True}},action='request_attempt_reserved',attempt_units=1)
    with psycopg.connect(URL) as observer:
        assert observer.execute('select count(*) from public.sam_live_stock_conversation_review_events').fetchone()[0]==1


@pytest.mark.parametrize('change',['account','class','final_ON','authority_revoked'])
def test_fresh_native_final_snapshot_and_authority_still_refuse_changed_inputs(monkeypatch,change):
    j,value,status=native_journey(monkeypatch,change=change)
    assert not any(c['state']=='ON' for c in j.calls),value
    with psycopg.connect(URL) as c:
        assert c.execute("select count(*) from public.sam_live_stock_conversation_review_events where review_json->'rootline_execution'->>'action'='claim_before_on'").fetchone()[0]==0
