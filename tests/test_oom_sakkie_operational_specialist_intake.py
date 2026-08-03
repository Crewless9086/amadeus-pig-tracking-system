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

def test_one_water_level_routes_independently_without_demanding_both():
    value,status=handle_operational_specialist_message(operational("Storage tanks 2/4"),
        issue_gateway_owner_authority("42","42"),now=NOW,
        rootline_operations_dispatcher=lambda _context:operational_result(recommendation="Needs Data"))
    assert status==200 and len(value["observations"])==1
    assert value["observations"][0]["kind"]=="storage_level"

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
