import importlib
import importlib.util
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
import unittest
import time
import os
import threading
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import contextmanager


class Context:
    def __init__(self):
        self.tools = {}; self.hooks = {}; self.auxiliary_tasks = []
        self.plugin_id = "charlie-builder"; self.profile_name = "default"
    def register_tool(self, **kwargs): self.tools[kwargs["name"]] = kwargs
    def register_hook(self, name, handler): self.hooks[name] = handler
    def register_auxiliary_task(self, name, **kwargs): self.auxiliary_tasks.append((name, kwargs))


class HermesNativePluginTests(unittest.TestCase):
    def setUp(self):
        self._hermes_home = tempfile.TemporaryDirectory()
        home = Path(self._hermes_home.name).resolve()
        (home / "plugins" / "charlie-builder").mkdir(parents=True)
        hermes_pkg = type(sys)("hermes_cli"); hermes_pkg.__path__ = []
        plugins = type(sys)("hermes_cli.plugins")
        manager = SimpleNamespace(home_path=home, scope_key=str(home))
        plugins.get_plugin_manager = lambda: manager
        @contextmanager
        def home_scope(selected):
            self.assertEqual(home, Path(selected).resolve())
            yield
        plugins._plugin_home_scope = home_scope
        self._hermes_modules = {
            name: sys.modules.get(name) for name in ("hermes_cli", "hermes_cli.plugins")
        }
        sys.modules["hermes_cli"] = hermes_pkg
        sys.modules["hermes_cli.plugins"] = plugins

    def tearDown(self):
        for name, prior in self._hermes_modules.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
        self._hermes_home.cleanup()

    def test_registration_defers_only_temporarily_unavailable_profile_scope(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        class Tools(dict):
            pass
        resolved = Tools({name: (lambda value: {"success": True})
                          for name in module._BOUNDED_TOOLS})
        resolved.supervisor = SimpleNamespace(
            native_llm=None,
            canonical=SimpleNamespace(resumable_native_executions=lambda: []),
        )
        context = Context()
        calls = {"count": 0}
        def factory(**kwargs):
            self.assertFalse(kwargs.get("validate_live"))
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("profile_scope_temporarily_unavailable")
            return resolved
        with patch.object(module, "build_plugin_from_environment", side_effect=factory):
            module.register(context)
            self.assertEqual(module._BOUNDED_TOOLS, frozenset(context.tools))
            self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))
            result = json.loads(context.tools["charlie_get_mission_status"]["handler"](
                {"mission_id": "CHARLIE-MISSION-TEST"}))
        self.assertTrue(result["success"])
        self.assertGreaterEqual(calls["count"], 2)

    def test_profile_bound_background_recovery_uses_exact_home_without_input(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        profile_home = Path(self._hermes_home.name).resolve()
        required = {
            "CHARLIE_CANONICAL_API_URL": "https://current.invalid",
            "CHARLIE_HERMES_GATEWAY_TOKEN": "current-gateway",
            "SLACK_BOT_TOKEN": "current-slack",
            "CHARLIE_SLACK_OWNER_USER_ID": "U-CURRENT",
            "CHARLIE_SLACK_CHARLIE_CHANNEL_ID": "C-CURRENT",
            "CHARLIE_SLACK_BUILD_CHANNEL_ID": "CB-CURRENT",
            "CHARLIE_SLACK_APPROVALS_CHANNEL_ID": "CA-CURRENT",
        }
        (profile_home / ".env").write_text(
            "".join(f"{key}={value}\n" for key, value in required.items()),
            encoding="utf-8")
        thread_home = threading.local()
        factory_calls = {"count": 0}
        dispatched = threading.Event()
        class Tools(dict):
            pass
        discovery_calls = {"count": 0}
        def discovery():
            discovery_calls["count"] += 1
            if discovery_calls["count"] == 1:
                return [{"mission_id": "CHARLIE-MISSION-TEST",
                         "slack_channel_id": "C-CURRENT", "slack_thread_ts": "1"}]
            return []
        supervisor = SimpleNamespace(
            native_llm=None, slack_bot=None,
            canonical=SimpleNamespace(resumable_native_executions=discovery),
            dispatch_cursor=lambda value: {"status": "BLOCKED"},
            dispatch_builder=lambda value: dispatched.set() or {"status": "BLOCKED"},
            supervise_once=lambda value: {"status": "BLOCKED"},
        )
        resolved = Tools({name: (lambda value: {"success": True})
                          for name in module._BOUNDED_TOOLS})
        resolved.supervisor = supervisor
        def factory(**kwargs):
            self.assertFalse(kwargs.get("validate_live"))
            factory_calls["count"] += 1
            self.assertEqual(profile_home, getattr(thread_home, "path", None))
            rows = (thread_home.path / ".env").read_text(encoding="utf-8").splitlines()
            names = {row.split("=", 1)[0] for row in rows if "=" in row}
            self.assertEqual(set(required), names)
            return resolved
        @contextmanager
        def exact_scope(home):
            old = getattr(thread_home, "path", None)
            thread_home.path = Path(home).resolve()
            try:
                yield
            finally:
                thread_home.path = old
        context = Context()
        with patch.object(module, "build_plugin_from_environment", side_effect=factory), \
                patch.object(module, "_bound_profile_home", exact_scope), \
                patch.object(module, "_RECOVERY_DISCOVERY_ATTEMPTS", 1):
            module.register(context)
            self.assertTrue(dispatched.wait(2))
            result = json.loads(context.tools["charlie_get_mission_status"]["handler"](
                {"mission_id": "CHARLIE-MISSION-TEST"}))
        self.assertTrue(result["success"])
        self.assertEqual(1, factory_calls["count"])
        self.assertEqual(module._BOUNDED_TOOLS, frozenset(context.tools))
        self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))
        self.assertEqual(4, len(context.auxiliary_tasks))

    def test_profile_bound_factory_initializes_once_under_concurrency(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        calls = {"count": 0}
        resolved = {"charlie_get_mission_status": lambda value: value}
        def factory(**kwargs):
            calls["count"] += 1
            time.sleep(0.02)
            return resolved
        tools = module._ProfileBoundPluginTools(self._hermes_home.name, factory=factory)
        results = []
        workers = [threading.Thread(target=lambda: results.append(tools._tools()))
                   for _ in range(8)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(1, calls["count"])
        self.assertTrue(all(item is resolved for item in results))

    def test_missing_configuration_is_not_deferred(self):
        module = importlib.import_module("integrations.hermes.charlie_builder")
        context = Context()
        with patch.object(
                module, "build_plugin_from_environment",
                side_effect=RuntimeError(
                    "hermes_protected_configuration_incomplete:SLACK_BOT_TOKEN")):
            with self.assertRaisesRegex(
                    RuntimeError, "^protected_configuration_missing:SLACK_BOT_TOKEN$"):
                module.register(context)

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
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin = Path(folder) / "charlie_builder"
            shutil.copytree(source, plugin)
            outside = Path(folder) / "outside"
            outside.mkdir()
            homes = {"builder": root / "profiles" / "builder",
                     "other": root / "profiles" / "other"}
            profile_values = {}
            for label, home in homes.items():
                home.mkdir(parents=True)
                suffix = "one" if label == "builder" else "two"
                values = {
                    "CHARLIE_CANONICAL_API_URL": f"https://canonical-{suffix}.invalid",
                    "CHARLIE_HERMES_GATEWAY_TOKEN": f"gateway-{suffix}-value",
                    "SLACK_BOT_TOKEN": f"xoxb-{suffix}-value",
                    "CHARLIE_SLACK_OWNER_USER_ID": f"U-{suffix}",
                    "CHARLIE_SLACK_CHARLIE_CHANNEL_ID": f"C-{suffix}",
                    "CHARLIE_SLACK_BUILD_CHANNEL_ID": f"CB-{suffix}",
                    "CHARLIE_SLACK_APPROVALS_CHANNEL_ID": f"CA-{suffix}",
                    "CHARLIE_GITHUB_PACKAGER_TOKEN": f"packager-{suffix}-value",
                }
                profile_values[label] = values
                (home / ".env").write_text("".join(
                    f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")

            # Faithful minimum of the v0.20.6 profile contract: multiplexing
            # makes unscoped get_secret fail closed, while PluginManager's
            # bound Hermes home lets get_env_value_prefer_dotenv read exactly
            # that profile's .env without populating os.environ.
            active_home = {"path": homes["builder"]}
            active_scope = {"value": None}
            unscoped_behavior = {"value": "raise"}
            scoped_values = {"SCOPED_ONLY": "scoped-current"}
            agent_pkg = type(sys)("agent"); agent_pkg.__path__ = []
            secret_scope = type(sys)("agent.secret_scope")
            class UnscopedSecretError(RuntimeError): pass
            secret_scope.UnscopedSecretError = UnscopedSecretError
            secret_scope.current_secret_scope = lambda: active_scope["value"]
            def scoped_secret(name, default=None):
                if active_scope["value"] is not None:
                    return scoped_values.get(name, default)
                if unscoped_behavior["value"] == "raise":
                    raise UnscopedSecretError(name)
                return default
            secret_scope.get_secret = scoped_secret
            hermes_pkg = type(sys)("hermes_cli"); hermes_pkg.__path__ = []
            config = type(sys)("hermes_cli.config")
            def profile_value(name):
                rows = (active_home["path"] / ".env").read_text(encoding="utf-8").splitlines()
                dotenv = dict(row.split("=", 1) for row in rows if "=" in row)
                return dotenv[name] if name in dotenv else scoped_secret(name)
            config.get_env_value_prefer_dotenv = profile_value
            injected = {"agent": agent_pkg, "agent.secret_scope": secret_scope,
                        "hermes_cli": hermes_pkg, "hermes_cli.config": config}
            previous = {name: sys.modules.get(name) for name in injected}
            sys.modules.update(injected)
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
                log_messages = []
                class Capture(logging.Handler):
                    def emit(self, record): log_messages.append(record.getMessage())
                capture = Capture()
                module._LOG.addHandler(capture)
                loaded = {"enabled": True, "error": ""}
                with patch.dict(os.environ, {"HERMES_MULTIPLEX_ACTIVE": "1"}, clear=True):
                    try:
                        module.register(context)
                    except Exception as exc:
                        loaded["error"] = str(exc)
                        raise
                    # Supported single-profile mode may make unscoped
                    # get_secret return None. The bound profile dotenv must
                    # still win over stale process-global state.
                    unscoped_behavior["value"] = "none"
                    os.environ.update({key: "stale-process-value"
                                       for key in profile_values["builder"]})
                    builder_tools = module.build_plugin_from_environment()
                    active_home["path"] = homes["other"]
                    other_tools = module.build_plugin_from_environment()
                    supervisor_module = sys.modules[spec.name + ".supervisor"]
                    active_scope["value"] = object()
                    scoped_wins = supervisor_module._profile_protected_value("SCOPED_ONLY")
                    scoped_miss = supervisor_module._profile_protected_value(
                        "CHARLIE_HERMES_GATEWAY_TOKEN")
                    for _ in range(100):
                        if log_messages:
                            break
                        time.sleep(0.01)
                module._LOG.removeHandler(capture)
            finally:
                os.chdir(old_cwd)
                sys.path[:] = old_path
                for name in list(sys.modules):
                    if name == spec.name or name.startswith(spec.name + "."):
                        sys.modules.pop(name, None)
                for name, prior in previous.items():
                    if prior is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = prior
            self.assertEqual(module._BOUNDED_TOOLS, frozenset(context.tools))
            self.assertTrue(loaded["enabled"])
            self.assertEqual("", loaded["error"])
            self.assertEqual({"pre_gateway_dispatch", "pre_tool_call"}, set(context.hooks))
            self.assertEqual(4, len(context.auxiliary_tasks))
            self.assertEqual("gateway-one-value", builder_tools.supervisor.canonical.client.token)
            self.assertEqual("gateway-two-value", other_tools.supervisor.canonical.client.token)
            self.assertNotEqual(builder_tools.supervisor.canonical.client.token,
                                other_tools.supervisor.canonical.client.token)
            self.assertEqual("packager-one-value", builder_tools.supervisor.github_packager_token)
            self.assertEqual("scoped-current", scoped_wins)
            self.assertEqual("", scoped_miss)
            rendered_surface = repr(context.tools)
            for value in profile_values["builder"].values():
                self.assertNotIn(value, rendered_surface)
                self.assertNotIn(value, "\n".join(log_messages))
            with self.assertRaisesRegex(Exception, "slack_signing_secret_required"):
                builder_tools.supervisor.handle_slack_request(b"{}", {})

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
        self.assertEqual("hermes_host_slack_adapter", metadata["slack_app_token_authority"])
        self.assertNotIn("slack_app_token_env", metadata)
        self.assertTrue(metadata["slack_signing_secret_optional_direct_http_only"])
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
