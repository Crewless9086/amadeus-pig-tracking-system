import argparse
import sys
from pathlib import Path

import gspread

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.orders.order_intake_service import (  # noqa: E402
    ORDER_INTAKE_STATE_SHEET,
    ORDER_INTAKE_ITEMS_SHEET,
    INTAKE_STATE_HEADERS,
    INTAKE_ITEM_HEADERS,
)
from services.google_sheets_service import _get_spreadsheet  # noqa: E402


def _get_or_create_worksheet(spreadsheet, sheet_name, headers, apply_changes):
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        print(f"FOUND {sheet_name}")
        return worksheet
    except gspread.WorksheetNotFound:
        print(f"MISSING {sheet_name}")
        if not apply_changes:
            print(f"WOULD_CREATE {sheet_name} headers={headers}")
            return None

    worksheet = spreadsheet.add_worksheet(
        title=sheet_name,
        rows=200,
        cols=max(26, len(headers)),
    )
    worksheet.update("A1", [headers], value_input_option="USER_ENTERED")
    print(f"CREATED {sheet_name} with headers")
    return worksheet


def _ensure_headers(worksheet, sheet_name, headers, apply_changes):
    if worksheet is None:
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


def main():
    parser = argparse.ArgumentParser(
        description="Create Phase 5.5 order intake state sheets."
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

    state_ws = _get_or_create_worksheet(
        spreadsheet,
        ORDER_INTAKE_STATE_SHEET,
        INTAKE_STATE_HEADERS,
        args.apply,
    )
    items_ws = _get_or_create_worksheet(
        spreadsheet,
        ORDER_INTAKE_ITEMS_SHEET,
        INTAKE_ITEM_HEADERS,
        args.apply,
    )

    _ensure_headers(state_ws, ORDER_INTAKE_STATE_SHEET, INTAKE_STATE_HEADERS, args.apply)
    _ensure_headers(items_ws, ORDER_INTAKE_ITEMS_SHEET, INTAKE_ITEM_HEADERS, args.apply)

    print("DONE")


if __name__ == "__main__":
    main()
