from modules.oom_sakkie.rootline_protected_irrigation import ACTION_KIND,build_preview_payload,execute_claimed_segment,protected_card_mission_id
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
def artifact(**changes):
 value={"job_id":"JOB-1","job_sha256":"a"*64,"zone_id":"B12345","channel":1,"segment_identity":"SEG-1","current_segment":1,"segment_requested_seconds":3599,"requested_total_duration_seconds":7200,"governed_executable_duration_seconds":7198,"plan_generation":"PLAN-1","controller_safety_generation":"SAFE-1","eligibility_sha256":"b"*64,"expected_segment_count":2,"maximum_duration_seconds":3599};value.update(changes);return value
def claim(payload=None):
 payload=payload or build_preview_payload(artifact(),mission_id="RMQ-20260813-04");return {"preview_payload":payload,"preview_digest":canonical_preview_digest(ACTION_KIND,payload),"mission_id":"RMQ-20260813-04","callback_token":"opaque"}
def parsed():return {"telegram_user_id":"1","telegram_chat_id":"1"}
def test_preview_binds_exact_governed_boundary():
 payload=build_preview_payload(artifact(),mission_id="RMQ-20260813-04");assert payload["requested_total_duration_seconds"]==7200 and payload["governed_executable_duration_seconds"]==7198 and payload["segment_requested_seconds"]==3599 and payload["evidence_generation"]=="PLAN-1"
def test_each_preview_digest_has_distinct_card_lifecycle_identity():
 one=protected_card_mission_id("a"*64);two=protected_card_mission_id("b"*64)
 assert one!=two and one.startswith("RMQ-20260813-04:PROTECTED:")
def test_preview_rejects_boundary_expansion():
 for changes in ({"zone_id":"C12345"},{"channel":2},{"segment_requested_seconds":3600},{"current_segment":2},{"expected_segment_count":3}):
  try:build_preview_payload(artifact(**changes),mission_id="RMQ-20260813-04")
  except ValueError:pass
  else:raise AssertionError(changes)
 try:build_preview_payload(artifact(),mission_id="OTHER")
 except ValueError:pass
 else:raise AssertionError("wrong mission accepted")
def test_mismatch_is_zero_control():
 row=claim();row["preview_digest"]="wrong";calls=[];result,status=execute_claimed_segment(row,parsed=parsed(),runner=lambda **kw:calls.append(kw));assert status==409 and result["hardware_commands"]==0 and calls==[]
def test_correctly_digested_generic_claim_cannot_cross_b_boundary():
 payload=build_preview_payload(artifact(),mission_id="RMQ-20260813-04")
 payload["zone_id"]="C12345";payload["channel"]=2
 row={"preview_payload":payload,"preview_digest":canonical_preview_digest(ACTION_KIND,payload),
   "mission_id":"RMQ-20260813-04","callback_token":"opaque"}
 calls=[];result,status=execute_claimed_segment(row,parsed=parsed(),runner=lambda **kw:calls.append(kw))
 assert status==409 and result["hardware_commands"]==0 and calls==[]
def test_exact_claim_delegates_once_to_existing_runner():
 calls=[]
 def runner(**kwargs):calls.append(kwargs);return {"success":True,"status":"segment_started","hardware_commands":1,"provider_control_calls":1}
 result,status=execute_claimed_segment(claim(),parsed=parsed(),runner=runner,environ={"DATABASE_URL":"db"});assert status==200 and result["status"]=="segment_started" and len(calls)==1 and calls[0]["expected_artifact"]["job_id"]=="JOB-1"
