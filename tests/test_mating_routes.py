import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, patch

from app import app
from modules.pig_weights.mating_routes import _deadline_read, _project_breeding_observations


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
            dry_run=False,
        )

    def test_mark_not_pregnant_route_passes_dry_run(self):
        service_result = {
            "success": True,
            "dry_run": True,
            "message": "Dry run passed. No mating or movement rows were changed.",
            "mating_id": "MAT-1",
            "movement_logged": False,
        }

        with patch("modules.pig_weights.mating_routes.mark_not_pregnant", return_value=service_result) as service:
            response = self.client.post(
                "/api/pig-weights/master/matings/MAT-1/mark-not-pregnant",
                json={"target_pen_id": "PEN-1", "moved_by": "Tester", "dry_run": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["dry_run"])
        service.assert_called_once_with(
            mating_id="MAT-1",
            target_pen_id="PEN-1",
            moved_by="Tester",
            dry_run=True,
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

    @patch("modules.pig_weights.mating_routes.require_owner_read_access", return_value=None)
    @patch("modules.pig_weights.mating_routes.get_breeding_attention_source_snapshot")
    def test_breeding_attention_owner_read_is_advisory_and_write_free(
        self, snapshot, _guard
    ):
        snapshot.return_value = {
            "success": True,
            "allocation_inputs": {
                "overview_rows": [], "pig_master_rows": [], "weight_rows": [],
                "sales_rows": [], "litter_rows": [], "pen_lookup": {},
                "source": "supabase_canonical", "allocation_query_status": "known",
                "medical_query_status": "known",
                "read_progress": {"status": "complete"},
            },
            "mating_rows": [],
            "observation_rows": [],
            "read_progress": {"status": "complete", "query_count": 8, "connection_count": 1},
        }
        response = self.client.get("/api/pig-weights/breeding-attention")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["writes_performed"])
        self.assertEqual(response.get_json()["source_read_progress"]["query_count"], 8)
        snapshot.assert_called_once_with(
            connect_factory=ANY, deadline_seconds=20, started_at=ANY,
        )

    @patch("modules.pig_weights.mating_routes.require_owner_read_access", return_value=None)
    @patch("modules.pig_weights.mating_routes.get_breeding_attention_source_snapshot", side_effect=RuntimeError("timeout"))
    def test_breeding_attention_dependency_failure_is_bounded_unavailable(self, *_mocks):
        response = self.client.get("/api/pig-weights/breeding-attention")
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(response.get_json()["female_count"])

    @patch("modules.pig_weights.mating_routes.require_owner_read_access", return_value=None)
    @patch("modules.pig_weights.mating_routes.get_breeding_attention_source_snapshot")
    def test_breeding_attention_partial_snapshot_is_unavailable_not_zero(self, snapshot, _guard):
        snapshot.return_value = {
            "success": True,
            "read_progress": {"status": "partial"},
            "allocation_inputs": {},
            "mating_rows": [],
            "observation_rows": [],
        }
        response = self.client.get("/api/pig-weights/breeding-attention")
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(response.get_json()["female_count"])

    @patch("modules.pig_weights.mating_routes.require_owner_read_access")
    def test_breeding_attention_anonymous_is_denied(self, guard):
        guard.return_value = ({"success": False, "error": "owner_read_required"}, 403)
        response = self.client.get("/api/pig-weights/breeding-attention")
        self.assertEqual(response.status_code, 403)

    @patch("modules.pig_weights.mating_routes.require_owner_read_access", return_value=None)
    def test_breeding_attention_owner_view_is_guarded(self, _guard):
        response = self.client.get("/api/pig-weights/breeding-attention/view")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Breeding Attention", response.data)

    def test_canonical_observation_projection_uses_latest_effective_fresh_facts(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        rows = [
            ("PIG-1", now - timedelta(hours=2), "behaviour", {"standing_heat_observed": False}, "OBS-NEW"),
            ("PIG-1", now - timedelta(hours=3), "behaviour", {"standing_heat_observed": True}, "OBS-OLD"),
            ("PIG-1", now - timedelta(days=2), "body_condition", {"body_condition_score": 3}, "OBS-BCS"),
            ("PIG-1", now - timedelta(days=10), "body_condition", {"body_condition_score": 1}, "OBS-BCS-OLD"),
        ]
        projected = _project_breeding_observations(rows, now=now)
        self.assertNotIn("heat_state", projected["PIG-1"])
        self.assertEqual(projected["PIG-1"]["body_condition_score"], 3)

    def test_stale_heat_observation_never_becomes_current_heat(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        projected = _project_breeding_observations([
            ("PIG-1", now - timedelta(days=3), "behaviour", {"standing_heat_observed": True}, "OBS-1"),
        ], now=now)
        self.assertNotIn("heat_state", projected["PIG-1"])

    def test_malformed_body_condition_is_unknown_not_affirmative(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        for score in (True, False, 0, 6, float("inf")):
            projected = _project_breeding_observations([
                ("PIG-1", now, "body_condition", {"body_condition_score": score}, "OBS-1"),
            ], now=now)
            self.assertNotIn("body_condition_score", projected["PIG-1"])

    @patch("modules.pig_weights.mating_routes.monotonic", side_effect=[0.0, 21.0])
    def test_total_read_deadline_fails_closed_after_slow_reader(self, _clock):
        with self.assertRaises(TimeoutError):
            _deadline_read(0.0, lambda: {"success": True})


if __name__ == "__main__":
    unittest.main()
