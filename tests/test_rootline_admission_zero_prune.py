"""Exact zero-charge pruning preserves the original admission query contract."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import ast,hashlib,os,uuid
import pytest
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.oom_sakkie.bounded_postgres_read import _ROOTLINE_PRIVATE_SQL_SHA256
ORIGINAL="with stamp as materialized (select clock_timestamp() as at),\n            latest as (select review_json->'ewelink_request_budget' as body\n                from public.sam_live_stock_conversation_review_events\n                where chatwoot_conversation_id=%s and event_source=%s\n                order by created_at desc,review_event_id desc limit 1),\n            counts as (select\n                coalesce(sum(case when cast(%s as text) is null or\n                    (review_json #>> '{ewelink_request_budget,detail,scope}'=%s and\n                     review_json #>> '{ewelink_request_budget,detail,region}'=%s)\n                    then (review_json #>> '{ewelink_request_budget,attempt_units}')::int else 0 end),0) as rolling,\n                coalesce(sum(case when created_at >= stamp.at-interval '5 minutes' then\n                    (review_json #>> '{ewelink_request_budget,attempt_units}')::int else 0 end),0) as recent\n                from public.sam_live_stock_conversation_review_events cross join stamp\n                where chatwoot_conversation_id=%s and event_source=%s\n                    and created_at >= stamp.at-(%s * interval '1 day'))\n            select latest.body,stamp.at,counts.rolling,counts.recent,exists(select 1 from latest)\n            from stamp cross join counts left join latest on true"
PREDICATE='\n                    and (review_json #>> \'{ewelink_request_budget,attempt_units}\') collate "C" is distinct from \'0\''
OLD_SHA='cf3bc81090d2ac5b8ef6331e63e26a043634315eb4bcba9c0ce44dcd55deab0b'
NEW_SHA='5e1d85a6a46efffe1c661e91a7b0d2c5fb2a26b9383c087528ff889c323a032b'

def current_sql():
    method=next(n for n in ast.walk(ast.parse(Path(budget.__file__).read_text())) if isinstance(n,ast.FunctionDef) and n.name=='_admission_preimage')
    return next(n.value for n in ast.walk(method) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('with stamp'))

def test_only_count_scan_exact_c_zero_predicate_and_private_fingerprint_change():
    assert hashlib.sha256(ORIGINAL.encode()).hexdigest()==OLD_SHA
    assert current_sql()==ORIGINAL.replace("and created_at >= stamp.at-(%s * interval '1 day')", "and created_at >= stamp.at-(%s * interval '1 day')"+PREDICATE)
    assert NEW_SHA in _ROOTLINE_PRIVATE_SQL_SHA256 and OLD_SHA not in _ROOTLINE_PRIVATE_SQL_SHA256

URL=os.getenv('ROOTLINE_DISPOSABLE_POSTGRES_URL','')
@pytest.fixture
def pg():
    if not URL:pytest.skip('explicit disposable local PostgreSQL required')
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    info=conninfo_to_dict(URL)
    assert info['host']=='127.0.0.1' and info['port']=='56437' and info['dbname']=='rootline_accounting_followup_20261116'
    with psycopg.connect(URL) as connection:
        with connection.transaction(force_rollback=True):
            connection.execute("set local statement_timeout='3000ms'")
            yield connection

AT=datetime(2026,11,16,12,tzinfo=timezone.utc)
def seed(connection,rows):
    from psycopg.types.json import Jsonb
    identity='SYNTHETIC-SEMANTICS-'+uuid.uuid4().hex
    for index,(age,body) in enumerate(rows):
        connection.execute('insert into public.sam_live_stock_conversation_review_events (review_event_id,chatwoot_conversation_id,event_source,created_at,review_json) values(%s,%s,%s,%s,%s)',
            (identity+'-'+str(index),identity,identity,AT-age,Jsonb({'ewelink_request_budget':body})))
    return identity

def observed(connection,sql,identity,scope='s1',region='eu'):
    import psycopg
    fixed=sql.replace('clock_timestamp() as at','%s::timestamptz as at')
    try:
        with connection.transaction():
            row=connection.execute(fixed,(AT,identity,identity,scope,scope,region,identity,identity,31)).fetchone()
        return ('ok',row)
    except psycopg.Error as exc:return ('error',exc.sqlstate)

def body(units,scope='s1',region='eu'):
    return {'attempt_units':units,'detail':{'scope':scope,'region':region},'state':{'version':1,'reserves':{},'scopes':{}}}

@pytest.mark.parametrize('units',[0,'0',0.0,'0.0','00',' 0','-0',-2,None,'bad','０','٠',True,{},[],2147483648])
@pytest.mark.parametrize('age,scope',[(timedelta(minutes=1),'s2'),(timedelta(hours=1),'s2'),(timedelta(hours=1),'s1')])
def test_units_cast_errors_and_scoped_case_short_circuit_unchanged(pg,units,age,scope):
    identity=seed(pg,[(age,body(units,scope))])
    old=observed(pg,ORIGINAL,identity);new=observed(pg,current_sql(),identity)
    assert old==new
    if units=='bad' and scope=='s2' and age==timedelta(hours=1):assert old[0]=='ok'
    if units in ('０','٠') and (scope=='s1' or age<timedelta(minutes=5)):assert old==('error','22P02')

@pytest.mark.parametrize('payload',[None,{},[],True,'scalar',{'detail':None},{'detail':[]},{'attempt_units':None},{'attempt_units':0,'detail':'scalar'}])
def test_missing_null_scalar_budget_and_detail_unchanged(pg,payload):
    identity=seed(pg,[(timedelta(minutes=1),payload)])
    assert observed(pg,ORIGINAL,identity)==observed(pg,current_sql(),identity)

@pytest.mark.parametrize('zone',['UTC','America/New_York'])
@pytest.mark.parametrize('scope,region',[('s1','eu'),(None,'eu'),('s1',None)])
def test_cutoff_equality_negative_units_and_latest_zero_state_preserved(pg,zone,scope,region):
    pg.execute("select set_config('TimeZone',%s,true)",(zone,))
    rows=[(timedelta(days=31),body(7)),(timedelta(days=31,microseconds=1),body(99)),
        (timedelta(minutes=5),body(3)),(timedelta(minutes=5,microseconds=1),body(-2)),
        (timedelta(minutes=1),body(5,'s2')),(timedelta(seconds=0),{**body(0),'latest_marker':'zero-row-still-latest'})]
    identity=seed(pg,rows);old=observed(pg,ORIGINAL,identity,scope,region);new=observed(pg,current_sql(),identity,scope,region)
    assert old==new and new[0]=='ok'
    assert new[1][0]['latest_marker']=='zero-row-still-latest'

def test_empty_ledger_unchanged(pg):
    identity='empty-'+uuid.uuid4().hex
    assert observed(pg,ORIGINAL,identity)==observed(pg,current_sql(),identity)
