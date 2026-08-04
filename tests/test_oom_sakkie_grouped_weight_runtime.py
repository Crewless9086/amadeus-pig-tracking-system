from modules.oom_sakkie.grouped_weight_runtime import handle_grouped_weight_message
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

def test_english_and_afrikaans_natural_groups_share_preview_boundary():
    readiness=lambda:{"success":True,"pigs":[
        {"pig_id":"PIG-11","tag_number":"11","status":"Active","on_farm":"Yes"},
        {"pig_id":"PIG-MONA","tag_number":"Mona","status":"Active","on_farm":"Yes"}]}
    preflight=lambda payload:({"success":True,"accepted_count":2,"accepted_rows":payload["rows"]},200)
    for text,language in (("Pig 11 47.2 kg, Mona 118 kg.","en"),("Vark 11 47,2 kg; Mona 118 kg.","af")):
        parsed={"text":text,"telegram_user_id":"42","telegram_chat_id":"42","provider_message_id":"5001",
            "provider_timestamp":"2026-08-04T06:30:00+00:00",
            "semantic":{"domain":"herd_management","language":language}}
        result,status=handle_grouped_weight_message(parsed,issue_gateway_owner_authority("42","42"),
            readiness_loader=readiness,preflight=preflight)
        assert status==200 and result["status"]=="grouped_weight_preview_ready"
        assert result["confirmation_required"] is True and result["writes_weights"] is False
        assert len(result["mappings"])==2
