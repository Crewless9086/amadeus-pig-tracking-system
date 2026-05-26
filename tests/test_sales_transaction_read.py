import os
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from modules.sales.sales_transaction_read import (
    get_monthly_sales_transaction_summary,
    list_sales_transactions,
)


class SalesTransactionReadTests(unittest.TestCase):
    def test_list_sales_transactions_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = list_sales_transactions()

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertNotIn("DATABASE_URL=", str(result))

    def test_list_sales_transactions_rejects_invalid_stream(self):
        with self.assertRaises(ValueError):
            list_sales_transactions(sale_stream="Auction")

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_list_sales_transactions_returns_json_safe_rows_and_never_writes(self):
        cursor = Mock()
        cursor.description = [
            ("sale_id",),
            ("sale_date",),
            ("sale_stream",),
            ("buyer_name",),
            ("gross_total",),
            ("item_count",),
        ]
        cursor.fetchall.return_value = [
            (
                "SALE-1",
                datetime(2026, 5, 21, 10, 0, 0),
                "Slaughter",
                "Abattoir",
                Decimal("1200.00"),
                2,
            )
        ]
        cursor_context = Mock()
        cursor_context.__enter__ = Mock(return_value=cursor)
        cursor_context.__exit__ = Mock(return_value=False)

        connection = Mock()
        connection.cursor.return_value = cursor_context
        connection_context = Mock()
        connection_context.__enter__ = Mock(return_value=connection)
        connection_context.__exit__ = Mock(return_value=False)

        psycopg = Mock(connect=Mock(return_value=connection_context))

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = list_sales_transactions(sale_stream="Slaughter", limit=5)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["sale_stream"], "Slaughter")
        self.assertEqual(result["sales_transactions"][0]["gross_total"], 1200.0)
        self.assertEqual(result["sales_transactions"][0]["sale_date"], "2026-05-21T10:00:00")
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])
        cursor.execute.assert_called_once()

    def test_monthly_sales_transaction_summary_reports_missing_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = get_monthly_sales_transaction_summary("2026-05-26")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["report_month"], "2026-05")
        self.assertEqual(result["streams"]["slaughter"]["transaction_count"], 0)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_monthly_sales_transaction_summary_returns_stream_counts_and_values(self):
        cursor = Mock()
        cursor.description = [
            ("sale_stream",),
            ("transaction_count",),
            ("pig_count",),
            ("gross_total",),
            ("net_total",),
            ("item_count",),
        ]
        cursor.fetchall.return_value = [
            ("Slaughter", 1, 1, Decimal("2500.00"), Decimal("2400.00"), 1),
            ("Livestock", 2, 5, Decimal("5000.00"), Decimal("5000.00"), 5),
        ]
        cursor_context = Mock()
        cursor_context.__enter__ = Mock(return_value=cursor)
        cursor_context.__exit__ = Mock(return_value=False)

        connection = Mock()
        connection.cursor.return_value = cursor_context
        connection_context = Mock()
        connection_context.__enter__ = Mock(return_value=connection)
        connection_context.__exit__ = Mock(return_value=False)

        psycopg = Mock(connect=Mock(return_value=connection_context))

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_monthly_sales_transaction_summary("2026-05-26")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["streams"]["slaughter"]["transaction_count"], 1)
        self.assertEqual(result["streams"]["slaughter"]["net_total"], 2400.0)
        self.assertEqual(result["streams"]["livestock"]["transaction_count"], 2)
        self.assertEqual(result["totals"]["transaction_count"], 3)
        self.assertEqual(result["totals"]["net_total"], 7400.0)
        cursor.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
