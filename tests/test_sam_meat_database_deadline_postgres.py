import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.sales.sam_meat_database_deadline import SamMeatDatabaseDeadline


DATABASE_URL = os.getenv("SAM_MEAT_DEADLINE_POSTGRES_URL", "").strip()


@unittest.skipUnless(DATABASE_URL, "SAM_MEAT_DEADLINE_POSTGRES_URL is required")
class SamMeatDatabaseDeadlinePostgresTests(unittest.TestCase):
    def test_protected_options_apply_and_do_not_leak(self):
        deadline = SamMeatDatabaseDeadline()
        with deadline.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select current_setting('statement_timeout'), current_setting('lock_timeout'), "
                    "current_setting('idle_in_transaction_session_timeout'), "
                    "current_setting('default_transaction_read_only')"
                )
                settings = cursor.fetchone()
            self.assertTrue(connection.autocommit)
        statement_ms = int(settings[0].removesuffix("ms"))
        lock_ms = int(settings[1].removesuffix("ms"))
        idle_ms = int(settings[2].removesuffix("ms"))
        self.assertTrue(2300 <= statement_ms <= 2400)
        self.assertEqual(lock_ms, 500)
        self.assertEqual(idle_ms, statement_ms + 100)
        self.assertEqual(settings[3], "on")
        self.assertTrue(connection.closed)
        with psycopg.connect(DATABASE_URL, autocommit=True) as ordinary:
            with ordinary.cursor() as cursor:
                cursor.execute("select current_setting('default_transaction_read_only')")
                self.assertEqual(cursor.fetchone()[0], "off")

    def test_statement_timeout_is_enforced_and_connection_closes(self):
        started = time.monotonic()
        connection = None
        with self.assertRaises(psycopg.errors.QueryCanceled):
            with SamMeatDatabaseDeadline().connect(DATABASE_URL) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("select pg_sleep(3)")
        self.assertLess(time.monotonic() - started, 4.0)
        self.assertTrue(connection.closed)

    def test_lock_timeout_is_enforced(self):
        table_name = "sam_meat_deadline_lock_gate"
        with psycopg.connect(DATABASE_URL, autocommit=True) as setup:
            with setup.cursor() as cursor:
                cursor.execute(f"create table if not exists {table_name} (id integer primary key)")
        locker = psycopg.connect(DATABASE_URL)
        try:
            with locker.cursor() as cursor:
                cursor.execute(f"lock table {table_name} in access exclusive mode")
            started = time.monotonic()
            with self.assertRaises(psycopg.errors.LockNotAvailable):
                with SamMeatDatabaseDeadline().connect(DATABASE_URL) as protected:
                    with protected.cursor() as cursor:
                        cursor.execute(f"select * from {table_name}")
            self.assertLess(time.monotonic() - started, 1.5)
        finally:
            locker.rollback()
            locker.close()

    def test_read_only_connection_rejects_writes(self):
        with SamMeatDatabaseDeadline().connect(DATABASE_URL) as protected:
            with protected.cursor() as cursor:
                with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                    cursor.execute("create temporary table forbidden_sam_meat_write (id integer)")

    def test_concurrent_deadlines_are_independent(self):
        def timed_query(delay):
            started = time.monotonic()
            with self.assertRaises(psycopg.errors.QueryCanceled):
                with SamMeatDatabaseDeadline().connect(DATABASE_URL) as protected:
                    with protected.cursor() as cursor:
                        cursor.execute("select pg_sleep(%s)", (delay,))
            return time.monotonic() - started

        with ThreadPoolExecutor(max_workers=2) as executor:
            durations = list(executor.map(timed_query, (3, 3)))
        self.assertTrue(all(2.0 <= duration < 4.0 for duration in durations))


if __name__ == "__main__":
    unittest.main()
