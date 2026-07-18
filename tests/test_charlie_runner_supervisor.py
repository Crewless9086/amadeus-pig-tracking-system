import tempfile
import unittest
import sys
import subprocess
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import charlie_runner_supervisor as supervisor
from modules.charlie import runner_control


class CharlieRunnerSupervisorTests(unittest.TestCase):
    def test_runner_child_is_windowless_on_windows(self):
        self.assertEqual(supervisor._windowless_process_kwargs("nt"), {"creationflags": 0x08000000})
        self.assertEqual(supervisor._windowless_process_kwargs("posix"), {"start_new_session": True})

    def test_windows_named_mutex_refuses_second_supervisor(self):
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 123
        kernel32.GetLastError.return_value = 183
        acquired, handle = supervisor._acquire_windows_supervisor_mutex(Path("runner.lock"), kernel32=kernel32)
        self.assertFalse(acquired)
        self.assertIsNone(handle)
        kernel32.CloseHandle.assert_called_once_with(123)

    def test_supervisor_and_runner_publish_one_canonical_control_directory(self):
        self.assertEqual(supervisor.RUNNER_DIR, runner_control.RUNNER_DIR)
        self.assertEqual(supervisor.SUPERVISOR_PATH.parent, runner_control.HEARTBEAT_PATH.parent)

    def test_duplicate_supervisor_does_not_overwrite_live_owner_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor_path = root / "supervisor.json"
            lock_path = root / "supervisor.lock"
            live_state = {"pid": 123, "status": "runner_started", "child_pid": 456}
            supervisor_path.write_text(json.dumps(live_state), encoding="utf-8")
            lock_path.write_text(json.dumps({"pid": 123}), encoding="utf-8")
            with (
                patch.object(supervisor, "SUPERVISOR_PATH", supervisor_path),
                patch.object(supervisor, "LOCK_PATH", lock_path),
                patch.object(supervisor, "SupervisorInstanceLock", return_value=supervisor.SupervisorInstanceLock(lock_path)),
                patch.object(supervisor, "_pid_alive", return_value=True),
            ):
                result = supervisor.main()

            self.assertEqual(result["status"], "duplicate_supervisor_refused")
            self.assertEqual(json.loads(supervisor_path.read_text(encoding="utf-8")), live_state)

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

    def test_repo_local_imports_follow_sys_path_bootstrap(self):
        source = (Path(__file__).parents[1] / "scripts" / "charlie_runner_supervisor.py").read_text(encoding="utf-8")
        self.assertLess(source.index("sys.path.insert"), source.index("from modules.charlie.repository_guard"))

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

    def test_three_identical_unclassified_child_crashes_enter_hold(self):
        children = [Mock(pid=201), Mock(pid=202), Mock(pid=203)]
        for child in children:
            child.wait.return_value = 3221225794
        notifier = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            heartbeat = root / "runner.json"
            heartbeat.write_text('{"last_result_status":"executive_cycle_observed"}', encoding="utf-8")
            with patch.object(supervisor, "RUNNER_DIR", root), patch.object(supervisor, "SUPERVISOR_PATH", root / "supervisor.json"), patch.object(supervisor, "RUNNER_HEARTBEAT_PATH", heartbeat), patch.object(supervisor, "STOP_PATH", root / "stop"):
                result = supervisor.supervise_runner(Mock(side_effect=children), lambda _delay: None, max_cycles=10, notifier=notifier)
        self.assertEqual(result["status"], "infrastructure_hold")
        self.assertIn("child_exit:3221225794", result["failure_status"])
        notifier.assert_called_once()

    @patch("modules.charlie.improvement_analyst.run_operational_analyst", return_value=({"success": True, "status": "analyst_cycle_complete", "lifecycle": {"updated_count": 1}}, 200))
    def test_conveyor_repair_triggers_analyst_validation_cycle(self, analyst):
        result = supervisor._run_analyst_repair_validation()
        self.assertTrue(result["success"])
        self.assertEqual(result["lifecycle"]["updated_count"], 1)
        analyst.assert_called_once_with(trigger="conveyor_repair_completed", limit=50)

    def test_typed_damage_recreates_only_dedicated_runner_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp)
            worktree = canonical / ".charlie_runner" / "runner"
            worktree.mkdir(parents=True)
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                return Mock(returncode=0, stdout="", stderr="")

            with patch.object(supervisor, "REPO_ROOT", worktree), patch.dict(os.environ, {"CHARLIE_RUNNER_BASE_BRANCH": "runner-base"}):
                result = supervisor._recreate_damaged_runner_worktree(
                    {"status": "git_operation_marker_permission_denied"}, run_factory=fake_run
                )
        self.assertTrue(result["success"])
        self.assertEqual(commands[-1], ["git", "worktree", "add", "--force", str(worktree), "runner-base"])


if __name__ == "__main__":
    unittest.main()
