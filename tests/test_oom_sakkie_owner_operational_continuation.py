from datetime import datetime, timezone
from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.owner_operational_continuation import handle_owner_operational_continuation
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result

NOW=datetime(2026,8,3,20,42,35,tzinfo=timezone.utc)

def parsed(text="C Camp has stopped",message="3219",reply=""):
    timestamp=(datetime(2026,8,3,20,43,3,tzinfo=timezone.utc) if message=="3221" else NOW)
    return {"text":text,"telegram_user_id":"42","telegram_chat_id":"42",
        "provider_message_id":message,"provider_timestamp":timestamp.isoformat(),
        "reply_to_message_id":reply}

def c_active(state="StoppedAwaitingVerification"):
    return {"mission_id":"OOM-ROOTLINE-69C2F9CE688CAA8B6B4F819A",
        "card_mission_id":"OOM-ROOTLINE-69C2F9CE688CAA8B6B4F819A-C-SEGMENT-1-20260803",
        "completion_card_mission_id":"OOM-ROOTLINE-69C2F9CE688CAA8B6B4F819A-C-SEGMENT-1-20260803-COMPLETION",
        "execution_id":"ROOTLINE-IRRIGATION-2CBB37586FE70DD527D9F54C",
        "domain":"irrigation","entity_id":"C12345","state":state,
        "execution_started_at":"2026-08-03T19:35:07+00:00","telegram_message_id":"3218"}

def memory_store():
    rows={}
    def store(action,identity,payload):
        if identity in rows:return {"success":True,"created":False}
        rows[identity]=dict(payload);return {"success":True,"created":True}
    return rows,store

def test_active_c_execution_consumes_natural_physical_stop_before_clarification():
    rows,store=memory_store()
    result,status=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[c_active()]),context_store=store,now=NOW)
    assert status==200 and result["status"]=="Completed"
    assert result["execution_id"]=="ROOTLINE-IRRIGATION-2CBB37586FE70DD527D9F54C"
    assert result["observation"]["observed_at"]==NOW.isoformat()
    assert result["observation"]["exact_runtime"]=="Unknown"
    assert result["hardware_commands"]==0 and len(rows)==1
    replay,_=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[c_active()]),context_store=store,now=NOW)
    assert replay["status"]=="owner_operational_transition_replayed_noop"
    assert replay["telegram_sends"]==0 and len(rows)==1

def test_pending_clarification_consumes_irrigation_before_keyword_routing():
    pending={"mission_id":"OOM-CLARIFY-1","card_mission_id":"OOM-CLARIFY-1",
        "candidate_domains":["herd","irrigation"],"telegram_message_id":"3220",
        "clarification_delivered_at":"2026-08-03T20:42:46+00:00",
        "historical_domain_only":True,
        "target_mission_id":c_active()["mission_id"],"target_execution_id":c_active()["execution_id"]}
    rows,store=memory_store()
    result,status=handle_owner_operational_continuation(parsed("Irrigation","3221"),
        issue_gateway_owner_authority("42","42"),lifecycle_loader=lambda *_:([pending],[]),
        context_store=store,now=NOW)
    assert status==200 and result["status"]=="owner_clarification_consumed"
    assert result["domain"]=="irrigation" and result["suppress_owner_delivery"] is True
    replay,_=handle_owner_operational_continuation(parsed("Irrigation","3221"),
        issue_gateway_owner_authority("42","42"),lifecycle_loader=lambda *_:([pending],[]),
        context_store=store,now=NOW)
    assert replay["status"]=="clarification_replayed_noop"

def test_explicit_stop_outranks_simultaneous_pending_clarification():
    pending={"mission_id":"OOM-CLARIFY-1","candidate_domains":["irrigation"],
        "clarification_delivered_at":"2026-08-03T20:42:30+00:00"}
    result,_=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([pending],[c_active()]),context_store=memory_store()[1],now=NOW)
    assert result["status"]=="Completed" and result["execution_id"]==c_active()["execution_id"]

def test_multiple_domains_with_one_compatible_entity_selects_only_c():
    herd={"mission_id":"HERD-1","card_mission_id":"HERD-1","domain":"herd",
          "entity_id":"PIG-1","state":"waiting"}
    result,_=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[herd,c_active()]),context_store=memory_store()[1],now=NOW)
    assert result["execution_id"]==c_active()["execution_id"]

def test_genuine_ambiguity_asks_once_and_completed_case_does_not_consume_unrelated():
    rows,store=memory_store()
    other={**c_active(),"entity_id":"B12345","card_mission_id":"B-SEGMENT"}
    result,_=handle_owner_operational_continuation(parsed("It has stopped"),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[c_active(),other]),context_store=store,now=NOW)
    assert result["status"]=="owner_context_clarification_required" and result["question_count"]==1
    completed={**c_active(state="Completed")}
    unrelated,_=handle_owner_operational_continuation(parsed("Customer replied","3225"),
        issue_gateway_owner_authority("42","42"),lifecycle_loader=lambda *_:([],[completed]),
        context_store=store,now=NOW)
    assert unrelated["handled"] is False

def test_same_domain_ambiguity_requires_entity_and_then_selects_it():
    pending={"mission_id":"OOM-CLARIFY-BC","card_mission_id":"OOM-CLARIFY-BC",
        "candidate_domains":["irrigation"],"telegram_message_id":"3220",
        "clarification_delivered_at":"2026-08-03T20:42:46+00:00",
        "candidate_bindings":[
            {"domain":"irrigation","entity_id":"B12345","mission_id":"B","execution_id":"B-EXEC"},
            {"domain":"irrigation","entity_id":"C12345","mission_id":"C","execution_id":"C-EXEC"}]}
    vague,_=handle_owner_operational_continuation(parsed("Irrigation","3221"),
        issue_gateway_owner_authority("42","42"),lifecycle_loader=lambda *_:([pending],[]),
        context_store=memory_store()[1],now=NOW)
    assert vague["handled"] is True
    assert vague["status"]=="owner_clarification_still_pending"
    assert vague["suppress_owner_delivery"] is True and vague["question_count"]==0
    precise,_=handle_owner_operational_continuation(parsed("C Camp irrigation","3221"),
        issue_gateway_owner_authority("42","42"),lifecycle_loader=lambda *_:([pending],[]),
        context_store=memory_store()[1],now=NOW)
    assert precise["status"]=="owner_clarification_consumed"
    assert precise["execution_id"]=="C-EXEC"

def test_anonymous_or_mismatched_owner_cannot_consume_context():
    for authority in (None,issue_gateway_owner_authority("99","99")):
        result,_=handle_owner_operational_continuation(parsed(),authority,
            lifecycle_loader=lambda *_:([],[c_active()]),context_store=memory_store()[1],now=NOW)
        assert result["handled"] is False

def test_negated_or_unrelated_off_text_never_closes_execution():
    for text in ("C Camp is not off", "The borehole is off; C Camp is still running", "I am taking the day off"):
        result,_=handle_owner_operational_continuation(parsed(text),issue_gateway_owner_authority("42","42"),
            lifecycle_loader=lambda *_:([],[c_active()]),context_store=memory_store()[1],now=NOW)
        assert result["handled"] is False

def test_stop_before_execution_start_is_not_consumed():
    old=parsed();old["provider_timestamp"]="2026-08-03T19:30:00+00:00"
    result,_=handle_owner_operational_continuation(old,issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[c_active()]),context_store=memory_store()[1],now=NOW)
    assert result["handled"] is False

def test_b_and_implicit_stop_render_selected_target_without_unrelated_claims():
    b={**c_active(),"entity_id":"B12345","card_mission_id":"B-SEGMENT"}
    result,_=handle_owner_operational_continuation(parsed("It has stopped"),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[b]),context_store=memory_store()[1],now=NOW)
    assert result["observation"]["entity_id"]=="B12345"
    assert "B CAMP" in result["answer"] and "C remains off" not in result["answer"]

def test_store_failure_contains_without_completion_claim():
    for store in (lambda *_:(_ for _ in ()).throw(RuntimeError("down")),
                  lambda *_:{"success":False,"created":None}):
        result,status=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
            lifecycle_loader=lambda *_:([],[c_active()]),context_store=store,now=NOW)
        assert status==503 and result["writes_operational_outcome"] is None
        assert result["writes_operational_outcome_unknown"] is True

def test_committed_completion_exact_replay_is_handled_before_legacy_routing():
    prior={"state":"execution_completed","mission_id":c_active()["mission_id"],
        "card_mission_id":c_active()["card_mission_id"],
        "completion_card_mission_id":c_active()["completion_card_mission_id"],
        "execution_id":c_active()["execution_id"],"entity":"C12345","label":"C Camp",
        "provider_message_id":"3219","provider_timestamp":NOW.isoformat(),
        "text_sha256":"40caab69047d636732c130441f646425bf0956d5d43d11fc23eb8ccc2975ceb8"}
    result,status=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[],[prior]),context_store=memory_store()[1],now=NOW)
    assert status==200 and result["handled"] is True
    assert result["status"]=="owner_operational_transition_replayed_noop"
    assert result["mission_id"]==c_active()["mission_id"]
    assert result["hardware_commands"]==0
    assert result["writes_operational_outcome"] is False
    assert result["operational_outcome_recorded"] is True

def test_first_completion_and_exact_replay_render_identically():
    rows,store=memory_store()
    first,_=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[c_active()],[]),context_store=store,now=NOW)
    prior=next(iter(rows.values()))
    replay,_=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[],[prior]),context_store=store,now=NOW)
    assert first["answer"]==replay["answer"]
    assert first["card_mission_id"]==replay["card_mission_id"]

def test_ambiguous_3218_is_never_edited_and_completion_delivery_replays_zero():
    events={
        "old-delivered":{"card_mission_id":c_active()["card_mission_id"],"state":"delivered","telegram_message_id":"3218","text_sha256":"a"*64},
        "old-contained":{"card_mission_id":c_active()["card_mission_id"],"state":"contained","telegram_message_id":"3218","text_sha256":"b"*64},
    }
    def family_store(action,identity,payload):
        if action=="load":return [row for row in events.values() if row.get("card_mission_id")==identity]
        if identity in events:return {"success":True,"created":False}
        events[identity]=dict(payload);return {"success":True,"created":True}
    sends=[];edits=[]
    result,_=handle_owner_operational_continuation(parsed(),issue_gateway_owner_authority("42","42"),
        lifecycle_loader=lambda *_:([],[c_active()]),context_store=memory_store()[1],now=NOW)
    first=deliver_family_result(parsed(),result,specialist="ROOTLINE",mission_id=result["mission_id"],
        card_mission_id=result["card_mission_id"],event_store=family_store,
        sender=lambda *_:(sends.append(True) or {"success":True,"telegram_message_id":"3223"}),
        editor=lambda *_:(edits.append(True) or {"success":True}))
    replay=deliver_family_result(parsed(),result,specialist="ROOTLINE",mission_id=result["mission_id"],
        card_mission_id=result["card_mission_id"],event_store=family_store,
        sender=lambda *_:(sends.append(True) or {"success":True,"telegram_message_id":"3224"}),
        editor=lambda *_:(edits.append(True) or {"success":True}))
    assert first["telegram_message_id"]=="3223" and len(sends)==1 and edits==[]
    assert replay["telegram_sends"]==0 and replay["telegram_edits"]==0

@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_operational_continuation")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_gateway_continuation_precedes_legacy_irrigation_status(owner_task,continuation,deliver):
    owner_task.return_value=({"handled":False},200)
    continuation.return_value=({"handled":True,"success":True,"status":"owner_clarification_consumed",
        "suppress_owner_delivery":True,"mission_id":"OOM-CLARIFY-1","answer":""},200)
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":3221,"date":1785789783,"text":"Irrigation",
        "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    value,status=handle_telegram_gateway_message(payload,headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200 and value["message"]["status"]=="owner_clarification_consumed"
    assert value["message"].get("tool_used")!="irrigation_status"
    deliver.assert_not_called()
