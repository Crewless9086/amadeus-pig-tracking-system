import unittest
from unittest.mock import MagicMock, Mock, patch

from scripts.irrigation_daily_sync import (
    apply_daily_sync,
    build_daily_sync_plan,
    filter_daily_sync_records,
)


class IrrigationDailySyncTests(unittest.TestCase):
    def _records(self):
        return {
            "ZONES": [
                {"zone_id": "B12345", "name": "B - Kamp"},
                {"zone_id": "C12345", "name": "C - Kamp"},
            ],
            "DAILY_PLAN": [
                {
                    "plan_id": "2026-05-22_B12345",
                    "date": "2026-05-22",
                    "zone_id": "B12345",
                    "planned_minutes": 60,
                    "status": "DONE",
                },
                {
                    "plan_id": "2026-05-23_B12345",
                    "date": "2026-05-23",
                    "zone_id": "B12345",
                    "planned_minutes": 60,
                    "status": "PLANNED",
                },
                {
                    "plan_id": "2026-05-23_C12345",
                    "date": "2026-05-23",
                    "zone_id": "C12345",
                    "planned_minutes": 60,
                    "status": "PLANNED",
                },
            ],
            "STATE": [
                {
                    "state_id": "MAIN",
                    "current_status": "IDLE",
                    "current_zone_id": "C12345",
                    "next_zone_id": "C12345",
                    "last_update": "2026-05-23T00:06:13.772+02:00",
                }
            ],
            "LOG": [
                {
                    "timestamp": "2026-05-22T00:06:08.105+02:00",
                    "event": "PLAN_CREATED",
                    "reason": "Daily plan created for 2026-05-22",
                    "zone_id": "SYSTEM",
                },
                {
                    "timestamp": "2026-05-23T00:06:14.597+02:00",
                    "event": "PLAN_CREATED",
                    "reason": "Daily plan created for 2026-05-23",
                    "zone_id": "SYSTEM",
                },
            ],
        }

    def test_filter_keeps_only_requested_day_plan_and_events(self):
        filtered = filter_daily_sync_records(self._records(), "2026-05-23")

        self.assertEqual(len(filtered["ZONES"]), 2)
        self.assertEqual(len(filtered["DAILY_PLAN"]), 2)
        self.assertEqual({row["date"] for row in filtered["DAILY_PLAN"]}, {"2026-05-23"})
        self.assertEqual(len(filtered["STATE"]), 1)
        self.assertEqual(len(filtered["LOG"]), 1)
        self.assertIn("2026-05-23", filtered["LOG"][0]["reason"])

    def test_plan_only_uses_daily_scope_and_writes_nothing(self):
        report = build_daily_sync_plan(self._records(), "2026-05-23")

        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "plan_only")
        self.assertFalse(report["writes_to_sheets"])
        self.assertFalse(report["writes_to_supabase"])
        self.assertEqual(report["payload_summary"]["irrigation_daily_plans"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["irrigation_plan_items"]["rows"], 2)
        self.assertEqual(report["payload_summary"]["irrigation_events"]["rows"], 1)
        self.assertEqual(report["payload_summary"]["irrigation_state_snapshots"]["rows"], 1)
        self.assertEqual(report["sync_date"], "2026-05-23")

    def test_apply_requires_database_url(self):
        report, exit_code = apply_daily_sync(self._records(), "2026-05-23", "")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "not_configured")
        self.assertFalse(report["writes_to_supabase"])

    @patch("scripts.irrigation_daily_sync._upsert_rows")
    def test_apply_uses_one_transaction(self, upsert_rows):
        connection = MagicMock()
        cursor = Mock()
        connect = Mock()
        connect.return_value = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        upsert_rows.side_effect = [2, 1, 2, 1, 1]

        report, exit_code = apply_daily_sync(
            self._records(),
            "2026-05-23",
            "postgresql://example",
            connect_factory=connect,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["import_batch_id"], "SYNC-IRRIGATION-2026-05-23")
        self.assertEqual(report["inserted_or_updated"]["irrigation_daily_plans"], 1)
        self.assertEqual(report["inserted_or_updated"]["irrigation_plan_items"], 2)
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
