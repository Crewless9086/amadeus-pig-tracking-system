import os
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from modules.sales.sales_transaction_cancel import cancel_sales_transaction


class SalesTransactionCancelTests(unittest.TestCase):
    def test_cancel_requires_cancelled_by_and_reason(self):
        result, status_code = cancel_sales_transaction("SALE-1", {}, database_url="postgresql://example")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("cancelled_by is required.", result["errors"])
        self.assertIn("cancel_reason is required.", result["errors"])
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_cancel_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = cancel_sales_transaction(
                "SALE-1",
                {"cancelled_by": "Charl", "cancel_reason": "Test cancel"},
            )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["source"]["writes_to_supabase"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_cancel_returns_not_found_without_write(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = cancel_sales_transaction(
                "SALE-MISSING",
                {"cancelled_by": "Charl", "cancel_reason": "Wrong sale"},
            )

        self.assertEqual(status_code, 404)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(cursor.execute.call_count, 1)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_cancel_is_idempotent_for_already_cancelled_transaction(self):
        cursor = Mock()
        cursor.fetchone.return_value = (
            "SALE-1",
            "Cancelled",
            "Cancelled",
            "Already cancelled",
            datetime(2026, 5, 21, 6, 0, 0),
        )
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = cancel_sales_transaction(
                "SALE-1",
                {"cancelled_by": "Charl", "cancel_reason": "Repeat click"},
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "already_cancelled")
        self.assertEqual(result["sales_transaction"]["sale_status"], "Cancelled")
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(cursor.execute.call_count, 1)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_cancel_marks_transaction_cancelled_and_appends_note(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (
                "SALE-1",
                "Confirmed",
                "Unpaid",
                "Original note",
                datetime(2026, 5, 21, 6, 0, 0),
            ),
            (
                "SALE-1",
                "Cancelled",
                "Cancelled",
                "Original note\n\nCancelled 2026-05-21T06:30:00+00:00 by Charl: Synthetic test complete",
                datetime(2026, 5, 21, 6, 30, 0),
            ),
        ]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = cancel_sales_transaction(
                "SALE-1",
                {"cancelled_by": "Charl", "cancel_reason": "Synthetic test complete"},
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["sales_transaction"]["sale_status"], "Cancelled")
        self.assertEqual(result["sales_transaction"]["payment_status"], "Cancelled")
        self.assertIn("Synthetic test complete", result["sales_transaction"]["notes"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertEqual(cursor.execute.call_count, 2)
        update_params = cursor.execute.call_args_list[1].args[1]
        self.assertIn("Original note", update_params[0])
        self.assertIn("by Charl: Synthetic test complete", update_params[0])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_cancel_returns_safe_database_failure(self):
        psycopg = Mock(connect=Mock(side_effect=RuntimeError("boom")))

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = cancel_sales_transaction(
                "SALE-1",
                {"cancelled_by": "Charl", "cancel_reason": "Failure test"},
            )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sales_transaction_cancel_failed")
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
