import unittest

from modules.charlie.private_response import build_executive_response_packet, spoken_summary


class CharliePrivateResponseTests(unittest.TestCase):
    def test_packet_separates_spoken_display_evidence_and_commitments(self):
        packet = build_executive_response_packet(
            "CORE is active. Recommendation: leave the runner working.",
            plan={"subject": {"type": "core"}},
            evidence=[{"intent_type": "read_core_status", "domain": "engineering", "source_of_truth": "Supabase", "observed_at": "2026-07-18T10:00:00Z", "success": True, "result": {"summary": "One mission active."}}],
            context={"commitments": [{"mission_id": "M-1", "status": "monitoring"}]},
        )
        self.assertIn("CORE is active", packet["spoken_summary"])
        self.assertEqual(packet["verified_facts"], ["One mission active."])
        self.assertEqual(packet["evidence"][0]["source"], "Supabase")
        self.assertEqual(packet["commitments"][0]["mission_id"], "M-1")
        self.assertEqual(packet["confidence"], 1.0)

    def test_spoken_summary_is_bounded_at_sentence_boundary(self):
        text = "First fact. " + "Second detail " * 80 + ". Final note."
        self.assertLessEqual(len(spoken_summary(text)), 520)

    def test_spoken_summary_removes_markdown_without_losing_words(self):
        text = "**CORE is active.** [Open mission](https://example.test) and `review` it.\n- Next action"
        summary = spoken_summary(text)
        self.assertEqual(summary, "CORE is active. Open mission and review it. Next action")
        self.assertNotIn("*", summary)
        self.assertNotIn("https://", summary)

    def test_packet_attributes_evidence_to_operational_agent(self):
        packet = build_executive_response_packet("You have six pigs.", evidence=[{
            "intent_type": "read_farm_status", "domain": "farm", "success": True,
            "result": {"summary": "Herd verified.", "direct_answer": "There are 6 pigs.", "agent": {"agent_id": "herdmaster", "name": "Herdmaster"}},
        }])
        self.assertEqual(packet["evidence"][0]["agent"]["agent_id"], "herdmaster")
        self.assertEqual(packet["evidence"][0]["direct_answer"], "There are 6 pigs.")

    def test_packet_confidence_inherits_agent_evidence_confidence(self):
        packet = build_executive_response_packet("There is a source mismatch.", evidence=[{
            "intent_type": "read_farm_status", "domain": "farm", "success": True,
            "result": {"summary": "Mismatch found.", "confidence": 0.94},
        }])
        self.assertEqual(packet["confidence"], 0.94)


if __name__ == "__main__":
    unittest.main()
