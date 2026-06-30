import tempfile
import unittest
from pathlib import Path
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
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_pickup_reports_no_available_mission(self, list_missions):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "no_mission_available")

    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_dry_run_does_not_write_or_update_status(self, list_missions):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)

        with patch("scripts.charlie_mission_pickup.update_mission_status") as update_status:
            result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-123")
        self.assertEqual(result["runner_mode"], "code_test_pr")
        update_status.assert_not_called()

    @patch("scripts.charlie_mission_pickup.list_missions")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    def test_pickup_writes_codex_chat_and_marks_in_progress(self, update_status, list_missions):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "in_progress"}, 200)

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

    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_pickup_content_includes_level_four_merge_guidance(self, list_missions):
        mission = dict(MISSION)
        mission["approval_level"] = "LEVEL 4"
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [mission]}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)
        content = charlie_mission_pickup._codex_chat_content(mission)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["runner_mode"], "merge_after_verification")
        self.assertIn("Runner mode: merge_after_verification", content)
        self.assertIn("LEVEL 4: release/merge authority", content)

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_watch_mode_can_timeout_without_pickup(self, list_missions, write_heartbeat, sleep):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

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
    @patch("scripts.charlie_mission_pickup.execute_codex_for_mission")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_continuous_watch_executes_active_in_progress_when_enabled(self, list_missions, write_heartbeat, execute_codex, sleep):
        def fake_list_missions(status="approved", limit=10):
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
        execute_codex.return_value = ({
            "success": True,
            "status": "codex_execution_completed",
            "mission_id": "CHARLIE-MISSION-ACTIVE",
            "mission_status": "pr_ready",
        }, 200)

        result, status_code = charlie_mission_pickup.watch_for_mission(
            interval_seconds=5,
            max_checks=1,
            continuous=True,
            execute_codex=True,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-ACTIVE")
        execute_codex.assert_called_once()
        write_heartbeat.assert_called()
        sleep.assert_not_called()

    @patch("scripts.charlie_mission_pickup.time.sleep")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_continuous_watch_waits_when_mission_is_active_without_execute_flag(self, list_missions, write_heartbeat, sleep):
        def fake_list_missions(status="approved", limit=10):
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
        def fake_list_missions(status="approved", limit=10):
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
    @patch("scripts.charlie_mission_pickup.process_release_approved_mission")
    @patch("scripts.charlie_mission_pickup.write_runner_heartbeat")
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_continuous_watch_processes_release_approved_when_enabled(self, list_missions, write_heartbeat, process_release, sleep):
        def fake_list_missions(status="approved", limit=10):
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

        list_missions.side_effect = fake_list_missions
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
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_pr_merged")
        process_release.assert_called_once_with(
            "CHARLIE-MISSION-RELEASE",
            notify=False,
            auto_close_no_release=False,
            auto_merge_pr=True,
        )
        write_heartbeat.assert_called()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
