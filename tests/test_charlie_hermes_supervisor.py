import hashlib
import hmac
import json
import unittest

from modules.charlie.hermes_supervisor import (
    CursorCloudV1, HermesBridgeError, HermesSupervisor, verify_slack_request,
)


def admission():
    return {"mission_id": "CMQ-X", "generation": "g1", "receipt_id": "MAR-" + "A" * 64,
            "repository": "Crewless9086/amadeus-pig-tracking-system", "base_sha": "a" * 40,
            "allowed_files": ["modules/charlie/example.py"], "allowed_effects": ["repository_source"],
            "owner_instruction_digest": "b" * 64, "acceptance_requirements": ["tests pass"]}


class FakeClient:
    def __init__(self): self.calls = []; self.agent_state = "IDLE"
    def request(self, method, path, payload=None, headers=None, query=None):
        self.calls.append((method, path, payload, query))
        if path == "/v1/agents":
            return {"agent": {"id": "bc-one"}, "run": {"id": "run-one"}}
        if path.endswith("/runs") and method == "POST": return {"run": {"id": "run-two"}}
        if path.endswith("/runs/run-one"): return {"id": "run-one", "status": "SUCCEEDED", "updatedAt": "2026-08-28T00:00:00Z"}
        if path == "/v1/agents/bc-one": return {"id": "bc-one", "status": self.agent_state, "latestRunId": "run-one"}
        return {"items": []}


class Canonical:
    def __init__(self): self.dispatch = {}; self.reconciled = 0; self.running = 0
    def reconcile_mission(self, payload, idempotency_key): self.reconciled += 1; return {"mission_id": "CMQ-X", "key": idempotency_key}
    def get_dispatch(self, key): return self.dispatch.get(key)
    def running_writer_count(self): return self.running
    def record_dispatch(self, key, value): self.dispatch[key] = value; return value
    def record_progress(self, mission_id, value): return value
    def record_followup(self, mission_id, agent_id, run_id): return {"agent_id": agent_id, "run_id": run_id}


class HermesSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient(); self.cursor = CursorCloudV1("secret", client=self.client)
        self.canonical = Canonical(); self.supervisor = HermesSupervisor(self.canonical, self.cursor, owner_slack_user_id="UOWNER", clock=lambda: 0)

    def test_slack_signature_owner_and_duplicate_identity(self):
        body = b'{"ok":true}'; sig = "v0=" + hmac.new(b"s", b"v0:100:" + body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_slack_request("s", 100, body, sig, now=100))
        event = {"event_id": "Ev1", "user": "UOWNER", "channel": "C1", "ts": "1.0", "text": "Build it"}
        first = self.supervisor.reconcile_slack_event(event); second = self.supervisor.reconcile_slack_event(event)
        self.assertEqual(first["key"], second["key"])
        with self.assertRaisesRegex(HermesBridgeError, "slack_owner_not_authorized"):
            self.supervisor.reconcile_slack_event({**event, "user": "UOTHER"})

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
        restarted = HermesSupervisor(self.canonical, self.cursor, owner_slack_user_id="UOWNER")
        self.assertEqual("existing_dispatch", restarted.dispatch_cursor(mission)["status"])
        self.canonical.dispatch = {}; self.canonical.running = 1
        with self.assertRaisesRegex(HermesBridgeError, "writer_capacity_reached"):
            restarted.dispatch_cursor(mission)

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
        self.assertEqual("owner-approvals", packet["channel"])

    def test_candidate_change_invalidates_approval(self):
        with self.assertRaisesRegex(HermesBridgeError, "owner_decision_not_ready"):
            self.supervisor.prepare_owner_decision({"mission_id": "M", "pr_number": 1,
                "head_sha": "b" * 40, "approved_head_sha": "a" * 40,
                "all_required_checks_pass": True, "independent_review": "APPROVE"})

    def test_stalled_cursor_run_is_escalated_without_llm(self):
        self.client.agent_state = "ACTIVE"
        supervisor = HermesSupervisor(self.canonical, self.cursor,
                                      owner_slack_user_id="UOWNER", clock=lambda: 2_000_000_000)
        result = supervisor.poll({"mission_id": "CMQ-X", "dispatch": {"cursor_agent_id": "bc-one"}})
        self.assertTrue(result["stalled"])

    def test_cancel_is_explicitly_governed_and_secret_not_serialized(self):
        with self.assertRaisesRegex(HermesBridgeError, "governed_cancel_required"):
            self.cursor.cancel_run("bc-one", "run-one")
        self.cursor.cancel_run("bc-one", "run-one", governed=True)
        self.assertNotIn("secret", json.dumps(self.client.calls))


if __name__ == "__main__": unittest.main()
