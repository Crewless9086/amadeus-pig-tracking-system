"""Pure, non-actuating contract for a multi-segment ROOTLINE irrigation job."""
from __future__ import annotations
import hashlib, json
from math import ceil
VERSION="rootline_irrigation_job.v1"
class IrrigationJobError(ValueError): pass
def build_irrigation_job(*,zone_id,operating_date,requested_total_seconds,maximum_segment_seconds,plan_identity,requested_total_minutes=None,expected_segment_count=None):
 total=_pos(requested_total_seconds,"requested_total_seconds_invalid"); maximum=_pos(maximum_segment_seconds,"maximum_segment_seconds_invalid")
 if maximum>3599: raise IrrigationJobError("segment_exceeds_native_fail_stop")
 expected=int(expected_segment_count or ceil(total/maximum))
 executable=min(total,expected*maximum)
 if expected!=ceil(executable/maximum): raise IrrigationJobError("expected_segment_count_invalid")
 material={"contract_version":VERSION,"zone_id":str(zone_id),"operating_date":str(operating_date),"requested_total_seconds":total,"requested_total_minutes":int(requested_total_minutes or ceil(total/60)),"governed_executable_seconds":executable,"maximum_segment_seconds":maximum,"expected_segment_count":expected,"plan_identity":str(plan_identity)}; digest=_digest(material)
 return {**material,"job_id":"ROOTLINE-IRRIGATION-JOB-"+digest[:24].upper(),"job_sha256":digest,"current_segment":0,"cumulative_verified_runtime_seconds":0,"state":"planned"}
def project_next_segment(job,events,rearm_readback_off=False):
 job=_validate(job); completed={}; active_by_segment={}
 for row in [dict(x) for x in (events or ()) if isinstance(x,dict) and x.get("job_id")==job["job_id"]]:
  if row.get("action")=="record_job_resolution" and row.get("resolution")=="Cancelled":
   if (row.get("job_sha256")!=job["job_sha256"] or row.get("zone_id")!=job["zone_id"]
       or row.get("terminal") is not True or row.get("provider_off_verified") is not True
       or row.get("fabricated_runtime_seconds")!=0 or row.get("water_credit_created") is not False
       or not _valid_cancellation_digest(row)):
    raise IrrigationJobError("terminal_cancellation_binding_invalid")
   return {"status":"job_cancelled","command_authority":False,"job_id":job["job_id"],
       "current_segment":row.get("current_segment"),
       "cumulative_verified_runtime_seconds":int(row.get("cumulative_verified_runtime_seconds") or 0),
       "remaining_seconds":0,"cancellation_identity":row.get("execution_id")}
  number=int(row.get("segment_number") or 0)
  if row.get("state") in {"claimed","Active"}: active_by_segment.setdefault(number,[]).append(row)
  if row.get("state")=="Completed":
   if row.get("shutdown_verified") is not True: raise IrrigationJobError("completed_segment_shutdown_unverified")
   runtime=_pos(row.get("verified_runtime_seconds"),"verified_runtime_seconds_invalid")
   expected_duration=min(job["maximum_segment_seconds"],max(0,
       job["governed_executable_seconds"]-(number-1)*job["maximum_segment_seconds"]))
   expected_identity="ROOTLINE-JOB-SEGMENT-"+_digest({"job_id":job["job_id"],
       "segment_number":number,"duration_seconds":expected_duration})[:24].upper()
   if (number<1 or number>job["expected_segment_count"]
       or runtime!=expected_duration or row.get("segment_identity")!=expected_identity):
    raise IrrigationJobError("completed_segment_authority_mismatch")
   if number in completed and _digest(completed[number])!=_digest(row): raise IrrigationJobError("conflicting_segment_completion")
   completed[number]=row
 active=[row for number,rows in active_by_segment.items() if number not in completed for row in rows]
 if active:
  ids={(x.get("segment_number"),x.get("execution_id")) for x in active}
  if len(ids)!=1: raise IrrigationJobError("conflicting_active_segments")
  return {"status":"segment_in_progress","command_authority":False,"job_id":job["job_id"],"current_segment":active[0]["segment_number"],"execution_id":active[0].get("execution_id")}
 contiguous=0
 while contiguous+1 in completed: contiguous+=1
 if any(n>contiguous for n in completed): raise IrrigationJobError("non_contiguous_segment_history")
 cumulative=sum(int(completed[n]["verified_runtime_seconds"]) for n in range(1,contiguous+1))
 if cumulative>=job["governed_executable_seconds"]: return {"status":"job_completed","command_authority":False,"job_id":job["job_id"],"current_segment":contiguous,"expected_segment_count":job["expected_segment_count"],"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":0}
 number=contiguous+1
 if number>job["expected_segment_count"]: raise IrrigationJobError("job_runtime_shortfall_after_final_segment")
 remaining=job["governed_executable_seconds"]-cumulative
 if number>1 and rearm_readback_off is not True: return {"status":"segment_rearm_required","command_authority":False,"job_id":job["job_id"],"current_segment":number,"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":remaining}
 duration=min(job["maximum_segment_seconds"],remaining); identity="ROOTLINE-JOB-SEGMENT-"+_digest({"job_id":job["job_id"],"segment_number":number,"duration_seconds":duration})[:24].upper()
 return {"status":"segment_ready","command_authority":True,"job_id":job["job_id"],"job_sha256":job["job_sha256"],"requested_total_seconds":job["requested_total_seconds"],"governed_executable_seconds":job["governed_executable_seconds"],"expected_segment_count":job["expected_segment_count"],"current_segment":number,"segment_number":number,"segment_identity":identity,"segment_requested_seconds":duration,"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":remaining,"predecessor_off_rearm_verified":number==1 or rearm_readback_off is True}
def apply_segment_completion(job,events,completion,rearm_readback_off=False):
 before=project_next_segment(job,events,rearm_readback_off=rearm_readback_off); row=dict(completion or {})
 if before["status"]=="job_completed":
  matches=[x for x in (events or ()) if isinstance(x,dict) and x.get("state")=="Completed" and x.get("job_id")==row.get("job_id") and x.get("segment_number")==row.get("segment_number") and x.get("segment_identity")==row.get("segment_identity")]
  if not matches: raise IrrigationJobError("completed_callback_identity_mismatch")
  return {**before,"created":False,"status":"job_completion_replay"}
 if before["status"]!="segment_ready" or row.get("job_id")!=before["job_id"] or row.get("segment_number")!=before["segment_number"] or row.get("segment_identity")!=before["segment_identity"]: raise IrrigationJobError("segment_completion_identity_mismatch")
 if row.get("shutdown_verified") is not True: raise IrrigationJobError("segment_completion_shutdown_unverified")
 return {**project_next_segment(job,[*list(events or ()),{**row,"state":"Completed"}]),"created":True}
def _validate(v):
 if not isinstance(v,dict): raise IrrigationJobError("job_invalid")
 keys=("contract_version","zone_id","operating_date","requested_total_seconds","requested_total_minutes","governed_executable_seconds","maximum_segment_seconds","expected_segment_count","plan_identity"); material={k:v.get(k) for k in keys}; digest=_digest(material)
 if material["contract_version"]!=VERSION or v.get("job_sha256")!=digest or v.get("job_id")!="ROOTLINE-IRRIGATION-JOB-"+digest[:24].upper() or int(material["governed_executable_seconds"])!=min(int(material["requested_total_seconds"]),int(material["expected_segment_count"])*int(material["maximum_segment_seconds"])) or material["expected_segment_count"]!=ceil(int(material["governed_executable_seconds"])/int(material["maximum_segment_seconds"])): raise IrrigationJobError("job_digest_invalid")
 return v
def _pos(v,e):
 if isinstance(v,bool): raise IrrigationJobError(e)
 try: v=int(v)
 except (TypeError,ValueError): raise IrrigationJobError(e)
 if v<=0: raise IrrigationJobError(e)
 return v
def _digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def _valid_cancellation_digest(row):
 keys=("contract_version","resolution","terminal","mission_id","job_id","job_sha256",
  "zone_id","current_segment","expected_segment_count","cumulative_verified_runtime_seconds",
  "cancelled_unverified_remaining_seconds","remaining_seconds","provider_off_verified",
  "provider_off_evidence_digest","provider_off_observed_at","fabricated_runtime_seconds",
  "water_credit_created","next_attempt_requires_fresh_execution_identity","reason")
 material={key:row.get(key) for key in keys}; digest=_digest(material)
 return (row.get("contract_version")=="rootline_parent_job_terminal_resolution.v1"
  and row.get("resolution_sha256")==digest
  and row.get("execution_id")=="ROOTLINE-JOB-CANCELLATION-"+digest[:24].upper())
