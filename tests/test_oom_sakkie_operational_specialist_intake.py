from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.operational_specialist_intake import (
    handle_operational_specialist_message, recover_contextual_specialist_replay,
    _project_pending_history)
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie import operational_specialist_intake
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.rootline_operational_adapter import _recovery_observations

NOW = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)
TEXT = "I am at the B and C valve area now, can observe both camps, and can intervene immediately for supervised commissioning."


def test_retained_manager_reservoir_fact_reconstructs_only_exact_provider_bound_observation():
    assert _recovery_observations(
        [{"subject": "reservoir", "state": "FULL"}], "3717",
        "2026-08-17T16:03:17+00:00") == [{
            "kind": "reservoir_level", "value": "1/1", "numerator": 1,
            "denominator": 1, "semantic_state": "FULL",
            "provider_message_id": "3717",
            "observed_at": "2026-08-17T16:03:17+00:00"}]
    assert _recovery_observations(
        [{"subject": "it", "state": "FULL"}], "3717",
        "2026-08-17T16:03:17+00:00") == []

@pytest.fixture(autouse=True)
def operation_store(monkeypatch):
    events={}
    def store(action, identity, payload):
        if action=="load": return [row for row in events.values() if row.get("mission_id")==identity]
        if identity in events: return {"success":True,"created":False}
        events[identity]=dict(payload); return {"success":True,"created":True}
    monkeypatch.setattr(operational_specialist_intake,"_operation_event_store",store)
    monkeypatch.setattr(operational_specialist_intake,"persist_rootline_observations",
        lambda context,_authority:{"success":True,"contract_version":"rootline_owner_observation_bridge_v1",
                         "status":"exact_replay","created":False,"canonical_writes":0,
                         "observation_ids":[f"OBS-{index}" for index,_ in enumerate(context["observations"])]})
    return events

def parsed(at=NOW, message="3181"):
    return {"text": TEXT, "telegram_user_id": "42", "telegram_chat_id": "42",
            "provider_message_id": message, "provider_timestamp": at.isoformat()}

def result():
    return {"success": True, "contract_version": "rootline_commissioning_continuation_adapter_v1",
            "writes_performed": False, "specialist_acceptance": True,
            "authorization_current": True,
            "authority": {"hardware_control": False, "configuration_write": False, "telegram_send": False},
            "hardware_commands": 0,
            "evidence_cutoff": NOW.isoformat(), "result_id": "ROOTLINE-RESULT-1"}

def test_fresh_authenticated_presence_is_accepted_without_hardware_authority():
    value, status = handle_operational_specialist_message(parsed(),
        issue_gateway_owner_authority("42", "42"), now=NOW, rootline_dispatcher=lambda _context: result())
    assert status == 200 and value["dispatch_state"] == "specialist_accepted"
    assert value["hardware_commands"] == 0 and value["writes_farm_data"] is False
    assert len(value["result_digest"]) == 64

def test_stale_presence_is_preserved_but_never_dispatched_or_actuated():
    calls=[]
    value, status = handle_operational_specialist_message(parsed(NOW-timedelta(seconds=301)),
        issue_gateway_owner_authority("42", "42"), now=NOW,
        rootline_dispatcher=lambda _context: calls.append(True))
    assert status == 200 and value["systemic_exception"] == "rootline_physical_presence_stale"
    assert calls == [] and value["hardware_commands"] == 0

def test_missing_adapter_is_one_visible_typed_exception():
    value, status = handle_operational_specialist_message(parsed(),
        issue_gateway_owner_authority("42", "42"), now=NOW, rootline_dispatcher=None)
    assert status == 503 and value["systemic_exception"] == "rootline_deployed_adapter_unavailable"
    assert value["answer"] and value["sends_telegram"] is False

def test_every_rootline_authority_escalation_is_contained():
    changed=[]
    for field in ("hardware_control","configuration_write","telegram_send"):
        item=result(); item["authority"]={**item["authority"],field:True}; changed.append(item)
    item=result(); item["hardware_commands"]=1; changed.append(item)
    item=result(); item["authorization_current"]=False; changed.append(item)
    for evidence in changed:
        value,status=handle_operational_specialist_message(parsed(),issue_gateway_owner_authority("42","42"),
            now=NOW,rootline_dispatcher=lambda _context,x=evidence:x)
        assert status==503 and value["systemic_exception"]=="rootline_deployed_adapter_result_invalid"
        assert value["hardware_commands"]==0 and value["writes_farm_data"] is False

def test_malformed_hardware_command_counts_are_contained_without_escaping():
    for malformed in ("invalid", {"count": 0}, [0], False, None):
        item=result(); item["hardware_commands"]=malformed
        value,status=handle_operational_specialist_message(parsed(),issue_gateway_owner_authority("42","42"),
            now=NOW,rootline_dispatcher=lambda _context,x=item:x)
        assert status==503 and value["systemic_exception"]=="rootline_deployed_adapter_result_invalid"
        assert value["hardware_commands"]==0 and value["writes_farm_data"] is False

def test_unrelated_message_is_not_claimed_and_anonymous_presence_is_denied():
    unrelated, _ = handle_operational_specialist_message({**parsed(), "text":"Pig 125 is found dead"}, None, now=NOW)
    denied, status = handle_operational_specialist_message(parsed(), None, now=NOW)
    assert unrelated["handled"] is False
    assert status == 409 and denied["systemic_exception"] == "operational_specialist_auth_or_chronology_invalid"

def operational(text="Reservoir 4/4 and the storage tanks are 2/4. C camps do need irrigation now."):
    return {**parsed(message="3213"), "text": text}

def operational_result(**changes):
    value={"success":True,"contract_version":"rootline_operational_dispatch_result_v1",
           "specialist_acceptance":True,"recommendation":"Run C",
           "evidence_generation":"ROOTLINE-GEN-1","hardware_commands":0,
           "authority":{"telegram_send":False,"hardware_control":False,
                        "farm_observation_write":False,"automatic_on_retry":False}}
    value.update(changes); return value

def test_water_levels_and_visible_c_need_outrank_legacy_irrigation_reader():
    calls=[]
    value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda context:(calls.append(context) or operational_result()))
    assert status==200 and value["specialist_identity"]=="ROOTLINE"
    assert value["visible_irrigation_need_zone"]=="C12345"
    assert [(x["kind"],x["value"]) for x in value["observations"]]==[("reservoir_level","4/4"),("storage_level","2/4")]
    assert all(x["provider_message_id"]=="3213" and x["observed_at"]==NOW.isoformat() for x in value["observations"])
    assert calls[0]["authority"]["hardware_control"] is False
    assert value["hardware_commands"]==0

def test_semantic_rootline_plan_question_is_not_claimed_as_owner_observation():
    request = {**operational("What is today's irrigation plan for B and C Camps?"),
        "semantic": {"domain": "rootline", "intent": "request_irrigation_plan",
                     "message_kind": "question", "needs_clarification": False}}
    value,status=handle_operational_specialist_message(request,issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _context: pytest.fail("question was dispatched as evidence"))
    assert status==200 and value["handled"] is False

def test_one_water_level_routes_independently_without_demanding_both():
    value,status=handle_operational_specialist_message(operational("Storage tanks 2/4"),
        issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _context:operational_result(recommendation="Needs Data"))
    assert status==200 and len(value["observations"])==1
    assert value["observations"][0]["kind"]=="storage_level"

def test_plain_storage_fraction_and_visible_c_need_are_both_retained():
    value,status=handle_operational_specialist_message(
        operational("Reservoir is 4/4 and Storage is 4/4.\nC camp do need water"),
        issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _context:operational_result(recommendation="Reassess"))
    assert status==200 and value["visible_irrigation_need_zone"]=="C12345"
    assert [(row["kind"],row["value"]) for row in value["observations"]]==[
        ("reservoir_level","4/4"),("storage_level","4/4")]


@pytest.mark.parametrize("text,language,facts", [
    ("Storage tanks and Reservoir is full", "en", [{"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}]),
    ("Storage and reservoir are full.", "en", [{"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}]),
    ("Both tanks are full.", "en", [{"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}]),
    ("Die opgaartenks en reservoir is vol.", "af", [{"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}]),
    ("Reservoir vol, storage ook vol.", "mixed", [{"subject":"reservoir","state":"FULL"},{"subject":"storage_tanks","state":"FULL"}]),
    ("Storage 3/4 and reservoir full.", "en", [{"subject":"storage_tanks","numerator":3,"denominator":4},{"subject":"reservoir","state":"FULL"}]),
])
def test_semantic_water_observation_family_is_typed_without_phrase_rules(text, language, facts):
    item={**operational(text),"semantic":{"domain":"rootline","intent":"water_levels_observed",
        "message_kind":"observation","observation":text,"observation_facts":facts,
        "language":language,"needs_clarification":False}}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _context:operational_result(recommendation="Hold"))
    assert status==200 and [row["kind"] for row in value["observations"]]==[
        "storage_level" if fact["subject"]=="storage_tanks" else "reservoir_level" for fact in facts]
    assert value["answer"].startswith("<b>WATER LEVELS RECORDED</b>")
    assert "No command" not in value["answer"]


def test_ambiguous_tank_observation_asks_no_writer_or_dispatcher():
    item={**operational("the tank is fine"),"semantic":{"domain":"rootline","intent":"water_level_ambiguous",
        "message_kind":"observation","observation":"A tank is described as fine.","observation_facts":[],
        "needs_clarification":True,"clarification_question":"Do you mean the storage tanks or the reservoir?"}}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _:pytest.fail("ambiguous evidence must not dispatch"),
        rootline_observation_writer=lambda *_:pytest.fail("ambiguous evidence must not write"))
    assert status==200 and value["handled"] is False


@pytest.mark.parametrize("text,language", [
    ("Done; at fertilizer valves now", "en"),
    ("Klaar; ek is nou by die kunsmiskleppe", "af"),
    ("Done, ek is nou by die fertilizer valves", "mixed"),
])
def test_contextual_commissioning_reply_binds_existing_specialist_before_observation(text, language):
    item={**operational(text),"provider_message_id":"3481","semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"observation",
        "continuation":True,"observation":"True","observation_facts":[],
        "language":language,"needs_clarification":False}}
    pending=lambda _:[{"mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "owner_user_id":"42","chat_id":"42",
        "specialist_identity":"ROOTLINE","task_state":"waiting_for_input",
        "telegram_message_id":"3480","delivery_provider_timestamp":NOW.isoformat(),
        "semantic_intent":"fertilizer_commissioning"}]
    calls=[]
    def followup(context,now=None):
        calls.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"waiting_for_input","answer":"Exact controller conflict",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,contextual_specialist_dispatcher=followup,
        rootline_observation_writer=lambda *_:pytest.fail("context reply must not enter observation writer"))
    assert status==200 and value["mission_id"]=="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    assert value["card_mission_id"]=="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    assert value["hardware_commands"]==0 and len(calls)==1


def test_exact_live_stale_projection_remains_actor_mission_age_and_digest_bound():
    observed=datetime(2026,8,24,15,26,34,tzinfo=timezone.utc)
    item={**operational(
        "I am at the fertilizer valves and ready for the five-minute Mixer CH2 commissioning test."),
        "provider_message_id":"4001","provider_timestamp":observed.isoformat(),
        "semantic":{"domain":"rootline","intent":"commissioning_ready",
            "message_kind":"confirmation","continuation":True,"language":"en",
            "needs_clarification":False}}
    pending=lambda _:[{"mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "state":"updated","task_state":"waiting_for_input",
        "telegram_message_id":"3480","notification_message_id":"3674",
        "delivery_provider_timestamp":"2026-08-10T11:00:08+00:00",
        "contextual_task_kind":"fertilizer_commissioning",
        "required_owner_confirmations":["physical_presence_at_fertilizer_valves",
            "exactly_one_mixer_ch2_five_minute_test"],
        "text_sha256":"a"*64}]
    captured=[]
    def followup(context,now=None):
        captured.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"specialist_accepted","answer":"Protected preview ready",
            "next_specialist_step":"supervised_fertilizer_mixer_proof",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=observed,pending_specialist_loader=pending,contextual_specialist_dispatcher=followup)
    assert status==200 and value["status"]=="specialist_accepted"
    assert captured[0]["mission_id"]=="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    assert captured[0]["parent_telegram_message_id"]=="3480"
    assert len(captured[0]["text_sha256"])==64
    assert value["hardware_commands"]==0 and value["provider_control_calls"]==0


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_manager_question_reply")
@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_operational_continuation")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_exact_mixer_presence_precedes_stale_generic_operational_context(
        owner_task, continuation, operational, manager_question, deliver):
    owner_task.return_value=({"handled":False},200)
    continuation.return_value=({"handled":True,"success":False,
        "status":"owner_operational_replay_binding_conflict"},409)
    operational.return_value=({"handled":True,"success":True,"status":"specialist_accepted",
        "answer":"Protected preview ready","specialist_identity":"ROOTLINE",
        "next_specialist_step":"supervised_fertilizer_mixer_proof",
        "mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False},200)
    deliver.return_value={"success":True,"status":"family_message_delivered",
        "telegram_sends":1,"telegram_edits":0}
    manager_question.return_value=({"handled":True,"success":True,
        "status":"manager_question_rootline_observation_ambiguous",
        "answer":"Which is full: the reservoir or the storage tanks?"},409)
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1",
         "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":4001,"date":1787585194,
        "text":"I am at the fertilizer valves and ready for the five-minute Mixer CH2 commissioning test.",
        "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    protected={"handled":True,"success":True,"status":"auxiliary_started",
        "answer":"<b>MIXER CH2 — SUPERVISED TEST</b>\n\nNothing has started yet. Confirm / Cancel.",
        "mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "callback_token":"TOKEN","preview_digest":"DIGEST",
        "hardware_commands":1,"provider_control_calls":1,"writes_farm_data":False}
    protected.update({"answer":"<b>MIXER CH2 - STARTED</b> Bounded provider-monitored run started."})
    with patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",
               return_value=None), patch(
               "modules.oom_sakkie.rootline_fertilizer_commissioning_runtime.execute_fertilizer_commissioning_under_standing_authority",
               return_value=protected) as execute_standing, patch(
               "modules.oom_sakkie.telegram_gateway._bind_protected_preview_card",
               side_effect=lambda result, delivery: delivery) as bind_card:
        value,status=handle_telegram_gateway_message(payload,
            headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200 and value["message"]["status"]=="auxiliary_started"
    assert value["message"]["card_mission_id"]=="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    assert "STARTED" in value["answer"] and "Confirm / Cancel" not in value["answer"]
    assert "reply_markup" not in value["message"]
    execute_standing.assert_called_once()
    bind_card.assert_called_once()
    continuation.assert_not_called()
    manager_question.assert_not_called()
    operational.assert_called_once()
    assert value["message"]["hardware_commands"]==1


@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_operational_continuation")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_nonexact_fertilizer_wording_cannot_bypass_generic_context_order(
        owner_task, continuation, operational):
    owner_task.return_value=({"handled":False},200)
    continuation.return_value=({"handled":True,"success":True,"status":"contained",
        "suppress_owner_delivery":True},200)
    operational.return_value=({"handled":False},200)
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1",
         "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":4002,"date":1787585194,
        "text":"I am near the fertilizer area.",
        "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    with patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",
               return_value=None):
        _,status=handle_telegram_gateway_message(payload,
            headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200
    continuation.assert_called_once()
    operational.assert_not_called()


def test_exact_mixer_readiness_outranks_generic_rootline_water_power_semantics():
    item={**operational(
        "I am at the fertilizer valves and ready for the five-minute Mixer CH2 commissioning test."),
        "provider_message_id":"3599","semantic":{
            "domain":"rootline","intent":"rootline_advice","message_kind":"observation",
            "continuation":False,"observation":"Owner is ready at fertilizer valves.",
            "observation_facts":[],"language":"en","needs_clarification":False}}
    pending=lambda _:[{"mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "task_state":"waiting_for_input","telegram_message_id":"3480",
        "delivery_provider_timestamp":NOW.isoformat(),
        "contextual_task_kind":"fertilizer_commissioning"}]
    calls=[]
    def followup(context,now=None):
        calls.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"waiting_for_input","answer":"Protected Mixer confirmation is ready.",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,contextual_specialist_dispatcher=followup,
        rootline_operations_dispatcher=lambda *_:pytest.fail("generic ROOTLINE planning consumed commissioning readiness"),
        rootline_observation_writer=lambda *_:pytest.fail("generic observation writer consumed commissioning readiness"))
    assert status==200 and value["contextual_task_kind"]=="fertilizer_commissioning"
    assert value["mission_id"]=="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    assert len(calls)==1 and value["hardware_commands"]==0


def test_exact_mixer_readiness_without_one_current_context_is_contained_not_generic():
    item={**operational(
        "I am at the fertilizer valves and ready for the five-minute Mixer CH2 commissioning test."),
        "provider_message_id":"3599","semantic":{
            "domain":"rootline","intent":"rootline_advice","message_kind":"observation",
            "continuation":False,"observation":"Owner is ready.","observation_facts":[],
            "language":"en","needs_clarification":False}}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=lambda _:[],
        rootline_operations_dispatcher=lambda *_:pytest.fail("generic ROOTLINE planning consumed commissioning readiness"))
    assert status==200 and value["systemic_exception"]=="fertilizer_commissioning_context_not_current"
    assert value["hardware_commands"]==0 and value["writes_farm_data"] is False


def test_multiple_pending_specialist_questions_do_not_enter_observation_writer():
    item={**operational("Done; at the valves now"),"semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"observation",
        "continuation":True,"observation":"True","observation_facts":[],
        "needs_clarification":False}}
    pending=lambda _:[{"mission_id":str(i),"card_mission_id":str(i),"specialist_identity":"ROOTLINE",
        "owner_user_id":"42","chat_id":"42","contextual_task_kind":"fertilizer_commissioning",
        "task_state":"waiting_for_input","telegram_message_id":str(i)} for i in (1,2)]
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,
        rootline_observation_writer=lambda *_:pytest.fail("ambiguous continuation must not write"))
    assert status==200 and value["status"]=="waiting_for_input"
    assert value["question_count"]==1 and value["hardware_commands"]==0


def test_context_loader_failure_fails_closed_before_observation_writer():
    item={**operational("Done; at fertilizer valves now"),"semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"observation",
        "continuation":True,"observation":"True","observation_facts":[],
        "needs_clarification":False}}
    def unavailable(_): raise RuntimeError("database unavailable")
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=unavailable,
        rootline_observation_writer=lambda *_:pytest.fail("lookup failure must not become observation"))
    assert status==200 and value["status"]=="waiting_for_input"
    assert value["hardware_commands"]==0 and value["writes_farm_data"] is False


def test_reply_identity_mismatch_fails_closed_before_observation_writer():
    item={**operational("Done; at fertilizer valves now"),"reply_to_message_id":"9999","semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"confirmation",
        "continuation":True,"observation":"False","observation_facts":[],
        "needs_clarification":False}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42",
        "specialist_identity":"ROOTLINE","task_state":"waiting_for_input",
        "telegram_message_id":"3480","delivery_provider_timestamp":NOW.isoformat(),
        "contextual_task_kind":"fertilizer_commissioning"}]
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,
        rootline_observation_writer=lambda *_:pytest.fail("reply mismatch must not become observation"))
    assert status==200 and value["status"]=="waiting_for_input"


def test_contextual_followup_replay_uses_durable_result_without_second_readback():
    item={**operational("Done; at fertilizer valves now"),"provider_message_id":"3481","semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"confirmation",
        "continuation":True,"observation":"False","observation_facts":[],
        "language":"en","needs_clarification":False}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42",
        "specialist_identity":"ROOTLINE","task_state":"waiting_for_input",
        "telegram_message_id":"3480","delivery_provider_timestamp":NOW.isoformat(),
        "contextual_task_kind":"fertilizer_commissioning"}]
    calls=[]
    def followup(context,now=None):
        calls.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"waiting_for_input","answer":"CH2 remains off",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    authority=issue_gateway_owner_authority("42","42")
    first,first_status=handle_operational_specialist_message(item,authority,now=NOW,
        pending_specialist_loader=pending,contextual_specialist_dispatcher=followup)
    second,second_status=handle_operational_specialist_message(item,authority,now=NOW,
        pending_specialist_loader=pending,contextual_specialist_dispatcher=followup)
    assert first_status==second_status==200 and len(calls)==1
    assert second["status"]=="contextual_specialist_replay_suppressed"
    assert second["hardware_commands"]==0


def test_presence_only_does_not_become_structured_configuration_confirmation():
    item={**operational("I am at the fertilizer valves"),"semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"observation",
        "continuation":True,"language":"en","needs_clarification":False}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "task_state":"waiting_for_input","telegram_message_id":"3480",
        "delivery_provider_timestamp":NOW.isoformat(),
        "contextual_task_kind":"fertilizer_commissioning",
        "required_owner_confirmations":["interlock_off","no_enabled_scene"],
        "confirmation_prompt_sha256":"a"*64,"text_sha256":"a"*64}]
    captured=[]
    def followup(context,now=None):
        captured.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"waiting_for_input","answer":"Setup evidence still needed",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,contextual_specialist_dispatcher=followup)
    assert status==200 and captured[0]["owner_confirmed_requested_setup"] is False
    assert value["hardware_commands"]==0


@pytest.mark.parametrize("text,language", [
    ("No, Interlock is still on and a Scene is enabled", "en"),
    ("Nee, Interlock is nog aan en 'n Scene is aktief", "af"),
])
def test_negative_configuration_confirmation_never_becomes_setup_proof(text,language):
    item={**operational(text),"semantic":{
        "domain":"rootline","intent":"commissioning_ready","message_kind":"confirmation",
        "continuation":True,"language":language,"needs_clarification":False,
        "confirmation_facts":{"interlock_off":False,"no_enabled_scene":False}}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "task_state":"waiting_for_input","telegram_message_id":"3480",
        "delivery_provider_timestamp":NOW.isoformat(),
        "contextual_task_kind":"fertilizer_commissioning",
        "required_owner_confirmations":["interlock_off","no_enabled_scene"],
        "confirmation_prompt_sha256":"a"*64,"text_sha256":"a"*64}]
    captured=[]
    def followup(context,now=None):
        captured.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"waiting_for_input","answer":"Unsafe settings remain",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,contextual_specialist_dispatcher=followup)
    assert status==200 and captured[0]["owner_confirmed_requested_setup"] is False
    assert captured[0]["owner_confirmation_facts"]=={
        "interlock_off":False,"no_enabled_scene":False}
    assert value["hardware_commands"]==0


def test_later_ch2_and_presence_reply_retains_prior_accepted_checklist_facts():
    item={**operational("CH2 inching is now on at 300 seconds and I’m back at the fertilizer valves ready for the test."),
        "provider_message_id":"3486","semantic":{"domain":"rootline","intent":"fertilizer_commissioning",
        "message_kind":"observation","continuation":True,"language":"en",
        "confirmation_facts":None,"needs_clarification":False}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "task_state":"waiting_for_input","telegram_message_id":"3480",
        "delivery_provider_timestamp":NOW.isoformat(),"contextual_task_kind":"fertilizer_commissioning",
        "required_owner_confirmations":["interlock_off","no_enabled_scene"],
        "confirmation_prompt_sha256":"a"*64,"text_sha256":"a"*64,
        "accepted_owner_confirmation_binding":{"prompt_sha256":"a"*64,
            "facts":{"interlock_off":True,"no_enabled_scene":True}}}]
    captured=[]
    def followup(context,now=None):
        captured.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"specialist_accepted","answer":"Ready","provider_control_calls":0,
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,contextual_specialist_dispatcher=followup)
    assert status==200 and captured[0]["owner_confirmed_requested_setup"] is True
    assert captured[0]["owner_confirmation_facts"]=={"interlock_off":True,"no_enabled_scene":True}
    assert value["response_contract_version"]=="contextual_specialist_response_v2"


def test_confirmation_waiting_delivery_reload_then_ch2_presence_retains_original_binding():
    rows={};mission="FERTILIZER-1";prompt_sha="a"*64
    initial={"event_id":mission+"-DELIVERED","mission_id":mission,"card_mission_id":mission,
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "state":"delivered","task_state":"waiting_for_input","telegram_message_id":"3480",
        "delivery_provider_timestamp":NOW.isoformat(),"text_sha256":prompt_sha,
        "contextual_task_kind":"fertilizer_commissioning",
        "required_owner_confirmations":["interlock_off","no_enabled_scene"],
        "confirmation_prompt_sha256":prompt_sha}
    rows[initial["event_id"]]=initial
    def store(action,identity,payload):
        if action=="load":return list(rows.values())
        created=identity not in rows
        if created:rows[identity]=dict(payload)
        return {"success":True,"created":created}
    waiting={"success":True,"status":"waiting_for_input","answer":"CH2 still reads OFF",
        "required_owner_confirmations":["interlock_off","no_enabled_scene"],
        "confirmation_prompt_sha256":prompt_sha,
        "accepted_owner_confirmation_binding":{"prompt_sha256":prompt_sha,
            "facts":{"interlock_off":True,"no_enabled_scene":True}}}
    delivered=deliver_family_result({**operational("Done"),"provider_message_id":"500"},waiting,
        specialist="ROOTLINE",mission_id=mission,card_mission_id=mission,event_store=store,
        editor=lambda *_:{"success":True,"telegram_message_id":"3480"})
    assert delivered["telegram_edits"]==1
    projected=_project_pending_history(list(rows.values()),NOW+timedelta(minutes=1))
    assert projected["text_sha256"]!=projected["confirmation_prompt_sha256"]
    item={**operational("CH2 inching is now on at 300 seconds and I’m back at the fertilizer valves ready for the test."),
        "provider_message_id":"3486","provider_timestamp":(NOW+timedelta(minutes=1)).isoformat(),
        "semantic":{"domain":"rootline","intent":"fertilizer_commissioning","message_kind":"observation",
            "continuation":True,"language":"en","needs_clarification":False}}
    captured=[]
    def followup(context,now=None):
        captured.append(context)
        return {"success":True,"contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"specialist_accepted","answer":"Ready","provider_control_calls":0,
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW+timedelta(minutes=1),pending_specialist_loader=lambda _:[projected],
        contextual_specialist_dispatcher=followup)
    assert status==200 and captured[0]["owner_confirmed_requested_setup"] is True
    assert value["hardware_commands"]==0 and value["writes_farm_data"] is False


def test_visible_notification_receipt_does_not_replace_active_waiting_lifecycle():
    prompt_sha="a"*64; answer_sha="b"*64
    history=[{"event_id":"MISSION-DELIVERED","state":"delivered",
        "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
        "telegram_message_id":"3480","delivery_provider_timestamp":(NOW-timedelta(minutes=4)).isoformat(),
        "contextual_task_kind":"fertilizer_commissioning","text_sha256":prompt_sha},
        {"event_id":"MISSION-UPDATE-X-DELIVERED","state":"updated",
         "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
         "telegram_message_id":"3480","contextual_task_kind":"fertilizer_commissioning",
         "text_sha256":answer_sha,"accepted_owner_confirmation_binding":{
             "prompt_sha256":prompt_sha,"facts":{"interlock_off":True,"no_enabled_scene":True}}},
        {"event_id":"MISSION-VISIBLE-WAIT-X-DELIVERED","state":"notification_delivered",
         "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
         "telegram_message_id":"3480","notification_message_id":"3489",
         "delivery_provider_timestamp":(NOW-timedelta(minutes=1)).isoformat(),
         "text_sha256":answer_sha}]
    projected=_project_pending_history(history,NOW)
    assert projected["state"]=="updated" and projected["task_state"]=="waiting_for_input"
    assert projected["telegram_message_id"]=="3480"
    assert projected["notification_message_id"]=="3489"
    assert projected["reply_message_ids"]==["3480","3489"]
    assert projected["delivery_provider_timestamp"]==(NOW-timedelta(minutes=1)).isoformat()
    assert projected["accepted_owner_confirmation_binding"]["facts"]=={
        "interlock_off":True,"no_enabled_scene":True}


def test_scheduler_notification_cannot_consume_contextual_owner_reply():
    history=[{"event_id":"MISSION-UPDATE-X-DELIVERED","state":"updated",
        "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
        "telegram_message_id":"3480","delivery_provider_timestamp":(NOW-timedelta(minutes=2)).isoformat(),
        "contextual_task_kind":"fertilizer_commissioning","text_sha256":"a"*64},
        {"event_id":"OOM-SCHEDULE-ROOTLINE-OTHER-DELIVERED","state":"notification_delivered",
         "mission_id":"OOM-SCHEDULE-ROOTLINE-OTHER","card_mission_id":"MISSION",
         "delivery_provider_timestamp":(NOW-timedelta(minutes=1)).isoformat()}]
    projected=_project_pending_history(history,NOW)
    assert projected["mission_id"]=="MISSION"
    assert projected["contextual_task_kind"]=="fertilizer_commissioning"
    assert projected["delivery_provider_timestamp"]==(NOW-timedelta(minutes=2)).isoformat()


def test_other_mission_receipt_cannot_refresh_but_durable_active_lifecycle_survives_delay():
    history=[{"event_id":"MISSION-UPDATE-X-DELIVERED","state":"updated",
        "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
        "telegram_message_id":"3480","delivery_provider_timestamp":(NOW-timedelta(hours=7)).isoformat(),
        "contextual_task_kind":"fertilizer_commissioning","text_sha256":"a"*64},
        {"event_id":"OOM-SCHEDULE-ROOTLINE-OTHER-DELIVERED","state":"notification_delivered",
         "mission_id":"OOM-SCHEDULE-ROOTLINE-OTHER","card_mission_id":"MISSION",
         "delivery_provider_timestamp":(NOW-timedelta(minutes=1)).isoformat()}]
    projected=_project_pending_history(history,NOW)
    assert projected["mission_id"]=="MISSION"
    assert projected["delivery_provider_timestamp"]==(NOW-timedelta(hours=7)).isoformat()


def test_visible_wait_after_specialist_acceptance_restores_same_active_context_and_reply_identity():
    history=[{"event_id":"MISSION-UPDATE-READY-DELIVERED","state":"updated",
        "task_state":"specialist_accepted","mission_id":"MISSION","card_mission_id":"MISSION",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "telegram_message_id":"3480","delivery_provider_timestamp":(NOW-timedelta(hours=8)).isoformat(),
        "contextual_task_kind":"fertilizer_commissioning","text_sha256":"a"*64,
        "accepted_owner_confirmation_binding":{"prompt_sha256":"b"*64,
            "facts":{"interlock_off":True,"no_enabled_scene":True}}},
        {"event_id":"MISSION-VISIBLE-WAIT-FRESH-DELIVERED","state":"notification_delivered",
         "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
         "telegram_message_id":"3480","notification_message_id":"3497",
         "delivery_provider_timestamp":(NOW-timedelta(minutes=1)).isoformat(),
         "semantic_intent":"fertilizer_commissioning_presence"}]
    projected=_project_pending_history(history,NOW)
    assert projected["state"]=="updated" and projected["task_state"]=="waiting_for_input"
    assert projected["contextual_task_kind"]=="fertilizer_commissioning"
    assert projected["reply_message_ids"]==["3480","3497"]
    item={**operational("Ek is nou by die kunsmiskleppe"),"reply_to_message_id":"3497",
        "semantic":{"domain":"rootline","intent":"availability_confirmation",
            "message_kind":"confirmation","continuation":True,"language":"af"}}
    captured=[]
    def followup(context,now=None):
        captured.append(context); return {"success":True,
            "contract_version":"rootline_fertilizer_commissioning_followup_v1",
            "status":"specialist_accepted","answer":"Ready",
            "ready_for_supervised_proof":True,"next_specialist_step":"supervised_fertilizer_mixer_proof",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False},
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=lambda _:[projected],
        contextual_specialist_dispatcher=followup)
    assert status==200 and value["status"]=="specialist_accepted"
    assert captured[0]["parent_telegram_message_id"]=="3480"


def test_old_waiting_notification_cannot_resurrect_later_completed_lifecycle():
    history=[{"event_id":"MISSION-UPDATE-READY-DELIVERED","state":"updated",
        "task_state":"specialist_accepted","mission_id":"MISSION","card_mission_id":"MISSION",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "telegram_message_id":"3480","delivery_provider_timestamp":(NOW-timedelta(minutes=3)).isoformat(),
        "contextual_task_kind":"fertilizer_commissioning"},
        {"event_id":"MISSION-VISIBLE-WAIT-DELIVERED","state":"notification_delivered",
         "task_state":"waiting_for_input","mission_id":"MISSION","card_mission_id":"MISSION",
         "notification_message_id":"3497","delivery_provider_timestamp":(NOW-timedelta(minutes=2)).isoformat()},
        {"event_id":"MISSION-UPDATE-COMPLETED-DELIVERED","state":"updated",
         "task_state":"completed","mission_id":"MISSION","card_mission_id":"MISSION",
         "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
         "telegram_message_id":"3480","delivery_provider_timestamp":(NOW-timedelta(minutes=1)).isoformat(),
         "contextual_task_kind":"fertilizer_commissioning"}]
    projected=_project_pending_history(history,NOW)
    assert projected["task_state"]=="completed"
    assert "notification_message_id" not in projected


def test_invalid_dispatch_result_is_terminal_and_replay_does_not_dispatch_again():
    item={**operational("Done; at fertilizer valves now"),"semantic":{
        "domain":"rootline","intent":"commissioning_ready","message_kind":"confirmation",
        "continuation":True,"language":"en","needs_clarification":False}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42","specialist_identity":"ROOTLINE",
        "task_state":"waiting_for_input","telegram_message_id":"3480",
        "delivery_provider_timestamp":NOW.isoformat(),
        "contextual_task_kind":"fertilizer_commissioning"}]
    calls=[]
    def invalid(*args,**kwargs): calls.append(1); return {}
    authority=issue_gateway_owner_authority("42","42")
    first,first_status=handle_operational_specialist_message(item,authority,now=NOW,
        pending_specialist_loader=pending,contextual_specialist_dispatcher=invalid)
    second,second_status=handle_operational_specialist_message(item,authority,now=NOW,
        pending_specialist_loader=pending,contextual_specialist_dispatcher=invalid)
    assert first_status==503 and second_status==200 and len(calls)==1
    assert second["replay_suppressed"] is True and second["hardware_commands"]==0


def test_exact_provider_replay_loads_terminal_before_routing():
    item=operational("Done; at fertilizer valves now")
    text_sha=__import__("hashlib").sha256(item["text"].encode()).hexdigest()
    row={"state":"contextual_followup_completed","context":{
        "owner_user_id":"42","chat_id":"42","provider_message_id":item["provider_message_id"],
        "provider_timestamp":item["provider_timestamp"],"text_sha256":text_sha},
        "outcome":{"status":"waiting_for_input","answer":"CH2 remains off",
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False,
            "response_contract_version":"contextual_specialist_response_v2",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False}}}
    value=recover_contextual_specialist_replay(item,replay_loader=lambda _:[row],
        delivery_loader=lambda _:True)
    assert value["replay_suppressed"] is True and value["suppress_owner_delivery"] is True
    assert value["hardware_commands"]==0


def test_one_exact_v2_terminal_supersedes_preserved_v1_history():
    item=operational("Done; at fertilizer valves now")
    text_sha=__import__("hashlib").sha256(item["text"].encode()).hexdigest()
    context={"owner_user_id":"42","chat_id":"42",
        "provider_message_id":item["provider_message_id"],
        "provider_timestamp":item["provider_timestamp"],"text_sha256":text_sha}
    zero={"hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False,
        "authority":{"configuration_write":False,"hardware_control":False,
                     "farm_write":False,"telegram_send":False}}
    rows=[{"state":"contextual_followup_completed","context":context,
           "outcome":{**zero,"status":"waiting_for_input"}},
          {"state":"contextual_followup_completed","context":context,
           "outcome":{**zero,"status":"waiting_for_input","answer":"Are you still there?",
             "response_contract_version":"contextual_specialist_response_v2"}}]
    value=recover_contextual_specialist_replay(item,replay_loader=lambda _:rows,
        delivery_loader=lambda _:False)
    assert value["delivery_recovery_required"] is True
    assert value["answer"]=="Are you still there?"


def test_exact_provider_outcome_without_delivery_resumes_delivery_not_specialist():
    item=operational("Done; at fertilizer valves now")
    text_sha=__import__("hashlib").sha256(item["text"].encode()).hexdigest()
    row={"state":"contextual_followup_completed","context":{
        "owner_user_id":"42","chat_id":"42","provider_message_id":item["provider_message_id"],
        "provider_timestamp":item["provider_timestamp"],"text_sha256":text_sha},
        "outcome":{"status":"waiting_for_input","answer":"Are you still there?",
            "mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
            "provider_message_id":item["provider_message_id"],"requires_visible_notification":True,
            "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False,
            "response_contract_version":"contextual_specialist_response_v2",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False}}}
    value=recover_contextual_specialist_replay(item,replay_loader=lambda _:[row],
        delivery_loader=lambda _:False)
    assert value["delivery_recovery_required"] is True
    assert value["replay_suppressed"] is False
    assert value["suppress_owner_delivery"] is False
    assert value["answer"]=="Are you still there?" and value["hardware_commands"]==0


def test_provider_delivery_lookup_failure_does_not_claim_suppression():
    item=operational("Done; at fertilizer valves now")
    text_sha=__import__("hashlib").sha256(item["text"].encode()).hexdigest()
    row={"state":"contextual_followup_completed","context":{
        "owner_user_id":"42","chat_id":"42","provider_message_id":item["provider_message_id"],
        "provider_timestamp":item["provider_timestamp"],"text_sha256":text_sha},
        "outcome":{"hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False,
            "response_contract_version":"contextual_specialist_response_v2",
            "authority":{"configuration_write":False,"hardware_control":False,
                         "farm_write":False,"telegram_send":False}}}
    def unavailable(_): raise RuntimeError("database unavailable")
    value=recover_contextual_specialist_replay(item,replay_loader=lambda _:[row],
        delivery_loader=unavailable)
    assert value["status"]=="contextual_specialist_delivery_receipt_lookup_unavailable"
    assert value["replay_suppressed"] is True and value["suppress_owner_delivery"] is True
    assert value["delivery_recovery_required"] is False and value["hardware_commands"]==0


def test_changed_provider_replay_binding_is_not_recovered():
    item=operational("Different text")
    row={"state":"contextual_followup_completed","context":{
        "owner_user_id":"42","chat_id":"42","provider_message_id":item["provider_message_id"],
        "provider_timestamp":item["provider_timestamp"],"text_sha256":"0"*64},
        "outcome":{"hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}}
    value=recover_contextual_specialist_replay(item,replay_loader=lambda _:[row])
    assert value["status"]=="contextual_specialist_provider_replay_binding_conflict"
    assert value["suppress_owner_delivery"] is True and value["hardware_commands"]==0


def test_provider_replay_ledger_failure_is_delivery_suppressed():
    item=operational("Done; at fertilizer valves now")
    def unavailable(_): raise RuntimeError("database unavailable")
    assert recover_contextual_specialist_replay(item,replay_loader=unavailable) is None


@pytest.mark.parametrize("parent_at", [None, NOW+timedelta(seconds=1), NOW-timedelta(days=31)])
def test_invalid_parent_provider_chronology_fails_closed(parent_at):
    item={**operational("Done; at fertilizer valves now"),"semantic":{
        "domain":"rootline","intent":"status_update","message_kind":"confirmation",
        "continuation":True,"needs_clarification":False}}
    pending=lambda _:[{"mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "owner_user_id":"42","chat_id":"42",
        "specialist_identity":"ROOTLINE","task_state":"waiting_for_input",
        "telegram_message_id":"3480",
        "delivery_provider_timestamp":parent_at.isoformat() if parent_at else None,
        "contextual_task_kind":"fertilizer_commissioning"}]
    value,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,pending_specialist_loader=pending,
        contextual_specialist_dispatcher=lambda *_:pytest.fail("invalid chronology must not dispatch"))
    assert status==409 and value["status"]=="contained"
    assert value["systemic_exception"]=="pending_specialist_chronology_invalid"


def test_recoverable_zero_write_containment_advances_same_mission_once():
    item={**operational("Storage tanks and Reservoir is full"),"semantic":{"domain":"rootline",
        "intent":"water_levels_observed","message_kind":"observation","observation":"Both are full.",
        "observation_facts":[{"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}],
        "needs_clarification":False}}
    mission=operational_specialist_intake._mission(item)
    old_context={"contract_version":"oom_rootline_operational_dispatch_v1","mission_id":mission,
        "owner_user_id":"42","chat_id":"42","provider_message_id":"3213","provider_timestamp":NOW.isoformat(),
        "observations":[],"visible_irrigation_need_zone":None,"semantic_observation":"True",
        "semantic_intent":"rootline_reassessment","content_sha256":__import__("hashlib").sha256(item["text"].encode()).hexdigest(),
        "authority":{"farm_observation_write":False,"hardware_control":False,"telegram_send":False,"automatic_on_retry":False}}
    events={mission+"-DISPATCH":{"event_id":mission+"-DISPATCH","mission_id":mission,"state":"claimed","context":old_context},
        mission+"-COMPLETED":{"event_id":mission+"-COMPLETED","mission_id":mission,"state":"completed","context":old_context,
            "outcome":{"systemic_exception":"rootline_canonical_observation_bridge_failed","writes_farm_data":False,
                       "result_digest":"a"*64}}}
    def store(action, identity, payload):
        if action=="load": return list(events.values())
        if identity in events:return {"success":True,"created":False}
        events[identity]=dict(payload);return {"success":True,"created":True}
    writer=lambda *_:{"success":True,"contract_version":"rootline_owner_observation_bridge_v1","status":"recorded",
        "canonical_writes":2,"observation_ids":["S","R"],"observation_generation":"G","readback":[]}
    first,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _:operational_result(recommendation="Hold"),
        rootline_observation_writer=writer,operation_store=store)
    replay_item={**item,"semantic":{**item["semantic"],"observation":"Both water stores report full.",
                                    "intent":"owner_water_observation"}}
    second,_=handle_operational_specialist_message(replay_item,issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _:pytest.fail("completed replay must not redispatch"),
        rootline_observation_writer=lambda *_:pytest.fail("completed replay must not rewrite"),operation_store=store)
    assert status==200 and first["mission_id"]==mission and first["writes_farm_data"] is True
    assert first["material_recomposition_authority"]["prior_result_digest"]=="a"*64
    assert second["replay_suppressed"] is True

def test_same_provider_strict_superset_recovers_only_previously_omitted_storage():
    item=operational("Reservoir is 4/4 and Storage is 4/4.")
    mission=operational_specialist_intake._mission(item)
    content=__import__("hashlib").sha256(item["text"].encode()).hexdigest()
    reservoir={"kind":"reservoir_level","value":"4/4","numerator":4,"denominator":4,
        "provider_message_id":"3213","observed_at":NOW.isoformat()}
    old_context={"contract_version":"oom_rootline_operational_dispatch_v1","mission_id":mission,
        "owner_user_id":"42","chat_id":"42","provider_message_id":"3213","provider_timestamp":NOW.isoformat(),
        "observations":[reservoir],"visible_irrigation_need_zone":None,"semantic_observation":"",
        "semantic_intent":"","content_sha256":content,
        "authority":{"farm_observation_write":False,"hardware_control":False,"telegram_send":False,
                     "automatic_on_retry":False}}
    old_outcome={"success":True,"status":"specialist_accepted","hardware_commands":0,
        "protected_actions_performed":False,"sends_telegram":False,"writes_farm_data":True,
        "result_digest":"b"*64,"canonical_observation":{"success":True,
            "readback":[{"kind":"reservoir","fraction":[4,4]}]}}
    events={"old-claim":{"event_id":"old-claim","mission_id":mission,"state":"claimed","context":old_context},
        "old-complete":{"event_id":"old-complete","mission_id":mission,"state":"completed",
                        "context":old_context,"outcome":old_outcome}}
    def store(action, identity, payload):
        if action=="load": return list(events.values())
        if identity in events:return {"success":True,"created":False}
        events[identity]=dict(payload);return {"success":True,"created":True}
    def writer(context, _authority):
        assert [(row["kind"],row["value"]) for row in context["observations"]]==[
            ("storage_level","4/4")]
        return {"success":True,"contract_version":"rootline_owner_observation_bridge_v1",
            "status":"recorded","created":True,"canonical_writes":1,
            "observation_ids":["ROOTLINE-TANK-STORAGE"],
            "observation_generation":"G","readback":[{"kind":"storage","fraction":[4,4]}]}
    result,status=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_observation_writer=writer,operation_store=store,
        rootline_operations_dispatcher=lambda _:operational_result(recommendation="Reassess"))
    assert status==200 and result["writes_farm_data"] is True
    assert result["material_recomposition_authority"]["from_systemic_exception"]==(
        "rootline_partial_observation_omission")
    assert len([row for row in events.values() if row["state"]=="completed"])==2
    assert operational_specialist_intake._missing_observation_readback_valid(
        {"observations":[{"kind":"storage_level","numerator":4,"denominator":4}]},
        {"readback":[]}) is False

def test_unavailable_operational_adapter_is_visible_and_never_falls_to_v1():
    value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=None)
    assert status==503 and value["handled"] is True
    assert value["systemic_exception"]=="rootline_operational_adapter_unavailable"
    assert "irrigation sheet" not in value["answer"].lower()
    assert value["hardware_commands"]==0

def test_unavailable_adapter_terminal_outcome_replays_without_redispatch():
    first,_=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=None)
    second,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _:pytest.fail("must not redispatch"))
    assert first["systemic_exception"]=="rootline_operational_adapter_unavailable"
    assert status==200 and second["replay_suppressed"] is True

def test_claim_and_terminal_persistence_exceptions_are_visible_zero_authority():
    def claim_fails(action, identity, payload):
        if action=="load": return []
        raise RuntimeError("db down")
    value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _:operational_result(),operation_store=claim_fails)
    assert status==503 and value["systemic_exception"]=="rootline_operational_result_persistence_failed"
    assert value["hardware_commands"]==0 and "recovery identity" in value["answer"]

    events=[]
    def terminal_fails(action, identity, payload):
        if action=="load": return []
        if payload["state"]=="claimed": events.append(payload); return {"success":True,"created":True}
        raise RuntimeError("completion down")
    value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=None,operation_store=terminal_fails)
    assert status==503 and value["systemic_exception"]=="rootline_operational_result_persistence_failed"
    assert len(events)==1 and value["hardware_commands"]==0

def test_concurrent_claim_conflict_has_clean_owner_copy():
    def conflict(action, identity, payload):
        return [] if action=="load" else {"success":True,"created":False}
    value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _:operational_result(),operation_store=conflict)
    assert status==202 and value["systemic_exception"]=="rootline_operational_dispatch_claim_conflict"
    assert "â" not in value["answer"] and "ï" not in value["answer"]

def test_operational_replay_identity_and_partial_rootline_result_are_deterministic():
    calls=[]
    dispatcher=lambda context:(calls.append(context) or operational_result(recommendation="Needs Data",unavailable=("forecast",)))
    first,_=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=dispatcher)
    second,_=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=dispatcher)
    assert first["mission_id"]==second["mission_id"] and first["result_digest"]==second["result_digest"]
    assert first["specialist_result"]["unavailable"]==("forecast",)
    assert first["hardware_commands"]==0 and first["writes_farm_data"] is False
    assert len(calls)==1 and second["replay_suppressed"] is True
    changed=operational("Reservoir 3/4 and storage tanks 2/4")
    conflict,status=handle_operational_specialist_message(changed,issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=dispatcher)
    assert status==409 and conflict["systemic_exception"]=="rootline_operational_replay_binding_conflict"
    assert len(calls)==1

def test_3213_canonical_observation_write_and_dispatch_are_exactly_once(monkeypatch):
    writes=[];dispatches=[]
    monkeypatch.setattr(operational_specialist_intake,"persist_rootline_observations",
        lambda context,authority:(writes.append((context["mission_id"],authority.provider_message_id)) or
            {"success":True,"contract_version":"rootline_owner_observation_bridge_v1",
             "status":"recorded","created":True,"canonical_writes":1,"observation_ids":["ROOTLINE-TANK-3213"]}))
    dispatcher=lambda context:(dispatches.append(context["mission_id"]) or operational_result())
    first,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=dispatcher)
    replay,replay_status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=dispatcher)
    assert status==200 and first["writes_farm_data"] is True
    assert replay_status==200 and replay["replay_suppressed"] is True
    assert len(writes)==1 and len(dispatches)==1

def test_committed_observation_truth_survives_invalid_dispatch_and_completion_failure(monkeypatch,operation_store):
    committed={"success":True,"contract_version":"rootline_owner_observation_bridge_v1",
        "status":"recorded","created":True,"canonical_writes":1,"observation_ids":["ROOTLINE-TANK-3213"]}
    monkeypatch.setattr(operational_specialist_intake,"persist_rootline_observations",lambda *_:committed)
    invalid,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _:{} )
    assert status==503 and invalid["writes_farm_data"] is True
    operation_store.clear()
    def completion_fails(action,identity,payload):
        if action=="load": return []
        if payload["state"]=="claimed": return {"success":True,"created":True}
        raise RuntimeError("completion unavailable")
    failed,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _:operational_result(),operation_store=completion_fails)
    assert status==503 and failed["writes_farm_data"] is True
    assert failed["canonical_observation_ids"]==["ROOTLINE-TANK-3213"]

def test_malformed_successful_writer_result_is_unknown_not_false(monkeypatch):
    monkeypatch.setattr(operational_specialist_intake,"persist_rootline_observations",lambda *_:{
        "success":True,"contract_version":"rootline_owner_observation_bridge_v1","status":"recorded"})
    value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda _:pytest.fail("must not dispatch"))
    assert status==503 and value["writes_farm_data"] is None
    assert value["writes_farm_data_unknown"] is True

def test_operational_authority_is_request_bound_and_escalation_fails_closed(operation_store):
    denied,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("99","99"),
        now=NOW,rootline_operations_dispatcher=lambda _:operational_result())
    assert status==409 and denied["systemic_exception"]=="operational_specialist_auth_or_chronology_invalid"
    for field in ("telegram_send","hardware_control","farm_observation_write","automatic_on_retry"):
        operation_store.clear()
        item=operational_result(); item["authority"]={**item["authority"],field:True}
        value,status=handle_operational_specialist_message(operational(),issue_gateway_owner_authority("42","42"),
            now=NOW,rootline_operations_dispatcher=lambda _,x=item:x)
        assert status==503 and value["hardware_commands"]==0

def test_negated_c_need_is_not_execution_intent():
    calls=[]
    value,status=handle_operational_specialist_message(
        operational("Reservoir 4/4. C camps do not need irrigation."),issue_gateway_owner_authority("42","42"),
        now=NOW,rootline_operations_dispatcher=lambda context:(calls.append(context) or operational_result()))
    assert status==200 and value["visible_irrigation_need_zone"] is None
    assert calls[0]["visible_irrigation_need_zone"] is None

@patch("modules.oom_sakkie.rootline_operational_adapter.build_current_rootline_specialist_result")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_exact_3213_gateway_path_never_reaches_legacy_sheet(owner_task,deliver,loader):
    owner_task.return_value=({"handled":False},200)
    loader.return_value={"success":True,"contract_version":"rootline_specialist_result_v1",
        "result_id":"ROOT-3213","generation":"GEN-3213",
        "recommendations":[{"subject":"C12345","status":"Needs Data"}],"evidence":{},
        "next_reassessment":{"trigger":"fresh_power_and_channel_state"}}
    deliver.return_value={"success":True,"status":"family_message_delivered","telegram_sends":1,"telegram_edits":0}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":3213,"date":1785774127,
        "text":"Reservoir 4/4 and the storage tanks are 2/4. C camps do need irrigation now.",
        "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    with patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",return_value=None):
        value,status=handle_telegram_gateway_message(payload,headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200 and value["message"]["specialist_identity"]=="ROOTLINE"
    assert value["message"].get("tool_used")!="irrigation_status"
    assert "irrigation sheet" not in value["answer"].lower()
    assert "ð" not in value["answer"]

@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_visible_containment_is_transport_success_not_silent_backend_failure(owner_task, operational, deliver):
    owner_task.return_value=({"handled":False},200)
    operational.return_value=({"handled":True,"success":False,"status":"contained",
        "answer":"Visible technical exception","specialist_identity":"ROOTLINE",
        "mission_id":"ROOT-1","card_mission_id":"ROOT-1"},503)
    deliver.return_value={"success":True,"status":"family_message_delivered","telegram_sends":1,"telegram_edits":0}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":3181,"date":1785684198,"text":TEXT,
             "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    with patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",return_value=None):
        value,status=handle_telegram_gateway_message(payload,headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200 and value["success"] is True
    assert value["message"]["success"] is False and value["delivery"]["success"] is True
    assert value["reply_transport"]=="backend_handles_owner_task_delivery"

@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_gateway_preserves_indeterminate_write_truth(owner_task,operational,deliver):
    owner_task.return_value=({"handled":False},200)
    operational.return_value=({"handled":True,"success":False,"status":"contained",
        "answer":"Visible exception","specialist_identity":"ROOTLINE","mission_id":"ROOT-1",
        "card_mission_id":"ROOT-1","writes_farm_data":None,"writes_farm_data_unknown":True},503)
    deliver.return_value={"success":True,"status":"family_message_delivered","telegram_sends":1,"telegram_edits":0}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
         "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":3213,"date":1785774127,"text":"Storage tanks 2/4",
        "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    with patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",return_value=None):
        value,status=handle_telegram_gateway_message(payload,headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200 and value["writes"] is None and value["writes_unknown"] is True
