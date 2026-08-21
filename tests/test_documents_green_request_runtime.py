from datetime import datetime,timezone

from modules.oom_sakkie.documents_green_request_runtime import handle_documents_green_request

NOW=datetime(2026,8,21,8,0,tzinfo=timezone.utc)
ENV={"DOCUMENTS_FARM_SCOPE_ID":"AMADEUS-FARM",
    "DOCUMENTS_GREEN_ID":"GREEN-HA-1","DOCUMENTS_PRINTER_ID":"GREEN-PRINTER-1",
    "DOCUMENTS_CUPS_QUEUE_ID":"green_private","DOCUMENTS_REGISTRY_VERSION":"REG-1",
    "DOCUMENTS_CANONICAL_API_ORIGIN":"https://amadeus.internal"}
PARSED={"text":"Please print the weekly weighing sheet",
    "telegram_user_id":"5721652188","telegram_chat_id":"5721652188",
    "telegram_chat_type":"private","provider_message_id":"MSG-1",
    "semantic":{"domain":"documents","intent":"weekly_weighing_sheet_print"}}

def pigs():return [{"pig_id":"PIG-1","tag_number":"127","current_pen_id":"B1"}]

def test_genuine_natural_request_builds_one_protected_preview_without_printing():
    calls=[]
    def create(**kwargs):
        calls.append(kwargs);return {"callback_token":"TOKEN123","status":"protected_claim_created"}
    result,status=handle_documents_green_request(PARSED,environ=ENV,pig_loader=pigs,
        claim_creator=create,now=NOW)
    assert status==200 and result["status"]=="documents_green_preview_ready"
    assert result["canonical_job_created"] is False and result["printer_calls"]==0
    assert len(calls)==1 and calls[0]["action_kind"]=="documents_green_print"
    preview=calls[0]["preview_payload"]
    assert preview["farm_scope_id"]=="AMADEUS-FARM" and preview["green_id"]=="GREEN-HA-1"
    assert preview["retrieval_url"].startswith("https://amadeus.internal/api/documents/")

def test_request_replay_identity_is_stable_for_same_canonical_day():
    calls=[];create=lambda **kwargs:(calls.append(kwargs) or {"callback_token":"TOKEN123"})
    for _ in range(2):handle_documents_green_request(PARSED,environ=ENV,pig_loader=pigs,
        claim_creator=create,now=NOW)
    assert calls[0]["mission_id"]==calls[1]["mission_id"]
    assert calls[0]["preview_payload"]==calls[1]["preview_payload"]

def test_farm_day_uses_johannesburg_and_recovers_new_provider_identity():
    calls=[];create=lambda **kwargs:(calls.append(kwargs) or {"callback_token":"TOKEN123"})
    handle_documents_green_request({**PARSED,"provider_message_id":"MSG-2"},environ=ENV,
        pig_loader=pigs,claim_creator=create,
        now=datetime(2026,8,20,22,30,tzinfo=timezone.utc))
    assert calls[0]["preview_payload"]["sheet_date"]=="2026-08-21"
    assert calls[0]["expires_at"]=="2026-08-21T22:00:00+00:00"
    assert calls[0]["reuse_active_provider_identity"] is True

def test_unauthorized_or_uncommissioned_request_has_zero_claim_and_print_effects():
    calls=[];create=lambda **kwargs:calls.append(kwargs)
    bad={**PARSED,"telegram_chat_id":"GROUP","telegram_chat_type":"group"}
    for parsed,env in ((bad,ENV),(PARSED,{**ENV,"DOCUMENTS_GREEN_ID":""})):
        result,status=handle_documents_green_request(parsed,environ=env,pig_loader=pigs,
            claim_creator=create,now=NOW)
        assert status>=400 and result["canonical_job_created"] is False
        assert result["printer_calls"]==0
    assert calls==[]

def test_unrelated_natural_message_is_not_captured():
    result,status=handle_documents_green_request({**PARSED,"text":"What needs attention?",
        "semantic":{"domain":"manager_round","intent":"daily_brief"}},
        environ=ENV,pig_loader=pigs,now=NOW)
    assert status==200 and result["handled"] is False
