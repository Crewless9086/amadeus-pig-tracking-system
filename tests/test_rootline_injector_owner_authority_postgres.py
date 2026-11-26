"""Actual canonical registry and owner-intake transaction gates; local disposable DB only."""
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
import pytest
from modules.telemetry import rootline_timed_control as timed
from modules.telemetry import rootline_owner_controls as owner
from modules.telemetry import rootline_command_acceptance as ca
from tests.test_rootline_owner_controls_postgres import database_url, sql, settings_request, preview_apply
from tests.test_rootline_injector_owner_authority import CanonicalDatabase, KEY, IDENTITY, setup

@pytest.fixture
def canonical(sql):
    now=datetime.now(timezone.utc)
    fixture=CanonicalDatabase(now)
    authority="isolated-injector-"+uuid4().hex
    fixture.device["authority_envelope"]["standing_authority_id"]=authority
    for proof in fixture.device["commissioning_evidence"].values():
        proof["evidence_id"]="isolated-proof-"+uuid4().hex
    with psycopg.connect(sql) as c:
        c.execute("create extension if not exists pgcrypto")
        c.execute(Path("supabase/migrations/202608170001_add_rootline_device_registry.sql").read_text("utf-8"))
        c.execute("insert into app_private.rootline_standing_authorities(standing_authority_id,version,issuer,policy_sha256,active,policy_payload) values(%s,'1','owner_policy',%s,true,%s)",(authority,fixture.policy_sha,Jsonb(fixture.policy)))
        for proof in fixture.device["commissioning_evidence"].values():
            c.execute("insert into app_private.rootline_device_commissioning_evidence(evidence_id,source,observed_at,evidence_sha256,current,evidence_payload) values(%s,%s,%s,%s,true,'{}')",(proof["evidence_id"],proof["source"],proof["observed_at"],proof["sha256"]))
        c.execute("insert into app_private.rootline_device_registry(device_key,contract_version,device_record,commissioning_stage,standing_authority_id,standing_authority_version,evidence_digest,registry_generation) values(%s,'rootline_device_spine.v1',%s,'standing_active',%s,'1',%s,2) on conflict(device_key) do update set device_record=excluded.device_record,commissioning_stage=excluded.commissioning_stage,standing_authority_id=excluded.standing_authority_id,standing_authority_version=excluded.standing_authority_version,evidence_digest=excluded.evidence_digest,registry_generation=2,authority_revoked=false",(KEY,Jsonb(fixture.device),authority,ca.digest(fixture.device)))
    fields=fixture.records[0]["context"]["change"]["changes"]["fields"]
    preview_apply(sql,settings_request(sql,device="injection",fields=fields,now=now),now=now)
    artifact=setup()[-1]
    return sql,authority,fields,artifact

def locked(c,artifact):
    c.execute("select pg_advisory_xact_lock(1874320911)")
    c.execute("select pg_advisory_xact_lock(1874320912)")
    return timed.locked_owner_injector_authority(c,artifact)

def test_real_registry120_saved600_passes_claim_and_edge_gate(canonical):
    url,authority,fields,artifact=canonical
    with psycopg.connect(url) as c:
        assert locked(c,artifact)
        assert owner.bind_owner_start(c,IDENTITY,artifact)
        assert owner.owner_start_allowed(c,IDENTITY,now=datetime.now(timezone.utc),execution=artifact)
        row=c.execute("select device_record->>'maximum_runtime_seconds',registry_generation from app_private.rootline_device_registry where device_key=%s",(KEY,)).fetchone()
        assert row==("120",2)

@pytest.mark.parametrize("change",["revoked","paused","duration","camp"])
def test_real_change_after_admission_blocks_locked_new_start(canonical,change):
    url,authority,fields,artifact=canonical
    with psycopg.connect(url) as c:
        assert locked(c,artifact)
    if change=="revoked":
        with psycopg.connect(url) as c:
            c.execute("insert into app_private.rootline_authority_events(event_id,standing_authority_id,version,event_type,reason) values(%s,%s,'1','revoked','isolated regression')",(uuid4().hex,authority))
    else:
        changed=dict(fields)
        if change=="duration":changed["pulse_minutes"]=9
        if change=="camp":changed["inject_camp_b"]=False
        preview_apply(url,settings_request(url,device="injection",fields=changed,mode="paused" if change=="paused" else "automatic",key="preview-change"),key="apply-change")
    with psycopg.connect(url) as c:
        if change=="revoked":
            with pytest.raises(ValueError,match="standing_authority_unresolved"):
                locked(c,artifact)
        else:
            assert not locked(c,artifact)
