import unittest
from threading import BoundedSemaphore
from unittest.mock import patch

from modules.oom_sakkie import sales_campaign_store
from modules.sales import butcher_truth_board
from modules.sales import meat_fulfillment
from modules.sales import meat_match_engine

from modules.sales.sam_meat_database_deadline import (
    SamMeatDatabaseDeadline,
    SamMeatDatabaseCapacityExceeded,
    SamMeatDatabaseDeadlineExceeded,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class SamMeatDatabaseDeadlineTests(unittest.TestCase):
    def test_connection_options_bound_every_database_wait(self):
        clock = FakeClock()
        calls = []

        def connect(database_url, **kwargs):
            calls.append((database_url, kwargs))
            return _Connection(_Cursor())

        deadline = SamMeatDatabaseDeadline(total_seconds=4.5, clock=clock)
        protected = deadline.connect("postgresql://private", connect_callable=connect)

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1]["autocommit"])
        self.assertLessEqual(calls[0][1]["connect_timeout"], 3)
        self.assertEqual(calls[0][1]["tcp_user_timeout"], 4000)
        options = calls[0][1]["options"]
        self.assertIn("statement_timeout=2400", options)
        self.assertIn("lock_timeout=500", options)
        self.assertIn("idle_in_transaction_session_timeout=2500", options)
        self.assertIn("default_transaction_read_only=on", options)
        protected.close()

    def test_remaining_absolute_budget_reduces_nested_connection_limits(self):
        clock = FakeClock()
        calls = []
        deadline = SamMeatDatabaseDeadline(total_seconds=4.5, clock=clock)
        first = deadline.connect("db", connect_callable=lambda *_args, **kwargs: calls.append(kwargs) or _Connection(_Cursor()))
        first.close()
        clock.value = 3.2
        second = deadline.connect("db", connect_callable=lambda *_args, **kwargs: calls.append(kwargs) or _Connection(_Cursor()))
        second.close()
        self.assertEqual(calls[1]["connect_timeout"], 1)
        self.assertIn("statement_timeout=199", calls[1]["options"])

    def test_exhausted_deadline_refuses_another_connection(self):
        clock = FakeClock()
        deadline = SamMeatDatabaseDeadline(total_seconds=4.5, clock=clock)
        clock.value = 4.4
        with self.assertRaises(SamMeatDatabaseDeadlineExceeded):
            deadline.connect("db", connect_callable=lambda *_args, **_kwargs: object())

    def test_factory_reuses_one_absolute_deadline_without_pooling(self):
        clock = FakeClock()
        calls = []
        factory = SamMeatDatabaseDeadline(total_seconds=4.5, clock=clock).connection_factory(
            connect_callable=lambda *_args, **kwargs: calls.append(kwargs) or _Connection(_Cursor())
        )
        first = factory("db")
        clock.value = 1.0
        second = factory("db")
        self.assertIsNot(first, second)
        self.assertEqual(len(calls), 2)
        first.close()
        second.close()

    def test_capacity_is_fail_fast_and_released_after_close(self):
        capacity = BoundedSemaphore(1)
        deadline = SamMeatDatabaseDeadline(capacity=capacity)
        first = deadline.connect("db", connect_callable=lambda *_args, **_kwargs: _Connection(_Cursor()))
        with self.assertRaises(SamMeatDatabaseCapacityExceeded):
            deadline.connect("db", connect_callable=lambda *_args, **_kwargs: _Connection(_Cursor()))
        first.close()
        second = deadline.connect("db", connect_callable=lambda *_args, **_kwargs: _Connection(_Cursor()))
        second.close()

    def test_capacity_released_after_connect_failure(self):
        capacity = BoundedSemaphore(1)
        deadline = SamMeatDatabaseDeadline(capacity=capacity)
        with self.assertRaises(RuntimeError):
            deadline.connect("db", connect_callable=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("failed")))
        replacement = deadline.connect("db", connect_callable=lambda *_args, **_kwargs: _Connection(_Cursor()))
        replacement.close()

    def test_option_string_cannot_include_database_or_customer_input(self):
        calls = []
        protected = SamMeatDatabaseDeadline().connect("postgresql://host/db?customer=SET statement_timeout=0", connect_callable=lambda database_url, **kwargs: calls.append((database_url, kwargs)) or _Connection(_Cursor()))
        protected.close()
        database_url, kwargs = calls[0]
        self.assertIn("customer=SET statement_timeout=0", database_url)
        self.assertNotIn("customer", kwargs["options"])
        self.assertEqual(kwargs["options"].count("-c "), 4)


    def test_price_reader_closes_cursor_and_connection_on_success_and_error(self):
        for error in (None, RuntimeError("database unavailable")):
            with self.subTest(error=error.__class__.__name__ if error else "success"):
                cursor = _Cursor(error)
                connection = _Connection(cursor)
                deadline = _DeadlineStub(connection=connection)
                result, status = sales_campaign_store.list_meat_price_book_entries(
                    database_url="postgresql://private", database_deadline=deadline,
                )
                self.assertEqual(deadline.calls, 1)
                self.assertTrue(cursor.exited)
                self.assertTrue(connection.exited)
                self.assertEqual(status, 503 if error else 200)
                if error:
                    self.assertEqual(result["status"], "meat_price_book_read_failed")
                    self.assertNotIn("database unavailable", str(result))

    def test_deadline_error_is_sanitized_without_retry(self):
        deadline = _DeadlineStub(error=SamMeatDatabaseDeadlineExceeded("private detail"))
        result, status = sales_campaign_store.list_meat_price_book_entries(
            database_url="postgresql://private", database_deadline=deadline,
        )
        self.assertEqual(deadline.calls, 1)
        self.assertEqual(status, 503)
        self.assertEqual(result["error_type"], "SamMeatDatabaseDeadlineExceeded")
        self.assertNotIn("private detail", str(result))

    def test_butcher_nested_readers_share_one_absolute_deadline(self):
        deadline = object()
        with (
            patch.object(butcher_truth_board, "get_sales_lead_meat_match", return_value=({"meat_match": {}}, 200)) as match,
            patch.object(butcher_truth_board, "get_meat_ops_status", return_value=({"reservations": [], "assembly": {}}, 200)) as ops,
            patch.object(butcher_truth_board, "get_meat_reconciliation_status", return_value=({"reconciliation": {}}, 200)) as reconciliation,
            patch.object(butcher_truth_board, "list_meat_processing_batches", return_value=({"batches": []}, 200)) as batches,
        ):
            result, status = butcher_truth_board.get_butcher_truth_board(
                "LEAD-1", database_url="postgresql://private", database_deadline=deadline,
            )
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        for mocked in (match, ops, reconciliation, batches):
            self.assertIs(mocked.call_args.kwargs["database_deadline"], deadline)


    def test_match_timeout_is_unavailable_not_known_zero(self):
        deadline = _DeadlineStub(error=SamMeatDatabaseDeadlineExceeded("private detail"))
        result = meat_match_engine._fetch_active_carcass_reservations(
            ["PIG-1"], database_url="postgresql://private", database_deadline=deadline,
        )
        self.assertIsNone(result)
        self.assertEqual(deadline.calls, 1)

    def test_fulfilment_does_not_present_partial_contract_as_complete(self):
        deadline = _DeadlineStub()
        with (
            patch.object(meat_fulfillment, "get_meat_ops_status", return_value=({"success": True}, 200)),
            patch.object(meat_fulfillment, "get_sales_lead_preorder_contract", return_value=({"success": False, "status": "deadline"}, 503)),
        ):
            result, status = meat_fulfillment.get_meat_fulfillment_timeline(
                "LEAD-1", database_url="postgresql://private", database_deadline=deadline,
            )
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "deadline")
        self.assertEqual(deadline.calls, 0)

class _Cursor:
    def __init__(self, error=None):
        self.error = error
        self.exited = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.exited = True

    def execute(self, *_args, **_kwargs):
        if self.error:
            raise self.error

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.exited = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.exited = True

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


class _DeadlineStub:
    def __init__(self, connection=None, error=None):
        self.connection = connection
        self.error = error
        self.calls = 0

    def connect(self, *_args, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.connection

if __name__ == "__main__":
    unittest.main()
