import unittest

from modules.charlie.vault_retrieval import (
    _eligible_current_vault_text,
    autonomy_readiness_packet,
    classify_mission_packs,
    evaluate_vault_source_coverage,
    owner_preference_packet,
    retrieve_vault_sources,
)


class CharlieVaultRetrievalTests(unittest.TestCase):
    def test_current_governance_has_priority_over_matching_legacy_text(self):
        packet = retrieve_vault_sources({"title": "agent operations"}, limit=6, excerpt_chars=0)
        paths = [item["path"] for item in packet["sources"]]

        self.assertEqual(paths[0], "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md")
        self.assertIn("docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md", paths)

    def test_historical_or_superseded_text_is_not_ordinary_current_context(self):
        self.assertFalse(_eligible_current_vault_text("docs/09-vault-brain/old.md", "Status: historical\nOld target"))
        self.assertFalse(_eligible_current_vault_text("docs/09-vault-brain/09-examples/example.md", "Current-looking text"))
        self.assertTrue(_eligible_current_vault_text("docs/09-vault-brain/current.md", "Status: current\nCurrent target"))
        self.assertFalse(_eligible_current_vault_text(
            "docs/09-vault-brain/00-governance/BEACON_HANDOVER_2026-07-27.md",
            "Current-looking handover text",
        ))

    def test_retrieve_vault_sources_selects_keyword_and_base_docs(self):
        packet = retrieve_vault_sources({
            "title": "Fix bulk weight upload",
            "raw_text": "Bulk weight upload needs farm data and pig weight rules.",
            "mission_type": "bugfix",
        }, limit=16, excerpt_chars=80)

        paths = [item["path"] for item in packet["sources"]]

        self.assertEqual(packet["version"], "charlie_vault_retrieval_v2")
        self.assertIn("docs/09-vault-brain/INDEX.md", paths)
        self.assertIn("docs/09-vault-brain/06-data/FARM_DATA_MODEL.md", paths)
        self.assertFalse(packet["missing_docs"])

    def test_retrieve_vault_sources_loads_agent_doctrine(self):
        packet = retrieve_vault_sources({
            "title": "Improve dashboard UI",
            "raw_text": "Make CHARLIE CORE dashboard owner actions visible.",
            "mission_type": "system improvement",
        }, agent="product_architect", limit=20, excerpt_chars=40)

        paths = [item["path"] for item in packet["sources"]]
        self.assertEqual(packet["agent"], "product_architect")
        self.assertIn("docs/09-vault-brain/02-agents/charlie-core/PRODUCT_ARCHITECT.md", paths)
        self.assertIn("docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md", paths)

    def test_retrieve_vault_sources_selects_litter_summary_golden_example(self):
        packet = retrieve_vault_sources({
            "title": "Show litter summary timing data",
            "raw_text": "Improve the litter summary read-service output with focused tests.",
            "mission_type": "feature build",
        }, limit=20, excerpt_chars=40)

        paths = [item["path"] for item in packet["sources"]]

        self.assertIn("docs/09-vault-brain/09-examples/GOLD_STANDARD_LITTER_SUMMARY_PR89.md", paths)

    def test_source_coverage_requires_active_agents_to_cite_vault(self):
        retrieval = retrieve_vault_sources({"title": "CHARLIE runner"}, limit=4, excerpt_chars=0)
        result = evaluate_vault_source_coverage(
            {
                "planner": {"vault_sources_used": ["docs/09-vault-brain/INDEX.md"]},
                "builder": {"vault_sources_used": []},
            },
            retrieval,
        )

        self.assertFalse(result["passed"])
        self.assertIn("builder", result["uncited_agents"])

    def test_ui_mission_requires_facelift_pack(self):
        packet = retrieve_vault_sources({"title": "Facelift the matings UI dashboard"}, limit=30, excerpt_chars=0)

        self.assertIn("ui", packet["mission_pack_keys"])
        self.assertIn(
            "docs/09-vault-brain/07-standards/AMADEUS_FARM_UI_FACELIFT_STANDARD.md",
            packet["mandatory_pack_docs"],
        )
        self.assertFalse(packet["missing_mandatory_docs"])

    def test_beacon_livestock_meta_mission_requires_awareness_policy(self):
        packet = retrieve_vault_sources({
            "title": "BEACON Facebook story for Molly piglets",
            "raw_text": "Prepare a Meta farm-awareness post about the litter.",
        }, limit=30, excerpt_chars=0)

        self.assertIn("beacon_livestock_awareness", packet["mission_pack_keys"])
        self.assertIn(
            "docs/09-vault-brain/04-workflows/BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md",
            packet["mandatory_pack_docs"],
        )

    def test_rootline_and_herdmaster_classification_is_additive(self):
        packs = classify_mission_packs({
            "title": "Oom Sakkie ROOTLINE irrigation and HERDMASTER pig allocation",
        })

        self.assertEqual(packs, ["oom_sakkie", "rootline", "herdmaster"])

    def test_sam_meat_and_livestock_select_distinct_packs(self):
        self.assertEqual(classify_mission_packs({"title": "SAM meat butcher quote"}), ["sam_meat"])
        self.assertEqual(classify_mission_packs({"title": "SAM live pig order"}), ["sam_livestock"])

    def test_documents_pack_fails_closed_until_doctrine_exists(self):
        retrieval = retrieve_vault_sources({"title": "Generate PDF document delivery"}, limit=30, excerpt_chars=0)
        result = evaluate_vault_source_coverage(
            {"planner": {"vault_sources_used": ["docs/09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md"]}},
            retrieval,
        )

        self.assertIn("documents", retrieval["mission_pack_keys"])
        self.assertTrue(retrieval["pack_blockers"])
        self.assertFalse(result["passed"])

    def test_legacy_document_cannot_be_claimed_as_doctrine(self):
        retrieval = retrieve_vault_sources({"title": "ordinary source audit"}, limit=30, excerpt_chars=0)
        result = evaluate_vault_source_coverage(
            {"planner": {"vault_sources_used": ["docs/05-ai/agents/beacon/BEACON_SCOPE.md"]}},
            retrieval,
        )

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["forbidden_doctrine_sources"],
            ["docs/05-ai/agents/beacon/BEACON_SCOPE.md"],
        )

    def test_current_state_and_vault_handover_cannot_be_claimed_as_doctrine(self):
        retrieval = retrieve_vault_sources({"title": "ordinary source audit"}, limit=30, excerpt_chars=0)
        result = evaluate_vault_source_coverage(
            {"planner": {"vault_sources_used": [
                "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md",
                "docs/09-vault-brain/00-governance/BEACON_HANDOVER_2026-07-27.md",
            ]}},
            retrieval,
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["forbidden_doctrine_sources"], [
            "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md",
            "docs/09-vault-brain/00-governance/BEACON_HANDOVER_2026-07-27.md",
        ])

    def test_registered_outside_vault_exceptions_remain_allowed(self):
        retrieval = retrieve_vault_sources({"title": "ordinary source audit"}, limit=30, excerpt_chars=0)
        result = evaluate_vault_source_coverage(
            {"planner": {"vault_sources_used": [
                "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
                "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
                "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md",
            ]}},
            retrieval,
        )

        self.assertFalse(result["forbidden_doctrine_sources"])

    def test_missing_mandatory_pack_document_fails_coverage(self):
        retrieval = retrieve_vault_sources({"title": "ROOTLINE irrigation"}, limit=30, excerpt_chars=0)
        retrieval["missing_mandatory_docs"] = ["docs/09-vault-brain/02-agents/farm/ROOTLINE.md"]
        result = evaluate_vault_source_coverage(
            {"planner": {"vault_sources_used": ["docs/09-vault-brain/02-agents/farm/ROOTLINE.md"]}},
            retrieval,
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["missing_mandatory_docs"], ["docs/09-vault-brain/02-agents/farm/ROOTLINE.md"])

    def test_owner_preference_packet_is_enforceable_context(self):
        packet = owner_preference_packet()

        self.assertEqual(packet["owner"], "CHARL")
        self.assertTrue(packet["preferences"])
        self.assertIn("Brain Guard blocks weak Vault usage.", packet["enforcement"])

    def test_autonomy_readiness_keeps_self_approval_off(self):
        packet = autonomy_readiness_packet({"improvements": {"pending": []}, "vault": {"health": {"success": True}}})

        self.assertFalse(packet["checks"]["self_approval"])
        self.assertFalse(packet["checks"]["autonomous_release"])
        self.assertEqual(packet["safe_mode"], "supervised_missions_only")


if __name__ == "__main__":
    unittest.main()
