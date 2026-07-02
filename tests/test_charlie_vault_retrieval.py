import unittest

from modules.charlie.vault_retrieval import (
    autonomy_readiness_packet,
    evaluate_vault_source_coverage,
    owner_preference_packet,
    retrieve_vault_sources,
)


class CharlieVaultRetrievalTests(unittest.TestCase):
    def test_retrieve_vault_sources_selects_keyword_and_base_docs(self):
        packet = retrieve_vault_sources({
            "title": "Fix bulk weight upload",
            "raw_text": "Bulk weight upload needs farm data and pig weight rules.",
            "mission_type": "bugfix",
        }, limit=16, excerpt_chars=80)

        paths = [item["path"] for item in packet["sources"]]

        self.assertEqual(packet["version"], "charlie_vault_retrieval_v1")
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
