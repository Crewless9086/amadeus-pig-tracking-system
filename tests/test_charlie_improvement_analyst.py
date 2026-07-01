import unittest
from unittest.mock import patch

from modules.charlie.improvement_analyst import (
    PROPOSAL_LABEL,
    analyze_improvement_opportunities,
    generate_and_store_proposals,
)


class CharlieImprovementAnalystTests(unittest.TestCase):
    def test_analyzer_detects_repeated_failures_and_labels_proposals(self):
        missions = [
            {
                "mission_id": "MISSION-1",
                "status": "blocked",
                "title": "Runner blocked",
                "metadata": {"review_packet": {"errors": ["Tests failed before owner review."], "blocked_reason": "Quality gate missing."}},
            },
            {
                "mission_id": "MISSION-2",
                "status": "pr_ready",
                "title": "Dashboard review",
                "metadata": {"review_packet": {"findings": ["Dashboard did not show test evidence."], "test_evidence": ["python -m unittest failed first."]}},
            },
        ]

        proposals = analyze_improvement_opportunities(missions)

        self.assertTrue(proposals)
        labels = {proposal["label"] for proposal in proposals}
        self.assertEqual(labels, {PROPOSAL_LABEL})
        target_areas = {proposal["target_area"] for proposal in proposals}
        self.assertIn("tests", target_areas)
        self.assertTrue(all(proposal["applies_automatically"] is False for proposal in proposals))
        self.assertTrue(all(proposal["status"] == "pending" for proposal in proposals))

    def test_analyzer_requires_recurrence_before_proposal(self):
        proposals = analyze_improvement_opportunities([
            {
                "mission_id": "MISSION-1",
                "status": "blocked",
                "title": "One blocked runner mission",
                "metadata": {"review_packet": {"blocked_reason": "Runner heartbeat missing."}},
            },
        ])

        self.assertEqual(proposals, [])

    @patch("modules.charlie.improvement_analyst.vault_store.write_artifact")
    @patch("modules.charlie.improvement_analyst.vault_store.list_artifacts")
    @patch("modules.charlie.improvement_analyst.mission_store.list_missions")
    def test_generate_preserves_owner_reviewed_proposal_decision_on_rerun(self, list_missions, list_artifacts, write_artifact):
        list_missions.return_value = ({
            "success": True,
            "missions": [
                {
                    "mission_id": "MISSION-1",
                    "status": "blocked",
                    "title": "Tests failed",
                    "metadata": {"review_packet": {"errors": ["Tests failed before owner review."]}},
                },
                {
                    "mission_id": "MISSION-2",
                    "status": "pr_ready",
                    "title": "Regression evidence",
                    "metadata": {"review_packet": {"findings": ["Missing regression test evidence."]}},
                },
            ],
        }, 200)
        write_artifact.return_value = ({"success": True, "status": "artifact_written"}, 200)

        cases = [
            ("approved", {"decision": "approve", "comments": "Good fix."}, {}),
            ("rejected", {"decision": "reject", "comments": "Not worth it."}, {}),
            (
                "sent_to_mission",
                {"decision": "send_to_mission", "comments": "Make it a mission."},
                {"mission_creation_status": "mission_recorded", "sent_to_mission_id": "CHARLIE-MISSION-IMPROVE-1"},
            ),
        ]

        for proposal_status, decision_record, extra_fields in cases:
            with self.subTest(proposal_status=proposal_status):
                existing_content = {
                    "proposal_id": "CHARLIE-IMPROVEMENT-TESTS",
                    "label": PROPOSAL_LABEL,
                    "status": proposal_status,
                    "decision_history": [decision_record],
                    "last_owner_decision": decision_record,
                    "created_at": "2026-07-01T10:00:00+00:00",
                    **extra_fields,
                }
                list_artifacts.return_value = ({
                    "success": True,
                    "artifacts": [{
                        "artifact_id": "ARTIFACT-TESTS",
                        "content": existing_content,
                        "created_by_agent": "charlie_improvement_analyst",
                        "created_at": "2026-07-01T10:00:00+00:00",
                    }],
                }, 200)
                write_artifact.reset_mock()

                result, status = generate_and_store_proposals(database_url="postgresql://example")

                self.assertEqual(status, 200)
                self.assertTrue(result["success"])
                written_proposal = write_artifact.call_args.args[2]
                self.assertEqual(written_proposal["proposal_id"], "CHARLIE-IMPROVEMENT-TESTS")
                self.assertEqual(written_proposal["status"], proposal_status)
                self.assertEqual(written_proposal["decision_history"][0]["decision"], decision_record["decision"])
                self.assertEqual(written_proposal["last_owner_decision"]["decision"], decision_record["decision"])
                self.assertEqual(written_proposal["created_at"], "2026-07-01T10:00:00+00:00")
                for field, value in extra_fields.items():
                    self.assertEqual(written_proposal[field], value)


if __name__ == "__main__":
    unittest.main()
