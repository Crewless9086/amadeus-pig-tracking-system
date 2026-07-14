import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import charlie_runner_supervisor as supervisor


class CharlieRunnerSupervisorTests(unittest.TestCase):
    @patch.object(supervisor, "_pid_alive")
    @patch.object(supervisor.subprocess, "run")
    def test_stale_owned_child_is_recovered_only_when_prior_supervisor_is_dead(self, run, pid_alive):
        pid_alive.side_effect = lambda pid: int(pid) == 222
        with tempfile.TemporaryDirectory() as tmp, patch.object(supervisor, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"):
            supervisor.SUPERVISOR_PATH.write_text('{"pid": 111, "child_pid": 222}', encoding="utf-8")
            self.assertTrue(supervisor._recover_stale_owned_child())
        run.assert_called_once()

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
