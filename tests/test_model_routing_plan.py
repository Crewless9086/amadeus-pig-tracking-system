import unittest

from scripts import model_routing_plan, trust_log


DISABLED_BUDGET = {"policy": {"live_model_api_calls_enabled": False}, "caps": {}}


class ModelRoutingPlanTests(unittest.TestCase):
    def test_luna_for_low_risk_triage_but_live_call_stays_disabled(self):
        decision = model_routing_plan.recommend_route("mission_triage", risk_level="low", budget_config=DISABLED_BUDGET)
        self.assertEqual(decision.recommended_model, "gpt-5.6-luna")
        self.assertFalse(decision.live_call_allowed)

    def test_terra_for_normal_review(self):
        decision = model_routing_plan.recommend_route("normal_pr_review", budget_config=DISABLED_BUDGET)
        self.assertEqual(decision.recommended_model, "gpt-5.6-terra")

    def test_sol_for_high_risk_and_owner_approval(self):
        decision = model_routing_plan.recommend_route("security_review", risk_level="high", budget_config=DISABLED_BUDGET)
        self.assertEqual(decision.recommended_model, "gpt-5.6-sol")
        self.assertTrue(decision.owner_approval_required)

    def test_red_zone_is_blocked_before_model_selection(self):
        decision = model_routing_plan.recommend_route("customer_send", budget_config=DISABLED_BUDGET)
        self.assertEqual(decision.recommended_model, "none")
        self.assertEqual(decision.blocked_reason, "red_zone")

    def test_trust_watch_prevents_live_route(self):
        entry = trust_log.TrustEntry(skill="mission_model_routing", tier="watch")
        decision = model_routing_plan.recommend_route(
            "docs_summary", budget_config=DISABLED_BUDGET, trust_entries={entry.skill: entry}
        )
        self.assertFalse(decision.live_call_allowed)
        self.assertIn(decision.blocked_reason, {"trust_tier_watch", "model_routing_dry_run_only"})


if __name__ == "__main__":
    unittest.main()
