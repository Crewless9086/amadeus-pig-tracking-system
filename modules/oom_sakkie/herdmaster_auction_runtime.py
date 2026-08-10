"""Protected BKB auction confirmation through Oom Sakkie's existing family rail."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from typing import Any, Mapping

from modules.oom_sakkie.family_message_lifecycle import deliver_family_result, load_family_lifecycle
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.pig_weights.herdmaster_auction_sale_recording import record_confirmed_auction_sale

MISSION_ID = "OOM-HERDMASTER-AUCTION-6D376FB82AE7277526D8958313BE1CFD"
OPERATION_ID = "HERD-AUCTION-6D376FB82AE7277526D8958313BE1CFD"
PREVIEW_HASH = "AUCT-PREVIEW-42DF5FAD754515C3A91E98E010CFA1F4"
EVIDENCE_GENERATION = "production-read-2026-08-10"
CONFIRMATION_TOKEN = "CONFIRM " + PREVIEW_HASH
INVOICE_SHA256 = "65f39574a84bc13ca35b441f981b0f0d1501f430313c1714bb228f5b10bbdea6"
PIGS = (
    ("84", "PIG-2026-B0BB"), ("51", "PIG-2026-04A0"),
    ("92", "PIG-2026-DB07"), ("93", "PIG-2026-B656"),
    ("94", "PIG-2026-AC81"), ("95", "PIG-2026-862A"),
    ("97", "PIG-2026-7CFC"), ("99", "PIG-2026-81B7"),
    ("100", "PIG-2026-592A"), ("101", "PIG-2026-E46E"),
    ("113", "PIG-2026-9097"), ("116", "PIG-2026-6577"),
    ("120", "PIG-2026-CEF3"), ("121", "PIG-2026-535A"),
    ("122", "PIG-2026-5C5C"), ("66", "PIG-2026-DF24"),
    ("68", "PIG-2026-88DE"), ("74", "PIG-2026-1DC8"),
)
TOKEN_PATTERN = re.compile(r"^CONFIRM AUCT-PREVIEW-[A-F0-9]{32}$")


def frozen_preview_result() -> dict[str, Any]:
    mappings = ", ".join(f"{tag} / {pig_id}" for tag, pig_id in PIGS)
    answer = (
        "<b>HERDMASTER — CONFIRM BKB AUCTION SALE</b>\n\n"
        "<b>Sale</b>\n• BKB Riversdal, 5 August 2026\n• Invoice S-EE02-2710\n"
        f"• 18 pigs: {mappings}\n\n"
        "<b>Proposed recording</b>\n• One completed Livestock/Auction sale\n"
        "• All 18 pigs Sold and off-farm, with 18 linked items and 18 immutable exits\n"
        "• Historical records remain unchanged\n\n"
        "<b>Settlement</b>\n"
        "• Gross excl. VAT R4,180.00; VAT R627.00; gross incl. VAT R4,807.00\n"
        "• Commission excl. VAT R292.60; commission VAT R43.89; total R336.49\n"
        "• Other deductions R0.00; EFT payable R4,470.51\n"
        "• Payment received, individual pig prices and V10/V11 membership: Unknown\n\n"
        "Nothing will be recorded unless you send this exact confirmation:\n"
        f"<code>{CONFIRMATION_TOKEN}</code>"
    )
    return {"handled": True, "success": True, "status": "waiting_for_confirmation",
        "answer": answer, "mission_id": MISSION_ID, "card_mission_id": MISSION_ID,
        "operation_id": OPERATION_ID, "preview_hash": PREVIEW_HASH,
        "evidence_generation": EVIDENCE_GENERATION,
        "confirmation_token": CONFIRMATION_TOKEN, "question_count": 1,
        "requires_visible_notification": True, "writes_farm_data": False,
        "protected_actions_performed": False}


def present_frozen_preview(gateway_authority, *, trigger_timestamp: str,
                           family_delivery=deliver_family_result):
    """Present the owner-directed frozen preview once through the family rail."""
    if not validates_gateway_owner_authority(gateway_authority) or not trigger_timestamp:
        return {"success": False, "status": "auction_preview_authority_required",
                "telegram_sends": 0, "telegram_edits": 0}
    parsed = {"telegram_user_id": gateway_authority.owner_user_id,
        "telegram_chat_id": gateway_authority.private_chat_id,
        "telegram_chat_type": "private",
        "provider_message_id": "owner-directed-auction-preview:" + PREVIEW_HASH,
        "provider_timestamp": trigger_timestamp,
        "text": "Present frozen protected auction preview " + PREVIEW_HASH}
    return family_delivery(parsed, frozen_preview_result(), specialist="HERDMASTER",
        mission_id=MISSION_ID, card_mission_id=MISSION_ID)


def handle_auction_confirmation(parsed: Mapping[str, Any], gateway_authority, *,
                                event_store=None, evidence_loader=None,
                                writer=record_confirmed_auction_sale):
    text = str((parsed or {}).get("text") or "").strip()
    if not TOKEN_PATTERN.fullmatch(text):
        return {"handled": False, "status": "auction_confirmation_not_applicable"}, 200
    if not validates_gateway_owner_authority(gateway_authority):
        return {"handled": True, "success": False,
            "status": "auction_confirmation_authority_denied", "answer": "",
            "writes_farm_data": False}, 403
    provider_message_id = str(parsed.get("provider_message_id") or "").strip()
    provider_timestamp = str(parsed.get("provider_timestamp") or "").strip()
    text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not provider_message_id or not provider_timestamp:
        return {"handled": True, "success": False,
            "status": "auction_confirmation_provider_identity_required", "answer": "",
            "writes_farm_data": False}, 409
    events = load_family_lifecycle(MISSION_ID, event_store=event_store)
    completed = next((row for row in reversed(events)
        if row.get("confirmation_provider_message_id") == provider_message_id
        and row.get("confirmation_provider_timestamp") == provider_timestamp
        and row.get("confirmation_text_sha256") == text_digest
        and row.get("task_state") == "completed"
        and row.get("state") in {"delivered", "updated", "notification_delivered"}), None)
    if completed:
        if (str(completed.get("owner_user_id") or "") != str(parsed.get("telegram_user_id") or "")
                or str(completed.get("chat_id") or "") != str(parsed.get("telegram_chat_id") or "")):
            return {"handled": True, "success": False,
                "status": "auction_confirmation_owner_binding_conflict", "answer": "",
                "writes_farm_data": False}, 403
        return {"handled": True, "success": True,
            "status": "auction_confirmation_replayed_zero_effect", "answer": "",
            "mission_id": MISSION_ID, "card_mission_id": MISSION_ID,
            "suppress_owner_delivery": True, "writes_farm_data": False}, 200
    ambiguous_completion = next((row for row in reversed(events)
        if row.get("confirmation_provider_message_id") == provider_message_id
        and row.get("confirmation_provider_timestamp") == provider_timestamp
        and row.get("confirmation_text_sha256") == text_digest
        and row.get("owner_user_id") == str(parsed.get("telegram_user_id") or "")
        and row.get("chat_id") == str(parsed.get("telegram_chat_id") or "")
        and row.get("task_state") == "completed"
        and row.get("state") in {"update_attempted", "contained"}), None)
    if ambiguous_completion:
        return {"handled": True, "success": True,
            "status": "auction_completion_delivery_ambiguous", "answer": "",
            "mission_id": MISSION_ID,
            "card_mission_id": MISSION_ID, "operation_id": OPERATION_ID,
            "preview_hash": PREVIEW_HASH, "evidence_generation": EVIDENCE_GENERATION,
            "confirmation_provider_message_id": provider_message_id,
            "confirmation_provider_timestamp": provider_timestamp,
            "confirmation_text_sha256": text_digest,
            "suppress_owner_delivery": True, "delivery_recovery_required": False,
            "writes_farm_data": False, "protected_actions_performed": False}, 200
    latest = next((row for row in reversed(events)
        if str(row.get("task_state") or "").strip()), None)
    active = latest if (latest
        and latest.get("task_state") == "waiting_for_confirmation"
        and latest.get("state") in {"delivered", "updated", "notification_delivered"}
        and latest.get("preview_hash") == text.removeprefix("CONFIRM ")
        and latest.get("operation_id") == OPERATION_ID
        and latest.get("evidence_generation") == EVIDENCE_GENERATION) else None
    if not active:
        return {"handled": True, "success": False,
            "status": "auction_confirmation_active_preview_required",
            "answer": ("⚠️ <b>HERDMASTER CONFIRMATION CONTAINED</b>\n\n"
                       "I could not bind this confirmation to the current protected auction preview. Nothing was recorded."),
            "writes_farm_data": False}, 409
    if (str(active.get("owner_user_id") or "") != str(parsed.get("telegram_user_id") or "")
            or str(active.get("chat_id") or "") != str(parsed.get("telegram_chat_id") or "")):
        return {"handled": True, "success": False,
            "status": "auction_confirmation_owner_binding_conflict", "answer": "",
            "writes_farm_data": False}, 403
    if not _strictly_after(provider_timestamp,
                           str(active.get("delivery_provider_timestamp") or "")):
        return {"handled": True, "success": False,
            "status": "auction_confirmation_chronology_conflict",
            "answer": ("⚠️ <b>HERDMASTER CONFIRMATION CONTAINED</b>\n\n"
                       "This confirmation does not follow the current protected preview. Nothing was recorded."),
            "writes_farm_data": False}, 409
    authority = {"principal_type": "service", "principal_id": "oom_sakkie",
        "actor_reference": str(parsed.get("telegram_user_id") or "")}
    confirmation = {"owner_confirmed": True,
        "confirmation_id": "TG-AUCT-" + hashlib.sha256(
            f"{provider_message_id}|{provider_timestamp}|{text}".encode()).hexdigest()[:24].upper(),
        "operation_id": OPERATION_ID, "preview_hash": PREVIEW_HASH,
        "evidence_generation": EVIDENCE_GENERATION,
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "private_chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": provider_message_id,
        "provider_timestamp": provider_timestamp,
        "confirmation_text_sha256": text_digest}
    loader = evidence_loader or load_current_auction_evidence
    result, status = writer(_report(), loader, confirmation, authority=authority,
        authority_verifier=lambda candidate: candidate == authority
            and validates_gateway_owner_authority(gateway_authority))
    if result.get("success") is not True:
        return {"handled": True, "success": False,
            "status": str(result.get("status") or "auction_confirmation_contained"),
            "answer": ("⚠️ <b>HERDMASTER AUCTION CONTAINED</b>\n\n"
                       "The current farm evidence no longer matches the confirmed preview. Nothing was recorded."),
            "mission_id": MISSION_ID, "card_mission_id": MISSION_ID,
            "writes_farm_data": False, "recording_result": result}, status
    answer = _completion_answer()
    return {"handled": True, "success": True, "status": "completed",
        "answer": answer, "mission_id": MISSION_ID, "card_mission_id": MISSION_ID,
        "operation_id": OPERATION_ID, "preview_hash": PREVIEW_HASH,
        "evidence_generation": EVIDENCE_GENERATION,
        "confirmation_provider_message_id": provider_message_id,
        "confirmation_provider_timestamp": provider_timestamp,
        "confirmation_text_sha256": text_digest,
        "owner_visible_completion_policy": "verified_edit_or_new_message",
        "writes_farm_data": not result.get("replay"),
        "rows_created": int(result.get("rows_created") or 0),
        "recording_result": result, "protected_actions_performed": not result.get("replay")}, status


def load_current_auction_evidence():
    import psycopg
    ids = [pig_id for _, pig_id in PIGS]
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select p.pig_id,p.tag_number,p.status,p.on_farm,p.purpose,
              coalesce(pen.pen_name,''),p.current_weight_kg,p.last_weight_date
              from current_canonical_pig_state p left join pens pen on pen.pen_id=p.current_pen_id
              where p.pig_id=any(%s)""", (ids,))
            rows = cursor.fetchall()
            cursor.execute("""select distinct m.pig_id from pig_medical_events m
              where m.pig_id=any(%s) and m.treatment_date<='2026-08-05'::date
                and (m.withdrawal_end_date is null or m.withdrawal_end_date>='2026-08-05'::date)""", (ids,))
            withdrawals = {str(row[0]) for row in cursor.fetchall()}
            cursor.execute("""select distinct i.pig_id from sales_transaction_items i
              join sales_transactions s using(sale_id)
              where i.pig_id=any(%s) and s.sale_status<>'Cancelled'""", (ids,))
            sold = {str(row[0]) for row in cursor.fetchall()}
            cursor.execute("select distinct pig_id from pig_active_outlets where pig_id=any(%s) and active", (ids,))
            outlets = {str(row[0]) for row in cursor.fetchall()}
    pigs = []
    for row in rows:
        pid = str(row[0])
        pigs.append({"pig_id": pid, "tag_number": str(row[1]), "status": str(row[2]),
            "on_farm": row[3] is True, "purpose": str(row[4]), "current_pen_name": str(row[5]),
            "latest_weight_kg": str(row[6] or ""), "latest_weight_date": str(row[7] or ""),
            "availability_state": "available" if pid not in outlets else "reserved",
            "reservation_order_state": "none" if pid not in outlets else "reserved",
            "active_reservation": pid in outlets, "active_order": pid in outlets,
            "prior_sale": pid in sold, "prior_sale_state": "active_sale" if pid in sold else "none",
            "withdrawal_state": "explicitly_cleared" if pid not in withdrawals else "active"})
    return {"evidence_generation": EVIDENCE_GENERATION, "pigs": pigs}


def _report():
    return {"tags": [tag for tag, _ in PIGS],
        "invoice_evidence": {"evidence_id": "PRIVATE-BKB-SETTLEMENT-S-EE02-2710",
                             "sha256": INVOICE_SHA256}}


def _completion_answer():
    return ("✅ <b>BKB AUCTION RECORDED</b>\n\n"
            "One completed auction sale was recorded for the confirmed 18 pigs. "
            "They are Sold and off-farm; their history remains preserved. "
            "The EFT payable is R4,470.51. Payment received, individual prices and V10/V11 membership remain Unknown.")


def _strictly_after(candidate: str, baseline: str) -> bool:
    try:
        left = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        right = datetime.fromisoformat(baseline.replace("Z", "+00:00"))
        return left > right
    except (AttributeError, TypeError, ValueError):
        return False
