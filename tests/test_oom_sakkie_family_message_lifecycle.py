from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import pytest

from modules.oom_sakkie.family_message_lifecycle import bind_existing_card,bind_legacy_provider_request,deliver_family_result


def test_postgres_lifecycle_load_uses_bounded_transaction_read_only(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read, family_message_lifecycle

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, *_args): pass
        def fetchall(self): return [({"event":"loaded"},)]

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        @property
        def read_only(self): return True
        @read_only.setter
        def read_only(self, _value):
            raise AssertionError("must not change read_only after bounded setup starts a transaction")

    calls=[]
    monkeypatch.setattr(bounded_postgres_read,"connect_bounded_rootline_postgres",
        lambda **kwargs:(calls.append(kwargs) or Connection()))
    assert family_message_lifecycle._event_store("load","CARD",None)==[{"event":"loaded"}]
    assert calls==[{"database_url":None}]


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


def test_orphaned_exclusive_completion_edit_claim_gets_one_idempotent_recovery():
    memory=Memory();mission="OOM-BEACON-MEDIA-ALBUM"
    deliver_family_result(PARSED,RESULT,specialist="BEACON_MEDIA",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow_parsed={**PARSED,"provider_message_id":"504"}
    completion={**RESULT,"status":"completed","answer":"Album complete.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    interrupted=True
    def crash_after_claim(action,identity,payload):
        nonlocal interrupted
        result=memory.store(action,identity,payload)
        if (action=="record" and payload.get("state")=="update_attempted"
                and interrupted):
            interrupted=False
            raise RuntimeError("process stopped after edit claim")
        return result
    with pytest.raises(RuntimeError):
        deliver_family_result(follow_parsed,completion,specialist="BEACON_MEDIA",
            mission_id=mission,card_mission_id=mission,event_store=crash_after_claim,
            sender=memory.send,editor=memory.edit)
    recovered=deliver_family_result(follow_parsed,completion,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(follow_parsed,completion,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    assert recovered["status"]=="family_message_completion_card_updated"
    assert recovered["telegram_edits"]==1 and replay["telegram_edits"]==0
    assert len(memory.sent)==1 and len(memory.edited)==1


def test_private_media_review_unconfirmed_edit_gets_one_bounded_recovery():
    memory=Memory();mission="OOM-BEACON-MEDIA-REVIEW"
    deliver_family_result(PARSED,RESULT,specialist="BEACON_MEDIA",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    callback={**PARSED,"provider_message_id":"505"}
    recorded={**RESULT,"status":"private_media_review_recorded",
        "answer":"Library decision recorded. Public Use remains separate.",
        "owner_visible_completion_policy":"verified_edit_or_new_message",
        "delivery_recovery_required":True}
    failed_once=True
    def fail_first_edit(chat_id,message_id,text):
        nonlocal failed_once
        if failed_once:
            failed_once=False
            return {"success":False,"telegram_message_id":message_id}
        return memory.edit(chat_id,message_id,text)
    contained=deliver_family_result(callback,recorded,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=fail_first_edit)
    recovered=deliver_family_result(callback,recorded,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=fail_first_edit)
    replay=deliver_family_result(callback,recorded,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=fail_first_edit)
    assert contained["status"]=="family_message_update_contained"
    assert recovered["status"]=="family_message_completion_card_updated"
    assert recovered["telegram_edits"]==1
    assert replay["telegram_sends"]==replay["telegram_edits"]==0
    assert len(memory.sent)==1 and len(memory.edited)==1


def test_private_media_review_presentation_edits_album_card_once_and_replay_is_silent():
    memory=Memory();group="BEACON-INTAKE-GROUP-BELLA"
    receipt={**RESULT,"status":"completed","answer":"8 photos received — processing complete.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    deliver_family_result(PARSED,receipt,specialist="BEACON_MEDIA",mission_id=group,
        card_mission_id=group,event_store=memory.store,sender=memory.send,editor=memory.edit)
    trigger={**PARSED,"provider_message_id":"canonical:album-completed:"+group}
    review={**RESULT,"status":"private_media_review_presented",
        "answer":"Accept into Private Library or Decline album for Private Library.",
        "reply_markup":{"inline_keyboard":[[{"text":"Accept into Private Library"}]]},
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    presented=deliver_family_result(trigger,review,specialist="BEACON_MEDIA",
        mission_id=group+":LIBRARY",card_mission_id=group,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(trigger,review,specialist="BEACON_MEDIA",
        mission_id=group+":LIBRARY",card_mission_id=group,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    assert presented["status"]=="family_message_completion_card_updated"
    assert presented["telegram_message_id"]=="700" and presented["telegram_edits"]==1
    assert replay["telegram_sends"]==replay["telegram_edits"]==0
    assert len(memory.sent)==1 and len(memory.edited)==1


def test_completed_card_regressed_by_unbound_prior_member_is_restored_once():
    memory=Memory();mission="OOM-BEACON-MEDIA-RESTORE"
    receipt={**RESULT,"answer":"Album started. Complete it when ready."}
    completed={**RESULT,"status":"completed","answer":"Album complete.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    first=deliver_family_result(PARSED,receipt,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    middle={**PARSED,"provider_message_id":"501"}
    deliver_family_result(middle,receipt,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    final={**PARSED,"provider_message_id":"504"}
    done=deliver_family_result(final,completed,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    regressed=deliver_family_result(middle,receipt,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    restored=deliver_family_result(final,completed,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(final,completed,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    assert first["telegram_sends"]==1 and done["telegram_edits"]==1
    assert regressed["telegram_edits"]==1 and restored["telegram_edits"]==1
    assert restored["status"]=="family_message_completion_card_updated"
    assert replay["telegram_edits"]==0 and len(memory.sent)==1


def test_immutable_beacon_album_receipt_never_replaces_existing_card():
    memory=Memory();mission="OOM-BEACON-MEDIA-IMMUTABLE"
    receipt={**RESULT,"status":"media_album_received","answer":"Album started.",
        "owner_visible_card_policy":"immutable_initial_card"}
    first=deliver_family_result(PARSED,receipt,specialist="BEACON_MEDIA",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    replay=deliver_family_result({**PARSED,"provider_message_id":"501"},receipt,
        specialist="BEACON_MEDIA",mission_id=mission,card_mission_id=mission,
        event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert first["telegram_sends"]==1
    assert replay["status"]=="family_message_immutable_card_replayed_noop"
    assert replay["telegram_sends"]==replay["telegram_edits"]==0
    assert memory.edited==[]


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


def test_ambiguous_edit_is_never_retried_but_one_visible_question_is_sent():
    memory=Memory();mission="OOM-ROOTLINE-WAIT-AMBIGUOUS"
    deliver_family_result(PARSED,RESULT,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow_parsed={**PARSED,"provider_message_id":"scheduled:stale-presence"}
    follow={**RESULT,"answer":"Are you at the fertilizer valves now?",
        "requires_visible_notification":True,"question_count":1}
    edits=[]
    def ambiguous_edit(*args):
        edits.append(args);return {"success":False,"status":"provider_outcome_ambiguous"}
    first=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=ambiguous_edit)
    recovered=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=ambiguous_edit)
    replay=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=ambiguous_edit)
    assert first["status"]=="family_message_update_contained"
    assert recovered["status"]=="family_message_card_updated_and_notified"
    assert recovered["telegram_edits"]==0 and recovered["telegram_sends"]==1
    assert replay["success"] is True
    assert replay["status"]=="family_message_replayed_noop"
    assert replay["telegram_edits"]==replay["telegram_sends"]==0
    assert len(edits)==1 and len(memory.sent)==2
    notice=next(row for row in memory.rows.values()
        if row.get("state")=="notification_delivered")
    assert notice["clarification_question"]=="Are you at the fertilizer valves now?"


def test_orphaned_visible_question_edit_claim_is_not_retried_and_gets_one_notice():
    memory=Memory();mission="OOM-ROOTLINE-WAIT-ORPHAN"
    deliver_family_result(PARSED,RESULT,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow_parsed={**PARSED,"provider_message_id":"retained-expired-presence"}
    follow={**RESULT,"answer":"Are you back at the fertilizer valves now?",
        "requires_visible_notification":True,"question_count":1}
    stopped=True
    def stop_after_edit_claim(action,identity,payload):
        nonlocal stopped
        result=memory.store(action,identity,payload)
        if action=="record" and payload.get("state")=="update_attempted" and stopped:
            stopped=False
            raise RuntimeError("worker stopped after edit claim")
        return result
    with pytest.raises(RuntimeError):
        deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
            card_mission_id=mission,event_store=stop_after_edit_claim,
            sender=memory.send,editor=memory.edit)
    recovered=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert recovered["status"]=="family_message_card_updated_and_notified"
    assert recovered["telegram_edits"]==0 and recovered["telegram_sends"]==1
    assert replay["telegram_edits"]==replay["telegram_sends"]==0
    assert len(memory.edited)==0 and len(memory.sent)==2


def test_context_recovery_projection_is_not_mistaken_for_provider_delivery():
    memory=Memory();mission="OOM-ROOTLINE-CONTEXT-RECOVERY"
    deliver_family_result(PARSED,RESULT,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    memory.store("record",mission+"-UPDATE-RECOVERY-DELIVERED",{
        "event_id":mission+"-UPDATE-RECOVERY-DELIVERED","state":"updated","task_state":"waiting_for_input",
        "mission_id":mission,"card_mission_id":mission,"telegram_message_id":"700",
        "provider_message_id":"501","provider_timestamp":PARSED["provider_timestamp"],
        "recovery_provider_message_id":"501",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "inbound_text_sha256":"not-a-delivery-binding","text_sha256":"a"*64})
    follow_parsed={**PARSED,"provider_message_id":"501"}
    follow={**RESULT,"answer":"Are you still at the valves?","requires_visible_notification":True}
    result=deliver_family_result(follow_parsed,follow,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert result["status"]=="family_message_card_updated_and_notified"
    assert result["telegram_edits"]==1 and result["telegram_sends"]==1


def test_validated_v2_delivery_resume_supersedes_old_same_provider_presentation_once():
    memory=Memory();mission="OOM-ROOTLINE-V1-V2"
    deliver_family_result(PARSED,{**RESULT,"answer":"Old v1 question"},specialist="ROOTLINE",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    resumed={**RESULT,"answer":"Are you still at the valves?",
        "requires_visible_notification":True,"delivery_recovery_required":True,
        "response_contract_version":"contextual_specialist_response_v2",
        "replay_suppressed":False,"suppress_owner_delivery":False,
        "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False,
        "provider_message_id":"500","mission_id":mission,"card_mission_id":mission,
        "authority":{"configuration_write":False,"hardware_control":False,
                     "farm_write":False,"telegram_send":False}}
    first=deliver_family_result(PARSED,resumed,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(PARSED,resumed,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert first["status"]=="family_message_card_updated_and_notified"
    assert first["telegram_edits"]==1 and first["telegram_sends"]==1
    assert replay["telegram_edits"]==replay["telegram_sends"]==0


def test_unvalidated_same_provider_delivery_resume_cannot_recompose():
    memory=Memory();mission="OOM-ROOTLINE-FORGED-RESUME"
    deliver_family_result(PARSED,{**RESULT,"answer":"Old v1 question"},specialist="ROOTLINE",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    forged={**RESULT,"answer":"Forged replacement","delivery_recovery_required":True,
        "response_contract_version":"contextual_specialist_response_v2",
        "provider_message_id":"500","mission_id":mission,"card_mission_id":mission}
    result=deliver_family_result(PARSED,forged,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert result["status"]=="family_message_provider_replay_noop"
    assert result["telegram_edits"]==result["telegram_sends"]==0


def test_process_interruption_does_not_blindly_resend():
    memory=Memory();mission="OOM-HERD-INTERRUPTED"
    memory.store("record",mission+"-DELIVERY-ATTEMPT",{"card_mission_id":mission,
        "event_id":mission+"-DELIVERY-ATTEMPT","state":"delivery_attempted","text_sha256":"x"})
    result=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert result["status"]=="family_message_delivery_ambiguous"
    assert memory.sent==[]


def test_provider_acceptance_with_failed_delivered_receipt_reports_physical_truth_and_replay_noop():
    memory=Memory(); mission="OOM-PROVIDER-ACCEPTED-RECEIPT-DOWN"
    def store(action, identity, payload):
        if action == "record" and identity.endswith("-DELIVERED"):
            return {"success": False, "created": False}
        return memory.store(action, identity, payload)
    first=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=store,sender=memory.send,editor=memory.edit)
    assert first["status"]=="family_message_provider_confirmed_receipt_unavailable"
    assert first["provider_delivery_confirmed"] is True
    assert first["telegram_message_id"]=="700" and first["telegram_sends"]==1
    assert replay["status"]=="family_message_delivery_ambiguous"
    assert replay["telegram_sends"]==0 and len(memory.sent)==1


def test_visible_notification_provider_truth_survives_failed_receipt_and_replay_is_silent():
    memory=Memory(); mission="OOM-VISIBLE-RECEIPT-DOWN"
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow={**RESULT,"answer":"One bounded follow-up", "requires_visible_notification":True}
    inbound={**PARSED,"provider_message_id":"501"}
    def store(action, identity, payload):
        if action=="record" and "-VISIBLE-WAIT-" in identity and identity.endswith("-DELIVERED"):
            return {"success":False,"created":False}
        return memory.store(action,identity,payload)
    first=deliver_family_result(inbound,follow,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(inbound,follow,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=store,sender=memory.send,editor=memory.edit)
    assert first["status"]=="family_message_notification_provider_confirmed_receipt_unavailable"
    assert first["provider_delivery_confirmed"] is True and first["telegram_sends"]==1
    assert replay["telegram_sends"]==0 and len(memory.sent)==2


def test_protected_completion_uses_verified_card_edit_without_second_message():
    memory=Memory();mission="OOM-PROTECTED-COMPLETE"
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    completed={"success":True,"status":"completed","answer":"Recorded once.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    inbound={**PARSED,"provider_message_id":"501"}
    result=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert result["status"]=="family_message_completion_card_updated"
    assert result["telegram_edits"]==1 and result["telegram_sends"]==0
    assert replay["telegram_edits"]==replay["telegram_sends"]==0
    assert len(memory.sent)==1 and len(memory.edited)==1


def test_protected_completion_without_card_sends_one_message_only():
    memory=Memory();mission="OOM-PROTECTED-NEW"
    completed={"success":True,"status":"completed","answer":"Recorded once.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    result=deliver_family_result(PARSED,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result(PARSED,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert result["telegram_sends"]==1 and result["telegram_edits"]==0
    assert replay["telegram_sends"]==replay["telegram_edits"]==0


def test_protected_completion_ambiguous_edit_retries_same_card_once_without_second_message():
    memory=Memory();mission="OOM-PROTECTED-AMBIGUOUS"
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    completed={"success":True,"status":"completed","answer":"Recorded once.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    inbound={**PARSED,"provider_message_id":"501"}
    edits=[]
    def editor(*args):
        edits.append(args)
        return ({"success":False,"status":"provider_outcome_ambiguous"} if len(edits)==1
          else {"success":True,"telegram_message_id":str(args[1])})
    first=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=editor)
    delayed=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=editor)
    assert first["status"]=="family_message_update_contained"
    assert delayed["status"]=="family_message_completion_card_updated"
    assert first["telegram_sends"]==delayed["telegram_sends"]==0
    assert delayed["telegram_edits"]==1 and len(memory.sent)==1 and len(edits)==2


def test_protected_completion_requires_exact_provider_card_identity():
    mission="OOM-PROTECTED-UNVERIFIED"
    completed={"success":True,"status":"completed","answer":"Recorded once.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    inbound={**PARSED,"provider_message_id":"501"}
    for response in ({"success":True},{"success":True,"telegram_message_id":"wrong"}):
        memory=Memory()
        deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
            card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
        result=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
            card_mission_id=mission,event_store=memory.store,sender=memory.send,
            editor=lambda *args,r=response:r)
        assert result["status"]=="family_message_update_contained"
        assert result["telegram_sends"]==result["telegram_edits"]==0
        assert len(memory.sent)==1


def test_concurrent_completion_claim_allows_only_one_external_effect():
    memory=Memory();mission="OOM-PROTECTED-CONCURRENT"
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    completed={"success":True,"status":"completed","answer":"Recorded once.",
        "owner_visible_completion_policy":"verified_edit_or_new_message"}
    inbound={**PARSED,"provider_message_id":"501"}
    first=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    second=deliver_family_result(inbound,completed,specialist="HERDMASTER",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert first["telegram_edits"]==1 and first["telegram_sends"]==0
    assert second["telegram_edits"]==second["telegram_sends"]==0
    assert len(memory.edited)==1


def test_concurrent_mixer_reassessment_preview_has_one_visible_effect_at_most():
    memory=Memory(); mission="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    deliver_family_result(PARSED,RESULT,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    preview={"success":True,"status":"waiting_for_input",
        "answer":"Mixer CH2 five-minute protected preview; fresh confirmation required.",
        "contextual_task_kind":"fertilizer_commissioning","hardware_commands":0,
        "provider_control_calls":0}
    inbound={**PARSED,"provider_message_id":"scheduled:mixer-reassessment-1"}
    barrier=Barrier(2); claim_lock=Lock(); effects=[]
    def concurrent_store(action,identity,payload):
        if action=="load":
            rows=list(memory.rows.values()); barrier.wait(timeout=5); return rows
        with claim_lock:
            return memory.store(action,identity,payload)
    def edit(chat,message_id,text):
        with claim_lock: effects.append((chat,message_id,text))
        return {"success":True,"telegram_message_id":message_id}
    def invoke(_):
        return deliver_family_result(inbound,preview,specialist="ROOTLINE",mission_id=mission,
            card_mission_id=mission,event_store=concurrent_store,sender=memory.send,editor=edit)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(invoke,range(2)))
    assert sum(result["telegram_edits"] for result in results)==1
    assert sum(result["telegram_sends"] for result in results)==0
    assert {result["status"] for result in results}=={
        "family_message_card_updated","family_message_update_delivery_ambiguous"}
    assert len(effects)==1
    replay=deliver_family_result(inbound,preview,specialist="ROOTLINE",mission_id=mission,
        card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert replay["telegram_edits"]==replay["telegram_sends"]==0


def test_protected_completion_verified_edit_removes_preview_buttons():
    memory=Memory();mission="OOM-PROTECTED-CLEAR-BUTTONS"
    preview={**RESULT,"status":"preview_ready","reply_markup":{"inline_keyboard":[[
      {"text":"Bevestig alles","callback_data":"oompa:opaque:confirm"}]]}}
    deliver_family_result(PARSED,preview,specialist="HERDMASTER",mission_id=mission,
      card_mission_id=mission,event_store=memory.store,sender=memory.send)
    captured={}
    def edit(chat,message,text,reply_markup=None):
        captured["reply_markup"]=reply_markup
        return {"success":True,"telegram_message_id":message}
    completed={"success":True,"status":"grouped_weights_completed","answer":"4 weights recorded exactly as previewed.",
      "owner_visible_completion_policy":"verified_edit_or_new_message"}
    with patch("modules.oom_sakkie.family_message_lifecycle._edit_telegram",side_effect=edit):
        result=deliver_family_result({**PARSED,"provider_message_id":"501"},completed,
          specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store)
    assert result["telegram_edits"]==1 and result["telegram_sends"]==0
    assert captured["reply_markup"]=={"inline_keyboard":[]}


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
