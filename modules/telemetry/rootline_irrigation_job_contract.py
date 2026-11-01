"""Pure, non-actuating contract for a multi-segment ROOTLINE irrigation job."""
from __future__ import annotations
import hashlib, json
from math import ceil
from datetime import datetime, timedelta, timezone
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
 job=_validate(job); completed={}; stopped={}; active_by_segment={}
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
  if row.get("state")=="Stopped":
   if not validate_weather_stopped_execution(row):
    raise IrrigationJobError("stopped_segment_evidence_invalid")
   expected_duration=min(job["maximum_segment_seconds"],max(0,
       job["governed_executable_seconds"]-(number-1)*job["maximum_segment_seconds"]))
   expected_identity="ROOTLINE-JOB-SEGMENT-"+_digest({"job_id":job["job_id"],
       "segment_number":number,"duration_seconds":expected_duration})[:24].upper()
   if (row.get("job_sha256")!=job["job_sha256"] or row.get("zone_id")!=job["zone_id"]
       or number<1 or number>job["expected_segment_count"]
       or row.get("planned_runtime_seconds")!=expected_duration
       or row.get("segment_identity")!=expected_identity):
    raise IrrigationJobError("stopped_segment_authority_mismatch")
   if number in stopped and _digest(stopped[number])!=_digest(row):
    raise IrrigationJobError("conflicting_segment_stop")
   stopped[number]=row
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
 if set(completed)&set(stopped): raise IrrigationJobError("conflicting_segment_terminal_outcomes")
 consumed={**completed,**stopped}
 active=[row for number,rows in active_by_segment.items() if number not in consumed for row in rows]
 if active:
  ids={(x.get("segment_number"),x.get("execution_id")) for x in active}
  if len(ids)!=1: raise IrrigationJobError("conflicting_active_segments")
  return {"status":"segment_in_progress","command_authority":False,"job_id":job["job_id"],"current_segment":active[0]["segment_number"],"execution_id":active[0].get("execution_id")}
 contiguous=0
 while contiguous+1 in consumed: contiguous+=1
 if any(n>contiguous for n in consumed): raise IrrigationJobError("non_contiguous_segment_history")
 cumulative=sum(int(row["verified_runtime_seconds"]) for n,row in completed.items() if n<=contiguous)
 for number,row in stopped.items():
  prior=sum(int(item["verified_runtime_seconds"]) for n,item in completed.items() if n<number)
  if row.get("cumulative_verified_runtime_seconds")!=prior:
   raise IrrigationJobError("stopped_segment_prior_credit_mismatch")
 if cumulative>=job["governed_executable_seconds"]: return {"status":"job_completed","command_authority":False,"job_id":job["job_id"],"current_segment":contiguous,"expected_segment_count":job["expected_segment_count"],"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":0}
 number=contiguous+1
 if number>job["expected_segment_count"]:
  if not stopped: raise IrrigationJobError("job_runtime_shortfall_after_final_segment")
  return {"status":"job_deferred","command_authority":False,"job_id":job["job_id"],
      "current_segment":contiguous,"expected_segment_count":job["expected_segment_count"],
      "cumulative_verified_runtime_seconds":cumulative,
      "remaining_seconds":job["governed_executable_seconds"]-cumulative,
      "consumed_segment_count":contiguous,"unused_segment_count":0,
      "reason":"weather_stop_original_segments_exhausted",
      "next_action_owner":"ROOTLINE","next_trigger":"next_permitted_normal_irrigation_plan"}
 remaining=job["governed_executable_seconds"]-cumulative
 if number>1 and rearm_readback_off is not True: return {"status":"segment_rearm_required","command_authority":False,"job_id":job["job_id"],"current_segment":number,"cumulative_verified_runtime_seconds":cumulative,"remaining_seconds":remaining}
 duration=min(job["maximum_segment_seconds"],job["governed_executable_seconds"]-(number-1)*job["maximum_segment_seconds"]); identity="ROOTLINE-JOB-SEGMENT-"+_digest({"job_id":job["job_id"],"segment_number":number,"duration_seconds":duration})[:24].upper()
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
 identity=hashlib.sha256(
  f"{row.get('job_id')}|{row.get('job_sha256')}|Cancelled".encode()).hexdigest()
 return (row.get("contract_version")=="rootline_parent_job_terminal_resolution.v1"
  and row.get("resolution_sha256")==digest
  and row.get("execution_id")=="ROOTLINE-JOB-CANCELLATION-"+identity[:24].upper())


WEATHER_STOP_CONTRACT = "rootline_irrigation_weather_stop.v1"
_WEATHER_STOP_FIELDS = (
    "terminal_contract", "execution_id", "job_id", "job_sha256", "zone_id", "device_id",
    "channel", "segment_number", "segment_identity", "operating_date", "claimed_at",
    "planned_runtime_seconds", "primary_stop_deadline", "native_fail_stop_deadline",
    "on_attempts", "start_evidence", "shutdown_evidence", "completed_at", "state",
    "shutdown_verified", "objective_satisfied", "verified_runtime_seconds",
    "weather_stop_evidence", "stop_requested_at", "partial_observation",
    "cumulative_verified_runtime_seconds", "remaining_seconds", "job_completed", "reason",
    "requested_total_duration_seconds", "requested_total_duration_minutes",
    "governed_executable_duration_seconds", "expected_segment_count",
)


def weather_stop_digest(row):
    return _digest({key: row.get(key) for key in _WEATHER_STOP_FIELDS})


def validate_weather_stopped_execution(row):
    """Verify a safe terminal stop without inventing continuous runtime credit."""
    if not isinstance(row, dict):
        return False
    weather = row.get("weather_stop_evidence")
    shutdown = row.get("shutdown_evidence")
    partial = row.get("partial_observation")
    if not all(isinstance(value, dict) for value in (weather, shutdown, partial)):
        return False
    try:
        claimed = _stop_time(row.get("claimed_at"))
        requested = _stop_time(row.get("stop_requested_at"))
        primary = _stop_time(row.get("primary_stop_deadline"))
        native = _stop_time(row.get("native_fail_stop_deadline"))
        completed = _stop_time(row.get("completed_at"))
        stopped = _stop_time(shutdown.get("retrieved_at") or shutdown.get("observed_at"))
        assessed = _stop_time(weather.get("assessed_at"))
        read_started = _stop_time(weather.get("read_started_at"))
        planned = row.get("planned_runtime_seconds")
        if (None in (claimed, requested, primary, native, completed, stopped, assessed, read_started)
                or type(planned) is not int or not 0 < planned <= 3599
                or not primary <= native <= claimed+timedelta(seconds=3599)
                or primary != claimed+timedelta(seconds=planned)
                or not claimed <= read_started < primary
                or not read_started <= assessed <= requested <= stopped <= completed):
            return False
        if (shutdown.get("device_id") != row.get("device_id")
                or type(shutdown.get("channel")) is not int or shutdown["channel"] != row.get("channel")
                or any(key in shutdown and shutdown[key] != row.get(key) for key in ("execution_id", "zone_id"))
                or ("retrieved_at" in shutdown and "observed_at" in shutdown
                    and _stop_time(shutdown["retrieved_at"]) != _stop_time(shutdown["observed_at"]))):
            return False
        if (row.get("terminal_contract") != WEATHER_STOP_CONTRACT
                or row.get("state") != "Stopped" or row.get("shutdown_verified") is not True
                or row.get("objective_satisfied") is not False or row.get("job_completed") is not False
                or row.get("on_attempts") != 1 or row.get("verified_runtime_seconds") != 0
                or (row.get("objective_evidence") or {}).get("verified_runtime_minutes") is not None
                or shutdown.get("authoritative") is not True or shutdown.get("state") != "OFF"
                or not shutdown.get("evidence_id")
                or weather.get("contract_version") != "rootline_active_weather.v1"
                or weather.get("stop_required") is not True
                or weather.get("reason") not in {
                    "active_weather_rain_hold", "active_weather_stale", "active_weather_unavailable",
                    "active_weather_policy_unavailable", "active_weather_unhealthy_or_conflicting"}
                or row.get("reason") != weather.get("reason")
                or weather.get("evidence_sha256") != _digest({key:value for key,value in weather.items()
                    if key != "evidence_sha256"})
                or partial.get("continuous_runtime_verified") is not False
                or partial.get("physical_delivery") != "Unknown"
                or row.get("terminal_sha256") != weather_stop_digest(row)):
            return False
        if row.get("job_id"):
            total = row.get("governed_executable_duration_seconds")
            prior = row.get("cumulative_verified_runtime_seconds")
            if (type(total) is not int or type(prior) is not int or not 0 <= prior < total
                    or type(row.get("remaining_seconds")) is not int
                    or row["remaining_seconds"] != total-prior):
                return False
        start = row.get("start_evidence") or {}
        start = start if isinstance(start, dict) else {}
        started = _stop_time(start.get("retrieved_at") or start.get("observed_at"))
        valid_start = (start.get("authoritative") is True and start.get("state") == "ON"
            and bool(start.get("evidence_id")) and started is not None
            and all(key not in start or start[key] == row.get(key)
                for key in ("execution_id", "zone_id", "device_id", "channel"))
            and claimed <= started <= requested)
        expected = (stopped-started).total_seconds() if valid_start else None
        return (partial.get("observed_interval_seconds") == expected
            and partial.get("start_observed_at") == (started.isoformat() if valid_start else None)
            and partial.get("off_observed_at") == stopped.isoformat())
    except (ValueError, TypeError, OverflowError):
        return False


def _stop_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None
