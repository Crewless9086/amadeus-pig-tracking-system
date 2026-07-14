import unittest
from pathlib import Path


class CharlieMissionControlFrontendTests(unittest.TestCase):
    def test_mission_control_uses_glanceable_full_page_contract(self):
        template = Path("templates/charlie-v2.html").read_text(encoding="utf-8")
        script = Path("static/js/charlieMissionControlV2.js").read_text(encoding="utf-8")

        for element_id in (
            "missionSummaryStrip",
            "queueHealthChip",
            "activeAgentChip",
            "queueList",
            "workflowPanel",
            "actionPanel",
        ):
            self.assertIn(f'id="{element_id}"', template)
        self.assertIn("renderMissionSummary", script)
        self.assertIn("firstUsefulTab", script)
        self.assertIn("/api/charlie/build-relay/mission-control", script)
        self.assertIn("state.initialized && allLoadedMissions().length", script)
        self.assertIn('href="/charlie-agents"', template)

    def test_send_back_requires_owner_comments_and_target_stage(self):
        template = Path("templates/charlie-v2.html").read_text(encoding="utf-8")
        script = Path("static/js/charlieMissionControlV2.js").read_text(encoding="utf-8")

        self.assertIn("openSendBackDrawer", script)
        self.assertIn('id="sendBackComments"', script)
        self.assertIn('id="sendBackStage"', script)
        self.assertIn("if (!comments)", script)
        self.assertIn("target_stage: targetStage", script)
        self.assertIn('if (!agents.includes("builder")) agents.unshift("builder")', script)
        self.assertIn('id="reviewDrawer"', template)


if __name__ == "__main__":
    unittest.main()
