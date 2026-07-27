import os
import subprocess
import json
import unittest
from unittest.mock import Mock, patch

from modules.charlie import execution_bridge, process_ownership, runner_control
from scripts import charlie_runner_supervisor


class CharlieProcessOwnershipTests(unittest.TestCase):
    def test_process_tree_digest_binds_creation_command_parentage_and_role(self):
        member = {
            "pid": 100,
            "parent_pid": 50,
            "creation_time": "created-1",
            "executable_path": "C:/Python/python.exe",
            "command_fingerprint": "command-1",
            "runner_generation": "generation-1",
            "mission_id": "charlie-control",
            "execution_id": "generation-1",
            "ownership_type": "charlie_runner",
            "revision": "revision-1",
            "startup_nonce": "nonce-1",
            "process_role": "supervisor_launcher",
        }
        tree = successful = {
            "version": "charlie_process_tree_v1",
            "runner_generation": "generation-1",
            "root_pid": 100,
            "root": dict(member),
            "members": [dict(member)],
        }
        original = process_ownership.process_tree_identity_digest(tree)
        for field, replacement in {
            "creation_time": "created-2",
            "executable_path": "C:/Other/python.exe",
            "command_fingerprint": "command-2",
            "parent_pid": 51,
            "process_role": "runner_launcher",
        }.items():
            changed = json.loads(json.dumps(successful))
            changed["members"][0][field] = replacement
            self.assertNotEqual(
                original,
                process_ownership.process_tree_identity_digest(changed),
                field,
            )
            root_changed = json.loads(json.dumps(successful))
            root_changed["root"][field] = replacement
            self.assertNotEqual(
                original,
                process_ownership.process_tree_identity_digest(root_changed),
                f"root:{field}",
            )

    def test_controller_signature_rejects_child_forgery_and_replay_changes(self):
        private_key, public_key = process_ownership.generate_controller_signing_key()
        acknowledgement = {
            "generation": "generation-1",
            "revision": "revision-1",
            "startup_nonce": "nonce-1",
            "member_pids": [100, 101],
        }
        signature = process_ownership.sign_controller_acknowledgement(
            acknowledgement, private_key
        )
        self.assertTrue(process_ownership.verify_controller_acknowledgement(
            acknowledgement, signature, public_key
        ))
        self.assertFalse(process_ownership.verify_controller_acknowledgement(
            {**acknowledgement, "generation": "generation-2"},
            signature,
            public_key,
        ))

    def test_structurally_present_empty_tree_fails_with_exact_field(self):
        tree = {
            "version": "charlie_process_tree_v1",
            "root": {"pid": None},
            "members": [{"pid": None}],
        }
        result = process_ownership.validate_bootstrap_tree(
            tree,
            generation="generation-1",
            revision="revision-1",
            startup_nonce="nonce-1",
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "ownership_identity_incomplete:root.pid")

    def test_live_revalidation_rejects_pid_reuse_creation_identity(self):
        root = process_ownership.make_ownership_record(
            {
                "pid": 100,
                "parent_pid": 50,
                "creation_time": "original",
                "executable_path": "C:/Python/python.exe",
                "command_line": "python supervisor.py",
            },
            "generation-1", "charlie-control", "generation-1", "charlie_runner",
            revision="revision-1", startup_nonce="nonce-1",
        )
        interpreter = {
            **root,
            "pid": 101,
            "parent_pid": 100,
            "creation_time": "interpreter",
        }
        tree = process_ownership.make_process_tree_record(
            root, [root, interpreter], "generation-1"
        )

        def inspect(pid):
            record = root if int(pid) == 100 else interpreter
            return {
                "pid": record["pid"],
                "parent_pid": record["parent_pid"],
                "creation_time": "reused" if int(pid) == 100 else record["creation_time"],
                "executable_path": record["executable_path"],
                "command_line": "python supervisor.py",
                "ancestry": [] if int(pid) == 100 else [{"pid": 100}],
                "inspection_complete": True,
            }

        with patch.object(process_ownership, "inspect_process", side_effect=inspect):
            result = process_ownership.validate_live_bootstrap_tree(
                tree,
                generation="generation-1",
                revision="revision-1",
                startup_nonce="nonce-1",
            )
        self.assertFalse(result["authorized"])
        self.assertEqual(
            result["reason"],
            "live_identity_creation_time_mismatch:member_0",
        )

    @unittest.skipUnless(os.name == "nt", "Windows launcher/interpreter harness")
    def test_external_controller_observes_real_windows_launcher_interpreter_tree(self):
        child = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$p=Start-Process powershell.exe -ArgumentList "
                "'-NoProfile','-NonInteractive','-Command','Start-Sleep -Seconds 30' "
                "-PassThru -WindowStyle Hidden; Wait-Process -Id $p.Id",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            result = process_ownership.observe_process_tree(
                child.pid,
                generation="generation-1",
                revision="revision-1",
                startup_nonce="nonce-1",
                timeout_seconds=10,
            )
            if not result["success"] and not process_ownership._windows_process_snapshot():
                self.skipTest("Windows process inspection is unavailable to this session")
            self.assertTrue(result["success"], result)
            self.assertGreaterEqual(len(result["tree"]["members"]), 2)
            self.assertEqual(result["tree"]["root"]["parent_pid"], os.getpid())
            self.assertTrue(all(item.get("executable_path") for item in result["tree"]["members"]))
            self.assertTrue(all(item.get("command_fingerprint") for item in result["tree"]["members"]))
            with patch.dict(os.environ, {
                process_ownership.TERMINATION_ENABLE_ENV:
                    process_ownership.TERMINATION_ENABLE_VALUE,
                process_ownership.TEST_ISOLATION_ENV: "0",
            }, clear=False):
                contained = runner_control._contain_observed_tree(result["tree"])
            self.assertTrue(contained["success"], contained)
            child.wait(timeout=10)
            self.assertIsNotNone(child.returncode)
        finally:
            if child.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
    def setUp(self):
        self.live = {
            "pid": 222, "creation_time": "20260719170000.000000+120", "executable_path": "C:/Python/python.exe",
            "command_line": "python worker.py --noninteractive", "parent_pid": 111, "name": "python.exe",
            "ancestry": [{"pid": 111, "name": "python.exe", "command_line": "python supervisor.py -NonInteractive"}],
            "current_process_ancestry": [{"pid": 900, "name": "codex.exe"}],
        }
        self.expected = {"runner_generation": "gen-1", "mission_id": "mission-1", "execution_id": "exec-1", "ownership_type": "charlie_worker"}
        self.record = process_ownership.make_ownership_record(self.live, **self.expected)

    def validate(self, live=None, record=None, expected=None, inspector=None):
        chosen = self.live if live is None else live
        return process_ownership.validate_termination(
            self.record if record is None else record,
            self.expected if expected is None else expected,
            inspector or (lambda _pid: chosen), current_pid=900,
        )

    def test_valid_disposable_charlie_worker_identity(self):
        self.assertTrue(self.validate()["authorized"])

    def test_stale_or_reused_pid(self):
        self.assertEqual(self.validate({**self.live, "pid": 223})["reason"], "pid_reused")

    def test_creation_time_mismatch(self):
        self.assertEqual(self.validate({**self.live, "creation_time": "new"})["reason"], "creation_time_mismatch")

    def test_executable_mismatch(self):
        self.assertEqual(self.validate({**self.live, "executable_path": "C:/bad.exe"})["reason"], "executable_mismatch")

    def test_command_mismatch(self):
        self.assertEqual(self.validate({**self.live, "command_line": "python other.py"})["reason"], "command_fingerprint_mismatch")

    def test_missing_identity_metadata(self):
        record = dict(self.record); record.pop("creation_time")
        self.assertEqual(self.validate(record=record)["reason"], "missing_identity_metadata")

    def test_corrupt_metadata(self):
        record = dict(self.record); record["pid"] = "broken"
        self.assertEqual(self.validate(record=record)["reason"], "corrupt_metadata")

    def test_runner_generation_mismatch(self):
        expected = {**self.expected, "runner_generation": "gen-2"}
        self.assertEqual(self.validate(expected=expected)["reason"], "runner_generation_mismatch")

    def test_mission_and_execution_mismatch(self):
        for field in ("mission_id", "execution_id"):
            with self.subTest(field=field):
                expected = {**self.expected, field: "different"}
                self.assertEqual(self.validate(expected=expected)["reason"], f"{field}_mismatch")

    def test_process_inspection_failure(self):
        self.assertEqual(self.validate(inspector=Mock(side_effect=OSError("denied")))["reason"], "process_inspection_failed")

    def test_partial_process_inspection_fails_closed(self):
        live = {**self.live, "inspection_complete": False}
        self.assertEqual(self.validate(live)["reason"], "process_inspection_failed")

    @patch.object(process_ownership, "_proc_ancestry")
    @patch.object(process_ownership, "_proc_row")
    def test_proc_inspection_returns_partial_evidence_for_inaccessible_ancestor(self, row, ancestry):
        row.return_value = {
            "pid": 222, "parent_pid": 111, "creation_time": "1", "executable_path": "/python",
            "command_line": "python worker.py", "name": "python", "row_complete": True,
        }
        ancestry.side_effect = [([{"pid": 111, "executable_path": ""}], False), ([], True)]
        result = process_ownership._inspect_proc(222)
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["ancestry"][0]["pid"], 111)

    @patch.object(process_ownership.os, "name", "posix")
    @patch.object(process_ownership, "_inspect_proc", side_effect=FileNotFoundError("exited"))
    def test_posix_process_exit_during_inspection_returns_no_identity(self, _inspect):
        self.assertIsNone(process_ownership.inspect_process(222))

    @patch.object(process_ownership.os, "name", "nt")
    @patch.object(process_ownership.subprocess, "run", side_effect=subprocess.TimeoutExpired(["powershell"], 8))
    def test_windows_target_inspection_timeout_returns_no_identity(self, _run):
        self.assertIsNone(process_ownership.inspect_process(222))

    @patch.object(process_ownership.os, "name", "nt")
    @patch.object(process_ownership, "_current_ancestry_windows", side_effect=subprocess.TimeoutExpired(["powershell"], 8))
    @patch.object(process_ownership.subprocess, "run")
    def test_windows_current_ancestry_timeout_returns_no_identity(self, run, _ancestry):
        run.return_value = Mock(returncode=0, stdout='{"pid":222,"parent_pid":111}', stderr="")
        self.assertIsNone(process_ownership.inspect_process(222))

    @patch.object(process_ownership.os, "name", "nt")
    @patch.object(process_ownership.subprocess, "run")
    def test_windows_invalid_inspection_json_returns_no_identity(self, run):
        run.return_value = Mock(returncode=0, stdout="not-json", stderr="")
        self.assertIsNone(process_ownership.inspect_process(222))

    def test_missing_pid_fails_closed(self):
        self.assertEqual(self.validate(live=False)["reason"], "pid_not_found")

    def test_cursor_target(self):
        self.assertEqual(self.validate({**self.live, "name": "Cursor.exe"})["reason"], "protected_process_boundary")

    def test_cursor_ancestor_boundary(self):
        live = {**self.live, "ancestry": [{"pid": 111, "name": "Cursor.exe"}]}
        self.assertEqual(self.validate(live)["reason"], "protected_process_boundary")

    def test_terminal_host_target(self):
        self.assertEqual(self.validate({**self.live, "name": "conhost.exe"})["reason"], "protected_process_boundary")

    def test_interactive_shell_target(self):
        live = {**self.live, "name": "powershell.exe", "executable_path": "C:/Windows/powershell.exe", "command_line": "powershell.exe"}
        record = process_ownership.make_ownership_record(live, **self.expected)
        self.assertEqual(self.validate(live, record=record)["reason"], "protected_process_boundary")

    def test_interactive_codex_target(self):
        live = {**self.live, "name": "codex.exe"}
        record = process_ownership.make_ownership_record(live, **self.expected)
        self.assertEqual(self.validate(live, record=record)["reason"], "protected_process_boundary")

    def test_current_process_ancestry(self):
        live = {**self.live, "ancestry": [{"pid": 900, "name": "python.exe"}]}
        self.assertEqual(self.validate(live)["reason"], "current_process_ancestry")

    def test_exact_fresh_child_can_be_contained_by_its_governed_starter(self):
        live = {**self.live, "ancestry": [{"pid": 900, "name": "python.exe"}]}
        result = process_ownership.validate_termination(
            self.record,
            self.expected,
            lambda _pid: live,
            current_pid=900,
            allow_current_descendant=True,
        )
        self.assertTrue(result["authorized"])

    def test_descendant_override_cannot_target_an_unrelated_process(self):
        result = process_ownership.validate_termination(
            self.record,
            self.expected,
            lambda _pid: self.live,
            current_pid=900,
            allow_current_descendant=True,
        )
        self.assertEqual(result["reason"], "not_current_process_descendant")

    def test_descendant_override_still_denies_protected_process_below_starter(self):
        live = {
            **self.live,
            "ancestry": [
                {"pid": 333, "name": "powershell.exe"},
                {"pid": 900, "name": "python.exe"},
            ],
        }
        result = process_ownership.validate_termination(
            self.record,
            self.expected,
            lambda _pid: live,
            current_pid=900,
            allow_current_descendant=True,
        )
        self.assertEqual(result["reason"], "protected_process_boundary")

    def test_windows_launcher_and_interpreter_form_one_valid_logical_tree(self):
        launcher = self.record
        interpreter_live = {
            **self.live,
            "pid": 333,
            "parent_pid": 222,
            "command_line": "python worker.py --noninteractive",
            "ancestry": [
                {"pid": 222, "name": "python.exe"},
                {"pid": 111, "name": "python.exe"},
            ],
        }
        interpreter = process_ownership.make_ownership_record(
            interpreter_live, **self.expected
        )
        tree = process_ownership.make_process_tree_record(
            launcher, [launcher, interpreter], "gen-1"
        )
        live = {222: self.live, 333: interpreter_live}

        result = process_ownership.validate_process_tree(
            tree,
            self.expected,
            lambda pid: live[pid],
            current_pid=900,
            require_descendant=True,
        )

        self.assertTrue(result["authorized"])
        self.assertEqual(result["member_pids"], [222, 333])

    def test_logical_tree_rejects_interpreter_outside_launcher_ancestry(self):
        unrelated_live = {
            **self.live,
            "pid": 333,
            "parent_pid": 777,
            "ancestry": [{"pid": 777, "name": "python.exe"}],
        }
        unrelated = process_ownership.make_ownership_record(
            unrelated_live, **self.expected
        )
        tree = process_ownership.make_process_tree_record(
            self.record, [self.record, unrelated], "gen-1"
        )
        live = {222: self.live, 333: unrelated_live}

        result = process_ownership.validate_process_tree(
            tree, self.expected, lambda pid: live[pid], current_pid=900
        )

        self.assertEqual(result["reason"], "member_333_not_descendant_of_root")

    def test_logical_tree_preserves_exact_member_mismatch_reason(self):
        interpreter_live = {
            **self.live,
            "pid": 333,
            "parent_pid": 222,
            "ancestry": [{"pid": 222, "name": "python.exe"}],
        }
        interpreter = process_ownership.make_ownership_record(
            interpreter_live, **self.expected
        )
        tree = process_ownership.make_process_tree_record(
            self.record, [self.record, interpreter], "gen-1"
        )
        changed = {**interpreter_live, "command_line": "python unrelated.py"}
        live = {222: self.live, 333: changed}

        result = process_ownership.validate_process_tree(
            tree, self.expected, lambda pid: live[pid], current_pid=900
        )

        self.assertEqual(
            result["reason"],
            "member_333_command_fingerprint_mismatch",
        )

    @patch.object(execution_bridge, "emergency_process_cleanup_disabled", return_value=True)
    @patch.object(execution_bridge, "record_emergency_cleanup_refusal", return_value={"status": "emergency_process_cleanup_disabled"})
    @patch.object(execution_bridge.os, "killpg", create=True)
    @patch.object(execution_bridge.os, "kill")
    @patch.object(execution_bridge.subprocess, "run")
    def test_emergency_containment_overrides_valid_execution_ownership(
        self, run, kill, killpg, _record, _disabled
    ):
        result = execution_bridge._terminate_process_tree(self.record, self.expected, lambda _pid: self.live)
        self.assertEqual(result["status"], "emergency_process_cleanup_disabled")
        run.assert_not_called()
        kill.assert_not_called()
        killpg.assert_not_called()

    @patch.object(runner_control, "emergency_process_cleanup_disabled", return_value=False)
    @patch.object(runner_control, "process_termination_enabled", return_value=True)
    @patch.object(runner_control.os, "kill")
    @patch.object(runner_control.subprocess, "run")
    def test_runner_control_validates_complete_identity_before_kill(self, run, kill, _enabled, _disabled):
        with patch.object(runner_control.os, "name", "nt"):
            result = runner_control._stop_process_tree(self.record, self.expected, lambda _pid: self.live)
        self.assertTrue(result["authorized"])
        run.assert_called_once()
        kill.assert_not_called()

    @patch.object(runner_control, "emergency_process_cleanup_disabled", return_value=False)
    @patch.object(runner_control.os, "kill")
    @patch.object(runner_control.subprocess, "run")
    def test_runner_control_refuses_kill_without_explicit_capability(self, run, kill, _disabled):
        result = runner_control._stop_process_tree(self.record, self.expected, lambda _pid: self.live)
        self.assertEqual(result["reason"], "process_termination_not_enabled")
        run.assert_not_called()
        kill.assert_not_called()

    @patch.object(charlie_runner_supervisor, "emergency_process_cleanup_disabled", return_value=True)
    @patch.object(charlie_runner_supervisor, "record_emergency_cleanup_refusal")
    @patch.object(charlie_runner_supervisor.os, "kill")
    @patch.object(charlie_runner_supervisor.subprocess, "run")
    def test_emergency_containment_overrides_supervisor_recovery(self, run, kill, record, _disabled):
        self.assertFalse(charlie_runner_supervisor._recover_stale_owned_child())
        record.assert_called_once()
        run.assert_not_called()
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
