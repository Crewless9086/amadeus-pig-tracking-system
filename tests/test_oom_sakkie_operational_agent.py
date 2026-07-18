import unittest
from unittest.mock import patch

from modules.agents.ledger import run_ledger
from modules.agents.oom_sakkie import run_oom_sakkie


class OomSakkieOperationalAgentTests(unittest.TestCase):
    @patch("modules.agents.oom_sakkie.delegate_to_agent")
    def test_oom_sakkie_coordinates_herdmaster_without_write_authority(self, delegate):
        delegate.return_value = ({
            "success": True, "direct_answer": "There are 12 pigs.", "summary": "Herd checked.",
            "facts": [{"name": "count", "value": 12}], "metrics": {"count": 12}, "breakdown": {},
            "anomalies": [], "recommendations": [], "unresolved_questions": [],
            "sources": [{"name": "pig_current_state"}], "confidence": .99, "agent": {"agent_id": "herdmaster"},
        }, 200)
        result = run_oom_sakkie({"question": "How are the pigs doing?"})
        self.assertTrue(result["success"])
        self.assertEqual(result["direct_answer"], "There are 12 pigs.")
        self.assertFalse(result["write_authority"])
        self.assertEqual(result["delegations"][0]["agent_id"], "herdmaster")

    def test_ledger_validates_precomputed_deterministic_price_evidence(self):
        result = run_ledger({"known_context": {"pricing": {"found": True, "unit_price": 800, "currency": "ZAR", "source": "supabase"}}})
        self.assertTrue(result["facts"][0]["value"])
        self.assertIn("800", result["direct_answer"])
        self.assertEqual(result["confidence"], .99)


if __name__ == "__main__":
    unittest.main()
