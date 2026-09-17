import unittest
from unittest.mock import patch

from app import app
from modules.pig_weights import pig_weights_routes


class PigLifecycleRouteAccessTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_death_route_denial_prevents_lifecycle_service(self):
        denied = {"success": False, "status": "authenticated_mortality_permission_required"}
        with patch.object(pig_weights_routes, "mortality_session_identity", return_value=None), patch.object(
            pig_weights_routes, "mark_pig_lifecycle_death"
        ) as mark_death:
            response = self.client.post("/api/pig-weights/pig/PIG-1/lifecycle/death", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), denied)
        mark_death.assert_not_called()

    def test_death_route_authorized_uses_shared_preview_service(self):
        result = {"success": True, "status": "preview_ready"}
        identity = {"actor_id":"synthetic-actor","language":"af","role":"farm_manager","capabilities":{"mortality_confirmation"}}
        payload = {"phase":"preview","event_date":"2026-09-09"}
        with patch.object(pig_weights_routes, "mortality_session_identity", return_value=identity), patch.object(
            pig_weights_routes, "require_mortality_session", return_value=None
        ), patch('modules.oom_sakkie.herdmaster_health_loss_runtime.handle_application_mortality', return_value=(result,200)) as shared, patch.object(
            pig_weights_routes, "mark_pig_lifecycle_death") as legacy:
            response = self.client.post("/api/pig-weights/pig/PIG-1/lifecycle/death", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), result)
        shared.assert_called_once_with("PIG-1", payload, identity, resume=False)
        legacy.assert_not_called()

    def test_compatibility_disabled_access_never_authorizes_mortality(self):
        with patch.dict('os.environ', {"OWNER_ACCESS_ENABLED":"false","OWNER_ACCESS_ALLOW_LOCAL_DEV":"true"}):
            response = self.client.post('/api/pig-weights/pig/PIG-1/lifecycle/death',json={"phase":"confirm","operation_id":"forged"})
        self.assertEqual(response.status_code,403)
