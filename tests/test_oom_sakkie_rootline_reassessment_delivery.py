from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger

ENV={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"true",
     "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
     "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
HEADERS={"X-Oom-Sakkie-Telegram-Token":"x"*40}

def current(status="Hold"):
    return {"success":True,"overall_status":"Plan ready","result_id":"R1","generation":"G1",
        "current_power":{"battery_soc_pct":50},"battery_policy":{"governing_reserve_soc_pct":63},
        "recommendations":[{"subject":"C12345","status":status,"reason":"Fresh evidence supports this C Camp decision."}],
        "owner_brief":{"family_fact_needed":"","reassess":"At 10:00 or when material evidence changes."}}

def memory_store():
    rows={}
    def store(action,identity,payload):
        if action=="record_observation":
            if identity in rows:return {"success":True,"created":False}
            rows[identity]=payload;return {"success":True,"created":True}
        if action=="load_delivered":
            found=[v for v in rows.values() if v.get("delivery_state")=="delivered" and f'{v["owner_user_id"]}|{v["chat_id"]}'==identity]
            return found[-1] if found else None
        if action=="load_identity": return rows.get(identity)
        if action=="claim_pending":
            if identity in rows:return {"success":True,"created":False}
            rows[identity]=payload;return {"success":True,"created":True}
        if action in {"mark_delivered","mark_ambiguous"}:
            rows[identity]={**rows[identity],**payload};return {"success":True,"created":True}
    return rows,store

def payload():
    return {"owner_user_id":"42","chat_id":"42","trigger":"declared_time",
            "trigger_id":"ROOTLINE-20260804-1000","trigger_timestamp":"2026-08-04T10:00:00+02:00"}

def test_changed_reassessment_uses_family_rail_then_replay_is_zero_send():
    rows,store=memory_store(); calls=[]
    def deliver(parsed,result,**kwargs):
        calls.append((parsed,result,kwargs)); return {"success":True,"status":"family_message_delivered",
            "telegram_message_id":"8001","telegram_sends":1,"telegram_edits":0}
    first,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=lambda:current("Run later"),state_store=store,family_delivery=deliver)
    replay,replay_status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=lambda:current("Run later"),state_store=store,family_delivery=deliver)
    assert status==200 and first["telegram_sends"]==1 and first["delivery_record"]["success"] is True
    assert replay_status==200 and replay["notify_owner"] is False and replay["telegram_sends"]==0
    assert len(calls)==1 and first["hardware_commands"]==0 and first["writes_farm_data"] is False

def test_ambiguous_delivery_is_contained_and_never_blind_retried():
    rows,store=memory_store(); calls=[]
    def ambiguous(*args,**kwargs):
        calls.append(1);return {"success":False,"status":"family_message_delivery_ambiguous","telegram_sends":0}
    first,status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=current,state_store=store,family_delivery=ambiguous)
    replay,replay_status=handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,
        specialist_loader=current,state_store=store,family_delivery=ambiguous)
    assert status==202 and replay_status==202 and replay["status"]=="rootline_reassessment_delivery_ambiguous"
    assert len(calls)==1 and replay["telegram_sends"]==0

def test_reassessment_denies_unbound_owner_and_unsafe_authority():
    _,status=handle_rootline_reassessment_trigger({**payload(),"chat_id":"99"},HEADERS,ENV,
        specialist_loader=current,state_store=memory_store()[1])
    assert status==403
