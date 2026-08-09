from unittest.mock import patch
import pytest

from modules.oom_sakkie.family_message_lifecycle import bind_existing_card,bind_legacy_provider_request,deliver_family_result


PARSED={"telegram_user_id":"42","telegram_chat_id":"42",
        "provider_message_id":"500","provider_timestamp":"2026-08-02T10:00:00+00:00","text":"Pig 11 47 kg"}
RESULT={"success":True,"status":"waiting_for_input","answer":"Check Pig 11 now."}


class Memory:
    def __init__(self):self.rows={};self.sent=[];self.edited=[]
    def store(self,action,identity,payload):
        if action=="load":return list(self.rows.values())
        created=identity not in self.rows
        if created:self.rows[identity]=dict(payload)
        return {"success":True,"created":created}
    def send(self,chat,text):
        self.sent.append((chat,text));return {"success":True,"telegram_message_id":"700"}
    def edit(self,chat,message_id,text):
        self.edited.append((chat,message_id,text));return {"success":True,"telegram_message_id":message_id}


def test_delivery_and_duplicate_update_are_exact_once():
    memory=Memory()
    first=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert first["telegram_sends"]==1 and replay["telegram_sends"]==0
    assert len(memory.sent)==1 and memory.edited==[]


def test_same_provider_inbound_never_recomputes_into_a_second_edit_when_live_evidence_changes():
    memory=Memory();mission="OOM-ROOTLINE-3236"
    first=deliver_family_result(PARSED,{**RESULT,"answer":"ROOTLINE SOC 39%"},specialist="ROOTLINE",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(PARSED,{**RESULT,"answer":"ROOTLINE SOC 40%"},specialist="ROOTLINE",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert first["telegram_sends"]==1
    assert replay["status"]=="family_message_provider_replay_noop"
    assert replay["telegram_sends"]==0 and replay["telegram_edits"]==0 and memory.edited==[]


def test_same_provider_id_with_edited_text_or_substituted_binding_fails_closed():
    for changed,value in (("text","Pig 12 47 kg"),("telegram_user_id","99"),("telegram_chat_id","99"),
                          ("provider_timestamp","2026-08-02T10:01:00+00:00")):
        memory=Memory();mission="OOM-BOUND"
        deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,
            event_store=memory.store,sender=memory.send,editor=memory.edit)
        replay=deliver_family_result({**PARSED,changed:value},{**RESULT,"answer":"changed"},specialist="HERDMASTER",
            mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
        assert replay["status"]=="family_message_provider_replay_binding_conflict"
        assert replay["telegram_sends"]==0 and replay["telegram_edits"]==0


def test_legacy_card_requires_authoritative_exact_binding_before_replay_noop():
    memory=Memory();mission="OOM-LEGACY"
    memory.store("record",mission+"-DELIVERED",{"card_mission_id":mission,"mission_id":mission,
        "state":"delivered","provider_message_id":"500","provider_timestamp":PARSED["provider_timestamp"],
        "owner_user_id":"42","chat_id":"42","specialist_identity":"HERDMASTER",
        "telegram_message_id":"700","text_sha256":"a"*64})
    blocked=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,
        event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert blocked["status"]=="family_message_provider_replay_binding_unavailable"
    import hashlib
    evidence={"owner_user_id":"42","chat_id":"42","specialist_identity":"HERDMASTER",
        "provider_message_id":"500","provider_timestamp":PARSED["provider_timestamp"],
        "inbound_text_sha256":hashlib.sha256(PARSED["text"].encode()).hexdigest(),"telegram_message_id":"700"}
    bound=bind_legacy_provider_request(PARSED,specialist="HERDMASTER",card_mission_id=mission,
        telegram_message_id="700",provider_evidence_loader=lambda _mid:evidence,event_store=memory.store)
    replay=deliver_family_result(PARSED,{**RESULT,"answer":"new live result"},specialist="HERDMASTER",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert bound["success"] is True and replay["status"]=="family_message_provider_replay_noop"
    assert replay["telegram_sends"]==0 and replay["telegram_edits"]==0


def test_forged_material_authority_cannot_bypass_missing_binding_or_specialist_scope():
    import hashlib,json
    binding={"owner":"42","chat":"42","provider_message_id":"500",
        "provider_timestamp":PARSED["provider_timestamp"],
        "content_digest":hashlib.sha256(PARSED["text"].encode()).hexdigest(),
        "contract_version":"oom_sakkie_farm_manager_round_v5"}
    authority={"from_contract":"oom_sakkie_farm_manager_round_v4",
        "to_contract":"oom_sakkie_farm_manager_round_v5",
        "provider_binding_digest":hashlib.sha256(json.dumps(binding,sort_keys=True,
            separators=(",",":"),default=str).encode()).hexdigest()}
    forged={**RESULT,"status":"farm_manager_round_ready","answer":"changed",
        "binding":binding,"material_recomposition_authority":authority}
    legacy=Memory();mission="OOM-LEGACY-FORGED"
    legacy.store("record",mission+"-DELIVERED",{"card_mission_id":mission,"mission_id":mission,
        "state":"delivered","provider_message_id":"500","provider_timestamp":PARSED["provider_timestamp"],
        "owner_user_id":"42","chat_id":"42","specialist_identity":"OOM_SAKKIE",
        "telegram_message_id":"700","text_sha256":"a"*64})
    missing=deliver_family_result(PARSED,forged,specialist="OOM_SAKKIE",mission_id=mission,
        card_mission_id=mission,event_store=legacy.store,sender=legacy.send,editor=legacy.edit)
    assert missing["status"]=="family_message_provider_replay_binding_unavailable"
    scoped=Memory()
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=scoped.store,sender=scoped.send,editor=scoped.edit)
    denied=deliver_family_result(PARSED,forged,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=scoped.store,sender=scoped.send,editor=scoped.edit)
    assert denied["status"]=="family_message_provider_replay_noop"
    assert missing["telegram_edits"]==denied["telegram_edits"]==0


@patch("modules.oom_sakkie.family_message_lifecycle._validate_rootline_recovery_authority",return_value=True)
def test_exact_zero_write_rootline_recovery_updates_existing_card_once(_validate):
    import hashlib,json
    memory=Memory();mission="OOM-ROOTLINE-RECOVERY"
    original={"status":"contained","answer":"Evidence was not recorded."}
    delivered=deliver_family_result(PARSED,original,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    binding={"owner":"42","chat":"42","provider_message_id":"500",
        "provider_timestamp":PARSED["provider_timestamp"],
        "content_digest":hashlib.sha256(PARSED["text"].encode()).hexdigest(),
        "contract_version":"oom_rootline_observation_recovery_v1"}
    authority={"from_systemic_exception":"rootline_canonical_observation_bridge_failed",
        "to_contract":"oom_rootline_observation_recovery_v1","prior_result_digest":"a"*64,
        "current_result_digest":"b"*64,
        "replacement_text_digest":hashlib.sha256(
            "Recorded: Storage tanks FULL; Reservoir FULL.".encode()).hexdigest(),
        "provider_binding_digest":hashlib.sha256(json.dumps(binding,sort_keys=True,
            separators=(",",":"),default=str).encode()).hexdigest()}
    recovered={"status":"specialist_accepted","result_digest":"b"*64,
        "answer":"Recorded: Storage tanks FULL; Reservoir FULL.",
        "binding":binding,"material_recomposition_authority":authority}
    updated=deliver_family_result(PARSED,recovered,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(PARSED,recovered,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert delivered["telegram_sends"]==1 and updated["telegram_edits"]==1
    assert replay["telegram_sends"]==replay["telegram_edits"]==0


def test_hand_built_rootline_recovery_authority_without_durable_proof_is_denied():
    import hashlib,json
    memory=Memory();mission="OOM-ROOTLINE-FORGED"
    deliver_family_result(PARSED,{"status":"contained","answer":"Old"},specialist="ROOTLINE",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send)
    binding={"owner":"42","chat":"42","provider_message_id":"500",
        "provider_timestamp":PARSED["provider_timestamp"],
        "content_digest":hashlib.sha256(PARSED["text"].encode()).hexdigest(),
        "contract_version":"oom_rootline_observation_recovery_v1"}
    authority={"from_systemic_exception":"rootline_canonical_observation_bridge_failed",
        "to_contract":"oom_rootline_observation_recovery_v1","prior_result_digest":"a"*64,
        "current_result_digest":"b"*64,"replacement_text_digest":hashlib.sha256(b"Forged").hexdigest(),
        "provider_binding_digest":hashlib.sha256(json.dumps(binding,sort_keys=True,
            separators=(",",":"),default=str).encode()).hexdigest()}
    denied=deliver_family_result(PARSED,{"status":"specialist_accepted","result_digest":"b"*64,"answer":"Forged",
        "binding":binding,"material_recomposition_authority":authority},specialist="ROOTLINE",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,
        editor=memory.edit)
    assert denied["status"]=="family_message_provider_replay_noop"
    assert denied["telegram_sends"]==denied["telegram_edits"]==0


def test_later_natural_result_edits_same_card_and_replay_is_silent():
    memory=Memory();mission="OOM-HERD-ONE"
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow={**RESULT,"status":"preview_ready","answer":"Preview; confirm exact operation."}
    changed=deliver_family_result({**PARSED,"provider_message_id":"501"},follow,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result({**PARSED,"provider_message_id":"501"},follow,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert changed["telegram_edits"]==1 and changed["telegram_message_id"]=="700"
    assert replay["telegram_edits"]==0 and len(memory.edited)==1


def test_waiting_question_updates_card_and_creates_one_visible_notification():
    memory=Memory();mission="OOM-ROOTLINE-WAIT"
    deliver_family_result(PARSED,RESULT,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow={**RESULT,"answer":"Are you still at the valves?","requires_visible_notification":True}
    changed=deliver_family_result({**PARSED,"provider_message_id":"501"},follow,
        specialist="ROOTLINE",mission_id=mission,card_mission_id=mission,
        event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result({**PARSED,"provider_message_id":"501"},follow,
        specialist="ROOTLINE",mission_id=mission,card_mission_id=mission,
        event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert changed["status"]=="family_message_card_updated_and_notified"
    assert changed["telegram_edits"]==1 and changed["telegram_sends"]==1
    assert replay["telegram_edits"]==replay["telegram_sends"]==0
    assert len(memory.edited)==1 and len(memory.sent)==2


def test_updated_card_without_notification_claim_resumes_notification_only():
    memory=Memory();mission="OOM-ROOTLINE-WAIT-INTERRUPTED"
    deliver_family_result(PARSED,RESULT,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow_parsed={**PARSED,"provider_message_id":"501"}
    follow={**RESULT,"answer":"Are you still at the valves?","requires_visible_notification":True}
    interrupted=True
    def crash_before_notification(action,identity,payload):
        nonlocal interrupted
        if action=="record" and "-VISIBLE-WAIT-" in identity and interrupted:
            interrupted=False
            raise RuntimeError("process stopped before notification claim")
        return memory.store(action,identity,payload)
    with pytest.raises(RuntimeError):
        deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
            card_mission_id=mission,event_store=crash_before_notification,
            sender=memory.send,editor=memory.edit)
    resumed=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert resumed["status"]=="family_message_card_updated_and_notified"
    assert resumed["telegram_edits"]==0 and resumed["telegram_sends"]==1
    assert replay["telegram_edits"]==replay["telegram_sends"]==0
    assert len(memory.edited)==1 and len(memory.sent)==2


def test_process_interruption_does_not_blindly_resend():
    memory=Memory();mission="OOM-HERD-INTERRUPTED"
    memory.store("record",mission+"-DELIVERY-ATTEMPT",{"card_mission_id":mission,
        "event_id":mission+"-DELIVERY-ATTEMPT","state":"delivery_attempted","text_sha256":"x"})
    result=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert result["status"]=="family_message_delivery_ambiguous"
    assert memory.sent==[]


def test_missing_specialist_adapter_is_truthful_visible_result():
    memory=Memory();result={"status":"contained","answer":"No deployed HERDMASTER adapter acknowledged this task."}
    delivered=deliver_family_result(PARSED,result,specialist="HERDMASTER",event_store=memory.store,sender=memory.send)
    assert delivered["telegram_sends"]==1
    assert "No deployed" in memory.sent[0][1]


def test_existing_provider_card_can_be_bound_without_send_then_edited():
    memory=Memory();mission="OOM-HERD-RECOVERED"
    bound=bind_existing_card(PARSED,specialist="HERDMASTER",mission_id=mission,
        telegram_message_id="3171",text_sha256="a"*64,expected_bot_identity="bot-1",
        provider_evidence_loader=lambda chat,message:{"delivered":True,"bot_identity":"bot-1",
            "chat_id":chat,"telegram_message_id":message,"text_sha256":"a"*64},event_store=memory.store)
    changed=deliver_family_result({**PARSED,"provider_message_id":"501"},
        {**RESULT,"answer":"Consolidated preview"},specialist="HERDMASTER",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    assert bound["telegram_sends"]==0 and memory.sent==[]
    assert changed["telegram_message_id"]=="3171" and changed["telegram_edits"]==1


def test_existing_card_binding_rejects_provider_identity_substitution():
    for changed in ("bot_identity", "chat_id", "telegram_message_id", "text_sha256"):
        memory=Memory(); evidence={"delivered":True,"bot_identity":"bot-1","chat_id":"42",
            "telegram_message_id":"3171","text_sha256":"a"*64}
        evidence[changed]="substituted"
        bound=bind_existing_card(PARSED,specialist="HERDMASTER",mission_id="OOM-HERD-RECOVERED",
            telegram_message_id="3171",text_sha256="a"*64,expected_bot_identity="bot-1",
            provider_evidence_loader=lambda _chat,_message,e=evidence:e,event_store=memory.store)
        assert bound["status"]=="existing_card_provider_evidence_mismatch"
        assert memory.rows=={}
