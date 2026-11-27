"""Exact additive camp index lifecycle on the existing migration rail."""
from copy import deepcopy
from pathlib import Path
import hashlib,re
import pytest
from psycopg.pq import TransactionStatus
from scripts import rootline_accounting_index as index,run_render_production_migrations as rail
from tests.test_rootline_restoration_index_migration import IndexConnection
from tests.test_rootline_camp_inventory_index import db,connection

ITEM=next(item for item in rail.ALLOWLIST if item.migration_id==index.CAMP_MIGRATION_ID)
PREFIX=rail.ALLOWLIST[:rail.ALLOWLIST.index(ITEM)]


def test_closed_registration_verification_only_sql_and_existing_runner():
    assert len(PREFIX)==12 and PREFIX[-1].migration_id==index.RESTORATION_MIGRATION_ID
    assert ITEM.migration_id not in (*rail.BASELINE_ELIGIBLE_IDS,*rail.LEGACY_ADOPTION_RECEIPT_IDS)
    text=rail._load_sql(ITEM)
    assert hashlib.sha256(text.encode()).hexdigest()==ITEM.sha256
    assert index.CAMP_EXPECTED_DEFINITION.replace("'","''") in text
    assert index.CAMP_DESCRIPTION in text
    stripped=re.sub(r"'(?:''|[^'])*'","''",text)
    assert 'CREATE INDEX' not in stripped and 'DROP ' not in stripped
    assert all(flag in text for flag in ('indisvalid','indisready','indislive'))
    from scripts.apply_supabase_migration import prepare_index
    assert prepare_index is index.prepare_index

@pytest.mark.parametrize('position,value',[(0,'r'),(1,'wrong'),(2,False),(3,False),(4,False)])
def test_wrong_or_invalid_existing_object_never_rebuilt(position,value):
    c=IndexConnection(index.CAMP_MIGRATION_ID,existing=True)
    row=list(c.row);row[position]=value;c.row=tuple(row)
    with pytest.raises(RuntimeError,match='definition_or_state_mismatch'):index.prepare_index(c,index.CAMP_MIGRATION_ID)
    assert not any(query==c.create or 'DROP ' in query for query,_ in c.calls)


def test_concurrent_prepare_once_restore_timeouts_and_failed_build_no_retry():
    c=IndexConnection(index.CAMP_MIGRATION_ID)
    assert index.prepare_index(c,index.CAMP_MIGRATION_ID)=='created_exact_valid'
    assert index.prepare_index(c,index.CAMP_MIGRATION_ID)=='existing_exact_valid'
    assert sum(query==c.create for query,_ in c.calls)==1
    assert c.settings=={'statement_timeout':300000,'lock_timeout':60000}
    failed=IndexConnection(index.CAMP_MIGRATION_ID);failed.fail_build=True
    with pytest.raises(RuntimeError,match='synthetic_build_failure'):index.prepare_index(failed,index.CAMP_MIGRATION_ID)
    assert failed.settings=={'statement_timeout':300000,'lock_timeout':60000}
    assert sum(query==failed.create for query,_ in failed.calls)==1
    assert not any('DROP ' in query for query,_ in failed.calls)

@pytest.mark.parametrize('autocommit,status',[(False,TransactionStatus.IDLE),(True,TransactionStatus.INTRANS)])
def test_owned_transaction_never_committed(autocommit,status):
    c=IndexConnection(index.CAMP_MIGRATION_ID);c.autocommit=autocommit;c.info.transaction_status=status
    with pytest.raises(RuntimeError,match='requires_idle_autocommit'):index.prepare_index(c,index.CAMP_MIGRATION_ID)
    assert c.calls==[]

@pytest.mark.parametrize('bad',[None,'definition','duplicate','invalid','unique','not_live'])
def test_only_exact_valid_prepared_addition_subtracted_from_previous_checkpoint(bad):
    c=IndexConnection(index.CAMP_MIGRATION_ID,existing=True)
    row=['public','sam_live_stock_conversation_review_events',index.CAMP_INDEX_NAME,False,False,True,True,index.CAMP_EXPECTED_DEFINITION]
    if bad=='definition':row[-1]='wrong'
    if bad=='invalid':row[5]=False
    if bad=='unique':row[3]=True
    if bad=='not_live':c.row=(*c.row[:4],False)
    other=['public','unrelated_table','unrelated_index',False,False,True,True,'unrelated definition']
    manifest={'columns':['unchanged'],'indexes':[other,row,row] if bad=='duplicate' else [other,row]};before=deepcopy(manifest)
    if bad:
        with pytest.raises(RuntimeError):rail._prior_catalog_without_prepared_restoration(c,manifest,migration_id=index.CAMP_MIGRATION_ID)
    else:
        assert rail._prior_catalog_without_prepared_restoration(c,manifest,migration_id=index.CAMP_MIGRATION_ID)=={'columns':['unchanged'],'indexes':[other]}
    assert manifest==before


def test_real_concurrent_build_exact_catalog_rollback_and_verification_only_migration(db,monkeypatch):
    # All names redirected into this test's unique owned schema, never public state.
    native_contracts=index._contracts
    mapped=tuple((name,db.query(definition),db.query(create),error) for name,definition,create,error in native_contracts(index.CAMP_MIGRATION_ID))
    monkeypatch.setattr(index,'_contracts',lambda identity:mapped if identity==index.CAMP_MIGRATION_ID else native_contracts(identity))
    schema=db.query('public.').rstrip('.')
    class Scoped:
        def __init__(self,c):self.c=c
        @property
        def autocommit(self):return self.c.autocommit
        @property
        def info(self):return self.c.info
        def execute(self,query,params=None):return self.c.execute(query.replace("n.nspname='public'","n.nspname='"+schema+"'"),params)
    with connection() as c:
        c.autocommit=True
        assert index.prepare_index(Scoped(c),index.CAMP_MIGRATION_ID)=='created_exact_valid'
        assert index.prepare_index(Scoped(c),index.CAMP_MIGRATION_ID)=='existing_exact_valid'
        actual=c.execute('select pg_get_indexdef(%s::regclass)',(schema+'.'+index.CAMP_INDEX_NAME,)).fetchone()[0]
        assert actual==mapped[0][1]
        assert c.execute("show statement_timeout").fetchone()[0]=='3s'
        c.execute('create table '+schema+'.migration_log(migration_id text primary key,description text)')
    migration=db.query(rail._load_sql(ITEM)).replace('app_private.migration_log',schema+'.migration_log')
    class Rollback(Exception):pass
    with connection() as c:
        with pytest.raises(Rollback):
            with c.transaction():c.execute(migration);raise Rollback()
        assert c.execute('select count(*) from '+schema+'.migration_log').fetchone()[0]==0
        assert index.verify_index(Scoped(c),migration_id=index.CAMP_MIGRATION_ID)
        c.execute(migration);c.execute(migration)
        assert c.execute('select migration_id,description from '+schema+'.migration_log').fetchall()==[(index.CAMP_MIGRATION_ID,index.CAMP_DESCRIPTION)]
    # Wrong existing same-name index is not repaired or logged.
    with connection() as c:
        c.execute('drop index '+schema+'.'+index.CAMP_INDEX_NAME)
        c.execute('create index '+index.CAMP_INDEX_NAME+' on '+schema+'.sam_live_stock_conversation_review_events(created_at)')
    with connection() as c:
        c.autocommit=True
        with pytest.raises(RuntimeError,match='definition_or_state_mismatch'):index.prepare_index(Scoped(c),index.CAMP_MIGRATION_ID)
        assert c.execute('select pg_get_indexdef(%s::regclass)',(schema+'.'+index.CAMP_INDEX_NAME,)).fetchone()[0]!=mapped[0][1]


from unittest.mock import patch
from tests.test_rootline_restoration_index_migration import ready_restoration,accounting_ready,predecessor,purpose_predecessor
from tests import test_rootline_accounting_index_migration as accounting
from tests import test_render_production_migration_rail as legacy

@pytest.fixture
def ready_camp(ready_restoration):
    with patch.object(rail,'ALLOWLIST',PREFIX):rail.run(legacy.DATABASE_URL,legacy.ENV)
    return True


def test_real_complete_rail_receipt_replay_and_historical_rows_preserved(ready_camp):
    with accounting.connect() as c:before=accounting.state(c)
    first=rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert first['camp_inventory_index_preparation']=='created_exact_valid'
    with accounting.connect() as c:
        assert index.verify_index(c,migration_id=ITEM.migration_id)
        after=accounting.state(c);assert before[3]==after[3]
        assert rail._verify_migration_log(c,ITEM.migration_id,required=True)==index.CAMP_DESCRIPTION
    second=rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert second['camp_inventory_index_preparation']=='existing_exact_valid'
    assert second['migrations'][-1]['receipt_id']==first['migrations'][-1]['receipt_id']
    with accounting.connect() as c:assert accounting.state(c)==after


def test_real_checkpoint_transaction_rollback_retains_only_prepared_index(ready_camp):
    with accounting.connect() as c:before=accounting.state(c)
    original=rail._verify_migration_readback
    def fail(c,item):
        if item.migration_id==ITEM.migration_id:raise RuntimeError('synthetic_after_prepared_camp')
        return original(c,item)
    with patch.object(rail,'_verify_migration_readback',fail):
        with pytest.raises(RuntimeError,match='migration_transaction_failed_and_rolled_back:.*camp_inventory_index_may_persist'):rail.run(legacy.DATABASE_URL,legacy.ENV)
    with accounting.connect() as c:
        assert accounting.state(c)==before
        assert index.verify_index(c,migration_id=ITEM.migration_id)
    result=rail.run(legacy.DATABASE_URL,legacy.ENV)
    assert result['camp_inventory_index_preparation']=='existing_exact_valid'


def test_real_concurrent_full_migration_runs_reuse_single_receipt(ready_camp):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:rail.run(legacy.DATABASE_URL,legacy.ENV),range(2)))
    assert results[0]['migrations'][-1]['receipt_id']==results[1]['migrations'][-1]['receipt_id']
