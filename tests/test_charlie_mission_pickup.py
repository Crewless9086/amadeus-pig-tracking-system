import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
    def test_resume_uses_exact_remote_branch_without_local_fast_forward(self):
        mission = {
            "mission_id": "M-1",
            "metadata": {"review_packet": {"agent_artifacts": {"builder": {"branch_name": "feature/test"}}}},
        }
        commands = []
        def run(command):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        result = charlie_mission_pickup._restore_mission_branch_for_resume(mission, run_subprocess=run)
        self.assertTrue(result["success"])
        self.assertIn(["git", "switch", "--detach", "origin/feature/test"], commands)
        self.assertNotIn(["git", "switch", "feature/test"], commands)
        self.assertFalse(any(command[:3] == ["git", "merge", "--ff-only"] for command in commands))
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

    def test_restore_mission_branch_for_resume_fetches_exact_remote_revision(self):
        mission = {
            "metadata": {
                "review_packet": {
                    "agent_artifacts": {
                        "builder": {"branch_name": "feature/beacon-opportunity-scanner"},
                    },
                },
            },
        }
        commands = []

        def run(command):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        result = charlie_mission_pickup._restore_mission_branch_for_resume(mission, run_subprocess=run)

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "mission_branch_restored")
        self.assertEqual(commands, [
            ["git", "fetch", "origin", "feature/beacon-opportunity-scanner"],
            ["git", "switch", "--detach", "origin/feature/beacon-opportunity-scanner"],
        ])

    def test_restore_mission_branch_uses_detached_remote_when_branch_is_owned_elsewhere(self):
        mission = {"metadata": {"review_packet": {"agent_artifacts": {"builder": {"branch_name": "feature/beacon-work"}}}}}
        commands = []

        def run(command):
            commands.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        result = charlie_mission_pickup._restore_mission_branch_for_resume(mission, run_subprocess=run)

        self.assertTrue(result["success"])
        self.assertIn(["git", "switch", "--detach", "origin/feature/beacon-work"], commands)
        self.assertNotIn(["git", "switch", "--track", "-c", "feature/beacon-work", "origin/feature/beacon-work"], commands)

    def test_restore_mission_branch_for_resume_rejects_unsafe_branch(self):
        mission = {"metadata": {"review_packet": {"agent_artifacts": {"builder": {"branch_name": "../unsafe"}}}}}

        result = charlie_mission_pickup._restore_mission_branch_for_resume(mission, run_subprocess=Mock())

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_mission_branch_name")

    def test_restore_mission_branch_for_resume_resolves_branch_from_pr_number(self):
        mission = {"metadata": {"review_packet": {"agent_artifacts": {"builder": {"pr_number": "168"}}}}}
        commands = []

        def run(command):
            commands.append(command)
            stdout = "feature/beacon-opportunity-scanner\n" if command[:3] == ["gh", "pr", "view"] else ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        result = charlie_mission_pickup._restore_mission_branch_for_resume(mission, run_subprocess=run)

        self.assertTrue(result["success"])
        self.assertEqual(result["branch_name"], "feature/beacon-opportunity-scanner")
        self.assertEqual(commands[0], ["gh", "pr", "view", "168", "--json", "headRefName", "--jq", ".headRefName"])
        self.assertEqual(commands[1], ["git", "fetch", "origin", "feature/beacon-opportunity-scanner"])

    @patch("scripts.charlie_mission_pickup.transition_mission_review_state")
    @patch("scripts.charlie_mission_pickup._owner_queue_missions")
    def test_reconcile_green_blocked_pr_moves_to_owner_review(self, owner_queue, transition):
        blocked = {
            **MISSION,
            "status": "blocked",
            "metadata": {
                "charlie_core": {"project_truth": {"workflow_template": "software_build"}},
                "review_packet": {"links": {"pr": "https://github.com/example/repo/pull/12"}},
            },
        }
        owner_queue.return_value = ([blocked], 200)
        transition.return_value = ({"success": True}, 200)

        def fake_runner(*_args, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"number":12,"url":"https://github.com/example/repo/pull/12","state":"OPEN","mergeable":"MERGEABLE","baseRefName":"main","headRefOid":"abc123","statusCheckRollup":[{"conclusion":"SUCCESS"}]}',
                stderr="",
            )

        result = charlie_mission_pickup.reconcile_blocked_pr_missions(run_subprocess=fake_runner)

        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(transition.call_args.args[1], "pr_ready")
        packet = transition.call_args.args[2]
        self.assertEqual(packet["review_status"], "ready_for_owner_review")
        self.assertEqual(packet["tested_revision"], "abc123")

    @patch("scripts.charlie_mission_pickup.transition_mission_review_state")
    @patch("scripts.charlie_mission_pickup._owner_queue_missions")
    def test_startup_reconciliation_does_not_reopen_resolved_historical_findings(self, owner_queue, transition):
        ready = {
            **MISSION,
            "status": "pr_ready",
            "metadata": {
                "charlie_core": {"project_truth": {"workflow_template": "software_build"}},
                "review_packet": {
                    "links": {"pr": "https://github.com/example/repo/pull/12"},
                    "tested_revision": "abc123",
                    "recommended_owner_decision": "approve_final_release",
                    "bugs": ["Resolved pre-build finding retained for audit."],
                    "evidence_reconciliation": {
                        "version": "charlie_evidence_reconciliation_v1",
                        "candidate_manifest": {"source_commit": "abc123"},
                        "active_blockers": [],
                        "requires_revalidation": [],
                        "resolved_findings": [{"state": "resolved", "finding": "pre-build finding"}],
                    },
                },
            },
        }
        owner_queue.return_value = ([ready], 200)
        transition.return_value = ({"success": True}, 200)

        def fake_runner(*_args, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"number":12,"url":"https://github.com/example/repo/pull/12","state":"OPEN","mergeable":"MERGEABLE","baseRefName":"main","headRefOid":"abc123","statusCheckRollup":[{"conclusion":"SUCCESS"}]}',
                stderr="",
            )

        result = charlie_mission_pickup.reconcile_blocked_pr_missions(run_subprocess=fake_runner)

        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(transition.call_args.args[1], "pr_ready")
        self.assertEqual(transition.call_args.args[2]["review_status"], "ready_for_owner_review")
        self.assertNotIn("return_to_stage", transition.call_args.args[2])

    @patch("scripts.charlie_mission_pickup.transition_mission_review_state")
    @patch("scripts.charlie_mission_pickup._owner_queue_missions")
    def test_reconcile_conflicting_pr_queues_publisher_recovery(self, owner_queue, transition):
        blocked = {
            **MISSION,
            "status": "blocked",
            "metadata": {"review_packet": {"links": {"pr": "https://github.com/example/repo/pull/13"}}},
        }
        owner_queue.return_value = ([blocked], 200)
        transition.return_value = ({"success": True}, 200)

        def fake_runner(*_args, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout='{"number":13,"state":"OPEN","mergeable":"CONFLICTING","baseRefName":"main","headRefOid":"def456","statusCheckRollup":[{"conclusion":"SUCCESS"}]}',
                stderr="",
            )

        result = charlie_mission_pickup.reconcile_blocked_pr_missions(run_subprocess=fake_runner)

        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(transition.call_args.args[1], "approved")
        packet = transition.call_args.args[2]
        self.assertEqual(packet["return_to_stage"], "publisher")
        self.assertEqual(packet["review_status"], "internal_recovery_queued")

    def test_browser_preflight_is_capability_only_by_default(self):
        self.assertFalse(charlie_mission_pickup._mission_requires_browser_preflight({
            "metadata": {"charlie_core": {"project_truth": {"workflow_template": "ui_product_build"}}},
        }))

    @patch("scripts.charlie_mission_pickup.threading.Thread")
    def test_analyst_cycle_is_queued_without_blocking_runner(self, thread):
        fake_thread = SimpleNamespace(is_alive=lambda: False, start=lambda: None)
        thread.return_value = fake_thread
        charlie_mission_pickup.ANALYST_THREAD = None

        result = charlie_mission_pickup._queue_analyst_cycle("MISSION-1", "mission_terminal")

        self.assertEqual(result["status"], "analyst_cycle_queued")
        thread.assert_called_once()

    @patch.dict("os.environ", {"CHARLIE_RUNNER_BASE_BRANCH": "charlie-runner-clean-base"})
    @patch("scripts.charlie_mission_pickup._recover_empty_git_operation_markers", return_value={"success": True, "status": "no_git_markers", "recovered": []})
    @patch("scripts.charlie_mission_pickup.subprocess.run")
    def test_ensure_base_branch_fails_instead_of_accepting_mission_branch(self, run, _markers):
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
    @patch("scripts.charlie_mission_pickup._recover_empty_git_operation_markers", return_value={"success": True, "status": "no_git_markers", "recovered": []})
    @patch("scripts.charlie_mission_pickup.subprocess.run")
    def test_ensure_base_branch_verifies_switch_result(self, run, _markers):
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

    def test_empty_git_rebase_marker_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "rebase-merge"
            marker.mkdir()

            def fake_run(command, **_kwargs):
                path = marker if command[-1] == "rebase-merge" else Path(tmp) / "rebase-apply"
                return SimpleNamespace(returncode=0, stdout=f"{path}\n", stderr="")

            with patch("scripts.charlie_mission_pickup.subprocess.run", side_effect=fake_run):
                result = charlie_mission_pickup._recover_empty_git_operation_markers(repo_root=Path(tmp))

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "empty_git_markers_recovered")
        self.assertFalse(marker.exists())

    def test_nonempty_git_rebase_marker_is_never_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "rebase-merge"
            marker.mkdir()
            (marker / "git-rebase-todo").write_text("pick abc", encoding="utf-8")

            def fake_run(command, **_kwargs):
                path = marker if command[-1] == "rebase-merge" else Path(tmp) / "rebase-apply"
                return SimpleNamespace(returncode=0, stdout=f"{path}\n", stderr="")

            with patch("scripts.charlie_mission_pickup.subprocess.run", side_effect=fake_run):
                result = charlie_mission_pickup._recover_empty_git_operation_markers(repo_root=Path(tmp))

            self.assertFalse(result["success"])
            self.assertEqual(result["status"], "git_operation_in_progress")
            self.assertTrue(marker.exists())

    def test_generated_codex_chat_is_archived_before_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chat = root / "planning" / "CODEX_CHAT.md"
            chat.parent.mkdir(parents=True)
            chat.write_text("active mission evidence", encoding="utf-8")
            calls = []

            def fake_run(command, **_kwargs):
                calls.append(command)
                if command[:3] == ["git", "status", "--porcelain"]:
                    return SimpleNamespace(returncode=0, stdout=" M planning/CODEX_CHAT.md\n", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            result = charlie_mission_pickup._preserve_generated_codex_chat_before_switch(
                repo_root=root,
                codex_chat_path=chat,
                run_factory=fake_run,
            )
            backup = Path(result["backup_path"])
            self.assertEqual(backup.read_text(encoding="utf-8"), "active mission evidence")
            self.assertIn(["git", "restore", "--worktree", "--", "planning/CODEX_CHAT.md"], calls)
            self.assertEqual(result["status"], "codex_chat_preserved")

    def test_permission_denied_git_marker_becomes_typed_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "rebase-merge"
            fake_marker = Mock()
            fake_marker.is_absolute.return_value = True
            fake_marker.exists.side_effect = PermissionError("access denied")
            with patch("scripts.charlie_mission_pickup.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=f"{marker}\n", stderr="")), patch("modules.charlie.repository_guard.Path", return_value=fake_marker):
                result = charlie_mission_pickup._recover_empty_git_operation_markers(repo_root=Path(tmp))
        self.assertEqual(result["status"], "git_operation_marker_permission_denied")
        self.assertTrue(result["recoverable_by_supervisor"])

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    def test_pickup_reports_no_available_mission(self, list_owner_work_missions):
        list_owner_work_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "no_mission_available")
        list_owner_work_missions.assert_called_once_with("approved", limit=100)

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
        list_owner_work_missions.assert_called_once_with("approved", limit=100)

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
        list_owner_work_missions.assert_called_once_with("approved", limit=100)

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
        list_owner_work_missions.assert_called_once_with("approved", limit=100)

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

    @patch("scripts.charlie_mission_pickup.notify_main")
    def test_notification_normalizes_internal_levels_to_cli_contract(self, notify_main):
        captured = []
        notify_main.side_effect = lambda: captured.append(list(charlie_mission_pickup.sys.argv)) or 0

        self.assertEqual(charlie_mission_pickup._send_notification("running", "Started", "Work started"), 0)
        self.assertEqual(charlie_mission_pickup._send_notification("pr_ready", "Ready", "Review ready"), 0)
        self.assertEqual(charlie_mission_pickup._send_notification("needs_owner_approval", "Review", "Decision needed"), 0)

        levels = [argv[argv.index("--level") + 1] for argv in captured]
        self.assertEqual(levels, ["info", "success", "warning"])

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

    def test_refreshed_workflow_keeps_only_one_active_stage(self):
        current = [
            {"agent": "product_architect", "status": "active"},
            {"agent": "technical_architect", "status": "active"},
        ]
        planned = [
            {"agent": "product_architect", "status": "pending"},
            {"agent": "technical_architect", "status": "pending"},
            {"agent": "builder", "status": "pending"},
        ]

        merged = charlie_mission_pickup._merge_resumable_workflow(current, planned)

        self.assertEqual([item["agent"] for item in merged if item["status"] == "active"], ["product_architect"])

    @patch("scripts.charlie_mission_pickup.update_mission_vault")
    @patch("scripts.charlie_mission_pickup.build_core_plan")
    def test_refresh_core_plan_preserves_owner_builder_send_back(self, build_plan, update_vault):
        mission = {
            "mission_id": "MISSION-1",
            "metadata": {"review_packet": {"return_to_stage": "builder"}},
            "agent_workflow": [{"agent": "business_reviewer", "status": "blocked"}],
        }
        build_plan.return_value = {
            "version": "v1",
            "project_truth": {"pipeline_profile": "content", "workflow_template": "content", "workflow_right_sized": True},
            "agent_workflow": [
                {"agent": "business_reviewer", "status": "pending"},
                {"agent": "reviewer", "status": "pending"},
            ],
        }
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        result = charlie_mission_pickup._refresh_core_plan_for_pickup(mission)

        payload = update_vault.call_args.args[1]
        self.assertTrue(result["refreshed"])
        self.assertEqual(payload["mission_context_pack"]["agent_order"], ["builder", "business_reviewer", "reviewer"])
        self.assertEqual(payload["agent_workflow"][0]["agent"], "builder")
        self.assertEqual(payload["agent_workflow"][0]["status"], "active")

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
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_continuous_watch_does_not_rerun_existing_in_progress_mission(self, list_missions, write_heartbeat, execute_codex, sleep):
        def fake_list_missions(status="", limit=10, **_kwargs):
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

        list_missions.side_effect = fake_list_missions
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
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_recover_stranded_mission_blocks_and_notifies(self, list_missions, runner_status, update_status, update_vault, send_blocked):
        active = {
            **MISSION,
            "status": "in_progress",
            "mission_id": "CHARLIE-MISSION-STRANDED",
            "agent_workflow": [{"agent": "builder", "status": "active"}],
            "metadata": {"execution_lease": {"lease_id": "lease-1", "expires_at": "2020-01-01T00:00:00+00:00"}},
        }
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [active]}, 200)
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
        self.assertEqual(update_status.call_args.args[1], "approved")
        self.assertEqual(update_status.call_args.kwargs["expected_status"], "in_progress")
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["blocked_agent"], "builder")
        self.assertEqual(packet["return_to_stage"], "builder")
        send_blocked.assert_called_once()

    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_active_execution_observes_non_owner_queue_rows(self, list_missions):
        active = {
            **MISSION,
            "mission_id": "CHARLIE-MISSION-SYSTEM-ACTIVE",
            "status": "in_progress",
            "metadata": {"intake_quality": {"queue_class": "system_recovery"}},
        }
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [active]}, 200)

        result = charlie_mission_pickup._active_mission()

        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-SYSTEM-ACTIVE")
        list_missions.assert_called_once_with(status="in_progress", limit=1, compact=False)

    def test_live_process_is_never_recovered_from_idle_observer_shape(self):
        decision = charlie_mission_pickup._stranded_recovery_decision(
            {"mission_id": "CHARLIE-MISSION-IDLE"},
            {
                "status": "runner_stale_or_stopped",
                "active": False,
                "process_alive": True,
                "age_seconds": 20,
                "last_mission_id": "CHARLIE-MISSION-IDLE",
                "last_result_status": "active_mission_in_progress",
                "current_agent": "",
                "execution_artifact": "",
            },
        )

        self.assertFalse(decision["recover"])
        self.assertEqual(decision["reason"], "execution_alive_or_lease_not_expired")

    def test_stale_lease_less_observer_mission_is_recovered(self):
        decision = charlie_mission_pickup._stranded_recovery_decision(
            {
                "mission_id": "CHARLIE-MISSION-ORPHAN",
                "status": "in_progress",
                "updated_at": "2020-01-01T00:00:00+00:00",
                "metadata": {},
            },
            {
                "status": "runner_active",
                "active": True,
                "process_alive": True,
                "age_seconds": 10,
                "last_mission_id": "CHARLIE-MISSION-ORPHAN",
                "last_result_status": "active_mission_in_progress",
                "current_agent": "",
                "execution_artifact": "",
            },
        )

        self.assertTrue(decision["recover"])
        self.assertEqual(decision["reason"], "in_progress_missing_execution_lease_and_no_active_stage")

    @patch("scripts.charlie_mission_pickup._pid_alive", return_value=False)
    def test_expired_lease_uses_recorded_owner_pid_not_new_runner_pid(self, _pid_alive):
        decision = charlie_mission_pickup._stranded_recovery_decision(
            {"mission_id": "CHARLIE-OLD-RUN", "metadata": {"execution_lease": {
                "lease_id": "lease-old",
                "holder": "CharlHP:133340",
                "heartbeat_at": "2020-01-01T00:00:00+00:00",
                "ttl_seconds": 900,
            }}},
            {
                "status": "runner_active",
                "active": True,
                "process_alive": True,
                "age_seconds": 5,
                "last_mission_id": "",
            },
        )

        self.assertTrue(decision["recover"])
        self.assertEqual(decision["reason"], "execution_lease_owner_dead_and_expired")

    @patch("scripts.charlie_mission_pickup.get_mission")
    def test_dependency_must_be_terminal_before_pickup(self, get_mission):
        mission = {"metadata": {"depends_on_mission_ids": ["MISSION-DATA"]}}
        get_mission.return_value = ({"mission": {"status": "blocked"}}, 200)
        self.assertFalse(charlie_mission_pickup._mission_dependencies_ready(mission))
        get_mission.return_value = ({"mission": {"status": "deployed"}}, 200)
        self.assertTrue(charlie_mission_pickup._mission_dependencies_ready(mission))

    @patch("scripts.charlie_mission_pickup.get_mission")
    def test_dependency_status_is_cached_within_queue_scan(self, get_mission):
        get_mission.return_value = ({"mission": {"status": "done"}}, 200)
        cache = {}
        mission = {"metadata": {"depends_on_mission_ids": ["PARENT-1"]}}
        self.assertTrue(charlie_mission_pickup._mission_dependencies_ready(mission, status_cache=cache))
        self.assertTrue(charlie_mission_pickup._mission_dependencies_ready(mission, status_cache=cache))
        get_mission.assert_called_once_with("PARENT-1")

    def test_recovery_slice_does_not_wait_for_parent_it_repairs(self):
        mission = {"metadata": {
            "depends_on_mission_ids": ["PARENT-1"],
            "mission_family": {"relationship": "acceptance_recovery", "parent_mission_id": "PARENT-1"},
        }}
        self.assertTrue(charlie_mission_pickup._mission_dependencies_ready(mission))

    @patch("scripts.charlie_mission_pickup.list_owner_work_missions")
    @patch("scripts.charlie_mission_pickup.get_mission")
    def test_dependency_blocked_first_row_does_not_hide_runnable_recovery(self, get_mission, list_owner):
        blocked_child = {"mission_id": "CHILD", "metadata": {"depends_on_mission_ids": ["PARENT"]}}
        recovery = {"mission_id": "RECOVERY", "metadata": {"mission_family": {
            "relationship": "acceptance_recovery", "parent_mission_id": "BROKEN",
        }}}
        list_owner.return_value = ({"missions": [blocked_child, recovery]}, 200)
        get_mission.return_value = ({"mission": {"status": "blocked"}}, 200)
        rows, status = charlie_mission_pickup._owner_queue_missions(("approved",), limit=1)
        self.assertEqual(status, 200)
        self.assertEqual([row["mission_id"] for row in rows], ["RECOVERY"])
        list_owner.assert_called_once_with("approved", limit=100)

    def test_execution_lease_includes_expiry(self):
        lease = charlie_mission_pickup._execution_lease_packet("MISSION-1")
        self.assertIn("expires_at", lease)
        self.assertFalse(charlie_mission_pickup._execution_lease_expired(lease))

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

    @patch("scripts.charlie_mission_pickup.runner_environment_preflight", return_value={"success": True})
    @patch("scripts.charlie_mission_pickup.get_mission", return_value=({"mission": MISSION}, 200))
    @patch("scripts.charlie_mission_pickup._send_notification")
    @patch("scripts.charlie_mission_pickup.run_agent_execution_bridge_v2")
    def test_internal_recovery_notification_uses_supported_info_level(
        self,
        run_bridge,
        send_notification,
        _get_mission,
        _preflight,
    ):
        run_bridge.return_value = ({
            "success": True,
            "status": "agent_stage_recovery_queued",
            "mission_id": "CHARLIE-MISSION-ACTIVE",
            "mission_status": "approved",
            "agent": "qa_red_team",
            "block_disposition": {
                "block_class": "implementation_fix_required",
                "responsible_stage": "builder",
            },
        }, 202)

        result, status_code = charlie_mission_pickup.execute_codex_for_mission(
            "CHARLIE-MISSION-ACTIVE",
            notify=True,
            timeout_seconds=30,
        )

        self.assertEqual(status_code, 202)
        self.assertEqual(result["status"], "agent_stage_recovery_queued")
        send_notification.assert_called_once()
        self.assertEqual(send_notification.call_args.args[0], "info")

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_continuous_watch_waits_when_mission_is_active_without_execute_flag(self, list_missions, write_heartbeat, sleep):
        def fake_list_missions(status="", limit=10, **_kwargs):
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

        list_missions.side_effect = fake_list_missions

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
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_continuous_watch_waits_when_release_is_in_progress(self, list_missions, write_heartbeat, sleep):
        def fake_list_missions(status="", limit=10, **_kwargs):
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

        list_missions.side_effect = fake_list_missions

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
        # pr_ready is reconciled for stale GitHub state, but it is not treated as
        # an active mission and therefore cannot stop the approved pickup.
        self.assertIn("pr_ready", queried_statuses)
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


    @patch("scripts.charlie_mission_pickup.notify_main")
    def test_executive_only_suppresses_direct_core_noise(self, notify_main):
        with patch.dict("scripts.charlie_mission_pickup.os.environ", {"CHARLIE_CORE_NOTIFICATION_MODE": "executive_only"}, clear=False):
            self.assertEqual(charlie_mission_pickup._send_notification("blocked", "Retry", "recoverable", "M1"), 0)
        notify_main.assert_not_called()

    @patch("scripts.charlie_mission_pickup.notify_main", return_value=0)
    def test_owner_decision_notification_is_deduplicated(self, notify_main):
        charlie_mission_pickup.NOTIFICATION_FINGERPRINTS.clear()
        with patch.dict("scripts.charlie_mission_pickup.os.environ", {"CHARLIE_CORE_NOTIFICATION_MODE": "executive_only"}, clear=False):
            for _ in range(2):
                self.assertEqual(charlie_mission_pickup._send_notification("needs_owner_approval", "Decision", "Choose", "M1"), 0)
        notify_main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
