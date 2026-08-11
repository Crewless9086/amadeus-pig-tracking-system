import json
from modules.oom_sakkie.gateway_authority import (
    issue_gateway_owner_authority, issue_mortality_correction_authority)
from modules.pig_weights.mortality_date_correction import (
    correct_mortality_effective_date, mortality_correction_preview_digest)


def packet():
    value={"operation_id":"HERD-MORTALITY-CORR-PIG130-20260811","pig_id":"PIG-2026-6DD4",
      "supersedes_operation_id":"HERD-HEALTH-LOSS-509CEA2267150F54F2243953A8CC3B4F",
      "prior_date":"2026-08-11","corrected_date":"2026-08-06","actor_reference":"5721652188",
      "owner_evidence":{"removed_and_buried":True,"other_pigs_visible_signs":"none_reported",
        "pen_cleaning":"reported_complete"},"evidence_generation":"production-read-2026-08-11",
      "preview_digest":""}
    value["preview_digest"]=mortality_correction_preview_digest(value)
    return value


def authority(value):
    base=issue_gateway_owner_authority("5721652188","5721652188")
    return issue_mortality_correction_authority(base,operation_id=value["operation_id"],
      evidence_generation=value["evidence_generation"],preview_digest=value["preview_digest"])


def test_correction_requires_exact_sealed_authority_before_database_access():
    value=packet()
    result,status=correct_mortality_effective_date(value,None,
      connect_factory=lambda:(_ for _ in ()).throw(AssertionError("database must not be read")))
    assert status==403 and result["writes_farm_data"] is False


def test_correction_authority_is_bound_to_operation_generation_and_preview():
    value=packet();sealed=authority(value)
    changed={**value,"corrected_date":"2026-08-07"}
    assert sealed.operation_id==value["operation_id"]
    result,status=correct_mortality_effective_date(changed,sealed,
      connect_factory=lambda:(_ for _ in ()).throw(AssertionError("database must not be read")))
    assert status==409 and result["status"]=="mortality_correction_preview_binding_invalid"
    substituted={**value,"owner_evidence":{**value["owner_evidence"],"pen_cleaning":"Unknown"}}
    substituted["preview_digest"]=mortality_correction_preview_digest(substituted)
    result,status=correct_mortality_effective_date(substituted,sealed,
      connect_factory=lambda:(_ for _ in ()).throw(AssertionError("database must not be read")))
    assert status==403 and result["status"]=="mortality_correction_authority_denied"


class CorrectionDb:
    def __init__(self):
        self.correction=None;self.inserted=[];self.updated_date="2026-08-11"
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return CorrectionCursor(self)


class CorrectionCursor:
    def __init__(self,db):self.db=db;self.result=None;self.rowcount=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,params=()):
        compact=" ".join(sql.split()).lower();self.rowcount=0
        if "from public.pig_lifecycle_corrections" in compact:
            self.result=self.db.correction
        elif "from public.pigs where pig_id" in compact:
            self.result=("Dead",False,self.db.updated_date,"Died","original note")
        elif "from public.pig_lifecycle_events" in compact:
            self.result=("LIFE-HL-ORIGINAL","2026-08-11",{"immutable":True})
        elif compact.startswith("insert into public.pig_lifecycle_corrections"):
            self.db.correction=(params[0],params[1],params[4],params[3],json.loads(params[6]),
              params[8],"HERD-HEALTH-LOSS-509CEA2267150F54F2243953A8CC3B4F")
            self.db.inserted.append("correction")
        elif compact.startswith("insert into public.pig_lifecycle_events"):
            self.db.inserted.append("superseding_event")
        elif compact.startswith("update public.pigs"):
            self.db.updated_date=params[0];self.db.inserted.append("projection_update");self.rowcount=1
    def fetchone(self):return self.result


def test_append_only_correction_success_then_exact_replay_is_zero_effect():
    value=packet();db=CorrectionDb();sealed=authority(value)
    result,status=correct_mortality_effective_date(value,sealed,connect_factory=lambda:db)
    assert status==201 and result["corrected_date"]=="2026-08-06"
    assert db.inserted==["correction","superseding_event","projection_update"]
    before=list(db.inserted)
    replay,replay_status=correct_mortality_effective_date(value,sealed,connect_factory=lambda:db)
    assert replay_status==200 and replay["status"]=="mortality_correction_replayed_noop"
    assert replay["rows_changed"]==0 and db.inserted==before
    changed={**value,"owner_evidence":{**value["owner_evidence"],"pen_cleaning":"Unknown"}}
    changed["preview_digest"]=mortality_correction_preview_digest(changed)
    conflict,conflict_status=correct_mortality_effective_date(
      changed,authority(changed),connect_factory=lambda:db)
    assert conflict_status==409 and conflict["status"]=="mortality_correction_idempotency_conflict"
    assert db.inserted==before
