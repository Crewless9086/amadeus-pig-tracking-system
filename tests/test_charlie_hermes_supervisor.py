import hashlib
import hmac
import json
import unittest

from modules.charlie.hermes_supervisor import (
    CursorCloudV1, GitHubReadMonitor, HermesBridgeError, HermesSupervisor, SlackBot,
    verify_slack_request,
)
from modules.charlie.mission_store import bind_external_supervisor_candidate
from tests.test_charlie_mission_store import FakeConnection


def admission():
    return {"mission_id": "CMQ-X", "generation": "g1", "receipt_id": "MAR-" + "A" * 64,
            "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
            "allowed_files": ["modules/charlie/example.py"], "allowed_effects": ["repository_source"],
            "owner_instruction_digest": "b" * 64, "acceptance_requirements": ["tests pass"]}


class FakeClient:
    def __init__(self): self.calls = []; self.agent_state = "IDLE"; self.conflict_once = False
    def request(self, method, path, payload=None, headers=None, query=None):
        self.calls.append((method, path, payload, query))
        if path == "/v1/agents":
            if self.conflict_once:
                self.conflict_once = False
                return {"error": "conflict", "status_code": 409}
            return {"agent": {"id": "bc-one"}, "run": {"id": "run-one"}}
        if path.endswith("/runs") and method == "POST": return {"run": {"id": "run-two"}}
        if path.endswith("/runs/run-one"): return {"id": "run-one", "status": "SUCCEEDED", "updatedAt": "2026-08-28T00:00:00Z"}
        if path.startswith("/v1/agents/bc-") and "/runs/" not in path:
            return {"id": path.rsplit("/", 1)[-1], "status": self.agent_state, "latestRunId": "run-one"}
        return {"items": []}


class Canonical:
    def __init__(self): self.dispatch = {}; self.reconciled = 0; self.running = 0; self.intake = {}
    def reconcile_mission(self, payload, idempotency_key):
        if idempotency_key not in self.intake:
            self.reconciled += 1; self.intake[idempotency_key] = {"mission_id": "CMQ-X", "key": idempotency_key}
        return self.intake[idempotency_key]
    def get_dispatch(self, key): return self.dispatch.get(key)
    def running_writer_count(self): return self.running
    def record_dispatch(self, key, value): self.dispatch[key] = value; return value
    def record_progress(self, mission_id, value): return value
    def record_followup(self, mission_id, agent_id, run_id): return {"agent_id": agent_id, "run_id": run_id}


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
        with self.assertRaisesRegex(HermesBridgeError, "valid_mission_admission_required"):
            self.supervisor.dispatch_cursor({"admission": {}})
        mission = {"admission": admission(), "instruction": "Bounded work"}
        one = self.supervisor.dispatch_cursor(mission); two = self.supervisor.dispatch_cursor(mission)
        self.assertEqual(one["cursor_agent_id"], two["cursor_agent_id"])
        self.assertEqual(1, len([call for call in self.client.calls if call[0:2] == ("POST", "/v1/agents")]))

    def test_restart_duplicate_and_writer_capacity(self):
        mission = {"admission": admission(), "instruction": "Bounded work"}
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
        result = self.supervisor.dispatch_cursor({"admission": admission(), "instruction": "Bounded work"})
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


if __name__ == "__main__": unittest.main()
