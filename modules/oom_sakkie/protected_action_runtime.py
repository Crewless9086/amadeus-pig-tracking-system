"""Precedence owner for active protected mortality and grouped-weight previews."""
from __future__ import annotations
import re
from modules.oom_sakkie.protected_action_claims import (
    CALLBACK_PREFIX, canonical_preview_digest, claim_callback, complete_claim, contain_claim, execute_grouped_weight_claim,
    resolve_natural_confirmation,
)
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority

NATURAL_CONFIRM=re.compile(r"^(?:i\s+confirm(?:\s+this)?|confirm(?:\s+all)?|yes[, ]*confirm|ek\s+bevestig(?:\s+alles)?|bevestig(?:\s+alles)?)\s*[.!]?$",re.I)

def handle_protected_action_input(parsed, gateway_authority, *, callback_data="",
                                  connect_factory=None, health_handler=None,
                                  irrigation_handler=None, documents_handler=None):
    owner=str(parsed.get("telegram_user_id") or "");chat=str(parsed.get("telegram_chat_id") or "")
    if not validates_gateway_owner_authority(gateway_authority) or not owner or owner!=chat:
        return {"handled":False,"status":"protected_action_not_applicable"},200
    data=str(callback_data or parsed.get("callback_data") or "")
    if not data:
        if not NATURAL_CONFIRM.fullmatch(str(parsed.get("text") or "").strip()):
            return {"handled":False,"status":"protected_action_not_applicable"},200
        active=resolve_natural_confirmation(owner_user_id=owner,private_chat_id=chat,
            reply_to_message_id=str(parsed.get("reply_to_message_id") or ""),connect_factory=connect_factory)
        if not active:return {"handled":False,"status":"protected_confirmation_not_unambiguous"},200
        data=f"{CALLBACK_PREFIX}{active['callback_token']}:confirm"
    try:
        claimed,status=claim_callback(data,owner_user_id=owner,private_chat_id=chat,
          provider_message_id=str(parsed.get("provider_message_id") or parsed.get("callback_query_id") or ""),
          provider_timestamp=str(parsed.get("provider_timestamp") or ""),
          source_card_message_id=str(parsed.get("reply_to_message_id") or ""),connect_factory=connect_factory)
    except Exception as exc:
        from modules.oom_sakkie.bounded_postgres_read import is_database_unavailable
        if not is_database_unavailable(exc):
            raise
        return {"handled":True,"success":False,
          "status":"protected_claim_store_degraded_hold",
          "answer":"ROOTLINE Hold: protected confirmation storage is temporarily unavailable. No controller command was issued.",
          "hardware_commands":0,"provider_control_calls":0,
          "durable_claim_truth_loaded":False,"current_segment_consumed":None,
          "segment_consumption_proven":False,"recovery_required":True},503
    if claimed.get("status")=="protected_callback_completed_delivery_retry":
        if claimed.get("action_kind")=="beacon_media_review":
            result=claimed.get("result") if isinstance(claimed.get("result"),dict) else {}
            return {"handled":True,**result,"specialist":"BEACON_MEDIA",
              "mission_id":str(result.get("mission_id") or claimed["mission_id"]),
              "card_mission_id":str(result.get("card_mission_id") or claimed["mission_id"]),
              "owner_visible_completion_policy":"verified_edit_or_new_message",
              "writes_farm_data":False,"delivery_recovery_required":True},200
        if claimed.get("action_kind")=="sam_sale_payment":
            result=claimed.get("result") if isinstance(claimed.get("result"),dict) else {}
            return {"handled":True,**result,"specialist":"SAM",
              "mission_id":claimed["mission_id"],
              "card_mission_id":str(result.get("card_mission_id") or claimed["mission_id"]),
              "reply_markup":{"inline_keyboard":[]},
              "owner_visible_completion_policy":"verified_edit_or_new_message",
              "writes_to_supabase":False},200
        if claimed.get("action_kind")=="rootline_fertilizer_mixer_commissioning":
            from modules.oom_sakkie.rootline_protected_mixer import protected_card_mission_id
            result=claimed.get("result") if isinstance(claimed.get("result"),dict) else {}
            return {"handled":True,**result,"specialist":"ROOTLINE",
              "mission_id":claimed["mission_id"],
              "card_mission_id":protected_card_mission_id(claimed["preview_digest"]),
              "reply_markup":{"inline_keyboard":[]},
              "owner_visible_completion_policy":"verified_edit_or_new_message",
              "delivery_recovery_required":True},200
        if claimed.get("action_kind")=="rootline_fertilizer_mixer_presence_refresh":
            result=claimed.get("result") if isinstance(claimed.get("result"),dict) else {}
            return {"handled":True,**result,"specialist":"ROOTLINE",
              "mission_id":claimed["mission_id"],
              "owner_visible_completion_policy":"verified_edit_or_new_message",
              "delivery_recovery_required":True},200
        from modules.oom_sakkie.rootline_protected_irrigation import protected_card_mission_id
        result=claimed.get("result") if isinstance(claimed.get("result"),dict) else {}
        answer=_irrigation_answer(result,claimed)
        return {"handled":True,**result,"answer":answer,"specialist":"ROOTLINE",
          "mission_id":claimed["mission_id"],
          "card_mission_id":protected_card_mission_id(claimed["preview_digest"],claimed["mission_id"]),
          "reply_markup":{"inline_keyboard":[]},
          "owner_visible_completion_policy":"verified_edit_or_new_message",
          "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False},200
    if status>=400 or claimed.get("status") not in {"protected_callback_claimed","protected_callback_recovered"}:
        if claimed.get("status")=="protected_preview_details" and claimed.get("action_kind")=="beacon_campaign_review":
            preview=claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"),dict) else {}
            selected=preview.get("selected_media")
            if isinstance(selected,list):
                photos="; ".join(f"{item.get('asset_id')} ({item.get('capture_date') or 'date Unknown'}, "
                    f"{item.get('source') or 'source Unknown'}, Public Use approved, "
                    f"thumbnail {item.get('thumbnail_url') or 'unavailable'})" for item in selected)
            else:
                photos=str((selected or {}).get("asset_id") or (selected or {}).get("mode") or "none")
            return {"handled":True,**claimed,"answer":(
                "<b>Campaign details</b>\n"
                f"Selected photos: {photos}\n"
                f"Attribution: {preview.get('attribution_identity') or 'Unknown'}\n"
                f"Packet/digest: {preview.get('packet_id') or ''} / {preview.get('campaign_digest') or ''}\n"
                f"Stops: {'; '.join(str(value).replace('_', ' ') for value in preview.get('stop_conditions') or [])}\n"
                "Rollback/provider chronology: publication failure is never retried automatically; "
                "boost failure stops spend; authority or evidence change pauses/stops the campaign; "
                "provider receipts remain immutable."),
                "suppress_owner_delivery":False,"writes_farm_data":False},200
        if claimed.get("status") in {"protected_preview_change_requested","protected_preview_cancelled",
                "protected_preview_media_removed"}:
            claimed["answer"]=("Send the corrected facts when ready; nothing was recorded."
                if claimed["status"]=="protected_preview_change_requested" else
                "Media removed. BEACON must issue a new exact text-only preview before approval."
                if claimed["status"]=="protected_preview_media_removed" else
                "Cancelled. Nothing was recorded.")
            if claimed.get("action_kind")=="sam_sale_payment":
                bound=claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"),dict) else {}
                claimed.update({"specialist":"SAM",
                  "card_mission_id":claimed["mission_id"]+":PAYMENT:"+str(bound.get("payment_preview_digest") or "")[:24].upper(),
                  "reply_markup":{"inline_keyboard":[]},
                  "owner_visible_completion_policy":"verified_edit_or_new_message"})
        return {"handled":True,**claimed,"writes_farm_data":False,"suppress_owner_delivery":claimed.get("status")=="protected_callback_replayed_noop"},status
    claimed["callback_token"]=data.split(":")[1]
    if claimed["action_kind"]=="documents_green_print":
        if documents_handler is None:
            from modules.documents.green_print_api import execute_claimed_weekly_print
            documents_handler=execute_claimed_weekly_print
        try:
            result=documents_handler(claimed,parsed)
        except Exception as exc:
            return {"handled":True,"success":False,
                "status":"documents_green_print_recovery_pending",
                "canonical_job_created":False,"printer_calls":0,
                "recovery_required":True,"error_type":type(exc).__name__},503
        completion=complete_claim(claimed["callback_token"],result,
            connect_factory=connect_factory)
        canonical=completion.get("result") if isinstance(completion.get("result"),dict) else result
        return {"handled":True,"success":True,
            "status":"documents_green_print_authorized",
            **canonical,"printer_calls":0,"suppress_owner_delivery":True},200
    if claimed["action_kind"]=="beacon_campaign_review":
        preview=claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"),dict) else {}
        if (preview.get("contract_version")!="beacon_campaign_owner_card_v1"
                or canonical_preview_digest("beacon_campaign_review",
                    {k:v for k,v in preview.items() if k!="campaign_digest"}) != preview.get("campaign_digest")
                or claimed.get("evidence_generation") != preview.get("campaign_digest")):
            result={"success":False,"status":"beacon_campaign_review_binding_mismatch",
                "publishes":False,"spends_money":False,"customer_sends":False}
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
            return {"handled":True,**result,"suppress_owner_delivery":True},409
        result={"success":True,"status":"beacon_campaign_review_approved",
            "packet_id":preview.get("packet_id"),"campaign_digest":preview.get("campaign_digest"),
            "answer":"Approved for BEACON execution under the exact protected envelope. Nothing was published or spent by this callback.",
            "reply_markup":{"inline_keyboard":[]},"publishes":False,"spends_money":False,
            "customer_sends":False,"writes_farm_data":False}
        completion=complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        if completion.get("replayed") is True:
            return {"handled":True,"success":True,"status":"protected_callback_replayed_noop",
                "answer":"","suppress_owner_delivery":True,"telegram_sends":0,
                "telegram_edits":0,"publishes":False,"spends_money":False,
                "customer_sends":False,"writes_farm_data":False},200
        return {"handled":True,**result},200
    if claimed["action_kind"]=="beacon_private_album_finish":
        preview=claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"),dict) else {}
        if (preview.get("contract_version")!="beacon_private_album_finish_v1"
                or str(preview.get("intake_group_id") or "")!=str(claimed.get("mission_id") or "")):
            result={"success":False,"status":"album_finish_claim_binding_mismatch",
                "telegram_sends":0,"telegram_edits":0,"writes_farm_data":False}
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
            return {"handled":True,**result,"suppress_owner_delivery":True},409
        from modules.beacon.media_intake import complete_claimed_telegram_album
        result,result_status=complete_claimed_telegram_album(preview,
            owner_user_id=owner,private_chat_id=chat)
        if result.get("success") is True:
            completed=complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
            canonical=completed.get("result") if isinstance(completed.get("result"),dict) else result
            if completed.get("replayed"):
                return {"handled":True,**canonical,"answer":"","suppress_owner_delivery":True,
                    "telegram_sends":0,"telegram_edits":0,"writes_farm_data":False},200
            context=str(canonical.get("owner_context") or "").strip() or "No additional caption was supplied."
            sheet=("available for private owner review" if canonical.get("contact_sheet_available")
                else "not yet available; the originals remain private and retained")
            answer=(f"BEACON completed this private album with {canonical['received_count']} stored photographs. "
                f"Retained context: {context} Private contact sheet: {sheet}. "
                "Next actions remain separate: Accept to Library; Approve Public Use; Review Campaign; Publish later.")
            return {"handled":True,**canonical,"answer":answer,"specialist":"BEACON_MEDIA",
                "mission_id":claimed["mission_id"],"card_mission_id":claimed["mission_id"],
                "reply_markup":{"inline_keyboard":[]},
                "owner_visible_completion_policy":"verified_edit_or_new_message",
                "writes_farm_data":False,"hardware_commands":0},result_status
        contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        return {"handled":True,**result,"writes_farm_data":False,"suppress_owner_delivery":True},result_status
    if claimed["action_kind"]=="beacon_media_review":
        from modules.oom_sakkie.beacon_media_review_runtime import execute_private_media_review
        result,result_status=execute_private_media_review(claimed,parsed)
        if result.get("success") is True:
            completed=complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
            if completed.get("replayed"):
                return {"handled":True,**(completed.get("result") or result),"answer":"",
                    "suppress_owner_delivery":True,"telegram_sends":0,"telegram_edits":0,
                    "writes_farm_data":False},200
            return {"handled":True,**result,"writes_farm_data":False},result_status
        contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        return {"handled":True,**result,"writes_farm_data":False,
            "suppress_owner_delivery":True},result_status
    if claimed["action_kind"]=="rootline_irrigation_segment":
        from modules.oom_sakkie.rootline_protected_irrigation import protected_card_mission_id
        if irrigation_handler is None:
            from modules.oom_sakkie.rootline_protected_irrigation import execute_claimed_segment
            irrigation_handler=execute_claimed_segment
        try:
            result,result_status=irrigation_handler(claimed,parsed=parsed)
        except Exception as exc:
            result={"success":False,"status":"protected_irrigation_recovery_pending",
              "hardware_commands":None,"provider_control_calls":None,
              "control_outcome":"unknown_recovery_required","recovery_required":True,
              "error_type":type(exc).__name__}
            # Keep the atomic callback claim in ``executing``. Telegram retries a
            # non-2xx callback with the same provider receipt, which
            # claim_callback recognizes as protected_callback_recovered; the
            # durable coordinator then resumes/contains any active execution.
            return {"handled":True,**result},503
        if result.get("success") is True and result.get("status") in {"segment_started","active_segment_owned"}:
            complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        elif int(result.get("hardware_commands") or 0)==0:
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        answer=_irrigation_answer(result,claimed)
        return {"handled":True,**result,"answer":answer,"specialist":"ROOTLINE",
          "mission_id":claimed["mission_id"],
          "card_mission_id":protected_card_mission_id(claimed["preview_digest"],claimed["mission_id"]),
          "reply_markup":{"inline_keyboard":[]},
          "owner_visible_completion_policy":"verified_edit_or_new_message"},result_status
    if claimed["action_kind"]=="rootline_fertilizer_mixer_presence_refresh":
        from modules.oom_sakkie.rootline_protected_mixer import execute_presence_refresh
        try:
            result,result_status=execute_presence_refresh(claimed,parsed=parsed,
                gateway_authority=gateway_authority,connect_factory=connect_factory)
        except Exception as exc:
            return {"handled":True,"success":False,
                "status":"mixer_presence_refresh_recovery_pending",
                "hardware_commands":0,"provider_control_calls":0,
                "recovery_required":True,"error_type":type(exc).__name__},503
        if result.get("success") is True:
            complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        else:
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        return {"handled":True,**result,"specialist":"ROOTLINE",
            "owner_visible_completion_policy":"verified_edit_or_new_message"},result_status
    if claimed["action_kind"]=="rootline_fertilizer_mixer_commissioning":
        from modules.oom_sakkie.rootline_protected_mixer import (
            execute_claimed_mixer, protected_card_mission_id,
        )
        try:
            result,result_status=execute_claimed_mixer(claimed,parsed=parsed)
        except Exception as exc:
            return {"handled":True,"success":False,
                "status":"mixer_protected_recovery_pending",
                "hardware_commands":None,"provider_control_calls":None,
                "recovery_required":True,"error_type":type(exc).__name__},503
        if result.get("success") is True and result.get("status") in {
                "auxiliary_started","auxiliary_active","auxiliary_claim_in_progress",
                "auxiliary_completed"}:
            complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        elif int(result.get("hardware_commands") or 0)==0:
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        return {"handled":True,**result,"specialist":"ROOTLINE",
            "mission_id":claimed["mission_id"],
            "card_mission_id":protected_card_mission_id(claimed["preview_digest"]),
            "reply_markup":{"inline_keyboard":[]},
            "owner_visible_completion_policy":"verified_edit_or_new_message"},result_status
    if claimed["action_kind"]=="grouped_weights":
        result,result_status=execute_grouped_weight_claim(claimed,actor_id=owner,connect_factory=connect_factory)
        if not result.get("success"):return {"handled":True,**result},result_status
        if result.get("status")=="grouped_weights_replayed_noop":
            return {"handled":True,**result,"answer":"","suppress_owner_delivery":True},result_status
        rows=result["rows"]
        answer=(f"✅ <b>WEIGHTS RECORDED</b>\n\n{len(rows)} weights were recorded exactly as previewed."
                + (f" {result['movement_count']} pen movements were also recorded." if result["movement_count"] else ""))
        return {"handled":True,**result,"answer":answer,"mission_id":claimed["mission_id"],
          "card_mission_id":claimed["mission_id"],"reply_markup":{"inline_keyboard":[]},
          "owner_visible_completion_policy":"verified_edit_or_new_message"},201
    if claimed["action_kind"]=="herdmaster_breeding_grouped":
        from modules.oom_sakkie.herdmaster_breeding_exposure_runtime import execute_claimed_group
        try:
            result,result_status=execute_claimed_group(claimed,actor_id=owner,connect_factory=connect_factory)
        except Exception as exc:
            return {"handled":True,"success":False,
              "status":"protected_execution_recovery_pending",
              "answer":"I retained your confirmation, but could not complete the recording yet. I will recover it safely; please do not confirm again.",
              "mission_id":claimed["mission_id"],"card_mission_id":claimed["mission_id"],
              "writes_farm_data":False,"recovery_required":True,
              "error_type":type(exc).__name__},503
        if result.get("success") is True:
            completion=complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
            canonical_result=completion.get("result") if isinstance(completion.get("result"),dict) else result
            row_count=int(((claimed.get("preview_payload") or {}).get("preview") or {}).get("row_count") or 0)
            result={**canonical_result,"answer":f"Recorded the confirmed facts for {row_count} animals exactly once.",
              "mission_id":claimed["mission_id"],"card_mission_id":claimed["mission_id"],
              "reply_markup":{"inline_keyboard":[]},"owner_visible_completion_policy":"verified_edit_or_new_message"}
        else:
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        return {"handled":True,**result},result_status
    if claimed["action_kind"]=="sam_sale_payment":
        from modules.oom_sakkie.sam_payment_owner_runtime import execute_claimed_sale_payment
        result,result_status=execute_claimed_sale_payment(claimed,connect_factory=connect_factory)
        if result.get("success") is True:
            completion=complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
            result=completion.get("result") if isinstance(completion.get("result"),dict) else result
            if completion.get("replayed") is True:
                result={**result,"answer":"","suppress_owner_delivery":True,
                    "writes_to_supabase":False,"status":"sale_payment_replayed_noop"}
        elif result_status >= 500 or result.get("status")=="payment_state_write_failed":
            return {"handled":True,**result,"status":"sale_payment_recovery_pending",
                "recovery_required":True},503
        else:
            contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        return {"handled":True,**result},result_status
    operation=str((claimed.get("preview_payload") or {}).get("operation_id") or "")
    if not operation:return {"handled":True,"success":False,"status":"mortality_claim_operation_missing","writes_farm_data":False},409
    if health_handler is None:
        from modules.oom_sakkie.herdmaster_health_loss_runtime import handle_authenticated_health_loss_message
        health_handler=handle_authenticated_health_loss_message
    bound_payload=claimed.get("preview_payload") or {}
    health_parsed={**parsed,"text":"CONFIRM "+operation,"callback_confirmation":True,
      "protected_preview_sha256":str(bound_payload.get("preview_sha256") or ""),
      "protected_preview_identity":bound_payload.get("identity") or {}}
    result,result_status=health_handler(health_parsed,gateway_authority,connect_factory=connect_factory)
    if result.get("success") is True and str(result.get("status") or "") in {"completed","mortality_lifecycle_recorded"}:
        complete_claim(claimed["callback_token"],result,connect_factory=connect_factory)
        result={**result,"reply_markup":{"inline_keyboard":[]},
          "owner_visible_completion_policy":"verified_edit_or_new_message"}
    elif result.get("success") is not True:
        contain_claim(claimed["callback_token"],result,connect_factory=connect_factory)
    return {"handled":True,**result},result_status


def _irrigation_answer(result, claim):
    preview=claim.get("preview_payload") if isinstance(claim.get("preview_payload"),dict) else {}
    zone=str(preview.get("zone_id") or "the governed zone")
    segment=int(preview.get("current_segment") or 0)
    seconds=int(preview.get("segment_requested_seconds") or 0)
    if result.get("status")=="execution_store_degraded_hold":
        return ("ROOTLINE Hold: durable execution history is temporarily unavailable. "
                "No controller command was issued and this confirmation has been contained.")
    if result.get("status")=="segment_started":
        return (f"{zone} irrigation segment {segment} started. It is bounded to {seconds} seconds; "
                "ROOTLINE will verify provider OFF before any later reassessment.")
    return (f"{zone} irrigation segment {segment} remains owned by ROOTLINE; "
            "no duplicate command was issued.")
