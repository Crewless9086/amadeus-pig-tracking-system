import os
import unittest
from unittest import mock

from app import app


OWNER_ENV = {
    "OWNER_ACCESS_ENABLED": "1",
    "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
    "OWNER_READ_TOKEN": "r" * 40,
    "OWNER_ADMIN_TOKEN": "a" * 40,
    "OWNER_SESSION_SECRET": "rootline-water-route-secret",
}


class WaterEnergyRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.env = mock.patch.dict(os.environ, OWNER_ENV, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def login(self, role):
        key = "OWNER_ADMIN_TOKEN" if role == "admin" else "OWNER_READ_TOKEN"
        response = self.client.post(
            "/owner/login",
            data={"owner_token": OWNER_ENV[key], "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def test_anonymous_cannot_read_refresh_or_record_tanks(self):
        self.assertEqual(
            self.client.get("/api/telemetry/rootline/water-energy-plan").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/telemetry/rootline/water-energy-plan/refresh").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/telemetry/rootline/tank-observations").status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/telemetry/rootline/water-energy-summary").status_code,
            403,
        )

    def test_owner_read_can_list_but_cannot_write(self):
        self.login("read")
        with mock.patch(
            "modules.telemetry.telemetry_routes.get_current_water_energy_plan",
            return_value=({"success": True, "authority": {"controls_hardware": False}}, 200),
        ):
            response = self.client.get("/api/telemetry/rootline/water-energy-plan")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["authority"]["controls_hardware"])
        self.assertFalse(response.get_json()["owner_can_administer"])
        self.assertEqual(
            self.client.post("/api/telemetry/rootline/water-energy-plan/refresh").status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/telemetry/rootline/tank-observations").status_code,
            403,
        )

    def test_owner_read_can_get_oom_sakkie_summary(self):
        self.login("read")
        with mock.patch(
            "modules.telemetry.telemetry_routes.get_oom_sakkie_water_energy_summary",
            return_value=({"success": True, "summary": "Hold pumping.", "authority": {"controls_hardware": False}}, 200),
        ):
            response = self.client.get("/api/telemetry/rootline/water-energy-summary")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["authority"]["controls_hardware"])

    def test_owner_admin_refresh_uses_server_derived_principal(self):
        self.login("admin")
        candidate = {
            "success": True,
            "plan_id": "ROOTLINE-WEP-20260728",
            "authority": {"controls_hardware": False},
        }
        with mock.patch(
            "modules.telemetry.telemetry_routes.build_current_water_energy_plan",
            return_value=candidate,
        ), mock.patch(
            "modules.telemetry.telemetry_routes.append_water_energy_plan",
            return_value=({"success": True, "created": True}, 201),
        ) as append:
            response = self.client.post(
                "/api/telemetry/rootline/water-energy-plan/refresh",
                json={"date": "2026-07-28"},
            )
        self.assertEqual(response.status_code, 201)
        principal = append.call_args.args[1]
        self.assertTrue(principal.startswith("owner-admin:"))
        self.assertNotIn("browser", principal)

    def test_tank_observation_uses_server_principal_and_counts(self):
        self.login("admin")
        with mock.patch(
            "modules.telemetry.telemetry_routes.record_tank_observation",
            return_value=({
                "success": True,
                "storage_reported_count": 4,
                "reservoir_reported_count": 8,
                "storage_state": "OK",
                "reservoir_state": "OK",
                "litres_inferred": False,
                "hardware_control_performed": False,
            }, 201),
        ) as record:
            response = self.client.post(
                "/api/telemetry/rootline/tank-observations",
                json={
                    "storage_reported_count": 4,
                    "reservoir_reported_count": 8,
                    "storage_state": "OK",
                    "reservoir_state": "OK",
                    "observed_at": "2026-07-28T12:00:00+02:00",
                    "idempotency_key": "tank-observation-1",
                },
            )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()["litres_inferred"])
        self.assertTrue(record.call_args.args[1].startswith("owner-admin:"))


if __name__ == "__main__":
    unittest.main()
