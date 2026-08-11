"""Precedence owner for active protected mortality and grouped-weight previews."""
from __future__ import annotations
import re
from modules.oom_sakkie.protected_action_claims import (
    CALLBACK_PREFIX, claim_callback, complete_claim, contain_claim, execute_grouped_weight_claim,
    resolve_natural_confirmation,
)
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority

NATURAL_CONFIRM=re.compile(r"^(?:i\s+confirm(?:\s+this)?|confirm(?:\s+all)?|yes[, ]*confirm|ek\s+bevestig(?:\s+alles)?|bevestig(?:\s+alles)?)\s*[.!]?$",re.I)

def handle_protected_action_input(parsed, gateway_authority, *, callback_data="",
                                  connect_factory=None, health_handler=None):
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
    claimed,status=claim_callback(data,owner_user_id=owner,private_chat_id=chat,
      provider_message_id=str(parsed.get("provider_message_id") or parsed.get("callback_query_id") or ""),
      provider_timestamp=str(parsed.get("provider_timestamp") or ""),
      source_card_message_id=str(parsed.get("reply_to_message_id") or ""),connect_factory=connect_factory)
    if status>=400 or claimed.get("status")!="protected_callback_claimed":
        if claimed.get("status") in {"protected_preview_change_requested","protected_preview_cancelled"}:
            claimed["answer"]=("Send the corrected facts when ready; nothing was recorded."
                if claimed["status"]=="protected_preview_change_requested" else
                "Cancelled. Nothing was recorded.")
        return {"handled":True,**claimed,"writes_farm_data":False,"suppress_owner_delivery":claimed.get("status")=="protected_callback_replayed_noop"},status
    claimed["callback_token"]=data.split(":")[1]
    if claimed["action_kind"]=="grouped_weights":
        result,result_status=execute_grouped_weight_claim(claimed,actor_id=owner,connect_factory=connect_factory)
        if not result.get("success"):return {"handled":True,**result},result_status
        rows=result["rows"]
        answer=(f"✅ <b>WEIGHTS RECORDED</b>\n\n{len(rows)} weights were recorded exactly as previewed."
                + (f" {result['movement_count']} pen movements were also recorded." if result["movement_count"] else ""))
        return {"handled":True,**result,"answer":answer,"mission_id":claimed["mission_id"],
          "card_mission_id":claimed["mission_id"],"reply_markup":{"inline_keyboard":[]},
          "owner_visible_completion_policy":"verified_edit_or_new_message"},201
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
