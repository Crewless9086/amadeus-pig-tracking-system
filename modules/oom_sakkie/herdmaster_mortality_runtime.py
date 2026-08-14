"""Existing-rail persistence for authenticated mortality specialist consumption."""
from __future__ import annotations

import hashlib,json
from datetime import datetime
from typing import Mapping,Sequence

from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.oom_sakkie.herdmaster_mortality_adapter import consume_mortality_packet
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

EVENT_SOURCE="oom_sakkie_herdmaster_mortality_consumption"


def consume_current_mortality_packet(*,packet:Mapping,authority,owner_user_id:str,
        observed_at:datetime,active_lifecycles:Sequence[Mapping]=(),language="en",state_store=None):
    bound=bind_gateway_owner_authority(authority,"farm_manager_round")
    if not bound or bound.owner_user_id!=str(owner_user_id):
        return None,{"success":False,"status":"mortality_consumption_auth_denied",
            "writes_farm_data":False,"sends_telegram":False}
    result,binding=consume_mortality_packet(packet,observed_at=observed_at,
        active_lifecycles=active_lifecycles,language=language)
    if result.availability.value!="available":
        return result,{**binding,"success":False,"status":"mortality_consumption_contained"}
    store=state_store or mortality_consumption_store
    identity=str(packet["review_identity"])
    owner_hash=hashlib.sha256(str(owner_user_id).encode()).hexdigest()
    prior=store("load",identity,None) or {}
    if prior and prior.get("owner_identity_sha256")!=owner_hash:
        return None,{**binding,"success":False,"status":"mortality_consumption_owner_binding_conflict"}
    if prior.get("evidence_digest")==packet["evidence_digest"]:
        return result,{**binding,"success":True,"status":"mortality_consumption_replay_suppressed",
            "review_identity":identity,"evidence_digest":packet["evidence_digest"],"notify_owner":False}
    record={"review_identity":identity,"owner_identity_sha256":owner_hash,
        "evidence_digest":str(packet["evidence_digest"]),
        "canonical_death_event_ids":sorted(str(row.get("event_id"))
            for row in packet.get("proven_facts") or () if row.get("event_id")),
        "deduplication_key":str(packet["deduplication_key"]),"observed_at":observed_at.isoformat(),
        "prior_evidence_digest":str(prior.get("evidence_digest") or ""),
        "status":"material_refresh" if prior else "initial_assessment",**binding}
    saved=store("record",identity,record)
    if not isinstance(saved,Mapping) or saved.get("success") is not True:
        return None,{**binding,"success":False,"status":"mortality_consumption_persistence_unproven"}
    if saved.get("created") is False:
        winner=store("load",identity,None) or {}
        if (winner.get("owner_identity_sha256")!=owner_hash
                or winner.get("evidence_digest")!=packet["evidence_digest"]):
            return None,{**binding,"success":False,"status":"mortality_consumption_winner_binding_conflict"}
        return result,{**binding,"success":True,"status":"mortality_consumption_replay_suppressed",
            "review_identity":identity,"evidence_digest":packet["evidence_digest"],"notify_owner":False}
    return result,{**record,"success":True,"notify_owner":True,
        "status":"mortality_consumption_material_refresh" if prior else "mortality_consumption_ready"}


def mortality_consumption_store(action,identity,payload):
    if action=="load":
        with connect_bounded_read() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'mortality_consumption'
                  from public.sam_live_stock_conversation_review_events where event_source=%s
                    and review_json->'mortality_consumption'->>'review_identity'=%s
                  order by created_at desc,review_event_id desc limit 1""",(EVENT_SOURCE,identity))
                row=cursor.fetchone();return row[0] if row else None
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event,record_sam_live_stock_review_event
    event_id="OOM-MORTALITY-"+hashlib.sha256(json.dumps({"identity":identity,
        "digest":payload.get("evidence_digest")},sort_keys=True).encode()).hexdigest().upper()
    event=build_sam_live_stock_review_event({"conversation_id":identity},{},{},
        {"score":0,"safe_to_send":False,"recommended_action":"internal_mortality_assessment"},event_source=EVENT_SOURCE)
    event.update({"review_event_id":event_id,"chatwoot_conversation_id":identity,
        "review_json":{"mortality_consumption":dict(payload)},"decision_json":{},"facts_json":{},
        "customer_message_excerpt":"","sam_reply_excerpt":""})
    saved,status=record_sam_live_stock_review_event(event)
    return {**saved,"success":status<400 and saved.get("success") is True,
            "created":saved.get("created",status<300)}
