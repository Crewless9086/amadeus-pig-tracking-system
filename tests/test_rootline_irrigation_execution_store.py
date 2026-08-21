from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import uuid
import json

import pytest

from modules.telemetry.rootline_irrigation_execution_store import (
    _claim_single_auxiliary, _claim_irrigation_output, _daily_dispatch_blocker,
    _event_id, _stored_event_body, _terminal_closes_active,
    _is_active_candidate, _verified_borehole_completion,
    _claim_borehole_material_load, RootlineExecutionStoreUnavailable,
    rootline_irrigation_execution_store,
)


class BoundedFailure(Exception):
    __module__="psycopg.errors"


def test_unverified_irrigation_containment_remains_recoverable_active_truth():
    assert _terminal_closes_active({"action":"contain_zone",
        "shutdown_verified":False}) is False
    assert _terminal_closes_active({"action":"record_ambiguous_shutdown",
        "shutdown_verified":False}) is False
    assert _terminal_closes_active({"action":"record_claim_recovery",
        "shutdown_verified":True}) is True
    assert _terminal_closes_active({"action":"record_completed"}) is True
    assert _terminal_closes_active({"action":"contain_auxiliary_device",
        "shutdown_verified":False},auxiliary=True) is False
    assert _terminal_closes_active({"action":"contain_auxiliary_device",
        "shutdown_verified":True},auxiliary=True) is True
    assert _terminal_closes_active({
        "action":"record_auxiliary_control_pulse_stopped"},auxiliary=True) is True


def _borehole_completion(execution_id="BOREHOLE-1"):
    return {"action":"record_borehole_completed","execution_id":execution_id,
        "shutdown_verified":True,
        "canonical_completion_evidence":{"evidence_id":"CANON-1",
            "execution_id":execution_id,"final_state":"OFF"},
        "provider_final_off_evidence":{"evidence_id":"PROVIDER-1",
            "execution_id":execution_id,"authoritative":True,"state":"OFF"},
        "physical_completion_evidence":{"evidence_id":"PHYSICAL-1",
            "execution_id":execution_id,"pump_stopped":True,"water_flow_stopped":True}}


def test_borehole_completion_requires_bound_canonical_provider_physical_final_off():
    complete=_borehole_completion()
    assert _verified_borehole_completion(complete) is True
    assert _terminal_closes_active(complete,borehole=True) is True
    for field in ("canonical_completion_evidence","provider_final_off_evidence",
                  "physical_completion_evidence"):
        incomplete={**complete,field:{}}
        assert _verified_borehole_completion(incomplete) is False
        assert _terminal_closes_active(incomplete,borehole=True) is False
    assert _terminal_closes_active({**complete,"shutdown_verified":False},borehole=True) is False
    mismatched={**complete,"provider_final_off_evidence":{
        **complete["provider_final_off_evidence"],"execution_id":"OTHER"}}
    assert _terminal_closes_active(mismatched,borehole=True) is False


def test_borehole_claim_and_off_identities_are_replay_stable_and_attempt_bounded():
    claim=_event_id("claim_borehole_before_on",{"execution_id":"BH-1"})
    assert claim==_event_id("claim_borehole_before_on",{
        "execution_id":"BH-1","untrusted_extra":"ignored"})
    attempts={_event_id("claim_borehole_off_attempt",{
        "execution_id":"BH-1","attempt":attempt}) for attempt in (1,2,3)}
    assert len(attempts)==3


class FailedConnection:
    def __init__(self): self.closed=False
    def __enter__(self): return self
    def __exit__(self,*args): self.closed=True; return False
    def cursor(self): raise BoundedFailure("statement timeout")


def test_active_history_bounded_read_failure_is_not_interpreted_as_empty(monkeypatch):
    calls=[];connection=FailedConnection()
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
        lambda **kwargs:(calls.append(kwargs) or connection))
    with pytest.raises(RootlineExecutionStoreUnavailable,match="load_active"):
        rootline_irrigation_execution_store("load_active",None)
    assert len(calls)==1 and connection.closed is True


@pytest.mark.parametrize("failure_name",["OperationalError","ConnectionTimeout","PoolTimeout","QueryCanceled","LockNotAvailable"])
def test_connection_pool_and_query_deadlines_fail_closed(monkeypatch,failure_name):
    failure=type(failure_name,(Exception,),{"__module__":"psycopg.errors"})
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
        lambda **kwargs:(_ for _ in ()).throw(failure(failure_name)))
    with pytest.raises(RootlineExecutionStoreUnavailable,match="load_active"):
        rootline_irrigation_execution_store("load_active",None)


def test_real_connect_stall_is_bounded_before_execution_truth_can_become_empty(monkeypatch):
    import time
    monkeypatch.setenv("DATABASE_URL","postgresql://stalled")
    monkeypatch.setattr(
        "modules.oom_sakkie.bounded_postgres_read.ROOTLINE_CONNECT_DEADLINE_SECONDS",.03)
    monkeypatch.setattr("psycopg.connect",
        lambda *_args,**_kwargs:(time.sleep(.2),None)[1])
    started=time.monotonic()
    with pytest.raises(RootlineExecutionStoreUnavailable,match="load_job_events"):
        rootline_irrigation_execution_store("load_job_events","JOB-UNCONSUMED")
    assert time.monotonic()-started < .12


def test_store_recovers_cleanly_after_database_availability_returns(monkeypatch):
    class EmptyCursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,*args):pass
        def fetchall(self):return []
    class EmptyConnection:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def cursor(self):return EmptyCursor()
    attempts=iter([FailedConnection(),EmptyConnection()])
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
        lambda **kwargs:next(attempts))
    with pytest.raises(RootlineExecutionStoreUnavailable):
        rootline_irrigation_execution_store("load_active",None)
    assert rootline_irrigation_execution_store("load_active",None) is None


def test_mandatory_eligibility_write_timeout_becomes_typed_degraded_boundary(monkeypatch):
    monkeypatch.setattr(
        "modules.sales.sam_live_stock_launch_control.record_sam_live_stock_review_event",
        lambda *args,**kwargs:({"success":False,"error_type":"QueryCanceled"},500))
    with pytest.raises(RootlineExecutionStoreUnavailable,match="record_eligibility"):
        rootline_irrigation_execution_store("record_eligibility",{
            "execution_id":"EXEC-BOUNDED-WRITE"})


def test_on_claim_identity_is_atomic_and_stable_across_replay():
    first = _event_id("claim_before_on", {"execution_id": "EXEC-1", "zone_id": "B12345"})
    replay = _event_id("claim_before_on", {"execution_id": "EXEC-1", "zone_id": "B12345",
                                            "untrusted_extra": "ignored"})
    other = _event_id("claim_before_on", {"execution_id": "EXEC-2", "zone_id": "B12345"})
    assert first == replay and first != other


def test_off_attempt_claims_are_unique_per_execution_and_attempt():
    identities = {_event_id("claim_off_attempt", {"execution_id": "EXEC-1", "attempt": n})
                  for n in (1, 2, 3)}
    assert len(identities) == 3
    assert _event_id("claim_off_attempt", {"execution_id": "EXEC-1", "attempt": 1}) in identities


def test_store_action_cannot_be_shadowed_by_loaded_active_payload():
    value=_stored_event_body("record_completed",{
        "execution_id":"EXEC-1","action":"mark_active","state":"Completed"},"EVENT-1")
    assert value["action"]=="record_completed"
    assert value["event_id"]=="EVENT-1"


def test_completed_shaped_mark_active_is_not_an_active_candidate():
    assert not _is_active_candidate(
        {"action":"mark_active","state":"Completed"},"mark_active","claim_before_on")
    assert _is_active_candidate(
        {"action":"mark_active","state":"Active"},"mark_active","claim_before_on")
    assert _is_active_candidate(
        {"action":"claim_before_on","state":"claimed"},"mark_active","claim_before_on")


def test_typed_history_append_call_casts_numeric_runtime_arguments():
    source=Path("modules/telemetry/rootline_irrigation_execution_store.py").read_text(encoding="utf-8")
    assert "%s::numeric,%s::numeric,%s::jsonb" in source


class DailyCursor:
    def __init__(self, answers, rows=()): self.answers=iter(answers); self.rows=rows; self.sql=[]
    def execute(self, statement, params=None): self.sql.append((statement,params))
    def fetchone(self): return next(self.answers)
    def fetchall(self): return self.rows


def test_daily_guard_requires_persisted_exact_eligibility_before_completion_checks():
    cursor=DailyCursor([None])
    status=_daily_dispatch_blocker(cursor,execution_id="EXEC-1",eligibility_id="ELIG-1",
        eligibility_sha256="a"*64,zone_id="B12345",operating_date="2026-08-12")
    assert status=="canonical_eligibility_unproven" and len(cursor.sql)==1


def test_daily_guard_rejects_existing_verified_completion_before_provider_on(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_history.project_canonical_irrigation_history",
        lambda rows,snapshot_cutoff:{"zones":{"B12345":{"verified_completed_days":["2026-08-12"]}}})
    cursor=DailyCursor([(1,),(datetime(2026,8,12,tzinfo=timezone.utc),)])
    status=_daily_dispatch_blocker(cursor,execution_id="EXEC-2",eligibility_id="ELIG-2",
        eligibility_sha256="b"*64,zone_id="B12345",operating_date="2026-08-12")
    assert status=="zone_daily_completion_already_credited" and len(cursor.sql)==3


def test_daily_guard_rejects_prior_accepted_on_during_delayed_completion_window(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_history.project_canonical_irrigation_history",
        lambda rows,snapshot_cutoff:{"zones":{"B12345":{"verified_completed_days":[]}}})
    cursor=DailyCursor([(1,),(datetime(2026,8,12,tzinfo=timezone.utc),),(1,)])
    status=_daily_dispatch_blocker(cursor,execution_id="EXEC-2",eligibility_id="ELIG-2",
        eligibility_sha256="b"*64,zone_id="B12345",operating_date="2026-08-12")
    assert status=="zone_daily_on_already_accepted" and len(cursor.sql)==4


def test_daily_guard_allows_other_zone_or_day_when_all_atomic_checks_are_clear(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_history.project_canonical_irrigation_history",
        lambda rows,snapshot_cutoff:{"zones":{"C12345":{"verified_completed_days":[]}}})
    cursor=DailyCursor([(1,),(datetime(2026,8,12,tzinfo=timezone.utc),),None])
    assert _daily_dispatch_blocker(cursor,execution_id="EXEC-C",eligibility_id="ELIG-C",
        eligibility_sha256="c"*64,zone_id="C12345",operating_date="2026-08-13") is None


def test_later_job_segment_requires_verified_off_rearm():
    missing=DailyCursor([(1,),None])
    status=_daily_dispatch_blocker(missing,execution_id="EXEC-2",eligibility_id="ELIG-2",
        eligibility_sha256="b"*64,zone_id="B12345",operating_date="2026-08-14",
        job_id="JOB-1",segment_number=2)
    assert status=="prior_segment_off_rearm_unproven"
    ready=DailyCursor([(1,),(1,),None])
    assert _daily_dispatch_blocker(ready,execution_id="EXEC-2",eligibility_id="ELIG-2",
        eligibility_sha256="b"*64,zone_id="B12345",operating_date="2026-08-14",
        job_id="JOB-1",segment_number=2) is None


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
                    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_persisted_second_segment_claim_is_concurrent_single_use(monkeypatch):
    import psycopg
    from modules.telemetry.rootline_irrigation_execution_store import (
        rootline_irrigation_execution_store,
    )
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]; monkeypatch.setenv("DATABASE_URL",url)
    migration=Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql")
    history=Path("supabase/migrations/202605230001_create_irrigation_tables.sql")
    with psycopg.connect(url) as connection:
        connection.execute(history.read_text(encoding="utf-8"))
        connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex; job=f"ROOTLINE-JOB-{suffix}"; execution=f"EXEC-2-{suffix}"
    eligibility=f"ELIG-2-{suffix}"; digest="b"*64; consumption=f"ROOTLINE-BC-{suffix}"
    prior={"action":"record_completed","execution_id":f"EXEC-1-{suffix}","job_id":job,
        "segment_number":1,"state":"Completed","verified_runtime_seconds":3599,
        "shutdown_verified":True,"rearm_readback_off":True}
    artifact={"action":"record_eligibility","execution_id":execution,
        "eligibility_id":eligibility,"eligibility_sha256":digest,"operating_date":"2026-08-14",
        "zone_id":"B12345","job_id":job,"segment_number":2,
        "predecessor_off_rearm_verified":True}
    with psycopg.connect(url) as connection:
        for event_id,payload,action in ((f"PRIOR-{suffix}",prior,"record_completed"),
                                        (f"ELIG-{suffix}",artifact,"record_eligibility")):
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
                values (%s,%s,'rootline_irrigation_execution',%s,%s::jsonb)""",
                (event_id,execution,action,json.dumps({"rootline_execution":payload})))
    body={"execution_id":execution,"eligibility_id":eligibility,"eligibility_sha256":digest,
        "consumption_key":consumption,"zone_id":"B12345","operating_date":"2026-08-14",
        "job_id":job,"segment_number":2}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:_claim_irrigation_output(body),(1,2)))
    assert sum(row.get("created") is True for row in results)==1
    assert rootline_irrigation_execution_store("load_job_events",job)[0]["segment_number"]==1
    replay=_claim_irrigation_output(body)
    assert replay["created"] is False and replay["status"]=="execution_replay"
    # Close this synthetic active claim so the shared disposable database does
    # not correctly block the next test as an already-owned controller.
    with psycopg.connect(url) as connection:
        connection.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
            values (%s,%s,'rootline_irrigation_execution','record_completed',%s::jsonb)""",
            (f"TERMINAL-{suffix}",execution,json.dumps({"rootline_execution":{
                "action":"record_completed","execution_id":execution,
                "job_id":job,"segment_number":2,"state":"Completed",
                "shutdown_verified":True}})))


def test_auxiliary_claim_and_off_identities_are_stable_and_separate():
    claim=_event_id("claim_auxiliary_before_on",{"execution_id":"AUX-1"})
    assert claim==_event_id("claim_auxiliary_before_on",{
        "execution_id":"AUX-1","untrusted_extra":"ignored"})
    assert _event_id("claim_auxiliary_off_attempt",{
        "execution_id":"AUX-1","attempt":1})!=_event_id(
            "claim_auxiliary_off_attempt",{"execution_id":"AUX-1","attempt":2})


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
                    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_auxiliary_consumption_is_atomic_without_blocking_bc_claim(monkeypatch):
    import psycopg
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"];monkeypatch.setenv("DATABASE_URL",url)
    migration=Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql")
    with psycopg.connect(url) as connection:connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex;key=f"ROOTLINE-AUX-CONSUME-{suffix}"
    parent=f"ROOTLINE-PARENT-{suffix}";job=f"ROOTLINE-IRRIGATION-JOB-{suffix[:24].upper()}"
    job_sha="a"*64;segment=f"ROOTLINE-JOB-SEGMENT-{suffix[:24].upper()}"
    with psycopg.connect(url) as connection:
        for action,event_id in (("claim_before_on",f"PARENT-CLAIM-{suffix}"),
                                ("mark_active",f"PARENT-ACTIVE-{suffix}")):
            body={"action":action,"execution_id":parent,"job_id":job,
                "job_sha256":job_sha,"segment_identity":segment,"zone_id":"B12345",
                "state":"Active" if action=="mark_active" else "claimed"}
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
                values (%s,%s,'rootline_irrigation_execution',%s,%s::jsonb)""",
                (event_id,parent,action,json.dumps({"rootline_execution":body})))
    def claim(index):
        return _claim_single_auxiliary({"execution_id":f"ROOTLINE-AUX-{suffix}-{index}",
            "consumption_key":key,"auxiliary_device_id":"FERTILIZER-INJECTION-CH1",
            "device_type":"fertilizer_injection_valve","job_id":job,"job_sha256":job_sha,
            "segment_identity":segment,"zone_id":"B12345","zone_execution_id":parent})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,(1,2)))
    assert sum(item.get("created") is True for item in results)==1
    assert sorted(item.get("status") for item in results)==[
        "claimed","eligibility_already_consumed"]
    winner=1 if results[0].get("created") else 2
    auxiliary=f"ROOTLINE-AUX-{suffix}-{winner}"
    with psycopg.connect(url) as connection:
        for event_id,execution,action,body in (
            (f"AUX-TERMINAL-{suffix}",auxiliary,"record_auxiliary_completed",
             {"action":"record_auxiliary_completed","execution_id":auxiliary,
              "shutdown_verified":True}),
            (f"PARENT-TERMINAL-{suffix}",parent,"record_completed",
             {"action":"record_completed","execution_id":parent,"job_id":job,
              "shutdown_verified":True})):
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
                values (%s,%s,'rootline_irrigation_execution',%s,%s::jsonb)""",
                (event_id,execution,action,json.dumps({"rootline_execution":body})))


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
                    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_borehole_claim_restart_replay_off_and_cross_load_final_state(monkeypatch):
    import hashlib
    import psycopg
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"];monkeypatch.setenv("DATABASE_URL",url)
    migration=Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql")
    with psycopg.connect(url) as connection:connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex;execution=f"ROOTLINE-BOREHOLE-{suffix[:24].upper()}"
    aux=f"ROOTLINE-AUX-{suffix}";digest="b"*64
    material={"contract_version":"rootline_borehole_runtime_eligibility.v1",
        "device_key":"ewelink:ewelink_owner_account:1002851416:1","baseline_sha256":"a"*64,
        "registry_generation":7,"need_sha256":"c"*64,"evidence_sha256":"d"*64,
        "requested_seconds":900,"assessed_at":"2026-08-21T12:00:00+00:00",
        "gates":{key:True for key in ("canonical_need","commissioned_baseline",
            "standing_authority","provider_off","dry_run","low_water","supply_pressure",
            "full_tank","energy","concurrency","bounded_runtime")},"blockers":[]}
    eligibility_digest=hashlib.sha256(json.dumps(material,sort_keys=True,
        separators=(",",":"),default=str).encode()).hexdigest()
    artifact={**material,"eligibility_sha256":eligibility_digest,
        "execution_id":"ROOTLINE-BOREHOLE-"+eligibility_digest[:24].upper(),
        "consumption_key":"borehole:"+eligibility_digest,"eligible":True,
        "command_authority":False,"hardware_commands":0}
    execution=artifact["execution_id"]
    def insert(event_id,identity,action,body):
        with psycopg.connect(url) as connection:
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
              (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
              values (%s,%s,'rootline_irrigation_execution',%s,%s::jsonb)""",
              (event_id,identity,action,json.dumps({"rootline_execution":body})))
    insert(f"ELIG-{suffix}",execution,"record_borehole_eligibility",
        {"action":"record_borehole_eligibility",**artifact})
    insert(f"AUX-CLAIM-{suffix}",aux,"claim_auxiliary_before_on",
        {"action":"claim_auxiliary_before_on","execution_id":aux})
    insert(f"AUX-CONTAIN-{suffix}",aux,"contain_auxiliary_device",
        {"action":"contain_auxiliary_device","execution_id":aux,"shutdown_verified":False})
    body=dict(artifact)
    blocked=_claim_borehole_material_load(body)
    assert blocked["status"]=="material_load_active"
    insert(f"AUX-CONTAIN-VERIFIED-{suffix}",aux,"contain_auxiliary_device",
        {"action":"contain_auxiliary_device","execution_id":aux,"shutdown_verified":True})
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda _:_claim_borehole_material_load(body),(1,2)))
    assert sum(row.get("created") is True for row in claims)==1
    assert rootline_irrigation_execution_store("load_active_borehole",None)["execution_id"]==execution
    for attempt in (1,2):
        rootline_irrigation_execution_store("record_borehole_off_outcome",{
            "execution_id":execution,"attempt":attempt,"accepted":True})
    assert [row["attempt"] for row in rootline_irrigation_execution_store(
        "load_borehole_off_attempts",execution)]==[1,2]
    incomplete={**_borehole_completion(execution),"physical_completion_evidence":{}}
    insert(f"BH-INCOMPLETE-{suffix}",execution,"record_borehole_completed",incomplete)
    assert rootline_irrigation_execution_store("load_active_borehole",None)["execution_id"]==execution
    complete=_borehole_completion(execution)
    insert(f"BH-COMPLETE-{suffix}",execution,"record_borehole_completed",complete)
    assert rootline_irrigation_execution_store("load_active_borehole",None) is None
    replay=_claim_borehole_material_load(body)
    assert replay["created"] is False and replay["status"]=="execution_replay"


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
                    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_consumption_key_is_atomically_single_use_across_regenerated_executions(monkeypatch):
    import psycopg
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    monkeypatch.setenv("DATABASE_URL",url)
    migration=Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql")
    with psycopg.connect(url) as connection:
        connection.execute(Path("supabase/migrations/202605230001_create_irrigation_tables.sql").read_text(encoding="utf-8"))
        connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex
    key=f"ROOTLINE-BC-CONSUMPTION-{suffix}"
    def claim(index):
        execution=f"ROOTLINE-EXEC-{suffix}-{index}"
        eligibility=f"ROOTLINE-ELIG-{suffix}-{index}"
        digest=(str(index)*64)[:64]
        with psycopg.connect(url) as connection:
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
                values (%s,%s,'rootline_irrigation_execution','record_eligibility',%s::jsonb)""",
                (f"ROOTLINE-TEST-ELIG-{suffix}-{index}",execution,json.dumps({
                    "rootline_execution":{"action":"record_eligibility","execution_id":execution,
                    "eligibility_id":eligibility,"eligibility_sha256":digest,
                    "operating_date":"2026-08-12","zone_id":"B12345"}})))
        return _claim_irrigation_output({"execution_id":execution,
            "eligibility_id":eligibility,"eligibility_sha256":digest,
            "consumption_key":key,"zone_id":"B12345","operating_date":"2026-08-12"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(claim,(1,2)))
    assert sum(item.get("created") is True for item in results)==1
    assert sorted(item.get("status") for item in results)==[
        "claimed","eligibility_already_consumed"]
    winner=1 if results[0].get("created") else 2
    execution=f"ROOTLINE-EXEC-{suffix}-{winner}"
    with psycopg.connect(url) as connection:
        connection.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
            values (%s,%s,'rootline_irrigation_execution','record_completed',%s::jsonb)""",
            (f"ROOTLINE-TEST-TERMINAL-{suffix}",execution,
             json.dumps({"rootline_execution":{"action":"record_completed",
                 "execution_id":execution,"shutdown_verified":True}})))
