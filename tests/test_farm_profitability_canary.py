import unittest

from modules.oom_sakkie.farm_profitability_canary import reconcile_farm_profitability_canary


OBSERVATION = {
    "facts": [{"pig_id": "FIXTURE-11", "weight_kg": 41, "stage": "finisher"}],
    "source": "canonical_fixture", "observed_at": "2026-07-23T19:45:00Z",
}


def evidence(recommendation="reconcile_weight_stage"):
    return {
        agent: {"source": f"{agent}_fixture", "observed_at": "2026-07-23T19:45:00Z",
                "authority": "read_only", "recommendation": recommendation,
                "facts": [{"kind": "fixture"}]}
        for agent in ("herdmaster", "ledger", "oom-sakkie")
    }


class FarmProfitabilityCanaryTests(unittest.TestCase):
    def test_attributable_agents_agree_on_advisory_intent(self):
        result = reconcile_farm_profitability_canary(
            observation=OBSERVATION, evidence_by_agent=evidence())

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "agreement_ready")
        self.assertTrue(result["intent"]["advisory_only"])
        self.assertFalse(result["authority"]["writes"])
        self.assertEqual(result["agreement"]["recommendation"], "reconcile_weight_stage")

    def test_disagreement_is_surfaced_without_an_action(self):
        rows = evidence()
        rows["ledger"]["recommendation"] = "defer_until_new_weight"

        result = reconcile_farm_profitability_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertFalse(result["success"])
        self.assertTrue(result["agreement"]["disagreement_detected"])
        self.assertTrue(any("disagree" in item.lower() for item in result["unresolved_questions"]))
        self.assertEqual(result["authority"]["commercial_action"], "none")

    def test_missing_provenance_fails_closed(self):
        rows = evidence()
        del rows["herdmaster"]["source"]

        result = reconcile_farm_profitability_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertFalse(result["success"])
        self.assertIn("herdmaster source is required for attribution.", result["unresolved_questions"])

    def test_non_read_only_evidence_is_rejected(self):
        rows = evidence()
        rows["ledger"]["authority"] = "write"

        result = reconcile_farm_profitability_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertFalse(result["success"])
        self.assertIn("ledger evidence must declare read_only authority.", result["unresolved_questions"])


if __name__ == "__main__":
    unittest.main()
