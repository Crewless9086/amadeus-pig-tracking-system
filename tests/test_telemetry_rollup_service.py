import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from modules.telemetry.rollup_service import get_daily_rollup_compare


class TelemetryRollupServiceTests(unittest.TestCase):
    def test_daily_rollup_compare_requires_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = get_daily_rollup_compare("2026-05-23")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["source"]["writes_to_supabase"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_daily_rollup_compare_returns_stored_and_current_counts(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (
                "PWRDAY-2026-05-23-sunsynk-main-inverter",
                "sunsynk-main-inverter",
                date(2026, 5, 23),
                datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 23, 22, 0, tzinfo=timezone.utc),
                119,
                288,
                Decimal("41.32"),
                Decimal("30"),
                Decimal("39"),
                Decimal("31.8"),
                Decimal("803.84"),
                Decimal("1206"),
                Decimal("255.96"),
                Decimal("2641"),
                Decimal("315"),
                Decimal("0"),
                Decimal("450"),
                Decimal("2.5383"),
                Decimal("7.9714"),
                Decimal("3.7892"),
                Decimal("0.0045"),
                Decimal("0"),
                "sample_integration_estimated",
                Decimal("9.1"),
                Decimal("23.1"),
                ["estimated"],
                "daily_rollup_plan_v1",
                datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc),
            ),
            (
                "WTHDAY-2026-05-23-weather-station-main",
                "weather-station-main",
                date(2026, 5, 23),
                datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 23, 22, 0, tzinfo=timezone.utc),
                119,
                288,
                Decimal("41.32"),
                Decimal("9"),
                Decimal("14"),
                Decimal("11.69"),
                Decimal("98.28"),
                Decimal("0"),
                Decimal("0"),
                Decimal("10"),
                Decimal("11"),
                Decimal("1016.93"),
                Decimal("1017.95"),
                Decimal("0"),
                {"irrigation_caution": False},
                "daily_rollup_plan_v1",
                datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc),
            ),
            (
                "IRRDAY-2026-05-23-irrigation-controller-main",
                "irrigation-controller-main",
                date(2026, 5, 23),
                "IRRPLAN-2026-05-23",
                datetime(2026, 5, 22, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 23, 22, 0, tzinfo=timezone.utc),
                2,
                0,
                0,
                0,
                Decimal("120"),
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                0,
                1,
                Decimal("0"),
                0,
                Decimal("0"),
                0,
                0,
                None,
                "daily_rollup_plan_v1",
                datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc),
            ),
            (119,),
            (120,),
            (1,),
            (2,),
        ]
        connection = MagicMock()
        psycopg = Mock()
        psycopg.connect.return_value = MagicMock()
        psycopg.connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_daily_rollup_compare("2026-05-23")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["stored_rollups"]["power"]["sample_count"], 119)
        self.assertEqual(result["stored_rollups"]["weather"]["sample_count"], 119)
        self.assertEqual(result["raw_counts"]["weather"], 120)
        self.assertTrue(result["comparison"]["power"]["sample_count_match"])
        self.assertFalse(result["comparison"]["weather"]["sample_count_match"])
        self.assertTrue(result["comparison"]["irrigation"]["event_count_match"])
        self.assertIn("estimated", " ".join(result["operator_summary"]["notes"]).lower())
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_daily_rollup_route_is_registered(self):
        route_source = Path("modules/telemetry/telemetry_routes.py").read_text(encoding="utf-8")

        self.assertIn("/telemetry/rollups/daily", route_source)
        self.assertIn("get_daily_rollup_compare", route_source)


if __name__ == "__main__":
    unittest.main()
