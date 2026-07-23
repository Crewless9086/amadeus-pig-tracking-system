import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.charlie_executive_watchdog import _idle_recommendations, _observer_recommendations, _queue_idle_brief, supervision_tick


class CharlieExecutiveWatchdogTests(unittest.TestCase):
    def test_reuses_due_observer_recommendations_without_requerying_domains(self):
        observers = {"runs": [{"recommendations": [{"summary": "Fix SAM context"}]}]}
        self.assertEqual(_observer_recommendations(observers), ["Fix SAM context"])
    def test_idle_recommendations_aggregate_all_agent_domains(self):
        readers = {
            "sam_lead_health": lambda: {"recommendations": [{"summary": "Improve SAM replies from owner corrections."}]},
            "ledger_cash_exceptions": lambda: {"recommendations": [{"summary": "Review two payment exceptions."}]},
            "herdmaster_readiness": lambda: {"recommendations": []},
            "beacon_opportunities": lambda: {"recommendations": [{"summary": "Review Beacon backlog."}]},
        }
        self.assertEqual(len(_idle_recommendations(readers=readers)), 3)

    @patch("scripts.charlie_executive_watchdog.queue_outbox")
    def test_idle_brief_is_daily_and_actionable(self, outbox):
        outbox.return_value = ({"success": True, "status": "created"}, 201)
        cycle = {"status_counts": {"blocked": 1}, "queue_health": {"runnable_count": 0}}
        result = _queue_idle_brief(cycle, ["Fix SAM"], now=datetime(2026, 7, 20, 9, tzinfo=ZoneInfo("Africa/Johannesburg")))
        self.assertTrue(result["success"])
        payload = outbox.call_args.args[1]
        self.assertIn("Reply with the recommendation number", payload["private_text"])
        self.assertEqual(outbox.call_args.kwargs["idempotency_key"], "executive-idle:2026-07-20")

    @patch("scripts.charlie_executive_watchdog._deliver_executive_outbox", return_value={"success": True})
    @patch("scripts.charlie_executive_watchdog.queue_due_owner_prompts", return_value=[{"status": "created"}])
    @patch("scripts.charlie_executive_watchdog._queue_idle_brief", return_value={"success": True})
    @patch("scripts.charlie_executive_watchdog._idle_recommendations", return_value=[])
    @patch("scripts.charlie_executive_watchdog._run_domain_observers", return_value={"success": True})
    @patch("scripts.charlie_executive_watchdog.run_executive_cycle")
    def test_starts_core_only_when_executive_selects_runnable_work(self, cycle, _observers, _recommendations, _brief, prompts, _delivery):
        cycle.return_value = ({"cycle": {"commands": [{"action": "ensure_queue_progress"}]}}, 200)
        started = []
        result = supervision_tick(
            runner_reader=lambda: {"active": False, "active_mission_id": ""},
            runner_starter=lambda status_override=None: (started.append(status_override) or {"status": "runner_started"}, 200),
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(started), 1)
        self.assertEqual(result["auction_prompts"], [{"status": "created"}])
        self.assertEqual(prompts.call_args.kwargs["today"].isoformat(), datetime.now(ZoneInfo("Africa/Johannesburg")).date().isoformat())


if __name__ == "__main__":
    unittest.main()
