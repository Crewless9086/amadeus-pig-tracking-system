import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.sales import sales_transaction_routes
from modules.sales.sam_farm_knowledge import load_sam_farm_knowledge, product_menu_text
from modules.sales import sam_meat_runtime
from tests.test_sam_meat_runtime import inbound_payload


class SamFarmKnowledgeTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_default_knowledge_pack_loads(self):
        result = load_sam_farm_knowledge(environ={})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Amadeus Farm", result["knowledge"]["public_profile"]["farm_name"])
        self._assert_public_menu_copy(result["knowledge"])
        self._assert_public_meat_copy(self._build_intro_reply(environ={}))
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["changes_runtime_now"])

    def test_missing_knowledge_file_uses_public_safe_fallback_menu(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing-sam-knowledge.json"
            result = load_sam_farm_knowledge(environ={
                "SAM_FARM_KNOWLEDGE_PATH": str(missing_path),
            })

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "fallback_default_file_missing")
        self.assertFalse(result["configured"])
        self._assert_public_menu_copy(result["knowledge"])
        self._assert_public_meat_copy(self._build_intro_reply(environ={
            "SAM_FARM_KNOWLEDGE_PATH": str(missing_path),
        }))

    def test_custom_knowledge_path_changes_sam_intro_without_code_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sam_knowledge.json"
            path.write_text(json.dumps({
                "public_profile": {
                    "farm_name": "Test Farm",
                    "short_intro": "Hello, Sam here from Test Farm.",
                    "one_line_story": "We raise slow farm pork with a clear preorder story.",
                },
                "product_menu": [
                    {"label": "Story first", "summary": "Ask me about the farm."}
                ],
            }), encoding="utf-8")

            inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
                content="Hi Sam, what can you help with?",
            ))
            facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
            decision = sam_meat_runtime.build_sam_meat_decision(
                inbound,
                facts,
                {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
                201,
                environ={"SAM_FARM_KNOWLEDGE_PATH": str(path)},
            )

        self.assertIn("Hello, Sam here from Test Farm.", decision["reply_text"])
        self.assertIn("slow farm pork", decision["reply_text"])
        self.assertIn("Story first", decision["reply_text"])

    def test_route_returns_current_knowledge(self):
        service_result = {
            "success": True,
            "status": "ok",
            "knowledge": {"public_profile": {"farm_name": "Amadeus Farm"}},
        }
        with patch.object(
            sales_transaction_routes,
            "load_sam_farm_knowledge",
            return_value=service_result,
        ) as loader:
            response = self.client.get("/api/sales/sam-farm-knowledge")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["knowledge"]["public_profile"]["farm_name"], "Amadeus Farm")
        loader.assert_called_once()

    def _assert_public_menu_copy(self, knowledge):
        menu = product_menu_text(knowledge)
        self._assert_public_meat_copy(menu)
        self.assertIn("farm confirms availability", menu.lower())

    def _assert_public_meat_copy(self, text):
        self.assertIn("half carcass", text.lower())
        self.assertNotIn("pilot", text.lower())

    def _build_intro_reply(self, environ):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Hi Sam, what can you help with?",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
            environ=environ,
        )
        return decision["reply_text"]


if __name__ == "__main__":
    unittest.main()
