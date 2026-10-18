"""Actual hosted adapter -> canonical intake on existing disposable PG schema."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import pytest

from modules.charlie import cloud_intake as cloud
from tests.test_charlie_manager_dependency_intake_postgres import dbcase, snapshot
from tests.test_charlie_cloud_intake import TOKEN, REVISION

pytestmark = pytest.mark.skipif(not os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL"), reason="explicit isolated PostgreSQL required")


@pytest.fixture
def h(dbcase, monkeypatch):
    h=dbcase
    monkeypatch.setattr(cloud,"MISSION_ID",h.mission["mission_id"])
    monkeypatch.setattr(cloud,"POLICY_ID",h.policy["policy_id"])
    monkeypatch.setattr(cloud,"CASE_IDS",frozenset(d["case_id"] for d in h.deps))
    monkeypatch.setenv("CORE_CLOUD_INTAKE_ENABLED","true")
    monkeypatch.setenv("RENDER_GIT_COMMIT",REVISION)
    monkeypatch.setenv("RENDER_SERVICE_ID",cloud.API_SERVICE)
    with h.db() as db:
        db.execute("update public.charlie_delegation_policies set enabled=false,expires_at=now()-interval '1 day',metadata_json=%s::jsonb",
                   (json.dumps({"source_revision":"d"*40,"execution_epoch_transition":{"next_activation_id":"sealed-windows","history":["untouched"]}}),))
        db.execute("insert into public.charlie_mission_events(event_id,mission_id,event_type,notes,metadata_json) values('ORIGINAL-CREATED',%s,'created','original',%s::jsonb)",
                   (h.mission["mission_id"],json.dumps({"original":True})))
    h.cloud=lambda fn,*args,**kwargs:fn(*args,connect_factory=h.connect,**kwargs)
    yield h


def proposal(h):
    ready=h.cloud(cloud.readiness)
    return {k:ready[k] for k in ("policy_sha256","mission_sha256","created_sha256","scope_sha256")} | {
        "duration_seconds":1200,"worker_token_sha256":hashlib.sha256(TOKEN.encode()).hexdigest(),
        "provider":{"worker_service_id":cloud.WORKER_SERVICE,"worker_deploy_id":"dep-"+"c"*20,
            "worker_revision":REVISION,"api_service_id":cloud.API_SERVICE,"api_deploy_id":"dep-"+"d"*20,
            "api_revision":REVISION,
            # A freshly observed provider precedes commissioning; leave 1s for
            # Docker/host clock adjustment without relaxing production checks.
            "observed_at":(datetime.fromisoformat(ready["server_time"])-timedelta(seconds=1)).isoformat(),
            "evidence_sha256":"e"*64}}


def prepare(h):
    prepared=h.cloud(cloud.create_epoch,proposal(h),actor="owner-admin:synthetic")
    return h.cloud(cloud.set_enabled,prepared["epoch"]["epoch_id"],{"policy_sha256":prepared["policy_sha256"]},
                   enabled=True,actor="owner-admin:synthetic")


def packet(epoch, request_id="1"*32, instance="2"*32):
    return {"epoch_id":epoch["epoch"]["epoch_id"],"request_id":request_id,"worker_instance":instance,
            "worker_service_id":cloud.WORKER_SERVICE,"worker_revision":REVISION}


def policy_row(h):
    with h.db() as db:
        return db.execute("select to_jsonb(p) from public.charlie_delegation_policies p").fetchone()[0]


def test_readiness_is_readonly_and_initial_current_is_inert(h):
    before=snapshot(h);old=policy_row(h)
    ready=h.cloud(cloud.readiness)
    assert ready["enabled"] is False and all(r["counts"]==[0,0,0] for r in ready["receipts"])
    assert h.cloud(cloud.current,TOKEN)["status"]=="awaiting_epoch"
    assert snapshot(h)==before and policy_row(h)==old


def test_epoch_preserves_child_created_original_scope_and_full_prior_policy_audit(h):
    before=snapshot(h);old=policy_row(h)
    result=h.cloud(cloud.create_epoch,proposal(h),actor="owner-admin:synthetic")
    after=snapshot(h);new=policy_row(h)
    assert result["enabled"] is False
    assert after["mission"]==before["mission"] and after["cases"]==before["cases"]
    assert new["scope_json"]==old["scope_json"]
    for key,value in old["metadata_json"].items(): assert new["metadata_json"][key]==value
    audits=[r[0] for r in after["findings"] if r[0]["event_type"]=="review_note"]
    assert len(audits)==1 and audits[0]["metadata_json"]["prior_policy"]==old
    assert [r for r in after["findings"] if r[0]["event_type"]=="created"]==before["findings"]


def test_actual_receipt_cycle_and_replay_keep_two_canonical_receipts_and_cases(h):
    admitted=prepare(h);before=snapshot(h)
    first=h.cloud(cloud.cycle,packet(admitted),TOKEN)
    assert first["success"] is True,first
    after=snapshot(h)
    assert after["cases"]==before["cases"] and len(after["commands"])==2
    assert len([r for r in after["findings"] if r[0]["event_type"]=="finding_recorded"])==2
    assert len([r for r in after["manager_events"] if r[0]["event_payload"].get("engineering_intake")])==2
    again=h.cloud(cloud.cycle,packet(admitted),TOKEN)
    assert again==first and snapshot(h)==after
    ready=h.cloud(cloud.readiness)
    assert all(r["verified"] and r["counts"]==[1,1,1] for r in ready["receipts"])
    assert ready["epoch"]["cycles"][0]["status"]=="completed"


@pytest.mark.parametrize("drift",["policy","mission","created","scope","duration","provider"])
def test_create_rejects_full_row_and_identity_drift_without_effect(h,drift):
    p=proposal(h)
    if drift in {"policy","mission","created","scope"}: p[drift+"_sha256"]="f"*64
    elif drift=="duration":p["duration_seconds"]=1201
    else:p["provider"]["api_revision"]="d"*40
    before=snapshot(h);old=policy_row(h)
    with pytest.raises((cloud.CloudIntakeRefused,cloud.intake.IntakeRefused)):
        h.cloud(cloud.create_epoch,p,actor="owner-admin:synthetic")
    assert snapshot(h)==before and policy_row(h)==old


def test_two_concurrent_creates_have_one_full_row_cas_winner(h):
    p=proposal(h)
    def run(_):
        try:return h.cloud(cloud.create_epoch,p,actor="owner-admin:synthetic")
        except cloud.CloudIntakeRefused:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sum(r is not None for r in results)==1
    assert len([r for r in snapshot(h)["findings"] if r[0]["event_type"]=="review_note"])==1


@pytest.mark.parametrize("stage",["audit_write","audit_readback"])
def test_failure_after_policy_cas_rolls_back_both_effects(h,monkeypatch,stage):
    original=cloud.mission_store.record_mission_event
    def failed(*a,**kw):
        result=original(*a,**kw)
        if stage=="audit_write":return {"success":False},503
        db=kw["connect_factory"]("unused").__enter__()
        with db.cursor() as cur:cur.execute("delete from public.charlie_mission_events where event_type='review_note'")
        return result
    monkeypatch.setattr(cloud.mission_store,"record_mission_event",failed)
    p=proposal(h);before=snapshot(h);old=policy_row(h)
    with pytest.raises(cloud.CloudIntakeRefused):h.cloud(cloud.create_epoch,p,actor="owner-admin:synthetic")
    assert snapshot(h)==before and policy_row(h)==old


@pytest.mark.parametrize("change",["token","epoch","instance","revision","hold","lease","generation"])
def test_cycle_safety_fences_cannot_create_receipts(h,change):
    admitted=prepare(h);p=packet(admitted);token=TOKEN
    if change=="token":token="b"*64
    if change=="epoch":p["epoch_id"]="e"*32
    if change=="revision":p["worker_revision"]="e"*40
    with h.db() as db:
        if change=="instance":db.execute("update public.charlie_delegation_policies set metadata_json=jsonb_set(metadata_json,'{cloud_receipt_epoch,worker_instance}',%s::jsonb)",(json.dumps("e"*32),))
        if change=="lease":db.execute("update public.charlie_missions set metadata_json=metadata_json||%s::jsonb",(json.dumps({"execution_lease":{"worker":"other"}}),))
        if change=="generation":db.execute("update app_private.oom_manager_cases set generation=generation+1")
        if change=="hold":db.execute("""insert into public.charlie_owner_execution_hold_events
            (event_id,hold_id,mission_id,generation_identity,event_type,reason,owner_identity_hash,authorization_identity)
            values('H','H',%s,'g','hold_created','test',%s,%s)""",(h.mission["mission_id"],"a"*64,"b"*64))
    try:
        result=h.cloud(cloud.cycle,p,token)
        assert result["success"] is False
    except (cloud.CloudIntakeRefused,cloud.intake.IntakeRefused):pass
    assert not snapshot(h)["commands"]


def test_revocation_between_cycle_admission_and_consumer_refuses_business_writes(h,monkeypatch):
    admitted=prepare(h);real=cloud.intake.consume_manager_dependencies
    def revoke(**kw):
        ready=h.cloud(cloud.readiness)
        h.cloud(cloud.set_enabled,ready["epoch"]["epoch_id"],{"policy_sha256":ready["policy_sha256"]},enabled=False,actor="owner-admin:synthetic")
        return real(**kw)
    monkeypatch.setattr(cloud.intake,"consume_manager_dependencies",revoke)
    result=h.cloud(cloud.cycle,packet(admitted),TOKEN)
    assert result["success"] is False and not snapshot(h)["commands"]
    assert policy_row(h)["enabled"] is False


def test_ambiguous_begun_cycle_never_reexecutes_on_duplicate(h,monkeypatch):
    admitted=prepare(h)
    def crash(**kw):raise RuntimeError("simulated process loss after begun commit")
    monkeypatch.setattr(cloud.intake,"consume_manager_dependencies",crash)
    with pytest.raises(RuntimeError):h.cloud(cloud.cycle,packet(admitted),TOKEN)
    with pytest.raises(cloud.CloudIntakeRefused,match="cycle_outcome_pending_owner_readback"):
        h.cloud(cloud.cycle,packet(admitted),TOKEN)
    assert not snapshot(h)["commands"]


def test_expiry_refuses_cycle_but_owner_can_revoke(h):
    admitted=prepare(h)
    with h.db() as db:
        db.execute("update public.charlie_delegation_policies set expires_at=now()-interval '1 second',metadata_json=jsonb_set(metadata_json,'{cloud_receipt_epoch,expires_at}',to_jsonb(now()-interval '1 second'))")
    ready=h.cloud(cloud.readiness)
    with pytest.raises(cloud.CloudIntakeRefused):h.cloud(cloud.cycle,packet(admitted),TOKEN)
    result=h.cloud(cloud.set_enabled,admitted["epoch"]["epoch_id"],{"policy_sha256":ready["policy_sha256"]},enabled=False,actor="owner-admin:synthetic")
    assert result["enabled"] is False and result["epoch"]["status"]=="revoked"


def test_generic_direct_and_executive_consumers_cannot_borrow_cloud_epoch(h):
    from modules.charlie import executive_runtime
    admitted=prepare(h)
    p=policy_row(h);p["scope"]=p["scope_json"]
    direct=cloud.intake.consume_manager_dependencies(mode="active",policies=[p],connect_factory=h.connect)
    assert direct["failures"]==1 and not snapshot(h)["commands"]
    reply,code=executive_runtime.run_manager_dependency_intake_cycle(policy_id=cloud.POLICY_ID,
        scope_sha256=admitted["scope_sha256"],connect_factory=h.connect)
    assert code==503 and reply["success"] is False and not snapshot(h)["commands"]


def test_later_cycle_replays_receipts_and_persists_second_observation(h,monkeypatch):
    admitted=prepare(h)
    assert h.cloud(cloud.cycle,packet(admitted),TOKEN)["success"]
    monkeypatch.setattr(cloud,"POLL_SECONDS",0)  # avoid sleeping; production spacing tested separately
    result=h.cloud(cloud.cycle,packet(admitted,request_id="3"*32),TOKEN)
    assert result["success"] and all(r["status"]=="intake_exact_replay" for r in result["intake"]["results"])
    ready=h.cloud(cloud.readiness)
    assert len(ready["epoch"]["cycles"])==2 and all(r["verified"] for r in ready["receipts"])
    assert len(snapshot(h)["commands"])==2


def test_rapid_new_request_is_refused_without_duplicate_business_effects(h):
    admitted=prepare(h)
    assert h.cloud(cloud.cycle,packet(admitted),TOKEN)["success"]
    with pytest.raises(cloud.CloudIntakeRefused,match="cycle_too_soon"):
        h.cloud(cloud.cycle,packet(admitted,request_id="3"*32),TOKEN)
    assert len(snapshot(h)["commands"])==2


@pytest.mark.parametrize("changed",["hold","generation","scope"])
def test_owner_can_read_and_revoke_after_business_readiness_fails(h,changed):
    admitted=prepare(h)
    with h.db() as db:
        if changed=="hold":db.execute("""insert into public.charlie_owner_execution_hold_events
            (event_id,hold_id,mission_id,generation_identity,event_type,reason,owner_identity_hash,authorization_identity)
            values('H','H',%s,'g','hold_created','test',%s,%s)""",(h.mission["mission_id"],"a"*64,"b"*64))
        if changed=="generation":db.execute("update app_private.oom_manager_cases set generation=generation+1")
        if changed=="scope":db.execute("update public.charlie_delegation_policies set scope_json=jsonb_set(scope_json,'{mission_id}','\"OTHER\"'::jsonb)")
    with pytest.raises((cloud.CloudIntakeRefused,cloud.intake.IntakeRefused)):h.cloud(cloud.readiness)
    observed=h.cloud(cloud.evidence,admitted["epoch"]["epoch_id"])
    result=h.cloud(cloud.set_enabled,admitted["epoch"]["epoch_id"],{"policy_sha256":observed["policy_sha256"]},
                   enabled=False,actor="owner-admin:synthetic")
    assert result["enabled"] is False
    final=h.cloud(cloud.evidence,admitted["epoch"]["epoch_id"])
    assert final["epoch"]["status"]=="revoked" and final["audits"][-1]["operation"]=="revoked"


def test_current_epoch_drift_is_refused_inside_canonical_locked_transaction(h,monkeypatch):
    admitted=prepare(h);real=cloud.intake.consume_manager_dependencies
    def replace_epoch(**kw):
        with h.db() as db:
            db.execute("update public.charlie_delegation_policies set metadata_json=jsonb_set(metadata_json,'{cloud_receipt_epoch,worker_instance}',%s::jsonb)",(json.dumps("e"*32),))
        return real(**kw)
    monkeypatch.setattr(cloud.intake,"consume_manager_dependencies",replace_epoch)
    result=h.cloud(cloud.cycle,packet(admitted),TOKEN)
    assert result["success"] is False
    assert all(r["reason"]=="cloud_epoch_context_changed" for r in result["intake"]["results"])
    assert not snapshot(h)["commands"]


def test_simultaneous_same_cycle_has_one_consumer_and_pending_duplicate(h,monkeypatch):
    from threading import Event
    admitted=prepare(h);real=cloud.intake.consume_manager_dependencies
    entered=Event();release=Event();calls=[]
    def held(**kw):
        calls.append(1);entered.set()
        assert release.wait(5)
        return real(**kw)
    monkeypatch.setattr(cloud.intake,"consume_manager_dependencies",held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(h.cloud,cloud.cycle,packet(admitted),TOKEN)
        try:
            assert entered.wait(5)
            with pytest.raises(cloud.CloudIntakeRefused,match="cycle_outcome_pending_owner_readback"):
                h.cloud(cloud.cycle,packet(admitted),TOKEN)
        finally:release.set()
        assert first.result(timeout=8)["success"] is True
    assert calls==[1] and len(snapshot(h)["commands"])==2


def test_lost_cycle_completion_stays_begun_with_independent_receipt_readback(h,monkeypatch):
    admitted=prepare(h);real=cloud._save
    def crash(cur,db,old,updated,kind,actor,now):
        value=real(cur,db,old,updated,kind,actor,now)
        if kind=="cycle_completed":raise RuntimeError("synthetic crash before completion commit")
        return value
    monkeypatch.setattr(cloud,"_save",crash)
    with pytest.raises(RuntimeError):h.cloud(cloud.cycle,packet(admitted),TOKEN)
    evidence=h.cloud(cloud.evidence,admitted["epoch"]["epoch_id"])
    assert all(r["verified"] for r in evidence["receipts"])
    assert evidence["epoch"]["cycles"][0]["status"]=="begun"
    with pytest.raises(cloud.CloudIntakeRefused,match="cycle_outcome_pending_owner_readback"):
        h.cloud(cloud.cycle,packet(admitted),TOKEN)
    assert len(snapshot(h)["commands"])==2


def failed_partial_epoch(h, monkeypatch):
    """Real first transaction commits; fail before its independent link transaction."""
    admitted = prepare(h)
    real_one = cloud.intake._one_dependency
    real_open = cloud.intake._open
    first_case = h.deps[0]["case_id"]
    def fail_between_transactions(expected, dep, url, factory, deadline, cloud_epoch=None):
        if dep["case_id"] != first_case:
            raise TimeoutError("synthetic shared budget exhausted")
        opens = [0]
        def connect(*args, **kwargs):
            opens[0] += 1
            if opens[0] == 2:
                raise TimeoutError("synthetic stop after committed pair")
            return real_open(*args, **kwargs)
        with monkeypatch.context() as local:
            local.setattr(cloud.intake, "_open", connect)
            return real_one(expected, dep, url, factory, deadline, cloud_epoch)
    with monkeypatch.context() as local:
        local.setattr(cloud.intake, "_one_dependency", fail_between_transactions)
        failed = h.cloud(cloud.cycle, packet(admitted), TOKEN)
    assert failed["success"] is False and failed["intake"]["failures"] == 2
    evidence = h.cloud(cloud.evidence, admitted["epoch"]["epoch_id"])
    assert [r["counts"] for r in evidence["receipts"]] == [[1,1,0],[0,0,0]]
    revoked = h.cloud(cloud.set_enabled, admitted["epoch"]["epoch_id"],
        {"policy_sha256": evidence["policy_sha256"]}, enabled=False, actor="owner-admin:synthetic")
    return revoked


def recovery_proposal(h):
    ready = h.cloud(cloud.readiness)
    p = proposal(h)
    p["recovery"] = ready["recovery"]
    p["worker_token_sha256"] = hashlib.sha256(("b" * 64).encode()).hexdigest()
    return p


def test_explicit_recovery_preserves_failed_history_and_finishes_same_receipts(h, monkeypatch):
    failed = failed_partial_epoch(h, monkeypatch)
    before = snapshot(h); prior_policy = policy_row(h)
    p = recovery_proposal(h)
    assert p["recovery"]["prior_epoch_id"] == failed["epoch"]["epoch_id"]
    # Readiness/proposal never renews a grant or writes a receipt.
    assert snapshot(h) == before and policy_row(h) == prior_policy
    prepared = h.cloud(cloud.create_epoch, p, actor="owner-admin:synthetic")
    assert prepared["epoch"]["epoch_id"] != failed["epoch"]["epoch_id"]
    assert prepared["epoch"]["recovery"] == p["recovery"] and prepared["enabled"] is False
    assert snapshot(h)["commands"] == before["commands"]
    enabled = h.cloud(cloud.set_enabled, prepared["epoch"]["epoch_id"],
        {"policy_sha256": prepared["policy_sha256"]}, enabled=True, actor="owner-admin:synthetic")
    result = h.cloud(cloud.cycle, packet(enabled, request_id="4"*32, instance="5"*32), "b"*64)
    assert result["success"] is True, result
    assert result["model_calls"] == result["farm_actions"] == 0
    assert result["mission_pickup_attempted"] is False
    evidence = h.cloud(cloud.evidence, enabled["epoch"]["epoch_id"])
    assert all(r["counts"] == [1,1,1] and r["verified"] for r in evidence["receipts"])
    after = snapshot(h)
    assert after["cases"] == before["cases"]
    assert before["commands"][0] in after["commands"]
    assert all(row in after["findings"] for row in before["findings"])
    audits = [r[0] for r in after["findings"] if r[0]["event_type"] == "review_note"]
    assert any(r["metadata_json"].get("prior_policy") == prior_policy for r in audits)
    monkeypatch.setattr(cloud, "POLL_SECONDS", 0)
    later = h.cloud(cloud.cycle, packet(enabled, request_id="6"*32, instance="5"*32), "b"*64)
    assert later["success"] and all(r["status"] == "intake_exact_replay" for r in later["intake"]["results"])
    assert snapshot(h)["commands"] == after["commands"]


@pytest.mark.parametrize("drift", ["missing", "epoch", "request", "digest", "extra", "token"])
def test_partial_recovery_requires_exact_explicit_owner_preimage_and_new_token(h, monkeypatch, drift):
    failed_partial_epoch(h, monkeypatch)
    p = recovery_proposal(h)
    if drift == "missing": del p["recovery"]
    elif drift == "epoch": p["recovery"]["prior_epoch_id"] = "e"*32
    elif drift == "request": p["recovery"]["prior_request_id"] = "e"*32
    elif drift == "digest": p["recovery"]["receipt_state_sha256"] = "e"*64
    elif drift == "extra": p["recovery"]["resume_builder"] = True
    else: p["worker_token_sha256"] = hashlib.sha256(TOKEN.encode()).hexdigest()
    before = snapshot(h); old = policy_row(h)
    with pytest.raises((cloud.CloudIntakeRefused, cloud.intake.IntakeRefused)):
        h.cloud(cloud.create_epoch, p, actor="owner-admin:synthetic")
    assert snapshot(h) == before and policy_row(h) == old


@pytest.mark.parametrize("drift", ["payload", "result", "recorded_by", "begun", "recovery_chain", "wrong_failure", "wrong_request", "prior_scope", "prior_expiry"])
def test_readiness_never_offers_recovery_for_unverified_or_ineligible_pair(h, monkeypatch, drift):
    failed_partial_epoch(h, monkeypatch)
    with h.db() as db:
        if drift == "payload": db.execute("update public.charlie_control_commands set payload_json=payload_json||%s::jsonb", (json.dumps({"unexpected":True}),))
        elif drift == "result": db.execute("update public.charlie_control_commands set result_json=result_json||%s::jsonb", (json.dumps({"repair_verified":True}),))
        elif drift == "recorded_by": db.execute("update public.charlie_mission_events set recorded_by='other' where event_type='finding_recorded'")
        else:
            policy = db.execute("select to_jsonb(p) from public.charlie_delegation_policies p").fetchone()[0]
            epoch = policy["metadata_json"][cloud.META_KEY]
            if drift == "begun": epoch["cycles"][0]["status"] = "begun"
            elif drift == "recovery_chain": epoch["recovery"] = {"prior_epoch_id":"a"*32}
            elif drift == "wrong_failure": epoch["cycles"][0]["result"]["intake"]["results"][0]["failure_kind"] = "OtherError"
            elif drift == "prior_scope": epoch["scope_sha256"] = "e"*64
            elif drift == "prior_expiry": epoch["expires_at"] = "2026-01-01T00:00:00+00:00"
            else: epoch["cycles"][0]["result"]["request_id"] = "e"*32
            db.execute("update public.charlie_delegation_policies set metadata_json=%s::jsonb", (json.dumps(policy["metadata_json"]),))
    before = snapshot(h); old = policy_row(h)
    with pytest.raises((cloud.CloudIntakeRefused, cloud.intake.IntakeRefused)):
        h.cloud(cloud.readiness)
    assert snapshot(h) == before and policy_row(h) == old


@pytest.mark.parametrize("drift", ["pair", "count", "hold", "generation"])
def test_recovery_enable_rechecks_receipts_and_current_world(h, monkeypatch, drift):
    failed_partial_epoch(h, monkeypatch)
    prepared = h.cloud(cloud.create_epoch, recovery_proposal(h), actor="owner-admin:synthetic")
    with h.db() as db:
        if drift == "pair": db.execute("update public.charlie_control_commands set result_json=result_json||%s::jsonb", (json.dumps({"repair_verified":True}),))
        elif drift == "count": db.execute("delete from public.charlie_control_commands")
        elif drift == "generation": db.execute("update app_private.oom_manager_cases set generation=generation+1")
        else: db.execute("""insert into public.charlie_owner_execution_hold_events
            (event_id,hold_id,mission_id,generation_identity,event_type,reason,owner_identity_hash,authorization_identity)
            values('REC-H','REC-H',%s,'g','hold_created','test',%s,%s)""",(h.mission["mission_id"],"a"*64,"b"*64))
    before = snapshot(h); old = policy_row(h)
    with pytest.raises((cloud.CloudIntakeRefused, cloud.intake.IntakeRefused)):
        h.cloud(cloud.set_enabled, prepared["epoch"]["epoch_id"], {"policy_sha256": prepared["policy_sha256"]},
                      enabled=True, actor="owner-admin:synthetic")
    assert snapshot(h) == before and policy_row(h) == old and old["enabled"] is False
