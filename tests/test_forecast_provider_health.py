from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from modules.telemetry import forecast_provider_health as health

NOW = datetime(2026, 11, 19, 21, 30, tzinfo=timezone.utc)


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


CYCLE_REQUEST = {"action": "nightly_claim", "provider": "visual_crossing", "attempt_id": str(uuid4())}
CYCLE_STATE = health.nightly_transition({}, CYCLE_REQUEST, NOW)[0]
CYCLE = {key: CYCLE_STATE[key] for key in ("attempt_id", "cycle_date", "operating_date")}


class Connection:
    def __init__(self,row):
        self.row=deepcopy(row);self.sql=[];self.last=""
        if self.row and isinstance(self.row[0],dict):
            metadata=self.row[0]
            metadata.setdefault("forecast_nightly_cycle",deepcopy(CYCLE_STATE))
            if "forecast_provider_health" in metadata:
                state=metadata["forecast_provider_health"]
                state["nightly_cycle"]=deepcopy(CYCLE)
                metadata["forecast_nightly_cycle"]["attempts"]=[{
                    "provider":self.row[1],"attempt_id":state["attempt_id"],
                    "generation":state["generation"],"status":"pending"}]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return self
    def execute(self,sql,params=None):
        self.sql.append((sql,params));self.last=sql
        if "update public.telemetry_sources" in sql:
            import json
            key="forecast_nightly_cycle" if "{forecast_nightly_cycle}" in sql else "forecast_provider_health"
            self.row[0][key]=json.loads(params[0])
        return self
    def fetchone(self):return (NOW,) if self.last=="select clock_timestamp()" else self.row


@pytest.mark.parametrize("row",[None,({},"wrong","forecast",True),({},"visual_crossing","power",True),({},"visual_crossing","forecast",False)])
def test_registered_active_matching_source_required(monkeypatch,row):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,"offline-key");connection=Connection(row)
    assert health.provider_health(CYCLE_REQUEST,"offline-key",connect_factory=lambda:connection)[1]==409
    assert len(connection.sql)==1


def test_namespaced_update_does_not_replace_other_source_metadata(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,"offline-key")
    connection=Connection(({"owner":"preserve"},"visual_crossing","forecast",True))
    result,status=health.provider_health({**claim(),"nightly_cycle":CYCLE},"offline-key",connect_factory=lambda:connection)
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
    if not url:pytest.skip("FORECAST_HEALTH_TEST_DATABASE_URL required; hosted PostgreSQL proof pending")
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
    # Fix only the nightly admission time, using the database clock's most recent
    # eligible SAST night. Provider leases and all SQL locking use the real clock.
    with connect() as db:
        server_now = db.execute("select clock_timestamp()").fetchone()[0]
    local = server_now.astimezone(__import__('zoneinfo').ZoneInfo('Africa/Johannesburg'))
    boundary = local.replace(hour=23, minute=30, second=0, microsecond=0)
    if boundary > local:
        boundary -= timedelta(days=1)
    original_transition = health.nightly_transition
    def at_nightly_boundary(state, request, now):
        return original_transition(state, request, boundary.astimezone(timezone.utc)
            if request.get('action') == 'nightly_claim' else now)
    monkeypatch.setattr(health, 'nightly_transition', at_nightly_boundary)
    cycle_request = {'action':'nightly_claim','provider':'visual_crossing','attempt_id':str(uuid4())}
    admitted, status = health.provider_health(cycle_request, 'offline-key', connect_factory=connect)
    assert status == 200 and admitted['allowed'] is True
    connect.cycle = {key: admitted['cycle'][key] for key in ('attempt_id','cycle_date','operating_date')}
    connect.cycle_request = cycle_request
    yield connect
    with connect() as db:db.execute("truncate public.telemetry_sources")


def test_postgres_concurrent_claims_one_winner_and_exact_replay(disposable_pg):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier=Barrier(2);requests=[{**claim(),"nightly_cycle":disposable_pg.cycle} for _ in range(2)]
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
    held,status=health.provider_health({**claim(),"nightly_cycle":disposable_pg.cycle},"offline-key",connect_factory=disposable_pg)
    assert status==200 and held["status"]=="nightly_provider_already_attempted"
    with disposable_pg() as db:
        metadata=db.execute("select metadata from public.telemetry_sources").fetchone()[0]
    assert metadata["owner"]=="preserve" and metadata["forecast_provider_health"]["retry_not_before"]==report["retry_not_before"]
    # The new nightly fence does not erase the persisted provider cooldown.
    import json
    next_state=deepcopy(metadata['forecast_nightly_cycle'])
    next_state.update(attempt_id=str(uuid4()),attempts=[])
    next_cycle={key:next_state[key] for key in ('attempt_id','cycle_date','operating_date')}
    with disposable_pg() as db:
        db.execute("update public.telemetry_sources set metadata=jsonb_set(metadata,'{forecast_nightly_cycle}',%s::jsonb)",(json.dumps(next_state),))
    held,status=health.provider_health({**claim(),'nightly_cycle':next_cycle},'offline-key',connect_factory=disposable_pg)
    assert status==200 and held['status']=='provider_cooldown'



def test_ingest_claim_checks_source_generation_and_lease():
    request=claim();state=health.transition({},request,NOW)[0]
    payload={"provider":"visual_crossing","source_id":"visual-crossing-forecast-main",
        "provenance":{"nightly_cycle":CYCLE},"forecast_run_at":NOW.isoformat(),
        "provider_health_claim":{"provider":"visual_crossing","generation":1,"attempt_id":request["attempt_id"]}}
    connection=Connection(({"forecast_provider_health":state},"visual_crossing","forecast",True))
    assert health.validate_ingest_claim(connection,payload)["generation"]==1
    for field,value in (("generation",2),("attempt_id",str(uuid4()))):
        invalid=deepcopy(payload);invalid["provider_health_claim"][field]=value
        with pytest.raises(ValueError,match="claim_conflict"):health.validate_ingest_claim(connection,invalid)
    expired=deepcopy(state);expired["lease_until"]=(NOW-timedelta(seconds=1)).isoformat()
    connection.row=Connection(({"forecast_provider_health":expired},"visual_crossing","forecast",True)).row
    with pytest.raises(ValueError,match="claim_expired"):health.validate_ingest_claim(connection,payload)


def _pg_ingest_payload(connect, request, generation):
    with connect() as db:
        run_at = db.execute("select clock_timestamp()").fetchone()[0].isoformat()
    return {'provider':'visual_crossing','source_id':health.SOURCES['visual_crossing'],
        'forecast_run_at':run_at, 'provenance':{'nightly_cycle':deepcopy(request['nightly_cycle'])},
        'provider_health_claim':{'provider':'visual_crossing','generation':generation,'attempt_id':request['attempt_id']}}


def test_postgres_old_worker_cannot_ingest_after_new_generation(disposable_pg):
    import json
    old={**claim(),'nightly_cycle':deepcopy(disposable_pg.cycle)}
    admission,code=health.provider_health(old,'offline-key',connect_factory=disposable_pg)
    assert code==200 and admission['allowed']
    old_payload=_pg_ingest_payload(disposable_pg,old,admission['generation'])
    with disposable_pg() as db, db.cursor() as cursor:
        assert health.validate_ingest_claim(cursor,old_payload)
    # Simulate the next nightly acquisition after an expired worker. No same-cycle
    # reclaim is allowed, even when its provider lease has expired.
    with disposable_pg() as db:
        metadata=db.execute('select metadata from public.telemetry_sources').fetchone()[0]
        metadata['forecast_provider_health']['lease_until']='2000-01-01T00:00:00+00:00'
        db.execute('update public.telemetry_sources set metadata=%s::jsonb',(json.dumps(metadata),))
    held,status=health.provider_health({**claim(),'nightly_cycle':disposable_pg.cycle},'offline-key',connect_factory=disposable_pg)
    assert status==200 and held['status']=='nightly_provider_already_attempted'
    with disposable_pg() as db:
        state=metadata['forecast_nightly_cycle']
        state.pop('ingest',None);state.pop('attempts',None)
        state['attempt_id']=str(uuid4())
        # The fixture advances only the nightly fence; provider generation and
        # source locks are exercised by the actual production endpoint.
        state['cycle_date']=(datetime.fromisoformat(state['cycle_date'])+timedelta(days=1)).date().isoformat()
        state['operating_date']=(datetime.fromisoformat(state['operating_date'])+timedelta(days=1)).date().isoformat()
        db.execute("update public.telemetry_sources set metadata=jsonb_set(metadata,'{forecast_nightly_cycle}',%s::jsonb)",(json.dumps(state),))
    cycle={key:state[key] for key in ('attempt_id','cycle_date','operating_date')}
    newer={**claim(),'nightly_cycle':cycle}
    admitted,status=health.provider_health(newer,'offline-key',connect_factory=disposable_pg)
    assert status==200 and admitted['allowed'] and admitted['generation']==2
    with pytest.raises(ValueError,match='nightly_cycle_conflict'):
        with disposable_pg() as db, db.cursor() as cursor:
            health.validate_ingest_claim(cursor,old_payload)
    switched=deepcopy(old_payload);switched['provenance']['nightly_cycle']=cycle
    with pytest.raises(ValueError,match='claim_conflict'):
        with disposable_pg() as db, db.cursor() as cursor:
            health.validate_ingest_claim(cursor,switched)
    new_payload=_pg_ingest_payload(disposable_pg,newer,2)
    with disposable_pg() as db, db.cursor() as cursor:
        assert health.validate_ingest_claim(cursor,new_payload)['generation']==2


def test_postgres_ingest_receipt_rollback_exact_replay_and_completed_cycle(disposable_pg):
    request={**claim(),'nightly_cycle':disposable_pg.cycle}
    admission,status=health.provider_health(request,'offline-key',connect_factory=disposable_pg)
    assert status==200 and admission['allowed']
    packet=_pg_ingest_payload(disposable_pg,request,admission['generation'])
    report=outcome(request,generation=admission['generation'],status='ingested',
        failure_kind=None,retry_not_before=None,forecast_run_at=packet['forecast_run_at'])
    # An uncommitted ingest receipt cannot authorize a provider success.
    with pytest.raises(RuntimeError,match='simulated snapshot failure'):
        with disposable_pg() as db, db.cursor() as cursor:
            health.validate_ingest_claim(cursor,packet)
            raise RuntimeError('simulated snapshot failure')
    unproven,status=health.provider_health(report,'offline-key',connect_factory=disposable_pg)
    assert status==400 and unproven['status']=='nightly_provider_ingest_unproven'
    with disposable_pg() as db:
        metadata=db.execute('select metadata from public.telemetry_sources').fetchone()[0]
        assert 'ingest' not in metadata['forecast_nightly_cycle']
        assert metadata['forecast_provider_health']['status']=='pending'
    # Two independent transactions replay the identical ingest receipt.
    for _ in range(2):
        with disposable_pg() as db, db.cursor() as cursor:
            assert health.validate_ingest_claim(cursor,packet)['generation']==admission['generation']
    conflicting=deepcopy(packet)
    conflicting['forecast_run_at']=(datetime.fromisoformat(packet['forecast_run_at'])-timedelta(microseconds=1)).isoformat()
    with pytest.raises(ValueError,match='nightly_ingest_already_bound'):
        with disposable_pg() as db, db.cursor() as cursor:
            health.validate_ingest_claim(cursor,conflicting)
    recorded,status=health.provider_health(report,'offline-key',connect_factory=disposable_pg)
    assert status==200 and recorded['success']
    replay,status=health.provider_health(report,'offline-key',connect_factory=disposable_pg)
    assert status==200 and replay['replayed']
    final={**disposable_pg.cycle_request,'action':'nightly_result','status':'ingested',
        'source_id':packet['source_id'],'forecast_run_at':packet['forecast_run_at']}
    assert health.provider_health(final,'offline-key',connect_factory=disposable_pg)[1]==200
    replay,status=health.provider_health(final,'offline-key',connect_factory=disposable_pg)
    assert status==200 and replay['status']=='nightly_result_replayed'
    with disposable_pg() as db:
        metadata=db.execute('select metadata from public.telemetry_sources').fetchone()[0]
    assert metadata['owner']=='preserve'
    assert metadata['forecast_nightly_cycle']['status']=='ingested'
    assert metadata['forecast_nightly_cycle']['ingest']['forecast_run_at']==packet['forecast_run_at']
    assert metadata['forecast_provider_health']['nightly_cycle']==disposable_pg.cycle
    assert len(metadata['forecast_nightly_cycle']['attempts'])==1
    with pytest.raises(ValueError,match='nightly_cycle_conflict'):
        with disposable_pg() as db, db.cursor() as cursor:
            health.validate_ingest_claim(cursor,packet)


@pytest.mark.parametrize('minute,allowed',[(29,False),(30,True),(59,True)])
def test_nightly_boundary_and_whole_cycle_no_reclaim(minute,allowed):
    at=NOW.replace(minute=minute)
    state,result,_,changed=health.nightly_transition({},CYCLE_REQUEST,at)
    assert result['allowed'] is allowed and changed is allowed
    if allowed:
        assert state['operating_date']=='2026-11-20'
        duplicate={**CYCLE_REQUEST,'attempt_id':str(uuid4())}
        assert health.nightly_transition(state,duplicate,at+timedelta(minutes=1))[1]['allowed'] is False
        assert health.nightly_transition(state,duplicate,at+timedelta(hours=1))[1]['allowed'] is False
        failed=health.nightly_transition(state,{**CYCLE_REQUEST,'action':'nightly_result','status':'failed'},at)[0]
        assert health.nightly_transition(failed,duplicate,at)[1]['allowed'] is False


def test_nightly_result_requires_exact_committed_ingest_and_provider_result():
    state=deepcopy(CYCLE_STATE)
    result={**CYCLE_REQUEST,'action':'nightly_result','status':'ingested',
        'source_id':health.SOURCES['visual_crossing'],'forecast_run_at':NOW.isoformat()}
    with pytest.raises(ValueError,match='ingest_unproven'):health.nightly_transition(state,result,NOW)
    state['ingest']={'source_id':result['source_id'],'forecast_run_at':NOW.isoformat(),
        'attempt_id':'provider-attempt','generation':1}
    state['attempts']=[{'provider':'visual_crossing','attempt_id':'provider-attempt','generation':1,'status':'pending'}]
    with pytest.raises(ValueError,match='ingest_unproven'):health.nightly_transition(state,result,NOW)
    state['attempts'][0]['status']='ingested'
    completed,receipt,_,_=health.nightly_transition(state,result,NOW)
    assert completed['status']=='ingested' and receipt['success']
    assert health.nightly_transition(completed,result,NOW)[1]['success']


def test_bound_provider_attempt_cannot_be_claimed_twice_or_omit_cycle(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,'offline-key')
    connection=Connection(({'owner':'preserve'},'visual_crossing','forecast',True))
    first={**claim(),'nightly_cycle':CYCLE}
    admitted,status=health.provider_health(first,'offline-key',connect_factory=lambda:connection)
    assert status==200 and admitted['allowed']
    again,status=health.provider_health({**claim(),'nightly_cycle':CYCLE},'offline-key',connect_factory=lambda:connection)
    assert status==200 and again['status']=='nightly_provider_already_attempted'
    missing,status=health.provider_health(claim(),'offline-key',connect_factory=lambda:connection)
    assert status==400 and missing['status']=='nightly_cycle_required'
    assert connection.row[0]['owner']=='preserve'
    assert len(connection.row[0]['forecast_nightly_cycle']['attempts'])==1


def test_ingest_cannot_omit_or_switch_cycle_and_records_exact_receipt():
    request=claim();state=health.transition({},request,NOW)[0]
    connection=Connection(({'forecast_provider_health':state},'visual_crossing','forecast',True))
    packet={'provider':'visual_crossing','source_id':health.SOURCES['visual_crossing'],
        'provider_health_claim':{k:request[k] for k in ('provider','attempt_id')}|{'generation':1},
        'forecast_run_at':NOW.isoformat(),'provenance':{'nightly_cycle':CYCLE}}
    missing=deepcopy(packet);missing['provenance']={}
    with pytest.raises(ValueError,match='nightly_cycle_required'):health.validate_ingest_claim(connection,missing)
    wrong=deepcopy(packet);wrong['provenance']['nightly_cycle']['attempt_id']=str(uuid4())
    with pytest.raises(ValueError,match='nightly_cycle_conflict'):health.validate_ingest_claim(connection,wrong)
    health.validate_ingest_claim(connection,packet)
    receipt=connection.row[0]['forecast_nightly_cycle']['ingest']
    assert receipt['attempt_id']==request['attempt_id'] and receipt['forecast_run_at']==NOW.isoformat()
    reads=[params[0] for sql,params in connection.sql if 'for update' in sql]
    assert reads[-2:]==[health.SOURCES['visual_crossing']]*2


def test_health_endpoint_uses_existing_request_budget_and_restores_outer_scope(monkeypatch):
    from modules.telemetry import rootline_cycle_budget as budget
    from modules.oom_sakkie.bounded_postgres_read import OWNER_REQUEST_DEADLINE_SECONDS
    seen=[]
    monkeypatch.setattr(health,'_provider_health_locked',lambda *a,**k:(seen.append(budget.remaining_seconds()) or ({'success':True},200)))
    assert budget.work_deadline() is None
    health.provider_health({})
    assert 0<seen[0]<=OWNER_REQUEST_DEADLINE_SECONDS and budget.work_deadline() is None


def test_expired_health_request_rejected_before_database_without_retry(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,'offline-key')
    calls=[]
    def forbidden():
        calls.append('connection')
        raise AssertionError('expired request must never connect')
    request={**claim(),'request_expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    result,status=health.provider_health(request,'offline-key',connect_factory=forbidden)
    assert status==408 and result['status']=='forecast_health_request_expired'
    assert calls==[]


def test_legacy_client_claim_without_cycle_rejected_before_source_access(monkeypatch):
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,'offline-key')
    connection=Connection(({'owner':'preserve'},'visual_crossing','forecast',True))
    original=deepcopy(connection.row)
    result,status=health.provider_health(claim(),'offline-key',connect_factory=lambda:connection)
    assert status==400 and result['status']=='nightly_cycle_required'
    assert connection.sql==[] and connection.row==original
