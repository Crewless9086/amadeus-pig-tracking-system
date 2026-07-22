import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.auth.owner_access import (
    configure_owner_access,
    owner_access_enabled,
    owner_local_dev_allowed,
)
from modules.pig_weights import pig_weights_routes
from modules.sales import sales_transaction_routes


READ_TOKEN = "read-owner-token-1234567890abcdef"
ADMIN_TOKEN = "admin-owner-token-1234567890abcdef"
SESSION_SECRET = "owner-session-secret-1234567890abcdef"


def owner_env(**overrides):
    env = {
        "OWNER_ACCESS_ENABLED": "1",
        "OWNER_ACCESS_ALLOW_LOCAL_DEV": "1",
        "OWNER_READ_TOKEN": READ_TOKEN,
        "OWNER_ADMIN_TOKEN": ADMIN_TOKEN,
        "OWNER_SESSION_SECRET": SESSION_SECRET,
    }
    env.update(overrides)
    return env


class OwnerAccessTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        app.config.update(SERVER_NAME=None)
        self.client = app.test_client()

    def _configure(self):
        configure_owner_access(app)

    def _login(self, token=READ_TOKEN, remote_addr="203.0.113.10"):
        return self.client.post(
            "/owner/login",
            data={"owner_token": token, "next": "/sales/meat-leads"},
            environ_base={"REMOTE_ADDR": remote_addr},
        )

    def test_owner_access_disabled_does_not_allow_remote_protected_flow(self):
        with patch.dict(os.environ, {"OWNER_ACCESS_ENABLED": "0", "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0"}, clear=False):
            self._configure()
            self.assertFalse(owner_access_enabled())
            response = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "owner_access_not_configured")

    def test_owner_access_disabled_allows_only_explicit_loopback_development(self):
        with patch.dict(os.environ, {"OWNER_ACCESS_ENABLED": "0", "OWNER_ACCESS_ALLOW_LOCAL_DEV": "1"}, clear=False):
            self._configure()
            response = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "127.0.0.1"})
        self.assertEqual(response.status_code, 200)

    def test_remote_protected_page_redirects_without_session_when_enabled(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/owner/login", response.headers.get("Location", ""))

    def test_remote_charlie_page_redirects_without_session_when_enabled(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self.client.get("/charlie", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/owner/login", response.headers.get("Location", ""))

    def test_local_loopback_page_allowed_when_local_dev_enabled(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "127.0.0.1"})
            self.assertTrue(owner_local_dev_allowed())
        self.assertEqual(response.status_code, 200)

    def test_valid_owner_read_token_login_creates_read_session(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self._login(READ_TOKEN)
            status = self.client.get("/owner/status", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(status.status_code, 200)
        self.assertIn(b"Logged in:</strong> yes", status.data)
        self.assertIn(b"Session level:</strong> read", status.data)

    def test_valid_owner_admin_token_login_creates_admin_session(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self._login(ADMIN_TOKEN)
            status = self.client.get("/owner/status", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(status.status_code, 200)
        self.assertIn(b"Logged in:</strong> yes", status.data)
        self.assertIn(b"Session level:</strong> admin", status.data)

    def test_authenticated_capture_derives_stable_non_secret_author(self):
        payload = {
            "pig_id": "P-1", "observed_at": "2026-07-22T10:00:00+02:00",
            "category": "welfare", "severity": "medium", "confidence": 0.9,
            "note": "Limp observed.", "idempotency_key": "obs-owner-author-1",
            "author_reference": "client-controlled-author",
        }
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(ADMIN_TOKEN)
            with patch.object(pig_weights_routes, "record_observation", return_value=({"success": True}, 201)) as capture:
                response = self.client.post(
                    "/api/pig-weights/observations",
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(response.status_code, 201)
        persisted_author = capture.call_args.args[1]
        self.assertTrue(persisted_author.startswith("owner-admin-"))
        self.assertNotEqual(persisted_author, payload["author_reference"])
        self.assertNotIn(ADMIN_TOKEN, persisted_author)

    def test_invalid_token_denied(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self._login("wrong-token")
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"not accepted", response.data)

    def test_logout_clears_session(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            logout = self.client.post("/owner/logout", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            status = self.client.get("/owner/status", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(logout.status_code, 302)
        self.assertEqual(logout.headers.get("Location"), "/")
        self.assertIn(b"Logged in:</strong> no", status.data)
        self.assertIn("session=", logout.headers.get("Set-Cookie", ""))

    def test_owner_status_includes_logout_form_when_logged_in(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            status = self.client.get("/owner/status", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(status.status_code, 200)
        html = status.data.decode("utf-8")
        self.assertIn('method="post" action="/owner/logout"', html)
        self.assertIn("Log out", html)

    def test_login_page_includes_logout_form_when_already_logged_in(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            login = self.client.get("/owner/login", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(login.status_code, 200)
        self.assertIn(b"Owner access is active for this browser.", login.data)
        self.assertIn(b'action="/owner/logout"', login.data)

    def test_logout_blocks_sales_page_and_command_state_again(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            logout = self.client.post("/owner/logout", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            page = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            command_state = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/command-state",
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(logout.headers.get("Location"), "/")
        self.assertEqual(page.status_code, 302)
        self.assertIn("/owner/login", page.headers.get("Location", ""))
        self.assertEqual(command_state.status_code, 403)
        self.assertEqual(command_state.get_json()["status"], "sam_command_state_access_denied")

    def test_session_cookie_flags_are_http_only_and_lax(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self._login(READ_TOKEN)
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_session_cookie_secure_when_not_local_dev(self):
        with patch.dict(os.environ, owner_env(OWNER_ACCESS_ALLOW_LOCAL_DEV="0"), clear=False):
            self._configure()
            response = self._login(READ_TOKEN)
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("Secure", cookie)

    def test_owner_access_enabled_without_secret_fails_closed_remote(self):
        env = {
            "OWNER_ACCESS_ENABLED": "1",
            "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
            "OWNER_READ_TOKEN": READ_TOKEN,
            "OWNER_ADMIN_TOKEN": "",
            "OWNER_SESSION_SECRET": "",
            "SECRET_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("OWNER_SESSION_SECRET", None)
            os.environ.pop("SECRET_KEY", None)
            self._configure()
            response = self.client.get(
                "/api/sales/meat-leads",
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "owner_access_not_configured")

    def test_sales_page_denied_remote_anonymous_when_access_enabled(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/owner/login", response.headers.get("Location", ""))

    def test_sales_page_allowed_with_owner_session(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            response = self.client.get("/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 200)

    def test_sales_leads_api_denied_remote_anonymous_when_access_enabled(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self.client.get("/api/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_read_access_denied")

    def test_sales_leads_api_allowed_with_owner_read_session(self):
        service_result = {"success": True, "sales_leads": []}
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            with patch.object(sales_transaction_routes, "list_sales_leads", return_value=(service_result, 200)) as list_leads:
                response = self.client.get("/api/sales/meat-leads", environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_leads.assert_called_once()

    def test_command_state_allowed_with_owner_read_session(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            with patch.object(sales_transaction_routes, "get_sam_command_state", return_value=({"ok": True}, 200)) as command_state:
                response = self.client.get(
                    "/api/sales/meat-leads/OSK-SALES-LEAD-1/command-state",
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        command_state.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_command_state_denies_external_worker_token(self):
        with patch.dict(os.environ, owner_env(INTERNAL_WORKER_TOKEN="worker-token-1234567890abcdef"), clear=False):
            self._configure()
            response = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/command-state",
                headers={"Authorization": "Bearer worker-token-1234567890abcdef"},
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "sam_command_state_access_denied")

    @patch.dict(os.environ, {"SAM_COMMAND_STATE_OWNER_TOKEN": "sam-command-token-1234567890abcdef"}, clear=False)
    def test_command_state_still_allows_existing_owner_token(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            with patch.object(sales_transaction_routes, "get_sam_command_state", return_value=({"ok": True}, 200)) as command_state:
                response = self.client.get(
                    "/api/sales/meat-leads/OSK-SALES-LEAD-1/command-state",
                    headers={"Authorization": "Bearer sam-command-token-1234567890abcdef"},
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(response.status_code, 200)
        command_state.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_frontend_contains_no_owner_or_command_state_secret_usage(self):
        checked_paths = [
            "static/js/meatSalesLeads.js",
            "templates/meat-sales-leads.html",
            "templates/owner-login.html",
        ]
        forbidden = [
            "OWNER_READ_TOKEN",
            "OWNER_ADMIN_TOKEN",
            "SAM_COMMAND_STATE_OWNER_TOKEN",
            "X-Sam-Command-State-Token",
            "Authorization",
            "localStorage",
            "sessionStorage",
            "data-secret",
        ]
        for path in checked_paths:
            text = Path(path).read_text(encoding="utf-8")
            for marker in forbidden:
                with self.subTest(path=path, marker=marker):
                    self.assertNotIn(marker, text)

    def test_contract_read_detail_denied_remote_anonymous_when_access_enabled(self):
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            response = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/contract",
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_read_access_denied")

    def test_contract_read_detail_allowed_with_owner_session(self):
        service_result = {"success": True, "lead_id": "OSK-SALES-LEAD-1", "contract": {}}
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self._login(READ_TOKEN)
            with patch.object(
                sales_transaction_routes,
                "get_sales_lead_preorder_contract",
                return_value=(service_result, 200),
            ) as get_contract:
                response = self.client.get(
                    "/api/sales/meat-leads/OSK-SALES-LEAD-1/contract",
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_contract.assert_called_once_with("OSK-SALES-LEAD-1")


if __name__ == "__main__":
    unittest.main()
