from datetime import datetime,timezone

from modules.oom_sakkie.documents_green_request_runtime import handle_documents_green_request
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result, localize_recipient_result

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

def test_genuine_natural_request_directly_authorizes_one_bounded_job():
    calls=[]
    def authorize(preview,revision,parsed):
        calls.append((preview,revision,parsed));return {"job_id":preview["job_id"]}
    result,status=handle_documents_green_request(PARSED,environ=ENV,pig_loader=pigs,
        standing_authorizer=authorize,now=NOW)
    assert status==200 and result["status"]=="documents_green_print_authorized"
    assert result["action_kind"]=="documents_green_print"
    assert result["action_kind"]=="documents_green_print"
    assert result["canonical_job_created"] is True and result["printer_calls"]==0
    assert result["reply_markup"]=={"inline_keyboard":[]}
    assert "confirm" not in result["answer"].lower()
    assert len(calls)==1
    preview=calls[0][0]
    assert preview["farm_scope_id"]=="AMADEUS-FARM" and preview["green_id"]=="GREEN-HA-1"
    assert preview["retrieval_url"].startswith("https://amadeus.internal/api/documents/")

def test_request_replay_identity_is_stable_for_same_canonical_day():
    calls=[];authorize=lambda p,r,x:(calls.append(p) or {"job_id":p["job_id"]})
    for _ in range(2):handle_documents_green_request(PARSED,environ=ENV,pig_loader=pigs,
        standing_authorizer=authorize,now=NOW)
    assert calls[0]==calls[1]

def test_farm_day_uses_johannesburg_and_recovers_new_provider_identity():
    calls=[];authorize=lambda p,r,x:(calls.append(p) or {"job_id":p["job_id"]})
    handle_documents_green_request({**PARSED,"provider_message_id":"MSG-2"},environ=ENV,
        pig_loader=pigs,standing_authorizer=authorize,
        now=datetime(2026,8,20,22,30,tzinfo=timezone.utc))
    assert calls[0]["sheet_date"]=="2026-08-21"
    assert calls[0]["authorization_expires_at"]=="2026-08-21T22:00:00+00:00"

def test_unauthorized_or_uncommissioned_request_has_zero_claim_and_print_effects():
    calls=[];create=lambda **kwargs:calls.append(kwargs)
    bad={**PARSED,"telegram_chat_id":"GROUP","telegram_chat_type":"group"}
    for parsed,env in ((bad,ENV),(PARSED,{**ENV,"DOCUMENTS_GREEN_ID":""})):
        result,status=handle_documents_green_request(parsed,environ=env,pig_loader=pigs,
            standing_authorizer=lambda p,r,x:calls.append(p),now=NOW)
        assert status>=400 and result["canonical_job_created"] is False
        assert result["printer_calls"]==0
    assert calls==[]

def test_unrelated_natural_message_is_not_captured():
    result,status=handle_documents_green_request({**PARSED,"text":"What needs attention?",
        "semantic":{"domain":"manager_round","intent":"daily_brief"}},
        environ=ENV,pig_loader=pigs,now=NOW)
    assert status==200 and result["handled"] is False

def test_ambiguous_semantic_result_asks_once_without_creating_claim():
    calls=[]
    result,status=handle_documents_green_request({**PARSED,
        "semantic":{"domain":"documents","intent":"weekly_weighing_sheet_print",
            "needs_clarification":True,
            "clarification_question":"Do you want the weekly weighing sheet printed?"}},
        environ=ENV,pig_loader=pigs,standing_authorizer=lambda p,r,x:calls.append(p),now=NOW)
    assert status==200 and result["status"]=="documents_green_request_clarification_required"
    assert result["canonical_job_created"] is False and result["printer_calls"]==0
    assert result["answer"]=="Do you want the weekly weighing sheet printed?"
    assert calls==[]


def test_actual_unbound_clarification_is_afrikaans_and_cannot_leak_english():
    parsed={**PARSED,"output_language":"af","semantic":{
        "domain":"documents","intent":"weekly_weighing_sheet_print",
        "needs_clarification":True,
        "clarification_question":"Do you want the weekly weighing sheet printed?"}}
    result,status=handle_documents_green_request(parsed,environ=ENV,pig_loader=pigs,now=NOW)
    localized=localize_recipient_result(parsed,result,"DOCUMENTS")
    assert status==200 and localized["answer"] == (
        "Wil jy hê ek moet die weeklikse weegblad vir drukwerk voorberei?")
    assert "Do you" not in localized["answer"]


def test_authorized_result_is_not_sent_through_protected_preview_delivery():
    result,status=handle_documents_green_request(PARSED,environ=ENV,pig_loader=pigs,
        standing_authorizer=lambda p,r,x:{"job_id":p["job_id"]},now=NOW)
    assert status==200 and result["reply_markup"]=={"inline_keyboard":[]}

def test_ambiguous_semantic_result_asks_once_without_creating_claim():
    calls=[]
    result,status=handle_documents_green_request({**PARSED,
        "semantic":{"domain":"documents","intent":"weekly_weighing_sheet_print",
            "needs_clarification":True,
            "clarification_question":"Do you want the weekly weighing sheet printed?"}},
        environ=ENV,pig_loader=pigs,standing_authorizer=lambda p,r,x:calls.append(p),now=NOW)
    assert status==200 and result["status"]=="documents_green_request_clarification_required"
    assert result["canonical_job_created"] is False and result["printer_calls"]==0
    assert result["answer"]=="Do you want the weekly weighing sheet printed?"
    assert calls==[]
