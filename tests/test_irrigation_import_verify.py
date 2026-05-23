import unittest
from unittest.mock import MagicMock, Mock

from scripts.irrigation_import_verify import verify_irrigation_import


class IrrigationImportVerifyTests(unittest.TestCase):
    def test_verify_requires_database_url(self):
        report, exit_code = verify_irrigation_import("")

        self.assertEqual(exit_code, 2)
        self.assertFalse(report["success"])
        self.assertEqual(report["status"], "not_configured")

    def test_verify_reports_counts_and_latest_state_strategy(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (2,),
            (2,),
            (73,),
            (73,),
            (146,),
            (146,),
            (1,),
            (1,),
            (77,),
            (77,),
        ]
        cursor.fetchall.return_value = [
            ("IRRSTATE-MAIN", "IDLE", "C12345", "C12345", "IMPORT-20260523-IRRIGATION-SHEET-V1")
        ]
        connection = MagicMock()
        connect = Mock()
        connect.return_value = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        report, exit_code = verify_irrigation_import(
            "postgresql://example",
            connect_factory=connect,
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(report["success"])
        self.assertEqual(report["table_counts"]["irrigation_zones"], 2)
        self.assertEqual(report["import_batch_counts"]["irrigation_events"], 77)
        self.assertTrue(report["state_strategy_verified"])


if __name__ == "__main__":
    unittest.main()
