import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
import unittest
import time
import os
from unittest.mock import patch
from types import SimpleNamespace


class Context:
    def __init__(self): self.tools = {}; self.hooks = {}; self.auxiliary_tasks = []
    def register_tool(self, **kwargs): self.tools[kwargs["name"]] = kwargs
    def register_hook(self, name, handler): self.hooks[name] = handler
    def register_auxiliary_task(self, name, **kwargs): self.auxiliary_tasks.append((name, kwargs))


class HermesNativePluginTests(unittest.TestCase):
    def test_directory_plugin_imports_and_registers_without_application_root(self):
        source = Path("integrations/hermes/charlie_builder").resolve()
        with tempfile.TemporaryDirectory() as folder:
            plugin = Path(folder) / "charlie_builder"
            shutil.copytree(source, plugin)
            outside = Path(folder) / "outside"
            outside.mkdir()
            spec = importlib.util.spec_from_file_location(
                "isolated_charlie_builder", plugin / "__init__.py",
                submodule_search_locations=[str(plugin)],
            )
            module = importlib.util.module_from_spec(spec)
            old_path, old_cwd = list(sys.path), Path.cwd()
            sys.modules[spec.name] = module
            try:
                sys.path[:] = [item for item in sys.path
                               if Path(item or ".").resolve() != old_cwd.resolve()]
                import os
                os.chdir(outside)
                spec.loader.exec_module(module)
                fake = {name: (lambda value: value) for name in (
                    "charlie_reconcile_mission", "charlie_dispatch_cursor",
                    "charlie_get_mission_status", "charlie_get_cursor_status",
                    "charlie_supervise_once", "charlie_continue_cursor",
                    "charlie_issue_admission", "charlie_prepare_owner_decision")}
                context = Context()
                with patch.object(module, "build_plugin_from_environment", return_value=fake):
                    module.register(context)
            finally:
                os.chdir(old_cwd)
                sys.path[:] = old_path
                for name in list(sys.modules):
                    if name == spec.name or name.startswith(spec.name + "."):
                        sys.modules.pop(name, None)
            self.assertEqual(8, len(context.tools))
            self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))
            self.assertEqual(4, len(context.auxiliary_tasks))

    def test_isolated_directory_plugin_uses_real_environment_factory(self):
        source = Path("integrations/hermes/charlie_builder").resolve()
        protected = {
            "CHARLIE_CANONICAL_API_URL": "https://canonical.invalid",
            "CHARLIE_HERMES_GATEWAY_TOKEN": "test-gateway-value-1326",
            "SLACK_SIGNING_SECRET": "test-signing-value-1326",
            "SLACK_BOT_TOKEN": "xoxb-test-value-1326",
            "CHARLIE_SLACK_OWNER_USER_ID": "U0BSRQJASRG",
            "SLACK_APP_TOKEN": "xapp-test-value-1326",
            "CHARLIE_SLACK_CHARLIE_CHANNEL_ID": "C0BSRQJ60KC",
            "CHARLIE_SLACK_BUILD_CHANNEL_ID": "C-BUILD",
            "CHARLIE_SLACK_APPROVALS_CHANNEL_ID": "C-APPROVALS",
        }
        with tempfile.TemporaryDirectory() as folder:
            plugin = Path(folder) / "charlie_builder"
            shutil.copytree(source, plugin)
            outside = Path(folder) / "outside"
            outside.mkdir()
            spec = importlib.util.spec_from_file_location(
                "isolated_charlie_builder_real", plugin / "__init__.py",
                submodule_search_locations=[str(plugin)],
            )
            module = importlib.util.module_from_spec(spec)
            old_path, old_cwd = list(sys.path), Path.cwd()
            sys.modules[spec.name] = module
            try:
                sys.path[:] = [item for item in sys.path
                               if Path(item or ".").resolve() != old_cwd.resolve()]
                os.chdir(outside)
                spec.loader.exec_module(module)
                module._RECOVERY_DISCOVERY_ATTEMPTS = 1
                module._RECOVERY_DISCOVERY_DELAY_SECONDS = 0
                context = Context()
                with patch.dict(os.environ, protected, clear=True):
                    module.register(context)
            finally:
                os.chdir(old_cwd)
                sys.path[:] = old_path
                for name in list(sys.modules):
                    if name == spec.name or name.startswith(spec.name + "."):
                        sys.modules.pop(name, None)
            self.assertEqual(module._BOUNDED_TOOLS, frozenset(context.tools))
            self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))
            self.assertEqual(4, len(context.auxiliary_tasks))

    def test_runtime_package_has_no_application_root_imports(self):
        for name in ("__init__.py", "supervisor.py", "native_executor.py",
                     "schemas.py", "protocol.py"):
            text = (Path("integrations/hermes/charlie_builder") / name).read_text(encoding="utf-8")
            self.assertNotIn("from modules.", text, name)
            self.assertNotIn("import modules.", text, name)

    def test_api_server_schema_is_exactly_the_registered_bounded_plugin_surface(self):
        configured = {"api_server": ["charlie_builder"], "slack": ["charlie_builder"]}
        module = importlib.import_module("integrations.hermes.charlie_builder")
        class Tools(dict):
            pass
        fake = Tools({name: (lambda value: value) for name in module._BOUNDED_TOOLS})
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=fake):
            with patch.object(module, "_RECOVERY_DISCOVERY_ATTEMPTS", 1):
                module.register(context)
        registry = {}
        for name, entry in context.tools.items():
            registry.setdefault(entry["toolset"], set()).add(name)
        resolved = set().union(*(registry.get(toolset, set())
                                 for toolset in configured["api_server"]))
        self.assertEqual(module._BOUNDED_TOOLS, frozenset(resolved))
        self.assertTrue(resolved.isdisjoint({
            "browser_exec", "execute_code", "patch", "read_file", "search_files", "write_file"}))

    def test_failed_plugin_registration_cannot_resolve_generic_api_tools(self):
        configured = {"api_server": ["charlie_builder"]}
        registry = {"generic-coding": {"browser_exec", "execute_code", "write_file"}}
        resolved = set().union(*(registry.get(toolset, set())
                                 for toolset in configured["api_server"]))
        self.assertEqual(set(), resolved)

    def test_startup_discovery_retries_after_transient_canonical_failure(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        calls = {"discovery": 0, "dispatch": 0}
        class Canonical:
            def resumable_native_executions(self):
                calls["discovery"] += 1
                if calls["discovery"] == 1:
                    raise RuntimeError("canonical_authority_unavailable")
                return []
        class Tools(dict):
            pass
        fake = Tools({name: (lambda value: value) for name in module._BOUNDED_TOOLS})
        fake_supervisor = SimpleNamespace(
            canonical=Canonical(), native_llm=None, slack_bot=None,
            dispatch_cursor=lambda value: value,
        )
        fake.supervisor = fake_supervisor
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=fake):
            with patch.object(module, "_RECOVERY_DISCOVERY_ATTEMPTS", 2), \
                    patch.object(module, "_RECOVERY_DISCOVERY_DELAY_SECONDS", 0):
                module.register(context)
                for _ in range(100):
                    if calls["discovery"] == 2:
                        break
                    time.sleep(0.01)
        self.assertEqual(2, calls["discovery"])

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
        self.assertEqual({"charlie_native_builder", "charlie_native_security_reviewer",
                          "charlie_native_functional_reviewer",
                          "charlie_native_challenge_reviewer"},
                         {item[0] for item in context.auxiliary_tasks})

    def test_registration_resumes_one_canonical_native_execution_without_slack_replay(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        observed = []
        recoveries = [[{"mission_id": "CMQ-NATIVE", "slack_channel_id": "C1",
                        "slack_thread_ts": "1.0"}], []]
        canonical = SimpleNamespace(
            resumable_native_executions=lambda: recoveries.pop(0) if recoveries else [])
        supervisor = SimpleNamespace(
            native_llm=None, canonical=canonical, slack_bot=None,
            dispatch_builder=lambda mission: observed.append(("dispatch", mission)) or {"pr_number": 9},
            dispatch_cursor=lambda mission: mission,
            supervise_once=lambda mission: observed.append(("supervise", mission)) or {
                "execution_status": "OWNER_DECISION_REQUIRED"},
        )
        class ToolMap(dict): pass
        tools = ToolMap({name: (lambda value: value) for name in (
            "charlie_reconcile_mission", "charlie_dispatch_cursor", "charlie_get_mission_status",
            "charlie_get_cursor_status", "charlie_supervise_once", "charlie_continue_cursor",
            "charlie_issue_admission", "charlie_prepare_owner_decision")})
        tools.supervisor = supervisor
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=tools):
            module.register(context)
        for _ in range(100):
            if any(item[0] == "supervise" for item in observed): break
            time.sleep(0.01)
        self.assertEqual(1, len([item for item in observed if item[0] == "dispatch"]))
        self.assertEqual("CMQ-NATIVE", observed[0][1]["mission_id"])

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
        self.assertIn("requires_env: []", plugin_manifest)
        self.assertNotIn("  - CURSOR_API_KEY", plugin_manifest)
        self.assertNotIn("SLACK_ALLOWED_USERS", plugin_manifest)
        self.assertIn("pre_gateway_dispatch", plugin_manifest)
        metadata = json.loads(Path("integrations/hermes/charlie_builder/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("channel-managed", metadata["slack_allowlist_authority"])
        self.assertNotIn("slack_gateway_allowed_users_env", metadata)
        self.assertEqual("CHARLIE_GITHUB_PACKAGER_TOKEN", metadata["native_packager_token_env"])
        self.assertEqual("hermes_native", metadata["primary_builder_provider"])

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
        supervisor.canonical = SimpleNamespace(
            prepare_dispatch_authorization=lambda mission_id: observed.append(("authorize", mission_id)) or {"mission_id": mission_id})
        context = Context()
        with patch.object(module, "build_plugin_from_environment", return_value=tools): module.register(context)
        event = SimpleNamespace(text="Pilot mission", message_id="1787904275.776069", internal=False,
            source=SimpleNamespace(platform="slack", user_id="UOWNER", chat_id="C1", thread_id=""))
        result = context.hooks["pre_gateway_dispatch"](event=event)
        self.assertEqual("skip", result["action"])
        for _ in range(100):
            if any(item[0] == "dispatch" for item in observed):
                break
            time.sleep(0.01)
        self.assertEqual(["reconcile", "authorize", "dispatch"], [item[0] for item in observed[:3]])
        self.assertEqual("CMQ-X", observed[2][1]["mission_id"])

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
        supervisor.canonical = SimpleNamespace(prepare_dispatch_authorization=lambda mission_id: {"mission_id": mission_id})
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
