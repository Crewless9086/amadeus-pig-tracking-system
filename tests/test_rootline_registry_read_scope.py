"""Fresh canonical authority reads reuse a connection, never prior results."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid
import pytest
from modules.telemetry import rootline_device_spine as spine
from modules.telemetry.rootline_command_acceptance import digest
from tests.test_rootline_injector_owner_authority import CanonicalDatabase, Cursor, KEY

NOW = datetime(2026, 11, 27, 11, tzinfo=timezone.utc)

class ScopedDatabase(CanonicalDatabase):
    def __init__(self, **kwargs):
        super().__init__(NOW)
        self.connections = []; self.isolation = "read committed"; self.after = None
        self.failure = None; self.spend = kwargs.get("spend", lambda *args: None)
    def factory(self):
        db = self
        class Connection:
            closed = False
            error = None
            def __enter__(self):
                db.spend("connection", 2); db.connections.append(self); return self
            def __exit__(self, kind, value, tb): self.closed = True; self.error = kind
            def cursor(self):
                class Read(Cursor):
                    def execute(self, sql, args=()):
                        db.spend("query with timeout setup", .5)
                        if "current_setting('transaction_isolation')" in sql:
                            self.rows = [(db.isolation,)]; db.queries.append((sql,args)); return self
                        if db.failure and db.failure in sql: raise RuntimeError("synthetic read failure")
                        result = super().execute(sql, args)
                        if db.after: db.after(sql)
                        return result
                return Read(db)
        return Connection()


def test_one_scope_four_fresh_reads_and_no_result_or_connection_escapes():
    db = ScopedDatabase(); result = db.load()
    assert result["device_record"]["standing_authority"] is True
    assert len(db.connections) == 1 and db.connections[0].closed
    assert sum("rootline_device_commissioning_evidence" in sql for sql,_ in db.queries) == 2
    assert sum("rootline_standing_authorities" in sql for sql,_ in db.queries) == 1
    db.revoked = True
    with pytest.raises(ValueError, match="authority_unresolved"): db.load()
    assert len(db.connections) == 2 and all(c.closed for c in db.connections)


@pytest.mark.parametrize("isolation", ["repeatable read", "serializable", "read uncommitted", None])
def test_incompatible_isolation_refused_before_registry(isolation):
    db = ScopedDatabase(); db.isolation = isolation
    with pytest.raises(ValueError, match="isolation_unproven"): db.load()
    assert len(db.queries) == 1 and db.connections[0].closed


@pytest.mark.parametrize("query", ["rootline_device_registry", "rootline_device_commissioning_evidence", "rootline_standing_authorities"])
def test_query_failure_closes_and_next_load_cannot_reuse_connection(query):
    db = ScopedDatabase(); db.failure = query
    with pytest.raises(RuntimeError, match="synthetic read failure"): db.load()
    assert db.connections[0].closed and db.connections[0].error is RuntimeError
    db.failure = None; assert db.load()["device_record"]
    assert len(db.connections) == 2 and all(c.closed for c in db.connections)


def test_revocation_between_queries_is_not_memoized():
    db = ScopedDatabase()
    db.after = lambda sql: setattr(db, "revoked", True) if "rootline_device_commissioning_evidence" in sql else None
    with pytest.raises(ValueError, match="authority_unresolved"): db.load()
    assert len(db.connections) == 1 and db.connections[0].closed


URL = os.getenv("ROOTLINE_HA_COMMAND_TEST_URL", "")

def _validate_client_target(url):
    parsed = urlparse(url)
    assert parsed.scheme == "postgresql" and parsed.hostname == "127.0.0.1" and parsed.port == 55485
    assert parsed.path == "/rootline_ha_command_mode_test" and parsed.username == "postgres"
    assert parsed.password is None and not parsed.query and not parsed.fragment


def _validate_server_target(row, *, github_actions=False, github_job=""):
    from ipaddress import IPv4Address, IPv4Network
    assert isinstance(row, tuple) and len(row) == 4, row
    database, user, address, port = row
    assert database == "rootline_ha_command_mode_test" and user == "postgres", row
    local = address == "127.0.0.1" and port == 55485
    # GitHub maps the already-validated loopback55485 client endpoint to its
    # disposable Docker service's internal address/5432, not server55485.
    container = (github_actions is True and github_job == "rootline-controller-transport"
        and isinstance(address, str) and IPv4Address(address) in IPv4Network("172.16.0.0/12")
        and port == 5432)
    assert local or container, row


def pg_connect():
    import psycopg
    _validate_client_target(URL)
    connection = psycopg.connect(URL, connect_timeout=5)
    try:
        row = connection.execute("select current_database(),current_user,host(inet_server_addr()),inet_server_port()").fetchone()
        _validate_server_target(row, github_actions=os.getenv("GITHUB_ACTIONS") == "true",
            github_job=os.getenv("GITHUB_JOB", ""))
        connection.commit()
        return connection
    except BaseException:
        connection.close()
        raise


@pytest.mark.parametrize("address,port,actions,job,accepted", [
    ("127.0.0.1",55485,False,"",True),
    ("172.18.0.2",5432,True,"rootline-controller-transport",True),
    ("172.18.0.2",5432,False,"rootline-controller-transport",False),
    ("172.18.0.2",5432,True,"another-job",False),
    ("172.18.0.2",55485,True,"rootline-controller-transport",False),
    ("127.0.0.1",5432,False,"",False),
    ("8.8.8.8",5432,True,"rootline-controller-transport",False),
    ("10.0.0.1",5432,True,"rootline-controller-transport",False),
    ("172.32.0.1",5432,True,"rootline-controller-transport",False),
])
def test_disposable_server_catalog_identity(address,port,actions,job,accepted):
    row=("rootline_ha_command_mode_test","postgres",address,port)
    if accepted:_validate_server_target(row,github_actions=actions,github_job=job)
    else:
        with pytest.raises(AssertionError):_validate_server_target(row,github_actions=actions,github_job=job)


@pytest.mark.parametrize("field,value", [(0,"production"),(1,"another_user")])
def test_disposable_server_rejects_wrong_database_or_user(field,value):
    row=["rootline_ha_command_mode_test","postgres","172.18.0.2",5432];row[field]=value
    with pytest.raises(AssertionError):
        _validate_server_target(tuple(row),github_actions=True,github_job="rootline-controller-transport")


@pytest.mark.parametrize("url", [
    "postgresql://postgres@db.example.com:55485/rootline_ha_command_mode_test",
    "postgresql://postgres@127.0.0.1:5432/rootline_ha_command_mode_test",
    "postgresql://postgres@127.0.0.1:55485/production",
    "postgresql://other@127.0.0.1:55485/rootline_ha_command_mode_test",
    "postgresql://postgres@127.0.0.1:55485/rootline_ha_command_mode_test?host=db.example.com",
])
def test_client_target_rejects_non_disposable_endpoint(url):
    with pytest.raises(AssertionError):_validate_client_target(url)


@pytest.fixture
def pg_device():
    if not URL: pytest.skip("explicit synthetic PostgreSQL required")
    from tests.test_rootline_device_spine_postgres import device
    migration = Path(__file__).parents[1]/"supabase/migrations/202608170001_add_rootline_device_registry.sql"
    with pg_connect() as db:
        db.execute("create extension if not exists pgcrypto")
        db.execute("create schema if not exists app_private")
        db.execute("create table if not exists app_private.oom_protected_action_claims(callback_token text primary key)")
        db.execute("create table if not exists app_private.migration_log(migration_id text primary key,description text not null)")
        db.execute(migration.read_text(encoding="utf-8"))
    suffix = "SCOPE59-"+uuid.uuid4().hex; evidence = {}
    stages = ("provider_discovered","readback_proven","bounded_actuation_ready","physical_identity_proven",
        "fail_stop_proven","replay_proven","operational_dependencies_proven","supervised")
    authority = suffix+":authority"; policy_sha = digest({})
    with pg_connect() as db:
        for stage in stages:
            identity = suffix+":"+stage; proof = hashlib.sha256(identity.encode()).hexdigest()
            evidence[stage] = {"source":"canonical","evidence_id":identity,"observed_at":NOW.isoformat(),"sha256":proof}
            db.execute("""insert into app_private.rootline_device_commissioning_evidence
                (evidence_id,source,observed_at,evidence_sha256,evidence_payload)
                values(%s,'canonical',%s,%s,'{"test_only":true}')""",(identity,NOW,proof))
        db.execute("""insert into app_private.rootline_standing_authorities
            (standing_authority_id,version,issuer,policy_sha256,active,revoked,policy_payload)
            values(%s,'1','owner_policy',%s,true,false,'{}')""",(authority,policy_sha))
    record = device(suffix,commissioning_stage="standing_active",standing_authority=True,
        commissioning_evidence=evidence,authority_envelope={"standing_authority_id":authority,"version":"1",
            "issuer":"owner_policy","policy_sha256":policy_sha,"revoked":False})
    saved = spine.store_device_record(record,connect_factory=pg_connect)
    return saved["device_key"], authority, evidence


def bounded_factory(trace, hook=None):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    @contextmanager
    def factory():
        raw = []
        def connect(*args, **kwargs):
            value = pg_connect(); raw.append(value); return value
        try:
            with connect_bounded_rootline_postgres(database_url=URL, connect=connect, read_only=True, read_committed=True) as db:
                class Connection:
                    def cursor(self):
                        original = db.cursor()
                        class Read:
                            def __enter__(self): original.__enter__(); return self
                            def __exit__(self,*args): return original.__exit__(*args)
                            def execute(self,sql,args=None):
                                trace.append(sql)
                                value=original.execute(sql,args)
                                if hook: hook(sql)
                                return self
                            def fetchone(self): return original.fetchone()
                        return Read()
                try: yield Connection()
                finally: trace.append("scope_exit")
        finally:
            assert all(value.closed for value in raw)
            trace.append("connection_closed")
    return factory


@pytest.mark.parametrize("invalidate", ["authority", "next_evidence"])
def test_real_read_committed_sees_interquery_commit_and_closes(pg_device,invalidate):
    key, authority, evidence = pg_device; trace=[]; fired=[]
    def hook(sql):
        if "rootline_device_commissioning_evidence" not in sql or fired: return
        fired.append(True)
        with pg_connect() as writer:
            if invalidate == "authority":
                writer.execute("""insert into app_private.rootline_authority_events
                    (event_id,standing_authority_id,version,event_type,reason)
                    values(%s,%s,'1','revoked','synthetic interquery revocation')""",(uuid.uuid4().hex,authority))
            else:
                writer.execute("""insert into app_private.rootline_device_evidence_events
                    (event_id,evidence_id,event_type,reason)
                    values(%s,%s,'invalidated','synthetic interquery invalidation')""",
                    (uuid.uuid4().hex,evidence["readback_proven"]["evidence_id"]))
    with pytest.raises(ValueError,match="unresolved"):
        spine.load_device_record(key,connect_factory=bounded_factory(trace,hook))
    assert fired and trace.count("scope_exit") == 1
    # Re-run without hook: canonical revocation remains effective in a new scope.
    with pytest.raises(ValueError,match="unresolved"):
        spine.load_device_record(key,connect_factory=bounded_factory(trace))
    assert trace.count("scope_exit") == 2


def test_real_calls_have_fresh_independent_connections(pg_device):
    key, authority, evidence = pg_device; trace=[]
    for _ in range(2): assert spine.load_device_record(key,connect_factory=bounded_factory(trace))["device_record"]
    assert trace.count("connection_closed") == 2
    assert sum("rootline_device_registry" in sql for sql in trace) == 2


@pytest.mark.parametrize("explicit_read_committed", [False, True])
def test_real_production_read_factory_and_borrowed_lock_keep_scope(pg_device, explicit_read_committed):
    from contextlib import nullcontext
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry import rootline_timed_control as timed
    from tests.test_rootline_command_mode import ENV
    key = pg_device[0]
    # False matches runtime/HA/protected mixer read factories; True matches
    # existing injector claim/dispatch lock factories. No isolation is changed
    # by load_device_record, and nullcontext never closes its caller's lock.
    with connect_bounded_rootline_postgres(database_url=URL, connect=lambda *a,**k:pg_connect(),
            read_only=False, read_committed=explicit_read_committed) as db:
        db.execute("select pg_advisory_xact_lock(597001)")
        assert spine.load_device_record(key,connect_factory=lambda:nullcontext(db))
        assert not db.closed
        template=CanonicalDatabase(NOW); suffix="LOCK59-"+uuid.uuid4().hex
        record=deepcopy(template.device)
        for stage,proof in record["commissioning_evidence"].items():
            proof["evidence_id"]=suffix+":"+stage
            db.execute("""insert into app_private.rootline_device_commissioning_evidence
              (evidence_id,source,observed_at,evidence_sha256,evidence_payload)
              values(%s,'canonical',%s,%s,'{}')""",(proof["evidence_id"],NOW,proof["sha256"]))
        envelope=record["authority_envelope"];envelope["standing_authority_id"]=suffix
        db.execute("""insert into app_private.rootline_standing_authorities
          (standing_authority_id,version,issuer,policy_sha256,active,revoked,policy_payload)
          values(%s,'1','owner_policy',%s,true,false,%s::jsonb)""",
          (suffix,template.policy_sha,json.dumps(template.policy)))
        prior=db.execute("select registry_generation from app_private.rootline_device_registry where device_key=%s",(KEY,)).fetchone()
        record["registry_generation"]=prior[0]+1 if prior else 1
        spine.store_device_record(record,connect_factory=lambda:nullcontext(db))
        with timed.timed_control_scope(ENV):
            assert timed.locked_owner_injector_authority(db,{"maximum_duration_seconds":120})
        assert not db.closed
        assert db.execute("select current_setting('transaction_isolation')").fetchone()==("read committed",)
        # Roll back only this test's synthetic commissioning/lock scope.
        db.rollback()
    assert db.closed


@pytest.mark.parametrize("command_mode", [True,False])
def test_real_borehole_preparation_resolves_registry_then_skips_only_unused_binding(monkeypatch,command_mode):
    from contextlib import nullcontext
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry import rootline_ewelink_request_budget as requests
    from modules.telemetry import rootline_owner_controls as owner
    from tests.test_rootline_command_mode import ENV
    from tests.test_rootline_continuous_borehole import snapshot
    db=ScopedDatabase();owner_reads=[];provider_reads=[];optional=[]
    db.device.update(provider="ewelink",device_id="1002851416",device_type="pump",
        adapter_profile="ewelink_borehole_conditions_v1",maximum_runtime_seconds=0,
        native_fail_stop_seconds=0,stop_mode="conditions")
    db.policy={"contract_version":"rootline_borehole_continuous_authority.v1","stop_mode":"conditions",
        "device_keys":["ewelink:ewelink_owner_account:1002851416:1"],"device_identities":["BOREHOLE-1-MINI-R4-CH1"],
        "allowed_channels":[1],"provider":"ewelink","provider_account_binding":"ewelink_owner_account",
        "device_id":"1002851416","maximum_runtime_seconds":0,"native_fail_stop_seconds":0,
        "application_stop_ownership_required":True,"automatic_on_retry":False,"solar_proxy_w":1500,
        "battery_floor_soc_pct":30,"forecast_start_deferral_seconds":3600,
        "forecast_deferral_once_per_opportunity":True,"rain_reassessment_seconds":3600,
        "rain_free_resume_seconds":3600,"grid_cost_estimate_zar_per_kwh":9.2,"missing_readings_alone_stop":False}
    db.policy_sha=digest(db.policy);db.device["authority_envelope"]["policy_sha256"]=db.policy_sha;db.digest=digest(db.device)
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",lambda **kw:db.factory())
    monkeypatch.setattr(runtime,"project_saved_program_for_execution",lambda *a,**k:{"candidate_tasks":[]})
    monkeypatch.setattr(managed,"run_rootline_managed_device_cycle",lambda **kw:kw["evidence_factory"](pending_devices={"BOREHOLE-1-MINI-R4-CH1"}))
    monkeypatch.setattr("modules.telemetry.weather_service.get_weather_control_snapshot",lambda *a,**k:(snapshot(NOW),200))
    monkeypatch.setattr("modules.telemetry.rootline_water_energy_plan.read_current_borehole_faults",lambda *a,**k:{"safe":True})
    def controls(*a,**k):
        owner_reads.append(True)
        return owner.project_owner_controls([],now=NOW)
    monkeypatch.setattr(owner,"load_runtime_owner_controls",controls)
    def observation(*args,**kwargs):optional.append(kwargs);return nullcontext()
    monkeypatch.setattr(requests,"optional_observation",observation)
    class Transport:
        def read_output_state(self,**kwargs):
            assert all(c.closed for c in db.connections)
            provider_reads.append(kwargs);return {"state":"OFF"}
    packet=runtime.run_rootline_managed_device_reassessment(
        environ={**(ENV if command_mode else {}),"ROOTLINE_BOREHOLE_ENABLED":"true"},
        database_url="synthetic",transport=Transport(),token_store=object(),clock=lambda:NOW,now=NOW,
        evidence_loader=lambda **kw:({},NOW.date().isoformat(),NOW),
        store=lambda action,body:{"start_eligible":False,"reason":"forecast_start_deferred"})
    assert packet.get("borehole_readiness")=="forecast_start_deferred",packet
    assert len(db.connections)==1 and db.connections[0].closed
    assert len(provider_reads)==1
    assert len(owner_reads)==len(optional)==(0 if command_mode else 1)


def test_read_cost_model_accounts_for_added_isolation_query_and_timeout_setup():
    from modules.telemetry.rootline_device_spine import CanonicalAuthorityResolver
    totals=[]
    for optimized in (False,True):
        cost=[];db=ScopedDatabase(spend=lambda kind,seconds:cost.append((kind,seconds)))
        if optimized:db.load()
        else:
            # Original shape: registry connection closes, then each resolver
            # SELECT opens its own bounded connection. SQL evidence stays fresh.
            with db.factory() as connection,connection.cursor() as cursor:
                cursor.execute("select * from app_private.rootline_device_registry",(KEY,))
                record=cursor.fetchone()[1]
            spine.validate_device(record,resolver=CanonicalAuthorityResolver(db.factory))
        assert len(db.connections)==(1 if optimized else 4)
        assert sum(kind=="query with timeout setup" for kind,_ in cost)==(5 if optimized else 4)
        totals.append(sum(seconds for _,seconds in cost))
    # Two loads save11s, plus omitted unused owner read2s=13s model.
    # .5s per SELECT explicitly includes the bounded timeout-setup overhead.
    assert totals==[10,4.5] and 2*(totals[0]-totals[1])+2==13


def test_rejected_catalog_identity_closes_before_any_fixture_mutation(monkeypatch):
    import psycopg
    import sys
    calls=[]
    class Connection:
        closed=False
        def execute(self,sql):calls.append(sql);return self
        def fetchone(self):return ("production","postgres","127.0.0.1",55485)
        def commit(self):pytest.fail("rejected target committed")
        def close(self):self.closed=True
    connection=Connection()
    monkeypatch.setattr(sys.modules[__name__],"URL","postgresql://postgres@127.0.0.1:55485/rootline_ha_command_mode_test")
    monkeypatch.setattr(psycopg,"connect",lambda *a,**k:connection)
    with pytest.raises(AssertionError):pg_connect()
    assert connection.closed and len(calls)==1 and calls[0].startswith("select current_database()")
