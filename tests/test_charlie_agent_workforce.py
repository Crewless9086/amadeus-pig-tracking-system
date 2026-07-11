import unittest

from modules.charlie.agent_workforce import build_agent_workforce_packet


class CharlieAgentWorkforceTests(unittest.TestCase):
    def test_packet_uses_measured_sam_evidence_without_auto_graduation(self):
        packet = build_agent_workforce_packet(
            mission_summary={"counts": {"done": 8, "blocked": 2, "in_progress": 1, "pr_ready": 3}},
            runner={"status": "active"},
            trust_entries={
                "mission_loop_foundation": {
                    "runs": "20", "passes": "19", "failures": "1", "tier": "auto",
                }
            },
            registry={"agents": []},
            sam_learning={
                "success": True,
                "status": "sam_live_stock_learning_scorecard_ready",
                "scorecard": {
                    "captured_owner_replies": 50,
                    "conversation_count": 10,
                    "unchanged_rate": 0.82,
                    "accepted_or_minor_edit_rate": 0.96,
                    "production_sample_target": 100,
                    "complete_conversation_target": 20,
                    "graduation": {
                        "classes": {
                            "location_question": {
                                "events": 24,
                                "consecutive_safe_accepted": 22,
                                "unchanged_rate": 0.84,
                                "narrow_auto_send_candidate": True,
                            }
                        }
                    },
                },
            },
        )

        self.assertTrue(packet["success"])
        sam = next(agent for agent in packet["agents"] if agent["id"] == "sam-live-stock")
        self.assertEqual(sam["evidence"]["progress_percent"], 50)
        self.assertEqual(sam["candidate_count"], 1)
        self.assertEqual(sam["stage"], "graduation_candidate")
        self.assertFalse(packet["authority"]["auto_graduation"])
        self.assertTrue(packet["authority"]["owner_activation_required"])

    def test_unmeasured_agents_report_not_measured_instead_of_fake_percent(self):
        packet = build_agent_workforce_packet(registry={"agents": []})
        herdmaster = next(agent for agent in packet["agents"] if agent["id"] == "herdmaster")
        self.assertFalse(herdmaster["evidence"]["measured"])
        self.assertIsNone(herdmaster["evidence"]["progress_percent"])
        self.assertEqual(herdmaster["evidence"]["label"], "Not measured")


if __name__ == "__main__":
    unittest.main()
