import unittest

from modules.charlie.agent_runtime import AgentDefinition, assess_evidence, delegate_to_agent, register_agent, registered_agents


class CharlieAgentRuntimeTests(unittest.TestCase):
    def test_default_registry_exposes_operational_herdmaster_contract(self):
        herdmaster = next(row for row in registered_agents() if row["agent_id"] == "herdmaster")
        self.assertEqual(herdmaster["authority_tier"], "read_only")
        self.assertIn("herd_inventory", herdmaster["capabilities"])
        self.assertIn("Supabase pig_current_state", herdmaster["source_contract"])

    def test_delegate_wraps_evidence_and_records_agent_telemetry(self):
        recorded = []
        register_agent(AgentDefinition(
            "test-agent", "Test Agent", "test", "read_only", ("inspect",), ("test_source",),
            lambda _request: {"success": True, "direct_answer": "42", "sources": [{"name": "test_source"}], "freshness": {"mode": "live"}, "confidence": .99},
        ))
        result, status = delegate_to_agent("test-agent", {"question": "What is the answer?", "capability": "inspect"}, intent_id="I-1", recorder=lambda *args, **kwargs: recorded.append((args, kwargs)))
        self.assertEqual(status, 200)
        self.assertTrue(result["agent"]["evidence_sufficient"])
        self.assertFalse(result["write_authority"])
        self.assertEqual(recorded[0][0][1], "agent.test-agent.inspect")

    def test_evidence_assessment_rejects_confident_sounding_unsourced_answer(self):
        sufficient, gaps = assess_evidence({"success": True, "direct_answer": "Probably 12", "confidence": .99, "freshness": {"mode": "live"}})
        self.assertFalse(sufficient)
        self.assertIn("source_provenance_missing", gaps)

    def test_runtime_records_agent_resolved_capability(self):
        register_agent(AgentDefinition(
            "routing-agent", "Routing Agent", "test", "read_only", ("overview", "inventory"), ("source",),
            lambda _request: {"success": True, "capability": "inventory", "direct_answer": "12", "sources": [{"name": "source"}], "freshness": {"mode": "live"}, "confidence": .99},
        ))
        recorded = []
        result, status = delegate_to_agent("routing-agent", {"question": "Count them", "capability": "overview"}, intent_id="I-2", recorder=lambda *args, **kwargs: recorded.append((args, kwargs)))
        self.assertEqual(status, 200)
        self.assertEqual(result["agent"]["capability"], "inventory")
        self.assertEqual(recorded[0][0][1], "agent.routing-agent.inventory")


if __name__ == "__main__":
    unittest.main()
