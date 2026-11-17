"""Actual gateway/native reserve/append/commit/begin_on on disposable PostgreSQL.
Only external reads, hardware HTTP and latency are synthetic; no live effects.
"""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import pytest
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.sales import sam_live_stock_launch_control as sales
from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
from tests.test_rootline_scheduled_final_snapshot import ScheduledJourney

URL=os.getenv("ROOTLINE_CAPACITY_EDGE_POSTGRES_URL",os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL",""))
pytestmark=pytest.mark.skipif(not URL,reason="explicit disposable PostgreSQL URL required")

@pytest.fixture(autouse=True)
def isolated():
    if not URL:return
    target=urlparse(URL)
    assert target.hostname in {"127.0.0.1","localhost"}
    assert target.path in {"/rootline_capacity_edge_test_20261117_01","/rootline_managed"}
    import psycopg
    migration = (Path(budget.__file__).resolve().parents[2] / "supabase/migrations/"
        "202607070001_create_sam_live_stock_conversation_review_events.sql")
    with psycopg.connect(URL) as c:
        c.execute(migration.read_text(encoding="utf-8"))
        c.execute("truncate public.sam_live_stock_conversation_review_events")

class RealReserveJourney(ScheduledJourney):
    def __init__(self,patch,*,fault=None,sql_seconds=.35,connect_seconds=.8,prior_safety_seconds=0):
        super().__init__(patch,full_seconds=24)
        original_spend=self.spend
        def spend(kind,seconds):
            original_spend(kind,seconds+(prior_safety_seconds if kind=="owned safety" else 0))
        self.spend=spend
        self.borehole_checks=0
        from tests import test_rootline_scheduled_final_snapshot as scheduled_fixture
        from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
        real_gateway=scheduled_fixture.handle_rootline_reassessment_trigger
        active_borehole={"contract_version":"rootline_borehole_runtime_eligibility.v5",
            "stop_mode":"conditions","device_key":"ewelink:ewelink_owner_account:1002851416:1",
            "device_id":"1002851416","channel":1,"auxiliary_device_id":"BOREHOLE-1-MINI-R4-CH1",
            "requested_seconds":None,"native_fail_stop_seconds":0,"state":"Active",
            "execution_id":"SYNTHETIC-ADOPTED-BH","claimed_at":self.now.isoformat(),"original_start_at":None,"on_attempts":0,
            "provider_start_evidence":{"authoritative":True,"state":"ON"}}
        journey=self
        class BoreholeTransport:
            def read_output_state(self,**kwargs):
                journey.borehole_checks+=1
                return {**kwargs,"authoritative":True,"state":"ON",
                    "retrieved_at":journey.now.isoformat(),"evidence_id":"OFFLINE-BH"}
            def set_state(self,**kwargs):pytest.fail("healthy adopted borehole must not be commanded")
        def managed(**kwargs):
            from modules.telemetry.rootline_cycle_budget import mandatory_safety
            with mandatory_safety():journey.spend("owned safety",22)
            def store(action,item):
                if action=="load_active_auxiliaries":return []
                if action=="load_active_borehole":return deepcopy(active_borehole)
                pytest.fail("unexpected borehole mutation: "+action)
            return run_rootline_managed_device_cycle(evidence={},environ=kwargs["environ"],
                transport=BoreholeTransport(),store=store,now=journey.now,clock=lambda:journey.now,
                allow_new_starts=False,allow_borehole_starts=False,after_safety=kwargs["after_safety"],
                energy_reader=lambda:{"continuous_borehole_fresh":True,"continuous_borehole_eligible":True},
                borehole_safety_reader=lambda:True,borehole_conditions_reader=lambda:{"success":True,"stop_required":False})
        def gateway(*args,**kwargs):
            kwargs["managed_device_cycle"]=managed
            return real_gateway(*args,**kwargs)
        patch.setattr(scheduled_fixture,"handle_rootline_reassessment_trigger",gateway)
        self.fault=fault;self.sql_trace=[];self.committed=[];self.reserve_started=None
        self.source.update(DATABASE_URL=URL,EWELINK_CLIENT_ID="offline-capacity-app")
        # Canonical A legacy binding is unrelated to capacity; no live source.
        from modules.telemetry import rootline_execution_runtime as runtime
        patch.setattr(runtime,"_refresh_a_irrigation_binding",lambda *a:None)
        j=self
        class Tokens:
            database_url=URL
            def latest(self):
                j.spend("token latest",2)
                if fault=="token":raise RuntimeError("secret-token raw SQL must not escape")
                return {"region":"eu"}
        self.tokens=Tokens();self.transport.token_store=self.tokens
        patch.setattr(coordinator,"prepare_execution_capacity",budget.prepare_execution_capacity)
        patch.setattr(budget.RequestBudget,"begin_on",ORIGINAL_BEGIN_ON)
        connect=bounded.connect_bounded_rootline_postgres
        def timed_connect(**kwargs):
            assert kwargs["database_url"]==URL
            j.spend("connection and transaction setup",connect_seconds)
            budget_remaining()
            return Connection(connect(**kwargs),j,sql_seconds)
        patch.setattr(bounded,"connect_bounded_rootline_postgres",timed_connect)
        recorder=sales.record_sam_live_stock_review_event
        def record(event,**kwargs):
            result,status=recorder(event,**kwargs)
            action=event["review_json"]["ewelink_request_budget"]["action"]
            if action=="active_duty_reserved" and fault=="receipt":
                result={**result,"persisted_receipt":{"review_event_id":"wrong","review_json":{}}}
            return result,status
        patch.setattr(sales,"record_sam_live_stock_review_event",record)
        original_capacity=self.transport.prepare_execution_capacity
        def capacity(execution):
            j.reserve_started=j.elapsed
            return original_capacity(execution)
        patch.setattr(self.transport,"prepare_execution_capacity",capacity)

class Connection:
    def __init__(self,inner,j,seconds):self.inner=inner;self.j=j;self.seconds=seconds;self.action=None
    def __getattr__(self,key):return getattr(self.inner,key)
    def __enter__(self):self.inner.__enter__();return self
    def __exit__(self,kind,value,tb):
        if kind is None and self.action=="active_duty_reserved" and self.j.fault=="commit":
            self.inner.__exit__(RuntimeError,RuntimeError("synthetic commit failure"),None)
            raise RuntimeError("secret commit payload")
        result=self.inner.__exit__(kind,value,tb)
        if kind is None:
            self.j.committed.append(self.action)
            self.j.spend("commit acknowledgement",.4)
            if self.action=="active_duty_reserved" and self.j.fault=="late_commit":
                self.j.spend("late commit acknowledgement",141)
        return result
    def execute(self,sql,params=None,**kwargs):
        cursor=self.cursor();return cursor.execute(sql,params,**kwargs)
    def cursor(self,*args,**kwargs):return Cursor(self.inner.cursor(*args,**kwargs),self)

class Cursor:
    def __init__(self,inner,connection):self.inner=inner;self.connection=connection
    def __getattr__(self,key):return getattr(self.inner,key)
    def __enter__(self):self.inner.__enter__();return self
    def __exit__(self,*args):return self.inner.__exit__(*args)
    def execute(self,sql,params=None,**kwargs):
        c=self.connection;j=c.j;text=str(sql)
        if isinstance(params,dict) and "review_json" in params:
            payload=json.loads(params["review_json"])
            c.action=payload.get("ewelink_request_budget",{}).get("action")
        j.sql_trace.append({"at":j.elapsed,"sql":text,"action":c.action})
        j.spend("SQL",c.seconds)
        if j.fault=="deadline" and "with stamp as" in text:
            j.spend("slow capacity preimage",141)
        if j.fault=="sql" and "with stamp as" in text:
            import psycopg
            raise psycopg.errors.QueryCanceled("secret SQL query")
        budget_remaining()
        self.inner.execute(sql,params,**kwargs);return self
    def fetchone(self):
        row=self.inner.fetchone()
        # Virtual clock covers DB clock samples as well as shared monotonic time.
        if row:return tuple(self.connection.j.now if isinstance(x,datetime) else x for x in row)
        return row
    def fetchall(self):return self.inner.fetchall()

def budget_remaining():
    from modules.telemetry.rootline_cycle_budget import remaining_seconds
    remaining_seconds()

ORIGINAL_BEGIN_ON=budget.RequestBudget.begin_on

def rows():
    import psycopg
    with psycopg.connect(URL) as c:
        return c.execute("select review_json->'ewelink_request_budget' from public.sam_live_stock_conversation_review_events order by created_at,review_event_id").fetchall()


def test_gateway_real_capacity_commit_begin_on_and_sender(monkeypatch):
    j=RealReserveJourney(monkeypatch)
    value,status=j.gateway()
    assert j.controls, json.dumps(value,default=str)
    assert j.controls[0]["status"]=="segment_started",j.controls
    assert [x["state"] for x in j.calls]==["ON"]
    assert j.evidence_reads==j.authority_calls==2 and len(j.reads)==3
    assert j.borehole_checks==1
    assert value["managed_device_result"]["status"]=="borehole_active"
    ledger=[r[0] for r in rows()]
    assert sorted(r["action"] for r in ledger)==["active_duty_on_attempt_reserved","active_duty_reserved"]
    reserve=next(r for r in ledger if r["action"]=="active_duty_reserved")["state"]["reserves"]
    assert len(reserve)==1
    entry=next(iter(reserve.values()))
    assert (datetime.fromisoformat(entry["admit_until"])-datetime.fromisoformat(entry["reserved_at"])).total_seconds()==30
    assert entry["remaining"]==budget.DUTY_CAPACITY["irrigation_zone_valve"]
    assert "active_duty_reserved" in j.committed
    assert next(t for kind,t,_ in j.events if kind=="HTTP ON")<140
    assert sum("returning review_event_id,review_json,created_at" in r["sql"] for r in j.sql_trace)==2
    assert not any("_provider_capacity_failure" in str(item) for _,item in j.backing.rows)
    assert any("pg_try_advisory_xact_lock" in r["sql"] for r in j.sql_trace)

@pytest.mark.parametrize("fault",["token","sql","deadline","receipt","commit","late_commit"])
def test_capacity_failures_reach_gateway_and_saved_outcome_without_on(monkeypatch,fault):
    j=RealReserveJourney(monkeypatch,fault=fault)
    value,status=j.gateway()
    assert not any(c["state"]=="ON" for c in j.calls)
    if fault=="late_commit":
        assert j.controls[0]["status"]=="execution_cycle_deadline_deferred",j.controls
        assert not any(a=="claim_before_on" for a,_ in j.backing.rows)
        assert any(r[0]["action"]=="active_duty_reserved" for r in rows())
        return
    assert j.controls[0]["status"]=="provider_capacity_unavailable",j.controls
    failure=value["irrigation_failure"]
    saved=[v for k,v in j.schedules.rows.items() if k.endswith(":outcome")][-1]
    assert saved["irrigation_failure"]==failure
    assert "secret" not in json.dumps(failure) and "raw SQL" not in json.dumps(failure)
    assert not any(a=="claim_before_on" for a,_ in j.backing.rows)
    if fault=="sql":assert failure["cause_type"]=="QueryCanceled"
    if fault in {"deadline","late_commit"}:assert failure["cycle_remaining_ms"]==0
    if fault=="receipt":assert failure["reason"]=="ewelink_request_accounting_unproven"
    if fault=="late_commit":assert any(r[0]["action"]=="active_duty_reserved" for r in rows())
    if fault in {"receipt","commit"}:assert rows()==[]


def test_hostile_capacity_metadata_is_sanitized_at_gateway_and_durable_outcome(monkeypatch):
    j=RealReserveJourney(monkeypatch)
    def reject(execution):
        execution["_provider_capacity_failure"]={"reason":"secret URL", "error_type":"RuntimeError",
            "raw":"secret SQL", "cycle_remaining_ms":-4}
        return None
    monkeypatch.setattr(j.transport,"prepare_execution_capacity",reject)
    value,_=j.gateway()
    assert value["irrigation_failure"]=={"error_type":"RuntimeError"}
    saved=[v for k,v in j.schedules.rows.items() if k.endswith(":outcome")][-1]
    assert saved["irrigation_failure"]=={"error_type":"RuntimeError"}
    assert not j.calls


def test_observed_late_capacity_edge_still_sends_before_original_deadline(monkeypatch):
    j=RealReserveJourney(monkeypatch,prior_safety_seconds=37.6)
    value,_=j.gateway()
    assert j.reserve_started==pytest.approx(128)
    assert j.controls, json.dumps(value,default=str)
    assert j.controls[0]["status"]=="segment_started",j.controls
    on_at=next(t for kind,t,_ in j.events if kind=="HTTP ON")
    assert on_at==pytest.approx(138.3) and on_at<140
    assert len(j.calls)==1


def test_capacity_after_same_profile_expires_safely_without_deadline_extension(monkeypatch):
    j=RealReserveJourney(monkeypatch,prior_safety_seconds=42)
    value,_=j.gateway()
    assert not any(c["state"]=="ON" for c in j.calls)
