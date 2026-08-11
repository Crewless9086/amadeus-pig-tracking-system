from datetime import datetime, timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_request_runtime import (
    delivery_retry_authority_for, handle_herdmaster_request)
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result

OWNER="5721652188"


def packet():
    def task(name,date,days,boar="Bola",cohort=1):
        return {"task_id":"TASK-"+name,"tag_number":name,"completed":False,
            "placement_cohort":"immediate" if cohort==1 else "next",
            "placement_cohort_number":cohort,"proposed_placement_date":date,
            "priority":28,"days_since_weaning":days,
            "male_recommendation":{"recommended":{"tag_number":boar}}}
    return {"success":True,"worklist_id":"HERD-WEEK-1",
        "generated_at":"2026-08-11T18:00:00+00:00",
        "tasks":[task("Shupe","2026-08-12",62),task("Sophie","2026-08-12",36),
                 task("Teena","2026-08-29",0,cohort=2),
                 task("Waki","2026-08-29",0,cohort=2),
                 task("Zigay","2026-08-29",0,cohort=2)]}


def parsed(domain="herd_management",language="en",message="3527"):
    return {"text":"Give me the updated practical breeding plan using all weanings recorded today.",
        "telegram_user_id":OWNER,"telegram_chat_id":OWNER,
        "provider_message_id":message,"provider_timestamp":"2026-08-11T16:39:53+00:00",
        "semantic":{"domain":domain,"intent":"current_breeding_plan","message_kind":"request",
                    "requested_action":"updated practical breeding plan","language":language,
                    "needs_clarification":False}}


def store():
    rows={}
    def call(action,identity,payload):
        if action=="load": return rows.get(identity)
        if identity in rows:return {"success":True,"created":False}
        rows[identity]=payload;return {"success":True,"created":True}
    return call


def test_specific_breeding_request_returns_current_herdmaster_plan_and_replay_is_silent():
    state=store(); authority=issue_gateway_owner_authority(OWNER,OWNER)
    first,status=handle_herdmaster_request(parsed(),authority,canonical_loader=packet,event_store=state)
    replay,_=handle_herdmaster_request(parsed(),authority,canonical_loader=packet,event_store=state)
    assert status==200 and first["specialist_identity"]=="HERDMASTER"
    assert "UPDATED BREEDING PLAN" in first["answer"] and "TODAY'S FARM BRIEF" not in first["answer"]
    assert all(name in first["answer"] for name in ("Shupe","Sophie","Teena","Waki","Zigay"))
    assert "Pig 127" not in first["answer"] and "PIG-" not in first["answer"]
    assert replay["status"]=="herdmaster_request_replay_recovered"


def test_afrikaans_paraphrase_and_broad_manager_boundary():
    result,_=handle_herdmaster_request(parsed(language="af"),
        issue_gateway_owner_authority(OWNER,OWNER),canonical_loader=packet,event_store=store())
    assert "OPGEDATEERDE TEELPLAN" in result["answer"] and "VANDAG SE SPEENWERK" in result["answer"]
    broad,_=handle_herdmaster_request(parsed(domain="manager_round",message="3529"),
        issue_gateway_owner_authority(OWNER,OWNER),canonical_loader=packet,event_store=store())
    assert broad=={"handled":False}


def test_missing_chronology_or_canonical_evidence_fails_closed_without_send_or_write():
    missing={**parsed(),"provider_message_id":""}
    result,_=handle_herdmaster_request(missing,issue_gateway_owner_authority(OWNER,OWNER),
        canonical_loader=packet,event_store=store())
    assert result=={"handled":False}
    failed,status=handle_herdmaster_request(parsed(message="3530"),
        issue_gateway_owner_authority(OWNER,OWNER),canonical_loader=lambda:{"success":False},event_store=store())
    assert status==503 and failed["writes_farm_data"] is False and not failed.get("answer")


def test_natural_paraphrase_family_is_owned_by_semantic_domain_not_exact_words():
    authority=issue_gateway_owner_authority(OWNER,OWNER)
    variants=(
        "Use today's weanings and update the practical mating plan.",
        "Werk die praktiese teelplan by met al vandag se speenwerk.",
        "Wat is die nuwe breeding plan after vandag se weanings?",
    )
    for index,text in enumerate(variants):
        value={**parsed(message=str(3600+index)),"text":text}
        result,status=handle_herdmaster_request(value,authority,
            canonical_loader=packet,event_store=store())
        assert status==200 and result["specialist_identity"]=="HERDMASTER"
        assert "TODAY'S FARM BRIEF" not in result["answer"]


def test_other_herd_management_intents_are_not_claimed_as_breeding_plans():
    for intent in ("latest_weight", "animal_lookup", "farrowing_status", "herd_inventory"):
        value=parsed(message="3700")
        value["semantic"]={**value["semantic"],"intent":intent}
        result,_=handle_herdmaster_request(value,issue_gateway_owner_authority(OWNER,OWNER),
            canonical_loader=packet,event_store=store())
        assert result=={"handled":False}


def family_store():
    rows={}
    def call(action,identity,payload):
        if action=="load": return list(rows.values())
        if identity in rows:return {"success":True,"created":False}
        rows[identity]=payload;return {"success":True,"created":True}
    return call,rows


def test_compute_crash_before_delivery_resumes_and_proven_delivery_replays_noop():
    authority=issue_gateway_owner_authority(OWNER,OWNER); computation=store()
    first,_=handle_herdmaster_request(parsed(),authority,canonical_loader=packet,event_store=computation)
    recovered,_=handle_herdmaster_request(parsed(),authority,canonical_loader=packet,event_store=computation)
    lifecycle,_rows=family_store(); sends=[]
    delivery=deliver_family_result(parsed(),recovered,specialist="HERDMASTER",
        mission_id=first["mission_id"],card_mission_id=first["card_mission_id"],event_store=lifecycle,
        sender=lambda chat,text:(sends.append((chat,text)) or {"success":True,"telegram_message_id":"4001"}))
    replay=deliver_family_result(parsed(),recovered,specialist="HERDMASTER",
        mission_id=first["mission_id"],card_mission_id=first["card_mission_id"],event_store=lifecycle,
        sender=lambda *_:(_ for _ in ()).throw(AssertionError("must not resend")))
    assert delivery["telegram_sends"]==1 and len(sends)==1
    assert replay["telegram_sends"]==0


def test_ambiguous_delivery_is_not_retried_without_definite_zero_send_proof():
    result,_=handle_herdmaster_request(parsed(),issue_gateway_owner_authority(OWNER,OWNER),
        canonical_loader=packet,event_store=store())
    lifecycle,_rows=family_store(); attempts=[]
    first=deliver_family_result(parsed(),result,specialist="HERDMASTER",
        mission_id=result["mission_id"],card_mission_id=result["card_mission_id"],event_store=lifecycle,
        sender=lambda *_:(attempts.append(1) or {"success":False}))
    second=deliver_family_result(parsed(),result,specialist="HERDMASTER",
        mission_id=result["mission_id"],card_mission_id=result["card_mission_id"],event_store=lifecycle,
        sender=lambda *_:(attempts.append(2) or {"success":True,"telegram_message_id":"bad"}))
    assert first["status"]=="family_message_delivery_contained"
    assert second["status"]=="family_message_delivery_ambiguous" and attempts==[1]


def test_definitely_not_sent_delivery_gets_one_content_bound_retry(monkeypatch):
    result,_=handle_herdmaster_request(parsed(),issue_gateway_owner_authority(OWNER,OWNER),
        canonical_loader=packet,event_store=store())
    lifecycle,rows=family_store(); attempts=[]
    first=deliver_family_result(parsed(),result,specialist="HERDMASTER",
        mission_id=result["mission_id"],card_mission_id=result["card_mission_id"],event_store=lifecycle,
        sender=lambda *_:(attempts.append("first") or
            {"success":False,"delivery_definitely_not_sent":True}))
    monkeypatch.setattr("modules.oom_sakkie.family_message_lifecycle.load_family_lifecycle",
        lambda _identity:list(rows.values()))
    retry_authority=delivery_retry_authority_for(result)
    second=deliver_family_result(parsed(),result,specialist="HERDMASTER",
        mission_id=result["mission_id"],card_mission_id=result["card_mission_id"],event_store=lifecycle,
        delivery_retry_authority=retry_authority,
        sender=lambda *_:(attempts.append("second") or
            {"success":True,"telegram_message_id":"4002"}))
    third=deliver_family_result(parsed(),result,specialist="HERDMASTER",
        mission_id=result["mission_id"],card_mission_id=result["card_mission_id"],event_store=lifecycle,
        sender=lambda *_:(_ for _ in ()).throw(AssertionError("must not send third time")))
    assert first["delivery_definitely_not_sent"] is True
    assert second["telegram_sends"]==1 and third["telegram_sends"]==0
    assert attempts==["first","second"]
