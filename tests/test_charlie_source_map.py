import unittest
from pathlib import Path

from modules.charlie.source_map import (
    REPO_ROOT,
    implementation_source_packet,
    validate_implementation_inspection,
)
from modules.charlie.vault_retrieval import retrieve_vault_sources


class CharlieSourceMapTests(unittest.TestCase):
    def test_charlie_dashboard_maps_dashboard_sources(self):
        mission = {
            "mission_type": "dashboard ui",
            "title": "CHARLIE CORE dashboard command center",
            "raw_text": "Redesign /charlie Mission Control and prove owner review buttons.",
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("charlie_core_dashboard", keys)
        self.assertIn("static/js/charlieMissionControl.js", packet["required_inspection_paths"])
        self.assertIn("tests/test_frontend_route_contracts.py", packet["required_inspection_paths"])
        self.assertIn("/api/charlie/build-relay/runner/status", packet["required_routes"])

    def test_forbidden_sam_beacon_mentions_do_not_map_sales_sources(self):
        mission = {
            "mission_type": "dashboard ui",
            "title": "CHARLIE CORE dashboard command center",
            "raw_text": "Hold all Beacon/SAM meat posting work; this mission is only for CHARLIE CORE dashboard quality.",
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("charlie_core_dashboard", keys)
        self.assertNotIn("sam_meat_sales", keys)
        self.assertNotIn("beacon_marketing", keys)
        self.assertIn("static/js/charlieMissionControl.js", packet["required_inspection_paths"])
        self.assertNotIn("modules/sales/sam_meat_runtime.py", packet["required_inspection_paths"])
        self.assertNotIn("modules/beacon/media_library.py", packet["required_inspection_paths"])

    def test_forbidden_clause_lists_do_not_map_sales_sources(self):
        mission = {
            "mission_type": "system improvement",
            "title": "CHARLIE CORE Dashboard Command Center UI Retest",
            "raw_text": (
                "This is a CHARLIE CORE dashboard mission only. "
                "Hold all SAM, Beacon, meat sales, Facebook posting, WhatsApp, and income-stream work out of scope. "
                "Do not change SAM, Beacon, meat sales, WhatsApp, Facebook posting, or live income systems. "
                "The source mapper must ignore forbidden/out-of-scope SAM/Beacon/Facebook/WhatsApp clauses. "
                "Rework /charlie Mission Control with owner review buttons and runner status."
            ),
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("charlie_core_dashboard", keys)
        self.assertNotIn("sam_meat_sales", keys)
        self.assertNotIn("beacon_marketing", keys)
        self.assertNotIn("modules/sales/sam_meat_runtime.py", packet["required_inspection_paths"])
        self.assertNotIn("modules/beacon/media_library.py", packet["required_inspection_paths"])

    def test_ui_media_reference_contract_does_not_map_beacon(self):
        mission = {
            "mission_type": "system improvement",
            "title": "CHARLIE CORE Dashboard Command Center UI Retest",
            "raw_text": (
                "UI agents must cite media_references_used and use the attached screenshot. "
                "Rework /charlie Mission Control with owner review buttons and runner status."
            ),
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("charlie_core_dashboard", keys)
        self.assertNotIn("beacon_marketing", keys)
        self.assertNotIn("modules/beacon/media_library.py", packet["required_inspection_paths"])

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

    def test_sam_live_stock_sales_maps_stage_1_2_authority_and_router(self):
        mission = {
            "mission_type": "income stream",
            "title": "SAM Live Stock Sales",
            "raw_text": (
                "Build SAM livestock sales for piglets, weaners, growers, and finishers "
                "using current Supabase app truth, not the old n8n workflow."
            ),
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("sam_live_stock_sales", keys)
        self.assertIn("orders_sales_transactions", keys)
        self.assertIn("modules/sales/sam_sales_router.py", packet["required_inspection_paths"])
        self.assertIn("tests/test_sam_sales_router.py", packet["required_inspection_paths"])
        self.assertIn(
            "docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md",
            packet["required_inspection_paths"],
        )
        self.assertIn(
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json",
            packet["required_inspection_paths"],
        )
        self.assertIn("/api/order-intake/context", packet["required_routes"])

        missing_paths = [
            path for path in packet["required_inspection_paths"]
            if not (REPO_ROOT / Path(path)).exists()
        ]
        self.assertEqual([], missing_paths)

    def test_litter_attention_maps_farm_reconciliation_sources(self):
        mission = {
            "mission_type": "farm data quality / backend logic",
            "title": "Fix litter attention false flags for sold piglets",
            "raw_text": (
                "Litter Attention is showing 6 litters need attention. Detailed view has the correct piglets. "
                "Sold piglets should not create false litter attention flags."
            ),
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("pig_litter_attention", keys)
        self.assertIn("modules/pig_weights/farm_supabase_read_service.py", packet["required_inspection_paths"])
        self.assertIn("tests/test_farm_supabase_read_service.py", packet["required_inspection_paths"])
        self.assertIn("/api/reports/farm-attention-summary", packet["required_routes"])

    def test_herdmaster_pig_allocation_maps_current_allocation_sources(self):
        mission = {
            "mission_type": "planning/docs",
            "title": "Herdmaster Vault Rules and Alert Design Pack",
            "raw_text": (
                "Create Herdmaster Pig Allocation alerts for purpose review, meat window, "
                "slaughter candidate, slow grower, breeding candidate, stale weight, and sow replacement."
            ),
            "vault": {
                "desired_outcome": (
                    "Owner-reviewable Vault/design pack that CHARLIE CORE and Herdmaster can use "
                    "as the authority for future alert builds."
                )
            },
        }

        packet = implementation_source_packet(mission)
        keys = {section["key"] for section in packet["matched_sections"]}

        self.assertIn("pig_allocation_herdmaster", keys)
        self.assertNotIn("charlie_core_dashboard", keys)
        self.assertIn("modules/pig_weights/pig_weights_service.py", packet["required_inspection_paths"])
        self.assertIn(
            "docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md",
            packet["required_inspection_paths"],
        )
        self.assertIn("tests/test_pig_allocation_readiness_service.py", packet["required_inspection_paths"])
        self.assertIn("docs/03-google-sheets/sheets/PIG_MASTER.md", packet["required_inspection_paths"])
        self.assertIn("docs/03-google-sheets/sheets/PIG_OVERVIEW.md", packet["required_inspection_paths"])
        self.assertIn("docs/03-google-sheets/sheets/WEIGHT_LOG.md", packet["required_inspection_paths"])
        self.assertNotIn("docs/03-google-sheets/sheets/FARM.md", packet["required_inspection_paths"])
        self.assertIn("/api/pig-weights/purpose-review", packet["required_routes"])

        missing_paths = [
            path for path in packet["required_inspection_paths"]
            if not (REPO_ROOT / Path(path)).exists()
        ]
        self.assertEqual([], missing_paths)

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

    def test_vault_sources_used_alone_does_not_satisfy_source_mapper_gate(self):
        source_packet = implementation_source_packet({
            "mission_type": "income stream",
            "title": "SAM meat readiness",
            "raw_text": "Test SAM Meat Sales.",
        })
        artifact = {
            "files_inspected": [
                "modules/sales/sam_meat_runtime.py",
                "tests/test_sam_meat_runtime.py",
                "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
            ],
            "implementation_sources_used": [],
            "vault_sources_used": [
                "docs/09-vault-brain/03-business/MEAT_SALES.md",
            ],
        }

        validation = validate_implementation_inspection(artifact, source_packet)

        self.assertFalse(validation["passed"], validation)
        self.assertIn("vault_docs", validation["missing_groups"])


if __name__ == "__main__":
    unittest.main()
