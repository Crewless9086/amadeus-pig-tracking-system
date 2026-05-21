import unittest
from decimal import Decimal
from unittest.mock import patch

from modules.orders.order_shadow_read import (
    compare_lines,
    compare_order_details,
    compare_shadow_order,
    normalize_value,
)


class OrderShadowReadTests(unittest.TestCase):
    def test_compare_order_details_matches_same_order_and_lines(self):
        sheet_detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Customer",
                "order_status": "Completed",
                "final_total": 1000.0,
            },
            "lines": [
                {
                    "order_line_id": "OL-1",
                    "order_id": "ORD-1",
                    "unit_price": 1000.0,
                    "line_status": "Reserved",
                }
            ],
        }
        shadow_detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Customer",
                "order_status": "Completed",
                "final_total": Decimal("1000.00"),
            },
            "lines": [
                {
                    "order_line_id": "OL-1",
                    "order_id": "ORD-1",
                    "unit_price": Decimal("1000.00"),
                    "line_status": "Reserved",
                }
            ],
        }

        comparison = compare_order_details(sheet_detail, shadow_detail)

        self.assertEqual(comparison["mismatch_count"], 0)

    def test_compare_lines_reports_missing_extra_and_field_mismatch(self):
        result = compare_lines(
            [
                {"order_line_id": "OL-1", "unit_price": 1000},
                {"order_line_id": "OL-MISSING", "unit_price": 1000},
            ],
            [
                {"order_line_id": "OL-1", "unit_price": 900},
                {"order_line_id": "OL-EXTRA", "unit_price": 1000},
            ],
        )

        self.assertEqual(result["missing_sample"], ["OL-MISSING"])
        self.assertEqual(result["extra_sample"], ["OL-EXTRA"])
        self.assertEqual(result["field_mismatch_sample"][0]["field"], "unit_price")

    def test_compare_shadow_order_never_writes_and_returns_mismatch_status(self):
        with patch("modules.orders.order_shadow_read.get_order_detail", return_value={
            "order": {"order_id": "ORD-1", "customer_name": "Sheet", "order_status": "Completed"},
            "lines": [],
        }), patch("modules.orders.order_shadow_read.get_shadow_order_detail", return_value=({
            "success": True,
            "shadow_detail": {
                "order": {"order_id": "ORD-1", "customer_name": "Shadow", "order_status": "Completed"},
                "lines": [],
                "status_logs": [],
            },
        }, 200)):
            result, status_code = compare_shadow_order("ORD-1")

        self.assertEqual(status_code, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "mismatches_found")
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_normalize_value_handles_decimals_and_blank_strings(self):
        self.assertEqual(normalize_value(Decimal("5.200")), 5.2)
        self.assertIsNone(normalize_value(" "))


if __name__ == "__main__":
    unittest.main()
