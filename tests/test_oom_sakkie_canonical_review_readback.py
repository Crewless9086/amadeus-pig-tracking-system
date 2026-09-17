import unittest
from unittest import mock

from modules.oom_sakkie.agent_runtime import get_agent_runtime_review_packet, get_jarvis_owner_review_packet
from modules.oom_sakkie.canonical_review_readback import get_canonical_review_readback
from modules.oom_sakkie.learning_packet import build_learning_packet
from modules.oom_sakkie import tools


class CanonicalReviewReadbackTests(unittest.TestCase):
    def test_canonical_owner_queue_is_used_without_markdown(self):
        def lister(**kwargs):
            self.assertEqual(kwargs, {"status": "owner_queue", "limit": 12, "compact": True})
            return {"missions": [{"mission_id": "CMQ-1", "status": "owner_review",
                "updated_at": "2026-08-15T00:00:00Z", "metadata": {"review_packet": {
                    "review_generation": "EXEC-1:abc", "review_status": "ready",
                    "recommended_next_action": "approve"}}}]}, 200
        result = get_canonical_review_readback(mission_lister=lister)
        self.assertTrue(result["success"])
        self.assertEqual(result["missions"][0]["mission_id"], "CMQ-1")
        self.assertFalse(result["historical_pointer_loaded"])
        self.assertFalse(result["historical_pointer_authority"])

    def test_missing_canonical_truth_is_unknown_and_zero_effect(self):
        result = get_canonical_review_readback(mission_lister=lambda **_: ({}, 503))
        self.assertFalse(result["success"])
        self.assertEqual(result["state"], "Unknown")
        for key in ("prompts_sent", "provider_messages", "missions_created",
                    "customer_writes", "farm_writes", "hardware_commands"):
            self.assertEqual(result[key], 0)

    def test_runtime_packets_use_injected_canonical_truth(self):
        canonical = {"success": True, "status": "canonical_review_ready", "missions": [{"mission_id": "CMQ-2"}]}
        packet = get_agent_runtime_review_packet(review_reader=lambda: canonical)
        owner = get_jarvis_owner_review_packet(review_reader=lambda: canonical)
        self.assertEqual(packet["canonical_review"], canonical)
        self.assertEqual(owner["current_review"]["canonical_review"], canonical)
        self.assertNotIn("handoff_file", owner["current_review"])

    def test_general_owner_packet_does_not_expose_canonical_missions(self):
        owner = get_jarvis_owner_review_packet()
        review = owner["current_review"]["canonical_review"]
        self.assertEqual(review["status"], "canonical_review_restricted")
        self.assertEqual(review["missions"], [])
        self.assertEqual(review["mission_count"], 0)

    def test_learning_packet_never_recommends_historical_handoff(self):
        packet, status = build_learning_packet({"kind": "routing_review", "title": "x"})
        self.assertEqual(status, 200)
        joined = "\n".join(packet["recommended_files"]) + packet["brief"]
        self.assertNotIn("CLAUDE_REVIEW_HANDOFF", joined)
        self.assertIn("canonical_review_readback.py", joined)

    def test_owner_tool_links_use_canonical_queue(self):
        with mock.patch.object(tools, "get_jarvis_owner_review_packet", return_value={
                "review_readiness": {}, "current_review": {}, "summary_status": "Unknown"}):
            result = tools.jarvis_owner_review_packet_handler({})
        self.assertEqual(result["links"], [{"label": "Canonical CORE Review Queue", "href": "/charlie"}])


if __name__ == "__main__":
    unittest.main()
