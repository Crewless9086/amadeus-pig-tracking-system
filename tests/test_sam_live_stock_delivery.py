import unittest
from decimal import Decimal

from modules.sales.sam_live_stock_delivery import SAFE_CUSTOMER_WORDING, calculate_live_stock_delivery_option, live_stock_delivery_policy


class SamLiveStockDeliveryTests(unittest.TestCase):
    def test_default_rate_is_r20_per_one_way_km(self):
        result = calculate_live_stock_delivery_option(customer_requested_delivery=True, one_way_km="15.5", distance_source="owner_checked_google_maps", destination={"town": "Albertinia"})
        self.assertEqual(result["estimated_delivery_charge_rands"], Decimal("310.00"))
        self.assertEqual(result["fee_source"], "default_policy_rate")
        self.assertEqual(result["rate_rands_per_one_way_km"], Decimal("20.00"))
        self.assertEqual(result["status"], "estimate_ready_for_owner_review")

    def test_owner_approved_manual_amount_override_wins_without_km(self):
        result = calculate_live_stock_delivery_option(customer_requested_delivery=True, owner_override_amount="450", owner_override_approved=True, owner_override_reason="Difficult access route", owner_override_source="owner_manual_review")
        self.assertEqual(result["estimated_delivery_charge_rands"], Decimal("450.00"))
        self.assertEqual(result["fee_source"], "owner_override_amount")
        self.assertTrue(result["owner_review_required"])
        self.assertFalse(result["customer_send_allowed"])

    def test_missing_km_returns_status_instead_of_zero_fee(self):
        result = calculate_live_stock_delivery_option(customer_requested_delivery=True)
        self.assertEqual(result["status"], "one_way_km_required")
        self.assertIsNone(result["estimated_delivery_charge_rands"])

    def test_collection_first_and_safety_wording(self):
        policy = live_stock_delivery_policy()
        result = calculate_live_stock_delivery_option(customer_requested_delivery=False, one_way_km=10)
        self.assertTrue(policy["collection_first"])
        self.assertFalse(policy["openly_offer_delivery"])
        self.assertEqual(result["status"], "collection_first_not_requested")
        self.assertIn("Because you asked about delivery", SAFE_CUSTOMER_WORDING)
        self.assertIn("owner approves", SAFE_CUSTOMER_WORDING)
        for key in ("sends_customer_message", "creates_quote", "reserves_stock", "writes_order", "writes_farm_data"):
            self.assertFalse(result[key])

    def test_override_requires_owner_audit_fields(self):
        result = calculate_live_stock_delivery_option(customer_requested_delivery=True, one_way_km=10, distance_source="manual_route_check", owner_override_rate=25, owner_override_approved=True)
        self.assertEqual(result["status"], "owner_override_incomplete")
        self.assertIsNone(result["estimated_delivery_charge_rands"])

    def test_distance_source_is_required_for_rate_calculation(self):
        result = calculate_live_stock_delivery_option(customer_requested_delivery=True, one_way_km=10)
        self.assertEqual(result["status"], "distance_source_required")


if __name__ == "__main__":
    unittest.main()
