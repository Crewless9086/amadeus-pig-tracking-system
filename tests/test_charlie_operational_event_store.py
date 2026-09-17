import unittest
from datetime import datetime, timezone

from modules.charlie.domain_observer_store import observer_last_runs, record_observer_run
from modules.charlie.operational_event_store import append_operational_event


class FakeCursor:
    def __init__(self, fetchones=None, fetchall=None):
        self.fetchones = list(fetchones or [])
        self.fetchall_value = list(fetchall or [])
        self.commands = []

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=None): self.commands.append((sql, params))
    def fetchone(self): return self.fetchones.pop(0) if self.fetchones else None
    def fetchall(self): return self.fetchall_value


class FakeConnection:
    def __init__(self, cursor): self.value = cursor
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.value


def event():
    return {
        "event_type": "mission.status_changed", "domain": "missions", "aggregate_type": "mission",
        "aggregate_id": "MISSION-1", "source_system": "charlie_mission_store", "authority_tier": "observe",
        "privacy_class": "internal", "occurred_at": "2026-07-19T12:00:00+00:00",
        "payload": {"status": "approved"}, "provenance": {"source_ref": "charlie_missions/MISSION-1"},
        "idempotency_key": "mission-1-approved",
    }


class OperationalStoreTests(unittest.TestCase):
    def test_append_is_idempotent_and_returns_existing_event(self):
        created_cursor = FakeCursor(fetchones=[("EVT-1",)])
        created, created_status = append_operational_event(event(), connect_factory=lambda _url: FakeConnection(created_cursor))
        self.assertEqual(created_status, 201)
        self.assertTrue(created["created"])

        duplicate_cursor = FakeCursor(fetchones=[None, ("EVT-1",)])
        duplicate, duplicate_status = append_operational_event(event(), connect_factory=lambda _url: FakeConnection(duplicate_cursor))
        self.assertEqual(duplicate_status, 200)
        self.assertFalse(duplicate["created"])
        self.assertEqual(duplicate["event_id"], "EVT-1")

    def test_observer_store_refuses_any_authority_expansion(self):
        run = {
            "run_id": "OBS-1", "observer_key": "sam_lead_health", "domain": "sales", "trigger": "schedule",
            "status": "observed", "authority_tier": "observe", "writes_authorized": True,
            "sends_authorized": False, "ran_at": "2026-07-19T12:00:00+00:00",
        }
        result, status = record_observer_run(run, connect_factory=lambda _url: None)
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "observer_authority_contract_invalid")

    def test_observer_run_and_last_run_are_durable(self):
        run = {
            "run_id": "OBS-1", "observer_key": "sam_lead_health", "domain": "sales", "trigger": "schedule",
            "status": "observed", "authority_tier": "observe", "writes_authorized": False,
            "sends_authorized": False, "ran_at": "2026-07-19T12:00:00+00:00", "source_refs": ["sales_leads"],
            "freshness": "live", "facts": [], "gaps": [], "recommendations": [],
        }
        cursor = FakeCursor(fetchones=[("OBS-1",)])
        result, status = record_observer_run(run, connect_factory=lambda _url: FakeConnection(cursor))
        self.assertEqual(status, 201)
        self.assertTrue(result["created"])

        timestamp = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
        last_cursor = FakeCursor(fetchall=[("sam_lead_health", timestamp)])
        last, last_status = observer_last_runs(connect_factory=lambda _url: FakeConnection(last_cursor))
        self.assertEqual(last_status, 200)
        self.assertEqual(last["last_runs"]["sam_lead_health"], timestamp.isoformat())


if __name__ == "__main__":
    unittest.main()
