"""Real guarded transports offline; optional explicit disposable-PG reservation tests."""
import io
import json
import os
from pathlib import Path
import threading
from urllib import request as urllib_request
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from modules.oom_sakkie import model_budget as budget


class Ledger:
    def __init__(self):
        self.rows = []
        self.lock = threading.Lock()
        self.fail_settle = False
    def reserve(self, metadata):
        with self.lock:
            total, _ = budget._aggregate([(row,) for row in self.rows])
            if total + metadata["reserved_micro_usd"] > budget.DAY_CAP_MICRO_USD:
                raise budget.ModelBudgetError("farm_model_daily_budget_exhausted")
            value = {**metadata, "day": "2026-09-23", "state": "reserved"}
            self.rows.append(value)
            return {**value, "created": True}
    def settle(self, reservation, usage):
        if self.fail_settle:
            raise RuntimeError("injected unavailable store")
        self.rows.append({**{k:v for k,v in reservation.items() if k != "created"},
                          **usage, "state":"settled"})


def request(**changes):
    payload = {"model":"gpt-5.4-mini", "messages":[{"role":"user", "content":"Synthetic farm question"}]}
    payload.update(changes)
    return urllib_request.Request("https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(), headers={"Authorization":"Bearer SYNTHETIC-NOT-A-KEY"}, method="POST")


def provider_body(model="gpt-5.4-mini-2026-03-17", usage=None):
    return json.dumps({"model":model, "choices":[{"message":{"content":"safe synthetic answer"}}],
        "usage":usage if usage is not None else {"prompt_tokens":100,"completion_tokens":20,"total_tokens":120,
            "prompt_tokens_details":{"cached_tokens":40},"completion_tokens_details":{"reasoning_tokens":10}}}).encode()


def call(ledger, opener, req=None):
    return budget.budgeted_urlopen(req or request(), timeout=3,
        purpose="test.synthetic", store=ledger, http_open=opener)


def test_reservation_precedes_provider_and_settlement_preserves_only_safe_metadata():
    ledger=Ledger()
    def opener(req, timeout):
        assert len(ledger.rows)==1 and ledger.rows[0]["state"]=="reserved"
        payload=json.loads(req.data)
        assert payload["model"]=="gpt-5.4-mini-2026-03-17"
        assert payload["max_completion_tokens"]==2048 and payload["service_tier"]=="default"
        return budget.BufferedResponse(provider_body(), headers={"x-request-id":"req_fixture_1"})
    with call(ledger,opener) as response:
        prefix=response.read(4)
        assert prefix+response.read()==provider_body() and response.getcode()==200
    assert len(ledger.rows)==2
    event=ledger.rows[-1]
    assert event["charged_micro_usd"]==138  # 60*.75 +40*.075 +20*4.5; reasoning already in20.
    assert event["reasoning_tokens"]==10 and event["provider_request_id"]=="req_fixture_1"
    assert event["returned_model"]=="gpt-5.4-mini-2026-03-17" and event["latency_ms"]>=0
    stored=json.dumps(ledger.rows)
    for private in ("Synthetic farm question","SYNTHETIC-NOT-A-KEY","safe synthetic answer","Authorization"):
        assert private not in stored


@pytest.mark.parametrize("model,snapshot,field,charge",[
    ("gpt-5.4-mini","gpt-5.4-mini-2026-03-17","max_completion_tokens",165),
    ("gpt-4.1-mini","gpt-4.1-mini-2025-04-14","max_tokens",72),
    ("gpt-4o-mini","gpt-4o-mini-2024-07-18","max_tokens",27),
])
def test_pinned_models_rates_and_compatible_output_cap(model,snapshot,field,charge):
    def opener(req,timeout):
        payload=json.loads(req.data)
        assert payload["model"]==snapshot and payload[field]==64
        return budget.BufferedResponse(provider_body(snapshot,{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120}))
    ledger=Ledger()
    call(ledger,opener,request(model=model,max_tokens=64))
    assert ledger.rows[-1]["charged_micro_usd"]==charge


@pytest.mark.parametrize("change",[
    {"model":"unpriced-model"}, {"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"synthetic"}}]}]},
    {"messages":[]}, {"messages":[{"role":"tool","content":"text"}]},
    {"messages":[{"role":"user","content":"x"}]*33}, {"n":2}, {"n":True},
    {"stream":True}, {"service_tier":"priority"}, {"tools":[]},
    {"max_tokens":0}, {"max_tokens":2049}, {"max_tokens":True},
    {"max_tokens":2,"max_completion_tokens":2},
    {"messages":[{"role":"user","content":"x"*100001}]},
])
def test_unsupported_payload_never_reserves_or_calls(change):
    ledger=Ledger(); effects=[]
    with pytest.raises(budget.ModelBudgetError):
        call(ledger,lambda *a,**k:effects.append(1),request(**change))
    assert not ledger.rows and not effects


@pytest.mark.parametrize("url",[
    "http://api.openai.com/v1/chat/completions", "https://other.example/v1/chat/completions",
    "https://api.openai.com/v1/audio/transcriptions", "https://api.openai.com/v1/chat/completions?x=1",
    "https://api.openai.com:444/v1/chat/completions", "https://user@api.openai.com/v1/chat/completions",
])
def test_unknown_endpoint_fails_before_store(url):
    req=request(); req.full_url=url
    with pytest.raises(budget.ModelBudgetError):
        call(None,lambda *a,**k:pytest.fail("provider called"),req)


def test_injected_transport_does_not_bypass_default_ledger(monkeypatch):
    class Denied:
        def reserve(self,metadata): raise budget.ModelBudgetError("farm_model_daily_budget_exhausted")
    monkeypatch.setattr(budget,"_default_store",lambda env:Denied())
    with pytest.raises(budget.ModelBudgetError,match="farm_model_daily_budget_exhausted"):
        budget.budgeted_urlopen(request(),timeout=3,purpose="test",http_open=lambda *a,**k:pytest.fail("bypass"))


def test_store_failure_prevents_network():
    class Broken:
        def reserve(self,metadata): raise RuntimeError("private database details")
    with pytest.raises(budget.ModelBudgetError) as exc:
        call(Broken(),lambda *a,**k:pytest.fail("provider called"))
    assert str(exc.value.reason)=="farm_model_budget_store_unavailable"


def test_unknown_provider_outcome_and_settlement_failure_keep_reserve():
    ledger=Ledger()
    def fail(*a,**k): raise TimeoutError("synthetic")
    with pytest.raises(TimeoutError): call(ledger,fail)
    assert len(ledger.rows)==1
    total,_=budget._aggregate([(row,) for row in ledger.rows])
    assert total==ledger.rows[0]["reserved_micro_usd"]
    ledger.fail_settle=True
    call(ledger,lambda *a,**k:budget.BufferedResponse(provider_body()))
    assert all(row["state"]=="reserved" for row in ledger.rows)


@pytest.mark.parametrize("body",[
    b"not-json", provider_body("wrong-model"),
    provider_body(usage={}),
    provider_body(usage={"prompt_tokens":-1,"completion_tokens":1,"total_tokens":0}),
    provider_body(usage={"prompt_tokens":True,"completion_tokens":1,"total_tokens":2}),
    provider_body(usage={"prompt_tokens":100,"completion_tokens":2049,"total_tokens":2149}),
    provider_body(usage={"prompt_tokens":100,"completion_tokens":1,"total_tokens":500}),
    provider_body(usage={"prompt_tokens":100,"completion_tokens":1,"total_tokens":101,"prompt_tokens_details":{"cached_tokens":101}}),
])
def test_unknown_usage_returns_response_without_refunding(body):
    ledger=Ledger()
    assert call(ledger,lambda *a,**k:budget.BufferedResponse(body)).read()==body
    assert len(ledger.rows)==1


def test_default_opener_seam_and_redirect_denial(monkeypatch):
    ledger=Ledger(); calls=[]
    monkeypatch.setattr(budget,"_default_store",lambda env:ledger)
    monkeypatch.setattr(budget,"_open_no_redirect",lambda req,timeout:calls.append(req) or budget.BufferedResponse(provider_body()))
    budget.budgeted_urlopen(request(),timeout=3,purpose="test")
    assert len(calls)==1 and len(ledger.rows)==2
    with pytest.raises(budget.ModelBudgetError,match="redirect_denied"):
        budget._NoRedirect().redirect_request(None,None,302,"redirect",{},"https://other.example")


def test_requests_adapter_sends_rewritten_bytes_once_and_audio_is_contained(monkeypatch):
    ledger=Ledger(); calls=[]
    monkeypatch.setattr(budget,"_default_store",lambda env:ledger)
    class Client:
        def post(self,url,**kwargs):
            calls.append((url,kwargs))
            assert len(ledger.rows)==1 and kwargs["allow_redirects"] is False
            assert json.loads(kwargs["data"])["max_completion_tokens"]==2048
            class Response:
                content=provider_body(); status_code=200; headers={}
            return Response()
    response=budget.budgeted_requests_post("https://api.openai.com/v1/chat/completions",
        purpose="test",http_client=Client(),json=json.loads(request().data),headers={"Authorization":"fixture"},timeout=3)
    assert response.json()["usage"]["total_tokens"]==120 and len(calls)==1
    response.raise_for_status()
    with pytest.raises(budget.ModelBudgetError,match="endpoint_unpriced"):
        budget.budgeted_requests_post("https://api.openai.com/v1/audio/transcriptions",purpose="test",
            http_client=Client(),data={"model":"whisper-1"},files={"file":("synthetic.ogg",b"fake")})
    assert len(calls)==1


def test_aggregate_rejects_orphan_duplicate_and_conflicting_settlements():
    ledger=Ledger(); call(ledger,lambda *a,**k:budget.BufferedResponse(provider_body()))
    reserve,settle=ledger.rows
    for rows in ([settle],[reserve,reserve],[reserve,settle,settle],[reserve,{**settle,"model":"different"}]):
        with pytest.raises(budget.ModelBudgetError): budget._aggregate([(row,) for row in rows])
    assert budget._aggregate([(reserve,)])[0]>budget._aggregate([(reserve,),(settle,)])[0]


# Hosted qualification: actual migration/locks/commits, fake HTTP only.
PG_URL=os.environ.get("OOM_PROTECTED_ACTION_POSTGRES_URL","").strip()
pg=pytest.mark.skipif(not PG_URL,reason="explicit disposable PostgreSQL URL is required")


class PgCursor:
    def __init__(self,cursor,schema): self.raw,self.schema=cursor,schema
    def execute(self,query,params=None):
        self.raw.execute(query.replace("public.",self.schema+"."),params); return self
    def __getattr__(self,name): return getattr(self.raw,name)
    def __enter__(self): self.raw.__enter__(); return self
    def __exit__(self,*args): return self.raw.__exit__(*args)


class PgConnection:
    def __init__(self,raw,schema): self.raw,self.schema=raw,schema
    def cursor(self): return PgCursor(self.raw.cursor(),self.schema)
    def __enter__(self): self.raw.__enter__(); return self
    def __exit__(self,*args): return self.raw.__exit__(*args)


@pytest.fixture
def pg_store():
    if not PG_URL: pytest.skip("explicit disposable PostgreSQL URL is required")
    import psycopg
    parsed=urlsplit(PG_URL)
    assert parsed.scheme in {"postgres","postgresql"} and parsed.hostname in {"localhost","127.0.0.1","::1"}
    assert "test" in parsed.path and not parsed.query and not parsed.fragment
    assert not any(os.environ.get(k) for k in ("PGHOSTADDR","PGSERVICE","PGSERVICEFILE","PGOPTIONS"))
    schema="farm_budget_"+uuid4().hex
    def connection(): return PgConnection(psycopg.connect(PG_URL),schema)
    with psycopg.connect(PG_URL) as db:
        db.execute("create schema "+schema)
    try:
        migration=Path(__file__).resolve().parents[1]/"supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql"
        with connection() as db,db.cursor() as cur: cur.execute(migration.read_text(encoding="utf-8"))
        yield budget.PostgresBudgetStore(database_url=PG_URL,connect_factory=connection),connection,schema
    finally:
        assert schema.startswith("farm_budget_") and len(schema)==44
        with psycopg.connect(PG_URL) as db: db.execute("drop schema "+schema+" cascade")


@pg
def test_pg_two_concurrent_reservations_cannot_overspend(pg_store):
    from concurrent.futures import ThreadPoolExecutor
    store,connection,_=pg_store
    barrier=threading.Barrier(2)
    def reserve():
        _,metadata=budget._prepare(request(),"test.concurrent")
        metadata["reserved_micro_usd"]=600000
        barrier.wait()
        try: store.reserve(metadata); return "admitted"
        except budget.ModelBudgetError as exc: return exc.status
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:reserve(),range(2)))
    assert sorted(results)==["admitted","farm_model_daily_budget_exhausted"]
    assert store.report()["reserved_micro_usd"]==600000


@pg
def test_pg_reservation_committed_before_http_and_replay_cannot_refund_twice(pg_store):
    store,connection,_=pg_store
    def opener(req,timeout):
        with connection() as db,db.cursor() as cur:
            cur.execute("select count(*) from public.sam_live_stock_conversation_review_events")
            assert cur.fetchone()[0]==1
        return budget.BufferedResponse(provider_body())
    call(store,opener)
    report=store.report()
    assert report["spent_micro_usd"]==138 and report["reserved_micro_usd"]==0
    with connection() as db,db.cursor() as cur:
        cur.execute("select review_json from public.sam_live_stock_conversation_review_events")
        events=[row[0] for row in cur.fetchall()]
    reserve=next(row for row in events if row["state"]=="reserved")
    settled=next(row for row in events if row["state"]=="settled")
    usage={k:v for k,v in settled.items() if k not in reserve or k in {"state"}}
    usage.pop("state",None)
    assert store.settle({**reserve,"created":True},usage)=={"created":False}
    assert store.report()["spent_micro_usd"]==138
    with pytest.raises(budget.ModelBudgetError,match="attempt_replayed"):
        store.reserve({k:v for k,v in reserve.items() if k not in {"day","state"}})


@pg
def test_pg_unknown_outcome_and_insert_failure_keep_reserve(pg_store):
    store,connection,schema=pg_store
    def fail(*a,**k): raise TimeoutError("synthetic")
    with pytest.raises(TimeoutError): call(store,fail)
    assert store.report()["reserved_micro_usd"]>0
    with connection() as db,db.cursor() as cur:
        cur.execute("create function public.fail_settlement() returns trigger language plpgsql as $$ begin if NEW.review_json->>'state'='settled' then raise exception 'test'; end if; return NEW; end $$")
        cur.execute("create trigger reject_settlement before insert on public.sam_live_stock_conversation_review_events for each row execute function public.fail_settlement()")
    call(store,lambda *a,**k:budget.BufferedResponse(provider_body()))
    report=store.report()
    assert report["spent_micro_usd"]==0 and report["reason_counts"]["in_flight_or_unknown_outcome"]==2


@pg
def test_pg_audit_migration_prevents_update_and_delete(pg_store):
    import psycopg
    store,connection,_=pg_store
    _,metadata=budget._prepare(request(),"test.audit")
    store.reserve(metadata)
    for sql in ("update public.sam_live_stock_conversation_review_events set review_json='{}'", "delete from public.sam_live_stock_conversation_review_events"):
        with pytest.raises(psycopg.Error):
            with connection() as db,db.cursor() as cur: cur.execute(sql)
    assert store.report()["reason_counts"]["in_flight_or_unknown_outcome"]==1


@pg
def test_pg_cap_checks_all_rows_without_a_loader_limit(pg_store):
    store,connection,_=pg_store
    with connection() as db,db.cursor() as cur:
        cur.execute("select (clock_timestamp() at time zone 'Africa/Johannesburg')::date::text")
        day=cur.fetchone()[0]
        for _ in range(1100):
            _,metadata=budget._prepare(request(),"test.history")
            budget.PostgresBudgetStore._insert(cur,{**metadata,"day":day,"state":"reserved","reserved_micro_usd":910})
    with pytest.raises(budget.ModelBudgetError,match="exhausted"):
        call(store,lambda *a,**k:pytest.fail("must not call"))


@pytest.mark.parametrize("midnight,commit_failure",[(True,False),(False,True)])
def test_clock_rollover_or_uncertain_commit_never_enters_provider(midnight,commit_failure):
    statements=[]
    class Cursor:
        def __init__(self): self.dates=iter(["2026-09-23", "2026-09-24" if midnight else "2026-09-23"]); self.query=""
        def execute(self,query,params=None): self.query=query; statements.append(query)
        def fetchone(self):
            return (next(self.dates),) if "clock_timestamp()" in self.query else ("event-created",)
        def fetchall(self): return []
        def __enter__(self): return self
        def __exit__(self,*args): return False
    class Connection:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self,kind,*args):
            if kind is None and commit_failure: raise OSError("uncertain commit")
            return False
    store=budget.PostgresBudgetStore(database_url="unused-test-only",connect_factory=Connection)
    with pytest.raises(budget.ModelBudgetError) as exc:
        call(store,lambda *a,**k:pytest.fail("no committed admission"))
    assert exc.value.status==("farm_model_budget_day_changed" if midnight else "farm_model_budget_store_unavailable")
    assert any("pg_advisory_xact_lock" in sql for sql in statements)
    if midnight: assert not any(sql.lstrip().startswith("insert") for sql in statements)


def test_body_rewrite_drops_stale_content_length_and_invalid_usage_never_logs_body():
    ledger=Ledger(); req=request()
    req.add_header("Content-Length",str(len(req.data)))
    def opener(bound,timeout):
        assert bound.get_header("Content-length") is None
        return budget.BufferedResponse(provider_body(),headers={"x-request-id":"bad\nprivate-body"})
    call(ledger,opener,req)
    assert ledger.rows[-1]["provider_request_id"]==""


def test_budget_report_failure_is_safe_and_never_uses_provider():
    class Broken:
        def report(self): raise OSError("private connection")
    assert budget.budget_status(store=Broken())=={"status":"farm_model_budget_store_unavailable","available":False}


@pg
def test_pg_lock_timeout_cannot_authorize_provider(pg_store):
    store,connection,_=pg_store
    with connection() as db,db.cursor() as cur:
        cur.execute("select (clock_timestamp() at time zone 'Africa/Johannesburg')::date::text")
        budget.PostgresBudgetStore._lock(cur,cur.fetchone()[0])
        with pytest.raises(budget.ModelBudgetError,match="store_unavailable"):
            call(store,lambda *a,**k:pytest.fail("locked budget must not authorize"))
    assert store.report()["reserved_micro_usd"]==0
