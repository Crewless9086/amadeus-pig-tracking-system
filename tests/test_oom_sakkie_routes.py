import unittest
from unittest.mock import patch

from app import app
from modules.oom_sakkie.access import is_review_request_allowed


class OomSakkieRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "not_configured"})
    def test_message_route_returns_shape_without_database(self, _write_trace):
        response = self.client.post("/api/oom-sakkie/message", json={
            "text": "what is the power doing now",
            "channel": "kiosk",
            "session_id": "route-test-session",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["tool_used"], "power_current")
        self.assertEqual(data["risk_level"], 0)
        self.assertFalse(data["needs_clarification"])
        self.assertIn("answer", data)
        self.assertIn("trace_id", data)
        self.assertIn("links", data)
        self.assertIn("stale_warnings", data)
        self.assertIn("safety_notes", data)
        self.assertEqual(data["trace_store"]["status"], "not_configured")

    def test_policy_route_returns_local_read_only_shape(self):
        response = self.client.get("/api/oom-sakkie/policy")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "local_kiosk_read_only")
        self.assertEqual(data["kiosk_policy"]["max_risk_level"], 0)
        self.assertEqual(data["continue_conversation_max_turns"], 5)
        self.assertEqual(data["voice_auto_send_ms"], 2000)

    def test_review_packet_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/review-packet",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "review_access_denied")

    def test_specialists_route_is_planned_only(self):
        response = self.client.get("/api/oom-sakkie/specialists")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "planned_only")
        self.assertFalse(data["delegation_enabled"])
        self.assertFalse(data["autonomous_loops_enabled"])
        self.assertGreaterEqual(len(data["specialists"]), 8)

    def test_specialists_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/specialists",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.get_review_advisor")
    def test_review_advisor_route_is_advisory_only(self, mock_advisor):
        mock_advisor.return_value = ({
            "success": True,
            "mode": "advisory_only",
            "autonomous_marking_enabled": False,
            "writes_feedback": False,
            "review_queue": [],
            "suggested_actions": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/review-advisor?channel=kiosk&days=14")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "advisory_only")
        self.assertFalse(data["autonomous_marking_enabled"])
        self.assertFalse(data["writes_feedback"])

    def test_review_advisor_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/review-advisor",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_message_route_remains_available_for_non_local_access_policy(self):
        response = self.client.post(
            "/api/oom-sakkie/message",
            json={"text": "what is the power doing now", "channel": "kiosk"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

        self.assertNotEqual(response.status_code, 403)

    def test_review_access_policy_is_loopback_by_default(self):
        self.assertTrue(is_review_request_allowed("127.0.0.1"))
        self.assertTrue(is_review_request_allowed("::1"))
        self.assertFalse(is_review_request_allowed("192.168.1.44", environ={}))
        self.assertTrue(is_review_request_allowed(
            "192.168.1.44",
            environ={"OOM_SAKKIE_REVIEW_ALLOW_PRIVATE_LAN": "true"},
        ))


if __name__ == "__main__":
    unittest.main()
