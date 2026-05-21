import unittest
from unittest.mock import MagicMock, Mock, patch

from scripts.order_sales_import_dry_run import (
    ORDER_LINES_SHEET,
    ORDER_MASTER_SHEET,
    SALES_PRICING_SHEET,
)
from scripts.order_sales_shadow_import import (
    IMPORT_BATCH_ID,
    IMPORT_TIMESTAMP,
    TABLE_INSERT_ORDER,
    apply_shadow_import,
    import_plan,
    load_local_env,
    normalize_shadow_row,
    prepare_shadow_payloads,
)


class OrderSalesShadowImportTests(unittest.TestCase):
    def _rows(self):
        return {
            "ORDER_MASTER": [
                {
                    "Order_ID": "ORD-COMPLETE",
                    "Customer_Name": "Real Customer",
                    "Order_Status": "Completed",
                    "Final_Total": "1000",
                },
                {
                    "Order_ID": "ORD-DRAFT",
                    "Customer_Name": "Real Customer",
                    "Order_Status": "Draft",
                },
            ],
            "ORDER_LINES": [
                {
                    "Order_Line_ID": "OL-COMPLETE",
                    "Order_ID": "ORD-COMPLETE",
                    "Unit_Price": "1000",
                },
                {
                    "Order_Line_ID": "OL-DRAFT",
                    "Order_ID": "ORD-DRAFT",
                    "Unit_Price": "1000",
                },
            ],
            "ORDER_INTAKE_STATE": [],
            "ORDER_INTAKE_ITEMS": [],
            "ORDER_DOCUMENTS": [],
            "ORDER_STATUS_LOG": [
                {
                    "Order_Status_Log_ID": "OSL-COMPLETE",
                    "Order_ID": "ORD-COMPLETE",
                    "New_Status": "Completed",
                }
            ],
            "SALES_PRICING": [
                {
                    "Sale_Category": "Grower Pigs",
                    "Weight_Band": "35_to_39_Kg",
                    "Price_Range": "1000",
                }
            ],
        }

    def test_plan_only_never_writes(self):
        plan = import_plan(self._rows())

        self.assertTrue(plan["success"])
        self.assertEqual(plan["mode"], "plan_only")
        self.assertFalse(plan["writes_to_supabase"])
        self.assertFalse(plan["writes_to_sheets"])
        self.assertEqual(plan["payload_summary"]["orders"]["rows"], 1)
        self.assertEqual(plan["payload_summary"]["order_lines"]["rows"], 1)

    def test_payloads_use_shadow_import_batch_id(self):
        _, payloads = prepare_shadow_payloads(self._rows())

        self.assertEqual(payloads["orders"][0]["import_batch_id"], IMPORT_BATCH_ID)
        self.assertEqual(payloads["order_lines"][0]["import_batch_id"], IMPORT_BATCH_ID)
        self.assertEqual(payloads["sales_pricing"][0]["import_batch_id"], IMPORT_BATCH_ID)

    def test_shadow_payloads_fill_not_null_timestamp_defaults(self):
        row = normalize_shadow_row(
            "sales_pricing",
            {
                "pricing_id": "PRICE-1",
                "effective_from": "2026-05-21",
                "created_at": None,
                "updated_at": None,
            },
        )

        self.assertEqual(row["created_at"], "2026-05-21")
        self.assertEqual(row["updated_at"], "2026-05-21")

        status_row = normalize_shadow_row(
            "order_status_logs",
            {"status_log_id": "OSL-1", "status_date": None, "created_at": None},
        )
        self.assertEqual(status_row["created_at"], IMPORT_TIMESTAMP)

    def test_apply_requires_database_url(self):
        report, exit_code = apply_shadow_import(self._rows(), "")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertFalse(report["writes_to_supabase"])
        self.assertEqual(report["status"], "not_configured")

    def test_load_local_env_reads_repo_env_file(self):
        load_dotenv = Mock(return_value=True)

        loaded = load_local_env(load_dotenv)

        load_dotenv.return_value = True
        self.assertTrue(loaded)
        self.assertTrue(str(load_dotenv.call_args.args[0]).endswith(".env"))

    def test_insert_order_respects_foreign_keys(self):
        self.assertEqual(
            TABLE_INSERT_ORDER,
            [
                "sales_pricing",
                "orders",
                "order_lines",
                "order_intakes",
                "order_intake_items",
                "order_documents",
                "order_status_logs",
            ],
        )

    @patch("scripts.order_sales_shadow_import._upsert_rows")
    def test_apply_uses_one_transaction_and_reports_counts(self, upsert_rows):
        connection = MagicMock()
        cursor = Mock()
        connect = Mock()
        connect.return_value = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        upsert_rows.side_effect = [1, 1, 1, 0, 0, 0, 1]

        report, exit_code = apply_shadow_import(
            self._rows(),
            "postgresql://example",
            connect_factory=connect,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertTrue(report["writes_to_supabase"])
        self.assertFalse(report["writes_to_sheets"])
        self.assertEqual(report["inserted_or_updated"]["orders"], 1)
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
