import unittest
from unittest.mock import Mock, patch

from services import google_sheets_service


class GoogleSheetsServiceCacheTests(unittest.TestCase):
    def setUp(self):
        google_sheets_service._CLIENT = None
        google_sheets_service._SPREADSHEET = None
        google_sheets_service._WORKSHEETS.clear()

    def tearDown(self):
        google_sheets_service._CLIENT = None
        google_sheets_service._SPREADSHEET = None
        google_sheets_service._WORKSHEETS.clear()

    def test_get_worksheet_reuses_client_spreadsheet_and_worksheet(self):
        worksheet = Mock()
        spreadsheet = Mock()
        spreadsheet.worksheet.return_value = worksheet
        client = Mock()
        client.open.return_value = spreadsheet

        with patch.object(google_sheets_service.Credentials, "from_service_account_file", return_value=Mock()) as creds, \
             patch.object(google_sheets_service.gspread, "authorize", return_value=client) as authorize:
            first = google_sheets_service.get_worksheet("ORDER_MASTER")
            second = google_sheets_service.get_worksheet("ORDER_MASTER")

        self.assertIs(first, worksheet)
        self.assertIs(second, worksheet)
        creds.assert_called_once()
        authorize.assert_called_once()
        client.open.assert_called_once_with(google_sheets_service.GOOGLE_SHEET_NAME)
        spreadsheet.worksheet.assert_called_once_with("ORDER_MASTER")

    def test_get_worksheet_requires_sheet_name(self):
        with self.assertRaises(ValueError):
            google_sheets_service.get_worksheet("")


if __name__ == "__main__":
    unittest.main()
