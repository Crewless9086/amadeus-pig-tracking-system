import unittest
from datetime import datetime, timedelta, timezone

from modules.beacon.autonomy_readiness import APPROVED_POLICY, AUTHORITY, evaluate_beacon_advisory_readiness


NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def evidence():
    campaigns = []
    approvals = []
    attributions = []
    recommendations = []
    budgets = []
    for index in range(10):
        observed = (NOW - timedelta(days=index * 4)).isoformat()
        campaigns.append({"evidence_id": f"c{index}", "status": "completed", "completed_at": observed, "observed_at": observed})
        approvals.append({"evidence_id": f"a{index}", "observed_at": observed, "proposed_hash": f"h{index}", "approved_hash": f"h{index}", "edit_classification": "unedited"})
        attributions.append({"evidence_id": f"x{index}", "observed_at": observed, "disposition": "complete", "campaign_id": f"c{index}", "source_ref": f"sam:{index}"})
        recommendations.append({"evidence_id": f"r{index}", "observed_at": observed, "matured": True, "outcome_score": 1, "outcome_label": "accurate", "caller_classification": "inaccurate"})
        budgets.append({"evidence_id": f"b{index}", "observed_at": observed, "authority_state": "owner_approved", "currency": "ZAR", "window": "campaign", "actual_spend": 50, "cap": 100})
    incidents = [{"evidence_id": "i0", "observed_at": NOW.isoformat(), "severity": "low", "resolved": True}]
    trust = [{"evidence_id": f"t{i}", "observed_at": (NOW - timedelta(days=i * 7)).isoformat(), "evaluated": True, "clean": True, "authority_breach": False} for i in range(8)]
    return {"campaigns": campaigns, "approvals": approvals, "attributions": attributions, "recommendations": recommendations, "incidents": incidents, "trust_weeks": trust, "budgets": budgets}


class BeaconAutonomyReadinessTests(unittest.TestCase):
    def test_positive_path_prepares_exactly_one_owner_notification(self):
        result = evaluate_beacon_advisory_readiness(evidence(), now=NOW)
        self.assertTrue(result["ready"])
        self.assertEqual(result["state"], "ready_for_owner_review")
        self.assertEqual(result["notification"]["type"], "threshold_met")
        self.assertEqual(result["authority"], AUTHORITY)
        prior = [{"ready": True, "notification_key": result["notification"]["notification_key"]}]
        repeated = evaluate_beacon_advisory_readiness(evidence(), prior_evaluations=prior, now=NOW)
        self.assertIsNone(repeated["notification"])

    def test_each_gate_fails_independently(self):
        mutations = {
            "campaign_evidence": lambda e: e["campaigns"].pop(),
            "unedited_approval_rate": lambda e: [e["approvals"].__setitem__(i, {**e["approvals"][i], "approved_hash": "edited", "edit_classification": "edited"}) for i in range(2)],
            "attribution_completeness": lambda e: e["attributions"].__setitem__(0, {**e["attributions"][0], "disposition": "ambiguous"}),
            "recommendation_accuracy": lambda e: [row.update(outcome_score=0, outcome_label="accurate") for row in e["recommendations"][:3]],
            "safety_incidents": lambda e: e["incidents"].append({"evidence_id": "bad", "observed_at": NOW.isoformat(), "severity": "high", "resolved": False}),
            "trust_history": lambda e: e["trust_weeks"][0].update(clean=False),
            "budget_compliance": lambda e: e["budgets"][0].update(actual_spend=101),
        }
        for gate, mutate in mutations.items():
            with self.subTest(gate=gate):
                item = evidence(); mutate(item)
                result = evaluate_beacon_advisory_readiness(item, now=NOW)
                self.assertFalse(result["ready"])
                self.assertEqual(result["gates"][gate]["status"], "failed")
                self.assertIsNone(result["notification"])

    def test_invalid_policy_states_fail_closed(self):
        for change, reason in [({"authority_state": "proposed"}, "policy_not_owner_approved"), ({"content_hash": "bad"}, "policy_malformed"), ({"superseded_by": "v2"}, "policy_superseded")]:
            with self.subTest(reason=reason):
                policy = {**APPROVED_POLICY, **change}
                result = evaluate_beacon_advisory_readiness(evidence(), policy=policy, now=NOW)
                self.assertFalse(result["ready"])
                self.assertTrue(all(g["status"] == "blocked" for g in result["gates"].values()))
                self.assertTrue(all(g["reason"] == reason for g in result["gates"].values()))

    def test_regression_and_recovery_preserve_history(self):
        prior = [{"ready": True, "evaluation_id": "old"}]
        failed = evidence(); failed["budgets"][0]["actual_spend"] = 101
        suspended = evaluate_beacon_advisory_readiness(failed, prior_evaluations=prior, now=NOW)
        self.assertEqual(suspended["state"], "suspended")
        self.assertEqual(suspended["notification"]["type"], "readiness_suspended")
        recovered = evaluate_beacon_advisory_readiness(evidence(), prior_evaluations=prior + [{"ready": False}], now=NOW)
        self.assertTrue(recovered["ready"])
        self.assertEqual(recovered["notification"]["type"], "threshold_met")

    def test_missing_stale_duplicate_and_superseded_evidence_fail_closed(self):
        item = evidence()
        item["campaigns"][0]["observed_at"] = (NOW - timedelta(days=100)).isoformat()
        item["campaigns"].append({**item["campaigns"][1], "evidence_id": "correction", "supersedes": "c1", "status": "incomplete"})
        result = evaluate_beacon_advisory_readiness(item, now=NOW)
        self.assertFalse(result["ready"])
        self.assertEqual(result["gates"]["campaign_evidence"]["reason"], "insufficient_campaign_evidence")


if __name__ == "__main__":
    unittest.main()
