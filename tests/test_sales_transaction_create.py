import os
import unittest
from unittest.mock import Mock, patch

from modules.sales import sales_transaction_create
from modules.sales.sales_transaction_create import create_sales_transaction


VALID_PAYLOAD = {
    "sale_date": "2026-05-21",
    "sale_stream": "Slaughter",
    "buyer_name": "JC Slaghuis",
    "destination": "Bartelsfontein",
    "payment_status": "Unpaid",
    "payment_method": "EFT",
    "sale_status": "Confirmed",
    "created_by": "Charl",
    "deductions_total": 0,
    "items": [
        {
            "item_type": "Pig",
            "pig_id": "PIG-TEST-1",
            "tag_number": "S10",
            "quantity": 1,
            "unit_price": 1200,
            "pricing_basis": "Per_Pig",
        }
    ],
}


class SalesTransactionCreateTests(unittest.TestCase):
    def test_create_requires_created_by(self):
        payload = dict(VALID_PAYLOAD)
        payload["created_by"] = ""

        result, status_code = create_sales_transaction(payload, database_url="postgresql://example")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("created_by is required.", result["errors"])
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_create_rejects_non_slaughter_scope(self):
        payload = dict(VALID_PAYLOAD)
        payload["sale_stream"] = "Livestock"

        result, status_code = create_sales_transaction(payload, database_url="postgresql://example")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertTrue(any("Slaughter only" in error for error in result["errors"]))
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_create_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = create_sales_transaction(VALID_PAYLOAD)

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertFalse(result["configured"])
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["source"]["writes_to_supabase"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_create_inserts_header_and_items_and_reports_write(self):
        cursor = Mock()
        cursor.fetchall.return_value = []
        connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}), \
             patch.object(sales_transaction_create, "generate_sale_id", return_value="SALE-2026-ABC123"), \
             patch.object(sales_transaction_create, "generate_sale_item_id", return_value="SALEITEM-2026-ABC123"):
            result, status_code = create_sales_transaction(VALID_PAYLOAD)

        self.assertEqual(status_code, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["sale_id"], "SALE-2026-ABC123")
        self.assertEqual(result["created_counts"]["sales_transactions"], 1)
        self.assertEqual(result["created_counts"]["sales_transaction_items"], 1)
        self.assertEqual(result["sales_transaction"]["sale_status"], "Confirmed")
        self.assertEqual(result["sales_transaction"]["payment_status"], "Unpaid")
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertEqual(cursor.execute.call_count, 3)
        connection.cursor.assert_called_once()

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_create_blocks_duplicate_pig_before_insert(self):
        cursor = Mock()
        cursor.fetchall.return_value = [("PIG-TEST-1", "SALE-OLD")]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = create_sales_transaction(VALID_PAYLOAD)

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "duplicate_pig")
        self.assertEqual(result["duplicates"], [{"pig_id": "PIG-TEST-1", "sale_id": "SALE-OLD"}])
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(cursor.execute.call_count, 1)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_create_returns_safe_database_failure(self):
        psycopg = Mock(connect=Mock(side_effect=RuntimeError("boom")))

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = create_sales_transaction(VALID_PAYLOAD)

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sales_transaction_create_failed")
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
