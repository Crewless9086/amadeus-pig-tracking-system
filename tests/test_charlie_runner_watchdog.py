import tempfile
import unittest
from pathlib import Path

from scripts.charlie_runner_watchdog import watchdog_tick


class CharlieRunnerWatchdogTests(unittest.TestCase):
    def test_windows_task_trusts_only_designated_runner_worktree(self):
        script = (Path(__file__).parents[1] / "scripts" / "charlie_runner_watchdog_task.ps1").read_text(encoding="utf-8")
        self.assertIn("safe.directory $repo", script)
        self.assertNotIn("safe.directory '*'", script)
        self.assertIn("charlie_runner_watchdog.py", script)

    def test_healthy_runner_is_not_started_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            result = watchdog_tick(
                status_reader=lambda: {"active": True, "status": "runner_active"},
                starter=lambda: calls.append(True),
                state_path=Path(tmp) / "watchdog.json",
            )
        self.assertEqual(result["status"], "runner_healthy")
        self.assertFalse(result["started"])
        self.assertEqual(calls, [])

    def test_stopped_runner_starts_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_stale_or_stopped", "orphan_processes": []},
                starter=lambda: ({"status": "runner_started"}, 200),
                state_path=Path(tmp) / "watchdog.json",
            )
        self.assertEqual(result["status"], "runner_started")
        self.assertTrue(result["started"])

    def test_tick_writes_process_scoped_safe_git_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "watchdog.json"
            watchdog_tick(
                status_reader=lambda: {"active": True, "status": "runner_active"},
                starter=lambda: self.fail("must not start"),
                state_path=state,
            )
            config = state.with_name("task-gitconfig")
            self.assertTrue(config.exists())
            self.assertIn("safe", config.read_text(encoding="utf-8"))

    def test_orphan_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_orphaned", "orphan_processes": [{"pid": 5}]},
                starter=lambda: self.fail("must not start over an orphan"),
                state_path=Path(tmp) / "watchdog.json",
            )
        self.assertEqual(result["status"], "orphan_requires_cleanup")


if __name__ == "__main__":
    unittest.main()
