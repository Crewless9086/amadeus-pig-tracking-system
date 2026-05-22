import json
import os
from datetime import datetime
from typing import Optional

import gspread
import pytz
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


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
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=str(rows), cols=str(cols))


def fetch_open_meteo_daily(lat: float, lon: float, tz: str, days: int) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "forecast_days": days,
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "precipitation_probability_max",
        ]),
    }
    response = requests.get(OPEN_METEO_URL, params=params, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Open-Meteo non-200: {response.status_code} {response.text[:200]}")
    return response.json()


def build_rows(data: dict, lat: float, lon: float, tz: str) -> list[list]:
    daily = data.get("daily") or {}
    times = daily.get("time") or []

    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    rain = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []
    gust = daily.get("wind_gusts_10m_max") or []
    rain_prob = daily.get("precipitation_probability_max") or []

    tzinfo = pytz.timezone(tz)
    run_ts = datetime.now(tzinfo).strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for idx, day in enumerate(times):
        rows.append([
            run_ts,
            tz,
            day,
            idx,
            tmax[idx] if idx < len(tmax) else "",
            tmin[idx] if idx < len(tmin) else "",
            rain[idx] if idx < len(rain) else "",
            rain_prob[idx] if idx < len(rain_prob) else "",
            wind[idx] if idx < len(wind) else "",
            gust[idx] if idx < len(gust) else "",
            "Open-Meteo",
            lat,
            lon,
        ])
    return rows


def write_current(ws, rows: list[list]):
    values = [HEADERS] + rows
    ws.clear()
    ws.update(values)


def append_history(ws, rows: list[list]):
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(HEADERS)
    ws.append_rows(rows, value_input_option="RAW")


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
        })

    return {
        "forecast_run_at": rows[0][0] if rows else datetime.now().isoformat(),
        "timezone": rows[0][1] if rows else os.getenv("TIMEZONE", "Africa/Johannesburg"),
        "days": days,
        "raw_payload": data,
    }


def post_backend_ingest(payload: dict) -> tuple[bool, Optional[str]]:
    if not BACKEND_INGEST_ENABLED:
        return False, None

    url = f"{AMADEUS_BACKEND_URL}/api/telemetry/weather/forecast/ingest"
    headers = {"X-Amadeus-Telemetry-Key": TELEMETRY_INGEST_API_KEY}
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code < 200 or response.status_code >= 300:
        return False, f"{response.status_code}: {response.text[:300]}"
    return True, None


def main():
    load_dotenv()
    require_backend_env()

    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if GOOGLE_SHEETS_ENABLED:
        sheet_id = env_required("GOOGLE_SHEET_ID")
        sa_file = env_required("GOOGLE_SERVICE_ACCOUNT_FILE")

    lat = float(env_required("LAT"))
    lon = float(env_required("LON"))
    tz = env_required("TIMEZONE")
    days = int(os.getenv("DAYS", "10"))

    data = fetch_open_meteo_daily(lat=lat, lon=lon, tz=tz, days=days)
    rows = build_rows(data=data, lat=lat, lon=lon, tz=tz)

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
            google_sheets_error = str(exc)

    backend_ingest_success = False
    backend_ingest_error = None
    try:
        backend_ingest_success, backend_ingest_error = post_backend_ingest(build_backend_payload(rows, data))
    except Exception as exc:
        backend_ingest_error = str(exc)

    print(json.dumps({
        "success": google_sheets_written or backend_ingest_success,
        "backend_ingest_enabled": BACKEND_INGEST_ENABLED,
        "backend_ingest_success": backend_ingest_success,
        "backend_ingest_error": backend_ingest_error,
        "google_sheets_enabled": GOOGLE_SHEETS_ENABLED,
        "google_sheets_written": google_sheets_written,
        "google_sheets_error": google_sheets_error,
        "forecast_days": len(rows),
        "run_timestamp": rows[0][0] if rows else None,
    }))


if __name__ == "__main__":
    main()
