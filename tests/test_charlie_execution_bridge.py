import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.charlie import execution_bridge


MISSION = {
    "mission_id": "CHARLIE-MISSION-EXEC123",
    "status": "in_progress",
    "title": "Build execution bridge",
    "raw_text": "Make Codex execute the mission.",
    "urgency": "P1",
    "mission_type": "agent build",
    "approval_level": "LEVEL 3",
    "vault": {
        "problem_statement": "Approved missions need a local Codex execution bridge.",
        "desired_outcome": "Codex can run locally and stop at owner review.",
        "acceptance_criteria": ["Bridge prepares a prompt.", "Bridge records review evidence."],
        "test_plan": ["Run focused bridge tests."],
        "forbidden_actions": ["No web-triggered shell execution."],
    },
    "agent_workflow": [{"agent": "planner", "status": "active", "purpose": "Scope execution."}],
    "mission_context_pack": {"version": "charlie_context_pack_v1"},
}


class CharlieExecutionBridgeTests(unittest.TestCase):
    @patch("modules.charlie.execution_bridge.shutil.which")
    @patch("modules.charlie.execution_bridge.os.name", "nt")
    def test_codex_executable_prefers_windows_cmd_shim(self, which):
        def fake_which(name):
            return "C:/Users/charl/AppData/Roaming/npm/codex.cmd" if name == "codex.cmd" else None

        which.side_effect = fake_which

        self.assertEqual(
            execution_bridge._codex_executable(),
            "C:/Users/charl/AppData/Roaming/npm/codex.cmd",
        )

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_codex_execution_writes_prompt_without_running_codex(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.prepare_codex_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )
            prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "execution_prepared")
        self.assertFalse(result["will_execute_codex"])
        self.assertIn("Build execution bridge", prompt)
        self.assertIn("No web-triggered shell execution.", prompt)
        self.assertIn("Stop at owner review", prompt)

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_codex_execution_bridge_defaults_to_dry_run(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_codex_execution_bridge(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "execution_dry_run")
        self.assertIn("prompt_path", result)

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_codex_execution_rejects_release_approved_mission(self, get_mission):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)

        result, status_code = execution_bridge.prepare_codex_execution(
            mission_id="CHARLIE-MISSION-EXEC123",
        )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "mission_not_ready_for_codex_execution")
        self.assertEqual(result["required_status"], "in_progress")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_codex_execution_bridge_records_review_packet_on_success(
        self,
        get_mission,
        update_vault,
        update_workflow,
        _changed_files,
    ):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(*_args, **kwargs):
            output_path = kwargs["cwd"]
            self.assertIn("input", kwargs)
            return SimpleNamespace(
                returncode=0,
                stdout="Summary complete\nTests run: bridge tests passed",
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_codex_execution_bridge(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        self.assertEqual(result["mission_status"], "pr_ready")
        self.assertGreaterEqual(update_workflow.call_count, 6)
        update_vault.assert_called()
        vault_metadata = update_vault.call_args.args[1]
        self.assertIn("review_packet", vault_metadata)
        self.assertIn("modules/charlie/execution_bridge.py", vault_metadata["review_packet"]["changed_files"])

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_release_execution_writes_release_packet(self, get_mission):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"summary": "Owner approved.", "test_evidence": ["tests passed"]}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.prepare_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )
            packet = Path(result["release_packet_path"]).read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_execution_prepared")
        self.assertIn("no_release_closeout", packet)
        self.assertIn("Owner approved.", packet)

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_release_execution_rejects_non_release_approved_mission(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        result, status_code = execution_bridge.prepare_release_execution(
            mission_id="CHARLIE-MISSION-EXEC123",
        )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "mission_not_ready_for_release_execution")
        self.assertEqual(result["required_status"], "release_approved")

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_complete_no_release_marks_release_approved_done(self, get_mission, update_vault, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.complete_no_release_mission(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_no_release_completed")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "done"])
        update_vault.assert_called_once()


if __name__ == "__main__":
    unittest.main()
