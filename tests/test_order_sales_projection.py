import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from modules.orders import order_sales_projection
from modules.orders.order_sales_projection import build_projection, classify_sale_stream, map_payment_status


class OrderSalesProjectionTests(unittest.TestCase):
    def setUp(self):
        self.order = {"order_id": "ORD-2026-12BCCC", "order_status": "Completed", "requested_category": "Live Stock", "customer_name": "Michaels", "final_total": "7500.00", "payment_status": "Pending"}
        self.lines = [{"order_line_id": f"OL-{i}", "line_status": "Collected", "pig_id": f"PIG-{i}", "sale_category": "Grower", "unit_price": "1500.00"} for i in range(1, 6)]

    def test_michaels_five_lines_make_one_livestock_projection(self):
        result = build_projection(self.order, self.lines, "Tester")
        self.assertEqual((result["linked_order_id"], result["sale_stream"]), ("ORD-2026-12BCCC", "Livestock"))
        self.assertEqual((result["pig_count"], len(result["items"])), (5, 5))
        self.assertEqual((result["gross_total"], result["net_total"]), (Decimal("7500.00"), Decimal("7500.00")))
        self.assertEqual(result["payment_status"], "Unpaid")

    def test_identity_stable_and_missing_final_total_sums_lines(self):
        order = {**self.order, "final_total": None}
        first = build_projection(order, self.lines[:2])
        second = build_projection(order, self.lines[:2])
        self.assertEqual(first["sale_id"], second["sale_id"])
        self.assertEqual(first["gross_total"], Decimal("3000.00"))

    def test_final_total_reconciles_as_net_and_unexplained_overage_fails(self):
        result = build_projection({**self.order, "final_total": "7000.00"}, self.lines)
        self.assertEqual(result["gross_total"], Decimal("7500.00"))
        self.assertEqual(result["deductions_total"], Decimal("500.00"))
        self.assertEqual(result["net_total"], Decimal("7000.00"))
        with self.assertRaisesRegex(ValueError, "exceeds collected line snapshots"):
            build_projection({**self.order, "final_total": "8000.00"}, self.lines)

    def test_stream_precedence_and_payment_safety(self):
        self.assertEqual(classify_sale_stream({**self.order, "order_stream": "Meat", "notes": "abattoir"}, self.lines), "Meat")
        with self.assertRaisesRegex(ValueError, "order_stream"):
            classify_sale_stream({**self.order, "order_stream": "Auction"}, self.lines)
        self.assertEqual(classify_sale_stream({**self.order, "notes": "abattoir"}, self.lines), "Slaughter")
        self.assertEqual(classify_sale_stream({**self.order, "requested_category": "Pork freezer pack"}, self.lines), "Meat")
        self.assertEqual(map_payment_status("Paid"), "Paid")
        self.assertEqual(map_payment_status("POP received"), "Unpaid")

    def test_requires_completed_order_with_collected_lines(self):
        with self.assertRaisesRegex(ValueError, "Only Completed"):
            build_projection({**self.order, "order_status": "Approved"}, self.lines)
        with self.assertRaisesRegex(ValueError, "no Collected"):
            build_projection(self.order, [{**self.lines[0], "line_status": "Reserved"}])

    def test_upsert_sql_uses_database_conflict_keys_for_concurrency(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("SALE-ONE",)
        data = build_projection(self.order, self.lines)
        order_sales_projection._upsert_header(cursor, data)
        header_sql = cursor.execute.call_args.args[0]
        self.assertIn("on conflict (linked_order_id)", header_sql)

        cursor.reset_mock()
        order_sales_projection._reconcile_items(cursor, "SALE-ONE", data["items"])
        item_sql = cursor.execute.call_args_list[1].args[0]
        self.assertIn("on conflict (sale_id, order_line_id)", item_sql)

    def test_item_failure_escapes_transaction_for_rollback_and_retry(self):
        cursor = MagicMock()
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        connection = MagicMock()
        connection.cursor.return_value = cursor_context
        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection
        connect_factory = MagicMock(return_value=connection_context)
        projection = build_projection(self.order, self.lines)

        with patch.object(order_sales_projection, "_load_completed_order", return_value=(self.order, self.lines)), \
             patch.object(order_sales_projection, "build_projection", return_value=projection), \
             patch.object(order_sales_projection, "_upsert_header", return_value="SALE-ONE"), \
             patch.object(order_sales_projection, "_reconcile_items", side_effect=RuntimeError("item write failed")):
            with self.assertRaisesRegex(RuntimeError, "item write failed"):
                order_sales_projection.project_completed_order_to_sale("ORD-2026-12BCCC", connect_factory=connect_factory)

        self.assertIs(connection_context.__exit__.call_args.args[0], RuntimeError)


if __name__ == "__main__":
    unittest.main()
