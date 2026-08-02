from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message

NOW = datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)
TEXT = "I am at the B and C valve area now, can observe both camps, and can intervene immediately for supervised commissioning."

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
