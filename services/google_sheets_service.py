import os
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Render / production env vars already in use
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "AMADEUS PIG TRACKING SYSTEM").strip()


def _get_client():
    creds = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return gspread.authorize(creds)


def _get_spreadsheet():
    client = _get_client()
    return client.open(GOOGLE_SHEET_NAME)


def get_worksheet(sheet_name: str):
    spreadsheet = _get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


def get_all_records(sheet_name: str):
    worksheet = get_worksheet(sheet_name)
    return worksheet.get_all_records()


def append_row(sheet_name: str, row_values: list):
    worksheet = get_worksheet(sheet_name)
    worksheet.append_row(row_values, value_input_option="USER_ENTERED")


def get_all_values(sheet_name: str):
    worksheet = get_worksheet(sheet_name)
    return worksheet.get_all_values()


def update_row_by_first_column_match(sheet_name: str, match_value: str, new_row_values: list):
    worksheet = get_worksheet(sheet_name)
    all_values = worksheet.get_all_values()

    if not all_values or len(all_values) < 2:
        raise ValueError(f"No data rows found in sheet '{sheet_name}'.")

    match_value = str(match_value).strip()

    for row_index, row in enumerate(all_values[1:], start=2):
        first_col = str(row[0]).strip() if row else ""
        if first_col == match_value:
            worksheet.update(f"A{row_index}", [new_row_values], value_input_option="USER_ENTERED")
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
    all_values = worksheet.get_all_values()

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
        worksheet.batch_update(batch_data, value_input_option="USER_ENTERED")

    return len(batch_data)