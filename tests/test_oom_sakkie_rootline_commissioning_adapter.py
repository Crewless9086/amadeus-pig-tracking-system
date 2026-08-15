from copy import deepcopy
from datetime import datetime, timezone

from modules.oom_sakkie.rootline_commissioning_adapter import (
    accept_supervised_commissioning_presence, _digest,
)
from modules.oom_sakkie.specialist_owner_decisions import (
    ROOTLINE_COMMISSIONING_ID, ROOTLINE_DECISION_ARTIFACT_SHA256, ROOTLINE_RELEASE_SHA256,
    rootline_supervised_commissioning_binding,
)

NOW=datetime(2026,8,2,16,0,tzinfo=timezone.utc)
OWNER="42"; ACTOR=_digest({"telegram_owner_id":OWNER})

def evidence():
    binding=rootline_supervised_commissioning_binding(expires_at="2026-08-03T10:00:00+00:00")
    card=binding["binding_digest"]; decision=binding["decision_token"]
    replay=_digest({"card_digest":card,"choice":"authorize","actor_identity_hash":ACTOR})
    receipt_id="OOMAQ-RECEIPT-"+replay[:24]
    return {"owner_attention":{"expected_owner_identity_hash":ACTOR,"item":{
            "external_decision_identity":ROOTLINE_COMMISSIONING_ID,"card_digest":card,
            "specialist_binding":binding}},
        "owner_card":{"telegram_chat_id":OWNER,"telegram_message_id":"3176"},
        "receipt":{"status":"consumed","choice_id":"authorize","actor_identity_hash":ACTOR,
            "decision_id":decision,"card_digest":card,"replay_key":replay,"receipt_id":receipt_id},
        "callback":{"deterministic_identity":ROOTLINE_COMMISSIONING_ID,
            "outcome_code":"supervised_commissioning_authorized",
            "specialist_callback":"prepare_supervised_commissioning_handover"},
        "resolution":{"deterministic_identity":ROOTLINE_COMMISSIONING_ID,"decision_id":decision,
            "receipt_id":receipt_id,"state":"resolved","telegram_chat_id":OWNER,"telegram_message_id":"3176"}}

def test_exact_governed_authorization_accepts_only_read_only_discovery():
    result=accept_supervised_commissioning_presence({"owner_user_id":OWNER,"chat_id":OWNER},evidence_loader=lambda _factory:evidence(),now=NOW)
    assert result["success"] is True and result["specialist_acceptance"] is True
    assert result["authorization_current"] is True
    assert result["next_state"]=="waiting_for_supervised_configuration_discovery"
    assert result["hardware_commands"]==0 and result["writes_performed"] is False
    assert result["authority"]=={"hardware_control":False,"configuration_write":False,"telegram_send":False}

def test_changed_receipt_card_actor_artifact_or_chronology_fails_closed():
    mutations=[]
    for path,value in (("owner_attention.expected_owner_identity_hash","0"*64),
        ("receipt.choice_id","not_now"),("receipt.actor_identity_hash","c"*64),
        ("receipt.card_digest","d"*64),("callback.outcome_code","commissioning_deferred"),
        ("resolution.telegram_message_id","999"),
        ("owner_attention.item.specialist_binding.evidence_binding.rootline_release_sha256","0"*64),
        ("owner_attention.item.specialist_binding.evidence_binding.decision_artifact_sha256","0"*64)):
        item=deepcopy(evidence()); target=item
        parts=path.split('.')
        for key in parts[:-1]: target=target[key]
        target[parts[-1]]=value; mutations.append(item)
    mutations.append({**evidence(),"receipt":{}})
    for item in mutations:
        result=accept_supervised_commissioning_presence({"owner_user_id":OWNER,"chat_id":OWNER},evidence_loader=lambda _factory,x=item:x,now=NOW)
        assert result["success"] is False and result["hardware_commands"]==0

def test_expired_or_unavailable_authorization_fails_closed():
    expired=deepcopy(evidence())
    expired["owner_attention"]["item"]["specialist_binding"]["expires_at"]="2026-08-02T15:59:59+00:00"
    for loader in (lambda _factory:expired,lambda _factory:(_ for _ in ()).throw(RuntimeError("db"))):
        result=accept_supervised_commissioning_presence({"owner_user_id":OWNER,"chat_id":OWNER},evidence_loader=loader,now=NOW)
        assert result["success"] is False and result["hardware_commands"]==0
