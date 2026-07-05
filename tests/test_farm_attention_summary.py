import unittest
from datetime import datetime
from unittest.mock import patch

from app import app
from modules.pig_weights import pig_weights_service
from modules.reports import report_service


class FixedDateTime:
    @classmethod
    def now(cls):
        return datetime(2026, 5, 30, 8, 15, 0)


class FarmAttentionSummaryTests(unittest.TestCase):
    def test_daily_order_summary_still_builds_attention_sections(self):
        orders = [
            {
                "order_id": "ORD-DRAFT",
                "order_status": "Draft",
                "payment_method": "",
                "collection_location": "",
                "active_line_count": 0,
                "reserved_pig_count": 0,
                "created_at": "30 May 2026",
            },
        ]

        with patch.object(report_service, "list_orders", return_value=orders), \
             patch.object(report_service, "get_all_records", return_value=[]):
            result = report_service.get_daily_order_summary(report_date="2026-05-30")

        self.assertTrue(result["success"])
        self.assertEqual(result["counts"]["new_drafts"], 1)
        self.assertEqual(result["counts"]["orders_needing_attention"], 1)
        self.assertEqual(
            result["sections"]["orders_needing_attention"][0]["reasons"],
            ["missing_payment_method", "missing_collection_location", "no_active_lines"],
        )

    def test_summary_combines_order_and_litter_attention_without_writes_or_delivery(self):
        order_summary = {
            "success": True,
            "rules": {
                "orders_needing_attention": "Order attention rule.",
            },
            "sections": {
                "orders_needing_attention": [
                    {
                        "order_id": "ORD-ATTN",
                        "reasons": ["missing_payment_method"],
                    },
                ],
            },
        }
        litter_summary = {
            "count": 3,
            "items": [
                {
                    "litter_id": "LIT-2026-8A0F",
                    "reason": "Piglets need tag numbers",
                },
                {
                    "litter_id": "LIT-OLDER",
                    "reason": "Weaned - review purpose",
                },
            ],
        }

        with patch.object(report_service, "datetime", FixedDateTime), \
             patch.object(report_service, "get_daily_order_summary", return_value=order_summary), \
             patch.object(report_service, "get_litter_attention_summary", return_value=litter_summary) as litter_mock:
            result = report_service.get_farm_attention_summary(report_date="2026-05-30", limit="2")

        litter_mock.assert_called_once_with(limit=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mode"], "read_only")
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["sends_telegram"])
        self.assertEqual(result["counts"]["attention_total"], 4)
        self.assertEqual(result["counts"]["orders_needing_attention"], 1)
        self.assertEqual(result["counts"]["litter_attention"], 3)
        self.assertEqual(result["counts"]["litter_attention_returned"], 2)
        self.assertIn("Orders needing attention: 1", result["digest_lines"])
        self.assertIn("- LIT-2026-8A0F: Piglets need tag numbers", result["digest_lines"])
        self.assertIn("- 1 more litter attention item(s) not shown in this response.", result["digest_lines"])

    def test_summary_returns_clear_empty_digest(self):
        order_summary = {
            "success": True,
            "rules": {},
            "sections": {
                "orders_needing_attention": [],
            },
        }
        litter_summary = {
            "count": 0,
            "items": [],
        }

        with patch.object(report_service, "get_daily_order_summary", return_value=order_summary), \
             patch.object(report_service, "get_litter_attention_summary", return_value=litter_summary):
            result = report_service.get_farm_attention_summary(report_date="2026-05-30")

        self.assertEqual(result["counts"]["attention_total"], 0)
        self.assertEqual(result["digest_lines"], ["No current farm attention items."])

    def test_summary_fallback_does_not_count_sold_litter_piglets_as_attention(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        order_summary = {
            "success": True,
            "rules": {},
            "sections": {
                "orders_needing_attention": [],
            },
        }
        overview_rows = [{
            "Litter_ID": "LIT-SOLD",
            "Total_Born": "7",
            "Born_Alive": "6",
            "Stillborn_Count": "1",
            "Mummified_Count": "0",
            "Pig_Master_Row_Count": "3",
            "Active_Pig_Count": "3",
            "Exited_Pig_Count": "3",
            "Litter_Status": "Active",
            "Needs_Attention": "Yes",
            "Attention_Reason": "Linked pig records do not match born alive count",
        }]
        pig_master_rows = [
            {"Pig_ID": f"PIG-A{i}", "Litter_ID": "LIT-SOLD", "Status": "Active", "On_Farm": "Yes"}
            for i in range(3)
        ] + [
            {"Pig_ID": "PIG-SOLD", "Litter_ID": "LIT-SOLD", "Status": "Sold", "On_Farm": "No", "Exit_Reason": "Livestock Sale"},
            {"Pig_ID": "PIG-DISPOSED", "Litter_ID": "LIT-SOLD", "Status": "Disposed", "On_Farm": "No", "Exit_Reason": "Disposed"},
            {"Pig_ID": "PIG-COMPLETED", "Litter_ID": "LIT-SOLD", "Status": "Completed Sale", "On_Farm": "No", "Exit_Reason": "Completed Sale"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_master_rows
            return []

        with patch.object(report_service, "get_daily_order_summary", return_value=order_summary), \
             patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = report_service.get_farm_attention_summary(report_date="2026-05-30")

        self.assertEqual(result["counts"]["attention_total"], 0)
        self.assertEqual(result["counts"]["litter_attention"], 0)
        self.assertEqual(result["sections"]["litter_attention"], [])
        self.assertEqual(result["digest_lines"], ["No current farm attention items."])

    def test_summary_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            report_service.get_farm_attention_summary(report_date="2026-05-30", limit="0")

    def test_route_exposes_farm_attention_summary(self):
        payload = {
            "success": True,
            "status": "ok",
            "mode": "read_only",
        }

        with patch("modules.reports.report_routes.get_farm_attention_summary", return_value=payload) as summary_mock:
            client = app.test_client()
            response = client.get("/api/reports/farm-attention-summary?date=2026-05-30&limit=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), payload)
        summary_mock.assert_called_once_with(report_date="2026-05-30", limit="7")


if __name__ == "__main__":
    unittest.main()
