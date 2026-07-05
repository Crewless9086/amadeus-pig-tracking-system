import unittest
from unittest.mock import patch

from modules.charlie.improvement_analyst import (
    PROPOSAL_LABEL,
    analyze_mission_replay,
    analyze_improvement_opportunities,
    create_owner_gated_improvement_missions,
    generate_and_store_proposals,
    record_proposal_decision,
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

    def test_replay_analysis_turns_known_failure_into_owner_gated_proposal(self):
        result, status = analyze_mission_replay({
            "mission_id": "MISSION-KNOWN",
            "status": "blocked",
            "metadata": {
                "review_packet": {
                    "review_status": "agent_blocked",
                    "blocked_agent": "reviewer",
                    "blocked_reason": "Visual Review media was not captured.",
                    "errors": ["python -m pytest failed: No module named pytest"],
                }
            },
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["known_failures"])
        codes = {item["known_failure_code"] for item in result["proposals"] if item.get("known_failure_code")}
        self.assertIn("pytest_missing", codes)
        self.assertIn("review_media_missing", codes)
        self.assertTrue(all(proposal["applies_automatically"] is False for proposal in result["proposals"]))

    @patch("modules.charlie.improvement_analyst.vault_store.write_artifact")
    @patch("modules.charlie.improvement_analyst.vault_store.list_artifacts")
    @patch("modules.charlie.improvement_analyst.mission_store.list_missions")
    def test_generate_stores_proposal_artifacts_under_real_source_mission(self, list_missions, list_artifacts, write_artifact):
        list_missions.return_value = ({
            "success": True,
            "missions": [
                {
                    "mission_id": "MISSION-2",
                    "status": "pr_ready",
                    "title": "Regression evidence",
                    "metadata": {"review_packet": {"findings": ["Missing regression test evidence."]}},
                },
                {
                    "mission_id": "MISSION-1",
                    "status": "blocked",
                    "title": "Tests failed",
                    "metadata": {"review_packet": {"errors": ["Tests failed before owner review."]}},
                },
            ],
        }, 200)
        list_artifacts.return_value = ({"success": True, "artifacts": []}, 200)
        write_artifact.return_value = ({"success": True, "status": "artifact_written"}, 200)

        result, status = generate_and_store_proposals(database_url="postgresql://example")

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertTrue(write_artifact.called)
        self.assertEqual(write_artifact.call_args.args[0], "MISSION-1")
        self.assertEqual(write_artifact.call_args.kwargs["project_id"], "")
        written_proposal = write_artifact.call_args.args[2]
        self.assertEqual(written_proposal["record_mission_id"], "MISSION-1")
        self.assertIn("MISSION-2", written_proposal["source_mission_ids"])

    @patch("modules.charlie.improvement_analyst.vault_store.write_artifact")
    @patch("modules.charlie.improvement_analyst.vault_store.list_artifacts")
    @patch("modules.charlie.improvement_analyst.mission_store.list_missions")
    def test_generate_reports_failed_durable_proposal_writes(self, list_missions, list_artifacts, write_artifact):
        list_missions.return_value = ({
            "success": True,
            "missions": [
                {
                    "mission_id": "MISSION-2",
                    "status": "pr_ready",
                    "title": "Regression evidence",
                    "metadata": {"review_packet": {"findings": ["Missing regression test evidence."]}},
                },
                {
                    "mission_id": "MISSION-1",
                    "status": "blocked",
                    "title": "Tests failed",
                    "metadata": {"review_packet": {"errors": ["Tests failed before owner review."]}},
                },
            ],
        }, 200)
        list_artifacts.return_value = ({"success": True, "artifacts": []}, 200)
        write_artifact.return_value = ({"success": False, "status": "artifact_write_failed"}, 500)

        result, status = generate_and_store_proposals(database_url="postgresql://example")

        self.assertEqual(status, 500)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "proposal_write_failed")
        self.assertEqual(result["failed_write_count"], 1)
        self.assertEqual(result["writes"][0]["status"], "artifact_write_failed")

    @patch("modules.charlie.improvement_analyst.mission_store.record_mission")
    @patch("modules.charlie.improvement_analyst.vault_store.write_artifact")
    @patch("modules.charlie.improvement_analyst.vault_store.list_artifacts")
    @patch("modules.charlie.improvement_analyst.mission_store.list_missions")
    def test_create_owner_gated_improvement_missions_does_not_apply_changes(
        self,
        list_missions,
        list_artifacts,
        write_artifact,
        record_mission,
    ):
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
        list_artifacts.return_value = ({"success": True, "artifacts": []}, 200)
        write_artifact.return_value = ({"success": True, "status": "artifact_written"}, 200)
        record_mission.return_value = ({"stored": True, "status": "mission_recorded", "mission_id": "MISSION-IMPROVE"}, 201)

        result, status = create_owner_gated_improvement_missions(database_url="postgresql://example")

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["created_count"], 1)
        created_payload = record_mission.call_args.args[0]
        self.assertEqual(created_payload["mission_type"], "system improvement")
        self.assertIn("No proposal content applies itself automatically.", created_payload["acceptance_criteria"])
        self.assertIn("does not approve, build, merge, deploy", result["execution_boundary"])

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

    @patch("modules.charlie.improvement_analyst.vault_store.write_owner_decision")
    @patch("modules.charlie.improvement_analyst.vault_store.update_artifact_content")
    @patch("modules.charlie.improvement_analyst.vault_store.get_artifact")
    def test_record_proposal_decision_approves_without_applying_change(self, get_artifact, update_artifact_content, write_owner_decision):
        get_artifact.return_value = (_artifact_payload(status="pending"), 200)
        update_artifact_content.return_value = ({"success": True, "status": "artifact_updated"}, 200)
        write_owner_decision.return_value = ({"success": True, "status": "owner_decision_written"}, 200)

        result, status = record_proposal_decision("ARTIFACT-TESTS", "approve", comments="Agree.")

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["proposal_status"], "approved")
        self.assertEqual(result["decision"], "approve")
        saved_proposal = update_artifact_content.call_args.args[1]
        self.assertFalse(saved_proposal["last_owner_decision"]["applies_automatically"])
        self.assertEqual(saved_proposal["decision_history"][-1]["comments"], "Agree.")
        write_owner_decision.assert_called_once()
        self.assertEqual(write_owner_decision.call_args.args[0], "MISSION-1")

    @patch("modules.charlie.improvement_analyst.vault_store.write_owner_decision")
    @patch("modules.charlie.improvement_analyst.vault_store.update_artifact_content")
    @patch("modules.charlie.improvement_analyst.vault_store.get_artifact")
    def test_record_proposal_decision_rejects_without_mission_creation(self, get_artifact, update_artifact_content, write_owner_decision):
        get_artifact.return_value = (_artifact_payload(status="pending"), 200)
        update_artifact_content.return_value = ({"success": True, "status": "artifact_updated"}, 200)
        write_owner_decision.return_value = ({"success": True, "status": "owner_decision_written"}, 200)

        result, status = record_proposal_decision("ARTIFACT-TESTS", "reject")

        self.assertEqual(status, 200)
        self.assertEqual(result["proposal_status"], "rejected")
        self.assertEqual(result["created_mission"], {})

    @patch("modules.charlie.improvement_analyst.vault_store.write_owner_decision")
    @patch("modules.charlie.improvement_analyst.mission_store.record_mission")
    @patch("modules.charlie.improvement_analyst.vault_store.update_artifact_content")
    @patch("modules.charlie.improvement_analyst.vault_store.get_artifact")
    def test_record_proposal_decision_send_to_mission_creates_normal_mission(self, get_artifact, update_artifact_content, record_mission, write_owner_decision):
        get_artifact.return_value = (_artifact_payload(status="pending"), 200)
        update_artifact_content.return_value = ({"success": True, "status": "artifact_updated"}, 200)
        record_mission.return_value = ({"stored": True, "status": "mission_recorded", "mission_id": "MISSION-IMPROVE-1"}, 200)
        write_owner_decision.return_value = ({"success": True, "status": "owner_decision_written"}, 200)

        result, status = record_proposal_decision("ARTIFACT-TESTS", "send_to_mission", comments="Build this.")

        self.assertEqual(status, 200)
        self.assertEqual(result["proposal_status"], "sent_to_mission")
        self.assertEqual(result["created_mission"]["mission_id"], "MISSION-IMPROVE-1")
        mission_payload = record_mission.call_args.args[0]
        self.assertEqual(mission_payload["metadata"]["proposal_label"], PROPOSAL_LABEL)
        self.assertEqual(mission_payload["approval_level"], "LEVEL 3")
        self.assertIn("Do not self-edit", mission_payload["forbidden_actions"][0])
        saved_proposal = update_artifact_content.call_args.args[1]
        self.assertEqual(saved_proposal["sent_to_mission_id"], "MISSION-IMPROVE-1")

    def test_record_proposal_decision_rejects_invalid_decision_before_storage(self):
        result, status = record_proposal_decision("ARTIFACT-TESTS", "merge")

        self.assertEqual(status, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_improvement_decision")

    @patch("modules.charlie.improvement_analyst.vault_store.get_artifact")
    def test_record_proposal_decision_rejects_invalid_label(self, get_artifact):
        get_artifact.return_value = (_artifact_payload(label="not_self_improvement"), 200)

        result, status = record_proposal_decision("ARTIFACT-TESTS", "approve")

        self.assertEqual(status, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_improvement_label")

    @patch("modules.charlie.improvement_analyst.vault_store.get_artifact")
    def test_record_proposal_decision_returns_not_configured_vault_status(self, get_artifact):
        get_artifact.return_value = ({"success": False, "configured": False, "status": "not_configured"}, 503)

        result, status = record_proposal_decision("ARTIFACT-TESTS", "approve")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")


def _artifact_payload(status="pending", label=PROPOSAL_LABEL):
    return {
        "success": True,
        "artifact": {
            "artifact_id": "ARTIFACT-TESTS",
            "mission_id": "MISSION-1",
            "content": {
                "proposal_id": "CHARLIE-IMPROVEMENT-TESTS",
                "label": label,
                "status": status,
                "problem_detected": "Repeated test weakness across CHARLIE missions.",
                "recommendation": "Tighten test gates.",
                "target_area": "tests",
                "decision_history": [],
                "applies_automatically": False,
            },
            "created_by_agent": "charlie_improvement_analyst",
            "created_at": "2026-07-01T10:00:00+00:00",
        },
    }


if __name__ == "__main__":
    unittest.main()
