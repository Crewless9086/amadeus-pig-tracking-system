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


MODULE_PATH = Path(__file__).resolve().parents[1] / "modules" / "telemetry" / "forecast_logger.py"

SPEC = importlib.util.spec_from_file_location("amadeus_forecast_logger", MODULE_PATH)
forecast_logger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forecast_logger)
for module_name in STUBBED_MODULES:
    sys.modules.pop(module_name, None)


def health_stub(payload):
    return {"success":True,"allowed":True,"attempt_id":payload["attempt_id"],
        "generation":payload.get("generation",1),"provider":payload["provider"],
        "source_id":forecast_logger.PROVIDERS[payload["provider"]][0]}


class LoggerImportTests(unittest.TestCase):
    def test_reusable_module_import_does_not_load_dotenv_or_call_network(self):
        import requests
        import dotenv
        with patch.object(requests,"get",side_effect=AssertionError("network forbidden")), patch.object(
                requests,"post",side_effect=AssertionError("network forbidden")), patch.object(
                dotenv,"load_dotenv",side_effect=AssertionError("dotenv import side effect")):
            spec=importlib.util.spec_from_file_location("forecast_import_probe",MODULE_PATH)
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))


class ForecastLoggerTests(unittest.TestCase):
    def setUp(self):
        refresh=patch.object(forecast_logger,"refresh_configuration")
        refresh.start();self.addCleanup(refresh.stop)
        env=patch.dict(os.environ,{"FORECAST_PROVIDERS":"open_meteo","WEATHERAPI_API_KEY":""})
        env.start();self.addCleanup(env.stop)
        health=patch.object(forecast_logger,"_health_request",side_effect=health_stub)
        health.start();self.addCleanup(health.stop)

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
            with self.assertRaisesRegex(SystemExit, "2"):
                forecast_logger.main(nightly=False)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "provider_rate_limited")
        self.assertTrue(result["existing_forecast_preserved"])
        self.assertFalse(result["success"])


from copy import deepcopy
from datetime import datetime, timedelta, timezone

FIXED = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)

class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)


def primary_fixture():
    return {"timezone": "Africa/Johannesburg", "daily_units": {
        "temperature_2m_max": "\u00b0C", "temperature_2m_min": "\u00b0C", "precipitation_sum": "mm",
        "precipitation_probability_max": "%", "wind_speed_10m_max": "km/h", "wind_gusts_10m_max": "km/h"}, "daily": {
        "time": ["2026-11-19", "2026-11-20", "2026-11-21"],
        "temperature_2m_max": [25, 26, 27], "temperature_2m_min": [12, 13, 14],
        "precipitation_sum": [0, 1.2, 2.4], "precipitation_probability_max": [5, 30, 60],
        "wind_speed_10m_max": [10, 11, 12], "wind_gusts_10m_max": [20, 21, 22]}}


def backup_fixture():
    return {"location": {"tz_id": "Africa/Johannesburg"},
        "forecast": {"forecastday": [{"date": date,
            "day": {"maxtemp_c": 25, "mintemp_c": 12, "totalprecip_mm": 1.2,
                "daily_chance_of_rain": 20, "maxwind_kph": 10},
            "hour": [{"time": f"{date} {hour:02d}:00", "chance_of_rain": str(hour),
                "gust_kph": hour+10} for hour in range(24)]}
            for date in ("2026-11-19", "2026-11-20", "2026-11-21")]}}


class ForecastResilienceTests(unittest.TestCase):
    def setUp(self):
        refresh=patch.object(forecast_logger,"refresh_configuration")
        refresh.start();self.addCleanup(refresh.stop)
        env=patch.dict(os.environ,{"FORECAST_PROVIDERS":"open_meteo,weatherapi"})
        env.start();self.addCleanup(env.stop)
        health=patch.object(forecast_logger,"_health_request",side_effect=health_stub)
        health.start();self.addCleanup(health.stop)

    def acquire(self, primary, backup=None):
        with patch.object(forecast_logger, "datetime", FixedClock), patch.dict(os.environ,
                {"WEATHERAPI_API_KEY": "offline-test-key"}), patch.object(forecast_logger,
                "fetch_open_meteo_daily", side_effect=primary) as first, patch.object(forecast_logger,
                "fetch_weatherapi_daily", return_value=backup or backup_fixture()) as second:
            result = forecast_logger.acquire_forecast(-34, 21, "Africa/Johannesburg", 3)
            return result, first.call_count, second.call_count

    def test_primary_success_does_not_fetch_backup(self):
        (rows, data, failures), first, second = self.acquire([primary_fixture()])
        self.assertEqual((first, second), (1, 0))
        self.assertEqual(data["provenance"]["provider"], "open_meteo")
        self.assertEqual(rows[0][0], FIXED.isoformat())
        self.assertEqual(failures, [])

    def test_quota_backup_then_primary_recovery_without_sticky_switch(self):
        with patch.object(forecast_logger, "datetime", FixedClock), patch.dict(os.environ,
                {"WEATHERAPI_API_KEY": "offline-test-key"}), patch.object(forecast_logger,
                "fetch_open_meteo_daily", side_effect=[forecast_logger.ForecastProviderRateLimited(),
                primary_fixture()]) as first, patch.object(forecast_logger,
                "fetch_weatherapi_daily", return_value=backup_fixture()) as second:
            rows, data, failures = forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
            payload = forecast_logger.build_backend_payload(rows, data)
            self.assertEqual(payload["source_id"], "weatherapi-forecast-main")
            self.assertEqual(payload["days"][0]["rain_probability_max_pct"], 23)
            self.assertEqual(payload["days"][0]["gust_max_kmh"], 33)
            self.assertEqual(payload["days"][0]["provider_daily_chance_of_rain_pct"],20)
            self.assertEqual(payload["days"][0]["provenance"], data["provenance"])
            self.assertIsNone(data["provenance"]["provider_model_updated_at"])
            self.assertEqual(data["provenance"]["coverage_days"],3)
            _, recovered, _ = forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
            self.assertEqual(recovered["provenance"]["provider"], "open_meteo")
            self.assertEqual((first.call_count,second.call_count),(2,1))

    def test_invalid_partial_stale_and_missing_primary_required_values_fall_back(self):
        fixtures=[{"timezone":"Africa/Johannesburg","daily":None}]
        wrong_units=primary_fixture();wrong_units["daily_units"]["precipitation_sum"]="inch";fixtures.append(wrong_units)
        partial=primary_fixture();partial["daily"]["time"].pop();fixtures.append(partial)
        stale=primary_fixture();stale["daily"]["time"][0]="2026-11-18";fixtures.append(stale)
        for bad in (None,float("nan"),-1,101):
            value=primary_fixture();value["daily"]["precipitation_probability_max"][0]=bad;fixtures.append(value)
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                (_, data, _), _, second = self.acquire([fixture])
                self.assertEqual(second,1)
                self.assertEqual(data["provenance"]["provider"],"weatherapi")

    def test_backup_missing_hour_or_rain_and_wrong_timezone_rejected(self):
        for kind in ("hour","rain","timezone","probability","null_day","null_hour","null_item"):
            data=backup_fixture()
            if kind=="null_day":data["forecast"]["forecastday"][0]["day"]=None
            if kind=="null_hour":data["forecast"]["forecastday"][0]["hour"][0]=None
            if kind=="null_item":data["forecast"]["forecastday"][0]=None
            if kind=="hour":data["forecast"]["forecastday"][0]["hour"].pop()
            if kind=="rain":data["forecast"]["forecastday"][0]["day"].pop("totalprecip_mm")
            if kind=="timezone":data["location"]["tz_id"]="UTC"
            if kind=="probability":data["forecast"]["forecastday"][0]["hour"][0].pop("chance_of_rain")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                forecast_logger.build_rows(data,-34,21,"Africa/Johannesburg",provider="weatherapi",fetched_at=FIXED)

    def test_both_failed_preserves_existing_and_exits_nonzero(self):
        with patch.object(forecast_logger,"fetch_open_meteo_daily",side_effect=RuntimeError()), patch.object(
                forecast_logger,"fetch_weatherapi_daily",side_effect=RuntimeError()), patch.dict(os.environ,
                {"WEATHERAPI_API_KEY":"offline-test-key","LAT":"-34","LON":"21","TIMEZONE":"Africa/Johannesburg"}), patch.object(
                forecast_logger,"GOOGLE_SHEETS_ENABLED",False), patch.object(forecast_logger,"require_backend_env"), redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(SystemExit,"2"):forecast_logger.main(nightly=False)
        self.assertTrue(json.loads(output.getvalue())["existing_forecast_preserved"])

    def test_long_retry_after_is_not_shortened_or_retried(self):
        for value in ("3600","Thu, 19 Nov 2026 18:00:00 GMT","invalid"):
            response=Mock(status_code=429,text="quota",headers={"Retry-After":value})
            with self.subTest(value=value), patch.object(forecast_logger,"datetime",FixedClock), patch.object(
                    forecast_logger.requests,"get",return_value=response) as get, patch.object(
                    forecast_logger.time,"sleep") as sleep:
                with self.assertRaises(forecast_logger.ForecastProviderRateLimited):
                    forecast_logger.fetch_open_meteo_daily(-34,21,"Africa/Johannesburg",3)
                get.assert_called_once();sleep.assert_not_called()

    def test_network_and_5xx_bounded_then_fallback(self):
        for failure in (forecast_logger.requests.Timeout("secret-url"),Mock(status_code=503,text="busy",headers={})):
            with self.subTest(failure=failure), patch.object(forecast_logger.requests,"get",side_effect=[failure,failure]) as get, patch.object(
                    forecast_logger.time,"sleep"), patch.object(forecast_logger,"OPEN_METEO_MAX_RETRIES",1):
                with self.assertRaises(RuntimeError):forecast_logger.fetch_open_meteo_daily(-34,21,"Africa/Johannesburg",3)
                self.assertEqual(get.call_count,2)

    def test_required_backend_failure_exits_three_even_with_mirror_success(self):
        with patch.object(forecast_logger,"datetime",FixedClock):
            rows=forecast_logger.build_rows(primary_fixture(),-34,21,"Africa/Johannesburg")
        data={"provenance":{"provider":"open_meteo","source_id":"open-meteo-forecast-main"},
            "health_claim":{"provider":"open_meteo","attempt_id":"00000000-0000-0000-0000-000000000001","generation":1}}
        with patch.dict(os.environ,{"LAT":"-34","LON":"21","TIMEZONE":"Africa/Johannesburg",
                "GOOGLE_SHEET_ID":"offline","GOOGLE_SERVICE_ACCOUNT_FILE":"offline"}), patch.object(forecast_logger,
                "BACKEND_INGEST_ENABLED",True), patch.object(forecast_logger,"GOOGLE_SHEETS_ENABLED",True), patch.object(
                forecast_logger,"require_backend_env"), patch.object(forecast_logger,"get_gspread_client"), patch.object(
                forecast_logger,"acquire_forecast",return_value=(rows,data,[])), patch.object(forecast_logger,
                "post_backend_ingest",return_value=(False,"backend_unavailable")), redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(SystemExit,"3"):forecast_logger.main(nightly=False)
        self.assertFalse(json.loads(output.getvalue())["success"])

    def test_backup_requests_free_three_day_contract(self):
        response=Mock(status_code=200);response.json.return_value=backup_fixture()
        with patch.dict(os.environ,{"WEATHERAPI_API_KEY":"offline-secret"}), patch.object(
                forecast_logger.requests,"get",return_value=response) as get:
            forecast_logger.fetch_weatherapi_daily(-34,21,"Africa/Johannesburg",10)
        self.assertEqual(get.call_args.kwargs["params"]["days"],3)
        self.assertEqual(get.call_args.args[0],"https://api.weatherapi.com/v1/forecast.json")

    def test_backend_mismatched_source_ack_is_not_success(self):
        response=Mock(status_code=201);response.json.return_value={"success":True,"source_id":"open-meteo-forecast-main","rows":3}
        with patch.object(forecast_logger,"BACKEND_INGEST_ENABLED",True), patch.object(
                forecast_logger.requests,"post",return_value=response):
            self.assertEqual(forecast_logger.post_backend_ingest({"source_id":"weatherapi-forecast-main","days":[{},{},{}]}),
                (False,"backend_ingest_identity_unconfirmed"))

    def test_backend_http200_false_is_not_success(self):
        response=Mock(status_code=200);response.json.return_value={"success":False}
        with patch.object(forecast_logger,"BACKEND_INGEST_ENABLED",True), patch.object(
                forecast_logger.requests,"post",return_value=response):
            self.assertEqual(forecast_logger.post_backend_ingest({}),(False,"backend_ingest_unconfirmed"))


def visual_fixture():
    return {"timezone":"Africa/Johannesburg","days":[{"datetime":date,
        "tempmax":26,"tempmin":16,"precip":0.2,"precipprob":10,"windspeed":29.5,"windgust":26.4,
        "source":"comb" if i==0 else "fcst", "hours":[{"datetime":f"{h:02d}:00:00",
            "precipprob":10+h,"source":"obs" if i==0 and h<12 else "fcst"} for h in range(24)]}
        for i,date in enumerate(("2026-11-19","2026-11-20","2026-11-21"))]}


class CommercialPrimaryTests(unittest.TestCase):
    def setUp(self):
        refresh=patch.object(forecast_logger,"refresh_configuration")
        refresh.start();self.addCleanup(refresh.stop)

    def test_visual_primary_default_and_three_day_no_key_request(self):
        response=Mock(status_code=200);response.json.return_value=visual_fixture()
        with patch.dict(os.environ,{"FORECAST_PROVIDERS":"visual_crossing,weatherapi","WEATHERAPI_API_KEY":""}), patch.object(
                forecast_logger,"datetime",FixedClock), patch.object(forecast_logger,"_health_request",side_effect=health_stub), patch.object(
                forecast_logger.requests,"get",return_value=response) as get:
            rows,data,failures=forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
        self.assertEqual(get.call_count,1)
        self.assertTrue(get.call_args.args[0].endswith("/-34,21/2026-11-19/2026-11-21"))
        self.assertEqual(get.call_args.kwargs["params"]["unitGroup"],"metric")
        self.assertNotIn("key",get.call_args.kwargs["params"])
        payload=forecast_logger.build_backend_payload(rows,data)
        self.assertEqual(payload["source_id"],"visual-crossing-forecast-main")
        self.assertEqual(payload["days"][0]["rain_probability_max_pct"],33)
        self.assertEqual(payload["days"][0]["provider_source"],"comb")
        self.assertEqual(payload["days"][0]["provider_hour_sources"],["fcst","obs"])
        self.assertFalse(payload["days"][0]["provenance"]["local_observation_credit"])

    def test_health_hold_and_unavailable_never_contact_affected_provider(self):
        for failure in (RuntimeError("health unavailable"),{"allowed":False,"status":"provider_cooldown"}):
            with self.subTest(failure=failure), patch.dict(os.environ,{"FORECAST_PROVIDERS":"visual_crossing"}), patch.object(
                    forecast_logger,"_health_request",side_effect=[failure]), patch.object(forecast_logger.requests,"get") as get:
                with self.assertRaises(RuntimeError):forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
                get.assert_not_called()

    def test_quota_saved_even_both_providers_fail(self):
        records=[]
        def health(payload):records.append(payload);return health_stub(payload)
        quota=forecast_logger.ForecastProviderRateLimited();quota.retry_not_before="2026-11-20T17:00:00+00:00"
        with patch.dict(os.environ,{"FORECAST_PROVIDERS":"visual_crossing,weatherapi","WEATHERAPI_API_KEY":"offline"}), patch.object(
                forecast_logger,"_health_request",side_effect=health), patch.object(forecast_logger,"fetch_visual_crossing_daily",side_effect=quota), patch.object(
                forecast_logger,"fetch_weatherapi_daily",side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
        results=[row for row in records if row["action"]=="result"]
        self.assertEqual(len(results),2)
        self.assertEqual(results[0]["retry_not_before"],quota.retry_not_before)
        self.assertTrue(all(row["status"]=="fetch_failed" for row in results))

    def test_ingested_health_record_follows_backend_ack_and_failure_is_nonzero(self):
        for accepted in (True,False):
            order=[]
            def health(payload):order.append(payload);return health_stub(payload)
            def ingest(payload):order.append({"action":"ingest"});return accepted,None
            with self.subTest(accepted=accepted), patch.dict(os.environ,{"FORECAST_PROVIDERS":"visual_crossing",
                    "LAT":"-34","LON":"21","TIMEZONE":"Africa/Johannesburg"}), patch.object(forecast_logger,
                    "datetime",FixedClock), patch.object(forecast_logger,"require_backend_env"), patch.object(forecast_logger,
                    "GOOGLE_SHEETS_ENABLED",False), patch.object(forecast_logger,"BACKEND_INGEST_ENABLED",True), patch.object(
                    forecast_logger,"fetch_visual_crossing_daily",return_value=visual_fixture()), patch.object(forecast_logger,
                    "_health_request",side_effect=health), patch.object(forecast_logger,"post_backend_ingest",side_effect=ingest), redirect_stdout(io.StringIO()) as output:
                if accepted:forecast_logger.main(nightly=False)
                else:
                    with self.assertRaisesRegex(SystemExit,"3"):forecast_logger.main(nightly=False)
            self.assertEqual([item["action"] for item in order],["claim","ingest","result"])
            self.assertEqual(order[-1]["status"],"ingested" if accepted else "ingest_failed")
            self.assertEqual(json.loads(output.getvalue())["success"],accepted)

    def test_persisted_retry_after_survives_new_refresh_and_primary_recovers_when_due(self):
        from modules.telemetry.forecast_provider_health import transition
        states={};clock=[FIXED];calls=[]
        class MovingClock(datetime):
            @classmethod
            def now(cls,tz=None):return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
        def health(payload):
            state,result,code,_=transition(states.get(payload["provider"],{}),payload,clock[0])
            states[payload["provider"]]=state
            self.assertEqual(code,200)
            return {**result,"provider":payload["provider"],"source_id":forecast_logger.PROVIDERS[payload["provider"]][0]}
        def request(url,**kwargs):
            calls.append(url)
            if "visualcrossing" in url and len(calls)==1:
                return Mock(status_code=429,text="quota",headers={"Retry-After":"3600"})
            response=Mock(status_code=200)
            response.json.return_value=visual_fixture() if "visualcrossing" in url else backup_fixture()
            return response
        with patch.dict(os.environ,{"FORECAST_PROVIDERS":"visual_crossing,weatherapi","WEATHERAPI_API_KEY":"offline"}), patch.object(
                forecast_logger,"datetime",MovingClock), patch.object(forecast_logger,"_health_request",side_effect=health), patch.object(
                forecast_logger.requests,"get",side_effect=request):
            selected=[]
            for offset in (0,900,3601):
                clock[0]=FIXED+timedelta(seconds=offset)
                rows,data,_=forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
                selected.append(data["provenance"]["provider"])
                # Represent the separately tested required-ingest acknowledgement boundary.
                self.assertTrue(forecast_logger._finish_provider(data["health_claim"],"ingested",forecast_run_at=rows[0][0]))
        self.assertEqual(selected,["weatherapi","weatherapi","visual_crossing"])
        self.assertEqual(sum("visualcrossing" in url for url in calls),2)
        self.assertEqual(states["visual_crossing"]["retry_not_before"],(FIXED+timedelta(hours=1)).isoformat())

    def test_primary_success_configuration_still_discloses_unconfigured_backup(self):
        with patch.dict(os.environ,{"FORECAST_PROVIDERS":"visual_crossing,weatherapi","WEATHERAPI_API_KEY":""}):
            self.assertEqual(forecast_logger.provider_configuration(),[
                {"provider":"visual_crossing","configured":True},{"provider":"weatherapi","configured":False}])

    def test_unconfigured_backup_is_explicit(self):
        with patch.dict(os.environ,{"FORECAST_PROVIDERS":"weatherapi","WEATHERAPI_API_KEY":""}), patch.object(
                forecast_logger,"_health_request") as health:
            with self.assertRaises(RuntimeError) as failure:forecast_logger.acquire_forecast(-34,21,"Africa/Johannesburg",3)
        self.assertEqual(failure.exception.provider_failures,[{"provider":"weatherapi","failure_kind":"not_configured"}])
        health.assert_not_called()

    def test_visual_missing_hours_and_probability_do_not_fabricate_dry_day(self):
        for kind in ("hours","probability","source"):
            data=visual_fixture()
            if kind=="hours":data["days"][0]["hours"].pop()
            if kind=="probability":data["days"][0]["hours"][0]["precipprob"]=None
            if kind=="source":data["days"][0]["source"]="obs"
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                forecast_logger.build_rows(data,-34,21,"Africa/Johannesburg",provider="visual_crossing",fetched_at=FIXED)


class LoggerStartupConfigurationTests(unittest.TestCase):
    def test_dotenv_values_loaded_after_import_are_used_by_main(self):
        spec=importlib.util.spec_from_file_location("forecast_startup_probe",MODULE_PATH)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        loaded={"LAT":"-34","LON":"21","TIMEZONE":"Africa/Johannesburg",
            "AMADEUS_BACKEND_URL":"https://backend.invalid/","TELEMETRY_INGEST_API_KEY":"offline-startup-key",
            "BACKEND_INGEST_ENABLED":"true","GOOGLE_SHEETS_ENABLED":"false",
            "OPEN_METEO_MAX_RETRIES":"2","FORECAST_PROVIDERS":"visual_crossing"}
        def acquire(*args):
            self.assertTrue(module.BACKEND_INGEST_ENABLED)
            self.assertFalse(module.GOOGLE_SHEETS_ENABLED)
            self.assertEqual(module.AMADEUS_BACKEND_URL,"https://backend.invalid")
            self.assertEqual(module.TELEMETRY_INGEST_API_KEY,"offline-startup-key")
            self.assertEqual(module.OPEN_METEO_MAX_RETRIES,2)
            rows=module.build_rows(visual_fixture(),-34,21,"Africa/Johannesburg",provider="visual_crossing",fetched_at=FIXED)
            return rows,{"response":visual_fixture(),"provenance":{"provider":"visual_crossing","source_id":"visual-crossing-forecast-main"},
                "health_claim":{"provider":"visual_crossing","generation":1,"attempt_id":"00000000-0000-0000-0000-000000000001"}},[]
        with patch.dict(os.environ,{},clear=True), patch.object(module,"load_dotenv",side_effect=lambda:os.environ.update(loaded)), patch.object(
                module,"acquire_forecast",side_effect=acquire), patch.object(module,"post_backend_ingest",return_value=(True,None)), patch.object(
                module,"_finish_provider",return_value=True), redirect_stdout(io.StringIO()) as output:
            module.main(nightly=False)
        self.assertTrue(json.loads(output.getvalue())["success"])
        self.assertNotIn("offline-startup-key",output.getvalue())


if __name__ == "__main__":
    unittest.main()

def test_duplicate_whole_nightly_logger_never_reaches_primary_or_backup():
    env={'LAT':'-34','LON':'21','TIMEZONE':'Africa/Johannesburg',
        'GOOGLE_SHEETS_ENABLED':'false','BACKEND_INGEST_ENABLED':'true',
        'AMADEUS_BACKEND_URL':'https://offline.invalid','TELEMETRY_INGEST_API_KEY':'offline'}
    with patch.dict(os.environ,env,clear=True), patch.object(forecast_logger,'load_dotenv'), \
            patch.object(forecast_logger,'_health_request',return_value={'success':True,'allowed':False,'status':'nightly_cycle_already_claimed'}) as health_call, \
            patch.object(forecast_logger,'acquire_forecast',side_effect=AssertionError('extra acquisition')), \
            redirect_stdout(io.StringIO()) as output:
        forecast_logger.main()
    assert health_call.call_count==1
    assert json.loads(output.getvalue())['provider_calls']==0


def test_health_request_client_outlasts_existing_endpoint_bound():
    from modules.oom_sakkie.bounded_postgres_read import OWNER_REQUEST_DEADLINE_SECONDS
    class Response:
        status_code=200
        def json(self):return {'success':True,'provider':'visual_crossing','source_id':'visual-crossing-forecast-main'}
    with patch.object(forecast_logger,'AMADEUS_BACKEND_URL','https://offline.invalid'), \
            patch.object(forecast_logger,'TELEMETRY_INGEST_API_KEY','offline'), \
            patch.object(forecast_logger.requests,'post',return_value=Response()) as post:
        forecast_logger._health_request({'provider':'visual_crossing','action':'nightly_claim'})
    connect,read=post.call_args.kwargs['timeout']
    assert connect==3 and read>OWNER_REQUEST_DEADLINE_SECONDS


def test_nightly_admission_failures_exit_without_provider_calls():
    import pytest
    env={'LAT':'-34','LON':'21','TIMEZONE':'Africa/Johannesburg',
        'GOOGLE_SHEETS_ENABLED':'false','BACKEND_INGEST_ENABLED':'true',
        'AMADEUS_BACKEND_URL':'https://offline.invalid','TELEMETRY_INGEST_API_KEY':'offline'}
    failures = [RuntimeError('forecast_health_unavailable'),
        {'success':False,'allowed':False,'status':'database_unavailable'},
        {'success':False,'allowed':True,'cycle':{'attempt_id':'x'}},
        {'success':True,'allowed':True,'cycle':{'attempt_id':'x'}},
        {'success':True,'allowed':False,'status':'unrecognized_hold'}]
    for failure in failures:
        kwargs={'side_effect':failure} if isinstance(failure,Exception) else {'return_value':failure}
        with patch.dict(os.environ,env,clear=True), patch.object(forecast_logger,'load_dotenv'), \
                patch.object(forecast_logger,'_health_request',**kwargs) as health, \
                patch.object(forecast_logger,'acquire_forecast',side_effect=AssertionError('provider call')), \
                redirect_stdout(io.StringIO()) as output:
            with pytest.raises(SystemExit) as error: forecast_logger.main()
        assert error.value.code == 2 and health.call_count == 1
        result=json.loads(output.getvalue())
        assert result['success'] is False and result['provider_calls'] == 0
        assert result['existing_forecast_preserved'] is True


def test_health_http_unconfirmed_claim_never_reaches_provider_for_legacy_client(monkeypatch):
    import pytest
    from modules.telemetry import forecast_provider_health as health
    from tests.test_forecast_provider_health import Connection
    monkeypatch.setenv(health.INGEST_API_KEY_ENV,'offline-key')
    connection=Connection(({'owner':'preserve'},'visual_crossing','forecast',True))
    replies=[]
    def server(url,*,json,headers,timeout):
        # Exact legacy claim fields: deployed clients had neither a nightly
        # cycle nor an expiry. Route that request to the real new endpoint.
        legacy={k:v for k,v in json.items() if k!='request_expires_at'}
        assert set(legacy)=={'provider','action','attempt_id'}
        body,status=health.provider_health(legacy,headers['X-Amadeus-Telemetry-Key'],
            connect_factory=lambda:connection)
        replies.append((body,status))
        class Response:
            status_code=status
            def json(self):return body
        return Response()
    with patch.dict(os.environ,{'FORECAST_PROVIDERS':'visual_crossing'}), \
            patch.object(forecast_logger,'AMADEUS_BACKEND_URL','https://offline.invalid'), \
            patch.object(forecast_logger,'TELEMETRY_INGEST_API_KEY','offline-key'), \
            patch.object(forecast_logger.requests,'post',side_effect=server) as post, \
            patch.object(forecast_logger,'fetch_visual_crossing_daily',side_effect=AssertionError('provider call')):
        with pytest.raises(RuntimeError,match='forecast_all_providers_unavailable'):
            forecast_logger.acquire_forecast(-34,21,'Africa/Johannesburg',3)
    assert post.call_count == 1 and connection.sql==[]
    assert replies[0][1]==400 and replies[0][0]['status']=='nightly_cycle_required'


def test_hourly_planning_preserves_forecast_only_and_target_date():
    data={'provenance':{'provider':'visual_crossing'},'response':{'days':[
        {'datetime':'2026-11-20','hours':[{'datetime':'08:00:00','source':'fcst',
            'precip':2,'precipprob':40,'windspeed':10},
            {'datetime':'09:00:00','source':'obs','precip':99}]},
        {'datetime':'2026-11-21','hours':[{'datetime':'10:00:00','source':'fcst',
            'precip':0,'precipprob':0,'windspeed':5}]}]}}
    hours=forecast_logger._planning_hours(data,'2026-11-21')
    assert len(hours)==1 and hours[0]['start_at']=='2026-11-21T10:00:00+02:00'
    assert hours[0]['local_observation_credit'] is False
    assert len(forecast_logger._planning_hours(data,'2026-11-20'))==1
    backup={'provenance':{'provider':'weatherapi'},'response':{'forecast':{'forecastday':[
        {'date':'2026-11-21','hour':[{'time':'2026-11-21 12:00','precip_mm':1,
            'chance_of_rain':30,'wind_kph':4}]}]}}}
    hour=forecast_logger._planning_hours(backup,'2026-11-21')[0]
    assert hour['start_at']=='2026-11-21T12:00:00+02:00'
    assert hour['source']=='fcst' and hour['local_observation_credit'] is False
