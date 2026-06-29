import unittest
from unittest.mock import Mock

from scripts import order_sales_live_import as live_import


def sheet_rows():
    return {
        "ORDER_MASTER": [
            {
                "Order_ID": "ORD-ACTIVE",
                "Customer_Name": "Owner Customer",
                "Order_Status": "Approved",
                "Requested_Quantity": "2",
            },
            {
                "Order_ID": "ORD-COMPLETED",
                "Customer_Name": "Owner Customer",
                "Order_Status": "Completed",
            },
            {
                "Order_ID": "ORD-TEST",
                "Customer_Name": "Charl N",
                "Order_Status": "Approved",
            },
        ],
        "ORDER_LINES": [
            {"Order_Line_ID": "OL-ACTIVE", "Order_ID": "ORD-ACTIVE", "Line_Status": "Draft"},
            {"Order_Line_ID": "OL-COMPLETED", "Order_ID": "ORD-COMPLETED", "Line_Status": "Collected"},
            {"Order_Line_ID": "OL-TEST", "Order_ID": "ORD-TEST", "Line_Status": "Draft"},
        ],
        "ORDER_INTAKE_STATE": [
            {"Intake_ID": "INTAKE-UNLINKED", "ConversationId": "C1", "Customer_Name": "Owner Customer"},
            {"Intake_ID": "INTAKE-TEST", "ConversationId": "C2", "Customer_Name": "Charl N"},
        ],
        "ORDER_INTAKE_ITEMS": [
            {"Intake_Item_ID": "ITEM-1", "Intake_ID": "INTAKE-UNLINKED", "Item_Key": "1"},
            {"Intake_Item_ID": "ITEM-TEST", "Intake_ID": "INTAKE-TEST", "Item_Key": "1"},
        ],
        "ORDER_DOCUMENTS": [
            {"Document_ID": "DOC-1", "Order_ID": "ORD-ACTIVE", "Document_Type": "Quote", "Document_Ref": "Q1"},
            {"Document_ID": "DOC-TEST", "Order_ID": "ORD-TEST", "Document_Type": "Quote", "Document_Ref": "Q2"},
        ],
        "ORDER_STATUS_LOG": [
            {"Order_Status_Log_ID": "LOG-1", "Order_ID": "ORD-ACTIVE", "New_Status": "Approved"},
            {"Order_Status_Log_ID": "LOG-ORPHAN", "Order_ID": "ORD-MISSING", "New_Status": "Draft"},
        ],
        "SALES_PRICING": [
            {"Sale_Category": "Grower", "Weight_Band": "60_to_64_Kg", "Price_Range": "1200"},
        ],
    }


class OrderSalesLiveImportTests(unittest.TestCase):
    def test_live_plan_includes_non_test_active_and_completed_orders(self):
        report = live_import.build_live_order_import_plan(sheet_rows())

        self.assertTrue(report["success"])
        self.assertEqual(report["import_batch_id"], live_import.IMPORT_BATCH_ID)
        self.assertEqual(report["payload_summary"]["orders"]["rows"], 2)
        self.assertEqual(report["payload_summary"]["order_lines"]["rows"], 2)
        self.assertEqual(report["payload_summary"]["order_intakes"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["order_intake_items"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["order_documents"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["order_status_logs"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["sales_pricing"]["rows"], 1)
        self.assertEqual(
            report["summaries"]["ORDER_MASTER"]["reason_counts"],
            {"included_live_order": 2, "test_customer_charl_n": 1},
        )
        self.assertEqual(
            report["link_issues"]["ORDER_STATUS_LOG"],
            {"missing_parent_order": 1},
        )

    def test_apply_uses_upserts_and_never_writes_sheets(self):
        calls = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return FakeCursor()

        def fake_upsert(cursor, table_name, rows):
            calls.append((table_name, len(rows)))
            return len(rows)

        connect_factory = Mock(return_value=FakeConnection())
        original_upsert = live_import._upsert_rows
        try:
            live_import._upsert_rows = fake_upsert
            result, status = live_import.apply_live_order_import(
                sheet_rows(),
                "postgres://example",
                connect_factory=connect_factory,
            )
        finally:
            live_import._upsert_rows = original_upsert

        self.assertEqual(status, 0)
        self.assertTrue(result["success"])
        self.assertTrue(result["writes_to_supabase"])
        self.assertFalse(result["writes_to_sheets"])
        self.assertIn(("orders", 2), calls)
        self.assertIn(("order_lines", 2), calls)


if __name__ == "__main__":
    unittest.main()
