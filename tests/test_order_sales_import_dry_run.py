import unittest

from scripts.order_sales_import_dry_run import (
    ORDER_DOCUMENTS_SHEET,
    ORDER_INTAKE_ITEMS_SHEET,
    ORDER_INTAKE_STATE_SHEET,
    ORDER_LINES_SHEET,
    ORDER_MASTER_SHEET,
    ORDER_STATUS_LOG_SHEET,
    SALES_PRICING_SHEET,
    build_order_sales_import_dry_run,
)


class OrderSalesImportDryRunTests(unittest.TestCase):
    def _empty_rows(self):
        return {
            ORDER_MASTER_SHEET: [],
            ORDER_LINES_SHEET: [],
            ORDER_INTAKE_STATE_SHEET: [],
            ORDER_INTAKE_ITEMS_SHEET: [],
            ORDER_DOCUMENTS_SHEET: [],
            ORDER_STATUS_LOG_SHEET: [],
            SALES_PRICING_SHEET: [],
        }

    def test_dry_run_never_writes_to_supabase(self):
        report = build_order_sales_import_dry_run(self._empty_rows())

        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "dry_run_only")
        self.assertFalse(report["writes_to_supabase"])
        self.assertFalse(report["writes_to_sheets"])

    def test_excludes_charl_n_order_and_dependent_rows(self):
        rows = self._empty_rows()
        rows[ORDER_MASTER_SHEET] = [
            {
                "Order_ID": "ORD-REAL",
                "Customer_Name": "Real Customer",
                "Order_Status": "Completed",
            },
            {
                "Order_ID": "ORD-TEST",
                "Customer_Name": "Charl N",
                "Order_Status": "Completed",
            },
        ]
        rows[ORDER_LINES_SHEET] = [
            {"Order_Line_ID": "OL-REAL", "Order_ID": "ORD-REAL"},
            {"Order_Line_ID": "OL-TEST", "Order_ID": "ORD-TEST"},
        ]
        rows[ORDER_DOCUMENTS_SHEET] = [
            {"Document_ID": "DOC-TEST", "Order_ID": "ORD-TEST"},
        ]
        rows[ORDER_STATUS_LOG_SHEET] = [
            {"Order_Status_Log_ID": "OSL-TEST", "Order_ID": "ORD-TEST"},
        ]

        report = build_order_sales_import_dry_run(rows)

        order_reasons = {
            decision["row_id"]: decision["reason"]
            for decision in report["decisions"][ORDER_MASTER_SHEET]
        }
        line_reasons = {
            decision["row_id"]: decision["reason"]
            for decision in report["decisions"][ORDER_LINES_SHEET]
        }
        document_reasons = {
            decision["row_id"]: decision["reason"]
            for decision in report["decisions"][ORDER_DOCUMENTS_SHEET]
        }

        self.assertEqual(order_reasons["ORD-REAL"], "included_order")
        self.assertEqual(order_reasons["ORD-TEST"], "test_customer_charl_n")
        self.assertEqual(line_reasons["OL-REAL"], "included_with_order")
        self.assertEqual(line_reasons["OL-TEST"], "parent_order_excluded")
        self.assertEqual(document_reasons["DOC-TEST"], "parent_order_excluded")

    def test_excludes_unlinked_child_rows(self):
        rows = self._empty_rows()
        rows[ORDER_MASTER_SHEET] = [
            {"Order_ID": "ORD-REAL", "Customer_Name": "Real Customer", "Order_Status": "Completed"},
        ]
        rows[ORDER_LINES_SHEET] = [
            {"Order_Line_ID": "OL-MISSING", "Order_ID": "ORD-MISSING"},
        ]
        rows[ORDER_INTAKE_ITEMS_SHEET] = [
            {"Intake_Item_ID": "ITEM-MISSING", "Intake_ID": "INTAKE-MISSING"},
        ]

        report = build_order_sales_import_dry_run(rows)

        line_reason = report["decisions"][ORDER_LINES_SHEET][0]["reason"]
        intake_item_reason = report["decisions"][ORDER_INTAKE_ITEMS_SHEET][0]["reason"]

        self.assertEqual(line_reason, "missing_parent_order")
        self.assertEqual(intake_item_reason, "missing_parent_intake")
        self.assertIn("ORDER_LINES", report["link_issues"])
        self.assertIn("ORDER_INTAKE_ITEMS", report["link_issues"])

    def test_pricing_requires_core_fields(self):
        rows = self._empty_rows()
        rows[SALES_PRICING_SHEET] = [
            {"Sale_Category": "Grower Pigs", "Weight_Band": "35_to_39_Kg", "Price_Range": "1400"},
            {"Sale_Category": "Grower Pigs", "Weight_Band": "", "Price_Range": "1400"},
            {"Sale_Category": "Grower Pigs", "Weight_Band": "40_to_44_Kg", "Price_Range": ""},
        ]

        report = build_order_sales_import_dry_run(rows)
        reasons = [decision["reason"] for decision in report["decisions"][SALES_PRICING_SHEET]]

        self.assertEqual(reasons, ["included_pricing", "missing_weight_band", "missing_price"])

    def test_maps_included_rows_to_supabase_payload_shape(self):
        rows = self._empty_rows()
        rows[ORDER_MASTER_SHEET] = [
            {
                "Order_ID": "ORD-REAL",
                "Customer_Name": "Real Customer",
                "Customer_Phone": "+27 64 508 7806",
                "Order_Status": "Completed",
                "Requested_Quantity": "2",
                "Quoted_Total": "1400",
                "ConversationId": "1774",
            },
        ]
        rows[ORDER_LINES_SHEET] = [
            {
                "Order_Line_ID": "OL-REAL",
                "Order_ID": "ORD-REAL",
                "Unit_Price": "700",
                "Current_Weight_Kg": "35.5",
                "Line_Status": "Draft",
                "Reserved_Status": "Not_Reserved",
            },
        ]
        rows[ORDER_INTAKE_STATE_SHEET] = [
            {
                "Intake_ID": "INTAKE-REAL",
                "ConversationId": "1774",
                "Customer_Name": "Real Customer",
                "Draft_Order_ID": "ORD-REAL",
                "Ready_For_Draft": "Yes",
                "Missing_Fields": "payment_method, collection_location",
            },
        ]
        rows[ORDER_INTAKE_ITEMS_SHEET] = [
            {
                "Intake_Item_ID": "ITEM-REAL",
                "Intake_ID": "INTAKE-REAL",
                "Item_Key": "item_1",
                "Quantity": "1",
                "Linked_Order_Line_IDs": "OL-REAL",
            },
        ]
        rows[ORDER_DOCUMENTS_SHEET] = [
            {
                "Document_ID": "DOC-REAL",
                "Order_ID": "ORD-REAL",
                "Document_Type": "Quote",
                "Document_Ref": "Q-REAL",
                "Total": "1400",
            },
        ]
        rows[ORDER_STATUS_LOG_SHEET] = [
            {
                "Order_Status_Log_ID": "OSL-REAL",
                "Order_ID": "ORD-REAL",
                "New_Status": "Draft",
            },
        ]
        rows[SALES_PRICING_SHEET] = [
            {"Sale_Category": "Grower Pigs", "Weight_Band": "35_to_39_Kg", "Price_Range": "1400"},
        ]

        report = build_order_sales_import_dry_run(rows)

        self.assertEqual(report["payload_summary"]["orders"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["order_lines"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["sales_pricing"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["orders"]["sample_ids"], ["ORD-REAL"])
        self.assertEqual(report["payload_summary"]["order_documents"]["sample_ids"], ["DOC-REAL"])
        self.assertEqual(report["payload_summary"]["order_intakes"]["sample_ids"], ["INTAKE-REAL"])
        self.assertEqual(report["payload_summary"]["order_intake_items"]["sample_ids"], ["ITEM-REAL"])
        self.assertEqual(report["payload_summary"]["order_status_logs"]["sample_ids"], ["OSL-REAL"])

        order_payload = report["payloads"]["orders"][0]
        line_payload = report["payloads"]["order_lines"][0]
        intake_payload = report["payloads"]["order_intakes"][0]
        intake_item_payload = report["payloads"]["order_intake_items"][0]
        document_payload = report["payloads"]["order_documents"][0]
        pricing_payload = report["payloads"]["sales_pricing"][0]

        self.assertEqual(order_payload["order_id"], "ORD-REAL")
        self.assertEqual(order_payload["customer_phone_normalized"], "27645087806")
        self.assertEqual(order_payload["requested_quantity"], 2)
        self.assertEqual(order_payload["quoted_total"], 1400.0)
        self.assertEqual(line_payload["current_weight_kg"], 35.5)
        self.assertEqual(line_payload["unit_price"], 700.0)
        self.assertTrue(intake_payload["ready_for_draft"])
        self.assertEqual(intake_payload["missing_fields"], ["payment_method", "collection_location"])
        self.assertEqual(intake_item_payload["linked_order_line_ids"], ["OL-REAL"])
        self.assertEqual(document_payload["total"], 1400.0)
        self.assertTrue(pricing_payload["pricing_id"].startswith("PRICE-GROWER_PIGS_35_TO_39_KG"))
        self.assertEqual(pricing_payload["currency"], "ZAR")
        self.assertEqual(pricing_payload["import_batch_id"], "DRY_RUN_ONLY")

    def test_non_completed_order_is_excluded(self):
        rows = self._empty_rows()
        rows[ORDER_MASTER_SHEET] = [
            {
                "Order_ID": "ORD-DRAFT",
                "Customer_Name": "Real Customer",
                "Order_Status": "Draft",
            }
        ]

        report = build_order_sales_import_dry_run(rows)

        decision = report["decisions"][ORDER_MASTER_SHEET][0]
        self.assertEqual(decision["decision"], "exclude")
        self.assertEqual(decision["reason"], "not_completed_order")

    def test_excludes_unlinked_intake_without_order(self):
        rows = self._empty_rows()
        rows[ORDER_INTAKE_STATE_SHEET] = [
            {
                "Intake_ID": "INTAKE-UNLINKED",
                "ConversationId": "1774",
                "Customer_Name": "Real Customer",
                "Draft_Order_ID": "",
            }
        ]

        report = build_order_sales_import_dry_run(rows)

        decision = report["decisions"][ORDER_INTAKE_STATE_SHEET][0]
        self.assertEqual(decision["decision"], "exclude")
        self.assertEqual(decision["reason"], "unlinked_intake_without_order")


if __name__ == "__main__":
    unittest.main()
