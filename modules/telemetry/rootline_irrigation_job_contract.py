"""Pure, non-actuating contract for a multi-segment ROOTLINE irrigation job."""
from __future__ import annotations
import hashlib, json
from math import ceil
VERSION="rootline_irrigation_job.v1"
class IrrigationJobError(ValueError): pass
def build_irrigation_job(*,zone_id,operating_date,requested_total_seconds,maximum_segment_seconds,plan_identity):
 total=_pos(requested_total_seconds,"requested_total_seconds_invalid"); maximum=_pos(maximum_segment_seconds,"maximum_segment_seconds_invalid")
 if maximum>3599: raise IrrigationJobError("segment_exceeds_native_fail_stop")
 material={"contract_version":VERSION,"zone_id":str(zone_id),"operating_date":str(operating_date),"requested_total_seconds":total,"maximum_segment_seconds":maximum,"expected_segment_count":ceil(total/maximum),"plan_identity":str(plan_identity)}; digest=_digest(material)
 return {**material,"job_id":"ROOTLINE-IRRIGATION-JOB-"+digest[:24].upper(),"job_sha256":digest,"current_segment":0,"cumulative_verified_runtime_seconds":0,"state":"planned"}
def project_next_segment(job,events):
 job=_validate(job); completed={}; active=[]
 for row in [dict(x) for x in (events or ()) if isinstance(x,dict) and x.get("job_id")==job["job_id"]]:
  number=int(row.get("segment_number") or 0)
  if row.get("state") in {"claimed","Active"}: active.append(row)
  if row.get("state")=="Completed":
   if row.get("shutdown_verified") is not True or row.get("rearm_readback_off") is not True: raise IrrigationJobError("completed_segment_off_rearm_unverified")
   _pos(row.get("verified_runtime_seconds"),"verified_runtime_seconds_invalid")
   if number in completed and _digest(completed[number])!=_digest(row): raise IrrigationJobError("conflicting_segment_completion")
   completed[number]=row
 if active:
  ids={(x.get("segment_number"),x.get("execution_id")) for x in active}
  if len(ids)!=1: raise IrrigationJobError("conflicting_active_segments")
  return {"status":"segment_in_progress","command_authority":False,"job_id":job["job_id"],"current_segment":active[0]["segment_number"],"execution_id":active[0].get("execution_id")}
 contiguous=0
 while contiguous+1 in completed: contiguous+=1
 if any(n>contiguous for n in completed): raise IrrigationJobError("non_contiguous_segment_history")
 cumulative=sum(int(completed[n]["verified_runtime_seconds"]) for n in range(1,contiguous+1))
 if cumulative>=job["requested_total_seconds"]: return {"status":"job_completed","command_authority":False,"job_id":job["job_id"],"current_segment":contiguous,"expected_segment_count":job["expected_segment_count"],"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":0}
 number=contiguous+1
 if number>job["expected_segment_count"]: raise IrrigationJobError("job_runtime_shortfall_after_final_segment")
 remaining=job["requested_total_seconds"]-cumulative; duration=min(job["maximum_segment_seconds"],remaining); identity="ROOTLINE-JOB-SEGMENT-"+_digest({"job_id":job["job_id"],"segment_number":number,"duration_seconds":duration})[:24].upper()
 return {"status":"segment_ready","command_authority":True,"job_id":job["job_id"],"job_sha256":job["job_sha256"],"requested_total_seconds":job["requested_total_seconds"],"expected_segment_count":job["expected_segment_count"],"current_segment":number,"segment_number":number,"segment_identity":identity,"segment_requested_seconds":duration,"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":remaining,"predecessor_off_rearm_verified":number==1 or (completed[number-1].get("shutdown_verified") is True and completed[number-1].get("rearm_readback_off") is True)}
def apply_segment_completion(job,events,completion):
 before=project_next_segment(job,events); row=dict(completion or {})
 if before["status"]=="job_completed": return {**before,"created":False,"status":"job_completion_replay"}
 if before["status"]!="segment_ready" or row.get("job_id")!=before["job_id"] or row.get("segment_number")!=before["segment_number"] or row.get("segment_identity")!=before["segment_identity"]: raise IrrigationJobError("segment_completion_identity_mismatch")
 if row.get("shutdown_verified") is not True or row.get("rearm_readback_off") is not True: raise IrrigationJobError("segment_completion_off_rearm_unverified")
 return {**project_next_segment(job,[*list(events or ()),{**row,"state":"Completed"}]),"created":True}
def _validate(v):
 if not isinstance(v,dict): raise IrrigationJobError("job_invalid")
 keys=("contract_version","zone_id","operating_date","requested_total_seconds","maximum_segment_seconds","expected_segment_count","plan_identity"); material={k:v.get(k) for k in keys}; digest=_digest(material)
 if material["contract_version"]!=VERSION or v.get("job_sha256")!=digest or v.get("job_id")!="ROOTLINE-IRRIGATION-JOB-"+digest[:24].upper() or material["expected_segment_count"]!=ceil(int(material["requested_total_seconds"])/int(material["maximum_segment_seconds"])): raise IrrigationJobError("job_digest_invalid")
 return v
def _pos(v,e):
 if isinstance(v,bool): raise IrrigationJobError(e)
 try: v=int(v)
 except (TypeError,ValueError): raise IrrigationJobError(e)
 if v<=0: raise IrrigationJobError(e)
 return v
def _digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
