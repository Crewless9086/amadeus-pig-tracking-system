import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.database_service import (
    ORDER_SCHEMA_TABLES,
    SALES_PAYMENT_DATE_MIGRATION_ID,
    SALES_TRANSACTION_SCHEMA_TABLES,
    TELEMETRY_POWER_SCHEMA_MIGRATION_ID,
    TELEMETRY_POWER_SCHEMA_TABLES,
    TELEMETRY_WEATHER_SCHEMA_MIGRATION_ID,
    TELEMETRY_WEATHER_SCHEMA_TABLES,
    check_database_foundation,
    check_database_health,
    check_order_schema,
    check_sales_transaction_payment_date_schema,
    check_sales_transaction_schema,
    check_telemetry_power_schema,
    check_telemetry_weather_schema,
)


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
        self.assertIn('@app.route("/health/database/order-schema")', app_source)
        self.assertIn("check_order_schema()", app_source)
        self.assertIn('@app.route("/health/database/sales-transaction-schema")', app_source)
        self.assertIn("check_sales_transaction_schema()", app_source)
        self.assertIn('@app.route("/health/database/sales-payment-date-schema")', app_source)
        self.assertIn("check_sales_transaction_payment_date_schema()", app_source)
        self.assertIn('@app.route("/health/database/telemetry-power-schema")', app_source)
        self.assertIn("check_telemetry_power_schema()", app_source)

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

    def test_order_schema_health_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            body, status_code = check_order_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertFalse(body["configured"])
        self.assertEqual(body["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(body))

    def test_sales_transaction_schema_health_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            body, status_code = check_sales_transaction_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertFalse(body["configured"])
        self.assertEqual(body["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(body))

    def test_sales_payment_date_schema_health_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            body, status_code = check_sales_transaction_payment_date_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertFalse(body["configured"])
        self.assertEqual(body["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(body))

    def test_telemetry_power_schema_health_reports_missing_database_url_without_importing_driver(self):
        with patch.dict(os.environ, {}, clear=True):
            body, status_code = check_telemetry_power_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertFalse(body["configured"])
        self.assertEqual(body["status"], "not_configured")
        self.assertNotIn("DATABASE_URL=", str(body))

    def test_order_sales_migration_creates_only_expected_boundary_tables(self):
        migration = Path("supabase/migrations/202605210002_create_order_sales_tables.sql").read_text(
            encoding="utf-8"
        )
        migration_lower = migration.lower()

        for table in ORDER_SCHEMA_TABLES:
            with self.subTest(table=table):
                self.assertIn(f"create table if not exists public.{table}", migration_lower)

        self.assertIn("202605210002_create_order_sales_tables", migration)
        self.assertIn("app_private.migration_log", migration)
        self.assertIn("customer_phone_raw", migration)
        self.assertIn("customer_phone_normalized", migration)
        self.assertIn("effective_from", migration)
        self.assertIn("future_storage_bucket", migration)
        self.assertIn("future_storage_path", migration)

        forbidden_tables = [
            "create table if not exists public.pigs",
            "create table if not exists public.pig_master",
            "create table if not exists public.weight_log",
            "create table if not exists public.mating_log",
            "create table if not exists public.litters",
            "create table if not exists public.weather",
            "create table if not exists public.sunsynk",
            "create table if not exists public.irrigation",
            "create table if not exists public.sales_availability",
        ]
        for forbidden in forbidden_tables:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, migration_lower)

    def test_sales_transaction_migration_creates_only_expected_extension_tables(self):
        migration = Path("supabase/migrations/202605210003_create_sales_transaction_tables.sql").read_text(
            encoding="utf-8"
        )
        migration_lower = migration.lower()

        for table in SALES_TRANSACTION_SCHEMA_TABLES:
            with self.subTest(table=table):
                self.assertIn(f"create table if not exists public.{table}", migration_lower)

        self.assertIn("202605210003_create_sales_transaction_tables", migration)
        self.assertIn("app_private.migration_log", migration)
        self.assertIn("sale_stream in ('Livestock', 'Slaughter', 'Meat')", migration)
        self.assertIn("buyer_phone_raw", migration)
        self.assertIn("buyer_phone_normalized", migration)
        self.assertIn("linked_order_id text references public.orders(order_id)", migration)
        self.assertIn("order_line_id text references public.order_lines(order_line_id)", migration)
        self.assertIn("deductions_total numeric(12, 2)", migration)

        forbidden_tables = [
            "create table if not exists public.pigs",
            "create table if not exists public.pig_master",
            "create table if not exists public.weight_log",
            "create table if not exists public.mating_log",
            "create table if not exists public.litters",
            "create table if not exists public.weather",
            "create table if not exists public.sunsynk",
            "create table if not exists public.irrigation",
            "create table if not exists public.customers",
            "create table if not exists public.sales_transaction_deductions",
        ]
        for forbidden in forbidden_tables:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, migration_lower)

    def test_sales_payment_date_migration_adds_only_payment_date_column(self):
        migration = Path("supabase/migrations/202605210004_add_sales_transaction_payment_date.sql").read_text(
            encoding="utf-8"
        )
        migration_lower = migration.lower()

        self.assertIn("alter table public.sales_transactions", migration_lower)
        self.assertIn("add column if not exists payment_date date", migration_lower)
        self.assertIn(SALES_PAYMENT_DATE_MIGRATION_ID, migration)
        self.assertIn("app_private.migration_log", migration)
        self.assertNotIn("create table", migration_lower)
        self.assertNotIn("drop table", migration_lower)
        self.assertNotIn("delete from", migration_lower)

    def test_telemetry_power_migration_creates_only_expected_first_tables(self):
        migration = Path(
            "supabase/migrations/202605210005_create_telemetry_power_tables.sql"
        ).read_text(encoding="utf-8")
        migration_lower = migration.lower()

        for table in TELEMETRY_POWER_SCHEMA_TABLES:
            with self.subTest(table=table):
                self.assertIn(f"create table if not exists public.{table}", migration_lower)

        self.assertIn(TELEMETRY_POWER_SCHEMA_MIGRATION_ID, migration)
        self.assertIn("app_private.migration_log", migration)
        self.assertIn("sunsynk-main-inverter", migration)
        self.assertIn("stale_after_minutes", migration)
        self.assertIn("battery_soc_pct", migration)
        self.assertIn("summary_headline", migration)

        forbidden_tables = [
            "create table if not exists public.weather_latest_state",
            "create table if not exists public.weather_forecast_snapshots",
            "create table if not exists public.irrigation_actions",
            "create table if not exists public.power_hourly_rollups",
            "create table if not exists public.power_daily_rollups",
            "create table if not exists public.power_monthly_rollups",
            "create table if not exists public.power_yearly_rollups",
        ]
        for forbidden in forbidden_tables:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, migration_lower)

    def test_telemetry_weather_migration_creates_only_expected_weather_tables(self):
        migration = Path(
            "supabase/migrations/202605220001_create_telemetry_weather_tables.sql"
        ).read_text(encoding="utf-8")
        migration_lower = migration.lower()

        for table in TELEMETRY_WEATHER_SCHEMA_TABLES:
            with self.subTest(table=table):
                self.assertIn(f"create table if not exists public.{table}", migration_lower)

        self.assertIn(TELEMETRY_WEATHER_SCHEMA_MIGRATION_ID, migration)
        self.assertIn("weather-station-main", migration)
        self.assertIn("open-meteo-forecast-main", migration)
        self.assertIn("app_private.migration_log", migration)

        forbidden = [
            "create table if not exists public.irrigation_actions",
            "create table if not exists public.weather_daily_rollups",
            "drop table",
            "delete from",
        ]
        for text in forbidden:
            with self.subTest(forbidden=text):
                self.assertNotIn(text, migration_lower)

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_order_schema_health_does_not_return_connection_string_on_failure(self):
        with patch.dict("sys.modules", {"psycopg": Mock(connect=Mock(side_effect=RuntimeError("boom")))}):
            body, status_code = check_order_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "order_schema_check_failed")
        self.assertNotIn("secret", str(body))
        self.assertNotIn("example", str(body))

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_sales_transaction_schema_health_does_not_return_connection_string_on_failure(self):
        with patch.dict("sys.modules", {"psycopg": Mock(connect=Mock(side_effect=RuntimeError("boom")))}):
            body, status_code = check_sales_transaction_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "sales_transaction_schema_check_failed")
        self.assertNotIn("secret", str(body))
        self.assertNotIn("example", str(body))

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_sales_payment_date_schema_health_does_not_return_connection_string_on_failure(self):
        with patch.dict("sys.modules", {"psycopg": Mock(connect=Mock(side_effect=RuntimeError("boom")))}):
            body, status_code = check_sales_transaction_payment_date_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "sales_payment_date_schema_check_failed")
        self.assertNotIn("secret", str(body))
        self.assertNotIn("example", str(body))

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret@example/db"}, clear=True)
    def test_telemetry_power_schema_health_does_not_return_connection_string_on_failure(self):
        with patch.dict("sys.modules", {"psycopg": Mock(connect=Mock(side_effect=RuntimeError("boom")))}):
            body, status_code = check_telemetry_power_schema()

        self.assertEqual(status_code, 503)
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "telemetry_power_schema_check_failed")
        self.assertNotIn("secret", str(body))
        self.assertNotIn("example", str(body))


if __name__ == "__main__":
    unittest.main()
