import unittest
from unittest.mock import MagicMock, Mock, patch

from modules.telemetry.irrigation_service import get_irrigation_status


class IrrigationTelemetryTests(unittest.TestCase):
    def test_irrigation_status_is_read_only_and_summarizes_plan(self):
        records = {
            "STATE": [
                {
                    "state_id": "main",
                    "current_zone_id": "",
                    "current_status": "IDLE",
                    "remaining_minutes": "",
                    "pause_reason": "",
                    "last_update": "2026-05-23T05:00:00+02:00",
                    "last_zone_completed": "ZONE-1",
                    "next_zone_id": "ZONE-2",
                }
            ],
            "DAILY_PLAN": [
                {
                    "plan_id": "2026-05-23_ZONE-1",
                    "date": "2026-05-23",
                    "zone_id": "ZONE-1",
                    "planned_start": "",
                    "planned_minutes": 20,
                    "status": "DONE",
                    "reason": "",
                    "actual_start": "2026-05-23T05:00:00+02:00",
                    "actual_end": "2026-05-23T05:20:00+02:00",
                    "water_score": 1,
                },
                {
                    "plan_id": "2026-05-23_ZONE-2",
                    "date": "2026-05-23",
                    "zone_id": "ZONE-2",
                    "planned_start": "",
                    "planned_minutes": 30,
                    "status": "PLANNED",
                    "reason": "",
                    "actual_start": "",
                    "actual_end": "",
                    "water_score": 5,
                },
            ],
            "ZONES": [
                {"zone_id": "ZONE-1", "name": "North Drip", "priority": 2},
                {"zone_id": "ZONE-2", "name": "South Sprinkler", "priority": 1},
            ],
            "RULES": [
                {"rule_key": "wind_pause_kmh", "rule_value": 35},
                {"rule_key": "live_rain_skip_mm", "rule_value": 2},
            ],
            "LOG": [
                {
                    "timestamp": "2026-05-23T05:20:00+02:00",
                    "zone_id": "ZONE-1",
                    "event": "ZONE_COMPLETED",
                    "reason": "Planned runtime completed",
                    "run_minutes_planned": 20,
                    "run_minutes_actual": 20,
                    "actor": "system",
                    "plan_id": "2026-05-23_ZONE-1",
                }
            ],
        }

        def fake_get_records(_spreadsheet_name, tab_name):
            return records[tab_name]

        with patch("modules.telemetry.irrigation_service.get_all_records_from_spreadsheet", side_effect=fake_get_records):
            result, status_code = get_irrigation_status(today="2026-05-23", spreadsheet_name="Irrigation")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "read_only")
        self.assertTrue(result["safety"]["read_only"])
        self.assertFalse(result["safety"]["can_control"])
        self.assertFalse(result["safety"]["hardware_commands_enabled"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertEqual(result["current"]["status"], "IDLE")
        self.assertEqual(result["today"]["planned_count"], 1)
        self.assertEqual(result["today"]["done_count"], 1)
        self.assertEqual(result["today"]["total_planned_minutes"], 50)
        self.assertEqual(result["today"]["completed_minutes"], 20)
        self.assertEqual(result["today"]["next_zone_id"], "ZONE-2")
        self.assertEqual(result["today"]["next_zone_name"], "South Sprinkler")
        self.assertEqual(result["today"]["next_zone_source"], "state")
        self.assertEqual(result["today"]["state_next_zone_id"], "ZONE-2")
        self.assertEqual(result["today"]["computed_next_zone_id"], "ZONE-2")
        self.assertFalse(result["today"]["next_zone_mismatch"])
        self.assertEqual(len(result["recent_events"]), 1)

    def test_irrigation_status_flags_state_and_computed_next_zone_mismatch(self):
        records = {
            "STATE": [
                {
                    "state_id": "main",
                    "current_status": "IDLE",
                    "next_zone_id": "ZONE-1",
                }
            ],
            "DAILY_PLAN": [
                {
                    "plan_id": "2026-05-23_ZONE-1",
                    "date": "2026-05-23",
                    "zone_id": "ZONE-1",
                    "planned_minutes": 20,
                    "status": "PLANNED",
                    "water_score": 1,
                },
                {
                    "plan_id": "2026-05-23_ZONE-2",
                    "date": "2026-05-23",
                    "zone_id": "ZONE-2",
                    "planned_minutes": 30,
                    "status": "PLANNED",
                    "water_score": 5,
                },
            ],
            "ZONES": [
                {"zone_id": "ZONE-1", "name": "North Drip", "priority": 2},
                {"zone_id": "ZONE-2", "name": "South Sprinkler", "priority": 1},
            ],
            "RULES": [],
            "LOG": [],
        }

        def fake_get_records(_spreadsheet_name, tab_name):
            return records[tab_name]

        with patch("modules.telemetry.irrigation_service.get_all_records_from_spreadsheet", side_effect=fake_get_records):
            result, status_code = get_irrigation_status(today="2026-05-23", spreadsheet_name="Irrigation")

        self.assertEqual(status_code, 200)
        self.assertEqual(result["today"]["next_zone_id"], "ZONE-1")
        self.assertEqual(result["today"]["next_zone_source"], "state")
        self.assertEqual(result["today"]["state_next_zone_id"], "ZONE-1")
        self.assertEqual(result["today"]["computed_next_zone_id"], "ZONE-2")
        self.assertTrue(result["today"]["next_zone_mismatch"])
        self.assertIn(
            "STATE next zone differs from the computed highest-priority planned zone.",
            result["operator_summary"]["notes"],
        )

    def test_irrigation_status_returns_safe_unavailable_on_sheet_failure(self):
        with patch(
            "modules.telemetry.irrigation_service.get_all_records_from_spreadsheet",
            side_effect=RuntimeError("sheet unavailable"),
        ):
            result, status_code = get_irrigation_status(today="2026-05-23", spreadsheet_name="Irrigation")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["mode"], "read_only")
        self.assertTrue(result["safety"]["read_only"])
        self.assertFalse(result["safety"]["can_control"])
        self.assertFalse(result["safety"]["hardware_commands_enabled"])
        self.assertFalse(result["source"]["writes_to_sheets"])

    @patch.dict("os.environ", {"IRRIGATION_STATUS_SOURCE": "supabase", "DATABASE_URL": "postgresql://example"}, clear=True)
    def test_irrigation_status_can_read_today_plan_from_supabase(self):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [("ZONE-1", "North Drip", 2), ("ZONE-2", "South Sprinkler", 1)],
            [
                (
                    "2026-05-23T05:20:00+02:00",
                    "ZONE-1",
                    "ZONE_COMPLETED",
                    "Planned runtime completed",
                    20,
                    20,
                    "system",
                    "2026-05-23_ZONE-1",
                )
            ],
        ]
        cursor.fetchone.side_effect = [
            ("IDLE", "", "ZONE-2", "ZONE-1", None, "", "2026-05-23T05:00:00+02:00"),
            ("IRRPLAN-2026-05-23", "2026-05-23", "Planned", 50),
        ]

        def execute_side_effect(query, params=None):
            if "from public.irrigation_plan_items" in query:
                cursor.fetchall.side_effect = [
                    [
                        (
                            "2026-05-23_ZONE-1",
                            "IRRPLAN-2026-05-23",
                            "ZONE-1",
                            None,
                            20,
                            "2026-05-23T05:00:00+02:00",
                            "2026-05-23T05:20:00+02:00",
                            "Done",
                            1,
                            "",
                        ),
                        (
                            "2026-05-23_ZONE-2",
                            "IRRPLAN-2026-05-23",
                            "ZONE-2",
                            None,
                            30,
                            None,
                            None,
                            "Planned",
                            5,
                            "",
                        ),
                    ],
                    [
                        (
                            "2026-05-23T05:20:00+02:00",
                            "ZONE-1",
                            "ZONE_COMPLETED",
                            "Planned runtime completed",
                            20,
                            20,
                            "system",
                            "2026-05-23_ZONE-1",
                        )
                    ],
                ]

        cursor.execute.side_effect = execute_side_effect
        connection = MagicMock()
        psycopg = Mock()
        psycopg.connect.return_value = MagicMock()
        psycopg.connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_irrigation_status(today="2026-05-23")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["source"]["source"], "supabase")
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(result["today"]["daily_plan_id"], "IRRPLAN-2026-05-23")
        self.assertEqual(result["today"]["total_plan_rows"], 2)
        self.assertEqual(result["today"]["planned_count"], 1)
        self.assertEqual(result["today"]["done_count"], 1)
        self.assertEqual(result["today"]["next_zone_id"], "ZONE-2")
        self.assertEqual(result["today"]["next_zone_source"], "state")
        self.assertTrue(result["safety"]["read_only"])
        self.assertFalse(result["safety"]["can_control"])

    @patch.dict("os.environ", {"IRRIGATION_STATUS_SOURCE": "supabase", "DATABASE_URL": "postgresql://example"}, clear=True)
    def test_supabase_recent_events_are_deduplicated_for_display(self):
        cursor = Mock()
        duplicate_event = (
            "2026-05-23T00:06:14.597+02:00",
            "",
            "PLAN_CREATED",
            "Daily plan created for 2026-05-23",
            120,
            None,
            "AUTO",
            "",
        )
        cursor.fetchall.side_effect = [
            [("ZONE-1", "North Drip", 1)],
            [(duplicate_event), (duplicate_event)],
        ]
        cursor.fetchone.side_effect = [
            ("IDLE", "", "ZONE-1", "", None, "", "2026-05-23T00:06:13.772+02:00"),
            ("IRRPLAN-2026-05-23", "2026-05-23", "Planned", 60),
        ]

        def execute_side_effect(query, params=None):
            if "from public.irrigation_plan_items" in query:
                cursor.fetchall.side_effect = [
                    [
                        (
                            "2026-05-23_ZONE-1",
                            "IRRPLAN-2026-05-23",
                            "ZONE-1",
                            None,
                            60,
                            None,
                            None,
                            "Planned",
                            5,
                            "",
                        )
                    ],
                    [duplicate_event, duplicate_event],
                ]

        cursor.execute.side_effect = execute_side_effect
        connection = MagicMock()
        psycopg = Mock()
        psycopg.connect.return_value = MagicMock()
        psycopg.connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_irrigation_status(today="2026-05-23")

        self.assertEqual(status_code, 200)
        self.assertEqual(len(result["recent_events"]), 1)
        self.assertEqual(result["recent_events"][0]["event"], "PLAN_CREATED")

    def test_irrigation_route_is_registered(self):
        import modules.telemetry.telemetry_routes as routes

        route_source = routes.__file__
        with open(route_source, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("/telemetry/irrigation/status", source)


if __name__ == "__main__":
    unittest.main()
