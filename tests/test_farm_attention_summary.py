import unittest
from datetime import datetime
from unittest.mock import patch

from app import app
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
