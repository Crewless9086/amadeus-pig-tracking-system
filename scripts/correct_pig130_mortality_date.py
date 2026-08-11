"""Governed one-time Pig 130 effective-date correction (idempotent on replay)."""
import argparse,json
from modules.oom_sakkie.gateway_authority import (
    issue_gateway_owner_authority,issue_mortality_correction_authority)
from modules.pig_weights.mortality_date_correction import (
    correct_mortality_effective_date,mortality_correction_preview_digest)

OPERATION="HERD-MORTALITY-CORR-PIG130-20260811"

def packet():
    value={"operation_id":OPERATION,"pig_id":"PIG-2026-6DD4",
      "supersedes_operation_id":"HERD-HEALTH-LOSS-509CEA2267150F54F2243953A8CC3B4F",
      "prior_date":"2026-08-11","corrected_date":"2026-08-06","actor_reference":"5721652188",
      "owner_evidence":{"removed_and_buried":True,
        "no_visible_signs_in_other_pigs_reported":True,"pen_cleaning_reported":True,
        "provider_message_ids":["3515","3517","3518"]},
      "evidence_generation":"production-read-2026-08-11","preview_digest":""}
    value["preview_digest"]=mortality_correction_preview_digest(value)
    return value

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",required=True,choices=[OPERATION])
    args=parser.parse_args();value=packet()
    base=issue_gateway_owner_authority(value["actor_reference"],value["actor_reference"])
    authority=issue_mortality_correction_authority(base,operation_id=args.execute,
      evidence_generation=value["evidence_generation"],preview_digest=value["preview_digest"])
    result,status=correct_mortality_effective_date(value,authority)
    print(json.dumps({"http_status":status,**result},sort_keys=True,default=str))
    raise SystemExit(0 if result.get("success") else 1)

if __name__=="__main__":main()
