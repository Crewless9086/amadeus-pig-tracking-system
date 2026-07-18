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


if __name__ == "__main__":
    unittest.main()
