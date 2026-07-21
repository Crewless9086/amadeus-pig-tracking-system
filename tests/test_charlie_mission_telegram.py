import unittest

from scripts import charlie_mission_telegram


MISSION = {
    "mission_id": "C79E0A47E2DE",
    "title": "Fix CHARLIE visual evidence",
    "status": "blocked",
    "metadata": {"review_packet": {"blocked_reason": "Screenshot evidence missing", "recommended_next_action": "Return to builder"}},
    "agent_workflow": [
        {"agent": "planner", "status": "complete"},
        {"agent": "builder", "status": "blocked"},
    ],
}


class CharlieMissionTelegramTests(unittest.TestCase):
    def setUp(self):
        self.mission = dict(MISSION)
        self.status_calls = []
        self.review_calls = []

    def list_loader(self, **_kwargs):
        return {"missions": [self.mission]}, 200

    def get_loader(self, mission_id):
        return {"mission": self.mission}, 200

    def status_updater(self, mission_id, status, **kwargs):
        self.status_calls.append((mission_id, status, kwargs))
        self.mission["status"] = status
        return {"status": "ok"}, 200

    def review_updater(self, mission_id, decision, **kwargs):
        self.review_calls.append((mission_id, decision, kwargs))
        self.mission["status"] = "approved" if decision == "send_back" else "release_approved"
        return {"status": "ok"}, 200

    def test_callback_contains_compact_mission_token(self):
        callback = charlie_mission_telegram.mission_callback(self.mission["mission_id"], "open")
        self.assertLessEqual(len(callback.encode("utf-8")), 64)
        self.assertNotIn(self.mission["mission_id"], callback)

    def test_open_resolves_live_mission_id(self):
        result, mission = charlie_mission_telegram.handle_callback(
            charlie_mission_telegram.mission_callback(self.mission["mission_id"]),
            list_loader=self.list_loader,
            get_loader=self.get_loader,
            status_updater=self.status_updater,
            review_updater=self.review_updater,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.mission_id, self.mission["mission_id"])
        self.assertEqual(mission["status"], "blocked")

    def test_send_back_reloads_and_uses_review_store(self):
        result, mission = charlie_mission_telegram.handle_callback(
            charlie_mission_telegram.mission_callback(self.mission["mission_id"], "sendback", "builder"),
            list_loader=self.list_loader,
            get_loader=self.get_loader,
            status_updater=self.status_updater,
            review_updater=self.review_updater,
        )
        self.assertTrue(result.ok)
        self.assertEqual(self.review_calls[0][1], "send_back")
        self.assertEqual(self.review_calls[0][2]["target_stage"], "builder")
        self.assertEqual(mission["status"], "approved")

    def test_stale_action_is_refused(self):
        self.mission["status"] = "in_progress"
        result, _mission = charlie_mission_telegram.handle_callback(
            charlie_mission_telegram.mission_callback(self.mission["mission_id"], "sendback", "builder"),
            list_loader=self.list_loader,
            get_loader=self.get_loader,
            status_updater=self.status_updater,
            review_updater=self.review_updater,
        )
        self.assertFalse(result.ok)
        self.assertIn("action_not_allowed", result.reason)
        self.assertEqual(self.review_calls, [])

    def test_card_explains_block_and_runner(self):
        text = charlie_mission_telegram.mission_card_text(self.mission, {"status": "runner_active"})
        self.assertIn("Screenshot evidence missing", text)
        self.assertIn("runner_active", text)
        self.assertIn("50%", text)

    def test_pr_ready_migration_allows_release_and_explains_separate_protected_operation(self):
        self.mission["status"] = "pr_ready"
        self.mission["metadata"] = {"review_packet": {
            "changed_files": ["supabase/migrations/202607160001_example.sql"],
            "test_evidence": ["Focused tests passed."],
        }}
        card = charlie_mission_telegram.mission_card_text(self.mission)
        keyboard = charlie_mission_telegram.mission_keyboard(self.mission)
        labels = [row[0]["text"] for row in keyboard["inline_keyboard"]]
        self.assertIn("READY TO APPROVE", card)
        self.assertIn("protected operations remain separately owner-gated", card)
        self.assertIn("Approve Release", labels)
        self.assertIn("Show Requirements", labels)


if __name__ == "__main__":
    unittest.main()
