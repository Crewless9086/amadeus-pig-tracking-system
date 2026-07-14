import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import charlie_runner_supervisor as supervisor


class CharlieRunnerSupervisorTests(unittest.TestCase):
    def test_repo_root_is_available_for_supervisor_module_imports(self):
        self.assertIn(str(supervisor.REPO_ROOT), sys.path)

    @patch.object(supervisor, "_process_identity")
    @patch.object(supervisor, "_pid_alive")
    @patch.object(supervisor.subprocess, "run")
    def test_stale_owned_child_is_recovered_only_when_prior_supervisor_is_dead(self, run, pid_alive, process_identity):
        pid_alive.side_effect = lambda pid: int(pid) == 222
        process_identity.return_value = {
            "created": "123", "executable": "python.exe", "command": "python runner.py"
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(supervisor, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"):
            supervisor.SUPERVISOR_PATH.write_text(
                '{"pid": 111, "child_pid": 222, "child_identity": '
                '{"created": "123", "executable": "python.exe", "command": "python runner.py"}}',
                encoding="utf-8",
            )
            self.assertTrue(supervisor._recover_stale_owned_child())
        run.assert_called_once()

    @patch.object(supervisor, "_process_identity")
    @patch.object(supervisor, "_pid_alive")
    @patch.object(supervisor.subprocess, "run")
    def test_reused_child_pid_is_not_terminated(self, run, pid_alive, process_identity):
        pid_alive.side_effect = lambda pid: int(pid) == 222
        process_identity.return_value = {
            "created": "new-process", "executable": "unrelated.exe", "command": "unrelated.exe"
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(supervisor, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"):
            supervisor.SUPERVISOR_PATH.write_text(
                '{"pid": 111, "child_pid": 222, "child_identity": '
                '{"created": "old-process", "executable": "python.exe", "command": "python runner.py"}}',
                encoding="utf-8",
            )
            self.assertFalse(supervisor._recover_stale_owned_child())
        run.assert_not_called()

    def test_unexpected_exit_restarts_with_backoff(self):
        children = [Mock(pid=101), Mock(pid=102)]
        children[0].wait.return_value = 1
        children[1].wait.return_value = 0
        popen = Mock(side_effect=children)
        sleeps = []

        with tempfile.TemporaryDirectory() as tmp, patch.object(supervisor, "RUNNER_DIR", Path(tmp)), patch.object(supervisor, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"), patch.object(supervisor, "STOP_PATH", Path(tmp) / "stop"):
            result = supervisor.supervise_runner(popen_factory=popen, sleep_fn=sleeps.append, max_cycles=2)

        self.assertEqual(popen.call_count, 2)
        self.assertEqual(sleeps, [5])
        self.assertEqual(result["restart_count"], 2)

    def test_stop_marker_prevents_child_start(self):
        popen = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / "stop"
            stop.write_text("stop", encoding="utf-8")
            with patch.object(supervisor, "RUNNER_DIR", Path(tmp)), patch.object(supervisor, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"), patch.object(supervisor, "STOP_PATH", stop):
                result = supervisor.supervise_runner(popen_factory=popen, sleep_fn=lambda _delay: None, max_cycles=1)

        popen.assert_not_called()
        self.assertEqual(result["cycles"], 0)


if __name__ == "__main__":
    unittest.main()
