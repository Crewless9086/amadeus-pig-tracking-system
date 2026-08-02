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

    @patch("modules.pig_weights.mating_routes.require_owner_read_access", return_value=None)
    @patch("modules.pig_weights.mating_routes.list_observations")
    def test_observation_history_is_owner_read_only(self, service, _guard):
        service.return_value = ({"success": True, "history": []}, 200)
        response = self.client.get(
            "/api/pig-weights/breeding-attention/SOW-1/observations"
        )
        self.assertEqual(response.status_code, 200)
        service.assert_called_once_with("SOW-1")

    @patch("modules.pig_weights.mating_routes.strict_owner_admin_principal", return_value="owner-admin:stable")
    @patch("modules.pig_weights.mating_routes.require_strict_owner_admin_access", return_value=None)
    @patch("modules.pig_weights.mating_routes.record_observation")
    def test_observation_record_uses_server_principal_and_ignores_browser_actor(
        self, service, _guard, _principal
    ):
        service.return_value = ({"success": True, "status": "observation_recorded"}, 201)
        response = self.client.post(
            "/api/pig-weights/breeding-attention/SOW-1/observations",
            json={"owner_id": "spoofed", "pig_id": "OTHER"},
        )
        self.assertEqual(response.status_code, 201)
        payload = service.call_args.args[0]
        self.assertEqual(payload["pig_id"], "SOW-1")
        service.assert_called_once_with(payload, actor_id="owner-admin:stable")

    @patch("modules.pig_weights.mating_routes.require_strict_owner_admin_access")
    def test_observation_record_owner_read_or_anonymous_is_denied(self, guard):
        guard.return_value = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        response = self.client.post(
            "/api/pig-weights/breeding-attention/SOW-1/observations", json={}
        )
        self.assertEqual(response.status_code, 403)

    @patch("modules.pig_weights.mating_routes.require_strict_owner_admin_access", return_value=None)
    @patch("modules.pig_weights.mating_routes._build_breeding_attention_packets")
    @patch("modules.pig_weights.mating_routes.preview_observation")
    def test_observation_preview_is_strict_admin_and_ignores_browser_context(
        self, service, packet_builder, _guard,
    ):
        attention_packet = {
            "success": True,
            "animals": [{
                "pig_id": "SOW-1",
                "current_state": "Needs Data",
                "filter_state": "Needs Data",
                "recommended_human_action": "owner decision required",
                "missing_facts": ["body condition"],
                "conflicting_facts": [],
            }],
        }
        packet_builder.return_value = (
            attention_packet, attention_packet, 0.0
        )
        service.return_value = ({"success": True, "status": "observation_preview"}, 200)
        response = self.client.post(
            "/api/pig-weights/breeding-attention/SOW-1/observations/preview",
            json={
                "pig_id": "OTHER",
                "current_attention": {"missing_facts": []},
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "body_condition_score": 3,
                "factual_note": "Observed standing and walking.",
                "idempotency_key": "preview-route-1",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = service.call_args.args[0]
        self.assertEqual(payload["pig_id"], "SOW-1")
        self.assertNotIn("current_attention", payload)
        self.assertEqual(
            service.call_args.kwargs["authoritative_attention"]["pig_id"],
            "SOW-1",
        )
        self.assertEqual(
            service.call_args.kwargs["hypothetical_attention"]["pig_id"],
            "SOW-1",
        )

    @patch("modules.pig_weights.mating_routes.require_strict_owner_admin_access", return_value=None)
    @patch("modules.pig_weights.mating_routes._build_breeding_attention_packets")
    def test_observation_preview_fails_closed_when_attention_is_unavailable(
        self, packet_builder, _guard,
    ):
        packet_builder.side_effect = RuntimeError("unavailable")
        response = self.client.post(
            "/api/pig-weights/breeding-attention/SOW-1/observations/preview",
            json={
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "body_condition_score": 3,
                "factual_note": "Observed standing and walking.",
                "idempotency_key": "preview-route-unavailable",
            },
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["status"],
            "current_attention_evidence_unavailable",
        )

    def test_canonical_observation_projection_uses_latest_effective_fresh_facts(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        rows = [
            ("PIG-1", now - timedelta(hours=2), "behaviour", {"standing_heat_observed": False}, "OBS-NEW"),
            ("PIG-1", now - timedelta(hours=3), "behaviour", {"standing_heat_observed": True}, "OBS-OLD"),
            ("PIG-1", now - timedelta(days=2), "body_condition", {"body_condition_score": 3}, "OBS-BCS"),
            ("PIG-1", now - timedelta(days=10), "body_condition", {"body_condition_score": 1}, "OBS-BCS-OLD"),
        ]
        projected = _project_breeding_observations(rows, now=now)
        self.assertEqual(projected["PIG-1"]["heat_state"], "not_observed")
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

    def test_versioned_breeding_observation_updates_only_supported_fresh_facts(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        projected = _project_breeding_observations([{
            "pig_id": "PIG-1",
            "observed_at": now,
            "observation_category": "other",
            "measurements_json": {
                "contract_version": "herdmaster_breeding_observation_v1",
                "body_condition_score": 3,
                "standing_heat": "observed",
                "visible_injury": "none_observed",
            },
            "observation_event_id": "OBS-1",
        }], now=now)
        self.assertEqual(projected["PIG-1"]["body_condition_score"], 3)
        self.assertEqual(projected["PIG-1"]["heat_state"], "standing")
        self.assertNotIn("medical_status", projected["PIG-1"])
        self.assertNotIn("breeding_ready", projected["PIG-1"])

    def test_equal_time_projection_uses_real_deterministic_event_identity(self):
        from modules.pig_weights.herdmaster_breeding_observation_service import (
            observation_event_id,
        )
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        actual_id = observation_event_id("preview-record-same")
        rows = [
            {
                "pig_id": "PIG-1",
                "observed_at": now,
                "observation_category": "other",
                "measurements_json": {
                    "contract_version": "herdmaster_breeding_observation_v1",
                    "standing_heat": "not_observed",
                },
                "observation_event_id": "HERD-OBS-00000000000000000000000000000000",
            },
            {
                "pig_id": "PIG-1",
                "observed_at": now,
                "observation_category": "other",
                "measurements_json": {
                    "contract_version": "herdmaster_breeding_observation_v1",
                    "standing_heat": "observed",
                },
                "observation_event_id": actual_id,
            },
        ]
        preview = _project_breeding_observations(rows, now=now)
        recorded = _project_breeding_observations(
            [{**rows[0]}, {**rows[1], "observation_event_id": actual_id}],
            now=now,
        )
        self.assertEqual(preview, recorded)

    def test_separate_versioned_events_project_each_latest_fact(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        version = "herdmaster_breeding_observation_v1"
        projected = _project_breeding_observations([
            ("PIG-1", now, "other", {
                "contract_version": version, "standing_heat": "not_recorded",
                "body_condition_score": 3,
            }, "OBS-BCS"),
            ("PIG-1", now - timedelta(hours=2), "other", {
                "contract_version": version, "standing_heat": "observed",
            }, "OBS-HEAT"),
        ], now=now)
        self.assertEqual(projected["PIG-1"]["body_condition_score"], 3)
        self.assertEqual(projected["PIG-1"]["heat_state"], "standing")

    def test_unrelated_other_event_cannot_hide_breeding_evidence(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        projected = _project_breeding_observations([
            ("PIG-1", now, "other", {"contract_version": "auction_review_v1"}, "OTHER"),
            ("PIG-1", now - timedelta(hours=1), "other", {
                "contract_version": "herdmaster_breeding_observation_v1",
                "standing_heat": "observed",
            }, "BREEDING"),
        ], now=now)
        self.assertEqual(projected["PIG-1"]["heat_state"], "standing")

    def test_cross_category_projection_uses_global_chronology(self):
        now = datetime(2026, 7, 27, 10, tzinfo=timezone.utc)
        version = "herdmaster_breeding_observation_v1"
        projected = _project_breeding_observations([
            ("PIG-1", now - timedelta(days=2), "body_condition",
             {"body_condition_score": 2}, "LEGACY-BCS"),
            ("PIG-1", now - timedelta(hours=2), "behaviour",
             {"standing_heat_observed": False}, "LEGACY-HEAT"),
            ("PIG-1", now - timedelta(hours=1), "other", {
                "contract_version": version, "standing_heat": "observed",
                "body_condition_score": 3,
            }, "PHASE2"),
        ], now=now)
        self.assertEqual(projected["PIG-1"]["body_condition_score"], 3)
        self.assertEqual(projected["PIG-1"]["heat_state"], "standing")
        inverse = _project_breeding_observations([
            ("PIG-1", now, "body_condition", {"body_condition_score": 4}, "NEW"),
            ("PIG-1", now - timedelta(hours=1), "other", {
                "contract_version": version, "body_condition_score": 3,
            }, "OLD"),
        ], now=now)
        self.assertEqual(inverse["PIG-1"]["body_condition_score"], 4)

    @patch("modules.pig_weights.mating_routes.monotonic", side_effect=[0.0, 21.0])
    def test_total_read_deadline_fails_closed_after_slow_reader(self, _clock):
        with self.assertRaises(TimeoutError):
            _deadline_read(0.0, lambda: {"success": True})


if __name__ == "__main__":
    unittest.main()
