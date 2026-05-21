import os
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from modules.sales.sales_transaction_update import update_slaughter_sale_payment


VALID_UPDATE = {
    "updated_by": "Charl",
    "update_reason": "Butcher paid final amount",
    "line_total": 1500,
    "payment_status": "Paid",
    "payment_method": "EFT",
    "payment_date": "2026-05-21",
    "sale_status": "Completed",
    "carcass_weight_kg": 62.5,
}


class SalesTransactionUpdateTests(unittest.TestCase):
    def test_update_requires_operator_reason_amount_and_statuses(self):
        result, status_code = update_slaughter_sale_payment("SALE-1", {}, database_url="postgresql://example")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("updated_by is required.", result["errors"])
        self.assertIn("update_reason is required.", result["errors"])
        self.assertIn("line_total is required", " ".join(result["errors"]))
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_update_requires_payment_date_when_paid(self):
        payload = dict(VALID_UPDATE)
        payload["payment_date"] = ""

        result, status_code = update_slaughter_sale_payment("SALE-1", payload, database_url="postgresql://example")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertIn("payment_date is required when payment_status is Paid.", result["errors"])
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_update_rejects_cancelled_status_values(self):
        payload = dict(VALID_UPDATE)
        payload["payment_status"] = "Cancelled"

        result, status_code = update_slaughter_sale_payment("SALE-1", payload, database_url="postgresql://example")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertIn("Use the cancel endpoint", " ".join(result["errors"]))

    def test_update_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = update_slaughter_sale_payment("SALE-1", VALID_UPDATE)

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["source"]["writes_to_supabase"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_update_returns_not_found_without_write(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = update_slaughter_sale_payment("SALE-MISSING", VALID_UPDATE)

        self.assertEqual(status_code, 404)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(cursor.execute.call_count, 1)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_update_rejects_already_cancelled_transaction(self):
        cursor = Mock()
        cursor.fetchone.return_value = ("SALE-1", "Slaughter", "Cancelled", "Cancelled", Decimal("1200.00"), "Old note")
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = update_slaughter_sale_payment("SALE-1", VALID_UPDATE)

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "already_cancelled")
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(cursor.execute.call_count, 1)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_update_changes_header_first_item_and_appends_note(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            ("SALE-1", "Slaughter", "Confirmed", "Unpaid", Decimal("1200.00"), "Original note"),
            (
                "SALE-1",
                Decimal("1500.00"),
                Decimal("1500.00"),
                "Paid",
                "EFT",
                datetime(2026, 5, 21, 0, 0, 0),
                "Completed",
                "Original note\n\nPayment update...",
                datetime(2026, 5, 21, 7, 0, 0),
            ),
            (
                "ITEM-1",
                Decimal("1500.00"),
                Decimal("1500.00"),
                Decimal("62.500"),
                datetime(2026, 5, 21, 7, 0, 0),
            ),
        ]
        cursor.fetchall.return_value = [("ITEM-1", Decimal("1200.00"), None)]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = update_slaughter_sale_payment("SALE-1", VALID_UPDATE)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["sales_transaction"]["gross_total"], 1500.0)
        self.assertEqual(result["sales_transaction"]["payment_status"], "Paid")
        self.assertEqual(result["sales_transaction"]["payment_date"], "2026-05-21T00:00:00")
        self.assertEqual(result["sales_transaction"]["sale_status"], "Completed")
        self.assertEqual(result["item"]["line_total"], 1500.0)
        self.assertEqual(result["items_updated"], 1)
        self.assertEqual(result["item"]["carcass_weight_kg"], 62.5)
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertEqual(cursor.execute.call_count, 4)
        header_update_params = cursor.execute.call_args_list[2].args[1]
        self.assertIn("Original note", header_update_params[6])
        self.assertIn("Payment update", header_update_params[6])
        self.assertIn("Amount 1200.00 -> 1500", header_update_params[6])
        self.assertEqual(header_update_params[4], "2026-05-21")

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_update_batch_header_without_reallocating_multiple_items(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            ("SALE-1", "Slaughter", "Confirmed", "Unpaid", Decimal("2500.00"), ""),
            (
                "SALE-1",
                Decimal("2700.00"),
                Decimal("2700.00"),
                "Paid",
                "EFT",
                datetime(2026, 5, 21, 0, 0, 0),
                "Completed",
                "Payment update...",
                datetime(2026, 5, 21, 7, 0, 0),
            ),
        ]
        cursor.fetchall.return_value = [
            ("ITEM-1", Decimal("1200.00"), None),
            ("ITEM-2", Decimal("1300.00"), None),
        ]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        payload = dict(VALID_UPDATE)
        payload["line_total"] = 2700
        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = update_slaughter_sale_payment("SALE-1", payload)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["sales_transaction"]["gross_total"], 2700.0)
        self.assertIsNone(result["item"])
        self.assertEqual(result["items_updated"], 0)
        self.assertEqual(cursor.execute.call_count, 3)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_update_returns_safe_database_failure(self):
        psycopg = Mock(connect=Mock(side_effect=RuntimeError("boom")))

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = update_slaughter_sale_payment("SALE-1", VALID_UPDATE)

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sales_transaction_update_failed")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertNotIn("postgresql://", str(result))
        self.assertFalse(result["source"]["writes_to_supabase"])


def _mock_psycopg_connection(cursor):
    cursor_context = Mock()
    cursor_context.__enter__ = Mock(return_value=cursor)
    cursor_context.__exit__ = Mock(return_value=False)

    connection = Mock()
    connection.cursor.return_value = cursor_context
    connection_context = Mock()
    connection_context.__enter__ = Mock(return_value=connection)
    connection_context.__exit__ = Mock(return_value=False)

    psycopg = Mock(connect=Mock(return_value=connection_context))
    return connection, psycopg


if __name__ == "__main__":
    unittest.main()
