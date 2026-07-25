import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.pig_weights import pig_observation_capture_service as capture_service
from modules.pig_weights import pig_weights_routes


OBSERVATION = {
    "observed_at": "2026-07-25T10:00:00+00:00",
    "category": "welfare",
    "severity": "high",
    "note": "Standing apart from the group.",
    "measurements": {"water_checks": 1},
    "confidence": 0.95,
    "idempotency_key": "obs-key-1",
}
INTENT = {
    "intended_at": "2026-07-25T10:00:00+00:00",
    "intent_type": "hold_for_review",
    "intent_status": "advisory",
    "rationale": "Review the factual welfare observation.",
    "confidence": 0.9,
    "idempotency_key": "intent-key-1",
}


class _Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return next(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


class PigObservationCaptureServiceTests(unittest.TestCase):
    def test_owner_authorized_observation_append_succeeds_without_current_state_mutation(self):
        cursor = _Cursor([("PIG-1",), None])
        result, status = capture_service.capture_observation(
            "PIG-1", OBSERVATION, actor_id="owner-admin:test", connect_factory=lambda _: _Connection(cursor)
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "pig_observation_captured")
        self.assertTrue(result["writes_to_supabase"])
        self.assertFalse(result["changes_pig_current_state"])
        sql = "\n".join(call[0].lower() for call in cursor.calls)
        self.assertIn("insert into public.pig_observation_events", sql)
        self.assertNotIn("update public.pigs", sql)
        self.assertNotIn("insert into public.pigs", sql)

    def test_advisory_intent_append_is_separate_from_observation_and_current_state(self):
        cursor = _Cursor([("PIG-1",), None])
        result, status = capture_service.capture_management_intent(
            "PIG-1", INTENT, actor_id="owner-admin:test", connect_factory=lambda _: _Connection(cursor)
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "pig_management_intent_captured")
        sql = "\n".join(call[0].lower() for call in cursor.calls)
        self.assertIn("insert into public.pig_management_intent_events", sql)
        self.assertNotIn("pig_observation_events", sql.split("insert into public.pig_management_intent_events")[1])
        self.assertNotIn("update public.pigs", sql)

    def test_invalid_or_non_advisory_payload_fails_before_connecting(self):
        payload = {**INTENT, "intent_status": "approved"}
        with patch.object(capture_service, "_connect") as connect:
            result, status = capture_service.capture_management_intent("PIG-1", payload, actor_id="owner-admin:test")
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "pig_management_intent_capture_invalid")
        self.assertFalse(result["writes_to_supabase"])
        connect.assert_not_called()

    def test_invalid_pig_and_schema_unavailable_fail_closed(self):
        missing_cursor = _Cursor([None])
        missing, missing_status = capture_service.capture_observation(
            "PIG-X", OBSERVATION, actor_id="owner-admin:test", connect_factory=lambda _: _Connection(missing_cursor)
        )
        self.assertEqual(missing_status, 404)
        self.assertFalse(missing["writes_to_supabase"])
        unavailable, unavailable_status = capture_service.capture_observation(
            "PIG-1", OBSERVATION, actor_id="owner-admin:test", connect_factory=lambda _: (_ for _ in ()).throw(RuntimeError())
        )
        self.assertEqual(unavailable_status, 503)
        self.assertEqual(unavailable["status"], "pig_observation_capture_schema_unavailable")
        self.assertFalse(unavailable["changes_pig_current_state"])

    def test_cross_pig_idempotency_conflict_has_no_write(self):
        cursor = _Cursor([("PIG-1",), ("PIG-OTHER", "obs-key-1")])
        result, status = capture_service.capture_observation(
            "PIG-1", OBSERVATION, actor_id="owner-admin:test", connect_factory=lambda _: _Connection(cursor)
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "pig_observation_capture_idempotency_conflict")
        self.assertFalse(result["writes_to_supabase"])
        self.assertEqual(len(cursor.calls), 2)

    def test_same_pig_duplicate_with_different_payload_is_a_conflict(self):
        cursor = _Cursor([("PIG-1",), ("PIG-1", "obs-key-1"), None])
        result, status = capture_service.capture_observation(
            "PIG-1", OBSERVATION, actor_id="owner-admin:test", connect_factory=lambda _: _Connection(cursor)
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "pig_observation_capture_idempotency_conflict")
        self.assertFalse(result["writes_to_supabase"])
        self.assertEqual(len(cursor.calls), 3)

    def test_capture_service_contains_no_protected_current_state_or_commercial_mutation(self):
        source = Path(capture_service.__file__).read_text(encoding="utf-8").lower()
        prohibited = (
            "update public.pigs", "insert into public.pigs", "delete from public.pigs",
            "update public.orders", "insert into public.orders", "update public.sales",
            "update public.reservations", "update public.pig_lifecycle_events",
        )
        for statement in prohibited:
            with self.subTest(statement=statement):
                self.assertNotIn(statement, source)


class PigObservationCaptureRouteTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_denied_capture_routes_do_not_call_services(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(pig_weights_routes, "require_owner_admin_access", return_value=denied), patch.object(
            pig_weights_routes, "capture_pig_observation"
        ) as observation, patch.object(pig_weights_routes, "capture_pig_management_intent") as intent:
            response = self.client.post("/api/pig-weights/pigs/PIG-1/observations", json=OBSERVATION)
            intent_response = self.client.post("/api/pig-weights/pigs/PIG-1/management-intents", json=INTENT)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(intent_response.status_code, 403)
        observation.assert_not_called()
        intent.assert_not_called()

    def test_authorized_routes_bind_server_owner_principal(self):
        result = {"success": True, "status": "pig_observation_captured"}
        with patch.object(pig_weights_routes, "require_owner_admin_access", return_value=None), patch.object(
            pig_weights_routes, "owner_admin_principal", return_value="owner-admin:test"
        ), patch.object(pig_weights_routes, "capture_pig_observation", return_value=(result, 201)) as observation:
            response = self.client.post("/api/pig-weights/pigs/PIG-1/observations", json=OBSERVATION)
        self.assertEqual(response.status_code, 201)
        observation.assert_called_once_with("PIG-1", OBSERVATION, actor_id="owner-admin:test")


if __name__ == "__main__":
    unittest.main()
