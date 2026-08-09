from datetime import datetime, timedelta, timezone

from modules.oom_sakkie.rootline_fertilizer_commissioning_adapter import assess_fertilizer_commissioning_reply

NOW=datetime(2026,8,9,11,1,tzinfo=timezone.utc)

def context(at=NOW):
    return {"contract_version":"oom_sakkie_contextual_specialist_followup_v2",
        "mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id":"OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "specialist_identity":"ROOTLINE","parent_telegram_message_id":"3480",
        "contextual_task_kind":"fertilizer_commissioning",
        "owner_confirmed_requested_setup":True,"language":"en",
        "required_owner_confirmations":["interlock_off","no_enabled_scene"],
        "owner_confirmation_facts":{"interlock_off":True,"no_enabled_scene":True},
        "confirmation_prompt_sha256":"a"*64,
        "provider_timestamp":at.isoformat(),
        "authority":{"readback":True,"configuration_write":False,
                     "hardware_control":False,"telegram_send":False}}

def snapshot(ch2=True, interlock=False, scenes=False):
    return {"authoritative":True,"device_id":"100204d497","timers_enabled":False,
        "interlock_enabled":interlock,"scenes_enabled":scenes,
        "provider_interlock_supported":True,"provider_scenes_supported":True,
        "provider_control_calls":0,"channels":[
            {"channel":1,"native_auto_off_enabled":True,"native_auto_off_seconds":120,
             "output_state":"OFF","power_restoration_state":"OFF"},
            {"channel":2,"native_auto_off_enabled":ch2,"native_auto_off_seconds":300,
             "output_state":"OFF","power_restoration_state":"OFF"},
            {"channel":3,"output_state":"OFF","power_restoration_state":"OFF"},
            {"channel":4,"output_state":"OFF","power_restoration_state":"OFF"}]}

def test_current_ch2_off_is_precise_read_only_conflict():
    value=assess_fertilizer_commissioning_reply(context(),now=NOW,
        readback_loader=lambda:snapshot(ch2=False))
    assert value["status"]=="waiting_for_input"
    assert value["safety_conflicts"]==["CH2 Inching still reads OFF"]
    assert value["hardware_commands"]==0 and value["provider_control_calls"]==0
    assert value["mixing_enabled"] is False and value["injection_enabled"] is False

def test_unavailable_interlock_and_scene_readback_use_retained_owner_confirmation():
    item=snapshot();item.update({"provider_interlock_supported":False,
                                 "provider_scenes_supported":False,
                                 "interlock_enabled":None,"scenes_enabled":None})
    value=assess_fertilizer_commissioning_reply(context(),now=NOW,readback_loader=lambda:item)
    assert value["configuration_verified"] is True
    assert value.get("safety_conflicts") is None

def test_presence_only_cannot_prove_unavailable_interlock_or_scene():
    item=snapshot();item.update({"provider_interlock_supported":False,
                                 "provider_scenes_supported":False,
                                 "interlock_enabled":None,"scenes_enabled":None})
    unconfirmed={**context(),"owner_confirmed_requested_setup":False}
    value=assess_fertilizer_commissioning_reply(unconfirmed,now=NOW,readback_loader=lambda:item)
    assert value["configuration_verified"] is False
    assert len(value["system_evidence_gaps"])==2 and value["hardware_commands"]==0

def test_changed_parent_digest_cannot_prove_unavailable_settings():
    item=snapshot();item.update({"provider_interlock_supported":False,
                                 "provider_scenes_supported":False,
                                 "interlock_enabled":None,"scenes_enabled":None})
    unbound={**context(),"confirmation_prompt_sha256":"short"}
    value=assess_fertilizer_commissioning_reply(unbound,now=NOW,readback_loader=lambda:item)
    assert value["configuration_verified"] is False

def test_negative_owner_confirmation_cannot_prove_unavailable_settings():
    item=snapshot();item.update({"provider_interlock_supported":False,
                                 "provider_scenes_supported":False,
                                 "interlock_enabled":None,"scenes_enabled":None})
    denied={**context(),"owner_confirmation_facts":{
        "interlock_off":False,"no_enabled_scene":False}}
    value=assess_fertilizer_commissioning_reply(denied,now=NOW,readback_loader=lambda:item)
    assert value["configuration_verified"] is False
    assert "ready_for_supervised_proof" not in value
    assert value["status"]=="waiting_for_input" and value["hardware_commands"]==0

def test_safe_but_stale_presence_asks_only_fresh_availability():
    value=assess_fertilizer_commissioning_reply(context(NOW-timedelta(minutes=6)),now=NOW,
        readback_loader=snapshot)
    assert value["status"]=="waiting_for_input" and "still at the fertilizer valves" in value["answer"]
    assert value["configuration_verified"] is True and value["hardware_commands"]==0
    assert value["question_count"]==1 and value["requires_visible_notification"] is True
    assert "five-minute mixer test" in value["answer"]

def test_safe_fresh_context_is_ready_but_never_actuates():
    value=assess_fertilizer_commissioning_reply(context(),now=NOW,readback_loader=snapshot)
    assert value["status"]=="specialist_accepted" and value["ready_for_supervised_proof"] is True
    assert value["hardware_commands"]==0 and value["authority"]["hardware_control"] is False

def test_safe_fresh_afrikaans_context_is_localized_and_never_actuates():
    value=assess_fertilizer_commissioning_reply({**context(),"language":"af"},now=NOW,
        readback_loader=snapshot)
    assert value["status"]=="specialist_accepted" and "KUNSMISKONTROLE — GEREED" in value["answer"]
    assert value["hardware_commands"]==0

def test_afrikaans_conflict_response_keeps_same_safety_boundary():
    item={**context(),"language":"af"}
    value=assess_fertilizer_commissioning_reply(item,now=NOW,
        readback_loader=lambda:snapshot(ch2=False))
    assert "Jou volgende stap" in value["answer"] and "Skakel CH2 Inching aan vir 300 sekondes" in value["answer"]
    assert value["hardware_commands"]==0
