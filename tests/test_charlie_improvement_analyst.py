import unittest

from modules.charlie.improvement_analyst import (
    PROPOSAL_LABEL,
    analyze_improvement_opportunities,
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


if __name__ == "__main__":
    unittest.main()
