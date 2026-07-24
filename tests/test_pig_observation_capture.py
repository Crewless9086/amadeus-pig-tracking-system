import unittest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch

from modules.pig_weights import pig_weights_routes
from modules.pig_weights.pig_observation_capture_service import record_management_intent, record_observation


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


class PigObservationCaptureTests(unittest.TestCase):
    observation = {
        "pig_id": "P-1", "observed_at": "2026-07-22T10:00:00+02:00",
        "category": "welfare", "severity": "medium", "confidence": 0.9,
        "note": "Limp observed.", "evidence_reference": "photo:local-1", "idempotency_key": "obs-1",
    }
    intent = {
        "pig_id": "P-1", "intended_at": "2026-07-22T10:01:00+02:00",
        "intent_type": "sell_after_weaning", "confidence": 0.8,
        "rationale": "Owner planning note.", "observation_event_id": "OBS-1", "idempotency_key": "intent-1",
    }

    def test_observation_persists_factual_event_with_server_author(self):
        cursor = _Cursor([("OBS-1",)])
        result, status = record_observation(self.observation, "owner-admin-test", connect_factory=lambda _: _Connection(cursor))
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "observation_recorded")
        self.assertFalse(result["writes_to_pigs"])
        sql, params = cursor.calls[0]
        self.assertIn("insert into public.pig_observation_events", sql.lower())
        self.assertEqual(params[3], "owner-admin-test")
        self.assertNotIn("author", self.observation)

    def test_management_intent_is_advisory_and_never_an_action(self):
        cursor = _Cursor([("INTENT-1",)])
        result, status = record_management_intent(self.intent, "owner-admin-test", connect_factory=lambda _: _Connection(cursor))
        self.assertEqual(status, 201)
        self.assertTrue(result["advisory_only"])
        self.assertFalse(result["executes_action"])
        self.assertIn("insert into public.pig_management_intent_events", cursor.calls[0][0].lower())

    def test_capture_rejects_invalid_confidence_before_database_write(self):
        result, status = record_observation({**self.observation, "confidence": 1.1}, "owner-admin-test", connect_factory=lambda _: self.fail("must not connect"))
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "invalid_observation")

    def test_capture_fails_closed_when_database_is_not_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            result, status = record_management_intent(self.intent, "owner-admin-test")
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "observation_capture_not_configured")

    def test_duplicate_idempotency_key_returns_existing_event_without_update(self):
        cursor = _Cursor([None, ("OBS-1", "P-1", datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc), "owner-admin-test", "welfare", "medium", "Limp observed.", Decimal("0.900"), "photo:local-1", "owner", "owner-admin-test", "obs-1")])
        result, status = record_observation(self.observation, "owner-admin-test", connect_factory=lambda _: _Connection(cursor))
        self.assertEqual(status, 201)
        self.assertTrue(result["replayed"])
        self.assertIn("select observation_event_id", cursor.calls[1][0].lower())

    def test_management_intent_replay_compares_postgres_decimal_confidence(self):
        cursor = _Cursor([None, ("INTENT-1", "P-1", datetime(2026, 7, 22, 8, 1, tzinfo=timezone.utc), "owner-admin-test", "sell_after_weaning", "Owner planning note.", Decimal("0.800"), "OBS-1", None, "owner", "owner-admin-test", "intent-1")])
        result, status = record_management_intent(self.intent, "owner-admin-test", connect_factory=lambda _: _Connection(cursor))
        self.assertEqual(status, 201)
        self.assertTrue(result["replayed"])

    def test_observation_reused_key_with_different_content_is_rejected(self):
        cursor = _Cursor([None, ("OBS-1", "P-1", datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc), "owner-admin-test", "welfare", "medium", "Different fact.", 0.9, "photo:local-1", "owner", "owner-admin-test", "obs-1")])
        result, status = record_observation(self.observation, "owner-admin-test", connect_factory=lambda _: _Connection(cursor))
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "idempotency_key_content_mismatch")

    def test_management_intent_reused_key_with_different_content_is_rejected(self):
        cursor = _Cursor([None, ("INTENT-1", "P-1", datetime(2026, 7, 22, 8, 1, tzinfo=timezone.utc), "owner-admin-test", "sell_after_weaning", "Different plan.", 0.8, "OBS-1", None, "owner", "owner-admin-test", "intent-1")])
        result, status = record_management_intent(self.intent, "owner-admin-test", connect_factory=lambda _: _Connection(cursor))
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "idempotency_key_content_mismatch")

    def test_routes_require_owner_admin_before_capture_service(self):
        app = __import__("app").app
        app.config.update(TESTING=True)
        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with app.test_client() as client, patch.object(pig_weights_routes, "require_owner_admin_access", return_value=denied), patch.object(pig_weights_routes, "record_observation") as capture:
            response = client.post("/api/pig-weights/pigs/P-1/observations", json=self.observation)
        self.assertEqual(response.status_code, 403)
        capture.assert_not_called()

    def test_routes_delegate_distinct_intent_capture(self):
        app = __import__("app").app
        app.config.update(TESTING=True)
        with app.test_client() as client, patch.object(pig_weights_routes, "require_owner_admin_access", return_value=None), patch.object(pig_weights_routes, "owner_actor_reference", return_value="owner-admin-test"), patch.object(pig_weights_routes, "record_management_intent", return_value=({"success": True, "advisory_only": True}, 201)) as capture:
            response = client.post("/api/pig-weights/pigs/P-1/management-intents", json=self.intent)
        self.assertEqual(response.status_code, 201)
        capture.assert_called_once_with(self.intent, "owner-admin-test")

    def test_routes_reject_capture_when_a_protected_session_has_no_actor_reference(self):
        app = __import__("app").app
        app.config.update(TESTING=True)
        with app.test_client() as client, patch.object(pig_weights_routes, "require_owner_admin_access", return_value=None), patch.object(pig_weights_routes, "owner_actor_reference", return_value=""), patch.object(pig_weights_routes, "record_observation") as capture:
            response = client.post("/api/pig-weights/pigs/P-1/observations", json=self.observation)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_actor_reference_unavailable")
        capture.assert_not_called()

    def test_observation_route_derives_pig_id_from_path(self):
        app = __import__("app").app
        app.config.update(TESTING=True)
        payload = {key: value for key, value in self.observation.items() if key != "pig_id"}
        with app.test_client() as client, patch.object(pig_weights_routes, "require_owner_admin_access", return_value=None), patch.object(pig_weights_routes, "owner_actor_reference", return_value="owner-admin-test"), patch.object(pig_weights_routes, "record_observation", return_value=({"success": True}, 201)) as capture:
            response = client.post("/api/pig-weights/pigs/P-1/observations", json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(capture.call_args.args[0]["pig_id"], "P-1")
        self.assertEqual(capture.call_args.args[1], "owner-admin-test")

    def test_capture_routes_reject_body_pig_id_mismatch_before_service(self):
        app = __import__("app").app
        app.config.update(TESTING=True)
        with app.test_client() as client, patch.object(pig_weights_routes, "require_owner_admin_access", return_value=None), patch.object(pig_weights_routes, "owner_actor_reference", return_value="owner-admin-test"), patch.object(pig_weights_routes, "record_observation") as observation_capture, patch.object(pig_weights_routes, "record_management_intent") as intent_capture:
            observation_response = client.post("/api/pig-weights/pigs/P-2/observations", json=self.observation)
            intent_response = client.post("/api/pig-weights/pigs/P-2/management-intents", json=self.intent)
        self.assertEqual(observation_response.status_code, 400)
        self.assertEqual(observation_response.get_json()["status"], "pig_id_path_mismatch")
        self.assertFalse(observation_response.get_json()["writes_to_pigs"])
        self.assertFalse(observation_response.get_json()["executes_action"])
        self.assertEqual(intent_response.status_code, 400)
        self.assertEqual(intent_response.get_json()["status"], "pig_id_path_mismatch")
        observation_capture.assert_not_called()
        intent_capture.assert_not_called()

    def test_global_capture_routes_are_not_exposed(self):
        app = __import__("app").app
        app.config.update(TESTING=True)
        with app.test_client() as client:
            observation_response = client.post("/api/pig-weights/observations", json=self.observation)
            intent_response = client.post("/api/pig-weights/management-intents", json=self.intent)
        self.assertEqual(observation_response.status_code, 404)
        self.assertEqual(intent_response.status_code, 404)

    def test_capture_rejects_missing_server_author_before_database_write(self):
        result, status = record_observation(self.observation, "", connect_factory=lambda _: self.fail("must not connect"))
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "invalid_observation")
