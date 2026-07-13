import unittest

from modules.charlie.mission_governance import (
    backflow_budget,
    build_followup_missions,
    ensure_acceptance_matrix,
    evaluate_quality_failure,
    mission_governance_summary,
    semantic_finding_family,
    update_acceptance_matrix,
)


def mission_with_events(events=None):
    return {
        "mission_id": "CHARLIE-MISSION-PARENT",
        "title": "Build safe opportunity scanner",
        "raw_text": "Build a Supabase-first scanner with owner-review cards and no execution authority.",
        "mission_type": "marketing intelligence",
        "approval_level": "LEVEL 3",
        "vault": {
            "acceptance_criteria": [
                "Read canonical allocation evidence.",
                "Produce owner-review opportunity cards.",
            ],
            "test_plan": ["Run scanner contract tests."],
        },
        "metadata": {
            "queue": {"priority": 20},
            "mission_memory": {"events": list(events or [])},
        },
    }


class CharlieMissionGovernanceTests(unittest.TestCase):
    def test_acceptance_matrix_is_frozen_before_builder(self):
        packet = ensure_acceptance_matrix(mission_with_events())

        self.assertTrue(packet["matrix_frozen"])
        self.assertEqual(packet["matrix_source"], "mission_vault")
        self.assertEqual(len(packet["acceptance_matrix"]), 3)
        self.assertEqual(packet["acceptance_matrix"][-1]["id"], "authority-boundary")

    def test_planner_replaces_fallback_matrix_before_builder(self):
        mission = mission_with_events()
        mission["vault"]["acceptance_criteria"] = []
        mission["metadata"]["mission_governance"] = ensure_acceptance_matrix(mission)

        packet = ensure_acceptance_matrix(mission, {"acceptance_criteria": ["Specific planner criterion"]})

        self.assertEqual(packet["matrix_source"], "planner")
        self.assertEqual(packet["acceptance_matrix"][0]["requirement"], "Specific planner criterion")

    def test_tester_and_qa_evidence_update_separate_matrix_rows(self):
        packet = ensure_acceptance_matrix(mission_with_events())
        packet = update_acceptance_matrix(packet, "tester", {"tests_run": ["25 focused tests passed"]}, True)
        packet = update_acceptance_matrix(packet, "qa_red_team", {"qa_findings": ["Authority boundaries passed"]}, True)

        self.assertTrue(all(row["status"] == "passed" for row in packet["acceptance_matrix"]))

    def test_preexisting_baseline_failure_does_not_backflow_parent(self):
        decision = evaluate_quality_failure(
            mission_with_events(),
            "tester",
            {
                "errors": ["Pre-existing SAM stress failure reproduces on main and was not introduced by this PR."],
                "test_status": "fail",
            },
            {"passed": False, "reason": "tester recorded non-passing test_status=fail."},
        )

        self.assertEqual(decision["route"], "continue_with_followups")
        self.assertFalse(decision["blocking_findings"])
        self.assertEqual(decision["followup_findings"][0]["family"], "baseline_regression")

    def test_timeout_is_followup_not_builder_backflow(self):
        decision = evaluate_quality_failure(
            mission_with_events(),
            "tester",
            {"errors": ["Broad mapped suite timed out after focused tests passed."], "test_status": "fail"},
            {"passed": False, "reason": "timeout"},
        )

        self.assertEqual(decision["route"], "continue_with_followups")
        self.assertEqual(decision["followup_findings"][0]["family"], "environment_timeout")

    def test_new_in_scope_defect_backflows_within_budget(self):
        decision = evaluate_quality_failure(
            mission_with_events(),
            "qa_red_team",
            {"bugs": ["Malformed allocation threshold produces an unsafe positive demand cap."], "red_team_status": "fail"},
            {"passed": False, "reason": "red team failed"},
        )

        self.assertEqual(decision["route"], "backflow")
        self.assertEqual(decision["blocking_findings"][0]["family"], "input_validation")

    def test_mission_wide_budget_converts_new_defect_to_child_followup(self):
        events = [
            {"type": "agent_backflow", "metadata": {"finding_family": family}}
            for family in ("input_validation", "supply_compatibility", "revision_evidence", "test_evidence")
        ]
        mission = mission_with_events(events)
        decision = evaluate_quality_failure(
            mission,
            "qa_red_team",
            {"bugs": [{"finding": "Malformed thresholds require another validation rule.", "file": "modules/beacon/scanner.py"}]},
            {"passed": False, "reason": "new edge"},
        )

        self.assertTrue(decision["budget"]["exhausted"])
        self.assertEqual(decision["route"], "continue_with_followups")
        children = build_followup_missions(mission, decision["followup_findings"])
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["status"], "new")
        self.assertEqual(children[0]["metadata"]["mission_family"]["parent_mission_id"], mission["mission_id"])
        self.assertEqual(children[0]["metadata"]["mission_family"]["root_mission_id"], mission["mission_id"])

    def test_failed_frozen_acceptance_does_not_become_child_when_budget_is_exhausted(self):
        events = [
            {"type": "agent_backflow", "metadata": {"finding_family": family}}
            for family in ("input_validation", "supply_compatibility", "revision_evidence", "test_evidence")
        ]
        decision = evaluate_quality_failure(
            mission_with_events(events),
            "tester",
            {
                "errors": ["The agreed allocation contract still fails its focused test."],
                "acceptance_results": [
                    {"id": "acceptance-allocation", "status": "failed", "evidence": ["1 focused test failed"]}
                ],
            },
            {"passed": False, "reason": "frozen criterion failed"},
        )

        self.assertEqual(decision["route"], "owner_block")
        self.assertEqual(decision["failed_acceptance_ids"], ["acceptance-allocation"])
        self.assertFalse(decision["followup_findings"])

    def test_same_family_budget_is_semantic_not_exact_text(self):
        mission = mission_with_events([
            {"type": "agent_backflow", "summary": "Malformed weight value", "metadata": {"finding_family": "input_validation"}},
            {"type": "agent_backflow", "summary": "Invalid allocation row", "metadata": {"finding_family": "input_validation"}},
        ])

        budget = backflow_budget(mission, [{"family": "input_validation"}])

        self.assertTrue(budget["exhausted"])
        self.assertIn("input_validation", budget["exhausted_families"])

    def test_historical_backflows_do_not_exhaust_a_new_builder_revision(self):
        events = [
            {"type": "agent_backflow", "metadata": {"finding_family": family}}
            for family in ("input_validation", "supply_compatibility", "revision_evidence", "test_evidence")
        ]
        mission = mission_with_events(events)
        mission["metadata"]["mission_memory"]["latest_by_agent"] = {
            "builder": {"type": "agent_complete", "commit_sha": "new-revision"}
        }

        budget = backflow_budget(mission, [{"family": "access_authority"}])

        self.assertFalse(budget["exhausted"])
        self.assertEqual(budget["mission_total"], 0)
        self.assertEqual(budget["historical_mission_total"], 4)
        self.assertEqual(budget["revision_scope"], "new-revision")

    def test_current_revision_backflows_still_exhaust_the_bounded_budget(self):
        events = [
            {
                "type": "agent_backflow",
                "metadata": {"finding_family": "access_authority", "revision_sha": "current-revision"},
            },
            {
                "type": "agent_backflow",
                "metadata": {"finding_family": "access_authority", "revision_sha": "current-revision"},
            },
            {
                "type": "agent_backflow",
                "metadata": {"finding_family": "access_authority", "revision_sha": "older-revision"},
            },
        ]
        mission = mission_with_events(events)
        mission["metadata"]["mission_memory"]["latest_by_agent"] = {
            "builder": {"type": "agent_complete", "commit_sha": "current-revision"}
        }

        budget = backflow_budget(mission, [{"family": "access_authority"}])

        self.assertTrue(budget["exhausted"])
        self.assertEqual(budget["mission_total"], 2)
        self.assertEqual(budget["historical_mission_total"], 3)

    def test_red_zone_never_becomes_followup_only(self):
        events = [{"type": "agent_backflow", "metadata": {"finding_family": "implementation_defect"}}] * 5
        decision = evaluate_quality_failure(
            mission_with_events(events),
            "qa_red_team",
            {"bugs": ["Customer send without owner approval is possible through the changed route."]},
            {"passed": False, "reason": "unsafe authority"},
        )

        self.assertEqual(decision["route"], "owner_block")

    def test_summary_separates_delivery_from_review_activity(self):
        mission = mission_with_events([
            {"type": "agent_complete", "agent": "builder"},
            {"type": "agent_complete", "agent": "tester"},
            {"type": "agent_backflow", "agent": "tester", "metadata": {"finding_family": "input_validation"}},
            {"type": "followup_discovered", "agent": "qa_red_team"},
        ])
        governance = ensure_acceptance_matrix(mission)
        governance = update_acceptance_matrix(governance, "tester", {"tests_run": ["pass"]}, True)
        mission["metadata"]["mission_governance"] = governance

        summary = mission_governance_summary(mission)

        self.assertEqual(summary["fix_count"], 1)
        self.assertEqual(summary["review_runs"], 3)
        self.assertEqual(summary["backflow_count"], 1)
        self.assertEqual(summary["followup_count"], 1)

    def test_semantic_family_groups_validation_variants(self):
        self.assertEqual(semantic_finding_family("Malformed structured weight evidence"), "input_validation")
        self.assertEqual(semantic_finding_family("Invalid threshold value"), "input_validation")


if __name__ == "__main__":
    unittest.main()
