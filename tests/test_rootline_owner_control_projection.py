import json
from pathlib import Path
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from modules.telemetry.rootline_owner_control_projection import (
    project_forecast, project_execution_event, build_owner_control_projection,
)

NOW = datetime(2026, 11, 25, 16, tzinfo=timezone.utc)


class OwnerProjectionTests(unittest.TestCase):
    def test_forecast_keeps_actual_provider_and_missing_values(self):
        result = project_forecast({"source": {"attribution_name": "Provider A", "is_stale": True,
            "last_forecast_run_at": NOW.isoformat()}, "days": [{"forecast_date": "2026-11-25",
            "rain_sum_mm": 0, "rain_probability_max_pct": None, "temp_max_c": 24, "wind_max_kmh": "NaN"}]})
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["source"], "Provider A")
        self.assertEqual(result["days"][0]["rain_mm"], 0)
        self.assertIsNone(result["days"][0]["rain_probability_pct"])
        self.assertIsNone(result["days"][0]["wind_kmh"])

    def test_missing_forecast_is_not_zero_rain(self):
        result = project_forecast({"success": False, "message": "No snapshot"})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["days"], [])

    def test_actual_command_receipt_fixture_reports_98_seconds(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/rootline_mixer_accepted_energy_stop.json").read_text())
        row = fixture["history"][-1]
        result = project_execution_event("event-1", NOW, row)
        self.assertEqual(result["device_id"], "mixer")
        self.assertEqual(result["status"], "off_command_accepted")
        self.assertEqual(result["accounted_seconds"], 98)
        self.assertNotIn("command_off_receipt", result)
        self.assertNotIn("provider_capacity_permit", result)

    def test_bad_receipt_cannot_be_promoted_to_off(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/rootline_mixer_accepted_energy_stop.json").read_text())
        row = fixture["history"][-1]
        row["command_off_receipt"]["receipt_sha256"] = "forged"
        result = project_execution_event("event-1", NOW, row)
        self.assertEqual(result["status"], "stop_pending")
        self.assertIsNone(result["accounted_seconds"])

    def test_claim_does_not_mean_command_accepted(self):
        result = project_execution_event("event-1", NOW, {"action": "claim_before_on", "zone_id": "A12345"})
        self.assertEqual(result["status"], "request_claimed")
        self.assertIsNone(result["accounted_seconds"])

    def test_eskom_requires_recorded_authoritative_readback(self):
        row = {"action": "record_eskom_completed", "readback": {"state": "ON", "authoritative": False}}
        self.assertEqual(project_execution_event("x", NOW, row)["status"], "unknown")
        row["readback"]["authoritative"] = True
        self.assertEqual(project_execution_event("x", NOW, row)["status"], "observed_on")

    def test_history_failure_does_not_erase_confirmed_setting_history(self):
        change = {"id": "change-1", "at": NOW.isoformat(), "device_id": "mixer", "kind": "settings_changed"}
        with patch("modules.telemetry.rootline_owner_control_projection.read_execution_projection", side_effect=RuntimeError("private error")):
            result = build_owner_control_projection("history", control_state={"history": [change]}, now=NOW)
        self.assertEqual(result["history"]["status"], "unavailable")
        self.assertEqual(result["history"]["rows"], [change])
        self.assertNotIn("private error", str(result))

    def test_camp_summary_counts_each_closed_execution_once_and_marks_partial(self):
        from modules.telemetry.rootline_owner_control_projection import project_devices
        from modules.telemetry.rootline_owner_controls import project_owner_controls
        event = {"id": "one", "at": NOW.isoformat(), "device_id": "camp_a", "kind": "run_stopped",
            "status": "off_command_accepted", "execution_id": "same-duty", "accounted_seconds": 60,
            "summary": "OFF accepted"}
        devices = project_devices(project_owner_controls([], now=NOW), {}, [event, {**event, "id": "two"}], NOW, truncated=True)
        summary = next(d for d in devices if d["id"] == "camp_a")["run_summary"]
        self.assertEqual(summary["stops"], 1)
        self.assertEqual(summary["accounted_minutes"], 1)
        self.assertTrue(summary["partial"])
        self.assertIn("partial history", summary["summary"])

    def test_paused_device_does_not_advertise_saved_plan_as_next_run(self):
        from modules.telemetry.rootline_owner_control_projection import project_next_action
        from modules.telemetry.rootline_owner_controls import project_owner_controls
        controls = project_owner_controls([], now=NOW)
        controls["devices"]["camp_a"]["mode"] = "paused"
        plan = {"candidate_tasks": [{"task_id": "irrigation_A12345", "planned_start_at": NOW.isoformat()}]}
        self.assertEqual(project_next_action("camp_a", "A12345", controls, plan, NOW), "Paused: no new automatic starts")

    def test_forecast_panel_calls_canonical_reader_only(self):
        with patch("modules.telemetry.rootline_owner_control_projection.get_weather_forecast", return_value=({"days": []}, 200)) as reader, patch("modules.telemetry.rootline_owner_control_projection.read_execution_projection") as execution:
            build_owner_control_projection("forecast", control_state={}, now=NOW, database_url="fixture")
        reader.assert_called_once_with(days=3, database_url="fixture", as_of=NOW)
        execution.assert_not_called()


if __name__ == "__main__":
    unittest.main()
