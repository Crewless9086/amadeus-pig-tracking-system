import unittest

from modules.sales.sam_pricing import (
    list_live_stock_price_entries,
    record_live_stock_price_entry,
    resolve_live_stock_price_rule,
)


class SamPricingTests(unittest.TestCase):
    def test_live_stock_price_defaults_match_sales_pricing_bands(self):
        result, status_code = list_live_stock_price_entries(database_url="")

        self.assertEqual(status_code, 200)
        self.assertEqual(result["source"], "code_defaults")
        self.assertEqual(len(result["price_entries"]), 21)
        rule = resolve_live_stock_price_rule("Weaner", "10_to_14_Kg", database_url="")
        self.assertTrue(rule["found"], rule)
        self.assertEqual(rule["sale_category"], "Weaner Piglets")
        self.assertEqual(rule["unit_price"], 500.0)

    def test_live_stock_price_write_requires_database(self):
        result, status_code = record_live_stock_price_entry(
            {
                "sale_category": "Weaner Piglets",
                "weight_band": "10_to_14_Kg",
                "unit_price": "550",
            },
            database_url="",
        )

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")

    def test_live_stock_price_validation_blocks_missing_weight_band(self):
        result, status_code = record_live_stock_price_entry(
            {"sale_category": "Weaner Piglets", "unit_price": "550"},
            database_url="postgres://not-used",
        )

        self.assertEqual(status_code, 400)
        self.assertIn("Weight_Band is required.", result["errors"])


if __name__ == "__main__":
    unittest.main()
