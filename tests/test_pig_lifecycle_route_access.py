import unittest
from unittest.mock import patch

from app import app
from modules.pig_weights import pig_weights_routes


class PigLifecycleRouteAccessTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_death_route_denial_prevents_lifecycle_service(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(pig_weights_routes, "require_owner_admin_access", return_value=denied), patch.object(
            pig_weights_routes, "mark_pig_lifecycle_death"
        ) as mark_death:
            response = self.client.post("/api/pig-weights/pig/PIG-1/lifecycle/death", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), denied[0])
        mark_death.assert_not_called()

    def test_death_route_authorized_calls_lifecycle_service(self):
        result = {"success": True, "status": "pig_lifecycle_death_recorded"}
        with patch.object(pig_weights_routes, "require_owner_admin_access", return_value=None), patch.object(
            pig_weights_routes, "mark_pig_lifecycle_death", return_value=(result, 200)
        ) as mark_death:
            response = self.client.post("/api/pig-weights/pig/PIG-1/lifecycle/death", json={"reason": "natural"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), result)
        mark_death.assert_called_once_with("PIG-1", {"reason": "natural"})
