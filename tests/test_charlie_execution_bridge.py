import tempfile
import unittest
import json
import os
import shutil
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


def _agent_from_prompt(prompt):
    for candidate in execution_bridge.all_agent_names():
        if f"{candidate.upper()} agent" in prompt:
            return candidate
    return "reviewer"


def _successful_stage_payload(agent):
    payload = {
        "summary": f"{agent} completed",
        "errors": [],
        "bugs": [],
        "files_inspected": ["modules/charlie/execution_bridge.py"],
        "commands_run": ["python -m unittest tests.test_charlie_execution_bridge"],
        "stdout_tail": "",
        "stderr_tail": "",
        "next_action": "continue",
        "opportunity": "clear owner opportunity" if agent == "idea_expander" else None,
        "owner_value": "owner value clear" if agent == "idea_expander" else None,
        "non_goals": ["no broad rebuild"] if agent == "idea_expander" else None,
        "user_flow": ["owner creates mission", "agents execute", "owner reviews"] if agent == "product_architect" else None,
        "acceptance_boundaries": ["owner approval remains required"] if agent == "product_architect" else None,
        "risk_notes": ["risk checked"] if agent in {"product_architect", "architect"} else None,
        "acceptance_criteria": ["acceptance"] if agent == "planner" else None,
        "test_plan": ["tests"] if agent == "planner" else None,
        "files_to_inspect": ["modules/charlie/execution_bridge.py"] if agent == "architect" else None,
        "implementation_plan": ["patch runner"] if agent == "architect" else None,
        "changed_files": ["modules/charlie/execution_bridge.py"] if agent in {"builder", "reviewer"} else None,
        "build_notes": ["patched"] if agent == "builder" else None,
        "branch_name": "charlie/test-pr-evidence" if agent == "builder" else None,
        "commit_sha": "abc1234" if agent == "builder" else None,
        "pr_url": "https://github.com/org/repo/pull/61" if agent in {"builder", "reviewer"} else None,
        "links": {"pr": "https://github.com/org/repo/pull/61"} if agent in {"builder", "reviewer"} else None,
        "tests_run": ["unit tests passed"] if agent == "tester" else None,
        "test_status": "pass" if agent == "tester" else None,
        "qa_findings": ["no high risk found"] if agent == "qa_red_team" else None,
        "red_team_status": "pass" if agent == "qa_red_team" else None,
        "risk_rating": "low" if agent == "qa_red_team" else None,
        "recommended_owner_decision": "approve_final_release" if agent == "reviewer" else None,
        "release_notes": ["owner review ready"] if agent == "reviewer" else None,
        "test_evidence": ["unit tests passed"] if agent == "reviewer" else None,
        "qa_evidence": ["QA/red-team passed"] if agent == "reviewer" else None,
    }
    return {key: value for key, value in payload.items() if value is not None}


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
            agent = _agent_from_prompt(prompt)
            payload = _successful_stage_payload(agent)
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
        self.assertIn("handoff_reports", vault_metadata["review_packet"])
        self.assertIn("qa_red_team", vault_metadata["review_packet"]["agent_artifacts"])
        self.assertIn("QA/red-team passed", vault_metadata["review_packet"]["qa_evidence"])
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
            agent = _agent_from_prompt(prompt)
            if agent == "builder":
                builder_calls["count"] += 1
            if agent == "tester":
                tester_calls["count"] += 1
            payload = _successful_stage_payload(agent)
            if agent == "tester" and tester_calls["count"] == 1:
                payload["test_status"] = "fail"
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
            agent = _agent_from_prompt(prompt)
            called_agents.append(agent)
            payload = _successful_stage_payload(agent)
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(called_agents, ["builder", "tester", "qa_red_team", "reviewer"])
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

    def test_builder_quality_gate_requires_pr_for_changed_files(self):
        artifact = {
            "summary": "build complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "build_notes": ["patched"],
        }

        result = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("Builder changed releaseable files", result["reason"])

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

    def test_reviewer_inherits_builder_pr_reference(self):
        reviewer = {
            "summary": "review complete",
            "changed_files": ["modules/charlie/execution_bridge.py"],
        }
        artifacts = {
            "builder": {
                "pr_url": "https://github.com/org/repo/pull/61",
                "links": {"pr": "https://github.com/org/repo/pull/61"},
            }
        }

        inherited = execution_bridge._inherit_pr_reference("reviewer", reviewer, artifacts)

        self.assertEqual(inherited["pr_url"], "https://github.com/org/repo/pull/61")
        self.assertEqual(inherited["links"]["pr"], "https://github.com/org/repo/pull/61")

    def test_visual_review_capture_writes_local_screenshot_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                def fake_runner(command, **_kwargs):
                    Path(command[-1]).write_bytes(b"fake png")
                    return SimpleNamespace(returncode=0, stdout="screenshot saved", stderr="")

                capture = execution_bridge._capture_visual_review_media(
                    "CHARLIE-MISSION-EXEC123",
                    {"url": "http://127.0.0.1:5000/charlie"},
                    run_subprocess=fake_runner,
                )
                media = execution_bridge._review_media_items("CHARLIE-MISSION-EXEC123")

        self.assertTrue(capture["captured"])
        self.assertEqual(capture["status"], "captured")
        self.assertEqual(media[0]["filename"], "owner_review_preview.png")
        self.assertIn("/api/charlie/build-relay/review-media/CHARLIE-MISSION-EXEC123/owner_review_preview.png", media[0]["reference"])

    def test_visual_review_packet_blocks_capture_without_preview_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                packet = execution_bridge._build_visual_review_packet(
                    mission_id="CHARLIE-MISSION-EXEC123",
                    mission_type="feature build",
                    changed_files=["templates/charlie.html"],
                    local_preview={"url": "", "status": "not_captured"},
                    artifacts={"builder": {"summary": "Changed owner review UI."}},
                )

        self.assertTrue(packet["ui_related"])
        self.assertEqual(packet["status"], "not_captured_blocked")
        self.assertEqual(packet["capture"]["status"], "preview_url_not_captured")
        self.assertEqual(packet["media"], [])
        self.assertIn("screenshot capture is blocked", packet["summary"])

    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_process_visual_review_cleanup_intent_updates_local_cleanup_status(self, update_vault):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        mission = {
            "mission_id": "CHARLIE-MISSION-EXEC123",
            "metadata": {
                "review_packet": {
                    "summary": "Ready",
                    "visual_review": {
                        "ui_related": True,
                        "cleanup": {"required": True, "status": "cleanup_requested"},
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                media_dir = Path(tmp) / "CHARLIE-MISSION-EXEC123"
                media_dir.mkdir()
                (media_dir / "owner_review_preview.png").write_bytes(b"fake png")

                result = execution_bridge.process_visual_review_cleanup_intent(
                    "CHARLIE-MISSION-EXEC123",
                    mission=mission,
                )

                self.assertFalse(media_dir.exists())

        self.assertTrue(result["processed"])
        self.assertEqual(result["status"], "cleaned")
        update_vault.assert_called_once()
        review_packet = update_vault.call_args.args[1]["review_packet"]
        cleanup = review_packet["visual_review"]["cleanup"]
        self.assertEqual(cleanup["status"], "cleaned")
        self.assertEqual(cleanup["result"]["status"], "review_media_cleaned")

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
        self.assertEqual(vault_metadata["review_packet"]["local_preview"]["status"], "captured")
        self.assertTrue(vault_metadata["review_packet"]["visual_review"]["ui_related"])
        self.assertEqual(vault_metadata["review_packet"]["visual_review"]["local_preview"]["url"], "http://127.0.0.1:5002/charlie")

    def test_visual_review_packet_collects_local_runner_media_for_ui_changes(self):
        mission_id = "CHARLIE-MISSION-VISUAL123"
        media_dir = execution_bridge._review_media_path(mission_id)
        if media_dir.exists():
            shutil.rmtree(media_dir)
        media_dir.mkdir(parents=True)
        try:
            (media_dir / "owner-review.png").write_bytes(b"not-real-image-but-route-contract")
            packet = execution_bridge._build_visual_review_packet(
                mission_id=mission_id,
                changed_files=["templates/charlie.html"],
                local_preview={"url": "http://127.0.0.1:5000/charlie", "status": "captured"},
            )
        finally:
            shutil.rmtree(media_dir, ignore_errors=True)

        self.assertTrue(packet["ui_related"])
        self.assertEqual(packet["status"], "captured")
        self.assertEqual(packet["media"][0]["reference"], "/api/charlie/build-relay/review-media/CHARLIE-MISSION-VISUAL123/owner-review.png")
        self.assertEqual(packet["cleanup"]["status"], "pending_owner_decision")

    def test_cleanup_visual_review_media_removes_only_runner_media_dir(self):
        mission_id = "CHARLIE-MISSION-CLEANUP123"
        media_dir = execution_bridge._review_media_path(mission_id)
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / "capture.png").write_bytes(b"temporary")

        result = execution_bridge.cleanup_visual_review_media(mission_id)

        self.assertTrue(result["cleaned"])
        self.assertEqual(result["status"], "review_media_cleaned")
        self.assertFalse(media_dir.exists())

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["static/js/charlieMissionControl.js"])
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_complete_codex_execution_does_not_default_local_preview_to_control_dashboard(
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
                "Summary complete\nTests run: checks passed\nNo local preview was provided.",
                encoding="utf-8",
            )
            result, status_code = execution_bridge.complete_codex_execution_from_artifact(
                "CHARLIE-MISSION-EXEC123",
                final_path=final_path,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        vault_metadata = update_vault.call_args.args[1]
        local_preview = vault_metadata["review_packet"]["local_preview"]
        self.assertEqual(local_preview["url"], "")
        self.assertEqual(local_preview["status"], "not_captured")
        self.assertIn("No mission-specific local preview URL", local_preview["message"])
        self.assertEqual(vault_metadata["review_packet"]["links"]["local_preview"], "")

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

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/routes.py"])
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_block_agent_stage_preserves_failed_qa_artifact_for_owner_review(
        self,
        update_vault,
        update_workflow,
        update_status,
        _changed_files,
    ):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        ledger = {
            "version": "charlie_agent_runner_v2",
            "execution_id": "EXEC123",
            "mission_id": "CHARLIE-MISSION-EXEC123",
            "stages": [],
            "backflow_events": [
                {"from_agent": "qa_red_team", "to_agent": "builder", "reason": "QA failed", "attempt": 1},
                {"from_agent": "qa_red_team", "to_agent": "builder", "reason": "QA failed", "attempt": 2},
            ],
            "quality_gates": [],
        }
        artifact = {
            "summary": "QA found release-blocking risks.",
            "errors": [],
            "bugs": ["Mutation routes allow read-role writes."],
            "files_inspected": ["modules/charlie/routes.py"],
            "commands_run": ["python -m unittest tests.test_charlie_build_relay"],
            "qa_findings": ["Owner mutation route requires stronger access gate."],
            "red_team_status": "fail",
            "risk_rating": "high",
            "quality_gate": {"passed": False, "reason": "QA/red-team reported red_team_status=fail."},
        }

        with tempfile.TemporaryDirectory() as tmp:
            final_path = Path(tmp) / "EXEC123.qa_red_team.final.md"
            stdout_path = Path(tmp) / "EXEC123.qa_red_team.stdout.txt"
            stderr_path = Path(tmp) / "EXEC123.qa_red_team.stderr.txt"
            prompt_path = Path(tmp) / "EXEC123.qa_red_team.prompt.md"
            for path in (final_path, stdout_path, stderr_path, prompt_path):
                path.write_text("", encoding="utf-8")
            result, status_code = execution_bridge._block_agent_stage(
                "CHARLIE-MISSION-EXEC123",
                "EXEC123",
                ledger,
                "qa_red_team",
                {
                    "final_path": final_path,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "prompt_path": prompt_path,
                },
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                "2026-07-01T06:00:00+00:00",
                blocked_reason="QA/red-team reported red_team_status=fail.",
                artifact=artifact,
                artifacts={"qa_red_team": artifact},
            )

        self.assertEqual(status_code, 504)
        self.assertEqual(result["status"], "agent_stage_blocked")
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["blocked_agent"], "qa_red_team")
        self.assertEqual(packet["blocked_reason"], "QA/red-team reported red_team_status=fail.")
        self.assertIn("qa_red_team", packet["agent_artifacts"])
        self.assertEqual(packet["agent_artifacts"]["qa_red_team"]["risk_rating"], "high")
        self.assertIn("Owner mutation route requires stronger access gate.", packet["qa_evidence"])
        self.assertEqual(len(packet["backflow_events"]), 2)
        self.assertEqual(packet["blocked_summary"]["blocked_at"], "qa_red_team")
        self.assertEqual(packet["blocked_summary"]["send_back_attempts"], 2)
        self.assertTrue(packet["unresolved_blockers"])
        self.assertTrue(any(
            "Owner mutation route requires stronger access gate." in item.get("finding", "")
            for item in packet["unresolved_blockers"]
        ))

    def test_agent_stage_prompt_includes_unresolved_backflow_issues(self):
        ledger = {
            "backflow_events": [
                {
                    "from_agent": "qa_red_team",
                    "to_agent": "builder",
                    "reason": "QA failed",
                    "unresolved_blockers": [
                        {
                            "severity": "high",
                            "file": "modules/charlie/routes.py",
                            "finding": "Dashboard route performs destructive cleanup.",
                        }
                    ],
                }
            ],
            "unresolved_blockers": [
                {
                    "severity": "high",
                    "file": "modules/charlie/routes.py",
                    "finding": "Dashboard route performs destructive cleanup.",
                }
            ],
        }

        prompt = execution_bridge.build_agent_stage_prompt(MISSION, "builder", artifacts={}, ledger=ledger)

        self.assertIn("Unresolved agent send-back issues", prompt)
        self.assertIn("Dashboard route performs destructive cleanup.", prompt)
        self.assertIn("modules/charlie/routes.py", prompt)

    def test_validate_qa_artifact_allows_empty_findings_when_qa_passes(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["qa_findings"] = []

        result = execution_bridge._validate_agent_artifact("qa_red_team", artifact)

        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_keys"], [])

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
        self.assertIn("live_release_verification", packet)

    @patch.dict(os.environ, {"CHARLIE_RELEASE_VERIFY_URL": "https://example.com/charlie"}, clear=True)
    def test_default_release_verify_url_prefers_explicit_charlie_url(self):
        self.assertEqual(execution_bridge._default_release_verify_url(), "https://example.com/charlie")

    def test_release_verification_reports_missing_url_as_unconfigured(self):
        result = execution_bridge._wait_for_release_verification("", attempts=3, interval_seconds=0)

        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "verify_url_not_configured")
        self.assertEqual(result["attempts"], 0)

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

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_records_failed_merge_packet(self, get_mission, update_vault, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            if command[:4] == ["gh", "pr", "merge", "56"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="merge failed")
            if command[:4] == ["gh", "pr", "view", "56"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "OPEN"}), stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 502)
        self.assertEqual(result["status"], "release_pr_merge_failed")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "blocked"])
        update_vault.assert_called_once()
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertEqual(release_packet["status"], "release_pr_merge_failed")
        self.assertEqual(release_packet["merge_result"]["stderr"], "merge failed")

    @patch("modules.charlie.execution_bridge._wait_for_release_verification", return_value={"verified": False, "status": "verify_url_not_provided", "attempts": 1})
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_reconciles_already_merged_pr(self, get_mission, update_vault, update_status, _verify):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            if command[:4] == ["gh", "pr", "merge", "56"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="local checkout failed")
            if command[:4] == ["gh", "pr", "view", "56"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"state": "MERGED", "mergedAt": "2026-06-30T20:48:26Z", "number": 56}),
                    stderr="",
                )
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

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
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertTrue(release_packet["merge_result"]["reconciled_as_merged"])
        self.assertTrue(release_packet["merge_result"]["reconciliation"]["merged"])

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
