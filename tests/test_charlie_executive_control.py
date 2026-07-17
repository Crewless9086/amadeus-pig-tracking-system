import unittest
from datetime import datetime, timedelta, timezone

from modules.charlie.executive_assurance import doctrine_promotion_decision, evaluate_autonomy_metrics
from modules.charlie.executive_control import (
    authority_decision, build_executive_cycle, capability_tier,
    portfolio_priority, recovery_decision, stable_fingerprint,
)


POLICIES = [{
    "policy_id": "POLICY-1", "capability": "core.internal_recovery",
    "authority_tier": "auto", "enabled": True, "expires_at": None,
}]


def blocked(owner_required=False, block_class="implementation_fix_required"):
    return {
        "mission_id": "MISSION-1", "status": "blocked", "urgency": "P1",
        "metadata": {"review_packet": {"blocked_reason": "focused tests failed", "block_disposition": {
            "block_class": block_class, "owner_required": owner_required,
            "responsible_stage": "builder", "reason": "focused tests failed",
        }}},
    }


class CharlieExecutiveControlTests(unittest.TestCase):
    def test_red_zone_cannot_be_delegated_by_normal_policy(self):
        result = authority_decision("core.internal_recovery", POLICIES, risk_flags=["payment"])
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authority_tier"], "charl_human")

    def test_missing_policy_fails_closed(self):
        self.assertFalse(authority_decision("core.unknown", POLICIES)["allowed"])

    def test_expired_policy_fails_closed(self):
        policy = {**POLICIES[0], "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
        self.assertFalse(authority_decision("core.internal_recovery", [policy])["allowed"])

    def test_recoverable_block_schedules_targeted_recovery(self):
        result = recovery_decision(blocked(), POLICIES)
        self.assertEqual(result["action"], "schedule_recovery")
        self.assertEqual(result["target_stage"], "builder")
        self.assertTrue(result["idempotency_key"].startswith("recover:MISSION-1:"))

    def test_owner_block_never_auto_recovers(self):
        result = recovery_decision(blocked(owner_required=True), POLICIES)
        self.assertEqual(result["action"], "escalate_owner")

    def test_cycle_keeps_unrelated_queue_productive(self):
        missions = [blocked(), {"mission_id": "MISSION-2", "status": "approved", "urgency": "P0", "metadata": {}}]
        policies = POLICIES + [{"policy_id": "P2", "capability": "core.queue_continue", "authority_tier": "auto", "enabled": True}]
        cycle = build_executive_cycle(missions, policies, runner={})
        actions = [item["action"] for item in cycle["commands"]]
        self.assertIn("schedule_recovery", actions)
        self.assertIn("ensure_queue_progress", actions)

    def test_queue_progress_fails_closed_without_policy(self):
        cycle = build_executive_cycle([{"mission_id": "MISSION-2", "status": "approved"}], [], runner={})
        self.assertFalse(any(item.get("action") == "ensure_queue_progress" for item in cycle["commands"]))
        self.assertEqual(cycle["escalations"][0]["reason"], "delegation_policy_missing")

    def test_portfolio_prioritizes_revenue_and_urgency(self):
        high = {"status": "approved", "urgency": "P0", "metadata": {"queue": {"revenue_impact": 15}}}
        low = {"status": "approved", "urgency": "P3", "metadata": {}}
        self.assertGreater(portfolio_priority(high), portfolio_priority(low))

    def test_fingerprint_is_deterministic(self):
        self.assertEqual(stable_fingerprint({"b": 2, "a": 1}), stable_fingerprint({"a": 1, "b": 2}))

    def test_trust_requires_observed_history(self):
        self.assertEqual(capability_tier({"runs": 9, "clean_passes": 9}), "watch")
        self.assertEqual(capability_tier({"runs": 20, "clean_passes": 19}), "delegated")
        self.assertEqual(capability_tier({"runs": 50, "clean_passes": 49}), "auto")
        self.assertEqual(capability_tier({"runs": 50, "clean_passes": 50, "escaped_defects": 1}), "watch")

    def test_assurance_requires_every_metric(self):
        result = evaluate_autonomy_metrics({"unattended_completion_rate": 1.0})
        self.assertFalse(result["promotion_allowed"])

    def test_assurance_passes_only_full_target_set(self):
        metrics = {
            "unattended_completion_rate": .96, "recoverable_resolution_rate": .99,
            "false_human_escalation_rate_max": .01, "deterministic_gate_pass_rate": 1,
            "unauthorized_red_zone_actions_max": 0, "crash_state_loss_max": 0,
            "substantial_owner_review_rate_max": .05, "delegated_acceptance_rate": .96,
            "improvement_effectiveness_rate": .81,
        }
        self.assertTrue(evaluate_autonomy_metrics(metrics)["promotion_allowed"])

    def test_doctrine_promotion_requires_source_tests_and_owner(self):
        evidence = {"source_refs": ["https://example.test/primary"]}
        self.assertFalse(doctrine_promotion_decision(evidence)["allowed"])
        self.assertTrue(doctrine_promotion_decision(evidence, owner_approved=True, deterministic_tests_passed=True)["allowed"])


if __name__ == "__main__":
    unittest.main()
