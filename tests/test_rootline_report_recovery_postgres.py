"""Real SQL consumption and rollback on the existing append-only scheduler rail."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Barrier
import uuid
import pytest
from modules.oom_sakkie import automatic_reassessment_store as store_module
from modules.oom_sakkie import automatic_reassessment_scheduler as scheduler
from tests.test_rootline_registry_read_scope import URL,pg_connect
from tests.test_rootline_report_recovery import record

@pytest.fixture
def database(monkeypatch):
    if not URL:pytest.skip("explicit disposable PostgreSQL required")
    from psycopg import sql
    from modules.oom_sakkie import bounded_postgres_read as bounded
    schema="rootline_recovery64_"+uuid.uuid4().hex
    with pg_connect() as c:
        c.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
        c.execute(sql.SQL("create table {}.sam_live_stock_conversation_review_events (like public.sam_live_stock_conversation_review_events including all)").format(sql.Identifier(schema)))
    native_connect=bounded.connect_bounded_rootline_postgres
    class Cursor:
        def __init__(self,native):self.native=native
        def __enter__(self):self.native.__enter__();return self
        def __exit__(self,*args):return self.native.__exit__(*args)
        def execute(self,query,params=None):return self.native.execute(query.replace("public.",schema+"."),params)
        def __getattr__(self,name):return getattr(self.native,name)
    class Connection:
        def __init__(self,native):self.native=native
        def cursor(self):return Cursor(self.native.cursor())
        def execute(self,query,params=None):return self.native.execute(query.replace("public.",schema+"."),params)
    @contextmanager
    def connect(**kwargs):
        kwargs.pop("database_url",None)
        with native_connect(database_url=URL,**kwargs) as c:yield Connection(c)
    monkeypatch.setenv("DATABASE_URL",URL)
    monkeypatch.setattr(bounded,"connect_bounded_rootline_postgres",connect)
    monkeypatch.setattr(store_module,"connect_bounded_read",lambda:connect(read_only=True))
    try:yield schema
    finally:
        with pg_connect() as c:c.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


def setup_source():
    now=datetime.now(timezone.utc)
    source=record(now-timedelta(minutes=2))
    assert store_module.automatic_reassessment_store("record_outcome",source["identity"],source)["success"]
    return source,now


def candidate(source,at):
    body=record(at,status="claimed")
    for key in ("daily_plan_stage","daily_plan_error_type","terminal_outcome"):body.pop(key,None)
    body["report_recovery_candidate"]=scheduler.report_recovery_binding(scheduler.report_recovery_source(source),body["identity"],body["invocation_receipt"])
    return body


def claim(body):
    value=store_module.automatic_reassessment_store("claim_schedule",body["identity"],body)
    actual=store_module.automatic_reassessment_store("load_schedule",body["identity"],None)
    return value,actual


def test_two_distinct_target_minutes_only_one_consumes_source(database):
    source,now=setup_source();targets=[candidate(source,now-timedelta(minutes=1)),candidate(source,now)]
    barrier=Barrier(2)
    def run(body):barrier.wait();return claim(body)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,targets))
    assert all(value["success"] and value["created"] for value,_ in results)
    recovered=[actual for _,actual in results if actual.get("report_recovery")]
    assert len(recovered)==1
    assert recovered[0]["report_recovery"]["source_identity"]==source["identity"]
    # An interrupted claimed turn remains consumed even without an outcome.
    later=candidate(source,now+timedelta(minutes=1))
    _,actual=claim(later);assert "report_recovery" not in actual


def test_failure_between_marker_and_target_rolls_back_both(database,monkeypatch):
    source,now=setup_source();body=candidate(source,now)
    original=store_module._record
    def fail(action,identity,value,connection):
        if identity==body["identity"]:raise RuntimeError("synthetic target write failure")
        return original(action,identity,value,connection)
    monkeypatch.setattr(store_module,"_record",fail)
    with pytest.raises(RuntimeError,match="target write failure"):claim(body)
    assert store_module.automatic_reassessment_store("load_schedule",body["identity"],None) is None
    monkeypatch.setattr(store_module,"_record",original)
    _,actual=claim(body)
    assert actual["report_recovery"]==body["report_recovery_candidate"]


def test_newer_success_rechecked_under_claim_lock_refuses_stale_candidate(database):
    source,now=setup_source();body=candidate(source,now)
    newer=record(now-timedelta(minutes=1),status="completed",terminal_outcome="rootline_reassessment_unchanged")
    store_module.automatic_reassessment_store("record_outcome",newer["identity"],newer)
    _,actual=claim(body)
    assert "report_recovery" not in actual


def test_same_minute_replay_does_not_consume_or_replace_binding(database):
    source,now=setup_source();body=candidate(source,now)
    first,actual=claim(body);second,replayed=claim(body)
    assert first["created"] is True and second["created"] is False
    assert actual==replayed
