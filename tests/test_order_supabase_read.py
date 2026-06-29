import unittest
from datetime import datetime
from unittest.mock import patch

from modules.orders import order_read, order_supabase_read


class OrderSupabaseReadTests(unittest.TestCase):
    def test_list_orders_maps_rollups(self):
        orders = [{
            "order_id": "ORD-1",
            "order_date": datetime(2026, 6, 1, 10, 0),
            "customer_name": "Customer",
            "customer_phone_raw": "082 111 2222",
            "customer_channel": "WhatsApp",
            "customer_language": "English",
            "order_source": "Chatwoot",
            "requested_category": "Grower",
            "requested_weight_range": "60_to_64_Kg",
            "requested_sex": "Any",
            "requested_quantity": 2,
            "quoted_total": 3000,
            "final_total": 3000,
            "order_status": "Approved",
            "approval_status": "Approved",
            "payment_status": "Pending",
            "payment_method": "EFT",
            "collection_location": "Riversdale",
            "reserved_pig_count": 1,
            "conversation_id": "1774",
            "notes": "Ready",
            "created_by": "Tester",
            "created_at": datetime(2026, 6, 1, 10, 0),
            "updated_at": datetime(2026, 6, 1, 11, 0),
        }]
        lines = [
            {
                "order_line_id": "OL-1",
                "order_id": "ORD-1",
                "pig_id": "PIG-1",
                "tag_number": "101",
                "unit_price": 1500,
                "line_status": "Draft",
                "reserved_status": "Reserved",
            },
            {
                "order_line_id": "OL-2",
                "order_id": "ORD-1",
                "pig_id": "PIG-2",
                "tag_number": "102",
                "unit_price": 1500,
                "line_status": "Cancelled",
                "reserved_status": "Not_Reserved",
            },
        ]

        def fake_fetch_all(sql, params=(), connect_factory=None):
            if "from public.orders" in sql:
                return orders
            if "from public.order_lines" in sql:
                return lines
            return []

        with patch.object(order_supabase_read, "_fetch_all", side_effect=fake_fetch_all):
            result = order_supabase_read.list_orders()

        self.assertEqual(result[0]["order_id"], "ORD-1")
        self.assertEqual(result[0]["active_line_count"], 1)
        self.assertEqual(result[0]["cancelled_line_count"], 1)
        self.assertEqual(result[0]["reserved_line_count"], 1)
        self.assertEqual(result[0]["reserved_pig_ids"], "PIG-1")

    def test_get_order_detail_maps_lines_and_source(self):
        order = {"order_id": "ORD-1", "order_status": "Draft"}
        lines = [{"order_line_id": "OL-1", "order_id": "ORD-1", "unit_price": 1200}]

        with patch.object(order_supabase_read, "_fetch_one", return_value=order), \
             patch.object(order_supabase_read, "_fetch_all", return_value=lines):
            result = order_supabase_read.get_order_detail("ORD-1")

        self.assertEqual(result["source"], "supabase_canonical")
        self.assertEqual(result["order"]["order_id"], "ORD-1")
        self.assertTrue(result["order"]["line_count_includes_cancelled"])
        self.assertEqual(result["lines"][0]["order_line_id"], "OL-1")

    def test_order_read_prefers_supabase_list_when_available(self):
        expected = [{"order_id": "ORD-1"}]
        with patch.object(order_supabase_read, "supabase_order_reads_available", return_value=True), \
             patch.object(order_supabase_read, "list_orders", return_value=expected):
            self.assertEqual(order_read.list_orders(), expected)

    def test_order_read_falls_back_when_supabase_unavailable(self):
        with patch.object(order_supabase_read, "supabase_order_reads_available", return_value=False), \
             patch.object(order_read, "get_all_records", return_value=[]):
            self.assertEqual(order_read.list_orders(), [])

    def test_status_logs_map_to_sheet_compatible_keys(self):
        rows = [{
            "status_log_id": "OSL-1",
            "order_id": "ORD-1",
            "status_date": datetime(2026, 6, 1, 9, 0),
            "old_status": "Draft",
            "new_status": "Completed | Approved",
            "changed_by": "Tester",
            "change_source": "App",
            "notes": "Done",
            "created_at": datetime(2026, 6, 1, 9, 1),
        }]

        with patch.object(order_supabase_read, "_fetch_all", return_value=rows):
            result = order_supabase_read.list_order_status_logs()

        self.assertEqual(result[0]["Order_Status_Log_ID"], "OSL-1")
        self.assertEqual(result[0]["Status_Date"], "2026-06-01")
        self.assertEqual(result[0]["New_Status"], "Completed | Approved")


if __name__ == "__main__":
    unittest.main()
