from modules.oom_sakkie.grouped_weight_runtime import handle_grouped_weight_message
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

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
    assert "D3" in result["answer"] and "2026-08-11" in result["answer"]
