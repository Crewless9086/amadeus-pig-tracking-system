import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, Mock

from scripts.telemetry_daily_rollup_plan import (
    apply_daily_rollups,
    build_daily_rollup_plan,
    _build_irrigation_daily_rollup,
    _build_power_daily_rollup,
    _build_weather_daily_rollup,
    _previous_day_za,
)


class TelemetryDailyRollupPlanTests(unittest.TestCase):
    def test_plan_requires_database_url(self):
        report, exit_code = build_daily_rollup_plan("2026-05-23", database_url="")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "not_configured")
        self.assertFalse(report["writes_to_supabase"])

    def test_power_rollup_estimates_samples_without_claiming_confirmed_kwh(self):
        start = datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 23, 22, 0, tzinfo=timezone.utc)
        rows = [
            {
                "battery_soc_pct": 50.0,
                "solar_power_w": 600.0,
                "load_power_w": 1200.0,
                "grid_power_w": 0.0,
                "generator_power_w": 0.0,
                "grid_active": False,
                "generator_active": False,
            },
            {
                "battery_soc_pct": 48.0,
                "solar_power_w": 0.0,
                "load_power_w": 900.0,
                "grid_power_w": 300.0,
                "generator_power_w": 0.0,
                "grid_active": True,
                "generator_active": False,
            },
        ]

        rollup = _build_power_daily_rollup(start.date(), start, end, rows)

        self.assertEqual(rollup["sample_count"], 2)
        self.assertEqual(rollup["coverage_pct"], 0.69)
        self.assertEqual(rollup["battery_soc_min_pct"], 48.0)
        self.assertEqual(rollup["grid_active_minutes"], 5)
        self.assertEqual(rollup["estimated_load_kwh"], 0.175)
        self.assertEqual(rollup["tariff_zar_per_kwh"], 9.10)
        self.assertEqual(rollup["energy_calculation_method"], "sample_integration_estimated")
        self.assertIn("estimated", " ".join(rollup["limitations"]))

    def test_weather_rollup_uses_max_rain_today_and_flags_caution(self):
        start = datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 23, 22, 0, tzinfo=timezone.utc)
        rows = [
            {
                "temperature_c": 12.0,
                "humidity_pct": 90.0,
                "rain_rate_mm_h": 0.0,
                "rain_today_mm": 0.2,
                "wind_speed_kmh": 8.0,
                "wind_gust_kmh": 10.0,
                "pressure_hpa": 1013.0,
            },
            {
                "temperature_c": 18.0,
                "humidity_pct": 80.0,
                "rain_rate_mm_h": 0.0,
                "rain_today_mm": 0.8,
                "wind_speed_kmh": 35.0,
                "wind_gust_kmh": 41.0,
                "pressure_hpa": 1015.0,
            },
        ]

        rollup = _build_weather_daily_rollup(start.date(), start, end, rows)

        self.assertEqual(rollup["sample_count"], 2)
        self.assertEqual(rollup["temperature_min_c"], 12.0)
        self.assertEqual(rollup["temperature_max_c"], 18.0)
        self.assertEqual(rollup["rain_total_mm"], 0.8)
        self.assertTrue(rollup["flags"]["irrigation_caution"])
        self.assertTrue(rollup["flags"]["wind_caution"])

    def test_irrigation_rollup_counts_plan_events_fertilizer_and_tank(self):
        start = datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 23, 22, 0, tzinfo=timezone.utc)
        data = {
            "daily_plan": {"daily_plan_id": "IRRPLAN-2026-05-23"},
            "plan_items": [
                {"item_status": "Completed", "planned_minutes": 60, "actual_minutes": 55},
                {"item_status": "Skipped", "planned_minutes": 45, "actual_minutes": 0},
            ],
            "events": [
                {
                    "event_type": "WEATHER_HOLD",
                    "planned_minutes": 15,
                    "actual_minutes": 0,
                    "reason": "Wind caution",
                }
            ],
            "auxiliary_tasks": [
                {"device_type": "fertilizer_injection_valve", "planned_minutes": 1},
                {"device_type": "fertilizer_mixer", "planned_minutes": 30},
            ],
            "sensor_states": [
                {"sensor_type": "tank_full", "status": "true"},
                {"sensor_type": "tank_empty", "status": "false"},
            ],
        }

        rollup = _build_irrigation_daily_rollup(start.date(), start, end, data)

        self.assertEqual(rollup["daily_plan_id"], "IRRPLAN-2026-05-23")
        self.assertEqual(rollup["planned_zone_count"], 2)
        self.assertEqual(rollup["completed_zone_count"], 1)
        self.assertEqual(rollup["skipped_zone_count"], 1)
        self.assertEqual(rollup["planned_minutes"], 105)
        self.assertEqual(rollup["weather_hold_minutes"], 15)
        self.assertEqual(rollup["fertilizer_injection_cycles"], 1)
        self.assertEqual(rollup["fertilizer_mixer_minutes"], 30)
        self.assertEqual(rollup["tank_full_count"], 1)

    def test_plan_reads_all_sources_and_writes_nothing(self):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (
                    datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
                    Decimal("50"),
                    Decimal("600"),
                    Decimal("1200"),
                    Decimal("0"),
                    Decimal("0"),
                    False,
                    False,
                )
            ],
            [
                (
                    datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
                    Decimal("14"),
                    Decimal("90"),
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("8"),
                    Decimal("10"),
                    Decimal("1013"),
                )
            ],
            [("Planned", Decimal("60"), None, None, None)],
            [
                (
                    datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
                    "",
                    "PLAN_CREATED",
                    Decimal("60"),
                    None,
                    "Daily plan created",
                    "AUTO",
                )
            ],
            [],
            [],
        ]
        cursor.fetchone.return_value = ("IRRPLAN-2026-05-23", "irrigation-controller-main")
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        connect = Mock(return_value=MagicMock())
        connect.return_value.__enter__.return_value = connection

        report, exit_code = build_daily_rollup_plan(
            "2026-05-23",
            "postgresql://example",
            connect_factory=connect,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "plan_only")
        self.assertFalse(report["writes_to_supabase"])
        self.assertEqual(report["payload_summary"]["power_daily_rollups"]["rows"], 1)
        self.assertEqual(report["payloads"]["irrigation_daily_rollups"][0]["planned_zone_count"], 1)
        self.assertEqual(cursor.execute.call_count, 7)

    def test_apply_requires_database_url(self):
        report, exit_code = apply_daily_rollups(
            "2026-05-23",
            database_url="",
            allow_partial=True,
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertEqual(report["mode"], "apply")
        self.assertFalse(report["writes_to_supabase"])

    def test_apply_refuses_open_day_without_explicit_partial_override(self):
        today = date.today().isoformat()

        report, exit_code = apply_daily_rollups(today, database_url="postgresql://example")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "day_not_closed")
        self.assertTrue(report["allow_partial_required"])
        self.assertFalse(report["writes_to_supabase"])

    def test_previous_day_helper_returns_closed_local_day(self):
        previous_day = _previous_day_za()

        self.assertLess(previous_day, date.today())

    def test_apply_upserts_three_daily_rows_in_one_transaction(self):
        connection = MagicMock()
        cursor = Mock()
        connect = Mock(return_value=MagicMock())
        connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [
            [
                (
                    datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
                    Decimal("50"),
                    Decimal("600"),
                    Decimal("1200"),
                    Decimal("0"),
                    Decimal("0"),
                    False,
                    False,
                )
            ],
            [
                (
                    datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc),
                    Decimal("14"),
                    Decimal("90"),
                    Decimal("0"),
                    Decimal("0"),
                    Decimal("8"),
                    Decimal("10"),
                    Decimal("1013"),
                )
            ],
            [("Planned", Decimal("60"), None, None, None)],
            [],
            [],
            [],
        ]
        cursor.fetchone.return_value = ("IRRPLAN-2026-05-23", "irrigation-controller-main")

        report, exit_code = apply_daily_rollups(
            "2026-05-23",
            "postgresql://example",
            connect_factory=connect,
            allow_partial=True,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "apply")
        self.assertTrue(report["partial_apply_allowed"])
        self.assertTrue(report["writes_to_supabase"])
        self.assertEqual(report["inserted_or_updated"]["power_daily_rollups"], 1)
        self.assertEqual(report["inserted_or_updated"]["weather_daily_rollups"], 1)
        self.assertEqual(report["inserted_or_updated"]["irrigation_daily_rollups"], 1)
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
