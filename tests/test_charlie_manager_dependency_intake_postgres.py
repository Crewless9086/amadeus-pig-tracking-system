"""Real manager producer -> existing CORE event/command rails, isolated PG only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import psycopg

from modules.charlie import manager_dependency_intake as intake
from modules.charlie import executive_runtime as executive
from modules.charlie.executive_store import load_executive_context
from modules.oom_sakkie import general_manager_worker as worker
from tests.test_oom_sakkie_mortality_reconciliation import legacy

URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="explicit isolated PostgreSQL required")
REVISION = "d"*40


class CoreCursor:
    def __init__(self, cursor, schema): self.cursor, self.schema = cursor, schema
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self,*args): return self.cursor.__exit__(*args)
    def execute(self,sql,params=None):
        self.cursor.execute(sql.replace("public.charlie_",self.schema+".charlie_"),params)
        return self
    def __getattr__(self,key): return getattr(self.cursor,key)


class CoreConnection:
    def __init__(self,connection,schema): self.connection,self.schema=connection,schema
    def __enter__(self): self.connection.__enter__(); return self
    def __exit__(self,*args): return self.connection.__exit__(*args)
    def cursor(self): return CoreCursor(self.connection.cursor(),self.schema)
    def execute(self,sql,params=None): return self.cursor().execute(sql,params)
    def close(self): self.connection.close()


@pytest.fixture
def dbcase(monkeypatch,request):
    info=psycopg.conninfo.conninfo_to_dict(URL)
    assert info.get("host") in {"127.0.0.1","localhost","::1"} and not info.get("hostaddr") and not info.get("service")
    assert info.get("dbname")=="core_manager_intake_test_20261006" or info.get("dbname","").endswith("_test")
    from tests.test_oom_sakkie_general_manager_postgres import SchedulerRecoveryPostgresTests
    h=SchedulerRecoveryPostgresTests(methodName="runTest"); h.setUp()
    h.now -= timedelta(minutes=getattr(request,"param",{}).get("initial_age_minutes",0))
    if getattr(request,"param",{}).get("initial_age_minutes"):
        class ManagerClock(datetime):
            @classmethod
            def now(cls,tz=None): return h.now.astimezone(tz) if tz else h.now.replace(tzinfo=None)
        monkeypatch.setattr(worker,"datetime",ManagerClock)
    original=h.db
    h.db=lambda:CoreConnection(original(),h.schema)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID","42")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","42")
    monkeypatch.delenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON",raising=False)
    monkeypatch.setattr(worker,"build_scheduled_brain_guard_audit",lambda **kw:{"passed":True})
    migrations=Path(__file__).parents[1]/"supabase/migrations"
    with h.db() as db:
        db.execute((migrations/"202606300001_create_charlie_mission_queue.sql").read_text())
        sql=(migrations/"202607170001_create_charlie_executive_control_plane.sql").read_text()
        db.execute(sql.split("insert into public.charlie_delegation_policies")[0])
        sql=(migrations/"202607270003_create_charlie_owner_execution_holds.sql").read_text()
        db.execute(sql.split("create or replace function")[0])
    h.seed([legacy(h.now),legacy(h.now,cluster=True)])
    def _herdmaster(now): return []
    produced=worker.run_general_manager_cycle(now=h.now,source_revision=REVISION,store=h.store,
        collectors=(_herdmaster,),deliver=lambda *a,**kw:pytest.fail("no provider"))
    assert produced["reconciliation_pending"]==2 and produced["exceptions"]==0
    with h.db() as db:
        rows=db.execute("select to_jsonb(m) from app_private.oom_manager_cases m order by case_id").fetchall()
        events=db.execute("select to_jsonb(e) from app_private.oom_manager_case_events e where event_payload ? 'technical_dependency' order by case_id").fetchall()
        deps=[]
        for (case,),(event,) in zip(rows,events):
            proof=event["event_payload"]["technical_dependency"]
            dep={k:proof[k] for k in ("case_id","generation","evidence_digest","evidence_refs_digest","dependency_id")}
            dep.update(anchor_event_id=event["event_id"],anchor_cycle_id=event["event_payload"]["cycle_id"])
            deps.append(dep)
        mission={"mission_id":"CORE-SYNTHETIC-INTAKE","status":"approved","source":"owner_authorized_test",
                 "telegram_user_id":"42","telegram_chat_id":"42","raw_text":"Reconcile manager technical dependencies",
                 "title":"Manager engineering follow-through","urgency":"P1","mission_type":"bug fix",
                 "approval_level":"LEVEL 3","selected_next_step":"Existing governed workflow",
                 "owner_decision":"Synthetic isolated admission","codex_chat_write_status":"",
                 "metadata_json":{"agent_workflow":[{"agent":"source_mapper","status":"pending"}],
                    "mission_control_projection":{"outcome":"Existing outcome","real_life_state":"prepared",
                     "current_worker":"NONE","next_automatic_step":"Existing queue","owner_action":"NONE"}}}
        scope={"contract":intake.CONTRACT,"mission_id":mission["mission_id"],
               "mission_identity_digest":intake.mission_identity_digest(mission),"owner_user_id":"42",
               "owner_binding":intake._mortality_owner_binding(),"producer_revision":REVISION,
               "dependencies":deps,"allowed_effects":list(intake._EFFECTS)}
        policy={"policy_id":"POLICY-SYNTHETIC-INTAKE","capability":intake.CAPABILITY,"scope":scope,
                "authority_tier":"auto","enabled":True,"expires_at":(h.now+timedelta(hours=1)).isoformat(),
                "max_actions":2,"max_cost":0,"rollback_required":True,"deterministic_gate_required":True}
        mission["metadata_json"]["manager_dependency_intake"]={"contract":intake.CONTRACT,"policy_id":policy["policy_id"],
            "scope_digest":intake.digest(scope),"authorization_identity":"synthetic-owner-authority"}
        db.execute("""insert into public.charlie_missions(mission_id,status,source,telegram_user_id,telegram_chat_id,
            raw_text,title,urgency,mission_type,approval_level,selected_next_step,owner_decision,codex_chat_write_status,metadata_json)
            values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            tuple(mission[k] for k in ("mission_id","status","source","telegram_user_id","telegram_chat_id","raw_text",
               "title","urgency","mission_type","approval_level","selected_next_step","owner_decision","codex_chat_write_status"))+(json.dumps(mission["metadata_json"]),))
        db.execute("""insert into public.charlie_delegation_policies(policy_id,capability,scope_json,authority_tier,enabled,
            expires_at,max_actions,max_cost,rollback_required,deterministic_gate_required) values(%s,%s,%s::jsonb,%s,true,%s,2,0,true,true)""",
            (policy["policy_id"],intake.CAPABILITY,json.dumps(scope),"auto",policy["expires_at"]))
    h.policy=policy; h.mission=mission; h.deps=deps; h.rows=rows; h.events=events
    h.connect=lambda _url:h.db()
    try: yield h
    finally: h.doCleanups()


def consume(h,**kwargs):
    return intake.consume_manager_dependencies(mode="active",policies=[h.policy],connect_factory=h.connect,**kwargs)


def snapshot(h):
    with h.db() as db:
        return {"cases":db.execute("select to_jsonb(m) from app_private.oom_manager_cases m order by case_id").fetchall(),
                "commands":db.execute("select to_jsonb(c) from public.charlie_control_commands c order by command_id").fetchall(),
                "findings":db.execute("select to_jsonb(e) from public.charlie_mission_events e order by event_id").fetchall(),
                "manager_events":db.execute("select to_jsonb(e) from app_private.oom_manager_case_events e order by event_id").fetchall(),
                "mission":db.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s",(h.mission["mission_id"],)).fetchone()[0]}


def test_real_producer_receipt_committed_readback_link_and_silent_replay(dbcase):
    h=dbcase; before=snapshot(h); result=consume(h); assert result["failures"]==0,result
    after=snapshot(h)
    assert after["cases"]==before["cases"]
    assert len(after["commands"])==len(after["findings"])==2
    assert len(after["manager_events"])==len(before["manager_events"])+2
    projection=after["mission"]["metadata_json"].pop("mission_control_projection")
    original=before["mission"]["metadata_json"].pop("mission_control_projection")
    assert all(projection[k]==v for k,v in original.items())
    after["mission"].pop("updated_at");before["mission"].pop("updated_at")
    assert after["mission"]==before["mission"]
    stable=snapshot(h); again=consume(h)
    assert again["failures"]==0 and all(r["status"]=="intake_exact_replay" for r in again["results"])
    assert snapshot(h)==stable
    assert all(not r["worker_picked_up"] and not r["repair_verified"] for r in result["results"])


def test_real_default_executive_hook_does_not_need_manual_adapter_call(dbcase,monkeypatch):
    h=dbcase;monkeypatch.setenv("CHARLIE_EXECUTIVE_MODE","active")
    monkeypatch.setattr(executive,"_load_executive_missions",lambda **kw:({"missions":[]},200))
    monkeypatch.setattr(executive,"build_executive_cycle",lambda *a,**kw:{"commands":[],"escalations":[]})
    result,status=executive.run_executive_cycle(connect_factory=h.connect)
    assert status==200 and result["manager_dependency_intake"]["failures"]==0,result
    assert len(snapshot(h)["findings"])==2


@pytest.mark.parametrize("mutation",["no_admission","mission_identity","hold","mission_lease","mission_paused",
    "policy_changed","policy_disabled","policy_expired","budget","owner","case_generation","case_material",
    "case_refs","case_lease","case_expired_lease","case_completed","source_revision","source_cycle_failed"])
def test_current_authority_and_source_fences_fail_without_any_receipt(dbcase,monkeypatch,mutation):
    h=dbcase
    with h.db() as db:
        if mutation=="no_admission": db.execute("update public.charlie_missions set metadata_json=metadata_json-'manager_dependency_intake'")
        elif mutation=="mission_identity": db.execute("update public.charlie_missions set raw_text='Changed work'")
        elif mutation=="mission_lease": db.execute("update public.charlie_missions set metadata_json=metadata_json||%s::jsonb", (json.dumps({"execution_lease":{"worker":"other"}}),))
        elif mutation=="mission_paused": db.execute("update public.charlie_missions set status='paused'")
        elif mutation=="hold": db.execute("""insert into public.charlie_owner_execution_hold_events
            (event_id,hold_id,mission_id,generation_identity,event_type,reason,owner_identity_hash,authorization_identity)
            values('H','H',%s,'g','hold_created','test',%s,%s)""",(h.mission["mission_id"],"a"*64,"b"*64))
        elif mutation=="policy_changed": db.execute("update public.charlie_delegation_policies set scope_json=jsonb_set(scope_json,'{producer_revision}',%s::jsonb)",(json.dumps("e"*40),))
        elif mutation=="policy_disabled": db.execute("update public.charlie_delegation_policies set enabled=false")
        elif mutation=="policy_expired": db.execute("update public.charlie_delegation_policies set expires_at=now()-interval '1 second'")
        elif mutation=="budget":
            # Exhaust only the authoritative command budget, not scope/admission.
            for n in range(2): db.execute("insert into public.charlie_control_commands(command_id,idempotency_key,command_type,authority_tier,policy_id) values(%s,%s,'other','auto',%s)",(str(n),str(n),h.policy["policy_id"]))
        elif mutation=="owner":
            monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID","43");monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS","43")
        elif mutation=="case_generation": db.execute("update app_private.oom_manager_cases set generation=generation+1")
        elif mutation=="case_material": db.execute("update app_private.oom_manager_cases set evidence_digest=%s",("e"*64,))
        elif mutation=="case_refs": db.execute("update app_private.oom_manager_cases set evidence_refs=evidence_refs||%s::jsonb", (json.dumps(["unknown"]),))
        elif mutation in {"case_lease","case_expired_lease"}: db.execute("update app_private.oom_manager_cases set assigned_worker_id='other',lease_until=now()+(%s * interval '1 second')",(10 if mutation=="case_lease" else -10,))
        elif mutation=="case_completed": db.execute("update app_private.oom_manager_cases set status='completed'")
        elif mutation=="source_revision": db.execute("update app_private.oom_manager_worker_cycles set source_revision=%s",("e"*40,))
        elif mutation=="source_cycle_failed": db.execute("update app_private.oom_manager_worker_cycles set status='failed'")
    before=snapshot(h);result=consume(h)
    assert result["failures"]==2,result
    assert snapshot(h)==before


def test_simultaneous_executives_create_one_receipt_each_under_locked_budget(dbcase):
    h=dbcase
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:consume(h),range(2)))
    assert all(r["failures"]==0 for r in results),results
    s=snapshot(h); assert len(s["commands"])==len(s["findings"])==2
    assert s["cases"]==h.rows
    links=[r for r in s["manager_events"] if r[0]["event_payload"].get("engineering_intake")]
    assert len(links)==2


def test_crash_after_core_commit_recovers_link_without_duplicate_finding(dbcase):
    h=dbcase;real=h.connect; calls=[0]
    def crashing(url):
        calls[0]+=1
        if calls[0]==2: raise RuntimeError("synthetic crash before backlink")
        return real(url)
    h.connect=crashing
    result=consume(h)
    assert result["failures"]==1
    first=snapshot(h);assert len(first["findings"])==2
    h.connect=real
    assert consume(h)["failures"]==0
    last=snapshot(h)
    assert last["findings"]==first["findings"] and last["commands"]==first["commands"]
    assert len([r for r in last["manager_events"] if r[0]["event_payload"].get("engineering_intake")])==2


def test_failure_inside_shared_core_transaction_rolls_back_command_and_projection(dbcase,monkeypatch):
    h=dbcase; before=snapshot(h)
    monkeypatch.setattr(intake,"append_mission_control_event",lambda *a,**kw:({"success":False},503))
    assert consume(h)["failures"]==2
    assert snapshot(h)==before


def test_committed_readback_checks_payload_not_only_matching_event_id(dbcase,monkeypatch):
    h=dbcase;real=h.connect;calls=[0]
    def tamper(url):
        calls[0]+=1
        if calls[0]==2:
            with real(url) as db:
                db.execute("update public.charlie_mission_events set metadata_json=jsonb_set(metadata_json,'{summary}',%s::jsonb)", (json.dumps("conflicting fact"),))
        return real(url)
    h.connect=tamper
    result=consume(h)
    assert result["failures"]==1,result
    links=[r for r in snapshot(h)["manager_events"] if r[0]["event_payload"].get("engineering_intake")]
    assert len(links)==1


def test_current_dispatch_outcome_supersedes_old_pending_anchor(dbcase):
    h=dbcase
    with h.db() as db:
        for dep in h.deps:
            db.execute("""insert into app_private.oom_manager_case_events(event_id,case_id,generation,event_type,event_payload)
                values(%s,%s,%s,'delivery_suppressed',%s::jsonb)""",("new-"+dep["case_id"],dep["case_id"],dep["generation"],json.dumps({"outcome_status":"current_work","cycle_id":dep["anchor_cycle_id"]})))
    before=snapshot(h);assert consume(h)["failures"]==2
    assert snapshot(h)==before


def test_policy_revocation_between_core_commit_and_link_does_not_acknowledge(dbcase):
    h=dbcase;real=h.connect;calls=[0]
    def revoke(url):
        calls[0]+=1
        if calls[0]==2:
            with real(url) as db: db.execute("update public.charlie_delegation_policies set enabled=false")
        return real(url)
    h.connect=revoke;result=consume(h)
    assert result["failures"]==2
    s=snapshot(h);assert len(s["findings"])==1
    assert not any(r[0]["event_payload"].get("engineering_intake") for r in s["manager_events"])


def test_superseded_mission_refused_using_existing_replacement_contract(dbcase):
    h=dbcase
    with h.db() as db:
        metadata={"supersession":{"status":"current_contract_replacement","supersedes_mission_id":h.mission["mission_id"]},
                  "orchestration_binding":{"validated":True,"generation_identity":"g2"},
                  "orchestration":{"generation_identity":"g2"}}
        db.execute("""insert into public.charlie_missions(mission_id,raw_text,title,urgency,mission_type,approval_level,metadata_json)
            values('REPLACEMENT','New work','Replacement','P1','bug fix','LEVEL 3',%s::jsonb)""",(json.dumps(metadata),))
    before=snapshot(h); result=consume(h)
    assert result["failures"]==2 and snapshot(h)==before


@pytest.mark.parametrize("column,value",[("command_type","different_action"),("authority_tier","charl_human"),
    ("idempotency_key","different_idempotency")])
def test_readback_rejects_conflicting_semantic_command_columns(dbcase,column,value):
    h=dbcase;real=h.connect;calls=[0]
    def tamper(url):
        calls[0]+=1
        if calls[0]==2:
            with real(url) as db:
                db.execute("update public.charlie_control_commands set "+column+"=%s",(value,))
        return real(url)
    h.connect=tamper; result=consume(h)
    assert result["failures"]>=1,result
    links=[r for r in snapshot(h)["manager_events"] if r[0]["event_payload"].get("engineering_intake")]
    assert not any(r[0]["case_id"]==h.deps[0]["case_id"] for r in links)


def test_policy_expiry_during_final_current_outcome_read_rolls_back(dbcase,monkeypatch):
    import time
    h=dbcase
    with h.db() as db:
        expires=db.execute("update public.charlie_delegation_policies set expires_at=clock_timestamp()+interval '0.4 seconds' returning expires_at").fetchone()[0]
    h.policy["expires_at"]=expires.isoformat()
    execute=CoreCursor.execute
    def delayed(self,sql,params=None):
        result=execute(self,sql,params)
        if "order by e.occurred_at desc,e.event_id desc limit 1" in sql: time.sleep(0.5)
        return result
    monkeypatch.setattr(CoreCursor,"execute",delayed)
    before=snapshot(h);result=consume(h)
    assert result["failures"]==2,result
    assert snapshot(h)==before


def test_shared_deadline_stops_between_commit_and_link_then_recovers(dbcase,monkeypatch):
    h=dbcase; real=h.connect; calls=[0]
    clock=[0.0]
    monkeypatch.setattr(intake.time,"monotonic",lambda:clock[0])
    # The existing connection acquisition rail uses this same monotonic clock;
    # advance only after an immediate successful connection has been acquired.
    original=intake._open
    def expire_after_open(url,factory,deadline):
        result=original(url,factory,deadline);calls[0]+=1
        if calls[0]==2: clock[0]=11.0
        return result
    monkeypatch.setattr(intake,"_open",expire_after_open)
    result=consume(h)
    assert result["failures"]==2
    first=snapshot(h); assert len(first["findings"])==1
    assert not any(r[0]["event_payload"].get("engineering_intake") for r in first["manager_events"])
    monkeypatch.setattr(intake,"_open",original)
    assert consume(h)["failures"]==0
    last=snapshot(h)
    assert len(last["findings"])==2 and len(last["commands"])==2
    assert last["cases"]==first["cases"]


def test_foreign_mission_owner_cannot_borrow_current_owner_hash(dbcase):
    h=dbcase
    with h.db() as db:
        db.execute("update public.charlie_missions set telegram_user_id='43',telegram_chat_id='43'")
        mission=db.execute("select to_jsonb(m) from public.charlie_missions m").fetchone()[0]
        scope=h.policy["scope"]; scope["owner_user_id"]="43";scope["mission_identity_digest"]=intake.mission_identity_digest(mission)
        admission={"contract":intake.CONTRACT,"policy_id":h.policy["policy_id"],"scope_digest":intake.digest(scope),"authorization_identity":"synthetic-owner-authority"}
        db.execute("update public.charlie_missions set metadata_json=jsonb_set(metadata_json,'{manager_dependency_intake}',%s::jsonb)",(json.dumps(admission),))
        db.execute("update public.charlie_delegation_policies set scope_json=%s::jsonb",(json.dumps(scope),))
    before=snapshot(h);assert consume(h)["failures"]==2;assert snapshot(h)==before


def test_later_natural_pending_events_do_not_replace_frozen_intake_anchor(dbcase):
    h=dbcase; assert consume(h)["failures"]==0;before=snapshot(h)
    # An additional genuine typed event for the same obligation is not another
    # engineering mission or another finding. The first admitted anchor stays.
    with h.db() as db:
        for (event,) in h.events:
            db.execute("""insert into app_private.oom_manager_case_events(event_id,case_id,generation,event_type,event_payload)
                values(%s,%s,%s,%s,%s::jsonb)""",("later-"+event["event_id"],event["case_id"],event["generation"],event["event_type"],json.dumps(event["event_payload"])))
    assert consume(h)["failures"]==0
    after=snapshot(h)
    assert before["commands"]==after["commands"] and before["findings"]==after["findings"]
    assert len([r for r in after["manager_events"] if r[0]["event_payload"].get("engineering_intake")])==2


@pytest.mark.parametrize("dbcase",[{"initial_age_minutes":6}],indirect=True)
def test_actual_later_manager_cycle_preserves_backlinked_dependency_and_replay(dbcase):
    h=dbcase
    assert consume(h)["failures"]==0
    before=snapshot(h)
    h.now=datetime.now(timezone.utc)
    def _herdmaster(now): return []
    result=worker.run_general_manager_cycle(now=h.now,source_revision=REVISION,store=h.store,
        collectors=(_herdmaster,),deliver=lambda *a,**kw:pytest.fail("no historical notice or farm effect"))
    assert result["reconciliation_pending"]==2 and result["exceptions"]==0
    assert result["deliveries_confirmed"]==0
    after=snapshot(h)
    for (old,),(current,) in zip(before["cases"],after["cases"]):
        for field in ("case_id","generation","evidence_digest","evidence_refs","summary","next_action","last_delivery_digest","last_delivery_at"):
            assert old[field]==current[field]
        assert current["status"]=="waiting_reassessment"
        assert datetime.fromisoformat(current["next_reassessment_at"])==h.now+worker.CADENCE
    old_events={v[0]["event_id"]:v[0] for v in before["manager_events"]}
    new_events={v[0]["event_id"]:v[0] for v in after["manager_events"]}
    assert all(new_events[key]==value for key,value in old_events.items())
    proofs=[e["event_payload"]["technical_dependency"] for e in new_events.values() if e["event_payload"].get("technical_dependency")]
    assert len(proofs)==4 and len({p["dependency_id"] for p in proofs})==2
    assert all(p["core_acknowledged"] is False and p["completion_proven"] is False for p in proofs)
    assert not any(e["event_type"] in {"delivery_confirmed","completed"} for e in new_events.values())
    assert consume(h)["failures"]==0
    final=snapshot(h)
    assert final==after
