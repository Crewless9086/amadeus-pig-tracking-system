import importlib.util
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


STUBBED_MODULES = []
if "gspread" not in sys.modules:
    gspread_stub = types.ModuleType("gspread")
    gspread_stub.Client = object
    gspread_stub.Spreadsheet = object
    gspread_stub.WorksheetNotFound = type("WorksheetNotFound", (Exception,), {})
    sys.modules["gspread"] = gspread_stub
    STUBBED_MODULES.append("gspread")
if "pytz" not in sys.modules:
    sys.modules["pytz"] = types.ModuleType("pytz")
    STUBBED_MODULES.append("pytz")
if "google.oauth2.service_account" not in sys.modules:
    google_stub = types.ModuleType("google")
    oauth2_stub = types.ModuleType("google.oauth2")
    service_account_stub = types.ModuleType("google.oauth2.service_account")
    service_account_stub.Credentials = object
    sys.modules.setdefault("google", google_stub)
    sys.modules.setdefault("google.oauth2", oauth2_stub)
    sys.modules["google.oauth2.service_account"] = service_account_stub
    STUBBED_MODULES.extend(["google.oauth2.service_account", "google.oauth2", "google"])


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "external_sources"
    / "telemetry"
    / "forecast"
    / "amadeus-forecast-logger"
    / "main.py"
)
SPEC = importlib.util.spec_from_file_location("amadeus_forecast_logger", MODULE_PATH)
forecast_logger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forecast_logger)
for module_name in STUBBED_MODULES:
    sys.modules.pop(module_name, None)


class ForecastLoggerTests(unittest.TestCase):
    def test_daily_provider_limit_is_not_retried(self):
        response = Mock(
            status_code=429,
            text='{"error":true,"reason":"Daily API request limit exceeded."}',
            headers={},
        )
        with patch.object(forecast_logger.requests, "get", return_value=response) as request_get:
            with self.assertRaises(forecast_logger.ForecastProviderRateLimited):
                forecast_logger.fetch_open_meteo_daily(-34.0, 21.0, "Africa/Johannesburg", 10)
        request_get.assert_called_once()

    def test_transient_rate_limit_retries_once(self):
        limited = Mock(status_code=429, text="rate limited", headers={"Retry-After": "1"})
        success = Mock(status_code=200)
        success.json.return_value = {"daily": {"time": []}}
        with patch.object(forecast_logger, "OPEN_METEO_MAX_RETRIES", 1), patch.object(
            forecast_logger.requests, "get", side_effect=[limited, success]
        ) as request_get, patch.object(forecast_logger.time, "sleep") as sleep:
            result = forecast_logger.fetch_open_meteo_daily(-34.0, 21.0, "Africa/Johannesburg", 10)
        self.assertEqual(result, {"daily": {"time": []}})
        self.assertEqual(request_get.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_api_key_is_passed_without_being_logged(self):
        response = Mock(status_code=200)
        response.json.return_value = {"daily": {"time": []}}
        with patch.object(forecast_logger, "OPEN_METEO_API_KEY", "secret-key"), patch.object(
            forecast_logger.requests, "get", return_value=response
        ) as request_get:
            forecast_logger.fetch_open_meteo_daily(-34.0, 21.0, "Africa/Johannesburg", 10)
        self.assertEqual(request_get.call_args.kwargs["params"]["apikey"], "secret-key")

    def test_main_preserves_existing_forecast_on_daily_limit(self):
        output = io.StringIO()
        env = {
            "BACKEND_INGEST_ENABLED": "false",
            "GOOGLE_SHEETS_ENABLED": "false",
            "LAT": "-34.0",
            "LON": "21.0",
            "TIMEZONE": "Africa/Johannesburg",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            forecast_logger, "GOOGLE_SHEETS_ENABLED", False
        ), patch.object(
            forecast_logger,
            "fetch_open_meteo_daily",
            side_effect=forecast_logger.ForecastProviderRateLimited("Open-Meteo daily request limit exceeded"),
        ), redirect_stdout(output):
            forecast_logger.main()
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "provider_rate_limited")
        self.assertTrue(result["existing_forecast_preserved"])
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
