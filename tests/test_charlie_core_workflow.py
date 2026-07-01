import unittest

from modules.charlie.core_workflow import (
    HANDOFF_VERSION,
    VAULT_SCHEMA,
    WORKFLOW_TEMPLATES,
    attach_core_plan_to_metadata,
    build_core_plan,
    build_handoff_report,
    build_income_stream_readiness,
    build_lesson_record,
    build_review_board_packet,
    classify_workflow_template,
    evaluate_core_readiness,
    evaluate_review_board,
)


class CharlieCoreWorkflowTests(unittest.TestCase):
    def test_templates_cover_required_mission_types(self):
        expected = {
            "software_build",
            "system_improvement",
            "business_plan",
            "content_engine",
            "automation_workflow",
            "income_stream",
        }
        self.assertTrue(expected.issubset(set(WORKFLOW_TEMPLATES)))
        self.assertEqual(classify_workflow_template("income stream", "build FRED revenue path"), "income_stream")
        self.assertEqual(classify_workflow_template("content engine", "BEACON marketing"), "content_engine")

    def test_core_plan_attaches_vault_schema_workflow_and_instruction_packs(self):
        mission = {
            "mission_id": "CHARLIE-MISSION-CORE",
            "title": "Build CHARLIE CORE",
            "raw_text": "Build the full CHARLIE CORE workflow system.",
            "mission_type": "system improvement",
        }
        metadata = attach_core_plan_to_metadata(mission, {})

        self.assertEqual(metadata["charlie_core"]["version"], "charlie_core_v3")
        self.assertEqual(metadata["charlie_core"]["vault_schema"]["version"], VAULT_SCHEMA["version"])
        self.assertEqual(metadata["mission_vault"]["project_truth"]["workflow_template"], "system_improvement")
        self.assertTrue(metadata["agent_workflow"])
        self.assertTrue(all(item["required_output"] == HANDOFF_VERSION for item in metadata["agent_workflow"]))
        self.assertTrue(all(item.get("instruction_pack") for item in metadata["agent_workflow"]))

    def test_handoff_report_requires_auditable_fields(self):
        report = build_handoff_report(
            {"mission_id": "MISSION-1", "title": "Test"},
            "builder",
            {
                "summary": "Built scoped change.",
                "files_inspected": ["modules/charlie/core_workflow.py"],
                "commands_run": ["python -m unittest tests.test_charlie_core_workflow"],
                "changed_files": ["modules/charlie/core_workflow.py"],
                "test_status": "pass",
                "confidence": "98%",
            },
        )

        self.assertEqual(report["version"], HANDOFF_VERSION)
        self.assertTrue(report["validation"]["valid"])
        self.assertEqual(report["agent"], "builder")

    def test_review_board_blocks_until_reviews_pass(self):
        packet = build_review_board_packet({"mission_id": "MISSION-1"})
        pending = evaluate_review_board(packet)
        self.assertFalse(pending["passed"])
        self.assertEqual(pending["decision"], "pending")

        for item in packet["reviews"]:
            item["status"] = "pass"
        passed = evaluate_review_board(packet)
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["decision"], "approve_owner_review")

        packet["reviews"][0]["status"] = "fail"
        failed = evaluate_review_board(packet)
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["decision"], "send_back")

    def test_core_readiness_reaches_ninety_plus_with_full_metadata(self):
        mission = {
            "mission_id": "MISSION-READY",
            "title": "Ready mission",
            "raw_text": "Build a ready mission.",
            "mission_type": "software build",
        }
        metadata = attach_core_plan_to_metadata(mission, {})
        metadata["review_packet"] = {
            "review_status": "ready_for_owner_review",
            "review_board": metadata["charlie_core"]["review_board"],
        }
        metadata["deployment_record"] = {"status": "verified", "commit_sha": "abc123", "verify_url": "https://example.test"}
        readiness = evaluate_core_readiness({
            **mission,
            "metadata": metadata,
            "vault": metadata["mission_vault"],
            "agent_workflow": metadata["agent_workflow"],
        })

        self.assertGreaterEqual(readiness["overall_percent"], 90)
        self.assertTrue(readiness["passed"])

    def test_income_stream_readiness_requires_money_path_gates(self):
        mission = {
            "mission_id": "MISSION-INCOME",
            "mission_type": "income stream",
            "metadata": {
                "mission_vault": {
                    "business_model": {"revenue_logic": "Preorder deposits before fulfillment."},
                    "risk_register": ["Customer promises require owner approval."],
                },
                "owner_review_decisions": [
                    {"decision": "approve_money_path"},
                    {"decision": "approve_customer_contact"},
                ],
                "review_packet": {
                    "review_board": {
                        "reviews": [
                            {"agent": "evidence_reviewer", "status": "pass"},
                            {"agent": "business_reviewer", "status": "pass"},
                        ]
                    }
                },
            },
        }
        readiness = build_income_stream_readiness(mission)

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["missing_gates"], [])

    def test_intelligence_loop_lesson_record_is_structured(self):
        lesson = build_lesson_record(
            {"mission_id": "MISSION-LESSON"},
            failure="Review failed because test evidence was missing.",
            improvement="Require tester handoff before review.",
            source_stage="reviewer",
        )

        self.assertEqual(lesson["status"], "queued")
        self.assertEqual(lesson["source_stage"], "reviewer")
        self.assertIn("test evidence", lesson["failure"])


if __name__ == "__main__":
    unittest.main()
