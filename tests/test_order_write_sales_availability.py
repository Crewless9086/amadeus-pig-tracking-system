import unittest

from modules.orders import order_write


class OrderWriteSalesAvailabilityTests(unittest.TestCase):
    def test_available_pigs_preserve_herdmaster_stock_context(self):
        rows = [
            {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "sex": "Female",
                "available_for_sale": "Yes",
                "reserved_status": "",
                "current_weight_kg": 12,
                "last_weight_date": "2026-06-22",
                "weight_band": "10_to_14_Kg",
                "sale_category": "Weaner Piglets",
                "suggested_price_category": "Weaner Piglets|10_to_14_Kg",
                "live_stock_sale_reason": "Purpose = Sale and current weight maps to band.",
                "litter_id": "LIT-1",
                "sow_tag_number": "S1",
                "boar_tag_number": "B1",
                "family_context": {"litter_id": "LIT-1", "sow_tag_number": "S1"},
                "media_references": [],
                "media_reference_status": "not_configured",
            },
            {
                "pig_id": "PIG-2",
                "available_for_sale": "No",
                "reserved_status": "",
            },
        ]

        pigs = order_write._available_pigs_from_sales_rows(rows)

        self.assertEqual(len(pigs), 1)
        self.assertEqual(pigs[0]["pig_id"], "PIG-1")
        self.assertEqual(pigs[0]["last_weight_date"], "2026-06-22")
        self.assertEqual(pigs[0]["family_context"]["litter_id"], "LIT-1")
        self.assertEqual(pigs[0]["media_references"], [])
        self.assertEqual(pigs[0]["media_reference_status"], "not_configured")
        self.assertIn("Purpose = Sale", pigs[0]["live_stock_sale_reason"])


if __name__ == "__main__":
    unittest.main()
