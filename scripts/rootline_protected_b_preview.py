"""Prepare and deliver exactly one protected B-segment preview; never actuates."""
from __future__ import annotations
import os
from datetime import datetime,timezone
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.protected_action_claims import bind_claim_card,contain_unbound_preview_claim
from modules.oom_sakkie.rootline_protected_irrigation import MISSION_ID,create_irrigation_preview_claim,protected_card_mission_id
from modules.telemetry.rootline_execution_runtime import _current
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
from modules.telemetry.rootline_ewelink_readback import read_current_device
from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store
from modules.telemetry.rootline_water_energy_plan import read_current_water_energy_evidence

def prepare_and_deliver(*,owner_user_id,private_chat_id,provider_message_id,environ=None,
        database_url=None,token_store=None,deliver=deliver_family_result,now=None):
    source=environ if environ is not None else os.environ;now=now or datetime.now(timezone.utc)
    database_url=database_url or source.get("DATABASE_URL")
    if not owner_user_id or str(owner_user_id)!=str(private_chat_id):
        raise RuntimeError("protected_irrigation_owner_private_chat_required")
    if rootline_irrigation_execution_store("load_active",None):
        raise RuntimeError("protected_irrigation_active_execution_present")
    token_store=token_store or PostgresOAuthTokenStore(database_url)
    current=_current(read_current_water_energy_evidence,read_current_device,token_store,source,database_url,now)
    artifact=current["artifact"]
    if artifact.get("eligible") is not True:
        raise RuntimeError(str(artifact.get("status") or "protected_irrigation_not_eligible"))
    claim=create_irrigation_preview_claim(artifact=artifact,owner_user_id=owner_user_id,
      private_chat_id=private_chat_id,mission_id=MISSION_ID,provider_message_id=provider_message_id)
    parsed={"telegram_user_id":str(owner_user_id),"telegram_chat_id":str(private_chat_id),
      "provider_message_id":str(provider_message_id),"provider_timestamp":now.isoformat()}
    answer=("<b>ROOTLINE — B IRRIGATION ACCEPTANCE</b>\n\nB/channel 1, segment 1: at most "
      "59 minutes 59 seconds. The requested plan is 120 minutes; this governed job allows two "
      "separate 3,599-second segments. Segment 2 requires a new OFF/readback reassessment.\n\n"
      "Confirm only while physically present at B. Emergency path: physical/controller OFF. "
      "No command has been sent.")
    result={"success":True,"status":"waiting_for_confirmation","answer":answer,
      "callback_token":claim["callback_token"],"reply_markup":claim["reply_markup"],
      "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    card_mission_id=protected_card_mission_id(claim["preview_digest"])
    delivery=deliver(parsed,result,specialist="ROOTLINE",mission_id=MISSION_ID,
      card_mission_id=card_mission_id)
    message_id=str(delivery.get("telegram_message_id") or "")
    if not delivery.get("success") or not message_id or not bind_claim_card(claim["callback_token"],message_id):
        contain_unbound_preview_claim(claim["callback_token"],{
          "success":False,"status":"protected_irrigation_preview_card_binding_unproven",
          "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False})
        raise RuntimeError("protected_irrigation_preview_card_binding_unproven")
    return {"claim":claim,"delivery":delivery,"artifact":artifact,"hardware_commands":0,
      "provider_control_calls":0}
