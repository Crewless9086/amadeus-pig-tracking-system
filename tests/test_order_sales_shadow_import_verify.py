import unittest
from unittest.mock import MagicMock, Mock

from scripts.order_sales_shadow_import import TABLE_INSERT_ORDER
from scripts.order_sales_shadow_import_verify import verify_shadow_import


class OrderSalesShadowImportVerifyTests(unittest.TestCase):
    def test_requires_database_url(self):
        report, exit_code = verify_shadow_import("")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "not_configured")

    def test_counts_each_shadow_table(self):
        connection = MagicMock()
        cursor = MagicMock()
        connect = Mock()
        connect.return_value = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        fetchone_values = [(index,) for index, _table in enumerate(TABLE_INSERT_ORDER, start=1)]
        cursor.fetchone.side_effect = fetchone_values
        cursor.fetchall.return_value = [("SAMPLE-1",)]

        report, exit_code = verify_shadow_import(
            "postgresql://example",
            import_batch_id="IMPORT-TEST",
            connect_factory=connect,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["counts"]["orders"], 2)
        self.assertEqual(report["sample_ids"]["orders"], ["SAMPLE-1"])
        self.assertEqual(cursor.execute.call_count, len(TABLE_INSERT_ORDER) * 2)


if __name__ == "__main__":
    unittest.main()
