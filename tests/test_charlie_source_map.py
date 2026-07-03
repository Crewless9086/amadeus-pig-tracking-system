import unittest

from modules.charlie.source_map import (
    implementation_source_packet,
    validate_implementation_inspection,
)
from modules.charlie.vault_retrieval import retrieve_vault_sources


class CharlieSourceMapTests(unittest.TestCase):
    def test_sam_meat_income_mission_maps_existing_implementation(self):
        mission = {
            "mission_type": "income stream",
            "title": "SAM Meat Sales and Beacon pilot readiness",
            "raw_text": "Get Meat Sales running with SAM, Beacon, Chatwoot, WhatsApp, quote, deposit, and pilot post.",
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("sam_meat_sales", keys)
        self.assertIn("beacon_marketing", keys)
        self.assertIn("modules/sales/sam_meat_runtime.py", packet["required_inspection_paths"])
        self.assertIn("tests/test_sam_meat_runtime.py", packet["required_inspection_paths"])
        self.assertIn("/api/sales/channels/chatwoot/sam-meat/inbound", packet["required_routes"])

    def test_live_pig_sales_maps_legacy_and_current_app_sources(self):
        mission = {
            "mission_type": "income stream",
            "title": "Live pig sales agent",
            "raw_text": "Move live pig sales from old n8n WhatsApp API workflow onto Supabase and the app sales dashboard.",
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("live_pig_sales_legacy", keys)
        self.assertIn("orders_sales_transactions", keys)
        self.assertIn("docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md", packet["required_inspection_paths"])
        self.assertIn("modules/sales/sales_transaction_read.py", packet["required_inspection_paths"])

    def test_vault_retrieval_includes_implementation_sources(self):
        mission = {
            "mission_type": "income stream",
            "title": "Meat Sales pilot",
            "raw_text": "Audit SAM Meat Sales and Beacon before live launch.",
        }

        retrieval = retrieve_vault_sources(mission, agent="source_mapper")
        implementation = retrieval["implementation_sources"]

        self.assertTrue(implementation["matched_sections"])
        self.assertIn("sam_meat_sales", {section["key"] for section in implementation["matched_sections"]})
        self.assertIn("docs/09-vault-brain/02-agents/charlie-core/SOURCE_MAPPER.md", retrieval["required_docs"])

    def test_implementation_inspection_requires_code_test_and_vault_sources(self):
        source_packet = implementation_source_packet({
            "mission_type": "income stream",
            "title": "SAM meat readiness",
            "raw_text": "Test SAM Meat Sales.",
        })
        artifact = {
            "files_inspected": [
                "modules/sales/sam_meat_runtime.py",
                "tests/test_sam_meat_runtime.py",
                "docs/09-vault-brain/03-business/MEAT_SALES.md",
                "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
            ],
            "implementation_sources_used": [],
        }

        validation = validate_implementation_inspection(artifact, source_packet)

        self.assertTrue(validation["passed"], validation)
        self.assertEqual(validation["missing_groups"], [])


if __name__ == "__main__":
    unittest.main()
