import json
import unittest
from pathlib import Path


class SamLivestockContinuousWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = (
            Path(__file__).parents[1]
            / "docs"
            / "04-n8n"
            / "workflows"
            / "SAM Livestock Continuous Inbound"
            / "workflow.json"
        )
        cls.workflow = json.loads(path.read_text(encoding="utf-8"))

    def test_source_is_inert_until_serialized_activation(self):
        self.assertFalse(self.workflow["active"])

    def test_composed_path_has_webhook_gate_backend_and_response(self):
        names = {node["name"] for node in self.workflow["nodes"]}
        self.assertIn("Chatwoot Message Webhook", names)
        self.assertIn("Gate Exact Livestock Inbound", names)
        self.assertIn("Relay to SAM Livestock Backend", names)
        self.assertIn("Return SAM Result", names)

    def test_gate_binds_account_inbox_and_exact_message_identity(self):
        gate = next(
            node for node in self.workflow["nodes"]
            if node["name"] == "Gate Exact Livestock Inbound"
        )
        code = gate["parameters"]["jsCode"]
        self.assertIn("147387", code)
        self.assertIn("96568", code)
        self.assertIn("inbound_message_id", code)
        self.assertIn("message_created", code)
        self.assertIn("automatic_retry_authorized: false", code)
        self.assertIn(
            "SAM_LIVE_STOCK_CHATWOOT_WEBHOOK_TOKEN",
            code,
        )
        self.assertIn("expectedToken.length >= 32", code)

    def test_relay_uses_backend_auth_without_embedding_secret(self):
        relay = next(
            node for node in self.workflow["nodes"]
            if node["name"] == "Relay to SAM Livestock Backend"
        )
        encoded = json.dumps(relay)
        self.assertIn("SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN", encoded)
        self.assertIn(
            "/api/sales/channels/chatwoot/sam-live-stock/inbound",
            encoded,
        )
        self.assertNotIn("Bearer ey", encoded)


if __name__ == "__main__":
    unittest.main()
