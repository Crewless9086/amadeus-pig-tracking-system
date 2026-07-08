import base64
import json
import os
import threading
import time
import gspread
from gspread.exceptions import APIError, WorksheetNotFound
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Render / production env vars already in use
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON_B64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "AMADEUS PIG TRACKING SYSTEM").strip()
SHEETS_RETRY_DELAYS = (2, 5)

_CACHE_LOCK = threading.RLock()
_CLIENT = None
_SPREADSHEET = None
_SPREADSHEETS_BY_NAME = {}
_WORKSHEETS = {}
_WORKSHEETS_BY_SPREADSHEET = {}


def _get_client():
    global _CLIENT

    with _CACHE_LOCK:
        if _CLIENT is not None:
            return _CLIENT

        creds = service_account_credentials(scopes=SCOPES)
        _CLIENT = gspread.authorize(creds)
        return _CLIENT


def service_account_credentials(scopes=None):
    scopes = scopes or SCOPES
    info = _service_account_info_from_env()
    if info:
        return Credentials.from_service_account_info(info, scopes=scopes)
    return Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=scopes,
    )


def _service_account_info_from_env():
    raw_json = GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw_json and GOOGLE_SERVICE_ACCOUNT_JSON_B64:
        raw_json = base64.b64decode(GOOGLE_SERVICE_ACCOUNT_JSON_B64).decode("utf-8")
    if not raw_json:
        return {}
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must contain a JSON object.")
    return parsed


def _reset_cached_spreadsheet():
    global _SPREADSHEET

    with _CACHE_LOCK:
        _SPREADSHEET = None
        _SPREADSHEETS_BY_NAME.clear()
        _WORKSHEETS.clear()
        _WORKSHEETS_BY_SPREADSHEET.clear()


def _is_quota_error(exc):
    text = str(exc).lower()
    return "429" in text or "quota exceeded" in text


def _run_with_quota_retry(operation):
    last_exc = None

    for attempt, delay in enumerate((0, *SHEETS_RETRY_DELAYS)):
        if delay:
            time.sleep(delay)

        try:
            return operation()
        except APIError as exc:
            last_exc = exc
            if not _is_quota_error(exc) or attempt >= len(SHEETS_RETRY_DELAYS):
                raise
            _reset_cached_spreadsheet()

    raise last_exc


def _get_spreadsheet():
    global _SPREADSHEET

    with _CACHE_LOCK:
        if _SPREADSHEET is not None:
            return _SPREADSHEET

    client = _get_client()
    spreadsheet = _run_with_quota_retry(lambda: client.open(GOOGLE_SHEET_NAME))

    with _CACHE_LOCK:
        _SPREADSHEET = spreadsheet
        return _SPREADSHEET


def _get_spreadsheet_by_name(spreadsheet_name: str):
    spreadsheet_name = str(spreadsheet_name or "").strip()
    if not spreadsheet_name:
        raise ValueError("Spreadsheet name is required.")

    if spreadsheet_name == GOOGLE_SHEET_NAME:
        return _get_spreadsheet()

    with _CACHE_LOCK:
        spreadsheet = _SPREADSHEETS_BY_NAME.get(spreadsheet_name)
        if spreadsheet is not None:
            return spreadsheet

    client = _get_client()
    spreadsheet = _run_with_quota_retry(lambda: client.open(spreadsheet_name))

    with _CACHE_LOCK:
        _SPREADSHEETS_BY_NAME[spreadsheet_name] = spreadsheet
        return spreadsheet


def get_worksheet(sheet_name: str):
    sheet_name = str(sheet_name or "").strip()
    if not sheet_name:
        raise ValueError("Sheet name is required.")

    with _CACHE_LOCK:
        worksheet = _WORKSHEETS.get(sheet_name)
        if worksheet is not None:
            return worksheet

    spreadsheet = _get_spreadsheet()
    worksheet = _run_with_quota_retry(lambda: spreadsheet.worksheet(sheet_name))

    with _CACHE_LOCK:
        _WORKSHEETS[sheet_name] = worksheet
        return worksheet


def get_worksheet_from_spreadsheet(spreadsheet_name: str, sheet_name: str):
    spreadsheet_name = str(spreadsheet_name or "").strip()
    sheet_name = str(sheet_name or "").strip()
    if not spreadsheet_name:
        raise ValueError("Spreadsheet name is required.")
    if not sheet_name:
        raise ValueError("Sheet name is required.")

    cache_key = (spreadsheet_name, sheet_name)
    with _CACHE_LOCK:
        worksheet = _WORKSHEETS_BY_SPREADSHEET.get(cache_key)
        if worksheet is not None:
            return worksheet

    spreadsheet = _get_spreadsheet_by_name(spreadsheet_name)
    worksheet = _run_with_quota_retry(lambda: spreadsheet.worksheet(sheet_name))

    with _CACHE_LOCK:
        _WORKSHEETS_BY_SPREADSHEET[cache_key] = worksheet
        return worksheet


def get_all_records(sheet_name: str):
    worksheet = get_worksheet(sheet_name)
    return _run_with_quota_retry(lambda: worksheet.get_all_records())


def get_all_records_from_spreadsheet(spreadsheet_name: str, sheet_name: str):
    worksheet = get_worksheet_from_spreadsheet(spreadsheet_name, sheet_name)
    return _run_with_quota_retry(lambda: worksheet.get_all_records())


def append_row(sheet_name: str, row_values: list):
    worksheet = get_worksheet(sheet_name)
    _run_with_quota_retry(lambda: worksheet.append_row(row_values, value_input_option="USER_ENTERED"))


def ensure_worksheet(sheet_name: str, headers: list, rows: int = 1000, cols: int = 26):
    sheet_name = str(sheet_name or "").strip()
    if not sheet_name:
        raise ValueError("Sheet name is required.")

    try:
        return get_worksheet(sheet_name)
    except WorksheetNotFound:
        spreadsheet = _get_spreadsheet()
        worksheet = _run_with_quota_retry(
            lambda: spreadsheet.add_worksheet(title=sheet_name, rows=rows, cols=cols)
        )
        if headers:
            _run_with_quota_retry(lambda: worksheet.append_row(headers, value_input_option="USER_ENTERED"))
        with _CACHE_LOCK:
            _WORKSHEETS[sheet_name] = worksheet
        return worksheet


def get_all_values(sheet_name: str):
    worksheet = get_worksheet(sheet_name)
    return _run_with_quota_retry(lambda: worksheet.get_all_values())


def update_row_by_first_column_match(sheet_name: str, match_value: str, new_row_values: list):
    worksheet = get_worksheet(sheet_name)
    all_values = _run_with_quota_retry(lambda: worksheet.get_all_values())

    if not all_values or len(all_values) < 2:
        raise ValueError(f"No data rows found in sheet '{sheet_name}'.")

    match_value = str(match_value).strip()

    for row_index, row in enumerate(all_values[1:], start=2):
        first_col = str(row[0]).strip() if row else ""
        if first_col == match_value:
            _run_with_quota_retry(
                lambda: worksheet.update(f"A{row_index}", [new_row_values], value_input_option="USER_ENTERED")
            )
            return row_index

    raise ValueError(f"Match value '{match_value}' not found in first column of '{sheet_name}'.")


def batch_update_rows_by_id(sheet_name: str, updates_map: dict):
    """
    Update multiple rows in a single API call.
    updates_map: {row_id: {field_name: new_value, ...}}
    Matches each row on its first column (the ID column).
    Raises ValueError if any ID is not found.
    Returns the number of rows updated.
    """
    if not updates_map:
        return 0

    worksheet = get_worksheet(sheet_name)
    all_values = _run_with_quota_retry(lambda: worksheet.get_all_values())

    if not all_values or len(all_values) < 2:
        raise ValueError(f"No data rows found in sheet '{sheet_name}'.")

    headers = all_values[0]
    header_map = {h: i for i, h in enumerate(headers)}

    batch_data = []
    found_ids = set()

    for row_index, row in enumerate(all_values[1:], start=2):
        row_id = str(row[0]).strip() if row else ""
        if row_id not in updates_map:
            continue

        field_updates = updates_map[row_id]
        padded_row = list(row) + [""] * (len(headers) - len(row))

        for field_name, field_value in field_updates.items():
            if field_name not in header_map:
                raise ValueError(f"Missing column '{field_name}' in '{sheet_name}'.")
            padded_row[header_map[field_name]] = field_value

        batch_data.append({"range": f"A{row_index}", "values": [padded_row]})
        found_ids.add(row_id)

    missing = set(updates_map.keys()) - found_ids
    if missing:
        raise ValueError(f"IDs not found in '{sheet_name}': {', '.join(sorted(missing))}")

    if batch_data:
        _run_with_quota_retry(lambda: worksheet.batch_update(batch_data, value_input_option="USER_ENTERED"))

    return len(batch_data)
