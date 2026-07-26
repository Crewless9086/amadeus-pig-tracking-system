import tempfile
import unittest
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules.charlie import process_ownership, runner_control
from scripts import charlie_runner_control as runner_control_cli


def successful_bootstrap_observation(root_pid, *, generation, revision, startup_nonce, **_kwargs):
    root = {
        "pid": root_pid, "creation_time": "launcher-created",
        "executable_path": "C:/venv/python.exe",
        "command_fingerprint": "launcher-command", "parent_pid": 999,
        "runner_generation": generation, "mission_id": "charlie-control",
        "execution_id": generation, "ownership_type": "charlie_runner",
        "revision": revision, "startup_nonce": startup_nonce,
        "process_role": "test_launcher",
    }
    interpreter = {
        **root, "pid": int(root_pid) + 1, "parent_pid": root_pid,
        "creation_time": "interpreter-created",
        "command_fingerprint": "interpreter-command",
        "process_role": "test_interpreter",
    }
    return {
        "success": True,
        "tree": {
            "version": "charlie_process_tree_v1",
            "runner_generation": generation,
            "root_pid": root_pid,
            "root": root,
            "members": [root, interpreter],
        },
        "validation": {"authorized": True, "member_pids": [root_pid, int(root_pid) + 1]},
    }


class CharlieRunnerControlTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows governed lifecycle harness")
    def test_windows_governed_start_and_stop_exact_observed_tree(self):
        if not process_ownership._windows_process_snapshot():
            self.skipTest("Windows process inspection is unavailable to this session")
        powershell = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        )
        command = (
            "$p=Start-Process powershell.exe -ArgumentList "
            "'-NoProfile','-NonInteractive','-Command','Start-Sleep -Seconds 30' "
            "-PassThru -WindowStyle Hidden; Wait-Process -Id $p.Id"
        )
        original_observe = runner_control.observe_process_tree

        def observe(root_pid, *, generation, revision, startup_nonce, **_kwargs):
            result = original_observe(
                root_pid,
                generation=generation,
                revision=revision,
                startup_nonce=startup_nonce,
                expected_root_executable=str(powershell),
                process_role_prefix="supervisor",
                timeout_seconds=10,
            )
            if result.get("success"):
                tree = result["tree"]
                members = [
                    item for item in tree["members"]
                    if Path(str(item.get("executable_path") or "")).name.casefold()
                    == "powershell.exe"
                ]
                tree = process_ownership.make_process_tree_record(
                    tree["root"], members, generation
                )
                result["tree"] = tree
                result["validation"] = process_ownership.validate_bootstrap_tree(
                    tree,
                    generation=generation,
                    revision=revision,
                    startup_nonce=startup_nonce,
                )
            return result

        started_pid = 0
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "CHARLIE_TEST_ISOLATION": "0",
            process_ownership.TERMINATION_ENABLE_ENV:
                process_ownership.TERMINATION_ENABLE_VALUE,
        }, clear=False), patch.object(
            runner_control, "RUNNER_DIR", Path(tmp)
        ), patch.object(runner_control, "LOG_PATH", Path(tmp) / "runner.log"), patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ), patch.object(runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(
            runner_control, "SUPERVISOR_COMMAND",
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
        ), patch.object(
            runner_control, "runner_status",
            return_value={"active": False, "status": "runner_not_started", "orphan_processes": []},
        ), patch.object(
            runner_control, "_current_git_commit", return_value="revision-1"
        ), patch.object(
            runner_control, "observe_process_tree", side_effect=observe
        ), patch.object(
            runner_control, "_wait_for_supervisor_ack",
            return_value={"success": True, "status": "current_generation_acknowledged"},
        ):
            try:
                started, start_status = runner_control.start_runner()
                self.assertEqual(start_status, 200, started)
                started_pid = int(started["pid"])
                stopped, stop_status = runner_control.stop_runner()
                self.assertEqual(stop_status, 200, stopped)
                self.assertTrue(runner_control.SUPERVISOR_STOP_PATH.exists())
                self.assertIsNone(runner_control.inspect_process(started_pid))
            finally:
                if started_pid and runner_control.inspect_process(started_pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(started_pid), "/T", "/F"],
                        capture_output=True, text=True, check=False,
                    )
    def test_governed_start_default_never_removes_stop_marker(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(runner_control.subprocess, "Popen") as popen:
            runner_control.SUPERVISOR_STOP_PATH.write_text(
                "owner stop", encoding="utf-8"
            )
            result, status = runner_control.start_runner()
            marker = runner_control.SUPERVISOR_STOP_PATH.read_text(encoding="utf-8")
        self.assertEqual(status, 423)
        self.assertEqual(result["status"], "governed_stop_active")
        self.assertEqual(marker, "owner stop")
        popen.assert_not_called()

    def test_supported_cli_start_cannot_remove_stop_marker(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(
            runner_control_cli.sys, "argv", ["charlie_runner_control.py", "start"]
        ), patch.object(runner_control.subprocess, "Popen") as popen:
            runner_control.SUPERVISOR_STOP_PATH.write_text(
                "owner stop", encoding="utf-8"
            )
            exit_code = runner_control_cli.main()
            marker = runner_control.SUPERVISOR_STOP_PATH.read_text(encoding="utf-8")
        self.assertEqual(exit_code, 1)
        self.assertEqual(marker, "owner stop")
        popen.assert_not_called()

    def test_final_acknowledgement_binds_both_live_trees_and_nonces(self):
        generation = "generation-1"
        revision = "revision-1"
        supervisor_tree = successful_bootstrap_observation(
            100,
            generation=generation,
            revision=revision,
            startup_nonce="supervisor-nonce",
        )["tree"]
        runner_tree = successful_bootstrap_observation(
            200,
            generation=generation,
            revision=revision,
            startup_nonce="runner-nonce",
        )["tree"]
        runner_identity = runner_tree["members"][1]
        packet = {
            "version": runner_control.SUPERVISOR_PACKET_VERSION,
            "generation": generation,
            "startup_nonce": "supervisor-nonce",
            "created_at": "created",
            "updated_at": "updated",
            "intended_runtime_revision": revision,
            "intended_execution_revision": revision,
            "status": "running",
            "runner_state": "running",
            "supervisor_tree_identity": supervisor_tree,
            "process_tree_identity": runner_tree,
            "runner_startup_nonce": "runner-nonce",
            "runner_controller_acknowledgement": {
                "generation": generation,
                "startup_nonce": "runner-nonce",
                "revision": revision,
            },
        }
        heartbeat = {
            "status": "ownership_ready",
            "supervisor_generation": generation,
            "runner_source_commit": revision,
            "startup_nonce": "runner-nonce",
            "pid": runner_identity["pid"],
            "process_identity": runner_identity,
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ), patch.object(
            runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"
        ), patch.object(
            runner_control, "validate_live_bootstrap_tree",
            side_effect=[
                {"authorized": True, "member_pids": [100, 101]},
                {"authorized": True, "member_pids": [200, 201]},
            ],
        ), patch.object(runner_control, "_pid_alive", return_value=True):
            runner_control.atomic_write_json(runner_control.SUPERVISOR_PATH, packet)
            runner_control.atomic_write_json(runner_control.HEARTBEAT_PATH, heartbeat)
            result = runner_control._wait_for_supervisor_ack(
                generation,
                revision,
                supervisor_pid=100,
                startup_nonce="supervisor-nonce",
                timeout_seconds=1,
                sleep_fn=lambda _seconds: None,
            )
            persisted = json.loads(
                runner_control.SUPERVISOR_PATH.read_text(encoding="utf-8")
            )
        self.assertTrue(result["success"])
        self.assertEqual(persisted["status"], "running_authorized")
        final = persisted["controller_final_acknowledgement"]
        self.assertEqual(final["supervisor_startup_nonce"], "supervisor-nonce")
        self.assertEqual(final["runner_startup_nonce"], "runner-nonce")
        self.assertEqual(final["supervisor_pid"], "100")
        self.assertEqual(final["runner_pid"], "201")

    def test_partial_current_generation_acknowledgement_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ), patch.object(
            runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"
        ), patch.object(runner_control, "_pid_alive", return_value=True):
            runner_control.atomic_write_json(
                runner_control.SUPERVISOR_PATH,
                {
                    "version": runner_control.SUPERVISOR_PACKET_VERSION,
                    "generation": "generation-1",
                },
            )
            result = runner_control._wait_for_supervisor_ack(
                "generation-1",
                "revision-1",
                supervisor_pid=100,
                startup_nonce="nonce-1",
                timeout_seconds=0.01,
                sleep_fn=lambda _seconds: None,
            )
        self.assertFalse(result["success"])
        self.assertNotEqual(result["reason"], "")

    def test_startup_failure_evidence_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "START_CONTAINMENT_PATH", Path(tmp) / "containment.json"
        ), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ):
            runner_control.SUPERVISOR_STOP_PATH.write_text("stop", encoding="utf-8")
            evidence = runner_control._write_startup_failure(
                "generation-1",
                "nonce-1",
                "revision-1",
                "postgresql://owner:secret@db.example/main",
                {"failure_detail": {"DATABASE_URL": "postgresql://owner:secret@db/main"}},
            )
            raw = runner_control.START_CONTAINMENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("secret", raw)
        self.assertNotIn("owner:", raw)
        self.assertEqual(evidence["status"], "ownership_identity_incomplete")

    def test_incomplete_controller_observation_is_durable_and_contained(self):
        process = Mock(pid=4321)
        process.poll.return_value = 1
        incomplete_tree = {
            "version": "charlie_process_tree_v1",
            "root": {"pid": 4321},
            "members": [{"pid": 4321}],
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "RUNNER_DIR", Path(tmp)
        ), patch.object(runner_control, "LOG_PATH", Path(tmp) / "runner.log"), patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(
            runner_control, "START_CONTAINMENT_PATH", Path(tmp) / "containment.json"
        ), patch.object(runner_control, "runner_status", return_value={
            "active": False, "status": "runner_not_started", "orphan_processes": [],
        }), patch.object(
            runner_control, "process_termination_enabled", return_value=True
        ), patch.object(
            runner_control, "_current_git_commit", return_value="revision-1"
        ), patch.object(
            runner_control.subprocess, "Popen", return_value=process
        ), patch.object(runner_control, "observe_process_tree", return_value={
            "success": False,
            "reason": "ownership_identity_incomplete:root.executable_path",
            "tree": incomplete_tree,
        }), patch.object(
            runner_control, "_contain_spawned_process",
            return_value={
                "success": True,
                "reason": "fresh_spawn_handle_tree_termination_verified",
            },
        ):
            result, status = runner_control.start_runner()
            evidence = json.loads(
                runner_control.START_CONTAINMENT_PATH.read_text(encoding="utf-8")
            )
            self.assertTrue(runner_control.SUPERVISOR_STOP_PATH.exists())
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "ownership_identity_incomplete")
        self.assertTrue(result["containment"]["success"])
        self.assertEqual(
            result["containment"]["reason"],
            "fresh_spawn_handle_tree_termination_verified",
        )
        self.assertEqual(
            evidence["reason"],
            "ownership_identity_incomplete:root.executable_path",
        )
        self.assertEqual(evidence["process_tree_identity"], incomplete_tree)

    def test_empty_observation_falls_back_to_exact_spawn_handle_and_verifies_exit(self):
        process = Mock(pid=4321)
        process.poll.return_value = 1
        with patch.object(
            runner_control, "_contain_observed_tree",
            return_value={"success": False, "reason": "ownership_identity_incomplete"},
        ), patch.object(
            runner_control.subprocess, "run", return_value=Mock(returncode=0)
        ):
            result = runner_control._contain_spawned_process(process, {})
        self.assertTrue(result["success"])
        self.assertEqual(
            result["reason"], "fresh_spawn_handle_tree_termination_verified"
        )
        process.wait.assert_called()

    def test_atomic_state_replacement_preserves_previous_packet_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "supervisor.json"
            path.write_text('{"generation":"old"}', encoding="utf-8")
            with self.assertRaises(OSError):
                runner_control.atomic_write_json(
                    path,
                    {"generation": "new"},
                    replace_fn=Mock(side_effect=OSError("replace denied")),
                )
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"generation": "old"})
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_governed_start_ack_timeout_places_stop_marker_and_contains_current_tree(self):
        process = Mock(pid=4321)
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "RUNNER_DIR", Path(tmp)
        ), patch.object(runner_control, "LOG_PATH", Path(tmp) / "runner.log"), patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ), patch.object(runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(runner_control, "runner_status", return_value={
            "active": False, "status": "runner_not_started", "orphan_processes": [],
        }), patch.object(runner_control, "process_termination_enabled", return_value=True), patch.object(
            runner_control, "_current_git_commit", return_value="revision-1"
        ), patch.object(
            runner_control.subprocess, "Popen", return_value=process
        ), patch.object(runner_control, "_wait_for_supervisor_ack", return_value={
            "success": False, "reason": "runner_heartbeat_acknowledgement_missing",
        }), patch.object(runner_control, "stop_runner", return_value=(
            {"success": True, "status": "runner_stop_requested"}, 200
        )), patch.object(runner_control, "_contain_started_supervisor", return_value={
            "success": True, "reason": "exact_supervisor_tree_terminated",
        }), patch.object(runner_control, "observe_process_tree", side_effect=successful_bootstrap_observation):
            result, status = runner_control.start_runner()
            self.assertTrue(runner_control.SUPERVISOR_STOP_PATH.exists())
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "runner_start_acknowledgement_failed")

    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_start_requires_bounded_containment_capability(self, status, _enabled):
        status.return_value = {
            "active": False, "status": "runner_not_started", "orphan_processes": [],
        }
        result, status_code = runner_control.start_runner()
        self.assertEqual(status_code, 423)
        self.assertEqual(result["status"], "start_containment_capability_not_enabled")

    def test_start_timeout_contains_only_exact_fresh_supervisor_identity(self):
        process = {
            "pid": 4321,
            "creation_time": "created-now",
            "executable_path": "C:/venv/python.exe",
            "command_line": "python charlie_runner_supervisor.py",
            "parent_pid": 123,
            "ancestry": [],
            "current_process_ancestry": [],
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "START_CONTAINMENT_PATH", Path(tmp) / "containment.json"
        ), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(runner_control, "_stop_process_tree", return_value={
            "authorized": True, "terminated": True, "pid": 4321,
        }) as stop_tree:
            runner_control.SUPERVISOR_STOP_PATH.write_text("stop", encoding="utf-8")
            result = runner_control._contain_started_supervisor(
                4321, "generation-1", inspector=Mock(return_value=process)
            )
            persisted = json.loads(runner_control.START_CONTAINMENT_PATH.read_text(encoding="utf-8"))
        self.assertTrue(result["success"])
        self.assertEqual(persisted["supervisor_identity"]["pid"], 4321)
        self.assertEqual(persisted["generation"], "generation-1")
        stop_tree.assert_called_once()
    def test_heartbeat_and_status_never_persist_environment_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "runner.json"
            secret = "postgresql://owner:do-not-persist@db.example.test/main"
            with patch.dict("modules.charlie.secret_redaction.os.environ", {"DATABASE_URL": secret}, clear=True):
                runner_control.write_runner_heartbeat({"status": "codex_running", "stderr_tail": secret}, heartbeat)
                stored = heartbeat.read_text(encoding="utf-8")
                result = runner_control.runner_status(heartbeat, include_orphans=False, include_git=False, include_ledger=False)
            self.assertNotIn("do-not-persist", stored)
            self.assertNotIn("do-not-persist", result["stderr_tail"])

    def test_worktree_resolves_primary_checkout_for_runtime_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            worktree = root / ".charlie_runner" / "live"
            git_dir = root / ".git" / "worktrees" / "live"
            git_dir.mkdir(parents=True)
            worktree.mkdir(parents=True)
            (worktree / ".git").write_text(f"gitdir: {git_dir}", encoding="utf-8")
            self.assertEqual(runner_control._shared_repository_root(worktree), root)

    def test_windows_powershell_probes_are_hidden(self):
        source = Path(runner_control.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count('["powershell", "-NoProfile", "-Command", script]'), 2)
        self.assertGreaterEqual(source.count('creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)'), 2)

    def test_shared_repo_venv_is_used_from_runner_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worktree = root / ".charlie_runner" / "clean"
            python = root / "venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            self.assertEqual(runner_control._python_executable(worktree), str(python))
    @patch("modules.charlie.runner_control._pid_descends_from", return_value=True)
    @patch("modules.charlie.runner_control._current_git_commit", return_value="same")
    @patch("modules.charlie.runner_control._pid_alive", return_value=True)
    def test_supervisor_owns_real_python_descendant_of_windows_venv_shim(self, _alive, _commit, descendant):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            heartbeat = root / "runner.json"
            supervisor = root / "supervisor.json"
            heartbeat.write_text(json.dumps({
                "pid": 55004, "last_seen": datetime.now(timezone.utc).isoformat(),
                "runner_source_commit": "same", "supervisor_generation": "gen-1",
                "last_result_status": "watch_started",
            }), encoding="utf-8")
            supervisor.write_text(json.dumps({
                "pid": 123636, "child_pid": 123588, "generation": "gen-1", "status": "runner_started",
            }), encoding="utf-8")
            with patch.object(runner_control, "HEARTBEAT_PATH", heartbeat), patch.object(runner_control, "SUPERVISOR_PATH", supervisor):
                result = runner_control.runner_status(include_orphans=False)
        self.assertTrue(result["active"])
        self.assertTrue(result["supervisor_owns_runner"])
        self.assertEqual(result["operating_state"], "waiting_for_queue")
        descendant.assert_called_once_with(55004, 123588)

    @patch("modules.charlie.runner_control._pid_descends_from", return_value=False)
    @patch("modules.charlie.runner_control._current_git_commit", return_value="same")
    @patch("modules.charlie.runner_control._pid_alive", return_value=True)
    def test_generation_ownership_survives_transient_windows_ancestry_failure(self, _alive, _commit, _descendant):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            heartbeat = root / "runner.json"
            supervisor = root / "supervisor.json"
            heartbeat.write_text(json.dumps({
                "pid": 55004, "last_seen": datetime.now(timezone.utc).isoformat(),
                "runner_source_commit": "same", "supervisor_generation": "gen-1",
            }), encoding="utf-8")
            supervisor.write_text(json.dumps({
                "pid": 123636, "child_pid": 123588, "generation": "gen-1", "status": "runner_started",
            }), encoding="utf-8")
            with patch.object(runner_control, "HEARTBEAT_PATH", heartbeat), patch.object(runner_control, "SUPERVISOR_PATH", supervisor):
                result = runner_control.runner_status(include_orphans=False)

        self.assertTrue(result["active"])
        self.assertTrue(result["supervisor_owns_runner"])

    @patch("modules.charlie.runner_control._current_git_commit", return_value="same")
    @patch("modules.charlie.runner_control._pid_alive", return_value=True)
    def test_default_status_is_active_only_for_generation_owned_child(self, _alive, _commit):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            heartbeat = root / "runner.json"
            supervisor = root / "supervisor.json"
            heartbeat.write_text(json.dumps({
                "pid": 222, "last_seen": datetime.now(timezone.utc).isoformat(),
                "runner_source_commit": "same", "supervisor_generation": "gen-1",
            }), encoding="utf-8")
            supervisor.write_text(json.dumps({
                "pid": 111, "child_pid": 222, "generation": "gen-1", "status": "runner_started",
            }), encoding="utf-8")
            with patch.object(runner_control, "HEARTBEAT_PATH", heartbeat), patch.object(runner_control, "SUPERVISOR_PATH", supervisor):
                result = runner_control.runner_status(include_orphans=False)
        self.assertTrue(result["active"])
        self.assertTrue(result["supervisor_owns_runner"])
        self.assertEqual(result["owner_process_pid"], 111)

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
        self.assertEqual(result["operating_state"], "running_agent")
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
    def test_healthy_idle_runner_reports_waiting_not_stale(self, _pid_alive):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "runner.json"
            runner_control.write_runner_heartbeat({"status": "watch_started"}, heartbeat)
            result = runner_control.runner_status(heartbeat)
        self.assertTrue(result["active"])
        self.assertEqual(result["operating_state"], "waiting_for_queue")

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

    def test_tasklist_pid_fallback_matches_exact_pid(self):
        completed = SimpleNamespace(returncode=0, stdout='"python.exe","10308","Console","1","20,000 K"\n')
        runner = Mock(return_value=completed)

        self.assertTrue(runner_control._pid_exists_windows_tasklist(10308, runner=runner))
        self.assertFalse(runner_control._pid_exists_windows_tasklist(1030, runner=runner))

    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_start_runner_does_not_start_duplicate_when_active(self, popen, status):
        status.return_value = {"active": True, "status": "runner_active"}

        result, status_code = runner_control.start_runner()

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "runner_already_active")

    @patch("modules.charlie.runner_control._current_git_commit", return_value="revision-1")
    @patch("modules.charlie.runner_control.observe_process_tree", side_effect=successful_bootstrap_observation)
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control._wait_for_supervisor_ack", return_value={"success": True, "status": "current_generation_acknowledged"})
    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_start_runner_accepts_watchdog_status_without_full_reprobe(self, popen, _ack, _enabled, _observe, _commit):
        popen.return_value.pid = 1234
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner_control, "RUNNER_DIR", Path(tmp)), patch.object(runner_control, "LOG_PATH", Path(tmp) / "runner.log"), patch.object(runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"), patch.object(runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"), patch.object(runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"):
            result, status_code = runner_control.start_runner(status_override={"active": False, "status": "runner_not_started", "orphan_processes": []})
        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "runner_started")
        popen.assert_called_once()

    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_watchdog_start_cannot_clear_governed_stop_marker(self, popen):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ):
            runner_control.SUPERVISOR_STOP_PATH.write_text("governed stop", encoding="utf-8")
            result, status_code = runner_control.start_runner(
                status_override={
                    "active": False,
                    "status": "runner_stale_or_stopped",
                    "orphan_processes": [],
                },
                respect_stop_marker=True,
            )
            self.assertTrue(runner_control.SUPERVISOR_STOP_PATH.exists())
        self.assertEqual(status_code, 423)
        self.assertEqual(result["status"], "governed_stop_active")
        popen.assert_not_called()

    @patch("modules.charlie.runner_control._current_git_commit", return_value="revision-1")
    @patch("modules.charlie.runner_control.observe_process_tree", side_effect=successful_bootstrap_observation)
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control._wait_for_supervisor_ack", return_value={"success": True, "status": "current_generation_acknowledged"})
    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_start_runner_launches_supervisor(self, popen, status, _ack, _enabled, _observe, _commit):
        status.return_value = {"active": False, "status": "runner_not_started", "orphan_processes": []}
        popen.return_value.pid = 4321
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner_control, "RUNNER_DIR", Path(tmp)), patch.object(runner_control, "LOG_PATH", Path(tmp) / "runner.log"), patch.object(runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"), patch.object(runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"), patch.object(runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"):
            result, status_code = runner_control.start_runner()

        self.assertEqual(status_code, 200)
        self.assertEqual(result["pid"], 4321)
        command = popen.call_args.args[0]
        self.assertTrue(command[-1].endswith("charlie_runner_supervisor.py"))

    @patch("modules.charlie.runner_control._pid_alive", return_value=True)
    @patch("modules.charlie.runner_control.subprocess.Popen")
    def test_start_runner_refuses_duplicate_when_live_supervisor_owns_control_plane(self, popen, _pid_alive):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ):
            runner_control.SUPERVISOR_PATH.write_text(
                json.dumps({"pid": 9876, "generation": "generation-live"}), encoding="utf-8"
            )
            result, status_code = runner_control.start_runner(
                status_override={"active": False, "status": "transient_stale", "orphan_processes": []}
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "runner_already_active")
        self.assertEqual(result["supervisor_pid"], 9876)
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

    @patch("modules.charlie.runner_control._stop_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_stop_runner_refuses_orphans_without_identity_records(self, status, _disabled, _enabled, stop_tree):
        status.return_value = {
            "pid": None,
            "orphan_processes": [{"pid": 1234}, {"pid": 5678}],
        }

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner_control, "RUNNER_DIR", Path(tmp)), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"):
            result, status_code = runner_control.stop_runner()

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "runner_process_ownership_not_proven")
        stop_tree.assert_not_called()

    @patch("modules.charlie.runner_control._stop_process_tree")
    @patch("modules.charlie.runner_control.validate_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_stop_uses_launcher_tree_and_persists_evidence(
        self, status, _disabled, _enabled, validate_tree, stop_tree
    ):
        root_record = {
            "pid": 200,
            "creation_time": "launcher-created",
            "executable_path": "C:/venv/python.exe",
            "command_fingerprint": "launcher-command",
            "parent_pid": 100,
            "runner_generation": "gen-1",
            "mission_id": "charlie-control",
            "execution_id": "gen-1",
            "ownership_type": "charlie_runner",
        }
        interpreter_record = {**root_record, "pid": 201, "parent_pid": 200}
        status.return_value = {"orphan_processes": [], "active": True}
        validate_tree.return_value = {
            "authorized": True,
            "reason": "logical_process_tree_identity_match",
            "pid": 200,
            "member_pids": [200, 201],
        }
        stop_tree.return_value = {"authorized": True, "terminated": True, "pid": 200}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor_path = root / "supervisor.json"
            heartbeat_path = root / "runner.json"
            stop_path = root / "supervisor.stop"
            supervisor_path.write_text(json.dumps({
                "pid": 100,
                "generation": "gen-1",
                "child_pid": 200,
                "child_identity": root_record,
            }), encoding="utf-8")
            heartbeat_path.write_text(
                json.dumps({"pid": 201, "process_identity": interpreter_record}),
                encoding="utf-8",
            )
            with patch.object(runner_control, "RUNNER_DIR", root), patch.object(
                runner_control, "SUPERVISOR_PATH", supervisor_path
            ), patch.object(runner_control, "HEARTBEAT_PATH", heartbeat_path), patch.object(
                runner_control, "SUPERVISOR_STOP_PATH", stop_path
            ):
                result, status_code = runner_control.stop_runner()
                persisted = json.loads(supervisor_path.read_text(encoding="utf-8"))

        self.assertEqual(status_code, 200)
        self.assertEqual(result["pids"], [200])
        stop_tree.assert_called_once()
        self.assertTrue(persisted["stop_evidence"]["stop_marker_present"])
        self.assertEqual(
            persisted["stop_evidence"]["reason"],
            "logical_process_tree_identity_match",
        )
        self.assertEqual(
            persisted["stop_evidence"]["process_tree_identity"]["members"][1]["pid"],
            201,
        )

    @patch("modules.charlie.runner_control._stop_process_tree")
    @patch("modules.charlie.runner_control.validate_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_stop_handles_current_supervisor_before_runner_spawn(
        self, status, _disabled, _enabled, validate_tree, stop_tree
    ):
        root_record = {
            "pid": 100,
            "creation_time": "launcher-created",
            "executable_path": "C:/venv/python.exe",
            "command_fingerprint": "supervisor-command",
            "parent_pid": 50,
            "runner_generation": "gen-1",
            "mission_id": "charlie-control",
            "execution_id": "gen-1",
            "ownership_type": "charlie_runner",
        }
        tree = {
            "version": "charlie_process_tree_v1",
            "generation": "gen-1",
            "root": root_record,
            "members": [root_record],
        }
        status.return_value = {"orphan_processes": [], "active": False}
        validate_tree.return_value = {
            "authorized": True, "reason": "logical_process_tree_identity_match",
            "pid": 100, "member_pids": [100],
        }
        stop_tree.return_value = {"authorized": True, "terminated": True, "pid": 100}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor_path = root / "supervisor.json"
            supervisor_path.write_text(json.dumps({
                "version": "charlie_supervisor_ownership_v2",
                "generation": "gen-1",
                "runner_state": "not_spawned",
                "supervisor_tree_identity": tree,
            }), encoding="utf-8")
            with patch.object(runner_control, "RUNNER_DIR", root), patch.object(
                runner_control, "SUPERVISOR_PATH", supervisor_path
            ), patch.object(runner_control, "HEARTBEAT_PATH", root / "runner.json"), patch.object(
                runner_control, "SUPERVISOR_STOP_PATH", root / "supervisor.stop"
            ):
                result, status_code = runner_control.stop_runner()
        self.assertEqual(status_code, 200)
        self.assertEqual(result["target_kind"], "supervisor")
        self.assertEqual(result["pids"], [100])

    @patch("modules.charlie.runner_control.validate_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_stop_returns_and_persists_exact_tree_rejection(
        self, status, _disabled, _enabled, validate_tree
    ):
        record = {
            "pid": 200,
            "creation_time": "created",
            "executable_path": "C:/python.exe",
            "command_fingerprint": "command",
            "parent_pid": 100,
            "runner_generation": "gen-1",
            "mission_id": "charlie-control",
            "execution_id": "gen-1",
            "ownership_type": "charlie_runner",
        }
        status.return_value = {"orphan_processes": [], "active": True}
        validate_tree.return_value = {
            "authorized": False,
            "reason": "member_201_command_fingerprint_mismatch",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor_path = root / "supervisor.json"
            heartbeat_path = root / "runner.json"
            stop_path = root / "supervisor.stop"
            supervisor_path.write_text(json.dumps({
                "generation": "gen-1", "child_identity": record,
            }), encoding="utf-8")
            heartbeat_path.write_text(
                json.dumps({"process_identity": {**record, "pid": 201}}),
                encoding="utf-8",
            )
            with patch.object(runner_control, "RUNNER_DIR", root), patch.object(
                runner_control, "SUPERVISOR_PATH", supervisor_path
            ), patch.object(runner_control, "HEARTBEAT_PATH", heartbeat_path), patch.object(
                runner_control, "SUPERVISOR_STOP_PATH", stop_path
            ):
                result, status_code = runner_control.stop_runner()
                persisted = json.loads(supervisor_path.read_text(encoding="utf-8"))

        self.assertEqual(status_code, 409)
        self.assertEqual(result["reason"], "member_201_command_fingerprint_mismatch")
        self.assertEqual(persisted["stop_evidence"]["reason"], result["reason"])
        self.assertTrue(persisted["stop_evidence"]["stop_marker_present"])

    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=False)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_stop_runner_without_capability_has_no_control_path_side_effects(self, status, _disabled, _enabled):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner_control, "RUNNER_DIR", Path(tmp)), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ):
            result, status_code = runner_control.stop_runner()
            self.assertFalse((Path(tmp) / "supervisor.stop").exists())
        self.assertEqual(status_code, 423)
        self.assertEqual(result["status"], "process_termination_not_enabled")
        status.assert_not_called()

    @patch("modules.charlie.runner_control._git_worktree_prune", return_value={"status": "ok", "returncode": 0})
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.stop_runner")
    @patch("modules.charlie.runner_control.runner_status")
    def test_cleanup_runner_environment_skips_active_runner(self, status, stop_runner, _disabled, prune):
        status.return_value = {"active": True, "status": "runner_active", "orphan_processes": []}

        result, status_code = runner_control.cleanup_runner_environment()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["actions"][0]["status"], "skipped_active_runner")
        stop_runner.assert_not_called()
        prune.assert_called_once()

    @patch("modules.charlie.runner_control._git_worktree_prune", return_value={"status": "ok", "returncode": 0})
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.stop_runner")
    @patch("modules.charlie.runner_control.runner_status")
    def test_cleanup_runner_environment_stops_stale_runner(self, status, stop_runner, _disabled, prune):
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
