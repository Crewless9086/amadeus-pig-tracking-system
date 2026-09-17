import pytest
from modules.telemetry.rootline_irrigation_job_contract import *
def job(total=7200,expected=None): return build_irrigation_job(zone_id="B12345",operating_date="2026-08-14",requested_total_seconds=total,requested_total_minutes=total//60,maximum_segment_seconds=3599,expected_segment_count=expected or (2 if total==7200 else None),plan_identity="RMQ-20260813-04:PLAN-1")
def complete(plan,events,number,runtime=3599):
 ready=project_next_segment(plan,events,rearm_readback_off=number>1); return {"job_id":plan["job_id"],"segment_number":number,"segment_identity":ready["segment_identity"],"execution_id":f"EXEC-{number}","verified_runtime_seconds":runtime,"shutdown_verified":True,"rearm_readback_off":False,"state":"Completed"}
def test_stable_two_segment_job_and_cumulative_completion():
 plan=job(); assert plan["job_id"]==job()["job_id"] and plan["expected_segment_count"]==2
 one=complete(plan,[],1); assert project_next_segment(plan,[one],rearm_readback_off=True)["segment_number"]==2
 two=complete(plan,[one],2); done=project_next_segment(plan,[one,two]); assert done["status"]=="job_completed" and done["cumulative_verified_runtime_seconds"]==7198
def test_duplicate_completed_callback_is_noop():
 plan=job(); one=complete(plan,[],1); ready=project_next_segment(plan,[one],rearm_readback_off=True); two={"job_id":plan["job_id"],"segment_number":2,"segment_identity":ready["segment_identity"],"execution_id":"EXEC-2","verified_runtime_seconds":3599,"shutdown_verified":True,"rearm_readback_off":False}
 assert apply_segment_completion(plan,[one],two,rearm_readback_off=True)["created"] is True
 assert apply_segment_completion(plan,[one,{**two,"state":"Completed"}],two)["status"]=="job_completion_replay"
def test_restart_claim_is_no_new_authority():
 plan=job(); ready=project_next_segment(plan,[]); state=project_next_segment(plan,[{"job_id":plan["job_id"],"segment_number":1,"segment_identity":ready["segment_identity"],"execution_id":"EXEC-1","state":"claimed"}]); assert state["status"]=="segment_in_progress" and state["command_authority"] is False
def test_off_rearm_unknown_fails_closed():
 plan=job(); row=complete(plan,[],1); held=project_next_segment(plan,[row])
 assert held["status"]=="segment_rearm_required" and held["command_authority"] is False
def test_exact_short_final_segment():
 plan=job(4000); one=complete(plan,[],1); assert project_next_segment(plan,[one],rearm_readback_off=True)["segment_requested_seconds"]==401
def test_legacy_executions_are_not_adopted_or_rewritten():
 plan=job(); legacy={"execution_id":"ROOTLINE-EXECUTION-LEGACY","state":"Completed","verified_runtime_seconds":3599,"shutdown_verified":True,"rearm_readback_off":True}
 before=dict(legacy); ready=project_next_segment(plan,[legacy])
 assert ready["segment_number"]==1 and legacy==before
def test_completed_callback_with_wrong_identity_fails_closed():
 plan=job(); one=complete(plan,[],1); two=complete(plan,[one],2); events=[one,two]
 with pytest.raises(IrrigationJobError,match="completed_callback_identity_mismatch"):
  apply_segment_completion(plan,events,{**two,"segment_identity":"wrong"})
def test_oversized_or_short_persisted_runtime_cannot_complete_or_advance():
 plan=job(); one=complete(plan,[],1)
 for runtime in (3598,7198):
  with pytest.raises(IrrigationJobError,match="completed_segment_authority_mismatch"):
   project_next_segment(plan,[{**one,"verified_runtime_seconds":runtime}],rearm_readback_off=True)
