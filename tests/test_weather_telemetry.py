import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from modules.telemetry.weather_service import (
    get_current_weather_state,
    get_weather_forecast,
    get_weather_today_summary,
    ingest_weather_forecast,
    ingest_weather_reading,
)


class WeatherTelemetryTests(unittest.TestCase):
    def test_weather_ingest_requires_configured_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = ingest_weather_reading({}, provided_api_key="")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "ingest_key_not_configured")

    @patch.dict(os.environ, {"TELEMETRY_INGEST_API_KEY": "expected"}, clear=True)
    def test_weather_ingest_rejects_invalid_api_key(self):
        result, status_code = ingest_weather_reading({}, provided_api_key="wrong")

        self.assertEqual(status_code, 401)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unauthorized")

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgresql://user:secret@example/db",
            "TELEMETRY_INGEST_API_KEY": "expected",
        },
        clear=True,
    )
    def test_weather_ingest_writes_raw_and_latest_state(self):
        cursor = Mock()
        _connection, psycopg = _mock_psycopg_connection(cursor)
        payload = {
            "timestamp_za": "2026-05-22T03:10:00+02:00",
            "temperature_c": 13.4,
            "humidity_pct": 88,
            "wind_speed_kmh": 4.2,
            "wind_gust_kmh": 11.5,
            "wind_direction_deg": 230,
            "rain_rate_mm_h": 0,
            "rain_today_mm": 0.8,
            "pressure_hpa": 1018.2,
        }

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = ingest_weather_reading(payload, provided_api_key="expected")

        self.assertEqual(status_code, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["source_id"], "weather-station-main")
        self.assertEqual(cursor.execute.call_count, 2)
        first_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(first_params["temperature_c"], 13.4)
        self.assertEqual(first_params["rain_today_mm"], 0.8)
        self.assertIn("irrigation_caution", first_params["flags"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_current_weather_returns_prepared_payload(self):
        cursor = Mock()
        cursor.fetchone.return_value = (
            "weather-station-main",
            "Amadeus Local Weather Station",
            "weather_com_pws",
            30,
            datetime.now(timezone.utc),
            Decimal("13.4"),
            Decimal("88"),
            Decimal("4.2"),
            Decimal("11.5"),
            Decimal("230"),
            Decimal("0"),
            Decimal("0.8"),
            Decimal("1018.2"),
            {"rain_today": True},
            "caution",
            "Weather is usable, but rain or irrigation caution is showing.",
            ["Rain today is 0.8 mm."],
        )
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_current_weather_state()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["source"]["source_id"], "weather-station-main")
        self.assertEqual(result["current"]["temperature_c"], 13.4)
        self.assertEqual(result["units"]["rain_rate"], "mm/h")
        self.assertFalse(result["source"]["writes_to_supabase"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_current_weather_no_reading_returns_unavailable(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_current_weather_state()

        self.assertEqual(status_code, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unavailable")

    @patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgresql://user:secret@example/db",
            "TELEMETRY_INGEST_API_KEY": "expected",
        },
        clear=True,
    )
    def test_forecast_ingest_writes_snapshot_rows(self):
        cursor = Mock()
        _connection, psycopg = _mock_psycopg_connection(cursor)
        payload = {
            "forecast_run_at": "2026-05-22T03:00:00+02:00",
            "timezone": "Africa/Johannesburg",
            "days": [
                {
                    "forecast_date": "2026-05-22",
                    "offset_days": 0,
                    "temp_max_c": 20.4,
                    "temp_min_c": 8.9,
                    "rain_sum_mm": 0.6,
                    "rain_probability_max_pct": 35,
                    "wind_max_kmh": 18.7,
                    "gust_max_kmh": 32.1,
                },
                {
                    "forecast_date": "2026-05-23",
                    "offset_days": 1,
                    "temp_max_c": 22.1,
                    "temp_min_c": 9.2,
                    "rain_sum_mm": 0,
                    "rain_probability_max_pct": 10,
                    "wind_max_kmh": 12,
                    "gust_max_kmh": 20,
                },
            ],
        }

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = ingest_weather_forecast(payload, provided_api_key="expected")

        self.assertEqual(status_code, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(cursor.execute.call_count, 2)
        first_params = cursor.execute.call_args_list[0].args[1]
        self.assertEqual(first_params["source_id"], "open-meteo-forecast-main")
        self.assertIn("rain_expected", first_params["flags"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_forecast_read_returns_latest_snapshot_window(self):
        cursor = Mock()
        cursor.fetchone.return_value = (
            "open-meteo-forecast-main",
            "Amadeus Forecast",
            "open_meteo",
            360,
        )
        cursor.fetchall.return_value = [
            (
                datetime.now(timezone.utc),
                "Africa/Johannesburg",
                date(2026, 5, 22),
                0,
                Decimal("20.4"),
                Decimal("8.9"),
                Decimal("0.6"),
                Decimal("35"),
                Decimal("18.7"),
                Decimal("32.1"),
                {"rain_expected": True},
            )
        ]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_weather_forecast(days=3)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["window"]["requested_days"], 3)
        self.assertEqual(result["window"]["returned_days"], 1)
        self.assertEqual(result["days"][0]["forecast_date"], "2026-05-22")
        self.assertTrue(result["days"][0]["flags"]["rain_expected"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_forecast_no_rows_returns_unavailable(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_weather_forecast(days=3)

        self.assertEqual(status_code, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["window"]["returned_days"], 0)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_today_weather_summary_returns_sample_aggregates(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (
                "weather-station-main",
                "Amadeus Local Weather Station",
                "weather_com_pws",
                30,
            ),
            (
                12,
                datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 22, 1, 0, tzinfo=timezone.utc),
                Decimal("10.5"),
                Decimal("18.2"),
                Decimal("14.1"),
                Decimal("88.2"),
                Decimal("12.4"),
                Decimal("25.8"),
                Decimal("0.4"),
                Decimal("1.2"),
                True,
            ),
        ]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_weather_today_summary("2026-05-22")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["window"]["date"], "2026-05-22")
        self.assertEqual(result["window"]["reading_count"], 12)
        self.assertEqual(result["temperature"]["max_c"], 18.2)
        self.assertEqual(result["rain"]["total_mm"], 1.2)
        self.assertTrue(result["flags"]["rain_today"])
        self.assertIn("Rain total so far is 1.2 mm.", result["summary"]["operator_notes"])

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_today_weather_summary_no_rows_returns_unavailable(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (
                "weather-station-main",
                "Amadeus Local Weather Station",
                "weather_com_pws",
                30,
            ),
            (
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ]
        _connection, psycopg = _mock_psycopg_connection(cursor)

        with patch.dict("sys.modules", {"psycopg": psycopg}):
            result, status_code = get_weather_today_summary("2026-05-22")

        self.assertEqual(status_code, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["window"]["returned_readings"], 0)

    def test_weather_routes_are_registered(self):
        route_source = Path("modules/telemetry/telemetry_routes.py").read_text(encoding="utf-8")

        self.assertIn("/telemetry/weather/current", route_source)
        self.assertIn("/telemetry/weather/today", route_source)
        self.assertIn("/telemetry/weather/forecast", route_source)
        self.assertIn("/telemetry/weather/ingest", route_source)
        self.assertIn("/telemetry/weather/forecast/ingest", route_source)


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
