import unittest
from unittest.mock import patch

from modules.documents import quote_service


class DocumentQuoteSupabaseReadTests(unittest.TestCase):
    def test_order_lines_prefer_supabase_detail(self):
        supabase_detail = {
            "lines": [
                {
                    "order_line_id": "LINE-1",
                    "order_id": "ORD-1",
                    "pig_id": "PIG-1",
                    "tag_number": "101",
                    "unit_price": 1250,
                }
            ]
        }
        with patch.object(quote_service.order_supabase_read, "supabase_order_reads_available", return_value=True), \
             patch.object(quote_service.order_supabase_read, "get_order_detail", return_value=supabase_detail), \
             patch.object(quote_service, "get_all_records") as get_records:
            lines = quote_service._get_order_lines_from_sheet("ORD-1")

        self.assertEqual(lines, supabase_detail["lines"])
        get_records.assert_not_called()

    def test_order_lines_fall_back_to_sheet_when_supabase_unavailable(self):
        sheet_rows = [
            {
                "Order_Line_ID": "LINE-1",
                "Order_ID": "ORD-1",
                "Pig_ID": "PIG-1",
                "Tag_Number": "101",
                "Unit_Price": "1250",
            },
            {
                "Order_Line_ID": "LINE-2",
                "Order_ID": "ORD-2",
                "Pig_ID": "PIG-2",
            },
        ]
        with patch.object(quote_service.order_supabase_read, "supabase_order_reads_available", return_value=False), \
             patch.object(quote_service, "get_all_records", return_value=sheet_rows) as get_records:
            lines = quote_service._get_order_lines_from_sheet("ORD-1")

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["order_line_id"], "LINE-1")
        self.assertEqual(lines[0]["unit_price"], 1250.0)
        get_records.assert_called_once_with(quote_service.ORDER_LINES_SHEET)

    def test_quote_readiness_allows_approved_active_order(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "order_status": "Approved",
                "customer_name": "Michaels",
                "customer_phone": "0720000000",
                "payment_method": "Cash",
                "collection_location": "Riversdale",
                "requested_quantity": 1,
            },
            "lines": [{
                "pig_id": "PIG-104",
                "sale_category": "Young Piglets",
                "weight_band": "7_to_9_Kg",
                "sex": "Any",
                "unit_price": 700,
                "line_status": "Reserved",
            }],
        }
        master = {
            "Order_ID": "ORD-1",
            "Order_Status": "Approved",
            "Customer_Name": "Michaels",
            "Customer_Phone": "0720000000",
            "Payment_Method": "Cash",
            "Collection_Location": "Riversdale",
            "Requested_Quantity": 1,
        }

        with patch.object(quote_service, "get_order_detail", return_value=detail), \
             patch.object(quote_service, "_get_order_master_row", return_value=master):
            readiness = quote_service.get_quote_readiness("ORD-1")

        self.assertTrue(readiness["quote_ready"])
        self.assertNotIn("draft_status", readiness["missing_fields"])
        self.assertNotIn("active_order_status", readiness["missing_fields"])


if __name__ == "__main__":
    unittest.main()
