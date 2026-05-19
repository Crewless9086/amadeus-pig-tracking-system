import unittest
from unittest.mock import patch

from app import app


class MatingRoutesTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_mark_not_pregnant_route_calls_service(self):
        service_result = {
            "success": True,
            "message": "Mating updated to Repeat_Service.",
            "mating_id": "MAT-1",
            "movement_logged": False,
        }

        with patch("modules.pig_weights.mating_routes.mark_not_pregnant", return_value=service_result) as service:
            response = self.client.post(
                "/api/pig-weights/master/matings/MAT-1/mark-not-pregnant",
                json={"target_pen_id": "PEN-1", "moved_by": "Tester"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["mating_id"], "MAT-1")
        service.assert_called_once_with(
            mating_id="MAT-1",
            target_pen_id="PEN-1",
            moved_by="Tester",
        )

    def test_mark_not_pregnant_route_returns_400_for_service_guard(self):
        with patch(
            "modules.pig_weights.mating_routes.mark_not_pregnant",
            side_effect=ValueError("Only Confirmed_Pregnant matings can be marked not pregnant."),
        ):
            response = self.client.post(
                "/api/pig-weights/master/matings/MAT-1/mark-not-pregnant",
                json={},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Only Confirmed_Pregnant", response.get_json()["errors"][0])


if __name__ == "__main__":
    unittest.main()
