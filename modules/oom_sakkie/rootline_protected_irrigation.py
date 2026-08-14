"""Protected owner-confirmed entry to the existing ROOTLINE segment spine."""
from __future__ import annotations
import os
from modules.oom_sakkie.protected_action_claims import (
    build_buttons, canonical_preview_digest, create_claim,
)

ACTION_KIND="rootline_irrigation_segment"
MISSION_ID="RMQ-20260813-04"
BOUND_KEYS=("job_id","job_sha256","zone_id","channel","segment_identity",
 "current_segment","segment_requested_seconds","requested_total_duration_seconds",
 "governed_executable_duration_seconds","plan_generation",
 "controller_safety_generation","eligibility_sha256")

def protected_card_mission_id(preview_digest):
    digest=str(preview_digest or "").lower()
    if len(digest)!=64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("protected_irrigation_preview_digest_invalid")
    return MISSION_ID+":PROTECTED:"+digest[:24].upper()

def build_preview_payload(artifact,*,mission_id):
    if str(mission_id)!=MISSION_ID:
        raise ValueError("protected_irrigation_mission_mismatch")
    payload={k:artifact.get(k) for k in BOUND_KEYS}
    payload.update({"mission_id":str(mission_id),"expected_segment_count":artifact.get("expected_segment_count"),
      "maximum_duration_seconds":artifact.get("maximum_duration_seconds"),
      "evidence_generation":artifact.get("plan_generation")})
    if (payload["zone_id"]!="B12345" or payload["channel"]!=1 or payload["current_segment"]!=1
        or payload["segment_requested_seconds"]!=3599 or payload["requested_total_duration_seconds"]!=7200
        or payload["governed_executable_duration_seconds"]!=7198 or payload["expected_segment_count"]!=2):
        raise ValueError("protected_irrigation_preview_outside_boundary")
    return payload

def create_irrigation_preview_claim(*,artifact,owner_user_id,private_chat_id,
        mission_id,provider_message_id,ttl_minutes=15,connect_factory=None):
    payload=build_preview_payload(artifact,mission_id=mission_id)
    claim=create_claim(action_kind=ACTION_KIND,owner_user_id=owner_user_id,
      private_chat_id=private_chat_id,mission_id=mission_id,
      provider_message_id=provider_message_id,
      evidence_generation=payload["evidence_generation"],preview_payload=payload,
      ttl_minutes=ttl_minutes,connect_factory=connect_factory)
    return {**claim,"preview_payload":payload,
      "reply_markup":build_buttons(claim["callback_token"])}

def execute_claimed_segment(claim,*,parsed,environ=None,database_url=None,runner=None,notify=None):
    payload=claim.get("preview_payload") if isinstance(claim.get("preview_payload"),dict) else {}
    try:
        boundary=build_preview_payload(payload,mission_id=str(payload.get("mission_id") or ""))
    except ValueError:
        return _safe("protected_irrigation_preview_binding_mismatch"),409
    if (canonical_preview_digest(ACTION_KIND,payload)!=claim.get("preview_digest")
        or boundary!=payload or str(claim.get("mission_id"))!=MISSION_ID):
        return _safe("protected_irrigation_preview_binding_mismatch"),409
    if runner is None:
        from modules.telemetry.rootline_execution_runtime import run_protected_rootline_segment
        runner=run_protected_rootline_segment
    source=environ if environ is not None else os.environ
    database_url=database_url or source.get("DATABASE_URL")
    notify=notify or (lambda _state,_execution:{"success":True,"provider_delivery_confirmed":False})
    result=runner(expected_artifact=payload,notify=notify,environ=source,database_url=database_url,
      owner_user_id=str(parsed.get("telegram_user_id") or ""),chat_id=str(parsed.get("telegram_chat_id") or ""))
    status=200 if result.get("success") is True else 409
    return result,status

def _safe(status):
    return {"success":False,"status":status,"hardware_commands":0,"provider_control_calls":0,
      "writes_farm_data":False,"borehole_authority":False,"fertilizer_authority":False}
