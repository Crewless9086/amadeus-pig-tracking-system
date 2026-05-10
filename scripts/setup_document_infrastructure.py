import argparse
import sys
from datetime import datetime
from pathlib import Path

import gspread

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.google_sheets_service import _get_spreadsheet  # noqa: E402


SYSTEM_SETTINGS_SHEET = "SYSTEM_SETTINGS"
ORDER_DOCUMENTS_SHEET = "ORDER_DOCUMENTS"

SYSTEM_SETTINGS_HEADERS = [
    "Setting_Key",
    "Setting_Value",
    "Description",
    "Updated_At",
    "Updated_By",
]

ORDER_DOCUMENTS_HEADERS = [
    "Document_ID",
    "Order_ID",
    "Document_Type",
    "Document_Ref",
    "Payment_Ref",
    "Version",
    "Document_Status",
    "Payment_Method",
    "VAT_Rate",
    "Subtotal_Ex_VAT",
    "VAT_Amount",
    "Total",
    "Valid_Until",
    "Google_Drive_File_ID",
    "Google_Drive_URL",
    "File_Name",
    "Created_At",
    "Created_By",
    "Sent_At",
    "Sent_By",
    "Notes",
]

SYSTEM_SETTINGS_SEED = [
    ("quote_valid_days", "3", "Number of days a generated quote remains valid."),
    ("vat_rate", "0.15", "VAT rate used for EFT quote/invoice calculations."),
    ("business_name", "AMADEUS FARM", "Business name shown on quote/invoice PDFs."),
    ("business_address_line_1", "Swartklip Road", "Business address line 1."),
    ("business_address_line_2", "Riversdale, 6670", "Business address line 2."),
    ("business_address_line_3", "Western Cape", "Business address line 3."),
    ("business_phone", "084-567-9327", "Business phone shown on documents."),
    ("business_email", "amadeusfarm572@gmail.com", "Business email shown on documents."),
    ("business_vat_number", "4510286224", "Business VAT number shown on documents."),
    ("bank_name", "First National Bank (FNB)", "Bank name shown on documents."),
    ("bank_account_name", "Charl Nieuwendyk", "Bank account holder shown on documents."),
    ("bank_account_type", "Cheque Account", "Bank account type shown on documents."),
    ("bank_account_number", "62315222711", "Bank account number shown on documents."),
    ("bank_branch_code", "250655", "Bank branch code shown on documents."),
    ("quote_drive_folder_id", "1r7oqIDMwZZi5T7BxC31y7UGNzn8Ud9ys", "Google Drive Shared Drive folder ID for quote PDFs."),
    ("invoice_drive_folder_id", "1_kbfX69s6yeb-Zfdcpu5jse8H30HvLGr", "Google Drive Shared Drive folder ID for invoice PDFs."),
    ("document_logo_path", "static/document-assets/amadeus-logo.png", "Runtime logo asset path for PDF generation."),
    ("draft_quote_note", "Draft quote - subject to availability and approval", "Visible note on Draft quotes."),
]


def _get_or_create_worksheet(spreadsheet, sheet_name, headers, apply_changes):
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        print(f"FOUND {sheet_name}")
        return worksheet, False
    except gspread.WorksheetNotFound:
        print(f"MISSING {sheet_name}")
        if not apply_changes:
            return None, True

    worksheet = spreadsheet.add_worksheet(
        title=sheet_name,
        rows=max(100, len(headers) + 10),
        cols=max(26, len(headers)),
    )
    worksheet.update("A1", [headers], value_input_option="USER_ENTERED")
    print(f"CREATED {sheet_name} with headers")
    return worksheet, True


def _ensure_headers(worksheet, sheet_name, headers, apply_changes):
    if worksheet is None:
        print(f"WOULD_CREATE {sheet_name} headers={headers}")
        return

    values = worksheet.get_all_values()
    current_headers = values[0] if values else []

    if current_headers == headers:
        print(f"HEADERS_OK {sheet_name}")
        return

    if not current_headers:
        if apply_changes:
            worksheet.update("A1", [headers], value_input_option="USER_ENTERED")
            print(f"HEADERS_CREATED {sheet_name}")
        else:
            print(f"WOULD_CREATE_HEADERS {sheet_name} headers={headers}")
        return

    raise ValueError(
        f"{sheet_name} exists with unexpected headers. "
        f"Expected {headers}; found {current_headers}."
    )


def _seed_system_settings(worksheet, apply_changes):
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    actor = "Document setup utility"

    if worksheet is None:
        print(f"WOULD_SEED {SYSTEM_SETTINGS_SHEET} rows={len(SYSTEM_SETTINGS_SEED)}")
        return

    rows = worksheet.get_all_records()
    existing_keys = {str(row.get("Setting_Key", "")).strip() for row in rows}
    missing = [row for row in SYSTEM_SETTINGS_SEED if row[0] not in existing_keys]

    if not missing:
        print(f"SETTINGS_OK {SYSTEM_SETTINGS_SHEET}")
        return

    seed_rows = [[key, value, description, timestamp, actor] for key, value, description in missing]

    if apply_changes:
        worksheet.append_rows(seed_rows, value_input_option="USER_ENTERED")
        print(f"SEEDED {SYSTEM_SETTINGS_SHEET} rows={len(seed_rows)}")
    else:
        print(f"WOULD_SEED {SYSTEM_SETTINGS_SHEET} rows={len(seed_rows)} keys={[row[0] for row in missing]}")


def main():
    parser = argparse.ArgumentParser(
        description="Create/seed Phase 2.2 document infrastructure sheets."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to live Google Sheets. Without this flag, the script is dry-run only.",
    )
    args = parser.parse_args()

    spreadsheet = _get_spreadsheet()
    mode = "APPLY" if args.apply else "DRY_RUN"
    print(f"MODE {mode}")

    settings_ws, _ = _get_or_create_worksheet(
        spreadsheet,
        SYSTEM_SETTINGS_SHEET,
        SYSTEM_SETTINGS_HEADERS,
        args.apply,
    )
    documents_ws, _ = _get_or_create_worksheet(
        spreadsheet,
        ORDER_DOCUMENTS_SHEET,
        ORDER_DOCUMENTS_HEADERS,
        args.apply,
    )

    _ensure_headers(settings_ws, SYSTEM_SETTINGS_SHEET, SYSTEM_SETTINGS_HEADERS, args.apply)
    _ensure_headers(documents_ws, ORDER_DOCUMENTS_SHEET, ORDER_DOCUMENTS_HEADERS, args.apply)
    _seed_system_settings(settings_ws, args.apply)

    print("DONE")


if __name__ == "__main__":
    main()
