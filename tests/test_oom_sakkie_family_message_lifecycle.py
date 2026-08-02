from modules.oom_sakkie.family_message_lifecycle import bind_existing_card,deliver_family_result


PARSED={"telegram_user_id":"42","telegram_chat_id":"42",
        "provider_message_id":"500","provider_timestamp":"2026-08-02T10:00:00+00:00"}
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


def test_later_natural_result_edits_same_card_and_replay_is_silent():
    memory=Memory();mission="OOM-HERD-ONE"
    deliver_family_result(PARSED,RESULT,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    follow={**RESULT,"status":"preview_ready","answer":"Preview; confirm exact operation."}
    changed=deliver_family_result({**PARSED,"provider_message_id":"501"},follow,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    replay=deliver_family_result({**PARSED,"provider_message_id":"501"},follow,specialist="HERDMASTER",mission_id=mission,card_mission_id=mission,event_store=memory.store,sender=memory.send,editor=memory.edit)
    assert changed["telegram_edits"]==1 and changed["telegram_message_id"]=="700"
    assert replay["telegram_edits"]==0 and len(memory.edited)==1


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
        telegram_message_id="3171",text_sha256="a"*64,event_store=memory.store)
    changed=deliver_family_result({**PARSED,"provider_message_id":"501"},
        {**RESULT,"answer":"Consolidated preview"},specialist="HERDMASTER",
        mission_id=mission,card_mission_id=mission,event_store=memory.store,
        sender=memory.send,editor=memory.edit)
    assert bound["telegram_sends"]==0 and memory.sent==[]
    assert changed["telegram_message_id"]=="3171" and changed["telegram_edits"]==1
