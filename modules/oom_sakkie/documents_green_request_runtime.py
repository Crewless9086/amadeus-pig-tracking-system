"""Bounded Oom Sakkie intake for the fixed weekly weighing-sheet pilot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from zoneinfo import ZoneInfo

from modules.documents.weekly_weight_sheet import (
    PRINT_ACTION_KIND, build_weekly_sheet_revision, protected_print_preview,
)
from modules.oom_sakkie.protected_action_claims import build_buttons, create_claim

MISSION_ID = "DMQ-20260816-01"
OPERATING_TZ = ZoneInfo("Africa/Johannesburg")


def handle_documents_green_request(parsed, *, environ=None, pig_loader=None,
                                   claim_creator=create_claim, now=None):
    """Create one exact protected preview from a genuine private owner request."""
    semantic=parsed.get("semantic") if isinstance(parsed.get("semantic"),dict) else {}
    if (semantic.get("domain")!="documents"
            or semantic.get("intent")!="weekly_weighing_sheet_print"):
        return {"handled":False,"status":"documents_green_request_not_applicable"},200
    if semantic.get("needs_clarification") is True:
        question=str(semantic.get("clarification_question") or "").strip()
        afrikaans=str(parsed.get("output_language") or semantic.get("language") or "").casefold().startswith("af")
        return {"handled":True,"success":False,
            "status":"documents_green_request_clarification_required",
            "specialist":"DOCUMENTS","mission_id":MISSION_ID,
            "answer":question or ("Wil jy hê ek moet die weeklikse weegblad vir drukwerk voorberei?"
                if afrikaans else "Do you want me to prepare the weekly weighing sheet for printing?"),
            "canonical_job_created":False,"printer_calls":0,
            "writes_farm_data":False},200
    owner=str(parsed.get("telegram_user_id") or "")
    chat=str(parsed.get("telegram_chat_id") or "")
    if not owner or owner!=chat or parsed.get("telegram_chat_type")!="private":
        return _hold("documents_green_owner_private_required"),403
    source=environ if environ is not None else os.environ
    required={key:str(source.get(env) or "").strip() for key,env in {
        "farm_scope_id":"DOCUMENTS_FARM_SCOPE_ID","green_id":"DOCUMENTS_GREEN_ID",
        "printer_id":"DOCUMENTS_PRINTER_ID","cups_queue_id":"DOCUMENTS_CUPS_QUEUE_ID",
        "registry_version":"DOCUMENTS_REGISTRY_VERSION",
        "canonical_api_origin":"DOCUMENTS_CANONICAL_API_ORIGIN"}.items()}
    if any(not value for value in required.values()):
        return _hold("documents_green_commissioning_incomplete"),503
    observed=(now or datetime.now(timezone.utc)).astimezone(OPERATING_TZ)
    try:
        rows=(pig_loader or _active_pigs)()
        canonical=[{"pig_id":row.get("pig_id"),"tag_number":row.get("tag_number"),
            "pen_id":row.get("current_pen_id")} for row in rows]
        revision=build_weekly_sheet_revision(authenticated_principal_id=owner,
            requester="oom_sakkie",sheet_date=observed.date(),rows=canonical)
        # Stable until the farm's Johannesburg midnight: replay/concurrent delivery of the same
        # weekly revision retains one preview digest and one canonical job.
        expires=(datetime.combine(observed.date()+timedelta(days=1),
            datetime.min.time(),tzinfo=OPERATING_TZ).astimezone(timezone.utc))
        job_id="GREEN-WWS-"+revision.version_id
        path=(f"/api/documents/{revision.document_id}/versions/"
              f"{revision.version_id}/pdf")
        preview=protected_print_preview(revision=revision,job_id=job_id,
            retrieval_url=required["canonical_api_origin"].rstrip("/")+path,
            authorization_expires_at=expires,**{
                key:required[key] for key in ("farm_scope_id","green_id","printer_id",
                    "cups_queue_id","registry_version")})
        claim=claim_creator(action_kind=PRINT_ACTION_KIND,owner_user_id=owner,
            private_chat_id=chat,mission_id=MISSION_ID+":"+revision.version_id,
            provider_message_id=str(parsed.get("provider_message_id") or ""),
            evidence_generation=revision.canonical_input_sha256,
            preview_payload=preview,expires_at=expires.isoformat(),
            reuse_active_provider_identity=True)
    except Exception as exc:
        return {**_hold("documents_green_preview_contained"),
            "error_type":type(exc).__name__},503
    return {"handled":True,"success":True,"status":"documents_green_preview_ready",
        "specialist":"DOCUMENTS","mission_id":MISSION_ID,
        "card_mission_id":MISSION_ID+":"+revision.version_id,
        "callback_token":claim["callback_token"],"preview_digest":preview["preview_digest"],
        "action_kind":PRINT_ACTION_KIND,
        "document_preview":{"effective_date":revision.sheet_date.isoformat(),
            "row_count":len(revision.canonical_rows),"printer_id":required["printer_id"],
            "copies":1,"paper":"A4","colour":"monochrome"},
        "answer":("Print the weekly weighing sheet?\n\n"
            f"Date: {revision.sheet_date.isoformat()}\nPigs: {len(revision.canonical_rows)}\n"
            "Printer: Green private printer\nCopies: 1, A4, monochrome\n\n"
            "Nothing will print until you confirm."),
        "reply_markup":build_buttons(claim["callback_token"]),
        "canonical_job_created":False,"printer_calls":0,"writes_farm_data":False},200


def _active_pigs():
    from modules.pig_weights.farm_supabase_read_service import get_active_pigs
    return get_active_pigs()


def _hold(status):
    return {"handled":True,"success":False,"status":status,"canonical_job_created":False,
        "printer_calls":0,"writes_farm_data":False,
        "answer":"The weekly print request is safely held. Nothing was printed."}
