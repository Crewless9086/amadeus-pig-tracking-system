import unittest

from modules.sales.sam_sales_router import (
    LANE_FARM_GENERAL,
    LANE_LIVE_STOCK,
    LANE_MEAT,
    LANE_OWNER_HANDOFF,
    LANE_SLAUGHTER,
    LANE_UNCLEAR,
    classify_sam_sales_lane,
)


class SamSalesRouterTests(unittest.TestCase):
    def assert_lane(self, message, lane):
        result = classify_sam_sales_lane(message)
        self.assertEqual(result["lane"], lane, result)
        self.assertFalse(result["writes_allowed"], result)
        self.assertFalse(result["customer_send_allowed"], result)
        return result

    def test_routes_clear_meat_request_to_meat_sales(self):
        result = self.assert_lane("Hi, I want a half carcass Set A pork pack for the freezer.", LANE_MEAT)

        self.assertGreaterEqual(result["confidence"], 0.9)
        self.assertIn("SAM Meat Sales", result["next_action"])

    def test_routes_clear_live_stock_request_to_live_stock_sales(self):
        result = self.assert_lane("I need 3 female weaners around 10 to 15kg next week.", LANE_LIVE_STOCK)

        self.assertGreaterEqual(result["confidence"], 0.9)
        self.assertIn("live-stock", result["next_action"].lower())

    def test_routes_piglets_for_sale_to_live_stock_sales(self):
        result = self.assert_lane("Do you have piglets for sale? I want two to raise.", LANE_LIVE_STOCK)

        self.assertGreaterEqual(result["confidence"], 0.86)

    def test_routes_pigs_for_sale_to_live_stock_sales(self):
        result = self.assert_lane("Do you have pigs for sale?", LANE_LIVE_STOCK)

        self.assertGreaterEqual(result["confidence"], 0.86)

    def test_routes_slaughter_or_abattoir_intent_separately(self):
        result = self.assert_lane("I need an 80kg pig for slaughter and abattoir help.", LANE_SLAUGHTER)

        self.assertTrue(result["owner_gate_required"], result)
        self.assertIn("slaughter", result["next_action"])

    def test_mixed_meat_and_live_stock_requires_clarification(self):
        result = self.assert_lane("I want pork for the freezer and maybe two live piglets.", LANE_UNCLEAR)

        self.assertTrue(result["owner_gate_required"], result)
        self.assertIn("mixed_sales_intent", result["reasons"])

    def test_negated_live_stock_does_not_contaminate_meat_lane(self):
        result = self.assert_lane("Not live pigs, I want pork chops and a freezer pack.", LANE_MEAT)

        self.assertIn("negated_live_stock_sales:live pigs", result["reasons"])

    def test_negated_meat_does_not_contaminate_live_stock_lane(self):
        result = self.assert_lane("Not meat, I want live pigs to raise.", LANE_LIVE_STOCK)

        self.assertIn("negated_meat_sales:meat", result["reasons"])

    def test_owner_payment_or_discount_terms_handoff(self):
        result = self.assert_lane("I paid and sent POP, can you give me a discount?", LANE_OWNER_HANDOFF)

        self.assertTrue(result["owner_gate_required"], result)

    def test_general_farm_question_is_not_sales_order(self):
        result = self.assert_lane("Where is Amadeus farm and what hours are you open?", LANE_FARM_GENERAL)

        self.assertLess(result["confidence"], 0.9)

    def test_prior_context_is_low_confidence_without_fresh_signal(self):
        result = classify_sam_sales_lane("Okay thanks", prior_context={"lane": LANE_LIVE_STOCK})

        self.assertEqual(result["lane"], LANE_LIVE_STOCK, result)
        self.assertLess(result["confidence"], 0.96)
        self.assertFalse(result["writes_allowed"], result)


if __name__ == "__main__":
    unittest.main()
