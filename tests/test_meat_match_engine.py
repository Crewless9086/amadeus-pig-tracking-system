import unittest

from modules.oom_sakkie.sales_campaign_store import DEFAULT_MEAT_PRICE_BOOK
from modules.sales.meat_match_engine import build_butcher_meat_match


class MeatMatchEngineTests(unittest.TestCase):
    def test_heaviest_preference_selects_heaviest_ready_candidate(self):
        lead = {
            "interest": {
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "notes": "I want the heaviest one",
            },
            "events": [],
        }
        contract = {
            "lead_summary": {"product": "Half Carcass", "cut_set": "Set A"},
            "required_before_money_path": {},
        }
        candidates = [
            {"pig_id": "PIG-1", "tag_number": "101", "planning_bucket": "ready_now", "latest_weight_kg": 58},
            {"pig_id": "PIG-2", "tag_number": "102", "planning_bucket": "ready_now", "latest_weight_kg": 70},
        ]

        match = build_butcher_meat_match(lead, contract, candidates, DEFAULT_MEAT_PRICE_BOOK)

        self.assertEqual(match["decision"], "recommend")
        self.assertEqual(match["recommendation"]["pig_id"], "PIG-2")
        self.assertIn("heaviest suitable candidate requested", match["recommendation"]["match_reasons"])
        self.assertFalse(match["changes_stock"])
        self.assertFalse(match["creates_order"])

    def test_target_packed_weight_selects_closest_yield(self):
        lead = {"interest": {"product_type": "half_carcass", "cut_set": "Set A"}, "events": []}
        contract = {"lead_summary": {"product": "Half Carcass", "cut_set": "Set A"}, "required_before_money_path": {}}
        candidates = [
            {"pig_id": "PIG-LIGHT", "tag_number": "201", "planning_bucket": "ready_now", "latest_weight_kg": 50},
            {"pig_id": "PIG-MATCH", "tag_number": "202", "planning_bucket": "ready_now", "latest_weight_kg": 74},
        ]

        match = build_butcher_meat_match(
            lead,
            contract,
            candidates,
            DEFAULT_MEAT_PRICE_BOOK,
            {"target_packed_kg": "25"},
        )

        self.assertEqual(match["criteria"]["preference"], "closest_weight")
        self.assertEqual(match["recommendation"]["pig_id"], "PIG-MATCH")
        self.assertIn("kg away from target packed weight", " ".join(match["recommendation"]["match_reasons"]))

    def test_budget_fit_prefers_candidate_inside_budget(self):
        lead = {"interest": {"product_type": "half_carcass", "cut_set": "Set A"}, "events": []}
        contract = {"lead_summary": {"product": "Half Carcass", "cut_set": "Set A"}, "required_before_money_path": {}}
        candidates = [
            {"pig_id": "PIG-OVER", "tag_number": "301", "planning_bucket": "ready_now", "latest_weight_kg": 74},
            {"pig_id": "PIG-IN", "tag_number": "302", "planning_bucket": "ready_now", "latest_weight_kg": 58},
        ]

        match = build_butcher_meat_match(
            lead,
            contract,
            candidates,
            DEFAULT_MEAT_PRICE_BOOK,
            {"budget_amount": "2700"},
        )

        self.assertEqual(match["criteria"]["preference"], "budget_fit")
        self.assertEqual(match["recommendation"]["pig_id"], "PIG-IN")
        self.assertIn("inside stated budget", match["recommendation"]["match_reasons"])


if __name__ == "__main__":
    unittest.main()
