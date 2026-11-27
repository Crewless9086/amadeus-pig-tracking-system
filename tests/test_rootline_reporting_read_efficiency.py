"""Lossless reporting projections on a uniquely owned synthetic PostgreSQL schema."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid
import pytest
from modules.telemetry import rootline_irrigation_history as history
from modules.telemetry import rootline_water_energy_plan as plan
from modules.oom_sakkie import bounded_postgres_read as bounded
from tests.test_rootline_registry_read_scope import pg_connect, URL
from tests.test_rootline_water_energy_plan import daily_program_facts
NOW = datetime(2026,11,27,12,tzinfo=timezone.utc)


@pytest.fixture
def database(monkeypatch):
    if not URL: pytest.skip("explicit synthetic PostgreSQL required")
    from psycopg import sql
    from psycopg.types.json import Jsonb
    schema = "rootline_reporting60_" + uuid.uuid4().hex
    with pg_connect() as db:
        db.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
        db.execute(sql.SQL("""create table {}.sam_live_stock_conversation_review_events(
            review_event_id text primary key,event_source text,review_json jsonb,created_at timestamptz);
            create table {}.irrigation_water_credit_events(credit_json jsonb,created_at timestamptz,credit_id text);
            create table {}.irrigation_events(irrigation_event_id text,event_at timestamptz,event_type text,
                zone_id text,planned_minutes numeric,actual_minutes numeric,details jsonb,source_id text,actor text,created_at timestamptz);
            create table {}.rootline_water_energy_plan_identities(plan_id text,operating_date date,current_generation integer);
            create table {}.rootline_water_energy_plan_generations(plan_id text,generation integer,plan_json jsonb,
                evidence_sha256 text,evidence_observed_at timestamptz,replacement_reason text)""").format(*[sql.Identifier(schema)]*5))
    metrics = {"queries": [], "bytes": 0, "connections": [], "failure": False}
    real = bounded.connect_bounded_rootline_postgres
    class Cursor:
        def __init__(self, cursor): self.cursor=cursor
        def __enter__(self): self.cursor.__enter__();return self
        def __exit__(self,*args): return self.cursor.__exit__(*args)
        def execute(self, query, params=None):
            assert query.lstrip().lower().startswith("select"),query
            metrics["queries"].append(query)
            if metrics["failure"] and "rootline_execution" in query: raise RuntimeError("synthetic read failed")
            return self.cursor.execute(query.replace("public.",schema+"."),params)
        def fetchall(self):
            rows=self.cursor.fetchall();metrics["bytes"]+=len(json.dumps(rows,default=str).encode());return rows
        def fetchone(self):
            row=self.cursor.fetchone();metrics["bytes"]+=len(json.dumps(row,default=str).encode());return row
    class Connection:
        def __init__(self, db): self.db=db
        def cursor(self): return Cursor(self.db.cursor())
    @contextmanager
    def factory(**kwargs):
        assert kwargs.get("database_url")==URL
        with real(database_url=URL,read_only=True) as db:
            assert db.execute("select current_setting('transaction_read_only')").fetchone()[0]=="on"
            metrics["connections"].append(db)
            yield Connection(db)
    monkeypatch.setattr(bounded,"connect_bounded_rootline_postgres",factory)
    monkeypatch.setattr(bounded,"connect_bounded_read",factory)
    sequence=0
    def seed(payloads, *, at=NOW, source="rootline_irrigation_execution", raw=False):
        nonlocal sequence
        with pg_connect() as db:
            for payload in payloads:
                sequence+=1
                db.execute(sql.SQL("insert into {}.sam_live_stock_conversation_review_events values(%s,%s,%s,%s)").format(sql.Identifier(schema)),
                    (f"row-{sequence:06}",source,Jsonb(payload if raw else {"rootline_execution":payload}),at))
    def save(packet, generation=1):
        with pg_connect() as db:
            db.execute(sql.SQL("delete from {}.rootline_water_energy_plan_generations").format(sql.Identifier(schema)))
            db.execute(sql.SQL("delete from {}.rootline_water_energy_plan_identities").format(sql.Identifier(schema)))
            db.execute(sql.SQL("insert into {}.rootline_water_energy_plan_identities values('plan',%s,%s)").format(sql.Identifier(schema)),(NOW.date(),generation))
            db.execute(sql.SQL("insert into {}.rootline_water_energy_plan_generations values('plan',%s,%s,'digest',%s,'initial')").format(sql.Identifier(schema)),(generation,Jsonb(packet),NOW))
    try:
        yield SimpleNamespace(seed=seed,save=save,metrics=metrics,factory=lambda:factory(database_url=URL),schema=schema)
    finally:
        assert all(c.closed for c in metrics["connections"])
        with pg_connect() as db:
            # Only the UUID schema created by this fixture; never public tables.
            db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


def pair(database, shared, cutoff=NOW):
    scope=history._reporting_execution_rows(URL,evidence_cutoff=cutoff) if shared else None
    kwargs={"_execution_rows":scope} if shared else {}
    with ThreadPoolExecutor(max_workers=2) as workers:
        parent=workers.submit(history.read_canonical_irrigation_history,URL,now=cutoff,evidence_cutoff=cutoff,**kwargs)
        managed=workers.submit(plan._read_managed_device_evidence,URL,cutoff,evidence_cutoff=cutoff,**kwargs)
        return parent.result(),managed.result()


def test_sql_union_matches_each_original_predicate_and_projector(database):
    # Every original action plus malformed payload/action shapes and unrelated rows.
    database.seed([{"action":action,"execution_id":"old-"+action,"proof":{"preserve":[1,None,"x"]}}
        for action in set(history.PARENT_ACCOUNTING_ACTIONS+history.MANAGED_ACCOUNTING_ACTIONS)])
    database.seed([None,[],"bad",{}, {"action":None},{"action":True},{"action":7},{"action":[]},{"action":{}},{"action":"unrelated"}])
    fixture=Path(__file__).parent/"fixtures/rootline_auxiliary_closure_history.json"
    body=json.loads(fixture.read_text()); rows=body if isinstance(body,list) else body["fertilizer_executions"]
    assert rows and any(r.get("action")=="contain_auxiliary_device" for r in rows)
    database.seed(rows,at=NOW-timedelta(days=1))
    database.seed([{"action":"mark_active","execution_id":"future"}],at=NOW+timedelta(seconds=1))
    baseline=pair(database,False); database.metrics["queries"].clear()
    result=pair(database,True)
    assert result==baseline
    assert result[0]["status"]=="Available" and result[1]["status"]=="Available"
    assert sum("select payload, parent_match" in q for q in database.metrics["queries"])==1
    assert not any("future" in str(packet) for packet in result)
    assert all(c.closed for c in database.metrics["connections"])


def test_shared_cutoff_copy_isolation_backdated_insert_and_fresh_next_call(database):
    database.seed([{"action":"mark_active","execution_id":"one","nested":{"value":1}}])
    shared=history._reporting_execution_rows(URL,evidence_cutoff=NOW)
    first=shared("parent",NOW);first[0]["nested"]["value"]=9
    database.seed([{"action":"mark_active","execution_id":"backdated"}],at=NOW-timedelta(days=30))
    assert shared("managed",NOW)==[{"action":"mark_active","execution_id":"one","nested":{"value":1}}]
    fresh=history._reporting_execution_rows(URL,evidence_cutoff=NOW)
    assert [r["execution_id"] for r in fresh("parent",NOW)]==["backdated","one"]
    with pytest.raises(ValueError):shared("parent",NOW+timedelta(seconds=1))
    with pytest.raises(ValueError):shared("command",NOW)


def test_shared_failure_closes_resources_and_both_projectors_stay_unavailable(database):
    database.metrics["failure"]=True
    result=pair(database,True)
    assert all(value["status"]=="Unavailable" for value in result)
    assert all(c.closed for c in database.metrics["connections"])
    database.metrics["failure"]=False
    assert all(value["status"]=="Available" for value in pair(database,True))


def program():
    facts=daily_program_facts(NOW)
    return plan.build_daily_program(facts,NOW.date().isoformat(),now=NOW),facts


@pytest.mark.parametrize("mutation", [None,"legacy","string_success","null_program","wrong_version","null_history","absent_history"])
def test_sql_saved_projection_is_exact_and_legacy_stays_full(database,mutation):
    packet,facts=program();packet["recent_irrigation_history"]={"large":"x"*347293}
    if mutation=="legacy":packet.pop("daily_program")
    if mutation=="string_success":packet["success"]="true"
    if mutation=="null_program":packet["daily_program"]=None
    if mutation=="wrong_version":packet["daily_program"]["version"]="old"
    if mutation=="null_history":packet["recent_irrigation_history"]=None
    if mutation=="absent_history":packet.pop("recent_irrigation_history")
    database.save(packet)
    full,status=plan.get_current_water_energy_plan(NOW.date(),URL)
    lean,lean_status=plan.get_current_water_energy_plan(NOW.date(),URL,_omit_replaced_history=True)
    assert status==lean_status==200
    expected=deepcopy(full)
    if plan._saved_program(packet):expected.pop("recent_irrigation_history",None)
    assert lean==expected
    if plan._saved_program(packet):
        assert plan.project_saved_program_for_execution(full,facts,now=NOW)==plan.project_saved_program_for_execution(lean,facts,now=NOW)
    assert plan.get_current_water_energy_plan(NOW.date(),URL)[0]==full


def test_nonzero_query_transfer_cost_uses_actual_sql_payloads(database,record_property):
    packet,facts=program();packet["recent_irrigation_history"]={"history":"x"*347293};database.save(packet)
    database.seed([{"action":"mark_active","execution_id":str(i),"original_proof":"x"*2048} for i in range(120)])
    before=database.metrics["bytes"];pair(database,False);plan.get_current_water_energy_plan(NOW.date(),URL)
    full_bytes=database.metrics["bytes"]-before
    before=database.metrics["bytes"];pair(database,True);plan.get_current_water_energy_plan(NOW.date(),URL,_omit_replaced_history=True)
    lean_bytes=database.metrics["bytes"]-before
    assert full_bytes-lean_bytes>347293
    # Declared model, not measured production latency: three connection setups,
    # nonzero per-query overhead, and JSON transfer at 200KB/s.
    old_cost=3*1.8+8*.15+full_bytes/200000
    new_cost=3*1.8+7*.15+lean_bytes/200000
    assert new_cost<old_cost
    record_property("full_json_bytes",full_bytes);record_property("projected_json_bytes",lean_bytes)
    record_property("modeled_seconds_saved",old_cost-new_cost)

def wire_other_readers(monkeypatch):
    from modules.telemetry import power_service,rootline_daily_advisor,rootline_owner_controls
    facts=daily_program_facts(NOW)
    packet={"success":True,"source":{"last_reading_at":NOW.isoformat(),"stale_after_minutes":15},"current":facts["power"]}
    monkeypatch.setattr(power_service,"get_current_power_state",lambda **kw:(deepcopy(packet),200))
    monkeypatch.setattr(rootline_daily_advisor,"get_rootline_daily_advisor",lambda *a,**kw:({
        "zones":deepcopy(facts["irrigation"]["zones"]),"generated_at":NOW.isoformat(),
        "operating_date":NOW.date().isoformat(),"current_weather_packet":{
            "success":True,"source":{"last_reading_at":NOW.isoformat(),"stale_after_minutes":30},
            "current":facts["weather"]}},200))
    monkeypatch.setattr(rootline_owner_controls,"load_runtime_owner_controls",lambda *a,**kw:rootline_owner_controls.project_owner_controls([],now=NOW))
    for name in ("read_latest_zone_water_balances","_read_latest_tank_observation","_read_latest_owner_zone_need","_read_historical_context"):
        monkeypatch.setattr(plan,name,lambda *a,**kw:{"status":"Unavailable"})


def test_actual_reporting_loader_shared_once_control_phase_and_next_call_fresh(database,monkeypatch):
    packet,_=program();database.save(packet);wire_other_readers(monkeypatch)
    first,_,_=plan.read_current_water_energy_evidence(database_url=URL,now=NOW,
        evidence_cutoff=NOW,forecast_mode="live_only")
    assert first["irrigation_history"]["status"]=="Available"
    assert sum("select payload, parent_match" in q for q in database.metrics["queries"])==1
    assert "recent_irrigation_history" not in first["saved_daily_plan"]
    assert all(c.closed for c in database.metrics["connections"])
    database.metrics["queries"].clear()
    plan.read_current_water_energy_evidence(database_url=URL,now=NOW,forecast_mode="live_only")
    assert not any("select payload, parent_match" in q for q in database.metrics["queries"])
    database.metrics["queries"].clear()
    plan.read_current_water_energy_evidence(database_url=URL,now=NOW,evidence_cutoff=NOW,forecast_mode="live_only")
    assert sum("select payload, parent_match" in q for q in database.metrics["queries"])==1


def test_old_unresolved_parent_and_duplicate_terminal_parity(database):
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job,project_next_segment
    job=build_irrigation_job(zone_id="B12345",operating_date="2026-08-01",requested_total_seconds=7200,
        requested_total_minutes=120,maximum_segment_seconds=3599,expected_segment_count=2,plan_identity="OLD")
    segment=project_next_segment(job,[])
    eligibility={"action":"record_eligibility",**job,"requested_total_duration_seconds":7200,
        "requested_total_duration_minutes":120,"governed_executable_duration_seconds":7198,"plan_generation":"OLD"}
    terminal={"action":"record_completed","job_id":job["job_id"],"segment_number":1,
        "segment_identity":segment["segment_identity"],"execution_id":"old-partial","state":"Completed",
        "verified_runtime_seconds":3599,"shutdown_verified":True}
    database.seed([eligibility,terminal,deepcopy(terminal)],at=NOW-timedelta(days=110))
    old=pair(database,False);new=pair(database,True)
    assert old==new
    assert job["job_id"] in json.dumps(new[0])
    assert new[0]["zones"]["B12345"]["verified_completed_days"]==[]


@pytest.mark.parametrize("race",[False,True])
def test_lean_revision_changed_unchanged_owner_change_and_cas_full_readback(race):
    from tests.test_rootline_water_energy_plan import MemoryProgrammeDB
    from modules.telemetry.rootline_owner_controls import project_owner_controls
    saved,facts=program();saved["generation"]=1
    full_db=MemoryProgrammeDB();lean_db=MemoryProgrammeDB()
    full_db.plans[saved["operating_date"]]=deepcopy(saved);lean_db.plans[saved["operating_date"]]=deepcopy(saved)
    lean=deepcopy(saved);lean.pop("recent_irrigation_history",None)
    if race:
        for db in (full_db,lean_db):
            db.plans[saved["operating_date"]]["generation"]=2
            db.plans[saved["operating_date"]]["recent_irrigation_history"]={"newer":"must survive CAS"}
    with full_db.connect() as c:full_result=plan.revise_program_remainder(saved,facts,now=NOW,connection=c)
    with lean_db.connect() as c:lean_result=plan.revise_program_remainder(lean,facts,now=NOW,connection=c)
    assert full_result==lean_result
    if race:
        assert lean_result[0]["recent_irrigation_history"]=={"newer":"must survive CAS"}
        assert lean_db.appends==0
        return
    assert lean_db.appends==full_db.appends==1
    with lean_db.connect() as c:unchanged=plan.revise_program_remainder(lean_result[0],facts,now=NOW,connection=c)
    assert unchanged[1]==200 and lean_db.appends==1
    # Actual canonical reducer supplies the baseline; an effective saved pause
    # changes the current projection, not the immutable programme's base work.
    controls=project_owner_controls([],now=NOW)
    controls["devices"]["camp_a"]["mode"]="paused"
    changed={**facts,"owner_controls":controls}
    full=plan.project_saved_program_for_execution(lean_result[0],changed,now=NOW)
    lean=deepcopy(lean_result[0]);lean.pop("recent_irrigation_history",None)
    assert plan.project_saved_program_for_execution(lean,changed,now=NOW)==full
    assert next(t for t in full["candidate_tasks"] if t["task_id"]=="irrigation_A12345")["zone_decision"]=="Hold"


def test_refresh_uses_fresh_lean_program_then_complete_projection_and_timings(database,monkeypatch):
    from modules.telemetry import rootline_specialist_result as specialist
    from modules.telemetry.rootline_stage_timings import StageTimings
    packet,facts=program();database.save(packet);wire_other_readers(monkeypatch)
    # Prime the existing programme's reachable live adjustments using the real
    # reducer, then reporting must use its normal unchanged revision path.
    projected=plan.project_saved_program_for_execution(packet,facts,now=NOW)
    adjustments=[{"task_id":t["task_id"],"decision":t.get("zone_decision"),"reason":t.get("live_adjustment_reason"),
        "window":t.get("preferred_window"),"start_at":t.get("planned_start_at"),"end_at":t.get("planned_end_at")}
        for t in projected["candidate_tasks"] if t.get("live_adjustment_reason")]
    packet["daily_program"]["adjustments"]=adjustments
    loaded,_,_=plan.read_current_water_energy_evidence(database_url=URL,now=NOW,evidence_cutoff=NOW,forecast_mode="live_only")
    projected=plan.project_saved_program_for_execution(packet,loaded,now=NOW)
    packet["daily_program"]["adjustments"]=[{"task_id":t["task_id"],"decision":t.get("zone_decision"),"reason":t.get("live_adjustment_reason"),
        "window":t.get("preferred_window"),"start_at":t.get("planned_start_at"),"end_at":t.get("planned_end_at")}
        for t in projected["candidate_tasks"] if t.get("live_adjustment_reason")]
    packet["daily_program"]["carry_origins"]=projected["daily_program"]["carry_origins"]
    database.save(packet)
    monkeypatch.setattr(specialist,"_with_provider_availability",lambda value,**kw:value)
    timings=StageTimings();result=specialist.refresh_current_rootline_specialist_result(database_url=URL,
        now=NOW,evidence_cutoff=NOW,stage_timings=timings)
    assert result["success"] is True
    assert {"plan_evidence","plan_programme","plan_revision","plan_enrichment"}<=set(timings.snapshot()["stages"])
    assert result["canonical_plan"]["generation"]==1
    assert all(c.closed for c in database.metrics["connections"])

def test_sql_cas_race_returns_new_generation_full_history(database):
    saved,facts=program();database.save(saved)
    lean,_=plan.get_current_water_energy_plan(NOW.date(),URL,_omit_replaced_history=True)
    newer=deepcopy(saved);newer["recent_irrigation_history"]={"newer":"never discard"}
    database.save(newer,generation=2)
    with database.factory() as connection:
        result,status=plan.revise_program_remainder(lean,facts,now=NOW,database_url=URL,connection=connection)
    assert status==200 and result["generation"]==2
    assert result["recent_irrigation_history"]=={"newer":"never discard"}
    assert all(c.closed for c in database.metrics["connections"])


def test_managed_projection_never_consumes_omitted_history(database,monkeypatch):
    saved,facts=program();database.save(saved);wire_other_readers(monkeypatch)
    current,_,_=plan.read_current_water_energy_evidence(database_url=URL,now=NOW,forecast_mode="live_only",
        purpose="managed",pending_devices=["FERTILIZER-MIXER-CH2"])
    full=plan.project_saved_program_for_execution(saved,current,now=NOW)
    lean=plan.project_saved_program_for_execution(current["saved_daily_plan"],current,now=NOW)
    for value in (full,lean):
        for key in ("recent_irrigation_history","generation","evidence_sha256","evidence_observed_at","replacement_reason"):
            value.pop(key,None)
    assert full==lean
    assert not any("select payload, parent_match" in q for q in database.metrics["queries"])


def test_canonical_startup_abort_proof_survives_shared_managed_read(database):
    from tests.test_rootline_auxiliary_shutdown_history import aborted_startup_history
    from modules.telemetry.rootline_irrigation_lifecycle import auxiliary_shutdown_unverified
    rows=aborted_startup_history()
    database.seed(rows,at=NOW-timedelta(days=1))
    cutoff=datetime.fromisoformat(rows[-1]["aborted_at"])+timedelta(seconds=1)
    before=pair(database,False,cutoff);after=pair(database,True,cutoff)
    assert before==after
    returned=after[1]["fertilizer_executions"]
    assert returned==[r for r in rows if r["action"] in history.MANAGED_ACCOUNTING_ACTIONS]
    assert not auxiliary_shutdown_unverified(returned,evidence_cutoff=cutoff)
    assert returned[-1]["mixing_credit"] is False


def test_measured_live_payload_model_is_explicitly_not_a_latency_guarantee():
    # Root's read-only 2026-11-27 aggregate: E60/union-size-20261127T130227058584.json.
    union_bytes=8331885;overlap_bytes=1044783;obsolete_plan_history_bytes=347293
    full_bytes=union_bytes+overlap_bytes+398328
    lean_bytes=union_bytes+398328-obsolete_plan_history_bytes
    assert full_bytes-lean_bytes==1392076
    # Only throughput and one eliminated SELECT are modeled. The union remains
    # large; this test must never assert that the whole55s report reserve fits.
    for bytes_per_second in (100000,200000,1000000):
        old_seconds=full_bytes/bytes_per_second+.15*8+3*1.8
        new_seconds=lean_bytes/bytes_per_second+.15*7+3*1.8
        assert new_seconds<old_seconds
        assert new_seconds>5
