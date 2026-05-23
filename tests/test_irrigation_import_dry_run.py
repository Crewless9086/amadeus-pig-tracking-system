import unittest
from unittest.mock import MagicMock, Mock, patch

from scripts.irrigation_import_dry_run import (
    APPLY_IMPORT_BATCH_ID,
    TABLE_INSERT_ORDER,
    apply_irrigation_import,
    build_irrigation_dry_run_payload,
    load_local_env,
)


class IrrigationImportDryRunTests(unittest.TestCase):
    def _records(self):
        return {
            "ZONES": [
                {
                    "zone_id": "C12345",
                    "name": "C - Kamp",
                    "priority": 2,
                    "summer_minutes": 60,
                    "winter_minutes": 30,
                    "active": "TRUE",
                },
                {
                    "zone_id": "B12345",
                    "name": "B - Kamp",
                    "priority": 1,
                    "summer_minutes": 60,
                    "winter_minutes": 30,
                    "active": "TRUE",
                },
            ],
            "DAILY_PLAN": [
                {
                    "plan_id": "2026-05-23_C12345",
                    "date": "2026-05-23",
                    "zone_id": "C12345",
                    "planned_minutes": 60,
                    "status": "PLANNED",
                    "water_score": 3,
                },
                {
                    "plan_id": "2026-05-23_B12345",
                    "date": "2026-05-23",
                    "zone_id": "B12345",
                    "planned_minutes": 60,
                    "status": "PLANNED",
                    "water_score": 5,
                },
            ],
            "STATE": [
                {
                    "state_id": "main",
                    "current_zone_id": "C12345",
                    "current_status": "IDLE",
                    "remaining_minutes": 0,
                    "last_update": "2026-05-23T00:06:13.772+02:00",
                    "next_zone_id": "C12345",
                }
            ],
            "LOG": [
                {
                    "timestamp": "2026-05-23T00:06:14.597+02:00",
                    "zone_id": "SYSTEM",
                    "event": "PLAN_CREATED",
                    "reason": "Daily plan created",
                    "actor": "AUTO",
                    "run_minutes_planned": 120,
                    "plan_id": "",
                }
            ],
        }

    def test_dry_run_maps_core_irrigation_tabs_without_writes(self):
        records = self._records()

        result = build_irrigation_dry_run_payload(records)

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "plan_only")
        self.assertFalse(result["writes_to_sheets"])
        self.assertFalse(result["writes_to_supabase"])
        self.assertEqual(result["import_strategy"]["state"], "latest_state_upsert")
        self.assertIn("upsert", result["import_strategy"]["apply_behavior"])
        self.assertEqual(result["payload_summary"]["irrigation_zones"]["rows"], 2)
        self.assertEqual(result["payload_summary"]["irrigation_daily_plans"]["rows"], 1)
        self.assertEqual(result["payload_summary"]["irrigation_plan_items"]["rows"], 2)
        self.assertEqual(result["payload_summary"]["irrigation_state_snapshots"]["rows"], 1)
        self.assertEqual(result["payload_summary"]["irrigation_events"]["rows"], 1)
        self.assertEqual(result["payload_samples"]["irrigation_daily_plans"][0]["total_planned_minutes"], 120)
        self.assertEqual(
            result["payload_samples"]["irrigation_state_snapshots"][0]["state_snapshot_id"],
            "IRRSTATE-main",
        )
        self.assertEqual(result["link_issues"], {})

    def test_apply_requires_database_url(self):
        report, exit_code = apply_irrigation_import(self._records(), "")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertFalse(report["writes_to_supabase"])
        self.assertEqual(report["status"], "not_configured")

    def test_load_local_env_reads_repo_env_file(self):
        load_dotenv = Mock(return_value=True)

        loaded = load_local_env(load_dotenv)

        self.assertTrue(loaded)
        self.assertTrue(str(load_dotenv.call_args.args[0]).endswith(".env"))

    def test_insert_order_respects_irrigation_foreign_keys(self):
        self.assertEqual(
            TABLE_INSERT_ORDER,
            [
                "irrigation_zones",
                "irrigation_daily_plans",
                "irrigation_plan_items",
                "irrigation_state_snapshots",
                "irrigation_events",
            ],
        )

    @patch("scripts.irrigation_import_dry_run._upsert_rows")
    def test_apply_uses_one_transaction_and_latest_state_strategy(self, upsert_rows):
        connection = MagicMock()
        cursor = Mock()
        connect = Mock()
        connect.return_value = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        upsert_rows.side_effect = [2, 1, 2, 1, 1]

        report, exit_code = apply_irrigation_import(
            self._records(),
            "postgresql://example",
            connect_factory=connect,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["import_batch_id"], APPLY_IMPORT_BATCH_ID)
        self.assertTrue(report["writes_to_supabase"])
        self.assertFalse(report["writes_to_sheets"])
        self.assertEqual(report["import_strategy"]["state"], "latest_state_upsert")
        self.assertEqual(report["inserted_or_updated"]["irrigation_state_snapshots"], 1)
        connection.commit.assert_called_once()

    def test_dry_run_reports_missing_zone_links(self):
        records = {
            "ZONES": [{"zone_id": "C12345", "name": "C - Kamp"}],
            "DAILY_PLAN": [
                {
                    "plan_id": "2026-05-23_UNKNOWN",
                    "date": "2026-05-23",
                    "zone_id": "UNKNOWN",
                    "planned_minutes": 60,
                    "status": "PLANNED",
                }
            ],
            "STATE": [{"state_id": "main", "current_status": "IDLE", "next_zone_id": "UNKNOWN"}],
            "LOG": [
                {
                    "timestamp": "2026-05-23T00:06:14.597+02:00",
                    "zone_id": "UNKNOWN",
                    "event": "ZONE_STARTED",
                }
            ],
        }

        result = build_irrigation_dry_run_payload(records)

        self.assertEqual(result["link_issues"]["plan_items"]["missing_zone_link"], 1)
        self.assertEqual(result["link_issues"]["state_snapshots"]["next_zone_missing"], 1)
        self.assertEqual(result["link_issues"]["events"]["missing_zone_link"], 1)


if __name__ == "__main__":
    unittest.main()
