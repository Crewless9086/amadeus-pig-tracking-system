import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import charlie_mission_pickup


MISSION = {
    "mission_id": "CHARLIE-MISSION-123",
    "status": "approved",
    "title": "Build useful thing",
    "raw_text": "Build useful thing from Telegram.",
    "urgency": "P2",
    "mission_type": "feature build",
    "approval_level": "LEVEL 3",
    "vault": {
        "mission_stage": "planned",
        "problem_statement": "Owner wants a useful thing.",
        "desired_outcome": "Useful thing is built and tested.",
        "acceptance_criteria": ["Dashboard shows the useful thing."],
        "test_plan": ["Run focused useful thing tests."],
        "forbidden_actions": ["No production writes."],
    },
    "agent_workflow": [
        {"agent": "planner", "status": "complete", "purpose": "Scope the mission."},
        {"agent": "builder", "status": "pending", "purpose": "Build the mission."},
    ],
    "media_references": [
        {"label": "Sketch", "reference": "planning/inbox/screenshots/useful.png"},
    ],
    "mission_context_pack": {
        "version": "charlie_context_pack_v1",
        "active_truth_docs": ["docs/00-start-here/CURRENT_STATE.md"],
        "shared_data_rules": ["Supabase is canonical where migration is complete."],
        "approval_rules": ["LEVEL 3 may open PR but not merge."],
        "parallel_work": "disabled_until_phase_6_parallel_controls",
    },
}


class CharlieMissionPickupTests(unittest.TestCase):
    def setUp(self):
        self._base_branch_env_patcher = patch.dict("os.environ", {"CHARLIE_RUNNER_BASE_BRANCH": ""})
        self._base_branch_env_patcher.start()
        self.addCleanup(self._base_branch_env_patcher.stop)
        if not self._testMethodName.startswith("test_ensure_base_branch"):
            self._base_branch_guard_patcher = patch(
                "scripts.charlie_mission_pickup._ensure_base_branch",
                return_value={
                    "success": True,
                    "status": "base_branch_not_required_outside_runner_worktree",
                    "current_branch": "test",
                },
            )
            self._base_branch_guard_patcher.start()
            self.addCleanup(self._base_branch_guard_patcher.stop)

    @patch("scripts.charlie_mission_pickup.update_mission_status")
    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup._owner_queue_missions")
    def test_reconcile_green_blocked_pr_moves_to_owner_review(self, owner_queue, update_vault, update_status):
        blocked = {
            **MISSION,
            "status": "blocked",
            "metadata": {
                "charlie_core": {"project_truth": {"workflow_template": "software_build"}},
                "review_packet": {"links": {"pr": "https://github.com/example/repo/pull/12"}},
            },
        }
        owner_queue.return_value = ([blocked], 200)
        update_vault.return_value = ({"success": True}, 200)
        update_status.return_value = ({"success": True}, 200)

        def fake_runner(*_args, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"number":12,"url":"https://github.com/example/repo/pull/12","state":"OPEN","mergeable":"MERGEABLE","headRefOid":"abc123","statusCheckRollup":[{"conclusion":"SUCCESS"}]}',
                stderr="",
            )

        result = charlie_mission_pickup.reconcile_blocked_pr_missions(run_subprocess=fake_runner)

        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(update_status.call_args.args[1], "pr_ready")
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["review_status"], "ready_for_owner_review")
        self.assertEqual(packet["tested_revision"], "abc123")

    @patch("scripts.charlie_mission_pickup.update_mission_status")
    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup._owner_queue_missions")
    def test_reconcile_conflicting_pr_queues_publisher_recovery(self, owner_queue, update_vault, update_status):
        blocked = {
            **MISSION,
            "status": "blocked",
            "metadata": {"review_packet": {"links": {"pr": "https://github.com/example/repo/pull/13"}}},
        }
        owner_queue.return_value = ([blocked], 200)
        update_vault.return_value = ({"success": True}, 200)
        update_status.return_value = ({"success": True}, 200)

        def fake_runner(*_args, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"number":13,"state":"OPEN","mergeable":"CONFLICTING","headRefOid":"def456","statusCheckRollup":[{"conclusion":"SUCCESS"}]}',
                stderr="",
            )

        result = charlie_mission_pickup.reconcile_blocked_pr_missions(run_subprocess=fake_runner)

        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(update_status.call_args.args[1], "approved")
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["return_to_stage"], "publisher")
        self.assertEqual(packet["review_status"], "internal_recovery_queued")

    def test_browser_preflight_is_capability_only_by_default(self):
        self.assertFalse(charlie_mission_pickup._mission_requires_browser_preflight({
            "metadata": {"charlie_core": {"project_truth": {"workflow_template": "ui_product_build"}}},
        }))

    @patch.dict("os.environ", {"CHARLIE_RUNNER_BASE_BRANCH": "charlie-runner-clean-base"})
    @patch("scripts.charlie_mission_pickup.subprocess.run")
    def test_ensure_base_branch_fails_instead_of_accepting_mission_branch(self, run):
        def fake_run(command, **_kwargs):
            if command == ["git", "branch", "--show-current"]:
                return SimpleNamespace(returncode=0, stdout="charlie/some-mission\n", stderr="")
            if command == ["git", "switch", "charlie-runner-clean-base"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="branch already checked out elsewhere")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        run.side_effect = fake_run

        result = charlie_mission_pickup._ensure_base_branch()

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "base_branch_switch_failed")
        self.assertEqual(result["current_branch"], "charlie/some-mission")
        self.assertIn("will not pick another mission", result["recommended_action"])

    @patch.dict("os.environ", {"CHARLIE_RUNNER_BASE_BRANCH": "charlie-runner-clean-base"})
    @patch("scripts.charlie_mission_pickup.subprocess.run")
    def test_ensure_base_branch_verifies_switch_result(self, run):
        calls = {"branch": 0}

        def fake_run(command, **_kwargs):
            if command == ["git", "branch", "--show-current"]:
                calls["branch"] += 1
                branch = "charlie/some-mission" if calls["branch"] == 1 else "charlie-runner-clean-base"
                return SimpleNamespace(returncode=0, stdout=f"{branch}\n", stderr="")
            if command == ["git", "switch", "charlie-runner-clean-base"]:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        run.side_effect = fake_run

        result = charlie_mission_pickup._ensure_base_branch()

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "base_branch_restored")
        self.assertEqual(result["previous_branch"], "charlie/some-mission")

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_pickup_reports_no_available_mission(self, list_owner_work_missions):
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "no_mission_available")
        list_owner_work_missions.assert_called_once_with("approved", limit=10)

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_dry_run_does_not_write_or_update_status(self, list_owner_work_missions):
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)

        with patch("scripts.charlie_mission_pickup.update_mission_status") as update_status:
            result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-123")
        self.assertEqual(result["runner_mode"], "code_test_pr")
        update_status.assert_not_called()
        list_owner_work_missions.assert_called_once_with("approved", limit=10)

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_default_pickup_uses_status_specific_owner_work_query(self, list_owner_work_missions):
        owner_mission = {**MISSION, "mission_id": "CHARLIE-MISSION-OWNER", "queue_class": "owner_work"}
        list_owner_work_missions.return_value = ({
            "success": True,
            "status": "ok",
            "missions": [owner_mission],
        }, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-OWNER")
        list_owner_work_missions.assert_called_once_with("approved", limit=10)

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_default_pickup_finds_approved_owner_mission_without_mixed_page_probe(self, list_owner_work_missions):
        owner_mission = {**MISSION, "mission_id": "CHARLIE-MISSION-DEEP", "queue_class": "owner_work"}
        list_owner_work_missions.return_value = ({
            "success": True,
            "status": "ok",
            "missions": [owner_mission],
        }, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-DEEP")
        list_owner_work_missions.assert_called_once_with("approved", limit=10)

    @patch("scripts.charlie_mission_pickup.notify_main")
    def test_pickup_notification_passes_mission_status_button_id(self, notify_main):
        captured_argv = []

        def fake_notify_main():
            captured_argv[:] = list(charlie_mission_pickup.sys.argv)
            return 0

        notify_main.side_effect = fake_notify_main

        result = charlie_mission_pickup._send_pickup_notification(MISSION)

        self.assertEqual(result, 0)
        self.assertIn("--mission-id", captured_argv)
        self.assertIn("CHARLIE-MISSION-123", captured_argv)

    @patch("scripts.charlie_mission_pickup.get_mission")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    def test_pickup_writes_codex_chat_and_marks_in_progress(self, update_status, update_vault, list_owner_work_missions, get_mission):
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "in_progress"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "CODEX_CHAT.md"
            with patch("scripts.charlie_mission_pickup.CODEX_CHAT_PATH", target):
                result, status_code = charlie_mission_pickup.pick_up_next_mission()
            content = target.read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "mission_picked_up")
        self.assertIn("Build useful thing from Telegram.", content)
        self.assertIn("CHARLIE_MISSION_PROTOCOL.md", content)
        self.assertIn("Runner mode: code_test_pr", content)
        self.assertIn("## MISSION VAULT", content)
        self.assertIn("Owner wants a useful thing.", content)
        self.assertIn("Dashboard shows the useful thing.", content)
        self.assertIn("Sketch: planning/inbox/screenshots/useful.png", content)
        self.assertIn("planner: complete", content)
        self.assertIn("Shared Mission Context Pack", content)
        self.assertIn("Supabase is canonical", content)
        self.assertIn("LEVEL 3 may open PR but not merge.", content)
        self.assertIn("LEVEL 3: code and tests may be changed", content)
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.args[1], "in_progress")
        self.assertEqual(update_status.call_args.kwargs["expected_status"], "approved")
        self.assertGreaterEqual(update_vault.call_count, 1)
        lease = update_vault.call_args.args[1]["execution_lease"]
        self.assertEqual(lease["mission_id"], "CHARLIE-MISSION-123")
        self.assertIn("lease_id", lease)
        self.assertTrue(result["execution_lease"]["persisted"])
        self.assertIn("workflow_refresh", result)

    @patch("scripts.charlie_mission_pickup.get_mission")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    def test_pickup_refreshes_old_workflow_before_claim(self, update_status, update_vault, list_owner_work_missions, get_mission):
        old_mission = {
            **MISSION,
            "metadata": {"charlie_core": {"project_truth": {"pipeline_profile": "full", "workflow_right_sized": False}}},
            "agent_workflow": [{"agent": "idea_expander", "status": "active"}],
        }
        refreshed_mission = {
            **old_mission,
            "agent_workflow": [{"agent": "planner", "status": "active"}],
            "mission_context_pack": {"agent_order": ["planner", "builder", "tester", "reviewer", "publisher"]},
        }
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [old_mission]}, 200)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "in_progress"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        get_mission.return_value = ({"success": True, "status": "ok", "mission": refreshed_mission}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "CODEX_CHAT.md"
            with patch("scripts.charlie_mission_pickup.CODEX_CHAT_PATH", target):
                result, status_code = charlie_mission_pickup.pick_up_next_mission()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["workflow_refresh"]["refreshed"])
        refresh_payload = update_vault.call_args_list[0].args[1]
        self.assertIn("agent_workflow", refresh_payload)
        self.assertIn("mission_context_pack", refresh_payload)
        self.assertIn("charlie_core", refresh_payload)
        self.assertEqual(update_status.call_args.kwargs["expected_status"], "approved")

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    def test_dry_run_does_not_refresh_old_workflow(self, update_status, update_vault, list_owner_work_missions):
        old_mission = {
            **MISSION,
            "metadata": {"charlie_core": {"project_truth": {"pipeline_profile": "full", "workflow_right_sized": False}}},
            "agent_workflow": [{"agent": "idea_expander", "status": "active"}],
        }
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [old_mission]}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        update_vault.assert_not_called()
        update_status.assert_not_called()

    def test_resume_workflow_inserts_required_agents_and_preserves_completed_evidence(self):
        current = [
            {"agent": "source_mapper", "status": "complete", "findings": "mapped"},
            {"agent": "builder", "status": "complete", "findings": "built"},
            {"agent": "business_reviewer", "status": "blocked"},
        ]
        planned = [
            {"agent": "source_mapper", "status": "active"},
            {"agent": "product_architect", "status": "pending"},
            {"agent": "builder", "status": "pending"},
            {"agent": "business_reviewer", "status": "pending"},
            {"agent": "product_reviewer", "status": "pending"},
        ]

        merged = charlie_mission_pickup._merge_resumable_workflow(current, planned, resume_stage="business_reviewer")
        by_agent = {item["agent"]: item for item in merged}

        self.assertEqual(by_agent["source_mapper"]["status"], "complete")
        self.assertEqual(by_agent["source_mapper"]["findings"], "mapped")
        self.assertEqual(by_agent["product_architect"]["status"], "active")
        self.assertEqual(by_agent["builder"]["status"], "pending")
        self.assertEqual(by_agent["business_reviewer"]["status"], "pending")
        self.assertEqual(by_agent["product_reviewer"]["status"], "pending")

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    def test_pickup_claim_lost_does_not_write_codex_chat(self, update_status, list_owner_work_missions):
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)
        update_status.return_value = ({"success": False, "status": "status_claim_lost"}, 409)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "CODEX_CHAT.md"
            with patch("scripts.charlie_mission_pickup.CODEX_CHAT_PATH", target):
                result, status_code = charlie_mission_pickup.pick_up_next_mission()

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "claim_lost")
        self.assertFalse(result["codex_chat_written"])
        self.assertFalse(target.exists())

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_pickup_content_includes_level_four_merge_guidance(self, list_owner_work_missions):
        mission = dict(MISSION)
        mission["approval_level"] = "LEVEL 4"
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [mission]}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)
        content = charlie_mission_pickup._codex_chat_content(mission)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["runner_mode"], "merge_after_verification")
        self.assertIn("Runner mode: merge_after_verification", content)
        self.assertIn("LEVEL 4: release/merge authority", content)

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_watch_mode_can_timeout_without_pickup(self, list_owner_work_missions, write_heartbeat, sleep):
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=2,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "watch_timeout_no_mission_available")
        self.assertEqual(result["checks"], 2)
        self.assertGreaterEqual(write_heartbeat.call_count, 2)
        sleep.assert_called_once_with(5)

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_continuous_watch_retries_transient_queue_read_failure(self, list_owner_work_missions, write_heartbeat, sleep):
        owner_queue_calls = {"count": 0}

        def fake_list_owner_work_missions(status="", limit=10):
            if status == "approved":
                owner_queue_calls["count"] += 1
                if owner_queue_calls["count"] == 1:
                    return {"success": False, "status": "mission_read_failed"}, 503
            return {"success": True, "status": "ok", "missions": []}, 200

        list_owner_work_missions.side_effect = fake_list_owner_work_missions

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=2,
            continuous=True,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "watch_timeout_no_mission_available")
        self.assertEqual(owner_queue_calls["count"], 2)
        self.assertGreaterEqual(write_heartbeat.call_count, 2)
        sleep.assert_called_once_with(5)

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.execute_codex_for_mission")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_continuous_watch_does_not_rerun_existing_in_progress_mission(self, list_owner_work_missions, write_heartbeat, execute_codex, sleep):
        def fake_list_owner_work_missions(status="", limit=10):
            if status == "in_progress":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-ACTIVE",
                        "title": "Active mission",
                        "status": "in_progress",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_owner_work_missions.side_effect = fake_list_owner_work_missions
        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=1,
            continuous=True,
            execute_codex=True,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "active_mission_in_progress")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-ACTIVE")
        execute_codex.assert_not_called()
        write_heartbeat.assert_called()
        sleep.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    def test_watch_notify_preflight_blocks_mute_runner(self, write_heartbeat):
        result, status_code = charlie_mission_pickup.watch_for_mission(
            notify=True,
            continuous=True,
            max_checks=1,
        )

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "notification_preflight_failed")
        self.assertIn("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS", result["missing_env"])
        write_heartbeat.assert_called_once()

    @patch("scripts.charlie_mission_pickup._send_blocked_notification")
    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    @patch("scripts.charlie_mission_pickup.runner_status")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_recover_stranded_mission_blocks_and_notifies(self, list_owner_work_missions, runner_status, update_status, update_vault, send_blocked):
        active = {
            **MISSION,
            "status": "in_progress",
            "mission_id": "CHARLIE-MISSION-STRANDED",
            "agent_workflow": [{"agent": "builder", "status": "active"}],
        }
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": [active]}, 200)
        runner_status.return_value = {
            "status": "runner_stale_or_stopped",
            "active": False,
            "process_alive": False,
            "age_seconds": 999,
            "last_mission_id": "CHARLIE-MISSION-STRANDED",
            "agent_ledger": {"latest_stage": {"agent": "builder"}},
        }
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        charlie_mission_pickup.RECOVERED_STALE_MISSIONS.clear()

        result = charlie_mission_pickup.recover_stranded_missions(notify=True)

        self.assertEqual(result["recovered_count"], 1)
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.args[1], "blocked")
        self.assertEqual(update_status.call_args.kwargs["expected_status"], "in_progress")
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["blocked_agent"], "builder")
        self.assertEqual(packet["return_to_stage"], "builder")
        send_blocked.assert_called_once()

    @patch("scripts.charlie_mission_pickup._send_blocked_notification")
    @patch("scripts.charlie_mission_pickup._send_review_ready_notification")
    @patch("scripts.charlie_mission_pickup.run_agent_execution_bridge_v2")
    def test_execute_codex_notifies_review_ready_for_any_pr_ready_result(self, run_bridge, send_review, send_blocked):
        run_bridge.return_value = ({
            "success": True,
            "status": "custom_completed_status",
            "mission_id": "CHARLIE-MISSION-ACTIVE",
            "mission_status": "pr_ready",
        }, 200)

        result, status_code = charlie_mission_pickup.execute_codex_for_mission(
            "CHARLIE-MISSION-ACTIVE",
            notify=True,
            timeout_seconds=30,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["mission_status"], "pr_ready")
        send_review.assert_called_once_with(result)
        send_blocked.assert_not_called()

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_continuous_watch_waits_when_mission_is_active_without_execute_flag(self, list_owner_work_missions, write_heartbeat, sleep):
        def fake_list_owner_work_missions(status="", limit=10):
            if status == "in_progress":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-ACTIVE",
                        "title": "Active mission",
                        "status": "in_progress",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_owner_work_missions.side_effect = fake_list_owner_work_missions

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=1,
            continuous=True,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "active_mission_in_progress")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-ACTIVE")
        write_heartbeat.assert_called()
        sleep.assert_not_called()

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_continuous_watch_waits_when_release_is_in_progress(self, list_owner_work_missions, write_heartbeat, sleep):
        def fake_list_owner_work_missions(status="", limit=10):
            if status == "release_in_progress":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-RELEASE",
                        "title": "Release mission",
                        "status": "release_in_progress",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_owner_work_missions.side_effect = fake_list_owner_work_missions

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=1,
            continuous=True,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "active_mission_in_progress")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-RELEASE")
        write_heartbeat.assert_called()
        sleep.assert_not_called()

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_continuous_watch_can_pick_next_approved_when_previous_is_pr_ready(self, list_owner_work_missions, write_heartbeat, sleep):
        def fake_list_owner_work_missions(status="", limit=10):
            if status == "approved":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [MISSION],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_owner_work_missions.side_effect = fake_list_owner_work_missions

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=1,
            continuous=True,
            dry_run=True,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-123")
        self.assertEqual(result["runner_mode"], "code_test_pr")
        queried_statuses = [call.args[0] for call in list_owner_work_missions.call_args_list]
        self.assertNotIn("pr_ready", queried_statuses)
        self.assertIn("approved", queried_statuses)
        write_heartbeat.assert_called()
        sleep.assert_not_called()

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.process_release_approved_mission")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_continuous_watch_processes_release_approved_when_enabled(self, list_owner_work_missions, write_heartbeat, process_release, sleep):
        def fake_list_owner_work_missions(status="", limit=10):
            if status == "release_approved":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-RELEASE",
                        "title": "Release mission",
                        "status": "release_approved",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_owner_work_missions.side_effect = fake_list_owner_work_missions
        process_release.return_value = ({
            "success": True,
            "status": "release_pr_merged",
            "mission_id": "CHARLIE-MISSION-RELEASE",
            "mission_status": "merged",
        }, 200)

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=1,
            continuous=True,
            watch_release=True,
            auto_merge_pr=True,
            release_verify_url="https://amadeus-pig-tracking-system.onrender.com/charlie",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_pr_merged")
        process_release.assert_called_once_with(
            "CHARLIE-MISSION-RELEASE",
            notify=False,
            auto_close_no_release=False,
            auto_merge_pr=True,
            release_verify_url="https://amadeus-pig-tracking-system.onrender.com/charlie",
        )
        write_heartbeat.assert_called()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
