from datetime import datetime, timezone
import hashlib, json
from modules.telemetry.rootline_delegated_principal import (
    CAPABILITY, CONTRACT_VERSION, EXCLUDED, delegated_replay_identity,
    handle_delegated_rootline_request,
)

NOW=datetime(2026,8,16,9,tzinfo=timezone.utc)

def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def fixture():
    base={"authorization_id":"AUTH-ANTON-1","principal_id":"100","private_chat_id":"100",
      "family_identity":"anton","role":"farm_manager","capabilities":[CAPABILITY],
      "zones":["B12345"],"commissioned_paths":["B12345"],"maximum_duration_seconds":3599,
      "authorized_at":"2026-08-16T07:00:00+00:00"}
    auth={**base,"active":True,"revoked_at":None,"owner_authority":False,
          "authorization_digest":digest(base)}
    req={"contract_version":CONTRACT_VERSION,"role":"farm_manager","capability":CAPABILITY,
      "principal_id":"100","private_chat_id":"100","family_identity":"anton",
      "authorization_id":auth["authorization_id"],"authorization_digest":auth["authorization_digest"],
      "provider_message_id":"4001","provider_timestamp":"2026-08-16T08:59:00+00:00",
      "evidence_generation":"PLAN-1","commissioned_path_id":"B12345",
      "zone_id":"B12345","action":"irrigation_start","bounded_duration_seconds":3599,
      "job_id":"JOB-1","job_sha256":"c"*64,"segment_identity":"SEGMENT-1",
      "current_segment":1,"execution_id":"ROOTLINE-EXECUTION-NEW",
      "eligibility_sha256":"b"*64,"consumption_key":"CONSUMPTION-1",
      "owner_authority":False,"excluded_authority":sorted(EXCLUDED)}
    req["replay_identity"]=delegated_replay_identity(req)
    return auth,req

def artifact():
    # Use validator injection seam by monkeypatching module validation; the tests
    # exercise ordering/binding while authority validation has its own suite.
    return {"contract_version":"rootline_execution_eligibility.v4","status":"execution_eligible",
      "authority_source":"owner_approved_routine_irrigation_v1","zone_id":"B12345",
      "plan_generation":"PLAN-1","maximum_duration_seconds":3599,"command_authority":True,
      "hardware_control":True,"execution_id":"ROOTLINE-EXECUTION-NEW",
      "eligibility_sha256":"b"*64,"job_id":"JOB-1","job_sha256":"c"*64,
      "segment_identity":"SEGMENT-1","current_segment":1,"consumption_key":"CONSUMPTION-1"}

def run(monkeypatch, mutate=None, auth_mutate=None):
    import modules.telemetry.rootline_delegated_principal as module
    monkeypatch.setattr(module,"validate_execution_eligibility",lambda value,now=None:value)
    auth,req=fixture()
    if mutate: mutate(req)
    if auth_mutate: auth_mutate(auth)
    calls=[]
    out=handle_delegated_rootline_request(req,
      authorization_loader=lambda _id:(calls.append("auth") or auth),
      eligibility_loader=lambda:(calls.append("evidence") or artifact()),
      executor=lambda **kw:(calls.append("execute") or {"success":True,"status":"completed",
        "hardware_commands":1,"provider_control_calls":2}),now=NOW)
    return out,calls

def test_anton_authorized_before_evidence_and_returns_sealed_outcome(monkeypatch):
    out,calls=run(monkeypatch)
    assert calls==["auth","evidence","execute"] and out["success"] is True
    assert out["owner_authority"] is False and len(out["outcome_sha256"])==64

def test_antoinette_and_owner_alias_fail_before_private_load(monkeypatch):
    for change in (lambda r:r.update(role="read_only_family_member",family_identity="antoinette"),
                   lambda r:r.update(owner_authority=True)):
        out,calls=run(monkeypatch,change)
        assert calls==[] and out["hardware_commands"]==0

def test_self_consistent_antoinette_farm_manager_authorization_is_denied(monkeypatch):
    auth,req=fixture(); auth["family_identity"]="antoinette"
    base={key:auth.get(key) for key in ("authorization_id","principal_id","private_chat_id",
      "family_identity","role","capabilities","zones","commissioned_paths",
      "maximum_duration_seconds","authorized_at")}
    auth["authorization_digest"]=digest(base)
    req.update(family_identity="antoinette",authorization_digest=auth["authorization_digest"])
    req["replay_identity"]=delegated_replay_identity(req); calls=[]
    out=handle_delegated_rootline_request(req,authorization_loader=lambda _:(calls.append("auth") or auth),
      eligibility_loader=lambda:(calls.append("evidence") or artifact()),
      executor=lambda **_:(calls.append("execute") or {}),now=NOW)
    assert calls==[] and out["hardware_commands"]==0

def test_revocation_and_private_chat_mismatch_fail_before_evidence(monkeypatch):
    out,calls=run(monkeypatch,auth_mutate=lambda a:a.update(revoked_at="2026-08-16T08:00:00Z"))
    assert calls==["auth"] and out["hardware_commands"]==0
    out,calls=run(monkeypatch,lambda r:r.update(private_chat_id="101"))
    assert calls==[]

def test_missing_or_contained_current_evidence_never_executes(monkeypatch):
    import modules.telemetry.rootline_delegated_principal as module
    monkeypatch.setattr(module,"validate_execution_eligibility",lambda value,now=None:value)
    auth,req=fixture(); calls=[]
    bad={**artifact(),"status":"durable_parent_job_deferred","command_authority":False}
    out=handle_delegated_rootline_request(req,authorization_loader=lambda _:auth,
      eligibility_loader=lambda:bad,executor=lambda **kw:calls.append("execute"),now=NOW)
    assert not calls and out["hardware_commands"]==0

def test_generation_zone_duration_and_commissioning_are_exact(monkeypatch):
    for change in (lambda r:r.update(evidence_generation="OTHER"),
                   lambda r:r.update(zone_id="C12345"),
                   lambda r:r.update(bounded_duration_seconds=60),
                   lambda r:r.update(commissioned_path_id="C12345")):
        out,calls=run(monkeypatch,change)
        assert "execute" not in calls and out["hardware_commands"]==0

def test_provider_replay_is_bound_to_exact_segment_and_cannot_advance(monkeypatch):
    auth,req=fixture()
    stale_replay=req["replay_identity"]
    req.update(segment_identity="SEGMENT-2",current_segment=2,
      execution_id="ROOTLINE-EXECUTION-SECOND",consumption_key="CONSUMPTION-2")
    req["replay_identity"]=stale_replay
    calls=[]
    out=handle_delegated_rootline_request(req,authorization_loader=lambda _:(calls.append("auth") or auth),
      eligibility_loader=lambda:(calls.append("evidence") or artifact()),
      executor=lambda **_:(calls.append("execute") or {}),now=NOW)
    assert calls==[] and out["hardware_commands"]==0

def test_executor_ambiguity_is_sealed_and_never_retried_here(monkeypatch):
    import modules.telemetry.rootline_delegated_principal as module
    monkeypatch.setattr(module,"validate_execution_eligibility",lambda value,now=None:value)
    auth,req=fixture(); count=[0]
    def broken(**_): count[0]+=1; raise TimeoutError()
    out=handle_delegated_rootline_request(req,authorization_loader=lambda _:auth,
      eligibility_loader=artifact,executor=broken,now=NOW)
    assert count==[1] and out["provider_outcome_ambiguous"] is True and out["success"] is False

def test_scheduler_delegation_rebuild_requires_exact_job_segment_and_consumption():
    from modules.telemetry.rootline_execution_runtime import _same_delegated_execution
    current={"eligible":True,"contract_version":"v4","authority_source":"standing",
      "job_id":"J","job_sha256":"j"*64,"zone_id":"B12345","channel":2,
      "segment_identity":"S2","current_segment":2,"segment_requested_seconds":3599,
      "requested_total_duration_seconds":7200,"governed_executable_duration_seconds":7198,
      "expected_segment_count":2,"plan_generation":"P","source_plan_generation":"E",
      "consumption_key":"K"}
    assert _same_delegated_execution(dict(current),current)
    for key in ("job_id","segment_identity","current_segment","consumption_key","zone_id"):
        changed=dict(current); changed[key]="different"
        assert not _same_delegated_execution(changed,current)

def test_malformed_requests_always_return_sealed_zero_effect_outcome():
    for request in (None,{"contract_version":CONTRACT_VERSION,
                          "bounded_duration_seconds":"not-an-int"}):
        out=handle_delegated_rootline_request(request,
          authorization_loader=lambda _: (_ for _ in ()).throw(AssertionError()),
          eligibility_loader=lambda: (_ for _ in ()).throw(AssertionError()),
          executor=lambda **_: (_ for _ in ()).throw(AssertionError()),now=NOW)
        assert out["success"] is False and out["bounded_duration_seconds"]==0
        assert out["hardware_commands"]==0 and len(out["outcome_sha256"])==64

def test_malformed_executor_mapping_is_sealed_ambiguous_not_raised(monkeypatch):
    import modules.telemetry.rootline_delegated_principal as module
    monkeypatch.setattr(module,"validate_execution_eligibility",lambda value,now=None:value)
    auth,req=fixture()
    out=handle_delegated_rootline_request(req,authorization_loader=lambda _:auth,
      eligibility_loader=artifact,executor=lambda **_:{"success":True,"status":"completed",
        "hardware_commands":"bad","provider_control_calls":0},now=NOW)
    assert out["success"] is False and out["provider_outcome_ambiguous"] is True
    assert out["hardware_commands"]==0 and out["provider_control_calls"]==0
