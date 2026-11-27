"""Disposable-only original/candidate inventory qualification; never production."""
import ast,json,uuid,hashlib,statistics,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
from copy import deepcopy
from contextlib import contextmanager
import pytest,psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from modules.telemetry import rootline_irrigation_execution_store as es
from scripts import rootline_accounting_index as index
from tests.test_rootline_registry_read_scope import URL,pg_connect
H=Path(es.__file__).parents[2]
ACTIONS=sorted({'claim_before_on','contain_zone','mark_active','mark_stopping','record_ambiguous_shutdown','record_auxiliary_on_outcome','record_claim_recovery','record_completed','record_execution_not_dispatched','record_on_outcome'})
ORIGINAL=next(n.value for n in ast.walk(ast.parse(Path(es.__file__).read_text())) if isinstance(n,ast.Constant) and isinstance(n.value,str) and "jsonb_typeof(review_json->'rootline_execution')" in n.value and "%s" in n.value and "order by created_at desc,review_event_id desc" in n.value)
PREDICATE="event_source='rootline_irrigation_execution' and (jsonb_typeof(review_json->'rootline_execution') is distinct from 'object' or jsonb_typeof(review_json->'rootline_execution'->'action') is distinct from 'string' or review_json->'rootline_execution'->>'action'=any(ARRAY["+','.join("'"+a+"'" for a in ACTIONS)+"]::text[]))"
CANDIDATE=es._CAMP_INVENTORY_SQL
DDL=index.CAMP_CREATE_SQL.replace("CREATE INDEX CONCURRENTLY", "CREATE INDEX",1)
NOW=datetime(2026,11,27,17,tzinfo=timezone.utc)


def connection():
    c=pg_connect();c.execute("set statement_timeout='3s'");c.execute("set lock_timeout='1s'");c.commit();return c

@pytest.fixture
def db():
    if not URL:pytest.skip('explicit disposable PostgreSQL required')
    schema='rootline_inventory65_'+uuid.uuid4().hex
    with connection() as c:
        c.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
        c.execute(sql.SQL('create table {}.sam_live_stock_conversation_review_events (review_event_id text primary key,event_source text,created_at timestamptz,review_json jsonb)').format(sql.Identifier(schema)))
        c.execute(sql.SQL('create index idx_source64 on {}.sam_live_stock_conversation_review_events(event_source,created_at desc,review_event_id)').format(sql.Identifier(schema)))
    class Database:
        def query(self,q):return q.replace('public.',schema+'.')
        def add(self,rows):
            with connection() as c:
                with c.cursor() as cur:cur.executemany(self.query('insert into public.sam_live_stock_conversation_review_events values(%s,%s,%s,%s)'),[(key,'rootline_irrigation_execution',at,Jsonb(body)) for key,at,body in rows])
        def selected(self,candidate):
            with connection() as c:
                c.execute('set transaction read only')
                return c.execute(self.query(CANDIDATE if candidate else ORIGINAL),None if candidate else (es.EVENT_SOURCE,ACTIONS)).fetchall()
        def reducer(self,candidate):
            database=self
            class Cursor:
                def __init__(self,c):self.c=c
                def __enter__(self):return self
                def __exit__(self,*args):self.c.close()
                def execute(self,q,params=None):
                    assert q==CANDIDATE and params is None
                    self.c.execute(database.query(CANDIDATE if candidate else ORIGINAL),None if candidate else (es.EVENT_SOURCE,ACTIONS))
                def fetchall(self):return self.c.fetchall()
            class Wrapper:
                def __init__(self,c):self.c=c
                def cursor(self):return Cursor(self.c.cursor())
            with connection() as c:
                c.execute('set transaction read only')
                try:return ('value',es._load('load_active',None,connection=Wrapper(c)))
                except Exception as exc:return ('error',type(exc).__name__)
        def index(self):
            with connection() as c:c.execute(self.query(DDL));c.execute(self.query('analyze public.sam_live_stock_conversation_review_events'))
    try:yield Database()
    finally:
        with connection() as c:c.execute(sql.SQL('drop schema {} cascade').format(sql.Identifier(schema)))


def event(identity,action,**kwargs):
    value={'execution_id':identity,'action':action,'device_id':'100204e9bc','channel':1,**kwargs}
    value['event_id']=es._event_id(action,value);return value

def no_send_rows():
    claim=event('no-send','claim_before_on',provider_capacity_permit={'permit':'test'})
    outcome=event('no-send','record_on_outcome',on_outcome={'provider_command_attempted':False,'accepted_unambiguous':False})
    terminal=event('no-send','record_execution_not_dispatched',terminal_contract='rootline_proven_no_send.v1',not_dispatched_verified=True,
        claim_event_id=claim['event_id'],claim_sha256=es._event_digest(claim),outcome_event_id=outcome['event_id'],outcome_sha256=es._event_digest(outcome),
        read_started_at=NOW.isoformat(),retired_at=NOW.isoformat(),shutdown_evidence={'authoritative':True,'state':'OFF','device_id':'100204e9bc','channel':1,'evidence_id':'a'*64,'retrieved_at':NOW.isoformat()})
    assert es._verified_not_dispatched(terminal,[claim,outcome,terminal])
    return [claim,outcome,terminal]

def rows(events):return [(f'{i:05d}',NOW+timedelta(seconds=i),{'rootline_execution':item}) for i,item in enumerate(events)]

@pytest.mark.parametrize('extra',[{}, {'rootline_execution':None},{'rootline_execution':[]},{'rootline_execution':4},{'rootline_execution':False},
    {'rootline_execution':'{"execution_id":"legacy","action":"claim_before_on"}'},{'rootline_execution':'broken'},
    {'rootline_execution':{'action':None}},{'rootline_execution':{'action':True}},{'rootline_execution':{'action':12}},{'rootline_execution':{'action':[]}}])
def test_malformed_exact_rows_and_failure_parity(db,extra):
    db.add(rows([event('old','claim_before_on')])+[('malformed',NOW+timedelta(days=1),extra)])
    db.index()
    assert db.selected(False)==db.selected(True)
    assert db.reducer(False)==db.reducer(True)


def test_real_reducer_old_outstanding_terminal_no_send_and_fresh_insert(db):
    events=[event('old','claim_before_on'),event('closed','claim_before_on'),event('closed','record_completed',shutdown_verified=True,shutdown_evidence={'authoritative':True,'state':'OFF'})]+no_send_rows()
    db.add(rows(events));db.index()
    assert db.selected(False)==db.selected(True)
    a=db.reducer(False);assert a==db.reducer(True) and a[0]=='value' and a[1]['execution_id']=='old',a
    # Fresh later proof closes old obligation; no time cutoff or old-row pruning.
    db.add([('new',NOW+timedelta(days=1),{'rootline_execution':event('old','record_completed',shutdown_verified=True,shutdown_evidence={'authoritative':True,'state':'OFF'})})])
    assert db.reducer(False)==db.reducer(True)==('value',None)
    # Backdated new claim is still visible on a fresh invocation.
    db.add([('backdated',NOW-timedelta(days=30),{'rootline_execution':event('backdated','claim_before_on')})])
    assert db.reducer(True)[1]['execution_id']=='backdated'


def test_invalid_terminal_and_same_timestamp_order_preserved(db):
    db.add([('a',NOW,{'rootline_execution':event('old','claim_before_on')}),('z',NOW,{'rootline_execution':event('old','record_completed',acceptance_mode='command_accepted',shutdown_verified=False)})])
    db.index();assert db.selected(False)==db.selected(True)
    assert db.selected(True)[0][0]['action']=='record_completed'
    assert db.reducer(False)==db.reducer(True)
    assert db.reducer(True)[1]['execution_id']=='old'


def nodes(plan):
    yield plan
    for child in plan.get('Plans',[]):yield from nodes(child)


@pytest.mark.parametrize("other_source_rows",[0,90000])
def test_representative_distribution_custom_generic_plans_and_timings(db,other_source_rows):
    with connection() as c:
        # 30,000 irrelevant execution events; 612 full inventory rows. Payload is synthetic.
        c.execute(db.query("insert into public.sam_live_stock_conversation_review_events select 'noise-'||i,'rootline_irrigation_execution',%s::timestamptz+i*interval '1 second',jsonb_build_object('rootline_execution',jsonb_build_object('action',case when i%%2=0 then 'record_eligibility' else 'record_job_resolution' end,'execution_id','unused-'||i,'detail',repeat(md5(i::text),32))) from generate_series(1,30000) i"),(NOW,))
        c.execute(db.query("insert into public.sam_live_stock_conversation_review_events select 'proof-'||i,'rootline_irrigation_execution',%s::timestamptz+i*interval '1 second',jsonb_build_object('rootline_execution',jsonb_build_object('action','record_on_outcome','execution_id','proof-'||i,'detail',repeat(md5(i::text),32))) from generate_series(1,612) i"),(NOW,))
        for start in range(1,other_source_rows+1,10000):
            c.execute(db.query("insert into public.sam_live_stock_conversation_review_events select 'other-'||i,'unrelated_source',%s::timestamptz+i*interval '1 second',jsonb_build_object('detail',repeat(md5(i::text),32)) from generate_series(%s::integer,%s::integer) i"),(NOW,start,min(start+9999,other_source_rows)))
        c.execute(db.query('analyze public.sam_live_stock_conversation_review_events'))
    before=db.selected(False);assert len(before)==612
    with connection() as c:
        baseline=c.execute('explain (format json) '+db.query(ORIGINAL),(es.EVENT_SOURCE,ACTIONS)).fetchone()[0][0]['Plan']
        original_times=[]
        for _ in range(5):
            t=time.perf_counter();assert c.execute(db.query(ORIGINAL),(es.EVENT_SOURCE,ACTIONS)).fetchall()==before;original_times.append(time.perf_counter()-t)
    db.index();assert db.selected(True)==before
    report={'other_source_rows':other_source_rows,'rows':30612+other_source_rows,'selected':612,'statement_timeout_ms':3000,'baseline_plan':baseline,'original_seconds':original_times,'plans':{},'candidate_seconds':{}}
    with connection() as c:
        c.execute('set transaction read only')
        for mode in ['force_custom_plan','force_generic_plan']:
            c.execute('set local plan_cache_mode='+mode)
            parameterized=db.query(ORIGINAL).replace('%s','$1',1).replace('%s','$2',1)
            c.execute('prepare original_query(text,text[]) as '+parameterized)
            execute_original="execute original_query('rootline_irrigation_execution',ARRAY["+','.join("'"+a+"'" for a in ACTIONS)+"]::text[])"
            original_plan=c.execute('explain (format json) '+execute_original).fetchone()[0][0]['Plan']
            report.setdefault('original_prepared_plans_after_index',{})[mode]=original_plan
            original_prepared_times=[]
            for _ in range(5):
                t=time.perf_counter();assert c.execute(execute_original).fetchall()==before;original_prepared_times.append(time.perf_counter()-t)
            report.setdefault('original_prepared_seconds_after_index',{})[mode]=original_prepared_times
            report.setdefault('original_prepared_index_selected',{})[mode]=any(n.get('Index Name')==index.CAMP_INDEX_NAME for n in nodes(original_plan))
            c.execute('deallocate original_query')
            c.execute('prepare candidate as '+db.query(CANDIDATE))
            plan=c.execute('explain (format json) execute candidate').fetchone()[0][0]['Plan']
            report.setdefault('natural_index_selected',{})[mode]=any(n.get('Index Name')==index.CAMP_INDEX_NAME for n in nodes(plan))
            times=[]
            for _ in range(5):
                t=time.perf_counter();assert c.execute('execute candidate').fetchall()==before;times.append(time.perf_counter()-t)
            report['plans'][mode]=plan;report['candidate_seconds'][mode]=times
            c.execute('deallocate candidate')
        catalog_index=c.execute("select pg_get_indexdef(indexrelid),pg_get_expr(indpred,indrelid),indisvalid,indisready from pg_index where indexrelid=%s::regclass",(db.query('public.'+index.CAMP_INDEX_NAME),)).fetchone()
        assert catalog_index[2:] == (True,True)
        report['index_definition']=catalog_index[0];report['index_predicate']=catalog_index[1]
    report['limitation']='Synthetic local warmed database; excludes TLS/setup/network and does not establish live speed. No timing threshold used.'
    if other_source_rows:
        assert report['natural_index_selected']=={'force_custom_plan':True,'force_generic_plan':True}
        assert report['original_prepared_index_selected']['force_generic_plan'] is False



def test_stopping_off_duty_and_typed_controller_no_send_proof(db):
    claim=event('typed-no-send','claim_before_on',acceptance_mode='command_accepted',claimed_at=NOW.isoformat(),provider_capacity_permit={'permit':'synthetic'})
    proof={'version':'rootline_controller_command.v1','accepted':False,'controller_command_attempted':False,'status':'controller_not_sent',
        'state':'ON','device_id':'100204e9bc','channel':1,'attempt_id':'typed-no-send:ON','issued_at':NOW.isoformat(),
        'consumed_at':NOW.isoformat(),'expires_at':(NOW+timedelta(seconds=30)).isoformat()}
    outcome=event('typed-no-send','record_on_outcome',on_outcome={'provider_command_attempted':False,'accepted_unambiguous':False,'status':'controller_not_sent','controller_response':proof})
    terminal=event('typed-no-send','record_execution_not_dispatched',terminal_contract='rootline_controller_no_send.v1',not_dispatched_verified=True,shutdown_verified=False,
        claim_sha256=es._event_digest(claim),outcome_sha256=es._event_digest(outcome),claim_event_id=claim['event_id'],outcome_event_id=outcome['event_id'])
    assert es._verified_not_dispatched(terminal,[claim,outcome,terminal])
    stopping=event('old-off-duty','mark_stopping',state='Stopping',acceptance_mode='command_accepted')
    unproven=event('old-off-duty','record_completed',acceptance_mode='command_accepted',shutdown_verified=False)
    events=[stopping,unproven,claim,outcome,terminal,event('aux-abort','record_auxiliary_startup_aborted',terminal_contract='rootline_auxiliary_startup_abort.v3')]
    db.add(rows(events));db.index()
    selected=db.selected(False);assert selected==db.selected(True)
    assert not any(row[0].get('action')=='record_auxiliary_startup_aborted' for row in selected)
    assert es._verified_not_dispatched(terminal,[r[0] for r in selected])
    assert db.reducer(False)==db.reducer(True)
    assert db.reducer(True)[1]['execution_id']=='old-off-duty' and db.reducer(True)[1]['state']=='Stopping'


def test_fixed_query_action_set_and_index_predicate_remain_exact():
    import re
    assert es._CAMP_INVENTORY_ACTIONS==frozenset(ACTIONS)
    assert CANDIDATE.split(" where ",1)[1].split(" order by ",1)[0]==PREDICATE
    assert DDL.split(" where ",1)[1]==PREDICATE
    assert "limit" not in CANDIDATE.lower() and "distinct on" not in CANDIDATE.lower()


def test_future_action_set_mismatch_falls_back_to_original_full_query(monkeypatch):
    captured=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query,params=None):captured.append((query,params))
        def fetchall(self):return []
    class Connection:
        def cursor(self):return Cursor()
    monkeypatch.setattr(es,'_CAMP_INVENTORY_ACTIONS',frozenset())
    assert es._load('load_active',None,connection=Connection()) is None
    assert captured==[(ORIGINAL,(es.EVENT_SOURCE,ACTIONS))]


@pytest.mark.parametrize("source", ["rootline_irrigation_execution", "isolated-camp-source"])
def test_fixed_query_requires_exact_source_identity(monkeypatch, source):
    captured=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query,params=None):captured.append((query,params))
        def fetchall(self):return []
    class Connection:
        def cursor(self):return Cursor()
    monkeypatch.setattr(es,'EVENT_SOURCE',source)
    assert es._load('load_active',None,connection=Connection()) is None
    expected=(CANDIDATE,None) if source=='rootline_irrigation_execution' else (ORIGINAL,(source,ACTIONS))
    assert captured==[expected]


def test_custom_source_real_query_does_not_leak_canonical_duty(db,monkeypatch):
    db.add(rows([event('canonical-duty','claim_before_on')]))
    isolated='isolated-'+uuid.uuid4().hex
    with connection() as c:
        c.execute(db.query('insert into public.sam_live_stock_conversation_review_events values(%s,%s,%s,%s)'),
                  ('isolated-row',isolated,NOW,Jsonb({'rootline_execution':event('isolated-duty','claim_before_on')})))
    class Cursor:
        def __init__(self,c):self.c=c
        def __enter__(self):return self
        def __exit__(self,*args):self.c.close()
        def execute(self,q,params=None):self.c.execute(db.query(q),params)
        def fetchall(self):return self.c.fetchall()
    class Wrapper:
        def __init__(self,c):self.c=c
        def cursor(self):return Cursor(self.c.cursor())
    with connection() as c:
        c.execute('set transaction read only')
        assert es._load('load_active',None,connection=Wrapper(c))['execution_id']=='canonical-duty'
        monkeypatch.setattr(es,'EVENT_SOURCE',isolated)
        assert es._load('load_active',None,connection=Wrapper(c))['execution_id']=='isolated-duty'
        monkeypatch.setattr(es,'EVENT_SOURCE',isolated+'-absent')
        assert es._load('load_active',None,connection=Wrapper(c)) is None
