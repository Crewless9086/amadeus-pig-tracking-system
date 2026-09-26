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


@pytest.mark.parametrize("language", ["af", "en"])
@pytest.mark.parametrize("watchers", ["weaning", "payment", "both", "empty"])
def test_canonical_morning_briefs_cross_family_delivery_once(language, watchers):
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    litters = [{"Litter_ID": "LOCAL-LITTER", "Sow_Pig_ID": "LOCAL-SOW",
        "Sow_Tag_Number": "X100", "Litter_Status": "Active",
        "Wean_Date": "2026-08-09", "Weaned_Count": None}]
    sales = [{"sale_id": "LOCAL-SALE", "sale_date": "2026-08-10",
        "sale_status": "pending", "payment_status": "pending",
        "buyer_name": "Voorbeeld", "net_total": 100, "item_count": 1}]
    daily_store = store()
    events, sends = [], []
    def event_store(action, identity, payload):
        if action == "load":
            return list(events)
        events.append(dict(payload))
        return {"success": True, "created": True}
    def sender(chat, text):
        sends.append((chat, text))
        return {"success": True, "telegram_message_id": "local-card"}
    def deliver(parsed, value, **kwargs):
        return deliver_family_result(parsed, value, event_store=event_store,
            sender=sender, **kwargs)
    kwargs = dict(owner_user_id="77", chat_id="77", specialist_results=[], now=NOW,
        litter_rows=litters if watchers in {"weaning", "both"} else [],
        sale_rows=sales if watchers in {"payment", "both"} else [],
        language=language, deliver=deliver, store=daily_store,
        semantic_prioritizer=lambda rows, **_kwargs: list(rows))
    first = run_daily_farm_manager(**kwargs)
    second = run_daily_farm_manager(**kwargs)
    assert first["status"] == "daily_manager_presented" and first["success"] is True
    assert second["status"] == "daily_manager_unchanged_silent"
    assert len(sends) == 1 and events
    assert first["writes_farm_data"] is False and first["hardware_commands"] == 0
    if language == "af" and watchers != "empty":
        assert "AKSIE NODIG" in sends[0][1]


@pytest.mark.parametrize("answer,accepted", [
    ("<b>AKSIE NODIG</b>\nBetaal die faktuur.", True),
    ("<b>Aksie&nbsp;nodig!</b>\nBetaal die faktuur.", True),
    ("<b>AKSIE NODIG</b>\nPlease confirm the payment.", False),
    ("<b>AKSIE NODIG</b>\n<b>Please</b> confirm&#32;the payment.", False),
])
def test_morning_language_guard_reads_visible_html_and_still_rejects_english(answer, accepted):
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    sends, events = [], []
    def event_store(action, identity, payload):
        if action == "load":
            return list(events)
        events.append(payload)
        return {"success": True, "created": True}
    outcome = deliver_family_result(
        {"telegram_user_id": "77", "telegram_chat_id": "77", "telegram_chat_type": "private",
         "provider_message_id": "local-visible-text", "output_language": "af"},
        {"success": True, "status": "daily_farm_manager_ready", "answer": answer,
         "recipient_render_contract": "specialist_structured_recipient_v1", "recipient_language": "af"},
        specialist="OOM_SAKKIE", event_store=event_store,
        sender=lambda chat, text: sends.append(text) or {"success": True, "telegram_message_id": "local-card"})
    assert outcome["success"] is accepted
    assert len(sends) == int(accepted)
    if not accepted:
        assert outcome["status"] == "recipient_language_render_unrecognized" and not events


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
        if action in {"load_notification_state", "load_notification_failure"}:
            return notification_state(rows.values(), identity, payload)
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


def test_daily_order_is_deterministic_and_never_calls_injected_ranker():
    items=[item("ONE","One"),item("TWO","Two"),item("THREE","Three")]
    ranked=build_daily_management_packet([result(items=items)],now=NOW,
        semantic_prioritizer=lambda *_args,**_kwargs: pytest.fail("routine model invocation"))
    assert [row.item_id for row in ranked["priorities"]]==["ONE","THREE","TWO"]
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
    assert "OOM SAKKIE IS CHECKING AUTOMATICALLY" in answer
    assert "Mortality follow-up" in answer
    assert "ACTION NEEDED" not in answer
    assert "Reconcile tags" not in answer
    assert "within 15 minutes" not in answer


def test_internal_only_morning_cycle_sends_one_bounded_summary():
    state = store(); deliveries = []
    rows = [item("MORTALITY", "Mortality follow-up â€” PIG-2026-3EE5", WorkState.URGENT),
        item("ROOTLINE", "Irrigation B, C: Checking safely", WorkState.PLANNED),
        replace(item("WEIGHTS", "Weighing: 0 of 75 recorded", WorkState.WAITING_EVIDENCE),
                metadata={"routine_weekly_weighing": True})]
    outcome = run_daily_farm_manager(owner_user_id="42", chat_id="42",
        specialist_results=[result(items=rows)], litter_rows=[], now=NOW, store=state,
        deliver=lambda *_args, **_kwargs: {"success": True, "telegram_message_id": "99",
                                            "telegram_sends": 1})
    assert outcome["status"] == "daily_manager_presented"
    assert outcome["task_count"] == 3
    assert outcome["telegram_sends"] == 1


def test_exact_owner_decision_is_the_only_action_section():
    protected = replace(item("SALE", "Payment evidence", WorkState.DUE_TODAY),
                        authority=Authority.OWNER_DECISION,
                        next_action="Review the protected preview.")
    automatic = item("ROOTLINE", "Irrigation: Checking safely")
    answer = build_daily_management_packet([result(items=[protected, automatic])],
                                           now=NOW)["answer"]
    assert "ACTION NEEDED" in answer
    assert "Review the protected preview." in answer
    assert "OOM SAKKIE IS CHECKING AUTOMATICALLY" in answer
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
        from hashlib import sha256
        claim = state.rows[kwargs["mission_id"]]
        assert claim["owner_user_id"] == claim["chat_id"] == "42"
        assert claim["card_mission_id"] == kwargs["card_mission_id"]
        assert "question" in claim and "question_binding" in claim
        assert claim["answer_sha256"] == sha256(outcome["answer"].strip().encode()).hexdigest()
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
    assert "OOM SAKKIE KONTROLEER OUTOMATIES" in packet["answer"]
    assert "Re" in packet["answer"]
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
    assert replay["status"]=="daily_manager_failure_backoff" and len(calls)==1


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


def _daily_family_transition_harness(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from modules.oom_sakkie import daily_farm_manager as daily, family_message_lifecycle as family
    state = SimpleNamespace(daily={}, family={}, sends=[], deletes=[], calls=[],
        fail_daily=None, fail_family=None, fail_task=False, ambiguous=False, crash_cleanup=False)
    def daily_store(action, identity, payload):
        if action in {"load_notification_state", "load_notification_failure"}:
            return notification_state(state.daily.values(), identity, payload)
        if action == "load_daily":
            rows = [row for row in state.daily.values()
                if row.get("daily_identity") == identity
                and row.get("owner_user_id") == payload["owner_user_id"]
                and row.get("chat_id") == payload["chat_id"]
                and row.get("status") in {"presented", "unchanged", "provider_ambiguous"}]
            return dict(rows[-1]) if rows else None
        if action == "load_answered_questions":
            return ()
        if action == "record_daily" and payload.get("status") == "presented" and state.fail_daily:
            failure, state.fail_daily = state.fail_daily, None
            if failure == "raise":
                raise RuntimeError("simulated process stop before daily receipt")
            return {"success": False, "created": False}
        if action == "record_task" and payload.get("lifecycle_state") == "presented" and state.fail_task:
            state.fail_task = False
            return {"success": False, "created": False}
        created = identity not in state.daily
        if created:
            state.daily[identity] = {**payload, "event_id": identity, "event_kind": action}
        return {"success": True, "created": created}
    def family_store(action, identity, payload):
        if action == "load":
            return [dict(row) for row in state.family.values() if row["card_mission_id"] == identity]
        if state.fail_family == payload.get("state"):
            state.fail_family = None
            return {"success": False, "created": False}
        created = identity not in state.family
        if created:
            state.family[identity] = dict(payload)
        return {"success": True, "created": created}
    def sender(_chat, _text):
        state.sends.append(str(8000 + len(state.sends)))
        if state.ambiguous:
            return {"success": False, "status": "provider_ambiguous"}
        return {"success": True, "telegram_message_id": state.sends[-1]}
    def deleter(_chat, message_id):
        if state.crash_cleanup:
            state.crash_cleanup = False
            raise RuntimeError("simulated process stop before cleanup")
        state.deletes.append(message_id)
        return {"success": True}
    def deliver(parsed, value, **kwargs):
        outcome = family.deliver_family_result(parsed, value, event_store=family_store, sender=sender, **kwargs)
        state.calls.append(outcome)
        return outcome
    def replace_brief(parsed, value, **kwargs):
        outcome = family.replace_current_brief(parsed, value, event_store=family_store,
            sender=sender, deleter=deleter, projection_lock=lambda _: nullcontext(), **kwargs)
        state.calls.append(outcome)
        return outcome
    # Crucial: production's duplicate-claim branch compares the default store
    # function identity. Passing only a custom store would mask this failure.
    monkeypatch.setattr(daily, "daily_farm_manager_store", daily_store)
    def run(label, *, now=NOW):
        work = replace(item("CURRENT", "Synthetic current work " + label,
            state=WorkState.URGENT, specialist="herdmaster"),
            authority=Authority.OWNER_DECISION)
        return daily.run_daily_farm_manager(owner_user_id="42", chat_id="42",
            specialist_results=[result(name="herdmaster", items=[work])], litter_rows=[],
            now=now, language="en", deliver=deliver, replace_brief=replace_brief,
            semantic_prioritizer=lambda rows, **_: list(rows))
    state.run = run
    return state


@pytest.mark.parametrize("labels", [("A", "B", "A", "B"), ("A", "B", "C", "B"),
    ("A", "B", "A", "B", "A", "B")])
def test_daily_material_recurrence_does_not_realert_already_notified_facts(monkeypatch, labels):
    state = _daily_family_transition_harness(monkeypatch)
    seen = set()
    state.latest = None
    for label in labels:
        outcome = state.run(label)
        assert outcome["success"]
        assert outcome["status"] == ("daily_manager_presented" if label not in seen else
            "daily_manager_unchanged_silent" if label == state.latest else "daily_manager_routine_coalesced")
        if label not in seen:
            state.latest = label
        seen.add(label)
    assert len(state.sends) == len(seen) and len(state.deletes) == len(seen) - 1



@pytest.mark.parametrize("interruption", ["daily_reject", "daily_raise", "cleanup_raise", "supersession_reject"])
def test_daily_confirmed_transition_recovers_receipts_without_repeating_provider_effect(monkeypatch, interruption):
    state = _daily_family_transition_harness(monkeypatch)
    assert state.run("A")["success"]
    if interruption.startswith("daily"):
        state.fail_daily = interruption.removeprefix("daily_")
    elif interruption == "cleanup_raise":
        state.crash_cleanup = True
    else:
        state.fail_family = "brief_generation_superseded"
    if interruption.endswith("raise"):
        with pytest.raises(RuntimeError, match="simulated process stop"):
            state.run("B")
    else:
        failed = state.run("B")
        assert not failed["success"]
    old_rows = {key: dict(value) for key, value in state.daily.items()}
    sends, deletes = len(state.sends), len(state.deletes)
    recovered = state.run("B")
    assert recovered["success"] and recovered["status"] == "daily_manager_presented"
    assert recovered["telegram_sends"] == recovered["telegram_edits"] == 0
    assert len(state.sends) == sends == 2
    assert len(state.deletes) == deletes + int(interruption == "supersession_reject")
    assert all(state.daily[key] == value for key, value in old_rows.items())
    assert any(key.endswith(":PRESENTED") and row.get("telegram_message_id") == recovered["telegram_message_id"]
        for key, row in state.daily.items())
    assert state.run("B")["status"] == "daily_manager_unchanged_silent"


def test_daily_replacement_ambiguity_retains_reason_and_never_retries_on_restart(monkeypatch):
    state = _daily_family_transition_harness(monkeypatch)
    assert state.run("A")["success"]
    state.ambiguous = True
    first = state.run("B")
    state.ambiguous = False
    replay = state.run("B")
    assert first["status"] == "daily_manager_delivery_ambiguous"
    assert replay["status"] == "daily_manager_failure_backoff"
    assert first["delivery_failure_reason"] == "brief_replacement_delivery_ambiguous"
    assert replay["delivery_failure_reason"] == "replacement_ambiguous"
    assert len(state.sends) == 2 and state.deletes == []
    assert not first.get("delivery_definitely_not_sent") and not replay.get("delivery_definitely_not_sent")
    assert any(row.get("status") == "replacement_ambiguous" for row in state.daily.values())


def test_daily_zero_send_recovery_receipt_failure_is_not_reported_as_delivery(monkeypatch):
    state = _daily_family_transition_harness(monkeypatch)
    state.run("A")
    state.fail_family = "brief_generation_superseded"
    assert not state.run("B")["success"]
    state.fail_daily = "reject"
    recovery_failure = state.run("B")
    assert recovery_failure["status"] == "daily_manager_provider_confirmed_lifecycle_unavailable"
    assert not recovery_failure["success"] and recovery_failure["telegram_sends"] == 0
    assert len(state.sends) == 2
    assert state.run("B")["success"]
    assert len(state.sends) == 2


def test_daily_presented_task_receipt_failure_recovers_without_false_completion(monkeypatch):
    state = _daily_family_transition_harness(monkeypatch)
    assert state.run("A")["success"]
    state.fail_task = True
    failed = state.run("B")
    assert failed["status"] == "daily_manager_provider_confirmed_lifecycle_unavailable"
    assert not failed["success"] and failed["telegram_message_id"]
    assert not any(row.get("status") == "presented"
        and row.get("material_digest") == failed["material_digest"] for row in state.daily.values())
    recovered = state.run("B")
    assert recovered["success"] and recovered["telegram_sends"] == 0
    assert len(state.sends) == 2 and len(state.deletes) == 1
    assert state.run("B")["status"] == "daily_manager_unchanged_silent"


def test_daily_and_family_transition_ids_survive_real_audit_parameter_bounds(monkeypatch):
    from modules.sales.sam_live_stock_launch_control import _review_event_params
    state = _daily_family_transition_harness(monkeypatch)
    for label in ("A", "B", "A", "B", "A", "B"):
        assert state.run(label)["success"]
    for identity in [*state.daily, *state.family]:
        assert len(identity) <= 120
        assert _review_event_params({"review_event_id": identity})["review_event_id"] == identity
    assert all("-GENERATION-" not in key for key in state.family if "TRANSITION-V2" in key)


def test_changed_packet_after_missing_daily_receipt_is_contained_without_stale_advance(monkeypatch):
    state = _daily_family_transition_harness(monkeypatch)
    assert state.run("A")["success"]
    state.fail_daily = "reject"
    assert not state.run("B")["success"]
    before = len(state.sends), len(state.deletes)
    changed = state.run("C")
    assert not changed["success"]
    assert changed["delivery_failure_reason"] == "brief_replacement_prior_binding_unproven"
    assert (len(state.sends), len(state.deletes)) == before
    assert state.run("B")["success"]
    from datetime import timedelta
    assert state.run("C")["status"] == "daily_manager_failure_backoff"
    assert state.run("C", now=NOW + timedelta(minutes=31))["success"]


def notification_state(values, identity, binding):
    rows = [row for row in values if row.get("owner_user_id") == binding.get("owner_user_id")
            and row.get("chat_id") == binding.get("chat_id")]
    presented = [row for row in rows if row.get("status") == "presented"]
    failures = [row for row in rows if row.get("status") == "notification_backoff"
                and row.get("daily_identity") == identity
                and row.get("material_digest") == binding.get("material_digest")]
    return {"success": True, "notified_keys": sorted({key for row in presented
        for key in row.get("notification_keys", [])}),
        "last_presented": presented[-1] if presented else {},
        **({"retry_after": failures[-1]["retry_after"],
            "failure_status": failures[-1]["failure_status"]} if failures else {})}


@pytest.mark.parametrize("language", ["en", "af"])
def test_real_daily_urgent_change_is_once_known_question_silent_and_next_day_due(monkeypatch, language):
    from datetime import timedelta
    from modules.oom_sakkie import daily_farm_manager as daily
    from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery
    memory = MemoryDelivery(monkeypatch)
    def forbidden(*a, **k): pytest.fail("routine model called")
    monkeypatch.setattr(daily, "_semantic_prioritize", forbidden)
    question = "Staan die vark nou?" if language == "af" else "Is the pig standing now?"
    base = replace(item("PIG-CASE", "Die vark se saak" if language == "af" else "Pig case",
        question=question), why="Die vark is veilig." if language == "af" else "Pig is stable.",
        next_action=question, metadata={"notification_decision_identity": "CASE-1"})
    def run(work, at=NOW):
        return daily.run_daily_farm_manager(owner_user_id="42", chat_id="42",
            specialist_results=[SpecialistResult("rootline", "rootline-1", at,
                SpecialistAvailability.AVAILABLE, work_items=(work,))], litter_rows=[], now=at,
            language=language, deliver=memory.deliver, replace_brief=memory.replace,
            semantic_prioritizer=forbidden)
    assert run(base)["status"] == "daily_manager_presented"
    wording = replace(base, genuine_question=("Is die vark nog regop?" if language == "af" else
                                              "Can the pig still stand?"), next_action="changed wording")
    assert run(wording)["status"] == "daily_manager_routine_coalesced"
    urgent = replace(base, state=WorkState.URGENT,
        why="Die vark staan nie en het dringend hulp nodig." if language == "af" else "Pig cannot stand; urgent help needed.")
    assert run(urgent)["status"] == "daily_manager_presented"
    assert len(memory.sends) == 2 and question not in memory.sends[-1][1]
    assert "earlier decision" in memory.sends[-1][1] if language == "en" else "vorige besluit" in memory.sends[-1][1]
    clock_only = replace(urgent, due_at=NOW + timedelta(minutes=5),
        next_action="Reassess at 12:35", provenance=replace(urgent.provenance,
        observed_at=NOW + timedelta(minutes=5)))
    assert run(clock_only, NOW + timedelta(minutes=5))["status"] in {
        "daily_manager_routine_coalesced", "daily_manager_unchanged_silent"}
    assert len(memory.sends) == 2
    assert run(urgent, NOW + timedelta(days=1, hours=6))["status"] == "daily_manager_presented"
    assert len(memory.sends) == 3 and question not in memory.sends[-1][1]
    assert all(row["writes_farm_data"] is False for row in [run(urgent, NOW + timedelta(days=1, hours=6))])


def test_new_canonical_decision_reopens_same_concern_without_wording_trigger(monkeypatch):
    from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery
    memory = MemoryDelivery(monkeypatch)
    work = replace(item("SAME", "Same pig", question="What happened?"),
                   metadata={"notification_decision_identity": "MATING-1"})
    def run(row):
        return run_daily_farm_manager(owner_user_id="42", chat_id="42", specialist_results=[result(items=[row])],
            litter_rows=[], now=NOW, deliver=memory.deliver, replace_brief=memory.replace)
    assert run(work)["success"]
    assert run(replace(work, genuine_question="Tell me the outcome?"))["status"] == "daily_manager_routine_coalesced"
    assert run(replace(work, metadata={"notification_decision_identity": "MATING-2"}))["status"] == "daily_manager_presented"
    assert len(memory.sends) == 2 and "What happened?" in memory.sends[-1][1]


@pytest.mark.parametrize("count", [8, 70])
def test_unseen_urgent_items_outside_first_six_are_not_acknowledged_or_lost(monkeypatch, count):
    from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery
    memory = MemoryDelivery(monkeypatch)
    work = [item(f"URGENT-{i}", f"Urgent animal {i}", WorkState.URGENT, value=100-i) for i in range(count)]
    def run():
        return run_daily_farm_manager(owner_user_id="42", chat_id="42", specialist_results=[result(items=work)],
            litter_rows=[], now=NOW, deliver=memory.deliver, replace_brief=memory.replace)
    expected = (count + 2) // 3
    for _ in range(expected): assert run()["status"] == "daily_manager_presented"
    assert len(memory.sends) == expected
    for i in range(count): assert any(f"Urgent animal {i}" in text for _, text in memory.sends)
    assert run()["status"] in {"daily_manager_routine_coalesced", "daily_manager_unchanged_silent"}
    assert len(memory.sends) == expected


def test_same_failed_generation_backs_off_but_new_urgent_and_next_day_can_progress(monkeypatch):
    from datetime import timedelta
    from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery
    memory = MemoryDelivery(monkeypatch)
    bad = replace(item("BAD", "Die vark se saak", WorkState.URGENT),
                  why="Please confirm the animal", next_action="Die saak word nagegaan.")
    def run(work, at=NOW):
        return run_daily_farm_manager(owner_user_id="42", chat_id="42", specialist_results=[result(items=[work])],
            litter_rows=[], now=at, language="af", deliver=memory.deliver, replace_brief=memory.replace)
    assert run(bad)["status"] == "daily_manager_recipient_language_rejected"
    assert run(bad, NOW + timedelta(minutes=5))["status"] == "daily_manager_failure_backoff"
    assert len(memory.deliveries) == 1 and not memory.sends and not memory.family_rows
    assert run(bad, NOW + timedelta(minutes=31))["status"] == "daily_manager_recipient_language_rejected"
    assert run(bad, NOW + timedelta(minutes=35))["status"] == "daily_manager_failure_backoff"
    assert len(memory.deliveries) == 2
    good = replace(bad, why="Die vark het nuwe hulp nodig en staan nie.")
    assert run(good, NOW + timedelta(minutes=36))["status"] == "daily_manager_presented"
    assert len(memory.sends) == 1
    assert run(good, NOW + timedelta(days=1, hours=8))["status"] == "daily_manager_presented"
    assert len(memory.sends) == 2


@pytest.mark.parametrize("text,accepted", [
    ("<b>VANDAG SE PLAASPLAN</b>\nDie grond is nat want die reën het geval.", True),
    ("Die besproeiing loop nie want dit is nie nodig nie.", True),
    ("<b>VANDAG SE PLAASPLAN</b>\nI want water.", False),
    ("Die besproeiing is veilig. I want die water.", False),
    ("Die grond is nat want current weather is dry.", False),
    ("Die grond is nat want die reën het geval. Please confirm the action.", False),
])
def test_afrikaans_want_requires_local_clause_context_and_no_english_bypass(text, accepted):
    from modules.oom_sakkie.family_message_lifecycle import _looks_afrikaans
    assert _looks_afrikaans(text) is accepted


def test_concurrent_real_family_initial_brief_has_one_provider_effect(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from modules.oom_sakkie import daily_farm_manager as daily
    from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery
    memory = MemoryDelivery(monkeypatch)
    barrier, lock = Barrier(2), Lock()
    original_daily, original_family = memory.store_daily, memory.store_family
    def durable(action, identity, payload):
        with lock: value = original_daily(action, identity, payload)
        if action == "load_daily": barrier.wait(timeout=3)
        return value
    def family_store(action, identity, payload):
        with lock: return original_family(action, identity, payload)
    monkeypatch.setattr(daily, "daily_farm_manager_store", durable)
    memory.store_family = family_store
    def run(_):
        return daily.run_daily_farm_manager(owner_user_id="42", chat_id="42",
            specialist_results=[result(items=[item("Q", "Current work", question="Is the pig standing?")])],
            litter_rows=[], now=NOW, deliver=memory.deliver, replace_brief=memory.replace)
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(run, range(2)))
    assert len(memory.sends) == 1
    assert sum(row["telegram_sends"] for row in outcomes) == 1
    assert len([row for row in memory.family_rows.values() if row["state"] == "delivery_attempted"]) == 1
    assert all(row["writes_farm_data"] is False for row in outcomes)


def test_unpersisted_failure_backoff_is_reported_unproven():
    base = store()
    def rejecting(action, identity, payload):
        if action == "record_daily" and payload.get("status") == "notification_backoff":
            return {"success": False}
        return base(action, identity, payload)
    outcome = run_daily_farm_manager(owner_user_id="42", chat_id="42",
        specialist_results=[], litter_rows=[], now=NOW, store=rejecting,
        deliver=lambda *a, **k: {"success": False, "status": "recipient_language_render_unrecognized",
                                "delivery_definitely_not_sent": True})
    assert outcome["status"] == "daily_manager_failure_backoff_persistence_unproven"
    assert not outcome["success"] and outcome["telegram_sends"] == 0


def test_prepolicy_pending_question_exact_task_seeds_current_identity_but_new_cycle_reopens(monkeypatch):
    from tests.test_oom_sakkie_herd_morning_language import MemoryDelivery
    memory = MemoryDelivery(monkeypatch)
    work = replace(item("LEGACY-TASK", "Current pig", question="Is the pig standing?"),
                   metadata={"notification_decision_identity": "LIFECYCLE-1"})
    def run(row):
        return run_daily_farm_manager(owner_user_id="42", chat_id="42", specialist_results=[result(items=[row])],
            litter_rows=[], now=NOW, deliver=memory.deliver, replace_brief=memory.replace)
    assert run(work)["status"] == "daily_manager_presented"
    # Synthetic historical shape predates the notification keys/typed ID.
    for row in memory.daily_rows.values():
        if row.get("status") == "presented":
            row.pop("notification_keys", None)
            row["question_binding"].pop("decision_identity", None)
    changed = replace(work, why="The same pending question has refreshed supporting records.")
    assert run(changed)["status"] == "daily_manager_routine_coalesced"
    reopened = replace(changed, item_id="NEW-TASK", metadata={"notification_decision_identity": "LIFECYCLE-2"})
    assert run(reopened)["status"] == "daily_manager_presented"
    assert len(memory.sends) == 2
