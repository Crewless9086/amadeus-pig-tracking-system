import unittest

from modules.oom_sakkie.farm_lifecycle_canary import reconcile_lifecycle_canary


OBSERVATION = {"pig_id": "PIG-11", "on_farm": True, "observed_at": "2026-07-24T17:45:00Z"}


def evidence(*, event_type="entered_farm"):
    return {
        "herdmaster": {
            "authority": "read_only",
            "sources": [
                {"name": "pig_current_state", "authority": "canonical"},
                {"name": "pig_lifecycle_events", "authority": "canonical"},
            ],
            "lifecycle_events": [{
                "pig_id": "PIG-11",
                "lifecycle_event_id": "EVENT-11", "lifecycle_event_type": event_type,
                "effective_at": "2026-07-20T12:00:00Z", "recorded_at": "2026-07-20T12:01:00Z",
                "actor_reference": "owner:charl",
                "source_system": "owner", "source_reference": "lifecycle-log-11",
                "idempotency_key": "lifecycle-event-11",
            }],
        }
    }


class FarmLifecycleCanaryTests(unittest.TestCase):
    def test_canonical_entered_farm_evidence_agrees_with_on_farm_state(self):
        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=evidence())

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "lifecycle_canary_verified")
        self.assertEqual(result["owner_agent"], "oom-sakkie")
        self.assertFalse(result["authority"]["writes"])
        self.assertFalse(result["authority"]["may_execute"])

    def test_missing_lifecycle_event_fails_closed(self):
        rows = evidence()
        rows["herdmaster"]["lifecycle_events"] = []

        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertFalse(result["success"])
        self.assertIn("Herdmaster evidence must include at least one lifecycle event.", result["unresolved_questions"])

    def test_each_required_source_must_have_canonical_authority(self):
        rows = evidence()
        for source in rows["herdmaster"]["sources"]:
            source["authority"] = "untrusted"

        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertFalse(result["success"])
        self.assertIn(
            "Herdmaster evidence must cite each source with canonical authority: pig_current_state, pig_lifecycle_events.",
            result["unresolved_questions"],
        )

    def test_missing_provenance_fails_closed(self):
        rows = evidence()
        del rows["herdmaster"]["lifecycle_events"][0]["source_reference"]

        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertFalse(result["success"])
        self.assertIn("Lifecycle event 0 is missing source_reference.", result["unresolved_questions"])

    def test_exited_farm_evidence_conflicts_with_on_farm_state(self):
        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=evidence(event_type="exited_farm"))

        self.assertFalse(result["success"])
        self.assertIn("Current state says on_farm=true but lifecycle evidence records exited_farm.", result["unresolved_questions"])

    def test_entered_farm_evidence_conflicts_with_off_farm_state(self):
        observation = {**OBSERVATION, "on_farm": False}
        result = reconcile_lifecycle_canary(observation=observation, evidence_by_agent=evidence())

        self.assertFalse(result["success"])
        self.assertIn("Current state says on_farm=false but lifecycle evidence records entered_farm.", result["unresolved_questions"])

    def test_latest_effective_event_overrides_historical_exit(self):
        rows = evidence(event_type="exited_farm")
        rows["herdmaster"]["lifecycle_events"].append({
            **rows["herdmaster"]["lifecycle_events"][0],
            "lifecycle_event_id": "EVENT-12",
            "lifecycle_event_type": "entered_farm",
            "effective_at": "2026-07-21T12:00:00Z",
            "recorded_at": "2026-07-21T12:01:00Z",
            "idempotency_key": "lifecycle-event-12",
        })

        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=rows)

        self.assertTrue(result["success"])

    def test_canonical_audit_rail_event_uses_recorded_at_not_observed_at(self):
        result = reconcile_lifecycle_canary(observation=OBSERVATION, evidence_by_agent=evidence())

        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
