import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from modules.beacon.autonomy_readiness import AutonomyPolicyRegistry, approve_threshold_policy, evaluate_autonomy_readiness, propose_threshold_policy

NOW = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)

def policy_payload():
    return {"policy_id": "BEACON-AUTONOMY-1", "effective_at": "2026-07-01T00:00:00+00:00", "expires_at": "2026-08-01T00:00:00+00:00", "evidence_schema_version": "beacon_autonomy_evidence_v1", "max_evidence_age_seconds": 3600, "thresholds": {"campaign_evidence": {"minimum_count": 3}, "unedited_approval_rate": {"minimum_rate": .9}, "attribution_completeness": {"minimum_rate": .9}, "recommendation_accuracy": {"minimum_rate": .8}, "safety_incidents": {"maximum_open_incidents": 0}, "trust_history": {"minimum_score": .95, "minimum_completed_evaluations": 10}, "budget_compliance": {"currency": "ZAR"}}}

def evidence():
    common = {"schema_version": "beacon_autonomy_evidence_v1", "recorded_at": NOW.isoformat(), "source": "verified_owner_evidence"}
    return {"campaign_evidence": {**common, "evidence_id": "campaign", "value": 3}, "unedited_approval_rate": {**common, "evidence_id": "approval", "value": .95}, "attribution_completeness": {**common, "evidence_id": "attribution", "value": .95}, "recommendation_accuracy": {**common, "evidence_id": "recommendation", "value": .9}, "safety_incidents": {**common, "evidence_id": "safety", "value": 0}, "trust_history": {**common, "evidence_id": "trust", "value": .97, "completed_evaluations": 12}, "budget_compliance": {**common, "evidence_id": "budget", "actual_spend": 90, "approved_cap": 100, "currency": "ZAR"}}

class BeaconAutonomyReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.registry = AutonomyPolicyRegistry(str(Path(self.temp.name) / "policy.sqlite3"))
    def tearDown(self): self.temp.cleanup()
    def approved(self):
        proposal = propose_threshold_policy(policy_payload(), now=NOW, registry=self.registry)["policy"]
        return approve_threshold_policy(proposal, "owner-charl", approved_at=NOW, registry=self.registry)["policy"]
    def test_all_positive_path_creates_exactly_one_notification(self):
        approved = self.approved()
        first = evaluate_autonomy_readiness(approved["policy_id"], evidence(), now=NOW, registry=self.registry)
        second = evaluate_autonomy_readiness(approved["policy_id"], evidence(), now=NOW, registry=self.registry)
        self.assertTrue(first["can_promote"]); self.assertTrue(first["notification_created"])
        self.assertTrue(second["notification_already_claimed"]); self.assertFalse(second["notification_created"])
        self.assertTrue(all(gate["passed"] for gate in first["gates"].values()))
        self.assertFalse(first["authority"]["posts_publicly"])
    def test_proposed_expired_malformed_and_superseded_policies_fail_closed(self):
        proposed = propose_threshold_policy(policy_payload(), now=NOW, registry=self.registry)["policy"]
        self.assertIn("policy_not_owner_approved", evaluate_autonomy_readiness(proposed["policy_id"], evidence(), now=NOW, registry=self.registry)["errors"])
        approved = approve_threshold_policy(proposed, "owner", approved_at=NOW, registry=self.registry)["policy"]
        expired = dict(policy_payload(), policy_id="EXPIRED", expires_at="2026-07-02T00:00:00+00:00")
        expired = approve_threshold_policy(propose_threshold_policy(expired, now=NOW, registry=self.registry)["policy"], "owner", approved_at=NOW, registry=self.registry)["policy"]
        self.assertIn("policy_expired", evaluate_autonomy_readiness(expired["policy_id"], evidence(), now=NOW, registry=self.registry)["errors"])
        tampered = dict(approved); tampered["policy_sha256"] = "0" * 64; self.registry.record("owner_approved", tampered)
        self.assertIn("policy_content_hash_mismatch", evaluate_autonomy_readiness(approved["policy_id"], evidence(), now=NOW, registry=self.registry)["errors"])
        first = self.approved(); later = propose_threshold_policy({**policy_payload(), "policy_id": first["policy_id"]}, now=NOW, registry=self.registry)["policy"]
        later = approve_threshold_policy(later, "owner", approved_at=NOW, registry=self.registry)["policy"]
        self.assertEqual(self.registry.latest_policy(first["policy_id"])["policy_version"], later["policy_version"])
        superseded = evaluate_autonomy_readiness(first["policy_id"], evidence(), now=NOW, registry=self.registry, supplied_policy_sha256=first["policy_sha256"])
        self.assertIn("caller_policy_hash_mismatch", superseded["errors"])
        self.assertFalse(superseded["can_promote"])
    def test_each_gate_fails_independently_under_explicit_and_semantics(self):
        approved = self.approved()
        mutations = {"campaign_evidence": {"value": 2}, "unedited_approval_rate": {"value": .1}, "attribution_completeness": {"value": .1}, "recommendation_accuracy": {"value": .1}, "safety_incidents": {"value": 1}, "trust_history": {"value": .1}, "budget_compliance": {"actual_spend": 101}}
        for name, mutation in mutations.items():
            with self.subTest(gate=name):
                sample = evidence(); sample[name].update(mutation)
                result = evaluate_autonomy_readiness(approved["policy_id"], sample, now=NOW, registry=self.registry)
                self.assertFalse(result["can_promote"]); self.assertFalse(result["notification_created"])
                self.assertFalse(result["gates"][name]["passed"])
                self.assertTrue(all(gate["passed"] for key, gate in result["gates"].items() if key != name))

    def test_future_dated_evidence_fails_closed(self):
        approved = self.approved()
        sample = evidence()
        sample["campaign_evidence"]["recorded_at"] = "2026-07-18T10:00:01+00:00"

        result = evaluate_autonomy_readiness(approved["policy_id"], sample, now=NOW, registry=self.registry)

        self.assertFalse(result["can_promote"])
        self.assertIn("evidence_stale_or_invalid", result["gates"]["campaign_evidence"]["blockers"])

    def test_negative_safety_incidents_fails_closed(self):
        approved = self.approved()
        sample = evidence()
        sample["safety_incidents"]["value"] = -1

        result = evaluate_autonomy_readiness(approved["policy_id"], sample, now=NOW, registry=self.registry)

        self.assertFalse(result["can_promote"])
        self.assertIn("safety_incidents_invalid", result["gates"]["safety_incidents"]["blockers"])

    def test_negative_budget_amounts_fail_closed(self):
        approved = self.approved()
        for field, blocker in (("actual_spend", "budget_actual_spend_invalid"), ("approved_cap", "budget_approved_cap_invalid")):
            with self.subTest(field=field):
                sample = evidence()
                sample["budget_compliance"][field] = -1

                result = evaluate_autonomy_readiness(approved["policy_id"], sample, now=NOW, registry=self.registry)

                self.assertFalse(result["can_promote"])
                self.assertFalse(result["gates"]["budget_compliance"]["passed"])
                self.assertIn(blocker, result["gates"]["budget_compliance"]["blockers"])

if __name__ == "__main__": unittest.main()
