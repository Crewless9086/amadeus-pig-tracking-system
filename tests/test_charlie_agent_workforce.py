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
            analyst_learning={
                "success": True,
                "status": "analyst_scorecard_ready",
                "scorecard": {
                    "observations": 12,
                    "proposals_total": 3,
                    "pending_proposals": 1,
                    "validated_improvements": 1,
                    "effective_improvements": 1,
                    "validated_effectiveness_rate": 1.0,
                    "stage": "proposal_ready",
                },
            },
            beacon_learning={
                "success": True,
                "status": "beacon_workforce_scorecard_ready",
                "scorecard": {
                    "stage": "owner_approved_posting",
                    "progress_percent": 34,
                    "approved_assets": 1,
                    "production_posts_sent": 1,
                    "production_performance_events": 0,
                    "qualified_buyer_leads": 0,
                    "tracked_spend_zar": 0,
                    "media_review_backlog": 0,
                    "scheduling_enabled": False,
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
        analyst = next(agent for agent in packet["agents"] if agent["id"] == "analyst")
        self.assertTrue(analyst["evidence"]["measured"])
        self.assertEqual(analyst["candidate_count"], 1)
        self.assertEqual(analyst["owner_action"], "Review ANALYST proposals")
        beacon = next(agent for agent in packet["agents"] if agent["id"] == "beacon")
        self.assertEqual(beacon["team"], "Marketing")
        self.assertEqual(beacon["evidence"]["progress_percent"], 34)
        self.assertEqual(beacon["stage"], "owner_approved_posting")
        self.assertTrue(beacon["links"])

    def test_unmeasured_agents_report_not_measured_instead_of_fake_percent(self):
        packet = build_agent_workforce_packet(registry={"agents": []})
        herdmaster = next(agent for agent in packet["agents"] if agent["id"] == "herdmaster")
        self.assertFalse(herdmaster["evidence"]["measured"])
        self.assertIsNone(herdmaster["evidence"]["progress_percent"])
        self.assertEqual(herdmaster["evidence"]["label"], "Not measured")

    def test_packet_preserves_executive_core_and_transport_boundaries(self):
        packet = build_agent_workforce_packet(registry={"agents": []})
        agents = {agent["id"]: agent for agent in packet["agents"]}
        connections = {(row["from"], row["to"]) for row in packet["map"]["connections"]}

        self.assertEqual(agents["charlie"]["name"], "CHARLIE")
        self.assertIn("private digital executive", agents["charlie"]["role"].lower())
        self.assertEqual(agents["charlie-core"]["name"], "CORE")
        self.assertIn(("owner", "charlie"), connections)
        self.assertIn(("charlie", "charlie-core"), connections)
        self.assertIn(("charlie-core", "analyst"), connections)
        self.assertEqual(agents["fred"]["team"], "Private Transfers")
        self.assertIn("client-facing transport", agents["fred"]["role"].lower())
        self.assertNotIn("finance", agents["fred"]["role"].lower())
        self.assertIn(("beacon", "beacon-strategy"), connections)
        self.assertIn(("beacon", "beacon-creative"), connections)
        self.assertIn(("beacon", "beacon-media"), connections)
        self.assertIn(("beacon", "beacon-scheduler"), connections)
        self.assertIn(("beacon", "beacon-performance"), connections)


if __name__ == "__main__":
    unittest.main()
