import unittest

from modules.charlie.core_workflow import (
    AGENT_DOCTRINE_PATHS,
    HANDOFF_VERSION,
    VAULT_SCHEMA,
    WORKFLOW_TEMPLATES,
    agent_instruction_pack,
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
from modules.charlie.model_registry import choose_agent_model


class CharlieCoreWorkflowTests(unittest.TestCase):
    def test_templates_cover_required_mission_types(self):
        expected = {
            "ui_product_build",
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
        self.assertEqual(classify_workflow_template("feature build", "rebuild dashboard UI from screenshot"), "ui_product_build")

    def test_non_ui_visual_gate_language_does_not_route_to_ui_workflow(self):
        self.assertEqual(
            classify_workflow_template(
                "system canary",
                "Verify non-UI visual pause gate hardening for risk_agent without frontend work.",
            ),
            "system_improvement",
        )
        self.assertEqual(
            classify_workflow_template(
                "system improvement",
                "Run a no UI owner review packet persistence canary. Do not change UI or product behavior.",
            ),
            "system_improvement",
        )
        self.assertEqual(
            classify_workflow_template(
                "system improvement",
                "Verify the runner without UI changes and without frontend work.",
            ),
            "system_improvement",
        )

    def test_ui_product_build_routes_through_design_council(self):
        mission = {
            "mission_id": "CHARLIE-MISSION-UI",
            "title": "Mission Control dashboard UI",
            "raw_text": "Rebuild the CHARLIE command center to match the attached screenshot.",
            "mission_type": "dashboard ui",
        }
        metadata = attach_core_plan_to_metadata(mission, {})
        agents = [item["agent"] for item in metadata["agent_workflow"]]

        expected_agents = [
            "visual_reference_interpreter",
            "creative_ui_designer",
            "ux_interaction_designer",
            "frontend_design_implementer",
            "visual_qa_reviewer",
        ]
        for agent in expected_agents:
            self.assertIn(agent, agents)
            self.assertTrue(AGENT_DOCTRINE_PATHS.get(agent))
        self.assertLess(agents.index("creative_ui_designer"), agents.index("frontend_design_implementer"))
        self.assertLess(agents.index("frontend_design_implementer"), agents.index("visual_qa_reviewer"))

    def test_software_build_routes_through_product_reviewer(self):
        mission = {
            "mission_id": "CHARLIE-MISSION-FEATURE",
            "title": "Litter Detail View",
            "raw_text": "Update the litter detail view so closed and active litter states are clear.",
            "mission_type": "feature build",
        }
        metadata = attach_core_plan_to_metadata(mission, {})
        agents = [item["agent"] for item in metadata["agent_workflow"]]

        self.assertIn("product_architect", agents)
        self.assertIn("product_reviewer", agents)
        self.assertIn("evidence_reviewer", agents)
        self.assertLess(agents.index("product_architect"), agents.index("builder"))
        self.assertLess(agents.index("tester"), agents.index("product_reviewer"))
        self.assertLess(agents.index("product_reviewer"), agents.index("reviewer"))

    def test_explicit_simple_non_ui_fix_uses_right_sized_pipeline(self):
        mission = {
            "mission_id": "CHARLIE-MISSION-SIMPLE",
            "title": "Simple backend bug fix",
            "raw_text": "Fix a small backend service regression. No UI changes, no frontend changes.",
            "mission_type": "feature build",
        }
        metadata = attach_core_plan_to_metadata(mission, {})
        agents = [item["agent"] for item in metadata["agent_workflow"]]

        self.assertEqual(metadata["mission_vault"]["project_truth"]["pipeline_profile"], "minimal_software_fix")
        self.assertTrue(metadata["mission_vault"]["project_truth"]["workflow_right_sized"])
        self.assertIn("builder", agents)
        self.assertIn("tester", agents)
        self.assertIn("qa_red_team", agents)
        self.assertIn("reviewer", agents)
        self.assertNotIn("idea_expander", agents)
        self.assertNotIn("product_architect", agents)
        self.assertLess(len(agents), len(WORKFLOW_TEMPLATES["software_build"]["agent_order"]))

    def test_ui_and_sensitive_work_stay_on_full_pipeline(self):
        mission = {
            "mission_id": "CHARLIE-MISSION-UI",
            "title": "Dashboard rebuild",
            "raw_text": "Rebuild the dashboard UI with a clean workflow.",
            "mission_type": "feature build",
        }
        metadata = attach_core_plan_to_metadata(mission, {})
        ui_agents = [item["agent"] for item in metadata["agent_workflow"]]

        sensitive = {
            "mission_id": "CHARLIE-MISSION-SAFE",
            "title": "Payment route fix",
            "raw_text": "Fix a small payment status regression. No UI changes.",
            "mission_type": "feature build",
        }
        sensitive_metadata = attach_core_plan_to_metadata(sensitive, {})
        sensitive_agents = [item["agent"] for item in sensitive_metadata["agent_workflow"]]

        self.assertEqual(metadata["mission_vault"]["project_truth"]["workflow_template"], "ui_product_build")
        self.assertIn("creative_ui_designer", ui_agents)
        self.assertFalse(sensitive_metadata["mission_vault"]["project_truth"]["workflow_right_sized"])
        self.assertIn("product_architect", sensitive_agents)

    def test_design_agents_have_specific_model_assignments(self):
        visual = choose_agent_model("creative_ui_designer", mission_type="dashboard ui")
        implementer = choose_agent_model("frontend_design_implementer", mission_type="dashboard ui")
        qa = choose_agent_model("visual_qa_reviewer", mission_type="dashboard ui")

        self.assertEqual(visual["registry_key"], "vision_design")
        self.assertEqual(implementer["registry_key"], "frontend_build")
        self.assertEqual(qa["registry_key"], "vision_design")

    def test_agent_instruction_pack_requires_confidence_or_clarification(self):
        pack = agent_instruction_pack("builder")
        rules = " ".join(pack["vault_rules"] + pack["quality_bar"]).lower()

        self.assertIn("96", rules)
        self.assertIn("clarifying", rules)
        self.assertIn("evidence", rules)
        self.assertIn("confidence", rules)

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
        agents = [item["agent"] for item in metadata["agent_workflow"]]
        self.assertIn("product_architect", agents)
        self.assertIn("source_mapper", agents)
        self.assertIn("council_synthesis", agents)
        self.assertIn("product_reviewer", agents)
        self.assertTrue(all(AGENT_DOCTRINE_PATHS.get(agent) for agent in agents))

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
