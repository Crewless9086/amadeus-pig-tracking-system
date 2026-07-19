import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.charlie import execution_bridge, runner_control


class CharlieEmergencyProcessContainmentTests(unittest.TestCase):
    def _marker_and_log(self, root):
        marker = Path(root) / "EMERGENCY_PROCESS_CLEANUP_DISABLED"
        marker.write_text("timestamp=test\nreason=test containment\n", encoding="utf-8")
        return marker, Path(root) / "refusals.jsonl"

    def test_stop_runner_refuses_before_status_or_termination(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker, log = self._marker_and_log(tmp)
            with (
                patch.object(runner_control, "EMERGENCY_CLEANUP_DISABLED_PATH", marker),
                patch.object(runner_control, "EMERGENCY_CLEANUP_REFUSAL_LOG", log),
                patch.object(runner_control, "runner_status") as status,
                patch.object(runner_control.subprocess, "run") as run,
                patch.object(runner_control.os, "kill") as kill,
            ):
                result, status_code = runner_control.stop_runner()
        self.assertEqual(status_code, 423)
        self.assertEqual(result["status"], "emergency_process_cleanup_disabled")
        status.assert_not_called()
        run.assert_not_called()
        kill.assert_not_called()

    def test_cleanup_runner_environment_refuses_before_status_or_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker, log = self._marker_and_log(tmp)
            with (
                patch.object(runner_control, "EMERGENCY_CLEANUP_DISABLED_PATH", marker),
                patch.object(runner_control, "EMERGENCY_CLEANUP_REFUSAL_LOG", log),
                patch.object(runner_control, "runner_status") as status,
                patch.object(runner_control.subprocess, "run") as run,
                patch.object(runner_control.os, "kill") as kill,
            ):
                result, status_code = runner_control.cleanup_runner_environment()
        self.assertEqual(status_code, 423)
        self.assertEqual(result["status"], "emergency_process_cleanup_disabled")
        status.assert_not_called()
        run.assert_not_called()
        kill.assert_not_called()

    def test_stop_process_tree_logs_pid_and_never_calls_kill_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker, log = self._marker_and_log(tmp)
            with (
                patch.object(runner_control, "EMERGENCY_CLEANUP_DISABLED_PATH", marker),
                patch.object(runner_control, "EMERGENCY_CLEANUP_REFUSAL_LOG", log),
                patch.object(runner_control.subprocess, "run") as run,
                patch.object(runner_control.os, "kill") as kill,
            ):
                result = runner_control._stop_process_tree(12345)
                logged = log.read_text(encoding="utf-8")
        self.assertEqual(result["status"], "emergency_process_cleanup_disabled")
        self.assertIn('"requested_pid": "12345"', logged)
        run.assert_not_called()
        kill.assert_not_called()

    def test_execution_bridge_termination_refuses_without_process_inspection(self):
        refusal = {
            "status": "emergency_process_cleanup_disabled",
            "operation": "_terminate_process_tree",
            "requested_pid": "54321",
        }
        with (
            patch.object(execution_bridge, "emergency_process_cleanup_disabled", return_value=True),
            patch.object(execution_bridge, "record_emergency_cleanup_refusal", return_value=refusal) as record,
            patch.object(execution_bridge.subprocess, "run") as run,
            patch.object(execution_bridge.os, "kill") as kill,
            patch.object(execution_bridge.os, "killpg", create=True) as killpg,
        ):
            result = execution_bridge._terminate_process_tree(54321)
        self.assertEqual(result["status"], "emergency_process_cleanup_disabled")
        record.assert_called_once_with("_terminate_process_tree", 54321)
        run.assert_not_called()
        kill.assert_not_called()
        killpg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
