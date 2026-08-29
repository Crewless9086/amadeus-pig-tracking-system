import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask

from modules.charlie.hermes_supervisor import (
    CanonicalCharlieApi, CursorCloudV1, GitHubReadMonitor, HermesBridgeError,
    HermesSupervisor, SlackBot, build_plugin_from_environment,
    verify_slack_request,
)
from modules.charlie.mission_store import (
    authorize_cursor_workspace_hook,
    bind_external_supervisor_branch,
    bind_external_supervisor_candidate,
    invalidate_external_candidate_admission,
    prepare_external_dispatch_authorization,
    prepare_external_execution_succession,
    refresh_external_dispatch_authorization_base,
    record_external_supervisor_state,
)
from tests.test_charlie_mission_store import FakeConnection


def admission():
    return {"mission_id": "CMQ-X", "generation": "g1", "receipt_id": "MAR-" + "A" * 64,
            "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
            "allowed_files": ["modules/charlie/example.py"], "allowed_effects": ["repository_source"],
            "owner_instruction_digest": "b" * 64, "acceptance_requirements": ["tests pass"]}


class FakeClient:
    def __init__(self): self.calls = []; self.agent_state = "IDLE"; self.conflict_once = False; self.run_branches = []
    def request(self, method, path, payload=None, headers=None, query=None):
        self.calls.append((method, path, payload, query))
        if path == "/v1/agents":
            if self.conflict_once:
                self.conflict_once = False
                return {"error": "conflict", "status_code": 409}
            return {"agent": {"id": payload["agentId"]}, "run": {"id": "run-one"}}
        if path.endswith("/runs") and method == "POST": return {"run": {"id": "run-two"}}
        if path.endswith("/runs/run-one"): return {"id": "run-one", "status": "SUCCEEDED", "updatedAt": "2026-08-28T00:00:00Z", "git": {"branches": self.run_branches}}
        if path.startswith("/v1/agents/bc-") and "/runs/" not in path:
            return {"id": path.rsplit("/", 1)[-1], "status": self.agent_state, "latestRunId": "run-one"}
        return {"items": []}


class Canonical:
    def __init__(self): self.dispatch = {}; self.reconciled = 0; self.running = 0; self.intake = {}; self.admitted = True; self.dispatch_authorized = False; self.admission_requests = []; self.branch_bindings = []; self.base_refreshes = []
    def reconcile_mission(self, payload, idempotency_key):
        if idempotency_key not in self.intake:
            self.reconciled += 1; self.intake[idempotency_key] = {"mission_id": "CMQ-X", "key": idempotency_key}
        return self.intake[idempotency_key]
    def get_dispatch(self, key): return self.dispatch.get(key)
    def get_mission(self, mission_id):
        current = admission()
        pre = {"status": "valid", "mission_id": mission_id, "generation": "g1",
            "authorization_id": "PDA-" + "A" * 64,
            "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
            "branch": "cursor/cmq-x-g1", "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
            "allowed_effects": ["create_feature_branch"], "owner_instruction_digest": "b" * 64}
        return {"mission": {"mission_id": mission_id, "raw_text": "Canonical bounded work", "metadata": {
            "mission_admission": {**current, "latest_correction_digest": current["owner_instruction_digest"],
                                  "status": "valid" if self.admitted else "revoked"},
            "mission_admission_contract": {"generation": current["generation"], "base_sha": current["base_sha"],
                "allowed_files": current["allowed_files"], "allowed_effects": current["allowed_effects"],
                "operational_acceptance": current["acceptance_requirements"]},
            "dispatch_authorization": pre if self.dispatch_authorized else {}}}}
    def prepare_dispatch_authorization(self, mission_id):
        self.dispatch_authorized = True
        return self.get_mission(mission_id)["mission"]["metadata"]["dispatch_authorization"]
    def running_writer_count(self): return self.running
    def record_dispatch(self, key, value): self.dispatch[key] = value; return value
    def record_progress(self, mission_id, value): return value
    def record_followup(self, mission_id, agent_id, run_id, failed_attempts):
        return {"agent_id": agent_id, "run_id": run_id, "failed_attempts": failed_attempts}
    def request_admission(self, mission_id, expected_head_sha, pr_number=0):
        self.admission_requests.append((mission_id, expected_head_sha, pr_number))
        return {"status": "protected_issuer_dispatched"}
    def bind_actual_branch(self, mission_id, **value):
        self.branch_bindings.append((mission_id, value)); return {"status": "external_branch_bound"}
    def refresh_dispatch_base(self, mission_id, **value):
        self.base_refreshes.append((mission_id, value)); return {"status": "base_current"}


class HermesSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(); self.cursor = CursorCloudV1("secret", client=self.client)
        self.canonical = Canonical(); self.supervisor = HermesSupervisor(
            self.canonical, self.cursor, owner_slack_user_id="UOWNER",
            slack_signing_secret="s", slack_command_channel_id="C1",
            slack_build_channel_id="CBUILD", slack_approval_channel_id="CAPPROVE", clock=lambda: 0)

    def test_slack_signature_owner_and_duplicate_identity(self):
        body = b'{"ok":true}'; sig = "v0=" + hmac.new(b"s", b"v0:100:" + body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_slack_request("s", 100, body, sig, now=100))
        event = {"event_id": "Ev1", "user": "UOWNER", "channel": "C1", "ts": "1.0", "text": "Build it"}
        first = self.supervisor.reconcile_slack_event(event); second = self.supervisor.reconcile_slack_event(event)
        self.assertEqual(first["key"], second["key"])
        self.assertEqual(1, self.canonical.reconciled)
        with self.assertRaisesRegex(HermesBridgeError, "slack_owner_not_authorized"):
            self.supervisor.reconcile_slack_event({**event, "user": "UOTHER"})
        with self.assertRaisesRegex(HermesBridgeError, "slack_channel_not_authorized"):
            self.supervisor.reconcile_slack_event({**event, "event_id": "Ev3", "channel": "COTHER"})

    def test_no_admission_no_agent_and_valid_dispatch_is_idempotent(self):
        self.canonical.admitted = False
        with self.assertRaisesRegex(HermesBridgeError, "current_dispatch_authorization_required"):
            self.supervisor.dispatch_cursor({"mission_id": "CMQ-X"})
        self.canonical.prepare_dispatch_authorization("CMQ-X")
        pre = self.supervisor.dispatch_cursor({"mission_id": "CMQ-X"})
        self.assertEqual(self.cursor.deterministic_agent_id("CMQ-X:g1"), pre["cursor_agent_id"])
        self.canonical.dispatch = {}
        self.canonical.admitted = True
        mission = {"mission_id": "CMQ-X", "instruction": "Forged work", "admission": {"receipt_id": "MAR-FAKE"}}
        one = self.supervisor.dispatch_cursor(mission); two = self.supervisor.dispatch_cursor(mission)
        self.assertEqual(one["cursor_agent_id"], two["cursor_agent_id"])
        self.assertEqual(2, len([call for call in self.client.calls if call[0:2] == ("POST", "/v1/agents")]))
        create_payload = [call[2] for call in self.client.calls if call[0:2] == ("POST", "/v1/agents")][-1]
        self.assertIn("Canonical bounded work", create_payload["prompt"]["text"])
        self.assertNotIn("Forged work", create_payload["prompt"]["text"])

    def test_oidc_workspace_pda_late_binds_once_and_enforces_scope_and_command(self):
        pda = {"version": "charlie_pre_dispatch_authorization_v2", "status": "valid",
            "mission_id": "CMQ-X", "generation": "g1", "execution_attempt": 3,
            "active_cursor_agent_id": "bc-three", "branch_binding_status": "unbound", "branch": "",
            "authorization_id": "PDA-OLD", "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
            "owner_instruction_digest": hashlib.sha256(b"pilot").hexdigest(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "allowed_effects": ["edit_allowed_documentation"],
            "allowed_test_commands": ["python -m unittest tests.test_charlie_hermes_supervisor -q"]}
        metadata = {"mission_vault": {"problem_statement": "pilot"}, "dispatch_authorization": pda, "execution_succession": {"active_attempt": 3},
            "external_supervisor_state": {"cursor_agent_id": "bc-three", "generation": "g1",
                                           "execution_attempt": 3}}
        connection = FakeConnection([("CMQ-X", metadata)])
        result, status = authorize_cursor_workspace_hook(
            cloud_agent_id="bc-three", branch_name="cursor/generated", repository="github.com/Crewless9086/amadeus-pig-tracking-system",
            action="repository_file_write", target_path="docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md",
            database_url="postgres://unit", connect_factory=lambda _: connection)
        self.assertEqual(200, status, result)
        saved = json.loads([params["metadata"] for sql, params in connection.cursor_instance.executed
                            if "update public.charlie_missions" in sql][0])
        self.assertEqual("cursor/generated", saved["dispatch_authorization"]["branch"])
        replay_connection = FakeConnection([("CMQ-X", saved)])
        replay, replay_status = authorize_cursor_workspace_hook(
            cloud_agent_id="bc-three", branch_name="cursor/generated", repository="github.com/Crewless9086/amadeus-pig-tracking-system",
            action="shell_verify", command="py -3 -m unittest tests.test_charlie_hermes_supervisor -q",
            database_url="postgres://unit", connect_factory=lambda _: replay_connection)
        self.assertEqual(200, replay_status, replay)
        denied, denied_status = authorize_cursor_workspace_hook(
            cloud_agent_id="bc-three", branch_name="cursor/generated", repository="github.com/Crewless9086/amadeus-pig-tracking-system",
            action="repository_file_write", target_path="app.py", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection([("CMQ-X", saved)]))
        self.assertEqual(403, denied_status)

    def test_cursor_hook_route_requires_oidc_and_returns_bounded_packet(self):
        from modules.charlie import routes
        app = Flask(__name__); app.register_blueprint(routes.charlie_bp)
        missing = app.test_client().post("/charlie/cursor/hooks/authorize", json={"action": "shell_verify"})
        self.assertEqual(401, missing.status_code)
        claims = {"cloud_agent_id": "bc-three", "branch_name": "cursor/generated"}
        with patch.object(routes, "verify_cursor_oidc_token", return_value=claims), \
             patch.object(routes, "authorize_cursor_workspace_hook",
                          return_value=({"success": True, "permission": "allow", "status": "cursor_workspace_authorized",
                                         "authorization_id": "PDA-X", "secret": "never"}, 200)):
            response = app.test_client().post("/charlie/cursor/hooks/authorize",
                headers={"Authorization": "Bearer signed"},
                json={"action": "shell_verify", "command": "git diff --check"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("allow", response.json["permission"])
        self.assertNotIn("secret", response.json)

    def test_canonical_dispatch_payload_matches_bounded_server_schema(self):
        class ApiClient:
            def __init__(self): self.payload = None
            def request(self, method, path, payload=None, **kwargs):
                self.payload = payload
                return {"dispatch": {"cursor_agent_id": "bc-one"}}
        client = ApiClient(); api = CanonicalCharlieApi("https://canonical", "t" * 32, client=client)
        result = api.record_dispatch("CMQ-X:g1", {"generation": "g1", "cursor_agent_id": "bc-one"})
        self.assertNotIn("mission_id", client.payload)
        self.assertEqual("bc-one", result["cursor_agent_id"])
        client.request = lambda *args, **kwargs: {"dispatch": {"independent_review": "SEND_BACK", "cursor_agent_id": "bc-one"}}
        progress = api.record_progress("CMQ-X", {"event": "poll"})
        self.assertEqual("SEND_BACK", progress["independent_review"])

    def test_restart_duplicate_and_writer_capacity(self):
        mission = {"mission_id": "CMQ-X", "instruction": "Bounded work"}
        self.supervisor.dispatch_cursor(mission)
        restarted = HermesSupervisor(self.canonical, self.cursor, owner_slack_user_id="UOWNER",
                                     slack_command_channel_id="C1", slack_build_channel_id="CBUILD",
                                     slack_approval_channel_id="CAPPROVE")
        self.assertEqual("existing_dispatch", restarted.dispatch_cursor(mission)["status"])
        self.canonical.dispatch = {}; self.canonical.running = 1
        with self.assertRaisesRegex(HermesBridgeError, "writer_capacity_reached"):
            restarted.dispatch_cursor(mission)

    def test_split_failure_recovers_deterministic_cursor_agent(self):
        self.client.conflict_once = True
        result = self.supervisor.dispatch_cursor({"mission_id": "CMQ-X", "instruction": "Bounded work"})
        self.assertTrue(result["cursor_agent_id"].startswith("bc-"))
        self.assertEqual("run-one", result["cursor_run_id"])

    def test_slack_envelope_and_actual_tool_handlers(self):
        body = json.dumps({"type": "event_callback", "event_id": "Ev2", "event": {
            "user": "UOWNER", "channel": "C1", "ts": "2.0", "text": "Build it"}}).encode()
        sig = "v0=" + hmac.new(b"s", b"v0:100:" + body, hashlib.sha256).hexdigest()
        result = self.supervisor.handle_slack_request(body, {
            "X-Slack-Request-Timestamp": "100", "X-Slack-Signature": sig}, now=100)
        self.assertEqual("CMQ-X", result["mission_id"])
        self.assertTrue(all(callable(value) for value in self.supervisor.tools().values()))

    def test_send_back_same_agent_busy_and_attempt_limit(self):
        mission = {"mission_id": "CMQ-X", "dispatch": {"cursor_agent_id": "bc-one", "failed_attempts": 0}}
        result = self.supervisor.route_send_back(mission, "SEND_BACK", "fix review")
        self.assertEqual("bc-one", result["agent_id"])
        self.assertEqual(1, result["failed_attempts"])
        self.client.agent_state = "ACTIVE"
        with self.assertRaisesRegex(HermesBridgeError, "cursor_agent_busy"):
            self.supervisor.route_send_back(mission, "SEND_BACK", "fix review")
        with self.assertRaisesRegex(HermesBridgeError, "failed_attempt_limit_reached"):
            self.supervisor.route_send_back({"mission_id": "CMQ-X", "dispatch": {"cursor_agent_id": "bc-one", "failed_attempts": 2}}, "SEND_BACK", "x")

    def test_owner_decision_is_notification_only(self):
        with self.assertRaisesRegex(HermesBridgeError, "owner_decision_not_ready"):
            self.supervisor.prepare_owner_decision({})
        packet = self.supervisor.prepare_owner_decision({"mission_id": "M", "pr_number": 1, "head_sha": "a" * 40,
                                                         "approved_head_sha": "a" * 40,
                                                         "all_required_checks_pass": True, "independent_review": "APPROVE"})
        self.assertFalse(packet["merge_or_deploy_performed"])
        self.assertEqual("CAPPROVE", packet["channel"])

    def test_slack_bot_posts_as_bot_and_preserves_thread(self):
        client = FakeClient(); client.request = lambda method, path, payload=None, **kwargs: {"ok": True, "ts": "2"}
        bot = SlackBot("xoxb-secret", client=client)
        result = bot.post("C1", "Acknowledged", thread_ts="1.0")
        self.assertTrue(result["ok"])

    def test_github_discovers_pull_and_detects_stalled_ci(self):
        class GitHubClient:
            def request(self, method, path, payload=None, headers=None, query=None):
                if path.endswith("/pulls"): return {"items": [{"number": 9}]}
                if path.endswith("/pulls/9"): return {"head": {"sha": "d" * 40, "ref": "feature"}}
                if path.endswith("/check-runs"): return {"check_runs": [{"name": "charlie-core", "status": "queued", "conclusion": None, "started_at": "2026-08-28T00:00:00Z"}]}
                if path.endswith("/reviews"): return {"items": [{"body": "SEND_BACK"}]}
                return {}
        monitor = GitHubReadMonitor("Crewless9086/amadeus-pig-tracking-system", client=GitHubClient())
        self.assertEqual(9, monitor.find_pull("feature"))
        state = monitor.pull_state(9, now=2_000_000_000)
        self.assertTrue(state["ci_stalled"])
        self.assertEqual("SEND_BACK", state["independent_review"])

    def test_poll_discovers_pr_and_invokes_protected_exact_candidate_admission_once(self):
        class Monitor:
            def find_pull(self, branch): return 9
            def pull_state(self, number, now=None):
                return {"pr_number": number, "head_sha": "d" * 40, "branch": "cursor/cmq-x-g1",
                    "checks": {}, "ci_stalled": False, "independent_review": "WAIT"}
        supervisor = HermesSupervisor(self.canonical, self.cursor, owner_slack_user_id="UOWNER",
            slack_command_channel_id="C1", slack_build_channel_id="CBUILD",
            slack_approval_channel_id="CAPPROVE", github=Monitor(), clock=lambda: 0)
        self.canonical.dispatch_authorized = True
        self.client.run_branches = [{"name": "cursor/cmq-x-g1"}]
        result = supervisor.poll({"mission_id": "CMQ-X", "dispatch": {"cursor_agent_id": "bc-one"}})
        self.assertEqual([("CMQ-X", "d" * 40, 9)], self.canonical.admission_requests)
        self.assertEqual("d" * 40, result["admission_requested_head"])
        self.assertEqual("cursor/cmq-x-g1", self.canonical.branch_bindings[0][1]["branches"][0]["name"])
        self.assertEqual("a" * 40, self.canonical.base_refreshes[0][1]["old_base_sha"])

    def test_actual_cursor_branch_binds_once_to_existing_agent(self):
        state = {"generation": "g1", "cursor_agent_id": "bc-one", "cursor_run_id": "run-one"}
        authorization = {"status": "valid", "generation": "g1", "branch": "cursor/requested",
            "base_sha": "a" * 40, "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"]}
        connection = FakeConnection([({"external_supervisor_state": state,
            "dispatch_authorization": authorization},)])
        result, status = bind_external_supervisor_branch(
            "CMQ-X", generation="g1", cursor_agent_id="bc-one", cursor_run_id="run-one",
            repository="Crewless9086/amadeus-pig-tracking-system",
            branches=[{"name": "cursor/actual"}], authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit-test", connect_factory=lambda _: connection)
        self.assertEqual(201, status, result)
        written = [params for sql, params in connection.cursor_instance.executed
                   if "update public.charlie_missions" in sql][0]
        metadata = json.loads(written["metadata"])
        self.assertEqual("cursor/actual", metadata["external_supervisor_state"]["branch"])
        self.assertEqual("cursor/requested", metadata["dispatch_authorization"]["requested_branch"])
        self.assertEqual("cursor/actual", metadata["dispatch_authorization"]["branch"])

    def test_branch_binding_fails_closed_for_zero_multiple_or_wrong_agent(self):
        kwargs = dict(mission_id="CMQ-X", generation="g1", cursor_agent_id="bc-one",
            cursor_run_id="run-one", repository="Crewless9086/amadeus-pig-tracking-system",
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit-test")
        for branches in ([], ["one", "two"]):
            result, status = bind_external_supervisor_branch(
                branches=branches, connect_factory=lambda _: FakeConnection(), **kwargs)
            self.assertEqual(409, status, result)
        metadata = {"external_supervisor_state": {"generation": "g1",
            "cursor_agent_id": "bc-other", "cursor_run_id": "run-one"},
            "dispatch_authorization": {"status": "valid", "generation": "g1"}}
        result, status = bind_external_supervisor_branch(branches=["one"],
            connect_factory=lambda _: FakeConnection([(metadata,)]), **kwargs)
        self.assertEqual(409, status, result)

    def test_disjoint_infrastructure_base_refresh_is_evented_and_bounded(self):
        problem = "Documentation pilot"
        metadata = {"mission_vault": {"problem_statement": problem},
            "external_supervisor_state": {"generation": "g1", "cursor_agent_id": "bc-one"},
            "dispatch_authorization": {"status": "valid", "generation": "g1", "base_sha": "a" * 40,
                "owner_instruction_digest": hashlib.sha256(problem.encode()).hexdigest(),
                "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"]}}
        connection = FakeConnection([(metadata,)])
        result, status = refresh_external_dispatch_authorization_base(
            "CMQ-X", generation="g1", cursor_agent_id="bc-one", old_base_sha="a" * 40,
            new_base_sha="b" * 40, changed_files=[
                ".cursor/hooks.json",
                "modules/charlie/cursor_cloud_identity.py",
                "scripts/charlie_mission_admission_guard.py",
                "tests/test_charlie_cursor_cloud_identity.py",
                "tests/test_charlie_mission_admission.py",
            ],
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit-test",
            connect_factory=lambda _: connection)
        self.assertEqual(201, status, result)
        written = [params for sql, params in connection.cursor_instance.executed
                   if "update public.charlie_missions" in sql][0]
        refreshed = json.loads(written["metadata"])["dispatch_authorization"]
        self.assertEqual("b" * 40, refreshed["base_sha"])
        self.assertTrue(refreshed["authorization_id"].startswith("PDA-"))
        conflict, conflict_status = refresh_external_dispatch_authorization_base(
            "CMQ-X", generation="g1", cursor_agent_id="bc-one", old_base_sha="a" * 40,
            new_base_sha="b" * 40, changed_files=["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"],
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([(metadata,)]))
        self.assertEqual(400, conflict_status, conflict)

    def test_installable_factory_requires_and_consumes_protected_config(self):
        env = {
            "CHARLIE_CANONICAL_API_URL": "https://canonical.example", "CHARLIE_HERMES_GATEWAY_TOKEN": "g" * 32,
            "CURSOR_API_KEY": "cursor", "SLACK_SIGNING_SECRET": "signing", "SLACK_BOT_TOKEN": "xoxb-bot",
            "SLACK_APP_TOKEN": "xapp-app",
            "CHARLIE_SLACK_OWNER_USER_ID": "UOWNER", "CHARLIE_SLACK_CHARLIE_CHANNEL_ID": "C1",
            "CHARLIE_SLACK_BUILD_CHANNEL_ID": "CBUILD", "CHARLIE_SLACK_APPROVALS_CHANNEL_ID": "CAPPROVE",
        }
        tools = build_plugin_from_environment(env)
        self.assertIn("charlie_issue_admission", tools)
        self.assertTrue(all(callable(handler) for handler in tools.values()))
        with self.assertRaisesRegex(HermesBridgeError, "hermes_protected_configuration_incomplete"):
            build_plugin_from_environment({})
        tools_without_process_allowlist = build_plugin_from_environment({**env, "SLACK_ALLOWED_USERS": ""})
        self.assertIn("charlie_dispatch_cursor", tools_without_process_allowlist)
        with self.assertRaisesRegex(HermesBridgeError, "placeholder_rejected"):
            build_plugin_from_environment({**env, "CHARLIE_GITHUB_READ_TOKEN": "placeholder"})
        with self.assertRaisesRegex(HermesBridgeError, "github_write_credential_forbidden"):
            build_plugin_from_environment({**env, "GITHUB_TOKEN": "write-capable"})

    def test_bounded_canonical_issuer_uses_bound_pr_not_caller_pr(self):
        from modules.charlie import routes
        app = Flask(__name__); app.register_blueprint(routes.charlie_bp)
        class Response:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *args): return False
        captured = {}
        def open_request(request, timeout=0):
            captured["body"] = json.loads(request.data)
            return Response()
        mission = {"mission": {"metadata": {"review_packet": {
            "pr_number": 1313, "candidate_revision": "d" * 40}}}}
        def env(name):
            return "g" * 32 if name == "CHARLIE_HERMES_GATEWAY_TOKEN" else "i" * 32
        with patch.object(routes, "env_value", side_effect=env), \
             patch.object(routes, "get_mission", return_value=(mission, 200)), \
             patch.object(routes.urllib.request, "urlopen", side_effect=open_request):
            response = app.test_client().post(
                "/charlie/hermes/missions/CMQ-X/admission",
                headers={"Authorization": "Bearer " + "g" * 32},
                json={"expected_head_sha": "d" * 40, "pr_number": 9999})
        self.assertEqual(202, response.status_code)
        self.assertEqual("1313", captured["body"]["inputs"]["pull_request_number"])

    def test_slack_reconcile_is_explicitly_charlie_software_plane(self):
        from modules.charlie import routes
        app = Flask(__name__); app.register_blueprint(routes.charlie_bp)
        captured = {}
        def record(mission, source_context=None):
            captured.update(mission)
            return {"mission_id": "CHARLIE-MISSION-ONE"}, 201
        payload = {"source": "slack", "source_event_id": "1787929390.145099",
            "owner_user_id": "UOWNER", "channel_id": "C1", "thread_ts": "1787929390.145099",
            "instruction": "Documentation pilot; do not merge or deploy.",
            "idempotency_key": "slack:C1:1787929390.145099"}
        with patch.object(routes, "env_value", return_value="g" * 32), \
             patch.object(routes, "record_mission", side_effect=record):
            response = app.test_client().post("/charlie/hermes/missions",
                headers={"Authorization": "Bearer " + "g" * 32}, json=payload)
        self.assertEqual(201, response.status_code)
        self.assertEqual("system improvement", captured["mission_type"])
        self.assertEqual({"plane": "software", "coordinator": "CHARLIE", "executor": "Cursor Cloud",
            "classification_source": "authenticated_slack_ingress"}, captured["metadata"]["mission_plane"])

    def test_pre_dispatch_authorization_is_bounded_and_replay_safe(self):
        state = {"slack_event_id": "1787929390.145099", "slack_owner_user_id": "UOWNER",
            "slack_channel_id": "C1", "generation": "slack-1787929390.145099-g1"}
        metadata = {"external_supervisor_state": state,
            "mission_vault": {"problem_statement": "Documentation pilot"}}
        connection = FakeConnection([("new", "slack", metadata)])
        result, status = prepare_external_dispatch_authorization(
            "CHARLIE-MISSION-13B47938FF65E2C1", authenticated_principal="hermes:charlie-builder",
            repository="Crewless9086/amadeus-pig-tracking-system", base_sha="a" * 40,
            owner_user_id="UOWNER", channel_id="C1", database_url="postgres://unit-test",
            connect_factory=lambda _: connection)
        self.assertEqual(201, status)
        authorization = result["authorization"]
        self.assertEqual(["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"], authorization["allowed_files"])
        self.assertIn("merge", authorization["forbidden_effects"])
        self.assertIn("deploy", authorization["forbidden_effects"])
        self.assertTrue(authorization["authorization_id"].startswith("PDA-"))

    def test_candidate_change_invalidates_approval(self):
        with self.assertRaisesRegex(HermesBridgeError, "owner_decision_not_ready"):
            self.supervisor.prepare_owner_decision({"mission_id": "M", "pr_number": 1,
                "head_sha": "b" * 40, "approved_head_sha": "a" * 40,
                "all_required_checks_pass": True, "independent_review": "APPROVE"})

    def test_stalled_cursor_run_is_escalated_without_llm(self):
        self.client.agent_state = "ACTIVE"
        supervisor = HermesSupervisor(self.canonical, self.cursor,
                                      owner_slack_user_id="UOWNER", slack_command_channel_id="C1",
                                      slack_build_channel_id="CBUILD", slack_approval_channel_id="CAPPROVE",
                                      clock=lambda: 2_000_000_000)
        result = supervisor.poll({"mission_id": "CMQ-X", "dispatch": {"cursor_agent_id": "bc-one"}})
        self.assertTrue(result["stalled"])

    def test_cancel_is_explicitly_governed_and_secret_not_serialized(self):
        with self.assertRaisesRegex(HermesBridgeError, "governed_cancel_required"):
            self.cursor.cancel_run("bc-one", "run-one")
        self.cursor.cancel_run("bc-one", "run-one", governed=True)
        self.assertNotIn("secret", json.dumps(self.client.calls))

    def test_canonical_candidate_binding_is_exact_and_bounded(self):
        binding = {"pr_number": 1313, "branch_name": "cursor/hermes", "base_sha": "a" * 40,
            "head_sha": "b" * 40, "candidate_diff_sha256": "c" * 64,
            "changed_files": ["a.py"], "generation": "g1", "allowed_files": ["a.py"],
            "forbidden_files": [".env"], "allowed_effects": ["repository_source"],
            "forbidden_effects": ["merge", "deploy"], "required_tests": ["unit"],
            "operational_acceptance": ["terminal-independent pilot"]}
        connection = FakeConnection([("approved", {"mission_family": {"root_mission_id": "CMQ-ROOT"}})])
        result, status = bind_external_supervisor_candidate("CMQ-X", binding,
            authenticated_principal="owner:charl", database_url="postgres://unit-test",
            connect_factory=lambda _: connection)
        self.assertEqual(201, status)
        self.assertEqual("external_candidate_bound", result["status"])
        written = [params for sql, params in connection.cursor_instance.executed
                   if "update public.charlie_missions set metadata_json" in sql][0]
        metadata = json.loads(written["metadata"])
        self.assertEqual(1313, metadata["review_packet"]["pr_number"])
        self.assertEqual("g1", metadata["mission_admission_contract"]["generation"])
        with self.assertRaises(KeyError):
            _ = metadata["database_url"]

        invalid = {**binding, "allowed_files": ["other.py"]}
        result, status = bind_external_supervisor_candidate("CMQ-X", invalid,
            authenticated_principal="owner:charl", database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection())
        self.assertEqual(400, status)
        self.assertEqual("external_candidate_binding_invalid", result["status"])

    def test_changed_head_invalidates_then_rebinds_same_mission_branch(self):
        old_head, new_head = "b" * 40, "d" * 40
        authorization = {"status": "valid", "base_sha": "a" * 40,
            "branch": "cursor/cmq-x-g1", "generation": "g1", "allowed_files": ["a.py"],
            "allowed_effects": ["source_edit"], "forbidden_effects": ["merge", "deploy"]}
        state = {"mission_admission": {"status": "valid", "head_sha": old_head,
                "receipt_id": "MAR-" + "A" * 64},
            "review_packet": {"pr_number": 1, "branch_name": "cursor/cmq-x-g1",
                "candidate_revision": old_head, "candidate_diff_sha256": "c" * 64,
                "changed_files": ["a.py"]},
            "mission_admission_contract": {"generation": "g1", "branch": "cursor/cmq-x-g1",
                "base_sha": "a" * 40, "allowed_files": ["a.py"]},
            "dispatch_authorization": authorization}
        class Cursor:
            def __init__(self): self.sql = ""
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, sql, params=None):
                self.sql = sql.lower(); params = params or {}
                if "update public.charlie_missions" in self.sql and params.get("metadata"):
                    state.clear(); state.update(json.loads(params["metadata"]))
            def fetchone(self):
                if "select status," in self.sql: return ("in_progress", dict(state))
                if "select coalesce(metadata_json" in self.sql: return (dict(state),)
                return ("inserted",)
        class Connection:
            def __init__(self): self.cursor_value = Cursor()
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def cursor(self): return self.cursor_value
        factory = lambda _: Connection()
        invalidated, status = invalidate_external_candidate_admission("CMQ-X", old_head, new_head,
            authenticated_principal="control_tower_isolated_validator_v2",
            database_url="postgres://unit-test", connect_factory=factory)
        self.assertEqual(201, status, invalidated)
        binding = {"pr_number": 1, "branch_name": "cursor/cmq-x-g1", "base_sha": "a" * 40,
            "head_sha": new_head, "candidate_diff_sha256": "e" * 64, "changed_files": ["a.py"],
            "generation": "g1", "allowed_files": ["a.py"], "forbidden_files": ["*"],
            "allowed_effects": ["source_edit"], "forbidden_effects": ["merge", "deploy"],
            "required_tests": ["mission-admission"], "operational_acceptance": ["stop before merge"]}
        rebound, rebound_status = bind_external_supervisor_candidate("CMQ-X", binding,
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit-test",
            connect_factory=factory)
        self.assertEqual(201, rebound_status, rebound)
        self.assertEqual(new_head, state["review_packet"]["candidate_revision"])

    def test_protected_admission_callback_is_signed_exact_and_replay_safe(self):
        from modules.charlie import routes
        app = Flask(__name__); app.register_blueprint(routes.charlie_bp)
        mission_id, base, head = "CMQ-X", "a" * 40, "b" * 40
        receipt = {"receipt_id": "MAR-" + "A" * 64, "content_sha256": "c" * 64,
            "authority_key_sha256": "d" * 64,
            "mission": {"mission_id": mission_id, "root_mission_id": "CMQ-ROOT", "generation": "g1"},
            "repository": {"base_sha": base},
            "candidate": {"head_sha": head, "branch": "cursor/cmq-x-g1",
                "diff_sha256": "e" * 64, "changed_files": ["a.py"]},
            "owner_instruction_chain": {"latest_correction_digest": "f" * 64},
            "collision_snapshot": {"snapshot_sha256": "1" * 64},
            "scope": {"allowed_files": ["a.py"], "forbidden_files": ["*"],
                "allowed_effects": ["source_edit"], "forbidden_effects": ["merge", "deploy"]},
            "required_tests": ["mission-admission"],
            "operational_acceptance": {"requirements": ["stop before merge"]}}
        identity = {"mission_id": mission_id, "root_mission_id": "CMQ-ROOT", "generation": "g1",
            "base_sha": base, "head_sha": head, "changed_files": ["a.py"],
            "allowed_files": ["a.py"], "forbidden_files": ["*"],
            "allowed_effects": ["source_edit"], "forbidden_effects": ["merge", "deploy"]}
        metadata = {"review_packet": {"pr_number": 9, "candidate_revision": head,
                "candidate_diff_sha256": "e" * 64, "changed_files": ["a.py"]},
            "mission_admission_contract": {"base_sha": base, "branch": "cursor/cmq-x-g1",
                "allowed_files": ["a.py"]}, "mission_family": {"generation": "g1"}}
        authority = {"latest_correction_digest": "f" * 64, "collision_snapshot_sha256": "1" * 64}
        body = {"envelope": {"receipt": receipt}, "pr_number": 9}
        with patch("scripts.charlie_mission_admission_guard._validate_external_receipt_envelope",
                   return_value=(receipt, identity)), \
             patch.object(routes, "get_mission", return_value=({"mission": {"metadata": metadata}}, 200)), \
             patch.object(routes, "read_current_mission_admission_authority", return_value=(authority, 200)), \
             patch.object(routes, "append_mission_admission_event",
                          side_effect=[({"success": True, "status": "mission_admission_recorded"}, 201),
                                       ({"success": True, "status": "exact_replay"}, 200)]) as writer:
            first = app.test_client().post(f"/charlie/hermes/missions/{mission_id}/protected-admission", json=body)
            second = app.test_client().post(f"/charlie/hermes/missions/{mission_id}/protected-admission", json=body)
        self.assertEqual(201, first.status_code)
        self.assertEqual(200, second.status_code)
        self.assertEqual(2, writer.call_count)
        with patch("scripts.charlie_mission_admission_guard._validate_external_receipt_envelope",
                   side_effect=ValueError("external_admission_signature_invalid")), \
             patch.object(routes, "append_mission_admission_event") as rejected_writer:
            rejected = app.test_client().post(f"/charlie/hermes/missions/{mission_id}/protected-admission", json=body)
        self.assertEqual(409, rejected.status_code)
        rejected_writer.assert_not_called()
        with patch("scripts.charlie_mission_admission_guard._validate_external_receipt_envelope",
                   return_value=(receipt, {**identity, "head_sha": "9" * 40})), \
             patch.object(routes, "get_mission", return_value=({"mission": {"metadata": metadata}}, 200)), \
             patch.object(routes, "read_current_mission_admission_authority", return_value=(authority, 200)), \
             patch.object(routes, "append_mission_admission_event") as mismatch_writer:
            mismatch = app.test_client().post(f"/charlie/hermes/missions/{mission_id}/protected-admission", json=body)
        self.assertEqual(409, mismatch.status_code)
        mismatch_writer.assert_not_called()

    def test_owner_notification_requires_current_approved_head_and_all_checks(self):
        class Monitor:
            def pull_state(self, number, now=None):
                return {"pr_number": number, "head_sha": "d" * 40, "branch": "cursor/cmq-x-g1",
                    "checks": {}, "all_required_checks_pass": True, "approved_head_sha": "d" * 40,
                    "ci_stalled": False, "independent_review": "APPROVE"}
        class Bot:
            def __init__(self): self.posts = []
            def post(self, channel, message, **kwargs): self.posts.append((channel, message)); return {"ok": True}
        bot = Bot(); self.client.run_branches = []
        supervisor = HermesSupervisor(self.canonical, self.cursor, owner_slack_user_id="UOWNER",
            slack_command_channel_id="C1", slack_build_channel_id="CBUILD",
            slack_approval_channel_id="CAPPROVE", github=Monitor(), slack_bot=bot, clock=lambda: 0)
        result = supervisor.supervise_once({"mission_id": "CMQ-X", "dispatch": {
            "cursor_agent_id": "bc-one", "pr_number": 9, "admission_requested_head": "d" * 40}})
        self.assertEqual("d" * 40, result["owner_notification_head"])
        self.assertEqual("CAPPROVE", bot.posts[0][0])
        self.assertIn("No merge or deployment", bot.posts[0][1])

    def test_end_to_end_pda_candidate_send_back_fresh_mar_and_owner_notification(self):
        class Monitor:
            head = "d" * 40
            verdict = "SEND_BACK"
            def find_pull(self, branch): return 9
            def pull_state(self, number, now=None):
                approved = self.verdict == "APPROVE"
                return {"pr_number": number, "head_sha": self.head,
                    "branch": "cursor/generated", "checks": {},
                    "all_required_checks_pass": approved,
                    "approved_head_sha": self.head if approved else "",
                    "ci_stalled": False, "independent_review": self.verdict}
        class Bot:
            def __init__(self): self.posts = []
            def post(self, channel, message, **kwargs):
                self.posts.append((channel, message, kwargs)); return {"ok": True}
        monitor, bot = Monitor(), Bot()
        supervisor = HermesSupervisor(self.canonical, self.cursor,
            owner_slack_user_id="UOWNER", slack_signing_secret="s",
            slack_command_channel_id="C1", slack_build_channel_id="CBUILD",
            slack_approval_channel_id="CAPPROVE", github=monitor,
            slack_bot=bot, clock=lambda: 0)
        event = {"event_id": "Ev-lifecycle", "user": "UOWNER", "channel": "C1",
                 "ts": "1.0", "text": "Bounded documentation pilot"}
        mission = supervisor.reconcile_slack_event(event)
        self.canonical.prepare_dispatch_authorization(mission["mission_id"])
        dispatch = supervisor.dispatch_cursor(mission)
        agent_id = dispatch["cursor_agent_id"]
        self.client.run_branches = [{"name": "cursor/generated"}]
        sent_back = supervisor.supervise_once({"mission_id": mission["mission_id"],
            "dispatch": {**dispatch, "pr_number": 9}})
        self.assertEqual(agent_id, sent_back["agent_id"])
        self.assertEqual((mission["mission_id"], "d" * 40, 9), self.canonical.admission_requests[-1])
        monitor.head, monitor.verdict = "e" * 40, "APPROVE"
        completed = supervisor.supervise_once({"mission_id": mission["mission_id"],
            "dispatch": {**dispatch, "pr_number": 9,
                         "admission_requested_head": "d" * 40}})
        self.assertEqual((mission["mission_id"], "e" * 40, 9), self.canonical.admission_requests[-1])
        self.assertEqual("e" * 40, completed["owner_notification_head"])
        self.assertEqual("CAPPROVE", bot.posts[-1][0])
        self.assertIn("No merge or deployment", bot.posts[-1][1])


    def test_attempt_two_has_distinct_deterministic_agent_and_governed_archive(self):
        original = self.cursor.deterministic_agent_id("CMQ-X:g1")
        successor = self.cursor.deterministic_agent_id("CMQ-X:g1:attempt-2")
        self.assertNotEqual(original, successor)
        self.cursor.create_agent(admission(), "bounded", execution_attempt=2)
        create = [call[2] for call in self.client.calls if call[:2] == ("POST", "/v1/agents")][-1]
        self.assertEqual(successor, create["agentId"])
        with self.assertRaisesRegex(HermesBridgeError, "governed_archive_required"):
            self.cursor.archive_agent("bc-old")
        self.cursor.archive_agent("bc-old", governed=True)

    def test_attempt_three_has_distinct_identity_and_current_main_start(self):
        third = self.cursor.deterministic_agent_id("CMQ-X:g1:attempt-3")
        self.cursor.create_agent(admission(), "bounded", execution_attempt=3)
        create = [call[2] for call in self.client.calls if call[:2] == ("POST", "/v1/agents")][-1]
        self.assertEqual(third, create["agentId"])
        self.assertEqual("a" * 40, create["repos"][0]["startingRef"])
        self.assertIs(create["autoCreatePR"], True)
        self.assertIs(create["workOnCurrentBranch"], False)

    def test_archived_zero_candidate_predecessor_permits_one_succession(self):
        problem = "Documentation pilot"
        metadata = {"mission_vault": {"problem_statement": problem},
            "external_supervisor_state": {"generation": "g1", "cursor_agent_id": "bc-old",
                "cursor_run_id": "run-old", "agent_state": "ARCHIVED", "event": "predecessor_archived",
                "repository_mutation": False, "slack_event_id": "Ev1", "slack_thread_ts": "1.0"},
            "dispatch_authorization": {"status": "valid", "generation": "g1",
                "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
                "owner_instruction_digest": hashlib.sha256(problem.encode()).hexdigest(),
                "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"]}}
        connection = FakeConnection([(metadata,)])
        result, status = prepare_external_execution_succession(
            "CMQ-X", generation="g1", predecessor_agent_id="bc-old", predecessor_run_id="run-old",
            predecessor_state="IDLE",
            replacement_reason="workspace_refresh_unsupported_after_hook_repair",
            observed_main_sha="a" * 40, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit-test", connect_factory=lambda _: connection)
        self.assertEqual(201, status, result)
        self.assertEqual(2, result["succession"]["active_attempt"])
        stored = json.loads([params for sql, params in connection.cursor_instance.executed
            if "update public.charlie_missions" in sql][0]["metadata"])
        self.assertEqual("ARCHIVED", stored["external_supervisor_state"]["agent_state"])
        for field, value in (("agent_state", "IDLE"), ("repository_mutation", True)):
            blocked = json.loads(json.dumps(metadata))
            blocked["external_supervisor_state"][field] = value
            rejected, rejected_status = prepare_external_execution_succession(
                "CMQ-X", generation="g1", predecessor_agent_id="bc-old", predecessor_run_id="run-old",
                predecessor_state="IDLE", replacement_reason="workspace_refresh_unsupported_after_hook_repair",
                observed_main_sha="a" * 40, authenticated_principal="hermes:charlie-builder",
                database_url="postgres://unit-test", connect_factory=lambda _, row=blocked: FakeConnection([(row,)]))
            self.assertEqual(409, rejected_status, (field, rejected))
        stale = json.loads(json.dumps(metadata))
        stale["dispatch_authorization"]["base_sha"] = "b" * 40
        rejected, rejected_status = prepare_external_execution_succession(
            "CMQ-X", generation="g1", predecessor_agent_id="bc-old", predecessor_run_id="run-old",
            predecessor_state="IDLE", replacement_reason="workspace_refresh_unsupported_after_hook_repair",
            observed_main_sha="a" * 40, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit-test", connect_factory=lambda _: FakeConnection([(stale,)]))
        self.assertEqual(409, rejected_status, rejected)

    def test_archived_attempt_two_permits_only_bounded_attempt_three(self):
        problem = "Documentation pilot"
        metadata = {"mission_vault": {"problem_statement": problem},
            "external_supervisor_state": {"generation": "g1", "cursor_agent_id": "bc-two",
                "cursor_run_id": "run-two", "agent_state": "ARCHIVED", "event": "predecessor_archived",
                "repository_mutation": False},
            "dispatch_authorization": {"status": "valid", "generation": "g1",
                "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
                "owner_instruction_digest": hashlib.sha256(problem.encode()).hexdigest(),
                "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"]},
            "execution_succession": {"active_attempt": 2, "predecessor_archived": True,
                "predecessor_agent_id": "bc-one", "successor_agent_id": "bc-two"}}
        result, status = prepare_external_execution_succession(
            "CMQ-X", generation="g1", predecessor_agent_id="bc-two", predecessor_run_id="run-two",
            predecessor_state="IDLE", replacement_reason="cursor_workspace_authorization_state_machine_repaired",
            observed_main_sha="a" * 40, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit", connect_factory=lambda _: FakeConnection([(metadata,)]))
        self.assertEqual(201, status, result)
        self.assertEqual(3, result["succession"]["active_attempt"])
        self.assertEqual(4, result["succession"]["maximum_attempts"])

    def test_archived_attempt_three_permits_only_cloud_socket_recovery_attempt_four(self):
        problem = "Documentation pilot"
        metadata = {"mission_vault": {"problem_statement": problem},
            "external_supervisor_state": {"generation": "g1", "cursor_agent_id": "bc-three",
                "cursor_run_id": "run-three", "agent_state": "ARCHIVED", "event": "predecessor_archived",
                "repository_mutation": False},
            "dispatch_authorization": {"status": "valid", "generation": "g1",
                "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
                "owner_instruction_digest": hashlib.sha256(problem.encode()).hexdigest(),
                "allowed_files": ["docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"]},
            "execution_succession": {"active_attempt": 3, "predecessor_archived": True,
                "predecessor_agent_id": "bc-two", "successor_agent_id": "bc-three"}}
        result, status = prepare_external_execution_succession(
            "CMQ-X", generation="g1", predecessor_agent_id="bc-three", predecessor_run_id="run-three",
            predecessor_state="IDLE", replacement_reason="cursor_cloud_socket_detection_repaired",
            observed_main_sha="a" * 40, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit", connect_factory=lambda _: FakeConnection([(metadata,)]))
        self.assertEqual(201, status, result)
        self.assertEqual(4, result["succession"]["active_attempt"])
        self.assertEqual(4, result["succession"]["maximum_attempts"])

    def test_archived_predecessor_cannot_reactivate_via_partial_progress(self):
        metadata = {"external_supervisor_state": {"generation": "g1", "cursor_agent_id": "bc-old",
            "cursor_run_id": "run-old", "agent_state": "ARCHIVED", "execution_attempt": 1},
            "execution_succession": {"active_attempt": 2, "predecessor_agent_id": "bc-old",
                "predecessor_archived": True, "successor_agent_id": ""}}
        result, status = record_external_supervisor_state("CMQ-X", {"agent_state": "ACTIVE"},
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([(metadata,)]))
        self.assertEqual(409, status, result)
        self.assertEqual("predecessor_reactivation_forbidden", result["status"])


if __name__ == "__main__": unittest.main()
