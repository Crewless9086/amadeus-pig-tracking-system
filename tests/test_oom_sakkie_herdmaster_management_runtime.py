from datetime import datetime, timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_management_runtime import consume_current_herdmaster_management, _consumption_claim_identity
from tests.test_oom_sakkie_herdmaster_management_adapter import canonical, observations, active, NOW, OWNER

def test_authenticated_runtime_consumes_and_records_existing_store_binding_once():
    recorded=[]
    result=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
        owner_user_id=OWNER,now=NOW,canonical_loader=canonical,observation_loader=lambda _owner: observations(),
        active_loader=lambda _owner: active(),prior_loader=lambda _owner,_context:[],recorder=lambda value:(recorded.append(value) or {"success":True,"created":True}))
    assert result["status"]=="herdmaster_management_round_consumed"
    assert result["accepted_work_item_count"]==3 and len(recorded)==1
    assert all("PIG-2026-E88A" not in item.item_id for item in result["specialist_result"].work_items)
    assert result["writes_farm_data"] is result["sends_telegram"] is False

def test_missing_historical_pregnancy_observations_stay_unknown_not_reconstructed():
    result=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
        owner_user_id=OWNER,now=NOW,canonical_loader=canonical,observation_loader=lambda _owner:[],
        active_loader=lambda _owner: active(),prior_loader=lambda _owner,_context:[],recorder=lambda _value:{"success":True,"created":True})
    text=" ".join(item.title+" "+item.next_action for item in result["specialist_result"].work_items)
    assert "Assumed Pregnant" not in text

def test_runtime_exact_replay_records_nothing():
    first=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
        owner_user_id=OWNER,now=NOW,canonical_loader=canonical,observation_loader=lambda _owner: observations(),
        active_loader=lambda _owner: active(),prior_loader=lambda _owner,_context:[],recorder=lambda _value:{"success":True,"created":True})
    b=first["binding"]
    prior={"management_round_identity":b["management_round_identity"],"deduplication_key":b["deduplication_key"],
        "result_digest":b["result_digest"],"evidence_generation":b["evidence_generation"],
        "active_case_digest":b["active_case_deduplication_state"]["digest"],
        "invocation_context_digest":b["invocation_context"]["digest"]}
    recorded=[]
    replay=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
        owner_user_id=OWNER,now=NOW,canonical_loader=canonical,observation_loader=lambda _owner: observations(),
        active_loader=lambda _owner: active(),prior_loader=lambda _owner,_context:[prior],recorder=lambda value:recorded.append(value))
    assert replay["status"]=="herdmaster_management_round_replay_suppressed" and recorded==[]

def test_authentication_precedes_every_loader_and_loader_failure_is_contained():
    calls=[]
    denied=consume_current_herdmaster_management(authority=None,owner_user_id=OWNER,now=NOW,
        canonical_loader=lambda:calls.append("canonical"), observation_loader=lambda _owner:calls.append("observations"),
        active_loader=lambda _owner:calls.append("active"), prior_loader=lambda _owner,_context:calls.append("prior"))
    assert denied["systemic_exception"]["reason"]=="authenticated_manager_context_denied" and calls==[]
    failed=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
        owner_user_id=OWNER,now=NOW,observation_loader=lambda _owner:(_ for _ in ()).throw(RuntimeError("db")))
    assert failed["systemic_exception"]["reason"]=="herdmaster_management_runtime_evidence_unavailable"

def test_persistence_interruption_is_contained_and_duplicate_claim_is_replay():
    kwargs=dict(authority=issue_gateway_owner_authority(OWNER,OWNER),owner_user_id=OWNER,now=NOW,
        canonical_loader=canonical,observation_loader=lambda _owner:observations(),
        active_loader=lambda _owner:active(),prior_loader=lambda _owner,_context:[])
    failed=consume_current_herdmaster_management(**kwargs,recorder=lambda _value:(_ for _ in ()).throw(RuntimeError("commit")))
    replay=consume_current_herdmaster_management(**kwargs,recorder=lambda _value:{"success":True,"created":False})
    assert failed["systemic_exception"]["reason"]=="herdmaster_management_consumption_persistence_failed"
    assert replay["status"]=="herdmaster_management_round_replay_suppressed"
    assert replay["specialist_result"] is None and replay["accepted_work_item_count"]==0

def test_claim_identity_excludes_invocation_timestamp_and_recorder_requires_proof():
    recorded=[]
    first=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
        owner_user_id=OWNER,now=NOW,canonical_loader=canonical,observation_loader=lambda _owner:observations(),
        active_loader=lambda _owner:active(),prior_loader=lambda _owner,_context:[],
        recorder=lambda value:(recorded.append(value) or {"success":True,"created":True}))
    changed={**first["binding"],"invocation_timestamp":"2026-08-02T14:00:01+00:00"}
    assert _consumption_claim_identity(first["binding"])==_consumption_claim_identity(changed)
    for response in (None,{}, {"success":False,"created":True}, {"success":True}):
        result=consume_current_herdmaster_management(authority=issue_gateway_owner_authority(OWNER,OWNER),
            owner_user_id=OWNER,now=NOW,canonical_loader=canonical,observation_loader=lambda _owner:observations(),
            active_loader=lambda _owner:active(),prior_loader=lambda _owner,_context:[],recorder=lambda _value,r=response:r)
        assert result["systemic_exception"]["reason"]=="herdmaster_management_consumption_persistence_unproven"
