import unittest

from modules.charlie.executive_store import mission_outbox_delivery


class _Cursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

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


if __name__ == "__main__":
    unittest.main()
