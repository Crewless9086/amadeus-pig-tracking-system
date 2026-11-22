"""Canonical command completion advances the saved programme without physical credit."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import pytest
from modules.telemetry import rootline_adaptive_irrigation as adaptive
from modules.telemetry import rootline_water_energy_plan as plan
from modules.telemetry.rootline_irrigation_history import project_canonical_irrigation_history, _attach_latest_zone_executions, _attach_parent_jobs
from modules.telemetry.rootline_irrigation_execution_store import _append_history
from tests.test_rootline_command_plan_truth import CLAIM, execution, recover, read_managed, saved_program, approved_mode
from tests.test_rootline_water_energy_plan import daily_program_facts

class TypedCapture:
    def __init__(self): self.rows=[]
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def cursor(self): return self
    def execute(self, sql, params):
        keys=("irrigation_event_id","event_at","event_type","zone_id","planned_minutes","actual_minutes","details")
        row=dict(zip(keys,params));row["details"]=json.loads(row["details"])
        row["event_at"]=datetime.fromisoformat(row["event_at"])
        row.update(source_id="irrigation-controller-main",actor="ROOTLINE")
        self.rows.append(row)
    def fetchone(self): return (True,)

def completed_e(zone="E12345"):
    store,transport,clock=execution(zone);clock[0]=CLAIM+timedelta(hours=2,seconds=26)
    result=recover(store,transport,clock)
    capture=TypedCapture()
    assert _append_history("record_completed",result["execution"],connection=capture)
    return store,transport,clock,result["execution"],capture.rows

def completion_facts(monkeypatch, store, typed, now):
    facts=daily_program_facts(now.astimezone(plan.ZA_TZ))
    facts.update(read_managed(monkeypatch,store.rows,now))
    history=project_canonical_irrigation_history(typed,snapshot_cutoff=now)
    _attach_latest_zone_executions(history,store.rows,canonical_ordered=True)
    _attach_parent_jobs(history,store.rows,canonical_ordered=True)
    # Existing epoch coverage is independent of the new completion event.
    for zone,ledger in facts["irrigation_history"]["zones"].items():
        for key in ("complete_from","complete_through","epoch_complete_through","planning_epoch_start"):
            if key in ledger: history["zones"][zone][key]=ledger[key]
    facts["irrigation_history"]=history
    return facts

def test_real_typed_command_completion_advances_to_b_without_water_credit(monkeypatch):
    store,transport,clock,done,typed=completed_e();now=clock[0]+timedelta(minutes=20)
    facts=completion_facts(monkeypatch,store,typed,now)
    saved=saved_program()
    # Reproduce a previously persisted false E-running projection.
    for task in saved["candidate_tasks"]:
        if task.get("scheduled_order"):
            task["planned_start_at"]=(now+timedelta(hours=2*(task["scheduled_order"]-1))).isoformat()
    original=deepcopy(saved)
    current=plan.project_saved_program_for_execution(saved,facts,now=now)
    tasks={t["task_id"]:t for t in current["candidate_tasks"]}
    assert tasks["irrigation_E12345"]["zone_decision"]=="Completed"
    assert tasks["irrigation_B12345"]["zone_decision"]=="Run now"
    assert tasks["irrigation_C12345"]["zone_decision"]=="Run later"
    assert tasks["irrigation_A12345"]["zone_decision"]=="Run later"
    assert tasks["irrigation_B12345"]["planned_start_at"]==now.astimezone(plan.ZA_TZ).isoformat()
    assert done["shutdown_verified"] is False and done["verified_runtime_seconds"]==0
    event=facts["irrigation_history"]["zones"]["E12345"]["events"][0]
    assert event["command_job_completed"] and not event["qualifies_as_completed_watering"]
    assert saved==original and len(transport.calls)==2

@pytest.mark.parametrize("change",["wrong_day","wrong_zone","wrong_channel","wrong_id","partial","missing_off","future","ambiguous","duration","bool_segment"])
def test_completion_validation_rejects_unbound_or_partial_programmes(change):
    _,_,clock,done,typed=completed_e()
    row={"state":"Completed","command_job_completed":True,"outcome_id":done["execution_id"],
        "source":"rootline_execution_coordinator","completed_at":done["completed_at"],
        "operating_date":done["operating_date"],"command_execution":deepcopy(typed[0]["details"]["command_execution"])}
    inner=row["command_execution"]
    if change=="wrong_day":row["operating_date"]="2026-11-21"
    elif change=="wrong_zone":inner["zone_id"]="B12345"
    elif change=="wrong_channel":inner["channel"]=1
    elif change=="wrong_id":row["outcome_id"]="OTHER"
    elif change=="partial":inner["expected_segment_count"]=2
    elif change=="missing_off":inner["command_off_receipt"]={}
    elif change=="future":row["completed_at"]=(clock[0]-timedelta(minutes=1)).isoformat()
    elif change=="ambiguous":inner["command_off_receipt"]["accepted_unambiguous"]=False
    elif change=="duration":inner["planned_runtime_seconds"]=60
    elif change=="bool_segment":inner["segment_number"]=True
    assert adaptive._command_completion_time(row,zone_id="E12345") is None

def test_actual_future_base_window_is_not_pulled_forward():
    saved=saved_program();now=CLAIM+timedelta(minutes=5)
    tasks={t["task_id"]:t for t in saved["candidate_tasks"]}
    tasks["irrigation_E12345"]["zone_decision"]="Completed"
    for key in ("B12345","C12345","A12345"):tasks["irrigation_"+key]["zone_decision"]="Run now"
    plan._adjust_live_slots(saved,{"irrigation_schedule_context":None},now)
    assert tasks["irrigation_B12345"]["zone_decision"]=="Run later"
    assert tasks["irrigation_B12345"]["planned_start_at"]==next(t["planned_start_at"] for t in saved["daily_program"]["base_tasks"] if t["task_id"]=="irrigation_B12345")


@pytest.mark.parametrize("zone",["A12345","B12345","C12345","E12345"])
def test_all_bound_completed_command_programmes_remain_completed(monkeypatch,zone):
    store,_,clock,_,typed=completed_e(zone)
    facts=completion_facts(monkeypatch,store,typed,clock[0])
    result=plan.project_saved_program_for_execution(saved_program(),facts,now=clock[0])
    task=next(t for t in result["candidate_tasks"] if t["task_id"]=="irrigation_"+zone)
    assert task["zone_decision"]=="Completed"
    assert not facts["irrigation_history"]["zones"][zone]["verified_completed_days"]


def test_conflicting_completion_ledger_does_not_establish_daily_completion(monkeypatch):
    store,_,clock,_,typed=completed_e()
    facts=completion_facts(monkeypatch,store,typed,clock[0])
    facts["irrigation_history"]["zones"]["E12345"]["conflicts"]=["same_execution_conflicting_terminal"]
    result=plan.project_saved_program_for_execution(saved_program(),facts,now=clock[0])
    assert next(t for t in result["candidate_tasks"] if t["task_id"]=="irrigation_E12345")["zone_decision"]!="Completed"
