import unittest
from unittest.mock import patch

from app import app


class LitterWeaningRoutesTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    @patch("modules.pig_weights.pig_weights_routes.require_owner_admin_access")
    def test_anonymous_or_owner_read_cannot_apply_weaning_packet(self, guard):
        guard.return_value = (
            {"success": False, "status": "owner_admin_access_denied"}, 403
        )
        response = self.client.post(
            "/api/pig-weights/litter/LIT-1/weaning-day",
            json={"dry_run": False},
        )
        self.assertEqual(response.status_code, 403)

    @patch(
        "modules.pig_weights.pig_weights_routes.require_owner_admin_access",
        return_value=None,
    )
    @patch(
        "modules.pig_weights.pig_weights_routes.owner_admin_principal",
        return_value="owner-admin:server-derived",
    )
    @patch(
        "modules.pig_weights.pig_weights_routes.process_litter_profile_weaning_day",
        side_effect=TimeoutError("private database detail"),
    )
    def test_unexpected_failure_is_structured_json_without_private_error(
        self, _service, _principal, _guard,
    ):
        response = self.client.post(
            "/api/pig-weights/litter/LIT-1/weaning-day",
            json={"dry_run": False},
        )
        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.is_json)
        payload = response.get_json()
        self.assertEqual(payload["status"], "weaning_day_unexpected_failure")
        self.assertEqual(payload["operation_state"], "unknown_verify_before_retry")
        self.assertIsNone(payload["writes_to_sheets"])
        self.assertIsNone(payload["writes_to_supabase"])
        self.assertNotIn("private database detail", str(payload))

    @patch(
        "modules.pig_weights.pig_weights_routes.require_owner_admin_access",
        return_value=None,
    )
    @patch(
        "modules.pig_weights.pig_weights_routes.owner_admin_principal",
        return_value="owner-admin:server-derived",
    )
    @patch("modules.pig_weights.pig_weights_routes.process_litter_profile_weaning_day")
    def test_structured_transaction_failure_is_preserved(
        self, service, _principal, _guard,
    ):
        service.return_value = ({
            "success": False,
            "status": "weaning_day_transaction_failed",
            "operation_state": "unknown_verify_before_retry",
        }, 503)
        response = self.client.post(
            "/api/pig-weights/litter/LIT-1/weaning-day",
            json={"dry_run": False},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["status"], "weaning_day_transaction_failed"
        )

    @patch(
        "modules.pig_weights.pig_weights_routes.require_owner_admin_access",
        return_value=None,
    )
    @patch(
        "modules.pig_weights.pig_weights_routes.owner_admin_principal",
        return_value="owner-admin:server-derived",
    )
    @patch("modules.pig_weights.pig_weights_routes.process_litter_profile_weaning_day")
    def test_browser_changed_by_is_replaced_with_server_principal(
        self, service, _principal, _guard,
    ):
        service.return_value = ({"success": True}, 200)
        response = self.client.post(
            "/api/pig-weights/litter/LIT-1/weaning-day",
            json={"dry_run": False, "changed_by": "browser:spoofed"},
        )
        self.assertEqual(response.status_code, 200)
        payload = service.call_args.args[1]
        self.assertEqual(payload["changed_by"], "owner-admin:server-derived")
        self.assertNotEqual(payload["changed_by"], "browser:spoofed")


if __name__ == "__main__":
    unittest.main()
