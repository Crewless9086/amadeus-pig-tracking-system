import unittest

from scripts.order_status_log_diagnostic import build_order_status_log_diagnostic


class OrderStatusLogDiagnosticTests(unittest.TestCase):
    def test_classifies_status_log_link_reasons(self):
        order_rows = [
            {"Order_ID": "ORD-REAL", "Customer_Name": "Real Customer"},
            {"Order_ID": "ORD-TEST", "Customer_Name": "Charl N"},
        ]
        status_log_rows = [
            {"Order_Status_Log_ID": "OSL-1", "Order_ID": "ORD-REAL"},
            {"Order_Status_Log_ID": "OSL-2", "Order_ID": "ORD-TEST"},
            {"Order_Status_Log_ID": "OSL-3", "Order_ID": "ORD-MISSING"},
            {"Order_Status_Log_ID": "OSL-4", "Order_ID": ""},
        ]

        report = build_order_status_log_diagnostic(order_rows, status_log_rows, sample_limit=5)

        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "diagnostic_only")
        self.assertFalse(report["writes_to_supabase"])
        self.assertFalse(report["writes_to_sheets"])
        self.assertEqual(
            report["reason_counts"],
            {
                "included_candidate": 1,
                "missing_order_id": 1,
                "missing_parent_order": 1,
                "test_parent_order": 1,
            },
        )

    def test_sample_limit_is_respected(self):
        order_rows = []
        status_log_rows = [
            {"Order_Status_Log_ID": f"OSL-{index}", "Order_ID": f"ORD-MISSING-{index}"}
            for index in range(5)
        ]

        report = build_order_status_log_diagnostic(order_rows, status_log_rows, sample_limit=2)

        self.assertEqual(report["reason_counts"]["missing_parent_order"], 5)
        self.assertEqual(len(report["samples"]["missing_parent_order"]), 2)


if __name__ == "__main__":
    unittest.main()
