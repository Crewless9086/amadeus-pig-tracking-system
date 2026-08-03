import unittest

from modules.charlie.development_coordination import (
    close_dependency,
    plan_development_dispatch,
    reduce_coordination,
    validate_successor_bindings,
)


class CharlieDevelopmentCoordinationTests(unittest.TestCase):
    def test_small_document_source_correction_selects_one_worker(self):
        plan = plan_development_dispatch({
            "title": "Correct one README heading", "mission_type": "documentation",
            "raw_text": "Fix one typo in README.md.", "urgency": "P3", "business_impact_score": 1,
        })
        self.assertEqual(plan["tier"], "T1")
        self.assertEqual(plan["agents"], ["builder"])
        self.assertEqual(plan["state"], "proposed")

    def test_bounded_domain_change_uses_specialist_only_when_needed(self):
        plan = plan_development_dispatch({
            "title": "Bound one HERDMASTER source correction", "mission_type": "bug fix",
            "raw_text": "Fix one bounded Herdmaster pig observation regression in modules/x.py.",
            "urgency": "P2", "business_impact_score": 2,
        })
        self.assertEqual(plan["tier"], "T1")
        self.assertEqual(plan["agents"], ["builder", "product_reviewer"])

    def test_protected_production_mission_stays_unreleased_without_authority(self):
        plan = plan_development_dispatch({
            "title": "Production correction", "mission_type": "release",
            "raw_text": "Deploy the approved production correction.", "urgency": "P0",
            "business_impact_score": 4,
        })
        self.assertEqual(plan["tier"], "T4")
        with self.assertRaisesRegex(ValueError, "protected_authority_required"):
            reduce_coordination(plan, [
                {"type": "authorize", "authority": "charlie"},
                {"type": "release", "authority": "charlie", "exact_protected_authority": False},
            ])

    def test_release_is_not_pickup_and_missing_ack_is_one_exception(self):
        plan = plan_development_dispatch({"raw_text": "Fix typo in README.md", "mission_type": "documentation"})
        events = [
            {"type": "authorize", "authority": "charlie"},
            {"type": "release", "authority": "charlie"},
        ]
        released = reduce_coordination(plan, events)
        self.assertEqual(released["state"], "released")
        self.assertFalse(released["pickup_proven"])
        contained = reduce_coordination(plan, events + [
            {"type": "contain_missing_ack"}, {"type": "contain_missing_ack"},
        ])
        self.assertEqual(contained["state"], "contained")
        self.assertEqual(len(contained["exceptions"]), 1)

    def test_ack_start_and_completion_artifact_close_dependency(self):
        plan = plan_development_dispatch({"raw_text": "Fix typo in README.md", "mission_type": "documentation"})
        artifact = {"business_outcome": "Owner documentation now names the canonical command.",
                    "artifact_evidence": ["docs/README.md@abc123"], "next_dependency": "DEP-1"}
        result = reduce_coordination(plan, [
            {"type": "authorize", "authority": "charl"},
            {"type": "release", "authority": "charlie"},
            {"type": "acknowledge", "worker_id": "builder-1", "dispatch_id": "D-1", "acknowledged_at": "2026-08-03T10:00:00Z"},
            {"type": "start", "dispatch_id": "D-1", "started_at": "2026-08-03T10:00:01Z"},
            {"type": "complete", "artifact": artifact},
        ])
        self.assertEqual(result["state"], "completed_with_artifact")
        self.assertTrue(result["pickup_proven"])
        self.assertTrue(close_dependency(artifact, "DEP-1")["closed"])

    def test_ambiguous_external_action_is_never_retried(self):
        plan = plan_development_dispatch({"raw_text": "Publish approved campaign.", "mission_type": "operation"})
        events = [
            {"type": "authorize", "authority": "charlie"},
            {"type": "release", "authority": "charlie", "exact_protected_authority": True},
            {"type": "contain_ambiguous_external_effect", "effect_identity": "provider-attempt-1"},
            {"type": "contain_ambiguous_external_effect", "effect_identity": "provider-attempt-1"},
        ]
        result = reduce_coordination(plan, events)
        self.assertEqual(result["state"], "contained")
        self.assertEqual(result["exceptions"], [{**result["exceptions"][0], "retry": False}])
        self.assertEqual(len(result["exceptions"]), 1)

    def test_oom_sakkie_cannot_authorize_core_execution(self):
        plan = plan_development_dispatch({"raw_text": "Fix one module.", "mission_type": "bug fix"})
        with self.assertRaisesRegex(ValueError, "owner_authority_required"):
            reduce_coordination(plan, [{"type": "authorize", "authority": "oom_sakkie"}])

    def test_only_charl_or_charlie_can_release_and_circular_work_is_rejected(self):
        plan = plan_development_dispatch({"raw_text": "Fix one module.", "mission_type": "bug fix"})
        with self.assertRaisesRegex(ValueError, "owner_authority_required"):
            reduce_coordination(plan, [{"type": "authorize", "authority": "worker"}])
        self.assertTrue(validate_successor_bindings([{"predecessor_id": "P1", "successor_id": "S1"}]))
        with self.assertRaisesRegex(ValueError, "duplicate_or_overlapping"):
            validate_successor_bindings([{"predecessor_id": "P1", "successor_id": "S1"}, {"predecessor_id": "P1", "successor_id": "S2"}])

    def test_no_business_outcome_requires_honest_reason(self):
        plan = plan_development_dispatch({"raw_text": "Inspect one source.", "mission_type": "audit"})
        events = [
            {"type": "authorize", "authority": "charlie"}, {"type": "release", "authority": "charlie"},
            {"type": "acknowledge", "worker_id": "source-mapper-1", "dispatch_id": "D-2", "acknowledged_at": "now"},
            {"type": "start", "dispatch_id": "D-2", "started_at": "now"},
            {"type": "complete", "artifact": {"business_outcome": "NO BUSINESS OUTCOME", "outcome_reason": "No reusable gap found.", "artifact_evidence": ["report.json#result"], "next_dependency": None}},
        ]
        self.assertEqual(reduce_coordination(plan, events)["state"], "completed_with_artifact")


if __name__ == "__main__":
    unittest.main()
