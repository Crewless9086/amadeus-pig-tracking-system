import tempfile
import unittest
import json
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
    def test_agent_runner_v2_defaults_to_dry_run(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_dry_run")
        self.assertEqual(result["agent_runner_version"], "charlie_agent_runner_v2")
        self.assertIn("ledger_path", result)

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_records_stage_artifacts_and_review_packet(
        self,
        get_mission,
        update_vault,
        update_workflow,
        write_heartbeat,
        _changed_files,
    ):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = "reviewer"
            for candidate in execution_bridge.AGENT_SEQUENCE:
                if f"{candidate.upper()} agent" in prompt:
                    agent = candidate
                    break
            payload = {
                "summary": f"{agent} completed",
                "errors": [],
                "bugs": [],
                "files_inspected": ["modules/charlie/execution_bridge.py"],
                "commands_run": ["rg run_agent_execution_bridge_v2 modules/charlie/execution_bridge.py"],
                "next_action": "continue",
                "acceptance_criteria": ["acceptance"] if agent == "planner" else None,
                "test_plan": ["tests"] if agent == "planner" else None,
                "files_to_inspect": ["modules/charlie/execution_bridge.py"] if agent == "architect" else None,
                "risk_notes": ["risk checked"] if agent == "architect" else None,
                "implementation_plan": ["patch runner"] if agent == "architect" else None,
                "changed_files": ["modules/charlie/execution_bridge.py"] if agent in {"builder", "reviewer"} else None,
                "build_notes": ["patched"] if agent == "builder" else None,
                "tests_run": ["unit tests passed"] if agent == "tester" else None,
                "test_status": "pass" if agent == "tester" else None,
                "recommended_owner_decision": "approve_final_release" if agent == "reviewer" else None,
                "release_notes": ["owner review ready"] if agent == "reviewer" else None,
                "test_evidence": ["unit tests passed"] if agent == "reviewer" else None,
                "pr_url": "https://github.com/org/repo/pull/61" if agent == "reviewer" else None,
                "links": {"pr": "https://github.com/org/repo/pull/61"} if agent == "reviewer" else None,
            }
            payload = {key: value for key, value in payload.items() if value is not None}
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertEqual(result["mission_status"], "pr_ready")
        self.assertEqual(result["agent_runner_version"], "charlie_agent_runner_v2")
        self.assertGreaterEqual(update_workflow.call_count, 10)
        update_vault.assert_called()
        vault_metadata = update_vault.call_args.args[1]
        self.assertIn("agent_execution", vault_metadata)
        self.assertIn("agent_artifacts", vault_metadata["review_packet"])
        self.assertIn("quality_gates", vault_metadata["review_packet"])
        self.assertEqual(vault_metadata["review_packet"]["links"]["pr"], "https://github.com/org/repo/pull/61")
        self.assertEqual(vault_metadata["review_packet"]["pr_url"], "https://github.com/org/repo/pull/61")
        self.assertEqual(vault_metadata["review_packet"]["review_status"], "ready_for_owner_review")
        self.assertTrue(any(call.args[0].get("current_agent") == "planner" for call in write_heartbeat.call_args_list))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_sends_failed_tester_back_to_builder(
        self,
        get_mission,
        update_vault,
        update_workflow,
        write_heartbeat,
        _changed_files,
    ):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        tester_calls = {"count": 0}
        builder_calls = {"count": 0}

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = "reviewer"
            for candidate in execution_bridge.AGENT_SEQUENCE:
                if f"{candidate.upper()} agent" in prompt:
                    agent = candidate
                    break
            if agent == "builder":
                builder_calls["count"] += 1
            if agent == "tester":
                tester_calls["count"] += 1
            payload = {
                "summary": f"{agent} completed",
                "errors": [],
                "bugs": [],
                "files_inspected": ["modules/charlie/execution_bridge.py"],
                "commands_run": ["python -m unittest tests.test_charlie_execution_bridge"],
                "next_action": "continue",
                "acceptance_criteria": ["acceptance"] if agent == "planner" else None,
                "test_plan": ["tests"] if agent == "planner" else None,
                "files_to_inspect": ["modules/charlie/execution_bridge.py"] if agent == "architect" else None,
                "risk_notes": ["risk checked"] if agent == "architect" else None,
                "implementation_plan": ["patch runner"] if agent == "architect" else None,
                "changed_files": ["modules/charlie/execution_bridge.py"] if agent in {"builder", "reviewer"} else None,
                "build_notes": ["patched"] if agent == "builder" else None,
                "tests_run": ["unit tests"] if agent == "tester" else None,
                "test_status": "fail" if agent == "tester" and tester_calls["count"] == 1 else ("pass" if agent == "tester" else None),
                "recommended_owner_decision": "approve_final_release" if agent == "reviewer" else None,
                "release_notes": ["ready"] if agent == "reviewer" else None,
                "test_evidence": ["unit tests passed"] if agent == "reviewer" else None,
                "pr_url": "https://github.com/org/repo/pull/61" if agent == "reviewer" else None,
            }
            payload = {key: value for key, value in payload.items() if value is not None}
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertGreaterEqual(builder_calls["count"], 2)
        self.assertGreaterEqual(tester_calls["count"], 2)
        vault_metadata = update_vault.call_args.args[1]
        self.assertTrue(vault_metadata["review_packet"]["backflow_events"])
        self.assertTrue(any(call.args[0].get("status") == "agent_backflow" for call in write_heartbeat.call_args_list))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_send_back_reruns_from_target_stage_only(
        self,
        get_mission,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = dict(MISSION)
        mission["metadata"] = {
            "review_packet": {
                "return_to_stage": "builder",
                "agent_artifacts": {
                    "planner": {
                        "summary": "planner preserved",
                        "acceptance_criteria": ["acceptance"],
                        "test_plan": ["tests"],
                        "files_inspected": ["docs/00-start-here/CURRENT_STATE.md"],
                        "commands_run": ["rg CHARLIE docs"],
                    },
                    "architect": {
                        "summary": "architect preserved",
                        "files_to_inspect": ["modules/charlie/execution_bridge.py"],
                        "risk_notes": ["risk"],
                        "implementation_plan": ["plan"],
                        "files_inspected": ["modules/charlie/execution_bridge.py"],
                        "commands_run": ["rg run_agent_execution_bridge_v2 modules/charlie/execution_bridge.py"],
                    },
                },
            }
        }
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        called_agents = []

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = "reviewer"
            for candidate in execution_bridge.AGENT_SEQUENCE:
                if f"{candidate.upper()} agent" in prompt:
                    agent = candidate
                    break
            called_agents.append(agent)
            payload = {
                "summary": f"{agent} completed",
                "errors": [],
                "bugs": [],
                "files_inspected": ["modules/charlie/execution_bridge.py"],
                "commands_run": ["python -m unittest tests.test_charlie_execution_bridge"],
                "next_action": "continue",
                "changed_files": ["modules/charlie/execution_bridge.py"] if agent in {"builder", "reviewer"} else None,
                "build_notes": ["patched"] if agent == "builder" else None,
                "tests_run": ["unit tests"] if agent == "tester" else None,
                "test_status": "pass" if agent == "tester" else None,
                "recommended_owner_decision": "approve_final_release" if agent == "reviewer" else None,
                "release_notes": ["ready"] if agent == "reviewer" else None,
                "test_evidence": ["unit tests passed"] if agent == "reviewer" else None,
                "pr_url": "https://github.com/org/repo/pull/61" if agent == "reviewer" else None,
            }
            payload = {key: value for key, value in payload.items() if value is not None}
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(called_agents, ["builder", "tester", "reviewer"])
        vault_metadata = update_vault.call_args.args[1]
        self.assertEqual(vault_metadata["review_packet"]["agent_artifacts"]["planner"]["summary"], "planner preserved")
        self.assertEqual(vault_metadata["agent_execution"]["rerun_from_stage"], "builder")

    def test_reviewer_quality_gate_requires_pr_for_changed_files(self):
        artifact = {
            "summary": "review complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["ready"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "test_evidence": ["unit tests passed"],
        }

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("PR link", result["reason"])

    def test_reviewer_quality_gate_accepts_pr_for_changed_files(self):
        artifact = {
            "summary": "review complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["ready"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "test_evidence": ["unit tests passed"],
            "links": {"pr": "https://github.com/org/repo/pull/61"},
        }

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertTrue(result["passed"])

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

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["static/js/charlieMissionControl.js"])
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_complete_codex_execution_from_existing_final_artifact(
        self,
        update_vault,
        update_workflow,
        _changed_files,
    ):
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            final_path = Path(tmp) / "EXEC123-20260630T000000Z-1.final.md"
            final_path.write_text(
                "Summary complete\nOpen: http://127.0.0.1:5002/charlie\nTests run: checks passed",
                encoding="utf-8",
            )
            result, status_code = execution_bridge.complete_codex_execution_from_artifact(
                "CHARLIE-MISSION-EXEC123",
                final_path=final_path,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        self.assertEqual(result["mission_status"], "pr_ready")
        self.assertGreaterEqual(update_workflow.call_count, 6)
        vault_metadata = update_vault.call_args.args[1]
        self.assertEqual(vault_metadata["review_packet"]["local_preview"]["url"], "http://127.0.0.1:5002/charlie")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/routes.py"])
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_block_codex_execution_without_final_artifact_creates_blocked_review_packet(
        self,
        update_vault,
        update_workflow,
        update_status,
        _changed_files,
    ):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "EXEC123.prompt.md"
            stdout_path = Path(tmp) / "EXEC123.stdout.txt"
            stderr_path = Path(tmp) / "EXEC123.stderr.txt"
            final_path = Path(tmp) / "EXEC123.final.md"
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("supervisor timeout", encoding="utf-8")
            result, status_code = execution_bridge.block_codex_execution_without_final_artifact(
                "CHARLIE-MISSION-EXEC123",
                execution_id="EXEC123",
                prompt_path=prompt_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                final_path=final_path,
            )

        self.assertEqual(status_code, 504)
        self.assertEqual(result["status"], "codex_no_final_artifact_timeout")
        self.assertEqual(result["mission_status"], "blocked")
        update_vault.assert_called_once()
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertIn("no final artifact", packet["summary"].lower())
        self.assertIn("modules/charlie/routes.py", packet["changed_files"])
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.args[1], "blocked")

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

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_blocks_without_pr_reference(self, get_mission, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"summary": "Approved but no PR."}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
            )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "release_pr_reference_required")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "blocked"])

    @patch("modules.charlie.execution_bridge._wait_for_release_verification", return_value={"verified": False, "status": "verify_url_not_provided", "attempts": 1})
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_merges_referenced_pr(self, get_mission, update_vault, update_status, _verify):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            self.assertEqual(command[:4], ["gh", "pr", "merge", "56"])
            return SimpleNamespace(returncode=0, stdout="Merged pull request", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_pr_merged")
        self.assertEqual(result["mission_status"], "merged")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "merged"])
        update_vault.assert_called_once()
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertIn("deployment_watch", release_packet)


if __name__ == "__main__":
    unittest.main()
