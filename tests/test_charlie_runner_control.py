import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from modules.charlie import runner_control


class CharlieRunnerControlTests(unittest.TestCase):
    def test_runner_status_reports_not_started_without_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner_control.runner_status(Path(tmp) / "missing.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "runner_not_started")
        self.assertFalse(result["active"])
        self.assertFalse(result["can_start_from_web"])
        self.assertFalse(result["can_stop_from_web"])
        self.assertEqual(result["orphan_processes"], [])

    @patch("modules.charlie.runner_control._find_runner_processes")
    def test_runner_status_reports_orphaned_process_without_default_heartbeat(self, find_processes):
        find_processes.return_value = [{
            "pid": 1234,
            "parent_pid": 1000,
            "command": "python scripts/charlie_mission_pickup.py --watch --continuous",
        }]

        with tempfile.TemporaryDirectory() as tmp:
            result = runner_control.runner_status(Path(tmp) / "missing.json", include_orphans=True)

        self.assertEqual(result["status"], "runner_orphaned")
        self.assertFalse(result["active"])
        self.assertEqual(result["orphan_processes"][0]["pid"], 1234)

    def test_runner_status_reports_active_with_fresh_heartbeat_and_live_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "runner.json"
            ledger = Path(tmp) / "ledger.json"
            ledger.write_text(json.dumps({
                "version": "charlie_agent_runner_v2",
                "execution_id": "EXEC-1",
                "status": "running",
                "last_progress_at": "2026-06-30T00:00:00+00:00",
                "stages": [{
                    "agent": "builder",
                    "status": "running",
                    "attempt": 1,
                    "current_action": "builder running",
                    "commands_run": ["node --check static/js/charlieMissionControl.js"],
                    "files_inspected": ["static/js/charlieMissionControl.js"],
                    "stdout_tail": "ok",
                }],
            }), encoding="utf-8")
            runner_control.write_runner_heartbeat({
                "status": "codex_running",
                "mission_id": "MISSION-1",
                "elapsed_seconds": 610,
                "changed_files_count": 2,
                "final_artifact_present": False,
                "execution_artifact": ".charlie_runner/executions/MISSION.final.md",
                "agent_runner_version": "charlie_agent_runner_v2",
                "current_agent": "builder",
                "current_action": "builder running",
                "agent_ledger_path": str(ledger),
                "stdout_tail": "running tests",
                "stderr_tail": "",
            }, heartbeat)

            with patch("modules.charlie.runner_control.REPO_ROOT", Path(tmp)):
                result = runner_control.runner_status(heartbeat)

        self.assertEqual(result["status"], "runner_active")
        self.assertTrue(result["active"])
        self.assertEqual(result["last_result_status"], "codex_running")
        self.assertEqual(result["last_mission_id"], "MISSION-1")
        self.assertEqual(result["elapsed_seconds"], 610)
        self.assertEqual(result["changed_files_count"], 2)
        self.assertFalse(result["final_artifact_present"])
        self.assertEqual(result["execution_artifact"], ".charlie_runner/executions/MISSION.final.md")
        self.assertEqual(result["agent_runner_version"], "charlie_agent_runner_v2")
        self.assertEqual(result["current_agent"], "builder")
        self.assertEqual(result["current_action"], "builder running")
        self.assertEqual(result["agent_ledger_path"], str(ledger))
        self.assertEqual(result["agent_ledger"]["latest_stage"]["agent"], "builder")
        self.assertEqual(result["agent_ledger"]["latest_stage"]["commands_run"][0], "node --check static/js/charlieMissionControl.js")
        self.assertEqual(result["stdout_tail"], "running tests")

    @patch("modules.charlie.runner_control._pid_alive", return_value=True)
    def test_runner_status_reports_stale_heartbeat(self, _pid_alive):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "runner.json"
            runner_control.write_runner_heartbeat({"status": "watch_started"}, heartbeat)
            now = datetime.now(timezone.utc) + timedelta(seconds=runner_control.STALE_SECONDS + 10)

            result = runner_control.runner_status(heartbeat, now=now)

        self.assertEqual(result["status"], "runner_stale_or_stopped")
        self.assertFalse(result["active"])
        self.assertFalse(result["heartbeat_fresh"])

    @patch("modules.charlie.runner_control._current_git_commit", return_value="new-commit")
    @patch("modules.charlie.runner_control._pid_alive", return_value=True)
    def test_runner_status_reports_code_stale_when_started_from_old_commit(self, _pid_alive, _commit):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "runner.json"
            heartbeat.write_text(json.dumps({
                "pid": 1234,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "last_result_status": "watch_started",
                "runner_source_commit": "old-commit",
            }), encoding="utf-8")

            result = runner_control.runner_status(heartbeat)

        self.assertEqual(result["status"], "runner_code_stale")
        self.assertFalse(result["active"])
        self.assertTrue(result["runner_code_stale"])
        self.assertEqual(result["runner_source_commit"], "old-commit")
        self.assertEqual(result["current_source_commit"], "new-commit")

    @patch("modules.charlie.runner_control._pid_alive", return_value=False)
    def test_runner_status_recovers_existing_final_artifact_from_stale_heartbeat(self, _pid_alive):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            heartbeat = tmp_path / "runner.json"
            final_path = tmp_path / "mission.final.md"
            final_path.write_text("Reviewer pass", encoding="utf-8")
            runner_control.write_runner_heartbeat({
                "status": "codex_running",
                "mission_id": "MISSION-1",
                "final_artifact_present": False,
                "execution_artifact": str(final_path),
            }, heartbeat)

            result = runner_control.runner_status(heartbeat)

        self.assertEqual(result["status"], "runner_stale_or_stopped")
        self.assertEqual(result["last_result_status"], "codex_final_artifact_seen")
        self.assertTrue(result["final_artifact_present"])

    @patch("modules.charlie.runner_control.os.kill")
    @patch("modules.charlie.runner_control._pid_alive_windows", return_value=True)
    def test_pid_alive_on_windows_does_not_use_os_kill_probe(self, pid_alive_windows, kill):
        with patch("modules.charlie.runner_control.os.name", "nt"):
            result = runner_control._pid_alive(1234)

        self.assertTrue(result)
        pid_alive_windows.assert_called_once_with(1234)
        kill.assert_not_called()

    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_start_runner_does_not_start_duplicate_when_active(self, popen, status):
        status.return_value = {"active": True, "status": "runner_active"}

        result, status_code = runner_control.start_runner()

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "runner_already_active")
        popen.assert_not_called()

    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_start_runner_does_not_start_duplicate_when_orphaned(self, popen, status):
        status.return_value = {
            "active": False,
            "status": "runner_orphaned",
            "orphan_processes": [{"pid": 1234}],
        }

        result, status_code = runner_control.start_runner()

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "runner_orphaned_existing_process")
        popen.assert_not_called()

    @patch("modules.charlie.runner_control.os.kill")
    @patch("modules.charlie.runner_control.runner_status")
    def test_stop_runner_stops_orphaned_processes(self, status, kill):
        status.return_value = {
            "pid": None,
            "orphan_processes": [{"pid": 1234}, {"pid": 5678}],
        }

        result, status_code = runner_control.stop_runner()

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "runner_stop_requested")
        self.assertEqual(result["pids"], [1234, 5678])
        self.assertEqual(kill.call_count, 2)

    @patch("modules.charlie.runner_control._git_worktree_prune", return_value={"status": "ok", "returncode": 0})
    @patch("modules.charlie.runner_control.stop_runner")
    @patch("modules.charlie.runner_control.runner_status")
    def test_cleanup_runner_environment_skips_active_runner(self, status, stop_runner, prune):
        status.return_value = {"active": True, "status": "runner_active", "orphan_processes": []}

        result, status_code = runner_control.cleanup_runner_environment()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["actions"][0]["status"], "skipped_active_runner")
        stop_runner.assert_not_called()
        prune.assert_called_once()

    @patch("modules.charlie.runner_control._git_worktree_prune", return_value={"status": "ok", "returncode": 0})
    @patch("modules.charlie.runner_control.stop_runner")
    @patch("modules.charlie.runner_control.runner_status")
    def test_cleanup_runner_environment_stops_stale_runner(self, status, stop_runner, prune):
        status.return_value = {
            "active": False,
            "status": "runner_code_stale",
            "process_alive": True,
            "orphan_processes": [],
        }
        stop_runner.return_value = ({"success": True, "status": "runner_stop_requested", "pids": [1234]}, 200)

        result, status_code = runner_control.cleanup_runner_environment()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["actions"][0]["result"]["status"], "runner_stop_requested")
        stop_runner.assert_called_once()
        prune.assert_called_once()

    @patch("modules.charlie.runner_control.subprocess.run")
    def test_git_worktree_prune_reports_permission_denied_as_partial_failure(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = ""
        run.return_value.stderr = "error: failed to delete '.git/worktrees/example': Permission denied"

        result = runner_control._git_worktree_prune()

        self.assertEqual(result["status"], "partial_failure")
        self.assertIn("Permission denied", result["stderr_tail"])


if __name__ == "__main__":
    unittest.main()
