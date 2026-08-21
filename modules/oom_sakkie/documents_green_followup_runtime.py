"""Durable manager-cycle ownership of Green print physical acceptance."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import os

from modules.oom_sakkie.protected_action_claims import build_buttons, create_claim

ACTION_KIND = "documents_green_physical_acceptance"
MISSION_ID = "DMQ-20260816-01:PHYSICAL"


def recover_documents_green_physical_follow_up(*, owner_user_id, chat_id, trigger_id,
        now=None, environ=None, loader=None, claim_creator=create_claim):
    if not owner_user_id or owner_user_id != chat_id:
        return _hold("documents_physical_follow_up_owner_binding_invalid")
    source = environ if environ is not None else os.environ
    farm = str(source.get("DOCUMENTS_FARM_SCOPE_ID") or "").strip()
    if not farm:
        return {"success": True, "status": "documents_physical_follow_up_not_configured",
            "handled": False, "telegram_sends": 0, "printer_calls": 0}
    try:
        if loader is None:
            from modules.documents.green_print_api import load_pending_physical_follow_up
            loader = lambda: load_pending_physical_follow_up(
                farm_scope_id=farm, authenticated_principal_id=owner_user_id)
        job = loader()
        if not job:
            return {"success": True, "status": "no_pending_documents_physical_follow_up",
                "handled": False, "telegram_sends": 0, "printer_calls": 0}
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        evidence = "GREEN-PAGE-" + hashlib.sha256((str(job["job_id"]) + ":" +
            str(job["document_version"])).encode()).hexdigest()[:24].upper()
        preview = {"contract_version": "documents_green_physical_acceptance_v1",
            "job_id": job["job_id"], "document_version": job["document_version"],
            "pdf_sha256": job["pdf_sha256"], "cups_job_id": job["cups_job_id"],
            "provider_id": job["provider_id"], "evidence_id": evidence}
        claim = claim_creator(action_kind=ACTION_KIND, owner_user_id=owner_user_id,
            private_chat_id=chat_id, mission_id=MISSION_ID + ":" + str(job["job_id"]),
            provider_message_id="scheduled:" + str(trigger_id),
            evidence_generation=str(job["pdf_sha256"]), preview_payload=preview,
            expires_at=(current + timedelta(days=7)).isoformat(),
            reuse_active_provider_identity=True)
    except Exception as exc:
        return {**_hold("documents_physical_follow_up_recovery_pending"),
            "error_type": type(exc).__name__}
    return {"handled": True, "success": True,
        "status": "documents_physical_acceptance_ready", "specialist": "DOCUMENTS",
        "mission_id": MISSION_ID, "card_mission_id": MISSION_ID + ":" + str(job["job_id"]),
        "callback_token": claim["callback_token"], "preview_digest": claim.get("preview_digest"),
        "answer": ("The printer reports that the weekly weighing sheet completed. "
            "Please confirm only after checking that the physical page is correct. "
            "If it is not correct, choose Change so the exception remains owned."),
        "reply_markup": build_buttons(claim["callback_token"]), "printer_calls": 0,
        "automatic_reprint": False, "recovery_required": False}


def _hold(status):
    return {"handled": True, "success": False, "status": status,
        "telegram_sends": 0, "printer_calls": 0, "automatic_reprint": False,
        "recovery_required": True}
