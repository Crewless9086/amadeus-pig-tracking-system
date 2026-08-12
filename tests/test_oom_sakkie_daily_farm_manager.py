from datetime import datetime, timezone

from modules.oom_sakkie.daily_farm_manager import (
    build_daily_management_packet, build_litter_watch_result, build_sale_watch_result,
    run_daily_farm_manager)
from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState)

NOW=datetime(2026,8,10,5,0,tzinfo=timezone.utc)


def result(name="rootline",items=()):
    return SpecialistResult(name,name+"-1",NOW,SpecialistAvailability.AVAILABLE,
        work_items=tuple(items))


def item(identity,title,state=WorkState.PLANNED,value=50,question=""):
    provenance=Provenance("rootline","rootline-1",("canonical",),NOW,1.0)
    return SpecialistWorkItem(item_id=identity,dedupe_key=identity,domain="water_energy",
        title=title,why="Supported reason",next_action="Supported action",assignee="charl",
        state=state,authority=Authority.READ_ONLY,provenance=provenance,
        business_value=value,genuine_question=question,question_for="charl" if question else "")


def store():
    rows={}
    def effect(action,identity,payload):
        if action=="load_daily":
            candidates=[row for row in rows.values() if row.get("daily_identity")==identity
                        and row.get("status") in {"presented","unchanged","provider_ambiguous"}]
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
    assert "/sales/slaughter?update_sale=SALE-TODAY&amp;payment_only=1" in build_daily_management_packet(
        [value],now=NOW)["answer"]
    assert task.authority is Authority.OWNER_DECISION


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
    assert "VANDAG SE PLAASPLAN" in packet["answer"]
    assert packet["all_tasks"][0]["authority"]=="read_only"


def test_provider_ambiguity_is_quarantined_without_retry():
    state=store(); calls=[]
    def ambiguous(*args,**kwargs):
        calls.append(1);return {"success":False,"status":"provider_ambiguous",
                                "telegram_sends":0,"telegram_edits":0}
    first=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[item("R-1","Rain Hold")])],litter_rows=[],
        deliver=ambiguous,store=state,now=NOW)
    replay=run_daily_farm_manager(owner_user_id="42",chat_id="42",
        specialist_results=[result(items=[item("R-1","Rain Hold")])],litter_rows=[],
        deliver=ambiguous,store=state,now=NOW)
    assert first["status"]=="daily_manager_delivery_ambiguous"
    assert replay["status"]=="daily_manager_replay_suppressed" and len(calls)==1
