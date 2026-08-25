from datetime import datetime, timezone
from dataclasses import replace
import pytest

from modules.oom_sakkie.daily_farm_manager import (
    build_daily_management_packet, build_litter_watch_result, build_sale_watch_result,
    run_daily_farm_manager)
from modules.oom_sakkie.farm_manager_loop import (
    Authority, PROTECTED_AUTHORITIES, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState)
from modules.oom_sakkie.herdmaster_daily_manager_adapter import (
    reconcile_manager_question_answer)

NOW=datetime(2026,8,10,5,0,tzinfo=timezone.utc)


def result(name="rootline",items=()):
    return SpecialistResult(name,name+"-1",NOW,SpecialistAvailability.AVAILABLE,
        work_items=tuple(items))


def item(identity,title,state=WorkState.PLANNED,value=50,question="",specialist="rootline"):
    provenance=Provenance(specialist,specialist+"-1",("canonical",),NOW,1.0)
    return SpecialistWorkItem(item_id=identity,dedupe_key=identity,domain="water_energy",
        title=title,why="Supported reason",next_action="Supported action",assignee="charl",
        state=state,authority=Authority.READ_ONLY,provenance=provenance,
        business_value=value,genuine_question=question,question_for="charl" if question else "")


def store():
    rows={}
    def effect(action,identity,payload):
        if action=="load_daily":
            candidates=[row for row in rows.values() if row.get("daily_identity")==identity
                        and row.get("status") in {"presented","unchanged"}
                        and row.get("owner_user_id")==str((payload or {}).get("owner_user_id") or "")
                        and row.get("chat_id")==str((payload or {}).get("chat_id") or "")]
            return candidates[-1] if candidates else None
        if action=="load_answered_questions":
            return ()
        created=identity not in rows
        if created: rows[identity]=dict(payload or {})
        return {"success":True,"created":created}
    effect.rows=rows
    return effect


def litter_rows():
    return [
        {"Litter_ID":"LIT-2026-1350","Sow_Pig_ID":"PIG-TEENA",
         "Sow_Tag_Number":"Teena","Litter_Status":"Active",
         "Wean_Date":"2026-08-06","Weaned_Count":None},
        {"Litter_ID":"LIT-Z-1","Sow_Pig_ID":"PIG-ZIGAY","Sow_Tag_Number":"Zigay",
         "Litter_Status":"Active","Farrowing_Date":"2026-07-10","Wean_Date":"2026-08-10"},
        {"Litter_ID":"LIT-Z-2","Sow_Pig_ID":"PIG-ZIGAY","Sow_Tag_Number":"Zigay",
         "Litter_Status":"Active","Farrowing_Date":"2026-07-10","Wean_Date":"2026-08-10"},
    ]


def test_teena_overdue_and_zigay_conflict_are_canonical_watchers():
    value=build_litter_watch_result(litter_rows(),now=NOW)
    titles={row.title for row in value.work_items}
    assert "Weaning overdue — Teena" in titles
    assert "Current-litter conflict — Zigay" in titles
    teena=next(row for row in value.work_items if "Teena" in row.title)
    assert "4 days overdue" in teena.why and teena.authority is Authority.OWNER_DECISION
    zigay=next(row for row in value.work_items if row.title=="Current-litter conflict — Zigay")
    assert zigay.authority is Authority.READ_ONLY and not zigay.genuine_question


def test_completed_weaning_is_not_presented():
    rows=litter_rows();rows[0]["Litter_Status"]="Weaned";rows[0]["Weaned_Count"]=9
    value=build_litter_watch_result(rows,now=NOW)
    assert all("Teena" not in row.title for row in value.work_items)


def test_sale_watcher_surfaces_today_readiness_and_suppresses_closed_settled_sale():
    value=build_sale_watch_result([{
        "sale_id":"SALE-TODAY","sale_date":"2026-08-10","sale_status":"in_progress",
        "payment_status":"pending","item_count":1,"external_reference":"",
    },{
        "sale_id":"SALE-CLOSED","sale_date":"2026-08-10","sale_status":"completed",
        "payment_status":"paid","item_count":1,"external_reference":"INV-1",
    }],now=NOW)
    assert len(value.work_items)==1
    task=value.work_items[0]
    assert task.dedupe_key=="sale:SALE-TODAY" and task.title=="Payment — Farm sale"
    assert "/sales/transactions/SALE-TODAY" in build_daily_management_packet(
        [value],now=NOW)["answer"]
    assert "Review payment evidence; preview only first" in task.next_action
    assert "Record" not in task.next_action
    assert task.authority is Authority.OWNER_DECISION


@pytest.mark.parametrize("payment_status", ["Not_Applicable", "not applicable"])
def test_completed_charity_sale_with_no_payment_required_is_retired(payment_status):
    value = build_sale_watch_result([{
        "sale_id": "SALE-CHARITY", "sale_date": "2026-08-10",
        "sale_status": "Completed", "payment_status": payment_status,
        "sale_stream": "Charity", "item_count": 1,
        "external_reference": "CHARITY-ACK-1",
    }], now=NOW)
    assert value.work_items == ()


def test_non_charity_unpaid_completed_sale_keeps_payment_control():
    value = build_sale_watch_result([{
        "sale_id": "SALE-NORMAL", "sale_date": "2026-08-10",
        "sale_status": "Completed", "payment_status": "Unpaid",
        "sale_stream": "Private sale", "item_count": 1,
        "external_reference": "INV-2",
    }], now=NOW)
    assert len(value.work_items) == 1
    assert "payment/settlement follow-up" in value.work_items[0].why


def test_maximum_three_priorities_retains_watch_and_one_question():
    items=[item(f"I-{index}",f"Task {index}",WorkState.URGENT if index<2 else WorkState.PLANNED,
        100-index,"One grouped question?" if index==0 else "") for index in range(7)]
    packet=build_daily_management_packet([result(items=items)],now=NOW)
    assert len(packet["priorities"])==3 and len(packet["watch"])==3
    assert len(packet["all_tasks"])==7 and packet["question"]=="One grouped question?"
    assert packet["answer"].count("<b>ONE QUESTION</b>")==1


def test_semantic_manager_may_rank_supported_ids_but_cannot_invent_or_omit_work():
    items=[item("ONE","One"),item("TWO","Two"),item("THREE","Three")]
    ranked=build_daily_management_packet([result(items=items)],now=NOW,
        semantic_prioritizer=lambda rows,**_kwargs:["THREE","ONE","TWO"])
    assert [row.item_id for row in ranked["priorities"]]==["THREE","ONE","TWO"]
    rejected=build_daily_management_packet([result(items=items)],now=NOW,
        semantic_prioritizer=lambda rows,**_kwargs:["INVENTED"])
    assert [row.item_id for row in rejected["priorities"]]==["ONE","THREE","TWO"]


def test_agent_owned_reconciliation_is_not_presented_as_owner_work_or_raw_polling():
    rows = [
        item("MORTALITY", "Mortality follow-up — Pig 126", WorkState.URGENT),
        item("ROOTLINE", "Irrigation: Checking safely", WorkState.PLANNED),
        replace(item("WEIGHTS", "Weighing: 0 of 75 recorded", WorkState.WAITING_EVIDENCE),
                next_action="Reconcile tags " + ", ".join(str(value) for value in range(1, 76))),
    ]
    answer = build_daily_management_packet([result(items=rows)], now=NOW)["answer"]
    assert answer == ""
    assert "ACTION NEEDED" not in answer
    assert "Reconcile tags" not in answer
    assert "within 15 minutes" not in answer


def test_internal_only_natural_cycle_records_tasks_but_sends_nothing():
    state = store(); deliveries = []
    rows = [item("MORTALITY", "Mortality follow-up â€” PIG-2026-3EE5", WorkState.URGENT),
        item("ROOTLINE", "Irrigation B, C: Checking safely", WorkState.PLANNED),
        replace(item("WEIGHTS", "Weighing: 0 of 75 recorded", WorkState.WAITING_EVIDENCE),
                metadata={"routine_weekly_weighing": True})]
    outcome = run_daily_farm_manager(owner_user_id="42", chat_id="42",
        specialist_results=[result(items=rows)], litter_rows=[], now=NOW, store=state,
        deliver=lambda *_args, **_kwargs: deliveries.append(1))
    assert outcome["status"] == "daily_manager_internal_work_silent"
    assert outcome["task_count"] == 3
    assert outcome["telegram_sends"] == 0 and deliveries == []


def test_exact_owner_decision_is_the_only_action_section():
    protected = replace(item("SALE", "Payment evidence", WorkState.DUE_TODAY),
                        authority=Authority.OWNER_DECISION,
                        next_action="Review the protected preview.")
    automatic = item("ROOTLINE", "Irrigation: Checking safely")
    answer = build_daily_management_packet([result(items=[protected, automatic])],
                                           now=NOW)["answer"]
    assert "ACTION NEEDED" in answer
    assert "Review the protected preview." in answer
    assert "OOM SAKKIE IS CHECKING AUTOMATICALLY" not in answer
    assert "No action required from you." not in answer


@pytest.mark.parametrize("authority", sorted(PROTECTED_AUTHORITIES, key=lambda value: value.value))
def test_every_protected_authority_remains_owner_visible(authority):
    protected = replace(item("PROTECTED", "Governed action", WorkState.DUE_TODAY),
                        authority=authority, next_action="Review the exact governed action.")
    answer = build_daily_management_packet([result(items=[protected])], now=NOW)["answer"]
    assert "ACTION NEEDED" in answer
    assert "Review the exact governed action." in answer
    assert "No action required from you." not in answer


def test_exact_ready_physical_work_remains_owner_visible():
    physical = replace(item("WEIGH-PIG", "Weigh Pig 146 now", WorkState.DUE_TODAY),
                       authority=Authority.ADVISORY,
                       metadata={"physical_work_ready": True})
    answer = build_daily_management_packet([result(items=[physical])], now=NOW)["answer"]
    assert "ACTION NEEDED" in answer and "Weigh Pig 146 now" in answer
    assert "No action required from you." not in answer


def test_automatic_reassessment_clock_does_not_create_a_new_owner_brief():
    first = item("ROOTLINE", "Irrigation: Checking safely")
    later = replace(first, next_action="ROOTLINE will reassess automatically around 10:46")
    earlier = replace(first, next_action="ROOTLINE will reassess automatically around 09:47")
    assert build_daily_management_packet([result(items=[earlier])], now=NOW)[
        "material_digest"] == build_daily_management_packet([result(items=[later])], now=NOW)[
            "material_digest"]


def test_changed_owner_action_remains_material():
    first = replace(item("SALE", "Payment", WorkState.DUE_TODAY),
                    authority=Authority.OWNER_DECISION, next_action="Review preview A")
    second = replace(first, next_action="Review preview B")
    assert build_daily_management_packet([result(items=[first])], now=NOW)[
        "material_digest"] != build_daily_management_packet([result(items=[second])], now=NOW)[
            "material_digest"]


def test_scheduler_daily_delivery_and_unchanged_replay_are_exact_once():
    state=store(); deliveries=[]
    def deliver(parsed,outcome,**kwargs):
        deliveries.append((parsed,outcome,kwargs))
        return {"success":True,"telegram_message_id":"4000","telegram_sends":1,
                "telegram_edits":0}
    first=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[item("R-1","Rain Hold")])],
        litter_rows=litter_rows(),deliver=deliver,store=state,now=NOW)
    replay=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[item("R-1","Rain Hold")])],
        litter_rows=litter_rows(),deliver=deliver,store=state,now=NOW)
    assert first["status"]=="daily_manager_presented" and first["telegram_sends"]==1
    assert replay["status"]=="daily_manager_unchanged_silent"
    assert replay["telegram_sends"]==0 and replay["telegram_edits"]==0
    assert len(deliveries)==1 and first["hardware_commands"]==0


def test_before_morning_boundary_is_silent_and_durably_due():
    value=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[],litter_rows=[],deliver=lambda *_a,**_k:None,
        store=store(),now=datetime(2026,8,10,4,44,tzinfo=timezone.utc))
    assert value["status"]=="daily_manager_not_due" and value["telegram_sends"]==0


def test_afrikaans_uses_same_evidence_and_authority():
    packet=build_daily_management_packet([result(items=[item("R-1","Reën hou besproeiing")])],
        now=NOW,language="af")
    assert packet["answer"] == ""
    assert packet["all_tasks"][0]["authority"]=="read_only"


def test_provider_ambiguity_is_quarantined_without_retry():
    state=store(); calls=[]
    def ambiguous(*args,**kwargs):
        calls.append(1);return {"success":False,"status":"provider_ambiguous",
                                "telegram_sends":0,"telegram_edits":0}
    first=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[replace(item("R-1","Rain Hold"), authority=Authority.OWNER_DECISION)])],litter_rows=[],
        deliver=ambiguous,store=state,now=NOW)
    replay=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[replace(item("R-1","Rain Hold"), authority=Authority.OWNER_DECISION)])],litter_rows=[],
        deliver=ambiguous,store=state,now=NOW)
    assert first["status"]=="daily_manager_delivery_ambiguous"
    assert replay["status"]=="daily_manager_replay_suppressed" and len(calls)==1


def test_material_refresh_replaces_brief_instead_of_editing_or_acknowledging():
    state=store(); replacements=[]
    def deliver(*_args,**_kwargs):
        return {"success":True,"telegram_message_id":"4000","telegram_sends":1}
    first=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[replace(item("R-1","Old current work"), authority=Authority.OWNER_DECISION)])],
        litter_rows=[],deliver=deliver,store=state,now=NOW)
    def replace_delivery(parsed,outcome,**kwargs):
        replacements.append((parsed,outcome,kwargs))
        return {"success":True,"status":"brief_replaced",
            "telegram_message_id":"4001","telegram_sends":1,"telegram_deletes":1}
    refreshed=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[replace(item("R-2","New current work"), authority=Authority.OWNER_DECISION)])],
        litter_rows=[],deliver=lambda *_a,**_k:pytest.fail("must not edit old brief"),
        replace_brief=replace_delivery,store=state,now=NOW)
    assert first["telegram_message_id"] == "4000"
    assert refreshed["status"] == "daily_manager_presented"
    assert refreshed["telegram_message_id"] == "4001"
    assert len(replacements) == 1
    assert replacements[0][2]["previous_message_id"] == "4000"
    assert replacements[0][1]["rolling_brief_replacement"] is True


def test_daily_projection_and_provider_claims_are_cross_owner_isolated():
    state=store(); sends=[]
    def deliver(parsed,_outcome,**kwargs):
        sends.append((parsed["telegram_user_id"],kwargs["mission_id"],kwargs["card_mission_id"]))
        return {"success":True,"telegram_message_id":str(5000+len(sends)),
            "telegram_sends":1}
    for owner in ("42","84"):
        value=run_daily_farm_manager(owner_user_id=owner,chat_id=owner,
                specialist_results=[result(items=[replace(item("R-1","Current work"), authority=Authority.OWNER_DECISION)])],
            litter_rows=[],deliver=deliver,store=state,now=NOW)
        assert value["status"] == "daily_manager_presented"
    assert len(sends) == 2 and sends[0][1] != sends[1][1]
    assert sends[0][2] != sends[1][2]
    assert all(":OWNER:" in row[2] for row in sends)


def test_herdmaster_reassesses_only_exact_current_question_from_owner_evidence():
    current=result(name="herdmaster",items=[item("H-1","Welfare",question="Are they eating?",
        specialist="herdmaster")])
    receipt={"task_id":"H-1","dedupe_key":"H-1","domain":"herd",
        "owner_evidence":"They are eating.",
        "accumulated_semantic_facts":{"observation":"They are eating."}}
    reconciled=reconcile_manager_question_answer(current,receipt)
    stale=reconcile_manager_question_answer(current,{**receipt,"task_id":"OLD"})
    assert reconciled.work_items[0].genuine_question==""
    assert reconciled.result_id==current.result_id
    assert stale == current and current.work_items[0].genuine_question=="Are they eating?"


def test_prior_daily_receipt_retires_same_durable_welfare_question_without_closing_case():
    current=result(name="herdmaster",items=[item("NEW-DIGEST:PRINCE","Prince welfare",
        question="Is Prince standing and drinking now?",specialist="herdmaster")])
    receipt={"task_id":"OLD-DIGEST:PRINCE","dedupe_key":"NEW-DIGEST:PRINCE",
        "domain":"herd","owner_evidence":"Prince is standing and drinking.",
        "accumulated_semantic_facts":{"observation":"Prince is standing and drinking."},
        "durable_concern_receipt":True}
    reconciled=reconcile_manager_question_answer(current,receipt)
    assert reconciled.work_items[0].genuine_question==""
    assert reconciled.work_items[0].state==current.work_items[0].state
    assert reconciled.work_items[0].metadata==current.work_items[0].metadata


def test_actual_delivery_boundary_preserves_complete_en_af_brief_without_mixed_language():
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    en_item=item("PRINCE-WELFARE","Prince welfare update",state=WorkState.URGENT,
        question="Is Prince standing and drinking now?",specialist="herdmaster")
    af_item=replace(en_item,title="Prince se welstandsopdatering",
        why="Kanonieke plaasbewyse vereis 'n huidige waarneming.",
        next_action="Bevestig of Prince nou staan en water drink.",
        genuine_question="Staan Prince nou en drink hy water?")
    packets = {"42": build_daily_management_packet([result("herdmaster",[en_item])],
                   now=NOW,language="en"),
               "77": build_daily_management_packet([result("herdmaster",[af_item])],
                   now=NOW,language="af")}
    visible = {}
    for user, language in (("42","en"),("77","af")):
        events=[]
        def event_store(action, identity, payload):
            if action == "load": return list(events)
            created = not any(row.get("event_id") == identity for row in events)
            if created: events.append(dict(payload))
            return {"success":True,"created":created}
        def sender(_chat,text):
            visible[user]=text
            return {"success":True,"telegram_message_id":"card-"+user}
        parsed={"telegram_user_id":user,"telegram_chat_id":user,
            "telegram_chat_type":"private","output_language":language,
            "provider_message_id":"scheduled:"+user,
            "provider_timestamp":NOW.isoformat(),"text":"Daily Farm Manager"}
        packet=packets[user]
        outcome={"success":True,"status":"daily_farm_manager_ready",
            "answer":packet["answer"],"recipient_render_contract":"specialist_structured_recipient_v1",
            "recipient_language":language,"writes_farm_data":False}
        delivered=deliver_family_result(parsed,outcome,specialist="OOM_SAKKIE",
            mission_id="BRIEF-"+user,card_mission_id="BRIEF-CARD-"+user,
            event_store=event_store,sender=sender)
        assert delivered["success"] is True and delivered["telegram_sends"] == 1
    assert "TODAY'S FARM PLAN" in visible["42"] and "ONE QUESTION" in visible["42"]
    assert "Prince welfare update" in visible["42"] and "standing and drinking" in visible["42"]
    assert "VANDAG SE PLAASPLAN" in visible["77"] and "EEN VRAAG" in visible["77"]
    assert "welstandsopdatering" in visible["77"] and "Staan Prince" in visible["77"]
    assert not any(word in visible["77"].casefold() for word in
                   ("today's", "one question", "supported action", "next check"))
