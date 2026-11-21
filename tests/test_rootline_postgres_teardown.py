"""Offline tests for exact fixture-client cleanup; no PostgreSQL connection."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

_spec = importlib.util.spec_from_file_location("fixture_cleanup_under_test",
    Path(__file__).with_name("rootline_postgres_teardown.py"))
_cleanup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cleanup)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []
    def __call__(self):
        return self.now
    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class Observer:
    autocommit = True
    def __init__(self, *snapshots):
        self.snapshots = snapshots
        self.calls = 0
    def execute(self, query):
        assert "pg_stat_activity" in query and "pid<>pg_backend_pid()" in query
        self.rows = self.snapshots[min(self.calls, len(self.snapshots) - 1)]
        self.calls += 1
        return self
    def fetchall(self):
        return self.rows


class FixtureClientCleanupTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.owned = {(11, "unique-owned"): SimpleNamespace(closed=True)}
        self.client = (11, "unique-owned", "client backend", "idle")
    def run_cleanup(self, observer, owned=None):
        return _cleanup.wait_for_closed_fixture_clients(observer,
            self.owned if owned is None else owned, timeout=0.025,
            clock=self.clock, wait=self.clock.wait)
    def test_background_only_needs_no_wait(self):
        observer = Observer([(22, "", "autovacuum worker", None)])
        self.assertEqual(self.run_cleanup(observer), [])
        self.assertEqual(self.clock.waits, [])
    def test_unknown_backend_fails_closed(self):
        observer = Observer([(22, "private-value", "extension worker", None)])
        with self.assertRaisesRegex(AssertionError, "unknown backend type") as error:
            self.run_cleanup(observer)
        self.assertNotIn("private-value", str(error.exception))
        self.assertEqual(self.clock.waits, [])
    def test_foreign_client_fails_immediately(self):
        observer = Observer([(22, "foreign", "client backend", "active")])
        with self.assertRaisesRegex(AssertionError, "unrelated client remains"):
            self.run_cleanup(observer)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(self.clock.waits, [])
    def test_open_owned_fails_even_when_server_list_empty(self):
        self.owned[(11, "unique-owned")].closed = False
        observer = Observer([])
        with self.assertRaisesRegex(AssertionError, "still open"):
            self.run_cleanup(observer)
        self.assertEqual(observer.calls, 0)
    def test_transient_closed_owned_must_reach_zero(self):
        observer = Observer([self.client], [])
        self.assertEqual(self.run_cleanup(observer), [])
        self.assertEqual(observer.calls, 2)
        self.assertEqual(self.clock.waits, [0.01])
    def test_persistent_closed_owned_fails_at_deadline(self):
        observer = Observer([self.client])
        with self.assertRaisesRegex(AssertionError, "not acknowledged"):
            self.run_cleanup(observer)
        self.assertAlmostEqual(sum(self.clock.waits), 0.025)
        self.assertEqual(observer.calls, 4)
    def test_pid_reuse_with_different_name_fails(self):
        observer = Observer([(11, "new-client", "client backend", "idle")])
        with self.assertRaisesRegex(AssertionError, "unrelated client remains"):
            self.run_cleanup(observer)
        self.assertEqual(self.clock.waits, [])
    def test_name_reuse_with_different_pid_fails(self):
        observer = Observer([(12, "unique-owned", "client backend", "idle")])
        with self.assertRaisesRegex(AssertionError, "unrelated client remains"):
            self.run_cleanup(observer)
        self.assertEqual(self.clock.waits, [])
    def test_foreign_arriving_during_acknowledgement_fails(self):
        observer = Observer([self.client], [(22, "foreign", "client backend", "idle")])
        with self.assertRaisesRegex(AssertionError, "unrelated client remains"):
            self.run_cleanup(observer)
        self.assertEqual(observer.calls, 2)
        self.assertEqual(self.clock.waits, [0.01])
    def test_transaction_observer_rejected(self):
        observer = Observer([])
        observer.autocommit = False
        with self.assertRaisesRegex(AssertionError, "autocommit"):
            self.run_cleanup(observer)
        self.assertEqual(observer.calls, 0)
    def test_all_closed_owned_clients_must_disappear(self):
        self.owned[(12, "second-owned")] = SimpleNamespace(closed=True)
        second = (12, "second-owned", "client backend", "idle")
        observer = Observer([self.client, second], [second], [])
        self.assertEqual(self.run_cleanup(observer), [])
        self.assertEqual(observer.calls, 3)
    def test_zero_clients_observed_after_deadline_is_not_success(self):
        observer = Observer([])
        execute = observer.execute
        def late(query):
            self.clock.now = 0.03
            return execute(query)
        observer.execute = late
        with self.assertRaisesRegex(AssertionError, "deadline exceeded"):
            self.run_cleanup(observer)
    def test_replication_and_unknown_server_roles_fail_closed(self):
        for kind in ("logical replication worker", "logical replication launcher", "walreceiver", "startup"):
            with self.subTest(kind=kind):
                observer = Observer([(22, "", kind, "active")])
                with self.assertRaisesRegex(AssertionError, "unknown backend type"):
                    self.run_cleanup(observer)
                self.assertEqual(self.clock.waits, [])

    def test_walsender_is_not_an_ordinary_background_worker(self):
        observer = Observer([(22, "", "walsender", "active")])
        with self.assertRaisesRegex(AssertionError, "unknown backend type"):
            self.run_cleanup(observer)


if __name__ == "__main__":
    unittest.main()
