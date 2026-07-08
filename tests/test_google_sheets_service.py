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

    def test_service_account_credentials_can_use_json_env(self):
        info = {
            "type": "service_account",
            "project_id": "amadeus-test",
            "private_key_id": "key",
            "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
            "client_email": "test@example.com",
            "client_id": "123",
            "token_uri": "https://oauth2.googleapis.com/token",
        }

        with patch.object(google_sheets_service, "GOOGLE_SERVICE_ACCOUNT_JSON", google_sheets_service.json.dumps(info)), \
             patch.object(google_sheets_service, "GOOGLE_SERVICE_ACCOUNT_JSON_B64", ""), \
             patch.object(google_sheets_service.Credentials, "from_service_account_info", return_value=Mock()) as from_info, \
             patch.object(google_sheets_service.Credentials, "from_service_account_file") as from_file:
            google_sheets_service.service_account_credentials(scopes=["scope"])

        from_info.assert_called_once_with(info, scopes=["scope"])
        from_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
