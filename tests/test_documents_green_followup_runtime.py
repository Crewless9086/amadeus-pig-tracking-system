from datetime import datetime, timezone
from modules.oom_sakkie.documents_green_followup_runtime import recover_documents_green_physical_follow_up
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result

JOB={"job_id":"JOB-1","document_version":"VER-1","pdf_sha256":"a"*64,
    "cups_job_id":"CUPS-1","provider_id":"ipps://printer/ipp/print"}

def test_provider_completion_creates_recoverable_physical_claim_without_printing():
    calls=[]
    result=recover_documents_green_physical_follow_up(owner_user_id="owner",chat_id="owner",
        trigger_id="T-1",now=datetime(2026,8,21,8,tzinfo=timezone.utc),
        environ={"DOCUMENTS_FARM_SCOPE_ID":"farm"},loader=lambda:JOB,
        claim_creator=lambda **kw:(calls.append(kw) or {"callback_token":"TOKEN","preview_digest":"d"}))
    assert result["status"]=="documents_physical_acceptance_ready"
    assert result["action_kind"]=="documents_green_physical_acceptance"
    buttons=result["reply_markup"]["inline_keyboard"][0]
    assert [button["text"] for button in buttons]==[
        "Page correct","Page incorrect","Not sure"]
    assert result["action_kind"]=="documents_green_physical_acceptance"
    buttons=result["reply_markup"]["inline_keyboard"][0]
    assert [button["text"] for button in buttons]==[
        "Page correct","Page incorrect","Not sure"]
    assert result["printer_calls"]==0 and result["automatic_reprint"] is False
    assert calls[0]["reuse_active_provider_identity"] is True

def test_no_pending_job_is_terminal_independent_noop():
    result=recover_documents_green_physical_follow_up(owner_user_id="owner",chat_id="owner",
        trigger_id="T-2",environ={"DOCUMENTS_FARM_SCOPE_ID":"farm"},loader=lambda:None)
    assert result["handled"] is False and result["telegram_sends"]==0


def test_physical_presenter_enters_exact_protected_delivery_binding():
    result=recover_documents_green_physical_follow_up(owner_user_id="owner",chat_id="owner",
        trigger_id="T-3",environ={"DOCUMENTS_FARM_SCOPE_ID":"farm"},loader=lambda:JOB,
        claim_creator=lambda **kw:{"callback_token":"TOKEN","preview_digest":"d"})
    captured=[]
    delivery=deliver_family_result({"telegram_user_id":"owner","telegram_chat_id":"owner"},
        result,specialist="DOCUMENTS",mission_id=result["mission_id"],
        card_mission_id=result["card_mission_id"],
        protected_delivery=lambda **kw:(captured.append(kw) or {
            "success":True,"status":"protected_delivery_replayed_noop",
            "telegram_sends":0,"telegram_edits":0}))
    assert delivery["success"] is True
    assert captured[0]["action_kind"]=="documents_green_physical_acceptance"
