from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from zoneinfo import ZoneInfo
import math
from uuid import uuid4
from typing import Optional

import requests
from dotenv import load_dotenv


CURRENT_TAB = "Forecast_10Day_Current"
HISTORY_TAB = "Forecast_10Day_History"

HEADERS = [
    "run_timestamp",
    "timezone",
    "forecast_date",
    "offset_days",
    "temp_max_c",
    "temp_min_c",
    "rain_sum_mm",
    "rain_prob_max_pct",
    "wind_max_kmh",
    "gust_max_kmh",
    "source",
    "lat",
    "lon",
]

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_API_KEY = ""
OPEN_METEO_MAX_RETRIES = 1
WEATHERAPI_URL = "https://api.weatherapi.com/v1/forecast.json"
PROVIDER_BUDGET_SECONDS = 60
MAX_RETRY_WAIT_SECONDS = 15
HEALTH_REQUEST_SECONDS = 45
HEALTH_OPERATION_SECONDS = 150
HEALTH_MAX_ATTEMPTS = 3
PROVIDERS = {
    "visual_crossing": ("visual-crossing-forecast-main", "Visual Crossing Weather", "https://www.visualcrossing.com/"),
    "weatherapi": ("weatherapi-forecast-main", "WeatherAPI.com", "https://www.weatherapi.com/"),
    "open_meteo": ("open-meteo-forecast-main", "Open-Meteo", "https://open-meteo.com/"),
}

AMADEUS_BACKEND_URL = ""
TELEMETRY_INGEST_API_KEY = ""
BACKEND_INGEST_ENABLED = False
GOOGLE_SHEETS_ENABLED = True


def refresh_configuration():
    """Read runtime configuration only after the entrypoint loads dotenv."""
    global OPEN_METEO_URL, OPEN_METEO_API_KEY, OPEN_METEO_MAX_RETRIES
    global AMADEUS_BACKEND_URL, TELEMETRY_INGEST_API_KEY
    global BACKEND_INGEST_ENABLED, GOOGLE_SHEETS_ENABLED
    OPEN_METEO_URL = os.getenv("OPEN_METEO_API_URL", "https://api.open-meteo.com/v1/forecast").strip()
    OPEN_METEO_API_KEY = os.getenv("OPEN_METEO_API_KEY", "").strip()
    OPEN_METEO_MAX_RETRIES = min(2, max(0, int(os.getenv("OPEN_METEO_MAX_RETRIES", "1"))))
    AMADEUS_BACKEND_URL = os.getenv("AMADEUS_BACKEND_URL", "").strip().rstrip("/")
    TELEMETRY_INGEST_API_KEY = os.getenv("TELEMETRY_INGEST_API_KEY", "").strip()
    BACKEND_INGEST_ENABLED = os.getenv("BACKEND_INGEST_ENABLED", "false").strip().lower() == "true"
    GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "true").strip().lower() == "true"


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def require_backend_env() -> None:
    if not BACKEND_INGEST_ENABLED:
        return

    missing = []
    for name, value in [
        ("AMADEUS_BACKEND_URL", AMADEUS_BACKEND_URL),
        ("TELEMETRY_INGEST_API_KEY", TELEMETRY_INGEST_API_KEY),
    ]:
        if not value:
            missing.append(name)

    if missing:
        raise RuntimeError(f"Missing required env var(s): {', '.join(missing)}")


def get_gspread_client(sa_file: str) -> gspread.Client:
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        creds_dict = json.loads(sa_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(sa_file, scopes=scopes)

    return gspread.authorize(creds)


def get_or_create_ws(spreadsheet: gspread.Spreadsheet, title: str, rows: int = 200, cols: int = 20):
    import gspread
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=str(rows), cols=str(cols))


class ForecastProviderRateLimited(RuntimeError):
    pass


def fetch_open_meteo_daily(lat: float, lon: float, tz: str, days: int) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "forecast_days": days,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "precipitation_probability_max",
        ]),
    }
    if OPEN_METEO_API_KEY:
        params["apikey"] = OPEN_METEO_API_KEY

    return _fetch_json(OPEN_METEO_URL, params, "open_meteo", OPEN_METEO_MAX_RETRIES)


def _retry_delay(value, attempt):
    if not value:
        return 2 ** attempt
    try:
        delay = float(value)
        if not math.isfinite(delay) or delay < 0:
            return None
        return delay
    except (ValueError, TypeError):
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                return None
            return max(0, (stamp-datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def _fetch_json(url, params, provider, retries):
    deadline = time.monotonic() + PROVIDER_BUDGET_SECONDS
    retry_bound = None
    for attempt in range(min(2, retries) + 1):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            error = RuntimeError(provider + "_deadline")
            error.failure_kind = "deadline"
            error.retry_not_before = retry_bound.isoformat() if retry_bound else None
            raise error
        try:
            response = requests.get(url, params=params, timeout=min(20, remaining))
        except requests.RequestException:
            response = None
        if response is not None and response.status_code == 200:
            try:
                packet = response.json()
            except ValueError:
                raise ValueError(provider + "_invalid_json") from None
            if not isinstance(packet, dict) or packet.get("error"):
                raise ValueError(provider + "_invalid_payload")
            return packet
        status = response.status_code if response is not None else 0
        quota = status == 429
        daily = quota and "daily api request limit exceeded" in response.text.lower()
        failure = ForecastProviderRateLimited if quota else RuntimeError
        header = response.headers.get("Retry-After") if response is not None else None
        delay = _retry_delay(header, attempt)
        if header and delay is not None:
            try:
                bound = datetime.now(timezone.utc)+timedelta(seconds=delay)
                retry_bound = max(retry_bound, bound) if retry_bound else bound
            except OverflowError:
                # An unrepresentable provider bound is not permission to retry early.
                retry_bound = datetime.max.replace(tzinfo=timezone.utc)
        error = failure(provider + "_request_failed_" + str(status))
        error.failure_kind = "quota" if quota else "network" if status == 0 else "http_error"
        error.retry_not_before = retry_bound.isoformat() if retry_bound else None
        if daily or status not in (0, 429) and status < 500:
            raise error
        # Never shorten provider instructions to fit this cron's bounded retry budget.
        if (attempt >= min(2, retries) or delay is None or delay > MAX_RETRY_WAIT_SECONDS
                or delay + 1 >= deadline-time.monotonic()):
            raise error
        time.sleep(delay)
    raise RuntimeError(provider + "_request_failed")


def fetch_weatherapi_daily(lat, lon, tz, days=3):
    key = os.getenv("WEATHERAPI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("weatherapi_not_configured")
    return _fetch_json(WEATHERAPI_URL, {"key": key, "q": f"{lat},{lon}",
        "days": 3, "aqi": "no", "alerts": "no"}, "weatherapi", 1)



def fetch_visual_crossing_daily(lat, lon, tz, days=3):
    start = datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
    end = start+timedelta(days=2)
    url = ("https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
        + f"{lat},{lon}/{start.isoformat()}/{end.isoformat()}")
    return _fetch_json(url, {"unitGroup": "metric", "include": "days,hours",
        "elements": "datetime,tempmax,tempmin,precip,precipprob,windspeed,windgust,source",
        "contentType": "json"}, "visual_crossing", 1)

def _number(value, minimum=None, maximum=None, required=True):
    if value is None and not required:
        return None
    if isinstance(value, bool):
        raise ValueError("forecast_numeric_field_invalid")
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError("forecast_numeric_field_missing") from None
    if (not math.isfinite(number) or minimum is not None and number < minimum
            or maximum is not None and number > maximum):
        raise ValueError("forecast_numeric_field_out_of_range")
    return number


def build_rows(data, lat, lon, tz, *, provider="open_meteo", fetched_at=None):
    fetched_at = fetched_at or datetime.now(timezone.utc)
    if fetched_at.tzinfo is None or tz != "Africa/Johannesburg":
        raise ValueError("forecast_timezone_unproven")
    today = fetched_at.astimezone(ZoneInfo(tz)).date()
    rows = []
    try:
        if provider == "open_meteo":
            if data.get("timezone") != tz:
                raise ValueError("forecast_timezone_mismatch")
            units = data.get("daily_units") or {}
            expected_units = {"temperature_2m_max": "\u00b0C", "temperature_2m_min": "\u00b0C",
                "precipitation_sum": "mm", "precipitation_probability_max": "%",
                "wind_speed_10m_max": "km/h", "wind_gusts_10m_max": "km/h"}
            if any(units.get(key) != value for key, value in expected_units.items()):
                raise ValueError("forecast_units_unproven")
            daily = data["daily"]
            dates = daily["time"]
            fields = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum",
                "precipitation_probability_max", "wind_speed_10m_max", "wind_gusts_10m_max")
            if not isinstance(dates, list) or any(len(daily[key]) != len(dates) for key in fields):
                raise ValueError("forecast_daily_arrays_incomplete")
            entries = [(day, [daily[key][i] for key in fields]) for i, day in enumerate(dates)]
        elif provider == "visual_crossing":
            if data.get("timezone") != tz:
                raise ValueError("forecast_timezone_mismatch")
            entries = []
            for day in data["days"]:
                hours = day["hours"]
                if [hour.get("datetime") for hour in hours] != [f"{h:02d}:00:00" for h in range(24)]:
                    raise ValueError("forecast_hourly_coverage_incomplete")
                if day.get("source") not in {"comb", "fcst"} or any(
                        hour.get("source") not in {"obs", "fcst"} for hour in hours):
                    raise ValueError("forecast_provider_source_invalid")
                probability = max(_number(hour.get("precipprob"), 0, 100) for hour in hours)
                entries.append((day["datetime"], [day.get("tempmax"), day.get("tempmin"),
                    day.get("precip"), probability, day.get("windspeed"), day.get("windgust")]))
        elif provider == "weatherapi":
            if data["location"]["tz_id"] != tz:
                raise ValueError("forecast_timezone_mismatch")
            entries = []
            for item in data["forecast"]["forecastday"]:
                day = item["day"]; hours = item["hour"]; date = item["date"]
                _number(day.get("daily_chance_of_rain"), 0, 100, required=False)
                expected = [f"{date} {hour:02d}:00" for hour in range(24)]
                if [hour.get("time") for hour in hours] != expected:
                    raise ValueError("forecast_hourly_coverage_incomplete")
                probability = max(_number(hour.get("chance_of_rain"), 0, 100) for hour in hours)
                gusts = [_number(hour.get("gust_kph"), 0, required=False) for hour in hours]
                entries.append((date, [day.get("maxtemp_c"), day.get("mintemp_c"),
                    day.get("totalprecip_mm"), probability, day.get("maxwind_kph"),
                    max(gusts) if all(value is not None for value in gusts) else None]))
        else:
            raise ValueError("forecast_provider_unknown")
        if provider in {"visual_crossing", "weatherapi"} and len(entries) != 3:
            raise ValueError("forecast_backup_horizon_mismatch")
        if not 3 <= len(entries) <= 16:
            raise ValueError("forecast_required_horizon_missing")
        for i, (date, values) in enumerate(entries):
            if date != (today+timedelta(days=i)).isoformat():
                raise ValueError("forecast_dates_stale_or_incomplete")
            values = [_number(values[0], required=False), _number(values[1], required=False),
                _number(values[2], 0), _number(values[3], 0, 100),
                _number(values[4], 0, required=False), _number(values[5], 0, required=False)]
            rows.append([fetched_at.isoformat(), tz, date, i, *values,
                PROVIDERS[provider][1], lat, lon])
    except (KeyError, TypeError, IndexError, AttributeError):
        raise ValueError("forecast_payload_incomplete") from None
    return rows


class ForecastHealthError(RuntimeError):
    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


def _health_request(payload):
    if not AMADEUS_BACKEND_URL or not TELEMETRY_INGEST_API_KEY:
        raise RuntimeError("forecast_health_not_configured")
    # Queue allowance belongs to transport, not the server's 12-second DB budget.
    # Every retry preserves the logical claim/result; only its expiry changes.
    deadline = time.monotonic() + HEALTH_OPERATION_SECONDS
    for attempt in range(HEALTH_MAX_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 6:
            break
        lifetime = min(HEALTH_REQUEST_SECONDS, remaining - 6)
        request_payload = {**payload, "request_expires_at":
            (datetime.now(timezone.utc) + timedelta(seconds=lifetime)).isoformat()}
        try:
            response = requests.post(AMADEUS_BACKEND_URL+"/api/telemetry/weather/forecast/provider-health",
                json=request_payload, headers={"X-Amadeus-Telemetry-Key": TELEMETRY_INGEST_API_KEY},
                timeout=(3, lifetime + 3))
            result = response.json()
        except (requests.RequestException, ValueError):
            result = None
        else:
            if time.monotonic() >= deadline:
                break
            if (200 <= response.status_code < 300 and isinstance(result, dict)
                    and result.get("success") is True and result.get("provider") == payload["provider"]
                    and result.get("source_id") == PROVIDERS[payload["provider"]][0]):
                return result
            if response.status_code not in {408, 502, 503, 504}:
                # Only expose the one protocol status used for no-ingest recovery.
                status = ("nightly_cycle_ingest_unproven" if isinstance(result, dict)
                    and response.status_code == 400 and result.get("status") == "nightly_cycle_ingest_unproven"
                    else None)
                raise ForecastHealthError("forecast_health_unconfirmed", status=status)
        if attempt + 1 < HEALTH_MAX_ATTEMPTS and deadline - time.monotonic() > 7:
            time.sleep(1)
    raise ForecastHealthError("forecast_health_unavailable")


def _finish_provider(claim, status, *, failure_kind=None, retry_not_before=None, forecast_run_at=None, nightly_cycle=None):
    payload = {"action": "result", **claim, "status": status, "failure_kind": failure_kind,
        "retry_not_before": retry_not_before, "forecast_run_at": forecast_run_at}
    if nightly_cycle is not None:
        payload["nightly_cycle"] = nightly_cycle
    try:
        return _health_request(payload).get("success") is True
    except RuntimeError:
        return False



def provider_configuration():
    order = [name.strip() for name in os.getenv("FORECAST_PROVIDERS", "visual_crossing,weatherapi").split(",")]
    return [{"provider": name, "configured": name != "weatherapi" or bool(
        os.getenv("WEATHERAPI_API_KEY", "").strip())} for name in order if name in PROVIDERS]

def acquire_forecast(lat, lon, tz, days, *, nightly_cycle=None):
    failures = []
    order = [name.strip() for name in os.getenv("FORECAST_PROVIDERS", "visual_crossing,weatherapi").split(",")]
    if not order or len(set(order)) != len(order) or any(name not in PROVIDERS for name in order):
        raise ValueError("forecast_provider_order_invalid")
    fetchers = {"visual_crossing": fetch_visual_crossing_daily,
        "weatherapi": fetch_weatherapi_daily, "open_meteo": fetch_open_meteo_daily}
    for provider in order:
        if provider == "weatherapi" and not os.getenv("WEATHERAPI_API_KEY", "").strip():
            failures.append({"provider": provider, "failure_kind": "not_configured"})
            continue
        attempt = str(uuid4())
        try:
            admission = _health_request({"action": "claim", "provider": provider, "attempt_id": attempt,
                **({"nightly_cycle": nightly_cycle} if nightly_cycle is not None else {})})
            if admission.get("allowed") is not True:
                failures.append({"provider": provider, "failure_kind": "health_hold",
                    "status": admission.get("status")})
                continue
            if (admission.get("attempt_id") != attempt or type(admission.get("generation")) is not int
                    or admission["generation"] < 1):
                raise RuntimeError("forecast_health_claim_invalid")
        except RuntimeError:
            failures.append({"provider": provider, "failure_kind": "health_unavailable"})
            continue
        claim = {"provider": provider, "attempt_id": attempt, "generation": admission["generation"]}
        try:
            data = fetchers[provider](lat=lat, lon=lon, tz=tz, days=days)
            fetched = datetime.now(timezone.utc)
            rows = build_rows(data, lat, lon, tz, provider=provider, fetched_at=fetched)
        except (RuntimeError, ValueError, requests.RequestException) as exc:
            kind = getattr(exc, "failure_kind", "quota" if isinstance(exc, ForecastProviderRateLimited)
                else "invalid_data" if isinstance(exc, ValueError) else "network")
            saved = _finish_provider(claim, "fetch_failed", failure_kind=kind,
                retry_not_before=getattr(exc, "retry_not_before", None), nightly_cycle=nightly_cycle)
            failures.append({"provider": provider, "failure_kind": kind, "health_persisted": saved})
            continue
        source_id, label, attribution = PROVIDERS[provider]
        request = {"provider": provider, "latitude": lat, "longitude": lon,
            "timezone": tz, "days": days if provider == "open_meteo" else 3,
            "start_date": rows[0][2], "end_date": rows[-1][2], "units": "metric",
            "contract": "rootline_forecast_request.v1"}
        provenance = {"provider": provider, "source_id": source_id,
            "fetched_at": fetched.isoformat(), "forecast_run_at": fetched.isoformat(),
            "freshness_basis": "retrieved", "provider_model_updated_at": None,
            "request_sha256": sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
            "coverage_start": rows[0][2], "coverage_end": rows[-1][2], "coverage_days": len(rows),
            "attribution": label, "attribution_url": attribution, "local_observation_credit": False}
        return rows, {"response": data, "provenance": provenance, "health_claim": claim}, failures
    error = ForecastProviderRateLimited if failures and all(
        item["failure_kind"] == "quota" for item in failures) else RuntimeError
    unavailable = error("forecast_all_providers_unavailable")
    unavailable.provider_failures = failures
    raise unavailable


def write_current(ws, rows: list[list]):
    values = [HEADERS] + rows
    ws.clear()
    ws.update(values)


def append_history(ws, rows: list[list]):
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(HEADERS)
    ws.append_rows(rows, value_input_option="RAW")



def _planning_hours(data, selected_date):
    provider = data.get("provenance", {}).get("provider")
    response = data.get("response") or {}
    if provider == "visual_crossing":
        selected = next((d for d in response.get("days", []) if d.get("datetime") == selected_date), {})
        rows = selected.get("hours", [])
        return [{"start_at": selected_date + "T" + h["datetime"] + "+02:00",
            "rain_sum_mm": h.get("precip"), "rain_probability_pct": h.get("precipprob"),
            "wind_max_kmh": h.get("windspeed"), "source": h.get("source"),
            "local_observation_credit": False} for h in rows if h.get("source") == "fcst"]
    if provider == "weatherapi":
        selected = next((d for d in response.get("forecast", {}).get("forecastday", [])
            if d.get("date") == selected_date), {})
        return [{"start_at": h["time"].replace(" ", "T") + ":00+02:00",
            "rain_sum_mm": h.get("precip_mm"), "rain_probability_pct": h.get("chance_of_rain"),
            "wind_max_kmh": h.get("wind_kph"), "source": "fcst",
            "local_observation_credit": False} for h in selected.get("hour", [])]
    return []


def build_backend_payload(rows: list[list], data: dict) -> dict:
    days = []
    for row in rows:
        days.append({
            "forecast_date": row[2],
            "offset_days": row[3],
            "temp_max_c": row[4],
            "temp_min_c": row[5],
            "rain_sum_mm": row[6],
            "rain_probability_max_pct": row[7],
            "wind_max_kmh": row[8],
            "gust_max_kmh": row[9],
            "provenance": data.get("provenance", {}),
            "planning_hours": _planning_hours(data, row[2]),
            **({"provider_daily_chance_of_rain_pct": _number(data["response"]["forecast"][
                "forecastday"][row[3]]["day"].get("daily_chance_of_rain"), 0, 100, required=False)}
                if data.get("provenance", {}).get("provider") == "weatherapi" else {}),
            **({"provider_source": data["response"]["days"][row[3]]["source"],
                "provider_hour_sources": sorted({hour["source"] for hour in data["response"]["days"][row[3]]["hours"]})}
                if data.get("provenance", {}).get("provider") == "visual_crossing" else {}),
        })

    return {
        "source_id": data["provenance"]["source_id"],
        "provider": data["provenance"]["provider"],
        "provider_health_claim": data["health_claim"],
        "provenance": data["provenance"],
        "forecast_run_at": rows[0][0],
        "timezone": rows[0][1] if rows else os.getenv("TIMEZONE", "Africa/Johannesburg"),
        "days": days,
        "raw_payload": {"response": data.get("response"), "provenance": data["provenance"]},
    }


def post_backend_ingest(payload: dict) -> tuple[bool, Optional[str]]:
    if not BACKEND_INGEST_ENABLED:
        return False, None

    url = f"{AMADEUS_BACKEND_URL}/api/telemetry/weather/forecast/ingest"
    headers = {"X-Amadeus-Telemetry-Key": TELEMETRY_INGEST_API_KEY}
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code < 200 or response.status_code >= 300:
        return False, f"backend_http_{response.status_code}"
    try:
        acknowledgement = response.json()
        if acknowledgement.get("success") is not True:
            return False, "backend_ingest_unconfirmed"
        if (acknowledgement.get("source_id") != payload.get("source_id")
                or acknowledgement.get("rows") != len(payload.get("days") or [])):
            return False, "backend_ingest_identity_unconfirmed"
    except (ValueError, AttributeError):
        return False, "backend_response_invalid"
    return True, None


def main(*, nightly=True):
    load_dotenv()
    refresh_configuration()
    require_backend_env()

    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if GOOGLE_SHEETS_ENABLED:
        sheet_id = env_required("GOOGLE_SHEET_ID")
        sa_file = env_required("GOOGLE_SERVICE_ACCOUNT_FILE")

    lat = float(env_required("LAT"))
    lon = float(env_required("LON"))
    tz = env_required("TIMEZONE")
    days = min(16, max(3, int(os.getenv("DAYS", "3"))))

    cycle = None
    if nightly:
        try:
            admission = _health_request({"action": "nightly_claim", "provider": "visual_crossing",
                "attempt_id": str(uuid4())})
            if admission.get("success") is not True or admission.get("allowed") is not True:
                if (admission.get("success") is True and admission.get("allowed") is False
                        and admission.get("status") in {"nightly_not_due", "nightly_cycle_already_claimed"}):
                    print(json.dumps({"success": True, "status": admission["status"], "provider_calls": 0}))
                    return
                raise RuntimeError("nightly_cycle_admission_invalid")
            cycle = admission.get("cycle")
            if not isinstance(cycle, dict) or not all(isinstance(cycle.get(k), str) and cycle[k]
                    for k in ("attempt_id", "cycle_date", "operating_date")):
                raise RuntimeError("nightly_cycle_claim_unproven")
        except RuntimeError as exc:
            print(json.dumps({"success": False, "status": "nightly_cycle_admission_unavailable",
                "provider_calls": 0, "existing_forecast_preserved": True, "error": str(exc)}))
            raise SystemExit(2) from None
    try:
        rows, data, failures = acquire_forecast(lat, lon, tz, days,
            **({"nightly_cycle": {k: cycle[k] for k in ("attempt_id", "cycle_date", "operating_date")}} if cycle else {}))
        if cycle is not None:
            data["provenance"]["nightly_cycle"] = {key: cycle[key] for key in (
                "attempt_id", "cycle_date", "operating_date")}

    except (RuntimeError, ValueError) as exc:
        if cycle is not None:
            _health_request({"action": "nightly_result", "provider": "visual_crossing",
                "attempt_id": cycle["attempt_id"], "status": "failed"})
        print(json.dumps({
            "success": False,
            "status": "provider_rate_limited" if isinstance(exc, ForecastProviderRateLimited) else "forecast_unavailable",
            "provider_failures": getattr(exc, "provider_failures", []),
            "provider_configuration": provider_configuration(),
            "existing_forecast_preserved": True,
            "error": str(exc),
        }))
        raise SystemExit(2)

    google_sheets_written = False
    google_sheets_error = None
    if GOOGLE_SHEETS_ENABLED:
        try:
            gc = get_gspread_client(sa_file)
            sh = gc.open_by_key(sheet_id)
            ws_current = get_or_create_ws(sh, CURRENT_TAB)
            ws_history = get_or_create_ws(sh, HISTORY_TAB)
            write_current(ws_current, rows)
            append_history(ws_history, rows)
            google_sheets_written = True
        except Exception as exc:
            google_sheets_error = type(exc).__name__

    backend_ingest_success = False
    backend_ingest_error = None
    try:
        backend_ingest_success, backend_ingest_error = post_backend_ingest(build_backend_payload(rows, data))
    except Exception as exc:
        backend_ingest_error = type(exc).__name__

    required_ingest = BACKEND_INGEST_ENABLED and backend_ingest_success
    # An unacknowledged nightly ingest may have committed. Do not write a
    # contradictory provider failure before reconciling its durable receipt.
    health_saved = False
    if required_ingest or cycle is None:
        health_saved = _finish_provider(data["health_claim"], "ingested" if required_ingest else "ingest_failed",
            failure_kind=None if required_ingest else "backend_ingest", forecast_run_at=rows[0][0],
            nightly_cycle={k: cycle[k] for k in ("attempt_id", "cycle_date", "operating_date")} if cycle else None)
    success = required_ingest and health_saved and all(item.get("health_persisted", True) for item in failures)
    nightly_result_confirmed = False
    if cycle is not None:
        try:
            recorded = _health_request({"action": "nightly_result", "provider": "visual_crossing",
                "attempt_id": cycle["attempt_id"], "status": "ingested",
                "source_id": data["provenance"]["source_id"], "forecast_run_at": rows[0][0]})
            success = nightly_result_confirmed = recorded.get("success") is True
            health_saved = success
        except RuntimeError as exc:
            success = False
            if getattr(exc, "status", None) == "nightly_cycle_ingest_unproven":
                try:
                    recorded = _health_request({"action": "nightly_result", "provider": "visual_crossing",
                        "attempt_id": cycle["attempt_id"], "status": "failed"})
                    nightly_result_confirmed = recorded.get("success") is True
                except RuntimeError:
                    pass
            # A lost response is unknown, not permission to close a committed
            # ingest as failed. Leave the original identity pending for recovery.
    print(json.dumps({
        "success": success,
        "provider": data["provenance"]["provider"],
        "source_id": data["provenance"]["source_id"],
        "provider_failures": failures,
        "provider_configuration": provider_configuration(),
        "provider_health_recorded": health_saved,
        "backend_ingest_enabled": BACKEND_INGEST_ENABLED,
        "backend_ingest_success": backend_ingest_success,
        "backend_ingest_error": backend_ingest_error,
        "nightly_result_confirmed": nightly_result_confirmed,
        "google_sheets_enabled": GOOGLE_SHEETS_ENABLED,
        "google_sheets_written": google_sheets_written,
        "google_sheets_error": google_sheets_error,
        "forecast_days": len(rows),
        "run_timestamp": rows[0][0] if rows else None,
    }))
    if not success:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
