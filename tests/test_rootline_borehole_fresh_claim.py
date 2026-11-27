"""Fresh V4 claim proof across the observed slow-read/reserve path; no live IO."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from modules.telemetry import rootline_borehole_commissioning as borehole
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry.rootline_cycle_budget import CYCLE_WORK_SECONDS

OBSERVED=datetime.fromisoformat("2026-11-15T19:59:38.907420+00:00")
ASSESSED=datetime.fromisoformat("2026-11-15T19:59:47.029382+00:00")
FINAL=datetime.fromisoformat("2026-11-15T20:00:24+00:00")
RESERVED=datetime.fromisoformat("2026-11-15T20:00:39+00:00")
CLAIMED=datetime.fromisoformat("2026-11-15T20:00:44+00:00")


def proof(at, state="OFF"):
    return {"authoritative":True,"state":state,"device_id":"1002851416","channel":1,
        "evidence_id":"a"*64,"retrieved_at":at.isoformat(),"borehole_configuration":{"online":True}}


def eligibility():
    return borehole.build_borehole_runtime_eligibility(need={"eligible":True},
        baseline={"current":True,"stop_mode":"scheduled","device_key":borehole.DEVICE_KEY,
            "maximum_routine_runtime_seconds":14400,"native_fail_stop_seconds":0,
            "baseline_sha256":"b"*64,"registry_generation":5},
        authority={"inside_standing_authority":True},provider=proof(OBSERVED),
        interlocks={},energy={"eligible":True},requested_seconds=14400,now=ASSESSED)


def body(artifact, *, claimed=FINAL, observed=FINAL, separate=True):
    value={**deepcopy(artifact),"state":"claimed","claimed_at":claimed.isoformat(),
        "primary_stop_deadline":(claimed+timedelta(hours=4)).isoformat(),
        "native_fail_stop_deadline":None,"on_attempts":0,"off_attempts":0}
    if separate:value["claim_provider_evidence"]={**proof(observed),"execution_id":artifact["execution_id"]}
    return value


class ClaimDatabase:
    """Replace DB boundary only; use the actual locked claim validation path."""
    def __init__(self, monkeypatch, artifact, at=CLAIMED):
        self.artifact=deepcopy(artifact);self.now=at;self.records=[];self.queries=[]
        backend=self
        class Cursor:
            rowcount=0
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def execute(self,sql,args=None):
                self.sql=sql;backend.queries.append(sql)
                if sql.lstrip().startswith("insert"):
                    event=json.loads(args[-1])["rootline_execution"]
                    self.rowcount=int(not any(row.get("event_id")==event["event_id"] for row in backend.records))
                    if self.rowcount:backend.records.append(event)
                return self
            def fetchone(self):
                if "clock_timestamp" in self.sql:return (backend.now,)
                if "record_borehole_eligibility" in self.sql:return (deepcopy(backend.artifact),)
                return None
            def fetchall(self):
                if "rootline_operational_intake" in self.sql:return []
                return [(deepcopy(row),) for row in backend.records]
        class Connection:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def cursor(self):return Cursor()
        self.connection = Connection
        monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
            lambda **_:Connection())
        monkeypatch.setattr(store,"_borehole_state_rows",lambda _:deepcopy(backend.records))


def test_observed_latency_uses_final_off_without_rewriting_eligibility_or_deadlines(monkeypatch):
    artifact=eligibility();original=deepcopy(artifact);db=ClaimDatabase(monkeypatch,artifact)
    clock=[FINAL];calls=[];claims=[]
    class Transport:
        state="OFF"
        def read_output_state(self,**_):return proof(clock[0],self.state)
        def prepare_execution_capacity(self,execution):
            claims.append(deepcopy(execution));clock[0]=RESERVED
            return "synthetic-unchanged-capacity-permit"
        def set_state(self,**kwargs):
            calls.append(kwargs);self.state=kwargs["state"]
            return {"accepted_unambiguous":True}
    def canonical(action,payload):
        if action=="load_active_borehole":return None
        if action=="claim_borehole_before_on":
            clock[0]=CLAIMED
            return store._claim_borehole_material_load(payload)
        if action=="dispatch_borehole_on_edge":return {**payload["dispatch"](),"provider_command_attempted":True}
        return {"success":True,"created":True}
    result=borehole.advance_borehole_execution(eligibility=artifact,store=canonical,
        transport=Transport(),now=FINAL,clock=lambda:clock[0])
    assert result["status"]=="borehole_started" and result["hardware_commands"]==1
    persisted=db.records[0]
    assert artifact==original and persisted["provider_evidence"]==original["provider_evidence"]
    assert persisted["eligibility_sha256"]==original["eligibility_sha256"]
    assert persisted["claim_provider_evidence"]=={**proof(FINAL),"execution_id":artifact["execution_id"]}
    assert "claimed_at" not in claims[0] and "primary_stop_deadline" not in claims[0]
    assert persisted["claimed_at"]==RESERVED.isoformat()
    assert persisted["primary_stop_deadline"]==(RESERVED+timedelta(hours=4)).isoformat()
    assert persisted["native_fail_stop_deadline"] is None
    assert [call["state"] for call in calls]==["ON"]
    assert any("pg_advisory_xact_lock" in sql for sql in db.queries)


@pytest.mark.parametrize("elapsed,created",[(30,True),(30.000001,False)])
def test_final_off_freshness_boundary_remains_exact(monkeypatch,elapsed,created):
    artifact=eligibility();ClaimDatabase(monkeypatch,artifact,FINAL+timedelta(seconds=elapsed))
    result=store._claim_borehole_material_load(body(artifact))
    assert result["created"] is created
    if not created:assert result["status"]=="borehole_current_observation_unproven"


@pytest.mark.parametrize("elapsed,created",[(CYCLE_WORK_SECONDS,True),(CYCLE_WORK_SECONDS+.000001,False)])
def test_fresh_proof_cannot_revive_planning_beyond_existing_cycle_ceiling(monkeypatch,elapsed,created):
    artifact=eligibility();ClaimDatabase(monkeypatch,artifact,ASSESSED+timedelta(seconds=elapsed))
    result=store._claim_borehole_material_load(body(artifact,
        claimed=ASSESSED+timedelta(seconds=131),observed=ASSESSED+timedelta(seconds=130)))
    assert result["created"] is created


@pytest.mark.parametrize("mutation",["none","wrong_execution","wrong_device","wrong_channel","on","unknown","future","before_assessed"])
def test_separate_proof_is_exact_bound_current_off_not_a_stale_positive(monkeypatch,mutation):
    artifact=eligibility();ClaimDatabase(monkeypatch,artifact);value=body(artifact)
    field=value["claim_provider_evidence"]
    if mutation=="none":value["claim_provider_evidence"]=None
    elif mutation=="wrong_execution":field["execution_id"]="OTHER"
    elif mutation=="wrong_device":field["device_id"]="OTHER"
    elif mutation=="wrong_channel":field["channel"]=2
    elif mutation in {"on","unknown"}:field["state"]=mutation.upper()
    elif mutation=="future":field["retrieved_at"]=(CLAIMED+timedelta(seconds=1)).isoformat()
    else:field["retrieved_at"]=(ASSESSED-timedelta(microseconds=1)).isoformat()
    result=store._claim_borehole_material_load(value)
    assert result=={"success":False,"created":False,"status":"borehole_current_observation_unproven"}


def test_original_provider_packet_and_digest_remain_immutable(monkeypatch):
    artifact=eligibility();ClaimDatabase(monkeypatch,artifact);value=body(artifact)
    value["provider_evidence"]["retrieved_at"]=FINAL.isoformat()
    assert store._claim_borehole_material_load(value)["status"]=="canonical_borehole_eligibility_unproven"


@pytest.mark.parametrize("at,created",[(OBSERVED+timedelta(seconds=30),True),(OBSERVED+timedelta(seconds=30.000001),False)])
def test_legacy_scheduled_claim_without_new_field_keeps_original_freshness(monkeypatch,at,created):
    artifact=eligibility();ClaimDatabase(monkeypatch,artifact,at)
    assert store._claim_borehole_material_load(body(artifact,claimed=at,separate=False))["created"] is created


def test_existing_owned_claim_and_dispatch_field_matching_prevent_duplicates(monkeypatch):
    artifact=eligibility();db=ClaimDatabase(monkeypatch,artifact);value=body(artifact)
    assert store._claim_borehole_material_load(value)["created"]
    assert store._claim_borehole_material_load(value)["status"]=="material_load_active"
    assert len(db.records)==1
    family=store._managed_family(borehole=True)
    assert store._managed_claim_matches(db.records,value,family)
    changed=deepcopy(value);changed["claim_provider_evidence"]["retrieved_at"]=CLAIMED.isoformat()
    assert not store._managed_claim_matches(db.records,changed,family)
    changed=deepcopy(value);changed["primary_stop_deadline"]=(FINAL+timedelta(hours=5)).isoformat()
    assert not store._managed_claim_matches(db.records,changed,family)


@pytest.mark.parametrize("state",["ON","Unknown"])
def test_final_unowned_on_or_unknown_is_not_restarted_adopted_or_turned_off(state):
    calls=[]
    class Transport:
        def read_output_state(self,**_):return proof(FINAL,state)
        def prepare_execution_capacity(self,_):pytest.fail("no reserve for unowned output")
        def set_state(self,**_):pytest.fail("no command for unowned output")
    def canonical(action,payload):calls.append(action);assert action=="load_active_borehole"
    result=borehole.advance_borehole_execution(eligibility=eligibility(),store=canonical,
        transport=Transport(),now=FINAL,clock=lambda:FINAL)
    assert result["status"]=="borehole_current_off_unproven" and result["hardware_commands"]==0
    assert calls==["load_active_borehole"]


@pytest.mark.parametrize("reason,success",[("borehole_current_observation_unproven",False),
    ("canonical_borehole_eligibility_unproven",False),("material_load_active",True),
    ("execution_replay",True),("untrusted details",False)])
def test_coordinator_exposes_only_bounded_real_refusal_and_truthful_success(reason,success):
    class Transport:
        def read_output_state(self,**_):return proof(FINAL)
        def set_state(self,**_):pytest.fail("claim refused")
    def canonical(action,payload):
        if action=="load_active_borehole":return None
        assert action=="claim_borehole_before_on"
        return {"success":success,"created":False,"status":reason}
    result=borehole.advance_borehole_execution(eligibility=eligibility(),store=canonical,
        transport=Transport(),now=FINAL,clock=lambda:FINAL)
    assert result["status"]==(reason if reason!="untrusted details" else "borehole_claim_conflict")
    assert result["success"] is success and result["hardware_commands"]==0


def test_slow_reservation_does_not_refresh_stale_off_proof(monkeypatch):
    artifact=eligibility();db=ClaimDatabase(monkeypatch,artifact,FINAL+timedelta(seconds=31));clock=[FINAL];captured=[]
    class Transport:
        def read_output_state(self,**_):return proof(FINAL)
        def prepare_execution_capacity(self,execution):clock[0]=FINAL+timedelta(seconds=31);return "permit"
        def set_state(self,**_):pytest.fail("expired startup must not send")
    def canonical(action,payload):
        if action=="load_active_borehole":return None
        assert action=="claim_borehole_before_on";captured.append(deepcopy(payload))
        return store._claim_borehole_material_load(payload)
    result=borehole.advance_borehole_execution(eligibility=artifact,store=canonical,
        transport=Transport(),now=FINAL,clock=lambda:clock[0])
    assert result["status"]=="borehole_current_observation_unproven" and result["success"] is False
    assert captured[0]["claimed_at"]==(FINAL+timedelta(seconds=31)).isoformat()
    assert captured[0]["primary_stop_deadline"]==(FINAL+timedelta(seconds=31,hours=4)).isoformat()
    assert captured[0]["claim_provider_evidence"]["retrieved_at"]==FINAL.isoformat()
    assert db.records==[]


@pytest.mark.parametrize("sender_second,on_sent",[(52,True),(54,False),(67,False)])
def test_complete_shared_claim_dispatch_and_budget_sender_keep_actual_timing_bounds(monkeypatch,sender_second,on_sent):
    import datetime as datetime_module
    import time as time_module
    from modules.telemetry import rootline_ewelink_request_budget as budget
    from modules.telemetry.rootline_cycle_budget import cycle_budget
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from tests.test_rootline_ewelink_request_budget import MemoryBudget,ENV
    artifact=eligibility();db=ClaimDatabase(monkeypatch,artifact)
    source={**ENV,"ROOTLINE_TIMED_CONTROL_ENABLED":"true","ROOTLINE_BOREHOLE_ENABLED":"true",
        "ROOTLINE_IFTTT_MAKER_KEY":"synthetic-offline-only"}
    client=MemoryBudget(environ=source);client.backend.now=FINAL
    monkeypatch.setattr(budget,"RequestBudget",lambda *_args,**_kwargs:client)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return client.backend.now.astimezone(tz or timezone.utc)
    monkeypatch.setattr(datetime_module,"datetime",Clock)
    monkeypatch.setattr(time_module,"monotonic",lambda:client.backend.now.timestamp())
    commands=[];edge_results=[];edges=[0]
    actual_rows=store._managed_edge_rows
    def edge_rows(cursor,identity):
        # Claim at44; first dispatch transaction at46; final fenced dispatch
        # at the selected time. DB phase durations after reserve are modeled.
        if edges[0]<2:
            edges[0]+=1
            client.backend.now=datetime.fromisoformat("2026-11-15T20:00:00+00:00")+timedelta(
                seconds=46 if edges[0]==1 else sender_second)
            db.now=client.backend.now
        return actual_rows(cursor,identity)
    monkeypatch.setattr(store,"_managed_edge_rows",edge_rows)
    original_append=client._append
    def append(state,**kwargs):
        original_append(state,**kwargs)
        if kwargs["action"]=="active_duty_on_attempt_reserved":
            client.backend.advance(2.126005)  # measured reservation audit duration reused as modeled final audit cost
    client._append=append
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def getcode(self):return 200
        def read(self,*_):return b"OK"
    def send(request,**_):
        commands.append({"state":"ON" if "/borehole_1_on/" in request.full_url else "OFF",
            "at":client.backend.now.isoformat()})
        return Response()
    class Tokens:
        def latest(self):return {"region":"eu"}
    class Transport(RootlineIFTTTTransport):
        def read_output_state(self,**_):
            return proof(client.backend.now,commands[-1]["state"] if commands else "OFF")
        def prepare_execution_capacity(self,execution):
            assert "claimed_at" not in execution and "primary_stop_deadline" not in execution
            client.backend.now=datetime.fromisoformat("2026-11-15T20:00:36.318299+00:00")
            value=super().prepare_execution_capacity(execution)
            client.backend.now=datetime.fromisoformat("2026-11-15T20:00:38.444304+00:00")
            return value
    def canonical(action,payload):
        if action=="load_active_borehole":return None
        if action=="claim_borehole_before_on":
            client.backend.now=db.now=CLAIMED
            return store._claim_borehole_material_load(payload)
        if action=="dispatch_borehole_on_edge":
            result=store._dispatch_managed_on_edge(payload,borehole=True);edge_results.append(result)
            return result
        if action=="record_borehole_on_outcome":
            return store._insert_managed_event(db.connection().cursor(),action,payload)
        if action=="mark_borehole_active":return store._guarded_managed_transition(action,payload)
        if action=="load_borehole_off_attempts":return []
        if action=="dispatch_borehole_off_edge":return store._dispatch_borehole_off_edge(payload)
        if action=="retire_not_dispatched_execution":return {"success":False,"status":"synthetic_terminal_not_proven"}
        raise AssertionError(action)
    invocation=datetime.fromisoformat("2026-11-15T19:58:35.532639+00:00")
    with cycle_budget(invocation.timestamp()+140):
        result=borehole.advance_borehole_execution(eligibility=artifact,store=canonical,
            transport=Transport(token_store=Tokens(),environ=source,http_open=send),now=FINAL,
            clock=lambda:client.backend.now)
    claim=next(row for row in db.records if row["action"]=="claim_borehole_before_on")
    assert claim["claimed_at"]=="2026-11-15T20:00:38.444304+00:00"
    assert claim["primary_stop_deadline"]=="2026-11-16T00:00:38.444304+00:00"
    assert claim["provider_evidence"]==artifact["provider_evidence"]
    assert claim["claim_provider_evidence"]["retrieved_at"]==FINAL.isoformat()
    reserve=client.backend.state["reserves"][artifact["execution_id"]]
    assert reserve["reserved_at"]=="2026-11-15T20:00:36.318299+00:00"
    assert reserve["admit_until"]=="2026-11-15T20:01:06.318299+00:00"
    assert sum(row["state"]=="ON" for row in commands)==int(on_sent)
    if on_sent:
        assert result["status"]=="borehole_started"
        assert commands==[{"state":"ON","at":"2026-11-15T20:00:54.126005+00:00"}]
        active=next(row for row in db.records if row["action"]=="mark_borehole_active")
        assert active["claimed_at"]==claim["claimed_at"] and active["primary_stop_deadline"]==claim["primary_stop_deadline"]
        assert datetime.fromisoformat(commands[0]["at"])<invocation+timedelta(seconds=140)
    else:
        assert edge_results[0]["provider_command_attempted"] is False
        assert edge_results[0]["status"]==("provider_command_deadline_reached" if sender_second==54 else "provider_capacity_not_available")
        assert not any(row["action"]=="mark_borehole_active" for row in db.records)
    print("FULL_SHARED_BOREHOLE_EDGE",{"sender_second":sender_second,"on_sent":on_sent,
        "claim_at":claim["claimed_at"],"stop_at":claim["primary_stop_deadline"],
        "permit_until":reserve["admit_until"],"commands":commands,"edge_result":edge_results[0]})
