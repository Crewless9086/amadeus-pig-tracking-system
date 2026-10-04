"""Shared cohort work uses canonical eligibility, not a missing weekly entry."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.pig_weights.pig_weights_service import get_pig_allocation_readiness
from modules.pig_weights.herdmaster_weighing_reconciliation import reconcile_weighing
from modules.pig_weights.herdmaster_purpose_work import build_purpose_work, load_purpose_work_snapshot
from modules.pig_weights.herdmaster_daily_manager_evidence import build_daily_manager_evidence
from modules.oom_sakkie.herd_read_queries import answer_herd_read_query
from modules.oom_sakkie.manager_case_sources import _purpose_review_candidates
from modules.oom_sakkie.general_manager_worker import normalize_candidate
from tests.test_oom_sakkie_conversation_followup import journey, interpretation
from tests.farm_model_test_support import isolated_model_budget


@pytest.fixture
def model_budget_fixture():
    scope = isolated_model_budget()
    try:
        yield
    finally:
        scope.close()

DAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def inputs(count=2, *, day=DAY, weight_day=None, kilograms=12):
    pigs, overview, weights = [], [], []
    for i in range(count):
        identity, tag = f"PIG-SYNTHETIC-{i:04d}", f"S{i:04d}"
        pigs.append({"pig_id": identity, "tag_number": tag, "pig_name": "Synthetic",
            "status": "Active", "on_farm": True, "animal_type": "Weaner", "purpose": "Unknown"})
        overview.append({"Pig_ID": identity, "Tag_Number": tag, "Status": "Active", "On_Farm": "Yes",
            "Animal_Type": "Weaner", "Purpose": "Unknown", "Sex": "Female", "Litter_ID": "COHORT-A",
            "Wean_Date": "2026-09-20", "Wean_Weight_Kg": 8, "Date_Of_Birth": "2026-08-01",
            "Current_Weight_Kg": kilograms if weight_day else 8,
            "Last_Weight_Date": (weight_day or date(2026,9,20)).isoformat(),
            "Allocation_Evidence_State": "known_unallocated"})
        if weight_day:
            weights.append({"weight_event_id": "W-"+identity, "pig_id": identity,
                "weight_date": weight_day, "weight_kg": kilograms})
    snapshot = {"overview_rows": overview, "pig_master_rows": overview, "weight_rows": [],
        "sales_rows": [], "litter_rows": [], "pen_lookup": {}, "read_progress": {"status": "complete"},
        "allocation_query_status": "known", "medical_query_status": "known"}
    allocation = get_pig_allocation_readiness(today=day, allow_sheet_fallback=False, canonical_inputs=snapshot)
    reconciliation = reconcile_weighing(pigs, {"latest_weights": weights}, analysis_date=day)
    return allocation, reconciliation, pigs


def work(*args, day=DAY, **kwargs):
    allocation, reconciliation, pigs = inputs(*args, day=day, **kwargs)
    return build_purpose_work(allocation, reconciliation, analysis_date=day), pigs


def daily(work, pigs):
    return build_daily_manager_evidence(pigs=pigs, window_weights=[], prior_weights=[],
        reconciliation_rows={}, purpose_work=work, analysis_date=DAY)


def test_real_eligibility_day13_day14_day7_weight_and_stable_case_identity():
    assert work(day=DAY-timedelta(days=1))[0]["cohorts"] == []
    due, pigs = work()
    assert due["cohorts"][0]["weighing_ids"] == [row["pig_id"] for row in pigs]
    later, _ = work(weight_day=DAY-timedelta(days=7), kilograms=Decimal("12.0"))
    assert later["cohorts"][0]["phase"] == "decision_due"
    assert later["cohorts"][0]["case_key"] == due["cohorts"][0]["case_key"]
    assert later["cohorts"][0]["material_digest"] != due["cohorts"][0]["material_digest"]
    assert work(weight_day=date(2026,9,20))[0]["cohorts"][0]["phase"] == "weight_due"


def test_time_only_read_and_row_order_do_not_change_digest_or_manager_generation():
    initial, _ = work()
    allocation, checks, _ = inputs(day=DAY+timedelta(days=3))
    allocation["pigs"].reverse(); checks["rows"].reverse()
    later = build_purpose_work(allocation, checks, analysis_date=DAY+timedelta(days=3))
    assert later == initial
    a = normalize_candidate(_purpose_review_candidates({"purpose_work": initial}, now=NOW,
        today=DAY, observed_at=NOW)[0], now=NOW)
    b = normalize_candidate(_purpose_review_candidates({"purpose_work": later}, now=NOW+timedelta(minutes=5),
        today=DAY, observed_at=NOW+timedelta(minutes=5))[0], now=NOW)
    assert a["case_id"] == b["case_id"] and a["evidence_digest"] == b["evidence_digest"]


@pytest.mark.parametrize("change", ["hold", "identity", "tag", "status", "weight", "missing"])
def test_one_blocked_member_stays_out_while_other_current_member_remains_due(change):
    allocation, checks, pigs = inputs()
    if change == "hold": checks["rows"][0]["state"] = "allocation_hold"
    elif change == "identity": checks["rows"][0]["canonical"]["pig_id"] = "OTHER"
    elif change == "tag": checks["rows"][0]["canonical"]["tag_number"] = "OTHER"
    elif change == "status": checks["rows"][0]["canonical"]["status"] = "Sold"
    elif change == "weight": checks["rows"][0].update(state="unresolved", reasons=["latest_weight_conflict"])
    else: checks["rows"].pop(0)
    group = build_purpose_work(allocation, checks, analysis_date=DAY)["cohorts"][0]
    assert group["weighing_ids"] == [pigs[1]["pig_id"]]
    assert group["blocked"][0]["pig_id"] == pigs[0]["pig_id"]
    assert group["member_ids"] == [row["pig_id"] for row in pigs]


@pytest.mark.parametrize("status,on_farm,stage,purpose", [("Sold","No","Weaner","Unknown"),
    ("Active","Yes","Sow","Unknown"),("Active","Yes","Boar","Unknown"),
    ("Active","Yes","Weaner","Breeding")])
def test_canonical_exclusions_cannot_become_physical(status,on_farm,stage,purpose):
    allocation, checks, _ = inputs()
    allocation["pigs"][0].update(status=status,on_farm=on_farm,animal_type=stage,purpose=purpose)
    group=build_purpose_work(allocation,checks,analysis_date=DAY)["cohorts"][0]
    assert group["member_ids"] == [allocation["pigs"][1]["pig_id"]]


@pytest.mark.parametrize("kilograms", [0,-1,float("nan"),float("inf"),True])
def test_invalid_qualifying_weight_never_becomes_decision(kilograms):
    allocation, checks, _ = inputs(weight_day=DAY-timedelta(days=1))
    allocation["pigs"][0]["latest_weight_kg"] = kilograms
    checks["rows"][0]["latest_weight"]["kg"] = kilograms
    group=build_purpose_work(allocation,checks,analysis_date=DAY)["cohorts"][0]
    assert group["phase"] == "held" and not group["weighing_ids"]
    assert "qualifying_weight_unproven" in group["blocked"][0]["reasons"]


@pytest.mark.parametrize("change", ["future", "wrong_date", "wrong_weight", "wrong_phase", "invalid_date"])
def test_latest_weight_date_value_and_phase_must_match_current_canonical_proof(change):
    allocation, checks, _ = inputs(weight_day=DAY-timedelta(days=1))
    row=allocation["pigs"][0]
    if change == "future": row["latest_weight_date"] = (DAY+timedelta(days=1)).isoformat()
    elif change == "wrong_date": row["latest_weight_date"] = (DAY-timedelta(days=2)).isoformat()
    elif change == "wrong_weight": row["latest_weight_kg"] = 99
    elif change == "wrong_phase": row["purpose_review_state"] = "weight_due"
    else: row["latest_weight_date"] = "not-a-date"
    group=build_purpose_work(allocation,checks,analysis_date=DAY)["cohorts"][0]
    assert group["phase"] == "held" and not group["weighing_ids"]


def test_missing_reconciliation_and_missing_allocation_are_not_false_no_work():
    allocation, _, _=inputs()
    result=build_purpose_work(allocation, {}, analysis_date=DAY)
    assert result["state"] == "unavailable" and result["cohorts"][0]["phase"] == "held"
    with pytest.raises(ValueError,match="purpose_work_evidence_unavailable"):
        _purpose_review_candidates({"purpose_work":result},now=NOW,today=DAY,observed_at=NOW)
    assert build_purpose_work({"success":False}, {}, analysis_date=DAY)["state"] == "unavailable"


def test_purpose_material_is_separate_from_historical_weekly_case_material():
    first,pigs=work()
    second,_=work(weight_day=DAY-timedelta(days=1))
    a,b=daily(first,pigs),daily(second,pigs)
    assert a["purpose_work"] != b["purpose_work"]
    assert a["material_digest"] == b["material_digest"]
    from modules.oom_sakkie.herdmaster_daily_manager_adapter import consume_daily_manager_evidence
    assert [row.dedupe_key for row in consume_daily_manager_evidence(a,observed_at=NOW).work_items] == ["herdmaster:weekly-weight-evidence"]


@pytest.mark.parametrize("language", ["en","af"])
def test_many_groups_long_tags_and_holds_remain_bounded_readable(language):
    allocation,checks,pigs=inputs(160)
    for i,row in enumerate(allocation["pigs"]):
        row["litter_id"] = "GROUP-"+str(i//20)
        if i%20==0: checks["rows"][i]["state"]="allocation_hold"
    result=build_purpose_work(allocation,checks,analysis_date=DAY)
    answer=answer_herd_read_query("weight_attention",language=language,loader=lambda _:daily(result,pigs))
    assert answer["success"] and len(answer["answer"])<3650
    assert "PIG-SYNTHETIC" not in answer["answer"]
    assert "19" in answer["answer"] and "6 groups" in answer["answer"] if language=="en" else "6 groepe" in answer["answer"]
    assert "held" in answer["answer"] if language=="en" else "teruggehou" in answer["answer"]
    candidates=_purpose_review_candidates({"purpose_work":result},now=NOW,today=DAY,observed_at=NOW)
    assert len(candidates)==8 and len({row["dedupe_key"] for row in candidates})==8
    for row in candidates: normalize_candidate(row,now=NOW)


@pytest.mark.parametrize("language", ["en","af"])
def test_typed_weight_question_real_semantic_service_family_delivery_and_replay(journey,monkeypatch,language,model_budget_fixture):
    from modules.oom_sakkie import herd_read_queries as reads,service
    result,pigs=work()
    packet=daily(result,pigs)
    before=deepcopy(packet)
    monkeypatch.setattr(reads,"load_herd_read_evidence",lambda capability:packet)
    monkeypatch.setattr(service,"classify_intent",lambda *_a:pytest.fail("no reclassification"))
    monkeypatch.setattr(service,"route_with_llm",lambda **_kw:pytest.fail("no second model"))
    monkeypatch.setattr(service,"compose_answer_with_llm",lambda **_kw:pytest.fail("no paid composition"))
    model=interpretation("herd_query",language,capability="weight_attention")
    answer,status=journey.send("Which pigs need weighing?" if language=="en" else "Watter varke moet geweeg word?",model)
    assert status==200,answer
    assert ("weigh 2 after weaning" in answer["answer"] if language=="en" else "weeg 2 ná speen" in answer["answer"]), answer
    assert "S0000" in answer["answer"] and "S0001" in answer["answer"]
    assert "4 October 2026" in answer["answer"] if language=="en" else "4 Oktober 2026" in answer["answer"]
    assert journey.sends[-1][1]==answer["answer"] and len(journey.sends)==1
    assert journey.claim.call_count==0 and packet==before
    replay,_=journey.send("Which pigs need weighing?" if language=="en" else "Watter varke moet geweeg word?",model)
    assert len(journey.sends)==1 and replay["delivery"]["telegram_sends"]==0
    candidates=_purpose_review_candidates({"purpose_work":result},now=NOW,today=DAY,observed_at=NOW)
    assert len(candidates)==1 and candidates[0]["physical_work_ready"] is True
    assert all(row["tag"] in candidates[0]["next_action"] for row in result["cohorts"][0]["members"])


def test_visible_bounded_projection_prioritizes_due_over_held_without_mutating_material():
    allocation,checks,pigs=inputs(4)
    for i,row in enumerate(allocation["pigs"]): row["litter_id"] = "GROUP-"+str(i)
    for row in checks["rows"][:3]: row["state"]="allocation_hold"
    result=build_purpose_work(allocation,checks,analysis_date=DAY)
    before=deepcopy(result)
    answer=answer_herd_read_query("weight_attention",loader=lambda _:daily(result,pigs))
    assert answer["success"] and "S0003" in answer["answer"]
    assert answer["answer"].index("S0003") < answer["answer"].index("held")
    assert result==before


@pytest.mark.parametrize("language",["en","af"])
def test_long_visible_labels_do_not_destroy_whole_answer(language):
    allocation,checks,pigs=inputs(80)
    for i,row in enumerate(allocation["pigs"]):
        row["litter_id"]="GROUP-"+str(i//20)
        row["sow_tag_number"]="Sow"*100
        row["tag_number"]="long-tag-"+str(i)+"x"*200
        checks["rows"][i]["canonical"]["tag_number"]=row["tag_number"]
        checks["rows"][i]["tag"]=row["tag_number"]
    result=build_purpose_work(allocation,checks,analysis_date=DAY)
    answer=answer_herd_read_query("weight_attention",language=language,loader=lambda _:daily(result,pigs))
    assert answer["success"] and len(answer["answer"])<2500
    assert "20" in answer["answer"] and "Pig Allocation" in answer["answer"]
    assert "long-tag-" not in answer["answer"] and "PIG-SYNTHETIC" not in answer["answer"]
    for candidate in _purpose_review_candidates({"purpose_work":result},now=NOW,today=DAY,observed_at=NOW):
        normalize_candidate(candidate,now=NOW)


def test_allocation_borrows_existing_transaction_and_remaining_budget(monkeypatch):
    from contextlib import nullcontext
    import time
    from modules.pig_weights import farm_supabase_read_service as canonical
    raw=SimpleNamespace()
    connection=SimpleNamespace(cursor=lambda:nullcontext(raw))
    allocation,checks,_=inputs()
    def read(*,connect_factory,deadline_seconds,today):
        assert connect_factory.transaction_managed is True
        assert 0<deadline_seconds<=2 and today==DAY
        with connect_factory("unused") as borrowed: assert borrowed.connection is connection
        return {"overview_rows":[],"pig_master_rows":[],"weight_rows":[],"sales_rows":[],
                "litter_rows":[],"pen_lookup":{},"read_progress":{"status":"complete"},
                "allocation_query_status":"known","medical_query_status":"known"}
    monkeypatch.setattr(canonical,"get_allocation_input_rows",read)
    result=load_purpose_work_snapshot(analysis_date=DAY,connection=connection,
        reconciliation=checks,deadline=time.monotonic()+2)
    assert result["purpose_work"]["state"]=="checked" and result["purpose_work"]["cohorts"]==[]
    assert not hasattr(connection,"commit") and not hasattr(connection,"close")


def test_expired_total_budget_never_calls_canonical_reader(monkeypatch):
    from contextlib import nullcontext
    import time
    from modules.pig_weights import farm_supabase_read_service as canonical
    read=Mock(side_effect=AssertionError("expired read must not start"))
    monkeypatch.setattr(canonical,"get_allocation_input_rows",read)
    connection=SimpleNamespace(cursor=lambda:nullcontext(SimpleNamespace()))
    with pytest.raises(TimeoutError,match="purpose_work_read_deadline"):
        load_purpose_work_snapshot(analysis_date=DAY,connection=connection,deadline=time.monotonic()-1)
    read.assert_not_called()


def test_advisory_age_derived_recommendation_is_not_current_cohort_task_material():
    early,checks,_=inputs(weight_day=DAY-timedelta(days=7),kilograms=40)
    late,late_checks,_=inputs(day=DAY+timedelta(days=200),weight_day=DAY-timedelta(days=7),kilograms=40)
    # Real allocation changes its age-derived growth and purpose suggestion.
    assert early["pigs"][0]["growth_class"] != late["pigs"][0]["growth_class"]
    assert early["pigs"][0]["suggested_purpose"] != late["pigs"][0]["suggested_purpose"]
    first=build_purpose_work(early,checks,analysis_date=DAY)
    second=build_purpose_work(late,late_checks,analysis_date=DAY+timedelta(days=200))
    assert first==second


def test_allocation_non_animal_source_overflow_cannot_be_successful_partial_evidence(monkeypatch):
    from modules.pig_weights import herdmaster_purpose_work as purpose
    import time
    calls=[]
    class Cursor:
        def execute(self,*args): calls.append(args)
        def fetchmany(self,count):
            assert count==4
            return [("medical1",),("medical2",),("medical3",),("medical4",)]
    monkeypatch.setattr(purpose,"ALLOCATION_STAGE_ROW_BOUND",3)
    cursor=purpose._PurposeReadCursor(Cursor(),time.monotonic()+2)
    cursor.execute("select pig_id from public.pig_medical_events")
    with pytest.raises(ValueError,match="allocation_source_row_bound_exceeded"):
        cursor.fetchall()
    assert calls[-1][0]=="select pig_id from public.pig_medical_events"


@pytest.mark.parametrize("language",["en","af"])
def test_mixed_hold_reasons_are_not_all_called_allocations(language):
    allocation,checks,pigs=inputs(3)
    checks["rows"][0]["state"]="allocation_hold"
    checks["rows"][1].update(state="unresolved",reasons=["latest_weight_conflict"])
    work=build_purpose_work(allocation,checks,analysis_date=DAY)
    result=answer_herd_read_query("weight_attention",language=language,loader=lambda _:daily(work,pigs))
    assert result["success"]
    assert "existing allocation; unresolved identity" in result["answer"] if language=="en" else "bestaande toewysing; onopgeloste identiteit" in result["answer"]
    assert "S0002" in result["answer"]


@pytest.mark.parametrize("stage,ready",[("Finisher",True),("",False),("Unsupported",False)])
def test_canonical_purpose_scope_is_not_weekly_denominator(stage,ready):
    allocation,checks,_=inputs(1)
    allocation["pigs"][0]["animal_type"]=stage
    checks["rows"][0]["canonical"]["animal_type"]=stage
    group=build_purpose_work(allocation,checks,analysis_date=DAY)["cohorts"][0]
    assert bool(group["weighing_ids"]) is ready
    assert (group["phase"]=="weight_due") is ready
    if not ready: assert "purpose_stage_unproven" in group["blocked"][0]["reasons"]


@pytest.mark.parametrize("tag",["", "Unknown", "Onbekend", "n/a", "na", "None", "null"])
def test_unusable_tag_sentinel_never_becomes_physical_target(tag):
    allocation,checks,_=inputs(1)
    allocation["pigs"][0]["tag_number"]=tag
    checks["rows"][0]["canonical"]["tag_number"]=tag
    group=build_purpose_work(allocation,checks,analysis_date=DAY)["cohorts"][0]
    assert group["phase"]=="held" and group["weighing_ids"]==[]
    assert "visible_identity_missing" in group["blocked"][0]["reasons"]


@pytest.mark.parametrize("allocation_on_farm",["No", "", None])
def test_allocation_on_farm_must_agree_with_current_canonical_true(allocation_on_farm):
    allocation,checks,_=inputs(1)
    allocation["pigs"][0]["on_farm"]=allocation_on_farm
    assert checks["rows"][0]["canonical"]["on_farm"] is True
    group=build_purpose_work(allocation,checks,analysis_date=DAY)["cohorts"][0]
    assert group["phase"]=="held" and group["weighing_ids"]==[]
    assert "allocation_reconciliation_identity_conflict" in group["blocked"][0]["reasons"]
