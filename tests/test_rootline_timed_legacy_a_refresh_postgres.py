"""Real registry/evidence/policy queries through each scheduled gateway path."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import pytest
import psycopg
from psycopg.types.json import Jsonb
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_device_registry as registry
from modules.telemetry.rootline_device_spine import store_device_record
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_capacity_edge_postgres import RealReserveJourney
from tests.test_rootline_execution_runtime import NOW
from tests.test_rootline_commissioning_bridges import record_for
from tests.test_rootline_a_camp_automation import canonical_record

URL=os.getenv("ROOTLINE_CAPACITY_EDGE_POSTGRES_URL",os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL",""))
pytestmark=pytest.mark.skipif(not URL,reason="explicit disposable database required")
REFRESH=runtime._refresh_a_irrigation_binding
ZONES={"B12345":1,"C12345":2,"A12345":4,"E12345":3}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def connect():
    target=urlparse(URL)
    assert target.hostname in {"127.0.0.1","localhost"}
    assert target.path in {"/rootline_capacity_edge_test_20261117_01","/rootline_managed"}
    return psycopg.connect(URL)

TABLES=("rootline_device_commissioning_evidence","rootline_standing_authorities",
    "rootline_device_registry","rootline_device_registry_history",
    "rootline_device_evidence_events","rootline_authority_events")

@contextmanager
def preserved_registry():
    with connect() as c:
        saved={table:c.execute("select row_to_json(t) from app_private."+table+" t").fetchall() for table in TABLES}
    try:yield
    finally:
        with connect() as c:
            c.execute("truncate "+",".join("app_private."+table for table in TABLES)+" cascade")
            for table in TABLES:
                for (row,) in saved[table]:
                    c.execute("insert into app_private."+table+" select * from jsonb_populate_record(null::app_private."+table+",%s)",(Jsonb(row),))

@pytest.fixture(scope="module",autouse=True)
def preserve_existing_registry():
    if not URL:
        yield
        return
    # Match the existing canonical spine test prerequisites. connect() checks
    # the disposable host/database before any DDL or data mutation.
    migrations=Path(runtime.__file__).resolve().parents[2] / "supabase/migrations"
    with connect() as c:
        c.execute("create extension if not exists pgcrypto")
        c.execute("create schema if not exists app_private")
        c.execute("create table if not exists app_private.migration_log(migration_id text primary key,description text not null)")
        c.execute((migrations/"202607070001_create_sam_live_stock_conversation_review_events.sql").read_text(encoding="utf-8"))
        c.execute((migrations/"202608170001_add_rootline_device_registry.sql").read_text(encoding="utf-8"))
    with preserved_registry():yield

@pytest.fixture(autouse=True)
def schema():
    if not URL:return
    target=urlparse(URL)
    assert target.hostname in {"127.0.0.1","localhost"}
    assert target.path in {"/rootline_capacity_edge_test_20261117_01","/rootline_managed"}
    # The module fixture independently prepares the canonical schema, then
    # preserves existing registry rows around this module's isolated cases.
    with connect() as c:
        c.execute("truncate app_private.rootline_device_registry_history,app_private.rootline_device_registry,app_private.rootline_device_evidence_events,app_private.rootline_authority_events,app_private.rootline_device_commissioning_evidence,app_private.rootline_standing_authorities cascade")
        c.execute("truncate public.sam_live_stock_conversation_review_events")

def seed(*,missing=None,legacy_a=False):
    result={}
    for zone,ch in ZONES.items():
        if zone==missing:continue
        key=f"ifttt_ewelink:ewelink_owner_account:100204e9bc:{ch}"
        row=record_for(key,"gravity_irrigation_valve",7200)
        row.update(stop_mode="scheduled",native_fail_stop_seconds=0,
            physical_effect=zone+" irrigation water flow")
        policy={"contract_version":"rootline_timed_standing_authority.v1","stop_mode":"scheduled",
            "device_keys":[key],"zone_ids":[zone],"allowed_channels":[ch],"device_id":"100204e9bc",
            "provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account",
            "maximum_runtime_seconds":7200,"application_timeout_required":True,"automatic_on_retry":False}
        refs={name:{"evidence_id":zone+":"+name,"source":"canonical","observed_at":NOW.isoformat(),
            "sha256":digest({"zone":zone,"evidence":name})} for name in ("owner_configuration","provider_readback")}
        if zone=="A12345" and legacy_a:
            row=canonical_record();refs=row["commissioning_evidence"];policy={}
        envelope=row["authority_envelope"]
        envelope.update(standing_authority_id="TEST-AUTH-"+zone,policy_sha256=digest(policy))
        row["commissioning_evidence"]=refs
        with connect() as c:
            for ref in refs.values():
                c.execute("insert into app_private.rootline_device_commissioning_evidence(evidence_id,source,observed_at,evidence_sha256,evidence_payload) values(%s,%s,%s,%s,%s)",
                    (ref["evidence_id"],ref["source"],ref["observed_at"],ref["sha256"],Jsonb({"test":True})))
            c.execute("insert into app_private.rootline_standing_authorities(standing_authority_id,version,issuer,policy_sha256,active,revoked,policy_payload) values(%s,'1','owner_policy',%s,true,false,%s)",
                (envelope["standing_authority_id"],envelope["policy_sha256"],Jsonb(policy)))
        store_device_record(row,connect_factory=connect)
        result[zone]=row
    return result

class RegistryJourney(RealReserveJourney):
    def __init__(self,patch,zone="B12345",*,revoke_final=False):
        super().__init__(patch,sql_seconds=.1,connect_seconds=.2)
        # Undo the previous capacity fixture's refresh isolation. Both legacy
        # and scheduled authority resolution below use actual PostgreSQL.
        patch.setattr(runtime,"_refresh_a_irrigation_binding",REFRESH)
        self.zone=zone;self.channel=ZONES[zone]
        self.registry_authority_calls=0
        self.connections=0
        from modules.oom_sakkie import bounded_postgres_read as bounded
        previous=bounded.connect_bounded_rootline_postgres
        def counted(**kwargs):
            self.connections+=1
            return previous(**kwargs)
        patch.setattr(bounded,"connect_bounded_rootline_postgres",counted)
        def authority(database_url,artifact):
            self.registry_authority_calls+=1
            value=runtime._canonical_standing_authority_proven(URL,artifact)
            if revoke_final and self.registry_authority_calls==1:
                revoke(zone)
            return value
        self.authority=authority

def revoke(zone):
    with connect() as c:c.execute("insert into app_private.rootline_authority_events(event_id,standing_authority_id,version,event_type,reason) values(%s,%s,'1','revoked','test only')",("REVOKE-"+zone,"TEST-AUTH-"+zone))

@pytest.mark.parametrize("zone",list(ZONES))
def test_all_four_gateway_paths_keep_real_fresh_scheduled_authority(monkeypatch,zone):
    seed();j=RegistryJourney(monkeypatch,zone)
    value,_=j.gateway()
    assert j.controls[0]["status"]=="segment_started",j.controls
    assert j.registry_authority_calls==2 and j.evidence_reads==2 and len(j.reads)==3
    assert j.borehole_checks==1 and value["managed_device_result"]["status"]=="borehole_active"
    assert [x["state"] for x in j.calls]==["ON"]
    with timed_control_scope(j.source):expected=registry.get_device_contract(zone)["contract_sha256"]
    assert j.backing.active["controller_safety_generation"]==expected
    assert registry._canonical_irrigation_binding.get() is None
    # Two fresh selected authority transactions each execute registry, two
    # evidence, resolver authority and explicit scoped policy reads.
    policy_reads=[r for r in j.sql_trace if "select issuer,policy_payload" in r["sql"]]
    assert len(policy_reads)==2

@pytest.mark.parametrize("case",["missing","revoked","bad_digest","invalid_evidence","conflicting_policy"])
@pytest.mark.parametrize("zone",list(ZONES))
def test_selected_authority_failures_do_not_widen_eligibility(monkeypatch,case,zone):
    records=seed(missing=zone if case=="missing" else None)
    if case=="revoked":revoke(zone)
    if case=="bad_digest":
        with connect() as c:c.execute("update app_private.rootline_device_registry set evidence_digest=%s where device_key=%s",("0"*64,f"ifttt_ewelink:ewelink_owner_account:100204e9bc:{ZONES[zone]}"))
    if case=="invalid_evidence":
        with connect() as c:c.execute("insert into app_private.rootline_device_evidence_events(event_id,evidence_id,event_type,reason) values(%s,%s,'invalidated','test')",("INVALID-"+zone,zone+":provider_readback"))
    if case=="conflicting_policy":
        # A different selected device cannot borrow another zone's envelope.
        record=deepcopy(records[zone]);record["authority_envelope"]=records[next(z for z in ZONES if z!=zone)]["authority_envelope"]
        with connect() as c:c.execute("update app_private.rootline_device_registry set device_record=%s,evidence_digest=%s where device_key=%s",(Jsonb(record),digest(record),f"ifttt_ewelink:ewelink_owner_account:100204e9bc:{ZONES[zone]}"))
    j=RegistryJourney(monkeypatch,zone);j.gateway()
    assert j.calls==[]
    assert not any(a=="claim_before_on" for a,_ in j.backing.rows)

@pytest.mark.parametrize("zone",list(ZONES))
def test_revocation_between_initial_and_final_remains_fresh(monkeypatch,zone):
    seed();j=RegistryJourney(monkeypatch,zone,revoke_final=True);j.gateway()
    assert j.registry_authority_calls==2
    assert j.calls==[] and not any(a=="claim_before_on" for a,_ in j.backing.rows)

@pytest.mark.parametrize("zone",list(ZONES))
def test_mixed_legacy_A_cannot_substitute_scheduled_authority(monkeypatch,zone):
    seed(legacy_a=True);j=RegistryJourney(monkeypatch,zone);j.gateway()
    if zone=="A12345":assert j.calls==[]
    else:assert j.controls[0]["status"]=="segment_started"


def test_ordinary_legacy_refresh_keeps_real_binding_and_contract_digest(monkeypatch):
    seed(legacy_a=True)
    source={"ROOTLINE_A_ENABLED":"true","ROOTLINE_TIMED_CONTROL_ENABLED":"false","DATABASE_URL":URL}
    token=registry._canonical_irrigation_binding.set(None)
    try:
        REFRESH(source,URL,NOW)
        binding=deepcopy(registry._canonical_irrigation_binding.get())
        assert binding and binding["commissioned"] is True
        expected=registry.get_device_contract("A12345")["contract_sha256"]
        REFRESH(source,URL,NOW)
        assert registry._canonical_irrigation_binding.get()==binding
        assert registry.get_device_contract("A12345")["contract_sha256"]==expected
    finally:registry._canonical_irrigation_binding.reset(token)


def test_timed_entry_clears_stale_binding_and_outer_scope_restores_on_error(monkeypatch):
    seed();j=RegistryJourney(monkeypatch)
    original=j.loader
    seen=[]
    def loader(**kwargs):
        seen.append(registry._canonical_irrigation_binding.get())
        raise RuntimeError("synthetic evidence unavailable")
    j.loader=loader
    stale={"commissioned":True,"commissioning_generation":123}
    token=registry._canonical_irrigation_binding.set(stale)
    try:
        j.gateway()
        assert seen==[None]
        assert registry._canonical_irrigation_binding.get() is stale
        assert not j.calls
    finally:registry._canonical_irrigation_binding.reset(token)
