"""Real cancellation proof, only in the named local disposable database."""
from contextlib import nullcontext
from pathlib import Path
import os,hashlib
import psycopg
import pytest
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry.rootline_failure_diagnostics import exception_failure
from modules.sales import sam_live_stock_launch_control as recorder
URL=os.getenv('ROOTLINE_DISPOSABLE_POSTGRES_URL','')
pytestmark=pytest.mark.skipif(not URL,reason='explicit disposable local PostgreSQL required')

@pytest.fixture
def local_db():
    from psycopg.conninfo import conninfo_to_dict
    info=conninfo_to_dict(URL)
    assert info['host']=='127.0.0.1' and info['port']=='56437' and info['dbname']=='rootline_accounting_followup_20261116'
    source=Path(os.getenv('ROOTLINE_SOURCE_CHECKOUT') or Path(__file__).resolve().parents[1]).resolve()
    migration=source/'supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql'
    assert hashlib.sha256(migration.read_bytes()).hexdigest()=='2e248b2b76f6101ff0e5fd7ef4fede94c7e7ad6fc992a3856a43c5bef3d0e3ee'
    with psycopg.connect(URL) as connection:
        connection.execute(migration.read_text())
    return URL


def connect(url):return psycopg.connect(url,options='-c statement_timeout=80 -c lock_timeout=0')


def test_real_postgres_canceled_exact_admission_query(local_db):
    with psycopg.connect(local_db) as blocker:
        blocker.execute('lock table public.sam_live_stock_conversation_review_events in access exclusive mode')
        client=budget.RequestBudget({},connect_factory=lambda:connect(local_db))
        with pytest.raises(budget.RequestBudgetUnavailable) as caught:
            with client._locked() as connection:client._admission_preimage(connection,scope='synthetic',region='eu')
    failure=exception_failure(caught.value)
    assert failure['accounting_operation']=='admission_preimage' and failure['sqlstate']=='57014'


def test_real_postgres_canceled_clock_after_reserved_intent_keeps_charge(local_db,monkeypatch):
    from psycopg.types.json import Jsonb
    import uuid
    identity='SYNTHETIC-'+uuid.uuid4().hex
    with psycopg.connect(local_db) as connection:
        connection.execute('insert into public.sam_live_stock_conversation_review_events (review_event_id,event_source,review_json) values(%s,%s,%s)',
            (identity,'synthetic-accounting-cancel',Jsonb({'ewelink_request_budget':{'attempt_units':1,'state':{'pending_attempt':{'id':identity}}}})))
    class SlowClock(psycopg.Connection):
        def execute(self,query,params=None,**kwargs):
            if query=='select clock_timestamp()':query='select clock_timestamp() from pg_sleep(0.2)'
            return super().execute(query,params,**kwargs)
    client=budget.RequestBudget({},connect_factory=lambda:SlowClock.connect(local_db,options='-c statement_timeout=80'))
    with pytest.raises(budget.RequestBudgetUnavailable) as caught:
        with client._locked() as connection:client._now(connection)
    assert exception_failure(caught.value)['accounting_operation']=='clock_read'
    assert exception_failure(caught.value)['sqlstate']=='57014'
    with psycopg.connect(local_db) as connection:
        state=connection.execute("select review_json->'ewelink_request_budget' from public.sam_live_stock_conversation_review_events where review_event_id=%s",(identity,)).fetchone()[0]
    assert state['attempt_units']==1 and state['state']['pending_attempt']['id']==identity


def test_real_postgres_recorder_insert_cancellation_survives_result_boundary(local_db):
    with psycopg.connect(local_db) as blocker:
        blocker.execute('lock table public.sam_live_stock_conversation_review_events in access exclusive mode')
        result,status=recorder.record_sam_live_stock_review_event({'review_event_id':'SYNTHETIC-INSERT-CANCEL'},
            database_url='synthetic',connect_factory=lambda:connect(local_db))
    assert status==500 and result['sqlstate']=='57014' and result['accounting_operation']=='review_event_insert'
