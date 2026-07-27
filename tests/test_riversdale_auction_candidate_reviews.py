import unittest
from datetime import date, datetime, timedelta, timezone
from modules.sales.riversdale_auction_candidate_reviews import (
    _withdrawal_state, read_latest_candidate_reviews, record_candidate_review,
)

class Cursor:
    def __init__(self, medical_rows=None, existing=None):
        self.medical_rows = medical_rows if medical_rows is not None else [
            ("MED-1", 7, date.today() - timedelta(days=1))
        ]
        self.existing, self.query = existing, ""
    def execute(self, query, params=()):
        self.query = " ".join(query.split()).lower()
        self.params = params
    def fetchall(self):
        return self.medical_rows if "pig_medical_events" in self.query else []
    def fetchone(self):
        if "from public.riversdale_auction_cycles" in self.query:
            return ("CYCLE-1",)
        if "where idempotency_key" in self.query:
            return self.existing
        if "returning review_id" in self.query:
            return ("R",)
        return None
    def __enter__(self): return self
    def __exit__(self, *_): return False

class Connection:
    def __init__(self, cursor): self.value = cursor
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self, *_): return False

def review(**changes):
    value = {"pig_id":"PIG-21","auction_cycle_id":"CYCLE-1",
             "withdrawal_state":"cleared","quality_state":"unknown",
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
        result,status=self.call(
            review(withdrawal_state="cleared"),
            cursor=Cursor(medical_rows=[("MED-X", None, None)]),
        )
        self.assertEqual((status,result["status"]),(409,"withdrawal_evidence_conflict"))
        self.assertEqual(result["authoritative_withdrawal_state"], "unknown")

    def test_replay_withheld_and_conflict_rejected(self):
        first_cursor = Cursor()
        self.assertEqual(self.call(cursor=first_cursor)[1], 201)
        digest = first_cursor.params[-1]
        result, status = self.call(cursor=Cursor(existing=("R", digest)))
        self.assertEqual((status, result["status"]), (200, "review_replayed_withheld"))
        result,status=self.call(cursor=Cursor(existing=("R", "different-hash")))
        self.assertEqual((status,result["status"]),(409,"review_idempotency_conflict"))

    def test_candidate_membership_is_reloaded_inside_locked_transaction(self):
        result, status = record_candidate_review(
            review(), actor_id="stable-owner",
            candidate_loader=lambda _connection, _cycle: [],
            connect_factory=lambda _: Connection(Cursor()),
        )
        self.assertEqual(
            (status, result["status"]), (409, "candidate_not_in_current_preview")
        )

    def test_equal_time_conflicting_reviews_fail_closed_deterministically(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=1)
        recorded = datetime.now(timezone.utc)
        rows = [
            ("PIG-21", "R-1", "cleared", "suitable", observed, "O-1", "", recorded),
            ("PIG-21", "R-2", "cleared", "hold", observed, "O-2", "", recorded),
        ]
        cursor = Cursor()
        cursor.fetchall = lambda: rows
        result, status = read_latest_candidate_reviews(
            auction_cycle_id="CYCLE-1", pig_ids=["PIG-21"],
            connect_factory=lambda _: Connection(cursor),
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["PIG-21"]["quality_state"], "unknown")
        self.assertFalse(result["PIG-21"]["fresh"])
        self.assertTrue(result["PIG-21"]["evidence_conflict"])

    def test_malformed_and_future_evidence_fail(self):
        self.assertEqual(self.call(review(quality_state="clear"))[1],400)
        self.assertEqual(self.call(review(observed_at="2999-01-01T00:00:00+00:00"))[1],400)

    def test_withdrawal_state_never_infers_clearance_from_absence(self):
        today = date.today()
        self.assertEqual(_withdrawal_state([], today=today), "unknown")
        self.assertEqual(_withdrawal_state(
            [("MED-1", None, None)], today=today
        ), "unknown")
        self.assertEqual(_withdrawal_state(
            [("MED-1", 7, today + timedelta(days=1))], today=today
        ), "hold")
        self.assertEqual(_withdrawal_state(
            [("MED-1", 7, today - timedelta(days=1))], today=today
        ), "cleared")

if __name__ == "__main__": unittest.main()
