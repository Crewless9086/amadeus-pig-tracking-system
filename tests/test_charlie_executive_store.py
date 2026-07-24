import unittest

from modules.charlie.executive_store import claim_pending_outbox, complete_outbox, mission_outbox_delivery


class _Cursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return ("failed",)

    def fetchall(self):
        return [("OUT-1", "owner:CAL:protected_review:generation", "NEEDS_OWNER_APPROVAL", "dead_letter", 5, None, "network", "2026-07-21T08:00:00Z", None, {"mission_id": "CAL", "notification_fingerprint": "generation"})]


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


class CharlieExecutiveStoreTests(unittest.TestCase):
    def test_mission_delivery_audit_exposes_durable_outbox_states(self):
        connection = _Connection()
        result, status_code = mission_outbox_delivery(
            "CAL", database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(result["items"][0]["status"], "dead_letter")
        self.assertEqual(result["items"][0]["notification_fingerprint"], "generation")
        self.assertEqual(connection.cursor_instance.executed[0][1]["mission_id"], "CAL")


    def test_outbox_claim_withholds_superseded_and_owner_decided_handoffs(self):
        connection = _Connection()
        result, code = claim_pending_outbox(
            database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )
        self.assertEqual(code, 200)
        sql, _params = connection.cursor_instance.executed[-1]
        self.assertIn("'withheld','superseded','owner_decided'", sql)
    def test_failed_protected_delivery_retains_explicit_failed_handoff_state(self):
        connection = _Connection()
        result, status_code = complete_outbox(
            "OUT-1", sent=False, error="telegram unavailable",
            database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "failed")
        sql, params = connection.cursor_instance.executed[-1]
        self.assertIn("jsonb_build_object('handoff_state'", sql)
        self.assertEqual(params["handoff_state"], "failed")
        self.assertFalse(params["sent"])

    def test_delivery_audit_exposes_explicit_handoff_binding(self):
        connection = _Connection()
        connection.cursor_instance.fetchall = lambda: [(
            "OUT-1", "owner:CAL:protected_review:decision-1", "NEEDS_OWNER_APPROVAL", "sent", 1,
            None, "", "2026-07-21T08:00:00Z", "2026-07-21T08:01:00Z",
            {"mission_id": "CAL", "notification_fingerprint": "decision-1", "handoff_state": "sent",
             "decision_identity": "decision-1", "review_generation": "EXEC-1:abc", "tested_revision": "abc"},
        )]
        result, code = mission_outbox_delivery(
            "CAL", database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )
        self.assertEqual(code, 200)
        self.assertEqual(result["items"][0]["handoff_state"], "sent")
        self.assertEqual(result["items"][0]["decision_identity"], "decision-1")
        self.assertEqual(result["items"][0]["tested_revision"], "abc")
if __name__ == "__main__":
    unittest.main()
