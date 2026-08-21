from datetime import datetime, timezone
from modules.oom_sakkie.documents_green_followup_runtime import recover_documents_green_physical_follow_up

JOB={"job_id":"JOB-1","document_version":"VER-1","pdf_sha256":"a"*64,
    "cups_job_id":"CUPS-1","provider_id":"ipps://printer/ipp/print"}

def test_provider_completion_creates_recoverable_physical_claim_without_printing():
    calls=[]
    result=recover_documents_green_physical_follow_up(owner_user_id="owner",chat_id="owner",
        trigger_id="T-1",now=datetime(2026,8,21,8,tzinfo=timezone.utc),
        environ={"DOCUMENTS_FARM_SCOPE_ID":"farm"},loader=lambda:JOB,
        claim_creator=lambda **kw:(calls.append(kw) or {"callback_token":"TOKEN","preview_digest":"d"}))
    assert result["status"]=="documents_physical_acceptance_ready"
    assert result["printer_calls"]==0 and result["automatic_reprint"] is False
    assert calls[0]["reuse_active_provider_identity"] is True

def test_no_pending_job_is_terminal_independent_noop():
    result=recover_documents_green_physical_follow_up(owner_user_id="owner",chat_id="owner",
        trigger_id="T-2",environ={"DOCUMENTS_FARM_SCOPE_ID":"farm"},loader=lambda:None)
    assert result["handled"] is False and result["telegram_sends"]==0
