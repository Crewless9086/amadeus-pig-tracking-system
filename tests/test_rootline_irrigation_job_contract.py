import pytest
from modules.telemetry.rootline_irrigation_job_contract import *
def job(total=7198): return build_irrigation_job(zone_id="B12345",operating_date="2026-08-14",requested_total_seconds=total,maximum_segment_seconds=3599,plan_identity="RMQ-20260813-04:PLAN-1")
def complete(plan,events,number,runtime=3599):
 ready=project_next_segment(plan,events); return {"job_id":plan["job_id"],"segment_number":number,"segment_identity":ready["segment_identity"],"execution_id":f"EXEC-{number}","verified_runtime_seconds":runtime,"shutdown_verified":True,"rearm_readback_off":True,"state":"Completed"}
def test_stable_two_segment_job_and_cumulative_completion():
 plan=job(); assert plan["job_id"]==job()["job_id"] and plan["expected_segment_count"]==2
 one=complete(plan,[],1); assert project_next_segment(plan,[one])["segment_number"]==2
 two=complete(plan,[one],2); done=project_next_segment(plan,[one,two]); assert done["status"]=="job_completed" and done["cumulative_verified_runtime_seconds"]==7198
def test_duplicate_completed_callback_is_noop():
 plan=job(); one=complete(plan,[],1); ready=project_next_segment(plan,[one]); two={"job_id":plan["job_id"],"segment_number":2,"segment_identity":ready["segment_identity"],"execution_id":"EXEC-2","verified_runtime_seconds":3599,"shutdown_verified":True,"rearm_readback_off":True}
 assert apply_segment_completion(plan,[one],two)["created"] is True
 assert apply_segment_completion(plan,[one,{**two,"state":"Completed"}],two)["status"]=="job_completion_replay"
def test_restart_claim_is_no_new_authority():
 plan=job(); ready=project_next_segment(plan,[]); state=project_next_segment(plan,[{"job_id":plan["job_id"],"segment_number":1,"segment_identity":ready["segment_identity"],"execution_id":"EXEC-1","state":"claimed"}]); assert state["status"]=="segment_in_progress" and state["command_authority"] is False
def test_off_rearm_unknown_fails_closed():
 plan=job(); row=complete(plan,[],1); row["rearm_readback_off"]=False
 with pytest.raises(IrrigationJobError,match="off_rearm_unverified"): project_next_segment(plan,[row])
def test_exact_short_final_segment():
 plan=job(4000); one=complete(plan,[],1); assert project_next_segment(plan,[one])["segment_requested_seconds"]==401
