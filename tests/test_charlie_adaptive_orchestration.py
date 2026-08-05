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

    def test_prohibitions_do_not_become_protected_impact(self):
        mission = {
            "mission_type": "read-only audit",
            "raw_text": (
                "Inspect one document read-only. Do not deploy; no publication; "
                "never send customer messages; migration prohibited; no hardware "
                "control; zero writes; no customer action."
            ),
        }
        packet = build_orchestration_packet(mission)
        self.assertEqual(packet["tier"], "T0")
        self.assertEqual([row["agent"] for row in packet["selected_agents"]], ["source_mapper"])
        self.assertFalse(any(packet["score"]["triggers"].values()))

    def test_quoted_and_historical_prohibitions_are_not_current_scope(self):
        packet = build_orchestration_packet({
            "mission_type": "read-only report",
            "raw_text": (
                'Report the historical phrase "do not deploy or publish". '
                "The prior system previously sent customer messages; sending is now prohibited."
            ),
        })
        self.assertEqual(packet["tier"], "T0")
        self.assertFalse(packet["score"]["triggers"]["deployment"])
        self.assertFalse(packet["score"]["triggers"]["publication"])
        self.assertFalse(packet["score"]["triggers"]["customer_delivery"])

    def test_mixed_negative_and_affirmative_clauses_keep_real_trigger(self):
        packet = build_orchestration_packet({
            "mission_type": "change",
            "raw_text": "Do not deploy automatically; prepare a production deployment requiring owner approval.",
        })
        self.assertEqual(packet["tier"], "T4")
        self.assertTrue(packet["score"]["triggers"]["deployment"])

    def test_acceptance_criteria_prohibitions_do_not_raise_tier(self):
        packet = build_orchestration_packet({
            "mission_type": "read-only audit",
            "raw_text": "Inspect one bounded source.",
            "acceptance_criteria": [
                "No customer action",
                "Migration prohibited",
                "No publication",
            ],
        })
        self.assertEqual(packet["tier"], "T0")

    def test_exact_failed_production_canary_wording_is_t0_source_mapper_only(self):
        mission = {
            "title": "Controlled T0 adaptive orchestration production canary",
            "mission_type": "read-only audit",
            "raw_text": (
                "Perform a read-only inventory and report of "
                "docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md. Inspect only. "
                "Do not edit files, write the repository, invoke product routes, contact "
                "customers, perform business actions, deploy, publish, migrate, or control "
                "hardware. Report the documented adaptive orchestration tier and authority "
                "boundary with source evidence."
            ),
            "acceptance_criteria": [
                "T0 orchestration packet is durable before runnable state.",
                "Only Source Mapper runs with zero repository mutation authority.",
                "Final artifact is durably ingested before mission completion.",
            ],
        }
        packet = build_orchestration_packet(mission)
        self.assertEqual(packet["tier"], "T0")
        self.assertEqual([row["agent"] for row in packet["selected_agents"]], ["source_mapper"])
        self.assertEqual(packet["authority_contract"]["permitted_writes"], [])
        self.assertEqual(packet["selected_agents"][0]["allowed_mutations"], [])
        self.assertEqual(packet["budgets"], {
            "maximum_elapsed_minutes": 20,
            "maximum_attempts_per_stage": 1,
            "maximum_recovery_cycles": 1,
            "maximum_tokens": 8000,
        })
        self.assertFalse(any(packet["score"]["triggers"].values()))
        self.assertIn(
            "production_canary",
            packet["score"]["intent_context"]["administrative_labels"],
        )

    def test_administrative_protected_labels_do_not_grant_authority(self):
        for label in (
            "production-shaped evidence",
            "production canary",
            "deployment test",
            "migration audit",
            "publication review",
        ):
            with self.subTest(label=label):
                packet = build_orchestration_packet({
                    "mission_type": "read-only audit",
                    "raw_text": f"Read-only inventory for the {label}. No writes or external action.",
                })
                self.assertEqual(packet["tier"], "T0")
                self.assertEqual(
                    [row["agent"] for row in packet["selected_agents"]],
                    ["source_mapper"],
                )
                self.assertEqual(packet["score"]["protected_triggers"], [])

    def test_genuine_protected_execution_intent_forces_t4(self):
        cases = (
            ("Deploy the approved build to production.", "deployment"),
            ("Publish the approved owner article.", "publication"),
            ("Apply the approved schema migration.", "database"),
            ("Send the approved message to the customer.", "customer_delivery"),
            ("Open the ROOTLINE irrigation valve.", "hardware"),
        )
        for text, trigger in cases:
            with self.subTest(text=text):
                packet = build_orchestration_packet({"mission_type": "operation", "raw_text": text})
                self.assertEqual(packet["tier"], "T4")
                self.assertTrue(packet["score"]["triggers"][trigger])
                self.assertIn("publisher", [row["agent"] for row in packet["selected_agents"]])

    def test_contradictory_read_only_and_protected_intent_fails_before_packet(self):
        with self.assertRaisesRegex(ValueError, "contradictory_read_only_protected_intent"):
            build_orchestration_packet({
                "mission_type": "read-only audit",
                "raw_text": "Read-only report that opens the ROOTLINE irrigation valve.",
            })

    def test_trivial_document_fix_is_short_t1(self):
        packet = build_orchestration_packet({"mission_type": "documentation", "raw_text": "Fix typo in README.md."})
        self.assertEqual(packet["tier"], "T1")
        self.assertEqual([x["agent"] for x in packet["selected_agents"]], ["builder"])
        self.assertLessEqual(packet["budgets"]["maximum_elapsed_minutes"], 120)

    def test_small_backend_fix_uses_one_capable_worker(self):
        self.assertEqual(
            self.agents({"mission_type": "bug fix", "raw_text": "Fix one bounded service regression in modules/x.py."}),
            ["builder"],
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
