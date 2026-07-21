import unittest
from unittest.mock import patch

from app import app
from modules.pig_weights import pig_weights_routes
from modules.sales import sales_transaction_routes


class LifecycleAuthorityRouteTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_lifecycle_write_routes_stop_before_services_when_owner_admin_access_denied(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        routes = [
            (
                pig_weights_routes,
                "/api/pig-weights/pig/PIG-1/lifecycle/death",
                "mark_pig_lifecycle_death",
            ),
            (
                pig_weights_routes,
                "/api/pig-weights/litter/LITTER-1/piglet-deaths",
                "mark_litter_profile_piglets_dead",
            ),
            (
                sales_transaction_routes,
                "/api/sales-transactions/SALE-1/confirm-pig-exits",
                "confirm_slaughter_pig_exits",
            ),
            (
                sales_transaction_routes,
                "/api/sales-transactions/SALE-1/reconcile-pig-exits",
                "reconcile_closed_slaughter_pig_exits",
            ),
        ]

        for module, path, service_name in routes:
            with self.subTest(path=path), patch.object(
                module, "require_owner_admin_access", return_value=denied
            ), patch.object(module, service_name) as service:
                response = self.client.post(path, json={"dry_run": False})

            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["status"], "owner_admin_access_denied")
            service.assert_not_called()


if __name__ == "__main__":
    unittest.main()
