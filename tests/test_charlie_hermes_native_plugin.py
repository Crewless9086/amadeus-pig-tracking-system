import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch


class Context:
    def __init__(self): self.tools = {}
    def register_tool(self, **kwargs): self.tools[kwargs["name"]] = kwargs


class HermesNativePluginTests(unittest.TestCase):
    def test_native_manifest_and_register_surface(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        fake = {
            "charlie_reconcile_mission": lambda value: {"mission_id": "CMQ-X", **value},
            "charlie_dispatch_cursor": lambda value: value,
            "charlie_get_mission_status": lambda value: {"mission": {"mission_id": value["mission_id"], "metadata": {"external_supervisor_state": {"cursor_agent_id": "bc-one"}}}},
            "charlie_get_cursor_status": lambda value: value,
            "charlie_supervise_once": lambda value: value,
            "charlie_continue_cursor": lambda value: value,
            "charlie_issue_admission": lambda value: value,
            "charlie_prepare_owner_decision": lambda value: value,
        }
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=fake):
            module.register(context)
        self.assertEqual(set(fake), set(context.tools))
        for name, registered in context.tools.items():
            self.assertEqual(name, registered["schema"]["name"])
            self.assertFalse(registered["schema"]["parameters"]["additionalProperties"])

    def test_wrappers_use_canonical_state_and_json_results(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        observed = {}
        def status(value):
            return {"mission": {"mission_id": value["mission_id"], "metadata": {
                "external_supervisor_state": {"cursor_agent_id": "bc-one"}}}}
        fake = {name: (lambda value, name=name: observed.setdefault(name, value) or value) for name in (
            "charlie_reconcile_mission", "charlie_dispatch_cursor", "charlie_get_cursor_status",
            "charlie_supervise_once", "charlie_continue_cursor", "charlie_issue_admission",
            "charlie_prepare_owner_decision")}
        fake["charlie_get_mission_status"] = status
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=fake): module.register(context)
        result = json.loads(context.tools["charlie_get_cursor_status"]["handler"]({"mission_id": "CMQ-X"}))
        self.assertEqual("bc-one", result["dispatch"]["cursor_agent_id"])

    def test_socket_mode_manifest_is_bounded(self):
        manifest = Path("integrations/hermes/charlie_builder/slack-app-manifest.yaml").read_text(encoding="utf-8")
        self.assertIn("socket_mode_enabled: true", manifest)
        self.assertNotIn("request_url:", manifest)
        self.assertIn("message.channels", manifest)


if __name__ == "__main__": unittest.main()
