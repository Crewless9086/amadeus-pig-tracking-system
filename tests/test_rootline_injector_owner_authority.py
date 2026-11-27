"""Production-shaped registry120 plus canonical owner saves, no external I/O."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.telemetry import rootline_timed_control as timed
from modules.telemetry import rootline_device_spine as spine
from modules.telemetry import rootline_owner_controls as owner
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry import rootline_command_acceptance as ca
from tests.test_rootline_owner_injection_programme import admission, controls
from tests.test_rootline_owner_controls import record
from tests.test_rootline_device_spine import _device
from tests.test_rootline_command_mode import ENV

KEY="ifttt_ewelink:ewelink_owner_account:100204d497:1"
IDENTITY="FERTILIZER-INJECTION-CH1"


class CanonicalDatabase:
    def __init__(self,now):
        self.now=now; self.queries=[];self.active=True;self.revoked=False;self.current=True
        self.policy={"contract_version":"rootline_timed_standing_authority.v1","stop_mode":"scheduled",
            "device_keys":[KEY],"device_identities":[IDENTITY],"allowed_channels":[1],
            "device_id":"100204d497","provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account",
            "maximum_runtime_seconds":120,"application_timeout_required":True,"automatic_on_retry":False}
        self.policy_sha=ca.digest(self.policy)
        proofs={key:{"source":"canonical","evidence_id":"TEST-"+key,"observed_at":now.isoformat(),"sha256":"a"*64}
            for key in ("owner_configuration","provider_readback")}
        self.device=_device(provider="ifttt_ewelink",provider_account_binding="ewelink_owner_account",
            device_id="100204d497",channel=1,device_type="flow_dependent_injection_valve",
            maximum_runtime_seconds=120,native_fail_stop_seconds=0,stop_mode="scheduled",
            commissioning_stage="standing_active",standing_authority=True,registry_generation=2,
            commissioning_evidence=proofs,authority_envelope={"standing_authority_id":"TEST-INJECTOR-AUTO",
                "version":"1","issuer":"owner_policy","policy_sha256":self.policy_sha,"revoked":False})
        self.digest=ca.digest(self.device)
        self.records=[record("injection",fields=controls()["devices"]["injection"]["fields"],at=now-timedelta(seconds=1))]
    def factory(self): return nullcontext(self)
    def cursor(self): return Cursor(self)
    def execute(self,sql,args=()): return self.cursor().execute(sql,args)
    def load(self):return spine.load_device_record(KEY,connect_factory=self.factory)


class Cursor:
    def __init__(self,db):self.connection=db;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=()):
        d=self.connection;d.queries.append((sql,args))
        if "current_setting('transaction_isolation')" in sql:
            self.rows=[("read committed",)]
        elif "rootline_device_registry" in sql:
            self.rows=[(spine.CONTRACT_VERSION,deepcopy(d.device),d.digest,2,ca.digest(d.device))]
        elif "rootline_device_commissioning_evidence" in sql:
            self.rows=[(args[0],"a"*64,d.current)]
        elif "select a.standing_authority_id" in sql:
            self.rows=[("TEST-INJECTOR-AUTO","1",d.policy_sha,d.active and not d.revoked,d.policy)]
        elif "select issuer,policy_payload" in sql:
            self.rows=[("owner_policy",deepcopy(d.policy),d.policy_sha,d.active,d.revoked,d.current)]
        elif "clock_timestamp" in sql:self.rows=[(d.now,)]
        elif "rootline_operational_intake" in sql:self.rows=[(deepcopy(r),) for r in d.records]
        else:raise AssertionError(sql)
        return self
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


def setup(zone="B12345"):
    with timed.timed_control_scope(ENV):
        memory,transport,clock,context,safety,artifact=admission(zone)
    return CanonicalDatabase(clock[0]),memory,transport,clock,context,safety,artifact


def permitted(db,artifact,loaded=None):
    return timed.canonical_timed_authority(loaded or db.load(),connect_factory=db.factory,
        identity=IDENTITY,requested_seconds=artifact["maximum_duration_seconds"],execution=artifact)


def test_registry120_is_unchanged_and_fresh_owner600_authorizes():
    db,_,_,_,_,_,artifact=setup()
    before=deepcopy(db.device);assert permitted(db,artifact)
    assert db.device==before and spine.scheduled_device_profile(db.device)
    assert timed.locked_owner_injector_authority(db,artifact)
    assert any("rootline_operational_intake" in q for q,_ in db.queries)
    assert all(q.lstrip().lower().startswith("select") for q,_ in db.queries)


@pytest.mark.parametrize("fault",["absent","expired","future","paused","wrong_camp","tampered_policy","revoked",
    "inactive","authority_event","wrong_channel","wrong_device","wrong_scope","bad_digest","stale_loaded","wrong_mode","forged_claim"])
def test_current_canonical_mismatch_cannot_extend_authority(fault):
    db,_,_,clock,_,_,artifact=setup()
    loaded=db.load()
    if fault=="absent":db.records=[]
    elif fault=="expired":db.records[0]["context"]["expires_at"]=(db.now-timedelta(seconds=1)).isoformat()
    elif fault=="future":db.records[0]["context"]["effective_at"]=(db.now+timedelta(seconds=1)).isoformat()
    elif fault=="paused":db.records[0]["context"]["change"]["changes"]["mode"]="paused"
    elif fault=="wrong_camp":db.records[0]["context"]["change"]["changes"]["fields"]["inject_camp_b"]=False
    elif fault=="tampered_policy":artifact["injection_policy"]["pulse_seconds"]=540
    elif fault=="revoked":db.revoked=True
    elif fault=="inactive":db.active=False
    elif fault=="authority_event":db.current=False
    elif fault=="wrong_channel":artifact["channel"]=2
    elif fault=="wrong_device":artifact["device_id"]="other"
    elif fault=="wrong_scope":db.policy["device_identities"]=[];db.policy_sha=ca.digest(db.policy)
    elif fault=="bad_digest":db.policy["automatic_on_retry"]=True
    elif fault=="stale_loaded":db.records[0]["context"]["change"]["changes"]["fields"]["pulse_minutes"]=9
    elif fault=="wrong_mode":artifact["acceptance_mode"]="physical"
    else:artifact.pop("injection_policy")
    assert not permitted(db,artifact,loaded=loaded)


def test_legacy120_authority_needs_no_new_owner_setting():
    db,_,_,_,_,_,artifact=setup();db.records=[]
    assert timed.canonical_timed_authority(db.load(),connect_factory=db.factory,identity=IDENTITY,requested_seconds=120)
    assert not any("rootline_operational_intake" in q for q,_ in db.queries)
    assert not timed.canonical_timed_authority(db.load(),connect_factory=db.factory,identity=IDENTITY,requested_seconds=600)


def test_full_managed_path_uses_real_registry_and_authority_then_one600_on():
    db,memory,transport,clock,context,safety,artifact=setup()
    def store(action,body):
        if action=="load_active_auxiliaries":return deepcopy(list(memory.auxiliary.values()))
        if action=="claim_auxiliary_before_on":
            assert owner.bind_owner_start(db,IDENTITY,body)
        if action=="dispatch_auxiliary_on_edge":
            assert owner.owner_start_allowed(db,IDENTITY,now=clock[0],execution=body)
        return memory(action,body)
    packet={"irrigation_auxiliary_tasks":[{"auxiliary_device_id":IDENTITY,
        "device_type":"fertilizer_injection_valve","decision":"Run now"}],
        "auxiliary_contexts":{IDENTITY:context},"auxiliary_safety":{IDENTITY:safety}}
    env={**ENV,"ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"}
    result=managed.run_rootline_managed_device_cycle(evidence=packet,store=store,transport=transport,
        connect_factory=db.factory,environ=env,clock=lambda:clock[0],now=clock[0],
        deadline_wait=lambda _:pytest.fail("no600second wait"))
    assert result.get("short_auxiliary_duty_owned"),str(result)
    active=memory.auxiliary[IDENTITY]
    assert active["injector_target"]["target_seconds"]==600
    assert len([c for c in transport.calls if c[0]=="100204d497" and c[2]=="ON"])==1
    assert db.device["maximum_runtime_seconds"]==120


def test_same_transaction_revocation_after_admission_blocks_claim_and_on():
    db,_,_,clock,_,_,artifact=setup()
    assert permitted(db,artifact)
    db.revoked=True
    with pytest.raises(ValueError,match="standing_authority_unresolved"):
        owner.bind_owner_start(db,IDENTITY,deepcopy(artifact))


def test_missing_fresh_owner_policy_returns_bounded_diagnostic_not_silent_skip():
    db,memory,transport,clock,context,safety,artifact=setup();db.records=[]
    def store(action,body):
        if action=="load_active_auxiliaries":return []
        return memory(action,body)
    packet={"irrigation_auxiliary_tasks":[{"auxiliary_device_id":IDENTITY,"device_type":"fertilizer_injection_valve","decision":"Run now"}],
        "auxiliary_contexts":{IDENTITY:context},"auxiliary_safety":{IDENTITY:safety}}
    result=managed.run_rootline_managed_device_cycle(evidence=packet,store=store,transport=transport,
        connect_factory=db.factory,environ={**ENV,"ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"},
        clock=lambda:clock[0],now=clock[0])
    assert result["auxiliary_admission_rejections"]==[{"device":IDENTITY,"reason":"canonical_timed_authority_unproven"}]
    assert result["hardware_commands"]==0 and not result["blocks_bc"]
    assert not any(r.get("action")=="claim_auxiliary_before_on" for r in memory.rows)


def startup600():
    from datetime import datetime, timezone
    from tests.test_rootline_startup_command_recovery import event
    artifact=deepcopy(setup()[-1])
    now=datetime.now(timezone.utc)-timedelta(seconds=700)
    artifact.update(claimed_at=now.isoformat(),primary_stop_deadline=(now+timedelta(seconds=600)).isoformat(),
        state="claimed",on_attempts=0,off_attempts=0,injector_timing_contract=ca.INJECTOR_TARGET_V2)
    claim=event("claim_auxiliary_before_on",artifact)
    held=event("contain_auxiliary_device",{**artifact,"state":"claimed_recovery_required",
        "reason":"restart_or_deadline_ambiguous","shutdown_verified":True,
        "shutdown_evidence":{"authoritative":True,"state":"OFF","device_id":artifact["device_id"],
            "channel":1,"evidence_id":"a"*64,"retrieved_at":(now+timedelta(seconds=601)).isoformat()}})
    barrier=event("claim_auxiliary_off_attempt",{"execution_id":artifact["execution_id"],"attempt":1})
    return [claim,held,barrier],held["event_id"]

def test600_never_dispatched_recovery_is_command_only():
    from modules.telemetry import rootline_irrigation_execution_store as store
    rows,held=startup600()
    assert store._auxiliary_command_abort_preimage(rows,held) is not None
    assert store._auxiliary_startup_abort_preimage(rows,held) is None

@pytest.mark.parametrize("fault",["native","legacy","policy","held_policy","dispatch","manual"])
def test600_restart_rejects_changed_or_ambiguous_claim(fault):
    from modules.telemetry import rootline_irrigation_execution_store as store
    from tests.test_rootline_startup_command_recovery import event
    rows,held=startup600()
    if fault=="native":rows[0]["acceptance_mode"]="physical"
    elif fault=="legacy":rows[0]["injector_timing_contract"]=ca.INJECTOR_TARGET_V1
    elif fault=="policy":rows[0]["injection_policy"]["pulse_seconds"]=540
    elif fault=="held_policy":rows[1]["injection_policy"]["pulse_seconds"]=540
    elif fault=="dispatch":rows.append(event("claim_auxiliary_dispatch",rows[0]))
    else:rows[0]["manual_isolation_active"]=True
    assert store._auxiliary_command_abort_preimage(rows,held) is None

def test_rejection_metadata_is_bounded_and_cannot_copy_payload():
    from modules.telemetry.rootline_failure_diagnostics import sanitize_auxiliary_rejections
    assert sanitize_auxiliary_rejections([{"device":[],"reason":{}}])==[]
    result=sanitize_auxiliary_rejections([{"device":IDENTITY,"reason":{},"current_failure":{
        "error_type":"TimeoutError","message":"private url","sql":"private query"}}]*3)
    assert result==[{"device":IDENTITY,"reason":"eligibility_unproven","current_failure":{"error_type":"TimeoutError"}}]*2


def test_scheduler_persists_deferral_without_owner_notification():
    from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment, SCHEDULER_IDENTITY
    db=setup()[0]; rows={}
    def store(action,identity,value):
        if action=="load_latest_outcome":return {}
        if action=="load_schedule":return rows.get(identity)
        if action in {"claim_schedule","record_outcome"}:
            rows[identity]=deepcopy(value);return {"success":True,"created":True}
        raise AssertionError(action)
    reason={"device":IDENTITY,"reason":"clean_water_flush_window_incomplete"}
    result=run_due_reassessment(payload={"specialist":"ROOTLINE","scheduler_identity":SCHEDULER_IDENTITY,
        "due_at":db.now.isoformat(),"evidence_cutoff":db.now.isoformat()},now=db.now,store=store,
        invoke=lambda:{"success":True,"status":"no_eligible_managed_device_task",
            "managed_device_result":{"auxiliary_admission_rejections":[reason]},
            "telegram_sends":0,"hardware_commands":0})
    assert result["terminal_outcome"]=="completed"
    outcome=next(iter(rows.values()))
    assert outcome["auxiliary_admission_rejections"]==[reason]
    assert outcome["telegram_sends"]==outcome["hardware_commands"]==0


@pytest.mark.parametrize("zone",["A12345","B12345","C12345","E12345"])
@pytest.mark.parametrize("route_failure",[False,True])
def test_actual_reassessment_projects_saved_plan_and_current_owner_policy(monkeypatch,route_failure,zone):
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_water_energy_plan as planner
    from modules.oom_sakkie import bounded_postgres_read as bounded
    from tests.test_rootline_water_energy_plan import daily_program_facts
    db,memory,transport,clock,context,safety,artifact=setup(zone)
    facts=daily_program_facts(clock[0])
    with timed.timed_control_scope(ENV):
        saved=planner.build_daily_program(facts,clock[0].astimezone(planner.ZA_TZ).date().isoformat(),now=clock[0])
    evidence={**facts,"evidence_purpose":"managed","saved_daily_plan":saved,
        "owner_controls":owner.read_owner_controls(db,now=clock[0]),
        "active_irrigation_context":context,"fertilizer_history_complete_through":clock[0].isoformat(),
        "fertilizer_executions":[],"fertilizer_batch_observations":[]}
    calls=[]
    def loader(**kwargs):
        calls.append(kwargs)
        assert kwargs["purpose"]=="managed" and kwargs["forecast_mode"]=="live_only"
        return deepcopy(evidence),clock[0].astimezone(planner.ZA_TZ).date().isoformat(),clock[0]
    original_safety=transport.read_safety_configuration
    monkeypatch.setattr(transport,"read_safety_configuration",lambda device_id,channel,**kwargs: original_safety(device_id=device_id,channel=channel))
    original=transport.read_output_state
    def read(**kwargs):
        if route_failure and kwargs["device_id"]==memory.active["device_id"]:
            raise TimeoutError("private provider URL must not escape")
        return original(**kwargs)
    monkeypatch.setattr(transport,"read_output_state",read)
    monkeypatch.setattr(bounded,"connect_bounded_rootline_postgres",lambda **kwargs:db.factory())
    def store(action,body):
        if action=="load_active_auxiliaries":return deepcopy(list(memory.auxiliary.values()))
        if action=="claim_auxiliary_before_on":assert owner.bind_owner_start(db,IDENTITY,body)
        if action=="dispatch_auxiliary_on_edge":assert owner.owner_start_allowed(db,IDENTITY,now=clock[0],execution=body)
        return memory(action,body)
    result=runtime.run_rootline_managed_device_reassessment(environ={**ENV,
        "ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"},now=clock[0],store=store,
        transport=transport,evidence_loader=loader,clock=lambda:clock[0],refresh_after_safety=False)
    assert calls
    if route_failure:
        assert result["hardware_commands"]==0,result
        reasons=result["auxiliary_admission_rejections"]
        assert reasons[0]["current_failure"]=={"error_type":"TimeoutError"}
        assert "private" not in str(result)
    else:
        assert result.get("short_auxiliary_duty_owned"),str(result)
        assert memory.auxiliary[IDENTITY]["injector_target"]["target_seconds"]==600
