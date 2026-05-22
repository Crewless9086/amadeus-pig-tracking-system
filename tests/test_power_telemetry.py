import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from modules.telemetry.power_service import (
    get_current_power_state,
    get_recent_power_profile,
    ingest_power_reading,
)


class PowerTelemetryTests(unittest.TestCase):
    def test_ingest_requires_configured_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = ingest_power_reading({}, provided_api_key="")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "ingest_key_not_configured")
        self.assertFalse(result["source"]["writes_to_supabase"])

    @patch.dict(os.environ, {"TELEMETRY_INGEST_API_KEY": "expected"}, clear=True)
    def test_ingest_rejects_invalid_api_key(self):
        result, status_code = ingest_power_reading({}, provided_api_key="wrong")

        self.assertEqual(status_code, 401)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unauthorized")

    @patch.dict(os.environ, {"TELEMETRY_INGEST_API_KEY": "expected"}, clear=True)
    def test_ingest_reports_missing_database_url_without_importing_driver(self):
        result, status_code = ingest_power_reading({}, provided_api_key="expected")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(result))

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgresql://user:secret@example/db",
            "TELEMETRY_INGEST_API_KEY": "expected",
        },
        clear=True,
    )
    def test_ingest_writes_raw_and_latest_power_state(self):
        cursor = Mock()
        _connection, psycopg = _mock_psycopg_connection(cursor)

        payload = {
            "timestamp_za": "2026-05-21T20:30:00+02:00",
            "soc": 82,
            "batt_power": -640,
            "pv_total": 3120,
            "pv1": 1580,
            "pv2": 1540,
            "load_power": 1240,
            "grid_power": 0,
            "gen_power": 0,
            "inv_pac": 1240,
            "grid_active": False,
            "gen_active": False,
            "battery_charging": True,
            "battery_discharging": False,
        }

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = ingest_power_reading(payload, provided_api_key="expected")

        self.assertEqual(status_code, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["source_id"], "sunsynk-main-inverter")
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertEqual(cursor.execute.call_count, 2)
        first_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(first_params["battery_soc_pct"], 82.0)
        self.assertEqual(first_params["solar_power_w"], 3120.0)
        self.assertEqual(first_params["battery_state"], "charging")
        self.assertIn("solar_active", first_params["flags"])
        self.assertIn("Solar is carrying", first_params["summary_headline"])

    def test_current_power_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = get_current_power_state()

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(result))

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_current_power_returns_prepared_payload(self):
        cursor = Mock()
        cursor.fetchone.return_value = (
            "sunsynk-main-inverter",
            "Amadeus Sunsynk Inverter",
            "sunsynk",
            15,
            datetime.now(timezone.utc),
            Decimal("82"),
            Decimal("-640"),
            Decimal("3120"),
            Decimal("1580"),
            Decimal("1540"),
            Decimal("1240"),
            Decimal("0"),
            Decimal("0"),
            Decimal("1240"),
            "charging",
            "not_using_grid",
            "off",
            {"solar_active": True, "grid_active": False},
            "ok",
            "Solar is carrying the farm load.",
            ["Battery is at 82%."],
        )
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_current_power_state()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["source"]["source_id"], "sunsynk-main-inverter")
        self.assertEqual(result["current"]["battery_soc_pct"], 82.0)
        self.assertFalse(result["source"]["writes_to_supabase"])
        self.assertEqual(result["summary"]["status"], "ok")

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_current_power_no_reading_returns_unavailable(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_current_power_state()

        self.assertEqual(status_code, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unavailable")

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_recent_power_profile_returns_sample_based_summary(self):
        cursor = Mock()
        cursor.fetchall.return_value = [
            (
                datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc),
                Decimal("46"),
                Decimal("800"),
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                Decimal("1000"),
                Decimal("0"),
                Decimal("0"),
                Decimal("1000"),
                False,
                False,
                False,
                True,
            ),
            (
                datetime(2026, 5, 22, 0, 5, tzinfo=timezone.utc),
                Decimal("45"),
                Decimal("850"),
                Decimal("100"),
                Decimal("40"),
                Decimal("60"),
                Decimal("1100"),
                Decimal("120"),
                Decimal("0"),
                Decimal("1100"),
                True,
                False,
                False,
                True,
            ),
        ]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_recent_power_profile(hours=24)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertIn("raw_payload is not null", cursor.execute.call_args.args[0])
        self.assertEqual(result["window"]["requested_hours"], 24)
        self.assertEqual(result["window"]["row_count"], 2)
        self.assertEqual(result["battery"]["min_soc_pct"], 45.0)
        self.assertEqual(result["battery"]["latest_soc_pct"], 45.0)
        self.assertEqual(result["activity"]["grid_active_samples"], 1)
        self.assertEqual(result["activity"]["grid_active_approx_minutes"], 5)
        self.assertIn("does not report kWh", " ".join(result["limitations"]))

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_recent_power_profile_no_rows_returns_unavailable(self):
        cursor = Mock()
        cursor.fetchall.return_value = []
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_recent_power_profile(hours=24)

        self.assertEqual(status_code, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["window"]["row_count"], 0)

    def test_telemetry_routes_are_registered(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        route_source = Path("modules/telemetry/telemetry_routes.py").read_text(encoding="utf-8")

        self.assertIn("telemetry_bp", app_source)
        self.assertIn("app.register_blueprint(telemetry_bp, url_prefix=\"/api\")", app_source)
        self.assertIn("/telemetry/power/recent", route_source)


def _mock_psycopg_connection(cursor):
    cursor_context = Mock()
    cursor_context.__enter__ = Mock(return_value=cursor)
    cursor_context.__exit__ = Mock(return_value=False)

    connection = Mock()
    connection.cursor.return_value = cursor_context
    connection_context = Mock()
    connection_context.__enter__ = Mock(return_value=connection)
    connection_context.__exit__ = Mock(return_value=False)

    psycopg = Mock(connect=Mock(return_value=connection_context))
    return connection, psycopg


if __name__ == "__main__":
    unittest.main()
