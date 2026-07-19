import unittest
from unittest.mock import Mock, patch

from modules.charlie import execution_bridge, process_ownership, runner_control
from scripts import charlie_runner_supervisor


class CharlieProcessOwnershipTests(unittest.TestCase):
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
