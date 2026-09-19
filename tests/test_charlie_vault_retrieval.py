import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.charlie import vault_retrieval

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
            {"planner": {"vault_sources_used": ["docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md"]}},
            retrieval,
        )

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["forbidden_doctrine_sources"],
            ["docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md"],
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


class VaultRequiredContextTests(unittest.TestCase):
    MISSION = {"title": "CHARLIE CORE Oom Sakkie ROOTLINE HERDMASTER SAM meat BEACON livestock dashboard"}

    def test_additive_packs_and_agent_survive_tiny_limit_and_thirty_doc_cap(self):
        packet = retrieve_vault_sources(self.MISSION, agent="product_architect", limit=1, excerpt_chars=0)
        required = set(packet["mandatory_pack_docs"] + packet["agent_doctrine_docs"] + packet["current_context_docs"])
        self.assertGreater(len(required), 30)
        self.assertEqual({row["path"] for row in packet["sources"]}, required)
        self.assertFalse(packet["missing_mandatory_docs"])
        self.assertTrue(all(row["delivery"] == "metadata_only" for row in packet["sources"]))

    def test_missing_mandatory_doc_beyond_old_cap_blocks_even_with_citations(self):
        target = vault_retrieval.MANDATORY_MISSION_PACKS["sam_meat"][-1]
        original = vault_retrieval._read_repo_text
        with patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: "" if path == target else original(path)):
            packet = retrieve_vault_sources(self.MISSION, limit=1)
        self.assertIn(target, packet["missing_mandatory_docs"])
        result = evaluate_vault_source_coverage({"planner": {"vault_sources_used": packet["mandatory_pack_docs"]}}, packet)
        self.assertFalse(result["passed"])

    def test_coverage_does_not_trust_missing_list_when_mandatory_source_omitted(self):
        packet = retrieve_vault_sources({"title": "ROOTLINE irrigation"}, limit=1)
        omitted = packet["mandatory_pack_docs"][-1]
        packet["sources"] = [row for row in packet["sources"] if row["path"] != omitted]
        packet["missing_mandatory_docs"] = []
        result = evaluate_vault_source_coverage({"planner": {"vault_sources_used": packet["mandatory_pack_docs"]}}, packet)
        self.assertFalse(result["passed"])
        self.assertIn(omitted, result["missing_mandatory_docs"])

    def test_excerpt_is_not_complete_delivery_and_full_text_preserves_utf8_bytes(self):
        target = vault_retrieval.COMMON_MANDATORY_DOCS[0]
        content = "Status: authoritative\r\n" + "Afrikaans: môre. " * 100 + "TAIL REQUIREMENT\r\n"
        original = vault_retrieval._read_repo_text
        with patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: content if path == target else original(path)):
            short = retrieve_vault_sources({}, limit=1, excerpt_chars=12)
            full = retrieve_vault_sources({}, limit=1, excerpt_chars=12, include_full_text=True)
        excerpt = next(row for row in short["sources"] if row["path"] == target)
        supplied = next(row for row in full["sources"] if row["path"] == target)
        self.assertEqual(excerpt["delivery"], "excerpt")
        self.assertTrue(excerpt["excerpt_truncated"])
        self.assertNotIn("full_text", excerpt)
        self.assertEqual(supplied["full_text"].encode("utf-8"), content.encode("utf-8"))
        self.assertEqual(supplied["content_sha256"], hashlib.sha256(content.encode("utf-8")).hexdigest())
        self.assertIn("not model reading or comprehension", full["read_evidence_scope"])

    def test_historical_required_doctrine_fails_closed(self):
        target = vault_retrieval.COMMON_MANDATORY_DOCS[0]
        original = vault_retrieval._read_repo_text
        with patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: "Status: historical\nOld authority" if path == target else original(path)):
            packet = retrieve_vault_sources({}, limit=1)
        self.assertEqual(packet["invalid_mandatory_docs"], [target])
        self.assertFalse(evaluate_vault_source_coverage({"planner": {"vault_sources_used": packet["mandatory_pack_docs"]}}, packet)["passed"])

    def test_file_reader_preserves_bytes_and_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "authority.md"
            content = "  môre\r\nEND\r\n".encode("utf-8")
            path.write_bytes(content)
            with patch.object(vault_retrieval, "REPO_ROOT", root):
                self.assertEqual(vault_retrieval._read_repo_text("authority.md").encode("utf-8"), content)
                path.write_bytes(b"authority\xff")
                self.assertEqual(vault_retrieval._read_repo_text("authority.md"), "")
                self.assertEqual(vault_retrieval._read_repo_text("../outside.md"), "")

    def test_runner_prompt_supplies_complete_required_text_after_budget_exhaustion(self):
        from modules.charlie import execution_bridge
        target = vault_retrieval.COMMON_MANDATORY_DOCS[0]
        content = "Status: authoritative\n" + ("môre " * 9000) + "TAIL AUTHORITY REQUIREMENT\n"
        original = vault_retrieval._read_repo_text
        with patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: content if path == target else original(path)), patch.object(execution_bridge, "VAULT_CONTEXT_CHAR_BUDGET", 1):
            context = execution_bridge.build_vault_brain_context(self.MISSION, "planner")
            prompt = execution_bridge._format_vault_context(context)
            execution_prompt = execution_bridge.build_codex_execution_prompt(self.MISSION)
            with patch.object(execution_bridge, "runner_environment_preflight", return_value={"status": "synthetic_no_execution"}):
                stage_prompt = execution_bridge.build_agent_stage_prompt(self.MISSION, "planner")
        self.assertIn(content, prompt)
        self.assertIn(content, execution_prompt)
        self.assertIn(content, stage_prompt)
        self.assertNotIn("Follow these documents before changing anything:\n- docs/00-start-here", execution_prompt)
        required = set(context["retrieval"]["full_text_required_docs"])
        self.assertEqual({row["path"] for row in context["docs"] if row["delivery"] == "full_text"}, required)
        for row in context["docs"]:
            if row["path"] in required:
                self.assertIn(row["content"], prompt)
        self.assertLessEqual(sum(len(row["content"]) for row in context["docs"] if not row["full_text_required"]), 1)

    def test_optional_excerpt_budget_stops_at_zero_without_capping_required_text(self):
        from modules.charlie import execution_bridge
        with patch.object(execution_bridge, "VAULT_CONTEXT_CHAR_BUDGET", 10):
            context = execution_bridge.build_vault_brain_context({})
        optional = [row for row in context["docs"] if not row["full_text_required"]]
        self.assertGreater(len(optional), 1)
        self.assertEqual(sum(len(row["content"]) for row in optional), 10)
        self.assertTrue(any(row["delivery"] == "metadata_only" for row in optional))
        self.assertTrue(all(row["delivery"] == "full_text" for row in context["docs"] if row["full_text_required"]))

    def test_runner_context_rejects_omitted_required_source_even_when_missing_list_empty(self):
        from modules.charlie import execution_bridge
        packet = retrieve_vault_sources({}, include_full_text=True)
        target = packet["full_text_required_docs"][-1]
        packet["sources"] = [row for row in packet["sources"] if row["path"] != target]
        packet["missing_full_text_required_docs"] = []
        with patch.object(execution_bridge, "retrieve_vault_sources", return_value=packet):
            with self.assertRaisesRegex(ValueError, "vault_required_context_unavailable"):
                execution_bridge.build_vault_brain_context({})

    def test_current_state_and_routing_survive_pack_cap_without_becoming_doctrine(self):
        from modules.charlie import execution_bridge
        register, source_map = vault_retrieval.CURRENT_CONTEXT_DOCS
        content = "# Control Tower Mission Register\nStatus: current-state evidence; non-doctrine\n" + "evidence " * 1000 + "FINAL APPROVAL AND HOLD\n"
        original = vault_retrieval._read_repo_text
        with patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: content if path == register else original(path)):
            packet = retrieve_vault_sources(self.MISSION, limit=1, excerpt_chars=0, include_full_text=True)
            context = execution_bridge.build_vault_brain_context(self.MISSION)
            prompt = execution_bridge._format_vault_context(context)
        by_path = {row["path"]: row for row in packet["sources"]}
        self.assertEqual(by_path[register]["source_class"], "current_state_evidence")
        self.assertEqual(by_path[source_map]["source_class"], "authority_routing")
        self.assertEqual(by_path[register]["full_text"], content)
        self.assertEqual(by_path[source_map]["full_text"], original(source_map))
        self.assertIn(content, prompt)
        self.assertIn("never reusable doctrine", prompt)
        coverage = evaluate_vault_source_coverage({"planner": {"vault_sources_used": packet["mandatory_pack_docs"] + [register]}}, packet)
        self.assertFalse(coverage["passed"])
        self.assertIn(register, coverage["forbidden_doctrine_sources"])

    def test_missing_current_state_or_routing_blocks_stage_prompt(self):
        from modules.charlie import execution_bridge
        original = vault_retrieval._read_repo_text
        for target in vault_retrieval.CURRENT_CONTEXT_DOCS:
            with self.subTest(path=target), patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: "" if path == target else original(path)):
                with self.assertRaisesRegex(ValueError, "vault_required_context_unavailable"):
                    execution_bridge.build_agent_stage_prompt(self.MISSION, "planner")

    def test_runner_prompt_blocks_missing_or_incomplete_pack_before_execution(self):
        from modules.charlie import execution_bridge
        target = vault_retrieval.COMMON_MANDATORY_DOCS[-1]
        original = vault_retrieval._read_repo_text
        with patch.object(vault_retrieval, "_read_repo_text", side_effect=lambda path: "" if path == target else original(path)):
            with self.assertRaisesRegex(ValueError, "vault_required_context_unavailable"):
                execution_bridge.build_codex_execution_prompt(self.MISSION)
        with self.assertRaisesRegex(ValueError, "vault_required_context_unavailable: documents"):
            execution_bridge.build_codex_execution_prompt({"title": "Generate PDF document delivery"})


if __name__ == "__main__":
    unittest.main()
