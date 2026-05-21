import unittest
from decimal import Decimal

from scripts.order_sales_shadow_compare import compare_table, normalize_value


class OrderSalesShadowCompareTests(unittest.TestCase):
    def test_compare_table_passes_matching_rows(self):
        result = compare_table(
            "orders",
            [
                {
                    "order_id": "ORD-1",
                    "customer_name": "Customer",
                    "order_status": "Completed",
                    "final_total": 1000.0,
                    "import_batch_id": "IMPORT-1",
                }
            ],
            [
                {
                    "order_id": "ORD-1",
                    "customer_name": "Customer",
                    "order_status": "Completed",
                    "final_total": Decimal("1000.00"),
                    "import_batch_id": "IMPORT-1",
                }
            ],
        )

        self.assertEqual(result["mismatch_count"], 0)

    def test_compare_table_reports_missing_extra_and_field_mismatch(self):
        result = compare_table(
            "orders",
            [
                {"order_id": "ORD-1", "customer_name": "Expected"},
                {"order_id": "ORD-MISSING", "customer_name": "Missing"},
            ],
            [
                {"order_id": "ORD-1", "customer_name": "Actual"},
                {"order_id": "ORD-EXTRA", "customer_name": "Extra"},
            ],
        )

        self.assertEqual(result["missing_sample"], ["ORD-MISSING"])
        self.assertEqual(result["extra_sample"], ["ORD-EXTRA"])
        self.assertEqual(result["field_mismatch_sample"][0]["field"], "customer_name")
        self.assertGreater(result["mismatch_count"], 0)

    def test_normalize_value_handles_database_types(self):
        self.assertEqual(normalize_value(Decimal("5.200")), 5.2)
        self.assertEqual(normalize_value("  text  "), "text")
        self.assertIsNone(normalize_value(None))


if __name__ == "__main__":
    unittest.main()
