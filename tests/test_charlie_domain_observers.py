import unittest
from datetime import datetime, timezone

from modules.charlie.domain_observers import OBSERVERS, due_observers, observer_quality, run_observer, run_observer_cycle


class DomainObserverTests(unittest.TestCase):
    def test_all_priority_domains_have_bounded_observers(self):
        self.assertEqual(set(OBSERVERS), {"sam_lead_health", "ledger_cash_exceptions", "herdmaster_readiness", "beacon_opportunities"})
        self.assertTrue(all(item["authority"] == "observe" for item in OBSERVERS.values()))

    def test_schedule_and_event_triggers_are_supported(self):
        now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
        recent = {key: now.isoformat() for key in OBSERVERS}
        self.assertEqual(due_observers(recent, now=now), [])
        due = due_observers(recent, now=now, event_domains={"sales"})
        self.assertEqual([item["observer_key"] for item in due], ["sam_lead_health"])
        self.assertEqual(due[0]["trigger"], "event")

    def test_observer_can_only_propose(self):
        result = run_observer("sam_lead_health", lambda _domain: {
            "source_refs": ["sales_leads"], "freshness": "live", "facts": [{"open": 3}],
            "recommendations": [{"summary": "Review one stale lead"}],
        })
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["writes_authorized"])
        self.assertFalse(result["sends_authorized"])
        self.assertTrue(result["recommendations"][0]["proposal_only"])
        self.assertFalse(result["recommendations"][0]["execution_authorized"])

    def test_failure_telemetry_and_false_positive_measurement(self):
        failed = run_observer("ledger_cash_exceptions", lambda _domain: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(failed["status"], "failed")
        observed = run_observer("beacon_opportunities", lambda _domain: {
            "source_refs": ["campaigns"], "freshness": "live", "recommendations": [{"summary": "Test"}],
        })
        recommendation_id = observed["recommendations"][0]["recommendation_id"]
        quality = observer_quality([failed, observed], {recommendation_id: False})
        self.assertEqual(quality["false_positive_rate"], 1.0)

    def test_cycle_runs_due_observers_and_persists_telemetry_only(self):
        recorded = []
        now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)
        readers = {domain: (lambda selected: lambda _domain: {
            "source_refs": [selected], "freshness": "live", "recommendations": [],
        })(domain) for domain in {item["domain"] for item in OBSERVERS.values()}}
        result = run_observer_cycle(readers, now=now, recorder=lambda run: recorded.append(run["run_id"]) or {"status": "recorded"})
        self.assertEqual(len(result["runs"]), 4)
        self.assertEqual(len(recorded), 4)
        self.assertFalse(result["writes_authorized"])
        self.assertFalse(result["sends_authorized"])
        self.assertTrue(all(item["persistence"]["status"] == "recorded" for item in result["runs"]))


if __name__ == "__main__":
    unittest.main()
