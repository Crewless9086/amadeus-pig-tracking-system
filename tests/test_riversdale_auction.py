import unittest
from datetime import date, datetime
from unittest.mock import patch

from modules.sales.riversdale_auction import build_owner_prompts, build_riversdale_auction_packet, first_wednesday, load_owner_confirmed_cycle, queue_due_owner_prompts
from modules.pig_weights.pig_weights_service import get_riversdale_auction_recommendation


class RiversdaleAuctionTests(unittest.TestCase):
    def _allocation(self):
        return {"pigs": [
            {"pig_id": "SLOW", "tag_number": "1", "growth_class": "Extremely Slow", "growth_reason": "0.09 kg/day", "readiness_bucket": "Livestock Candidate", "litter_quality": "Fair", "withdrawal_clear": "Yes"},
            {"pig_id": "ORDER", "tag_number": "2", "growth_class": "Extremely Slow", "readiness_bucket": "Allocated", "reserved_for_order_id": "ORD-1"},
            {"pig_id": "BREED", "tag_number": "3", "growth_class": "Extremely Slow", "readiness_bucket": "Retain / Breeding Candidate"},
            {"pig_id": "APPROVED", "tag_number": "4", "growth_class": "Steady", "owner_approved_auction_candidate": "Yes", "readiness_bucket": "Growing", "withdrawal_clear": "Yes"},
        ]}

    def test_first_wednesday_and_two_prompt_windows_are_deterministic(self):
        self.assertEqual(first_wednesday(date(2026, 8, 10)).isoformat(), "2026-08-05")
        first_prompt = build_owner_prompts(date(2026, 7, 22))
        second_prompt = build_owner_prompts(date(2026, 7, 29))
        self.assertEqual([item["days_before"] for item in first_prompt], [14])
        self.assertEqual([item["days_before"] for item in second_prompt], [7])
        self.assertEqual(len({item["idempotency_key"] for item in first_prompt + second_prompt}), 2)
        self.assertEqual(build_owner_prompts(date(2026, 8, 5)), [])
        self.assertIn("operating", first_prompt[0]["question"])

    def test_confirmation_gates_cohort_and_missing_margin_blocks_profitability(self):
        packet = build_riversdale_auction_packet(self._allocation(), today=date(2026, 8, 1))
        self.assertEqual(packet["status"], "awaiting_owner_auction_confirmation")
        self.assertEqual(packet["cohort"], [])
        self.assertTrue(packet["one_pig_one_active_outlet"])
        self.assertFalse(packet["creates_reservations"])

        packet = build_riversdale_auction_packet(self._allocation(), today=date(2026, 8, 1), confirmation={"operating": True, "confirmed_date": "2026-08-05"}, ledger_evidence={"SLOW": {"feed_cost_to_date": 100, "likely_auction_price": 150}, "APPROVED": {"feed_cost_to_date": 90, "likely_auction_price": 130}}, sam_demand={"summary": "No suitable direct-sale demand"}, oom_sakkie_preparation={"summary": "Transport checklist prepared"})
        self.assertEqual(packet["status"], "cohort_ready_for_owner_review")
        self.assertEqual([item["pig_id"] for item in packet["cohort"]], ["SLOW", "APPROVED"])
        self.assertEqual(packet["profitability_recommendation"], "ready_for_owner_review")
        self.assertEqual({item["pig_id"] for item in packet["excluded"]}, {"ORDER", "BREED"})

    def test_direct_sale_and_brand_risk_have_priority_over_auction(self):
        allocation = {"pigs": [
            {"pig_id": "DIRECT", "growth_class": "Extremely Slow", "readiness_bucket": "Livestock Candidate", "available_for_sale": "Yes"},
            {"pig_id": "RISK", "growth_class": "Extremely Slow", "readiness_bucket": "Livestock Candidate", "brand_quality_status": "Brand risk"},
        ]}
        packet = build_riversdale_auction_packet(allocation, today=date(2026, 8, 1), confirmation={"operating": True, "confirmed_date": "2026-08-05"})
        self.assertEqual(packet["cohort"], [])
        reasons = {row["pig_id"]: row["reason"] for row in packet["excluded"]}
        self.assertIn("customer-sale suitability", reasons["DIRECT"])
        self.assertIn("brand-quality", reasons["RISK"])

    def test_duplicate_or_missing_pig_identity_fails_closed_for_every_cohort_view(self):
        allocation = {"pigs": [
            {"pig_id": "DUP-1", "growth_class": "Extremely Slow", "readiness_bucket": "Livestock Candidate"},
            {"pig_id": "DUP-1", "growth_class": "Extremely Slow", "readiness_bucket": "Livestock Candidate", "tag_number": "conflicting-row"},
            {"pig_id": "", "growth_class": "Extremely Slow", "readiness_bucket": "Livestock Candidate"},
        ]}
        packet = build_riversdale_auction_packet(
            allocation, today=date(2026, 8, 1),
            confirmation={"operating": True, "confirmed_date": "2026-08-05"},
        )
        self.assertEqual(packet["cohort"], [])
        self.assertEqual(packet["candidate_preview"], [])
        self.assertFalse(packet["one_pig_one_active_outlet"])
        self.assertEqual([row["pig_id"] for row in packet["excluded"]], ["DUP-1", "DUP-1", ""])
        self.assertTrue(all("blocks non-overlapping" in row["reason"] for row in packet["excluded"]))

    def test_prompt_queue_uses_stable_outbox_idempotency_keys(self):
        calls = []
        def queue(event, payload, **kwargs):
            calls.append((event, payload, kwargs))
            return {"status": "created"}
        self.assertEqual(len(queue_due_owner_prompts(queue, today=date(2026, 7, 22))), 1)
        self.assertEqual(len(queue_due_owner_prompts(queue, today=date(2026, 7, 29))), 1)
        self.assertEqual(len({call[2]["idempotency_key"] for call in calls}), 2)
        self.assertTrue(all(call[0] == "NEEDS_OWNER_AUCTION_CONFIRMATION" for call in calls))

    def test_owner_confirmed_cycle_is_loaded_from_the_canonical_store(self):
        class Cursor:
            def execute(self, *_args): pass
            def fetchone(self): return (date(2026, 8, 5), True, datetime(2026, 7, 22, 9, 0))
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        class Connection:
            def cursor(self): return Cursor()
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        confirmation = load_owner_confirmed_cycle(today=date(2026, 8, 1), database_url="postgresql://test", connect_factory=lambda _url: Connection())
        self.assertEqual(confirmation["status"], "owner_confirmed_cycle_loaded")
        self.assertEqual(confirmation["confirmed_date"], "2026-08-05")

    @patch("modules.pig_weights.pig_weights_service.get_pig_allocation_readiness")
    @patch("modules.pig_weights.pig_weights_service.load_owner_confirmed_cycle")
    def test_recommendation_uses_persisted_cycle_when_no_override_is_supplied(self, load_cycle, allocation):
        allocation.return_value = self._allocation()
        load_cycle.return_value = {"operating": True, "confirmed_date": "2026-08-05"}
        packet = get_riversdale_auction_recommendation(today=date(2026, 8, 1), ledger_evidence={"SLOW": {"feed_cost_to_date": 100, "likely_auction_price": 150}, "APPROVED": {"feed_cost_to_date": 90, "likely_auction_price": 130}}, sam_demand={"summary": "No suitable direct-sale demand"}, oom_sakkie_preparation={"summary": "Transport checklist prepared"})
        self.assertEqual(packet["status"], "cohort_ready_for_owner_review")
        load_cycle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
