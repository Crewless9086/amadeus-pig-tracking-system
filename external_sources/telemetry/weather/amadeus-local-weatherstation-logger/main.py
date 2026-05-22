import json
import os
from datetime import datetime
from typing import Any, Optional

import gspread
import pytz
import requests
from dateutil import parser as dateparser
from google.oauth2.service_account import Credentials


SHEET_TAB_NAME = "Current_Conditions"

TIMEZONE = os.getenv("TIMEZONE", "Africa/Johannesburg")
TZ = pytz.timezone(TIMEZONE)

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

WCOM_API_KEY = os.getenv("WCOM_API_KEY", "").strip()
STATION_ID = os.getenv("STATION_ID", "").strip()
DUP_WINDOW_SEC = int(os.getenv("DUP_WINDOW_SEC", "60"))

AMADEUS_BACKEND_URL = os.getenv("AMADEUS_BACKEND_URL", "").strip().rstrip("/")
TELEMETRY_INGEST_API_KEY = os.getenv("TELEMETRY_INGEST_API_KEY", "").strip()
BACKEND_INGEST_ENABLED = os.getenv("BACKEND_INGEST_ENABLED", "false").strip().lower() == "true"
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "true").strip().lower() == "true"

URL_CURRENT = (
    "https://api.weather.com/v2/pws/observations/current"
    "?stationId={stationId}&format=json&units=m&apiKey={apiKey}"
)


def require_env() -> None:
    missing = []
    for key, value in [
        ("WCOM_API_KEY", WCOM_API_KEY),
        ("STATION_ID", STATION_ID),
    ]:
        if not value:
            missing.append(key)

    if GOOGLE_SHEETS_ENABLED:
        for key, value in [
            ("GOOGLE_SHEET_ID", GOOGLE_SHEET_ID),
            ("GOOGLE_SERVICE_ACCOUNT_FILE", GOOGLE_SERVICE_ACCOUNT_FILE),
        ]:
            if not value:
                missing.append(key)

    if BACKEND_INGEST_ENABLED:
        for key, value in [
            ("AMADEUS_BACKEND_URL", AMADEUS_BACKEND_URL),
            ("TELEMETRY_INGEST_API_KEY", TELEMETRY_INGEST_API_KEY),
        ]:
            if not value:
                missing.append(key)

    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


def parse_any_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return TZ.localize(value)
        return value.astimezone(TZ)

    try:
        parsed = dateparser.parse(str(value))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return TZ.localize(parsed)
        return parsed.astimezone(TZ)
    except Exception:
        return None


def get_gspread_client() -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_FILE)
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def safe_fetch_current() -> tuple[int, Optional[dict], str]:
    url = URL_CURRENT.format(stationId=STATION_ID, apiKey=WCOM_API_KEY)
    response = requests.get(url, timeout=30)
    text = response.text or ""

    if response.status_code == 204:
        return response.status_code, None, text
    if response.status_code != 200:
        return response.status_code, None, text
    if not text.strip():
        return response.status_code, None, text

    try:
        return response.status_code, response.json(), text
    except Exception:
        return response.status_code, None, text


def get_last_logged_timestamp(ws) -> Optional[datetime]:
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return None

    for row in reversed(values[1:]):
        if row and len(row) > 0 and str(row[0]).strip():
            return parse_any_datetime(row[0])

    return None


def post_backend_ingest(payload: dict) -> tuple[bool, Optional[str]]:
    if not BACKEND_INGEST_ENABLED:
        return False, None

    url = f"{AMADEUS_BACKEND_URL}/api/telemetry/weather/ingest"
    headers = {"X-Amadeus-Telemetry-Key": TELEMETRY_INGEST_API_KEY}
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code < 200 or response.status_code >= 300:
        return False, f"{response.status_code}: {response.text[:300]}"
    return True, None


def main():
    require_env()

    status, data, raw = safe_fetch_current()

    if status == 204:
        print(json.dumps({"success": True, "skipped": "204_no_new_station_data"}))
        return

    if status != 200 or not data:
        print(json.dumps({"success": False, "api_status": status, "api_error": raw[:300]}))
        return

    observations = data.get("observations") or []
    if not observations:
        print(json.dumps({"success": True, "skipped": "no_observations"}))
        return

    obs = observations[0]
    obs_time_local = obs.get("obsTimeLocal")
    if not obs_time_local:
        print(json.dumps({"success": False, "error": "missing_obsTimeLocal"}))
        return

    obs_ts = parse_any_datetime(obs_time_local)
    if not obs_ts:
        print(json.dumps({"success": False, "error": f"could_not_parse_obsTimeLocal={obs_time_local}"}))
        return

    obs_ts = obs_ts.astimezone(TZ)
    timestamp_str = obs_ts.strftime("%Y-%m-%d %H:%M:%S")
    metric = obs.get("metric") or {}

    row = [
        timestamp_str,
        metric.get("temp", ""),
        metric.get("windSpeed", ""),
        metric.get("windGust", ""),
        obs.get("winddir", ""),
        metric.get("precipRate", ""),
        metric.get("precipTotal", ""),
        metric.get("pressure", ""),
        obs.get("humidity", ""),
    ]

    weather_payload = {
        "reading_at": obs_ts.isoformat(),
        "temperature_c": metric.get("temp"),
        "wind_speed_kmh": metric.get("windSpeed"),
        "wind_gust_kmh": metric.get("windGust"),
        "wind_direction_deg": obs.get("winddir"),
        "rain_rate_mm_h": metric.get("precipRate"),
        "rain_today_mm": metric.get("precipTotal"),
        "pressure_hpa": metric.get("pressure"),
        "humidity_pct": obs.get("humidity"),
        "raw_payload": obs,
    }

    google_sheets_written = False
    google_sheets_skipped = None
    google_sheets_error = None
    if GOOGLE_SHEETS_ENABLED:
        try:
            gc = get_gspread_client()
            sh = gc.open_by_key(GOOGLE_SHEET_ID)
            ws = sh.worksheet(SHEET_TAB_NAME)
            last_ts = get_last_logged_timestamp(ws)

            if last_ts is not None and obs_ts <= last_ts:
                google_sheets_skipped = (
                    f"api timestamp not newer: api={timestamp_str}, "
                    f"last={last_ts.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            elif last_ts is not None and (obs_ts - last_ts).total_seconds() < DUP_WINDOW_SEC:
                google_sheets_skipped = f"duplicate within {DUP_WINDOW_SEC}s: api={timestamp_str}"
            else:
                ws.append_row(row, value_input_option="USER_ENTERED")
                google_sheets_written = True
        except Exception as exc:
            google_sheets_error = str(exc)

    backend_ingest_success = False
    backend_ingest_error = None
    try:
        backend_ingest_success, backend_ingest_error = post_backend_ingest(weather_payload)
    except Exception as exc:
        backend_ingest_error = str(exc)

    print(json.dumps({
        "success": google_sheets_written or backend_ingest_success,
        "backend_ingest_enabled": BACKEND_INGEST_ENABLED,
        "backend_ingest_success": backend_ingest_success,
        "backend_ingest_error": backend_ingest_error,
        "google_sheets_enabled": GOOGLE_SHEETS_ENABLED,
        "google_sheets_written": google_sheets_written,
        "google_sheets_skipped": google_sheets_skipped,
        "google_sheets_error": google_sheets_error,
        "timestamp_za": obs_ts.isoformat(),
    }))


if __name__ == "__main__":
    main()
