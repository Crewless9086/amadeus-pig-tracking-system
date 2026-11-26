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


def _command_plan_fixture():
    from copy import deepcopy
    from tests.test_rootline_command_mode import start, receipt, recover
    from modules.telemetry import rootline_command_acceptance as ca
    _, _, store, transport, clock = start(at=NOW)
    active = deepcopy(store.active)
    active["action"] = "mark_active"
    task = {"task_id": "irrigation_" + active["zone_id"],
            "planned_duration_minutes": active["requested_total_duration_seconds"] // 60}
    deadline = ca.command_stop_deadline(active)
    clock[0] = deadline
    complete = recover(store, transport, clock)["execution"]
    complete["action"] = "record_completed"
    return task, active, complete


def test_daily_status_command_job_is_running_then_completed_without_physical_proof():
    from modules.telemetry.rootline_owner_control_projection import project_plan_run
    from modules.telemetry.rootline_command_acceptance import job_completed
    task, active, completed = _command_plan_fixture()
    assert job_completed(completed)
    assert project_plan_run(task, active["operating_date"], [("a", NOW, active)])["run_status"] == "running"
    # Mutable current plan generation is deliberately not a binding criterion.
    task["generation"] = "new-plan-generation"
    assert project_plan_run(task, active["operating_date"], [("c", NOW, completed), ("a", NOW, active)])["run_status"] == "completed"


def test_daily_status_partial_stop_manual_previous_day_and_bad_job_never_complete():
    from copy import deepcopy
    from modules.telemetry.rootline_owner_control_projection import project_plan_run
    task, active, completed = _command_plan_fixture()
    partial = {**completed, "command_job_completed": False}
    assert project_plan_run(task, active["operating_date"], [("p", NOW, partial)])["run_status"] == "stopped"
    for changed in ({"owner_request_id": "manual"}, {"operating_date": "2020-01-01"},
                    {"job_sha256": "forged"}, {"zone_id": "C12345"}):
        value = {**completed, **changed}
        assert project_plan_run(task, active["operating_date"], [("x", NOW, value)])["run_status"] != "completed"
    unresolved = {**active, "action": "record_ambiguous_shutdown"}
    assert project_plan_run(task, active["operating_date"], [("u", NOW, unresolved), ("a", NOW, active)])["run_status"] == "unknown"


def test_daily_status_incomplete_unavailable_and_claim_do_not_invent_progress():
    from modules.telemetry.rootline_owner_control_projection import project_plan_run
    task, active, completed = _command_plan_fixture()
    assert project_plan_run(task, active["operating_date"], [], truncated=True)["run_status"] == "unknown"
    assert project_plan_run(task, active["operating_date"], [], unavailable=True)["run_status"] == "unavailable"
    claim = {**active, "action": "claim_before_on"}
    claim.pop("command_on_receipt")
    assert project_plan_run(task, active["operating_date"], [("q", NOW, claim)])["run_status"] == "unknown"


def test_optional_plan_status_failure_does_not_fail_plan_or_editing_read():
    from modules.telemetry.rootline_owner_controls import get_owner_plan
    task, active, completed = _command_plan_fixture()
    plan = {"daily_program": {"base_tasks": [task]}, "operating_date": active["operating_date"],
            "plan_id": "plan", "generation": 1, "status": "ready"}
    with patch("modules.telemetry.rootline_water_energy_plan.get_current_water_energy_plan", return_value=(plan,200)), \
         patch("modules.telemetry.rootline_owner_controls._started_tasks", return_value=set()), \
         patch("modules.telemetry.rootline_owner_control_projection.connect_bounded_rootline_postgres", side_effect=RuntimeError("private error")) as reader:
        plain = get_owner_plan(object(), NOW)
        assert not reader.called and plain["rows"][0]["editable"] is True
        displayed = get_owner_plan(object(), NOW, include_activity=True)
        assert displayed["rows"][0]["run_status"] == "unavailable"
        assert displayed["rows"][0]["editable"] is True
        assert "private error" not in str(displayed)


def test_owner_next_action_local_time_and_clean_reason_separator():
    from modules.telemetry.rootline_owner_control_projection import project_next_action
    text = project_next_action("camp_a", "A12345", {}, {"candidate_tasks": [
        {"task_id": "irrigation_A12345", "planned_start_at": NOW.isoformat()}]}, NOW)
    assert "SAST" not in text and "18:00" in text
    projected = project_execution_event("x", NOW, {"action": "claim_before_on",
        "zone_id": "A12345", "reason": "weather_hold"})
    assert " - weather hold" in projected["summary"] and "Ã" not in projected["summary"]


# Existing explicitly named disposable-database fixtures; skipped without opt-in.
from tests.test_rootline_owner_controls_postgres import database_url, sql


def test_owner_plan_get_real_postgres_command_history(sql):
    from datetime import timedelta
    import psycopg
    from modules.telemetry import rootline_owner_controls as controls
    from modules.telemetry import rootline_water_energy_plan as planner
    from modules.telemetry import rootline_irrigation_execution_store as execution_store
    from tests.test_rootline_owner_controls_postgres import seed_program
    from tests.test_rootline_command_mode import start, recover
    def insert_at(cursor, action, body, observed_at):
        event_id = execution_store._event_id(action, body)
        payload = execution_store._stored_event_body(action, body, event_id)
        cursor.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,source_agent,event_source,
             recommended_action,review_json,created_at)
            values (%s,%s,%s,%s,%s,%s::jsonb,%s)""",
            (event_id, str(body["execution_id"]), "rootline_backend",
             execution_store.EVENT_SOURCE, action,
             json.dumps({"rootline_execution": payload}, sort_keys=True, separators=(",", ":"), default=str), observed_at))
    saved, at = seed_program(sql)
    _, _, memory, transport, clock = start(at=at)
    active = memory.active
    target = next(t for t in saved["daily_program"]["base_tasks"]
        if t["task_id"] == "irrigation_" + active["zone_id"])
    # The saved canonical programme and actual coordinator fixture must match.
    assert (target.get("requested_total_duration_minutes") or target["planned_duration_minutes"]) * 60 == active["requested_total_duration_seconds"]
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        insert_at(cursor, "mark_active", active, at)
    value, status = controls.get_owner_controls(panel="plan", database_url=sql, now=at+timedelta(minutes=1))
    assert status == 200
    row = next(r for r in value["plan"]["rows"] if r["id"] == target["task_id"])
    assert row["run_status"] == "running"
    clock[0] = at + timedelta(seconds=active["planned_runtime_seconds"]+1)
    completed = recover(memory, transport, clock)["execution"]
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        insert_at(cursor, "record_completed", completed, clock[0])
    value, status = controls.get_owner_controls(panel="plan", database_url=sql, now=clock[0]+timedelta(seconds=1))
    assert status == 200
    assert next(r for r in value["plan"]["rows"] if r["id"]==target["task_id"])["run_status"]=="completed"


def test_later_recovery_or_unbound_terminal_never_leaves_older_running_status():
    from modules.telemetry.rootline_owner_control_projection import project_plan_run
    task, active, completed = _command_plan_fixture()
    for action in ("record_claim_recovery", "record_job_resolution"):
        later = {**active, "action": action}
        assert project_plan_run(task, active["operating_date"], [("z", NOW, later), ("a", NOW, active)])["run_status"] == "unknown"
    malformed = {**completed, "job_sha256": "unbound"}
    assert project_plan_run(task, active["operating_date"], [("z", NOW, malformed), ("a", NOW, active)])["run_status"] == "unknown"
