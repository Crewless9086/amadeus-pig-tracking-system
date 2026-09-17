import unittest

from modules.charlie.executive_governance import build_approval_bundle, evaluate_mission_class, research_observation


class CharlieExecutiveGovernanceTests(unittest.TestCase):
    def test_related_decisions_are_one_owner_bundle(self):
        bundle = build_approval_bundle("GOAL-1", [
            {"title": "Apply migration", "risk_flags": ["destructive_migration"], "evidence": {"tests": "green"}},
            {"title": "Release", "risk_flags": []},
        ])
        self.assertEqual(len(bundle["decisions"]), 2)
        self.assertEqual(bundle["authority_tier"], "charl_human")
        self.assertIn("destructive_migration", bundle["red_zone_flags"])

    def test_eval_requires_all_deterministic_gates(self):
        spec = {"scenarios": ["happy", "restart"], "required_gates": ["unit", "crash"], "minimum_pass_rate": 1}
        result = evaluate_mission_class(spec, {"scenarios": {"happy": True, "restart": True}, "gates": {"unit": True, "crash": False}})
        self.assertFalse(result["passed"])
        self.assertEqual(result["missing_gates"], ["crash"])

    def test_eval_passes_only_complete_evidence(self):
        spec = {"scenarios": ["happy", "restart"], "required_gates": ["unit"], "minimum_pass_rate": 1}
        result = evaluate_mission_class(spec, {"scenarios": {"happy": True, "restart": True}, "gates": {"unit": True}})
        self.assertTrue(result["passed"])

    def test_research_requires_source_and_never_auto_activates(self):
        result = research_observation(business_area="sales", topic="market change", source_url="https://example.com/official", source_kind="official")
        self.assertTrue(result["accepted"])
        self.assertFalse(result["observation"]["auto_activate"])
        self.assertTrue(result["observation"]["owner_review_required"])

    def test_research_rejects_unsourced_claim(self):
        self.assertFalse(research_observation(business_area="sales", topic="claim", source_url="")["accepted"])


if __name__ == "__main__":
    unittest.main()
