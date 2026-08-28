import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace


class Context:
    def __init__(self): self.tools = {}; self.hooks = {}
    def register_tool(self, **kwargs): self.tools[kwargs["name"]] = kwargs
    def register_hook(self, name, handler): self.hooks[name] = handler


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
        with patch.object(module, "build_plugin_from_environment", return_value=fake) as factory:
            module.register(context)
        factory.assert_called_once_with(validate_live=False)
        self.assertEqual(set(fake), set(context.tools))
        self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))
        for name, registered in context.tools.items():
            self.assertEqual(name, registered["schema"]["name"])
            self.assertFalse(registered["schema"]["parameters"]["additionalProperties"])
        self.assertTrue(Path("integrations/hermes/charlie_builder/supervisor.py").is_file())

    def test_registration_never_requires_live_transports(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        fake = {name: (lambda value: value) for name in (
            "charlie_reconcile_mission", "charlie_dispatch_cursor",
            "charlie_get_mission_status", "charlie_get_cursor_status",
            "charlie_supervise_once", "charlie_continue_cursor",
            "charlie_issue_admission", "charlie_prepare_owner_decision")}
        context = Context()

        def build(*, validate_live):
            if validate_live:
                raise RuntimeError("external transport was contacted")
            return fake

        with patch.object(module, "build_plugin_from_environment", side_effect=build):
            module.register(context)

        self.assertEqual(set(fake), set(context.tools))
        self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))

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
        plugin_manifest = Path("integrations/hermes/charlie_builder/plugin.yaml").read_text(encoding="utf-8")
        self.assertIn("SLACK_APP_TOKEN", plugin_manifest)
        self.assertNotIn("SLACK_ALLOWED_USERS", plugin_manifest)
        self.assertIn("pre_gateway_dispatch", plugin_manifest)
        metadata = json.loads(Path("integrations/hermes/charlie_builder/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("channel-managed", metadata["slack_allowlist_authority"])
        self.assertNotIn("slack_gateway_allowed_users_env", metadata)

    def test_authorized_slack_event_is_deterministically_reconciled_and_dispatched(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        observed = []
        class Bot:
            def post(self, *args, **kwargs): observed.append(("post", args, kwargs))
        supervisor = SimpleNamespace(
            owner_slack_user_id="UOWNER", slack_command_channel_id="C1", slack_bot=Bot(),
            reconcile_slack_event=lambda event: observed.append(("reconcile", event)) or {"mission_id": "CMQ-X"},
            dispatch_cursor=lambda mission: observed.append(("dispatch", mission)) or {"cursor_agent_id": "bc-one"},
        )
        class ToolMap(dict): pass
        tools = ToolMap({name: (lambda value: value) for name in (
            "charlie_reconcile_mission", "charlie_dispatch_cursor", "charlie_get_mission_status",
            "charlie_get_cursor_status", "charlie_supervise_once", "charlie_continue_cursor",
            "charlie_issue_admission", "charlie_prepare_owner_decision")})
        tools.supervisor = supervisor
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=tools): module.register(context)
        event = SimpleNamespace(text="Pilot mission", message_id="1787904275.776069", internal=False,
            source=SimpleNamespace(platform="slack", user_id="UOWNER", chat_id="C1", thread_id=""))
        result = context.hooks["pre_gateway_dispatch"](event=event)
        self.assertEqual("skip", result["action"])
        self.assertEqual(["reconcile", "dispatch"], [item[0] for item in observed])
        self.assertEqual("CMQ-X", observed[1][1]["mission_id"])

    def test_wrong_owner_and_channel_are_skipped_without_dispatch(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        observed = []
        supervisor = SimpleNamespace(
            owner_slack_user_id="UOWNER", slack_command_channel_id="C1", slack_bot=None,
            reconcile_slack_event=lambda event: observed.append(("reconcile", event)),
            dispatch_cursor=lambda mission: observed.append(("dispatch", mission)),
        )
        class ToolMap(dict): pass
        tools = ToolMap({name: (lambda value: value) for name in (
            "charlie_reconcile_mission", "charlie_dispatch_cursor", "charlie_get_mission_status",
            "charlie_get_cursor_status", "charlie_supervise_once", "charlie_continue_cursor",
            "charlie_issue_admission", "charlie_prepare_owner_decision")})
        tools.supervisor = supervisor
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=tools): module.register(context)
        for owner, channel in (("UOTHER", "C1"), ("UOWNER", "COTHER")):
            event = SimpleNamespace(text="Pilot", message_id=f"{owner}:{channel}", internal=False,
                source=SimpleNamespace(platform="slack", user_id=owner, chat_id=channel, thread_id=""))
            result = context.hooks["pre_gateway_dispatch"](event=event)
            self.assertEqual({"action": "skip", "reason": "slack_ingress_not_authorized"}, result)
        self.assertEqual([], observed)

    def test_slack_hook_failure_and_tool_boundary_fail_closed(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        posts = []
        class Bot:
            def post(self, *args, **kwargs): posts.append((args, kwargs))
        supervisor = SimpleNamespace(
            owner_slack_user_id="UOWNER", slack_command_channel_id="C1", slack_bot=Bot(),
            reconcile_slack_event=lambda _event: {"mission_id": "CMQ-X"},
            dispatch_cursor=lambda _mission: (_ for _ in ()).throw(RuntimeError("current_canonical_admission_required")),
        )
        class ToolMap(dict): pass
        tools = ToolMap({name: (lambda value: value) for name in (
            "charlie_reconcile_mission", "charlie_dispatch_cursor", "charlie_get_mission_status",
            "charlie_get_cursor_status", "charlie_supervise_once", "charlie_continue_cursor",
            "charlie_issue_admission", "charlie_prepare_owner_decision")})
        tools.supervisor = supervisor
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=tools): module.register(context)
        event = SimpleNamespace(text="Pilot", message_id="1.0", internal=False,
            source=SimpleNamespace(platform="slack", user_id="UOWNER", chat_id="C1", thread_id="1.0"))
        result = context.hooks["pre_gateway_dispatch"](event=event)
        self.assertEqual("skip", result["action"])
        self.assertEqual(1, len(posts))
        blocked = context.hooks["pre_tool_call"]("terminal", session_id="agent:main:slack:channel:C1")
        self.assertEqual("block", blocked["action"])
        self.assertEqual("block", context.hooks["pre_tool_call"]("file", session_id="agent:main:slack:channel:C1")["action"])
        self.assertEqual("block", context.hooks["pre_tool_call"]("code_execution", session_id="agent:main:slack:channel:C1")["action"])
        self.assertIsNone(context.hooks["pre_tool_call"]("terminal", session_id="agent:main:cli:local"))


if __name__ == "__main__": unittest.main()
