from datetime import datetime, timezone

from modules.oom_sakkie.farm_manager_loop import (Authority, FamilyBrief, Provenance,
    SpecialistWorkItem, WorkState)
from modules.oom_sakkie.owner_response_composer import (compose_manager_brief,
    compose_rootline, compose_weight_preview)
from modules.oom_sakkie.rootline_reassessment_lifecycle import reassess_rootline, record_reassessment_delivery
from modules.oom_sakkie.herdmaster_weight_preview import preview_grouped_herd_weights

NOW=datetime(2026,8,4,6,0,tzinfo=timezone.utc)

def rootline(c="Hold"):
    return {"success":True,"overall_status":"Plan ready","operating_date":"2026-08-04",
        "current_power":{"battery_soc_pct":41,"solar_power_w":0,"load_power_w":776,"grid_power_w":0},
        "battery_policy":{"governing_reserve_soc_pct":63},
        "recommendations":[
            {"subject":"B12345","status":"Hold","reason":"Reserve is below the governing target."},
            {"subject":"C12345","status":c,"reason":"Fresh evidence supports this C Camp decision."},
            {"subject":"borehole","status":"Hold","reason":"Current storage does not support pumping."},
            {"subject":"fertilizer_injection","status":"Do Not Run","reason":"Irrigation interlock remains protected."}],
        "owner_brief":{"reassess":"At 10:00 or when material evidence changes.","family_fact_needed":""},
        "next_reassessment":{"trigger":"time_or_change","at":"10:00 SAST"},"result_id":"R1","generation":"G1"}

def test_verbose_rootline_packet_becomes_compact_farm_message_without_b_camp_copy_error():
    packet=rootline()
    packet["recommendations"][1]["reason"]=("Not selected for today's proportional B-Camp plan; "
        "retain the four-day weekly target.")
    answer=compose_rootline(packet)
    assert "<b>ROOTLINE — WATER &amp; POWER</b>" in answer
    assert "<b>B Camp:</b> Hold" in answer and "<b>C Camp:</b> Hold" in answer
    assert "B-Camp plan" not in answer and "authority" not in answer.lower()
    assert "today's proportional camp plan" in answer
    assert "internal" not in answer.lower() and len(answer)<1200

def test_rootline_hostile_scalar_values_are_never_rendered_as_telegram_html():
    packet=rootline(); packet["current_power"]={key:"<b>oops</b>" for key in
        ("battery_soc_pct","solar_power_w","load_power_w","grid_power_w")}
    packet["battery_policy"]={"governing_reserve_soc_pct":"<i>bad</i>","absolute_floor_soc_pct":"<u>bad</u>"}
    answer=compose_rootline(packet)
    assert "<b>oops</b>" not in answer and "<i>bad</i>" not in answer and "<u>bad</u>" not in answer
    assert answer.count("Unavailable") == 5

def test_manager_sections_and_afrikaans_layout_preserve_supported_facts():
    p=Provenance("herdmaster","R",("canonical",),NOW,1)
    items=(SpecialistWorkItem("w","w","herd","Pig 127 mortality record follow-up",
        "Owner reported dead; recording remains governed.","Review the retained mortality preview.","charl",
        WorkState.URGENT,Authority.ADVISORY,p,business_value=120),
        SpecialistWorkItem("m","m","herd","Prepare Mona and Mysikind",
        "Both remain Assumed Pregnant, not clinically confirmed.","Prepare proportionally.","charl",
        WorkState.DUE_TODAY,Authority.ADVISORY,p,business_value=100))
    brief=FamilyBrief(generated_at=NOW,queue=items,by_family_member={"charl":items},questions={},
        suppressed={},follow_ups=(),specialist_gaps={})
    answer=compose_manager_brief(brief,language="af")
    assert "Pig 127-sterfterekord" in answer and "breathing" not in answer.lower()
    assert "vermoedelik dragtig" in answer and "<b>🐷 Welsyn &amp; Kudde</b>" in answer
    assert "Volgende herbeoordeling" in answer

def test_production_shaped_afrikaans_brief_marks_dynamic_specialist_source_words():
    p=Provenance("herdmaster","ROUND-20260804",("canonical",),NOW,1)
    item=SpecialistWorkItem("prep","prep","herd","Prepare Mona and Mysikind and complete Monday weighing",
        "Mona and Mysikind remain Assumed Pregnant; farrowing range 22–26 August and preparation window 8–15 August.",
        "Weigh every current active/on-farm pig and prepare both farrowing areas.","charl",WorkState.DUE_TODAY,
        Authority.ADVISORY,p,business_value=100,genuine_question="Are both farrowing areas ready?",question_for="charl")
    brief=FamilyBrief(generated_at=NOW,queue=(item,),by_family_member={"charl":(item,)},
        questions={"charl":("Are both farrowing areas ready?",)},suppressed={},follow_ups=(),specialist_gaps={})
    answer=compose_manager_brief(brief,language="af")
    assert "Spesialisbewys (bronwoorde)" in answer
    assert "Bronitem (bronwoorde): Prepare Mona" in answer
    assert "Spesialisvraag (bronwoorde): Are both farrowing areas ready?" in answer
    assert "Wat ek van jou nodig het" in answer and "Welsyn &amp; Kudde" in answer

def test_production_shaped_rootline_afrikaans_marks_every_dynamic_source_fragment():
    packet=rootline(); packet["overall_status"]="Dynamic specialist decision"
    packet["owner_brief"]={"recommend_now":"Dynamic specialist decision",
        "family_fact_needed":"Are the east tanks still half full?",
        "reassess":"When rain telemetry or storage evidence changes dynamically."}
    packet["recommendations"][0]["reason"]="A dynamic specialist reason with 17 mm uncertainty."
    packet["battery_policy"]["governing_reason"]="A dynamic reserve model selected 63 percent."
    answer=compose_rootline(packet,language="af")
    assert "Bronbesluit (bronwoorde): Dynamic specialist decision" in answer
    assert "Spesialisrede (bronwoorde): A dynamic specialist reason" in answer
    assert "Spesialisbewys (bronwoorde): A dynamic reserve model" in answer
    assert "Spesialisvraag (bronwoorde): Are the east tanks" in answer
    assert "Spesialis se herbeoordeling (bronwoorde): When rain telemetry" in answer

def test_natural_grouped_weight_preview_is_one_confirmation_boundary():
    answer=compose_weight_preview([
        {"label":"Pig 11","pig_id":"PIG-2026-E88A","weight_kg":47.2},
        {"label":"Mona","pig_id":"PIG-2026-D050","weight_kg":118}],language="en")
    assert answer.count("kg")==2 and "Confirm this grouped preview" in answer
    assert "recorded" in answer and "PIG-2026-E88A" in answer

def test_natural_grouped_weight_lines_resolve_canonically_without_repeating_known_date():
    pigs={"success":True,"pigs":[
        {"pig_id":"PIG-2026-E88A","tag_number":"11","status":"Active","on_farm":"Yes"},
        {"pig_id":"PIG-2026-D050","tag_number":"Mona","status":"Active","on_farm":"Yes"}]}
    def preflight(payload): return {"success":True,"accepted_count":2,"accepted_rows":payload["rows"]},200
    result=preview_grouped_herd_weights("Pig 11 47.2 kg, Mona 118 kg.",weight_date="2026-08-04",
        readiness=pigs,preflight=preflight)
    assert result["success"] is True and result["weight_date"]=="2026-08-04"
    assert [(row["pig_id"],row["weight_kg"]) for row in result["rows"]]==[
        ("PIG-2026-E88A",47.2),("PIG-2026-D050",118)]
    assert result["confirmation_required"] is True and result["writes_performed"] is False

def store():
    rows={}
    def action(kind,identity,payload):
        if kind=="load_delivered":
            values=[v for v in rows.values() if v.get("delivery_state")=="delivered" and f'{v["owner_user_id"]}|{v["chat_id"]}'==identity]
            return values[-1] if values else None
        if kind=="load_identity": return rows.get(identity)
        if kind in {"claim_pending","record_observation"}:
            if identity in rows:return {"success":True,"created":False}
            rows[identity]=payload;return {"success":True,"created":True}
        if kind in {"mark_delivered","mark_ambiguous"}:
            rows[identity]={**rows[identity],**payload};return {"success":True}
    return rows,action

def test_automatic_reassessment_suppresses_unchanged_and_emits_one_material_change():
    rows,state=store()
    first=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",
        specialist_loader=lambda:rootline(),state_store=state)
    assert rows[first["notification_identity"]]["zones"] == [
        {"zone_id":"B12345","decision":"Hold",
         "reason":"Reserve is below the governing target.",
         "planned_duration_minutes":None,"feasible_window":None},
        {"zone_id":"C12345","decision":"Hold",
         "reason":"Fresh evidence supports this C Camp decision.",
         "planned_duration_minutes":None,"feasible_window":None},
    ]
    assert rows[first["notification_identity"]]["operating_date"] == "2026-08-04"
    pending=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",
        specialist_loader=lambda:rootline(),state_store=state)
    assert pending["notify_owner"] is True and pending["status"]=="rootline_reassessment_delivery_pending"
    record_reassessment_delivery(identity=first["notification_identity"],owner_user_id="42",chat_id="42",
        material_digest=first["material_digest"],delivery={"provider_delivery_confirmed":True,
        "provider_message_id":"7001","provider_timestamp":"2026-08-04T06:00:01Z"},state_store=state)
    unchanged=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",
        specialist_loader=lambda:rootline(),state_store=state)
    changed=reassess_rootline(owner_user_id="42",chat_id="42",trigger="material_evidence_change",
        specialist_loader=lambda:rootline("Run later"),state_store=state)
    record_reassessment_delivery(identity=changed["notification_identity"],owner_user_id="42",chat_id="42",
        material_digest=changed["material_digest"],delivery={"provider_delivery_confirmed":True,
        "provider_message_id":"7002"},state_store=state)
    replay=reassess_rootline(owner_user_id="42",chat_id="42",trigger="material_evidence_change",
        specialist_loader=lambda:rootline("Run later"),state_store=state)
    assert first["notify_owner"] is True
    assert unchanged["notify_owner"] is False and unchanged["telegram_sends"]==0
    observations=[row for row in rows.values() if row.get("delivery_state")=="observation_only"]
    assert len(observations)==2
    assert changed["notify_owner"] is True and "C Camp:</b> Recommendation - irrigate" in changed["answer"]
    assert "Not yet authorized or started" in changed["answer"]
    assert replay["notify_owner"] is False and len(rows)==4
    assert all(item["hardware_commands"]==0 for item in (first,unchanged,changed,replay))


def test_later_result_generation_updates_observation_silently_when_material_is_stable():
    rows,state=store()
    first_packet=rootline()
    first_packet["next_reassessment"]={"trigger":"new_canonical_evidence",
        "at":"2026-08-04T10:40:14+02:00"}
    first=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",
        specialist_loader=lambda:first_packet,state_store=state)
    record_reassessment_delivery(identity=first["notification_identity"],owner_user_id="42",chat_id="42",
        material_digest=first["material_digest"],delivery={"provider_delivery_confirmed":True,
        "provider_message_id":"7001"},operating_date=first["operating_date"],
        result_id=first["result_id"],evidence_generation=first["evidence_generation"],state_store=state)
    later_packet={**first_packet,"generation":"G2","result_id":"R2",
        "current_power":{**first_packet["current_power"],"battery_soc_pct":40},
        "next_reassessment":{"trigger":"new_canonical_evidence",
            "at":"2026-08-04T10:40:41+02:00"}}
    changed=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",
        specialist_loader=lambda:later_packet,state_store=state)
    assert changed["status"]=="rootline_reassessment_unchanged"
    assert changed["notify_owner"] is False and changed["telegram_sends"]==0
    assert any(row.get("result_id") == "R2" and row.get("delivery_state") == "observation_only"
               for row in rows.values())


def test_fixed_reassessment_deadline_change_remains_material():
    rows,state=store()
    first_packet=rootline()
    first_packet["next_reassessment"]={"trigger":"bounded_forecast_rain_check",
        "at":"2026-08-04T11:00:00+02:00"}
    first=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",
        specialist_loader=lambda:first_packet,state_store=state)
    record_reassessment_delivery(identity=first["notification_identity"],owner_user_id="42",chat_id="42",
        material_digest=first["material_digest"],delivery={"provider_delivery_confirmed":True,
        "provider_message_id":"7001"},state_store=state)
    changed_packet={**first_packet,"next_reassessment":{
        "trigger":"bounded_forecast_rain_check","at":"2026-08-04T11:30:00+02:00"}}
    changed=reassess_rootline(owner_user_id="42",chat_id="42",trigger="material_evidence_change",
        specialist_loader=lambda:changed_packet,state_store=state)
    assert changed["status"]=="rootline_reassessment_changed"
    assert changed["notify_owner"] is True

def test_reassessment_is_owner_scoped_and_ambiguous_delivery_never_becomes_unchanged():
    rows,state=store()
    a=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",specialist_loader=lambda:rootline(),state_store=state)
    b=reassess_rootline(owner_user_id="43",chat_id="43",trigger="declared_time",specialist_loader=lambda:rootline(),state_store=state)
    assert a["notification_identity"] != b["notification_identity"] and b["notify_owner"] is True
    record_reassessment_delivery(identity=a["notification_identity"],owner_user_id="42",chat_id="42",
        material_digest=a["material_digest"],delivery={"provider_delivery_ambiguous":True},state_store=state)
    again=reassess_rootline(owner_user_id="42",chat_id="42",trigger="declared_time",specialist_loader=lambda:rootline(),state_store=state)
    assert again["status"]=="rootline_reassessment_delivery_ambiguous" and again["notify_owner"] is False
