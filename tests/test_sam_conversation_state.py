import unittest

from modules.sales.sam_conversation_state import plan_live_stock_next_action


class SamConversationStateTests(unittest.TestCase):
    def test_plan_asks_for_missing_item_details(self):
        plan = plan_live_stock_next_action(
            {"conversation_id": "1845", "known_fields": {}, "items": []},
            {"customer_phone": "+27000000000"},
        )

        self.assertEqual(plan["next_action"], "ask_missing_field")
        self.assertIn("requested_items", plan["missing_fields"])

    def test_plan_create_draft_when_order_commitment_and_items_complete(self):
        plan = plan_live_stock_next_action(
            {
                "conversation_id": "1478",
                "known_fields": {
                    "collection_location": "Albertinia",
                    "order_commitment": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Piglet",
                    "weight_range": "7_to_9_Kg",
                    "status": "active",
                }],
            },
            {"customer_phone": "+27633640810"},
        )

        self.assertEqual(plan["next_action"], "create_draft")
        self.assertEqual(plan["missing_fields"], [])
        self.assertTrue(plan["ready_for_draft"])

    def test_plan_create_draft_then_quote_when_quote_requested(self):
        plan = plan_live_stock_next_action(
            {
                "conversation_id": "1478",
                "known_fields": {
                    "collection_location": "Albertinia",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Piglet",
                    "weight_range": "7_to_9_Kg",
                    "status": "active",
                }],
            },
            {"customer_phone": "+27633640810"},
        )

        self.assertEqual(plan["next_action"], "create_draft_then_quote")
        self.assertIn("draft_order_id", plan["missing_fields"])

    def test_plan_generate_quote_when_draft_exists(self):
        plan = plan_live_stock_next_action(
            {
                "conversation_id": "1478",
                "draft_order_id": "ORD-1",
                "known_fields": {
                    "collection_location": "Albertinia",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Piglet",
                    "weight_range": "7_to_9_Kg",
                    "status": "active",
                }],
            },
            {"customer_phone": "+27633640810"},
        )

        self.assertEqual(plan["next_action"], "generate_quote")
        self.assertEqual(plan["missing_fields"], [])
        self.assertTrue(plan["ready_for_quote"])


if __name__ == "__main__":
    unittest.main()
