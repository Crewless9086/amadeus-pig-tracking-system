from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
from modules.oom_sakkie import operational_specialist_intake
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message

NOW = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)
TEXT = "I am at the B and C valve area now, can observe both camps, and can intervene immediately for supervised commissioning."

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
    second,_=handle_operational_specialist_message(item,issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _:pytest.fail("completed replay must not redispatch"),
        rootline_observation_writer=lambda *_:pytest.fail("completed replay must not rewrite"),operation_store=store)
    assert status==200 and first["mission_id"]==mission and first["writes_farm_data"] is True
    assert first["material_recomposition_authority"]["prior_result_digest"]=="a"*64
    assert second["replay_suppressed"] is True

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
    value,status=handle_telegram_gateway_message(payload,headers={"Authorization":"Bearer "+"x"*40},environ=env)
    assert status==200 and value["writes"] is None and value["writes_unknown"] is True
