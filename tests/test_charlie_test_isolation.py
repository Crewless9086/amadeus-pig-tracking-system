import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.charlie import (
    _guard_direct_charlie_test_execution,
    process_ownership,
    runner_control,
    runtime_path_root,
    validated_test_control_root,
)
from modules.charlie import execution_bridge
from scripts import charlie_telegram_relay_watchdog
from tests import isolated_control_root


class CharlieTestIsolationTests(unittest.TestCase):
    def test_runner_paths_resolve_only_inside_disposable_control_root(self):
        root = isolated_control_root().resolve()
        shared = runner_control._shared_repository_root().resolve()
        self.assertEqual(Path(os.environ[runner_control.TEST_CONTROL_ROOT_ENV]).resolve(), root)
        self.assertNotEqual(root, shared)
        self.assertNotIn(shared, root.parents)
        paths = (
            runner_control.CONTROL_ROOT,
            runner_control.RUNNER_DIR,
            runner_control.HEARTBEAT_PATH,
            runner_control.LOG_PATH,
            runner_control.SUPERVISOR_PATH,
            runner_control.SUPERVISOR_STOP_PATH,
            runner_control.EMERGENCY_CLEANUP_DISABLED_PATH,
            runner_control.EMERGENCY_CLEANUP_REFUSAL_LOG,
            execution_bridge.RUNTIME_ROOT,
            execution_bridge.EXECUTION_DIR,
            execution_bridge.REVIEW_MEDIA_DIR,
            execution_bridge.LEGACY_REVIEW_MEDIA_DIR,
            execution_bridge.MISSION_MEDIA_DIR,
            charlie_telegram_relay_watchdog.RUNTIME_ROOT,
            charlie_telegram_relay_watchdog.STATE_PATH,
            charlie_telegram_relay_watchdog.STDOUT_PATH,
            charlie_telegram_relay_watchdog.STDERR_PATH,
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(Path(path).resolve().is_relative_to(root))

    def test_test_isolation_cannot_enable_process_termination(self):
        values = {
            process_ownership.TEST_ISOLATION_ENV: "1",
            process_ownership.TERMINATION_ENABLE_ENV: process_ownership.TERMINATION_ENABLE_VALUE,
        }
        self.assertFalse(process_ownership.process_termination_enabled(values))

    def test_owner_checkout_is_rejected_as_test_control_root(self):
        values = {
            runner_control.TEST_ISOLATION_ENV: "1",
            runner_control.TEST_CONTROL_ROOT_ENV: str(runner_control._shared_repository_root()),
        }
        with self.assertRaises(RuntimeError):
            runner_control._control_root(environ=values)
        with self.assertRaises(RuntimeError):
            validated_test_control_root(runner_control.REPO_ROOT, values)

    def test_missing_test_control_root_is_rejected(self):
        values = {runner_control.TEST_ISOLATION_ENV: "1"}
        with self.assertRaises(RuntimeError):
            runner_control._control_root(environ=values)
        with self.assertRaises(RuntimeError):
            validated_test_control_root(runner_control.REPO_ROOT, values)

    def test_path_beneath_owner_checkout_is_rejected_as_test_control_root(self):
        values = {
            runner_control.TEST_ISOLATION_ENV: "1",
            runner_control.TEST_CONTROL_ROOT_ENV: str(
                runner_control._shared_repository_root() / "test-control"
            ),
        }
        with self.assertRaises(RuntimeError):
            runner_control._control_root(environ=values)
        with self.assertRaises(RuntimeError):
            validated_test_control_root(runner_control.REPO_ROOT, values)

    def test_production_runtime_path_is_unchanged_without_test_isolation(self):
        default = runner_control.REPO_ROOT / "runtime-default"
        self.assertEqual(runtime_path_root(default, environ={}), default)

    def test_direct_charlie_test_execution_requires_explicit_safe_isolation(self):
        direct_path = runner_control.REPO_ROOT / "tests" / "test_charlie_example.py"
        with patch.object(sys, "argv", [str(direct_path)]), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                _guard_direct_charlie_test_execution()

    def test_direct_charlie_test_execution_rejects_owner_roots(self):
        direct_path = runner_control.REPO_ROOT / "tests" / "test_charlie_example.py"
        shared = runner_control._shared_repository_root()
        for unsafe_root in (shared, shared / "nested-test-control"):
            with self.subTest(unsafe_root=unsafe_root), patch.object(
                sys, "argv", [str(direct_path)]
            ), patch.dict(
                os.environ,
                {
                    runner_control.TEST_ISOLATION_ENV: "1",
                    runner_control.TEST_CONTROL_ROOT_ENV: str(unsafe_root),
                },
                clear=True,
            ):
                with self.assertRaises(RuntimeError):
                    _guard_direct_charlie_test_execution()

    def test_direct_charlie_test_execution_clears_process_opt_ins(self):
        direct_path = runner_control.REPO_ROOT / "tests" / "test_charlie_example.py"
        values = {
            runner_control.TEST_ISOLATION_ENV: "1",
            runner_control.TEST_CONTROL_ROOT_ENV: str(isolated_control_root()),
            "CHARLIE_PROCESS_TERMINATION_ENABLED": process_ownership.TERMINATION_ENABLE_VALUE,
            "CHARLIE_SUBPROCESS_TESTS_ENABLED": "1",
        }
        with patch.object(sys, "argv", [str(direct_path)]), patch.dict(os.environ, values, clear=True):
            _guard_direct_charlie_test_execution()
            self.assertNotIn("CHARLIE_PROCESS_TERMINATION_ENABLED", os.environ)
            self.assertNotIn("CHARLIE_SUBPROCESS_TESTS_ENABLED", os.environ)

    def test_live_termination_and_subprocess_flags_are_absent(self):
        self.assertNotIn("CHARLIE_PROCESS_TERMINATION_ENABLED", os.environ)
        self.assertNotIn("CHARLIE_SUBPROCESS_TESTS_ENABLED", os.environ)


if __name__ == "__main__":
    unittest.main()
