import unittest
import json
from pathlib import Path

from modules.charlie.development_coordination import (
    close_dependency,
    plan_development_dispatch,
    reduce_coordination,
    validate_dispatch_scope,
    validate_successor_bindings,
)
from modules.charlie.mission_replacement import NON_RUNNABLE_PREDECESSOR_STATUSES


class CharlieDevelopmentCoordinationTests(unittest.TestCase):
    def test_unsigned_t1_proposal_recomputes_exactly_and_states_do_not_collapse(self):
        path = Path(__file__).parents[1] / "docs/06-operations/contracts/CORE_T1_POST_P0_HANDOVER_CORRECTION_PROPOSAL.json"
        proposal = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(proposal["signature"])
        self.assertIsNone(proposal["authorization"])
        plan = plan_development_dispatch(proposal["mission"])
        proof = proposal["planning_proof"]
        self.assertEqual(plan["plan_id"], proof["plan_id"])
        self.assertEqual(plan["orchestration_generation"], proof["orchestration_generation"])
        self.assertEqual(plan["score"]["total"], 12)
        self.assertEqual(plan["tier"], "T1")
        self.assertEqual(plan["agents"], ["builder"])
        self.assertEqual(reduce_coordination(plan, [])["state"], "proposed")
        authorized = [{"type": "authorize", "authority": "charlie"}]
        self.assertEqual(reduce_coordination(plan, authorized)["state"], "owner_authorized")
        released = authorized + [{"type": "release", "authority": "charlie"}]
        self.assertEqual(reduce_coordination(plan, released)["state"], "released")
        self.assertFalse(reduce_coordination(plan, released)["pickup_proven"])
        acknowledged = released + [{"type": "acknowledge", "worker_id": "builder-1",
                                    "worker_role": "builder", "dispatch_id": "D-T1",
                                    "acknowledged_at": "now"}]
        self.assertEqual(reduce_coordination(plan, acknowledged)["state"], "acknowledged")
        self.assertEqual(reduce_coordination(plan, acknowledged + [
            {"type": "start", "dispatch_id": "D-T1", "started_at": "later"},
        ])["state"], "started")

    def test_reconciled_legacy_inventory_and_s01_are_not_pickup_candidates(self):
        statuses = ["new"] * 55 + ["paused"] * 27 + ["blocked"] * 3 + ["pr_ready"]
        legacy = [{"mission_id": f"LEGACY-{index:02d}", "status": status}
                  for index, status in enumerate(statuses, start=1)]
        self.assertEqual(len(legacy), 86)
        self.assertTrue(all(row["status"] in NON_RUNNABLE_PREDECESSOR_STATUSES for row in legacy))
        self.assertNotIn("S01_OOM_DAILY_CONTROL_CLOSURE", {row["mission_id"] for row in legacy})
        self.assertFalse(any(row["status"] in {"approved", "in_progress", "release_approved"} for row in legacy))

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
            {"type": "acknowledge", "worker_id": "builder-1", "worker_role": "builder", "dispatch_id": "D-1", "acknowledged_at": "2026-08-03T10:00:00Z"},
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
            {"type": "acknowledge", "worker_id": "source-mapper-1", "worker_role": "source_mapper", "dispatch_id": "D-2", "acknowledged_at": "now"},
            {"type": "start", "dispatch_id": "D-2", "started_at": "now"},
            {"type": "complete", "artifact": {"business_outcome": "NO BUSINESS OUTCOME", "outcome_reason": "No reusable gap found.", "artifact_evidence": ["report.json#result"], "next_dependency": None}},
        ]
        self.assertEqual(reduce_coordination(plan, events)["state"], "completed_with_artifact")

    def test_only_selected_worker_can_accept_and_scope_cannot_pick_second_mission(self):
        plan = plan_development_dispatch({
            "mission_id": "CORE-T1-DOC-CANARY",
            "raw_text": "Correct one stale S01 section in one operator handover.",
            "mission_type": "documentation",
        })
        self.assertEqual(plan["agents"], ["builder"])
        self.assertTrue(validate_dispatch_scope(
            plan, plan_id=plan["plan_id"], mission_id="CORE-T1-DOC-CANARY", worker_role="builder",
        )["single_mission"])
        with self.assertRaisesRegex(ValueError, "worker_not_selected"):
            validate_dispatch_scope(
                plan, plan_id=plan["plan_id"], mission_id="CORE-T1-DOC-CANARY", worker_role="tester",
            )
        with self.assertRaisesRegex(ValueError, "mission_scope_mismatch"):
            validate_dispatch_scope(
                plan, plan_id=plan["plan_id"], mission_id="CORE-SECOND-MISSION", worker_role="builder",
            )
        with self.assertRaisesRegex(ValueError, "worker_not_selected"):
            reduce_coordination(plan, [
                {"type": "authorize", "authority": "charlie"},
                {"type": "release", "authority": "charlie"},
                {"type": "acknowledge", "worker_id": "tester-1", "worker_role": "tester",
                 "dispatch_id": "D-3", "acknowledged_at": "now"},
            ])

    def test_completion_requires_the_declared_file_artifact(self):
        plan = plan_development_dispatch({
            "mission_id": "CORE-T1-DOC-CANARY", "mission_type": "documentation",
            "raw_text": "Correct one stale heading in docs/required.md.",
            "expected_files": ["docs/required.md"],
        })
        events = [
            {"type": "authorize", "authority": "charlie"},
            {"type": "release", "authority": "charlie"},
            {"type": "acknowledge", "worker_id": "builder-1", "worker_role": "builder",
             "dispatch_id": "D-4", "acknowledged_at": "now"},
            {"type": "start", "dispatch_id": "D-4", "started_at": "now"},
        ]
        wrong = {"business_outcome": "Wrong file changed.",
                 "artifact_evidence": ["docs/other.md@abc"], "next_dependency": None}
        with self.assertRaisesRegex(ValueError, "declared_artifact_required"):
            reduce_coordination(plan, events + [{"type": "complete", "artifact": wrong}])


if __name__ == "__main__":
    unittest.main()
