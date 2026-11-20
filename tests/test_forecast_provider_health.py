from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from modules.telemetry import forecast_provider_health as health

NOW = datetime(2026, 11, 19, 18, tzinfo=timezone.utc)


def claim(provider="visual_crossing"):
    return {"action":"claim","provider":provider,"attempt_id":str(uuid4())}


def outcome(request, generation=1, **overrides):
    return {**request,"action":"result","generation":generation,"status":"fetch_failed",
        "failure_kind":"quota","retry_not_before":(NOW+timedelta(days=1)).isoformat(),
        "forecast_run_at":None,**overrides}


def test_pending_admission_and_bounded_unknown_outcome_recovery():
    first=claim(); state,result,code,changed=health.transition({},first,NOW)
    assert changed and code==200 and result["allowed"] and state["generation"]==1
    assert health.transition(state,first,NOW)[1]["allowed"] is False
    other=claim()
    assert health.transition(state,other,NOW+timedelta(minutes=14))[1]["status"]=="probe_pending"
    later,admitted,_,_=health.transition(state,other,NOW+timedelta(minutes=16))
    assert admitted["allowed"] and later["generation"]==2 and later["recovered_unknown_outcome"]
    original=deepcopy(later)
    assert health.transition(later,outcome(first),NOW+timedelta(minutes=16))[2:]==(409,False)
    assert later==original


def test_result_exact_replay_conflict_and_persisted_cooldown():
    first=claim();state=health.transition({},first,NOW)[0]
    report=outcome(first)
    state,result,code,changed=health.transition(state,report,NOW+timedelta(seconds=10))
    assert code==200 and changed and result["retry_not_before"]==report["retry_not_before"]
    assert health.transition(state,report,NOW+timedelta(seconds=11))[1]["replayed"]
    changed_report={**report,"retry_not_before":None}
    assert health.transition(state,changed_report,NOW+timedelta(seconds=12))[2]==409
    assert health.transition(state,claim(),NOW+timedelta(hours=23))[1]["status"]=="provider_cooldown"
    next_claim=claim();state,admission,_,_=health.transition(state,next_claim,NOW+timedelta(days=1,seconds=1))
    assert admission["allowed"]
    success=outcome(next_claim,generation=2,status="ingested",failure_kind=None,retry_not_before=None,
        forecast_run_at=(NOW+timedelta(days=1)).isoformat())
    state,_,_,_=health.transition(state,success,NOW+timedelta(days=1,seconds=2))
    assert state["status"]=="ingested" and state["retry_not_before"]==report["retry_not_before"]


@pytest.mark.parametrize("change",[
    {"failure_kind":"secret raw URL"},{"status":"unknown"},{"retry_not_before":"2026-11-20T18:00:00"},
    {"retry_not_before":"2026-11-20T18:00:00+02:00"},{"generation":True},{"extra":"field"},
    {"status":"ingested","failure_kind":None,"forecast_run_at":None},
    {"status":"ingested","failure_kind":None,"forecast_run_at":(NOW+timedelta(seconds=1)).isoformat()},
])
def test_rejects_nonfinite_contract_fields(change):
    request=claim();state=health.transition({},request,NOW)[0]
    with pytest.raises(ValueError):health.transition(state,outcome(request,**change),NOW)


def test_auth_and_provider_guard_precede_database(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,"offline-key")
    def forbidden():raise AssertionError("must not access DB")
    assert health.provider_health(claim(),"bad",connect_factory=forbidden)[1]==401
    for provider in ("unregistered",[],None):
        assert health.provider_health({"provider":provider},"offline-key",connect_factory=forbidden)[1]==400


class Connection:
    def __init__(self,row):self.row=row;self.sql=[];self.last=""
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self
    def execute(self,sql,params=None):self.sql.append((sql,params));self.last=sql;return self
    def fetchone(self):return (NOW,) if self.last=="select clock_timestamp()" else self.row


@pytest.mark.parametrize("row",[None,({},"wrong","forecast",True),({},"visual_crossing","power",True),({},"visual_crossing","forecast",False)])
def test_registered_active_matching_source_required(monkeypatch,row):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,"offline-key");connection=Connection(row)
    assert health.provider_health(claim(),"offline-key",connect_factory=lambda:connection)[1]==409
    assert len(connection.sql)==1


def test_namespaced_update_does_not_replace_other_source_metadata(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,"offline-key")
    connection=Connection(({"owner":"preserve"},"visual_crossing","forecast",True))
    result,status=health.provider_health(claim(),"offline-key",connect_factory=lambda:connection)
    assert status==200 and result["allowed"]
    sql,params=connection.sql[-1]
    assert "jsonb_set" in sql and "{forecast_provider_health}" in sql
    assert params[1]=="visual-crossing-forecast-main"


def test_route_uses_ingest_key_and_preserves_health_status(monkeypatch):
    from flask import Flask
    from modules.telemetry import telemetry_routes
    app=Flask(__name__)
    seen=[]
    monkeypatch.setattr(health,"provider_health",lambda payload,key:(seen.append((payload,key)) or {"success":False,"status":"probe_pending"},409))
    with app.test_request_context("/telemetry/weather/forecast/provider-health",method="POST",
            json={"action":"claim","provider":"visual_crossing"},headers={"X-Amadeus-Telemetry-Key":"key"}):
        response,status=telemetry_routes.telemetry_forecast_provider_health()
    assert status==409 and seen[0][1]=="key" and response.json["status"]=="probe_pending"


@pytest.fixture
def disposable_pg(monkeypatch):
    url=os.getenv("FORECAST_HEALTH_TEST_DATABASE_URL","")
    if not url:pytest.skip("explicit isolated local PostgreSQL URL required")
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    options=conninfo_to_dict(url)
    assert options.get("host") in {"127.0.0.1","localhost"}
    assert options.get("dbname","").startswith("forecast_health_")
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,"offline-key")
    def connect():return psycopg.connect(url,connect_timeout=3,options="-c statement_timeout=3000 -c lock_timeout=1000")
    with connect() as db:
        db.execute("create table if not exists public.telemetry_sources(source_id text primary key, provider text not null, source_type text not null, active boolean not null, metadata jsonb not null default '{}'::jsonb, updated_at timestamptz not null default now())")
        db.execute("truncate public.telemetry_sources")
        db.execute("insert into public.telemetry_sources(source_id,provider,source_type,active,metadata) values('visual-crossing-forecast-main','visual_crossing','forecast',true,'{\"owner\":\"preserve\"}')")
    yield connect
    with connect() as db:db.execute("truncate public.telemetry_sources")


def test_postgres_concurrent_claims_one_winner_and_exact_replay(disposable_pg):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier=Barrier(2);requests=[claim(),claim()]
    def run(request):
        barrier.wait(timeout=5)
        return health.provider_health(request,"offline-key",connect_factory=disposable_pg)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,requests))
    winners=[i for i,(result,_) in enumerate(results) if result.get("allowed") is True]
    assert len(winners)==1
    index=winners[0];admission=results[index][0]
    report=outcome(requests[index],generation=admission["generation"],retry_not_before="2099-01-01T00:00:00+00:00")
    assert health.provider_health(report,"offline-key",connect_factory=disposable_pg)[1]==200
    replay,status=health.provider_health(report,"offline-key",connect_factory=disposable_pg)
    assert status==200 and replay["replayed"]
    assert health.provider_health({**report,"retry_not_before":None},"offline-key",connect_factory=disposable_pg)[1]==409
    held,status=health.provider_health(claim(),"offline-key",connect_factory=disposable_pg)
    assert status==200 and held["status"]=="provider_cooldown"
    with disposable_pg() as db:
        metadata=db.execute("select metadata from public.telemetry_sources").fetchone()[0]
    assert metadata["owner"]=="preserve" and metadata["forecast_provider_health"]["retry_not_before"]==report["retry_not_before"]


def test_ingest_claim_checks_source_generation_and_lease():
    request=claim();state=health.transition({},request,NOW)[0]
    payload={"provider":"visual_crossing","source_id":"visual-crossing-forecast-main",
        "provider_health_claim":{"provider":"visual_crossing","generation":1,"attempt_id":request["attempt_id"]}}
    connection=Connection(({"forecast_provider_health":state},"visual_crossing","forecast",True))
    assert health.validate_ingest_claim(connection,payload)["generation"]==1
    for field,value in (("generation",2),("attempt_id",str(uuid4()))):
        invalid=deepcopy(payload);invalid["provider_health_claim"][field]=value
        with pytest.raises(ValueError,match="claim_conflict"):health.validate_ingest_claim(connection,invalid)
    expired=deepcopy(state);expired["lease_until"]=(NOW-timedelta(seconds=1)).isoformat()
    connection.row=({"forecast_provider_health":expired},"visual_crossing","forecast",True)
    with pytest.raises(ValueError,match="claim_expired"):health.validate_ingest_claim(connection,payload)


def test_postgres_old_worker_cannot_ingest_after_new_generation(disposable_pg):
    import json
    old=claim();admission,code=health.provider_health(old,"offline-key",connect_factory=disposable_pg)
    assert code==200 and admission["allowed"]
    old_payload={"provider":"visual_crossing","source_id":"visual-crossing-forecast-main",
        "provider_health_claim":{"provider":"visual_crossing","generation":admission["generation"],"attempt_id":old["attempt_id"]}}
    with disposable_pg() as db:
        with db.cursor() as cursor:assert health.validate_ingest_claim(cursor,old_payload)
        metadata=db.execute("select metadata from public.telemetry_sources").fetchone()[0]
        metadata["forecast_provider_health"]["lease_until"]="2000-01-01T00:00:00+00:00"
        db.execute("update public.telemetry_sources set metadata=%s::jsonb",(json.dumps(metadata),))
    newer=claim();admission,code=health.provider_health(newer,"offline-key",connect_factory=disposable_pg)
    assert code==200 and admission["generation"]==2
    # Rejection occurs inside the same transaction that would write snapshots.
    with pytest.raises(ValueError,match="claim_conflict"):
        with disposable_pg() as db, db.cursor() as cursor:health.validate_ingest_claim(cursor,old_payload)
    new_payload={"provider":"visual_crossing","source_id":"visual-crossing-forecast-main",
        "provider_health_claim":{"provider":"visual_crossing","generation":2,"attempt_id":newer["attempt_id"]}}
    with disposable_pg() as db, db.cursor() as cursor:assert health.validate_ingest_claim(cursor,new_payload)
