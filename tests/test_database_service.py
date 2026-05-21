import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.database_service import check_database_foundation, check_database_health


class DatabaseServiceHealthTests(unittest.TestCase):
    def test_database_health_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            body, status_code = check_database_health()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertFalse(body["configured"])
        self.assertEqual(body["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(body))

    def test_database_health_endpoint_is_registered(self):
        app_source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn('@app.route("/health/database")', app_source)
        self.assertIn("check_database_health()", app_source)
        self.assertIn('@app.route("/health/database/foundation")', app_source)
        self.assertIn("check_database_foundation()", app_source)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_database_health_does_not_return_connection_string_on_failure(self):
        with patch.dict("sys.modules", {"psycopg": Mock(connect=Mock(side_effect=RuntimeError("boom")))}):
            body, status_code = check_database_health()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "connection_failed")
        self.assertNotIn("secret", str(body))
        self.assertNotIn("example", str(body))

    def test_foundation_health_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            body, status_code = check_database_foundation()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertFalse(body["configured"])
        self.assertEqual(body["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(body))

    def test_foundation_migration_is_internal_only(self):
        migration = Path("supabase/migrations/202605210001_foundation_migration_log.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("create schema if not exists app_private", migration)
        self.assertIn("app_private.migration_log", migration)
        self.assertIn("202605210001_foundation_migration_log", migration)

        forbidden_business_tables = [
            "create table orders",
            "create table order_lines",
            "create table pigs",
            "create table weights",
            "create table matings",
            "create table litters",
        ]
        for forbidden in forbidden_business_tables:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, migration.lower())

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_foundation_health_does_not_return_connection_string_on_failure(self):
        with patch.dict("sys.modules", {"psycopg": Mock(connect=Mock(side_effect=RuntimeError("boom")))}):
            body, status_code = check_database_foundation()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "foundation_check_failed")
        self.assertNotIn("secret", str(body))
        self.assertNotIn("example", str(body))


if __name__ == "__main__":
    unittest.main()
