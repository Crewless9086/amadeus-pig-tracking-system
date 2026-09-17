import unittest
from unittest.mock import patch

from scripts import charlie_mission_pickup


class DomainObserverRunnerTests(unittest.TestCase):
    def test_observers_are_default_off(self):
        with patch("scripts.charlie_mission_pickup.observer_last_runs") as last_runs:
            result = charlie_mission_pickup._run_domain_observers(environ={})
        self.assertEqual(result["status"], "domain_observers_disabled")
        last_runs.assert_not_called()

    @patch("scripts.charlie_mission_pickup.run_observer_cycle")
    @patch("scripts.charlie_mission_pickup.observer_readers", return_value={"sam_lead_health": object()})
    @patch("scripts.charlie_mission_pickup.observer_last_runs")
    def test_enabled_observers_use_durable_schedule_and_recorder(self, last_runs, readers, run_cycle):
        last_runs.return_value = ({"success": True, "last_runs": {"sam_lead_health": "2026-07-19T12:00:00+00:00"}}, 200)
        run_cycle.return_value = {"success": True, "status": "observer_cycle_complete", "runs": []}
        result = charlie_mission_pickup._run_domain_observers(environ={"CHARLIE_DOMAIN_OBSERVERS_ENABLED": "1"})
        self.assertEqual(result["status"], "observer_cycle_complete")
        kwargs = run_cycle.call_args.kwargs
        self.assertEqual(kwargs["last_runs"]["sam_lead_health"], "2026-07-19T12:00:00+00:00")
        self.assertTrue(callable(kwargs["recorder"]))
        readers.assert_called_once()

    @patch("scripts.charlie_mission_pickup.observer_last_runs", return_value=({"success": False, "status": "observer_store_not_configured"}, 503))
    def test_enabled_observers_fail_closed_without_store(self, _last_runs):
        result = charlie_mission_pickup._run_domain_observers(environ={"CHARLIE_DOMAIN_OBSERVERS_ENABLED": "1"})
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "observer_store_not_configured")


if __name__ == "__main__":
    unittest.main()
