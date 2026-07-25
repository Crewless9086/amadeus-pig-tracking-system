import unittest

from modules.charlie.adaptive_orchestration import (
    build_orchestration_packet,
    expand_orchestration,
    throughput_snapshot,
)
from modules.charlie.core_workflow import attach_core_plan_to_metadata, build_core_plan


class AdaptiveOrchestrationTests(unittest.TestCase):
    def agents(self, mission):
        return [row["agent"] for row in build_orchestration_packet(mission)["selected_agents"]]

    def test_read_only_audit_is_t0_without_mutation_roles(self):
        packet = build_orchestration_packet({"mission_type": "audit", "raw_text": "Read-only status audit."})
        self.assertEqual(packet["tier"], "T0")
        self.assertEqual(self.agents({"mission_type": "audit", "raw_text": "Read-only status audit."}), ["source_mapper"])
        self.assertEqual(packet["authority_contract"]["permitted_writes"], [])

    def test_trivial_document_fix_is_short_t1(self):
        packet = build_orchestration_packet({"mission_type": "documentation", "raw_text": "Fix typo in README.md."})
        self.assertEqual(packet["tier"], "T1")
        self.assertEqual([x["agent"] for x in packet["selected_agents"]], ["builder", "tester", "reviewer"])
        self.assertLessEqual(packet["budgets"]["maximum_elapsed_minutes"], 120)

    def test_small_backend_fix_uses_three_roles(self):
        self.assertEqual(
            self.agents({"mission_type": "bug fix", "raw_text": "Fix one bounded service regression in modules/x.py."}),
            ["builder", "tester", "reviewer"],
        )

    def test_farm_and_sales_select_domain_reviewers(self):
        farm = self.agents({"mission_type": "feature", "raw_text": "Implement Herdmaster pig observation service."})
        sales = self.agents({"mission_type": "feature", "raw_text": "Implement SAM sales order handling."})
        self.assertIn("product_reviewer", farm)
        self.assertIn("business_reviewer", sales)

    def test_ui_requires_visual_specialists(self):
        agents = self.agents({"mission_type": "feature", "raw_text": "Rebuild UI from screenshot."})
        self.assertTrue({"creative_ui_designer", "frontend_design_implementer", "visual_qa_reviewer"}.issubset(agents))

    def test_protected_triggers_cannot_remain_t1(self):
        cases = {
            "schema migration": "evidence_reviewer",
            "payment processing": "business_reviewer",
            "publish campaign spend": "business_reviewer",
            "ROOTLINE valve control": "evidence_reviewer",
            "authentication credential change": "security_reviewer",
            "Telegram customer send": "business_reviewer",
        }
        for text, specialist in cases.items():
            with self.subTest(text=text):
                packet = build_orchestration_packet({"mission_type": "fix", "raw_text": text})
                self.assertEqual(packet["tier"], "T4")
                self.assertIn(specialist, [x["agent"] for x in packet["selected_agents"]])
                self.assertIn("publisher", [x["agent"] for x in packet["selected_agents"]])

    def test_material_security_evidence_expands_before_execution(self):
        original = build_orchestration_packet({"mission_type": "fix", "raw_text": "Fix typo in module comment."})
        expanded = expand_orchestration(original, {"mission_type": "fix", "raw_text": "Fix typo in module comment."},
                                        {"discovered": "authentication credential impact"})
        self.assertNotEqual(original["generation_identity"], expanded["generation_identity"])
        self.assertIn("security_reviewer", [x["agent"] for x in expanded["selected_agents"]])
        self.assertTrue(expanded["expansion_history"])

    def test_unchanged_evidence_does_not_create_generation(self):
        mission = {"mission_type": "fix", "raw_text": "Fix typo in README.md."}
        packet = build_orchestration_packet(mission)
        self.assertEqual(expand_orchestration(packet, mission, {}), packet)

    def test_existing_workflow_remains_frozen(self):
        existing = [{"agent": "planner", "status": "complete"}]
        metadata = attach_core_plan_to_metadata({"mission_type": "bug fix", "raw_text": "small fix"}, {"agent_workflow": existing})
        self.assertEqual(metadata["agent_workflow"], existing)
        self.assertIn("orchestration", metadata)

    def test_core_plan_exposes_selection_reasons_authority_and_budgets(self):
        plan = build_core_plan({"mission_type": "bug fix", "raw_text": "Fix one bounded regression in modules/x.py."})
        self.assertEqual(plan["orchestration"]["tier"], "T1")
        for stage in plan["agent_workflow"]:
            self.assertIn("selection_reason", stage)
            self.assertIn("authority", stage)
            self.assertIn("budget", stage)

    def test_candidate_binding_and_lineage_remain_required(self):
        packet = build_orchestration_packet({"mission_type": "bug fix", "raw_text": "Fix module regression."})
        self.assertTrue(packet["validation_contract"]["candidate_binding_required"])
        self.assertTrue(packet["validation_contract"]["durable_lineage_required"])

    def test_throughput_is_grouped_by_tier(self):
        packets = [
            {**build_orchestration_packet({"raw_text": "Read-only status audit"}), "final_outcome": "owner_ready", "elapsed_seconds": 60, "agent_execution_count": 1},
            {**build_orchestration_packet({"raw_text": "Fix typo in README.md"}), "final_outcome": "owner_ready", "elapsed_seconds": 600, "agent_execution_count": 3},
        ]
        report = throughput_snapshot(packets)
        self.assertEqual(report["T0"]["average_elapsed_seconds"], 60)
        self.assertEqual(report["T1"]["agent_executions"], 3)


if __name__ == "__main__":
    unittest.main()
