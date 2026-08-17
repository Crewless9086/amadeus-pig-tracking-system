import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import uuid

import psycopg
import pytest

from modules.telemetry.rootline_device_spine import load_device_record, store_device_record

URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="disposable PostgreSQL URL is required")

def connect():
    return psycopg.connect(URL)

@pytest.fixture(scope="module", autouse=True)
def exact_migration():
    with connect() as db:
        db.execute("create schema if not exists app_private")
        db.execute("""create table if not exists app_private.oom_protected_action_claims(
          callback_token text primary key)""")
        db.execute("""create table if not exists app_private.migration_log(
          migration_id text primary key,description text not null)""")
        for role in ("anon", "authenticated"):
            db.execute("do $block$ begin execute 'create role %s'; exception when duplicate_object then null; end $block$" % role)
    sql = (Path(__file__).parents[1] / "supabase" / "migrations" /
        "202608170001_add_rootline_device_registry.sql").read_text(encoding="utf-8")
    with connect() as db:
        db.execute(sql)

def device(identity, generation=1, **changes):
    row={"provider":"test_provider","provider_account_binding":"test_vault",
      "device_id":identity,"channel":1,"physical_name":"Disposable relay",
      "device_type":"generic_relay_output","adapter_profile":"test_relay",
      "safe_state":"OFF","maximum_runtime_seconds":60,"native_fail_stop_seconds":60,
      "readback":"provider_state","physical_effect":"test_only","dependencies":[],
      "manual_isolation":"test breaker","commissioning_stage":"registered",
      "standing_authority":False,"registry_generation":generation}
    row.update(changes)
    return row

def test_exact_seed_loads_and_matches_source_digest():
    row=load_device_record("ifttt_ewelink:ewelink_owner_account:100204d497:2",
      connect_factory=connect)
    assert row["device_record"]["commissioning_stage"]=="bounded_actuation_ready"
    assert row["registry_generation"]==1 and row["execution_authority"] is False

def test_concurrent_next_generation_is_one_history_append_and_one_replay():
    identity="relay-"+uuid.uuid4().hex
    first=store_device_record(device(identity),connect_factory=connect)
    updated=device(identity,2,commissioning_stage="provider_discovered")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _item:store_device_record(updated,connect_factory=connect),(1,2)))
    assert first["registry_generation"]==1
    assert sorted(result["replayed"] for result in results)==[False,True]
    key=first["device_key"]
    with connect() as db:
        count=db.execute("""select count(*) from app_private.rootline_device_registry_history
          where device_key=%s""",(key,)).fetchone()[0]
    assert count==2

def test_generation_conflict_digest_tamper_and_history_mutation_fail_closed():
    identity="relay-"+uuid.uuid4().hex
    first=store_device_record(device(identity),connect_factory=connect)
    with pytest.raises(ValueError,match="generation_conflict"):
        store_device_record(device(identity,3,commissioning_stage="readback_proven"),
          connect_factory=connect)
    with connect() as db:
        db.execute("update app_private.rootline_device_registry set evidence_digest=%s where device_key=%s",
          ("0"*64,first["device_key"]))
    with pytest.raises(ValueError,match="digest_mismatch"):
        load_device_record(first["device_key"],connect_factory=connect)
    with pytest.raises(psycopg.errors.RaiseException):
        with connect() as db:
            db.execute("delete from app_private.rootline_device_registry_history where device_key=%s",
              (first["device_key"],))
