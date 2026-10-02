from modules.oom_sakkie.grouped_weight_runtime import handle_grouped_weight_message
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
import pytest

def test_english_and_afrikaans_natural_groups_share_preview_boundary():
    readiness=lambda:{"success":True,"pigs":[
        {"pig_id":"PIG-11","tag_number":"11","status":"Active","on_farm":"Yes"},
        {"pig_id":"PIG-MONA","tag_number":"Mona","status":"Active","on_farm":"Yes"}]}
    preflight=lambda payload:({"success":True,"accepted_count":2,"accepted_rows":payload["rows"]},200)
    claim=lambda **kwargs:{"success":True,"callback_token":"abc123","preview_digest":"d"*64}
    for text,language in (("Pig 11 47.2 kg, Mona 118 kg.","en"),("Vark 11 47,2 kg; Mona 118 kg.","af")):
        parsed={"text":text,"telegram_user_id":"42","telegram_chat_id":"42","provider_message_id":"5001",
            "provider_timestamp":"2026-08-04T06:30:00+00:00",
            "semantic":{"domain":"herd_management","language":language}}
        result,status=handle_grouped_weight_message(parsed,issue_gateway_owner_authority("42","42"),
            readiness_loader=readiness,preflight=preflight,pen_loader=lambda:[],claim_creator=claim)
        assert status==200 and result["status"]=="grouped_weight_preview_ready"
        assert result["confirmation_required"] is True and result["writes_weights"] is False
        assert len(result["mappings"])==2
        assert result["reply_markup"]["inline_keyboard"][0][0]["text"]=="Bevestig alles"

def test_exact_compound_message_previews_all_four_shared_date_and_pen():
    names={"Bonnie":"PIG-2026-5376","Waki":"PIG-2026-7531","Zigay":"PIG-2026-EEAC","Teena":"PIG-2026-74FF"}
    readiness=lambda:{"success":True,"pigs":[{"pig_id":pid,"tag_number":name,"status":"Active","on_farm":"Yes","current_pen_id":"PEN-OLD"} for name,pid in names.items()]}
    captured={}
    def preflight(payload):captured.update(payload);return {"success":True,"accepted_count":4,"accepted_rows":payload["rows"]},200
    parsed={"text":"Weight added for these Sows:\nBonnie - 64.4 kg\nWaki - 70.0 kg\nZigay - 71.4 kg\nTeena - 69.2 kg\n\nPlease log these weights for today 2026-08-11, and they all moved to Pen: D3.",
      "telegram_user_id":"42","telegram_chat_id":"42","provider_message_id":"3519","provider_timestamp":"2026-08-11T14:39:39+00:00","semantic":{"domain":"herd_management","language":"en"}}
    result,status=handle_grouped_weight_message(parsed,issue_gateway_owner_authority("42","42"),readiness_loader=readiness,
      preflight=preflight,pen_loader=lambda:[{"pen_id":"PEN-017","pen_name":"D3"}],
      claim_creator=lambda **kwargs:{"callback_token":"opaque123","preview_digest":"e"*64})
    assert status==200 and len(result["mappings"])==4
    assert result["weight_date"]=="2026-08-11"
    assert {row["moved_to_pen_id"] for row in captured["rows"]}=={"PEN-017"}
    assert all(name in result["answer"] for name in names)
    assert "D3" in result["answer"] and "11 August 2026" in result["answer"]


@pytest.mark.parametrize('label',['','Mona'])
def test_visible_identity_failure_is_contained_before_any_claim(label):
    readiness={'success':True,'pigs':[{'pig_id':pid,'name':pid,'tag_number':label,'status':'Active','on_farm':'Yes'}
        for pid in ('PIG-1','PIG-2')]}
    parsed={'text':'PIG-1 47.2 kg, PIG-2 118 kg.','telegram_user_id':'42','telegram_chat_id':'42',
        'provider_message_id':'5001','provider_timestamp':'2026-10-01T12:00:00+00:00',
        'semantic':{'domain':'herd_management','language':'en'}}
    result,status=handle_grouped_weight_message(parsed,issue_gateway_owner_authority('42','42'),
        readiness_loader=lambda:readiness,pen_loader=lambda:[],
        preflight=lambda payload:({'success':True,'accepted_count':2,'accepted_rows':payload['rows']},200),
        claim_creator=lambda **_:pytest.fail('ambiguous visible identity created a claim'))
    assert status==200 and result['status']=='weight_visible_identity_required'
    assert result['question_count']==1 and 'visible name or tag' in result['clarification_question']
    assert result['writes_weights'] is False and result['protected_actions_performed'] is False


def test_configured_af_recipient_keeps_full_typed_weights_from_english_input():
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_oom_sakkie_family_message_lifecycle import Memory,PARSED
    parsed={**PARSED,'text':'Mona 47.2 kg, Linda 118 kg.','output_language':'af',
        'provider_timestamp':'2026-10-01T12:00:00+00:00','semantic':{'domain':'herd_management','language':'en'}}
    readiness={'success':True,'pigs':[{'pig_id':pid,'tag_number':tag,'status':'Active','on_farm':'Yes'}
        for pid,tag in [('PIG-A','Mona'),('PIG-B','Linda')]]}
    result,status=handle_grouped_weight_message(parsed,issue_gateway_owner_authority('42','42'),
        readiness_loader=lambda:readiness,pen_loader=lambda:[],
        preflight=lambda payload:({'success':True,'accepted_count':2,'accepted_rows':payload['rows']},200),
        claim_creator=lambda **kw:{'callback_token':'T','preview_digest':'d'*64})
    assert status==200 and result['recipient_language']=='af'
    memory=Memory()
    delivered=deliver_family_result(parsed,result,specialist='HERDMASTER',event_store=memory.store,
        sender=memory.send,protected_delivery=lambda **kw:kw['deliver']())
    assert delivered['telegram_sends']==1
    text=memory.sent[0][1]
    assert all(value in text for value in ['Mona','Linda','47.2 kg','118 kg','Gewigte'])
    assert 'PIG-' not in text and len(result['mappings'])==2
