import tempfile
import unittest
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules.charlie import process_ownership, runner_control
from tests.charlie_windows_lifecycle_harness import (job_owned_test, close_retained_test_process,
    owned_powershell_child, current_job_active_count, exited_launcher_command)
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


def stopped_observe_only_supervisor():
    private_key, public_key = process_ownership.generate_controller_signing_key()
    acknowledgement = {
        "status": "current_process_tree_acknowledged",
        "generation": "stopped-generation",
        "revision": "stopped-revision",
        "execution_mode": runner_control.EXECUTION_MODE_OBSERVE_ONLY,
    }
    acknowledgement["signature"] = process_ownership.sign_controller_acknowledgement(
        acknowledgement, private_key
    )
    return {
        "status": "supervisor_stopped",
        "generation": "stopped-generation",
        "intended_execution_revision": "stopped-revision",
        "execution_mode": runner_control.EXECUTION_MODE_OBSERVE_ONLY,
        "controller_public_key": public_key,
        "controller_final_acknowledgement": acknowledgement,
    }


class CharlieRunnerControlTests(unittest.TestCase):
    def test_termination_authority_requires_signed_exact_runner_tree(self):
        tree = successful_bootstrap_observation(
            100, generation="g", revision="r", startup_nonce="n"
        )["tree"]
        private_key, public_key = process_ownership.generate_controller_signing_key()
        acknowledgement = {
            "status": "current_process_tree_acknowledged",
            "generation": "g",
            "revision": "r",
            "execution_mode": runner_control.EXECUTION_MODE_OBSERVE_ONLY,
            "runner_tree_digest": process_ownership.process_tree_identity_digest(tree),
            "runner_member_pids": [100, 101],
        }
        acknowledgement["signature"] = process_ownership.sign_controller_acknowledgement(
            acknowledgement, private_key
        )
        supervisor = {
            "generation": "g",
            "intended_execution_revision": "r",
            "execution_mode": runner_control.EXECUTION_MODE_OBSERVE_ONLY,
            "controller_public_key": public_key,
            "controller_final_acknowledgement": acknowledgement,
        }

        decision = runner_control._validate_tree_termination_authority(
            supervisor, tree, target_kind="runner"
        )

        self.assertTrue(decision["authorized"])
        self.assertEqual(decision["member_pids"], [100, 101])

    def test_termination_authority_refuses_stale_or_substituted_tree(self):
        tree = successful_bootstrap_observation(
            100, generation="g", revision="r", startup_nonce="n"
        )["tree"]
        private_key, public_key = process_ownership.generate_controller_signing_key()
        acknowledgement = {
            "status": "current_process_tree_acknowledged",
            "generation": "g",
            "revision": "r",
            "execution_mode": runner_control.EXECUTION_MODE_OBSERVE_ONLY,
            "runner_tree_digest": process_ownership.process_tree_identity_digest(tree),
            "runner_member_pids": [100, 101],
        }
        acknowledgement["signature"] = process_ownership.sign_controller_acknowledgement(
            acknowledgement, private_key
        )
        substituted = json.loads(json.dumps(tree))
        substituted["root"]["pid"] = os.getpid()
        substituted["members"][0]["pid"] = os.getpid()
        supervisor = {
            "generation": "g",
            "intended_execution_revision": "r",
            "execution_mode": runner_control.EXECUTION_MODE_OBSERVE_ONLY,
            "controller_public_key": public_key,
            "controller_final_acknowledgement": acknowledgement,
        }

        decision = runner_control._validate_tree_termination_authority(
            supervisor, substituted, target_kind="runner"
        )

        self.assertFalse(decision["authorized"])
        self.assertEqual(decision["reason"], "controller_tree_runner_tree_digest_mismatch")

    @patch("modules.charlie.runner_control._start_runner_unlocked")
    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    def test_governed_resume_archives_stop_and_starts_observe_only(
        self, _disabled, _enabled, status, start
    ):
        status.return_value = {
            "active": False, "process_alive": False, "orphan_processes": []
        }
        start.return_value = ({"success": True, "status": "runner_started"}, 200)
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ):
            runner_control.SUPERVISOR_STOP_PATH.write_text("stop-evidence", encoding="utf-8")
            runner_control.SUPERVISOR_PATH.write_text(
                json.dumps(stopped_observe_only_supervisor()), encoding="utf-8"
            )
            result, code = runner_control.resume_observe_only_runner()
            archived = Path(result["cleared_stop_marker_evidence"])
            self.assertFalse(runner_control.SUPERVISOR_STOP_PATH.exists())
            self.assertEqual(archived.read_text(encoding="utf-8"), "stop-evidence")
        self.assertEqual(code, 200)
        self.assertEqual(result["status"], "observe_only_runner_resumed")
        start.assert_called_once_with(
            status_override=status.return_value,
            execution_mode=runner_control.EXECUTION_MODE_OBSERVE_ONLY,
        )

    @patch("modules.charlie.runner_control._start_runner_unlocked")
    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    def test_governed_resume_restores_stop_marker_when_start_fails(
        self, _disabled, _enabled, status, start
    ):
        status.return_value = {
            "active": False, "process_alive": False, "orphan_processes": []
        }
        start.return_value = ({"success": False, "status": "start_failed"}, 503)
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ):
            runner_control.SUPERVISOR_STOP_PATH.write_text("stop-evidence", encoding="utf-8")
            runner_control.SUPERVISOR_PATH.write_text(
                json.dumps(stopped_observe_only_supervisor()), encoding="utf-8"
            )
            result, code = runner_control.resume_observe_only_runner()
            self.assertEqual(
                runner_control.SUPERVISOR_STOP_PATH.read_text(encoding="utf-8"),
                "stop-evidence",
            )
            self.assertFalse(list(Path(tmp).glob("supervisor.stop.cleared-*")))
        self.assertEqual(code, 503)
        self.assertEqual(result["status"], "governed_resume_start_failed")

    @patch("modules.charlie.runner_control._start_runner_unlocked")
    @patch("modules.charlie.runner_control.runner_status")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    def test_governed_resume_refuses_live_runner(
        self, _disabled, _enabled, status, start
    ):
        status.return_value = {
            "active": True, "process_alive": True, "orphan_processes": []
        }
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ):
            runner_control.SUPERVISOR_STOP_PATH.write_text("stop", encoding="utf-8")
            result, code = runner_control.resume_observe_only_runner()
        self.assertEqual(code, 409)
        self.assertEqual(result["status"], "governed_resume_refused_live_runner")
        start.assert_not_called()

    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    def test_governed_resume_serializes_against_normal_start(
        self, _disabled, _enabled
    ):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def starting(**kwargs):
            calls.append(kwargs)
            entered.set()
            release.wait(5)
            return {"success": True, "status": "runner_started"}, 200

        status = {"active": False, "process_alive": False, "orphan_processes": []}
        outcome = {}
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runner_control, "RUNNER_DIR", Path(tmp)
        ), patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", Path(tmp) / "supervisor.stop"
        ), patch.object(
            runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
        ), patch.object(
            runner_control, "runner_status", return_value=status
        ), patch.object(
            runner_control, "_start_runner_unlocked", side_effect=starting
        ):
            runner_control.SUPERVISOR_STOP_PATH.write_text("stop", encoding="utf-8")
            runner_control.SUPERVISOR_PATH.write_text(
                json.dumps(stopped_observe_only_supervisor()), encoding="utf-8"
            )
            worker = threading.Thread(
                target=lambda: outcome.setdefault(
                    "resume", runner_control.resume_observe_only_runner()
                )
            )
            worker.start()
            self.assertTrue(entered.wait(5))
            competing, competing_code = runner_control.start_runner(
                status_override=status,
                execution_mode=runner_control.EXECUTION_MODE_OBSERVE_ONLY,
            )
            release.set()
            worker.join(5)
        self.assertEqual(competing_code, 409)
        self.assertEqual(competing["status"], "runner_controller_start_in_progress")
        self.assertEqual(outcome["resume"][1], 200)
        self.assertEqual(len(calls), 1)

    def test_observe_only_active_state_is_reported_truthfully(self):
        self.assertEqual(
            runner_control._runner_operating_state(
                {"execution_mode": "observe_only"}, {}, True
            ),
            "observe_only",
        )

    def test_observe_only_packet_requires_exact_mode(self):
        tree = successful_bootstrap_observation(
            100, generation="g", revision="r", startup_nonce="n"
        )["tree"]
        packet = {
            "version": runner_control.SUPERVISOR_PACKET_VERSION,
            "generation": "g",
            "startup_nonce": "n",
            "created_at": "now",
            "intended_runtime_revision": "r",
            "intended_execution_revision": "r",
            "runner_state": "not_spawned",
            "status": "supervisor_ready",
            "supervisor_tree_identity": tree,
        }
        valid, reason = runner_control.validate_supervisor_packet(
            packet, "g", "r", "r",
            runner_states={"not_spawned"}, startup_nonce="n",
            statuses={"supervisor_ready"}, execution_mode="observe_only",
        )
        self.assertFalse(valid)
        self.assertEqual(reason, "supervisor_packet_execution_mode_mismatch")

    def test_invalid_execution_mode_never_spawns(self):
        result, status = runner_control.start_runner(
            status_override={"active": False}, execution_mode="forged"
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "execution_mode_invalid")
    @unittest.skipUnless(os.name == "nt", "Windows launcher-first exit harness")
    @job_owned_test
    def test_windows_exited_launcher_still_contains_unobserved_child(self):
        process = None
        try:
            process = subprocess.Popen(exited_launcher_command(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                **runner_control.background_process_kwargs())
            self.assertEqual(process.wait(timeout=15), 0)
            self.assertGreaterEqual(current_job_active_count(), 2)  # test worker plus orphan
            with patch.object(runner_control, "inspect_descendant_processes", side_effect=AssertionError("exited PID inspection")), \
                 patch.object(runner_control.subprocess, "run", side_effect=AssertionError("exited PID termination")):
                containment = runner_control._contain_spawned_process(process, {})
            self.assertTrue(containment["success"], containment)
            self.assertEqual(containment["reason"], "spawned_process_handle_already_exited")
            self.assertGreaterEqual(current_job_active_count(), 2)
            # The exited handle grants no orphan/PID authority. The parent job owns cleanup.
        finally:
            close_retained_test_process(process)

    @unittest.skipUnless(os.name == "nt", "Windows failed-start containment harness")
    @job_owned_test
    def test_windows_failed_start_leaves_zero_observed_processes(self):
        self.assertTrue(process_ownership._windows_process_snapshot(), "Windows process inspection required")
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        process = None
        try:
            command = owned_powershell_child("Start-Sleep -Seconds 120") + "$child.WaitForExit()"
            process = subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                **runner_control.background_process_kwargs())
            observed = process_ownership.observe_process_tree(process.pid,
                generation="generation-failed-start", revision="revision-1", startup_nonce="nonce-failed-start",
                expected_script="", expected_root_executable=str(powershell),
                process_role_prefix="supervisor", timeout_seconds=10)
            self.assertTrue(observed["success"], observed)
            tree = observed["tree"]
            containment = runner_control._contain_spawned_process(process, tree)
            self.assertTrue(containment["success"], containment)
            for member in tree.get("members") or []:
                current = runner_control.inspect_process(member.get("pid"))
                self.assertFalse(isinstance(current, dict) and current.get("creation_time") == member["creation_time"], member)
        finally:
            close_retained_test_process(process)

    @unittest.skipUnless(os.name == "nt", "Windows governed lifecycle harness")
    @job_owned_test
    def test_windows_governed_start_refuses_protected_ancestry_stop(self):
        self.assertTrue(process_ownership._windows_process_snapshot(), "Windows process inspection required")
        powershell = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        )
        original_observe = runner_control.observe_process_tree
        publisher_threads = []
        publisher_failures = []
        publisher_stop = threading.Event()
        captured_processes = []

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
                excluded_pids = set()
                if runner_pid_path.exists():
                    excluded_pids.add(
                        int(runner_pid_path.read_text(encoding="utf-8"))
                    )
                    changed = True
                    while changed:
                        changed = False
                        for item in tree["members"]:
                            if (
                                int(item.get("parent_pid") or -1)
                                in excluded_pids
                                and int(item.get("pid") or -1)
                                not in excluded_pids
                            ):
                                excluded_pids.add(
                                    int(item.get("pid") or -1)
                                )
                                changed = True
                members = [
                    item for item in tree["members"]
                    if int(item.get("pid") or -1) not in excluded_pids
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
                def publish_runner_ready():
                    try:
                        deadline = time.monotonic() + 30
                        packet = {}
                        while time.monotonic() <= deadline and not publisher_stop.is_set():
                            packet = runner_control._read_json(
                                runner_control.SUPERVISOR_PATH
                            )
                            if packet.get("controller_acknowledgement"):
                                break
                            time.sleep(0.05)
                        runner_nonce = "windows-harness-runner-nonce"
                        deadline = time.monotonic() + 30
                        while (
                            not runner_pid_path.exists()
                            and time.monotonic() <= deadline and not publisher_stop.is_set()
                        ):
                            time.sleep(0.05)
                        if publisher_stop.is_set():
                            return
                        if not runner_pid_path.exists():
                            publisher_failures.append("runner_pid_not_published")
                            return
                        runner_pid = int(
                            runner_pid_path.read_text(encoding="utf-8")
                        )
                        runner_observation = original_observe(
                        runner_pid,
                        generation=generation,
                        revision=revision,
                        startup_nonce=runner_nonce,
                        expected_script="",
                        expected_root_executable=str(powershell),
                        expected_root_parent_pid=root_pid,
                        process_role_prefix="runner",
                        timeout_seconds=10,
                        )
                        if not runner_observation.get("success"):
                            publisher_failures.append(
                                str(runner_observation)
                            )
                            return
                        runner_tree = runner_observation["tree"]
                        runner_members = list(runner_tree["members"])
                        runner_tree = process_ownership.make_process_tree_record(
                            runner_tree["root"], runner_members, generation
                        )
                        runner_identity = runner_tree["members"][-1]
                        packet.update({
                        "status": "running",
                        "runner_state": "running",
                        "child_pid": runner_pid,
                        "child_identity": runner_tree["root"],
                        "process_tree_identity": runner_tree,
                        "runner_startup_nonce": runner_nonce,
                        "runner_controller_acknowledgement": {
                            "generation": generation,
                            "startup_nonce": runner_nonce,
                            "revision": revision,
                            "runner_tree_digest": (
                                process_ownership.process_tree_identity_digest(
                                    runner_tree
                                )
                            ),
                        },
                        })
                        runner_control.atomic_write_json(
                            runner_control.SUPERVISOR_PATH, packet
                        )
                        runner_control.atomic_write_json(
                            runner_control.HEARTBEAT_PATH,
                            {
                            "last_result_status": "ownership_ready",
                            "supervisor_generation": generation,
                            "runner_source_commit": revision,
                            "startup_nonce": runner_nonce,
                            "pid": runner_identity["pid"],
                            "process_identity": runner_identity,
                            },
                        )
                    except Exception as exc:
                        publisher_failures.append(repr(exc))
                publisher = threading.Thread(
                    target=publish_runner_ready, daemon=True
                )
                publisher.start()
                publisher_threads.append(publisher)
            return result

        original_wait_for_ack = runner_control._wait_for_supervisor_ack
        with tempfile.TemporaryDirectory() as tmp:
            stop_path = Path(tmp) / "supervisor.stop"
            runner_pid_path = Path(tmp) / "runner.pid"
            quoted_stop = str(stop_path).replace("'", "''")
            quoted_runner_pid = str(runner_pid_path).replace("'", "''")
            helper_script = (
                "$deadline=[DateTime]::UtcNow.AddSeconds(120);"
                f"while (!(Test-Path -LiteralPath '{quoted_stop}') -and [DateTime]::UtcNow -lt $deadline) "
                "{ Start-Sleep -Milliseconds 100 }"
            )
            runner_script = owned_powershell_child("Start-Sleep -Seconds 120") + "$child.WaitForExit()"
            supervisor_command = (owned_powershell_child(helper_script, "s")
                + owned_powershell_child(runner_script, "r")
                + f"Set-Content -LiteralPath '{quoted_runner_pid}' -Value $r.Id;"
                + "$s.WaitForExit()")
            real_popen = subprocess.Popen
            expected_command = [str(powershell), "-NoProfile", "-NonInteractive", "-Command", supervisor_command]
            def capture_supervisor(command, *args, **kwargs):
                process = real_popen(command, *args, **kwargs)
                if command == expected_command:
                    captured_processes.append(process)
                return process
            with patch.dict(os.environ, {
                "CHARLIE_TEST_ISOLATION": "0",
                process_ownership.TERMINATION_ENABLE_ENV:
                    process_ownership.TERMINATION_ENABLE_VALUE,
            }, clear=False), patch.object(
                runner_control, "RUNNER_DIR", Path(tmp)
            ), patch.object(
                runner_control, "LOG_PATH", Path(tmp) / "runner.log"
            ), patch.object(
                runner_control, "SUPERVISOR_PATH", Path(tmp) / "supervisor.json"
            ), patch.object(
                runner_control, "HEARTBEAT_PATH", Path(tmp) / "runner.json"
            ), patch.object(
                runner_control, "SUPERVISOR_STOP_PATH", stop_path
            ), patch.object(
                runner_control, "SUPERVISOR_COMMAND",
                [
                    str(powershell), "-NoProfile", "-NonInteractive", "-Command",
                    supervisor_command,
                ],
            ), patch.object(
                runner_control, "runner_status",
                return_value={
                    "active": False,
                    "status": "runner_not_started",
                    "orphan_processes": [],
                },
            ), patch.object(
                runner_control, "_current_git_commit", return_value="revision-1"
            ), patch.object(
                runner_control, "observe_process_tree", side_effect=observe
            ), patch.object(
                runner_control,
                "_wait_for_supervisor_ack",
                side_effect=lambda *args, **kwargs: original_wait_for_ack(
                    *args, **{**kwargs, "timeout_seconds": 90}
                ),
            ), patch.object(runner_control.subprocess, "Popen", side_effect=capture_supervisor):
                try:
                    started, start_status = runner_control.start_runner()
                    self.assertEqual(
                        start_status, 200,
                        {"start": started, "publisher_failures": publisher_failures},
                    )
                    # Production ancestry guards remain intact. This controller cannot
                    # authorize independent stop of its own descendant runner tree.
                    stopped, stop_status = runner_control.stop_runner()
                    self.assertEqual(stop_status, 409, stopped)
                    self.assertEqual(stopped["status"], "runner_process_ownership_not_proven")
                    self.assertEqual(stopped["reason"], "current_process_ancestry")
                    self.assertTrue(runner_control.SUPERVISOR_STOP_PATH.exists())
                finally:
                    publisher_stop.set()
                    stop_path.write_text("disposable test cleanup", encoding="utf-8")
                    for publisher in publisher_threads:
                        publisher.join(timeout=12)
                    for process in captured_processes:
                        close_retained_test_process(process)
                    self.assertFalse(any(publisher.is_alive() for publisher in publisher_threads), "test publisher did not stop")
                    # Exact outer job cleanup also covers orphan descendants on every failure.

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

    def test_stop_marker_appearing_at_spawn_boundary_prevents_process_creation(self):
        marker = Mock()
        marker.exists.side_effect = [False, False, True]
        marker.__str__ = Mock(return_value="supervisor.stop")
        with patch.object(
            runner_control, "SUPERVISOR_STOP_PATH", marker
        ), patch.object(
            runner_control, "_read_json", return_value={}
        ), patch.object(
            runner_control, "runner_status",
            return_value={"active": False, "orphan_processes": []},
        ), patch.object(
            runner_control, "process_termination_enabled", return_value=True
        ), patch.object(
            runner_control, "_current_git_commit", return_value="revision-1"
        ), patch.object(runner_control.subprocess, "Popen") as popen:
            result, status = runner_control.start_runner()
        self.assertEqual(status, 423)
        self.assertEqual(result["status"], "governed_stop_active")
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
        private_key, public_key = (
            process_ownership.generate_controller_signing_key()
        )
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
                "runner_tree_digest": (
                    process_ownership.process_tree_identity_digest(runner_tree)
                ),
            },
            "controller_public_key": public_key,
        }
        heartbeat = {
            "last_result_status": "ownership_ready",
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
                controller_private_key=private_key,
                controller_public_key=public_key,
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
        process.poll.side_effect = lambda: 1 if process.wait.called else None
        with patch.object(
            runner_control, "_contain_observed_tree",
            return_value={"success": False, "reason": "ownership_identity_incomplete"},
        ), patch.object(
            runner_control, "inspect_descendant_processes", return_value=[]
        ), patch.object(
            runner_control.subprocess, "run", return_value=Mock(returncode=0)
        ):
            result = runner_control._contain_spawned_process(process, {})
        self.assertTrue(result["success"])
        self.assertEqual(
            result["reason"], "fresh_spawn_handle_tree_termination_verified"
        )
        process.wait.assert_called()

    def test_exited_launcher_does_not_authorize_descendant_pid_termination(self):
        process = Mock(pid=4321)
        process.poll.return_value = 1
        with patch.object(
            runner_control,
            "_contain_observed_tree",
            return_value={"success": False, "reason": "partial_observation"},
        ), patch.object(
            runner_control,
            "inspect_descendant_processes",
        ) as descendants, patch.object(
            runner_control,
            "inspect_process",
        ) as inspect, patch.object(
            runner_control.subprocess, "run"
        ) as terminate:
            result = runner_control._contain_spawned_process(process, {})

        self.assertTrue(result["success"])
        self.assertEqual(result["reason"], "spawned_process_handle_already_exited")
        self.assertNotIn("descendant_pids", result)
        descendants.assert_not_called()
        inspect.assert_not_called()
        terminate.assert_not_called()

    def test_spawned_descendant_identity_change_fails_closed_before_termination(self):
        process = Mock(pid=4321)
        process.poll.return_value = None
        captured = {
            "pid": 4322,
            "parent_pid": 4321,
            "creation_time": "child-created",
            "executable_path": "C:/venv/python.exe",
            "command_line": "python child.py",
            "name": "python.exe",
        }
        baseline = {
            **captured,
            "ancestry": [
                {"pid": 4321, "name": "python.exe", "command_line": "python parent.py"},
                {"pid": os.getpid(), "name": "python.exe", "command_line": "python test.py"},
            ],
            "current_process_ancestry": [{"pid": os.getpid()}],
            "inspection_complete": True,
        }
        mutations = {
            "pid": 9999,
            "parent_pid": 9999,
            "creation_time": "reused-created",
            "executable_path": "C:/other/python.exe",
            "command_line": "python substituted.py",
        }
        for field, value in mutations.items():
            with self.subTest(field=field), patch.object(
                runner_control,
                "_contain_observed_tree",
                return_value={"success": False, "reason": "partial_observation"},
            ), patch.object(
                runner_control,
                "inspect_descendant_processes",
                return_value=[captured],
            ), patch.object(
                runner_control,
                "inspect_process",
                return_value={**baseline, field: value},
            ), patch.object(runner_control.subprocess, "run") as terminate:
                result = runner_control._contain_spawned_process(process, {})

            self.assertFalse(result["success"])
            self.assertTrue(result["reason"].startswith(
                "spawned_descendant_identity_unverified:4322:"
            ))
            self.assertNotIn("descendant_pids", result)
            terminate.assert_not_called()

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
        self.assertFalse(result["success"])
        self.assertEqual(
            result["reason"], "controller_observed_supervisor_identity_required"
        )
        self.assertEqual(persisted["supervisor_identity"], {})
        self.assertEqual(persisted["generation"], "generation-1")
        stop_tree.assert_not_called()
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
                "reason": "bounded diagnostic reason",
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
        self.assertEqual(result["reason"], "bounded diagnostic reason")

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

    def test_heartbeat_retains_shadow_cycle_and_next_eligible_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "runner.json"
            shadow = {
                "success": True,
                "status": "shadow_feedback_waiting",
                "processed_count": 0,
                "next_eligible_event": "control_tower_feedback_recorded",
            }

            first = runner_control.write_runner_heartbeat({
                "status": "shadow_observation_cycle",
                "shadow": shadow,
                "checks": 3,
                "next_eligible_event": "control_tower_feedback_recorded",
                "mission_pickup_attempted": False,
                "release_attempted": False,
            }, heartbeat)
            second = runner_control.write_runner_heartbeat({
                "status": "observe_only_ready",
            }, heartbeat)

        self.assertEqual(first["shadow"], shadow)
        self.assertEqual(second["shadow"], shadow)
        self.assertEqual(second["checks"], 3)
        self.assertEqual(second["next_eligible_event"], "control_tower_feedback_recorded")
        self.assertFalse(second["mission_pickup_attempted"])
        self.assertFalse(second["release_attempted"])

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

    @patch("modules.charlie.runner_control._validate_tree_termination_authority")
    @patch("modules.charlie.runner_control._stop_process_tree")
    @patch("modules.charlie.runner_control.validate_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_stop_uses_launcher_tree_and_persists_evidence(
        self, status, _disabled, _enabled, validate_tree, stop_tree, authority
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
        authority.return_value = {
            "authorized": True, "reason": "controller_signed_exact_process_tree"
        }

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

    @patch("modules.charlie.runner_control._validate_tree_termination_authority")
    @patch("modules.charlie.runner_control._stop_process_tree")
    @patch("modules.charlie.runner_control.validate_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_stop_handles_current_supervisor_before_runner_spawn(
        self, status, _disabled, _enabled, validate_tree, stop_tree, authority
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
        authority.return_value = {
            "authorized": True, "reason": "controller_signed_exact_process_tree"
        }
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

    @patch("modules.charlie.runner_control._validate_tree_termination_authority")
    @patch("modules.charlie.runner_control.validate_process_tree")
    @patch("modules.charlie.runner_control.process_termination_enabled", return_value=True)
    @patch("modules.charlie.runner_control.emergency_process_cleanup_disabled", return_value=False)
    @patch("modules.charlie.runner_control.runner_status")
    def test_governed_stop_returns_and_persists_exact_tree_rejection(
        self, status, _disabled, _enabled, validate_tree, authority
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
        authority.return_value = {
            "authorized": True, "reason": "controller_signed_exact_process_tree"
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


class WindowsHarnessBoundaryTests(unittest.TestCase):
    """No native calls: qualification of the hosted test containment decisions."""
    def test_exited_launcher_creates_only_job_inheriting_child_then_exits(self):
        from tests import charlie_windows_lifecycle_harness as harness
        command = harness.exited_launcher_command()
        self.assertEqual(command[:4], [harness.sys.executable, "-I", "-S", "-c"])
        events = []
        class LauncherExited(Exception): pass
        def leave(code):
            events.append(("exit", code))
            raise LauncherExited()
        fake_process = SimpleNamespace(DEVNULL=-3, CREATE_NO_WINDOW=0x08000000,
            Popen=Mock(side_effect=lambda *args, **kwargs: events.append(("spawn", args, kwargs))))
        modules = {"os": SimpleNamespace(_exit=leave), "subprocess": fake_process,
            "sys": SimpleNamespace(executable="synthetic-python.exe")}
        def fake_import(name, *_args, **_kwargs): return modules[name]
        with self.assertRaises(LauncherExited):
            exec(compile(command[4], "<exited-launcher-fixture>", "exec"),
                {"__builtins__": {"__import__": fake_import, "getattr": getattr}})
        self.assertEqual([event[0] for event in events], ["spawn", "exit"])
        self.assertEqual(events[-1], ("exit", 0))
        self.assertEqual(events[0][1], (["synthetic-python.exe", "-I", "-S", "-c", "import time; time.sleep(120)"],))
        self.assertEqual(events[0][2], {"stdin": -3, "stdout": -3, "stderr": -3,
            "close_fds": True, "creationflags": 0x08000000})
        self.assertFalse(events[0][2]["creationflags"] & 0x01000000)  # no CREATE_BREAKAWAY_FROM_JOB

    def test_exited_launcher_does_not_claim_success_if_child_creation_fails(self):
        from tests import charlie_windows_lifecycle_harness as harness
        leave = Mock()
        modules = {"os": SimpleNamespace(_exit=leave),
            "subprocess": SimpleNamespace(DEVNULL=-3, Popen=Mock(side_effect=OSError("synthetic"))),
            "sys": SimpleNamespace(executable="synthetic-python.exe")}
        def fake_import(name, *_args, **_kwargs): return modules[name]
        with self.assertRaises(OSError):
            exec(compile(harness.exited_launcher_command()[4], "<exited-launcher-fixture>", "exec"),
                {"__builtins__": {"__import__": fake_import, "getattr": getattr}})
        leave.assert_not_called()

    def test_worker_environment_allows_only_platform_inputs_and_fixed_test_controls(self):
        from tests import charlie_windows_lifecycle_harness as harness
        source = {"SystemRoot": "C:/Windows", "PATH": "synthetic-path", "PSModulePath": "untrusted-user-module-path",
            "USERPROFILE": "C:/Users/runner", "APPDATA": "C:/Users/runner/AppData/Roaming",
            "LOCALAPPDATA": "C:/Users/runner/AppData/Local", "PROGRAMDATA": "C:/ProgramData",
            "SYSTEMDRIVE": "C:", "PROGRAMFILES": "C:/Program Files", "OPENAI_API_KEY": "secret",
            "GH_TOKEN": "secret", "DATABASE_URL": "secret", "PYTHONPATH": "untrusted", "TEMP": "outside"}
        result = harness.worker_environment(source, Path("case-root"), "test-job")
        self.assertEqual(set(result), {"SystemRoot", "PATH", *harness.NATIVE_PLATFORM_ENV, "PSModulePath",
            harness.JOB_ENV, "TEMP", "TMP", "PYTHONDONTWRITEBYTECODE", "PYTHON_DOTENV_DISABLED", "DATABASE_URL"})
        self.assertEqual(result["PSModulePath"], "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\Modules")
        self.assertEqual(result["TEMP"], str(Path("case-root")))
        self.assertEqual(result["TMP"], str(Path("case-root")))
        self.assertEqual(result["DATABASE_URL"], "")
        self.assertNotIn("secret", json.dumps(result))
        with self.assertRaisesRegex(RuntimeError, "system_root_required"):
            harness.worker_environment({}, Path("case-root"), "test-job")

    def test_snapshot_comparison_runs_identical_inspector_without_logging_process_details(self):
        from tests import charlie_windows_lifecycle_harness as harness
        current = {"SYSTEMROOT": "C:/Windows", "USERPROFILE": "synthetic-profile", "PSMODULEPATH": "system-modules", harness.JOB_ENV: "same-owned-job"}
        calls = []
        def inspect():
            calls.append(dict(os.environ))
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(["private-command-not-for-report"], 8, output="private-process-output")
            return [{"command_line": "private-process-details"}]
        with patch.dict(os.environ, current, clear=True):
            result = harness.compare_snapshot_environments(inspect)
            self.assertEqual(dict(os.environ), current)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("USERPROFILE", calls[0]); self.assertNotIn("PSMODULEPATH", calls[0])
        self.assertEqual(calls[0][harness.JOB_ENV], "same-owned-job")
        self.assertEqual(calls[1], current)
        self.assertEqual(result["legacy_sanitized"]["error_type"], "TimeoutExpired")
        self.assertFalse(result["legacy_sanitized"]["success"])
        self.assertTrue(result["minimal_platform"]["success"])
        self.assertEqual(result["minimal_platform"]["row_count"], 1)
        self.assertNotIn("private-", json.dumps(result))

    def test_snapshot_comparison_preserves_corrected_failure_and_restores_environment(self):
        from tests import charlie_windows_lifecycle_harness as harness
        current = {"SYSTEMROOT": "C:/Windows", "APPDATA": "synthetic"}
        inspect = Mock(side_effect=OSError("sensitive details"))
        with patch.dict(os.environ, current, clear=True):
            result = harness.compare_snapshot_environments(inspect)
            self.assertEqual(dict(os.environ), current)
        self.assertEqual(inspect.call_count, 2)
        for item in result.values():
            self.assertFalse(item["success"])
            self.assertEqual(item["error_type"], "OSError")
            self.assertEqual(item["row_count"], 0)
        self.assertNotIn("sensitive", json.dumps(result))

    def fake_api(self):
        api = Mock()
        api.CreateJobObjectW.return_value = 10
        api.OpenJobObjectW.return_value = 10
        api.GetCurrentProcess.return_value = 20
        api.OpenProcess.return_value = 30
        api.AssignProcessToJobObject.return_value = 1
        api.TerminateJobObject.return_value = 1
        api.TerminateProcess.return_value = 1
        api.WaitForSingleObject.return_value = 0
        api.ResumeThread.return_value = 1
        def query(_job, kind, pointer, _size, _returned):
            if kind == 9:
                pointer._obj.basic.flags = 0x2000
            else:
                pointer._obj.active = 0
            return 1
        api.QueryInformationJobObject.side_effect = query
        def membership(_process, _job, present):
            present._obj.value = True
            return 1
        api.IsProcessInJob.side_effect = membership
        def exit_code(_process, code):
            code._obj.value = 0
            return 1
        api.GetExitCodeProcess.side_effect = exit_code
        return api
    def test_guard_refuses_missing_job_before_native_access(self):
        from tests import charlie_windows_lifecycle_harness as harness
        with patch.dict(os.environ, {harness.JOB_ENV:""}),patch.object(harness,"_kernel") as kernel:
            with self.assertRaisesRegex(RuntimeError,"explicit_windows_test_job_required"):
                with harness.windows_job_guard(): pass
            kernel.assert_not_called()
    def test_guard_refuses_breakaway_missing_kill_limit_or_wrong_membership(self):
        from tests import charlie_windows_lifecycle_harness as harness
        for flags, member in ((0,True),(0x2000|0x800,True),(0x2000|0x1000,True),(0x2000,False)):
            with self.subTest(flags=flags,member=member):
                api=self.fake_api()
                def query(_job,_kind,pointer,_size,_returned):
                    pointer._obj.basic.flags=flags
                    return 1
                def membership(_process,_job,present):
                    present._obj.value=member
                    return 1
                api.QueryInformationJobObject.side_effect=query
                api.IsProcessInJob.side_effect=membership
                with patch.object(harness,"_kernel",return_value=api),patch.dict(os.environ,{harness.JOB_ENV:"charlie-test-"+"a"*32}):
                    with self.assertRaisesRegex(RuntimeError,"ownership_or_limits_invalid"):
                        with harness.windows_job_guard(): self.fail("guard yielded")
                api.CloseHandle.assert_called_once_with(10)
    def test_taskkill_requires_live_membership_and_retains_handle_during_call(self):
        from tests import charlie_windows_lifecycle_harness as harness
        api = self.fake_api(); calls=[]
        def run(command, **_kwargs):
            self.assertNotIn(unittest.mock.call(30),api.CloseHandle.call_args_list)
            calls.append(command)
        with patch.object(harness,"_kernel",return_value=api),patch.object(harness.subprocess,"run",side_effect=run), \
             patch.dict(os.environ,{harness.JOB_ENV:"charlie-test-"+"a"*32}):
            with harness.windows_job_guard():
                subprocess.run(["taskkill","/PID","123","/T","/F"])
                def outside(_process,_job,present):
                    present._obj.value=False
                    return 1
                api.IsProcessInJob.side_effect=outside
                with self.assertRaisesRegex(RuntimeError,"outside_test_job"):
                    subprocess.run(["taskkill","/PID","456","/T","/F"])
            self.assertEqual(len(calls),1)
            self.assertEqual(api.CloseHandle.call_args_list.count(unittest.mock.call(30)),2)
    def test_suspended_worker_assigned_before_resume_and_cleanup_always_verified(self):
        from tests import charlie_windows_lifecycle_harness as harness
        api=self.fake_api(); order=[]
        api.AssignProcessToJobObject.side_effect=lambda *args: order.append("assign") or 1
        api.ResumeThread.side_effect=lambda *args: order.append("resume") or 1
        native=SimpleNamespace(CreateProcess=Mock(return_value=(40,41,123,124)))
        with tempfile.TemporaryDirectory() as tmp,patch.object(harness,"_kernel",return_value=api), \
             patch.dict("sys.modules",{"_winapi":native}), \
             patch.object(harness.subprocess,"STARTUPINFO",return_value=SimpleNamespace(),create=True), \
             patch.dict(harness.os.environ,{"SystemRoot":"C:/Windows"}), \
             patch.object(harness.ctypes,"get_last_error",return_value=0,create=True):
            root=Path(tmp)
            (root/"result.json").write_text(json.dumps({"tests_run":1,"failures":0,"errors":0,"skips":0}))
            result=harness._run_owned_worker(harness.SELECTORS[0],root)
            self.assertEqual(order,["assign","resume"])
            self.assertTrue(native.CreateProcess.call_args.args[5] & 4)
            self.assertFalse(native.CreateProcess.call_args.args[4])
            self.assertTrue(result["cleanup_verified"])
            api.TerminateJobObject.assert_called_once_with(10,1)
            self.assertEqual(set(c.args[0] for c in api.CloseHandle.call_args_list),{10,40,41})
    def test_assignment_failure_never_resumes_or_claims_unverified_cleanup(self):
        from tests import charlie_windows_lifecycle_harness as harness
        api=self.fake_api();api.AssignProcessToJobObject.return_value=0;api.TerminateProcess.return_value=0
        native=SimpleNamespace(CreateProcess=Mock(return_value=(40,41,123,124)))
        with tempfile.TemporaryDirectory() as tmp,patch.object(harness,"_kernel",return_value=api), \
             patch.dict("sys.modules",{"_winapi":native}), \
             patch.object(harness.subprocess,"STARTUPINFO",return_value=SimpleNamespace(),create=True), \
             patch.dict(harness.os.environ,{"SystemRoot":"C:/Windows"}), \
             patch.object(harness.ctypes,"get_last_error",return_value=5,create=True):
            result=harness._run_owned_worker(harness.SELECTORS[0],Path(tmp))
        self.assertFalse(result["cleanup_verified"])
        api.ResumeThread.assert_not_called()
        api.TerminateProcess.assert_called_once_with(40,1)
    def test_timeout_empties_exact_owned_job_and_records_failure(self):
        from tests import charlie_windows_lifecycle_harness as harness
        api=self.fake_api();api.WaitForSingleObject.return_value=258
        native=SimpleNamespace(CreateProcess=Mock(return_value=(40,41,123,124)))
        with tempfile.TemporaryDirectory() as tmp,patch.object(harness,"_kernel",return_value=api), \
             patch.dict("sys.modules",{"_winapi":native}), \
             patch.object(harness.subprocess,"STARTUPINFO",return_value=SimpleNamespace(),create=True), \
             patch.dict(harness.os.environ,{"SystemRoot":"C:/Windows"}), \
             patch.object(harness.ctypes,"get_last_error",return_value=0,create=True):
            result=harness._run_owned_worker(harness.SELECTORS[0],Path(tmp))
        self.assertTrue(result["timed_out"])
        self.assertTrue(result["cleanup_verified"])
        self.assertNotIn("exit_code",result)
        api.WaitForSingleObject.assert_called_once_with(40,180000)
        api.TerminateJobObject.assert_called_once_with(10,1)


if __name__ == "__main__":
    unittest.main()
