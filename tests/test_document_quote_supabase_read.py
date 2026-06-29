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


if __name__ == "__main__":
    unittest.main()
