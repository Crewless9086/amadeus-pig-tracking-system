"""Exercise real session guards and API dispatch without network or hardware."""
import os
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch
from flask import Flask
from modules.auth.owner_access import configure_owner_access, set_owner_session
from modules.telemetry.rootline_owner_control_routes import rootline_owner_controls_bp

URL = "/api/telemetry/rootline/owner-controls"


class OwnerControlsRoutesTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "OWNER_ACCESS_ENABLED": "0", "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
            "OWNER_ADMIN_TOKEN": "a" * 40, "OWNER_READ_TOKEN": "r" * 40,
            "OWNER_SESSION_SECRET": "isolated-route-test-secret",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.service = ModuleType("modules.telemetry.rootline_owner_controls")
        self.service.get_owner_controls = Mock(return_value=({"success": True}, 200))
        self.service.preview_owner_control = Mock(return_value=({"success": True}, 200))
        self.service.apply_owner_control = Mock(return_value=({"success": True}, 202))
        self.modules = patch.dict(sys.modules, {self.service.__name__: self.service})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.app = Flask(__name__)
        configure_owner_access(self.app)
        self.app.register_blueprint(rootline_owner_controls_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def login(self, role="admin"):
        with self.app.test_request_context():
            set_owner_session(role)
            from flask import session
            values = dict(session)
        with self.client.session_transaction() as sess:
            sess.update(values)
        return self.client.get(URL).get_json()["csrf_token"]

    def test_disabled_global_auth_does_not_open_new_routes(self):
        self.assertEqual(self.client.get(URL).status_code, 403)
        for action in ("preview", "apply"):
            self.assertEqual(self.client.post(URL + "/" + action, json={}).status_code, 403)
        self.service.get_owner_controls.assert_not_called()
        self.service.apply_owner_control.assert_not_called()

    def test_reader_cannot_preview_or_apply(self):
        token = self.login("read")
        self.assertEqual(token, "")
        for action in ("preview", "apply"):
            self.assertEqual(self.client.post(URL + "/" + action, json={}).status_code, 403)

    def test_admin_response_is_not_cacheable_and_has_bound_token(self):
        token = self.login()
        response = self.client.get(URL + "?panel=forecast")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertTrue(response.json["owner_can_administer"])
        self.assertEqual(response.json["csrf_token"], token)
        self.service.get_owner_controls.assert_called_with(panel="forecast")
        self.assertEqual(self.client.get(URL + "?panel=bogus").status_code, 400)

    def test_mutation_requires_matching_csrf_and_json_object(self):
        token = self.login()
        for action in ("preview", "apply"):
            url = URL + "/" + action
            for value in ("", "wrong", "non-ascii-\u2603"):
                self.assertEqual(self.client.post(url, json={}, headers={"X-ROOTLINE-CSRF": value}).status_code, 403)
            self.assertEqual(self.client.post(url, data="{}", headers={"X-ROOTLINE-CSRF": token}).status_code, 415)
            self.assertEqual(self.client.post(url, json=[], headers={"X-ROOTLINE-CSRF": token}).status_code, 400)
        self.service.apply_owner_control.assert_not_called()

    def test_cross_origin_rejected_even_with_token(self):
        token = self.login()
        for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"},
                        {"Origin": "http://["}, {"Sec-Fetch-Site": "cross-site"}):
            headers["X-ROOTLINE-CSRF"] = token
            self.assertEqual(self.client.post(URL + "/apply", json={}, headers=headers).status_code, 403)
        self.service.apply_owner_control.assert_not_called()

    def test_server_identity_and_service_status_preserved(self):
        token = self.login()
        payload = {"actor_identity": "spoofed", "request_id": "example"}
        response = self.client.post(URL + "/apply", json=payload,
            headers={"X-ROOTLINE-CSRF": token, "Origin": "http://localhost"})
        self.assertEqual(response.status_code, 202)
        actual_payload, actor = self.service.apply_owner_control.call_args.args
        self.assertEqual(actual_payload, payload)
        self.assertTrue(actor.startswith("owner-admin:"))
        self.assertNotEqual(actor, "spoofed")

    def test_https_origin_allowed_behind_tls_proxy(self):
        token = self.login()
        response = self.client.post(URL + "/apply", json={},
            headers={"X-ROOTLINE-CSRF": token, "Origin": "https://localhost"})
        self.assertEqual(response.status_code, 202)

    def test_cleared_session_invalidates_old_token(self):
        token = self.login()
        with self.client.session_transaction() as sess:
            sess.clear()
        self.assertEqual(self.client.post(URL + "/apply", json={},
            headers={"X-ROOTLINE-CSRF": token}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
