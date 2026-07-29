import unittest

from modules.sales.sam_live_stock_runtime import (
    build_live_stock_customer_guidance,
    build_live_stock_qualification_followup,
    extract_live_stock_facts,
    review_sam_live_stock_conversation,
)
from modules.sales import sales_transaction_routes


class SamLiveStockContinuousFollowupTests(unittest.TestCase):
    def test_known_customer_weight_band_without_repeated_kg_is_preserved(self):
        facts = extract_live_stock_facts("Female and male 7 to 19")
        self.assertEqual(facts["weight_range"], "7-19 kg")
        self.assertEqual(facts["category"], "weaner")
        self.assertEqual(facts["sex"], "split")
        guidance = build_live_stock_customer_guidance(
            {"customer_name": "Misokuhle"},
            facts,
        )
        self.assertEqual(guidance["questions_asked"], ["how many do you need"])
        self.assertNotIn("Which size", guidance["reply_text"])
        self.assertIn("Price and current availability still need", guidance["reply_text"])

    def test_known_weight_and_sex_asks_only_quantity_even_with_other_missing_fields(self):
        facts = extract_live_stock_facts("Female and male 7 to 19")
        guidance = build_live_stock_customer_guidance(
            {"customer_name": "Misokuhle", "content": "Female and male 7 to 19"},
            facts,
        )
        self.assertEqual(guidance["guidance_scope"], "qualification_only")
        self.assertEqual(guidance["questions_asked"], ["how many do you need"])
        self.assertNotIn("location", guidance["reply_text"].lower())
        self.assertNotIn("collect", guidance["reply_text"].lower())

    def test_split_sex_quantities_are_summed(self):
        facts = extract_live_stock_facts(
            "I want weaned piglets. I would like 4 females and one male."
        )
        self.assertEqual(facts["quantity"], 5)
        self.assertEqual(facts["sex"], "split")

    def test_location_and_timing_continue_while_commercial_facts_wait(self):
        followup = build_live_stock_qualification_followup(
            {
                "customer_name": "Azulidgaf",
                "content": (
                    "I want weaned piglets. I would like 4 females "
                    "and one male."
                ),
            },
            {
                "category": "weaner",
                "quantity": 5,
                "sex": "split",
                "location": "",
                "timing": "",
            },
            ["location", "timing"],
        )
        self.assertTrue(followup["applicable"])
        self.assertIn(
            "what town or area are you in",
            followup["reply_text"].lower(),
        )
        self.assertNotIn("when would you need them", followup["reply_text"])
        self.assertIn(
            "Price and current availability still need to be confirmed",
            followup["reply_text"],
        )
        self.assertFalse(followup["delivery_promised"])

    def test_known_riversdale_with_no_safe_question_is_not_customer_reply(self):
        followup = build_live_stock_qualification_followup(
            {"customer_name": "Delia"},
            {
                "category": "weaner",
                "quantity": 5,
                "sex": "split",
                "location": "Riversdale",
                "timing": "this week",
            },
            ["order_commitment"],
        )
        self.assertFalse(followup["applicable"])
        self.assertEqual(followup["reply_text"], "")

    def test_delivery_exception_does_not_owner_gate_safe_timing_question(self):
        decision = {
            "sales_lane": "live_stock_sales",
            "conversation_ownership": "AUTO_SPECIALIST",
            "suggested_reply_text": (
                "Thanks, I’ve noted Riversdale. Delivery still needs owner "
                "confirmation and is not promised. When would you need them?"
            ),
            "missing_fields": ["timing"],
            "blockers": [],
            "delivery_owner_exception": {
                "eligible": True,
                "customer_delivery_promised": False,
            },
            "protected_owner_exception_required": True,
        }
        review = review_sam_live_stock_conversation(
            {"content": "Riversdale"},
            {
                "location": "Riversdale",
                "transport_expectation": "delivery_requested",
            },
            decision,
        )
        self.assertTrue(review["safe_to_send"])
        self.assertFalse(review["owner_authority_required"])
        event = {
            "sam_reply_excerpt": decision["suggested_reply_text"],
            "recommended_action": "ask_one_missing_detail",
            "decision_json": decision,
            "review_json": review,
        }
        self.assertTrue(
            sales_transaction_routes
            ._sam_live_stock_owner_review_notification_needed(event)
        )


if __name__ == "__main__":
    unittest.main()
