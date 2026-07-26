import unittest
from datetime import datetime, timezone
from modules.sales.riversdale_auction_candidate_reviews import record_candidate_review

class Cursor:
    def __init__(self, medical=True, inserted=True, existing=None):
        self.medical, self.inserted, self.existing, self.query = medical, inserted, existing, ""
    def execute(self, query, params=()):
        self.query = " ".join(query.split()).lower()
        self.params = params
    def fetchall(self):
        if "pig_medical_events" not in self.query:
            return []
        refs = self.params[1]
        return [(value,) for value in refs] if self.medical else []
    def fetchone(self):
        if "from public.riversdale_auction_cycles" in self.query:
            return ("CYCLE-1",)
        if "returning review_id" in self.query:
            return ("R",) if self.inserted else None
        return self.existing
    def __enter__(self): return self
    def __exit__(self, *_): return False

class Connection:
    def __init__(self, cursor): self.value = cursor
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self, *_): return False

def review(**changes):
    value = {"pig_id":"PIG-21","withdrawal_state":"unknown","quality_state":"unknown",
             "observed_at":datetime.now(timezone.utc).isoformat(),"medical_evidence_refs":[],
             "physical_observation":"Owner physical inspection.","follow_up":"Recheck.",
             "idempotency_key":"review-21","owner_id":"browser-spoof"}
    value.update(changes)
    return value

class CandidateReviewTests(unittest.TestCase):
    def call(self, value=None, actor="stable-owner", cursor=None, candidates=("PIG-21",)):
        return record_candidate_review(value or review(), actor_id=actor, candidate_ids=candidates,
            connect_factory=lambda _: Connection(cursor or Cursor()))

    def test_owner_records_exact_append_only_evidence_and_client_identity_is_ignored(self):
        result, status = self.call()
        self.assertEqual((status,result["status"]),(201,"review_recorded"))
        self.assertNotIn("owner_id",result)
        self.assertTrue(all(result[k] is False for k in (
            "creates_cohort","creates_outlet_assignment","creates_reservation","books_auction",
            "creates_sale","sends_reminder","contacts_customer","changes_medical_record",
            "changes_lifecycle","changes_purpose","changes_farm_state")))

    def test_missing_or_incompatible_principal_and_non_candidate_fail_before_store(self):
        called=[]
        factory=lambda _: called.append(True)
        self.assertEqual(record_candidate_review(review(),actor_id="",candidate_ids=["PIG-21"],connect_factory=factory)[1],403)
        self.assertEqual(record_candidate_review(review(),actor_id="owner",candidate_ids=[],connect_factory=factory)[1],409)
        self.assertEqual(called,[])

    def test_unknown_is_preserved_and_bad_reference_fails_closed(self):
        self.assertEqual(self.call()[0]["review_contract_version"],"riversdale_candidate_review_v1")
        result,status=self.call(review(medical_evidence_refs=["MED-X"]),cursor=Cursor(medical=False))
        self.assertEqual((status,result["status"]),(409,"invalid_medical_evidence_reference"))

    def test_replay_withheld_and_conflict_rejected(self):
        # Existing matching hash is integration-tested in PostgreSQL; an absent/conflicting row rejects.
        result,status=self.call(cursor=Cursor(inserted=False,existing=None))
        self.assertEqual((status,result["status"]),(409,"review_idempotency_conflict"))

    def test_malformed_and_future_evidence_fail(self):
        self.assertEqual(self.call(review(quality_state="clear"))[1],400)
        self.assertEqual(self.call(review(observed_at="2999-01-01T00:00:00+00:00"))[1],400)

if __name__ == "__main__": unittest.main()
