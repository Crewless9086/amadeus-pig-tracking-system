import gspread
from google.oauth2.service_account import Credentials
from config.app_config import SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_NAME


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client():
    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_spreadsheet():
    client = get_gspread_client()
    return client.open(GOOGLE_SHEET_NAME)


def get_worksheet(sheet_name: str):
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


def get_all_records(sheet_name: str):
    worksheet = get_worksheet(sheet_name)
    return worksheet.get_all_records()


def append_row(sheet_name: str, row_values: list):
    worksheet = get_worksheet(sheet_name)
    worksheet.append_row(row_values, value_input_option="USER_ENTERED")