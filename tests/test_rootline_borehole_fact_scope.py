"""Fresh sequential facts share only an explicitly owned read-only transaction."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import uuid
import pytest
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_owner_controls as controls
from modules.telemetry import rootline_water_energy_plan as plan
from modules.telemetry import weather_service as weather
from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded
from tests.test_rootline_registry_read_scope import URL, pg_connect
NOW=datetime(2026,11,27,12,tzinfo=timezone.utc)

class Connection:
    def __init__(self,events,identity=0):self.events=events;self.identity=identity;self.closed=False;self.mode=("read committed","on")
    def __enter__(self):self.events.append(("enter",self.identity));return self
    def __exit__(self,kind,value,tb):self.events.append(("exit",self.identity,kind));self.closed=True
    def close(self):self.closed=True;self.events.append(("close",self.identity))
    def execute(self,sql,params=None):
        assert not self.closed
        self.events.append(("query",self.identity,sql));return self
    def fetchone(self):return self.mode

def factory_case():
    events=[];connections=[]
    def connect():
        c=Connection(events,len(connections));connections.append(c);return c
    return connect,events,connections

def test_same_pass_one_connection_all_sequential_reads_and_next_pass_new():
    connect,events,connections=factory_case()
    readers=[(name,lambda c,name=name:events.append(("read",name,c.identity)) or name) for name in ("energy","protection","owner_stop","weather")]
    first=runtime._read_borehole_facts(readers,connect=connect)
    assert first=={"values":{n:n for n,_ in readers},"failed":[]}
    assert len(connections)==1 and connections[0].closed
    assert [e[1] for e in events if e[0]=="read"]==[n for n,_ in readers]
    runtime._read_borehole_facts(readers,connect=connect)
    assert len(connections)==2 and all(c.closed for c in connections)

@pytest.mark.parametrize("failed",range(4))
def test_each_query_failure_closes_before_remaining_fresh_reads(failed):
    connect,events,connections=factory_case()
    def read(c,index):
        if index==failed:raise ValueError("synthetic query error")
        if index>failed:assert connections[0].closed and c is connections[1]
        return index
    result=runtime._read_borehole_facts([(str(i),lambda c,i=i:read(c,i)) for i in range(4)],connect=connect)
    assert result["failed"]==[str(failed)]
    assert len(connections)==(1 if failed==3 else 2) and all(c.closed for c in connections)
    assert any(e[0]=="exit" and e[2] is ValueError for e in events)

@pytest.mark.parametrize("error",[RootlineCycleDeadlineExceeded("deadline"),asyncio.CancelledError()])
def test_deadline_or_cancellation_closes_without_reacquisition(error):
    connect,events,connections=factory_case()
    def fail(c):raise error
    with pytest.raises(type(error)):
        runtime._read_borehole_facts([("first",fail),("later",lambda c:pytest.fail("must not reacquire"))],connect=connect)
    assert len(connections)==1 and connections[0].closed
    assert any(e[0]=="exit" and e[2] is type(error) for e in events)

@pytest.mark.parametrize("mode",[("repeatable read","on"),("read committed","off")])
def test_wrong_transaction_scope_refused_before_reader(mode):
    connect,events,connections=factory_case()
    def wrong():c=connect();c.mode=mode;return c
    result=runtime._read_borehole_facts([("owner",lambda c:pytest.fail("unproven transaction"))],connect=wrong)
    assert result["failed"]==["owner"] and connections[0].closed

def test_enter_failure_closes_allocated_candidate():
    connect,events,connections=factory_case()
    class Broken(Connection):
        def __enter__(self):raise RuntimeError("enter failed")
    c=Broken(events)
    result=runtime._read_borehole_facts([("owner",lambda c:None)],connect=lambda:c)
    assert result["failed"]==["owner"] and c.closed

@pytest.fixture
def database():
    if not URL:pytest.skip("explicit isolated PostgreSQL required")
    from psycopg import sql
    schema="rootline_facts63_"+uuid.uuid4().hex
    with pg_connect() as db:
        db.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
        db.execute(sql.SQL("create table {}.sam_live_stock_conversation_review_events(review_event_id text,event_source text,review_json jsonb,created_at timestamptz)").format(sql.Identifier(schema)))
    try:yield schema
    finally:
        with pg_connect() as db:db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))

def scoped_factory(schema,connections,queries):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    @contextmanager
    def connect():
        with connect_bounded_rootline_postgres(database_url=URL,read_only=True,read_committed=True) as native:
            connections.append(native)
            class Borrowed:
                def execute(self,query,params=None):
                    queries.append(query)
                    return native.execute(query.replace("public.",schema+"."),params)
                def close(self):native.close()
            yield Borrowed()
    return connect

def test_real_read_committed_sees_owner_stop_committed_between_owner_queries(database):
    from psycopg import sql
    from psycopg.types.json import Jsonb
    connections=[];queries=[];active={"execution_id":"ROOTLINE-TEST63","device_key":"ewelink:ewelink_owner_account:1002851416:1"}
    at=datetime.now(timezone.utc)
    stop={"mission_id":"ROOTLINE-OWNER-CONTROLS","state":"confirmed","context":{
        "contract_version":controls.VERSION,"event_type":"owner_control","actor":"synthetic63",
        "source":"authenticated_owner_controls","request_id":"stop63","effective_at":at.isoformat(),"expires_at":(at+timedelta(hours=1)).isoformat(),
        "change":{"kind":"stop","device_id":"borehole","reason":"Synthetic owner stop","changes":{"execution_id":active["execution_id"]}}}}
    def protection(connection):
        with pg_connect() as writer:
            writer.execute(sql.SQL("insert into {}.sam_live_stock_conversation_review_events values(%s,%s,%s,%s)").format(sql.Identifier(database)),
                ("stop63",controls.SOURCE,Jsonb({"rootline_operational_intake":stop}),at))
        return plan.read_current_borehole_faults(URL,now=at,include_evidence=True,_connection=connection)
    def owner_stop(c):
        try:return controls.owner_stop_for_execution(active,database_url=URL,_connection=c)
        except Exception as exc:pytest.fail(repr(exc))
    result=runtime._read_borehole_facts([
        ("energy",lambda c:controls.load_runtime_owner_controls(URL,now=at,_connection=c)),
        ("protection",protection),
        ("owner_stop",owner_stop)],
        connect=scoped_factory(database,connections,queries))
    assert result["failed"]==[] and result["values"]["energy"]["requests"]==[]
    assert result["values"]["owner_stop"]["request_id"]=="stop63"
    assert len(connections)==1 and connections[0].closed
    assert sum("context'->>'contract_version'" in q for q in queries)==2
    assert "select clock_timestamp()" in queries

def test_real_aborted_query_discarded_then_later_owner_read_succeeds(database):
    connections=[];queries=[]
    result=runtime._read_borehole_facts([
        ("bad",lambda c:c.execute("select 1/0")),
        ("owner",lambda c:controls.load_runtime_owner_controls(URL,now=NOW,_connection=c))],
        connect=scoped_factory(database,connections,queries))
    assert result["failed"]==["bad"] and result["values"]["owner"]["requests"]==[]
    assert len(connections)==2 and all(c.closed for c in connections)


@pytest.mark.parametrize("canonical", [True, False])
def test_production_reassessment_wires_owned_scope_and_closes_before_condition_write(monkeypatch, canonical):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry import power_service, rootline_energy_policy
    from modules.oom_sakkie import bounded_postgres_read as bounded
    connect,events,connections=factory_case()
    def store(action,body):
        assert action=="assess_borehole_conditions"
        assert connections and all(c.closed for c in connections)
        events.append(("condition_write",))
        assert body["weather_snapshot"]=={"weather":"fresh"}
        return {"success":True,"stop_required":False}
    if canonical:monkeypatch.setattr(runtime,"rootline_irrigation_execution_store",store)
    monkeypatch.setattr(bounded,"connect_bounded_rootline_postgres",lambda **kw:connect())
    monkeypatch.setattr(power_service,"get_current_power_state",lambda **kw:({},200))
    def owner(*args,**kw):
        assert kw["_connection"] is connections[-1] and not connections[-1].closed
        events.append(("owner_energy",));return {}
    monkeypatch.setattr(controls,"load_runtime_owner_controls",owner)
    monkeypatch.setattr(rootline_energy_policy,"managed_energy_decision",lambda *a,**kw:{"borehole_eligible":True})
    def protection(*args,**kw):
        assert kw["_connection"] is connections[-1]
        events.append(("protection",));return {"safe":True}
    monkeypatch.setattr(plan,"read_current_borehole_faults",protection)
    def stop(*args,**kw):
        assert kw["_connection"] is connections[-1]
        events.append(("owner_stop",));return None
    monkeypatch.setattr(controls,"owner_stop_for_execution",stop)
    def weather_read(*args,**kw):
        assert kw["_connection"] is connections[-1]
        events.append(("weather",));return {"weather":"fresh"},200
    monkeypatch.setattr(weather,"get_weather_control_snapshot",weather_read)
    def cycle(**kw):
        reader=kw["borehole_facts_reader"]
        if not canonical:
            assert reader is None
        else:
            facts=reader({"execution_id":"scope63"})
            assert facts["failed"]==[] and len(connections)==1 and connections[0].closed
            kw["borehole_conditions_reader"](_weather=facts["values"]["weather"],protection=facts["values"]["protection"])
            events.append(("provider_or_off_checkpoint",))
            assert connections[0].closed
        return {"short_auxiliary_duty_owned":True,"hardware_commands":0}
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",cycle)
    result=runtime.run_rootline_managed_device_reassessment(environ={},now=NOW,clock=lambda:NOW,
        database_url="synthetic",store=store,token_store=object(),transport=object())
    assert result["hardware_commands"]==0
    if canonical:
        assert [e[0] for e in events if e[0] in {"owner_energy","protection","owner_stop","weather","condition_write","provider_or_off_checkpoint"}]==["owner_energy","protection","owner_stop","weather","condition_write","provider_or_off_checkpoint"]
    else:assert not connections


@pytest.mark.parametrize("failure_pass",[1,2,3])
def test_actual_three_pass_bundle_failure_invalidates_observation_and_closes_before_provider(monkeypatch,failure_pass):
    from tests.test_rootline_borehole_observation_bookmark import Case
    from modules.telemetry import rootline_managed_devices_runtime as managed
    c=Case();connect,events,connections=factory_case();passes=[]
    original=c.transport.read_output_state
    def provider(**kw):
        assert all(connection.closed for connection in connections)
        return original(**kw)
    c.transport.read_output_state=provider
    def facts(active):
        passes.append(active["execution_id"])
        def owner(connection):
            if len(passes)==failure_pass:raise RuntimeError("synthetic owner unavailable")
            return None
        return runtime._read_borehole_facts([
            ("energy",lambda connection:{"continuous_borehole_fresh":True,"continuous_borehole_eligible":True,"borehole_fresh":True,"borehole_eligible":True}),
            ("protection",lambda connection:{"safe":True}),
            ("owner_stop",owner),("weather",lambda connection:{})],connect=connect)
    def conditions(**kw):
        assert all(connection.closed for connection in connections)
        return {"success":True,"stop_required":False}
    result=managed.run_rootline_managed_device_cycle(evidence={},store=c.store,transport=c.transport,
        environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED":"true"},canonical_loader=lambda key:None,
        now=c.now,clock=lambda:c.now,borehole_facts_reader=facts,
        borehole_conditions_reader=conditions,after_safety=lambda result:None,
        evidence_factory=lambda **kw:{"irrigation_auxiliary_tasks":[]},allow_borehole_starts=False)
    assert len(passes)==3 and all(connection.closed for connection in connections)
    assert c.transport.reads==(3 if failure_pass==2 else 2) and c.transport.commands==[]
    assert result["hardware_commands"]==0


@pytest.mark.parametrize("error",[RootlineCycleDeadlineExceeded("deadline"),asyncio.CancelledError()])
def test_actual_supervisor_checks_owned_deadline_after_failed_bundle_closed(error):
    from tests.test_rootline_borehole_observation_bookmark import Case
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry.rootline_owned_deadlines import owned_deadline_checkpoint
    c=Case();connect,events,connections=factory_case();checks=[]
    def checkpoint(**kw):
        if connections:
            assert all(connection.closed for connection in connections)
            checks.append("closed before due OFF checkpoint")
    def facts(active):
        def fail(connection):raise error
        return runtime._read_borehole_facts([("weather",fail)],connect=connect)
    def invoke():
        return managed._supervise_owned_devices_unbounded(store=c.store,transport=c.transport,
            energy_reader=None,borehole_safety_reader=None,clock=lambda:c.now,
            previous_borehole=None,previous_due_auxiliaries=set(),borehole_facts_reader=facts)
    with owned_deadline_checkpoint(checkpoint):
        if isinstance(error,asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):invoke()
        else:invoke()
    assert checks and len(connections)==1 and connections[0].closed
    assert c.transport.commands==[]


def test_real_weather_reader_borrowed_parity_and_failure_contract(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read as bounded
    class WeatherConnection:
        def __init__(self,fail=False):self.closed=False;self.fail=fail;self.queries=[]
        def __enter__(self):return self
        def __exit__(self,*args):self.closed=True
        def cursor(self):
            parent=self
            class Cursor:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def execute(self,query,params):
                    parent.queries.append((query,params))
                    if parent.fail:raise RuntimeError("weather SQL failed")
                def fetchone(self):return ("weather", "Farm", "local", 15, NOW, 22, 50, 1, 2, 90, 0, 0, 1000, {}, "ok", "Fine", [], [[NOW.isoformat(),0]])
            return Cursor()
    ordinary=WeatherConnection();borrowed=WeatherConnection()
    monkeypatch.setattr(bounded,"connect_bounded_read",lambda **kw:ordinary)
    default=weather.get_weather_control_snapshot("synthetic",now=NOW,dry_interval_minutes=60)
    same=weather.get_weather_control_snapshot("synthetic",now=NOW,dry_interval_minutes=60,_connection=borrowed)
    assert default==same and default[0]["success"] is True
    assert ordinary.closed and not borrowed.closed and ordinary.queries==borrowed.queries
    failed=WeatherConnection(True)
    monkeypatch.setattr(bounded,"connect_bounded_read",lambda **kw:failed)
    packet,status=weather.get_weather_control_snapshot("synthetic",now=NOW)
    assert status>=400 and packet["success"] is False and failed.closed
    borrowed_fail=WeatherConnection(True)
    with pytest.raises(RuntimeError,match="weather SQL failed"):
        weather.get_weather_control_snapshot("synthetic",now=NOW,_connection=borrowed_fail)
    assert not borrowed_fail.closed


@pytest.mark.parametrize("scenario",["healthy","late_owner_stop","fault_then_weather_failure","energy_then_weather_failure"])
def test_production_callback_with_actual_managed_cycle_fresh_scopes_and_off(monkeypatch,scenario):
    from tests.test_rootline_borehole_fault_read_reuse import Case
    from modules.oom_sakkie import bounded_postgres_read as bounded
    case=Case(monkeypatch);connections=[];events=[];owner_reads=[]
    original_store=case.store
    def store(action,body):
        if action=="assess_borehole_conditions":
            assert connections and all(c.closed for c in connections)
        return original_store(action,body)
    case.store=store
    monkeypatch.setattr(runtime,"rootline_irrigation_execution_store",store)
    class FactsConnection(Connection):
        def fetchall(self):return deepcopy(case.rows)
    def connect(**kw):
        assert kw["read_only"] is True and kw["read_committed"] is True
        connection=FactsConnection(events,len(connections));connections.append(connection);return connection
    monkeypatch.setattr(bounded,"connect_bounded_rootline_postgres",connect)
    monkeypatch.setattr(controls,"load_runtime_owner_controls",lambda *args,**kw:controls.project_owner_controls([],now=case.now))
    def owner(active,**kw):
        owner_reads.append(active["execution_id"])
        if scenario=="late_owner_stop" and len(owner_reads)==2:
            return {"request_id":"late63","change":{"kind":"stop","changes":{"execution_id":active["execution_id"]}}}
        return None
    monkeypatch.setattr(controls,"owner_stop_for_execution",owner)
    original_read=case.transport.read_output_state
    def read(**kw):
        assert all(c.closed for c in connections)
        return original_read(**kw)
    case.transport.read_output_state=read
    original_command=case.transport.set_state
    def command(**kw):
        assert all(c.closed for c in connections)
        return original_command(**kw)
    case.transport.set_state=command
    if scenario.endswith("weather_failure"):
        if scenario.startswith("fault"):case.fault("manual_off_active",True)
        else:case.soc=1
        def failed_weather(*args,**kw):raise RuntimeError("weather unavailable")
        monkeypatch.setattr(weather,"get_weather_control_snapshot",failed_weather)
        case.condition_error=True
    result=case.run(callback=lambda _:None,planning=lambda:None)
    assert all(c.closed for c in connections)
    if scenario=="healthy":
        assert len(connections)==len(owner_reads)==len(case.conditions)==3
        assert case.transport.commands==[] and result["hardware_commands"]==0
    else:
        assert [row["state"] for row in case.transport.commands]==["OFF"]
        assert len(owner_reads)==(2 if scenario=="late_owner_stop" else 1)
