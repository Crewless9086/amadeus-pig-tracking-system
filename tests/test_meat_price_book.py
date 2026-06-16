import unittest

from modules.oom_sakkie.sales_campaign_store import (
    DEFAULT_MEAT_PRICE_BOOK,
    build_meat_pricing_estimate_from_contract,
    record_meat_price_book_entry,
)


class MeatPriceBookTests(unittest.TestCase):
    def test_estimate_prefills_owner_approval_from_default_half_set_a_rule(self):
        lead = {
            "lead_id": "OSK-SALES-LEAD-TEST",
            "contact_label": "Charl N",
            "interest": {
                "product": "Half Carcass",
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "timing": "next available week",
                "delivery_or_collection": "collection",
                "payment_method": "EFT",
            },
            "events": [],
        }
        contract = {
            "lead_summary": {
                "product": "Half Carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
            },
            "required_before_money_path": {},
        }

        estimate = build_meat_pricing_estimate_from_contract(lead, contract, DEFAULT_MEAT_PRICE_BOOK)

        approval = estimate["recommended_owner_approval"]
        self.assertEqual(approval["price_per_kg"], "R130.00/kg")
        self.assertEqual(approval["available_week"], "next available week")
        self.assertIn("19-21kg", approval["estimated_weight_or_size"])
        self.assertIn("50% deposit", approval["deposit_rule"])
        self.assertEqual(approval["payment_method"], "EFT")
        self.assertEqual(approval["delivery_or_collection"], "collection")
        self.assertEqual(estimate["estimated_total_label"], "R2,600.00")
        self.assertFalse(estimate["creates_order"])
        self.assertFalse(estimate["changes_stock"])

    def test_estimate_uses_selected_pig_live_weight_when_available(self):
        lead = {
            "interest": {
                "product_type": "half_carcass",
                "cut_set": "Set A",
            },
            "events": [],
        }

        estimate = build_meat_pricing_estimate_from_contract(
            lead,
            {"lead_summary": {}, "required_before_money_path": {}},
            DEFAULT_MEAT_PRICE_BOOK,
            {"selected_pig_live_weight_kg": "62"},
        )

        self.assertEqual(estimate["yield_estimate"]["source"], "selected_pig_latest_live_weight")
        self.assertIn("19.6-21.7kg", estimate["recommended_owner_approval"]["estimated_weight_or_size"])

    def test_price_book_entry_requires_database_for_writes(self):
        result, status_code = record_meat_price_book_entry(
            {"product_type": "half_carcass", "price_amount": "135"},
            database_url="",
        )

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
