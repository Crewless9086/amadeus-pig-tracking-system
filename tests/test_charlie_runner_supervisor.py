import tempfile
import unittest
import sys
import subprocess
import json
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import charlie_runner_supervisor as supervisor


class CharlieRunnerSupervisorTests(unittest.TestCase):
    def test_instance_lock_refuses_live_owner_and_recovers_stale_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "supervisor.lock"
            path.write_text('{"pid": 123}', encoding="utf-8")
            lock = supervisor.SupervisorInstanceLock(path)
            with patch.object(supervisor, "_pid_alive", return_value=True):
                self.assertEqual(lock.acquire(), (False, 123))
            with patch.object(supervisor, "_pid_alive", return_value=False), patch.object(supervisor.os, "getpid", return_value=456):
                self.assertEqual(lock.acquire(), (True, 456))
                lock.release()
            self.assertFalse(path.exists())

    def test_transaction_pool_url_is_used_for_supabase_session_pool(self):
        original = "postgresql://user:pass@aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require"
        converted = supervisor._transaction_pool_url(original)
        self.assertIn(":6543/postgres", converted)
        self.assertNotIn(":5432/postgres", converted)
        self.assertEqual(supervisor._transaction_pool_url("postgresql://localhost:5432/app"), "postgresql://localhost:5432/app")

    def test_pid_alive_uses_exact_tasklist_pid_on_windows(self):
        runner = Mock(return_value=Mock(returncode=0, stdout='"python.exe","1234","Console","1","20,000 K"\n'))
        with patch("scripts.charlie_runner_supervisor.os.name", "nt"):
            self.assertTrue(supervisor._pid_alive(1234, runner=runner))
            self.assertFalse(supervisor._pid_alive(123, runner=runner))
    @patch("scripts.charlie_runner_supervisor.subprocess.run", side_effect=subprocess.TimeoutExpired(["powershell"], 5))
    def test_windows_process_command_timeout_is_nonfatal(self, _run):
        self.assertEqual(supervisor._windows_process_command(1234), "")
    def test_shared_repo_venv_is_used_from_runner_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree = root / ".charlie_runner" / "clean"
            python = root / "venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            self.assertEqual(supervisor._python_executable(worktree), str(python))
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
        child_env = popen.call_args_list[0].kwargs["env"]
        self.assertIn("GIT_CONFIG_GLOBAL", child_env)

    def test_stop_marker_prevents_child_start(self):
        popen = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / "stop"
            stop.write_text("stop", encoding="utf-8")
            with patch.object(supervisor, "RUNNER_DIR", Path(tmp)), patch.object(supervisor, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"), patch.object(supervisor, "STOP_PATH", stop):
                result = supervisor.supervise_runner(popen_factory=popen, sleep_fn=lambda _delay: None, max_cycles=1)

        popen.assert_not_called()
        self.assertEqual(result["cycles"], 0)

    def test_identical_infrastructure_failure_enters_hold_after_three_exits(self):
        children = [Mock(pid=101), Mock(pid=102), Mock(pid=103)]
        for child in children:
            child.wait.return_value = 1
        notifier = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            heartbeat = root / "runner.json"
            heartbeat.write_text('{"last_result_status":"base_branch_checkout_failed"}', encoding="utf-8")
            with patch.object(supervisor, "RUNNER_DIR", root), patch.object(supervisor, "SUPERVISOR_PATH", root / "supervisor.json"), patch.object(supervisor, "RUNNER_HEARTBEAT_PATH", heartbeat), patch.object(supervisor, "STOP_PATH", root / "stop"):
                result = supervisor.supervise_runner(
                    popen_factory=Mock(side_effect=children),
                    sleep_fn=lambda _delay: None,
                    max_cycles=10,
                    notifier=notifier,
                )
            state = json.loads((root / "supervisor.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "infrastructure_hold")
        self.assertEqual(result["restart_count"], 3)
        self.assertEqual(state["identical_failure_count"], 3)
        notifier.assert_called_once()


if __name__ == "__main__":
    unittest.main()
