import unittest
from pathlib import Path

from modules.sales.riversdale_auction_list import record_auction_list_events


class RiversdaleAuctionListTests(unittest.TestCase):
    def test_missing_identity_and_invalid_selection_fail_before_database(self):
        called = []
        factory = lambda _: called.append(True)
        payload = {"action":"add","pig_ids":["PIG-1"],"idempotency_key":"key"}
        self.assertEqual(record_auction_list_events(payload,actor_id="",selectable_ids=["PIG-1"],current_ids=[],connect_factory=factory)[1],403)
        self.assertEqual(record_auction_list_events(payload,actor_id="owner",selectable_ids=[],current_ids=[],connect_factory=factory)[1],409)
        self.assertEqual(called,[])

    def test_remove_requires_current_membership_and_confirmation_is_ui_contract(self):
        result,status=record_auction_list_events(
            {"action":"remove","pig_ids":["PIG-1"],"idempotency_key":"key"},
            actor_id="owner",selectable_ids=[],current_ids=[],connect_factory=lambda _:None)
        self.assertEqual((status,result["status"]),(409,"auction_list_selection_not_allowed"))
        js=Path("static/js/pigAllocation.js").read_text(encoding="utf-8")
        self.assertIn('action === "remove" && !window.confirm',js)

    def test_integrated_table_contract_and_zero_authority(self):
        html=Path("templates/pig-allocation.html").read_text(encoding="utf-8")
        js=Path("static/js/pigAllocation.js").read_text(encoding="utf-8")
        self.assertNotIn('id="riversdale_candidate_review"',html)
        self.assertNotIn("renderAuctionCandidateReviews",js)
        for text in ("Auction Candidates","Auction List","Select all visible","Clear selection",
                     "Add selected to Auction List","Remove selected","Print Auction List"):
            self.assertIn(text,html+js)
        self.assertIn("creates_cohort\":False",Path("modules/sales/riversdale_auction_list.py").read_text())

    def test_migration_is_append_only_and_not_assignment(self):
        sql=Path("supabase/migrations/202607260009_create_riversdale_auction_list_events.sql").read_text(encoding="utf-8").lower()
        self.assertIn("event_type in ('added','removed')",sql)
        self.assertIn("before update or delete",sql)
        self.assertIn("grant select,insert",sql)
        self.assertNotIn("insert into public.pig_active_outlets",sql)
        self.assertNotIn("insert into public.riversdale_auction_cohort_members",sql)

if __name__=="__main__": unittest.main()
