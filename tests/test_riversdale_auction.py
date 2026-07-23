import unittest
from datetime import date

from modules.sales.riversdale_auction import build_owner_prompts, build_riversdale_auction_packet, first_wednesday, queue_due_owner_prompts


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
        prompts = build_owner_prompts(date(2026, 8, 5))
        self.assertEqual([item["days_before"] for item in prompts], [14, 7])
        self.assertEqual(len({item["idempotency_key"] for item in prompts}), 2)
        self.assertIn("operating", prompts[0]["question"])

    def test_confirmation_gates_cohort_and_missing_margin_blocks_profitability(self):
        packet = build_riversdale_auction_packet(self._allocation(), today=date(2026, 8, 1))
        self.assertEqual(packet["status"], "awaiting_owner_auction_confirmation")
        self.assertEqual(packet["cohort"], [])
        self.assertTrue(packet["one_pig_one_active_outlet"])
        self.assertFalse(packet["creates_reservations"])

        packet = build_riversdale_auction_packet(self._allocation(), today=date(2026, 8, 1), confirmation={"operating": True, "confirmed_date": "2026-08-05"}, ledger_evidence={"SLOW": {"feed_cost_to_date": 100, "likely_auction_price": 150}, "APPROVED": {"feed_cost_to_date": 90, "likely_auction_price": 130}})
        self.assertEqual(packet["status"], "cohort_ready_for_owner_review")
        self.assertEqual([item["pig_id"] for item in packet["cohort"]], ["SLOW", "APPROVED"])
        self.assertEqual(packet["profitability_recommendation"], "ready_for_owner_review")
        self.assertEqual({item["pig_id"] for item in packet["excluded"]}, {"ORDER", "BREED"})

    def test_prompt_queue_uses_stable_outbox_idempotency_keys(self):
        calls = []
        def queue(event, payload, **kwargs):
            calls.append((event, payload, kwargs))
            return {"status": "created"}
        self.assertEqual(len(queue_due_owner_prompts(queue, today=date(2026, 8, 5))), 2)
        self.assertEqual(len({call[2]["idempotency_key"] for call in calls}), 2)
        self.assertTrue(all(call[0] == "NEEDS_OWNER_AUCTION_CONFIRMATION" for call in calls))


if __name__ == "__main__":
    unittest.main()
