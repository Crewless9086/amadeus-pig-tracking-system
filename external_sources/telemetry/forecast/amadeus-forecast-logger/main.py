import os
import json
import requests
import gspread
import pytz
from datetime import datetime
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


def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


import json
from google.oauth2.service_account import Credentials
import gspread
import os

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
    r = requests.get(OPEN_METEO_URL, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Open-Meteo non-200: {r.status_code} {r.text[:200]}")
    return r.json()


def build_rows(data: dict, lat: float, lon: float, tz: str) -> list[list]:
    daily = data.get("daily") or {}
    times = daily.get("time") or []

    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    rain = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []
    gust = daily.get("wind_gusts_10m_max") or []
    rain_prob = daily.get("precipitation_probability_max") or []

    # Run timestamp in local timezone
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
    # Overwrite the whole sheet with headers + rows
    values = [HEADERS] + rows
    ws.clear()
    ws.update(values)


def append_history(ws, rows: list[list]):
    # Ensure header exists if sheet is empty
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(HEADERS)
    # Append rows
    ws.append_rows(rows, value_input_option="RAW")


def main():
    load_dotenv()  # local only (Render env vars also work)

    sheet_id = env_required("GOOGLE_SHEET_ID")
    sa_file = env_required("GOOGLE_SERVICE_ACCOUNT_FILE")

    lat = float(env_required("LAT"))
    lon = float(env_required("LON"))
    tz = env_required("TIMEZONE")
    days = int(os.getenv("DAYS", "10"))

    # Fetch forecast
    data = fetch_open_meteo_daily(lat=lat, lon=lon, tz=tz, days=days)
    rows = build_rows(data=data, lat=lat, lon=lon, tz=tz)

    # Write to Google Sheets
    gc = get_gspread_client(sa_file)
    sh = gc.open_by_key(sheet_id)

    ws_current = get_or_create_ws(sh, CURRENT_TAB)
    ws_history = get_or_create_ws(sh, HISTORY_TAB)

    write_current(ws_current, rows)
    append_history(ws_history, rows)

    print(f"✅ Logged {len(rows)} forecast days to {CURRENT_TAB} and appended to {HISTORY_TAB}.")


if __name__ == "__main__":
    main()
