"""Real admission transactions on isolated local PostgreSQL and canonical DDL.

The fixture rewrites schema qualification only. No live URL, model, or provider.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import psycopg
from psycopg import sql
import pytest

from modules.charlie import cloud_engineering as core
from tests.test_charlie_cloud_engineering import (
    INSTANCE, OWNER, REVISION, TOKEN, complete_artifact, manifest, reservation,
)

URL = os.getenv("CORE_ENGINEERING_POSTGRES_URL") or os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable local PostgreSQL required")


class Cursor:
    def __init__(self, raw, schema): self.raw, self.schema = raw, schema
    def __enter__(self): self.raw.__enter__(); return self
    def __exit__(self, *args): return self.raw.__exit__(*args)
    def execute(self, query, params=None):
        query = query.replace("public.", self.schema + ".").replace("app_private.", self.schema + ".")
        query = query.replace("set search_path = public,", "set search_path = " + self.schema + ",")
        self.raw.execute(query, params)
        return self
    def __getattr__(self, name): return getattr(self.raw, name)


class Connection:
    def __init__(self, raw, schema): self.raw, self.schema = raw, schema
    def __enter__(self): self.raw.__enter__(); return self
    def __exit__(self, *args): return self.raw.__exit__(*args)
    def cursor(self): return Cursor(self.raw.cursor(), self.schema)
    def execute(self, query, params=None): return self.cursor().execute(query, params)
    def close(self): self.raw.close()
    def rollback(self): self.raw.rollback()
    def __getattr__(self, name): return getattr(self.raw, name)


@pytest.fixture
def h(monkeypatch):
    parsed = psycopg.conninfo.conninfo_to_dict(URL)
    assert parsed.get("host") in {"127.0.0.1", "localhost", "::1"}
    assert not parsed.get("hostaddr") and not parsed.get("service")
    assert parsed.get("dbname", "").endswith("_test")
    schema = "core_engineering_" + uuid.uuid4().hex
    with psycopg.connect(URL) as db: db.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
    h = SimpleNamespace(schema=schema, mid="CORE-SYNTHETIC-ENGINEERING")
    h.db = lambda: Connection(psycopg.connect(URL, options="-c statement_timeout=10000"), schema)
    h.connect = lambda _url: h.db()
    h.call = lambda fn, *args, **kwargs: fn(*args, database_url="synthetic", connect_factory=h.connect, **kwargs)
    monkeypatch.setenv("CORE_CLOUD_ENGINEERING_ENABLED", "true")
    monkeypatch.setenv("RENDER_SERVICE_ID", core.API)
    monkeypatch.setenv("RENDER_GIT_COMMIT", REVISION)
    monkeypatch.setenv("OWNER_ADMIN_TOKEN", "synthetic_owner_token_" + "o" * 40)
    migrations = Path(__file__).parents[1] / "supabase/migrations"
    try:
        with h.db() as db:
            db.execute("create table app_private.migration_log(migration_id text primary key,description text not null)")
            db.execute((migrations / "202606300001_create_charlie_mission_queue.sql").read_text(encoding="utf-8"))
            source = (migrations / "202607170001_create_charlie_executive_control_plane.sql").read_text(encoding="utf-8")
            db.execute(source.split("create table if not exists public.charlie_control_commands")[0])
            # Include real hold/update/append-only triggers; do not stub the hold guard.
            source = (migrations / "202607270003_create_charlie_owner_execution_holds.sql").read_text(encoding="utf-8")
            db.execute(source.split("create or replace function public.append_charlie_owner_execution_hold(")[0])
            seed(db, h.mid)
        yield h
    finally:
        assert schema.startswith("core_engineering_") and len(schema) == 49
        with psycopg.connect(URL) as db:
            db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


def seed(db, mid):
    db.execute("""insert into public.charlie_missions
        (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json)
        values(%s,'paused','synthetic','Synthetic bounded private repair','Synthetic repair','P1','bug fix','LEVEL 3',%s::jsonb)""",
        (mid, json.dumps({"original_history": {"retained": True}, "orchestration": {"generation_identity": "synthetic"}})))
    db.execute("""insert into public.charlie_mission_events(event_id,mission_id,event_type,notes)
        values(%s,%s,'created','Synthetic initial event')""", ("created-" + mid, mid))


def row(h):
    with h.db() as db:
        return db.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s", (h.mid,)).fetchone()[0]


def snapshot(h):
    with h.db() as db:
        return {"missions": db.execute("select to_jsonb(m) from public.charlie_missions m order by mission_id").fetchall(),
                "events": db.execute("select to_jsonb(e) from public.charlie_mission_events e order by event_id").fetchall(),
                "holds": db.execute("select to_jsonb(h) from public.charlie_owner_execution_hold_events h order by event_id").fetchall()}


def proposal(h):
    ready = h.call(core.owner_read, h.mid)
    return {"manifest": manifest(), "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
            "expected_mission_sha256": ready["mission_sha256"]}


def admit(h): return h.call(core.authorize, h.mid, proposal(h), actor=OWNER)


def op(h, operation, payload, token=TOKEN):
    return h.call(core.worker_operation, h.mid, operation, payload, token)


def claim(h):
    return op(h, "claim", {"instance": INSTANCE, "worker_revision": REVISION, "worker_service": core.WORKER})


def hold(h):
    with h.db() as db:
        db.execute("""insert into public.charlie_owner_execution_hold_events
            (event_id,hold_id,mission_id,generation_identity,event_type,reason,owner_identity_hash,authorization_identity)
            values('H','H',%s,'synthetic','hold_created','Synthetic hold',%s,%s)""", (h.mid,"a"*64,"b"*64))


def test_authorization_preserves_paused_mission_history_and_has_no_secret_readback(h):
    before = snapshot(h); result = admit(h); after = snapshot(h)
    old = before["missions"][0][0]; new = after["missions"][0][0]
    assert new["status"] == old["status"] == "paused"
    assert {k:v for k,v in new.items() if k not in {"metadata_json","updated_at"}} == {k:v for k,v in old.items() if k not in {"metadata_json","updated_at"}}
    assert {k:v for k,v in new["metadata_json"].items() if k != core.KEY} == old["metadata_json"]
    assert before["events"][0] in after["events"] and len(after["events"]) == len(before["events"]) + 1
    assert result["grant"]["state"] == "issued"
    assert "token_sha256" not in result["grant"] and "owner_binding" not in result["grant"]
    stable = snapshot(h); op(h, "current", {}); assert snapshot(h) == stable


@pytest.mark.parametrize("changed", ["preimage", "mission_status", "owner", "api", "scope", "hold"])
def test_admission_refusal_has_zero_effect(h, monkeypatch, changed):
    p = proposal(h)
    if changed == "preimage": p["expected_mission_sha256"] = "0" * 64
    if changed == "api": monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    if changed == "scope": p["manifest"]["allowed_files"] = ["modules/charlie/mission_store.py"]
    if changed == "hold": hold(h)
    if changed == "mission_status":
        with h.db() as db: db.execute("update public.charlie_missions set status='approved' where mission_id=%s", (h.mid,))
    before = snapshot(h)
    with pytest.raises(core.EngineeringRefused): h.call(core.authorize, h.mid, p, actor="service:worker" if changed == "owner" else OWNER)
    assert snapshot(h) == before


def test_concurrent_authorization_and_claim_each_have_one_winner(h):
    p = proposal(h)
    def run_authorize(_):
        try: return h.call(core.authorize, h.mid, p, actor=OWNER)
        except core.EngineeringRefused: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(run_authorize, range(2)))
    assert sum(r is not None for r in results) == 1
    def run_claim(n):
        try: return op(h, "claim", {"instance": f"{n+1:032x}", "worker_revision":REVISION,"worker_service":core.WORKER})
        except core.EngineeringRefused: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(run_claim, range(2)))
    assert sum(r is not None for r in results) == 1
    assert len(snapshot(h)["events"]) == 3


@pytest.mark.parametrize("kind", ["execution_lease", "hermes_native_execution"])
@pytest.mark.parametrize("same_mission", [True, False])
def test_active_writer_lease_prevents_admission_on_same_or_other_mission(h, kind, same_mission):
    target = h.mid if same_mission else "CORE-SYNTHETIC-OTHER"
    key = "expires_at" if kind == "execution_lease" else "claim_expires_at"
    with h.db() as db:
        if not same_mission: seed(db, target)
        db.execute("update public.charlie_missions set metadata_json=metadata_json||%s::jsonb where mission_id=%s",
            (json.dumps({kind: {key:(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}}),target))
    p=proposal(h);before=snapshot(h)
    with pytest.raises(core.EngineeringRefused):h.call(core.authorize,h.mid,p,actor=OWNER)
    assert snapshot(h)==before


def test_second_engineering_mission_refuses_active_and_accepts_revoked_grant(h):
    admit(h)
    with h.db() as db: seed(db, "CORE-SYNTHETIC-OTHER")
    original = h.mid; h.mid = "CORE-SYNTHETIC-OTHER"
    with pytest.raises(core.EngineeringRefused, match="competing_writer"): admit(h)
    h.mid = original; h.call(core.revoke, h.mid, actor=OWNER)
    h.mid = "CORE-SYNTHETIC-OTHER"
    admitted=admit(h)
    assert admitted["grant"]["state"]=="issued"


def test_active_receipt_policy_refuses_new_engineering_grant(h):
    with h.db() as db:
        db.execute("""insert into public.charlie_delegation_policies(policy_id,capability,authority_tier,enabled)
            values('core.manager_dependency_intake.20261010','synthetic','auto',true)""")
    with pytest.raises(core.EngineeringRefused, match="receipt_grant_active"): admit(h)


@pytest.mark.parametrize("changed", ["owner", "api", "mission", "correction", "hold", "expired", "credential"])
def test_each_operation_rechecks_current_authority_with_zero_effect(h, monkeypatch, changed):
    admit(h); claim(h)
    if changed == "owner": monkeypatch.setenv("OWNER_ADMIN_TOKEN", "rotated_synthetic_" + "x" * 40)
    if changed == "api": monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    if changed == "hold": hold(h)
    with h.db() as db:
        if changed == "mission": db.execute("update public.charlie_missions set raw_text='New scope' where mission_id=%s", (h.mid,))
        if changed == "correction": db.execute("""insert into public.charlie_mission_events(event_id,mission_id,event_type,notes,metadata_json)
            values('correction',%s,'owner_correction_recorded','Changed allowed repair','{"source":"synthetic_owner"}')""", (h.mid,))
        if changed == "expired": db.execute("""update public.charlie_missions set metadata_json=jsonb_set(metadata_json,
            '{cloud_engineering_execution,expires_at}',to_jsonb(now()-interval '1 second')) where mission_id=%s""", (h.mid,))
    before=snapshot(h)
    with pytest.raises(core.EngineeringRefused):op(h,"reserve",reservation(),token="z"*64 if changed=="credential" else TOKEN)
    assert snapshot(h)==before


def test_reservation_replay_and_concurrency_charge_once_durably(h):
    admit(h);claim(h)
    def run(_):
        try:return op(h,"reserve",reservation())
        except core.EngineeringRefused:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sum(r is not None for r in results)==1
    state=op(h,"current",{})["grant"]
    assert state["reserved_micro_usd"]==100000 and len(state["reservations"])==1
    before=snapshot(h)
    with pytest.raises(core.EngineeringRefused,match="reservation_already_consumed"):op(h,"reserve",reservation())
    assert snapshot(h)==before


def test_eighth_reservation_survives_failure_and_ninth_never_commits(h):
    original=proposal(h);h.call(core.authorize,h.mid,original,actor=OWNER);claim(h)
    for n in range(1,9):op(h,"reserve",reservation(n))
    before=snapshot(h)
    with pytest.raises(core.EngineeringRefused,match="model_budget_exhausted"):op(h,"reserve",reservation(9))
    assert snapshot(h)==before
    blocked=op(h,"block",{"instance":INSTANCE,"reason":"synthetic_timeout"})["grant"]
    assert blocked["state"]=="blocked" and blocked["reserved_micro_usd"]==800000
    with pytest.raises(core.EngineeringRefused):op(h,"reserve",reservation(10))
    with pytest.raises(core.EngineeringRefused):h.call(core.authorize,h.mid,original,actor=OWNER)


@pytest.mark.parametrize("phase",["mission_update","audit_insert"])
def test_crash_after_either_write_rolls_back_entire_transaction(h,monkeypatch,phase):
    real=Cursor.execute
    def fail(self,query,params=None):
        result=real(self,query,params)
        if (phase=="mission_update" and query.startswith("update public.charlie_missions")) or (
                phase=="audit_insert" and query.startswith("insert into public.charlie_mission_events")):
            raise RuntimeError("synthetic injected crash")
        return result
    p=proposal(h);before=snapshot(h)
    with monkeypatch.context() as scoped:
        scoped.setattr(Cursor,"execute",fail)
        with pytest.raises(RuntimeError,match="synthetic injected crash"):h.call(core.authorize,h.mid,p,actor=OWNER)
    assert snapshot(h)==before


def test_revocation_after_hold_uses_canonical_readback_and_keeps_reservations(h):
    admit(h);claim(h);op(h,"reserve",reservation());hold(h)
    before=snapshot(h);revoked=h.call(core.revoke,h.mid,actor=OWNER)["grant"]
    assert revoked["state"]=="revoked" and revoked["reserved_micro_usd"]==100000
    assert op(h,"current",{})["grant"]["state"]=="revoked"
    with pytest.raises(core.EngineeringRefused):op(h,"reserve",reservation(2))
    after=snapshot(h)
    assert after["holds"]==before["holds"] and before["events"][0] in after["events"]
    stable=snapshot(h);h.call(core.revoke,h.mid,actor=OWNER);assert snapshot(h)==stable


def test_revocation_terminal_read_and_no_restart_after_owner_change(h,monkeypatch):
    admit(h);claim(h);op(h,"reserve",reservation())
    monkeypatch.setenv("OWNER_ADMIN_TOKEN","new_owner_"+"z"*40)
    value=h.call(core.revoke,h.mid,actor=OWNER)["grant"]
    assert value["state"]=="revoked" and value["reserved_micro_usd"]==100000
    before=snapshot(h)
    assert op(h,"current",{})["grant"]["state"]=="revoked"
    with pytest.raises(core.EngineeringRefused):claim(h)
    with pytest.raises(core.EngineeringRefused):op(h,"reserve",reservation(2))
    assert snapshot(h)==before


def test_complete_artifact_is_durable_immutable_and_terminal_replay_refused(h):
    admit(h);claim(h)
    for n, task in enumerate(("charlie_native_builder","charlie_native_security_reviewer","charlie_native_functional_reviewer"),1):
        op(h,"reserve",reservation(n,task=task))
    for stage in ("baseline_verified","candidate_prepared","tests_passed","reviews_passed"):
        op(h,"progress",{"instance":INSTANCE,"stage":stage,"artifact_sha256":"a"*64})
    state=op(h,"current",{})["grant"];artifact=complete_artifact(state)
    payload={"instance":INSTANCE,"artifact":artifact,"artifact_sha256":core.digest(artifact)}
    done=op(h,"complete",payload)["grant"]
    assert done["state"]=="artifact_ready" and done["artifact"]==artifact
    assert h.call(core.owner_read,h.mid)["grant"]["artifact_sha256"]==core.digest(artifact)
    before=snapshot(h)
    for operation, body in (("complete",payload),("reserve",reservation(4)),("block",{"instance":INSTANCE,"reason":"late"})):
        with pytest.raises(core.EngineeringRefused):op(h,operation,body)
    assert snapshot(h)==before
    revoked=h.call(core.revoke,h.mid,actor=OWNER)["grant"]
    assert revoked["state"]=="revoked" and revoked["artifact"]==artifact
    assert revoked["reserved_micro_usd"]==300000


def test_correction_between_readiness_and_authorize_refuses_stale_preimage(h):
    p=proposal(h)
    with h.db() as db:
        db.execute("""insert into public.charlie_mission_events(event_id,mission_id,event_type,notes)
            values('new-correction',%s,'owner_correction_recorded','Changed allowed repair')""",(h.mid,))
    before=snapshot(h)
    with pytest.raises(core.EngineeringRefused,match="mission_preimage_changed"):
        h.call(core.authorize,h.mid,p,actor=OWNER)
    assert snapshot(h)==before


def test_lost_reservation_response_remains_spent_and_cannot_replay(h,monkeypatch):
    admit(h);claim(h);original=core._public
    def lost(grant,**kwargs):
        if len(grant.get("reservations",[]))==1:
            raise RuntimeError("synthetic response loss after commit")
        return original(grant,**kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(core,"_public",lost)
        with pytest.raises(RuntimeError,match="response loss after commit"):op(h,"reserve",reservation())
    retained=op(h,"current",{})["grant"]
    assert len(retained["reservations"])==1 and retained["reserved_micro_usd"]==100000
    before=snapshot(h)
    with pytest.raises(core.EngineeringRefused,match="reservation_already_consumed"):op(h,"reserve",reservation())
    assert snapshot(h)==before


def test_two_distinct_final_reservations_cannot_overrun_shared_budget(h):
    p=proposal(h);p["manifest"]["budget_micro_usd"]=100000
    h.call(core.authorize,h.mid,p,actor=OWNER);claim(h)
    def reserve(n):
        try:return op(h,"reserve",reservation(n+1))
        except core.EngineeringRefused:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,range(2)))
    assert sum(r is not None for r in results)==1
    retained=op(h,"current",{})["grant"]
    assert len(retained["reservations"])==1 and retained["reserved_micro_usd"]==100000


@pytest.mark.parametrize("kind", ["missing_completion", "immutable_not_run", "unreserved_model"])
def test_false_completion_evidence_cannot_commit_artifact_or_audit(h, kind):
    admit(h); claim(h)
    for number, role in enumerate(("builder", "security_reviewer", "functional_reviewer"), 1):
        op(h, "reserve", reservation(number, task="charlie_native_" + role))
    for stage in ("baseline_verified", "candidate_prepared", "tests_passed", "reviews_passed"):
        op(h, "progress", {"instance": INSTANCE, "stage": stage, "artifact_sha256": "a" * 64})
    artifact = complete_artifact(op(h, "current", {})["grant"])
    if kind == "missing_completion": artifact["tests"].pop("completion")
    elif kind == "immutable_not_run":
        c = artifact["tests"]["completion"]; node = c["expected_test_ids"][0]
        c["outcomes"][node]["call"] = "skipped"
    else: artifact["model_calls"][0]["request_sha256"] = "0" * 64
    before = snapshot(h)
    with pytest.raises(core.EngineeringRefused):
        op(h, "complete", {"instance": INSTANCE, "artifact": artifact, "artifact_sha256": core.digest(artifact)})
    assert snapshot(h) == before
    retained = op(h, "current", {})["grant"]
    assert retained["state"] == "reviews_passed" and retained["reserved_micro_usd"] == 300000
